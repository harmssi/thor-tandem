"""Einstellungen: the settings of Toravo Tandem, built like the iPad's: a list of areas on the left, the chosen area on
the right, grouped rows with short texts, every change takes effect at once. The top screen explains the row in focus.

Controller and finger do the same things in the same places:
    left list   up/down choose an area, A or right open it, B back to the library
    an area     up/down move, left/right change a value (slider, choice, colour), A switches/opens, B back (a sub-page
                goes back to its area, an area back to the list); "‹ Zurück" always sits top left on the right side
L/R still switch the tabs. The state (area, focus) travels with the other screen's through the service like the rest
of the interface: S['page'] ('light', or 'controls>map' for a sub-page), S['pane'] (0 list, 1 area), S['i'] (row).

A row is a dict: k (link, slider, toggle, choice, check, swatches, button, info), t (label), v (value text), help (for
the top screen), fn (A / tap), adj (fn(-1 | 1) for left/right) and what its kind needs (val, on, opts, cur, colors).
"""
import time

ui = None  # the window's module (tandem_ui), set by it: colours and helpers live there

CATS = [  # id, title, icon, icon colour, what the top screen says while the list has the focus; None: a gap between groups
    ('screens', 'Bildschirme & Ton', 'screens', '#0a84ff', 'Helligkeit beider Bildschirme, Lautstärke und wann die Bildschirme zum Schutz schwarz werden.'),
    ('controls', 'Controller & Tasten', 'pad', '#8e8e93', 'Welche Taste was tut – in Tandem, in jedem Emulator und in den Ports. Dazu Gyro und Bildschirmtastatur.'),
    ('light', 'Beleuchtung', 'light', '#bf5af2', 'Farbe und Helligkeit der Leuchtringe um die beiden Sticks.'),
    ('perf', 'Leistung & Akku', 'bolt', '#30d158', 'Leistungsprofil, Akku, Temperatur und Lüfter.'),
    None,
    ('network', 'WLAN & Netzwerk', 'wifi', '#0a84ff', 'WLAN wählen und die Einstellungsseite für Handy und PC.'),
    ('bluetooth', 'Bluetooth', 'bt', '#0a84ff', 'Bluetooth-Kopfhörer und ein zweites Gamepad für Spieler 2 koppeln und verbinden.'),
    ('accounts', 'Konten', 'person', '#ff9f0a', 'RetroAchievements für Erfolge, YouTube, Plex und Battle.net verwalten.'),
    None,
    ('look', 'Aussehen', 'look', '#ff375f', 'Farben, Stil und Sprache der Oberfläche.'),
    ('library', 'Bibliothek', 'stack', '#64d2ff', 'Spiele, Spieleordner, Speicherplatz und Cover.'),
    None,
    ('updates', 'Updates', 'scan', '#5e5ce6', 'Spiel-Begleiter, Emulatoren, Kerne und Tandem automatisch aktuell halten.'),
    ('about', 'Über den Thor', 'info', '#8e8e93', 'Gerät, Versionen und der Einrichtungsassistent.'),
    ('onoff', 'Ein / Aus', 'off', '#ff453a', 'Standby, Neustart, Ausschalten und der Desktop.'),
]
AREAS = [c for c in CATS if c]
TITLES = {c[0]: c[1] for c in AREAS} | {'controls>map': 'Tastenbelegung', 'network>wifi': 'WLAN', 'bluetooth>dev': 'Gerät', 'library>restore': 'Wiederherstellen', 'library>stats': 'Spielzeit & Statistik', 'library>sysbackup': 'Linux- & Tandem-Backup', 'library>storage': 'Android- & Linux-Speicher', 'library>cleanup': 'Speicher-Bereinigung', 'library>compress': 'Spiele schrumpfen (CHD / RVZ)', 'updates>companions': 'Spiel-Begleiter', 'updates>apps': 'Emulatoren & Quellen', 'updates>native': 'Switch-Spiele nativ'}
ICONS = {
    'screens': '<rect x="5" y="3" width="14" height="8" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="5" y="13" width="14" height="8" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    'light': '<circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2.5v2.6M12 18.9v2.6M2.5 12h2.6M18.9 12h2.6M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    'bolt': '<path d="M13.5 2.5L5 13.5h6l-1.5 8 8.5-11h-6z" fill="currentColor"/>',
    'wifi': '<path d="M3 9.5a13 13 0 0 1 18 0M6.2 12.8a8.5 8.5 0 0 1 11.6 0M9.4 16a4 4 0 0 1 5.2 0" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="19" r="1.5" fill="currentColor"/>',
    'person': '<circle cx="12" cy="8.5" r="3.8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    'look': '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor"/>',
    'stack': '<rect x="4" y="9" width="16" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M6.5 6h11M9 3h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    'info': '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 11v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="7.6" r="1.3" fill="currentColor"/>',
    'bt': '<path d="M7 7.5l10 9-5 4.5V3l5 4.5-10 9" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>',
    'audio': '<path d="M4.5 14v-2a7.5 7.5 0 0 1 15 0v2" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="3.5" y="13.5" width="4.5" height="6.5" rx="1.6" fill="currentColor"/><rect x="16" y="13.5" width="4.5" height="6.5" rx="1.6" fill="currentColor"/>',
    'pad': '<path d="M6 8h12a4 4 0 0 1 4 4v1a3 3 0 0 1-5.5 1.7L15 13H9l-1.5 1.7A3 3 0 0 1 2 13v-1a4 4 0 0 1 4-4z" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M7 10v3M5.5 11.5h3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="16.5" cy="11" r="1" fill="currentColor"/><circle cx="18.5" cy="13" r="1" fill="currentColor"/>',
    'input': '<rect x="3" y="7" width="18" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M6.5 10.5h1M10 10.5h1M13.5 10.5h1M17 10.5h.5M8 14h8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    'phone': '<rect x="7" y="3" width="10" height="18" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M11 18h2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    'other': '<circle cx="12" cy="12" r="7.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M9 9.5l6 5-3 2.5V7l3 2.5-6 5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
    'off': '<path d="M12 3.5v8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M7 6.5a7.5 7.5 0 1 0 10 0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
}
KIND_NAMES = {'audio': 'Kopfhörer / Lautsprecher', 'pad': 'Gamepad', 'input': 'Tastatur / Maus', 'phone': 'Telefon', 'other': 'Gerät'}
REST = [(0, 'Nie'), (1, '1 Min.'), (3, '3 Min.'), (10, '10 Min.')]
COLORS = [('Weiß', 'FFFFFF'), ('Rot', 'FF2000'), ('Orange', 'FF7A00'), ('Gelb', 'FFD000'), ('Grün', '20E040'), ('Türkis', '00D0C0'),
          ('Blau', '1060FF'), ('Lila', '9040FF'), ('Pink', 'FF30A0')]  # the same as thor.COLORS
REFRESH = 30  # seconds after which the Thor's values (temperature, fan …) are asked again while the settings show


def open_now(win): return win.S['tab'] == 4 and not win.S['sys']


def page_of(win):
    page = win.S.get('page') or AREAS[0][0]
    return page if page in TITLES else AREAS[0][0]


# ---- data ------------------------------------------------------------------------------------------------------------
def need(win):
    """Asks the service for what the settings show, once, and the Thor's values again every REFRESH seconds."""
    if win.SYS is None and not win.asked: win.asked = True; win.load_sys()
    partial = win.THOR is not None and not (win.THOR.get('rgb') or win.THOR.get('gyro'))  # Armada Control did not answer: soon again
    if time.time() - win.thor_at > (5 if partial else REFRESH):
        win.thor_at = time.time()
        win.call('api/thor', then=lambda t: t and setattr(win, 'THOR', t))
    if page_of(win).startswith('bluetooth'):
        now = time.time()
        if now - getattr(win, 'bt_at', 0) > (2 if (win.__dict__.get('BT') or {}).get('scanning') else 6):
            win.bt_at = now
            win.call('api/bluetooth', then=lambda b: b and (setattr(win, 'BT', b), win.update()))
            win.call('api/airpods', then=lambda a: a and (setattr(win, 'AIRPODS', a), win.update()))
        if now - getattr(win, 'bt_scan', 0) > 120:  # opening the area looks for devices at once (both windows ask: one scan)
            win.bt_scan = now
            win.post('api/bluetooth', {'scan': True}, then=lambda r: setattr(win, 'bt_at', 0))
    if win.CTRL is None and page_of(win).startswith('controls'):
        win.CTRL = {}
        win.call('api/controls', then=lambda c: setattr(win, 'CTRL', c or {}))
    if win.SAVES is None and page_of(win) == 'library':
        win.SAVES = {}
        win.call('api/saves', then=lambda s: setattr(win, 'SAVES', s or {}))
    if page_of(win).startswith('library'):
        sb = getattr(win, 'SYSBK', None)
        sb_running = bool(((sb or {}).get('backups') or {}).get('job', {}).get('running') or ((sb or {}).get('storage') or {}).get('job', {}).get('running'))
        if sb is None or time.time() - getattr(win, 'sysbk_at', 0) > (3 if sb_running else 20):
            win.sysbk_at = time.time()
            win.call('api/sysbackup', then=lambda r: r and (setattr(win, 'SYSBK', r), win.update()))
    if page_of(win) == 'perf' and time.time() - getattr(win, 'ptele_at', 0) > 15:
        win.ptele_at = time.time()
        win.call('api/telemetry', then=lambda r: r and setattr(win, 'QTELE', r))
    if page_of(win).startswith('updates'):
        uc = getattr(win, 'UPDC', None)
        uc_running = bool(((uc or {}).get('job') or {}).get('running'))
        if uc is None or time.time() - getattr(win, 'updc_at', 0) > (2.5 if uc_running else 18):
            win.updc_at = time.time()
            win.call('api/updater', then=lambda r: r and (setattr(win, 'UPDC', r), win.update()))
        if time.time() - getattr(win, 'swnat_at', 0) > 10:
            win.swnat_at = time.time()
            win.call('api/switch_native', then=lambda r: r and setattr(win, 'SWNAT', r))
    if page_of(win) == 'accounts' and win.__dict__.get('YT_QR'):
        if win.CFG.get('yt_set'):
            win.YT_QR = None
        elif time.time() - getattr(win, 'yt_qr_at', 0) > 5:
            win.yt_qr_at = time.time()
            def _on_qr(r):
                if not r: return
                if r.get('signed_in'): win.YT_QR = None
                elif r.get('code'): win.YT_QR = r
                win.update()
            win.post('api/ytlogin', {'a': 'qr'}, then=_on_qr)


def thor_set(win, key, value):
    """Changes a Thor setting: shown at once, sent at most every 150 ms (a held key or a dragged slider)."""
    T = win.THOR or {}
    if key == 'rgb' and T.get('rgb'): T['rgb'].update(value, **({'level': value['brightness']} if 'brightness' in value else {}))
    elif key == 'gyro' and T.get('gyro'): T['gyro']['enabled'] = value
    elif key == 'profile' and T.get('power'): T['power']['profile'] = value
    pending = win.__dict__.setdefault('thor_pending', {})
    pending[key] = {**pending.get(key, {}), **value} if isinstance(value, dict) else value
    if not getattr(win, 'thor_timer', None):
        win.thor_timer = ui.QTimer(win, singleShot=True)
        def send():
            todo, win.thor_pending = win.thor_pending, {}
            for k, v in todo.items():
                win.post('api/thor', {'key': k, 'value': v}, then=lambda r: r and (win.toast(r['error']) if r.get('error') else setattr(win, 'THOR', r)))
        win.thor_timer.timeout.connect(send)
    if not win.thor_timer.isActive(): win.thor_timer.start(150)
    win.update()


def config_set(win, **change):
    win.CFG = {**win.CFG, **change}
    win.post('api/config', change, then=lambda c: c and c.get('error') and win.toast(c['error']))


def level(win, key, value):
    """Brightness or volume by the controller: the same path as the slider (one change per 60 ms)."""
    low = 0 if key == 'vol' else 5
    value = max(low, min(100, value))
    if value != win.SET.get(key):
        win.SET[key] = value
        win.pending = {'key': key, 'value': value, 'from': win.me}
        if not win.timers['set'].isActive(): win.timers['set'].start(60)


def go_page(win, page):
    win.S.update(page=page, pane=1, i=0)
    if page == 'network>wifi': win.toast('Suche Netze …'); win.load_sys(True)
    win.push()


