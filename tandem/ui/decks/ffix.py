"""Final Fantasy IX on the bottom screen (Steam 377840): party, enemies, map, items, abilities, boosters.

Native port of decks/377840.html (which stays for the Firefox front end). The game's Memoria build has a status server
on 127.0.0.1:8766: /events sends the JSON state about every 150 ms, /ui/<atlas>/<sprite>.png and /map/<name>.png are
the game's own pictures, /cmd/booster/<name> switches a booster. Everything is laid out on a fixed 1240x1080 stage (the
Thor's bottom screen) and scaled to the window.

Interface for tandem_ui (see DECKS there): Deck(window), paint(painter) -> bool, close().
The functions above the class are plain Python (no Qt) and carry the logic worth testing.
"""
import json, threading, time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen, QPolygonF, QRadialGradient, QTransform

STRINGS = {
 'en': dict(waiting='Waiting for FF IX…', waiting_hint='Start Final Fantasy IX (Memoria with [ThorStatus] Enabled = 1). Reconnecting automatically.', title_screen='Title screen', title_hint='Load a save to see your party.',
            scene_field='Field', scene_world='World map', scene_battle='Battle', scene_menu='Menu', scene_cards='Tetra Master', scene_ending='Ending', scene_other='Event',
            tabs=['Auto', 'Abilities', 'Map', 'Items', 'Key items', 'Extras'], enemies='Enemies', no_enemies='No enemies in sight', no_items='Nothing here yet',
            map_loading='Loading map from your game data…', map_last='Last known position', map_schematic='Schematic map (image not available)', gil='Gil', time='Time', hp='HP', mp='MP', atb='ATB', trance='Trance', lv='Lv', fps='FPS',
            progress='Progress', used='used', ready='READY', weak='Weak', absorbs='Absorbs', immune='Immune', halves='Halves', steal='Steal', drops='Drops', nothing_left='nothing left', ap_none='The equipment teaches nothing new', ap_done='learnt',
            boosters='Boosters', boosters_off='Boosters are switched off in Memoria.ini ([Cheats] Enabled)', b_speed='High speed', b_assist='Battle assist', b_dmg='9999 damage', b_noenc='No battles', on='ON', off='OFF',
            counters='Hidden counters', c_steals='Successful steals', c_frogs='Frogs caught', c_dragons='Dragons slain', c_treasure='Treasure hunter', c_cards='Cards (won / lost / draw)', c_chocographs='Chocographs',
            c_excalibur='Excalibur II (12 h)', c_excalibur_over='time is up', rank='rank',
            st=dict(Petrify='Stone', Venom='Venom', Virus='Virus', Silence='Silence', Blind='Darkness', Trouble='Trouble', Zombie='Zombie', Death='KO', Confuse='Confuse', Berserk='Berserk', Stop='Stop', AutoLife='Auto-Life', Trance='Trance',
                    Defend='Defend', Poison='Poison', Sleep='Sleep', Regen='Regen', Haste='Haste', Slow='Slow', Float='Float', Shell='Shell', Protect='Protect', Heat='Heat', Freeze='Freeze', Vanish='Vanish', Doom='Doom', Mini='Mini',
                    Reflect='Reflect', GradualPetrify='Gradual Petrify'),
            el=dict(Fire='Fire', Cold='Ice', Thunder='Thunder', Earth='Earth', Aqua='Water', Wind='Wind', Holy='Holy', Darkness='Shadow')),
 'de': dict(waiting='Warte auf FF IX…', waiting_hint='Final Fantasy IX starten (Memoria mit [ThorStatus] Enabled = 1). Verbindet sich automatisch neu.', title_screen='Titelbildschirm', title_hint='Spielstand laden, dann erscheint die Gruppe.',
            scene_field='Feld', scene_world='Weltkarte', scene_battle='Kampf', scene_menu='Menü', scene_cards='Tetra Master', scene_ending='Abspann', scene_other='Ereignis',
            tabs=['Auto', 'Fähigk.', 'Karte', 'Items', 'Schlüssel', 'Extras'], enemies='Gegner', no_enemies='Keine Gegner in Sicht', no_items='Noch nichts vorhanden',
            map_loading='Karte wird aus deinen Spieldaten geladen…', map_last='Zuletzt bekannte Position', map_schematic='Schematische Karte (Bild nicht verfügbar)', gil='Gil', time='Zeit', hp='LP', mp='MP', atb='ATB', trance='Trance', lv='St.', fps='FPS',
            progress='Fortschritt', used='benutzt', ready='BEREIT', weak='Schwach', absorbs='Absorbiert', immune='Immun', halves='Halbiert', steal='Stehlen', drops='Beute', nothing_left='nichts mehr', ap_none='Die Ausrüstung lehrt nichts Neues', ap_done='gelernt',
            boosters='Booster', boosters_off='Booster sind in Memoria.ini abgeschaltet ([Cheats] Enabled)', b_speed='Schnelllauf', b_assist='Kampfhilfe', b_dmg='9999 Schaden', b_noenc='Keine Kämpfe', on='AN', off='AUS',
            counters='Versteckte Zähler', c_steals='Erfolgreich gestohlen', c_frogs='Frösche gefangen', c_dragons='Drachen besiegt', c_treasure='Schatzjäger', c_cards='Karten (Sieg / Niederlage / Remis)', c_chocographs='Chocografe',
            c_excalibur='Excalibur II (12 Std.)', c_excalibur_over='Zeit abgelaufen', rank='Rang',
            st=dict(Petrify='Stein', Venom='Toxin', Virus='Virus', Silence='Stumm', Blind='Blind', Trouble='Ärger', Zombie='Zombie', Death='K.O.', Confuse='Konfus', Berserk='Berserker', Stop='Stopp', AutoLife='Wiederbeleben', Trance='Trance',
                    Defend='Abwehr', Poison='Gift', Sleep='Schlaf', Regen='Regena', Haste='Hast', Slow='Gemach', Float='Levitas', Shell='Shell', Protect='Protes', Heat='Hitze', Freeze='Frost', Vanish='Unsichtbar', Doom='Countdown', Mini='Mini',
                    Reflect='Reflek', GradualPetrify='Versteinerung'),
            el=dict(Fire='Feuer', Cold='Eis', Thunder='Blitz', Earth='Erde', Aqua='Wasser', Wind='Wind', Holy='Heilig', Darkness='Schatten'))}
