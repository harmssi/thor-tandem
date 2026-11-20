"""Command deck for Red Alert 2 / Yuri's Revenge on the bottom screen (the native port in ports/ra2, the engine Thor RA2).

Native port of the Android deck of "Thor RA2" (ThorDeck.java): the sidebar of the player's side, drawn with the sidebar
art, the HUD font and the cameos the game reads from the player's own files and sends over: credits, options and
diplomacy, the radar in its frame (a tap moves the view), repair / sell, the four build tabs, a cameo strip four wide
with the power bar (tap = build or place, buildings: tap again = hold, hold = hold / cancel), superweapon sockets, the
command bar (stop, guard, deploy, all of type, cheer, scatter, whole army, next unit, base, last alert), control groups
I to V (tap picks, hold sets), game speed, quick save / load (hold), ZOOM and leaving the game.
Everything shown is the snapshot the engine sends over the deck socket (decks/portsocket.py, the engine's thor.cpp);
every press goes back as a command the engine runs through its own sidebar code. Without the art the same layout is
drawn as plain plates. Laid out in the art's own pixels (462 wide: the 168 px sidebar and a 294 px strip) and scaled.

Interface for tandem_ui (see DECKS there): Deck(window), paint(painter) -> bool, press(pos), close().
parse() and pips() are plain Python (no Qt) and carry the logic worth testing.
"""
import struct, threading, time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPolygonF, QTransform

from decks.portsocket import Link

# Commands and the snapshot's numbers (thor::Command and the header in the engine's engine/thor.hpp)
CMD_BUILD, CMD_RADAR, CMD_REPAIR, CMD_SELL, CMD_MENU, CMD_TAB, CMD_SUPER, CMD_GROUP, CMD_HOT, CMD_SPEED, CMD_SAVE, CMD_LOAD, CMD_DIPLO = range(1, 14)
HOT_STOP, HOT_GUARD, HOT_SCATTER, HOT_DEPLOY, HOT_TYPE, HOT_ARMY, HOT_BASE, HOT_ALERT, HOT_NEXT, HOT_PREVIOUS, HOT_CHEER = range(1, 12)
(H_VERSION, H_IN_GAME, H_CREDITS, H_POWER_OUT, H_POWER_DRAIN, H_FLAGS, H_FACTION, H_TAB, H_TABS, H_RADAR_W, H_RADAR_H, H_VIEW_X, H_VIEW_Y, H_VIEW_W, H_VIEW_H,
 H_ITEMS, H_SUPERS, H_RADAR_SERIAL, H_GENERATION, H_GROUPS, H_SPEED, H_SELECTED, H_MISC) = range(23)
HEADER, ITEM, SUPER = 24, 7, 5
F_RADAR, F_REPAIR, F_SELL, F_PLACING, F_TARGETING, F_LOW_POWER, F_RADAR_BUILDING, F_LOCKED, F_PAUSED = (1 << k for k in range(9))
M_QUICK_SAVE, M_ALERTS, M_CAMPAIGN = 1, 2, 4
ST_AVAILABLE, ST_BUILDING, ST_ON_HOLD, ST_READY, ST_DISABLED = range(5)
# Picture keys: (kind << 16) | index; chrome = a piece of the side's sidebar art, index = (piece << 8) | frame
KIND_SUPER, KIND_CHROME, KIND_GLYPH = 2, 3, 4
(CH_CREDITS, CH_TOP, CH_RADAR, CH_SIDE1, CH_SIDE2, CH_SIDE3, CH_TAB0, _, _, _, CH_REPAIR, CH_SELL, CH_POWERP, CH_OPTBTN, CH_DIPLOBTN, CH_ADDON, CH_SIDEBTTN,
 CH_BUTTON0) = range(18)
HOLD, CONFIRM = .45, 3.0  # seconds: a held cameo or group, an armed "tap again"
AW, SB, ROWS, ROW, BAR_Y, BTN_W, BTN_H = 462, 168, 5, 50, 250, 52, 32  # the sidebar's own numbers, in art pixels
BAR_X, STATUS_Y = SB + 17, BAR_Y + 4 * BTN_H
TAB_NAMES = ('Gebäude', 'Verteidigung', 'Infanterie', 'Fahrzeuge')
# The command bar: action, the game's own button art (buttonNN.shp) or None = an icon of ours, name
HOTS = ((HOT_STOP, 8, 'Stopp'), (HOT_GUARD, 6, 'Bewachen'), (HOT_DEPLOY, 4, 'Aufstellen'), (HOT_TYPE, 3, 'Alle vom Typ'), (HOT_CHEER, 10, 'Jubeln'),
        (HOT_SCATTER, None, 'Verteilen'), (HOT_ARMY, None, 'Armee'), (HOT_NEXT, None, 'Nächste'), (HOT_BASE, None, 'Basis'), (HOT_ALERT, None, 'Alarm'))
