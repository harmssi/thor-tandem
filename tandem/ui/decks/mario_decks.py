"""Bespoke Mario Companions on the AYN Thor bottom screen:
1. Super Mario Odyssey (0100000000010000 · 'odyssey'): Odyssey Kingdom Travel Passport
   - All 17 Kingdoms Power Moon counter (-1 / +1 / +5) & Regional Purple Coins (50/100) stamp checklist
   - Live Cappy Shake & Motion Action Pad (Kreiswurf, Aufwärtswurf, Abwärtswurf, Zielsuch-Wurf -> UDP SHAKE!)
2. Super Mario Bros. Wonder (010015100B514000 · 'wonder'): Flower Kingdom Royal Stage Deck
   - Worlds W1–W6, Petal Isles & Special World Wonder-Seed counter + 10-Flower-Coins / Secret Exits checklist
   - Complete 24-Badge Cabinet (Action, Boost & Expert Badges) with active loadout pin
3. Mario Kart World / 8 Deluxe (0400C3F00006E000 / 0100152000022000 · 'mkworld'): Pit-Wall Racing Telemetry
   - Interactive Driver Weight × Kart/Tire Chassis Dyno with live Speed, Acceleration, Mini-Turbo, Weight & Offroad bars
   - Grand Prix & Knockout Rally 3-Star Gold Cup Tracker + Charge-Jump / Rail-Grind / Wall-Ride pro techniques."""
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QLinearGradient, QPen, QPolygonF
from decks.native_base import CompanionBase, qcol

# ---- Super Mario Odyssey Data ---------------------------------------------------------------------------------------
ODYSSEY_KINGDOMS = (
    ('cap', 'Hutland (Bonneton)', 31, 50),
    ('cascade', 'Kaskadenland (Fossilfälle)', 40, 50),
    ('sand', 'Wüstenland (Tostarena)', 89, 100),
    ('lake', 'Seeland (Lamode)', 42, 50),
    ('wooded', 'Forstland (Dampfgärten)', 76, 100),
    ('cloud', 'Wolkenland (Nimbus-Arena)', 9, 0),
    ('lost', 'Verlorenes Land (Vergessene Insel)', 35, 50),
    ('metro', 'Cityland (New Donk City)', 81, 100),
    ('snow', 'Polarland (Schlotterkomben)', 55, 50),
    ('seaside', 'Küstenland (Blubberstrand)', 71, 100),
    ('luncheon', 'Schlemmerland (Brutzelberg)', 68, 100),
    ('ruined', 'Ruinenland (Drachenhorst)', 10, 0),
    ('bowser', 'Bowsers Land (Festung)', 62, 100),
    ('moon', 'Mondland (Honeylune-Krater)', 38, 50),
    ('mushroom', 'Pilz-Königreich (Schloss Peach)', 104, 100),
    ('dark', 'Finstere Seite (Hasen-Krater)', 24, 0),
    ('darker', 'Stockfinstere Seite (Meisterprüfung)', 1, 0),
)

ODYSSEY_MOVES = (
    ('Cap-Hechtsprung (Weitester Sprung!)', 'Springen -> Y werfen -> ZL+Y (Hechtsprung in Cappy + Y gedrückt halten) -> nochmal ZL+Y'),
    ('Regenbogenwirbel', 'In der Luft B + Y gleichzeitig für Extra-Höhenschub'),
    ('Rückwärtssalto -> Aufwärtswurf', 'ZL halten + A -> oben Schütteln für maximale vertikale Kanten-Höhe'),
    ('Roll-Boost (Schnellste Fortbewegung)', 'ZL gedrückt halten + Schütteln (oder Y-Trommelfeuer) bergab und auf Ebenen'),
)

