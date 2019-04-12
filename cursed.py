import copy
import re
import curses
import os
from typing import Dict, Tuple, List

COLOR_TASK_DEFAULT  = 0
COLOR_TASK_CURSOR   = 2
COLOR_TASK_DONE     = 9
COLOR_CELL_ACTIVE   = 13
COLOR_CELL_INACTIVE = 0

# {{{ Util

class Util:

    def log(s):
        with open(os.environ['HOME'] + '/todotui.log', "a") as f:
            f.write(s)

    def order(p):
        return (min(p[0], p[1]), max(p[0], p[1]))

    def clamp(val, lo, hi):
        return max(lo, min(hi, val))

    def scroll(scroll: int, cursor: int, offset: int, limit: int, items):
        bounds = limit-offset
        if cursor-scroll > bounds: scroll = cursor-bounds
        if cursor-scroll < offset: scroll = cursor-offset
        if cursor+offset >= items: scroll = items-limit
        return scroll if scroll >= 0 else 0

    def assign(a: object, b: object):
        a.__dict__.update(copy.deepcopy(b).__dict__)

    def substitute_span(string: str, span: str, sub: str):
        lo, hi = span
        return '{}{}{}'.format(string[:lo], sub, string[hi:])

    def substitute(string: str, subs: Dict[str, str]):
        keys = ''.join([k for k, v in subs.items()])
        regex = r'(?<!%)%[{}]'.format(keys)
        found = re.search(regex, string)
        while found:
            string = Util.substitute_span(string, found.span(), subs[found.group(0)[1:]])
            found = re.search(regex, string)
        re.sub('%%', '%', string)
        return string

    def overlap(a, b):
        (a_min, a_max) = a
        (b_min, b_max) = b
        if   a_min <= b_min: minimum = a
        elif b_min <= a_min: minimum = b
        if   a_max >= b_max: maximum = a
        elif b_max >= a_max: maximum = b
        if minimum is maximum: return (True, b if minimum == a else a)
        (p_min, p_max) = minimum
        (q_min, q_max) = maximum
        if p_max < q_min: return (False, None)
        else:             return (True, (q_min, p_max))

# }}}
# {{{ Config

class Config:

    def __init__(self, node = {}):
        self.node = node

    def __iter__(self):
        return self.node.iter()

    def __repr__(self):
        return str(node)

    def get(self, key, default = None, transform = None, config = False, required = False):
        if key not in self.node:
            if required: raise(Exception("Missing config key {}".format(key)))
            return default
        node = Config(self.node[key]) if config else self.node[key]
        return transform(node) if transform else item

def config_get(config, key, default = None, transform = None, context = None, required = False):
    if key not in config:
        if required: raise(Exception("Config missing required key: {} -> {}".format(key, config)))
        return default
    if transform:
        if context: return transform(config[key], context = context)
        else:       return transform(config[key])
    else:
        return config[key]

def configure(config, item, preset, ckey, dkey, default = None, transform = None, context = None):
    if not preset or ckey in config:
        item.__dict__[dkey] = config_get(config, ckey, default = default, transform = transform, context = context)
    elif dkey not in item.__dict__:
        item.__dict__[dkey] = default

def config_assign(config, item, ckey, context):
    nkey = config_get(config, ckey, default = None)
    if nkey: Util.assign(item, context[nkey])
    return nkey is not None

# }}}
# {{{ Key

class Key:

    ESCAPE     = 27
    SPACE      = ord(' ')
    SSPACE     = 0
    BACKSPACE  = curses.KEY_BACKSPACE
    TAB        = ord('\t')
    EXIT       = curses.KEY_EXIT
    STAB       = curses.KEY_BTAB
    ENTER      = ord('\n')
    NUM_ENTER  = curses.KEY_ENTER
    UP         = curses.KEY_UP
    DOWN       = curses.KEY_DOWN
    LEFT       = curses.KEY_LEFT
    RIGHT      = curses.KEY_RIGHT
    SLEFT      = curses.KEY_SLEFT
    SRIGHT     = curses.KEY_SRIGHT

