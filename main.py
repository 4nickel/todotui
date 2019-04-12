#!/usr/bin/env /usr/bin/python3

import re
import os
import subprocess
import copy
from cursed import *
from curses import ascii
from shutil import copyfile
from typing import Dict, Tuple, List

from datetime import date
from enum import Enum

from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

# {{{ TaskFeature

class TaskFeature:

    def __init__(self, todo, name):
        self.todo = todo
        self.name = name
        self.tasks = []

    def __repr__(self):
        return self.name

    def __iter__(self):
        return self.tasks.iter()

    def add_task(self, task):
        self.tasks.append(task)
        return self

    def del_task(self, task):
        self.tasks.remove(task)
        return self

# }}}
# {{{ Context

class Context(TaskFeature):

    def __init__(self, todo, name):
        super().__init__(todo, name)
        todo.contexts[name] = self

    def add_task(self, task):
        self.tasks.append(task)
        return self

    def del_task(self, task):
        self.tasks.remove(task)
        return self

# }}}
# {{{ Project

class Project(TaskFeature):

    def __init__(self, todo, name):
        super().__init__(todo, name)
        todo.projects[name] = self

# }}}
# {{{ Priority

class Priority(TaskFeature):

    def __init__(self, todo, name):
        super().__init__(todo, name)

    def metric(self):
        return float(ord('Z')) - float(ord(self.name)) + 1.0

    def compare(prio):
        if   Priority.metric(self.name) < Priority.metric(prio.name): return -1
        elif Priority.metric(self.name) > Priority.metric(prio.name): return  1
        else: return 0

    def increase(prio):
        if not prio:    return 'Z'
        if prio == 'A': return 'A'
        return chr(ord(prio)-1)

    def decrease(prio):
        if not prio:    return None
        if prio == 'Z': return None
        return chr(ord(prio)+1)

# }}}
# {{{ Date

class Date:

    DONE = 0
    ADD  = 1
    DUE  = 2
    THR  = 3
    AUX  = 4

    def __init__(self, date, kind):
        self.date = date
        self.kind = kind

        # TODO: use r.group(i) instead?
        r = re.match(r'.*:?({})-({})-({})'.format(RE_YYYY, RE_MM, RE_DD), self.date)
        self.yy = int(r.groups()[0])
        self.mm = int(r.groups()[1])
        self.dd = int(r.groups()[2])

    def __repr__(self):
        return "{:>04}-{:>02}-{:>02}".format(self.yy, self.mm, self.dd)

    def format(self):
        return self.date

    def __iter__(self):
        yield self.yy
        yield self.mm
        yield self.dd

    def prefix(i):
        if i == Date.DUE: return DATE_DUE
        if i == Date.THR: return DATE_THR
        return ""

    def metric(self):
        return float(self.yy) * 1000.0 + float(self.mm) * 100.0 + float(self.dd)

    def compare(self, date):
        if   self.yy < date.yy: return -1
        elif self.yy > date.yy: return  1
        elif self.mm < date.mm: return -1
        elif self.mm > date.mm: return  1
        elif self.dd < date.dd: return -1
        elif self.dd > date.dd: return  1
        else: return 0

    def today():
        d = date.today()
        return "{:>04}-{:>02}-{:>02}".format(d.year, d.month, d.day)

# }}}
# {{{ TaskSorter

class TaskSorter:

    def get_projects(self, projects):
        return [(self.tui.get_project(p), m) for p, m in projects]

    def get_contexts(self, contexts):
        return [(self.tui.get_context(c), m) for c, m in contexts]

    def __init__(self, config = {}, context = None):
        if context: over = config_assign(config, self, "name", context.sorters)
        else:       over = False
        self.config, self.tui = config, context

        configure(config, self, over, "m_prio",         "m_prio",        default =  1000)
        configure(config, self, over, "m_done",         "m_done",        default = -1000)
        configure(config, self, over, "m_contexts",     "m_contexts",    default = [], transform = self.get_contexts)
        configure(config, self, over, "m_projects",     "m_projects",    default = [], transform = self.get_projects)
        configure(config, self, over, "m_regexes",      "m_regexes",     default = [])
        configure(config, self, over, "o_split",        "o_split",       default = True)
        configure(config, self, over, "o_group",        "o_group",       default = True)

    def __deepcopy__(self, memo):
        return TaskSorter(config = copy.deepcopy(self.config), context = self.tui)

    def metric_contexts(self, task):
        result = 0
        for context, metric in self.m_contexts:
            if task.has_context(context): result += metric
        return result

    def metric_projects(self, task):
        result = 0
        for project, metric in self.m_projects:
            if task.has_project(project): result += metric
        return result

    def metric_regexes(self, task):
        result = 0
        for regex, metric in self.m_regexes:
            if task.has_regex(regex): result += metric
        return result

    def metric_done(self, task):
        return self.m_done if task.done else 0

    def metric_prio(self, task):
        return task.priority.metric() * self.m_prio if task.priority else 0

    def metric_line(self, task):
        return task.line if task.done else -task.line

    def metric_todo(self, task):
        fns = [
            self.metric_done,
            self.metric_prio,
            self.metric_line,
            self.metric_contexts,
            self.metric_projects,
            self.metric_regexes,
        ]
        metric = 0
        for fn in fns: metric += fn(task)
        return metric

    def group_projects(self, tasks):
        results = {}
        for task in tasks:
            if task.projects:
                for project in task.projects:
                    if not project in results: results[project] = []
                    results[project].append(task)
            else:
                if not self.tui.none_project in results: results[self.tui.none_project] = []
                results[self.tui.none_project].append(task)
        return results

    def group_contexts(self, tasks):
        results = {}
        for task in tasks:
            if task.contexts:
                for context in task.contexts:
                    if not context in results: results[context] = []
                    results[context].append(task)
            else:
                if not self.tui.none_context in results: results[self.tui.none_context] = []
                results[self.tui.none_context].append(task)
        return results

    def sort_groups(self, groups):
        results = []
        for key in groups:
            results.extend(sorted(groups[key], key = lambda task: self.metric_todo(task), reverse = True))
        return results

    def split(self, tasks):
        todo = []
        done = []
        for task in tasks:
            if task.done: done.append(task)
            else:         todo.append(task)
        return (todo, done)

    def sorted(self, tasks):
        if self.o_split: todo, done = self.split(tasks)
        else:            todo, done = (tasks, [])

        if self.o_group:
            todo = self.sort_groups(self.group_projects(todo))
            done = sorted(done, key = lambda task: self.metric_done(task), reverse = True)
        else:
            todo = sorted(todo, key = lambda task: self.metric_todo(task), reverse = True)
            done = sorted(done, key = lambda task: self.metric_done(task), reverse = True)
        return todo + done

