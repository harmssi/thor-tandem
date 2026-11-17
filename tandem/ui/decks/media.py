"""The bottom screen of Tandem's media apps (decks/youtube.py, decks/plex.py): browse below, watch above.

mpv runs full screen on the top screen (started by the service, see MEDIA_APPS in tandem.py) and is steered over its
JSON IPC socket (decks/mpv.py). This deck shows what a TV app shows - big pictures, a clear focus, a "now playing" page
with seek bar, subtitles, audio tracks and volume - and works by touch and by controller alike (the service hands the
controller's navigation to the deck while a media app runs: D-pad, A open/play, B back, X play/pause, Y queue, L/R tabs).

A source (YouTube, Plex) is plain Python and does the talking; everything slow runs on a thread:
    name, accent, tabs, search_title
    page(tab) / open(item) / search(text) -> {'title', 'items', 'note', 'search', 'chips', 'code', 'poll'}
    resolve(item) -> {'url', 'opts' (loadfile options), 'subs' [(url, title, lang)]}
    progress(item, pos, dur, state)      # 'playing' every 10 s, 'paused', 'stopped'
    actions(item) -> [(label, fn -> message)]; headers(url) -> dict; optional thumb(url, w, h) -> url
Items are dicts: id, title, sub, thumb, kind ('video', 'folder' or 'header'), badge, progress (0..1), watched.
"""
import threading, time, traceback, urllib.request
from collections import OrderedDict

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QLinearGradient, QPainterPath, QPen

from decks.mpv import Mpv, tracks

BG, CARD, RAISED, TEXT, DIM, FAINT = (QColor(c) for c in ('#0f0f11', '#1c1c20', '#2a2a30', '#f4f4f6', '#a3a3ad', '#5c5c66'))
COLS = 3
LANG_NAMES = {'de': 'Deutsch', 'en': 'Englisch'}


class Problem(Exception):
    """Something to tell the player (in German); args[1], if there, is a code for the source."""


def clock(secs):
    if secs is None: return ''
    secs = int(secs)
    return f'{secs // 3600}:{secs // 60 % 60:02d}:{secs % 60:02d}' if secs >= 3600 else f'{secs // 60}:{secs % 60:02d}'


def count(n):
    """Views the short German way, as YouTube writes them: 950, 56 Tsd., 1,2 Mio."""
    if n < 10000: return str(n)
    if n < 1e6: return f'{n / 1e3:.0f} Tsd.'
    value, unit = (n / 1e6, 'Mio.') if n < 1e9 else (n / 1e9, 'Mrd.')
    return f'{value:.1f}'.removesuffix('.0').replace('.', ',') + ' ' + unit


def resumable(pos, dur):
    """Worth starting where it was left: more than half a minute in and not in the last half minute."""
    return bool(pos and pos > 30 and (not dur or pos < dur - 30))


def header(title): return {'kind': 'header', 'title': title}


def grid(items, cols=COLS):
    """[(index, row, column)] of the cards; a header ends the row and is no card."""
    cells, row, col = [], -1, cols
    for i, it in enumerate(items):
        if it.get('kind') == 'header': col = cols; continue
        if col >= cols: row, col = row + 1, 0
        cells.append((i, row, col)); col += 1
    return cells


def move(cells, i, a):
    """The card the D-pad goes to from card i (an index into the items); the same one at an edge."""
    if not cells: return None
    here = next((c for c in cells if c[0] == i), cells[0])
    n = cells.index(here)
    if a == 'left': return cells[max(0, n - 1)][0]
    if a == 'right': return cells[min(len(cells) - 1, n + 1)][0]
    row = [c for c in cells if c[1] == here[1] + (1 if a == 'down' else -1)]
    return min(row, key=lambda c: abs(c[2] - here[2]))[0] if row else here[0]


def up_next(items, i):
    """What plays after item i of a page: the episodes after it (a TV app goes on with the series), else nothing."""
    if items[i].get('type') != 'episode': return []
    return [it for it in items[i + 1:] if it.get('type') == 'episode']


