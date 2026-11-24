"""Schnellmenü: Bento Command Center opened by the Thor hardware key on the bottom screen.
Controls: FPS-Fenster (MangoHud on top screen: Aus / FPS / Leiste / Graph), Quick Game Switcher (recent games),
dual-screen brightness & volume sliders, per-game power/FPS/scaling, night mode, stick RGB swatches,
dual-screen recording/screenshot, and quick session actions."""
import time

ui = None  # set by tandem_ui
CLOSE_AFTER = 22  # seconds untouched
HUD_OPTS = ((0, 'Aus'), (1, 'FPS'), (2, 'Leiste'), (3, 'Graph'))


def toggle(win):
    win.QUICK = None if win.QUICK else time.time()
    if win.QUICK:
        win.call('api/thor', then=lambda t: t and setattr(win, 'THOR', t))
        win.call('api/record', then=lambda r: r and setattr(win, 'REC', r))
        win.call('api/framegen', then=lambda r: r and setattr(win, 'FG', r))
        win.call('api/telemetry', then=lambda r: r and setattr(win, 'QTELE', r))
    win.update()


def touched(win):
    if win.QUICK: win.QUICK = time.time()


def _fmt_rem(mins):
    if not mins: return ''
    h, m = divmod(int(mins), 60)
    return f'~{h}:{m:02d} Std.' if h else f'~{m} Min.'


def _fmt_play(secs):
    secs = int(secs or 0)
    if secs < 60:
        return ''
    if secs < 3600:
        return f'{secs // 60} Min.'
    return f'{secs / 3600:.1f} Std.'.replace('.', ',')