# }}}
# {{{ Point

class Point:

    UNICODE_L = '•'
    UNICODE_S = '·'

    def __init__(self: 'Point', x: int = 0, y: int = 0):
        self.x = x
        self.y = y

    def __repr__(self: 'Point'):
        return '({}, {})'.format(self.x, self.y)

    def __hash__(self: 'Point'):
        return hash((self.x, self.y))

    def __iter__(self: 'Point'):
        yield self.x
        yield self.y

    def __getitem__(self: 'Point', index: int):
        if   index == 0: return self.x
        elif index == 1: return self.y
        else: raise("Index out of bounds {}".format(index))

    def __setitem__(self: 'Point', index: int, value: int):
        if   index == 0: self.x = value
        elif index == 1: self.y = value
        else: raise("Index out of bounds {}".format(index))

    def __eq__(a: 'Point', b: 'Point'):
        return a.x == b.x and a.y == b.y

    def __add__(a: 'Point', b: 'Point'):
        return Point(a.x + b.x, a.y + b.y)

    def __sub__(a: 'Point', b: 'Point'):
        return Point(a.x - b.x, a.y - b.y)

# }}}
# {{{ Line

class Line:

    VERTICAL    = 1
    HORIZONTAL  = 2
    ANGLED      = 3

    ASCII_H    = "-"
    ASCII_V    = "|"
    ASCII_X    = "+"

    UNICODE_H  = "─"
    UNICODE_V  = "│"
    UNICODE_X  = "┼"
    UNICODE_HU = "┴"
    UNICODE_HD = "┬"
    UNICODE_VR = "├"
    UNICODE_VL = "┤"
    UNICODE_TL = "┌"
    UNICODE_BR = "┘"
    UNICODE_TR = "┐"
    UNICODE_BL = "└"

    UNICODE_BLOCK     = "█"
    UNICODE_BLOCK_U12 = "▀"
    UNICODE_BLOCK_U18 = "▔"
    UNICODE_BLOCK_D18 = "▁"
    UNICODE_BLOCK_D14 = "▂"
    UNICODE_BLOCK_D38 = "▃"
    UNICODE_BLOCK_D12 = "▄"
    UNICODE_BLOCK_D58 = "▅"
    UNICODE_BLOCK_D34 = "▆"
    UNICODE_BLOCK_D78 = "▇"
    UNICODE_BLOCK_L78 = "▉"
    UNICODE_BLOCK_L34 = "▊"
    UNICODE_BLOCK_L58 = "▋"
    UNICODE_BLOCK_L12 = "▌"
    UNICODE_BLOCK_L38 = "▍"
    UNICODE_BLOCK_L14 = "▎"
    UNICODE_BLOCK_L18 = "▏"
    UNICODE_BLOCK_R12 = "▐"
    UNICODE_BLOCK_R18 = "▕"

    UNICODE_SHADE_LIGHT  = "░"
    UNICODE_SHADE_MEDIUM = "▒"
    UNICODE_SHADE_DARK   = "▓"


    UNICODE_QUAD_LL       = "▖"
    UNICODE_QUAD_LR       = "▗"
    UNICODE_QUAD_UL       = "▘"
    UNICODE_QUAD_UR       = "▝"
    UNICODE_QUAD_UL_LR    = "▚"
    UNICODE_QUAD_UR_LL    = "▞"
    UNICODE_QUAD_UL_LL_LR = "▙"
    UNICODE_QUAD_UL_UR_LL = "▛"
    UNICODE_QUAD_UL_UR_LR = "▜"
    UNICODE_QUAD_UR_LL_LR = "▟"

    def __init__(self: 'Line', p: Point, q: Point):
        self.p = p
        self.q = q

    def __repr__(self: 'Line'):
        return '({}, {})'.format(self.p, self.q)

    def __hash__(self: 'Line'):
        return hash((self.p, self.q))

    def __iter__(self: 'Line'):
        yield self.p
        yield self.q

    def __getitem__(self: 'Line', index: int):
        if   index == 0: return self.p
        elif index == 1: return self.q
        else: raise("Index out of bounds {}".format(index))

    def __setitem__(self: 'Line', index: int, value: Point):
        if   index == 0: self.p = value
        elif index == 1: self.q = value
        else: raise("Index out of bounds {}".format(index))

    def __eq__(a: 'Line', b: 'Line'):
        return a.p == b.p and a.q == b.q

    def vertical(self: 'Line'):
        return self.p.x == self.q.x

    def horizontal(self: 'Line'):
        return self.p.y == self.q.y

    def parallel(self: 'Line', line: 'Line'):
        return  Line.orientation(self) == Line.orientation(line)

    def orientation(self: 'Line'):
        if   self.vertical():   return Line.VERTICAL
        elif self.horizontal(): return Line.HORIZONTAL
        else:                   return Line.ANGLED

    def project(self: 'Line', axis: int):
        return Util.order((self.p[axis], self.q[axis]))

    def collision(a: 'Line', b: 'Line'):
        (overlap_x, segment_x) = Util.overlap(a.project(0), b.project(0))
        (overlap_y, segment_y) = Util.overlap(a.project(1), b.project(1))
        if overlap_x and overlap_y: return (True, (segment_x, segment_y))
        else:                       return (False, None)

    def collisions(lines: List['Line']):
        results = {}
        for a in lines:
            for b in lines:
                # NOTE: Only checks in non-parallel lines
                if a is b or a.parallel(b) or (b, a) in results: continue
                (collide, segments) = a.collision(b)
                if collide: results[(a, b)] = segments
        return results

    def resolve_collision(collision: Tuple[Tuple['Line', 'Line'], Tuple[Tuple[int, int], Tuple[int, int]]]):
        (a, b), (sx, sy) = collision

        p = Point(sx[0], sy[0]) # sx[0] == sx[1] and sy[0] == sy[1]
        h = a if a.horizontal() else b
        v = a if a.vertical()   else b

        if   p == h.p and p == v.p: r = Line.UNICODE_TL
        elif p == h.p and p == v.q: r = Line.UNICODE_BL
        elif p == h.q and p == v.p: r = Line.UNICODE_TR
        elif p == h.q and p == v.q: r = Line.UNICODE_BR
        elif p == h.p:              r = Line.UNICODE_VR
        elif p == h.q:              r = Line.UNICODE_VL
        elif p == v.p:              r = Line.UNICODE_HD
        elif p == v.q:              r = Line.UNICODE_HU
        else:                       r = Line.UNICODE_X
        return (p, r)

    def resolve_collisions(collisions: Dict[Tuple['Line', 'Line'], Tuple[Tuple[int, int], Tuple[int, int]]]):
        return [Line.resolve_collision(c) for c in collisions.items()]

    def column(p: Point, length: int) -> 'Line':
        return Line(p, Point(p.x, p.y + length))

    def row(p: Point, length: int) -> 'Line':
        return Line(p, Point(p.x + length, p.y))