# ---- the areas -------------------------------------------------------------------------------------------------------
def groups(win, page):
    """[(header, rows, footer)] of one page."""
    SET, CFG, SYS, T, P = win.SET, win.CFG, win.SYS or {}, win.THOR, win.PAIR or {}
    loading = [(None, [{'k': 'info', 't': 'Einen Moment …', 'v': '', 'help': 'Tandem fragt den Thor.'}], None)]
    if page == 'screens':
        sl = lambda key, label, help: {'k': 'slider', 't': label, 'val': SET.get(key), 'low': 0 if key == 'vol' else 5, 'key': key, 'help': help,
                                       'adj': lambda d: level(win, key, (SET.get(key) or 0) + 5 * d)}
        rows = [sl(k, l, h) for k, l, h in (('bt', 'Oben', 'Helligkeit des oberen Bildschirms.'), ('bb', 'Unten', 'Helligkeit des unteren Bildschirms.')) if SET.get(k) is not None]
        rows.append(choice('Nachtmodus', [('off', 'Aus'), ('warm', 'Warm'), ('night', 'Nacht')], CFG.get('night_mode') or 'off',
                           lambda v: config_set(win, night_mode=v),
                           'Wärmeres Bild mit weniger Blaulicht auf beiden Bildschirmen – schont die Augen am Abend.'))
        sound = ([sl('vol', 'Lautstärke', 'Lautstärke des Thor. Die Tasten an der Seite ändern sie in 5er-Schritten.')] if SET.get('vol') is not None else []) + \
                [toggle('Ton stumm', getattr(win, 'MUTED', False), lambda v: win.toggle_mute(v), 'Schaltet Lautsprecher und Kopfhörer stumm.')]
        rest = CFG.get('rest_min', 3)
        stby = [toggle('Beim Zuklappen in Standby', CFG.get('lid_sleep', True), lambda v: config_set(win, lid_sleep=v),
                       'Schließt du den Thor, geht er von selbst in den Standby und wacht beim Aufklappen wieder auf.'),
                toggle('Musik bei geschlossenem Deckel', CFG.get('lid_music', True), lambda v: config_set(win, lid_music=v),
                       'Spielt YouTube, Plex oder Hintergrundmusik über Kopfhörer weiter, wenn der Deckel geschlossen wird (nur Bildschirme & Lichter aus).'),
                toggle('Am TV / Monitor abdunkeln', CFG.get('dock_dim', True), lambda v: config_set(win, dock_dim=v),
                       'Dunkelt die beiden eingebauten OLED-Bildschirme automatisch ab, sobald ein USB-C-Monitor oder Fernseher angeschlossen ist.'),
                choice('Am Ladegerät', [('doze', 'Erreichbar'), ('sleep', 'Tiefschlaf')], CFG.get('charger_standby', 'doze'),
                       lambda v: config_set(win, charger_standby=v),
                       'Erreichbar: Bildschirme, Ton und Lichter aus, Spiel pausiert, aber WLAN und Downloads laufen weiter. Tiefschlaf: legt das Gerät ganz schlafen.')]
        return [('Helligkeit', rows, None),
                ('Ton', sound, None),
                ('Ruheschutz (OLED)', [
                    choice('Schwarz nach', REST, rest, lambda v: config_set(win, rest_min=v),
                           'Rührt niemand Tandem an, startet nach dieser Zeit der Dual-Screen-OLED-Bildschirmschoner. Jede Taste weckt ihn.'),
                    choice('Bildschirmschoner-Stil', list(ui.screensaver.STYLES), CFG.get('saver_style') or 'kosmos',
                           lambda v: config_set(win, saver_style=v),
                           'Thor Kosmos lässt deine Spiele-Cover schwebend über beide OLED-Bildschirme gleiten; Arcade zeigt wechselnde Spiel-Porträts; Dual-Aurora fließendes Nordlicht.'),
                    {'k': 'button', 't': 'Bildschirmschoner jetzt starten',
                     'fn': lambda: win.post('api/saver', {'open': True}),
                     'help': 'Startet den Dual-Screen-Bildschirmschoner sofort auf beiden Bildschirmen.'},
                ], 'Während ein Spiel läuft, bleibt der Bildschirm an.'),
                ('Im Spiel', [
                    choice('FPS-Fenster (oben)', [(0, 'Aus'), (1, 'FPS'), (2, 'Leiste'), (3, 'Graph')], int(CFG.get('hud_level') or 0),
                           lambda v: config_set(win, hud_level=v),
                           'Blendet oben im Spiel Live-FPS, Auslastung und Frametime-Graph ein (auch jederzeit über die Thor-Taste umschaltbar).'),
                    choice('OLED-Farbbrillanz', [('srgb', 'sRGB'), ('natural', 'Natürlich'), ('vibrant', 'Brillant'), ('ultra', 'Ultra')],
                           CFG.get('oled_vibrance') or 'vibrant', lambda v: config_set(win, oled_vibrance=v),
                           'Hardware-Farbraum-Steuerung für beide OLED-Displays (wie auf dem Steam Deck OLED – null GPU-Kosten).'),
                    choice('Lautsprecher-Klang (DSP)', [('off', 'Aus'), ('cinema', 'Kino-Bass'), ('clear', 'Klar'), ('night', 'Nacht')],
                           CFG.get('speaker_dsp') or 'cinema', lambda v: config_set(win, speaker_dsp=v),
                           'Psychoakustische PipeWire-Klangbühne exklusiv für die eingebauten Lautsprecher (wie auf dem Steam Deck OLED; Kopfhörer & Bluetooth bleiben unverändert bitgenau).'),
                    toggle('Low-Latency-Modus', CFG.get('low_latency', True), lambda v: config_set(win, low_latency=v),
                           'Direkter Gamescope-Low-Latency-Pfad, 2-Frame-Swapchain und 24-ms-PipeWire-Audio (~25 ms geringere Eingabeverzögerung als Android).'),
                    toggle('Retro-Zero-Lag (RetroArch)', CFG.get('ra_zerolag', True), lambda v: config_set(win, ra_zerolag=v),
                           'Senkt die RetroArch-Latenz um ~55 ms (2-Bild-Vulkan-Swapchain, 28-ms-Audio, automatischer Frame-Delay und 1 Preemptive Frame für klassische 2D-Konsolen).'),
                    toggle('Sofort-Fortsetzen (RetroArch)', CFG.get('ra_autoresume', True), lambda v: config_set(win, ra_autoresume=v),
                           'Speichert beim Beenden oder Spielwechsel automatisch den Stand und lädt ihn beim nächsten Start nahtlos weiter (wie auf OnionOS).'),
                    choice('Retro-Optik (Shader)', [('sharp', 'Scharf'), ('auto', 'Auto'), ('crt', 'CRT-OLED'), ('lcd', 'Handheld-LCD')],
                           CFG.get('ra_shader') or 'sharp', lambda v: config_set(win, ra_shader=v),
                           'Offline integrierte Vulkan-OLED-Shader für RetroArch: Auto wählt Handheld-LCD-Raster für GB/GBC/GBA und Trinitron-CRT-Scanlines für TV-Konsolen.'),
                    toggle('30-Sekunden-Replay-Puffer (RAM)', CFG.get('replay_buffer', False), lambda v: config_set(win, replay_buffer=v),
                           'Hält im Spiel die letzten 30 Sekunden rein im Arbeitsspeicher (0 % Flash-Abnutzung) bereit – jederzeit per „⏪ 30s-Clip“ im Schnellmenü speichern & per QR aufs Handy teilen.'),
                    toggle('Couch-Koop am TV (BT-Pad = Spieler 1)', CFG.get('dock_pad_swap', True), lambda v: config_set(win, dock_pad_swap=v),
                           'Setzt im TV-/Dock-Modus ein verbundenes Bluetooth-Gamepad automatisch auf Spieler 1.'),
                    choice('Konsolen-Klänge', [('off', 'Aus'), ('subtle', 'Dezent')], CFG.get('ui_sounds') or 'off',
                           lambda v: config_set(win, ui_sounds=v),
                           'Dezente akustische Rückmeldung beim Navigieren und Spielstart wie auf der Switch 2.'),
                ], None),
                ('Standby', stby, None)]
    if page == 'controls':
        C, gyro = win.CTRL or {}, (T or {}).get('gyro')
        off = len({d.get('emu') for d in C.get('off') or []})  # emulators that differ, not keys
        cstyle = CFG.get('controls_style') if CFG.get('controls_style') in ('thor', 'xbox') else 'thor'
        rows = [{'k': 'link', 't': 'Tastenbelegung', 'v': 'Übersicht', 'fn': lambda: go_page(win, 'controls>map'), 'help': 'Welche Taste wo was tut: in Tandem, in jedem Spiel, die Kürzel mit Select.'},
                choice('Tasten-Stil', [('thor', 'Thor-Aufdruck'), ('xbox', 'Xbox-Stil')], cstyle,
                       lambda v: (config_set(win, controls_style=v), setattr(win, 'CTRL', None)),
                       'Einheitlich über alle Konsolen: Thor-Aufdruck (A rechts = Bestätigen, B unten = Zurück) oder Xbox-Stil (Unten = Bestätigen, Rechts = Zurück). Gilt sofort in allen Emulatoren.'),
                {'k': 'button', 't': 'In allen Emulatoren angleichen', 'v': (f'{off} Emulator' + ('en' if off != 1 else '') + ' weichen ab' if off != 1 else '1 Emulator weicht ab') if off else 'alles gleich',
                 'fn': lambda: apply_controls(win), 'help': 'Stellt in jedem installierten Emulator die Tandem-Belegung ein. Vorher wird jede geänderte Datei gesichert.'}]
        rows2 = [{'k': 'info', 't': 'Controller', 'v': 'Xbox 360 (fest)', 'help': 'Unter Tandem meldet sich der Thor immer als Xbox-360-Controller. Nur so liegt jede Taste in jedem Emulator gleich.'}]
        if gyro: rows2.append(toggle('Gyro', gyro.get('enabled'), lambda on: thor_set(win, 'gyro', on), 'Bewegungssensor des Thor für Spiele, die ihn nutzen (z. B. Zielen durch Neigen).'))
        layout = 'us' if CFG.get('kb_layout') == 'us' else 'de'
        rows2.append(choice('Bildschirmtastatur', [('de', 'Deutsch'), ('us', 'Englisch')], layout, lambda v: config_set(win, kb_layout=v),
                            'Belegung der Tasten auf dem unteren Bildschirm, wenn etwas eingetippt wird.'))
        rows2.append(toggle('Menü-Vibration', CFG.get('ui_haptics', True), lambda v: config_set(win, ui_haptics=v),
                            'Dezentes haptisches Klicken beim Navigieren durch Menüs, Tabs und beim Spielstart.'))
        rows2.append(toggle('Tastatur-Vibration', CFG.get('kb_haptics', True), lambda v: config_set(win, kb_haptics=v),
                            'Kurzes haptisches Klicken beim Tippen auf der Bildschirmtastatur.'))
        rows2.append({'k': 'button', 't': 'Thor klingeln & vibrieren',
                      'fn': lambda: win.post('api/locate', {}),
                      'help': 'Spielt einen Suchton ab und lässt den Thor rhythmisch vibrieren (auch vom Handy über die Einstellungsseite auslösbar).'})
        return [(None, rows, 'Bestätigen ist immer A, zurück immer B – in Tandem, in jedem Emulator und in den Ports.'), ('Controller', rows2, None)]
    if page == 'controls>map':
        table = (win.CTRL or {}).get('table')
        if table is None: return loading
        out, seen = [], {}
        for row in table:
            head = row.get('group') or row.get('where') or ''
            if head not in seen: seen[head] = []; out.append((head or None, seen[head], None))
            seen[head].append({'k': 'info', 't': row.get('what', ''), 'v': row.get('pad', ''), 'sub': row.get('where') if row.get('group') else None,
                               'help': (f'Gilt für: {row["where"]}.' if row.get('where') and row.get('group') else '')})
        return out or [(None, [{'k': 'info', 't': 'Keine Übersicht', 'v': '', 'help': ''}], None)]
    if page == 'light':
        if T is None: return loading
        rgb = T.get('rgb')
        if not rgb: return [(None, [{'k': 'info', 't': 'Stick-Beleuchtung', 'v': 'nicht verfügbar', 'help': 'ArmadaOS meldet für dieses Gerät keine steuerbare Beleuchtung (oder Armada Control antwortet nicht).'}], None)]
        on, color = bool(rgb.get('enabled')), str(rgb.get('color', 'FFFFFF')).upper()
        names = [c[1] for c in COLORS]
        def step(d):
            n = names.index(color) if color in names else -1
            thor_set(win, 'rgb', {'color': names[(n + d) % len(names)], 'enabled': True})
        return [(None, [toggle('Stick-Beleuchtung', on, lambda v: thor_set(win, 'rgb', {'enabled': v}), 'Die Leuchtringe um beide Sticks ein- oder ausschalten.'),
                        {'k': 'swatches', 't': 'Farbe', 'cur': color, 'adj': step, 'fn': lambda: step(1),
                         'help': 'Links/rechts wählt die Farbe, die Ringe zeigen sie sofort.'},
                        {'k': 'slider', 't': 'Helligkeit', 'val': rgb.get('level', 50), 'low': 0, 'set': lambda v: thor_set(win, 'rgb', {'brightness': v, 'enabled': True}),
                         'adj': lambda d: thor_set(win, 'rgb', {'brightness': max(0, min(100, rgb.get('level', 50) + 5 * d)), 'enabled': True}),
                         'help': 'Wie hell die Ringe leuchten. Mit „Mit dem Bildschirm“ ist das die größte Helligkeit.'},
                        toggle('Mit dem Bildschirm', rgb.get('linkBrightness'), lambda v: thor_set(win, 'rgb', {'linkBrightness': v, 'brightness': rgb.get('level', 50)}),
                               'Die Ringe werden mit dem oberen Bildschirm heller und dunkler.'),
                        choice('Stick-Modus (Bifrost)',
                               [('cover', 'Spiel-Farbe'), ('ambilight', 'Ambilight'), ('battery', 'Akku'), ('thermal', 'Temp'), ('static', 'Fest')],
                               CFG.get('rgb_mode') or ('cover' if CFG.get('rgb_sync', True) else 'static'),
                               lambda v: config_set(win, rgb_mode=v, rgb_sync=(v != 'static')),
                               'Spiel-Farbe folgt dem Cover; Ambilight liest live die Bildfarbe beim Spielen; Akku zeigt Ladestand & Schnellladen; Temp warnt ab 65 °C; Fest behält deine gewählte Farbe.')],
                 'Die Einstellung bleibt auch nach einem Neustart.')]
    if page == 'perf':
        if T is None: return loading
        pw, B = T.get('power'), win.BATT
        qt = getattr(win, 'QTELE', None) or {}
        bd = qt.get('battery') or {}
        chg = qt.get('charger') or {}
        rows = []
        if pw:
            labels = dict(pw.get('profiles') or [])
            rows.append(choice('Leistungsprofil', list(labels.items()), pw.get('profile'), lambda v: thor_set(win, 'profile', v),
                               'Sparsam: länger spielen, leiser. Ausgewogen: schedutil für fast alles. Leistung: volle Taktraten. Turbo: alle Kerne auf Maximum + Adreno 740 auf 680 MHz.'))
            pf = pw.get('perf') or {}
            cur_gpu = (pf.get('gpu_mhz') if pf.get('gpu_gov') == 'performance' and pf.get('gpu_mhz') in (401, 550, 680) else 0)
            rows.append(choice('Adreno GPU-Takt', [(0, 'Auto'), (401, '401 MHz'), (550, '550 MHz'), (680, '680 MHz')],
                               cur_gpu, lambda v: thor_set(win, 'gpu_clock', v),
                               'Fixiert den Adreno-740-Takt gegen Shader-Ruckler in schweren Spielen oder überlässt ihn der Automatik.'))
            rows.append(choice('Lüfter-Modus', [('auto', 'Auto'), ('quiet', 'Leise'), ('cool', 'Kühl'), ('max', 'Max')],
                               pf.get('fan_mode') or 'auto', lambda v: thor_set(win, 'fan_mode', v),
                               'Kühl hält den Snapdragon 8 Gen 2 bei langen Sessions deutlich unter 65 °C und verhindert Throttling.'))
        rows.append(toggle('Unterwegs-Modus (Akku-Sparpaket)', CFG.get('travel_mode', False),
                           lambda v: config_set(win, travel_mode=v),
                           'Schaltet mit einem Tipp auf Profil Sparsam, senkt das obere OLED-Panel auf 60 Hz, schaltet die Stick-LEDs aus und beendet Hintergrund-Steam – bringt unterwegs spürbar längere Laufzeit.'))
        rows.append(toggle('Unterwegs automatisch bei Akkubetrieb', CFG.get('auto_travel', False),
                           lambda v: config_set(win, auto_travel=v),
                           'Aktiviert den Unterwegs-Modus automatisch beim Abziehen des Ladekabels und gibt am Netzteil sofort wieder 120 Hz & volle Leistung frei.'))
        cur_hz = 60 if (CFG.get('travel_mode') or int(CFG.get('panel_hz') or 120) == 60) else 120
        rows.append(choice('Bildwiederholrate (Oben)', [(120, '120 Hz'), (60, '60 Hz (Akku+)')],
                           cur_hz, lambda v: config_set(win, panel_hz=v, **({'travel_mode': False} if v == 120 and CFG.get('travel_mode') else {})),
                           '60 Hz spart unterwegs rund 1,2–1,8 W Display- und GPU-Energie; Retro- und 60-FPS-Spiele laufen damit genauso flüssig.'))
        if T.get('sleep_mode') in ('s2idle', 'fake'):
            rows.append(choice('Standby-Modus', [('s2idle', 'Nativ (Tiefschlaf)'), ('fake', 'Schnell-Ruhe')],
                               T['sleep_mode'], lambda v: thor_set(win, 'sleep_mode', v),
                               'Nativ (s2idle) versetzt den Snapdragon-Chip in echten Kernel-Tiefschlaf für minimalen Standby-Verbrauch in der Tasche.'))

        chg_rows = []
        if chg:
            chg_rows.append({'k': 'info', 't': 'Schnelllade-Status', 'v': chg.get('label') or '–',
                             'help': chg.get('hint') or 'USB-Power-Delivery- und PPS-Status des Ladeanschlusses.'})
            if chg.get('online') and (chg.get('voltage_v') or chg.get('current_limit_a')):
                va_parts = []
                if chg.get('voltage_v'): va_parts.append(f'{chg["voltage_v"]:g} V')
                if chg.get('current_limit_a'): va_parts.append(f'{chg["current_limit_a"]:g} A Limit')
                if chg.get('live_input_w'): va_parts.append(f'{chg["live_input_w"]:g} W aktuell')
                chg_rows.append({'k': 'info', 't': 'Netzteil-Aushandlung', 'v': ' · '.join(va_parts),
                                 'help': 'Ausgehandelte USB-C-Spannung und maximaler Eingangsstrom. Für volles Schnellladen (9 V / PPS) ein USB-PD-Netzteil ab 27 W direkt anschließen.'})
            if chg.get('cell_max_a'):
                cur_a = f'{chg["cell_charge_a"]:g} A aktiv · ' if chg.get('cell_charge_a') else ''
                chg_rows.append({'k': 'info', 't': 'Zell-Ladestrom', 'v': f'{cur_a}bis {chg["cell_max_a"]:g} A PD/PPS',
                                 'help': 'Maximal zulässiger Ladestrom des 6000-mAh-Akkus über Qualcomm PMIC.'})
            if chg.get('mins_to_full'):
                chg_rows.append({'k': 'info', 't': 'Restladezeit', 'v': f'~{chg["mins_to_full"]} Min.',
                                 'help': 'Geschätzte Zeit bis zur Vollladung.'})
        pf_c = (pw or {}).get('perf') or {}
        cur_lim = pf_c.get('charge_limit') if pf_c.get('charge_limit') in (80, 85, 100) else 100
        chg_rows.append(choice('Bypass-Ladelimit (Hardware)', [(100, 'Aus (100 %)'), (80, '80 % Bypass'), (85, '85 % Bypass')],
                               cur_lim, lambda v: thor_set(win, 'charge_limit', v),
                               'Stoppt das Laden bei 80 % bzw. 85 % und versorgt den Thor am Netzteil direkt – weniger Hitze und maximale Akku-Lebensdauer.'))
        chg_rows.append(choice('Akku-Schutz (Lade-Hinweis)', [(0, 'Aus'), (80, 'Bei 80 %'), (90, 'Bei 90 %')],
                               int(CFG.get('charge_alert') or 0), lambda v: config_set(win, charge_alert=v),
                               'Meldet sich mit Hinweis und Ton, sobald der Akku beim Laden 80 % bzw. 90 % erreicht – schont die Akkuzellen auf Dauer.'))

        pf_i = (pw or {}).get('perf') or {}
        eng = T.get('engine') or {}
        hd_rows = []
        if eng:
            hd_rows.append(toggle('⚡ HyperDrive (Max-FPS & Low-Lag)', bool(eng.get('hyperdrive')),
                                  lambda v: thor_set(win, 'hyperdrive', v),
                                  'Aktiviert mit einem Klick Turnip WinNative 27.0, FEX Fast-JIT (TSO=0, +35–50 % DX11-FPS), Proton-CachyOS ARM64EC, den SteamOS-LAVD-Scheduler und Big-Core-Isolierung (Kerne 3–7 exklusiv fürs Spiel, Kerne 0–2 für Tandem).'))
            drv_choices = [(d[0], d[1]) for d in (eng.get('turnip_drivers') or [['stable', 'Stable'], ['devel', 'Devel'], ['winnative', 'WinNative']])]
            hd_rows.append(choice('Turnip Vulkan-Treiber', drv_choices, eng.get('turnip') or 'stable',
                                  lambda v: thor_set(win, 'turnip', v),
                                  'WinNative 27.0 ist speziell für Windows-DX11/DX12-Spiele unter ARM64EC optimiert; Devel bietet neueste Mesa-Git-Features; Stable maximale Kompatibilität.'))
            hd_rows.append(choice('FEX x86-Engine', [('fast', 'Fast (Max-FPS)'), ('default', 'Ausgewogen'), ('compatible', 'Kompatibel (TSO)')],
                                  eng.get('fex_profile') or 'default', lambda v: thor_set(win, 'fex_profile', v),
                                  'Fast schaltet langsame Software-TSO-Barrieren auf dem Snapdragon 8 Gen 2 ab und beschleunigt CPU-limitierte DirectX-11-Spiele massiv.'))
            hd_rows.append(choice('Gaming-Scheduler (Kernel BPF)', [('lavd', 'LAVD (SteamOS)'), ('cosmos', 'Cosmos (big.LITTLE)'), ('eevdf', 'EEVDF (Standard)')],
                                  eng.get('scheduler') or 'eevdf', lambda v: thor_set(win, 'scheduler', v),
                                  'LAVD (Latency-Aware Virtual Deadline aus SteamOS/CachyOS) priorisiert Spiel- und Audio-Threads für glattere Frametimes ohne Mikroruckler.'))
            hd_rows.append(choice('Asymmetrische Kern-Isolierung', [('big', 'Gold + Prime (3–7)'), ('all', 'Alle Kerne (0–7)')],
                                  eng.get('cores') or 'all', lambda v: thor_set(win, 'core_mode', v),
                                  'Hält Spiel- und FEX-Threads von den langsamen Cortex-A510-Silberkernen (0–2) fern und reserviert die Silberkerne für das untere Tandem-Display (0 % CPU-Abzug im Spiel).'))

        cmhz = pf_i.get('cpu_mhz') or {}
        cpu_str = f'{cmhz.get("prime", "–")} MHz ({pf_i.get("cpu_gov") or "–"}) · GPU {pf_i.get("gpu_mhz") or "–"} MHz' if cmhz else ''
        ram_str = f'{pf_i["ram_free_gib"]:g} von {pf_i["ram_total_gib"]:g} GiB frei'.replace('.', ',') if pf_i.get('ram_free_gib') is not None and pf_i.get('ram_total_gib') else ''
        w_live = f' · {bd["watts"]:g} W' if (bd.get('watts') and not (B or {}).get('charging')) else ''
        info = ([{'k': 'info', 't': 'Akku', 'v': f'{B["level"]} %' + (' · lädt' if B.get('charging') else w_live), 'help': 'Aktueller Ladestand und Entladeleistung des Akkus.'}] if B else []) + \
               ([{'k': 'info', 't': 'Akku-Zustand', 'v': f'{bd["health"]} %' + (f' · {bd["cycles"]} Zyklen' if bd.get('cycles') is not None else ''), 'help': 'Gesundheitszustand und bisherige Ladezyklen des Akkus.'}] if bd.get('health') is not None else []) + \
               ([{'k': 'info', 't': 'Freier Spiel-Speicher (RAM)', 'v': ram_str, 'help': 'Freier Arbeitsspeicher für Spiele (deutlich mehr als unter Android, plus schneller LZ4-ZRAM).'}] if ram_str else []) + \
               ([{'k': 'info', 't': 'CPU / GPU Live', 'v': cpu_str, 'help': 'Aktueller Prime-Core-Takt, CPU-Governor und Adreno-740-GPU-Takt.'}] if cpu_str else []) + \
               ([{'k': 'info', 't': 'Aktiver Scheduler', 'v': (pf_i.get('scheduler') or 'eevdf').upper(), 'help': 'Aktiver Linux-Kernel- bzw. sched_ext-BPF-Scheduler.'}] if pf_i.get('scheduler') else []) + \
               ([{'k': 'info', 't': 'Temperatur', 'v': f'{pw["temp"]} °C', 'help': 'Temperatur im Gerät. Bis etwa 80 °C ist alles in Ordnung.'},
                 {'k': 'info', 't': 'Lüfter', 'v': f'{pw["fan"]} U/min', 'help': 'Der Lüfter regelt sich selbst nach der Temperatur und dem Profil.'}] if pw else [])
        sections = [('Leistung & Unterwegs', rows, 'Gilt sofort und bleibt bis zur nächsten Änderung.' if rows else 'Das Leistungsprofil ist hier nicht erreichbar.')]
        if hd_rows:
            sections.append(('HyperDrive & Treiber-Engine', hd_rows, 'Holt auf dem Snapdragon 8 Gen 2 maximale PC- & Emulator-FPS bei minimaler Latenz heraus.'))
        sections.extend([('Schnellladen & Akku-Pflege', chg_rows, None), ('Zustand', info, None)])
        return sections
    if page == 'network':
        own = P.get('own') or P.get('url')
        wol_rows = [{'k': 'link', 't': 'PC-MAC-Adresse', 'v': CFG.get('wol_mac') or 'nicht gesetzt', 'fn': win.ask_wol_mac, 'bottom': True,
                     'help': 'MAC-Adresse deines Streaming-PCs für Wake-on-LAN (z. B. für Moonlight).'}]
        if CFG.get('wol_mac'):
            wol_rows.append({'k': 'button', 't': 'PC jetzt aufwecken',
                             'fn': lambda: win.post('api/wol', {}, then=lambda r: r and win.toast(r.get('text') or r.get('error', ''))),
                             'help': 'Sendet ein Wake-on-LAN-Signal im Heimnetz an den eingetragenen PC.'})
        return [(None, [{'k': 'link', 't': 'WLAN', 'v': SYS.get('ssid') or ('nicht verbunden' if win.SYS else '…'), 'fn': lambda: go_page(win, 'network>wifi'),
                         'help': 'Netze in der Nähe zeigen und verbinden.'}], None),
                ('Vom Handy oder PC', [{'k': 'info', 't': 'Adresse', 'v': own or '–', 'help': 'Diese Adresse im Browser öffnen: dort gibt es dieselben Einstellungen, bequem mit Tastatur.'},
                                       {'k': 'info', 't': 'PIN', 'v': str(P.get('pin') or '–'), 'help': 'Die PIN gilt einmal. Danach bleibt der Browser ein Jahr angemeldet.'}] +
                 ([{'k': 'info', 't': 'Im Heimnetz', 'v': P['ip_url'], 'help': 'Falls der Name nicht gefunden wird: diese Adresse mit Zahlen.'}] if P.get('ip_url') else []), None),
                ('PC-Streaming (Wake-on-LAN)', wol_rows, None)]
    if page == 'network>wifi':
        nets = SYS.get('networks') or []
        rows = [{'k': 'check', 't': n['ssid'], 'on': n.get('active'), 'v': f'{n["signal"]} %' + (' · geschützt' if n.get('secure') else ''), 'fn': lambda n=n: win.wifi(n),
                 'bottom': bool(n.get('secure') and not n.get('known')), 'help': 'Verbinden.' + (' Das Passwort tippst du unten ein.' if n.get('secure') and not n.get('known') else '')} for n in nets]
        return [(None, rows or [{'k': 'info', 't': 'Keine Netze gefunden', 'v': '', 'help': ''}], None),
                (None, [{'k': 'button', 't': 'Erneut suchen', 'fn': lambda: (win.toast('Suche Netze …'), win.load_sys(True)), 'help': 'Sucht noch einmal nach Netzen.'}], None)]
    if page == 'bluetooth':
        B = win.__dict__.get('BT')
        if B is None: return loading
        if B.get('error'): return [(None, [{'k': 'info', 't': 'Bluetooth', 'v': 'nicht verfügbar', 'help': B['error']}], None)]
        bt = lambda body, text: lambda: (win.toast(text), win.post('api/bluetooth', body, then=lambda r: (r and r.get('error') and win.toast(r['error']), setattr(win, 'bt_at', 0))))
        top = [toggle('Bluetooth', B.get('powered'), lambda on: bt({'power': on}, 'Bluetooth ' + ('ein' if on else 'aus'))(), 'Bluetooth des Thor ein- oder ausschalten.'),
               toggle('Gaming-Low-Latency-Audio (AAC / SBC-XQ)', CFG.get('bt_low_latency', True), lambda v: config_set(win, bt_low_latency=v),
                      'Aktiviert SBC-XQ, AAC mit voller Bitrate und 10-ms-PipeWire-Puffer und verhindert das Zurückfallen auf dumpfen 8-kHz-Telefonklang in Spielen.')]
        if B.get('powered'):
            top.append({'k': 'button', 't': 'Nach Geräten suchen', 'v': 'sucht …' if B.get('scanning') else '', 'fn': bt({'scan': True}, 'Suche Geräte …'),
                        'help': 'Sucht 30 Sekunden lang nach Geräten. Kopfhörer oder Gamepad vorher in den Kopplungsmodus bringen (meist die Bluetooth- oder Ein-Taste lange halten).'})
        AP = win.__dict__.get('AIRPODS') or {}
        ap_rows = []
        if B.get('powered') and AP.get('is_airpods'):
            pods = AP.get('pods') or {}
            b_parts = []
            for pk, pl in (('left', 'Links'), ('right', 'Rechts'), ('case', 'Ladecase')):
                pv = pods.get(pk) or {}
                if pv.get('level') is not None:
                    b_parts.append(f'{pl} {pv["level"]} %')
            ap_rows = [
                {'k': 'info', 't': AP.get('name') or 'Apple AirPods',
                 'v': ' · '.join(b_parts) if b_parts else ('verbunden' if AP.get('active') else 'gekoppelt'),
                 'help': 'Direkte Kommunikation über das Apple-Accessory-Protokoll (L2CAP 0x1001) – ganz ohne iPhone.'},
                choice('Geräuschkontrolle', [('off', 'Aus'), ('anc', 'ANC'), ('transparency', 'Transparenz'), ('adaptive', 'Adaptiv')],
                       AP.get('noise_mode') or 'off',
                       lambda m: win.post('api/airpods', {'action': 'noise', 'mode': m},
                                          then=lambda r: (AP.update(noise_mode=m), r and r.get('text') and win.toast(r['text']), win.update())),
                       'Schaltet Aktive Geräuschunterdrückung (ANC), Transparenz oder Adaptives Audio direkt auf den AirPods um.'),
                toggle('Konversationsbewusstsein', bool(AP.get('conv_awareness')),
                       lambda v: win.post('api/airpods', {'action': 'conv', 'on': v}, then=lambda _r: (AP.update(conv_awareness=v), win.update())),
                       'Senkt die Medienlautstärke automatisch ab und verstärkt Stimmen, sobald du sprichst (AirPods Pro 2 / AirPods 4).'),
                toggle('Automatische Ohr-Erkennung', CFG.get('airpods_ear_pause', True),
                       lambda v: config_set(win, airpods_ear_pause=v),
                       'Pausiert Hintergrundmusik automatisch beim Herausnehmen eines AirPods und spielt beim Einsetzen weiter.'),
            ]
        def row(d):
            sub = KIND_NAMES.get(d['kind'], 'Gerät') + (f' · Akku {d["battery"]} %' if d.get('battery') is not None else '')
            if d['paired']:
                return {'k': 'link', 't': d['name'], 'sub': sub, 'icon': d['kind'], 'v': 'verbunden' if d['connected'] else 'nicht verbunden',
                        'fn': lambda d=d: (win.S.update(dev=d['addr']), go_page(win, 'bluetooth>dev')), 'help': 'Verbinden, trennen oder vergessen.'}
            return {'k': 'link', 't': d['name'], 'sub': sub, 'icon': d['kind'], 'v': 'Koppeln', 'fn': bt({'addr': d['addr'], 'do': 'pair'}, 'Kopple ' + d['name'] + ' …'),
                    'help': 'Koppeln und verbinden. Das Gerät muss dazu im Kopplungsmodus sein.'}
        devs = B.get('devices') or []
        mine, near = [row(d) for d in devs if d['paired']], [row(d) for d in devs if not d['paired']]
        return ([(None, top, None)]
                + ([('AirPods (Nativ · AAP)', ap_rows, None)] if ap_rows else [])
                + [('Meine Geräte', mine, None if mine else 'Noch kein Gerät gekoppelt.') if B.get('powered') else (None, [], None),
                   ('Geräte in der Nähe', near or [{'k': 'info', 't': 'Suche …' if B.get('scanning') else 'Keine gefunden', 'v': '', 'help': 'Gerät in den Kopplungsmodus bringen und „Nach Geräten suchen“ wählen.'}],
                    'Kopfhörer werden nach dem Verbinden sofort die Tonausgabe. Ein Gamepad ist in den Emulatoren der nächste Controller (Spieler 2).') if B.get('powered') else (None, [], None)])
    if page == 'bluetooth>dev':
        d = next((d for d in (win.__dict__.get('BT') or {}).get('devices') or [] if d['addr'] == win.S.get('dev')), None)
        if d is None: return [(None, [{'k': 'info', 't': 'Gerät nicht gefunden', 'v': '', 'help': ''}], None)]
        act = lambda what, text: lambda: (win.toast(text), win.post('api/bluetooth', {'addr': d['addr'], 'do': what}, then=lambda r: (r and r.get('error') and win.toast(r['error']), setattr(win, 'bt_at', 0))))
        info = [{'k': 'info', 't': d['name'], 'sub': KIND_NAMES.get(d['kind'], 'Gerät'), 'icon': d['kind'], 'v': 'verbunden' if d['connected'] else 'nicht verbunden', 'help': 'Adresse ' + d['addr'] + '.'}]
        if d.get('battery') is not None: info.append({'k': 'info', 't': 'Akku', 'v': f'{d["battery"]} %', 'help': 'Ladestand, wie das Gerät ihn meldet.'})
        acts = [{'k': 'button', 't': 'Trennen' if d['connected'] else 'Verbinden', 'fn': act('disconnect', 'Trenne …') if d['connected'] else act('connect', 'Verbinde …'),
                 'help': 'Die Verbindung trennen; das Gerät bleibt gekoppelt.' if d['connected'] else 'Mit dem gekoppelten Gerät verbinden. Es muss eingeschaltet sein.'},
                {'k': 'button', 't': 'Gerät vergessen', 'warn': True, 'fn': lambda: (act('forget', 'Vergesse …')(), key(win, 'back')),
                 'help': 'Entfernt die Kopplung. Zum erneuten Verbinden muss das Gerät wieder gekoppelt werden.'}]
        return [(None, info, None), (None, acts, None)]
    if page == 'accounts':
        ask = lambda key: lambda: win.ask_account(key)
        def _start_qr(force=False):
            win.yt_qr_at = time.time()
            def _got(r):
                if not r: return win.toast('Tandem-Dienst antwortet nicht.')
                if r.get('error'): return win.toast(r['error'])
                if r.get('signed_in'): win.YT_QR = None; win.toast('Bei YouTube angemeldet.')
                else: win.YT_QR = r
                win.update()
            win.post('api/ytlogin', {'a': 'qr_new' if force else 'qr'}, then=_got)
        qrd = win.__dict__.get('YT_QR')
        if CFG.get('yt_set'):
            yt_rows = [{'k': 'info', 't': 'Konto', 'v': 'angemeldet', 'help': 'Deine Abos, Playlists und „Mag ich“ stehen in der YouTube-App bereit.'},
                       {'k': 'button', 't': 'YouTube abmelden', 'warn': True,
                        'fn': lambda: win.post('api/ytlogin', {'a': 'logout'}, then=lambda r: (setattr(win, 'YT_QR', None), win.toast((r or {}).get('error') or 'Abgemeldet.'), win.update())),
                        'help': 'Entfernt die gespeicherte YouTube-Anmeldung vom Thor.'}]
        elif qrd and qrd.get('code'):
            yt_rows = [{'k': 'qr', 't': 'Bei YouTube anmelden', 'code': qrd['code'], 'link': qrd.get('link') or 'youtube.com/activate', 'qr': qrd['qr'],
                        'help': 'QR-Code mit dem Handy scannen (der Code ist schon vorausgefüllt) – oder youtube.com/activate öffnen und diesen Code eingeben.'},
                       {'k': 'button', 't': 'Neuer Code', 'fn': lambda: _start_qr(True), 'help': 'Fordert einen frischen Anmeldecode von Google an.'},
                       {'k': 'button', 't': 'Abbrechen', 'fn': lambda: (setattr(win, 'YT_QR', None), win.update()), 'help': 'Schließt die QR-Anzeige.'}]
        else:
            yt_rows = [{'k': 'button', 't': 'Per QR-Code anmelden', 'v': 'nicht angemeldet', 'fn': lambda: _start_qr(False),
                        'help': 'Zeigt einen QR-Code und Anmeldecode zum bequemen Bestätigen am Handy oder PC – ganz ohne Tippen auf dem Thor.'}]
        return [('YouTube', yt_rows, 'Liest nur Abos, Playlists und „Mag ich“; Videos laufen weiter ohne Konto.'),
                ('RetroAchievements', [{'k': 'link', 't': 'Benutzername', 'v': CFG.get('ra_user') or 'kein Konto', 'fn': ask('ra_user'), 'bottom': True, 'help': 'Dein Name bei retroachievements.org. Eingetippt wird unten.'},
                                       {'k': 'link', 't': 'Anmelden', 'v': 'angemeldet' if CFG.get('ra_login') else 'Passwort eingeben', 'fn': ask('ra_password'), 'bottom': True,
                                        'help': 'Das Passwort wird nur zum Anmelden benutzt und nicht gespeichert. Danach sind alle Emulatoren angemeldet.'},
                                       {'k': 'link', 't': 'Web-API-Schlüssel', 'v': 'hinterlegt' if CFG.get('ra_key_set') else 'fehlt', 'fn': ask('ra_key'), 'bottom': True,
                                        'help': 'Damit zeigt Tandem während des Spiels deine Erfolge. Zu finden auf retroachievements.org unter Einstellungen.'}],
                 'Der Hardcore-Modus bleibt aus, damit Speicherstände funktionieren.'),
                ('Battle.net (WoW Forever)', [{'k': 'link', 't': 'E-Mail', 'v': 'hinterlegt' if CFG.get('bnet_set') else 'eintragen', 'fn': ask('bnet_email'), 'bottom': True,
                                               'help': 'Deine Battle.net-E-Mail. WoW Forever meldet sich damit beim Start selbst an, wie unter Android.'},
                                              {'k': 'link', 't': 'Passwort', 'v': 'hinterlegt' if CFG.get('bnet_set') else 'eintragen', 'fn': ask('bnet_password'), 'bottom': True,
                                               'help': 'Bleibt nur auf dem Thor. Beim Start liegt es kurz in login.txt im Spielordner und wird nach der Anmeldung überschrieben und gelöscht.'}]
                 + ([{'k': 'button', 't': 'Anmeldung vergessen', 'v': '', 'fn': lambda: win.post('api/config', {'bnet_forget': True}, then=lambda c: c and setattr(win, 'CFG', c)),
                      'help': 'Löscht E-Mail und Passwort von Battle.net vom Thor.'}] if CFG.get('bnet_set') else []),
                 'Den Code aus der Authenticator-App tippst du im Spiel ein, falls gefragt.'),
                ('Weitere', [{'k': 'info', 't': 'Steam', 'v': 'über Apps › Steam starten', 'help': 'Steam läuft als eigene Sitzung; danach startet wieder Tandem.'},
                             {'k': 'info', 't': 'Plex', 'v': 'angemeldet' if CFG.get('plex_set') else 'über Apps › Plex', 'help': 'Anmeldung direkt in der Plex-App unter Apps.'}], None)]
    if page == 'look':
        rows = [{'k': 'check', 't': t['name'], 'on': t['id'] == ui.THEME['id'], 'fn': lambda t=t: set_theme(win, t['id']), 'help': 'Farben und Stil der Oberfläche auf beiden Bildschirmen.'}
                for t in CFG.get('themes') or []]
        disp = [choice('Ansicht', [('grid', 'Kacheln'), ('stage', 'Bühne')], CFG.get('view_mode') or 'grid',
                       lambda v: config_set(win, view_mode=v),
                       'Kacheln zeigt ein 5-Spalten-Raster; Bühne präsentiert die Spiele groß in der Mitte als gleitendes Karussell.'),
                toggle('Plattform-Rahmen', CFG.get('overlays', True), lambda v: (win.comp_cache.clear(), config_set(win, overlays=v)),
                       'Legt farbige Konsolen-Rahmen und Plattform-Abzeichen (Cocoon) um die Spiele-Cover.'),
                choice('Animationen', [('full', 'Flüssig'), ('reduced', 'Reduziert')], CFG.get('motion') or 'full',
                       lambda v: config_set(win, motion=v),
                       'Flüssige Übergänge für Cover, Fokusring und Karussell, oder reduzierte Bewegung.')]
        return [('Darstellung', disp, None),
                ('Thema', rows, 'Die Hervorhebung nimmt im Spiel die Farbe des Covers an, wenn das Thema es vorsieht.'),
                ('Sprache', [choice('Sprache / Language', [('de', 'Deutsch'), ('en', 'English')], CFG.get('lang') or 'de', lambda v: config_set(win, lang=v),
                                    'Sprache der Oberfläche auf beiden Bildschirmen und der Einstellungsseite. Spiele bleiben, wie sie sind.')], None)]
    if page == 'library':
        played_map = win.L.get('played') or {}
        total_secs = sum(int(p.get('secs') or 0) for p in played_map.values() if isinstance(p, dict))
        rows = [{'k': 'info', 't': 'Spiele', 'v': str(len(win.L['games'])), 'help': 'Alle Spiele, die Tandem gefunden hat.'},
                {'k': 'link', 't': 'Spielzeit & Statistik', 'v': ui.hours(total_secs) if total_secs else 'noch nichts gespielt',
                 'fn': lambda: go_page(win, 'library>stats'), 'help': 'Gesamtspielzeit, letzte 7 Tage und deine meistgespielten Spiele auf dem Thor.'},
                {'k': 'info', 't': 'Spieleordner', 'v': 'ROMs/<System>', 'help': 'Spiele gehören in einen Ordner „ROMs“ auf der Karte oder im Gerät, je System ein Unterordner (wie bei ES-DE).'},
                {'k': 'button', 't': 'Neu einlesen und Cover laden', 'fn': lambda: win.start({'id': 'rescan', 's': 'app'}), 'help': 'Sucht neue Spiele und lädt fehlende Cover aus dem Netz.'}]
        SV = win.SAVES or {}
        snaps = SV.get('snapshots') or []
        sv_state = f'{ui.ago(SV["last"])} ({SV.get("where") or "lokal"})' if SV.get('last') else 'noch keine Sicherung'
        sv_rows = [{'k': 'info', 't': 'Letzte Sicherung', 'v': sv_state, 'help': 'Sichert Spielstände aller Emulatoren, Ports und BananaNative auf Karte und Server.'},
                   {'k': 'button', 't': 'Spielstände jetzt sichern', 'fn': lambda: (win.toast('Sichere Spielstände …'), win.post('api/saves')),
                    'help': 'Legt ein Archiv auf der Karte an und überträgt die Spielstände per SSH.'},
                   {'k': 'link', 't': 'Wiederherstellen', 'v': f'{len(snaps)} Archive' if snaps else 'keine Archive',
                    'fn': lambda: go_page(win, 'library>restore'), 'help': 'Älteren Spielstand aus den lokalen Sicherungsarchiven zurückspielen (legt vorher automatisch eine Sicherung an).'},
                   toggle('Automatisch sichern', CFG.get('save_auto', True), lambda v: config_set(win, save_auto=v),
                          'Sichert Spielstände im Hintergrund nach jedem beendeten Spiel.'),
                   toggle('Echtzeit-Cloud-Saves (vor Start laden)', CFG.get('cloud_saves', True), lambda v: config_set(win, cloud_saves=v),
                          'Prüft beim Spielstart in < 1 Sekunde ohne Hintergrund-Prozess (0 MB RAM), ob auf deinem Server ein neuerer Spielstand vom PC/Mac liegt, und lädt ihn mit lokalem Konflikt-Backup.'),
                   {'k': 'link', 't': 'Sicherungsziel', 'v': CFG.get('save_target') or 'nur Karte', 'fn': win.ask_save_target, 'bottom': True,
                    'help': 'SSH-Ziel im Heimnetz (z. B. benutzer@server:~/backups/thor-saves). Leer lassen für reine Kartensicherung.'}]
        SB = getattr(win, 'SYSBK', None) or {}
        BK = SB.get('backups') or {}
        ST = SB.get('storage') or {}
        bk_job = BK.get('job') or {}
        bk_val = (bk_job.get('step') if bk_job.get('running')
                  else f'{ui.ago(BK["last"])} ({BK.get("last_where") or "lokal"})' if BK.get('last')
                  else f'{len(BK.get("archives") or [])} Archive' if BK.get('archives') else 'bereit')
        st_val = (f'{round(ST["linux_total_gib"])} / {round(ST["android_gib"])} GiB'
                  if ST.get('supported') else 'prüfe …')
        CL = SB.get('cleanup') or {}
        cl_mb = float(CL.get('total_mb') or 0)
        cl_val = (f'{cl_mb / 1024:.1f} GB frei machen'.replace('.', ',') if cl_mb >= 1024
                  else f'{round(cl_mb)} MB frei machen' if cl_mb >= 1 else 'sauber')
        CMP = SB.get('compress') or {}
        cmp_job = CMP.get('job') or {}
        cmp_cnt = int(CMP.get('count') or 0)
        cmp_save = float(CMP.get('est_save_mb') or 0)
        cmp_val = (cmp_job.get('step') if cmp_job.get('running')
                   else (f'~{cmp_save / 1024:.1f} GB sparen'.replace('.', ',') if cmp_save >= 1024 else f'{cmp_cnt} Discs (~{round(cmp_save)} MB)') if cmp_cnt else 'optimal gepackt')
        sys_rows = [
            {'k': 'link', 't': 'Speicher-Bereinigung', 'v': cl_val,
             'fn': lambda: go_page(win, 'library>cleanup'),
             'help': 'Findet verwaiste Steam-Proton-Prefixe deinstallierter Spiele, alte Shader-Caches und Papierkorb-Reste – ohne jemals Spielstände oder installierte Spiele anzufassen.'},
            {'k': 'link', 't': 'Spiele schrumpfen (CHD / RVZ)', 'v': cmp_val,
             'fn': lambda: go_page(win, 'library>compress'),
             'help': 'Wandelt große .iso- und .bin/.cue-Spiele (PS1, PS2, PSP, Dreamcast, Saturn, GameCube, Wii) verlustfrei in .chd bzw. .rvz um – spart 40–65 % Platz bei 0 MB Hintergrund-RAM im Spiel.'},
            {'k': 'link', 't': 'Linux- & Tandem-Backup', 'v': bk_val,
             'fn': lambda: go_page(win, 'library>sysbackup'),
             'help': 'Integriertes System-Backup für Tandem, Emulatoren, Begleiter-Pakete, Ports und das komplette Linux-Home auf SD-Karte und SSH-Server.'},
            {'k': 'link', 't': 'Android- & Linux-Speicher', 'v': st_val,
             'fn': lambda: go_page(win, 'library>storage'),
             'help': 'Interne UFS-Aufteilung ansehen und die Android-Partition nachträglich verkleinern, um live mehr internen Speicher für Tandem und Linux zu gewinnen.'},
        ]
        store = [{'k': 'info', 't': s['name'], 'v': f'{round(s["free"] / 1e9)} von {round(s["total"] / 1e9)} GB frei', 'help': 'Freier Platz.'} for s in SYS.get('storage') or []]
        return [(None, rows, None), ('System & interner Speicher', sys_rows, None), ('Spielstände', sv_rows, None), ('Speicher', store, None)]
    if page == 'library>cleanup':
        SB = getattr(win, 'SYSBK', None) or {}
        CL = SB.get('cleanup')
        if CL is None:
            return loading
        def _fmt_sz(mb):
            mb = float(mb or 0)
            if mb >= 1024: return f'{mb / 1024:.1f} GB'.replace('.', ',')
            if mb >= 1: return f'{round(mb)} MB'
            return '0 MB'
        def _clean(which):
            win.toast('Bereinige Speicher …')
            win.post('api/sysbackup', {'action': 'cleanup', 'which': which},
                     then=lambda r: (setattr(win, 'sysbk_at', 0),
                                     win.toast('Keine Antwort.' if r is None else r.get('error') or r.get('text', '')),
                                     win.update()))
        c_comp = CL.get('compatdata') or {}
        c_shd = CL.get('shadercache') or {}
        c_tmp = CL.get('trash') or CL.get('temp') or {}
        tot_mb = float(CL.get('total_mb') or 0)
        ov_c = [
            {'k': 'info', 't': 'Freigebbarer Speicher', 'v': _fmt_sz(tot_mb),
             'help': 'Gesamter Speicherplatz aus verwaisten Proton-Prefixen, alten Shader-Caches und Papierkorb-Resten.'},
            {'k': 'info', 't': 'Verwaiste Proton-Prefixe', 'v': f'{c_comp.get("count", 0)} · {_fmt_sz(c_comp.get("mb", 0))}',
             'sub': ', '.join((c_comp.get('items') or [])[:5]),
             'help': 'Übriggebliebene compatdata-Ordner bereits deinstallierter Steam-Spiele (installierte Spiele & Shortcuts bleiben 100 % geschützt).'},
            {'k': 'info', 't': 'Alte Steam-Shader-Caches', 'v': f'{c_shd.get("count", 0)} · {_fmt_sz(c_shd.get("mb", 0))}',
             'help': 'Nicht mehr benötigte Vulkan-Shader-Caches deinstallierter Titel.'},
            {'k': 'info', 't': 'Papierkorb & Temp-Reste', 'v': _fmt_sz(c_tmp.get('mb', 0)),
             'help': 'Dateien im Linux-Papierkorb, abgebrochene .part-Downloads und alte Crash-Dumps.'},
        ]
        act_c = [
            {'k': 'button', 't': 'Alles sicher bereinigen', 'v': _fmt_sz(tot_mb) if tot_mb >= 1 else 'sauber',
             'fn': lambda: _clean('all'),
             'help': 'Räumt verwaiste Proton-Prefixe, alte Shader-Caches und Papierkorb-Reste in einem Durchgang auf. Spielstände werden niemals gelöscht.'},
        ]
        if c_comp.get('count'):
            act_c.append({'k': 'button', 't': 'Nur verwaiste Proton-Prefixe löschen', 'v': _fmt_sz(c_comp.get('mb', 0)),
                          'fn': lambda: _clean('compatdata'),
                          'help': 'Entfernt nur übriggebliebene compatdata-Ordner deinstallierter Spiele.'})
        if c_shd.get('count'):
            act_c.append({'k': 'button', 't': 'Nur alte Shader-Caches löschen', 'v': _fmt_sz(c_shd.get('mb', 0)),
                          'fn': lambda: _clean('shadercache'),
                          'help': 'Entfernt nur nicht mehr benötigte Steam-Shader-Caches.'})
        if float(c_tmp.get('mb') or 0) >= 0.5:
            act_c.append({'k': 'button', 't': 'Papierkorb & Temp leeren', 'v': _fmt_sz(c_tmp.get('mb', 0)),
                          'fn': lambda: _clean('temp'),
                          'help': 'Leert den Papierkorb und temporäre Download-Reste.'})
        return [('Analyse', ov_c, None),
                ('Bereinigen', act_c, 'Installierte Spiele, Shortcuts, Emulatoren und Spielstände bleiben unangetastet.')]
    if page == 'library>compress':
        SB = getattr(win, 'SYSBK', None) or {}
        CMP = SB.get('compress') or {}
        job = CMP.get('job') or {}
        items_c = CMP.get('items') or []
        est_mb = float(CMP.get('est_save_mb') or 0)
        est_lbl = f'~{est_mb / 1024:.1f} GB'.replace('.', ',') if est_mb >= 1024 else f'~{round(est_mb)} MB'
        ov_cmp = [
            {'k': 'info', 't': 'Unkomprimierte Disc-Spiele', 'v': str(CMP.get('count', 0)),
             'help': 'Gefundene .bin/.cue-, .gdi-, .iso- und .gcm-Abbilder auf SD-Karte und internem Speicher.'},
            {'k': 'info', 't': 'Geschätzte Ersparnis', 'v': est_lbl if items_c else '0 MB',
             'help': 'CHD (PS1/PS2/PSP/Dreamcast/Saturn) und RVZ (GameCube/Wii) sind 100 % verlustfrei und laden in Emulatoren direkt.'},
        ]
        if job.get('running'):
            ov_cmp.append({'k': 'info', 't': 'Aktiver Vorgang', 'v': job.get('step') or 'läuft …',
                           'help': 'Läuft auf 2 Silberkernen mit minimalem RAM-Bedarf.'})
        act_cmp = [
            {'k': 'button', 't': 'Alle verlustfrei in CHD / RVZ umwandeln',
             'v': est_lbl if items_c else 'alles gepackt',
             'fn': lambda: (win.toast('Starte CHD/RVZ-Komprimierung …'),
                            win.post('api/sysbackup', {'action': 'compress_roms'},
                                     then=lambda r: (setattr(win, 'sysbk_at', 0),
                                                     r and win.toast(r.get('error') or r.get('text', '')),
                                                     win.update()))),
             'help': 'Prüft jedes erzeugte .chd/.rvz per Verify-Check, bevor das unkomprimierte Original ersetzt wird (läuft nur außerhalb von Spielen = 0 MB RAM-Verbrauch beim Zocken).'},
        ]
        item_rows = [{'k': 'info', 't': it['name'], 'v': f'{it["mb"]:g} MB → .{it["target"].split("-")[0]}',
                      'sub': it['sys'].upper(), 'help': it['path']} for it in items_c[:15]]
        return [('Übersicht', ov_cmp, None), ('Aktion', act_cmp, None)] + ([('Gefundene Discs', item_rows, None)] if item_rows else [])
    if page == 'library>sysbackup':
        SB = getattr(win, 'SYSBK', None) or {}
        BK = SB.get('backups') or {}
        job = BK.get('job') or {}
        arcs = BK.get('archives') or []
        dest_lbl = ('SD-Karte' if BK.get('dest_on_card') else 'Intern') + (f' ({BK.get("dest_free_gib", 0):g} GiB frei)' if BK.get('dest_free_gib') else '')
        ssh_lbl = CFG.get('save_target') or 'aus (unter Bibliothek › Sicherungsziel)'
        def _start_bk(mode):
            win.post('api/sysbackup', {'action': 'backup', 'mode': mode},
                     then=lambda r: (setattr(win, 'sysbk_at', 0),
                                     win.toast('Keine Antwort.' if r is None else r.get('error') or r.get('text', '')),
                                     win.update()))
        top_rows = [
            {'k': 'info', 't': 'Lokales Ziel', 'v': dest_lbl, 'sub': BK.get('dest') or '',
             'help': 'Archive werden mit zstd gepackt (.tar.zst), sodass Linux-Rechte und Symlinks auch auf exFAT-SD-Karten 100 % erhalten bleiben.'},
            {'k': 'info', 't': 'SSH-Spiegelziel', 'v': ssh_lbl,
             'help': 'Ist ein SSH-Ziel eingetragen, überträgt Tandem das Backup zusätzlich per rsync auf deinen Server.'},
        ]
        if job.get('running'):
            top_rows.append({'k': 'info', 't': 'Aktiver Vorgang', 'v': job.get('step') or 'läuft …',
                             'help': 'Die Sicherung läuft im Hintergrund weiter.'})
        elif job.get('error'):
            top_rows.append({'k': 'info', 't': 'Letzter Status', 'v': 'Fehler', 'sub': job['error'][:90], 'help': job['error']})
        act_rows = [
            {'k': 'button', 't': 'System-Profil jetzt sichern', 'v': 'empfohlen (~1–4 GB)',
             'fn': lambda: _start_bk('profile'),
             'help': 'Sichert Tandem, alle GBA-Begleiter, Ports, BananaNative/Peanuts, Emulatoren, BIOS, Switch-Keys, Steam-Shortcuts, SSH und alle Spielstände.'},
            {'k': 'button', 't': 'Komplett-Backup 1:1 starten', 'v': 'ganzes Linux-Home',
             'fn': lambda: _start_bk('full'),
             'help': 'Sichert dein gesamtes /var/home/armada inklusive installierter Spiele (ohne regenerierbare Shader-Caches) auf SD-Karte bzw. SSH-Server.'},
        ]
        arc_rows = [{
            'k': 'button',
            't': ('Komplett · ' if a.get('kind') == 'full' else 'Profil · ') + time.strftime('%d.%m.%Y · %H:%M', time.localtime(a['at'])),
            'v': f'{a.get("size_gb", 0):g} GB',
            'sub': a.get('file', ''),
            'bottom': True,
            'fn': lambda fn=a['file']: win.ask_restore_sysbackup(fn),
            'help': 'Spielt dieses Linux- & Tandem-Backup zurück (bestätigt durch „JA“ unten; aktuelle Spielstände werden vorher automatisch gesichert).',
        } for a in arcs]
        return [('Übersicht', top_rows, None),
                ('Neue Sicherung anlegen', act_rows, None),
                ('Vorhandene System-Archive', arc_rows or [{'k': 'info', 't': 'Noch kein System-Archiv vorhanden', 'v': '', 'help': 'Starte oben ein System-Profil- oder Komplett-Backup.'}],
                 'Vor jedem Zurückspielen sichert Tandem automatisch alle aktuellen Spielstände.')]
    if page == 'library>storage':
        SB = getattr(win, 'SYSBK', None) or {}
        ST = SB.get('storage') or {}
        if not ST:
            return loading
        if not ST.get('supported'):
            return [(None, [{'k': 'info', 't': 'Nicht verfügbar', 'v': '', 'sub': ST.get('reason', ''), 'help': ST.get('reason', '')}], None)]
        job = ST.get('job') or {}
        cur_and = ST.get('android_gib', 0)
        lin_tot = ST.get('linux_total_gib', 0)
        lin_free = ST.get('linux_free_gib', 0)
        ov_rows = [
            {'k': 'info', 't': 'Interner UFS-Speicher', 'v': f'{ST.get("total_gib", 0):g} GiB',
             'sub': f'{ST.get("disk", "")} · Sektorgröße {ST.get("sector_size", 4096)} B',
             'help': 'Gesamter interner UFS-4.0-Speicher des AYN Thor.'},
            {'k': 'info', 't': 'Linux & Tandem (Btrfs)', 'v': f'{lin_free:g} von {lin_tot:g} GiB frei',
             'sub': ('Erweitert: ' + ', '.join(ST['extra_chunks'])) if ST.get('extra_chunks') else 'Standard-Partition ARMADA_ROOT',
             'help': 'Dein interner Speicher für ArmadaOS Linux, Tandem, native Ports und Spiele (/var/home).'},
            {'k': 'info', 't': 'Android (userdata)', 'v': f'{cur_and:g} GiB',
             'sub': f'{ST.get("userdata_node", "")} · bis auf {ST.get("android_min_gib", 8)} GiB verkleinerbar',
             'help': 'Die Android-Nutzerpartition ist unter Linux ausgehängt und kann nachträglich im laufenden Betrieb verkleinert werden.'},
        ]
        if job.get('running'):
            ov_rows.append({'k': 'info', 't': 'Aktiver Vorgang', 'v': job.get('step') or 'läuft …',
                            'help': 'Partitionierung und Btrfs-Erweiterung laufen im Hintergrund.'})
        elif job.get('error'):
            ov_rows.append({'k': 'info', 't': 'Letzter Status', 'v': 'Fehler', 'sub': job['error'][:90], 'help': job['error']})
        presets = ST.get('presets_gib') or []
        p_rows = [{
            'k': 'button',
            't': f'Android auf {g} GiB verkleinern',
            'v': f'+{max(1, round(cur_and - g))} GiB für Linux',
            'sub': f'Linux wächst live auf ~{round(lin_tot + max(0, cur_and - g))} GiB',
            'warn': True,
            'bottom': True,
            'fn': lambda g=g: win.ask_shrink_android(g),
            'help': 'Sichert zuerst automatisch GPT & Spielstände, verkleinert Android userdata ohne Neuinstallation und bindet den freien Platz sofort live per Btrfs in /var/home ein. ACHTUNG: Android-Nutzerdaten (Apps/Daten unter Android) werden dabei zurückgesetzt!',
        } for g in presets]
        return [('Aktuelle Aufteilung', ov_rows, None),
                ('Android nachträglich verkleinern (live)',
                 p_rows or [{'k': 'info', 't': 'Android ist bereits minimal', 'v': f'{cur_and:g} GiB',
                             'help': 'Die Android-Partition ist bereits auf dem Minimum.'}],
                 'Wichtig: Deine Linux-Installation, Tandem und alle Spiele bleiben komplett erhalten; nur die Android-Nutzerdaten werden auf Werkseinstellung gesetzt.')]
    if page == 'library>stats':
        played_map = win.L.get('played') or {}
        sessions = win.L.get('sessions') or {}
        games_by_id = {g['id']: g for g in (win.L.get('games') or []) + (win.L.get('apps') or [])}
        total_secs = sum(int(p.get('secs') or 0) for p in played_map.values() if isinstance(p, dict))
        played_cnt = sum(1 for p in played_map.values() if isinstance(p, dict) and int(p.get('secs') or 0) > 0)
        now = time.time()
        wdays = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')
        day_rows, week_secs = [], 0
        for d in range(6, -1, -1):
            tm = time.localtime(now - d * 86400)
            key_d = time.strftime('%Y-%m-%d', tm)
            ds = int(sessions.get(key_d) or 0)
            week_secs += ds
            lbl = 'Heute' if d == 0 else 'Gestern' if d == 1 else f'{wdays[tm.tm_wday]}, {tm.tm_mday:02d}.{tm.tm_mon:02d}.'
            day_rows.append({'k': 'info', 't': lbl, 'v': ui.hours(ds) if ds > 0 else '–', 'help': f'Spielzeit am {key_d}.'})
        summary = [{'k': 'info', 't': 'Gesamtspielzeit', 'v': ui.hours(total_secs) if total_secs else '0 Min.', 'help': 'Aufgezeichnete Spielzeit über alle Spiele auf dem Thor.'},
                   {'k': 'info', 't': 'Letzte 7 Tage', 'v': ui.hours(week_secs) if week_secs else '0 Min.', 'help': 'Spielzeit in den letzten sieben Tagen.'},
                   {'k': 'info', 't': 'Gespielte Titel', 'v': f'{played_cnt} von {len(win.L.get("games") or [])}', 'help': 'Wie viele Spiele deiner Bibliothek bereits gestartet wurden.'}]
        ranked = sorted(((gid, p) for gid, p in played_map.items() if isinstance(p, dict) and int(p.get('secs') or 0) > 0),
                        key=lambda kv: int(kv[1].get('secs') or 0), reverse=True)[:10]
        top_rows = [{'k': 'info', 't': (games_by_id.get(gid) or {}).get('t') or gid,
                     'sub': (win.sys_name(games_by_id[gid]) if gid in games_by_id else '') + (f' · zuletzt {ui.ago(p["last"])}' if p.get('last') else ''),
                     'v': ui.hours(int(p.get('secs') or 0)),
                     'help': f'Insgesamt {ui.hours(int(p.get("secs") or 0))} gespielt.'} for gid, p in ranked]
        return [('Übersicht', summary, None),
                ('Meistgespielt', top_rows or [{'k': 'info', 't': 'Noch keine Spiele gespielt', 'v': '', 'help': 'Starte ein Spiel – Tandem zählt die Spielzeit automatisch mit.'}], None),
                ('Letzte 7 Tage', day_rows, None)]
    if page == 'library>restore':
        snaps = (win.SAVES or {}).get('snapshots') or []
        if not snaps:
            return [(None, [{'k': 'info', 't': 'Keine Sicherungsarchive gefunden', 'v': '', 'help': 'Erstelle zuerst unter Bibliothek eine Spielstand-Sicherung.'}], None)]
        def do_restore(arc):
            win.toast('Stelle Spielstände wieder her …')
            win.post('api/saves_restore', {'file': arc['file']},
                     then=lambda r: win.toast('Keine Antwort.' if r is None else r.get('error') or r.get('text', '')))
        r_rows = [{'k': 'button', 't': time.strftime('%d.%m.%Y · %H:%M', time.localtime(s['at'])),
                   'v': f'{len(s.get("items") or [])} Systeme',
                   'sub': ', '.join((s.get('items') or [])[:5]),
                   'fn': lambda s=s: do_restore(s),
                   'help': 'Spielt alle Spielstände dieses Zeitpunkts zurück. Aktuelle Spielstände werden vorher automatisch gesichert.'}
                  for s in snaps]
        return [('Sicherungsarchive (neueste zuerst)', r_rows, 'Vor dem Zurückspielen legt Tandem automatisch eine Sicherheitskopie deiner aktuellen Stände an.')]
    if page == 'updates':
        U = win.UPD or {}
        UC = getattr(win, 'UPDC', None) or {}
        SN = getattr(win, 'SWNAT', None) or {}
        job = UC.get('job') or {}
        comp = UC.get('companions') or {}
        apps = UC.get('appimages') or []
        fps = (UC.get('flatpaks') or {}).get('installed') or []
        pend = int(UC.get('pending_count') or 0)
        upd_status = (job.get('step') if job.get('running')
                      else f'{pend} verfügbar' if pend
                      else f'geprüft {ui.ago(UC["last_check"])}' if UC.get('last_check') else 'bereit')
        rows = [
            {'k': 'info', 't': 'Toravo Tandem', 'v': 'Version ' + str(CFG.get('version', '')),
             'help': 'Installierte Version von Toravo Tandem mit integriertem Update- und Begleiter-Dienst.'},
            {'k': 'button', 't': 'Alles prüfen & aktualisieren', 'v': upd_status,
             'fn': lambda: (win.toast('Starte Voll-Update …'),
                            win.post('api/updater', {'action': 'update_all'},
                                     then=lambda r: (setattr(win, 'updc_at', 0), r and win.toast(r.get('error') or r.get('text', ''))))),
             'help': 'Aktualisiert Spiel-Begleiter (Steam & GBA), ARM64-Emulatoren, fehlende RetroArch-Kerne und Flatpaks in einem Durchgang.'},
            toggle('Automatisch aktuell halten', CFG.get('auto_update', True), lambda v: config_set(win, auto_update=v),
                   'Hält Emulatoren, Kerne und Spiel-Begleiter im Leerlauf vollautomatisch per SHA-256-Prüfung aktuell – mit 1-Tipp-Rollback.'),
            toggle('Begleiter automatisch installieren', CFG.get('auto_companions', True), lambda v: config_set(win, auto_companions=v),
                   'Erkennt installierte Steam-, GBA-, Port- und Dual-Screen-Spiele und richtet passende Begleiter für den unteren Bildschirm automatisch ein.'),
            {'k': 'button', 't': 'Nach Update suchen',
             'fn': lambda: (self_update(win, False),
                            win.post('api/updater', {'action': 'check'}, then=lambda _r: setattr(win, 'updc_at', 0))),
             'v': U.get('text', ''),
             'help': 'Prüft alle Release-Quellen ohne Änderungen auf dem Gerät vorzunehmen.'},
        ]
        if U.get('new'):
            rows.append({'k': 'button', 't': f'Version {U["new"]} installieren', 'fn': lambda: self_update(win, True),
                         'help': 'Installiert die neue Tandem-Version; bei Fehlern greift automatisch das Backup der bisherigen Version.'})
        n_steam = sum(1 for c in (comp.get('steam') or []) if c.get('installed'))
        n_gba = int(comp.get('gba_installed_packs') or 0)
        comp_val = f'{n_steam} Steam · {n_gba} GBA aktiv' if (n_steam or n_gba) else 'bereit'
        inst_apps = sum(1 for a in apps if a.get('installed'))
        pend_apps = sum(1 for a in apps if a.get('update_available')) + len((UC.get('flatpaks') or {}).get('updates') or [])
        apps_val = f'{pend_apps} Update offen' if pend_apps else f'{inst_apps} ARM64 · {len(fps)} Flatpak'
        hub_rows = [
            {'k': 'link', 't': 'Spiel-Begleiter', 'v': comp_val, 'fn': lambda: go_page(win, 'updates>companions'),
             'help': 'Automatisch erkannte und installierte Begleiter für deine Steam-Spiele, Game-Boy-/GBA-Klassiker und nativen PC-Ports.'},
            {'k': 'link', 't': 'Emulatoren & Quellen', 'v': apps_val, 'fn': lambda: go_page(win, 'updates>apps'),
             'help': 'Direkte GitHub-/Forgejo-Quellen für ARM64-AppImages (mit SHA-256-Abgleich & 1-Tipp-Rollback), Flatpaks und eigene Paketquellen.'},
        ]
        out = [(None, rows, 'Quelle: ' + (CFG.get('update_url') or 'keine') if CFG.get('update_url') is not None else None),
               ('Begleiter & Paketquellen', hub_rows, None)]
        if SN.get('banana_version') or SN.get('peanuts_version') or any(g.get('supported') for g in (SN.get('games') or [])):
            nat_rows = [
                {'k': 'link', 't': 'Switch-Spiele nativ umwandeln',
                 'v': (SN.get('job') or {}).get('step') if (SN.get('job') or {}).get('running') else f'{sum(1 for g in (SN.get("games") or []) if g.get("supported"))} kompatibel',
                 'fn': lambda: go_page(win, 'updates>native'),
                 'help': 'Zeigt kompatible Switch-Spiele auf der Karte und wandelt sie direkt auf dem Thor in native Pakete um.'},
            ]
            out.append(('Erweitert', nat_rows, None))
        return out
    if page == 'updates>companions':
        UC = getattr(win, 'UPDC', None) or {}
        comp = UC.get('companions') or {}
        steam_items = comp.get('steam') or []
        ports = comp.get('ports_ready') or []
        top_act = [
            {'k': 'button', 't': 'Alle Begleiter jetzt abgleichen',
             'v': 'läuft …' if (UC.get('job') or {}).get('running') else '',
             'fn': lambda: (win.toast('Prüfe & installiere Spiel-Begleiter …'),
                            win.post('api/updater', {'action': 'sync_companions'},
                                     then=lambda r: (setattr(win, 'updc_at', 0), r and win.toast(r.get('error') or r.get('text', ''))))),
             'help': 'Sucht nach allen installierten Spielen mit Begleiter-Unterstützung und installiert oder aktualisiert deren Plugins & Pakete.'},
        ]
        st_rows = [{
            'k': 'info',
            't': s['title'],
            'v': ('Update ' + s['latest_version']) if s.get('update_available') else (('✓ ' + s['version']) if s.get('installed') else s.get('status', 'bereit')),
            'help': 'Wird direkt im Steam-Spielverzeichnis installiert (mit SHA-256-Prüfung und Backup der Originaldatei).',
        } for s in steam_items] or [{
            'k': 'info', 't': 'Automatische Steam-Erkennung aktiv', 'v': 'bereit',
            'help': 'Sobald FINAL FANTASY IX (Memoria), Fallout 4 oder Persona 5 Royal in Steam installiert sind, lädt Tandem das passende Begleiter-Plugin automatisch.',
        }]
        gba_rows = [
            {'k': 'info', 't': 'GB / GBC / GBA Begleiter-Pakete', 'v': f'{comp.get("gba_installed_packs", 0)} installiert',
             'help': 'Interaktive Zweitbildschirm-Pakete (Karten, Inventar, Team, Breitbild) – werden für deine ROMs automatisch geladen.'},
            {'k': 'info', 't': 'Erkannte Spiele deiner Sammlung', 'v': f'{comp.get("gba_matched_games", 0)} Spiele',
             'help': 'Spiele deiner Bibliothek (inkl. deutscher/europäischer Versionen und ROM-Hacks) mit passendem Begleiter-Paket.'},
            {'k': 'info', 't': 'RetroArch Live-Speicherbrücke', 'v': '✓ UDP 55355 aktiv',
             'help': 'Tandem schaltet den lokalen RetroArch-Netzwerkkanal automatisch frei, damit Begleiter Live-Spieldaten lesen können.'},
        ]
        port_rows = [
            {'k': 'info', 't': 'Native PC-Klassiker (Ports)', 'v': f'{len(ports)} aktiv' if ports else '7 unterstützt',
             'sub': ', '.join(ports[:5]) if ports else 'Half-Life, Age of Kings, Red Alert 2, Heroes III, Diablo II …',
             'help': 'Maßgeschneiderte Touch-Begleiter für native Linux-Ports auf dem unteren Bildschirm.'},
            {'k': 'info', 't': 'Universal-Begleiter', 'v': '✓ Für jedes Spiel',
             'help': 'Visuelle Spielstände, Notiz- & Zeichenblock, Offline-Guides, Musik-Mixer, Maus-Trackpad und Live-Telemetrie in jedem Spiel.'},
        ]
        return [(None, top_act, None), ('Steam-Begleiter', st_rows, None), ('Handheld- & Retro-Begleiter', gba_rows, None), ('PC-Ports & Universal-Deck', port_rows, None)]
    if page == 'updates>apps':
        UC = getattr(win, 'UPDC', None) or {}
        apps = UC.get('appimages') or []
        tp = UC.get('turnip') or {}
        fp = UC.get('flatpaks') or {}
        tp_rows = []
        if tp:
            tp_ver = (f'Update → {tp["latest_version"]}' if tp.get('update_available')
                      else f'✓ {tp["current_version"]}' if tp.get('installed')
                      else ('Installieren (' + tp['latest_version'] + ')' if tp.get('latest_version') else 'Installieren'))
            tp_rows.append({
                'k': 'button',
                't': tp.get('name') or 'Turnip Adreno 740 (Mesa-Git)',
                'v': tp_ver,
                'sub': '~/.local/share/armada/turnip/dd-turnip (ARM64 glibc)',
                'fn': lambda: (win.toast('Lade neuesten Adreno-740-Turnip-Treiber …'),
                               win.post('api/updater', {'action': 'update_app', 'id': 'turnip:dd'},
                                        then=lambda r: (setattr(win, 'updc_at', 0), r and win.toast(r.get('error') or r.get('text', ''))))),
                'help': 'Lädt den aktuellen Mesa-Git-Turnip-Treiber (ARM64 Linux glibc, geprüft per SHA-256 & ELF-Check) für Auswahl unter Leistung › Turnip.',
            })
            if tp.get('has_rollback'):
                tp_rows.append({
                    'k': 'button',
                    't': '↺ Vorheriger Turnip-Treiber',
                    'v': 'Rollback',
                    'fn': lambda: win.post('api/updater', {'action': 'rollback_turnip'},
                                           then=lambda r: (setattr(win, 'updc_at', 0), r and win.toast(r.get('error') or r.get('text', '')))),
                    'help': 'Stellt die vorherige Version (.prev) des heruntergeladenen Turnip-Treibers sofort wieder her.',
                })
        app_rows = []
        for a in apps:
            ver_lbl = (f'Update → {a["latest_version"]}' if a.get('update_available')
                       else f'✓ {a["current_version"]}' if a.get('installed')
                       else 'Installieren')
            app_rows.append({
                'k': 'button',
                't': a['name'],
                'v': ver_lbl,
                'sub': a['file'] + (' · Eigene Quelle' if a.get('custom') else ''),
                'fn': lambda aid=a['id'], nm=a['name']: (
                    win.toast(f'Lade {nm} …'),
                    win.post('api/updater', {'action': 'update_app', 'id': aid},
                             then=lambda r: (setattr(win, 'updc_at', 0), r and win.toast(r.get('error') or r.get('text', ''))))),
                'help': 'Direkter ARM64-AppImage-Bezug von der Originalquelle mit SHA-256-Prüfung und Erhalt deiner Controller-Belegung.',
            })
            if a.get('has_rollback'):
                short_nm = a['name'].split(' (')[0]
                app_rows.append({
                    'k': 'button',
                    't': f'↺ Vorherige Version ({short_nm})',
                    'v': 'Rollback',
                    'fn': lambda aid=a['id']: win.post('api/updater', {'action': 'rollback', 'id': aid},
                                                       then=lambda r: (setattr(win, 'updc_at', 0), r and win.toast(r.get('error') or r.get('text', '')))),
                    'help': 'Stellt mit einem Tipp sofort die vorherige funktionierende AppImage-Version (.prev) wieder her.',
                })
            if a.get('custom'):
                app_rows.append({
                    'k': 'button', 't': f'Quelle entfernen: {a["name"]}', 'warn': True,
                    'fn': lambda aid=a['id']: win.post('api/updater', {'action': 'remove_feed', 'id': aid},
                                                       then=lambda r: (setattr(win, 'updc_at', 0), r and win.toast(r.get('error') or r.get('text', '')))),
                    'help': 'Entfernt diese benutzerdefinierte GitHub-Quelle aus dem Update-Dienst.',
                })
        app_rows.append({
            'k': 'link', 't': '+ Eigene GitHub-Quelle hinzufügen', 'v': 'AppImage', 'fn': win.ask_custom_feed, 'bottom': True,
            'help': 'Beliebiges GitHub-Projekt (Besitzer/Projekt) eintragen – Tandem findet ARM64-AppImages automatisch ohne Regex-Bastelei.',
        })
        fp_rows = [{
            'k': 'info', 't': f['name'],
            'v': 'Update verfügbar' if f.get('update_available') else ('✓ ' + (f.get('version') or 'installiert')),
            'sub': f['ref'],
            'help': 'Wird beim Voll-Update automatisch über Flatpak aktualisiert.',
        } for f in (fp.get('installed') or [])]
        secs_u = []
        if tp_rows:
            secs_u.append(('Adreno 740 Grafiktreiber (Turnip Mesa-Git)', tp_rows, 'Wird nach der Installation automatisch unter Leistung › Turnip & im Quick Menu wählbar.'))
        secs_u.extend([
            ('ARM64 AppImages (Direkt-Quellen)', app_rows, 'Vor jedem Update wird die bisherige Datei als .prev für einen 1-Tipp-Rollback aufgehoben.'),
            ('Flatpak-Emulatoren', fp_rows or [{'k': 'info', 't': 'Keine Flatpak-Emulatoren erkannt', 'v': '', 'help': ''}], None),
        ])
        return secs_u
    if page == 'updates>native':
        SN = getattr(win, 'SWNAT', None) or {}
        job = SN.get('job') or {}
        j_rows = []
        if job.get('running'):
            j_rows.append({'k': 'info', 't': job.get('title', ''), 'v': job.get('step', 'läuft …'), 'help': 'Umwandlung läuft im Hintergrund weiter.'})
        elif job.get('error'):
            j_rows.append({'k': 'info', 't': 'Letzter Lauf', 'v': 'Fehler', 'sub': job['error'][:80], 'help': job['error']})
        cand = [g for g in (SN.get('games') or []) if g.get('supported')]
        c_rows = [{
            'k': 'button',
            't': g['t'],
            'v': '✓ Nativ bereit' if g.get('converted') else ('Umwandeln' if g.get('host_ready') else 'Profil bereit'),
            'sub': ('Mit Begleiter · ' if g.get('companion') else '') + ('Update erkannt' if g.get('has_update') else 'Basis-Dump'),
            'fn': lambda gid=g['id']: win.post('api/switch_native', {'id': gid},
                                               then=lambda r: (setattr(win, 'swnat_at', 0), r and win.toast(r.get('error') or r.get('text', '')))),
            'help': 'Startet die native ARM64- & Vulkan-Shader-Umwandlung im Hintergrund (dauert je nach Spiel ca. 5–25 Min.).',
        } for g in cand]
        return ([('Aktiver Auftrag', j_rows, None)] if j_rows else []) + [
            ('Kompatible Switch-Spiele auf deinem Thor', c_rows or [{'k': 'info', 't': 'Keine passenden Switch-Spiele gefunden', 'v': '', 'help': 'Lege .nsp- oder .xci-Dateien in ROMs/switch ab.'}],
             'Updates (.nsp) kannst du optional im Web-Dashboard unter Bibliothek › Switch-Update hochladen.')]
    if page == 'about':
        B = win.BATT
        ai_rows = [
            {'k': 'button', 't': 'Claude Code starten (Skip Permissions)', 'v': 'Autonom',
             'fn': lambda: win.start({'id': 'ai:claude', 's': 'app'}),
             'help': 'Startet Claude Code direkt mit --dangerously-skip-permissions oben und der KI-Schnellleiste + Tastatur unten.'},
            {'k': 'button', 't': 'Google Antigravity (agy) starten (Skip Permissions)', 'v': 'Autonom',
             'fn': lambda: win.start({'id': 'ai:agy', 's': 'app'}),
             'help': 'Startet Google Antigravity CLI (agy) direkt mit --dangerously-skip-permissions oben und der KI-Tastatur unten.'},
            {'k': 'link', 't': 'KI-Arbeitsordner', 'v': CFG.get('ai_workdir') or 'Home (~)', 'fn': win.ask_ai_workdir, 'bottom': True,
             'help': 'Standard-Projektverzeichnis, in dem Claude Code und Google Antigravity (agy) beim Start geöffnet werden.'},
        ]
        return [(None, [{'k': 'info', 't': 'Gerät', 'v': 'AYN Thor', 'help': 'Zwei Bildschirme, oben das Spiel, unten die Bedienung.'},
                        {'k': 'info', 't': 'ArmadaOS', 'v': (T or {}).get('os') or '–', 'help': 'Das Betriebssystem. Updates dafür kommen über Steam oder den Desktop.'},
                        {'k': 'info', 't': 'Tandem', 'v': 'Version ' + str(CFG.get('version', '')), 'help': 'Toravo Tandem, die Oberfläche für beide Bildschirme.'}] +
                 ([{'k': 'info', 't': 'Akku', 'v': f'{B["level"]} %', 'help': 'Ladestand des Akkus.'}] if B else []), None),
                ('KI-Agenten auf dem Thor', ai_rows, 'Beide Agenten laufen nativ unter ARM64-Linux ohne Rückfrage-Sperren (--dangerously-skip-permissions).'),
                (None, [{'k': 'button', 't': 'Einrichtung erneut zeigen', 'fn': lambda: win.post('api/setup', {'open': True}), 'help': 'Zeigt die vier Schritte vom ersten Start: Spiele, Emulatoren, Netz und Konto.'}], None)]
    if page == 'onoff':
        texts = {'suspend': 'Der Thor schläft und wacht mit der Ein-Taste sofort wieder auf.',
                 'sleep': 'Legt den Thor auch am Ladegerät ganz schlafen.',
                 'reboot': 'Startet den Thor neu.', 'poweroff': 'Schaltet den Thor aus.',
                 'desktop': 'Wechselt zum KDE-Desktop. Zurück geht es über „Zurück zu Tandem“ auf dem Desktop.'}
        return [(None, [{'k': 'button', 't': ui.POWER[n][1], 'warn': n in ('reboot', 'poweroff'), 'fn': lambda n=n: win.confirm_action(n), 'help': texts[n] + ' Tandem fragt vorher.'}
                        for n in ui.POWER], 'Kurzer Druck auf die Ein-Taste versetzt den Thor direkt in den Standby; langes Halten öffnet das Ein-/Aus-Menü.')]
    return []


