"""Companion packs on screen: layout.json + style.css as a tree of boxes, laid out and painted with QPainter.

Follows gba-duo-wide (docs-packs/companion-styling.md, companion-pages.md and the app's companion/ sources): the widget
tree with its bindings and UI state, the documented CSS subset with the app's built-in styles, flex / grid / stack
layout, and painting. Everything is measured in CSS px; the caller scales the painter. Not here: transitions (changes
show at once), blurred shadows, text along a transform.
"""
import math, os, re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen

BUILT_IN = '''
:root { width: 100%; height: 100%; color: #ffffff; font-size: 14px; }
column, list { display: flex; flex-direction: column; }
row { display: flex; flex-direction: row; align-items: flex-start; }
box { display: flex; flex-direction: column; }
image { width: 32px; height: 32px; object-fit: contain; image-rendering: pixelated; }
spacer { width: 8px; height: 8px; flex-shrink: 0; }
bar { display: stack; height: 12px; background-color: rgba(108, 74, 182, 0.3); accent-color: #6c4ab6; }
bar > fill { position: absolute; left: 0; top: 0; bottom: 0; }
bar > label { align-self: center; justify-self: center; font-size: 10px; white-space: nowrap; }
tabs { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
tab-bar { display: flex; flex-direction: row; flex-shrink: 0; }
tab { padding: 8px 12px; color: #888888; }
tab:active { color: #ffffff; }
tab-content { display: stack; place-items: stretch; flex: 1 1 auto; min-height: 0; }
empty { color: #888888; }
pages { display: stack; place-items: stretch; flex: 1 1 auto; min-height: 0; }
button { display: flex; flex-direction: row; align-items: center; justify-content: center; gap: 6px; padding: 8px 14px;
         border-radius: 8px; background-color: rgba(255, 255, 255, 0.12); }
button:pressed { opacity: 0.7; }
'''
INHERITED = ('color', 'font-family', 'font-size', 'font-weight', 'font-style', 'letter-spacing', 'line-height', 'text-align', 'text-transform',
             'text-shadow', 'white-space', 'visibility', 'accent-color', 'image-rendering')
INITIAL = {'display': 'flex', 'flex-direction': 'row', 'flex-wrap': 'nowrap', 'justify-content': 'normal', 'align-items': 'normal', 'align-self': 'auto',
           'align-content': 'normal', 'justify-items': 'normal', 'justify-self': 'auto', 'flex-grow': '0', 'flex-shrink': '1', 'flex-basis': 'auto',
           'position': 'static', 'opacity': '1', 'color': '#ffffff', 'font-size': '14px', 'font-weight': '400', 'object-fit': 'contain',
           'background-repeat': 'repeat', 'background-position': '0% 0%', 'background-size': 'auto', 'box-sizing': 'border-box'}
SIDES = ('top', 'right', 'bottom', 'left')
CORNERS = ('top-left', 'top-right', 'bottom-right', 'bottom-left')
BORDER_STYLES = ('none', 'solid', 'dashed', 'dotted', 'hidden')
INF = float('inf')
GENERIC = {'sans-serif': 'Roboto', 'serif': 'Noto Serif', 'monospace': 'Hack'}  # Android's default is Roboto; where it is missing Qt takes its own sans
TOKEN = re.compile(r'\{([^{}]+)\}')
SEGMENT = re.compile(r'([a-zA-Z0-9_]+)|\[(\d+)\]')
KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


# ---- values ------------------------------------------------------------------------------------------------------------
def split(text, sep=' '):
    """Splits at sep outside brackets and quotes; for ' ' any run of white space separates."""
    out, depth, quote, cur = [], 0, '', []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote: quote = ''
        elif ch in '"\'': quote = ch; cur.append(ch)
        elif ch == '(': depth += 1; cur.append(ch)
        elif ch == ')': depth -= 1; cur.append(ch)
        elif depth == 0 and (ch == sep or (sep == ' ' and ch.isspace())): out.append(''.join(cur)); cur = []
        else: cur.append(ch)
    out.append(''.join(cur))
    return [part.strip() for part in out if part.strip() or sep != ' ']


NUMBER = re.compile(r'([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)([a-z%]*)\Z')
_lengths = {}


def length(text, fs=14.0, vw=538.0, vh=468.0):
    """A CSS length as (px, percent); None for auto, none or nonsense."""
    key = (text, fs, vw, vh)
    if key not in _lengths:
        if len(_lengths) > 4000: _lengths.clear()
        _lengths[key] = _sum(text.strip().lower(), fs, vw, vh)
    return _lengths[key]


def _plain(text, fs, vw, vh):
    m = NUMBER.match(text)
    if not m: return None
    n, unit = float(m[1]), m[2]
    if unit == '%': return (0.0, n)
    k = {'': 1, 'px': 1, 'em': fs, 'rem': 14, 'vw': vw / 100, 'vh': vh / 100, 'vmin': min(vw, vh) / 100, 'vmax': max(vw, vh) / 100}.get(unit)
    return None if k is None else (n * k, 0.0)


def _sum(text, fs, vw, vh):
    m = re.match(r'(calc|min|max|clamp)\((.*)\)\Z', text, re.S)
    if m:
        args = [_sum(a, fs, vw, vh) for a in split(m[2], ',')]
        if not args or any(a is None for a in args): return None
        if m[1] == 'calc': return args[0]
        if any(a[1] for a in args) and any(a[0] for a in args): return None  # % against px: not comparable before layout
        i = 1 if args[0][1] else 0
        v = [a[i] for a in args]
        best = min(v) if m[1] == 'min' else max(v) if m[1] == 'max' else max(v[0], min(v[1], v[2])) if len(v) == 3 else None
        return None if best is None else ((0.0, best) if i else (best, 0.0))
    if text.startswith('(') and text.endswith(')'): return _sum(text[1:-1].strip(), fs, vw, vh)
    terms = split(text)
    if len(terms) > 1:  # a + b - c (the signs stand alone, as CSS wants)
        total, sign = [0.0, 0.0], 1
        for term in terms:
            if term in '+-': sign = 1 if term == '+' else -1; continue
            v = _product(term, fs, vw, vh)
            if v is None: return None
            total[0] += sign * v[0]; total[1] += sign * v[1]
        return tuple(total)
    return _product(text, fs, vw, vh)


def _product(text, fs, vw, vh):
    for op in '*/':
        parts = split(text, op)
        if len(parts) == 2:
            a, b = (_sum(part, fs, vw, vh) if part[:1] in '(cm' else _plain(part, fs, vw, vh) for part in parts)
            if a is None or b is None: return None
            if op == '/': return (a[0] / b[0], a[1] / b[0]) if b[0] and not b[1] else None
            return (a[0] * b[0], a[1] * b[0]) if not NUMBER.match(parts[0]) or NUMBER.match(parts[0])[2] else (b[0] * a[0], b[1] * a[0])
    return _plain(text, fs, vw, vh)


def resolve(value, base):
    if value is None or (value[1] and base is None): return None
    return value[0] + (value[1] * base / 100 if value[1] else 0)


_colors = {}


def color(text, current=None):
    text = text.strip().lower()
    if text == 'currentcolor': return current or QColor('#ffffff')
    c = _colors.get(text)
    if c is None:
        c = _color(text)
        if len(_colors) < 2000: _colors[text] = c
    return c


def _color(t):
    if t == 'transparent': return QColor(0, 0, 0, 0)
    if t.startswith('#'):
        h = t[1:]
        if len(h) in (3, 4): h = ''.join(ch * 2 for ch in h)
        try: v = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
        except ValueError: return QColor(0, 0, 0, 0)
        return QColor(*v) if len(v) in (3, 4) else QColor(0, 0, 0, 0)
    m = re.match(r'(rgba?|hsla?)\((.*)\)\Z', t)
    if m:
        parts = [p for p in re.split(r'[\s,/]+', m[2].strip()) if p]
        try:
            num = lambda s, full: float(s[:-1]) * full / 100 if s.endswith('%') else float(s)
            a = max(0.0, min(1.0, num(parts[3], 1))) if len(parts) > 3 else 1.0
            if m[1].startswith('rgb'): return QColor(*(max(0, min(255, round(num(p, 255)))) for p in parts[:3]), round(a * 255))
            return QColor.fromHslF((float(parts[0].replace('deg', '')) % 360) / 360, num(parts[1], 1) if '%' not in parts[1] else float(parts[1][:-1]) / 100,
                                   float(parts[2].rstrip('%')) / 100, a)
        except (ValueError, IndexError): return QColor(0, 0, 0, 0)
    c = QColor(t)
    return c if c.isValid() else QColor(0, 0, 0, 0)


def is_color(token):
    t = token.lower()
    return t.startswith(('#', 'rgb', 'hsl', 'var(')) or t in ('transparent', 'currentcolor') or (t.isalpha() and QColor.isValidColorName(t))


# ---- CSS ---------------------------------------------------------------------------------------------------------------
def four(values):
    v = list(values)
    return (v * 4)[:4] if len(v) == 1 else [v[0], v[1], v[0], v[1]] if len(v) == 2 else [v[0], v[1], v[2], v[1]] if len(v) == 3 else v[:4]


_expanded = {}


def expand(name, value):
    """A declaration as longhands [(name, value)]."""
    key = (name, value)
    if key not in _expanded:
        if len(_expanded) > 6000: _expanded.clear()
        _expanded[key] = _expand(name, value)
    return _expanded[key]


def _border(value):
    width, style, col = '3px', 'none', 'currentcolor'
    for token in split(value):
        low = token.lower()
        if low in BORDER_STYLES: style = low
        elif low in ('thin', 'medium', 'thick'): width = {'thin': '1px', 'medium': '3px', 'thick': '5px'}[low]
        elif NUMBER.match(low) or low.startswith(('calc(', 'max(', 'min(', 'clamp(')): width = low
        else: col = token
    return width, style, col


