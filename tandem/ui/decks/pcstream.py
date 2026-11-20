"""PC-Streaming & Remote-Desktop companion deck (Moonlight / Chiaki) for Toravo Tandem:
Precision multi-zone trackpad (cursor move, tap-to-click, right-edge scroll wheel, drag-lock),
PC quick-macro keys (Esc, Win, Alt+Tab, F11, Task-Mgr), Wake-on-LAN trigger, and tactile 3D haptic keyboard toggle."""
import time
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen


MACROS = (
    ('Esc', 1, []),
    ('Tab', 15, []),
    ('Win', 125, []),
    ('Alt+Tab', 15, ['alt']),
    ('Vollbild', 87, []),
    ('Task-Mgr', 1, ['ctrl', 'shift']),
)


class Deck:
    def __init__(self, w):
        self.w = w
        self.kb_open = False
        self.drag_lock = False
        self.pad_rect = QRectF()
        self.scroll_rect = QRectF()
        self.mode = None  # 'move' | 'scroll'
        self.last_pos = None
        self.down_pos = None
        self.down_at = 0.0
        self.moved_px = 0.0

    def close(self):
        if self.drag_lock:
            self.w.post('api/mouse', {'btn': 'left', 'action': 'up'})

    def _ui(self):
        import tandem_ui
        return tandem_ui

    def press(self, pos):
        if self.kb_open: return
        if pos is None:
            if self.mode == 'move' and self.moved_px < 8.0 and time.time() - self.down_at < 0.28:
                self.w.haptic()
                self.w.post('api/mouse', {'btn': 'left', 'action': 'click'})
            self.mode = self.last_pos = None
            return
        if self.scroll_rect.contains(pos):
            self.mode, self.last_pos, self.moved_px = 'scroll', pos, 0.0
        elif self.pad_rect.contains(pos):
            self.mode, self.last_pos, self.down_pos, self.down_at, self.moved_px = 'move', pos, pos, time.time(), 0.0

    def move(self, pos):
        if not self.mode or self.last_pos is None: return False
        dx = pos.x() - self.last_pos.x()
        dy = pos.y() - self.last_pos.y()
        self.moved_px += abs(dx) + abs(dy)
        if self.mode == 'scroll':
            steps = int(-dy / max(8.0, 2.2 * self.w.u))
            if steps:
                self.last_pos = pos
                self.w.post('api/mouse', {'wheel': steps})
            return True
        if abs(dx) >= 0.8 or abs(dy) >= 0.8:
            self.last_pos = pos
            speed = min(2.4, 1.15 + (abs(dx) + abs(dy)) * 0.025)
            self.w.post('api/mouse', {'dx': round(dx * speed), 'dy': round(dy * speed)})
        return True

    def _toggle_drag(self):
        self.drag_lock = not self.drag_lock
        self.w.haptic()
        self.w.post('api/mouse', {'btn': 'left', 'action': 'down' if self.drag_lock else 'up'})

    def paint(self, p):
        ui = self._ui()
        w, u = self.w, self.w.u
        p.fillRect(0, 0, w.width(), w.height(), ui.INK)
        x0, cw, bottom = 2.6 * u, w.width() - 5.2 * u, w.height() - 2.2 * u
        y = 2.0 * u

        # Top Macro + Keyboard + WoL bar
        w.text(p, f'● {(w.RUN or {}).get("t", "PC-Stream").upper()}', x0, y, ('u', 1.45, 700, .12), ui.LIVE, 30 * u, 0, 4.6 / 1.45)
        kb_r = QRectF(x0 + cw - 34.5 * u, y, 16.5 * u, 4.6 * u)
        wol_r = QRectF(x0 + cw - 17.0 * u, y, 17.0 * u, 4.6 * u)
        w.capsule(p, kb_r, ui.FOCUS if self.kb_open else ui.RAISED, None if self.kb_open else ui.LINE)
        w.text(p, 'Tastatur', kb_r.x(), kb_r.y(), ('u', 1.75, 700), ui.INK if self.kb_open else ui.TEXT, kb_r.width(), 1, 4.6 / 1.75)
        w.hit(kb_r, lambda: setattr(self, 'kb_open', not self.kb_open), name='pc_kb')
        w.capsule(p, wol_r, ui.RAISED, ui.LINE)
        w.text(p, 'PC wecken', wol_r.x(), wol_r.y(), ('u', 1.75, 600), ui.TEXT, wol_r.width(), 1, 4.6 / 1.75)
        w.hit(wol_r, lambda: w.post('api/wol', {}, then=lambda r: r and w.toast(r.get('text') or r.get('error', ''))), name='pc_wol')
        y += 5.6 * u

        # Quick PC Hotkeys row
        mw = (cw - (len(MACROS) - 1) * .9 * u) / len(MACROS)
        for i, (lbl, code, mods) in enumerate(MACROS):
            mr = QRectF(x0 + i * (mw + .9 * u), y, mw, 4.6 * u)
            w.capsule(p, mr, ui.PANEL, ui.LINE)
            w.text(p, lbl, mr.x(), mr.y(), ('u', 1.7, 600), ui.TEXT, mw, 1, 4.6 / 1.7)
            w.hit(mr, lambda c=code, m=mods: (w.haptic(), w.post('api/key', {'code': c, 'mods': m})), name='macro:' + lbl)
        y += 5.8 * u

        if self.kb_open:
            self.pad_rect = self.scroll_rect = QRectF()
            w.keyboard(p, y, w.term_key, bottom_y=bottom - 6.6 * u)
        else:
            # Precision Trackpad + Right Scroll Strip
            pad_h = max(20 * u, bottom - 13.4 * u - y)
            full_r = QRectF(x0, y, cw, pad_h)
            sc_w = 7.5 * u
            self.pad_rect = QRectF(x0, y, cw - sc_w - .8 * u, pad_h)
            self.scroll_rect = QRectF(full_r.right() - sc_w, y, sc_w, pad_h)
            w.box(p, self.pad_rect, 2.0 * u, QColor('#101218'), ui.LINE)
            w.text(p, 'TOUCHPAD · TIPPEN = KLICK', self.pad_rect.x(), self.pad_rect.center().y() - 1.2 * u,
                   ('u', 1.5, 700, .14), QColor(255, 255, 255, 42), self.pad_rect.width(), 1)
            w.box(p, self.scroll_rect, 1.8 * u, ui.PANEL, ui.LINE)
            # Scroll ticks
            p.setPen(QPen(QColor(255, 255, 255, 48), .22 * u))
            ty = self.scroll_rect.y() + 4 * u
            while ty < self.scroll_rect.bottom() - 3 * u:
                p.drawLine(QPointF(self.scroll_rect.x() + 2.2 * u, ty), QPointF(self.scroll_rect.right() - 2.2 * u, ty))
                ty += 2.6 * u
            y += pad_h + 1.2 * u
            # Left / Middle / Drag-Lock / Right mouse buttons
            bw = (cw - 2 * 1.2 * u) / 3
            for bi, (lbl, fn, hi) in enumerate((
                ('Linksklick', lambda: (w.haptic(), w.post('api/mouse', {'btn': 'left', 'action': 'click'})), False),
                ('Halten / Ziehen', self._toggle_drag, self.drag_lock),
                ('Rechtsklick', lambda: (w.haptic(), w.post('api/mouse', {'btn': 'right', 'action': 'click'})), False),
            )):
                br = QRectF(x0 + bi * (bw + 1.2 * u), y, bw, 5.2 * u)
                w.capsule(p, br, ui.FOCUS if hi else ui.RAISED, None if hi else ui.LINE)
                w.text(p, lbl, br.x(), br.y(), ('u', 1.85, 700 if hi else 600), ui.INK if hi else ui.TEXT, bw, 1, 5.2 / 1.85)
                w.hit(br, fn, name='mbtn:' + lbl)

        w.button(p, QRectF(x0, bottom - 5.4 * u, cw, 5.4 * u), 'Spiel beenden', w.confirm_quit,
                 ('u', 2.0, 600), ui.WARN, ui.faded(ui.WARN, .14), None, 1.4)
        return True
