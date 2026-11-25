"""Self-check for the native front end: python3 ui/test_ui.py (needs PySide6, no display; skipped without PySide6).
Runs both windows against a real Tandem service in dry-run mode and walks through the views index.html has."""
import base64, json, os, socket, socketserver, struct, sys, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MALLOC_ARENA_MAX', '1')  # keeps tandem_ui from restarting itself
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import test_tandem as base  # noqa: E402  (redirects HOME and has the sample library)
import tandem  # noqa: E402
os.environ['XDG_CACHE_HOME'] = str(base.TMP / 'cache')  # the accent cache must not land in the real one
try:
    import tandem_ui as ui
    from PySide6.QtCore import QBuffer, QEvent, QPointF, Qt
    from PySide6.QtGui import QFontDatabase, QGuiApplication, QImage, QMouseEvent
    from decks import aok, cnc, d2, ffix, hev, homm3, kknd2, packcss, packlua, packmem, pipboy, portsocket, ra2
except ImportError: ui = None
SHOTS = os.environ.get('TANDEM_UI_SHOTS')  # a folder: every painted view is saved there to look at


def ffix_state(battle=False):
    """A state as the game's status server sends it (the sample from decks/377840.html)."""
    learn = lambda name, ap, top, support=False: {'name': name, 'ap': ap, 'max': top, 'done': ap >= top, 'support': support}
    st = {'inGame': True, 'scene': 'battle' if battle else 'world', 'fps': 60, 'lang': 'GR', 'playTime': 24690, 'gil': 48213, 'location': 'Lindblum – Theaterviertel', 'scenario': 4720,
          'party': [{'id': 0, 'name': 'Zidane', 'lv': 21, 'hp': 412, 'maxHp': 480, 'mp': 61, 'maxMp': 78, 'trance': 180, 'hasTrance': True, 'face': 'zidane', 'status': ['Haste'],
                     'learn': [learn('Flammenklinge', 40, 40), learn('Mutkraft', 12, 60), learn('Auto-Hast', 33, 50, True)]},
                    {'id': 1, 'name': 'Vivi', 'lv': 19, 'hp': 96, 'maxHp': 301, 'mp': 120, 'maxMp': 160, 'trance': 0, 'hasTrance': True, 'face': 'vivi', 'status': ['Poison', 'Protect'], 'learn': [learn('Feuga', 22, 40)]},
                    {'id': 2, 'name': 'Steiner', 'lv': 20, 'hp': 0, 'maxHp': 540, 'mp': 20, 'maxMp': 40, 'trance': 255, 'hasTrance': True, 'inTrance': True, 'face': 'steiner', 'status': ['Death'], 'learn': []}],
          'items': [{'id': i, 'name': f'Gegenstand {i}', 'n': 3 + i, 'icon': f'item{i:02d}_00'} for i in range(40)],
          'keyItems': [{'id': 0, 'name': 'Fahrkarte nach Alexandria', 'used': True, 'icon': 'k'}, {'id': 1, 'name': 'Gartenschlüssel', 'icon': 'k'}],
          'world': {'x': .55, 'y': .42, 'rot': 40, 'naviMap': 1, 'chocobo': {'x': .3, 'y': .6}, 'airship': {'x': .7, 'y': .25}},
          'boosters': {'allowed': True, 'speed': True, 'assist': False, 'dmg': False, 'noenc': True, 'speedFactor': 3},
          'counters': {'steals': 17, 'frogs': 4, 'dragons': 2, 'treasure': 262, 'cardWins': 12, 'cardLosses': 7, 'cardDraws': 3, 'chocographs': 9}}
    if battle:
        st['battle'] = {'enemies': [{'name': 'Ochu', 'hp': 680, 'maxHp': 800, 'atb': 20, 'maxAtb': 40, 'status': ['Slow'], 'weak': ['Fire', 'Cold'], 'absorb': ['Earth'], 'immune': ['Aqua'], 'half': [],
                                     'steal': ['Potion', 'Äther'], 'drop': ['Gysahl-Grün']}, {'name': 'Gargoyle', 'hp': 120, 'maxHp': 400, 'atb': 5, 'maxAtb': 40, 'status': ['Sleep']}]}
        for n, m in enumerate(st['party']): m.update(atb=40 if n == 0 else 10 + n * 12, maxAtb=40, canAct=True)
    return st


class FakeGame(BaseHTTPRequestHandler):
    """Stands in for the status server inside FF IX."""
    state, commands, png = ffix_state(), [], b''

    def log_message(self, *args): pass

    def do_GET(self):
        if self.path.startswith('/cmd/'): FakeGame.commands.append(self.path)
        if self.path != '/events':
            self.send_response(200); self.send_header('Content-Length', str(len(FakeGame.png))); self.end_headers()
            return self.wfile.write(FakeGame.png)
        self.send_response(200); self.end_headers()
        try:
            while True: self.wfile.write(f'data: {json.dumps(FakeGame.state)}\n\n'.encode()); self.wfile.flush(); time.sleep(0.05)
        except OSError: pass


def pipboy_state():
    """Game data as the ThorPipBoy plugin reports it (keys of its protocol)."""
    item = lambda id, name, kind, **more: {'id': id, 'stack': 0, 'name': name, 'type': kind, 'count': 1, 'equipped': False, 'weight': 1.5, 'value': 20, **more}
    return {'game': {'ready': True, 'player': True, 'pipboyOpen': False},
            'player.stats': {'name': 'Nora', 'level': 7, 'xpProgress': .4, 'hp': 181.3, 'hpMax': 200, 'ap': 82.0, 'apMax': 90, 'rads': 12, 'caps': 345, 'weight': 143.2, 'weightMax': 240, 'damageResist': 31, 'energyResist': 12, 'radResist': 10},
            'player.special': [{'key': k, 'value': v, 'base': 4} for k, v in zip('SPECIAL', (4, 5, 3, 6, 4, 4, 2))],
            'player.limbs': {k: {'value': v, 'max': 100, 'crippled': v == 0} for k, v in (('head', 100), ('torso', 80), ('leftArm', 0), ('rightArm', 100), ('leftLeg', 55), ('rightLeg', 100))},
            'player.location': {'x': 1200.4, 'y': -3400.0, 'z': 12.0, 'heading': 1.2, 'interior': False, 'cell': 'Wilderness', 'location': 'Sanctuary Hills', 'worldspace': 'Commonwealth'},
            'world.time': {'year': 287, 'month': 10, 'day': 23, 'hour': 9.5, 'daysPassed': 1.2},
            'player.inventory': [item('0x00004822', '10-mm-Pistole', 'weapon', equipped=True, fav=3), item('0x0001F669', 'Baseballschläger', 'weapon'), item('0x00023736', 'Stimpak', 'aid', count=4, fav=0),
                                 item('0x000366C4', 'Vault-111-Overall', 'apparel', equipped=True), item('0x0001F276', '10-mm-Patrone', 'ammo', count=64, weight=0), item('0x00059B27', 'Klebeband', 'junk')]
                                + [item(f'0x{n:08X}', f'Waffe {n:02d}', 'weapon') for n in range(30)],
            'player.quests': [], 'pipboy.Quests': [{'text': 'Raus aus der Zeit', 'active': True, 'enabled': True, 'objectives': [{'text': 'Verlasse Vault 111', 'completed': True}, {'text': 'Geh nach Hause'}]},
                                                    {'text': 'Wenn die Freiheit ruft', 'objectives': [{'text': 'Untersuche Concord'}]}],
            'radio': {'enabled': False, 'frequency': 0, 'stations': [{'text': 'Diamond City Radio', 'frequency': 99.1, 'inRange': True}, {'text': 'Klassik-Radio', 'frequency': 95.3, 'inRange': True}]},
            'pipboy.Map': {'World': {'Extents': {'NWX': -135168, 'NWY': 102400, 'NEX': 114688, 'NEY': 102400, 'SWX': -135168, 'SWY': -147456}, 'Player': {'X': 1200, 'Y': -3400, 'Rotation': 70},
                                     'Locations': [{'X': -80000, 'Y': 90000, 'Discovered': True, 'Visible': True, 'text': 'Sanctuary Hills'}, {'X': -60000, 'Y': 60000, 'Discovered': False, 'Visible': True, 'text': 'Concord'}],
                                     'Quests': [{'X': -60000, 'Y': 61000}]}}}


class FakeFallout(socketserver.BaseRequestHandler):
    """Stands in for the ThorPipBoy plugin inside Fallout 4: a WebSocket server that answers subscriptions and commands."""
    state, commands = pipboy_state(), []

    def tell(self, message):
        data = json.dumps(message).encode()
        self.request.sendall(bytes([0x81]) + (bytes([len(data)]) if len(data) < 126 else bytes([126]) + struct.pack('>H', len(data)) if len(data) < 65536 else bytes([127]) + struct.pack('>Q', len(data))) + data)

    def handle(self):
        buf = b''
        try:
            while b'\r\n\r\n' not in buf: buf += self.request.recv(4096)
            self.request.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n')
            self.tell({'type': 'hello', 'server': 'ThorPipBoy', 'ready': True})
            buf = buf.split(b'\r\n\r\n', 1)[1]
            while True:
                chunk = self.request.recv(65536)
                if not chunk: return
                frames, buf = pipboy.ws_frames(buf + chunk)
                for _, op, payload in frames:
                    m = json.loads(payload)
                    if m['type'] == 'subscribe': self.tell({'type': 'data', 'id': m['id'], 'data': {k: FakeFallout.state[k] for k in m['fields']}})
                    elif m['type'] == 'heartbeat': self.tell({'type': 'heartbeat', 'ready': True})
                    elif m['type'] == 'command':
                        FakeFallout.commands.append((m['command'], m['params']))
                        result = {'enabled': m['params'].get('enable')} if m['command'] == 'radio' else {'action': 'used' if m['command'] == 'use' else 'equipped'}
                        self.tell({'type': 'commandResult', 'id': m['id'], 'command': m['command'], 'success': True, 'result': result})
        except OSError: pass


def hev_state(t=1.0):
    """A snapshot as the Half-Life client library sends it (cl_dll/thor_deck.cpp): in the test chamber, crowbar and pistol."""
    return {'v': 1, 'seq': 7, 't': t, 'map': 'c1a0d', 'deck': 1, 'hp': 82, 'ap': 15, 'suit': 1, 'dead': 0, 'hide': 0, 'fl': 1, 'flbat': 64, 'dmg': 1 << 18, 'geiger': 300,
            'train': 0, 'pain': [0, .5, 0, 0], 'water': 0, 'air': -1.0, 'ground': 1, 'fallv': 0, 'speed': 120, 'move': 3, 'yaw': 45.0, 'pitch': 0.0, 'pos': [100, 200, 0],
            'slots': 5, 'cur': 2, 'sel': 0, 'w': [[1, 'weapon_crowbar', 0, 0, -1, -1, -1, -1, -1, 1], [2, 'weapon_9mmhandgun', 1, 0, 12, 68, 250, -1, -1, 1],
                                                  [4, 'weapon_9mmAR', 2, 0, 0, 0, 250, 2, 10, 0]],
            'feed': [[3, 'a', 'weapon_9mmAR#2', 2, 1.0], [2, 'w', 'weapon_9mmhandgun', 0, 30.0], [1, 'i', 'item_battery', 0, 70.0]]}


class FakeHalfLife(socketserver.BaseRequestHandler):
    """Stands in for the game's end of the deck socket (ports/tandem_deck.h): the launcher's line, then snapshots; commands are kept."""
    commands, home = [], ''

    def handle(self):
        try:
            self.request.sendall(json.dumps({'game': 'valve', 'data': '', 'home': FakeHalfLife.home}).encode() + b'\n#icons 3\nabc\n')
            self.request.settimeout(.05)
            t = 1.0
            while True:
                t += .05
                self.request.sendall(json.dumps(hev_state(t)).encode() + b'\n')
                try: data = self.request.recv(4096)
                except socket.timeout: continue
                if not data: return
                FakeHalfLife.commands += [line for line in data.decode().split('\n') if line]
        except OSError: pass


def aok_state():
    """A state line as the Age of Kings port sends it (ports/aok/deck_socket.inc): a villager selected, one house to build, one villager queued."""
    i = [1, 1, 200, 180, 100, 150, 4, 5, 0, 0, 1, 25, 25, 50730, 15, 83, 3, 10, 2, 1, 3, 4, 2, 0, 0, 4, 0, 4, 2, 0, 2, 1, 150, 2, 0, 0, 0, 1]
    i += [1, 0, 50706, 3, 1, 0, -1, 0] + [15, 27, 0, -1, 1, 1, -1, 0] + [0, 83, 2, 50730, 15] + [0, 1, 50706, 7]
    return {'v': 1, 'ingame': 1, 'i': i, 'age': 'Dunkle Zeit', 'next': 'Feudalzeit', 'name': 'Dorfbewohner', 'labels': ['Haus', 'Mehr'], 'goto': ['Dorfzentrum'] + [''] * 13,
            'help': ['<b>Haus bauen</b>  (Q)', '']}


def ra2_state():
    """A state line as the Red Alert 2 port sends it (the engine's thor.cpp): Soviet, radar on, a power plant building, a barracks, one superweapon, group I."""
    i = [2, 1, 9500, 150, 100, 1, 1, 0, 0b1111, 4, 2, 1, 0, 2, 1, 2, 1, 7, 3, 5, 4, 0, 0x300, 0]
    i += [5, 800, 1, 400, 1, 0, 0] + [9, 500, 0, 0, 0, 0, 0] + [2 << 16 | 1, 0, 250, 300, 0] + [3, 3, 0, 0, 0, 0, 0, 0, 0, 0]
    return {'v': 1, 'ingame': 1, 'zoom': 125, 'i': i}


def cnc_state():
    """A state line as the Command & Conquer port sends it (the engine's thor_tandem.cpp): Red Alert, Soviet, radar on, a power plant
    building, a rifleman to train, group 2 with six units selected, the controller's ring on the first item."""
    i = [4, 1, 8105, 200, 70, cnc.F_RADAR | cnc.F_REPAIR_OK, 10, 20, 64, 64, 12 * 16, 22 * 16, 15 * 16, 8 * 16, 1, 1, 1, 0, 0, 0, 0b10, 0, 6, 0, 0, 4, 6, 1]
    i += [0, 0, 5 << 16 | 3, 300, cnc.ST_BUILDING, 400] + [1, 0, 3 << 16 | 1, 100, cnc.ST_AVAILABLE, 0]
    return {'v': 1, 'game': 'ra', 'ingame': 1, 'pal': 11, 'radar': 12, 'focus': 0, 'pw': [1, 2, 3, 4, 5, 6], 'i': i}


def homm3_state():
    """A state as the Heroes III port sends it (the fork's ThorDeck.cpp): the adventure map, one hero selected, one town, two stacks, the map 4 x 2."""
    return {'mode': 'adventure', 'player': 0, 'day': 1, 'week': 1, 'month': 1, 'res': [20, 10, 26, 10, 10, 10, 20000],
            'heroes': [{'id': 7, 'name': 'Xsi', 'level': 1, 'icon': 3, 'mp': 1500, 'mpMax': 1500, 'mana': 20, 'manaMax': 20, 'selected': True}],
            'towns': [{'id': 9, 'name': 'Agony', 'icon': 2}], 'army': [{'slot': 0, 'name': 'Skelette', 'count': 30, 'icon': 56}, {'slot': 2, 'name': 'Zombies', 'count': 6, 'icon': 58}],
            'spells': [{'id': 1, 'name': 'Schiff rufen', 'icon': 1, 'cost': 8, 'ok': False}, {'id': 4, 'name': 'Erde sehen', 'icon': 4, 'cost': 2, 'ok': True}],
            'can': {'endTurn': True, 'next': False, 'hero': True}, 'map': {'w': 4, 'h': 2, 'levels': 1, 'view': [0, 0, 2, 1, 0], 'version': 1}}


def kknd2_state():
    """A state line as the KKnD 2 port sends it (the game's thor/linux/TandemDeck.cs): Evolved in a skirmish, a factory with a unit
    in the works and a locked one, a lab with one building to research, two units selected, group 1, the controller's ring on card 0."""
    return {'v': 1, 'tab': 1, 'producer': 0, 'focus': 0, 'paused': False, 'speed': 150, 'waypoint': False, 'force': True, 'playing': True, 'over': False,
            'won': False, 'faction': 'evolved', 'cash': 900, 'queues': [{'id': 31, 'cat': 'vehicle', 'by': 'Beast Enclosure',
                                                                        'items': [['evolved_giant_beetle', 'Giant Beetle', 600, 40, 1, True, False, False, False],
                                                                                  ['evolved_mammoth', 'Mammoth', 1200, -1, 0, False, False, True, False]]}],
            'sel': [['evolved_berserker', 'Berserker', 2, 64]], 'groups': [2] + [0] * 9, 'gicons': ['evolved_berserker'] + [None] * 9,
            'techs': [[40, 'evolved_clanhall', 'Clanhall', 1, 3, False, 500]], 'labs': 1, 'free': 1, 'rigs': 2, 'tankers': 1, 'stations': 1, 'oil': 12000,
            'secs': 75, 'stance': 'Defend', 'pings': [10.5, 12.5], 'mode': 'UnitOrderGenerator', 'level': 'levels/multi/mlti_01.lpm', 'map': [64, 64],
            'bounds': [1, 1, 62, 62], 'cam': [10, 10, 30, 17], 'dots': [20.5, 30.5, 0xFF00FF, 0, 22.5, 30.5, 0xFF00FF, 1]}


