"""Bespoke Zelda Companions on the AYN Thor bottom screen:
1. Link's Awakening (01006BB00C6F0000 · 'zelda_la'): Koholint carved-mahogany & vellum diorama
   - 14-step Koholint Trading Chain + 3 Ocarina Melodies + Live Map/Inventory touch actions
   - 8 Instruments of the Sirens + Color Dungeon boss & key item guide
   - 50 Secret Seashells & 32 Heart Pieces regional tracker
2. Ocarina of Time (0400486024DEC000 / N64 / 3DS · 'oot'): Sheikah Time-Altar & Triforce Subscreen
   - All 12 Ocarina Melodies drawn on real 5-line golden musical staves with color-coded N64/NSO notes
     AND a live 'Spielen' button that plays the exact note sequence into the running game!
   - Spiritual Stones, 6 Sage Medallions & Biggoron Sword trading quest
   - Golden Skulltulas (100) & Heart Pieces (36) regional checklist."""
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QLinearGradient, QPen, QPolygonF
from decks.native_base import CompanionBase, qcol

# ---- Link's Awakening Data ------------------------------------------------------------------------------------------
LA_TRADES = (
    ('la_tr01', '1 · Yoshi-Puppe', 'Kran-Spiel in Mövendorf -> zur Mutter mit Drillingen'),
    ('la_tr02', '2 · Schleife', 'Mutter in Mövendorf -> Komet / kleiner Kettenhund neben Struppi'),
    ('la_tr03', '3 · Hundefutter', 'Madame Miamaumiau -> Sale (Krokodil am Toronbo-Strand)'),
    ('la_tr04', '4 · Bananen', 'Sale -> Kiki der Affe rechts vor Schloss Kanalet (Brücke!)'),
    ('la_tr05', '5 · Stock', 'Affenbrücke -> Tarin am Bienenbaum in der Ukuku-Prärie'),
    ('la_tr06', '6 · Honigwabe', 'Tarin -> Bär-Koch im Zoodorf (Südosten)'),
    ('la_tr07', '7 · Ananas', 'Koch -> Papahl (verirrt im Tal-Tal-Gebirge östlich vom Hühnerstall)'),
    ('la_tr08', '8 · Hibiskus', 'Papahl -> Ziege Christine im Zoodorf'),
    ('la_tr09', '9 · Brief', 'Christine -> Dr. Wright (Hütte nördlich vom Zauberwald)'),
    ('la_tr10', '10 · Besen', 'Dr. Wright -> Oma Ulrira (Mövendorf / Zoodorf)'),
    ('la_tr11', '11 · Angelhaken', 'Oma -> Fischer unter der Brücke in der Martha-Bucht'),
    ('la_tr12', '12 · Halskette', 'Fischer -> Nixe in der Martha-Bucht'),
    ('la_tr13', '13 · Nixenschuppe', 'Nixe -> Meerjungfrauen-Statue südlich der Bucht'),
    ('la_tr14', '14 · Lupe ★', 'Geheime Höhle -> liest das Buch in der Bibliothek (Windfisch-Ei-Weg!)'),
)

LA_DUNGEONS = (
    ('la_d1', 'L1 · Wurmpalast', 'Vollmond-Cello', 'Greifenfeder · Moldorm am Schwanzende treffen'),
    ('la_d2', 'L2 · Dschinn-Grotte', 'Muschelhorn', 'Kraftarmband · Flaschengeist-Krug an die Wand werfen'),
    ('la_d3', 'L3 · Schlüsselkeller', 'Seelilien-Glocke', 'Pegasus-Stiefel · Schleimaugen mit Ramm-Sprint teilen'),
    ('la_d4', 'L4 · Wundertunnel', 'strömungs-Harfe', 'Schwimmflossen · Anglerfisch unter Wasser schlagen'),
    ('la_d5', 'L5 · Fischmaul', 'Windmarimba', 'Enterhaken · Schleimaal mit Haken aus Wandlöchern ziehen'),
    ('la_d6', 'L6 · Maskentempel', 'Korallen-Triangel', 'Kraftarmband St.2 · Fassade mit Bomben ins Gesicht'),
    ('la_d7', 'L7 · Adlerfestung', 'Orgel der Abendruhe', 'Spiegelschild · 4 Säulen mit Eisenkugel einreißen'),
    ('la_d8', 'L8 · Reptilienfelsen', 'Donnertrommel', 'Magischer Stab · Heißkopf mit Feuerstab schmelzen'),
    ('la_d0', 'Bonus · Farb-Dungeon', 'Rote / Blaue Rüstung', 'Friedhof-Grabsteine: Unten, Links, Oben, Rechts, Oben'),
)

