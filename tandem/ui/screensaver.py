"""Dual-Screen OLED Screensaver for Toravo Tandem on the AYN Thor.
Both screens share wall-clock time `time.time()`, so stars, aurora ribbons, and floating library covers
flow seamlessly across the hinge from the top OLED screen into the bottom OLED screen while keeping
a pure #000000 background and zero stationary pixels for complete OLED burn-in protection."""
import math, random, time

ui = None  # set by tandem_ui

STYLES = (
    ('kosmos', 'Thor Kosmos'),
    ('arcade', 'Arcade-Schaufenster'),
    ('aurora', 'Dual-Aurora'),
    ('minimal', 'OLED-Uhr pur'),
)


def _date_str(en=False):
    tm = time.localtime()
    if en:
        wd = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[tm.tm_wday]
        mo = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')[tm.tm_mon - 1]
        return f'{wd}, {tm.tm_mday} {mo}'
    wd = ('Mo.', 'Di.', 'Mi.', 'Do.', 'Fr.', 'Sa.', 'So.')[tm.tm_wday]
    mo = ('Jan.', 'Feb.', 'März', 'Apr.', 'Mai', 'Juni', 'Juli', 'Aug.', 'Sep.', 'Okt.', 'Nov.', 'Dez.')[tm.tm_mon - 1]
    return f'{wd} {tm.tm_mday}. {mo}'


def _cover_games(win):
    games = [g for g in (win.L.get('games') or []) if (g.get('box') or g.get('cover')) and g.get('s') not in ('app', 'term')]
    return games


def _game_color(win, game):
    QColor = ui.QColor
    key = (game.get('cover') or game.get('box')) if game else None
    hex_c = ui.ACCENTS.get(key) if key else None
    if hex_c:
        return QColor(hex_c)
    palette = ('#946ef8', '#ffb23e', '#34d399', '#38bdf8', '#f472b6', '#fb7185')
    idx = ui.jhash(game['id']) % len(palette) if game else 0
    return QColor(palette[idx])


