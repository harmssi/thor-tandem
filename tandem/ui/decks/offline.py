"""Videos to watch without a network (on a flight): YouTube and Plex downloads on the SD card.

Files: <card>/Videos/Tandem-Offline/<app>/<id>.<ext>, beside it <id>.json (title, channel or show, description, length,
where playback stands, and for Plex what still has to go back to the server) and <id>.jpg (the picture). Without a card
~/Videos/Tandem-Offline is used. The queue lives in ~/.config/tandem/media/offline.json (0600: the Plex job keeps no
token, the source adds it when it fetches), so a download goes on after a restart or standby: a source fetches with
resume (yt-dlp --continue, HTTP Range). Downloads run only on Wi-Fi and only with RESERVE bytes left on the card.
A source that downloads has fetch(job, base, progress) -> {'file', 'meta'}; it registers with start(name, source)."""
import glob, json, os, shutil, subprocess, threading, time
from pathlib import Path

STORE = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'tandem/media/offline.json'
RESERVE = 2e9
_lock, _wake = threading.Lock(), threading.Event()
_sources, _state = {}, {'jobs': None, 'thread': None, 'listeners': []}


class Full(Exception):
    """Not enough room on the card."""


def root():
    cards = sorted(glob.glob('/run/media/*/*')) + sorted(glob.glob('/media/*/*'))
    base = next((Path(c) for c in cards if os.access(c, os.W_OK)), None)
    return (base / 'Videos/Tandem-Offline') if base else Path.home() / 'Videos/Tandem-Offline'


def size_text(n):
    if not n: return ''
    return f'{n / 1e9:.1f} GB'.replace('.', ',') if n >= 1e9 else f'{max(1, round(n / 1e6))} MB'


def on_wifi():
    try: out = subprocess.run(['nmcli', '-t', '-f', 'TYPE,STATE', 'device'], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError): return False
    return any(line.startswith('wifi:connected') for line in out.splitlines())


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f: json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def jobs():
    if _state['jobs'] is None:
        try: _state['jobs'] = json.loads(STORE.read_text()).get('jobs', [])
        except (OSError, ValueError): _state['jobs'] = []
    return _state['jobs']


def _save(): _write(STORE, {'jobs': jobs()})


def _changed():
    for fn in list(_state['listeners']):
        try: fn()
        except Exception: pass


# ---- what is on the card ---------------------------------------------------------------------------------------------
def folder(app): return root() / app


def items(app):
    """The finished downloads of one app, newest first: [(meta, video file)]."""
    out = []
    for side in folder(app).glob('*.json'):
        try: meta = json.loads(side.read_text())
        except (OSError, ValueError): continue
        f = side.parent / meta.get('file', '')
        if meta.get('file') and f.is_file(): out.append((meta, f))
    return sorted(out, key=lambda m: -m[0].get('at', 0))


def find(app, vid):
    side = folder(app) / f'{safe(vid)}.json'
    try: meta = json.loads(side.read_text())
    except (OSError, ValueError): return None
    f = side.parent / meta.get('file', '')
    return (meta, f) if meta.get('file') and f.is_file() else None


def update(app, vid, **change):
    """Changes the sidecar of one download (position, watched, what still goes to the server)."""
    with _lock:
        side = folder(app) / f'{safe(vid)}.json'
        try: meta = json.loads(side.read_text())
        except (OSError, ValueError): return None
        meta.update(change)
        _write(side, meta)
        return meta


def delete(app, vid):
    base = folder(app) / safe(vid)
    for f in base.parent.glob(base.name + '.*'):
        try: f.unlink()
        except OSError: pass
    with _lock:
        jobs()[:] = [j for j in jobs() if not (j['app'] == app and j['id'] == vid)]
        _save()
    _changed()


def safe(vid): return ''.join(c for c in str(vid) if c.isalnum() or c in '-_')[:64] or 'x'


# ---- the queue -------------------------------------------------------------------------------------------------------
def add(app, item, **extra):
    """Puts one video in the queue; returns a German text for the player."""
    vid = str(item['id'])
    if find(app, vid): return 'Schon heruntergeladen.'
    with _lock:
        if any(j['app'] == app and j['id'] == vid for j in jobs()): return 'Ist schon in der Warteschlange.'
        keep = {k: item.get(k) for k in ('id', 'title', 'sub', 'thumb', 'dur', 'channel', 'type') if item.get(k) is not None}
        jobs().append({'app': app, 'id': vid, 'item': keep, 'state': 'wait', 'pct': 0, **extra})
        _save()
    _wake.set(); _changed()
    return f'Wird heruntergeladen: {item["title"]}' if on_wifi() else 'Kommt in die Warteschlange und lädt im WLAN.'


def queued(app): return [j for j in jobs() if j['app'] == app]


def start(app, source, listener=None):
    """A source is there to fetch its jobs; the one worker for all starts with the first."""
    _sources[app] = source
    if listener: _state['listeners'] = [listener]  # the deck on screen repaints
    if not _state['thread'] or not _state['thread'].is_alive():
        _state['thread'] = threading.Thread(target=_work, daemon=True)
        _state['thread'].start()
    _wake.set()


def _next():
    with _lock:
        return next((j for j in jobs() if j['state'] in ('wait', 'run') and j['app'] in _sources), None)


def _work():
    while True:
        job = _next()
        if not job or not on_wifi():
            _wake.wait(60); _wake.clear()
            continue
        base = folder(job['app']) / safe(job['id'])
        try:
            base.parent.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(base.parent).free < RESERVE + (job.get('size') or 0): raise Full()
            job['state'] = 'run'; _changed()
            last = [0.0]

            def progress(pct, size=None):
                job['pct'] = max(0, min(100, int(pct)))
                if size: job['size'] = size
                if size and shutil.disk_usage(base.parent).free < RESERVE: raise Full()
                if time.time() - last[0] > 1: last[0] = time.time(); _changed()
            got = _sources[job['app']].fetch(job, base, progress)
            thumb = job['item'].get('thumb')
            meta = {**job['item'], **got.get('meta', {}), 'file': got['file'], 'size': (base.parent / got['file']).stat().st_size, 'at': time.time()}
            if thumb and got.get('thumb_bytes'): (base.parent / f'{base.name}.jpg').write_bytes(got['thumb_bytes']); meta['thumb_file'] = f'{base.name}.jpg'
            _write(base.parent / f'{base.name}.json', meta)
            with _lock: jobs()[:] = [j for j in jobs() if j is not job]; _save()
        except Full:
            job.update(state='fail', error='Kein Platz mehr auf der Karte.')
            with _lock: _save()
        except Exception as error:
            job['tries'] = job.get('tries', 0) + 1
            job.update(state='fail' if job['tries'] >= 3 else 'wait', error=str(error)[:120])
            with _lock: _save()
            if job['state'] == 'wait': _wake.wait(30)  # the network went: try again later
        _changed()