def _expand(name, value):
    v = value.strip()
    if name in ('margin', 'padding'): return [(f'{name}-{side}', x) for side, x in zip(SIDES, four(split(v)))]
    if name == 'inset': return list(zip(SIDES, four(split(v))))
    if name in ('gap', 'grid-gap'):
        parts = split(v)
        return [('row-gap', parts[0]), ('column-gap', parts[-1])] if parts else []
    if name == 'border':
        w, s, c = _border(v)
        return [(f'border-{side}-{what}', x) for side in SIDES for what, x in (('width', w), ('style', s), ('color', c))]
    if name in ('border-top', 'border-right', 'border-bottom', 'border-left'):
        w, s, c = _border(v)
        return [(f'{name}-width', w), (f'{name}-style', s), (f'{name}-color', c)]
    if name in ('border-width', 'border-style', 'border-color'): return [(f'border-{side}-{name[7:]}', x) for side, x in zip(SIDES, four(split(v)))]
    if name == 'border-radius': return [(f'border-{corner}-radius', x) for corner, x in zip(CORNERS, four(split(v.split('/')[0])))]
    if name == 'background':
        out = {'background-color': 'transparent', 'background-image': 'none', 'background-repeat': 'repeat', 'background-position': '0% 0%', 'background-size': 'auto'}
        position, size = split(v, '/')[0], (split(v, '/') + [''])[1]
        where = []
        for token in split(position):
            low = token.lower()
            if low.startswith(('url(', 'linear-gradient(')) or low == 'none': out['background-image'] = token
            elif low in ('repeat', 'no-repeat', 'repeat-x', 'repeat-y'): out['background-repeat'] = low
            elif is_color(token): out['background-color'] = token
            else: where.append(token)
        if where: out['background-position'] = ' '.join(where)
        if size: out['background-size'] = size
        return list(out.items())
    if name == 'flex':
        low = v.lower()
        if low == 'none': g, s, b = '0', '0', 'auto'
        elif low == 'auto': g, s, b = '1', '1', 'auto'
        else:
            parts, g, s, b = split(low), '1', '1', '0px'
            numbers = [p for p in parts if NUMBER.match(p) and not NUMBER.match(p)[2]]
            rest = [p for p in parts if p not in numbers]
            if numbers: g = numbers[0]
            if len(numbers) > 1: s = numbers[1]
            if rest: b = rest[0]
            elif len(numbers) > 2: b = numbers[2] + 'px'
        return [('flex-grow', g), ('flex-shrink', s), ('flex-basis', b)]
    if name == 'flex-flow': return [('flex-wrap' if 'wrap' in p else 'flex-direction', p) for p in split(v.lower())]
    if name in ('place-items', 'place-self'):
        parts, kind = split(v.lower()), name[6:]
        return [(f'align-{kind}', parts[0]), (f'justify-{kind}', parts[-1])] if parts else []
    if name == 'text-decoration': return [('text-decoration-line', ' '.join(p for p in split(v.lower()) if p in ('underline', 'line-through', 'none')) or 'none')]
    if name == 'font-weight': return [(name, {'normal': '400', 'bold': '700', 'bolder': '700', 'lighter': '300'}.get(v.lower(), v))]
    if name in ('transition', 'animation') or name.startswith(('transition-', 'animation-')): return []
    return [(name, v)]


def declarations(body):
    out = []
    for part in split(body, ';'):
        name, colon, value = part.partition(':')
        name, value = name.strip(), re.sub(r'\s*!important\s*$', '', value.strip())
        if colon and name and value: out.append((name if name.startswith('--') else name.lower(), value))
    return out


class Selector:
    """type, .class, #id, compounds, descendant and child combinators, the documented pseudo-classes."""
    PART = re.compile(r'([#.:]?)(-?[A-Za-z_*][\w-]*)(?:\(([^)]*)\))?')

    def __init__(self, text):
        self.parts, self.ok = [], True  # [(combinator before it, type, id, classes, pseudos)]
        comb = ' '
        text = re.sub(r'\(([^)]*)\)', lambda m: '(' + m[1].replace(' ', '') + ')', text)
        for token in re.sub(r'\s*>\s*', ' > ', text.strip()).split():
            if token == '>': comb = '>'; continue
            if any(c in re.sub(r'\([^)]*\)', '', token) for c in '+~[') or '::' in token: self.ok = False; return
            kind, ident, classes, pseudos, pos = None, None, set(), [], 0
            for m in self.PART.finditer(token):
                if m.start() != pos: self.ok = False; return
                pos = m.end()
                if m[1] == '': kind = None if m[2] == '*' else m[2].lower()
                elif m[1] == '#': ident = m[2]
                elif m[1] == '.': classes.add(m[2])
                else: pseudos.append((m[2].lower(), nth(m[3]) if m[3] is not None else None))
            if pos != len(token) or any(name not in ('root', 'empty', 'first-child', 'last-child', 'nth-child', 'nth-last-child', 'pressed', 'active', 'disabled')
                                        or (arg is None) != ('nth' not in name) for name, arg in pseudos): self.ok = False; return
            self.parts.append((comb, kind, ident, frozenset(classes), pseudos))
            comb = ' '
        self.ok = bool(self.parts)
        if self.ok:
            self.spec = (sum(1 for p in self.parts if p[2]), sum(len(p[3]) + len(p[4]) for p in self.parts), sum(1 for p in self.parts if p[1]))
            last = self.parts[-1]
            self.bucket = '#' + last[2] if last[2] else '.' + min(last[3]) if last[3] else last[1] or '*'

    def matches(self, node, i=None):
        i = len(self.parts) - 1 if i is None else i
        comb, kind, ident, classes, pseudos = self.parts[i]
        if (kind and kind != node.type) or (ident and ident != node.id) or not classes <= node.classes: return False
        for name, arg in pseudos:
            if not node.pseudo(name, arg): return False
        if i == 0: return True
        parent = node.parent
        if comb == '>': return parent is not None and self.matches(parent, i - 1)
        while parent is not None:
            if self.matches(parent, i - 1): return True
            parent = parent.parent
        return False


def nth(text):
    """'odd', 'even', '3', '2n+1', '-n+3' as (a, b)."""
    t = text.replace(' ', '').lower()
    if t == 'odd': return (2, 1)
    if t == 'even': return (2, 0)
    m = re.match(r'([-+]?\d*)n([-+]\d+)?\Z', t)
    if m: return (int(m[1] + '1') if m[1] in ('', '-', '+') else int(m[1]), int(m[2] or 0))
    try: return (0, int(t))
    except ValueError: return (0, 0)


class Sheet:
    def __init__(self):
        self.rules, self.fonts, self.buckets, self.warnings = [], [], {}, []

    def add(self, css, base, root, vw, vh, origin):
        """Parses a stylesheet. base: its folder (for url()), root: the folder nothing may leave."""
        def url(m):
            rel = m[1].strip().strip('"\'')
            path = os.path.normpath(os.path.join(base, rel))
            inside = not re.match(r'[a-z]+:|/', rel) and (path + os.sep).startswith(os.path.normpath(root) + os.sep)
            return 'url("%s")' % (path if inside else '')
        def block(text):
            pos = 0
            while True:
                brace = text.find('{', pos)
                if brace < 0: break
                head, depth, i = text[pos:brace].strip(), 1, brace + 1
                while i < len(text) and depth: depth += (text[i] == '{') - (text[i] == '}'); i += 1
                body, pos = text[brace + 1:i - 1], i
                if head.startswith('@font-face'): self.fonts.append(dict(declarations(body)))
                elif head.startswith('@media'):
                    ok = media(head[6:], vw, vh)
                    if ok: block(body)
                    elif ok is None: self.warnings.append(f'skipped: {head}')
                elif head.startswith('@'): self.warnings.append(f'skipped: {head}')
                else:
                    decls = declarations(body)
                    for text_ in split(head, ','):
                        sel = Selector(text_)
                        if not sel.ok: self.warnings.append(f'skipped selector: {text_}'); continue
                        rule = (origin, sel.spec, len(self.rules), sel, decls)
                        self.rules.append(rule)
                        self.buckets.setdefault(sel.bucket, []).append(rule)
        block(re.sub(r'url\(([^)]*)\)', url, re.sub(r'/\*.*?\*/', '', css, flags=re.S)))

    def matching(self, node):
        found = []
        for key in ['*', node.type, *('.' + c for c in node.classes)] + (['#' + node.id] if node.id else []):
            for rule in self.buckets.get(key, ()):
                if rule[3].matches(node): found.append(rule)
        found.sort(key=lambda r: r[:3])
        return found


def media(query, vw, vh):
    """True / False, or None for a condition this cannot judge (the block is skipped)."""
    def one(text):
        result = True
        for part in re.split(r'\s+and\s+', text.strip().lower()):
            part, negate = part.strip(), False
            if part.startswith('not '): part, negate = part[4:].strip(), True
            if part.startswith('only '): part = part[5:].strip()
            if part in ('all', 'screen', ''): ok = True
            else:
                m = re.match(r'\(\s*(min-|max-)?(width|height)\s*:\s*([^)]+)\)\Z', part)
                o = re.match(r'\(\s*orientation\s*:\s*(portrait|landscape)\s*\)\Z', part)
                r = re.match(r'\(\s*(width|height)\s*(<=|>=|<|>)\s*([^)]+)\)\Z', part)
                if m:
                    v, have = length(m[3]), vw if m[2] == 'width' else vh
                    if v is None or v[1]: return None
                    ok = have >= v[0] if m[1] == 'min-' else have <= v[0] if m[1] == 'max-' else have == v[0]
                elif o: ok = (vh > vw) == (o[1] == 'portrait')
                elif r:
                    v, have = length(r[3]), vw if r[1] == 'width' else vh
                    if v is None or v[1]: return None
                    ok = {'<=': have <= v[0], '>=': have >= v[0], '<': have < v[0], '>': have > v[0]}[r[2]]
                else: return None
            result = result and (ok != negate)
        return result
    results = [one(q) for q in split(query, ',')]
    return None if any(r is None for r in results) else any(results)


