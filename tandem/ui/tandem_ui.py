#!/usr/bin/env python3
"""Toravo Tandem – native front end, one process per screen:  tandem_ui.py --screen top|bottom [--url http://127.0.0.1:8377]

Replaces the two Firefox kiosk windows (index.html) to save memory. It is a plain QRasterWindow painted with QPainter:
no QtWidgets, no QML engine, no GPU context. Behaviour and look follow index.html (sizes there are in cqw = 1 % of the
screen width; here that unit is `u`). The service (tandem.py) is the back end, reached over HTTP and Server-Sent Events;
it also reads the controller and sends its buttons as 'key' events.
"""
import argparse, colorsys, ctypes, gc, importlib, json, math, os, random, signal, socket, sys, threading, time, traceback
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

if 'MALLOC_ARENA_MAX' not in os.environ and sys.platform == 'linux':
    # glibc otherwise keeps the freed buffers of every decoded picture, per thread: about 20 MB more per window (measured
    # on the Thor: 73 MB without, 53 MB with). The settings only count at program start, hence the restart in place.
    os.environ.update(MALLOC_ARENA_MAX='1', MALLOC_MMAP_THRESHOLD_='65536', MALLOC_TRIM_THRESHOLD_='131072')
    os.execv(sys.executable, [sys.executable, *sys.argv])
os.environ.pop('QT_QPA_PLATFORMTHEME', None)  # the KDE theme plug-in would pull in the Plasma libraries for nothing
os.environ['XDG_CURRENT_DESKTOP'] = ''
from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, QSize, Qt, QTimer, Signal  # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QImage, QImageReader,  # noqa: E402
                           QLinearGradient, QPainter, QPen, QRasterWindow)
try: from PySide6.QtSvg import QSvgRenderer  # icons only; without it tiles show initials
except ImportError: QSvgRenderer = None

INK, PANEL, RAISED, LINE, TEXT, MUTED, FOCUS, LIVE, WARN = (QColor(c) for c in ('#0a0c13', '#141824', '#1e2434', '#2c3449', '#eef0f6', '#8d94aa', '#ffb23e', '#39d0b8', '#ff7a66'))
ON_ART = QColor('#eef0f6')  # text on covers and on their dark shade: light in every theme
FAMILIES = {'d': ['Barlow Condensed', 'Nimbus Sans Narrow'], 'b': ['Barlow', 'Noto Sans'], 'm': ['Hack', 'Liberation Mono'],  # display, body, monospace
            'n': ['Arial Narrow', 'Nimbus Sans Narrow', 'Barlow Condensed'], 's': ['Georgia', 'Noto Serif', 'C059', 'Nimbus Roman']}  # for decks: narrow, serif
TABS, COLS = ['Start', 'Systeme', 'Steam', 'Apps', 'System'], 5
RA = [('save', 'Speichern'), ('load', 'Laden'), ('slot-', 'Slot −'), ('slot+', 'Slot +'), ('ff', 'Vorspulen'), ('pause', 'Pause'), ('menu', 'Menü'), ('shot', 'Foto')]
ICONS = {'term': '<path d="M4 5h16v14H4z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M7 9l3 3-3 3M12 15h5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
         'web': '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4 12h16M12 4c3 3 3 13 0 16M12 4c-3 3-3 13 0 16" fill="none" stroke="currentColor" stroke-width="1.6"/>',
         'get': '<path d="M12 4v10m0 0l-4-4m4 4l4-4M5 19h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
         'scan': '<path d="M19 12a7 7 0 1 1-2-5M19 5v4h-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
         'play': '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 8.5l6 3.5-6 3.5z" fill="currentColor"/>',
         'pad': '<path d="M6 8h12a4 4 0 0 1 4 4v1a3 3 0 0 1-5.5 1.7L15 13H9l-1.5 1.7A3 3 0 0 1 2 13v-1a4 4 0 0 1 4-4z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M7 10v3M5.5 11.5h3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
         'desk': '<path d="M4 5h16v11H4zM9 20h6M12 16v4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
         'vol0': '<path d="M3 9v6h4l5 4V5L7 9z" fill="currentColor"/>'}
ICONS['vol1'] = ICONS['vol0'] + '<path d="M15 9a4 4 0 0 1 0 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
ICONS['vol2'] = ICONS['vol1'] + '<path d="M17.5 6.5a8 8 0 0 1 0 11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
# On-screen keyboard: physical keys (evdev codes) in ISO order; the labels follow the layout the service set, the
# system's keymap does the actual translation.
KB_CODES = [[41, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14], [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27], [58, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 43, 28],
            [42, 86, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 103], [29, 56, 57, 100, 1, 105, 108, 106]]
KB_ROWS = [[41, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27], [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 43], [44, 45, 46, 47, 48, 49, 50, 51, 52, 53]]
KB_NAME = {14: '⌫', 15: 'Tab', 28: '↵', 42: '⇧', 58: '⇪', 29: 'Strg', 56: 'Alt', 57: ' ', 100: 'AltGr', 1: 'Esc', 103: '↑', 105: '←', 108: '↓', 106: '→'}
KB = {'us': ['`1234567890-=', 'qwertyuiop[]', "asdfghjkl;'\\", 'zxcvbnm,./', '~!@#$%^&*()_+', 'QWERTYUIOP{}', 'ASDFGHJKL:"|', 'ZXCVBNM<>?'],
      'de': ['^1234567890ß´', 'qwertzuiopü+', 'asdfghjklöä#', 'yxcvbnm,.-', '°!"§$%&/()=?`', 'QWERTZUIOPÜ*', "ASDFGHJKLÖÄ'", 'YXCVBNM;:_']}
KB_ALTGR = {'de': {16: '@', 18: '€', 8: '{', 9: '[', 10: ']', 11: '}', 12: '\\', 27: '~', 86: '|'}}
KB_MODS = {42: 'shift', 29: 'ctrl', 56: 'alt', 100: 'altgr'}

# ---- HOOK: native per-game decks -------------------------------------------------------------------------------------
# A game can bring its own bottom screen while it runs (the Firefox front end shows decks/<appid>.html for that). Natively
# a deck is a module in ui/decks, named here by Steam appid. It is loaded when its game starts and dropped, with its
# pictures, when the game ends. The module provides
#     class Deck:
#         def __init__(self, window)   # start whatever feeds it (its own thread; window.loaded.emit() asks for a repaint)
#         def paint(self, painter)     # paint the whole bottom screen, return True (False: show the normal in-game panel)
#         def close(self)              # stop threads, let go of pictures
# and may use the window's helpers: hit(), scroller(), text(), box(), font(), width_of(), Images, http(), memo (a dict
# that outlives the deck) and, for a scaled stage, window.xf / window.zoom (see hit()). Optional: press(pos or None) hears
# a finger go down and up, ingame() paints the normal in-game panel below a deck's own tabs.
# An emulated game with a companion pack (run['pack'], see find_pack in tandem.py) gets the deck 'pack'.
DECKS = {'377840': 'ffix', '377160': 'pipboy'}  # Final Fantasy IX, Fallout 4
POWER = {'suspend': ('In den Standby gehen?', 'Standby'), 'reboot': ('Thor neu starten?', 'Neu starten'), 'poweroff': ('Thor ausschalten?', 'Ausschalten'),
         'desktop': ('Zum Desktop wechseln?', 'Desktop')}

ADDR = ('127.0.0.1', 8377)


def http(path, data=None, timeout=300, addr=None):
    """One request to the Tandem service; returns the open reply stream (body follows). Local plain HTTP only, so a
    socket is enough and urllib (with ssl and email) stays out of memory."""
    body = json.dumps(data).encode() if data is not None else b''
    sock = socket.create_connection(addr or ADDR, timeout=timeout)
    sock.sendall(f'{"POST" if data is not None else "GET"} /{path} HTTP/1.1\r\nHost: {ADDR[0]}:{ADDR[1]}\r\nContent-Type: application/json\r\n'
                 f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode() + body)
    stream = sock.makefile('rb')
    sock.close()  # the stream keeps the connection
    if b' 200 ' not in stream.readline(): raise OSError(f'{path}: kein 200')
    while stream.readline().strip(): pass
    return stream


def fetch(path, data=None, addr=None):
    with http(path, data, addr=addr) as stream: return stream.read()


def jhash(text):  # same numbers as hash() in index.html, so tiles keep their colours
    h = 7
    for c in text: h = (h * 31 + ord(c)) & 0xffffffff
    return h


def hours(secs): return f'{round(secs / 360) / 10:g} Std.' if secs >= 3600 else f'{max(1, round(secs / 60))} Min.'


