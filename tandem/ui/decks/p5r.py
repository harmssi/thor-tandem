"""Persona 5 Royal – Phantom Thieves Metaverse Deck (01005CA01580E000 / Steam 1687950).
Rebuilds Tobias's Thor P5R (P5View.java) natively in QPainter:
- Stark #0B0B0B black + #E5191C Phantom-Red diagonal wedge + halftone dot pattern + slanted white/dark parallelograms
- 10-Element Shadow Affinity Lookup (Phys, Schuss, Feuer, Eis, Elek, Wind, Psy, Nukl, Segen, Fluch -> SW, RS, NU, RF, AB)
  filterable by Palace / Mementos
- All 23 Arcana Confidants with interactive Rank 0–10 progress & Royal 3rd-Semester deadline locks (Maruki/Kasumi/Akechi)
- Social Stats (Wissen, Charme, Können, Mut, Güte 1–5), Metaverse Battle/Dialogue Quick Pads & Exam/Crossword cheat sheet."""
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPolygonF
from decks.native_base import CompanionBase, qcol

ELEMENTS = ('Phys', 'Schuss', 'Feuer', 'Eis', 'Elek', 'Wind', 'Psy', 'Nukl', 'Segen', 'Fluch')
EL_COLS = ('#ff9a3c', '#c8c8d0', '#ff5a3c', '#6fd0ff', '#ffe600', '#5be38a', '#ff7ad9', '#63f0e0', '#fff3b0', '#b57bff')

PALACES = (
    ('all', 'Alle'),
    ('kamo', '1·Burg'),
    ('mada', '2·Museum'),
    ('kane', '3·Bank'),
    ('futa', '4·Pyramide'),
    ('okum', '5·Raumhafen'),
    ('sae', '6·Kasino'),
    ('shid', '7·Schiff'),
    ('maru', '8·Labor'),
)

# 10-char affinity string in P5View order: Phys, Gun, Fire, Ice, Elec, Wind, Psy, Nuke, Bless, Curse
# w=SW(Weak), r=RS(Resist), n=NU(Null), p=RF(Repel), d=AB(Drain), -=Normal
SHADOWS = (
    ('Jack Laterne', 'kamo', '--dwww----'),
    ('Pixie', 'kamo', '-w--rw---w'),
    ('Incubus', 'kamo', '--w-w---w-'),
    ('Mandrake', 'kamo', '--w--r----'),
    ('Bicorn', 'kamo', '----w----w'),
    ('Berith (Ritter)', 'kamo', '-nrd------'),
    ('Erzengel', 'kamo', '----w---nw'),
    ('Jack Frost', 'mada', '--wd------'),
    ('Mokoi', 'mada', '----rw----'),
    ('Shiisaa', 'mada', 'rr----w-nw'),
    ('Makami', 'mada', '-r--wrrn--'),
    ('Nue', 'mada', '--wdr----n'),
    ('Rakshasa', 'kane', 'r-w--w--wr'),
    ('Oni', 'kane', 'rr--------'),
    ('Königin Mab', 'kane', '--r--w----'),
    ('Take-Minakata', 'kane', '----rww--r'),
    ('Kin-Ki', 'kane', 'pr----w---'),
    ('Anubis (Kein Schw.!)', 'futa', '--------nn'),
    ('Thoth', 'futa', '--rrrrw-nw'),
    ('Lamia', 'futa', '---wr-w--n'),
    ('Mothman', 'futa', '-w--r-r---'),
    ('Naga', 'futa', '-r--nw---w'),
    ('Arahabaki', 'okum', 'pp----wwrr'),
    ('Girimehkala', 'okum', 'pp----w-wn'),
    ('Decarabia', 'okum', 'w-p---r-r-'),
    ('Lilim', 'okum', '---rw-w-wn'),
    (' Belphegor', 'okum', '--wdr---wr'),
    ('Walküre', 'sae', '-rwd----r-'),
    ('Rangda', 'sae', 'ppw-w---wn'),
    ('Skadi', 'sae', '---dn-----'),
    ('Thor', 'sae', 'r---d--rr-'),
    ('Baphomet', 'sae', '--r-----wn'),
    ('Cerberus', 'shid', '--dw--w---'),
    ('Oberon', 'shid', '----r-dwn-'),
    ('Kali', 'shid', 'r-p---d-r-'),
    ('Zaou-Gongen', 'shid', '--p-w---nn'),
    ('Fafnir (Labor-Panzer)', 'maru', 'rrddn--d--'),
    ('Hastur', 'maru', '--w--d-p-n'),
    ('Macabre', 'maru', '----r---wn'),
    ('Byakhee', 'maru', '--dww---wn'),
)

