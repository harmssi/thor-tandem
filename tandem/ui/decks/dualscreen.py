"""Interactive Dual-Screen bottom deck for Nintendo DS (melonDS), 3DS (Azahar), and Wii U (Cemu):
Captures the emulator's secondary window from :0 via libX11 XGetImage at 30 fps and forwards real finger touches
(press, drag, release) directly to that X11 window, while keeping Notizen, Guides, Cockpit & Steuerung one tap away."""
import ctypes, os, time
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from decks import universal

DUAL_TABS = ('Touchscreen', 'Notizen', 'Guides', 'Cockpit', 'Steuerung')


class _XImage(ctypes.Structure):
    _fields_ = [('width', ctypes.c_int), ('height', ctypes.c_int), ('xoffset', ctypes.c_int), ('format', ctypes.c_int),
                ('data', ctypes.c_void_p), ('byte_order', ctypes.c_int), ('bitmap_unit', ctypes.c_int),
                ('bitmap_bit_order', ctypes.c_int), ('bitmap_pad', ctypes.c_int), ('depth', ctypes.c_int),
                ('bytes_per_line', ctypes.c_int), ('bits_per_pixel', ctypes.c_int),
                ('red_mask', ctypes.c_ulong), ('green_mask', ctypes.c_ulong), ('blue_mask', ctypes.c_ulong)]


_X_ERR = None


class X11Grabber:
    """Zero-subprocess X11 window frame grabber over :0 using libX11 XGetImage."""
    def __init__(self):
        self.x11 = self.dpy = None
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return
        try:
            x11 = ctypes.CDLL('libX11.so.6')
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            dpy = x11.XOpenDisplay((os.environ.get('DISPLAY') or ':0').encode())
            if not dpy: return
            global _X_ERR
            _X_ERR = _X_ERR or ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(lambda *_: 0)
            x11.XSetErrorHandler(_X_ERR)
            x11.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                         ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                         ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
                                         ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
            x11.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
            x11.XGetImage.restype = ctypes.POINTER(_XImage)
            x11.XDestroyImage = getattr(x11, 'XDestroyImage', None)
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            self.x11, self.dpy = x11, dpy
        except OSError:
            pass

    def grab(self, wid):
        if not self.dpy or not wid: return None
        x11, dpy = self.x11, self.dpy
        root = ctypes.c_ulong()
        gx, gy = ctypes.c_int(), ctypes.c_int()
        gw, gh, gbw, gd = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
        if not x11.XGetGeometry(dpy, int(wid), ctypes.byref(root), ctypes.byref(gx), ctypes.byref(gy),
                                ctypes.byref(gw), ctypes.byref(gh), ctypes.byref(gbw), ctypes.byref(gd)):
            return None
        w, h = gw.value, gh.value
        if w < 64 or h < 48 or w > 4096 or h > 4096: return None
        xim_p = x11.XGetImage(dpy, int(wid), 0, 0, w, h, 0xFFFFFFFF, 2)  # ZPixmap = 2
        if not xim_p: return None
        try:
            xim = xim_p.contents
            if not xim.data or xim.bits_per_pixel not in (24, 32): return None
            size = xim.bytes_per_line * h
            raw = ctypes.string_at(xim.data, size)
            img = QImage(raw, w, h, xim.bytes_per_line, QImage.Format.Format_RGB32).copy()
            return img
        finally:
            if x11.XDestroyImage:
                x11.XDestroyImage.argtypes = [ctypes.POINTER(_XImage)]
                x11.XDestroyImage(xim_p)

    def close(self):
        if self.dpy and self.x11:
            self.x11.XCloseDisplay(self.dpy)
            self.dpy = None


