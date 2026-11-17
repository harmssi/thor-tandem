"""HEV deck for Half-Life, Opposing Force and Blue Shift on the bottom screen (the native port in ports/halflife).

Native port of the Android deck of "Thor Half-Life" (HevDeck.java): health, armour, suit status and lamp · arsenal
(slot columns, tap = select) or saved games · pickups · hazards and compass · location with a breadcrumb map · buttons.
All data is the snapshot the game's client library sends over the deck socket (decks/portsocket.py); every action goes
back as a console command the library checks against its own list. The layout is drawn on a 1240x1080 grid and scaled.
Unlike the app it does not animate: it repaints when something it shows has changed, to leave the processor to the game.

Interface for tandem_ui (see DECKS there): Deck(window), paint(painter) -> bool, close().
The functions above the class are plain Python (no Qt) and carry the logic worth testing.
"""
import math, os, struct, threading, time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen, QPolygonF

from decks.portsocket import Link

# DMG_* bits from cl_dll/health.h
DMG_BURN, DMG_FREEZE, DMG_SHOCK, DMG_DROWN, DMG_NERVEGAS, DMG_POISON = 1 << 3, 1 << 4, 1 << 8, 1 << 14, 1 << 16, 1 << 17
DMG_RADIATION, DMG_ACID, DMG_SLOWBURN, DMG_SLOWFREEZE = 1 << 18, 1 << 20, 1 << 21, 1 << 22
WEAPONS = {'weapon_crowbar': 'Brechstange', 'weapon_9mmhandgun': '9-mm-Pistole', 'weapon_glock': '9-mm-Pistole', 'weapon_357': '.357 Magnum', 'weapon_python': '.357 Magnum',
           'weapon_9mmAR': 'MP5', 'weapon_mp5': 'MP5', 'weapon_shotgun': 'Schrotflinte', 'weapon_crossbow': 'Armbrust', 'weapon_rpg': 'Raketenwerfer', 'weapon_gauss': 'Tau-Kanone',
           'weapon_egon': 'Gluonenkanone', 'weapon_hornetgun': 'Hivehand', 'weapon_handgrenade': 'Granaten', 'weapon_satchel': 'Rucksackladung', 'weapon_tripmine': 'Laserfalle',
           'weapon_snark': 'Snarks',  # Opposing Force:
           'weapon_pipewrench': 'Rohrzange', 'weapon_knife': 'Kampfmesser', 'weapon_grapple': 'Barnacle', 'weapon_eagle': 'Desert Eagle', 'weapon_m249': 'M249 SAW',
           'weapon_sniperrifle': 'Scharfschützengewehr', 'weapon_displacer': 'Displacer', 'weapon_shockrifle': 'Shock Roach', 'weapon_sporelauncher': 'Sporenwerfer', 'weapon_penguin': 'Pinguine'}
SECONDARY = {'weapon_9mmAR': 'Granaten', 'weapon_mp5': 'Granaten'}
ITEMS = {'item_healthkit': 'Medikit', 'item_battery': 'HEV-Batterie', 'item_longjump': 'Weitsprungmodul', 'item_suit': 'HEV-Anzug', 'item_antidote': 'Gegengift',
         'item_security': 'Sicherheitskarte', 'item_nightvision': 'Nachtsicht', 'dmg_rad': 'Strahlung'}
CHAPTERS = [  # map name prefixes -> the official chapter title
    ('t0a0', 'Hazard Course'), ('c0a0', 'Black Mesa Inbound'), ('c1a0', 'Anomalous Materials'), ('c1a1', 'Unforeseen Consequences'), ('c1a2', 'Office Complex'),
    ('c1a3', '"We\'ve Got Hostiles"'), ('c1a4', 'Blast Pit'), ('c2a1', 'Power Up'), ('c2a2', 'On A Rail'), ('c2a3', 'Apprehension'),
    ('c2a4d c2a4e c2a4f c2a4g', 'Questionable Ethics'), ('c2a4', 'Residue Processing'), ('c2a5', 'Surface Tension'), ('c3a1', '"Forget About Freeman!"'), ('c3a2', 'Lambda Core'),
    ('c4a1a c4a1b c4a1c c4a1d c4a1e c4a1f', 'Interloper'), ('c4a1', 'Xen'), ('c4a2', 'Gonarch\'s Lair'), ('c4a3', 'Nihilanth'), ('c5a1', 'Endgame'),
    ('ofboot', 'Boot Camp'), ('of0a', 'Incoming'), ('of1a1 of1a2 of1a3 of1a4', 'Welcome to Black Mesa'), ('of1a5 of1a6', '"We Are Pulling Out"'),  # Opposing Force
    ('of2a1 of2a2 of2a3', 'Missing in Action'), ('of2a4 of2a5 of2a6', 'Friendly Fire'), ('of3a1 of3a2 of3a3', 'We Are Not Alone'), ('of3a4 of3a5 of3a6', 'Crush Depth'),
    ('of4a1 of4a2 of4a3', 'Vicarious Reality'), ('of4a4 of4a5', 'Pit Worm\'s Nest'), ('of5a', 'Foxtrot Uniform'), ('of6a4b of6a5', 'Worlds Collide'), ('of6a', '"The Package"'),
    ('of7a', 'Conclusion'),
    ('ba_hazard', 'Hazard Course'), ('ba_tram', 'Living Quarters Outbound'), ('ba_security ba_maint ba_elevator', 'Insecurity'), ('ba_canal', 'Duty Calls'),  # Blue Shift
    ('ba_yard ba_teleport1', 'Captive Freight'), ('ba_xen', 'Focal Point'), ('ba_power', 'Power Struggle'), ('ba_outro', 'A Leap of Faith')]


def pretty(name, prefix):
    rest = name[len(prefix):] if name.startswith(prefix) else name
    return rest.replace('_', ' ').capitalize() or name


def weapon_name(name): return WEAPONS.get(name) or pretty(name, 'weapon_')


