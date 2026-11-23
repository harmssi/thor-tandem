"""Companion packs for emulated games on the bottom screen (the format of gba-duo-wide: manifest.json, layout.json,
style.css, main.lua, assets/). The service names the pack that matches the running ROM (run['pack'], a folder in
~/.config/tandem/packs); this deck runs it while the game runs and lets go of everything afterwards.

Who does what:
  packlua  – the pack's Lua in a sandbox (liblua 5.4 through ctypes), with limits
  packmem  – the game's memory from RetroArch (UDP, read only, whole pages, batched per tick) and gfx.* pictures
  packcss  – layout.json + CSS as boxes, laid out and painted with QPainter
One worker thread asks RetroArch and runs the script (so a slow answer or a slow script never holds the window); the
window's own thread only applies finished snapshots and paints. No second process: that would cost another Python
(about 10 MB) for something the hook in packlua already stops – a script that runs too long.
"""
import json, os, sys, threading, time
from collections import deque
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QTransform

from decks import packcss, packlua, packmem

PACKS = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'tandem/packs'
FORMAT = 4  # manifest.json formatVersion this understands (4: gameScript – game.lua runs in the wide core, see README)


class Deck:
    ADDR = ('127.0.0.1', 55355)  # RetroArch's network commands; the self-check points this at a stand-in
    W, H = 538.0, 468.0  # the companion screen the packs are drawn for: the Thor's bottom screen under Android, in dp

    def __init__(self, window):
        self.w, run = window, window.RUN
        self.dir = PACKS / run['pack']
        if self.dir.parent != PACKS or not self.dir.is_dir(): raise ValueError('Begleiter-Paket fehlt')
        m = self.manifest = json.loads((self.dir / 'manifest.json').read_text(encoding='utf-8'))
        if not 1 <= int(m.get('formatVersion', -1)) <= FORMAT: raise ValueError(f'formatVersion {m.get("formatVersion")} wird nicht unterstützt')
        layout = json.loads(self.inside(m.get('layout', 'layout.json')).read_text(encoding='utf-8'))
        styles = [(self.inside(name).read_text(encoding='utf-8'), str(self.inside(name).parent)) for name in m.get('styles') or []]
        self.script = self.inside(m['script']).read_text(encoding='utf-8') if m.get('script') else ''
        self.mem = packmem.Memory(run['s'], self.ADDR)
        self.gfx = packmem.Gfx(self.mem)
        self.tree = packcss.Tree(layout, styles, str(self.dir), self.gfx.image, self.W, self.H)
        self.tree.on_ui, self.tree.on_call = self.ui_changed, self.called
        self.tree.update({})  # nothing shows before the first values: every visibleIf is off
        self.ui, self.fresh, self.todo, self.calls = dict(self.tree.ui), deque(maxlen=1), deque(), deque()
        self.period = 1 / max(1, min(30, int(m.get('tickHz', 4))))
        self.memo = window.memo.setdefault('pack', {})
        default_tab = 'Cover' if run.get('pack_mode') == 'art' else 'Begleiter'
        self.tab = self.memo.get(run['pack'], default_tab)
        self.ready, self.failed, self.error, self.log, self.told, self.region_told, self.pressed, self.xf = False, None, None, deque(maxlen=20), False, False, None, QTransform()
        self.snap = self.shown = None  # the script's last values, and what the tree was last given (with the wide switch)
        self.alive, self.wake = True, threading.Event()
        self.thread = threading.Thread(target=self.work, daemon=True)
        self.thread.start()

    def inside(self, name):
        """A file of the pack; nothing outside its folder."""
        path = (self.dir / str(name)).resolve()
        if self.dir.resolve() not in path.parents: raise ValueError(f'{name} liegt nicht im Paket')
        return path

    def close(self):
        self.alive = False
        self.wake.set()
        self.thread.join(1.5)  # the worker closes Lua and the socket itself
        self.tree.close()
        self.gfx.images = {}
        self.tree.on_ui = self.tree.on_call = self.tree.root = self.pressed = None  # cut the circles: the tree's nodes go at once

    # ---- worker: RetroArch and the script ------------------------------------------------------------------------------
    def source(self, name):
        try: return self.inside(name.decode() + '.lua').read_bytes()
        except (OSError, ValueError): return None

    def picture(self, kind, text): return self.gfx.call(kind.decode(), text)

    def note(self, text):
        text = text.decode('utf-8', 'replace') if isinstance(text, bytes) else str(text)
        if text != self.error: print(f'Begleiter {self.dir.name}: {text}', file=sys.stderr, flush=True)
        self.error = text
        self.log.append(text)

    def work(self):
        lua = None
        try:
            while self.alive:  # the game is up when RetroArch says so
                state = self.mem.status()
                if state and state['state'] in ('PLAYING', 'PAUSED'): break
                self.wake.wait(0.5)
            if not self.alive: return
            lua = packlua.Lua(self.mem.u, self.mem.read, self.picture, self.gfx.lz77, self.note, self.source, None if self.mem.gba else self.mem.bank8)
            self.mem.begin()
            ok, why = lua.call('load', self.script, '=' + str(self.manifest.get('script', 'main.lua')))
            if not ok:
                self.failed = why
                return self.w.loaded.emit()
            last = None
            while self.alive:
                start = time.monotonic()
                if self.tab == 'Begleiter' and self.mem.begin():
                    acted = False
                    while self.calls:
                        name, args = self.calls.popleft()
                        ok, text = lua.call('action', name, packlua.literal([a if isinstance(a, (str, int, float, bool)) else None for a in args[:16]]))
                        acted = True
                        if not ok: self.note(text)
                        elif text != 'null': self.todo.append(json.loads(text))
                    ok, text = lua.call('update', packlua.literal(self.ui))
                    if not ok: self.note(text)  # the screen keeps its last state
                    elif text != last or acted or not self.ready:
                        last, self.ready = text, True
                        self.fresh.append(json.loads(text))
                        self.w.loaded.emit()
                self.wake.wait(max(0.02, self.period - (time.monotonic() - start)))
                self.wake.clear()
        except Exception as error:  # a broken pack must not take the window with it
            self.failed = f'{type(error).__name__}: {error}'
            self.w.loaded.emit()
        finally:
            if lua: lua.close()
            self.mem.close()

    # ---- window thread -------------------------------------------------------------------------------------------------

    def ui_changed(self, ui):
        self.ui = ui
        self.wake.set()  # a tap shows at once: update(ui) runs now, not at the next tick

    def called(self, name, args):
        if name == 'wideView':  # reserved: the player's switch for game.lua's wide view; the service flips it (RUN['wide'])
            if self.w.RUN.get('wide') is not None: self.w.post('api/wide', {'on': str(args[0]) if args else 'toggle'})
            return
        self.calls.append((name, args))
        self.wake.set()

    def press(self, pos):
        """A finger went down (pos) or up (None): the widget under it matches :pressed meanwhile."""
        node = next((n for rect, n in reversed(self.tree.clicks) if pos is not None and self.xf.mapRect(rect).contains(pos)), None) if self.tab == 'Begleiter' else None
        if node is self.pressed: return
        if self.pressed is not None: self.tree.press(self.pressed, False)
        if node is not None: self.tree.press(node, True)
        self.pressed = node
        self.w.update()

    def choose(self, tab):
        self.tab = self.memo[self.w.RUN['pack']] = tab
        self.wake.set()

    def _paint_cover_art(self, p, ui, top):
        """GBADuo v1.0.1 Cover-Art companion screen mode: full-aspect uncropped box/cover over a soft ambient glow."""
        import math
        w, u, W, H = self.w, self.w.u, self.w.width(), self.w.height()
        gm = next((g for g in (w.L.get('games') or []) if g.get('id') == w.RUN.get('id')), None) or w.RUN
        art_key = gm.get('box') or gm.get('cover') or gm.get('hero')
        avail_h = H - top - 3.6 * u
        avail_w = W - 8.0 * u
        imgs = getattr(w, 'saver_imgs', None) or w.images
        img = imgs.get(art_key, 640, 640, cover=False) if art_key else None
        if img and not getattr(img, 'isNull', lambda: True)() and img.width() > 0 and img.height() > 0:
            ar = img.width() / img.height()
            ch = min(avail_h * 0.86, avail_w / max(ar, 0.01))
            cw = ch * ar
            if cw > avail_w * 0.88:
                s = (avail_w * 0.88) / cw
                cw, ch = cw * s, ch * s
            cx, cy = W / 2, top + avail_h * 0.48
            halo = ui.QRadialGradient(ui.QPointF(cx, cy), max(cw, ch) * 0.82)
            halo.setColorAt(0.0, ui.faded(ui.FOCUS, 0.24))
            halo.setColorAt(1.0, ui.QColor(0, 0, 0, 0))
            p.fillRect(QRectF(0, top, W, H - top), ui.QBrush(halo))
            cr = QRectF(cx - cw / 2, cy - ch / 2, cw, ch)
            w.box(p, cr.translated(0.4 * u, 0.6 * u), 0.75 * u, ui.QColor(0, 0, 0, 175))
            clip = ui.QPainterPath()
            clip.addRoundedRect(cr, 0.75 * u, 0.75 * u)
            p.save()
            p.setClipPath(clip)
            p.drawImage(cr, img)
            p.restore()
            w.box(p, cr, 0.75 * u, None, ui.QColor(255, 255, 255, 58), max(1.0, 0.1 * u))
            w.text(p, w.RUN.get('t', ''), 3 * u, cr.bottom() + 1.4 * u, ('d', 2.4, 700, .03), ui.TEXT, W - 6 * u, 1)
        else:
            w.text(p, w.RUN.get('t', ''), 4 * u, top, ('d', 3.4, 700), ui.TEXT, W - 8 * u, 1, (H - top) / (3.4 * u))

    def _paint_shelf(self, p, ui, top):
        """GBADuo v1.0.1 Companion Shelf: switch between compatible packs for this game or refresh from gba-duo-companions."""
        w, u, W, H = self.w, self.w.u, self.w.width(), self.w.height()
        cands = list(dict.fromkeys([w.RUN['pack'], *(w.RUN.get('pack_candidates') or [])]))
        y = top + 2.2 * u
        x0, cw = 3.2 * u, W - 6.4 * u
        w.text(p, 'BEGLEITER-REGAL  ·  GBADUO KOMPATIBEL', x0, y, ('d', 2.2, 700, .06), ui.FOCUS, cw)
        sync_r = QRectF(x0 + cw - 24 * u, y - 0.5 * u, 24 * u, 3.8 * u)
        w.box(p, sync_r, 0.8 * u, ui.RAISED, ui.LINE, 1.0)
        w.text(p, 'PAKETE AKTUALISIEREN', sync_r.x(), sync_r.y(), ('d', 1.65, 700, .04), ui.TEXT, sync_r.width(), 1, sync_r.height() / (1.65 * u))
        w.hit(sync_r, lambda: (w.post('api/packs', {'action': 'sync'}), w.toast('Suche neue GBA-Begleiter im Web …')), name='pack_sync')
        y += 4.6 * u
        for pid in cands[:6]:
            active = (pid == w.RUN.get('pack'))
            r = QRectF(x0, y, cw, 6.2 * u)
            w.box(p, r, 0.9 * u, ui.faded(ui.FOCUS, 0.16) if active else ui.PANEL, ui.FOCUS if active else ui.LINE, 1.5 if active else 1.0)
            lbl = f'●  {pid}' if active else f'○  {pid}'
            w.text(p, lbl, r.x() + 1.8 * u, r.y(), ('u', 1.9, 700 if active else 500), ui.TEXT, cw - 16 * u, 0, r.height() / (1.9 * u))
            tag = 'AKTIV' if active else 'WÄHLEN'
            w.text(p, tag, r.right() - 13 * u, r.y(), ('d', 1.75, 700, .06), ui.FOCUS if active else ui.MUTED, 11.2 * u, 2, r.height() / (1.75 * u))
            w.hit(r, lambda pid=pid: (w.post('api/packs', {'action': 'assign', 'gid': w.RUN.get('id'), 'pack': pid}), self.choose('Begleiter')), name=f'pack_pick:{pid}')
            y += 7.0 * u

    def paint(self, p):
        w = self.w
        if self.failed:  # the script did not load: the normal panel, and say why once
            if not self.told: self.told = True; w.toast(f'Begleiter: {self.failed}'[:160])
            return False
        if w.RUN.get('pack_other_region') and not self.region_told:
            self.region_told = True
            w.toast('Hinweis: Begleiter aus anderer Spielregion – Werte können leicht abweichen.')
        ui = sys.modules[type(w).__module__]  # the window's colours follow its theme
        u, W, H = w.u, w.width(), w.height()
        cands = w.RUN.get('pack_candidates') or []
        tabs = (['Begleiter', 'Cover']
                + (['Pakete'] if len(cands) > 1 else [])
                + (['Erfolge'] if w.ACH and w.ACH.get('list') else [])
                + ['Steuerung'])
        if self.tab not in tabs: self.tab = 'Begleiter'
        # one slim row of tabs on top: the pack keeps the rest of the screen
        top, x, f = 4.6 * u, W - .8 * u, ('d', 2.2, 700, .06)
        for label in reversed(tabs):
            wide = w.width_of(label.upper(), f) + 2.6 * u
            x -= wide
            rect = QRectF(x, .5 * u, wide, top - u)
            if label == self.tab: w.box(p, rect, .8 * u, ui.TEXT)
            w.text(p, label.upper(), x, rect.y(), f, ui.INK if label == self.tab else ui.MUTED, wide, 1, rect.height() / (f[1] * u))
            w.hit(QRectF(x, 0, wide, top), lambda label=label: self.choose(label), name=label)
            x -= .5 * u
        head_title = str(self.manifest.get('name') or w.RUN['t'])
        if w.RUN.get('pack_other_region'):
            head_title += '  ·  Andere Region'
        w.text(p, head_title, 1.6 * u, 0, ('b', 1.85), ui.FOCUS if w.RUN.get('pack_other_region') else ui.MUTED, max(4 * u, x - 2 * u), lh=top / (1.85 * u))
        if self.tab == 'Steuerung': return w.ingame(p, top + 1.6 * u, ach='Erfolge' not in tabs) or True
        if self.tab == 'Cover':
            self._paint_cover_art(p, ui, top)
            return True
        if self.tab == 'Pakete':
            self._paint_shelf(p, ui, top)
            return True
        if self.tab == 'Erfolge':
            w.scroller(p, 'ach', QRectF(2.6 * u, top + 1.6 * u, W - 5.2 * u, H - top - 4.2 * u), lambda y: w.achievements(p, y))
            return True
        wide = w.RUN.get('wide')  # None: the pack has no wide()
        if self.fresh: self.snap = self.fresh.popleft()
        if self.snap is not None and self.shown != (id(self.snap), wide):
            self.shown = (id(self.snap), wide)
            self.tree.update({**self.snap, '_wide': int(bool(wide)), '_wideLabel': 'N/A' if wide is None else 'ON' if wide else 'OFF'})
        while self.todo: self.tree.perform(packcss.actions(self.todo.popleft(), script=True))
        s = min(W / self.W, (H - top) / self.H)
        self.xf = QTransform().translate((W - self.W * s) / 2, top + (H - top - self.H * s) / 2).scale(s, s)
        ground = packcss.color(self.tree.root.style.get('background-color', 'transparent'))
        if ground.alpha(): p.fillRect(QRectF(0, top, W, H - top), ground)
        p.save()
        p.setTransform(self.xf, True)
        p.setClipRect(QRectF(0, 0, self.W, self.H))
        self.tree.paint(p, s)
        p.restore()
        for rect, node in self.tree.clicks: w.hit(self.xf.mapRect(rect), lambda node=node: self.tree.tap(node), name=node.name)
        if not self.ready: w.text(p, 'Warte auf das Spiel …', 0, top, ('b', 2.4), ui.MUTED, W, 1, (H - top) / (2.4 * u))
        return True
