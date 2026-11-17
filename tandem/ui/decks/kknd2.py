"""Deck for KKnD 2: Krossfire on the bottom screen (the native port in ports/kknd2: "KKND2 Thor", OpenRA with OpenKrush).

Native port of the Android deck of KKND2 Thor 0.2.0 (thor/android/Deck/DeckView.cs) in the look of the player's faction:
the game's own sidebar buttons and bitmap font (the game reads them from the player's surv/mute/robo.bpk and sends them
over). Header with faction, game time, speed and the oil economy (rigs, tankers, power stations, oil left in the ground,
oil to spend); the level's minimap with units, the view and attack alerts (a tap moves the view); the selection with
health; the build pages (infantry, vehicles, buildings, defence) with a card per item (tap = build, resume or pick up to
place on the top screen, hold = hold, then cancel), one chip per factory, and the research page (tap = start or stop);
ten control groups (tap = select, again = look at it, hold = store the selection); the command buttons (deploy, stop,
attack-move, force move, waypoints, scatter, stance, sell, repair, army, same type, base, alert, pause, speed, find,
save, the game's menu) and leaving the game. The controller works in the game (thor/android/ThorInput.cs): L2/R2 turn
the pages, L1/R1 move a ring over the cards and A builds the ringed one; the game keeps page and ring and sends them, so
a tap here sends "tab"/"producer" to it instead of switching by itself.
Everything shown is the snapshot the game sends over the deck socket (decks/portsocket.py, the game's
thor/linux/TandemDeck.cs); every press goes back as a command that the game runs through its own order code.
Drawn in the Android deck's 1240 x 1080 design space and scaled.

Interface for tandem_ui (see DECKS there): Deck(window), paint(painter) -> bool, press(pos), close().
parse(), parse_art(), cards() and speed_label() are plain Python (no Qt) and carry the logic worth testing.
"""
import struct, threading, time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QTransform

from decks.portsocket import Link

W, H, P = 1240, 1080, 3  # the design space; screen pixels per art pixel
HOLD, CONFIRM = .45, 3.0  # seconds: a held card or group, an armed "tap again"
TABS = (('infantry',), ('vehicle', 'beast', 'aircraft'), ('building',), ('tower', 'wall'))
TAB_NAMES, TECH_TAB = ('INFANTERIE', 'FAHRZEUGE', 'GEBÄUDE', 'ABWEHR'), 4
BLANK, INFANTRY, VEHICLE, BUILDING, TOWER = 0, 1, 2, 5, 6  # frames of the faction's sidebar buttons
SHADE, DIM, GOOD, BAD, TEXT = 0xFFC4C4C4, 0xFF8C8C8C, 0xFF58D868, 0xFFFF4840, 0xFFF2F2EF
LOOKS = {'evolved': (0xFFFFA428, 0xFF151413, 'EVOLVED', 105), 'series9': (0xFFFFD630, 0xFF0E1218, 'SERIES 9', 106)}
SURVIVORS = (0xFFFF6A48, 0xFF17120F, 'SURVIVORS', 104)  # accent, background, name, emblem in the font
# The command buttons: id, label, what goes to the game
COMMANDS = (('deploy', 'AUFBAUEN', 'deploy'), ('stop', 'STOPP', 'stop'), ('attack', 'ANGRIFF', 'mode attack'), ('move', 'BEWEGEN', 'move'),
            ('waypoint', 'WEGPUNKT', 'waypoint'), ('scatter', 'STREUEN', 'scatter'), ('stance', 'HALTUNG', 'stance'), ('sell', 'VERKAUFEN', 'mode sell'),
            ('repair', 'REPARIEREN', 'mode repair'), ('army', 'ARMEE', 'army 0'), ('type', 'GLEICHE', 'army 1'), ('base', 'BASIS', 'base'),
            ('alert', 'ALARM', 'alert'), ('pause', 'PAUSE', 'pause'), ('speed', 'TEMPO', 'speed'), ('find', 'FINDEN', 'find'),
            ('save', 'SPEICHERN', 'save'), ('menu', 'MENÜ', 'menu'))