def pickup_name(kind, name):
    """A line of the pickup feed: kind 'a' (ammo, named after its weapon; '#2' = the secondary kind), 'w', 'i'."""
    if kind == 'a': return SECONDARY.get(name[:-2]) or weapon_name(name[:-2]) if name.endswith('#2') else weapon_name(name)
    return weapon_name(name) if kind == 'w' else ITEMS.get(name) or pretty(name, 'item_')


def chapter(level, previous=''):
    """The chapter a map belongs to, or None. Blue Shift visits ba_teleport2 twice: from Xen and back from the power plant."""
    m = (level or '').lower()
    if m == 'ba_teleport2': return 'A Leap of Faith' if (previous or '').lower().startswith('ba_power') else 'Focal Point'
    for prefixes, title in CHAPTERS:
        for prefix in prefixes.split():
            exact = len(prefix) == 5 and prefix[0] == 'c'  # Half-Life: five letters are a whole map name (c2a4 next to c2a4d)
            if m and (m == prefix if exact else m.startswith(prefix)): return title
    return None


def save_map(data):
    """The map a saved game is on: 'mapName' of its GameHeader block (layout as in the engine's SV_GetSaveComment), or ''."""
    try:
        magic, _, _, count, size = struct.unpack_from('<5i', data, 0)
        if magic != 0x5641534A or not 0 <= count <= 0x10000 or not 0 <= size <= 0x400000: return ''  # "JSAV"
        tokens, p = [], 20
        for _ in range(count):
            end = data.index(b'\0', p)
            tokens.append(data[p:end].decode('latin-1')); p = end + 1
        block, name = struct.unpack_from('<hh', data, p)
        if tokens[name] != 'GameHeader': return ''
        fields = data[p + 4]
        p += 4 + block
        for _ in range(fields):
            size, name = struct.unpack_from('<hh', data, p)
            if tokens[name] == 'mapName': return data[p + 4:p + 4 + size].split(b'\0')[0].decode('latin-1')
            p += 4 + size
    except (struct.error, ValueError, IndexError): pass
    return ''


def sprite_entry(text, exists):
    """The line of a sprites/weapon_x.txt that names the weapon's silhouette: (sheet, x, y, w, h) or None. A sprite of its
    own for 1280 is best, then the 640 sheet; exists(sheet) says whether that sprite file is there."""
    best, score = None, -1
    for line in text.split('\n'):
        t = line.split()
        if len(t) < 7 or t[0] != 'weapon' or not all(v.isdigit() for v in [t[1]] + t[3:7]): continue
        rank = {'1280': 3, '640': 2, '2560': 1}.get(t[1], 0)
        if rank > score and exists(t[2]): best, score = (t[2], *map(int, t[3:7])), rank
    return best