LA_ZONES = (
    ('la_z_mabe', 'Mövendorf & Zauberwald', 7, 'Kran-Spiel, Hundehütte, Gras mähen, Baum rammen'),
    ('la_z_beach', 'Toronbo-Strand & Kokos-Küste', 6, 'Palmen rammen, Schaufel-Stellen, Sale-Haus'),
    ('la_z_prairie', 'Ukuku-Prärie & Schloss Kanalet', 9, '5 Goldene Blätter, Höhlen sprengen, Schlossgraben'),
    ('la_z_bay', 'Martha-Bucht & Zoodorf', 8, 'Unterwasser-Gräben, Geisterhaus, Büsche'),
    ('la_z_face', 'Maskenschrein & Stromschnellen', 7, 'Floßfahrt-Route links halten, Ruinen-Inseln'),
    ('la_z_taltal', 'Tal-Tal-Gebirge & Tamaranch', 8, 'Felsen heben, Brücke, Hühnerstall-Klippen'),
    ('la_z_shells40', 'Muschel-Basar Belohnung (40 Muscheln)', 5, 'Cocolint-Schwert St. 2 mit Schwertstrahl!'),
)

# ---- Ocarina of Time Data -------------------------------------------------------------------------------------------
# Notes: ('A', 0.82), ('CDown', 0.66), ('CRight', 0.50), ('CLeft', 0.34), ('CUp', 0.18) on the 5-line staff!
OOT_SONGS = (
    ('Zeldas Wiegenlied', 'CLeft,CUp,CRight,CLeft,CUp,CRight', 'Königliche Siegel öffnen & Feenquellen rufen', '#f472b6'),
    ('Eponas Lied', 'CUp,CLeft,CRight,CUp,CLeft,CRight', 'Epona herbeirufen & Milch von Kühen erhalten', '#fb923c'),
    ('Salias Lied', 'CDown,CRight,CLeft,CDown,CRight,CLeft', 'Darunia aufmuntern & Rat von Salia holen', '#4ade80'),
    ('Hymne der Sonne', 'CRight,CDown,CUp,CRight,CDown,CUp', 'Tag/Nacht wechseln & Zombies (Gibdos) lähmen!', '#facc15'),
    ('Hymne der Zeit', 'CRight,A,CDown,CRight,A,CDown', 'Zeitblöcke versetzen & Zeitfels öffnen', '#38bdf8'),
    ('Hymne des Sturms', 'A,CDown,CUp,A,CDown,CUp', 'Windmühle beschleunigen & Grotten öffnen', '#a78bfa'),
    ('Menuett des Waldes', 'A,CUp,CLeft,CRight,CLeft,CRight', 'Teleport: Heilige Waldlichtung (Waldtempel)', '#22c55e'),
    ('Bolero des Feuers', 'CDown,A,CDown,A,CRight,CDown,CRight,CDown', 'Teleport: Todeskrater (Feuertempel)', '#ef4444'),
    ('Serenade des Wassers', 'A,CDown,CRight,CRight,CLeft', 'Teleport: Hylia-See (Wassertempel)', '#0ea5e9'),
    ('Requiem der Geister', 'A,CDown,A,CRight,CDown,A', 'Teleport: Wüstenkoloss (Geistertempel)', '#f59e0b'),
    ('Nocturne des Schattens', 'CLeft,CRight,CRight,A,CLeft,CRight,CDown', 'Teleport: Friedhof Kakariko (Schattentempel)', '#c084fc'),
    ('Präludium des Lichts', 'CUp,CRight,CUp,CRight,CLeft,CUp', 'Teleport: Zitadelle der Zeit', '#fde047'),
)