def _draw_game_art(win, p, gm, cx, cy, base_w, base_h, col, max_px=340):
    """Draw a game's original retail packaging (`box`) at its true physical aspect ratio with subtle 3D case depth,
    or fall back to its standard library `cover` when no original box exists. Returns the drawn QRectF."""
    u, QRectF, QPointF, QColor, QPainterPath, QPolygonF = (
        win.u, ui.QRectF, ui.QPointF, ui.QColor, ui.QPainterPath, getattr(ui, 'QPolygonF', None))
    has_box = bool(gm.get('box'))
    art_key = gm.get('box') or gm.get('cover')
    img = win.thumbs.get(art_key, max_px, max_px, cover=False) if has_box else win.thumbs.get(art_key, int(max_px * 0.72), max_px, cover=True)
    cw, ch = base_w, base_h
    if has_box and img and not getattr(img, 'isNull', lambda: True)() and img.height() > 0:
        ar = max(0.56, min(1.52, img.width() / img.height()))
        area = base_w * base_h * 1.06
        ch = math.sqrt(area / ar)
        cw = ch * ar
    cr = QRectF(cx - cw / 2, cy - ch / 2, cw, ch)
    if img and not getattr(img, 'isNull', lambda: True)():
        if has_box:
            # Check if the retail box scan already carries a transparent curved plastic case silhouette (e.g. Switch box PNG)
            alpha_corner = img.width() > 4 and img.height() > 4 and ((img.pixel(1, 1) >> 24) & 255) < 180
            if alpha_corner:
                p.drawImage(cr, img)
            else:
                rad = 0.42 * u
                # Subtle 3D physical box spine / thickness on the left edge + soft offset shadow
                spine = max(2.0, 0.44 * u)
                win.box(p, cr.translated(0.42 * u, 0.58 * u), rad, QColor(0, 0, 0, 165))
                if QPolygonF is not None:
                    side = QPolygonF([
                        QPointF(cr.left() - spine, cr.top() + 0.32 * u),
                        QPointF(cr.left() + 0.1 * u, cr.top()),
                        QPointF(cr.left() + 0.1 * u, cr.bottom()),
                        QPointF(cr.left() - spine, cr.bottom() - 0.32 * u),
                    ])
                    p.setPen(ui.Qt.PenStyle.NoPen)
                    p.setBrush(QColor(max(14, col.red() // 3), max(14, col.green() // 3), max(18, col.blue() // 3), 235))
                    p.drawPolygon(side)
                clip = QPainterPath()
                clip.addRoundedRect(cr, rad, rad)
                p.save()
                p.setClipPath(clip)
                p.drawImage(cr, img)
                p.restore()
                win.box(p, cr, rad, None, QColor(255, 255, 255, 68), max(1.0, 0.10 * u))
        else:
            rad = 1.35 * u
            win.box(p, cr.translated(0.35 * u, 0.50 * u), rad, QColor(0, 0, 0, 150))
            clip = QPainterPath()
            clip.addRoundedRect(cr, rad, rad)
            p.save()
            p.setClipPath(clip)
            p.drawImage(cr, img)
            p.restore()
            win.box(p, cr, rad, None, QColor(255, 255, 255, 56), max(1.0, 0.11 * u))
    else:
        rad = 1.35 * u
        win.box(p, cr, rad, QColor(20, 22, 34, 210), QColor(col.red(), col.green(), col.blue(), 110), max(1.0, 0.11 * u))
        win.text(p, gm['t'], cr.x() + u, cr.center().y() - 1.5 * u, ('u', 1.45, 600), QColor(240, 240, 248, 210), cw - 2 * u, 1, 1.3, 2)
    return cr


def _draw_starfield(p, W, H, side_idx, t, count=54):
    QColor, QPointF = ui.QColor, ui.QPointF
    p.setPen(ui.Qt.PenStyle.NoPen)
    rng = random.Random(90210)
    total_h = 2.0  # 0..1 = top screen, 1..2 = bottom screen
    for i in range(count):
        nx = rng.random()
        ny0 = rng.random() * total_h
        depth = 0.35 + 0.65 * rng.random()
        speed = 0.014 * depth
        twinkle = 0.55 + 0.45 * math.sin(t * (1.1 + depth) + i * 1.7)
        ny = (ny0 + t * speed) % total_h
        local_y = ny - side_idx
        if -0.04 <= local_y <= 1.04:
            alpha = int(max(18, min(205, 195 * depth * twinkle)))
            rad = (0.7 + 1.45 * depth) * (W / 1280.0)
            tint = (210, 222, 255) if i % 5 == 0 else ((255, 228, 196) if i % 7 == 0 else (245, 246, 252))
            p.setBrush(QColor(tint[0], tint[1], tint[2], alpha))
            p.drawEllipse(QPointF(nx * W, local_y * H), rad, rad)


def _draw_hud_pill(win, p, cx, cy, sub_line=''):
    u, QRectF, QColor = win.u, ui.QRectF, ui.QColor
    en = win.CFG.get('lang') == 'en'
    clk = ui.clock()
    dt = _date_str(en)
    B = win.BATT or {}
    bat_str = f'{B["level"]} %' + ((' · charging' if en else ' · lädt') if B.get('charging') else '') if B.get('level') is not None else ''
    meta = '  ·  '.join(x for x in (dt, bat_str) if x)

    pw = (44 if not sub_line else 52) * u
    ph = (12.8 if not sub_line else 15.6) * u
    r = QRectF(cx - pw / 2, cy - ph / 2, pw, ph)
    win.box(p, r, 2.4 * u, QColor(12, 13, 20, 212), QColor(255, 255, 255, 34), max(1.0, 0.1 * u))
    win.text(p, clk, r.x(), r.y() + 1.1 * u, ('u', 4.6, 700, -.03), QColor(244, 244, 250, 238), pw, 1)
    win.text(p, meta, r.x() + 1.5 * u, r.y() + 7.4 * u, ('u', 1.65, 500), QColor(168, 170, 190, 210), pw - 3 * u, 1)
    if sub_line:
        win.text(p, sub_line, r.x() + 1.8 * u, r.y() + 10.6 * u, ('u', 1.55, 600), ui.faded(ui.FOCUS, .88), pw - 3.6 * u, 1)


def _draw_kosmos(win, p, W, H, side_idx, t):
    u, QRectF, QPointF, QColor, QRadialGradient, QPainterPath = (
        win.u, ui.QRectF, ui.QPointF, ui.QColor, ui.QRadialGradient, ui.QPainterPath)
    games = _cover_games(win)
    # Soft drifting cosmic nebula across the dual-screen hinge
    neb_x = W * (0.5 + 0.26 * math.sin(t * 0.09))
    neb_global_y = 1.0 + 0.35 * math.cos(t * 0.07)
    neb_y = (neb_global_y - side_idx) * H
    spot_game = games[int(t // 10) % len(games)] if games else None
    acc = _game_color(win, spot_game)
    grad = QRadialGradient(QPointF(neb_x, neb_y), W * 0.62)
    grad.setColorAt(0.0, QColor(acc.red(), acc.green(), acc.blue(), 38))
    grad.setColorAt(0.55, QColor(90, 68, 185, 16))
    grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.fillRect(0, 0, W, H, ui.QBrush(grad))

    _draw_starfield(p, W, H, side_idx, t, count=64)
    if side_idx == 0:
        tx = W * (0.5 + 0.24 * math.cos(t * 0.075))
        ty = H * (0.14 + 0.06 * math.sin(t * 0.095))
        win.text(p, 'TORAVO  ·  AYN THOR', tx - 24 * u, ty, ('u', 1.45, 700, .24), QColor(245, 245, 252, 76), 48 * u, 1)

    # Floating library boxes/covers gliding continuously from top screen (0..1) into bottom screen (1..2);
    # prefer games with original retail packaging (`box`) while still mixing in the rest of the library
    if games:
        boxed = [g for g in games if g.get('box')]
        pool = boxed + [g for g in games if not g.get('box')][::3] if len(boxed) >= 6 else games
        n_slots = min(7, len(pool))
        span = 2.36  # 0..2.36 wraps smoothly outside both viewports
        lanes = (0.15, 0.83, 0.35, 0.66, 0.22, 0.76, 0.50)
        for slot in range(n_slots):
            speed = 0.030 + (slot % 3) * 0.008
            raw = t * speed + slot * (span / n_slots)
            cycle = int(raw // span)
            gy = (raw % span) - 0.18  # -0.18 .. 2.18
            local_cy = (gy - side_idx) * H
            cw = (13.0 + (slot % 3) * 2.2) * u
            ch = cw * 1.36
            if local_cy + ch * 0.85 < 0 or local_cy - ch * 0.85 > H:
                continue
            g_idx = (slot * 13 + cycle * 7) % len(pool)
            gm = pool[g_idx]
            cx = W * (lanes[slot % len(lanes)] + 0.035 * math.sin(t * 0.35 + slot * 2.1))
            tilt = 3.6 * math.sin(t * 0.42 + slot * 1.5)
            col = _game_color(win, gm)

            p.save()
            p.translate(cx, local_cy)
            p.rotate(tilt)
            # Soft colored aura behind original box / cover
            halo = QRadialGradient(QPointF(0, 0), cw * 1.05)
            halo.setColorAt(0.0, QColor(col.red(), col.green(), col.blue(), 60))
            halo.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
            p.setPen(ui.Qt.PenStyle.NoPen)
            p.setBrush(ui.QBrush(halo))
            p.drawEllipse(QPointF(0, 0), cw * 1.05, ch * 0.85)
            _draw_game_art(win, p, gm, 0.0, 0.0, cw, ch, col, max_px=340)
            p.restore()

    # Drifting OLED Glass HUD on bottom screen
    if side_idx == 1:
        hx = W * (0.5 + 0.20 * math.sin(t * 0.11))
        hy = H * (0.52 + 0.22 * math.cos(t * 0.083))
        sub = f'★ {spot_game["t"]}' if spot_game else ''
        _draw_hud_pill(win, p, hx, hy, sub)


def _draw_arcade(win, p, W, H, side_idx, t):
    u, QRectF, QPointF, QColor, QRadialGradient, QPainterPath = (
        win.u, ui.QRectF, ui.QPointF, ui.QColor, ui.QRadialGradient, ui.QPainterPath)
    games = _cover_games(win)
    period = 12.0
    slot = int(t // period)
    phase = (t % period) / period
    # Smooth OLED fade at start & end of each 12s showcase
    fade = min(1.0, phase / 0.12, (1.0 - phase) / 0.12)
    fade = max(0.0, fade)
    gm = games[(slot * 19 + 5) % len(games)] if games else None
    col = _game_color(win, gm)

    _draw_starfield(p, W, H, side_idx, t * 0.6, count=36)

    dx = 2.8 * u * math.sin(t * 0.19)
    dy = 2.2 * u * math.cos(t * 0.15)

    if side_idx == 0 and gm:
        p.save()
        p.setOpacity(fade)
        cx, cy = W * 0.5 + dx, H * 0.48 + dy
        halo = QRadialGradient(QPointF(cx - 16 * u, cy), W * 0.46)
        halo.setColorAt(0.0, QColor(col.red(), col.green(), col.blue(), 68))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, W, H, ui.QBrush(halo))

        cw, ch = 22.0 * u, 30.5 * u
        cr = _draw_game_art(win, p, gm, cx - 22.5 * u, cy, cw, ch, col, max_px=480)

        tx = max(cr.right() + 4.0 * u, cx - 6.5 * u)
        tw = max(28 * u, (cx + 42 * u) - tx)
        ty = cy - 11.5 * u
        sys_lbl = win.sys_name(gm).upper()
        meta_bits = [sys_lbl]
        if gm.get('year'): meta_bits.append(str(gm['year']))
        if gm.get('dev'): meta_bits.append(gm['dev'])
        win.text(p, '  ·  '.join(meta_bits), tx, ty, ('u', 1.45, 700, .12), col, tw)
        ty += 3.0 * u
        ty += win.text(p, gm['t'], tx, ty, ('d', 4.4, 700, -.02), QColor(246, 246, 252), tw, 0, 1.08, 2) + 1.4 * u
        if gm.get('desc'):
            ty += win.text(p, gm['desc'], tx, ty, ('b', 1.75, 400), QColor(175, 177, 195), tw, 0, 1.38, 3) + 1.4 * u
        secs = int(((win.L.get('played') or {}).get(gm['id']) or {}).get('secs') or 0)
        en = win.CFG.get('lang') == 'en'
        stat_txt = ((f'Played {ui.hours(secs)}' if en else f'Gespielt: {ui.hours(secs)}') if secs > 60
                    else ('Ready in your library' if en else 'Bereit in deiner Bibliothek'))
        win.text(p, stat_txt, tx, ty, ('u', 1.65, 600), QColor(145, 148, 168), tw)
        p.restore()
    else:
        # Bottom screen: harmonic equalizer bars + drifting HUD clock
        bars = 28
        bw = 1.15 * u
        gap = 0.75 * u
        total_w = bars * bw + (bars - 1) * gap
        bx0 = W * 0.5 - total_w / 2 + dx
        base_y = H * 0.76 + dy
        p.setPen(ui.Qt.PenStyle.NoPen)
        for bi in range(bars):
            wave = (0.35 + 0.35 * math.sin(t * 2.1 + bi * 0.42) + 0.30 * math.cos(t * 1.35 - bi * 0.27))
            bh = (2.2 + 9.5 * max(0.08, wave)) * u
            alpha = int(55 + 125 * max(0.0, wave))
            p.setBrush(QColor(col.red(), col.green(), col.blue(), alpha))
            br = QRectF(bx0 + bi * (bw + gap), base_y - bh / 2, bw, bh)
            p.drawRoundedRect(br, bw / 2, bw / 2)
        en = win.CFG.get('lang') == 'en'
        prompt = 'Press any button to wake' if en else 'Beliebige Taste zum Aufwecken'
        _draw_hud_pill(win, p, W * 0.5 - dx * 0.8, H * 0.36 - dy * 0.8, prompt)


def _draw_aurora(win, p, W, H, side_idx, t):
    QPointF, QColor, QPainterPath, QLinearGradient = ui.QPointF, ui.QColor, ui.QPainterPath, ui.QLinearGradient
    _draw_starfield(p, W, H, side_idx, t * 0.45, count=42)
    ribbons = (
        (0.32, '#34d399', '#0ea5e9', 0.31, 1.0),
        (0.68, '#946ef8', '#ec4899', 0.24, -1.3),
        (1.18, '#38bdf8', '#818cf8', 0.28, 0.8),
        (1.56, '#ffb23e', '#946ef8', 0.22, -0.9),
    )
    steps = 28
    for g_center, c_hex1, c_hex2, speed, ph in ribbons:
        base_y = (g_center - side_idx + 0.14 * math.sin(t * 0.13 + ph)) * H
        if base_y < -H * 0.45 or base_y > H * 1.45:
            continue
        c1, c2 = QColor(c_hex1), QColor(c_hex2)
        band_h = H * 0.34
        path = QPainterPath()
        pts_top, pts_bot = [], []
        for i in range(steps + 1):
            xf = i / steps
            x = xf * W
            wy = (math.sin(xf * 4.4 + t * speed + ph) * H * 0.09
                  + math.cos(xf * 2.3 - t * speed * 0.7) * H * 0.05)
            thickness = band_h * (0.45 + 0.55 * math.sin(xf * math.pi))
            pts_top.append(QPointF(x, base_y + wy - thickness * 0.5))
            pts_bot.append(QPointF(x, base_y + wy + thickness * 0.5))
        path.moveTo(pts_top[0])
        for pt in pts_top[1:]:
            path.lineTo(pt)
        for pt in reversed(pts_bot):
            path.lineTo(pt)
        path.closeSubpath()

        lg = QLinearGradient(0, base_y - band_h * 0.6, W, base_y + band_h * 0.6)
        lg.setColorAt(0.0, QColor(c1.red(), c1.green(), c1.blue(), 0))
        lg.setColorAt(0.3, QColor(c1.red(), c1.green(), c1.blue(), 54))
        lg.setColorAt(0.7, QColor(c2.red(), c2.green(), c2.blue(), 48))
        lg.setColorAt(1.0, QColor(c2.red(), c2.green(), c2.blue(), 0))
        p.setPen(ui.Qt.PenStyle.NoPen)
        p.setBrush(ui.QBrush(lg))
        p.drawPath(path)

    if side_idx == 1:
        hx = W * (0.5 + 0.22 * math.sin(t * 0.09))
        hy = H * (0.5 + 0.22 * math.cos(t * 0.07))
        _draw_hud_pill(win, p, hx, hy)


def _draw_minimal(win, p, W, H, side_idx, t):
    u, QColor = win.u, ui.QColor
    spot = random.Random(int(t // 45) + side_idx * 17).random
    x = (10 + 62 * spot()) * u
    y = (12 + 68 * spot()) * H / 100
    win.text(p, ui.clock(), x, y, ('u', 4.2, 600, -.02), QColor(115, 118, 136))
    if side_idx == 1 and win.BATT and win.BATT.get('level') is not None:
        win.text(p, f'{win.BATT["level"]} %  ·  {_date_str(win.CFG.get("lang") == "en")}',
                 x, y + 5.2 * u, ('u', 1.65, 400), QColor(82, 85, 100))


def draw(win, p):
    """Paints one frame of the active OLED screensaver and schedules the next smooth frame."""
    W, H = win.width(), win.height()
    p.fillRect(0, 0, W, H, ui.QColor(0, 0, 0))
    style = win.CFG.get('saver_style') or 'kosmos'
    side_idx = 0 if win.side == 'top' else 1
    t = time.time()
    if style == 'minimal':
        _draw_minimal(win, p, W, H, side_idx, t)
        ui.QTimer.singleShot(15000, win.update)
        return
    if style == 'arcade':
        _draw_arcade(win, p, W, H, side_idx, t)
    elif style == 'aurora':
        _draw_aurora(win, p, W, H, side_idx, t)
    else:
        _draw_kosmos(win, p, W, H, side_idx, t)
    if getattr(ui, 'os', None) is None or __import__('os').environ.get('QT_QPA_PLATFORM') != 'offscreen':
        ui.QTimer.singleShot(34, win.update)  # ~30 fps smooth dual-screen motion on OLED