def ago(t):
    days = int((time.time() - t) // 86400)
    return 'heute' if days < 1 else 'gestern' if days == 1 else f'vor {days} Tagen'


def clock(): return time.strftime('%H:%M')


def rgba(r, g, b, a): return QColor(r, g, b, round(a * 255))


def faded(color, a): return QColor(color.red(), color.green(), color.blue(), round(a * 255))


# ---- themes -----------------------------------------------------------------------------------------------------------
# A theme is one JSON file (format: README). The shipped ones lie in ui/themes, the user's own in ~/.config/tandem/themes
# (same file name: the user's wins). The built-in values below are the Toravo look; a theme only says what differs.
THEME_DIRS = [Path(__file__).resolve().parent / 'themes', Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'tandem/themes']
DEFAULT_THEME = {'id': 'toravo', 'name': 'Toravo', 'radius': 1.0, 'glow': 1.0, 'gradient': None, 'background': None, 'gameAccent': True,
                 'colors': {'bg': '#0a0c13', 'panel': '#141824', 'raised': '#1e2434', 'line': '#2c3449', 'text': '#eef0f6', 'muted': '#8d94aa', 'accent': '#ffb23e', 'live': '#39d0b8', 'warn': '#ff7a66'},
                 'fonts': {'display': ['Barlow Condensed', 'Nimbus Sans Narrow'], 'body': ['Barlow', 'Noto Sans']}}
THEME = dict(DEFAULT_THEME)  # the active one, complete


def is_color(value): return isinstance(value, str) and len(value) == 7 and value[0] == '#' and all(c in '0123456789abcdefABCDEF' for c in value[1:])


def read_theme(name):
    """The theme of that name, complete: whatever the file does not say, or says wrongly, keeps the built-in value.
    A missing or broken file gives the built-in look."""
    theme = {**DEFAULT_THEME, 'colors': dict(DEFAULT_THEME['colors']), 'fonts': dict(DEFAULT_THEME['fonts'])}
    file = next((d / f'{name}.json' for d in reversed(THEME_DIRS) if (d / f'{name}.json').is_file()), None)
    try: data = json.loads(file.read_text()) if file else None
    except (OSError, ValueError): data = None
    if not isinstance(data, dict): return theme
    theme['id'] = str(name)
    if isinstance(data.get('name'), str) and data['name'].strip(): theme['name'] = data['name'].strip()[:40]
    else: theme['name'] = str(name)
    colors, fonts, number = data.get('colors'), data.get('fonts'), lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for key in theme['colors']:
        if isinstance(colors, dict) and is_color(colors.get(key)): theme['colors'][key] = colors[key]
    for key in theme['fonts']:
        if isinstance(fonts, dict) and isinstance(fonts.get(key), list) and fonts[key] and all(isinstance(f, str) for f in fonts[key]): theme['fonts'][key] = fonts[key][:6]
    if number(data.get('radius')): theme['radius'] = max(0.0, min(3.0, data['radius']))
    if number(data.get('glow')): theme['glow'] = max(0.0, min(1.0, data['glow']))
    if isinstance(data.get('gradient'), list) and 2 <= len(data['gradient']) <= 4 and all(is_color(c) for c in data['gradient']): theme['gradient'] = data['gradient']
    if isinstance(data.get('gameAccent'), bool): theme['gameAccent'] = data['gameAccent']
    if isinstance(data.get('background'), str) and (file.parent / data['background']).is_file(): theme['background'] = str(file.parent / data['background'])
    return theme


def apply_theme(theme):
    """Makes a theme the active one. The colour objects and font lists are changed in place: all drawing code holds them."""
    THEME.clear(); THEME.update(theme)
    for color, key in ((INK, 'bg'), (PANEL, 'panel'), (RAISED, 'raised'), (LINE, 'line'), (TEXT, 'text'), (MUTED, 'muted'), (FOCUS, 'accent'), (LIVE, 'live'), (WARN, 'warn')):
        color.setRgba(QColor(theme['colors'][key]).rgba())
    FAMILIES['d'][:], FAMILIES['b'][:] = theme['fonts']['display'], theme['fonts']['body']


# ---- a game's own accent colour (from its cover) -------------------------------------------------------------------------
def luminance(rgb):
    lin = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in (v / 255 for v in rgb)]
    return .2126 * lin[0] + .7152 * lin[1] + .0722 * lin[2]


