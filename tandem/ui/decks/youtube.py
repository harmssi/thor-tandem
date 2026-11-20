"""YouTube on the Thor: mpv plays on the top screen, this deck (decks/media.py) browses and steers it on the bottom one.

Search, channel pages and the stream addresses come from yt-dlp (a single file in ~/.local/share/tandem-media, fetched
and kept current here), without a Google account: nothing in anybody's account is read or changed. What the player
remembers lives in ~/.config/tandem/media/youtube.json: watched positions (for "Weiterschauen"), saved channels (the
start page shows their newest videos) and the last searches. Video: H.264 up to 1080p, which the Thor's decoder plays
(hwdec v4l2m2m: about 5 % of one core against 30 % in software, measured 16.11.2026). Since late 2025 yt-dlp needs a
JavaScript runtime for YouTube (without one only low formats came, measured 18.11.2026: no 1080p): Deno, fetched beside it.

With the owner's own Google OAuth client (Einstellungen-Seite › YouTube; type "TV and Limited Input devices", scope
youtube.readonly) there are also "Abos", "Playlists" and "Mag ich": sign-in is Google's device way (google.com/device
and a code), the tokens stay in ~/.config/tandem/media/youtube-auth.json (0600). Abos read the subscription list once
(1 unit per 50 channels of the 10,000 a day) and then each channel's free RSS feed; playback stays without account.
"Downloads" (decks/offline.py) keeps videos on the card for watching without a network - for the owner's own use only:
YouTube's terms allow offline viewing only through YouTube's own apps.
"""
import json, os, platform, re, subprocess, threading, time, urllib.error, urllib.parse, urllib.request, uuid, zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from decks import media, offline
from decks.plex import write_private

DATA = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'tandem-media'
YTDLP = DATA / 'yt-dlp'
YTDLP_URL = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp'
STORE = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'tandem/media/youtube.json'
FORMAT = 'bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/bv*[height<=1080]+ba/b[height<=1080]/b'  # H.264: the Thor decodes it in hardware
OFFLINE_FORMAT = 'bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4][height<=1080]/b[height<=1080]'  # one mp4, H.264 + AAC
DENO = DATA / 'deno'
DENO_URL = 'https://github.com/denoland/deno/releases/latest/download/deno-{}-unknown-linux-gnu.zip'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'tandem/config.json'
AUTH = STORE.with_name('youtube-auth.json')
DEVICE_STATE = STORE.with_name('youtube-device.json')
PROFILE = STORE.with_name('yt-browser')  # Firefox profile of the sign-in on the Thor (tandem.py yt_login); its cookies are the account
COOKIES = STORE.with_name('youtube-cookies.txt')  # exported Netscape cookies.txt (from Thor browser login or remote.html import)
AUTH_COOKIES = ('SAPISID', '__Secure-1PAPISID', '__Secure-3PAPISID', 'SID', '__Secure-1PSID', '__Secure-3PSID')
SERVER = 'http://127.0.0.1:' + os.environ.get('TANDEM_PORT', '8377') + '/api/'
ACCOUNT_FEEDS = {'Abos': 'https://www.youtube.com/feed/subscriptions', 'Playlists': 'https://www.youtube.com/feed/playlists',
                 'Mag ich': 'https://www.youtube.com/playlist?list=LL'}
DEVICE_URL, TOKEN_URL, API = 'https://oauth2.googleapis.com/device/code', 'https://oauth2.googleapis.com/token', 'https://www.googleapis.com/youtube/v3/'
SCOPE = 'https://www.googleapis.com/auth/youtube.readonly'
TV_DEVICE_URL, TV_TOKEN_URL = 'https://www.youtube.com/o/oauth2/device/code', 'https://www.youtube.com/o/oauth2/token'
TV_SCOPE = 'http://gdata.youtube.com https://www.googleapis.com/auth/youtube-paid-content'
TV_UA = 'Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version'
TV_CLIENT_RX = re.compile(r'clientId:"([0-9]+-[0-9a-zA-Z_\-]+\.apps\.googleusercontent\.com)",\w+:"([0-9a-zA-Z_\-]{16,48})"')
INNERTUBE_BROWSE = 'https://www.youtube.com/youtubei/v1/browse?prettyPrint=false'
FEED = 'https://www.youtube.com/feeds/videos.xml?channel_id='
NS = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015', 'm': 'http://search.yahoo.com/mrss/'}
SUB_LANGS = ('de', 'en')
WATCH = 'https://www.youtube.com/watch?v='


def thumb(vid): return f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg'


def entry(e, channel=None):
    """A card from one of yt-dlp's flat entries (search, channel page); None for what is no single video."""
    vid = e.get('id')
    if not vid or len(vid) != 11 or e.get('ie_key', 'Youtube') != 'Youtube': return None  # playlists and channels in the results
    dur = e.get('duration')
    live = e.get('live_status') == 'is_live'
    name = e.get('channel') or e.get('uploader') or (channel or {}).get('name') or ''
    url = e.get('channel_url') or e.get('uploader_url') or (channel or {}).get('url')
    views = e.get('view_count')
    sub = ' · '.join(x for x in (name, media.count(views) + ' Aufrufe' if views else '') if x)
    return {'id': vid, 'title': e.get('title') or vid, 'sub': sub, 'thumb': thumb(vid), 'kind': 'video', 'dur': dur,
            'badge': 'LIVE' if live else media.clock(dur) if dur else '', 'channel': {'name': name, 'url': url} if url else None}