# }}}
# {{{ TaskFilter

class TaskFilter:

    def get_projects(self, projects):
        return [(self.tui.get_project(p), m) for p, m in projects]

    def get_contexts(self, contexts):
        return [(self.tui.get_context(c), m) for c, m in contexts]

    def toggle_threshold(self):
        if self.threshold:
            self.threshold_prev = self.threshold
            self.threshold = None
        else:
            self.threshold = self.threshold_prev

    def __init__(self, config = {}, context = None):
        if context: over = config_assign(config, self, "name", context.filters)
        else:       over = False
        self.config, self.tui = config, context

        configure(config, self, over, "done",           "done",           default = None)
        configure(config, self, over, "archived",       "archived",       default = None)
        configure(config, self, over, "empty",          "empty",          default = None)
        configure(config, self, over, "threshold",      "threshold",      default = None)
        configure(config, self, over, "threshold_implied", "threshold_implied", default = True)
        configure(config, self, over, "contexts",       "contexts",       default = [], transform = self.get_contexts)
        configure(config, self, over, "projects",       "projects",       default = [], transform = self.get_projects)
        configure(config, self, over, "regexes",        "regexes",        default = [])
        self.threshold_prev  = None

    def __deepcopy__(self, memo):
        return TaskFilter(config = copy.deepcopy(self.config), context = self.tui)

    def match_threshold(self, task, threshold, mode):
        if self.threshold is None: return True
        elif not task.date_thr:    return self.threshold_implied
        else:
            compare = Date.compare(task.date_thr, threshold)
            return compare <= 0 if mode else compare > 0

    def match_today(self, task):
        return self.match_threshold(task, Date(Date.today(), Date.THR), self.threshold)

    def match_bool(self, a, b):
        return a == b if a is not None else True

    def match_done(self, task):
        return self.match_bool(self.done, task.done)

    def match_archived(self, task):
        return self.match_bool(self.archived, task.archived)

    def match_empty(self, task):
        return self.match_bool(self.empty, task.empty)

    def match_regexes(self, task):
        for regex, mode in self.regexes:
            if task.has_regex(regex) != mode: return False
        return True

    def match_projects(self, task):
        for project, mode in self.projects:
            if task.has_project(project) != mode: return False
        return True

    def match_contexts(self, task):
        for context, mode in self.contexts:
            if task.has_context(context) != mode: return False
        return True

    def match(self, task):
        fns = [
            self.match_done,
            self.match_archived,
            self.match_empty,
            self.match_projects,
            self.match_contexts,
            self.match_regexes,
            self.match_today
        ]
        for fn in fns:
            if fn(task) == False: return False
        return True

    def filter(self, tasks):
        return filter(lambda task: task if self.match(task) else None, tasks)

# }}}
# {{{ TaskParser

class TaskParser:

    def __init__(self):
        pass

    def tokenize(self, text):
        return re.findall(r'([ \t\n\r\f\v]+|\S+)', text)

    def match_context(self, string):
        return re.match(r'^{}$'.format(RE_CONTEXT), string)

    def match_project(self, string):
        return re.match(r'^{}$'.format(RE_PROJECT), string)

    def match_priority(self, string):
        return re.match(r'^{}$'.format(RE_PRIORITY), string)

    def match_date(self, string):
        return re.match(r'^{}$'.format(RE_DATE), string)

    def match_metadate(self, string):
        return re.match(r'^{}$'.format(RE_METADATE), string)

    def match_done(self, string):
        return string == 'x'

    def populate(self, task):

        tokens = self.tokenize(task.text)
        result = []
        tdates = []
        mdates = []
        adates = []
        dlimit = 3
        task.done = False

        skip = False
        for index, token in enumerate(tokens):
            if skip:
                skip = False
                continue

            # Done flag / priority must come first
            if index == 0:
                if self.match_done(token):
                    task.done = True
                    dlimit = 5
                    skip = True
                    continue
                elif self.match_priority(token):
                    task.set_priority(token[1:-1])
                    dlimit = 5
                    skip = True
                    continue

            # Date handling is a bit complicated
            if self.match_date(token):
                if index <= dlimit and len(tdates) <= 2:
                    date = Date(token, None)
                    tdates.append(date)
                    skip = True
                    continue
                else:
                    date = Date(token, Date.AUX)
                    adates.append(date)
                    result.append(date)
                    continue
            elif self.match_metadate(token):
                date = Date(token, None)
                mdates.append(date)
                result.append(date)
                continue

            # Context and project are straight forward
            elif self.match_context(token):
                result.append(task.set_context(token))
                continue
            elif self.match_project(token):
                result.append(task.set_project(token))
                continue
            else:
                result.append(token)
                continue

        # Figure out which date is which
        if len(tdates) == 2:
            tdates[0].kind = Date.DONE
            tdates[1].kind = Date.ADD
        if len(tdates) == 1:
            if task.done: tdates[0].kind = Date.DONE
            else:         tdates[0].kind = Date.ADD

        # Meta-dates get some special consideration
        for date in mdates:
            if date.date.startswith(Date.prefix(Date.DUE)):
                date.kind = Date.DUE
                task.set_date(date)
            if date.date.startswith(Date.prefix(Date.THR)):
                date.kind = Date.THR
                task.set_date(date)
            else:
                # Unknown meta-dates are added to aux
                date.kind = Date.AUX
                mdates.remove(date)
                adates.append(date)
                task.set_date(date)

        for date in tdates: task.set_date(date)
        for date in mdates: task.set_date(date)
        for date in adates: task.set_date(date)

        task.tokens = result

# }}}
# {{{ TaskPrinter