def contrast(a, b):
    """Contrast ratio of two colours as WCAG defines it (1 … 21)."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + .05) / (lo + .05)


def dominant(pixels):
    """The strongest colour of a picture given as (r, g, b) pixels: the hue that carries most colourful area, made
    saturated. None if the picture is grey, dark or pale all over."""
    buckets = {}
    for r, g, b in pixels:
        h, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if sat < .3 or val < .25: continue
        weight, bucket = sat * val, buckets.setdefault(int(h * 12) % 12, [0.0, 0.0, 0.0, 0.0])
        bucket[0] += weight; bucket[1] += r * weight; bucket[2] += g * weight; bucket[3] += b * weight
    if not buckets: return None
    weight, r, g, b = max(buckets.values())
    if weight < .03 * len(pixels): return None  # a few coloured specks do not make a colour
    h, sat, val = colorsys.rgb_to_hsv(r / weight / 255, g / weight / 255, b / weight / 255)
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, max(sat, .6), max(val, .75)))


def readable(rgb, background, ratio=4.5):
    """The colour, made lighter (on a dark background) or darker (on a light one) until it stands out enough to be
    read as text there."""
    h, light, sat = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    step = .03 if luminance(background) < .18 else -.03
    for _ in range(34):
        rgb = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, light, sat))
        if contrast(rgb, background) >= ratio or not 0 < light < 1: break
        light = max(0.0, min(1.0, light + step))
    return rgb


ACCENT_FILE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'tandem/accents.json'
ACCENTS = {}  # cover -> '#rrggbb' as found in the picture ('' = none); kept on disk, each cover is looked at once


def load_accents():
    try: ACCENTS.update({k: v for k, v in json.loads(ACCENT_FILE.read_text()).items() if v == '' or is_color(v)})
    except (OSError, ValueError, AttributeError): pass


def save_accents():
    try:
        load_accents()  # the other screen's window writes the same file
        ACCENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = ACCENT_FILE.with_suffix(f'.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(ACCENTS))
        os.replace(tmp, ACCENT_FILE)
    except OSError: pass


def load_image(path, w, h, cover=True, addr=None):
    """Decode straight to the size on screen: the full-size picture never sits in memory. cover fills w x h (centred,
    cropped), otherwise the picture fits inside; w = 0 keeps its own size."""
    buf = QBuffer(); buf.setData(QByteArray(fetch(path, addr=addr))); buf.open(QBuffer.OpenModeFlag.ReadOnly)
    kind = path.rsplit('.', 1)[-1].lower().replace('jpeg', 'jpg').encode()
    reader = QImageReader(buf, kind)  # naming the format keeps Qt from loading every image plug-in (HEIF, RAW, EXR …) to probe
    if not reader.canRead(): buf.seek(0); reader = QImageReader(buf)  # wrong file ending: let Qt find out
    size = reader.size()
    if w and size.isValid() and size.width() and size.height():
        k = (max if cover else min)(w / size.width(), h / size.height())
        reader.setScaledSize(QSize(max(w if cover else 1, round(size.width() * k)), max(h if cover else 1, round(size.height() * k))))
    img = reader.read()
    if img.isNull(): return False
    if cover and w:
        if img.width() < w or img.height() < h or not size.isValid():
            img = img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        img = img.copy((img.width() - w) // 2, (img.height() - h) // 2, w, h)
    return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class Images:
    """Pictures from a local service, loaded lazily in the background and kept only while recently used."""

    def __init__(self, limit, ready, addr=None, workers=2):
        self.cache, self.todo, self.lock, self.wake, self.limit, self.ready, self.addr = OrderedDict(), [], threading.Lock(), threading.Semaphore(0), limit, ready, addr
        self.failed, self.alive = {}, True
        for _ in range(workers): threading.Thread(target=self.work, daemon=True).start()

    def get(self, path, w=0, h=0, cover=True, retry=0):
        """The picture, None while it loads, False if there is none (asked again after retry seconds, if given)."""
        key = (path, int(w), int(h), cover)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                if self.cache[key] is not False or not retry or time.time() - self.failed.get(key, 0) < retry: return self.cache[key]
            self.cache[key] = None
            self.todo.append(key)
            while len(self.cache) > self.limit: self.cache.popitem(last=False)
        self.wake.release()
        return None

    def close(self):  # the owner is done: end the threads, drop the pictures
        self.alive = False
        with self.lock: self.cache.clear()
        for _ in range(2): self.wake.release()

    def work(self):
        while True:
            self.wake.acquire()
            if not self.alive: return
            with self.lock:
                key = self.todo.pop()  # newest request first: that is what is on screen now
                if key not in self.cache: continue
            try: img = load_image(*key, addr=self.addr)
            except Exception: img = False
            with self.lock:
                if key in self.cache: self.cache[key] = img
                if img is False: self.failed[key] = time.time()
            if self.alive: self.ready.emit()


class Tandem(QRasterWindow):
    event = Signal(object)  # a message from the service's event stream
    result = Signal(object, object)  # (callback, reply) from a request thread
    loaded = Signal()  # a picture arrived (or a deck has news): repaint
    Images, http = Images, staticmethod(http)  # for deck modules
    memo = {}  # what decks want to remember between games (chosen tab …)

    def __init__(self, screen):
        super().__init__()
        self.side, self.me = screen, f'{screen}-{random.getrandbits(32):x}'
        self.setTitle('Toravo Tandem')
        self.L = {'systems': {}, 'games': [], 'apps': [], 'fav': [], 'played': {}}
        self.S, self.RUN, self.BATT, self.SET, self.CFG = {'tab': 0, 'sys': None, 'i': 0}, None, None, {'bt': None, 'bb': None, 'vol': None}, {}
        self.ACH = self.PAIR = self.SYS = self.PROMPT = self.CONFIRM = self.OSD = self.SETUP = None
        self.TOAST, self.SUB, self.KM, self.asked = '', '', set(), False
        self.hits, self.scrolls, self.clip, self.off, self.maxoff, self.seen = [], [], None, {}, {}, None
        self.press = self.drag = self.scrolling = self.pending = self.deck = self.xf = None
        self.zoom = 1.0
        self.moved = False
        self.fonts, self.svgs, self.u = {}, {}, 1.0
        self.images = Images(2 if screen == 'top' else 60, self.loaded)  # top: full-screen art; bottom: tiles
        self.thumbs = Images(6, self.loaded, workers=1)  # covers at 24 pixels, to find a game's colour
        self.backdrop = None
        load_accents()
        self.active = time.time()  # last input, for resting()
        self.event.connect(self.on_event)
        self.result.connect(lambda then, reply: (then(reply), self.update()))
        self.loaded.connect(self.update)
        self.timers = {name: QTimer(self, singleShot=True) for name in ('toast', 'osd', 'set')}
        self.timers['toast'].timeout.connect(lambda: self.toast(''))
        self.timers['osd'].timeout.connect(lambda: (setattr(self, 'OSD', None), self.update()))
        self.tick = QTimer(self, interval=30000)
        self.tick.timeout.connect(self.pulse)
        self.tick.start()
        self.timers['set'].timeout.connect(lambda: self.post('api/set', self.pending))  # at most one change per 60 ms while a slider moves
        self.pulse()
        threading.Thread(target=self.listen, daemon=True).start()

    # ---- service -----------------------------------------------------------------------------------------------------
    def call(self, path, data=None, then=None):
        def work():
            try: reply = json.loads(fetch(path, data))
            except (OSError, ValueError): reply = None
            if then: self.result.emit(then, reply)
        threading.Thread(target=work, daemon=True).start()

    def post(self, path, data=None, then=None): self.call(path, data or {}, then)

    def listen(self):
        while True:
            try:
                with http('api/events', timeout=60) as stream:  # the service pings every 20 s
                    self.event.emit({'kind': 'library'})  # (re)connected: the library may be new
                    for line in stream:
                        if line.startswith(b'data: '): self.event.emit(json.loads(line[6:]))
            except (OSError, ValueError): pass
            time.sleep(1)

    def load(self):
        def got(library):
            if library: self.L = library
        self.call('api/library', then=got)

    def pulse(self):
        def got(s):
            if not s: return
            self.BATT, self.PAIR, self.CFG = s.get('battery'), s.get('pair'), s.get('config') or self.CFG
            self.follow_setup(s.get('setup'))
            self.follow_theme()
            if not self.drag: self.SET = s.get('settings') or self.SET
        self.call('api/state', then=got)
        self.update()  # the clock

    def load_sys(self, scan=False): self.call('api/system' + ('?scan' if scan else ''), then=lambda s: s and setattr(self, 'SYS', s))

    def load_ach(self):
        if self.side != 'bottom': return  # only the bottom screen shows achievements
        def got(a):
            if self.RUN: self.ACH = a or {'note': 'Erfolge konnten nicht geladen werden.'}
        self.call('api/achievements', then=got)

    # ---- first-run assistant: the service holds its state ({'open', 'step'}) and what it found (api/setup) ----------------
    def follow_setup(self, state):
        if not state or not state.get('open'): self.SETUP = None
        elif self.SETUP: self.SETUP['step'] = state['step']
        else:
            self.SETUP = {'step': state['step']}  # the findings follow
            self.call('api/setup', then=lambda r: r and self.SETUP is not None and self.SETUP.update({**r, 'step': self.SETUP['step']}))

    def setup_pages(self):
        s = self.SETUP
        if 'folders' not in s: return [('Einen Moment …', [])] * 4
        games = [f'{f["root"]}: ' + (', '.join(f'{x["name"]} {x["n"]}' for x in f['systems']) or 'keine Spiele') for f in s['folders']] or ['Kein Spieleordner gefunden. Spiele gehören in einen Ordner „ROMs“ auf der Karte oder im Gerät.']
        missing = [f'{m["name"]} ({m["n"]} Spiele) braucht {m["emu"] or "einen Emulator"}.' for m in s['missing']]
        emus = missing + ['Tandem kann das Fehlende jetzt installieren.' if s['install'] or all(m['extra'] for m in s['missing']) else 'Bitte im Desktop-Modus im Armada Store installieren.'] if missing else ['Für alle gefundenen Spiele ist ein Emulator da.']
        net = ['WLAN: ' + (s['wifi'] or 'nicht verbunden'), 'Erfolge (RetroAchievements): ' + ((s['ra_user'] + (' · angemeldet' if s['ra_login'] else '')) if s['ra_user'] else 'kein Konto'),
               'Ändern kannst du beides jederzeit unter „System“ – oder bequem vom Handy über die dort gezeigte Adresse.']
        return [('Willkommen bei Tandem', ['Oben läuft dein Spiel, unten liegt die Bedienung.', 'Vier kurze Schritte zeigen, was Tandem auf diesem Gerät gefunden hat.', 'A oder „Weiter“ geht voran, B zurück.']),
                ('Deine Spiele', games), ('Emulatoren', emus), ('Netz und Konto', net)]

    def setup_go(self, a):
        step = self.SETUP['step']
        if a == 'install': return self.post('api/setup', {'install': True}, then=lambda r: r and self.toast(r.get('error') or r.get('text', '')))
        self.post('api/setup', {'done': True} if a == 'ok' and step >= 3 else {'step': min(3, step + 1) if a == 'ok' else max(0, step - 1)})

    def draw_setup(self, p):
        u, W, H, step = self.u, self.width(), self.height(), min(3, self.SETUP['step'])
        title, rows = self.setup_pages()[step]
        x0, cw = 5 * u, W - 10 * u
        y = 5 * u + self.text(p, f'EINRICHTUNG · SCHRITT {step + 1} VON 4', x0, 5 * u, ('d', 2.2, 700, .08), FOCUS) + 1.5 * u
        y += self.text(p, title.upper(), x0, y, ('d', 5 if self.side == 'top' else 4.4, 700), TEXT, cw, lh=1.1, lines=None) + 2 * u
        if self.side == 'top':
            for row in rows: y += self.text(p, row, x0, y, ('b', 2.6), MUTED, cw, lh=1.4, lines=None) + 1.2 * u
            return
        can = step == 2 and any(m['store'] or m['extra'] for m in self.SETUP.get('missing', ()))
        names = ([('Zurück', 'back')] if step else []) + ([('Installieren', 'install')] if can else []) + [('Fertig' if step == 3 else 'Weiter', 'ok')]
        w = (cw - 1.4 * u * (len(names) - 1)) / len(names)
        for n, (label, a) in enumerate(names):
            last = a == 'ok'
            self.button(p, QRectF(x0 + n * (w + 1.4 * u), H - 2.6 * u - 6.3 * u, w, 6.3 * u), label.upper(), lambda a=a: self.setup_go(a), ('d', 2.6, 700, .06), INK if last else MUTED, FOCUS if last else PANEL, FOCUS if last else LINE, 1.4)

    def resting(self):
        """OLED care: black screen with a wandering clock once nobody has touched Tandem for the configured minutes."""
        # shortcut: never rests while a game runs (the pad then talks to the game, not to us), add when the bottom deck burns in
        minutes = self.CFG.get('rest_min', 3)
        return bool(minutes) and not self.RUN and time.time() - self.active > minutes * 60

    def wake(self):  # True: this input only woke the screen up
        was, self.active = self.resting(), time.time()
        return was

    def on_event(self, m):
        kind = m.get('kind')
        if kind not in ('library', 'config') and self.wake(): return self.update()
        if kind == 'toast': return self.toast(m.get('text', ''))
        if kind == 'library': return self.load()
        if kind == 'key':
            if m['a'] == 'home': self.SUB, self.PROMPT = '', None
            if self.side == 'top':  # one window acts on the controller, the other follows through the service
                if m['a'] == 'home': self.S = {'tab': 0, 'sys': None, 'i': 0}; self.push()
                else: self.go(m['a'])
            return self.update()
        if kind == 'confirm':
            if m.get('from') != self.me:
                if m.get('open') and m.get('action') in POWER: self.confirm_action(m['action'], remote=True)
                elif m.get('open') and self.RUN: self.confirm_quit(next((g for g in self.L['games'] if g['id'] == m.get('then')), None), remote=True)
                else: self.CONFIRM = None
            return self.update()
        if kind == 'config':
            self.CFG = m['config']
            self.follow_theme()
            return self.pulse()
        if kind == 'settings':
            if m.get('from') != self.me and not self.drag: self.SET = m['settings']
            if m.get('osd'):
                self.OSD = m['settings'].get(m['osd'])
                self.timers['osd'].start(1600)
            return self.update()
        was, self.RUN = self.RUN, m.get('run')
        self.follow_setup(m.get('setup'))
        if m.get('from') != self.me: self.S = dict(m['ui'])
        if self.RUN and (not was or was['id'] != self.RUN['id']): self.ACH = None; self.load_ach()
        if not self.RUN: self.ACH = None
        if self.deck is not None and (not self.RUN or not was or was['id'] != self.RUN['id']): self.drop_deck()
        if was and not self.RUN: self.load()  # play time and "last played" changed
        self.update()

    def follow_theme(self):  # the config names the look: take it over when it is another one (or its file changed name)
        if (self.CFG.get('theme') or 'toravo') != THEME['id']: self.set_theme(self.CFG.get('theme') or 'toravo')

    def set_theme(self, name):
        apply_theme(read_theme(name))
        self.fonts, self.svgs, self.backdrop = {}, {}, None
        self.update()

    def next_theme(self):
        looks = [t['id'] for t in self.CFG.get('themes') or []]
        if not looks: return
        name = looks[(looks.index(THEME['id']) + 1) % len(looks)] if THEME['id'] in looks else looks[0]
        self.set_theme(name)
        self.post('api/config', {'theme': name})  # the service stores it and tells the other screen

    def game_accent(self, items):
        """The colour of the game in front (running, else selected), from its cover; None for the theme's own accent."""
        if not THEME['gameAccent']: return None
        it = next((g for g in self.L['games'] if g['id'] == self.RUN['id']), None) if self.playing() else items[self.S['i']] if items else None
        if not it or it.get('kind') or it.get('s') == 'app' or not it.get('cover'): return None
        key = it['cover']
        if key not in ACCENTS:
            img = self.thumbs.get(key, 24, 24)  # decoded straight to 24 x 24, never at full size
            if img is None: return None  # still loading; the repaint comes with it
            found = dominant([((px >> 16) & 255, (px >> 8) & 255, px & 255) for px in (img.pixel(x, y) for x in range(img.width()) for y in range(img.height()))]) if img else None
            ACCENTS[key] = '#%02x%02x%02x' % found if found else ''
            save_accents()
        if not ACCENTS[key]: return None
        c, bg = QColor(ACCENTS[key]), QColor(THEME['colors']['bg'])
        return QColor(*readable((c.red(), c.green(), c.blue()), (bg.red(), bg.green(), bg.blue())))

    def accent_fill(self, rect):
        """What bars are filled with: the accent, or the theme's gradient along the bar."""
        if not THEME['gradient']: return FOCUS
        g = QLinearGradient(rect.left(), 0, rect.right(), 0)
        for n, c in enumerate(THEME['gradient']): g.setColorAt(n / (len(THEME['gradient']) - 1), QColor(c))
        return QBrush(g)

    def show_deck(self, p):
        """The running game's own bottom screen, if there is a native one. Loaded on first use, see DECKS."""
        name = DECKS.get(str(self.RUN.get('appid'))) or ('pack' if self.RUN.get('pack') else None)
        if not name or self.deck is False: return False
        if self.deck is None:
            try: self.deck = (importlib.import_module('decks.' + name), name)[0].Deck(self)
            except Exception as error:
                traceback.print_exc()
                self.deck = False  # not again for this game
                self.toast(f'Begleiter lädt nicht: {error}')
                return False
        return self.deck.paint(p)

    def drop_deck(self):  # the game is over: its deck, the module and the pictures go
        if self.deck: self.deck.close()
        self.deck = None
        for name in [n for n in sys.modules if n.startswith('decks.')]: del sys.modules[name]
        gc.collect()  # a deck is full of closures: collect it now …
        try: ctypes.CDLL(None).malloc_trim(0)  # … and hand the freed memory back to the system (glibc would keep it)
        except (OSError, AttributeError): pass

    def confirm_action(self, name, remote=False):  # Standby, restart, power off, desktop: ask first, on both screens
        text, yes = POWER[name]
        if not remote: self.post('api/confirm', {'open': True, 'action': name, 'from': self.me})
        self.CONFIRM = {'text': text, 'yes': yes, 'run': lambda: self.post('api/action', {'name': name}, then=lambda r: r and r.get('error') and self.toast(r['error']))}
        self.update()

    # ---- behaviour (as in index.html) ---------------------------------------------------------------------------------
    def playing(self): return bool(self.RUN and not self.RUN.get('paused'))

    def items(self):
        L, S, RUN, games = self.L, self.S, self.RUN, self.L['games']
        if S['sys']: return [g for g in games if g['s'] == S['sys']]
        if S['tab'] == 0:
            last = lambda g: (L['played'].get(g['id']) or {}).get('last') or 0
            held = next((g for g in games if g['id'] == RUN['id']), None) if RUN and RUN.get('paused') else None  # like the Switch: the suspended game stands in front
            rest = sorted((g for g in games if (last(g) or g['id'] in L['fav']) and g is not held), key=lambda g: (-last(g), g['t']))[:30]
            return ([held] if held else []) + rest
        if S['tab'] == 1: return [{'id': 'sys:' + s, 't': v['name'], 's': s, 'kind': 'sys', 'n': v['n'], 'cover': v.get('cover'), 'hero': v.get('hero')} for s, v in L['systems'].items()]
        if S['tab'] == 2: return sorted((g for g in games if g['s'] == 'steam'), key=lambda g: (g.get('inst') == 'no', g.get('inst') != 'load'))  # loading first, then installed, then the rest
        if S['tab'] == 4: return []
        return [{'id': 'term', 't': 'Terminal', 's': 'app'}, *L['apps'],
                *({'id': 'upd:' + e['id'], 't': e['name'] + (' aktualisieren' if e.get('installed') else ' installieren'), 's': 'app'} for e in L.get('extras') or []),
                {'id': 'act:steam', 't': 'Steam starten', 's': 'app'}, {'id': 'rescan', 't': 'Bibliothek neu einlesen', 's': 'app'}, {'id': 'act:desktop', 't': 'Zum Desktop', 's': 'app'}]

    def sys_name(self, it):
        s = it['s']
        return 'Steam' if s == 'steam' else 'App' if s == 'app' else 'Linux-Shell' if s == 'term' else (self.L['systems'].get(s) or {'name': s})['name']

    def toast(self, text):
        self.TOAST = text
        if text: self.timers['toast'].start(6000)
        self.update()

    def push(self):
        self.update()
        self.post('api/ui', {**self.S, 'from': self.me})

    def unconfirm(self):  # the question shows on both screens: tell the other one
        self.CONFIRM = None
        self.post('api/confirm', {'open': False, 'from': self.me})

    def confirm_quit(self, then=None, remote=False):
        title = self.RUN['t']
        if not remote: self.post('api/confirm', {'open': True, 'then': then['id'] if then else None, 'from': self.me})
        def run():
            def work():  # quit, wait until the game is gone, then start the next one
                try:
                    fetch('api/quit', {})
                    for _ in range(20):
                        if not then or not json.loads(fetch('api/state')).get('run'): break
                        time.sleep(0.3)
                    if then: fetch('api/launch', {'id': then['id']})
                except (OSError, ValueError): pass
            threading.Thread(target=work, daemon=True).start()
        self.CONFIRM = {'text': f'„{title}“ ist noch offen. Beenden und „{then["t"]}“ starten?' if then else f'„{title}“ beenden?',
                        'yes': 'Beenden und starten' if then else 'Beenden', 'run': run}
        self.update()

    def resume(self): self.post('api/resume', then=lambda r: r and r.get('error') and self.toast(r['error']))

    def start(self, it):
        gid, RUN = it['id'], self.RUN
        if gid == 'act:desktop': return self.confirm_action('desktop')  # asks first, on both screens
        if RUN and RUN.get('paused') and it.get('kind') != 'sys':
            if gid == RUN['id']: return self.resume()
            if gid != 'rescan' and gid != 'act:steam' and not gid.startswith('upd:'): return self.confirm_quit(it)
        if gid.startswith('upd:'):
            self.toast('Lade … das kann eine Minute dauern.')
            return self.post('api/update', {'id': gid[4:]})
        if gid == 'act:steam': return self.post('api/action', {'name': 'steam'})
        if gid == 'rescan': return self.post('api/rescan', then=lambda r: r and self.toast(f'{r["games"]} Spiele gefunden' + (f', {r["covers"]} Cover geladen.' if r.get('covers') else '.')))
        self.post('api/launch', {'id': gid}, then=lambda r: r is None and self.toast('Tandem-Dienst antwortet nicht.'))

    def go(self, a):
        items, S = self.items(), self.S
        n = len(items)
        S['i'] = max(0, min(S['i'], n - 1))
        it = items[S['i']] if n else None
        if self.SETUP and not self.RUN:
            if a in ('ok', 'back'): self.setup_go(a)
            return
        if self.CONFIRM:
            c = self.CONFIRM
            if a == 'ok': self.unconfirm(); c['run']()
            elif a == 'back': self.unconfirm()
            return self.update()
        if self.playing():
            if a == 'back' and self.RUN['s'] != 'term': self.toast('Zum Beenden unten „Spiel beenden“ tippen.')
            return
        if a == 'ok' and S['tab'] == 4 and not S['sys']: return self.next_theme()  # the System tab's one controller action
        if a == 'left': S['i'] = max(0, S['i'] - 1)
        elif a == 'right': S['i'] = min(n - 1, S['i'] + 1)
        elif a == 'up': S['i'] -= COLS if S['i'] >= COLS else 0
        elif a == 'down': S['i'] += COLS if S['i'] + COLS < n else 0
        elif a in ('prev', 'next'): S.update(sys=None, tab=(S['tab'] + (1 if a == 'next' else len(TABS) - 1)) % len(TABS), i=0)
        elif a == 'ok':
            if not it: return
            if it.get('kind') == 'sys': S.update(sys=it['s'], i=0)
            else: return self.start(it)
        elif a == 'close':
            if self.RUN and self.RUN.get('paused'): self.confirm_quit()
            return
        elif a == 'fav':
            if not it or it.get('kind') or it['s'] == 'app': return
            self.post('api/fav', {'id': it['id']})
        elif a == 'back' and S['sys']: S.update(i=list(self.L['systems']).index(S['sys']) if S['sys'] in self.L['systems'] else 0, sys=None, tab=1)
        self.push()

    def ask(self, title, secret, done):  # text entry without a real keyboard: the key grid fills a field on this screen
        self.PROMPT, self.KM = {'title': title, 'secret': secret, 'done': done, 'value': ''}, set()

    def key_label(self, code, layout):
        if code in KB_NAME: return KB_NAME[code]
        if code == 86: return ('|' if 'altgr' in self.KM else '>' if 'shift' in self.KM else '<') if layout == 'de' else '\\'
        if 'altgr' in self.KM and code in KB_ALTGR.get(layout, {}): return KB_ALTGR[layout][code]
        for r, row in enumerate(KB_ROWS):
            if code in row: return KB[layout][r + (4 if 'shift' in self.KM else 0)][row.index(code)]
        return ''

    def prompt_key(self, code):
        P = self.PROMPT
        if code in (42, 100): self.KM ^= {KB_MODS[code]}
        elif code == 14: P['value'] = P['value'][:-1]
        elif code == 28: self.PROMPT = None; P['done'](P['value'])
        else:
            P['value'] += ' ' if code == 57 else self.key_label(code, 'us' if self.CFG.get('kb_layout') == 'us' else 'de')
            self.KM -= {'shift', 'altgr'}

    def term_key(self, code):
        if code in KB_MODS: self.KM ^= {KB_MODS[code]}; return
        self.post('api/key', {'code': code, 'mods': sorted(self.KM)}, then=lambda r: r and r.get('error') and self.toast(r['error']))
        self.KM = set()

    def set_value(self, key, x, left, width):
        low = 0 if key == 'vol' else 5
        value = round(low + max(0.0, min(1.0, (x - left) / width)) * (100 - low))
        if value != self.SET[key]:
            self.SET[key] = value
            self.pending = {'key': key, 'value': value, 'from': self.me}
            if not self.timers['set'].isActive(): self.timers['set'].start(60)
            self.update()

    def ask_account(self, key):
        def done(value):
            if not value: return
            def saved(c):
                if c is None: return self.toast('Speichern fehlgeschlagen.')
                self.CFG = c
                self.toast(c.get('error') or ('Angemeldet und eingetragen in: ' + ', '.join(c['applied']) if c.get('applied') else 'Gespeichert.'))
            self.post('api/config', {key: value}, then=saved)
        self.ask({'ra_user': 'Benutzername bei RetroAchievements', 'ra_password': 'Passwort bei RetroAchievements', 'ra_key': 'Web-API-Schlüssel'}[key], key != 'ra_user', done)

    def wifi(self, net):
        def connect(password=''):
            self.toast(f'Verbinde mit {net["ssid"]} …')
            def done(r):
                self.toast('Verbinden fehlgeschlagen.' if r is None else r.get('error') or f'Verbunden mit {net["ssid"]}.')
                self.SUB = ''
                self.load_sys()
            self.post('api/wifi', {'ssid': net['ssid'], 'password': password}, then=done)
        if net.get('secure') and not net.get('known'): self.ask('Passwort für ' + net['ssid'], True, lambda pw: pw and connect(pw))
        else: connect()

    # ---- input -------------------------------------------------------------------------------------------------------
    def keyPressEvent(self, e):
        if self.wake(): return self.push()  # push: the other screen wakes up too
        if self.playing() and self.RUN['s'] == 'term': return  # keys belong to the terminal
        K = Qt.Key
        a = {K.Key_Left: 'left', K.Key_Right: 'right', K.Key_Up: 'up', K.Key_Down: 'down', K.Key_Return: 'ok', K.Key_Enter: 'ok', K.Key_Escape: 'back',
             K.Key_Q: 'prev', K.Key_E: 'next', K.Key_F: 'fav', K.Key_X: 'close'}.get(e.key())
        if a: self.go(a)

    def mousePressEvent(self, e):
        if self.wake(): return self.push()
        pos = e.position()
        self.press, self.moved, self.last = pos, False, pos.y()
        self.drag = next((fn for rect, fn, drag, _ in reversed(self.hits) if drag and rect.contains(pos)), None)
        self.scrolling = next((entry for entry in self.scrolls if entry[0].contains(pos)), None)
        if self.drag: self.drag(pos.x())
        if self.deck and hasattr(self.deck, 'press'): self.deck.press(pos)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self.press is None: return
        if self.drag: return self.drag(pos.x())
        if self.scrolling and (self.moved or abs(pos.y() - self.press.y()) > 1.5 * self.u):
            self.moved = True
            _, key, zoom = self.scrolling
            self.off[key] = max(0, min(self.maxoff.get(key, 0), self.off.get(key, 0) - (pos.y() - self.last) / zoom))
            self.last = pos.y()
            self.update()

    def mouseReleaseEvent(self, e):
        pos, self.press = self.press, None
        if self.deck and hasattr(self.deck, 'press'): self.deck.press(None)
        if self.drag or self.moved or pos is None:
            self.drag = None
            return
        fn = next((fn for rect, fn, drag, _ in reversed(self.hits) if not drag and rect.contains(pos)), None)
        if fn: fn(); self.update()

    # ---- drawing helpers ---------------------------------------------------------------------------------------------
    def resizeEvent(self, e):
        self.u, self.fonts = self.width() / 100, {}

    def font(self, kind, size, weight=400, spacing=0.0):
        """kind: see FAMILIES; size in u; spacing in em."""
        key = (kind, size, weight, spacing)
        if key not in self.fonts:
            f = QFont(FAMILIES[kind])
            f.setPixelSize(max(1, round(size * self.u)))
            f.setWeight(QFont.Weight(weight))
            if spacing: f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing * size * self.u)
            self.fonts[key] = (f, QFontMetricsF(f))
        return self.fonts[key]

    def width_of(self, text, f): return self.font(*f)[1].horizontalAdvance(text)

    def wrap(self, text, f, w, lines=None):
        fm, out, line = self.font(*f)[1], [], ''
        for word in text.split():
            trial = f'{line} {word}' if line else word
            if line and fm.horizontalAdvance(trial) > w: out.append(line); line = word
            else: line = trial
        out.append(line)
        if lines and len(out) > lines: out = out[:lines - 1] + [' '.join(out[lines - 1:])]
        return [fm.elidedText(l, Qt.TextElideMode.ElideRight, w) for l in out]

    def text(self, p, text, x, y, f, color, w=None, align=0, lh=1.2, lines=1):
        """Draws text with its top at y (align 0 left, 1 centre, 2 right inside w; wraps when lines != 1). Returns its height."""
        font, fm = self.font(*f)
        rows = [text] if w is None else self.wrap(text, f, w, lines) if lines != 1 else [fm.elidedText(text, Qt.TextElideMode.ElideRight, w)]
        step = f[1] * self.u * lh
        p.setFont(font); p.setPen(color)
        for n, row in enumerate(rows):
            dx = 0 if not align or w is None else (w - fm.horizontalAdvance(row)) / (2 if align == 1 else 1)
            p.drawText(QPointF(x + dx, y + n * step + (step - fm.height()) / 2 + fm.ascent()), row)
        return len(rows) * step

    def spans(self, p, x, y, parts, lh=1.2):
        """Inline runs [(text, font, colour)] on one line starting at x; returns the x after the last one."""
        for text, f, color in parts:
            self.text(p, text, x, y, f, color, lh=lh * parts[0][1][1] / f[1])
            x += self.width_of(text, f)
        return x

    def box(self, p, rect, radius, fill=None, border=None, bw=1.0):
        p.setPen(QPen(border, bw) if border else Qt.PenStyle.NoPen)
        p.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, radius * THEME['radius'], radius * THEME['radius'])

    def hit(self, rect, fn, drag=False, name=''):
        """Marks an area that reacts to a tap (or, with drag, follows the finger). The name is for the self-check."""
        if self.clip is not None: rect = rect.intersected(self.clip)
        if self.xf is not None: rect = self.xf.mapRect(rect)  # a deck paints on a scaled stage: taps arrive in window pixels
        if not rect.isEmpty(): self.hits.append((rect, fn, drag, name))

    def button(self, p, rect, label, fn, f, fg=TEXT, bg=RAISED, border=LINE, radius=1.2):
        self.box(p, rect, radius * self.u, bg, border)
        self.text(p, label, rect.x(), rect.y(), f, fg, rect.width(), 1, rect.height() / (f[1] * self.u))
        self.hit(rect, fn, name=label)

    def icon(self, p, name, rect, color):
        if not QSvgRenderer: return
        key = (name, color.name())
        if key not in self.svgs:
            self.svgs[key] = QSvgRenderer(QByteArray(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{ICONS[name].replace("currentColor", color.name())}</svg>'.encode()))
        self.svgs[key].render(p, rect)

    def paint_of(self, it, rect):  # the coloured gradient that stands in for missing art
        h = 212 if it['s'] == 'steam' else 160 if it['s'] in ('app', 'term') else (self.L['systems'].get(it['s']) or {'hue': 200})['hue']
        k = jhash(it['t']) % 50
        angle = math.radians(120 + k)
        dx, dy = math.sin(angle), -math.cos(angle)
        half = (abs(rect.width() * dx) + abs(rect.height() * dy)) / 2
        c = rect.center()
        g = QLinearGradient(c.x() - dx * half, c.y() - dy * half, c.x() + dx * half, c.y() + dy * half)
        g.setColorAt(0, QColor.fromHslF(h / 360, .62, (24 + k % 14) / 100)); g.setColorAt(1, QColor.fromHslF(((h + 38 + k) % 360) / 360, .58, (12 + k % 9) / 100))
        return g

    def scroller(self, p, key, rect, draw):
        """A clipped area whose content (draw(y) -> end y) can be dragged up and down."""
        off = max(0, min(self.off.get(key, 0), self.maxoff.get(key, 0)))
        p.save(); p.setClipRect(rect)
        self.clip = rect
        end = draw(rect.y() - off)
        self.clip = None
        p.restore()
        self.off[key], self.maxoff[key] = off, max(0, end - (rect.y() - off) - rect.height())
        self.scrolls.append((self.xf.mapRect(rect) if self.xf is not None else rect, key, self.zoom))

    # ---- painting ----------------------------------------------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.hits, self.scrolls, self.clip = [], [], None
        if self.resting():  # black pixels are off on an OLED; the clock moves every minute
            p.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0))
            spot = random.Random(int(time.time() // 60) + (self.side == 'top')).random
            self.text(p, clock(), (8 + 70 * spot()) * self.u, (5 + 80 * spot()) * self.height() / 100, ('b', 3, 400), QColor(70, 70, 80))
            return p.end()
        items = self.items()
        self.S['i'] = max(0, min(self.S['i'], len(items) - 1))
        p.fillRect(0, 0, self.width(), self.height(), INK)
        if THEME['background']:  # the theme's picture, toned down so that text stays readable
            if self.backdrop is None:
                reader = QImageReader(THEME['background'])
                size = reader.size()
                if size.isValid() and size.width() and size.height():
                    k = max(self.width() / size.width(), self.height() / size.height())
                    reader.setScaledSize(QSize(max(1, round(size.width() * k)), max(1, round(size.height() * k))))
                self.backdrop = reader.read()
            if not self.backdrop.isNull():
                p.drawImage((self.width() - self.backdrop.width()) // 2, (self.height() - self.backdrop.height()) // 2, self.backdrop)
                p.fillRect(0, 0, self.width(), self.height(), faded(INK, .72))
        FOCUS.setRgba((self.game_accent(items) or QColor(THEME['colors']['accent'])).rgba())  # highlights take the colour of the game in front
        if self.SETUP and not self.RUN: self.draw_setup(p)
        else: (self.draw_top if self.side == 'top' else self.draw_bottom)(p, items)
        if self.TOAST and not (self.side == 'bottom' and (self.PROMPT or self.CONFIRM)): self.draw_toast(p)
        if self.OSD is not None: self.draw_osd(p)
        p.end()

    def draw_toast(self, p):
        u, W, H, f = self.u, self.width(), self.height(), ('b', 2.6 if self.side == 'bottom' else 1.9)
        rows = self.wrap(self.TOAST, f, 76 * u, None)
        w, h = max(self.width_of(r, f) for r in rows) + 4 * u, len(rows) * f[1] * u * 1.35 + 2.4 * u
        rect = QRectF((W - w) / 2, H - 4 * u - h, w, h)
        self.box(p, rect, 1.2 * u, RAISED, WARN)
        for n, row in enumerate(rows): self.text(p, row, rect.x() + 2 * u, rect.y() + 1.2 * u + n * f[1] * u * 1.35, f, TEXT, lh=1.35)

    def draw_osd(self, p):  # volume indicator for the hardware keys
        u, W, H, big = self.u, self.width(), self.height(), self.side == 'bottom'
        w, ico, size, bar = (70, 5, 3.6, 1.6) if big else (44, 3.4, 2.4, 1)
        h = (ico + 2.8) * u
        rect = QRectF((W - w * u) / 2, H - (8 if big else 6) * u - h, w * u, h)
        self.box(p, rect, h / 2, faded(PANEL, .94), LINE)
        x, mid = rect.x() + 2.4 * u, rect.center().y()
        self.icon(p, 'vol2' if self.OSD > 50 else 'vol1' if self.OSD > 0 else 'vol0', QRectF(x, mid - ico * u / 2, ico * u, ico * u), TEXT)
        num = (size * 1.7) * u
        track = QRectF(x + (ico + 1.6) * u, mid - bar * u / 2, rect.right() - 2.4 * u - num - 1.6 * u - (x + (ico + 1.6) * u), bar * u)
        self.box(p, track, bar * u / 2, LINE)
        if self.OSD > 0: self.box(p, QRectF(track.x(), track.y(), track.width() * self.OSD / 100, track.height()), bar * u / 2, self.accent_fill(track))
        self.text(p, str(self.OSD), rect.right() - 2.4 * u - num, mid - size * u * .6, ('d', size, 700), TEXT, num, 2)

    def pads(self, p, x, y, hints, size=1.7, gap=2.4):
        """Controller hints: a round key cap and its meaning."""
        u, d = self.u, 2.6 * self.u * size / 1.7
        for letter, label in hints:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(TEXT)
            p.drawEllipse(QRectF(x, y, d, d))
            self.text(p, letter, x, y, ('d', 1.5 * size / 1.7, 700), INK, d, 1, d / (1.5 * size / 1.7 * u))
            x += d + .7 * u
            self.text(p, label, x, y, ('b', size), MUTED, lh=d / (size * u))
            x += self.width_of(label, ('b', size)) + gap * u
        return x - gap * u

    def draw_top(self, p, items):
        u, W, H, RUN, P, L = self.u, self.width(), self.height(), self.RUN, self.playing(), self.L
        it = RUN if P else items[self.S['i']] if items else None
        full = QRectF(0, 0, W, H)
        art = self.images.get(it['hero'], W, H) if it and it.get('hero') else False
        if it:
            if art: p.drawImage(0, 0, art); p.fillRect(full, faded(INK, .25))
            else:
                p.fillRect(full, QBrush(self.paint_of(it, full)))
                if art is False: self.text(p, it['t'][:2], W - 3 * u - 60 * u, H / 2 - 18 * u, ('d', 30, 700, -.02), rgba(255, 255, 255, .13), 60 * u, 2)
            g = QLinearGradient(0, 0, W, 0)
            g.setColorAt(0, faded(INK, .92)); g.setColorAt(.45, faded(INK, .55)); g.setColorAt(.8, faded(INK, 0))
            p.fillRect(full, QBrush(g))
            g = QLinearGradient(0, H, 0, 0)
            g.setColorAt(0, faded(INK, .85)); g.setColorAt(.55, faded(INK, 0))
            p.fillRect(full, QBrush(g))
        b, m = ('b', 1.7, 500), ('b', 1.8)
        status = ([('Akku ', b, MUTED), (f'{self.BATT["level"]} %{" ⚡" if self.BATT.get("charging") else ""}', b, TEXT), ('     ', b, TEXT)] if self.BATT else []) + [(clock(), b, TEXT)]
        self.spans(p, W - 3 * u - sum(self.width_of(t, f) for t, f, _ in status), 2.2 * u, status)
        held = bool(it and RUN and RUN.get('paused') and it['id'] == RUN['id'])
        sysinfo = L['systems'].get(it['s']) if it else None
        if not it and self.S['tab'] == 4: label, name, meta, hints, miss = 'System', f'Aussehen: {THEME["name"]}', [[('Helligkeit, WLAN und Konten stehen unten.', m, MUTED)]], [('A', 'Aussehen wechseln')], None
        elif not it: label, name, meta, hints, miss = 'Toravo Tandem', 'Noch nichts hier', [[('Mit RB zu den Systemen wechseln.', m, MUTED)]], [], None
        else:
            label, name = ('Läuft · ' if P else 'Pausiert · ' if held else '') + self.sys_name(it), it['t']
            fact = lambda key, value: [(key + ' ', m, MUTED), (str(value), ('b', 1.8, 500), TEXT)]
            played = L['played'].get(it['id']) or {}
            if P: meta = [fact('Emulator', RUN['emu']), fact('Läuft seit', hours(time.time() - RUN['since']))]
            elif it.get('kind') == 'sys': meta = [[(str(it['n']), ('b', 1.8, 500), TEXT), (' Spiele', m, MUTED)], fact('Emulator', sysinfo.get('emu') or 'fehlt')]
            else: meta = ([fact('Zuletzt', ago(played['last']))] if played.get('last') else []) + ([fact('Spielzeit', hours(played['secs']))] if played.get('secs') else []) + \
                        ([fact('Emulator', sysinfo.get('emu') or 'fehlt')] if sysinfo else []) + ([[('★ Favorit', ('b', 1.8, 500), TEXT)]] if it['id'] in L['fav'] else [])
            miss = sysinfo.get('missing') if sysinfo and not P else None
            if P: hints = [('B', 'Beenden (unten bestätigen)')]
            else:
                inst = it.get('inst')
                hints = [('A', 'Öffnen' if it.get('kind') == 'sys' else 'Fortsetzen' if held else 'Installieren' if inst == 'no' else 'Lädt noch' if inst == 'load' else 'Starten')] + \
                        ([('X', 'Beenden')] if held else []) + [('B', 'Zurück')] + ([] if it.get('kind') or it['s'] in ('app', 'term') else [('Y', 'Favorit')])
        nf, mf = ('d', 6.2, 700), ('m', 1.45, 500)
        rows = self.wrap(name.upper(), nf, 62 * u, None)
        cmd = self.wrap(miss, mf, 71.6 * u, None) if miss else []
        height = 2.3 * u + .6 * u + len(rows) * 6.2 * u * 1.02 + 1.2 * u + 2.2 * u + (1.6 * u + len(cmd) * 1.45 * u * 1.4 + 1.8 * u if cmd else 0) + (2.2 * u + 2.6 * u if hints else 0)
        x, y = 4 * u, H - 4 * u - height
        y += self.text(p, label.upper(), x, y, ('d', 1.9, 700, .14), LIVE if P else FOCUS) + .6 * u
        for row in rows: y += self.text(p, row, x, y, nf, TEXT, lh=1.02)
        y += 1.2 * u
        mx = x
        for part in meta: mx = self.spans(p, mx, y, part) + 2.4 * u
        y += 2.2 * u
        if cmd:
            y += 1.6 * u
            box = QRectF(x, y, max(self.width_of(r, mf) for r in cmd) + 2.4 * u, len(cmd) * 1.45 * u * 1.4 + 1.8 * u)
            self.box(p, box, .8 * u, faded(INK, .7), LINE)
            for n, row in enumerate(cmd): self.text(p, row, x + 1.2 * u, y + .9 * u + n * 1.45 * u * 1.4, mf, WARN, lh=1.4)
            y = box.bottom()
        if hints: self.pads(p, x, y + 2.2 * u, hints)
        if self.CONFIRM:  # the question shows here too: the controller answers it
            p.fillRect(full, faded(INK, .88))
            f = ('d', 3.6, 700)
            rows = self.wrap(self.CONFIRM['text'].upper(), f, 70 * u, None)
            y = (H - len(rows) * 3.6 * u * 1.2 - 2.4 * u - 3.1 * u) / 2
            for row in rows: y += self.text(p, row, 0, y, f, TEXT, W, 1)
            hints = [('A', self.CONFIRM['yes']), ('B', 'Abbrechen')]
            w = sum(3.1 * u + .7 * u + self.width_of(l, ('b', 2)) for _, l in hints) + 3 * u
            self.pads(p, (W - w) / 2, y + 2.4 * u, hints, 2, 3)

    # bottom screen ---------------------------------------------------------------------------------------------------
    def tabs(self, p, title=None, buttons=None):
        """The top row: the five tabs, or a title with buttons on the right [(label, on, fn)]. Returns the y below it."""
        u, f = self.u, ('d', 3, 700, .08)
        x, y, h = 2.6 * u, 2.6 * u, 5.2 * u
        if title is None:  # a theme's wider font must not push the tabs into the count on the right
            need = sum(self.width_of(label.upper(), f) + 4.2 * u for label in TABS)
            if need > 76 * u: f = ('d', round(3 * 76 * u / need, 2), 700, .08)
        def tab(x, label, on, fn):
            w = self.width_of(label.upper(), f) + 3.2 * u
            rect = QRectF(x, y, w, h)
            if on: self.box(p, rect, u, TEXT)
            self.text(p, label.upper(), x, y, f, INK if on else MUTED, w, 1, h / (f[1] * u))
            self.hit(rect, fn, name=label)
            return w
        if title is None:
            for n, label in enumerate(TABS): x += tab(x, label, n == self.S['tab'] and not self.S['sys'], lambda n=n: self.open_tab(n)) + u
        else:
            right = self.width() - 2.6 * u
            for label, on, fn in reversed(buttons):
                right -= self.width_of(label.upper(), f) + 3.2 * u
                tab(right, label, on, fn)
                right -= u
            self.text(p, title, x, y, ('b', 2.3), MUTED, right - x, lh=h / (2.3 * u))
        return y + h + 2.2 * u

    def open_tab(self, n):
        self.S, self.SUB = {'tab': n, 'sys': None, 'i': 0}, ''
        if n == 4: self.load_sys()
        self.push()

    def sliders(self, p, y):
        u, x0, cw = self.u, 2.6 * self.u, self.width() - 5.2 * self.u
        for key, label in (('bt', 'Helligkeit oben'), ('bb', 'Helligkeit unten'), ('vol', 'Lautstärke')):
            value = self.SET.get(key)
            if value is None: continue
            self.text(p, label, x0, y, ('b', 2.5), MUTED, lh=2)
            left, width, low = x0 + 27 * u + 1.5 * u, cw - 27 * u - 11 * u - 3 * u, 0 if key == 'vol' else 5
            part = (value - low) / (100 - low)
            self.box(p, QRectF(left, y + 2.05 * u, width, .9 * u), .45 * u, LINE)
            self.box(p, QRectF(left, y + 2.05 * u, width * part, .9 * u), .45 * u, self.accent_fill(QRectF(left, 0, width, 1)))
            p.setBrush(FOCUS)
            p.drawEllipse(QPointF(left + width * part, y + 2.5 * u), 1.5 * u, 1.5 * u)
            self.text(p, f'{value} %', x0 + cw - 9 * u, y, ('b', 2.5), TEXT, 9 * u, 2, 2)
            self.hit(QRectF(left - 1.5 * u, y - .5 * u, width + 3 * u, 6 * u), lambda x, key=key, left=left, width=width: self.set_value(key, x, left, width), True, key)
            y += 5 * u + 1.8 * u
        return y

    def row_buttons(self, p, y, buttons, cols=4, f=('d', 2.6, 700, .06), fg=MUTED, bg=PANEL):
        """A grid of equal buttons [(label, fn)]; returns the y below it."""
        u, x0, cw, h = self.u, 2.6 * self.u, self.width() - 5.2 * self.u, 6.3 * self.u
        w = (cw - (cols - 1) * 1.2 * u) / cols
        for n, (label, fn) in enumerate(buttons):
            self.button(p, QRectF(x0 + (n % cols) * (w + 1.2 * u), y + (n // cols) * (h + 1.2 * u), w, h), label.upper(), fn, f, fg, bg, LINE, 1.4)
        return y + ((len(buttons) + cols - 1) // cols) * (h + 1.2 * u) - 1.2 * u

    def keyboard(self, p, y, press, skip=()):
        u, x0, cw, bottom = self.u, 2.6 * self.u, self.width() - 5.2 * self.u, self.height() - 2.6 * self.u
        layout = (self.RUN or {}).get('layout') if not self.PROMPT else self.CFG.get('kb_layout')
        layout = layout if layout in KB else 'us' if not self.PROMPT else 'de'
        h = (bottom - y - 4 * 1.1 * u) / 5
        for r, row in enumerate(KB_CODES):
            row = [c for c in row if c not in skip]
            unit = (cw - (len(row) - 1) * u) / sum(5 if c == 57 else 1 for c in row)
            x = x0
            for code in row:
                w = unit * (5 if code == 57 else 1)
                on, label = KB_MODS.get(code) in self.KM, self.key_label(code, layout)
                self.button(p, QRectF(x, y + r * (h + 1.1 * u), w, h), label, lambda code=code: press(code), ('b', 3.4 if len(label) < 3 else 2.4, 600), INK if on else TEXT, FOCUS if on else RAISED, FOCUS if on else LINE)
                x += w + u

    def draw_bottom(self, p, items):
        u, W, H, RUN, P = self.u, self.width(), self.height(), self.RUN, self.playing()
        x0, cw, bottom = 2.6 * u, W - 5.2 * u, H - 2.6 * u
        act = lambda label, fn, x, w, quit=False: self.button(p, QRectF(x, bottom - 6.3 * u, w, 6.3 * u), label.upper(), fn, ('d', 2.6, 700, .06), INK if quit else MUTED, WARN if quit else PANEL, WARN if quit else LINE, 1.4)
        if self.PROMPT:
            def close(ok):
                P_, self.PROMPT = self.PROMPT, None
                if ok: P_['done'](P_['value'])
            y = self.tabs(p, self.PROMPT['title'], [('Abbrechen', False, lambda: close(False)), ('Fertig', True, lambda: close(True))])
            value = '•' * len(self.PROMPT['value']) if self.PROMPT['secret'] else self.PROMPT['value']
            self.box(p, QRectF(x0, y, cw, 9 * u), 1.4 * u, PANEL, FOCUS)
            end = x0 + 2 * u + self.width_of(value, ('b', 4, 500))
            self.text(p, value, x0 + 2 * u, y, ('b', 4, 500), TEXT, lh=9 / 4)
            p.fillRect(QRectF(min(end + .4 * u, x0 + cw - 2 * u), y + 2.5 * u, .4 * u, 4 * u), FOCUS)
            return self.keyboard(p, y + 9 * u + 2.2 * u, self.prompt_key, skip=(29, 56, 1, 103, 105, 108, 106, 15, 58))
        if self.CONFIRM:
            c = self.CONFIRM
            self.text(p, c['text'].upper(), x0, x0, ('d', 4.4, 700), TEXT, cw, lh=1.1, lines=None)
            half = (cw - 1.4 * u) / 2
            act('Abbrechen', self.unconfirm, x0, half)
            return act(c['yes'], lambda: (self.unconfirm(), c['run']()), x0 + half + 1.4 * u, half, True)
        if P and RUN['s'] == 'term':
            layout = RUN.get('layout') if RUN.get('layout') in KB else 'us'
            y = self.tabs(p, 'Linux-Shell', [(f'Tastatur: {"Deutsch" if layout == "de" else "Englisch"}', False, lambda: self.post('api/layout', {'layout': 'us' if layout == 'de' else 'de'})),
                                             ('Schließen', False, lambda: self.post('api/quit'))])
            return self.keyboard(p, y, self.term_key)
        if P and self.show_deck(p): return  # HOOK: native deck, see DECKS above
        if P: return self.ingame(p)
        if self.S['tab'] == 4 and not self.S['sys']: return self.draw_system(p)
        y = self.tabs(p)
        crumb = f'{self.sys_name({"s": self.S["sys"]})} · {len(items)} Spiele' if self.S['sys'] else f'{len(items)} Einträge'
        self.text(p, crumb, x0, 2.6 * u, ('b', 2.3), MUTED, cw, 2, 5.2 / 2.3)
        if RUN and RUN.get('paused'):
            rect = QRectF(x0, y, cw, 6.6 * u)
            self.box(p, rect, 1.4 * u, RAISED, LIVE)
            f, wq, wr = ('d', 2.4, 700, .06), self.width_of('BEENDEN', ('d', 2.4, 700, .06)) + 4 * u, self.width_of('FORTSETZEN', ('d', 2.4, 700, .06)) + 4 * u
            self.button(p, QRectF(rect.right() - 1.6 * u - wq, y + 1.2 * u, wq, 4.2 * u), 'BEENDEN', lambda: self.post('api/quit'), f, TEXT, PANEL, LINE, 1.1)
            self.button(p, QRectF(rect.right() - 1.6 * u - wq - 1.4 * u - wr, y + 1.2 * u, wr, 4.2 * u), 'FORTSETZEN', self.resume, f, INK, LIVE, LIVE, 1.1)
            x = self.spans(p, x0 + 1.6 * u, y, [('⏸ ', ('b', 2.5), MUTED)], 6.6 / 2.5)
            room = rect.right() - 1.6 * u - wq - wr - 3 * u - x - self.width_of(' ist pausiert', ('b', 2.5))
            title = self.font('b', 2.5, 500)[1].elidedText(RUN['t'], Qt.TextElideMode.ElideRight, room)
            self.spans(p, x, y, [(title, ('b', 2.5, 500), TEXT), (' ist pausiert', ('b', 2.5), MUTED)], 6.6 / 2.5)
            y += 6.6 * u + 2.2 * u
        if not items:
            empty = ('Hier erscheinen zuletzt gespielte Spiele und Favoriten. Wechsle mit RB zu den Systemen und starte etwas.' if self.S['tab'] == 0 else
                     'Keine installierten Steam-Spiele gefunden.' if self.S['tab'] == 2 else 'Keine Spiele gefunden. Lege ROMs in ROMs/<System> ab und lies die Bibliothek unter Apps neu ein.')
            return self.text(p, empty, x0 + u, y + 4 * u, ('b', 2.4), MUTED, cw - 2 * u, lh=1.5, lines=None)
        gap = 1.8 * u
        size = (cw - (COLS - 1) * gap) / COLS
        view = QRectF(x0 - .8 * u, y - .8 * u, cw + 1.6 * u, bottom - y + 1.6 * u)
        seen, i = (self.S['tab'], self.S['sys'], self.S['i'], len(items)), self.S['i']
        if seen != self.seen:  # keep the selection in view (the grid follows the controller)
            top = (i // COLS) * (size + gap)
            self.maxoff['grid'] = max(0, (len(items) + COLS - 1) // COLS * (size + gap) - gap + 1.6 * u - view.height())
            self.off['grid'], self.seen = max(min(self.off.get('grid', 0), top), top + size + 1.6 * u - view.height()), seen
        def grid(y):
            for n, x in enumerate(items):
                rect = QRectF(x0 + (n % COLS) * (size + gap), y + .8 * u + (n // COLS) * (size + gap), size, size)
                if n != i and rect.bottom() > view.top() and rect.top() < view.bottom(): self.tile(p, rect, x, n, False)
            n = i
            self.tile(p, QRectF(x0 + (n % COLS) * (size + gap), y + .8 * u + (n // COLS) * (size + gap), size, size), items[n], n, True)  # on top: it is larger
            return y + .8 * u + (len(items) + COLS - 1) // COLS * (size + gap) - gap + .8 * u
        self.scroller(p, 'grid', view, grid)

    def ingame(self, p, top=None, ach=True):
        """The panel while a game runs: title, sliders, RetroArch's buttons, achievements, quit. A deck with tabs of its
        own shows it below them (top) and may keep the achievements for a tab of their own (ach=False)."""
        u, RUN = self.u, self.RUN
        x0, cw, bottom = 2.6 * u, self.width() - 5.2 * u, self.height() - 2.6 * u
        y = (x0 if top is None else top) + self.text(p, RUN['t'].upper(), x0, x0 if top is None else top, ('d', 4.4, 700), TEXT, cw, lh=1.0, lines=2) + .8 * u
        y += self.text(p, 'läuft auf dem oberen Bildschirm', x0, y, ('b', 2.2, 500), LIVE) + 1.8 * u
        tip = f'{self.sys_name(RUN)} · {RUN["emu"]} · seit {hours(time.time() - RUN["since"])} · {clock()}' + (f' · Akku {self.BATT["level"]} %{" (lädt)" if self.BATT.get("charging") else ""}' if self.BATT else '')
        y += self.text(p, tip, x0, y, ('b', 2.2), MUTED, cw, lh=1.45, lines=None) + 1.8 * u
        y = self.sliders(p, y)
        if RUN['emu'] == 'RetroArch': y = self.row_buttons(p, y, [(label, lambda k=k: self.post('api/retroarch', {'name': k})) for k, label in RA]) + 1.8 * u
        if self.ACH and ach: self.scroller(p, 'ach', QRectF(x0, y, cw, bottom - 6.3 * u - 1.8 * u - y), lambda y: self.achievements(p, y))
        return self.button(p, QRectF(x0, bottom - 6.3 * u, cw, 6.3 * u), 'SPIEL BEENDEN', lambda: self.post('api/quit'), ('d', 2.6, 700, .06), INK, WARN, WARN, 1.4)

    def achievements(self, p, y):
        """The running game's RetroAchievements from y on; returns the y below them (for scroller())."""
        A, u, x0, cw = self.ACH, self.u, 2.6 * self.u, self.width() - 5.2 * self.u
        f, w = ('b', 2.1), cw - 2.8 * u
        if A.get('note'): return y + self.text(p, A['note'], x0, y, ('b', 2.2), MUTED, cw, lh=1.45, lines=None)
        self.spans(p, x0, y, [(f'Erfolge {A["earned"]} / {A["total"]}', ('b', 2.2, 500), TEXT), (f' · {A["points"]} Punkte', ('b', 2.2), MUTED)], 1.45)
        y += 2.2 * u * 1.45 + u
        for a in A.get('list') or []:
            rows = self.wrap(a.get('d') or '', f, w, None)
            h = (1 + len(rows)) * 2.1 * u * 1.25 + 2 * u
            self.box(p, QRectF(x0, y, cw, h), u, PANEL)
            self.text(p, ('✓ ' if a.get('e') else '') + a['t'], x0 + 1.4 * u, y + u, ('b', 2.1, 500), LIVE if a.get('e') else TEXT, w - 8 * u, lh=1.25)
            self.text(p, str(a.get('p', '')), x0 + 1.4 * u, y + u, f, FOCUS, w, 2, 1.25)
            for n, row in enumerate(rows): self.text(p, row, x0 + 1.4 * u, y + u + (n + 1) * 2.1 * u * 1.25, f, MUTED, lh=1.25)
            y += h + u
        return y - u

    def tile(self, p, rect, x, n, on):
        u, RUN = self.u, self.RUN
        if on:
            rect = rect.adjusted(-.02 * rect.width(), -.02 * rect.height(), .02 * rect.width(), .02 * rect.height())
            if THEME['glow']: self.box(p, rect.adjusted(-.35 * u, -.35 * u, .35 * u, .35 * u), 1.9 * u, faded(FOCUS, .25 * THEME['glow']))
        size = round(rect.width())
        cover = self.images.get(x['cover'], size, size) if x.get('cover') else False
        self.box(p, rect, 1.6 * u, QBrush(self.paint_of(x, rect)))
        if cover:
            brush = QBrush(cover)
            brush.setTransform(brush.transform().translate(rect.x(), rect.y()))
            if x.get('inst'): p.setOpacity(.4)  # not installed (yet): dimmed
            self.box(p, rect.adjusted(.35 * u, .35 * u, -.35 * u, -.35 * u), 1.25 * u, brush)  # the tile's colour stays as a thin frame
            p.setOpacity(1)
        elif cover is False:
            name = None if x['s'] != 'app' else 'term' if x['id'] == 'term' else 'scan' if x['id'] == 'rescan' else 'play' if x['id'] == 'act:steam' else 'desk' if x['id'] == 'act:desktop' else 'get' if x['id'].startswith('upd:') else \
                'web' if 'firefox' in x['t'].lower() or 'browser' in x['t'].lower() else 'pad'
            if name and QSvgRenderer: self.icon(p, name, QRectF(rect.x() + .22 * rect.width(), rect.y() + .14 * rect.height(), .56 * rect.width(), .56 * rect.height()), rgba(255, 255, 255, .85))
            else: self.text(p, x['t'][:2], rect.x() + 1.2 * u, rect.y() + .4 * u, ('d', 7, 700), rgba(255, 255, 255, .28), lh=1)
        rows = self.wrap(x['t'], ('b', 1.75, 500), rect.width() - 2.2 * u, 2)
        lh = 1.75 * u * 1.15
        shade = QRectF(rect.x(), rect.bottom() - 3.9 * u - len(rows) * lh, rect.width(), 3.9 * u + len(rows) * lh)
        g = QLinearGradient(0, shade.bottom(), 0, shade.top())
        g.setColorAt(0, rgba(0, 0, 0, .78)); g.setColorAt(1, rgba(0, 0, 0, 0))
        p.save(); p.setClipRect(shade)
        self.box(p, rect, 1.6 * u, QBrush(g))
        p.restore()
        for k, row in enumerate(rows): self.text(p, row, rect.x() + 1.1 * u, shade.bottom() - .9 * u - (len(rows) - k) * lh, ('b', 1.75, 500), ON_ART, lh=1.15)
        badge = str(x['n']) if x.get('kind') == 'sys' else ('↓' if x['inst'] == 'no' else '…' if x.get('pct') is None else f'{x["pct"]} %') if x.get('inst') else None
        if badge:
            w = self.width_of(badge, ('d', 1.9, 700)) + 1.6 * u
            self.box(p, QRectF(rect.right() - u - w, rect.y() + u, w, 2.5 * u), .8 * u, rgba(0, 0, 0, .55))
            self.text(p, badge, rect.right() - u - w, rect.y() + u, ('d', 1.9, 700), ON_ART, w, 1, 2.5 / 1.9)
        star = '⏸' if RUN and RUN.get('paused') and x['id'] == RUN['id'] else '★' if x['id'] in self.L['fav'] else ''
        if star: self.text(p, star, rect.right() - 4 * u, rect.y() + u, ('b', 2.4), FOCUS, 3 * u, 2)
        if on: self.box(p, rect, 1.6 * u, None, FOCUS, .35 * u)
        def tap(n=n):
            if n == self.S['i']: self.go('ok')
            else: self.S['i'] = n; self.push()
        self.hit(rect, tap, name=x['t'])

    def draw_system(self, p):
        u, x0, cw, bottom, SYS, CFG = self.u, 2.6 * self.u, self.width() - 5.2 * self.u, self.height() - 2.6 * self.u, self.SYS, self.CFG
        if not SYS and not self.asked: self.asked = True; self.load_sys()
        y = self.sliders(p, self.tabs(p))
        f, bf = ('b', 2.5), ('d', 2.3, 700, .06)
        foot = bottom - 6.3 * u
        if self.SUB == 'wifi':
            def nets(y):
                for n in (SYS or {}).get('networks') or []:
                    rect = QRectF(x0, y, cw, 6 * u)
                    self.box(p, rect, 1.2 * u, RAISED, LINE)
                    self.text(p, n['ssid'], x0 + 1.8 * u, y, ('b', 2.6, 500), TEXT, cw * .55, lh=6 / 2.6)
                    self.text(p, ('verbunden · ' if n.get('active') else '') + f'{n["signal"]} %' + (' · geschützt' if n.get('secure') else ''), x0, y, ('b', 2.6, 500), MUTED, cw - 1.8 * u, 2, 6 / 2.6)
                    self.hit(rect, lambda n=n: self.wifi(n), name=n['ssid'])
                    y += 7 * u
                if not (SYS or {}).get('networks'): y += self.text(p, 'Keine Netze gefunden.', x0, y, ('b', 2.2), MUTED, lh=1.45) + u
                self.button(p, QRectF(x0, y, cw, 6 * u), 'Zurück', lambda: setattr(self, 'SUB', ''), ('b', 2.6, 500), TEXT, RAISED, LINE)
                return y + 6 * u
            self.scroller(p, 'wifi', QRectF(x0, y, cw, foot - 1.8 * u - y), nets)
        else:
            def line(y, label, value, buttons=()):
                right = x0 + cw
                for text, fn in reversed(buttons):
                    w = self.width_of(text.upper(), bf) + 3.6 * u
                    self.button(p, QRectF(right - w, y, w, 5.6 * u), text.upper(), fn, bf)
                    right -= w + 1.4 * u
                self.text(p, label, x0, y, f, MUTED, lh=5.6 / 2.5)
                self.text(p, value, x0 + 26.4 * u, y, ('b', 2.5, 500), TEXT, right - x0 - 26.4 * u, lh=5.6 / 2.5)
                return y + 5.6 * u + 1.8 * u
            def scan():
                self.SUB = 'wifi'
                self.toast('Suche Netze …')
                self.load_sys(True)
            y = line(y, 'WLAN', (SYS.get('ssid') or 'nicht verbunden') if SYS else '…', [('Netze', scan)])
            y = line(y, 'Speicher', ' · '.join(f'{s["name"]} {round(s["free"] / 1e9)} von {round(s["total"] / 1e9)} GB frei' for s in SYS['storage']) if SYS else '…')
            y = line(y, 'Erfolge', (CFG.get('ra_user') or 'kein Konto') + (' · angemeldet' if CFG.get('ra_login') else ''),
                     [('Name', lambda: self.ask_account('ra_user')), ('Passwort', lambda: self.ask_account('ra_password')), ('Schlüssel' + (' ✓' if CFG.get('ra_key_set') else ''), lambda: self.ask_account('ra_key'))])
            y = line(y, 'Aussehen', THEME['name'], [('Wechseln', self.next_theme)])
            y = line(y, 'Tandem', 'Version ' + str(CFG.get('version', '')), [('Einrichtung', lambda: self.post('api/setup', {'open': True}))])
            if self.PAIR and self.PAIR.get('url'):
                own = self.PAIR.get('own')  # the owner's own address for the settings page comes first
                self.spans(p, x0, y, [('Bequemer vom Handy oder PC' + ('' if own else ' im selben WLAN') + ': ', ('b', 2.2), MUTED), (own or self.PAIR['url'], ('b', 2.2, 500), TEXT), (' · PIN ', ('b', 2.2), MUTED), (str(self.PAIR['pin']), ('b', 2.2, 500), TEXT)])
                self.text(p, f'Im Heimnetz auch: {self.PAIR["url"]} · {self.PAIR["ip_url"]}' if own else f'Falls der Name nicht gefunden wird: {self.PAIR["ip_url"]}', x0, y + 3.4 * u, ('b', 2.2), MUTED, self.width() - 5.2 * u)
        self.row_buttons(p, foot, [(POWER[name][1], lambda name=name: self.confirm_action(name)) for name in POWER])


def main():
    global ADDR
    parser = argparse.ArgumentParser(description='Toravo Tandem, native front end')
    parser.add_argument('--screen', choices=('top', 'bottom'), required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8377')
    parser.add_argument('--window', help='WIDTHxHEIGHT: a plain window instead of full screen (for trying it on a desktop)')
    args = parser.parse_args()
    url = urlparse(args.url)
    ADDR = (url.hostname or '127.0.0.1', url.port or 8377)
    signal.signal(signal.SIGINT, signal.SIG_DFL); signal.signal(signal.SIGTERM, signal.SIG_DFL)  # Qt's loop would hold Python's handlers back
    app = QGuiApplication(sys.argv[:1])
    for file in sorted((Path(__file__).resolve().parent / 'fonts').glob('*.ttf')): QFontDatabase.addApplicationFont(str(file))
    try: apply_theme(read_theme(json.loads(fetch('api/state')).get('config', {}).get('theme') or 'toravo'))  # the first frame already in the chosen look
    except (OSError, ValueError): pass
    window = Tandem(args.screen)
    def oops(kind, error, trace):  # an error must not leave a frozen screen without a hint
        traceback.print_exception(kind, error, trace)
        window.toast(f'Fehler: {error}')
    sys.excepthook = oops
    if args.window:
        window.resize(*map(int, args.window.split('x')))
        window.show()
    else: window.showFullScreen()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