NOTE_SPEC = {
    'CUp': ('▲', 0.15, '#facc15'),
    'CLeft': ('◀', 0.33, '#facc15'),
    'CRight': ('▶', 0.51, '#facc15'),
    'CDown': ('▼', 0.69, '#facc15'),
    'A': ('A', 0.87, '#38bdf8'),
}

OOT_TEMPLES = (
    ('oot_s1', 'Kokiri-Smaragd · Deku-Baum', 'Schleuder · Gohma mit Deku-Nuss + Sprungattacke (23–1–2 Brüder!)'),
    ('oot_s2', 'Goronen-Opal · Dodongos Höhle', 'Bomben · König Dodongo Bomben ins offene Maul werfen'),
    ('oot_s3', 'Zora-Saphir · Jabu-Jabus Bauch', 'Bumerang · Barinade Tentakel mit Bumerang trennen'),
    ('oot_m1', 'Amulett des Waldes · Waldtempel', 'Feenbogen · Phantom-Ganon Energiebälle mit Schwert zurückschlagen'),
    ('oot_m2', 'Amulett des Feuers · Feuertempel', 'Stahlhammer · Volvagia aus dem Loch schlagen + Hammerhieb'),
    ('oot_m3', 'Amulett des Wassers · Wassertempel', 'Enterhaken St.2 · Mittel-Turm: unter schwimmendem Block ein Schlüssel!'),
    ('oot_m4', 'Amulett des Schattens · Schattentempel', 'Gleitstiefel + Auge der Wahrheit (Brunnen in Kakariko!)'),
    ('oot_m5', 'Amulett der Geister · Geistertempel', 'Silberhandschuhe (Kind) + Spiegelschild (Erwachsener) gegen Koume/Kotake'),
    ('oot_bg', 'Biggoron-Schwert (Unzerbrechlich!)', 'Kiki-Ei -> Blaues Huhn -> Cojiro -> Pilz -> Säge -> Zerbr. Schwert -> Frosch -> Augentropfen!'),
)

OOT_REGIONS = (
    ('oot_r1', 'Kokiri-Wald & Verlorene Wälder (6 Skulltulas · 2 Herzteile)'),
    ('oot_r2', 'Hyrule-Ebene, Marktplatz & Schloss (4 Skulltulas · 3 Herzteile)'),
    ('oot_r3', 'Lon-Lon-Farm (4 Skulltulas nachts · Kisten-Schieberätsel Herzteil)'),
    ('oot_r4', 'Kakariko & Friedhof (8 Skulltulas · 6 Herzteile inkl. 50 Skulltulas)'),
    ('oot_r5', 'Todesberg & Goronia (8 Skulltulas · 4 Herzteile inkl. Kraterbohne)'),
    ('oot_r6', 'Zoras Fluss, Reich & Quelle (8 Skulltulas · 4 Herzteile inkl. Frösche)'),
    ('oot_r7', 'Hylia-See & Labor (5 Skulltulas · Angeln 10-Pfund-Fisch & Tauch-Herzteil)'),
    ('oot_r8', 'Gerudotal, Festung & Wüstenkoloss (6 Skulltulas · Bogenschießen zu Pferd)'),
)