class TaskPrinter:

    def __init__(self, config = {}, context = None):
        self.tui                = context
        name = config_get(config, "name", default = None)
        if name:
            printer = self.tui.printers[name]
            self.show_line      = printer.show_line
            self.show_done      = printer.show_done
            self.show_projects  = printer.show_projects
            self.show_contexts  = printer.show_contexts
            self.show_priority  = printer.show_priority
            self.show_dates     = printer.show_dates
            self.show_datekinds = printer.show_datekinds
        else:
            self.show_line      = config_get(config, "show_line",      default = False)
            self.show_done      = config_get(config, "show_done",      default = True)
            self.show_projects  = config_get(config, "show_projects",  default = True)
            self.show_contexts  = config_get(config, "show_contexts",  default = True)
            self.show_priority  = config_get(config, "show_priority",  default = True)
            self.show_dates     = config_get(config, "show_dates",     default = True)
            self.show_datekinds = config_get(config, "show_datekinds", default = True)

    def format(self, task):

        strings = []

        if self.show_line:
            strings.extend(['{:02}'.format(task.line), ' '])

        if task.done:
            if self.show_done:
                strings.extend(['x', ' '])
        else:
            if self.show_priority and task.priority:
                strings.extend(['({})'.format(str(task.priority)), ' '])

        if self.show_dates:
            if task.date_done: strings.extend([str(task.date_done), ' '])
            if task.date_add:  strings.extend([str(task.date_add), ' '])

        for index, token in enumerate(task.tokens):
            if type(token) == str: strings.append(token)
            elif  self.show_projects  and type(token) == Project: strings.append(str(token))
            elif  self.show_contexts  and type(token) == Context: strings.append(str(token))
            elif  self.show_datekinds and type(token) == Date:    strings.append(token.format())

        return ''.join(strings).strip()

# }}}
# {{{ TaskSeperator

class TaskSeperator:

    def __init__(self, offset, width, string, glyph):
        self.offset = offset
        self.width  = width
        self.string = string
        self.glyph  = glyph

    def from_string(string):
        for s in SEPERATORS:
            if s.string == string:
                return s
        return None

# }}}
# {{{ TaskField

class TaskField:

    def __init__(self, width, title, string):
        self.width = width
        self.title = title
        self.string = string

    def from_string(string):
        for f in FIELDS:
            if f.string == string:
                return f
        raise(Exception("Invalid key string: {}".format(string)))

    def from_strings(field_strings):
        return [TaskField.from_string(s) for s in field_strings]

# }}}
# {{{ Task

class Task:

    def __init__(self, todo, line, archived, text):
        self.todo      = todo
        self.line      = line
        self.text      = text
        self.archived  = archived
        self.empty     = len(text) == 0
        self.date_done = None
        self.date_add  = None
        self.date_due  = None
        self.date_thr  = None
        self.priority  = None
        self.date_aux  = []
        self.projects  = []
        self.contexts  = []
        self.tokens    = []
        TASK_PARSER.populate(self)

    def __repr__(self):
        return "{} [{}]".format(self.text, self.id)

    def clear(self):
        self.delete_features()
        self.text       = ""
        self.done       = False
        self.archived   = False
        self.empty      = True
        self.date_done  = None
        self.date_add   = None
        self.date_due   = None
        self.date_thr   = None
        self.tokens.clear()

    def set_date(self, date):
        if   date.kind == Date.DONE: self.date_done = date
        elif date.kind == Date.ADD:  self.date_add  = date
        elif date.kind == Date.DUE:  self.date_due  = date
        elif date.kind == Date.THR:  self.date_thr  = date
        elif date.kind == Date.AUX:  self.date_aux.append(date)
        else: raise(Exception("Invalid date kind {}".date.kind))

    def set_context(self, name):
        context = self.todo.tui.get_context(name).add_task(self)
        self.contexts.append(context)
        return context

    def set_project(self, name):
        project = self.todo.tui.get_project(name).add_task(self)
        self.projects.append(project)
        return project

    def set_priority(self, name):
        if self.priority: self.unset_priority()
        self.priority = self.todo.tui.get_priority(name).add_task(self) if name else None
        return self.priority

    def remove_token(self, token):
        index = self.tokens.index(token)
        if index > 0: index -= 1
        try:
            self.tokens.remove(self.tokens[index])
            self.tokens.remove(self.tokens[index])
        except:
            pass

    def unset_context(self, name):
        context = self.todo.tui.get_context(name, create = False)
        context.del_task(self)
        self.contexts.remove(context)
        self.remove_token(context)

    def unset_project(self, name):
        project = self.todo.tui.get_project(name, create = False)
        project.del_task(self)
        self.projects.remove(project)
        self.remove_token(project)

    def unset_priority(self):
        if self.priority: self.priority.del_task(self)
        self.priority = None

    def add_project(self, name):
        project = self.set_project(name)
        self.tokens.extend([' ', project])

    def add_context(self, name):
        context = self.set_context(name)
        self.tokens.extend([' ', context])

    def add_contexts(self, names):
        for name in names: self.add_context(name)

    def add_projects(self, names):
        for name in names: self.add_project(name)

    def has_project(self, project):
        for p in self.projects:
            if p.name == project.name: return True
        return False

    def has_context(self, context):
        for c in self.contexts:
            if c.name == context.name: return True
        return False

    def has_regex(self, regex):
        return re.search(regex, self.text) is not None

    def match(self, task_filter):
        return task_filter.match(self)

    def archive(self):
        if not self.done: raise(Exception("Attempt to archive active to-do\n"))
        if self.empty:    raise(Exception("Attempt to archive empty to-do\n"))
        self.archived = True
        self.todo.todo_tasks.remove(self)
        self.todo.done_tasks.append(self)
        self.line = len(self.todo.done_tasks)

    def do(self, today = True):
        self.done = True
        if today: self.date_done = Date(Date.today(), Date.DONE)

    def undo(self):
        self.done = False
        self.date_done = None

    def pinc(self):
        self.set_priority(Priority.increase(self.priority.name if self.priority else None))

    def pdec(self):
        self.set_priority(Priority.decrease(self.priority.name if self.priority else None))

    def delete_features(self):
        for p in self.projects.copy(): self.unset_project(p.name)
        for c in self.contexts.copy(): self.unset_context(c.name)
        self.unset_priority()

