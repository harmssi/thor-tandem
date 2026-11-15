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
        self.tab = self.memo.get(run['pack'], 'Begleiter')
        self.ready, self.failed, self.error, self.log, self.told, self.pressed, self.xf = False, None, None, deque(maxlen=20), False, None, QTransform()
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

    def paint(self, p):
        w = self.w
        if self.failed:  # the script did not load: the normal panel, and say why once
            if not self.told: self.told = True; w.toast(f'Begleiter: {self.failed}'[:160])
            return False
        ui = sys.modules[type(w).__module__]  # the window's colours follow its theme
        u, W, H = w.u, w.width(), w.height()
        tabs = ['Begleiter'] + (['Erfolge'] if w.ACH and w.ACH.get('list') else []) + ['Steuerung']
        if self.tab not in tabs: self.tab = 'Begleiter'
        # one slim row of tabs on top: the pack keeps the rest of the screen
        top, x, f = 4.6 * u, W - .8 * u, ('d', 2.2, 700, .06)
        for label in reversed(tabs):
            wide = w.width_of(label.upper(), f) + 3 * u
            x -= wide
            rect = QRectF(x, .5 * u, wide, top - u)
            if label == self.tab: w.box(p, rect, .8 * u, ui.TEXT)
            w.text(p, label.upper(), x, rect.y(), f, ui.INK if label == self.tab else ui.MUTED, wide, 1, rect.height() / (f[1] * u))
            w.hit(QRectF(x, 0, wide, top), lambda label=label: self.choose(label), name=label)
            x -= .6 * u
        w.text(p, str(self.manifest.get('name') or w.RUN['t']), 1.6 * u, 0, ('b', 1.9), ui.MUTED, x - 2 * u, lh=top / (1.9 * u))
        if self.tab == 'Steuerung': return w.ingame(p, top + 1.6 * u, ach='Erfolge' not in tabs) or True
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