class Deck:
    def __init__(self, w):
        self.w = w
        self.sub = universal.Deck(w, embed=True)
        self.tab = 0
        self.wid = 0
        self.frame = None
        self.screen_rect = QRectF()
        self.touch_active = False
        self.last_move = 0.0
        self.last_lookup = 0.0
        self.grabber = X11Grabber()
        self.timer = QTimer(w)
        self.timer.timeout.connect(self._tick)
        if os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
            self.timer.start(34)  # ~30 fps live second screen

    def close(self):
        self.timer.stop()
        self.grabber.close()
        self.sub.close()

    def _ui(self):
        import tandem_ui
        return tandem_ui

    def set_tab(self, i):
        self.tab = i
        # Map DUAL_TABS index -> universal.TABS index: 1->2 (Notizen), 2->3 (Guides), 3->5 (Cockpit), 4->0 (Steuerung)
        mapping = {1: 2, 2: 3, 3: 5, 4: 0}
        if i in mapping:
            self.sub.set_tab(mapping[i])
        self.w.update()

    def _tick(self):
        if self.tab != 0 or self.w.DOZE or self.w.resting():
            return
        now = time.time()
        if not self.wid and now - self.last_lookup > 1.5:
            self.last_lookup = now
            self.sub._bg_get('api/dualwin', lambda r: setattr(self, 'wid', int((r or {}).get('wid') or 0)))
            return
        if self.wid:
            img = self.grabber.grab(self.wid)
            if img is None:
                self.wid = 0
            else:
                self.frame = img
                self.w.update()

    def _norm(self, pos):
        r = self.screen_rect
        if r.width() <= 1 or r.height() <= 1: return None
        nx = max(0.0, min(1.0, (pos.x() - r.x()) / r.width()))
        ny = max(0.0, min(1.0, (pos.y() - r.y()) / r.height()))
        return round(nx, 4), round(ny, 4)

    def press(self, pos):
        if self.tab != 0:
            return self.sub.press(pos)
        if pos is None:
            if self.touch_active and self.wid:
                self.touch_active = False
                self.sub._bg_post('api/dualtouch', {'wid': self.wid, 'x': 0.5, 'y': 0.5, 'phase': 'up'})
            return
        if self.wid and self.screen_rect.contains(pos):
            xy = self._norm(pos)
            if xy:
                self.touch_active = True
                self.sub._bg_post('api/dualtouch', {'wid': self.wid, 'x': xy[0], 'y': xy[1], 'phase': 'down'})

    def move(self, pos):
        if self.tab != 0:
            return self.sub.move(pos)
        if self.touch_active and self.wid:
            now = time.time()
            if now - self.last_move >= 0.022:
                self.last_move = now
                xy = self._norm(pos)
                if xy:
                    self.sub._bg_post('api/dualtouch', {'wid': self.wid, 'x': xy[0], 'y': xy[1], 'phase': 'move'})
            return True
        return False

    def paint(self, p):
        ui = self._ui()
        w, u = self.w, self.w.u
        p.fillRect(0, 0, w.width(), w.height(), ui.INK)
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        y = 1.6 * u
        bar = QRectF(x0, y, cw - 15.5 * u, 4.8 * u)
        w.capsule(p, bar, ui.PANEL, ui.LINE)
        tw = bar.width() / len(DUAL_TABS)
        for i, lbl in enumerate(DUAL_TABS):
            r = QRectF(bar.x() + i * tw + .2 * u, y + .2 * u, tw - .4 * u, 4.4 * u)
            on = (i == self.tab)
            if on: w.capsule(p, r, ui.RAISED, ui.faded(ui.FOCUS, .7))
            w.text(p, lbl, r.x(), r.y(), ('u', 1.65, 700 if on else 500), ui.FOCUS if on else ui.MUTED, r.width(), 1, 4.4 / 1.65)
            w.hit(r, lambda i=i: self.set_tab(i), name='dtab:' + lbl)
        # Screen swap pill (F9 = 67 in Azahar / emulator swap)
        sw_r = QRectF(x0 + cw - 14.5 * u, y, 14.5 * u, 4.8 * u)
        w.capsule(p, sw_r, ui.RAISED, ui.LINE)
        w.text(p, '⇄ Tauschen', sw_r.x(), sw_r.y(), ('u', 1.65, 600), ui.TEXT, sw_r.width(), 1, 4.8 / 1.65)
        w.hit(sw_r, lambda: w.post('api/key', {'code': 67, 'mods': []}), name='dual_swap')
        y += 6.0 * u

        if self.tab != 0:
            self.screen_rect = QRectF()
            self.sub.paint_body(p, y)
            return True

        avail = QRectF(1.6 * u, y, w.width() - 3.2 * u, w.height() - y - 1.6 * u)
        if self.frame and not self.frame.isNull():
            fw, fh = self.frame.width(), self.frame.height()
            scale = min(avail.width() / max(1, fw), avail.height() / max(1, fh))
            dw, dh = fw * scale, fh * scale
            sr = QRectF(avail.center().x() - dw / 2, avail.center().y() - dh / 2, dw, dh)
            self.screen_rect = sr
            clip = QPainterPath(); clip.addRoundedRect(sr, 1.2 * u, 1.2 * u)
            p.save(); p.setClipPath(clip); p.drawImage(sr, self.frame); p.restore()
        else:
            self.screen_rect = avail
            w.box(p, avail, 1.8 * u, ui.PANEL, ui.LINE)
            w.text(p, 'Warte auf zweiten Spielbildschirm …', avail.x(), avail.center().y() - 3 * u,
                   ('u', 2.3, 600), ui.TEXT, avail.width(), 1)
            w.text(p, 'Sobald das Spiel läuft, erscheint hier der untere Touchscreen live mit Finger-Bedienung.',
                   avail.x() + 6 * u, avail.center().y() + 1.2 * u, ('u', 1.85, 400), ui.MUTED, avail.width() - 12 * u, 1, 1.4, 2)
        return True
