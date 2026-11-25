"""Bottom-screen deck for 'Thor als Pro-Controller & Touch-Deck (Mac / PC)':
Turns the AYN Thor into a wireless 120 Hz Hall-effect controller + precision trackpad + macro pad for Mac & PC."""
import json, threading, time
from PySide6.QtCore import QPointF, QRectF, QTimer
from PySide6.QtGui import QColor


class Deck:
    def __init__(self, w):
        self.w = w
        ui = self._ui()
        base_url = getattr(ui, 'URL', None) or f'http://{ui.ADDR[0]}:{ui.ADDR[1]}'
        self.origin = base_url.rstrip('/')
        self.server = self.origin + '/'
        self.st = {'active': True, 'target_ip': '', 'port': 8389, 'packets': 0}
        self.pad_rect = QRectF()
        self.last_pt = None
        self.down_at = 0.0
        self.moved = 0.0
        self.timer = QTimer(w)
        self.timer.timeout.connect(self._poll)
        if __import__('os').environ.get('QT_QPA_PLATFORM') != 'offscreen':
            self._poll()
            self.timer.start(2500)

    def close(self):
        self.timer.stop()

    def _ui(self):
        import tandem_ui
        return tandem_ui

    def _poll(self):
        def work():
            try:
                import urllib.request
                with urllib.request.urlopen(self.server + 'api/propad', timeout=4) as r:
                    res = json.loads(r.read())
            except Exception:
                res = None
            self.w.result.emit(lambda d: d and setattr(self, 'st', d), res)
        threading.Thread(target=work, daemon=True).start()

    def _post(self, body, then=None):
        def work():
            try:
                import urllib.request
                req = urllib.request.Request(self.server + 'api/propad', data=json.dumps(body).encode(),
                                             headers={'Content-Type': 'application/json', 'Origin': self.origin}, method='POST')
                with urllib.request.urlopen(req, timeout=5) as r:
                    res = json.loads(r.read())
            except Exception:
                res = None
            if then:
                self.w.result.emit(then, res)
        threading.Thread(target=work, daemon=True).start()

    def press(self, pos):
        if pos is None:
            if self.last_pt is not None and self.moved < 8.0 and (time.time() - self.down_at) < 0.28:
                self.w.haptic()
                self._post({'action': 'mouse', 'click': 'left'})
            self.last_pt = None
            return
        if self.pad_rect.contains(pos):
            self.last_pt, self.down_at, self.moved = pos, time.time(), 0.0

    def move(self, pos):
        if self.last_pt is None:
            return False
        dx, dy = pos.x() - self.last_pt.x(), pos.y() - self.last_pt.y()
        self.moved += abs(dx) + abs(dy)
        if abs(dx) >= 1.0 or abs(dy) >= 1.0:
            self.last_pt = pos
            self._post({'action': 'mouse', 'dx': round(dx * 1.4), 'dy': round(dy * 1.4)})
        return True

    def paint(self, p):
        ui = self._ui()
        w, u = self.w, self.w.u
        p.fillRect(0, 0, w.width(), w.height(), ui.INK)
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        y = 2.2 * u
        # Header card
        hdr = QRectF(x0, y, cw, 7.2 * u)
        ip = self.st.get('target_ip') or ''
        w.box(p, hdr, 1.8 * u, ui.PANEL, ui.LIVE if ip else ui.LINE)
        w.text(p, '🎮 PRO-CONTROLLER & TOUCH-DECK (MAC / PC)', x0 + 1.8 * u, y + 1.0 * u,
               ('u', 1.38, 700, .09), ui.LIVE if ip else ui.FOCUS, cw - 24 * u)
        ip_lbl = f'Ziel: {ip}:8389  ·  {self.st.get("packets", 0)} Pakete' if ip else 'Noch keine Mac-/PC-IP eingetragen'
        w.text(p, ip_lbl, x0 + 1.8 * u, y + 3.5 * u, ('u', 1.82, 600), ui.TEXT if ip else ui.MUTED, cw - 24 * u)
        ip_btn = QRectF(hdr.right() - 20.4 * u, y + 1.3 * u, 19.0 * u, 4.6 * u)
        w.button(p, ip_btn, 'Mac / PC-IP setzen',
                 lambda: w.ask('IP-Adresse deines Mac oder PCs', ip, False,
                               lambda v: v.strip() and self._post({'action': 'target', 'ip': v.strip()},
                                                                  lambda r: r and (setattr(self, 'st', r), r.get('text') and w.toast(r['text'])))),
                 ('u', 1.65, 700), ui.INK, ui.FOCUS, None, 1.2)
        y += 8.5 * u

        # Quick Macro Row (6 desktop/gaming shortcuts)
        macros = (('Esc', 'ESC'), ('Space', ' '), ('Enter', '\r'), ('Cmd/Win+Tab', 'TAB'), ('F5 Save', 'F5'), ('F11 Vollbild', 'F11'))
        mw = (cw - 5 * 1.0 * u) / 6
        for i, (mlbl, mch) in enumerate(macros):
            mr = QRectF(x0 + i * (mw + 1.0 * u), y, mw, 4.8 * u)
            w.button(p, mr, mlbl, lambda ch=mch: (w.haptic(), self._post({'action': 'key', 'ch': ch})),
                     ('u', 1.55, 600), ui.TEXT, ui.RAISED, ui.LINE, 1.1)
        y += 6.1 * u

        # Large Precision Trackpad
        bot = w.height() - 2.2 * u - 5.6 * u
        pad_h = max(18 * u, bot - 1.4 * u - y)
        self.pad_rect = QRectF(x0, y, cw, pad_h)
        w.box(p, self.pad_rect, 2.0 * u, QColor('#0e1117'), ui.LINE)
        pinfo = w.PAIR or {}
        dl_hint = ((pinfo.get('ip_url') or 'http://thor.local:8378') + '/thor-pad.py')
        w.text(p, 'HALL-STICKS AKTIV  ·  MULTI-TOUCH TRACKPAD', self.pad_rect.x(), self.pad_rect.center().y() - 2.6 * u,
               ('u', 1.55, 700, .12), QColor(255, 255, 255, 58), cw, 1)
        w.text(p, f'Mac/PC-Empfänger (1 Befehl): curl -sL {dl_hint} | python3',
               self.pad_rect.x() + 2 * u, self.pad_rect.center().y() + 1.0 * u,
               ('u', 1.52, 500), ui.MUTED, cw - 4 * u, 1)

        w.button(p, QRectF(x0, bot, cw, 5.6 * u), 'Controller-Modus beenden', w.confirm_quit,
                 ('u', 2.05, 600), ui.WARN, ui.faded(ui.WARN, .14), None, 1.4)
        return True
