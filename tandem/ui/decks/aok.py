"""Command deck for Age of Kings on the bottom screen (the native port in ports/aok, the engine OpenAoK).

Native port of the Android deck of "Thor AoK" (ThorDeck.java), drawn with the game's own interface art (the top bar, the
parchment and the stone of the player's civilisation, sent by the game): stockpiles, population and age · mini-map (a
tap moves the view) with its three modes and the last alert · the selection with its hit points and queue · quick
buttons · control groups I to IV (tap picks, hold sets), find the selection, flare, game speed · three pages of tiles:
the selection's commands with the game's icons (hold = help), the player's buildings to go to, the game's screens.
Everything shown is the snapshot the engine sends over the deck socket (decks/portsocket.py, ports/aok/deck_socket.inc);
every press goes back as a command the engine runs through its own panel code. Laid out on a 1240x1080 grid and scaled.

Interface for tandem_ui (see DECKS there): Deck(window), paint(painter) -> bool, press(pos), close().
parse() is plain Python (no Qt) and carries the logic worth testing.
"""
import re, struct, threading, time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPolygonF, QTransform

from decks.portsocket import Link

# Commands (Thor::Command in the engine's src/thor/Thor.h) and the items of CMD_GAME
CMD_COMMAND, CMD_MINIMAP, CMD_IDLE_VILLAGER, CMD_IDLE_MILITARY, CMD_TOWN_CENTER, CMD_AGE_UP, CMD_MENU, CMD_CANCEL_QUEUE = range(1, 9)
CMD_DELETE, CMD_OBJECTIVES, CMD_TECH_TREE, CMD_GO_TO, CMD_GROUP_SELECT, CMD_GROUP_ASSIGN, CMD_SPEED, CMD_GAME = range(9, 17)
GAME_NOTIFICATION, GAME_TO_SELECTED, GAME_FLARE, GAME_MAP_NORMAL, GAME_MAP_COMBAT, GAME_MAP_ECONOMIC, GAME_STATISTICS, GAME_CLOCK = range(8)
# The snapshot's numbers (Thor::Header in src/thor/Thor.cpp), then 8 per command, 5 per queue slot, 4 per go-to building
(H_VERSION, H_IN_GAME, H_WOOD, H_FOOD, H_GOLD, H_STONE, H_POP, H_POP_CAP, H_AGE, H_FLAGS, H_SELECTED, H_HP, H_MAX_HP, H_SEL_SLP, H_SEL_FRAME, H_SEL_UNIT,
 H_QUEUE_DONE, H_QUEUE_TOTAL, H_COMMANDS, H_QUEUE, H_MAP_SERIAL, H_MAP_W, H_MAP_H, H_VIEW) = range(24)
H_CIV, H_SPEED, H_GROUPS, H_GO_TOS, HEADER = 31, 32, 33, 37, 38
F_PLACING, F_AGE_RESEARCHING = 1, 2
KIND_CAPTION = 27  # UIRenderer::CommandKind: a tile that only says something
HOLD, CONFIRM = .42, 3.0  # seconds: a held tile or group, an armed "tap again"
# The interface art (1280x1024, interfac.drs 51141 + civilisation): its top bar's stockpile slots, the parchment, the stone
ART_BASE, ART_BAR, ART_PARCHMENT, ART_STONE = 51141, (0, 0, 477, 32), (346, 824, 500, 194), (36, 846, 270, 150)
ART_SLOT_RIGHT = (75, 152, 229, 306, 383)  # wood, food, gold, stone, population
C = {'bg': 0x0E0D0B, 'panel': 0x1A1814, 'hi': 0x26221B, 'line': 0x3A3328, 'amber': 0xE8B04A, 'text': 0xEDE6D6, 'dim': 0x8C8372, 'red': 0xD9573F, 'green': 0x6FBF4A,
     'ink': 0x2A1C0C, 'inkdim': 0x6B553A, 'bronze': 0xB89A5A, 'white': 0xFFFFFF}