def toggle(label, on, set_, help):
    return {'k': 'toggle', 't': label, 'on': bool(on), 'fn': lambda: set_(not on), 'adj': lambda d: set_(d > 0) if (d > 0) != bool(on) else None, 'help': help}


def choice(label, opts, cur, set_, help):
    ids = [o[0] for o in opts]
    n = ids.index(cur) if cur in ids else 0
    return {'k': 'choice', 't': label, 'opts': opts, 'cur': cur, 'set': set_, 'help': help, 'fn': lambda: set_(ids[(n + 1) % len(ids)]),
            'adj': lambda d: set_(ids[n + d]) if 0 <= n + d < len(ids) else None}


def set_theme(win, name):
    win.set_theme(name)
    config_set(win, theme=name)


def apply_controls(win):
    win.toast('Gleiche an …')
    def done(r):
        win.toast('Keine Antwort.' if r is None else r.get('error') or r.get('text', ''))
        win.CTRL = None  # ask again: what differs now
    win.post('api/controls', {'apply': True}, then=done)


def self_update(win, apply):
    win.toast('Installiere …' if apply else 'Suche …')
    def done(r):
        win.UPD = r or {'error': 'Keine Antwort.'}
        win.toast(win.UPD.get('error') or win.UPD.get('text', ''))
    win.post('api/selfupdate', {'apply': apply}, then=done)