# }}}
# {{{ Rect

class Rect:

    def __init__(self: 'Rect', p: Point, q: Point):
        self.p = Point(min(p.x, q.x), min(p.y, q.y))
        self.q = Point(max(p.x, q.x), max(p.y, q.y))

    def __repr__(self: 'Rect'):
        return "[{} | {}]".format(self.p, self.q)

    def __hash__(self: 'Rect'):
        return hash((self.p, self.q))

    def __iter__(self: 'Rect'):
        yield Point(self.p.x, self.p.y)
        yield Point(self.q.x, self.p.y)
        yield Point(self.q.x, self.q.y)
        yield Point(self.p.x, self.q.y)

    def __eq__(a: 'Rect', b: 'Rect'):
        return a.p == b.p and a.q == b.q

    def __add__(a: 'Rect', p: Point):
        return Rect(a.p + p, a.q + p)

    def width(self: 'Rect'):
        return self.q.x - self.p.x

    def height(self: 'Rect'):
        return self.q.y - self.p.y

    def border(self: 'Rect'):
        a, b, c, d = self
        return [Line(a, b), Line(b, c), Line(d, c), Line(a, d)]

    def contains(self: 'Rect', p: 'Point'):
        return self.p.x <= p.x and self.p.y <= p.y and self.q.x >= p.x and self.q.y >= q.y