# ---- Super Mario Bros. Wonder Data ----------------------------------------------------------------------------------
WONDER_WORLDS = (
    ('w1', 'W1 · Röhrenfelsen-Wiese', 35, 'Geheimer Ausgang in „Piranha-Pflanzen auf Marsch“!'),
    ('w2', 'W2 · Wölkchen-Gebirge', 30, 'Geheimer Ausgang in „Condarts im Anflug“ -> Spezialwelt-Zugang'),
    ('w3', 'W3 · Glitzerwasser-Fälle', 22, 'Meisterprüfungen öffnen den direkten Blüteninseln-Pfad'),
    ('w4', 'W4 · Sonnenbrand-Wüste', 35, '3 versteckte Ruinen-Level im Treibsand + Geheimer Ausgang in „Geheimnis des Tempels“'),
    ('w5', 'W5 · Pilz-Sumpf', 19, 'Dunkle Sporen-Höhlen – Delfin-Kick oder Schwebe-Drehsprung ideal'),
    ('w6', 'W6 · Magma-Tiefe', 35, '4 Drachenfelsen-Prüfungen vor dem Weg zu Schloss Bowser'),
    ('wp', 'Blüteninseln (Zentrum)', 28, 'Verbindet alle 6 Welten + Bowsers Festungs-Samen'),
    ('ws', 'Spezialwelt ★', 18, 'Finale Abzeichen-Meisterprüfung nach 100 % Samen & Flaggen!'),
)

WONDER_BADGES = (
    ('wb_para', 'Fallschirmmütze (Aktion)', 'R halten zum sanften Gleiten – sicherstes Allround-Abzeichen!'),
    ('wb_spin', 'Schwebe-Drehsprung (Aktion)', 'R in der Luft für Extra-Doppelsprung auf hohe Flaggenmasten!'),
    ('wb_wall', 'Klimmsprung (Aktion)', 'Einmal senkrecht an derselben Wand hochspringen'),
    ('wb_vine', 'Rankenschuss (Aktion)', 'Zieht dich in der Luft wie ein Enterhaken an jede Wand!'),
    ('wb_dolp', 'Delfin-Kick (Aktion)', 'Unterwasser-Turbo & Steinblöcke unter Wasser durchbrechen'),
    ('wb_crou', 'Hochsprung aus der Hocke (Aktion)', 'Aufladen für geheime Decken-Röhren'),
    ('wb_sens', 'Detektor (Stärkung)', 'Schlägt akustisch & optisch Alarm in der Nähe von 10er-Münzen & Samen!'),
    ('wb_magn', 'Münzmagnet (Stärkung)', 'Zieht Blumenmünzen & Goldmünzen automatisch an'),
    ('wb_safe', 'Rettung aus der Tiefe (Stärkung)', 'Einmal pro Level automatischer Rettungssprung aus Lava/Abgrund!'),
    ('wb_mush', 'Auto-Superpilz (Stärkung)', 'Startet jedes Level automatisch groß'),
    ('wb_jet', 'Spurt (Profi)', 'Dauer-Sprint + kurzzeitig über Abgründe in der Luft weiterlaufen'),
    ('wb_inv', 'Unsichtbarkeit (Profi)', 'Feinde sehen dich nicht (und du dich selbst auch nicht!)'),
)

# ---- Mario Kart World Data ------------------------------------------------------------------------------------------
MK_DRIVERS = (
    ('Feder (Baby / Toadette / Koopa)', 2, 9, 10, 2, 8),
    ('Leicht (Toad / Shy Guy / Lakitu)', 4, 8, 9, 4, 8),
    ('Mittel (Mario / Peach / Yoshi)', 6, 7, 8, 6, 7),
    ('Cruiser (Luigi / Rosalina / Waluigi)', 8, 6, 6, 8, 6),
    ('Schwer (Bowser / Donkey Kong / Wario)', 10, 4, 4, 10, 5),
)

MK_CHASSIS = (
    ('Roller-Buggy (Max. Mini-Turbo!)', -2, +3, +3, -2, +1),
    ('Allround-Roadster', 0, +1, +1, 0, +1),
    ('Rallye-Geländekart (Knockout-Meta)', +1, +1, 0, +1, +3),
    ('Innen-Drift-Sportbike', +1, +2, +2, -1, 0),
    ('Schwerlast-Bolide (Top-Speed)', +3, -2, -2, +2, -1),
)

