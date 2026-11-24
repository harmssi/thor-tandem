"""PlayTranslate-style real-time German screen translator tab for Toravo Tandem's bottom OLED.

Supports:
- 1-Tap immediate top-screen OCR -> German translation ('⚡ Jetzt übersetzen')
- Auto-Dialogue mode ('Auto-Dialog', pixel-diff + typewriter settle detector on Silver cores 0-2)
- Interactive finger-drag dialogue crop selector on a live preview of the top screen ('⊞ Rahmen')
- Tappable word-lookup chips, Romaji/Pinyin reading display, German TTS ('🔊'), and 30-line dialogue log
- Built-in 1-click offline language pack installer (Deutsch + Japanisch / Chinesisch / Spanisch / Französisch)
"""
import json
import os
import threading
import time
from urllib.parse import quote
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainterPath, QPen

SRC_CYCLE = (
    ('auto', 'Auto'),
    ('en', 'EN'),
    ('ja', 'JA'),
    ('zh', 'ZH'),
    ('es', 'ES'),
    ('fr', 'FR'),
)


class TranslatorView:
    def __init__(self, deck):
        self.deck = deck
        self.w = deck.w
        self.st = {
            'ready': True, 'models': ['en_de'], 'catalog': [], 'install': {'running': False, 'step': '', 'error': ''},
            'auto': False, 'mode': 'auto', 'src': 'auto', 'target': 'de', 'busy': False,
            'last': None, 'word_info': None, 'error': '', 'seq': 0,
            'region': 'full', 'crop': [0.0, 0.0, 1.0, 1.0], 'history': [], 'tts_available': True,
        }
        self.loaded = False
        self.show_packs = False
        self.cropping = False
        self.preview_img = None
        self.preview_rect = QRectF()
        self.drag_start = None
        self.drag_cur = None
        self.poll_timer = QTimer(self.w)
        self.poll_timer.timeout.connect(self.refresh)

    def _ui(self):
        return self.deck._ui()

    def activate(self, trigger_now=False):
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return
        self.refresh()
        if not self.poll_timer.isActive():
            self.poll_timer.start(1600)
        if trigger_now:
            self.capture_now()

    def deactivate(self):
        self.poll_timer.stop()
        self.cropping = False
        self.drag_start = self.drag_cur = None

    def close(self):
        self.deactivate()

    def refresh(self):
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return
        gid = (self.w.RUN or {}).get('id') or ''
        self.deck._bg_get(f'api/translate?id={quote(gid)}', self._on_state)

    def _on_state(self, r):
        if isinstance(r, dict) and 'error' not in r or (isinstance(r, dict) and 'ready' in r):
            self.st = r
            self.loaded = True
            # Keep polling faster while auto-mode or installer is active
            fast = bool(r.get('auto') or (r.get('install') or {}).get('running') or r.get('busy'))
            if self.poll_timer.isActive():
                want = 1100 if fast else 2400
                if self.poll_timer.interval() != want:
                    self.poll_timer.setInterval(want)
            self.w.update()

    def _post(self, payload, then=None):
        gid = (self.w.RUN or {}).get('id') or ''
        body = {'id': gid, **payload}
        self.deck._bg_post('api/translate', body, then or self._on_state)

    def capture_now(self):
        self.w.haptic()
        self.st['busy'] = True
        self.st['error'] = ''
        self.w.update()
        self._post({'action': 'now'})

    def toggle_auto(self):
        self.w.haptic()
        nxt = not bool(self.st.get('auto'))
        self.st['auto'] = nxt
        self.w.update()
        self._post({'action': 'options', 'auto': nxt})

    def toggle_mode(self):
        self.w.haptic()
        nxt = 'offline' if self.st.get('mode') != 'offline' else 'auto'
        self.st['mode'] = nxt
        self.w.update()
        self._post({'action': 'options', 'mode': nxt})

    def cycle_src(self):
        self.w.haptic()
        codes = [c[0] for c in SRC_CYCLE]
        cur = self.st.get('src') or 'auto'
        nxt = codes[(codes.index(cur) + 1) % len(codes)] if cur in codes else 'auto'
        self.st['src'] = nxt
        self.w.update()
        self._post({'action': 'options', 'src': nxt})

    def set_region(self, reg):
        self.w.haptic()
        self.cropping = False
        self.st['region'] = reg
        self.w.update()
        self._post({'action': 'crop', 'region': reg}, then=lambda r: (self._on_state(r), self.capture_now()))

    def open_crop_editor(self):
        self.w.haptic()
        self.cropping = True
        self.drag_start = self.drag_cur = None
        self.w.update()
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return

        def on_png(raw):
            if raw:
                img = QImage()
                if img.loadFromData(raw, 'PNG'):
                    self.preview_img = img
                    self.w.update()

        self.deck._bg_get('api/translate_preview', on_png, raw=True)

    # ---- Finger drag for custom dialogue box crop --------------------------------------------------------------------
    def _norm_pt(self, pos):
        r = self.preview_rect
        if r.width() <= 4 or r.height() <= 4:
            return (0.0, 0.0)
        nx = max(0.0, min(1.0, (pos.x() - r.x()) / r.width()))
        ny = max(0.0, min(1.0, (pos.y() - r.y()) / r.height()))
        return (nx, ny)

    def press(self, pos):
        if not self.cropping:
            return
        if pos is None:
            if self.drag_start and self.drag_cur:
                x0, y0 = self.drag_start
                x1, y1 = self.drag_cur
                lx, rx = min(x0, x1), max(x0, x1)
                ty, by = min(y0, y1), max(y0, y1)
                if (rx - lx) >= 0.06 and (by - ty) >= 0.05:
                    box = [round(lx, 4), round(ty, 4), round(rx - lx, 4), round(by - ty, 4)]
                    self.cropping = False
                    self.drag_start = self.drag_cur = None
                    self.w.haptic()
                    self._post({'action': 'crop', 'region': 'custom', 'box': box},
                               then=lambda r: (self._on_state(r), self.capture_now()))
                    return
            self.drag_start = self.drag_cur = None
            self.w.update()
            return
        if self.preview_rect.contains(pos):
            pt = self._norm_pt(pos)
            self.drag_start = self.drag_cur = pt
            self.w.update()

    def move(self, pos):
        if self.cropping and self.drag_start is not None:
            self.drag_cur = self._norm_pt(pos)
            self.w.update()
            return True
        return False

    # ---- Painting ----------------------------------------------------------------------------------------------------
    def paint(self, p, y):
        ui = self._ui()
        w, u = self.w, self.w.u
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        bot = self.deck._quit_footer(p)
        st = self.st

        # Interactive Crop Selector View
        if self.cropping:
            self._paint_crop_editor(p, x0, y, cw, bot)
            return

        # Language Pack Manager / First-Time Installer View
        if not st.get('ready') or self.show_packs:
            self._paint_packs(p, x0, y, cw, bot)
            return

        # ---- Row 1: Primary Translate Controls ----
        busy = bool(st.get('busy'))
        auto_on = bool(st.get('auto'))
        offline_only = (st.get('mode') == 'offline')

        b_now = QRectF(x0, y, 27.5 * u, 5.0 * u)
        w.capsule(p, b_now, ui.RAISED if busy else ui.FOCUS, ui.FOCUS if busy else None)
        now_lbl = '⏳ Übersetze …' if busy else '⚡ Jetzt übersetzen'
        w.text(p, now_lbl, b_now.x(), b_now.y(), ('u', 1.82, 700), ui.FOCUS if busy else ui.INK, b_now.width(), 1, 5.0 / 1.82)
        w.hit(b_now, self.capture_now, name='tr:now')

        b_auto = QRectF(b_now.right() + 1.0 * u, y, 20.5 * u, 5.0 * u)
        w.capsule(p, b_auto, ui.faded(ui.LIVE, .20) if auto_on else ui.PANEL, ui.LIVE if auto_on else ui.LINE)
        w.text(p, '● Auto-Dialog' if auto_on else 'Auto-Dialog', b_auto.x(), b_auto.y(), ('u', 1.72, 700 if auto_on else 600),
               ui.LIVE if auto_on else ui.TEXT, b_auto.width(), 1, 5.0 / 1.72)
        w.hit(b_auto, self.toggle_auto, name='tr:auto')

        b_mode = QRectF(b_auto.right() + 1.0 * u, y, 16.5 * u, 5.0 * u)
        w.capsule(p, b_mode, ui.RAISED if offline_only else ui.PANEL, ui.FOCUS if offline_only else ui.LINE)
        w.text(p, '100 % Offline' if offline_only else 'Hybrid · DE', b_mode.x(), b_mode.y(), ('u', 1.65, 600),
               ui.FOCUS if offline_only else ui.TEXT, b_mode.width(), 1, 5.0 / 1.65)
        w.hit(b_mode, self.toggle_mode, name='tr:mode')

        last = st.get('last')
        b_tts = QRectF(b_mode.right() + 1.0 * u, y, 13.5 * u, 5.0 * u)
        can_tts = bool(last and last.get('translated') and st.get('tts_available', True))
        w.capsule(p, b_tts, ui.PANEL, ui.LINE)
        w.text(p, '🔊 Vorlesen', b_tts.x(), b_tts.y(), ('u', 1.62, 600), ui.TEXT if can_tts else ui.MUTED, b_tts.width(), 1, 5.0 / 1.62)
        if can_tts:
            w.hit(b_tts, lambda: (w.haptic(), self._post({'action': 'speak', 'text': last['translated']})), name='tr:speak')

        b_pk = QRectF(b_tts.right() + 1.0 * u, y, max(8.0 * u, x0 + cw - b_tts.right() - 1.0 * u), 5.0 * u)
        w.capsule(p, b_pk, ui.PANEL, ui.LINE)
        w.text(p, 'Sprachen', b_pk.x(), b_pk.y(), ('u', 1.62, 600), ui.MUTED, b_pk.width(), 1, 5.0 / 1.62)
        w.hit(b_pk, lambda: (w.haptic(), setattr(self, 'show_packs', True), w.update()), name='tr:packs')
        y += 6.0 * u

        # ---- Row 2: Capture Region & Source Language ----
        reg = st.get('region') or 'full'
        reg_opts = (('full', 'Vollbild'), ('bottom', 'Dialog unten'), ('top', 'Dialog oben'))
        rx = x0
        for rid, rlbl in reg_opts:
            rw = 16.8 * u
            rr = QRectF(rx, y, rw, 4.3 * u)
            on = (reg == rid)
            w.capsule(p, rr, ui.RAISED if on else ui.PANEL, ui.FOCUS if on else ui.LINE)
            w.text(p, rlbl, rr.x(), rr.y(), ('u', 1.6, 700 if on else 500), ui.FOCUS if on else ui.MUTED, rw, 1, 4.3 / 1.6)
            w.hit(rr, lambda rid=rid: self.set_region(rid), name='treg:' + rid)
            rx += rw + .8 * u

        rcrop = QRectF(rx, y, 20.2 * u, 4.3 * u)
        on_custom = (reg == 'custom')
        w.capsule(p, rcrop, ui.RAISED if on_custom else ui.PANEL, ui.FOCUS if on_custom else ui.LINE)
        w.text(p, '⊞ Eigener Rahmen', rcrop.x(), rcrop.y(), ('u', 1.6, 700 if on_custom else 600),
               ui.FOCUS if on_custom else ui.TEXT, rcrop.width(), 1, 4.3 / 1.6)
        w.hit(rcrop, self.open_crop_editor, name='treg:custom')

        src_lbl = dict(SRC_CYCLE).get(st.get('src') or 'auto', 'Auto')
        rsrc = QRectF(rcrop.right() + .8 * u, y, max(12 * u, x0 + cw - rcrop.right() - .8 * u), 4.3 * u)
        w.capsule(p, rsrc, ui.PANEL, ui.LINE)
        w.text(p, f'Quelle: {src_lbl} → DE', rsrc.x(), rsrc.y(), ('u', 1.58, 600), ui.TEXT, rsrc.width(), 1, 4.3 / 1.58)
        w.hit(rsrc, self.cycle_src, name='tr:src')
        y += 5.4 * u

        # ---- Main Scrollable Translation Stage + Word Lookup + History ----
        area = QRectF(x0, y, cw, max(10 * u, bot - y))

        def draw_stage(top):
            cy = top
            err = st.get('error')
            if err:
                er = QRectF(x0, cy, cw, 5.2 * u)
                w.box(p, er, 1.4 * u, ui.faded(ui.WARN, .14), ui.WARN)
                w.text(p, err, x0 + 1.8 * u, cy, ('u', 1.8, 600), ui.WARN, cw - 3.6 * u, 0, 5.2 / 1.8)
                cy += 6.2 * u

            cur = st.get('last')
            if not cur:
                empty_r = QRectF(x0, cy, cw, 18.5 * u)
                w.box(p, empty_r, 1.8 * u, ui.PANEL, ui.LINE)
                w.text(p, 'LIVE-SPIELÜBERSETZER (DEUTSCH)', x0 + 2.2 * u, cy + 1.8 * u, ('u', 1.45, 700, .1), ui.FOCUS, cw - 4.4 * u)
                w.text(p, 'Tippe oben auf „⚡ Jetzt übersetzen“ oder schalte „Auto-Dialog“ ein.\n'
                          '• Liest englische, japanische, chinesische & spanische Dialoge vom oberen Bildschirm und übersetzt sie sofort auf Deutsch.\n'
                          '• Läuft komplett auf den Silberkernen (0 % FPS-Verlust im Spiel) – auch offline unterwegs.',
                       x0 + 2.2 * u, cy + 4.6 * u, ('u', 1.85, 400), ui.MUTED, cw - 4.4 * u, 0, 1.42, 6)
                return cy + 19.5 * u

            # Hero German Translation Card
            de_lines = w.wrap(cur.get('translated') or '', ('u', 2.35, 700), cw - 4.4 * u, 10)
            rd_txt = cur.get('reading') or ''
            rd_lines = w.wrap(rd_txt, ('u', 1.72, 500), cw - 4.4 * u, 4) if rd_txt else []
            src_lines = w.wrap(cur.get('source') or '', ('u', 1.78, 400), cw - 4.4 * u, 6)
            words = cur.get('words') or []

            de_h = len(de_lines) * 2.35 * u * 1.32
            rd_h = (len(rd_lines) * 1.72 * u * 1.32 + .8 * u) if rd_lines else 0.0
            src_h = len(src_lines) * 1.78 * u * 1.32
            card_h = 4.6 * u + de_h + rd_h + 1.4 * u + src_h + 2.0 * u
            hero = QRectF(x0, cy, cw, card_h)
            w.box(p, hero, 1.8 * u, ui.PANEL, ui.faded(ui.FOCUS, .55))

            det_up = (cur.get('detected') or 'AUTO').upper()
            eng_lbl = 'OFFLINE NMT' if cur.get('engine') == 'offline' else 'HYBRID DE'
            w.text(p, f'● {det_up} → DEUTSCH  ·  {eng_lbl}', x0 + 2.2 * u, cy + 1.2 * u, ('u', 1.38, 700, .09), ui.FOCUS, cw - 4.4 * u)

            ty = cy + 3.8 * u
            for ln in de_lines:
                ty += w.text(p, ln, x0 + 2.2 * u, ty, ('u', 2.35, 700), ui.TEXT, cw - 4.4 * u, lh=1.32)
            if rd_lines:
                ty += .5 * u
                for ln in rd_lines:
                    ty += w.text(p, ln, x0 + 2.2 * u, ty, ('u', 1.72, 500), ui.FOCUS, cw - 4.4 * u, lh=1.32)
            ty += .8 * u
            p.fillRect(QRectF(x0 + 2.2 * u, ty, cw - 4.4 * u, max(1.0, .08 * u)), ui.faded(ui.TEXT, .1))
            ty += .8 * u
            for ln in src_lines:
                ty += w.text(p, ln, x0 + 2.2 * u, ty, ('u', 1.78, 400), ui.MUTED, cw - 4.4 * u, lh=1.32)
            cy += card_h + 1.2 * u

            # Tappable Word Lookup Chips (PlayTranslate Lens / Yomitan style)
            if words:
                wx, wy = x0, cy
                row_h = 4.0 * u
                sel_w = ((st.get('word_info') or {}).get('word') or '').lower()
                for tok in words[:12]:
                    tw_chip = min(28 * u, w.width_of(tok, ('u', 1.62, 600)) + 2.8 * u)
                    if wx + tw_chip > x0 + cw and wx > x0:
                        wx = x0
                        wy += row_h + .7 * u
                    cr = QRectF(wx, wy, tw_chip, row_h)
                    on_w = (tok.lower() == sel_w)
                    w.capsule(p, cr, ui.RAISED if on_w else ui.PANEL, ui.FOCUS if on_w else ui.LINE)
                    w.text(p, tok, cr.x(), cr.y(), ('u', 1.62, 600), ui.FOCUS if on_w else ui.TEXT, tw_chip, 1, row_h / 1.62)
                    w.hit(cr, lambda tok=tok: (w.haptic(), self._post({'action': 'word', 'word': tok})), name='tword:' + tok)
                    wx += tw_chip + .7 * u
                cy = wy + row_h + 1.2 * u

            winfo = st.get('word_info')
            if winfo and winfo.get('translation'):
                m_extra = '  ·  '.join(winfo.get('meanings') or [])
                w_lines = w.wrap(m_extra, ('u', 1.68, 400), cw - 3.6 * u, 3) if m_extra else []
                wh = (5.4 * u + len(w_lines) * 2.2 * u) if w_lines else 5.2 * u
                wr = QRectF(x0, cy, cw, wh)
                w.box(p, wr, 1.4 * u, ui.RAISED, ui.FOCUS)
                head_w = f"{winfo['word']}  →  {winfo['translation']}" + (f"  ({winfo['reading']})" if winfo.get('reading') else '')
                w.text(p, head_w, x0 + 1.8 * u, cy + 1.1 * u, ('u', 1.9, 700), ui.TEXT, cw - 3.6 * u)
                wy2 = cy + 4.0 * u
                for mln in w_lines:
                    wy2 += w.text(p, mln, x0 + 1.8 * u, wy2, ('u', 1.68, 400), ui.MUTED, cw - 3.6 * u, lh=1.3)
                cy += wh + 1.4 * u

            # Dialogue History Log
            hist = [h for h in (st.get('history') or []) if h.get('source') != cur.get('source')]
            if hist:
                w.text(p, 'DIALOG-VERLAUF', x0 + .4 * u, cy + .4 * u, ('u', 1.38, 700, .09), ui.MUTED, cw * .6)
                clr = QRectF(x0 + cw - 15 * u, cy, 15 * u, 3.4 * u)
                w.text(p, 'Verlauf leeren', clr.x(), clr.y(), ('u', 1.5, 600), ui.MUTED, clr.width(), 2, 3.4 / 1.5)
                w.hit(clr, lambda: (w.haptic(), self._post({'action': 'options', 'clear': True})), name='tr:clear')
                cy += 3.8 * u
                for idx, h_it in enumerate(hist[:15]):
                    hl_de = w.wrap(h_it.get('translated') or '', ('u', 1.82, 600), cw - 9.5 * u, 3)
                    hl_src = w.wrap(h_it.get('source') or '', ('u', 1.55, 400), cw - 9.5 * u, 2)
                    hh = 2.2 * u + len(hl_de) * 2.35 * u + len(hl_src) * 2.0 * u
                    hr = QRectF(x0, cy, cw, hh)
                    w.box(p, hr, 1.4 * u, ui.PANEL, ui.LINE)
                    hy = cy + 1.0 * u
                    for ln in hl_de:
                        hy += w.text(p, ln, x0 + 1.6 * u, hy, ('u', 1.82, 600), ui.TEXT, cw - 9.5 * u, lh=1.28)
                    for ln in hl_src:
                        hy += w.text(p, ln, x0 + 1.6 * u, hy, ('u', 1.55, 400), ui.MUTED, cw - 9.5 * u, lh=1.28)
                    if st.get('tts_available', True):
                        sb = QRectF(hr.right() - 6.8 * u, cy + (hh - 4.0 * u) / 2, 5.4 * u, 4.0 * u)
                        w.capsule(p, sb, ui.RAISED, ui.LINE)
                        w.text(p, '🔊', sb.x(), sb.y(), ('u', 1.7, 600), ui.TEXT, sb.width(), 1, 4.0 / 1.7)
                        w.hit(sb, lambda t=h_it['translated']: (w.haptic(), self._post({'action': 'speak', 'text': t})), name=f'tr_hspk:{idx}')
                    cy += hh + .9 * u
            return cy + 1.0 * u

        w.scroller(p, 'utranslate', area, draw_stage)

    def _paint_crop_editor(self, p, x0, y, cw, bot):
        ui = self._ui()
        w, u = self.w, self.w.u
        back = QRectF(x0, y, 13 * u, 4.6 * u)
        w.capsule(p, back, ui.RAISED, ui.LINE)
        w.text(p, '‹ Abbrechen', back.x(), back.y(), ('u', 1.75, 600), ui.TEXT, back.width(), 1, 4.6 / 1.75)
        w.hit(back, lambda: (setattr(self, 'cropping', False), w.update()), name='tr:crop_cancel')
        w.text(p, 'Mit dem Finger den Dialog-Bereich aufziehen:', x0 + 14.4 * u, y, ('u', 1.95, 700), ui.TEXT, cw - 15 * u, 0, 4.6 / 1.95)
        y += 5.6 * u

        avail_h = max(16 * u, bot - y)
        # Fit 16:9 box inside (cw, avail_h)
        pw = min(cw, avail_h * (16.0 / 9.0))
        ph = pw * (9.0 / 16.0)
        px = x0 + (cw - pw) / 2
        py = y + (avail_h - ph) / 2
        prect = QRectF(px, py, pw, ph)
        self.preview_rect = prect
        w.box(p, prect, 1.4 * u, QColor('#0a0c12'), ui.LINE)
        if self.preview_img and not self.preview_img.isNull():
            clip = QPainterPath()
            clip.addRoundedRect(prect, 1.4 * u, 1.4 * u)
            p.save()
            p.setClipPath(clip)
            p.drawImage(prect, self.preview_img)
            p.restore()
        else:
            w.text(p, 'Lade Live-Vorschau vom oberen Bildschirm …', prect.x(), prect.center().y() - 1.2 * u,
                   ('u', 1.85, 500), ui.MUTED, prect.width(), 1)

        if self.drag_start and self.drag_cur:
            lx, rx = min(self.drag_start[0], self.drag_cur[0]), max(self.drag_start[0], self.drag_cur[0])
            ty, by = min(self.drag_start[1], self.drag_cur[1]), max(self.drag_start[1], self.drag_cur[1])
            box = [lx, ty, max(0.02, rx - lx), max(0.02, by - ty)]
        else:
            box = self.st.get('crop') or [0.04, 0.63, 0.92, 0.34]
        sr = QRectF(prect.x() + box[0] * pw, prect.y() + box[1] * ph, box[2] * pw, box[3] * ph)
        p.save()
        p.setPen(QPen(ui.FOCUS, .32 * u))
        p.setBrush(ui.faded(ui.FOCUS, .18))
        p.drawRoundedRect(sr, .8 * u, .8 * u)
        p.restore()

    def _paint_packs(self, p, x0, y, cw, bot):
        ui = self._ui()
        w, u = self.w, self.w.u
        st = self.st
        inst = st.get('install') or {}
        if st.get('ready'):
            back = QRectF(x0, y, 13.5 * u, 4.6 * u)
            w.capsule(p, back, ui.RAISED, ui.LINE)
            w.text(p, '‹ Übersetzer', back.x(), back.y(), ('u', 1.72, 600), ui.TEXT, back.width(), 1, 4.6 / 1.72)
            w.hit(back, lambda: (setattr(self, 'show_packs', False), w.update()), name='tr:packs_back')
            w.text(p, 'Offline-Sprachpakete (Deutsch)', x0 + 15 * u, y, ('u', 2.2, 700), ui.TEXT, cw - 15 * u, 0, 4.6 / 2.2)
            y += 5.8 * u
        else:
            card = QRectF(x0, y, cw, 16.5 * u)
            w.box(p, card, 1.8 * u, ui.PANEL, ui.FOCUS)
            w.text(p, 'OFFLINE-SPIELÜBERSETZER EINRICHTEN', x0 + 2.2 * u, y + 1.5 * u, ('u', 1.45, 700, .09), ui.FOCUS, cw - 4.4 * u)
            msg = inst.get('step') if inst.get('running') else (inst.get('error') or 'Lädt einmalig PaddleOCR + Offline-Sprachpakete (Englisch & Japanisch → Deutsch, ~220 MB, kein Cloud-Konto nötig).')
            w.text(p, msg, x0 + 2.2 * u, y + 4.2 * u, ('u', 1.85, 500), ui.WARN if inst.get('error') else ui.TEXT, cw - 4.4 * u, 0, 1.38, 3)
            btn = QRectF(x0 + 2.2 * u, y + 10.6 * u, 36 * u, 4.6 * u)
            w.capsule(p, btn, ui.RAISED if inst.get('running') else ui.FOCUS, ui.LINE if inst.get('running') else None)
            w.text(p, 'Installation läuft …' if inst.get('running') else 'Jetzt installieren (1 Klick)', btn.x(), btn.y(),
                   ('u', 1.8, 700), ui.TEXT if inst.get('running') else ui.INK, btn.width(), 1, 4.6 / 1.8)
            if not inst.get('running'):
                w.hit(btn, lambda: (w.haptic(), self._post({'action': 'install'})), name='tr:install')
            y += 18.0 * u

        for item in (st.get('catalog') or []):
            if y + 6.0 * u > bot:
                break
            r = QRectF(x0, y, cw, 5.6 * u)
            w.box(p, r, 1.4 * u, ui.PANEL, ui.LINE)
            w.text(p, item['title'], x0 + 1.8 * u, y, ('u', 1.9, 600), ui.TEXT, cw - 20 * u, 0, 5.6 / 1.9)
            mb = QRectF(r.right() - 16.5 * u, y + .7 * u, 15.0 * u, 4.2 * u)
            installed = bool(item.get('installed'))
            w.capsule(p, mb, ui.faded(ui.LIVE, .18) if installed else ui.RAISED, ui.LIVE if installed else ui.FOCUS)
            w.text(p, '✓ Bereit' if installed else 'Herunterladen', mb.x(), mb.y(), ('u', 1.62, 700 if installed else 600),
                   ui.LIVE if installed else ui.FOCUS, mb.width(), 1, 4.2 / 1.62)
            if not installed:
                w.hit(mb, lambda pid=item['id']: (w.haptic(), self._post({'action': 'model', 'id': pid})), name='tr_dl:' + item['id'])
            y += 6.4 * u
