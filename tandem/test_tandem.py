"""Self-check for tandem.py: python3 test_tandem.py (standard library only, runs on ArmadaOS too)."""
import atexit, json, os, shutil, stat, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix='tandem-test-'))
atexit.register(shutil.rmtree, TMP, True)
os.environ['HOME'] = str(TMP / 'home')
os.environ['XDG_STATE_HOME'] = str(TMP / 'state')
os.environ['XDG_CONFIG_HOME'] = str(TMP / 'config')
os.environ['XDG_RUNTIME_DIR'] = str(TMP / 'run')
os.environ['TANDEM_SAVE_BACKUP_DIR'] = str(TMP / 'save-backups')
os.environ['TANDEM_SYS_BACKUP_DIR'] = str(TMP / 'sys-backups')
import tandem  # noqa: E402  (after HOME is redirected)

HOME = TMP / 'home'
tandem.PORTS_DIR = TMP / 'ports'  # never the ports installed on the device this runs on
SD = TMP / 'sd'


def touch(path, text=''):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


TINY_PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
            b'\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82')


def touch_bin(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def setUpModule():
    touch(SD / 'ROMs/psx/Breath of Fire III (Europe).chd')
    touch(SD / 'ROMs/psx/notes.txt')
    touch(SD / 'ROMs/gba/Legend of Zelda, The - The Minish Cap (Europe) (En,Fr,De,Es,It).gba')
    touch(SD / 'ROMs/switch/Some Game.nsp')
    touch(SD / 'Cocoon/downloaded_media/psx/icon/Breath of Fire III (Europe)__cocoon_edit_12_abcdef.png', 'png')
    touch(SD / 'Cocoon/downloaded_media/psx/hero/Breath of Fire III (Europe)__cocoon_edit_12_abcdef.jpg', 'jpg')
    touch_bin(SD / 'Cocoon/downloaded_media/psx/logo/Breath of Fire III (Europe)__cocoon_edit_12_abcdef.png', TINY_PNG)
    touch_bin(SD / 'Cocoon/downloaded_media/psx/screenshot_gameplay/Breath of Fire III (Europe)__cocoon_edit_12_abcdef.png', TINY_PNG)
    touch_bin(SD / 'Cocoon/assets/icon_overlays/pack-1/icon_overlays/psx/mask.png', TINY_PNG)
    touch_bin(SD / 'Cocoon/assets/icon_overlays/pack-1/icon_overlays/psx/overlay.png', TINY_PNG)
    touch(SD / 'secret.png', 'secret')
    touch(SD / 'Cocoon/assets/smart_folders/pack-1/smart_folders/by_platform/psx/icon.png', 'png')
    touch(SD / 'Cocoon/assets/smart_folders/pack-1/smart_folders/by_platform/psx/hero.png', 'png')
    fake = HOME / 'Applications/DuckStation-arm64.AppImage'  # stands in for the emulator: records its arguments, then waits
    touch(fake, f'#!/bin/sh\nprintf "%s\\n" "$@" > "{TMP}/args"\nsleep 30\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    touch(HOME / '.local/share/Steam/steamapps/appmanifest_1145360.acf', '"AppState"\n{\n\t"appid"\t\t"1145360"\n\t"name"\t\t"Hades"\n}\n')
    touch(HOME / '.local/share/Steam/steamapps/appmanifest_1493710.acf', '"AppState"\n{\n\t"appid"\t\t"1493710"\n\t"name"\t\t"Proton Experimental"\n}\n')


def make():
    library = tandem.Library([str(SD / 'ROMs')], HOME / '.local/share/Steam')
    library.scan()
    return tandem.Tandem(library)


class WowLogin(unittest.TestCase):
    def test_login_file(self):  # written for the client, owner-only, then overwritten and removed
        folder = TMP / 'wow/_forever_'; (folder / 'Logs').mkdir(parents=True, exist_ok=True)
        keep = tandem.wow_folders, tandem.load_config
        tandem.wow_folders = lambda: [folder]
        try:
            tandem.load_config = lambda: {}
            self.assertFalse(tandem.wow_login(0))
            self.assertFalse((folder / 'login.txt').exists())
            tandem.load_config = lambda: {'bnet_email': 'a@example.org', 'bnet_password': 'geheim'}
            self.assertTrue(tandem.wow_login(0))
            self.assertEqual((folder / 'login.txt').read_text(), 'a@example.org\ngeheim\n')
            self.assertEqual((folder / 'login.txt').stat().st_mode & 0o777, 0o600)
            for _ in range(80):
                if not (folder / 'login.txt').exists(): break
                time.sleep(.1)
            self.assertFalse((folder / 'login.txt').exists())
        finally: tandem.wow_folders, tandem.load_config = keep


    def test_pick_account(self):  # '!' moves to the chosen game account, other lines stay
        cfg = TMP / 'Config.wtf'
        cfg.write_text('SET portal "EU"\r\nSET accountList "!WoW1|Konto2|"\r\n')
        tandem.wow_pick_account(cfg, 'Konto2')
        self.assertEqual(cfg.read_bytes(), b'SET portal "EU"\r\nSET accountList "WoW1|!Konto2|"\r\n')
        cfg.write_text('SET portal "EU"\r\n')
        tandem.wow_pick_account(cfg, 'Konto2')
        self.assertIn('SET accountList "!Konto2|"', cfg.read_text())


    def test_chooser(self):  # blue mark on row one + red accept button = the account chooser
        try: from PIL import Image
        except ImportError: self.skipTest('PIL fehlt')
        import wowpick
        im = Image.new('RGB', (1920, 1080))
        self.assertFalse(wowpick.chooser_up(im))
        im.putpixel((1000, 496), (23, 110, 212)); im.putpixel((894, 664), (171, 1, 1))
        self.assertTrue(wowpick.chooser_up(im))
        im = Image.new('RGB', (1920, 1080))  # the dialog sits higher when the login form is shorter
        im.putpixel((1000, 476), (25, 104, 198)); im.putpixel((894, 716), (163, 1, 1))
        self.assertTrue(wowpick.chooser_up(im))


class FrameGen(unittest.TestCase):
    def test_switch(self):  # the layer file is set aside while off and comes back on
        keep, tandem.LSFG_LAYER = tandem.LSFG_LAYER, TMP / 'vulkan/VkLayer_LSFGVK_frame_generation.json'
        try:
            self.assertEqual(tandem.frame_gen(), {'on': False, 'there': False})
            tandem.LSFG_LAYER.parent.mkdir(parents=True, exist_ok=True); tandem.LSFG_LAYER.write_text('{}')
            self.assertEqual(tandem.frame_gen(False), {'on': False, 'there': True})
            self.assertEqual(tandem.frame_gen(False), {'on': False, 'there': True})
            self.assertEqual(tandem.frame_gen(True), {'on': True, 'there': True})
        finally: tandem.LSFG_LAYER = keep


class Scan(unittest.TestCase):
    def test_titles(self):
        self.assertEqual(tandem.clean('Golden Sun (Germany) [!]'), 'Golden Sun')
        self.assertEqual(tandem.clean('Legend of Zelda, The - The Minish Cap (Europe) (En,Fr)'), 'The Legend of Zelda - The Minish Cap')

    def test_library(self):
        t = make()
        by_title = {g['t']: g for g in t.library.games.values()}
        self.assertEqual(set(by_title), {'Breath of Fire III', 'The Legend of Zelda - The Minish Cap', 'Some Game', 'Hades'})  # no notes.txt, no Proton
        self.assertTrue(by_title['Breath of Fire III']['cover'].endswith('.png'))
        self.assertTrue(by_title['Breath of Fire III']['hero'].endswith('.jpg'))
        self.assertTrue(by_title['Breath of Fire III']['logo'].endswith('.png'))
        self.assertTrue(by_title['Breath of Fire III']['shot'].endswith('.png'))
        payload = t.library.payload(t.saved)
        self.assertIn('psx', payload['overlays'])
        self.assertIn('cocoon', [th['id'] for th in tandem.themes()])
        self.assertEqual(payload['systems']['psx']['emu'], 'DuckStation')
        self.assertTrue(payload['systems']['psx']['cover'] and payload['systems']['psx']['hero'])
        self.assertIsNone(payload['systems']['gba']['cover'])
        self.assertIn('RetroArch', payload['systems']['gba']['missing'])
        self.assertIn('Eden', payload['systems']['switch']['missing'])
        self.assertEqual(payload['extras'][0]['installed'], False)
        self.assertNotIn('path', payload['games'][0])


class Launch(unittest.TestCase):
    def test_start_track_quit(self):
        t = make()
        gid = next(g['id'] for g in t.library.games.values() if g['s'] == 'psx')
        result = t.launch(gid)
        self.assertTrue(result.get('tracked'), result)
        self.assertEqual(result['cmd'][1], '-batch')
        self.assertIn('error', t.launch(gid))  # one game at a time
        for _ in range(50):
            if (TMP / 'args').exists(): break
            time.sleep(0.1)
        self.assertEqual((TMP / 'args').read_text().split('\n')[1], str(SD / 'ROMs/psx/Breath of Fire III (Europe).chd'))
        t.run['since'] -= 120
        t.quit()
        for _ in range(60):
            if not t.run: break
            time.sleep(0.1)
        self.assertIsNone(t.run)
        self.assertGreaterEqual(json.loads((TMP / 'state/tandem/state.json').read_text())['played'][gid]['secs'], 120)

    def test_companion_pack_matches_the_rom(self):
        rom = bytearray(0x200)
        rom[0xAC:0xB0], rom[0xB2] = b'AGSD', 0x96
        (TMP / 'gs.gba').write_bytes(rom)
        game = {'s': 'gba', 'path': str(TMP / 'gs.gba')}
        self.assertEqual(tandem.rom_identity(game['path']), ('AGSD', tandem.zlib.crc32(rom)))
        self.assertIsNone(tandem.find_pack(game))  # no packs folder
        pack = lambda name, match: touch(TMP / f'config/tandem/packs/{name}/manifest.json', json.dumps({'match': match}))
        pack('a-other', {'gameCode': ['AMTP'], 'crc32': []})
        pack('b-broken', {'gameCode': 'x', 'crc32': ['zz']})
        pack('c-by-crc', {'gameCode': [], 'crc32': ['%08X' % (tandem.zlib.crc32(rom) ^ 1)]})
        pack('d-golden-sun', {'gameCode': ['AGSD', 'AGFD'], 'crc32': []})
        self.assertEqual(tandem.find_pack(game), 'd-golden-sun')
        pack('c-by-crc', {'gameCode': [], 'crc32': ['%08X' % tandem.zlib.crc32(rom)]})
        self.assertEqual(tandem.find_pack(game), 'c-by-crc')
        self.assertIsNone(tandem.find_pack({**game, 's': 'snes'}))
        gb = bytearray(0x150)
        gb[0x104:0x108], gb[0x13F:0x143], gb[0x143], gb[0x14B] = b'\xce\xed\x66\x66', b'AZ7P', 0xC0, 0x33
        (TMP / 'z.gbc').write_bytes(gb)
        self.assertEqual(tandem.rom_identity(TMP / 'z.gbc')[0], 'CGB-AZ7P')
        gb[0x143], gb[0x14B] = 0, 1
        (TMP / 'm.gb').write_bytes(gb)
        self.assertEqual(tandem.rom_identity(TMP / 'm.gb')[0], 'DMG-????')
        with tandem.zipfile.ZipFile(TMP / 'gs.zip', 'w') as z: z.writestr('gs.gba', bytes(rom))
        self.assertEqual(tandem.rom_identity(TMP / 'gs.zip'), ('AGSD', tandem.zlib.crc32(rom)))
        self.assertEqual(tandem.rom_identity(TMP / 'missing.gba'), (None, None))

    def test_wide_view_core_and_switch(self):
        cores = tandem.RA_CORES[0]
        folder = TMP / 'config/tandem/packs/w-wide'
        touch(folder / 'manifest.json', json.dumps({'match': {}, 'gameScript': 'game.lua'}))
        touch(folder / 'game.lua', 'local names = pack.require("names")\nfunction wide(view) return nil end\n')
        touch(folder / 'names.lua', 'return {}')
        cmd = ['flatpak', 'run', tandem.RA_REF, '-L', str(cores / 'mgba_libretro.so'), 'rom.gba']
        self.assertEqual(tandem.wide_core(cmd, 'w-wide', True), (cmd, None))  # the wide core is not installed: as before
        touch(tandem.RA_WIDE_CORE)
        touch(tandem.RA_WIDE / 'stale.lua')
        wide, on = tandem.wide_core(cmd, 'w-wide', False)
        self.assertEqual((wide[4], wide[5], on), (str(tandem.RA_WIDE_CORE), 'rom.gba', False))
        self.assertEqual(sorted(p.name for p in tandem.RA_WIDE.iterdir()), ['game.lua', 'names.lua', 'on'])
        self.assertEqual((tandem.RA_WIDE / 'on').read_text(), '0')
        saves = cores.parent / 'saves'  # a Game Boy game moves from Gambatte to the wide mGBA and keeps its save
        touch(saves / 'Gambatte/rom.srm', 'save')
        gb = tandem.wide_core(cmd[:4] + [str(cores / 'gambatte_libretro.so'), 'roms/rom.gb'], 'w-wide', True)
        self.assertEqual((gb[0][4], gb[1], (saves / 'mGBA/rom.srm').read_text()), (str(tandem.RA_WIDE_CORE), True, 'save'))
        self.assertTrue((saves / 'mGBA/rom.srm').is_symlink())
        touch(folder / 'game.lua', 'function frame(view) end\n')  # a game.lua without wide(): the plain core
        self.assertEqual(tandem.wide_core(cmd, 'w-wide', True), (cmd, None))
        self.assertEqual(tandem.wide_core(cmd[:4] + [str(cores / 'gpsp_libretro.so'), 'rom.gba'], 'w-wide', True)[1], None)
        t = make()
        self.assertIn('error', t.wide('on'))  # nothing runs
        t.run = {'id': 'g1', 'wide': False}
        self.assertEqual((t.wide('toggle')['wide'], (tandem.RA_WIDE / 'on').read_text(), t.saved['wide']), (True, '1', {'g1': True}))
        self.assertEqual((t.wide('off')['wide'], t.wide('on')['wide'], t.wide('')['wide']), (False, True, False))
        t.run = {'id': 'g2', 'wide': None}
        self.assertIn('error', t.wide('on'))  # a pack without wide()
        t.run = None

    def test_homm3_setup(self):
        """ports/homm3/setup.py: what of a Steam HD Edition folder VCMI gets and under which names, and the mod switch."""
        import importlib.util
        source = Path(__file__).parent / 'ports/homm3/setup.py'
        if not source.is_file(): self.skipTest('the installed copy has no port sources')
        spec = importlib.util.spec_from_file_location('homm3_setup', source)
        setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)
        hd = TMP / 'hd'
        for name in ('data/H3BITMAP.LOD', 'data/H3SPRITE.LOD', 'data/HEROES3.SND', 'data/sprite_DXT_com_x2.pak', 'data/maps/EN/a.h3m', 'data/maps/DE/a.h3m', 'data/maps/DE/Tutorial.tut',
                     'data/mp3/Grass.mp3', 'data/VIDEO/Intro.ogv', 'data/LOC/EN/h3bitmap.lod', 'data/LOC/DE/h3bitmap.lod', 'data/LOC/DE/heroes3cd.snd', 'data/LOC/DE/H3Intro.ogv'): touch(hd / name)
        got = {f'{target}/{name}': str(source.relative_to(hd)) for source, target, name in setup.plan(hd, 'de')}  # later entries win: the localized ones
        self.assertEqual(got, {'Data/H3bitmap.lod': 'data/H3BITMAP.LOD', 'Data/H3sprite.lod': 'data/H3SPRITE.LOD', 'Data/Heroes3.snd': 'data/HEROES3.SND', 'Mp3/Grass.mp3': 'data/mp3/Grass.mp3',
                               'Video/Intro.ogv': 'data/VIDEO/Intro.ogv', 'Data/H3pbitma.lod': 'data/LOC/DE/h3bitmap.lod', 'Data/Heroes3-cd2.snd': 'data/LOC/DE/heroes3cd.snd',
                               'Video/H3Intro.ogv': 'data/LOC/DE/H3Intro.ogv', 'Maps/a.h3m': 'data/maps/DE/a.h3m', 'Maps/Tutorial.tut': 'data/maps/DE/Tutorial.tut'})
        self.assertIn(('Data', 'H3pbitma.lod', 'data/LOC/DE/h3bitmap.lod'), [(t, n, str(s.relative_to(hd))) for s, t, n in setup.plan(hd, 'xx')])  # no such language: the first one there
        settings = TMP / 'homm3-config/modSettings.json'
        self.assertEqual((setup.enable_mod(settings), setup.enable_mod(settings)), (True, False))
        self.assertEqual(json.loads(settings.read_text())['presets']['default']['mods'], ['vcmi', 'core', 'roe-support'])
        touch(settings, json.dumps({'activePreset': 'mine', 'presets': {'mine': {'mods': ['vcmi'], 'settings': {'x': 1}}}}))  # the player's own preset keeps what it has
        setup.enable_mod(settings)
        self.assertEqual(json.loads(settings.read_text())['presets']['mine'], {'mods': ['vcmi', 'roe-support'], 'settings': {'x': 1}})

    def test_native_port(self):
        run = tandem.PORTS_DIR / 'halflife/run'  # stands in for a built port: records its argument and the deck socket, then waits
        touch(run, f'#!/bin/sh\necho "$1 $TANDEM_DECK_SOCKET" > "{TMP}/port"\nsleep 30\n')
        run.chmod(0o755)
        try:
            t = make()
            self.assertEqual([g['t'] for g in t.library.games.values() if g['s'] == 'port'], ['Half-Life', 'Half-Life: Opposing Force', 'Half-Life: Blue Shift'])
            self.assertEqual(t.library.payload({})['systems']['port'], {'name': 'Ports', 'hue': 28, 'n': 3, 'emu': 'Port', 'missing': None, 'cover': None, 'hero': None})
            self.assertTrue(t.launch('port-opfor').get('tracked'))
            for _ in range(50):
                if (TMP / 'port').exists(): break
                time.sleep(0.1)
            self.assertEqual((TMP / 'port').read_text().strip(), f'gearbox {tandem.DECK_SOCKET}')
            self.assertEqual(t.run['port'], {'deck': 'hev', 'socket': str(tandem.DECK_SOCKET)})  # the bottom screen loads that deck
            t.quit()
            for _ in range(60):
                if not t.run: break
                time.sleep(0.1)
            self.assertIsNone(t.run)
        finally: run.unlink()

    def test_missing_emulator(self):
        t = make()
        gid = next(g['id'] for g in t.library.games.values() if g['s'] == 'switch')
        self.assertIn('Eden', t.launch(gid)['error'])
        self.assertIsNone(t.run)


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = make()
        cls.t.dry = True
        cls.server = tandem.ThreadingHTTPServer(('127.0.0.1', 0), tandem.handler(cls.t))
        cls.base = f'http://127.0.0.1:{cls.server.server_address[1]}'
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    def call(self, path, data=None, headers=None):
        request = urllib.request.Request(self.base + path, None if data is None else json.dumps(data).encode(), headers or {})
        try:
            with urllib.request.urlopen(request, timeout=5) as r: return r.status, r.read()
        except urllib.error.HTTPError as error: return error.code, error.read()

    def test_pages_and_media(self):
        status, page = self.call('/')
        self.assertEqual(status, 200)
        self.assertIn(b'window.BOOT={"library"', page)
        library = json.loads(self.call('/api/library')[1])
        cover = next(g['cover'] for g in library['games'] if g['cover'])
        self.assertEqual(self.call('/' + cover), (200, b'png'))
        self.assertEqual(self.call('/media/../../secret.png')[0], 404)
        self.assertEqual(self.call('/media/' + str(SD / 'secret.png'))[0], 404)

    def test_foreign_origin_cannot_launch(self):
        gid = next(iter(self.t.library.games))
        self.assertEqual(self.call('/api/launch', {'id': gid}, {'Origin': 'https://example.org'})[0], 403)
        self.assertIsNone(self.t.run)

    def test_settings_and_commands(self):
        state = json.loads(self.call('/api/state')[1])
        self.assertEqual(set(state['settings']), {'bt', 'bb', 'vol'})  # None on a machine without these controls
        self.assertIn('error', json.loads(self.call('/api/set', {'key': 'nope', 'value': 5})[1]))
        self.assertIn('error', json.loads(self.call('/api/retroarch', {'name': 'QUIT; rm'})[1]))
        self.assertEqual(json.loads(self.call('/api/retroarch', {'name': 'save'})[1]), {'ok': True})
        self.assertIn('error', json.loads(self.call('/api/action', {'name': 'format'})[1]))
        self.assertEqual(self.call('/api/action', {'name': 'poweroff'}, {'Origin': 'https://example.org'})[0], 403)

    def test_config_keeps_the_key_private(self):
        saved = json.loads(self.call('/api/config', {'ra_user': ' tester ', 'ra_key': 'geheim-123'})[1])
        self.assertEqual({k: saved[k] for k in ('ra_user', 'ra_key_set', 'ra_login')}, {'ra_user': 'tester', 'ra_key_set': True, 'ra_login': False})
        self.assertNotIn(b'geheim-123', self.call('/api/state')[1])
        self.assertNotIn(b'geheim-123', self.call('/')[1])
        self.assertEqual(oct((TMP / 'config/tandem/config.json').stat().st_mode & 0o777), '0o600')
        self.assertEqual(self.call('/api/config', {'ra_key': 'x'}, {'Origin': 'https://example.org'})[0], 403)

    def test_achievements_need_an_account_and_match_titles(self):
        self.assertEqual(tandem.ra_norm('Legend of Zelda, The: The Minish Cap'), tandem.ra_norm('The Legend of Zelda - The Minish Cap'))
        self.assertIn('note', json.loads(self.call('/api/achievements')[1]))  # nothing running
        self.assertIn('note', tandem.achievements({'s': 'switch', 't': 'x'}))

    def test_sign_in_reaches_the_emulators(self):
        ini = HOME / '.local/share/duckstation/settings.ini'
        touch(ini, '[Main]\nStartFullscreen = true\n\n[Cheevos]\nEnabled = false\n\n[GPU]\nRenderer = Vulkan\n')
        self.assertEqual(tandem.apply_ra('tester', 'tok123'), ['DuckStation'])
        text = ini.read_text()
        for part in ('Enabled = true', 'Username = tester', 'Token = tok123', 'ChallengeMode = false', '[GPU]\nRenderer = Vulkan', 'StartFullscreen = true'):
            self.assertIn(part, text)
        self.assertEqual(text.count('[Cheevos]'), 1)

    def test_remote_page_needs_the_pin(self):
        import http.cookiejar
        tandem.new_pin()
        pair = tandem.ThreadingHTTPServer(('127.0.0.1', 0), tandem.pair_handler(self.t))
        threading.Thread(target=pair.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{pair.server_address[1]}/'
        jar = http.cookiejar.CookieJar()
        browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        send = lambda path, body: browser.open(urllib.request.Request(url + path, body.encode()), timeout=5).read().decode()
        with self.assertRaises(urllib.error.HTTPError): send('api/config', '{"ra_user": "boese"}')  # no session yet
        self.assertIn('PIN stimmt nicht', send('', 'pin=000000x'))
        self.assertNotEqual(tandem.public_config()['ra_user'], 'boese')
        pin = tandem.PAIR['pin']
        self.assertIn('RetroAchievements', send('', f'pin={pin}'))  # redirected to the settings page
        self.assertNotEqual(tandem.PAIR['pin'], pin)  # one PIN, one use
        self.assertEqual(json.loads(send('api/config', '{"ra_user": "vomhandy"}'))['ra_user'], 'vomhandy')
        self.assertIn('settings', json.loads(browser.open(url + 'api/all', timeout=5).read()))
        # the browser stays known: a year's cookie, and only the token's hash on disk, for the owner alone
        cookie = next(iter(jar))
        self.assertGreater(cookie.expires - time.time(), 360 * 86400)
        self.assertEqual(stat.S_IMODE(tandem.DEVICES.stat().st_mode), 0o600)
        self.assertNotIn(cookie.value, tandem.DEVICES.read_text())
        again = tandem.ThreadingHTTPServer(('127.0.0.1', 0), tandem.pair_handler(self.t))  # as after a restart of the service
        threading.Thread(target=again.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{again.server_address[1]}/'
        self.assertIn('settings', json.loads(browser.open(url + 'api/all', timeout=5).read()))
        stranger = urllib.request.build_opener()
        with self.assertRaises(urllib.error.HTTPError): stranger.open(url + 'api/all', timeout=5)
        for n in range(12): tandem.save_devices(tandem.devices() + [f'{n:064x}'])  # more browsers than are kept: the oldest goes
        self.assertEqual(len(tandem.devices()), 10)
        with self.assertRaises(urllib.error.HTTPError): browser.open(url + 'api/all', timeout=5)
        tandem.save_devices([tandem.token_hash(cookie.value)])
        send('api/logout', '{}')
        self.assertEqual(tandem.devices(), [])
        with self.assertRaises(urllib.error.HTTPError): browser.open(url + 'api/all', timeout=5)
        info = tandem.pair_info()
        if info['url']: self.assertRegex(info['url'], r'^http://[^/]+\.local:\d+$')

    def test_steam_library_file(self):
        import struct
        blob = bytes(60) + b'\x00common\0\x01name\0Mein Spiel\0\x01type\0Game\0\x01installdir\0MeinSpiel\0\x08\x08'
        file = Path(tempfile.mkdtemp()) / 'appinfo.vdf'
        file.write_bytes(struct.pack('<II', 0x07564428, 1) + struct.pack('<II', 4711, len(blob)) + blob + struct.pack('<I', 0))
        self.assertEqual(tandem.steam_apps(file), {'4711': {'name': 'Mein Spiel', 'type': 'Game', 'installdir': 'MeinSpiel'}})
        self.assertEqual(tandem.steam_apps(file.with_name('fehlt')), {})

    def test_steam_shortcuts(self):
        import struct
        steam = Path(tempfile.mkdtemp())
        (steam / 'userdata/1/config').mkdir(parents=True)
        entry = lambda n, appid, name: b'\x00' + n + b'\x00\x02appid\x00' + struct.pack('<I', appid) + b'\x01AppName\x00' + name + b'\x00\x00tags\x00\x08\x08'
        (steam / 'userdata/1/config/shortcuts.vdf').write_bytes(b'\x00shortcuts\x00' + entry(b'0', 0x80000008, b'Toravo Tandem') + entry(b'1', 4274032209, b'Battle.net') + b'\x08\x08')
        self.assertEqual(tandem.steam_shortcuts(steam), [('4274032209', 'Battle.net', steam / 'userdata/1/config/grid')])

    def test_system_info_shape(self):
        info = json.loads(self.call('/api/system')[1])
        self.assertEqual(set(info), {'ssid', 'networks', 'storage', 'host'})
        self.assertEqual(info['storage'][0]['name'], 'Intern')
        self.assertIn('error', json.loads(self.call('/api/wifi', {'ssid': ''})[1]))

    def test_favourite_and_ui(self):
        gid = next(iter(self.t.library.games))
        self.assertEqual(json.loads(self.call('/api/fav', {'id': gid})[1])['fav'], [gid])
        self.call('/api/ui', {'tab': 1, 'sys': 'psx', 'i': 2, 'from': 'x'})
        self.assertEqual(json.loads(self.call('/api/state')[1])['ui'], {'tab': 1, 'sys': 'psx', 'i': 2, 'page': '', 'pane': 0, 'dev': ''})
        self.call('/api/ui', {'tab': 4, 'i': 3, 'page': 'controls>map', 'pane': 1, 'dev': ''})  # the settings: page and focus side travel along
        self.assertEqual(json.loads(self.call('/api/state')[1])['ui'], {'tab': 4, 'sys': None, 'i': 3, 'page': 'controls>map', 'pane': 1, 'dev': ''})
        self.call('/api/ui', {'tab': 4, 'page': '../x', 'pane': 'x'})
        self.assertEqual({k: v for k, v in json.loads(self.call('/api/state')[1])['ui'].items() if k in ('page', 'pane')}, {'page': '', 'pane': 0})
        self.call('/api/ui', {'tab': 1, 'sys': ['bad'], 'i': 0})
        self.assertIsNone(json.loads(self.call('/api/state')[1])['ui']['sys'])


class SelfUpdate(unittest.TestCase):
    def test_checks_refuses_damage_and_installs(self):
        import hashlib, io, shutil, tarfile
        tandem.save_config({'update_url': ''})  # switched off by the owner; without an entry the project's releases are asked
        self.assertIn('Keine Update-Quelle', tandem.self_update()['text'])
        self.assertIn('error', tandem.save_config({'update_url': 'http://unsicher.example'}))
        src, here = TMP / 'release', TMP / 'installed'
        (src / 'tandem').mkdir(parents=True); here.mkdir()
        (here / 'old.txt').write_text('alt')
        (src / 'tandem/install.sh').write_text('echo neu > "$TANDEM_DEST/new.txt"; echo "Selbsttest: ok"\n')
        blob = io.BytesIO()
        with tarfile.open(fileobj=blob, mode='w:gz') as tar: tar.add(src / 'tandem', 'tandem')
        (src / 't.tar.gz').write_bytes(blob.getvalue())
        manifest = lambda version, sha: (src / 'manifest.json').write_text(json.dumps({'version': version, 'file': 't.tar.gz', 'sha256': sha}))
        tandem.save_config({'update_url': 'file://' + str(src)})
        was, tandem.HERE, tandem.VERSION = (tandem.HERE, tandem.VERSION), here, '0.1.0'
        try:
            manifest('0.1.0', 'x'); self.assertIn('aktuell', tandem.self_update(True)['text'])
            manifest('0.2.0', 'x'); self.assertEqual(tandem.self_update()['new'], '0.2.0')  # only looking: nothing installed
            self.assertIn('beschädigt', tandem.self_update(True)['error']); self.assertFalse((here / 'new.txt').exists())
            manifest('0.2.0', hashlib.sha256(blob.getvalue()).hexdigest())
            self.assertIn('installiert', tandem.self_update(True)['text'])
            self.assertTrue((here / 'new.txt').exists()); self.assertEqual((TMP / 'tandem.prev/old.txt').read_text(), 'alt')  # the way back
        finally:
            tandem.HERE, tandem.VERSION = was; tandem.save_config({'update_url': ''})


class FirstRun(unittest.TestCase):
    def test_assistant_state_and_findings(self):
        tandem.SETUP_MARK.unlink(missing_ok=True)
        t = make()
        self.assertEqual(t.setup, {'open': True, 'step': 0})  # no marker: the assistant opens
        info = tandem.setup_info(t)
        self.assertEqual(info['folders'][0]['root'], str(SD / 'ROMs'))
        self.assertEqual({s['name']: s['n'] for s in info['folders'][0]['systems']}, {'PlayStation': 1, 'Game Boy Advance': 1, 'Switch': 1})
        missing = {m['s']: m for m in info['missing']}
        self.assertEqual(sorted(missing), ['gba', 'switch'])  # DuckStation is there (the stand-in), RetroArch and Eden are not
        self.assertEqual((missing['gba']['store'], missing['switch']['store'], missing['switch']['extra']), ('retroarch', None, 'eden'))
        self.assertFalse(info['install'])  # no Armada Store here
        self.assertIn('Passwort', tandem.install_missing(t)['error'])  # cannot install by itself: says what to do instead
        self.assertEqual(tandem.setup_command(t, {'step': 3})['step'], 3)
        self.assertEqual(tandem.setup_command(t, {'step': 99})['step'], 9)
        self.assertFalse(tandem.SETUP_MARK.exists())
        self.assertEqual(tandem.setup_command(t, {'open': False}), {'ok': True, 'open': False, 'step': 0})  # closed, but not done: comes again
        self.assertFalse(tandem.SETUP_MARK.exists())
        tandem.setup_command(t, {'open': True}); t.ui['tab'] = 3
        self.assertEqual(tandem.setup_command(t, {'done': True}), {'ok': True, 'open': False, 'step': 0})
        self.assertTrue(tandem.SETUP_MARK.exists())
        self.assertEqual(t.ui['tab'], 0)  # finished: on to the Start tab
        self.assertFalse(make().setup['open'])  # marker there: not again by itself


class OwnAddress(unittest.TestCase):
    def test_settings_page_address(self):
        self.assertIsNone(tandem.pair_info()['own'])
        self.assertEqual(tandem.save_config({'remote_url': ' https://thor.example.de/ '})['remote_url'], 'https://thor.example.de')
        self.assertEqual(tandem.pair_info()['own'], 'https://thor.example.de')
        for bad in ('thor.example.de', 'javascript:alert(1)', 'https://a b', 'https://' + 'x' * 120, 'https://x"y'):
            self.assertIn('error', tandem.save_config({'remote_url': bad}))
        self.assertEqual(tandem.public_config()['remote_url'], 'https://thor.example.de')  # a wrong value changes nothing
        self.assertEqual(tandem.save_config({'remote_url': ''})['remote_url'], '')
        self.assertIsNone(tandem.pair_info()['own'])

    def test_wifi_answer_is_kept_for_a_while(self):
        calls, real = [], tandem.wifi_state
        tandem.wifi_state = lambda rescan=False: calls.append(rescan) or ([{'ssid': 'Daheim'}], 'Daheim')
        try:
            tandem.WIFI['at'] = 0
            for _ in range(3): self.assertEqual(tandem.system_info()['ssid'], 'Daheim')
            self.assertEqual(calls, [False])  # asked once, answered three times
            tandem.system_info(rescan=True)
            self.assertEqual(calls, [False, True])  # opening the list still scans
        finally: tandem.wifi_state = real

    def test_wifi_link_for_the_status_bar(self):
        real_run, real_glob = tandem.run_quiet, tandem.glob.glob
        tandem.glob.glob = lambda pattern: ['/sys/class/net/wlan0/wireless'] if pattern.endswith('/wireless') else real_glob(pattern)
        tandem.run_quiet = lambda cmd, timeout=5: 'Connected to 00:11:22:33:44:55 (on wlan0)\n\tSSID: Daheim\n\tsignal: -63 dBm\n' if cmd[:2] == ['iw', 'dev'] else ''
        try:
            tandem.LINK['at'] = 0
            self.assertEqual(tandem.wifi_link(), {'ssid': 'Daheim', 'signal': 74})
            tandem.LINK['at'] = 0
            tandem.run_quiet = lambda cmd, timeout=5: 'Not connected.\n'
            self.assertEqual(tandem.wifi_link(), {'ssid': '', 'signal': 0})
        finally: tandem.run_quiet, tandem.glob.glob, tandem.LINK['at'] = real_run, real_glob, 0


class Doze(unittest.TestCase):
    def test_suspend_on_charger_only_darkens_and_wake_restores(self):
        writes, old = [], (tandem.on_power, tandem.set_raw, tandem.BACKLIGHTS)
        with tempfile.TemporaryDirectory() as d:
            for n in ('top', 'bot'): Path(d, n).mkdir(); Path(d, n, 'brightness').write_text('700')
            tandem.on_power, tandem.set_raw = (lambda: True), (lambda k, r: writes.append((k, r)))
            tandem.BACKLIGHTS = {'bt': d + '/top', 'bb': d + '/bot'}
            try:
                self.assertTrue(tandem.action('suspend')['doze'])
                self.assertFalse(tandem.action('wake')['doze'])
            finally: tandem.on_power, tandem.set_raw, tandem.BACKLIGHTS = old
        self.assertEqual(writes, [('bt', 0), ('bb', 0), ('bt', 700), ('bb', 700)])

    def test_dark_panel_still_wakes_lit(self):  # 18.11.: a doze over already dark panels woke to 0/0
        writes, old = [], (tandem.on_power, tandem.set_raw, tandem.BACKLIGHTS)
        with tempfile.TemporaryDirectory() as d:
            for n in ('top', 'bot'):
                Path(d, n).mkdir(); Path(d, n, 'brightness').write_text('0'); Path(d, n, 'max_brightness').write_text('400')
            tandem.on_power, tandem.set_raw = (lambda: True), (lambda k, r: writes.append((k, r)))
            tandem.BACKLIGHTS = {'bt': d + '/top', 'bb': d + '/bot'}
            try:
                tandem.action('suspend'); tandem.action('wake')
            finally: tandem.on_power, tandem.set_raw, tandem.BACKLIGHTS = old
        self.assertEqual(writes[-2:], [('bt', 300), ('bb', 300)])

    def test_power_key_and_lid(self):
        pk = tandem.PowerKey()
        self.assertIsNone(pk.event(1, 116, 1, 10.0, False))
        self.assertEqual(pk.event(1, 116, 0, 10.2, False), 'standby')  # short press -> standby
        self.assertIsNone(pk.event(1, 116, 1, 10.4, False))  # bounce guard
        self.assertEqual(pk.event(1, 116, 1, 12.0, True), 'wake')  # power press while dozing -> wake
        self.assertIsNone(pk.event(1, 116, 0, 12.15, False))  # wake release does not bounce back to standby
        self.assertIsNone(pk.event(1, 116, 1, 20.0, False))
        self.assertEqual(pk.tick(20.85, False), 'power')  # held >= 0.8 s -> power menu right away
        self.assertIsNone(pk.tick(21.0, False))  # once per hold
        self.assertIsNone(pk.event(1, 116, 0, 21.1, False))  # release after hold is ignored
        self.assertEqual(pk.event(5, 0, 1, 30.0, False), 'standby')  # lid closed -> standby
        self.assertIsNone(pk.event(1, 116, 1, 35.0, True))  # power bumped with lid closed -> ignored
        self.assertEqual(pk.event(5, 0, 0, 40.0, True), 'wake')  # lid opened -> wake
        self.assertIsNone(pk.event(5, 0, 1, 50.0, False, lid_sleep=False))  # lid_sleep disabled
        pk.event(5, 0, 0, 51.0, False)
        self.assertEqual(pk.resumed(60.0), 'wake')
        self.assertIsNone(pk.event(1, 116, 1, 60.5, False))  # post-suspend bounce guard

    def test_standby_pauses_playtime_and_per_game_options(self):
        t = make()
        t.dry = True
        gid = next(g['id'] for g in t.library.games.values() if g['s'] == 'psx')
        self.assertTrue(t.launch(gid).get('tracked'))
        t0 = t.run['since']
        tandem.sleep_game(t, True)
        tandem.SLEEP_STATE['since'] -= 3600  # 1 hour asleep
        tandem.sleep_game(t, False)
        self.assertGreaterEqual(t.run['since'] - t0, 3599)  # slept time shifted out of playtime
        self.assertEqual(t.gameopt({'profile': 'Eco', 'fps': 45, 'scale': 'linear'}), {'ok': True, 'profile': 'Eco', 'fps': 45, 'scale': 'linear'})
        self.assertIn('error', t.gameopt({'fps': 99}))
        t.quit()
        self.assertIsNone(t.run)
        self.assertTrue(t.launch(gid).get('tracked'))
        self.assertEqual((t.run['profile'], t.run['fps']), ('Eco', 45))  # remembered on next launch
        t.quit()
        cfg = tandem.save_config({'lid_sleep': False, 'charger_standby': 'sleep'})
        self.assertEqual((cfg['lid_sleep'], cfg['charger_standby']), (False, 'sleep'))
        tandem.save_config({'lid_sleep': True, 'charger_standby': 'doze'})

    def test_saves_night_mode_and_scaling(self):
        import saves
        fake_home = TMP / 'save-home'
        touch(fake_home / '.local/share/duckstation/memcards/card1.mcd', 'psx-save')
        touch(fake_home / '.local/share/banananative/0400486024DEC000/save/slot_00/progress.sav', 'zelda-save')
        touch(fake_home / '.local/share/banananative/0400486024DEC000/temp/vk_pipelines.bin', 'huge-cache')
        dest = TMP / 'backups'
        res = saves.backup(target='', home=fake_home, local_dir=dest, run_rsync=False)
        self.assertTrue(res.get('ok'), res)
        self.assertEqual(res['count'], 2)
        self.assertEqual((dest / 'latest/duckstation/card1.mcd').read_text(), 'psx-save')
        self.assertEqual((dest / 'latest/banananative-0400486024DEC000/slot_00/progress.sav').read_text(), 'zelda-save')
        self.assertFalse((dest / 'latest/banananative-0400486024DEC000/vk_pipelines.bin').exists())  # shader caches excluded
        self.assertEqual(len(list(dest.glob('saves-*.tar.gz'))), 1)
        # night_mode + save_target validation + per-game scaling
        cfg = tandem.save_config({'night_mode': 'warm', 'save_auto': False, 'save_target': 'user@server:~/saves'})
        self.assertEqual((cfg['night_mode'], cfg['save_auto'], cfg['save_target']), ('warm', False, 'user@server:~/saves'))
        self.assertIn('error', tandem.save_config({'save_target': 'not a ssh target'}))
        tandem.save_config({'night_mode': 'off', 'save_auto': True, 'save_target': saves.DEFAULT_TARGET})
        t = make(); t.dry = True
        gid = next(g['id'] for g in t.library.games.values() if g['s'] == 'psx')
        t.launch(gid)
        self.assertEqual(t.gameopt({'scale': 'sgsr'})['scale'], 'sgsr')
        t.quit()
        t.launch(gid)
        self.assertEqual(t.run['scale'], 'sgsr')
        t.quit()


class Themes(unittest.TestCase):
    def test_list_and_choice(self):
        folder = tandem.CONFIG.parent / 'themes'
        touch(folder / 'meins.json', '{"name": "Mein Thema", "colors": {"accent": "#00ff00"}}')
        touch(folder / 'kaputt.json', '{"name": ')
        ids = [t['id'] for t in tandem.themes()]
        self.assertEqual(ids[0], 'toravo')  # the default first
        self.assertTrue({'studio', 'oled', 'hell', 'meins'} <= set(ids))
        self.assertNotIn('kaputt', ids)
        self.assertEqual(tandem.public_config()['theme'], 'toravo')
        self.assertEqual(tandem.public_config()['rest_min'], 3)
        self.assertEqual(tandem.save_config({'rest_min': 10})['rest_min'], 10)
        self.assertEqual(tandem.save_config({'rest_min': 7})['rest_min'], 10)  # not offered: stays
        self.assertEqual(tandem.save_config({'theme': 'meins'})['theme'], 'meins')
        self.assertEqual(tandem.save_config({'theme': 'gibtsnicht'})['theme'], 'meins')  # unknown: stays
        (folder / 'meins.json').unlink()
        self.assertEqual(tandem.public_config()['theme'], 'toravo')  # the file is gone: back to the default


class SteamGame(unittest.TestCase):
    def test_when_a_steam_game_counts_as_over(self):
        over = tandem.steam_game_over
        self.assertFalse(over(0, 200, False))  # nothing seen yet, still within the time for starting
        self.assertTrue(over(0, 300, True))  # it never came
        self.assertFalse(over(44, 60, False))  # only the set-up step ran; Steam may be asking about cloud saves
        self.assertTrue(over(44, 60, True))
        self.assertFalse(over(600, 4, False))  # a short gap
        self.assertTrue(over(600, 10, False))  # the game was there and is gone


class DiabloSetup(unittest.TestCase):
    def test_setup_logic(self):  # ports/d2/setup.py checks its own plain logic (keys, checksums, the downloader's file list)
        setup = Path(__file__).resolve().parent / 'ports/d2/setup.py'
        if not setup.is_file(): self.skipTest('no ports/d2 here')  # the installed copy has no ports
        import subprocess, sys
        self.assertEqual(subprocess.run([sys.executable, str(setup), '--selftest'], capture_output=True, text=True).stdout.strip(), 'setup.py: ok')


class Pad(unittest.TestCase):
    def test_buttons_stick_and_repeat(self):
        pad = tandem.PadNav(32767)
        self.assertEqual(pad.event(1, 305, 1, 0), ['ok'])  # printed A
        self.assertEqual(pad.event(1, 305, 0, 0), [])  # release
        self.assertEqual([pad.event(1, c, 1, 0) for c in (304, 307, 308, 310, 311)], [['back'], ['fav'], ['close'], ['prev'], ['next']])
        self.assertEqual(pad.event(3, 16, 1, 1.0), ['right'])  # D-pad
        self.assertEqual(pad.tick(1.2), [])  # not yet repeating
        self.assertEqual(pad.tick(1.41), ['right'])
        self.assertEqual(pad.tick(1.45), [])
        self.assertEqual(pad.tick(1.54), ['right'])
        self.assertEqual(pad.event(3, 16, 0, 2.0), [])
        self.assertEqual(pad.tick(9), [])  # released: no repeat
        self.assertEqual(pad.event(3, 1, 9000, 3.0), [])  # inside the dead zone
        self.assertEqual(pad.event(3, 1, -30000, 3.1), ['up'])
        self.assertEqual(pad.event(3, 1, -32000, 3.2), [])  # still up: one step only
        self.assertEqual(pad.event(3, 1, 0, 3.3), [])



class ThorHardware(unittest.TestCase):
    """thor.py against a stand-in for the Decky loader: token, WebSocket upgrade, one call per connection."""
    def setUp(self):
        import socketserver, struct, thor
        self.thor, calls, rgb = thor, [], {'enabled': False, 'linkBrightness': False, 'brightness': 25, 'maxBrightness': 50, 'color': 'FFFFFF', 'saturation': 100}
        self.calls, self.rgb = calls, rgb
        class Decky(socketserver.StreamRequestHandler):
            def handle(self):
                line = self.rfile.readline().decode()
                while self.rfile.readline().strip(): pass
                if '/auth/token' in line: return self.wfile.write(b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\ntok')
                if 'auth=tok' not in line: return self.wfile.write(b'HTTP/1.1 403 Forbidden\r\n\r\n')
                self.wfile.write(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n')
                b1, b2 = self.rfile.read(2)
                n = b2 & 0x7f
                if n == 126: n = struct.unpack('>H', self.rfile.read(2))[0]
                mask = self.rfile.read(4)
                msg = json.loads(bytes(b ^ mask[i % 4] for i, b in enumerate(self.rfile.read(n))))
                plugin, method, *args = msg['args']
                calls.append((plugin, method, args))
                result = {'get_rgb': rgb, 'set_rgb': rgb, 'set_gyro_enabled': True,
                          'get_config': {'gyro': {'supported': True, 'enabled': True}, 'rgbSupported': True, 'osVersion': '1'}}[method]
                for reply in ({'type': 1, 'id': msg['id'] + 1, 'result': 'not mine'}, {'type': 1, 'id': msg['id'], 'result': result}):  # someone else's answer comes first
                    data = json.dumps(reply).encode()
                    self.wfile.write(b'\x81' + (bytes([len(data)]) if len(data) < 126 else b'\x7e' + struct.pack('>H', len(data))) + data)
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Decky)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.old = thor.DECKY, thor.POWER
        thor.DECKY, thor.POWER = self.server.server_address, ['false']  # no armada-powerd here

    def tearDown(self):
        self.thor.DECKY, self.thor.POWER = self.old
        self.server.shutdown(); self.server.server_close()

    def test_state_and_changes(self):
        thor = self.thor
        state = thor.state()
        self.assertEqual((state['rgb']['color'], state['rgb']['level'], state['gyro']['enabled'], state['power']), ('FFFFFF', 25, True, None))
        thor.change('rgb', {'color': '#1060ff', 'brightness': 80, 'enabled': True})
        self.assertEqual(next(c for c in reversed(self.calls) if c[1] == 'set_rgb'), ('Armada Control', 'set_rgb', [True, False, '1060FF', 100, 50, 80]))
        thor.change('rgb', {'linkBrightness': True, 'brightness': 40})  # linked: the slider sets the ceiling too
        self.assertEqual(next(c for c in reversed(self.calls) if c[1] == 'set_rgb')[2], [False, True, 'FFFFFF', 100, 40, 40])
        thor.change('gyro', False)
        self.assertIn(('Armada Control', 'set_gyro_enabled', [False]), self.calls)
        self.assertIn('error', thor.change('rgb', {'color': 'nicht'}))
        self.assertIn('error', thor.change('profile', 'Turbo'))
        self.assertIn('error', thor.change('profile', 'Eco'))  # armada-powerd is missing here
        self.assertIn('error', thor.change('fan', 1))



class Bluetooth(unittest.TestCase):
    """bluetooth.py against a stand-in for BlueZ's D-Bus objects (pairing with a real device needs hands at the Thor)."""
    A1, A2 = 'AA:BB:CC:DD:EE:01', 'AA:BB:CC:DD:EE:02'
    OBJS = {'/org/bluez': {'org.bluez.AgentManager1': {}},
            '/org/bluez/hci0': {'org.bluez.Adapter1': {'Powered': True, 'Discovering': True}},
            '/org/bluez/hci0/dev_1': {'org.bluez.Device1': {'Address': A1, 'Name': 'WH-1000XM4', 'Alias': 'WH-1000XM4', 'Icon': 'audio-headset', 'Paired': True, 'Connected': True},
                                      'org.bluez.Battery1': {'Percentage': 70}},
            '/org/bluez/hci0/dev_2': {'org.bluez.Device1': {'Address': A2, 'Name': '8BitDo Pro 2', 'Class': 0x002508, 'Paired': False, 'RSSI': -50}},
            '/org/bluez/hci0/dev_3': {'org.bluez.Device1': {'Address': 'AA:BB:CC:DD:EE:03', 'Paired': False, 'RSSI': -40}}}  # nameless: left out

    class Bus:
        def __init__(self, objs): self.objs, self.calls = objs, []
        def get_object(self, name, path):
            bus = self
            class Obj:
                def __getattr__(self, method): return lambda *a, **k: bus.calls.append((path, method, a)) or (bus.objs if method == 'GetManagedObjects' else None)
            return Obj()

    def test_state(self):
        import bluetooth
        s = bluetooth.state(self.OBJS)
        self.assertTrue(s['powered'] and s['scanning'])
        self.assertEqual([(d['name'], d['kind'], d['paired'], d['connected'], d['battery']) for d in s['devices']],
                         [('WH-1000XM4', 'audio', True, True, 70), ('8BitDo Pro 2', 'pad', False, False, None)])
        self.assertIn('error', bluetooth.state({}))

    def test_actions(self):
        try: import dbus  # noqa: F401  only where python3-dbus is (ArmadaOS)
        except ImportError: self.skipTest('python3-dbus fehlt')
        import bluetooth
        b = self.Bus(self.OBJS)
        agent = []
        old = bluetooth.Agent.on, bluetooth.Agent.off
        bluetooth.Agent.on, bluetooth.Agent.off = lambda bus: agent.append('on'), lambda bus: agent.append('off')
        try:
            self.assertEqual(bluetooth.act(self.A2, 'pair', b), {'text': '8BitDo Pro 2 verbunden.'})
            self.assertEqual([c[1] for c in b.calls if c[0].endswith('dev_2')], ['Pair', 'Set', 'Connect'])
            self.assertEqual(agent, ['on', 'off'])
            b.calls.clear()
            self.assertEqual(bluetooth.act(self.A1, 'forget', b)['text'], 'WH-1000XM4 vergessen.')
            self.assertEqual([c[1] for c in b.calls if c[1] != 'GetManagedObjects'], ['RemoveDevice'])
            self.assertIn('error', bluetooth.act('AA:BB:CC:DD:EE:09', 'connect', b))
            self.assertIn('error', bluetooth.act(self.A1, 'rm -rf', b))
        finally: bluetooth.Agent.on, bluetooth.Agent.off = old


class English(unittest.TestCase):
    """The English interface: the setting persists, and every German text the screens can show has an English one."""
    GERMAN = __import__('re').compile(r'[äöüÄÖÜß„]|\b(der|die|das|und|nicht|ist|kein|keine|mit|für|von|auf|noch|wird|bitte|Spiel|Spiele|starten|beenden|'
                                      r'Einstellungen|Taste|Tasten|Akku|Bildschirm|fehlt|gefunden|installiert|läuft|Suche|Fehler|Passwort|Konto)\b')
    FILES = ['tandem.py', 'thor.py', 'bluetooth.py', 'controls.py', 'saves.py', 'thor_storage.py', 'thor_updater.py',
             'thor_airpods.py', 'thor_features.py', 'telemetry.py', 'companion.py', 'setup.py',
             'ui/tandem_ui.py', 'ui/settings_view.py', 'ui/quick_view.py', 'ui/screensaver.py', 'ui/qr.py',
             'ui/decks/media.py', 'ui/decks/offline.py', 'ui/decks/youtube.py', 'ui/decks/plex.py', 'ui/decks/gallery.py',
             'ui/decks/pack.py', 'ui/decks/mpv.py', 'ui/decks/universal.py', 'ui/decks/dualscreen.py', 'ui/decks/pcstream.py']
    KEEP = {'Tandem/0.1 (game launcher)', '<p><b>Die PIN stimmt nicht.</b></p>', 'ist', '7: kein 200',  # not shown, or translated as a whole (rules) or by the web page
            'Emulator fehlt (unter Apps oder im Armada Store installieren) – ', ' Installieren: Einstellungsseite › Gerät.', 'Passwort für ', 'keine Spiele',
            'Läuft · ', ' · Akku 7 %7', ' (lädt)', 'Angemeldet und eingetragen in: ', 'Einstellungen · ', ' · geschützt', ' Das Passwort tippst du unten ein.', ' · lädt',
            '„7“ ', 'Neu von ', 'TLS-Zertifikat nicht nutzbar, Einstellungsseite bleibt bei HTTP: 7', 'Toravo Tandem: 7 Spiele aus 7 – http://127.0.0.1:7/',  # log lines
            '^1234567890ß´', 'qwertzuiopü+', 'asdfghjklöä#', 'QWERTZUIOPÜ*', "ASDFGHJKLÖÄ'"}  # key caps
    KEEP |= {'Kein „Microsoft X-Box 360 pad“ gefunden (läuft Tandem?).', 'Drücke gedrucktes 7 ...', '7: 7: 7: ist 7, soll 7',
             '7 Spiel', '[^A-Za-z0-9ÄÖÜäöüß _\\-]'}  # controls.measure + internal search/filename regexes

    def test_setting(self):
        tandem.save_config({'lang': 'en'})
        self.assertEqual(tandem.public_config()['lang'], 'en')
        tandem.save_config({'lang': 'xx'})
        self.assertEqual(tandem.public_config()['lang'], 'en')
        tandem.save_config({'lang': 'de'})
        self.assertEqual(tandem.public_config()['lang'], 'de')
        self.assertIn('Sprache / Language', tandem.REMOTE_PAGE)
        self.assertNotIn('__EN__', tandem.REMOTE_PAGE)

    def test_lookup(self):
        import sys
        sys.path.insert(0, str(Path(tandem.__file__).parent / 'ui'))
        from lang import tr
        for de, en in (('Spiel beenden', 'Quit game'), (' ist pausiert', ' is paused'), ('EINSTELLUNGEN · BILDSCHIRME & TON', 'SETTINGS · SCREENS & SOUND'),
                       ('Läuft · Game Boy', 'Playing · Game Boy'), ('12:00  ·  80 % lädt  ·  Lüfter 2400', '12:00  ·  80 % charging  ·  Fan 2400'),
                       ('„Tetris“ beenden?', 'Quit “Tetris”?'), ('Mo 17. Nov.', 'Mon 17 Nov'), ('vor 3 Tagen', '3 days ago'), ('Tetris', 'Tetris')):
            self.assertEqual(tr(de), en)

    def test_covered(self):
        """Every German literal in the code the screens draw from translates (f-strings with 7 for each value)."""
        import ast, sys
        here = Path(tandem.__file__).parent
        sys.path.insert(0, str(here / 'ui'))
        from lang import tr
        missing = []
        for name in self.FILES:
            if not (here / name).is_file(): continue  # setup.py and the decks are not installed everywhere
            tree, inner = ast.parse((here / name).read_text(encoding='utf-8')), set()
            docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr)}
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr):
                    inner |= {id(v) for v in node.values}
                    text = ''.join(v.value if isinstance(v, ast.Constant) else '7' for v in node.values)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and id(node) not in inner: text = node.value
                else: continue
                if '\n' in text or text in self.KEEP or not self.GERMAN.search(text): continue
                if tr(text) == text: missing.append(f'{name}:{node.lineno}: {text}')
        self.assertEqual(missing, [], "\n".join(missing))


class VolumeRepeatTest(unittest.TestCase):
    def test_vol_repeat(self):
        v = tandem.VolRepeat()
        self.assertEqual(v.event(1, 115, 1, 10.0), 5)
        self.assertEqual(v.tick(10.20), 0)
        self.assertEqual(v.tick(10.36), 5)
        self.assertEqual(v.tick(10.46), 5)
        self.assertEqual(v.event(1, 115, 2, 10.50), 0)  # kernel EV_REP ignored if present
        self.assertEqual(v.event(1, 115, 0, 10.52), 0)
        self.assertEqual(v.tick(10.70), 0)
        self.assertEqual(v.event(1, 114, 1, 20.0), -5)
        self.assertEqual(v.tick(20.36), -5)
        v.clear()
        self.assertEqual(v.tick(20.50), 0)


class YouTubeAuthAndPromptTest(unittest.TestCase):
    def tearDown(self):
        tandem.save_config({'yt_forget': True})

    def test_firefox_wal_export_and_sso_fallback(self):
        import sqlite3
        prof, cfile, _ = tandem.yt_paths()
        prof.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(prof / 'cookies.sqlite')
        try:
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('CREATE TABLE moz_cookies (host TEXT, path TEXT, isSecure INT, expiry INT, name TEXT, value TEXT)')
            # Live uncommitted/uncheckpointed WAL rows: Firefox 128+ ms timestamp + session cookie (expiry 0) on .google.com
            con.execute("INSERT INTO moz_cookies VALUES ('.google.com', '/', 1, 1893456000000, 'SAPISID', 'abc123')")
            con.execute("INSERT INTO moz_cookies VALUES ('.google.com', '/', 1, 0, 'SID', 'sidval')")
            con.commit()  # stays in cookies.sqlite-wal while connection is open!
            self.assertTrue(tandem.yt_cookie_signed_in())
            self.assertTrue(tandem.export_yt_cookies())
            self.assertEqual(stat.S_IMODE(cfile.stat().st_mode), 0o600)
            txt = cfile.read_text()
            self.assertIn('.google.com\tTRUE\t/\tTRUE\t1893456000\tSAPISID\tabc123', txt)
            self.assertIn('.youtube.com\tTRUE\t/\tTRUE\t1893456000\tSAPISID\tabc123', txt)  # SSO fallback mirrored to .youtube.com
        finally:
            con.close()

    def test_cookie_import_formats_and_forget(self):
        _, cfile, _ = tandem.yt_paths()
        self.assertIn('error', tandem.save_config({'yt_cookies': ''}))
        self.assertIn('error', tandem.save_config({'yt_cookies': '.example.com\tTRUE\t/\tFALSE\t0\tFOO\tbar\n'}))
        res = tandem.save_config({'yt_cookies': json.dumps([{'domain': '.youtube.com', 'path': '/', 'secure': True, 'expirationDate': 1893456000, 'name': '__Secure-3PAPISID', 'value': 'xyz'}])})
        self.assertEqual(res.get('text'), 'YouTube-Cookies gespeichert.')
        self.assertTrue(tandem.public_config()['yt_cookie'])
        self.assertTrue(tandem.public_config()['yt_set'])
        self.assertEqual(stat.S_IMODE(cfile.stat().st_mode), 0o600)
        tandem.save_config({'yt_forget': True})
        self.assertFalse(tandem.public_config()['yt_cookie'])
        self.assertFalse(cfile.exists())

    def test_keyboard_type_text_and_prompt_state(self):
        import sys
        pressed = []
        kb = tandem.Keyboard.__new__(tandem.Keyboard)
        kb.fd = 1
        kb.press = lambda code, mods=(): pressed.append((code, list(mods))) or {'ok': True}
        kb.type_text('a@b.de', 'de')
        self.assertEqual(pressed, [(30, []), (16, ['altgr']), (48, []), (52, []), (32, []), (18, [])])
        sys.path.insert(0, str(Path(tandem.__file__).parent / 'ui'))
        import qr
        m = qr.matrix('https://www.youtube.com/activate?user_code=ABCD-EFGH')
        self.assertEqual(len(m), 29)  # v3: 29x29
        self.assertIn('<svg', qr.svg('https://plex.tv/link'))
        self.assertTrue(qr.png('hi').startswith(b'\x89PNG\r\n\x1a\n'))
        _, _, afile = tandem.yt_paths()
        tandem._write_priv_json(afile, {'access': 'a', 'refresh': 'r', 'until': int(time.time()) + 3600, 'tv': True})
        self.assertTrue(tandem.yt_auth_signed_in())
        self.assertTrue(tandem.public_config()['yt_set'])
        tandem.save_config({'yt_forget': True})
        self.assertFalse(tandem.yt_auth_signed_in())
        self.assertFalse(tandem.public_config()['yt_set'])


class CompanionAndLibraryUpgradesTest(unittest.TestCase):
    def test_sfc_gamelist_m3u_and_collections(self):
        root = TMP / 'lib-upgrades/ROMs'
        touch(root / 'sfc/Chrono Trigger (Japan).sfc', 'rom')
        touch(root / 'psx/Final Fantasy VII (Disc 1).chd', 'd1')
        touch(root / 'psx/Final Fantasy VII (Disc 2).chd', 'd2')
        touch(root / 'psx/Final Fantasy VII.m3u', 'Final Fantasy VII (Disc 1).chd\nFinal Fantasy VII (Disc 2).chd\n')
        touch(root.parent / 'Cocoon/gamelists/snes/gamelist.xml',
              '<?xml version="1.0"?><gameList><game><path>./Chrono Trigger (Japan).sfc</path><name>Chrono Trigger</name>'
              '<desc>Time travel RPG.</desc><genre>RPG</genre><developer>Square</developer>'
              '<releasedate>19950311T000000</releasedate><cocoon:timetobeathastily>82800</cocoon:timetobeathastily></game></gameList>')
        lib = tandem.Library([str(root)], TMP / 'no-steam')
        games = lib.scan()
        sfc_games = [g for g in games.values() if g['s'] == 'sfc']
        self.assertEqual(len(sfc_games), 1)
        ct = sfc_games[0]
        self.assertEqual((ct['t'], ct['genre'], ct['dev'], ct['year'], ct['ttb'], ct['desc']),
                         ('Chrono Trigger', 'RPG', 'Square', '1995', 23.0, 'Time travel RPG.'))
        psx_games = [g for g in games.values() if g['s'] == 'psx']
        self.assertEqual([g['t'] for g in psx_games], ['Final Fantasy VII'])  # Disc 1/2 hidden by .m3u

        t = tandem.Tandem(lib, dry=True)
        self.assertTrue(t.collection_act({'a': 'create', 'name': 'RPGs', 'id': ct['id']})['ok'])
        self.assertEqual(t.saved['collections']['RPGs'], [ct['id']])
        self.assertTrue(t.collection_act({'a': 'sort', 'sort': 'year'})['ok'])
        self.assertEqual(t.saved['sort'], 'year')
        self.assertTrue(t.collection_act({'a': 'hide', 'id': ct['id']})['ok'])
        self.assertIn(ct['id'], t.saved['hidden'])
        t.collection_act({'a': 'hide', 'id': ct['id']})
        self.assertNotIn(ct['id'], t.saved['hidden'])

    def test_saves_restore_notes_sketch_upload_and_telemetry(self):
        import io, sys
        import companion, saves, telemetry
        # 1. Time-Machine savegame snapshot & restore
        fhome = TMP / 'restore-home'
        bdir = TMP / 'restore-backups'
        touch(fhome / '.local/share/duckstation/memcards/card1.mcd', 'original-save')
        b1 = saves.backup(target='', home=fhome, local_dir=bdir, run_rsync=False)
        self.assertTrue(b1.get('ok'))
        snaps = saves.snapshots(bdir)
        self.assertEqual(len(snaps), 1)
        touch(fhome / '.local/share/duckstation/memcards/card1.mcd', 'corrupted-save')
        time.sleep(1.05)  # distinct timestamp for pre-restore safety backup
        r1 = saves.restore(snaps[0]['file'], home=fhome, local_dir=bdir)
        self.assertTrue(r1.get('ok'), r1)
        self.assertEqual((fhome / '.local/share/duckstation/memcards/card1.mcd').read_text(), 'original-save')
        self.assertGreaterEqual(len(saves.snapshots(bdir)), 2)  # safety backup created before restore

        # 2. Notes, checklists & PNG sketch
        n = companion.notes_save('game123', {'text': 'Boss weak to ice', 'add_check': 'Get key'})
        self.assertEqual((n['text'], n['checks']), ('Boss weak to ice', [{'t': 'Get key', 'done': False}]))
        n2 = companion.notes_save('game123', {'toggle_idx': 0})
        self.assertTrue(n2['checks'][0]['done'])
        sys.path.insert(0, str(Path(tandem.__file__).parent / 'ui'))
        import qr
        sample_png = qr.png('sketch-test')
        self.assertTrue(companion.sketch_save('game123', sample_png)['has_sketch'])
        self.assertEqual(companion.sketch_bytes('game123'), sample_png)

        # 3. Streaming wireless upload (ROM auto-detect + Guide + unsafe path rejection)
        uroot = TMP / 'upload-roms/ROMs'
        uroot.mkdir(parents=True, exist_ok=True)
        rom_bytes = b'SUPER_MARIO_WORLD_ROM_DATA'
        up = companion.handle_upload(io.BytesIO(rom_bytes), len(rom_bytes), 'Super Mario World.sfc', 'rom', 'auto', '',
                                     [str(uroot)], TMP / 'cfg', set(tandem.SYSTEMS))
        self.assertTrue(up.get('ok'), up)
        self.assertEqual((uroot / 'snes/Super Mario World.sfc').read_bytes(), rom_bytes)
        up_g = companion.handle_upload(io.BytesIO(b'# Walkthrough\nStep 1'), 20, 'walkthrough.md', 'guide', '', 'game123',
                                       [str(uroot)], TMP / 'cfg', set(tandem.SYSTEMS))
        self.assertTrue(up_g.get('ok'), up_g)
        self.assertEqual(len(companion.guides_list('game123')['items']), 1)

        # 4. Telemetry (Qualcomm Full power_now quirk + Discharging watts/playtime + PipeWire parser + Dual-screen config)
        ps_full = TMP / 'ps-full/battery'
        for k, v in (('type', 'Battery'), ('status', 'Full'), ('capacity', '100'), ('current_now', '0'),
                     ('voltage_now', '4400000'), ('power_now', '43635399'), ('charge_now', '6064000'), ('charge_full', '6064000')):
            touch(ps_full / k, v)
        bf = telemetry.battery_detail(ps_full.parent)
        self.assertEqual((bf['level'], bf['charging'], bf['watts'], bf['mins_left']), (100, True, 0.0, None))

        ps_dis = TMP / 'ps-dis/battery'
        for k, v in (('type', 'Battery'), ('status', 'Discharging'), ('capacity', '50'), ('current_now', '-1000000'),
                     ('voltage_now', '4000000'), ('charge_now', '3000000'), ('charge_full', '6000000')):
            touch(ps_dis / k, v)
        bd = telemetry.battery_detail(ps_dis.parent)
        self.assertEqual((bd['watts'], bd['mins_left']), (4.0, 180))

        streams = telemetry.audio_streams('Audio\n └─ Streams:\n        81. RetroArch                           [vol: 0.80]\n        85. tandem-bgm                          [vol: 0.45]\n')
        self.assertEqual(streams, [{'id': 81, 'name': 'RetroArch', 'vol': 80, 'muted': False, 'bgm': False},
                                   {'id': 85, 'name': 'tandem-bgm', 'vol': 45, 'muted': False, 'bgm': True}])
        self.assertIn('error', telemetry.wake_on_lan('not-a-mac'))

        dhome = TMP / 'dual-home'
        touch(dhome / '.config/melonDS/melonDS.toml', '[Instance0.Window0]\nEnabled = true\nScreenSizing = 0\n[Instance0.Window1]\nEnabled = false\n')
        touch(dhome / '.config/azahar-emu/qt-config.ini', '[Layout]\nlayout_option=0\n')
        companion.setup_dual_emu('nds', 'melonDS', dhome)
        companion.setup_dual_emu('n3ds', 'Azahar', dhome)
        mtoml = (dhome / '.config/melonDS/melonDS.toml').read_text()
        self.assertIn('ScreenSizing = 4', mtoml)
        self.assertIn('ScreenSizing = 5', mtoml)
        self.assertIn('layout_option=5', (dhome / '.config/azahar-emu/qt-config.ini').read_text())

        # 5. MangoHud in-place update (preserves inode for mangoapp inotify), stats_payload & controls_style
        mh = TMP / 'mangohud.test'
        mh.write_text('no_display\n')
        ino_before = mh.stat().st_ino
        old_mf = telemetry.mangohud_files
        telemetry.mangohud_files = lambda *a: [mh]
        try:
            self.assertEqual(tandem.save_config({'hud_level': 2})['hud_level'], 2)
            self.assertEqual(mh.stat().st_ino, ino_before)
            self.assertIn('horizontal', mh.read_text())
            self.assertEqual(tandem.save_config({'hud_level': 0})['hud_level'], 0)
            self.assertEqual(mh.read_text().strip(), 'no_display')
        finally:
            telemetry.mangohud_files = old_mf

        self.assertEqual(tandem.save_config({'controls_style': 'xbox'})['controls_style'], 'xbox')
        self.assertEqual(tandem.controls_info()['style'], 'xbox')
        self.assertEqual(tandem.save_config({'controls_style': 'thor'})['controls_style'], 'thor')

        t_stat = make()
        gid_s = next(iter(t_stat.library.games))
        today = time.strftime('%Y-%m-%d')
        t_stat.saved['played'] = {gid_s: {'secs': 5400, 'last': int(time.time())}}
        t_stat.saved['sessions'] = {today: 1800}
        sp = t_stat.stats_payload()
        self.assertEqual((sp['total_secs'], sp['week_secs'], sp['played_count'], len(sp['days'])), (5400, 1800, 1, 7))
        self.assertEqual(sp['top_games'][0]['id'], gid_s)

        # 6. Switch-2 features: Virtual Game Card pinning, synthesized WAVs, battery health, saver_style, Peanuts Native discovery
        self.assertTrue(t_stat.collection_act({'a': 'pin', 'id': gid_s})['ok'])
        self.assertEqual(t_stat.saved['pinned'], [gid_s])
        t_stat.collection_act({'a': 'pin', 'id': gid_s})
        self.assertEqual(t_stat.saved['pinned'], [])

        c5 = tandem.save_config({'saver_style': 'arcade', 'charge_alert': 90, 'ui_sounds': 'subtle'})
        self.assertEqual((c5['saver_style'], c5['charge_alert'], c5['ui_sounds']), ('arcade', 90, 'subtle'))
        tandem.save_config({'saver_style': 'kosmos', 'charge_alert': 0, 'ui_sounds': 'off'})

        wav = telemetry.synth_wav(telemetry.SOUNDS['locator'])
        self.assertTrue(wav.startswith(b'RIFF') and b'WAVEfmt ' in wav)

        touch(ps_dis / 'state_of_health', '99')
        touch(ps_dis / 'cycle_count', '14')
        touch(ps_dis / 'temp', '315')
        bd2 = telemetry.battery_detail(ps_dis.parent)
        self.assertEqual((bd2['health'], bd2['cycles'], bd2['bat_temp']), (99, 14, 31.5))

        nhome = TMP / 'native-home'
        apprun = nhome / '.local/opt/peanuts/AppDir/AppRun'
        touch(apprun, '#!/bin/sh\n')
        os.chmod(apprun, 0o755)
        touch(nhome / '.local/opt/peanuts/AppDir/usr/share/banananative/source', 'version 0.1.6-1\n')
        touch(nhome / '.local/opt/peanuts/builder/peanuts/games.tsv', '01001B300B9BE000\tDiablo III: Eternal Collection\t\tyes\n')
        touch(nhome / 'Games/PeanutsNative/DiabloIII/01001B300B9BE000-work/android-pack/game.tsv',
              'title_id\t01001B300B9BE000\nname\tDiablo III: Eternal Collection\n')
        touch(nhome / 'Games/PeanutsNative/DiabloIII/icon.png', 'png')
        touch(nhome / 'Games/PeanutsNative/DiabloIII/box.png', 'box')
        npacks = companion.discover_native_packs([], nhome)
        self.assertEqual(len(npacks), 1)
        self.assertEqual((npacks[0]['tid'], npacks[0]['engine']), ('01001B300B9BE000', 'PeanutsNative'))
        self.assertTrue(npacks[0]['cover'].endswith('icon.png') and npacks[0]['box'].endswith('box.png'))
        sinfo = companion.switch_native_info({'s1': {'id': 's1', 't': 'Diablo III', 's': 'switch', 'path': '/tmp/Diablo [01001B300B9BE000].nsp'}}, [], nhome)
        self.assertEqual((sinfo['peanuts_version'], sinfo['catalog_count'], sinfo['games'][0]['converted']), ('0.1.6-1', 1, True))

        cands = tandem._box_candidates('Chrono Trigger (Uncensored)')
        self.assertIn('Chrono Trigger (Germany)', cands)
        self.assertIn('Chrono Trigger (USA)', cands)
        self.assertEqual(tandem._norm_box_title("Pokémon: Let’s Go, Evoli! (PeanutsNative)"),
                         tandem._norm_box_title("Pokémon: Let's Go, Eevee!"))

        t_sw = tandem.Tandem(lambda: {'systems': {}, 'games': [], 'apps': []}, dry=True)
        out_sw = {}
        th_sw = threading.Thread(target=lambda: out_sw.update(t_sw.ask_swkbd({
            'title': 'Wie lautet dein Name?', 'initial': 'Tobias', 'min': 1, 'max': 12
        })))
        th_sw.start()
        for _ in range(50):
            if t_sw.swkbd: break
            time.sleep(0.01)
        self.assertTrue(t_sw.prompt_open and t_sw.swkbd['title'] == 'Wie lautet dein Name?')
        t_sw.finish_swkbd(t_sw.swkbd['id'], True, 'Tobias123456789')
        th_sw.join(timeout=2)
        self.assertEqual(out_sw, {'ok': True, 'text': 'Tobias123456'})
        self.assertFalse(t_sw.prompt_open)

        # Native companion matching for all 11 BananaNative / PeanutsNative titles + cstate persistence + UDP bridge
        expected_companions = [
            ({'id': 'native-01001b300b9be000', 'tid': '01001B300B9BE000', 't': 'Diablo III'}, 'd3'),
            ({'id': 'native-01005ca01580e000', 'tid': '01005CA01580E000', 't': 'Persona 5 Royal'}, 'p5r'),
            ({'id': 'native-01006bb00c6f0000', 'tid': '01006BB00C6F0000', 't': "Link's Awakening"}, 'zelda_la'),
            ({'id': 'native-0400486024dec000', 'tid': '0400486024DEC000', 't': 'Ocarina of Time'}, 'oot'),
            ({'id': 'native-0100000000010000', 'tid': '0100000000010000', 't': 'SUPER MARIO ODYSSEY'}, 'odyssey'),
            ({'id': 'native-010015100b514000', 'tid': '010015100B514000', 't': 'Super Mario Bros. Wonder'}, 'wonder'),
            ({'id': 'native-0400c3f00006e000', 'tid': '0400C3F00006E000', 't': 'Mario Kart World'}, 'mkworld'),
            ({'id': 'native-0100187003a36000', 'tid': '0100187003A36000', 't': "Pokemon: Let's Go, Eevee!"}, 'letsgo'),
            ({'id': 'native-01009aa000faa000', 'tid': '01009AA000FAA000', 't': 'Sonic Mania Plus'}, 'mania'),
            ({'id': 'native-0100606026f12000', 'tid': '0100606026F12000', 't': 'FINAL FANTASY RESONANCE'}, 'ffres'),
            ({'id': 'native-010051f0207b2000', 'tid': '010051F0207B2000', 't': 'Tomodachi Life'}, 'tomodachi'),
            ({'id': 'n64-oot', 's': 'n64', 't': 'The Legend of Zelda: Ocarina of Time'}, 'oot'),
        ]
        for g_in, want_key in expected_companions:
            self.assertEqual(companion.resolve_native_companion(g_in), want_key)
        cs = companion.cstate_save('d3', {'toggle': 'd3_kanai', 'patch': {'gr_best': 95}})
        self.assertTrue(cs['ok'] and cs['data']['done']['d3_kanai'] and cs['data']['gr_best'] == 95)
        self.assertEqual(companion.cstate_get('d3')['data']['gr_best'], 95)
        import socket as _sock
        with _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM) as rx_s:
            rx_s.bind(('127.0.0.1', 0))
            port_u = rx_s.getsockname()[1]
            rx_s.settimeout(1.0)
            res_u = companion.send_native_pad('NOTE:CLeft,CUp,CRight', port=port_u)
            self.assertTrue(res_u['ok'])
            self.assertEqual(rx_s.recv(64), b'NOTE:CLeft,CUp,CRight')

        # GBADuo v1.0.1 multi-region matching + automatic companion pack download for owned GBA games
        self.assertTrue(companion.same_gba_game('BPRE', 'BPRD'))   # FireRed US <-> DE
        self.assertTrue(companion.same_gba_game('AGSE', 'AGSP'))   # Golden Sun US <-> EU
        self.assertFalse(companion.same_gba_game('CGB-AZ8E', 'CGB-AZ8P'))  # GB/GBC never cross-match
        self.assertFalse(companion.same_gba_game('BPRE', 'BPGE'))  # FireRed != LeafGreen

        gba_dir = TMP / 'gbaduo-test'
        gba_dir.mkdir(parents=True, exist_ok=True)
        rom_fr_de = bytearray(0x200)
        rom_fr_de[0xAC:0xB0], rom_fr_de[0xB2] = b'BPRD', 0x96  # German FireRed (BPRD)
        (gba_dir / 'Pokemon Feuerrot.gba').write_bytes(rom_fr_de)
        rom_unb = bytearray(0x200)
        rom_unb[0xAC:0xB0], rom_unb[0xB2] = b'BPRE', 0x96     # Pokemon Unbound hack (BPRE header)
        (gba_dir / 'Pokemon Unbound v2.gba').write_bytes(rom_unb)

        fake_cat_json = json.dumps({
            'formatVersion': 1,
            'companions': [
                {'id': 'pokemon-firered-companion', 'title': 'FireRed', 'version': '3.1.0',
                 'download': 'https://example.test/fr.zip', 'games': [{'gameCode': 'BPRE'}],
                 'overview': 'overview/fr.png'},
                {'id': 'pokemon-unbound-companion', 'title': 'Unbound', 'version': '0.2.0',
                 'download': 'https://example.test/unb.zip', 'games': [{'gameCode': 'BPRE'}]},
            ],
        }).encode('utf-8')

        def _make_pack_zip(pid, code):
            zb = io.BytesIO()
            with tandem.zipfile.ZipFile(zb, 'w') as zf:
                zf.writestr(f'{pid}/manifest.json', json.dumps({
                    'id': pid, 'name': pid, 'version': '3.1.0', 'formatVersion': 4,
                    'match': {'gameCode': [code], 'crc32': []}, 'layout': 'layout.json',
                }))
                zf.writestr(f'{pid}/layout.json', json.dumps({'type': 'text', 'text': 'ok'}))
            return zb.getvalue()

        fr_zip = _make_pack_zip('pokemon-firered-companion', 'BPRE')
        unb_zip = _make_pack_zip('pokemon-unbound-companion', 'BPRE')

        class _FakeResp:
            def __init__(self, payload): self.p = payload
            def read(self, *_a): return self.p
            def __enter__(self): return self
            def __exit__(self, *a): pass

        def _fake_open(req, timeout=10):
            u = req.full_url if hasattr(req, 'full_url') else str(req)
            if u.endswith('companions.json'): return _FakeResp(fake_cat_json)
            if u.endswith('fr.zip'): return _FakeResp(fr_zip)
            if u.endswith('unb.zip'): return _FakeResp(unb_zip)
            raise OSError(u)

        owned_games = [
            {'id': 'gba-fr-de', 's': 'gba', 't': 'Pokémon Feuerrot', 'path': str(gba_dir / 'Pokemon Feuerrot.gba')},
            {'id': 'gba-unb', 's': 'gba', 't': 'Pokémon Unbound', 'path': str(gba_dir / 'Pokemon Unbound v2.gba')},
        ]
        sync_res = companion.sync_owned_gba_packs(owned_games, tandem.rom_identity, cfg_dir=gba_dir / 'cfg',
                                                  force_catalog=True, opener=_fake_open)
        self.assertTrue(sync_res['ok'])
        self.assertEqual(sorted(sync_res['installed']), ['pokemon-firered-companion', 'pokemon-unbound-companion'])
        # German FireRed (BPRD) matches US FireRed pack (BPRE) via v1.0.1 multi-region (other_region=True), NOT Unbound!
        m_fr = companion.match_packs_for_rom('BPRD', 0, 'Pokémon Feuerrot', installed=companion.list_installed_packs(gba_dir / 'cfg'))
        self.assertEqual((m_fr['best_installed'], m_fr['best_other_region']), ('pokemon-firered-companion', True))
        # Unbound ROM matches Unbound pack as exact preferred pack!
        m_unb = companion.match_packs_for_rom('BPRE', 0, 'Pokémon Unbound', installed=companion.list_installed_packs(gba_dir / 'cfg'))
        self.assertEqual((m_unb['best_installed'], m_unb['best_other_region']), ('pokemon-unbound-companion', False))


