"""Bespoke Companions for Pokémon: Let's Go, Sonic Mania Plus, FINAL FANTASY RESONANCE & Tomodachi Life:
1. Pokémon: Let's Go, Evoli! (0100187003A36000 · 'letsgo'): Silph-Co. Pokédex Mk.E
   - Real interactive 18-Type Dual-Defender Effectiveness Calculator (4x, 2x, 0.5x, 0.25x, 0x)
   - Catch-Combo Shiny / Guaranteed-IV Calculator + Eevee Partner Moves & Secret Techniques + 8 Kanto Gyms
2. Sonic Mania Plus (01009AA000FAA000 · 'mania'): Studiopolis Chevron Tachometer
   - Interactive 7 Chaos Emeralds Ring + 12 Zones Giant Special-Ring Guide
   - Sonic / Tails / Knuckles / Mighty / Ray Movesets & Boss Weaknesses
3. FINAL FANTASY RESONANCE (0100606026F12000 · 'ffres'): Astral Crystal Chronicle
   - Elemental Resonance & Stagger Chain Matrix + Live Quick Menu/Map triggers
   - High-Rank Hunts (Jagdbrett S/A/B) & Chapter / Esper Codex
4. Tomodachi Life: Living the Dream (010051F0207B2000 · 'tomodachi'): Sunny Island Town Hall Book
   - Interactive 16-Personality Compass (4 sliders -> exact Mii Personality & Harmony match!)
   - Daily Island Event Schedule & Landmark Milestones."""
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QLinearGradient, QPen, QPolygonF
from decks.native_base import CompanionBase, qcol

# ---- 1. Pokémon: Let's Go, Evoli! (18-Type Matrix) ------------------------------------------------------------------
PK_TYPES = (
    'Normal', 'Feuer', 'Wasser', 'Pflanze', 'Elektro', 'Eis', 'Kampf', 'Gift', 'Boden',
    'Flug', 'Psycho', 'Käfer', 'Gestein', 'Geist', 'Drache', 'Unlicht', 'Stahl', 'Fee',
)
PK_COLS = (
    '#a8a77a', '#ee8130', '#6390f0', '#7ac74c', '#f7d02c', '#96d9d6', '#c22e28', '#a33ea1', '#e2bf65',
    '#a98ff3', '#f95587', '#a6b91a', '#b6a136', '#735797', '#6f35fc', '#705746', '#b7b7ce', '#d685ad',
)
# Attacking type -> (super_effective_def_indices, not_very_effective_def_indices, immune_def_indices)
PK_ATK = {
    0: ((), (12, 16), (13,)),
    1: ((3, 5, 11, 16), (1, 2, 12, 14), ()),
    2: ((1, 8, 12), (2, 3, 14), ()),
    3: ((2, 8, 12), (1, 3, 7, 9, 11, 14, 16), ()),
    4: ((2, 9), (3, 4, 14), (8,)),
    5: ((3, 8, 9, 14), (1, 2, 5, 16), ()),
    6: ((0, 5, 12, 15, 16), (7, 9, 10, 11, 17), (13,)),
    7: ((3, 17), (7, 8, 12, 13), (16,)),
    8: ((1, 4, 7, 12, 16), (3, 11), (9,)),
    9: ((3, 6, 11), (4, 12, 16), ()),
    10: ((6, 7), (10, 16), (15,)),
    11: ((3, 10, 15), (1, 6, 7, 9, 13, 16, 17), ()),
    12: ((1, 5, 9, 11), (6, 8, 16), ()),
    13: ((10, 13), (15,), (0,)),
    14: ((14,), (16,), (17,)),
    15: ((10, 13), (6, 15, 17), ()),
    16: ((5, 12, 17), (1, 2, 4, 16), ()),
    17: ((6, 14, 15), (1, 7, 16), ()),
}

def pk_def_matchups(t1, t2=None):
    """Return grouped incoming attack multipliers {'4x': [], '2x': [], '0.5x': [], '0.25x': [], '0x': []} against (t1, t2)."""
    res = {'4x': [], '2x': [], '0.5x': [], '0.25x': [], '0x': []}
    defs = [t1] if (t2 is None or t2 == t1) else [t1, t2]
    for atk_i, atk_name in enumerate(PK_TYPES):
        se, nve, imm = PK_ATK[atk_i]
        mult = 1.0
        for d in defs:
            if d in imm:
                mult *= 0.0
            elif d in se:
                mult *= 2.0
            elif d in nve:
                mult *= 0.5
        if mult == 4.0:
            res['4x'].append((atk_i, atk_name))
        elif mult == 2.0:
            res['2x'].append((atk_i, atk_name))
        elif mult == 0.5:
            res['0.5x'].append((atk_i, atk_name))
        elif mult == 0.25:
            res['0.25x'].append((atk_i, atk_name))
        elif mult == 0.0:
            res['0x'].append((atk_i, atk_name))
    return res


PK_GYMS = (
    ('pk_g1', '1 · Felsorden (Rocko · Marmoria)', 'Gestein/Boden -> Wasser & Pflanze (Evoli lernt Doppelkick früh!)'),
    ('pk_g2', '2 · Quellorden (Misty · Azuria)', 'Wasser -> Elektro & Pflanze (Bizzelturbo beim Attacken-Lehrer!)'),
    ('pk_g3', '3 · Donnerorden (Major Bob · Orania)', 'Elektro -> Boden (Digda-Höhle direkt östlich von Orania!)'),
    ('pk_g4', '4 · Farborden (Erika · Prismania)', 'Pflanze/Gift -> Feuer (Flackerbrand), Flug, Eis & Psycho'),
    ('pk_g5', '5 · Seelenorden (Koga · Fuchsania)', 'Gift -> Psycho (Psystrahl) & Boden'),
    ('pk_g6', '6 · Sumpforden (Sabrina · Saffronia)', 'Psycho -> Unlicht ( Knirscher / Flatterflug ) & Geist'),
    ('pk_g7', '7 · Vulkanorden (Pyro · Zinnoberinsel)', 'Feuer -> Wasser (Blubbsauger), Boden & Gestein'),
    ('pk_g8', '8 · Erdorden (Giovanni · Vertania)', 'Boden -> Wasser, Pflanze & Eis · danach Siegesstraße & Top Vier!'),
    ('pk_g9', 'Geheimhöhle Azuria · Mewtu (St. 70)', 'Vor dem Kampf speichern · Unlicht/Geist bricht Psycho-Barriere in 5 Min.'),
)