def sprite_mask(data, rx, ry, rw, rh):
    """Frame 0 of a GoldSrc sprite (IDSP v2), cut to a rectangle: (w, h, one byte of coverage per pixel) or None."""
    try:
        magic, version, _, fmt, _, _, _, frames, _, _, colours = struct.unpack_from('<4if2iifiH', data, 0)
        pal = data[42:42 + colours * 3]
        group, _, _, fw, fh = struct.unpack_from('<5i', data, 42 + colours * 3)
    except struct.error: return None
    if magic != 0x50534449 or version != 2 or frames < 1 or group: return None
    px = data[62 + colours * 3:62 + colours * 3 + fw * fh]
    rw, rh = min(rw, fw - rx), min(rh, fh - ry)
    if rw <= 0 or rh <= 0 or len(px) < fw * fh or len(pal) < colours * 3: return None
    lum = [max(pal[i * 3:i * 3 + 3]) for i in range(colours)] + [0] * (256 - colours)  # brightness = coverage
    if fmt == 2: lum = list(range(256))  # the index is the alpha
    if fmt == 3: lum[255] = 0  # index 255 is see-through
    rows = [px[(ry + y) * fw + rx:(ry + y) * fw + rx + rw] for y in range(rh)]
    # A rectangle without a bright pixel is no icon (Opposing Force's weapon_penguin.txt points at an empty stripe).
    if max(lum[i] for row in rows for i in row) < 120: return None
    # HUD sheets have a dim background that is not black: cut it off and stretch the rest
    return rw, rh, b''.join(row.translate(bytes(max(0, min(255, (v - 48) * 255 // 160)) for v in lum)) for row in rows)


def hazards(d):
    """What threatens the player right now: [(label, colour name)]."""
    dmg, geiger, out = d.get('dmg', 0), d.get('geiger', 0), []
    if dmg & DMG_RADIATION or 0 < geiger < 1000: out.append(('Strahlung', 'amber'))
    if dmg & (DMG_BURN | DMG_SLOWBURN): out.append(('Feuer', 'red'))
    if dmg & DMG_SHOCK: out.append(('Strom', 'teal2'))
    if dmg & (DMG_POISON | DMG_NERVEGAS): out.append(('Gift', 'green'))
    if dmg & DMG_ACID: out.append(('Säure', 'green'))
    if dmg & (DMG_FREEZE | DMG_SLOWFREEZE): out.append(('Kälte', 'teal2'))
    if dmg & DMG_DROWN: out.append(('Ertrinken', 'red'))
    if not d.get('ground', 1) and d.get('fallv', 0) > 580: out.append(('Sturz', 'red' if d['fallv'] > 1024 else 'amber'))
    if d.get('train'): out.append(('Zugsteuerung', 'text2'))
    return out


def status(d, ingame, paused):
    """The suit's status chip: (label, colour name)."""
    if not ingame: return 'Bereitschaft', 'text3'
    if d.get('dead'): return 'Nulllinie', 'red'
    if paused: return 'Pausiert', 'teal'
    if not d.get('suit'): return 'Kein Anzug', 'text2'
    if d.get('hp', 0) <= 25: return 'Kritisch', 'red'
    if d.get('hp', 0) <= 50 or d.get('dmg'): return 'Warnung', 'amber'
    return 'Normal', 'green'


def visible(d):
    """What of a snapshot shows on the deck. The game sends twenty a second; a repaint is due only when this changes."""
    pos = d.get('pos') or [0, 0]
    return (d.get('map'), d.get('hp'), d.get('ap'), d.get('suit'), d.get('dead'), d.get('fl'), d.get('flbat'), d.get('dmg'), d.get('geiger', 0) // 50, d.get('train'),
            d.get('water'), round(d.get('air', -1)), d.get('ground'), d.get('fallv', 0) > 580, d.get('fallv', 0) > 1024, round(d.get('speed', 0) / 20),
            round(d.get('yaw', 0) / 3), round(pos[0] / 24), round(pos[1] / 24), d.get('cur'), d.get('sel'), str(d.get('w')),
            [(f[0], f[3], min(80, f[4]) // 10) for f in d.get('feed') or []], [v > 0 for v in d.get('pain') or []])


def color(rgb, a=1.0): return QColor((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255, round(max(0, min(1, a)) * 255))


# The look of the app ("HEV terminal"): near-black surfaces, quiet panels with thin lines, amber as the suit's colour,
# red for what is critical, teal for neutral news (air, water).
C = {'bg': 0x0A0907, 'bg2': 0x0F0D0A, 'panel': 0x14120E, 'panel2': 0x1B1813, 'line': 0x2A2620, 'line2': 0x3A342B, 'text': 0xF4F1EA, 'text2': 0xADA698, 'text3': 0x6F685C,
     'amber': 0xF5A524, 'amber2': 0xFFCB6B, 'red': 0xE5484D, 'red2': 0xF08A6E, 'green': 0x4CC38A, 'teal': 0x4DB6C4, 'teal2': 0x8FDCE6}
GAMES = {'valve': ('HEV-Panzerung', 'Taschenlampe', 'Lampe', 'HEV-Anzug noch nicht angelegt'), 'gearbox': ('PCV-Panzerung', 'Nachtsicht', 'Nachtsicht', 'PCV noch nicht angelegt'),
         'bshift': ('Panzerung', 'Taschenlampe', 'Lampe', 'Schutzweste noch nicht angelegt')}  # armour, lamp, lamp button, hint without a suit
ARMED = 2.5  # seconds a "tap again" stays open


class Deck:
    def __init__(self, window):
        self.w = window
        self.d, self.hello, self.connected, self.alive = {}, {}, False, True
        self.sig = self.last_t = None
        self.t_changed = self.painted = self.toast_until = self.saves_at = 0.0
        self.tab_saves = False  # the saves tab in place of the arsenal
        self.paused, self.toast, self.armed, self.saves, self.shots, self.icons, self.masks = False, '', (None, 0.0), [], {}, {}, {}
        self.trail, self.trail_map, self.previous_map, self.trail_wait = [], '', '', 0.0
        self.slots, self.rows, self.s, self.ox, self.oy = 5, 4, 1.0, 0.0, 0.0
        self.link = Link((window.RUN.get('port') or {}).get('socket') or '', self.heard)

    def close(self):
        self.alive = False
        self.link.close()

    # ---- the game's data (on the link's thread) ------------------------------------------------------------------------
    def heard(self, d):
        now = time.time()
        if d is None: self.connected, self.d = False, {}
        elif 'v' not in d: self.hello = d  # the launcher's own line: game folder, where the game files and the saves are
        else:
            self.connected = True
            if d.get('t') != self.last_t: self.last_t, self.t_changed = d.get('t'), now
            self.paused = bool(d.get('map')) and now - self.t_changed > .4
            self.track(d, now)
            self.d = d
        if self.tab_saves and now - self.saves_at > 1: self.scan_saves(now)
        sig = (self.connected, visible(self.d), self.paused, len(self.trail), self.tab_saves, [(s[0], s[2]) for s in self.saves], now < self.toast_until, now - self.armed[1] < ARMED)
        if sig != self.sig and now - self.painted >= .1:  # ten pictures a second at most
            self.sig, self.painted = sig, now
            self.changed()

    def track(self, d, now):
        """The breadcrumb trail of the current map: a point every 48 units, a fresh start after a jump."""
        level, pos = d.get('map') or '', (d.get('pos') or [0, 0])[:2]
        if level != self.trail_map:
            if self.trail_map: self.previous_map = self.trail_map
            self.trail_map, self.trail, self.trail_wait = level, [], now + 1.5
        if not level or d.get('dead') or self.paused or now < self.trail_wait: return
        far = math.dist(pos, self.trail[-1]) if self.trail else 1e9
        if far > 2000: self.trail = []  # teleport or level change
        if far > 48: self.trail = self.trail[-1199:] + [pos]  # a new list: the painter reads the old one to its end

    def scan_saves(self, now):
        """The game's saved games, newest first: [(name, map, time, picture or None)]; each file is read once."""
        self.saves_at, folder, found = now, os.path.join(self.hello.get('home') or '', self.hello.get('game') or '', 'save'), []
        try: names = [n for n in os.listdir(folder) if n.lower().endswith('.sav')]
        except OSError: names = []
        for n in names:
            path = os.path.join(folder, n)
            try: key = (path, os.path.getmtime(path))
            except OSError: continue
            if key not in self.shots:
                try:
                    with open(path, 'rb') as f: level = save_map(f.read(0x410000))
                except OSError: level = ''
                shot = QImage(path[:-4] + '.bmp')  # the engine's own picture of the save: its middle, 4:3, small
                if not shot.isNull():
                    w = min(shot.width(), shot.height() * 4 // 3)
                    shot = shot.copy((shot.width() - w) // 2, (shot.height() - w * 3 // 4) // 2, w, w * 3 // 4).scaledToWidth(320, Qt.TransformationMode.SmoothTransformation)
                self.shots[key] = (n[:-4], level, key[1], None if shot.isNull() else shot)
            found.append(self.shots[key])
        self.saves = sorted(found, key=lambda s: -s[2])

    def changed(self):
        if self.alive: self.w.loaded.emit()

    def later(self, secs):  # one more repaint, to take a toast or an open "tap again" away
        timer = threading.Timer(secs, lambda: (setattr(self, 'sig', None), self.changed()))
        timer.daemon = True
        timer.start()

    def say(self, text):
        self.toast, self.toast_until = text, time.time() + 1.6
        self.changed(); self.later(1.7)

    def twice(self, key):
        """True on the second tap on the same thing within ARMED seconds; the first one arms it."""
        now = time.time()
        if self.armed[0] == key and now - self.armed[1] < ARMED:
            self.armed = (None, 0.0)
            return True
        self.armed = (key, now)
        self.changed(); self.later(ARMED + .1)
        return False

    # ---- drawing helpers (y is the text's baseline, as in the app) -----------------------------------------------------
    def R(self, x, y, w, h): return QRectF(self.ox + x * self.s, self.oy + y * self.s, w * self.s, h * self.s)

    def font(self, kind, px, weight=400, spacing=0.0): return self.w.font(kind, round(px * self.s / self.w.u, 3), weight, spacing)

    def width(self, text, f): return self.font(*f)[1].horizontalAdvance(text)

    def fit(self, text, f, room): return self.font(*f)[1].elidedText(text, Qt.TextElideMode.ElideRight, room)

    def txt(self, p, text, x, y, f, col, align=0):
        font, fm = self.font(*f)
        p.setFont(font); p.setPen(col)
        p.drawText(QPointF(x - fm.horizontalAdvance(text) * align / 2, y), text)

    def label(self, p, text, x, y, col=None): self.txt(p, text.upper(), x, y, ('b', 13, 600, .22), col or color(C['text3']))

    def panel(self, p, r, radius, fill, line, width=1.0, dash=False):
        p.setPen(QPen(line, width, Qt.PenStyle.DashLine if dash else Qt.PenStyle.SolidLine) if line is not None else Qt.PenStyle.NoPen)
        p.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), radius * self.s, radius * self.s)

    def bar(self, p, r, fraction, c1, c2):
        """Thin gradient bar: track and fill."""
        rad = r.height() / 2
        self.panel(p, r, rad / self.s, color(C['line']), None)
        fraction = max(0, min(1, fraction))
        if fraction > 0:
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, c1); g.setColorAt(1, c2)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(QRectF(r.left(), r.top(), max(r.height(), r.width() * fraction), r.height()), rad, rad)

    def cells(self, p, r, n, fraction, on, off):
        """The suit's segmented bar: n cells, lit up to the fraction."""
        gap = r.height() * .35
        w, lit = (r.width() - gap * (n - 1)) / n, round(max(0, min(1, fraction)) * n)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            p.setBrush(on if i < lit else off)
            p.drawRoundedRect(QRectF(r.left() + i * (w + gap), r.top(), w, r.height()), 2, 2)

    def icon(self, name, tint):
        """A weapon's silhouette from the player's own HUD sprites (<game>/sprites/weapon_x.txt and the sheets it names;
        the add-ons share weapons with Half-Life), in the wanted colour, or None. Nothing of the game ships with Tandem."""
        if name not in self.masks:
            self.masks[name] = None
            data, game = self.hello.get('data') or '', self.hello.get('game') or 'valve'
            roots = [os.path.join(data, folder, 'sprites') for folder in dict.fromkeys((game + '_hd', game, 'valve_hd', 'valve'))]
            find = lambda rel: next((os.path.join(r, rel) for r in roots if os.path.isfile(os.path.join(r, rel))), None)
            try:
                with open(find(name + '.txt'), encoding='latin-1') as f: entry = sprite_entry(f.read(), lambda sheet: find(sheet + '.spr'))
                with open(find(entry[0] + '.spr'), 'rb') as f: mask = sprite_mask(f.read(), *entry[1:])
                if mask: self.masks[name] = QImage(mask[2], mask[0], mask[1], mask[0], QImage.Format.Format_Alpha8).copy()  # copy: the bytes go
            except (OSError, TypeError): pass  # no such file (find gave None): the tile shows the name alone
        mask = self.masks[name]
        if mask is None: return None
        key = (name, tint.rgba())
        if key not in self.icons:
            img = QImage(mask.size(), QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(tint)
            q = QPainter(img)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            q.drawImage(0, 0, mask); q.end()
            self.icons[key] = img
        return self.icons[key]

    # ---- painting -----------------------------------------------------------------------------------------------------
    def paint(self, p):
        W, H, d = self.w.width(), self.w.height(), self.d
        self.s = s = min(W / 1240, H / 1080)
        self.ox, self.oy = (W - 1240 * s) / 2, (H - 1080 * s) / 2
        self.game = self.hello.get('game') if self.hello.get('game') in GAMES else 'valve'
        self.ingame = ingame = self.connected and bool(d.get('map'))
        self.now = time.time()
        p.fillRect(QRectF(0, 0, W, H), color(C['bg']))
        live = ingame and (d.get('suit') or d.get('dead'))  # dead: the server takes the suit away, show health 0, not dashes
        self.vital(p, self.R(24, 24, 400, 212), 'Gesundheit', max(0, d.get('hp', 0)) if live else None, True)
        self.vital(p, self.R(440, 24, 400, 212), GAMES[self.game][0], d.get('ap', 0) if live else None, False)
        self.suit(p, self.R(856, 24, 360, 212), d)
        self.arsenal(p, self.R(24, 252, 1192, 448), d)
        self.feed(p, self.R(24, 716, 400, 228), d)
        self.hazard(p, self.R(440, 716, 400, 228), d)
        self.location(p, self.R(856, 716, 360, 228), d)
        self.buttons(p, d)
        if self.toast and self.now < self.toast_until:
            f = ('b', 15, 600, .1)
            tw = self.width(self.toast.upper(), f) + 48 * s
            r = QRectF(W / 2 - tw / 2, self.oy + (700 - 64) * s, tw, 44 * s)
            self.panel(p, r, 22, color(C['panel2'], .96), color(C['amber']), 1.5 * s)
            self.txt(p, self.toast.upper(), r.center().x(), r.center().y() + 5 * s, f, color(C['amber2']), 1)
        return True

    def vital(self, p, r, title, value, health):
        s, low = self.s, health and value is not None and value <= 25
        accent, accent2 = (color(C['red']), color(C['red2'])) if low else (color(C['amber']), color(C['amber2']))
        self.panel(p, r, 12, color(C['panel']), color(C['red'], .9) if low else color(C['line']))
        x = r.left() + 24 * s
        self.label(p, title, x, r.top() + 36 * s)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(accent if value is not None else color(C['text3']))
        cx, cy, rr = r.right() - 40 * s, r.top() + 31 * s, 11 * s
        if health:  # a cross …
            t = rr * .36
            p.drawRect(QRectF(cx - t, cy - rr, 2 * t, 2 * rr)); p.drawRect(QRectF(cx - rr, cy - t, 2 * rr, 2 * t))
        else:  # … or a shield
            p.drawPolygon(QPolygonF([QPointF(cx + a * rr, cy + b * rr) for a, b in ((0, -1.05), (1, -.6), (.85, .3), (0, 1.1), (-.85, .3), (-1, -.6))]))
        num, f = '---' if value is None else str(value), ('m', 96, 700)
        self.txt(p, num, x - 4 * s, r.top() + 136 * s, f, color(C['text3']) if value is None else accent)
        self.txt(p, '/100', x + self.width(num, f) + 6 * s, r.top() + 136 * s, ('m', 20), color(C['text3']))
        self.cells(p, QRectF(x, r.bottom() - 50 * s, r.right() - 24 * s - x, 16 * s), 20, (value or 0) / 100, accent2, color(C['line']))
        sub = '' if value is None else ('Kritisch' if low else '') if health else ('Keine Panzerung' if value == 0 else '')
        if sub: self.txt(p, sub.upper(), x, r.bottom() - 14 * s, ('b', 11, 600, .22), color(C['red2'] if health else C['text3']))

    def suit(self, p, r, d):
        s, ingame = self.s, self.ingame
        self.panel(p, r, 12, color(C['panel']), color(C['line']))
        x = r.left() + 24 * s
        self.label(p, 'Anzugstatus', x, r.top() + 36 * s)
        text, col = status(d, ingame, self.paused)
        col, f = color(C[col]), ('b', 14, 600, .22)
        chip = QRectF(x, r.top() + 56 * s, self.width(text.upper(), f) + 44 * s, 38 * s)
        self.panel(p, chip, 19, color(col.rgb() & 0xFFFFFF, .14), color(col.rgb() & 0xFFFFFF, .6))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(col)
        p.drawEllipse(QPointF(chip.left() + 18 * s, chip.center().y()), 5 * s, 5 * s)
        self.txt(p, text.upper(), chip.left() + 32 * s, chip.center().y() + 5 * s, f, col)
        if ingame and not d.get('dead'): self.txt(p, f'{round(d.get("speed", 0))} u/s', r.right() - 24 * s, chip.center().y() + 5 * s, ('m', 15), color(C['text3']), 2)
        fy, on, bat, has = r.top() + 134 * s, bool(d.get('fl')), d.get('flbat', 0), ingame and d.get('suit')
        self.label(p, GAMES[self.game][1], x, fy)
        self.txt(p, 'AN' if on else 'AUS', r.right() - 24 * s, fy, f, color(C['amber2'] if on else C['text3']), 2)
        low = bat <= 20
        self.bar(p, QRectF(x, fy + 20 * s, r.right() - 94 * s - x, 10 * s), bat / 100 if has else 0, color(C['red' if low else 'amber']), color(C['red2' if low else 'amber2']))
        self.txt(p, f'{bat}%' if has else '--', r.right() - 24 * s, fy + 31 * s, ('m', 15), color(C['red2' if low else 'text2']), 2)

    def tabs(self, p, r):
        s, x, f = self.s, r.left() + 24 * self.s, ('b', 13, 600, .22)
        def choose(saves): self.tab_saves, self.saves_at = saves, 0.0
        for i, name in enumerate(('ARSENAL', 'SPIELSTÄNDE')):
            on, w = self.tab_saves == (i == 1), self.width(name, f)
            self.txt(p, name, x, r.top() + 36 * s, f, color(C['amber2'] if on else C['text3']))
            if on: p.fillRect(QRectF(x, r.top() + 44 * s, w, 2 * s), color(C['amber']))
            self.w.hit(QRectF(x - 16 * s, r.top(), w + 32 * s, 56 * s), lambda i=i: choose(i == 1), name=name)
            x += w + 32 * s

    def arsenal(self, p, r, d):
        s, ingame = self.s, self.ingame
        self.panel(p, r, 12, color(C['panel']), color(C['line']))
        self.tabs(p, r)
        if self.tab_saves: return self.saved(p, r, d)
        weapons = d.get('w') or []  # [id, name, slot, pos, clip, ammo1, max1, ammo2, max2, selectable]
        cur = next((w for w in weapons if w[0] == d.get('cur')), None)
        if cur: self.txt(p, weapon_name(cur[1]).upper(), r.right() - 24 * s, r.top() + 36 * s, ('b', 14, 600, .22), color(C['amber2']), 2)
        # columns = the game's weapon slots, rows grow with the fullest slot (Opposing Force: five throwables), never shrink
        self.slots = max(5, min(10, d.get('slots', 5)))
        self.rows = max([self.rows] + [min(6, sum(1 for w in weapons if w[2] == col)) for col in range(self.slots)])
        gap, left, top = 12 * s, r.left() + 16 * s, r.top() + 56 * s
        cw = (r.width() - 32 * s - gap * (self.slots - 1)) / self.slots
        th = (r.bottom() - 16 * s - top - 26 * s - 8 * s * (self.rows - 1)) / self.rows
        for col in range(self.slots):
            cx = left + col * (cw + gap)
            self.txt(p, str(col + 1), cx + 4 * s, top + 14 * s, ('m', 15), color(C['text3']))
            p.fillRect(QRectF(cx + 22 * s, top + 8 * s, cw - 22 * s, 1), color(C['line']))
            mine = [w for w in weapons if w[2] == col][:self.rows]
            for row in range(self.rows):
                box = QRectF(cx, top + 26 * s + row * (th + 8 * s), cw, th)
                if row < len(mine): self.weapon(p, box, mine[row], d)
                else: self.panel(p, box, 8, None, QColor(255, 255, 255, 16))
        if not ingame or not weapons or d.get('dead'):
            msg = ('Starte oder lade ein Spiel auf dem oberen Bildschirm' if not ingame else 'Gestorben – Schnellladen oder Menü' if d.get('dead')
                   else GAMES[self.game][3] if not d.get('suit') else 'Noch keine Waffen')
            f = ('b', 20, 500)
            mw = self.width(msg, f)
            self.panel(p, QRectF(r.center().x() - mw / 2 - 28 * s, r.center().y() - 30 * s, mw + 56 * s, 60 * s), 8, color(C['bg2'], .94), color(C['line2']))
            self.txt(p, msg, r.center().x(), r.center().y() + 7 * s, f, color(C['text2']), 1)

    def weapon(self, p, b, w, d):
        s, (wid, name, _, _, clip, ammo, most, ammo2, _, ok) = self.s, w[:10]
        active, pending = wid == d.get('cur'), wid == d.get('sel') and wid != d.get('cur')
        self.panel(p, b, 8, color(C['amber'], .13) if active else color(C['bg2']), color(C['amber'] if active else C['line']))
        if active:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(C['amber']))
            p.drawRoundedRect(QRectF(b.left(), b.top() + 10 * s, 4 * s, b.height() - 20 * s), 2 * s, 2 * s)
        if pending: self.panel(p, b, 8, None, color(C['amber2']), 1.5 * s, dash=True)
        x = b.left() + 14 * s
        icon = self.icon(name, color(C['amber']) if active else color(C['text2'], .55) if ok else color(C['text3'], .35))
        if icon:
            k = min(b.width() * .5 / icon.width(), (b.height() - 48 * s) / icon.height())
            p.drawImage(QRectF(b.right() - 10 * s - icon.width() * k, b.bottom() - 12 * s - icon.height() * k, icon.width() * k, icon.height() * k), icon)
        f = ('b', 17, 600)
        self.txt(p, self.fit(weapon_name(name), f, b.width() - 28 * s), x, b.top() + 26 * s, f, color(C['text3'] if not ok else C['amber2'] if active else C['text']))
        ay = b.bottom() - 16 * s
        if most == -1 or ammo < 0:
            if not icon: self.txt(p, 'NAHKAMPF', x, ay, ('b', 11, 600, .22), color(C['text3']))
        else:
            big, small = ('m', 24, 700), ('m', 15)
            main = str(clip if clip >= 0 else ammo)
            self.txt(p, main, x, ay, big, color(C['red2'] if max(0, clip) + max(0, ammo) == 0 else C['text'] if active else C['text2']))
            mx = x + self.width(main, big) + 6 * s
            if clip >= 0:
                self.txt(p, f'/ {ammo}', mx, ay, small, color(C['text3']))
                mx += self.width(f'/ {ammo}', small) + 8 * s
            if ammo2 >= 0: self.txt(p, f'+{ammo2}', mx, ay, small, color(C['amber2'] if ammo2 > 0 else C['text3']))
            if most > 0: self.bar(p, QRectF(x, b.bottom() - 8 * s, b.width() - 28 * s, 3 * s), ammo / most, color(C['amber'], .6), color(C['amber2'], .7))
        if not ok: self.txt(p, 'LEER', b.right() - 12 * s, b.top() + 25 * s, ('b', 11, 600, .22), color(C['red2']), 2)
        def select():
            if not self.ingame or self.d.get('dead'): return
            if not ok: return self.say('Leer')
            self.link.send(f'thor_select {wid}')
        self.w.hit(b, select, name=name)

    def saved(self, p, r, d):
        """The saves tab in place of the arsenal: the engine's saved games, tap twice = load; SPEICHERN = "save new"."""
        s, can, f = self.s, self.ingame and not d.get('dead'), ('b', 14, 600, .22)
        new = QRectF(r.right() - 16 * s - self.width('SPEICHERN', f) - 48 * s, r.top() + 12 * s, self.width('SPEICHERN', f) + 48 * s, 40 * s)
        self.panel(p, new, 20, color(C['amber'], .12 if can else .04), color(C['amber'] if can else C['line']))
        self.txt(p, 'SPEICHERN', new.center().x(), new.center().y() + 5 * s, f, color(C['amber2'] if can else C['text3']), 1)
        def save():
            if not can: return
            self.link.send('save new')  # the engine takes the next free saveNNN name, it never overwrites
            self.say('Spiel gespeichert')
            self.saves_at = time.time() - .5  # look again in half a second, when the game has written it
        self.w.hit(new, save, name='SPEICHERN')
        area = QRectF(r.left() + 16 * s, r.top() + 60 * s, r.width() - 32 * s, r.height() - 76 * s)
        if not self.saves: return self.txt(p, 'Noch keine Spielstände', area.center().x(), area.center().y(), ('b', 17), color(C['text3']), 1)
        gap = 12 * s
        cw, ch = (area.width() - gap) / 2, (area.height() - 2 * gap) / 3
        def load(name):
            if self.connected and self.twice(name):
                self.link.send(f'load {name}')
                self.say('Lade Spielstand')
        def cards(y):
            for i, (name, level, when, shot) in enumerate(self.saves):
                b = QRectF(area.left() + (i % 2) * (cw + gap), y + (i // 2) * (ch + gap), cw, ch)
                if b.bottom() < area.top() or b.top() > area.bottom(): continue
                armed = self.armed[0] == name and self.now - self.armed[1] < ARMED
                self.panel(p, b, 8, color(C['amber'], .13) if armed else color(C['bg2']), color(C['amber'] if armed else C['line']))
                th = ch - 16 * s
                dst = QRectF(b.left() + 8 * s, b.top() + 8 * s, th * 4 / 3, th)
                if shot: p.drawImage(dst, shot)
                else: p.fillRect(dst, color(C['panel2']))
                tx, title = dst.right() + 16 * s, ('b', 19, 600)
                self.txt(p, self.fit(chapter(level) or level or name, title, b.right() - 14 * s - tx), tx, b.top() + 34 * s, title, color(C['amber2'] if armed else C['text']))
                self.txt(p, level.upper(), tx, b.top() + 62 * s, ('m', 15), color(C['text3']))
                tag = 'QUICK' if name.lower().startswith('quick') else 'AUTO' if name.lower().startswith('autosave') else name
                self.txt(p, tag, b.right() - 14 * s, b.top() + 62 * s, ('m', 15), color(C['text3'] if tag == name else C['teal2']), 2)
                if armed: self.txt(p, 'NOCHMAL TIPPEN ZUM LADEN', tx, b.bottom() - 16 * s, ('b', 13, 600, .1), color(C['amber2']))
                else: self.txt(p, time.strftime('%d.%m.%Y %H:%M', time.localtime(when)), tx, b.bottom() - 16 * s, ('m', 15), color(C['text2']))
                self.w.hit(b, lambda name=name: load(name), name='save:' + name)
            return y + (len(self.saves) + 1) // 2 * (ch + gap) - gap
        self.w.scroller(p, 'hev-saves', area, cards)

    def feed(self, p, r, d):
        s = self.s
        self.panel(p, r, 12, color(C['panel']), color(C['line']))
        x, feed = r.left() + 24 * s, d.get('feed') or []  # [seq, kind, name, count, age]
        self.label(p, 'Aufgenommen', x, r.top() + 36 * s)
        if not feed or not self.ingame: return self.txt(p, 'Noch nichts aufgenommen', x, r.top() + 80 * s, ('b', 17), color(C['text3']))
        y = r.top() + 58 * s
        for _, kind, name, count, age in feed[:5]:
            a = 1 if age < 20 else max(.35, 1 - (age - 20) / 60)  # older lines fade
            self.label(p, {'a': 'Munition', 'w': 'Waffe'}.get(kind, 'Objekt'), x, y + 20 * s, color(C['amber' if kind == 'w' else 'text2' if kind == 'a' else 'teal'], a))
            f = ('b', 18, 500)
            self.txt(p, self.fit(pickup_name(kind, name), f, r.width() - 200 * s), x + 110 * s, y + 21 * s, f, color(C['text'], a))
            if count > 0: self.txt(p, f'+{count}', r.right() - 24 * s, y + 21 * s, ('m', 20), color(C['amber2'], a), 2)
            y += 32 * s

    def hazard(self, p, r, d):
        s, ingame = self.s, self.ingame
        active = hazards(d) if ingame else []
        self.panel(p, r, 12, color(C['panel']), color(C['amber'], .55) if active else color(C['line']))
        x, micro = r.left() + 24 * s, ('b', 11, 600, .22)
        self.label(p, 'Gefahren', x, r.top() + 36 * s)
        y, geiger = r.top() + 52 * s, d.get('geiger', 0)
        g = (1000 - geiger) / 1000 if 0 < geiger < 1000 else 0
        self.txt(p, 'GEIGER', x, y + 14 * s, micro, color(C['text3']))
        self.cells(p, QRectF(x + 76 * s, y + 6 * s, r.right() - 24 * s - x - 76 * s, 8 * s), 16, g if ingame else 0, color(C['red2'] if g > .6 else C['amber']), color(C['line']))
        y += 28 * s
        air = d.get('air', -1)
        if ingame and air >= 0:  # the air meter, only under water
            part = max(0, air) / 12
            self.txt(p, 'LUFT', x, y + 14 * s, micro, color(C['teal2']))
            self.bar(p, QRectF(x + 76 * s, y + 6 * s, r.right() - 84 * s - x - 76 * s, 8 * s), part, color(C['red' if part < .34 else 'teal']), color(C['red2' if part < .34 else 'teal2']))
            self.txt(p, f'{max(0, air):.0f}s', r.right() - 24 * s, y + 15 * s, ('m', 15), color(C['red2' if part < .34 else 'teal2']), 2)
        else:
            wet = ingame and d.get('water', 0) > 0
            self.txt(p, 'LUFT', x, y + 14 * s, micro, color(C['text3']))
            self.txt(p, '--' if not ingame else 'im Wasser' if wet else 'ok', x + 76 * s, y + 15 * s, ('m', 15), color(C['teal2' if wet else 'text3']))
        y += 30 * s
        if not active: self.txt(p, 'Keine Gefahren erkannt' if ingame else '--', x, y + 22 * s, ('b', 16), color(C['text3']))
        else:
            cx, cy, f = x, y + 2 * s, ('b', 14, 600, .22)
            for text, col in active:
                w = self.width(text.upper(), f) + 28 * s
                if cx + w > r.right() - 20 * s: cx, cy = x, cy + 36 * s
                self.panel(p, QRectF(cx, cy, w, 28 * s), 6, color(C[col], .2), None)
                self.txt(p, text.upper(), cx + 14 * s, cy + 19 * s, f, color(C[col]))
                cx += w + 8 * s
        self.compass(p, QRectF(r.left() + 16 * s, r.bottom() - 50 * s, r.width() - 32 * s, 36 * s), d)

    def compass(self, p, r, d):
        """A compass tape; heading 0 = +Y (north on the map), where the damage comes from as red marks at its edges."""
        s, ingame = self.s, self.ingame
        self.panel(p, r, 6, color(C['bg2']), None)
        heading, per = (90 - d.get('yaw', 0)) % 360 if ingame else 0, r.width() / 120  # 120 degrees show
        p.save(); p.setClipRect(r)
        for deg in range(0, 360, 15):
            rel = (deg - heading + 180) % 360 - 180
            if abs(rel) > 70: continue
            px, major = r.center().x() + rel * per, deg % 45 == 0
            p.fillRect(QRectF(px - .5 * s, r.bottom() - (12 if major else 7) * s, s, (9 if major else 4) * s), color(C['text2' if major else 'line2']))
            if major: self.txt(p, ('N', 'NO', 'O', 'SO', 'S', 'SW', 'W', 'NW')[deg // 45], px, r.top() + 15 * s, ('b', 11, 600), color(C['amber' if deg == 0 else 'text2']), 1)
        p.restore()
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(C['amber']))
        p.drawPolygon(QPolygonF([QPointF(r.center().x() - 6 * s, r.top()), QPointF(r.center().x() + 6 * s, r.top()), QPointF(r.center().x(), r.top() + 7 * s)]))
        front, right, rear, left = ((d.get('pain') or []) + [0] * 4)[:4] if ingame else [0] * 4
        red = lambda v: color(C['red'], min(1, v))
        if right > 0: p.fillRect(QRectF(r.right() - 6 * s, r.top(), 6 * s, r.height()), red(right))
        if left > 0: p.fillRect(QRectF(r.left(), r.top(), 6 * s, r.height()), red(left))
        if front > 0: p.fillRect(QRectF(r.center().x() - 30 * s, r.bottom() - 3 * s, 60 * s, 3 * s), red(front))
        if rear > 0:
            for x in (r.left(), r.right() - 40 * s): p.fillRect(QRectF(x, r.bottom() - 3 * s, 40 * s, 3 * s), red(rear))

    def location(self, p, r, d):
        s, ingame, level = self.s, self.ingame, d.get('map') or ''
        self.panel(p, r, 12, color(C['panel']), color(C['line']))
        x = r.left() + 24 * s
        self.label(p, 'Ort', x, r.top() + 36 * s)
        if ingame: self.txt(p, level.upper(), r.right() - 24 * s, r.top() + 36 * s, ('m', 15), color(C['text3']), 2)
        title, f = chapter(level, self.previous_map) if ingame else None, ('b', 20, 600)
        self.txt(p, self.fit(title or (level if ingame else '--'), f, r.width() - 48 * s), x, r.top() + 66 * s, f, color(C['amber2' if title else 'text2']))
        m = QRectF(r.left() + 16 * s, r.top() + 82 * s, r.width() - 32 * s, r.height() - 96 * s)  # the breadcrumb map: north up, fitted to the panel
        self.panel(p, m, 6, color(C['bg2']), None)
        trail, pos = self.trail, (d.get('pos') or [0, 0])[:2]
        if not ingame or not trail: return
        xs, ys = [q[0] for q in trail] + [pos[0]], [q[1] for q in trail] + [pos[1]]
        k = (min(m.width(), m.height()) - 28 * s) / max(512, max(xs) - min(xs), max(ys) - min(ys))
        mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        at = lambda q: QPointF(m.center().x() + (q[0] - mx) * k, m.center().y() - (q[1] - my) * k)
        p.save(); p.setClipRect(m)
        p.setPen(QPen(color(C['amber'], .45), 2 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(QPolygonF([at(q) for q in trail]))
        here, a, size = at(pos), math.radians(d.get('yaw', 0)), 9 * s
        dx, dy = math.cos(a), -math.sin(a)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(C['amber2']))
        p.drawPolygon(QPolygonF([QPointF(here.x() + dx * size * 1.4, here.y() + dy * size * 1.4), QPointF(here.x() - (dx + dy) * size * .8, here.y() - (dy - dx) * size * .8),
                                 QPointF(here.x() - dx * size * .3, here.y() - dy * size * .3), QPointF(here.x() - (dx - dy) * size * .8, here.y() - (dy + dx) * size * .8)]))
        p.restore()

    def buttons(self, p, d):
        s, ingame, lamp = self.s, self.ingame, bool(d.get('fl')) and self.ingame
        def load():
            if self.twice('quick'):
                self.link.send('loadquick'); self.say('Lade Schnellspeicherstand')
        def save(): self.link.send('savequick'); self.say('Schnellgespeichert')
        def leave():
            if self.twice('quit'): self.w.post('api/quit')
        open_ = lambda key: self.armed[0] == key and self.now - self.armed[1] < ARMED
        # name, hint, lit, enabled, action. MENÜ is the game's own Escape (opens its menu, closes it again).
        items = [(GAMES[self.game][2], 'F', lamp, ingame, lambda: self.link.send('impulse 100')), ('Benutzen', 'E', False, ingame, lambda: self.link.send('thor_use')),
                 ('Schnellspeichern', 'F6', False, ingame, save), ('Nochmal tippen' if open_('quick') else 'Schnellladen', 'F7', open_('quick'), self.connected, load),
                 ('Menü', 'ESC', False, self.connected, lambda: self.link.send('cancelselect')), ('Nochmal tippen' if open_('quit') else 'Beenden', 'TANDEM', open_('quit'), True, leave)]
        bw = (1192 - (len(items) - 1) * 12) / len(items)
        for i, (name, hint, lit, enabled, act) in enumerate(items):
            b, f = self.R(24 + i * (bw + 12), 960, bw, 96), ('b', 15, 600, .1)
            self.panel(p, b, 12, color(C['amber'], .12) if lit else color(C['panel']), color(C['amber'] if lit else C['line']))
            self.txt(p, self.fit(name.upper(), f, b.width() - 20 * s), b.center().x(), b.center().y() + 2 * s, f, color(C['text3'] if not enabled else C['amber2'] if lit else C['text']), 1)
            self.txt(p, hint, b.center().x(), b.bottom() - 16 * s, ('m', 13), color(C['text3']), 1)
            if i == 0:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(C['amber'] if lamp else C['line2']))
                p.drawEllipse(QPointF(b.left() + 22 * s, b.top() + 22 * s), 5 * s, 5 * s)
            if enabled: self.w.hit(b, act, name=name)