# }}}
# {{{ TodoTxt

class TodoTxt:

    def __init__(self, tui, config):
        command           = ['/usr/bin/todo-txt', '-f']
        self.tui          = tui
        self.config       = config
        self.todo_file    = config["todo"]
        self.done_file    = config["done"]
        self.report_file  = config["report"]
        self.todo_mtime   = None
        self.done_mtime   = None
        self.todo_tasks   = []
        self.done_tasks   = []

    def update_mtime(self):
        todo_mtime = os.path.getmtime(self.todo_file)
        done_mtime = os.path.getmtime(self.done_file)
        if self.has_changed(todo_mtime, done_mtime):
            self.todo_mtime = todo_mtime
            self.done_mtime = done_mtime
            return True
        return False

    def update(self):
        if self.update_mtime():
            for task in self.todo_tasks: task.clear()
            for task in self.done_tasks: task.clear()
            self.todo_tasks = self.read_tasks(self.todo_file, archived = False)
            self.done_tasks = self.read_tasks(self.done_file, archived = True)
            return True
        return False

    def has_changed(self, todo_mtime, done_mtime):
        if self.todo_mtime != todo_mtime or self.done_mtime != done_mtime:
            return True
        return False

    def read_tasks(self, file_name, archived):
        lines = []
        tasks = []
        with open(file_name) as f:
            lines = f.readlines()
        for i, l in enumerate([l.strip() for l in lines]):
            tasks.append(Task(self, i+1, archived, l))
        return tasks

    def write_task(self, fd, task):
        fd.write("{}\n".format(TODO_PRINTER.format(task)))

    def write_todo(self, empty = True):
        self.todo_backup()
        with open(self.todo_file, "w") as fd:
            for task in self.todo_tasks:
                if task.empty and not empty: continue
                self.write_task(fd, task)

    def write_archive(self):
        self.todo_backup()
        with open(self.done_file, "w") as fd:
            for task in self.done_tasks:
                self.write_task(fd, task)

    def todo_pinc(self, tasks = []):
        for task in tasks: task.pinc()
        self.write_todo()

    def todo_pdec(self, tasks = []):
        for task in tasks: task.pdec()
        self.write_todo()

    def todo_rm(self, tasks = []):
        for task in tasks: task.clear()
        self.write_todo()

    def todo_do(self, tasks = [], today = True):
        for task in tasks: task.do()
        self.write_todo()

    def todo_undo(self, tasks = []):
        for task in tasks:
            task.done = False
            task.date_done = None
        self.write_todo()

    def todo_add(self, tasks = [], today = True):
        with open(self.todo_file, "a") as fd:
            for task in tasks:
                if today: task.date_add = Date(Date.today(), Date.ADD)
                self.write_task(fd, task)

    def todo_archive(self):
        done = [task for task in self.todo_tasks if task.done]
        for task in done: task.archive()
        self.write_todo(empty = False)
        self.write_archive()

    def todo_environment(self):
        environment = os.environ.copy()
        environment["TODO_FILE"]   = self.todo_file
        environment["DONE_FILE"]   = self.done_file
        environment["REPORT_FILE"] = self.report_file
        return environment

    def todo_command(self, action, options = [], arguments = []):
        command = self.command.copy()
        command.extend(options)
        command.append(action)
        command.extend(arguments)
        process = subprocess.Popen(command, env = self.todo_environment(),
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE)

    def todo_backup(self):
        copyfile(self.todo_file, "{}.bak".format(self.todo_file))

    def todo_restore(self):
        copyfile("{}.bak".format(self.todo_file), self.todo_file)

# }}}
# {{{ TextInput

class TextInput:

    def __init__(self, text = "", cursor = True):
        self.text   = text
        self.cursor = cursor

    def __repr__(self):
        return "{}{}".format(self.text, Line.UNICODE_BLOCK_L18 if self.cursor else "")

    def backspace(self):
        self.text = self.text[:-1]

    def input(self, char):
        if char == curses.KEY_BACKSPACE:
            self.backspace()
            return True
        elif curses.ascii.isprint(chr(char)):
            self.text += chr(char)
            return True
        return False

# }}}
# {{{ TextInputPopup

class TextInputPopup(CenteredPopup):

    WIDTH  = 80
    HEIGHT = 3

    def __init__(self, tui, title):
        super().__init__(tui, TextInputPopup.WIDTH, TextInputPopup.HEIGHT, title)
        self.input = TextInput()

    def handle_input(self, char):
        if super().handle_input(char): return True
        if not self.input.input(char):
            if   char == Key.ENTER:  self.accept()
            elif char == Key.ESCAPE: self.cancel()
        return False

    def draw(self):
        super().draw()
        self.window.put(1, 1, ' {}'.format(str(self.input)))

    def cancel(self):
        super().cancel()

# }}}
# {{{ EditPopup

class Option:

    def __init__(self, name, key, value = None, transform = None):
        self.name      = name
        self.key       = key
        self.transform = transform
        self.value     = value

    def __repr__(self):
        return str(self.value)

    def select_key(self, context = None, position = None):
        pass

    def select_val(self, context = None, position = None):
        pass

    def select_del(self, context = None, position = None):
        pass

    def select_add(self, context = None, position = None):
        pass

    def apply(self, obj):
        obj.__dict__[self.key] = self.transform(self.value) if self.transform else self.value

    def get_name(self):
        return self.name

class ListElementOption(Option):

    def __init__(self, name, index, value, transform = None):
        super().__init__(name, index, value, transform)

    def apply(self, obj):
        obj[self.key] = self.transform(self.value) if self.transform else self.value

    def select_add(self, context = None, position = None):
        context.options.append(None)

    def select_del(self, context = None, position = None):
        context.options.remove(self)
        context.height -= 1
        if context.cursor > 0: context.cursor -= 1
        context.window.resize(context.width, context.height)

class BoolOption(Option):

    TRUE  = "Yes"
    FALSE = "No"

    def __init__(self, name, key, value = False):
        super().__init__(name, key, value)

    def __repr__(self):
        return BoolOption.TRUE if self.value else BoolOption.FALSE

    def toggle(self):
        self.value = not self.value

    def set(self):
        self.value = True

    def unset(self):
        self.value = False

    def select_val(self, context = None, position = None):
        self.toggle()

