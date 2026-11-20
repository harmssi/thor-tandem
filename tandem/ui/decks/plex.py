"""Plex on the Thor: mpv plays on the top screen, this deck (decks/media.py) browses the player's own Plex server.

Sign-in is Plex's PIN way (plex.tv/link): the deck asks plex.tv for a code, shows it, and once the code was entered on
plex.tv/link with the owner's account, plex.tv hands out a token. Which server, and how to reach it, comes from plex.tv
(the account's resources; the first connection that answers wins, the local ones first) - nothing about the server is
written into this file. Token and server are kept in ~/.config/tandem/media/plex.json, readable only by the user; the
token travels in a header (X-Plex-Token), never in an address, so it shows up in no log.
Files play as they are (Direct Play: the Thor decodes H.264/HEVC/VP9 in hardware); where playback stands goes back to
the server (/:/timeline) every ten seconds and on pause and stop, so "Weiterschauen" is right on every Plex app; at
90 % the item counts as watched (/:/scrobble). Start shows the server's own home hubs (/hubs/promoted), a film or an
episode opens a detail page first (backdrop, year, length, rating, summary; play, resume, from the start, watched,
download); an intro marker shows "Intro überspringen" while it runs.
Downloads (decks/offline.py) take the original file (/library/parts/…?download=1, resumable with Range); what is watched
offline is kept beside the file and goes to the server (timeline, scrobble) as soon as it answers again.
"""
import json, os, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from pathlib import Path

from decks import media, offline

PLEX_TV = 'https://plex.tv'
STORE = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'tandem/media/plex.json'
try: LANG = 'en' if json.loads((STORE.parent.parent / 'config.json').read_text()).get('lang') == 'en' else 'de'  # the hub titles come from the server
except (OSError, ValueError): LANG = 'de'
PLAYABLE = {'movie', 'episode', 'clip', 'track'}
OPENS = {'show', 'season', 'artist', 'album', 'collection', 'playlist'}


def write_private(path, data):
    """JSON into a file only its user can read (0600 from the start, not chmod'ed afterwards)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f: json.dump(data, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def card(m, server=''):
    """A card from one of Plex's Metadata entries."""
    kind = m.get('type')
    dur = (m.get('duration') or 0) / 1000 or None
    offset = (m.get('viewOffset') or 0) / 1000
    if kind == 'episode':
        title = m.get('grandparentTitle') or m.get('title')
        sub = ' · '.join(x for x in (f'S{m.get("parentIndex", "?")} E{m.get("index", "?")}', m.get('title')) if x)
        art = m.get('thumb') or m.get('grandparentArt')
    elif kind == 'season':
        title, sub, art = m.get('parentTitle') or m.get('title'), m.get('title'), m.get('art') or m.get('parentArt') or m.get('thumb')
    elif kind == 'track':
        title, sub, art = m.get('title'), ' · '.join(x for x in (m.get('grandparentTitle'), m.get('parentTitle')) if x), m.get('parentThumb') or m.get('thumb')
    else:
        title = m.get('title') or '?'
        sub = ' · '.join(str(x) for x in (m.get('year'), m.get('studio') or (f'{m.get("leafCount")} Folgen' if m.get('leafCount') else None)) if x)
        art = m.get('art') or m.get('thumb')  # the wide background suits the cards better than the poster
    watched = bool(m.get('viewCount')) and not offset if kind in PLAYABLE else m.get('viewedLeafCount') == m.get('leafCount') and bool(m.get('leafCount'))
    return {'id': str(m.get('ratingKey') or m.get('key')), 'title': title, 'sub': sub, 'thumb': art and server + art, 'kind': 'video' if kind in PLAYABLE else 'folder',
            'type': kind, 'key': m.get('key'), 'dur': dur, 'progress': offset / dur if offset and dur else None, 'watched': watched,
            'badge': media.clock(dur) if dur and kind in PLAYABLE else ''}


def pick_connections(resource):
    """The addresses to try, best first: local before remote, relays last; for a local one also plain http (a router
    that blocks *.plex.direct names still lets the address through)."""
    order = sorted(resource.get('connections') or [], key=lambda c: (bool(c.get('relay')), not c.get('local')))
    out = []
    for c in order:
        if c.get('uri'): out.append(c['uri'])
        if c.get('local') and c.get('address') and c.get('port'): out.append(f'http://{c["address"]}:{c["port"]}')
    return list(dict.fromkeys(out))