STANCES = {'HoldFire': 'FEUER AUS', 'ReturnFire': 'ERWIDERN', 'Defend': 'VERTEIDIGEN', 'AttackAnything': 'ALLES'}


def parse(d):
    """A state line of the game as the deck uses it, or None for anything else."""
    if not isinstance(d, dict) or d.get('v') != 1: return None
    m = dict(d)
    m['items'] = [[dict(zip(('name', 'title', 'cost', 'progress', 'count', 'active', 'building', 'locked', 'paused'), it)) for it in q.get('items', [])]
                  for q in d.get('queues', [])]
    m['techs'] = [dict(zip(('id', 'name', 'title', 'level', 'max', 'busy', 'cost'), t)) for t in d.get('techs', [])]
    m['sel'] = [dict(zip(('name', 'title', 'count', 'hp'), s)) for s in d.get('sel', [])]
    dots = d.get('dots', [])
    m['dots'] = [tuple(dots[i:i + 4]) for i in range(0, len(dots) - 3, 4)]
    pings = d.get('pings', [])
    m['pings'] = [tuple(pings[i:i + 2]) for i in range(0, len(pings) - 1, 2)]
    m['ingame'] = (d.get('map') or [0])[0] > 0
    return m


def parse_art(data):
    """The faction's interface art (block art:<faction>): [(width, height, x, y, BGRA bytes)], the 12 sidebar buttons first, then
    the font from ASCII 32 on. None if the block is empty or cut short."""
    if len(data) < 2: return None
    (count,), at, frames = struct.unpack_from('<H', data), 2, []
    for _ in range(count):
        if at + 8 > len(data): return None
        w, h, x, y = struct.unpack_from('<HHhh', data, at)
        at += 8
        frames.append((w, h, x, y, data[at:at + w * h * 4]))
        at += w * h * 4
    return frames if at == len(data) and count > 12 else None


def queues_for(m, tab):
    return [] if tab >= len(TABS) else [n for n, q in enumerate(m['queues']) if q['cat'] in TABS[tab]]


def current_queue(m):
    """The index of the queue the build page shows (the game's tab and producer), or None."""
    qs = queues_for(m, m['tab'])
    return qs[max(0, min(m['producer'], len(qs) - 1))] if qs else None


def speed_label(percent): return '2X' if percent > 190 else '1.5X' if percent > 140 else '0.5X' if percent < 60 else '1X'


def cards(m):
    """The cards of the page the game has open: dicts with what a card shows, and 'tap' / 'hold' as (command, what to say)."""
    out, oil = [], m['cash']
    if m['tab'] == TECH_TAB:
        for t in m['techs']:
            done, can = t['level'] >= t['max'], t['level'] < t['max'] and (t['busy'] or m['free'] > 0)
            out.append({'icon': t['name'], 'title': t['title'], 'line': f'STUFE {t["level"]}/{t["max"]}', 'line_color': GOOD if done else 0,
                        'status': 'FORSCHT' if t['busy'] else 'MAX' if done else f'ÖL {t["cost"]}', 'badge': '', 'progress': -1, 'on': t['busy'],
                        'dim': not can and not t['busy'], 'hold': None,
                        'tap': (f'research {t["id"]}', 'FORSCHUNG GESTOPPT' if t['busy'] else 'FORSCHUNG GESTARTET') if can else None})
        return out
    q = current_queue(m)
    if q is None: return out
    qid = m['queues'][q]['id']
    for it in m['items'][q]:
        running, poor = it['progress'] >= 0 and not it['paused'], it['cost'] > oil and not it['locked']
        out.append({'icon': it['name'], 'title': it['title'], 'line': f'ÖL {it["cost"]}', 'line_color': BAD if poor else 0,
                    'status': 'GESPERRT' if it['locked'] else 'ANGEHALTEN' if it['paused'] else 'OBEN SETZEN' if it['building'] and it['active'] else '',
                    'badge': '' if it['count'] == 0 or it['building'] else 'INF' if it['count'] < 0 else str(it['count']),
                    'progress': it['progress'], 'on': it['active'], 'dim': it['locked'] or (poor and it['count'] == 0),
                    'tap': None if it['locked'] else (f'produce {qid} {it["name"]} 0', None),
                    'hold': None if it['locked'] else (f'produce {qid} {it["name"]} 1', 'ANGEHALTEN' if running else 'ABGEBROCHEN')})
    return out