class NullableBoolOption(Option):

    NONE = "Ignore"

    def __init__(self, name, key, value = None):
        super().__init__(name, key, value)

    def __repr__(self):
        if self.value is None: return NullableBoolOption.NONE
        else: return BoolOption.TRUE if self.value else BoolOption.FALSE

    def cycle(self):
        if    self.value == True:  self.value = False
        elif  self.value == False: self.value = None
        else:                      self.value = True

    def ignore(self):
        self.value = None

    def positive(self):
        self.value = True

    def negative(self):
        self.value = False

    def select_val(self, context = None, position = None):
        self.cycle()

class StringBoolListElementOption(ListElementOption):

    def __init__(self, name, index, value, transform = None):
        super().__init__(name, index, value, transform)
        self.input = None

    def toggle(self):
        self.value = not self.value

    def apply(self, obj):
        val = self.transform((self.name, self.value)) if self.transform else (self.name, self.value)
        if self.key == len(obj):
            obj.append(val)
        else:
            obj[self.key] = val

    def accept(self, context = None, position = None):
        if context.input.text == "":
            self.select_del(context, position)
        else:
            self.name = context.input.text
        self.input = None
        context.input = None

    def cancel(self, context = None, position = None):
        self.input = None
        context.input = None

    def select_key(self, context = None, position = None):
        self.input = TextInput(text = self.name)
        context.input = self.input

    def select_val(self, context = None, position = None):
        self.toggle()

    def get_name(self):
        if self.input: return str(self.input)
        return super().get_name()

class ListEditOption(Option):

    def __init__(self, name, key, value = [], transform = None, element = None, title = "List"):
        super().__init__(name, key, value, transform)
        self.title   = title
        self.element = element

    def __repr__(self):
        return "Edit"

    def select_val(self, context = None, position = None):
        options = []

        for index, element in enumerate(self.value):
            obj, val = element
            options.append(StringBoolListElementOption(str(obj), index, val, transform = self.element))

        OptionListPopup(context, position.x, position.y, context.width, len(self.value) + 2, self.title, self.value, options, element = self.element)

class OptionPopup(ModalPopup):

    def __init__(self, tui, x, y, width, height, title, obj, options):
        super().__init__(tui, x, y, width, height, title)
        self.tui     = tui
        self.obj     = obj
        self.options = options
        self.cursor  = 0
        self.scroll  = 0
        self.input   = None

    def cursor_next(self):
        if len(self.options) > 0: self.cursor = (self.cursor + 1) % len(self.options)

    def cursor_prev(self):
        if len(self.options) > 0: self.cursor = (self.cursor - 1) % len(self.options)

    def child_position(self):
        return Point(self.position.x, self.position.y + self.height)

    def select_add(self, context = None, position = None):
        pass

    def cursor_select_add(self):
        self.select_add(self, self.child_position())

    def cursor_select_del(self):
        if len(self.options) > 0: self.options[self.cursor].select_del(self, self.child_position())

    def cursor_select_val(self):
        if len(self.options) > 0: self.options[self.cursor].select_val(self, self.child_position())

    def cursor_select_key(self):
        if len(self.options) > 0: self.options[self.cursor].select_key(self, self.child_position())

    def handle_input(self, char):

        # If there is an input active, delegate to it
        if self.input:
            if not self.input.input(char):
                try:
                    if   char == Key.ESCAPE: self.options[self.cursor].cancel(self)
                    elif char == Key.ENTER:  self.options[self.cursor].accept(self)
                except: raise(Exception("{} : {}".format(len(self.options), self.cursor)))
            return True

        if super().handle_input(char): return True
        elif char == Key.SPACE:  self.cursor_select_val()
        elif char == Key.SSPACE: self.cursor_select_key()
        elif char == ord('a'):   self.cursor_select_add()
        elif char == ord('d'):   self.cursor_select_del()
        elif char == ord('j'):   self.cursor_next()
        elif char == ord('k'):   self.cursor_prev()
        else: return False
        return True

    def accept(self):
        for option in self.options:
            option.apply(self.obj)
        self.cancel()

    def draw(self):
        super().draw()
        for line, option in enumerate(self.options):
            if line == self.cursor and self.mode == OptionPopup.WIDGET: color = curses.color_pair(4)
            else: color = curses.color_pair(0)
            self.window.put(1, line+1, " {:<28}{:>28} ".format(option.get_name(), str(option)), color)

    def cancel(self):
        super().cancel()

# }}}

class OptionListPopup(OptionPopup):

    def __init__(self, tui, x, y, width, height, title, obj, options, element = None):
        super().__init__(tui, x, y, width, height, title, obj, options)
        self.element = element

    def select_add(self, context = None, position = None):
        element = StringBoolListElementOption("", len(context.options), True, transform = self.element)
        self.height += 1
        if self.options: self.cursor += 1
        self.options.append(element)
        self.window.resize(self.width, self.height)
        element.select_key(context = self, position = position)

    def accept(self):
        for option in self.options:
            option.apply(self.obj)

        while len(self.obj) > len(self.options):
            self.obj.remove(self.obj[len(self.obj) - 1])

        self.cancel()

# {{{ TaskAddPopup

class TaskAddPopup(TextInputPopup):

    def __init__(self, tui, view):
        super().__init__(tui, "Add Task")
        self.view  = view

    def task(self):
        task = Task(self.view.todo, len(self.view.todo.todo_tasks), False, self.input.text)
        task.add_contexts(self.view.add_contexts)
        task.add_projects(self.view.add_projects)
        return task

    def accept(self):
        if len(self.input.text) > 0:
            task = self.task()
            self.view.todo.todo_add([self.task()])
        self.cancel()

# }}}
# {{{ TodoView

class TodoViewState:

    def __init__(self):
        self.cursor = 0
        self.scroll = 0
        self.max_x  = 0
        self.max_y  = 0
        self.layout = None

class FieldLayout:

    def __init__(self, sep: int, txt: int, width: int):
        self.sep   = sep
        self.txt   = txt
        self.width = width