def channel_entry(e):
    """A folder card when search returns a YouTube channel itself (e.g. searching 'Toravo')."""
    if e.get('ie_key') not in ('YoutubeTab', 'YoutubeChannel'): return None
    url = e.get('channel_url') or e.get('url') or (f'https://www.youtube.com/channel/{e["id"]}' if str(e.get('id', '')).startswith('UC') else '')
    if not url or '/playlist' in url: return None
    name = e.get('channel') or e.get('title') or e.get('uploader') or ''
    if not name: return None
    thumbs = e.get('thumbnails') or []
    pic = next((t.get('url') for t in reversed(thumbs) if str(t.get('url', '')).startswith(('http', '//'))), None)
    if pic and pic.startswith('//'): pic = 'https:' + pic
    subs = e.get('channel_follower_count')
    sub = ' · '.join(x for x in ('Kanal', media.count(subs) + ' Abonnenten' if subs else '') if x)
    return {'id': url, 'title': name, 'sub': sub, 'thumb': pic, 'kind': 'folder', 'channel': {'name': name, 'url': url}}


def google_client():
    """(client id, secret) the owner entered on the settings page, or None."""
    try: c = json.loads(CONFIG.read_text())
    except (OSError, ValueError): return None
    return (c['yt_client_id'], c['yt_client_secret']) if c.get('yt_client_id') and c.get('yt_client_secret') else None


def _cookies_file_ok():
    cfile = PROFILE.with_name('youtube-cookies.txt')
    if not cfile.is_file(): return False
    try:
        for line in cfile.read_text(errors='replace').splitlines():
            parts = line.split('\t')
            if len(parts) >= 7 and 'youtube.com' in parts[0] and parts[5] in AUTH_COOKIES and parts[6].strip():
                return True
    except OSError: pass
    return False


def browser_signed_in():
    """True when youtube-cookies.txt or the Firefox profile (including live -wal) holds Google's YouTube session cookie."""
    if _cookies_file_ok(): return True
    db = PROFILE / 'cookies.sqlite'
    if not db.is_file(): return False
    import shutil, sqlite3, tempfile
    with tempfile.TemporaryDirectory(prefix='ytck-') as tmp:
        dst = Path(tmp) / 'cookies.sqlite'
        for suf in ('', '-wal', '-shm'):
            src = Path(str(db) + suf)
            if src.is_file():
                try: shutil.copy2(src, Path(str(dst) + suf))
                except OSError: pass
        try:
            with sqlite3.connect(str(dst)) as con:
                placeholders = ','.join('?' for _ in AUTH_COOKIES)
                return bool(con.execute(f"SELECT 1 FROM moz_cookies WHERE name IN ({placeholders}) AND (host LIKE '%youtube.com' OR host LIKE '%google.com') LIMIT 1", AUTH_COOKIES).fetchone())
        except sqlite3.Error: return False


def tell_server(action):
    req = urllib.request.Request(SERVER + 'ytlogin', data=json.dumps({'a': action}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r: got = json.loads(r.read())
    except (OSError, ValueError): return 'Tandem-Dienst nicht erreichbar.'
    return got.get('error') or ''


def sign_in():
    """Opens Google sign-in on the top screen, waits until it finishes (automatically on cookie detection or on „Fertig“), then reloads the tab."""
    problem = tell_server('start')
    if problem: return problem
    for _ in range(900):
        time.sleep(1.5)
        try:
            with urllib.request.urlopen(SERVER + 'state', timeout=5) as r: run = json.loads(r.read()).get('run') or {}
        except (OSError, ValueError): continue
        if not run.get('login'): break
    if browser_signed_in(): return {'reload_tab': True, 'say': 'Bei YouTube angemeldet.'}
    return 'Nicht angemeldet.'


def sign_in_page(note=''):
    """Account tabs without an account: sign in right here, Google's page on the top screen, keys on this one."""
    return {'title': 'Bei YouTube anmelden', 'items': [], 'buttons': [('Anmelden', sign_in)],
            'detail': {'title': 'Bei YouTube anmelden', 'meta': note or 'Abos, Playlists und „Mag ich“',
                       'summary': 'Oben öffnet sich Googles Anmeldeseite groß im Vollbild, unten eine Tastatur mit Schnell-Tasten (@, gmail.com, Tab, Weiter). '
                                  'Sobald du angemeldet bist, schließt sich das Browserfenster von selbst und lädt deine Abos. '
                                  'Alternativ kannst du am Handy/PC auf der Tandem-Einstellungsseite unter „Konten › YouTube“ deine Browser-Cookies einfügen.'}}


def post_form(url, fields, ua=None):
    headers = {'User-Agent': ua} if ua else {}
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read())
    except urllib.error.HTTPError as error:
        try: return json.loads(error.read())
        except ValueError: return {'error': f'http {error.code}'}
    except (OSError, ValueError): raise media.Problem('Google ist nicht erreichbar.')


def tv_signed_in():
    try: a = json.loads(AUTH.read_text())
    except (OSError, ValueError): return False
    return bool(a.get('tv') and (a.get('refresh') or a.get('until', 0) > time.time() + 60))


def yt_tv_client():
    """Discover YouTube's public TVHTML5 OAuth client parameters from youtube.com/tv at runtime and cache locally (0600)."""
    cfile = AUTH.with_name('youtube-tv-client.json')
    try:
        cached = json.loads(cfile.read_text())
        if cached.get('id') and cached.get('secret'): return cached['id'], cached['secret']
    except (OSError, ValueError): pass
    try:
        req = urllib.request.Request('https://www.youtube.com/tv', headers={'User-Agent': TV_UA})
        html = urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'replace')
        m = TV_CLIENT_RX.search(html)
        if not m:
            for s in re.findall(r'src="(/s/_/kabuki/[^"]+\.js)"', html)[:2]:
                js = urllib.request.urlopen(urllib.request.Request('https://www.youtube.com' + s, headers={'User-Agent': TV_UA}), timeout=12).read().decode('utf-8', 'replace')
                m = TV_CLIENT_RX.search(js)
                if m: break
        if m:
            write_private(cfile, {'id': m[1], 'secret': m[2]})
            return m[1], m[2]
    except OSError: pass
    raise media.Problem('Google ist nicht erreichbar.')


