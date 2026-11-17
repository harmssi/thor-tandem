"""Deck for Diablo II (the native port in ports/d2: Thor D2, a fork of D2Android, under Proton) on the bottom screen.

A rebuild of Thor D2's Android deck (D2Deck.java, 1240 x 1080): header with name, class, area and gold; life and mana orbs,
experience and mercenary; resistances and attributes (+ spends a stat point); left/right/F1-F8 skills; effects and auras;
tabs Inventory, Skills, Stash, Cube, Mercenary, Quests; the waypoint list while the game's waypoint menu is open; items by
tap or drag (swap, double tap moves over, use, belt, identify, sell, drop); sort inventory/stash, gold in/out, sell junk,
portal, potion, transmute. It looks like the game when the player's game files are there (decks/d2art.py reads them),
else in its own dark look.

ports/d2's pad.py passes every packet of the mod on to 127.0.0.1:7958 (D2ModLink's packets: 1 status, 2 state, 6 effects/
name/points, 9 quests, 40/41 the deck's data …) and adds b'D2PD' + (wheel open, entry or 255): the pad's window wheel.
Commands go straight to the mod at 127.0.0.1:7959 ('D2AC', version 1, command, 0, 0, payload little-endian).
Before a character is in the game, the deck shows what ports/d2's setup.py writes to data/setup.json, and BEENDEN.

Interface for tandem_ui (see DECKS there): Deck(window), paint(painter) -> bool, close().
"""
import json, math, os, socket, struct, threading, time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen, QRadialGradient, QTransform

APP_PORT, MOD_PORT = 7958, 7959
STATUS, STATE, EFFECTS, QUESTS, STATS, ITEMS = 1, 2, 6, 9, 40, 41
INV, BELT, BODY, STASH, CUBE = range(5)
CMD_DRINK, CMD_PORTAL, CMD_SELECT_SKILL, CMD_SELL_JOB, CMD_POINTS, CMD_SORT, CMD_CUBE_OPEN, CMD_DECK_ITEM, CMD_TRANSMUTE = 1, 7, 13, 17, 19, 24, 37, 38, 39
DI_MOVE, DI_USE, DI_IDENTIFY, DI_SELL, DI_GOLD, DI_WAYPOINT = 1, 2, 3, 5, 6, 7
DI_TO_INV, DI_TO_CUBE, DI_TO_STASH, DI_TO_BELT, DI_TO_BODY, DI_TO_GROUND = 0, 3, 4, 10, 11, 12
KIND_STAT, KIND_SKILL, KIND_KEY = 0, 1, 2
SORT_RUNNING, SORT_DONE, SORT_PARTIAL, SORT_CURSOR, SORT_NO_ROOM = 0, 1, 2, 3, 5
UI_WAYPOINT, UI_NPCSHOP, UI_STASH, UI_CUBE = 0x14, 0x0C, 0x19, 0x1A
GRIDS_INV_W, GRIDS_INV_H, GRIDS_CUBE_W, GRIDS_CUBE_H, GRIDS_STASH_W, GRIDS_STASH_H = 1, 2, 3, 4, 5, 6
WAYPOINT_LEVELS = (1, 3, 4, 5, 6, 27, 29, 32, 35, 40, 48, 42, 57, 43, 44, 52, 74, 46, 75, 76, 77, 78, 79, 80, 81, 83, 101, 103, 106, 107, 109,
                   111, 112, 113, 115, 123, 117, 118, 129)
DATA = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'tandem-ports/d2/data'
SETUP, GAME = DATA / 'setup.json', DATA / 'game'
CACHE = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'tandem/d2'
W, H = 1240, 1080
GOLD, TEXT, DIM, RED, PANEL_FILL, EDGE, XP, MERC = 0xFFC7B377, 0xFFE8E2D2, 0xFF8F8775, 0xFFD04040, 0xE0100C09, 0xFF5A4A30, 0xFFB89A3A, 0xFF3FA040
TAB_INV, TAB_SKILLS, TAB_STASH, TAB_CUBE, TAB_MERC, TAB_QUESTS = range(6)
TABS = ('Inventar', 'Fertigk.', 'Truhe', 'Würfel', 'Söldner', 'Quests')
CLASSES = ('Amazone', 'Zauberin', 'Totenbeschwörer', 'Paladin', 'Barbar', 'Druide', 'Assassine')
DIFFICULTY = ('Normal', 'Albtraum', 'Hölle')
SLOTS = ('', 'Kopf', 'Amulett', 'Rüstung', 'Rechts', 'Links', 'Ring r.', 'Ring l.', 'Gürtel', 'Stiefel', 'Handsch.', 'Waffe 2 r.', 'Waffe 2 l.')
KEY_PAD = ('X', 'Y', 'R3', 'RB+R3', 'RB+X', 'RB+Y', 'RB+A', 'RB+B')  # F1..F8 on the pad, as Thor D2's defaults
QUESTS_EN = (('Den of Evil', "Sisters' Burial Grounds", 'Tools of the Trade', 'The Search for Cain', 'The Forgotten Tower', 'Sisters to the Slaughter'),
             ("Radament's Lair", 'The Horadric Staff', 'Tainted Sun', 'Arcane Sanctuary', 'The Summoner', 'The Seven Tombs'),
             ("Lam Esen's Tome", "Khalim's Will", 'Blade of the Old Religion', 'The Golden Bird', 'The Blackened Temple', 'The Guardian'),
             ('The Fallen Angel', "Terror's End", "Hell's Forge"),
             ('Siege on Harrogath', 'Rescue on Mount Arreat', 'Prison of Ice', 'Betrayal of Harrogath', 'Rite of Passage', 'Eve of Destruction'))
QUEST_FIRST_WORD = (1, 9, 17, 25, 35)
# effects (D2Effects): shrines and potions with the game's name key and our text; harms; skill states
EFFECT_INFO = {128: ('ShrId6', '+100 % Verteidigung'), 129: ('ShrId7', '+200 % Angriffswert und Schaden'), 130: ('ShrId10', '+75 % Blitzwiderstand'),
               131: ('ShrId8', '+75 % Feuerwiderstand'), 132: ('ShrId9', '+75 % Kältewiderstand'), 133: ('ShrId11', '+75 % Giftwiderstand'),
               134: ('ShrId12', '+2 auf alle Fertigkeiten'), 135: ('ShrId13', 'Mana lädt sich 5x so schnell auf'), 136: ('ShrId14', 'Ausdauer unbegrenzt'),
               137: ('ShrId15', 'x1,5 Erfahrung (+50 %)'), 100: ('hp3', 'Leben füllt sich auf'), 106: ('mp3', 'Mana füllt sich auf'),
               180: ('vps', 'Ausdauer erholt sich viel schneller'), 178: ('yps', '+50 % Giftwiderstand, Vergiftung endet'),
               179: ('wms', '+50 % Kältewiderstand, Einfrieren endet')}
HARMS = ((1, -1, 'Eingefroren: Bewegung, Angriff und Erholung stark verlangsamt'), (2, -1, 'Vergiftet: verliert Leben über die Zeit'),
         (11, 44, 'Unterkühlt: Bewegung und Angriff verlangsamt'), (21, 139, 'Betäubt: kann sich nicht bewegen und nicht angreifen'),
         (24, 87, 'Verlangsamt: Bewegung und Angriff langsamer'), (52, 82, 'Heilung verhindert: Leben erholt sich nicht'),
         (62, 67, 'Offene Wunden: verliert Leben über die Zeit'))
WHEEL = ('Inv.', 'Char.', 'Skills', 'Karte', 'Quests', 'Söldner', 'Pause', 'Rezepte')
WHEEL_ICONS = (2, 0, 4, 8, 12, -1, -2, -3)  # minipanelbtn frames; -1 mercenary, -2 pause bars, -3 cube
PAUSED_NOTE = 'Spiel pausiert: erst oben fortsetzen'


# ---- the mod's packets (plain Python) ----------------------------------------------------------------------------------
def kind(data):
    return data[5] if len(data) >= 8 and data[:4] == b'D2AM' and data[4] == 2 else -1


def parse_stats(d):
    """Packet 40: difficulty, values {stat: value}, mercenary, single player, waypoints (only while the menu is open)."""
    try:
        diff, n = d[8], d[9]
        values = dict(struct.unpack_from('<HI', d, 10 + 6 * i) for i in range(n))
        at = 10 + 6 * n
        life, top = struct.unpack_from('<II', d, at + 1)
        return {'difficulty': diff, 'v': values, 'merc': d[at] != 0, 'merc_life': life, 'merc_max': top, 'merc_level': d[at + 9],
                'single': len(d) > at + 10 and d[at + 10] != 0, 'waypoints': d[at + 12:at + 17] if len(d) > at + 16 and d[at + 11] else None}
    except (struct.error, IndexError):
        return None


def parse_items(d):
    """Packet 41: (owner, chunk, [item...]) or None."""
    try:
        owner, chunk, n, at, items = d[8] & 1, d[9], d[10], 11, []
        for _ in range(n):
            iid, code, page, x, y, size, quality, flags, quantity, ln = struct.unpack_from('<I4sBBBBBBHB', d, at)
            name = d[at + 17:at + 17 + ln]
            if len(name) != ln: return None
            items.append({'id': iid, 'code': code.decode('latin-1').strip(), 'page': page, 'x': x, 'y': y, 'w': max(1, size >> 4), 'h': max(1, size & 15),
                          'q': quality, 'flags': flags, 'n': quantity, 'name': name.decode('utf-8', 'replace')})
            at += 17 + ln
        return owner, chunk, items
    except (struct.error, IndexError):
        return None


