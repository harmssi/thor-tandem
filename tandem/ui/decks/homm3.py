"""Deck for Heroes of Might and Magic III on the bottom screen (the native port in ports/homm3, the VCMI fork "Heroes III Thor Edition").

Native port of the Android deck of that fork (ThorDeck.java, H3Art.java), in the look of the game: its own stone
texture, picture buttons, portraits, icons and fonts, which the running game reads from the player's files and sends over
("art <key>"); until a piece arrives, or if the files do not have it, the deck draws that piece itself in the same style.
Adventure map: resources and date, minimap (tap = jump), heroes and towns with portraits (tap = select, again = open),
army (tap two slots = move / swap / merge, hold the second = split half off) and four pages of commands: the side panel
buttons, adventure spells, map tools, game. Town: its buildings and armies. Any window: accept / cancel / arrows.
Battle: turn order, active unit, the hero's spells, log, the battle buttons, speed.
Everything shown is the snapshot the game sends over the deck socket (decks/portsocket.py, the fork's ThorDeck.cpp);
every press goes back as a text command the game runs on its own thread. Laid out on 1240 x 1080 units and scaled.

Interface for tandem_ui (see DECKS there): Deck(window), paint(painter) -> bool, press(pos), close().
plain(), clean(), parse_art() and spell_order() are plain Python (no Qt) and carry the logic worth testing.
"""
import base64, json, re, struct, threading, time

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPen, QTransform

from decks.portsocket import Link

W, H = 1240, 1080
GOLD, WHITE, GREY, RED = 0xFFE5D77B, 0xFFFFF3DE, 0xFF8C8273, 0xFFE8503C  # the game's yellow and white text
FRAME_HI, FRAME_MID, FRAME_LO, STONE, STONE_DARK, BLACK = 0xFFE7C66B, 0xFFA57B29, 0xFF5A3F10, 0xFF3B2A1C, 0xFF1E150D, 0xFF000000
MOVE, MANA = (0xFF2E7D1E, 0xFFB8E04A), (0xFF1C2E9C, 0xFF6FA8FF)
HOLD, CONFIRM = .45, 3.0  # seconds: a held army slot, an armed "tap again"
RES = ('Holz', 'Queck', 'Erz', 'Schw', 'Krist', 'Edel', 'Gold')
PREMUL = QImage.Format.Format_ARGB32_Premultiplied
SMOOTH = QPainter.RenderHint.SmoothPixmapTransform


def plain(s):
    """Only what the game's fonts have (Latin-1); typographic characters become plain ones."""
    for a, b in (('…', '...'), ('–', '-'), ('—', '-'), ('·', '-'), ('×', 'x'), ('’', "'"), ('‘', "'"), ('“', '"'), ('”', '"'), ('„', '"')): s = s.replace(a, b)
    return ''.join(ch if 32 <= ord(ch) < 127 or 160 <= ord(ch) < 256 else ' ' for ch in s)


def clean(s):
    """VCMI text markup: {highlight} and {#color|text} -> plain text."""
    return re.sub(r'\{#[0-9A-Za-z]+\|', '', s).replace('{', '').replace('}', '')


def parse_art(data):
    """A block "art:<key>" of the game: (width, height, meta, RGBA bytes), or None when the game files do not have the piece.
    meta = the advance of the characters 32..255 when the piece is a font atlas."""
    if len(data) < 12: return None
    w, h, n = struct.unpack_from('<III', data)
    at = 12 + n * 4
    if not w or not h or w > 65536 or h > 4096 or len(data) < at + w * h * 4: return None
    return w, h, list(struct.unpack_from(f'<{n}i', data, 12)), data[at:at + w * h * 4]


def spell_order(spells, room):
    """Castable spells first; the spell book has the rest if the list is longer than the page."""
    return ([s for s in spells if s.get('ok')] + [s for s in spells if not s.get('ok')])[:room]