# ---- 2. Sonic Mania Plus Data ---------------------------------------------------------------------------------------
MANIA_ZONES = (
    ('sm_z01', '1 · Green Hill Zone', 'Akt 1: Obere Brücke hinter Korkenzieher · Akt 2: Über S-Röhre am Start'),
    ('sm_z02', '2 · Chemical Plant Zone', 'Akt 1: Rechts unter gelbem Sprungbrett · Akt 2: Hinter blauer Gel-Grube'),
    ('sm_z03', '3 · Studiopolis Zone', 'Akt 1: Popcorn-Maschine ganz nach oben · Akt 2: Hinter Lotterie-Röhren'),
    ('sm_z04', '4 · Flying Battery Zone', 'Akt 1: Magnetdecke im Innenraum · Akt 2: Linke Außenwand per Propeller'),
    ('sm_z05', '5 · Press Garden Zone', 'Akt 1: Kistenstapel mit Feuer-Schild · Akt 2: Gefrorener Birkenwald oben'),
    ('sm_z06', '6 · Stardust Speedway Zone', 'Akt 1: Hohe Ranken-Plattform Mitte · Akt 2: Vor dem Katapult-Bogen'),
    ('sm_z07', '7 · Hydrocity Zone', 'Akt 1: Wasserstrudel-Kammer rechts · Akt 2: Nach der Riesenwalzen-Flucht'),
    ('sm_z08', '8 · Mirage Saloon Zone', 'Akt 1/2: Hinter drehbaren Saloon-Türen & Riesenkaktus-Röhren'),
    ('sm_z09', '9 · Oil Ocean Zone', 'Akt 1: Obere grüne Plattform vor Ziel · Akt 2: U-Boot-Lagerraum'),
    ('sm_z10', '10 · Lava Reef Zone', 'Akt 1: Bohr-Schacht links · Akt 2: Kristallhöhle mit Flammen-Schild'),
    ('sm_z11', '11 · Metallic Madness Zone', 'Akt 1: Mini-Sonic-Röhre im Hintergrund · Akt 2: Greifarm-Schacht'),
    ('sm_z12', '12 · Titanic Monarch Zone', '7 Chaos Emeralds gesammelt -> Wahres Finale in Egg Reverie Zone!'),
)

# ---- 3. FINAL FANTASY RESONANCE Data --------------------------------------------------------------------------------
FFR_TACTICS = (
    ('Elementar-Resonanz (2er-Kette)', 'Feuer + Wind = Flammensturm · Eis + Blitz = Supraleiter (+65 % Stagger-Bruch!)'),
    ('Äther-Bruch (Stagger-Fenster)', 'Erst Debuff/Imperil setzen, Leiste brechen -> Limit-Resonanz erst ab 150 % Multiplikator zünden!'),
    ('Perfekter Konter / Ausweich-Fokus', 'Kurz vor rotem Aufblitzen ausweichen lädt 1 volle ATB-/Resonanz-Kugel sofort auf'),
    ('Gruppen-Synergie', 'Brecher + Magier + Wächter hält Boss-Aggro stabil und verdoppelt Ketten-Dauer'),
)

FFR_HUNTS = (
    ('ffr_h1', 'Rang B · Eisenklauen-Behemoth (Grenzsteppe · Blitz-Schwäche)'),
    ('ffr_h2', 'Rang B · Nebel-Morbol (Sumpfwald · Feuer-Resonanz & Antidot-Amulett!)'),
    ('ffr_h3', 'Rang A · Kristall-Drakon (Äther-Minen · Flügel zuerst brechen)'),
    ('ffr_h4', 'Rang A · Karmesin-Tombery (Ruinen · Konter-Stellung meiden, Distanzmagie!)'),
    ('ffr_h5', 'Rang A · Sturm-Garuda (Hochklippen · Eis/Gravitation unterbricht Luftwirbel)'),
    ('ffr_h6', 'Rang S · Chronos-Wächter (Astral-Sanktuarium · Stop-Immunität anlegen)'),
    ('ffr_h7', 'Rang S · Omega-Resonanzkern (Geheimlabor · Donner-Äther + Heil-Kette)'),
    ('ffr_h8', 'Alle Esper-Prüfungen & Ultima-Waffen-Schmiede abgeschlossen'),
)

# ---- 4. Tomodachi Life: Living the Dream Data -----------------------------------------------------------------------
TL_GRID = {
    (0, 0): ('Sanft · Träumerisch', 'Fantasievoll, friedliebend – harmoniert perfekt mit Lebhaft-Kumpelhaft'),
    (0, 1): ('Sanft · Fürsorglich', 'Hilfsbereit, warmherzig – schlichtet Insel-Streits zuverlässig'),
    (1, 0): ('Reserviert · Denker', 'Ruhig, analytisch – liebt Bücher, Schach & ruhige Strandspaziergänge'),
    (1, 1): ('Reserviert · Perfektionist', 'Ordentlich, zielstrebig – mag klare Struktur & Musikinstrumente'),
    (2, 0): ('Lebhaft · Charmeur', 'Ausdrucksstark, kreativ – geborener Star auf der Traumbühne!'),
    (2, 1): ('Lebhaft · Kumpelhaft', 'Gesellig, herzlich – schließt am schnellsten neue Freundschaften'),
    (3, 0): ('unabhängig · Freigeist', 'Originell, abenteuerlustig – überrascht mit schrägen Träumen'),
    (3, 1): ('Direkt · Tatkräftig', 'Sportlich, entschlossen – treibt Insel-Projekte voran'),
}