MK_CUPS = (
    ('mk_c1', 'Pilz-Pokal · GP & Knockout-Rallye (3★ Gold)'),
    ('mk_c2', 'Blumen-Pokal · GP & Knockout-Rallye (3★ Gold)'),
    ('mk_c3', 'Stern-Pokal · GP & Knockout-Rallye (3★ Gold)'),
    ('mk_c4', 'Spezial-Pokal · Regenbogen-Boulevard freischalten!'),
    ('mk_c5', 'Panzer- & Bananen-Rallye (Durchgehende Überland-Etappen)'),
    ('mk_c6', 'Blatt- & Blitz-Rallye (Knockout-Ausscheidung unter Top 4!)'),
    ('mk_c7', 'Spiegel-Modus / 200 ccm Meisterschaft'),
    ('mk_c8', 'Freie Fahrt · P-Schalter-Missionen & Fragezeichen-Platten'),
)


class OdysseyDeck(CompanionBase):
    KEY = 'odyssey'
    TABS = ('Reisepass', 'Cappy-Labor', 'Tipps & Jagd', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'odyssey')

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#0b1220'))

        hdr = QRectF(0, 0, W, 11.0 * u)
        g = QLinearGradient(0, 0, 0, hdr.height())
        g.setColorAt(0.0, qcol('#991b1b'))
        g.setColorAt(1.0, qcol('#450a0a'))
        p.fillRect(hdr, g)

        total_moons = sum(int(self.get_val('m_' + k[0], 0) or 0) for k in ODYSSEY_KINGDOMS)
        w.text(p, 'ODYSSEY-REISEPASS  ·  SUPER MARIO ODYSSEY', 2.8 * u, 1.15 * u, ('d', 2.45, 700, .04), qcol('#fef08a'), W * 0.65)
        w.text(p, f'Gesammelte Kraftmonde: {total_moons} / 880', 2.8 * u, 4.0 * u, ('u', 1.6, 600), qcol('#fde68a'), W * 0.6)

        shake_r = QRectF(W - 22.5 * u, 1.1 * u, 19.8 * u, 4.3 * u)
        self.chamfer_box(p, shake_r, 0.6 * u, qcol('#facc15'), qcol('#ffffff'), 1.5)
        w.text(p, '↻ CAPPY-WIRBEL [SHAKE]', shake_r.x(), shake_r.y(), ('d', 1.72, 700), qcol('#450a0a'), shake_r.width(), 1, 4.3 / 1.72)
        w.hit(shake_r, lambda: self.send_pad('SHAKE', 'Cappy-Kreiswurf!'), name='ody_hdr_shake')

        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, 6.2 * u, tw - 0.6 * u, 4.1 * u)
            on = (i == self.tab)
            w.capsule(p, r, qcol('#facc15') if on else qcol('#2a0a0d'), qcol('#ffffff') if on else qcol('#7f1d1d'))
            w.text(p, lbl.upper(), r.x(), r.y(), ('d', 1.82, 700, .04), qcol('#450a0a') if on else qcol('#fecaca'), r.width(), 1, 4.1 / 1.82)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'ody_tab:{lbl}')

        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#0b1220')
            return True
        top = hdr.bottom() + 1.3 * u
        if self.tab == 0:
            self._paint_passport(p, top)
        elif self.tab == 1:
            self._paint_cappy(p, top)
        else:
            self._paint_tips(p, top)
        return True

    def _paint_passport(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_kingdoms(top):
            cy = top
            rh = 6.2 * u
            for kid, kname, max_m, pcoins in ODYSSEY_KINGDOMS:
                r = QRectF(x0, cy, cw, rh - 0.55 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    cur_m = int(self.get_val('m_' + kid, 0) or 0)
                    pc_done = self.is_done('pc_' + kid)
                    full = (cur_m >= max_m and (pcoins == 0 or pc_done))
                    w.box(p, r, 1.0 * u, qcol('#132820') if full else qcol('#141e33'), qcol('#facc15') if full else qcol('#2c3b59'))
                    self.txt_mid(p, kname, QRectF(r.x() + 1.3 * u, r.y(), cw * 0.41, r.height()),
                                 ('u', 1.75, 700), qcol('#fef08a' if full else '#f8fafc'), 0)

                    if pcoins > 0:
                        pr = QRectF(r.x() + cw * 0.43, r.y() + 0.9 * u, 15.0 * u, rh - 2.35 * u)
                        w.capsule(p, pr, qcol('#581c87') if pc_done else qcol('#1e1b4b'), qcol('#c084fc'))
                        self.txt_mid(p, f'{"✓" if pc_done else "○"} {pcoins} Lila', pr, ('d', 1.58, 700), qcol('#f3e8ff'), 1)
                        w.hit(pr, lambda k='pc_' + kid: self.toggle_done(k), name=f'ody_pc:{kid}')

                    # Moon counter -1 / count / +1 / +5
                    b_m1 = QRectF(r.right() - 25.5 * u, r.y() + 0.85 * u, 4.4 * u, rh - 2.25 * u)
                    b_lbl = QRectF(b_m1.right() + 0.4 * u, r.y() + 0.85 * u, 9.6 * u, rh - 2.25 * u)
                    b_p1 = QRectF(b_lbl.right() + 0.4 * u, r.y() + 0.85 * u, 4.4 * u, rh - 2.25 * u)
                    b_p5 = QRectF(b_p1.right() + 0.4 * u, r.y() + 0.85 * u, 5.0 * u, rh - 2.25 * u)
                    for br, col_b, txt in ((b_m1, '#1e293b', '−1'), (b_p1, '#b91c1c', '+1'), (b_p5, '#ca8a04', '+5')):
                        w.capsule(p, br, qcol(col_b), qcol('#ffffff', 0.25))
                        self.txt_mid(p, txt, br, ('d', 1.65, 700), qcol('#ffffff'), 1)
                    self.txt_mid(p, f'☽ {cur_m}/{max_m}', b_lbl, ('m', 1.52, 700), qcol('#fde047'), 1)
                    w.hit(b_m1, lambda f='m_' + kid, mx=max_m: self.bump_val(f, -1, 0, mx), name=f'ody_m1:{kid}')
                    w.hit(b_p1, lambda f='m_' + kid, mx=max_m: self.bump_val(f, 1, 0, mx), name=f'ody_p1:{kid}')
                    w.hit(b_p5, lambda f='m_' + kid, mx=max_m: self.bump_val(f, 5, 0, mx), name=f'ody_p5:{kid}')
                cy += rh
            return cy

        w.scroller(p, 'ody_pass', area, draw_kingdoms)

    def _paint_cappy(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        # 4 Large Tactile Motion-Action Pads (sends real UDP SHAKE chords to PeanutsNative!)
        pads = (
            ('KREISWURF (360°)', 'SHAKE', 'Rundumschlag gegen Gegnergruppen & Münzringe', '#dc2626'),
            ('AUFWÄRTSWURF', 'LUP+SHAKE', 'Trifft fliegende Gegner & hohe Fragezeichenblöcke', '#f59e0b'),
            ('ABWÄRTS- / ROLL-TURBO', 'ZL+SHAKE', 'Rollender Abwärtswurf & maximaler Roll-Speed!', '#0ea5e9'),
            ('WELTKARTE / REISEPASS', 'MINUS', 'Öffnet sofort die In-Game-Broschüre & Schnellreise', '#22c55e'),
        )
        pw = (cw - 1.4 * u) / 2
        ph = 9.4 * u
        for idx, (lbl, seq, sub, col_h) in enumerate(pads):
            col, row = idx % 2, idx // 2
            r = QRectF(x0 + col * (pw + 1.4 * u), y + row * (ph + 1.1 * u), pw, ph)
            w.box(p, r, 1.2 * u, qcol('#141e33'), qcol(col_h))
            w.text(p, lbl, r.x() + 1.5 * u, r.y() + 1.3 * u, ('d', 2.05, 700, .04), qcol(col_h), pw - 3.0 * u)
            w.text(p, sub, r.x() + 1.5 * u, r.y() + 4.8 * u, ('u', 1.52, 400), qcol('#e2e8f0'), pw - 3.0 * u, 0, 1.25, 2)
            w.hit(r, lambda seq=seq, lbl=lbl: self.send_pad(seq, lbl), name=f'ody_act:{idx}')
        y += 2 * ph + 2.6 * u

        rem = H - y - 1.8 * u
        rh = rem / len(ODYSSEY_MOVES)
        for idx, (mtitle, mhow) in enumerate(ODYSSEY_MOVES):
            ry = y + idx * rh
            r = QRectF(x0, ry, cw, rh - 0.5 * u)
            w.box(p, r, 0.8 * u, qcol('#111829'))
            w.text(p, mtitle, r.x() + 1.3 * u, r.y() + 0.55 * u, ('u', 1.68, 700), qcol('#fde047'), cw * 0.36)
            w.text(p, mhow, r.x() + cw * 0.37, r.y() + 0.55 * u, ('u', 1.5, 400), qcol('#cbd5e1'), cw * 0.61, 0, 1.25, 2)

    def _paint_tips(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        goals = (
            ('ody_g1', 'Mondstein-Würfel in jedem Land nach Story-Abschluss aktivieren (verdoppelt Monde!)'),
            ('ody_g2', 'Toadette im Pilz-Königreich für Rekord-Kraftmonde besuchen'),
            ('ody_g3', 'Peach & Tiara in allen 16 bereisbaren Ländern für je 1 Kraftmond ansprechen'),
            ('ody_g4', 'Hinweis-Kunst-Bilder finden -> im Ziel-Land am markierten Punkt Stampfattacke'),
            ('ody_g5', 'Kapitän Toad in jedem Land aufspüren (drehe die Kamera unter Brücken & Klippen!)'),
            ('ody_g6', '250 Kraftmonde -> Finstere Seite des Mondes freischalten'),
            ('ody_g7', '500 Kraftmonde -> Stockfinstere Seite (Ultimative Odyssee-Prüfung) freischalten!'),
        )
        rh = (H - y - 2.0 * u) / len(goals)
        for idx, (gid, txt) in enumerate(goals):
            r = QRectF(x0, y + idx * rh, cw, rh - 0.5 * u)
            chk = self.is_done(gid)
            w.box(p, r, 0.8 * u, qcol('#132820') if chk else qcol('#141e33'), qcol('#4ade80') if chk else qcol('#2c3b59'))
            self.txt_mid(p, f'{"✓" if chk else "○"}  {txt}', QRectF(r.x() + 1.4 * u, r.y(), cw - 2.8 * u, r.height()),
                         ('u', 1.68, 600), qcol('#bbf7d0') if chk else qcol('#f1f5f9'), 0)
            w.hit(r, lambda k=gid: self.toggle_done(k), name=f'ody_g:{gid}')


class WonderDeck(CompanionBase):
    KEY = 'wonder'
    TABS = ('Welten & Samen', 'Abzeichen-Tresor', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'wonder')

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#130c26'))

        hdr = QRectF(0, 0, W, 11.0 * u)
        g = QLinearGradient(0, 0, W, hdr.height())
        g.setColorAt(0.0, qcol('#4c1d95'))
        g.setColorAt(0.6, qcol('#831843'))
        g.setColorAt(1.0, qcol('#1e1b4b'))
        p.fillRect(hdr, g)

        seeds = sum(int(self.get_val('ws_' + k[0], 0) or 0) for k in WONDER_WORLDS)
        active_b = self.get_val('active_badge', 'Fallschirmmütze (Aktion)')
        w.text(p, 'BLUMENKÖNIGREICH  ·  SUPER MARIO BROS. WONDER', 2.8 * u, 1.15 * u, ('d', 2.35, 700, .04), qcol('#67e8f9'), W * 0.72)
        w.text(p, f'Wundersamen: {seeds}  ·  Aktives Abzeichen: {active_b}', 2.8 * u, 4.05 * u, ('u', 1.55, 600), qcol('#fbcfe8'), W * 0.85)

        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, 6.2 * u, tw - 0.6 * u, 4.1 * u)
            on = (i == self.tab)
            w.capsule(p, r, qcol('#22d3ee') if on else qcol('#241545'), qcol('#ffffff') if on else qcol('#ec4899', 0.6))
            w.text(p, lbl.upper(), r.x(), r.y(), ('d', 1.85, 700, .04), qcol('#130c26') if on else qcol('#f5d0fe'), r.width(), 1, 4.1 / 1.85)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'wnd_tab:{lbl}')

        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#130c26')
            return True
        top = hdr.bottom() + 1.3 * u
        if self.tab == 0:
            self._paint_worlds(p, top)
        else:
            self._paint_badges(p, top)
        return True

    def _paint_worlds(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_w(top):
            cy = top
            rh = 7.4 * u
            for wid, wname, max_s, secret in WONDER_WORLDS:
                r = QRectF(x0, cy, cw, rh - 0.6 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    cur_s = int(self.get_val('ws_' + wid, 0) or 0)
                    done_100 = self.is_done('w100_' + wid)
                    w.box(p, r, 1.1 * u, qcol('#1c2e35') if done_100 else qcol('#1f153a'),
                          qcol('#22d3ee') if done_100 else qcol('#6d28d9'))
                    w.text(p, wname, r.x() + 1.4 * u, r.y() + 0.75 * u, ('u', 1.82, 700), qcol('#ffffff'), cw * 0.56)
                    w.text(p, secret, r.x() + 1.4 * u, r.y() + 3.7 * u, ('u', 1.46, 400), qcol('#e9d5ff'), cw * 0.6)

                    chk_r = QRectF(r.right() - 31.5 * u, r.y() + 1.3 * u, 11.2 * u, 4.2 * u)
                    w.capsule(p, chk_r, qcol('#0d9488') if done_100 else qcol('#2e1d59'), qcol('#5eead4'))
                    w.text(p, '✓ 100%' if done_100 else '○ 10er/Flag', chk_r.x(), chk_r.y(), ('d', 1.58, 700), qcol('#ffffff'), chk_r.width(), 1, 4.2 / 1.58)
                    w.hit(chk_r, lambda k='w100_' + wid: self.toggle_done(k), name=f'wnd_100:{wid}')

                    bm = QRectF(r.right() - 19.2 * u, r.y() + 1.3 * u, 4.4 * u, 4.2 * u)
                    bl = QRectF(bm.right() + 0.3 * u, r.y() + 1.3 * u, 8.8 * u, 4.2 * u)
                    bp = QRectF(bl.right() + 0.3 * u, r.y() + 1.3 * u, 4.4 * u, 4.2 * u)
                    w.capsule(p, bm, qcol('#31205e'))
                    w.capsule(p, bp, qcol('#ec4899'))
                    w.text(p, '−', bm.x(), bm.y(), ('d', 2.0, 700), qcol('#ffffff'), bm.width(), 1, 4.2 / 2.0)
                    w.text(p, '+', bp.x(), bp.y(), ('d', 2.0, 700), qcol('#ffffff'), bp.width(), 1, 4.2 / 2.0)
                    w.text(p, f'✦ {cur_s}/{max_s}', bl.x(), bl.y(), ('m', 1.52, 700), qcol('#67e8f9'), bl.width(), 1, 4.2 / 1.52)
                    w.hit(bm, lambda f='ws_' + wid, m=max_s: self.bump_val(f, -1, 0, m), name=f'wnd_m:{wid}')
                    w.hit(bp, lambda f='ws_' + wid, m=max_s: self.bump_val(f, 1, 0, m), name=f'wnd_p:{wid}')
                cy += rh
            return cy

        w.scroller(p, 'wnd_worlds', area, draw_w)

    def _paint_badges(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        area = QRectF(x0, y, cw, H - y - 1.8 * u)
        active = self.get_val('active_badge', 'Fallschirmmütze (Aktion)')

        def draw_b(top):
            cy = top
            rh = 6.2 * u
            for bid, bname, bdesc in WONDER_BADGES:
                r = QRectF(x0, cy, cw, rh - 0.55 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    pinned = (bname == active)
                    got = self.is_done(bid)
                    w.box(p, r, 1.0 * u, qcol('#2b184a') if pinned else qcol('#1d1336'),
                          qcol('#fbbf24') if pinned else (qcol('#22d3ee') if got else qcol('#4c1d95')))
                    w.text(p, ('★ ' if pinned else ('✓ ' if got else '○ ')) + bname,
                           r.x() + 1.3 * u, r.y() + 0.65 * u, ('u', 1.72, 700), qcol('#fde047' if pinned else '#ffffff'), cw - 15.0 * u)
                    w.text(p, bdesc, r.x() + 1.3 * u, r.y() + 3.25 * u, ('u', 1.45, 400), qcol('#e9d5ff'), cw - 15.0 * u)
                    pin_r = QRectF(r.right() - 13.5 * u, r.y() + 0.95 * u, 12.2 * u, rh - 2.45 * u)
                    w.capsule(p, pin_r, qcol('#fbbf24') if pinned else qcol('#31205e'))
                    self.txt_mid(p, 'AKTIV' if pinned else 'WÄHLEN', pin_r, ('d', 1.62, 700),
                                 qcol('#130c26') if pinned else qcol('#f5d0fe'), 1)
                    w.hit(pin_r, lambda bn=bname: self.set_val('active_badge', bn), name=f'wnd_pin:{bid}')
                    w.hit(QRectF(r.x(), r.y(), cw - 14.5 * u, r.height()), lambda k=bid: self.toggle_done(k), name=f'wnd_got:{bid}')
                cy += rh
            return cy

        w.scroller(p, 'wnd_badges', area, draw_b)


class MarioKartWorldDeck(CompanionBase):
    KEY = 'mkworld'
    TABS = ('Prüfstand', 'Pokale & Technik', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'mkworld')

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#0a0d14'))

        hdr = QRectF(0, 0, W, 11.0 * u)
        p.fillRect(hdr, qcol('#131722'))
        # Racing slanted stripe accent
        stripe = QPolygonF([QPointF(W - 26 * u, 0), QPointF(W, 0), QPointF(W, hdr.height()), QPointF(W - 31 * u, hdr.height())])
        p.setPen(qcol('#000000', 0))
        p.setBrush(qcol('#dc2626', 0.35))
        p.drawPolygon(stripe)

        w.text(p, 'BOXENMAUER-TELEMETRIE  ·  MARIO KART WORLD', 2.8 * u, 1.15 * u, ('d', 2.45, 700, .05), qcol('#ffffff'), W * 0.78)
        cups_done = sum(1 for k, _ in MK_CUPS if self.is_done(k))
        w.text(p, f'Goldpokale & Meilensteine: {cups_done} / {len(MK_CUPS)}', 2.8 * u, 4.05 * u, ('u', 1.55, 600), qcol('#38bdf8'), W * 0.65)

        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, 6.2 * u, tw - 0.6 * u, 4.1 * u)
            on = (i == self.tab)
            self.slant(p, r, 0.7 * u, qcol('#f97316') if on else qcol('#1e2433'), qcol('#ffffff') if on else qcol('#334155'), 1.5 if on else 1.0)
            w.text(p, lbl.upper(), r.x() + 0.3 * u, r.y(), ('d', 1.85, 700, .04), qcol('#0a0d14') if on else qcol('#cbd5e1'), r.width(), 1, 4.1 / 1.85)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'mk_tab:{lbl}')

        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#0a0d14')
            return True
        top = hdr.bottom() + 1.3 * u
        if self.tab == 0:
            self._paint_dyno(p, top)
        else:
            self._paint_cups(p, top)
        return True

    def _paint_dyno(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        di = int(self.get_val('mk_drv', 2) or 0) % len(MK_DRIVERS)
        ci = int(self.get_val('mk_chs', 0) or 0) % len(MK_CHASSIS)
        drv = MK_DRIVERS[di]
        chs = MK_CHASSIS[ci]

        # Left column: Driver Weight Class selector; Right column: Chassis selector
        col_w = (cw - 1.6 * u) / 2
        for idx, d in enumerate(MK_DRIVERS):
            r = QRectF(x0, y + idx * 4.5 * u, col_w, 4.05 * u)
            on = (idx == di)
            self.slant(p, r, 0.45 * u, qcol('#ef4444', 0.28) if on else qcol('#151b28'), qcol('#ef4444') if on else qcol('#293246'), 1.4 if on else 1.0)
            w.text(p, d[0], r.x() + 1.2 * u, r.y(), ('u', 1.58, 700 if on else 500), qcol('#ffffff') if on else qcol('#94a3b8'), col_w - 2.4 * u, 0, 4.05 / 1.58)
            w.hit(r, lambda idx=idx: self.set_val('mk_drv', idx), name=f'mk_d:{idx}')

        for idx, c in enumerate(MK_CHASSIS):
            r = QRectF(x0 + col_w + 1.6 * u, y + idx * 4.5 * u, col_w, 4.05 * u)
            on = (idx == ci)
            self.slant(p, r, 0.45 * u, qcol('#06b6d4', 0.28) if on else qcol('#151b28'), qcol('#06b6d4') if on else qcol('#293246'), 1.4 if on else 1.0)
            w.text(p, c[0], r.x() + 1.2 * u, r.y(), ('u', 1.58, 700 if on else 500), qcol('#ffffff') if on else qcol('#94a3b8'), col_w - 2.4 * u, 0, 4.05 / 1.58)
            w.hit(r, lambda idx=idx: self.set_val('mk_chs', idx), name=f'mk_c:{idx}')

        y += 5 * 4.5 * u + 1.2 * u

        # Live Telemetry Stat Bars (1..12 scale)
        stats = (
            ('HÖCHSTTEMPO', drv[1] + chs[1], '#ef4444'),
            ('BESCHLEUNIGUNG', drv[2] + chs[2], '#22c55e'),
            ('MINI-TURBO (DRIFT)', drv[3] + chs[3], '#f97316'),
            ('GEWICHT & RAMMEN', drv[4] + chs[4], '#eab308'),
            ('OFFROAD & WASSER', drv[5] + chs[5], '#06b6d4'),
        )
        rem = H - y - 1.8 * u
        rh = rem / len(stats)
        for idx, (sname, raw_v, col_h) in enumerate(stats):
            val = max(1, min(12, raw_v))
            ry = y + idx * rh
            self.txt_mid(p, sname, QRectF(x0, ry, cw * 0.28, rh), ('d', 1.82, 700, .04), qcol('#e2e8f0'), 0)
            bar_r = QRectF(x0 + cw * 0.29, ry + rh * 0.22, cw * 0.58, rh * 0.56)
            self.slant(p, bar_r, 0.4 * u, qcol('#151b28'), qcol('#293246'), 1.0)
            fill_r = QRectF(bar_r.x(), bar_r.y(), bar_r.width() * (val / 12.0), bar_r.height())
            self.slant(p, fill_r, 0.4 * u, qcol(col_h))
            self.txt_mid(p, f'{val:02d} / 12', QRectF(bar_r.right() + 1.0 * u, ry, cw * 0.12, rh), ('m', 1.65, 700), qcol(col_h), 2)

    def _paint_cups(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        tech = QRectF(x0, y, cw, 7.6 * u)
        self.slant(p, tech, 0.65 * u, qcol('#161e2e'), qcol('#f97316'), 1.5)
        w.text(p, 'PROFI-TECHNIK: CHARGE-JUMP & RAIL-GRIND', tech.x() + 1.4 * u, tech.y() + 0.9 * u, ('d', 1.85, 700), qcol('#fdba74'), cw - 2.8 * u)
        w.text(p, 'Auf Geraden R gedrückt halten (Auflade-Sprung) -> auf Geländer grinden oder schräg an Wände springen für Wall-Ride-Mini-Turbos!',
               tech.x() + 1.4 * u, tech.y() + 3.65 * u, ('u', 1.48, 400), qcol('#e2e8f0'), cw - 2.8 * u, 0, 1.25, 2)
        y += 8.8 * u

        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_c(top):
            cy = top
            rh = 5.6 * u
            for cid, clbl in MK_CUPS:
                r = QRectF(x0, cy, cw, rh - 0.5 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(cid)
                    self.slant(p, r, 0.45 * u, qcol('#142920') if chk else qcol('#151b28'),
                               qcol('#facc15') if chk else qcol('#293246'), 1.3)
                    self.txt_mid(p, f'{"★★★" if chk else "☆☆☆"}   {clbl}', QRectF(r.x() + 1.4 * u, r.y(), cw - 2.8 * u, r.height()),
                                 ('u', 1.72, 700 if chk else 500), qcol('#fef08a') if chk else qcol('#e2e8f0'), 0)
                    w.hit(r, lambda k=cid: self.toggle_done(k), name=f'mk_cup:{cid}')
                cy += rh
            return cy

        w.scroller(p, 'mk_cups', area, draw_c)


def Deck(w):
    comp = (w.RUN or {}).get('companion')
    if comp == 'wonder':
        return WonderDeck(w)
    if comp == 'mkworld':
        return MarioKartWorldDeck(w)
    return OdysseyDeck(w)
