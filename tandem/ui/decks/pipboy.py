"""Pip-Boy for Fallout 4 on the bottom screen (Steam 377160): STAT, INV, DATA, MAP, RADIO, FAV; tap = equip / use.

Native port of the owner's Android app "Thor Pip-Boy" (PipBoyView.java): green phosphor screen, everything drawn here,
no game graphics. The data comes from the F4SE plugin ThorPipBoy.dll inside the game: a WebSocket server on
127.0.0.1:8767 with JSON messages (subscribe -> data, command -> commandResult, heartbeat). Sizes follow the app: the
unit `u` is a thirtieth of the screen's shorter side.

Interface for tandem_ui (see DECKS there): Deck(window), paint(painter) -> bool, close().
The functions above the class are plain Python (no Qt) and carry the logic worth testing.
"""
import base64, json, math, os, socket, struct, threading, time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainterPath, QPen, QPolygonF, QRadialGradient

STRINGS = {
 'en': dict(waiting='WAITING FOR FALLOUT 4…', waiting_hint='Start the game with F4SE. The ThorPipBoy plugin listens on 127.0.0.1:8767.', loading='CONNECTED – WAITING FOR SAVE GAME…',
            tabs=['STAT', 'INV', 'DATA', 'MAP', 'RADIO', 'FAV'],
            subs=[['STATUS', 'S.P.E.C.I.A.L.'], ['WEAPONS', 'APPAREL', 'AID', 'MISC', 'JUNK', 'AMMO'], ['QUESTS', 'WORLD'], ['WORLD MAP'], ['STATIONS'], ['QUICK KEYS 1–12']], localmap='LOCAL MAP',
            special=['Strength', 'Perception', 'Endurance', 'Charisma', 'Intelligence', 'Agility', 'Luck'], hp='HP', ap='AP', level='LEVEL', rads='RADS', caps='CAPS', weight='WEIGHT', col_wt='WT', col_val='VAL',
            empty='– nothing here –', no_quests='No active objectives.', equipped='Equipped: {}', unequipped='Unequipped: {}', used='Used: {}', no_action='{} – no action', failed='Failed ({})',
            radio_on='RADIO ON', radio_off='RADIO OFF', radio_none='No stations received yet.', location='LOCATION', cell='CELL', worldspace='WORLDSPACE', interior='Interior', position='POSITION', date='DATE',
            map_interior='Inside: {}', map_nodata='No map data – showing position only.', map_zoom='Tap to zoom', dr='DR', er='ER', rr='RES', stimpak='Stimpak', radaway='RadAway', none_left='No {} left',
            no_favorites='No favorites yet – mark items in the in-game Pip-Boy (Favorite).'),
 'de': dict(waiting='WARTE AUF FALLOUT 4…', waiting_hint='Spiel mit F4SE starten. Das ThorPipBoy-Plugin lauscht auf 127.0.0.1:8767.', loading='VERBUNDEN – WARTE AUF SPIELSTAND…',
            tabs=['STAT', 'INV', 'DATEN', 'KARTE', 'RADIO', 'FAV'],
            subs=[['STATUS', 'S.P.E.C.I.A.L.'], ['WAFFEN', 'KLEIDUNG', 'HILFE', 'VERSCH.', 'SCHROTT', 'MUNITION'], ['QUESTS', 'WELT'], ['WELTKARTE'], ['SENDER'], ['SCHNELLTASTEN 1–12']], localmap='LOKALE KARTE',
            special=['Stärke', 'Wahrnehmung', 'Ausdauer', 'Charisma', 'Intelligenz', 'Beweglichkeit', 'Glück'], hp='TP', ap='AP', level='STUFE', rads='RADS', caps='KRONKORKEN', weight='GEWICHT', col_wt='GEW', col_val='WERT',
            empty='– nichts vorhanden –', no_quests='Keine aktiven Ziele.', equipped='Ausgerüstet: {}', unequipped='Abgelegt: {}', used='Benutzt: {}', no_action='{} – keine Aktion', failed='Fehlgeschlagen ({})',
            radio_on='RADIO AN', radio_off='RADIO AUS', radio_none='Noch keine Sender empfangen.', location='ORT', cell='ZELLE', worldspace='WELTRAUM', interior='Innenraum', position='POSITION', date='DATUM',
            map_interior='Innen: {}', map_nodata='Keine Kartendaten – nur Position.', map_zoom='Tippen zum Zoomen', dr='SW', er='EW', rr='STRW', stimpak='Stimpak', radaway='RadAway', none_left='Kein {} mehr',
            no_favorites='Noch keine Favoriten – im Spiel-Pip-Boy Gegenstände als Favorit markieren.')}
SUBSCRIPTIONS = [('main', 400, ['game', 'player.stats', 'player.special', 'player.limbs', 'player.location', 'world.time']), ('inv', 1000, ['player.inventory']),
                 ('quests', 2000, ['player.quests', 'pipboy.Quests']), ('radio', 1500, ['radio']), ('map', 2500, ['pipboy.Map'])]  # as the app asks: name, interval in ms, keys
INV_TYPES = [('weapon',), ('apparel',), ('aid',), ('book', 'holotape', 'key', 'misc'), ('junk',), ('ammo',)]  # the INV sub tabs
STIMPAK, RADAWAY = '0x00023736', '0x00023742'  # base form ids in Fallout4.esm, as the plugin reports them
T_STAT, T_INV, T_DATA, T_MAP, T_RADIO, T_FAV = range(6)


def language(d): return 'en' if str((d.get('game') or {}).get('lang') or 'de').lower()[:2] != 'de' else 'de'  # German unless the game data names another language


def num(o, *keys):
    """The first of the keys that the object has, as a number (the game's model writes X or x); None if there is none."""
    for k in keys:
        if isinstance(o, dict) and isinstance(o.get(k), (int, float)): return o[k]
    return None


def fmt_weight(w): return '–' if w <= 0 else str(round(w)) if w >= 10 else f'{w:.1f}'


