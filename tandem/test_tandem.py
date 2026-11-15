"""Self-check for tandem.py: python3 test_tandem.py (standard library only, runs on ArmadaOS too)."""
import json, os, stat, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix='tandem-test-'))
os.environ['HOME'] = str(TMP / 'home')
os.environ['XDG_STATE_HOME'] = str(TMP / 'state')
os.environ['XDG_CONFIG_HOME'] = str(TMP / 'config')
import tandem  # noqa: E402  (after HOME is redirected)

HOME = TMP / 'home'
SD = TMP / 'sd'


def touch(path, text=''):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def setUpModule():
    touch(SD / 'ROMs/psx/Breath of Fire III (Europe).chd')
    touch(SD / 'ROMs/psx/notes.txt')
    touch(SD / 'ROMs/gba/Legend of Zelda, The - The Minish Cap (Europe) (En,Fr,De,Es,It).gba')
    touch(SD / 'ROMs/switch/Some Game.nsp')
    touch(SD / 'Cocoon/downloaded_media/psx/icon/Breath of Fire III (Europe)__cocoon_edit_12_abcdef.png', 'png')
    touch(SD / 'Cocoon/downloaded_media/psx/hero/Breath of Fire III (Europe)__cocoon_edit_12_abcdef.jpg', 'jpg')
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
        payload = t.library.payload(t.saved)
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

    def test_system_info_shape(self):
        info = json.loads(self.call('/api/system')[1])
        self.assertEqual(set(info), {'ssid', 'networks', 'storage', 'host'})
        self.assertEqual(info['storage'][0]['name'], 'Intern')
        self.assertIn('error', json.loads(self.call('/api/wifi', {'ssid': ''})[1]))

    def test_favourite_and_ui(self):
        gid = next(iter(self.t.library.games))
        self.assertEqual(json.loads(self.call('/api/fav', {'id': gid})[1])['fav'], [gid])
        self.call('/api/ui', {'tab': 1, 'sys': 'psx', 'i': 2, 'from': 'x'})
        self.assertEqual(json.loads(self.call('/api/state')[1])['ui'], {'tab': 1, 'sys': 'psx', 'i': 2})
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


class Pad(unittest.TestCase):
    def test_buttons_stick_and_repeat(self):
        pad = tandem.PadNav(32767)
        self.assertEqual(pad.event(1, 305, 1, 0), ['ok'])  # printed A
        self.assertEqual(pad.event(1, 305, 0, 0), [])  # release
        self.assertEqual([pad.event(1, c, 1, 0) for c in (304, 307, 308, 310, 311)], [['back'], ['close'], ['fav'], ['prev'], ['next']])
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


if __name__ == '__main__':
    unittest.main()