# }}}
# {{{ Window

class Window(Rect):

    def __init__(self, x, y, w, h):
        super().__init__(Point(x, y), Point(x+w, y+h))
        self.window = curses.newwin(h, w, y, x)
        self.window.keypad(1)

    def __repr__(self):
        return "Window(({}, {}), ({}, {}))".format(self.x, self.y, self.w, self.h)

    def refresh(self):
        self.window.refresh()

    def put(self, x, y, string, color = None):
        if color: self.window.addstr(y, x, string, color)
        else:     self.window.addstr(y, x, string)

    def erase(self):
        self.window.erase()

    def clear(self):
        self.window.clear()

    def move(self, x: int, y: int):
        self.p = Point(x, y)
        self.window.mvwin(y, x)

    def resize(self, w, h):
        self.q = Point(self.p.x + w, self.p.y + h)
        self.window.resize(h, w)

    def draw_line_h(self, line, color = None):
        (px, py), (qx, qy) = line
        while px < qx:
            self.put(px, py, Line.UNICODE_H, color = color)
            px += 1

    def draw_line_v(self, line, color = None):
        (px, py), (qx, qy) = line
        while py < qy:
            self.put(px, py, Line.UNICODE_V, color = color)
            py += 1

    def draw_line(self, line, color = None):
        orientation = line.orientation()
        if   orientation == Line.HORIZONTAL: self.draw_line_h(line, color = color)
        elif orientation == Line.VERTICAL:   self.draw_line_v(line, color = color)
        else: raise(Exception("Invalid line orientation: {}".format(orientation)))

    def draw_lines(self, lines, color = None):
        for line in lines: self.draw_line(line, color)
        r = Line.resolve_collisions(Line.collisions(lines))
        for (x, y), s in r:
            try:
                if color: self.put(x, y, s, color)
                else:     self.put(x, y, s)
            except: pass

    def getch(self):
        return self.window.getch()

    def border(self):
        self.window.border()

# }}}
# {{{ LayoutNode

class LayoutNode():

    def __init__(self, parent, config):
        self.config   = config
        self.parent   = parent
        self.children = []

    def __iter__(self):
        return self.children.iter()

    def initialize(self):
        self.cursor   = self.child(0)
        for node in self.children: node.initialize()

    def child(self, index):
        return self.children[index]

    def count(self):
        return len(self.children)

    def tui(self):
        return self.parent.tui()

    def index(self):
        return self.parent.children.index(self)

    def width(self):
        return self.parent.width()

    def height(self):
        return self.parent.height()

    def size(self):
        return (self.width(), self.height())

    def clear(self):
        for node in self.children: node.clear()

    def erase(self):
        for node in self.children: node.erase()

    def refresh(self):
        for node in self.children: node.refresh()

    def draw(self):
        for node in self.children: node.draw()

    def resize(self):
        for node in self.children: node.resize()

    def cursor_next(self):
        index = (self.cursor.index() + 1) % self.count()
        self.cursor = self.child(index)

    def cursor_prev(self):
        index = (self.cursor.index() - 1) % self.count()
        self.cursor = self.child(index)

    def border_lines(self):
        (w, h) = (self.width() - 1, self.height() - 1)
        return [
            Line(Point(0, 0), Point(w, 0)), # t
            Line(Point(0, h), Point(w, h)), # b
            Line(Point(0, 0), Point(0, h)), # l
            Line(Point(w, 0), Point(w, h)), # r
        ]

    def offset(self, axis: int):
        offset = 0
        for node in self.parent.children:
            if self is node: break
            offset += node.size()[axis]
        return offset

    def tile(self, axis: int):
        n = self.parent.count()
        m = self.parent.size()[axis]
        x = int(m / n)
        r = m - x * n
        return x + r if self.index() == 0 else x

    def max_x(self):
        return self.width() - 1

    def max_y(self):
        return self.height() - 1

    def update(self):
        for node in self.children:
            node.update()

