"""Diablo III: Eternal Collection – Sanktuario Nephalem-Altar (01001B300B9BE000).
Rebuilds Tobias's Android ThorDeck natively in QPainter for PeanutsNative on Linux:
- Obsidian & blood-crimson gothic altar with rising hellfire embers & class-colored resource essence
- Live zero-focus touch Skill Altar (Slots 1–6: Y, B, A, X, ZL, ZR), giant Heiltrank globe (R),
  Stadtportal (▶), Ziel fixieren (L), Inventar (+), Fertigkeiten (+,R), Quests (+,L), Karte (▼), Spielmenü (−)
- Kanai's Cube, Legendary Gems & Class Endgame Set reference for all 7 Sanctuary classes
- Interactive Season Journey / Torment / Primal Ancient (GR70) progression tracker."""
import math, random, time
from PySide6.QtCore import QPointF, QRectF, QTimer
from PySide6.QtGui import QBrush, QLinearGradient, QPainterPath, QPen, QPolygonF, QRadialGradient
from decks.native_base import CompanionBase, qcol

CLASSES = (
    ('barbar', 'Barbar', 'Wut', '#ea580c', ' Ödlande-Wirbelwind', 'Ambos Stolz · Kanalisierungs-Mantel · Band der Macht', 'Verderben der Gefangenen · Taeguk · Stärke der Schlichtheit'),
    ('kreuzritter', 'Kreuzritter', 'Zorn', '#eab308', 'Aegis der Tapferkeit', 'Schicksal der Grausamen · Steinpanzerhandschuhe · Prunkring', 'Gefangene · Geschlagene · Gogok der Schnelligkeit'),
    ('daemonenjaeger', 'Dämonenjäger', 'Hass / Disz.', '#a855f7', 'Getriebe des Schreckens', 'Morgendämmerung · Tiefenwühler · Zusammenkunft der Elemente', 'Stärke der Schlichtheit · Gefangene · Taeguk'),
    ('moench', 'Mönch', 'Geisteskraft', '#f59e0b', 'Innas Mantra (Myst. Verbündeter)', 'Fliegender Drache · Bindungen der niederen Götter · Prunkring', 'Vollstrecker · Gefangene · Geschlagene'),
    ('totenbeschwoerer', 'Totenbeschw.', 'Essenz', '#14b8a6', 'Trag’Ouls Todesnova', 'Blutstromklinge · Mantel des Kanalisierens · Krysbin-Urteil', 'Gefangene · Geschlagene · Zeis Stein der Rache'),
    ('hexendoktor', 'Hexendoktor', 'Mana', '#3b82f6', 'Mundunugus Geisterfeuer', 'Der Barbier · Gevatter Grins · Ring der Leere', 'Vollstrecker · Gefangene · Verderben der Mächtigen'),
    ('zauberer', 'Zauberer', 'Arkankraft', '#ec4899', 'Tal Rashas Kometensturm', 'Großwesir · Nilfurs Prahlerei · Halo von Karini', 'Gefangene · Zeis Stein · Geschlagene'),
)

JOURNEY = (
    ('d3_kanai', 'Kanais Würfel in den Ruinen von Sescheron (Akt III) bergen'),
    ('d3_bounties', 'Kopfgeld-Runde Akt I–V (Prunkring & Würfel-Materialien)'),
    ('d3_keywardens', 'Schlüsselhüter Akt I–IV -> Höllenfeueramulett schmieden'),
    ('d3_set6', 'Vollständigen 6er-Klassenset-Bonus aktivieren (Haedrigs Gabe)'),
    ('d3_gems25', '3 Legendäre Edelsteine auf Rang 25+ aufwerten'),
    ('d3_t16', 'Nephalemportal auf Qual XVI unter 4 Minuten abschließen'),
    ('d3_gr70', 'Großes Nephalemportal Stufe 70 solo -> Archaische Items freigeschaltet!'),
    ('d3_echo', 'Hallender Alptraum (Flüsternde Buße Rang 125 zum Caldesann-Veredeln)'),
    ('d3_altar', 'Altar der Riten im Neu-Tristram-Lager vollständig entsiegeln'),
    ('d3_gr110', 'Großes Nephalemportal Stufe 110+ meistern'),
)