CONFIDANTS = (
    ('maruki', 'Ratsmitglied · Takuto Maruki ★ PFLICHT R9 bis 17.11.!', '3. Semester / Royal-Palast freischalten + Detox / Flow'),
    ('akechi', 'Gerechtigkeit · Goro Akechi ★ Royal R8 bis 17.11.', 'Wahres Ende & Showtime / 3. Erwachen im Januar'),
    ('kasumi', 'Glaube · Kasumi Yoshizawa ★ Royal R5 bis 18.12.', 'Ränge 6–10 im 3. Semester + Hinterhalt aus Distanz'),
    ('ryuji', 'Wagen · Ryuji Sakamoto', 'Rang 7: Sofort-Sieg (Insta-Kill) beim Sprinten durch schwache Schatten!'),
    ('kawakami', 'Mäßigung · Sadayo Kawakami', 'Rang 10: Spezialmassage – abends nach Palast/Mementos noch ausgehen!'),
    ('chihaya', 'Schicksal · Chihaya Mifune', 'Rang 5: Sympathie-Lesung (+Vertrauten-Punkte ohne Zeitverlust!) · R8: Himmels-Alarm'),
    ('hifumi', 'Stern · Hifumi Togo', 'Gruppenmitglieder mitten im Kampf einwechseln & Flucht-Garantie'),
    ('takemi', 'Tod · Tae Takemi', 'Rang 5/7: Kraftkleber (SP-Regeneration jede Runde!) im Klinik-Shop'),
    ('yoshida', 'Sonne · Toranosuke Yoshida', 'Mehr Geld & seltene Items bei Schatten-Verhandlungen'),
    ('futaba', 'Eremit · Futaba Sakura', 'Mementos-Scan, Gruppen-Buffs & Notfall-Schild'),
    ('mishima', 'Mond · Yuuki Mishima', 'Volle EP auch für Reserve-Gruppenmitglieder'),
    ('sojiro', 'Hierophant · Sojiro Sakura', 'Meister-Curry & SP-heilender Leblanc-Kaffee'),
    ('twins', 'Stärke · Caroline & Justine', 'Personas über eigener Stufe gegen Yen fusionieren (Rang 5!)'),
    ('ann', 'Liebende · Ann Takamaki', 'Verhandlungs-Rettung & Statusleiden-Heilung'),
    ('makoto', 'Priesterin · Makoto Niijima', 'Schatten-Affinitäten-Analyse im Kampf-HUD'),
    ('yusuke', 'Herrscher · Yusuke Kitagawa', 'Skill-Karten kostenlos duplizieren'),
    ('haru', 'Herrscherin · Haru Okumura', 'SP-Gemüse auf dem Schuldach anbauen'),
    ('iwai', 'Gehängter · Munehisa Iwai', 'Fernwaffen mit Statuseffekten modifizieren'),
    ('shinya', 'Turm · Shinya Oda', 'Down-Schuss (schlägt jeden Gegner nieder, ignoriert Resistenzen!)'),
    ('ohya', 'Teufel · Ichiko Ohya', 'Palast-Sicherheitsstufe steigt kaum noch'),
)

STATS = (
    ('st_know', 'WISSEN', 'Gelehrter -> Enzyklopädisch'),
    ('st_charm', 'CHARME', 'Kopfdreher -> Herzensbrecher'),
    ('st_prof', 'KÖNNEN', 'Meisterhaft -> Transzendent'),
    ('st_guts', 'MUT', 'Furchtlos -> Löwenherz'),
    ('st_kind', 'GÜTE', 'Selbstlos -> Engelsgleich'),
)

