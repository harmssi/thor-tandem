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
    ('accounts', 'Konten', 'person', '#ff9f0a', 'RetroAchievements für Erfolge in allen Emulatoren. Steam und Plex folgen.'),
    None,
    ('look', 'Aussehen', 'look', '#ff375f', 'Farben, Stil und Sprache der Oberfläche.'),
    ('library', 'Bibliothek', 'stack', '#64d2ff', 'Spiele, Spieleordner, Speicherplatz und Cover.'),
    None,
    ('updates', 'Updates', 'scan', '#5e5ce6', 'Tandem und die Switch-Emulatoren auf den neuesten Stand bringen.'),
    ('about', 'Über den Thor', 'info', '#8e8e93', 'Gerät, Versionen und der Einrichtungsassistent.'),
    ('onoff', 'Ein / Aus', 'off', '#ff453a', 'Standby, Neustart, Ausschalten und der Desktop.'),
]
AREAS = [c for c in CATS if c]
TITLES = {c[0]: c[1] for c in AREAS} | {'controls>map': 'Tastenbelegung', 'network>wifi': 'WLAN'}
ICONS = {
    'screens': '<rect x="5" y="3" width="14" height="8" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="5" y="13" width="14" height="8" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    'light': '<circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2.5v2.6M12 18.9v2.6M2.5 12h2.6M18.9 12h2.6M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    'bolt': '<path d="M13.5 2.5L5 13.5h6l-1.5 8 8.5-11h-6z" fill="currentColor"/>',
    'wifi': '<path d="M3 9.5a13 13 0 0 1 18 0M6.2 12.8a8.5 8.5 0 0 1 11.6 0M9.4 16a4 4 0 0 1 5.2 0" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="19" r="1.5" fill="currentColor"/>',
    'person': '<circle cx="12" cy="8.5" r="3.8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    'look': '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor"/>',
    'stack': '<rect x="4" y="9" width="16" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M6.5 6h11M9 3h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    'info': '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 11v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="7.6" r="1.3" fill="currentColor"/>',
    'off': '<path d="M12 3.5v8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M7 6.5a7.5 7.5 0 1 0 10 0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
}
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
    if win.CTRL is None and page_of(win).startswith('controls'):
        win.CTRL = {}
        win.call('api/controls', then=lambda c: setattr(win, 'CTRL', c or {}))


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
        rest = CFG.get('rest_min', 3)
        return [('Helligkeit', rows, None),
                ('Ton', [sl('vol', 'Lautstärke', 'Lautstärke des Thor. Die Tasten an der Seite ändern sie in 5er-Schritten.')] if SET.get('vol') is not None else [], None),
                ('Ruheschutz (OLED)', [choice('Schwarz nach', REST, rest, lambda v: config_set(win, rest_min=v),
                                             'Rührt niemand Tandem an, werden beide Bildschirme schwarz und zeigen nur eine wandernde Uhr. Das schont die OLED-Bildschirme. Jede Taste weckt sie.')],
                 'Während ein Spiel läuft, bleibt der Bildschirm an.')]
    if page == 'controls':
        C, gyro = win.CTRL or {}, (T or {}).get('gyro')
        off = len({d.get('emu') for d in C.get('off') or []})  # emulators that differ, not keys
        rows = [{'k': 'link', 't': 'Tastenbelegung', 'v': 'Übersicht', 'fn': lambda: go_page(win, 'controls>map'), 'help': 'Welche Taste wo was tut: in Tandem, in jedem Spiel, die Kürzel mit Select.'},
                {'k': 'button', 't': 'In allen Emulatoren angleichen', 'v': (f'{off} Emulator' + ('en' if off != 1 else '') + ' weichen ab' if off != 1 else '1 Emulator weicht ab') if off else 'alles gleich',
                 'fn': lambda: apply_controls(win), 'help': 'Stellt in jedem installierten Emulator die Tandem-Belegung ein. Vorher wird jede geänderte Datei gesichert.'}]
        rows2 = [{'k': 'info', 't': 'Controller', 'v': 'Xbox 360 (fest)', 'help': 'Unter Tandem meldet sich der Thor immer als Xbox-360-Controller. Nur so liegt jede Taste in jedem Emulator gleich.'}]
        if gyro: rows2.append(toggle('Gyro', gyro.get('enabled'), lambda on: thor_set(win, 'gyro', on), 'Bewegungssensor des Thor für Spiele, die ihn nutzen (z. B. Zielen durch Neigen).'))
        layout = 'us' if CFG.get('kb_layout') == 'us' else 'de'
        rows2.append(choice('Bildschirmtastatur', [('de', 'Deutsch'), ('us', 'Englisch')], layout, lambda v: config_set(win, kb_layout=v),
                            'Belegung der Tasten auf dem unteren Bildschirm, wenn etwas eingetippt wird.'))
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
                               'Die Ringe werden mit dem oberen Bildschirm heller und dunkler.')],
                 'Die Einstellung bleibt auch nach einem Neustart.')]
    if page == 'perf':
        if T is None: return loading
        pw, B = T.get('power'), win.BATT
        rows = []
        if pw:
            labels = dict(pw.get('profiles') or [])
            rows.append(choice('Leistungsprofil', list(labels.items()), pw.get('profile'), lambda v: thor_set(win, 'profile', v),
                               'Sparsam: länger spielen, leiser. Ausgewogen: für fast alles. Leistung: volle Kraft für PS2, Switch und PC-Spiele – wärmer und lauter.'))
        info = ([{'k': 'info', 't': 'Akku', 'v': f'{B["level"]} %' + (' · lädt' if B.get('charging') else ''), 'help': 'Ladestand des Akkus.'}] if B else []) + \
               ([{'k': 'info', 't': 'Temperatur', 'v': f'{pw["temp"]} °C', 'help': 'Temperatur im Gerät. Bis etwa 80 °C ist alles in Ordnung.'},
                 {'k': 'info', 't': 'Lüfter', 'v': f'{pw["fan"]} U/min', 'help': 'Der Lüfter regelt sich selbst nach der Temperatur und dem Profil.'}] if pw else [])
        return [(None, rows, 'Gilt sofort und bleibt bis zur nächsten Änderung.' if rows else 'Das Leistungsprofil ist hier nicht erreichbar.'), ('Zustand', info, None)]
    if page == 'network':
        own = P.get('own') or P.get('url')
        return [(None, [{'k': 'link', 't': 'WLAN', 'v': SYS.get('ssid') or ('nicht verbunden' if win.SYS else '…'), 'fn': lambda: go_page(win, 'network>wifi'),
                         'help': 'Netze in der Nähe zeigen und verbinden.'}], None),
                ('Vom Handy oder PC', [{'k': 'info', 't': 'Adresse', 'v': own or '–', 'help': 'Diese Adresse im Browser öffnen: dort gibt es dieselben Einstellungen, bequem mit Tastatur.'},
                                       {'k': 'info', 't': 'PIN', 'v': str(P.get('pin') or '–'), 'help': 'Die PIN gilt einmal. Danach bleibt der Browser ein Jahr angemeldet.'}] +
                 ([{'k': 'info', 't': 'Im Heimnetz', 'v': P['ip_url'], 'help': 'Falls der Name nicht gefunden wird: diese Adresse mit Zahlen.'}] if P.get('ip_url') else []), None)]
    if page == 'network>wifi':
        nets = SYS.get('networks') or []
        rows = [{'k': 'check', 't': n['ssid'], 'on': n.get('active'), 'v': f'{n["signal"]} %' + (' · geschützt' if n.get('secure') else ''), 'fn': lambda n=n: win.wifi(n),
                 'bottom': bool(n.get('secure') and not n.get('known')), 'help': 'Verbinden.' + (' Das Passwort tippst du unten ein.' if n.get('secure') and not n.get('known') else '')} for n in nets]
        return [(None, rows or [{'k': 'info', 't': 'Keine Netze gefunden', 'v': '', 'help': ''}], None),
                (None, [{'k': 'button', 't': 'Erneut suchen', 'fn': lambda: (win.toast('Suche Netze …'), win.load_sys(True)), 'help': 'Sucht noch einmal nach Netzen.'}], None)]
    if page == 'accounts':
        ask = lambda key: lambda: win.ask_account(key)
        return [('RetroAchievements', [{'k': 'link', 't': 'Benutzername', 'v': CFG.get('ra_user') or 'kein Konto', 'fn': ask('ra_user'), 'bottom': True, 'help': 'Dein Name bei retroachievements.org. Eingetippt wird unten.'},
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
                             {'k': 'info', 't': 'Plex', 'v': 'kommt später', 'help': 'Plex folgt in einer der nächsten Versionen.'}], None)]
    if page == 'look':
        rows = [{'k': 'check', 't': t['name'], 'on': t['id'] == ui.THEME['id'], 'fn': lambda t=t: set_theme(win, t['id']), 'help': 'Farben und Stil der Oberfläche auf beiden Bildschirmen.'}
                for t in CFG.get('themes') or []]
        return [('Thema', rows, 'Die Hervorhebung nimmt im Spiel die Farbe des Covers an, wenn das Thema es vorsieht.'),
                ('Sprache', [choice('Sprache / Language', [('de', 'Deutsch'), ('en', 'English')], CFG.get('lang') or 'de', lambda v: config_set(win, lang=v),
                                    'Sprache der Oberfläche auf beiden Bildschirmen und der Einstellungsseite. Spiele bleiben, wie sie sind.')], None)]
    if page == 'library':
        rows = [{'k': 'info', 't': 'Spiele', 'v': str(len(win.L['games'])), 'help': 'Alle Spiele, die Tandem gefunden hat.'},
                {'k': 'info', 't': 'Spieleordner', 'v': 'ROMs/<System>', 'help': 'Spiele gehören in einen Ordner „ROMs“ auf der Karte oder im Gerät, je System ein Unterordner (wie bei ES-DE).'},
                {'k': 'button', 't': 'Neu einlesen und Cover laden', 'fn': lambda: win.start({'id': 'rescan', 's': 'app'}), 'help': 'Sucht neue Spiele und lädt fehlende Cover aus dem Netz.'}]
        store = [{'k': 'info', 't': s['name'], 'v': f'{round(s["free"] / 1e9)} von {round(s["total"] / 1e9)} GB frei', 'help': 'Freier Platz.'} for s in SYS.get('storage') or []]
        return [(None, rows, None), ('Speicher', store, None)]
    if page == 'updates':
        U = win.UPD or {}
        rows = [{'k': 'info', 't': 'Tandem', 'v': 'Version ' + str(CFG.get('version', '')), 'help': 'Die installierte Version.'},
                {'k': 'button', 't': 'Nach Update suchen', 'fn': lambda: self_update(win, False), 'v': U.get('text', ''), 'help': 'Fragt die Update-Quelle nach einer neuen Version. Installiert wird erst auf Wunsch.'}]
        if U.get('new'): rows.append({'k': 'button', 't': f'Version {U["new"]} installieren', 'fn': lambda: self_update(win, True), 'help': 'Installiert die neue Version; sie gilt ab dem nächsten Start von Tandem. Geht etwas schief, bleibt die bisherige.'})
        extras = [{'k': 'button', 't': e['name'] + (' aktualisieren' if e.get('installed') else ' installieren'), 'fn': lambda e=e: win.start({'id': 'upd:' + e['id'], 's': 'app'}),
                   'help': 'Lädt die neueste Fassung aus dem Netz. Das kann eine Minute dauern.'} for e in win.L.get('extras') or []]
        return [(None, rows, 'Quelle: ' + (CFG.get('update_url') or 'keine') if CFG.get('update_url') is not None else None), ('Emulatoren', extras, None)]
    if page == 'about':
        B = win.BATT
        return [(None, [{'k': 'info', 't': 'Gerät', 'v': 'AYN Thor', 'help': 'Zwei Bildschirme, oben das Spiel, unten die Bedienung.'},
                        {'k': 'info', 't': 'ArmadaOS', 'v': (T or {}).get('os') or '–', 'help': 'Das Betriebssystem. Updates dafür kommen über Steam oder den Desktop.'},
                        {'k': 'info', 't': 'Tandem', 'v': 'Version ' + str(CFG.get('version', '')), 'help': 'Toravo Tandem, die Oberfläche für beide Bildschirme.'}] +
                 ([{'k': 'info', 't': 'Akku', 'v': f'{B["level"]} %', 'help': 'Ladestand des Akkus.'}] if B else []), None),
                (None, [{'k': 'button', 't': 'Einrichtung erneut zeigen', 'fn': lambda: win.post('api/setup', {'open': True}), 'help': 'Zeigt die vier Schritte vom ersten Start: Spiele, Emulatoren, Netz und Konto.'}], None)]
    if page == 'onoff':
        texts = {'suspend': 'Der Thor schläft und wacht mit der Ein-Taste sofort wieder auf.', 'reboot': 'Startet den Thor neu.', 'poweroff': 'Schaltet den Thor aus.',
                 'desktop': 'Wechselt zum KDE-Desktop. Zurück geht es über „Zurück zu Tandem“ auf dem Desktop.'}
        return [(None, [{'k': 'button', 't': ui.POWER[n][1], 'warn': n in ('reboot', 'poweroff'), 'fn': lambda n=n: win.confirm_action(n), 'help': texts[n] + ' Tandem fragt vorher.'}
                        for n in ui.POWER], None)]
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
    return max(w * .4, w - 4 * u - (win.width_of(r['v'], ('u', 1.9, 400)) + 2 * u if r.get('v') else 0) - (2.4 * u if r['k'] in ('link', 'check') else 0))


