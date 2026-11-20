"""mpv's JSON IPC (mpv manual, "JSON IPC") for the media decks: commands go out, watched properties and events come in.

Mpv(path, heard) keeps trying to connect to the player's socket (mpv --input-ipc-server=path), watches WATCH and calls
heard(message) for every event on its own thread ({'event': 'gone'} when the player went away). props holds the last
value of each watched property. options() packs per-file options for loadfile.
"""
import json, socket, threading, time

WATCH = ('pause', 'time-pos', 'duration', 'track-list', 'idle-active', 'paused-for-cache', 'eof-reached', 'speed')


def options(values):
    """loadfile's per-file options; every value is quoted as %bytes%value, so commas and '=' in a URL stay intact."""
    return ','.join(f'{k}=%{len(str(v).encode())}%{v}' for k, v in values.items() if v is not None)


def tracks(track_list, kind):
    """[(id, label, selected)] of one kind ('sub' or 'audio') from mpv's track-list."""
    out = []
    for t in track_list or []:
        if t.get('type') != kind: continue
        lang = LANGS.get(t.get('lang'), t.get('lang') or '')
        title = t.get('title') or ''
        if len(title) > 40 or '&' in title or title.lower() in (lang.lower(), (t.get('lang') or '').lower()): title = ''  # a stream's URL is no name
        label = f'{title} ({lang})' if title and lang and lang.lower() not in title.lower() else title or lang or f'Spur {t["id"]}'
        out.append((t['id'], label, bool(t.get('selected'))))
    return out


LANGS = {'de': 'Deutsch', 'ger': 'Deutsch', 'deu': 'Deutsch', 'en': 'Englisch', 'eng': 'Englisch', 'fr': 'Französisch', 'fre': 'Französisch', 'fra': 'Französisch',
         'es': 'Spanisch', 'spa': 'Spanisch', 'it': 'Italienisch', 'ita': 'Italienisch', 'ja': 'Japanisch', 'jpn': 'Japanisch'}


class Mpv:
    def __init__(self, path, heard):
        self.path, self.heard, self.alive, self.sock, self.props, self.lock = path, heard, True, None, {}, threading.Lock()
        threading.Thread(target=self.listen, daemon=True).start()

    def listen(self):
        while self.alive:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(self.path)
                self.sock, buf = sock, b''
                for n, name in enumerate(WATCH): self.command('observe_property', n + 1, name)
                self.heard({'event': 'connected'})
                while self.alive:
                    chunk = sock.recv(1 << 16)
                    if not chunk: break
                    *lines, buf = (buf + chunk).split(b'\n')
                    for line in lines: self.take(line)
            except OSError: pass
            finally:
                try: sock.close()
                except OSError: pass
            if self.sock:
                self.sock = None
                self.heard({'event': 'gone'})
            time.sleep(.5)  # the player is not up yet, or gone

    def take(self, line):
        try: m = json.loads(line)
        except ValueError: return
        if not isinstance(m, dict) or 'event' not in m: return  # replies to our commands: nothing waits for them
        if m['event'] == 'property-change': self.props[m.get('name')] = m.get('data')
        self.heard(m)

    def command(self, *args):
        sock = self.sock
        if not sock: return False
        try:
            with self.lock: sock.sendall(json.dumps({'command': list(args)}).encode() + b'\n')
            return True
        except OSError: return False

    def load(self, url, **opts):
        """Play url now (replaces what plays); opts are per-file options such as start, audio-file, force-media-title."""
        return self.command('loadfile', url, 'replace', -1, options({k.replace('_', '-'): v for k, v in opts.items()}))

    def close(self):
        self.alive = False
        sock, self.sock = self.sock, None
        if sock:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            sock.close()