def parse(d):
    """A state line of the game as the deck shows it, or None when no game is being played (or the line is cut short)."""
    i = (d or {}).get('i') or []
    if not (d or {}).get('ingame') or len(i) < HEADER: return None
    n, q, g = (max(0, min(15, i[k])) for k in (H_COMMANDS, H_QUEUE, H_GO_TOS))
    at_q = HEADER + n * 8
    at_g = at_q + q * 5
    if len(i) < at_g + g * 4: return None
    word = lambda key, k: (d.get(key) or [])[k] if k < len(d.get(key) or []) else ''
    commands = {}
    for k in range(n):
        slot, kind, slp, frame, enabled, affordable, count, _ = i[HEADER + k * 8:HEADER + k * 8 + 8]
        commands[slot] = {'kind': kind, 'icon': (slp, frame), 'enabled': enabled == 1, 'affordable': affordable == 1, 'count': count, 'name': word('labels', k),
                          'help': ' '.join(re.sub(r'</?[bi]>', '', word('help', k)).split())}
    queue = [{'slot': i[o], 'count': i[o + 2], 'icon': (i[o + 3], i[o + 4])} for o in range(at_q, at_g, 5)]
    go_to = [{'entry': i[o], 'count': i[o + 1], 'icon': (i[o + 2], i[o + 3]), 'name': word('goto', i[o])} for o in range(at_g, at_g + g * 4, 4)]
    return {'stock': i[H_WOOD:H_STONE + 1], 'pop': i[H_POP], 'cap': i[H_POP_CAP], 'age': d.get('age') or '', 'next': d.get('next') or '', 'flags': i[H_FLAGS],
            'selected': i[H_SELECTED], 'hp': i[H_HP], 'max': i[H_MAX_HP], 'icon': (i[H_SEL_SLP], i[H_SEL_FRAME]), 'unit': i[H_SEL_UNIT], 'name': d.get('name') or '',
            'done': i[H_QUEUE_DONE], 'total': i[H_QUEUE_TOTAL], 'commands': commands, 'queue': queue, 'goto': go_to, 'map': tuple(i[H_MAP_SERIAL:H_MAP_H + 1]),
            'view': [(i[H_VIEW + k * 2], i[H_VIEW + k * 2 + 1]) for k in range(4)], 'civ': i[H_CIV], 'speed': i[H_SPEED], 'groups': i[H_GROUPS:H_GROUPS + 4]}


