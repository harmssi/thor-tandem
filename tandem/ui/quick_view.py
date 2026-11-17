"""Schnellmenü: what the Thor key opens on the bottom screen, like the Thor's own panel under Android. Everything about the
device in one place, by touch (while a game runs the controller belongs to the game): both brightnesses and the volume,
performance profile, stick lights, temperature/fan/battery, recording both screens, a screenshot, and the way back to
Tandem or out of the game. The Thor key or "Schließen" closes it; it also closes itself after a while untouched.
"""
import time

ui = None  # the window's module (tandem_ui), set by it
CLOSE_AFTER = 20  # seconds untouched


def toggle(win):
    win.QUICK = None if win.QUICK else time.time()
    if win.QUICK:
        win.call('api/thor', then=lambda t: t and setattr(win, 'THOR', t))
        win.call('api/record', then=lambda r: r and setattr(win, 'REC', r))
        win.call('api/framegen', then=lambda r: r and setattr(win, 'FG', r))
    win.update()


def touched(win):
    if win.QUICK: win.QUICK = time.time()


def draw(win, p):
    u, W, H, T = win.u, win.width(), win.height(), win.THOR or {}
    if time.time() - win.QUICK > CLOSE_AFTER: win.QUICK = None; return
    ui.QTimer.singleShot(1000, win.update)  # the clock and the auto-close
    QRectF, TEXT, MUTED, FOCUS, WARN, LIVE, RAISED = ui.QRectF, ui.TEXT, ui.MUTED, ui.FOCUS, ui.WARN, ui.LIVE, ui.RAISED
    p.fillRect(0, 0, W, H, ui.faded(ui.INK, .94))
    win.hit(QRectF(0, 0, W, H), lambda: touched(win))  # taps between the tiles go nowhere else
    x0, cw = 3 * u, W - 6 * u
    f_head, f_lab, f_btn, f_small = ('u', 3.2, 700, -.02), ('u', 2.2, 500), ('u', 2.2, 600), ('u', 1.9, 500)
    win.text(p, 'Thor', x0, 2.4 * u, f_head, TEXT)
    pw, B = T.get('power') or {}, win.BATT
    state = '  ·  '.join(s for s in (ui.clock(), f'{B["level"]} %' + (' lädt' if B.get('charging') else '') if B else '',
                                     f'{pw["temp"]} °C' if pw.get('temp') is not None else '', f'Lüfter {pw["fan"]}' if pw.get('fan') is not None else '') if s)
    win.text(p, state, x0, 2.9 * u, f_small, MUTED, cw, 2)
    y = 8.6 * u

    def slider(key, label):  # the same path as the settings: SET + api/set, at most every 60 ms
        nonlocal y
        val = win.SET.get(key)
        if val is None: return
        win.text(p, label, x0, y, f_lab, TEXT, 18 * u)
        left, width = x0 + 19 * u, cw - 27 * u
        track = QRectF(left, y + 1.1 * u, width, 1.4 * u)
        win.capsule(p, track, ui.faded(TEXT, .14))
        if val: win.capsule(p, QRectF(left, track.y(), max(track.height(), width * val / 100), track.height()), FOCUS)
        win.text(p, f'{val}', x0 + cw - 6 * u, y, f_lab, MUTED, 6 * u, 2)
        win.hit(QRectF(left - 1.5 * u, y - .6 * u, width + 3 * u, 4.8 * u), lambda x: (touched(win), win.set_value(key, x, left, width)), True, key)
        y += 5.4 * u

    slider('bt', 'Oben')
    slider('bb', 'Unten')
    slider('vol', 'Lautstärke')
    y += .8 * u

    def row(buttons, h=6.4 * u):  # [(label, fn, active, colour)] side by side
        nonlocal y
        gap = 1.2 * u
        w = (cw - gap * (len(buttons) - 1)) / len(buttons)
        for n, (label, fn, on, color) in enumerate(buttons):
            fg, bg = (ui.INK, color) if on else (TEXT, RAISED)
            win.button(p, QRectF(x0 + n * (w + gap), y, w, h), label, lambda fn=fn: (touched(win), fn()), f_btn, fg, bg)
        y += h + 1.4 * u

    send = ui.settings_view.thor_set
    if pw.get('profiles'):
        win.text(p, 'Leistung', x0, y, f_small, MUTED); y += 2.8 * u
        row([(label, lambda v=v: send(win, 'profile', v), pw.get('profile') == v, FOCUS) for v, label in pw['profiles']])
    rgb = T.get('rgb')
    if rgb:
        names = [c[1] for c in ui.settings_view.COLORS]
        color = str(rgb.get('color', 'FFFFFF')).upper()
        nxt = names[(names.index(color) + 1) % len(names)] if color in names else names[0]
        win.text(p, 'Stick-Licht', x0, y, f_small, MUTED); y += 2.8 * u
        row([('An' if rgb.get('enabled') else 'Aus', lambda: send(win, 'rgb', {'enabled': not rgb.get('enabled')}), bool(rgb.get('enabled')), ui.QColor('#' + color)),
             ('Nächste Farbe', lambda: send(win, 'rgb', {'color': nxt, 'enabled': True}), False, FOCUS)])
    fg = getattr(win, 'FG', None)
    if fg and fg.get('there'):  # Lossless Scaling frame generation, counts from the next game start
        win.text(p, 'Frame Generation (ab dem nächsten Spielstart)', x0, y, f_small, MUTED); y += 2.8 * u
        row([('An' if fg['on'] else 'Aus', lambda: win.post('api/framegen', {'on': not fg['on']}, then=lambda r: r and (setattr(win, 'FG', r), win.update())),
              bool(fg['on']), FOCUS)])
    rec = (win.REC or {}).get('on')
    win.text(p, 'Aufnehmen', x0, y, f_small, MUTED); y += 2.8 * u
    row([('■ Aufnahme stoppen' if rec else '● Aufnahme starten', lambda: record(win, not rec), bool(rec), WARN),
         ('Bildschirmfoto', lambda: shot(win), False, FOCUS)])
    if win.REC and win.REC.get('last') and not rec:
        win.text(p, 'Gespeichert: ' + win.REC['last'], x0, y - .6 * u, f_small, MUTED, cw); y += 3 * u
    bottom = H - 3 * u - 6.4 * u
    y = max(y, bottom - 7.8 * u)
    if win.RUN:
        row([('Zu Tandem', lambda: (close(win), win.post('api/pause')), False, FOCUS),
             ('Spiel beenden', lambda: (close(win), win.confirm_quit()), False, WARN)])
    row([('Schließen', lambda: close(win), False, FOCUS)])


def close(win):
    win.QUICK = None
    win.update()


def record(win, on):
    win.toast('Aufnahme startet …' if on else 'Aufnahme wird gespeichert …')
    win.post('api/record', {'action': 'start' if on else 'stop'},
             then=lambda r: r and (win.toast(r['error']) if r.get('error') else (setattr(win, 'REC', r), win.update())))


def shot(win):
    win.post('api/shot', {}, then=lambda r: r and win.toast(r.get('error') or 'Bildschirmfoto gespeichert'))