def parse_state(d):
    """Packet 2 (D2ModState), only what the deck uses: open windows, area, town, paused, class and skills."""
    try:
        ui_low, ui_high, level, town, flags = struct.unpack_from('<IIHBB', d, 16)
        n, at = d[58], 59  # monsters: id, x, y, life, flags, name
        for _ in range(n): at += 11 + d[at + 10]
        for _ in range(2): at += 1 + 10 * d[at]
        s = {'ui': ui_low | ui_high << 32, 'level': level, 'town': town != 0, 'paused': flags & 64 != 0, 'cls': -1, 'left': -1, 'right': -1, 'keys': [-1] * 16}
        if at < len(d):
            s['cls'] = d[at]
            sk = lambda v: -1 if v == 0xFFFF else v
            s['left'], s['right'] = (sk(v) for v in struct.unpack_from('<HH', d, at + 1))
            s['keys'] = [sk(struct.unpack_from('<H', d, at + 5 + 3 * i)[0]) for i in range(16)]
        return s
    except (struct.error, IndexError):
        return None


def parse_info(d):
    """Packet 6: effects, game flags, the character's name, and the extension: points, experience, grids."""
    try:
        n = d[9]
        effects = [struct.unpack_from('<HHH', d, 10 + 6 * i) for i in range(n)] if len(d) >= 10 + 6 * n else []
        effects = [(s & 0x7FFF, left, full, s & 0x8000 != 0) for s, left, full in effects]
        at = 10 + n * 6
        flags = d[at] if len(d) > at else -1
        name = d[at + 1:at + 17].split(b'\0')[0].decode('latin-1') if len(d) >= at + 17 else ''
        info = {'effects': effects, 'flags': flags, 'name': name or None, 'points': None, 'xp': None, 'grids': None}
        buffs = at + 1 + 16 + 2
        if len(d) <= buffs: return info
        ext = buffs + 1 + d[buffs] + 16
        if len(d) <= ext: return info
        size = d[ext]
        if len(d) < ext + 1 + size: return info
        if size >= 67:
            p = ext + 1
            features = d[p + 2]
            info['points'] = {'features': features, 'first': -1 if struct.unpack_from('<H', d, p + 16)[0] == 0xFFFF else struct.unpack_from('<H', d, p + 16)[0],
                              'levels': list(d[p + 18:p + 48]), 'sort_counter': d[p + 69] if size >= 72 else -1,
                              'sort_state': d[p + 70] & 0x7F if size >= 72 else -1, 'sort_moves': d[p + 71] if size >= 72 else -1}
        if size >= 120: info['xp'] = struct.unpack_from('<III', d, ext + 109)
        if size >= 133: info['grids'] = list(d[ext + 126:ext + 134])
        return info
    except (struct.error, IndexError):
        return None


def parse_quests(d):
    if len(d) < 10 or len(d) < 10 + 2 * d[9]: return None
    return list(struct.unpack_from(f'<{d[9]}H', d, 10))


def command(cmd, payload=b''):
    return b'D2AC' + bytes((1, cmd)) + b'\0\0' + bytes(payload)


def points_command(kind_, what, key=0, move=False):
    return command(CMD_POINTS, bytes((kind_, what & 0xFF, what >> 8 & 0xFF, key if kind_ == KIND_KEY else 0)) + (b'\1' if move and kind_ == KIND_KEY else b''))


def deck_item(op, iid, to=0, x=0, y=0, other=0):
    return command(CMD_DECK_ITEM, struct.pack('<BIBBBI', op, iid, to, x, y, other))


def resistance(stats, stat, max_stat):
    """As the character screen shows it: minus 40 (Nightmare) or 100 (Hell), at most 75 + the bonus to the maximum."""
    v = stats['v']
    penalty = {1: 40, 2: 100}.get(stats['difficulty'], 0)
    return min(_signed(v.get(stat, 0)) - penalty, 75 + _signed(v.get(max_stat, 0)))


def _signed(x): return x - (1 << 32) if x >= 1 << 31 else x


def act_of(level):
    return 0 if level <= 0 else 1 if level < 40 else 2 if level < 75 else 3 if level < 103 else 4 if level < 109 else 5


def free_spot(items, page, gw, gh, w, h):
    """The first free place for a w x h item in a grid, row by row; None when there is none."""
    used = {(x, y) for o in items if o['page'] == page for y in range(o['y'], min(gh, o['y'] + o['h'])) for x in range(o['x'], min(gw, o['x'] + o['w']))}
    return next(((x, y) for y in range(gh - h + 1) for x in range(gw - w + 1) if not any((x + i, y + j) in used for j in range(h) for i in range(w))), None)


def beltable(it): return it['code'].startswith(('hp', 'mp')) or it['code'] in ('rvs', 'rvl', 'yps', 'vps', 'wms', 'tsc', 'isc')


def usable(it): return (beltable(it) and it['code'] != 'isc') or it['code'] == 'tbk'


def identified(it): return it['flags'] & 4 != 0


def one_line(it): return it['name'].replace('\n', ' ').strip() if it['name'] else it['code']


def quality_color(it):
    if it['flags'] & 8: return 0xFFC7B377  # runeword
    return {4: 0xFF6969FF, 5: 0xFF00C400, 6: 0xFFFFFF64, 7: 0xFFC7B377, 8: 0xFFFFA800}.get(it['q'], 0xFF8A8A8A if it['flags'] & 3 else 0xFFE8E8E8)


