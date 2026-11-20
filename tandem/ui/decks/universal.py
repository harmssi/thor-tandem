"""Universal bottom-screen companion deck for every game in Toravo Tandem:
Tabs: Steuerung · Stände · Notizen · Guides · Musik · Cockpit
Keeps tab 0 ('Steuerung') 100% compatible with Tandem's standard in-game controls & RetroAchievements."""
import json, math, os, threading, time
from urllib.parse import quote
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF

TABS = ('Steuerung', 'Stände', 'Notizen', 'Guides', 'Musik', 'Cockpit')
PENS = (('#f5f5f7', 'Weiß'), ('#ffb23e', 'Gold'), ('#2dd4bf', 'Türkis'), ('#ff6b5e', 'Rot'))


def _ago(ts):
    if not ts: return 'leer'
    d = max(0, int(time.time() - ts))
    if d < 60: return 'gerade eben'
    if d < 3600: return f'vor {d // 60} Min.'
    if d < 86400: return f'vor {d // 3600} Std.'
    return f'vor {d // 86400} Tagen'


def _fmt_mins(mins):
    if not mins: return '–'
    h, m = divmod(int(mins), 60)
    return f'~{h} Std. {m:02d} Min.' if h else f'~{m} Min.'


class Deck:
    def __init__(self, w, embed=False):
        self.w, self.embed = w, embed
        self.gid = (w.RUN or {}).get('id') or 'game'
        self.tab = 0
        self.server = self._ui().URL.rstrip('/') + '/'
        # Savestates
        self.slots, self.slots_at = [], 0.0
        # Notes & Sketch
        self.note_mode = 'sketch'  # 'sketch' | 'list'
        self.notes = {'text': '', 'checks': [], 'has_sketch': False}
        self.notes_loaded = False
        self.canvas = QImage(960, 560, QImage.Format.Format_ARGB32_Premultiplied)
        self.canvas.fill(QColor(0, 0, 0, 0))
        self.undo_stack = []
        self.pen_idx = 0
        self.eraser = False
        self.drawing = False
        self.last_pt = None
        self.canvas_rect = QRectF()
        self.save_timer = QTimer(w)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self._upload_sketch)
        # Guides
        self.guides, self.guides_loaded = [], False
        self.open_guide = None  # {'name', 'kind', 'text', 'img', 'zoom', 'px', 'py', 'font'}
        self.pan_start = None
        self.map_rect = QRectF()
        # Music
        self.bgm, self.bgm_at = {'playing': False, 'paused': False, 'track': '', 'vol': 65, 'tracks': [], 'streams': []}, 0.0
        # Cockpit telemetry
        self.tele = None
        self.tele_timer = QTimer(w)
        self.tele_timer.timeout.connect(self._poll_cockpit)
        if os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
            self._fetch_notes()

    def close(self):
        self.tele_timer.stop()
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._upload_sketch()

    def _ui(self):
        import tandem_ui
        return tandem_ui

    def _bg_get(self, path, then, raw=False):
        def work():
            try:
                import urllib.request
                with urllib.request.urlopen(self.server + path.lstrip('/'), timeout=8) as r:
                    data = r.read()
                res = data if raw else json.loads(data)
            except Exception:
                res = None
            self.w.result.emit(then, res)
        threading.Thread(target=work, daemon=True).start()

    def _bg_post(self, path, body, then=None, content_type='application/json'):
        def work():
            try:
                import urllib.request
                payload = body if isinstance(body, bytes) else json.dumps(body).encode()
                req = urllib.request.Request(self.server + path.lstrip('/'), data=payload,
                                             headers={'Content-Type': content_type, 'Origin': self._ui().URL}, method='POST')
                with urllib.request.urlopen(req, timeout=12) as r:
                    res = json.loads(r.read())
            except Exception:
                res = None
            if then: self.w.result.emit(then, res)
        threading.Thread(target=work, daemon=True).start()

    # ---- Tab switching & data loaders --------------------------------------------------------------------------------
    def set_tab(self, idx):
        self.tab = idx
        if idx == 5:
            self._poll_cockpit()
            if not self.tele_timer.isActive(): self.tele_timer.start(2500)
        else:
            self.tele_timer.stop()
        if idx == 1: self._fetch_slots()
        elif idx == 2 and not self.notes_loaded: self._fetch_notes()
        elif idx == 3 and not self.guides_loaded: self._fetch_guides()
        elif idx == 4: self._fetch_bgm()
        self.w.update()

    def _fetch_slots(self):
        self._bg_get('api/savestates', lambda r: setattr(self, 'slots', (r or {}).get('slots') or []))

    def _fetch_notes(self):
        self.notes_loaded = True
        def on_notes(r):
            if isinstance(r, dict) and 'error' not in r: self.notes = r
        self._bg_get(f'api/notes?id={quote(self.gid)}', on_notes)
        def on_png(raw):
            if raw:
                img = QImage()
                if img.loadFromData(raw, 'PNG'):
                    p = QPainter(self.canvas)
                    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                    p.drawImage(self.canvas.rect(), img)
                    p.end()
        self._bg_get(f'api/sketch?id={quote(self.gid)}', on_png, raw=True)

    def _upload_sketch(self):
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        self.canvas.save(buf, 'PNG')
        self._bg_post(f'api/sketch?id={quote(self.gid)}', bytes(ba), content_type='image/png')

    def _fetch_guides(self):
        self.guides_loaded = True
        self._bg_get(f'api/guides?id={quote(self.gid)}', lambda r: setattr(self, 'guides', (r or {}).get('items') or []))

    def _open_guide_item(self, it):
        url = f'api/guide_file?id={quote(self.gid)}&name={quote(it["name"])}'
        if it['kind'] == 'image':
            def on_img(raw):
                if not raw: return
                img = QImage()
                if img.loadFromData(raw):
                    self.open_guide = {'name': it['name'], 'title': it['title'], 'kind': 'image', 'img': img, 'zoom': 1.0, 'px': 0.0, 'py': 0.0}
            self._bg_get(url, on_img, raw=True)
        else:
            def on_txt(r):
                if isinstance(r, dict):
                    self.open_guide = {'name': it['name'], 'title': it['title'], 'kind': 'text', 'text': r.get('text', ''), 'font': 2.0}
            self._bg_get(url, on_txt)

    def _fetch_bgm(self):
        self._bg_get('api/bgm', lambda r: r and setattr(self, 'bgm', r))

    def _poll_cockpit(self):
        self._bg_get('api/telemetry', lambda r: r and setattr(self, 'tele', r))

    # ---- Pointer / Touch interaction (Sketch canvas & Map pan) -------------------------------------------------------
    def _to_canvas(self, pos):
        r = self.canvas_rect
        if r.width() <= 1 or r.height() <= 1: return QPointF(0, 0)
        return QPointF((pos.x() - r.x()) * self.canvas.width() / r.width(),
                       (pos.y() - r.y()) * self.canvas.height() / r.height())

    def press(self, pos):
        if pos is None:
            if self.drawing:
                self.drawing = False
                self.last_pt = None
                self.save_timer.start(550)
            self.pan_start = None
            return
        if self.tab == 2 and self.note_mode == 'sketch' and self.canvas_rect.contains(pos):
            if len(self.undo_stack) >= 8: self.undo_stack.pop(0)
            self.undo_stack.append(self.canvas.copy())
            self.drawing = True
            self.last_pt = self._to_canvas(pos)
            self._stroke_to(self.last_pt)
            self.w.update()
        elif self.tab == 3 and self.open_guide and self.open_guide['kind'] == 'image' and self.map_rect.contains(pos):
            self.pan_start = (pos, self.open_guide['px'], self.open_guide['py'])

    def move(self, pos):
        if self.drawing and self.last_pt is not None:
            pt = self._to_canvas(pos)
            self._stroke_to(pt)
            self.last_pt = pt
            self.w.update()
            return True
        if self.pan_start is not None and self.open_guide and self.open_guide['kind'] == 'image':
            p0, ox, oy = self.pan_start
            self.open_guide['px'] = ox + (pos.x() - p0.x())
            self.open_guide['py'] = oy + (pos.y() - p0.y())
            self.w.update()
            return True
        return False

    def _stroke_to(self, pt):
        p = QPainter(self.canvas)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.eraser:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            pen = QPen(Qt.GlobalColor.transparent, 26, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        else:
            col = QColor(PENS[self.pen_idx][0])
            pen = QPen(col, 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if self.last_pt is None or self.last_pt == pt:
            p.drawPoint(pt)
        else:
            p.drawLine(self.last_pt, pt)
        p.end()

    # ---- Painting ----------------------------------------------------------------------------------------------------
    def paint(self, p):
        ui = self._ui()
        w, u = self.w, self.w.u
        p.fillRect(0, 0, w.width(), w.height(), ui.INK)
        y = self.paint_tabs(p, 1.8 * u)
        self.paint_body(p, y)
        return True

    def paint_tabs(self, p, y):
        ui = self._ui()
        w, u = self.w, self.w.u
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        bar = QRectF(x0, y, cw, 5.2 * u)
        w.capsule(p, bar, ui.PANEL, ui.LINE)
        tw = cw / len(TABS)
        for i, label in enumerate(TABS):
            r = QRectF(x0 + i * tw + .25 * u, y + .25 * u, tw - .5 * u, 4.7 * u)
            on = (i == self.tab)
            if on: w.capsule(p, r, ui.RAISED, ui.faded(ui.FOCUS, .7))
            w.text(p, label, r.x(), r.y(), ('u', 1.72, 700 if on else 500), ui.FOCUS if on else ui.MUTED, r.width(), 1, 4.7 / 1.72)
            w.hit(r, lambda i=i: self.set_tab(i), name='utab:' + label)
        return y + 6.8 * u

    def paint_body(self, p, y):
        self.canvas_rect = QRectF()
        self.map_rect = QRectF()
        if self.tab == 0: self.w.ingame(p, top=y)
        elif self.tab == 1: self._paint_states(p, y)
        elif self.tab == 2: self._paint_notes(p, y)
        elif self.tab == 3: self._paint_guides(p, y)
        elif self.tab == 4: self._paint_music(p, y)
        elif self.tab == 5: self._paint_cockpit(p, y)

    def _quit_footer(self, p):
        ui = self._ui()
        w, u = self.w, self.w.u
        x0, cw, bottom = 2.6 * u, w.width() - 5.2 * u, w.height() - 2.2 * u
        w.button(p, QRectF(x0, bottom - 5.6 * u, cw, 5.6 * u), 'Spiel beenden', w.confirm_quit,
                 ('u', 2.05, 600), ui.WARN, ui.faded(ui.WARN, .14), None, 1.4)
        return bottom - 7.0 * u

    # -- Tab 1: Visual Save-States --
    def _paint_states(self, p, y):
        ui = self._ui()
        w, u = self.w, self.w.u
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        bot = self._quit_footer(p)
        emu = (w.RUN or {}).get('emu') or ''
        w.text(p, 'Speicherstände', x0, y, ('u', 2.8, 700, -.02), ui.TEXT, cw * .65)
        rb = QRectF(x0 + cw - 17 * u, y - .2 * u, 17 * u, 4.4 * u)
        w.capsule(p, rb, ui.RAISED, ui.LINE)
        w.text(p, 'Aktualisieren', rb.x(), rb.y(), ('u', 1.7, 600), ui.TEXT, rb.width(), 1, 4.4 / 1.7)
        w.hit(rb, self._fetch_slots, name='Aktualisieren')
        y += 5.2 * u
        if not self.slots:
            msg = ('Noch keine Schnellstände für dieses Spiel gefunden. Nutze Select + R1 im Spiel oder speichere direkt in einen Slot.'
                   if emu in ('RetroArch', 'DuckStation', 'PPSSPP', 'ARMSX2')
                   else f'{emu} verwaltet Spielstände direkt im Spiel (automatische Sicherung läuft über Tandem).')
            w.text(p, msg, x0, y + 4 * u, ('u', 2.0, 400), ui.MUTED, cw, 0, 1.45, 5)
            return

        area = QRectF(x0, y, cw, bot - y)
        gap = 1.6 * u
        card_w = (cw - gap) / 2
        card_h = 19.5 * u

        def draw_slots(top):
            for idx, sl in enumerate(self.slots):
                col, row = idx % 2, idx // 2
                rx, ry = x0 + col * (card_w + gap), top + row * (card_h + gap)
                r = QRectF(rx, ry, card_w, card_h)
                if r.bottom() < area.top() or r.top() > area.bottom(): continue
                w.box(p, r, 1.6 * u, ui.PANEL, ui.LINE)
                tr = QRectF(rx + 1.0 * u, ry + 1.0 * u, 16 * u, 11.5 * u)
                img = w.images.get(sl['thumb'], int(tr.width()), int(tr.height())) if sl.get('thumb') else None
                if img:
                    clip = QPainterPath(); clip.addRoundedRect(tr, 1.0 * u, 1.0 * u)
                    p.save(); p.setClipPath(clip); p.drawImage(tr.topLeft(), img); p.restore()
                else:
                    w.box(p, tr, 1.0 * u, ui.INK, ui.LINE)
                    w.text(p, 'LEER' if not sl.get('mtime') else 'STAND', tr.x(), tr.y(), ('u', 1.5, 700, .08), ui.MUTED, tr.width(), 1, 11.5 / 1.5)
                tx, tw_txt = tr.right() + 1.4 * u, r.right() - tr.right() - 2.4 * u
                w.text(p, sl['label'], tx, ry + 1.6 * u, ('u', 2.0, 700), ui.TEXT, tw_txt)
                w.text(p, _ago(sl.get('mtime')), tx, ry + 4.8 * u, ('u', 1.7, 400), ui.LIVE if sl.get('mtime') else ui.MUTED, tw_txt)
                if emu == 'RetroArch' and sl['slot'] >= 0:
                    bw = (card_w - 3.0 * u) / 2
                    by = ry + 13.6 * u
                    b_save = QRectF(rx + 1.0 * u, by, bw, 4.6 * u)
                    b_load = QRectF(rx + 2.0 * u + bw, by, bw, 4.6 * u)
                    w.capsule(p, b_save, ui.RAISED, ui.faded(ui.FOCUS, .55))
                    w.text(p, 'Speichern', b_save.x(), b_save.y(), ('u', 1.75, 600), ui.TEXT, bw, 1, 4.6 / 1.75)
                    w.hit(b_save, lambda s=sl['slot']: self._act_slot(s, 'save'), name=f'slot_save:{sl["slot"]}')
                    w.capsule(p, b_load, ui.RAISED if sl.get('mtime') else ui.INK, ui.LINE)
                    w.text(p, 'Laden', b_load.x(), b_load.y(), ('u', 1.75, 600), ui.TEXT if sl.get('mtime') else ui.MUTED, bw, 1, 4.6 / 1.75)
                    if sl.get('mtime'):
                        w.hit(b_load, lambda s=sl['slot']: self._act_slot(s, 'load'), name=f'slot_load:{sl["slot"]}')
            rows = (len(self.slots) + 1) // 2
            return top + rows * (card_h + gap)

        w.scroller(p, 'ustates', area, draw_slots)

    def _act_slot(self, slot, mode):
        def done(r):
            if r and r.get('ok'):
                self.w.toast(f'Slot {slot} {"gespeichert" if mode == "save" else "geladen"}.')
                QTimer.singleShot(700, self._fetch_slots)
            elif r and r.get('error'):
                self.w.toast(r['error'])
        self._bg_post('api/savestates', {'slot': slot, 'mode': mode}, done)

    # -- Tab 2: Per-Game Notes, Checklist & Finger Sketch --
    def _paint_notes(self, p, y):
        ui = self._ui()
        w, u = self.w, self.w.u
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        bot = self._quit_footer(p)
        # Mode switch pills + tools
        for idx, (m_id, lbl) in enumerate((('sketch', 'Skizzenblock'), ('list', 'Checkliste & Notiz'))):
            mr = QRectF(x0 + idx * 21.5 * u, y, 20.5 * u, 4.6 * u)
            on = (self.note_mode == m_id)
            w.capsule(p, mr, ui.RAISED if on else ui.PANEL, ui.FOCUS if on else ui.LINE)
            w.text(p, lbl, mr.x(), mr.y(), ('u', 1.75, 600), ui.TEXT if on else ui.MUTED, mr.width(), 1, 4.6 / 1.75)
            w.hit(mr, lambda m_id=m_id: setattr(self, 'note_mode', m_id), name='nmode:' + m_id)

        if self.note_mode == 'sketch':
            # Pen palette + Eraser + Undo + Clear
            px = x0 + 44.5 * u
            for ci, (hex_c, cname) in enumerate(PENS):
                cr = QRectF(px + ci * 5.0 * u, y + .3 * u, 4.0 * u, 4.0 * u)
                sel = (not self.eraser and self.pen_idx == ci)
                p.setPen(QPen(ui.TEXT if sel else ui.LINE, (.38 if sel else .16) * u))
                p.setBrush(QColor(hex_c))
                p.drawEllipse(cr)
                w.hit(cr.adjusted(-.4 * u, -.4 * u, .4 * u, .4 * u),
                      lambda ci=ci: (setattr(self, 'pen_idx', ci), setattr(self, 'eraser', False)), name='pen:' + cname)
            ex = px + len(PENS) * 5.0 * u + .8 * u
            for lbl, act, hi in (('Radierer', lambda: setattr(self, 'eraser', not self.eraser), self.eraser),
                                 ('Zurück', self._undo_sketch, False),
                                 ('Leeren', self._clear_sketch, False)):
                bw = w.width_of(lbl, ('u', 1.65, 600)) + 2.4 * u
                if ex + bw > x0 + cw: break
                br = QRectF(ex, y, bw, 4.6 * u)
                w.capsule(p, br, ui.RAISED if hi else ui.PANEL, ui.FOCUS if hi else ui.LINE)
                w.text(p, lbl, br.x(), br.y(), ('u', 1.65, 600), ui.TEXT, bw, 1, 4.6 / 1.65)
                w.hit(br, act, name='sketch:' + lbl)
                ex += bw + .8 * u
            y += 5.8 * u
            crect = QRectF(x0, y, cw, max(16 * u, bot - y))
            self.canvas_rect = crect
            w.box(p, crect, 1.8 * u, QColor('#0c0d12'), ui.LINE)
            # Subtle dot grid for dungeon/map sketching
            p.setPen(QPen(QColor(255, 255, 255, 18), max(1.0, .16 * u)))
            step = 4.0 * u
            gx = crect.x() + step
            while gx < crect.right() - u:
                gy = crect.y() + step
                while gy < crect.bottom() - u:
                    p.drawPoint(QPointF(gx, gy))
                    gy += step
                gx += step
            clip = QPainterPath(); clip.addRoundedRect(crect, 1.8 * u, 1.8 * u)
            p.save(); p.setClipPath(clip)
            p.drawImage(crect, self.canvas)
            p.restore()
            return

        # Checklist & Text mode
        b_add = QRectF(x0 + cw - 20 * u, y, 20 * u, 4.6 * u)
        w.capsule(p, b_add, ui.FOCUS)
        w.text(p, '+ Punkt', b_add.x(), b_add.y(), ('u', 1.8, 700), ui.INK, b_add.width(), 1, 4.6 / 1.8)
        w.hit(b_add, lambda: w.ask('Neuer Checklisten-Punkt', '', False,
                                   lambda v: v.strip() and self._bg_post('api/notes', {'id': self.gid, 'add_check': v}, lambda r: r and setattr(self, 'notes', r))),
              name='add_check')
        y += 5.8 * u
        area = QRectF(x0, y, cw, bot - y)

        def draw_list(top):
            cy = top
            # Free-form note card
            note_txt = self.notes.get('text') or ''
            nh = max(8.5 * u, (len(w.wrap(note_txt, ('u', 1.9, 400), cw - 4 * u, 6)) * 2.6 + 4.4) * u) if note_txt else 7.2 * u
            nr = QRectF(x0, cy, cw, nh)
            w.box(p, nr, 1.6 * u, ui.PANEL, ui.LINE)
            w.text(p, 'NOTIZ ZUM SPIEL (ANTIPPEN ZUM BEARBEITEN)', x0 + 1.8 * u, cy + 1.1 * u, ('u', 1.4, 700, .08), ui.FOCUS, cw - 3.6 * u)
            w.text(p, note_txt or 'Hier Codes, Fundorte, Passwörter oder eigene Gedanken festhalten …',
                   x0 + 1.8 * u, cy + 3.4 * u, ('u', 1.9, 400), ui.TEXT if note_txt else ui.MUTED, cw - 3.6 * u, 0, 1.35, 6)
            w.hit(nr, lambda: w.ask('Notiz zum Spiel', self.notes.get('text', ''), False,
                                    lambda v: self._bg_post('api/notes', {'id': self.gid, 'text': v}, lambda r: r and setattr(self, 'notes', r))),
                  name='edit_note')
            cy += nh + 1.4 * u
            checks = self.notes.get('checks') or []
            for idx, item in enumerate(checks):
                rr = QRectF(x0, cy, cw, 5.4 * u)
                w.box(p, rr, 1.3 * u, ui.PANEL, ui.LINE)
                done = bool(item.get('done'))
                cb = QRectF(x0 + 1.4 * u, cy + 1.2 * u, 3.0 * u, 3.0 * u)
                w.box(p, cb, .7 * u, ui.LIVE if done else ui.INK, None if done else ui.MUTED)
                if done:
                    w.text(p, '✓', cb.x(), cb.y(), ('u', 1.9, 700), ui.INK, cb.width(), 1, 3.0 / 1.9)
                w.text(p, item['t'], cb.right() + 1.6 * u, cy, ('u', 1.95, 500), ui.MUTED if done else ui.TEXT, cw - 12 * u, 0, 5.4 / 1.95)
                del_r = QRectF(rr.right() - 5.2 * u, cy + .7 * u, 4.2 * u, 4.0 * u)
                w.text(p, '×', del_r.x(), del_r.y(), ('u', 2.4, 600), ui.MUTED, del_r.width(), 1, 4.0 / 2.4)
                w.hit(QRectF(x0, cy, cw - 6 * u, 5.4 * u),
                      lambda i=idx: self._bg_post('api/notes', {'id': self.gid, 'toggle_idx': i}, lambda r: r and setattr(self, 'notes', r)),
                      name=f'chk:{idx}')
                w.hit(del_r, lambda i=idx: self._bg_post('api/notes', {'id': self.gid, 'del_idx': i}, lambda r: r and setattr(self, 'notes', r)),
                      name=f'chk_del:{idx}')
                cy += 6.2 * u
            return cy

        w.scroller(p, 'unotes', area, draw_list)

    def _undo_sketch(self):
        if self.undo_stack:
            self.canvas = self.undo_stack.pop()
            self.save_timer.start(300)

    def _clear_sketch(self):
        self.undo_stack.append(self.canvas.copy())
        self.canvas.fill(QColor(0, 0, 0, 0))
        self._bg_post(f'api/sketch?id={quote(self.gid)}', b'', content_type='image/png')

    # -- Tab 3: Guides, Maps & Wiki Reader --
    def _paint_guides(self, p, y):
        ui = self._ui()
        w, u = self.w, self.w.u
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        bot = self._quit_footer(p)
        if self.open_guide:
            og = self.open_guide
            back = QRectF(x0, y, 11 * u, 4.6 * u)
            w.capsule(p, back, ui.RAISED, ui.LINE)
            w.text(p, '‹ Liste', back.x(), back.y(), ('u', 1.8, 600), ui.TEXT, back.width(), 1, 4.6 / 1.8)
            w.hit(back, lambda: setattr(self, 'open_guide', None), name='guide_back')
            w.text(p, og['title'], x0 + 12.4 * u, y, ('u', 2.2, 700), ui.TEXT, cw - 36 * u, 0, 4.6 / 2.2)
            if og['kind'] == 'image':
                for bi, (lbl, dz) in enumerate((('−', -.4), ('1:1', 0.0), ('+', .4))):
                    zr = QRectF(x0 + cw - (3 - bi) * 7.2 * u, y, 6.6 * u, 4.6 * u)
                    w.capsule(p, zr, ui.RAISED, ui.LINE)
                    w.text(p, lbl, zr.x(), zr.y(), ('u', 1.85, 700), ui.TEXT, zr.width(), 1, 4.6 / 1.85)
                    def step_z(dz=dz):
                        if dz == 0.0: og['zoom'], og['px'], og['py'] = 1.0, 0.0, 0.0
                        else: og['zoom'] = max(1.0, min(4.5, round(og['zoom'] + dz, 2)))
                    w.hit(zr, step_z, name='zoom:' + lbl)
                y += 5.8 * u
                mrect = QRectF(x0, y, cw, bot - y)
                self.map_rect = mrect
                w.box(p, mrect, 1.6 * u, QColor('#0a0b0f'), ui.LINE)
                img = og['img']
                scale = min(mrect.width() / max(1, img.width()), mrect.height() / max(1, img.height())) * og['zoom']
                dw, dh = img.width() * scale, img.height() * scale
                dx = mrect.center().x() - dw / 2 + og['px']
                dy = mrect.center().y() - dh / 2 + og['py']
                clip = QPainterPath(); clip.addRoundedRect(mrect, 1.6 * u, 1.6 * u)
                p.save(); p.setClipPath(clip); p.drawImage(QRectF(dx, dy, dw, dh), img); p.restore()
            else:
                for bi, (lbl, df) in enumerate((('A−', -.25), ('A+', .25))):
                    fr = QRectF(x0 + cw - (2 - bi) * 7.5 * u, y, 6.8 * u, 4.6 * u)
                    w.capsule(p, fr, ui.RAISED, ui.LINE)
                    w.text(p, lbl, fr.x(), fr.y(), ('u', 1.8, 700), ui.TEXT, fr.width(), 1, 4.6 / 1.8)
                    w.hit(fr, lambda df=df: og.update(font=max(1.5, min(3.2, og['font'] + df))), name='gfont:' + lbl)
                y += 5.8 * u
                area = QRectF(x0, y, cw, bot - y)
                w.box(p, area, 1.6 * u, ui.PANEL, ui.LINE)
                inner = area.adjusted(2.0 * u, 1.4 * u, -2.0 * u, -1.4 * u)
                fsz = og['font']
                paras = og['text'].splitlines()

                def draw_txt(top):
                    cy = top
                    for para in paras:
                        if not para.strip():
                            cy += 1.4 * u; continue
                        cy += w.text(p, para, inner.x(), cy, ('u', fsz, 400), ui.TEXT, inner.width(), 0, 1.42, None) + .5 * u
                    return cy

                w.scroller(p, 'uguide:' + og['name'], inner, draw_txt)
            return

        w.text(p, 'Karten & Komplettlösungen', x0, y, ('u', 2.6, 700, -.02), ui.TEXT, cw * .55)
        b_wiki = QRectF(x0 + cw - 36 * u, y - .2 * u, 18.5 * u, 4.6 * u)
        b_ask = QRectF(x0 + cw - 16.5 * u, y - .2 * u, 16.5 * u, 4.6 * u)
        w.capsule(p, b_wiki, ui.FOCUS)
        w.text(p, 'Spiel-Wiki laden', b_wiki.x(), b_wiki.y(), ('u', 1.7, 700), ui.INK, b_wiki.width(), 1, 4.6 / 1.7)
        w.hit(b_wiki, lambda: self._fetch_wiki((w.RUN or {}).get('t', '')), name='wiki_auto')
        w.capsule(p, b_ask, ui.RAISED, ui.LINE)
        w.text(p, 'Thema suchen', b_ask.x(), b_ask.y(), ('u', 1.7, 600), ui.TEXT, b_ask.width(), 1, 4.6 / 1.7)
        w.hit(b_ask, lambda: w.ask('Wiki / Guide suchen', (w.RUN or {}).get('t', ''), False, self._fetch_wiki), name='wiki_search')
        y += 5.8 * u
        if not self.guides:
            w.text(p, 'Noch keine Karten oder Guides zu diesem Spiel gespeichert.\n'
                      '• Tippe oben auf „Spiel-Wiki laden“ für eine Offline-Übersicht.\n'
                      '• Eigene Kartenbilder (PNG/JPG) oder Lösungen (TXT/MD) kannst du bequem am Handy/Mac über die Tandem-Webseite hochladen.',
                   x0, y + 2 * u, ('u', 1.95, 400), ui.MUTED, cw, 0, 1.48, 7)
            return
        area = QRectF(x0, y, cw, bot - y)

        def draw_guides(top):
            cy = top
            for it in self.guides:
                r = QRectF(x0, cy, cw, 6.2 * u)
                w.box(p, r, 1.4 * u, ui.PANEL, ui.LINE)
                badge = 'KARTE / BILD' if it['kind'] == 'image' else 'TEXT / GUIDE'
                w.text(p, badge, x0 + 1.8 * u, cy + .9 * u, ('u', 1.35, 700, .08), ui.FOCUS, 22 * u)
                w.text(p, it['title'], x0 + 1.8 * u, cy + 2.8 * u, ('u', 2.05, 600), ui.TEXT, cw - 12 * u)
                w.text(p, '›', r.right() - 4.0 * u, cy, ('u', 2.8, 600), ui.MUTED, 3 * u, 1, 6.2 / 2.8)
                w.hit(r, lambda it=it: self._open_guide_item(it), name='guide:' + it['name'])
                cy += 7.1 * u
            return cy

        w.scroller(p, 'uguidelist', area, draw_guides)

    def _fetch_wiki(self, query):
        if not query or not query.strip(): return
        self.w.toast(f'Lade Übersicht zu „{query.strip()}“ …')
        def done(r):
            if r and r.get('ok'):
                self.guides = r.get('items') or []
                self.w.toast(f'Gespeichert: {r.get("title")}')
            elif r and r.get('error'):
                self.w.toast(r['error'])
        self._bg_post('api/guides', {'id': self.gid, 'q': query.strip()}, done)

    # -- Tab 4: Background Music & PipeWire Stream Mixer --
    def _paint_music(self, p, y):
        ui = self._ui()
        w, u = self.w, self.w.u
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        bot = self._quit_footer(p)
        card = QRectF(x0, y, cw, 12.6 * u)
        w.box(p, card, 1.8 * u, ui.PANEL, ui.LINE)
        tr = self.bgm.get('track') or 'Keine Hintergrundmusik aktiv'
        st_lbl = '● SPIELT IM HINTERGRUND' if self.bgm.get('playing') else ('PAUSIERT' if self.bgm.get('paused') else 'BEREIT')
        w.text(p, st_lbl, x0 + 2.0 * u, y + 1.2 * u, ('u', 1.4, 700, .1), ui.LIVE if self.bgm.get('playing') else ui.MUTED, cw - 4 * u)
        w.text(p, tr, x0 + 2.0 * u, y + 3.3 * u, ('u', 2.3, 700), ui.TEXT, cw - 4 * u)
        btns = [('⏮', 'prev'), ('⏸ Pause' if self.bgm.get('playing') else '▶ Abspielen', 'toggle'), ('⏭', 'next'), ('■ Stopp', 'stop')]
        bx = x0 + 2.0 * u
        for lbl, act in btns:
            bw = (15.5 if len(lbl) > 3 else 7.2) * u
            br = QRectF(bx, y + 7.0 * u, bw, 4.4 * u)
            hi = (act == 'toggle')
            w.capsule(p, br, ui.FOCUS if hi else ui.RAISED, None if hi else ui.LINE)
            w.text(p, lbl, br.x(), br.y(), ('u', 1.8, 700 if hi else 600), ui.INK if hi else ui.TEXT, bw, 1, 4.4 / 1.8)
            w.hit(br, lambda act=act: self._bg_post('api/bgm', {'action': act}, lambda r: r and (setattr(self, 'bgm', r), r.get('error') and w.toast(r['error']))),
                  name='bgm:' + act)
            bx += bw + 1.0 * u
        # BGM Volume step pills on right of card
        vx = card.right() - 23 * u
        w.text(p, f'Musik {self.bgm.get("vol", 65)} %', vx, y + 7.0 * u, ('u', 1.75, 600), ui.MUTED, 11.5 * u, 0, 4.4 / 1.75)
        for vi, (vl, dv) in enumerate((('−', -10), ('+', 10))):
            vr = QRectF(card.right() - (2 - vi) * 5.2 * u - .8 * u, y + 7.0 * u, 4.6 * u, 4.4 * u)
            w.capsule(p, vr, ui.RAISED, ui.LINE)
            w.text(p, vl, vr.x(), vr.y(), ('u', 2.0, 700), ui.TEXT, vr.width(), 1, 4.4 / 2.0)
            w.hit(vr, lambda dv=dv: self._bg_post('api/bgm', {'action': 'vol', 'vol': max(0, min(100, self.bgm.get('vol', 65) + dv))},
                                                  lambda r: r and setattr(self, 'bgm', r)), name='bgmvol:' + vl)
        y += 13.8 * u
        # PipeWire Game Stream independent mixer (if any non-bgm stream is active)
        game_streams = [s for s in (self.bgm.get('streams') or []) if not s.get('bgm') and s.get('vol') is not None]
        if game_streams:
            gs = game_streams[0]
            gr = QRectF(x0, y, cw, 5.4 * u)
            w.box(p, gr, 1.4 * u, ui.PANEL, ui.LINE)
            w.text(p, f'Spielton ({gs["name"]}) · {gs["vol"]} %', x0 + 1.8 * u, y, ('u', 1.85, 600), ui.TEXT, cw - 15 * u, 0, 5.4 / 1.85)
            for vi, (vl, dv) in enumerate((('−', -10), ('+', 10))):
                vr = QRectF(gr.right() - (2 - vi) * 5.4 * u - .8 * u, y + .6 * u, 4.6 * u, 4.2 * u)
                w.capsule(p, vr, ui.RAISED, ui.LINE)
                w.text(p, vl, vr.x(), vr.y(), ('u', 2.0, 700), ui.TEXT, vr.width(), 1, 4.2 / 2.0)
                w.hit(vr, lambda sid=gs['id'], nv=max(0, min(100, gs['vol'] + dv)):
                      self._bg_post('api/bgm', {'action': 'stream_vol', 'id': sid, 'vol': nv}, lambda *_: self._fetch_bgm()),
                      name='gvol:' + vl)
            y += 6.4 * u
        tracks = self.bgm.get('tracks') or []
        if not tracks:
            w.text(p, 'Lege eigene MP3/FLAC/OGG-Lieder in ~/Music oder auf der SD-Karte unter Music/ ab, um sie im Spiel getrennt vom Spielton zu mischen.',
                   x0, y + 1.5 * u, ('u', 1.9, 400), ui.MUTED, cw, 0, 1.45, 4)
            return
        area = QRectF(x0, y, cw, bot - y)

        def draw_tracks(top):
            cy = top
            for t in tracks:
                r = QRectF(x0, cy, cw, 5.2 * u)
                active = (t['title'] == self.bgm.get('track'))
                w.box(p, r, 1.2 * u, ui.RAISED if active else ui.PANEL, ui.FOCUS if active else ui.LINE)
                w.text(p, ('▶ ' if active else '') + t['title'], x0 + 1.6 * u, cy, ('u', 1.9, 600 if active else 500),
                       ui.FOCUS if active else ui.TEXT, cw - 18 * u, 0, 5.2 / 1.9)
                w.text(p, t['sub'], r.right() - 16 * u, cy, ('u', 1.65, 400), ui.MUTED, 14.4 * u, 2, 5.2 / 1.65)
                w.hit(r, lambda path=t['path']: self._bg_post('api/bgm', {'action': 'play', 'path': path}, lambda res: res and setattr(self, 'bgm', res)),
                      name='track:' + t['title'])
                cy += 5.9 * u
            return cy

        w.scroller(p, 'ubgm', area, draw_tracks)

    # -- Tab 5: Live Hardware Cockpit (Wattage, Playtime Left, Thermals & Sparklines) --
    def _paint_cockpit(self, p, y):
        ui = self._ui()
        w, u = self.w, self.w.u
        x0, cw = 2.6 * u, w.width() - 5.2 * u
        bot = self._quit_footer(p)
        t = self.tele or {}
        bat = t.get('battery') or w.BATT or {}
        hist = t.get('hist') or {}
        gap = 1.5 * u
        hw = (cw - gap) / 2
        ch = 15.5 * u

        # 4 Telemetry Cards (2x2 grid)
        lvl = bat.get('level')
        mins = bat.get('mins_left')
        chg = bat.get('charging')
        c1_val = f'{lvl} %' if lvl is not None else '–'
        c1_sub = 'Lädt am Netzteil' if chg else (f'Restspielzeit {_fmt_mins(mins)}' if mins else 'Berechne Restlaufzeit …')

        watts = bat.get('watts')
        c2_val = f'{watts:.1f} W'.replace('.', ',') if watts is not None else '– W'
        c2_sub = 'Netzbetrieb' if chg else 'Aktuelle Leistungsaufnahme'

        temp, fan = t.get('temp'), t.get('fan')
        c3_val = f'{temp} °C' if temp is not None else '– °C'
        c3_sub = f'Lüfter {fan} U/min' if fan is not None else 'SoC-Temperatur'

        cpu, ru, rt = t.get('cpu'), t.get('ram_used'), t.get('ram_total')
        c4_val = f'{cpu:.0f} %' if cpu is not None else '– %'
        c4_sub = f'Speicher {ru:.1f} / {rt:.1f} GB'.replace('.', ',') if (ru is not None and rt) else 'Prozessorlast'

        cards = [
            ('AKKU & LAUFZEIT', c1_val, c1_sub, None, ui.LIVE),
            ('VERBRAUCH', c2_val, c2_sub, hist.get('watts'), ui.FOCUS),
            ('TEMPERATUR & LÜFTER', c3_val, c3_sub, hist.get('temp'), QColor('#ff7a45')),
            ('CPU & ARBEITSSPEICHER', c4_val, c4_sub, hist.get('cpu'), QColor('#38bdf8')),
        ]
        for idx, (head, val, sub, series, col) in enumerate(cards):
            cx, cy = x0 + (idx % 2) * (hw + gap), y + (idx // 2) * (ch + gap)
            r = QRectF(cx, cy, hw, ch)
            w.box(p, r, 1.8 * u, ui.PANEL, ui.LINE)
            w.text(p, head, cx + 1.8 * u, cy + 1.3 * u, ('u', 1.35, 700, .1), ui.MUTED, hw - 3.6 * u)
            w.text(p, val, cx + 1.8 * u, cy + 3.6 * u, ('u', 3.6, 700, -.02), ui.TEXT, hw * .58)
            w.text(p, sub, cx + 1.8 * u, cy + 9.2 * u, ('u', 1.75, 500), col if idx == 0 and not chg else ui.MUTED, hw - 3.6 * u)
            if series and len(series) >= 2:
                sr = QRectF(cx + hw * .56, cy + 3.8 * u, hw * .39, 4.6 * u)
                lo, hi = min(series), max(series)
                span = max(1.0, hi - lo)
                pts = [QPointF(sr.x() + i * sr.width() / (len(series) - 1),
                               sr.bottom() - ((v - lo) / span) * sr.height()) for i, v in enumerate(series)]
                p.save()
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                p.setPen(QPen(col, .32 * u, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawPolyline(QPolygonF(pts))
                p.restore()

        py = y + 2 * (ch + gap) + .6 * u
        if py + 5.2 * u <= bot:
            cur_p = (w.RUN or {}).get('profile') or t.get('profile') or 'Balanced'
            w.text(p, 'Profil (dieses Spiel):', x0, py, ('u', 1.85, 600), ui.MUTED, 28 * u, 0, 4.8 / 1.85)
            px = x0 + 26 * u
            pw = (cw - 26 * u - 2 * u) / 3
            for pid, plbl in (('Eco', 'Sparsam'), ('Balanced', 'Ausgewogen'), ('Performance', 'Leistung')):
                pr = QRectF(px, py, pw, 4.8 * u)
                on = (cur_p == pid)
                w.capsule(p, pr, ui.RAISED if on else ui.PANEL, ui.FOCUS if on else ui.LINE)
                w.text(p, plbl, pr.x(), pr.y(), ('u', 1.8, 700 if on else 500), ui.FOCUS if on else ui.TEXT, pw, 1, 4.8 / 1.8)
                w.hit(pr, lambda pid=pid: w.post('api/gameopt', {'profile': pid}, then=lambda *_: self._poll_cockpit()), name='cprof:' + pid)
                px += pw + u