def kknd2_art():
    """An art block as the game sends it: 12 sidebar buttons of 16 x 16, then a font of 224 glyphs where only 'A' has pixels."""
    frames = [struct.pack('<HHhh', 16, 16, 0, 0) + bytes([255]) * 16 * 16 * 4 for _ in range(12)]
    frames += [struct.pack('<HHhh', 3, 1, 0, 2) + bytes([255]) * 12 if n == 33 else struct.pack('<HHhh', 3, 0, 0, 0) for n in range(224)]
    return struct.pack('<H', len(frames)) + b''.join(frames)


class FakeKknd2(socketserver.BaseRequestHandler):
    """Stands in for the KKnD 2 port: the state, the faction's art, the minimap and one icon; commands are kept."""
    commands = []

    def handle(self):
        try:
            self.request.sendall(json.dumps(kknd2_state()).encode() + b'\n')
            while data := self.request.recv(4096):
                for line in data.decode().split('\n'):
                    if line == 'art evolved': self.request.sendall(b'#art:evolved %d\n' % len(kknd2_art()) + kknd2_art())
                    elif line == 'minimap': self.request.sendall(b'#minimap 36\n' + struct.pack('<HH', 4, 2) + bytes(32))
                    elif line == 'icon evolved_giant_beetle': self.request.sendall(b'#icon:evolved_giant_beetle 8\n' + struct.pack('<HHI', 1, 1, 0xFF00FF00))
                    elif line and not line.startswith('icon '): FakeKknd2.commands.append(line)
        except OSError: pass


class FakeHomm3(socketserver.BaseRequestHandler):
    """Stands in for the Heroes III port: the state, the minimap (JSON as a block) when the deck says "fresh", and the art the deck asks
    for (only the gold icon is there); commands are kept."""
    commands = []

    def handle(self):
        try:
            self.request.sendall(json.dumps(homm3_state()).encode() + b'\n')
            while data := self.request.recv(4096):
                for line in data.decode().split('\n'):
                    minimap = json.dumps({'minimap': base64.b64encode(bytes(range(24))).decode(), 'w': 4, 'h': 2}).encode()
                    if line == 'fresh': self.request.sendall(b'#json %d\n' % len(minimap) + minimap)
                    elif line == 'art def:RESOURCE:6': self.request.sendall(b'#art:def:RESOURCE:6 16\n' + struct.pack('<III', 1, 1, 0) + bytes([0, 255, 0, 255]))
                    elif line.startswith('art '): self.request.sendall(b'#art:%s 12\n' % line[4:].encode() + bytes(12))  # the files do not have it: drawn plain
                    elif line: FakeHomm3.commands.append(line)
        except OSError: pass


class FakeCnc(socketserver.BaseRequestHandler):
    """Stands in for the Command & Conquer port: the state, the radar and the pictures the deck asks for (only the power plant has a
    cameo, there is no sidebar art); commands are kept."""
    commands = []

    def handle(self):
        try:
            self.request.sendall(json.dumps(cnc_state()).encode() + b'\n')
            while data := self.request.recv(4096):
                for line in data.decode().split('\n'):
                    if line == 'radar': self.request.sendall(b'#radar 36\n' + struct.pack('<HH', 4, 2) + bytes(32))
                    elif line == f'pic {5 << 16 | 3}': self.request.sendall(b'#pic:%d 17\n' % (5 << 16 | 3) + struct.pack('<HHI', 1, 1, 0xFF00FF00) + b'Kraftwerk')
                    elif line.startswith('pic '): self.request.sendall(b'#pic:%s 4\n' % line.split()[1].encode() + bytes(4))
                    elif line: FakeCnc.commands.append(line)
        except OSError: pass


class FakeRa2(socketserver.BaseRequestHandler):
    """Stands in for the Red Alert 2 port: the state, the radar and the pictures the deck asks for (only cameo 5 has one); commands are kept."""
    commands = []

    def handle(self):
        try:
            self.request.sendall(json.dumps(ra2_state()).encode() + b'\n')
            while data := self.request.recv(4096):
                for line in data.decode().split('\n'):
                    if line == 'radar': self.request.sendall(b'#radar 36\n' + struct.pack('<HH', 4, 2) + bytes(32))
                    elif line == 'pic 5': self.request.sendall(b'#pic:5 17\n' + struct.pack('<HHI', 1, 1, 0xFF00FF00) + 'Kraftwerk'.encode())
                    elif line.startswith('pic '): self.request.sendall(b'#pic:%s 4\n' % line.split()[1].encode() + bytes(4))  # no sidebar art: plain plates
                    elif line: FakeRa2.commands.append(line)
        except OSError: pass


class FakeAok(socketserver.BaseRequestHandler):
    """Stands in for the Age of Kings port: the state, and the binary blocks the deck asks for (mini-map, icons); commands are kept."""
    commands = []

    def handle(self):
        try:
            self.request.sendall(json.dumps(aok_state()).encode() + b'\n')
            while data := self.request.recv(4096):
                for line in data.decode().split('\n'):
                    if line == 'map': self.request.sendall(b'#map 32\n' + bytes(32))
                    elif line.startswith('icon 50'): self.request.sendall(b'#icon:%s:%s 8\n' % tuple(n.encode() for n in line.split()[1:]) + struct.pack('<HHI', 1, 1, 0xFF00FF00))
                    elif line.startswith('icon'): self.request.sendall(b'#icon:%s:%s 0\n' % tuple(n.encode() for n in line.split()[1:]))  # no interface art: plain panels
                    elif line: FakeAok.commands.append(line)
        except OSError: pass


class FakeRetroArch:
    """Stands in for RetroArch's network commands (UDP): GET_STATUS and READ_CORE_MEMORY over a small GBA memory map."""
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.addr, self.asked, self.state = self.sock.getsockname(), [], 'PLAYING'
        self.ram = {0x02000000: bytearray(0x40000), 0x03000000: bytearray(0x8000), 0x08000000: bytearray(0x3000), 0xC000: bytearray(0x2000), 0x10000: bytearray(0x6000)}
        threading.Thread(target=self.serve, daemon=True).start()

    def poke(self, addr, data):
        base = next(b for b, mem in self.ram.items() if b <= addr < b + len(mem))
        self.ram[base][addr - base:addr - base + len(data)] = data

    def reads(self): return [(w[1], w[2]) for w in self.asked if w[0] == 'READ_CORE_MEMORY']

    def serve(self):
        while True:
            try: data, peer = self.sock.recvfrom(4096)
            except OSError: return
            words = data.decode().split()
            self.asked.append(words)
            if words[0] == 'GET_STATUS': reply = f'GET_STATUS {self.state} game_boy_advance,Sample,crc32=1053dce4\n'
            elif words[0] == 'READ_CORE_MEMORY':
                addr, n = int(words[1], 16), int(words[2])
                base = next((b for b, mem in self.ram.items() if b <= addr < b + len(mem)), None)
                reply = f'READ_CORE_MEMORY {addr:x} -1 no memory map defined\n' if base is None else \
                    f'READ_CORE_MEMORY {addr:x} ' + ' '.join('%02X' % b for b in self.ram[base][addr - base:addr - base + n]) + '\n'
            else: continue
            try: self.sock.sendto(reply.encode(), peer)
            except OSError: return


SAMPLE_LAYOUT = {'type': 'box', 'id': 'screen', 'children': [
    {'type': 'box', 'id': 'wait', 'visibleIf': '$waiting', 'children': [{'type': 'text', 'text': 'WARTEN'}]},
    {'type': 'pages', 'id': 'stage', 'visibleIf': '$ready', 'pages': [
        {'name': 'party', 'child': {'type': 'box', 'class': 'page', 'children': [
            {'type': 'box', 'class': 'head', 'children': [{'type': 'text', 'id': 'coins', 'text': '{coins} G'}, {'type': 'text', 'id': 'math', 'class': 'grow', 'text': '{math}'}]},
            {'type': 'list', 'id': 'party', 'items': '$party', 'empty': 'leer', 'template': {
                'type': 'box', 'class': 'mon', 'classIf': {'low': '$low'}, 'onClick': [{'set': {'selected': '{@index}'}}, {'navigate': 'detail'}],
                'children': [{'type': 'text', 'class': 'name', 'text': '{name}'}, {'type': 'bar', 'class': 'hp', 'value': '$hp', 'maxKey': '$maxHp', 'label': '{hp}/{maxHp}'}]}},
            {'type': 'button', 'id': 'poke', 'text': 'Aktion', 'onClick': {'call': 'poke', 'args': ['{coins}']}},
            {'type': 'button', 'id': 'wide', 'text': 'WIDE {_wideLabel}', 'onClick': {'call': 'wideView', 'args': ['toggle']}}]}},
        {'name': 'detail', 'child': {'type': 'box', 'class': 'page', 'children': [
            {'type': 'button', 'id': 'back', 'text': 'Zurück', 'onClick': 'back'},
            {'type': 'text', 'id': 'who', 'text': '{detail.name} L{detail.level}'},
            {'type': 'image', 'id': 'pic', 'src': 'asset:dot.png'}]}}]}]}
SAMPLE_CSS = '''/* a small pack for the self-check */
:root { --gap: 8px; background: #101020; }
#screen { padding: 10px; }
.page { gap: var(--gap); flex: 1; }
.head { flex-direction: row; gap: 10px; height: 40px; }
#coins { width: 100px; }
.grow { flex: 1; text-align: right; }
#party { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gap); }
.mon { padding: 6px; border: 2px solid #ffffff; height: 50px; background: linear-gradient(180deg, #223 0%, #446 100%); }
.mon.low { border-color: #ff0000; }
.mon:pressed { opacity: .5; }
.mon:nth-child(2n + 1) > .name { color: #ffff00; }
bar.hp { height: 10px; }
#pic { width: 64px; height: 64px; }
@media (max-width: 300px) { #party { grid-template-columns: 1fr; } }
.gone + .x { color: red; }
'''
SAMPLE_LUA = '''local names = pack.require("names")
local BASE = 0x02000500
actions = {}
function actions.poke(n)
  local ok, why = mem.write8(0x02000250, 0)  -- Tandem never writes: refused, with a reason
  return { set = { wrote = tostring(ok), why = why, got = n } }
end
function update(ui)
  if mem.u8(0x02000000) == 0 then return { waiting = true, ready = false } end
  local party = {}
  for i = 0, mem.u8(0x02000001) - 1 do
    local b = BASE + i * 0x14C
    local hp, max = mem.u16(b + 0x38), mem.u16(b + 0x34)
    party[#party + 1] = { name = names[mem.u8(b)] or "?", level = mem.u8(b + 0x0F), hp = hp, maxHp = max, low = hp * 4 <= max }
  end
  local out = { ready = true, waiting = false, party = party, coins = mem.u32(0x02000250),
                math = string.format("%d %d %d %d", 0xF0 & 0x3C, 1 << 4, 7 // 2, mem.u16(0x02000250) >> 4),
                code = mem.read(0x080000AC, 4), far = mem.u8(0x03000010) }
  if ui.page == "detail" and ui.selected then out.detail = party[ui.selected + 1] end
  if mem.u8(0x02000002) == 1 then while true do end end  -- a value the script cannot cope with: it must not hang anything
  return out
end
'''


def sample_pack(folder):
    base.touch(folder / 'manifest.json', json.dumps({'id': 'sample-pack', 'name': 'Probe', 'formatVersion': 2, 'match': {'gameCode': ['TEST'], 'crc32': []}, 'tickHz': 20,
                                                     'layout': 'layout.json', 'styles': ['style.css'], 'script': 'main.lua'}))
    base.touch(folder / 'layout.json', json.dumps(SAMPLE_LAYOUT))
    base.touch(folder / 'style.css', SAMPLE_CSS)
    base.touch(folder / 'main.lua', SAMPLE_LUA)
    base.touch(folder / 'names.lua', 'return { [1] = "Isaac", [2] = "Garet" }')
    (folder / 'assets').mkdir(exist_ok=True)
    dot = QImage(8, 8, QImage.Format.Format_ARGB32)
    dot.fill(Qt.GlobalColor.yellow); dot.save(str(folder / 'assets/dot.png'))


def sample_game(ra):
    """Two party members as Golden Sun keeps them: 0x14C bytes each from 0x02000500."""
    for i, (who, level, hp, top) in enumerate(((1, 5, 30, 40), (2, 7, 10, 50))):
        at = 0x02000500 + i * 0x14C
        ra.poke(at, bytes([who])); ra.poke(at + 0x0F, bytes([level])); ra.poke(at + 0x34, struct.pack('<H', top)); ra.poke(at + 0x38, struct.pack('<H', hp))
    ra.poke(0x02000250, struct.pack('<I', 1234)); ra.poke(0x080000AC, b'TEST'); ra.poke(0x03000010, b'\x07')