class FieldsLayout:

    def __init__(self, fields: List[TaskField], seperator: TaskSeperator, total_width: int):
        self.seperator    = seperator
        self.total_width  = total_width
        self.fields       = fields
        self.widths       = []
        self.layout       = {}

        self.spread_layout()
        self.create_layout()

    def __getitem__(self, key: TaskField):
        return self.layout[key]

    def __setitem__(self, key: TaskField, val: FieldLayout):
        self.layout[key] = val

    def create_layout(self):
        self.layout.clear()
        x = 0
        for index, (field, width) in enumerate(list(zip(self.fields, self.widths))):
            sep = x
            if index > 0: x += self.seperator.width
            x += self.seperator.offset
            txt = x
            x += width
            x += self.seperator.offset
            self.layout[field] = FieldLayout(sep, txt, width)

    def spread_layout(self):
        results = []
        indices = []
        accumulator = 0

        for index, field in enumerate(self.fields):
            fwidth = field.width
            if index == 0: cwidth = self.seperator.offset * 2
            else:          cwidth = self.seperator.offset * 2 + self.seperator.width
            accumulator += cwidth + fwidth
            if fwidth == 0: indices.append(index)
            results.append(fwidth)

        if indices:
            border_width = 2
            rest = self.total_width - (accumulator + border_width)
            size = int(rest / len(indices) if len(indices) > 0 else 0)
            for index in indices:
                results[index] = size
            # space left due to rounding inaccuracies is added to the first possible column
            results[indices[0]] += rest - (size * len(indices))

        self.widths = results