class Plex:
    name, accent, tabs, offline_app = 'Plex', '#e5a00d', ('Start', 'Bibliotheken', 'Suche', 'Downloads'), 'plex'
    LIB = 'com.plexapp.plugins.library'
    search_title = 'Plex durchsuchen'

    def __init__(self, store=STORE):
        self.store, self.pin, self.lock = store, None, threading.Lock()
        try: self.data = json.loads(store.read_text())
        except (OSError, ValueError): self.data = {}
        if not self.data.get('client'): self.data['client'] = uuid.uuid4().hex; self.save()

    def save(self): write_private(self.store, self.data)

    def head(self, token=None):
        h = {'Accept': 'application/json', 'X-Plex-Product': 'Toravo Tandem', 'X-Plex-Version': '1.0', 'X-Plex-Client-Identifier': self.data['client'],
             'X-Plex-Platform': 'Linux', 'X-Plex-Device': 'AYN Thor', 'X-Plex-Device-Name': 'Thor (Tandem)', 'X-Plex-Provides': 'player', 'X-Plex-Language': LANG}
        if token: h['X-Plex-Token'] = token
        return h

    def call(self, url, token=None, method='GET', params=None, timeout=12):
        if params: url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method=method, headers=self.head(token), data=b'' if method == 'POST' else None)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as error:
            if error.code == 401: raise media.Problem('Plex lässt die Anmeldung nicht mehr zu.', 401)
            raise media.Problem(f'Plex antwortet mit Fehler {error.code}.')
        except (OSError, ValueError) as error: raise media.Problem(f'Plex nicht erreichbar ({getattr(error, "reason", error)}).')
        return json.loads(body) if body.strip() else {}

    def pms(self, path, **params):
        s = self.data['server']
        return self.call(s['uri'] + path, s['token'], params=params).get('MediaContainer', {})

    # ---- sign-in and finding the server --------------------------------------------------------------------------------
    def login_page(self):
        """The page with the code; asked for again every few seconds until plex.tv has the token."""
        if self.pin and time.time() < self.pin['until']:
            got = self.call(f'{PLEX_TV}/api/v2/pins/{self.pin["id"]}')
            if got.get('authToken'):
                with self.lock:
                    self.data['token'], self.pin = got['authToken'], None
                    self.data.pop('server', None)
                    self.save()
                return None
        else:
            got = self.call(f'{PLEX_TV}/api/v2/pins', method='POST')  # a short code for plex.tv/link
            self.pin = {'id': got['id'], 'code': got['code'], 'until': time.time() + 14 * 60}
        return {'title': 'Mit Plex verbinden', 'code': self.pin['code'], 'poll': 3, 'items': [],
                'note': 'Am Handy oder PC plex.tv/link öffnen, mit deinem Plex-Konto anmelden und diesen Code eingeben.'}

    def find_server(self):
        found = self.call(f'{PLEX_TV}/api/v2/resources', self.data['token'], params={'includeHttps': 1, 'includeRelay': 1})
        servers = sorted((r for r in found if 'server' in (r.get('provides') or '')), key=lambda r: not r.get('owned'))
        for r in servers:
            for uri in pick_connections(r):
                try:
                    self.call(uri + '/identity', timeout=4)
                except media.Problem: continue
                with self.lock:
                    self.data['server'] = {'name': r.get('name'), 'uri': uri, 'token': r.get('accessToken') or self.data['token'], 'id': r.get('clientIdentifier')}
                    self.save()
                return True
        return False

    def ready(self):
        """None when the server can be asked, else the page to show instead (sign-in, or no server found)."""
        if not self.data.get('token'):
            page = self.login_page()
            if page: return page
        if not self.data.get('server') and not self.find_server():
            return {'title': 'Kein Server', 'poll': 20, 'items': [], 'note': 'Kein Plex-Server unter deinem Konto antwortet. Läuft er und ist er im selben Netz?'}
        return None

    def forget(self, error):
        """The token stopped working (signed out on plex.tv): sign in again."""
        if error.args[1:] == (401,):
            with self.lock:
                self.data.pop('token', None); self.data.pop('server', None); self.save()

    # ---- pages ----------------------------------------------------------------------------------------------------------
    def cards(self, container):
        server = self.data['server']['uri']
        return [card(m, server) for m in container.get('Metadata') or [] if m.get('type') != 'photo']

    def page(self, tab):
        if tab == 'Downloads': return media.offline_page('plex', 'Filme und Folgen, die du auf ihrer Seite herunterlädst, gehen hier auch ohne Netz – im Flugzeug.')
        gate = self.ready()
        if gate: return gate
        try: return self.tab_page(tab)
        except media.Problem as error:
            self.forget(error)
            if error.args[1:] != (401,): self.data.pop('server', None)  # perhaps it moved: look for it again next time
            raise

    def tab_page(self, tab):
        if tab == 'Start':
            self.sync()
            items, seen = [], set()
            for hub in self.pms('/hubs/promoted', count=12).get('Hub') or []:  # the server's own home rows, as the Plex apps show them
                found = [c for c in self.cards(hub) if c['id'] not in seen]  # "On Deck" repeats "Continue Watching"
                seen |= {c['id'] for c in found}
                if found and hub.get('type') != 'playlist': items += [media.header(hub.get('title') or '')] + found
            return {'title': self.data['server'].get('name') or 'Plex', 'items': items, 'note': '' if items else 'Auf dem Server ist noch nichts.'}
        if tab == 'Bibliotheken':
            sections = self.pms('/library/sections').get('Directory') or []
            items = [{'id': 's' + s['key'], 'title': s.get('title'), 'sub': {'movie': 'Filme', 'show': 'Serien', 'artist': 'Musik'}.get(s.get('type'), 'Bibliothek'),
                      'thumb': None, 'kind': 'folder', 'type': 'section', 'key': f'/library/sections/{s["key"]}/all'} for s in sections if s.get('type') != 'photo']
            return {'title': 'Bibliotheken', 'items': items, 'note': '' if items else 'Keine Bibliotheken gefunden.'}
        if tab == 'Suche':
            return {'title': 'Suche', 'search': True, 'chips': self.data.get('searches', [])[:8], 'items': [], 'note': 'Tippe ins Suchfeld oder auf eine frühere Suche.'}

    def open(self, item):
        key = item['key']
        if item['type'] == 'section': return {'title': item['title'], 'items': self.cards(self.pms(key, sort='titleSort', **{'X-Plex-Container-Size': 300}))}
        items = self.cards(self.pms(key if key.endswith('/children') else f'/library/metadata/{item["id"]}/children'))
        if item['type'] == 'show' and len(items) == 1 and items[0]['type'] == 'season': return self.open(items[0])  # one season: straight to its episodes
        return {'title': item['title'] if item['type'] != 'season' else f'{item["title"]} · {item["sub"]}', 'items': items}

    def search(self, query):
        with self.lock:
            self.data['searches'] = [query] + [s for s in self.data.get('searches', []) if s.lower() != query.lower()][:11]
            self.save()
        items = []
        for hub in self.pms('/hubs/search', query=query, limit=12).get('Hub') or []:
            found = self.cards(hub)
            if found: items += [media.header(hub.get('title') or '')] + found
        return {'title': f'„{query}“', 'search': True, 'query': query, 'items': items, 'note': '' if items else 'Nichts gefunden.'}

    # ---- detail page ----------------------------------------------------------------------------------------------------
    def detail(self, item):
        """The page before a film or an episode plays: from the server, or for a download from the card (no network)."""
        local = offline.find('plex', item['id'])
        m = None
        if not local or self.data.get('server'):
            try: m = (self.pms(f'/library/metadata/{item["id"]}').get('Metadata') or [None])[0]
            except media.Problem:
                if not local: raise
        if m is None:
            meta, file = local
            pic = file.parent / meta['thumb_file'] if meta.get('thumb_file') else None
            pos, dur = meta.get('pos'), meta.get('dur')
            play = [('Fortsetzen ab ' + media.clock(pos), lambda: {'play': {**item, **meta}}), ('Von Anfang', lambda: {'play': {**item, **meta, 'from_start': True}})] \
                if media.resumable(pos, dur) else [('Abspielen', lambda: {'play': {**item, **meta}})]
            return {'title': meta.get('title'), 'item': item, 'buttons': play + media.offline_actions('plex', item),
                    'detail': {'title': meta.get('title'), 'meta': ' · '.join(x for x in (meta.get('sub'), media.clock(dur), 'auf der Karte') if x), 'summary': meta.get('summary'),
                               'backdrop': pic.as_uri() if pic and pic.is_file() else None}}
        server = self.data['server']['uri']
        dur, offset = (m.get('duration') or 0) / 1000 or None, (m.get('viewOffset') or 0) / 1000
        if m.get('type') == 'episode':
            title, bits = m.get('grandparentTitle') or '', [f'S{m.get("parentIndex", "?")} E{m.get("index", "?")} · {m.get("title", "")}']
        else: title, bits = m.get('title') or '', [str(m['year']) if m.get('year') else None]
        rating = m.get('audienceRating') or m.get('rating')
        bits += [f'{round(dur / 60)} Min.' if dur else None, m.get('contentRating'), f'★ {rating:.1f}'.replace('.', ',') if rating else None]
        card_ = card(m, server)
        play = [('Fortsetzen ab ' + media.clock(offset), lambda: {'play': card_}), ('Von Anfang', lambda: {'play': {**card_, 'from_start': True}})] \
            if media.resumable(offset, dur) else [('Abspielen', lambda: {'play': card_})]
        seen = bool(m.get('viewCount')) and not offset
        mark = ('Als ungesehen markieren' if seen else 'Als gesehen markieren', lambda: self.mark(item['id'], not seen))
        art = m.get('art') or m.get('grandparentArt') or m.get('thumb')
        return {'title': title, 'item': item, 'buttons': play + [mark] + media.offline_actions('plex', {**card_, 'id': item['id']}),
                'detail': {'title': title, 'meta': ' · '.join(x for x in bits if x), 'summary': m.get('summary'), 'backdrop': art and server + art}}

    def mark(self, rid, watched):
        self.pms('/:/scrobble' if watched else '/:/unscrobble', identifier=self.LIB, key=rid)
        if offline.find('plex', rid): offline.update('plex', rid, watched=watched, pos=0)
        return {'reload': True}

    # ---- offline ----------------------------------------------------------------------------------------------------------
    def fetch(self, job, base, progress):
        """One download for decks/offline.py: the original file, resumed where it stopped (Range)."""
        if self.ready(): raise media.Problem('Plex ist nicht angemeldet.')
        s = self.data['server']
        m = (self.pms(f'/library/metadata/{job["id"]}').get('Metadata') or [{}])[0]
        part = ((m.get('Media') or [{}])[0].get('Part') or [{}])[0]
        if not part.get('key'): raise media.Problem('Zu diesem Eintrag gibt es keine Datei.')
        ext = (part.get('container') or Path(part.get('file') or 'x.mkv').suffix.lstrip('.') or 'mkv')[:5]
        size = part.get('size') or 0
        tmp = Path(f'{base}.{ext}.part')
        have = tmp.stat().st_size if tmp.exists() else 0
        if size and size - have > __import__('shutil').disk_usage(base.parent).free - offline.RESERVE: raise offline.Full()
        progress(100 * have / size if size else 0, size)
        req = urllib.request.Request(s['uri'] + part['key'] + '?download=1', headers={**self.head(s['token']), **({'Range': f'bytes={have}-'} if have else {})})
        try: r = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as error:
            raise media.Problem('Der Plex-Server erlaubt keine Downloads (Einstellungen › Bibliothek).' if error.code in (401, 403) else f'Plex: Fehler {error.code}.')
        with r, open(tmp, 'ab' if have and r.status == 206 else 'wb') as out:
            got = have if r.status == 206 else 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk: break
                out.write(chunk); got += len(chunk)
                progress(100 * got / size if size else 0)
        if size and tmp.stat().st_size < size: raise media.Problem('Download unvollständig.')
        os.replace(tmp, f'{base}.{ext}')
        art = m.get('thumb') or m.get('art') or m.get('grandparentArt')
        try:
            with urllib.request.urlopen(urllib.request.Request(self.thumb(s['uri'] + art, 640, 360), headers=self.head(s['token'])), timeout=15) as r: picture = r.read()
        except (OSError, TypeError): picture = None
        c = card(m)
        return {'file': f'{base.name}.{ext}', 'thumb_bytes': picture,
                'meta': {'title': c['title'], 'sub': c['sub'], 'type': m.get('type'), 'dur': c['dur'], 'summary': m.get('summary'), 'pos': (m.get('viewOffset') or 0) / 1000}}

    def sync(self):
        """What was watched without a network goes to the server now (position, watched)."""
        for meta, _ in offline.items('plex'):
            if not meta.get('dirty'): continue
            try:
                if meta.get('watched'): self.pms('/:/scrobble', identifier=self.LIB, key=meta['id'])
                elif meta.get('pos'): self.pms('/:/timeline', ratingKey=meta['id'], key=f'/library/metadata/{meta["id"]}', state='stopped',
                                               time=int(meta['pos'] * 1000), duration=int((meta.get('dur') or 0) * 1000))
                offline.update('plex', meta['id'], dirty=False)
            except media.Problem: return

    # ---- playing --------------------------------------------------------------------------------------------------------
    def resolve(self, item):
        local = offline.find('plex', item['id'])
        if local:
            meta, file = local
            start = None if item.get('from_start') else meta.get('pos') if media.resumable(meta.get('pos'), meta.get('dur')) else None
            item['dur'] = item.get('dur') or meta.get('dur')
            return {'url': str(file), 'subs': [], 'opts': {'start': start, 'force_media_title': f'{meta.get("title")} – {meta.get("sub")}' if meta.get('sub') else meta.get('title')}}
        m = (self.pms(f'/library/metadata/{item["id"]}', includeMarkers=1).get('Metadata') or [{}])[0]
        intro = next((k for k in m.get('Marker') or [] if k.get('type') == 'intro'), None)
        if intro: item['skip'] = [intro.get('startTimeOffset', 0) / 1000, intro.get('endTimeOffset', 0) / 1000]
        part = ((m.get('Media') or [{}])[0].get('Part') or [{}])[0]
        if not part.get('key'): raise media.Problem('Zu diesem Eintrag gibt es keine Datei.')
        s = self.data['server']
        # shortcut: Direct Play only (mpv plays nearly every file); add Plex's transcoder when a file is too heavy for the Thor
        subs = [(s['uri'] + st['key'], st.get('displayTitle') or st.get('language') or 'Untertitel', st.get('languageCode') or '')
                for st in part.get('Stream') or [] if st.get('streamType') == 3 and st.get('key')]  # subtitles in their own files; those inside the file mpv sees itself
        offset = 0 if item.get('from_start') else (m.get('viewOffset') or 0) / 1000
        item['dur'] = item.get('dur') or (m.get('duration') or 0) / 1000 or None
        return {'url': s['uri'] + part['key'], 'subs': subs,
                'opts': {'start': offset if media.resumable(offset, item['dur']) else None, 'force_media_title': f'{item["title"]} – {item["sub"]}' if item.get('sub') else item['title'],
                         'http_header_fields': f'X-Plex-Token: {s["token"]}'}}

    def progress(self, item, pos, dur, state):
        if pos is None: return
        dur = dur or item.get('dur') or 0
        done = bool(dur and pos >= .9 * dur)
        local = offline.find('plex', item['id'])
        if local: offline.update('plex', item['id'], pos=0 if done else pos, watched=done or local[0].get('watched', False), dirty=True)
        if not self.data.get('server'): return
        try:
            self.pms('/:/timeline', ratingKey=item['id'], key=f'/library/metadata/{item["id"]}', state=state, time=int(pos * 1000), duration=int(dur * 1000))
            if done and not item.get('scrobbled'):
                self.pms('/:/scrobble', identifier=self.LIB, key=item['id'])
                item['scrobbled'] = True
            if local: offline.update('plex', item['id'], dirty=False)
        except media.Problem: pass  # the next report tries again; a download keeps it for later (sync)

    def actions(self, item): return media.offline_actions('plex', item)

    def headers(self, url):
        s = self.data.get('server')
        return {'X-Plex-Token': s['token']} if s and url.startswith(s['uri']) else {}

    def thumb(self, url, w, h):
        """Plex scales pictures itself: only the size on screen comes over the network."""
        s = self.data.get('server')
        if not s or not url.startswith(s['uri']): return url
        return f'{s["uri"]}/photo/:/transcode?' + urllib.parse.urlencode({'width': w, 'height': h, 'minSize': 1, 'upscale': 1, 'url': url[len(s['uri']):]})


class Deck(media.Deck):
    def __init__(self, window): super().__init__(window, Plex())