class ThorStorageTests(unittest.TestCase):
    def test_system_backup_and_restore_roundtrip(self):
        import thor_storage
        fake_home = TMP / 'sysbk-home'
        dest_dir = TMP / 'sysbk-dest'
        (fake_home / '.config/tandem/packs/pokemon-emerald-companion').mkdir(parents=True, exist_ok=True)
        (fake_home / '.config/tandem/packs/pokemon-emerald-companion/manifest.json').write_text('{"id":"emerald"}')
        (fake_home / '.ssh').mkdir(parents=True, exist_ok=True)
        key_file = fake_home / '.ssh/id_ed25519'
        key_file.write_text('secret-key-material')
        os.chmod(key_file, 0o600)
        link_file = fake_home / '.config/tandem/current-pack'
        if link_file.exists() or link_file.is_symlink():
            link_file.unlink()
        link_file.symlink_to('packs/pokemon-emerald-companion')

        res = thor_storage.run_system_backup(mode='profile', home=fake_home, dest_dir=dest_dir)
        self.assertTrue(res.get('ok'), res)
        arcs = thor_storage.list_system_backups(dest_dir)
        self.assertEqual(len(arcs), 1)
        self.assertEqual(arcs[0]['kind'], 'profile')

        # Wipe files & restore into clean home, verifying symlinks and 0600 permissions survive!
        restored = TMP / 'sysbk-restored'
        restored.mkdir(parents=True, exist_ok=True)
        r_res = thor_storage.restore_system_backup(arcs[0]['file'], home=restored, dest_dir=dest_dir)
        self.assertTrue(r_res.get('ok'), r_res)
        self.assertEqual((restored / '.config/tandem/packs/pokemon-emerald-companion/manifest.json').read_text(), '{"id":"emerald"}')
        self.assertTrue((restored / '.config/tandem/current-pack').is_symlink())
        self.assertEqual(os.stat(restored / '.ssh/id_ed25519').st_mode & 0o777, 0o600)

        # Reject path traversal or unknown filenames
        self.assertIn('error', thor_storage.restore_system_backup('../evil.tar.zst', home=restored, dest_dir=dest_dir))

    def test_shrink_sfdisk_plan_4k_sectors_and_repeat_shrink(self):
        import thor_storage
        # Exact AYN Thor UFS 4.0 LUN 0 geometry (4096-byte logical sectors, sda17 userdata = 113 GiB, sda18..20 ArmadaOS)
        sec = 4096
        ud_start = 1916416       # ~7.31 GiB
        ud_size = 29622016       # 113.0 GiB
        armada_efi = 31538432    # right after userdata
        sfdisk_doc = {
            'partitiontable': {
                'label': 'gpt',
                'id': '98101b32-bbe2-4bf2-a06e-2bb33d000c20',
                'device': '/dev/sda',
                'unit': 'sectors',
                'firstlba': 6,
                'lastlba': 61388794,
                'sectorsize': sec,
                'table-length': 128,
                'partitions': [
                    {'node': '/dev/sda16', 'start': 1850880, 'size': 65536,
                     'type': '0fc63daf-8483-4772-8e79-3d69d8477de4', 'uuid': '11111111-1111-1111-1111-111111111111', 'name': 'metadata'},
                    {'node': '/dev/sda17', 'start': ud_start, 'size': ud_size,
                     'type': '1b81e7e6-f50d-419b-a739-2eec8cfa3335', 'uuid': '22222222-2222-2222-2222-222222222222', 'name': 'userdata'},
                    {'node': '/dev/sda18', 'start': armada_efi, 'size': 131072,
                     'type': 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b', 'uuid': '33333333-3333-3333-3333-333333333333', 'name': 'ARMADA'},
                    {'node': '/dev/sda19', 'start': armada_efi + 131072, 'size': 262144,
                     'type': 'bc13c2ff-59e6-4262-a352-b275fd6f7172', 'uuid': '44444444-4444-4444-4444-444444444444', 'name': 'ARMADA_BOOT'},
                    {'node': '/dev/sda20', 'start': armada_efi + 393216, 'size': 29418496,
                     'type': '0fc63daf-8483-4772-8e79-3d69d8477de4', 'uuid': '6c7d87a1-336c-4a78-8078-845910d52d27', 'name': 'ARMADA_ROOT'},
                ],
            }
        }
        plan = thor_storage.build_shrink_sfdisk_plan(sfdisk_doc, 16)
        self.assertEqual(plan['new_node'], '/dev/sda21')
        self.assertEqual(plan['new_label'], 'ARMADA_DATA')
        self.assertEqual(plan['android_new_gib'], 16.0)
        self.assertEqual(plan['gained_gib'], 97.0)
        # 1 MiB alignment check (256 * 4096 = 1 MiB)
        self.assertEqual((plan['new_start'] * sec) % (1024 * 1024), 0)
        self.assertEqual(((plan['new_start'] + plan['new_size']) * sec) % (1024 * 1024), 0)
        # Mounted ARMADA partitions remain 100% untouched byte-for-byte!
        self.assertIn('/dev/sda20: start=31931648, size=29418496, type=0fc63daf-8483-4772-8e79-3d69d8477de4, name="ARMADA_ROOT", uuid=6c7d87a1-336c-4a78-8078-845910d52d27', plan['script'])

        # Second subsequent shrink (16 GiB -> 8 GiB) must stop at sda21 ceiling and create sda22 ARMADA_DATA2!
        doc2 = json.loads(json.dumps(sfdisk_doc))
        doc2['partitiontable']['partitions'][1]['size'] = plan['userdata_new_size']
        doc2['partitiontable']['partitions'].append({
            'node': '/dev/sda21', 'start': plan['new_start'], 'size': plan['new_size'],
            'type': thor_storage.LINUX_PART_TYPE, 'uuid': '55555555-5555-5555-5555-555555555555', 'name': 'ARMADA_DATA',
        })
        plan2 = thor_storage.build_shrink_sfdisk_plan(doc2, 8)
        self.assertEqual((plan2['new_node'], plan2['new_label'], plan2['gained_gib']), ('/dev/sda22', 'ARMADA_DATA2', 8.0))
        self.assertLessEqual(plan2['new_start'] + plan2['new_size'], plan['new_start'])
        with self.assertRaises(ValueError):
            thor_storage.build_shrink_sfdisk_plan(doc2, 6)  # below ANDROID_MIN_GIB=8

    def test_moment_menu_filter_and_pre_quit_selection(self):
        import companion, math
        w, h = 160, 90
        # 1) Final Fantasy-style dark-blue save menu: 4 stacked horizontal slot boxes with white borders & small text dots
        ff_menu = bytearray(w * h * 3)
        for y in range(h):
            for x in range(w):
                off = (y * w + x) * 3
                in_box = 10 <= x < w - 10 and 8 <= y < h - 8
                slot_border = in_box and (y in (8, 26, 44, 62, 80) or x in (10, w - 11))
                fake_text = in_box and (y % 18 in (6, 7)) and (16 <= x < 62) and (x % 3 == 0)
                if slot_border or fake_text:
                    ff_menu[off:off + 3] = b'\xe8\xec\xf8'
                elif in_box:
                    ff_menu[off:off + 3] = b'\x12\x1e\x58'
                else:
                    ff_menu[off:off + 3] = b'\x06\x08\x14'
        res_menu = companion.score_gameplay_frame_rgb(w, h, ff_menu)
        self.assertTrue(res_menu['is_menu'], res_menu)

        # 2) Rich gameplay world scene (sky gradient, textured terrain, varied colors & sprites, even with 4:3 pillarboxes!)
        world = bytearray(w * h * 3)
        for y in range(h):
            for x in range(20, w - 20):  # 4:3 active viewport with black pillarbox bars on left/right
                off = (y * w + x) * 3
                if y < 34:
                    r = 45 + (y * 3)
                    g = 110 + (y * 2) + int(12 * math.sin(x * 0.25))
                    b = 215 - y
                else:
                    n = ((x * 37 + y * 53) ^ (x * y)) & 31
                    r = min(255, 40 + (x % 55) * 2 + n)
                    g = min(255, 95 + ((y * 3 + x) % 70) + n)
                    b = min(255, 35 + ((x * 5 - y * 2) % 60) + n)
                world[off:off + 3] = bytes((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))
        res_world = companion.score_gameplay_frame_rgb(w, h, world)
        self.assertFalse(res_world['is_menu'], res_world)
        self.assertGreater(res_world['score'], 0.55)
        self.assertGreater(res_world['score'], res_menu['score'] * 3)

        # 3) Pre-quit selection skips final-seconds menu/borderline shots in favor of real world gameplay >=25s before quit
        f_world = TMP / 'moment-world.png'
        f_late = TMP / 'moment-late.png'
        f_menu = TMP / 'moment-menu.png'
        for fp in (f_world, f_late, f_menu):
            fp.write_bytes(TINY_PNG)
        entries = [
            {'path': str(f_world), 'at': 1000.0, 'score': res_world['score'], 'is_menu': False, 'motion': 9.5},
            {'path': str(f_late), 'at': 1032.0, 'score': 0.50, 'is_menu': False, 'motion': 1.0},  # 8s before quit (opening menu)
            {'path': str(f_menu), 'at': 1038.0, 'score': res_menu['score'], 'is_menu': True, 'motion': 0.4},
        ]
        chosen = companion.pick_best_moment(entries, quit_at=1040.0, min_pre_quit_secs=25.0)
        self.assertEqual(chosen['path'], str(f_world))

    def test_steam_companion_provisioner_and_updater_rollback(self):
        import hashlib, thor_updater
        fake_home = TMP / 'upd-home'
        ffix_dir = fake_home / '.local/share/Steam/steamapps/common/FINAL FANTASY IX'
        fo4_dir = fake_home / '.local/share/Steam/steamapps/common/Fallout 4'
        (ffix_dir / 'x64/FF9_Data/Managed').mkdir(parents=True, exist_ok=True)
        (ffix_dir / 'Memoria.ini').write_text('[Graphics]\nEnabled = 1\n', encoding='utf-8')
        (ffix_dir / 'x64/FF9_Data/Managed/Assembly-CSharp.dll').write_bytes(b'OLD_FFIX_DLL')
        (fo4_dir / 'Data/F4SE/Plugins').mkdir(parents=True, exist_ok=True)
        (fo4_dir / 'Data/F4SE/Plugins/ThorPipBoy.dll').write_bytes(b'OLD_PIPBOY_V010')

        ffix_blob = b'MZ_NEW_FFIX_V030_COMPANION_DLL'
        pip_blob = b'MZ_NEW_PIPBOY_V020_COMPANION_DLL'
        pip_ini = b'[Server]\nPort = 27016\n'
        ffix_sha = hashlib.sha256(ffix_blob).hexdigest()
        pip_sha = hashlib.sha256(pip_blob).hexdigest()

        elf_v1 = b'\x7fELF' + b'V1_ARM64_APPIMAGE_' + (b'\x90' * 5000)
        elf_v2 = b'\x7fELF' + b'V2_ARM64_APPIMAGE_' + (b'\x90' * 5000)
        elf_v2_sha = hashlib.sha256(elf_v2).hexdigest()
        apps_dir = fake_home / 'Applications'
        apps_dir.mkdir(parents=True, exist_ok=True)
        (apps_dir / 'DuckStation.AppImage').write_bytes(elf_v1)

        class _Resp:
            def __init__(self, data): self.d = data
            def read(self, *_a): return self.d
            def __enter__(self): return self
            def __exit__(self, *a): pass

        def _opener(req, timeout=15):
            u = req.full_url if hasattr(req, 'full_url') else str(req)
            if 'harmssi/thor-ffix/releases/latest' in u:
                return _Resp(json.dumps({
                    'tag_name': 'v0.3.0',
                    'assets': [
                        {'name': 'Assembly-CSharp.dll', 'browser_download_url': 'https://example.test/ffix.dll'},
                        {'name': 'SHA256SUMS', 'browser_download_url': 'https://example.test/ffix.sums'},
                    ],
                }).encode())
            if u == 'https://example.test/ffix.sums':
                return _Resp(f'{ffix_sha}  Assembly-CSharp.dll\n'.encode())
            if u == 'https://example.test/ffix.dll':
                return _Resp(ffix_blob)
            if 'harmssi/thor-pipboy/releases/latest' in u:
                return _Resp(json.dumps({
                    'tag_name': 'v0.2.0',
                    'assets': [
                        {'name': 'ThorPipBoy.dll', 'browser_download_url': 'https://example.test/pipboy.dll'},
                        {'name': 'ThorPipBoy.ini', 'browser_download_url': 'https://example.test/pipboy.ini'},
                        {'name': 'SHA256SUMS', 'browser_download_url': 'https://example.test/pipboy.sums'},
                    ],
                }).encode())
            if u == 'https://example.test/pipboy.sums':
                return _Resp(f'{pip_sha}  ThorPipBoy.dll\n'.encode())
            if u == 'https://example.test/pipboy.dll':
                return _Resp(pip_blob)
            if u == 'https://example.test/pipboy.ini':
                return _Resp(pip_ini)
            if 'stenzek/duckstation/releases' in u:
                return _Resp(json.dumps([{
                    'tag_name': 'v0.1-10950',
                    'assets': [{
                        'name': 'DuckStation-arm64.AppImage',
                        'browser_download_url': 'https://example.test/duck-v2.AppImage',
                        'size': len(elf_v2),
                        'digest': f'sha256:{elf_v2_sha}',
                        'updated_at': '2026-11-22T12:00:00Z',
                    }],
                }]).encode())
            if u == 'https://example.test/duck-v2.AppImage':
                return _Resp(elf_v2)
            raise OSError(u)

        # 1) Automatic Steam companion installation + SHA256SUMS check + .thor-bak backup + Memoria.ini [ThorStatus]
        res_st = thor_updater.sync_steam_companions(home=fake_home, apply_updates=True, opener=_opener)
        self.assertEqual(len(res_st['updated']), 2, res_st)
        self.assertEqual((ffix_dir / 'x64/FF9_Data/Managed/Assembly-CSharp.dll').read_bytes(), ffix_blob)
        self.assertEqual((ffix_dir / 'x64/FF9_Data/Managed/Assembly-CSharp.dll.thor-bak').read_bytes(), b'OLD_FFIX_DLL')
        self.assertIn('[ThorStatus]\nEnabled = 1', (ffix_dir / 'Memoria.ini').read_text())
        self.assertEqual((fo4_dir / 'Data/F4SE/Plugins/ThorPipBoy.dll').read_bytes(), pip_blob)
        self.assertEqual((fo4_dir / 'Data/F4SE/Plugins/ThorPipBoy.ini').read_bytes(), pip_ini)

        # Second sync is an instant idempotent no-op because local SHA-256 already matches SHA256SUMS!
        res_st2 = thor_updater.sync_steam_companions(home=fake_home, apply_updates=True, opener=_opener)
        self.assertEqual(res_st2['updated'], [])

        # 2) AppImage SHA-256 digest update detection, atomic install, .prev backup & 1-tap rollback
        chk = thor_updater.check_appimages(apps_dir=apps_dir, opener=_opener, network=True)
        duck = next(a for a in chk if a['id'] == 'duckstation')
        self.assertTrue(duck['update_available'])
        upd = thor_updater.install_or_update_appimage('duckstation', apps_dir=apps_dir, opener=_opener)
        self.assertTrue(upd.get('ok'), upd)
        self.assertEqual((apps_dir / 'DuckStation.AppImage').read_bytes(), elf_v2)
        self.assertEqual((apps_dir / 'DuckStation.AppImage.prev').read_bytes(), elf_v1)
        rb = thor_updater.rollback_appimage('duckstation', apps_dir=apps_dir)
        self.assertTrue(rb.get('ok'), rb)
        self.assertEqual((apps_dir / 'DuckStation.AppImage').read_bytes(), elf_v1)

        # 3) Custom Obtainium-style GitHub feed + RetroArch UDP memory bridge
        ra_cfg = fake_home / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg'
        ra_cfg.parent.mkdir(parents=True, exist_ok=True)
        ra_cfg.write_text('network_cmd_enable = "false"\n', encoding='utf-8')
        self.assertTrue(thor_updater.ensure_retroarch_udp_companion(home=fake_home))
        self.assertIn('network_cmd_enable = "true"', ra_cfg.read_text())
        self.assertTrue(thor_updater.save_custom_feed('https://github.com/example/my-emu')['ok'])
        self.assertTrue(any(f['id'] == 'custom-my-emu' for f in thor_updater.all_appimage_feeds()))
        thor_updater.remove_custom_feed('custom-my-emu')
        self.assertFalse(any(f['id'] == 'custom-my-emu' for f in thor_updater.all_appimage_feeds()))

    def test_fast_charging_diagnostics_travel_mode_and_ai_launchers(self):
        import telemetry
        ps_root = TMP / 'fake-psy'
        tc_root = TMP / 'fake-typec'
        (ps_root / 'battery').mkdir(parents=True, exist_ok=True)
        (ps_root / 'qcom-battmgr-usb').mkdir(parents=True, exist_ok=True)
        (ps_root / 'ucsi-psy').mkdir(parents=True, exist_ok=True)
        (tc_root / 'port0').mkdir(parents=True, exist_ok=True)
        (tc_root / 'port0-partner').mkdir(parents=True, exist_ok=True)

        touch(ps_root / 'battery/type', 'Battery\n')
        touch(ps_root / 'battery/status', 'Charging\n')
        touch(ps_root / 'battery/capacity', '42\n')
        touch(ps_root / 'battery/constant_charge_current', '6000000\n')
        touch(ps_root / 'battery/constant_charge_current_max', '9000000\n')
        touch(ps_root / 'battery/time_to_full_avg', '2400\n')
        touch(ps_root / 'qcom-battmgr-usb/type', 'USB\n')
        touch(ps_root / 'qcom-battmgr-usb/online', '1\n')
        touch(ps_root / 'qcom-battmgr-usb/voltage_now', '9000000\n')
        touch(ps_root / 'qcom-battmgr-usb/input_current_limit', '3000000\n')
        touch(ps_root / 'qcom-battmgr-usb/usb_type', 'Unknown SDP DCP [PD_PPS]\n')
        touch(ps_root / 'ucsi-psy/type', 'USB\n')
        touch(ps_root / 'ucsi-psy/online', '1\n')
        touch(ps_root / 'ucsi-psy/usb_type', 'C [PD_PPS]\n')
        touch(tc_root / 'port0/data_role', 'host [device]\n')
        touch(tc_root / 'port0-partner/supports_usb_power_delivery', 'yes\n')

        chg_fast = telemetry.charger_detail(root=ps_root, typec_root=tc_root)
        self.assertTrue(chg_fast['fast_charging'], chg_fast)
        self.assertEqual(chg_fast['protocol'], 'PD_PPS')
        self.assertEqual((chg_fast['voltage_v'], chg_fast['current_limit_a'], chg_fast['max_input_w']), (9.0, 3.0, 27.0))
        self.assertEqual(chg_fast['mins_to_full'], 40)

        # Simulate 5V SDP computer port -> must flag pc_port=True and fast_charging=False
        touch(ps_root / 'qcom-battmgr-usb/voltage_now', '5000000\n')
        touch(ps_root / 'qcom-battmgr-usb/usb_type', 'Unknown [SDP] DCP PD\n')
        touch(ps_root / 'ucsi-psy/usb_type', '[C] PD\n')
        chg_pc = telemetry.charger_detail(root=ps_root, typec_root=tc_root)
        self.assertFalse(chg_pc['fast_charging'])
        self.assertTrue(chg_pc['pc_port'])

        # AI direct launchers (--dangerously-skip-permissions for both Claude Code and Google Antigravity `agy`)
        tandem.save_config({'ai_workdir': str(TMP), 'panel_hz': 60, 'auto_travel': True})
        cfg_pub = tandem.public_config()
        self.assertEqual(cfg_pub['panel_hz'], 60)
        self.assertTrue(cfg_pub['auto_travel'])
        self.assertEqual(tandem.base_panel_hz(), 60)
        sc_claude = tandem.write_ai_launcher('claude')
        sc_agy = tandem.write_ai_launcher('agy')
        self.assertIn('claude --dangerously-skip-permissions', sc_claude.read_text())
        self.assertIn('agy --dangerously-skip-permissions', sc_agy.read_text())
        self.assertIn('BROWSER=', sc_agy.read_text())
        self.assertTrue((tandem.STATE / 'ai-bin' / 'ai-browser.sh').is_file())
        self.assertTrue(callable(tandem.x11))
        self.assertTrue(callable(tandem.x_press_code))
        from types import SimpleNamespace
        r_aiw = tandem.ai_window_act(SimpleNamespace(dry=True), 'toggle')
        self.assertTrue(r_aiw.get('ok'))
        fake_t = SimpleNamespace(dry=True, run={'layout': 'de'}, publish=lambda *a, **kw: None)
        st_qr = tandem.ai_auth_register(fake_t, 'https://accounts.google.com/o/oauth2/auth?test=1', open_ui=True)
        self.assertTrue(st_qr.get('ok') and st_qr.get('open') and st_qr.get('has_url'))
        if st_qr.get('qr'):
            import sys as _sys
            _sys.path.insert(0, str(Path(tandem.__file__).parent / 'ui'))
            import qr
            self.assertGreater(len(qr.matrix(st_qr['qr'])), 20)
        page = tandem.ai_login_page(tandem.AI_AUTH['token'])
        self.assertIn('accounts.google.com', page)
        sub_code = tandem.ai_auth_submit(fake_t, '4/0A-sample-code')
        self.assertTrue(sub_code.get('ok') and sub_code.get('mode') == 'code')
        sub_cb = tandem.ai_auth_submit(fake_t, 'http://localhost:41234/callback?code=abc')
        self.assertTrue(sub_cb.get('ok') and sub_cb.get('mode') == 'callback')
        for title, expected in (
            ('WoW Forever', 'wow'),
            ('Super Mario Sunshine', 'sunshine'),
            ("Luigi's Mansion", 'luigis_mansion'),
            ('Paper Mario: The Thousand-Year Door', 'ttyd'),
            ('Mario Kart: Double Dash!!', 'mkdd'),
            ('Super Smash Bros. Melee', 'melee'),
            ('Animal Crossing', 'ac_gc'),
            ('Crash Bandicoot: The Wrath of Cortex', 'crash_woc'),
        ):
            self.assertEqual(tandem.companion.resolve_native_companion({'t': title, 's': 'gc'}), expected)

        # v1.2.0: Thor Speaker Audio-DSP filter-chain, RetroArch Zero-Lag + offline OLED Slang shaders & Auto-Resume
        dsp_conf = telemetry.build_speaker_dsp_conf('cinema')
        self.assertIn('libpipewire-module-filter-chain', dsp_conf)
        self.assertIn('alsa_output.platform-sound.HiFi__Speaker__sink', dsp_conf)
        self.assertIn('toravo_speaker_dsp', dsp_conf)
        self.assertEqual(telemetry.build_speaker_dsp_conf('off'), '')
        sids = telemetry._parse_sink_ids(
            'Audio\n ├─ Sinks:\n │      54. Built-in Audio Speaker playback     [vol: 0.55]\n'
            ' ├─ Sources:\n ├─ Filters:\n │    - filter-chain-1\n'
            ' │      83. toravo_speaker_dsp                  [Audio/Sink]\n'
            ' │      89. toravo_speaker_dsp.output           [Stream/Output/Audio]\n └─ Streams:\n'
        )
        self.assertEqual(sids, {'speaker': 54, 'dsp': 83})

        ra_home = TMP / 'ra-home'
        ra_cfg = ra_home / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg'
        touch(ra_cfg, 'audio_latency = "64"\nvideo_max_swapchain_images = "3"\npreemptive_frames_enable = "false"\n')
        res_gba = tandem.companion.configure_retroarch(
            {'ra_zerolag': True, 'ra_autoresume': True, 'ra_shader': 'auto'},
            game={'s': 'gba', 't': 'Golden Sun'}, opt={}, home=ra_home,
        )
        self.assertEqual(res_gba['shader_mode'], 'lcd')
        self.assertTrue(res_gba['preemptive'] and res_gba['shader_path'].endswith('handheld-lcd.slangp'))
        self.assertTrue(Path(res_gba['shader_path']).is_file())
        cfg_txt = ra_cfg.read_text()
        self.assertIn('video_max_swapchain_images = "2"', cfg_txt)
        self.assertIn('audio_latency = "28"', cfg_txt)
        self.assertIn('preemptive_frames_enable = "true"', cfg_txt)
        self.assertIn('savestate_auto_save = "true"', cfg_txt)
        self.assertIn('video_shader_enable = "true"', cfg_txt)

        # 3D cores (N64) keep preemptive_frames off under Zero-Lag and pick CRT-OLED in 'auto' mode
        res_n64 = tandem.companion.configure_retroarch(
            {'ra_zerolag': True, 'ra_autoresume': False, 'ra_shader': 'auto'},
            game={'s': 'n64', 't': 'Mario Kart 64'}, opt={}, home=ra_home,
        )
        self.assertEqual((res_n64['shader_mode'], res_n64['preemptive'], res_n64['autoresume']), ('crt', False, False))
        cfg_txt2 = ra_cfg.read_text()
        self.assertIn('preemptive_frames_enable = "false"', cfg_txt2)
        self.assertIn('savestate_auto_save = "false"', cfg_txt2)

        c12 = tandem.save_config({'speaker_dsp': 'clear', 'ra_zerolag': False, 'ra_autoresume': False, 'ra_shader': 'crt'})
        self.assertEqual((c12['speaker_dsp'], c12['ra_zerolag'], c12['ra_autoresume'], c12['ra_shader']), ('clear', False, False, 'crt'))

        # v1.3.0: PlayTranslate-style Tandem German Game Translator (per-game crop persistence, engine status, options)
        import thor_translate
        t_prefs = TMP / 'tr-prefs.json'
        self.assertEqual(thor_translate.game_crop_spec('gba1', t_prefs)['region'], 'full')
        st_crop = thor_translate.set_game_crop('gba1', 'custom', [0.05, 0.62, 0.90, 0.32], prefs_file=t_prefs)
        self.assertEqual(st_crop['region'], 'custom')
        self.assertEqual(st_crop['crop'], [0.05, 0.62, 0.9, 0.32])
        st_opt = thor_translate.set_options(None, auto=False, mode='offline', src='ja')
        self.assertEqual((st_opt['mode'], st_opt['src'], st_opt['target']), ('offline', 'ja', 'de'))
        thor_translate.set_options(None, auto=False, mode='auto', src='auto', clear_history=True)

        # v1.4.0: CBZ/PDF Manual Reader, Bifrost LED modes, Custom Artwork overrides & Safe Storage Cleaner
        import zipfile
        cbz_path = TMP / 'manual.cbz'
        tiny_png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x02\x00\x00\x00\xfd\xd4\x9as'
            b'\x00\x00\x00\x16IDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        with zipfile.ZipFile(cbz_path, 'w') as zf:
            zf.writestr('01_cover.png', tiny_png)
            zf.writestr('02_controls.png', tiny_png)
        b_info = tandem.companion.book_info(cbz_path)
        self.assertEqual((b_info['format'], b_info['pages']), ('cbz', 2))
        raw_p0, mime_p0 = tandem.companion.book_page_png(cbz_path, 0)
        self.assertEqual(mime_p0, 'image/png')
        self.assertTrue(raw_p0.startswith(b'\x89PNG'))

        # Bifrost smart LED modes (battery + fast-charge cyan + thermal guardian)
        self.assertEqual(telemetry.bifrost_rgb_color('battery', {'level': 85, 'charging': True}, fast_chg=True), '00D0C0')
        self.assertEqual(telemetry.bifrost_rgb_color('battery', {'level': 12, 'charging': False}), 'FF2000')
        self.assertEqual(telemetry.bifrost_rgb_color('thermal', temp_c=44), '00D0C0')
        self.assertEqual(telemetry.bifrost_rgb_color('thermal', temp_c=80), 'FF2000')
        c14 = tandem.save_config({'rgb_mode': 'ambilight'})
        self.assertEqual((c14['rgb_mode'], c14['rgb_sync']), ('ambilight', True))
        c14_s = tandem.save_config({'rgb_mode': 'static'})
        self.assertEqual((c14_s['rgb_mode'], c14_s['rgb_sync']), ('static', False))

        # Safe Storage Cleaner: keeps installed AppIDs + Proton runtimes, cleans orphaned compatdata/shadercache/trash
        import thor_storage
        cl_home = TMP / 'clean-home'
        cl_steam = cl_home / '.local/share/Steam'
        touch(cl_steam / 'steamapps/appmanifest_1091500.acf', '"AppState" { "appid" "1091500" "name" "Installed Game" }\n')
        touch(cl_steam / 'steamapps/appmanifest_1493710.acf', '"AppState" { "appid" "1493710" "name" "Proton Experimental" }\n')
        touch(cl_steam / 'steamapps/compatdata/1091500/pfx/system.reg', 'keep' * 500)
        touch(cl_steam / 'steamapps/compatdata/999999/pfx/system.reg', 'orphan' * 2000)
        touch(cl_steam / 'steamapps/shadercache/999999/foz.bin', 'shader' * 2000)
        touch(cl_home / '.local/share/Trash/files/old.iso', 'trash' * 2000)
        scan_before = thor_storage.scan_storage_cleanup(home=cl_home, steam_dir=cl_steam)
        self.assertEqual(scan_before['compatdata']['items'], ['999999'])
        self.assertEqual(scan_before['shadercache']['count'], 1)
        res_cl = thor_storage.run_storage_cleanup('all', home=cl_home, steam_dir=cl_steam)
        self.assertTrue(res_cl['ok'] and res_cl['removed'] >= 3)
        self.assertTrue((cl_steam / 'steamapps/compatdata/1091500/pfx/system.reg').is_file())
        self.assertFalse((cl_steam / 'steamapps/compatdata/999999').exists())

        # v1.5.0: Native AirPods AAP (L2CAP 0x1001), 3x4 Macro Pad, Live Cheats, Heroic GOG/Epic, Netplay & BT Low-Latency
        import thor_airpods, thor_features
        # 1) AirPods AAP battery, ear detection & noise control packet roundtrip
        aap_batt = bytes.fromhex('04 00 04 00 04 00 03 02 01 64 02 01 04 01 63 01 01 08 01 52 02 01')
        ev_b = thor_airpods.parse_aap_packet(aap_batt)
        self.assertEqual(ev_b['kind'], 'battery')
        self.assertEqual((ev_b['battery']['right']['level'], ev_b['battery']['left']['level'], ev_b['battery']['case']['level']), (100, 99, 82))
        self.assertTrue(ev_b['battery']['left']['charging'] and not ev_b['battery']['right']['charging'])
        ev_ear = thor_airpods.parse_aap_packet(bytes.fromhex('04 00 04 00 06 00 00 01'))
        self.assertEqual((ev_ear['kind'], ev_ear['both_in_ear'], ev_ear['any_in_ear']), ('ear', False, True))
        pkt_anc = thor_airpods.build_aap_noise_packet('anc')
        ev_nm = thor_airpods.parse_aap_packet(pkt_anc)
        self.assertEqual((ev_nm['kind'], ev_nm['mode']), ('noise_mode', 'anc'))
        self.assertTrue(thor_airpods.is_airpods_device({'Name': "Tobias's AirPods Pro"}))
        self.assertTrue(thor_airpods.is_airpods_device({'Name': 'Wireless', 'UUIDs': [thor_airpods.APPLE_AAP_UUID]}))
        self.assertIn('bluez5.enable-sbc-xq = true', thor_airpods.build_bt_low_latency_conf(True))

        # 2) 3x4 Stream-Deck Macro Pad (presets, key combo parser, custom tile save)
        self.assertEqual(thor_features.parse_macro_step('CTRL+SHIFT+S'), (31, ['ctrl', 'shift']))
        mdir = TMP / 'macros'
        m0 = thor_features.macros_get('steam123', {'s': 'steam', 'genre': 'Strategy'}, mdir)
        self.assertEqual(m0['preset'], 'strategy')
        m1 = thor_features.macros_save('steam123', {'idx': 0, 'spec': 'F5', 'label': 'Schnell'}, macros_dir=mdir)
        self.assertEqual((m1['preset'], m1['pads'][0]['spec'], m1['pads'][0]['label']), ('custom', 'F5', 'Schnell'))

        # 3) Live Libretro .cht Cheat & 60-FPS/Widescreen Manager
        cdir = TMP / 'cheats'
        c_add = thor_features.cheat_toggle('gba1', add_desc='60 FPS Patch', add_code='82001234 0001', cheats_dir=cdir)
        self.assertEqual(len(c_add['items']), 1)
        self.assertTrue(c_add['items'][0]['enable'])
        c_tog = thor_features.cheat_toggle('gba1', idx=0, cheats_dir=cdir)
        self.assertFalse(c_tog['items'][0]['enable'])

        # 4) Couch-Coop Dock Pad Swap & RetroArch LAN Netplay
        thor_features.set_netplay('host')
        self.assertEqual(thor_features.netplay_cli_args(), ['--host', '--nick', 'Thor'])
        thor_features.set_netplay('off')
        self.assertEqual(thor_features.netplay_cli_args(), [])
        thor_features.apply_dock_coop_pad(True, True, home=ra_home)
        self.assertIn('input_player1_joypad_index = "1"', ra_cfg.read_text())
        thor_features.apply_dock_coop_pad(False, False, home=ra_home)
        self.assertIn('input_player1_joypad_index = "0"', ra_cfg.read_text())

        # 5) Heroic GOG & Epic Games discovery bridge
        h_home = TMP / 'heroic-home'
        gog_dir = h_home / 'Games/GOG/Cyberpunk'
        epic_dir = h_home / 'Games/Epic/Hades'
        touch(gog_dir / 'start.sh', '#!/bin/sh\n')
        touch(epic_dir / 'Hades.exe', 'MZ')
        touch(h_home / '.config/heroic/gog_store/installed.json',
              json.dumps({'installed': [{'appName': '1423049311', 'title': 'Cyberpunk 2077 GOG', 'install_path': str(gog_dir)}]}))
        touch(h_home / '.config/heroic/legendaryConfig/legendary/installed.json',
              json.dumps({'Sugar': {'title': 'Hades Epic', 'install_path': str(epic_dir), 'executable': 'Hades.exe'}}))
        ext_pc = thor_features.discover_external_pc_games(h_home)
        self.assertEqual({g['store'] for g in ext_pc}, {'GOG', 'Epic'})

        tandem.save_config({'speaker_dsp': 'cinema', 'ra_zerolag': True, 'ra_autoresume': True, 'ra_shader': 'sharp',
                            'rgb_mode': 'cover', 'replay_buffer': False, 'dock_pad_swap': True, 'bt_low_latency': True,
                            'panel_hz': 120, 'auto_travel': False, 'ai_workdir': ''})


if __name__ == '__main__':
    unittest.main()