# Icons of ours on a 28x28 grid, as lines: scatter, army, next unit, base, alert, slower, faster, save, load
TRAY = [(3, 17), (3, 24), (25, 24), (25, 17)]
ICONS = {'Verteilen': [l for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)) for l in ([(14 + dx * 4, 14 + dy * 4), (14 + dx * 11, 14 + dy * 11)],
                                                                                    [(14 + dx * 11, 14 + dy * 5), (14 + dx * 11, 14 + dy * 11), (14 + dx * 5, 14 + dy * 11)])],
         'Armee': [[(4, 9 + q * 7), (14, 3 + q * 7), (24, 9 + q * 7)] for q in range(3)],
         'Nächste': [[(3, 14), (19, 14)], [(12, 6), (20, 14), (12, 22)], [(25, 5), (25, 23)]],
         'Basis': [[(3, 14), (14, 4), (25, 14)], [(6, 12), (6, 24), (22, 24), (22, 12)], [(12, 24), (12, 17), (16, 17), (16, 24)]],
         'Alarm': [[(14, 3), (26, 24), (2, 24), (14, 3)], [(14, 10), (14, 17)], [(14, 20.5), (14, 21)]],
         'Langsamer': [[(22, 5), (11, 14), (22, 23)], [(13, 5), (2, 14), (13, 23)]], 'Schneller': [[(6, 5), (17, 14), (6, 23)], [(15, 5), (26, 14), (15, 23)]],
         'Speichern': [[(14, 2), (14, 16)], [(8, 10), (14, 16), (20, 10)], TRAY], 'Laden': [[(14, 17), (14, 3)], [(8, 9), (14, 3), (20, 9)], TRAY]}
SUPER_NAMES = {1: 'Atomrakete', 2: 'Eiserner Vorhang', 3: 'Wettersturm', 4: 'Chronosphäre', 6: 'Fallschirmjäger', 7: 'Fallschirmjäger', 8: 'Psycho-Dominator',
               9: 'Spionageflugzeug', 10: 'Genmutator', 11: 'Schutzschild'}


def parse(d):
    """A state line of the game as the deck shows it, or None when no game is being played (or the line is cut short)."""
    i = (d or {}).get('i') or []
    if not (d or {}).get('ingame') or len(i) < HEADER or i[H_IN_GAME] != 1: return None
    n, s, g = max(0, i[H_ITEMS]), max(0, i[H_SUPERS]), max(0, min(5, i[H_GROUPS]))
    at_s = HEADER + n * ITEM
    at_g = at_s + s * SUPER
    if len(i) < at_g + g * 2: return None
    return {'credits': i[H_CREDITS], 'out': i[H_POWER_OUT], 'drain': i[H_POWER_DRAIN], 'flags': i[H_FLAGS], 'side': i[H_FACTION], 'tab': max(0, min(3, i[H_TAB])),
            'tabs': i[H_TABS], 'radar': (i[H_RADAR_SERIAL], i[H_RADAR_W], i[H_RADAR_H]), 'view': i[H_VIEW_X:H_VIEW_H + 1], 'gen': i[H_GENERATION],
            'speed': i[H_SPEED], 'selected': i[H_SELECTED], 'misc': i[H_MISC], 'zoom': d.get('zoom') or 100,
            'items': [dict(zip(('key', 'cost', 'state', 'progress', 'queued', 'tab'), i[o:o + 6])) for o in range(HEADER, at_s, ITEM)],
            'supers': [dict(zip(('key', 'ready', 'progress', 'seconds'), i[o:o + 4])) for o in range(at_s, at_g, SUPER)],
            'groups': [(i[at_g + k * 2], i[at_g + k * 2 + 1]) if k < g else (0, 0) for k in range(5)]}


def pips(total, out, drain, blink=False):
    """The sidebar's power column from the bottom up, a frame of powerp.shp per pip: 0 empty, 1 green, 2 yellow (the
    last 100 spare), 3 red (in use), 4 white (the blink of an outage). The column fills as the base grows."""
    power = out + drain
    used = total - max(0, min(total - 1, int(total * 400 / (power + 400))))
    if not power: used = 0
    spare = max(0, out - drain)
    yellow_amount = min(spare, 100)
    denom = drain + spare
    red = round(used * drain / denom) if denom else 0
    yellow = round(used * yellow_amount / denom) if denom else 0
    return [4 if drain > out and k < used and blink else 3 if k < red else 2 if k < red + yellow else 1 if k < used else 0 for k in range(total)]


def speed_label(speed):
    """GameSpeed 0..6 as the Options slider counts it: logic frames a second / 15."""
    return '-' if speed < 0 else f'{(60 if speed <= 0 else 60 / speed) / 15:.1f}'.removesuffix('.0') + 'x'


