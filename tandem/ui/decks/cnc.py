"""Command deck for Command & Conquer (Tiberian Dawn) and Red Alert on the bottom screen (the native port in ports/cnc,
the engine Thor Conquer).

Native port of the Android deck of "Thor Conquer" (ThorDeck.java, 0.5.0), drawn as the game's own sidebar: tab bar
(options, credits, side or what the top screen waits for), the radar in its housing (a tap moves the view) with REPAIR /
SELL / MAP, the order pad (control groups 1-4: tap picks, tap again looks, hold stores; select, stop, guard, scatter,
primary, deselect; jumps to units, base and the last alert; game speed; quick save and load), the power bar and the two
build strips (tap = build or place, tap again = hold, hold = cancel). L1/R1 on the controller move a ring through the
build items and A builds the ringed one (the engine does that and names the item). The sidebar art, the fonts and the
cameos are read by the engine from the player's own game files and sent over; until they arrive, and where a game has
none, the same layout is drawn as plain bevels.
Everything shown is the snapshot the engine sends over the deck socket (decks/portsocket.py, the engine's
common/thor_tandem.cpp); every press goes back as a command the engine runs through its own sidebar, radar or keyboard
code. Laid out in the art's own pixels (one is three pixels of the 1240 wide screen) and scaled.

Interface for tandem_ui (see DECKS there): Deck(window), paint(painter) -> bool, press(pos), close().
parse(), power_height() and ascii() are plain Python (no Qt) and carry the logic worth testing.
"""
import struct, threading, time, unicodedata

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QTransform

from decks.portsocket import Link

# Commands, flags and states (ThorCommandType, THOR_FLAG_*, THOR_STATE_* in the engine's common/thor.h)
CMD_BUILD, CMD_RADAR, CMD_REPAIR, CMD_SELL, CMD_KEY, _, CMD_TAKE_CONTROL, CMD_JUMP, CMD_GROUP, CMD_ORDER, CMD_SPEED, CMD_QUICK = range(1, 13)
(F_RADAR, F_REPAIR, F_SELL, F_PLACING, F_TARGETING, F_REPAIR_OK, F_AUTOPILOT, F_ALERT_KNOWN, F_ALERT, F_PRIMARY_OK, F_SAVE_OK,
 F_QUICKSAVE) = (1 << k for k in range(12))
ST_AVAILABLE, ST_BUILDING, ST_ON_HOLD, ST_READY, ST_DISABLED, ST_CHARGING = range(6)
HEADER, ITEM, SCANCODE_ESCAPE = 28, 6, 41
# Picture keys of the interface art: a font atlas (16 x 6 cells of ASCII 32..127) and one frame of a sidebar shape
KEY_FONT, KEY_ART, FONT_CELL, FONT_SMALL, FONT_TAB = 0x7E << 16, 0x7F << 16, 20, 0, 1
ART_SIDE_TOP, ART_RADAR, ART_RADAR_FRAME, ART_REPAIR, ART_SELL, ART_MAP, ART_POWERBAR, ART_POWER, ART_TABS, ART_STRIPUP, ART_STRIPDN = 0, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13
HOLD, CONFIRM = .45, 3.0  # seconds: a held cameo or button, an armed "tap again"
AW, TAB_H, LEFT, M = 1240 / 3, 16, 160, 8 / 3  # art pixels: the stage's width, the tab bar, the sidebar's width, a gap
# The order pad below the groups, row by row: key, label, the hint of a tap
ORDERS = (('select', 'AUSWAHL'), ('stop', 'STOPP'), ('guard', 'WACHE'), ('scatter', 'STREUEN'), ('primary', 'PRIMÄR'), ('deselect', 'ABWAHL'),
          ('units', 'EINHEITEN'), ('base', 'BASIS'), ('alert', 'ALARM'), ('speed', 'TEMPO'), ('save', 'SICHERN'), ('load', 'LADEN'))


def parse(d):
    """A state line of the game as the deck shows it, or None when no mission is being played (or the line is cut short)."""
    i = (d or {}).get('i') or []
    if not (d or {}).get('ingame') or len(i) < HEADER or i[0] < 4 or i[1] != 1: return None
    n = max(0, i[14]) + max(0, i[15])
    if len(i) < HEADER + n * ITEM: return None
    return {'td': d.get('game') == 'td', 'credits': i[2], 'power': i[3], 'drain': i[4], 'flags': i[5], 'map': i[6:10], 'view': i[10:14], 'side': i[16] & 1,
            'groups': i[21:25], 'speed': i[25], 'selected': i[26], 'group': i[27], 'pal': d.get('pal'), 'radar': d.get('radar'), 'focus': d.get('focus', -1),
            'pw': d.get('pw') or [0] * 6,
            'items': [dict(zip(('column', 'index', 'key', 'cost', 'state', 'progress'), i[o:o + ITEM])) for o in range(HEADER, HEADER + n * ITEM, ITEM)]}


def power_height(value, span, factor):
    """How high the sidebar's power bar stands for an amount of power (the game's PowerClass::Power_Height)."""
    v, left = 0.0, value
    while left > 0:
        v += (span - 2 - v) / factor * min(left, 100) / 100
        left -= 100
    return max(0, min(span - 2, v))


def ascii(text):
    """The game's fonts hold ASCII only: accents go."""
    return ''.join(ch for ch in unicodedata.normalize('NFD', text) if ' ' <= ch <= '~')