def brighter(c):  # the game's glyphs are not white: tinting multiplies, so the colour is lifted
    return 0xFF000000 | sum(min(255, (c >> s & 255) * 13 // 10 + 40) << s for s in (16, 8, 0))


def effect_time(tenths):
    s = (tenths + 9) // 10
    return f'{s // 60}:{s % 60:02d}' if s >= 60 else str(s)


def color(argb): return QColor.fromRgba(argb & 0xFFFFFFFF)


class Touch(QObject):
    """Drag and drop needs the finger's moves, which tandem_ui does not pass to decks."""
    def __init__(self, deck):
        super().__init__()
        self.deck = deck

    def eventFilter(self, obj, e):
        t = e.type()
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease): self.deck.touch(t, e.position())
        return False


class Deck:
    def __init__(self, window):
        self.w, self.alive, self.sock = window, True, None
        self.state = self.stats = self.info = None
        self.state_at = self.stats_at = self.info_at = self.status_at = 0.0
        self.status, self.items, self.building, self.quests = -1, [[], []], [[], []], None
        self.game_since, self.quest_game, self.quest_packets, self.quest_first = 0.0, -1.0, 0, 0.0
        self.wheel = (False, 255)
        self.book, self.recipes = None, None  # Thor D2's recipe book on the cube tab: [category, page] while open; its entries
        self.ring = None  # the pad's target ring: (page, pages, [(what, quality, chosen, label)]) while B is held
        self.art, self.armed = None, 0.0
        self.tab, self.selected, self.picked, self.wp_act = TAB_INV, None, -1, 0
        self.note, self.note_until, self.sort_sent, self.junk_armed, self.last_tap = '', 0.0, 0.0, 0.0, (None, 0.0)
        self.hits, self.xf, self.fonts, self.grids = [], None, {}, None
        self.down = self.drag = None
        self.touch_filter = Touch(self)
        window.installEventFilter(self.touch_filter)
        threading.Thread(target=self.listen, daemon=True).start()
        threading.Thread(target=self.tick, daemon=True).start()
        threading.Thread(target=self.load_art, daemon=True).start()

    def close(self):
        self.alive = False
        self.w.removeEventFilter(self.touch_filter)
        if self.sock: self.sock.close()
        if self.art: self.art.s.close()

    def load_art(self):
        try: self.art = __import__('decks.d2art', fromlist=['Art']).Art(GAME, CACHE)
        except Exception as error:  # no or broken game files: our own look
            print(f'd2 deck: own look ({error})')
            return
        try: self.recipes = __import__('decks.d2recipes', fromlist=['book']).book(self.art.s.read, self.art.strings)
        except (OSError, ValueError, struct.error) as error: print(f'd2 deck: no recipe book ({error})')
        if self.alive: self.w.loaded.emit()

    # ---- the mod ------------------------------------------------------------------------------------------------------
    def listen(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', APP_PORT))
            s.settimeout(1)
            self.sock = s
        except OSError as error:
            self.say(f'Port {APP_PORT} belegt: {error}', 3600)
            return
        while self.alive:
            try: data = s.recv(8192)
            except socket.timeout: continue
            except OSError: return
            self.heard(data)

    def heard(self, data, now=None):
        now = now or time.monotonic()
        if data[:4] == b'D2PD' and len(data) >= 6:
            self.wheel = (data[4] != 0, data[5])
            return self.w.loaded.emit()
        if data[:4] == b'D2PB':  # the pad's wheel chose the recipe book
            self.tab, self.book = TAB_CUBE, self.book or [0, 0, 0]
            return self.w.loaded.emit()
        if data[:4] == b'D2PR' and len(data) >= 5:
            self.ring = parse_ring(data)
            return self.w.loaded.emit()
        t = kind(data)
        if t == STATE:
            s = parse_state(data)
            if s:
                if now - self.state_at > 1: self.game_since = now
                self.state, self.state_at = s, now
        elif t == STATUS and len(data) >= 10: self.status, self.status_at = data[8], now
        elif t == EFFECTS:
            info = parse_info(data)
            if info: self.info, self.info_at = info, now
        elif t == QUESTS:
            q = parse_quests(data)
            if q is not None:
                if self.quest_game != self.game_since: self.quest_game, self.quest_packets, self.quest_first = self.game_since, 0, now
                self.quest_packets, self.quests = self.quest_packets + 1, q
        elif t == STATS:
            st = parse_stats(data)
            if st: self.stats, self.stats_at = st, now
        elif t == ITEMS:
            got = parse_items(data)
            if got:
                owner, chunk, items = got
                if chunk == 0: self.building[owner] = []
                self.building[owner] = self.building[owner] + items
                self.items[owner] = self.building[owner]

    def tick(self):  # four times a second, as the Android deck: the values change all the time
        while self.alive:
            self.w.loaded.emit()
            time.sleep(.25)

    def send(self, data):
        if self.sock:
            try: self.sock.sendto(data, ('127.0.0.1', MOD_PORT))
            except OSError: pass

    def say(self, text, secs=4):
        self.note, self.note_until = text, time.monotonic() + secs

    def fresh(self, at, secs): return time.monotonic() - at < secs

    def single(self):
        info = self.info if self.fresh(self.info_at, 2.5) else None
        return bool(self.stats and self.stats['single'] and info and info['flags'] >= 0 and info['flags'] & 1)

    def points(self): return self.info['points'] if self.info and self.fresh(self.info_at, 3) else None

    def can(self, pts, k): return pts is not None and pts['features'] & (0x04 << k) != 0

    def is_open(self, ui): return bool(self.state and self.state['ui'] >> ui & 1)

    def quest_words(self):
        if self.quests is None or not (self.quest_packets >= 2 or (self.quest_packets == 1 and self.quest_first - self.game_since >= 1)): return None
        return self.quests

    # ---- drawing helpers (design pixels) ------------------------------------------------------------------------------
    def hit(self, r, fn, item=None, drop=False, name=''):
        self.hits.append((QRectF(r), fn, item, drop))
        self.w.hit(QRectF(r), fn, name=name)

    def qfont(self, size, bold=False):
        key = (round(size, 1), bold)
        if key not in self.fonts:
            f = QFont('serif')
            f.setPixelSize(max(1, round(size)))
            f.setBold(bold)
            self.fonts[key] = (f, QFontMetricsF(f))
        return self.fonts[key]

    def width(self, s, size):
        if self.art: return self.art.body.width(s, size * .78)
        return self.qfont(size)[1].horizontalAdvance(s)

    def body(self, p, s, x, y, size, argb, align=0):
        if self.art: return self.art.body.draw(p, s.replace('·', '-'), x, y + size * .15, size * .78, brighter(argb), align)
        self.plain(p, s, x, y, size, argb, align, False)

    def title(self, p, s, x, y, size, argb, align=0):
        if self.art: return self.art.title.draw(p, s.replace('·', '-'), x, y + size * .1, size * .85, brighter(argb), align)
        self.plain(p, s, x, y, size, argb, align, True)

    def plain(self, p, s, x, y, size, argb, align, bold):
        f, fm = self.qfont(size, bold)
        p.setFont(f)
        p.setPen(color(argb))
        p.drawText(QPointF(x - (fm.horizontalAdvance(s) / (2 if align == 1 else 1) if align else 0), y), s)

    def ellipsize(self, s, max_w, size):
        if self.width(s, size) <= max_w: return s
        n = len(s)
        while n > 1 and self.width(s[:n] + '…', size) > max_w: n -= 1
        return s[:n] + '…'

    def panel(self, p, l, t, r, b, fill=PANEL_FILL):
        rect = QRectF(l, t, r - l, b - t)
        if self.art and self.art.frame:
            p.drawImage(rect, self.art.frame.compose(round(rect.width() / 1.5), round(rect.height() / 1.5), fill))
            return
        p.fillRect(rect, color(fill))
        self.stroke(p, rect, EDGE, 3)
        self.stroke(p, QRectF(l + 5, t + 5, r - l - 10, b - t - 10), 0xFF2A2116, 1)

    def stroke(self, p, r, argb, w):
        p.setPen(QPen(color(argb), w))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)

    def button(self, p, r, label, enabled, fn):
        self.panel(p, r.left(), r.top(), r.right(), r.bottom())
        p.fillRect(r.adjusted(6, 6, -6, -6), color(0x30C7B377 if enabled else 0x60000000))
        self.body(p, label, r.center().x(), r.center().y() + 9, 22, GOLD if enabled else DIM, 1)
        if enabled: self.hit(r, fn, name=label)

    def skill_name(self, sid):
        n = self.art.skill_name[sid] if self.art and 0 <= sid < len(self.art.skill_name) else None
        return n or f'#{sid}'

    def skill_icon(self, sid): return self.art.skill_icon(sid) if self.art and sid >= 0 else None

    def picture(self, it): return self.art.picture(it['code'], it['q'], self.w.loaded.emit) if self.art else None

    # ---- paint ----------------------------------------------------------------------------------------------------------
    def paint(self, p):
        w = self.w
        k = min(w.width() / W, w.height() / H)
        self.xf = xf = QTransform.fromTranslate((w.width() - W * k) / 2, (w.height() - H * k) / 2).scale(k, k)
        p.save()
        p.fillRect(0, 0, w.width(), w.height(), color(0xFF070605))
        p.setTransform(xf)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, color(0xFF15110D)); g.setColorAt(1, color(0xFF070605))
        p.fillRect(QRectF(0, 0, W, H), g)
        w.xf, w.zoom = xf, k
        self.hits = []
        try:
            s = self.state if self.fresh(self.state_at, .5) else None
            st = self.stats if self.fresh(self.stats_at, 3) else None
            if s is None or st is None: self.waiting(p)
            else: self.game(p, s, st)
            if self.wheel[0]: self.draw_wheel(p)
            elif self.ring: self.draw_ring(p)
        finally:
            w.xf, w.zoom = None, 1.0
            p.restore()
        return True

    def game(self, p, s, st):
        self.header(p, s, st)
        self.orbs(p, st)
        self.values(p, st)
        self.skills(p, s)
        self.effects(p)
        self.tabs(p)
        content = QRectF(616, 182, 608, 718)
        info = self.info if self.fresh(self.info_at, 3) else None
        self.grids = info and info['grids']
        waypoints = st['waypoints'] is not None and self.is_open(UI_WAYPOINT)
        if not waypoints: self.wp_act = 0
        hero = self.items[0]
        if waypoints: self.waypoints(p, s, st, content)
        elif self.tab == TAB_INV: self.inventory(p, content)
        elif self.tab == TAB_STASH: self.grid_page(p, hero, STASH, self.dim(GRIDS_STASH_W, 6), self.dim(GRIDS_STASH_H, 8), content, 'Truhe leer oder noch nicht geladen')
        elif self.tab == TAB_CUBE and self.book: self.recipe_book(p, content)
        elif self.tab == TAB_CUBE: self.grid_page(p, hero, CUBE, self.dim(GRIDS_CUBE_W, 3), self.dim(GRIDS_CUBE_H, 4), content, 'Würfel ist leer')
        elif self.tab == TAB_MERC: self.merc(p, st, content)
        elif self.tab == TAB_SKILLS: self.skill_keys(p, s, st, content)
        else: self.quest_page(p, s, content)
        self.actions(p, st)
        held = self.held() if self.drag else None
        ghost = self.picture(held) if held else None
        if ghost is not None:  # the item follows the finger
            d = self.drag
            p.setOpacity(200 / 255)
            p.drawImage(QRectF(d['x'] - d['gx'], d['y'] - d['gy'], d['w'], d['h']), ghost)
            p.setOpacity(1)

    def dim(self, i, fallback): return self.grids[i] if self.grids and self.grids[i] > 0 else fallback

    def waiting(self, p):
        self.panel(p, 16, 16, 1224, 1064)
        try: setup = json.loads(SETUP.read_text())
        except (OSError, ValueError): setup = None
        self.title(p, 'Thor D2', W / 2, 500 if not setup or setup.get('done') else 300, 56, GOLD, 1)
        if setup and not setup.get('done'):  # ports/d2's installer is at work
            f, _ = self.qfont(30, True)
            p.setFont(f); p.setPen(color(TEXT))
            p.drawText(QRectF(80, 370, W - 160, 100), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), setup.get('text', ''))
            if setup.get('percent') is not None and not setup.get('error'):
                r = QRectF(160, 480, W - 320, 36)
                p.fillRect(r, color(0xFF0A0807))
                p.fillRect(QRectF(r.x(), r.y(), r.width() * max(0, min(100, setup['percent'])) / 100, r.height()), color(XP))
                self.stroke(p, r, EDGE, 2)
            if setup.get('error'):
                p.setPen(color(RED))
                p.drawText(QRectF(100, 540, W - 200, 200), int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap), setup['error'])
            if setup.get('step') == 'keys': self.body(p, 'Die Installation geht los, sobald die zwei CD-Keys da sind.', W / 2, 600, 24, DIM, 1)
        else:
            connected = self.status == 1 and self.fresh(self.status_at, 3)
            self.body(p, 'Warte auf einen Charakter im Spiel …' if connected else 'Warte auf das Spiel …', W / 2, 560, 28, DIM, 1)
        self.body(p, 'Im Menü: Stick Zeiger · A Linksklick · X Rechtsklick · B zurück', W / 2, 790, 20, DIM, 1)
        self.body(p, 'Im Spiel: A Angriff · B nehmen, halten: Ring · X/Y/R3 F1–F3 · LT/RT Tränke · Start Menü', W / 2, 825, 20, DIM, 1)
        armed = time.monotonic() - self.armed < 3

        def quit_():
            if time.monotonic() - self.armed < 3: self.w.post('api/quit')
            else: self.armed = time.monotonic()
        self.button(p, QRectF(W / 2 - 200, 900, 400, 90), 'NOCHMAL = BEENDEN' if armed else 'BEENDEN', True, quit_)
        if time.monotonic() < self.note_until: self.body(p, self.note, W / 2, 1030, 20, GOLD, 1)

    def header(self, p, s, st):
        self.panel(p, 16, 16, 1224, 100)
        info = self.info if self.fresh(self.info_at, 3) else None
        cls = CLASSES[s['cls']] if 0 <= s['cls'] < len(CLASSES) else ''
        v = st['v']
        self.title(p, (info and info['name']) or '?', 40, 62, 40, GOLD)
        self.body(p, f'{cls} · Stufe {v.get(12, 0)}' + (f' · {DIFFICULTY[st["difficulty"]]}' if st['difficulty'] < 3 else ''), 40, 90, 22, DIM)
        area = self.art.level_name(s['level']) if self.art else None
        act = act_of(s['level'])
        self.title(p, area or f'Gebiet {s["level"]}', 1200, 62, 34, GOLD, 2)
        self.body(p, (f'Akt {act}' if act else '') + (' · Stadt' if s['town'] else '') + f' · Gold {fmt(v.get(14, 0))} · Truhe {fmt(v.get(15, 0))}', 1200, 90, 22, DIM, 2)

    def orbs(self, p, st):
        self.panel(p, 16, 108, 600, 400)
        v = st['v']
        life, top, mana, mtop = v.get(6, 0) >> 8, v.get(7, 0) >> 8, v.get(8, 0) >> 8, v.get(9, 0) >> 8
        size = 150
        self.orb(p, True, 40, 124, size, life * 100 // top if top else 0)
        self.orb(p, False, 576 - size, 124, size, mana * 100 // mtop if mtop else 0)
        self.body(p, f'{life} / {top}', 40 + size / 2, 304, 24, TEXT, 1)
        self.body(p, f'{mana} / {mtop}', 576 - size / 2, 304, 24, TEXT, 1)
        self.body(p, 'Leben', 40 + size / 2, 330, 20, RED, 1)
        self.body(p, 'Mana', 576 - size / 2, 330, 20, 0xFF6080E0, 1)
        mx, mw = 210, 196
        self.body(p, 'Erfahrung', mx + mw / 2, 160, 20, DIM, 1)
        info = self.info if self.fresh(self.info_at, 3) else None
        xp, share, xp_text = info and info['xp'], 0, fmt(v.get(13, 0))
        if xp and xp[2] > xp[1]:
            share = (xp[0] - xp[1]) / (xp[2] - xp[1])
            xp_text = f'{round(share * 100)} %'
        self.bar(p, mx, 172, mw, share, XP)
        self.body(p, xp_text, mx + mw / 2, 222, 22, TEXT, 1)
        if st['merc']:
            self.body(p, f'Söldner {st["merc_level"]}', mx + mw / 2, 264, 20, DIM, 1)
            self.bar(p, mx, 276, mw, st['merc_life'] / st['merc_max'] if st['merc_max'] else 0, MERC)
            self.body(p, f'{st["merc_life"] >> 8} / {st["merc_max"] >> 8}', mx + mw / 2, 326, 20, TEXT, 1)
        else: self.body(p, 'kein Söldner', mx + mw / 2, 290, 20, DIM, 1)
        a, b = v.get(4, 0), v.get(5, 0)
        if a or b: self.body(p, (f'Attributpunkte {a}' if a else '') + (' · ' if a and b else '') + (f'Fertigkeitspunkte {b}' if b else ''), 308, 380, 22, GOLD, 1)

    def orb(self, p, life, x, y, size, percent):
        if self.art:
            img, glass = self.art.orbs[0 if life else 1], self.art.glass[0 if life else 1]
            k = size / img.width()
            pc = max(0, min(100, percent))
            if pc:
                h = img.height()
                vis = max(1, round(h * pc / 100))
                p.drawImage(QRectF(x, y + (h - vis) * k, img.width() * k, vis * k), img, QRectF(0, h - vis, img.width(), vis))
            gx, gy = (0, 0) if life else (-2, -4)
            p.drawImage(QRectF(x + gx * k, y + gy * k, glass.width() * k, glass.height() * k), glass)
            return
        cx, cy, rad = x + size / 2, y + size / 2, size / 2 - 4  # own look: a glass ball filled from below
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(0xFF0A0808))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.save()
        p.setClipRect(QRectF(x, y + size - 4 - (size - 8) * max(0, min(100, percent)) / 100, size, size))
        g = QRadialGradient(cx - rad / 3, cy - rad / 3, rad * 1.3)
        g.setColorAt(0, color(0xFFE04030 if life else 0xFF4060F0)); g.setColorAt(1, color(0xFF500808 if life else 0xFF080C50))
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.restore()
        p.setPen(QPen(color(EDGE), 4)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), rad, rad)

    def bar(self, p, x, y, w, share, argb):
        p.fillRect(QRectF(x, y, w, 18), color(0xFF0A0807))
        p.fillRect(QRectF(x, y, w * max(0, min(1, share)), 18), color(argb))
        self.stroke(p, QRectF(x, y, w, 18), EDGE, 2)

    def values(self, p, st):
        self.panel(p, 16, 412, 600, 610)
        for i, (name, a, b, c) in enumerate((('Feuer', 39, 40, 0xFFE05030), ('Kälte', 43, 44, 0xFF5090F0), ('Blitz', 41, 42, 0xFFF0E050), ('Gift', 45, 46, 0xFF40C040))):
            x = 36 + i * 140
            p.fillRect(QRectF(x, 430, 128, 78), color(0xFF0A0807))
            self.stroke(p, QRectF(x, 430, 128, 78), c, 2)
            val = resistance(st, a, b)
            self.body(p, name, x + 64, 456, 20, c, 1)
            self.body(p, f'{val}%', x + 64, 498, 30, RED if val < 0 else TEXT, 1)
        v, pts = st['v'], self.points()
        for i, (name, stat) in enumerate((('Stärke', 0), ('Geschick', 2), ('Vitalität', 3), ('Energie', 1))):
            x = 36 + i * 140
            self.body(p, name, x, 540, 20, DIM)
            self.body(p, str(v.get(stat, 0)), x, 574, 28, TEXT)
            if v.get(4, 0) > 0 and self.single() and self.can(pts, KIND_STAT):
                self.button(p, QRectF(x + 76, 540, 52, 44), '+', True, lambda stat=stat: self.send(points_command(KIND_STAT, stat)))
        self.body(p, f'Verteidigung {v.get(31, 0)} · Magiefund {_signed(v.get(80, 0))}%', 36, 598, 20, DIM)

    def skills(self, p, s):
        self.panel(p, 16, 622, 600, 820)
        self.skill(p, s['left'], 'Links', 36, 640)
        self.skill(p, s['right'], 'Rechts', 316, 640)
        for i in range(8):
            sid = s['keys'][i]
            x, y = 36 + (i % 4) * 140, 750 + (i // 4) * 34
            self.body(p, f'F{i + 1} ' + (self.ellipsize(self.skill_name(sid), 104, 18) if sid >= 0 else '–'), x, y, 18, TEXT if sid >= 0 else DIM)

    def skill(self, p, sid, side, x, y):
        r = QRectF(x, y, 64, 64)
        p.fillRect(r, color(0xFF0A0807))
        icon = self.skill_icon(sid)
        if icon: p.drawImage(r, icon)
        self.body(p, side, x + 76, y + 24, 18, DIM)
        self.body(p, self.ellipsize(self.skill_name(sid), 190, 24) if sid >= 0 else '–', x + 76, y + 56, 24, GOLD)

    def effects(self, p):
        self.panel(p, 16, 832, 600, 1064)
        self.body(p, 'Effekte und Auren', 36, 870, 24, GOLD)
        info = self.info if self.fresh(self.info_at, 2.5) else None
        if not info or not info['effects']:
            self.body(p, 'keine', 36, 906, 20, DIM)
            return
        y = 906
        for e in info['effects']:
            if y > 1050: break
            self.body(p, self.ellipsize(self.describe(e), 548, 20), 36, y, 20, TEXT)
            y += 30

    def skill_of_state(self, state):
        for st, skill, _ in HARMS:
            if st == state: return skill
        ss = self.art.state_skills if self.art else None
        if not ss or not 0 <= state < 256: return -1
        return ss[0][state] if ss[0][state] >= 0 else ss[1][state]

    def describe(self, e):
        """D2Effects.describe: what it does, and how long it lasts."""
        state, left, full, pts = e
        info, harm = EFFECT_INFO.get(state), next((t for st, _, t in HARMS if st == state), None)
        if info: what = f'{(self.art and self.art.text(info[0])) or info[0]}: {info[1]}'
        elif harm: what = harm
        else:
            sid = self.skill_of_state(state)
            name = self.art.skill_name[sid] if self.art and 0 <= sid < len(self.art.skill_name) else None
            short = self.art.skill_short[sid] if self.art and 0 <= sid < len(self.art.skill_short) else None
            what = (name or '?') + (f': {short}' if short else '')
        if pts and full > 0: return f'{what} - Schutz noch {round(100 * min(left, full) / full)} % ({left} von {full})'
        if full > 0: return f'{what} - noch {effect_time(left)}' + (' (ein Fluch beendet ihn)' if 128 <= state <= 137 else '')
        if info: return what
        sid = self.skill_of_state(state)
        cls = self.art.skill_class[sid] if self.art and 0 <= sid < len(self.art.skill_class) else -1
        curse = sid in (66, 71, 72, 76, 77, 81, 82, 86, 87, 91)
        aura = sid >= 0 and not harm and not curse and cls == 3
        return f'{what} - ' + ('solange sie wirkt' if aura else 'Restzeit unbekannt')

    def tabs(self, p):
        w = (1224 - 616) / len(TABS)
        for i, name in enumerate(TABS):
            a = QRectF(616 + i * w + (4 if i else 0), 108, w - (4 if i else 0), 64)
            self.panel(p, a.left(), a.top(), a.right(), a.bottom())
            if i == self.tab: p.fillRect(a.adjusted(6, 6, -6, -6), color(0x40C7B377))
            self.body(p, name, a.center().x(), a.center().y() + 8, 20, GOLD if i == self.tab else DIM, 1)
            self.hit(a, lambda i=i: setattr(self, 'tab', i), name=name)  # a taken item stays taken, so it can go to another tab

    def inventory(self, p, area):
        self.panel(p, area.left(), area.top(), area.right(), area.bottom())
        items = self.items[0]
        bottom = self.grid(p, items, INV, self.dim(GRIDS_INV_W, 10), self.dim(GRIDS_INV_H, 4), area.left() + 20, area.top() + 20, area.width() - 40, 58, 420)
        rows = max([1] + [it['x'] // 4 + 1 for it in items if it['page'] == BELT])
        self.body(p, 'Gürtel', area.left() + 20, bottom + 40, 22, GOLD)
        self.belt(p, items, rows, area.left() + 20, bottom + 52, 56)
        self.body(p, 'Angelegt', area.left() + 268, bottom + 40, 22, GOLD)
        y = bottom + 70
        row_h = min(28, (area.bottom() - 56 - y) / 10)
        for loc in range(1, 11):
            it = next((i for i in items if i['page'] == BODY and i['x'] == loc), None)
            a = QRectF(area.left() + 268, y - row_h + 6, area.right() - 16 - area.left() - 268, row_h)
            if it and it['id'] == self.selected: p.fillRect(a, color(0x40C7B377))
            self.body(p, SLOTS[loc], area.left() + 268, y, 18, DIM)
            self.body(p, self.ellipsize(one_line(it), area.width() - 400, 18) if it else '–', area.left() + 368, y, 18, quality_color(it) if it else DIM)
            self.hit(a, lambda it=it, loc=loc: self.hold(it) if it and self.selected is None else self.on_cell(BODY, loc, 0), drop=True, name=f'slot {loc}')
            y += row_h
        self.draw_selected(p, items, area)

    def grid_page(self, p, items, page, gw, gh, area, empty):
        self.panel(p, area.left(), area.top(), area.right(), area.bottom())
        if not any(i['page'] == page for i in items) and self.selected is None:
            return self.body(p, empty, area.left() + 28, area.top() + 56, 24, DIM)
        self.grid(p, items, page, gw, gh, area.left() + 20, area.top() + 20, area.width() - 40, 80, area.height() - 100)
        self.draw_selected(p, items, area)

    def merc(self, p, st, area):
        self.panel(p, area.left(), area.top(), area.right(), area.bottom())
        if not st['merc']: return self.body(p, 'Kein Söldner in der Nähe (oder keiner angeheuert)', area.left() + 28, area.top() + 56, 24, DIM)
        self.body(p, f'Söldner, Stufe {st["merc_level"]}', area.left() + 28, area.top() + 56, 28, GOLD)
        self.body(p, f'Leben {st["merc_life"] >> 8} / {st["merc_max"] >> 8}', area.left() + 28, area.top() + 92, 22, TEXT)
        y, items = area.top() + 140, self.items[1]
        if not items: self.body(p, 'Keine Ausrüstung gesehen', area.left() + 28, y, 22, DIM)
        for it in items:
            img = self.picture(it)
            if img is not None:
                h = 48
                p.drawImage(QRectF(area.left() + 28, y - 36, h * img.width() / img.height(), h), img)
            self.body(p, self.ellipsize(one_line(it), area.width() - 140, 22), area.left() + 100, y, 22, quality_color(it))
            y += 58

    # ---- skills on keys: tap a skill, then a target; the mod sends the game's own packets ---------------------------
    def skill_keys(self, p, s, st, area):
        self.panel(p, area.left(), area.top(), area.right(), area.bottom())
        pts = self.points()
        spend = st['v'].get(5, 0) > 0 and self.single() and self.can(pts, KIND_SKILL)  # a free point: every skill of the class shows
        learnt = [0] + ([pts['first'] + i for i, lv in enumerate(pts['levels']) if lv > 0 or spend] if pts and pts['first'] >= 0 else [])
        self.body(p, '1. Fertigkeit antippen' if self.picked < 0 else f'2. Ziel antippen: {self.skill_name(self.picked)}', area.left() + 24, area.top() + 40, 22, GOLD)
        size, gap, x, y = (44 if spend else 52), 8, area.left() + 24, area.top() + 58
        for sid in learnt:
            passive = self.art is not None and self.art.skill_passive(sid) == 1
            a = QRectF(x, y, size, size)
            p.fillRect(a.adjusted(-4, -4, 4, 4), color(0x80C7B377 if sid == self.picked else 0xFF0A0807))
            icon, level = self.skill_icon(sid), self.level(pts, sid)
            if icon:
                p.setOpacity(90 / 255 if passive or (sid > 0 and level == 0) else 1)
                p.drawImage(a, icon)
                p.setOpacity(1)
            else: self.body(p, self.ellipsize(self.skill_name(sid), size, 14), a.center().x(), a.center().y() + 5, 14, TEXT, 1)
            if level > 0: self.body(p, str(level), a.right() - 2, a.bottom() - 2, 16, TEXT, 2)
            if not passive or spend: self.hit(a, lambda sid=sid: setattr(self, 'picked', -1 if self.picked == sid else sid), name=f'skill {sid}')
            x += size + gap
            if x + size > area.right() - 20: x, y = area.left() + 24, y + size + gap
        ty = max(y + size + 36, area.top() + 200)
        if spend:
            skill, free = self.picked, st['v'].get(5, 0)
            self.button(p, QRectF(area.left() + 24, ty - 24, area.width() - 48, 56),
                        f'Punkt vergeben: {self.ellipsize(self.skill_name(skill), 300, 22)} ({free})' if skill > 0 else f'Fertigkeitspunkte: {free} – Fertigkeit antippen',
                        skill > 0, lambda: self.send(points_command(KIND_SKILL, skill)))
            ty += 68
        self.body(p, 'Maustasten', area.left() + 24, ty, 20, DIM)
        self.target(p, QRectF(area.left() + 24, ty + 12, 272, 64), 'Links (A)', s['left'], lambda: self.send(command(CMD_SELECT_SKILL, struct.pack('<BH', 0, self.picked))))
        self.target(p, QRectF(area.left() + 312, ty + 12, area.width() - 336, 64), 'Rechts', s['right'], lambda: self.send(command(CMD_SELECT_SKILL, struct.pack('<BH', 1, self.picked))))
        ty += 108
        self.body(p, 'Fertigkeitstasten (Pad)', area.left() + 24, ty, 20, DIM)
        keys = self.can(pts, KIND_KEY)
        for i in range(8):
            cx, cy = area.left() + 24 + (i % 2) * 288, ty + 10 + (i // 2) * 62
            self.target(p, QRectF(cx, cy, 272, 56), f'F{i + 1} {KEY_PAD[i]}', s['keys'][i],
                        (lambda i=i: self.send(points_command(KIND_KEY, self.picked, i, True))) if keys else None)

    @staticmethod
    def level(pts, sid):
        i = sid - pts['first'] if pts and pts['first'] >= 0 else -1
        return pts['levels'][i] if sid > 0 and 0 <= i < len(pts['levels']) else 0

    def target(self, p, a, label, current, assign):
        self.panel(p, a.left(), a.top(), a.right(), a.bottom())
        ic = QRectF(a.left() + 8, a.top() + 8, a.height() - 16, a.height() - 16)
        icon = self.skill_icon(current)
        if icon: p.drawImage(ic, icon)
        self.body(p, label, ic.right() + 10, a.top() + 26, 16, DIM)
        self.body(p, self.ellipsize(self.skill_name(current), a.right() - ic.right() - 20, 20) if current >= 0 else '–', ic.right() + 10, a.top() + 52, 20,
                  GOLD if self.picked >= 0 and assign else TEXT)
        if not assign: return

        def tap():
            if self.picked < 0: return
            if self.state and self.state['paused']: return self.say(PAUSED_NOTE)  # the mod takes no commands while paused
            assign()
            self.say(f'Gelegt: {self.skill_name(self.picked)} → {label}')
            self.picked = -1
        self.hit(a, tap, name=label)

    # ---- waypoints: while the game's waypoint menu is open its list shows here; a tap travels ----------------------
    def waypoints(self, p, s, st, area):
        self.panel(p, area.left(), area.top(), area.right(), area.bottom())
        act = self.wp_act or max(1, act_of(s['level']))
        w = (area.width() - 40 - 4 * 8) / 5
        for a in range(1, 6):
            x = area.left() + 20 + (a - 1) * (w + 8)
            self.button(p, QRectF(x, area.top() + 20, w, 64), f'Akt {a}', True, lambda a=a: setattr(self, 'wp_act', a))
            if a == act: p.fillRect(QRectF(x + 6, area.top() + 26, w - 12, 52), color(0x40C7B377))
        single = self.single()
        first, count, y = 30 if act == 5 else (act - 1) * 9, 3 if act == 4 else 9, area.top() + 100
        for i in range(first, first + count):
            level = WAYPOINT_LEVELS[i]
            active, here = st['waypoints'][i >> 3] >> (i & 7) & 1, level == s['level']
            name = self.art.level_name(level) if self.art else None
            a = QRectF(area.left() + 20, y, area.width() - 40, 58)
            p.fillRect(a, color(0x40C7B377 if here else 0xFF0A0807))
            self.stroke(p, a, 0xFF2A2318, 1)
            self.body(p, (name or f'Gebiet {level}') + (' · hier' if here else ''), a.left() + 20, a.center().y() + 9, 24, GOLD if here else TEXT if active else 0xFF5A5448)
            if active and not here and single:
                self.hit(a, lambda level=level: (self.send(deck_item(DI_WAYPOINT, 0, level)), self.say('Reise …')), name=f'wp {level}')
            y += 66

    # ---- Thor D2's recipe book (D2RezeptBuch, the cube's part): categories, a page of recipes, turn the pages
    def recipe_book(self, p, area):
        from decks.d2recipes import CATEGORIES, READY, ALMOST, ingredients, status
        self.panel(p, area.left(), area.top(), area.right(), area.bottom())
        cat, page, want = self.book
        w = (area.width() - 24) / len(CATEGORIES)
        for i, name in enumerate(CATEGORIES):
            a = QRectF(area.left() + 12 + i * w, area.top() + 12, w - 4, 52)
            if i == cat: p.fillRect(a, color(0x40C7B377))
            self.stroke(p, a, EDGE, 2)
            self.body(p, name, a.center().x(), a.center().y() + 8, 18, GOLD if i == cat else DIM, 1)
            self.hit(a, lambda i=i: setattr(self, 'book', [i, 0, self.book[2]]), name=name)
        # D2RezeptBuch's filters: all, ready with what is carried (inventory, cube, stash), one kind missing
        carried = [it for it in self.items[0] if it['page'] in (INV, CUBE, STASH)]
        entries = [e for e in self.recipes['entries'] if e['cat'] == cat]
        states = [status(e, carried, self.recipes['items']) for e in entries]
        counts = (len(entries), states.count(READY), states.count(ALMOST))
        for i, label in enumerate(('Alle', 'Bereit', 'Fast')):
            a = QRectF(area.left() + 12 + i * 196, area.top() + 70, 188, 44)
            if i == want: p.fillRect(a, color(0x40C7B377))
            self.stroke(p, a, EDGE, 2)
            self.body(p, f'{label} {counts[i]}', a.center().x(), a.center().y() + 7, 18, GOLD if i == want else DIM, 1)
            self.hit(a, lambda i=i: setattr(self, 'book', [self.book[0], 0, i]), name=label)
        shown = [e for e, st in zip(entries, states) if want == 0 or st == (READY if want == 1 else ALMOST)]
        per = 5
        pages = max(1, (len(shown) + per - 1) // per)
        page = self.book[1] = min(page, pages - 1)
        y = area.top() + 124
        for e in shown[page * per:page * per + per]:
            line = e['name'] + (f" · {e['info']}" if e['info'] and e['cat'] == 5 else '')
            self.body(p, self.ellipsize(line, area.width() - 40, 24), area.left() + 20, y + 26, 24, e['colour'])
            self.wrap(p, ingredients(e), QRectF(area.left() + 14, y + 34, area.width() - 28, 52), 18, DIM)
            y += 94
        if not shown: self.body(p, 'Nichts davon trägst du gerade bei dir' if want else 'Keine Rezepte', area.center().x(), y + 60, 20, DIM, 1)
        for label, step, x in (('<', -1, area.left() + 20), ('>', 1, area.right() - 110)):
            r = QRectF(x, area.bottom() - 62, 90, 50)
            self.button(p, r, label, pages > 1, lambda step=step: self.book.__setitem__(1, (self.book[1] + step) % pages))
        self.body(p, f'Seite {page + 1}/{pages} · {len(shown)} Rezepte', area.center().x(), area.bottom() - 28, 20, DIM, 1)

    def quest_name(self, act, q):
        n = self.art.text(f'qstsa{act + 1}q{q + 1}') if self.art else None
        return n.replace('\n', ' ') if n else QUESTS_EN[act][q]

    def quest_page(self, p, s, area):
        self.panel(p, area.left(), area.top(), area.right(), area.bottom())
        words, act, y, hint = self.quest_words(), max(1, act_of(s['level'])), area.top() + 52, None
        for a in range(5):
            current = a + 1 == act
            self.body(p, f'Akt {a + 1}', area.left() + 28, y, 28 if current else 22, GOLD if current else DIM)
            done = 0
            for q in range(len(QUESTS_EN[a])):
                w = QUEST_FIRST_WORD[a] + q
                v = words[w] if words is not None and w < len(words) else -1
                finished = v >= 0 and v & 1
                done += bool(finished)
                state = '?' if v < 0 else 'erledigt' if finished else 'Belohnung' if v & 2 else 'begonnen' if v & 4 else '·'
                if current:
                    y += 34
                    self.body(p, self.ellipsize(self.quest_name(a, q), area.width() - 200, 22), area.left() + 52, y, 22, DIM if finished else TEXT)
                    self.body(p, state, area.right() - 28, y, 22, MERC if finished else GOLD, 2)
                if hint is None and v >= 0 and not finished and a + 1 >= act: hint = self.quest_name(a, q) + ('' if state == '·' else f' ({state})')
            if not current: self.body(p, f'{done} / {len(QUESTS_EN[a])}' if words is not None else '?', area.right() - 28, y, 22, DIM, 2)
            y += 44
        self.body(p, 'Queststand noch unbekannt' if words is None else f'Als Nächstes: {hint}' if hint else 'Alle Quests dieses Akts erledigt',
                  area.left() + 28, area.bottom() - 28, 22, GOLD)

    # ---- the action bar --------------------------------------------------------------------------------------------
    def actions(self, p, st):
        self.panel(p, 616, 912, 1224, 1064)
        single, now = self.single(), time.monotonic()
        noted = self.note if now < self.note_until else None
        held = self.held() if single else None
        if held:
            self.item_actions(p, held)
            return self.body(p, self.ellipsize(noted or 'Aufgenommen – Ziel antippen', 568, 20), 636, 1040, 20, GOLD)
        locked = 'Mehrspieler/Battle.net: Deck-Aktionen gesperrt'
        if self.tab == TAB_CUBE:
            opened = self.is_open(UI_CUBE)
            self.button(p, QRectF(636, 930, 200, 72), 'Würfel öffnen', single and not opened, lambda: (self.send(command(CMD_CUBE_OPEN, bytes(4))), self.say('Öffne den Würfel')))
            self.button(p, QRectF(844, 930, 200, 72), 'Transmutieren', single and opened, lambda: (self.send(command(CMD_TRANSMUTE, bytes(4))), self.say('Transmutiere')))
            self.button(p, QRectF(1052, 930, 152, 72), 'Würfel' if self.book else 'Rezepte', bool(self.recipes),
                        lambda: setattr(self, 'book', None if self.book else [0, 0, 0]))
            status = locked if not single else noted or ('Gegenstand antippen, dann Würfelfeld; Transmutieren' if opened else 'Würfel öffnen, um ihn zu füllen')
            return self.body(p, self.ellipsize(status, 568, 20), 636, 1040, 20, DIM)
        pts = self.points()
        sorting = pts is not None and pts['sort_state'] == SORT_RUNNING and now - self.sort_sent < 90
        stash_open, shop_open = self.is_open(UI_STASH), self.is_open(UI_NPCSHOP)

        def sort(data):
            self.send(data)
            self.sort_sent = time.monotonic()
            self.say('Sortieren: Das Spiel legt die Gegenstände einzeln um')
        v = st['v']
        if self.tab == TAB_STASH:
            self.button(p, QRectF(636, 930, 184, 72), 'Sortiere …' if sorting else 'Sortieren', single and stash_open and not sorting, lambda: sort(command(CMD_SORT, b'\4\0')))
            self.button(p, QRectF(832, 930, 180, 72), 'Gold rein', single and stash_open and v.get(14, 0) > 0,
                        lambda: (self.send(deck_item(DI_GOLD, 0, 0)), self.say('Gold geht in die Truhe')))
            self.button(p, QRectF(1024, 930, 180, 72), 'Gold raus', single and stash_open and v.get(15, 0) > 0,
                        lambda: (self.send(deck_item(DI_GOLD, 0, 1)), self.say('Gold kommt aus der Truhe')))
        else: self.button(p, QRectF(636, 930, 268, 72), 'Sortiere …' if sorting else 'Inventar sortieren', single and not sorting, lambda: sort(command(CMD_SORT, b'\0\0')))
        if self.tab != TAB_STASH and shop_open:
            # junk: plain weapons and armour (white or grey), without sockets, not ethereal; asks once before it sells
            junk = [it['id'] for it in self.items[0] if it['page'] == INV and it['flags'] & 16 and it['q'] < 4 and not it['flags'] & 3]
            armed = now < self.junk_armed

            def sell():
                if time.monotonic() >= self.junk_armed:
                    self.junk_armed = time.monotonic() + 4
                    return self.say('Einfache Waffen und Rüstungen ohne Sockel – nochmal tippen')
                self.junk_armed = 0
                ids = junk[:48]
                self.send(command(CMD_SELL_JOB, struct.pack('<BBBBII', len(ids), 0, 0, 0, 0, int(time.monotonic() * 1000) & 0x7FFFFFFF) + struct.pack(f'<{len(ids)}I', *ids)))
                self.say(f'Verkaufe {len(ids)} Gegenstände')
            self.button(p, QRectF(916, 930, 288, 72), f'Wirklich {len(junk)} verkaufen?' if armed else f'Ramsch verkaufen ({len(junk)})', single and bool(junk), sell)
        elif self.tab != TAB_STASH:
            self.button(p, QRectF(916, 930, 144, 72), 'Portal', single, lambda: self.send(command(CMD_PORTAL, b'\0')))
            self.button(p, QRectF(1072, 930, 132, 72), 'Trank', single, lambda: self.send(command(CMD_DRINK, b'\0\0')))
        if not single: status = locked
        elif noted: status = noted
        elif pts and pts['sort_counter'] > 0: status = sort_text(pts['sort_state'], pts['sort_moves'])
        else: status = 'Ziehen oder antippen und Ziel antippen; Doppeltipp lagert um'
        self.body(p, self.ellipsize(status, 568, 20), 636, 1040, 20, DIM)

    def item_actions(self, p, it):
        inv, b = it['page'] == INV, []
        if usable(it) and (inv or it['page'] == BELT): b.append(('Benutzen', lambda: self.send(deck_item(DI_USE, it['id']))))
        if inv and beltable(it):
            def to_belt():
                used = {o['x'] for o in self.items[0] if o['page'] == BELT}
                slot = next((i for i in range(4) if i not in used), None)  # the first free place of the bottom row
                if slot is None: self.say('Die Gürtelreihe ist voll')
                else: self.send(deck_item(DI_MOVE, it['id'], DI_TO_BELT, slot))
            b.append(('In Gürtel', to_belt))
        scroll = next((i for i in self.items[0] if (i['code'] == 'isc' or (i['code'] == 'ibk' and i['n'] > 0)) and i['page'] in (INV, BELT)), None)
        if not identified(it) and it['q'] >= 4 and scroll: b.append(('Identifiz.', lambda: self.send(deck_item(DI_IDENTIFY, it['id'], other=scroll['id']))))
        if inv and self.is_open(UI_NPCSHOP): b.append(('Verkaufen', lambda: self.send(deck_item(DI_SELL, it['id']))))
        b.append(('Wegwerfen', lambda: self.send(deck_item(DI_MOVE, it['id'], DI_TO_GROUND))))
        b.append(('Abbrechen', lambda: None))
        w, x = (568 - (len(b) - 1) * 8) / len(b), 636
        for label, fn in b:
            def run(fn=fn):
                if self.state and self.state['paused']: return self.say(PAUSED_NOTE)
                fn()
                self.selected = None
            self.button(p, QRectF(x, 930, w, 72), label, True, run)
            x += w + 8

    def draw_selected(self, p, items, area):
        it = next((i for i in items if i['id'] == self.selected), None)
        if not it: return
        line = one_line(it) + (' · ätherisch' if it['flags'] & 1 else '') + (' · nicht identifiziert' if not identified(it) and it['q'] >= 4 else '')
        p.fillRect(QRectF(area.left() + 8, area.bottom() - 50, area.width() - 16, 42), color(0xE0000000))
        self.body(p, self.ellipsize(line, area.width() - 40, 22), area.left() + 20, area.bottom() - 20, 22, quality_color(it))

    # ---- grids and items ---------------------------------------------------------------------------------------------
    def grid(self, p, items, page, cols, rows, x0, y0, max_w, max_cell, max_h):
        on = [i for i in items if i['page'] == page]
        cols, rows = max([cols] + [i['x'] + i['w'] for i in on]), max([rows] + [i['y'] + i['h'] for i in on])
        cell = min(max_cell, max_w / cols, max_h / rows)
        for y in range(rows):
            for x in range(cols):
                r = QRectF(x0 + x * cell + 1, y0 + y * cell + 1, cell - 2, cell - 2)
                p.fillRect(r, color(0xFF0A0807))
                self.stroke(p, r, 0xFF2A2318, 1)
                self.hit(r, lambda x=x, y=y: self.on_cell(page, x, y), drop=True, name=f'cell {page} {x} {y}')
        for it in on: self.tile(p, it, QRectF(x0 + it['x'] * cell + 1, y0 + it['y'] * cell + 1, it['w'] * cell - 2, it['h'] * cell - 2), cell)
        return y0 + rows * cell

    def belt(self, p, items, rows, x0, y0, cell):
        for y in range(rows):
            for x in range(4):
                r = QRectF(x0 + x * cell + 1, y0 + y * cell + 1, cell - 2, cell - 2)
                p.fillRect(r, color(0xFF0A0807))
                self.stroke(p, r, 0xFF2A2318, 1)
                slot = (rows - 1 - y) * 4 + x
                self.hit(r, lambda slot=slot: self.on_cell(BELT, slot, 0), drop=True, name=f'belt {slot}')
        for it in (i for i in items if i['page'] == BELT):
            top = y0 + (rows - 1 - it['x'] // 4) * cell  # row 0 is the bottom row of the belt, as in the game
            self.tile(p, it, QRectF(x0 + it['x'] % 4 * cell + 1, top + 1, cell - 2, cell - 2), cell)

    def tile(self, p, it, a, cell):
        c = quality_color(it)
        # like the game: a tinted cell behind the item, red-ish when unidentified
        tint = 0x50A02020 if not identified(it) and it['q'] >= 4 else (c & 0xFFFFFF) | 0x28000000
        p.fillRect(a, color(0x70C7B377 if it['id'] == self.selected else tint))
        img = self.picture(it)
        if img is not None:
            k = min(a.width() / img.width(), a.height() / img.height())
            w, h = img.width() * k, img.height() * k
            p.drawImage(QRectF(a.center().x() - w / 2, a.center().y() - h / 2, w, h), img)
        else:
            self.stroke(p, a, c, 1.5)
            name = one_line(it)
            self.wrap(p, max(name.split(' '), key=len) if it['w'] == 1 and it['h'] == 1 else name, a, max(12, min(17, cell * .3)), c)
        if it['n'] > 1 and it['w'] * it['h'] <= 2: self.body(p, str(it['n']), a.right() - 3, a.bottom() - 3, 16, TEXT, 2)

        def tap():
            now = time.monotonic()
            if self.last_tap[0] == it['id'] and now - self.last_tap[1] < .45:
                self.last_tap = (None, 0.0)
                return self.quick_move(it)
            self.last_tap = (it['id'], now)
            if self.selected == it['id']: self.selected = None
            else: self.hold(it)
        self.hit(a, tap, item=it, name=f'item {it["id"]}')

    def wrap(self, p, s, a, size, c):
        max_w, lines, line = a.width() - 6, [], ''
        for word in s.split(' '):
            nxt = f'{line} {word}' if line else word
            if self.width(nxt, size) <= max_w or not line: line = nxt
            else: lines.append(line); line = word
        if line: lines.append(line)
        n = min(max(1, int((a.height() - 4) / (size * 1.1))), len(lines))
        y = a.center().y() - (n - 1) * size * .55 + size * .4
        for i in range(n): self.body(p, self.ellipsize(lines[i], max_w, size), a.center().x(), y + i * size * 1.1, size, c, 1)

    # ---- items by touch: tap = take, tap a cell = put it there; the action bar offers the right-click jobs ---------
    def hold(self, it):
        self.selected = it['id']
        self.say(f'Aufgenommen: {one_line(it)} – Ziel antippen')

    def held(self):
        return next((i for i in self.items[0] if i['id'] == self.selected), None) if self.selected is not None else None

    def quick_move(self, it):
        """Double tap: over to the open stash or cube and back, a potion into the belt, a worn item into the inventory."""
        to = INV if it['page'] != INV else STASH if self.is_open(UI_STASH) else CUBE if self.is_open(UI_CUBE) else BELT if beltable(it) else -1
        self.selected = None
        if to < 0: return self.say('Doppeltipp lagert um: erst Truhe oder Würfel öffnen')
        if to == BELT:
            used = {o['x'] for o in self.items[0] if o['page'] == BELT}
            spot = next(((i, 0) for i in range(4) if i not in used), None)
        else:
            gw, w0, gh, h0 = {INV: (GRIDS_INV_W, 10, GRIDS_INV_H, 4), STASH: (GRIDS_STASH_W, 6, GRIDS_STASH_H, 8), CUBE: (GRIDS_CUBE_W, 3, GRIDS_CUBE_H, 4)}[to]
            spot = free_spot(self.items[0], to, self.dim(gw, w0), self.dim(gh, h0), it['w'], it['h'])
        if spot is None: return self.say('Dort ist kein Platz')
        self.selected = it['id']
        self.on_cell(to, *spot)
        self.selected = None

    def on_cell(self, page, x, y):
        it = self.held()
        if not it: return
        if it['page'] == page and it['x'] == x and it['y'] == y:
            self.selected = None
            return
        if self.state and self.state['paused']: return self.say(PAUSED_NOTE)
        to = {STASH: DI_TO_STASH, CUBE: DI_TO_CUBE, BELT: DI_TO_BELT, BODY: DI_TO_BODY}.get(page, DI_TO_INV)
        if (to == DI_TO_STASH or it['page'] == STASH) and not self.is_open(UI_STASH): return self.say('Erst im Spiel die Truhe öffnen')
        if (to == DI_TO_CUBE or it['page'] == CUBE) and not self.is_open(UI_CUBE): return self.say('Erst im Spiel den Würfel öffnen')
        in_way = sum(1 for o in self.items[0] if o['id'] != it['id'] and o['page'] == page and (
            o['x'] == x if page == BODY else page != BELT and o['x'] < x + it['w'] and x < o['x'] + o['w'] and o['y'] < y + it['h'] and y < o['y'] + o['h']))
        if in_way > 1: return self.say('Dort ist kein Platz')  # one item in the way: the two swap (the game's own swap)
        self.send(deck_item(DI_MOVE, it['id'], to, x, y))
        self.say(('Tausche: ' if in_way == 1 else 'Lege um: ') + one_line(it))
        self.selected = None

    # ---- drag and drop: the same take and put as two taps, in one move ---------------------------------------------
    def touch(self, t, pos):
        if self.xf is None: return
        at = self.xf.inverted()[0].map(pos)
        if t == QEvent.Type.MouseButtonPress: self.down, self.drag = at, None
        elif t == QEvent.Type.MouseMove and self.down is not None:
            if not self.drag and math.hypot(at.x() - self.down.x(), at.y() - self.down.y()) > 18: self.start_drag()
            if self.drag:
                self.drag['x'], self.drag['y'] = at.x(), at.y()
                self.w.update()
        elif t == QEvent.Type.MouseButtonRelease:
            d, self.down, self.drag = self.drag, None, None
            if not d: return
            # drop where the item's top left cell lands; outside a grid (belt, equipped slots) where the finger is
            to = self.hit_at(at.x() - d['gx'] + d['cw'] / 2, at.y() - d['gy'] + d['ch'] / 2) or self.hit_at(at.x(), at.y())
            if to: to()  # no target: the item stays taken, a tap can still place it
            self.w.update()

    def hit_at(self, x, y):
        return next((fn for r, fn, _, drop in reversed(self.hits) if drop and r.contains(QPointF(x, y))), None)

    def start_drag(self):
        h = next(((r, it) for r, _, it, _ in reversed(self.hits) if r.contains(self.down)), None)
        if not h or not h[1]: return
        r, it = h
        self.hold(it)
        self.w.moved = True  # the finger's release is no tap now
        grid = it['page'] != BELT  # belt tiles are one cell whatever the item's size
        self.drag = {'x': self.down.x(), 'y': self.down.y(), 'gx': self.down.x() - r.left(), 'gy': self.down.y() - r.top(), 'w': r.width(), 'h': r.height(),
                     'cw': r.width() / (it['w'] if grid else 1), 'ch': r.height() / (it['h'] if grid else 1)}

    # ---- the pad's window wheel (D2TouchOverlay.drawPadWheel), over the deck while it is open --------------------------
    def draw_wheel(self, p):
        dp, entry = 2.5, self.wheel[1]
        cx, cy = W / 2, H / 2
        ring, r = min(W, H) * .28, 26 * dp
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, 0, 0, 140))
        p.drawEllipse(QPointF(cx, cy), ring + r + 10 * dp, ring + r + 10 * dp)
        for i in range(8):
            a = math.radians(i * 45)
            x, y, on = cx + math.sin(a) * ring, cy - math.cos(a) * ring, i == entry
            p.setPen(QPen(color(GOLD) if on else QColor(90, 74, 48), (3 if on else 1.5) * dp))
            p.setBrush(QColor(40, 32, 18, 230) if on else QColor(12, 10, 8, 200))
            p.drawEllipse(QPointF(x, y), r, r)
            half, icon, img = r * .62, WHEEL_ICONS[i], None
            if self.art: img = self.art.mini[min(len(self.art.mini) - 1, icon + on)] if icon >= 0 else self.art.merc_icon if icon == -1 else self.art.cube_icon if icon == -3 else None
            if img is not None:
                k = min(2 * half / img.width(), 2 * half / img.height())
                p.drawImage(QRectF(x - img.width() * k / 2, y - img.height() * k / 2, img.width() * k, img.height() * k), img)
                if not on: continue
            elif icon == -2:
                c = color(GOLD) if on else QColor(230, 220, 200, 220)
                p.fillRect(QRectF(x - 7 * dp, y - 9 * dp, 4.5 * dp, 18 * dp), c)
                p.fillRect(QRectF(x + 2.5 * dp, y - 9 * dp, 4.5 * dp, 18 * dp), c)
            self.wheel_tab(p, WHEEL[i], x, y + r + 4 * dp, dp)
        self.wheel_tab(p, 'View', cx, cy - 6 * dp, dp)

    # ---- the pad's target ring (D2TouchOverlay.drawRing): Thor D2 draws it over the game, here over the deck
    def draw_ring(self, p):
        dp, (page, pages, places) = 2.5, self.ring
        cx, cy, n = W / 2, H / 2, len(places)
        ring, r = min(W, H) * .3, 22 * dp
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, 0, 0, 150))
        p.drawEllipse(QPointF(cx, cy), ring + r + 30 * dp, ring + r + 30 * dp)
        for i, (what, q, on, label) in enumerate(places):
            a = math.radians(i * 360 / n)
            x, y = cx + math.sin(a) * ring, cy - math.cos(a) * ring
            p.setPen(QPen(color(GOLD) if on else QColor(90, 74, 48), (3 if on else 1.5) * dp))
            p.setBrush(QColor(40, 32, 18, 230) if on else QColor(12, 10, 8, 200))
            p.drawEllipse(QPointF(x, y), r, r)
            if what in (1, 2):  # page turns
                self.plain(p, '›' if what == 1 else '‹', x, y + 9 * dp, 26 * dp, GOLD, 1, True)
                continue
            if what == 0: continue
            c = quality_color({'q': q, 'flags': 0}) if what == 3 else (0xFFE8E2D2 if what == 4 else 0xFFC7B377)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(c))
            p.drawEllipse(QPointF(x, y), 6 * dp, 6 * dp)
            self.wheel_tab(p, label, x, y + r + 4 * dp, dp)
        self.wheel_tab(p, f'Seite {page + 1}/{pages}' if pages > 1 else 'Loslassen: nehmen', cx, cy - 6 * dp, dp)

    def wheel_tab(self, p, text, cx, top, dp):
        small = self.art and self.art.small
        k = 2.0
        w = (small.width(text, small.height) * k if small else self.qfont(10 * dp)[1].horizontalAdvance(text)) + 8 * dp
        h = 12 * k if small else 13 * dp
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(10, 8, 6, 220))
        p.drawRoundedRect(QRectF(cx - w / 2, top, w, h), 3 * dp, 3 * dp)
        if small: small.draw(p, text, cx, top + h / 2 + 7 * k, small.height * k, 0xFFC7B378, 1)  # the game's gold tint (D2Hud.goldText)
        else: self.plain(p, text, cx, top + 10 * dp, 10 * dp, 0xFFFFFFFF, 1, False)


def parse_ring(d):
    """ports/d2's pad.py: b'D2PR' + open, then places, page, pages and per place what, quality, chosen, label."""
    if d[4] == 0 or len(d) < 8: return None
    places, at = [], 8
    try:
        for _ in range(d[5]):
            what, q, on, n = d[at:at + 4]
            places.append((what, q, on != 0, d[at + 4:at + 4 + n].decode('utf-8', 'replace')))
            at += 4 + n
    except ValueError:
        return None
    return d[6], d[7], places


def sort_text(state, moves):
    return {SORT_RUNNING: 'Sortiere …', SORT_DONE: f'Sortiert ({moves} Züge)', SORT_PARTIAL: 'Teilweise sortiert', SORT_CURSOR: 'Abgebrochen: Gegenstand am Mauszeiger',
            SORT_NO_ROOM: 'Kein Platz zum Sortieren'}.get(state, 'Nicht sortiert (Händler/Truhe offen, Monster nah oder Pause)')


def fmt(v): return f'{v:,}'.replace(',', '.')