def color(argb): return QColor((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, argb >> 24)


def alpha(rgb, a): return (rgb & 0xFFFFFF) | round(a * 255) << 24


def box(l, t, r, b): return QRectF(l, t, r - l, b - t)


def cell(row, col): return QRectF(BAR_X + col * BTN_W, BAR_Y + row * BTN_H, BTN_W, BTN_H)


RADAR_VIEW, STRIP = box(16, 49, 156, 157), QRectF(SB, 0, AW - SB, ROWS * ROW)


class Deck:
    def __init__(self, window):
        self.w = window
        self.m, self.alive, self.fonts, self.tints = None, True, {}, {}
        self.pics, self.names, self.radar, self.radar_asked, self.gen, self.side = {}, {}, None, None, None, None
        self.pressed, self.held, self.said, self.said_until, self.armed = None, False, '', 0.0, (None, 0.0)
        self.painted, self.waiting, self.areas, self.stage, self.ah = 0.0, False, [], None, 402.0
        self.link = Link((window.RUN.get('port') or {}).get('socket') or '', self.heard, self.block)

    def close(self):
        self.alive = False
        self.link.close()

    # ---- the game's data (on the link's thread) ------------------------------------------------------------------------
    def heard(self, d):
        if d is not None and 'v' not in d: return
        self.m = m = parse(d)
        if d is None:  # what was asked for is lost: ask again
            self.pics, self.radar_asked = {k: v for k, v in self.pics.items() if v is not None}, None
        if m and m['gen'] != self.gen:  # a new game: the numbers mean other things now
            self.gen, self.pics, self.names, self.radar, self.radar_asked = m['gen'], {}, {}, None, None
        if m and m['side'] != self.side:  # the art differs per side
            self.side, self.pics = m['side'], {k: v for k, v in self.pics.items() if k >> 16 != KIND_CHROME}
        if m and m['flags'] & F_RADAR and m['radar'] != self.radar_asked:
            self.radar_asked = m['radar']
            self.link.send('radar')
        self.changed()

    def block(self, name, data):
        if len(data) < 4: return
        w, h = struct.unpack_from('<HH', data)
        img = QImage(data[4:4 + w * h * 4], w, h, w * 4, QImage.Format.Format_ARGB32).copy() if w and h and len(data) >= 4 + w * h * 4 else None  # copy: the bytes go
        if name == 'radar': self.radar = img
        elif name.startswith('pic:') and name[4:].isdigit():
            self.pics[int(name[4:])] = img if img is not None else False  # False: asked, there is none
            self.names[int(name[4:])] = data[4 + w * h * 4:].decode('utf-8', 'replace')
        self.changed()

    def pic(self, key):
        """A picture from the player's game files (cameo, sidebar art, font glyph), or None while it is on its way (or there is none)."""
        if key not in self.pics:
            self.pics[key] = None
            self.link.send(f'pic {key}')
        return self.pics.get(key) or None

    def art(self, piece, frame=0): return self.pic(KIND_CHROME << 16 | piece << 8 | frame)

    def has_art(self, piece): return self.pics.get(KIND_CHROME << 16 | piece << 8) is not False

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
        """A finger down (pos) or up (None). The radar answers at once; a cameo, a group or LOAD held long enough does
        its second thing, and its tap on release then does nothing."""
        if pos is None:
            self.pressed = None
            return self.changed()
        self.held = False
        at, m = self.stage.inverted()[0].map(pos) if self.stage else pos, self.m
        if m and RADAR_VIEW.contains(at) and self.radar is not None and m['flags'] & F_RADAR:
            d = self.radar_rect(m)
            u, v = (at.x() - d.left()) / d.width(), (at.y() - d.top()) / d.height()
            if 0 <= u <= 1 and 0 <= v <= 1: self.cmd(CMD_RADAR, round(u * 65535), round(v * 65535))
            return
        self.pressed = key = next((key for rect, key in reversed(self.areas) if rect.contains(at)), None)
        if key and key[0] in ('item', 'group', 'load'):
            timer = threading.Timer(.7 if key[0] == 'load' else HOLD, self.hold, (key,))
            timer.daemon = True
            timer.start()
        self.changed()

    def hold(self, key):
        m = self.m
        if self.pressed != key or not m or getattr(self.w, 'moved', False): return  # let go, or the strip is being dragged
        self.held = True
        if key[0] == 'group':
            self.cmd(CMD_GROUP, key[1] + 1, 1)
            self.say(f'Auswahl ist jetzt Gruppe {key[1] + 1}')
        elif key[0] == 'load':
            if m['misc'] & M_QUICK_SAVE: self.cmd(CMD_LOAD); self.say('Lade Schnellspeicherstand …')
        else:
            item = next((it for it in m['items'] if it['key'] == key[1]), None)
            if item: self.build(item, True)
        self.changed()

    def build(self, item, right):
        """A click on a cameo as on the sidebar: left starts, queues or places, right holds and then cancels."""
        self.cmd(CMD_BUILD, item['tab'], item['key'] & 0xFFFF, int(right))
        name, state = self.names.get(item['key']) or '', item['state']
        self.say((('Abgebrochen: ' if state in (ST_ON_HOLD, ST_READY) else 'Angehalten: ') if right else 'Platzieren: ' if state == ST_READY else '') + name)

    def say(self, text, secs=4):
        self.said, self.said_until = text, time.time() + secs
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

    # ---- drawing helpers (art pixels) ------------------------------------------------------------------------------------
    def accent(self): return (0xFF6EB4FF, 0xFFF2B32E, 0xFFC9A0FF)[self.m['side'] if self.m and 0 <= self.m['side'] <= 2 else 0]

    def area(self, r, key):
        """Names a rect for touch (it lights up while the finger is on it); True while it is pressed."""
        self.areas.append((r, key))
        return self.pressed == key

    def draw(self, p, img, x, y): p.drawImage(QPointF(x, y), img)

    def plate(self, p, r, lit=False):
        """The look without the game's art: a bevelled steel plate, lit in the side's colour."""
        p.fillRect(r, color(alpha(self.accent(), .55) if lit else 0xFF3C424B))
        p.fillRect(QRectF(r.left(), r.top(), r.width(), .6), color(0x66FFFFFF)); p.fillRect(QRectF(r.left(), r.top(), .6, r.height()), color(0x66FFFFFF))
        p.fillRect(QRectF(r.left(), r.bottom() - .6, r.width(), .6), color(0xAA000000)); p.fillRect(QRectF(r.right() - .6, r.top(), .6, r.height()), color(0xAA000000))

    def piece(self, p, piece, frame, x, y, w, h):
        """One piece of the sidebar art at (x, y); without art a plate of the piece's size."""
        img = self.art(piece, frame) or (self.art(piece) if frame else None)
        if img is not None: self.draw(p, img, x, y)
        elif not self.has_art(piece): self.plate(p, QRectF(x, y, w, h), frame == 1)

    def font(self, size):
        if size not in self.fonts:
            f = QFont('sans-serif')
            f.setPixelSize(100); f.setBold(True)  # set large and scaled when drawn: a size of a few art pixels has no hinting to lose
            self.fonts[size] = (f, QFontMetricsF(f), size / 100)
        return self.fonts[size]

    def caption(self, p, text, cx, baseline, size, argb, room, align=1):
        """A small caption in a plain font (any language), shrunk to fit; align 0 left, 1 centred, 2 right."""
        f, fm, k = self.font(size)
        k = min(k, room / max(1, fm.horizontalAdvance(text)))
        p.save()
        p.translate(cx - fm.horizontalAdvance(text) * k * align / 2, baseline); p.scale(k, k)
        p.setFont(f); p.setPen(color(argb)); p.drawText(QPointF(0, 0), text)
        p.restore()

    def glyph(self, ch, argb):
        """A character of the game's HUD font in a colour; None while on its way, False when the font has none."""
        img = self.pic(KIND_GLYPH << 16 | ord(ch)) if ord(ch) < 128 else False
        if not img: return False if self.pics.get(KIND_GLYPH << 16 | ord(ch), False) is False else None
        if (ch, argb) not in self.tints:
            tinted = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
            tinted.fill(color(argb | 0xFF000000))
            q = QPainter(tinted)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply); q.drawImage(0, 0, img)  # the font is white with a shade
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn); q.drawImage(0, 0, img)
            q.end()
            self.tints[ch, argb] = tinted
        return self.tints[ch, argb]

    def text(self, p, t, x, y, argb, align=1, shadow=False):
        """Text in the game's HUD font (16 px cell), cell top at y; align 0 left, 1 centred, 2 right of x. What the font
        cannot spell is drawn as a caption."""
        glyphs = [None if ch == ' ' else self.glyph(ch, argb) for ch in t]
        if any(g is False for g in glyphs) or not self.m:  # no game yet: nothing answers a request for the font
            if shadow: self.caption(p, t, x + .7, y + 12.2, 10.5, 0xFF000000, 200, align)
            return self.caption(p, t, x, y + 11.5, 10.5, argb, 200, align)
        width = sum(g.width() if g else 8 for g in glyphs)
        left = round(x - width * align / 2)
        if shadow: p.fillRect(QRectF(left - 2, y + 1, width + 3, 12), color(0xB0000000))  # on a picture: a dark plate keeps the thin strokes readable
        for g in glyphs:
            if g: self.draw(p, g, left, y)
            left += g.width() if g else 8

    def clock(self, p, r, done, argb):
        """The sidebar's build clock: the part still to do stays dark, clockwise from 12 o'clock."""
        rad = (r.width() ** 2 + r.height() ** 2) ** .5
        p.save()
        p.setClipRect(r, Qt.ClipOperation.IntersectClip)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(argb))
        p.drawPie(QRectF(r.center().x() - rad, r.center().y() - rad, rad * 2, rad * 2), round((90 - 360 * done) * 16), round(-360 * (1 - done) * 16))
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
        w.xf, w.zoom = xf, k  # taps arrive in window pixels
        try:
            if not m: self.idle(p)
            else: self.head(p, m); self.supers(p, m); self.foot(p, m); self.strip(p, m); self.bar(p, m); self.status(p, m)
        finally:
            w.xf, w.zoom = None, 1.0
            p.restore()
        return True

    def button(self, p, r, key, label, fn, armed=False):
        """A plate with a name, in the sidebar's own button art where there is one."""
        down = self.area(r, key) or armed
        img = self.art(CH_SIDEBTTN, int(down))
        if img is not None and abs(img.width() - r.width()) < 2: self.draw(p, img, r.left(), r.top())
        else: self.plate(p, r, down)
        self.text(p, label, r.center().x(), r.center().y() - 7.5, 0xFFFFFFFF)
        self.w.hit(r, fn, name=label)

    def leave(self, p, r):
        """Ends the game and returns to Tandem: asks first."""
        armed = self.is_armed('quit')
        self.button(p, r, ('leave',), 'NOCHMAL TIPPEN' if armed else 'BEENDEN', lambda: self.twice('quit') and self.w.post('api/quit'), armed)

    def idle(self, p):
        cx = AW / 2
        self.caption(p, 'RED ALERT 2', cx, self.ah / 2 - 20, 34, 0xFFE8B04A, AW - 40)
        self.caption(p, 'Oben im Menü ein Gefecht oder eine Kampagne starten', cx, self.ah / 2 + 8, 10, 0xFFA7ABB3, AW - 40)
        self.caption(p, 'Stick = Zeiger · A = Klick · B = Rechtsklick · Steuerkreuz = von Knopf zu Knopf', cx, self.ah / 2 + 26, 7.5, 0xFF6B7078, AW - 40)
        self.leave(p, QRectF(cx - 62.5, self.ah - 60, 125, 25))

    def cap_button(self, p, r, key, piece, on, label, fn):
        """A sidebar button with its own art (frame 1 = pressed / armed); without art a labelled plate."""
        on = self.area(r, key) or on
        if self.has_art(piece): self.piece(p, piece, int(on), r.left(), r.top(), r.width(), r.height())
        else:
            self.plate(p, r, on)
            self.caption(p, label, r.center().x(), r.center().y() + 2.4, 6.5, 0xFFFFFFFF, r.width() - 4)
        self.w.hit(r, fn, name=label)

    def head(self, p, m):
        """Credits, options / diplomacy, radar, repair / sell, tabs."""
        sov, flags = m['side'] != 0, m['flags']  # Yuri shares the Soviet geometry
        self.piece(p, CH_CREDITS, 0, 0, 0, SB, 16)
        self.text(p, str(m['credits']), 84, 1, (0xFFA4D2FF, 0xFFFFFF00, 0xFFE2C4FF)[max(0, min(2, m['side']))])
        self.piece(p, CH_TOP, 0, 0, 16, SB, 32)
        x, y, h = (14, 21, 22) if sov else (11, 20, 18)
        self.cap_button(p, QRectF(x, y, 72, h), ('menu',), CH_OPTBTN, bool(flags & F_PAUSED), 'Menü', lambda: self.cmd(CMD_MENU))
        self.cap_button(p, QRectF(x + 72, y, 72, h), ('diplo',), CH_DIPLOBTN, False, 'Einsatz' if m['misc'] & M_CAMPAIGN else 'Bündnisse', lambda: self.cmd(CMD_DIPLO))
        self.radar_screen(p, m)
        self.piece(p, CH_SIDE1, 0, 0, 158, SB, 69)
        repair, sell = (QRectF(33, 165, 52, 32), QRectF(85, 165, 52, 32)) if sov else (QRectF(20, 166, 64, 31), QRectF(84, 166, 64, 31))
        self.cap_button(p, repair, ('repair',), CH_REPAIR, bool(flags & F_REPAIR), 'Reparieren', lambda: self.cmd(CMD_REPAIR))
        self.cap_button(p, sell, ('sell',), CH_SELL, bool(flags & F_SELL), 'Verkaufen', lambda: self.cmd(CMD_SELL))
        for i in range(4):
            has, active, ready = m['tabs'] >> i & 1, i == m['tab'], m['tabs'] >> (4 + i) & 1
            r = QRectF(20 + 32 * i, 197, 32, 28) if sov else QRectF(26 + 29 * i, 197, 28, 27)
            if self.has_art(CH_TAB0 + i): self.piece(p, CH_TAB0 + i, 2 if not has else (4 if active else 3) if ready and self.blink() else int(active), r.left(), r.top(), r.width(), r.height())
            else:
                self.plate(p, r, active)
                self.caption(p, TAB_NAMES[i][0], r.center().x(), r.center().y() + 4, 11, 0xFFFFFFFF if has else 0xFF6B7078, r.width())
            if has: self.w.hit(r, lambda i=i: (self.cmd(CMD_TAB, i), self.say(TAB_NAMES[i])), name=TAB_NAMES[i])

    def radar_rect(self, m):
        """The radar picture at its aspect ratio inside the radar screen."""
        _, rw, rh = m['radar']
        f = min(RADAR_VIEW.width() / max(1, rw), RADAR_VIEW.height() / max(1, rh))
        return QRectF(RADAR_VIEW.center().x() - rw * f / 2, RADAR_VIEW.center().y() - rh * f / 2, rw * f, rh * f)

    def radar_screen(self, p, m):
        frames = m['misc'] >> 8 & 255
        if not (m['flags'] & F_RADAR and self.radar is not None and m['radar'][1] > 0 and m['radar'][2] > 0):
            self.piece(p, CH_RADAR, 0, 0, 48, SB, 110)  # the side's logo
            if not self.has_art(CH_RADAR):
                p.fillRect(RADAR_VIEW, color(0xFF000000))
                self.caption(p, 'Kein Radar', RADAR_VIEW.center().x(), RADAR_VIEW.center().y() + 3, 8, 0xFFA7ABB3, 130)
            return
        self.piece(p, CH_RADAR, max(0, frames - 1), 0, 48, SB, 110)  # the frame with its screen on
        p.fillRect(RADAR_VIEW, color(0xFF000000))
        d, (vx, vy, vw, vh) = self.radar_rect(m), m['view']
        kx, ky = d.width() / m['radar'][1], d.height() / m['radar'][2]
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(d, self.radar)
        p.setClipRect(RADAR_VIEW, Qt.ClipOperation.IntersectClip)
        p.setPen(QPen(color(0xFFFFFFFF), .8)); p.setBrush(Qt.BrushStyle.NoBrush)  # what the top screen shows
        p.drawRect(QRectF(d.left() + vx * kx, d.top() + vy * ky, vw * kx, vh * ky))
        p.restore()

    def power(self, p, m, x, top, height):
        """The power bar: the sidebar's pip column."""
        low = m['drain'] > m['out']
        column = pips(max(1, int((height + 3) / 3)), m['out'], m['drain'], low and self.blink(.2))
        for i, frame in enumerate(column):
            y = top + height - (i + 1) * 3
            img = self.art(CH_POWERP, frame)
            if img is not None: self.draw(p, img, x, y)
            elif not self.has_art(CH_POWERP): p.fillRect(QRectF(x, y, 12, 2), color((0xFF20242A, 0xFF35C24A, 0xFFE6D23A, 0xFFD2362E, 0xFFFFFFFF)[frame]))

    def strip_row(self, p, x, y, cols):
        """One row of the cameo strip, cols sockets wide: side2.shp cut into left edge, socket, right edge."""
        img = self.art(CH_SIDE2)
        if img is None or img.width() < 168:
            if not self.has_art(CH_SIDE2):
                self.plate(p, QRectF(x, y, 42 + 63 * cols, ROW))
                for i in range(cols): p.fillRect(QRectF(x + 22 + 63 * i, y + 1, 60, 48), color(0xFF000000))
            return
        h = img.height()
        p.drawImage(QRectF(x, y, 22, h), img, QRectF(0, 0, 22, h))
        for i in range(cols): p.drawImage(QRectF(x + 22 + 63 * i, y, 63, h), img, QRectF(22, 0, 63, h))
        p.drawImage(QRectF(x + 22 + 63 * cols, y, 20, h), img, QRectF(148, 0, 20, h))

    def cameo(self, p, r, key, name):
        img = self.pic(key)
        if img is not None: return p.drawImage(r, img)
        p.fillRect(r, color(0xFF181B20))
        self.caption(p, name, r.center().x(), r.bottom() - 5, 6, 0xFFFFFFFF, 56)

    def supers(self, p, m):
        """The left strip: four superweapon sockets, as the sidebar shows them."""
        self.strip_row(p, 0, 227, 2); self.strip_row(p, 0, 277, 2)
        self.power(p, m, 0 if m['side'] else 5, 227, 100)
        for n, sw in enumerate(m['supers'][:4]):
            r, kind = QRectF(22 + n % 2 * 63, 228 + n // 2 * 50, 60, 48), sw['key'] & 0xFFFF
            name = self.names.get(sw['key']) or SUPER_NAMES.get(kind, 'Superwaffe')
            self.cameo(p, r, sw['key'], name)
            if sw['ready']:
                if self.blink(): self.text(p, 'BEREIT', r.center().x(), r.top() + 1, 0xFFFFFFFF, shadow=True)
            else:
                self.clock(p, r, sw['progress'] / 1000, 0x96000000)
                self.text(p, f'{sw["seconds"] // 60}:{sw["seconds"] % 60:02d}', r.center().x(), r.top() + 15, 0xFFFFFFFF, shadow=True)
            if self.area(r, ('super', kind)): p.fillRect(r, color(0x40FFFFFF))
            self.w.hit(r, lambda kind=kind, name=name: (self.cmd(CMD_SUPER, kind), self.say(name)), name=f'super{kind}')

    def foot(self, p, m):
        y, side3, addon = 327, self.art(CH_SIDE3), self.art(CH_ADDON)
        if side3 is not None:
            self.draw(p, side3, 0, y)
            y += side3.height()
        elif not self.has_art(CH_SIDE3): self.plate(p, box(0, y, SB, self.ah))
        if addon is not None: self.draw(p, addon, 0, y)
        self.leave(p, QRectF(21, self.ah - 59, 125, 25))
        self.button(p, QRectF(21, self.ah - 31, 125, 25), ('zoom',), f'ZOOM {m["zoom"]}%', lambda: self.link.send(f'zoom {100 if m["zoom"] >= 150 else m["zoom"] + 25}'))

    def strip(self, p, m):
        """The cameo strip, four sockets wide; more rows than fit can be dragged."""
        items = m['items']

        def rows(top):
            for r in range(max(ROWS, -(-len(items) // 4))): self.strip_row(p, SB, top + r * ROW, 4)
            for n, it in enumerate(items):
                r = QRectF(SB + 22 + n % 4 * 63, top + 1 + n // 4 * ROW, 60, 48)
                if r.bottom() > STRIP.top() and r.top() < STRIP.bottom(): self.tile(p, m, it, r)
            return top + max(ROWS, -(-len(items) // 4)) * ROW
        self.w.scroller(p, f'ra2-tab{m["tab"]}', STRIP, rows)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.power(p, m, SB + (0 if m['side'] else 5), 0, STRIP.height())
        if not items: self.caption(p, 'Hier gibt es noch nichts zu bauen', STRIP.center().x(), 30, 8, 0xFFA7ABB3, 240)
        if len(items) > ROWS * 4: self.caption(p, '▼ ziehen', AW - 4, STRIP.bottom() - 3, 5.6, alpha(self.accent(), .9), 40, 2)

    def tile(self, p, m, it, r):
        state, busy = it['state'], it['state'] in (ST_BUILDING, ST_ON_HOLD)
        self.cameo(p, r, it['key'], self.names.get(it['key']) or '')
        if state == ST_DISABLED: p.fillRect(r, color(0xA8000000))
        elif busy: self.clock(p, r, it['progress'] / 1000, 0xB8000000 if state == ST_ON_HOLD else 0x96000000)
        if state == ST_READY:
            if self.blink(): self.text(p, 'BEREIT', r.center().x(), r.top() + 1, 0xFFFFFFFF, shadow=True)
        elif state == ST_ON_HOLD: self.text(p, 'PAUSE', r.center().x(), r.top() + 1, 0xFFFFFFFF, shadow=True)
        elif state == ST_BUILDING: self.text(p, f'{it["progress"] // 10}%', r.center().x(), r.top() + 15, 0xFFFFFFFF, shadow=True)
        if it['queued'] > 1 or it['queued'] == 1 and not (busy or state == ST_READY):  # units queued behind the current one
            self.text(p, str(it['queued']), r.right() - 2, r.top() - 1, 0xFFFFFFFF, 2, True)
        if it['cost'] > 0 and state not in (ST_READY, ST_ON_HOLD):
            self.text(p, f'${it["cost"]}', r.left() + 2, r.top() - 1, 0xFF8A8F98 if state == ST_DISABLED else 0xFFFF6A5A if it['cost'] > m['credits'] else 0xFFFFE9A0, 0, True)
        if self.area(r.intersected(STRIP), ('item', it['key'])): p.fillRect(r, color(0x40FFFFFF))
        # Buildings: a second tap while building puts it on hold (the right click). Units: every tap queues one more.
        self.w.hit(r, self.tap(lambda: self.build(it, it['tab'] < 2 and state == ST_BUILDING)), name=f'item{it["key"]}')

    def bar_back(self, p, r, down):
        """The bar's own backdrop: the first pixel column of a command button, stretched (black with its lines)."""
        img = self.art(CH_BUTTON0)
        if img is not None: p.drawImage(r, img, QRectF(0, 0, 1, img.height()))
        else:
            p.fillRect(r, color(0xFF000000))
            p.fillRect(QRectF(r.left(), r.bottom() - 1, r.width(), 1), color(alpha(self.accent(), .35)))
        if down: p.fillRect(r, color(alpha(self.accent(), .28)))

    def command(self, p, r, key, art, label, dim, fn):
        """A button of the command bar: the game's own icon or one of ours, and its name."""
        down, acc = self.area(r, key), self.accent()
        img = self.art(CH_BUTTON0 + art, int(down)) if art is not None else None
        self.bar_back(p, r, down)
        if img is not None:  # the art's icon band, moved up to make room for the caption
            p.setOpacity(.35 if dim else 1)
            p.drawImage(QRectF(r.left(), r.top() + 2, img.width(), 21), img, QRectF(0, 6, img.width(), 21))
            p.setOpacity(1)
        elif label in ICONS:
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.translate(r.center().x() - 8.4, r.top() + 3.5); p.scale(.6, .6)
            p.setPen(QPen(color(alpha(acc, .3 if dim else 1)), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)); p.setBrush(Qt.BrushStyle.NoBrush)
            for line in ICONS[label]: p.drawPolyline(QPolygonF([QPointF(*at) for at in line]))
            p.restore()
        self.caption(p, label, r.center().x(), r.bottom() - 4, 5.6, alpha(acc, .4 if dim else .9), 48)
        self.w.hit(r, self.tap(fn), name=label)

    def bar(self, p, m):
        """The advanced command bar, the control groups, speed, quick save / load."""
        acc, speed, fixed = self.accent(), m['speed'], m['speed'] < 0  # a network game's speed and saves are the session's
        self.bar_back(p, QRectF(SB, BAR_Y, AW - SB, 4 * BTN_H), False)
        for row in range(4): self.bar_back(p, QRectF(SB, BAR_Y + row * BTN_H, AW - SB, BTN_H), False)
        for i, (action, art, name) in enumerate(HOTS):
            dim = not m['misc'] & M_ALERTS if action == HOT_ALERT else i < 6 and not m['selected'] and action != HOT_CHEER  # orders need a selection
            self.command(p, cell(i // 5, i % 5), ('hot', i), art, name, dim, lambda action=action, name=name: (self.cmd(CMD_HOT, action), self.say(name)))
        for i, (count, selected) in enumerate(m['groups']):  # ring and numeral as on the bar's own team buttons
            r = cell(2, i)
            self.bar_back(p, r, self.area(r, ('group', i)))
            ring, full = QRectF(r.center().x() - 12, r.top() + 3.5, 24, 18), count > 0 and selected == count
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(color(alpha(acc, 1 if count else .35)), 1.6)); p.setBrush(color(acc) if full else Qt.BrushStyle.NoBrush)
            p.drawEllipse(ring)
            p.restore()
            self.caption(p, ('I', 'II', 'III', 'IV', 'V')[i], r.center().x(), r.top() + 16.5, 11, 0xFF000000 if full else alpha(acc, 1 if count else .35), 20)
            self.caption(p, f'{count} Einh.' if count else 'halten', r.center().x(), r.bottom() - 4, 5.6, alpha(acc, .9 if count else .4), 48)
            self.w.hit(r, self.tap(lambda i=i: (self.cmd(CMD_GROUP, i + 1, 0), self.say(f'Gruppe {i + 1}'))), name=f'group{i + 1}')

        def pace(v): self.cmd(CMD_SPEED, v); self.say(f'Tempo {speed_label(v)}')
        self.command(p, cell(3, 0), ('slower',), None, 'Langsamer', fixed or speed >= 6, lambda: fixed or pace(max(1, min(6, speed + 1))))
        r = cell(3, 1)
        self.bar_back(p, r, self.area(r, ('speed',)))
        self.text(p, speed_label(speed), r.center().x(), r.top() + 4, alpha(acc, .4) if fixed else 0xFFFFFFFF)
        self.caption(p, 'Tempo', r.center().x(), r.bottom() - 4, 5.6, alpha(acc, .85), 48)
        self.w.hit(r, lambda: fixed or pace(4), name='Tempo')
        self.command(p, cell(3, 2), ('faster',), None, 'Schneller', fixed or speed <= 1, lambda: fixed or pace(max(1, min(6, speed - 1))))
        self.command(p, cell(3, 3), ('save',), None, 'Speichern', fixed, lambda: fixed or (self.cmd(CMD_SAVE), self.say('Schnell gespeichert')))
        self.command(p, cell(3, 4), ('load',), None, 'Laden', fixed or not m['misc'] & M_QUICK_SAVE,
                     lambda: self.say('Zum Laden gedrückt halten' if m['misc'] & M_QUICK_SAVE else 'Noch kein Schnellspeicherstand'))

    def status(self, p, m):
        flags, low = m['flags'], m['drain'] > m['out']
        p.fillRect(box(SB, STATUS_Y, AW, self.ah), color(0xFF000000))
        headline, detail = (('Gebäude platzieren', 'Oben den Bauplatz antippen, nochmal tippen baut') if flags & F_PLACING else
                            ('Ziel wählen', 'Oben das Ziel der Superwaffe antippen') if flags & F_TARGETING else
                            ('Reparieren', 'Oben ein Gebäude antippen · nochmal Reparieren beendet') if flags & F_REPAIR else
                            ('Verkaufen', 'Oben ein Gebäude antippen · nochmal Verkaufen beendet') if flags & F_SELL else
                            (self.said, '') if self.said and time.time() < self.said_until else
                            (f'{m["selected"]} ausgewählt' if m['selected'] else 'Bereit', 'Tippen = bauen · halten = anhalten, abbrechen · L/R = Reiter'))
        self.caption(p, headline, SB + 6, STATUS_Y + 10.5, 8.6, self.accent(), 190, 0)
        self.caption(p, ('Strom fehlt ' if low else 'Strom ') + f'{m["out"]} / {m["drain"]}', AW - 6, STATUS_Y + 10, 6.6, 0xFFFF6A5A if low else 0xFFA7ABB3, 90, 2)
        self.caption(p, detail, SB + 6, STATUS_Y + 20, 6.6, 0xFFA7ABB3, AW - SB - 12, 0)