# }}}
# {{{ Layout

class Layout(LayoutNode):

    def __init__(self, tui, config):
        super().__init__(None, config)
        self.m_tui = tui
        self.popup = None

        node = config["columns"]
        if not node: raise(Exception("Layout must have at least one column"))
        for name in node:
            self.children.append(LayoutColumn(self, node[name]))

        self.initialize()

    def tui(self):
        return self.m_tui

    def column(self, index):
        return self.children[index][1]

    def width(self):
        return self.size()[0]

    def height(self):
        return self.size()[1]

    def size(self):
        return self.tui().size()

    def popup_set(self, popup):
        if self.popup: raise(Exception("Two popups"))
        self.popup = popup

    def popup_del(self):
        del self.popup.window
        del self.popup
        self.popup = None

# }}}
# {{{ LayoutColumn

class LayoutColumn(LayoutNode):

    def __init__(self, parent, config):
        super().__init__(parent, config)

        node = config["cells"]
        if not node: raise(Exception("Column must have at least one cell"))
        for name in node:
            self.children.append(LayoutCell(self, node[name]))

        self.cursor = self.child(0)

    def offset(self):
        return super().offset(0)

    def width(self):
        return super().tile(0)

# }}}
# {{{ LayoutCell

class LayoutCell(LayoutNode):

    def __init__(self, parent, config):
        super().__init__(parent, config)

        node = config["views"]
        if not node: raise(Exception("Cell must have at least one view"))
        for name in node:
            self.children.append(self.tui().views[name])

        self.lines = []
        self.states = {}

    def initialize(self):
        self.cursor = self.child(0)
        self.create_window()

    def cursor_next(self):
        index = (self.cursor.index(self) + 1) % len(self.children)
        self.cursor = self.child(index)

    def cursor_prev(self):
        index = (self.cursor.index(self) - 1) % len(self.children)
        self.cursor = self.child(index)

    def state(self, view):
        if view not in self.states:
            state = view.init_state()
            self.states[view] = state
            return state
        return self.states[view]

    def refresh(self):
        self.window.refresh()

    def erase(self):
        self.window.erase()

    def clear(self):
        self.window.clear()

    def add_lines(self, lines):
        self.lines.extend(lines)

    def create_window(self):
        (x, y) = self.origin()
        (w, h) = self.size()
        self.window = Window(x, y, w, h)

    def origin(self):
        return (self.parent.offset(), self.offset())

    def is_active(self):
        return self is self.tui().cursor_cell()

    def draw(self):
        self.lines.clear()
        self.add_lines(self.border_lines())
        if self.cursor: self.cursor.draw(self)
        color = COLOR_CELL_ACTIVE if self.is_active() else COLOR_CELL_INACTIVE
        self.window.draw_lines(self.lines, curses.color_pair(color))

    def resize(self):
        (x, y) = self.origin()
        (w, h) = self.size()
        self.window.resize(w, h)
        self.window.move(x, y)

    def height(self):
        return super().tile(1)

    def offset(self):
        return super().offset(1)

    def update(self):
        self.cursor.update(self, force = True)

# }}}
# {{{ View

class View:

    def __init__(self, tui, name):
        self.tui  = tui
        self.name = name

    def init_state(self):
        pass

    def state(self, cell):
        return cell.state(self)

    def index(self, cell):
        return cell.children.index(self)

# }}}
# {{{ Popup

