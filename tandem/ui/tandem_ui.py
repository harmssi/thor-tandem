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
                           QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient, QRasterWindow)
try: from PySide6.QtSvg import QSvgRenderer  # icons only; without it tiles show initials
except ImportError: QSvgRenderer = None
import settings_view  # noqa: E402  the Einstellungen tab (its own module: big, and changed on its own)
sys.modules.setdefault('tandem_ui', sys.modules[__name__])  # decks importing tandem_ui see the live __main__ module
settings_view.ui = sys.modules[__name__]
import quick_view  # noqa: E402  the Thor key's quick menu on the bottom screen
quick_view.ui = sys.modules[__name__]
import screensaver  # noqa: E402  dual-screen OLED screensaver showcase
screensaver.ui = sys.modules[__name__]
import iisu_fx  # noqa: E402  iiSU x Cocoon 3D showcase, Hinge-Bridge, Liquid Glass, Spring & Pods
iisu_fx.ui = sys.modules[__name__]
import lang  # noqa: E402  English texts (config lang 'en')
import qr  # noqa: E402  pure-Python QR code renderer for phone sign-in

INK, PANEL, RAISED, LINE, TEXT, MUTED, FOCUS, LIVE, WARN = (QColor(c) for c in ('#07080b', '#15161b', '#202128', '#2c2d35', '#f5f5f7', '#9a9ba4', '#ffb23e', '#34d399', '#ff6b5e'))
ON_ART = QColor('#eef0f6')  # text on covers and on their dark shade: light in every theme
FAMILIES = {'u': ['Inter', 'Adwaita Sans', 'Noto Sans'], 'd': ['Barlow Condensed', 'Nimbus Sans Narrow'], 'b': ['Barlow', 'Noto Sans'], 'm': ['Hack', 'Liberation Mono'],  # interface; display, body (decks); monospace
            'n': ['Arial Narrow', 'Nimbus Sans Narrow', 'Barlow Condensed'], 's': ['Georgia', 'Noto Serif', 'C059', 'Nimbus Roman']}  # for decks: narrow, serif
TABS, COLS = ['Start', 'Systeme', 'Steam', 'Apps', 'Einstellungen'], 5
WEEKDAYS, MONTHS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'], ['Jan.', 'Feb.', 'März', 'Apr.', 'Mai', 'Juni', 'Juli', 'Aug.', 'Sep.', 'Okt.', 'Nov.', 'Dez.']
RA = [('save', 'Speichern'), ('load', 'Laden'), ('slot-', 'Slot −'), ('slot+', 'Slot +'), ('ff', 'Vorspulen'), ('pause', 'Pause'), ('menu', 'Menü'), ('shot', 'Foto')]
ICONS = {'term': '<path d="M4 5h16v14H4z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M7 9l3 3-3 3M12 15h5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
         'web': '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4 12h16M12 4c3 3 3 13 0 16M12 4c-3 3-3 13 0 16" fill="none" stroke="currentColor" stroke-width="1.6"/>',
         'get': '<path d="M12 4v10m0 0l-4-4m4 4l4-4M5 19h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
         'scan': '<path d="M19 12a7 7 0 1 1-2-5M19 5v4h-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
         'play': '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 8.5l6 3.5-6 3.5z" fill="currentColor"/>',
         'pad': '<path d="M6 8h12a4 4 0 0 1 4 4v1a3 3 0 0 1-5.5 1.7L15 13H9l-1.5 1.7A3 3 0 0 1 2 13v-1a4 4 0 0 1 4-4z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M7 10v3M5.5 11.5h3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
         'yt': '<rect x="2.5" y="5.5" width="19" height="13" rx="4" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 9v6l5-3z" fill="currentColor"/>',
         'plex': '<path d="M8 4h4.5l5 8-5 8H8l5-8z" fill="currentColor"/>',
         'gal': '<rect x="3" y="5" width="18" height="14" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="8.5" cy="10" r="1.6" fill="currentColor"/><path d="M4.5 17l4.5-4.5 3.5 3.5 3-3 4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
         'desk': '<path d="M4 5h16v11H4zM9 20h6M12 16v4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
         'vol0': '<path d="M3 9v6h4l5 4V5L7 9z" fill="currentColor"/>'}
ICONS['vol1'] = ICONS['vol0'] + '<path d="M15 9a4 4 0 0 1 0 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
ICONS['vol2'] = ICONS['vol1'] + '<path d="M17.5 6.5a8 8 0 0 1 0 11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
# On-screen keyboard: physical keys (evdev codes) in ISO order; the labels follow the layout the service set, the
# system's keymap does the actual translation.
KB_CODES = [[41, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14], [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27], [58, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 43, 28],
            [42, 86, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 103], [29, 56, -2, 57, 100, 1, 105, 108, 106]]
KB_ROWS = [[41, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27], [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 43], [44, 45, 46, 47, 48, 49, 50, 51, 52, 53]]
KB_NAME = {-2: '@', 14: '⌫', 15: 'Tab', 28: '↵', 42: '⇧', 58: '⇪', 29: 'Strg', 56: 'Alt', 57: ' ', 100: 'AltGr', 1: 'Esc', 103: '↑', 105: '←', 108: '↓', 106: '→'}
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
# An emulated game with a companion pack (run['pack'], see find_pack in tandem.py) gets the deck 'pack'; a native port
# names its deck itself (run['port'], see PORTS in tandem.py) and talks to it over a socket (decks/portsocket.py).
DECKS = {'377840': 'ffix', '377160': 'pipboy'}  # Final Fantasy IX, Fallout 4
POWER = {'suspend': ('In den Standby gehen?', 'Standby'), 'sleep': ('In den Tiefschlaf gehen?', 'Tiefschlaf'),
         'reboot': ('Thor neu starten?', 'Neu starten'), 'poweroff': ('Thor ausschalten?', 'Ausschalten'),
         'desktop': ('Zum Desktop wechseln?', 'Desktop')}
POWER_MENU = [('suspend', 'Standby', False), ('sleep', 'Tiefschlaf', False), ('reboot', 'Neu starten', True),
              ('poweroff', 'Ausschalten', True), ('desktop', 'Zum Desktop', True)]

ADDR = ('127.0.0.1', 8377)
URL = 'http://127.0.0.1:8377'


class Haptics:
    """Crisp 12 ms LRA tap on the Thor's Qualcomm HV haptics motor (qcom-hv-haptics) for tactile keyboard clicks."""
    def __init__(self): self.fd, self.eff_id, self.tried = None, -1, False

    def open(self):
        self.tried = True
        if sys.platform != 'linux' or os.environ.get('QT_QPA_PLATFORM') == 'offscreen': return
        import fcntl, glob, struct
        for p in sorted(glob.glob('/dev/input/event*')):
            fd = -1
            try:
                fd = os.open(p, os.O_RDWR | os.O_NONBLOCK)
                name = fcntl.ioctl(fd, 0x80FF4506, bytes(256)).split(b'\0', 1)[0].decode('utf-8', 'replace')
                if 'qcom-hv-haptics' in name:
                    buf = bytearray(struct.pack('HhHHHHH2x', 0x50, -1, 0, 0, 0, 12, 0) + struct.pack('HH28x', 0x3000, 0x1C00))
                    fcntl.ioctl(fd, 0x40304580, buf, True)  # EVIOCSFF (48-byte struct ff_effect on LP64)
                    self.fd, self.eff_id = fd, struct.unpack_from('h', buf, 2)[0]
                    return
                os.close(fd)
            except OSError:
                if fd >= 0:
                    try: os.close(fd)
                    except OSError: pass

    def tap(self):
        if not self.tried: self.open()
        if self.fd is None or self.eff_id < 0: return
        import struct
        try: os.write(self.fd, struct.pack('llHHi', 0, 0, 0x15, self.eff_id, 1))
        except OSError: pass


