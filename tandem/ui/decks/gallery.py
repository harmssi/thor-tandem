"""Aufnahmen (Fotos & Videos): Tandem's dual-screen gallery for ~/Pictures/Tandem and ~/Videos/Tandem (plus SD card).
mpv shows the selected photo or plays the selected video on the top screen; the bottom screen browses thumbnails, switches
between the top and bottom capture (-oben / -unten), controls playback, and deletes captures with two-tap confirmation."""
import glob, os, re, shutil, subprocess, threading, time
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QImageReader, QPainterPath, QPen

from decks.mpv import Mpv

HOME = Path.home()
CACHE = Path(os.environ.get('XDG_CACHE_HOME', HOME / '.cache')) / 'tandem/gallery'
SOCKET = f'/tmp/tandem-mpv-{os.getuid()}.sock'
TABS = ['Alle', 'Fotos', 'Videos']
COLS = 3
STAMP_RE = re.compile(r'^(\d{8}-\d{6})-(oben|unten)\.(png|jpg|mp4|mkv)$', re.I)


def fmt_stamp(stamp):
    if len(stamp) == 15 and stamp[8] == '-':
        return f'{stamp[6:8]}.{stamp[4:6]}.{stamp[0:4]} · {stamp[9:11]}:{stamp[11:13]}'
    return stamp


def fmt_size(n):
    return f'{n / (1 << 20):.0f} MB' if n >= 2 << 20 else f'{max(1, round(n / 1024))} KB'


def fmt_dur(secs):
    if secs is None: return '0:00'
    s = max(0, int(secs))
    return f'{s // 60}:{s % 60:02d}'


def media_roots():
    """All Pictures/Tandem and Videos/Tandem folders on the device and any mounted SD card."""
    roots = [HOME / 'Pictures/Tandem', HOME / 'Videos/Tandem']
    for pat in ('/run/media/*/*', '/media/*/*'):
        for card in sorted(glob.glob(pat)):
            roots += [Path(card) / 'Pictures/Tandem', Path(card) / 'Videos/Tandem']
    seen, out = set(), []
    for r in roots:
        try: rp = r.resolve()
        except OSError: continue
        if rp not in seen and r.is_dir():
            seen.add(rp); out.append(r)
    return out


def scan_items(roots=None):
    """Group <stamp>-oben / <stamp>-unten pairs into sorted gallery items (newest first)."""
    grouped = {}
    for folder in (roots if roots is not None else media_roots()):
        try: entries = list(Path(folder).iterdir())
        except OSError: continue
        for f in entries:
            if not f.is_file() or f.name.endswith('.v.mp4'): continue
            m = STAMP_RE.match(f.name)
            if m:
                stamp, side, ext = m[1], m[2].lower(), m[3].lower()
                kind = 'video' if ext in ('mp4', 'mkv') else 'photo'
                key = (kind, stamp)
            else:
                ext = f.suffix.lower().lstrip('.')
                if ext not in ('png', 'jpg', 'mp4', 'mkv'): continue
                kind = 'video' if ext in ('mp4', 'mkv') else 'photo'
                stamp, side, key = f.stem, 'oben', (kind, f.name)
            it = grouped.setdefault(key, {'id': f'{kind}:{stamp}', 'kind': kind, 'stamp': stamp, 'title': fmt_stamp(stamp),
                                          'oben': None, 'unten': None, 'size': 0, 'mtime': 0.0})
            try:
                st = f.stat()
                it['size'] += st.st_size
                it['mtime'] = max(it['mtime'], st.st_mtime)
            except OSError: pass
            it[side] = str(f)
    items = list(grouped.values())
    items.sort(key=lambda x: (x['mtime'], x['stamp']), reverse=True)
    return items