POSITIVE = {'AutoLife', 'Trance', 'Defend', 'Regen', 'Haste', 'Float', 'Shell', 'Protect', 'Vanish', 'Reflect'}
BOOSTERS = [('speed', 'b_speed', 'icon_ff'), ('noenc', 'b_noenc', 'icon_encounter'), ('assist', 'b_assist', 'icon_battle'), ('dmg', 'b_dmg', 'icon_9999')]
T_AUTO, T_AP, T_MAP, T_ITEMS, T_KEY, T_EXTRA, ENEMIES = 0, 1, 2, 3, 4, 5, -1
CAL, CAL_SCHEM = (0.040, 0.925, 0.963, 0.926), (0, 1, 1, 1)  # normalised game coordinates -> fractions of the map picture


def language(st): return 'en' if st and st.get('lang') not in (None, 'GR') else 'de'  # the deck speaks the game's language


def fmt_time(secs):
    secs = int(secs)
    return f'{secs // 3600}:{secs // 60 % 60:02d}:{secs % 60:02d}'


def fmt_gil(n): return f'{int(n):,}'.replace(',', '.')


def treasure_rank(points): return 'S' if points >= 340 else 'H' if points < 200 else chr(71 - (points - 200) // 20)


def view_mode(st, tab, seen_world):
    """What the panel shows: the chosen tab, or for Auto the enemies in a battle, else the map once the world map was seen."""
    if tab != T_AUTO: return tab
    return ENEMIES if st.get('battle') else T_MAP if (st.get('world') or seen_world) and st.get('scene') != 'menu' else T_ITEMS


def signature(st, mode, party_shown):
    """The part of a state that is on screen in the current view, coarse enough that changes below a pixel do not count.
    The game sends its state about seven times a second; the deck repaints only when this value changes."""
    fps = st.get('fps') or 0
    if not st.get('inGame'): return (False, round(fps / 5))
    battle = bool(st.get('battle'))
    head = (st.get('location'), st.get('scene'), st.get('scenario'), st.get('gil'), int(st.get('playTime') or 0), round(fps / 5), st.get('lang'))
    members = st.get('party') or []
    party = [(m.get('id'), m.get('name'), m.get('lv'), m.get('hp'), m.get('maxHp'), m.get('mp'), m.get('maxMp'), m.get('status'), m.get('face'), m.get('inTrance'), m.get('hasTrance'), (m.get('trance') or 0) // 2,
              battle and m.get('atb') is not None and (round(100 * m['atb'] / max(1, m.get('maxAtb') or 1)), m.get('canAct')))
             for m in members] if party_shown else None
    if mode == ENEMIES: panel = [{k: v for k, v in e.items() if k not in ('atb', 'maxAtb')} for e in st['battle'].get('enemies') or []]
    elif mode == T_MAP:
        w = st.get('world')
        panel = w and (round(w.get('x') or 0, 3), round(w.get('y') or 0, 3), round((w.get('rot') or 0) / 3), w.get('naviMap'), w.get('airship'), w.get('chocobo'))
    elif mode == T_AP: panel = [(m.get('name'), m.get('learn')) for m in members]
    elif mode == T_EXTRA: panel = (st.get('boosters'), st.get('counters'))
    else: panel = st.get('keyItems' if mode == T_KEY else 'items')
    return (head, party, panel)


def color(text, alpha=None):
    c = QColor(text)
    if alpha is not None: c.setAlphaF(alpha)
    return c


GOLD, CREAM, MUTED, HP, HPMID, HPLOW, MP, ATB, TRANCE, ENEMY, GOOD = (color(c) for c in ('#D9B45A', '#F2E8D0', '#8C93B0', '#5BD08A', '#E8C14E', '#E0556A', '#5AA9F0', '#F2D25C', '#F06BC8', '#E07A5A', '#7FD69B'))
SHADOW, TRACK, NONE = color('#000000', .8), color('#0B1022'), Qt.PenStyle.NoPen


class Deck:
    ADDR = ('127.0.0.1', 8766)

    def __init__(self, window):
        self.w = window
        self.images = window.Images(120, window.loaded, self.ADDR)  # sprites are small; the map is loaded at its size on screen
        self.memo = window.memo.setdefault('ffix', {'tab': T_AUTO, 'party_hidden': False})
        self.st = self.seen_world = self.sig = None
        self.connected, self.alive, self.skins, self.S = False, True, {}, STRINGS['de']
        threading.Thread(target=self.listen, daemon=True).start()

    def close(self):
        self.alive = False
        self.images.close()
        self.skins.clear()

    # ---- the game's state ---------------------------------------------------------------------------------------------
    def listen(self):
        raw = None
        while self.alive:
            try:
                with self.w.http('events', timeout=12, addr=self.ADDR) as stream:  # the server sends a keep-alive at least every 5 s
                    self.connected = True
                    self.changed()
                    for line in stream:
                        if not self.alive: return
                        if line == raw or not line.startswith(b'data: '): continue  # nothing new: do not even parse
                        raw = line
                        try: st = json.loads(line[6:])
                        except ValueError: continue
                        if st.get('world'): self.seen_world = st
                        self.st = st
                        sig = signature(st, self.mode(st), not self.memo['party_hidden'])
                        if sig != self.sig:
                            self.sig = sig
                            self.changed()
            except OSError: pass
            if self.connected:
                self.connected, self.st, self.sig, raw = False, None, None, None
                self.changed()
            time.sleep(1)

    def changed(self):
        if self.alive: self.w.loaded.emit()

    def mode(self, st): return view_mode(st, self.memo['tab'], self.seen_world)

    def boost(self, name):
        if not ((self.st or {}).get('boosters') or {}).get('allowed'): return
        def work():
            try: self.w.http('cmd/booster/' + name, timeout=5, addr=self.ADDR).close()
            except OSError: pass
        threading.Thread(target=work, daemon=True).start()

    def sprite(self, path): return self.images.get(f'ui/{path}.png', retry=8) or None  # asked again while the game is not ready to cut it

    # ---- drawing helpers ----------------------------------------------------------------------------------------------
    def t(self, p, text, x, y, px, col, kind='n', weight=400, w=None, align=0, lh=1.0):
        """Text with the deck's drop shadow; sizes in stage pixels. kind 'n' narrow, 's' serif."""
        f = (kind, px / self.w.u, weight)
        self.w.text(p, text, x + 2, y + 2, f, SHADOW, w, align, lh)
        return self.w.text(p, text, x, y, f, col, w, align, lh)

    def tw(self, text, px, kind='n', weight=400): return self.w.width_of(text, (kind, px / self.w.u, weight))

    def win(self, p, x, y, w, h, dark=False):
        """A window in the game's own skin (tiled paper, nine-slice frame); a plain panel until the sprites are there."""
        bg, frame = self.sprite('window/dialog_bg'), self.sprite('window/dialog_frame_info')
        if not (bg and frame): return self.w.box(p, QRectF(x, y, w, h), 18, color('#141B36', .82), color('#D9B45A', .4), 2)
        key = (round(w), round(h), dark)
        if key not in self.skins:  # composed once per size: the nine-slice costs too much for every repaint
            img = QImage(key[0], key[1], QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            q = QPainter(img)
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            inner = QRectF(8, 8, key[0] - 16, key[1] - 16)
            q.setBrushOrigin(8, 8)
            q.fillRect(inner, QBrush(bg))
            if dark: q.fillRect(inner, color('#000000', .4))
            k, b = min(frame.width(), frame.height()) * 2 // 5, 26
            sx, sy, dx, dy = [0, k, frame.width() - k, frame.width()], [0, k, frame.height() - k, frame.height()], [0, b, key[0] - b, key[0]], [0, b, key[1] - b, key[1]]
            for i in range(3):
                for j in range(3):
                    if i == 1 and j == 1: continue
                    q.drawImage(QRectF(dx[i], dy[j], dx[i + 1] - dx[i], dy[j + 1] - dy[j]), frame, QRectF(sx[i], sy[j], sx[i + 1] - sx[i], sy[j + 1] - sy[j]))
            q.end()
            self.skins[key] = img
        p.drawImage(QPointF(x, y), self.skins[key])

    def bar(self, p, x, y, w, label, value, frac, col, h, glow=False):
        """Label, value and a filled track; returns the y below it."""
        self.t(p, label, x, y, 19, MUTED, weight=700)
        if value: self.t(p, value, x, y, 21, col if glow else CREAM, w=w, align=2)
        track = QRectF(x, y + 26, w, h)
        self.w.box(p, track, h / 2, TRACK)
        frac = max(0.0, min(1.0, frac or 0))
        if frac > 0:
            g = QLinearGradient(0, track.top(), 0, track.bottom())
            g.setColorAt(0, col.lighter(135)); g.setColorAt(1, col)
            self.w.box(p, QRectF(x, y + 26, max(h, w * frac), h), h / 2, QBrush(g))
        return y + 26 + h + 8

    def chips(self, p, x, y, statuses, right):
        """Status chips from x up to right; returns the x after the last one."""
        for name in statuses or []:
            label = self.S['st'].get(name)
            if not label: continue
            w = self.tw(label, 18, weight=700) + 20
            if x + w > right: break
            col = color('#7FC8F0' if name in POSITIVE else '#E88A9A')
            self.w.box(p, QRectF(x, y, w, 26), 12, color(col.name(), .2))
            self.w.text(p, label, x, y, ('n', 18 / self.w.u, 700), col, w, 1, 26 / 18)
            x += w + 8
        return x

    def icon(self, p, path, x, y, h, opacity=1.0):
        """A sprite scaled to height h; returns its width (0 while it is not there)."""
        img = self.sprite(path)
        if not img: return 0
        w = h * img.width() / max(1, img.height())
        p.setOpacity(opacity)
        p.drawImage(QRectF(x, y, w, h), img)
        p.setOpacity(1)
        return w

    # ---- painting -----------------------------------------------------------------------------------------------------
    def paint(self, p):
        w = self.w
        s = min(w.width() / 1240, w.height() / 1080)
        xf = QTransform().translate((w.width() - 1240 * s) / 2, (w.height() - 1080 * s) / 2).scale(s, s)
        p.save()
        p.fillRect(0, 0, w.width(), w.height(), Qt.GlobalColor.black)
        p.setTransform(xf)
        p.setClipRect(QRectF(0, 0, 1240, 1080))
        w.xf, w.zoom = xf, s  # taps and drags arrive in window pixels
        try: self.draw(p)
        finally:
            w.xf, w.zoom = None, 1.0
            p.restore()
        return True

    def draw(self, p):
        st = self.st if self.connected else None
        self.S = S = STRINGS[language(st)]
        skin = bool(self.sprite('window/dialog_bg') and self.sprite('window/dialog_frame_info'))
        playing = bool(st and st.get('inGame'))
        if not (playing and skin):  # night sky with a thin frame; in the game's skin the stage is black
            g = QLinearGradient(0, 0, 0, 1080)
            g.setColorAt(0, color('#070A16')); g.setColorAt(1, color('#141C3C'))
            p.fillRect(QRectF(0, 0, 1240, 1080), QBrush(g))
            p.setPen(NONE); p.setBrush(color('#FFFFFF', .3))
            x = 9
            for _ in range(60):  # the same fixed stars as the page (they do not twinkle here: no repaint without news)
                vals = []
                for _ in range(4): x = x * 16807 % 2147483647; vals.append(x / 2147483647)
                size = .6 + vals[2] * 2.8
                p.drawEllipse(QRectF(vals[0] * 1240, vals[1] * 972, size, size))
            w = self.w
            w.box(p, QRectF(10, 10, 1220, 1060), 18, None, color('#D9B45A', .33), 2)
        if not playing:
            self.waiting(p, S['title_screen' if st else 'waiting'], S['title_hint' if st else 'waiting_hint'])
            if st: self.fps(p, st)
            return
        self.header(p, st)
        hidden = self.memo['party_hidden']
        if not hidden: self.party(p, st)
        self.tabs(p, hidden)
        self.panel(p, st, 24 if hidden else 664)

    def waiting(self, p, title, hint):
        cx, cy = 620, 480
        g = QRadialGradient(cx, cy, 162)
        g.setColorAt(0, color('#78BEFF', .55)); g.setColorAt(1, color('#78BEFF', 0))
        p.setPen(NONE); p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), 162, 162)
        g = QLinearGradient(cx - 45, cy - 90, cx + 45, cy + 90)
        g.setColorAt(0, color('#CDEBFF')); g.setColorAt(1, color('#3F7FD8'))
        p.setPen(QPen(GOLD, 3)); p.setBrush(QBrush(g))
        p.drawPolygon(QPolygonF([QPointF(cx, cy - 90), QPointF(cx + 45, cy - 4.5), QPointF(cx, cy + 90), QPointF(cx - 45, cy - 4.5)]))
        p.setPen(NONE); p.setBrush(color('#FFFFFF', .4))
        p.drawPolygon(QPolygonF([QPointF(cx, cy - 90), QPointF(cx + 16, cy - 4.5), QPointF(cx, cy + 90), QPointF(cx - 16, cy - 4.5)]))
        p.setPen(QPen(GOLD, 3)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy + 67), 85, 13)
        self.t(p, title, 0, 600, 54, CREAM, 's', 700, 1240, 1)
        f = ('n', 26 / self.w.u, 400)
        for n, row in enumerate(self.w.wrap(hint, f, 820, None)): self.t(p, row, 210, 675 + n * 34, 26, MUTED, w=820, align=1, lh=34 / 26)

    def fps(self, p, st):
        fps = st.get('fps') or 0
        p.setPen(NONE); p.setBrush(GOOD if self.connected else HPLOW)
        p.drawEllipse(QRectF(1114, 102, 12, 12))
        self.t(p, f'{round(fps)} {self.S["fps"]}', 1000, 98, 19, GOOD if fps >= 55 else HPMID if fps >= 28 else HPLOW, w=200, align=2)

    def header(self, p, st):
        S, scene = self.S, st.get('scene')
        label = S.get(f'scene_{scene}') or S['scene_other']
        where = st.get('location') or label
        self.win(p, 12, 10, 1216, 122)
        size = next((n for n in range(46, 26, -2) if self.tw(where, n, 's', 700) <= 690), 26)
        self.t(p, where, 36, 30, size, CREAM, 's', 700, 690)
        col = ENEMY if scene == 'battle' else MP if scene == 'world' else GOLD
        w = self.tw(label, 22, weight=700) + 32
        self.w.box(p, QRectF(36, 86, w, 32), 16, color(col.name(), .2), col, 2)
        self.w.text(p, label, 36, 86, ('n', 22 / self.w.u, 700), col, w, 1, 32 / 22)
        if (st.get('scenario') if st.get('scenario') is not None else -1) >= 0: self.t(p, f'{S["progress"]} {st["scenario"]}', 36 + w + 18, 92, 20, MUTED)
        self.t(p, S['gil'], 710, 30, 20, MUTED, w=300, align=2)
        self.t(p, S['time'], 900, 30, 20, MUTED, w=300, align=2)
        self.t(p, fmt_gil(st.get('gil') or 0), 710, 58, 36, GOLD, weight=700, w=300, align=2)
        self.t(p, fmt_time(st.get('playTime') or 0), 900, 58, 36, CREAM, weight=700, w=300, align=2)
        self.fps(p, st)

    def party(self, p, st):
        S, members, battle, h = self.S, st.get('party') or [], bool(st.get('battle')), 220
        for i in range(4):
            y = 140 + i * (h + 12)
            if i >= len(members):
                self.w.box(p, QRectF(24, y, 616, h), 18, color('#141B36', .25))
                continue
            m = members[i]
            status = m.get('status') or []
            ko = m.get('hp') == 0 or 'Death' in status
            self.win(p, 24, y, 616, h, ko)
            if m.get('inTrance'): self.w.box(p, QRectF(32, y + 8, 600, h - 16), 14, None, TRANCE, 4)
            x = 24
            if m.get('face'):
                fw = self.icon(p, 'face/' + m['face'], 44, y + 18, 184, .43 if ko else 1)
                if fw: x = 44 + fw
            x, right = x + 22, 640 - 22
            level = f'{S["lv"]} {m.get("lv") if m.get("lv") is not None else 1}'
            lw = self.tw(level, 24)
            name = m.get('name') or '?'
            self.t(p, name, x, y + 12, 36, MUTED if ko else CREAM, 's', 700, right - lw - 14 - x)
            self.chips(p, x + min(self.tw(name, 36, 's', 700), right - lw - 14 - x) + 18, y + 20, status, right - lw - 14)
            self.t(p, level, right - lw, y + 22, 24, GOLD)
            maxhp, maxmp, maxatb = max(1, m.get('maxHp') or 1), max(1, m.get('maxMp') or 1), max(1, m.get('maxAtb') or 1)
            part = (m.get('hp') or 0) / maxhp
            by = self.bar(p, x, y + 64, right - x, S['hp'], f'{m.get("hp") or 0} / {maxhp}', part, HPLOW if part < .25 else HPMID if part < .5 else HP, 20)
            by = self.bar(p, x, by, right - x, S['mp'], f'{m.get("mp") or 0} / {maxmp}', (m.get('mp') or 0) / maxmp, MP, 14)
            fighting = battle and m.get('atb') is not None
            trance = m.get('hasTrance') or (m.get('trance') or 0) > 0
            half = (right - x - 16) / 2
            if fighting:
                ready = m['atb'] >= maxatb and m.get('canAct') is not False
                self.bar(p, x, by, half if trance else right - x, S['atb'], S['ready'] if ready else '', m['atb'] / maxatb, ATB, 12, ready)
            if trance:
                full = bool(m.get('inTrance')) or (m.get('trance') or 0) >= 255
                self.bar(p, x + half + 16 if fighting else x, by, half if fighting else right - x, S['trance'], '!!' if m.get('inTrance') else '', (m.get('trance') or 0) / 255, TRANCE, 12, full)

    def tabs(self, p, hidden):
        left, w = 24 if hidden else 664, ((1136 - (24 if hidden else 664)) - 30) / 6
        def tab(x, width, label, on, fn, px=19):
            rect = QRectF(x, 140, width, 150)
            self.w.box(p, rect, 14, color('#2A3360') if on else color('#141B36', .56), GOLD if on else None, 2)
            self.w.text(p, label, x, 140, ('n', px / self.w.u, 700), GOLD if on or px > 19 else MUTED, width, 1, 150 / px)
            self.w.hit(rect, fn, name=label)
        def choose(i): self.memo['tab'] = i
        def toggle(): self.memo['party_hidden'] = not self.memo['party_hidden']
        for i, label in enumerate(self.S['tabs']): tab(left + i * (w + 6), w, label, self.memo['tab'] == i, lambda i=i: choose(i))
        tab(1144, 72, '»' if hidden else '«', False, toggle, 44)

    def panel(self, p, st, left):
        top, right, bottom = 302, 1216, 1056
        self.win(p, left, top, right - left, bottom - top)
        pad = 10 if self.skins else 0
        x, y, W, H = left + pad, top + pad, right - left - 2 * pad, bottom - top - 2 * pad
        mode, area = self.mode(st), QRectF(x, y, W, H)
        if mode in (ENEMIES, T_MAP):
            p.save(); p.setClipRect(area)
            (self.enemies if mode == ENEMIES else self.map)(p, st, x, y, W, H)
            return p.restore()
        draw = {T_AP: self.abilities, T_EXTRA: self.extras}.get(mode) or (lambda p, st, x, y, W: self.items(p, st.get('keyItems' if mode == T_KEY else 'items') or [], mode == T_KEY, x, y, W))
        self.w.scroller(p, f'ffix{mode}', area, lambda y0: draw(p, st, x, y0, W))  # each list keeps its own position

    def items(self, p, items, key, x, y, W):
        S = self.S
        if not items:
            self.t(p, S['no_items'], x + 22, y + 22, 24, MUTED)
            return y + 60
        y += 14
        for n, it in enumerate(items):
            if n % 2 == 0: self.w.box(p, QRectF(x + 8, y, W - 16, 48), 10, color('#FFFFFF', .13))
            tx = x + 24
            if it.get('icon'):
                iw = self.icon(p, 'icon/' + it['icon'], tx, y + 5, 38)
                tx += max(30, iw) + 12 if iw else 0
            value = (S['used'] if it.get('used') else '◆') if key else f'× {it.get("n") or 0}'
            vw = self.tw(value, 26)
            self.t(p, it.get('name') or '', tx, y + 11, 26, MUTED if key and it.get('used') else CREAM, w=x + W - 24 - vw - 12 - tx)
            self.t(p, value, x + W - 24 - vw, y + 11, 26, GOLD)
            y += 48
        return y + 14

    def abilities(self, p, st, x, y, W):
        S = self.S
        for m in st.get('party') or []:
            self.t(p, m.get('name') or '?', x + 22, y + 16, 28, GOLD, 's', 700)
            y += 46
            if not m.get('learn'):
                self.t(p, S['ap_none'], x + 22, y + 11, 21, MUTED, w=W - 44)
                y += 44
            for a in m.get('learn') or []:
                done = bool(a.get('done'))
                tx = x + 22
                iw = 0 if a.get('support') else self.icon(p, 'icon/ability_stone', tx, y + 6, 32)
                if iw: tx += 48
                else:
                    p.setPen(NONE); p.setBrush(color('#7FC8F0' if a.get('support') else '#E0556A'))
                    p.drawEllipse(QRectF(tx + 10, y + 13, 18, 18))
                    tx += 40
                self.t(p, a.get('name') or '', tx, y + 10, 24, MUTED if done else CREAM, w=x + W - 22 - 110 - 14 - 140 - 14 - tx)
                track = QRectF(x + W - 22 - 110 - 14 - 140, y + 13, 140, 18)
                self.w.box(p, track, 9, TRACK)
                part = 1 if done else min(1, (a.get('ap') or 0) / max(1, a.get('max') or 1))
                if part > 0: self.w.box(p, QRectF(track.x(), track.y(), max(18, 140 * part), 18), 9, GOLD if done else color('#58C8F0'))
                self.t(p, f'★ {S["ap_done"]}' if done else f'{a.get("ap") or 0} / {a.get("max") or 0}', x + W - 22 - 110, y + 11, 21, GOLD if done else CREAM, w=110, align=2)
                y += 44
        return y + 10

    def enemies(self, p, st, x, y, W, H):
        S, foes = self.S, st['battle'].get('enemies') or []
        self.t(p, S['enemies'], x + 22, y + 12, 30, ENEMY, 's', 700)
        if not foes: return self.t(p, S['no_enemies'], x + 22, y + 68, 24, MUTED)
        h = min(250, (H - 74) / len(foes))
        compact, y = h < 100, y + 64
        names = lambda kind: ', '.join(S['el'].get(n, n) for n in kind or [])
        for e in foes:
            card = QRectF(x + 14, y, W - 28, h - 10)
            self.w.box(p, card, 14, color('#000000', .38))
            p.save(); p.setClipRect(card)
            cx, cw, size, maxhp = card.x() + 16, card.width() - 32, min(28, h * .26), max(1, e.get('maxHp') or 1)
            self.t(p, e.get('name') or '?', cx, y + min(36, h * .32) - size * .8, size, CREAM, 's', 700, cw)
            ly = self.bar(p, cx, y + min(54, h * .42) - 8, cw, S['hp'], '' if compact else f'{e.get("hp") or 0} / {maxhp}', (e.get('hp') or 0) / maxhp, ENEMY, 10 if compact else 14)
            def line(label, value, col):  # scan and steal information, one line each
                nonlocal ly
                if value:
                    lw = self.tw(label, 19, weight=700) + 12
                    self.t(p, label, cx, ly + 5, 19, MUTED, weight=700)
                    self.t(p, value, cx + lw, ly + 3, 22, col, w=cw - lw)
                ly += 28
            if not compact and 'weak' in e and h >= 150:
                used, limit = min(54, h * .42) - 8 + 48 + 22 + 28, h - 34  # the same cut-offs as the page, measured from the card's top
                line(S['weak'], names(e.get('weak')), color('#FFD27A'))
                resist = ' · '.join(f'{S[k]} {names(e.get(f))}' for k, f in (('absorbs', 'absorb'), ('immune', 'immune'), ('halves', 'half')) if e.get(f))
                if resist and used < h - 40:
                    self.t(p, resist, cx, ly + 3, 22, MUTED, w=cw)
                    ly += 28; used += 28
                if used < limit:
                    line(S['steal'], ', '.join(e.get('steal') or []) or S['nothing_left'], color('#9FE0A8'))
                    used += 28
                if used < limit and e.get('drop'): line(S['drops'], ', '.join(e['drop']), CREAM)
            elif not compact: self.chips(p, cx, ly - 2, e.get('status'), cx + cw)
            p.restore()
            y += h

    def extras(self, p, st, x, y, W):
        S, bo, co = self.S, st.get('boosters'), st.get('counters')
        self.t(p, S['boosters'], x + 22, y + 12, 28, GOLD, 's', 700)
        if not bo or not co: return y + 62
        bw = (W - 58) / 2
        for i, (name, label, icon) in enumerate(BOOSTERS):
            on = bool(bo.get(name))
            rect = QRectF(x + 22 + (i % 2) * (bw + 14), y + 62 + (i // 2) * 162, bw, 150)
            self.w.box(p, rect, 14, color('#245A38', .75) if on else color('#000000', .56), GOOD if on else color('#FFFFFF', .4), 3 if on else 2)
            text = S[label] + (f' ×{bo["speedFactor"]}' if name == 'speed' and (bo.get('speedFactor') or 0) > 1 else '')
            self.t(p, text, rect.x() + 24, rect.y() + 50, 22, CREAM if on and bo.get('allowed') else MUTED, weight=700, w=bw - 90)
            self.t(p, S['on' if on else 'off'], rect.x() + 24, rect.y() + 80, 20, GOOD if on else MUTED)
            self.icon(p, 'icon/' + icon, rect.right() - 18 - 40, rect.y() + 55, 40, 1 if on else .47)
            self.w.hit(rect, lambda name=name: self.boost(name), name=name)
        y += 62 + 2 * 162 + 8
        if not bo.get('allowed'):
            self.t(p, S['boosters_off'], x + 22, y, 19, HPMID, w=W - 44)
            y += 27
        self.t(p, S['counters'], x + 22, y + 6, 28, GOLD, 's', 700)
        y += 42
        treasure, left = co.get('treasure') or 0, 12 * 3600 - (st.get('playTime') or 0)
        rows = [(S['c_excalibur'], fmt_time(left) if left > 0 else S['c_excalibur_over']), (S['c_steals'], co.get('steals') or 0), (S['c_frogs'], co.get('frogs') or 0), (S['c_dragons'], co.get('dragons') or 0),
                (S['c_treasure'], f'{S["rank"]} {treasure_rank(treasure)} · {treasure}'), (S['c_chocographs'], f'{co.get("chocographs") or 0} / 24'),
                (S['c_cards'], f'{co.get("cardWins") or 0} / {co.get("cardLosses") or 0} / {co.get("cardDraws") or 0}')]
        for n, (label, value) in enumerate(rows):
            if n % 2: self.w.box(p, QRectF(x + 8, y, W - 16, 42), 10, color('#FFFFFF', .13))
            over = n == 0 and left <= 0
            vw = self.tw(str(value), 23)
            self.t(p, label, x + 24, y + 10, 23, MUTED if over else CREAM, w=W - 60 - vw)
            self.t(p, str(value), x + W - 24 - vw, y + 10, 23, MUTED if over else GOLD)
            y += 42
        return y + 10

    def map(self, p, st, x, y, W, H):
        S = self.S
        live = st.get('world')
        world = live or (self.seen_world or {}).get('world')
        aw, ah = W - 32, H - 72
        img = self.images.get(f'map/{"mist" if world and world.get("naviMap") == 0 else "world"}.png', aw, ah, cover=False, retry=15)  # decoded at the size shown
        dw, dh = (img.width(), img.height()) if img else (1536 * min(aw / 1536, ah / 1280), 1280 * min(aw / 1536, ah / 1280))
        dx, dy = x + 16 + (aw - dw) / 2, y + 16 + (ah - dh) / 2
        frame = QRectF(dx, dy, dw, dh)
        if img: p.drawImage(QPointF(dx, dy), img)
        else:  # no picture (yet): a schematic sea chart
            g = QLinearGradient(frame.topLeft(), frame.bottomRight())
            g.setColorAt(0, color('#0E2546')); g.setColorAt(1, color('#0A1830'))
            p.fillRect(frame, QBrush(g))
            p.setPen(QPen(color('#4A78B8', .2), 1))
            for n in range(1, 12): p.drawLine(QPointF(dx + dw * n / 12, dy), QPointF(dx + dw * n / 12, dy + dh))
            for n in range(1, 10): p.drawLine(QPointF(dx, dy + dh * n / 10), QPointF(dx + dw, dy + dh * n / 10))
        self.w.box(p, frame, 0, None, color('#D9B45A', .4), 2)
        if world:
            cal = CAL if img else CAL_SCHEM
            at = lambda o: QPointF(dx + dw * (cal[0] + cal[1] * (o.get('x') or 0)), dy + dh * (cal[2] - cal[3] * (o.get('y') or 0)))
            for what, col in (('airship', '#7FE0FF'), ('chocobo', '#F2D25C')):
                if world.get(what):
                    p.setPen(QPen(color('#000000', .67), 3)); p.setBrush(color(col))
                    p.drawEllipse(at(world[what]), 9, 9)
            here = at(world)
            p.setPen(NONE); p.setBrush(color('#FFDC78', .35 if live else .18))  # the page lets it pulse; here it rests
            p.drawEllipse(here, 26, 26)
            p.save()
            p.translate(here); p.rotate(world.get('rot') or 0)
            p.setPen(QPen(color('#3A2A00'), 2.5)); p.setBrush(color('#FFE9A8'))
            p.drawPolygon(QPolygonF([QPointF(0, -18), QPointF(11, 12), QPointF(0, 6), QPointF(-11, 12)]))
            p.restore()
        caption = (S['map_schematic'] if img is False else S['map_loading']) if not img else S['map_last'] if not live and world else ''
        if caption: self.t(p, caption, x + 20, y + H - 33, 21, MUTED)