def draw(win, p):
    u, W, H, T = win.u, win.width(), win.height(), win.THOR or {}
    if time.time() - win.QUICK > CLOSE_AFTER: win.QUICK = None; return
    ui.QTimer.singleShot(1000, win.update)
    QRectF, QPointF, TEXT, MUTED, FOCUS, WARN, LIVE, PANEL, RAISED, LINE, INK = (
        ui.QRectF, ui.QPointF, ui.TEXT, ui.MUTED, ui.FOCUS, ui.WARN, ui.LIVE, ui.PANEL, ui.RAISED, ui.LINE, ui.INK)

    # Backdrop
    p.fillRect(0, 0, W, H, ui.faded(INK, .95))
    g = ui.QLinearGradient(0, 0, 0, 26 * u)
    g.setColorAt(0, ui.faded(FOCUS, .12)); g.setColorAt(1, ui.faded(FOCUS, 0))
    p.fillRect(QRectF(0, 0, W, 26 * u), ui.QBrush(g))
    win.hit(QRectF(0, 0, W, H), lambda: touched(win))

    x0, cw = 2.6 * u, W - 5.2 * u
    f_sec = ('u', 1.38, 700, .09)
    f_btn = ('u', 1.82, 600)

    # ---- Top Header Bar ----
    hy = 2.0 * u
    badge = QRectF(x0, hy, 12.2 * u, 4.6 * u)
    win.capsule(p, badge, ui.faded(FOCUS, .18), ui.faded(FOCUS, .45))
    win.text(p, 'THOR', badge.x(), badge.y(), ('u', 1.75, 700, .14), FOCUS, badge.width(), 1, 4.6 / 1.75)

    close_w = win.width_of('Schließen', ('u', 1.8, 600)) + 3.4 * u
    close_r = QRectF(x0 + cw - close_w, hy, close_w, 4.6 * u)
    win.capsule(p, close_r, RAISED, LINE)
    win.text(p, 'Schließen', close_r.x(), close_r.y(), ('u', 1.8, 600), TEXT, close_w, 1, 4.6 / 1.8)
    win.hit(close_r, lambda: close(win), name='Schließen')

    pw = T.get('power') or {}
    perf = pw.get('perf') or {}
    qt = getattr(win, 'QTELE', None) or {}
    bat = qt.get('battery') or win.BATT or {}
    chg = qt.get('charger') or {}
    parts = [ui.clock()]
    if bat.get('level') is not None:
        btxt = f'{bat["level"]} %' + (' lädt' if bat.get('charging') else '')
        if bat.get('charging') and chg.get('fast_charging'):
            btxt += ' · PD Schnellladen'
        elif not bat.get('charging') and bat.get('watts'):
            btxt += f' · {bat["watts"]:.1f} W'.replace('.', ',')
        if not bat.get('charging') and bat.get('mins_left'):
            btxt += f' ({_fmt_rem(bat["mins_left"])})'
        parts.append(btxt)
    if perf.get('cpu_mhz'):
        cm = perf['cpu_mhz']
        peak = max(cm.values()) if isinstance(cm, dict) else max(cm)
        if peak:
            parts.append(f'CPU {peak / 1000:.2f} GHz'.replace('.', ','))
    if perf.get('gpu_mhz'):
        parts.append(f'GPU {perf["gpu_mhz"]} MHz')
    if perf.get('ram_free_gib') is not None:
        parts.append(f'{perf["ram_free_gib"]:g} GB frei'.replace('.', ','))
    if perf.get('scheduler') in ('lavd', 'cosmos'):
        parts.append(perf['scheduler'].upper())
    if pw.get('temp') is not None: parts.append(f'{pw["temp"]} °C')
    if pw.get('fan') is not None: parts.append(f'Lüfter {pw["fan"]}')
    win.text(p, '  ·  '.join(parts), badge.right() + 1.4 * u, hy, ('u', 1.68, 500), MUTED,
             close_r.x() - badge.right() - 2.8 * u, 2, 4.6 / 1.68)

    footer_h = 5.6 * u
    body_top, body_bottom = 7.6 * u, H - 2.2 * u - footer_h - 1.2 * u

    def seg_row(rx, ry, rw, rh, items, active_color=FOCUS):
        """Segmented pill control inside a card: [(label, fn, is_active, hit_name)]."""
        track = QRectF(rx, ry, rw, rh)
        win.box(p, track, 1.2 * u, INK, LINE)
        iw = (rw - .5 * u) / max(1, len(items))
        for idx, item in enumerate(items):
            lbl, fn, on = item[0], item[1], item[2]
            hname = item[3] if len(item) > 3 else lbl
            ir = QRectF(rx + .25 * u + idx * iw, ry + .25 * u, iw, rh - .5 * u)
            if on:
                win.box(p, ir, 1.0 * u, active_color)
            win.text(p, lbl, ir.x(), ir.y(), ('u', 1.72, 700 if on else 500),
                     INK if on else TEXT, ir.width(), 1, ir.height() / (1.72 * u))
            win.hit(ir, lambda fn=fn: (win.ui_haptic(), touched(win), fn()), name=hname)

    def draw_body(y):
        gap = 1.3 * u
        send = ui.settings_view.thor_set
        cfg_set = ui.settings_view.config_set

        # ---- 1. FPS-Fenster (MangoHud Top-Screen Overlay) + Nachtmodus (2-col Bento) ----
        col_w = (cw - gap) / 2
        card_h1 = 9.2 * u
        hud_card = QRectF(x0, y, col_w, card_h1)
        night_card = QRectF(x0 + col_w + gap, y, col_w, card_h1)
        win.box(p, hud_card, 1.7 * u, PANEL, LINE)
        win.text(p, 'FPS-FENSTER (OBEN)', hud_card.x() + 1.6 * u, y + 1.1 * u, f_sec, FOCUS, col_w - 3.2 * u)
        cur_hud = int(win.CFG.get('hud_level') or 0)
        seg_row(hud_card.x() + 1.2 * u, y + 3.5 * u, col_w - 2.4 * u, 4.5 * u,
                [(lbl, lambda lv=lv: set_hud(win, lv), cur_hud == lv, f'hud:{lbl}') for lv, lbl in HUD_OPTS], LIVE if cur_hud else FOCUS)

        win.box(p, night_card, 1.7 * u, PANEL, LINE)
        win.text(p, 'NACHTMODUS', night_card.x() + 1.6 * u, y + 1.1 * u, f_sec, MUTED, col_w - 3.2 * u)
        cur_night = win.CFG.get('night_mode') or 'off'
        seg_row(night_card.x() + 1.2 * u, y + 3.5 * u, col_w - 2.4 * u, 4.5 * u,
                [(lbl, lambda m=m: cfg_set(win, night_mode=m), cur_night == m)
                 for m, lbl in (('off', 'Aus'), ('warm', 'Warm'), ('night', 'Nacht'))])
        y += card_h1 + gap

        # ---- 1b. Unterwegs-Sparmodus, Bypass-Ladelimit & Panel-Frequenz (Akku-Optimierung) ----
        travel_on = bool(win.CFG.get('travel_mode'))
        cur_hz = 60 if (travel_on or int(win.CFG.get('panel_hz') or 120) == 60) else 120
        col3_w = (cw - 2 * gap) / 3
        tcard = QRectF(x0, y, col3_w, card_h1)
        hzcard = QRectF(x0 + col3_w + gap, y, col3_w, card_h1)
        chgcard = QRectF(x0 + 2 * (col3_w + gap), y, col3_w, card_h1)
        win.box(p, tcard, 1.7 * u, PANEL, LIVE if travel_on else LINE)
        win.text(p, 'AKKU UNTERWEGS', tcard.x() + 1.4 * u, y + 1.1 * u, f_sec, LIVE if travel_on else MUTED, col3_w - 2.8 * u)
        seg_row(tcard.x() + 1.0 * u, y + 3.5 * u, col3_w - 2.0 * u, 4.5 * u,
                [('Normal', lambda: cfg_set(win, travel_mode=False), not travel_on, 'travel:off'),
                 ('Unterwegs', lambda: cfg_set(win, travel_mode=True), travel_on, 'travel:on')],
                LIVE if travel_on else FOCUS)

        win.box(p, hzcard, 1.7 * u, PANEL, LINE)
        win.text(p, 'DISPLAY OBEN', hzcard.x() + 1.4 * u, y + 1.1 * u, f_sec, MUTED, col3_w - 2.8 * u)
        seg_row(hzcard.x() + 1.0 * u, y + 3.5 * u, col3_w - 2.0 * u, 4.5 * u,
                [('120 Hz', lambda: cfg_set(win, travel_mode=False, panel_hz=120), cur_hz == 120, 'hz:120'),
                 ('60 Hz', lambda: cfg_set(win, panel_hz=60), cur_hz == 60, 'hz:60')])

        cur_cl = int(perf.get('charge_limit') or 100)
        win.box(p, chgcard, 1.7 * u, PANEL, LIVE if cur_cl < 100 else LINE)
        win.text(p, 'BYPASS-LIMIT', chgcard.x() + 1.4 * u, y + 1.1 * u, f_sec, LIVE if cur_cl < 100 else MUTED, col3_w - 2.8 * u)
        seg_row(chgcard.x() + 1.0 * u, y + 3.5 * u, col3_w - 2.0 * u, 4.5 * u,
                [('Aus', lambda: send(win, 'charge_limit', 100), cur_cl >= 100, 'cl:100'),
                 ('80 %', lambda: send(win, 'charge_limit', 80), cur_cl == 80, 'cl:80'),
                 ('85 %', lambda: send(win, 'charge_limit', 85), cur_cl == 85, 'cl:85')],
                LIVE if cur_cl < 100 else FOCUS)
        y += card_h1 + gap

        # ---- 2. Brightness, Volume & Thor Audio-DSP Bento Card ----
        s_rows = [(k, l) for k, l in (('bt', 'Oben'), ('bb', 'Unten'), ('vol', 'Lautstärke')) if win.SET.get(k) is not None]
        if s_rows:
            rh = 4.9 * u
            dsp_extra = 5.4 * u
            scard_h = len(s_rows) * rh + dsp_extra + 1.4 * u
            win.box(p, QRectF(x0, y, cw, scard_h), 1.8 * u, PANEL, LINE)
            sy = y + .7 * u
            muted = getattr(win, 'MUTED', False)
            for idx, (key, label) in enumerate(s_rows):
                val = win.SET[key]
                if idx:
                    p.fillRect(QRectF(x0 + 1.8 * u, sy, cw - 3.6 * u, max(1.0, .08 * u)), ui.faded(TEXT, .07))
                win.text(p, label, x0 + 1.8 * u, sy, ('u', 1.9, 500), TEXT, 17 * u, 0, rh / (1.9 * u))
                right_pad = 21 * u if key == 'vol' else 9.5 * u
                left, width = x0 + 18.5 * u, cw - 18.5 * u - right_pad
                mid = sy + rh / 2
                track = QRectF(left, mid - .55 * u, width, 1.1 * u)
                win.capsule(p, track, ui.faded(TEXT, .12))
                fill_c = WARN if (key == 'vol' and muted) else FOCUS
                if val:
                    win.capsule(p, QRectF(left, track.y(), max(track.height(), width * val / 100), track.height()), fill_c)
                p.setPen(ui.Qt.PenStyle.NoPen); p.setBrush(ui.QColor('#ffffff'))
                p.drawEllipse(QPointF(left + width * (val / 100), mid), 1.25 * u, 1.25 * u)
                win.text(p, f'{val} %', left + width + 1.0 * u, sy, ('u', 1.8, 600), MUTED, 7.2 * u, 2, rh / (1.8 * u))
                win.hit(QRectF(left - 1.4 * u, sy, width + 2.8 * u, rh),
                        lambda x, key=key, left=left, width=width: (touched(win), win.set_value(key, x, left, width)), True, key)
                if key == 'vol':
                    mr = QRectF(x0 + cw - 11.2 * u, sy + .65 * u, 9.8 * u, rh - 1.3 * u)
                    win.capsule(p, mr, WARN if muted else RAISED, None if muted else LINE)
                    win.text(p, 'Ton an' if muted else 'Ton aus', mr.x(), mr.y(), ('u', 1.65, 700 if muted else 600),
                             INK if muted else TEXT, mr.width(), 1, mr.height() / (1.65 * u))
                    win.hit(mr, lambda: (touched(win), win.toggle_mute()), name='Ton an' if muted else 'Ton aus')
                sy += rh
            p.fillRect(QRectF(x0 + 1.8 * u, sy, cw - 3.6 * u, max(1.0, .08 * u)), ui.faded(TEXT, .07))
            cur_dsp = win.CFG.get('speaker_dsp') or 'cinema'
            win.text(p, 'Klang-DSP', x0 + 1.8 * u, sy + .2 * u, ('u', 1.82, 500), TEXT, 16.5 * u, 0, 5.0 / 1.82)
            seg_row(x0 + 18.5 * u, sy + .5 * u, cw - 19.9 * u, 4.4 * u,
                    [(lbl, lambda m=m: cfg_set(win, speaker_dsp=m), cur_dsp == m, f'dsp:{m}')
                     for m, lbl in (('off', 'Aus'), ('cinema', 'Kino-Bass'), ('clear', 'Klar'), ('night', 'Nacht'))],
                    LIVE if cur_dsp != 'off' else FOCUS)
            y += scard_h + gap

        # ---- 3. OnionOS-Style Visual Game Switcher ("Schnellwechsel · Letzte Spiele") ----
        played = win.L.get('played') or {}
        cur_gid = (win.RUN or {}).get('id')
        hidden = set(win.L.get('hidden') or [])
        recents = sorted(
            (g for g in (win.L.get('games') or [])
             if g['id'] in played and (played[g['id']].get('last') or 0) > 0
             and g['id'] != cur_gid and g['id'] not in hidden and g.get('s') not in ('app', 'term')),
            key=lambda g: -(played[g['id']].get('last') or 0)
        )[:4]
        if recents:
            rc_h = 14.8 * u
            rcard = QRectF(x0, y, cw, rc_h)
            win.box(p, rcard, 1.8 * u, PANEL, LINE)
            win.text(p, 'SCHNELLWECHSEL · LETZTE SPIELE', x0 + 1.6 * u, y + 1.0 * u, f_sec, MUTED, cw - 3.2 * u)
            rw_item = (cw - 2.4 * u - 3 * 1.0 * u) / 4
            rh_item = 10.3 * u
            for ri, rg in enumerate(recents):
                rx = x0 + 1.2 * u + ri * (rw_item + 1.0 * u)
                rr = QRectF(rx, y + 3.3 * u, rw_item, rh_item)
                win.box(p, rr, 1.3 * u, RAISED, LINE)
                art_tok = rg.get('moment') or rg.get('hero') or rg.get('cover')
                art = win.thumbs.get(art_tok, max(64, round(rw_item)), max(48, round(rh_item))) if art_tok else None
                clip = ui.QPainterPath(); clip.addRoundedRect(rr, 1.3 * u, 1.3 * u)
                p.save()
                p.setClipPath(clip)
                if art:
                    p.drawImage(rr, art)
                scrim = ui.QLinearGradient(0, rr.top(), 0, rr.bottom())
                scrim.setColorAt(0.0, ui.rgba(8, 10, 16, .12 if art else 0.0))
                scrim.setColorAt(0.42, ui.rgba(8, 10, 16, .48 if art else 0.0))
                scrim.setColorAt(1.0, ui.rgba(8, 10, 16, .92 if art else .35))
                p.fillRect(rr, ui.QBrush(scrim))
                p.restore()
                if rg.get('moment'):
                    mb = QRectF(rr.right() - 8.2 * u, rr.y() + .65 * u, 7.5 * u, 2.1 * u)
                    win.capsule(p, mb, ui.rgba(8, 12, 18, .78), ui.faded(LIVE, .55))
                    win.text(p, '● Live-Bild', mb.x(), mb.y(), ('u', 1.15, 700), LIVE, mb.width(), 1, 2.1 / 1.15)
                ptxt = _fmt_play((played.get(rg['id']) or {}).get('secs'))
                sub_lbl = f'{win.sys_name(rg)} · {ptxt}' if ptxt else win.sys_name(rg)
                win.text(p, rg['t'], rx + .95 * u, rr.bottom() - 4.3 * u, ('u', 1.62, 700),
                         ui.QColor('#ffffff') if art else TEXT, rw_item - 1.9 * u)
                win.text(p, sub_lbl, rx + .95 * u, rr.bottom() - 2.15 * u, ('u', 1.35, 500),
                         ui.rgba(225, 232, 245, .86) if art else MUTED, rw_item - 1.9 * u)
                win.hit(rr, lambda g=rg: (close(win), win.confirm_quit(g) if win.RUN else win.start(g)), name='qswitch:' + rg['id'])
            y += rc_h + gap

        # ---- 4. HyperDrive, Performance, Turnip, GPU Clock, Fan, Res, FPS Cap & Scaling Card ----
        eng = T.get('engine') or {}
        has_eng = bool(eng)
        has_prof = bool(pw.get('profiles'))
        fg = getattr(win, 'FG', None)
        has_fg = bool(fg and fg.get('there'))
        is_ra = bool((win.RUN or {}).get('emu') == 'RetroArch')
        rows_n = (2 if has_eng else 0) + int(has_prof) + 2 + (3 if win.RUN else 0) + int(is_ra) + int(has_fg)
        if rows_n:
            pcard_h = 3.2 * u + rows_n * 5.4 * u + (.6 * u if not win.RUN else 0)
            pcard = QRectF(x0, y, cw, pcard_h)
            hyper_on = bool(eng.get('hyperdrive'))
            win.box(p, pcard, 1.8 * u, PANEL, LIVE if hyper_on else LINE)
            hdr_lbl = ('⚡ HYPERDRIVE AKTIV · DIESES SPIEL' if win.RUN else '⚡ HYPERDRIVE AKTIV · ENGINE') if hyper_on else ('LEISTUNG & HARDWARE (DIESES SPIEL)' if win.RUN else 'LEISTUNG & HARDWARE')
            win.text(p, hdr_lbl, x0 + 1.6 * u, y + 1.0 * u, f_sec, LIVE if hyper_on else MUTED, cw - 3.2 * u)
            py = y + 3.3 * u
            if has_eng:
                seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                        [('Standard', lambda: send(win, 'hyperdrive', False), not hyper_on, 'hd:off'),
                         ('⚡ HyperDrive (WinNative · FEX Fast · LAVD · Big-Cores)', lambda: send(win, 'hyperdrive', True), hyper_on, 'hd:on')],
                        LIVE if hyper_on else FOCUS)
                py += 5.4 * u
                cur_drv = eng.get('turnip') or 'stable'
                drv_opts = eng.get('turnip_drivers') or [['stable', 'Stable'], ['devel', 'Devel'], ['winnative', 'WinNative']]
                seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                        [(f'Turnip {dlbl.split(" (")[0]}', lambda did=did: send(win, 'turnip', did), cur_drv == did, f'drv:{did}')
                         for did, dlbl in drv_opts[:4]])
                py += 5.4 * u
            if has_prof:
                cur_prof = (win.RUN or {}).get('profile') or pw.get('profile')
                seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                        [(label, (lambda v=v: win.set_gameopt(profile=v)) if win.RUN else (lambda v=v: send(win, 'profile', v)),
                          cur_prof == v) for v, label in pw['profiles']])
                py += 5.4 * u
            # Adreno 740 GPU Clock + Fan Mode
            cur_gpu = int(perf.get('gpu_mhz') or 0) if perf.get('gpu_gov') == 'performance' else 0
            seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                    [(lbl, lambda mhz=mhz: send(win, 'gpu_clock', mhz),
                      (cur_gpu == 0 if mhz == 0 else abs(cur_gpu - mhz) < 35), f'gpu:{mhz}')
                     for mhz, lbl in ((0, 'GPU Auto'), (401, '401 MHz'), (550, '550 MHz'), (680, '680 Max'))])
            py += 5.4 * u
            cur_fan = perf.get('fan_mode') or 'auto'
            seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                    [(lbl, lambda fm=fm: send(win, 'fan_mode', fm), cur_fan == fm, f'fan:{fm}')
                     for fm, lbl in (('auto', 'Lüfter Auto'), ('quiet', 'Leise'), ('cool', 'Kühl'), ('max', 'Max'))])
            py += 5.4 * u
            if win.RUN:
                cur_res = int((win.RUN or {}).get('res') or 0)
                seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                        [(lbl, lambda rh=rh: win.set_gameopt(res=rh), cur_res == rh, f'res:{rh}')
                         for rh, lbl in ((0, '1080p Nativ'), (900, '900p SGSR'), (720, '720p Boost'))])
                py += 5.4 * u
                cur_fps = (win.RUN or {}).get('fps') or 0
                seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                        [(lbl, lambda hz=hz: win.set_gameopt(fps=hz), cur_fps == hz)
                         for hz, lbl in ((0, 'Offen'), (60, '60 FPS'), (45, '45 FPS'), (40, '40 FPS'), (30, '30 FPS'))])
                py += 5.4 * u
                cur_scale = (win.RUN or {}).get('scale') or 'linear'
                seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                        [(lbl, lambda m=m: win.set_gameopt(scale=m), cur_scale == m)
                         for m, lbl in (('linear', 'Standard'), ('sgsr', 'SGSR'), ('fsr', 'FSR'), ('pixel', 'Pixel'))])
                py += 5.4 * u
                if is_ra:
                    cur_sh = (win.RUN or {}).get('shader') or ''
                    seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                            [(lbl, lambda sh=sh: win.set_gameopt(shader=sh), cur_sh == sh, f'rsh:{sh or "global"}')
                             for sh, lbl in (('', 'Shader Global'), ('sharp', 'Scharf'), ('crt', 'CRT-OLED'), ('lcd', 'Handheld-LCD'))])
                    py += 5.4 * u
            if has_fg:
                seg_row(x0 + 1.2 * u, py, cw - 2.4 * u, 4.5 * u,
                        [('Frame Gen: Aus', lambda: win.post('api/framegen', {'on': False}, then=lambda r: r and (setattr(win, 'FG', r), win.update())), not fg['on']),
                         ('Frame Gen: An', lambda: win.post('api/framegen', {'on': True}, then=lambda r: r and (setattr(win, 'FG', r), win.update())), bool(fg['on']))])
            y += pcard_h + gap

        # ---- 5. Stick-Licht & Aufnahmen (2-col or full-width Bento) ----
        rgb = T.get('rgb')
        rec = (win.REC or {}).get('on')
        if rgb:
            rc_left = QRectF(x0, y, col_w, 9.0 * u)
            rc_right = QRectF(x0 + col_w + gap, y, col_w, 9.0 * u)
            win.box(p, rc_left, 1.7 * u, PANEL, LINE)
            win.text(p, 'STICK-BELEUCHTUNG', rc_left.x() + 1.6 * u, y + 1.0 * u, f_sec, MUTED, col_w - 13 * u)
            sync_on = bool(win.CFG.get('rgb_sync', True))
            sr_btn = QRectF(rc_left.right() - 11.4 * u, y + .65 * u, 10.2 * u, 2.3 * u)
            win.capsule(p, sr_btn, ui.faded(FOCUS, .22) if sync_on else RAISED, FOCUS if sync_on else LINE)
            win.text(p, 'Spiel-Farbe', sr_btn.x(), sr_btn.y(), ('u', 1.28, 700 if sync_on else 500),
                     FOCUS if sync_on else MUTED, sr_btn.width(), 1, 2.3 / 1.28)
            win.hit(sr_btn, lambda: (win.ui_haptic(), touched(win), cfg_set(win, rgb_sync=not sync_on)), name='qrgb_sync')
            on_rgb = bool(rgb.get('enabled'))
            cur_c = str(rgb.get('color', 'FFFFFF')).upper()
            tog_r = QRectF(rc_left.x() + 1.2 * u, y + 3.4 * u, 9.5 * u, 4.4 * u)
            win.capsule(p, tog_r, ui.QColor('#' + cur_c) if on_rgb else RAISED, None if on_rgb else LINE)
            win.text(p, 'An' if on_rgb else 'Aus', tog_r.x(), tog_r.y(), ('u', 1.75, 700),
                     INK if on_rgb else TEXT, tog_r.width(), 1, 4.4 / 1.75)
            win.hit(tog_r, lambda: (touched(win), send(win, 'rgb', {'enabled': not on_rgb})), name='qrgb_tog')
            # Color dots
            sx = tog_r.right() + 1.1 * u
            avail_dots = int((rc_left.right() - 1.2 * u - sx) / (3.9 * u))
            for cname, hex_c in ui.settings_view.COLORS[:max(4, avail_dots)]:
                dr = QRectF(sx, y + 4.0 * u, 3.2 * u, 3.2 * u)
                sel = (cur_c == hex_c and on_rgb)
                p.setPen(ui.QPen(TEXT if sel else LINE, (.32 if sel else .12) * u))
                p.setBrush(ui.QColor('#' + hex_c))
                p.drawEllipse(dr)
                win.hit(dr.adjusted(-.3 * u, -.3 * u, .3 * u, .3 * u),
                        lambda hc=hex_c: (touched(win), send(win, 'rgb', {'color': hc, 'enabled': True})), name='qrgb:' + cname)
                sx += 3.85 * u

            win.box(p, rc_right, 1.7 * u, PANEL, LINE)
            win.text(p, 'AUFNAHME & FOTO', rc_right.x() + 1.6 * u, y + 1.0 * u, f_sec, MUTED, col_w - 3.2 * u)
            bw_r = (col_w - 3.4 * u) / 2
            b_rec = QRectF(rc_right.x() + 1.2 * u, y + 3.4 * u, bw_r, 4.4 * u)
            b_shot = QRectF(b_rec.right() + 1.0 * u, y + 3.4 * u, bw_r, 4.4 * u)
            rec_lbl = '■ Aufnahme stoppen' if rec else '● Aufnahme starten'
            win.button(p, b_rec, rec_lbl, lambda: (touched(win), record(win, not rec)), ('u', 1.68, 700 if rec else 600),
                       INK if rec else TEXT, WARN if rec else RAISED, None, 1.1)
            win.button(p, b_shot, 'Bildschirmfoto', lambda: (touched(win), shot(win)), ('u', 1.68, 600), TEXT, RAISED, None, 1.1)
            y += 9.0 * u + gap
        else:
            rc_full = QRectF(x0, y, cw, 8.8 * u)
            win.box(p, rc_full, 1.7 * u, PANEL, LINE)
            win.text(p, 'AUFNAHME & FOTO', x0 + 1.6 * u, y + 1.0 * u, f_sec, MUTED, cw - 3.2 * u)
            bw_r = (cw - 3.6 * u) / 2
            rec_lbl = '■ Aufnahme stoppen' if rec else '● Aufnahme starten'
            win.button(p, QRectF(x0 + 1.2 * u, y + 3.3 * u, bw_r, 4.4 * u), rec_lbl,
                       lambda: (touched(win), record(win, not rec)), f_btn, INK if rec else TEXT, WARN if rec else RAISED, None, 1.2)
            win.button(p, QRectF(x0 + 2.4 * u + bw_r, y + 3.3 * u, bw_r, 4.4 * u), 'Bildschirmfoto',
                       lambda: (touched(win), shot(win)), f_btn, TEXT, RAISED, None, 1.2)
            y += 8.8 * u + gap

        if win.REC and win.REC.get('last') and not rec:
            win.text(p, 'Gespeichert: ' + win.REC['last'], x0 + .6 * u, y - .4 * u, ('u', 1.65, 400), MUTED, cw)
            y += 2.2 * u
        return y

    win.scroller(p, 'quick', QRectF(0, body_top, W, body_bottom - body_top), draw_body)

    # ---- Docked Bottom Action Bar ----
    fy = H - 2.2 * u - footer_h
    f_acts = []
    if win.RUN:
        f_acts.append(('Zu Tandem', lambda: (close(win), win.post('api/pause')), RAISED, TEXT))
    else:
        f_acts.append(('Zufallsspiel', lambda: (close(win), win.pick_random()), ui.faded(FOCUS, .18), FOCUS))
        f_acts.append(('Bildschirmschoner', lambda: (close(win), win.post('api/saver', {'open': True})), RAISED, TEXT))
    f_acts.append(('Standby', lambda: (close(win), win.post('api/action', {'name': 'suspend'})), RAISED, TEXT))
    if win.RUN:
        f_acts.append(('Spiel beenden', lambda: (close(win), win.confirm_quit()), ui.faded(WARN, .18), WARN))
    fgap = 1.2 * u
    fw = (cw - fgap * (len(f_acts) - 1)) / len(f_acts)
    for idx, (lbl, fn, bg, fg_c) in enumerate(f_acts):
        win.button(p, QRectF(x0 + idx * (fw + fgap), fy, fw, footer_h), lbl, fn, ('u', 1.95, 600), fg_c, bg, LINE, 1.3)


def set_hud(win, level):
    win.CFG['hud_level'] = level
    win.post('api/hud', {'level': level})
    win.update()


def close(win):
    win.QUICK = None
    win.update()


def record(win, on):
    win.toast('Aufnahme startet …' if on else 'Aufnahme wird gespeichert …')
    win.post('api/record', {'action': 'start' if on else 'stop'},
             then=lambda r: r and (win.toast(r['error']) if r.get('error') else (setattr(win, 'REC', r), win.update())))


def shot(win):
    win.post('api/shot', {}, then=lambda r: r and win.toast(r.get('error') or 'Bildschirmfoto gespeichert'))
