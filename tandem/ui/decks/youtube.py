"""YouTube on the Thor: mpv plays on the top screen, this deck (decks/media.py) browses and steers it on the bottom one.

Search, channel pages and the stream addresses come from yt-dlp (a single file in ~/.local/share/tandem-media, fetched
and kept current here), without a Google account: nothing in anybody's account is read or changed. What the player
remembers lives in ~/.config/tandem/media/youtube.json: watched positions (for "Weiterschauen"), saved channels (the
start page shows their newest videos) and the last searches. Video: H.264 up to 1080p, which the Thor's decoder plays
(hwdec v4l2m2m: about 5 % of one core against 30 % in software, measured 16.11.2026).
"""
import json, os, subprocess, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from decks import media

DATA = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'tandem-media'
YTDLP = DATA / 'yt-dlp'
YTDLP_URL = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp'
STORE = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'tandem/media/youtube.json'
FORMAT = 'bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/bv*[height<=1080]+ba/b[height<=1080]/b'  # H.264: the Thor decodes it in hardware
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
    name, accent, tabs = 'YouTube', '#ff0033', ('Start', 'Suche', 'Kanäle', 'Verlauf')
    search_title = 'YouTube durchsuchen'

    def __init__(self):
        self.lock, self.cache, self.saved_at = threading.Lock(), {}, 0.0
        try: self.data = json.loads(STORE.read_text())
        except (OSError, ValueError): self.data = {}
        for key, empty in (('history', {}), ('channels', []), ('searches', [])): self.data.setdefault(key, empty)
        threading.Thread(target=self.keep_ytdlp, daemon=True).start()

    # ---- yt-dlp ---------------------------------------------------------------------------------------------------------
    def keep_ytdlp(self):
        """Fetch yt-dlp if it is missing; update it when it is older than two days (YouTube changes often)."""
        try:
            if not YTDLP.is_file():
                DATA.mkdir(parents=True, exist_ok=True)
                tmp = YTDLP.with_suffix('.part')
                with urllib.request.urlopen(YTDLP_URL, timeout=60) as r: tmp.write_bytes(r.read())
                tmp.chmod(0o755); os.replace(tmp, YTDLP)
            elif time.time() - YTDLP.stat().st_mtime > 2 * 86400:
                subprocess.run([str(YTDLP), '-U'], capture_output=True, timeout=120)
                os.utime(YTDLP)  # also when it was current: not again for two days
        except (OSError, subprocess.SubprocessError): pass

    def ytdlp(self, *args, timeout=45):
        for _ in range(60):  # the first start fetches it
            if YTDLP.is_file(): break
            time.sleep(1)
        try: out = subprocess.run([str(YTDLP), '--no-warnings', *args], capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError: raise media.Problem('yt-dlp fehlt noch (Internet?).')
        except subprocess.TimeoutExpired: raise media.Problem('YouTube antwortet nicht.')
        if out.returncode:
            line = (out.stderr.strip().splitlines() or ['unbekannter Fehler'])[-1]
            raise media.Problem(line.removeprefix('ERROR: ')[:160])
        return json.loads(out.stdout)

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
            note = '' if items else 'Oben auf „Suche“ tippen. Kanäle, die du dir in „Läuft“ merkst, zeigen hier ihre neuen Videos.'
            return {'title': 'Start', 'items': items, 'note': note}
        if tab == 'Suche':
            return {'title': 'Suche', 'search': True, 'chips': self.data['searches'][:8], 'items': [], 'note': 'Tippe ins Suchfeld oder auf eine frühere Suche.'}
        if tab == 'Kanäle':
            items = [{'id': ch['url'], 'title': ch['name'], 'sub': 'Kanal', 'thumb': ch.get('thumb'), 'kind': 'folder', 'channel': ch} for ch in self.data['channels']]
            return {'title': 'Kanäle', 'items': items, 'note': '' if items else 'Noch keine Kanäle gemerkt: beim Abspielen in „Läuft“ auf „Kanal merken“ tippen.'}
        if tab == 'Verlauf':
            items = self.history()[:60]
            return {'title': 'Verlauf', 'items': items, 'note': '' if items else 'Hier erscheinen die Videos, die du angesehen hast.'}

    def try_videos(self, ch, n):
        try: return self.channel_videos(ch, n)
        except media.Problem: return []

    def open(self, item):
        ch = item['channel']
        return {'title': ch['name'], 'items': self.channel_videos(ch, 30)}

    def search(self, query):
        with self.lock:
            self.data['searches'] = [query] + [s for s in self.data['searches'] if s.lower() != query.lower()][:11]
            self.save()
        items = self.flat(f'ytsearch24:{query}', 24)
        return {'title': f'„{query}“', 'search': True, 'query': query, 'items': items, 'note': '' if items else 'Nichts gefunden.'}

    # ---- playing --------------------------------------------------------------------------------------------------------
    def resolve(self, item):
        info = self.ytdlp('-J', '--no-playlist', '-f', FORMAT, WATCH + item['id'])
        video, audio = stream(info)
        if not item.get('channel') and info.get('channel_url'): item['channel'] = {'name': info.get('channel') or '', 'url': info['channel_url']}
        item.setdefault('dur', info.get('duration'))
        seen = self.data['history'].get(item['id'], {})
        start = seen.get('pos') if media.resumable(seen.get('pos'), seen.get('dur') or info.get('duration')) else None
        return {'url': video, 'opts': {'audio_file': audio, 'start': start, 'force_media_title': info.get('title') or item['title']}, 'subs': subtitles(info)}

    def progress(self, item, pos, dur, state):
        if pos is None: return
        with self.lock:
            keep = {k: item.get(k) for k in ('id', 'title', 'sub', 'thumb', 'kind', 'dur', 'badge', 'channel')}
            self.data['history'][item['id']] = {'item': keep, 'pos': pos, 'dur': dur or item.get('dur'), 't': time.time()}
            if len(self.data['history']) > 200:  # the oldest go
                for vid in sorted(self.data['history'], key=lambda v: self.data['history'][v].get('t', 0))[:-200]: del self.data['history'][vid]
            if state != 'playing' or time.time() - self.saved_at > 30: self.save()

    def actions(self, item):
        ch = item.get('channel')
        if not ch or not ch.get('url'): return []
        known = any(c['url'] == ch['url'] for c in self.data['channels'])
        return [('Kanal vergessen' if known else 'Kanal merken', lambda: self.keep_channel(ch, item, not known))]

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