def flat(win, page=None):
    return [r for _, rows, _ in groups(win, page or page_of(win)) for r in rows]


def focused(win):
    if win.S.get('pane') != 1: return None
    rows = flat(win)
    return rows[max(0, min(win.S['i'], len(rows) - 1))] if rows else None


# ---- controller ------------------------------------------------------------------------------------------------------
def key(win, a):
    """A controller action while the settings show (on the top window, which acts for both)."""
    need(win)
    S, page = win.S, page_of(win)
    if a not in ('up', 'down', 'left', 'right', 'ok', 'back'): return
    if S.get('pane') != 1:
        ids = [c[0] for c in AREAS]
        n = ids.index(page.split('>')[0])
        if a in ('up', 'down'): S.update(page=ids[max(0, min(len(ids) - 1, n + (1 if a == 'down' else -1)))], i=0)
        elif a in ('ok', 'right'): S.update(page=ids[n], pane=1, i=0)
        elif a == 'back': S.update(tab=0, i=0, page='', pane=0)  # leaving the settings, like closing the app
        else: return
        return win.push()
    rows = flat(win)
    i = max(0, min(S['i'], len(rows) - 1))
    row = rows[i] if rows else None
    if a in ('up', 'down'): S['i'] = max(0, min(len(rows) - 1, i + (1 if a == 'down' else -1)))
    elif a in ('left', 'right') and row and row.get('adj'): row['adj'](-1 if a == 'left' else 1)
    elif a == 'ok':
        # shortcut: text entry needs the bottom screen's keys, so the bottom window acts on A there (see bottom_ok); the top
        # one does not know when that field closes, upgrade with a 'prompt' event if that confuses
        if row and row.get('fn') and not row.get('bottom'): return row['fn']()
    elif a in ('back', 'left'):
        if '>' in page:
            parent = page.split('>')[0]
            S.update(page=parent, i=next((n for n, r in enumerate(flat(win, parent)) if r.get('k') == 'link' and r['t'] == TITLES[page]), 0))
        else: S['pane'] = 0
    else: return
    win.push()