def color(rgb, a=1.0): return QColor((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255, round(a * 255))


def box(l, t, r, b): return QRectF(l, t, r - l, b - t)


MAP_PANEL, MAP_AREA, SEL_PANEL, SPEED_BOX, GRID = box(16, 96, 640, 404), box(24, 104, 632, 396), box(724, 96, 1224, 404), box(1020, 494, 1152, 556), box(16, 618, 1224, 1064)
MAP_BUTTONS = [box(648, 96 + k * 78, 716, 170 + k * 78) for k in range(4)]  # normal, combat, economic, last alert
BUTTONS = [box(16 + k * 203, 414, 207 + k * 203, 486) for k in range(6)]
GROUPS = [box(16 + k * 158, 494, 164 + k * 158, 556) for k in range(4)]
SMALL = [box(656, 494, 826, 556), box(836, 494, 944, 556), box(954, 494, 1016, 556), box(1156, 494, 1224, 556)]  # find selection, flare, slower, faster
TABS = [box(16 + k * 406, 564, 412 + k * 406, 610) for k in range(3)]
TILES = [QRectF(16 + (k % 5) * 243.6, 618 + (k // 5) * 152, 233.6, 142) for k in range(15)]


class Deck:
    def __init__(self, window):
        self.w = window
        self.m, self.alive, self.tab, self.fonts = None, True, 0, {}
        self.icons, self.map, self.map_asked, self.art, self.art_slp, self.stage = {}, None, None, None, None, None
        self.pressed, self.held, self.help, self.help_until, self.armed = None, False, '', 0.0, (None, 0.0)
        self.painted, self.waiting, self.areas = 0.0, False, []
        self.link = Link((window.RUN.get('port') or {}).get('socket') or '', self.heard, self.block)

    def close(self):
        self.alive = False
        self.link.close()

    # ---- the game's data (on the link's thread) ------------------------------------------------------------------------
    def heard(self, d):
        if d is not None and 'v' not in d: return
        self.m = m = parse(d)
        if d is None:  # what was asked for is lost: ask again
            self.icons, self.map_asked, self.art_slp = {k: v for k, v in self.icons.items() if v is not None}, None, self.art and self.art_slp
        if m and m['map'] != self.map_asked and m['map'][1] > 0:
            self.map_asked = m['map']
            self.link.send('map')
        self.changed()

    def block(self, name, data):
        if name == 'map' and self.map_asked and len(data) == self.map_asked[1] * self.map_asked[2] * 4:
            _, w, h = self.map_asked
            self.map = QImage(data, w, h, w * 4, QImage.Format.Format_ARGB32).copy()  # copy: the bytes go
        elif name.startswith('icon:') and name.count(':') == 2:
            key, img = tuple(int(n) for n in name.split(':')[1:]), None
            if len(data) >= 4:
                w, h = struct.unpack_from('<HH', data)
                if len(data) == 4 + w * h * 4: img = QImage(data[4:], w, h, w * 4, QImage.Format.Format_ARGB32).copy()
            if key[0] == self.art_slp: self.art = self.cut_art(img) if img is not None and img.width() == 1280 else None
            else: self.icons[key] = img if img is not None else False  # False: asked, there is none
        self.changed()

    @staticmethod
    def cut_art(img):
        """The look of everything here, from the civilisation's interface picture: bar, parchment and the stone as a brush."""
        stone = img.copy(*ART_STONE)
        tile = QImage(stone.width() * 2, stone.height() * 2, QImage.Format.Format_RGB32)  # mirrored each way, so that it repeats without a seam
        q = QPainter(tile)
        for k in range(4): q.drawImage(k % 2 * stone.width(), k // 2 * stone.height(), stone.transformed(QTransform().scale(1 - k % 2 * 2, 1 - k // 2 * 2)))
        q.end()
        brush = QBrush(tile)
        brush.setTransform(QTransform().scale(2.5, 2.5))
        return {'bar': img.copy(*ART_BAR), 'parchment': img.copy(*ART_PARCHMENT), 'stone': brush}

    def icon(self, key):
        """An interface icon of the game, or None while it is on its way (or there is none)."""
        if key[0] <= 0 or key[1] < 0: return None
        if key not in self.icons:
            self.icons[key] = None
            self.link.send(f'icon {key[0]} {key[1]}')
        return self.icons[key] if isinstance(self.icons[key], QImage) else None  # None: on its way, False: there is none

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

    def cmd(self, kind, a=0, b=0): self.link.send(f'cmd {kind} {a} {b}')

    # ---- touch ----------------------------------------------------------------------------------------------------------
    def press(self, pos):
        """A finger down (pos) or up (None). The mini-map answers at once; a tile or a group held long enough shows its
        help or takes the selection, and its tap on release then does nothing."""
        if pos is None:
            self.pressed = None
            return self.changed()
        self.held = False
        at = self.stage.inverted()[0].map(pos) if self.stage else pos
        if self.m and MAP_AREA.contains(at):
            fx, fy = (at.x() - MAP_AREA.left()) / MAP_AREA.width(), (at.y() - MAP_AREA.top()) / MAP_AREA.height()
            return self.cmd(CMD_MINIMAP, int(max(0, min(.9999, fx)) * 65536), int(max(0, min(.9999, fy)) * 65536))
        self.pressed = key = next((key for rect, key in reversed(self.areas) if rect.contains(at)), None)
        if key and key[0] in ('group', 'tile'):
            timer = threading.Timer(HOLD, self.hold, (key,))
            timer.daemon = True
            timer.start()
        self.changed()

    def hold(self, key):
        if self.pressed != key or not self.m: return
        self.held = True
        if key[0] == 'group': self.cmd(CMD_GROUP_ASSIGN, key[1] + 1)
        elif self.tab == 0 and key[1] + 1 in self.m['commands']: self.say(self.m['commands'][key[1] + 1]['help'], 6)
        self.changed()

    def say(self, text, secs):
        self.help, self.help_until = text, time.time() + secs
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

    # ---- drawing helpers (stage coordinates; y is the text's baseline) -------------------------------------------------
    def font(self, size, bold):
        if (size, bold) not in self.fonts:
            f = QFont('serif')
            f.setStyleHint(QFont.StyleHint.Serif); f.setPixelSize(size); f.setBold(bold)
            self.fonts[size, bold] = (f, QFontMetricsF(f))
        return self.fonts[size, bold]

    def label(self, p, text, x, y, size, col, align=1, bold=True, room=None):
        """align: 0 left, 1 centred, 2 right. With room, a text too long ends in an ellipsis."""
        f, fm = self.font(size, bold)
        if room: text = fm.elidedText(text, Qt.TextElideMode.ElideRight, room)
        p.setFont(f); p.setPen(color(C[col]))
        p.drawText(QPointF(x - fm.horizontalAdvance(text) * align / 2, y), text)

    def wrapped(self, p, text, x, y, right, line_h, lines, size, col):
        f, fm = self.font(size, False)
        p.setFont(f); p.setPen(color(C[col]))
        line = ''
        for word in text.split():
            if line and fm.horizontalAdvance(line + ' ' + word) > right - x:
                p.drawText(QPointF(x, y), line)
                y, lines, line = y + line_h, lines - 1, word
                if not lines: return
            else: line = (line + ' ' + word).strip()
        p.drawText(QPointF(x, y), line)

    def panel(self, p, r, key=None, fill=None):
        """A button's face: carved into the stone with the light from the upper left, or a plain dark panel without the
        art. key names it for touch: it lights up while the finger is on it."""
        down = key is not None and self.pressed == key
        if key is not None: self.areas.append((r, key))
        p.setPen(Qt.PenStyle.NoPen if self.art else QPen(color(C['line']), 2))
        p.setBrush(fill if fill is not None else (color(0x463A26, .82) if down else color(0, .69)) if self.art else color(C['hi' if down else 'panel']))
        p.drawRoundedRect(r, 6, 6)
        if not self.art: return
        p.setPen(QPen(color(C['bronze']), 2))
        p.drawLine(QPointF(r.left() + 3, r.top() + 1), QPointF(r.right() - 3, r.top() + 1)); p.drawLine(QPointF(r.left() + 1, r.top() + 3), QPointF(r.left() + 1, r.bottom() - 3))
        p.setPen(QPen(color(0x1A140C), 2))
        p.drawLine(QPointF(r.left() + 3, r.bottom() - 1), QPointF(r.right() - 3, r.bottom() - 1)); p.drawLine(QPointF(r.right() - 1, r.top() + 3), QPointF(r.right() - 1, r.bottom() - 3))

    def picture(self, p, key, r, opacity=1.0):
        img = self.icon(key)
        if img is None: return
        p.setOpacity(opacity); p.drawImage(r, img); p.setOpacity(1)

    # ---- painting -----------------------------------------------------------------------------------------------------
    def paint(self, p):
        w, m = self.w, self.m
        s = min(w.width() / 1240, w.height() / 1080)
        self.stage = xf = QTransform().translate((w.width() - 1240 * s) / 2, (w.height() - 1080 * s) / 2).scale(s, s)
        self.painted, self.areas = time.time(), []
        p.save()
        p.fillRect(0, 0, w.width(), w.height(), color(C['bg']))
        p.setTransform(xf)
        p.setClipRect(QRectF(0, 0, 1240, 1080))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w.xf, w.zoom = xf, s  # taps arrive in window pixels
        try:
            if not m: self.idle(p)
            else:
                if ART_BASE + max(0, min(12, m['civ'] - 1)) != self.art_slp:
                    self.art_slp, self.art = ART_BASE + max(0, min(12, m['civ'] - 1)), None
                    self.link.send(f'icon {self.art_slp} 0')
                if self.art: p.fillRect(QRectF(0, 84, 1240, 996), self.art['stone'])
                self.header(p, m); self.minimap(p, m); self.selection(p, m); self.buttons(p, m); self.groups(p, m); self.tabs(p)
                (self.commands, self.go_to, self.game)[self.tab](p, m)
        finally:
            w.xf, w.zoom = None, 1.0
            p.restore()
        return True

    def leave(self, p, r):
        """Ends the game and returns to Tandem: asks first."""
        armed = self.is_armed('quit')
        self.panel(p, r, ('leave',), color(0x7A2418) if armed else None)
        self.label(p, 'Nochmal tippen' if armed else 'Beenden', r.center().x(), r.center().y() + 10, 28, 'text' if armed else 'red', room=r.width() - 16)
        self.w.hit(r, lambda: self.twice('quit') and self.w.post('api/quit'), name='Beenden')

    def idle(self, p):
        self.label(p, 'AGE OF KINGS', 620, 500, 96, 'amber')
        self.label(p, 'Starte oben ein Spiel', 620, 580, 36, 'dim', bold=False)
        self.leave(p, QRectF(500, 900, 240, 110))

    def header(self, p, m):
        values, pop, cap = [str(v) for v in m['stock']], m['pop'], m['cap']
        if self.art:  # the game's own top bar, its stockpile slots as they are; the numbers end at each slot's right edge
            p.drawImage(QRectF(0, 0, 1240, 84), self.art['bar'])
            k = 1240 / ART_BAR[2]
            for i, v in enumerate(values): self.label(p, v, ART_SLOT_RIGHT[i] * k - 10, 56, 36, 'white', 2)
            self.label(p, f'{pop}/{cap}', ART_SLOT_RIGHT[4] * k - 10, 56, 36, 'red' if pop >= cap else 'white', 2)
            left = ART_SLOT_RIGHT[4] * k + 8
            p.fillRect(box(left, 14, 1232, 70), color(0, .63))
            return self.label(p, m['age'], (left + 1232) / 2, 54, 32, 'amber', room=1216 - left)
        p.fillRect(QRectF(0, 0, 1240, 84), color(C['hi']))
        for i, (name, v) in enumerate(zip(('HOLZ', 'NAHRUNG', 'GOLD', 'STEIN', 'BEV.'), values + [f'{pop}/{cap}'])):
            self.label(p, name, 24 + i * 196, 30, 20, 'dim', 0, False)
            self.label(p, v, 24 + i * 196, 68, 38, 'red' if i == 4 and pop >= cap else 'text', 0)
        self.label(p, m['age'].upper(), 1216, 56, 34, 'amber', 2)

    def minimap(self, p, m):
        self.panel(p, MAP_PANEL)
        for i, (name, item) in enumerate((('KARTE', GAME_MAP_NORMAL), ('KAMPF', GAME_MAP_COMBAT), ('WIRT.', GAME_MAP_ECONOMIC), ('ALARM', GAME_NOTIFICATION))):
            self.panel(p, MAP_BUTTONS[i], ('mapmode', i))
            self.label(p, name, MAP_BUTTONS[i].center().x(), MAP_BUTTONS[i].center().y() + 6, 17, 'amber' if i == 3 else 'text')
            self.w.hit(MAP_BUTTONS[i], lambda item=item: self.cmd(CMD_GAME, item), name=name)
        _, mw, mh = m['map']
        if self.map is None or mw <= 0 or mh <= 0: return
        p.drawImage(MAP_AREA, self.map)
        p.save()
        p.setClipRect(MAP_AREA, Qt.ClipOperation.IntersectClip)
        p.setPen(QPen(color(C['white']), 2.5)); p.setBrush(Qt.BrushStyle.NoBrush)  # what the top screen shows
        p.drawPolygon(QPolygonF([QPointF(MAP_AREA.left() + x * MAP_AREA.width() / mw, MAP_AREA.top() + y * MAP_AREA.height() / mh) for x, y in m['view']]))
        p.restore()

    def selection(self, p, m):
        ink, dim = ('ink', 'inkdim') if self.art else ('text', 'dim')
        if self.art: p.drawImage(SEL_PANEL, self.art['parchment'])
        else: self.panel(p, SEL_PANEL)
        l, t, right = SEL_PANEL.left() + 28, SEL_PANEL.top() + 26, SEL_PANEL.right()
        if self.help and time.time() < self.help_until: return self.wrapped(p, self.help, l, t + 26, right - 28, 32, 8, 26, ink)
        if m['selected'] == 0 and m['unit'] < 0: return self.label(p, 'Nichts ausgewählt', SEL_PANEL.center().x(), SEL_PANEL.center().y(), 28, dim, bold=False)
        self.picture(p, m['icon'], QRectF(l, t, 128, 128))
        p.setPen(QPen(color(C['line']), 2)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(QRectF(l, t, 128, 128))
        self.label(p, m['name'] + (f'  ×{m["selected"]}' if m['selected'] > 1 else ''), l + 148, t + 40, 32, ink, 0, room=right - l - 168)
        if m['max'] > 0:
            bar = box(l + 148, t + 62, right - 32, t + 82)
            p.fillRect(bar, color(0x3A1A14))
            p.fillRect(QRectF(bar.left(), bar.top(), bar.width() * max(0, min(m['hp'], m['max'])) / m['max'], bar.height()), color(C['green']))
            self.label(p, f'{m["hp"]} / {m["max"]}', l + 148, t + 116, 26, dim, 0, False)
        # The queue: each item a small tile, the first with its progress; a tap takes it back.
        x, y = l, t + 142
        for k, item in enumerate(m['queue']):
            r = QRectF(x, y, 64, 64)
            self.panel(p, r, ('queue', k), color(0x463A26, .82))
            self.picture(p, item['icon'], r.adjusted(4, 4, -4, -4))
            if item['count'] > 1: self.label(p, f'×{item["count"]}', x + 8, y + 28, 24, 'amber', 0)
            if k == 0 and m['total'] > 0: p.fillRect(QRectF(x, y + 68, 64 * min(1, m['done'] / m['total']), 6), color(C['green']))
            self.w.hit(r, lambda slot=item['slot']: self.cmd(CMD_CANCEL_QUEUE, slot), name=f'queue{k}')
            x += 74
            if x + 64 > right - 24: x, y = l, y + 82

    def buttons(self, p, m):
        def delete():
            if self.twice('delete'): self.cmd(CMD_DELETE)
        armed, age_running = self.is_armed('delete'), m['flags'] & F_AGE_RESEARCHING
        # caption above (or None), name, colour, action
        items = [('UNTÄTIG', 'Dorfbewohner', 'text', lambda: self.cmd(CMD_IDLE_VILLAGER)), ('UNTÄTIG', 'Militär', 'text', lambda: self.cmd(CMD_IDLE_MILITARY)),
                 (None, 'Dorfzentrum', 'text', lambda: self.cmd(CMD_TOWN_CENTER)),
                 ('NÄCHSTES ZEITALTER', m['next'] or 'Nächstes Zeitalter', 'green' if age_running else 'amber', lambda: self.cmd(CMD_AGE_UP)),
                 ('SICHER? NOCHMAL TIPPEN' if armed else None, 'Löschen', 'text' if armed else 'red', delete), (None, 'Menü', 'text', lambda: self.cmd(CMD_MENU))]
        for i, (caption, name, col, act) in enumerate(items):
            r = BUTTONS[i]
            self.panel(p, r, ('button', i), color(0x7A2418) if armed and i == 4 else None)
            if caption:
                self.label(p, caption, r.center().x(), r.top() + 26, 13 if i == 4 else 15, 'text' if i == 4 else 'dim', bold=i == 4, room=r.width() - 10)
                self.label(p, name, r.center().x(), r.top() + 56, 23, col, room=r.width() - 12)
            else: self.label(p, name, r.center().x(), r.center().y() + 10, 26, col, room=r.width() - 16)
            self.w.hit(r, act, name=name)

    def groups(self, p, m):
        def pick(k):
            self.cmd(CMD_GROUP_SELECT, k + 1)
            if not m['groups'][k]: self.say('Gruppe ist leer. Einheiten auswählen, dann diesen Knopf halten, um sie zu speichern. Tippen ruft die Gruppe auf, nochmal tippen springt zu ihr.', 4)
        for k, r in enumerate(GROUPS):
            n = m['groups'][k]
            self.panel(p, r, ('group', k))
            self.label(p, ('I', 'II', 'III', 'IV')[k], r.left() + 40 if n else r.center().x(), r.center().y() + 12, 32, 'amber' if n else 'dim')
            if n: self.label(p, f'×{n}', r.right() - 14, r.center().y() + 10, 28, 'text', 2)
            self.w.hit(r, self.tap(lambda k=k: pick(k)), name=f'group{k + 1}')
        for k, (name, act) in enumerate((('Einheit finden', lambda: self.cmd(CMD_GAME, GAME_TO_SELECTED)), ('Signal', lambda: self.cmd(CMD_GAME, GAME_FLARE)),
                                         ('−', lambda: self.cmd(CMD_SPEED, -1)), ('+', lambda: self.cmd(CMD_SPEED, 1)))):
            r = SMALL[k]
            self.panel(p, r, ('small', k))
            self.label(p, name, r.center().x(), r.center().y() + (7 if k < 2 else 13), 20 if k < 2 else 40, 'text', room=r.width() - 12)
            self.w.hit(r, act, name={'−': 'slower', '+': 'faster'}.get(name, name))
        self.label(p, 'TEMPO', SPEED_BOX.center().x(), SPEED_BOX.top() + 22, 15, 'dim', bold=False)
        self.label(p, f'{m["speed"] / 100:g}×', SPEED_BOX.center().x(), SPEED_BOX.bottom() - 8, 28, 'amber' if m['speed'] > 100 else 'text')

    def tabs(self, p):
        for k, name in enumerate(('BEFEHLE', 'GEHE ZU', 'SPIEL')):
            r = TABS[k]
            self.panel(p, r, ('tab', k), None if k != self.tab else color(0x463A26, .82) if self.art else color(C['hi']))
            self.label(p, name, r.center().x(), r.center().y() + 9, 24, 'amber' if k == self.tab else 'dim')
            if k == self.tab: p.fillRect(box(r.left() + 12, r.bottom() - 5, r.right() - 12, r.bottom() - 2), color(C['amber']))
            self.w.hit(r, lambda k=k: setattr(self, 'tab', k), name=name)

    def empty(self, p, r):
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(0, .38) if self.art else color(0x15130F))
        p.drawRoundedRect(r, 6, 6)

    def tile(self, p, k, key, name, col='text', count=None, opacity=1.0):
        """A tile with the game's icon, a number on it and its name below."""
        r = TILES[k]
        self.panel(p, r, ('tile', k))
        side = min(r.height() - 48, r.width() - 40)
        ir = QRectF(r.center().x() - side / 2, r.top() + 10, side, side)
        self.picture(p, key, ir, opacity)
        if count is not None: self.label(p, count, *((ir.right() + 8, ir.top() + 30) if count.startswith('×') else (ir.left() + 6, ir.top() + 28)), 26, 'amber', 0)
        self.label(p, name, r.center().x(), r.bottom() - 12, 21, col, bold=False, room=r.width() - 16)

    def commands(self, p, m):
        """The selection's commands, where the game's panel has them."""
        for k, r in enumerate(TILES):
            c = m['commands'].get(k + 1)
            if not c: self.empty(p, r)
            elif c['kind'] == KIND_CAPTION:
                self.panel(p, r)
                self.label(p, c['name'], r.center().x(), r.center().y() + 12, 32, 'dim', room=r.width() - 16)
            else:
                self.tile(p, k, c['icon'], c['name'], 'dim' if not c['enabled'] else 'text' if c['affordable'] else 'red', str(c['count']) if c['count'] >= 0 else None, 1 if c['enabled'] else .35)
                self.w.hit(r, self.tap(lambda k=k: (self.cmd(CMD_COMMAND, k + 1), setattr(self, 'help_until', 0.0))), name=f'command{k + 1}')
        if m['flags'] & F_PLACING:
            p.fillRect(box(GRID.left(), GRID.bottom() - 40, GRID.right(), GRID.bottom()), color(0, .82))
            self.label(p, 'Oben das Gebäude setzen', GRID.center().x(), GRID.bottom() - 12, 24, 'amber')

    def go_to(self, p, m):
        """The player's buildings, one tile a kind: a tap goes to the next of them."""
        for k, r in enumerate(TILES):
            if k >= len(m['goto']): self.empty(p, r); continue
            b = m['goto'][k]
            self.tile(p, k, b['icon'], b['name'], count=f'×{b["count"]}' if b['count'] > 1 else None)
            self.w.hit(r, lambda entry=b['entry']: self.cmd(CMD_GO_TO, entry), name=f'goto{b["entry"]}')
        if not m['goto']: self.label(p, 'Hier erscheinen deine Gebäude', GRID.center().x(), GRID.center().y(), 28, 'dim', bold=False)

    def game(self, p, m):
        items = (('Ziele', (CMD_OBJECTIVES,)), ('Technologien', (CMD_TECH_TREE,)), ('Statistik', (CMD_GAME, GAME_STATISTICS)), ('Spielzeit', (CMD_GAME, GAME_CLOCK)), ('Menü', (CMD_MENU,)))
        for k, r in enumerate(TILES):
            if k == 14: self.leave(p, r)
            elif k >= len(items): self.empty(p, r)
            else:
                self.panel(p, r, ('tile', k))
                self.label(p, items[k][0], r.center().x(), r.center().y() + 10, 28, 'text', room=r.width() - 16)
                self.w.hit(r, lambda args=items[k][1]: self.cmd(*args), name=items[k][0])