def row_lines(win, r, w):
    lw = label_width(win, r, w)
    return win.wrap(r['t'], ('u', 2, 500), lw, 3) if lw else [r['t']]


def row_height(win, r, w):
    u = win.u
    if r['k'] == 'swatches': return 7.6 * u
    if r['k'] not in FREE: return 6.2 * u
    return max(6.2 * u, len(row_lines(win, r, w)) * 2 * u * 1.25 + (1.7 * u * 1.35 if r.get('sub') else 0) + 2.8 * u)


def draw_row(win, p, r, rect, n, on):
    u, kind = win.u, r['k']
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if on:
        win.box(p, rect.adjusted(.35 * u, .35 * u, -.35 * u, -.35 * u), 1.5 * u, ui.faded(ui.FOCUS, .14), ui.FOCUS, .22 * u)
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
            if sel: win.box(p, sr, .9 * u, ui.FOCUS if on else ui.faded(ui.TEXT, .2))
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
        for line in lines: ty += win.text(p, line, x + 2 * u, ty, lf, color, lh=1.25)
        if sub: win.text(p, r['sub'], x + 2 * u, ty, ('u', 1.7), ui.MUTED, label_width(win, r, w), lh=1.35)
        label_w = label_width(win, r, w)
    else:
        label_w = right - x - 2 * u
        win.text(p, r['t'], x + 2 * u, y, lf, color, label_w, lh=h / (2 * u))
    if r.get('v') and kind not in ('slider',):
        vx = x + 2 * u + min(max(win.width_of(l, lf) for l in row_lines(win, r, w)), label_w) + 2 * u
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
            dict(row['opts']).get(row['cur'], '') if row['k'] == 'choice' else next((n for n, h in COLORS if h == row.get('cur')), '') if row['k'] == 'swatches' else row.get('v') or ''
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
    win.pads(p, x, y + 2.6 * u, hints)