def color(argb): return QColor((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, (argb >> 24) & 255)


def box(l, t, r, b): return QRectF(l, t, r - l, b - t)


def clock(secs): return f'{secs // 60}:{secs % 60:02d}'


class Deck:
    def __init__(self, window):
        self.w = window
        self.m, self.alive, self.painted, self.waiting = None, True, 0.0, False
        self.art, self.art_asked, self.glyphs, self.tints, self.icons = None, None, [], {}, {}
        self.minimap, self.level, self.auto_tab = None, None, False
        self.pressed, self.held, self.longs, self.said, self.said_until, self.armed = None, False, [], '', 0.0, (None, 0.0)
        self.stage, self.mm, self.focus_seen, self.plain = None, None, -1, None
        self.link = Link((window.RUN.get('port') or {}).get('socket') or '', self.heard, self.block)

    def close(self):
        self.alive = False
        self.link.close()

    # ---- the game's data (on the link's thread) ------------------------------------------------------------------------
    def heard(self, d):
        m = parse(d)
        if d is not None and m is None: return
        self.m = m
        if m:
            faction = m['faction'] or 'survivors'
            if faction != self.art_asked:
                self.art_asked = faction
                self.link.send(f'art {faction}')
            if m['level'] != self.level:  # another game: its minimap, and the icons again (the player's colour may differ)
                self.level, self.minimap, self.icons, self.auto_tab = m['level'], None, {}, False
                if m['level']: self.link.send('minimap')
            # start of a game: open the first page that can build something (usually the buildings once the base is set up)
            if not self.auto_tab and m['queues']:
                self.auto_tab = True
                if m['tab'] != TECH_TAB and not queues_for(m, m['tab']):
                    first = next((t for t in range(len(TABS)) if queues_for(m, t)), None)
                    if first is not None: self.link.send(f'tab {first}')
        else: self.art_asked = self.level = None  # the game is gone: ask again when it is back
        self.changed()

    def block(self, name, data):
        if name.startswith('art:'):
            frames = parse_art(data)
            self.art, self.tints = ([self.image(f) for f in frames[:12]] if frames else None), {}
            self.glyphs = [(self.image(f) if f[1] else None, f[0], f[2], f[3]) for f in frames[12:]] if frames else []
        elif name == 'minimap': self.minimap = self.image(struct.unpack_from('<HH', data) + (0, 0, data[4:])) if len(data) > 4 else None
        elif name.startswith('icon:') and len(data) > 4: self.icons[name[5:]] = self.image(struct.unpack_from('<HH', data) + (0, 0, data[4:]))
        self.changed()

    @staticmethod
    def image(frame):
        w, h, _, _, px = frame
        if not w or not h or len(px) < w * h * 4: return None
        return QImage(px, w, h, w * 4, QImage.Format.Format_ARGB32).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)  # a copy: the bytes go

    def icon(self, name):
        if not name: return None
        if name not in self.icons:
            self.icons[name] = None
            self.link.send(f'icon {name}')
        return self.icons[name]

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

    def say(self, text, secs=1.5):
        self.said, self.said_until = text, time.time() + secs
        self.changed(); self.later(secs + .1)

    def send(self, what):
        """A (command, what to say) pair of cards() or a plain command."""
        cmd, text = what if isinstance(what, tuple) else (what, None)
        self.link.send(cmd)
        if text: self.say(text)

    # ---- touch ----------------------------------------------------------------------------------------------------------
    def press(self, pos):
        """A finger down (pos) or up (None). The minimap answers at once; a card or group held long enough does its second thing,
        and the tap on release then does nothing."""
        if pos is None:
            self.pressed = None
            return
        self.held = False
        at = self.stage.inverted()[0].map(pos) if self.stage else pos
        if self.mm and self.mm[0].contains(at):
            _, ox, oy, s, bx, by = self.mm
            self.link.send(f'jump {bx + (at.x() - ox) / s:.1f} {by + (at.y() - oy) / s:.1f}')
            return
        self.pressed = key = next((key for rect, key, _ in reversed(self.longs) if rect.contains(at)), None)
        if key is not None:
            timer = threading.Timer(HOLD, self.hold, (key,))
            timer.daemon = True
            timer.start()

    def hold(self, key):
        if self.pressed != key or getattr(self.w, 'moved', False): return  # let go, or the cards are being dragged
        fn = next((fn for _, k, fn in self.longs if k == key), None)
        if fn:
            self.held = True
            fn()
            self.changed()

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

    def area(self, rect, fn, key=None, hold=None, name=''):
        """A tap area (and, with hold, what holding it does)."""
        self.w.hit(rect, self.tap(fn), name=name)
        if hold: self.longs.append((rect, key or name, hold))

    # ---- drawing in the faction's look (design pixels) -----------------------------------------------------------------
    def look(self):
        return LOOKS.get((self.m or {}).get('faction'), SURVIVORS)

    def tinted(self, img, argb):
        """img multiplied by a colour (the Android deck's colour filter), kept for the next frame."""
        key = (img.cacheKey(), argb)
        if key not in self.tints:
            t = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
            t.fill(0)
            q = QPainter(t)
            q.drawImage(0, 0, img)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            q.fillRect(t.rect(), color(argb))
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            q.drawImage(0, 0, img)
            q.end()
            self.tints[key] = t
        return self.tints[key]

    def plate(self, p, r, on=False, dim=False, panel=False):
        """A button or panel: the game's blank 32 x 32 sidebar button stretched, its corners kept."""
        accent = self.look()[0]
        if not self.art:
            p.setPen(QPen(color(accent if on else 0xFF323844), 1)); p.setBrush(color(0xFF0D0F12 if panel else 0xFF181B20))
            p.drawRect(r.adjusted(.5, .5, -.5, -.5))
        else:
            img = self.tinted(self.art[BLANK], 0xFF4A4A4A if panel else 0xFF808080 if dim else SHADE)
            k, iw, ih = 7, img.width(), img.height()
            l, t, rr, bb = round(r.left()), round(r.top()), round(r.right()), round(r.bottom())
            dx, dy, sx, sy = (l, l + k * P, rr - k * P, rr), (t, t + k * P, bb - k * P, bb), (0, k, iw - k, iw), (0, k, ih - k, ih)
            for i in range(3):
                for j in range(3):
                    p.drawImage(box(dx[i], dy[j], dx[i + 1], dy[j + 1]), img, box(sx[i], sy[j], sx[i + 1], sy[j + 1]))
        if on: self.outline(p, r, accent)

    def outline(self, p, r, argb):
        c = color(argb)
        c.setAlphaF(.22)
        p.fillRect(r.adjusted(6, 6, -6, -6), c)
        p.setPen(QPen(color(argb), P)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r.adjusted(4.5, 4.5, -4.5, -4.5))

    def symbol(self, p, r, frame, on, dim):
        """One of the game's own sidebar buttons with its symbol (infantry, vehicles, ...)."""
        s = min(r.width(), r.height())
        p.drawImage(QRectF(r.center().x() - s / 2, r.center().y() - s / 2, s, s), self.tinted(self.art[frame], 0xFF808080 if dim else SHADE))
        if on: self.outline(p, r, self.look()[0])

    def txt(self, p, s, x, top, sc=2.0, argb=0, draw=True):
        """Text in the game's bitmap font (11 px capitals), top = the upper edge of the line. Returns the width."""
        if not self.glyphs:
            if self.plain is None:
                f = QFont('sans-serif'); f.setPixelSize(100); f.setBold(True)
                self.plain = (f, QFontMetricsF(f))
            k = 9.5 * sc / 100
            if draw:
                p.save(); p.translate(x, top + 11.5 * sc); p.scale(k, k)
                p.setFont(self.plain[0]); p.setPen(color(argb or TEXT)); p.drawText(QPointF(0, 0), s)
                p.restore()
            return self.plain[1].horizontalAdvance(s) * k
        x0 = x
        for ch in s:
            i = ord(ch) - 32
            img, gw, gx, gy = self.glyphs[i if 0 <= i < len(self.glyphs) else ord('?') - 32]
            if draw and img is not None:
                p.drawImage(QRectF(x + gx * sc, top + gy * sc, gw * sc, img.height() * sc), self.tinted(img, argb) if argb else img)
            x += (gw + 1) * sc
        return x - x0

    def txt_w(self, s, sc=2.0): return self.txt(None, s, 0, 0, sc, 0, False)

    def txt_right(self, p, s, right, top, sc=2.0, argb=0): return self.txt(p, s, right - self.txt_w(s, sc), top, sc, argb)

    def txt_center(self, p, s, cx, top, sc=2.0, argb=0): return self.txt(p, s, cx - self.txt_w(s, sc) / 2, top, sc, argb)

    def fit(self, s, room, sc=2.0):
        if self.txt_w(s, sc) <= room: return s
        while len(s) > 1 and self.txt_w(s + '..', sc) > room: s = s[:-1]
        return s + '..'

    def bar(self, p, r, fraction, argb):
        p.fillRect(r, color(0xFF000000))
        p.fillRect(QRectF(r.left() + P, r.top() + P, (r.width() - 2 * P) * max(0.0, min(1.0, fraction)), r.height() - 2 * P), color(argb))

    def cameo(self, p, r, name, dim):
        img = self.icon(name)
        if img is None: return
        s = min(r.width() / img.width(), r.height() / img.height())
        s = int(s) if s >= 1 else s  # whole upscales stay pixel-sharp
        w, h = img.width() * s, img.height() * s
        p.save()
        p.setOpacity(.35 if dim else 1)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, s < 1)
        p.drawImage(QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h), img)
        p.restore()

    # ---- painting -------------------------------------------------------------------------------------------------------
    def paint(self, p):
        w, m = self.w, self.m
        k = min(w.width() / W, w.height() / H)
        self.stage = xf = QTransform.fromTranslate((w.width() - W * k) / 2, (w.height() - H * k) / 2).scale(k, k)
        self.painted, self.longs, self.mm = time.time(), [], None
        p.save()
        p.fillRect(0, 0, w.width(), w.height(), color(self.look()[1]))
        p.setTransform(xf)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)  # the game's pixel art stays crisp
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w.xf, w.zoom = xf, k  # taps arrive in window pixels
        try:
            if not m or not m['ingame']: self.idle(p)
            else:
                self.header(p, m)
                self.map(p, m, box(16, 96, 436, 516))
                self.selection(p, m, box(16, 524, 436, 676))
                self.pages(p, m, box(448, 96, 1224, 676))
                self.groups(p, m, box(16, 684, 1224, 796))
                self.commands(p, m, box(16, 804, 1224, 1060))
                if m['over']:
                    banner = box(448, 380, 1224, 500)
                    self.plate(p, banner, True)
                    self.txt_center(p, 'SIEG' if m['won'] else 'NIEDERLAGE', banner.center().x(), banner.top() + 30, 4, GOOD if m['won'] else BAD)
                if time.time() < self.said_until: self.toast(p, self.said)
        finally:
            w.xf, w.zoom = None, 1.0
            p.restore()
        return True

    def toast(self, p, text):
        tw = self.txt_w(text, 3)
        r = box(620 - tw / 2 - 36, 440, 620 + tw / 2 + 36, 530)
        self.plate(p, r, True)
        self.txt(p, text, r.left() + 36, r.top() + 24, 3)

    def leave(self, p, r):
        """Ends the game and returns to Tandem: asks first."""
        armed = self.is_armed('quit')
        self.plate(p, r, armed)
        self.txt_center(p, 'NOCHMAL = BEENDEN' if armed else 'BEENDEN', r.center().x(), r.center().y() - 11, 2, BAD if armed else 0)
        self.area(r, lambda: self.twice('quit') and self.w.post('api/quit'), name='BEENDEN')

    def idle(self, p):
        accent = self.look()[0]
        self.txt_center(p, 'KKND 2: KROSSFIRE', W / 2, 330, 5, accent)
        self.txt_center(p, 'KOMMANDO-DECK - BEREITSCHAFT', W / 2, 430, 2, DIM)
        self.txt_center(p, 'KARTE, ÖL UND BAUMENÜS ERSCHEINEN HIER, SOBALD EIN GEFECHT LÄUFT.', W / 2, 480, 2)
        self.txt_center(p, 'LINKER STICK ZEIGER - A KLICK - B RECHTSKLICK - RECHTER STICK KARTE - SELECT ZURÜCK', W / 2, 530, 1.5, DIM)
        r = box(W / 2 - 300, 860, W / 2 - 8, 960)
        self.plate(p, r)
        self.txt_center(p, 'MENÜ', r.center().x(), r.center().y() - 11)
        self.area(r, lambda: self.link.send('menu'), name='MENÜ')
        self.leave(p, box(W / 2 + 8, 860, W / 2 + 300, 960))

    def header(self, p, m):
        accent, _, name, emblem = self.look()
        logo = self.glyphs[emblem][0] if len(self.glyphs) > emblem else None
        if logo is not None: p.drawImage(QRectF(16, 8, 24 * P, 24 * P), logo)
        self.txt(p, name, 104, 8, 3, accent)
        x = 104 + self.txt(p, clock(m['secs']), 104, 50) + 24
        x += self.txt(p, speed_label(m['speed']), x, 50, 2, DIM) + 24
        if m['paused']: self.txt(p, 'PAUSE', x, 50, 2, accent)
        # the oil economy: drill rigs, tankers, power stations and what is left under the rigs
        self.txt(p, f'BOHRTURM {m["rigs"]}  TANKER {m["tankers"]}  KRAFTWERK {m["stations"]}', 448, 14, 2, DIM)
        self.txt(p, f'IM BODEN {m["oil"]:,}'.replace(',', '.'), 448, 50, 2, BAD if m['rigs'] > 0 and m['oil'] < 5000 else DIM)
        value = f'{m["cash"]:,}'.replace(',', '.')
        self.txt_right(p, value, 1224, 20, 4)
        self.txt_right(p, 'ÖL', 1224 - self.txt_w(value, 4) - 20, 42, 2, accent)

    def map(self, p, m, r):
        self.plate(p, r, panel=True)
        inner = r.adjusted(12, 12, -12, -12)
        bx, by, bw, bh = m['bounds']
        s = min(inner.width() / max(1, bw), inner.height() / max(1, bh))
        ox, oy = inner.left() + (inner.width() - bw * s) / 2, inner.top() + (inner.height() - bh * s) / 2
        cell = lambda x, y, w=0, h=0: QRectF(ox + (x - bx) * s, oy + (y - by) * s, w * s, h * s)
        p.save()
        p.setClipRect(inner)
        p.fillRect(inner, color(0xFF000000))
        if self.minimap is not None:  # the .mim covers the whole map, border included
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(cell(0, 0, *m['map']), self.minimap)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        for x, y, rgb, building in m['dots']:
            size = 2.2 if building else 1.2
            p.fillRect(cell(x - size / 2, y - size / 2, size, size), color(0xFF000000 | int(rgb)))
        p.setPen(QPen(color(TEXT), 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(cell(*m['cam']))
        if m['pings'] and self.blink(.3):  # attack alerts: blinking rings
            p.setPen(QPen(color(BAD), 4))
            for x, y in m['pings']: p.drawEllipse(cell(x, y).topLeft(), 16, 16)
        p.restore()
        self.mm = (inner, ox, oy, s, bx, by)  # a finger on it moves the view (press)

    def blink(self, period):
        """True every other period; asks for the repaint that shows the change."""
        if not self.waiting:
            self.waiting = True
            self.later(period)
        return int(time.time() / period) % 2 == 0

    def selection(self, p, m, r):
        accent = self.look()[0]
        self.plate(p, r, panel=True)
        if not m['sel']:
            self.txt(p, 'NICHTS GEWÄHLT', r.left() + 20, r.top() + 18, 2, DIM)
            return
        y = r.top() + 12
        for s in m['sel'][:3]:
            self.cameo(p, QRectF(r.left() + 12, y, 40, 40), s['name'], False)
            count = f'x{s["count"]}'
            self.txt_right(p, count, r.right() - 16, y, 2, accent)
            self.txt(p, self.fit(s['title'].upper(), r.width() - 90 - self.txt_w(count)), r.left() + 62, y)
            self.bar(p, box(r.left() + 62, y + 28, r.right() - 16, y + 40), s['hp'] / 100, GOOD if s['hp'] > 50 else accent if s['hp'] > 25 else BAD)
            y += 44

    def pages(self, p, m, r):
        accent, ts = self.look()[0], 128
        symbols = (INFANTRY, VEHICLE, BUILDING, TOWER)
        for i in range(5):  # the game's own sidebar buttons for the four build pages, then research
            t = QRectF(r.left() + i * (ts + 8), r.top(), ts, ts) if i < 4 else box(r.left() + 4 * (ts + 8), r.top(), r.right(), r.top() + ts)
            on = i == m['tab']
            if i == TECH_TAB:
                self.plate(p, t, on)
                self.txt(p, 'FORSCHUNG', t.left() + 22, t.top() + 20, 2, accent if on else 0)
                self.txt(p, 'KEIN LABOR' if not m['labs'] else f'LABOR {m["free"]}/{m["labs"]} FREI', t.left() + 22, t.top() + 54, 2, DIM)
                busy = sum(1 for x in m['techs'] if x['busy'])
                if busy: self.txt(p, f'LÄUFT {busy}', t.left() + 22, t.top() + 88, 2, accent)
            else:
                qs = queues_for(m, i)
                if self.art: self.symbol(p, t, symbols[i], on, not qs)
                else:
                    self.plate(p, t, on)
                    self.txt_center(p, TAB_NAMES[i][:3], t.center().x(), t.top() + 50, 2, 0 if qs else DIM)
                busy = sum(1 for q in qs for it in m['items'][q] if it['progress'] >= 0)
                if busy: self.txt_right(p, str(busy), t.right() - 14, t.top() + 10, 2, accent)
            self.area(t, lambda i=i: self.link.send(f'tab {i}'), name='FORSCHUNG' if i == TECH_TAB else TAB_NAMES[i])

        y, queues = r.top() + ts + 8, queues_for(m, m['tab'])
        if len(queues) > 1:  # a chip per factory, each with its own queue
            x, current = r.left(), current_queue(m)
            for n, q in enumerate(queues):
                label = f'{m["queues"][q]["by"].upper()} {n + 1}'
                cw = self.txt_w(label) + 36
                if x + cw > r.right(): break
                chip = QRectF(x, y, cw, 48)
                self.plate(p, chip, q == current)
                self.txt(p, label, chip.left() + 18, chip.top() + 11, 2, accent if q == current else 0)
                self.area(chip, lambda n=n: self.link.send(f'producer {n}'), name=f'producer{n}')
                x += cw + 8
            y += 56

        items = cards(m)
        if not items:
            self.txt(p, 'NOCH NICHTS ZU ERFORSCHEN.' if m['tab'] == TECH_TAB else 'ERST DAS PASSENDE GEBÄUDE BAUEN.', r.left() + 12, y + 24, 2, DIM)
            return
        area, cw, ch, key = box(r.left(), y, r.right(), r.bottom()), (r.width() - 8) / 2, 104, 'kknd2-cards'
        focus = m['focus']
        if 0 <= focus < len(items) and focus != self.focus_seen:  # the controller's ring moved: bring its card into view
            at = focus // 2 * (ch + 8)
            self.w.off[key] = max(at + ch - area.height(), min(at, self.w.off.get(key, 0)))
        self.focus_seen = focus

        def draw(top):
            for n, c in enumerate(items):
                card = QRectF(area.left() + n % 2 * (cw + 8), top + n // 2 * (ch + 8), cw, ch)
                if card.bottom() > area.top() and card.top() < area.bottom(): self.card(p, c, card, area, n == focus)
            return top + (len(items) + 1) // 2 * (ch + 8) - 8
        self.w.scroller(p, key, area, draw)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

    def card(self, p, c, r, area, ring):
        accent = self.look()[0]
        self.plate(p, r, c['on'], c['dim'])
        self.cameo(p, box(r.left() + 12, r.top() + 10, r.left() + 96, r.bottom() - 10), c['icon'], c['dim'])
        tx = r.left() + 106
        badge = self.txt_w(c['badge'], 3) + 10 if c['badge'] else 0
        self.txt(p, self.fit(c['title'].upper(), r.right() - tx - 14 - badge), tx, r.top() + 12, 2, DIM if c['dim'] else 0)
        if c['badge']: self.txt_right(p, c['badge'], r.right() - 14, r.top() + 10, 3)
        lw = self.txt(p, c['line'], tx, r.top() + 42, 2, c['line_color'] or (DIM if c['dim'] else accent))
        if c['status'] and self.txt_w(c['status']) <= r.right() - tx - lw - 30: self.txt(p, c['status'], tx + lw + 16, r.top() + 42, 2, DIM if c['dim'] else 0)
        elif c['status']: self.txt(p, c['status'], tx, r.top() + 68, 2, DIM if c['dim'] else 0)  # too long for the same line: a third one
        if c['progress'] >= 0: self.bar(p, box(tx, r.bottom() - 26, r.right() - 16, r.bottom() - 12), c['progress'] / 100, accent)
        if ring: self.outline(p, r, TEXT)
        if c['tap']:
            hold = (lambda: self.send(c['hold'])) if c['hold'] else None
            self.area(r.intersected(area), lambda: self.send(c['tap']), key=('card', c['icon']), hold=hold, name='card:' + c['icon'])

    def groups(self, p, m, r):
        accent, gw = self.look()[0], int((r.width() - 9 * 6) / 10)
        for i in range(10):
            g, n = QRectF(r.left() + i * (gw + 6), r.top(), gw, r.height()), m['groups'][i]
            self.plate(p, g, False, n == 0)
            key = str((i + 1) % 10)
            self.txt(p, key, g.left() + 12, g.top() + 8, 3, accent if n else DIM)
            if n:
                self.cameo(p, box(g.left() + 40, g.top() + 14, g.right() - 10, g.bottom() - 34), m['gicons'][i], False)
                self.txt_right(p, f'x{n}', g.right() - 12, g.bottom() - 34, 2)
            self.area(g, lambda i=i: self.link.send(f'group {i} 0'), key=('group', i), name=f'group{key}',
                      hold=lambda i=i, key=key: self.send((f'group {i} 1', f'GRUPPE {key}')))

    def commands(self, p, m, r):
        """Seven columns: the 18 commands of the Android deck, then leaving the game (three columns wide)."""
        cols, rows, accent = 7, 3, self.look()[0]
        bw, bh = int((r.width() - (cols - 1) * 8) / cols), int((r.height() - (rows - 1) * 8) / rows)
        on = {'attack': m['mode'] == 'AttackMoveOrderGenerator', 'sell': m['mode'] == 'SellOrderGenerator', 'repair': m['mode'] == 'TechnicianEnterOrderGenerator',
              'move': m['force'], 'waypoint': m['waypoint'], 'pause': m['paused'], 'alert': bool(m['pings'])}
        for n, (cid, label, cmd) in enumerate(COMMANDS):
            b = QRectF(r.left() + n % cols * (bw + 8), r.top() + n // cols * (bh + 8), bw, bh)
            state = STANCES.get(m['stance'], '') if cid == 'stance' else speed_label(m['speed']) if cid == 'speed' else ''
            dim = (cid == 'stance' and not m['stance']) or (cid == 'find' and not m['sel'])
            lit = on.get(cid, False)
            self.plate(p, b, lit, dim)
            sc = lambda t: 2 if self.txt_w(t) <= bw - 16 else 1.5  # VERTEIDIGEN and REPARIEREN are wider than a button
            self.txt_center(p, label, b.center().x(), b.top() + (10 if state else 25), sc(label), DIM if dim else accent if lit else 0)
            if state: self.txt_center(p, state, b.center().x(), b.top() + 42, sc(state), DIM if dim else accent)
            self.area(b, (lambda: self.send(('save', 'GESPEICHERT'))) if cid == 'save' else (lambda cmd=cmd: self.link.send(cmd)), name=label)
        n = len(COMMANDS)
        self.leave(p, QRectF(r.left() + n % cols * (bw + 8), r.top() + n // cols * (bh + 8), r.right() - (r.left() + n % cols * (bw + 8)), bh))