def color(argb): return QColor((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, argb >> 24)


def box(l, t, r, b): return QRectF(l, t, r - l, b - t)


def part(a, b): return a / max(1, b)


class Deck:
    def __init__(self, window):
        self.w = window
        self.st, self.alive, self.fresh, self.minimap = {}, True, False, None
        self.pics, self.fonts, self.tints, self.plain_fonts = {}, {}, {}, {}
        self.tab, self.slot, self.pressed, self.pressed_at, self.held, self.armed = 0, -1, None, 0.0, False, 0.0
        self.painted, self.waiting, self.areas, self.stage, self.zoom, self.map_rect = 0.0, False, [], None, 1.0, None
        self.link = Link((window.RUN.get('port') or {}).get('socket') or '', self.heard, self.block)

    def close(self):
        self.alive = False
        self.link.close()

    # ---- the game's data (on the link's thread) ------------------------------------------------------------------------
    def heard(self, d):
        if d is None:  # the game is gone: what was asked for and never came is asked again
            self.st, self.fresh = {}, False
            self.pics, self.fonts = {k: v for k, v in self.pics.items() if v}, {k: v for k, v in self.fonts.items() if v}
        elif 'minimap' in d:
            w, h, rgb = d.get('w') or 0, d.get('h') or 0, base64.b64decode(d['minimap'])
            if w > 0 and h > 0 and len(rgb) >= w * h * 3: self.minimap = QImage(rgb, w, h, w * 3, QImage.Format.Format_RGB888).copy()  # copy: the bytes go
        elif 'mode' in d:
            self.st = d
            if not self.fresh:  # connected after the game started: it sends its minimap again
                self.fresh = True
                self.link.send('fresh')
        self.changed()

    def block(self, name, data):
        if name == 'json':  # a state too long for a line (the minimap)
            try: return self.heard(json.loads(data))
            except ValueError: return
        if not name.startswith('art:'): return
        art = parse_art(data)
        img = QImage(art[3], art[0], art[1], art[0] * 4, QImage.Format.Format_RGBA8888).convertToFormat(PREMUL) if art else None
        if not name.startswith('art:font:'): self.pics[name[4:]] = img or False  # False: asked, there is none
        elif img is None or len(art[2]) < 224: self.fonts[name[9:]] = False
        else:  # an atlas of the characters 32..255, each in a cell of its advance + 4
            xs, x = [], 0
            for adv in art[2][:224]:
                xs.append(x)
                x += adv + 4
            self.fonts[name[9:]] = (img, xs, art[2][:224])
        self.changed()

    def ask(self, store, name, key):
        """A piece of the game's art, or None while it is on its way (or there is none). Asked once, and only of a game that listens."""
        if name not in store and self.fresh:
            store[name] = None
            self.link.send('art ' + key)
        return store.get(name) or None

    def pic(self, key): return self.ask(self.pics, key, key)

    def font(self, name): return self.ask(self.fonts, name, 'font:' + name)

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

    # ---- touch ----------------------------------------------------------------------------------------------------------
    def press(self, pos):
        """A finger down (pos) or up (None). The minimap answers at once; everything else on release (see hit)."""
        if pos is None:
            self.held, self.pressed = self.pressed is not None and time.time() - self.pressed_at >= HOLD, None
            return self.changed()
        at, m = self.stage.inverted()[0].map(pos) if self.stage else pos, self.st.get('map') or {}
        if self.map_rect and self.map_rect.contains(at):
            r = self.map_rect
            return self.link.send(f'tile {int((at.x() - r.left()) / r.width() * m.get("w", 0))} {int((at.y() - r.top()) / r.height() * m.get("h", 0))}')
        self.pressed, self.pressed_at = next((cmd for rect, cmd in reversed(self.areas) if rect.contains(at)), None), time.time()
        self.changed()

    def hit(self, r, cmd, hold=None):
        """Names a rect for touch: a tap runs cmd, a long press hold. True while a finger is on it."""
        self.areas.append((r, cmd))
        self.w.hit(r, lambda: self.run(hold if hold and self.held else cmd), name=cmd)
        return self.pressed == cmd

    def run(self, cmd):
        self.held = False
        if cmd.startswith('ui:tab '): self.tab = int(cmd[7:])
        elif cmd == 'ui:quit':  # ends the game and returns to Tandem: asks first
            if time.time() - self.armed < CONFIRM: self.w.post('api/quit')
            else: self.armed = time.time(); self.later(CONFIRM + .1)
        elif cmd.startswith('ui:'):
            # army: the first tap picks a stack up, the second puts it down (move / swap / merge), held = half of it
            kind, slot, filled = cmd.split()
            if self.slot < 0: self.slot = int(slot) if filled == '1' else -1
            elif int(slot) == self.slot: self.slot = -1
            else:
                self.link.send(f'army {self.slot} {slot} {"s" if kind == "ui:split" else "m"}')
                self.slot = -1
        else: self.link.send(cmd)
        self.changed()

    # ---- the look: the game's art and fonts, or the same in plain ---------------------------------------------------------
    def tint(self, key, img, argb):
        """img multiplied by a colour (the fonts are white; a dimmed picture is one times grey), kept."""
        if (key, argb) not in self.tints:
            out = QImage(img.size(), PREMUL)
            out.fill(color(argb | BLACK))
            q = QPainter(out)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply); q.drawImage(0, 0, img)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn); q.drawImage(0, 0, img)
            q.end()
            self.tints[key, argb] = out
        return self.tints[key, argb]

    def serif(self, line):
        size = max(1, round(line * .72))
        if size not in self.plain_fonts:
            f = QFont('serif')
            f.setPixelSize(size); f.setBold(True)
            self.plain_fonts[size] = (f, QFontMetricsF(f))
        return self.plain_fonts[size]

    def width(self, font, s, line):
        f, s = self.font(font), plain(s)
        if not f: return self.serif(line)[1].horizontalAdvance(s)
        return sum(f[2][ord(ch) - 32] for ch in s) * line / f[0].height()

    def fit(self, font, s, line, room):
        if self.width(font, s, line) <= room: return s
        while len(s) > 1 and self.width(font, s + '..', line) > room: s = s[:-1]
        return s.strip() + '..'

    def text(self, p, font, s, x, y, line, argb, align=1):
        """One line in a game font; align 0 = left, 1 = centred, 2 = right; y = top of the line."""
        f, s = self.font(font), plain(s)
        x -= self.width(font, s, line) * align / 2
        if not f:
            p.setFont(self.serif(line)[0])
            p.setPen(color(BLACK)); p.drawText(QPointF(x + 1.5, y + line * .76 + 1.5), s)
            p.setPen(color(argb)); p.drawText(QPointF(x, y + line * .76), s)
            return
        atlas, xs, ws = f
        k, img = line / atlas.height(), self.tint('font:' + font, atlas, argb)
        p.setRenderHint(SMOOTH, abs(k * self.zoom - round(k * self.zoom)) > .02)  # whole multiples stay crisp pixels
        for ch in s:
            g = ord(ch) - 32
            if ws[g] > 0: p.drawImage(QRectF(x, y, (ws[g] + 4) * k, line), img, QRectF(xs[g], 0, ws[g] + 4, atlas.height()))
            x += ws[g] * k

    def shade(self, p, r, a, b, across=False):
        g = QLinearGradient(r.left(), r.top(), r.right() if across else r.left(), r.top() if across else r.bottom())
        g.setColorAt(0, color(a)); g.setColorAt(1, color(b))
        p.fillRect(r, QBrush(g))

    def stone(self, p, r):
        """The game's dialog stone texture (DiBoxBck), tiled; a brown gradient of ours until it arrives."""
        img = self.pic('img:DIBOXBCK')
        if img is None: return self.shade(p, r, STONE, STONE_DARK)
        brush = QBrush(img)
        brush.setTransform(QTransform().scale(2, 2))
        p.setRenderHint(SMOOTH, False)
        p.fillRect(r, brush)

    def frame(self, p, r, u=2, sunken=True):
        """Gold bevel frame around r (drawn outside-in), like the game's panel borders."""
        for i, (tl, br) in enumerate(zip((BLACK, FRAME_LO if sunken else FRAME_HI, FRAME_MID), (BLACK, FRAME_HI if sunken else FRAME_LO, FRAME_MID))):
            o = i * u
            p.fillRect(box(r.left() + o, r.top() + o, r.right() - o, r.top() + o + u), color(tl)); p.fillRect(box(r.left() + o, r.top() + o, r.left() + o + u, r.bottom() - o), color(tl))
            p.fillRect(box(r.left() + o, r.bottom() - o - u, r.right() - o, r.bottom() - o), color(br)); p.fillRect(box(r.right() - o - u, r.top() + o, r.right() - o, r.bottom() - o), color(br))

    def well(self, p, r):
        """Dark inset field with a gold frame: the game's info boxes and list slots."""
        p.fillRect(r, color(0xB0000000))
        self.frame(p, r)

    def button(self, p, r, label, cmd, enabled=True, lit=False):
        """Text button in the game's style: brown stone face, gold bevel, gold lettering; inactive ones are grey and do nothing."""
        down = enabled and self.hit(r, cmd)
        self.shade(p, r, 0xFF2A1B0E if down else 0xFF7A5524 if lit else 0xFF5C3F1E, 0xFF4A3218 if down else 0xFF4E3414 if lit else 0xFF2E1E0E)
        self.frame(p, r, 2, down)
        line = min(28, r.height() * .5)
        self.text(p, 'medium', self.fit('medium', label, line, r.width() - 20), r.center().x(), r.center().y() - line / 2 + (2 if down else 0), line,
                  (WHITE if lit else GOLD) if enabled else GREY)

    def grid(self, p, buttons, cols, top, bottom):
        """Rows of text buttons: (label, command[, active])."""
        rows = (len(buttons) + cols - 1) // cols
        bw, bh = (W - 32 - (cols - 1) * 8) / cols, (bottom - top - (rows - 1) * 8) / rows
        for i, b in enumerate(buttons):
            x, y = 16 + (i % cols) * (bw + 8), top + (i // cols) * (bh + 8)
            self.button(p, QRectF(x, y, bw, bh), b[0], b[1], len(b) < 3 or bool(b[2]))

    def picture(self, p, key, r, crisp=True, dim=False):
        """A picture of the game scaled into r (in proportion, centred); False if the game files do not have it (yet)."""
        img = self.pic(key)
        if img is None: return False
        k = min(r.width() / img.width(), r.height() / img.height())
        p.setRenderHint(SMOOTH, not crisp)
        p.drawImage(QRectF(r.center().x() - img.width() * k / 2, r.center().y() - img.height() * k / 2, img.width() * k, img.height() * k),
                    self.tint(key, img, 0xFF707070) if dim else img)
        return True

    def art_button(self, p, x, y, w, h, name, label, cmd, enabled=True):
        """One of the game's own picture buttons (frames: normal, pressed, blocked), with a caption below."""
        r = QRectF(x, y, w, h)
        down = enabled and self.hit(r, cmd)
        # the adventure map buttons carry the player's colour, as in the game
        if not self.picture(p, f'def:{name}:{2 if not enabled else 1 if down else 0}' + (f':{self.st.get("player", 0)}' if name.startswith('IAM') else ''), r):
            self.shade(p, r, 0xFF5C3F1E, 0xFF2E1E0E); self.frame(p, r, 2, down)
        self.text(p, 'small', self.fit('small', label, 22, w + 8), x + w / 2, y + h + 4, 22, GOLD if enabled else GREY)

    def bar(self, p, r, fraction, colors, upright=False):
        """Bar like the movement / spell point bars beside the game's hero portraits."""
        p.fillRect(r, color(BLACK))
        f = max(0.0, min(1.0, fraction))
        if f <= 0: return
        if upright: self.shade(p, box(r.left() + 1, r.bottom() - (r.height() - 2) * f - 1, r.right() - 1, r.bottom() - 1), colors[1], colors[0])
        else: self.shade(p, box(r.left() + 1, r.top() + 1, r.left() + 1 + (r.width() - 2) * f, r.bottom() - 1), colors[0], colors[1], True)

    # ---- painting -----------------------------------------------------------------------------------------------------
    def paint(self, p):
        w, mode = self.w, self.st.get('mode', 'menu')
        self.zoom = k = min(w.width() / W, w.height() / H)
        self.stage = xf = QTransform().translate((w.width() - W * k) / 2, 0).scale(k, k)
        self.painted, self.areas, self.map_rect = time.time(), [], None
        p.save()
        p.fillRect(0, 0, w.width(), w.height(), color(STONE_DARK))
        p.setTransform(xf)
        w.xf, w.zoom = xf, k  # taps arrive in window pixels
        try:
            self.stone(p, QRectF(0, 0, W, H))
            if mode == 'menu': self.menu(p)
            elif mode == 'battle': self.battle(p, self.st.get('battle') or {})
            else: self.adventure(p, mode)
        finally:
            w.xf, w.zoom = None, 1.0
            p.restore()
        return True

    def menu(self, p):
        self.well(p, box(220, 300, 1020, 760))
        self.text(p, 'big', 'Heroes III', W / 2, 350, 80, GOLD)
        self.text(p, 'big', 'Thor Edition', W / 2, 440, 60, WHITE)
        self.text(p, 'medium', 'für VCMI, eine Open-Source-Engine für Heroes III', W / 2, 530, 32, WHITE)
        self.text(p, 'medium', 'Spiel auf dem oberen Bildschirm wählen', W / 2, 590, 32, GOLD)
        self.text(p, 'small', 'Linker Stick = Zeiger - X = Klick - Y = Rechtsklick - A = OK - B = Abbrechen', W / 2, 650, 24, GREY)
        self.text(p, 'small', 'L1 / R1 = nächster Held / Stadt - R2 = Zauberbuch - Select = Zug beenden - Start = Optionen', W / 2, 682, 24, GREY)
        self.quit(p, box(470, 820, 770, 890))

    def quit(self, p, r):
        armed = time.time() - self.armed < CONFIRM
        self.button(p, r, 'Nochmal tippen' if armed else 'Spiel beenden', 'ui:quit', lit=armed)

    def can(self, what): return bool((self.st.get('can') or {}).get(what))

    def resources(self, p):
        res = self.st.get('res') or []
        for i in range(7):
            x = 16 + i * 146
            self.well(p, box(x, 10, x + 140, 72))
            if not self.picture(p, f'def:RESOURCE:{i}', box(x + 6, 15, x + 58, 67)): self.text(p, 'small', RES[i], x + 8, 14, 20, GREY, 0)
            self.text(p, 'medium', str(res[i]) if i < len(res) else '-', x + 132, 25, 32, GOLD if i == 6 else WHITE, 2)
        self.well(p, box(1038, 10, 1224, 72))
        self.text(p, 'small', f'Monat {self.st.get("month", 0)}, Woche {self.st.get("week", 0)}', 1131, 15, 24, WHITE)
        self.text(p, 'small', f'Tag {self.st.get("day", 0)}', 1131, 41, 24, GOLD)

    def adventure(self, p, mode):
        st, live = self.st, mode == 'adventure'  # selection and army orders only act on the plain map
        self.resources(p)
        self.well(p, box(16, 84, 456, 524))
        m, mm = st.get('map') or {}, self.minimap
        if mm is not None and mm.width() == m.get('w'):
            k = 420 / max(mm.width(), mm.height())
            d = QRectF(26 + (420 - mm.width() * k) / 2, 94 + (420 - mm.height() * k) / 2, mm.width() * k, mm.height() * k)
            p.setRenderHint(SMOOTH, False)
            p.drawImage(d, mm)
            v = m.get('view') or []
            if len(v) >= 4 and v[2] > 0:
                p.setPen(QPen(color(WHITE), 2)); p.setBrush(QBrush())
                p.drawRect(QRectF(d.left() + v[0] * k, d.top() + v[1] * k, v[2] * k, v[3] * k).intersected(d))
            if live: self.map_rect = d
        heroes, towns = st.get('heroes') or [], st.get('towns') or []
        self.portraits(p, heroes, 84, 298, True, live)
        self.portraits(p, towns, 310, 524, False, live)
        hero, town = next((h for h in heroes if h.get('selected')), None), next((t for t in towns if t.get('selected')), None)
        self.army(p, live)
        self.info(p, hero, town, live)
        if mode == 'town': self.town(p, town)
        elif not live: self.window(p, 716)
        else:
            for i, name in enumerate(('Befehle', 'Abenteuerzauber', 'Karte', 'Spiel')):
                self.button(p, QRectF(16 + i * 304, 716, 296, 46), name, f'ui:tab {i}', lit=self.tab == i)
            (self.commands, self.spells, self.map_tools, self.game)[self.tab](p, hero)

    def portraits(self, p, items, top, bottom, heroes, live):
        """Heroes (portrait between movement and spell point bars, as in the game's hero list) or towns."""
        self.well(p, box(468, top, 1224, bottom))
        items = items[:16]
        if not items: return self.text(p, 'medium', 'Keine Helden' if heroes else 'Keine Städte', 846, (top + bottom) / 2 - 16, 32, GREY)
        rows = 2 if len(items) > 8 else 1
        cols = max(4, (len(items) + rows - 1) // rows)
        cw, ch = 744 / cols, (bottom - top - 12) / rows
        bar, name_h = (min(12, cw * .09) if heroes else 0), (24 if rows == 1 else 18)
        ph = min(ch - name_h - 10, (cw - 2 * bar - 14) * 64 / 58)
        pw = ph * 58 / 64
        for i, o in enumerate(items):
            cx, y, sel = 474 + (i % cols) * cw + cw / 2, top + 8 + (i // cols) * ch, o.get('selected')
            pr = QRectF(cx - pw / 2, y, pw, ph)
            if sel: p.fillRect(box(cx - pw / 2 - bar - 5, y - 3, cx + pw / 2 + bar + 5, y + ph + 3), color(FRAME_HI))
            if not self.picture(p, f'def:{"PortraitsLarge" if heroes else "ITPT"}:{o.get("icon", 0)}', pr, False, heroes and o.get('sleeping')): p.fillRect(pr, color(0xFF2A1B0E))
            if heroes:
                self.bar(p, box(cx - pw / 2 - bar - 2, y, cx - pw / 2 - 2, y + ph), part(o.get('mp', 0), o.get('mpMax', 0)), MOVE, True)
                self.bar(p, box(cx + pw / 2 + 2, y, cx + pw / 2 + bar + 2, y + ph), part(o.get('mana', 0), o.get('manaMax', 0)), MANA, True)
                if o.get('sleeping'): self.text(p, 'big', 'Zz', cx, y + ph / 2 - 20, 40, WHITE)
            self.text(p, 'small', self.fit('small', o.get('name', ''), name_h, cw - 6), cx, y + ph + 5, name_h, GOLD if sel else WHITE)
            if live: self.hit(box(cx - cw / 2, y - 4, cx + cw / 2, y + ch - 4), f'{"hero" if heroes else "town"} {o.get("id")}')

    def army(self, p, live):
        self.well(p, box(16, 536, 892, 704))
        stacks = {s.get('slot'): s for s in self.st.get('army') or []}
        if not stacks: self.slot = -1
        for i in range(7):
            x, s = 26 + i * 123, stacks.get(i)
            r = box(x, 544, x + 116, 672)
            p.fillRect(r, color(0xFF140D07))
            if s:
                if not self.picture(p, f'def:TWCRPORT:{s.get("icon", 0)}', r): self.text(p, 'small', self.fit('small', s.get('name', ''), 20, 110), x + 58, 580, 20, WHITE)
                p.fillRect(box(x, 644, x + 116, 672), color(0xA0000000))
                self.text(p, 'medium', str(s.get('count', 0)), x + 110, 644, 28, WHITE, 2)
            self.frame(p, box(x - 3, 541, x + 119, 675), 1)
            if i == self.slot:
                p.setPen(QPen(color(FRAME_HI), 4)); p.setBrush(QBrush())
                p.drawRect(box(x - 1, 543, x + 117, 673))
            if live: self.hit(r, f'ui:slot {i} {int(bool(s))}', f'ui:split {i} {int(bool(s))}')
        hint = (self.st.get('armyOf') or '') if not live else 'Platz antippen: ziehen, tauschen, vereinen - halten: Hälfte abteilen' if self.slot >= 0 else 'Armee: Trupp antippen zum Aufnehmen'
        self.text(p, 'small', self.fit('small', hint, 22, 850), 454, 678, 22, GOLD if self.slot >= 0 else GREY)

    def info(self, p, hero, town, live):
        self.well(p, box(900, 536, 1224, 704))
        if hero:
            self.text(p, 'big', self.fit('big', hero.get('name', ''), 36, 300), 1062, 542, 36, GOLD)
            self.text(p, 'small', f'Stufe {hero.get("level", 0)}', 1062, 578, 22, WHITE)
            for i, (name, key) in enumerate((('Ang', 'attack'), ('Vtd', 'defense'), ('Kra', 'power'), ('Wis', 'knowledge'))):
                self.text(p, 'small', name, 942 + i * 80, 604, 20, GREY)
                self.text(p, 'medium', str(hero.get(key, 0)), 942 + i * 80, 624, 28, WHITE)
            self.bar(p, box(912, 660, 1058, 672), part(hero.get('mp', 0), hero.get('mpMax', 0)), MOVE)
            self.bar(p, box(1066, 660, 1212, 672), part(hero.get('mana', 0), hero.get('manaMax', 0)), MANA)
            self.text(p, 'small', f'Bew. {hero.get("mp", 0)}', 985, 675, 20, WHITE)
            self.text(p, 'small', f'Mana {hero.get("mana", 0)}/{hero.get("manaMax", 0)}', 1139, 675, 20, WHITE)
        elif town:
            self.text(p, 'big', self.fit('big', town.get('name', ''), 36, 300), 1062, 560, 36, GOLD)
            self.text(p, 'small', 'Heute gebaut' if town.get('built') else 'Kann heute bauen', 1062, 610, 22, WHITE)
            if live: self.text(p, 'small', 'Stadt nochmal antippen: betreten', 1062, 650, 20, GREY)

    def commands(self, p, hero):
        sleeping, under = bool(hero and hero.get('sleeping')), ((self.st.get('map') or {}).get('view') or [0] * 5)[4] > 0
        self.art_button(p, 17, 774, 192, 96, 'IAM000', 'Nächster Held', 'key adventureNextHero', self.can('next'))
        self.art_button(p, 215, 774, 192, 96, 'IAM001', 'Zug beenden', 'key adventureEndTurn', self.can('endTurn'))
        for i, (name, label, cmd, on) in enumerate((
                ('IAM006', 'Ziehen', 'key adventureMoveHero', self.can('move')),
                ('IAM011' if sleeping else 'IAM005', 'Wecken' if sleeping else 'Schlafen', 'key adventureToggleSleep', self.can('hero')),
                ('IAM007', 'Zauber', 'key adventureCastSpell', self.can('hero')), ('IAM002', 'Königreich', 'key adventureKingdomOverview', True),
                ('IAM004', 'Aufgaben', 'key adventureQuestLog', self.can('quests')),
                ('IAM003' if under else 'IAM010', 'Oberwelt' if under else 'Unterwelt', 'key adventureToggleMapLevel', self.can('level')),
                ('IAM008', 'Abenteuer', 'key adventureGameOptions', True), ('IAM009', 'System', 'key globalOptions', True))):
            self.art_button(p, 413 + i * 102, 774, 96, 96, name, label, cmd, on)
        self.grid(p, (('Nächste Stadt', 'key adventureNextTown'), ('Heldenfenster' if hero else 'Stadt betreten', 'key adventureViewSelected'),
                      ('Erneut besuchen', 'key adventureVisitObject', self.can('visit')), ('Nach dem Gral graben', 'key adventureDigGrail', self.can('dig')),
                      ('Marktplatz', 'key adventureMarketplace', self.can('market')), ('Diebesgilde', 'key adventureThievesGuild'),
                      ('Rätselkarte', 'key adventureViewPuzzle'), ('Schnellspeichern', 'key adventureQuickSave', self.can('quickSave'))), 4, 908, 1068)

    def spells(self, p, hero):
        known = self.st.get('spells') or []
        if not hero or not known:
            return self.text(p, 'medium', 'Dieser Held kennt keine Abenteuerzauber' if hero else 'Held wählen, um Abenteuerzauber zu sehen', W / 2, 900, 32, GREY)
        self.spell_grid(p, known, 'spell ', 16, 772, 1224, 1068, 4, 3)

    def spell_grid(self, p, known, cmd, left, top, right, bottom, cols, rows):
        """Spell icons from the game's spell book with name and cost; tap = cast (target on the top screen)."""
        cw, ch = (right - left - (cols - 1) * 8) / cols, (bottom - top - (rows - 1) * 8) / rows
        for i, o in enumerate(spell_order(known, cols * rows)):
            x, y, ok = left + (i % cols) * (cw + 8), top + (i // cols) * (ch + 8), bool(o.get('ok'))
            r = QRectF(x, y, cw, ch)
            down = ok and self.hit(r, f'{cmd}{o.get("id")}')
            self.shade(p, r, 0xFF2A1B0E if down else 0xFF5C3F1E, 0xFF4A3218 if down else 0xFF2E1E0E); self.frame(p, r, 2, down)
            iw, line = min(ch - 12, cw * .4) * 83 / 65, 24 if ch > 80 else 20
            self.picture(p, f'def:Spells:{o.get("icon", 0)}', box(x + 8, y + 6, x + 8 + iw, y + ch - 6), True, not ok)
            self.text(p, 'small', self.fit('small', o.get('name', ''), line, cw - iw - 22), x + 14 + iw, y + ch / 2 - line - 1, line, GOLD if ok else GREY, 0)
            self.text(p, 'small', f'{o.get("cost", 0)} Mana', x + 14 + iw, y + ch / 2 + 2, line, WHITE if ok else GREY, 0)

    def map_tools(self, p, hero):
        world = self.can('worldView')
        self.grid(p, (('Weltansicht', 'key adventureViewWorld', not world), ('Welt 1x', 'key adventureViewWorld1', world), ('Welt 2x', 'key adventureViewWorld2', world),
                      ('Welt 4x', 'key adventureViewWorld4', world), ('Zurück zur Karte', 'key adventureExitWorldView', world), ('Vergrößern', 'key adventureZoomIn'),
                      ('Verkleinern', 'key adventureZoomOut'), ('Zoom zurücksetzen', 'key adventureZoomReset'),
                      ('Oberwelt / Unterwelt', 'key adventureToggleMapLevel', self.can('level')), ('Raster', 'key adventureToggleGrid', not world),
                      ('Besuchbares zeigen', 'key adventureToggleVisitable', not world), ('Blockiertes zeigen', 'key adventureToggleBlocked', not world)), 4, 772, 1068)

    def game(self, p, hero):
        self.grid(p, (('Schnellspeichern', 'key adventureQuickSave', self.can('quickSave')), ('Schnellladen', 'key adventureQuickLoad', self.can('quickLoad')),
                      ('Spiel speichern', 'key adventureSaveGame'), ('Spiel laden', 'key adventureLoadGame'), ('Szenario-Info', 'key adventureViewScenario'),
                      ('Abenteuer-Optionen', 'key adventureGameOptions'), ('Systemoptionen', 'key globalOptions'), ('Hauptmenü', 'key adventureMainMenu')), 4, 772, 968)
        self.quit(p, box(16 + 3 * 304, 976, 1224, 1068))

    def town(self, p, town):
        self.text(p, 'big', (town or {}).get('name') or 'Stadt', W / 2, 718, 40, GOLD)
        self.grid(p, (('Rathaus', 'key townOpenHall'), ('Festung', 'key townOpenFort'), ('Rekrutieren', 'key townOpenRecruitment'), ('Taverne', 'key townOpenTavern'),
                      ('Marktplatz', 'key townOpenMarket'), ('Magiergilde', 'key townOpenMageGuild'), ('Armeen tauschen', 'key townSwapArmies'),
                      ('Besuchender Held', 'key townOpenVisitingHero'), ('Garnisonsheld', 'key townOpenGarrisonedHero'), ('Vorige Stadt', 'key moveUp'),
                      ('Nächste Stadt', 'key moveDown'), ('Stadt verlassen', 'key globalReturn')), 4, 772, 1068)

    def window(self, p, top):
        """A window of the game is open on the top screen: answer it from here (the keys Enter, Escape, arrows)."""
        self.text(p, 'medium', 'Oben ist ein Fenster offen', W / 2, top + 6, 32, GOLD)
        y = top + 56
        h = 1068 - y
        aw, ah = (1224 - 800 - 16) / 3, (h - 8) / 2
        self.button(p, box(16, y, 400, y + h), 'OK / Annehmen', 'key globalAccept,globalReturn', lit=True)
        self.button(p, box(408, y, 792, y + h), 'Abbrechen / Schließen', 'key globalCancel,globalReturn')
        self.button(p, box(800 + aw + 8, y, 800 + 2 * aw + 8, y + ah), 'Hoch', 'key moveUp')
        self.button(p, box(800, y + ah + 8, 800 + aw, y + h), 'Links', 'key moveLeft')
        self.button(p, box(800 + aw + 8, y + ah + 8, 800 + 2 * aw + 8, y + h), 'Runter', 'key moveDown')
        self.button(p, box(800 + 2 * aw + 16, y + ah + 8, 1224, y + h), 'Rechts', 'key moveRight')

    def battle(self, p, b):
        u, has_hero = b.get('unit'), 'hero' in b
        self.well(p, box(16, 10, 1224, 72))  # hero and spell points
        if has_hero:
            self.picture(p, f'def:PortraitsLarge:{b.get("heroIcon", 0)}', box(22, 14, 72, 68), False)
            self.text(p, 'big', self.fit('big', b.get('hero', ''), 36, 380), 84, 23, 36, GOLD, 0)
            self.text(p, 'medium', f'Zauberpunkte {b.get("mana", 0)} / {b.get("manaMax", 0)}', 1214, 14, 28, WHITE, 2)
            self.bar(p, box(820, 48, 1214, 62), part(b.get('mana', 0), b.get('manaMax', 0)), MANA)
        else: self.text(p, 'big', 'Kampf', 30, 23, 36, GOLD, 0)

        self.well(p, box(16, 84, 1224, 226))  # turn order: attacker red, defender blue, as the banners on the battlefield
        for i, o in enumerate((b.get('queue') or [])[:13]):
            x = 26 + i * 92
            p.fillRect(box(x - 3, 91, x + 87, 219), color(FRAME_HI if i == 0 else 0xFF2848B0 if o.get('side') else 0xFFB02818))
            p.fillRect(box(x, 94, x + 84, 187), color(0xFF140D07))
            self.picture(p, f'def:TWCRPORT:{o.get("icon", 0)}', box(x, 94, x + 84, 187), False, o.get('turn', 0) > 0)
            p.fillRect(box(x, 189, x + 84, 216), color(BLACK))
            self.text(p, 'small', str(o.get('count', 0)), x + 42, 191, 24, WHITE)

        self.well(p, box(16, 238, 420, 700))  # active unit
        if u:
            self.picture(p, f'def:TWCRPORT:{u.get("icon", 0)}', box(28, 250, 144, 378))
            self.text(p, 'big', self.fit('big', u.get('name', ''), 32, 250), 156, 262, 32, GOLD, 0)
            self.text(p, 'big', f'x {u.get("count", 0)}', 156, 310, 40, WHITE, 0)
            for i, (name, value) in enumerate((('Angriff', u.get('attack', 0)), ('Verteidigung', u.get('defense', 0)), ('Schaden', f'{u.get("dmgMin", 0)} - {u.get("dmgMax", 0)}'),
                                               ('Leben', f'{u.get("hp", 0)} / {u.get("hpMax", 0)}'), ('Tempo', u.get('speed', 0)), ('Schüsse', u.get('shots', 0) if u.get('shooter') else '-'))):
                self.text(p, 'medium', name, 32, 398 + i * 44, 28, WHITE, 0)
                self.text(p, 'medium', str(value), 404, 398 + i * 44, 28, GOLD, 2)
            self.bar(p, box(30, 668, 406, 684), part(u.get('hp', 0), u.get('hpMax', 0)), (0xFF8C1C10, RED))
        else: self.text(p, 'medium', 'Warte auf Euren Zug', 218, 450, 28, GREY)

        self.well(p, box(432, 238, 1224, 700))  # the hero's combat spells
        if b.get('spells'): self.spell_grid(p, b['spells'], 'bspell ', 442, 248, 1214, 690, 3, 6)
        else: self.text(p, 'medium', 'Keine Kampfzauber' if has_hero else 'Kein Held in diesem Kampf', 828, 450, 28, GREY)

        self.well(p, box(16, 712, 1224, 852))  # log, the newest line at the bottom
        log, y = b.get('log') or [], 818
        for i in range(len(log) - 1, -1, -1):
            for line in reversed(self.wrap(clean(log[i]), 26, 1180)):
                if y <= 714: break
                self.text(p, 'small', line, 28, y, 26, WHITE if i == len(log) - 1 else GREY, 0)
                y -= 30

        if self.st.get('modal'): return self.window(p, 858)
        tactics, mine = bool(b.get('tactics')), bool(u)
        buttons = [('icm011', 'Nächste Einheit', 'key battleTacticsNext', True), ('icm012', 'Kampf beginnen', 'key battleTacticsEnd', True)] if tactics else \
                  [('icm005', 'Zauberbuch', 'key battleCastSpell', mine and has_hero), ('icm006', 'Warten', 'key battleWait', mine), ('icm007', 'Verteidigen', 'key battleDefend', mine)]
        buttons += [('icm004', 'Auto-Kampf', 'key battleAutocombat', True), ('icm002', 'Rückzug', 'key battleRetreat', mine and not tactics),
                    ('icm001', 'Aufgeben', 'key battleSurrender', mine and not tactics), ('icm003', 'Optionen', 'key globalOptions', True)]
        for i, (name, label, cmd, on) in enumerate(buttons): self.art_button(p, 16 + i * 152, 864, 144, 108, name, label, cmd, on)
        self.button(p, box(1080, 864, 1224, 914), 'Einheit-Info', 'key battleOpenActiveUnit', mine)
        self.button(p, box(1080, 922, 1224, 972), 'Reihenfolge oben', 'key battleToggleQueue')
        self.text(p, 'small', 'Kampftempo', 28, 1024, 24, WHITE, 0)
        for i, name in enumerate(('Langsam', 'Normal', 'Schnell')):
            self.button(p, QRectF(190 + i * 208, 1010, 200, 58), name, f'speed {i + 1}', lit=b.get('speed', 2) == i + 1)
        self.button(p, box(830, 1010, 1224, 1068), 'Heldenwerte', 'key battleToggleHeroesStats')

    def wrap(self, s, line, room):
        out = []
        for para in s.split('\n'):
            cur = ''
            for word in para.split(' '):
                if cur and self.width('small', cur + ' ' + word, line) > room: out.append(cur); cur = word
                else: cur = f'{cur} {word}' if cur else word
            if cur: out.append(cur)
        return out