class TodoView(View):

    def __init__(self, tui, name, config = {}):
        super().__init__(tui, name)
        self.config       = config
        self.tui          = tui
        self.todo         = tui.todos[config_get(config, "todo")]
        self.title        = config_get(config, "title",        default = "Todo")
        self.task_filter  = config_get(config, "filter",       default = DEFAULT_FILTER,    transform = TaskFilter,  context = self.tui)
        self.task_sorter  = config_get(config, "sorter",       default = DEFAULT_SORTER,    transform = TaskSorter,  context = self.tui)
        self.task_printer = config_get(config, "printer",      default = DEFAULT_PRINTER,   transform = TaskPrinter, context = self.tui)
        self.border       = config_get(config, "border",       default = True)
        self.columns      = config_get(config, "columns",      default = DEFAULT_COLUMNS,   transform = TaskField.from_strings)
        self.seperator    = config_get(config, "seperator",    default = DEFAULT_SEPERATOR, transform = TaskSeperator.from_string)
        self.add_contexts = config_get(config, "add_contexts", default = [])
        self.add_projects = config_get(config, "add_projects", default = [])
        self.todo_mtime   = None
        self.done_mtime   = None
        self.status       = ""

        self.done_count   = 0
        self.todo_count   = 0
        self.total_count  = 0

    def substitute(self, string: str):
        return Util.substitute(string, {
            't':self.todo_count,
            'c':self.todo_count + self.done_count,
            'd':self.done_count,
            'f':self.todo.todo_file,
            'p':((self.todo_count + self.done_count)) * 100
        })

    def init_state(self):
        return TodoViewState()

    def has_changed(self):
        if self.todo_mtime != self.todo.todo_mtime or self.done_mtime != self.todo.done_mtime:
            return True
        return False

    def update_mtime(self):
        if self.todo.update() or self.has_changed():
            self.todo_mtime = self.todo.todo_mtime
            self.done_mtime = self.todo.done_mtime
            return True
        return False

    def update(self, cell: LayoutCell, force: bool = False):
        if self.update_mtime() or force:
            self.update_tasks()
            self.update_layout(cell)
            self.update_cursor(cell)
            return True
        return False

    def update_cursor(self, cell: LayoutCell):
        state = self.state(cell)
        other_lines = 4
        state.scroll = Util.scroll(state.scroll, state.cursor, 5, state.max_y-other_lines, len(self.tasks)-1)
        state.cursor = Util.clamp(state.cursor, 0, len(self.tasks)-1)

    def update_layout(self, cell: LayoutCell):
        state = self.state(cell)
        state.max_y = cell.max_y()
        state.max_x = cell.max_x()
        state.layout = FieldsLayout(self.columns, self.seperator, state.max_x)

    def update_tasks(self):
        self.tasks = self.task_sorter.sorted(self.task_filter.filter(self.todo.todo_tasks + self.todo.done_tasks))
        self.done_count = 0
        self.todo_count = 0
        self.total_count = self.todo_count + self.done_count
        self.todo_percent = self.todo_count / self.total_count * 100.0 if self.total_count != 0 else 0
        self.done_percent = self.done_count / self.total_count * 100.0 if self.total_count != 0 else 0
        for task in self.tasks:
            if task.done: self.done_count += 1
            else:         self.todo_count += 1

    def task(self, index: int):
        return self.tasks[index]

    def cursor_task(self, cell: LayoutCell):
        return self.task(self.state(cell).cursor)

    def task_command(self, cell: LayoutCell, action: str):
        self.todo.todo_command(action, [str(self.cursor_task(cell).line)])

    def field_string(self, task: Task, field: TaskField):
        if   field == FIELD_LINE:      return '{:>02}'.format(str(task.line))
        elif field == FIELD_TEXT:      return self.task_printer.format(task)
        elif field == FIELD_DONE:      return 'x' if task.done else ''
        elif field == FIELD_PROJECT:   return ' '.join([str(p) for p in task.projects])
        elif field == FIELD_CONTEXT:   return ' '.join([str(c) for c in task.contexts])
        elif field == FIELD_METRIC:    return '{:>2}'.format(self.task_sorter.metric_todo(task) if not task.done else self.task_sorter.metric_done(task))
        elif field == FIELD_PRIORITY:  return str(task.priority)  if task.priority  else ''
        elif field == FIELD_DATE_DONE: return str(task.date_done) if task.date_done else ''
        elif field == FIELD_DATE_ADD:  return str(task.date_add)  if task.date_add  else ''
        elif field == FIELD_DATE_DUE:  return str(task.date_due)  if task.date_due  else ''
        elif field == FIELD_DATE_THR:  return str(task.date_thr)  if task.date_thr  else ''
        else:                          raise(Exception("Invalid Enum"))

    def handle_input(self, cell: LayoutCell, char: int):
        state = self.state(cell)
        if   char == ord('q'):      self.tui.exit = True
        elif char == ord('j'):      state.cursor += 1
        elif char == ord('k'):      state.cursor -= 1
        elif char == ord('a'):      TaskAddPopup(cell.tui().layout, self)
        elif char == ord('p'):      self.todo.todo_pinc([self.cursor_task(cell)])
        elif char == ord('P'):      self.todo.todo_pdec([self.cursor_task(cell)])
        elif char == ord('A'):      self.todo.todo_archive()
        elif char == ord('r'):      self.todo.todo_rm([self.cursor_task(cell)])
        elif char == ord('d'):      self.todo.todo_do([self.cursor_task(cell)])
        elif char == ord('u'):      self.todo.todo_undo([self.cursor_task(cell)])
        elif char == ord('U'):      self.update(cell, force = True)
        elif char == ord('J'):      cell.parent.cursor_next()
        elif char == ord('K'):      cell.parent.cursor_prev()
        elif char == ord('H'):      cell.parent.parent.cursor_prev()
        elif char == ord('L'):      cell.parent.parent.cursor_next()
        elif char == ord('f'):
            OptionPopup(cell.tui().layout, 40, 20, 60, 10, "Edit Filter", self.task_filter, [
                NullableBoolOption("Done",      "done",              value = self.task_filter.done),
                NullableBoolOption("Archived",  "archived",          value = self.task_filter.archived),
                NullableBoolOption("Empty",     "empty",             value = self.task_filter.empty),
                NullableBoolOption("Threshold", "threshold",         value = self.task_filter.threshold),
                BoolOption("Threshold Implied", "threshold_implied", value = self.task_filter.threshold_implied),
                ListEditOption("Contexts",      "contexts",          value = self.task_filter.contexts.copy(), element = self.tui.get_context_option, title = "Contexts"),
                ListEditOption("Projects",      "projects",          value = self.task_filter.projects.copy(), element = self.tui.get_project_option, title = "Projects"),
                ListEditOption("Regexes",       "regexes",           value = self.task_filter.regexes.copy(), title = "Regexes"),
            ])
        elif char == ord('T'):
            self.task_filter.toggle_threshold()
            self.update(cell, force = True)
        elif char == 21:            state.cursor -= int(cell.height()/2)
        elif char == 4:             state.cursor += int(cell.height()/2)
        elif char == Key.TAB:       cell.cursor_next()
        elif char == Key.STAB:      cell.cursor_prev()
        elif char == curses.KEY_RESIZE:
            self.tui.resize()
            self.tui.layout.update()
        self.update_cursor(cell)
        self.status = str(char)

    def column_line(self, state: TodoViewState, x: int, y: int, field: TaskField):
        offset = state.layout[field].sep
        return Line(Point(x+offset, y), Point(x+offset, state.max_y))

    def column_lines(self, state: TodoViewState, x: int, y: int):
        lines = []
        if self.seperator.width == 0: return lines

        for index, field in enumerate(self.columns):
            if index > 0: lines.append(self.column_line(state, x, y, field))
        return lines

    def row_lines(self, state: TodoViewState, x: int, y: int):
         return [Line(Point(x, y), Point(state.max_x, y))]

    def draw_field(self, cell: LayoutCell, state: TodoViewState, x: int, y: int, task: Task, field: TaskField, cursor: int = -1):
        offset = state.layout[field].txt
        if cursor == state.cursor: color = COLOR_TASK_CURSOR
        else:                      color = COLOR_TASK_DONE if task.done else COLOR_TASK_DEFAULT
        cell.window.put(x+offset, y, self.field_string(task, field), curses.color_pair(color))

    def draw_task(self, cell: LayoutCell, state: TodoViewState, x: int, y: int, task: Task, cursor: int):
        for index, field in enumerate(self.columns):
            self.draw_field(cell, state, x, y, task, field, cursor = cursor)

    def draw_tasks(self, cell: LayoutCell, state: TodoViewState, x: int, y: int):
        tasks = self.tasks[state.scroll:state.scroll+state.max_y-y]
        for line, task in enumerate(tasks):
            self.draw_task(cell, state, x, y+line, task, line+state.scroll)

    def draw_titles(self, cell: LayoutCell, state, x: int, y: int):
        for index, field in enumerate(self.columns):
            offset = state.layout[field].txt
            width  = state.layout[field].width
            string = self.substitute(self.title) if field == FIELD_TEXT else field.title
            cell.window.put(x+offset, y, string)

    def draw_status(self, cell: LayoutCell, state: TodoViewState, x: int):
        offset = state.layout[FIELD_TEXT].txt
        width  = state.layout[FIELD_TEXT].width
        cell.window.put(x + offset + width - len(self.status), 1, self.status)

    def draw(self, cell: LayoutCell):
        self.update(cell)
        state = self.state(cell)

        cell.add_lines(self.column_lines(state, 1, 0))
        cell.add_lines(self.row_lines(state, 0, 2))

        self.draw_titles(cell, state, 1, 1)
        self.draw_status(cell, state, 1)
        self.draw_tasks(cell, state, 1, 3)

# }}}
# {{{ Tui

