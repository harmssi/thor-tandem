"""Self-check for the media apps (decks/media.py, youtube.py, plex.py, mpv.py): python3 ui/test_media.py.
Plex runs against a stand-in for plex.tv and a Plex server, mpv against a stand-in socket; nothing goes on the network.
Needs PySide6 (skipped without it); paints the deck offscreen (TANDEM_UI_SHOTS=folder saves the pictures)."""
import atexit, json, os, shutil, socket, stat, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
TMP = Path(tempfile.mkdtemp(prefix='tandem-media-'))
atexit.register(shutil.rmtree, TMP, True)
os.environ['XDG_CONFIG_HOME'] = str(TMP / 'config')
os.environ['XDG_DATA_HOME'] = str(TMP / 'data')
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtGui import QFontDatabase, QGuiApplication, QImage, QPainter
    from decks import media, mpv, offline, plex, youtube
    offline.root = lambda: TMP / 'card'  # never the real SD card
except ImportError: media = None
SHOTS = os.environ.get('TANDEM_UI_SHOTS')
TOKEN = 'secret-token-123'


class FakePlex(BaseHTTPRequestHandler):
    """plex.tv (pins, resources) and one Plex server in one; remembers the timeline reports."""
    linked, timeline, seen_tokens = False, [], []

    def log_message(self, *a): pass

    def reply(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.startswith('/api/v2/pins'): return self.reply({'id': 7, 'code': 'AB12'})
        self.reply({}, 404)

    def do_GET(self):
        path, _, query = self.path.partition('?')
        token = self.headers.get('X-Plex-Token')
        if token: FakePlex.seen_tokens.append(self.path)
        if path == '/api/v2/pins/7': return self.reply({'id': 7, 'authToken': TOKEN if FakePlex.linked else None})
        if path == '/api/v2/resources':
            base = f'http://127.0.0.1:{self.server.server_port}'
            return self.reply([{'name': 'Heim', 'provides': 'server', 'owned': True, 'accessToken': TOKEN, 'clientIdentifier': 'x',
                                'connections': [{'uri': 'http://192.0.2.1:9', 'local': False, 'relay': True}, {'uri': base, 'local': True, 'address': '127.0.0.1', 'port': self.server.server_port}]}])
        if path == '/identity': return self.reply({'MediaContainer': {'machineIdentifier': 'x'}})
        if token != TOKEN: return self.reply({}, 401)
        ep = {'type': 'episode', 'ratingKey': '11', 'key': '/library/metadata/11', 'grandparentTitle': 'Serie', 'title': 'Pilot', 'parentIndex': 1, 'index': 1, 'duration': 1200000, 'viewOffset': 300000, 'thumb': '/t/11'}
        pages = {'/library/onDeck': {'Metadata': [ep]},
                 '/library/recentlyAdded': {'Metadata': [{'type': 'movie', 'ratingKey': '20', 'title': 'Film', 'year': 2024, 'duration': 6000000, 'viewCount': 1, 'art': '/a/20'}]},
                 '/library/sections': {'Directory': [{'key': '1', 'title': 'Filme', 'type': 'movie'}, {'key': '2', 'title': 'Fotos', 'type': 'photo'}]},
                 '/library/metadata/30/children': {'Metadata': [{'type': 'season', 'ratingKey': '31', 'key': '/library/metadata/31/children', 'parentTitle': 'Serie', 'title': 'Staffel 1'}]},
                 '/library/metadata/31/children': {'Metadata': [ep, {**ep, 'ratingKey': '12', 'index': 2, 'title': 'Zwei', 'viewOffset': 0}]},
                 '/library/metadata/11': {'Metadata': [{**ep, 'Media': [{'Part': [{'key': '/library/parts/5/file.mkv', 'Stream': [{'streamType': 3, 'key': '/library/streams/9', 'displayTitle': 'Deutsch (SRT)', 'languageCode': 'ger'}, {'streamType': 3, 'displayTitle': 'Englisch'}]}]}]}]},
                 '/hubs/search': {'Hub': [{'title': 'Filme', 'Metadata': [{'type': 'movie', 'ratingKey': '20', 'title': 'Film'}]}, {'title': 'Leer', 'Metadata': []}]},
                 '/hubs/promoted': {'Hub': [{'title': 'Weiterschauen', 'hubIdentifier': 'home.continue', 'Metadata': [ep]},
                                            {'title': 'Auf Deck', 'hubIdentifier': 'home.ondeck', 'Metadata': [ep]},  # the same again: left out
                                            {'title': 'Zuletzt hinzugefügt', 'hubIdentifier': 'movie.recentlyadded.1', 'Metadata': [{'type': 'movie', 'ratingKey': '20', 'title': 'Film', 'year': 2024, 'duration': 6000000, 'viewCount': 1, 'art': '/a/20'}]}]},
                 '/library/metadata/20': {'Metadata': [{'type': 'movie', 'ratingKey': '20', 'title': 'Film', 'year': 2024, 'duration': 6000000, 'audienceRating': 8.1, 'summary': 'Ein Film.',
                                                        'art': '/a/20', 'Media': [{'Part': [{'key': '/library/parts/6/film.mp4', 'container': 'mp4', 'size': 3000}]}]}]},
                 '/:/timeline': {}, '/:/scrobble': {}, '/:/unscrobble': {}}
        if path == '/library/parts/6/film.mp4':
            body, start = b'x' * 3000, int((self.headers.get('Range') or 'bytes=0-')[6:].split('-')[0])
            self.send_response(206 if start else 200); self.send_header('Content-Length', str(3000 - start)); self.end_headers()
            return self.wfile.write(body[start:])
        if path in ('/:/timeline', '/:/scrobble', '/:/unscrobble'): FakePlex.timeline.append(path + '?' + query)
        if path in pages: return self.reply({'MediaContainer': pages[path]})
        self.reply({}, 404)


class FakeMpv:
    """A socket that answers like mpv: records commands, sends a property and file-loaded after loadfile."""
    def __init__(self, path):
        self.commands, self.srv = [], socket.socket(socket.AF_UNIX)
        self.srv.bind(path); self.srv.listen(1)
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        conn, _ = self.srv.accept()
        buf = b''
        while True:
            chunk = conn.recv(65536)
            if not chunk: return
            *lines, buf = (buf + chunk).split(b'\n')
            for line in lines:
                cmd = json.loads(line)['command']
                self.commands.append(cmd)
                if cmd[0] == 'loadfile':
                    for m in ({'event': 'property-change', 'name': 'duration', 'data': 1200.0}, {'event': 'property-change', 'name': 'time-pos', 'data': 300.0},
                              {'event': 'property-change', 'name': 'track-list', 'data': [{'id': 1, 'type': 'audio', 'lang': 'ger', 'selected': True}, {'id': 2, 'type': 'audio', 'lang': 'eng', 'title': 'Original'},
                                                                                          {'id': 1, 'type': 'sub', 'lang': 'ger', 'title': 'Deutsch (SRT)'}]},
                              {'event': 'property-change', 'name': 'pause', 'data': False}, {'event': 'file-loaded'}):
                        conn.sendall(json.dumps(m).encode() + b'\n')


if media:
    class Window(QObject):
        """What a deck uses of the Tandem window, enough to paint offscreen (the real one is checked in test_ui.py)."""
        loaded = Signal()

        def __init__(self, run):
            super().__init__()
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import tandem_ui as ui
            self.ui, self.RUN, self.memo, self.SET, self.u, self.me = ui, run, {}, {'vol': 40}, 12.4, 'test'
            self.off, self.maxoff, self.hits, self.scrolls, self.clip, self.xf, self.zoom, self.fonts = {}, {}, [], [], None, None, 1.0, {}
            self.posted, self.asked, self.OSD, self.timers = [], [], None, {'osd': type('T', (), {'start': lambda s, ms: None})()}
            self.PROMPT = None

        def width(self): return 1240
        def height(self): return 1080
        def post(self, path, data=None, then=None): self.posted.append((path, data))
        def ask(self, title, secret, done): self.asked.append(done)
        def update(self): pass
        def set_value(self, key, x, left, width): self.SET[key] = round(100 * (x - left) / width)
        def __getattr__(self, name):  # the drawing helpers of the real window
            fn = getattr(self.ui.Tandem, name)
            return lambda *a, **k: fn(self, *a, **k)


@unittest.skipIf(media is None, 'PySide6 fehlt')
class MediaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(__file__).resolve().parent / 'fonts').glob('*.ttf'): QFontDatabase.addApplicationFont(str(font))
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FakePlex)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        plex.PLEX_TV = f'http://127.0.0.1:{cls.server.server_port}'

    def spin(self, test, secs=5):
        end = time.time() + secs
        while time.time() < end:
            self.app.processEvents()
            if test(): return
            time.sleep(.02)
        self.fail('timed out')

    def test_helpers(self):
        items = [media.header('A'), *({'kind': 'video'} for _ in range(4)), media.header('B'), {'kind': 'video'}]
        cells = media.grid(items)
        self.assertEqual(cells, [(1, 0, 0), (2, 0, 1), (3, 0, 2), (4, 1, 0), (6, 2, 0)])
        self.assertEqual([media.move(cells, 2, a) for a in ('left', 'right', 'down', 'up')], [1, 3, 4, 2])
        self.assertEqual((media.move(cells, 4, 'down'), media.move(cells, 6, 'up'), media.move([], 0, 'up')), (6, 4, None))
        self.assertEqual([media.clock(s) for s in (5, 75, 3725, None)], ['0:05', '1:15', '1:02:05', ''])
        self.assertEqual([media.count(n) for n in (950, 56000, 1000000, 1234567, 2.5e9)], ['950', '56 Tsd.', '1 Mio.', '1,2 Mio.', '2,5 Mrd.'])
        self.assertEqual([media.resumable(p, d) for p in (10, 300, 590) for d in (600,)], [False, True, False])
        eps = [{'type': 'episode', 'n': n} for n in range(3)]
        self.assertEqual((media.up_next(eps, 0), media.up_next([{'type': 'movie'}] + eps, 0)), (eps[1:], []))
        self.assertEqual(mpv.options({'start': 12, 'audio-file': 'http://a/b?x=1,2', 'skip': None}), 'start=%2%12,audio-file=%16%http://a/b?x=1,2')
        tl = [{'type': 'audio', 'id': 1, 'lang': 'eng', 'title': 'videoplayback?expire=1&a=b', 'selected': True}, {'type': 'sub', 'id': 2, 'lang': 'ger', 'title': 'Forced'}, {'type': 'sub', 'id': 3}]
        self.assertEqual((mpv.tracks(tl, 'audio'), mpv.tracks(tl, 'sub')), ([(1, 'Englisch', True)], [(2, 'Forced (Deutsch)', False), (3, 'Spur 3', False)]))

    def test_youtube_sign_in_on_thor(self):  # QR device-code sign-in (phone/PC) + TV InnerTube tile parsing + cookie fallback
        import sqlite3
        yt = youtube.YouTube.__new__(youtube.YouTube)
        yt.lock, yt.cache, yt.auth = threading.Lock(), {}, {}
        old_post, old_client = youtube.post_form, youtube.yt_tv_client
        calls = []
        def fake_post(url, fields, ua=None):
            calls.append((url, fields))
            if 'device/code' in url:
                return {'device_code': 'dev-1', 'user_code': 'ABCD-EFGH', 'expires_in': 1800, 'interval': 5}
            return {'access_token': 'tok-123', 'refresh_token': 'ref-456', 'expires_in': 3600}
        youtube.post_form = fake_post
        youtube.yt_tv_client = lambda: ('test-tv-id', 'test-tv-secret')
        try:
            page = yt.account_page('Abos')
            self.assertEqual((page['code'], page['link'], page['qr']), ('ABCD-EFGH', 'youtube.com/activate', 'https://www.youtube.com/activate?user_code=ABCD-EFGH'))
            # Simulate poll interval elapsed -> approves token and writes 0600 youtube-auth.json
            d = json.loads(youtube.DEVICE_STATE.read_text()); d['polled'] = 0; youtube.DEVICE_STATE.write_text(json.dumps(d))
            yt.cache[('tv', 'Abos')] = (time.time(), [{'id': 'v1234567890', 'title': 'Abo-Video'}])
            got_tv = yt.account_page('Abos')
            self.assertEqual([i['id'] for i in got_tv['items']], ['v1234567890', 'logout'])
            self.assertTrue(youtube.tv_signed_in())
            # Also verify TVHTML5 tileRenderer parser (video + playlist)
            vtile = {'header': {'tileHeaderRenderer': {'thumbnailOverlays': [{'thumbnailOverlayTimeStatusRenderer': {'text': {'simpleText': '12:34'}}}]}},
                     'metadata': {'tileMetadataRenderer': {'title': {'simpleText': 'Clip'}, 'lines': [
                         {'lineRenderer': {'items': [{'lineItemRenderer': {'text': {'runs': [{'text': 'Toravo', 'navigationEndpoint': {'browseEndpoint': {'browseId': 'UC123'}}}]}}}]}},
                         {'lineRenderer': {'items': [{'lineItemRenderer': {'text': {'simpleText': '10 Tsd. Aufrufe'}}}]}}]}},
                     'onSelectCommand': {'watchEndpoint': {'videoId': '12345678901'}}}
            vcard = youtube.tv_tile_to_card(vtile, 'video')
            self.assertEqual((vcard['id'], vcard['dur'], vcard['sub'], vcard['channel']['url']), ('12345678901', 754, 'Toravo · 10 Tsd. Aufrufe', 'https://www.youtube.com/channel/UC123'))
            ptile = {'header': {'tileHeaderRenderer': {'thumbnail': {'thumbnails': [{'url': 'https://t/p.jpg'}]}, 'thumbnailOverlays': [{'thumbnailOverlayTimeStatusRenderer': {'text': {'runs': [{'text': '8'}, {'text': ' Videos'}]}}}] }},
                     'metadata': {'tileMetadataRenderer': {'title': {'simpleText': 'Mix'}}},
                     'onSelectCommand': {'browseEndpoint': {'browseId': 'VLPL99'}}}
            pcard = youtube.tv_tile_to_card(ptile, 'playlist')
            self.assertEqual((pcard['id'], pcard['tv_playlist'], pcard['sub']), ('PL99', 'VLPL99', '8 Videos'))
            youtube.AUTH.unlink(missing_ok=True); yt.auth = {}
        finally:
            youtube.post_form, youtube.yt_tv_client = old_post, old_client
        youtube.PROFILE.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(youtube.PROFILE / 'cookies.sqlite') as con:
            con.execute('CREATE TABLE moz_cookies (name TEXT, host TEXT, value TEXT)')
            con.execute("INSERT INTO moz_cookies VALUES ('SAPISID', '.youtube.com', 'x')")
        self.assertTrue(youtube.browser_signed_in())
        yt.cache[('acct', youtube.ACCOUNT_FEEDS['Abos'])] = (time.time(), [{'id': 'abcdefghijk', 'title': 'T'}])
        got = yt.account_page('Abos')
        self.assertEqual([i['id'] for i in got['items']], ['abcdefghijk', 'logout'])

    def test_youtube_parsing(self):
        e = {'id': 'abcdefghijk', 'title': 'T', 'duration': 75, 'channel': 'K', 'channel_url': 'https://y/c', 'view_count': 56000}
        self.assertEqual(youtube.entry(e), {'id': 'abcdefghijk', 'title': 'T', 'sub': 'K · 56 Tsd. Aufrufe', 'thumb': 'https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg', 'kind': 'video',
                                            'dur': 75, 'badge': '1:15', 'channel': {'name': 'K', 'url': 'https://y/c'}})
        self.assertEqual([youtube.entry({'id': 'UCxyz', 'ie_key': 'YoutubeTab'}), youtube.entry({'id': 'abcdefghijk', 'live_status': 'is_live'})['badge']], [None, 'LIVE'])
        info = {'subtitles': {'en': [{'ext': 'json3', 'url': 'j'}, {'ext': 'vtt', 'url': 'e'}]}, 'automatic_captions': {'de': [{'ext': 'vtt', 'url': 'a'}], 'en': [{'ext': 'vtt', 'url': 'x'}]},
                'requested_formats': [{'vcodec': 'avc1', 'url': 'v'}, {'vcodec': 'none', 'url': 'au'}]}
        self.assertEqual(youtube.subtitles(info), [('a', 'Deutsch (automatisch)', 'de'), ('e', 'Englisch', 'en')])
        self.assertEqual((youtube.stream(info), youtube.stream({'url': 'b'})), (('v', 'au'), ('b', None)))
        yt = youtube.YouTube.__new__(youtube.YouTube)
        yt.lock, yt.cache, yt.saved_at, yt.data = threading.Lock(), {}, 0, {'history': {}, 'channels': [], 'searches': []}
        it = youtube.entry(e)
        yt.progress(it, 40, 75, 'paused')
        self.assertEqual(yt.history(True)[0]['progress'], 40 / 75)
        self.assertEqual(json.loads(youtube.STORE.read_text())['history']['abcdefghijk']['pos'], 40)
        label, fn = yt.actions(it)[0]
        self.assertEqual((label, fn(), yt.actions(it)[0][0]), ('Kanal merken', '„K“ gemerkt.', 'Kanal vergessen'))
        self.assertEqual((yt.actions(it)[1][0], yt.actions(it)[1][1]()['open_channel']['url']), ('Zum Kanal', 'https://y/c'))
        self.assertEqual(yt.page('Kanäle')['items'][0]['channel']['url'], 'https://y/c')
        ch = youtube.channel_entry({'ie_key': 'YoutubeChannel', 'channel': 'Toravo', 'channel_url': 'https://www.youtube.com/@Toravo', 'channel_follower_count': 4200, 'thumbnails': [{'url': '//yt3.ggpht.com/a.jpg'}]})
        self.assertEqual((ch['kind'], ch['title'], ch['sub'], ch['thumb']), ('folder', 'Toravo', 'Kanal · 4200 Abonnenten', 'https://yt3.ggpht.com/a.jpg'))
        yt.ytdlp = lambda *a: {'url': None, 'requested_formats': [{'vcodec': 'avc1', 'url': 'https://v', 'http_headers': {'User-Agent': 'UA/1'}}, {'vcodec': 'none', 'url': 'https://a'}]}
        res = yt.resolve({'id': 'abcdefghijk', 'title': 'T'})
        self.assertEqual((res['url'], res['opts']['audio_file'], res['opts']['user_agent'], res['opts']['referrer']), ('https://v', 'https://a', 'UA/1', 'https://www.youtube.com/'))

    def test_plex(self):
        FakePlex.linked, FakePlex.timeline[:] = False, []
        p = plex.Plex(TMP / 'plex.json')
        page = p.page('Start')
        self.assertEqual((page['code'], page['poll']), ('AB12', 3))
        self.assertEqual(p.page('Start')['code'], 'AB12')  # not linked yet: the same code again
        FakePlex.linked = True
        start = p.page('Start')
        self.assertEqual([it['title'] if it['kind'] == 'header' else (it['title'], it['sub'], it['progress'], it['watched']) for it in start['items']],
                         ['Weiterschauen', ('Serie', 'S1 E1 · Pilot', .25, False), 'Zuletzt hinzugefügt', ('Film', '2024', None, True)])
        self.assertEqual(p.data['server']['uri'], f'http://127.0.0.1:{self.server.server_port}')  # the relay that does not answer is skipped
        self.assertEqual(stat.S_IMODE(os.stat(TMP / 'plex.json').st_mode), 0o600)
        self.assertNotIn(TOKEN, start['items'][1]['thumb'] + p.thumb(start['items'][1]['thumb'], 300, 200))  # the token goes in a header
        self.assertEqual(p.headers(start['items'][1]['thumb']), {'X-Plex-Token': TOKEN})
        libs = p.page('Bibliotheken')['items']
        self.assertEqual([(i['title'], i['sub']) for i in libs], [('Filme', 'Filme')])  # photos are left out
        episodes = p.open({'type': 'show', 'id': '30', 'key': '/library/metadata/30/children', 'title': 'Serie'})  # one season: straight to its episodes
        self.assertEqual([e['sub'] for e in episodes['items']], ['S1 E1 · Pilot', 'S1 E2 · Zwei'])
        found = p.search('Film')
        self.assertEqual([i['title'] for i in found['items']], ['Filme', 'Film'])
        got = p.resolve(dict(start['items'][1]))
        self.assertEqual((got['url'].endswith('/library/parts/5/file.mkv'), got['opts']['start'], [s[1:] for s in got['subs']]), (True, 300.0, [('Deutsch (SRT)', 'ger')]))
        self.assertNotIn(TOKEN, got['url'] + ''.join(s[0] for s in got['subs']))
        p.progress({'id': '11', 'dur': 1200}, 310.5, 1200, 'paused')
        self.assertIn('state=paused&time=310500&duration=1200000', FakePlex.timeline[-1])
        p.progress({'id': '11', 'dur': 1200}, 1100, 1200, 'playing')  # past 90 %: watched
        self.assertTrue(FakePlex.timeline[-1].startswith('/:/scrobble?') and 'key=11' in FakePlex.timeline[-1])
        film = p.detail({'id': '20', 'title': 'Film'})
        self.assertEqual((film['detail']['meta'], [b[0] for b in film['buttons']]), ('2024 · 100 Min. · ★ 8,1', ['Abspielen', 'Als gesehen markieren', 'Herunterladen']))
        # a download: the original file onto the "card", resumed after a break; then it plays from there without the server
        part = TMP / 'card/plex/20.mp4.part'
        part.parent.mkdir(parents=True, exist_ok=True); part.write_bytes(b'x' * 1000)
        shown = []
        got = p.fetch({'id': '20', 'item': {'id': '20', 'title': 'Film'}}, TMP / 'card/plex/20', lambda pct, size=None: shown.append(pct))
        self.assertEqual((got['file'], (TMP / 'card/plex/20.mp4').stat().st_size, round(shown[0]), shown[-1]), ('20.mp4', 3000, 33, 100))
        offline._write(TMP / 'card/plex/20.json', {'id': '20', **got['meta'], 'file': got['file']})
        self.assertEqual(p.resolve({'id': '20', 'title': 'Film'})['url'], str(TMP / 'card/plex/20.mp4'))
        p.progress({'id': '20', 'dur': 6000}, 5900, 6000, 'stopped')
        self.assertTrue(offline.find('plex', '20')[0]['watched'])
        self.assertEqual([i['title'] for i in p.page('Downloads')['items']], ['Film'])
        self.assertEqual(p.detail({'id': '20', 'title': 'Film'})['buttons'][-1][0], 'Download löschen')
        offline.delete('plex', '20')
        self.assertFalse(list((TMP / 'card/plex').iterdir()))
        self.assertFalse([t for t in FakePlex.seen_tokens if TOKEN in t])  # never in an address
        again = plex.Plex(TMP / 'plex.json')
        self.assertEqual(again.data['token'], TOKEN)

    def test_deck(self):
        sock = str(TMP / 'mpv.sock')
        fake = FakeMpv(sock)

        class Source(youtube.YouTube):
            def __init__(self): self.lock, self.cache, self.saved_at, self.data = threading.Lock(), {}, 0, {'history': {}, 'channels': [], 'searches': ['lofi']}
            def page(self, tab): return super().page(tab) if tab == 'Suche' else {'title': tab, 'items': [media.header('Neu'), *({'id': str(n), 'title': f'Video {n}', 'sub': 'Kanal', 'kind': 'video', 'badge': '3:00', 'type': 'episode'} for n in range(5))]}
            def resolve(self, item): return {'url': 'http://v/' + item['id'], 'opts': {'start': 30, 'force_media_title': item['title']}, 'subs': [('http://s/de.vtt', 'Deutsch', 'de')]}
            def search(self, text): return {'title': text, 'search': True, 'query': text, 'items': self.page('x')['items'][1:3]}

        w = Window({'id': 'app7', 's': 'app', 'port': {'deck': 'youtube', 'socket': sock, 'pad': True}})
        deck = media.Deck(w, Source())
        img = QImage(1240, 1080, QImage.Format.Format_RGB32)

        def paint(name):
            w.hits = []; w.scrolls = []
            p = QPainter(img); deck.paint(p); p.end()
            if SHOTS: img.save(str(Path(SHOTS) / f'media-{name}.png'))
            return [h[3] for h in w.hits]

        self.spin(lambda: deck.page()['items'] and deck.mpv.sock)
        names = paint('start')
        self.assertIn('card:Video 0', names); self.assertIn('tab:Suche', names); self.assertNotIn('tab:Läuft', names)
        deck.key('right'); deck.key('down')
        self.assertEqual(deck.focus[id(deck.page())], 4)  # the first key puts the focus on the first card, then one down
        deck.key('fav')
        self.assertEqual([q['title'] for q in deck.queue], ['Video 3'])
        deck.key('ok')  # plays Video 3, the episodes after it come next
        self.spin(lambda: any(c[0] == 'loadfile' for c in fake.commands) and not deck.busy)
        load = next(c for c in fake.commands if c[0] == 'loadfile')
        self.assertEqual((load[1], load[2], load[4]), ('http://v/3', 'replace', 'start=%2%30,force-media-title=%7%Video 3'))
        self.spin(lambda: any(c[0] == 'sub-add' for c in fake.commands))
        self.assertEqual([q['title'] for q in deck.queue], ['Video 4'])
        self.spin(lambda: deck.mpv.props.get('track-list'))
        names = paint('playing')
        self.assertIn('Tonspur:Original (Englisch)', names); self.assertIn('Untertitel:Deutsch (SRT)', names); self.assertIn('Tempo:1,5×', names)
        deck.key('left'); deck.key('ok'); deck.key('up')
        self.spin(lambda: [c for c in fake.commands if c[0] == 'cycle'])
        self.assertEqual([c[:3] for c in fake.commands if c[0] in ('seek', 'cycle')][-2:], [['seek', -10, 'relative'], ['cycle', 'pause']])
        self.assertEqual(w.posted[-1], ('api/set', {'key': 'vol', 'value': 45, 'from': 'test'}))
        deck.key('back')
        names = paint('start-mini')
        self.assertIn('mini:pause', names); self.assertIn('tab:Warteschlange', names)
        deck.open_tab('Suche'); self.spin(lambda: not deck.page().get('loading'))
        self.assertIn('chip:lofi', paint('search'))
        deck.key('up'); w.asked[-1]('katzen')
        self.spin(lambda: deck.page().get('query') == 'katzen' and deck.page()['items'])
        self.assertIn('card:Video 1', paint('results'))
        deck.close()


if __name__ == '__main__':
    unittest.main()