ANSWERS = (
    ('Kreuzworträtsel Leblanc', 'Blaue Berge · Semsterferien · Allergie · Melancholie · Sonnenfinsternis · Poltergeist · Garderobe · Geldwäsche · Charisma'),
    ('April–Mai Unterricht', 'Schurken · Linie B · Kakao · Synästhesie · Fatalismus · Kein Zeitverlust bei Kreuzworträtseln!'),
    ('Juni–Juli Unterricht', 'Heiligenschein · Königskrabbe · Grün (Geldscheine) · Hund · Milchstraße · Dreieck'),
    ('Sept.–Nov. Unterricht', 'Wohlstand · Chronostasis · Tomaten · 32 Flächen (Fußball) · Krähe · Scharlachrot'),
    ('Fusions-Alarm Tipp', '2× Gelbe Personas fusionieren = Unfall mit mächtigem kompletten Skillset!'),
)


class Deck(CompanionBase):
    KEY = 'p5r'
    TABS = ('Schatten', 'Vertraute', 'Alltag & Taktik', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'p5r')

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#0b0b0b'))

        # Signature Phantom-Red angled wedge + halftone dots (ported directly from P5View.java!)
        wedge = QPolygonF([QPointF(0, 0), QPointF(W, 0), QPointF(W, 8.8 * u), QPointF(0, 12.6 * u)])
        p.setPen(qcol('#000000', 0))
        p.setBrush(qcol('#e5191c'))
        p.drawPolygon(wedge)

        p.setBrush(qcol('#ffffff', 0.16))
        for ry in range(6):
            for rx in range(14):
                r_dot = (0.14 + (rx + ry) * 0.014) * u
                p.drawEllipse(QPointF(W - (14 - rx) * 2.1 * u + (ry % 2) * 0.9 * u, 0.9 * u + ry * 1.45 * u), r_dot, r_dot)

        # Stark white skewed title plate
        plate = QRectF(2.4 * u, 1.0 * u, 42.0 * u, 4.3 * u)
        self.slant(p, plate, 1.4 * u, qcol('#ffffff'), qcol('#0b0b0b'), 2.2)
        w.text(p, 'TAKE YOUR HEART  ·  PHANTOM-DECK', plate.x() + 1.8 * u, plate.y(), ('d', 2.25, 700, .05), qcol('#0b0b0b'), plate.width() - 2.4 * u, 0, 4.3 / 2.25)

        # Slanted rebellion tab bar
        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        ty = 6.2 * u
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.35 * u, ty, tw - 0.7 * u, 4.3 * u)
            on = (i == self.tab)
            self.slant(p, r, 0.9 * u, qcol('#0b0b0b') if on else qcol('#ffffff'),
                       qcol('#ffe600') if on else qcol('#0b0b0b'), 2.0 if on else 1.5)
            w.text(p, lbl.upper(), r.x() + 0.4 * u, r.y(), ('d', 1.92, 700, .05),
                   qcol('#ffe600') if on else qcol('#0b0b0b'), r.width(), 1, 4.3 / 1.92)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'p5_tab:{lbl}')

        top = 12.2 * u
        if self.is_tools_tab():
            self.paint_tools_embedded(p, 11.4 * u, '#0b0b0b')
            return True
        if self.tab == 0:
            self._paint_shadows(p, top)
        elif self.tab == 1:
            self._paint_confidants(p, top)
        else:
            self._paint_today(p, top)
        return True

    def _paint_shadows(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.4 * u, W - 4.8 * u

        cur_pal = self.get_val('palace', 'all')
        pw = cw / len(PALACES)
        for i, (pid, plbl) in enumerate(PALACES):
            r = QRectF(x0 + i * pw + 0.15 * u, y, pw - 0.3 * u, 3.8 * u)
            on = (pid == cur_pal)
            self.slant(p, r, 0.55 * u, qcol('#e5191c') if on else qcol('#1c1c1c'), qcol('#ffffff') if on else None, 1.3)
            w.text(p, plbl, r.x() + 0.2 * u, r.y(), ('d', 1.52, 700), qcol('#ffffff') if on else qcol('#a3a3a3'), r.width(), 1, 3.8 / 1.52)
            w.hit(r, lambda pid=pid: self.set_val('palace', pid), name=f'p5_pal:{pid}')
        y += 4.6 * u

        # Column header for the 10 P5R elements
        name_w = cw * 0.31
        cell_area = cw - name_w
        cell_w = cell_area / 10.0
        for ei, el in enumerate(ELEMENTS):
            ex = x0 + name_w + ei * cell_w
            w.text(p, el, ex, y, ('d', 1.48, 700), qcol(EL_COLS[ei]), cell_w, 1)
        y += 2.4 * u

        rows = [s for s in SHADOWS if cur_pal == 'all' or s[1] == cur_pal]
        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_list(top):
            cy = top
            rh = 5.4 * u
            marks = {'w': ('SW', '#e5191c', '#ffffff'), 'r': ('RS', '#303036', '#d4d4d8'),
                     'n': ('NU', '#ffffff', '#0b0b0b'), 'p': ('RF', '#34e0ff', '#0b0b0b'),
                     'd': ('AB', '#5be38a', '#0b0b0b')}
            for idx, (sname, _, aff) in enumerate(rows):
                r = QRectF(x0, cy, cw, rh - 0.5 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    self.slant(p, r, 0.5 * u, qcol('#161618' if idx % 2 == 0 else '#1e1e22'))
                    self.txt_mid(p, sname.strip(), QRectF(x0 + 1.1 * u, cy, name_w - 1.5 * u, r.height()), ('u', 1.72, 700), qcol('#ffffff'), 0)
                    for ei in range(10):
                        ch = aff[ei] if ei < len(aff) else '-'
                        cr = QRectF(x0 + name_w + ei * cell_w + 0.22 * u, cy + 0.45 * u, cell_w - 0.44 * u, rh - 1.4 * u)
                        if ch in marks:
                            txt, bg, fg = marks[ch]
                            self.slant(p, cr, 0.35 * u, qcol(bg))
                            self.txt_mid(p, txt, cr, ('d', 1.65, 700), qcol(fg), 1)
                        else:
                            self.slant(p, cr, 0.35 * u, qcol('#252529'))
                            self.txt_mid(p, '·', cr, ('m', 1.5, 400), qcol('#71717a'), 1)
                cy += rh
            return cy

        w.scroller(p, 'p5_shadows', area, draw_list)

    def _paint_confidants(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.4 * u, W - 4.8 * u
        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_conf(top):
            cy = top
            rh = 7.4 * u
            for cid, title, perk in CONFIDANTS:
                r = QRectF(x0, cy, cw, rh - 0.6 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    rk = int(self.get_val('cf_' + cid, 0) or 0)
                    royal = '★' in title
                    self.slant(p, r, 0.65 * u, qcol('#221114' if royal else '#17171a'),
                               qcol('#ffe600') if rk >= 10 else (qcol('#e5191c') if royal else qcol('#333338')), 1.4)
                    w.text(p, title, r.x() + 1.4 * u, r.y() + 0.7 * u, ('d', 1.88, 700),
                           qcol('#ffe600') if rk >= 10 else qcol('#ffffff'), cw - 20.0 * u)
                    w.text(p, perk, r.x() + 1.4 * u, r.y() + 3.7 * u, ('u', 1.5, 400), qcol('#c4c4cc'), cw - 20.0 * u)
                    # Rank badge & - / + buttons
                    minus_r = QRectF(r.right() - 17.5 * u, r.y() + 1.1 * u, 4.4 * u, 4.6 * u)
                    plus_r = QRectF(r.right() - 5.4 * u, r.y() + 1.1 * u, 4.4 * u, 4.6 * u)
                    badge_r = QRectF(minus_r.right() + 0.4 * u, r.y() + 1.1 * u, 6.9 * u, 4.6 * u)
                    self.slant(p, minus_r, 0.35 * u, qcol('#2b2b30'))
                    self.slant(p, plus_r, 0.35 * u, qcol('#e5191c'))
                    self.slant(p, badge_r, 0.35 * u, qcol('#ffffff' if rk >= 10 else '#0b0b0b'), qcol('#ffffff', 0.4), 1.0)
                    w.text(p, '−', minus_r.x(), minus_r.y(), ('d', 2.1, 700), qcol('#ffffff'), minus_r.width(), 1, 4.6 / 2.1)
                    w.text(p, '+', plus_r.x(), plus_r.y(), ('d', 2.1, 700), qcol('#ffffff'), plus_r.width(), 1, 4.6 / 2.1)
                    w.text(p, 'MAX' if rk >= 10 else f'R {rk}', badge_r.x(), badge_r.y(), ('d', 1.85, 700),
                           qcol('#0b0b0b') if rk >= 10 else qcol('#ffe600'), badge_r.width(), 1, 4.6 / 1.85)
                    w.hit(minus_r, lambda k='cf_' + cid: self.bump_val(k, -1, 0, 10), name=f'p5_cfm:{cid}')
                    w.hit(plus_r, lambda k='cf_' + cid: self.bump_val(k, 1, 0, 10), name=f'p5_cfp:{cid}')
                cy += rh
            return cy

        w.scroller(p, 'p5_conf', area, draw_conf)

    def _paint_today(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.4 * u, W - 4.8 * u

        # 5 Social Stats rank bars (tap to cycle 1..5)
        sw = cw / 5.0
        for i, (sk, sname, sub) in enumerate(STATS):
            val = int(self.get_val(sk, 1) or 1)
            r = QRectF(x0 + i * sw + 0.25 * u, y, sw - 0.5 * u, 9.2 * u)
            self.slant(p, r, 0.55 * u, qcol('#18181c'), qcol('#ffe600' if val >= 5 else '#e5191c'), 1.4)
            w.text(p, sname, r.x() + 0.8 * u, r.y() + 0.8 * u, ('d', 1.75, 700, .04), qcol('#ffe600'), r.width() - 1.6 * u)
            w.text(p, f'★ {val} / 5', r.x() + 0.8 * u, r.y() + 3.6 * u, ('m', 1.85, 700), qcol('#ffffff'), r.width() - 1.6 * u)
            bar_bg = QRectF(r.x() + 0.8 * u, r.y() + 6.9 * u, r.width() - 1.6 * u, 1.2 * u)
            p.fillRect(bar_bg, qcol('#2e2e34'))
            p.fillRect(QRectF(bar_bg.x(), bar_bg.y(), bar_bg.width() * (val / 5.0), bar_bg.height()), qcol('#ffe600' if val >= 5 else '#e5191c'))
            w.hit(r, lambda sk=sk, val=val: self.set_val(sk, 1 if val >= 5 else val + 1), name=f'p5_st:{sk}')
        y += 10.6 * u

        # Metaverse & Dialogue Live Touch Pads (UDP -> P5R)
        pads = (
            ('ALL-OUT ATTACK', 'X', 'Generalangriff!', '#e5191c'),
            ('DIEBESAUGE', 'ZL', 'Beute & Fallen', '#34e0ff'),
            ('BATON PASS', 'R', 'Staffelwechsel', '#ffe600'),
            ('AUTO-DIALOG', 'PLUS', 'Textlauf an/aus', '#ffffff'),
            ('DIALOG-LOG', 'MINUS', 'Verlauf lesen', '#c4c4cc'),
        )
        pw = cw / len(pads)
        for i, (lbl, seq, hint, col_hex) in enumerate(pads):
            r = QRectF(x0 + i * pw + 0.25 * u, y, pw - 0.5 * u, 7.2 * u)
            self.slant(p, r, 0.55 * u, qcol('#1b1b20'), qcol(col_hex), 1.6)
            w.text(p, lbl, r.x() + 0.7 * u, r.y() + 1.0 * u, ('d', 1.68, 700), qcol(col_hex), r.width() - 1.4 * u)
            w.text(p, f'[{seq}] {hint}', r.x() + 0.7 * u, r.y() + 4.0 * u, ('u', 1.42, 500), qcol('#d4d4d8'), r.width() - 1.4 * u)
            w.hit(r, lambda seq=seq, lbl=lbl: self.send_pad(seq, f'{lbl} ({seq})'), name=f'p5_pad:{seq}')
        y += 8.6 * u

        # Classroom & Crossword Reference
        rem = H - y - 1.8 * u
        rh = rem / len(ANSWERS)
        for idx, (head, ans) in enumerate(ANSWERS):
            ry = y + idx * rh
            r = QRectF(x0, ry, cw, rh - 0.45 * u)
            self.slant(p, r, 0.45 * u, qcol('#151518' if idx % 2 == 0 else '#1d1d22'))
            w.text(p, head.upper(), r.x() + 1.2 * u, r.y() + 0.55 * u, ('d', 1.65, 700), qcol('#ff5fd2'), cw * 0.28)
            w.text(p, ans, r.x() + cw * 0.29, r.y() + 0.55 * u, ('u', 1.52, 500), qcol('#f4f4f5'), cw * 0.69, 0, 1.25, 2)