class Tui:

    def __init__(self, screen, config_file):
        self.screen      = screen
        self.config_file = config_file

        self.curses_settings()
        self.screen_settings()

        self.projects = {}
        self.contexts = {}
        self.priorities = {}

        self.none_project = Project(self, "NONE")
        self.none_context = Context(self, "NONE")

        self.exit = False
        self.popup = None

        self.read_config()

    def system_settings():
        os.environ.setdefault('ESCDELAY', '25')

    def curses_settings(self):
        curses.curs_set(0)
        curses.noecho()
        curses.cbreak()
        curses.use_default_colors()
        for i in range(0, curses.COLORS):
            curses.init_pair(i+1, i, -1)

    def cursor_cell(self):
        return self.layout.cursor.cursor

    def main(self):
        while not self.exit:
            self.layout.erase()
            self.layout.draw()
            self.layout.refresh()
            cell = self.cursor_cell()
            if self.layout.popup:
                self.layout.popup.erase()
                self.layout.popup.draw()
                self.layout.popup.refresh()
                c = self.layout.popup.window.getch()
                self.layout.popup.handle_input(c)
            else:
                c = cell.window.getch()
                cell.cursor.handle_input(cell, c)

    def screen_settings(self):
        self.screen.keypad(1)

    def configure_todos(self, config):
        node = config_get(config, "files", required = True)
        for name in node:
            self.todos[name] = TodoTxt(self, config_get(node, name, required = True))

    def configure_views(self, config):
        node = config_get(config, "views", required = True)
        for name in node:
            view = config_get(node,  name,  required = True)
            kind = config_get(view, "type", required = True)
            if kind == "TodoView": self.views[name] = TodoView(self, name, config = view)
            else: raise(Exception("Unknown View Type: {}".format(kind)))

    def configure_layout(self, config):
        self.layout = Layout(self, config["layout"])

    def configure_printers(self, config):
        node = config_get(config, "printers", default = [])
        for name in node:
            self.printers[name] = config_get(node, name, context = self, required = True, transform = TaskPrinter)

    def configure_sorters(self, config):
        node = config_get(config, "sorters",  default = [])
        for name in node:
            self.sorters[name] = config_get(node, name, context = self, required = True, transform = TaskSorter)

    def configure_filters(self, config):
        node = config_get(config, "filters",  default = [])
        for name in node:
            self.filters[name] = config_get(node, name, context = self, required = True, transform = TaskFilter)

    def resize(self):
        self.layout.resize()

    def read_config(self):
        self.todos    = {}
        self.views    = {}
        self.printers = {}
        self.filters  = {}
        self.sorters  = {}
        with open(CONFIG_FILE, "r") as f:
            config = load(f, Loader=Loader)
        self.configure_todos(config)
        self.configure_printers(config)
        self.configure_sorters(config)
        self.configure_filters(config)
        self.configure_views(config)
        self.configure_layout(config)

    def size(self):
        (y, x) = self.screen.getmaxyx()
        return (x, y)

    def get_context(self, name: str, create: bool = True):
        if name in self.contexts: return self.contexts[name]
        elif create: return Context(self, name)
        else: raise(Exception("Unknown context: {}".format(name)))

    def get_project(self, name: str, create: bool = True):
        if name in self.projects: return self.projects[name]
        elif create: return Project(self, name)
        else: raise(Exception("Unknown project: {}".format(name)))

    def get_priority(self, name: str, create: bool = True):
        if name in self.priorities: return self.priorities[name]
        elif create: return Priority(self, name)
        else: raise(Exception("Unknown priority: {}".format(name)))

    def get_context_option(self, option):
        context, setting = option
        return (self.get_context(context), setting)

    def get_project_option(self, option):
        project, setting = option
        return (self.get_project(project), setting)

# }}}
# {{{ Constants

RE_DONE         = r'^x .*'
RE_YYYY         = r'[0-9]{4}'
RE_MM           = r'[0-9]{2}'
RE_DD           = r'[0-9]{2}'
RE_DATE         = r'{}-{}-{}'.format(RE_YYYY, RE_MM, RE_DD)
RE_METADATE     = r'\S+:{}'.format(RE_DATE)
RE_PROJECT      = r'\+\S+'
RE_CONTEXT      = r'@\S+'
RE_PRIORITY     = r'\([A-Z]\)'

DATE_DUE = "due:"
DATE_THR = "t:"

TODO_DIR = "/home/czar/cloud/todo"
TODO_FILE = TODO_DIR + "/todo.txt"
DONE_FILE = TODO_DIR + "/done.txt"

CONFIG_DIR = "/home/czar/.config/todotui"
CONFIG_FILE = CONFIG_DIR + "/config.yaml"

SEPERATOR_PACKED        = TaskSeperator(0, 0, "Packed",       "")
SEPERATOR_SPACED        = TaskSeperator(0, 1, "Spaced",       "")
SEPERATOR_PACKED_BORDER = TaskSeperator(0, 1, "PackedBorder", Line.UNICODE_V)
SEPERATOR_SPACED_BORDER = TaskSeperator(1, 1, "SpacedBorder", Line.UNICODE_V)
SEPERATORS = [SEPERATOR_PACKED, SEPERATOR_SPACED, SEPERATOR_PACKED_BORDER, SEPERATOR_SPACED_BORDER]
DEFAULT_SEPERATOR = SEPERATOR_SPACED_BORDER

FIELD_LINE      = TaskField(2,  '##',        'Line')
FIELD_DONE      = TaskField(1,  'x',         'Done')
FIELD_TEXT      = TaskField(0,  'Todo',      'Text')
FIELD_PROJECT   = TaskField(10, 'project',   'Project')
FIELD_CONTEXT   = TaskField(10, 'context',   'Context')
FIELD_PRIORITY  = TaskField(1,  '!',         'Priority')
FIELD_DATE_ADD  = TaskField(10, 'date',      'DateAdd')
FIELD_DATE_THR  = TaskField(10, 'threshold', 'DateThr')
FIELD_DATE_DUE  = TaskField(10, 'due',       'DateDue')
FIELD_DATE_DONE = TaskField(10, 'done',      'DateDone')
FIELD_METRIC    = TaskField(10, 'sort',      'Metric')
FIELDS = [FIELD_LINE, FIELD_DONE, FIELD_TEXT, FIELD_PROJECT, FIELD_CONTEXT, FIELD_PRIORITY, FIELD_METRIC, FIELD_DATE_ADD, FIELD_DATE_THR, FIELD_DATE_DUE, FIELD_DATE_DONE]

TODO_PRINTER    = TaskPrinter()
DEFAULT_FILTER  = TaskFilter(config = {"archived":False, "empty":False})
DEFAULT_SORTER  = TaskSorter()
DEFAULT_PRINTER = TaskPrinter(config = {"show_line":False, "hide_dates":True, "hide_contexts":True, "hide_projects":True})
DEFAULT_COLUMNS = [FIELD_LINE, FIELD_DATE_DUE, FIELD_TEXT]

TASK_PARSER = TaskParser()

# }}}
# {{{ Main

Tui.system_settings()

def main(screen):
    tui = Tui(screen, CONFIG_FILE)
    DEFAULT_SORTER.tui  = tui
    DEFAULT_FILTER.tui  = tui
    DEFAULT_PRINTER.tui = tui
    tui.main()
curses.wrapper(main)

# }}}