class Thumbs:
    """Decodes photo thumbnails or extracts one video frame with ffmpeg in the background."""

    def __init__(self, ready):
        self.ready, self.cache, self.todo, self.lock, self.sem = ready, OrderedDict(), [], threading.Lock(), threading.Semaphore(0)
        self.alive = True
        CACHE.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self.work, daemon=True).start()

    def get(self, item, w, h):
        key = (item['id'], int(w), int(h))
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            self.cache[key] = None
            self.todo.append((key, dict(item)))
            while len(self.cache) > 60: self.cache.popitem(last=False)
        self.sem.release()
        return None

    def work(self):
        while self.alive:
            self.sem.acquire()
            if not self.alive: return
            with self.lock:
                if not self.todo: continue
                key, item = self.todo.pop()
            src = item.get('oben') or item.get('unten')
            img = False
            if src:
                pic_path = src
                if item['kind'] == 'video':
                    thumb = CACHE / f'{item["stamp"]}.jpg'
                    if not thumb.is_file() and shutil.which('ffmpeg'):
                        for seek_t in ('2.0', '0.1'):
                            try:
                                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', seek_t, '-i', src, '-frames:v', '1',
                                                '-vf', 'scale=384:-1', str(thumb)], capture_output=True, timeout=8)
                            except (OSError, subprocess.SubprocessError): pass
                            if thumb.is_file() and thumb.stat().st_size > 0: break
                    pic_path = str(thumb) if thumb.is_file() else ''
                if pic_path:
                    reader = QImageReader(pic_path)
                    sz = reader.size()
                    w, h = key[1], key[2]
                    if sz.isValid() and sz.width() and sz.height():
                        k = max(w / sz.width(), h / sz.height())
                        reader.setScaledSize(QSize(max(w, round(sz.width() * k)), max(h, round(sz.height() * k))))
                    raw = reader.read()
                    if not raw.isNull():
                        img = raw.copy((raw.width() - w) // 2, (raw.height() - h) // 2, w, h).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            with self.lock:
                self.cache[key] = img
            if self.alive: self.ready.emit()

    def close(self):
        self.alive = False
        self.sem.release()


class Deck:
    def __init__(self, win, sock_path=None, roots=None):
        self.w, self.roots = win, roots
        self.tab, self.i, self.screen_side = 0, 0, 'oben'
        self.armed_id, self.armed_at = '', 0.0
        self.shown_path = ''
        self.all_items = scan_items(roots)
        self.thumbs = Thumbs(win.loaded)
        self.mpv = Mpv(sock_path or SOCKET, self.on_mpv)

    def on_mpv(self, m):
        if m.get('event') == 'connected':
            self.shown_path = ''
            self.sync_top()
        self.w.loaded.emit()

    def filtered(self):
        if self.tab == 1: return [x for x in self.all_items if x['kind'] == 'photo']
        if self.tab == 2: return [x for x in self.all_items if x['kind'] == 'video']
        return self.all_items

    def current(self):
        items = self.filtered()
        if not items: return None
        self.i = max(0, min(self.i, len(items) - 1))
        return items[self.i]

    def sync_top(self):
        it = self.current()
        if not it or not self.mpv.sock: return
        path = it.get(self.screen_side) or it.get('oben') or it.get('unten')
        if not path or path == self.shown_path: return
        self.shown_path = path
        self.mpv.command('loadfile', path, 'replace')
        self.mpv.command('set_property', 'pause', False)

    def refresh(self):
        self.all_items = scan_items(self.roots)
        self.shown_path = ''
        self.sync_top()
        self.w.update()

    def select(self, idx):
        items = self.filtered()
        if not items: return
        self.i = max(0, min(idx, len(items) - 1))
        self.armed_id = ''
        self.sync_top()
        self.w.update()

    def flip_side(self):
        it = self.current()
        if not it or not (it.get('oben') and it.get('unten')): return
        self.screen_side = 'unten' if self.screen_side == 'oben' else 'oben'
        self.shown_path = ''
        self.sync_top()
        self.w.update()

    def toggle_play(self):
        it = self.current()
        if not it: return
        if it['kind'] == 'photo': return self.flip_side()
        paused = bool(self.mpv.props.get('pause'))
        if self.mpv.props.get('eof-reached'):
            self.mpv.command('seek', 0, 'absolute')
            paused = True
        self.mpv.command('set_property', 'pause', not paused)
        self.w.update()

    def seek(self, delta):
        self.mpv.command('seek', delta, 'relative')

    def delete_current(self):
        it = self.current()
        if not it: return
        now = time.time()
        if self.armed_id != it['id'] or now - self.armed_at > 4:
            self.armed_id, self.armed_at = it['id'], now
            self.w.update()
            return
        for side in ('oben', 'unten'):
            if it.get(side):
                try: Path(it[side]).unlink(missing_ok=True)
                except OSError: pass
        (CACHE / f'{it["stamp"]}.jpg').unlink(missing_ok=True)
        self.armed_id = ''
        self.w.toast('Aufnahme gelöscht.')
        self.refresh()

    def key(self, a):
        items = self.filtered()
        n = len(items)
        if a in ('prev', 'next'):
            self.tab = (self.tab + (1 if a == 'next' else len(TABS) - 1)) % len(TABS)
            self.i, self.armed_id = 0, ''
            self.sync_top()
        elif a == 'left' and n: self.select(self.i - 1)
        elif a == 'right' and n: self.select(self.i + 1)
        elif a == 'up' and self.i >= COLS: self.select(self.i - COLS)
        elif a == 'down' and self.i + COLS < n: self.select(self.i + COLS)
        elif a == 'ok': self.toggle_play()
        elif a == 'close': self.flip_side()
        elif a == 'fav': self.delete_current()
        elif a == 'back':
            if self.armed_id: self.armed_id = ''; self.w.update()
            else: self.w.post('api/quit')

    def paint(self, p):
        w = self.w
        u, W, H = w.u, w.width(), w.height()
        from tandem_ui import FOCUS, INK, LIVE, MUTED, ON_ART, PANEL, RAISED, TEXT, WARN, faded, rgba
        p.fillRect(0, 0, W, H, INK)
        x0, cw = 2.6 * u, W - 5.2 * u
        # Top tab bar: Alle · Fotos · Videos  +  Neu laden · Schließen
        y, th = 2.4 * u, 5.2 * u
        tx = x0
        f_tab = ('u', 2.0, 600)
        for idx, label in enumerate(TABS):
            tw = w.width_of(label, f_tab) + 3.4 * u
            rect = QRectF(tx, y, tw, th)
            on = idx == self.tab
            w.capsule(p, rect, FOCUS if on else PANEL)
            w.text(p, label, tx, y, f_tab, INK if on else TEXT, tw, 1, th / (2.0 * u))
            w.hit(rect, lambda idx=idx: (setattr(self, 'tab', idx), self.select(0)), name='gal:' + label)
            tx += tw + .9 * u
        right = W - 2.6 * u
        for label, fn in (('Schließen', lambda: w.post('api/quit')), ('Neu laden', self.refresh)):
            bw = w.width_of(label, f_tab) + 3.4 * u
            right -= bw
            r = QRectF(right, y, bw, th)
            w.capsule(p, r, RAISED)
            w.text(p, label, right, y, f_tab, TEXT, bw, 1, th / (2.0 * u))
            w.hit(r, fn, name=label)
            right -= .9 * u
        y += th + 2.0 * u
        items = self.filtered()
        it = self.current()
        self.sync_top()
        if not items:
            w.text(p, 'Noch keine Aufnahmen vorhanden. Mache im Spiel über das Schnellmenü ein Bildschirmfoto oder starte eine Videoaufnahme.',
                   x0 + u, y + 6 * u, ('u', 2.2), MUTED, cw - 2 * u, lh=1.5, lines=None)
            return True
        bar_h = (13.4 if it and it['kind'] == 'video' else 7.6) * u
        grid_bottom = H - 2.4 * u - bar_h - 1.6 * u
        gap = 1.6 * u
        card_w = (cw - (COLS - 1) * gap) / COLS
        card_h = card_w * 9 / 16 + 4.4 * u
        area = QRectF(x0 - .8 * u, y - .8 * u, cw + 1.6 * u, grid_bottom - y + 1.6 * u)
        # Keep selected card scrolled into view
        seen = (self.tab, self.i, len(items))
        if getattr(self, '_seen', None) != seen:
            top_row = (self.i // COLS) * (card_h + gap)
            total_h = ((len(items) + COLS - 1) // COLS) * (card_h + gap) - gap
            w.maxoff['gal'] = max(0, total_h - area.height())
            w.off['gal'] = max(min(w.off.get('gal', 0), top_row), top_row + card_h - area.height())
            self._seen = seen

        def draw_grid(gy):
            for idx, entry in enumerate(items):
                col, row = idx % COLS, idx // COLS
                rx, ry = x0 + col * (card_w + gap), gy + .8 * u + row * (card_h + gap)
                rect = QRectF(rx, ry, card_w, card_h)
                if rect.bottom() < area.top() or rect.top() > area.bottom(): continue
                sel = idx == self.i
                w.box(p, rect, 1.4 * u, RAISED if sel else PANEL, FOCUS if sel else rgba(255, 255, 255, .08), (.28 * u) if sel else 1.0)
                pic_h = card_w * 9 / 16
                pic_r = QRectF(rx, ry, card_w, pic_h)
                img = self.thumbs.get(entry, round(card_w), round(pic_h))
                if img:
                    clip = QPainterPath()
                    clip.addRoundedRect(pic_r, 1.4 * u, 1.4 * u)
                    p.save(); p.setClipPath(clip, Qt.ClipOperation.IntersectClip); p.drawImage(pic_r.topLeft(), img); p.restore()
                badge = ('Video' if entry['kind'] == 'video' else 'Foto') + ' · ' + fmt_size(entry['size'])
                bf = ('u', 1.35, 700)
                bw = w.width_of(badge, bf) + 1.6 * u
                w.capsule(p, QRectF(pic_r.right() - .8 * u - bw, pic_r.y() + .8 * u, bw, 2.3 * u), rgba(0, 0, 0, .68))
                w.text(p, badge, pic_r.right() - .8 * u - bw, pic_r.y() + .8 * u, bf, ON_ART, bw, 1, 2.3 / 1.35)
                w.text(p, entry['title'], rx + 1.1 * u, pic_r.bottom() + .8 * u, ('u', 1.65, 600 if sel else 500), TEXT if sel else MUTED, card_w - 2.2 * u)
                w.hit(rect, lambda idx=idx: self.select(idx), name='item:' + entry['stamp'])
            return gy + .8 * u + ((len(items) + COLS - 1) // COLS) * (card_h + gap) - gap + .8 * u

        w.scroller(p, 'gal', area, draw_grid)
        # Bottom control bar for the currently viewed capture
        by = H - 2.4 * u - bar_h
        w.box(p, QRectF(x0, by, cw, bar_h), 1.8 * u, PANEL, rgba(255, 255, 255, .08))
        cy = by + 1.2 * u
        if it['kind'] == 'video':
            pos, dur = self.mpv.props.get('time-pos') or 0.0, self.mpv.props.get('duration') or 0.0
            w.text(p, fmt_dur(pos), x0 + 1.8 * u, cy, ('u', 1.8, 600), MUTED, 8 * u)
            bar_x, bar_w = x0 + 10 * u, cw - 20 * u
            track = QRectF(bar_x, cy + 1.4 * u, bar_w, 1.2 * u)
            w.capsule(p, track, faded(TEXT, .14))
            if dur > 0:
                part = max(0.0, min(1.0, pos / dur))
                w.capsule(p, QRectF(bar_x, track.y(), max(track.height(), bar_w * part), track.height()), FOCUS)
            w.hit(QRectF(bar_x, cy, bar_w, 4.2 * u), lambda x: dur > 0 and self.mpv.command('seek', max(0.0, min(1.0, (x - bar_x) / bar_w)) * dur, 'absolute'), True, 'gal:seek')
            w.text(p, fmt_dur(dur), x0 + cw - 9.8 * u, cy, ('u', 1.8, 600), MUTED, 8 * u, 2)
            cy += 5.4 * u
        both = bool(it.get('oben') and it.get('unten'))
        armed = self.armed_id == it['id'] and time.time() - self.armed_at <= 4
        paused = bool(self.mpv.props.get('pause')) or bool(self.mpv.props.get('eof-reached'))
        btns = []
        if it['kind'] == 'video':
            btns += [('Abspielen' if paused else 'Pause', self.toggle_play, LIVE if not paused else RAISED, INK if not paused else TEXT),
                     ('−10 s', lambda: self.seek(-10), RAISED, TEXT),
                     ('+10 s', lambda: self.seek(10), RAISED, TEXT)]
        if both:
            side_lbl = 'Bild: Unten' if self.screen_side == 'unten' else 'Bild: Oben'
            btns.append((side_lbl, self.flip_side, FOCUS if self.screen_side == 'unten' else RAISED, INK if self.screen_side == 'unten' else TEXT))
        btns.append(('Nochmal tippen' if armed else 'Löschen', self.delete_current, WARN if armed else faded(WARN, .16), INK if armed else WARN))
        bh = 5.2 * u
        bw = (cw - 3.2 * u - (len(btns) - 1) * 1.0 * u) / len(btns)
        bx = x0 + 1.6 * u
        for lbl, fn, bg, fg in btns:
            w.button(p, QRectF(bx, cy, bw, bh), lbl, fn, ('u', 1.95, 600), fg, bg, None, 1.1)
            bx += bw + 1.0 * u
        return True

    def close(self):
        self.thumbs.close()
        self.mpv.close()