class Pics:
    """Pictures from the internet or the Plex server, decoded straight to the size on screen; the last ones are kept."""

    def __init__(self, ready, headers, limit=80, workers=3):
        self.cache, self.todo, self.lock, self.wake = OrderedDict(), [], threading.Lock(), threading.Semaphore(0)
        self.ready, self.headers, self.limit, self.alive = ready, headers, limit, True
        for _ in range(workers): threading.Thread(target=self.work, daemon=True).start()

    def get(self, url, w, h):
        key = (url, int(w), int(h))
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            self.cache[key] = None
            self.todo.append(key)
            while len(self.cache) > self.limit: self.cache.popitem(last=False)
        self.wake.release()
        return None

    def work(self):
        while True:
            self.wake.acquire()
            if not self.alive: return
            with self.lock:
                if not self.todo: continue
                key = self.todo.pop()  # newest first: that is what is on screen
                if key not in self.cache: continue
            try: img = self.load(*key)
            except Exception: img = False
            with self.lock:
                if key in self.cache: self.cache[key] = img
            if self.alive: self.ready.emit()

    def load(self, url, w, h):
        with urllib.request.urlopen(urllib.request.Request(url, headers=self.headers(url)), timeout=12) as r: data = r.read()
        buf = QBuffer(); buf.setData(QByteArray(data)); buf.open(QBuffer.OpenModeFlag.ReadOnly)
        reader = QImageReader(buf)
        size = reader.size()
        if size.isValid() and size.width() and size.height():
            k = max(w / size.width(), h / size.height())
            reader.setScaledSize(QSize(max(w, round(size.width() * k)), max(h, round(size.height() * k))))
        img = reader.read()
        if img.isNull(): return False
        if img.width() < w or img.height() < h: img = img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        return img.copy((img.width() - w) // 2, (img.height() - h) // 2, w, h).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    def close(self):
        self.alive = False
        with self.lock: self.cache.clear()
        for _ in range(3): self.wake.release()


class Deck:
    def __init__(self, window, source):
        self.w, self.src, self.accent = window, source, QColor(source.accent)
        self.alive, self.gen, self.pad = True, 0, False
        self.pics = Pics(window.loaded, source.headers)
        self.now, self.queue, self.busy, self.subs = None, [], '', []
        self.stack, self.focus, self.page_at = [], {}, 0.0
        self.said, self.said_until, self.armed, self.reported = '', 0.0, 0.0, 0.0
        sock = ((window.RUN or {}).get('port') or {}).get('socket')
        self.mpv = Mpv(sock, self.heard) if sock else None
        self.open_tab(window.memo.get('media:' + source.name, source.tabs[0]))
        threading.Thread(target=self.tick, daemon=True).start()

    def close(self):
        if self.now: self.report('stopped')
        self.alive = False
        if self.mpv: self.mpv.close()
        self.pics.close()

    # ---- state ------------------------------------------------------------------------------------------------------------
    def tabs(self): return (['Läuft'] if self.now else []) + list(self.src.tabs) + (['Warteschlange'] if self.queue else [])

    def say(self, text, secs=2.5):
        self.said, self.said_until = text, time.time() + secs
        self.w.loaded.emit()

    def open_tab(self, tab):
        if tab not in self.tabs(): tab = self.src.tabs[0]
        self.tab, self.stack = tab, []
        self.w.memo['media:' + self.src.name] = tab if tab in self.src.tabs else self.src.tabs[0]
        if tab in self.src.tabs:
            self.stack = [{'title': tab, 'items': [], 'loading': True}]
            self.load(lambda: self.src.page(tab))

    def load(self, fn, push=False, title=''):
        """Runs fn (a source call that returns a page) on a thread; its page replaces the current one (push: goes on top)."""
        self.gen += 1
        gen = self.gen
        if push: self.stack.append({'title': title, 'items': [], 'loading': True})
        else: self.stack[-1]['loading'] = True

        def run():
            try: page = fn()
            except Problem as error: page = {'error': error.args[0]}
            except Exception as error:
                traceback.print_exc()
                page = {'error': f'Fehler: {error}'}
            if gen != self.gen or not self.alive or not self.stack: return
            old = self.stack[-1]
            page = {'items': [], **(page or {})}
            page.setdefault('title', old.get('title'))
            if old.get('id') and old.get('items') and page.get('poll'): page['id'] = old['id']  # a page that is asked again keeps its focus
            self.stack[-1], self.page_at = page, time.time()
            self.w.loaded.emit()
        threading.Thread(target=run, daemon=True).start()
        self.w.loaded.emit()

    def page(self): return self.stack[-1] if self.stack else None

    def activate(self, i):
        items = self.page()['items']
        it = items[i]
        self.focus[id(self.page())] = i
        if it['kind'] == 'folder': self.load(lambda: self.src.open(it), push=True, title=it['title'])
        elif it['kind'] == 'video': self.play(it, up_next(items, i))

    def back(self):
        if self.tab == 'Läuft' or self.tab == 'Warteschlange': return self.open_tab(self.w.memo.get('media:' + self.src.name, self.src.tabs[0]))
        if len(self.stack) > 1:
            self.gen += 1  # a page that is still loading for the one we leave must not land on this one
            self.stack.pop()
        elif self.now: self.open_tab('Läuft')

    def search(self, text):
        text = text.strip()
        if not text: return
        self.tab = 'Suche'
        self.stack = [{'title': 'Suche', 'search': True, 'query': text, 'items': [], 'loading': True}]
        self.load(lambda: self.src.search(text))

    def ask(self):
        self.w.ask(self.src.search_title, False, self.search)
        self.w.update()

    # ---- playing ----------------------------------------------------------------------------------------------------------
    def playing(self): return bool(self.now and self.mpv and not self.mpv.props.get('pause') and not self.busy)

    def play(self, item, after=None):
        if not self.mpv: return self.say('Kein Abspieler verbunden.')
        if self.now: self.report('stopped')
        self.now, self.busy, self.subs = dict(item), 'Lädt …', []
        if after is not None and after: self.queue = [dict(it) for it in after]
        self.mpv.props.update({'time-pos': None, 'duration': item.get('dur'), 'track-list': []})
        self.tab, self.stack = 'Läuft', []
        now = self.now

        def run():
            try:
                got = self.src.resolve(now)
                if self.now is not now: return
                self.subs = got.get('subs') or []
                if not self.mpv.load(got['url'], **got.get('opts', {})): raise Problem('Der Abspieler antwortet nicht.')
            except Problem as error:
                if self.now is now: self.now, self.busy = None, ''; self.say(error.args[0], 5)
            except Exception as error:
                traceback.print_exc()
                if self.now is now: self.now, self.busy = None, ''; self.say(f'Fehler: {error}', 5)
            self.w.loaded.emit()
        threading.Thread(target=run, daemon=True).start()

    def next(self):
        if self.queue: self.play(self.queue.pop(0))
        else:
            self.now = None
            if self.mpv: self.mpv.command('show-text', self.w.tr(f'{self.src.name}: unten etwas auswählen'), 4000)
            if self.tab == 'Läuft': self.open_tab(self.w.memo.get('media:' + self.src.name, self.src.tabs[0]))

    def heard(self, m):
        ev = m.get('event')
        if ev == 'connected' and not self.now: self.mpv.command('show-text', self.w.tr(f'{self.src.name}: unten etwas auswählen'), 6000)
        elif ev == 'file-loaded':
            self.busy = ''
            for url, title, lang in self.subs: self.mpv.command('sub-add', url, 'auto', title, lang)
        elif ev == 'end-file':
            if m.get('reason') == 'eof' and self.now and not self.busy:
                dur = self.mpv.props.get('duration')
                self.report('stopped', dur, dur)
                self.next()
            elif m.get('reason') == 'error' and self.now:
                self.say(f'„{self.now["title"]}“ lässt sich nicht abspielen ({m.get("file_error", "Fehler")}).', 5)
                self.next()
        elif ev == 'property-change' and m.get('name') == 'pause' and self.now and not self.busy:
            self.report('paused' if m.get('data') else 'playing')
        elif ev == 'gone' and self.now: self.busy = 'Abspieler weg …'
        self.w.loaded.emit()

    def report(self, state, pos=None, dur=None):
        """Where playback stands, to the source (Plex: the server; YouTube: the history), on a thread."""
        if not self.now or not self.mpv: return
        pos = pos if pos is not None else self.mpv.props.get('time-pos')
        dur = dur if dur is not None else self.mpv.props.get('duration')
        if pos is None: return
        self.reported = time.time()
        threading.Thread(target=self.src.progress, args=(self.now, pos, dur, state), daemon=False).start()  # a last report must outlive the deck

    def tick(self):
        while self.alive:
            time.sleep(1)
            if self.playing():
                if time.time() - self.reported > 10: self.report('playing')
                self.w.loaded.emit()  # the clock and the bar move
            page = self.page()
            if page and page.get('poll') and not page.get('loading') and time.time() - self.page_at > page['poll'] and self.tab in self.src.tabs:
                tab = self.tab
                self.load(lambda: self.src.page(tab))
            if self.said and time.time() > self.said_until: self.said = ''; self.w.loaded.emit()

    def toggle(self):
        if self.mpv and self.now: self.mpv.command('cycle', 'pause')

    def seek(self, secs, how='relative'):
        if self.mpv and self.now: self.mpv.command('seek', secs, how)

    def enqueue(self, it):
        if it.get('kind') != 'video': return
        self.queue.append(dict(it))
        self.say(f'In der Warteschlange: {it["title"]}')

    def volume(self, step):
        vol = self.w.SET.get('vol')
        if vol is None: return
        self.w.SET['vol'] = max(0, min(100, vol + step))
        self.w.post('api/set', {'key': 'vol', 'value': self.w.SET['vol'], 'from': self.w.me})
        self.w.OSD = self.w.SET['vol']; self.w.timers['osd'].start(1600)

    # ---- controller -------------------------------------------------------------------------------------------------------
    def key(self, a):
        self.pad = True
        tabs = self.tabs()
        if a in ('prev', 'next'):
            n = tabs.index(self.tab) if self.tab in tabs else 0
            return self.open_tab(tabs[(n + (1 if a == 'next' else -1)) % len(tabs)])
        if a == 'close': return self.toggle()
        if a == 'back': return self.back()
        if self.tab == 'Läuft':
            if a == 'ok': self.toggle()
            elif a in ('left', 'right'): self.seek(-10 if a == 'left' else 30)
            elif a in ('up', 'down'): self.volume(5 if a == 'up' else -5)
            elif a == 'fav': self.cycle_subs()
            return
        if self.tab == 'Warteschlange':
            if a == 'ok' and self.queue: self.play(self.queue.pop(0))
            return
        page = self.page()
        if not page: return
        if page.get('search') and a == 'up' and self.focus.get(id(page), -1) in [c[0] for c in grid(page['items'])[:COLS]] + [-1]:
            return self.ask()  # from the first row up into the search field
        cells = grid(page['items'])
        here = self.focus.get(id(page))
        if a in ('left', 'right', 'up', 'down'):
            self.focus[id(page)] = move(cells, here, a) if here is not None else (cells[0][0] if cells else None)
        elif a == 'ok':
            if here is not None and here < len(page['items']): self.activate(here)
            elif page.get('search'): self.ask()
        elif a == 'fav' and here is not None and here < len(page['items']): self.enqueue(page['items'][here])

    def cycle_subs(self):
        subs = tracks(self.mpv.props.get('track-list') if self.mpv else [], 'sub')
        if not subs: return self.say('Keine Untertitel.')
        on = next((n for n, s in enumerate(subs) if s[2]), -1)
        if on + 1 >= len(subs): self.mpv.command('set_property', 'sid', 'no'); self.say('Untertitel aus')
        else: self.mpv.command('set_property', 'sid', subs[on + 1][0]); self.say('Untertitel: ' + subs[on + 1][1])

    def tap(self, fn):
        def run():
            self.pad = False  # a finger is in charge: no focus ring
            fn()
        return run

    # ---- painting ---------------------------------------------------------------------------------------------------------
    def paint(self, p):
        w = self.w
        u, W, H = w.u, w.width(), w.height()
        p.fillRect(0, 0, W, H, BG)
        g = QLinearGradient(0, 0, 0, 30 * u)  # a breath of the app's colour from the top
        g.setColorAt(0, QColor(self.accent.red(), self.accent.green(), self.accent.blue(), 34)); g.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(0, 0, W, 30 * u), g)
        y = self.top(p)
        mini = self.now and self.tab != 'Läuft'
        body = QRectF(0, y, W, H - y - (13 * u if mini else 0))
        if self.tab == 'Läuft': self.player(p, body)
        elif self.tab == 'Warteschlange': self.waiting(p, body)
        else: self.browse(p, body)
        if mini: self.mini(p, QRectF(2.6 * u, H - 12 * u, W - 5.2 * u, 10 * u))
        if self.said: self.toast(p)
        return True

    def logo(self, p, x, y, h):
        """The app's sign: YouTube's red play button, Plex's chevron."""
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(self.accent)
        if self.src.name == 'YouTube':
            p.drawRoundedRect(QRectF(x, y + h * .14, h * 1.42, h * .72), h * .2, h * .2)
            self.triangle(p, QPointF(x + h * .71, y + h * .5), h * .34, TEXT)
            return x + h * 1.42
        path = QPainterPath()
        for px, py in ((0, 0), (.42, 0), (.86, .5), (.42, 1), (0, 1), (.44, .5)): path.lineTo(x + px * h * .7, y + py * h) if px or py else path.moveTo(x, y)
        path.closeSubpath(); p.drawPath(path)
        return x + h * .62

    def triangle(self, p, c, r, color):
        path = QPainterPath(QPointF(c.x() - r * .6, c.y() - r))
        path.lineTo(c.x() + r, c.y()); path.lineTo(c.x() - r * .6, c.y() + r); path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(color); p.drawPath(path)

    def glyph(self, p, name, c, r, color):
        """play, pause, prev, next: drawn, so they need no icon font."""
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(color)
        if name == 'play': return self.triangle(p, QPointF(c.x() + r * .15, c.y()), r, color)
        if name == 'pause':
            for dx in (-.55, .2): p.drawRoundedRect(QRectF(c.x() + dx * r, c.y() - r * .85, r * .38, r * 1.7), r * .08, r * .08)
            return
        k = -1 if name == 'prev' else 1  # a triangle towards the bar
        path = QPainterPath(QPointF(c.x() - k * r * .6, c.y() - r * .8)); path.lineTo(c.x() + k * r * .5, c.y()); path.lineTo(c.x() - k * r * .6, c.y() + r * .8); path.closeSubpath()
        p.drawPath(path)
        p.drawRect(QRectF(c.x() + k * .62 * r - r * .1, c.y() - r * .8, r * .2, r * 1.6))

    def top(self, p):
        """Logo, the tabs as a row of pills, and the way out on the right. Returns the y below."""
        w, u = self.w, self.w.u
        x, y, h = 2.6 * u, 2.4 * u, 5.4 * u
        x = self.logo(p, x, y + 1.1 * u, 3.2 * u) + 1.1 * u
        w.text(p, self.src.name, x, y, ('u', 2.5, 700, -.02), TEXT, lh=h / (2.5 * u))
        x += w.width_of(self.src.name, ('u', 2.5, 700, -.02)) + 2.2 * u
        tabs, f = self.tabs(), ('u', 2.0, 600)
        room = w.width() - 2.6 * u - 13 * u - x
        need = sum(w.width_of(t, f) + 3.4 * u for t in tabs)
        if need > room: f = ('u', round(2.0 * room / need, 2), 600)
        for t in tabs:
            tw = w.width_of(t, f) + 3.4 * u
            rect = QRectF(x, y + .5 * u, tw, h - u)
            on = t == self.tab
            if on: w.capsule(p, rect, TEXT)
            w.text(p, t, rect.x(), rect.y(), f, BG if on else DIM, rect.width(), 1, rect.height() / (f[1] * u))
            w.hit(rect, self.tap(lambda t=t: self.open_tab(t)), name='tab:' + t)
            x += tw + .4 * u
        armed = time.time() - self.armed < 3
        rect = QRectF(w.width() - 2.6 * u - 12 * u, y + .5 * u, 12 * u, h - u)
        w.capsule(p, rect, QColor('#c2412f') if armed else RAISED)
        w.text(p, 'Nochmal tippen' if armed else 'Beenden', rect.x(), rect.y(), ('u', 1.7 if armed else 2.0, 600), TEXT, rect.width(), 1, rect.height() / ((1.7 if armed else 2.0) * u))

        def leave():
            if time.time() - self.armed < 3: w.post('api/quit')
            else: self.armed = time.time()
        w.hit(rect, leave, name='Beenden')
        return y + h + 1.6 * u

    # -- browse --
    def browse(self, p, body):
        w, u, page = self.w, self.w.u, self.page()
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        y = body.y()
        if page.get('code'): return self.login(p, body, page)
        if len(self.stack) > 1 or page.get('search'):
            if page.get('search'):
                field = QRectF(x0, y, cw, 6.4 * u)
                w.capsule(p, field, CARD, QColor(255, 255, 255, 30))
                w.text(p, page.get('query') or self.src.search_title + ' …', x0 + 3 * u, y, ('u', 2.3, 500), TEXT if page.get('query') else FAINT, cw - 6 * u, lh=6.4 / 2.3)
                w.hit(field, self.tap(self.ask), name='Suchfeld')
                y += 7.6 * u
                if not page.get('query') and page.get('chips'):
                    cx = x0
                    for chip in page['chips']:
                        cwid = min(w.width_of(chip, ('u', 1.9, 500)) + 3.2 * u, 40 * u)
                        if cx + cwid > x0 + cw: break
                        rect = QRectF(cx, y, cwid, 4.6 * u)
                        w.capsule(p, rect, RAISED)
                        w.text(p, chip, rect.x() + 1.6 * u, rect.y(), ('u', 1.9, 500), TEXT, cwid - 3.2 * u, lh=4.6 / 1.9)
                        w.hit(rect, self.tap(lambda chip=chip: self.search(chip)), name='chip:' + chip)
                        cx += cwid + u
                    y += 6 * u
            else:
                rect = QRectF(x0, y, 6 * u, 5 * u)
                w.capsule(p, rect, RAISED)
                w.text(p, '‹', rect.x(), rect.y() - .3 * u, ('u', 3.4, 500), TEXT, rect.width(), 1, 5 / 3.4)
                w.hit(rect, self.tap(self.back), name='Zurück')
                w.text(p, page.get('title') or '', x0 + 7.4 * u, y, ('u', 2.8, 700, -.02), TEXT, cw - 7.4 * u, lh=5 / 2.8)
                y += 6.4 * u
        if page.get('loading') and not page['items']:
            return w.text(p, 'Lädt …', x0, y + 12 * u, ('u', 2.4, 500), DIM, cw, 1)
        if page.get('error'):
            w.text(p, page['error'], x0 + 6 * u, y + 10 * u, ('u', 2.3, 500), TEXT, cw - 12 * u, 1, 1.35, None)
            rect = QRectF(x0 + cw / 2 - 10 * u, y + 22 * u, 20 * u, 6 * u)
            w.capsule(p, rect, RAISED)
            w.text(p, 'Nochmal', rect.x(), rect.y(), ('u', 2.1, 600), TEXT, rect.width(), 1, 6 / 2.1)
            return w.hit(rect, self.tap(lambda: self.open_tab(self.tab) if len(self.stack) < 2 else self.back()), name='Nochmal')
        if not page['items'] and page.get('note'):
            return w.text(p, page['note'], x0 + 6 * u, y + 8 * u, ('u', 2.2, 500), DIM, cw - 12 * u, 1, 1.4, None)
        self.cards(p, QRectF(0, y, w.width(), body.bottom() - y), page)

    def cards(self, p, area, page):
        w, u = self.w, self.w.u
        x0, gap = 2.6 * u, 1.6 * u
        cw = (w.width() - 5.2 * u - (COLS - 1) * gap) / COLS
        th = cw * 9 / 16
        ch, hh = th + 9.8 * u, 5 * u
        items, key = page['items'], f'media:{self.tab}:{len(self.stack)}'
        spots, y, col = [], 0.0, None  # where each card or header goes, from the top of the list; col None: a new row starts
        for i, it in enumerate(items):
            if it.get('kind') == 'header':
                if col is not None: y += ch  # the row of cards above ends
                spots.append((i, x0, y)); y += hh; col = None
                continue
            if col is None or col >= COLS:
                if col is not None: y += ch
                col = 0
            spots.append((i, x0 + col * (cw + gap), y)); col += 1
        total = y + (ch if col is not None else 0)
        focus = self.focus.get(id(page))
        if self.pad and focus is not None:  # keep the focused card in view
            at = next((s[2] for s in spots if s[0] == focus), None)
            if at is not None:
                off = w.off.get(key, 0)
                if at - off < 0: w.off[key] = max(0, at - (hh if focus and items[focus - 1].get('kind') == 'header' else 0))
                elif at + ch - off > area.height(): w.off[key] = at + ch - area.height()
                w.maxoff[key] = max(0, total - area.height())

        def draw(top):
            for i, x, sy in spots:
                if top + sy > area.bottom() or top + sy + ch < area.y(): continue
                it = items[i]
                if it.get('kind') == 'header': w.text(p, it['title'], x, top + sy + 1.2 * u, ('u', 2.3, 700, -.01), TEXT, w.width() - 5.2 * u)
                else: self.card(p, it, QRectF(x, top + sy, cw, th), i, focus == i and self.pad)
            return top + total
        w.scroller(p, key, area, draw)

    def card(self, p, it, r, i, focused):
        w, u = self.w, self.w.u
        img = self.picture(it.get('thumb'), r.width(), r.height()) if it.get('thumb') else False
        path = QPainterPath(); path.addRoundedRect(r, 1.2 * u, 1.2 * u)
        p.save(); p.setClipPath(path)
        if img: p.drawImage(r.topLeft(), img)
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            hue = (sum(map(ord, it['title'])) * 37) % 360
            g.setColorAt(0, QColor.fromHsl(hue, 90, 52)); g.setColorAt(1, QColor.fromHsl((hue + 40) % 360, 80, 24))
            p.fillRect(r, g)
            if img is False or not it.get('thumb'): w.text(p, it['title'], r.x() + 1.6 * u, r.y() + r.height() / 2 - 2.6 * u, ('u', 2.4, 700, -.02), TEXT, r.width() - 3.2 * u, 1, 1.15, 2)
        if it.get('progress'):
            p.fillRect(QRectF(r.x(), r.bottom() - .55 * u, r.width(), .55 * u), QColor(255, 255, 255, 70))
            p.fillRect(QRectF(r.x(), r.bottom() - .55 * u, r.width() * min(1, it['progress']), .55 * u), self.accent)
        p.restore()
        if it.get('badge'):
            f = ('u', 1.5, 600)
            bw = w.width_of(it['badge'], f) + 1.4 * u
            b = QRectF(r.right() - bw - .8 * u, r.bottom() - 3.2 * u - (.6 * u if it.get('progress') else 0), bw, 2.5 * u)
            w.box(p, b, .5 * u, QColor(204, 0, 0, 230) if it['badge'] == 'LIVE' else QColor(0, 0, 0, 200))
            w.text(p, it['badge'], b.x(), b.y(), f, TEXT, b.width(), 1, 2.5 / 1.5)
        if it.get('watched'):
            c = QPointF(r.right() - 2.2 * u, r.y() + 2.2 * u)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(self.accent); p.drawEllipse(c, 1.3 * u, 1.3 * u)
            p.setPen(QPen(BG, .35 * u)); p.drawPolyline([QPointF(c.x() - .6 * u, c.y()), QPointF(c.x() - .1 * u, c.y() + .5 * u), QPointF(c.x() + .65 * u, c.y() - .45 * u)])
        if focused:
            p.setPen(QPen(TEXT, .4 * u)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-.5 * u, -.5 * u, .5 * u, .5 * u), 1.6 * u, 1.6 * u)
        th = w.text(p, it['title'], r.x(), r.bottom() + .9 * u, ('u', 1.95, 600), TEXT, r.width(), 0, 1.22, 2)
        if it.get('sub'): w.text(p, it['sub'], r.x(), r.bottom() + 1.2 * u + th, ('u', 1.6, 400), DIM, r.width())
        w.hit(QRectF(r.x(), r.y(), r.width(), r.height() + 7.8 * u), self.tap(lambda: self.activate(i)), name='card:' + it['title'])
        if it.get('kind') == 'video':  # "later": the queue, by touch
            plus = QRectF(r.x() + .8 * u, r.y() + .8 * u, 4 * u, 4 * u)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, 0, 0, 150)); p.drawEllipse(plus)
            p.setPen(QPen(TEXT, .3 * u)); c = plus.center()
            p.drawLine(QPointF(c.x() - .9 * u, c.y()), QPointF(c.x() + .9 * u, c.y())); p.drawLine(QPointF(c.x(), c.y() - .9 * u), QPointF(c.x(), c.y() + .9 * u))
            w.hit(plus.adjusted(-.8 * u, -.8 * u, .8 * u, .8 * u), self.tap(lambda: self.enqueue(it)), name='queue:' + it['title'])

    def picture(self, url, width, height):
        width, height = int(width), int(height)
        if hasattr(self.src, 'thumb'): url = self.src.thumb(url, width, height)
        return self.pics.get(url, width, height)

    def login(self, p, body, page):
        w, u = self.w, self.w.u
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        y = body.y() + 6 * u
        w.text(p, page['title'], x0, y, ('u', 3.4, 700, -.02), TEXT, cw, 1)
        w.text(p, 'plex.tv/link', x0, y + 6 * u, ('u', 2.6, 600), self.accent, cw, 1)
        code = page['code']
        box = QRectF(w.width() / 2 - 30 * u, y + 12 * u, 60 * u, 16 * u)
        w.box(p, box, 2 * u, CARD, QColor(255, 255, 255, 30))
        w.text(p, ' '.join(code), box.x(), box.y(), ('u', 8, 700, .05), TEXT, box.width(), 1, 16 / 8)
        w.text(p, page['note'], x0 + 8 * u, y + 32 * u, ('u', 2.2, 500), DIM, cw - 16 * u, 1, 1.4, None)

    # -- now playing --
    def player(self, p, body):
        w, u, it = self.w, self.w.u, self.now
        if not it: return w.text(p, 'Gerade läuft nichts.', 0, body.y() + 12 * u, ('u', 2.4, 500), DIM, w.width(), 1)
        props = self.mpv.props if self.mpv else {}
        x0, cw, y = 2.6 * u, w.width() - 5.2 * u, body.y() + .6 * u
        r = QRectF(x0, y, 34 * u, 34 * u * 9 / 16)
        img = self.picture(it.get('thumb'), r.width(), r.height()) if it.get('thumb') else None
        path = QPainterPath(); path.addRoundedRect(r, 1.4 * u, 1.4 * u)
        p.save(); p.setClipPath(path)
        p.drawImage(r.topLeft(), img) if img else p.fillRect(r, CARD)
        p.restore()
        tx = r.right() + 2.4 * u
        th = w.text(p, it['title'], tx, y + .4 * u, ('u', 3.0, 700, -.02), TEXT, x0 + cw - tx, 0, 1.18, 3)
        if it.get('sub'): w.text(p, it['sub'], tx, y + .8 * u + th, ('u', 2.0, 500), DIM, x0 + cw - tx, 0, 1.3, 2)
        state = self.busy or ('Puffert …' if props.get('paused-for-cache') else 'Pausiert' if props.get('pause') else 'Läuft oben')
        w.text(p, state, tx, r.bottom() - 2.6 * u, ('u', 1.8, 600), self.accent if not self.busy else DIM, x0 + cw - tx)
        # seek bar: drag anywhere on it
        pos, dur = props.get('time-pos') or 0, props.get('duration') or it.get('dur') or 0
        y = r.bottom() + 3.2 * u
        track = QRectF(x0, y + 2 * u, cw, .8 * u)
        w.capsule(p, track, RAISED)
        k = max(0.0, min(1.0, pos / dur)) if dur else 0
        if k: w.capsule(p, QRectF(track.x(), track.y(), max(track.height(), track.width() * k), track.height()), self.accent)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(TEXT); p.drawEllipse(QPointF(track.x() + track.width() * k, track.center().y()), 1.3 * u, 1.3 * u)
        w.text(p, clock(pos), x0, y + 3.6 * u, ('u', 1.8, 500), DIM)
        w.text(p, clock(dur) if dur else '', x0, y + 3.6 * u, ('u', 1.8, 500), DIM, cw, 2)
        if dur: w.hit(QRectF(x0, y - u, cw, 6 * u), lambda x: self.seek(max(0.0, min(1.0, (x - x0) / cw)) * dur, 'absolute+keyframes'), drag=True, name='seek')
        # transport
        y += 8 * u
        mid = w.width() / 2
        for dx, d, name, fn in ((-30, 8, '−10', lambda: self.seek(-10)), (-16, 8, 'prev', lambda: self.seek(0, 'absolute')), (0, 11, 'pause' if not props.get('pause') else 'play', self.toggle),
                                (16, 8, 'next', lambda: self.next() if self.queue else self.say('Die Warteschlange ist leer.')), (30, 8, '+30', lambda: self.seek(30))):
            c = QPointF(mid + dx * u, y + 5.5 * u)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(TEXT if d == 11 else RAISED); p.drawEllipse(c, d * u / 2, d * u / 2)
            if name[0] in '+−': w.text(p, name, c.x() - 4 * u, c.y() - 1.4 * u, ('u', 2.1, 700), TEXT, 8 * u, 1, 2.8 / 2.1)
            else: self.glyph(p, name, c, (2.2 if d == 11 else 1.5) * u, BG if d == 11 else TEXT)
            w.hit(QRectF(c.x() - d * u / 2, c.y() - d * u / 2, d * u, d * u), self.tap(fn), name=name)
        y += 13.5 * u
        # subtitles, audio, volume
        tl = props.get('track-list') or []
        subs, audio = tracks(tl, 'sub'), tracks(tl, 'audio')
        y = self.chips(p, y, 'Untertitel', [('no', 'Aus', not any(s[2] for s in subs))] + subs, lambda tid: self.mpv.command('set_property', 'sid', tid))
        if len(audio) > 1: y = self.chips(p, y, 'Tonspur', audio, lambda tid: self.mpv.command('set_property', 'aid', tid))
        vol = w.SET.get('vol')
        if vol is not None:
            w.text(p, 'Lautstärke', x0, y, ('u', 1.8, 600), DIM, 16 * u, lh=4.6 / 1.8)
            track = QRectF(x0 + 17 * u, y + 1.9 * u, cw - 17 * u - 7 * u, .8 * u)
            w.capsule(p, track, RAISED)
            if vol: w.capsule(p, QRectF(track.x(), track.y(), max(track.height(), track.width() * vol / 100), track.height()), TEXT)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(TEXT); p.drawEllipse(QPointF(track.x() + track.width() * vol / 100, track.center().y()), 1.3 * u, 1.3 * u)
            w.text(p, str(vol), track.right() + u, y, ('u', 2.0, 600), TEXT, 6 * u, 2, 4.6 / 2.0)
            w.hit(QRectF(track.x() - u, y - .6 * u, track.width() + 2 * u, 5.8 * u), lambda x: w.set_value('vol', x, track.x(), track.width()), drag=True, name='vol')
            y += 6.4 * u
        acts = [(label, fn) for label, fn in self.src.actions(it)] + [('Stopp', self.stop)]
        bw = (cw - (len(acts) - 1) * 1.2 * u) / len(acts)
        for n, (label, fn) in enumerate(acts):
            rect = QRectF(x0 + n * (bw + 1.2 * u), y + .4 * u, bw, 5.6 * u)
            w.capsule(p, rect, CARD, QColor(255, 255, 255, 26))
            w.text(p, label, rect.x(), rect.y(), ('u', 2.0, 600), TEXT, rect.width(), 1, 5.6 / 2.0)
            w.hit(rect, self.tap(lambda fn=fn: self.said_from(fn)), name=label)

    def said_from(self, fn):
        text = fn()
        if text: self.say(text)

    def stop(self):
        self.report('stopped')
        if self.mpv: self.mpv.command('stop')
        self.queue, self.now = [], None
        self.next()

    def chips(self, p, y, title, options, choose):
        """One row of choices (subtitles, audio tracks); returns the y below."""
        w, u = self.w, self.w.u
        x0, end = 2.6 * u + 17 * u, w.width() - 2.6 * u
        w.text(p, title, 2.6 * u, y, ('u', 1.8, 600), DIM, 16 * u, lh=4.6 / 1.8)
        x, f = x0, ('u', 1.85, 500)
        if len(options) == 1: w.text(p, 'keine', x, y, f, FAINT, lh=4.6 / 1.85)
        for tid, label, on in options:
            cwid = min(w.width_of(label, f) + 3 * u, 30 * u)
            if x + cwid > end: break
            rect = QRectF(x, y, cwid, 4.6 * u)
            w.capsule(p, rect, TEXT if on else RAISED)
            w.text(p, label, rect.x() + 1.5 * u, rect.y(), f, BG if on else TEXT, cwid - 3 * u, lh=4.6 / 1.85)
            w.hit(rect, self.tap(lambda tid=tid: choose(tid)), name=f'{title}:{label}')
            x += cwid + .8 * u
        return y + 6.2 * u

    # -- queue and the bar at the bottom --
    def waiting(self, p, body):
        w, u = self.w, self.w.u
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        y = body.y()
        w.text(p, f'{len(self.queue)} als Nächstes', x0, y, ('u', 2.4, 700), TEXT, lh=5 / 2.4)
        rect = QRectF(x0 + cw - 14 * u, y, 14 * u, 5 * u)
        w.capsule(p, rect, RAISED)
        w.text(p, 'Leeren', rect.x(), rect.y(), ('u', 2.0, 600), TEXT, rect.width(), 1, 5 / 2.0)
        w.hit(rect, self.tap(self.clear_queue), name='Leeren')
        area = QRectF(0, y + 6.6 * u, w.width(), body.bottom() - y - 6.6 * u)

        def draw(top):
            yy = top
            for n, it in enumerate(self.queue):
                r = QRectF(x0, yy, 16 * u, 9 * u)
                img = self.picture(it.get('thumb'), r.width(), r.height()) if it.get('thumb') else None
                path = QPainterPath(); path.addRoundedRect(r, u, u)
                p.save(); p.setClipPath(path); p.drawImage(r.topLeft(), img) if img else p.fillRect(r, CARD); p.restore()
                w.text(p, it['title'], r.right() + 2 * u, yy + 1.4 * u, ('u', 2.0, 600), TEXT, cw - 26 * u)
                w.text(p, it.get('sub') or '', r.right() + 2 * u, yy + 4.6 * u, ('u', 1.7, 400), DIM, cw - 26 * u)
                w.hit(QRectF(x0, yy, cw - 8 * u, 9 * u), self.tap(lambda n=n: self.play(self.queue.pop(n))), name='q:' + it['title'])
                x = QRectF(x0 + cw - 6 * u, yy + 2 * u, 5 * u, 5 * u)
                w.capsule(p, x, RAISED)
                w.text(p, '×', x.x(), x.y(), ('u', 2.6, 500), TEXT, x.width(), 1, 5 / 2.6)
                w.hit(x, self.tap(lambda n=n: self.queue.pop(n)), name='qx:' + it['title'])
                yy += 10.4 * u
            return yy
        w.scroller(p, 'media:queue', area, draw)

    def clear_queue(self):
        self.queue = []
        self.open_tab('Läuft' if self.now else self.src.tabs[0])

    def mini(self, p, r):
        w, u, it = self.w, self.w.u, self.now
        props = self.mpv.props if self.mpv else {}
        w.box(p, r, 1.6 * u, RAISED)
        t = QRectF(r.x() + u, r.y() + u, (r.height() - 2 * u) * 16 / 9, r.height() - 2 * u)
        img = self.picture(it.get('thumb'), t.width(), t.height()) if it.get('thumb') else None
        path = QPainterPath(); path.addRoundedRect(t, .8 * u, .8 * u)
        p.save(); p.setClipPath(path); p.drawImage(t.topLeft(), img) if img else p.fillRect(t, CARD); p.restore()
        tx = t.right() + 1.6 * u
        w.text(p, it['title'], tx, r.y() + 1.6 * u, ('u', 2.0, 600), TEXT, r.right() - 10 * u - tx)
        w.text(p, self.busy or f'{clock(props.get("time-pos"))} / {clock(props.get("duration"))}', tx, r.y() + 5 * u, ('u', 1.7, 500), DIM, r.right() - 10 * u - tx)
        dur = props.get('duration')
        if dur and props.get('time-pos'):
            p.fillRect(QRectF(r.x() + 1.6 * u, r.bottom() - .45 * u, (r.width() - 3.2 * u) * min(1, props['time-pos'] / dur), .45 * u), self.accent)
        w.hit(QRectF(r.x(), r.y(), r.width() - 9 * u, r.height()), self.tap(lambda: self.open_tab('Läuft')), name='mini')
        c = QPointF(r.right() - 5 * u, r.center().y())
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(TEXT); p.drawEllipse(c, 3.3 * u, 3.3 * u)
        self.glyph(p, 'play' if props.get('pause') else 'pause', c, 1.4 * u, BG)
        w.hit(QRectF(c.x() - 4 * u, r.y(), 8 * u, r.height()), self.tap(self.toggle), name='mini:pause')

    def toast(self, p):
        w, u = self.w, self.w.u
        f = ('u', 2.0, 600)
        tw = min(w.width_of(self.said, f) + 5 * u, w.width() - 8 * u)
        r = QRectF((w.width() - tw) / 2, w.height() - (15.5 if self.now and self.tab != 'Läuft' else 9) * u, tw, 5.4 * u)
        w.capsule(p, r, QColor(255, 255, 255, 235))
        w.text(p, self.said, r.x() + 2.5 * u, r.y(), f, BG, tw - 5 * u, lh=5.4 / 2.0)