HAPTICS = Haptics()


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
DEFAULT_THEME = {'id': 'toravo', 'name': 'Toravo', 'era': 'modern', 'bgm': 'era-modern.ogg', 'radius': 1.0, 'glow': 1.0, 'gradient': None, 'background': None, 'gameAccent': True,
                 'colors': {'bg': '#07080b', 'panel': '#15161b', 'raised': '#202128', 'line': '#2c2d35', 'text': '#f5f5f7', 'muted': '#9a9ba4', 'accent': '#ffb23e', 'live': '#34d399', 'warn': '#ff6b5e'},
                 'fonts': {'ui': ['Inter', 'Adwaita Sans', 'Noto Sans'], 'display': ['Barlow Condensed', 'Nimbus Sans Narrow'], 'body': ['Barlow', 'Noto Sans']}}
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
    if data.get('era') in ('8bit', '16bit', 'modern'): theme['era'] = data['era']
    if isinstance(data.get('bgm'), str) and data['bgm'].strip(): theme['bgm'] = os.path.basename(data['bgm'].strip())
    elif theme['era'] in ('8bit', '16bit'): theme['bgm'] = f'era-{theme["era"]}.ogg'
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
    FAMILIES['u'][:], FAMILIES['d'][:], FAMILIES['b'][:] = theme['fonts']['ui'], theme['fonts']['display'], theme['fonts']['body']


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
    """Decode and scale cleanly with `SmoothTransformation` (never raw `QImageReader` upscaling) plus crisp integer
    pixel-art preservation for native <=512x480 console screenshots.
    `cover`:
      - True: fills w x h (centred, cropped)
      - False: fits inside w x h preserving aspect ratio
      - 'tile': portrait/wide cover over darkened blurred self-fill so no title gets cut off
      - 'hero': full-screen top backdrop; if source is low-res (<720x360) or portrait/square (<1.15:1), renders a silky
        ambient color-wash backdrop + razor-sharp framed showcase artwork on the right instead of smearing small art."""
    buf = QBuffer(); buf.setData(QByteArray(fetch(path, addr=addr))); buf.open(QBuffer.OpenModeFlag.ReadOnly)
    kind = path.rsplit('.', 1)[-1].lower().replace('jpeg', 'jpg').encode()
    reader = QImageReader(buf, kind)  # naming the format keeps Qt from loading every image plug-in (HEIF, RAW, EXR …) to probe
    if not reader.canRead(): buf.seek(0); reader = QImageReader(buf)  # wrong file ending: let Qt find out
    size = reader.size()
    orig_w = size.width() if size.isValid() else 0
    orig_h = size.height() if size.isValid() else 0
    is_pixel_art = bool(0 < orig_w <= 512 and 0 < orig_h <= 480 and orig_w != orig_h)

    if cover == 'hero':
        if w and h and orig_w and orig_h:
            ar = orig_w / orig_h
            if ar < 1.10 or ar > 3.5 or orig_h < 120:
                img = reader.read()
                if img.isNull(): return False
                blur = img.scaled(28, 18, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                blur = blur.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                p = QPainter(out)
                p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
                p.drawImage(0, 0, blur, (blur.width() - w) // 2, (blur.height() - h) // 2, w, h)
                p.fillRect(0, 0, w, h, QColor(8, 10, 18, 148))
                p.end()
                return out
            if orig_w < 720 or orig_h < 360:
                img = reader.read()
                if img.isNull(): return False
                if orig_w <= 400 and orig_h <= 320:
                    img = img.scaled(orig_w * 2, orig_h * 2,
                                     Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
                scaled = img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                p = QPainter(out)
                p.drawImage(0, 0, scaled, (scaled.width() - w) // 2, (scaled.height() - h) // 2, w, h)
                p.fillRect(0, 0, w, h, QColor(8, 10, 18, 52))
                p.end()
                return out
        cover = True

    if cover == 'square':
        img = reader.read()
        if img.isNull(): return False
        if w and h and img.width() and img.height():
            if is_pixel_art and (img.width() < w or img.height() < h):
                mult = max(2, min(4, math.ceil(max(w / img.width(), h / img.height()))))
                img = img.scaled(img.width() * mult, img.height() * mult,
                                 Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
            portrait = img.height() > img.width() * 1.14
            tw = round(w * 1.04) if portrait else w
            th = round(h * 1.04) if portrait else h
            if img.width() != tw or img.height() != th:
                img = img.scaled(tw, th, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            cx = max(0, (img.width() - w) // 2)
            cy = max(0, round((img.height() - h) * (0.28 if portrait else 0.50)))
            img = img.copy(cx, cy, min(w, img.width()), min(h, img.height()))
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    if cover == 'tile':
        cover = True
        if w and h and orig_w and orig_h and not .83 < (orig_w / orig_h) / (w / h) < 1.2:
            img = reader.read()
            if img.isNull(): return False
            fit = img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            blur = img.scaled(14, 14, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            blur = blur.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            p = QPainter(out)
            p.drawImage(0, 0, blur, (blur.width() - w) // 2, (blur.height() - h) // 2, w, h)
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, 90))
            p.drawImage((w - fit.width()) // 2, (h - fit.height()) // 2, fit)
            p.end()
            return out

    # Only pre-downscale in QImageReader when source is much larger than target (2x supersampled decode);
    # NEVER upscale via QImageReader.setScaledSize (which uses non-smooth point scaling in Qt!).
    if w and h and orig_w and orig_h:
        k = (max if cover else min)(w / orig_w, h / orig_h)
        if k < 0.5:
            k2 = min(1.0, k * 2.0)
            reader.setScaledSize(QSize(max(1, round(orig_w * k2)), max(1, round(orig_h * k2))))
    img = reader.read()
    if img.isNull(): return False
    if w and h and img.width() and img.height():
        if is_pixel_art and (img.width() < w or img.height() < h):
            mult = max(2, min(4, math.ceil(max(w / img.width(), h / img.height()))))
            img = img.scaled(img.width() * mult, img.height() * mult,
                             Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        if cover:
            if img.width() != w or img.height() != h:
                img = img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            img = img.copy((img.width() - w) // 2, (img.height() - h) // 2, w, h)
        else:
            k_fit = min(w / img.width(), h / img.height())
            tw, th = max(1, round(img.width() * k_fit)), max(1, round(img.height() * k_fit))
            if (tw, th) != (img.width(), img.height()):
                img = img.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
        self.ACH = self.PAIR = self.SYS = self.PROMPT = self.CONFIRM = self.OSD = self.SETUP = self.QUICK = self.REC = self.SAVES = self.SYSBK = self.UPDC = None
        self.GAME_MENU, self.DOCK = None, None
        self.DOZE, self.MUTED, self.POWER_OPEN, self.PROMPT_OPEN, self.power_i = False, False, False, False, 0
        self.kb_rc, self.kb_pad = (1, 0), False
        self.kb_keys, self.kb_down, self.kb_flash = [], None, None
        self.THOR = self.CTRL = self.UPD = self.focus_seen = None  # the settings: Thor hardware, button layout, update check
        self.thor_at = 0.0
        self.ui_lock, self.ui_out, self.ui_busy = threading.Lock(), None, False
        self.TOAST, self.SUB, self.KM, self.asked = '', '', set(), False
        self.hits, self.scrolls, self.clip, self.off, self.maxoff, self.seen = [], [], None, {}, {}, None
        self.tile_rects = []
        self.press = self.drag = self.drag_kind = self.scrolling = self.pending = self.deck = self.xf = None
        self.press_rect = None
        self.vel_samples, self.kinetic, self.stopped_kinetic = [], None, False
        self.scroll_touch_at = {}
        self.stage_drag = None
        self.lp_target, self.lp_fired = None, False
        self.zoom = 1.0
        self.moved = False
        self.fonts, self.svgs, self.u = {}, {}, 1.0
        self.images = Images(18 if screen == 'top' else 96, self.loaded)  # top: hero, logo and preview; bottom: tiles and frames
        self.ov_raw, self.ov_cache = {}, {}  # persistent platform mask/overlay frames (instant on theme/era switch)
        self.comp_cache = OrderedDict()
        self._cfg_seq, self._last_overlays = 0, True
        self.thumbs = Images(8, self.loaded, workers=1)  # covers at 24 pixels, to find a game's colour
        self.saver_imgs = Images(160, self.loaded, workers=4)  # uncropped full-aspect covers & boxes for the dual-screen screensaver
        self.backdrop, self.WIFI = None, None
        self.hero = {'cur': None, 'prev': None, 't0': 0.0, 'key': None, 'kt': 0.0}  # top: picture cross-fade and title fade-in
        self.lift = (None, 0.0)  # bottom: the selected tile rises (key, start)
        self.acc_anim = {'from_c': None, 'to_c': None, 'to': None, 't0': 0.0}
        self.tab_anim = {'fx': 0.0, 'fw': 0.0, 'tx': 0.0, 'tw': 0.0, 'key': None, 't0': 0.0}
        self.scroll_anim = None  # (from_off, to_off, t0) for smooth D-pad row scrolling
        self.focus_anim = {'fx': 0.0, 'fy': 0.0, 'tx': 0.0, 'ty': 0.0, 'key': None, 'page': None, 't0': 0.0}
        self.page_anim = (None, 0.0)
        self.stage_anim = {'from': 0.0, 'to': 0.0, 'page': None, 't0': 0.0}
        self._rgb_last, self._rgb_pending = None, None
        self.rgb_timer = QTimer(self); self.rgb_timer.setSingleShot(True); self.rgb_timer.timeout.connect(self._flush_rgb)
        load_accents()
        self.active = time.time()  # last input, for resting()
        self.event.connect(self.on_event)
        self.result.connect(lambda then, reply: (then(reply), self.update()))
        self.loaded.connect(self.update)
        self.timers = {name: QTimer(self, singleShot=True) for name in ('toast', 'osd', 'set')}
        self.kb_rep = QTimer(self)
        self.kb_rep.timeout.connect(self._kb_repeat_tick)
        self.kinetic_timer = QTimer(self, interval=16)
        self.kinetic_timer.timeout.connect(self._tick_kinetic)
        self.saver_timer = QTimer(self, interval=16)
        self.saver_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.saver_timer.timeout.connect(self._tick_saver)
        self.lp_timer = QTimer(self, singleShot=True)
        self.lp_timer.timeout.connect(self._on_long_press)
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

    def _prewarm_overlays(self):
        ovs = dict((self.L or {}).get('overlays') or {})
        if not ovs: return
        def work():
            changed = False
            for ov in ovs.values():
                for k in ('mask', 'overlay'):
                    pth = ov.get(k)
                    if pth and pth not in self.ov_raw:
                        try: img = load_image(pth, 0, 0, False, addr=self.images.addr)
                        except Exception: img = False
                        self.ov_raw[pth] = img
                        changed = True
            if changed and self.images.alive:
                self.loaded.emit()
        threading.Thread(target=work, daemon=True).start()

    def overlay_image(self, path, size):
        """Return scaled platform mask/overlay QImage synchronously from persistent RAM cache (loads once on demand)."""
        ck = (path, int(size))
        cached = self.ov_cache.get(ck)
        if cached is not None:
            return cached
        raw = self.ov_raw.get(path)
        if raw is None:
            try: raw = load_image(path, 0, 0, False, addr=self.images.addr)
            except Exception: raw = False
            self.ov_raw[path] = raw
        if not raw:
            self.ov_cache[ck] = False
            return False
        scaled = raw.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation) if (raw.width() != size or raw.height() != size) else raw
        if len(self.ov_cache) > 128:
            self.ov_cache.clear()
        self.ov_cache[ck] = scaled
        return scaled

    def load(self):
        def got(library):
            if library:
                self.L = library
                if self.side == 'bottom':
                    self._prewarm_overlays()
        self.call('api/library', then=got)

    def pulse(self):
        seq = self._cfg_seq
        def got(s):
            if not s: return
            self.BATT, self.WIFI, self.PAIR = s.get('battery'), s.get('wifi'), s.get('pair')
            if self._cfg_seq == seq and s.get('config'):
                self.CFG = s['config']
            self.BT_AUDIO = s.get('bt_audio')
            self.DOZE, self.MUTED = bool(s.get('doze')), bool(s.get('muted'))
            if s.get('power') and not self.POWER_OPEN: self.power_i = 0
            self.POWER_OPEN = bool(s.get('power'))
            self.PROMPT_OPEN = bool(s.get('prompt'))
            if self.side == 'bottom' and s.get('swkbd') and (not self.PROMPT or self.PROMPT.get('swkbd_id') != s['swkbd'].get('id')):
                self.open_swkbd(s['swkbd'])
            elif self.side == 'bottom' and not s.get('swkbd') and self.PROMPT and self.PROMPT.get('swkbd_id'):
                self.PROMPT = None
            self.follow_setup(s.get('setup'))
            if self._cfg_seq == seq:
                self.follow_theme()
            if not self.drag and isinstance(s.get('settings'), dict):
                self.SET = {k: (v if v is not None else self.SET.get(k)) for k, v in s['settings'].items()}
        self.call('api/state', then=got)
        if (self.side == 'bottom' and self.RUN and self.ACH and self.ACH.get('list')
                and time.time() - getattr(self, '_ach_poll_at', 0) > 45):
            self._ach_poll_at = time.time()
            self.load_ach(refresh=True)
        # Auto-dim bottom OLED during gameplay when untouched (saves ~1.2 W; first touch wakes immediately)
        idle_s = int(self.CFG.get('bottom_idle_secs') or 0)
        if (self.side == 'bottom' and idle_s > 0 and self.RUN and not self.QUICK and not self.DOZE
                and not getattr(self, '_auto_bb_off', False) and time.time() - self.active >= idle_s):
            self._auto_bb_off = True
            self._auto_bb_saved = max(15, int(self.SET.get('bb') or 50))
            self.post('api/set', {'key': 'bb', 'value': 0, 'from': self.me})
        if not (self.side == 'top' and self.playing() and not self.POWER_OPEN):
            self.update()  # the clock

    def load_sys(self, scan=False): self.call('api/system' + ('?scan' if scan else ''), then=lambda s: s and setattr(self, 'SYS', s))

    def load_ach(self, refresh=False):
        if self.side != 'bottom': return  # only the bottom screen shows achievements
        if not refresh: self._ach_poll_at = time.time()
        def got(a):
            if not self.RUN: return
            if refresh and not (a and a.get('list')): return
            self.ACH = a or {'note': 'Erfolge konnten nicht geladen werden.'}
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
               'Ändern kannst du beides jederzeit unter „Einstellungen“ – oder bequem vom Handy über die dort gezeigte Adresse.']
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
        y = 5 * u + self.text(p, f'EINRICHTUNG · SCHRITT {step + 1} VON 4', x0, 5 * u, ('u', 1.6 if self.side == 'top' else 1.9, 700, .14), FOCUS) + 1.5 * u
        y += self.text(p, title, x0, y, ('u', 4.4 if self.side == 'top' else 4, 700, -.025), TEXT, cw, lh=1.1, lines=None) + 2 * u
        if self.side == 'top':
            for row in rows: y += self.text(p, row, x0, y, ('u', 2), MUTED, cw, lh=1.45, lines=None) + 1.2 * u
            return
        can = step == 2 and any(m['store'] or m['extra'] for m in self.SETUP.get('missing', ()))
        names = ([('Zurück', 'back')] if step else []) + ([('Installieren', 'install')] if can else []) + [('Fertig' if step == 3 else 'Weiter', 'ok')]
        w = (cw - 1.4 * u * (len(names) - 1)) / len(names)
        for n, (label, a) in enumerate(names):
            last = a == 'ok'
            self.button(p, QRectF(x0 + n * (w + 1.4 * u), H - 2.6 * u - 6.3 * u, w, 6.3 * u), label, lambda a=a: self.setup_go(a), ('u', 2.2, 600), INK if last else TEXT, FOCUS if last else PANEL, None, 1.4)

    def resting(self):
        """OLED care / Showcase screensaver: manually triggered (SAVER_NOW) or after configured idle minutes."""
        if getattr(self, 'SAVER_NOW', False) and not self.RUN:
            return True
        minutes = self.CFG.get('rest_min', 3)
        return bool(minutes) and not self.RUN and time.time() - self.active > minutes * 60

    def wake(self):  # True: this input only woke the screen up
        was = self.resting()
        self.active = time.time()
        if getattr(self, '_auto_bb_off', False):
            self._auto_bb_off = False
            restore_v = getattr(self, '_auto_bb_saved', 50)
            self.SET['bb'] = restore_v
            self.post('api/set', {'key': 'bb', 'value': restore_v, 'from': self.me})
            was = True
        if self.saver_timer.isActive():
            self.saver_timer.stop()
        if getattr(self, 'SAVER_NOW', False):
            self.SAVER_NOW = False
            self.post('api/saver', {'open': False})
        return was

    def _tick_saver(self):
        if not self.DOZE and self.resting():
            self.update()
        else:
            self.saver_timer.stop()

    def on_event(self, m):
        kind = m.get('kind')
        # a key that ends the rest only wakes the screen; news from the service (a game started, the other screen moved)
        # must still be taken over, or the bottom screen keeps showing the library instead of the game's deck
        if kind not in ('library', 'config') and self.wake() and kind == 'key': return self.update()
        if kind == 'toast': return self.toast(m.get('text', ''))
        if kind == 'launch_fx':
            self.LAUNCH_FX = {'title': m.get('title', ''), 'id': m.get('id', ''), 'at': time.time()}
            return self.update()
        if kind == 'trophy':
            if self.side == 'bottom':
                self.TROPHY = {'title': m.get('title', ''), 'desc': m.get('desc', ''), 'points': m.get('points', 0), 'at': time.time()}
                self.haptic()
                QTimer.singleShot(140, self.haptic)
            return self.update()
        if kind == 'mute': self.MUTED = bool(m.get('muted')); return self.update()
        if kind == 'saves': self.SAVES = m.get('saves'); return self.update()
        if kind == 'sysbackup':
            self.SYSBK = {
                'backups': m.get('backups') or {},
                'storage': m.get('storage') or {},
                'cleanup': m.get('cleanup') or {},
                'compress': m.get('compress') or {},
            }
            return self.update()
        if kind == 'updater':
            self.UPDC = {k: v for k, v in m.items() if k != 'kind'}
            return self.update()
        if kind == 'open_shrink':
            self.wake()
            if self.side == 'bottom':
                self.ask_shrink_android(int(m.get('gib') or 8))
            return self.update()
        if kind == 'dock': self.DOCK = m.get('dock'); return self.update()
        if kind == 'quick':  # the Thor key: its menu lives on the bottom screen
            if self.side == 'bottom': self.wake(); quick_view.toggle(self)
            return
        if kind == 'rec': self.REC = m.get('rec'); return self.update()
        if kind == 'library': return self.load()
        if kind == 'key':
            if self.POWER_OPEN:
                total = len(POWER_MENU) + 1
                if m['a'] == 'up': self.power_i = (self.power_i - 1) % total
                elif m['a'] == 'down': self.power_i = (self.power_i + 1) % total
                elif self.side == 'bottom' and m['a'] == 'back': self.post('api/action', {'name': 'power_close'})
                elif self.side == 'bottom' and m['a'] == 'ok': self.power_pick(self.power_i)
                return self.update()
            if self.playing() and (self.RUN.get('keys') or self.RUN['s'] == 'term'):
                if self.side == 'bottom':
                    cancel = (lambda: self.post('api/ytlogin', {'a': 'cancel'})) if self.RUN.get('login') else None
                    self.kb_key(m['a'], self.term_key, skip=(), cancel=cancel)
                return self.update()
            if self.PROMPT or self.PROMPT_OPEN:
                if self.side == 'bottom' and self.PROMPT:
                    self.kb_key(m['a'], self.prompt_key, skip=(29, 56, 1, 103, 105, 108, 106, 15, 58), cancel=self.cancel_prompt)
                return self.update()
            if self.GAME_MENU:
                if self.side == 'bottom': self.game_menu_key(m['a'])
                return self.update()
            if m['a'] == 'menu' and not self.playing() and not self.CONFIRM and not self.SETUP and not settings_view.open_now(self):
                if self.side == 'bottom': self.open_game_menu()
                return self.update()
            if self.playing() and (self.RUN.get('port') or {}).get('pad'):  # a media app: its deck has the controller (decks/media.py)
                if self.deck and hasattr(self.deck, 'key') and not self.PROMPT: self.deck.key(m['a'])
                return self.update()
            if m['a'] == 'home':
                self.SUB = ''
                if self.PROMPT: self.cancel_prompt()
            if m['a'] == 'search' and not self.playing() and not self.PROMPT and not self.CONFIRM and not self.SETUP:
                if self.side == 'bottom': self.open_search()
                return self.update()
            if self.side == 'bottom' and settings_view.open_now(self) and m['a'] == 'ok' and not self.PROMPT: settings_view.bottom_ok(self)  # typing happens down here
            if self.side == 'top':  # one window acts on the controller, the other follows through the service
                if m['a'] == 'home': self.S = {'tab': 0, 'sys': None, 'i': 0}; self.push()
                else: self.go(m['a'])
            return self.update()
        if kind == 'prompt':
            if m.get('from') != self.me: self.PROMPT_OPEN = bool(m.get('open'))
            return self.update()
        if kind == 'swkbd':
            self.PROMPT_OPEN = bool(m.get('open'))
            if self.side == 'bottom':
                if m.get('open'):
                    self.wake()
                    self.open_swkbd(m)
                elif self.PROMPT and self.PROMPT.get('swkbd_id') == m.get('id'):
                    self.PROMPT = None
            return self.update()
        if kind == 'confirm':
            if m.get('from') != self.me:
                if m.get('open') and m.get('action') in POWER: self.confirm_action(m['action'], remote=True)
                elif m.get('open') and self.RUN: self.confirm_quit(next((g for g in self.L['games'] if g['id'] == m.get('then')), None), remote=True)
                else: self.CONFIRM = None
            return self.update()
        if kind == 'config':
            self._cfg_seq += 1
            self.CFG = m['config']
            self.follow_theme()
            self.update()
            return self.pulse()
        if kind == 'thor': self.THOR = m.get('thor'); return self.update()
        if kind == 'ai_auth':
            self.AI_AUTH = m
            if self.side == 'bottom' and m.get('open'): self.wake()
            return self.update()
        if kind == 'saver':
            self.SAVER_NOW = bool(m.get('open'))
            if not self.SAVER_NOW: self.active = time.time()
            return self.update()
        if kind == 'settings':
            if m.get('from') != self.me and not self.drag: self.SET = m['settings']
            if m.get('osd'):
                self.OSD = m['settings'].get(m['osd'])
                self.timers['osd'].start(1600)
            return self.update()
        was_doze, self.DOZE = self.DOZE, bool(m.get('doze'))
        if was_doze and not self.DOZE: self.active = time.time()
        if m.get('power') and not self.POWER_OPEN: self.power_i = 0
        self.POWER_OPEN = bool(m.get('power'))
        self.PROMPT_OPEN = bool(m.get('prompt'))
        was, self.RUN = self.RUN, m.get('run')
        self.follow_setup(m.get('setup'))
        if m.get('from') != self.me: self.S = dict(m['ui'])
        if self.RUN:
            self.SAVER_NOW = False
            self.active = time.time()
        if self.RUN and (not was or was['id'] != self.RUN['id']): self.ACH = None; self.load_ach()
        if not self.RUN: self.ACH = None
        if self.deck is not None and (not self.RUN or not was or was['id'] != self.RUN['id']): self.drop_deck()
        if was and not self.RUN:
            self.SAVER_NOW = False
            self.active = time.time()
            self.load()  # play time and "last played" changed
        self.update()

    def follow_theme(self):  # the config names the look: take it over when it is another one (or overlays changed)
        want = self.CFG.get('theme') or 'toravo'
        ov_on = bool(self.CFG.get('overlays', True))
        if want != THEME['id']:
            self.set_theme(want)
        elif ov_on != self._last_overlays:
            self._last_overlays = ov_on
            self.comp_cache.clear()
            self.update()

    def set_theme(self, name):
        self._cfg_seq += 1
        self._last_overlays = bool(self.CFG.get('overlays', True))
        apply_theme(read_theme(name))
        self.fonts, self.svgs, self.backdrop = {}, {}, None
        self.comp_cache.clear()
        t_acc = self.game_accent(self.items()) or QColor(THEME['colors']['accent'])
        FOCUS.setRgba(t_acc.rgba())
        self.acc_anim = {'from_c': QColor(t_acc), 'to_c': QColor(t_acc), 'to': t_acc.rgba(), 't0': 0.0}
        self.update()

    def next_theme(self):
        looks = [t['id'] for t in self.CFG.get('themes') or []]
        if not looks: return
        name = looks[(looks.index(THEME['id']) + 1) % len(looks)] if THEME['id'] in looks else looks[0]
        self.set_theme(name)
        self.post('api/config', {'theme': name})  # the service stores it and tells the other screen

    def game_accent(self, items):
        """The colour of the game or app in front (running, else selected); None for the theme's own accent."""
        if not THEME['gameAccent']: return None
        it = next((g for g in self.L['games'] if g['id'] == self.RUN['id']), None) if self.playing() else items[self.S['i']] if items else None
        if not it or it.get('kind'): return None
        if it.get('s') in ('app', 'term'):
            c, bg = QColor(iisu_fx.app_profile(it)['accent']), QColor(THEME['colors']['bg'])
            return QColor(*readable((c.red(), c.green(), c.blue()), (bg.red(), bg.green(), bg.blue())))
        if not it.get('cover'): return None
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
        comp = self.RUN.get('companion')
        comp_mod = ({'d3': 'd3', 'p5r': 'p5r', 'zelda_la': 'zelda_decks', 'oot': 'zelda_decks',
                     'odyssey': 'mario_decks', 'wonder': 'mario_decks', 'mkworld': 'mario_decks',
                     'letsgo': 'world_decks', 'mania': 'world_decks', 'ffres': 'world_decks', 'tomodachi': 'world_decks',
                     'wow': 'classic_decks', 'sunshine': 'classic_decks', 'luigis_mansion': 'classic_decks',
                     'ttyd': 'classic_decks', 'mkdd': 'classic_decks', 'melee': 'classic_decks',
                     'ac_gc': 'classic_decks', 'crash_woc': 'classic_decks'}.get(comp)
                    if comp and not self.RUN.get('pack') and not self.RUN.get('dual') else None)
        name = (DECKS.get(str(self.RUN.get('appid')))
                or (self.RUN.get('port') or {}).get('deck')
                or ('pack' if self.RUN.get('pack') else None)
                or ('dualscreen' if self.RUN.get('dual') else None)
                or comp_mod
                or ('universal' if self.RUN.get('s') not in ('term',) and not self.RUN.get('keys') else None))
        deck_tag = f'pack:{self.RUN.get("pack")}' if name == 'pack' else (f'{name}:{comp}' if comp_mod and name == comp_mod else name)
        if not name: return False
        if self.deck is not None and (getattr(self, 'deck_name', None) is None or getattr(self, '_deck_id', None) != id(self.deck)):
            self.deck_name, self._deck_id = deck_tag, id(self.deck)
        elif getattr(self, 'deck_name', None) != deck_tag:
            if self.deck and self.deck is not False: self.deck.close()
            self.deck, self._deck_id = None, None
            self.deck_name = deck_tag
        if self.deck is False: return False
        if self.deck is None:
            try:
                self.deck = (importlib.import_module('decks.' + name), name)[0].Deck(self)
                self._deck_id = id(self.deck)
            except Exception as error:
                traceback.print_exc()
                self.deck, self._deck_id = False, None  # not again for this game
                self.toast(f'Begleiter lädt nicht: {error}')
                return False
        return self.deck.paint(p)

    def drop_deck(self):  # the game is over: its deck, the module and the pictures go
        if self.deck and self.deck is not False: self.deck.close()
        self.deck, self.deck_name, self._deck_id = None, None, None
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

    def _sort_games(self, seq):
        items_l = list(seq)
        L, mode = self.L, self.L.get('sort') or 'recent'
        last = lambda g: (L['played'].get(g['id']) or {}).get('last') or 0
        secs = lambda g: (L['played'].get(g['id']) or {}).get('secs') or 0
        yr = lambda g: int(g['year']) if str(g.get('year', '')).isdigit() else 0
        if mode == 'az': return sorted(items_l, key=lambda g: g['t'].lower())
        if mode == 'time': return sorted(items_l, key=lambda g: (-secs(g), -last(g), g['t'].lower()))
        if mode == 'year': return sorted(items_l, key=lambda g: (-yr(g), g['t'].lower()))
        if mode == 'short':
            short_hits = [g for g in items_l if 0 < float(g.get('ttb') or 0) <= 5.5]
            pool = short_hits if short_hits else items_l
            return sorted(pool, key=lambda g: (float(g.get('ttb') or 999), g['t'].lower()))
        return sorted(items_l, key=lambda g: (g['id'] not in L['fav'], -last(g), g['t'].lower()))

    def items(self):
        L, S, RUN = self.L, self.S, self.RUN
        games = [g for g in self.L['games'] if g.get('inst') != 'no']
        hidden = set(L.get('hidden') or [])
        if S.get('q'):
            words = S['q'].lower().split()
            last = lambda g: (L['played'].get(g['id']) or {}).get('last') or 0
            hit = lambda g: all(w in f'{g["t"]} {self.sys_name(g)} {g["s"]} {g.get("genre", "")} {g.get("dev", "")}'.lower() for w in words)
            return sorted((g for g in games if hit(g)), key=lambda g: (g['id'] in hidden, g['id'] not in L['fav'], -last(g), g['t']))
        if S['sys'] == '_hidden':
            return sorted((g for g in games if g['id'] in hidden), key=lambda g: g['t'].lower())
        if isinstance(S['sys'], str) and S['sys'].startswith('col:'):
            cname = S['sys'][4:]
            cset = set((L.get('collections') or {}).get(cname) or [])
            return self._sort_games(g for g in games if g['id'] in cset and g['id'] not in hidden)
        if S['sys']:
            return self._sort_games(g for g in games if g['s'] == S['sys'] and g['id'] not in hidden)
        if S['tab'] == 0:
            last = lambda g: (L['played'].get(g['id']) or {}).get('last') or 0
            held = next((g for g in games if g['id'] == RUN['id']), None) if RUN and RUN.get('paused') else None  # like the Switch: the suspended game stands in front
            pin_ids = [pid for pid in (L.get('pinned') or []) if pid not in hidden]
            by_id = {g['id']: g for g in games}
            pinned_games = [by_id[pid] for pid in pin_ids if pid in by_id and by_id[pid] is not held]
            pin_set = {g['id'] for g in pinned_games}
            rest = sorted((g for g in games if g['id'] not in hidden and g['id'] not in pin_set and (last(g) or g['id'] in L['fav']) and g is not held), key=lambda g: (-last(g), g['t']))[:30]
            return ([held] if held else []) + pinned_games + rest
        if S['tab'] == 1:
            sys_items = [{'id': 'sys:' + s, 't': v['name'], 's': s, 'kind': 'sys', 'n': v['n'], 'cover': v.get('cover'), 'hero': v.get('hero'), 'logo': v.get('logo')}
                         for s, v in L['systems'].items()]
            col_items = []
            for cname, gids in sorted((L.get('collections') or {}).items()):
                cnt = sum(1 for g in games if g['id'] in set(gids) and g['id'] not in hidden)
                if cnt:
                    sample = next((g for g in games if g['id'] in set(gids) and g.get('cover')), None)
                    col_items.append({'id': 'col:' + cname, 't': '★ ' + cname, 's': 'col:' + cname, 'kind': 'sys', 'n': cnt,
                                      'cover': sample.get('cover') if sample else None, 'hero': sample.get('hero') if sample else None})
            hid_cnt = sum(1 for g in games if g['id'] in hidden)
            hid_items = [{'id': 'sys:_hidden', 't': 'Ausgeblendet', 's': '_hidden', 'kind': 'sys', 'n': hid_cnt}] if hid_cnt else []
            return col_items + sys_items + hid_items
        if S['tab'] == 2: return sorted((g for g in games if g['s'] == 'steam' and g['id'] not in hidden), key=lambda g: (g.get('inst') == 'no', g.get('inst') != 'load'))  # loading first, then installed, then the rest
        if S['tab'] == 4: return []
        return [{'id': 'propad', 't': 'Pro-Controller (Mac & PC)', 's': 'app'},
                {'id': 'airplay:top', 't': 'AirPlay-Empfänger (Vollbild)', 's': 'app'},
                {'id': 'ai:claude', 't': 'Claude Code (Skip Permissions)', 's': 'app'},
                {'id': 'ai:agy', 't': 'Google Antigravity · agy (Skip Permissions)', 's': 'app'},
                {'id': 'term', 't': 'Terminal', 's': 'app'}, *L['apps'],
                *({'id': 'upd:' + e['id'], 't': e['name'] + (' aktualisieren' if e.get('installed') else ' installieren'), 's': 'app'} for e in L.get('extras') or []),
                {'id': 'act:steam', 't': 'Steam starten', 's': 'app'}, {'id': 'rescan', 't': 'Bibliothek neu einlesen', 's': 'app'}, {'id': 'act:desktop', 't': 'Zum Desktop', 's': 'app'}]

    def sys_name(self, it):
        s = it['s']
        if s == '_hidden': return 'Ausgeblendet'
        if isinstance(s, str) and s.startswith('col:'): return s[4:]
        if s == 'steam' and it.get('store'): return it['store']
        return 'Steam' if s == 'steam' else 'App' if s == 'app' else 'Linux-Shell' if s == 'term' else (self.L['systems'].get(s) or {'name': s})['name']

    def toast(self, text):
        self.TOAST = text
        if text: self.timers['toast'].start(6000)
        self.update()

    def push(self):
        self.update()
        with self.ui_lock:
            self.ui_out, start = {**self.S, 'from': self.me}, not self.ui_busy
            self.ui_busy = True
        if start: threading.Thread(target=self.send_ui, daemon=True).start()

    def send_ui(self):  # one sender, newest state last: parallel requests reached the service out of order on fast input
        while True:
            with self.ui_lock:
                data, self.ui_out = self.ui_out, None
                if data is None: self.ui_busy = False; return
            try: fetch('api/ui', data)
            except OSError: pass

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
        if self.CFG.get('ui_sounds') == 'subtle': self.post('api/sound', {'kind': 'launch'})
        self.ui_haptic()
        if it.get('s') not in ('app', 'term') and not it.get('kind'):
            self.LAUNCH_FX = {'title': it.get('t', ''), 'id': gid, 'at': time.time()}
            QTimer.singleShot(95, self.ui_haptic)
        self.post('api/launch', {'id': gid}, then=lambda r: r is None and self.toast('Tandem-Dienst antwortet nicht.'))

    def grid_cols(self):
        if self.S['tab'] in (1, 3) and not self.S['sys'] and not self.S.get('q'):
            return COLS
        c = int(self.CFG.get('grid_cols') or COLS)
        return c if c in (3, 4, 5, 6) else COLS

    def cycle_cols(self):
        order = (5, 4, 3, 6)
        cur = self.grid_cols()
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else 4
        self.CFG = {**self.CFG, 'grid_cols': nxt}
        self.off['grid'] = 0
        self.seen = None
        if self.CFG.get('ui_sounds') == 'subtle':
            self.post('api/sound', {'kind': 'zoom'})
        self.post('api/config', {'grid_cols': nxt})
        self.update()

    def go(self, a):
        items, S = self.items(), self.S
        n = len(items)
        if not settings_view.open_now(self): S['i'] = max(0, min(S['i'], n - 1))  # the settings keep their own row
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
        if settings_view.open_now(self) and a not in ('prev', 'next'): return settings_view.key(self, a)
        stage = self.stage_on(items)
        cols = self.grid_cols()
        if a == 'left': S['i'] = max(0, S['i'] - 1)
        elif a == 'right': S['i'] = min(n - 1, S['i'] + 1)
        elif a == 'up': S['i'] = max(0, S['i'] - cols) if stage else (S['i'] - cols if S['i'] >= cols else S['i'])
        elif a == 'down': S['i'] = min(n - 1, S['i'] + cols) if stage else (S['i'] + cols if S['i'] + cols < n else S['i'])
        elif a in ('prev', 'next'):
            S.pop('q', None)
            S.update(sys=None, tab=(S['tab'] + (1 if a == 'next' else len(TABS) - 1)) % len(TABS), i=0)
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
        elif a == 'back' and S.get('q'):
            S.pop('q', None); S['i'] = 0
        elif a == 'back' and S['sys']: S.update(i=list(self.L['systems']).index(S['sys']) if S['sys'] in self.L['systems'] else 0, sys=None, tab=1)
        if self.CFG.get('ui_sounds') == 'subtle' and a in ('left', 'right', 'up', 'down', 'prev', 'next', 'back', 'ok'):
            self.post('api/sound', {'kind': 'back' if a == 'back' else 'ok' if a == 'ok' else 'tick'})
        if a in ('left', 'right', 'up', 'down', 'prev', 'next', 'back', 'ok', 'fav'):
            self.ui_haptic()
        self.push()

    def ask(self, title, secret, done, initial=''):  # text entry without a real keyboard: the key grid fills a field on this screen
        self.PROMPT, self.KM, self.kb_rc, self.kb_pad = {'title': title, 'secret': secret, 'done': done, 'value': initial}, set(), (1, 0), False
        self.PROMPT_OPEN = True
        self.post('api/prompt', {'open': True, 'from': self.me})

    def open_swkbd(self, req):
        sid = req.get('id')
        def done(val):
            self.post('api/swkbd_done', {'id': sid, 'ok': True, 'text': val})
        self.PROMPT = {'title': req.get('title') or 'Text eingeben', 'secret': False, 'done': done,
                       'value': req.get('initial') or '', 'guide': req.get('guide') or '',
                       'min': int(req.get('min') or 0), 'max': int(req.get('max') or 0), 'swkbd_id': sid}
        self.KM, self.kb_rc, self.kb_pad = set(), (1, 0), False
        self.PROMPT_OPEN = True

    def finish_prompt(self, ok):
        P = self.PROMPT
        if not P: return
        sid = P.get('swkbd_id')
        if ok and P.get('min', 0) > 0 and len(P['value']) < P['min']:
            return self.toast(f'Mindestens {P["min"]} Zeichen eingeben.')
        if not ok and sid and P.get('min', 0) > 0:
            return self.toast('Name erforderlich – bitte eingeben und Fertig tippen.')
        self.PROMPT, self.PROMPT_OPEN = None, False
        if sid:
            if ok: P['done'](P['value'])
            else: self.post('api/swkbd_done', {'id': sid, 'ok': False, 'text': ''})
        else:
            self.post('api/prompt', {'open': False, 'from': self.me})
            if ok: P['done'](P['value'])

    def cancel_prompt(self):
        if self.PROMPT and self.PROMPT.get('swkbd_id'):
            return self.finish_prompt(False)
        self.PROMPT, self.PROMPT_OPEN = None, False
        self.post('api/prompt', {'open': False, 'from': self.me})

    def open_search(self):
        def done(value):
            q = value.strip()[:60]
            if q and self.S['tab'] in (3, 4): self.S['tab'] = 0
            if q: self.S['q'] = q
            else: self.S.pop('q', None)
            self.S['i'] = 0
            self.push()
        self.ask('Spiele durchsuchen', False, done, self.S.get('q', ''))
        self.update()

    def clear_search(self):
        self.S.pop('q', None)
        self.S['i'] = 0
        self.push()

    def toggle_mute(self, on=None):
        data = {'on': bool(on)} if isinstance(on, bool) else {}
        self.MUTED = bool(on) if isinstance(on, bool) else not self.MUTED
        self.post('api/mute', data, then=lambda r: r and setattr(self, 'MUTED', bool(r.get('muted'))))
        self.update()

    def set_gameopt(self, **kw):
        if not self.RUN: return
        for k in ('profile', 'fps', 'scale', 'res', 'shader'):
            if k in kw: self.RUN[k] = kw[k]
        self.post('api/gameopt', kw, then=lambda r: r and r.get('error') and self.toast(r['error']))
        self.update()

    def ask_save_target(self):
        def done(value):
            def saved(c):
                if c is None: return self.toast('Speichern fehlgeschlagen.')
                self.CFG = c
                self.toast(c.get('error') or 'Gespeichert.')
            self.post('api/config', {'save_target': value.strip()}, then=saved)
        self.ask('Sicherungsziel (SSH)', False, done, self.CFG.get('save_target', ''))
        self.update()

    def ask_restore_sysbackup(self, arc_file):
        def done(val):
            if val.strip().upper() not in ('JA', 'YES'):
                return self.toast('Abgebrochen.')
            self.toast('Stelle System-Sicherung wieder her …')
            self.post('api/sysbackup', {'action': 'restore', 'file': arc_file},
                      then=lambda r: (setattr(self, 'sysbk_at', 0),
                                      self.toast('Keine Antwort.' if r is None else r.get('error') or r.get('text', ''))))
        self.ask('„JA“ tippen zum Wiederherstellen', False, done, '')
        self.update()

    def ask_shrink_android(self, gib):
        def _submit(pw=None):
            payload = {'action': 'shrink_android', 'gib': int(gib)}
            if pw: payload['password'] = pw
            self.post('api/sysbackup', payload,
                      then=lambda r: (setattr(self, 'sysbk_at', 0),
                                      self.toast('Keine Antwort.' if r is None else r.get('error') or r.get('text', '')),
                                      self.update()))
        def _checked(r):
            if r is None: return self.toast('Tandem-Dienst antwortet nicht.')
            if r.get('need_password'):
                def _got_pw(pw):
                    if not pw: return self.toast('Abgebrochen.')
                    _submit(pw)
                self.ask(f'Linux-Passwort (Android auf {gib} GiB)', True, _got_pw, '')
                self.update()
            elif r.get('ok'):
                def _got_ok(val):
                    if val.strip().upper() not in ('JA', 'YES'):
                        return self.toast('Abgebrochen.')
                    _submit(None)
                self.ask(f'„JA“ tippen (Android auf {gib} GiB)', False, _got_ok, '')
                self.update()
            else:
                self.toast(r.get('error') or 'Nicht erlaubt.')
        self.post('api/sysbackup', {'action': 'check_sudo'}, then=_checked)

    def ask_wol_mac(self):
        def done(value):
            def saved(c):
                if c is None: return self.toast('Speichern fehlgeschlagen.')
                self.CFG = c
                self.toast(c.get('error') or 'Gespeichert.')
            self.post('api/config', {'wol_mac': value.strip()}, then=saved)
        self.ask('PC-MAC-Adresse (AA:BB:CC:DD:EE:FF)', False, done, self.CFG.get('wol_mac', ''))
        self.update()

    def ask_custom_feed(self):
        def done(value):
            val = value.strip()
            if not val:
                return
            self.post('api/updater', {'action': 'add_feed', 'repo': val},
                      then=lambda r: (setattr(self, 'updc_at', 0),
                                      r and self.toast(r.get('error') or r.get('text', ''))))
        self.ask('GitHub-Quelle (Besitzer/Projekt)', False, done, '')
        self.update()

    def ask_ai_workdir(self):
        def done(value):
            def saved(c):
                if c is None: return self.toast('Speichern fehlgeschlagen.')
                self.CFG = c
                self.toast(c.get('error') or 'Gespeichert.')
            self.post('api/config', {'ai_workdir': value.strip()}, then=saved)
        self.ask('KI-Arbeitsordner (leer = Home)', False, done, self.CFG.get('ai_workdir', ''))
        self.update()

    def cycle_sort(self):
        order = ('recent', 'az', 'time', 'year', 'short')
        cur = self.L.get('sort') or 'recent'
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else 'az'
        self.L['sort'] = nxt
        self.post('api/collection', {'a': 'sort', 'sort': nxt})
        self.update()

    def open_game_menu(self, it=None):
        if it is None:
            items = self.items()
            it = items[self.S['i']] if items and 0 <= self.S['i'] < len(items) else None
        if not it or it.get('kind') or it['s'] in ('app', 'term'):
            return
        self.GAME_MENU = {'id': it['id'], 'i': 0}
        self.update()

    def _game_menu_rows(self, g):
        L = self.L
        gid, s = g['id'], g['s']
        opt = (L.get('gameopt') or {}).get(gid) or {}
        emus = (L.get('emulators') or {}).get(s) or []
        rows = [('▶ Spiel starten', '', lambda: (setattr(self, 'GAME_MENU', None), self.start(g)))]
        if len(emus) > 1 and not g.get('native_engine'):
            cur_e = opt.get('emu', '')
            cur_lbl = next((e['label'] for e in emus if e['id'] == cur_e), 'Standard')
            ids = [''] + [e['id'] for e in emus]
            nxt_e = ids[(ids.index(cur_e) + 1) % len(ids)] if cur_e in ids else emus[0]['id']
            rows.append(('Emulator / Core', cur_lbl, lambda ne=nxt_e: self.post('api/gameopt', {'id': gid, 'emu': ne})))
        profs = [('', 'Standard'), ('Eco', 'Sparsam'), ('Balanced', 'Ausgewogen'), ('Performance', 'Leistung'), ('Turbo', 'Turbo')]
        cur_p = opt.get('profile', '')
        pids = [x[0] for x in profs]
        nxt_p = pids[(pids.index(cur_p) + 1) % len(pids)] if cur_p in pids else ''
        plbl = dict(profs).get(cur_p, 'Standard')
        rows.append(('Leistung (dieses Spiel)', plbl, lambda np=nxt_p: self.post('api/gameopt', {'id': gid, 'profile': np})))
        if s in ('steam', 'port'):
            res_opts = [(0, '1080p Nativ'), (900, '900p SGSR'), (720, '720p Max-FPS')]
            cur_r = int(opt.get('res') or 0)
            rids = [x[0] for x in res_opts]
            nxt_r = rids[(rids.index(cur_r) + 1) % len(rids)] if cur_r in rids else 0
            rlbl = dict(res_opts).get(cur_r, '1080p Nativ')
            rows.append(('Render-Auflösung', rlbl, lambda nr=nxt_r: self.post('api/gameopt', {'id': gid, 'res': nr})))
            for fkey, flbl in (('tu_deck_emu', 'Turnip Deck-Modus'), ('tu_sysmem', 'Turnip Sysmem-Fix'),
                               ('fex_tso', 'Strict TSO (Crash-Fix)'), ('fex_fast', 'FEX-Turbo (Fast-Math)')):
                fv = bool(opt.get(fkey))
                rows.append((flbl, 'An' if fv else 'Aus', lambda fk=fkey, nv=not fv: self.post('api/gameopt', {'id': gid, fk: nv})))
        is_pin = gid in (L.get('pinned') or [])
        rows.append(('An Start anpinnen', '✓ Angepinnt' if is_pin else 'Nein',
                     lambda: self.post('api/collection', {'a': 'pin', 'id': gid})))
        is_fav = gid in (L.get('fav') or [])
        rows.append(('Favorit', '★ Ja' if is_fav else 'Nein', lambda: self.post('api/fav', {'id': gid})))
        rows.append(('🎨 Cover & Bild wählen', '', lambda: self._open_art_picker(g)))
        if s not in ('steam', 'port', 'app', 'term') and not g.get('native_engine'):
            rows.append(('🧩 ROM-Patch anwenden (IPS/BPS)', '', lambda: self._open_patch_picker(g)))
            np_m = getattr(self, 'NETPLAY_MODE', 'off')
            np_lbl = 'Host aktiv' if np_m == 'host' else ('Beitreten' if np_m == 'join' else 'Aus')
            def _cycle_np():
                if np_m == 'off':
                    self.NETPLAY_MODE = 'host'
                    self.post('api/netplay', {'mode': 'host'}, then=lambda r: r and self.toast(r.get('text', '')))
                elif np_m == 'host':
                    self.ask('Host-IP im WLAN (RetroArch Netplay)', False,
                             lambda ip: ip.strip() and (setattr(self, 'NETPLAY_MODE', 'join'),
                                                        self.post('api/netplay', {'mode': 'join', 'host_ip': ip.strip()},
                                                                  then=lambda r: r and self.toast(r.get('error') or r.get('text', '')))))
                else:
                    self.NETPLAY_MODE = 'off'
                    self.post('api/netplay', {'mode': 'off'}, then=lambda r: r and self.toast(r.get('text', '')))
            rows.append(('🌐 LAN-Netplay (Koop)', np_lbl, _cycle_np))
        if s == 'switch' and not g.get('direct'):
            rows.append(('Nativ umwandeln (Peanuts)', 'Starten',
                         lambda: (setattr(self, 'GAME_MENU', None),
                                  self.post('api/switch_native', {'id': gid},
                                            then=lambda r: r and self.toast(r.get('error') or r.get('text', ''))))))
        for cname, gids in sorted((L.get('collections') or {}).items()):
            in_c = gid in gids
            rows.append((f'Sammlung: {cname}', '✓ Enthalten' if in_c else 'Hinzufügen',
                         lambda cn=cname: self.post('api/collection', {'a': 'toggle', 'name': cn, 'id': gid})))
        rows.append(('+ Neue Sammlung anlegen …', '',
                     lambda: self.ask('Name der Sammlung', False,
                                      lambda v: v.strip() and self.post('api/collection', {'a': 'create', 'name': v.strip(), 'id': gid}))))
        is_hid = gid in (L.get('hidden') or [])
        rows.append(('Wieder einblenden' if is_hid else 'Spiel ausblenden', '',
                     lambda: (setattr(self, 'GAME_MENU', None), self.post('api/collection', {'a': 'hide', 'id': gid}))))
        rows.append(('Schließen', '', lambda: setattr(self, 'GAME_MENU', None)))
        return rows

    def _open_art_picker(self, g, query=''):
        gm = self.GAME_MENU
        if not gm: return
        gm.update(art_picker=True, art_loading=True, art_items=[], art_has_custom=False, art_q=query, i=0)
        self.update()
        from urllib.parse import quote
        url = f'api/artwork?id={quote(g["id"])}' + (f'&q={quote(query)}' if query else '')
        def _got(r):
            if self.GAME_MENU is not gm: return
            gm['art_loading'] = False
            if isinstance(r, dict):
                gm['art_items'] = r.get('items') or []
                gm['art_has_custom'] = bool(r.get('has_custom'))
            self.update()
        self.call(url, then=_got)

    def _art_picker_rows(self, g):
        gm = self.GAME_MENU or {}
        rows = [
            ('‹ Zurück zu Optionen', '', lambda: (gm.update(art_picker=False, i=0), self.update())),
            ('Titel manuell suchen …', gm.get('art_q') or g['t'],
             lambda: self.ask('Spieltitel für Cover-Suche', False, lambda v: v.strip() and self._open_art_picker(g, v.strip()))),
        ]
        if gm.get('art_has_custom'):
            rows.append(('↺ Standard-Cover wiederherstellen', '',
                         lambda: (self.toast('Stelle Standard-Cover wieder her …'),
                                  self.post('api/artwork', {'id': g['id'], 'action': 'reset'},
                                            then=lambda r: (self.toast((r or {}).get('error') or (r or {}).get('text', '')),
                                                            self._open_art_picker(g, gm.get('art_q', '')))))))
        if gm.get('art_loading'):
            rows.append(('Suche Cover & Hero-Bilder …', '', lambda: None))
        elif not gm.get('art_items'):
            rows.append(('Keine passenden Bilder gefunden', 'Titel oben anpassen', lambda: None))
        else:
            for cand in gm['art_items']:
                slot = cand.get('slot', 'cover')
                act_lbl = 'Als Hero setzen' if slot == 'hero' else 'Als Cover setzen'
                rows.append((cand.get('label') or 'Cover', act_lbl,
                             lambda u_c=cand['url'], sl=slot: (
                                 self.toast('Lade & speichere Bild …'),
                                 self.post('api/artwork', {'id': g['id'], 'action': 'apply', 'url': u_c, 'slot': sl},
                                           then=lambda r: (self.toast((r or {}).get('error') or (r or {}).get('text', '')),
                                                           setattr(self, 'GAME_MENU', None) if (r or {}).get('ok') else None)))))
        return rows

    def _open_patch_picker(self, g):
        gm = self.GAME_MENU
        if not gm: return
        gm.update(patch_picker=True, patch_loading=True, patch_items=[], i=0)
        self.update()
        from urllib.parse import quote
        def _got(r):
            if self.GAME_MENU is not gm: return
            gm['patch_loading'] = False
            gm['patch_items'] = (r or {}).get('items') or []
            self.update()
        self.call(f'api/patch?id={quote(g["id"])}', then=_got)

    def _patch_picker_rows(self, g):
        gm = self.GAME_MENU or {}
        rows = [('‹ Zurück zu Optionen', '', lambda: (gm.update(patch_picker=False, i=0), self.update()))]
        if gm.get('patch_loading'):
            rows.append(('Suche Patch-Dateien (.ips / .bps / .ups / .xdelta) …', '', lambda: None))
        elif not gm.get('patch_items'):
            rows.append(('Keine Patch-Dateien gefunden', 'In ROMs/patches oder Downloads ablegen', lambda: None))
        else:
            for pt in gm['patch_items']:
                rows.append((pt['name'], f'{pt["kb"]:g} KB · Anwenden',
                             lambda pp=pt['path']: (
                                 self.toast('Wende ROM-Patch an …'),
                                 self.post('api/patch', {'id': g['id'], 'patch': pp},
                                           then=lambda r: (self.toast((r or {}).get('error') or (r or {}).get('text', '')),
                                                           setattr(self, 'GAME_MENU', None) if (r or {}).get('ok') else None)))))
        return rows

    def game_menu_key(self, a):
        gm = self.GAME_MENU
        if not gm: return
        g = next((x for x in self.L['games'] if x['id'] == gm['id']), None)
        if not g:
            self.GAME_MENU = None; return
        rows = (self._art_picker_rows(g) if gm.get('art_picker')
                else self._patch_picker_rows(g) if gm.get('patch_picker')
                else self._game_menu_rows(g))
        if a == 'up': gm['i'] = (gm['i'] - 1) % len(rows)
        elif a == 'down': gm['i'] = (gm['i'] + 1) % len(rows)
        elif a == 'back' and (gm.get('art_picker') or gm.get('patch_picker')):
            gm.update(art_picker=False, patch_picker=False, i=0)
        elif a in ('back', 'close', 'menu'): self.GAME_MENU = None
        elif a == 'ok' and rows: rows[min(gm['i'], len(rows) - 1)][2]()

    def power_pick(self, idx):
        self.POWER_OPEN = False
        if idx >= len(POWER_MENU):
            self.post('api/action', {'name': 'power_close'})
            return
        name, _, confirm = POWER_MENU[idx]
        if confirm:
            self.post('api/action', {'name': 'power_close'})
            self.confirm_action(name)
        else:
            self.post('api/action', {'name': name}, then=lambda r: r and r.get('error') and self.toast(r['error']))

    def key_label(self, code, layout):
        if code in KB_NAME: return KB_NAME[code]
        if code == 86: return ('|' if 'altgr' in self.KM else '>' if 'shift' in self.KM else '<') if layout == 'de' else '\\'
        if 'altgr' in self.KM and code in KB_ALTGR.get(layout, {}): return KB_ALTGR[layout][code]
        for r, row in enumerate(KB_ROWS):
            if code in row: return KB[layout][r + (4 if 'shift' in self.KM else 0)][row.index(code)]
        return ''

    def prompt_key(self, code):
        P = self.PROMPT
        if not P: return
        if code in (42, 100): self.KM ^= {KB_MODS[code]}
        elif code == 14: P['value'] = P['value'][:-1]
        elif code == 28:
            self.finish_prompt(True)
        else:
            ch = ' ' if code == 57 else self.key_label(code, 'us' if self.CFG.get('kb_layout') == 'us' else 'de')
            if not P.get('max') or len(P['value']) + len(ch) <= P['max']:
                P['value'] += ch
            self.KM -= {'shift', 'altgr'}

    def kb_key(self, a, press, skip=(), cancel=None):
        """Controller navigation on the on-screen keyboard: D-pad moves, A types, X deletes, Y adds a space, B cancels."""
        rows = [[c for c in row if c not in skip] for row in KB_CODES]
        rows = [r for r in rows if r]
        if not rows: return
        r, c = self.kb_rc
        r = max(0, min(len(rows) - 1, r))
        c = max(0, min(len(rows[r]) - 1, c))
        if a in ('up', 'down', 'left', 'right'):
            self.kb_pad = True
            if a == 'left': c = (c - 1) % len(rows[r])
            elif a == 'right': c = (c + 1) % len(rows[r])
            else:
                nr = max(0, min(len(rows) - 1, r + (1 if a == 'down' else -1)))
                c = round(c * (len(rows[nr]) - 1) / max(1, len(rows[r]) - 1)) if len(rows[nr]) > 1 else 0
                r = nr
            self.kb_rc = (r, c)
        elif a == 'ok':
            self.kb_pad = True
            code = rows[r][c]
            self.haptic()
            hit = next(((kr, kc, kl, _, _) for kr, kc, kl, _, _ in self.kb_keys if kc == code), None)
            if hit:
                self.kb_flash = (code, hit[2], hit[0], time.time())
                QTimer.singleShot(135, self.update)
            press(code)
        elif a == 'close': self.haptic(); press(14)  # X: Backspace
        elif a == 'fav': self.haptic(); press(57)    # Y: Space
        elif a == 'back' and cancel: cancel()

    def haptic(self):
        if self.CFG.get('kb_haptics', True): HAPTICS.tap()

    def ui_haptic(self):
        if self.CFG.get('ui_haptics', True): HAPTICS.tap()

    def _rgb_cover_allowed(self):
        rm = self.CFG.get('rgb_mode') or ('cover' if self.CFG.get('rgb_sync', True) else 'static')
        return rm == 'cover' or (rm == 'ambilight' and not self.playing())

    def _queue_rgb(self, hex_color):
        if self.side != 'bottom' or not self._rgb_cover_allowed(): return
        if self.THOR and self.THOR.get('rgb') and not self.THOR['rgb'].get('enabled'): return
        hc = str(hex_color or '').lstrip('#').upper()
        if len(hc) != 6 or hc == self._rgb_last or hc == self._rgb_pending: return
        self._rgb_pending = hc
        self.rgb_timer.start(280)

    def _flush_rgb(self):
        hc = self._rgb_pending
        self._rgb_pending = None
        if not hc or hc == self._rgb_last or not self._rgb_cover_allowed(): return
        if self.THOR and self.THOR.get('rgb') and not self.THOR['rgb'].get('enabled'): return
        self._rgb_last = hc
        self.post('api/thor', {'rgb': {'color': hc, 'enabled': True}})

    def pick_random(self):
        """Jumps to a random installed game in the current list (or across the library) with a haptic click."""
        items = self.items()
        pool = [(idx, it) for idx, it in enumerate(items) if not it.get('kind') and it.get('s') not in ('app', 'term') and it.get('inst') != 'no']
        if len(pool) > 1:
            pool = [x for x in pool if x[0] != self.S.get('i')]
        if pool:
            idx, pick = random.choice(pool)
            self.S['i'] = idx
            self.ui_haptic()
            self.toast(f'Zufall: {pick["t"]}')
            self.push()
            return
        all_g = [g for g in (self.L.get('games') or []) if g.get('s') not in ('app', 'term') and g.get('inst') != 'no' and g['id'] not in (self.L.get('hidden') or ())]
        if not all_g:
            return self.toast('Keine Spiele gefunden.')
        pick = random.choice(all_g)
        self.S = {'tab': 1, 'sys': pick['s'], 'i': 0}
        sys_items = self.items()
        for idx, it in enumerate(sys_items):
            if it.get('id') == pick['id']:
                self.S['i'] = idx
                break
        self.ui_haptic()
        self.toast(f'Zufall: {pick["t"]}')
        self.push()

    def _kb_repeat_tick(self):
        if not self.kb_down or self.kb_down[1] != 14:
            self.kb_rep.stop()
            return
        self.kb_rep.setInterval(65)
        self.haptic()
        self.kb_down[4](14)
        self.update()

    def term_key(self, code):
        if code in KB_MODS: self.KM ^= {KB_MODS[code]}; return
        if code == -2:
            self.KM = set()
            self.post('api/key', {'seq': '@'}, then=lambda r: r and r.get('error') and self.toast(r['error']))
            return
        lay = (self.RUN or {}).get('layout')
        text = self.key_label(code, lay if lay in KB else ('us' if self.CFG.get('kb_layout') == 'us' else 'de'))
        self.post('api/key', {'code': code, 'mods': sorted(self.KM), 'text': text}, then=lambda r: r and r.get('error') and self.toast(r['error']))
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
        self.ask({'ra_user': 'Benutzername bei RetroAchievements', 'ra_password': 'Passwort bei RetroAchievements', 'ra_key': 'Web-API-Schlüssel',
                  'bnet_email': 'E-Mail bei Battle.net', 'bnet_password': 'Passwort bei Battle.net'}[key], key not in ('ra_user', 'bnet_email'), done)

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
        if self.DOZE: return
        if self.wake(): return self.push()  # push: the other screen wakes up too
        if self.playing() and self.RUN['s'] == 'term': return  # keys belong to the terminal
        K = Qt.Key
        if e.key() == K.Key_S and not self.playing() and not self.PROMPT and not self.CONFIRM and not self.SETUP and not self.POWER_OPEN:
            if self.side == 'bottom': self.open_search()
            return
        a = {K.Key_Left: 'left', K.Key_Right: 'right', K.Key_Up: 'up', K.Key_Down: 'down', K.Key_Return: 'ok', K.Key_Enter: 'ok', K.Key_Escape: 'back',
             K.Key_Q: 'prev', K.Key_E: 'next', K.Key_F: 'fav', K.Key_X: 'close'}.get(e.key())
        if a and self.POWER_OPEN:
            total = len(POWER_MENU) + 1
            if a == 'up': self.power_i = (self.power_i - 1) % total
            elif a == 'down': self.power_i = (self.power_i + 1) % total
            elif a == 'back': self.post('api/action', {'name': 'power_close'})
            elif a == 'ok': self.power_pick(self.power_i)
            return self.update()
        if a: self.go(a)

    def _tick_kinetic(self):
        kin = self.kinetic
        if not kin:
            self.kinetic_timer.stop()
            return
        now = time.time()
        dt = max(0.001, min(0.05, now - kin['t']))
        kin['t'] = now
        key = kin['key']
        mx = self.maxoff.get(key, 0)
        cur = self.off.get(key, 0)
        nxt = max(0.0, min(mx, cur + kin['v'] * dt))
        self.off[key] = nxt
        self.scroll_touch_at[key] = now
        kin['v'] *= 0.915 ** (dt * 60.0)
        if abs(kin['v']) < 18.0 or (nxt <= 0.0 and kin['v'] < 0) or (nxt >= mx and kin['v'] > 0):
            self.kinetic = None
            self.kinetic_timer.stop()
        self.update()

    def _on_long_press(self):
        if self.press is None or self.moved or self.drag or self.lp_target is None:
            return
        idx = self.lp_target
        items = self.items()
        if not (0 <= idx < len(items)):
            return
        it = items[idx]
        if it.get('kind') or it.get('s') in ('app', 'term'):
            return
        self.lp_fired = True
        self.press_rect = None
        self.haptic()
        if self.S.get('i') != idx:
            self.S['i'] = idx
            self.push()
        self.open_game_menu(it)

    def wheelEvent(self, e):
        if self.DOZE or self.wake(): return
        pos = e.position()
        dy = e.angleDelta().y()
        if not dy: return
        sc = next((entry for entry in reversed(self.scrolls) if entry[0].contains(pos)), None)
        if sc:
            _, key, zoom = sc
            self.kinetic = None
            self.off[key] = max(0, min(self.maxoff.get(key, 0), self.off.get(key, 0) - (dy * 0.75) / zoom))
            self.scroll_touch_at[key] = time.time()
            self.update()
        elif self.side == 'bottom' and self.stage_on():
            items = self.items()
            if items:
                self.S['i'] = max(0, min(len(items) - 1, self.S['i'] + (-1 if dy > 0 else 1)))
                self.push()

    def mousePressEvent(self, e):
        if self.DOZE: return
        if self.wake(): return self.push()
        pos = e.position()
        now = time.time()
        self.press, self.moved, self.last = pos, False, pos.y()
        self.vel_samples = [(now, pos.x(), pos.y())]
        self.lp_timer.stop()
        self.lp_target, self.lp_fired = None, False
        self.stage_drag = None
        # Tap on a fast-coasting scroller stops momentum cleanly without firing an accidental tile tap
        if self.kinetic and abs(self.kinetic.get('v', 0)) > 115:
            sc_hit = next((entry for entry in reversed(self.scrolls) if entry[0].contains(pos)), None)
            if sc_hit and sc_hit[1] == self.kinetic['key']:
                self.stopped_kinetic = True
                self.kinetic = None
                self.kinetic_timer.stop()
            else:
                self.stopped_kinetic = False
        else:
            self.stopped_kinetic = False
            if self.kinetic:
                self.kinetic = None
                self.kinetic_timer.stop()
        khit = next((k for k in reversed(self.kb_keys) if k[0].contains(pos)), None)
        if khit is not None:
            self.kb_pad = False
            self.kb_down = khit
            self.haptic()
            if khit[1] == 14:  # Backspace fires immediately on press and repeats smoothly when held
                khit[4](14)
                self.kb_rep.start(340)
            self.update()
            return
        dhit = next(((fn, drag) for rect, fn, drag, _ in reversed(self.hits) if drag and rect.contains(pos)), None)
        self.drag = dhit[0] if dhit else None
        self.drag_kind = dhit[1] if dhit else None
        self.scrolling = next((entry for entry in reversed(self.scrolls) if entry[0].contains(pos)), None)
        if self.drag:
            self.drag(pos.y() if self.drag_kind == 'y' else pos.x())
            self.press_rect = None
        else:
            phit = next((rect for rect, _, drag, _ in reversed(self.hits) if not drag and rect.contains(pos)), None)
            self.press_rect = phit
            # Arm 420ms long-press on game tiles to open per-game options menu
            if (self.side == 'bottom' and not self.playing() and not self.PROMPT and not self.CONFIRM
                    and not self.QUICK and not self.GAME_MENU and not self.POWER_OPEN and not self.stopped_kinetic):
                t_idx = next((idx for trect, idx in reversed(self.tile_rects) if trect.contains(pos)), None)
                if t_idx is not None:
                    self.lp_target = t_idx
                    self.lp_timer.start(420)
        if self.deck and hasattr(self.deck, 'press'): self.deck.press(pos)
        if self.press_rect is not None: self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        now = time.time()
        if self.kb_down is not None:
            khit = next((k for k in reversed(self.kb_keys) if k[0].contains(pos)), None)
            if khit is not None and khit[1] != self.kb_down[1] and self.kb_down[1] != 14:
                self.kb_down = khit
                self.haptic()
                self.update()
            return
        if self.press is None: return
        self.vel_samples.append((now, pos.x(), pos.y()))
        cutoff = now - 0.10
        while len(self.vel_samples) > 2 and self.vel_samples[0][0] < cutoff:
            self.vel_samples.pop(0)
        dx, dy = pos.x() - self.press.x(), pos.y() - self.press.y()
        if abs(dx) > 1.25 * self.u or abs(dy) > 1.25 * self.u:
            self.lp_timer.stop()
            if self.press_rect is not None:
                self.press_rect = None
                self.update()
        if self.deck and hasattr(self.deck, 'move') and self.deck.move(pos): return
        if self.drag:
            return self.drag(pos.y() if self.drag_kind == 'y' else pos.x())
        # Live 1:1 horizontal finger drag on the Stage Carousel (`Bühne`)
        if (self.side == 'bottom' and not self.playing() and not self.PROMPT and not self.CONFIRM
                and not self.QUICK and not self.GAME_MENU and self.stage_on()):
            if self.stage_drag is not None or (abs(dx) > 1.4 * self.u and abs(dx) > abs(dy) and self.press.y() > 8.5 * self.u):
                items = self.items()
                if items:
                    self.moved = True
                    step = max(8.0 * self.u, 21.0 * self.u)
                    if self.stage_drag is None:
                        self.stage_drag = {'start_i': float(self.S['i']), 'pos': float(self.S['i']), 'step': step}
                    raw_pos = max(0.0, min(float(len(items) - 1), self.stage_drag['start_i'] - dx / self.stage_drag['step']))
                    self.stage_drag['pos'] = raw_pos
                    near_i = int(round(raw_pos))
                    if near_i != self.S['i']:
                        self.S['i'] = near_i
                        self.haptic()
                        self.push()
                    self.update()
                    return
        if self.scrolling and (self.moved or (abs(dy) > 1.35 * self.u and abs(dy) >= abs(dx) * 0.7)):
            self.moved = True
            _, key, zoom = self.scrolling
            if key == 'grid': self.scroll_anim = None
            self.off[key] = max(0, min(self.maxoff.get(key, 0), self.off.get(key, 0) - (pos.y() - self.last) / zoom))
            self.scroll_touch_at[key] = now
            self.last = pos.y()
            self.update()

    def mouseReleaseEvent(self, e):
        pos, self.press = self.press, None
        self.lp_timer.stop()
        had_press_rect = self.press_rect is not None
        self.press_rect = None
        if self.kb_down is not None:
            self.kb_rep.stop()
            krect, code, label, _, press_fn = self.kb_down
            self.kb_down = None
            rel_pos = e.position()
            inside = krect.adjusted(-2 * self.u, -2 * self.u, 2 * self.u, 2 * self.u).contains(rel_pos)
            if inside:
                self.kb_flash = (code, label, krect, time.time())
                QTimer.singleShot(135, self.update)
                if code != 14: press_fn(code)
            self.update()
            return
        if self.deck and hasattr(self.deck, 'press'): self.deck.press(None)
        if self.lp_fired:
            self.lp_fired = False
            self.drag = self.drag_kind = None
            self.update()
            return
        rel = e.position()
        # Compute finger release velocity (vx, vy in px/s)
        vx = vy = 0.0
        if len(self.vel_samples) >= 2:
            dt = self.vel_samples[-1][0] - self.vel_samples[0][0]
            if dt > 0.008:
                vx = (self.vel_samples[-1][1] - self.vel_samples[0][1]) / dt
                vy = (self.vel_samples[-1][2] - self.vel_samples[0][2]) / dt
        # Finish Stage Carousel horizontal drag / flick
        if self.stage_drag is not None:
            sd = self.stage_drag
            self.stage_drag = None
            items = self.items()
            if items:
                proj = sd['pos'] - (vx * 0.16) / sd['step']
                target_i = max(0, min(len(items) - 1, int(round(proj))))
                self.stage_anim.update({'from': sd['pos'], 'to': float(target_i), 't0': time.time()})
                if target_i != self.S['i']:
                    self.S['i'] = target_i
                    self.haptic()
                self.push()
            self.update()
            return
        if self.drag:
            self.drag = self.drag_kind = None
            if had_press_rect: self.update()
            return
        if pos is None:
            return
        dx, dy = rel.x() - pos.x(), rel.y() - pos.y()
        # Edge & swipe gestures when no scroll/button drag claimed the gesture
        if not self.PROMPT and not self.POWER_OPEN:
            # 1) Swipe down from top bezel of bottom screen -> toggle Thor Bento Quick Menu
            if self.side == 'bottom' and pos.y() < 3.1 * self.u and dy > 6.5 * self.u and abs(dx) < dy * 0.75:
                self.haptic()
                quick_view.toggle(self)
                return
            # 2) Swipe up from bottom edge while Quick Menu is open -> close Quick Menu
            if self.side == 'bottom' and self.QUICK and pos.y() > self.height() - 6.0 * self.u and dy < -6.0 * self.u:
                self.haptic()
                quick_view.close(self)
                return
            # 3) Universal left-edge swipe-back on bottom screen
            if self.side == 'bottom' and pos.x() < 3.4 * self.u and dx > 7.0 * self.u and abs(dy) < dx * 0.68:
                if self.QUICK:
                    self.haptic(); quick_view.close(self); return
                if self.GAME_MENU:
                    self.haptic(); self.GAME_MENU = None; self.update(); return
                if settings_view.open_now(self):
                    self.haptic(); self.post('api/uikey', {'a': 'back'}); return
                if self.S.get('sys') or self.S.get('q'):
                    self.haptic(); self.post('api/uikey', {'a': 'back'}); return
            # 4) Horizontal swipe on Top Screen when browsing games -> step previous/next game
            if (self.side == 'top' and not self.playing() and not self.CONFIRM
                    and not settings_view.open_now(self) and abs(dx) > 9.0 * self.u and abs(dx) > abs(dy) * 1.5):
                self.haptic()
                self.go('right' if dx < 0 else 'left')
                return
        if self.moved:
            # Start smooth 120 Hz kinetic momentum on the active scroller!
            if self.scrolling and abs(vy) > 155.0:
                _, key, zoom = self.scrolling
                self.kinetic = {'key': key, 'v': max(-4200.0, min(4200.0, -vy / zoom)), 't': time.time()}
                if not self.kinetic_timer.isActive():
                    self.kinetic_timer.start()
            if had_press_rect: self.update()
            return
        if self.stopped_kinetic:
            self.stopped_kinetic = False
            return
        # Exact hit first, then forgiving 1.1u nearest-target touch slop so slightly off-edge taps never miss!
        fn = next((fn for rect, fn, drag, _ in reversed(self.hits) if not drag and rect.contains(pos)), None)
        if fn is None:
            slop = 1.1 * self.u
            best_d2 = (slop * 3.5) ** 2
            for rect, cand_fn, drag, _ in reversed(self.hits):
                if not drag and rect.adjusted(-slop, -slop, slop, slop).contains(pos):
                    c = rect.center()
                    d2 = (pos.x() - c.x()) ** 2 + (pos.y() - c.y()) ** 2
                    if d2 < best_d2:
                        best_d2, fn = d2, cand_fn
        if fn:
            self.haptic()
            fn()
            self.update()
        elif had_press_rect:
            self.update()

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

    def tr(self, text): return lang.tr(text) if self.CFG.get('lang') == 'en' else text  # every text passes here: see lang.py

    def width_of(self, text, f): return self.font(*f)[1].horizontalAdvance(self.tr(text))

    def wrap(self, text, f, w, lines=None):
        fm, out, line, text = self.font(*f)[1], [], '', self.tr(text)
        for word in text.split():
            trial = f'{line} {word}' if line else word
            if line and fm.horizontalAdvance(trial) > w: out.append(line); line = word
            else: line = trial
        out.append(line)
        if lines and len(out) > lines: out = out[:lines - 1] + [' '.join(out[lines - 1:])]
        return [fm.elidedText(l, Qt.TextElideMode.ElideRight, w) for l in out]

    def text(self, p, text, x, y, f, color, w=None, align=0, lh=1.2, lines=1):
        """Draws text with its top at y (align 0 left, 1 centre, 2 right inside w; wraps when lines != 1). Returns its height."""
        font, fm, text = *self.font(*f), self.tr(text)
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

    def button(self, p, rect, label, fn, f, fg=TEXT, bg=RAISED, border=None, radius=1.2, name=None):
        self.box(p, rect, min(rect.height() / 2, radius * 1.5 * self.u), bg, border)
        self.text(p, label, rect.x(), rect.y(), f, fg, rect.width(), 1, rect.height() / (f[1] * self.u))
        self.hit(rect, fn, name=name or label)

    def icon(self, p, name, rect, color):
        if not QSvgRenderer: return
        key = (name, color.name())
        if key not in self.svgs:
            self.svgs[key] = QSvgRenderer(QByteArray(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{ICONS[name].replace("currentColor", color.name())}</svg>'.encode()))
        self.svgs[key].render(p, rect)

    def dur(self, secs): return secs * (.25 if self.CFG.get('motion') == 'reduced' else 1.0)

    def ease(self, start, secs):
        """0 … 1 (eased out) since start. Asks for the next frame only while it runs: when nothing moves, nothing repaints."""
        if secs <= 0: return 1.0
        t = (time.time() - start) / secs
        if t >= 1: return 1.0
        QTimer.singleShot(16, self.update)
        return 1 - (1 - max(0.0, t)) ** 3

    def lerp_color(self, a, b, t):
        if a is None or t >= 1: return b
        if t <= 0: return a
        return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                      round(a.blue() + (b.blue() - a.blue()) * t), round(a.alpha() + (b.alpha() - a.alpha()) * t))

    def stage_on(self, items=None):
        """Cocoon stage (carousel showcase) when chosen for game lists; system folders and apps stay in the grid."""
        return (self.CFG.get('view_mode') == 'stage' and not settings_view.open_now(self)
                and (self.S.get('q') or self.S['sys'] or self.S['tab'] in (0, 2)) and (items is None or bool(items)))

    def toggle_view(self):
        mode = 'grid' if self.CFG.get('view_mode') == 'stage' else 'stage'
        self.CFG = {**self.CFG, 'view_mode': mode}
        self.post('api/config', {'view_mode': mode})
        self.update()

    def capsule(self, p, rect, fill, border=None):  # always fully round, whatever the theme's radius
        p.setPen(QPen(border, 1) if border else Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

    def glyph_wifi(self, p, cx, base, size, signal, color):
        """Wi-Fi as a dot and two arcs (line icon); signal 0-100 lights 1-3 of them, None: no Wi-Fi link at all."""
        bars = 0 if not signal else 3 if signal >= 65 else 2 if signal >= 40 else 1
        dim = faded(color, color.alphaF() * .3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for n, r in enumerate((.62, 1.0)):
            p.setPen(QPen(color if bars >= n + 2 else dim, .15 * size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(QRectF(cx - r * size, base - r * size, 2 * r * size, 2 * r * size), 48 * 16, 84 * 16)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(color if bars else dim)
        dot = QPainterPath(QPointF(cx, base))
        dot.arcTo(QRectF(cx - .3 * size, base - .3 * size, .6 * size, .6 * size), 45, 90)
        dot.closeSubpath()
        p.drawPath(dot)

    def glyph_battery(self, p, x, mid, h, level, charging, color):
        """A battery outline filled to the level; green while charging (with a bolt), red when low."""
        w, line = 2.05 * h, .09 * h
        body = QRectF(x, mid - h / 2, w, h)
        p.setPen(QPen(faded(color, color.alphaF() * .55), line)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(body, .3 * h, .3 * h)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(faded(color, color.alphaF() * .55))
        p.drawRoundedRect(QRectF(body.right() + .07 * h, mid - .18 * h, .12 * h, .36 * h), .06 * h, .06 * h)
        inner = body.adjusted(.17 * h, .17 * h, -.17 * h, -.17 * h)
        fill = LIVE if charging else WARN if level <= 20 else color
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(inner.x(), inner.y(), max(inner.height() * .5, inner.width() * max(0, min(100, level)) / 100), inner.height()), .14 * h, .14 * h)
        if charging:
            bolt = QPainterPath()
            pts = [(.56, -.08), (.22, .56), (.47, .56), (.42, 1.08), (.8, .4), (.54, .4), (.62, -.08)]
            bolt.moveTo(body.x() + pts[0][0] * w, body.y() + pts[0][1] * h)
            for bx, by in pts[1:]: bolt.lineTo(body.x() + bx * w, body.y() + by * h)
            bolt.closeSubpath()
            p.setPen(QPen(QColor(0, 0, 0, 200), .1 * h)); p.setBrush(QColor(255, 255, 255, round(color.alphaF() * 255)))
            p.drawPath(bolt)
        return w + .2 * h

    def status_bar(self, p, items=()):
        """Symmetrical Console Header on the top screen: channel capsule on top-left + date, time, Wi-Fi and battery on
        top-right. Gentle 5-minute pixel shift protects OLED pixels while keeping both capsules aligned on one axis."""
        u, W = self.u, self.width()
        spot = random.Random(int(time.time() // 300)).random
        dx, dy = (spot() - .5) * .6 * u, (spot() - .5) * .45 * u
        iisu_fx.draw_top_header(self, p, items, dx, dy)
        ink, dim, f, fb = rgba(241, 245, 249, .92), rgba(203, 213, 225, .68), ('u', 1.3, 400), ('u', 1.32, 700)
        t = time.localtime()
        date = f'{WEEKDAYS[t.tm_wday]} {t.tm_mday}. {MONTHS[t.tm_mon - 1]}'
        batt = f'{self.BATT["level"]} %' if self.BATT else ''
        bta = getattr(self, 'BT_AUDIO', None) or {}
        bt_txt = (f'🎧 {bta["battery_pct"]} %' if bta.get('active') and bta.get('battery_pct') is not None
                  else '🎧' if bta.get('active') else '')
        h, pad, ic = 3.15 * u, 1.45 * u, 1.05 * u
        w = (pad + self.width_of(date, f) + .8 * u + self.width_of(clock(), fb) + 1.6 * u
             + (self.width_of(bt_txt, f) + 1.2 * u if bt_txt else 0)
             + (1.9 * u + 1.2 * u if self.WIFI is not None else 0)
             + ((self.width_of(batt, f) + .6 * u + 2.05 * ic + .2 * ic) if self.BATT else 0) + pad)
        rect = QRectF(W - 4.2 * u - w + dx, 1.85 * u + dy, w, h)
        if iisu_fx.era_mode() in ('8bit', '16bit'):
            iisu_fx.glass_card(self, p, rect, h * 0.45, shadow=False, accent_tint=0.06)
            ink, dim = TEXT, MUTED
        elif iisu_fx.is_light():
            ink, dim = rgba(17, 24, 39, .94), rgba(71, 85, 105, .84)
            self.capsule(p, rect, rgba(255, 255, 255, .80), rgba(15, 23, 42, .12))
        else:
            self.capsule(p, rect, rgba(8, 11, 20, .58), rgba(255, 255, 255, .13))
        x, y = rect.x() + pad, rect.y() + (h - 1.3 * u * 1.2) / 2
        self.text(p, date, x, y, f, dim); x += self.width_of(date, f) + .8 * u
        self.text(p, clock(), x, y, fb, ink); x += self.width_of(clock(), fb) + 1.6 * u
        if bt_txt:
            self.text(p, bt_txt, x, y, f, ink)
            x += self.width_of(bt_txt, f) + 1.2 * u
        mid = rect.center().y()
        if self.WIFI is not None:
            self.glyph_wifi(p, x + .95 * u, mid + .55 * u, 1.05 * u, self.WIFI.get('signal') if self.WIFI.get('ssid') or self.WIFI.get('signal') else 0, ink)
            x += 1.9 * u + 1.2 * u
        if self.BATT:
            self.text(p, batt, x, y, f, ink); x += self.width_of(batt, f) + .6 * u
            self.glyph_battery(p, x, mid, ic, self.BATT['level'], self.BATT.get('charging'), ink)

    def paint_of(self, it, rect):  # the coloured gradient that stands in for missing art
        if it.get('s') in ('app', 'term'):
            return iisu_fx.app_tile_brush(self, it, rect)
        h = 212 if it['s'] == 'steam' else (self.L['systems'].get(it['s']) or {'hue': 200})['hue']
        k = jhash(it['t']) % 50
        angle = math.radians(120 + k)
        dx, dy = math.sin(angle), -math.cos(angle)
        half = (abs(rect.width() * dx) + abs(rect.height() * dy)) / 2
        c = rect.center()
        g = QLinearGradient(c.x() - dx * half, c.y() - dy * half, c.x() + dx * half, c.y() + dy * half)
        g.setColorAt(0, QColor.fromHslF(h / 360, .62, (24 + k % 14) / 100)); g.setColorAt(1, QColor.fromHslF(((h + 38 + k) % 360) / 360, .58, (12 + k % 9) / 100))
        return g

    def scroller(self, p, key, rect, draw):
        """A clipped area whose content (draw(y) -> end y) can be dragged, flicked with momentum, or fast-scrubbed."""
        u = self.u
        off = max(0, min(self.off.get(key, 0), self.maxoff.get(key, 0)))
        p.save(); p.setClipRect(rect)
        self.clip = rect
        end = draw(rect.y() - off)
        self.clip = None
        p.restore()
        max_off = max(0, end - (rect.y() - off) - rect.height())
        self.off[key], self.maxoff[key] = off, max_off
        mapped = self.xf.mapRect(rect) if self.xf is not None else rect
        self.scrolls.append((mapped, key, self.zoom))
        if max_off > 3.0 * u and rect.height() > 10.0 * u:
            total_h = rect.height() + max_off
            bar_h = max(4.2 * u, rect.height() * (rect.height() / total_h))
            bar_y = rect.y() + (rect.height() - bar_h) * (off / max_off)
            dt_touch = time.time() - self.scroll_touch_at.get(key, 0.0)
            active_sb = dt_touch < 1.35 or (self.kinetic and self.kinetic.get('key') == key)
            alpha = 0.56 if active_sb else 0.18
            bw = (0.66 if active_sb else 0.44) * u
            bx = rect.right() - bw - 0.32 * u
            self.capsule(p, QRectF(bx, bar_y, bw, bar_h), faded(FOCUS if active_sb else TEXT, alpha))
            if key == 'grid' and max_off > rect.height() * 1.1:
                def scrub_y(py, r_top=mapped.y(), r_h=mapped.height(), m_off=max_off, k=key):
                    frac = max(0.0, min(1.0, (py - r_top - 2.0 * u) / max(1.0, r_h - 4.0 * u)))
                    self.kinetic = None
                    self.scroll_anim = None
                    self.off[k] = frac * m_off
                    self.scroll_touch_at[k] = time.time()
                    self.update()
                self.hit(QRectF(rect.right() - 2.8 * u, rect.y(), 3.2 * u, rect.height()), scrub_y, 'y', 'scrollbar:' + key)

    # ---- painting ----------------------------------------------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.hits, self.scrolls, self.kb_keys, self.tile_rects, self.clip = [], [], [], [], None
        if self.DOZE:  # panels asleep on a charger: pure black, zero touch targets
            if self.saver_timer.isActive(): self.saver_timer.stop()
            p.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0))
            return p.end()
        if self.resting():  # dual-screen 60-FPS OLED showcase screensaver (30-FPS in travel_mode)
            iv = 33 if self.CFG.get('travel_mode') else 16
            if self.saver_timer.interval() != iv:
                self.saver_timer.setInterval(iv)
            if not self.saver_timer.isActive() and os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
                self.saver_timer.start()
            screensaver.draw(self, p)
            return p.end()
        if self.saver_timer.isActive():
            self.saver_timer.stop()
        items = self.items()
        if not settings_view.open_now(self): self.S['i'] = max(0, min(self.S['i'], len(items) - 1))
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
        target_acc = self.game_accent(items) or QColor(THEME['colors']['accent'])
        acc_key = target_acc.rgba()
        if self.playing() or self.CFG.get('motion') == 'reduced':
            self.acc_anim.update(from_c=QColor(target_acc), to_c=QColor(target_acc), to=acc_key, t0=0.0)
            FOCUS.setRgba(acc_key)
        else:
            if self.acc_anim['to'] is None:
                self.acc_anim.update(from_c=QColor(target_acc), to_c=QColor(target_acc), to=acc_key, t0=0.0)
            elif acc_key != self.acc_anim['to']:
                cur_acc = self.lerp_color(self.acc_anim['from_c'], self.acc_anim['to_c'], self.ease(self.acc_anim['t0'], self.dur(.24))) if self.acc_anim['t0'] else self.acc_anim['to_c']
                self.acc_anim.update(from_c=QColor(cur_acc), to_c=QColor(target_acc), to=acc_key, t0=time.time())
            t_acc = self.ease(self.acc_anim['t0'], self.dur(.24)) if self.acc_anim['t0'] else 1.0
            if t_acc >= 1: self.acc_anim['t0'] = 0.0
            FOCUS.setRgba(self.lerp_color(self.acc_anim['from_c'], self.acc_anim['to_c'], t_acc).rgba())  # smooth colour morph between games
        if self.side == 'bottom' and not self.SETUP:
            self._queue_rgb('%02X%02X%02X' % (target_acc.red(), target_acc.green(), target_acc.blue()))
        if self.SETUP and not self.RUN: self.draw_setup(p)
        else: (self.draw_top if self.side == 'top' else self.draw_bottom)(p, items)
        if self.QUICK and self.side == 'bottom': quick_view.draw(self, p)
        if self.POWER_OPEN: self.draw_power(p)
        if self.press_rect is not None and not self.moved and not self.kb_down:
            pr = self.press_rect
            rad_p = min(pr.height() / 2, 1.8 * self.u)
            p.setPen(QPen(faded(FOCUS, .42), max(1.0, .14 * self.u)))
            p.setBrush(rgba(255, 255, 255, .09))
            p.drawRoundedRect(pr, rad_p, rad_p)
        if self.TOAST and not (self.side == 'bottom' and (self.PROMPT or self.CONFIRM or self.POWER_OPEN)): self.draw_toast(p)
        tr_pop = getattr(self, 'TROPHY', None)
        if tr_pop and self.side == 'bottom':
            age = time.time() - tr_pop['at']
            if age < 5.5:
                self.draw_trophy_banner(p, tr_pop, age)
                QTimer.singleShot(40, self.update)
            else:
                self.TROPHY = None
        if self.OSD is not None: self.draw_osd(p)
        iisu_fx.draw_launch_ceremony(self, p)
        p.end()

    def draw_trophy_banner(self, p, tr_pop, age):
        """PS5/Xbox-style animated gold trophy unlock card on the bottom OLED (0% occlusion on top game screen)."""
        u, W = self.u, self.width()
        slide = min(1.0, age / 0.28) if age < 4.9 else max(0.0, (5.5 - age) / 0.6)
        ease_s = 1 - (1 - slide) ** 3
        bw, bh = min(W - 6 * u, 68 * u), 9.6 * u
        bx = (W - bw) / 2
        by = -bh + (bh + 2.4 * u) * ease_s
        rect = QRectF(bx, by, bw, bh)
        p.save()
        p.setOpacity(max(0.0, min(1.0, ease_s)))
        gold = QColor('#facc15')
        self.box(p, rect.adjusted(0, .3 * u, 0, .4 * u), 2.2 * u, rgba(0, 0, 0, .65))
        self.box(p, rect, 2.2 * u, QColor('#151822'), gold, .24 * u)
        badge = QRectF(bx + 1.5 * u, by + 1.5 * u, 6.6 * u, 6.6 * u)
        self.capsule(p, badge, faded(gold, .22), gold)
        self.text(p, '🏆', badge.x(), badge.y(), ('u', 3.0, 700), gold, badge.width(), 1, 6.6 / 3.0)
        pts = f' · +{tr_pop["points"]} Pkt.' if tr_pop.get('points') else ''
        self.text(p, 'TROPHÄE FREIGESCHALTET' + pts, badge.right() + 1.6 * u, by + 1.3 * u, ('u', 1.35, 700, .1), gold, bw - 11 * u)
        self.text(p, tr_pop.get('title', ''), badge.right() + 1.6 * u, by + 3.4 * u, ('u', 2.05, 700), TEXT, bw - 11 * u)
        if tr_pop.get('desc'):
            self.text(p, tr_pop['desc'], badge.right() + 1.6 * u, by + 6.1 * u, ('u', 1.48, 400), MUTED, bw - 11 * u)
        p.restore()

    def draw_power(self, p):
        """Long-press power sheet: navigable with D-pad + A/B and by touch on the bottom screen."""
        u, W, H = self.u, self.width(), self.height()
        p.fillRect(0, 0, W, H, faded(INK, .92))
        self.hit(QRectF(0, 0, W, H), lambda: self.post('api/action', {'name': 'power_close'}))
        rows = [(lbl, idx, name in ('reboot', 'poweroff')) for idx, (name, lbl, _) in enumerate(POWER_MENU)] + [('Abbrechen', len(POWER_MENU), False)]
        w = (46 if self.side == 'top' else 72) * u
        rh, gap = (4.6 if self.side == 'top' else 6.2) * u, 1.1 * u
        head_h = (4.2 if self.side == 'top' else 5.4) * u
        total_h = head_h + len(rows) * rh + (len(rows) - 1) * gap
        x, y = (W - w) / 2, (H - total_h) / 2
        self.text(p, 'Ein / Aus', x, y, ('u', 2.4 if self.side == 'top' else 3.2, 700, -.02), TEXT, w, 1)
        y += head_h
        f = ('u', 1.9 if self.side == 'top' else 2.3, 600)
        for lbl, idx, warn in rows:
            on = idx == self.power_i
            rect = QRectF(x, y, w, rh)
            bg = (WARN if warn else FOCUS) if on else RAISED
            fg = INK if on else (WARN if warn else TEXT)
            self.box(p, rect, 1.5 * u, bg, faded(TEXT, .12) if not on else None)
            self.text(p, lbl, x, y, f, fg, w, 1, rh / (f[1] * u))
            self.hit(rect, lambda idx=idx: (setattr(self, 'power_i', idx), self.power_pick(idx)), name='pwr:' + lbl)
            y += rh + gap

    def draw_toast(self, p):
        u, W, H, f = self.u, self.width(), self.height(), ('u', 2.3 if self.side == 'bottom' else 1.6, 500)
        rows = self.wrap(self.TOAST, f, 70 * u, None)
        lh = f[1] * u * 1.35
        w, h = max(self.width_of(r, f) for r in rows) + 6.2 * u, len(rows) * lh + 2.6 * u
        # top screen: a banner below the status line; bottom: above the volume display when that shows
        rect = QRectF((W - w) / 2, 6 * u if self.side == 'top' else H - (16.7 * u if self.OSD is not None else 4 * u) - h, w, h)
        self.box(p, rect, min(h / 2, 2.2 * u), faded(RAISED, .97), faded(TEXT, .08))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(FOCUS)
        p.drawEllipse(QPointF(rect.x() + 2.4 * u, rect.y() + 1.3 * u + lh / 2), .5 * u, .5 * u)
        for n, row in enumerate(rows): self.text(p, row, rect.x() + 3.8 * u, rect.y() + 1.3 * u + n * lh, f, TEXT, lh=1.35)

    def draw_osd(self, p):  # volume indicator for the hardware keys
        u, W, H, big = self.u, self.width(), self.height(), self.side == 'bottom'
        w, ico, size, bar = (64, 4.4, 2.6, 1.3) if big else (40, 3, 1.8, .9)
        h = (ico + 2.8) * u
        rect = QRectF((W - w * u) / 2, H - (8 if big else 6) * u - h, w * u, h)
        self.capsule(p, rect, faded(RAISED, .96), faded(TEXT, .08))
        x, mid = rect.x() + 2.4 * u, rect.center().y()
        self.icon(p, 'vol2' if self.OSD > 50 else 'vol1' if self.OSD > 0 else 'vol0', QRectF(x, mid - ico * u / 2, ico * u, ico * u), TEXT)
        num = (size * 2) * u
        track = QRectF(x + (ico + 1.6) * u, mid - bar * u / 2, rect.right() - 2.6 * u - num - 1.6 * u - (x + (ico + 1.6) * u), bar * u)
        self.capsule(p, track, faded(TEXT, .14))
        if self.OSD > 0: self.capsule(p, QRectF(track.x(), track.y(), max(track.height(), track.width() * self.OSD / 100), track.height()), TEXT)
        self.text(p, str(self.OSD), rect.right() - 2.6 * u - num, mid - size * u * .6, ('u', size, 600), TEXT, num, 2)

    def keycap(self, p, x, y, d, letter, fill):
        era = iisu_fx.era_mode()
        era_c = iisu_fx.sfc_pad_color(letter)
        btn_fill = era_c if era_c is not None else fill
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(btn_fill)
        if era == '8bit':
            p.drawRoundedRect(QRectF(x, y, d, d), 0.16 * d, 0.16 * d)
        else:
            p.drawEllipse(QRectF(x, y, d, d))
        fg_k = QColor('#ffffff') if (era == '8bit' and letter in ('A', 'B')) or (era == '16bit' and letter in ('A', 'X')) else INK
        self.text(p, letter, x, y, ('u', d / self.u * .5, 700), fg_k, d, 1, 2)

    def pads(self, p, x, y, hints, size=1.7, gap=2.4, actions=None):
        """Controller hints as interactive era-styled capsules: works both as pad legend AND direct touchscreen buttons."""
        u, f = self.u, ('u', 1.6 * size / 1.7, 500)
        h = 3.6 * u * size / 1.7
        d = h - 1.1 * u * size / 1.7
        era = iisu_fx.era_mode()
        key_map = {'A': 'ok', 'B': 'back', 'X': 'close', 'Y': 'fav', '+': 'menu', '−': 'search'}
        for n, (letter, label) in enumerate(hints):
            w = (h - d) / 2 + d + .9 * u + self.width_of(label, f) + 1.5 * u
            crect = QRectF(x, y, w, h)
            if era in ('8bit', '16bit'):
                iisu_fx.glass_card(self, p, crect, h * 0.42, shadow=False, accent_tint=0.14 if n == 0 else 0.0)
            else:
                self.capsule(p, crect, faded(TEXT, .16 if n == 0 else .08), faded(TEXT, .1))
            self.keycap(p, x + (h - d) / 2, y + (h - d) / 2, d, letter, FOCUS if n == 0 else faded(TEXT, .85))
            self.text(p, label, x + (h - d) / 2 + d + .9 * u, y, f if n else (f[0], f[1], 600), TEXT, lh=h / (f[1] * u))
            custom_fn = (actions or {}).get(letter)
            if custom_fn:
                self.hit(crect.adjusted(-.3 * u, -.5 * u, .3 * u, .5 * u), custom_fn, name=f'pad:{letter}')
            elif letter in key_map:
                act_a = key_map[letter]
                if letter == 'B' and self.playing():
                    fn_pad = self.confirm_quit
                else:
                    fn_pad = lambda a=act_a: self.post('api/uikey', {'a': a})
                self.hit(crect.adjusted(-.3 * u, -.5 * u, .3 * u, .5 * u), fn_pad, name=f'pad:{letter}')
            x += w + gap * u * .5
        return x

    def draw_top(self, p, items):
        u, W, H, RUN, P, L = self.u, self.width(), self.height(), self.RUN, self.playing(), self.L
        if not P and settings_view.open_now(self): return (settings_view.draw_top(self, p), self.draw_confirm(p))
        it = RUN if P else items[self.S['i']] if items else None
        full, hero = QRectF(0, 0, W, H), self.hero
        if (it or {}).get('id') != hero['key']: hero['key'], hero['kt'] = (it or {}).get('id'), time.time()
        art = self.images.get(it['hero'], W, H, 'hero') if it and it.get('hero') else False
        if art and art is not hero['cur']: hero['prev'], hero['cur'], hero['t0'] = hero['cur'], art, time.time()
        if it:
            shown = art or (hero['cur'] if art is None else None)  # while the next picture loads, the last one stays
            if shown:
                t = self.ease(hero['t0'], self.dur(.46))
                if t < 1 and hero['prev'] is not None: p.drawImage(0, 0, hero['prev'])
                else: hero['prev'] = None  # the fade is over: let go of the old picture
                p.save()
                p.setOpacity(t)
                if t < 1 and self.CFG.get('motion') != 'reduced':
                    z = 1.0 + .032 * (1.0 - t)
                    p.translate(W / 2, H / 2); p.scale(z, z); p.translate(-W / 2, -H / 2)
                p.drawImage(0, 0, shown)
                p.restore()
                p.fillRect(full, faded(INK, .18))
            else:
                hero['cur'] = hero['prev'] = None
                p.fillRect(full, QBrush(self.paint_of(it, full)))
                if art is False:
                    if it.get('kind') == 'sys':
                        iisu_fx.draw_svg(p, iisu_fx.console_svg_for(it.get('s')),
                                         QRectF(W - 44 * u, H * .22, 32 * u, 32 * u), rgba(255, 255, 255, .14))
                    elif it.get('s') not in ('app', 'term'):
                        self.text(p, it['t'][:1].upper(), W - 52 * u, H / 2 - 22 * u, ('u', 34, 700), rgba(255, 255, 255, .08), 44 * u, 2)
            g = QLinearGradient(0, 0, W, 0)
            g.setColorAt(0, faded(INK, .92)); g.setColorAt(.42, faded(INK, .52)); g.setColorAt(.78, faded(INK, 0))
            p.fillRect(full, QBrush(g))
            g = QLinearGradient(0, H, 0, 0)
            g.setColorAt(0, faded(INK, .92)); g.setColorAt(.58, faded(INK, 0))
            p.fillRect(full, QBrush(g))
            g = QLinearGradient(0, 0, 0, 9 * u)
            g.setColorAt(0, rgba(0, 0, 0, .20 if iisu_fx.is_light() else .35)); g.setColorAt(1, rgba(0, 0, 0, 0))
            p.fillRect(QRectF(0, 0, W, 9 * u), QBrush(g))
            iisu_fx.draw_hinge_bridge(self, p, 'top')
        else:  # nothing in front: Hinge-Bridge aurora instead of a flat wall
            iisu_fx.draw_hinge_bridge(self, p, 'top')
        iisu_fx.draw_era_backdrop(self, p)
        self.status_bar(p, items)
        held = bool(it and RUN and RUN.get('paused') and it['id'] == RUN['id'])
        sysinfo = L['systems'].get(it['s']) if it else None
        m, mv = ('u', 1.5, 400), ('u', 1.5, 600)
        if not it:
            empty_top = 'Keine passenden Spiele gefunden.' if self.S.get('q') else 'Mit R zu den Systemen wechseln.'
            name, meta, hints, miss = 'Noch nichts hier', [[('Toravo Tandem', ('u', 1.5, 600), FOCUS)], [(empty_top, m, MUTED)]], ([('B', 'Suche beenden')] if self.S.get('q') else []), None
        else:
            name = (iisu_fx.app_profile(it).get('headline') or it['t']) if (not P and it.get('s') in ('app', 'term')) else it['t']
            fact = lambda key, value: [(key + ' ', m, MUTED), (str(value), mv, TEXT)]
            played = L['played'].get(it['id']) or {}
            sname = 'System' if it.get('kind') == 'sys' else self.sys_name(it)
            frozen_now = bool(P and RUN.get('frozen'))
            lead = ([('❄️ ', ('u', 1.5, 700), QColor('#38bdf8')), ('Eingefroren (0 W)', ('u', 1.5, 700), QColor('#38bdf8')), (' · ' + sname, mv, TEXT)] if frozen_now else
                    [('● ', ('u', 1.5, 700), LIVE), ('Läuft', ('u', 1.5, 700), LIVE), (' · ' + sname, mv, TEXT)] if P else
                    [('❚❚ ', ('u', 1.4, 700), FOCUS), ('Pausiert', ('u', 1.5, 700), FOCUS), (' · ' + sname, mv, TEXT)] if held else
                    [(sname, ('u', 1.5, 600), FOCUS)])
            if P: meta = [lead, fact('Emulator', RUN['emu']), fact('Läuft seit', hours(time.time() - RUN['since']))]
            elif it.get('kind') == 'sys': meta = [lead, [(str(it['n']), mv, TEXT), (' Spiele', m, MUTED)], fact('Emulator', sysinfo.get('emu') or 'fehlt')]
            elif it.get('s') in ('app', 'term'):
                aprof = iisu_fx.app_profile(it)
                meta = [lead, [(aprof['cat'], mv, TEXT)]]
            else:
                pdb_map = {'platinum': ('Platin', QColor('#67e8f9')), 'gold': ('Gold', QColor('#facc15')),
                           'silver': ('Silber', QColor('#cbd5e1')), 'bronze': ('Bronze', QColor('#fb923c'))}
                pdb_fact = ([[('ProtonDB ', m, MUTED), (pdb_map[it['protondb']][0], ('u', 1.5, 700), pdb_map[it['protondb']][1])]]
                            if it.get('protondb') in pdb_map else [])
                ttb_val = float(it.get('ttb') or 0)
                p_secs = int(played.get('secs') or 0)
                ttb_str = (f'{min(100, round(p_secs / (ttb_val * 3600) * 100))} % (~{ttb_val:g} Std.)'
                           if (ttb_val > 0 and p_secs >= 600) else f'~{ttb_val:g} Std.')
                extra_facts = (pdb_fact
                               + ([fact('Jahr', it['year'])] if it.get('year') else [])
                               + ([fact('Genre', it['genre'])] if it.get('genre') else [])
                               + ([fact('Studio', it['dev'])] if it.get('dev') and not played.get('last') else [])
                               + ([fact('Spielumfang', ttb_str)] if ttb_val > 0 else []))
                meta = ([lead] + extra_facts[:2]
                        + ([fact('Zuletzt', ago(played['last']))] if played.get('last') else [])
                        + ([fact('Spielzeit', hours(played['secs']))] if played.get('secs') else [])
                        + ([fact('Laufzeit', it['native_engine'])] if it.get('native_engine') else [fact('Emulator', sysinfo.get('emu') or 'fehlt')] if sysinfo else [])
                        + ([[('★ Favorit', mv, FOCUS)]] if it['id'] in L['fav'] else []))
            miss = sysinfo.get('missing') if sysinfo and not P and not it.get('native_engine') else None
            if P: hints = [('B', 'Beenden (unten bestätigen)')]
            else:
                inst = it.get('inst')
                can_opt = not it.get('kind') and it['s'] not in ('app', 'term')
                hints = [('A', 'Öffnen' if it.get('kind') == 'sys' else 'Fortsetzen' if held else 'Installieren' if inst == 'no' else 'Lädt noch' if inst == 'load' else 'Starten')] + \
                        ([('X', 'Beenden')] if held else []) + [('B', 'Suche beenden' if self.S.get('q') else 'Zurück')] + ([] if not can_opt else [('Y', 'Favorit'), ('+', 'Optionen')]) + \
                        ([] if self.S['tab'] == 3 else [('−', 'Suche')])
        has_moment = bool(it and not P and it.get('moment'))
        shot_src = it.get('moment') if has_moment else (it.get('shot') if it and not P else None)
        sw, sh = (round(29.0 * u), round(16.3 * u)) if has_moment else (round(26.5 * u), round(14.9 * u))
        shot = self.images.get(shot_src, sw, sh, True) if shot_src else False
        is_app_card = bool(it and not P and it.get('s') in ('app', 'term'))
        use_3d = bool(it and not P and self.CFG.get('showcase_3d', True) and not it.get('kind')
                      and it.get('s') not in ('app', 'term') and (it.get('box') or it.get('cover') or shot))
        max_tw = (W - 4.2 * u - (33.0 * u if is_app_card else 35.5 * u if use_3d else (sw + 6.8 * u))) if (is_app_card or use_3d or shot) else 60 * u
        logo = self.images.get(it['logo'], round(min(40 * u, max_tw)), round(15.5 * u), False) if it and it.get('logo') else False
        nf, mf = ('u', 4.6, 700, -.025), ('m', 1.3, 500)
        if not logo and len(self.wrap(name, nf, max_tw)) > 2: nf = ('u', 3.7, 700, -.02)  # long names get smaller, not taller
        rows = [] if logo else self.wrap(name, nf, max_tw, 3)
        head_h = (logo.height() + .4 * u) if logo else len(rows) * nf[1] * u * 1.08
        app_desc = iisu_fx.app_profile(it).get('desc') if is_app_card else None
        raw_desc = (it.get('desc') or app_desc) if (it and not P and not miss) else None
        desc_rows = self.wrap(raw_desc, ('u', 1.45, 400), max_tw, 2) if raw_desc else []
        desc_h = (1.1 * u + len(desc_rows) * 1.45 * u * 1.38) if desc_rows else 0
        cmd = self.wrap(miss, mf, max_tw, None) if miss else []
        height = head_h + 1.5 * u + 1.8 * u + desc_h + (1.6 * u + len(cmd) * 1.3 * u * 1.4 + 1.8 * u if cmd else 0) + (2.4 * u + 3.6 * u if hints else 0)
        t = self.ease(hero['kt'], self.dur(.38))  # a new title or clear logo rises into place
        move = 0 if self.CFG.get('motion') == 'reduced' else (1 - t) * 1.2 * u
        x, y = 4.2 * u, H - 4.2 * u - height + move
        p.setOpacity(.15 + .85 * t)
        if logo:
            lrect = QRectF(x, y, logo.width(), logo.height())
            rad_g = max(lrect.width(), lrect.height()) * .62
            glow = QRadialGradient(lrect.center(), rad_g)
            glow.setColorAt(0, rgba(255, 255, 255, .45) if iisu_fx.is_light() else rgba(0, 0, 0, .42))
            glow.setColorAt(1, rgba(255, 255, 255, 0) if iisu_fx.is_light() else rgba(0, 0, 0, 0))
            p.fillRect(QRectF(lrect.center().x() - rad_g, lrect.center().y() - rad_g, 2 * rad_g, 2 * rad_g), QBrush(glow))
            p.drawImage(lrect.topLeft(), logo)
            y += head_h
        else:
            for row in rows: y += self.text(p, row, x, y, nf, TEXT, lh=1.08)
        y += 1.5 * u
        mx, mx_limit = x, x + max_tw
        sep_w = self.width_of('   ·   ', m)
        for n, part in enumerate(meta):
            part_w = sum(self.width_of(txt, fnt) for txt, fnt, _ in part)
            if n and mx + sep_w + part_w > mx_limit:
                break
            if n: mx = self.spans(p, mx, y, [('   ·   ', m, faded(MUTED, .6))])
            mx = self.spans(p, mx, y, part)
        y += 1.8 * u
        if desc_rows:
            y += 1.1 * u
            for drow in desc_rows:
                y += self.text(p, drow, x, y, ('u', 1.45, 400), faded(TEXT, .78), max_tw, lh=1.38)
        if cmd:
            y += 1.6 * u
            box = QRectF(x, y, max(self.width_of(r, mf) for r in cmd) + 2.4 * u, len(cmd) * 1.3 * u * 1.4 + 1.8 * u)
            self.box(p, box, u, faded(INK, .72), faded(WARN, .35))
            for n, row in enumerate(cmd): self.text(p, row, x + 1.2 * u, y + .9 * u + n * 1.3 * u * 1.4, mf, WARN, lh=1.4)
            y = box.bottom()
        if hints: self.pads(p, x, y + 2.4 * u, hints)
        if is_app_card:
            iisu_fx.draw_app_showcase(self, p, it, t)
        elif use_3d:
            iisu_fx.draw_3d_showcase(self, p, it, t, has_moment, shot if shot else None)
        elif shot:
            smove = 0 if self.CFG.get('motion') == 'reduced' else (1 - t) * 1.4 * u
            srect = QRectF(W - 3.8 * u - sw + smove, H - 4.2 * u - sh, sw, sh)
            sr = 1.4 * u
            for k, a in ((1.4, .18), (.7, .28)): self.box(p, srect.adjusted(-k * u, -k * u + .65 * u, k * u, k * u + .65 * u), sr + k * u, rgba(0, 0, 0, a * t))
            sbrush = QBrush(shot)
            sbrush.setTransform(sbrush.transform().translate(srect.x(), srect.y()))
            self.box(p, srect, sr, sbrush, faded(FOCUS, .45) if has_moment else rgba(255, 255, 255, .18), 1.3 if has_moment else 1.0)
            if has_moment:
                blbl = '● Zuletzt im Spiel'
                bf = ('u', 1.25, 700, .03)
                bw = self.width_of(blbl, bf) + 2.2 * u
                bh = 2.5 * u
                brect = QRectF(srect.x() + 1.0 * u, srect.y() + 1.0 * u, bw, bh)
                self.capsule(p, brect, rgba(10, 11, 18, .82), rgba(255, 255, 255, .18))
                self.text(p, blbl, brect.x(), brect.y(), bf, FOCUS, bw, 1, bh / (1.25 * u))
            self.hit(srect, lambda: self.post('api/uikey', {'a': 'ok'}), name='pad:shot')
        p.setOpacity(1)
        self.draw_confirm(p)

    def draw_confirm(self, p):
        u, W, H = self.u, self.width(), self.height()
        if self.CONFIRM:  # the question shows here too: the controller answers it
            p.fillRect(QRectF(0, 0, W, H), faded(INK, .9))
            f = ('u', 3.4, 700, -.02)
            rows = self.wrap(self.CONFIRM['text'], f, 64 * u, None)
            y = (H - len(rows) * 3.4 * u * 1.2 - 3 * u - 4.2 * u) / 2
            for row in rows: y += self.text(p, row, 0, y, f, TEXT, W, 1)
            hints = [('A', self.CONFIRM['yes']), ('B', 'Abbrechen')]
            f = ('u', 1.6 * 2 / 1.7, 500)
            h, d = 3.6 * u * 2 / 1.7, (3.6 - 1.1) * u * 2 / 1.7
            w = sum((h - d) / 2 + d + .9 * u + self.width_of(l, f) + 1.5 * u for _, l in hints) + 1.5 * u
            self.pads(p, (W - w) / 2, y + 3 * u, hints, 2, 3)

    # bottom screen ---------------------------------------------------------------------------------------------------
    def tabs(self, p, title=None, buttons=None):
        """Unified full-width Liquid-Glass Console Menu Dock (`x0` to `x0 + cw`). Returns the y below it."""
        return iisu_fx.draw_console_dock(self, p, getattr(self, '_cur_items', ()), title=title, buttons=buttons)

    def open_tab(self, n):
        self.S, self.SUB = {'tab': n, 'sys': None, 'i': 0}, ''
        if n == 4: self.load_sys()
        self.push()

    def sliders(self, p, y):
        """Brightness and volume in one grouped card; returns the y below it."""
        u, x0, cw = self.u, 2.6 * self.u, self.width() - 5.2 * self.u
        rows = [(key, label) for key, label in (('bt', 'Helligkeit oben'), ('bb', 'Helligkeit unten'), ('vol', 'Lautstärke')) if self.SET.get(key) is not None]
        if not rows: return y
        rh = 6.2 * u
        self.box(p, QRectF(x0, y, cw, len(rows) * rh + 1.2 * u), 2 * u, PANEL)
        y += .6 * u
        for n, (key, label) in enumerate(rows):
            value = self.SET[key]
            if n: p.fillRect(QRectF(x0 + 2 * u, y, cw - 4 * u, max(1.0, .08 * u)), faded(TEXT, .07))
            self.text(p, label, x0 + 2 * u, y, ('u', 2.1, 500), TEXT, lh=rh / (2.1 * u))
            left, width, low = x0 + 27 * u, cw - 27 * u - 11 * u, 0 if key == 'vol' else 5
            part = max(0.0, min(1.0, (value - low) / (100 - low)))
            mid = y + rh / 2
            self.capsule(p, QRectF(left, mid - .5 * u, width, u), faded(TEXT, .12))
            self.capsule(p, QRectF(left, mid - .5 * u, max(u, width * part), u), self.accent_fill(QRectF(left, 0, width, 1)))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(rgba(0, 0, 0, .35))
            p.drawEllipse(QPointF(left + width * part, mid + .15 * u), 1.55 * u, 1.55 * u)
            p.setBrush(QColor('#ffffff'))
            p.drawEllipse(QPointF(left + width * part, mid), 1.45 * u, 1.45 * u)
            self.text(p, f'{value} %', x0 + cw - 9 * u, y, ('u', 2.1, 500), MUTED, 7 * u, 2, rh / (2.1 * u))
            self.hit(QRectF(left - 1.5 * u, y, width + 3 * u, rh), lambda x, key=key, left=left, width=width: self.set_value(key, x, left, width), True, key)
            y += rh
        return y + .6 * u + 1.8 * u

    def row_buttons(self, p, y, buttons, cols=4, f=('u', 2.1, 600), fg=TEXT, bg=PANEL):
        """A grid of equal buttons [(label, fn)]; returns the y below it."""
        u, x0, cw, h = self.u, 2.6 * self.u, self.width() - 5.2 * self.u, 6.3 * self.u
        w = (cw - (cols - 1) * 1.2 * u) / cols
        for n, (label, fn) in enumerate(buttons):
            self.button(p, QRectF(x0 + (n % cols) * (w + 1.2 * u), y + (n // cols) * (h + 1.2 * u), w, h), label, fn, f, fg, bg, None, 1.4)
        return y + ((len(buttons) + cols - 1) // cols) * (h + 1.2 * u) - 1.2 * u

    def keyboard(self, p, y, press, skip=(), bottom_y=None):
        u, x0, cw = self.u, 2.6 * self.u, self.width() - 5.2 * self.u
        bottom = (self.height() - 2.6 * u) if bottom_y is None else bottom_y
        layout = (self.RUN or {}).get('layout') if not self.PROMPT else self.CFG.get('kb_layout')
        layout = layout if layout in KB else 'us' if not self.PROMPT else 'de'
        rows = [r for r in ([c for c in row if c not in skip] for row in KB_CODES) if r]
        h = (bottom - y - (len(rows) - 1) * 1.15 * u) / max(1, len(rows))
        sel_r, sel_c = self.kb_rc if getattr(self, 'kb_pad', False) else (-1, -1)
        now = time.time()
        down_code = self.kb_down[1] if self.kb_down else None
        flash = self.kb_flash if self.kb_flash and now - self.kb_flash[3] < .13 else None
        if flash: QTimer.singleShot(20, self.update)
        callout = None
        specials = {14, 15, 28, 29, 42, 56, 58, 100, 1, 103, 105, 106, 108}
        alt_map = KB_ALTGR.get(layout, {})
        for r, row in enumerate(rows):
            weight = lambda c: 4.8 if c == 57 else 1.55 if c in (14, 28, 42, 100) else 1.25 if c == -2 else 1.0
            unit = (cw - (len(row) - 1) * .95 * u) / sum(weight(c) for c in row)
            x = x0
            for c_idx, code in enumerate(row):
                w = unit * weight(code)
                base_rect = QRectF(x, y + r * (h + 1.15 * u), w, h)
                on = KB_MODS.get(code) in self.KM
                label = self.key_label(code, layout)
                alt_lbl = '' if ('altgr' in self.KM or code == 57) else alt_map.get(code, '')
                pressed_now = (down_code == code)
                flashed_now = bool(flash and flash[0] == code and not pressed_now)
                fade = max(0.0, 1.0 - (now - flash[3]) / .13) if flashed_now else 0.0
                active_k = pressed_now or fade > 0
                dy = .18 * u if pressed_now else .08 * u * fade
                krect = base_rect.adjusted(0, dy, 0, dy)
                rad = 1.25 * u
                if not pressed_now:
                    self.box(p, base_rect.adjusted(0, .2 * u, 0, .24 * u), rad, rgba(0, 0, 0, .46))
                if pressed_now or on:
                    bg, fg = FOCUS, INK
                elif flashed_now:
                    bg, fg = self.lerp_color(RAISED, FOCUS, .75 * fade), INK if fade > .45 else TEXT
                elif code == 28:
                    bg, fg = faded(FOCUS, .22), FOCUS
                elif code in specials:
                    bg, fg = PANEL, TEXT if code in (14, 42, 100) else MUTED
                else:
                    bg, fg = RAISED, TEXT
                pad_focus = (r == sel_r and c_idx == sel_c and not on and not pressed_now)
                border = FOCUS if (pad_focus or code == 28) else rgba(255, 255, 255, .09) if not active_k else None
                if pressed_now and THEME['glow']:
                    self.box(p, krect.adjusted(-.45 * u, -.45 * u, .45 * u, .45 * u), rad + .45 * u, faded(FOCUS, .28 * THEME['glow']))
                self.box(p, krect, rad, bg, border, .22 * u if pad_focus else 1.0)
                if not active_k and not on:
                    p.fillRect(QRectF(krect.x() + rad * .7, krect.y() + 1, max(0.0, krect.width() - rad * 1.4), 1.0), rgba(255, 255, 255, .09))
                if code == 57:
                    sp_lbl = 'Deutsch' if layout == 'de' else 'English'
                    self.text(p, sp_lbl, krect.x(), krect.y(), ('u', 1.85, 500), INK if (pressed_now or on) else faded(MUTED, .55), krect.width(), 1, h / (1.85 * u))
                else:
                    if alt_lbl and not (pressed_now or on):
                        self.text(p, alt_lbl, krect.x(), krect.y() + .45 * u, ('u', 1.35, 600), faded(MUTED, .72), krect.width() - .65 * u, 2, 1.1)
                    fsz = 3.0 if len(label) < 2 else 2.4 if len(label) == 2 else 1.95
                    self.text(p, label, krect.x(), krect.y(), ('u', fsz, 600 if (pressed_now or on or code in (-2, 28)) else 500), fg, krect.width(), 1, h / (fsz * u))
                if (pressed_now or (flashed_now and fade > .35)) and code not in specials and code != 57 and label.strip():
                    callout = (base_rect, label)
                def tap_key(code=code, label=label, base_rect=base_rect):
                    self.kb_pad = False
                    self.haptic()
                    self.kb_flash = (code, label, base_rect, time.time())
                    QTimer.singleShot(135, self.update)
                    press(code)
                self.kb_keys.append((base_rect, code, label, alt_lbl, press))
                self.hit(base_rect, tap_key, name=label)
                x += w + .95 * u
        if callout:
            crect, clbl = callout
            bw = max(crect.width() * 1.36, 8.6 * u)
            bh = 9.4 * u
            bx = max(1.4 * u, min(self.width() - bw - 1.4 * u, crect.center().x() - bw / 2))
            by = max(1.2 * u, crect.top() - bh - .9 * u)
            pop = QRectF(bx, by, bw, bh)
            self.box(p, pop.adjusted(0, .35 * u, 0, .45 * u), 2.0 * u, rgba(0, 0, 0, .58))
            self.box(p, pop, 2.0 * u, RAISED, FOCUS, .26 * u)
            self.text(p, clbl, pop.x(), pop.y(), ('u', 4.5 if len(clbl) == 1 else 3.0, 700), FOCUS, pop.width(), 1, bh / ((4.5 if len(clbl) == 1 else 3.0) * u))

    def draw_bottom(self, p, items):
        self._cur_items = items
        u, W, H, RUN, P = self.u, self.width(), self.height(), self.RUN, self.playing()
        x0, cw, bottom = 2.6 * u, W - 5.2 * u, H - 2.6 * u
        act = lambda label, fn, x, w, quit=False: self.button(p, QRectF(x, bottom - 6.3 * u, w, 6.3 * u), label, fn, ('u', 2.2, 600), INK if quit else TEXT, WARN if quit else PANEL, None, 1.4)
        if self.PROMPT:
            btns = []
            if not (self.PROMPT.get('swkbd_id') and self.PROMPT.get('min', 0) > 0):
                btns.append(('Abbrechen', False, lambda: self.finish_prompt(False)))
            btns.append(('Fertig', True, lambda: self.finish_prompt(True)))
            y = self.tabs(p, self.PROMPT['title'], btns)
            raw_val = self.PROMPT['value']
            masked = self.PROMPT['secret'] and not self.PROMPT.get('show')
            value = '•' * len(raw_val) if masked else raw_val
            self.box(p, QRectF(x0, y, cw, 9 * u), 1.8 * u, PANEL, FOCUS, .2 * u)
            right_edge = x0 + cw - 2.0 * u
            if raw_val:
                clr = QRectF(right_edge - 5.4 * u, y + 1.8 * u, 5.4 * u, 5.4 * u)
                self.capsule(p, clr, RAISED, rgba(255, 255, 255, .1))
                self.text(p, '×', clr.x(), clr.y() - .15 * u, ('u', 3.0, 600), MUTED, clr.width(), 1, 5.4 / 3.0)
                self.hit(clr, lambda: (self.haptic(), self.PROMPT.__setitem__('value', '')), name='prompt:clear')
                right_edge = clr.x() - 1.0 * u
            if self.PROMPT['secret'] and raw_val:
                slbl = 'Verbergen' if self.PROMPT.get('show') else 'Zeigen'
                sf = ('u', 1.85, 600)
                sw = self.width_of(slbl, sf) + 3.0 * u
                srect = QRectF(right_edge - sw, y + 1.8 * u, sw, 5.4 * u)
                self.capsule(p, srect, RAISED, rgba(255, 255, 255, .1))
                self.text(p, slbl, srect.x(), srect.y(), sf, TEXT, sw, 1, 5.4 / 1.85)
                self.hit(srect, lambda: (self.haptic(), self.PROMPT.__setitem__('show', not self.PROMPT.get('show'))), name='prompt:show')
                right_edge = srect.x() - 1.2 * u
            max_tw = max(4 * u, right_edge - (x0 + 2.4 * u) - 1.0 * u)
            fm_p = self.font('u', 3.6, 500)[1]
            shown_val = value
            while shown_val and fm_p.horizontalAdvance(shown_val) > max_tw:
                shown_val = '…' + shown_val[2:] if len(shown_val) > 2 else shown_val[1:]
            end = x0 + 2.4 * u + self.width_of(shown_val, ('u', 3.6, 500))
            self.text(p, shown_val, x0 + 2.4 * u, y, ('u', 3.6, 500), TEXT, lh=9 / 3.6)
            p.fillRect(QRectF(min(end + .4 * u, right_edge - .5 * u), y + 2.5 * u, .35 * u, 4 * u), FOCUS)
            return self.keyboard(p, y + 9 * u + 2.2 * u, self.prompt_key, skip=(29, 56, 1, 103, 105, 108, 106, 15, 58))
        if self.CONFIRM:
            c = self.CONFIRM
            f = ('u', 3.6, 700, -.02)
            self.text(p, c['text'], x0, H * .38 - len(self.wrap(c['text'], f, cw, None)) * 3.6 * u * .6, f, TEXT, cw, 1, lh=1.2, lines=None)
            half = (cw - 1.4 * u) / 2
            act('Abbrechen', self.unconfirm, x0, half)
            return act(c['yes'], lambda: (self.unconfirm(), c['run']()), x0 + half + 1.4 * u, half, True)
        if self.GAME_MENU and not P:
            return self.draw_game_menu(p)
        if P and (RUN['s'] == 'term' or RUN.get('keys')):  # keys: YouTube browser login or Battle.net launcher
            ai_auth = getattr(self, 'AI_AUTH', None) or {}
            if RUN['s'] == 'term' and ai_auth.get('open'):
                y = self.tabs(p, 'KI-Anmeldung per QR-Code', [('Zur Tastatur', False, lambda: self.post('api/ai_auth', {'action': 'close'}))])
                qr_url = ai_auth.get('qr') or ''
                card_h = H - y - 10.6 * u
                card_r = QRectF(x0, y, cw, max(24 * u, card_h))
                self.box(p, card_r, 2.0 * u, PANEL, faded(FOCUS, .45))
                qsize = min(card_r.height() - 4.0 * u, 30 * u)
                qrect = QRectF(card_r.x() + 2.4 * u, card_r.y() + (card_r.height() - qsize) / 2, qsize, qsize)
                if qr_url:
                    try:
                        qr.draw(p, qrect, qr_url, round(1.8 * u))
                    except ValueError:
                        self.box(p, qrect, 1.5 * u, RAISED, LINE)
                        self.text(p, 'Kein QR', qrect.x(), qrect.y(), ('u', 2.0, 600), MUTED, qrect.width(), 1, qrect.height() / (2.0 * u))
                else:
                    self.box(p, qrect, 1.5 * u, RAISED, LINE)
                    self.text(p, 'Kein WLAN', qrect.x(), qrect.y(), ('u', 2.0, 600), WARN, qrect.width(), 1, qrect.height() / (2.0 * u))
                tx = qrect.right() + 2.8 * u
                tw = card_r.right() - tx - 2.4 * u
                ty = qrect.y() + .4 * u
                self.text(p, 'Bequem am Handy anmelden', tx, ty, ('u', 2.6, 700, -.01), TEXT, tw)
                ty += 4.2 * u
                steps = ('1. QR-Code mit dem Handy scannen und auf „Anmeldung im Browser öffnen“ tippen.\n\n'
                         '2. Bei Google oder Claude anmelden und den angezeigten Code (oder die Callback-URL) '
                         'auf der Handy-Seite einfügen → „An Thor senden“.')
                self.text(p, steps, tx, ty, ('u', 1.95, 400), MUTED, tw, lh=1.42, lines=None)
                if qr_url:
                    self.text(p, qr_url, tx, qrect.bottom() - 2.6 * u, ('m', 1.45, 500), FOCUS, tw)
                by = card_r.bottom() + 1.8 * u
                bh = 5.6 * u
                half = (cw - 1.4 * u) / 2
                self.button(p, QRectF(x0, by, half, bh), 'Auf Thor im Browser öffnen',
                            lambda: self.post('api/ai_auth', {'action': 'browser'}, then=lambda r: r and r.get('error') and self.toast(r['error'])),
                            ('u', 2.0, 600), TEXT, PANEL, LINE, 1.3)
                self.button(p, QRectF(x0 + half + 1.4 * u, by, half, bh), 'Zur Tastatur',
                            lambda: self.post('api/ai_auth', {'action': 'close'}),
                            ('u', 2.0, 700), INK, FOCUS, None, 1.3)
                return
            layout = RUN.get('layout') if RUN.get('layout') in KB else 'us'
            lang_btn = (f'Tastatur: {"Deutsch" if layout == "de" else "Englisch"}', False, lambda: self.post('api/layout', {'layout': 'us' if layout == 'de' else 'de'}))
            if RUN.get('login'):
                btns = [('Abbrechen', False, lambda: self.post('api/ytlogin', {'a': 'cancel'})), lang_btn, ('Fertig', True, lambda: self.post('api/ytlogin', {'a': 'done'}))]
                title = 'Bei YouTube anmelden'
            else:
                btns = [lang_btn, ('Schließen', False, lambda: self.post('api/quit'))]
                title = RUN['t'] if (RUN.get('keys') or RUN.get('id', '').startswith('ai:')) else 'Linux-Shell'
            y = self.tabs(p, title, btns)
            if RUN.get('keys'):
                quick = [('@', 'seq', '@'), ('.com', 'seq', '.com'), ('.de', 'seq', '.de'), ('gmail.com', 'seq', 'gmail.com'), ('Tab ⇥', 'code', 15), ('Weiter ↵', 'code', 28)]
                qh, qgap = 5.0 * u, 1.0 * u
                qw = (cw - qgap * (len(quick) - 1)) / len(quick)
                for qi, (qlbl, qkind, qval) in enumerate(quick):
                    is_go = qlbl.startswith('Weiter')
                    qfn = (lambda v=qval: self.post('api/key', {'seq': v})) if qkind == 'seq' else (lambda v=qval: self.term_key(v))
                    self.button(p, QRectF(x0 + qi * (qw + qgap), y, qw, qh), qlbl, qfn, ('u', 2.0, 600), INK if is_go else TEXT, FOCUS if is_go else PANEL, faded(TEXT, .1) if not is_go else None, 1.2)
                y += qh + 1.4 * u
            elif RUN['s'] == 'term':
                if str(RUN.get('id') or '').startswith('ai:'):
                    ai_quick = [
                        ('QR-Login', lambda: self.post('api/ai_auth', {'action': 'open'}), False),
                        ('@', lambda: self.post('api/key', {'seq': '@'}), False),
                        ('Tab ⇥', lambda: self.post('api/key', {'code': 15, 'mods': []}), False),
                        ('Einfügen', lambda: self.post('api/ai_window', {'action': 'paste'}), False),
                        ('Web ⇄ Term', lambda: self.post('api/ai_window', {'action': 'toggle'}, then=lambda r: r and r.get('error') and self.toast(r['error'])), False),
                        ('⇧Tab', lambda: self.post('api/key', {'code': 15, 'mods': ['shift']}), False),
                        ('Strg+C', lambda: self.post('api/key', {'code': 46, 'mods': ['ctrl']}), False),
                        ('Senden ↵', lambda: self.post('api/key', {'code': 28, 'mods': []}), True),
                    ]
                else:
                    ai_quick = [
                        ('Claude ⚡', lambda: self.post('api/key', {'seq': 'claude --dangerously-skip-permissions', 'enter': True}), False),
                        ('agy ⚡', lambda: self.post('api/key', {'seq': 'agy --dangerously-skip-permissions', 'enter': True}), False),
                        ('Einfügen', lambda: self.post('api/ai_window', {'action': 'paste'}), False),
                        ('Web ⇄ Term', lambda: self.post('api/ai_window', {'action': 'toggle'}, then=lambda r: r and r.get('error') and self.toast(r['error'])), False),
                        ('Strg+C', lambda: self.post('api/key', {'code': 46, 'mods': ['ctrl']}), False),
                        ('Esc', lambda: self.post('api/key', {'code': 1, 'mods': []}), False),
                        ('Senden ↵', lambda: self.post('api/key', {'code': 28, 'mods': []}), True),
                    ]
                qh, qgap = 4.8 * u, 0.8 * u
                qw = (cw - qgap * (len(ai_quick) - 1)) / len(ai_quick)
                for qi, (qlbl, qfn, is_go) in enumerate(ai_quick):
                    self.button(p, QRectF(x0 + qi * (qw + qgap), y, qw, qh), qlbl, qfn, ('u', 1.72, 600),
                                INK if is_go else TEXT, FOCUS if is_go else PANEL, faded(TEXT, .1) if not is_go else None, 1.15)
                y += qh + 1.2 * u
            return self.keyboard(p, y, self.term_key)
        if P and self.show_deck(p): return  # HOOK: native deck, see DECKS above
        iisu_fx.draw_era_backdrop(self, p)
        iisu_fx.draw_hinge_bridge(self, p, 'bottom')
        if P: return self.ingame(p)
        if not self.S.get('q') and settings_view.open_now(self): return settings_view.draw(self, p)
        if self.S.get('q'):
            vlabel = 'Kacheln' if self.CFG.get('view_mode') == 'stage' else 'Bühne'
            y = self.tabs(p, f'Suche: {self.S["q"]}', [(vlabel, False, self.toggle_view), ('Ändern', False, self.open_search), ('Fertig', True, self.clear_search)])
        else:
            y = self.tabs(p)
            if self.S['sys']:
                bf = ('u', 1.85, 600)
                back_txt = '‹ Systeme'
                bw_c = self.width_of(back_txt, bf) + 2.8 * u
                bh_c = 4.3 * u
                sy = y - .4 * u
                brect_c = QRectF(x0, sy, bw_c, bh_c)
                self.capsule(p, brect_c, faded(FOCUS, .14), faded(FOCUS, .40))
                self.text(p, back_txt, x0, sy, bf, FOCUS, bw_c, 1, bh_c / (1.85 * u))
                self.hit(brect_c, lambda: self.go('back'), name='sys-back')
                right_s = x0 + cw
                if self.S['sys'] != '_hidden':
                    sf = ('u', 1.7, 600)
                    slabels = {'recent': 'Zuletzt', 'az': 'A–Z', 'time': 'Spielzeit', 'year': 'Jahr', 'short': 'Kurz (<5h)'}
                    slbl = slabels.get(self.L.get('sort') or 'recent', 'Zuletzt')
                    sw2 = self.width_of(slbl, sf) + 4.4 * u
                    srect2 = QRectF(right_s - sw2, sy, sw2, bh_c)
                    self.capsule(p, srect2, faded(PANEL, .92), faded(TEXT, .10))
                    iisu_fx.draw_svg(p, 'nav_sort', QRectF(srect2.x() + 1.0 * u, srect2.center().y() - .95 * u, 1.9 * u, 1.9 * u), FOCUS)
                    self.text(p, slbl, srect2.x() + 2.8 * u, sy, sf, TEXT, sw2 - 3.3 * u, 1, bh_c / (1.7 * u))
                    self.hit(srect2, self.cycle_sort, name='Sort:' + slbl)
                    right_s = srect2.x() - 1.2 * u
                ic_sys = 2.2 * u
                ix_s = x0 + bw_c + 1.4 * u
                iisu_fx.draw_svg(p, iisu_fx.console_svg_for(self.S['sys']),
                                 QRectF(ix_s, sy + (bh_c - ic_sys) / 2, ic_sys, ic_sys), FOCUS)
                sys_title = self.sys_name({'s': self.S['sys']})
                cnt_txt = f'{len(items)} Eintrag' if len(items) == 1 else f'{len(items)} Spiele'
                self.text(p, f'{sys_title}  ·  {cnt_txt}', ix_s + ic_sys + .9 * u, sy, ('u', 1.95, 700, -.01), TEXT,
                          max(8 * u, right_s - (ix_s + ic_sys + .9 * u)), lh=bh_c / (1.95 * u))
                y = sy + bh_c + 1.8 * u
        if RUN and RUN.get('paused'):
            rect = QRectF(x0, y, cw, 7 * u)
            self.box(p, rect, 2 * u, PANEL, faded(LIVE, .35))
            f, bh = ('u', 1.9, 600), 4.4 * u
            wq, wr = self.width_of('Beenden', f) + 4 * u, self.width_of('Fortsetzen', f) + 4 * u
            by = y + (7 * u - bh) / 2
            for label, fn, bx, w, fg, bg in (('Beenden', lambda: self.post('api/quit'), rect.right() - 1.3 * u - wq, wq, TEXT, faded(TEXT, .1)),
                                             ('Fortsetzen', self.resume, rect.right() - 1.3 * u - wq - u - wr, wr, INK, LIVE)):
                self.capsule(p, QRectF(bx, by, w, bh), bg)
                self.text(p, label, bx, by, f, fg, w, 1, bh / (f[1] * u))
                self.hit(QRectF(bx, by, w, bh), fn, name=label)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(LIVE)
            for k in (0, 1): p.drawRoundedRect(QRectF(x0 + 2 * u + k * .9 * u, y + 2.6 * u, .55 * u, 1.8 * u), .2 * u, .2 * u)
            x = x0 + 4.6 * u
            room = rect.right() - 1.3 * u - wq - wr - 3 * u - x - self.width_of(' ist pausiert', ('u', 2.1))
            title = self.font('u', 2.1, 600)[1].elidedText(RUN['t'], Qt.TextElideMode.ElideRight, room)
            self.spans(p, x, y, [(title, ('u', 2.1, 600), TEXT), (' ist pausiert', ('u', 2.1), MUTED)], 7 / 2.1)
            y += 7 * u + 2 * u
        if not items:
            empty = ('Keine passenden Spiele gefunden.' if self.S.get('q') else
                     'Hier erscheinen zuletzt gespielte Spiele und Favoriten. Wechsle mit R zu den Systemen und starte etwas.' if self.S['tab'] == 0 else
                     'Keine installierten Steam-Spiele gefunden.' if self.S['tab'] == 2 else 'Keine Spiele gefunden. Lege ROMs in ROMs/<System> ab und lies die Bibliothek unter Apps neu ein.')
            return self.text(p, empty, x0 + u, y + 4 * u, ('u', 2.2), MUTED, cw - 2 * u, lh=1.5, lines=None)
        page_key = (self.S['tab'], self.S['sys'], self.S.get('q', ''), self.CFG.get('view_mode', 'grid'), self.grid_cols())
        if self.page_anim[0] != page_key: self.page_anim = (page_key, time.time())
        if self.stage_on(items): return self.draw_stage(p, items, y, bottom)
        cols = self.grid_cols()
        gap, edge = (2.2 if cols <= 4 else 1.7 if cols == 6 else 2.0) * u, 2.6 * u
        size = (cw - (cols - 1) * gap) / cols
        tile_h = size  # strictly 1:1 square tiles across all tabs and zoom levels ("aus einem Guss")
        show_pods = bool(self.S['tab'] == 0 and not self.S['sys'] and not self.S.get('q') and self.CFG.get('home_pods', False))
        pods_h = (17.2 * u) if show_pods else 0.0
        view = QRectF(x0 - edge, y - edge, cw + 2 * edge, bottom - y + 2 * edge)
        seen, i = (self.S['tab'], self.S['sys'], self.S.get('q', ''), self.S['i'], len(items), cols), self.S['i']
        if seen != self.seen:  # keep the selection in view (the grid follows the controller smoothly)
            row_top = pods_h + (i // cols) * (tile_h + gap)
            self.maxoff['grid'] = max(0, pods_h + (len(items) + cols - 1) // cols * (tile_h + gap) - gap + 2 * edge - view.height())
            cur_off = self.off.get('grid', 0)
            target_off = 0.0 if (show_pods and i < cols and row_top + tile_h + 2 * edge <= view.height()) else max(
                0, min(self.maxoff['grid'], max(min(cur_off, row_top), row_top + tile_h + 2 * edge - view.height())))
            if abs(target_off - cur_off) > .5 and self.seen and self.seen[:3] == seen[:3] and self.CFG.get('motion') != 'reduced':
                self.scroll_anim = (cur_off, target_off, time.time())
            else:
                self.scroll_anim = None
                self.off['grid'] = target_off
            self.seen = seen
        if self.scroll_anim:
            ts = self.ease(self.scroll_anim[2], self.dur(.22))
            self.off['grid'] = self.scroll_anim[0] + (self.scroll_anim[1] - self.scroll_anim[0]) * ts
            if ts >= 1: self.scroll_anim = None
        if self.lift[0] != seen[:4]: self.lift = (seen[:4], time.time())
        tx_sel, ty_sel = x0 + (i % cols) * (size + gap), edge + pods_h + (i // cols) * (tile_h + gap)
        fa = self.focus_anim
        if fa['page'] != page_key:
            fa.update(fx=tx_sel, fy=ty_sel, tx=tx_sel, ty=ty_sel, key=i, page=page_key, t0=0.0)
        elif fa['key'] != i:
            tf = iisu_fx.spring(self, fa['t0'], self.dur(.22)) if fa['t0'] else 1.0
            fa.update(fx=fa['fx'] + (fa['tx'] - fa['fx']) * tf, fy=fa['fy'] + (fa['ty'] - fa['fy']) * tf, tx=tx_sel, ty=ty_sel, key=i, t0=time.time())
        def grid(gy):
            g_start = gy + edge
            if show_pods:
                g_start = iisu_fx.draw_home_pods(self, p, items, x0, cw, g_start)
            vis_k = 0
            for n, x in enumerate(items):
                rect = QRectF(x0 + (n % cols) * (size + gap), g_start + (n // cols) * (tile_h + gap), size, tile_h)
                if rect.bottom() > view.top() and rect.top() < view.bottom():
                    if n != i: self.tile(p, rect, x, n, False, vis_k)
                    vis_k += 1
            if fa['t0'] and self.CFG.get('motion') != 'reduced':
                tf = iisu_fx.spring(self, fa['t0'], self.dur(.22))
                if tf < 1 and THEME['glow']:
                    gx, gy_ = fa['fx'] + (fa['tx'] - fa['fx']) * tf, gy + fa['fy'] + (fa['ty'] - fa['fy']) * tf
                    self.box(p, QRectF(gx - .9 * u, gy_ - .9 * u, size + 1.8 * u, tile_h + 1.8 * u), .12 * size + .9 * u, faded(FOCUS, .18 * THEME['glow']))
            n = i
            self.tile(p, QRectF(x0 + (n % cols) * (size + gap), g_start + (n // cols) * (tile_h + gap), size, tile_h), items[n], n, True, 0)
            return g_start + (len(items) + cols - 1) // cols * (tile_h + gap) - gap + edge
        self.scroller(p, 'grid', view, grid)

    def draw_game_menu(self, p):
        """Per-game details & options sheet (Start button or '⋯' pill): description, emulator/core, profile, collections, hide."""
        gm = self.GAME_MENU
        g = next((x for x in self.L['games'] if x['id'] == gm['id']), None) if gm else None
        if not g:
            self.GAME_MENU = None
            return
        u, W, H = self.u, self.width(), self.height()
        x0, cw, bottom = 2.6 * u, W - 5.2 * u, H - 2.6 * u
        y = self.tabs(p, g['t'], [('Fertig', True, lambda: setattr(self, 'GAME_MENU', None))])
        rows = (self._art_picker_rows(g) if gm.get('art_picker')
                else self._patch_picker_rows(g) if gm.get('patch_picker')
                else self._game_menu_rows(g))
        sel = max(0, min(gm['i'], len(rows) - 1))
        area = QRectF(x0, y, cw, bottom - y)

        def paint_sheet(top):
            cy = top
            sub_parts = [self.sys_name(g)]
            if g.get('year'): sub_parts.append(str(g['year']))
            if g.get('genre'): sub_parts.append(g['genre'])
            if g.get('dev'): sub_parts.append(g['dev'])
            if g.get('ttb'): sub_parts.append(f'~{g["ttb"]:g} Std.')
            cy += self.text(p, '  ·  '.join(sub_parts), x0 + .4 * u, cy, ('u', 1.85, 600), FOCUS, cw - .8 * u) + .8 * u
            if g.get('desc'):
                dlines = self.wrap(g['desc'], ('u', 1.85, 400), cw - 3.6 * u, 5)
                dh = len(dlines) * 1.85 * u * 1.38 + 2.4 * u
                dbox = QRectF(x0, cy, cw, dh)
                self.box(p, dbox, 1.6 * u, PANEL, LINE)
                dy = cy + 1.2 * u
                for dl in dlines:
                    dy += self.text(p, dl, x0 + 1.8 * u, dy, ('u', 1.85, 400), MUTED, cw - 3.6 * u, lh=1.38)
                cy += dh + 1.6 * u
            rh = 5.8 * u
            box = QRectF(x0, cy, cw, len(rows) * rh)
            self.box(p, box, 1.8 * u, PANEL, LINE)
            for idx, (lbl, val, fn) in enumerate(rows):
                ry = cy + idx * rh
                if idx: p.fillRect(QRectF(x0 + 2 * u, ry, cw - 4 * u, max(1.0, .08 * u)), faded(TEXT, .08))
                rrect = QRectF(x0, ry, cw, rh)
                if idx == sel:
                    self.box(p, rrect.adjusted(.35 * u, .35 * u, -.35 * u, -.35 * u), 1.4 * u, faded(FOCUS, .16), FOCUS, .22 * u)
                is_play = idx == 0
                self.text(p, lbl, x0 + 2.2 * u, ry, ('u', 2.05, 700 if is_play else 500), FOCUS if is_play else TEXT, cw * .62, lh=rh / (2.05 * u))
                if val:
                    self.text(p, val, x0 + cw * .58, ry, ('u', 1.95, 600), FOCUS if idx == sel else MUTED, cw * .42 - 2.2 * u, 2, rh / (1.95 * u))
                self.hit(rrect, lambda idx=idx, fn=fn: (gm.__setitem__('i', idx), fn()), name='gopt:' + lbl)
            return cy + len(rows) * rh + 2 * u

        self.scroller(p, 'gmenu:' + g['id'], area, paint_sheet)

    def draw_stage(self, p, items, y, bottom):
        """Cocoon-style showcase carousel: large centre cover with soft floor reflection, flanked by scaled neighbours."""
        u, W, RUN = self.u, self.width(), self.RUN
        i, page_key = self.S['i'], (self.S['tab'], self.S['sys'], self.S.get('q', ''))
        sa = self.stage_anim
        if sa['page'] != page_key:
            sa.update({'from': float(i), 'to': float(i), 'page': page_key, 't0': 0.0})
        elif sa['to'] != float(i):
            ts = iisu_fx.spring(self, sa['t0'], self.dur(.30)) if sa['t0'] else 1.0
            cur = sa['from'] + (sa['to'] - sa['from']) * ts
            sa.update({'from': cur, 'to': float(i), 't0': time.time()})
        ts = iisu_fx.spring(self, sa['t0'], self.dur(.30)) if sa['t0'] else 1.0
        pos = (self.stage_drag['pos'] if self.stage_drag is not None
               else float(i) if self.CFG.get('motion') == 'reduced'
               else sa['from'] + (sa['to'] - sa['from']) * ts)
        seen = (self.S['tab'], self.S['sys'], self.S.get('q', ''), i, len(items))
        if self.lift[0] != seen[:4]: self.lift = (seen[:4], time.time())
        avail_h = bottom - y
        info_h = 11.5 * u
        stage_h = max(20 * u, avail_h - info_h)
        csize = min(30 * u, stage_h * .82)
        if self.stage_drag is not None:
            self.stage_drag['step'] = max(8.0 * u, csize * .72)
        cy = y + stage_h * .46
        cx = W / 2
        order = sorted([n for n in range(len(items)) if abs(n - pos) <= 3.35], key=lambda n: -abs(n - pos))
        for n in order:
            d = n - pos
            ad = abs(d)
            scale = max(.44, 1.0 - .21 * min(ad, 2.6))
            sz = csize * scale
            step = csize * .72
            ox = math.copysign(step * (min(ad, 1.0) + max(0.0, ad - 1.0) * .68), d) if ad > 1e-4 else 0.0
            rect = QRectF(cx + ox - sz / 2, cy - sz / 2 + ad * .55 * u, sz, sz)
            p.save()
            p.setOpacity(max(.28, 1.0 - .22 * min(ad, 3.0)))
            if n == i and ad < .35 and self.CFG.get('showcase_3d', True) and not items[n].get('kind'):
                _, sp_hex, mkind = iisu_fx.MEDIA_PROFILES.get(str(items[n].get('s') or '').lower(), (0.72, None, 'cart'))
                sp_col = QColor(sp_hex) if sp_hex else QColor(FOCUS)
                c_img = self.images.get(items[n]['cover'], round(sz), round(sz), 'square') if items[n].get('cover') else None
                iisu_fx._draw_media_peek(self, p, rect, mkind, sp_col, c_img if c_img else None, max(0.0, 1.0 - ad * 2.5))
            self.tile(p, rect, items[n], n, n == i and ad < .45, 0)
            if n == i and ad < .35:
                sheen = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + rect.height() * .26)
                sheen.setColorAt(0, rgba(255, 255, 255, .14)); sheen.setColorAt(1, rgba(255, 255, 255, 0))
                self.box(p, QRectF(rect.x(), rect.y(), rect.width(), rect.height() * .26), .12 * rect.width(), QBrush(sheen))
                refl_h = min(5.2 * u, bottom - info_h - rect.bottom() + 1.5 * u)
                if refl_h > 1.5 * u:
                    rrect = QRectF(rect.x() + .8 * u, rect.bottom() + .5 * u, rect.width() - 1.6 * u, refl_h)
                    rg = QLinearGradient(0, rrect.top(), 0, rrect.bottom())
                    rg.setColorAt(0, faded(FOCUS, .16)); rg.setColorAt(1, faded(FOCUS, 0))
                    self.box(p, rrect, .1 * sz, QBrush(rg))
            p.restore()
        it = items[i]
        held = bool(RUN and RUN.get('paused') and it['id'] == RUN['id'])
        played = self.L['played'].get(it['id']) or {}
        iy = bottom - info_h + .6 * u
        iy += self.text(p, it['t'], 6 * u, iy, ('u', 2.7, 700, -.015), TEXT, W - 12 * u, 1) + .35 * u
        sub = self.sys_name(it) + (f'  ·  {hours(played["secs"])}' if played.get('secs') else '') + ('  ·  ★ Favorit' if it['id'] in self.L['fav'] else '')
        iy += self.text(p, sub, 6 * u, iy, ('u', 1.85, 500), MUTED, W - 12 * u, 1) + 1.1 * u
        inst = it.get('inst')
        act_lbl = 'Fortsetzen' if held else 'Installieren' if inst == 'no' else 'Lädt noch' if inst == 'load' else 'Starten'
        bf = ('u', 2.0, 600)
        bw = self.width_of(act_lbl, bf) + 4.8 * u
        bh = 4.6 * u
        brect = QRectF((W - bw) / 2, min(iy, bottom - bh), bw, bh)
        self.capsule(p, brect, FOCUS)
        self.text(p, act_lbl, brect.x(), brect.y(), bf, INK, bw, 1, bh / (2.0 * u))
        self.hit(brect, lambda: self.go('ok'), name=act_lbl)
        if len(items) > 1:
            cnt = f'{i + 1} / {len(items)}'
            cf = ('u', 1.55, 600)
            cw_p = self.width_of(cnt, cf) + 2.2 * u
            crect = QRectF(brect.right() + 1.2 * u, brect.y() + .7 * u, cw_p, bh - 1.4 * u)
            if crect.right() < W - 3 * u:
                self.capsule(p, crect, faded(PANEL, .88), faded(TEXT, .1))
                self.text(p, cnt, crect.x(), crect.y(), cf, MUTED, cw_p, 1, crect.height() / (1.55 * u))

    def ingame(self, p, top=None, ach=True):
        """The panel while a game runs: title, sliders, RetroArch's buttons, achievements, quit. A deck with tabs of its
        own shows it below them (top) and may keep the achievements for a tab of their own (ach=False)."""
        u, RUN = self.u, self.RUN
        x0, cw, bottom = 2.6 * u, self.width() - 5.2 * u, self.height() - 2.6 * u
        y = (x0 if top is None else top)
        y += self.text(p, '● LÄUFT OBEN', x0, y, ('u', 1.5, 700, .14), LIVE, lh=1.6) + .4 * u
        y += self.text(p, RUN['t'], x0, y, ('u', 3.8, 700, -.02), TEXT, cw, lh=1.1, lines=2) + .6 * u
        tip = f'{self.sys_name(RUN)} · {RUN["emu"]} · seit {hours(time.time() - RUN["since"])} · {clock()}' + (f' · Akku {self.BATT["level"]} %{" (lädt)" if self.BATT.get("charging") else ""}' if self.BATT else '')
        y += self.text(p, tip, x0, y, ('u', 2), MUTED, cw, lh=1.45, lines=None) + 2 * u
        y = self.sliders(p, y)
        if RUN['emu'] == 'RetroArch':
            y = self.row_buttons(p, y, [(label, lambda k=k: self.post('api/retroarch', {'name': k})) for k, label in RA]) + 1.8 * u
        elif top is None:
            rec = (self.REC or {}).get('on')
            y = self.row_buttons(p, y, [('Zu Tandem', lambda: self.post('api/pause')),
                                        ('Foto', lambda: quick_view.shot(self)),
                                        ('Stopp' if rec else 'Aufnahme', lambda: quick_view.record(self, not rec)),
                                        ('Ton an' if self.MUTED else 'Ton aus', self.toggle_mute)]) + 1.8 * u
        if self.ACH and ach: self.scroller(p, 'ach', QRectF(x0, y, cw, bottom - 6.3 * u - 1.8 * u - y), lambda y: self.achievements(p, y))
        # tinted, not filled: it stays on screen for the whole game (OLED)
        return self.button(p, QRectF(x0, bottom - 6.3 * u, cw, 6.3 * u), 'Spiel beenden', self.confirm_quit, ('u', 2.2, 600), WARN, faded(WARN, .14), None, 1.4)

    def achievements(self, p, y):
        """The running game's RetroAchievements from y on (with tappable 📌 target pins); returns the y below them."""
        A, u, x0, cw = self.ACH, self.u, 2.6 * self.u, self.width() - 5.2 * self.u
        f, w = ('u', 1.9), cw - 3.2 * u
        if A.get('note'): return y + self.text(p, A['note'], x0, y, ('u', 2), MUTED, cw, lh=1.45, lines=None)
        pinned = set(A.get('pinned') or [])
        items_all = A.get('list') or []
        pin_items = [a for a in items_all if a.get('t') in pinned and not a.get('e')]
        if pin_items:
            self.text(p, '📌 ANGEHEFTETE ZIELE', x0, y, ('u', 1.4, 700, .09), FOCUS, cw)
            y += 2.3 * u
            for pa in pin_items:
                pr = QRectF(x0, y, cw, 5.4 * u)
                self.box(p, pr, 1.4 * u, faded(FOCUS, .12), faded(FOCUS, .55))
                self.text(p, '📌 ' + pa['t'], x0 + 1.5 * u, y + .7 * u, ('u', 1.82, 700), TEXT, w - 7 * u)
                self.text(p, pa.get('d') or '', x0 + 1.5 * u, y + 2.9 * u, ('u', 1.48, 400), MUTED, w - 2 * u)
                t_pin = pa['t']
                self.hit(pr, lambda t_p=t_pin: self.post('api/ach_pin', {'title': t_p}, then=lambda r: r and (A.update(pinned=r.get('pinned', [])), self.update())),
                         name='achpin:' + t_pin)
                y += 6.2 * u
            y += .6 * u
        self.spans(p, x0, y, [(f'Erfolge {A["earned"]} / {A["total"]}', ('u', 2, 600), TEXT), (f' · {A["points"]} Punkte', ('u', 2), MUTED)], 1.45)
        y += 2 * u * 1.45 + u
        for a in items_all:
            rows = self.wrap(a.get('d') or '', f, w, None)
            h = (1 + len(rows)) * 1.9 * u * 1.3 + 2.2 * u
            ar = QRectF(x0, y, cw, h)
            is_pin = a.get('t') in pinned and not a.get('e')
            self.box(p, ar, 1.6 * u, PANEL, FOCUS if is_pin else None)
            prefix = '✓ ' if a.get('e') else ('📌 ' if is_pin else '')
            self.text(p, prefix + a['t'], x0 + 1.6 * u, y + 1.1 * u, ('u', 1.9, 600), LIVE if a.get('e') else (FOCUS if is_pin else TEXT), w - 8 * u, lh=1.3)
            self.text(p, str(a.get('p', '')), x0 + 1.6 * u, y + 1.1 * u, ('u', 1.9, 600), FOCUS, w, 2, 1.3)
            for n, row in enumerate(rows): self.text(p, row, x0 + 1.6 * u, y + 1.1 * u + (n + 1) * 1.9 * u * 1.3, f, MUTED, lh=1.3)
            if not a.get('e') and a.get('t'):
                t_a = a['t']
                self.hit(ar, lambda t_p=t_a: self.post('api/ach_pin', {'title': t_p}, then=lambda r: r and (A.update(pinned=r.get('pinned', [])), self.update())),
                         name='ach:' + t_a)
            y += h + u
        return y - u

    def framed_cover(self, x, cover, size):
        """Composites a game cover through Cocoon's platform mask.png + overlay.png in Modern era (8-bit/16-bit use era frames)."""
        if self.side != 'bottom' or iisu_fx.era_mode() != 'modern' or not self.CFG.get('overlays', True) or x.get('kind') or x['s'] in ('app', 'term'):
            return cover, False
        ov = (self.L.get('overlays') or {}).get(x['s'])
        if not ov: return cover, False
        key = (x['cover'], ov['mask'], ov['overlay'], size)
        if key in self.comp_cache:
            self.comp_cache.move_to_end(key)
            return self.comp_cache[key], True
        mask = self.overlay_image(ov['mask'], size)
        over = self.overlay_image(ov['overlay'], size)
        if not mask or not over: return cover, False
        out = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(0)
        qp = QPainter(out)
        qp.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        qp.drawImage(0, 0, cover.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation) if cover.width() != size or cover.height() != size else cover)
        qp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        qp.drawImage(0, 0, mask.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation) if mask.width() != size or mask.height() != size else mask)
        qp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        qp.drawImage(0, 0, over.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation) if over.width() != size or over.height() != size else over)
        qp.end()
        self.comp_cache[key] = out
        while len(self.comp_cache) > 64: self.comp_cache.popitem(last=False)
        return out, True

    def tile(self, p, rect, x, n, on, vis_k=0):
        """A rounded tile with the cover (and Cocoon platform frame when present). The selected one rises smoothly, with a
        soft offset shadow, game-coloured glow, ring and specular sheen."""
        u, RUN, base = self.u, self.RUN, rect
        tp = 1.0
        if self.page_anim[1] and self.CFG.get('motion') != 'reduced':
            delay = min(.09, vis_k * .012)
            raw = (time.time() - self.page_anim[1] - delay) / self.dur(.20)
            if raw < 1:
                QTimer.singleShot(16, self.update)
                tp = 1 - (1 - max(0.0, raw)) ** 3
                rect = rect.adjusted(0, (1 - tp) * .65 * u, 0, (1 - tp) * .65 * u)
        t = iisu_fx.spring(self, self.lift[1], self.dur(.30)) if on else 0
        if on:
            grow = .015 + (.012 if self.CFG.get('motion') == 'reduced' else .034 * t)
            rise = 0 if self.CFG.get('motion') == 'reduced' else .42 * u * t
            rect = rect.adjusted(-grow * rect.width(), -grow * rect.height() - rise, grow * rect.width(), grow * rect.height() - rise)
        r = .12 * rect.width()
        p.save()
        if tp < 1: p.setOpacity(p.opacity() * (.45 + .55 * tp))
        if on:
            for k, a in ((1.6, .10), (.9, .16)): self.box(p, rect.adjusted(-k * u, -k * u + .9 * u, k * u, k * u + .9 * u), r + k * u, rgba(0, 0, 0, a * min(1.0, t)))
            if THEME['glow']: self.box(p, rect.adjusted(-1.1 * u, -1.1 * u, 1.1 * u, 1.1 * u), r + 1.1 * u, faded(FOCUS, .24 * THEME['glow'] * min(1.0, t)))
        size = max(16, round(base.width()))
        cover = self.images.get(x['cover'], size, size, 'square') if x.get('cover') else False
        framed = False
        if cover:
            comp, framed = self.framed_cover(x, cover, size)
            if x.get('inst'): p.setOpacity(p.opacity() * .4)  # not installed (yet): dimmed
            if framed:
                p.drawImage(rect, comp)
            else:
                self.box(p, rect, r, PANEL)
                brush = QBrush(comp)
                kx, ky = rect.width() / comp.width(), rect.height() / comp.height()
                brush.setTransform(brush.transform().translate(rect.x(), rect.y()).scale(kx, ky))
                self.box(p, rect, r, brush)
            if x.get('inst'): p.setOpacity(1.0 if tp >= 1 else (.45 + .55 * tp))
            if x.get('dup_cover'):
                sub_t = x['t'].split(' - ', 1)[-1].split(': ', 1)[-1].strip() or x['t']
                sf = ('u', 1.24, 700, -.01)
                band_h = 2.6 * u
                band = QRectF(rect.x() + .55 * u, rect.bottom() - band_h - .55 * u, rect.width() - 1.1 * u, band_h)
                self.box(p, band, .85 * u, rgba(8, 11, 18, .82), rgba(255, 255, 255, .16), 0.9)
                self.text(p, sub_t, band.x() + .65 * u, band.y(), sf, QColor('#f8fafc'), band.width() - 2.6 * u if framed else band.width() - 1.3 * u, 0, band_h / (1.24 * u))
        else:
            self.box(p, rect, r, QBrush(self.paint_of(x, rect)))
            if cover is False:
                if x.get('kind') == 'sys':
                    iisu_fx.draw_system_tile_art(self, p, rect, x)
                    rows = self.wrap(x['t'], ('u', 1.6, 700), rect.width() - 2.8 * u, 2)
                    lh = 1.6 * u * 1.2
                    for k, row in enumerate(rows):
                        self.text(p, row, rect.x() + 1.4 * u, rect.bottom() - 1.3 * u - (len(rows) - k) * lh, ('u', 1.6, 700), ON_ART, lh=1.2)
                elif x.get('s') in ('app', 'term'):
                    iisu_fx.draw_app_tile_art(self, p, rect, x, on=on)
                else:
                    self.text(p, x['t'][:1].upper(), rect.x() + 1.4 * u, rect.y() + .6 * u, ('u', 6, 700), rgba(255, 255, 255, .22), lh=1)
                    rows = self.wrap(x['t'], ('u', 1.6, 600), rect.width() - 2.8 * u, 2)
                    lh = 1.6 * u * 1.2
                    for k, row in enumerate(rows):
                        self.text(p, row, rect.x() + 1.4 * u, rect.bottom() - 1.3 * u - (len(rows) - k) * lh, ('u', 1.6, 600), ON_ART, lh=1.2)
        if not framed and not (x.get('kind') == 'sys' and cover):
            iisu_fx.draw_square_rim(self, p, rect, x, r, on=on)
        if on and t > 0:
            path = QPainterPath(); path.addRoundedRect(rect, (r * .65 if framed else r * THEME['radius']), (r * .65 if framed else r * THEME['radius']))
            p.save(); p.setClipPath(path, Qt.ClipOperation.IntersectClip)
            g = QLinearGradient(rect.topLeft(), QPointF(rect.x() + rect.width() * .55, rect.y() + rect.height() * .6))
            g.setColorAt(0, rgba(255, 255, 255, .2 * t)); g.setColorAt(.55, rgba(255, 255, 255, .04 * t)); g.setColorAt(1, rgba(255, 255, 255, 0))
            p.fillRect(rect, QBrush(g))
            p.restore()
        badge = str(x['n']) if x.get('kind') == 'sys' else ('↓' if x['inst'] == 'no' else '…' if x.get('pct') is None else f'{x["pct"]} %') if x.get('inst') else None
        if badge:
            f = ('u', 1.5, 700)
            w = self.width_of(badge, f) + 1.8 * u
            self.capsule(p, QRectF(rect.right() - .9 * u - w, rect.y() + .9 * u, w, 2.6 * u), rgba(0, 0, 0, .62))
            self.text(p, badge, rect.right() - .9 * u - w, rect.y() + .9 * u, f, ON_ART, w, 1, 2.6 / 1.5)
        elif not framed and not x.get('kind') and x['s'] not in ('app', 'term') and (iisu_fx.era_mode() != 'modern' or (not self.S['sys'] and self.S['tab'] == 0)):
            tag = x['s'].upper()[:6]
            era_t = iisu_fx.era_mode()
            tf = ('u', 1.15, 700, .04)
            tw = self.width_of(tag, tf) + 1.4 * u
            trect_b = QRectF(rect.right() - .7 * u - tw, rect.bottom() - 2.6 * u, tw, 1.9 * u)
            if era_t == '8bit':
                p.fillRect(trect_b, QColor('#090a14'))
                p.setPen(QPen(QColor('#ffd60a') if on else QColor('#ff3b30'), max(1.0, .14 * u)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(trect_b)
                self.text(p, tag, trect_b.x(), trect_b.y(), tf, QColor('#ffd60a') if on else ON_ART, tw, 1, 1.9 / 1.15)
            elif era_t == '16bit':
                self.box(p, trect_b, .55 * u, QColor('#161542'), QColor('#facc15') if on else QColor('#818cf8'), max(1.0, .13 * u))
                self.text(p, tag, trect_b.x(), trect_b.y(), tf, QColor('#facc15') if on else ON_ART, tw, 1, 1.9 / 1.15)
            else:
                self.capsule(p, trect_b, rgba(0, 0, 0, .66), rgba(255, 255, 255, .12))
                self.text(p, tag, trect_b.x(), trect_b.y(), tf, ON_ART, tw, 1, 1.9 / 1.15)
        held = RUN and RUN.get('paused') and x['id'] == RUN['id']
        if held or x['id'] in self.L['fav']:
            c = QPointF(rect.x() + 2.2 * u, rect.y() + 2.2 * u)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(rgba(0, 0, 0, .62))
            p.drawEllipse(c, 1.35 * u, 1.35 * u)
            p.setBrush(LIVE if held else FOCUS)
            if held:
                for k in (-1, 1): p.drawRoundedRect(QRectF(c.x() + k * .32 * u - .2 * u, c.y() - .55 * u, .4 * u, 1.1 * u), .12 * u, .12 * u)
            else:
                star = QPainterPath()
                for k in range(10):
                    rr, ang = (.78 if k % 2 == 0 else .34) * u, math.radians(-90 + 36 * k)
                    pt = QPointF(c.x() + rr * math.cos(ang), c.y() + rr * math.sin(ang))
                    star.lineTo(pt) if k else star.moveTo(pt)
                star.closeSubpath()
                p.drawPath(star)
        if x['id'] in (self.L.get('pinned') or ()) and self.S['tab'] == 0 and not self.S['sys']:
            pf = ('u', 1.12, 700, .06)
            pw = self.width_of('PIN', pf) + 1.4 * u
            pr = QRectF(rect.right() - .8 * u - pw, rect.y() + .8 * u, pw, 2.0 * u)
            self.capsule(p, pr, faded(FOCUS, .92))
            self.text(p, 'PIN', pr.x(), pr.y(), pf, INK, pw, 1, 2.0 / 1.12)
        if on:
            iisu_fx.draw_era_focus(self, p, rect, r, t, framed=framed)
        p.restore()
        def tap(n=n):
            if n == self.S['i']: self.go('ok')
            else: self.S['i'] = n; self.push()
        self.hit(base, tap, name=x['t'])
        if not x.get('kind') and x.get('s') not in ('app', 'term'):
            trect = base.intersected(self.clip) if self.clip is not None else base
            if self.xf is not None: trect = self.xf.mapRect(trect)
            if not trect.isEmpty(): self.tile_rects.append((trect, n))


def main():
    global ADDR, URL
    parser = argparse.ArgumentParser(description='Toravo Tandem, native front end')
    parser.add_argument('--screen', choices=('top', 'bottom'), required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8377')
    parser.add_argument('--window', help='WIDTHxHEIGHT: a plain window instead of full screen (for trying it on a desktop)')
    args = parser.parse_args()
    url = urlparse(args.url)
    ADDR = (url.hostname or '127.0.0.1', url.port or 8377)
    URL = f'http://{ADDR[0]}:{ADDR[1]}'
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