def bottom_ok(win):
    """A on a row that types something: the bottom window opens its keyboard."""
    need(win)
    row = focused(win)
    if row and row.get('bottom') and row.get('fn'): row['fn'](); win.update()


# ---- bottom screen ---------------------------------------------------------------------------------------------------
def draw(win, p):
    need(win)
    u, W, H = win.u, win.width(), win.height()
    y = win.tabs(p)
    bottom, page, pane = H - 2.6 * u, page_of(win), win.S.get('pane', 0)
    side_w = 33 * u
    x0, x1 = 2.6 * u, 2.6 * u + side_w + 2.4 * u
    # the list of areas
    def side(y):
        rh, card = 5.4 * u, []
        for c in CATS + [None]:
            if c: card.append(c); continue
            if not card: continue
            win.box(p, ui.QRectF(x0, y, side_w, len(card) * rh + .8 * u), 1.8 * u, ui.PANEL)
            yy = y + .4 * u
            for cid, title, icon, color, _ in card:
                rect, on = ui.QRectF(x0 + .4 * u, yy, side_w - .8 * u, rh), page.split('>')[0] == cid
                if on: win.box(p, rect, 1.4 * u, ui.FOCUS if pane == 0 else ui.faded(ui.TEXT, .12))
                sq = ui.QRectF(rect.x() + 1.2 * u, yy + (rh - 3.3 * u) / 2, 3.3 * u, 3.3 * u)
                win.box(p, sq, .8 * u, ui.QColor(color))
                draw_icon(win, p, icon, sq.adjusted(.55 * u, .55 * u, -.55 * u, -.55 * u))
                win.text(p, title, sq.right() + 1.3 * u, yy, ('u', 2, 500), ui.INK if on and pane == 0 else ui.TEXT, rect.right() - sq.right() - 2 * u, lh=rh / (2 * u))
                win.hit(rect, lambda cid=cid: (win.S.update(page=cid, pane=0, i=0), win.push()), name=title)
                yy += rh
            y += len(card) * rh + .8 * u + 1.6 * u
            card = []
        return y - 1.6 * u
    win.scroller(p, 'set-side', ui.QRectF(x0, y, side_w, bottom - y), side)
    # the chosen area
    w = W - x1 - 2.6 * u
    head = 5.4 * u
    if '>' in page:
        parent = TITLES[page.split('>')[0]]
        back = '‹ ' + parent
        bw = win.width_of(back, ('u', 2, 600)) + 3 * u
        win.capsule(p, ui.QRectF(x1, y, bw, head - 1 * u), ui.faded(ui.TEXT, .1))
        win.text(p, back, x1, y, ('u', 2, 600), ui.FOCUS, bw, 1, (head - u) / (2 * u))
        win.hit(ui.QRectF(x1, y - .4 * u, bw, head), lambda: key(win, 'back'), name='nav-back')
        win.text(p, TITLES[page], x1 + bw + 1.6 * u, y, ('u', 2.6, 700, -.01), ui.TEXT, w - bw - 1.6 * u, lh=(head - u) / (2.6 * u))
    else: win.text(p, TITLES[page], x1 + .4 * u, y, ('u', 2.8, 700, -.015), ui.TEXT, w, lh=(head - u) / (2.8 * u))
    view = ui.QRectF(x1, y + head, w, bottom - y - head)
    spot, sel = {}, min(win.S['i'], len(flat(win, page)) - 1)
    def content(y):
        top, n = y, 0
        for header, rows, footer in groups(win, page):
            if not rows and not footer: continue
            if header:
                win.text(p, header.upper(), x1 + 2 * u, y, ('u', 1.45, 600, .1), ui.MUTED, w - 4 * u, lh=1.4)
                y += 2.6 * u
            if rows:
                hs = [row_height(win, r, w) for r in rows]
                win.box(p, ui.QRectF(x1, y, w, sum(hs)), 1.8 * u, ui.PANEL)
                for k, (r, h) in enumerate(zip(rows, hs)):
                    if k: p.fillRect(ui.QRectF(x1 + 2 * u, y, w - 2 * u, max(1.0, .08 * u)), ui.faded(ui.TEXT, .08))
                    if n == sel and pane == 1: spot['span'] = (y - top, y - top + h)
                    draw_row(win, p, r, ui.QRectF(x1, y, w, h), n, n == sel and pane == 1)
                    y += h; n += 1
            if footer: y += .9 * u + win.text(p, footer, x1 + 2 * u, y + .9 * u, ('u', 1.7), ui.MUTED, w - 4 * u, lh=1.4, lines=None)
            y += 2.6 * u
        return y
    win.scroller(p, 'set:' + page, view, content)
    seen = (page, win.S['i'], pane)
    if 'span' in spot and seen != win.focus_seen:  # the controller moved: keep the row in view (a finger's scrolling is left alone)
        win.focus_seen = seen
        key_, (a, b), off = 'set:' + page, spot['span'], win.off.get('set:' + page, 0)
        new = a - u if a - u < off else b + u - view.height() if b + u > off + view.height() else off
        if new != off: win.off[key_] = max(0, new); win.update()