def device_flow(force_new=False):
    """Shared QR / device-code flow (YouTube TV client by default, or owner's custom client). Saves youtube-auth.json (0600) on approval."""
    custom = google_client()
    if tv_signed_in() and not custom: return {'signed_in': True}
    if custom:
        try:
            a = json.loads(AUTH.read_text())
            if not a.get('tv') and (a.get('refresh') or a.get('until', 0) > time.time() + 60): return {'signed_in': True}
        except (OSError, ValueError): pass
    cid, secret = custom or yt_tv_client()
    d = None
    if not force_new:
        try: d = json.loads(DEVICE_STATE.read_text())
        except (OSError, ValueError): d = None
    if d and time.time() < d.get('until', 0) and bool(d.get('custom')) == bool(custom):
        wait_s = max(4, int(d.get('interval', 5)) - 1)
        if time.time() - d.get('polled', 0) >= wait_s:
            d['polled'] = time.time()
            write_private(DEVICE_STATE, d)
            if custom:
                got = post_form(TOKEN_URL, {'client_id': cid, 'client_secret': secret, 'device_code': d['device_code'], 'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})
            else:
                got = post_form(TV_TOKEN_URL, {'client_id': cid, 'client_secret': secret, 'code': d['device_code'], 'grant_type': 'http://oauth.net/grant_type/device/1.0'}, TV_UA)
            if got.get('access_token'):
                write_private(AUTH, {'access': got['access_token'], 'refresh': got.get('refresh_token'),
                                     'until': time.time() + int(got.get('expires_in', 3600)), 'tv': not custom})
                DEVICE_STATE.unlink(missing_ok=True)
                return {'signed_in': True}
            if got.get('error') in ('invalid_client', 'unauthorized_client') and not custom:
                AUTH.with_name('youtube-tv-client.json').unlink(missing_ok=True)
            if got.get('error') not in ('authorization_pending', 'slow_down', None):
                DEVICE_STATE.unlink(missing_ok=True)
                d = None
        if d:
            return {'signed_in': False, 'code': d['code'], 'link': d['link'], 'qr': d['qr'], 'poll': max(5, int(d.get('interval', 5)))}
    if custom:
        got = post_form(DEVICE_URL, {'client_id': cid, 'scope': SCOPE})
    else:
        got = post_form(TV_DEVICE_URL, {'client_id': cid, 'scope': TV_SCOPE, 'device_id': str(uuid.uuid4()), 'device_model': 'ytlr::'}, TV_UA)
        if not got.get('user_code'):
            AUTH.with_name('youtube-tv-client.json').unlink(missing_ok=True)
    if not got.get('user_code'):
        raise media.Problem('Google lehnt den Client ab – in der Cloud Console den Typ „TV und Geräte mit begrenzter Eingabe“ wählen.' if custom else 'Google ist nicht erreichbar.')
    code = got['user_code']
    qr_url = f'https://www.youtube.com/activate?user_code={urllib.parse.quote(code)}'
    link = 'youtube.com/activate'
    d = {'device_code': got['device_code'], 'code': code, 'link': link, 'qr': qr_url,
         'until': time.time() + int(got.get('expires_in', 1800)), 'interval': int(got.get('interval', 5)), 'polled': time.time(), 'custom': bool(custom)}
    write_private(DEVICE_STATE, d)
    return {'signed_in': False, 'code': code, 'link': link, 'qr': qr_url, 'poll': max(5, d['interval'])}


def _yt_txt(obj):
    if not isinstance(obj, dict): return ''
    return obj.get('simpleText') or ''.join(r.get('text', '') for r in obj.get('runs') or [])


def _clock_secs(badge):
    parts = [int(x) for x in badge.split(':')] if re.fullmatch(r'\d+(?::\d\d){1,2}', badge or '') else []
    return sum(v * (60 ** i) for i, v in enumerate(reversed(parts))) if parts else None


def tv_tile_to_card(tile, want='video'):
    """Convert one TVHTML5 tileRenderer into a Tandem video or playlist card."""
    meta = (tile.get('metadata') or {}).get('tileMetadataRenderer') or {}
    head = (tile.get('header') or {}).get('tileHeaderRenderer') or {}
    cmd = tile.get('onSelectCommand') or {}
    title = _yt_txt(meta.get('title')).strip()
    thumbs = ((head.get('thumbnail') or {}).get('thumbnails')) or []
    pic = thumbs[-1].get('url') if thumbs else None
    if pic and pic.startswith('//'): pic = 'https:' + pic
    ov = next((o['thumbnailOverlayTimeStatusRenderer'] for o in (head.get('thumbnailOverlays') or []) if 'thumbnailOverlayTimeStatusRenderer' in o), {})
    badge = _yt_txt(ov.get('text')).replace('\xa0', ' ').strip()
    is_live = ov.get('style') == 'LIVE' or badge.upper() == 'LIVE'
    if want == 'playlist':
        bid = (cmd.get('browseEndpoint') or {}).get('browseId') or ''
        pid = (cmd.get('watchPlaylistEndpoint') or {}).get('playlistId') or (bid[2:] if bid.startswith('VL') else '')
        if not pid and not bid.startswith('VL'): return None
        tv_bid = bid if bid.startswith('VL') else 'VL' + pid
        return {'id': pid or tv_bid, 'title': title or '?', 'sub': badge or 'Playlist', 'kind': 'folder', 'thumb': pic, 'tv_playlist': tv_bid}
    vid = (cmd.get('watchEndpoint') or {}).get('videoId')
    if not vid or len(vid) != 11: return None
    lines = meta.get('lines') or []
    ch_name, ch_url, views = '', None, ''
    if lines:
        for item in ((lines[0].get('lineRenderer') or {}).get('items') or []):
            li = item.get('lineItemRenderer') or {}
            runs = (li.get('text') or {}).get('runs') or []
            if runs and not ch_name:
                ch_name = ''.join(r.get('text', '') for r in runs).strip()
                cid = (((runs[0].get('navigationEndpoint') or {}).get('browseEndpoint')) or {}).get('browseId') or ''
                if cid.startswith('UC'): ch_url = f'https://www.youtube.com/channel/{cid}'
            elif not ch_name:
                ch_name = _yt_txt(li.get('text')).strip()
    for line in lines[1:]:
        for item in ((line.get('lineRenderer') or {}).get('items') or []):
            t = _yt_txt((item.get('lineItemRenderer') or {}).get('text')).replace('\xa0', ' ').strip()
            if any(w in t for w in ('Aufruf', 'view', 'Zuschauer')):
                views = t; break
    dur = None if is_live else _clock_secs(badge)
    sub = ' · '.join(x for x in (ch_name, views) if x)
    return {'id': vid, 'title': title or vid, 'sub': sub, 'thumb': thumb(vid), 'kind': 'video', 'dur': dur,
            'badge': 'LIVE' if is_live else badge, 'channel': {'name': ch_name, 'url': ch_url} if ch_url else None}


def iso_secs(text):
    """'PT1H2M3S' -> 3723."""
    m = re.fullmatch(r'P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', text or '')
    return sum(int(v or 0) * k for v, k in zip(m.groups(), (86400, 3600, 60, 1))) if m else None


def api_card(vid, sn, dur=None):
    ch = sn.get('videoOwnerChannelTitle') or sn.get('channelTitle') or ''
    cid = sn.get('videoOwnerChannelId') or sn.get('channelId')
    return {'id': vid, 'title': sn.get('title') or vid, 'sub': ch, 'thumb': thumb(vid), 'kind': 'video', 'dur': dur, 'badge': media.clock(dur) if dur else '',
            'channel': {'name': ch, 'url': f'https://www.youtube.com/channel/{cid}'} if cid else None}


def feed(cid):
    """The newest uploads of one channel from its RSS feed (no API units)."""
    with urllib.request.urlopen(FEED + urllib.parse.quote(cid), timeout=10) as r: root = ET.fromstring(r.read())
    out = []
    for e in root.findall('a:entry', NS):
        vid, name = e.findtext('yt:videoId', '', NS), e.findtext('a:author/a:name', '', NS)
        if len(vid) != 11 or '/shorts/' in (e.find('a:link', NS).get('href', '') if e.find('a:link', NS) is not None else ''): continue
        out.append({'id': vid, 'title': e.findtext('a:title', vid, NS), 'sub': name, 'thumb': thumb(vid), 'kind': 'video', 'badge': '',
                    'channel': {'name': name, 'url': f'https://www.youtube.com/channel/{cid}'}, 'published': e.findtext('a:published', '', NS)})
    return out


def subtitles(info):
    """[(url, title, lang)]: the uploader's own subtitles in German and English, else YouTube's automatic ones (as WebVTT)."""
    out = []
    for lang in SUB_LANGS:
        for kind, label in (('subtitles', ''), ('automatic_captions', ' (automatisch)')):
            vtt = next((f['url'] for f in (info.get(kind) or {}).get(lang, []) if f.get('ext') == 'vtt'), None)
            if vtt:
                out.append((vtt, media.LANG_NAMES.get(lang, lang) + label, lang))
                break
    return out


def stream(info):
    """(video url, separate audio url or None) of the format yt-dlp chose."""
    parts = info.get('requested_formats') or [info]
    video = next((f['url'] for f in parts if f.get('vcodec') != 'none'), parts[0].get('url'))
    audio = next((f['url'] for f in parts if f.get('vcodec') == 'none' and f.get('url') != video), None)
    return video, audio


class YouTube:
    name, accent, offline_app = 'YouTube', '#ff0033', 'youtube'
    search_title = 'YouTube durchsuchen'

    @property
    def tabs(self):
        return ('Start', 'Suche', 'Kanäle', 'Abos', 'Playlists', 'Mag ich', 'Verlauf', 'Downloads')  # the account tabs sign in on the Thor itself (19.11.)

    def __init__(self):
        self.lock, self.cache, self.saved_at, self.device = threading.Lock(), {}, 0.0, None
        try: self.data = json.loads(STORE.read_text())
        except (OSError, ValueError): self.data = {}
        try: self.auth = json.loads(AUTH.read_text())
        except (OSError, ValueError): self.auth = {}
        for key, empty in (('history', {}), ('channels', []), ('searches', [])): self.data.setdefault(key, empty)
        threading.Thread(target=self.keep_ytdlp, daemon=True).start()

    # ---- yt-dlp ---------------------------------------------------------------------------------------------------------
    def keep_ytdlp(self):
        """Fetch yt-dlp (and Deno, its JavaScript runtime) if missing; update yt-dlp when older than two days (YouTube changes often)."""
        try:
            if not DENO.is_file():
                DATA.mkdir(parents=True, exist_ok=True)
                arch = 'aarch64' if platform.machine() in ('aarch64', 'arm64') else 'x86_64'
                tmp = DATA / 'deno.zip'
                with urllib.request.urlopen(DENO_URL.format(arch), timeout=120) as r: tmp.write_bytes(r.read())
                with zipfile.ZipFile(tmp) as z: z.extract('deno', DATA / 'deno.part')
                (DATA / 'deno.part/deno').chmod(0o755); os.replace(DATA / 'deno.part/deno', DENO)
                tmp.unlink(); (DATA / 'deno.part').rmdir()
        except (OSError, zipfile.BadZipFile, KeyError): pass
        try:
            if not YTDLP.is_file():
                DATA.mkdir(parents=True, exist_ok=True)
                tmp = YTDLP.with_suffix('.part')
                with urllib.request.urlopen(YTDLP_URL, timeout=60) as r: tmp.write_bytes(r.read())
                tmp.chmod(0o755); os.replace(tmp, YTDLP)
            elif time.time() - YTDLP.stat().st_mtime > 2 * 86400:
                subprocess.run([str(YTDLP), '-U'], capture_output=True, timeout=120)
                subprocess.run(['flatpak', 'update', '--user', '-y', '--noninteractive', 'io.mpv.Mpv'], capture_output=True, timeout=600)  # mpv's own yt-dlp plays the videos
                os.utime(YTDLP)  # also when it was current: not again for two days
        except (OSError, subprocess.SubprocessError): pass

    def ytdlp(self, *args, timeout=45):
        for _ in range(60):  # the first start fetches it
            if YTDLP.is_file(): break
            time.sleep(1)
        try: out = subprocess.run([str(YTDLP), '--no-warnings', *self.js(), *args], capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError: raise media.Problem('yt-dlp fehlt noch (Internet?).')
        except subprocess.TimeoutExpired: raise media.Problem('YouTube antwortet nicht.')
        if out.returncode:
            line = (out.stderr.strip().splitlines() or ['unbekannter Fehler'])[-1]
            raise media.Problem(line.removeprefix('ERROR: ')[:160])
        return json.loads(out.stdout)

    def js(self): return ['--js-runtimes', f'deno:{DENO}'] if DENO.is_file() else []

    def flat(self, source, n=24, channel=None):
        info = self.ytdlp('--flat-playlist', '-J', '--playlist-end', str(n), source)
        return [c for c in (entry(e, channel) for e in info.get('entries') or []) if c]

    def channel_videos(self, ch, n=24):
        key = (ch['url'], n)
        hit = self.cache.get(key)
        if hit and time.time() - hit[0] < 1800: return hit[1]
        videos = self.flat(ch['url'].rstrip('/') + '/videos', n, ch)
        self.cache[key] = (time.time(), videos)
        return videos

    # ---- pages ----------------------------------------------------------------------------------------------------------
    def history(self, unfinished=False):
        rows = sorted(self.data['history'].values(), key=lambda h: -h.get('t', 0))
        if unfinished: rows = [h for h in rows if media.resumable(h.get('pos'), h.get('dur'))]
        return [{**h['item'], 'progress': (h.get('pos') or 0) / h['dur'] if h.get('dur') else None} for h in rows if h.get('item')]

    def page(self, tab):
        if tab == 'Start':
            items = []
            going = self.history(True)[:6]
            if going: items += [media.header('Weiterschauen')] + going
            channels = self.data['channels'][:8]
            with ThreadPoolExecutor(4) as pool:
                found = list(pool.map(lambda ch: self.try_videos(ch, 6), channels))
            for ch, videos in zip(channels, found):
                if videos: items += [media.header('Neu von ' + ch['name'])] + videos
            if self.tv_token() and not google_client():
                try:
                    subs = self.tv_feed('Abos')[:9]
                    if subs: items += [media.header('Neu in deinen Abos')] + subs
                except media.Problem: pass
            elif browser_signed_in() and not google_client():
                try:
                    subs = [c for c in (entry(e) for e in self.account(ACCOUNT_FEEDS['Abos'], 12)) if c][:9]
                    if subs: items += [media.header('Neu in deinen Abos')] + subs
                except media.Problem: pass
            elif self.token():
                try:
                    subs = self.subscriptions()[:9]
                    if subs: items += [media.header('Neu in deinen Abos')] + subs
                except media.Problem: pass
            note = '' if items else 'Oben auf „Suche“ tippen oder unter „Abos“ anmelden. Gemerkte Kanäle zeigen hier ihre neuen Videos.'
            return {'title': 'Start', 'items': items, 'note': note}
        if tab == 'Suche':
            return {'title': 'Suche', 'search': True, 'chips': self.data['searches'][:8], 'items': [], 'note': 'Tippe ins Suchfeld oder auf eine frühere Suche.'}
        if tab == 'Kanäle':
            items = [{'id': ch['url'], 'title': ch['name'], 'sub': 'Kanal', 'thumb': ch.get('thumb'), 'kind': 'folder', 'channel': ch} for ch in self.data['channels']]
            return {'title': 'Kanäle', 'items': items, 'note': '' if items else 'Noch keine Kanäle gemerkt: beim Abspielen in „Läuft“ auf „Kanal merken“ tippen.'}
        if tab == 'Verlauf':
            items = self.history()[:60]
            return {'title': 'Verlauf', 'items': items, 'note': '' if items else 'Hier erscheinen die Videos, die du angesehen hast.'}
        if tab == 'Downloads': return media.offline_page('youtube', 'Videos, die du beim Abspielen unter „Läuft“ herunterlädst, gehen hier auch ohne Internet – im Flugzeug.')
        if tab in ('Abos', 'Playlists', 'Mag ich') and not google_client(): return self.account_page(tab)
        if tab in ('Abos', 'Playlists', 'Mag ich'):
            gate = self.signed_in()
            if gate: return gate
            if tab == 'Abos': items = self.subscriptions()
            elif tab == 'Playlists':
                lists = self.api('playlists', part='snippet,contentDetails', mine='true', maxResults=50).get('items') or []
                items = [{'id': pl['id'], 'title': pl['snippet'].get('title') or '?', 'sub': f'{pl.get("contentDetails", {}).get("itemCount", 0)} Videos', 'kind': 'folder',
                          'thumb': ((pl['snippet'].get('thumbnails') or {}).get('high') or {}).get('url'), 'playlist': pl['id']} for pl in lists]
            else:
                liked = self.api('videos', part='snippet,contentDetails', myRating='like', maxResults=50).get('items') or []
                items = [api_card(v['id'], v['snippet'], iso_secs((v.get('contentDetails') or {}).get('duration'))) for v in liked]
            empty = {'Abos': 'Keine neuen Videos deiner Abos.', 'Playlists': 'Du hast noch keine Playlists.', 'Mag ich': 'Noch keine Videos mit „Mag ich“.'}[tab]
            items = list(items) + [{'id': 'logout', 'title': 'Abmelden', 'sub': 'YouTube-Konto vom Thor entfernen', 'kind': 'folder', 'logout': True}]
            return {'title': tab, 'items': items, 'note': '' if len(items) > 1 else empty}

    def cookie_args(self):
        cfile = PROFILE.with_name('youtube-cookies.txt')
        return ['--cookies', str(cfile)] if _cookies_file_ok() else ['--cookies-from-browser', f'firefox:{PROFILE}']

    def account(self, source, n=60):
        """A feed of the signed-in account through youtube-cookies.txt or the sign-in profile's cookies (cached for ten minutes)."""
        hit = self.cache.get(('acct', source))
        if hit and time.time() - hit[0] < 600: return hit[1]
        info = self.ytdlp(*self.cookie_args(), '--flat-playlist', '-J', '--playlist-end', str(n), source, timeout=90)
        self.cache[('acct', source)] = (time.time(), info.get('entries') or [])
        return self.cache[('acct', source)][1]

    def qr_page(self, force_new=False):
        st = device_flow(force_new=force_new)
        if st.get('signed_in'): return None
        return {'title': 'Bei YouTube anmelden', 'code': st['code'], 'link': st['link'], 'qr': st['qr'], 'poll': st['poll'], 'items': [],
                'new_code': lambda: self.qr_page(True),
                'note': 'QR-Code mit dem Handy scannen (der Code ist schon vorausgefüllt) – oder youtube.com/activate öffnen und diesen Code eingeben.'}

    def tv_feed(self, tab):
        hit = self.cache.get(('tv', tab))
        if hit and time.time() - hit[0] < 300: return hit[1]
        if tab == 'Abos':
            items = self.tv_browse('FEsubscriptions', want='video', pages=2)
        elif tab == 'Playlists':
            items = self.tv_browse('FEplaylist_aggregation', want='playlist', pages=1)
            if not items: items = self.tv_browse('FElibrary', want='playlist', pages=1)
        else:
            items = self.tv_browse('VLLL', want='video', pages=1, allow_empty=True)
        self.cache[('tv', tab)] = (time.time(), items)
        return items

    def account_page(self, tab):
        empty = {'Abos': 'Keine neuen Videos deiner Abos.', 'Playlists': 'Du hast noch keine Playlists.', 'Mag ich': 'Noch keine Videos mit „Mag ich“.'}[tab]
        if self.tv_token():
            items = list(self.tv_feed(tab))
            items.append({'id': 'logout', 'title': 'Abmelden', 'sub': 'YouTube-Konto vom Thor entfernen', 'kind': 'folder', 'logout': True})
            return {'title': tab, 'items': items, 'note': '' if len(items) > 1 else empty}
        if not browser_signed_in():
            gate = self.qr_page()
            if gate: return gate
            return self.account_page(tab)
        try: entries = self.account(ACCOUNT_FEEDS[tab])
        except media.Problem: return self.qr_page(True)
        if tab == 'Playlists':
            items = [{'id': e['id'], 'title': e.get('title') or '?', 'sub': 'Playlist', 'kind': 'folder', 'thumb': ((e.get('thumbnails') or [{}])[-1]).get('url'),
                      'feed': e.get('url') or 'https://www.youtube.com/playlist?list=' + e['id']} for e in entries if e.get('id')]
        else: items = [c for c in (entry(e) for e in entries) if c]
        items.append({'id': 'logout', 'title': 'Abmelden', 'sub': 'YouTube-Konto vom Thor entfernen', 'kind': 'folder', 'logout': True})
        return {'title': tab, 'items': items, 'note': '' if len(items) > 1 else empty}

    def try_videos(self, ch, n):
        try: return self.channel_videos(ch, n)
        except media.Problem: return []

    def open(self, item):
        if item.get('logout'):
            AUTH.unlink(missing_ok=True); DEVICE_STATE.unlink(missing_ok=True)
            with self.lock: self.auth = {}
            tell_server('logout')
            self.cache = {k: v for k, v in self.cache.items() if k[0] not in ('acct', 'tv', 'subs', 'subfeed')}
            return self.qr_page(True)
        if item.get('tv_playlist'):
            items = self.tv_browse(item['tv_playlist'], want='video', pages=2, allow_empty=True)
            return {'title': item['title'], 'items': items, 'note': '' if items else 'Die Playlist ist leer.'}
        if item.get('feed'):
            items = [c for c in (entry(e) for e in self.account(item['feed'], 100)) if c]
            return {'title': item['title'], 'items': items, 'note': '' if items else 'Die Playlist ist leer.'}
        if item.get('playlist'):
            got = self.api('playlistItems', part='snippet', playlistId=item['playlist'], maxResults=50).get('items') or []
            items = [api_card(v['snippet']['resourceId']['videoId'], v['snippet']) for v in got
                     if (v.get('snippet') or {}).get('resourceId', {}).get('videoId') and v['snippet'].get('title') not in ('Private video', 'Deleted video')]
            return {'title': item['title'], 'items': items, 'note': '' if items else 'Die Playlist ist leer.'}
        ch = item['channel']
        videos = self.channel_videos(ch, 30)
        known = any(c['url'] == ch['url'] for c in self.data.get('channels', ()))
        sample = videos[0] if videos else item
        return {'title': ch['name'], 'items': videos,
                'head_action': ('Kanal vergessen' if known else 'Kanal merken', lambda: self.keep_channel(ch, sample, not known))}

    def search(self, query):
        with self.lock:
            self.data['searches'] = [query] + [s for s in self.data['searches'] if s.lower() != query.lower()][:11]
            self.save()
        info = self.ytdlp('--flat-playlist', '-J', '--playlist-end', '24', f'ytsearch24:{query}')
        raw = info.get('entries') or []
        channels = [c for c in (channel_entry(e) for e in raw) if c]
        videos = [c for c in (entry(e) for e in raw) if c]
        items = channels[:3] + videos
        return {'title': f'„{query}“', 'search': True, 'query': query, 'items': items, 'note': '' if items else 'Nichts gefunden.'}

    # ---- Google account -------------------------------------------------------------------------------------------------
    def save_auth(self): write_private(AUTH, self.auth)

    def sync_auth(self):
        try: mtime = AUTH.stat().st_mtime
        except OSError:
            if self.auth: self.auth = {}
            return
        if getattr(self, 'auth_mtime', 0) != mtime:
            try: self.auth = json.loads(AUTH.read_text()); self.auth_mtime = mtime
            except (OSError, ValueError): self.auth = {}

    def tv_token(self):
        self.sync_auth()
        a = self.auth
        if not a.get('tv'): return None
        if a.get('access') and a.get('until', 0) > time.time() + 60: return a['access']
        if a.get('refresh'):
            cid, secret = yt_tv_client()
            got = post_form(TV_TOKEN_URL, {'client_id': cid, 'client_secret': secret, 'refresh_token': a['refresh'], 'grant_type': 'refresh_token'}, TV_UA)
            if got.get('access_token'):
                with self.lock:
                    a.update(access=got['access_token'], until=time.time() + int(got.get('expires_in', 3600)))
                    self.save_auth()
                    try: self.auth_mtime = AUTH.stat().st_mtime
                    except OSError: pass
                return a['access']
            if got.get('error') in ('unauthorized_client', 'invalid_client'):
                AUTH.with_name('youtube-tv-client.json').unlink(missing_ok=True)
            if got.get('error') in ('invalid_grant', 'unauthorized_client', 'invalid_client'):
                with self.lock: self.auth = {}; AUTH.unlink(missing_ok=True)
        return None

    def tv_browse(self, browse_id, want='video', pages=1, allow_empty=False):
        token = self.tv_token()
        if not token: raise media.Problem('Nicht bei Google angemeldet.')
        out, seen, cont = [], set(), None
        ctx = {'client': {'clientName': 'TVHTML5', 'clientVersion': '7.20250312.16.00', 'hl': 'de', 'gl': 'DE'}}
        for step in range(pages):
            body = {'context': ctx, **({'continuation': cont} if cont else {'browseId': browse_id})}
            req = urllib.request.Request(INNERTUBE_BROWSE, data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token, 'User-Agent': TV_UA}, method='POST')
            try:
                with urllib.request.urlopen(req, timeout=15) as r: data = json.loads(r.read())
            except urllib.error.HTTPError as error:
                if error.code == 401:
                    with self.lock: self.auth.pop('access', None); self.save_auth()
                    raise media.Problem('Google-Anmeldung abgelaufen – Tab erneut öffnen.')
                if error.code == 404 and allow_empty: return out
                raise media.Problem(f'YouTube-API: Fehler {error.code}.')
            except (OSError, ValueError): raise media.Problem('YouTube ist nicht erreichbar.')
            tiles, conts = [], []
            def walk(x):
                if isinstance(x, dict):
                    if 'tileRenderer' in x: tiles.append(x['tileRenderer'])
                    elif 'nextContinuationData' in x and isinstance(x['nextContinuationData'], dict):
                        c = x['nextContinuationData'].get('continuation')
                        if c: conts.append(c)
                    else:
                        for v in x.values(): walk(v)
                elif isinstance(x, list):
                    for v in x: walk(v)
            walk(data)
            for tr in tiles:
                card = tv_tile_to_card(tr, want=want)
                if card and card['id'] not in seen:
                    seen.add(card['id']); out.append(card)
            cont = conts[0] if conts else None
            if not cont or len(out) >= 60: break
        return out

    def token(self):
        self.sync_auth()
        a, client = self.auth, google_client()
        if not client or a.get('tv'): return None
        if a.get('access') and a.get('until', 0) > time.time() + 60: return a['access']
        if a.get('refresh'):
            got = post_form(TOKEN_URL, {'client_id': client[0], 'client_secret': client[1], 'refresh_token': a['refresh'], 'grant_type': 'refresh_token'})
            if got.get('access_token'):
                with self.lock: a.update(access=got['access_token'], until=time.time() + int(got.get('expires_in', 3600))); self.save_auth()
                return a['access']
            if got.get('error') in ('invalid_grant', 'unauthorized_client', 'invalid_client'):
                with self.lock: self.auth = {}; self.save_auth()
        return None

    def signed_in(self):
        """None when signed in to Google, else the QR + code page (asked again every few seconds)."""
        if self.token(): return None
        return self.qr_page()

    def api(self, path, **params):
        token = self.token()
        if not token: raise media.Problem('Nicht bei Google angemeldet.')
        req = urllib.request.Request(API + path + '?' + urllib.parse.urlencode(params), headers={'Authorization': 'Bearer ' + token})
        try:
            with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read())
        except urllib.error.HTTPError as error:
            if error.code == 401:
                with self.lock: self.auth.pop('access', None)
                raise media.Problem('Google-Anmeldung abgelaufen – Tab erneut öffnen.')
            raise media.Problem('YouTube-API: Tageskontingent erschöpft oder API nicht freigeschaltet.' if error.code == 403 else f'YouTube-API: Fehler {error.code}.')
        except (OSError, ValueError): raise media.Problem('YouTube ist nicht erreichbar.')

    def subscriptions(self):
        """Newest uploads of the subscribed channels: the list once every six hours, then each channel's feed (15 min)."""
        subs = self.cache.get('subs')
        if not subs or time.time() - subs[0] > 6 * 3600:
            ids, page = [], None
            for _ in range(4):  # up to 200 channels, 4 units
                got = self.api('subscriptions', part='snippet', mine='true', maxResults=50, order='relevance', **({'pageToken': page} if page else {}))
                ids += [s['snippet']['resourceId']['channelId'] for s in got.get('items') or [] if s.get('snippet', {}).get('resourceId', {}).get('channelId')]
                page = got.get('nextPageToken')
                if not page: break
            subs = self.cache['subs'] = (time.time(), ids)
        hit = self.cache.get('subfeed')
        if hit and time.time() - hit[0] < 900: return hit[1]
        def one(cid):
            try: return feed(cid)[:6]
            except (OSError, ET.ParseError): return []
        with ThreadPoolExecutor(8) as pool: found = [v for vs in pool.map(one, subs[1][:60]) for v in vs]
        found.sort(key=lambda v: v.get('published', ''), reverse=True)
        self.cache['subfeed'] = (time.time(), found[:60])
        return found[:60]

    # ---- offline ----------------------------------------------------------------------------------------------------------
    def fetch(self, job, base, progress):
        """One download for decks/offline.py: mp4 (H.264 + AAC, up to 1080p) and what the card shows, with yt-dlp."""
        url = WATCH + job['id']
        info = self.ytdlp('-J', '--no-playlist', '-f', OFFLINE_FORMAT, url, timeout=60)
        size = info.get('filesize') or info.get('filesize_approx') or sum((f.get('filesize') or f.get('filesize_approx') or 0) for f in info.get('requested_formats') or [])
        progress(0, size)
        cmd = [str(YTDLP), '--no-warnings', *self.js(), '--no-playlist', '--continue', '--newline', '-f', OFFLINE_FORMAT, '--merge-output-format', 'mp4',
               '--progress-template', 'download:%(progress._percent_str)s', '-o', f'{base}.%(ext)s', url]
        run = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        parts = max(1, len(info.get('requested_formats') or [1]))
        done = 0
        try:
            for line in run.stdout:
                m = re.search(r'([\d.]+)%', line)
                if m:
                    pct = float(m[1])
                    if pct >= 100: done += 1
                    progress(min(99, (min(done, parts - 1) * 100 + pct) / parts))
        except offline.Full:
            run.kill(); raise
        if run.wait():
            raise media.Problem('Herunterladen fehlgeschlagen.')
        try:
            with urllib.request.urlopen(thumb(job['id']), timeout=15) as r: picture = r.read()
        except OSError: picture = None
        ch = {'name': info.get('channel') or info.get('uploader') or '', 'url': info.get('channel_url')}
        return {'file': base.name + '.mp4', 'thumb_bytes': picture,
                'meta': {'title': info.get('title') or job['item'].get('title'), 'sub': ch['name'], 'channel': ch, 'dur': info.get('duration'),
                         'description': (info.get('description') or '')[:4000], 'upload_date': info.get('upload_date')}}

    # ---- playing --------------------------------------------------------------------------------------------------------
    def resolve(self, item):
        local = offline.find('youtube', item['id'])
        if local:
            meta, file = local
            start = meta.get('pos') if media.resumable(meta.get('pos'), meta.get('dur')) else None
            return {'url': str(file), 'opts': {'start': start, 'force_media_title': meta.get('title') or item['title']}, 'subs': []}
        if item.get('queued'): raise media.Problem('Lädt noch herunter.')
        info = self.ytdlp('-J', '--no-playlist', '-f', FORMAT, WATCH + item['id'])
        if not item.get('channel') and info.get('channel_url'): item['channel'] = {'name': info.get('channel') or '', 'url': info['channel_url']}
        item.setdefault('dur', info.get('duration'))
        seen = self.data['history'].get(item['id'], {})
        start = seen.get('pos') if media.resumable(seen.get('pos'), seen.get('dur') or info.get('duration')) else None
        video, audio = stream(info)
        parts = info.get('requested_formats') or [info]
        ua = next(((f.get('http_headers') or {}).get('User-Agent') for f in parts if f.get('http_headers')), None)
        if video and ua:  # pass yt-dlp's own User-Agent + Referer so googlevideo serves 1080p directly without a 2nd yt-dlp run in mpv
            opts = {'start': start, 'force_media_title': info.get('title') or item['title'], 'user_agent': ua, 'referrer': 'https://www.youtube.com/'}
            if audio: opts['audio_file'] = audio
            return {'url': video, 'opts': opts, 'subs': subtitles(info)}
        return {'url': WATCH + item['id'], 'opts': {'start': start, 'force_media_title': info.get('title') or item['title']}, 'subs': subtitles(info)}

    def progress(self, item, pos, dur, state):
        if pos is None: return
        if offline.find('youtube', item['id']): offline.update('youtube', item['id'], pos=pos)
        with self.lock:
            keep = {k: item.get(k) for k in ('id', 'title', 'sub', 'thumb', 'kind', 'dur', 'badge', 'channel')}
            self.data['history'][item['id']] = {'item': keep, 'pos': pos, 'dur': dur or item.get('dur'), 't': time.time()}
            if len(self.data['history']) > 200:  # the oldest go
                for vid in sorted(self.data['history'], key=lambda v: self.data['history'][v].get('t', 0))[:-200]: del self.data['history'][vid]
            if state != 'playing' or time.time() - self.saved_at > 30: self.save()

    def actions(self, item):
        acts = media.offline_actions('youtube', item)
        ch = item.get('channel')
        if not ch or not ch.get('url'): return acts
        known = any(c['url'] == ch['url'] for c in self.data['channels'])
        return [('Kanal vergessen' if known else 'Kanal merken', lambda: self.keep_channel(ch, item, not known)),
                ('Zum Kanal', lambda: {'open_channel': ch})] + acts

    def keep_channel(self, ch, item, keep):
        with self.lock:
            self.data['channels'] = [c for c in self.data['channels'] if c['url'] != ch['url']]
            if keep: self.data['channels'].insert(0, {'name': ch['name'], 'url': ch['url'], 'thumb': item.get('thumb')})
            self.save()
        return f'„{ch["name"]}“ ' + ('gemerkt.' if keep else 'vergessen.')

    def headers(self, url): return {}

    def save(self):
        self.saved_at = time.time()
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STORE.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.data, ensure_ascii=False))
            os.replace(tmp, STORE)
        except OSError: pass


class Deck(media.Deck):
    def __init__(self, window): super().__init__(window, YouTube())
