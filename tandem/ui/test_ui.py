"""Self-check for the native front end: python3 ui/test_ui.py (needs PySide6, no display; skipped without PySide6).
Runs both windows against a real Tandem service in dry-run mode and walks through the views index.html has."""
import json, os, socket, socketserver, struct, sys, threading, time, unittest
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
    from decks import ffix, packcss, packlua, packmem, pipboy
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
                         ('#00cc66', '#0a0c13', '#eef0f6', 1.0, 1.0, ui.DEFAULT_THEME['fonts'], None, False, None))  # what is wrong keeps its default, the rest counts
        ui.apply_theme(half)
        self.assertEqual((ui.FOCUS.name(), ui.INK.name()), ('#00cc66', '#0a0c13'))
        ui.apply_theme(ui.read_theme('toravo'))
        self.assertEqual(ui.FOCUS.name(), '#ffb23e')

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
        self.assertNotIn('SPIEL BEENDEN', [h[3] for h in bottom.hits])
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
        self.assertEqual((deck.tree.snapshot['waiting'], [n for n in names() if n in ('Begleiter', 'Erfolge', 'Steuerung', 'mon', 'SPIEL BEENDEN')]), (True, ['Steuerung', 'Erfolge', 'Begleiter']))
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
        self.assertTrue({'SPIEL BEENDEN', 'vol', 'SPEICHERN' if bottom.RUN['emu'] == 'RetroArch' else 'vol'} <= set(names()))
        self.assertNotIn('mon', names())
        self.tap('Erfolge'); self.paint('pack-achievements')
        self.assertTrue(bottom.maxoff['ach'] > 0 and 'SPIEL BEENDEN' not in names())
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
        self.tap('BEENDEN'); self.wait(lambda: not top.RUN and not bottom.RUN)  # the bar's own button
        # System tab: account name through the on-screen keys
        self.tap('System'); self.wait(lambda: bottom.SYS)
        self.paint('system')
        self.tap('AUSSCHALTEN'); self.wait(lambda: top.CONFIRM and bottom.CONFIRM)  # power actions ask first, on both screens
        self.paint('power')
        top.go('back'); self.wait(lambda: not bottom.CONFIRM)
        self.tap('STANDBY'); self.wait(lambda: top.CONFIRM)
        self.assertEqual(self.actions, [])
        top.go('ok'); self.wait(lambda: self.actions == ['suspend'] and not bottom.CONFIRM)
        self.assertEqual(ui.THEME['id'], 'toravo')
        self.tap('WECHSELN'); self.wait(lambda: self.service.saved is not None and tandem.public_config()['theme'] != 'toravo' and top.CFG.get('theme') == ui.THEME['id'] != 'toravo')  # touch: next look, stored by the service
        self.paint('theme-' + ui.THEME['id'])
        seen = {ui.THEME['id']}
        for _ in range(8):  # the controller's A on the System tab walks through all of them, back to the default
            before = ui.THEME['id']
            top.go('ok'); self.wait(lambda: tandem.public_config()['theme'] == ui.THEME['id'] != before and bottom.CFG.get('theme') == ui.THEME['id'])
            self.paint('theme-' + ui.THEME['id']); seen.add(ui.THEME['id'])
            if ui.THEME['id'] == 'toravo': break
        self.assertTrue({'toravo', 'studio', 'oled', 'hell'} <= seen)
        self.assertEqual((ui.THEME['id'], ui.INK.name()), ('toravo', '#0a0c13'))
        self.tap('NAME'); self.assertTrue(bottom.PROMPT)
        self.paint('prompt')
        for key in ('⇧', 'A', 'b', 'c', '⌫'): self.tap(key)
        self.assertEqual(bottom.PROMPT['value'], 'Ab')
        self.tap('Fertig'); self.wait(lambda: bottom.CFG.get('ra_user') == 'Ab')
        bottom.SYS['networks'] = [{'ssid': 'Daheim', 'signal': 70, 'secure': True, 'known': False, 'active': False}]
        bottom.SUB = 'wifi'
        self.paint('wifi')
        self.tap('Daheim'); self.assertIn('Daheim', bottom.PROMPT['title'])
        self.paint('wifi-password')
        self.tap('Abbrechen'); self.assertIsNone(bottom.PROMPT)
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
        self.assertEqual(self.actions, ['suspend'])  # nothing ran
        self.tap('ABBRECHEN'); self.wait(lambda: not top.CONFIRM)


if __name__ == '__main__':
    unittest.main()