class Deck(CompanionBase):
    KEY = 'd3'
    TABS = ('Altar', 'Klassen & Würfel', 'Saison & Qual', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'd3')
        rng = random.Random(13)
        self.embers = [[rng.random(), rng.random(), 0.04 + rng.random() * 0.08, 0.4 + rng.random() * 0.9, rng.random() * 6.28] for _ in range(28)]
        self.t0 = time.monotonic()
        self.anim = QTimer(w)
        self.anim.timeout.connect(self._tick)
        import os
        if os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
            self.anim.start(90)

    def _tick(self):
        if self.tab == 0:
            self.w.update()

    def close(self):
        self.anim.stop()
        super().close()

    def _cur_class(self):
        cid = self.get_val('cls', 'totenbeschwoerer')
        return next((c for c in CLASSES if c[0] == cid), CLASSES[4])

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#090506'))

        # Sanctuary crimson-obsidian top header + diamond gothic rule
        hdr = QRectF(0, 0, W, 11.2 * u)
        g = QLinearGradient(0, 0, 0, hdr.height())
        g.setColorAt(0.0, qcol('#26090c'))
        g.setColorAt(1.0, qcol('#0d0607'))
        p.fillRect(hdr, g)

        cls = self._cur_class()
        res_col = qcol(cls[3])

        # Rising embers in background on Altar tab
        if self.tab == 0:
            dt = time.monotonic() - self.t0
            for ex, ey, spd, sz, ph in self.embers:
                yy = (ey - dt * spd) % 1.0
                xx = ex + math.sin(dt * 1.4 + ph) * 0.015
                alpha = max(0.05, min(0.55, (1.0 - abs(yy - 0.5) * 1.8) * 0.5))
                p.setPen(qcol('#000000', 0))
                p.setBrush(qcol('#f97316' if sz > 0.8 else '#dc2626', alpha))
                p.drawEllipse(QPointF(xx * W, hdr.bottom() + yy * (H - hdr.bottom())), sz * 0.36 * u, sz * 0.36 * u)

        # Sanctuary diamond emblem + title
        cx, cy = 4.2 * u, 3.6 * u
        gem = QPolygonF([QPointF(cx, cy - 2.1 * u), QPointF(cx + 1.45 * u, cy), QPointF(cx, cy + 2.1 * u), QPointF(cx - 1.45 * u, cy)])
        p.setPen(QPen(qcol('#d6a553'), 1.6))
        p.setBrush(qcol('#991b1b'))
        p.drawPolygon(gem)
        w.text(p, 'DIABLO III · SANKTUARIO-ALTAR', 6.8 * u, 1.3 * u, ('s', 2.45, 700, .04), qcol('#f3dfb6'), W * 0.62)
        w.text(p, f'{cls[1]}  ·  Ressource: {cls[2]}', 6.8 * u, 4.15 * u, ('u', 1.6, 600), res_col, W * 0.55)

        # GR / Torment badge on top right
        gr = int(self.get_val('gr_best', 70) or 70)
        gr_box = QRectF(W - 24.5 * u, 1.2 * u, 21.8 * u, 4.4 * u)
        self.chamfer_box(p, gr_box, 0.7 * u, qcol('#1a0c0e'), qcol('#d6a553', 0.65), 1.3)
        w.text(p, f'GR-Stufe {gr}  (− / +)', gr_box.x(), gr_box.y(), ('m', 1.55, 700), qcol('#f3dfb6'), gr_box.width(), 1, 4.4 / 1.55)
        w.hit(QRectF(gr_box.x(), gr_box.y(), gr_box.width() * 0.5, gr_box.height()), lambda: self.bump_val('gr_best', -5, 1, 150), name='d3_gr_dn')
        w.hit(QRectF(gr_box.center().x(), gr_box.y(), gr_box.width() * 0.5, gr_box.height()), lambda: self.bump_val('gr_best', 5, 1, 150), name='d3_gr_up')

        # Gothic beveled tab bar
        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        ty = 6.3 * u
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, ty, tw - 0.6 * u, 4.2 * u)
            on = (i == self.tab)
            self.chamfer_box(p, r, 0.65 * u, qcol('#3b1014') if on else qcol('#160b0d'),
                             qcol('#eab308') if on else qcol('#4a2c2a'), 1.6 if on else 1.0)
            w.text(p, lbl.upper(), r.x(), r.y(), ('d', 1.85, 700, .05), qcol('#fef08a') if on else qcol('#b89f8d'), r.width(), 1, 4.2 / 1.85)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'd3_tab:{lbl}')

        p.setPen(QPen(qcol('#784c24', 0.75), 1.2))
        p.drawLine(QPointF(0, hdr.bottom()), QPointF(W, hdr.bottom()))

        top = hdr.bottom() + 1.4 * u
        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#090506')
            return True
        if self.tab == 0:
            self._paint_altar(p, top, cls, res_col)
        elif self.tab == 1:
            self._paint_builds(p, top, cls, res_col)
        else:
            self._paint_journey(p, top)
        return True

    def _paint_altar(self, p, y, cls, res_col):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        # Class selector strip (tints resource ring & build)
        cw_btn = cw / len(CLASSES)
        for i, c in enumerate(CLASSES):
            r = QRectF(x0 + i * cw_btn + 0.2 * u, y, cw_btn - 0.4 * u, 4.1 * u)
            on = (c[0] == cls[0])
            self.chamfer_box(p, r, 0.5 * u, qcol(c[3], 0.28) if on else qcol('#150b0d'),
                             qcol(c[3]) if on else qcol('#3a2322'), 1.5 if on else 1.0)
            w.text(p, c[1], r.x(), r.y(), ('d', 1.58, 700), qcol('#fff7ed') if on else qcol('#a89080'), r.width(), 1, 4.1 / 1.58)
            w.hit(r, lambda cid=c[0]: self.set_val('cls', cid), name=f'd3_cls:{c[0]}')
        y += 5.3 * u

        # Left side: 6 Nephalem Skill Runes (2 rows x 3, matching Switch slots Y, B, A, X, ZL, ZR)
        skills = (
            ('1', 'Y', 'Primär / Slot 1', 'Y'),
            ('2', 'B', 'Sekundär / Slot 2', 'B'),
            ('3', 'A', 'Aktion / Slot 3', 'A'),
            ('4', 'X', 'Defensiv / Slot 4', 'X'),
            ('5', 'ZL', 'Macht / Slot 5', 'ZL'),
            ('6', 'ZR', 'Meister / Slot 6', 'ZR'),
        )
        left_w = cw * 0.54
        sw = (left_w - 2.0 * u) / 3
        sh = 11.4 * u
        for idx, (num, key_lbl, role_lbl, seq) in enumerate(skills):
            col, row = idx % 3, idx // 3
            rx = x0 + col * (sw + 1.0 * u)
            ry = y + row * (sh + 1.1 * u)
            r = QRectF(rx, ry, sw, sh)
            self.chamfer_box(p, r, 1.0 * u, qcol('#190c0f'), qcol('#d6a553', 0.8), 1.5)
            orb = QRectF(rx + 1.0 * u, ry + 1.1 * u, 4.2 * u, 4.2 * u)
            rg = QRadialGradient(orb.center(), 2.4 * u)
            rg.setColorAt(0.0, res_col)
            rg.setColorAt(1.0, qcol('#14080a'))
            p.setPen(QPen(qcol('#f3dfb6'), 1.2))
            p.setBrush(QBrush(rg))
            p.drawEllipse(orb)
            w.text(p, key_lbl, orb.x(), orb.y(), ('m', 1.55, 700), qcol('#ffffff'), orb.width(), 1, 4.2 / 1.55)
            w.text(p, f'RUNE {num}', orb.right() + 0.8 * u, ry + 1.5 * u, ('d', 1.85, 700, .04), qcol('#f3dfb6'), sw - 6.4 * u)
            w.text(p, role_lbl, rx + 1.0 * u, ry + 6.7 * u, ('u', 1.48, 500), qcol('#cbb5a0'), sw - 2.0 * u)
            w.hit(r, lambda seq=seq, role_lbl=role_lbl: self.send_pad(seq, f'{role_lbl} ausgelöst'), name=f'd3_sk:{key_lbl}')

        # Center-right: Giant Crimson Heiltrank Orb + Stadtportal & Ziel fixieren (exact ThorDeck layout!)
        pot_x = x0 + left_w + 1.4 * u
        pot_w = 15.6 * u
        pot_r = QRectF(pot_x, y, pot_w, 23.9 * u)
        self.chamfer_box(p, pot_r, 1.3 * u, qcol('#24080b'), qcol('#ef4444'), 1.8)
        globe = QRectF(pot_r.center().x() - 5.2 * u, y + 2.0 * u, 10.4 * u, 10.4 * u)
        gg = QRadialGradient(globe.center() - QPointF(1.2 * u, 1.5 * u), 6.2 * u)
        gg.setColorAt(0.0, qcol('#fca5a5'))
        gg.setColorAt(0.35, qcol('#dc2626'))
        gg.setColorAt(1.0, qcol('#450a0a'))
        p.setPen(QPen(qcol('#fde047'), 1.8))
        p.setBrush(QBrush(gg))
        p.drawEllipse(globe)
        w.text(p, 'R', globe.x(), globe.y(), ('s', 2.8, 700), qcol('#ffffff'), globe.width(), 1, 10.4 / 2.8)
        w.text(p, 'HEILTRANK', pot_r.x(), y + 14.2 * u, ('d', 2.15, 700, .06), qcol('#fecaca'), pot_w, 1)
        w.text(p, 'Sofort trinken', pot_r.x(), y + 17.8 * u, ('u', 1.5, 500), qcol('#fca5a5'), pot_w, 1)
        w.hit(pot_r, lambda: self.send_pad('R', 'Heiltrank (R)'), name='d3_potion')

        act_x = pot_r.right() + 1.2 * u
        act_w = x0 + cw - act_x
        tp_r = QRectF(act_x, y, act_w, 11.4 * u)
        self.chamfer_box(p, tp_r, 1.0 * u, qcol('#0c1e35'), qcol('#38bdf8'), 1.6)
        w.text(p, 'STADTPORTAL  [▶]', tp_r.x() + 1.4 * u, tp_r.y() + 2.2 * u, ('d', 2.1, 700, .04), qcol('#bae6fd'), act_w - 2.8 * u)
        w.text(p, 'Rückkehr ins Lager', tp_r.x() + 1.4 * u, tp_r.y() + 6.0 * u, ('u', 1.55, 500), qcol('#7dd3fc'), act_w - 2.8 * u)
        w.hit(tp_r, lambda: self.send_pad('RIGHT', 'Stadtportal wird gewirkt …'), name='d3_tp')

        lk_r = QRectF(act_x, y + 12.5 * u, act_w, 11.4 * u)
        self.chamfer_box(p, lk_r, 1.0 * u, qcol('#1f1509'), qcol('#f59e0b'), 1.6)
        w.text(p, 'ZIEL FIXIEREN  [L]', lk_r.x() + 1.4 * u, lk_r.y() + 2.2 * u, ('d', 2.1, 700, .04), qcol('#fde68a'), act_w - 2.8 * u)
        w.text(p, 'Elite / Boss fokussieren', lk_r.x() + 1.4 * u, lk_r.y() + 6.0 * u, ('u', 1.55, 500), qcol('#fcd34d'), act_w - 2.8 * u)
        w.hit(lk_r, lambda: self.send_pad('L', 'Ziel fixiert (L)'), name='d3_lock')

        y += 25.4 * u

        # Bottom Sanctuary Menu Bar + Active Class Build Strip
        menus = (
            ('INVENTAR', '+', 'PLUS', 'Beute, Edelsteine & Begleiter'),
            ('FERTIGKEITEN', '+ R', 'PLUS,R', 'Aktive Runen & 4 Passiva'),
            ('QUESTS & AKT', '+ L', 'PLUS,L', 'Saisonreise & Kopfgelder'),
            ('WELTKARTE', '▼', 'DOWN', 'Akt-Wegpunkte & Portale'),
            ('SPIELMENÜ', '−', 'MINUS', 'Pause & Qual-Stufe'),
            ('SCHNELL-IMPULS', 'LS', 'LS', 'Bewegungs-Impuls / Rolle'),
        )
        mw = (cw - 2.4 * u) / 3
        mh = 8.4 * u
        for idx, (lbl, badge, seq, sub) in enumerate(menus):
            col, row = idx % 3, idx // 3
            rx = x0 + col * (mw + 1.2 * u)
            ry = y + row * (mh + 1.0 * u)
            r = QRectF(rx, ry, mw, mh)
            self.chamfer_box(p, r, 0.85 * u, qcol('#160d0f'), qcol('#855836'), 1.3)
            w.text(p, lbl, rx + 1.4 * u, ry + 1.35 * u, ('d', 1.95, 700, .04), qcol('#f3dfb6'), mw - 7.5 * u)
            w.text(p, badge, rx + mw - 6.2 * u, ry + 1.35 * u, ('m', 1.55, 700), qcol('#eab308'), 4.8 * u, 2)
            w.text(p, sub, rx + 1.4 * u, ry + 4.55 * u, ('u', 1.5, 400), qcol('#cbb5a0'), mw - 2.8 * u)
            w.hit(r, lambda seq=seq, lbl=lbl: self.send_pad(seq, f'{lbl} ({seq})'), name=f'd3_menu:{lbl}')

        fy = y + 2 * mh + 2.1 * u
        if H - fy >= 4.4 * u:
            foot = QRectF(x0, fy, cw, min(9.2 * u, H - fy - 1.6 * u))
            self.chamfer_box(p, foot, 0.85 * u, qcol('#150b0d'), res_col, 1.3)
            w.text(p, f'AKTIVER KLASSEN-FOKUS  ·  {cls[4]}', foot.x() + 1.6 * u, foot.y() + 1.5 * u,
                   ('d', 1.85, 700, .03), qcol('#fff7ed'), cw - 18.0 * u)
            w.text(p, 'WÜRFEL & REZEPTE →', foot.right() - 16.5 * u, foot.y() + 1.6 * u,
                   ('m', 1.45, 700), res_col, 15.0 * u, 2)
            w.text(p, f'Kanais Würfel:  {cls[5]}', foot.x() + 1.6 * u, foot.y() + 4.9 * u,
                   ('u', 1.55, 500), qcol('#cbb5a0'), cw - 3.2 * u)
            w.hit(foot, lambda: self.set_tab(1), name='d3_foot_builds')

    def _paint_builds(self, p, y, cls, res_col):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        # Class strip at top too
        cw_btn = cw / len(CLASSES)
        for i, c in enumerate(CLASSES):
            r = QRectF(x0 + i * cw_btn + 0.2 * u, y, cw_btn - 0.4 * u, 4.0 * u)
            on = (c[0] == cls[0])
            self.chamfer_box(p, r, 0.5 * u, qcol(c[3], 0.28) if on else qcol('#150b0d'),
                             qcol(c[3]) if on else qcol('#3a2322'), 1.5 if on else 1.0)
            w.text(p, c[1], r.x(), r.y(), ('d', 1.55, 700), qcol('#fff7ed') if on else qcol('#a89080'), r.width(), 1, 4.0 / 1.55)
            w.hit(r, lambda cid=c[0]: self.set_val('cls', cid), name=f'd3_bcls:{c[0]}')
        y += 5.4 * u

        # Featured Set Banner
        hero = QRectF(x0, y, cw, 12.2 * u)
        self.chamfer_box(p, hero, 1.1 * u, qcol('#1c0d10'), res_col, 1.8)
        w.text(p, f'{cls[1].upper()} · LEIT-BUILD:{cls[4].upper()}', x0 + 2.0 * u, y + 1.6 * u, ('s', 2.35, 700), qcol('#fef08a'), cw - 4 * u)
        w.text(p, f' Legendäre Edelsteine (Schmuck-Sockel):  {cls[6]}', x0 + 2.0 * u, y + 5.7 * u, ('u', 1.72, 500), qcol('#f3dfb6'), cw - 4 * u)
        w.text(p, 'Smaragd in Waffe (+130 % Krit.-Schaden) · Diamanten in Rüstung (Widerstand) · Topas/Rubin nach Ressource',
               x0 + 2.0 * u, y + 8.8 * u, ('u', 1.52, 400), qcol('#cbb5a0'), cw - 4 * u)
        y += 13.8 * u

        # Kanai's Cube 3-Slot Altar + Cube Recipes
        cube_slots = [s.strip() for s in cls[5].split('·')]
        slot_titles = ('WAFFEN-MACHT (Slot 1)', 'RÜSTUNGS-MACHT (Slot 2)', 'SCHMUCK-MACHT (Slot 3)')
        sw = (cw - 2.4 * u) / 3
        for i in range(3):
            r = QRectF(x0 + i * (sw + 1.2 * u), y, sw, 12.4 * u)
            done = self.is_done(f'cube_{cls[0]}_{i}')
            self.chamfer_box(p, r, 0.9 * u, qcol('#1e2918') if done else qcol('#160c0e'),
                             qcol('#4ade80') if done else qcol('#d6a553', 0.75), 1.5)
            w.text(p, slot_titles[i], r.x() + 1.4 * u, r.y() + 1.4 * u, ('d', 1.72, 700, .04), qcol('#fde68a'), sw - 2.8 * u)
            w.text(p, cube_slots[i] if i < len(cube_slots) else '–', r.x() + 1.4 * u, r.y() + 4.8 * u, ('u', 1.78, 700), qcol('#ffffff'), sw - 2.8 * u, 0, 1.3, 2)
            w.text(p, '✓ Extrahiert' if done else 'Tippen zum Abhaken', r.x() + 1.4 * u, r.y() + 9.4 * u,
                   ('u', 1.45, 600), qcol('#4ade80') if done else qcol('#a89080'), sw - 2.8 * u)
            w.hit(r, lambda k=f'cube_{cls[0]}_{i}': self.toggle_done(k), name=f'd3_cube:{i}')
        y += 14.0 * u

        # Kanai's Cube core recipes reference table
        recipes = (
            ('Seite 1 · Legendäre Macht extrahieren', '1× Akt-I–V-Kopfgeldmaterial + 5× Atem des Todes'),
            ('Seite 2 · Legendären Gegenstand umschmieden', '5× jedes Akt-Material + 50× Vergessene Seele (Chance auf Archaisch!)'),
            ('Seite 3 · Seltenen Gegenstand (St. 70) aufwerten', '25× Atem des Todes + je 50× Weiß / Blau / Gelb'),
            ('Seite 4 · Set-Gegenstand umwandeln', '10× Atem des Todes + 10× Vergessene Seele (gleiches Set)'),
            ('Seite 10 · Caldesanns Verzweiflung', 'Uraltes Item + Edelstein St. 50–125 + 3× Makelloser Königlicher Stein'),
        )
        rem_h = H - y - 2.0 * u
        rh = rem_h / len(recipes)
        for idx, (name, mats) in enumerate(recipes):
            ry = y + idx * rh
            p.fillRect(QRectF(x0, ry, cw, rh - 0.35 * u), qcol('#140b0d' if idx % 2 == 0 else '#1a0e11'))
            w.text(p, name, x0 + 1.4 * u, ry + 0.6 * u, ('u', 1.62, 700), qcol('#f3dfb6'), cw * 0.48)
            w.text(p, mats, x0 + cw * 0.49, ry + 0.6 * u, ('u', 1.55, 400), qcol('#d6c2b2'), cw * 0.49, 2)

    def _paint_journey(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        done_n = sum(1 for k, _ in JOURNEY if self.is_done(k))
        bar_r = QRectF(x0, y, cw, 5.2 * u)
        self.chamfer_box(p, bar_r, 0.7 * u, qcol('#160b0d'), qcol('#855836'), 1.3)
        fill_w = (cw - 0.8 * u) * (done_n / len(JOURNEY))
        if fill_w > 0:
            p.fillRect(QRectF(x0 + 0.4 * u, y + 0.4 * u, fill_w, 4.4 * u), qcol('#991b1b', 0.75))
        w.text(p, f'SAISONREISE & SANKTUARIO-MEILENSTEINE  ·  {done_n} / {len(JOURNEY)} ERLEDIGT',
               bar_r.x() + 1.6 * u, bar_r.y(), ('d', 1.95, 700, .05), qcol('#fef08a'), cw - 3.2 * u, 0, 5.2 / 1.95)
        y += 6.4 * u

        area = QRectF(x0, y, cw, H - y - 2.0 * u)

        def draw_rows(top):
            cy = top
            row_h = 6.2 * u
            for key, label in JOURNEY:
                r = QRectF(x0, cy, cw, row_h - 0.6 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(key)
                    self.chamfer_box(p, r, 0.6 * u, qcol('#1b2618') if chk else qcol('#150b0d'),
                                     qcol('#4ade80') if chk else qcol('#3d2522'), 1.3)
                    mark = '◆' if chk else '◇'
                    self.txt_mid(p, mark, QRectF(r.x() + 1.0 * u, r.y(), 3.4 * u, r.height()), ('s', 2.1, 700), qcol('#4ade80') if chk else qcol('#d6a553'), 1)
                    self.txt_mid(p, label, QRectF(r.x() + 4.8 * u, r.y(), cw - 6.2 * u, r.height()), ('u', 1.72, 600 if chk else 500),
                                 qcol('#dcfce7') if chk else qcol('#f3dfb6'), 0)
                    w.hit(r, lambda k=key: self.toggle_done(k), name=f'd3_j:{key}')
                cy += row_h
            return cy

        w.scroller(p, 'd3_journey', area, draw_rows)