def color(argb): return QColor((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, argb >> 24)


def box(l, t, r, b): return QRectF(l, t, r - l, b - t)


def layout(td, ah):
    """The deck's rects in art pixels for a stage ah high (the Android deck's onSizeChanged)."""
    top = QRectF(0, TAB_H, LEFT, 166 if td else 160)
    L = {'menu': QRectF(0, 0, LEFT, TAB_H), 'credits': QRectF(LEFT, 0, LEFT, TAB_H), 'state': box(2 * LEFT, 0, AW, TAB_H), 'top': top,
         'radar': QRectF(16, TAB_H + 7, 128, 128) if td else QRectF(6, TAB_H + 7, 146, 130)}
    for key, (x, y, w, h) in zip(('repair', 'sell', 'zoom'), ((4, 146, 49, 16), (57, 146, 49, 16), (110, 146, 46, 16)) if td else ((18, 134, 41, 18), (63, 134, 41, 18), (108, 134, 41, 18))):
        L[key] = QRectF(x, top.top() + y, w, h)
    pad, status = top.bottom() + M, 44 / 3
    row, gw, bw = (ah - pad - M * 5) / 5, (LEFT - M * 5) / 4, (LEFT - M * 4) / 3
    for g in range(4): L['group', g] = QRectF(M + g * (gw + M), pad, gw, row)
    for n, (key, _) in enumerate(ORDERS): L[key] = QRectF(M + n % 3 * (bw + M), pad + (1 + n // 3) * (row + M), bw, row)
    L['status'] = box(LEFT, ah - status, AW - 50, ah)
    L['leave'] = box(AW - 50, ah - status, AW, ah)
    L['power'] = box(LEFT + M, TAB_H + M, LEFT + 76 / 3, ah - status - M)
    x, cw = L['power'].right() + M, (AW - M - L['power'].right() - M - M) / 2
    for c in range(2):
        panel = L['panel', c] = QRectF(x + c * (cw + M), TAB_H + M, cw, ah - status - M - TAB_H - M)
        L['strip', c] = box(panel.left() + 2, panel.top() + 12, panel.right() - 2, panel.bottom() - 30)
        L['up', c] = QRectF(panel.center().x() - 34, panel.bottom() - 29, 33, 28)
        L['down', c] = QRectF(panel.center().x() + 1, panel.bottom() - 29, 33, 28)
    return L


class Deck:
    def __init__(self, window):
        self.w = window
        self.m, self.game, self.alive, self.plain, self.metrics, self.faces = None, '', True, {}, {}, {}
        self.pics, self.names, self.radar, self.radar_asked, self.pal = {}, {}, None, None, None
        self.pressed, self.held, self.said, self.said_until, self.armed = None, False, '', 0.0, (None, 0.0)
        self.painted, self.waiting, self.areas, self.stage, self.ah, self.L = 0.0, False, [], None, 360.0, {}
        self.zoomed, self.cancel, self.shown, self.focus = False, (None, 0.0), None, -1
        self.link = Link((window.RUN.get('port') or {}).get('socket') or '', self.heard, self.block)

    def close(self):
        self.alive = False
        self.link.close()

    # ---- the game's data (on the link's thread) ------------------------------------------------------------------------
    def heard(self, d):
        if d is not None and 'v' not in d: return
        self.m = m = parse(d)
        if d: self.game = d.get('game') or self.game
        if not m:  # between missions the engine forgets what was asked for: ask again in the next one
            self.pics, self.radar, self.radar_asked, self.pal, self.zoomed = {k: v for k, v in self.pics.items() if v}, None, None, None, False
        elif m['pal'] != self.pal:  # another palette (a fade, another theatre): every picture again, the old one stays meanwhile
            self.pal, self.radar_asked = m['pal'], None
            for key in list(self.pics): self.link.send(f'pic {key}')
        if m and m['flags'] & F_RADAR and m['radar'] != self.radar_asked:
            self.radar_asked = m['radar']
            self.link.send('radar')
        if m:  # giving an item up takes two right clicks in the engine: hold first, abandon once it is on hold
            key, until = self.cancel
            item = next((it for it in m['items'] if it['key'] == key), None)
            if key is not None and (time.time() > until or (item and item['state'] == ST_ON_HOLD)):
                self.cancel = (None, 0.0)
                if item and item['state'] == ST_ON_HOLD: self.click(item, True)
        self.changed()

    def block(self, name, data):
        if len(data) < 4: return
        w, h = struct.unpack_from('<HH', data)
        img = QImage(data[4:4 + w * h * 4], w, h, w * 4, QImage.Format.Format_ARGB32).copy() if w and h and len(data) >= 4 + w * h * 4 else None  # copy: the bytes go
        if name == 'radar': self.radar = img
        elif name.startswith('pic:') and name[4:].isdigit():
            if img is not None or not self.pics.get(int(name[4:])): self.pics[int(name[4:])] = img if img is not None else False  # False: asked, there is none
            self.names[int(name[4:])] = data[4 + w * h * 4:].decode('latin-1')
        self.changed()

    def pic(self, key):
        """A picture from the player's game files (cameo, sidebar art, font atlas), or None while it is on its way (or there is none)."""
        if key not in self.pics:
            self.pics[key] = None
            self.link.send(f'pic {key}')
        return self.pics[key] or None

    def art(self, piece, frame=0):
        """One frame of the game's own interface art for the player's side."""
        return self.pic(KEY_ART | ((self.m['side'] << 7 | piece) << 8) | frame)

    def changed(self):
        """A repaint, ten a second at most (the processor is the game's): the last change of a burst is painted too."""
        wait = self.painted + .1 - time.time()
        if not self.alive or self.waiting: return
        if wait <= 0: return self.w.loaded.emit()
        self.waiting = True
        self.later(wait)

    def later(self, secs):
        timer = threading.Timer(secs, lambda: (setattr(self, 'waiting', False), self.alive and self.w.loaded.emit()))
        timer.daemon = True
        timer.start()

    def cmd(self, kind, a=0, b=0, c=0): self.link.send(f'cmd {kind} {a} {b} {c}')

    # ---- touch ----------------------------------------------------------------------------------------------------------
    def press(self, pos):
        """A finger down (pos) or up (None). The radar answers at once; a cameo, a group, SELECT or LOAD held long enough
        does its second thing, and its tap on release then does nothing."""
        if pos is None:
            self.pressed = None
            return self.changed()
        self.held = False
        at, m = self.stage.inverted()[0].map(pos) if self.stage else pos, self.m
        if m and self.L and self.L['radar'].contains(at) and self.radar is not None and m['flags'] & F_RADAR and m['map'][2] > 0:
            win = self.radar_window(m)
            d = self.radar_rect(win)
            if d.contains(at):
                self.cmd(CMD_RADAR, m['map'][0] + int(win.left() + (at.x() - d.left()) / d.width() * win.width()),
                         m['map'][1] + int(win.top() + (at.y() - d.top()) / d.height() * win.height()))
            return
        self.pressed = key = next((key for rect, key in reversed(self.areas) if rect.contains(at)), None)
        if key and key[0] in ('item', 'group', 'select', 'load'):
            timer = threading.Timer(HOLD, self.hold, (key,))
            timer.daemon = True
            timer.start()
        self.changed()

    def hold(self, key):
        m = self.m
        if self.pressed != key or not m or getattr(self.w, 'moved', False): return  # let go, or a strip is being dragged
        self.held = True
        if key[0] == 'group':
            if m['selected'] > 0: self.cmd(CMD_GROUP, key[1], 1); self.say(f'AUSWAHL ALS GRUPPE {key[1] + 1} GESPEICHERT')
            else: self.say('ERST OBEN EINHEITEN AUSWÄHLEN')
        elif key[0] == 'select': self.cmd(CMD_ORDER, 3); self.say('GANZE ARMEE GEWÄHLT')
        elif key[0] == 'load':
            if m['flags'] & F_QUICKSAVE: self.cmd(CMD_QUICK, 1); self.say('SPIELSTAND GELADEN')
            else: self.held = False  # nothing to load: the tap says why
        else:
            item = next((it for it in m['items'] if it['key'] == key[1]), None)
            if item and item['state'] in (ST_BUILDING, ST_ON_HOLD, ST_READY):
                if item['state'] == ST_BUILDING: self.cancel = (item['key'], time.time() + 1.5)
                self.click(item, True, f'{self.name(item)} - ABGEBROCHEN')
        self.changed()

    def name(self, item): return self.names.get(item['key']) or ''

    def click(self, item, right, text=None):
        """A click on a cameo as on the sidebar: left builds, resumes or places, right holds and then cancels."""
        self.cmd(CMD_BUILD, item['column'], item['index'], item['key'] << 1 | int(right))
        self.say(text or self.name(item) + (' - PAUSIERT' if right else ' - BEREIT' if item['state'] == ST_READY else ''))

    def say(self, text, secs=4):
        self.said, self.said_until = ascii(text), time.time() + secs
        self.changed(); self.later(secs + .1)

    def tap(self, fn):
        """What a tap does, unless the finger was held."""
        return lambda: None if self.held else fn()

    def twice(self, key):
        """True on the second tap on the same thing within CONFIRM seconds; the first one arms it."""
        now = time.time()
        if self.armed[0] == key and now - self.armed[1] < CONFIRM:
            self.armed = (None, 0.0)
            return True
        self.armed = (key, now)
        self.changed(); self.later(CONFIRM + .1)
        return False

    def is_armed(self, key): return self.armed[0] == key and time.time() - self.armed[1] < CONFIRM

    def order(self, key):
        """A tap on a button of the order pad."""
        m = self.m
        flags = m['flags']
        if key == 'select': self.cmd(CMD_JUMP, 2); self.say('EINHEITEN IM BILD GEWÄHLT - HALTEN = GANZE ARMEE')
        elif key in ('stop', 'guard', 'scatter'): self.cmd(CMD_ORDER, ('stop', 'guard', 'scatter').index(key))
        elif key == 'primary': self.cmd(CMD_ORDER, 5)
        elif key == 'deselect': self.cmd(CMD_ORDER, 4)
        elif key in ('units', 'base'): self.cmd(CMD_JUMP, int(key == 'base'))
        elif key == 'alert': self.cmd(CMD_JUMP, 4)
        elif key == 'speed': self.cmd(CMD_SPEED, 6 if m['speed'] <= 1 else min(6, m['speed'] - 1))  # one step faster, after the fastest the slowest
        elif key == 'save':
            if flags & F_SAVE_OK: self.cmd(CMD_QUICK, 0); self.say('SCHNELLSPEICHERN FERTIG')
            else: self.say('SCHNELLSPEICHERN GEHT IN KAMPAGNEN-MISSIONEN')
        elif key == 'load':
            self.say('LADEN HALTEN = ZURÜCK ZUM SPIELSTAND' if flags & F_QUICKSAVE else 'NOCH KEIN SCHNELLSPEICHERSTAND' if flags & F_SAVE_OK else 'SCHNELLSPEICHERN GEHT IN KAMPAGNEN-MISSIONEN')

    def enabled(self, key):
        m = self.m
        return {'stop': m['selected'] > 0, 'guard': m['selected'] > 0, 'scatter': m['selected'] > 0, 'primary': bool(m['flags'] & F_PRIMARY_OK),
                'deselect': m['selected'] > 0 or bool(m['flags'] & (F_REPAIR | F_SELL)), 'alert': bool(m['flags'] & F_ALERT_KNOWN),
                'save': bool(m['flags'] & F_SAVE_OK), 'load': bool(m['flags'] & F_QUICKSAVE)}.get(key, True)

    # ---- drawing helpers (art pixels) ------------------------------------------------------------------------------------
    def tones(self):
        """Light edge, face and dark edge of the plain look: green for Tiberian Dawn, steel for Red Alert (warmer for the Soviets)."""
        m = self.m
        td, soviet = (m['td'], m['side'] == 1) if m else (self.game == 'td', False)
        return (0xFF3CA428, 0xFF10200C, 0xFF0C3008) if td else (0xFFB0A090 if soviet else 0xFFA8A8B0, 0xFF4A3A34 if soviet else 0xFF484C54, 0xFF18181C)

    def area(self, r, key):
        """Names a rect for touch (it shows as pressed while the finger is on it); True while it is pressed."""
        self.areas.append((r, key))
        return self.pressed == key

    def bevel(self, p, r, sunken, fill):
        """A bevelled box in whole art pixels: raised (a button) or sunken (a slot, a pressed button)."""
        light, _, dark = self.tones()
        p.fillRect(r, color(dark if sunken else light))
        p.fillRect(box(r.left() + 1, r.top() + 1, r.right(), r.bottom()), color(light if sunken else dark))
        p.fillRect(box(r.left() + 1, r.top() + 1, r.right() - 1, r.bottom() - 1), color(fill))

    def plate(self, p, r, down):
        """A button of the order pad: a bevel with the tab bar's own metal as its face (pressed: the pressed tab)."""
        self.bevel(p, r, down, self.tones()[1])
        tab = self.art(ART_TABS, int(down))
        if tab is None or tab.width() < 64 or tab.height() < 10: return
        if self.faces.get(int(down), (None,))[0] is not tab:  # the plain middle of the tab, without knob and edges, mirrored into a tile
            crop = tab.copy(22, 3, tab.width() - 34, tab.height() - 6)
            tile = QImage(crop.width() * 2, crop.height() * 2, QImage.Format.Format_ARGB32)
            q = QPainter(tile)
            for n in range(4): q.drawImage(n % 2 * crop.width(), n // 2 * crop.height(), crop.mirrored(bool(n % 2), bool(n // 2)))
            q.end()
            self.faces[int(down)] = (tab, tile)
        brush = QBrush(self.faces[int(down)][1])
        brush.setTransform(QTransform.fromTranslate(r.left(), r.top()))
        p.fillRect(box(r.left() + 1, r.top() + 1, r.right() - 1, r.bottom() - 1), brush)

    def sliced(self, p, img, r, edge=12):
        """Art stretched over r; `edge` art pixels at both ends keep their size."""
        w, h, e = img.width(), img.height(), min(edge, r.width() / 2)
        p.drawImage(QRectF(r.left(), r.top(), e, r.height()), img, QRectF(0, 0, edge, h))
        p.drawImage(box(r.left() + e, r.top(), r.right() - e, r.bottom()), img, QRectF(edge, 0, w - 2 * edge, h))
        p.drawImage(QRectF(r.right() - e, r.top(), e, r.height()), img, QRectF(w - edge, 0, edge, h))

    def font(self, which):
        """One of the game's bitmap fonts as (atlas, left edge and width of each glyph, first row and height of the capitals); None until it is here."""
        atlas = self.pic(KEY_FONT | which) if self.m else None
        if atlas is None: return None
        if self.metrics.get(which, (None,))[0] is not atlas:
            bits, stride, left, width, top, bottom = bytes(atlas.constBits()), atlas.bytesPerLine(), [0] * 96, [0] * 96, FONT_CELL, 0
            for ch in range(1, 96):
                cx, cy = ch % 16 * FONT_CELL, ch // 16 * FONT_CELL
                rows = [[x for x in range(FONT_CELL) if bits[(cy + y) * stride + (cx + x) * 4 + 3]] for y in range(FONT_CELL)]
                used = [x for row in rows for x in row]
                if used: left[ch], width[ch] = min(used), max(used) - min(used) + 1
                if used and chr(ch + 32).isascii() and (chr(ch + 32).isupper() or chr(ch + 32).isdigit()):
                    top, bottom = min(top, next(y for y, row in enumerate(rows) if row)), max(bottom, max(y for y, row in enumerate(rows) if row))
            width[0] = max(2, width[ord('n') - 32] * 2 // 3)  # the space
            self.metrics[which] = (atlas, left, width, top, bottom - top + 1) if bottom > top else (atlas, None, None, 0, 0)
        return self.metrics[which] if self.metrics[which][1] else None

    def plain_font(self, which):
        if which not in self.plain:
            f = QFont('sans-serif')
            f.setPixelSize(100); f.setBold(True)  # set large and scaled when drawn: a size of a few art pixels has no hinting to lose
            self.plain[which] = (f, QFontMetricsF(f))
        return self.plain[which]

    def text_width(self, which, t, px):
        f = self.font(which)
        if not f: return self.plain_font(which)[1].horizontalAdvance(t) * px * (11 if which == FONT_TAB else 8) / 100
        return sum((f[2][ord(ch) - 32 if ' ' <= ch <= '\x7f' else 0] + 1) * px for ch in t) - px

    def text(self, p, which, t, x, cy, px=1.0, align=1, opacity=1.0, room=None):
        """Text in one of the game's fonts, its capitals centred on cy, a font pixel px art pixels large; align 0 left at x,
        1 centred, 2 right. With room it shrinks until it fits. Without the font (not here yet) a plain one."""
        f = self.font(which)
        if f: t = ascii(t)  # the game's fonts hold ASCII only
        while room and px > 1 / 3 and self.text_width(which, t, px) > room: px -= 1 / 6
        x -= self.text_width(which, t, px) * align / 2
        p.save()
        p.setOpacity(opacity)
        if not f:
            font, _ = self.plain_font(which)
            k = px * (11 if which == FONT_TAB else 8) / 100
            p.translate(x, cy + 36 * k); p.scale(k, k)
            p.setFont(font); p.setPen(color(0xFFE0E0E0)); p.drawText(QPointF(0, 0), t)
        else:
            atlas, left, width, top, height = f
            x, y = round(x * 3) / 3, round((cy - (top + height / 2) * px) * 3) / 3  # on whole screen pixels
            for ch in t:
                n = ord(ch) - 32
                if n and width[n]: p.drawImage(QRectF(x, y, width[n] * px, FONT_CELL * px), atlas, QRectF(n % 16 * FONT_CELL + left[n], n // 16 * FONT_CELL, width[n], FONT_CELL))
                x += (width[n] + 1) * px
        p.restore()

    def blink(self, period=.4):
        """True every other period; asks for the repaint that shows the change."""
        if not self.waiting:
            self.waiting = True
            self.later(period)
        return int(time.time() / period) % 2 == 0

    # ---- painting -----------------------------------------------------------------------------------------------------
    def paint(self, p):
        w, m = self.w, self.m
        k = w.width() / AW
        self.ah = w.height() / k
        self.stage = xf = QTransform().scale(k, k)
        self.painted, self.areas = time.time(), []
        p.save()
        p.fillRect(0, 0, w.width(), w.height(), color(0xFF000000))
        p.setTransform(xf)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)  # the game's pixel art stays crisp
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w.xf, w.zoom = xf, k  # taps arrive in window pixels
        try:
            if not m: self.idle(p)
            else:
                self.L = layout(m['td'], self.ah)
                self.tabs(p, m); self.top(p, m); self.pad(p, m); self.power(p, m); self.column(p, m, 0); self.column(p, m, 1); self.status(p, m)
        finally:
            w.xf, w.zoom = None, 1.0
            p.restore()
        return True

    def leave(self, p, r):
        """Ends the game and returns to Tandem: asks first."""
        armed = self.is_armed('quit')
        self.bevel(p, r, self.area(r, ('leave',)) or armed, 0xFF7A1A14 if armed else self.tones()[1])
        self.text(p, FONT_SMALL, 'NOCHMAL' if armed else 'BEENDEN', r.center().x(), r.center().y(), 1, 1, room=r.width() - 4)
        self.w.hit(r, lambda: self.twice('quit') and self.w.post('api/quit'), name='BEENDEN')

    def idle(self, p):
        cx, cy, td = AW / 2, self.ah / 2, self.game == 'td'
        self.text(p, FONT_TAB, 'COMMAND & CONQUER' if td else 'RED ALERT', cx, cy - 30, 3.2, room=AW - 40)
        self.text(p, FONT_SMALL, 'KOMMANDO-DECK - BEREITSCHAFT', cx, cy, 1.2, opacity=.6)
        self.text(p, FONT_SMALL, 'Bauleiste und Radar erscheinen hier, sobald eine Mission läuft.', cx, cy + 22, 1, opacity=.8, room=AW - 30)
        self.text(p, FONT_SMALL, 'Linker Stick = Zeiger - A = Klick - B = Rechtsklick - Rechter Stick = Karte - Select = Menü', cx, cy + 40, .8, opacity=.5, room=AW - 30)
        self.leave(p, QRectF(cx - 40, self.ah - 44, 80, 22))

    def tab(self, p, r, frame, down=False):
        img = self.art(ART_TABS, 1 if down else frame) or self.art(ART_TABS, frame)
        if img is not None: self.sliced(p, img, r)
        else: self.bevel(p, r, down, self.tones()[1])

    def tabs(self, p, m):
        L, flags, plain = self.L, m['flags'], 0 if m['td'] else 2
        self.tab(p, L['menu'], 0, self.area(L['menu'], ('menu',)))  # the game's own options menu
        self.text(p, FONT_TAB, 'Optionen', L['menu'].center().x(), L['menu'].center().y())
        self.w.hit(L['menu'], lambda: self.cmd(CMD_KEY, SCANCODE_ESCAPE), name='Optionen')
        if self.shown is None or abs(m['credits'] - self.shown) < 1: self.shown = m['credits']  # the counter ticks like the game's
        else:
            self.shown += (1 if m['credits'] > self.shown else -1) * max(1, abs(m['credits'] - self.shown) * .18)
            self.changed()
        self.tab(p, L['credits'], plain)
        self.text(p, FONT_TAB, str(round(self.shown)), L['credits'].center().x(), L['credits'].center().y())
        auto = bool(flags & F_AUTOPILOT)  # the side, or what the top screen is waiting for
        mode = ('AUTOPILOT' if auto else 'BAUEN' if flags & F_PLACING else 'ZIEL' if flags & F_TARGETING else 'REPARIEREN' if flags & F_REPAIR else 'VERKAUFEN' if flags & F_SELL
                else ('NOD' if m['side'] else 'GDI') if m['td'] else 'SOWJETS' if m['side'] else 'ALLIIERTE')
        self.tab(p, L['state'], plain, auto and (self.area(L['state'], ('state',)) or self.blink(.5)))
        self.text(p, FONT_TAB, mode, L['state'].center().x(), L['state'].center().y(), room=L['state'].width() - 12)
        if auto: self.w.hit(L['state'], lambda: self.cmd(CMD_TAKE_CONTROL), name='AUTOPILOT')

    def art_button(self, p, key, piece, label, on, enabled, fn):
        """One of the sidebar's own three buttons (frames: up, down, disabled); without art a labelled bevel."""
        r = self.L[key]
        down = (self.area(r, (key,)) and enabled) or on
        img = self.art(piece, 1 if down else 0) if enabled else self.art(piece, 2) or self.art(piece, 0)
        if img is not None:
            r.setWidth(img.width()); r.setHeight(img.height())  # the touch area is the art
            p.setOpacity(1 if enabled or self.art(piece, 2) is not None else .43)
            p.drawImage(r.topLeft(), img)
            p.setOpacity(1)
        else:
            self.bevel(p, r, down, self.tones()[1])
            self.text(p, FONT_SMALL, label, r.center().x(), r.center().y(), 2 / 3, opacity=1 if enabled else .43, room=r.width() - 4)
        if enabled: self.w.hit(r, fn, name=label)

    def top(self, p, m):
        """The radar housing with the map in it, and the sidebar's own three buttons."""
        L, flags, td = self.L, m['flags'], m['td']
        active = bool(flags & F_RADAR) and self.radar is not None and m['map'][2] > 0
        side = self.art(ART_SIDE_TOP)
        if side is None: self.bevel(p, L['top'], False, self.tones()[1])
        elif td:  # the sidebar art starts below the radar: only its button row is used here
            p.save(); p.setClipRect(L['top'], Qt.ClipOperation.IntersectClip); p.drawImage(QPointF(0, L['top'].top() + 144), side); p.restore()
        else: p.drawImage(L['top'].topLeft(), side)
        housing = self.art(ART_RADAR, 22 if active else 0) if td else self.art(ART_RADAR_FRAME, 1) if active else self.art(ART_RADAR)
        if housing is not None: p.drawImage(L['top'].topLeft(), housing)
        else: self.bevel(p, L['radar'].adjusted(-1, -1, 1, 1), True, 0xFF000000)
        if active: self.radar_screen(p, m)
        self.art_button(p, 'repair', ART_REPAIR, 'REPARIEREN', bool(flags & F_REPAIR), bool(flags & F_REPAIR_OK), lambda: self.cmd(CMD_REPAIR))
        self.art_button(p, 'sell', ART_SELL, 'VERKAUFEN', bool(flags & F_SELL), True, lambda: self.cmd(CMD_SELL))
        self.art_button(p, 'zoom', ART_MAP, 'KARTE', self.zoomed, active, lambda: setattr(self, 'zoomed', not self.zoomed))

    def radar_window(self, m):
        """The part of the map (in cells from the map's corner) the radar shows: all of it, or with MAP half of it around the view."""
        (mx, my, mw, mh), (vx, vy, vw, vh) = m['map'], m['view']
        if not self.zoomed: return QRectF(0, 0, mw, mh)
        ww, wh = mw / 2, mh / 2
        return QRectF(max(0, min(mw - ww, vx / 16 - mx + vw / 32 - ww / 2)), max(0, min(mh - wh, vy / 16 - my + vh / 32 - wh / 2)), ww, wh)

    def radar_rect(self, win):
        """Where that part is drawn: at its aspect ratio inside the housing."""
        area = self.L['radar']
        f = min(area.width() / max(1, win.width()), area.height() / max(1, win.height()))
        return QRectF(area.center().x() - win.width() * f / 2, area.center().y() - win.height() * f / 2, win.width() * f, win.height() * f)

    def radar_screen(self, p, m):
        win = self.radar_window(m)
        d, (mx, my, _, _), (vx, vy, vw, vh) = self.radar_rect(win), m['map'], m['view']
        p.fillRect(self.L['radar'], color(0xFF000000))
        p.drawImage(d, self.radar, QRectF(round(win.left()), round(win.top()), round(win.width()), round(win.height())))
        kx, ky = d.width() / win.width(), d.height() / win.height()
        p.save()
        p.setClipRect(d, Qt.ClipOperation.IntersectClip)
        p.setPen(QPen(color(0xFFFFFFFF), 1)); p.setBrush(Qt.BrushStyle.NoBrush)  # the game's own view box is white, too
        p.drawRect(QRectF(d.left() + (vx / 16 - mx - win.left()) * kx, d.top() + (vy / 16 - my - win.top()) * ky, vw / 16 * kx, vh / 16 * ky))
        p.restore()

    def pad(self, p, m):
        L = self.L
        for g in range(4):
            r, has = L['group', g], m['groups'][g] > 0
            self.plate(p, r, self.area(r, ('group', g)) or m['group'] == g)
            self.text(p, FONT_TAB, str(g + 1), r.center().x(), r.center().y() - (5 if has else 0), opacity=1 if has else .31)
            if has: self.text(p, FONT_TAB, str(m['groups'][g]), r.center().x(), r.bottom() - 8, 2 / 3)
            # tap = pick the group, tap again = look at it
            self.w.hit(r, self.tap(lambda g=g, has=has: self.cmd(CMD_GROUP, g, 2 if m['group'] == g else 0) if has else self.say(f'GRUPPE {g + 1} IST LEER - HALTEN SPEICHERT DIE AUSWAHL')),
                       name=f'group{g + 1}')
        for key, label in ORDERS:
            r, on = L[key], self.enabled(key)
            lit = key == 'alert' and m['flags'] & F_ALERT and self.blink()  # the base is under attack: blinks for 30 s
            down = (self.area(r, (key,)) and on) or bool(lit)
            self.plate(p, r, down)
            self.text(p, FONT_TAB, label + (f' {max(1, min(6, 7 - m["speed"]))}' if key == 'speed' else ''), r.center().x() + down, r.center().y() + down,
                      opacity=1 if on else .31, room=r.width() - 4)
            if on or key in ('save', 'load'): self.w.hit(r, self.tap(lambda key=key: self.order(key)), name=label)

    def power(self, p, m):
        """The game's power bar at the game's own scale, the drain marker beside it."""
        td, area = m['td'], self.L['power']
        span, factor = (220, 6) if td else (153, 5)
        ph, dh = power_height(m['power'], span, factor), power_height(m['drain'], span, factor)
        level = 2 if m['drain'] > m['power'] * 2 else 1 if m['drain'] > m['power'] else 0
        b0, b1 = self.art(ART_POWERBAR, 0), self.art(ART_POWERBAR, 1)
        if b0 is None or b1 is None:
            r = box(area.left() + 4, area.top(), area.right() - 4, area.bottom() - 16)
            self.bevel(p, r, True, 0xFF000000)
            u = (r.height() - 2) / span
            p.fillRect(box(r.left() + 1, r.bottom() - 1 - ph * u, r.right() - 1, r.bottom() - 1), color((0xFF30B030, 0xFFD8C020, 0xFFD02020)[level]))
            p.fillRect(box(r.left() - 2, r.bottom() - 1.5 - dh * u, r.right() + 2, r.bottom() - .5 - dh * u), color(0xFFFFFFFF))
            total, y = r.height(), r.top()
        else:
            second = 100 if td else 112
            # Tiberian Dawn's frames are longer than its bar: the game cuts them off at the screen's edge
            total, x, y = span if td else second + b1.height(), area.center().x() - b0.width() / 2, area.top()
            p.save(); p.setClipRect(QRectF(x, y, b0.width(), total), Qt.ClipOperation.IntersectClip)
            p.drawImage(QPointF(x, y), b0); p.drawImage(QPointF(x, y + second), b1)
            if td:  # the filled bar is art, too: its lower part is laid over the empty one
                bottom, f0, f1 = y + total - 1, self.art(ART_POWERBAR, 2 + level * 2), self.art(ART_POWERBAR, 3 + level * 2)
                if f0 is not None and f1 is not None and ph > 0:
                    p.setClipRect(box(x, bottom - ph - 3, x + b0.width(), bottom + 1), Qt.ClipOperation.IntersectClip)
                    p.drawImage(QPointF(x, y), f0); p.drawImage(QPointF(x, y + second), f1)
            p.restore()
            if not td:
                bottom = y + 175
                if ph > 0:
                    p.fillRect(box(x + 10, bottom - ph, x + 12, bottom + 1), color(0xFF000000 | m['pw'][level * 2]))
                    p.fillRect(box(x + 12, bottom - ph, x + 14, bottom + 1), color(0xFF000000 | m['pw'][level * 2 + 1]))
            marker = self.art(ART_POWER)
            if marker is not None: p.drawImage(QPointF(x + (0 if td else 2), bottom - dh - 4), marker)
        ty = min(area.bottom() - 10 / 3, y + total + 14 / 3)
        self.text(p, FONT_SMALL, str(m['power']), area.center().x(), ty, 2 / 3, room=area.width())
        self.text(p, FONT_SMALL, str(m['drain']), area.center().x(), ty + 22 / 3, 2 / 3, opacity=1 if level else .6, room=area.width())

    def column(self, p, m, col):
        """A build strip: structures or units, two cameos wide; more than fit can be dragged or stepped with the arrows."""
        L, key = self.L, f'cnc-col{col}'
        panel, area, items = L['panel', col], L['strip', col], [it for it in m['items'] if it['column'] == col]
        self.bevel(p, panel, True, 0xFF000000)
        self.text(p, FONT_SMALL, 'EINHEITEN' if col else 'GEBÄUDE', panel.left() + 4, panel.top() + 20 / 3, align=0)
        self.text(p, FONT_SMALL, str(len(items)), panel.right() - 4, panel.top() + 20 / 3, align=2, opacity=.63)
        cw = (area.width() - 2) / 2
        ch = cw * .75  # the cameos are 64 x 48
        cell = ch + 26 / 3 + 2
        focus = m['items'][m['focus']] if 0 <= m['focus'] < len(m['items']) else None
        if focus in items and m['focus'] != self.focus:  # the controller's ring moved: bring its item into view
            at = items.index(focus) // 2 * cell
            self.w.off[key] = max(at + cell - area.height(), min(at, self.w.off.get(key, 0)))
        if col: self.focus = m['focus']

        def tiles(top):
            for n, it in enumerate(items):
                r = QRectF(area.left() + n % 2 * (cw + 2), top + n // 2 * cell, cw, ch)
                if r.bottom() + 9 > area.top() and r.top() < area.bottom(): self.tile(p, m, it, r, area, it is focus)
            return top + -(-len(items) // 2) * cell
        self.w.scroller(p, key, area, tiles)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        off, most = self.w.off.get(key, 0), self.w.maxoff.get(key, 0)
        for name, piece, on, step in (('up', ART_STRIPUP, off > 0, -cell), ('down', ART_STRIPDN, off < most, cell)):
            r = L[name, col]
            down = self.area(r, (name, col)) and on
            img = (self.art(piece, 1 if down else 0) if on else self.art(piece, 2)) or self.art(piece, 0)
            if img is not None: p.drawImage(QPointF(r.center().x() - img.width() / 2, r.center().y() - img.height() / 2), img)
            else:
                self.bevel(p, r, down, self.tones()[1])
                self.text(p, FONT_SMALL, '^' if step < 0 else 'v', r.center().x(), r.center().y(), opacity=1 if on else .35)
            self.w.hit(r, lambda step=step: self.w.off.__setitem__(key, max(0, min(most, off + step))), name=f'{name}{col}')

    def tile(self, p, m, it, r, area, ring):
        state, img = it['state'], self.pic(it['key'])
        p.save()
        p.setClipRect(r, Qt.ClipOperation.IntersectClip)
        if img is not None: p.drawImage(r, img)
        else:
            p.fillRect(r, color(self.tones()[1]))
            self.text(p, FONT_SMALL, self.name(it), r.center().x(), r.center().y(), 2 / 3, room=r.width() - 2)
        if state == ST_DISABLED: p.fillRect(r, color(0xB0000000))
        elif state in (ST_BUILDING, ST_ON_HOLD, ST_CHARGING):  # the sidebar's clock: what is still to do stays dark, clockwise from 12 o'clock
            done, rad = it['progress'] / 1000, (r.width() ** 2 + r.height() ** 2) ** .5
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(0x98000000))
            p.drawPie(QRectF(r.center().x() - rad, r.center().y() - rad, rad * 2, rad * 2), round((90 - 360 * done) * 16), round(-360 * (1 - done) * 16))
        p.restore()
        pressed = self.area(r.intersected(area), ('item', it['key']))
        if pressed or ring or state == ST_READY:
            p.setPen(QPen(color(0xFFFFFFFF if pressed or ring else self.tones()[0]), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(-.5, -.5, .5, .5) if ring else r.adjusted(.5, .5, -.5, -.5))
        word = 'BEREIT' if state == ST_READY else 'ANGEHALTEN' if state == ST_ON_HOLD else None  # across the cameo, like the sidebar
        if word:
            tw = min(self.text_width(FONT_SMALL, word, 1), r.width() - 2)
            p.fillRect(box(r.center().x() - tw / 2 - 2, r.center().y() - 5, r.center().x() + tw / 2 + 2, r.center().y() + 5), color(0xA0000000))
            self.text(p, FONT_SMALL, word, r.center().x(), r.center().y(), room=r.width() - 2)
        if it['cost'] > 0:
            self.text(p, FONT_SMALL, f'${it["cost"]}', r.left() + 1, r.bottom() + 13 / 3, 2 / 3, 0, .43 if state == ST_DISABLED or it['cost'] > m['credits'] else 1)
        # a tap on an item under construction puts it on hold (like a right click), a tap on hold resumes
        self.w.hit(QRectF(r.left(), r.top(), r.width(), r.height() + 8), self.tap(lambda: self.click(it, state == ST_BUILDING)), name=f'item{it["key"]}')

    def status(self, p, m):
        r, flags = self.L['status'], m['flags']
        self.bevel(p, r, True, 0xFF000000)
        line = ('DIE KI SPIELT - AUTOPILOT ANTIPPEN ZUM ÜBERNEHMEN' if flags & F_AUTOPILOT else 'PLATZIEREN: OBEN AUF DIE KARTE KLICKEN' if flags & F_PLACING
                else 'ZIEL AUF DEM OBEREN BILDSCHIRM WÄHLEN' if flags & F_TARGETING else 'REPARIEREN: OBEN EIN GEBÄUDE ANKLICKEN' if flags & F_REPAIR
                else 'VERKAUFEN: OBEN EIN GEBÄUDE ANKLICKEN' if flags & F_SELL else self.said if time.time() < self.said_until
                else 'TIPPEN = BAUEN   NOCHMAL = PAUSE   LANG = ABBRUCH')
        self.text(p, FONT_SMALL, line, r.left() + 4, r.center().y(), align=0, room=r.width() - 8)
        self.leave(p, self.L['leave'])