def draw_icon(win, p, name, rect):
    """White line icon of an area (own set, kept beside the window's ICONS)."""
    if not ui.QSvgRenderer: return
    k = ('settings', name)
    if k not in win.svgs:
        win.svgs[k] = ui.QSvgRenderer(ui.QByteArray(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{(ICONS.get(name) or ui.ICONS.get(name, "")).replace("currentColor", "#ffffff")}</svg>'.encode()))
    win.svgs[k].render(p, rect)


FREE = ('info', 'link', 'button', 'check')  # rows whose label may take two lines and a subtitle


def label_width(win, r, w):
    u = win.u
    if r['k'] not in FREE: return None
    return max(w * .4, w - 4 * u - (win.width_of(r['v'], ('u', 1.9, 400)) + 2 * u if r.get('v') else 0) - (2.4 * u if r['k'] in ('link', 'check') else 0) - (4.6 * u if r.get('icon') else 0))


def row_lines(win, r, w):
    lw = label_width(win, r, w)
    return win.wrap(r['t'], ('u', 2, 500), lw, 3) if lw else [r['t']]


def row_height(win, r, w):
    u = win.u
    if r['k'] == 'qr': return 23 * u
    if r['k'] == 'swatches': return 7.6 * u
    if r['k'] not in FREE: return 6.2 * u
    return max(6.2 * u, len(row_lines(win, r, w)) * 2 * u * 1.25 + (1.7 * u * 1.35 if r.get('sub') else 0) + 2.8 * u)


def draw_row(win, p, r, rect, n, on):
    u, kind = win.u, r['k']
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if on:
        win.box(p, rect.adjusted(.35 * u, .35 * u, -.35 * u, -.35 * u), 1.5 * u, ui.faded(ui.FOCUS, .14), ui.FOCUS, .22 * u)
    if kind == 'qr':
        import qr
        qs = 19.6 * u
        qr.draw(p, ui.QRectF(x + 2 * u, y + (h - qs) / 2, qs, qs), r['qr'], round(1.5 * u))
        rx, rw = x + 2 * u + qs + 2.4 * u, w - 6.4 * u - qs
        ry = y + 2.4 * u
        ry += win.text(p, r['link'], rx, ry, ('u', 2.0, 600), ui.FOCUS, rw, lh=1.3) + .8 * u
        box = ui.QRectF(rx, ry, rw, 6.8 * u)
        win.box(p, box, 1.2 * u, ui.RAISED, ui.faded(ui.TEXT, .12))
        win.text(p, r['code'], box.x(), box.y(), ('u', 2.6, 700, .03), ui.TEXT, box.width(), 1, 6.8 / 2.6)
        ry += 8.0 * u
        win.text(p, 'Mit Handy scannen', rx, ry, ('u', 1.75, 400), ui.MUTED, rw, lh=1.35)
        win.hit(rect, lambda: (win.S.update(pane=1, i=n), win.push()), name=r['t'])
        return
    def tap():
        win.S.update(pane=1, i=n)
        if r.get('fn') and kind not in ('slider', 'choice', 'swatches', 'info'): r['fn']()
        win.push()
    win.hit(rect, tap, name=r['t'])
    color = ui.WARN if r.get('warn') else ui.FOCUS if kind == 'button' else ui.TEXT
    lf, vf = ('u', 2, 500), ('u', 1.9, 400)
    right = x + w - 2 * u
    if kind == 'link':
        win.text(p, '›', right - 1.2 * u, y, ('u', 2.8, 400), ui.MUTED, 1.4 * u, 2, h / (2.8 * u))
        right -= 2.4 * u
    elif kind == 'toggle':
        sw = ui.QRectF(right - 5.6 * u, y + (h - 3.2 * u) / 2, 5.6 * u, 3.2 * u)
        win.capsule(p, sw, ui.LIVE if r['on'] else ui.faded(ui.TEXT, .2))
        p.setPen(ui.Qt.PenStyle.NoPen); p.setBrush(ui.QColor('#ffffff'))
        p.drawEllipse(ui.QPointF(sw.right() - 1.6 * u if r['on'] else sw.x() + 1.6 * u, sw.center().y()), 1.3 * u, 1.3 * u)
        right = sw.x() - 1.6 * u
    elif kind == 'check':
        if r.get('on'): win.text(p, '✓', right - 2 * u, y, ('u', 2.4, 700), ui.FOCUS, 2 * u, 2, h / (2.4 * u))
        right -= 3.2 * u
    elif kind == 'choice':
        opts = r['opts']
        fs = ('u', 1.75, 600)
        seg = max(win.width_of(l, fs) for _, l in opts) + 2.6 * u
        total = min(seg * len(opts) + .6 * u, w * .64)
        seg = (total - .6 * u) / len(opts)
        box = ui.QRectF(right - total, y + (h - 4.2 * u) / 2, total, 4.2 * u)
        win.box(p, box, 1.1 * u, ui.faded(ui.TEXT, .08))
        for k, (oid, label) in enumerate(opts):
            sr = ui.QRectF(box.x() + .3 * u + k * seg, box.y() + .3 * u, seg, box.height() - .6 * u)
            sel = oid == r['cur']
            if sel: win.box(p, sr, .9 * u, ui.FOCUS if on else ui.faded(ui.FOCUS, .32), None if on else ui.faded(ui.FOCUS, .55))
            win.text(p, label, sr.x(), sr.y(), fs, ui.INK if sel and on else ui.TEXT if sel else ui.MUTED, sr.width(), 1, sr.height() / (fs[1] * u))
            win.hit(sr, lambda oid=oid: (win.S.update(pane=1, i=n), r['set'](oid), win.push()), name=f'{r["t"]}:{label}')
        right = box.x() - 1.4 * u
    elif kind == 'swatches':
        d, gap = 3.6 * u, 1.05 * u
        sx = right - len(COLORS) * (d + gap) + gap
        for name, hexc in COLORS:
            c = ui.QPointF(sx + d / 2, y + h / 2)
            if hexc == r['cur']:
                p.setPen(ui.QPen(ui.TEXT, .28 * u)); p.setBrush(ui.Qt.BrushStyle.NoBrush); p.drawEllipse(c, d / 2 + .55 * u, d / 2 + .55 * u)
            p.setPen(ui.QPen(ui.faded(ui.TEXT, .25), .08 * u)); p.setBrush(ui.QColor('#' + hexc)); p.drawEllipse(c, d / 2, d / 2)
            win.hit(ui.QRectF(sx - gap / 2, y, d + gap, h), lambda hexc=hexc: (win.S.update(pane=1, i=n), thor_set(win, 'rgb', {'color': hexc, 'enabled': True}), win.push()), name=name)
            sx += d + gap
        right = right - len(COLORS) * (d + gap)
    elif kind == 'slider':
        val, low = r.get('val') or 0, r.get('low', 0)
        left, width = x + 17 * u, w - 17 * u - 9.5 * u
        part = max(0.0, min(1.0, (val - low) / (100 - low)))
        mid = y + h / 2
        win.capsule(p, ui.QRectF(left, mid - .45 * u, width, .9 * u), ui.faded(ui.TEXT, .12))
        win.capsule(p, ui.QRectF(left, mid - .45 * u, max(.9 * u, width * part), .9 * u), win.accent_fill(ui.QRectF(left, 0, width, 1)))
        p.setPen(ui.Qt.PenStyle.NoPen); p.setBrush(ui.rgba(0, 0, 0, .35)); p.drawEllipse(ui.QPointF(left + width * part, mid + .15 * u), 1.45 * u, 1.45 * u)
        p.setBrush(ui.QColor('#ffffff')); p.drawEllipse(ui.QPointF(left + width * part, mid), 1.35 * u, 1.35 * u)
        win.text(p, f'{val} %', right - 7 * u, y, vf, ui.MUTED, 7 * u, 2, h / (vf[1] * u))
        if r.get('adj'):
            win.hit(ui.QRectF(right - 7.4 * u, y, 7.6 * u, h), lambda r=r: (win.S.update(pane=1, i=n), r['adj'](1 if (r.get('val') or 0) < 100 else -19), win.push()), name=f'{r["t"]}:step')
        if r.get('key'): drag = lambda px, key=r['key']: win.set_value(key, px, left, width)
        else:
            def drag(px):
                v = round(low + max(0.0, min(1.0, (px - left) / width)) * (100 - low))
                if v != r.get('val'): r['val'] = v; r['set'](v)
        win.hit(ui.QRectF(left - 1.5 * u, y, width + 3 * u, h), drag, True, r.get('key') or r['t'])
        right = left - u
    if kind in FREE:
        lines = row_lines(win, r, w)
        sub = 1.7 * u * 1.35 if r.get('sub') else 0
        ty = y + (h - len(lines) * 2 * u * 1.25 - sub) / 2
        tx = x + 2 * u
        if r.get('icon'):  # a device's kind, as in the list of areas
            sq = ui.QRectF(tx, y + (h - 3.3 * u) / 2, 3.3 * u, 3.3 * u)
            win.box(p, sq, .8 * u, ui.QColor('#0a84ff'))
            draw_icon(win, p, r['icon'], sq.adjusted(.5 * u, .5 * u, -.5 * u, -.5 * u))
            tx += 4.6 * u
        for line in lines: ty += win.text(p, line, tx, ty, lf, color, lh=1.25)
        if sub: win.text(p, r['sub'], tx, ty, ('u', 1.7), ui.MUTED, label_width(win, r, w), lh=1.35)
        label_w = label_width(win, r, w)
    else:
        label_w = right - x - 2 * u
        win.text(p, r['t'], x + 2 * u, y, lf, color, label_w, lh=h / (2 * u))
    if r.get('v') and kind not in ('slider',):
        vx = x + 2 * u + (4.6 * u if r.get('icon') and kind in FREE else 0) + min(max(win.width_of(l, lf) for l in row_lines(win, r, w)), label_w) + 2 * u
        win.text(p, r['v'], vx, y, vf, ui.MUTED, right - vx, 2, h / (vf[1] * u))


# ---- top screen ------------------------------------------------------------------------------------------------------
def draw_top(win, p):
    """What the focus is on, in large: the area or the row, its value and a sentence on what it does."""
    need(win)
    u, W, H, page = win.u, win.width(), win.height(), page_of(win)
    full = ui.QRectF(0, 0, W, H)
    g = ui.QRadialGradient(ui.QPointF(.12 * W, 1.05 * H), .75 * W)
    g.setColorAt(0, ui.faded(ui.FOCUS, .16)); g.setColorAt(1, ui.faded(ui.FOCUS, 0))
    p.fillRect(full, ui.QBrush(g))
    rgb = (win.THOR or {}).get('rgb')
    if page == 'light' and rgb and rgb.get('enabled'):  # the two stick rings, in their colour
        c = ui.QColor('#' + str(rgb.get('color', 'FFFFFF')))
        glow = .35 + .65 * rgb.get('level', 50) / 100
        for cx in (.62 * W, .84 * W):
            rg = ui.QRadialGradient(ui.QPointF(cx, .42 * H), 11 * u)
            rg.setColorAt(0, ui.faded(c, 0)); rg.setColorAt(.62, ui.faded(c, .0)); rg.setColorAt(.74, ui.faded(c, glow)); rg.setColorAt(.86, ui.faded(c, .25 * glow)); rg.setColorAt(1, ui.faded(c, 0))
            p.fillRect(ui.QRectF(cx - 11 * u, .42 * H - 11 * u, 22 * u, 22 * u), ui.QBrush(rg))
            p.setPen(ui.Qt.PenStyle.NoPen); p.setBrush(ui.rgba(30, 31, 36, 1)); p.drawEllipse(ui.QPointF(cx, .42 * H), 6.4 * u, 6.4 * u)
            p.setBrush(ui.rgba(46, 47, 54, 1)); p.drawEllipse(ui.QPointF(cx, .42 * H), 4.6 * u, 4.6 * u)
    win.status_bar(p)
    row = focused(win)
    area = next(c for c in AREAS if c[0] == page.split('>')[0])
    if row is None: label, name, help, value = 'Einstellungen', TITLES[page], area[4], ''
    else:
        label, name, help = 'Einstellungen · ' + TITLES[page], row['t'], row.get('help', '')
        value = f'{row["val"]} %' if row['k'] == 'slider' and row.get('val') is not None else ('Ein' if row['on'] else 'Aus') if row['k'] == 'toggle' else \
            dict(row['opts']).get(row['cur'], '') if row['k'] == 'choice' else next((n for n, h in COLORS if h == row.get('cur')), '') if row['k'] == 'swatches' else row.get('code') or row.get('v') or ''
        if row['k'] == 'qr' and row.get('qr'):
            import qr
            qr.draw(p, ui.QRectF(W - 30 * u, H / 2 - 12 * u, 24 * u, 24 * u), row['qr'], round(1.8 * u))
    kind = row['k'] if row else None
    hints = [('A', 'Öffnen'), ('↕', 'Auswählen'), ('B', 'Zur Bibliothek')] if row is None else \
        ([('↔', 'Ändern')] if kind in ('slider', 'swatches') else [('A', 'Ein/Aus')] if kind == 'toggle' else [('↔', 'Wählen')] if kind == 'choice' else
         [('A', 'Eintippen (unten)' if row.get('bottom') else 'Öffnen')] if kind == 'link' else [('A', 'Ausführen' if kind == 'button' else 'Wählen')] if kind in ('button', 'check') else []) + [('B', 'Zurück')]
    nf, hf = ('u', 4.6, 700, -.025), ('u', 2, 400)
    if len(win.wrap(name, nf, 64 * u)) > 1: nf = ('u', 3.4, 700, -.02)  # long names get smaller, then wrap
    names = win.wrap(name, nf, 64 * u, 3)
    rows = win.wrap(help, hf, 62 * u, 4) if help else []
    height = 2 * u + .9 * u + len(names) * nf[1] * u * 1.08 + (3.2 * u * 1.2 if value else 0) + 1.6 * u + len(rows) * 2 * u * 1.45 + 2.6 * u + 3.6 * u
    x, y = 4.2 * u, H - 4.2 * u - height
    y += win.text(p, label.upper(), x, y, ('u', 1.4, 700, .16), ui.FOCUS, lh=2 / 1.4) + .9 * u
    for line in names: y += win.text(p, line, x, y, nf, ui.TEXT, lh=1.08)
    if value: y += win.text(p, value, x, y, ('u', 3.2, 500), ui.FOCUS, 64 * u, lh=1.2)
    y += 1.6 * u
    for line in rows: y += win.text(p, line, x, y, hf, ui.MUTED, lh=1.45)
    pad_acts = {'↔': (lambda: (row['adj'](1), win.push()))} if (row and row.get('adj')) else None
    win.pads(p, x, y + 2.6 * u, hints, actions=pad_acts)