TL_EVENTS = (
    ('tl_e1', '07:00 – 11:00 · Morgenmarkt', 'Frische Insel-Zutaten zum halben Preis am Strandstand'),
    ('tl_e2', '12:00 – 14:00 · Mittags-Café & Parktreff', 'Beste Zeit für Freundschafts-Gespräche & Gerüchte'),
    ('tl_e3', '15:00 – 18:00 · Nachmittags-Flohmarkt', 'Seltene Kleidungsstücke & Inneneinrichtungen im Park'),
    ('tl_e4', '19:00 – 22:00 · Traumbühne & Frage-Show', 'Quirky Questions, Konzerte & gemeinsame Insel-Auftritte'),
    ('tl_e5', 'Ab 22:00 · Schlafende Miis (Traumblasen!)', 'Tippe auf Traumblasen für seltene Schätze & lustige Rituale!'),
    ('tl_e6', 'Täglich · Spendenbrunnen & Foto-Studio', 'Tages-Einnahmen abholen & Gruppenfotos im Rathaus sichern'),
)


class LetsGoDeck(CompanionBase):
    KEY = 'letsgo'
    TABS = ('Typen-Rechner', 'Fangserie & Evoli', '8 Orden & Liga', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'letsgo')

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#0d181e'))

        # Silph-Co. Pokédex crimson bezel + cyan lens
        hdr = QRectF(0, 0, W, 11.0 * u)
        p.fillRect(hdr, qcol('#991b1b'))
        lens = QRectF(2.6 * u, 1.15 * u, 4.1 * u, 4.1 * u)
        p.setPen(QPen(qcol('#ffffff'), 2.0))
        p.setBrush(qcol('#38bdf8'))
        p.drawEllipse(lens)

        w.text(p, 'SILPH-POKÉDEX Mk.E  ·  LET’S GO, EVOLI!', 7.8 * u, 1.15 * u, ('d', 2.4, 700, .04), qcol('#ffffff'), W * 0.65)
        combo = int(self.get_val('combo', 0) or 0)
        iv_txt = '4× 31-DV garantiert!' if combo >= 31 else ('3× 31-DV' if combo >= 21 else ('2× 31-DV' if combo >= 11 else '0–1× 31-DV'))
        w.text(p, f'Aktive Fangserie: {combo}  ({iv_txt})', 7.8 * u, 4.0 * u, ('u', 1.55, 600), qcol('#fde68a'), W * 0.65)

        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, 6.2 * u, tw - 0.6 * u, 4.1 * u)
            on = (i == self.tab)
            w.capsule(p, r, qcol('#fde047') if on else qcol('#5c0f12'), qcol('#ffffff') if on else qcol('#fca5a5', 0.45))
            w.text(p, lbl.upper(), r.x(), r.y(), ('d', 1.82, 700, .04), qcol('#450a0a') if on else qcol('#fee2e2'), r.width(), 1, 4.1 / 1.82)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'pk_tab:{lbl}')

        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#0d181e')
            return True
        top = hdr.bottom() + 1.3 * u
        if self.tab == 0:
            self._paint_types(p, top)
        elif self.tab == 1:
            self._paint_combo(p, top)
        else:
            self._paint_gyms(p, top)
        return True

    def _paint_types(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        t1 = int(self.get_val('pk_t1', 2) or 0) % 18
        t2_raw = self.get_val('pk_t2', -1)
        t2 = int(t2_raw) if isinstance(t2_raw, int) and 0 <= t2_raw < 18 and t2_raw != t1 else None

        # 18 Type pills (3 rows x 6): tap once = primary type, tap another = dual type, tap active 2nd = clear 2nd!
        bw = (cw - 2.5 * u) / 6.0
        bh = 4.1 * u
        for i, tname in enumerate(PK_TYPES):
            col, row = i % 6, i // 6
            r = QRectF(x0 + col * (bw + 0.5 * u), y + row * (bh + 0.45 * u), bw, bh)
            sel = 1 if i == t1 else (2 if i == t2 else 0)
            w.capsule(p, r, qcol(PK_COLS[i], 0.92 if sel else 0.25), qcol('#ffffff') if sel else qcol(PK_COLS[i], 0.65))
            tag = f'① {tname}' if sel == 1 else (f'② {tname}' if sel == 2 else tname)
            self.txt_mid(p, tag, r, ('d', 1.62, 700), qcol('#090d11') if sel else qcol('#f1f5f9'), 1)

            def tap_type(idx=i):
                c1 = int(self.get_val('pk_t1', 2) or 0) % 18
                c2 = self.get_val('pk_t2', -1)
                if idx == c1:
                    if isinstance(c2, int) and 0 <= c2 < 18:
                        self.set_val('pk_t1', c2)
                        self.set_val('pk_t2', -1)
                elif idx == c2:
                    self.set_val('pk_t2', -1)
                elif not isinstance(c2, int) or c2 < 0:
                    self.set_val('pk_t2', idx)
                else:
                    self.set_val('pk_t1', idx)
                    self.set_val('pk_t2', -1)

            w.hit(r, tap_type, name=f'pk_type:{tname}')

        y += 3 * (bh + 0.45 * u) + 0.8 * u
        match = pk_def_matchups(t1, t2)
        pair_lbl = PK_TYPES[t1] + (f' + {PK_TYPES[t2]}' if t2 is not None else ' (Monotyp)')
        w.text(p, f'GEGNER-TYP: {pair_lbl.upper()}  —  WOMIT ANGREIFEN?', x0, y, ('d', 1.9, 700, .04), qcol('#67e8f9'), cw)
        y += 2.8 * u

        groups = (
            ('4× EXTREM EFFEKTIV', match['4x'], '#22c55e'),
            ('2× SEHR EFFEKTIV', match['2x'], '#4ade80'),
            ('½× WENIG EFFEKTIV', match['0.5x'], '#f59e0b'),
            ('¼× KAUM WIRKUNG', match['0.25x'], '#fb923c'),
            ('0× IMMUN (KEIN SCHADEN)', match['0x'], '#ef4444'),
        )
        shown = [g for g in groups if g[1]] or [('NEUTRAL', [], '#94a3b8')]
        rh = min(8.6 * u, (H - y - 1.8 * u) / len(shown))
        for idx, (glbl, items, col_h) in enumerate(shown):
            ry = y + idx * rh
            r = QRectF(x0, ry, cw, rh - 0.55 * u)
            w.box(p, r, 0.85 * u, qcol('#13232c'), qcol(col_h, 0.7))
            self.txt_mid(p, glbl, QRectF(r.x() + 1.4 * u, r.y(), cw * 0.33, r.height()), ('d', 1.82, 700), qcol(col_h), 0)
            names = '  ·  '.join(n for _, n in items) if items else 'Alle übrigen Typen treffen 1× normal'
            self.txt_mid(p, names, QRectF(r.x() + cw * 0.35, r.y(), cw * 0.63, r.height()), ('u', 1.72, 600), qcol('#f8fafc'), 0)
        tip_y = y + len(shown) * rh + 0.8 * u
        if H - tip_y >= 5.2 * u:
            tr = QRectF(x0, tip_y, cw, H - tip_y - 1.8 * u)
            w.box(p, tr, 0.85 * u, qcol('#101d24'), qcol('#274352'))
            w.text(p, 'TIPP: Tippe auf einen 2. Typ für Doppel-Typ-Gegner (z. B. Garados = Wasser + Flug -> 4× Elektro!), nochmals tippen zum Löschen.',
                   tr.x() + 1.4 * u, tr.y() + 1.1 * u, ('u', 1.55, 500), qcol('#94a3b8'), cw - 2.8 * u, 0, 1.35, 2)

    def _paint_combo(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        combo = int(self.get_val('combo', 0) or 0)
        shiny = '1 : 273 (mit Schillerpin + Lockparfüm!)' if combo >= 31 else ('1 : 585' if combo >= 21 else ('1 : 1024' if combo >= 11 else '1 : 4096 (Basis)'))
        box_r = QRectF(x0, y, cw, 9.6 * u)
        w.box(p, box_r, 1.1 * u, qcol('#13232c'), qcol('#38bdf8'))
        w.text(p, f'FANGSERIE: {combo} IN FOLGE', x0 + 1.6 * u, y + 1.1 * u, ('d', 2.2, 700), qcol('#fde047'), cw * 0.5)
        w.text(p, f'Shiny-Chance (nächster Spawn): {shiny}', x0 + 1.6 * u, y + 4.8 * u, ('u', 1.62, 500), qcol('#67e8f9'), cw * 0.62)

        for bi, (lbl, delta, rst) in enumerate((('Reset', 0, True), ('−1', -1, False), ('+1', 1, False), ('+5', 5, False))):
            br = QRectF(box_r.right() - (4 - bi) * 7.8 * u - 0.8 * u, y + 2.2 * u, 7.1 * u, 5.2 * u)
            w.capsule(p, br, qcol('#dc2626' if bi >= 2 else '#1e3440'), qcol('#ffffff', 0.35))
            w.text(p, lbl, br.x(), br.y(), ('d', 1.85, 700), qcol('#ffffff'), br.width(), 1, 5.2 / 1.85)
            w.hit(br, (lambda: self.set_val('combo', 0)) if rst else (lambda d=delta: self.bump_val('combo', d, 0, 999)), name=f'pk_cb:{lbl}')
        y += 11.0 * u

        moves = (
            ('Blubbsauger (Wasser · Azuria)', 'Stärke 90 · Heilt Evoli um 50 % des angerichteten Schadens!'),
            ('Bizzelturbo (Elektro · Orania)', 'Stärke 90 · 100 % Paralyse-Garantie auf den Gegner!'),
            ('Flackerbrand (Feuer · Prismania)', 'Stärke 90 · 100 % Verbrennungs-Garantie (halbiert Physisch)!'),
            ('glitzersturm (Fee) & Knisterladung (Unlicht)', 'Heilt alle Statusprobleme der Gruppe / legt Reflektor-Schild!'),
            ('5 Geheime Techniken', 'Spaltenschnitt (MS Anne) · Lichtflut · Himmelsritt · Kraftschub · Wellenspurt (Safari-Park)'),
        )
        rh = (H - y - 1.8 * u) / len(moves)
        for idx, (mname, mdesc) in enumerate(moves):
            ry = y + idx * rh
            r = QRectF(x0, ry, cw, rh - 0.45 * u)
            w.box(p, r, 0.75 * u, qcol('#112028'))
            w.text(p, mname, r.x() + 1.3 * u, r.y() + 0.55 * u, ('u', 1.62, 700), qcol('#fde68a'), cw * 0.41)
            w.text(p, mdesc, r.x() + cw * 0.42, r.y() + 0.55 * u, ('u', 1.48, 400), qcol('#e2e8f0'), cw * 0.56, 0, 1.25, 2)

    def _paint_gyms(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_g(top):
            cy = top
            rh = 6.4 * u
            for gid, gname, gtip in PK_GYMS:
                r = QRectF(x0, cy, cw, rh - 0.5 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(gid)
                    w.box(p, r, 0.8 * u, qcol('#132d24') if chk else qcol('#13232c'), qcol('#4ade80') if chk else qcol('#274352'))
                    w.text(p, f'{"◆" if chk else "◇"}  {gname}', r.x() + 1.3 * u, r.y() + 0.65 * u, ('u', 1.72, 700), qcol('#ffffff'), cw - 2.6 * u)
                    w.text(p, gtip, r.x() + 1.3 * u, r.y() + 3.3 * u, ('u', 1.46, 400), qcol('#cbd5e1'), cw - 2.6 * u)
                    w.hit(r, lambda k=gid: self.toggle_done(k), name=f'pk_gym:{gid}')
                cy += rh
            return cy

        w.scroller(p, 'pk_gyms', area, draw_g)


class SonicManiaDeck(CompanionBase):
    KEY = 'mania'
    TABS = ('Emeralds & Zonen', ' Helden & Tricks', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'mania')

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#0f1126'))

        # Signature Sonic Mania Yellow / Cyan / Magenta geometric chevrons!
        hdr = QRectF(0, 0, W, 11.0 * u)
        p.fillRect(hdr, qcol('#171a3b'))
        for ci, (col_h, x_off) in enumerate((('#facc15', 22.0), ('#06b6d4', 15.5), ('#ec4899', 9.0))):
            poly = QPolygonF([QPointF(W - x_off * u, 0), QPointF(W - (x_off - 5.2) * u, 0),
                              QPointF(W - (x_off + 1.8) * u, hdr.height()), QPointF(W - (x_off + 7.0) * u, hdr.height())])
            p.setPen(qcol('#000000', 0))
            p.setBrush(qcol(col_h, 0.85))
            p.drawPolygon(poly)

        em_n = sum(1 for i in range(7) if self.is_done(f'em_{i}'))
        w.text(p, 'STUDIOPOLIS-TACHO  ·  SONIC MANIA PLUS', 2.8 * u, 1.15 * u, ('d', 2.45, 700, .05), qcol('#facc15'), W * 0.7)
        w.text(p, f'Chaos Emeralds: {em_n} / 7  {"(SUPER SONIC BEREIT!)" if em_n == 7 else ""}', 2.8 * u, 4.05 * u, ('u', 1.55, 700), qcol('#67e8f9'), W * 0.7)

        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, 6.2 * u, tw - 0.6 * u, 4.1 * u)
            on = (i == self.tab)
            self.slant(p, r, 0.75 * u, qcol('#facc15') if on else qcol('#222652'), qcol('#ffffff') if on else qcol('#06b6d4', 0.6), 1.5 if on else 1.0)
            w.text(p, lbl.upper(), r.x() + 0.3 * u, r.y(), ('d', 1.85, 700, .04), qcol('#0f1126') if on else qcol('#f8fafc'), r.width(), 1, 4.1 / 1.85)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'sm_tab:{lbl}')

        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#0f1126')
            return True
        top = hdr.bottom() + 1.3 * u
        if self.tab == 0:
            self._paint_zones(p, top)
        else:
            self._paint_heroes(p, top)
        return True

    def _paint_zones(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        # 7 Interactive Chaos Emeralds bar
        em_cols = (('#22c55e', 'Grün'), ('#eab308', 'Gelb'), ('#3b82f6', 'Blau'), ('#ec4899', 'Pink'),
                   ('#e2e8f0', 'Weiß'), ('#06b6d4', 'Cyan'), ('#ef4444', 'Rot'))
        ew = cw / 7.0
        for i, (ec, elbl) in enumerate(em_cols):
            r = QRectF(x0 + i * ew + 0.25 * u, y, ew - 0.5 * u, 5.2 * u)
            got = self.is_done(f'em_{i}')
            self.chamfer_box(p, r, 0.7 * u, qcol(ec, 0.88 if got else 0.16), qcol('#ffffff') if got else qcol(ec), 1.5)
            w.text(p, f'◆ {elbl}' if got else f'◇ {elbl}', r.x(), r.y(), ('d', 1.65, 700),
                   qcol('#0f1126') if got else qcol('#e2e8f0'), r.width(), 1, 5.2 / 1.65)
            w.hit(r, lambda k=f'em_{i}': self.toggle_done(k), name=f'sm_em:{i}')
        y += 6.4 * u

        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_z(top):
            cy = top
            rh = 6.1 * u
            for zid, zname, zring in MANIA_ZONES:
                r = QRectF(x0, cy, cw, rh - 0.5 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(zid)
                    self.slant(p, r, 0.5 * u, qcol('#162e2a') if chk else qcol('#191d42'), qcol('#facc15') if chk else qcol('#313875'), 1.2)
                    w.text(p, f'{"✓" if chk else "◎"}  {zname}', r.x() + 1.3 * u, r.y() + 0.6 * u, ('d', 1.85, 700), qcol('#facc15' if chk else '#ffffff'), cw * 0.34)
                    w.text(p, zring, r.x() + cw * 0.35, r.y() + 0.6 * u, ('u', 1.5, 400), qcol('#cbd5e1'), cw * 0.63, 0, 1.3, 2)
                    w.hit(r, lambda k=zid: self.toggle_done(k), name=f'sm_z:{zid}')
                cy += rh
            return cy

        w.scroller(p, 'sm_zones', area, draw_z)

    def _paint_heroes(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        cards = (
            ('Sonic · Drop Dash', 'In der Luft Sprungtaste nochmals gedrückt halten -> startet beim Landen sofort als Spin-Dash!'),
            ('Mighty the Armadillo (Plus)', 'Sprungtaste in der Luft nach unten = Hammer-Drop (immun gegen Stacheln & öffnet versteckte Böden!)'),
            ('Ray the Flying Squirrel (Plus)', 'Wie Super Mario World Cape: nach dem Absprung zurücklehnen (◀), dann vorwärts stürzen (▶) um endlos zu fliegen!'),
            ('UFO-Spezialstage Trick', 'Erst Blaue Kugeln sammeln (Mach-Stufe 2 -> 3!), Ringe halten nur die Zeit oben – Kurven früh innen schneiden'),
            ('Super-Verwandlung (50+ Ringe)', 'Mit allen 7 Chaos Emeralds und 50 Ringen in der Luft Y / Oben drücken'),
        )
        rh = (H - y - 1.8 * u) / len(cards)
        for idx, (head, body) in enumerate(cards):
            ry = y + idx * rh
            r = QRectF(x0, ry, cw, rh - 0.5 * u)
            self.slant(p, r, 0.5 * u, qcol('#191d42'), qcol('#06b6d4' if idx % 2 == 0 else '#ec4899'), 1.3)
            w.text(p, head, r.x() + 1.4 * u, r.y() + 0.7 * u, ('d', 1.88, 700), qcol('#facc15'), cw - 2.8 * u)
            w.text(p, body, r.x() + 1.4 * u, r.y() + 3.4 * u, ('u', 1.5, 400), qcol('#f1f5f9'), cw - 2.8 * u, 0, 1.25, 2)


class FFResonanceDeck(CompanionBase):
    KEY = 'ffres'
    TABS = ('Resonanz & Taktik', 'Jagdbrett & Chronik', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'ffres')

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#070e1a'))

        hdr = QRectF(0, 0, W, 11.0 * u)
        g = QLinearGradient(0, 0, 0, hdr.height())
        g.setColorAt(0.0, qcol('#0f2342'))
        g.setColorAt(1.0, qcol('#081224'))
        p.fillRect(hdr, g)

        # Astral crystal vector spire
        cx, cy = 4.0 * u, 3.4 * u
        cryst = QPolygonF([QPointF(cx, cy - 2.3 * u), QPointF(cx + 1.1 * u, cy - 0.4 * u), QPointF(cx, cy + 2.3 * u), QPointF(cx - 1.1 * u, cy - 0.4 * u)])
        p.setPen(QPen(qcol('#e0f2fe'), 1.4))
        p.setBrush(qcol('#38bdf8'))
        p.drawPolygon(cryst)

        hunts_n = sum(1 for k, _ in FFR_HUNTS if self.is_done(k))
        chap = int(self.get_val('ffr_chap', 1) or 1)
        w.text(p, 'ÄTHER-CHRONIK  ·  FINAL FANTASY RESONANCE', 6.4 * u, 1.15 * u, ('s', 2.25, 700, .03), qcol('#f8fafc'), W * 0.65)
        w.text(p, f'Aktuelles Kapitel: {chap}  ·  Jagdbrett: {hunts_n}/{len(FFR_HUNTS)} erlegt', 6.4 * u, 4.05 * u, ('u', 1.55, 500), qcol('#7dd3fc'), W * 0.62)

        ch_r = QRectF(W - 22.0 * u, 1.15 * u, 19.4 * u, 4.2 * u)
        self.chamfer_box(p, ch_r, 0.55 * u, qcol('#0c1b33'), qcol('#d4af37'), 1.3)
        w.text(p, f'Kapitel {chap}  (− / +)', ch_r.x(), ch_r.y(), ('m', 1.52, 700), qcol('#fef08a'), ch_r.width(), 1, 4.2 / 1.52)
        w.hit(QRectF(ch_r.x(), ch_r.y(), ch_r.width() * 0.5, ch_r.height()), lambda: self.bump_val('ffr_chap', -1, 1, 18), name='ffr_ch_dn')
        w.hit(QRectF(ch_r.center().x(), ch_r.y(), ch_r.width() * 0.5, ch_r.height()), lambda: self.bump_val('ffr_chap', 1, 1, 18), name='ffr_ch_up')

        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, 6.2 * u, tw - 0.6 * u, 4.1 * u)
            on = (i == self.tab)
            self.chamfer_box(p, r, 0.55 * u, qcol('#1e3a5f') if on else qcol('#0c172b'),
                             qcol('#d4af37') if on else qcol('#23385c'), 1.5 if on else 1.0)
            w.text(p, lbl.upper(), r.x(), r.y(), ('d', 1.85, 700, .05), qcol('#fef08a') if on else qcol('#cbd5e1'), r.width(), 1, 4.1 / 1.85)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'ffr_tab:{lbl}')

        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#070e1a')
            return True
        top = hdr.bottom() + 1.3 * u
        if self.tab == 0:
            self._paint_tactics(p, top)
        else:
            self._paint_hunts(p, top)
        return True

    def _paint_tactics(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        # Live Quick-Command bar
        cmds = (
            ('HAUPTMENÜ [+]', 'PLUS', '#d4af37'),
            ('GEBIETSKARTE [−]', 'MINUS', '#38bdf8'),
            ('ZIEL-FOKUS [RS]', 'RS', '#60a5fa'),
            ('TAKTIK-WECHSEL [L]', 'L', '#a78bfa'),
        )
        bw = (cw - 2.4 * u) / 4.0
        for i, (lbl, seq, col_h) in enumerate(cmds):
            r = QRectF(x0 + i * (bw + 0.8 * u), y, bw, 6.4 * u)
            self.chamfer_box(p, r, 0.6 * u, qcol('#0e1d36'), qcol(col_h), 1.4)
            w.text(p, lbl, r.x(), r.y(), ('d', 1.75, 700), qcol('#f8fafc'), bw, 1, 6.4 / 1.75)
            w.hit(r, lambda seq=seq, lbl=lbl: self.send_pad(seq, lbl), name=f'ffr_cmd:{seq}')
        y += 7.8 * u

        rh = 7.4 * u
        for idx, (head, desc) in enumerate(FFR_TACTICS):
            ry = y + idx * rh
            r = QRectF(x0, ry, cw, rh - 0.55 * u)
            self.chamfer_box(p, r, 0.6 * u, qcol('#0c182d'), qcol('#d4af37', 0.55), 1.1)
            w.text(p, head, r.x() + 1.4 * u, r.y() + 0.75 * u, ('s', 1.85, 700), qcol('#fef08a'), cw - 2.8 * u)
            w.text(p, desc, r.x() + 1.4 * u, r.y() + 3.65 * u, ('u', 1.52, 400), qcol('#dbeafe'), cw - 2.8 * u)
        es_y = y + len(FFR_TACTICS) * rh + 0.6 * u
        if H - es_y >= 5.5 * u:
            er = QRectF(x0, es_y, cw, H - es_y - 1.8 * u)
            self.chamfer_box(p, er, 0.7 * u, qcol('#0e1d36'), qcol('#38bdf8'), 1.3)
            w.text(p, 'ESPER-RESONANZ  ·  IFRITS FLAMME · SHIVAS FROST · RAMUHS URTEIL · BAHAMUTS FLARE',
                   er.x() + 1.4 * u, er.y() + 0.9 * u, ('d', 1.82, 700, .04), qcol('#7dd3fc'), cw - 2.8 * u)
            w.text(p, 'Esper-Beschwörung friert den Stagger-Zerfall für 8 Sek. ein – ideal unmittelbar nach dem Äther-Bruch!',
                   er.x() + 1.4 * u, er.y() + 3.7 * u, ('u', 1.52, 400), qcol('#e2e8f0'), cw - 2.8 * u)

    def _paint_hunts(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        area = QRectF(x0, y, cw, H - y - 1.8 * u)

        def draw_h(top):
            cy = top
            rh = 5.8 * u
            for hid, hlbl in FFR_HUNTS:
                r = QRectF(x0, cy, cw, rh - 0.5 * u)
                if r.bottom() >= area.top() and r.top() <= area.bottom():
                    chk = self.is_done(hid)
                    self.chamfer_box(p, r, 0.55 * u, qcol('#0f2924') if chk else qcol('#0c182d'),
                                     qcol('#34d399') if chk else qcol('#27416b'), 1.2)
                    self.txt_mid(p, f'{"◆" if chk else "◇"}  {hlbl}', QRectF(r.x() + 1.4 * u, r.y(), cw - 2.8 * u, r.height()),
                                 ('u', 1.7, 600), qcol('#a7f3d0') if chk else qcol('#f1f5f9'), 0)
                    w.hit(r, lambda k=hid: self.toggle_done(k), name=f'ffr_h:{hid}')
                cy += rh
            return cy

        w.scroller(p, 'ffr_hunts', area, draw_h)


class TomodachiDeck(CompanionBase):
    KEY = 'tomodachi'
    TABS = ('Persönlichkeiten', 'Insel-Tagesplan', 'Werkzeuge')

    def __init__(self, w):
        super().__init__(w, 'tomodachi')

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol('#0c2126'))

        hdr = QRectF(0, 0, W, 11.0 * u)
        g = QLinearGradient(0, 0, W, hdr.height())
        g.setColorAt(0.0, qcol('#0f766e'))
        g.setColorAt(1.0, qcol('#155e75'))
        p.fillRect(hdr, g)

        miis = int(self.get_val('mii_count', 1) or 1)
        w.text(p, 'INSEL-RATHAUSBUCH  ·  TOMODACHI LIFE', 2.8 * u, 1.15 * u, ('d', 2.4, 700, .04), qcol('#fef3c7'), W * 0.68)
        w.text(p, f'Eingezogene Inselbewohner: {miis} Miis', 2.8 * u, 4.05 * u, ('u', 1.58, 600), qcol('#a7f3d0'), W * 0.6)

        mc_r = QRectF(W - 21.5 * u, 1.15 * u, 18.8 * u, 4.2 * u)
        w.capsule(p, mc_r, qcol('#0c2126'), qcol('#fde68a'))
        w.text(p, f'Bewohner: {miis}  (−/+)', mc_r.x(), mc_r.y(), ('m', 1.5, 700), qcol('#fef3c7'), mc_r.width(), 1, 4.2 / 1.5)
        w.hit(QRectF(mc_r.x(), mc_r.y(), mc_r.width() * 0.5, mc_r.height()), lambda: self.bump_val('mii_count', -1, 1, 100), name='tl_m_dn')
        w.hit(QRectF(mc_r.center().x(), mc_r.y(), mc_r.width() * 0.5, mc_r.height()), lambda: self.bump_val('mii_count', 1, 1, 100), name='tl_m_up')

        tx0, tcw = 2.6 * u, W - 5.2 * u
        tw = tcw / len(self.TABS)
        for i, lbl in enumerate(self.TABS):
            r = QRectF(tx0 + i * tw + 0.3 * u, 6.2 * u, tw - 0.6 * u, 4.1 * u)
            on = (i == self.tab)
            w.capsule(p, r, qcol('#fde68a') if on else qcol('#0c2c33'), qcol('#fb7185') if on else qcol('#2dd4bf', 0.5))
            w.text(p, lbl.upper(), r.x(), r.y(), ('d', 1.85, 700, .04), qcol('#0c2126') if on else qcol('#ecfeff'), r.width(), 1, 4.1 / 1.85)
            w.hit(r, lambda i=i: self.set_tab(i), name=f'tl_tab:{lbl}')

        if self.is_tools_tab():
            self.paint_tools_embedded(p, hdr.bottom(), '#0c2126')
            return True
        top = hdr.bottom() + 1.3 * u
        if self.tab == 0:
            self._paint_compass(p, top)
        else:
            self._paint_schedule(p, top)
        return True

    def _paint_compass(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u

        # 4 Interactive Trait Axes (1..8) -> maps onto the Tomodachi Personality Compass!
        axes = (
            ('tl_move', 'BEWEGUNG', 'Gemütlich', 'Flink'),
            ('tl_talk', 'SPRACHE', 'Höflich', 'Direkt'),
            ('tl_expr', 'AUSDRUCK', 'Dezent', 'Lebhaft'),
            ('tl_mind', 'DENKWEISE', 'Verträumt', 'Rational'),
        )
        for idx, (ak, aname, left_l, right_l) in enumerate(axes):
            val = int(self.get_val(ak, 4) or 4)
            ry = y + idx * 5.6 * u
            r = QRectF(x0, ry, cw, 5.0 * u)
            w.box(p, r, 0.9 * u, qcol('#112f36'), qcol('#2dd4bf', 0.45))
            w.text(p, aname, r.x() + 1.3 * u, ry, ('d', 1.75, 700), qcol('#fde68a'), 14.0 * u, 0, 5.0 / 1.75)
            w.text(p, left_l, r.x() + 15.5 * u, ry, ('u', 1.48, 500), qcol('#99f6e4'), 11.0 * u, 2, 5.0 / 1.48)
            seg_x = r.x() + 27.5 * u
            seg_w = (cw - 41.5 * u) / 8.0
            for s in range(1, 9):
                sr = QRectF(seg_x + (s - 1) * seg_w + 0.18 * u, ry + 0.85 * u, seg_w - 0.36 * u, 3.3 * u)
                on = (s == val)
                w.capsule(p, sr, qcol('#fb7185' if on else ('#2dd4bf' if s < val else '#19414a')), qcol('#ffffff') if on else None)
                w.text(p, str(s), sr.x(), sr.y(), ('m', 1.45, 700), qcol('#ffffff'), sr.width(), 1, 3.3 / 1.45)
                w.hit(sr, lambda ak=ak, s=s: self.set_val(ak, s), name=f'tl_ax:{ak}:{s}')
            w.text(p, right_l, r.right() - 12.8 * u, ry, ('u', 1.48, 500), qcol('#fda4af'), 11.5 * u, 0, 5.0 / 1.48)

        y += 4 * 5.6 * u + 1.2 * u
        energy = int(self.get_val('tl_move', 4)) + int(self.get_val('tl_expr', 4))
        talk_direct = int(self.get_val('tl_talk', 4))
        rational = 1 if int(self.get_val('tl_mind', 4)) >= 5 else 0
        group_i = 0 if (energy <= 8 and talk_direct <= 4) else (1 if energy <= 8 else (2 if talk_direct <= 5 else 3))
        ptitle, pdesc = TL_GRID[(group_i, rational)]

        res_r = QRectF(x0, y, cw, 9.6 * u)
        w.box(p, res_r, 1.2 * u, qcol('#143840'), qcol('#fb7185'))
        w.text(p, f'ERGEBNIS-PROFIL:  {ptitle.upper()}', res_r.x() + 1.8 * u, res_r.y() + 1.3 * u, ('d', 2.2, 700, .04), qcol('#fef3c7'), cw - 3.6 * u)
        w.text(p, pdesc, res_r.x() + 1.8 * u, res_r.y() + 4.8 * u, ('u', 1.65, 500), qcol('#ecfeff'), cw - 3.6 * u)

        gy = res_r.bottom() + 1.2 * u
        if H - gy >= 7.0 * u:
            gifts = (
                ('Stufen-Aufstieg Geschenk', 'Lieder, Inneneinrichtung, Taschengeld oder Reise-Gutschein (beruhigt jeden Streit sofort!)'),
                ('Lieblingsessen finden', 'Reaktion „Super-Lecker!“ füllt die Zufriedenheit massiv & gibt Gold-/Silber-Bauch-Bonus'),
                ('Wunschblasen-Farben', 'Orange = Freundschaft / Liebe  ·  Grün = Hunger / Spiel  ·  Blau = Sorge / Streit schlichten!'),
            )
            gh = (H - gy - 1.8 * u) / len(gifts)
            for gi, (gt, gd) in enumerate(gifts):
                gr = QRectF(x0, gy + gi * gh, cw, gh - 0.45 * u)
                w.box(p, gr, 0.8 * u, qcol('#102b31'), qcol('#245561'))
                self.txt_mid(p, gt, QRectF(gr.x() + 1.3 * u, gr.y(), cw * 0.31, gr.height()), ('u', 1.6, 700), qcol('#fde68a'), 0)
                self.txt_mid(p, gd, QRectF(gr.x() + cw * 0.33, gr.y(), cw * 0.65, gr.height()), ('u', 1.48, 400), qcol('#ecfeff'), 0)

    def _paint_schedule(self, p, y):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        x0, cw = 2.6 * u, W - 5.2 * u
        rh = (H - y - 1.8 * u) / len(TL_EVENTS)
        for idx, (eid, etime, edesc) in enumerate(TL_EVENTS):
            ry = y + idx * rh
            r = QRectF(x0, ry, cw, rh - 0.5 * u)
            chk = self.is_done(eid)
            w.box(p, r, 0.85 * u, qcol('#133d36') if chk else qcol('#112f36'), qcol('#34d399') if chk else qcol('#245561'))
            w.text(p, f'{"✓" if chk else "☀"}  {etime}', r.x() + 1.3 * u, r.y() + 0.55 * u, ('u', 1.68, 700), qcol('#fde68a'), cw * 0.42)
            w.text(p, edesc, r.x() + cw * 0.43, r.y() + 0.55 * u, ('u', 1.5, 400), qcol('#ecfeff'), cw * 0.55, 0, 1.25, 2)
            w.hit(r, lambda k=eid: self.toggle_done(k), name=f'tl_ev:{eid}')


def Deck(w):
    comp = (w.RUN or {}).get('companion')
    if comp == 'mania':
        return SonicManiaDeck(w)
    if comp == 'ffres':
        return FFResonanceDeck(w)
    if comp == 'tomodachi':
        return TomodachiDeck(w)
    return LetsGoDeck(w)