class Popup:

    def __init__(self, parent, x, y, width, height):
        self.position = Point(x, y)
        self.parent = parent
        self.width  = width
        self.height = height

        self.window = Window(x, y, width, height)
        self.window.refresh()
        self.window.border()

        if self.parent.popup: raise(Exception("Parent already has an active popup"))
        self.parent.popup = self
        self.popup = None

    def tui(self):
        return self.parent.tui()

    def erase(self):
        self.window.erase()
        if self.popup: self.popup.erase()

    def refresh(self):
        self.window.refresh()
        if self.popup: self.popup.refresh()

    def clear(self):
        self.window.clear()

    def handle_input(self, char):
        if self.popup:
            self.popup.handle_input(char)
            return True
        else: return False

    def accept(self):
        pass

    def draw(self):
        self.window.border()
        if self.popup: self.popup.draw()

    def border(self):
        self.window.border()

    def cancel(self):
        self.parent.popup = None
        del self.window
        del self

    def center(self):
        return (int(self.width/2), int(self.height/2))

class TitledPopup(Popup):

    def __init__(self, parent, x, y, width, height, title):
        super().__init__(parent, x, y, width, height)
        self.title = title

    def draw_title(self):
        (cx, cy) = self.center()
        name = "{} {} {}".format(Point.UNICODE_S, self.title, Point.UNICODE_S)
        self.window.border()
        self.window.put(cx - int(len(name)/2),  0, name)

    def draw(self):
        super().draw()
        self.draw_title()

class ModalPopup(TitledPopup):

    WIDGET = 0
    ACCEPT = 1
    CANCEL = 2

    BUTTON_SPACING = 20

    def __init__(self, parent, x, y, width, height, title):
        super().__init__(parent, x, y, width, height, title)
        self.mode = ModalPopup.WIDGET

    def mode_next(self):
        self.mode = (self.mode + 1) % 3

    def mode_prev(self):
        self.mode = (self.mode - 1) % 3

    def handle_input_accept(self, char):
        if   char == Key.ENTER:  self.accept()
        elif char == Key.ESCAPE: self.cancel()
        elif char == Key.TAB:    self.mode_next()
        elif char == Key.STAB:   self.mode_prev()
        else: return False
        return True

    def handle_input_cancel(self, char):
        if   char == Key.ENTER:  self.cancel()
        elif char == Key.ESCAPE: self.cancel()
        elif char == Key.TAB:    self.mode_next()
        elif char == Key.STAB:   self.mode_prev()
        else: return False
        return True

    def handle_input_widget(self, char):
        if   char == Key.ENTER:  self.accept()
        elif char == Key.ESCAPE: self.cancel()
        elif char == Key.TAB:    self.mode_next()
        elif char == Key.STAB:   self.mode_prev()
        else: return False
        return True

    def handle_input(self, char):
        if super().handle_input(char): return True
        elif self.mode == ModalPopup.ACCEPT: return self.handle_input_accept(char)
        elif self.mode == ModalPopup.CANCEL: return self.handle_input_cancel(char)
        elif self.mode == ModalPopup.WIDGET: return self.handle_input_widget(char)
        else: return False
        return True

    def draw_accept(self):
        (cx, cy) = self.center()
        if self.mode == ModalPopup.ACCEPT: color = curses.color_pair(4)
        else:                              color = curses.color_pair(0)
        button = "{} {} {}".format(Point.UNICODE_S, "Accept", Point.UNICODE_S)
        x = cx - ModalPopup.BUTTON_SPACING
        self.window.put(x, self.height-1, button, color)

    def draw_cancel(self):
        (cx, cy) = self.center()
        if self.mode == ModalPopup.CANCEL: color = curses.color_pair(4)
        else:                              color = curses.color_pair(0)
        button = "{} {} {}".format(Point.UNICODE_S, "Cancel", Point.UNICODE_S)
        x = cx + ModalPopup.BUTTON_SPACING - len(button)
        self.window.put(x, self.height-1, button, color)

    def draw(self):
        super().draw()
        self.draw_accept()
        self.draw_cancel()

class CenteredPopup(ModalPopup):

    def __init__(self, parent, width, height, title):
        (x, y, w, h) = self.centered(parent, width, height)
        super().__init__(parent, x, y, w, h, title)

    def centered(self, parent, width, height):
        (w, h) = parent.size()
        (cx, cy) = (int(w/2), int(h/2))
        (x, y) = (cx-int(width/2), cy-int(height/2))
        return (x, y, width, height)

# }}}