# ---- bindings ----------------------------------------------------------------------------------------------------------
class Scope:
    """A list item's values: its own fields first, then the whole snapshot."""
    __slots__ = ('item', 'index', 'root')

    def __init__(self, item, index, root): self.item, self.index, self.root = item, index, root


def lookup(path, ctx):
    if isinstance(ctx, Scope):
        if path == '@index': return ctx.index
        found = _lookup(path, ctx.item)
        return found if found is not None else _lookup(path, ctx.root)
    return _lookup(path, ctx)


def _lookup(path, cur):
    for m in SEGMENT.finditer(path):
        if m[1]: cur = cur.get(m[1]) if isinstance(cur, dict) else None
        else: cur = cur[int(m[2])] if isinstance(cur, list) and int(m[2]) < len(cur) else None
        if cur is None: return None
    return cur


def show(value):
    if value is None: return ''
    if value is True: return 'true'
    if value is False: return 'false'
    if isinstance(value, float): return str(int(value)) if value == int(value) else str(value)
    return str(value)


def fill(template, ctx): return TOKEN.sub(lambda m: show(lookup(m[1], ctx)), template) if '{' in template else template


def truthy(value): return bool(value)


def number(value):
    if isinstance(value, bool): return 0.0
    if isinstance(value, (int, float)): return float(value)
    try: return float(value) if isinstance(value, str) else 0.0
    except ValueError: return 0.0


def actions(value, script=False):
    """onClick (or what a script returned) as [('set', {…}) | ('navigate', page, state) | ('back', state) | ('call', name, args)]."""
    if isinstance(value, list): return [a for v in value for a in actions(v, script)]
    if value == 'back': return [('back', 'page')]
    if not isinstance(value, dict): return []
    out, state = [], str(value.get('state', 'page'))
    if not KEY.match(state): return []
    if isinstance(value.get('set'), dict):
        values = {str(k): v for k, v in value['set'].items() if KEY.match(str(k))}
        if values: out.append(('set', values))
    go, back = value.get('navigate'), value.get('back')
    if isinstance(go, str) and not back: out.append(('navigate', go, state))
    elif go is None and back is True: out.append(('back', state))
    elif go is None and isinstance(back, str) and KEY.match(back): out.append(('back', back))
    call = value.get('call')
    if isinstance(call, str) and KEY.match(call) and not script:
        args = value.get('args')
        out.append(('call', call, [] if args is None else args if isinstance(args, list) else [args]))
    return out


# ---- the tree ----------------------------------------------------------------------------------------------------------
class Node:
    __slots__ = ('type', 'id', 'static', 'dynamic', 'classes', 'inline', 'defaults', 'bound', 'pressed', 'active', 'parent', 'children', 'sibling', 'kind',
                 'text', 'image', 'key', 'hidden', 'switched', 'click', 'ctx', 'binds', 'manages', 'style', 'vars', 'cache', 'sizes', 'rect', 'name')

    def __init__(self, kind, type_, id_=None, classes=(), inline=(), defaults=()):
        self.kind, self.type, self.id, self.static, self.dynamic = kind, type_, id_, frozenset(classes), frozenset()
        self.classes, self.inline, self.defaults, self.bound = self.static, list(inline), list(defaults), []
        self.pressed = self.active = self.hidden = self.switched = self.manages = False
        self.parent, self.children, self.sibling, self.text, self.image, self.key, self.click, self.ctx = None, [], True, None, None, None, None, None
        self.binds, self.style, self.vars, self.cache, self.sizes, self.rect, self.name = [], {}, {}, {}, {}, None, ''

    def pseudo(self, name, arg):
        if name == 'root': return self.parent is None
        if name == 'empty': return not self.children
        if name == 'pressed': return self.pressed
        if name == 'active': return self.active
        if name == 'disabled': return False
        mates = [c for c in self.parent.children if c.sibling] if self.parent else [self]
        if self not in mates: return False
        i = mates.index(self) + 1
        if name == 'first-child': return i == 1
        if name == 'last-child': return i == len(mates)
        if name == 'nth-last-child': i = len(mates) + 1 - i
        a, b = arg
        return i == b if a == 0 else (i - b) % a == 0 and (i - b) // a >= 0

    def get(self, name): return self.style.get(name) or INITIAL.get(name, '')