def date_string(t):
    if not t: return '–'
    year, hour = int(t.get('year') or 0), t.get('hour') or 0  # the game stores 287 for 2287; the month is 1-based
    return f'{int(t.get("day") or 0):02d}.{int(t.get("month") or 0):02d}.{year + 2000 if year < 1000 else year}  {int(hour):02d}:{int((hour - int(hour)) * 60):02d}'


def inventory_of(d, sub):
    """The INV list of one sub tab: worn or drawn items first, then by name."""
    items = [o for o in d.get('player.inventory') or [] if isinstance(o, dict) and o.get('type') in INV_TYPES[sub]]
    return sorted(items, key=lambda o: (not o.get('equipped'), str(o.get('name') or '').lower()))


def favourites(d):
    """Quick keys 1–12 and the Stimpak / RadAway buttons: (slots, stimpak item, its count, radaway item, its count)."""
    slots, stim, rad, stim_n, rad_n = [None] * 12, None, None, 0, 0
    for o in d.get('player.inventory') or []:
        if not isinstance(o, dict): continue
        fav = o.get('fav')
        if isinstance(fav, int) and 0 <= fav < 12: slots[fav] = o
        if o.get('id') == STIMPAK: stim, stim_n = stim or o, stim_n + (o.get('count') or 0)
        if o.get('id') == RADAWAY: rad, rad_n = rad or o, rad_n + (o.get('count') or 0)
    return slots, stim, stim_n, rad, rad_n


def quest_groups(d):
    """[(quest name, is active, [(objective, state)])] from the game's own Pip-Boy model (active quest first, open
    objectives first); if that is empty, from the plain objective list."""
    out = []
    pip = [q for q in d.get('pipboy.Quests') or [] if isinstance(q, dict)]
    if pip:
        for q in sorted(pip, key=lambda q: (not q.get('active'), not q.get('enabled'))):
            goals = [(o.get('text'), 'failed' if o.get('failed') else 'completed' if o.get('completed') else 'active') for o in q.get('objectives') or [] if isinstance(o, dict) and str(o.get('text') or '').strip()]
            out.append((q.get('text') or '', bool(q.get('active')), sorted(goals, key=lambda g: g[1] != 'active')))
        return out
    groups = {}
    for o in d.get('player.quests') or []:
        if isinstance(o, dict) and str(o.get('objective') or '').strip(): groups.setdefault(o.get('quest') or '', []).append((o['objective'], o.get('state') or ''))
    return [(name, any(state == 'active' for _, state in goals), goals) for name, goals in groups.items()]


def visible(d, tab, sub):
    """What of the game data is on screen in this view, coarse enough that changes below a pixel or a digit do not
    count. The plugin reports several times a second (health regenerates, the player walks); the deck repaints only
    when this value changes."""
    game, stats = d.get('game') or {}, d.get('player.stats') or {}
    if not (game.get('ready') and game.get('player')): return (False,)
    whole = lambda *keys: tuple(int(stats.get(k) or 0) for k in keys)
    foot = whole('hp', 'hpMax', 'ap', 'apMax', 'level') + (round((stats.get('xpProgress') or 0) * 200),)
    place = d.get('player.location') or {}
    if tab == T_STAT:
        limbs = d.get('player.limbs') or {}
        view = (d.get('player.special'),) if sub else (stats.get('name'), whole('rads', 'damageResist', 'energyResist', 'radResist'),
                                                       [(k, round((v.get('value') or 0) / (v.get('max') or 100), 2), v.get('crippled')) for k, v in sorted(limbs.items()) if isinstance(v, dict)])
    elif tab == T_INV: view = inventory_of(d, sub)
    elif tab == T_DATA: view = (date_string(d.get('world.time')), place.get('location'), place.get('cell'), place.get('interior'), place.get('worldspace'),
                                tuple(round(place.get(k) or 0) for k in 'xyz'), whole('caps', 'weight', 'weightMax')) if sub else quest_groups(d)
    elif tab == T_MAP:
        world = (d.get('pipboy.Map') or {}).get('Local' if place.get('interior') else 'World') or {}
        me = world.get('Player') or {}
        coarse = lambda v, step: None if v is None else round(v / step)
        view = (place.get('interior'), place.get('cell'), place.get('location'), {k: v for k, v in world.items() if k != 'Player'}, coarse(num(me, 'X', 'x'), 40), coarse(num(me, 'Y', 'y'), 40), coarse(num(me, 'Rotation', 'rotation'), 3),
                None if me else (coarse(place.get('x'), 40), coarse(place.get('y'), 40), coarse(place.get('heading'), .05)))
    elif tab == T_RADIO: view = d.get('radio')
    else: view = favourites(d)
    return (True, foot, view)


def ws_frame(text, mask=None):
    """One masked text frame, as a client has to send it (RFC 6455)."""
    data, mask = text.encode(), mask or os.urandom(4)
    head = bytes([0x81, 0x80 | len(data)]) if len(data) < 126 else bytes([0x81, 0x80 | 126]) + struct.pack('>H', len(data)) if len(data) < 65536 else bytes([0x81, 0x80 | 127]) + struct.pack('>Q', len(data))
    return head + mask + bytes(b ^ mask[i & 3] for i, b in enumerate(data))


def ws_frames(buf):
    """Takes the complete frames off the front of the buffer: ([(fin, opcode, payload)], rest)."""
    out = []
    while len(buf) >= 2:
        size, at = buf[1] & 0x7F, 2
        if size == 126:
            if len(buf) < 4: break
            size, at = struct.unpack('>H', buf[2:4])[0], 4
        elif size == 127:
            if len(buf) < 10: break
            size, at = struct.unpack('>Q', buf[2:10])[0], 10
        if size > 64 << 20: raise OSError('Frame zu groß')
        mask = buf[at:at + 4] if buf[1] & 0x80 else b''
        at += len(mask)
        if len(buf) < at + size: break
        payload = buf[at:at + size]
        out.append((bool(buf[0] & 0x80), buf[0] & 0x0F, bytes(b ^ mask[i & 3] for i, b in enumerate(payload)) if mask else bytes(payload)))
        buf = buf[at + size:]
    return out, buf