@unittest.skipUnless(ui, 'PySide6 fehlt')
class PackParts(unittest.TestCase):
    """What a companion pack runs on: Lua, the game's memory, layout."""
    @classmethod
    def setUpClass(cls): cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_lua_bridge(self):
        mem, logs = bytes(range(256)) * 4, []
        lua = packlua.Lua(lambda a, n: int.from_bytes(mem[a:a + n], 'little'), lambda a, n: mem[a:a + n], lambda kind, text: (None, 'kein Bild'),
                          lambda a: (None, 'keine Daten'), logs.append, lambda name: b'return { answer = 42 }' if name == b'data' else None)
        self.assertEqual(lua.call('load', '''
            local data = pack.require("data")
            function update(ui)
              if ui.mode == "loop" then while true do end end
              if ui.mode == "trap" then while true do pcall(function() while true do end end) end end
              if ui.mode == "error" then error("kaputt") end
              if ui.mode == "nothing" then return 5 end
              log("page " .. tostring(ui.page))
              return { bits = 0xF0 & 0x3C, shift = mem.u16(0x10) >> 4, div = 7 // 2, signed = mem.s8(0xFF), big = mem.u32(0xFC), len = #mem.read(0, 300),
                       list = { 1, 2 }, empty = {}, text = "Ä \\"x\\"\\n", half = 0.5, answer = data.answer, picture = pcall(gfx.sprite, {}),
                       gone = { tostring(io), tostring(os), tostring(load), tostring(debug), tostring(require) }, n = ui.n, flag = ui.flag,
                       wrote = { mem.write8(0x02000000, 1) } }
            end''', '=main.lua'), (True, ''))
        ok, text = lua.call('update', packlua.literal({'page': 'party', 'n': 3, 'flag': True}))
        self.assertTrue(ok, text)
        self.assertEqual(json.loads(text), {'bits': 48, 'shift': 0x111, 'div': 3, 'signed': -1, 'big': 0xFFFEFDFC, 'len': 300, 'list': [1, 2], 'empty': {}, 'text': 'Ä "x"\n',
                                            'half': 0.5, 'answer': 42, 'picture': False, 'gone': ['nil'] * 5, 'n': 3, 'flag': True, 'wrote': [False, "Tandem only reads the game's memory"]})
        self.assertEqual(logs, [b'page party'])
        start = time.time()
        for mode, why in (('loop', 'instruction budget'), ('trap', 'instruction budget'), ('error', 'kaputt'), ('nothing', 'must return a table')):  # broken scripts: stopped, not fatal
            ok, text = lua.call('update', packlua.literal({'mode': mode}))
            self.assertFalse(ok); self.assertIn(why, text)
        self.assertLess(time.time() - start, 2)
        self.assertTrue(lua.call('update', '{}')[0])  # and the next call starts fresh
        self.assertEqual(lua.call('action', 'nope', packlua.literal([])), (False, "no action 'nope'"))
        lua.close()
        broken = packlua.Lua(*[lambda *a: None] * 6)
        ok, why = broken.call('load', 'x = = 1', '=main.lua')
        self.assertFalse(ok); self.assertIn('unexpected symbol', why)
        self.assertEqual(broken.call('load', 'local t = {} while true do t[#t + 1] = ("x"):rep(4096) .. #t end', '=main.lua')[0], False)  # 16 MB, then stop
        broken.close()
        self.assertEqual(packlua.literal({'a': [1, 'x"y', None, True], 'end': 1.5}), '{["a"]={1,"x\\"y",nil,true,n=4},["end"]=1.5}')

    def test_memory_is_read_in_batches(self):
        ra = FakeRetroArch()
        ra.poke(0x02000250, struct.pack('<I', 1234)); ra.poke(0x02001FFE, b'\xAA\xBB\xCC'); ra.poke(0x08002FF0, bytes(range(16)))
        m = packmem.Memory('gba', ra.addr)
        self.assertEqual(m.status(), {'state': 'PLAYING', 'system': 'game_boy_advance', 'title': 'Sample', 'crc32': '1053dce4'})
        self.assertTrue(m.begin())
        self.assertEqual([m.u(0x02000250, 4)] + [m.u(0x02000000 + a, 1) for a in range(0, 4096, 64)], [1234] + [ra.ram[0x02000000][a] for a in range(0, 4096, 64)])
        self.assertEqual(ra.reads(), [('2000000', '4096')])  # 65 values, one request
        self.assertEqual(m.read(0x02001FFE, 3), b'\xAA\xBB\xCC')  # across a page border: the two pages that were missing, together
        self.assertEqual(ra.reads()[1:], [('2001000', '8192')])
        self.assertEqual((m.u(0x03000010, 1), m.u(0x08002FFE, 2), m.read(0x08002FFC, 8)), (0, 0x0F0E, bytes([12, 13, 14, 15, 0, 0, 0, 0])))  # past the end of the ROM: zeros
        self.assertEqual(m.u(0x04000000, 2), 0)  # nothing mapped there: zero, not an error
        before = len(ra.reads())
        self.assertTrue(m.begin())  # next tick: everything in use comes with one request per region; the ROM is not asked again
        self.assertEqual(ra.reads()[before:], [('2000000', '12288'), ('3000000', '4096')])
        self.assertEqual((m.u(0x02000250, 4), m.u(0x08002FFE, 2), m.u(0x04000000, 2)), (1234, 0x0F0E, 0))
        self.assertEqual(len(ra.reads()), before + 2)
        ra.poke(0x02000250, struct.pack('<I', 99))
        self.assertEqual(m.u(0x02000250, 4), 1234)  # one tick sees one state …
        m.begin(); self.assertEqual(m.u(0x02000250, 4), 99)  # … the next one the new values
        for _ in range(6): m.begin()
        self.assertEqual(m.hot, {})  # what is no longer used is no longer fetched
        gb = packmem.Memory('gb', ra.addr)
        gb.begin(); [gb.u(0xC000 + a, 1) for a in range(0, 0x300, 16)]
        before = len(ra.reads())
        gb.begin()
        self.assertEqual(ra.reads()[before:], [('c000', '768')])
        self.assertEqual(gb.u(0xDFFF, 2), 0)  # the last byte of work RAM and one that is not there
        ra.poke(0xD123, b'\x11'); ra.poke(0x11123, b'\x33')  # work RAM bank 1 at its place, bank 3 where Gambatte's memory map keeps it
        gb.begin()
        self.assertEqual((gb.bank8(1, 0xD123), gb.bank8(3, 0xD123), gb.bank8(3, 0xC000), gb.bank8(3, 0xD124), gb.bank8(0, 0xD123)), (0x11, 0x33, ra.ram[0xC000][0], 0, 0x11))
        self.assertEqual(ra.reads()[-2:], [('d100', '256'), ('11100', '256')])
        ra.sock.close()
        start = time.time()
        self.assertFalse(m.begin() and m.u(0x02000250, 4) is not None)  # RetroArch is gone: no value …
        self.assertIsNone(m.u(0x02000250, 4)); self.assertIsNone(m.read(0x03000000, 16))
        self.assertLess(time.time() - start, 1)  # … and only one wait for it
        m.close(); gb.close()

    def test_pictures_from_memory(self):
        ra = FakeRetroArch()
        tile = bytes([0x21, 0x43, 0x65, 0x87] * 8)  # colours 1..8 along each row
        ra.poke(0x08000100, tile + tile); ra.poke(0x08000400, struct.pack('<16H', *(0x1F if n == 1 else 0x3E0 if n == 2 else n << 10 for n in range(16))))
        ra.poke(0x08000800, struct.pack('<4H', 0, 0x400, 0x800, 1))  # the map: plain, mirrored, upside down, the second tile
        m = packmem.Memory('gba', ra.addr)
        g = packmem.Gfx(m)
        m.begin()
        key = g.call('tilemap', json.dumps({'tiles': 0x08000100, 'map': 0x08000800, 'palette': 0x08000400, 'stride': 2, 'width': 16, 'height': 16}))
        self.assertEqual(key, g.call('tilemap', json.dumps({'tiles': 0x08000100, 'map': 0x08000800, 'palette': 0x08000400, 'stride': 2, 'width': 16, 'height': 16})))
        image = g.image(key)
        self.assertEqual((image.width(), image.height()), (16, 16))
        self.assertEqual([image.pixel(x, 0) for x in (0, 1, 15, 14)], [0xFFF80000, 0xFF00F800, 0xFFF80000, 0xFF00F800])  # red, green; mirrored on the right
        key = g.call('decode', json.dumps({'tiles': 0x08000100, 'palette': 0x08000400, 'width': 8, 'height': 8}))
        self.assertEqual(g.image(key).pixel(1, 7), 0xFF00F800)
        packed = bytes([0x10, 64, 0, 0, 0b00001111]) + tile[:4] + bytes([0xF0, 3, 0xF0, 3, 0xF0, 3, 0x30, 3])  # LZ77: four bytes, then four times "repeat"
        ra.poke(0x08001000, packed)
        self.assertEqual(g.lz77(0x08001000), tile + tile)
        with self.assertRaises(ValueError): g.lz77(0x08000100)
        with self.assertRaises(ValueError): g.call('tilemap', json.dumps({'tiles': 1, 'map': 2, 'palette': 3, 'width': 12, 'height': 8}))
        key = g.call('sprite', json.dumps({'tiles': 0x08000100, 'palette': 0x08000400, 'width': 8, 'height': 8, 'parts': [{'w': 8, 'h': 8, 'tile': 0, 'bank': 0, 'hflip': True}]}))
        self.assertEqual(g.image(key).pixel(7, 0), 0xFFF80000)
        ra.poke(0x02001000, struct.pack('<2I', 1, 0)); ra.poke(0x02002000, bytes(8) + struct.pack('<4H', 0, 0, 0, 0))  # a 2 x 1 map of 16-pixel cells
        ra.poke(0x05000000 - 0x05000000 + 0x03000000, struct.pack('<3H', 0x7FFF, 0x1F, 0x3E0))
        key = g.call('layers', json.dumps({'x': 0, 'y': 0, 'width': 20, 'height': 8, 'scale': 2, 'palette': 0x03000000, 'layers': [
            {'grid': 0x02001000, 'stride': 2, 'cellBytes': 4, 'gridW': 2, 'gridH': 1, 'idMask': 0xFFF, 'metatiles': 0x02002000, 'tiles': 0x08000100}]}))
        image = g.image(key)
        self.assertEqual([hex(image.pixel(x, 0)) for x in (0, 15, 16)], ['0xff00ff00', '0xffffffff', '0x0'])  # the tile's green; the backdrop where it has none; clear outside the map
        ra.sock.close(); m.close()

    def test_layout_and_visibility(self):
        folder = base.TMP / 'packs-test/sample-pack'
        sample_pack(folder)
        tree = packcss.Tree(SAMPLE_LAYOUT, [(SAMPLE_CSS, str(folder))], str(folder))
        self.assertEqual(tree.sheet.warnings, ['skipped selector: .gone + .x'])
        nodes = []
        tree.walk(tree.root, nodes.append)
        by = lambda name: [n for n in tree_nodes() if n.name == name]
        def tree_nodes():
            found = []
            tree.walk(tree.root, found.append)
            return found
        party = [{'name': 'Isaac', 'level': 5, 'hp': 30, 'maxHp': 40, 'low': False}, {'name': 'Garet', 'level': 7, 'hp': 10, 'maxHp': 50, 'low': True},
                 {'name': 'Ivan', 'level': 4, 'hp': 0, 'maxHp': 0, 'low': True}]
        tree.update({'waiting': True, 'ready': False})
        tree.layout()
        self.assertEqual((tree.shown(by('wait')[0]), tree.shown(by('stage')[0])), (True, False))
        tree.update({'waiting': False, 'ready': True, 'party': party, 'coins': 1234, 'math': '48 16 3'})
        tree.layout()
        self.assertEqual((tree.shown(by('wait')[0]), tree.shown(by('stage')[0])), (False, True))
        self.assertEqual(tree.root.rect, (0.0, 0.0, 538.0, 468.0))
        self.assertEqual((by('coins')[0].text, by('coins')[0].rect), ('1234 G', (10.0, 10.0, 100.0, 40.0)))  # a fixed width in a row, stretched to its height
        self.assertEqual(by('math')[0].rect, (120.0, 10.0, 408.0, 40.0))  # flex: 1 takes the rest after the gap
        mons = by('mon')
        self.assertEqual([m.rect for m in mons], [(10.0, 58.0, 255.0, 50.0), (273.0, 58.0, 255.0, 50.0), (10.0, 116.0, 255.0, 50.0)])  # a grid of two columns, var(--gap) between
        self.assertEqual([m.style['border-top-color'] for m in mons], ['#ffffff', '#ff0000', '#ff0000'])  # classIf
        self.assertEqual([m.children[0].get('color') for m in mons], ['#ffff00', '#ffffff', '#ffff00'])  # :nth-child(2n + 1) > .name
        fills = [m.children[1].children[0] for m in mons]
        self.assertEqual([round(f.rect[2], 2) for f in fills], [round(239 * 0.75, 2), round(239 * 0.2, 2), 0.0])  # value / max of the bar's width
        self.assertEqual([m.children[1].children[1].text for m in mons], ['30/40', '10/50', '0/0'])
        self.assertEqual(by('poke')[0].rect[1], 174.0)  # the button follows the list
        self.assertFalse(tree.shown(by('who')[0].parent))  # the other page is not laid out
        tree.update({'waiting': False, 'ready': True, 'party': [], 'coins': 0})
        empty = next(n for n in by('party')[0].children if n.type == 'empty')
        self.assertEqual((by('mon'), tree.shown(empty), empty.text), ([], True, 'leer'))
        tree.update({'waiting': False, 'ready': True, 'party': party, 'detail': party[1]})
        seen, called = [], []
        tree.on_ui, tree.on_call = seen.append, lambda name, args: called.append((name, args))
        tree.tap(by('mon')[1])  # onClick: remember the row, open the page
        self.assertEqual((tree.ui, seen[-1]), ({'page': 'detail', 'selected': 1}, {'page': 'detail', 'selected': 1}))
        tree.layout()
        self.assertEqual((tree.shown(by('who')[0].parent), by('who')[0].text, by('pic')[0].rect[2:], by('pic')[0].image.width()), (True, 'Garet L7', (64.0, 64.0), 8))
        tree.tap(by('back')[0])
        self.assertEqual(tree.ui['page'], 'party')
        tree.update({'ready': True, 'coins': 7, 'party': party, 'ui': {'navigate': 'detail'}})  # the script may turn the page itself …
        self.assertEqual(tree.ui['page'], 'detail')
        tree.update({'ready': True, 'coins': 7, 'party': party, 'ui': {'back': True}})
        self.assertEqual(tree.ui['page'], 'party')
        tree.tap(by('poke')[0])
        self.assertEqual(called, [('poke', [7])])  # a whole {…} keeps its type
        mon = by('mon')[0]
        tree.press(mon, True); self.assertEqual(mon.get('opacity'), '.5')  # :pressed
        tree.press(mon, False); self.assertEqual(mon.get('opacity'), '1')
        image = QImage(538, 468, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = ui.QPainter(image)
        tree.paint(painter)
        painter.end()
        self.assertEqual([hex(image.pixel(x, y)) for x, y in ((2, 2), (11, 59), (274, 59))], ['0xff101020', '0xffffffff', '0xffff0000'])  # background, a white frame, a red one
        self.assertEqual(sorted({n.name for _, n in tree.clicks}), ['mon', 'poke', 'wide'])
        small = packcss.Tree(SAMPLE_LAYOUT, [(SAMPLE_CSS, str(folder))], str(folder), width=280, height=400)  # @media: one column on a narrow screen
        small.update({'ready': True, 'party': party})
        small.layout()
        found = []
        small.walk(small.root, found.append)
        self.assertEqual([n.rect[:3] for n in found if n.name == 'mon'], [(10.0, 58.0, 260.0), (10.0, 116.0, 260.0), (10.0, 174.0, 260.0)])
        self.assertEqual(packcss.length('calc(100% - 24px)'), (-24.0, 100.0))
        self.assertEqual((packcss.length('clamp(14px, 4vw, 22px)'), packcss.length('2em', 10.0), packcss.length('auto')), ((21.52, 0.0), (20.0, 0.0), None))
        tree.close(); small.close()


@unittest.skipUnless(ui, 'PySide6 fehlt')
class Looks(unittest.TestCase):
    def test_theme_files(self):
        default = ui.read_theme('toravo')
        self.assertEqual({k: default[k] for k in ('colors', 'fonts', 'radius', 'glow', 'gradient', 'gameAccent')}, {k: ui.DEFAULT_THEME[k] for k in ('colors', 'fonts', 'radius', 'glow', 'gradient', 'gameAccent')})  # the shipped default is the built-in look
        studio = ui.read_theme('studio')
        self.assertEqual((studio['name'], studio['colors']['accent'], studio['gradient'][0], studio['fonts']['body'][0]), ('Studio', '#8a5cf6', '#8a5cf6', 'Inter'))
        self.assertEqual((ui.read_theme('oled')['colors']['bg'], ui.read_theme('oled')['glow']), ('#000000', 0.0))
        self.assertGreater(ui.luminance((0xf3, 0xf4, 0xf8)), .8)  # "Hell" is a light theme
        folder = ui.THEME_DIRS[1]
        base.touch(folder / 'kaputt.json', '{"name": "Kaputt", "colors": ')
        base.touch(folder / 'halb.json', '{"name": "Halb", "colors": {"accent": "#00cc66", "bg": "rot", "text": 7}, "radius": "rund", "glow": 9, "fonts": {"body": []}, "gradient": ["#000000"], "gameAccent": false, "background": "fehlt.jpg"}')
        self.assertEqual(ui.read_theme('kaputt')['colors'], ui.DEFAULT_THEME['colors'])  # unreadable: the built-in look, no crash
        self.assertEqual(ui.read_theme('gibtsnicht')['id'], 'toravo')
        half = ui.read_theme('halb')
        self.assertEqual((half['colors']['accent'], half['colors']['bg'], half['colors']['text'], half['radius'], half['glow'], half['fonts'], half['gradient'], half['gameAccent'], half['background']),
                         ('#00cc66', '#07080b', '#f5f5f7', 1.0, 1.0, ui.DEFAULT_THEME['fonts'], None, False, None))  # what is wrong keeps its default, the rest counts
        ui.apply_theme(half)
        self.assertEqual((ui.FOCUS.name(), ui.INK.name()), ('#00cc66', '#07080b'))
        ui.apply_theme(ui.read_theme('toravo'))
        self.assertEqual(ui.FOCUS.name(), '#ffb23e')
        # iiSU Aero OLED & iiSU Pearl flagship themes + spring physics
        aero = ui.read_theme('iisu-aero')
        pearl = ui.read_theme('iisu-pearl')
        self.assertEqual((aero['name'], aero['colors']['accent']), ('iiSU Aero OLED', '#38bdf8'))
        self.assertEqual(pearl['name'], 'iiSU Pearl')
        ui.apply_theme(pearl)
        self.assertTrue(ui.iisu_fx.is_light())
        ui.apply_theme(ui.read_theme('toravo'))
        self.assertFalse(ui.iisu_fx.is_light())

    def test_game_accent(self):
        red, grey = [(200, 30, 40)] * 300 + [(20, 20, 20)] * 200 + [(240, 240, 240)] * 76, [(90, 90, 90)] * 500 + [(200, 30, 40)] * 5
        self.assertIsNone(ui.dominant(grey))  # a few specks are no colour
        self.assertIsNone(ui.dominant([]))
        r, g, b = ui.dominant(red)
        self.assertTrue(r > 180 and g < 90 and b < 100)
        self.assertEqual(ui.dominant([(30, 60, 200)] * 300 + [(200, 30, 40)] * 100)[2] > 180, True)  # the larger area wins
        self.assertAlmostEqual(ui.contrast((255, 255, 255), (0, 0, 0)), 21, 1)
        dark, light = (10, 12, 19), (243, 244, 248)
        for colour in ((60, 20, 120), (200, 30, 40), (250, 240, 60), (20, 40, 160)):
            self.assertGreaterEqual(ui.contrast(ui.readable(colour, dark), dark), 4.5)  # readable on the dark themes …
            self.assertGreaterEqual(ui.contrast(ui.readable(colour, light), light), 4.5)  # … and on the light one
        self.assertEqual(ui.readable((255, 178, 62), dark), (255, 178, 62))  # already fine: untouched


@unittest.skipUnless(ui, 'PySide6 fehlt')
class PipboyState(unittest.TestCase):
    def test_what_counts_as_a_change(self):
        d, same = pipboy_state(), pipboy_state()
        same['player.stats'].update(hp=181.9, ap=82.7); same['player.location']['x'] += 300; same['world.time']['hour'] += .2
        for tab, sub in ((pipboy.T_STAT, 0), (pipboy.T_INV, 0), (pipboy.T_RADIO, 0), (pipboy.T_FAV, 0), (pipboy.T_DATA, 0)): self.assertEqual(pipboy.visible(d, tab, sub), pipboy.visible(same, tab, sub))
        self.assertNotEqual(pipboy.visible(d, pipboy.T_DATA, 1), pipboy.visible(same, pipboy.T_DATA, 1))  # the WORLD page shows time and position
        same['player.stats']['hp'] = 180.2
        self.assertNotEqual(pipboy.visible(d, pipboy.T_INV, 0), pipboy.visible(same, pipboy.T_INV, 0))  # the footer shows whole hit points
        same = pipboy_state(); same['player.inventory'][5]['count'] = 2  # junk changes: only its own list repaints
        self.assertEqual(pipboy.visible(d, pipboy.T_INV, 0), pipboy.visible(same, pipboy.T_INV, 0))
        self.assertNotEqual(pipboy.visible(d, pipboy.T_INV, 4), pipboy.visible(same, pipboy.T_INV, 4))
        self.assertEqual(pipboy.visible({'game': {'ready': True, 'player': False}}, 0, 0), (False,))

    def test_lists_and_formats(self):
        d = pipboy_state()
        self.assertEqual([o['name'] for o in pipboy.inventory_of(d, 0)][:3], ['10-mm-Pistole', 'Baseballschläger', 'Waffe 00'])  # the drawn weapon first, then by name
        self.assertEqual([o['name'] for o in pipboy.inventory_of(d, 3)], [])
        slots, stim, stim_n, rad, rad_n = pipboy.favourites(d)
        self.assertEqual((slots[3]['name'], slots[0]['name'], slots[1], stim_n, rad, rad_n), ('10-mm-Pistole', 'Stimpak', None, 4, None, 0))
        self.assertEqual(pipboy.quest_groups(d)[0], ('Raus aus der Zeit', True, [('Geh nach Hause', 'active'), ('Verlasse Vault 111', 'completed')]))
        self.assertEqual(pipboy.quest_groups({'player.quests': [{'quest': 'A', 'objective': 'tu es', 'state': 'active'}, {'quest': 'A', 'objective': ' '}]}), [('A', True, [('tu es', 'active')])])
        self.assertEqual((pipboy.date_string(d['world.time']), pipboy.date_string(None)), ('23.10.2287  09:30', '–'))
        self.assertEqual([pipboy.fmt_weight(w) for w in (0, 1.25, 14.6)], ['–', '1.2', '15'])
        self.assertEqual((pipboy.language(d), pipboy.language({'game': {'lang': 'en'}})), ('de', 'en'))

    def test_ra2_deck_logic(self):
        m = ra2.parse(ra2_state())
        self.assertEqual((m['credits'], m['out'], m['drain'], m['side'], m['radar'], m['view'], m['zoom'], m['groups']), (9500, 150, 100, 1, (7, 4, 2), [1, 0, 2, 1], 125, [(3, 3)] + [(0, 0)] * 4))
        self.assertEqual((m['items'][0], m['supers']), ({'key': 5, 'cost': 800, 'state': ra2.ST_BUILDING, 'progress': 400, 'queued': 1, 'tab': 0}, [{'key': 2 << 16 | 1, 'ready': 0, 'progress': 250, 'seconds': 300}]))
        self.assertEqual([ra2.parse(d) for d in (None, {'v': 1, 'ingame': 0}, {**ra2_state(), 'i': ra2_state()['i'][:-1]})], [None, None, None])  # no game, or a line cut short
        self.assertEqual((ra2.pips(10, 0, 0), ra2.pips(10, 400, 100), ra2.pips(10, 100, 300, True)), ([0] * 10, [3, 3, 2, 2, 1, 1, 0, 0, 0, 0], [4] * 5 + [0] * 5))  # in use, the last 100 spare, the rest; an outage blinks
        self.assertEqual([ra2.speed_label(v) for v in (-1, 0, 1, 4, 6)], ['-', '4x', '4x', '1x', '0.7x'])

    def test_homm3_deck_logic(self):
        self.assertEqual((homm3.plain('Zug… „Ende“ – 5×'), homm3.clean('{Skelette} treffen {#ff0000|hart}')), ('Zug... "Ende" - 5x', 'Skelette treffen hart'))
        art = struct.pack('<III', 2, 1, 2) + struct.pack('<2i', 5, 7) + bytes(range(8)) + b'rest'
        self.assertEqual([homm3.parse_art(d) for d in (art, art[:19], bytes(12), b'')], [(2, 1, [5, 7], bytes(range(8))), None, None, None])  # a piece, one cut short, none
        self.assertEqual([s['id'] for s in homm3.spell_order(homm3_state()['spells'] + [{'id': 9, 'ok': True}], 2)], [4, 9])  # what can be cast comes first

    def test_d2_deck_logic(self):
        head = lambda t: b'D2AM' + bytes((2, t)) + b'\0\0'
        stats = head(d2.STATS) + bytes((2, 3)) + struct.pack('<HIHIHI', 12, 80, 39, 160, 40, 5) + bytes((1,)) + struct.pack('<II', 300 << 8, 400 << 8) + bytes((70, 1, 0))
        s = d2.parse_stats(stats)
        self.assertEqual((d2.kind(stats), s['v'], s['merc'], s['merc_life'] >> 8, s['merc_level'], s['single'], s['waypoints'], d2.resistance(s, 39, 40)),
                         (d2.STATS, {12: 80, 39: 160, 40: 5}, True, 300, 70, True, None, 60))  # Hell: 160 - 100, cap 80
        self.assertEqual(d2.resistance({**s, 'v': {39: 200}}, 39, 40), 75)
        item = struct.pack('<I4sBBBBBBHB', 7, b'hp1 ', d2.BELT, 2, 0, 0x11, 2, 0, 1, 5) + b'Trank'
        self.assertEqual(d2.parse_items(head(d2.ITEMS) + bytes((0, 0, 1)) + item), (0, 0, [{'id': 7, 'code': 'hp1', 'page': d2.BELT, 'x': 2, 'y': 0, 'w': 1, 'h': 1, 'q': 2, 'flags': 0, 'n': 1, 'name': 'Trank'}]))
        self.assertEqual((d2.parse_items(head(d2.ITEMS) + bytes((0, 0, 1)) + item[:-1]), d2.parse_stats(stats[:12]), d2.kind(b'D2AC' + stats[4:]), d2.parse_state(head(2))), (None, None, -1, None))  # cut short, foreign
        info = d2.parse_info(head(d2.EFFECTS) + bytes((1, 1)) + struct.pack('<HHH', 0x8000 | 101, 30, 60) + b'\1ThorTest' + bytes(8))
        self.assertEqual((info['effects'], info['flags'], info['name']), ([(101, 30, 60, True)], 1, 'ThorTest'))
        self.assertEqual((d2.command(d2.CMD_SORT, b'\0\0'), d2.points_command(d2.KIND_KEY, 300, 2, True), d2.deck_item(d2.DI_MOVE, 9, d2.DI_TO_BELT, 1)),
                         (b'D2AC\x01\x18\0\0\0\0', b'D2AC\x01\x13\0\0\2\x2c\1\2\1', b'D2AC\x01\x26\0\0\1\x09\0\0\0\x0a\1\0\0\0\0\0'))
        self.assertEqual((d2.free_spot([{'page': 0, 'x': 0, 'y': 0, 'w': 2, 'h': 3}], 0, 4, 4, 2, 2), d2.free_spot([], 0, 1, 1, 2, 1), [d2.act_of(v) for v in (1, 40, 75, 103, 109)]),
                         ((2, 0), None, [1, 2, 3, 4, 5]))  # first free place row by row; too big; acts by area number
        from decks import d2recipes  # the recipe book: a cube recipe record (3 El runes -> Eld), names by key
        rec = bytearray(4 + d2recipes.RECORD); rec[:4] = struct.pack('<i', 1); rec[4] = 1; rec[4 + 0x10] = 1
        struct.pack_into('<HHHBB', rec, 4 + 0x14, 1, 1, 0, 0, 3); struct.pack_into('<HH', rec, 4 + 0x4C, 0, 2); rec[4 + 0x4C + 8] = d2recipes.KIND_ITEM
        rows = d2recipes.recipes(bytes(rec))
        self.assertEqual((rows[0][1], rows[0][2]['item'], d2recipes.clean('[fs]El-Rune'), d2recipes.recipes(bytes(rec[:-1]))), ([(1, 1, 0, 0, 3)], 2, 'El-Rune', None))
        tables = type('T', (), {'get': lambda self, c: None, 'tier': staticmethod(lambda it: None), 'item_is_index': lambda self, it, t: False})()
        eld = {'cat': 0, 'doable': True, 'parts': [{'n': 3, 'label': 'El-Rune', 'codes': ['r01'], 'type': -1, 'q': 0, 'flags': 0}]}
        el = {'code': 'r01', 'q': 2, 'flags': 0}
        self.assertEqual([d2recipes.status(eld, have, tables) for have in ([el] * 3, [el], [])], [d2recipes.READY, d2recipes.ALMOST, d2recipes.ALMOST])
        self.assertEqual((d2recipes.ingredients(eld), d2recipes.status({**eld, 'doable': False}, [el] * 3, tables)), ('3x El-Rune', d2recipes.NONE))
        ring = b'D2PR\1' + bytes((2, 0, 1)) + bytes((3, 7, 1, 4)) + b'Gold' + bytes((5, 0, 0, 5)) + b'Akara'
        self.assertEqual((d2.parse_ring(ring), d2.parse_ring(b'D2PR\0'), d2.parse_ring(ring[:-2])), ((0, 1, [(3, 7, True, 'Gold'), (5, 0, False, 'Akara')]), None, (0, 1, [(3, 7, True, 'Gold'), (5, 0, False, 'Aka')])))
        # the game files: MPQ hashing, PKWARE explode (blast.c's example), a DC6 frame, a string table
        from decks import d2art
        self.assertEqual((d2art.mpq_hash('(hash table)', 3), d2art.explode(bytes.fromhex('00048224258f807f'), 100)), (0xC3AF3770, b'AIAIAIAIAIAIA'))
        pal = [bytes((i, i, i, 255)) for i in range(256)]
        frame = struct.pack('<6iII', 0, 2, 2, 0, 0, 0, 0, 8) + bytes((2, 5, 6, 0x80, 0x81, 1, 7, 0x80))  # bottom row first
        self.assertEqual(d2art.dc6(struct.pack('<6iI', 6, 1, 0, -1, 1, 1, 28) + frame, pal)[0], (2, 2, 0, 0, bytearray(bytes(4) + pal[7] + pal[5] + pal[6])))
        tbl = struct.pack('<HHi', 0, 1, 1) + bytes(13) + struct.pack('<H', 0) + struct.pack('<BHIIIH', 1, 0, 0, 40, 42, 10) + b'k\0' + 'Höhleÿc1'.encode()
        strings = d2art.Strings(tbl, None, None)
        self.assertEqual((strings.get('k'), strings.get(0), strings.get('x')), ('Höhle', 'Höhle', None))

    def test_kknd2_deck_logic(self):
        m = kknd2.parse(kknd2_state())
        self.assertEqual((m['ingame'], m['dots'], m['pings'], m['sel'][0]['hp'], kknd2.current_queue(m), [kknd2.parse(d) for d in (None, {'game': 1}, {'v': 2})]),
                         (True, [(20.5, 30.5, 0xFF00FF, 0), (22.5, 30.5, 0xFF00FF, 1)], [(10.5, 12.5)], 64, 0, [None, None, None]))
        cards = kknd2.cards(m)  # the vehicle page: a unit in the works (tap builds one more, hold holds it) and a locked one
        self.assertEqual([(c['badge'], c['status'], c['dim'], c['tap'], c['hold']) for c in cards],
                         [('1', '', False, ('produce 31 evolved_giant_beetle 0', None), ('produce 31 evolved_giant_beetle 1', 'ANGEHALTEN')), ('', 'GESPERRT', True, None, None)])
        tech = kknd2.cards({**m, 'tab': kknd2.TECH_TAB})  # research: a free lab, so it can start
        self.assertEqual((tech[0]['line'], tech[0]['status'], tech[0]['tap']), ('STUFE 1/3', 'ÖL 500', ('research 40', 'FORSCHUNG GESTARTET')))
        self.assertEqual([kknd2.cards({**m, 'tab': t}) for t in (0, 2)], [[], []])  # no infantry or building queue yet
        self.assertEqual([kknd2.speed_label(v) for v in (50, 100, 150, 200)], ['0.5X', '1X', '1.5X', '2X'])
        art = kknd2.parse_art(kknd2_art())
        self.assertEqual((len(art), art[0][:4], art[12 + 33][:4], art[12][:4], kknd2.parse_art(kknd2_art()[:-1]), kknd2.parse_art(b'')), (236, (16, 16, 0, 0), (3, 1, 0, 2), (3, 0, 0, 0), None, None))

    def test_cnc_deck_logic(self):
        m = cnc.parse(cnc_state())
        self.assertEqual((m['td'], m['credits'], m['power'], m['drain'], m['side'], m['map'], m['view'], m['groups'], m['group'], m['speed'], m['focus']),
                         (False, 8105, 200, 70, 1, [10, 20, 64, 64], [192, 352, 240, 128], [0, 6, 0, 0], 1, 4, 0))
        self.assertEqual(m['items'], [{'column': 0, 'index': 0, 'key': 5 << 16 | 3, 'cost': 300, 'state': cnc.ST_BUILDING, 'progress': 400},
                                      {'column': 1, 'index': 0, 'key': 3 << 16 | 1, 'cost': 100, 'state': cnc.ST_AVAILABLE, 'progress': 0}])
        self.assertEqual([cnc.parse(d) for d in (None, {'v': 1, 'game': 'td', 'ingame': 0}, {**cnc_state(), 'i': cnc_state()['i'][:-1]})], [None, None, None])  # no mission, or a line cut short
        self.assertEqual([round(cnc.power_height(v, 153, 5), 1) for v in (0, 50, 100, 200, 100000)], [0, 15.1, 30.2, 54.4, 151])  # the game's own curve, capped
        self.assertEqual((cnc.ascii('GEBÄUDE - PRIMÄR'), sorted(k for k in cnc.layout(True, 360) if isinstance(k, str))[:3]), ('GEBAUDE - PRIMAR', ['alert', 'base', 'credits']))

    def test_aok_deck_logic(self):
        m = aok.parse(aok_state())
        self.assertEqual((m['stock'], m['pop'], m['cap'], m['map'], m['view'], m['speed'], m['groups']), ([200, 180, 100, 150], 4, 5, (3, 4, 2), [(0, 0), (4, 0), (4, 2), (0, 2)], 150, [2, 0, 0, 0]))
        self.assertEqual(m['commands'][1], {'kind': 0, 'icon': (50706, 3), 'enabled': True, 'affordable': False, 'count': -1, 'name': 'Haus', 'help': 'Haus bauen (Q)'})
        self.assertEqual((m['commands'][15]['kind'], m['queue'], m['goto']), (aok.KIND_CAPTION, [{'slot': 0, 'count': 2, 'icon': (50730, 15)}], [{'entry': 0, 'count': 1, 'icon': (50706, 7), 'name': 'Dorfzentrum'}]))
        self.assertEqual([aok.parse(d) for d in (None, {'v': 1, 'ingame': 0}, {**aok_state(), 'i': aok_state()['i'][:-1]})], [None, None, None])  # no game, or a line cut short

    def test_hev_deck_logic(self):
        self.assertEqual(portsocket.split_lines(b'{"a":1}\n#radar 4\n\n{"x{"b":2}\nnoise\n{"c"'), ([{'a': 1}, ('radar', b'\n{"x'), {'b': 2}], b'{"c"'))  # a block's bytes are not lines
        self.assertEqual(portsocket.split_lines(b'{"a":1}\n#radar 4\nAB'), ([{'a': 1}], b'#radar 4\nAB'))  # a block that is still on its way waits whole
        self.assertEqual([hev.chapter(m) for m in ('c1a0d', 'c2a4', 'c2a4e', 'of1a5b', 'ba_xen3', 'unknown', '')],
                         ['Anomalous Materials', 'Residue Processing', 'Questionable Ethics', '"We Are Pulling Out"', 'Focal Point', None, None])
        self.assertEqual((hev.chapter('ba_teleport2', 'ba_xen6'), hev.chapter('ba_teleport2', 'ba_power2')), ('Focal Point', 'A Leap of Faith'))
        self.assertEqual([hev.pickup_name(*f) for f in (('a', 'weapon_9mmAR#2'), ('a', 'weapon_shotgun'), ('w', 'weapon_rpg'), ('i', 'item_battery'), ('i', 'item_new_thing'))],
                         ['Granaten', 'Schrotflinte', 'Raketenwerfer', 'HEV-Batterie', 'New thing'])
        tokens = b'GameHeader\0mapName\0comment\0'  # a saved game's start: header, token table, the GameHeader block with two fields
        save = struct.pack('<5i', 0x5641534A, 0x71, 0, 3, len(tokens)) + tokens + struct.pack('<hhB', 1, 0, 2) + struct.pack('<hh', 4, 2) + b'abc\0' + struct.pack('<hh', 7, 1) + b'c2a3b\0\0'
        self.assertEqual((hev.save_map(save), hev.save_map(save[:30]), hev.save_map(b'nothing')), ('c2a3b', '', ''))
        txt = 'weapon 320 320hud1 0 0 80 20\nweapon 640 640hud1 0 2 3 2\nweapon 1280 gone 0 0 9 9\nammo 640 640hud7 0 0 24 24\n'
        self.assertEqual(hev.sprite_entry(txt, lambda sheet: sheet != 'gone'), ('640hud1', 0, 2, 3, 2))
        pixels = bytes([0, 0, 0, 0,  0, 0, 0, 0,  1, 2, 1, 0,  2, 2, 1, 0])  # a 4x4 sheet; palette: black, dim grey, white
        spr = struct.pack('<4if2iifiH', 0x50534449, 2, 0, 1, 1.0, 4, 4, 1, 0.0, 0, 3) + bytes([0, 0, 0, 60, 60, 60, 255, 255, 255]) + struct.pack('<5i', 0, 0, 0, 4, 4) + pixels
        self.assertEqual(hev.sprite_mask(spr, 0, 2, 3, 2), (3, 2, bytes([19, 255, 19, 255, 255, 19])))  # the dim background is cut down, bright is solid
        self.assertIsNone(hev.sprite_mask(spr, 0, 0, 4, 2))  # nothing bright in there: no icon
        d = hev_state()
        self.assertEqual(hev.hazards(d), [('Strahlung', 'amber')])
        self.assertEqual([hev.status(*a) for a in ((d, True, False), (d, True, True), (d, False, False), ({**d, 'hp': 20, 'dmg': 0}, True, False), ({**d, 'dead': 1}, True, False))],
                         [('Warnung', 'amber'), ('Pausiert', 'teal'), ('Bereitschaft', 'text3'), ('Kritisch', 'red'), ('Nulllinie', 'red')])
        self.assertEqual(hev.visible(d), hev.visible({**d, 't': 9.0, 'seq': 99, 'yaw': 45.4}))  # time passing and a twitch of the stick: no repaint
        self.assertNotEqual(hev.visible(d), hev.visible({**d, 'hp': 81}))

    def test_websocket_frames(self):
        for text in ('{"type":"heartbeat"}', 'ä' * 300, 'x' * 70000):
            frames, rest = pipboy.ws_frames(pipboy.ws_frame(text) + b'\x81')  # the next frame has only begun
            self.assertEqual((frames, rest), ([(True, 1, text.encode())], b'\x81'))
        part = pipboy.ws_frame('abc')[:5]
        self.assertEqual(pipboy.ws_frames(part), ([], part))  # not complete yet: nothing is taken
        self.assertEqual(pipboy.ws_frames(b'\x81\x03abc\x89\x00'), ([(True, 1, b'abc'), (True, 9, b'')], b''))  # unmasked, as a server sends


@unittest.skipUnless(ui, 'PySide6 fehlt')
class FfixState(unittest.TestCase):
    def test_what_counts_as_a_change(self):
        st, same = ffix_state(True), ffix_state(True)
        sig = lambda s, mode=ffix.ENEMIES, party=True: ffix.signature(s, mode, party)
        same['party'][1]['atb'] += 0.1; same['battle']['enemies'][0]['atb'] = 33; same['playTime'] += 0.4; same['world']['x'] += 0.2
        self.assertEqual(sig(st), sig(same))  # below a pixel, or not on screen in this view
        same['party'][1]['atb'] += 4
        self.assertNotEqual(sig(st), sig(same))
        self.assertEqual(sig(st, party=False), sig(same, party=False))  # party column folded away
        same = ffix_state(True); same['battle']['enemies'][1]['hp'] -= 1
        self.assertNotEqual(sig(st), sig(same))
        same = ffix_state(); same['world']['x'] += 0.2
        self.assertEqual(sig(ffix_state(), ffix.T_ITEMS), sig(same, ffix.T_ITEMS))
        self.assertNotEqual(sig(ffix_state(), ffix.T_MAP), sig(same, ffix.T_MAP))

    def test_view_and_formats(self):
        st = ffix_state()
        self.assertEqual(ffix.view_mode(ffix_state(True), ffix.T_AUTO, None), ffix.ENEMIES)
        self.assertEqual(ffix.view_mode(st, ffix.T_AUTO, None), ffix.T_MAP)
        self.assertEqual(ffix.view_mode({**st, 'world': None}, ffix.T_AUTO, None), ffix.T_ITEMS)
        self.assertEqual(ffix.view_mode({**st, 'world': None}, ffix.T_AUTO, st), ffix.T_MAP)  # the world map was seen before
        self.assertEqual(ffix.view_mode({**st, 'scene': 'menu'}, ffix.T_AUTO, st), ffix.T_ITEMS)
        self.assertEqual(ffix.view_mode(ffix_state(True), ffix.T_KEY, None), ffix.T_KEY)
        self.assertEqual((ffix.fmt_time(24690.7), ffix.fmt_gil(48213), ffix.fmt_gil(7)), ('6:51:30', '48.213', '7'))
        self.assertEqual([ffix.treasure_rank(t) for t in (0, 200, 262, 339, 340)], ['H', 'G', 'D', 'A', 'S'])
        self.assertEqual([ffix.language(s) for s in (None, {'lang': 'GR'}, {'lang': 'US'}, {})], ['de', 'de', 'en', 'de'])


@unittest.skipUnless(ui, 'PySide6 fehlt')
class Views(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.setUpModule()
        library = tandem.Library([str(base.SD / 'ROMs')], base.HOME / '.local/share/Steam')
        library.scan()
        cls.service = tandem.Tandem(library, dry=True)
        cls.service.setup['open'] = False  # the walk-through starts past the first-run assistant
        tandem.change = lambda key, value: {'error': 'Selbsttest'}  # on a real Thor the check must not turn the volume up …
        tandem.KEYBOARD.press = lambda code, mods: {'ok': True}  # … or type into the window in front
        cls.actions = []
        tandem.action = lambda name: cls.actions.append(name) or {'ok': True}  # … and never switch it off
        cls.game = ThreadingHTTPServer(('127.0.0.1', 0), FakeGame)
        cls.game.daemon_threads = True
        threading.Thread(target=cls.game.serve_forever, daemon=True).start()
        ffix.Deck.ADDR = cls.game.server_address
        socketserver.ThreadingTCPServer.daemon_threads = True
        cls.fallout = socketserver.ThreadingTCPServer(('127.0.0.1', 0), FakeFallout)
        threading.Thread(target=cls.fallout.serve_forever, daemon=True).start()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), tandem.handler(cls.service))
        cls.server.daemon_threads = True
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        ui.ADDR = cls.server.server_address
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        picture, buf = QImage(96, 120, QImage.Format.Format_RGB32), QBuffer()
        picture.fill(Qt.GlobalColor.darkCyan); buf.open(QBuffer.OpenModeFlag.WriteOnly); picture.save(buf, 'PNG')
        FakeGame.png = bytes(buf.data())
        for file in (HERE / 'fonts').glob('*.ttf'): QFontDatabase.addApplicationFont(str(file))
        cls.top, cls.bottom = ui.Tandem('top'), ui.Tandem('bottom')
        cls.top.resize(1920, 1080); cls.bottom.resize(1240, 1080)
        cls.top.show(); cls.bottom.show()
        cls.wait(cls, lambda: cls.top.L['games'] and cls.bottom.L['games'] and cls.bottom.CFG)

    def wait(self, done, secs=5):
        end = time.time() + secs
        while time.time() < end:
            self.app.processEvents()
            if done(): return True
            time.sleep(0.01)
        raise AssertionError('Zeit abgelaufen')

    def paint(self, name):
        for win in (self.top, self.bottom):
            win.update()
            for _ in range(5): self.app.processEvents(); time.sleep(0.02)  # pictures arrive from their threads
            if SHOTS: win.screen().grabWindow(win.winId()).save(f'{SHOTS}/{name}-{win.side}.png')

    def tap(self, name, win=None):
        win = win or self.bottom
        win.update()  # the areas are those of the last painting
        for _ in range(4): self.app.processEvents(); time.sleep(0.02)
        rect = next(h[0] for h in reversed(win.hits) if h[3] == name)
        for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QGuiApplication.sendEvent(win, QMouseEvent(kind, rect.center(), rect.center(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.app.processEvents()

    def test_game_start_reaches_a_resting_screen(self):
        bottom, run = self.bottom, {'id': 'x', 't': 'Spiel', 's': 'port', 'emu': 'Port', 'since': int(time.time())}
        bottom.active = 0  # nobody touched it for long: the screen rests
        self.assertTrue(bottom.resting())
        bottom.on_event({'kind': 'state', 'run': run, 'ui': dict(bottom.S), 'from': 'service'})
        self.assertEqual((bottom.RUN, bottom.resting()), (run, False))  # the start wakes it and is taken over
        bottom.active = 0
        bottom.on_event({'kind': 'key', 'a': 'right'})
        bottom.on_event({'kind': 'state', 'run': None, 'ui': dict(bottom.S), 'from': 'service'})
        self.assertIsNone(bottom.RUN)

    def test_quick_menu(self):  # the Thor key: a menu on the bottom screen only, closed by its button or the key again
        top, bottom = self.top, self.bottom
        bottom.SET = {'bt': 50, 'bb': 50, 'vol': 50}
        try:
            for win in (top, bottom): win.on_event({'kind': 'quick'})
            self.assertIsNone(top.QUICK)
            self.assertTrue(bottom.QUICK)
            bottom.off['quick'] = 0
            self.paint('quick')
            names = [h[3] for h in bottom.hits]
            slider = next(h for h in reversed(bottom.hits) if h[3] == 'bb')
            slider[1](slider[0].left())
            self.assertEqual(bottom.SET['bb'], 5)  # never fully dark
            for _ in range(2):
                bottom.off['quick'] = bottom.maxoff.get('quick', 0)
                self.paint('quick-bot')
                names = list(dict.fromkeys(names + [h[3] for h in bottom.hits]))
            bottom.off['quick'] = 0
            for name in ('bt', 'bb', 'vol', 'qwhisper', 'qbot_off', 'qairplane', 'fan:silent', 'Bildschirmfoto', 'Schließen'):
                self.assertIn(name, names)
            self.tap('Schließen')
            self.assertIsNone(bottom.QUICK)
            bottom.on_event({'kind': 'quick'}); bottom.on_event({'kind': 'quick'})
            self.assertIsNone(bottom.QUICK)
        finally:
            bottom.QUICK = None

    def test_power_menu_search_and_doze_guard(self):
        top, bottom = self.top, self.bottom
        # doze guard: dark screens register zero touch targets
        for win in (top, bottom): win.on_event({'kind': 'state', 'run': None, 'ui': dict(win.S), 'doze': True, 'power': False})
        self.paint('doze')
        self.assertEqual((top.hits, bottom.hits), ([], []))
        for win in (top, bottom): win.on_event({'kind': 'state', 'run': None, 'ui': dict(win.S), 'doze': False, 'power': True})
        self.paint('power')
        self.assertIn('pwr:Standby', [h[3] for h in bottom.hits])
        self.tap('pwr:Neu starten')
        self.wait(lambda: top.CONFIRM and bottom.CONFIRM)
        self.tap('Abbrechen')
        self.wait(lambda: not top.CONFIRM and not bottom.CONFIRM)
        # global library search across systems
        bottom.open_tab(1)
        self.paint('pre-search')
        self.tap('Suche')
        self.assertIsNotNone(bottom.PROMPT)
        bottom.PROMPT['value'] = 'Minish'
        self.tap('Fertig')
        self.wait(lambda: top.S.get('q') == 'Minish' and len(top.items()) == 1)
        self.assertEqual(top.items()[0]['t'], 'The Legend of Zelda - The Minish Cap')
        top.go('back')
        self.wait(lambda: not bottom.S.get('q'))

    def test_zy_gallery_deck(self):  # after test_walk_through so drop_deck() does not unload ffix.Deck.ADDR
        from decks import gallery
        bottom = self.bottom
        gal_dir = base.TMP / 'gal'
        gal_dir.mkdir(exist_ok=True)
        for side in ('oben', 'unten'):
            (gal_dir / f'20261119-164500-{side}.png').write_bytes(FakeGame.png)
        items = gallery.scan_items([gal_dir])
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]['oben'] and items[0]['unten'])
        bottom.RUN = {'id': 'app9', 't': 'Aufnahmen', 's': 'app', 'emu': 'Aufnahmen', 'since': time.time(),
                      'port': {'deck': 'gallery', 'socket': str(base.TMP / 'no-mpv.sock'), 'pad': True}}
        bottom.deck = gallery.Deck(bottom, str(base.TMP / 'no-mpv.sock'), [gal_dir])
        self.paint('gallery')
        self.assertIn('Bild: Oben', [h[3] for h in bottom.hits])
        self.tap('Bild: Oben')
        self.paint('gallery-bot')
        self.assertIn('Bild: Unten', [h[3] for h in bottom.hits])
        self.tap('Löschen')  # first tap only arms
        self.paint('gallery-armed')
        self.assertTrue((gal_dir / '20261119-164500-oben.png').exists())
        self.tap('Nochmal tippen')  # second tap deletes both screens' captures
        self.assertFalse((gal_dir / '20261119-164500-oben.png').exists())
        self.assertFalse((gal_dir / '20261119-164500-unten.png').exists())
        bottom.drop_deck()
        bottom.RUN = None

    def test_walk_through(self):
        top, bottom = self.top, self.bottom
        self.paint('systems')  # nothing played yet: the service opens on the systems
        self.assertEqual(bottom.S['tab'], 1)
        self.assertIn('PlayStation', [h[3] for h in bottom.hits])
        top.go('right'); self.wait(lambda: bottom.S['i'] == 1)  # the controller acts on the top window, the bottom one follows
        top.go('left'); self.wait(lambda: bottom.S['i'] == 0)
        self.tap('PlayStation'); self.wait(lambda: top.S['i'] == list(top.L['systems']).index('psx'))  # a tap selects …
        self.tap('PlayStation'); self.wait(lambda: top.S['sys'] == 'psx')  # … the second one opens
        self.paint('games')
        self.wait(lambda: 'media/' in ''.join(ui.ACCENTS))  # the selected game's cover was looked at once, for its colour
        self.assertTrue(ui.ACCENT_FILE.is_file())
        top.go('fav'); self.wait(lambda: self.service.saved.get('fav'))
        top.go('fav'); self.wait(lambda: not self.service.saved.get('fav'))
        top.go('ok'); self.wait(lambda: top.RUN and bottom.RUN and bottom.ACH)  # start (dry run); the achievements were asked for
        bottom.SET = {'bt': 50, 'bb': 50, 'vol': 50}
        bottom.ACH = {'earned': 1, 'total': 2, 'points': 15, 'list': [{'t': 'Erster Schritt', 'd': 'Verlasse das Dorf. ' * 12, 'p': 5, 'e': True}, {'t': 'Zweiter', 'd': 'Noch offen', 'p': 10}] * 6}
        self.paint('ingame')
        self.assertGreater(bottom.maxoff['ach'], 0)  # the list is longer than its space: it scrolls
        slider = next(h for h in bottom.hits if h[3] == 'vol')
        slider[1](slider[0].right())
        self.assertEqual(bottom.SET['vol'], 100)
        top.go('back'); self.assertIn('unten', top.TOAST)
        # the game's own deck: FF IX (a stand-in for the status server inside the game)
        bottom.RUN['deck'], bottom.RUN['appid'] = 'deck/377840.html', '377840'
        self.paint('deck'); self.wait(lambda: bottom.deck and bottom.deck.st and bottom.deck.sprite('face/zidane'))
        self.paint('deck-field')
        self.assertNotIn('Spiel beenden', [h[3] for h in bottom.hits])
        self.tap('Items'); self.paint('deck-Items')
        area = bottom.scrolls[-1][0]  # forty items do not fit: the list follows the finger
        mouse = lambda kind, y: QGuiApplication.sendEvent(bottom, QMouseEvent(kind, QPointF(area.center().x(), y), QPointF(area.center().x(), y), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        mouse(QEvent.Type.MouseButtonPress, area.center().y()); mouse(QEvent.Type.MouseMove, area.center().y() - 100); mouse(QEvent.Type.MouseMove, area.center().y() - 300); mouse(QEvent.Type.MouseButtonRelease, area.center().y() - 300)
        self.assertEqual(bottom.off['ffix3'], 300)
        self.paint('deck-Items-scrolled')
        for name in ('Schlüssel', 'Fähigk.', 'Extras'): self.tap(name); self.paint('deck-' + name)
        self.tap('speed'); self.wait(lambda: FakeGame.commands == ['/cmd/booster/speed'])
        self.tap('«'); self.assertTrue(ui.Tandem.memo['ffix']['party_hidden'])
        self.paint('deck-wide')
        self.tap('»'); self.tap('Auto')
        FakeGame.state = ffix_state(True); self.wait(lambda: bottom.deck.st.get('battle'))
        self.paint('deck-battle')
        bottom.RUN['paused'] = True; self.paint('deck-paused')  # Home: Tandem's own bottom view is back …
        self.assertIn('Start', [h[3] for h in bottom.hits])
        bottom.RUN['paused'] = False; self.paint('deck-resumed')  # … and the deck returns with the game
        self.assertIn('Extras', [h[3] for h in bottom.hits])
        bottom.drop_deck()  # what the end of the game does
        self.assertIsNone(bottom.deck); self.assertNotIn('decks.ffix', sys.modules)
        # Fallout 4: the Pip-Boy (a stand-in for the plugin's WebSocket server); this game has no page, only the native deck
        __import__('decks.pipboy').pipboy.Deck.ADDR = self.fallout.server_address  # dropping a deck unloads the deck modules: this is a fresh one
        bottom.RUN['deck'], bottom.RUN['appid'] = None, '377160'
        self.paint('pip'); self.wait(lambda: bottom.deck and bottom.deck.ready and bottom.deck.d.get('pipboy.Map'))
        self.paint('pip-stat')
        self.tap('S.P.E.C.I.A.L.'); self.paint('pip-special')
        self.tap('INV'); self.paint('pip-inv')
        self.tap('Baseballschläger'); self.wait(lambda: FakeFallout.commands == [('toggle', {'id': '0x0001F669', 'stack': 0})] and 'Ausgerüstet: Baseballschläger' == bottom.deck.toast)
        self.paint('pip-inv-toast')
        self.assertGreater(bottom.maxoff['pipboy-inv0'], 0)  # thirty-two weapons: the list scrolls
        self.tap('SCHROTT'); self.paint('pip-junk')
        self.tap('Klebeband'); self.assertIn('keine Aktion', bottom.deck.toast)  # junk cannot be used
        self.tap('DATEN'); self.paint('pip-quests'); self.tap('WELT'); self.paint('pip-world')
        self.tap('KARTE'); self.paint('pip-map'); self.tap('map'); self.assertTrue(ui.Tandem.memo['pipboy']['zoom']); self.paint('pip-map-zoom')
        self.tap('RADIO'); self.paint('pip-radio'); self.tap('radio'); self.wait(lambda: FakeFallout.commands[-1] == ('radio', {'enable': True}) and bottom.deck.toast == 'RADIO AN')
        self.tap('FAV'); self.paint('pip-fav')
        self.tap('fav4'); self.wait(lambda: FakeFallout.commands[-1] == ('equip', {'id': '0x00004822', 'stack': 0}))
        self.tap('Stimpak'); self.wait(lambda: FakeFallout.commands[-1] == ('use', {'id': '0x00023736', 'stack': 0}) and bottom.deck.toast == 'Benutzt: Stimpak')
        self.tap('RadAway'); self.assertEqual(bottom.deck.toast, 'Kein RadAway mehr')
        self.tap('STAT'); self.tap('STATUS')
        bottom.drop_deck()
        self.assertIsNone(bottom.deck); self.assertNotIn('decks.pipboy', sys.modules)
        bottom.RUN['appid'] = None
        # a native port: Half-Life's HEV deck over the deck socket (a stand-in for the game's client library)
        FakeHalfLife.home = str(base.TMP / 'hl')
        (base.TMP / 'hl/valve/save').mkdir(parents=True)
        (base.TMP / 'hl/valve/save/quick.sav').write_bytes(b'')
        path = str(base.TMP / 'deck.sock')
        game = socketserver.ThreadingUnixStreamServer(path, FakeHalfLife)
        threading.Thread(target=game.serve_forever, daemon=True).start()
        bottom.RUN['port'] = {'deck': 'hev', 'socket': path}
        self.paint('hev'); self.wait(lambda: bottom.deck and bottom.deck.d.get('w') and bottom.deck.hello)
        self.paint('hev-arsenal')
        self.assertNotIn('Spiel beenden', [h[3] for h in bottom.hits])
        self.tap('weapon_crowbar'); self.wait(lambda: FakeHalfLife.commands == ['thor_select 1'])
        self.tap('weapon_9mmAR'); self.assertEqual(bottom.deck.toast, 'Leer')  # no ammunition: nothing is sent
        self.tap('Lampe'); self.tap('Benutzen'); self.wait(lambda: FakeHalfLife.commands[1:] == ['impulse 100', 'thor_use'])
        self.tap('Schnellladen'); self.paint('hev-armed'); self.tap('Nochmal tippen'); self.wait(lambda: FakeHalfLife.commands[-1] == 'loadquick')  # only the second tap loads
        self.tap('SPIELSTÄNDE'); self.wait(lambda: bottom.deck.saves); self.paint('hev-saves')
        self.tap('save:quick'); self.tap('save:quick'); self.wait(lambda: FakeHalfLife.commands[-1] == 'load quick')
        self.tap('SPEICHERN'); self.wait(lambda: FakeHalfLife.commands[-1] == 'save new')
        self.tap('ARSENAL')
        bottom.drop_deck()
        self.assertIsNone(bottom.deck); self.assertNotIn('decks.hev', sys.modules)
        bottom.RUN['port'] = None; game.shutdown(); game.server_close()
        # another native port: the command deck of Age of Kings, with the mini-map and the icons as binary blocks
        path = str(base.TMP / 'aok.sock')
        game = socketserver.ThreadingUnixStreamServer(path, FakeAok)
        threading.Thread(target=game.serve_forever, daemon=True).start()
        bottom.RUN['port'] = {'deck': 'aok', 'socket': path}
        self.paint('aok'); self.wait(lambda: bottom.deck and getattr(bottom.deck, 'map', None) is not None and bottom.deck.icons.get((50706, 3)))
        self.paint('aok-commands')
        self.assertEqual((bottom.deck.map.width(), bottom.deck.icons[50706, 3].pixel(0, 0), bottom.deck.art), (4, 0xFF00FF00, None))
        self.tap('Dorfzentrum'); self.tap('command1'); self.tap('faster'); self.wait(lambda: FakeAok.commands == ['cmd 5 0 0', 'cmd 1 1 0', 'cmd 15 1 0'])
        at = bottom.deck.stage.map(aok.MAP_AREA.center())  # a finger on the middle of the mini-map
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonPress, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.wait(lambda: FakeAok.commands[-1] == 'cmd 2 32768 32768')
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonRelease, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        bottom.deck.press(bottom.deck.stage.map(aok.GROUPS[1].center())); self.wait(lambda: FakeAok.commands[-1] == 'cmd 14 2 0')  # held: the selection becomes group II
        bottom.deck.press(None)
        self.tap('GEHE ZU'); self.tap('goto0'); self.wait(lambda: FakeAok.commands[-1] == 'cmd 12 0 0'); self.paint('aok-goto')
        self.tap('SPIEL'); self.tap('Beenden'); self.paint('aok-game'); self.assertTrue(bottom.deck.is_armed('quit'))  # asks first
        bottom.drop_deck()
        bottom.RUN['port'] = None; game.shutdown(); game.server_close()
        # and the command deck of Red Alert 2: the radar, the cameos and the sidebar art as binary blocks
        path = str(base.TMP / 'ra2.sock')
        game = socketserver.ThreadingUnixStreamServer(path, FakeRa2)
        threading.Thread(target=game.serve_forever, daemon=True).start()
        bottom.RUN['port'] = {'deck': 'ra2', 'socket': path}
        self.paint('ra2'); self.wait(lambda: bottom.deck and bottom.deck.radar is not None and bottom.deck.pics.get(5))
        self.paint('ra2-deck')
        self.assertEqual((bottom.deck.radar.width(), bottom.deck.pics[5].pixel(0, 0), bottom.deck.names[5], bottom.deck.has_art(ra2.CH_SIDE2)), (4, 0xFF00FF00, 'Kraftwerk', False))
        self.tap('Reparieren'); self.tap('item9'); self.tap('item5'); self.tap('Infanterie'); self.tap('ZOOM 125%')  # a building in the works: its tap holds it
        self.wait(lambda: FakeRa2.commands == ['cmd 3 0 0 0', 'cmd 1 0 9 0', 'cmd 1 0 5 1', 'cmd 6 2 0 0', 'zoom 150'])
        at = bottom.deck.stage.map(ra2.RADAR_VIEW.center())  # a finger on the middle of the radar
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonPress, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.wait(lambda: FakeRa2.commands[-1] == 'cmd 2 32768 32768 0')
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonRelease, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        bottom.deck.press(bottom.deck.stage.map(ra2.cell(2, 1).center())); self.wait(lambda: FakeRa2.commands[-1] == 'cmd 8 2 1 0')  # held: the selection becomes group II
        bottom.deck.press(None)
        self.tap('BEENDEN'); self.paint('ra2-armed'); self.assertTrue(bottom.deck.is_armed('quit'))  # asks first
        bottom.drop_deck()
        bottom.RUN['port'] = None; game.shutdown(); game.server_close()
        # and the command deck of Command & Conquer / Red Alert: the snapshot, radar and cameos of the engine Thor Conquer
        path = str(base.TMP / 'cnc.sock')
        game = socketserver.ThreadingUnixStreamServer(path, FakeCnc)
        threading.Thread(target=game.serve_forever, daemon=True).start()
        bottom.RUN['port'] = {'deck': 'cnc', 'socket': path}
        key = 5 << 16 | 3
        self.paint('cnc'); self.wait(lambda: bottom.deck and bottom.deck.radar is not None and bottom.deck.pics.get(key) and bottom.deck.pics.get(3 << 16 | 1) is False)
        self.paint('cnc-deck')
        self.assertEqual((bottom.deck.radar.width(), bottom.deck.pics[key].pixel(0, 0), bottom.deck.names[key], bottom.deck.pics[3 << 16 | 1]), (4, 0xFF00FF00, 'Kraftwerk', False))
        for name in ('Optionen', 'REPARIEREN', 'VERKAUFEN', f'item{key}', f'item{3 << 16 | 1}', 'group2', 'group1', 'BASIS', 'TEMPO', 'SICHERN'): self.tap(name)
        # the menu key, repair, sell, a building in the works is held, a unit is trained, the selected group is looked at, an empty one and a skirmish's quick save only say so
        self.wait(lambda: FakeCnc.commands == ['cmd 5 41 0 0', 'cmd 3 0 0 0', 'cmd 4 0 0 0', f'cmd 1 0 0 {key << 1 | 1}', f'cmd 1 1 0 {(3 << 16 | 1) << 1}', 'cmd 9 1 2 0', 'cmd 8 1 0 0', 'cmd 11 3 0 0'])
        at = bottom.deck.stage.map(bottom.deck.L['radar'].center())  # a finger on the middle of the radar: the middle of the 64 x 64 map
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonPress, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.wait(lambda: FakeCnc.commands[-1] == 'cmd 2 42 52 0')
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonRelease, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        bottom.deck.press(bottom.deck.stage.map(bottom.deck.L['group', 2].center())); self.wait(lambda: FakeCnc.commands[-1] == 'cmd 9 2 1 0')  # held: the selection becomes group 3
        bottom.deck.press(None)
        bottom.deck.press(bottom.deck.stage.map(bottom.deck.L['strip', 0].topLeft() + QPointF(5, 5)))  # the building held: on hold now ...
        self.wait(lambda: FakeCnc.commands[-1] == f'cmd 1 0 0 {key << 1 | 1}' and bottom.deck.cancel[0] == key)
        bottom.deck.press(None)
        bottom.deck.heard({**cnc_state(), 'i': cnc_state()['i'][:32] + [cnc.ST_ON_HOLD] + cnc_state()['i'][33:]})  # ... and given up once the game says so
        self.wait(lambda: FakeCnc.commands[-2:] == [f'cmd 1 0 0 {key << 1 | 1}'] * 2 and bottom.deck.cancel[0] is None)
        self.tap('BEENDEN'); self.paint('cnc-armed'); self.assertTrue(bottom.deck.is_armed('quit'))  # asks first
        bottom.drop_deck()
        bottom.RUN['port'] = None; game.shutdown(); game.server_close()
        # and the deck of KKnD 2: the state, the faction's art, the minimap and the icons of the game OpenRA as binary blocks
        path = str(base.TMP / 'kknd2.sock')
        game = socketserver.ThreadingUnixStreamServer(path, FakeKknd2)
        threading.Thread(target=game.serve_forever, daemon=True).start()
        bottom.RUN['port'] = {'deck': 'kknd2', 'socket': path}
        self.paint('kknd2'); self.wait(lambda: bottom.deck and bottom.deck.art and bottom.deck.minimap is not None and bottom.deck.icons.get('evolved_giant_beetle'))
        self.paint('kknd2-deck')
        self.assertEqual((len(bottom.deck.art), bottom.deck.minimap.width(), bottom.deck.icons['evolved_giant_beetle'].pixel(0, 0)), (12, 4, 0xFF00FF00))
        self.assertNotIn('card:evolved_mammoth', [h[3] for h in bottom.hits])  # a locked card does nothing
        for name in ('INFANTERIE', 'FORSCHUNG', 'card:evolved_giant_beetle', 'group1', 'TEMPO', 'BEWEGEN', 'ANGRIFF', 'MENÜ'): self.tap(name)
        # the vehicle page stays the game's: the taps on the pages only ask the game to turn them
        self.wait(lambda: FakeKknd2.commands == ['tab 0', 'tab 4', 'produce 31 evolved_giant_beetle 0', 'group 0 0', 'speed', 'move', 'mode attack', 'menu'])
        at = bottom.deck.stage.map(bottom.deck.mm[0].center())  # a finger on the middle of the minimap: the middle of the map's bounds
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonPress, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.wait(lambda: FakeKknd2.commands[-1] == 'jump 32.0 32.0')
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonRelease, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        bottom.deck.press(bottom.deck.stage.map(next(r for r, k, _ in bottom.deck.longs if k == ('group', 2)).center()))
        self.wait(lambda: FakeKknd2.commands[-1] == 'group 2 1')  # held: the selection becomes group 3
        bottom.deck.press(None)
        self.tap('BEENDEN'); self.paint('kknd2-armed'); self.assertTrue(bottom.deck.is_armed('quit'))  # asks first
        bottom.deck.heard(None); self.paint('kknd2-idle'); self.tap('MENÜ'); self.wait(lambda: FakeKknd2.commands[-1] == 'menu')  # the game's menus: the idle page
        bottom.drop_deck()
        bottom.RUN['port'] = None; game.shutdown(); game.server_close()
        # and the deck of Heroes III: the state, the minimap as a JSON block, the game's art as binary blocks
        path = str(base.TMP / 'homm3.sock')
        game = socketserver.ThreadingUnixStreamServer(path, FakeHomm3)
        threading.Thread(target=game.serve_forever, daemon=True).start()
        bottom.RUN['port'] = {'deck': 'homm3', 'socket': path}
        self.paint('homm3'); self.wait(lambda: bottom.deck and bottom.deck.minimap is not None and bottom.deck.pics.get('def:RESOURCE:6') and bottom.deck.fonts.get('medium') is False)
        self.paint('homm3-deck')
        self.assertEqual((bottom.deck.minimap.width(), bottom.deck.pics['def:RESOURCE:6'].pixel(0, 0), bottom.deck.pics['img:DIBOXBCK']), (4, 0xFF00FF00, False))
        self.assertNotIn('key adventureNextHero', [h[3] for h in bottom.hits])  # the game says there is no next hero: the button does nothing
        for name in ('key adventureEndTurn', 'hero 7', 'ui:slot 0 1', 'ui:slot 2 1', 'ui:tab 1', 'spell 4', 'ui:tab 3', 'key adventureMainMenu'): self.tap(name)
        self.wait(lambda: FakeHomm3.commands == ['key adventureEndTurn', 'hero 7', 'army 0 2 m', 'spell 4', 'key adventureMainMenu'])  # two slots tapped: the stack moves
        at = bottom.deck.stage.map(bottom.deck.map_rect.center())  # a finger on the middle of the minimap: the middle tile
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonPress, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.wait(lambda: FakeHomm3.commands[-1] == 'tile 2 1')
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonRelease, at, at, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        bottom.deck.heard({**homm3_state(), 'mode': 'battle', 'battle': {'hero': 'Xsi', 'mana': 20, 'manaMax': 20, 'unit': {'name': 'Skelette', 'count': 30, 'icon': 56},
                                                                         'queue': [{'icon': 56, 'count': 30, 'side': 0, 'turn': 0}], 'speed': 2, 'log': ['{Skelette} greifen an']}})
        self.paint('homm3-battle'); self.tap('key battleDefend'); self.tap('speed 3'); self.wait(lambda: FakeHomm3.commands[-2:] == ['key battleDefend', 'speed 3'])
        bottom.deck.heard({'mode': 'menu'})
        self.tap('ui:quit'); self.paint('homm3-armed'); self.assertLess(time.time() - bottom.deck.armed, homm3.CONFIRM)  # asks first
        bottom.drop_deck()
        bottom.RUN['port'] = None; game.shutdown(); game.server_close()
        # an emulated game with a companion pack (stand-ins: RetroArch's memory commands, a small pack of our own)
        ra = FakeRetroArch()
        sample_pack(base.TMP / 'config/tandem/packs/sample-pack')
        __import__('decks.pack').pack.Deck.ADDR = ra.addr
        system = bottom.RUN['s']
        bottom.RUN['pack'], bottom.RUN['s'] = 'sample-pack', 'gba'
        self.paint('pack-start'); self.wait(lambda: bottom.deck and bottom.deck.ready)
        deck = bottom.deck
        names = lambda: [h[3] for h in bottom.hits]
        self.paint('pack-waiting')
        self.assertEqual((deck.tree.snapshot['waiting'], [n for n in names() if n in ('Begleiter', 'Erfolge', 'Steuerung', 'mon', 'Spiel beenden')]), (True, ['Steuerung', 'Erfolge', 'Begleiter']))
        sample_game(ra); ra.poke(0x02000000, bytes([1, 2]))  # the game is past its title screen
        self.wait(lambda: (self.paint('pack'), deck.tree.snapshot.get('ready'))[1])
        self.assertEqual({k: deck.tree.snapshot[k] for k in ('coins', 'math', 'code', 'far')}, {'coins': 1234, 'math': '48 16 3 77', 'code': 'TEST', 'far': 7})
        self.assertEqual([p['name'] for p in deck.tree.snapshot['party']], ['Isaac', 'Garet'])
        self.assertEqual(names().count('mon'), 2)
        tick, before = deck.mem.tick, len(ra.reads())
        self.wait(lambda: deck.mem.tick >= tick + 4)
        asked = ra.reads()[before:]
        self.assertEqual(set(asked), {('2000000', '4096'), ('3000000', '4096')})  # per tick: one request per memory region, the ROM not again
        self.assertLessEqual(len(asked), 2 * (deck.mem.tick - tick + 1))
        self.tap('mon'); self.wait(lambda: (self.paint('pack-detail'), (deck.tree.snapshot.get('detail') or {}).get('name'))[1] == 'Garet')  # a tap: page and values at once
        self.assertEqual(deck.tree.ui, {'page': 'detail', 'selected': 1})
        self.tap('back'); self.assertEqual(deck.tree.ui['page'], 'party')
        self.tap('poke'); self.wait(lambda: (self.paint('pack-action'), deck.tree.ui.get('wrote'))[1] == 'false')  # actions run in the script; writing is refused
        self.assertEqual((deck.tree.ui['got'], ra.ram[0x02000000][0x250]), (1234, 1234 & 255))
        self.assertFalse([w for w in ra.asked if w[0] not in ('GET_STATUS', 'READ_CORE_MEMORY')])  # nothing but reading was ever asked
        ra.poke(0x02000002, b'\x01'); self.wait(lambda: 'instruction budget' in (deck.error or ''))  # the script runs away: stopped, the screen keeps its state
        self.paint('pack-broken'); self.assertEqual(names().count('mon'), 2)
        ra.poke(0x02000002, b'\x00'); ra.poke(0x02000250, struct.pack('<I', 77))
        self.wait(lambda: (self.paint('pack-again'), deck.tree.snapshot['coins'])[1] == 77)  # … and goes on afterwards
        # the reserved wideView switch: N/A without wide(), else the service flips it and the pack shows the state
        posts, post = [], bottom.post
        bottom.post = lambda path, data=None, then=None: posts.append((path, data))
        self.tap('wide'); self.assertEqual((deck.tree.snapshot['_wideLabel'], deck.tree.snapshot['_wide'], posts), ('N/A', 0, []))
        bottom.RUN['wide'] = False; self.paint('pack-wide-off'); self.assertEqual(deck.tree.snapshot['_wideLabel'], 'OFF')
        self.tap('wide'); self.assertEqual(posts, [('api/wide', {'on': 'toggle'})])
        bottom.RUN['wide'] = True; self.paint('pack-wide-on'); self.assertEqual((deck.tree.snapshot['_wideLabel'], deck.tree.snapshot['_wide']), ('ON', 1))
        bottom.post = post; del bottom.RUN['wide']
        self.tap('Steuerung'); self.paint('pack-controls')
        self.assertTrue({'Spiel beenden', 'vol', 'Speichern' if bottom.RUN['emu'] == 'RetroArch' else 'vol'} <= set(names()))
        self.assertNotIn('mon', names())
        self.tap('Erfolge'); self.paint('pack-achievements')
        self.assertTrue(bottom.maxoff['ach'] > 0 and 'Spiel beenden' not in names())
        self.tap('Begleiter'); self.paint('pack-back'); self.assertEqual(names().count('mon'), 2)
        bottom.ACH = None; self.paint('pack-no-ra'); self.assertNotIn('Erfolge', names())  # no RetroAchievements for the game: no such tab
        bottom.drop_deck()
        self.assertFalse([name for name in sys.modules if name.startswith('decks.pack')])  # Lua, memory reader and layout are gone with the game
        bottom.RUN['pack'], bottom.RUN['s'] = None, system
        ra.sock.close()
        # paused: the game stands in front on Start, X asks on both screens, B takes the question back
        for win in (top, bottom): win.RUN['paused'] = True; win.S.update(tab=0, sys=None, i=0)
        self.paint('paused')
        self.assertEqual(top.items()[0]['id'], top.RUN['id'])
        top.go('close'); self.wait(lambda: bottom.CONFIRM)
        self.paint('confirm')
        top.go('back'); self.wait(lambda: not bottom.CONFIRM)
        self.tap('Beenden'); self.wait(lambda: not top.RUN and not bottom.RUN)  # the bar's own button
        # terminal keys, volume display, toast
        bottom.RUN = top.RUN = {'id': 'term', 't': 'Terminal', 's': 'term', 'emu': 'Terminal', 'since': time.time(), 'layout': 'de'}
        self.paint('terminal')
        self.tap('Strg'); self.assertEqual(bottom.KM, {'ctrl'})
        self.tap('c'); self.assertEqual(bottom.KM, set())
        bottom.RUN = top.RUN = None
        for win in (top, bottom): win.on_event({'kind': 'settings', 'settings': {'vol': 35}, 'osd': 'vol'}); win.on_event({'kind': 'toast', 'text': 'Hallo ' * 30})
        self.assertEqual(top.OSD, 35)
        self.paint('osd')
        for n in range(len(ui.TABS)): bottom.open_tab(n); self.paint(f'tab{n}')
        bottom.open_tab(3); self.paint('apps')  # Apps has an obvious way to the desktop; it asks first
        self.tap('Zum Desktop'); self.tap('Zum Desktop'); self.wait(lambda: top.CONFIRM and bottom.CONFIRM and 'Desktop' in top.CONFIRM['text'])
        self.assertEqual(self.actions, [])  # nothing ran
        self.tap('Abbrechen'); self.wait(lambda: not top.CONFIRM)


    def test_zz_settings(self):  # after the walk-through: it starts from the service's first page
        top, bottom, changes = self.top, self.bottom, []
        fake = {'rgb': {'enabled': True, 'linkBrightness': False, 'brightness': 50, 'maxBrightness': 50, 'color': 'FFFFFF', 'saturation': 100, 'level': 50},
                'gyro': {'supported': True, 'enabled': True}, 'power': {'profile': 'Balanced', 'profiles': [['Eco', 'Sparsam'], ['Balanced', 'Ausgewogen']], 'temp': 40, 'fan': 2000}, 'os': '1'}
        tandem.thor.state = lambda: fake  # never the Thor's real lights and fan while testing on one
        tandem.thor.change = lambda key, value: changes.append((key, value)) or fake
        tandem.settings = lambda: {'bt': 50, 'bb': 50, 'vol': 50}  # the computer running this has no such panels
        tandem.system_info = lambda roots=(), rescan=False: {'ssid': '', 'networks': [{'ssid': 'Daheim', 'signal': 70, 'secure': True, 'known': False, 'active': False}], 'storage': []}  # nor this network
        if self.service.run: self.service.quit()  # whatever an earlier test left running
        self.wait(lambda: not top.RUN and not bottom.RUN)
        for win in (top, bottom): win.CONFIRM = win.THOR = None; win.thor_at = 0; win.drop_deck(); win.SET = tandem.settings()
        names = lambda: [h[3] for h in bottom.hits]
        bottom.open_tab(4); self.wait(lambda: top.S['tab'] == 4 and bottom.SYS and bottom.THOR and top.THOR)
        self.paint('settings')
        self.assertTrue({'Bildschirme & Ton', 'Beleuchtung', 'Ein / Aus', 'Oben', 'vol', 'Schwarz nach:Nie'} <= set(names()))
        # the controller: the list, into an area, change a value, back out
        top.go('down'); top.go('down'); self.wait(lambda: bottom.S.get('page') == 'light')
        top.go('ok'); top.go('down'); self.wait(lambda: bottom.S.get('pane') == 1 and bottom.S['i'] == 1)
        self.paint('settings-light')
        top.go('right'); self.wait(lambda: changes and changes[-1] == ('rgb', {'color': 'FF2000', 'enabled': True}))  # the next colour, sent once
        top.go('up'); top.go('ok'); self.wait(lambda: changes[-1] == ('rgb', {'enabled': False}))  # A switches
        top.go('back'); self.wait(lambda: bottom.S.get('pane') == 0)
        top.go('back'); self.wait(lambda: bottom.S['tab'] == 0)  # B in the list: back to the library
        bottom.open_tab(4); self.wait(lambda: top.S['tab'] == 4)
        # the finger: a sub-page and its way back, always top left
        self.tap('Controller & Tasten'); self.tap('Tastenbelegung'); self.wait(lambda: top.S.get('page') == 'controls>map')
        self.paint('settings-map')
        self.tap('nav-back'); self.wait(lambda: top.S.get('page') == 'controls' and top.S['i'] == 0)
        self.tap('Bildschirme & Ton'); self.tap('Schwarz nach:Nie'); self.wait(lambda: tandem.public_config()['rest_min'] == 0)
        self.tap('Schwarz nach:3 Min.'); self.wait(lambda: tandem.public_config()['rest_min'] == 3)
        self.paint('settings-screens')
        slider = next(h for h in bottom.hits if h[3] == 'vol'); slider[1](slider[0].right())
        self.assertEqual(bottom.SET['vol'], 100)
        self.tap('Ein / Aus'); self.tap('Ausschalten'); self.wait(lambda: top.CONFIRM and bottom.CONFIRM)  # power actions ask first, on both screens
        self.paint('settings-power')
        top.go('back'); self.wait(lambda: not bottom.CONFIRM)
        self.tap('Standby'); self.wait(lambda: top.CONFIRM)
        top.go('ok'); self.wait(lambda: self.actions[-1:] == ['suspend'] and not bottom.CONFIRM)
        self.tap('Aussehen')
        other = next(t for t in bottom.CFG['themes'] if t['id'] != 'toravo')
        self.tap(other['name']); self.wait(lambda: tandem.public_config()['theme'] == other['id'] == ui.THEME['id'])
        self.paint('settings-theme')
        self.tap('Toravo'); self.wait(lambda: tandem.public_config()['theme'] == 'toravo' == ui.THEME['id'])
        self.tap('Ansicht:Bühne'); self.wait(lambda: tandem.public_config()['view_mode'] == 'stage' == bottom.CFG.get('view_mode'))
        bottom.open_tab(0); self.wait(lambda: top.S['tab'] == 0)
        self.paint('stage')
        self.tap('Kacheln'); self.wait(lambda: tandem.public_config()['view_mode'] == 'grid' == bottom.CFG.get('view_mode'))
        bottom.open_tab(4); self.wait(lambda: top.S['tab'] == 4)
        self.tap('Konten'); self.tap('Benutzername'); self.assertTrue(bottom.PROMPT)  # text: the keys on the bottom screen
        for key in ('⇧', 'A', 'b', 'c', '⌫'): self.tap(key)
        self.assertEqual(bottom.PROMPT['value'], 'Ab')
        self.tap('Fertig'); self.wait(lambda: bottom.CFG.get('ra_user') == 'Ab')
        self.tap('WLAN & Netzwerk'); self.tap('WLAN'); self.wait(lambda: top.S.get('page') == 'network>wifi')
        self.paint('settings-wifi')
        self.tap('Daheim'); self.assertIn('Daheim', bottom.PROMPT['title'])
        self.tap('Abbrechen'); self.assertIsNone(bottom.PROMPT)
        # System backup & retroactive Android/Linux storage split inside Bibliothek
        fake_sysbk = {
            'backups': {
                'dest': '/run/media/armada/THOR/Backups/Thor-Linux', 'dest_on_card': True, 'dest_free_gib': 108.9,
                'last': int(time.time()) - 3600, 'last_mode': 'profile', 'last_where': 'SD-Karte + Server',
                'archives': [{'file': 'thor-profile-20261122-154000.tar.zst', 'kind': 'profile',
                              'at': int(time.time()) - 3600, 'size_gb': 1.84, 'items': 28}],
                'job': {'running': False, 'step': '', 'error': ''},
            },
            'storage': {
                'supported': True, 'disk': '/dev/sda', 'sector_size': 4096, 'total_gib': 234.2,
                'userdata_node': '/dev/sda17', 'userdata_num': 17, 'android_gib': 113.0, 'android_min_gib': 8,
                'presets_gib': [16, 24, 32, 48], 'linux_total_gib': 112.2, 'linux_used_gib': 94.1,
                'linux_free_gib': 18.1, 'reclaimable_max_gib': 105, 'extra_chunks': [],
                'job': {'running': False, 'step': '', 'error': ''},
            },
            'cleanup': {
                'total_mb': 1420.5,
                'compatdata': {'count': 2, 'mb': 980.0, 'items': ['413150', '620']},
                'shadercache': {'count': 1, 'mb': 320.5},
                'temp': {'count': 3, 'mb': 120.0},
            },
        }
        old_sysbk = tandem.sysbackup_state
        tandem.sysbackup_state = lambda: fake_sysbk
        try:
            for win in (top, bottom): win.SYSBK = None; win.sysbk_at = 0
            self.tap('Bibliothek'); self.wait(lambda: top.S.get('page') == 'library' and bottom.SYSBK and top.SYSBK)
            self.paint('settings-library')
            self.tap('Speicher-Bereinigung'); self.wait(lambda: top.S.get('page') == 'library>cleanup')
            self.paint('settings-cleanup')
            self.tap('nav-back'); self.wait(lambda: top.S.get('page') == 'library')
            self.tap('Linux- & Tandem-Backup'); self.wait(lambda: top.S.get('page') == 'library>sysbackup')
            self.paint('settings-sysbackup')
            self.tap('nav-back'); self.wait(lambda: top.S.get('page') == 'library')
            self.tap('Android- & Linux-Speicher'); self.wait(lambda: top.S.get('page') == 'library>storage')
            self.paint('settings-storage')
            self.tap('nav-back'); self.wait(lambda: top.S.get('page') == 'library')
        finally:
            tandem.sysbackup_state = old_sysbk
        # Integrated Update & Auto-Companion Center inside Updates
        self.tap('Updates'); self.wait(lambda: top.S.get('page') == 'updates' and bottom.UPDC is not None)
        self.paint('settings-updates')
        self.tap('Spiel-Begleiter'); self.wait(lambda: top.S.get('page') == 'updates>companions')
        self.paint('settings-companions')
        self.tap('nav-back'); self.wait(lambda: top.S.get('page') == 'updates')
        self.tap('Emulatoren & Quellen'); self.wait(lambda: top.S.get('page') == 'updates>apps')
        self.paint('settings-apps')
        self.tap('nav-back'); self.wait(lambda: top.S.get('page') == 'updates')
        bottom.open_tab(1); self.wait(lambda: top.S['tab'] == 1)
        # Touchscreen gestures: system back-pill, top-bezel swipe-down Quick Menu, left-edge swipe-back & top-screen touch pads
        self.tap('PlayStation'); self.tap('PlayStation'); self.wait(lambda: top.S.get('sys') == 'psx')
        self.paint('system-touch-back')
        self.assertIn('sys-back', [h[3] for h in bottom.hits])
        was_fav = bool(top.L.get('fav'))
        self.tap('pad:Y', win=top); self.wait(lambda: bool(top.L.get('fav')) != was_fav)
        self.tap('pad:Y', win=top); self.wait(lambda: bool(top.L.get('fav')) == was_fav)
        self.tap('sys-back'); self.wait(lambda: top.S.get('sys') is None)
        # Swipe down from top bezel of bottom screen opens Quick Menu, left-edge swipe-back closes it
        p0, p1 = ui.QPointF(bottom.width() * 0.5, bottom.u * 1.2), ui.QPointF(bottom.width() * 0.5, bottom.u * 12.0)
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonPress, p0, p0, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseMove, p1, p1, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonRelease, p1, p1, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.app.processEvents()
        self.assertTrue(bottom.QUICK)
        b0, b1 = ui.QPointF(bottom.u * 1.0, bottom.height() * 0.5), ui.QPointF(bottom.u * 14.0, bottom.height() * 0.5)
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonPress, b0, b0, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseMove, b1, b1, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QGuiApplication.sendEvent(bottom, QMouseEvent(QEvent.Type.MouseButtonRelease, b1, b1, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.app.processEvents()
        self.assertIsNone(bottom.QUICK)

    @classmethod
    def tearDownClass(cls):
        for win in (getattr(cls, 'top', None), getattr(cls, 'bottom', None)):
            if win is not None:
                try:
                    win.drop_deck()
                    win.close()
                except Exception:
                    pass
        if getattr(cls, 'app', None):
            cls.app.processEvents()
        cls.top = cls.bottom = None
        super().tearDownClass()


@unittest.skipUnless(ui, 'PySide6 fehlt')
class CompanionDecksAndGameMenuTest(unittest.TestCase):
    def test_universal_dual_and_pcstream_decks(self):
        QGuiApplication.instance() or QGuiApplication(['tandem-test'])
        from decks import dualscreen, pcstream, universal
        w = ui.Tandem('bottom')
        w.resize(1240, 1080)
        w.u, w.fonts = w.width() / 100, {}
        ui.URL = 'http://127.0.0.1:1'
        w.RUN = {'id': 'g1', 't': 'Chrono Trigger', 's': 'sfc', 'emu': 'RetroArch', 'since': int(time.time()) - 120}
        w.SET = {'bt': 60, 'bb': 60, 'vol': 40}
        w.BATT = {'level': 82, 'charging': False}
        img = QImage(1240, 1080, QImage.Format.Format_RGB32)

        def render(deck, shot_name=''):
            w.hits, w.scrolls, w.kb_keys = [], [], []
            p = ui.QPainter(img)
            p.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
            deck.paint(p); p.end()
            if SHOTS and shot_name:
                Path(SHOTS).mkdir(parents=True, exist_ok=True)
                img.save(str(Path(SHOTS) / f'{shot_name}.png'))
            return [h[3] for h in w.hits]

        u_deck = universal.Deck(w)
        # Tab 0: Steuerung keeps standard in-game buttons + adds universal tabs
        h0 = render(u_deck, 'univ-steuerung')
        self.assertTrue({'utab:Steuerung', 'utab:Stände', 'utab:Notizen', 'utab:Guides', 'utab:Musik', 'utab:Cockpit', 'Spiel beenden', 'Speichern', 'Laden'} <= set(h0))
        # Tab 2: Notizen sketch strokes + undo
        u_deck.tab = 2
        render(u_deck)
        u_deck.press(QPointF(300, 400))
        u_deck.move(QPointF(420, 460))
        u_deck.press(None)
        u_deck.save_timer.stop()
        h2 = render(u_deck, 'univ-sketch')
        self.assertIn('sketch:Radierer', h2)
        self.assertEqual(len(u_deck.undo_stack), 1)
        # Tab 5: Cockpit renders wattage/runtime sparklines cleanly
        u_deck.tab = 5
        u_deck.tele = {'battery': {'level': 76, 'charging': False, 'watts': 6.4, 'mins_left': 195},
                       'cpu': 34.0, 'ram_used': 4.8, 'ram_total': 11.6, 'temp': 51, 'fan': 1900, 'profile': 'Balanced',
                       'hist': {'watts': [5.8, 6.2, 6.4, 6.1, 6.5], 'cpu': [28, 35, 34, 31, 36], 'temp': [49, 50, 51, 51, 52]}}
        h5 = render(u_deck, 'univ-cockpit')
        self.assertIn('cprof:Performance', h5)
        u_deck.close()

        # Dual-screen deck (DS / 3DS / Wii U)
        w.RUN['dual'] = True
        d_deck = dualscreen.Deck(w)
        hd = render(d_deck, 'dual-screen')
        self.assertTrue({'dtab:Touchscreen', 'dtab:Notizen', 'dtab:Guides', 'dtab:Cockpit', 'dual_swap'} <= set(hd))
        d_deck.set_tab(1)
        self.assertEqual(d_deck.sub.tab, 2)
        d_deck.close()

        # PC-Stream deck (Moonlight / Chiaki)
        w.RUN = {'id': 'app3', 't': 'Moonlight', 's': 'app', 'emu': 'Moonlight', 'since': int(time.time())}
        p_deck = pcstream.Deck(w)
        hp = render(p_deck, 'pcstream-pad')
        self.assertTrue({'pc_kb', 'pc_wol', 'macro:Esc', 'macro:Alt+Tab', 'mbtn:Linksklick', 'mbtn:Rechtsklick'} <= set(hp))
        p_deck.kb_open = True
        render(p_deck, 'pcstream-kb')
        self.assertGreater(len(w.kb_keys), 25)
        p_deck.close()

        # Redesigned Thor Quick Menu (FPS-Fenster + Quick Game Switcher) + Library Stats page
        w.RUN = {'id': 'g1', 't': 'Chrono Trigger', 's': 'sfc', 'emu': 'RetroArch', 'since': int(time.time()) - 120}
        w.L = {'games': [{'id': 'g1', 't': 'Chrono Trigger', 's': 'sfc'},
                         {'id': 'g2', 't': 'Super Metroid', 's': 'sfc'},
                         {'id': 'g3', 't': 'Metal Gear Solid', 's': 'psx'}],
               'apps': [],
               'systems': {'sfc': {'name': 'Super Famicom'}, 'psx': {'name': 'PlayStation'}},
               'played': {'g1': {'secs': 3600, 'last': int(time.time()) - 300},
                          'g2': {'secs': 1800, 'last': int(time.time()) - 600},
                          'g3': {'secs': 900, 'last': int(time.time()) - 900}},
               'sessions': {time.strftime('%Y-%m-%d'): 2700}}
        w.THOR = {'rgb': {'enabled': True, 'color': '9040FF', 'level': 60},
                  'power': {'profile': 'Balanced', 'profiles': [('Eco', 'Sparsam'), ('Balanced', 'Ausgewogen'), ('Performance', 'Leistung')], 'temp': 47, 'fan': 1850}}
        w.QTELE = {'battery': {'level': 84, 'charging': False, 'watts': 5.8, 'mins_left': 210}}
        w.QUICK = time.time()
        w.hits, w.scrolls = [], []
        pq = ui.QPainter(img)
        pq.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
        ui.quick_view.draw(w, pq); pq.end()
        if SHOTS:
            img.save(str(Path(SHOTS) / 'quick-bento.png'))
        qhits = {h[3] for h in w.hits}
        self.assertTrue({'hud:Aus', 'hud:FPS', 'hud:Leiste', 'hud:Graph', 'qswitch:g2', 'qswitch:g3', 'Ton aus', 'Zu Tandem', 'Spiel beenden'} <= qhits)
        stats_groups = ui.settings_view.groups(w, 'library>stats')
        self.assertEqual([g[0] for g in stats_groups], ['Übersicht', 'Meistgespielt', 'Letzte 7 Tage'])
        self.assertEqual(stats_groups[1][1][0]['t'], 'Chrono Trigger')

        # Universal Deck Tab 6: Switch-2 Precision Mouse Mode + Tab 7: Live German Game Translator (PlayTranslate style)
        u_mouse = universal.Deck(w)
        u_mouse.tab = 6
        hm = render(u_mouse, 'univ-mouse')
        self.assertTrue({'utab:Maus', 'utab:Übersetzen', 'umouse:Linksklick', 'umouse:Halten / Ziehen', 'umouse:Rechtsklick'} <= set(hm))
        u_mouse.set_tab(7)
        u_mouse.tr_view.st['last'] = {
            'source': 'It is dangerous to go alone! Take this magic sword.',
            'translated': 'Es ist gefährlich, alleine zu gehen! Nimm dieses magische Schwert.',
            'reading': '', 'detected': 'en', 'engine': 'offline',
            'words': ['dangerous', 'alone', 'magic', 'sword'], 'at': int(time.time()),
        }
        ht = render(u_mouse, 'univ-translate')
        self.assertTrue({'tr:now', 'tr:auto', 'tr:mode', 'treg:full', 'treg:bottom', 'treg:custom', 'tword:sword'} <= set(ht))
        u_mouse.close()

        # Dual-Screen OLED Screensaver showcase (Thor Kosmos, Arcade, Dual-Aurora)
        w.RUN = None
        w_top = ui.Tandem('top')
        w_top.resize(1920, 1080)
        w_top.u, w_top.fonts = w_top.width() / 100, {}
        w_top.L = w.L = {
            'games': [
                {'id': 'g1', 't': 'Chrono Trigger', 's': 'sfc', 'year': '1995', 'dev': 'Square',
                 'desc': 'Eine Reise durch die Epochen zur Rettung der Welt.', 'cover': 'c1', 'box': 'b1'},
                {'id': 'g2', 't': 'Super Mario Odyssey', 's': 'switch', 'year': '2017', 'dev': 'Nintendo',
                 'desc': 'Entdecke riesige Königreiche an Bord der Odyssee.', 'cover': 'c2', 'box': 'b2'},
                {'id': 'g3', 't': 'Golden Sun', 's': 'gba', 'year': '2001', 'dev': 'Camelot',
                 'desc': 'Magische Alchemie in Weyard.', 'cover': 'c3', 'box': 'b3'},
                {'id': 'g4', 't': 'Metal Gear Solid', 's': 'psx', 'year': '1998', 'dev': 'Konami', 'cover': 'c4'},
                *[{'id': f'gx{i}', 't': f'Klassiker {i}', 's': 'gba', 'cover': f'c{(i % 4) + 1}', 'box': f'b{(i % 3) + 1}'} for i in range(5, 33)],
                {'id': 'steam999', 't': 'Uninstalled PC Game', 's': 'steam', 'inst': 'no', 'cover': 'c1'},
            ],
            'systems': {'sfc': {'name': 'Super Famicom'}, 'switch': {'name': 'Switch'}, 'gba': {'name': 'Game Boy Advance'}, 'psx': {'name': 'PlayStation'}},
            'played': {'g1': {'secs': 12600, 'last': int(time.time()) - 300}},
        }
        # Inject synthetic retail boxes (SNES horizontal, Switch transparent case, GBA square) + fallback covers
        for cid, col_a, col_b in (('c1', '#ffb23e', '#946ef8'), ('c2', '#ef4444', '#f59e0b'),
                                  ('c3', '#10b981', '#0ea5e9'), ('c4', '#38bdf8', '#6366f1')):
            cov = QImage(244, 340, QImage.Format.Format_RGB32)
            cp = ui.QPainter(cov)
            cg = ui.QLinearGradient(0, 0, 244, 340)
            cg.setColorAt(0, ui.QColor(col_a)); cg.setColorAt(1, ui.QColor(col_b))
            cp.fillRect(0, 0, 244, 340, ui.QBrush(cg)); cp.end()
            for tw in (w_top, w):
                for sz in ((244, 340), (345, 480)):
                    tw.thumbs.cache[(cid, sz[0], sz[1], True)] = cov
                for mx in (380, 420, 440, 480):
                    tw.saver_imgs.cache[(cid, mx, mx, False)] = cov
            ui.ACCENTS[cid] = col_a
        for bid, bw, bh, alpha, col_a in (('b1', 340, 242, False, '#ffb23e'), ('b2', 220, 356, True, '#ef4444'), ('b3', 340, 340, False, '#10b981')):
            bimg = QImage(bw, bh, QImage.Format.Format_ARGB32 if alpha else QImage.Format.Format_RGB32)
            bimg.fill(ui.QColor(0, 0, 0, 0) if alpha else ui.QColor(col_a))
            if alpha:
                bp = ui.QPainter(bimg); bp.setBrush(ui.QColor(col_a)); bp.setPen(ui.Qt.PenStyle.NoPen)
                bp.drawRoundedRect(8, 8, bw - 16, bh - 16, 18, 18); bp.end()
            for tw in (w_top, w):
                for mx in (340, 380, 420, 440, 480):
                    tw.thumbs.cache[(bid, mx, mx, False)] = bimg
                    tw.saver_imgs.cache[(bid, mx, mx, False)] = bimg

        img_top = QImage(1920, 1080, QImage.Format.Format_RGB32)
        for st_name in ('kosmos', 'arcade', 'aurora', 'minimal'):
            w_top.CFG['saver_style'] = w.CFG['saver_style'] = st_name
            for target_w, target_img, suffix in ((w_top, img_top, 'top'), (w, img, 'bottom')):
                ps = ui.QPainter(target_img)
                ps.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
                ui.screensaver.draw(target_w, ps)
                ps.end()
                if SHOTS:
                    target_img.save(str(Path(SHOTS) / f'saver-{st_name}-{suffix}.png'))

        # Verify top-screen "Zuletzt im Spiel" (`moment`) card + crisp `cover='hero'` rendering
        w_top.RUN = None
        w_top.L['fav'] = ['g1']
        mom_sw, mom_sh = round(29.0 * w_top.u), round(16.3 * w_top.u)
        mom_img = QImage(mom_sw, mom_sh, QImage.Format.Format_RGB32)
        mp = ui.QPainter(mom_img)
        mg = ui.QLinearGradient(0, 0, mom_sw, mom_sh)
        mg.setColorAt(0, ui.QColor('#1d4ed8')); mg.setColorAt(0.55, ui.QColor('#10b981')); mg.setColorAt(1, ui.QColor('#f59e0b'))
        mp.fillRect(0, 0, mom_sw, mom_sh, ui.QBrush(mg)); mp.end()
        hero_img = QImage(1920, 1080, QImage.Format.Format_RGB32)
        hp = ui.QPainter(hero_img)
        hg = ui.QLinearGradient(0, 0, 1920, 1080)
        hg.setColorAt(0, ui.QColor('#1e1b4b')); hg.setColorAt(1, ui.QColor('#312e81'))
        hp.fillRect(0, 0, 1920, 1080, ui.QBrush(hg)); hp.end()
        w_top.images.cache[('m1', mom_sw, mom_sh, True)] = mom_img
        w_top.images.cache[('h1', 1920, 1080, 'hero')] = hero_img
        w_top.S = {'tab': 0, 'sys': None, 'i': 0}
        w_top.hero.update(key='g1', kt=time.time() - 5.0, cur=hero_img, prev=None, t0=time.time() - 5.0)
        pm = ui.QPainter(img_top)
        pm.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
        w_top.draw_top(pm, [{**w_top.L['games'][0], 'hero': 'h1', 'moment': 'm1', 'protondb': 'platinum'}])
        pm.end()
        if SHOTS:
            img_top.save(str(Path(SHOTS) / 'top-moment-preview.png'))

        # Verify PDF/CBZ manual book reader UI + Macro Pad & Cheats Hub + AirPods Quick Card + Artwork Picker
        u_book = universal.Deck(w)
        u_book.ctrl_sub = 'macros'
        hmac_hits = render(u_book, 'univ-macros')
        self.assertTrue({'csub:pad', 'csub:macros', 'csub:cheats', 'mpad:0', 'mpad:11', 'macro_edit'} <= set(hmac_hits))
        u_book.ctrl_sub = 'cheats'
        u_book.cheats = {'items': [{'idx': 0, 'desc': '60 FPS Widescreen', 'code': '8200', 'enable': True}], 'can_fetch': True}
        hcht_hits = render(u_book, 'univ-cheats')
        self.assertTrue({'cheat_fetch', 'cheat_add', 'cht:0'} <= set(hcht_hits))
        u_book.tab = 3
        u_book.open_guide = {'name': 'Handbuch.pdf', 'title': 'Handbuch (PDF)', 'kind': 'book',
                             'pages': 24, 'page': 0, 'img': mom_img, 'zoom': 1.0, 'px': 0.0, 'py': 0.0}
        hb = render(u_book, 'univ-manual-book')
        self.assertTrue({'guide_back', 'bpage:◀', 'bpage:1/24', 'bpage:▶', 'zoom:+'} <= set(hb))
        u_book.close()

        # Verify AirPods AAP card + 30s Replay button + Deep-Freeze in Quick Menu
        w.RUN = {'id': 'g1', 't': 'Chrono Trigger', 's': 'sfc', 'emu': 'RetroArch', 'since': int(time.time()) - 120}
        w.AIRPODS = {'active': True, 'addr': 'AA:BB:CC:DD:EE:FF', 'name': 'AirPods Pro', 'is_airpods': True,
                     'aap_connected': True, 'battery_pct': 94,
                     'pods': {'left': {'level': 95, 'charging': False}, 'right': {'level': 94, 'charging': False}, 'case': {'level': 80, 'charging': True}},
                     'noise_mode': 'anc', 'conv_awareness': True, 'paired_audio': [{'addr': 'AA:BB:CC:DD:EE:FF', 'name': 'AirPods Pro'}]}
        w.QUICK = time.time()
        w.off['quick'] = 0
        w.hits, w.scrolls = [], []
        pq2 = ui.QPainter(img)
        pq2.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
        ui.quick_view.draw(w, pq2); pq2.end()
        q2_hits = {h[3] for h in w.hits}
        self.assertTrue({'ap:off', 'ap:anc', 'ap:transparency', 'ap:adaptive', '🗣️ Gespräch', '❄️ Freeze'} <= q2_hits, q2_hits)
        w.off['quick'] = w.maxoff.get('quick', 600)
        w.hits, w.scrolls = [], []
        pq3 = ui.QPainter(img)
        pq3.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
        ui.quick_view.draw(w, pq3); pq3.end()
        q3_hits = {h[3] for h in w.hits}
        self.assertIn('⏪ 30s-Clip', q3_hits)
        w.off.pop('quick', None)
        w.AIRPODS = None
        w.QUICK = None
        w.RUN = None

        # Verify v1.6.0 Pro-Controller Deck, Trophy Unlock Banner, Pinned Achievements & CHD/RVZ Shrinker Settings
        from decks import propad
        pp_deck = propad.Deck(w)
        hpp = render(pp_deck, 'propad-deck')
        self.assertTrue({'Mac / PC-IP setzen', 'Esc', 'F5 Save', 'Controller-Modus beenden'} <= set(hpp))
        pp_deck.close()

        w.TROPHY = {'title': 'Meister der Zeit', 'desc': 'Ziehe das Master-Schwert aus dem Zeitenfels.', 'points': 25, 'at': time.time() - 0.5}
        pt_banner = ui.QPainter(img)
        pt_banner.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
        w.draw_trophy_banner(pt_banner, w.TROPHY, 0.5)
        pt_banner.end()
        w.TROPHY = None

        w.SYSBK = {'compress': {'count': 2, 'total_mb': 1200.0, 'est_save_mb': 580.0,
                                'items': [{'sys': 'psx', 'name': 'SilentHill.cue', 'path': '/roms/psx/SilentHill.cue', 'target': 'chd-cd', 'mb': 650.0}],
                                'job': {'running': False, 'step': ''}}}
        cmp_groups = ui.settings_view.groups(w, 'library>compress')
        self.assertEqual([g[0] for g in cmp_groups], ['Übersicht', 'Aktion', 'Gefundene Discs'])

        w.GAME_MENU = {'id': 'g1', 'i': 0, 'art_picker': True, 'art_loading': False, 'art_has_custom': True,
                       'art_items': [{'label': 'Chrono Trigger · Libretro Cover', 'url': 'https://example.com/c.png', 'slot': 'cover'}]}
        w.hits, w.scrolls = [], []
        pa = ui.QPainter(img)
        pa.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
        w.draw_game_menu(pa); pa.end()
        ahits = {h[3] for h in w.hits}
        self.assertIn('gopt:↺ Standard-Cover wiederherstellen', ahits)
        self.assertIn('gopt:Chrono Trigger · Libretro Cover', ahits)
        w.GAME_MENU = None

        # Regression check: universal deck initializes cleanly via ADDR fallback even if URL is unset
        from decks import universal as udeck
        saved_url = getattr(ui, 'URL', None)
        try:
            ui.URL = ''
            d_chk = udeck.Deck(w)
            self.assertTrue(d_chk.server.startswith('http://'))
            d_chk.close()
        finally:
            if saved_url is not None: ui.URL = saved_url

        # All 11 bespoke Native Game Companions render cleanly at 1240x1080 across every tab (including embedded Werkzeuge)
        native_cases = (
            ('d3', '01001B300B9BE000', 'Diablo III: Eternal Collection (PeanutsNative)'),
            ('p5r', '01005CA01580E000', 'Persona 5 Royal (PeanutsNative)'),
            ('zelda_la', '01006BB00C6F0000', "The Legend of Zelda: Link's Awakening (PeanutsNative)"),
            ('oot', '0400486024DEC000', 'The Legend of Zelda: Ocarina of Time (BananaNative)'),
            ('odyssey', '0100000000010000', 'SUPER MARIO ODYSSEY (PeanutsNative)'),
            ('wonder', '010015100B514000', 'Super Mario Bros. Wonder (PeanutsNative)'),
            ('mkworld', '0400C3F00006E000', 'Mario Kart World (BananaNative)'),
            ('letsgo', '0100187003A36000', "Pokémon: Let's Go, Evoli! (PeanutsNative)"),
            ('mania', '01009AA000FAA000', 'Sonic Mania Plus (PeanutsNative)'),
            ('ffres', '0100606026F12000', 'FINAL FANTASY RESONANCE (PeanutsNative)'),
            ('tomodachi', '010051F0207B2000', 'Tomodachi Life: Living the Dream (PeanutsNative)'),
        )
        old_run, old_deck, old_dname = w.RUN, w.deck, getattr(w, 'deck_name', None)
        try:
            w.deck, w.deck_name = None, None
            for comp_key, tid, title in native_cases:
                w.RUN = {'id': 'native-' + tid.lower(), 'tid': tid, 't': title, 's': 'switch',
                         'emu': 'PeanutsNative', 'since': int(time.time()) - 120, 'companion': comp_key}
                comp_img = QImage(1240, 1080, QImage.Format.Format_RGB32)
                w.hits = []
                cp = ui.QPainter(comp_img)
                cp.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
                ok_deck = w.show_deck(cp)
                cp.end()
                self.assertTrue(ok_deck, f'Companion {comp_key} failed to paint tab 0')
                self.assertIsNot(w.deck, False, f'Companion {comp_key} raised during paint')
                self.assertGreater(len(w.hits), 3, f'Companion {comp_key} registered too few interactive hit areas')
                if SHOTS:
                    comp_img.save(str(Path(SHOTS) / f'companion-{comp_key}.png'))
                # Cycle through every tab of this bespoke companion (including embedded Werkzeuge tab)
                ntabs = len(w.deck.TABS)
                for ti in range(1, ntabs):
                    w.deck.set_tab(ti)
                    w.hits = []
                    cp2 = ui.QPainter(comp_img)
                    cp2.setRenderHints(ui.QPainter.RenderHint.Antialiasing | ui.QPainter.RenderHint.TextAntialiasing)
                    self.assertTrue(w.show_deck(cp2), f'Companion {comp_key} failed on tab {ti}')
                    cp2.end()
                w.deck.set_tab(0)
            if w.deck and w.deck is not False:
                w.deck.close()
        finally:
            w.RUN, w.deck, w.deck_name = old_run, old_deck, old_dname


if __name__ == '__main__':
    unittest.main()
