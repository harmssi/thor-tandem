"""Bespoke Classic, Steam & Retro Companions on the AYN Thor bottom OLED screen:
1. WoW Forever ('wow'): Azeroth Guild & Dungeon Tome (classes, WotLK 1-80 dungeon path, quick chat/macro buttons)
2. Super Mario Sunshine ('sunshine'): Delfino Shine Sprite & Blue Coin Tracker (7 worlds + FLUDD tech)
3. Luigi's Mansion ('luigis_mansion'): Game Boy Horror Mansion Radar (4 areas, 50 Boos, portrait ghosts, rank)
4. Paper Mario: The Thousand-Year Door ('ttyd'): Rogueport Star-Map & Badge/Recipe Book (8 chapters, partners)
5. Mario Kart: Double Dash!! ('mkdd'): Team Grand Prix Board (cups, special items, shortcuts)
6. Super Smash Bros. Melee ('melee'): Challenger Unlock Board & Advanced Tech Lab (Wavedash, L-Cancel, SHFFL)
7. Animal Crossing ('ac_gc'): Town Almanac (seasonal fish/bugs, house loan & Nook shop milestones)
8. Crash Bandicoot: The Wrath of Cortex ('crash_woc'): 5 Warp Rooms, Crystals/Gems/Relics & Elemental Powers."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QLinearGradient
from decks.native_base import CompanionBase, qcol

# ---- 1. WoW Forever (WotLK 3.3.5a) ----------------------------------------------------------------------------------
WOW_DUNGEONS = (
    ('wow_d1', '15–26 · Todesminen & Verlies', 'Westfall / Sturmwind · Erste blaue Ausrüstung & Quests'),
    ('wow_d2', '28–42 · Scharlachrotes Kloster', 'Friedhof, Bibliothek, Waffenkammer, Kathedrale (Top XP!)'),
    ('wow_d3', '44–52 · Zul’Farrak & Maraudon', 'Tanaris / Desolace · Treppe in ZF + Quest-Ketten'),
    ('wow_d4', '53–60 · Schwarzfelstiefen & Stratholme', 'Klassik-Endgame · Übergang zum Dunklen Portal (Lvl 58)'),
    ('wow_d5', '60–70 · Scherbenwelt (Höllenfeuer -> Terrasse)', 'Bollwerk, Blutkessel, Sklavenunterkünfte, Sethekkhallen'),
    ('wow_d6', '70–80 · Nordend (Burg Utgarde -> Seelenschmiede)', 'Nexus, Azjol-Nerub, Gundrak, Hallen des Steins, Grube von Saron'),
    ('wow_d7', '80 · Heroics, Naxxramas, Ulduar, PDK & ICC', 'Embleme des Frosts sammeln -> T9/T10 Set-Boni freischalten'),
)

WOW_DAILY = (
    ('wow_q1', 'Zufälliger Heroic-Dungeon (Tagesbonus)', '2× Emblem des Frosts + Gold über Dungeonbrowser (I)'),
    ('wow_q2', 'Wöchentliche Raid-Quest (Dalaran)', '5× Emblem des Frosts · Erzmagier Lan’dalock vor der Violetten Festung'),
    ('wow_q3', 'Tägliche Berufe / Koch- & Angelquest', 'Dalaran-Kochmarken & Juwelierssymbol für epische Sockel'),
    ('wow_q4', 'Tausendwinter-Schlacht (PvP / Archavons Kammer)', 'Ehre + Chance auf T10-Hände/Beine im 10er & 25er Raid'),
    ('wow_q5', 'Reitkunst & Kaltwetterflug (Lvl 77)', 'Dalaran-Flugplatz · Fliegen in Nordend für schnelles Questen'),
    ('wow_q6', 'Duale Talentspezialisierung (1000 Gold)', 'Klassenlehrer · Blitzschnell zwischen Schaden / Heiler / Tank wechseln'),
)

WOW_MACROS = (
    ('/reload', 'UI neu laden (wenn Addons hängen)', '/reload'),
    ('/who', 'Spieler in der Zone anzeigen', '/who'),
    ('/played', 'Gesamtspielzeit anzeigen', '/played'),
    ('/dance', 'Emote: Tanzen', '/dance'),
)

# ---- 2. Super Mario Sunshine ----------------------------------------------------------------------------------------
SUNSHINE_WORLDS = (
    ('sms_plaza', 'Piazza Delfino (Insel-Hub)', '16 Insignien · 20 Blaue Münzen (inkl. 240-Münzen-Tausch im Bootshaus)'),
    ('sms_bianco', 'Monte Bianco', '8 Episoden + 2 Geheim-Insignien + 100-Münzen · 30 Blaue Münzen'),
    ('sms_ricco', 'Porto d’Oro', '8 Episoden + Blooper-Surfen + 100-Münzen · 30 Blaue Münzen'),
    ('sms_gelato', 'Lido Ridente', '8 Episoden + Sandvogel + 100-Münzen · 30 Blaue Münzen'),
    ('sms_pinna', 'Parco Fortuna', '8 Episoden + Mecha-Bowser + Achterbahn · 30 Blaue Münzen'),
    ('sms_sirena', 'Baia Paradiso (Hotel Delfino)', '8 Episoden + Buu Huu-Kasino + 100-Münzen · 30 Blaue Münzen'),
    ('sms_noki', 'Baia dei Noki', '8 Episoden + Zahnarzt-Aal + Muschelturm · 30 Blaue Münzen'),
    ('sms_pianta', 'Villaggio Palma', '8 Episoden + Kettenhund-Bad + 100-Münzen · 30 Blaue Münzen'),
    ('sms_corona', 'Monte Corona (Finale)', 'Boot-Steuerung sanft mit Düse korrigieren -> Bowser & Bowser Jr.'),
)

SUNSHINE_TECH = (
    ('Wirbelsprung (Spin Jump)', 'Stick im Kreis drehen + A -> deutlich höher als der normale Sprung'),
    ('Bauchplatscher-Rutsch', 'Während Laufen kurz B (oder erst spritzen + B) -> extrem schnelles Rutschen'),
    ('Schwebdüsen-Reset', 'Nach Wandsprung oder Bodenkontakt lädt die Schwebdüse sofort wieder voll auf'),
    ('Turbo- & Raketendüse', 'Auf Piazza Delfino nach 25 bzw. 30 Insignien freigeschaltet'),
)

# ---- 3. Luigi's Mansion ---------------------------------------------------------------------------------------------
LM_AREAS = (
    ('lm_a1', 'Bereich 1 · Erdgeschoss & Foyer', 'Chauncey (Baby) besiegen -> Schlüssel für Bereich 2 (5 Buu Huus ab B2)'),
    ('lm_a2', 'Bereich 2 · Küche, Bad & Ballsaal', 'Bogmire (Friedhof) · Schattenkugeln einsaugen und auf ihn schießen!'),
    ('lm_a3', 'Bereich 3 · Hof, Wintergarten & Stromausfall', 'Boolossus (15 Buu Huus) mit Eis-Medaille auf Einhorn-Statue platzen lassen'),
    ('lm_a4', 'Bereich 4 · Dachboden & Dach (Finale)', 'König Buu Huu / Bowser · Stachelkugeln gegen den Kopf saugen & feuern'),
    ('lm_med1', 'Feuer-Medaille (Spiegelzimmer)', 'Kerzen entzünden & Eisgeister / Schneebälle schmelzen'),
    ('lm_med2', 'Wasser-Medaille (Küche)', 'Pflanzen gießen (Garten-Herz!) & Feuergeister löschen'),
    ('lm_med3', 'Eis-Medaille (Teezimmer)', 'Flammen einfrieren & Boolossus einfrieren'),
)

LM_GHOSTS = (
    ('Neville & Lydia', 'Warten bis Neville gähnt (Herz zeigen) · bei Lydia erst Vorhang aufsaugen'),
    ('Melody (Klavier)', 'Instrumente berühren, Mario-Quiz beantworten -> Notenblätter einsaugen'),
    ('Madame Clairvoya', 'Alle 5 Mario-Gegenstände bringen (Mütze, Handschuh, Schuh, Brief, Stern)'),
    ('Geld-Ränge', 'Rang A: 100 Mio. G · Rang B: 70 Mio. · Rang C: 60 Mio. (Goldmäuse & Edelsteine!)'),
)

# ---- 4. Paper Mario: The Thousand-Year Door -------------------------------------------------------------------------
TTYD_CHAPTERS = (
    ('ttyd_c1', 'Kap. 1 · Blütenweiler & Lohgards Burg', 'Diamantstern · Partner: Gumbrina & Koops · Frosch-Orden gegen Lohgard!'),
    ('ttyd_c2', 'Kap. 2 · Wunderwald & Großer Baum', 'Smaragdstern · Partner: Aerona · 101 Bubus durch den Baum führen'),
    ('ttyd_c3', 'Kap. 3 · Falkenheim (Arena)', 'Goldstern · Partner: Mini-Yoshi · Von Liga 20 bis Champion Aurum'),
    ('ttyd_c4', 'Kap. 4 · Düsterdorf & Spukabtei', 'Rubinstern · Partner: Barbara · Versteckter Name: Rumpel („p“ finden!)'),
    ('ttyd_c5', 'Kap. 5 · Isla Corsaria & Piratengrotte', 'Saphirstern · Partner: Bart-omb · Cortez in 3 Phasen besiegen'),
    ('ttyd_c6', 'Kap. 6 · Glimmer-Liner (Zug)', 'Granatstern · Detektiv-Rätsel an 3 Tagen -> Bahnhof Großfrostheim'),
    ('ttyd_c7', 'Kap. 7 · Großfrostheim & Mondbasis', 'Kristallstern · Basis-Code & General Bumm-Bumm -> Crucius'),
    ('ttyd_c8', 'Kap. 8 · Äonenpalast & Königin der Finsternis', 'Duell-Vorbereitung: Lebenskraft-Pilze, Kraft-Plus & Power-Sprung'),
)

TTYD_RECIPES = (
    ('Gelee-Ultra (50 KP + 50 BP)', 'Ultra-Pilz + Gelee-Bonbon (Zess T. nach Kontaktlinse + Kochbuch)'),
    ('Pilz-Crêpe (30 KP + 20 BP)', 'Ultra-Pilz + Kuchen-Mix -> günstig & stark für den Endkampf'),
    ('Power-Kombo (Orden)', 'Kraft-Plus + Kraft-Sprung + Multibounce + Fix-Wechsel (Partner sofort!)'),
    ('Duellkerker (100 Ebenen)', 'Etage 50: Großer Beutel (20 Items) · Etage 100: Knochen-Lohgard'),
)

# ---- 5. Mario Kart: Double Dash!! -----------------------------------------------------------------------------------
MKDD_CUPS = (
    ('mkdd_mush', 'Pilz-Cup (4 Strecken)', 'Luigis Piste · Peach Beach · Baby-Park · Staubtrockene Wüste'),
    ('mkdd_flow', 'Blumen-Cup (4 Strecken)', 'Pilz-Brücke · Marios Piste · Daisy-Dampfer · Waluigi-Arena'),
    ('mkdd_star', 'Stern-Cup (4 Strecken)', 'Sorbet-Land · Pilz-City · Yoshis Piste · DK Bergland'),
    ('mkdd_spec', 'Spezial-Cup (4 Strecken)', 'Wario-Kolosseum · Dino Dino-Dschungel · Bowsers Festung · Regenbogen-Boulevard'),
    ('mkdd_all', 'Meisterschafts-Tour (16 Strecken)', 'Alle 16 Kurse am Stück -> schaltet Spiegel-Modus & Gold-Kart frei!'),
)

MKDD_TIPS = (
    ('Doppel-Drift (Snaking)', 'R halten + Stick schnell links/rechts -> blaue Funken = Mini-Turbo'),
    ('Raketenstart (Doppel-Turbo)', 'A genau bei „LOS!“ drücken (beide Fahrer jubeln -> max. Boost)'),
    ('Beste Spezial-Items', 'Bowser Jr. (Riesenpanzer) + Diddy Kong (Riesenbanane) oder Koopa (3× Panzer)'),
    ('Charakter-Wechsel (Z)', 'Z wechselt Fahrer & lagert ein Item sicher für die nächste Box'),
)

# ---- 6. Super Smash Bros. Melee -------------------------------------------------------------------------------------
MELEE_UNLOCKS = (
    ('ssbm_puff', 'Pummeluff', 'Classic- oder Adventure-Modus 1× auf beliebigem Grad beenden'),
    ('ssbm_doc', 'Dr. Mario', 'Classic-Modus mit Mario ohne Continue beenden'),
    ('ssbm_falco', 'Falco', '100-Man Melee bestehen'),
    ('ssbm_pichu', 'Pichu', 'Event-Match #37 (Legendäre Pokémon) schaffen'),
    ('ssbm_marth', 'Marth', 'Mit allen 14 Start-Charakteren mindestens 1 VS-Match spielen'),
    ('ssbm_ylink', 'Junger Link', 'Classic-Modus mit 10 verschiedenen Charakteren abschließen'),
    ('ssbm_ganon', 'Ganondorf', 'Event-Match #29 (Triforce-Treffen) gewinnen'),
    ('ssbm_mewtwo', 'Mewtu', '20 Stunden kumulierte VS-Zeit (4 Spieler = 5 Std.) oder 700 VS-Matches'),
    ('ssbm_luigi', 'Luigi', 'Adventure-Modus Stage 1 mit einer „2“ in der Sekunden-Endziffer beenden'),
    ('ssbm_roy', 'Roy', 'Classic-Modus mit Marth ohne Continue beenden'),
    ('ssbm_gw', 'Mr. Game & Watch', 'Classic, Adventure oder Target-Test mit allen anderen 24 Kämpfern schaffen'),
)

MELEE_TECH = (
    ('Wavedash', 'Sprung (X/Y) -> sofort L/R + Stick schräg nach unten-links/-rechts'),
    ('L-Cancel', 'Kurz vor dem Landen nach Luftangriff L/R/Z antippen -> halbe Landeverzögerung!'),
    ('SHFFL', 'Short Hop -> Luftangriff -> Fast Fall (Stick runter) -> L-Cancel'),
    ('DI (Survival)', 'Bei starkem Treffer Stick senkrecht zur Flugrichtung halten -> länger überleben'),
)

# ---- 7. Animal Crossing (GameCube) ----------------------------------------------------------------------------------
AC_MILESTONES = (
    ('ac_h1', 'Start-Job & 1. Kredit (19.800 Sternis)', 'Tom Nooks Aufgaben erledigen -> eigenes Haus schuldenfrei'),
    ('ac_h2', 'Haus-Erweiterung I (148.000 Sternis)', 'Größeres Erdgeschoss bei Tom Nook'),
    ('ac_h3', 'Keller-Ausbau (49.800 Sternis)', 'Perfekt für Rüben-Lagerung & seltene Möbel (zählt nicht zur AdH)'),
    ('ac_h4', 'Obergeschoss (798.000 Sternis)', 'Komplettes 2-Etagen-Haus -> goldene Statue am Bahnhof!'),
    ('ac_nook', 'Nooks Laden -> HyperNook', '240.000 Sternis Umsatz + 1 Besucher-Kauf schaltet HyperNook frei'),
    ('ac_mus', 'Museum (Fossilien, Fische, Insekten, Kunst)', 'Fossilien per Brief ans Fernmuseum senden -> 1 Tag später bestimmen'),
)

AC_TIPS = (
    ('Geld-Stein (täglich)', 'Jeden Tag spuckt 1 Stein bei schnellem Schaufel-Klopfen bis zu 4.100 Sternis aus'),
    ('Sonntag: Rübenhandel', 'Sigrid verkauft morgens bis 12:00 Uhr · Nook kauft Mo–Sa (höchster Kurs Do/Fr)'),
    ('Seltene Fische (15.000 ★)', 'Quastenflosser (Regen/Schnee abends am Meer) · Flussbarsch-Schatten beachten'),
    ('Goldene Werkzeuge', 'Goldschaufel: Schaufel im Leuchtloch vergraben · Goldaxt: 15 Tage perfekte Stadt'),
)

# ---- 8. Crash Bandicoot: The Wrath of Cortex (PS2) ------------------------------------------------------------------
CRASH_ROOMS = (
    ('cb_w1', 'Warp-Raum 1 (Level 1–5 + Crunch/Erde)', 'Arktis-Wahn, Tornado-Gasse, Bambus-Pfad, Zauberwald, Absturz -> Fels-Boss'),
    ('cb_w2', 'Warp-Raum 2 (Level 6–10 + Crunch/Wasser)', 'Tsunami, Smokey & der Bandit, Eskimo-Roll, Korallenriff, H2 Oh No -> Wasser-Boss'),
    ('cb_w3', 'Warp-Raum 3 (Level 11–15 + Crunch/Feuer)', 'Zauber-Chaos, Banzai Bonsai, Lava-Höhle, Feuerwerk-Fabrik, Dschungel-Rumble -> Feuer-Boss'),
    ('cb_w4', 'Warp-Raum 4 (Level 16–20 + Crunch/Wind)', 'Atmosphären-Flug, Goldrausch, Mittelalter-Wahnsinn, Kisten-Kugeln, Eis-Station -> Wind-Boss'),
    ('cb_w5', 'Warp-Raum 5 (Level 21–25 + Cortex-Finale)', 'Solar-Express, Blitzschlag, Geisterstadt, Schmelzofen, Crunch-Time (Finale)'),
    ('cb_rel', 'Bonus-Warp-Raum (5–25 Relikte)', 'Jede 5 Relikte öffnen ein Geheim-Level (5, 10, 15, 20, 25 Relikte)'),
)

CRASH_POWERS = (
    ('Schleich-Schuhe (Raum 1)', 'Ermöglicht das Laufen über Nitro-Kisten ohne Explosion'),
    ('Doppelsprung (Raum 2)', 'Zweiter Sprung in der Luft -> Pflicht für viele Kisten-Edelsteine'),
    ('Todes-Tornado-Wirbel (Raum 3)', 'Wirbeln gedrückt halten -> über große Abgründe gleiten'),
    ('Wumpa-Bazooka (Raum 4)', 'Kisten & Gegner aus sicherer Entfernung abschießen'),
    ('Sprint-Schuhe (Raum 5)', 'R2 halten zum Rennen -> essenziell für Gold- & Platin-Relikte'),
)


# ---- Shared Compact Styled Deck Engine ------------------------------------------------------------------------------
class _StyledGuideDeck(CompanionBase):
    """Reusable high-craft 2–3 tab themed companion with interactive checklists, counters, and optional quick actions."""
    BG = '#0d1018'
    ACCENT = '#ff8c1a'
    ACCENT2 = '#38bdf8'
    TITLE = 'Begleiter'
    SUBTITLE = ''
    TABS = ('Fortschritt', 'Tipps', 'Werkzeuge')
    CHECKLIST = ()          # ((id, title, desc), ...)
    SECONDARY = ()          # ((id, title, desc), ...) or ((title, desc), ...)
    SECONDARY_CHECK = False
    COUNTER = None          # (state_key, label, max_val) or None
    QUICK_BTNS = ()         # ((label, desc, cmd_text), ...)

    def __init__(self, w):
        super().__init__(w, self.KEY)

    def _draw_header(self, p, W, u):
        w = self.w
        hh = 6.2 * u
        g = QLinearGradient(0, 0, W, hh)
        g.setColorAt(0, qcol(self.ACCENT, 0.24))
        g.setColorAt(1, qcol(self.BG, 0.96))
        p.fillRect(QRectF(0, 0, W, hh), QBrush(g))
        p.fillRect(QRectF(0, hh - 0.14 * u, W, 0.14 * u), qcol(self.ACCENT, 0.55))
        w.text(p, self.TITLE, 2.6 * u, 0.9 * u, ('u', 2.2, 700, -0.01), qcol('#f8fafc'), W * 0.42)
        if self.SUBTITLE:
            w.text(p, self.SUBTITLE, 2.6 * u, 3.55 * u, ('u', 1.38, 500), qcol(self.ACCENT), W * 0.42)
        # Tabs on right
        tw_tot = W * 0.52
        tx0 = W - tw_tot - 2.4 * u
        gap = 0.8 * u
        tw = (tw_tot - gap * (len(self.TABS) - 1)) / len(self.TABS)
        for idx, lbl in enumerate(self.TABS):
            on = self.tab == idx
            tr = QRectF(tx0 + idx * (tw + gap), 1.1 * u, tw, 4.0 * u)
            w.box(p, tr, 1.1 * u, qcol(self.ACCENT) if on else qcol('#1b2030'), None if on else qcol(self.ACCENT, 0.28))
            w.text(p, lbl, tr.x(), tr.y(), ('u', 1.62, 700 if on else 500),
                   qcol('#090b10') if on else qcol('#e2e8f0'), tr.width(), 1, tr.height() / (1.62 * u))
            w.hit(tr, lambda i=idx: self.set_tab(i), name=f'{self.KEY}:tab:{idx}')
        return hh + 1.4 * u

    def _draw_checklist(self, p, items, y, x0, cw, u):
        w = self.w
        done_n = sum(1 for k, _, _ in items if self.is_done(k))
        # Summary pill
        sr = QRectF(x0, y, cw, 4.4 * u)
        w.box(p, sr, 1.2 * u, qcol('#151a26'), qcol(self.ACCENT, 0.35))
        pct = int(round(100 * done_n / max(1, len(items))))
        w.text(p, f'Fortschritt: {done_n} / {len(items)} ({pct} %)', x0 + 1.6 * u, y, ('u', 1.75, 700),
               qcol(self.ACCENT), cw * 0.6, 0, 4.4 / 1.75)
        bar_w = cw * 0.34
        bar_x = x0 + cw - bar_w - 1.6 * u
        w.box(p, QRectF(bar_x, y + 1.6 * u, bar_w, 1.2 * u), 0.6 * u, qcol('#0b0e15'))
        if pct:
            w.box(p, QRectF(bar_x, y + 1.6 * u, max(1.2 * u, bar_w * pct / 100), 1.2 * u), 0.6 * u, qcol(self.ACCENT))
        y += 5.4 * u

        if self.COUNTER:
            ckey, clbl, cmax = self.COUNTER
            cval = int(self.get_val(ckey, 0) or 0)
            cr = QRectF(x0, y, cw, 5.2 * u)
            w.box(p, cr, 1.2 * u, qcol('#141925'), qcol(self.ACCENT2, 0.4))
            w.text(p, f'{clbl}: {cval} / {cmax}', x0 + 1.6 * u, y, ('u', 1.8, 700), qcol(self.ACCENT2), cw * 0.56, 0, 5.2 / 1.8)
            for idx, (lbl, delta) in enumerate((('−5', -5), ('−1', -1), ('+1', 1), ('+5', 5))):
                bw = 6.2 * u
                bx = x0 + cw - 1.4 * u - (4 - idx) * (bw + 0.7 * u) + 0.7 * u
                br = QRectF(bx, y + 0.7 * u, bw, 3.8 * u)
                w.box(p, br, 0.9 * u, qcol(self.ACCENT2, 0.22) if delta > 0 else qcol('#1f2636'), qcol(self.ACCENT2, 0.45))
                w.text(p, lbl, br.x(), br.y(), ('u', 1.65, 700), qcol('#f8fafc'), bw, 1, 3.8 / 1.65)
                w.hit(br, lambda d=delta, k=ckey, m=cmax: self.bump_val(k, d, 0, m), name=f'{self.KEY}:cnt:{lbl}')
            y += 6.2 * u

        for cid, title, desc in items:
            on = self.is_done(cid)
            rh = 6.6 * u
            rr = QRectF(x0, y, cw, rh)
            w.box(p, rr, 1.3 * u, qcol(self.ACCENT, 0.14) if on else qcol('#151924'),
                  qcol(self.ACCENT, 0.65) if on else qcol('#272d3d'))
            chk = QRectF(x0 + 1.4 * u, y + 1.8 * u, 3.0 * u, 3.0 * u)
            w.box(p, chk, 0.8 * u, qcol(self.ACCENT) if on else qcol('#0b0e15'), qcol(self.ACCENT, 0.7))
            if on:
                w.text(p, '✓', chk.x(), chk.y(), ('u', 2.0, 800), qcol('#090b10'), chk.width(), 1, chk.height() / (2.0 * u))
            w.text(p, title, x0 + 5.8 * u, y + 0.9 * u, ('u', 1.82, 700), qcol('#f8fafc' if not on else self.ACCENT), cw - 7.4 * u)
            w.text(p, desc, x0 + 5.8 * u, y + 3.6 * u, ('u', 1.45, 400), qcol('#9ca3af'), cw - 7.4 * u)
            w.hit(rr, lambda k=cid: self.toggle_done(k), name=f'{self.KEY}:{cid}')
            y += rh + 1.0 * u
        return y

    def _draw_tips(self, p, y, x0, cw, u):
        w = self.w
        if self.QUICK_BTNS:
            gap = 1.0 * u
            bw = (cw - gap * (len(self.QUICK_BTNS) - 1)) / len(self.QUICK_BTNS)
            for idx, (lbl, desc, cmd) in enumerate(self.QUICK_BTNS):
                br = QRectF(x0 + idx * (bw + gap), y, bw, 5.4 * u)
                w.box(p, br, 1.2 * u, qcol(self.ACCENT, 0.2), qcol(self.ACCENT, 0.6))
                w.text(p, lbl, br.x(), br.y() + 0.6 * u, ('u', 1.75, 700), qcol(self.ACCENT), bw, 1)
                w.text(p, desc, br.x() + 0.6 * u, br.y() + 3.0 * u, ('u', 1.25, 400), qcol('#cbd5e1'), bw - 1.2 * u, 1)
                w.hit(br, lambda c=cmd: w.post('api/key', {'seq': c, 'enter': True}), name=f'{self.KEY}:q:{lbl}')
            y += 6.6 * u
        if self.SECONDARY_CHECK:
            return self._draw_checklist(p, self.SECONDARY, y, x0, cw, u)
        for title, desc in self.SECONDARY:
            rh = 6.8 * u
            rr = QRectF(x0, y, cw, rh)
            w.box(p, rr, 1.3 * u, qcol('#151924'), qcol(self.ACCENT2, 0.35))
            w.text(p, title, x0 + 1.8 * u, y + 1.0 * u, ('u', 1.85, 700), qcol(self.ACCENT2), cw - 3.6 * u)
            w.text(p, desc, x0 + 1.8 * u, y + 3.7 * u, ('u', 1.5, 400), qcol('#d1d5db'), cw - 3.6 * u)
            y += rh + 1.1 * u
        return y

    def paint(self, p):
        w, u = self.w, self.w.u
        W, H = w.width(), w.height()
        p.fillRect(0, 0, W, H, qcol(self.BG))
        y = self._draw_header(p, W, u)
        if self.is_tools_tab():
            self.paint_tools_embedded(p, y, self.BG)
            return True
        x0, cw = 2.6 * u, W - 5.2 * u
        if self.tab == 0:
            w.scroller(p, f'{self.KEY}_t0', QRectF(0, y, W, H - y - 1.2 * u),
                       lambda sy: self._draw_checklist(p, self.CHECKLIST, sy, x0, cw, u))
        else:
            w.scroller(p, f'{self.KEY}_t1', QRectF(0, y, W, H - y - 1.2 * u),
                       lambda sy: self._draw_tips(p, sy, x0, cw, u))
        return True


class WowDeck(_StyledGuideDeck):
    KEY = 'wow'
    BG = '#0b0f19'
    ACCENT = '#f59e0b'
    ACCENT2 = '#38bdf8'
    TITLE = 'WoW Forever · WotLK'
    SUBTITLE = 'Instanz-Pfad · Tagesziele · Chat-Makros'
    TABS = ('Instanzen', 'Tagesziele', 'Werkzeuge')
    CHECKLIST = WOW_DUNGEONS
    SECONDARY = WOW_DAILY
    SECONDARY_CHECK = True
    QUICK_BTNS = WOW_MACROS


class SunshineDeck(_StyledGuideDeck):
    KEY = 'sunshine'
    BG = '#071520'
    ACCENT = '#fbbf24'
    ACCENT2 = '#38bdf8'
    TITLE = 'Super Mario Sunshine'
    SUBTITLE = 'Isla Delfino · 120 Insignien · 240 Blaue Münzen'
    TABS = ('Welten', 'Dreckweg', 'Werkzeuge')
    CHECKLIST = SUNSHINE_WORLDS
    SECONDARY = SUNSHINE_TECH
    COUNTER = ('sms_blue_coins', 'Blaue Münzen', 240)


class LuigisMansionDeck(_StyledGuideDeck):
    KEY = 'luigis_mansion'
    BG = '#0c0a16'
    ACCENT = '#34d399'
    ACCENT2 = '#a78bfa'
    TITLE = "Luigi's Mansion · GB Horror"
    SUBTITLE = 'Villa-Bereiche · 50 Buu Huus · Porträtgeister'
    TABS = ('Villa', 'Geister', 'Werkzeuge')
    CHECKLIST = LM_AREAS
    SECONDARY = LM_GHOSTS
    COUNTER = ('lm_boos', 'Gefangene Buu Huus', 50)


class TtydDeck(_StyledGuideDeck):
    KEY = 'ttyd'
    BG = '#170f14'
    ACCENT = '#f43f5e'
    ACCENT2 = '#fbbf24'
    TITLE = 'Paper Mario · Äonentor'
    SUBTITLE = '8 Sternjuwelen · Orden-Kombos · Zess T.'
    TABS = ('Kapitel', 'Rezepte', 'Werkzeuge')
    CHECKLIST = TTYD_CHAPTERS
    SECONDARY = TTYD_RECIPES
    COUNTER = ('ttyd_shines', 'Insignien-Sonnen', 42)


class MkddDeck(_StyledGuideDeck):
    KEY = 'mkdd'
    BG = '#140c0c'
    ACCENT = '#ef4444'
    ACCENT2 = '#facc15'
    TITLE = 'Mario Kart: Double Dash!!'
    SUBTITLE = 'Grand Prix · Spezial-Items · Snaking'
    TABS = ('Cups', 'Technik', 'Werkzeuge')
    CHECKLIST = MKDD_CUPS
    SECONDARY = MKDD_TIPS


class MeleeDeck(_StyledGuideDeck):
    KEY = 'melee'
    BG = '#0b101d'
    ACCENT = '#60a5fa'
    ACCENT2 = '#f472b6'
    TITLE = 'Super Smash Bros. Melee'
    SUBTITLE = 'Kämpfer-Freischaltung · Pro-Techniken'
    TABS = ('Freischalten', 'Tech-Lab', 'Werkzeuge')
    CHECKLIST = MELEE_UNLOCKS
    SECONDARY = MELEE_TECH


class AcGcDeck(_StyledGuideDeck):
    KEY = 'ac_gc'
    BG = '#0a1610'
    ACCENT = '#4ade80'
    ACCENT2 = '#fbbf24'
    TITLE = 'Animal Crossing · Stadt-Almanach'
    SUBTITLE = 'Haus-Kredit · HyperNook · Saison-Tipps'
    TABS = ('Meilensteine', 'Tipps', 'Werkzeuge')
    CHECKLIST = AC_MILESTONES
    SECONDARY = AC_TIPS


class CrashWocDeck(_StyledGuideDeck):
    KEY = 'crash_woc'
    BG = '#190e09'
    ACCENT = '#fb923c'
    ACCENT2 = '#38bdf8'
    TITLE = 'Crash: Zorn des Cortex'
    SUBTITLE = '5 Warp-Räume · Relikte · Elementar-Kräfte'
    TABS = ('Warp-Räume', 'Kräfte', 'Werkzeuge')
    CHECKLIST = CRASH_ROOMS
    SECONDARY = CRASH_POWERS
    COUNTER = ('cb_relics', 'Gesammelte Relikte', 30)


CLASSIC_MAP = {
    'wow': WowDeck,
    'sunshine': SunshineDeck,
    'luigis_mansion': LuigisMansionDeck,
    'ttyd': TtydDeck,
    'mkdd': MkddDeck,
    'melee': MeleeDeck,
    'ac_gc': AcGcDeck,
    'crash_woc': CrashWocDeck,
}


def Deck(w):
    comp = (w.RUN or {}).get('companion') or ''
    cls = CLASSIC_MAP.get(comp, WowDeck)
    return cls(w)