class Tree:
    """The companion screen: widgets from layout.json, their styles, the UI state, layout and painting."""

    def __init__(self, layout, styles, folder, image=lambda key: None, width=538.0, height=468.0):
        """layout: layout.json as a dict; styles: [(css text, its folder)]; folder: the pack; image(key) -> QImage or None."""
        self.folder, self.load_image, self.vw, self.vh = folder, image, float(width), float(height)
        self.sheet, self.font_ids, self.families, self.fonts, self.files = Sheet(), [], {}, {}, {}
        self.sheet.add(BUILT_IN, folder, folder, self.vw, self.vh, 0)
        for css, base in styles: self.sheet.add(css, base, folder, self.vw, self.vh, 1)
        for face in self.sheet.fonts:
            m = re.search(r'url\("([^"]*)"\)', face.get('src', ''))
            if not m or not m[1] or not os.path.isfile(m[1]): continue
            ident = QFontDatabase.addApplicationFont(m[1])
            names = QFontDatabase.applicationFontFamilies(ident) if ident >= 0 else []
            if ident >= 0: self.font_ids.append(ident)
            if names: self.families[face.get('font-family', '').strip().strip('"\'').lower()] = names[0]
        self.ui, self.history, self.initial, self.snapshot, self.dirty = {}, {}, {}, None, []
        self.on_call, self.on_ui, self.stale, self.clicks = (lambda name, args: None), (lambda ui: None), True, []
        self.root = None  # while it is None nothing is styled yet
        self.root = self.inflate(layout, None)
        self.mark(self.root)
        self.flush()

    def close(self):
        for ident in self.font_ids: QFontDatabase.removeApplicationFont(ident)
        self.font_ids, self.files, self.fonts = [], {}, {}

    # -- building (CompanionTree.kt) -------------------------------------------------------------------------------------
    def attach(self, node, parent):
        node.parent = parent
        if parent is not None: parent.children.append(node)
        return node

    def part(self, parent, type_, sibling=True):
        node = self.attach(Node(type_, type_, classes=(type_,)), parent)
        node.sibling = sibling
        return node

    def inflate(self, w, parent):
        kind = w.get('type')
        if kind not in ('column', 'row', 'box', 'list', 'tabs', 'pages', 'button', 'text', 'bar', 'image', 'spacer'): raise ValueError(f"Unknown widget type '{kind}'")
        legacy, px = [], lambda field, *props: legacy.extend((prop, f'{w[field]}px') for prop in props) if isinstance(w.get(field), (int, float)) else None
        android = lambda c: '#' + c[3:] + c[1:3] if isinstance(c, str) and len(c) == 9 else str(c)  # #AARRGGBB
        if kind == 'text':
            px('size', 'font-size')
            if 'color' in w: legacy.append(('color', android(w['color'])))
            if 'bold' in w: legacy.append(('font-weight', '700' if w['bold'] else '400'))
        elif kind == 'bar': px('height', 'height')
        elif kind in ('image', 'spacer'): px('size', 'width', 'height')
        elif kind == 'box':
            px('width', 'width'); px('height', 'height'); px('padding', 'padding'); px('cornerRadius', 'border-radius')
            if 'background' in w: legacy.append(('background-color', android(w['background'])))
            if 'borderColor' in w and w.get('borderWidth', 0) > 0: legacy.append(('border', f"{w['borderWidth']}px solid {android(w['borderColor'])}"))
        style = w.get('style')
        inline = legacy + ([(k if k.startswith('--') else k.lower(), str(v)) for k, v in style.items()] if isinstance(style, dict) else declarations(style) if isinstance(style, str) else [])
        old_box = kind == 'box' and isinstance(w.get('child'), dict)  # the original frame around one child
        node = self.attach(Node('widget', kind, w.get('id'), str(w.get('class', '')).split(), inline,
                                [('display', 'stack'), ('place-items', 'stretch'), ('align-self', 'flex-start')] if old_box else ()), parent)
        node.name = str(w.get('id') or w.get('class') or kind)
        strip = lambda path: str(path)[1:] if str(path).startswith('$') else str(path)
        if 'visibleIf' in w:
            path = strip(w['visibleIf'])
            node.binds.append(lambda ctx: self.hide(node, not truthy(lookup(path, ctx))))
        if isinstance(w.get('classIf'), dict):
            conds = {name: strip(path) for name, path in w['classIf'].items()}
            def classes(ctx):
                on = frozenset(name for name, path in conds.items() if truthy(lookup(path, ctx)))
                if on != node.dynamic:
                    node.dynamic, node.classes = on, node.static | on
                    self.mark(node)
            node.binds.append(classes)
        if isinstance(w.get('bindStyle'), dict):
            bound = {k if k.startswith('--') else k.lower(): str(v) for k, v in w['bindStyle'].items()}
            node.binds.append(lambda ctx: self.bind(node, [(k, fill(v, ctx)) for k, v in bound.items()]))
        todo = actions(w.get('onClick'))
        if todo:
            node.click = todo
            node.binds.append(lambda ctx: setattr(node, 'ctx', ctx))
        children = [w['child']] if old_box else [c for c in w.get('children') or [] if isinstance(c, dict)]
        if kind in ('column', 'row', 'box'):
            for child in children: self.inflate(child, node)
        elif kind == 'button':
            if 'text' in w: self.inflate({'type': 'text', 'text': w['text'], 'class': 'label'}, node)
            for child in children: self.inflate(child, node)
        elif kind == 'text':
            template = str(w.get('text', ''))
            node.text = fill(template, None)
            node.binds.append(lambda ctx: self.say(node, fill(template, ctx)))
        elif kind == 'image':
            src = str(w.get('src', ''))
            if src.startswith(('asset:', 'gfx:')): node.binds.append(lambda ctx: self.picture(node, src))
            elif src.startswith('$'): node.binds.append(lambda ctx: self.picture(node, lookup(src[1:], ctx)))
            if src.startswith('asset:'): self.picture(node, src)
        elif kind == 'bar':
            bar_fill = self.part(node, 'fill')
            label = self.part(node, 'label') if 'label' in w else None
            if label: label.text = fill(str(w['label']), None)
            bar_fill.bound = [('width', '0%')]
            value_key, max_key, fixed = strip(w.get('value', '')), strip(w['maxKey']) if 'maxKey' in w else None, number(w.get('max', 1.0))
            def bar(ctx):
                top = number(lookup(max_key, ctx)) if max_key else fixed
                part = max(0.0, min(1.0, number(lookup(value_key, ctx)) / top)) if top > 0 else 0.0
                self.bind(bar_fill, [('width', '%.3f%%' % (part * 100))])
                if label: self.say(label, fill(str(w['label']), ctx))
            node.binds.append(bar)
        elif kind == 'list':
            if not isinstance(w.get('template'), dict): raise ValueError("list needs a 'template'")
            node.manages = True
            empty, items, path = self.part(node, 'empty', sibling=False), [], strip(w.get('items', ''))
            empty.text, empty.hidden = str(w.get('empty', '')), True
            def rows(ctx):
                root = ctx.root if isinstance(ctx, Scope) else ctx
                values = lookup(path, ctx)
                values = values if isinstance(values, list) else []
                if len(values) != len(items):
                    for item in items: node.children.remove(item)
                    items[:] = [self.inflate(w['template'], node) for _ in values]
                    self.mark(node)
                self.hide(empty, not (not values and 'empty' in w))
                for index, item in enumerate(items): self.apply(item, Scope(values[index], index, root))
            node.binds.append(rows)
        elif kind == 'tabs':
            tabs = [t for t in w.get('tabs') or [] if isinstance(t, dict) and isinstance(t.get('child'), dict)]
            strip_, content = self.part(node, 'tab-bar'), self.part(node, 'tab-content')
            labels, panels = [self.part(strip_, 'tab') for _ in tabs], [self.inflate(t['child'], content) for t in tabs]
            def select(index):
                for i, (label, panel) in enumerate(zip(labels, panels)): label.active, panel.switched = i == index, i != index
                self.mark(node); self.flush()
            for i, (label, tab) in enumerate(zip(labels, tabs)):
                label.text, label.name, label.click = str(tab.get('title', '')), str(tab.get('title', '')), (lambda i=i: select(i))
            select(0)
        elif kind == 'pages':
            pages = [p for p in w.get('pages') or [] if isinstance(p, dict) and isinstance(p.get('child'), dict)]
            if not pages: raise ValueError('pages needs at least one page')
            names, state = [str(p.get('name')) for p in pages], str(w.get('state', 'page'))
            first = str(w.get('initial', names[0]))
            self.initial.setdefault(state, first)
            self.ui.setdefault(state, first)
            panels = [self.inflate(p['child'], node) for p in pages]
            def turn(_ctx):
                name = show(self.ui.get(state))
                index = names.index(name) if name in names else names.index(first) if first in names else 0
                for i, panel in enumerate(panels):
                    if panel.switched != (i != index): panel.switched, self.stale = i != index, True
            turn(None)
            node.binds.append(turn)
        return node

    def hide(self, node, hidden):
        if node.hidden != hidden: node.hidden, self.stale = hidden, True

    def say(self, node, text):
        if node.text != text: node.text, self.stale = text, True

    def bind(self, node, decls):
        if decls != node.bound:
            node.bound = decls
            self.mark(node)

    def picture(self, node, key):
        key = key if isinstance(key, str) else None
        if key == node.key and (node.image is not None or key is None): return
        node.key, node.image, self.stale = key, self.find(key) if key else None, True

    # -- data and taps ---------------------------------------------------------------------------------------------------
    def update(self, values):
        """A snapshot from the pack's update(); its 'ui' entry holds actions (navigate …), not data."""
        todo = values.get('ui') if isinstance(values, dict) else None
        self.snapshot = {k: v for k, v in values.items() if k != 'ui'} if isinstance(values, dict) else {}
        self.rebind()
        if todo is not None: self.perform(actions(todo, script=True))

    def rebind(self):
        self.apply(self.root, {**(self.snapshot or {}), 'ui': dict(self.ui)})
        self.flush()

    def apply(self, node, ctx):
        for bind in node.binds: bind(ctx)
        if not node.manages:
            for child in list(node.children): self.apply(child, ctx)

    def perform(self, todo, ctx=None):
        changed, calls = False, []
        def put(key, value):
            nonlocal changed
            if key in self.ui and self.ui[key] == value and type(self.ui[key]) is type(value): return
            self.ui[key], changed = value, True
        def value_of(v):
            if not isinstance(v, str): return v
            whole = re.match(r'\{([^{}]+)\}\Z', v)
            return lookup(whole[1], ctx) if whole else fill(v, ctx)
        for action in todo:
            if action[0] == 'set':
                for key, v in action[1].items(): put(key, value_of(v))
            elif action[0] == 'navigate':
                page, state = fill(action[1], ctx), action[2]
                current = self.ui.get(state)
                if page != show(current) or current is None:
                    if current is not None: self.history[state] = (self.history.get(state, []) + [show(current)])[-32:]
                    put(state, page)
            elif action[0] == 'back':
                stack = self.history.get(action[1]) or []
                previous = stack.pop() if stack else self.initial.get(action[1])
                if previous is not None: put(action[1], previous)
            else: calls.append((action[1], [value_of(a) for a in action[2]]))
        if changed:
            self.rebind()
            self.on_ui(dict(self.ui))
        for name, args in calls: self.on_call(name, args)

    def tap(self, node):
        if callable(node.click): node.click()
        elif node.click: self.perform(node.click, node.ctx)

    def press(self, node, down):
        if node.pressed != down:
            node.pressed = down
            self.mark(node)
            self.flush()

    # -- styles (StyleResolver.kt) ---------------------------------------------------------------------------------------
    def mark(self, node): self.dirty.append(node)

    def flush(self):
        if not self.dirty or self.root is None: return
        dirty, self.dirty, self.stale = self.dirty, [], True
        marked = set(map(id, dirty))
        for node in dirty:
            up, covered = node.parent, False
            while up is not None and not covered: covered, up = id(up) in marked, up.parent
            attached = node is self.root or (node.parent is not None and node in node.parent.children)
            if not covered and attached: self.restyle(node)

    def restyle(self, node):
        parent = node.parent
        matched = self.sheet.matching(node)
        decls = [d for r in matched if r[0] == 0 for d in r[4]] + node.defaults + [d for r in matched if r[0] == 1 for d in r[4]] + node.inline + node.bound
        variables = dict(parent.vars) if parent is not None else {}
        for name, value in decls:
            if name.startswith('--'): variables[name] = value
        style = {}
        for name, value in decls:
            if name.startswith('--'): continue
            if 'var(' in value:
                value = self.substitute(value, variables)
                if value is None: continue
            for prop, v in expand(name, value):
                low = v.lower()
                if low in ('initial', 'unset') or (low == 'inherit' and parent is None): style.pop(prop, None)
                elif low == 'inherit': style[prop] = parent.get(prop)
                else: style[prop] = v
        fs = float(parent.style['font-size'][:-2]) if parent is not None else 14.0
        mine = style.get('font-size')
        if mine:
            size = length(mine, fs, self.vw, self.vh)
            fs = max(0.0, resolve(size, fs)) if size is not None else fs
        style['font-size'] = f'{fs}px'
        for prop in ('letter-spacing', 'line-height'):  # inherited as px, not as "1.2em"
            v = style.get(prop)
            if v and v.lower() != 'normal':
                size = length(v, fs, self.vw, self.vh)
                unitless = prop == 'line-height' and NUMBER.match(v.strip()) and not NUMBER.match(v.strip())[2]
                style[prop] = f'{float(v) * fs if unitless else resolve(size, fs)}px' if size is not None else 'normal'
        if parent is not None:
            for prop in INHERITED:
                if prop not in style and prop in parent.style: style[prop] = parent.style[prop]
        if style != node.style or variables != node.vars or not node.style:
            node.style, node.vars, node.cache, self.stale = style, variables, {}, True
        for child in node.children: self.restyle(child)

    def substitute(self, value, variables, depth=0):
        while 'var(' in value and depth < 20:
            start = value.rfind('var(')  # innermost first
            level, end = 1, start + 4
            while end < len(value) and level: level += (value[end] == '(') - (value[end] == ')'); end += 1
            name, _, fallback = value[start + 4:end - 1].partition(',')
            found = variables.get(name.strip())
            if found is None: found = fallback.strip() if fallback.strip() else None
            if found is None: return None
            value, depth = value[:start] + found + value[end:], depth + 1
        return value

    # -- typed values ----------------------------------------------------------------------------------------------------
    def px(self, node, prop):
        """A length property as (px, percent) or None (auto, none)."""
        cache = node.cache
        if prop not in cache:
            v = node.style.get(prop)
            cache[prop] = length(v, float(node.style['font-size'][:-2]), self.vw, self.vh) if v else None
        return cache[prop]

    def num(self, node, prop, default=0.0):
        try: return float(node.get(prop))
        except ValueError: return default

    def box(self, node):
        """(border widths, paddings) as (top, right, bottom, left) each."""
        hit = node.cache.get('#box')
        if hit is None:
            border, pad = [], []
            for side in SIDES:
                w = self.px(node, f'border-{side}-width')
                on = node.style.get(f'border-{side}-style', 'none').lower() not in ('none', 'hidden')
                border.append(max(0.0, w[0]) if w and on else 0.0)
                p = self.px(node, f'padding-{side}')
                pad.append(max(0.0, p[0]) if p else 0.0)
            hit = node.cache['#box'] = (border, pad)
        return hit

    def margins(self, node, base):
        """[top, right, bottom, left]; an auto margin is None."""
        out = []
        for side in SIDES:
            v = node.style.get(f'margin-{side}')
            if v and v.strip().lower() == 'auto': out.append(None)
            else: out.append(resolve(self.px(node, f'margin-{side}'), base) or 0.0)
        return out

    def limits(self, node, pw, ph):
        lo = lambda prop, base: max(0.0, resolve(self.px(node, prop), base) or 0.0)
        hi = lambda prop, base: (lambda v: INF if v is None else max(0.0, v))(resolve(self.px(node, prop), base))
        return lo('min-width', pw), hi('max-width', pw), lo('min-height', ph), hi('max-height', ph)

    def font(self, node):
        hit = node.cache.get('#font')
        if hit is None:
            s = node.style
            key = (s.get('font-family', 'sans-serif'), s['font-size'], s.get('font-weight', '400'), s.get('font-style', 'normal'), s.get('letter-spacing', 'normal'),
                   s.get('text-decoration-line', 'none'))
            hit = self.fonts.get(key)
            if hit is None:
                names = [self.families.get(n.strip().strip('"\'').lower(), GENERIC.get(n.strip().lower(), n.strip().strip('"\'')))
                         for n in split(key[0], ',')]
                f = QFont(names)
                f.setPixelSize(max(1, round(float(key[1][:-2]))))
                try: f.setWeight(QFont.Weight(max(1, min(1000, int(float(key[2]))))))
                except ValueError: pass
                f.setItalic(key[3] != 'normal')
                f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)  # the painter scales: sizes must grow evenly
                if key[4] != 'normal': f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(key[4][:-2]))
                f.setUnderline('underline' in key[5]); f.setStrikeOut('line-through' in key[5])
                hit = self.fonts[key] = (f, QFontMetricsF(f))
            node.cache['#font'] = hit
        return hit

    def lines(self, node, room):
        """The text of a node as lines for the given width (None: unlimited) -> (lines, width, line height)."""
        key = ('#text', node.text, room)
        hit = node.cache.get(key)
        if hit is None:
            f, fm = self.font(node)
            text, change = node.text or '', node.style.get('text-transform', 'none')
            text = text.upper() if change == 'uppercase' else text.lower() if change == 'lowercase' else ' '.join(w[:1].upper() + w[1:] for w in text.split(' ')) if change == 'capitalize' else text
            space = node.style.get('white-space', 'normal')
            lh = node.style.get('line-height', 'normal')
            height = float(lh[:-2]) if lh.endswith('px') else fm.ascent() + fm.descent()
            clamp = node.style.get('line-clamp', 'none')
            if space in ('nowrap', 'pre'): rows = [text.split('\n')[0]]
            else:
                rows = []
                for para in text.split('\n'):
                    line = ''
                    for word in para.split(' '):
                        trial = f'{line} {word}' if line else word
                        if line and room is not None and fm.horizontalAdvance(trial) > room + 0.01: rows.append(line); line = word
                        else: line = trial
                    rows.append(line)
                if clamp.isdigit() and len(rows) > int(clamp): rows = rows[:int(clamp) - 1] + [' '.join(rows[int(clamp) - 1:])]
            hit = node.cache[key] = (rows, max((fm.horizontalAdvance(r) for r in rows), default=0.0) if text else 0.0, height)
        return hit

    def find(self, key):
        """A widget's picture: 'asset:…' from the pack's assets folder, 'gfx:…' from the script."""
        if not key.startswith('asset:'): return self.load_image(key)
        root = os.path.join(os.path.normpath(self.folder), 'assets')
        path = os.path.normpath(os.path.join(root, key[6:]))
        return self.file(path) if path.startswith(root + os.sep) else None

    def file(self, path):
        """A picture from the pack, decoded once."""
        if path not in self.files:
            image = QImage(path) if path and os.path.isfile(path) else QImage()
            self.files[path] = None if image.isNull() else image
        return self.files[path]

    # -- layout (LayoutEngine.kt) ----------------------------------------------------------------------------------------
    def shown(self, node): return not (node.hidden or node.switched) and node.get('display') != 'none'

    def layout(self):
        self.stale = False
        self.walk(self.root, lambda n: n.sizes.clear())
        key = (self.vw, self.vh, None, None, None)
        self.lay(self.root, *key)
        self.commit(self.root, key, 0.0, 0.0)

    def walk(self, node, fn):
        fn(node)
        for child in node.children: self.walk(child, fn)

    def commit(self, node, key, x, y):
        w, h, placed = node.sizes[key]
        node.rect = (x, y, w, h)
        for child, cx, cy, ckey in placed: self.commit(child, ckey, x + cx, y + cy)

    def lay(self, node, pw, ph, aw, fw, fh):
        """Size of a node (border box) and the places of its children. pw/ph: the box percentages refer to (None: not
        known), aw: the room a content-sized width may take (None: unlimited), fw/fh: sizes the parent decided."""
        key = (pw, ph, aw, fw, fh)
        hit = node.sizes.get(key)
        if hit is not None: return hit
        border, pad = self.box(node)
        ex, ey = border[1] + border[3] + pad[1] + pad[3], border[0] + border[2] + pad[0] + pad[2]
        outer = node.get('box-sizing') == 'content-box'
        minw, maxw, minh, maxh = self.limits(node, pw, ph)
        w = fw if fw is not None else resolve(self.px(node, 'width'), pw)
        h = fh if fh is not None else resolve(self.px(node, 'height'), ph)
        if outer:
            if fw is None and w is not None: w += ex
            if fh is None and h is not None: h += ey
        ratio = self.ratio(node)
        if ratio:
            if w is None and h is not None: w = h * ratio
            elif h is None and w is not None: h = w / ratio
        if fw is None and w is not None: w = max(minw, min(w, maxw))
        if fh is None and h is not None: h = max(minh, min(h, maxh))
        room = None if aw is None else max(0.0, min(aw, maxw) - ex)
        if w is None and maxw < INF and room is None: room = max(0.0, maxw - ex)
        def content(iw, ih):
            if node.text is not None:
                rows, tw, lh = self.lines(node, iw if iw is not None else room)
                return tw, len(rows) * lh, []
            if node.type == 'image' and node.kind == 'widget':
                return (node.image.width(), node.image.height(), []) if node.image is not None else (0.0, 0.0, [])
            items = [c for c in node.children if self.shown(c) and c.get('position') != 'absolute']
            mode = node.get('display')
            return (self.grid if mode == 'grid' else self.stack if mode == 'stack' else self.flex)(node, items, iw, ih, room)
        ih = None if h is None else max(0.0, h - ey)
        cw, ch, placed = content(None if w is None else max(0.0, w - ex), ih)
        if w is None:
            w = max(minw, min(cw + ex, maxw))
            if abs(w - cw - ex) > 0.01: cw, ch, placed = content(max(0.0, w - ex), ih)  # min/max changed it: the content follows
        if h is None:
            h = max(minh, min(w / ratio if ratio else ch + ey, maxh))
            if abs(h - ch - ey) > 0.01 and node.text is None: cw, ch, placed = content(max(0.0, w - ex), max(0.0, h - ey))
        ox, oy = border[3] + pad[3], border[0] + pad[0]
        placed = [(child, x + ox, y + oy, k) for child, x, y, k in placed]
        bw, bh = w - border[1] - border[3], h - border[0] - border[2]  # the padding box holds absolute children
        for child in node.children:
            if not self.shown(child) or child.get('position') != 'absolute': continue
            left, right, top, bottom = (resolve(self.px(child, side), bw if side in ('left', 'right') else bh) for side in ('left', 'right', 'top', 'bottom'))
            m = [v or 0.0 for v in self.margins(child, bw)]
            lim = self.limits(child, bw, bh)
            cfw = cfh = None
            if resolve(self.px(child, 'width'), bw) is None and left is not None and right is not None: cfw = max(lim[0], min(bw - left - right - m[1] - m[3], lim[1]))
            if resolve(self.px(child, 'height'), bh) is None and top is not None and bottom is not None: cfh = max(lim[2], min(bh - top - bottom - m[0] - m[2], lim[3]))
            ckey = (bw, bh, max(0.0, bw - (left or 0) - (right or 0) - m[1] - m[3]), cfw, cfh)
            cw_, ch_, _ = self.lay(child, *ckey)
            x = border[3] + left + m[3] if left is not None else border[3] + bw - right - m[1] - cw_ if right is not None else ox + m[3]
            y = border[0] + top + m[0] if top is not None else border[0] + bh - bottom - m[2] - ch_ if bottom is not None else oy + m[0]
            placed.append((child, x, y, ckey))
        hit = node.sizes[key] = (w, h, placed)
        return hit

    def ratio(self, node):
        v = node.style.get('aspect-ratio')
        if not v or v.strip().lower() == 'auto': return None
        try:
            a, _, b = v.partition('/')
            r = float(a) / (float(b) if b.strip() else 1.0)
            return r if r > 0 else None
        except (ValueError, ZeroDivisionError): return None

    def align(self, node, child, axis):
        """How a child sits across (axis 'align') or along ('justify') its cell: 'stretch', 'start', 'center' or 'end'."""
        v = child.get(f'{axis}-self').lower()
        if v == 'auto': v = node.get(f'{axis}-items').lower()
        return {'flex-start': 'start', 'left': 'start', 'baseline': 'start', 'flex-end': 'end', 'right': 'end', 'normal': 'stretch'}.get(v, v)

    def flex(self, node, items, iw, ih, room):
        direction, wrap = node.get('flex-direction').lower(), node.get('flex-wrap').lower() != 'nowrap'
        row, reverse = direction.startswith('row'), direction.endswith('reverse')
        gap_r, gap_c = (max(0.0, (self.px(node, p) or (0.0, 0.0))[0]) for p in ('row-gap', 'column-gap'))
        gap, cross_gap = (gap_c, gap_r) if row else (gap_r, gap_c)
        main, cross = (iw, ih) if row else (ih, iw)
        items = sorted(items, key=lambda c: self.num(c, 'order'))
        A, B = (3, 1) if row else (0, 2)  # the margins before and after along the main axis
        C, D = (0, 2) if row else (3, 1)
        info = []
        for c in items:
            m = self.margins(c, iw)
            mm, mc = (m[A] or 0.0) + (m[B] or 0.0), (m[C] or 0.0) + (m[D] or 0.0)
            lim = self.limits(c, iw, ih)
            lo, hi = (lim[0], lim[1]) if row else (lim[2], lim[3])
            basis = c.get('flex-basis').lower()
            base = resolve(self.px(c, 'width' if row else 'height'), main) if basis == 'auto' else None if basis == 'content' else resolve(self.px(c, 'flex-basis'), main)
            sized = resolve(self.px(c, 'height' if row else 'width'), cross) is not None  # its cross size is its own
            how = self.align(node, c, 'align')
            stretch = how == 'stretch' and not sized and m[C] is not None and m[D] is not None
            if base is None:  # as large as its content
                if row: base = self.lay(c, iw, ih, None, None, None)[0]
                else: base = self.lay(c, iw, ih, None if cross is None and room is None else max(0.0, (cross if cross is not None else room) - mc),
                                      max(lim[0], min(cross - mc, lim[1])) if stretch and cross is not None else None, None)[1]
            info.append({'c': c, 'm': m, 'mm': mm, 'mc': mc, 'lo': lo, 'hi': hi, 'base': base, 'main': max(lo, min(base, hi)), 'grow': self.num(c, 'flex-grow'),
                         'shrink': self.num(c, 'flex-shrink', 1.0), 'how': how, 'stretch': stretch, 'lim': lim})
        limit = main if main is not None else room if row else None
        lines = [[]]
        for i in info:
            used = sum(j['main'] + j['mm'] for j in lines[-1]) + gap * len(lines[-1])
            if wrap and limit is not None and lines[-1] and used + i['main'] + i['mm'] > limit + 0.01: lines.append([])
            lines[-1].append(i)
        for line in lines:
            if main is not None: self.flexible(line, main - gap * (len(line) - 1))
        def place(i, cross_size):  # the final layout of an item; cross_size: its line's, None while that is being found
            c, m = i['c'], i['m']
            forced = max(i['lim'][2 if row else 0], min(cross_size - i['mc'], i['lim'][3 if row else 1])) if i['stretch'] and cross_size is not None else None
            fixed = i['main'] if main is not None or row else None
            ck = (iw, ih, None, i['main'], forced) if row else (iw, ih, None if cross_size is None and room is None else max(0.0, (cross_size if cross_size is not None else room) - i['mc']), forced, fixed)
            i['key'], (i['w'], i['h'], _) = ck, self.lay(c, *ck)
            return (i['h'] if row else i['w']) + i['mc']
        sizes = []
        for line in lines:
            if cross is not None and len(lines) == 1: size = cross
            else: size = max((place(i, None) for i in line), default=0.0)
            sizes.append(size)
        extra = cross - sum(sizes) - cross_gap * (len(lines) - 1) if cross is not None else 0.0
        packing = node.get('align-content').lower()
        if len(lines) > 1 and extra > 0 and packing in ('normal', 'stretch'): sizes, extra = [s + extra / len(lines) for s in sizes], 0.0
        at_cross = extra / 2 if packing == 'center' and len(lines) > 1 else extra if packing in ('end', 'flex-end') and len(lines) > 1 else 0.0
        placed, longest = [], 0.0
        justify = node.get('justify-content').lower()
        for line, size in zip(lines, sizes):
            for i in line: place(i, size)
            used = sum((i['w'] if row else i['h']) + i['mm'] for i in line) + gap * (len(line) - 1)
            longest = max(longest, used)
            free = (main - used) if main is not None else 0.0
            autos = sum((i['m'][A] is None) + (i['m'][B] is None) for i in line)
            at, between = 0.0, gap
            if autos and free > 0: share = free / autos
            else:
                share, n = 0.0, len(line)
                if justify == 'center': at = free / 2
                elif justify in ('flex-end', 'end', 'right'): at = free
                elif justify == 'space-between' and n > 1 and free > 0: between += free / (n - 1)
                elif justify == 'space-around' and n and free > 0: at, between = free / n / 2, between + free / n
                elif justify == 'space-evenly' and n and free > 0: at, between = free / (n + 1), between + free / (n + 1)
            for i in line:
                m, length_, thick = i['m'], i['w'] if row else i['h'], i['h'] if row else i['w']
                at += share if m[A] is None else m[A]
                spare = size - thick - i['mc']
                if m[C] is None or m[D] is None: off = (m[C] or 0.0) + (max(0.0, spare) / (2 if m[D] is None else 1) if m[C] is None else 0.0)
                else: off = m[C] + (spare / 2 if i['how'] == 'center' else spare if i['how'] == 'end' else 0.0)
                pos = (main if main is not None else used) - at - length_ if reverse else at
                placed.append((i['c'], pos, at_cross + off, i['key']) if row else (i['c'], at_cross + off, pos, i['key']))
                at += length_ + (share if m[B] is None else m[B]) + between
            at_cross += size + cross_gap
        total = sum(sizes) + cross_gap * (len(lines) - 1)
        return (main if main is not None else longest, cross if cross is not None else total, placed) if row else (cross if cross is not None else total, main if main is not None else longest, placed)

    @staticmethod
    def flexible(line, room):
        """CSS's "resolving flexible lengths": grow or shrink the items of a line to fill room."""
        growing = sum(i['main'] + i['mm'] for i in line) < room
        for i in line:
            factor = i['grow'] if growing else i['shrink']
            i['frozen'] = factor == 0 or (i['base'] > i['main'] if growing else i['base'] < i['main'])
        for _ in range(len(line) + 1):
            active = [i for i in line if not i['frozen']]
            if not active: break
            free = room - sum(i['mm'] + (i['main'] if i['frozen'] else i['base']) for i in line)
            if growing:
                total = sum(i['grow'] for i in active)
                if total < 1: free *= total
                for i in active: i['main'] = i['base'] + (free * i['grow'] / total if total else 0.0)
            else:
                total = sum(i['shrink'] * i['base'] for i in active)
                for i in active: i['main'] = i['base'] + (free * i['shrink'] * i['base'] / total if total else 0.0)
            off = 0.0
            for i in active:
                fit = max(i['lo'], min(i['main'], i['hi']))
                i['off'], i['main'] = fit - i['main'], fit
                off += i['off']
            for i in active:
                if off == 0 or (off > 0) == (i['off'] > 0) and i['off'] != 0: i['frozen'] = True

    def tracks(self, node, prop, room, gap, count):
        """grid-template-*: [('px', n) | ('fr', n, floor) | ('auto', 0, floor)]."""
        text = node.style.get(prop, 'none').strip().lower()
        if text in ('none', ''): return []
        def one(token):
            m = re.match(r'minmax\((.*)\)\Z', token)
            if m:
                lo, hi = (split(m[1], ',') + ['auto'])[:2]
                floor = resolve(length(lo), room) or 0.0
                if hi.endswith('fr'): return ('fr', float(hi[:-2] or 1), floor)
                top = resolve(length(hi), room)
                return ('px', max(floor, top)) if top is not None else ('auto', 0.0, floor)
            if token.endswith('fr'):
                try: return ('fr', float(token[:-2] or 1), 0.0)
                except ValueError: return ('auto', 0.0, 0.0)
            v = resolve(length(token), room)
            return ('px', max(0.0, v)) if v is not None else ('auto', 0.0, 0.0)
        out = []
        for token in split(text):
            m = re.match(r'repeat\(\s*([^,]+),(.*)\)\Z', token)
            if not m: out.append(one(token)); continue
            inner = [one(t) for t in split(m[2])]
            n = m[1].strip()
            if n in ('auto-fill', 'auto-fit'):
                each = sum((t[1] if t[0] == 'px' else t[2]) for t in inner) + gap * len(inner)
                fit = max(1, int(((room or 0.0) + gap) // each)) if each > 0 and room is not None else 1
                if n == 'auto-fit': fit = max(1, min(fit, -(-count // len(inner))))
                out += inner * min(fit, 64)
            else: out += inner * max(1, min(int(float(n)), 256))
        return out

    def grid(self, node, items, iw, ih, room):
        gap_r, gap_c = (max(0.0, (self.px(node, p) or (0.0, 0.0))[0]) for p in ('row-gap', 'column-gap'))
        wide = iw if iw is not None else room
        cols = self.tracks(node, 'grid-template-columns', wide, gap_c, len(items)) or [('auto', 0.0, 0.0)]
        n, cells, taken, r, c = len(cols), [], set(), 0, 0
        for item in sorted(items, key=lambda c_: self.num(c_, 'order')):  # row-major auto-placement; "span n" and a start column
            m = re.match(r'(?:(\d+)\s*)?(?:/\s*)?(?:span\s+(\d+)|(\d+))?\s*\Z', item.style.get('grid-column', 'auto').strip().lower())
            start = int(m[1]) - 1 if m and m[1] else None
            span = max(1, min(n, int(m[2]) if m and m[2] else int(m[3]) - int(m[1]) if m and m[3] and m[1] else 1))
            while True:
                if start is not None and c > start: r, c = r + 1, 0
                if start is not None: c = min(start, n - span)
                if c + span <= n and not any((r, c + k) in taken for k in range(span)): break
                c += 1
                if c + span > n: r, c = r + 1, 0
            taken.update((r, c + k) for k in range(span))
            cells.append((item, r, c, span))
            c += span
            if c >= n: r, c = r + 1, 0
        nrows = max((cell[1] for cell in cells), default=-1) + 1
        m_of = {id(item): [v or 0.0 for v in self.margins(item, iw)] for item, *_ in cells}
        widths = [t[1] if t[0] == 'px' else 0.0 for t in cols]
        for k, t in enumerate(cols):  # content-sized columns (and fr ones when there is no width to share)
            if t[0] == 'auto' or (t[0] == 'fr' and wide is None):
                widths[k] = max([t[2]] + [self.lay(item, None, ih, None, None, None)[0] + m_of[id(item)][1] + m_of[id(item)][3] for item, _, c_, span in cells if c_ == k and span == 1])
        if wide is not None:
            left = wide - sum(widths) - gap_c * (n - 1)
            frs = [k for k, t in enumerate(cols) if t[0] == 'fr']
            while frs:  # a column that would fall below its floor keeps the floor, the others share the rest
                unit = max(0.0, left) / sum(cols[k][1] for k in frs)
                low = [k for k in frs if cols[k][1] * unit < cols[k][2]]
                if not low:
                    for k in frs: widths[k] = cols[k][1] * unit
                    break
                for k in low: widths[k], left = cols[k][2], left - cols[k][2]
                frs = [k for k in frs if k not in low]
        xs = [sum(widths[:k]) + gap_c * k for k in range(n)]
        def size(cell, row_h):
            item, _, c_, span = cell
            m = m_of[id(item)]
            cw = sum(widths[c_:c_ + span]) + gap_c * (span - 1)
            lim = self.limits(item, cw, row_h)
            fw = max(lim[0], min(cw - m[1] - m[3], lim[1])) if self.align(node, item, 'justify') == 'stretch' and resolve(self.px(item, 'width'), cw) is None else None
            fh = max(lim[2], min(row_h - m[0] - m[2], lim[3])) if row_h is not None and self.align(node, item, 'align') == 'stretch' and resolve(self.px(item, 'height'), row_h) is None else None
            key = (cw, row_h, max(0.0, cw - m[1] - m[3]), fw, fh)
            return key, self.lay(item, *key)
        rows = self.tracks(node, 'grid-template-rows', ih, gap_r, nrows)
        rows += [('auto', 0.0, 0.0)] * (nrows - len(rows))
        heights = [t[1] if t[0] == 'px' else 0.0 for t in rows]
        for k, t in enumerate(rows):
            if k < nrows and (t[0] == 'auto' or (t[0] == 'fr' and ih is None)):
                heights[k] = max([t[2]] + [size(cell, None)[1][1] + m_of[id(cell[0])][0] + m_of[id(cell[0])][2] for cell in cells if cell[1] == k])
        if ih is not None:
            frs = [k for k, t in enumerate(rows) if t[0] == 'fr']
            left = ih - sum(heights) - gap_r * (len(rows) - 1)
            for k in frs: heights[k] = max(rows[k][2], rows[k][1] * max(0.0, left) / sum(rows[j][1] for j in frs))
        ys = [sum(heights[:k]) + gap_r * k for k in range(len(rows))]
        placed = []
        for cell in cells:
            item, r_, c_, span = cell
            m, cw, rh = m_of[id(item)], sum(widths[c_:c_ + span]) + gap_c * (span - 1), heights[r_]
            key, (w, h, _) = size(cell, rh)
            jx, jy = self.align(node, item, 'justify'), self.align(node, item, 'align')
            dx = (cw - w - m[1] - m[3]) * (0.5 if jx == 'center' else 1 if jx == 'end' else 0)
            dy = (rh - h - m[0] - m[2]) * (0.5 if jy == 'center' else 1 if jy == 'end' else 0)
            placed.append((item, xs[c_] + m[3] + dx, ys[r_] + m[0] + dy, key))
        total_w, total_h = sum(widths) + gap_c * (n - 1), sum(heights) + gap_r * max(0, len(rows) - 1)
        return iw if iw is not None else total_w, ih if ih is not None else total_h, placed

    def stack(self, node, items, iw, ih, room):
        done = []
        for c in items:
            m = [v or 0.0 for v in self.margins(c, iw)]
            lim = self.limits(c, iw, ih)
            jx, jy = self.align(node, c, 'justify'), self.align(node, c, 'align')
            jx, jy = ('start' if jx == 'stretch' and node.get('justify-items').lower() == 'normal' and c.get('justify-self').lower() == 'auto' else jx,
                      'start' if jy == 'stretch' and node.get('align-items').lower() == 'normal' and c.get('align-self').lower() == 'auto' else jy)
            fw = max(lim[0], min(iw - m[1] - m[3], lim[1])) if jx == 'stretch' and iw is not None and resolve(self.px(c, 'width'), iw) is None else None
            fh = max(lim[2], min(ih - m[0] - m[2], lim[3])) if jy == 'stretch' and ih is not None and resolve(self.px(c, 'height'), ih) is None else None
            wide = iw if iw is not None else room
            key = (iw, ih, None if wide is None else max(0.0, wide - m[1] - m[3]), fw, fh)
            w, h, _ = self.lay(c, *key)
            done.append((c, key, w, h, m, jx, jy))
        cw = iw if iw is not None else max((d[2] + d[4][1] + d[4][3] for d in done), default=0.0)
        ch = ih if ih is not None else max((d[3] + d[4][0] + d[4][2] for d in done), default=0.0)
        placed = []
        for c, key, w, h, m, jx, jy in done:
            if jx == 'stretch' and iw is None and resolve(self.px(c, 'width'), None) is None:  # the stack took its width from its largest child
                key = (iw, ih, None, max(0.0, cw - m[1] - m[3]), key[4])
                w, h, _ = self.lay(c, *key)
            dx = (cw - w - m[1] - m[3]) * (0.5 if jx == 'center' else 1 if jx == 'end' else 0)
            dy = (ch - h - m[0] - m[2]) * (0.5 if jy == 'center' else 1 if jy == 'end' else 0)
            placed.append((c, m[3] + dx, m[0] + dy, key))
        return cw, ch, placed

    # -- painting (CssPainter.kt, CompanionScreen.kt) --------------------------------------------------------------------
    def paint(self, p, scale=1.0):
        """Paints the tree in CSS px (the painter is already scaled by `scale`). Fills self.clicks [(QRectF, node)]."""
        if self.stale: self.layout()
        self.clicks, self.scale = [], scale
        self.draw(p, self.root, True)

    def draw(self, p, node, visible):
        if not self.shown(node) or node.rect is None: return
        x, y, w, h = node.rect
        if node.get('position') == 'relative':
            left, top = resolve(self.px(node, 'left'), None), resolve(self.px(node, 'top'), None)
            if left or top:
                p.save(); p.translate(left or 0.0, top or 0.0)
                self.draw_at(p, node, visible, x, y, w, h)
                return p.restore()
        self.draw_at(p, node, visible, x, y, w, h)

    def draw_at(self, p, node, visible, x, y, w, h):
        opacity = max(0.0, min(1.0, self.num(node, 'opacity', 1.0)))
        if opacity <= 0: return
        if opacity < 1:  # the subtree as one picture, then faded: text on its own panel must not shine through
            k, pad = self.scale, 6
            image = QImage(math.ceil((w + 2 * pad) * k), math.ceil((h + 2 * pad) * k), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            q = QPainter(image)
            q.setRenderHints(p.renderHints())
            q.scale(k, k); q.translate(pad - x, pad - y)
            self.body(q, node, visible, x, y, w, h)
            q.end()
            p.save(); p.setOpacity(p.opacity() * opacity)
            p.drawImage(QRectF(x - pad, y - pad, image.width() / k, image.height() / k), image)
            return p.restore()
        self.body(p, node, visible, x, y, w, h)

    def body(self, p, node, visible, x, y, w, h):
        s = node.style
        visible = s.get('visibility', 'visible') == 'visible'
        rect = QRectF(x, y, w, h)
        border, pad = self.box(node)
        radii = [min(max(0.0, resolve(self.px(node, f'border-{c}-radius'), min(w, h)) or 0.0), min(w, h) / 2) for c in CORNERS]
        if visible: self.frame(p, node, rect, border, radii)
        clip = s.get('overflow', 'visible').lower() in ('hidden', 'clip')
        if clip:
            p.save()
            p.setClipPath(self.outline(rect, radii), Qt.ClipOperation.IntersectClip)
        if visible and node.text: self.write(p, node, x + border[3] + pad[3], y + border[0] + pad[0], w - border[1] - border[3] - pad[1] - pad[3], h - border[0] - border[2] - pad[0] - pad[2])
        if visible and node.type == 'image' and node.kind == 'widget':
            if node.image is None and node.key: node.image = self.find(node.key)
            if node.image is not None: self.show_image(p, node, QRectF(x + border[3] + pad[3], y + border[0] + pad[0], w - border[1] - border[3] - pad[1] - pad[3], h - border[0] - border[2] - pad[0] - pad[2]))
        for child in sorted(node.children, key=lambda c: int(self.num(c, 'z-index'))) if any('z-index' in c.style for c in node.children) else node.children:
            self.draw(p, child, visible)
        if clip: p.restore()
        if node.click: self.clicks.append((rect, node))

    @staticmethod
    def outline(rect, radii):
        path = QPainterPath()
        if not any(radii): path.addRect(rect); return path
        x, y, r, b = rect.left(), rect.top(), rect.right(), rect.bottom()
        tl, tr, br, bl = radii
        path.moveTo(x + tl, y)
        path.lineTo(r - tr, y); path.arcTo(r - 2 * tr, y, 2 * tr, 2 * tr, 90, -90)
        path.lineTo(r, b - br); path.arcTo(r - 2 * br, b - 2 * br, 2 * br, 2 * br, 0, -90)
        path.lineTo(x + bl, b); path.arcTo(x, b - 2 * bl, 2 * bl, 2 * bl, 270, -90)
        path.lineTo(x, y + tl); path.arcTo(x, y, 2 * tl, 2 * tl, 180, -90)
        path.closeSubpath()
        return path

    def frame(self, p, node, rect, border, radii):
        s, ink = node.style, color(node.get('color'))
        path = self.outline(rect, radii)
        shadow = s.get('box-shadow', 'none')
        if shadow.lower() != 'none':
            parts = split(split(shadow, ',')[0])
            sizes = [length(t, float(s['font-size'][:-2]), self.vw, self.vh) for t in parts]
            nums = [v[0] for v in sizes if v is not None]
            tint = next((color(t, ink) for t, v in zip(parts, sizes) if v is None and t.lower() != 'inset'), ink)
            if len(nums) >= 2 and 'inset' not in [t.lower() for t in parts]:
                grow = nums[3] if len(nums) > 3 else 0.0
                p.save()
                p.setClipPath(self.around(rect, path), Qt.ClipOperation.IntersectClip)
                p.fillPath(self.outline(rect.adjusted(-grow, -grow, grow, grow).translated(nums[0], nums[1]), [r + grow if r else 0.0 for r in radii]), tint)
                p.restore()
        fill_ = color(s.get('background-color', 'transparent'), ink)
        if node.kind == 'fill' and fill_.alpha() == 0 and s.get('background-image', 'none').lower() == 'none':
            fill_ = color(s.get('accent-color', '#6c4ab6') if s.get('accent-color', 'auto') != 'auto' else '#6c4ab6', ink)  # a bar's fill takes the bar's accent
        if fill_.alpha(): p.fillPath(path, fill_)
        image = s.get('background-image', 'none')
        if image.lower() != 'none': self.backdrop(p, node, image, rect, border, path)
        widths = border
        if any(widths):
            tints = [color(s.get(f'border-{side}-color', 'currentcolor'), ink) for side in SIDES]
            styles = [s.get(f'border-{side}-style', 'none').lower() for side in SIDES]
            if len(set(widths)) == 1 and len({t.rgba() for t in tints}) == 1 and len(set(styles)) == 1:
                bw = widths[0]
                pen = QPen(tints[0], bw)
                if styles[0] != 'solid': pen.setStyle(Qt.PenStyle.DashLine if styles[0] == 'dashed' else Qt.PenStyle.DotLine)
                pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                p.save(); p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(self.outline(rect.adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2), [max(0.0, r - bw / 2) for r in radii]))
                p.restore()
            else:
                p.save(); p.setClipPath(path, Qt.ClipOperation.IntersectClip)
                x, y, r, b = rect.left(), rect.top(), rect.right(), rect.bottom()
                t_, r_, b_, l_ = widths
                if l_: p.fillRect(QRectF(x, y, l_, rect.height()), tints[3])
                if r_: p.fillRect(QRectF(r - r_, y, r_, rect.height()), tints[1])
                if t_: p.fillRect(QRectF(x, y, rect.width(), t_), tints[0])
                if b_: p.fillRect(QRectF(x, b - b_, rect.width(), b_), tints[2])
                p.restore()

    @staticmethod
    def around(rect, path):
        """Everything but the box itself: a shadow never shows through its own box."""
        outside = QPainterPath()
        outside.addRect(rect.adjusted(-4000, -4000, 4000, 4000))
        return outside.subtracted(path)

    def backdrop(self, p, node, image, rect, border, path):
        s = node.style
        inner = rect.adjusted(border[3], border[0], -border[1], -border[2])
        low = image.lower()
        if low.startswith('linear-gradient('):
            parts = split(image[image.index('(') + 1:image.rindex(')')], ',')
            angle, first = 180.0, parts[0].strip().lower() if parts else ''
            if first.endswith('deg'):
                try: angle, parts = float(first[:-3]), parts[1:]
                except ValueError: pass
            elif first.endswith('turn'): angle, parts = float(first[:-4]) * 360, parts[1:]
            elif first.startswith('to '):
                words = first.split()[1:]
                dx, dy = ('right' in words) - ('left' in words), ('bottom' in words) - ('top' in words)
                angle, parts = math.degrees(math.atan2(dx * inner.width() if dx and dy else dx, -(dy * inner.height() if dx and dy else dy))) % 360, parts[1:]
            rad = math.radians(angle)
            dx, dy = math.sin(rad), -math.cos(rad)
            half = (abs(inner.width() * dx) + abs(inner.height() * dy)) / 2
            c = inner.center()
            g = QLinearGradient(c.x() - dx * half, c.y() - dy * half, c.x() + dx * half, c.y() + dy * half)
            stops = []
            for part in parts:
                tokens = split(part)
                at = length(tokens[-1]) if len(tokens) > 1 else None
                stops.append([color(tokens[0], color(node.get('color'))), None if at is None else (at[1] / 100 if at[1] else at[0] / (2 * half or 1))])
            if stops:
                if stops[0][1] is None: stops[0][1] = 0.0
                if stops[-1][1] is None: stops[-1][1] = 1.0
                for n, stop in enumerate(stops):  # stops without a place spread evenly between their neighbours
                    if stop[1] is None:
                        j = next(k for k in range(n, len(stops)) if stops[k][1] is not None)
                        stop[1] = stops[n - 1][1] + (stops[j][1] - stops[n - 1][1]) / (j - n + 1)
                    stop[1] = max(stop[1], stops[n - 1][1]) if n else stop[1]
                    g.setColorAt(max(0.0, min(1.0, stop[1])), stop[0])
                p.fillPath(path, QBrush(g))
            return
        m = re.match(r'url\("([^"]*)"\)', image)
        picture = self.file(m[1]) if m else None
        if picture is None: return
        size = s.get('background-size', 'auto').strip().lower()
        iw, ih = float(picture.width()), float(picture.height())
        if size in ('cover', 'contain'):
            k = (max if size == 'cover' else min)(inner.width() / iw, inner.height() / ih)
            tw, th = iw * k, ih * k
        else:
            parts = split(size) + ['auto']
            a, b = (resolve(length(parts[0], float(s['font-size'][:-2]), self.vw, self.vh), inner.width()),
                    resolve(length(parts[1], float(s['font-size'][:-2]), self.vw, self.vh), inner.height()))
            tw, th = (a if a is not None else iw * b / ih if b is not None else iw), (b if b is not None else ih * a / iw if a is not None else ih)
        if tw <= 0 or th <= 0: return
        words = split(s.get('background-position', '0% 0%').lower())
        if len(words) == 1: words.append('center')
        if words[0] in ('top', 'bottom') or words[1] in ('left', 'right'): words = words[::-1]
        def offset(word, room):
            if word in ('left', 'top'): return 0.0
            if word in ('right', 'bottom'): return room
            if word == 'center': return room / 2
            v = length(word, float(s['font-size'][:-2]), self.vw, self.vh)
            return 0.0 if v is None else v[0] + v[1] * room / 100
        ox, oy = inner.left() + offset(words[0], inner.width() - tw), inner.top() + offset(words[1], inner.height() - th)
        repeat = s.get('background-repeat', 'repeat').lower()
        rx, ry = repeat in ('repeat', 'repeat-x'), repeat in ('repeat', 'repeat-y')
        p.save()
        p.setClipPath(path, Qt.ClipOperation.IntersectClip)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, s.get('image-rendering', 'auto') not in ('pixelated', 'crisp-edges'))
        x0 = ox - math.ceil((ox - rect.left()) / tw) * tw if rx else ox
        y0 = oy - math.ceil((oy - rect.top()) / th) * th if ry else oy
        yy = y0
        while yy < rect.bottom():
            xx = x0
            while xx < rect.right():
                p.drawImage(QRectF(xx, yy, tw, th), picture)
                if not rx: break
                xx += tw
            if not ry: break
            yy += th
        p.restore()

    def write(self, p, node, x, y, w, h):
        s = node.style
        f, fm = self.font(node)
        rows, wide, lh = self.lines(node, w if s.get('white-space', 'normal') not in ('nowrap', 'pre') else None)
        if s.get('white-space', 'normal') in ('nowrap', 'pre') and s.get('text-overflow', 'clip') == 'ellipsis' and wide > w + 0.5:
            rows = [fm.elidedText(rows[0], Qt.TextElideMode.ElideRight, w)]
        elif s.get('line-clamp', 'none').isdigit() and rows and fm.horizontalAdvance(rows[-1]) > w + 0.5: rows = rows[:-1] + [fm.elidedText(rows[-1], Qt.TextElideMode.ElideRight, w)]
        over = wide > w + 0.5 or len(rows) * lh > h + 0.5
        if over:  # as Compose does: text larger than its box is cut at the box
            p.save(); p.setClipRect(QRectF(x, y, w, h), Qt.ClipOperation.IntersectClip)
        side = s.get('text-align', 'start').lower()
        p.setFont(f)
        shadow = s.get('text-shadow', 'none')
        passes = [(0.0, 0.0, color(node.get('color')))]
        if shadow.lower() != 'none':
            parts = split(split(shadow, ',')[0])
            sizes = [length(t, float(s['font-size'][:-2]), self.vw, self.vh) for t in parts]
            nums = [v[0] for v in sizes if v is not None]
            tint = next((color(t, passes[0][2]) for t, v in zip(parts, sizes) if v is None), passes[0][2])
            if len(nums) >= 2: passes.insert(0, (nums[0], nums[1], tint))
        for dx, dy, tint in passes:
            p.setPen(tint)
            for n, row in enumerate(rows):
                free = w - fm.horizontalAdvance(row)
                off = free / 2 if side == 'center' else free if side in ('right', 'end') else 0.0
                p.drawText(QPointF(x + off + dx, y + dy + n * lh + (lh - fm.ascent() - fm.descent()) / 2 + fm.ascent()), row)
        if over: p.restore()

    def show_image(self, p, node, rect):
        image, fit = node.image, node.get('object-fit').lower()
        iw, ih = float(image.width()), float(image.height())
        if not iw or not ih or rect.width() <= 0 or rect.height() <= 0: return
        if fit == 'fill': target = rect
        else:
            k = max(rect.width() / iw, rect.height() / ih) if fit == 'cover' else 1.0 if fit == 'none' else min(rect.width() / iw, rect.height() / ih)
            if fit == 'scale-down': k = min(1.0, k)
            target = QRectF(rect.center().x() - iw * k / 2, rect.center().y() - ih * k / 2, iw * k, ih * k)
        p.save()
        if fit in ('cover', 'none'): p.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, node.style.get('image-rendering', 'auto') not in ('pixelated', 'crisp-edges'))
        p.drawImage(target, image)
        p.restore()