class LinksAwakeningDeck(CompanionBase):
    KEY = 'zelda_la'
    TABS = ('Tausch & Lieder', 'Dungeons', 'Muscheln', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'zelda_la')

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#1a120b'))

        # Carved Koholint wood & rupee-emerald header
        hdr = QRectF(0, 0, W, 11.0 * u)
        g = QLinearGradient(0, 0, 0, hdr.height())
        g.setColorAt(0.0, qcol('#2e1f12'))
        g.setColorAt(1.0, qcol('#1b120a'))
        p.fillRect(hdr, g)

        # Rupee vector emblem
        rx, ry = 4.1 * u, 3.4 * u
        rup = QPolygonF([
            QPointF(rx, ry - 2.0 * u), QPointF(rx + 1.15 * u, ry - 0.9 * u), QPointF(rx + 1.15 * u, ry + 0.9 * u),
            QPointF(rx, ry + 2.0 * u), QPointF(rx - 1.15 * u, ry + 0.9 * u), QPointF(rx - 1.15 * u, ry - 0.9 * u),
        ])
        p.setPen(QPen(qcol('#a7f3d0'), 1.5))
        p.setBrush(qcol('#10b981'))
        p.drawPolygon(rup)

        w.text(p, 'COCOLINT-CHRONIK  ·  LINK’S AWAKENING', 6.5 * u, 1.2 * u, ('s', 2.35, 700, .03), qcol('#fef3c7'), W * 0.56)
        shells = int(self.get_val('shells', 0) or 0)
        hearts = int(self.get_val('hearts', 0) or 0)
        w.text(p, f'Zaubermuscheln: {shells}/50  ·  Herzteile: {hearts}/32', 6.5 * u, 4.05 * u, ('u', 1.55, 600), qcol('#6ee7b7'), W * 0.56)

        # Quick live map / inventory / save triggers
        btn_specs = (('Karte [−]', 'MINUS', 12.6 * u), ('Start / Speichern [+]', 'PLUS', 19.4 * u))
        bx = W - 2.9 * u - sum(bw for _, _, bw in btn_specs) - 1.0 * u
        for blbl, seq, bw in btn_specs:
            br = QRectF(bx, 1.15 * u, bw, 4.2 * u)
            self.chamfer_box(p, br, 0.55 * u, qcol('#3b2818'), qcol('#f59e0b'), 1.3)
            w.text(p, blbl, br.x(), br.y(), ('d', 1.48, 700), qcol('#fef3c7'), br.width(), 1, 4.2 / 1.48)
            w.hit(br, lambda seq=seq, blbl=blbl: self.send_pad(seq, blbl), name=f'la_btn:{seq}')
            bx += bw + 1.0 * u

        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, 6.2 * u, tw - 0.6 * u, 4.1 * u)
            on = (i == self.tab)
            self.chamfer_box(p, r, 0.6 * u, qcol('#f59e0b') if on else qcol('#261a10'),
                             qcol('#fef3c7') if on else qcol('#5c4028'), 1.5 if on else 1.0)
            w.text(p, lbl.upper(), r.x(), r.y(), ('d', 1.82, 700, .04),
                   qcol('#1a120b') if on else qcol('#e7d3b0'), r.width(), 1, 4.1 / 1.82)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'la_tab:{lbl}')

        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#1a120b')
            return True
        top = hdr.bottom() + 1.3 * u
        if self.tab == 0:
            self._paint_trades(p, top)
        elif self.tab == 1:
            self._paint_dungeons(p, top)
        else:
            self._paint_shells(p, top)
        return True

    def _paint_trades(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        # 3 Koholint Ocarina Songs banner
        songs = (
            ('Ballade vom Windfisch', 'Marin am Dorfplatz · weckt den Windfisch vor dem Ei'),
            ('Manbos Mambo', 'Mondfisch-Höhle · Teleport zu Manbos Teich & Dungeon-Eingang!'),
            ('Krötenrap (Seelied)', 'Mamu im Schilderwald (300 Rubine) · erweckt Fliegenden Gockel & Schildkrötenfelsen'),
        )
        sw = (cw - 2.0 * u) / 3
        for i, (stitle, sdesc) in enumerate(songs):
            r = QRectF(x0 + i * (sw + 1.0 * u), y, sw, 8.2 * u)
            chk = self.is_done(f'la_song_{i}')
            self.chamfer_box(p, r, 0.7 * u, qcol('#1c2e24') if chk else qcol('#261a10'),
                             qcol('#34d399') if chk else qcol('#8c6239'), 1.3)
            w.text(p, ('♪ ' if not chk else '✓ ') + stitle, r.x() + 1.1 * u, r.y() + 0.9 * u, ('s', 1.72, 700), qcol('#fef3c7'), sw - 2.2 * u)
            w.text(p, sdesc, r.x() + 1.1 * u, r.y() + 3.6 * u, ('u', 1.42, 400), qcol('#d6c2a5'), sw - 2.2 * u, 0, 1.25, 2)
            w.hit(r, lambda k=f'la_song_{i}': self.toggle_done(k), name=f'la_sng:{i}')
        y += 9.4 * u

        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_chain(top):
            cy = top
            rh = 5.6 * u
            for tid, item, how in LA_TRADES:
                r = QRectF(x0, cy, cw, rh - 0.5 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(tid)
                    self.chamfer_box(p, r, 0.55 * u, qcol('#1b2b20') if chk else qcol('#24180f'),
                                     qcol('#34d399') if chk else qcol('#4d3520'), 1.2)
                    self.txt_mid(p, ('✓ ' if chk else '○ ') + item, QRectF(r.x() + 1.2 * u, r.y(), cw * 0.33, r.height()),
                                 ('u', 1.72, 700), qcol('#6ee7b7') if chk else qcol('#fde68a'), 0)
                    self.txt_mid(p, how, QRectF(r.x() + cw * 0.35, r.y(), cw * 0.63, r.height()),
                                 ('u', 1.56, 400), qcol('#e7d3b0'), 0)
                    w.hit(r, lambda k=tid: self.toggle_done(k), name=f'la_tr:{tid}')
                cy += rh
            return cy

        w.scroller(p, 'la_trades', area, draw_chain)

    def _paint_dungeons(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_dng(top):
            cy = top
            rh = 6.8 * u
            for did, dname, instr, tip in LA_DUNGEONS:
                r = QRectF(x0, cy, cw, rh - 0.55 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(did)
                    self.chamfer_box(p, r, 0.6 * u, qcol('#1b2b20') if chk else qcol('#24180f'),
                                     qcol('#34d399') if chk else qcol('#6b4829'), 1.3)
                    w.text(p, ('★ ' if chk else '◇ ') + dname, r.x() + 1.3 * u, r.y() + 0.7 * u, ('s', 1.85, 700), qcol('#fef3c7'), cw * 0.52)
                    w.text(p, instr, r.x() + cw * 0.53, r.y() + 0.7 * u, ('d', 1.75, 700), qcol('#34d399' if chk else '#f59e0b'), cw * 0.45, 2)
                    w.text(p, tip, r.x() + 1.3 * u, r.y() + 3.55 * u, ('u', 1.52, 400), qcol('#d6c2a5'), cw - 2.6 * u)
                    w.hit(r, lambda k=did: self.toggle_done(k), name=f'la_d:{did}')
                cy += rh
            return cy

        w.scroller(p, 'la_dungeons', area, draw_dng)

    def _paint_shells(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        # Interactive Counters for Shells (0..50) and Heart Pieces (0..32)
        half = (cw - 1.6 * u) / 2
        for idx, (field, title, mx, col_h) in enumerate((('shells', 'ZAUBERMUSCHELN', 50, '#34d399'), ('hearts', 'HERZTEILE', 32, '#fb7185'))):
            val = int(self.get_val(field, 0) or 0)
            r = QRectF(x0 + idx * (half + 1.6 * u), y, half, 9.2 * u)
            self.chamfer_box(p, r, 0.8 * u, qcol('#24180f'), qcol(col_h), 1.5)
            w.text(p, f'{title}  ·  {val} / {mx}', r.x() + 1.4 * u, r.y() + 1.0 * u, ('d', 1.9, 700), qcol('#fef3c7'), half - 2.8 * u)
            bg = QRectF(r.x() + 1.4 * u, r.y() + 4.1 * u, half - 14.0 * u, 3.2 * u)
            p.fillRect(bg, qcol('#140d07'))
            p.fillRect(QRectF(bg.x(), bg.y(), bg.width() * min(1.0, val / mx), bg.height()), qcol(col_h, 0.85))
            b_dn = QRectF(r.right() - 11.4 * u, r.y() + 3.5 * u, 4.6 * u, 4.4 * u)
            b_up = QRectF(r.right() - 6.0 * u, r.y() + 3.5 * u, 4.6 * u, 4.4 * u)
            self.chamfer_box(p, b_dn, 0.4 * u, qcol('#3b2818'))
            self.chamfer_box(p, b_up, 0.4 * u, qcol(col_h, 0.35), qcol(col_h), 1.2)
            w.text(p, '−', b_dn.x(), b_dn.y(), ('d', 2.2, 700), qcol('#fef3c7'), b_dn.width(), 1, 4.4 / 2.2)
            w.text(p, '+', b_up.x(), b_up.y(), ('d', 2.2, 700), qcol('#ffffff'), b_up.width(), 1, 4.4 / 2.2)
            w.hit(b_dn, lambda f=field, m=mx: self.bump_val(f, -1, 0, m), name=f'la_dn:{field}')
            w.hit(b_up, lambda f=field, m=mx: self.bump_val(f, 1, 0, m), name=f'la_up:{field}')
        y += 10.6 * u

        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_zones(top):
            cy = top
            rh = 6.2 * u
            for zid, zname, cnt, hint in LA_ZONES:
                r = QRectF(x0, cy, cw, rh - 0.5 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(zid)
                    self.chamfer_box(p, r, 0.55 * u, qcol('#1b2b20') if chk else qcol('#24180f'),
                                     qcol('#34d399') if chk else qcol('#5c4028'), 1.2)
                    w.text(p, f'{"✓" if chk else "○"} {zname} ({cnt}×)', r.x() + 1.3 * u, r.y() + 0.65 * u, ('u', 1.72, 700), qcol('#fef3c7'), cw - 2.6 * u)
                    w.text(p, hint, r.x() + 1.3 * u, r.y() + 3.25 * u, ('u', 1.48, 400), qcol('#d6c2a5'), cw - 2.6 * u)
                    w.hit(r, lambda k=zid: self.toggle_done(k), name=f'la_z:{zid}')
                cy += rh
            return cy

        w.scroller(p, 'la_zones', area, draw_zones)


class OcarinaDeck(CompanionBase):
    KEY = 'oot'
    TABS = ('Okarina-Lieder', 'Tempel & Quest', 'Skulltulas', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'oot')

    def _draw_triforce(self, p, cx, cy, s):
        p.setPen(QPen(qcol('#fef08a'), 1.2))
        p.setBrush(QBrush(qcol('#eab308')))
        for dx, dy in ((0, -s * 0.55), (-s * 0.52, s * 0.45), (s * 0.52, s * 0.45)):
            tri = QPolygonF([QPointF(cx + dx, cy + dy - s * 0.5), QPointF(cx + dx - s * 0.5, cy + dy + s * 0.45), QPointF(cx + dx + s * 0.5, cy + dy + s * 0.45)])
            p.drawPolygon(tri)

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#0a1020'))

        hdr = QRectF(0, 0, W, 11.0 * u)
        g = QLinearGradient(0, 0, 0, hdr.height())
        g.setColorAt(0.0, qcol('#162447'))
        g.setColorAt(1.0, qcol('#0b1326'))
        p.fillRect(hdr, g)

        self._draw_triforce(p, 4.2 * u, 3.5 * u, 1.9 * u)
        w.text(p, 'CHRONIK DER ZEIT  ·  OCARINA OF TIME', 7.2 * u, 1.2 * u, ('s', 2.35, 700, .03), qcol('#fef08a'), W * 0.56)
        sk = int(self.get_val('skulltulas', 0) or 0)
        hp = int(self.get_val('oot_hearts', 0) or 0)
        w.text(p, f'Goldene Skulltulas: {sk}/100  ·  Herzteile: {hp}/36', 7.2 * u, 4.05 * u, ('u', 1.55, 600), qcol('#93c5fd'), W * 0.56)

        btn_specs = (('Start / Speichern [+]', 'PLUS', 19.4 * u), ('Karte [−]', 'MINUS', 12.6 * u))
        bx = W - 2.9 * u - sum(bw for _, _, bw in btn_specs) - 1.0 * u
        for blbl, seq, bw in btn_specs:
            br = QRectF(bx, 1.15 * u, bw, 4.2 * u)
            self.chamfer_box(p, br, 0.55 * u, qcol('#172554'), qcol('#eab308'), 1.3)
            w.text(p, blbl, br.x(), br.y(), ('d', 1.48, 700), qcol('#fef08a'), br.width(), 1, 4.2 / 1.48)
            w.hit(br, lambda seq=seq, blbl=blbl: self.send_pad(seq, blbl), name=f'oot_btn:{seq}')
            bx += bw + 1.0 * u

        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, 6.2 * u, tw - 0.6 * u, 4.1 * u)
            on = (i == self.tab)
            self.chamfer_box(p, r, 0.6 * u, qcol('#eab308') if on else qcol('#131e38'),
                             qcol('#fef08a') if on else qcol('#334155'), 1.5 if on else 1.0)
            w.text(p, lbl.upper(), r.x(), r.y(), ('d', 1.82, 700, .04),
                   qcol('#0a1020') if on else qcol('#cbd5e1'), r.width(), 1, 4.1 / 1.82)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'oot_tab:{lbl}')

        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#0a1020')
            return True
        top = hdr.bottom() + 1.3 * u
        if self.tab == 0:
            self._paint_songs(p, top)
        elif self.tab == 1:
            self._paint_temples(p, top)
        else:
            self._paint_skulltulas(p, top)
        return True

    def _paint_songs(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_staves(top):
            cy = top
            rh = 8.4 * u
            for idx, (sname, notes_csv, effect, acc_hex) in enumerate(OOT_SONGS):
                r = QRectF(x0, cy, cw, rh - 0.6 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    self.chamfer_box(p, r, 0.7 * u, qcol('#111a30'), qcol(acc_hex, 0.65), 1.3)
                    w.text(p, sname, r.x() + 1.3 * u, r.y() + 0.8 * u, ('s', 1.88, 700), qcol(acc_hex), cw * 0.36)
                    w.text(p, effect, r.x() + 1.3 * u, r.y() + 3.9 * u, ('u', 1.42, 400), qcol('#cbd5e1'), cw * 0.36, 0, 1.25, 2)

                    # Authentic 5-line golden Ocarina musical staff!
                    st_r = QRectF(r.x() + cw * 0.38, r.y() + 0.9 * u, cw * 0.45, rh - 2.4 * u)
                    p.fillRect(st_r, qcol('#090e1b'))
                    p.setPen(QPen(qcol('#eab308', 0.38), 1.0))
                    for ln in range(5):
                        ly = st_r.top() + st_r.height() * (0.15 + ln * 0.175)
                        p.drawLine(QPointF(st_r.left() + 0.6 * u, ly), QPointF(st_r.right() - 0.6 * u, ly))

                    notes = notes_csv.split(',')
                    step_x = (st_r.width() - 2.4 * u) / max(1, len(notes))
                    for ni, nkey in enumerate(notes):
                        glyph, rel_y, ncol = NOTE_SPEC[nkey]
                        nx = st_r.left() + 1.2 * u + (ni + 0.5) * step_x
                        ny = st_r.top() + rel_y * st_r.height()
                        nr = QRectF(nx - 1.35 * u, ny - 1.35 * u, 2.7 * u, 2.7 * u)
                        p.setPen(QPen(qcol('#0a1020'), 1.2))
                        p.setBrush(qcol(ncol))
                        p.drawEllipse(nr)
                        w.text(p, glyph, nr.x(), nr.y(), ('d', 1.48, 700), qcol('#0a1020'), nr.width(), 1, 2.7 / 1.48)

                    play_r = QRectF(r.right() - 14.2 * u, r.y() + 1.5 * u, 12.8 * u, rh - 3.6 * u)
                    self.chamfer_box(p, play_r, 0.55 * u, qcol(acc_hex, 0.22), qcol(acc_hex), 1.5)
                    self.txt_mid(p, '♪ SPIELEN', play_r, ('d', 1.75, 700), qcol('#ffffff'), 1)
                    w.hit(play_r, lambda seq='NOTE:' + notes_csv, sn=sname: self.send_pad(seq, f'Okarina spielt: {sn}'), name=f'oot_play:{idx}')
                cy += rh
            return cy

        w.scroller(p, 'oot_songs', area, draw_staves)

    def _paint_temples(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_t(top):
            cy = top
            rh = 6.8 * u
            for tid, tname, tip in OOT_TEMPLES:
                r = QRectF(x0, cy, cw, rh - 0.55 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(tid)
                    self.chamfer_box(p, r, 0.6 * u, qcol('#132a22') if chk else qcol('#111a30'),
                                     qcol('#4ade80') if chk else qcol('#3b4f7a'), 1.3)
                    w.text(p, ('◆ ' if chk else '◇ ') + tname, r.x() + 1.3 * u, r.y() + 0.7 * u, ('s', 1.85, 700),
                           qcol('#86efac') if chk else qcol('#fef08a'), cw - 2.6 * u)
                    w.text(p, tip, r.x() + 1.3 * u, r.y() + 3.55 * u, ('u', 1.5, 400), qcol('#cbd5e1'), cw - 2.6 * u)
                    w.hit(r, lambda k=tid: self.toggle_done(k), name=f'oot_t:{tid}')
                cy += rh
            return cy

        w.scroller(p, 'oot_temples', area, draw_t)

    def _paint_skulltulas(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        half = (cw - 1.6 * u) / 2
        for idx, (field, title, mx, col_h) in enumerate((('skulltulas', 'GOLDENE SKULLTULAS', 100, '#eab308'), ('oot_hearts', 'HERZTEILE', 36, '#f43f5e'))):
            val = int(self.get_val(field, 0) or 0)
            r = QRectF(x0 + idx * (half + 1.6 * u), y, half, 9.2 * u)
            self.chamfer_box(p, r, 0.8 * u, qcol('#111a30'), qcol(col_h), 1.5)
            w.text(p, f'{title}  ·  {val} / {mx}', r.x() + 1.4 * u, r.y() + 1.0 * u, ('d', 1.9, 700), qcol('#fef08a'), half - 2.8 * u)
            bg = QRectF(r.x() + 1.4 * u, r.y() + 4.1 * u, half - 14.0 * u, 3.2 * u)
            p.fillRect(bg, qcol('#070b15'))
            p.fillRect(QRectF(bg.x(), bg.y(), bg.width() * min(1.0, val / mx), bg.height()), qcol(col_h, 0.85))
            b_dn = QRectF(r.right() - 11.4 * u, r.y() + 3.5 * u, 4.6 * u, 4.4 * u)
            b_up = QRectF(r.right() - 6.0 * u, r.y() + 3.5 * u, 4.6 * u, 4.4 * u)
            self.chamfer_box(p, b_dn, 0.4 * u, qcol('#1e293b'))
            self.chamfer_box(p, b_up, 0.4 * u, qcol(col_h, 0.35), qcol(col_h), 1.2)
            w.text(p, '−', b_dn.x(), b_dn.y(), ('d', 2.2, 700), qcol('#ffffff'), b_dn.width(), 1, 4.4 / 2.2)
            w.text(p, '+', b_up.x(), b_up.y(), ('d', 2.2, 700), qcol('#ffffff'), b_up.width(), 1, 4.4 / 2.2)
            w.hit(b_dn, lambda f=field, m=mx: self.bump_val(f, -1, 0, m), name=f'oot_dn:{field}')
            w.hit(b_up, lambda f=field, m=mx: self.bump_val(f, 1, 0, m), name=f'oot_up:{field}')
        y += 10.6 * u

        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_regs(top):
            cy = top
            rh = 5.6 * u
            for rid, rlbl in OOT_REGIONS:
                r = QRectF(x0, cy, cw, rh - 0.5 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(rid)
                    self.chamfer_box(p, r, 0.55 * u, qcol('#132a22') if chk else qcol('#111a30'),
                                     qcol('#4ade80') if chk else qcol('#2d3d63'), 1.2)
                    self.txt_mid(p, f'{"✓" if chk else "○"}  {rlbl}', QRectF(r.x() + 1.3 * u, r.y(), cw - 2.6 * u, r.height()),
                                 ('u', 1.7, 600), qcol('#bbf7d0') if chk else qcol('#e2e8f0'), 0)
                    w.hit(r, lambda k=rid: self.toggle_done(k), name=f'oot_r:{rid}')
                cy += rh
            return cy

        w.scroller(p, 'oot_regs', area, draw_regs)


def Deck(w):
    comp = (w.RUN or {}).get('companion')
    return OcarinaDeck(w) if comp == 'oot' else LinksAwakeningDeck(w)