def color(rgb, alpha=255): return QColor((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255, alpha)


G, G_DIM, G_FAINT, BG, BG_HI = color(0x1AFF80), color(0x1AFF80, 0x66), color(0x1AFF80, 0x2A), color(0x040C06), color(0x0C2A16)


class Deck:
    ADDR = ('127.0.0.1', 8767)

    def __init__(self, window):
        self.w = window
        self.memo = window.memo.setdefault('pipboy', {'tab': 0, 'sub': [0] * 6, 'zoom': False})  # the chosen tabs outlive the game
        self.d, self.connected, self.ready, self.alive, self.sock, self.lock = {}, False, False, True, None, threading.Lock()
        self.pending, self.toast, self.toast_until, self.seq, self.sig, self.S, self.u, self.lines = {}, '', 0, 0, None, STRINGS['de'], 36.0, None
        threading.Thread(target=self.listen, daemon=True).start()

    def close(self):
        self.alive = False
        self.hang_up()

    # ---- the game's data ----------------------------------------------------------------------------------------------
    def listen(self):
        while self.alive:
            try: self.session()
            except (OSError, ValueError): pass
            self.hang_up()
            if self.connected:
                self.connected = self.ready = False
                self.changed()
            time.sleep(1.5)

    def session(self):
        sock = socket.create_connection(self.ADDR, timeout=1.5)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(2)  # every two seconds without news: a heartbeat, so the server answers at least that
        sock.sendall(f'GET / HTTP/1.1\r\nHost: {self.ADDR[0]}:{self.ADDR[1]}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                     f'Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            chunk = sock.recv(4096)
            if not chunk or len(buf) > 8192: raise OSError('kein WebSocket')
            buf += chunk
        head, buf = buf.split(b'\r\n\r\n', 1)
        if not head.startswith(b'HTTP/1.1 101'): raise OSError('kein WebSocket')
        self.sock, self.connected, self.d, self.sig = sock, True, {}, None
        self.changed()
        for name, every, keys in SUBSCRIPTIONS: self.send({'type': 'subscribe', 'id': name, 'settings': {'frequency': every, 'sendOnChange': True}, 'fields': keys})
        heard, beat, text = time.time(), time.time(), b''
        while self.alive:
            try: chunk = sock.recv(65536)
            except socket.timeout: chunk = None
            now = time.time()
            if chunk == b'' or now - heard > 10: raise OSError('Verbindung still')
            if now - beat >= 2:
                beat = now
                self.send({'type': 'heartbeat'})
            if not chunk: continue
            heard = now
            frames, buf = ws_frames(buf + chunk)
            for fin, op, payload in frames:
                if op == 8: raise OSError('Server hat geschlossen')
                if op == 9:
                    with self.lock: sock.sendall(bytes([0x8A, 0x80 | len(payload)]) + b'\0\0\0\0' + payload)  # pong (mask of zeros)
                if op > 2: continue
                text += payload
                if fin:
                    try: self.message(json.loads(text))
                    except ValueError: pass
                    text = b''

    def message(self, m):
        kind = m.get('type')
        if kind == 'hello': self.ready = bool(m.get('ready'))
        elif kind == 'data' and isinstance(m.get('data'), dict):
            self.d = {**self.d, **m['data']}  # a new dict each time: the painting thread reads the old one to its end
            if 'game' in m['data']: self.ready = bool((self.d.get('game') or {}).get('ready') and (self.d.get('game') or {}).get('player'))
        elif kind == 'commandResult':
            name, S, result = self.pending.pop(m.get('id'), ''), self.S, m.get('result') if isinstance(m.get('result'), dict) else {}
            action = result.get('action')
            if not m.get('success'): self.say(S['failed'].format(m.get('error') or ''))
            elif action == 'used': self.say(S['used'].format(name))
            elif action == 'unequipped': self.say(S['unequipped'].format(name))
            elif action in ('equipped', 'already_equipped'): self.say(S['equipped'].format(name))
            elif m.get('command') == 'radio' and result: self.say(S['radio_on' if result.get('enabled') else 'radio_off'])
            return
        else: return
        sig = (self.ready, visible(self.d, self.memo['tab'], self.memo['sub'][self.memo['tab']]))
        if sig != self.sig:
            self.sig = sig
            self.changed()

    def send(self, message):
        with self.lock:
            try: self.sock.sendall(ws_frame(json.dumps(message)))
            except (OSError, AttributeError): pass

    def hang_up(self):
        sock, self.sock = self.sock, None
        if sock:
            try: sock.close()
            except OSError: pass

    def changed(self):
        if self.alive: self.w.loaded.emit()

    def command(self, name, params, label=''):
        self.seq += 1
        self.pending[f'c{self.seq}'] = label
        threading.Thread(target=self.send, args=({'type': 'command', 'id': f'c{self.seq}', 'command': name, 'params': params},), daemon=True).start()  # never write to the net from the painting thread

    def item(self, o, how='toggle'): self.command(how, {'id': o.get('id'), 'stack': o.get('stack') or 0}, o.get('name') or '')

    def say(self, text):
        self.toast, self.toast_until = text, time.time() + 2.5
        self.changed()
        timer = threading.Timer(2.6, self.changed)  # one more repaint, to take it away
        timer.daemon = True
        timer.start()

    # ---- drawing helpers (y is the text's baseline, as in the app) ------------------------------------------------------
    def txt(self, p, text, x, y, size, align=0, col=G, glow=False):
        font, fm = self.w.font('m', size / self.w.u, 700)
        text = str(text)
        x -= fm.horizontalAdvance(text) * (align / 2)
        p.setFont(font)
        if glow:  # the phosphor's glow: the same text, faint, a little off in four directions
            p.setPen(QColor(col.red(), col.green(), col.blue(), 0x38))
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)): p.drawText(QPointF(x + dx, y + dy), text)
        p.setPen(col)
        p.drawText(QPointF(x, y), text)

    def width(self, text, size): return self.w.font('m', size / self.w.u, 700)[1].horizontalAdvance(str(text))

    def fit(self, text, room, size): return self.w.font('m', size / self.w.u, 700)[1].elidedText(str(text), Qt.TextElideMode.ElideRight, room)

    def frame(self, p, rect, col=G, width=1.0, fill=None):
        p.setPen(QPen(col, width) if col else Qt.PenStyle.NoPen)
        p.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
        p.drawRect(rect)

    def line(self, p, x1, y1, x2, y2, col=G, width=1.0, round_caps=False):
        p.setPen(QPen(col, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap if round_caps else Qt.PenCapStyle.FlatCap))
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def scrollbar(self, p, key, area):
        most = self.w.maxoff.get(key, 0)
        if most <= 0: return
        h = max(self.u, area.height() * area.height() / (area.height() + most))
        p.fillRect(QRectF(area.right() - self.u * .25, area.top() + (area.height() - h) * self.w.off.get(key, 0) / most, self.u * .25, h), G_DIM)

    # ---- painting -----------------------------------------------------------------------------------------------------
    def paint(self, p):
        W, H, d, memo = self.w.width(), self.w.height(), self.d, self.memo
        self.u = u = min(W, H) / 30
        self.S = STRINGS[language(d)]
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, color(0x06160B)); g.setColorAt(1, color(0x020703))
        p.fillRect(QRectF(0, 0, W, H), QBrush(g))
        pad = u * 1.2
        if not (self.connected and self.ready): self.waiting(p, W, H)
        else:
            self.tabs(p, pad, pad, W - pad, u * 2.4)
            sub_top = pad + u * 2.7
            self.subtabs(p, d, pad, sub_top, W - pad, u * 2)
            foot = u * 2.4
            area = QRectF(pad, sub_top + u * 2.6, W - 2 * pad, H - pad - foot - u * .6 - (sub_top + u * 2.6))
            p.save(); p.setClipRect(area)
            (self.stat, self.inv, self.data, self.map, self.radio, self.fav)[memo['tab']](p, d, area)
            p.restore()
            self.footer(p, d, pad, H - pad - foot, W - pad, foot)
            if self.toast and time.time() < self.toast_until: self.draw_toast(p, W, area.bottom() - (u * 3.4 if memo['tab'] == T_FAV else 0))  # FAV: above the Stimpak / RadAway buttons
        if self.lines is None:  # scan lines: every third row a little darker
            row = QImage(1, 3, QImage.Format.Format_ARGB32_Premultiplied)
            row.fill(Qt.GlobalColor.transparent); row.setPixelColor(0, 0, QColor(0, 0, 0, 0x22))
            self.lines = QBrush(row)
        p.fillRect(QRectF(0, 0, W, H), self.lines)
        g = QRadialGradient(W / 2, H / 2, max(W, H) * .72)  # the tube darkens towards its corners
        g.setColorAt(0, QColor(0, 0, 0, 0)); g.setColorAt(.6, QColor(0, 0, 0, 0)); g.setColorAt(1, QColor(0, 0, 0, 0x99))
        p.fillRect(QRectF(0, 0, W, H), QBrush(g))
        return True

    def waiting(self, p, W, H):  # the app lets the ring turn and the cursor blink; here it rests, to leave the processor to the game
        u, cx, cy, S = self.u, W / 2, H / 2, self.S
        ring = QRectF(cx - u * 4, cy - u * 7, u * 8, u * 8)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(G_DIM, u * .25)); p.drawEllipse(ring)
        p.setPen(QPen(G, u * .25)); p.drawArc(ring, 60 * 16, 70 * 16)
        self.txt(p, S['loading' if self.connected else 'waiting'] + '_', cx, cy + u * 3.5, u * 1.5, 1, G, True)
        size = u * .8
        while size > u * .4 and self.width(S['waiting_hint'], size) > W - u * 2: size *= .95
        self.txt(p, S['waiting_hint'], cx, cy + u * 5.6, size, 1, G_DIM)

    def tabs(self, p, left, top, right, h):
        u, names, memo = self.u, self.S['tabs'], self.memo
        cw, base = (right - left) / len(names), top + h - u * .2
        def choose(i): memo['tab'] = i
        for i, name in enumerate(names):
            cx = left + cw * (i + .5)
            self.txt(p, name, cx, top + h * .68, u * 1.25, 1, G if i == memo['tab'] else G_DIM, i == memo['tab'])
            if i == memo['tab']: a, b = cx - self.width(name, u * 1.25) / 2 - u * .6, cx + self.width(name, u * 1.25) / 2 + u * .6
            self.w.hit(QRectF(left + cw * i, top, cw, h + u), lambda i=i: choose(i), name=name)
        ln = lambda x1, y1, x2, y2: self.line(p, x1, y1, x2, y2, G, u * .14)  # the Pip-Boy's line with a bracket around the active tab
        ln(left, base, a, base); ln(b, base, right, base); ln(a, base, a, top + u * .2); ln(b, base, b, top + u * .2)
        ln(a, top + u * .2, a + u * .6, top + u * .2); ln(b, top + u * .2, b - u * .6, top + u * .2); ln(left, base, left, base + u * .6); ln(right, base, right, base + u * .6)

    def subtabs(self, p, d, left, top, right, h):
        u, memo = self.u, self.memo
        tab = memo['tab']
        names = [self.S['localmap']] if tab == T_MAP and (d.get('player.location') or {}).get('interior') else self.S['subs'][tab]
        if memo['sub'][tab] >= len(names): memo['sub'][tab] = 0
        size, gap = u * .95, u * 1.6
        x = left + (right - left - sum(self.width(n, size) + gap for n in names) + gap) / 2
        def choose(i): memo['sub'][tab] = i
        for i, name in enumerate(names):
            tw = self.width(name, size)
            self.txt(p, name, x, top + h * .68, size, 0, G if i == memo['sub'][tab] else G_DIM, i == memo['sub'][tab])
            self.w.hit(QRectF(x - gap / 2, top, tw + gap, h), lambda i=i: choose(i), name=name)
            x += tw + gap

    def footer(self, p, d, left, top, right, h):
        u, S, stats = self.u, self.S, d.get('player.stats')
        p.fillRect(QRectF(left, top, right - left, h), BG_HI)
        if not stats: return
        y, size, n = top + h * .68, u * .95, lambda k: int(stats.get(k) or 0)
        self.txt(p, f'{S["hp"]} {n("hp")}/{n("hpMax")}', left + u * .6, y, size)
        self.txt(p, f'{S["ap"]} {n("ap")}/{n("apMax")}', right - u * .6, y, size, 2)
        level = f'{S["level"]} {n("level")}'  # in the middle: level and the bar to the next one
        lw, bar = self.width(level, size), (right - left) * .22
        x = left + (right - left) / 2 - (lw + u + bar) / 2
        self.txt(p, level, x, y, size)
        box = QRectF(x + lw + u, top + h * .35, bar, h * .32)
        self.frame(p, box, G, u * .1)
        if isinstance(stats.get('xpProgress'), (int, float)): p.fillRect(QRectF(box.x(), box.y(), bar * max(0, min(1, stats['xpProgress'])), box.height()), G)

    def draw_toast(self, p, W, bottom):
        u, size = self.u, self.u * .95
        tw = self.width(self.toast, size) + u * 2
        box = QRectF((W - tw) / 2, bottom - u * 2.4, tw, u * 2)
        self.frame(p, box, G, u * .1, color(0x04140A, 0xEE))
        self.txt(p, self.toast, W / 2, box.center().y() + size * .35, size, 1, G, True)

    # STAT ----------------------------------------------------------------------------------------------------------------
    def limb(self, d, key):
        """(fraction, crippled) of one limb."""
        o = (d.get('player.limbs') or {}).get(key)
        if not isinstance(o, dict): return 1.0, False
        top = o.get('max') if (o.get('max') or 0) > 0 else 100
        return max(0.0, min(1.0, (o['value'] if isinstance(o.get('value'), (int, float)) else top) / top)), bool(o.get('crippled'))

    def stat(self, p, d, a):
        u, S, stats = self.u, self.S, d.get('player.stats')
        if self.memo['sub'][T_STAT] == 1: return self.special(p, d, a)
        cx, cy, s, bw = a.center().x(), a.top() + a.height() * .47, a.height() / 15, u * 4.5
        self.figure(p, d, cx, cy, s)
        for key, x, y in (('head', cx - bw / 2, cy - s * 7.2), ('leftArm', cx - s * 7.5 - bw, cy - s * 2.2), ('rightArm', cx + s * 7.5, cy - s * 2.2), ('leftLeg', cx - s * 6 - bw, cy + s * 5.2), ('rightLeg', cx + s * 6, cy + s * 5.2)):
            part, crippled = self.limb(d, key)
            p.fillRect(QRectF(x, y, bw * part, u * .55), G_DIM if crippled else G)
            self.frame(p, QRectF(x, y, bw, u * .55), G, u * .08)
        if stats:
            n = lambda k: int(stats.get(k) or 0)
            self.txt(p, stats.get('name') or '', a.left(), a.top() + u * 1.2, u * 1.1)
            self.txt(p, f'{S["rads"]} {n("rads")}', a.right(), a.top() + u * 1.2, u, 2)
            self.txt(p, f'{S["dr"]} {n("damageResist")}   {S["er"]} {n("energyResist")}   {S["rr"]} {n("radResist")}', cx, a.bottom() - u * .6, u * .9, 1, G_DIM)

    def figure(self, p, d, cx, cy, s):
        """The stylised figure (the app's own motif); a crippled limb is drawn faint (the app lets it blink)."""
        tone = lambda key: G_FAINT if self.limb(d, key)[1] else G
        ln = lambda key, *pts: [self.line(p, cx + pts[i] * s, cy + pts[i + 1] * s, cx + pts[i + 2] * s, cy + pts[i + 3] * s, tone(key), s * .32, True) for i in range(0, len(pts) - 2, 2)]
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(tone('head'), s * .32, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawEllipse(QPointF(cx, cy - s * 4.6), s * 1.5, s * 1.5)
        p.drawArc(QRectF(cx - s * .7, cy - s * 4.6, s * 1.4, s * .9), -20 * 16, -140 * 16)  # the smile
        ln('head', -.6, -4.9, -.2, -4.9); ln('head', .2, -4.9, .6, -4.9)
        p.setPen(QPen(tone('torso'), s * .32)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(cx - s * 1.9, cy - s * 2.8, s * 3.8, s * 4.4), s * .8, s * .8)
        ln('torso', 0, -2.8, 0, 1.6)
        part, crippled = self.limb(d, 'torso')  # the torso's bar sits inside the body
        p.fillRect(QRectF(cx - s * 1.4, cy + s * .3, s * 2.8, s * .65), BG)
        p.fillRect(QRectF(cx - s * 1.3, cy + s * .4, s * 2.6 * part, s * .45), G_DIM if crippled else G)
        ln('leftArm', -2.1, -2.4, -3.6, -.4, -4.1, 1.6); ln('rightArm', 2.1, -2.4, 3.6, -.4, 4.1, 1.6)
        ln('leftLeg', -.9, 1.8, -1.3, 4.4, -1.5, 6.4, -2.3, 6.4); ln('rightLeg', .9, 1.8, 1.3, 4.4, 1.5, 6.4, 2.3, 6.4)

    def special(self, p, d, a):
        u, rows = self.u, {e.get('key'): e for e in d.get('player.special') or [] if isinstance(e, dict)}
        if not rows: return
        row_h, y = min(a.height() / 7.5, u * 2.4), a.top() + u * .4
        for key, name in zip('SPECIAL', self.S['special']):
            o = rows.get(key) or {}
            value, base, ty = round(o.get('value') or 0), round(o.get('base') or 0), y + row_h * .66
            self.txt(p, key, a.left() + u * .4, ty, u * 1.3, 0, G, True)
            self.txt(p, name, a.left() + u * 2.4, ty, u)
            cell = a.width() * .036
            for k in range(10):  # ten boxes
                box = QRectF(a.left() + a.width() * .48 + k * cell + cell * .12, y + row_h * .25, cell * .76, row_h * .5)
                if k < min(value, 10): p.fillRect(box, G)
                else: self.frame(p, box, G_DIM, u * .06)
            self.txt(p, f'{value} ({"+" if value > base else ""}{value - base})' if value != base and base > 0 else str(value), a.right() - u * .2, ty, u * 1.1, 2)
            self.line(p, a.left(), y + row_h, a.right(), y + row_h, G_FAINT)
            y += row_h

    # INV -----------------------------------------------------------------------------------------------------------------
    def inv(self, p, d, a):
        u, S, sub = self.u, self.S, self.memo['sub'][T_INV]
        items, row_h, col_val, col_wt = inventory_of(d, sub), u * 2, a.right() - u * .4, a.right() - u * 5.2
        self.txt(p, S['col_wt'], col_wt, a.top() + u * .9, u * .75, 2, G_DIM)
        self.txt(p, S['col_val'], col_val, a.top() + u * .9, u * .75, 2, G_DIM)
        area = QRectF(a.left(), a.top() + u * 1.4, a.width(), a.height() - u * 1.4)
        if not items: return self.txt(p, S['empty'], a.center().x(), area.top() + u * 3, u, 1, G_DIM)
        def tap(o):  # weapons, apparel and aid act; the rest only says so
            if sub <= 2: self.item(o)
            else: self.say(S['no_action'].format(o.get('name') or ''))
        def rows(y):
            for o in items:
                if y + row_h >= area.top() and y <= area.bottom():
                    worn, ty, count = bool(o.get('equipped')), y + row_h * .66, o.get('count') or 1
                    if worn:
                        p.fillRect(QRectF(a.left(), y, a.width(), row_h), BG_HI)
                        p.fillRect(QRectF(a.left() + u * .3, y + row_h * .36, u * .6, row_h * .28), G)
                    name = self.fit(f'{o.get("name") or ""}' + (f' ({count})' if count > 1 else ''), col_wt - u * 4.5 - (a.left() + u * 1.4), u)
                    self.txt(p, name, a.left() + u * 1.4, ty, u, 0, G, worn)
                    self.txt(p, fmt_weight(o.get('weight') or 0), col_wt, ty, u * .9, 2, G_DIM)
                    self.txt(p, int(o.get('value') or 0), col_val, ty, u * .9, 2, G_DIM)
                    self.line(p, a.left(), y + row_h, a.right(), y + row_h, G_FAINT)
                    self.w.hit(QRectF(a.left(), y, a.width(), row_h), lambda o=o: tap(o), name=o.get('name') or '')
                y += row_h
            return y
        self.w.scroller(p, f'pipboy-inv{sub}', area, rows)
        p.setClipRect(a)  # the scroller ended the clipping of the content area
        self.scrollbar(p, f'pipboy-inv{sub}', area)

    # FAV -----------------------------------------------------------------------------------------------------------------
    def fav(self, p, d, a):
        u, S = self.u, self.S
        slots, stim, stim_n, rad, rad_n = favourites(d)
        gap, quick = u * .4, u * 3.4
        gw, gh = (a.width() - gap * 3) / 4, (a.height() - quick - gap * 3) / 3
        for i, o in enumerate(slots):
            box = QRectF(a.left() + (i % 4) * (gw + gap), a.top() + (i // 4) * (gh + gap), gw, gh)
            worn = bool(o and o.get('equipped'))
            self.frame(p, box, G if o else G_FAINT, u * (.14 if worn else .08), BG_HI if worn else None)
            self.txt(p, i + 1, box.left() + u * .4, box.top() + u, u * .8, 0, G_DIM)
            if not o: continue
            name, second, room = str(o.get('name') or ''), '', gw - u * .8  # the name on up to two lines, broken at the last blank that fits
            if self.width(name, u) > room:
                cut = name.rfind(' ')
                while cut > 0 and self.width(name[:cut], u) > room: cut = name.rfind(' ', 0, cut)
                name, second = (name[:cut], self.fit(name[cut + 1:], room, u)) if cut > 0 else (self.fit(name, room, u), '')
            ny = box.center().y() + u * (-.25 if second else .35)
            for row in (name, second) if second else (name,):
                self.txt(p, row, box.center().x(), ny, u, 1, G, worn)
                ny += u * 1.2
            if o.get('type') == 'aid' or (o.get('count') or 1) > 1: self.txt(p, f'×{o.get("count") or 1}', box.right() - u * .4, box.bottom() - u * .4, u * .85, 2, G_DIM)
            self.w.hit(box, lambda o=o: self.item(o, 'equip' if o.get('type') == 'weapon' else 'use' if o.get('type') == 'aid' else 'toggle'), name=f'fav{i + 1}')
        top, bw = a.bottom() - quick + gap, (a.width() - gap) / 2
        for box, o, count, label in ((QRectF(a.left(), top, bw, quick - gap), stim, stim_n, S['stimpak']), (QRectF(a.right() - bw, top, bw, quick - gap), rad, rad_n, S['radaway'])):
            has = bool(o and count > 0)
            self.frame(p, box, G if has else G_DIM, u * .14, BG_HI if has else None)
            self.txt(p, self.fit(f'{((o or {}).get("name") or label).upper()}  {count}', box.width() - u, u * 1.3), box.center().x(), box.center().y() + u * .45, u * 1.3, 1, G if has else G_DIM, has)
            self.w.hit(box, (lambda o=o: self.item(o, 'use')) if has else (lambda label=label: self.say(S['none_left'].format(label))), name=label)
        if not any(slots): self.txt(p, self.fit(S['no_favorites'], a.width() - u, u * .9), a.center().x(), a.top() + (a.height() - quick) / 2 + u * .35, u * .9, 1, G_DIM)

    # DATA ----------------------------------------------------------------------------------------------------------------
    def data(self, p, d, a):
        u, S = self.u, self.S
        if self.memo['sub'][T_DATA] == 1: return self.world(p, d, a)
        groups = quest_groups(d)
        if not groups: return self.txt(p, S['no_quests'], a.center().x(), a.top() + u * 3, u, 1, G_DIM)
        qh, oh = u * 2, u * 1.6
        def rows(y):
            for name, active, goals in groups:
                if active: p.fillRect(QRectF(a.left(), y + qh * .3, u * .5, qh * .4), G)
                self.txt(p, self.fit(name or '?', a.width() - u * 2, u * 1.1), a.left() + u, y + qh * .68, u * 1.1, 0, G if active else G_DIM, True)
                y += qh
                for goal, state in goals:
                    box = QRectF(a.left() + u * 1.6, y + oh * .25, u * .7, oh * .5)
                    tone = G if state == 'active' else G_DIM
                    self.frame(p, box, tone, u * .08)
                    if state == 'completed': p.fillRect(box.adjusted(u * .15, u * .15, -u * .15, -u * .15), G_DIM)
                    if state == 'failed':
                        self.line(p, box.left(), box.top(), box.right(), box.bottom(), tone, u * .08); self.line(p, box.left(), box.bottom(), box.right(), box.top(), tone, u * .08)
                    self.txt(p, self.fit(goal, a.width() - u * 3.6, u * .9), a.left() + u * 2.9, y + oh * .68, u * .9, 0, tone)
                    y += oh
                y += u * .5
            return y
        self.w.scroller(p, 'pipboy-quests', a, rows)
        p.setClipRect(a)
        self.scrollbar(p, 'pipboy-quests', a)

    def world(self, p, d, a):
        u, S, place, stats = self.u, self.S, d.get('player.location') or {}, d.get('player.stats') or {}
        y, vx = a.top() + u * 1.6, a.left() + a.width() * .34
        rows = [(S['date'], date_string(d.get('world.time'))), (S['location'], place.get('location')), (S['cell'], (place.get('cell') or '') + (f'  [{S["interior"]}]' if place.get('interior') else '') if place else ''),
                (S['worldspace'], place.get('worldspace')), (S['position'], f'{place.get("x") or 0:.0f} / {place.get("y") or 0:.0f} / {place.get("z") or 0:.0f}' if place else ''),
                (S['caps'], int(stats.get('caps') or 0) if stats else ''), (S['weight'], f'{round(stats.get("weight") or 0)} / {round(stats.get("weightMax") or 0)}' if stats else '')]
        for label, value in rows:
            self.txt(p, label, a.left() + u * .4, y, u * .9, 0, G_DIM)
            self.txt(p, self.fit('–' if value in (None, '') else value, a.right() - vx, u * 1.05), vx, y, u * 1.05, 0, G, True)
            self.line(p, a.left(), y + u * .7, a.right(), y + u * .7, G_FAINT)
            y += u * 2.2

    # MAP -----------------------------------------------------------------------------------------------------------------
    def map(self, p, d, a):
        u, S, memo, place = self.u, self.S, self.memo, d.get('player.location') or {}
        step = u * 2.5
        for n in range(int(a.width() / step) + 1): self.line(p, a.left() + n * step, a.top(), a.left() + n * step, a.bottom(), G_FAINT)
        for n in range(int(a.height() / step) + 1): self.line(p, a.left(), a.top() + n * step, a.right(), a.top() + n * step, G_FAINT)
        self.frame(p, a, G_DIM)
        inside = bool(place.get('interior'))
        world = (d.get('pipboy.Map') or {}).get('Local' if inside else 'World') or {}
        marks = lambda key: [o for o in world.get(key) or [] if isinstance(o, dict) and num(o, 'X', 'x') is not None and num(o, 'Y', 'y') is not None]
        quests, doors, places, me = marks('Quests'), marks('Doors') if inside else [], marks('Locations'), world.get('Player') if isinstance(world.get('Player'), dict) else None
        px, py, rot = num(me, 'X', 'x'), num(me, 'Y', 'y'), num(me, 'Rotation', 'rotation')
        if px is None and place and not inside: px, py, rot = place.get('x'), place.get('y'), math.degrees(place.get('heading') or 0)
        xs, ys = [], []  # the extent: the world's corners, indoors the doors, quest markers and the player plus a margin
        if not inside and isinstance(world.get('Extents'), dict):
            xs = [v for k, v in world['Extents'].items() if k.endswith('X') and isinstance(v, (int, float))]
            ys = [v for k, v in world['Extents'].items() if k.endswith('Y') and isinstance(v, (int, float))]
        if not xs or not ys:
            points = places + doors + quests + ([me] if me and px is not None and py is not None else [])
            xs, ys = [num(o, 'X', 'x') for o in points], [num(o, 'Y', 'y') for o in points]
            if xs:
                margin = max(1500, max(max(xs) - min(xs), max(ys) - min(ys)) * .15)
                xs, ys = [min(xs) - margin, max(xs) + margin], [min(ys) - margin, max(ys) + margin]
        if not (xs and ys and min(xs) < max(xs) and min(ys) < max(ys)) and px is not None and py is not None: xs, ys = [px - 20000, px + 20000], [py - 20000, py + 20000]
        if inside: self.txt(p, S['map_interior'].format(place.get('cell') or ''), a.left() + u * .5, a.top() + u * 1.3, u * .9)
        if not (xs and ys and min(xs) < max(xs) and min(ys) < max(ys)): return self.txt(p, S['map_nodata'], a.center().x(), a.center().y(), u, 1, G_DIM)
        scale, mx, my = min(a.width() / (max(xs) - min(xs)), a.height() / (max(ys) - min(ys))) * .96, (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2  # fitted, y upwards
        if memo['zoom'] and px is not None: scale, mx, my = scale * 3.5, px, py
        at = lambda o: QPointF(a.center().x() + (num(o, 'X', 'x') - mx) * scale, a.center().y() - (num(o, 'Y', 'y') - my) * scale)
        size = u * .35
        for o in places:
            if o.get('Visible') is False: continue
            c = at(o)
            if not a.contains(c): continue
            known = o.get('Discovered', True)
            p.setPen(Qt.PenStyle.NoPen if known else QPen(G_DIM, u * .06)); p.setBrush(G if known else Qt.BrushStyle.NoBrush)
            p.drawPolygon(QPolygonF([QPointF(c.x(), c.y() - size), QPointF(c.x() + size, c.y()), QPointF(c.x(), c.y() + size), QPointF(c.x() - size, c.y())]))
            if memo['zoom'] and known: self.txt(p, o.get('text') or o.get('Name') or '', c.x() + size * 1.6, c.y() + size, u * .65, 0, G_DIM)
        named = []
        for o in doors:  # doors as open circles; one label where several lie close together
            c = at(o)
            p.setPen(QPen(G, u * .1)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, u * .4, u * .4)
            if not any(abs(n.x() - c.x()) < u * 6 and abs(n.y() - c.y()) < u * 1.2 for n in named):
                self.txt(p, o.get('Name') or '', c.x() + u * .6, c.y() + u * .3, u * .65, 0, G_DIM)
                named.append(c)
        for o in quests:  # quest markers as squares with a glow
            c, q = at(o), u * .45
            p.fillRect(QRectF(c.x() - q * 1.5, c.y() - q * 1.5, q * 3, q * 3), color(0x1AFF80, 0x30))
            self.frame(p, QRectF(c.x() - q, c.y() - q, q * 2, q * 2), G, u * .12)
            p.fillRect(QRectF(c.x() - q * .4, c.y() - q * .4, q * .8, q * .8), G)
        if px is not None and py is not None:
            s = u * .9
            p.save()
            p.translate(a.center().x() + (px - mx) * scale, a.center().y() - (py - my) * scale); p.rotate(rot or 0)
            arrow = QPainterPath()
            arrow.moveTo(0, -s); arrow.lineTo(s * .65, s * .75); arrow.lineTo(0, s * .35); arrow.lineTo(-s * .65, s * .75); arrow.closeSubpath()
            p.setPen(QPen(color(0x1AFF80, 0x55), u * .3)); p.setBrush(G)
            p.drawPath(arrow)
            p.restore()
        self.txt(p, self.fit(place.get('location') or place.get('worldspace') or '', a.width() * .6, u * .95), a.right() - u * .5, a.bottom() - u * .6, u * .95, 2, G, True)
        self.txt(p, S['map_zoom'], a.left() + u * .5, a.bottom() - u * .6, u * .7, 0, G_DIM)
        def zoom(): memo['zoom'] = not memo['zoom']
        self.w.hit(a, zoom, name='map')

    # RADIO ---------------------------------------------------------------------------------------------------------------
    def radio(self, p, d, a):
        u, S, radio = self.u, self.S, d.get('radio') or {}
        on = bool(radio.get('enabled'))
        button = QRectF(a.left(), a.top(), a.width() * .42, u * 2.2)
        self.frame(p, button, G, u * .1, G if on else None)
        self.txt(p, S['radio_on' if on else 'radio_off'], button.center().x(), button.center().y() + u * .35, u, 1, BG if on else G)
        self.w.hit(button, lambda: self.command('radio', {'enable': not on}), name='radio')
        area = QRectF(a.left(), a.top() + u * 3, a.width() * .5, a.height() - u * 3)
        stations = [o for o in radio.get('stations') or [] if isinstance(o, dict) and o.get('inRange', True)]
        row_h, tuned = u * 1.9, radio.get('frequency') or 0
        def rows(y):
            for o in stations:
                active = bool(o.get('active')) or (on and isinstance(o.get('frequency'), (int, float)) and abs(o['frequency'] - tuned) < .15)
                if active:
                    p.fillRect(QRectF(area.left(), y, area.width(), row_h), BG_HI)
                    p.fillRect(QRectF(area.left() + u * .2, y + row_h * .36, u * .6, row_h * .28), G)
                self.txt(p, self.fit(o.get('text') or o.get('name') or '?', area.width() - u * 1.6, u * .95), area.left() + u * 1.3, y + row_h * .66, u * .95, 0, G, active)
                y += row_h
            return y
        if stations:
            self.w.scroller(p, 'pipboy-radio', area, rows)
            p.setClipRect(a)
        else: self.txt(p, S['radio_none'], area.left(), area.top() + u * 1.2, u * .9, 0, G_DIM)
        wave = QRectF(a.left() + a.width() * .56, a.top() + u * 3, a.width() * .44, a.height() - u * 4.5)
        self.frame(p, wave, G_DIM)
        for n in range(1, 8): self.line(p, wave.left() + wave.width() * n / 8, wave.bottom() - u * .4, wave.left() + wave.width() * n / 8, wave.bottom(), G_DIM)
        curve = QPainterPath()  # the app lets the wave run; here it stands still while the radio plays
        for n in range(121):
            phase = n / 120 * math.pi * 6
            y = wave.center().y() - (.32 * math.sin(phase) + .12 * math.sin(phase * 2.7) + .05 * math.sin(phase * 7) if on else 0) * wave.height()
            curve.moveTo(wave.left(), y) if n == 0 else curve.lineTo(wave.left() + wave.width() * n / 120, y)
        p.setPen(QPen(G, u * .14)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(curve)
        if on and tuned > 0: self.txt(p, f'{tuned:.1f}', wave.right(), a.bottom() - u * .3, u * .9, 2, G_DIM)
