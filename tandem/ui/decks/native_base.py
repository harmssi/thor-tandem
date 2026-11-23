"""Shared foundation for bespoke Native Game Companions on the AYN Thor bottom OLED screen.
Provides zero-latency UDP button/chord/melody dispatch to PeanutsNative/BananaNative (127.0.0.1:8779),
persistent per-game state (/api/cstate), custom QPainter geometry helpers, and seamless embedded access
to Tandem's universal tools (Steuerung, Stände, Skizzenblock, Guides, Musik, Cockpit, Maus)."""
import json, socket, threading
from urllib.parse import quote
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainterPath, QPen, QPolygonF


def qcol(hex_str, alpha=1.0):
    c = QColor(hex_str)
    if alpha < 1.0:
        c.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return c


class CompanionBase:
    KEY = 'native'
    TABS = ('Übersicht', 'Werkzeuge')

    def __init__(self, w, key=None):
        self.w = w
        self.key = key or self.KEY
        memo_bucket = w.memo.setdefault('ncomp', {})
        self.tab = int(memo_bucket.get(self.key, 0))
        if not (0 <= self.tab < len(self.TABS)):
            self.tab = 0
        self.state = {}
        self._univ = None
        ui = self.ui()
        base_url = getattr(ui, 'URL', None) or f'http://{ui.ADDR[0]}:{ui.ADDR[1]}'
        self.origin = base_url.rstrip('/')
        self.server = self.origin + '/'
        self._load_state()

    def ui(self):
        import tandem_ui
        return tandem_ui

    def univ(self):
        if self._univ is None:
            from decks import universal
            self._univ = universal.Deck(self.w, embed=True)
        return self._univ

    def is_tools_tab(self):
        return self.tab == len(self.TABS) - 1

    def set_tab(self, idx):
        self.tab = int(idx)
        self.w.memo.setdefault('ncomp', {})[self.key] = self.tab
        self.w.haptic()
        self.w.update()

    def close(self):
        if self._univ is not None:
            self._univ.close()
            self._univ = None

    def press(self, pos):
        if pos is None:
            if getattr(self, '_swipe_start', None) is not None and getattr(self, '_swipe_last', None) is not None:
                u = self.w.u
                dx = self._swipe_last.x() - self._swipe_start.x()
                dy = self._swipe_last.y() - self._swipe_start.y()
                if self._swipe_start.y() < 11.0 * u and abs(dx) > 6.5 * u and abs(dx) > abs(dy) * 1.4 and len(self.TABS) > 1:
                    nxt = (self.tab + (-1 if dx > 0 else 1)) % len(self.TABS)
                    self._swipe_start = self._swipe_last = None
                    self.set_tab(nxt)
                    return
            self._swipe_start = self._swipe_last = None
        else:
            self._swipe_start = self._swipe_last = pos
        if self.is_tools_tab() and self._univ is not None:
            return self._univ.press(pos)

    def move(self, pos):
        if getattr(self, '_swipe_start', None) is not None:
            self._swipe_last = pos
        if self.is_tools_tab() and self._univ is not None:
            return self._univ.move(pos)
        return False

    # ---- Persistent companion state (/api/cstate) -------------------------------------------------------------------
    def _load_state(self):
        import os
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return

        def work():
            try:
                import urllib.request
                with urllib.request.urlopen(f'{self.server}api/cstate?key={quote(self.key)}', timeout=5) as r:
                    res = json.loads(r.read())
                data = res.get('data') if isinstance(res, dict) else None
            except Exception:
                data = None
            if isinstance(data, dict):
                self.w.result.emit(lambda d: (self.state.update(d), self.w.update()), data)

        threading.Thread(target=work, daemon=True).start()

    def _post_cstate(self, payload):
        import os
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return

        def work():
            try:
                import urllib.request
                req = urllib.request.Request(
                    f'{self.server}api/cstate',
                    data=json.dumps({'key': self.key, **payload}).encode('utf-8'),
                    headers={'Content-Type': 'application/json', 'Origin': self.origin},
                    method='POST',
                )
                urllib.request.urlopen(req, timeout=6).read()
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def is_done(self, item_id):
        return bool((self.state.get('done') or {}).get(item_id))

    def toggle_done(self, item_id):
        done = dict(self.state.get('done') or {})
        if done.get(item_id):
            done.pop(item_id, None)
        else:
            done[item_id] = True
        self.state['done'] = done
        self.w.haptic()
        self.w.update()
        self._post_cstate({'toggle': item_id})

    def get_val(self, field, default=0):
        return self.state.get(field, default)

    def set_val(self, field, val):
        self.state[field] = val
        self.w.haptic()
        self.w.update()
        self._post_cstate({'patch': {field: val}})

    def bump_val(self, field, delta, lo=0, hi=999):
        cur = int(self.state.get(field, 0) or 0)
        nxt = max(lo, min(hi, cur + delta))
        self.set_val(field, nxt)

    # ---- Direct localhost UDP Gamepad Bridge (127.0.0.1:8779) -------------------------------------------------------
    def send_pad(self, seq, toast=None):
        self.w.haptic()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(str(seq).encode('ascii'), ('127.0.0.1', 8779))
        except OSError:
            pass
        if toast:
            self.w.toast(toast)
        self.w.update()

    # ---- Custom QPainter geometry helpers ---------------------------------------------------------------------------
    def txt_mid(self, p, text, rect, font_spec, color, align=1, pad_x=0.0):
        """Vertically center single-line `text` inside `rect` using Tandem's unit-scaled `lh` convention."""
        u = self.w.u
        w_avail = max(1.0, rect.width() - 2.0 * pad_x)
        lh = rect.height() / max(0.1, font_spec[1] * u)
        self.w.text(p, text, rect.x() + pad_x, rect.y(), font_spec, color, w_avail, align, lh)

    def slant(self, p, rect, lean, fill, stroke=None, sw=1.5):
        path = QPainterPath()
        path.moveTo(rect.left() + lean, rect.top())
        path.lineTo(rect.right() + lean, rect.top())
        path.lineTo(rect.right(), rect.bottom())
        path.lineTo(rect.left(), rect.bottom())
        path.closeSubpath()
        p.setPen(QPen(stroke, sw) if stroke is not None else Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fill))
        p.drawPath(path)

    def chamfer_box(self, p, rect, cut, fill, stroke=None, sw=1.4):
        l, t, r, b = rect.left(), rect.top(), rect.right(), rect.bottom()
        c = min(cut, rect.width() * 0.25, rect.height() * 0.25)
        poly = QPolygonF([
            QPointF(l + c, t), QPointF(r - c, t), QPointF(r, t + c), QPointF(r, b - c),
            QPointF(r - c, b), QPointF(l + c, b), QPointF(l, b - c), QPointF(l, t + c),
        ])
        p.setPen(QPen(stroke, sw) if stroke is not None else Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fill))
        p.drawPolygon(poly)

    def vgrad(self, rect, top_hex, bot_hex):
        g = QLinearGradient(0, rect.top(), 0, rect.bottom())
        g.setColorAt(0.0, qcol(top_hex))
        g.setColorAt(1.0, qcol(bot_hex))
        return g

    def paint_tools_embedded(self, p, top_y, bg_hex='#090b10'):
        u = self.w.u
        p.fillRect(QRectF(0, top_y, self.w.width(), self.w.height() - top_y), qcol(bg_hex))
        uv = self.univ()
        body_y = uv.paint_tabs(p, top_y + 1.0 * u)
        uv.paint_body(p, body_y)
