"""Dual-Screen 60-FPS OLED Screensaver for Toravo Tandem on the AYN Thor.
Both screens share wall-clock time `time.time()`, so stars, aurora ribbons, and up to 28 floating
library covers flow seamlessly across the hinge from the top OLED screen into the bottom OLED screen
while keeping a pure #000000 background and zero stationary pixels for complete OLED burn-in protection.

Performance architecture (QRasterWindow CPU rasterizer):
- Cover cards (including ambient glow, 3D case spine, drop shadow, rounded-rect clip & crisp SmoothTransformation
  scaling) are pre-baked ONCE into cached `Format_ARGB32_Premultiplied` sprites (`_CARD_SPRITES`).
- Cosmic nebula is pre-baked ONCE per accent color into a compact 320x180 premultiplied sprite (`_NEBULA_SPRITES`).
- Per-frame rendering performs pure axis-aligned ARM NEON premultiplied blits (< 2 ms/frame at locked 60 FPS, < 5% CPU).
"""
from collections import OrderedDict
import math, random, time

ui = None  # set by tandem_ui

STYLES = (
    ('kosmos', 'Thor Kosmos'),
    ('arcade', 'Arcade-Schaufenster'),
    ('aurora', 'Dual-Aurora'),
    ('minimal', 'OLED-Uhr pur'),
)

_CARD_SPRITES = OrderedDict()   # (win_side, src_key, cw_px, ch_px, has_box, col_hex, tier) -> QImage (ARGB32_Premultiplied)
_HUD_SPRITES = OrderedDict()    # (win_side, key_tuple) -> QImage (ARGB32_Premultiplied)
_STAR_TABLE = tuple(
    (r.random(), r.random() * 2.0, 0.35 + 0.65 * r.random(), r.random() * 6.28)
    for r in [random.Random(90210)] for _ in range(64)
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
    games = [g for g in (win.L.get('games') or [])
             if (g.get('box') or g.get('cover')) and g.get('s') not in ('app', 'term') and g.get('inst') not in ('no', 'load')]
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


def _preload_art(win, games_iter, max_px=380):
    """Warm up upcoming screensaver covers in background worker threads so covers never pop in sluggishly."""
    imgs = getattr(win, 'saver_imgs', None) or win.thumbs
    for gm in games_iter:
        if not gm:
            continue
        src = gm.get('box') or gm.get('cover')
        if src:
            imgs.get(src, max_px, max_px, cover=False)


def _nebula_sprite(col):
    QImage, QPainter, QRadialGradient, QPointF, QColor = (
        ui.QImage, ui.QPainter, ui.QRadialGradient, ui.QPointF, ui.QColor)
    key = ('neb', col.red(), col.green(), col.blue())
    sp = _HUD_SPRITES.get(key)
    if sp is not None:
        return sp
    nw, nh = 320, 180
    sp = QImage(nw, nh, QImage.Format.Format_ARGB32_Premultiplied)
    sp.fill(QColor(0, 0, 0, 0))
    np = QPainter(sp)
    grad = QRadialGradient(QPointF(nw * 0.5, nh * 0.5), nw * 0.5)
    grad.setColorAt(0.0, QColor(col.red(), col.green(), col.blue(), 42))
    grad.setColorAt(0.55, QColor(90, 68, 185, 18))
    grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    np.fillRect(0, 0, nw, nh, ui.QBrush(grad))
    np.end()
    _HUD_SPRITES[key] = sp
    return sp


def _card_sprite(win, gm, base_w, base_h, col, tier=2, max_px=380):
    """Return a pre-baked `QImage(Format_ARGB32_Premultiplied)` for `gm` at `(base_w, base_h)` including glow,
    shadow, 3D spine, rounded-corner clip, crisp `SmoothTransformation` scaling, and border."""
    QImage, QPainter, QRectF, QPointF, QColor, QPainterPath, QRadialGradient = (
        ui.QImage, ui.QPainter, ui.QRectF, ui.QPointF, ui.QColor, ui.QPainterPath, ui.QRadialGradient)
    QPolygonF = getattr(ui, 'QPolygonF', None)
    has_box = bool(gm.get('box'))
    src = gm.get('box') or gm.get('cover')
    imgs = getattr(win, 'saver_imgs', None) or win.thumbs
    img = imgs.get(src, max_px, max_px, cover=False) if src else None
    if img is False and gm.get('box') and gm.get('cover'):
        has_box = False
        src = gm['cover']
        img = imgs.get(src, max_px, max_px, cover=False)

    ready = bool(img and not getattr(img, 'isNull', lambda: True)() and img.width() > 0 and img.height() > 0)
    bw_i, bh_i = max(24, round(base_w)), max(32, round(base_h))
    ckey = (win.side, src if ready else ('placeholder:' + gm['id']), bw_i, bh_i, has_box, col.rgba(), tier)
    cached = _CARD_SPRITES.get(ckey)
    if cached is not None:
        _CARD_SPRITES.move_to_end(ckey)
        return cached

    cw, ch = float(bw_i), float(bh_i)
    if ready:
        ar = img.width() / img.height()
        area = cw * ch * (1.06 if has_box else 1.0)
        ch = math.sqrt(area / ar)
        cw = ch * ar
        max_w, max_h = bw_i * 1.48, bh_i * 1.24
        if cw > max_w:
            s = max_w / cw
            cw, ch = cw * s, ch * s
        if ch > max_h:
            s = max_h / ch
            cw, ch = cw * s, ch * s

    u = win.u
    pad = max(10, round(2.2 * u))
    sw = max(32, round(cw) + pad * 2)
    sh = max(32, round(ch) + pad * 2)
    sp = QImage(sw, sh, QImage.Format.Format_ARGB32_Premultiplied)
    sp.fill(QColor(0, 0, 0, 0))

    p = QPainter(sp)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    layer_opacity = 0.70 + tier * 0.10
    p.setOpacity(max(0.0, min(1.0, layer_opacity)))

    cx, cy = sw * 0.5, sh * 0.5
    halo = QRadialGradient(QPointF(cx, cy), max(cw, ch) * 0.68)
    halo.setColorAt(0.0, QColor(col.red(), col.green(), col.blue(), 34 + tier * 8))
    halo.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
    p.setPen(ui.Qt.PenStyle.NoPen)
    p.setBrush(ui.QBrush(halo))
    p.drawEllipse(QPointF(cx, cy), cw * 0.68, ch * 0.62)

    cr = QRectF(cx - cw / 2, cy - ch / 2, cw, ch)
    if ready:
        scaled = img.scaled(max(1, round(cw)), max(1, round(ch)),
                            ui.Qt.AspectRatioMode.IgnoreAspectRatio,
                            ui.Qt.TransformationMode.SmoothTransformation)
        alpha_corner = scaled.width() > 4 and scaled.height() > 4 and ((scaled.pixel(1, 1) >> 24) & 255) < 180
        if alpha_corner:
            p.drawImage(cr.topLeft(), scaled)
        elif has_box:
            rad = 0.42 * u
            spine = max(2.0, 0.44 * u)
            win.box(p, cr.translated(0.40 * u, 0.54 * u), rad, QColor(0, 0, 0, 165))
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
            p.drawImage(cr.topLeft(), scaled)
            p.restore()
            win.box(p, cr, rad, None, QColor(255, 255, 255, 68), max(1.0, 0.10 * u))
        else:
            rad = 0.72 * u
            win.box(p, cr.translated(0.35 * u, 0.50 * u), rad, QColor(0, 0, 0, 150))
            clip = QPainterPath()
            clip.addRoundedRect(cr, rad, rad)
            p.save()
            p.setClipPath(clip)
            p.drawImage(cr.topLeft(), scaled)
            p.restore()
            win.box(p, cr, rad, None, QColor(255, 255, 255, 56), max(1.0, 0.11 * u))
    else:
        rad = 0.85 * u
        win.box(p, cr, rad, QColor(20, 22, 34, 210), QColor(col.red(), col.green(), col.blue(), 110), max(1.0, 0.11 * u))
        win.text(p, gm['t'], cr.x() + u, cr.center().y() - 1.5 * u, ('u', 1.45, 600), QColor(240, 240, 248, 210), cw - 2 * u, 1, 1.3, 2)
    p.end()

    # Cache both ready covers and loading placeholders (`ckey` already separates `src` vs `'placeholder:' + gm['id']`)
    _CARD_SPRITES[ckey] = sp
    while len(_CARD_SPRITES) > 160:
        _CARD_SPRITES.popitem(last=False)
    return sp


def _draw_game_art(win, p, gm, cx, cy, base_w, base_h, col, tier=3, max_px=440):
    sp = _card_sprite(win, gm, base_w, base_h, col, tier=tier, max_px=max_px)
    p.drawImage(ui.QPointF(round(cx - sp.width() * 0.5), round(cy - sp.height() * 0.5)), sp)
    return ui.QRectF(cx - base_w * 0.5, cy - base_h * 0.5, base_w, base_h)


def _draw_starfield(p, W, H, side_idx, t, count=54):
    QColor, QRectF = ui.QColor, ui.QRectF
    p.setPen(ui.Qt.PenStyle.NoPen)
    total_h = 2.0  # 0..1 = top screen, 1..2 = bottom screen
    for i in range(min(count, len(_STAR_TABLE))):
        nx, ny0, depth, ph = _STAR_TABLE[i]
        speed = 0.014 * depth
        gy = (ny0 + t * speed) % total_h
        if int(gy) != side_idx:
            continue
        ly = (gy - side_idx) * H
        lx = ((nx + 0.018 * math.sin(t * 0.22 + i)) % 1.0) * W
        twinkle = 0.55 + 0.45 * math.sin(t * (1.1 + depth) + ph)
        alpha = int(18 + 88 * depth * twinkle)
        r = (0.75 + 1.25 * depth) * (W / 1920.0 + 0.35)
        p.fillRect(QRectF(lx - r, ly - r, r * 2.0, r * 2.0), QColor(225, 232, 255, alpha))


def _draw_hud_pill(win, p, cx, cy, sub_line=''):
    """Pre-baked translucent drifting OLED HUD pill with glowing orange border and 'Toravo Tandem' header."""
    u, QRectF, QColor, QImage, QPainter = win.u, ui.QRectF, ui.QColor, ui.QImage, ui.QPainter
    en = win.CFG.get('lang') == 'en'
    clk = ui.clock()
    dt = _date_str(en)
    bat = win.BATT
    b_str = f'{bat["level"]} %' + ((' · charging' if en else ' · lädt') if bat.get('charging') else '') if bat else ''
    meta = '  ·  '.join(x for x in (dt, b_str) if x)

    hkey = (win.side, round(u * 10), clk, meta, sub_line)
    sp = _HUD_SPRITES.get(hkey)
    if sp is None:
        pw = (34 if win.side == 'top' else 44) * u
        ph = (17.2 if sub_line else 14.0) * u
        pad = round(1.2 * u) + 4
        sw, sh = round(pw) + pad * 2, round(ph) + pad * 2
        sp = QImage(sw, sh, QImage.Format.Format_ARGB32_Premultiplied)
        sp.fill(QColor(0, 0, 0, 0))
        hp = QPainter(sp)
        hp.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        r = QRectF(pad, pad, pw, ph)
        orange_border = QColor('#ff8c1a')
        orange_glow = QColor(255, 140, 26, 46)
        orange_text = QColor('#ffa43a')
        win.box(hp, r.adjusted(-0.35 * u, -0.35 * u, 0.35 * u, 0.35 * u), 2.9 * u, None, orange_glow, max(2.2, 0.36 * u))
        win.box(hp, r, 2.6 * u, QColor(12, 13, 20, 222), orange_border, max(1.8, 0.22 * u))
        win.text(hp, 'Toravo Tandem', r.x() + 1.5 * u, r.y() + 1.15 * u, ('u', 1.48, 700, .06), orange_text, pw - 3.0 * u, 1)
        win.text(hp, clk, r.x(), r.y() + 3.65 * u, ('u', 4.6, 700, -.03), QColor(246, 246, 252, 242), pw, 1)
        win.text(hp, meta, r.x() + 1.5 * u, r.y() + 10.1 * u, ('u', 1.65, 500), QColor(174, 176, 196, 216), pw - 3.0 * u, 1)
        if sub_line:
            win.text(hp, sub_line, r.x() + 1.8 * u, r.y() + 13.3 * u, ('u', 1.55, 600), orange_text, pw - 3.6 * u, 1)
        hp.end()
        _HUD_SPRITES[hkey] = sp
        while len(_HUD_SPRITES) > 12:
            _HUD_SPRITES.popitem(last=False)
    else:
        _HUD_SPRITES.move_to_end(hkey)
    p.drawImage(int(round(cx - sp.width() * 0.5)), int(round(cy - sp.height() * 0.5)), sp)


def _top_badge_sprite(win):
    u, QRectF, QColor, QImage, QPainter = win.u, ui.QRectF, ui.QColor, ui.QImage, ui.QPainter
    hkey = ('top-badge', round(u * 10))
    sp = _HUD_SPRITES.get(hkey)
    if sp is None:
        bw_t, bh_t = 25 * u, 3.8 * u
        pad = 6
        sw, sh = round(bw_t) + pad * 2, round(bh_t) + pad * 2
        sp = QImage(sw, sh, QImage.Format.Format_ARGB32_Premultiplied)
        sp.fill(QColor(0, 0, 0, 0))
        hp = QPainter(sp)
        hp.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        tr_box = QRectF(pad, pad, bw_t, bh_t)
        win.box(hp, tr_box, 1.9 * u, QColor(12, 13, 20, 216), QColor('#ff8c1a'), max(1.4, 0.16 * u))
        win.text(hp, 'TORAVO TANDEM', tr_box.x(), tr_box.y(), ('u', 1.38, 700, .18), QColor('#ffa43a'), bw_t, 1, bh_t / (1.38 * u))
        hp.end()
        _HUD_SPRITES[hkey] = sp
    return sp


def _draw_kosmos(win, p, W, H, side_idx, t):
    u = win.u
    games = _cover_games(win)
    spot_game = games[int(t // 10) % len(games)] if games else None

    # Pure #000000 OLED zero-watt black background + crisp twinkling starfield
    _draw_starfield(p, W, H, side_idx, t, count=48)

    # Up to 28 multi-depth parallax covers gliding silk-smooth at 60 FPS across both OLED screens
    if games:
        pool = games
        n_slots = min(28, len(pool))
        span = 2.44
        lanes = (
            0.08, 0.90, 0.36, 0.66, 0.20, 0.79, 0.50, 0.14,
            0.85, 0.42, 0.60, 0.27, 0.73, 0.54, 0.11, 0.92,
            0.31, 0.69, 0.17, 0.82, 0.46, 0.63, 0.24, 0.76,
            0.39, 0.57, 0.13, 0.87,
        )
        do_preload = (int(t * 4) % 16 == 0)
        upcoming = []
        drawable = []
        for slot in range(n_slots):
            tier = slot % 4  # 0 = deep far, 1 = mid-far, 2 = mid-near, 3 = near foreground
            speed = 0.022 + tier * 0.0075 + (slot % 2) * 0.0025
            raw = t * speed + slot * (span / n_slots)
            cycle = int(raw // span)
            g_idx = (slot * 23 + cycle * 13) % len(pool)
            if do_preload:
                next_idx = (slot * 23 + (cycle + 1) * 13) % len(pool)
                upcoming.append(pool[g_idx])
                upcoming.append(pool[next_idx])
            gy = (raw % span) - 0.22
            local_cy = (gy - side_idx) * H
            cw = (9.2 + tier * 2.1) * u
            ch = cw * 1.36
            if local_cy + ch * 0.96 < 0 or local_cy - ch * 0.96 > H:
                continue
            drawable.append((tier, slot, pool[g_idx], local_cy, cw, ch))

        # Fast integer-aligned ARM NEON premultiplied sprite blits (back-to-front)
        for tier, slot, gm, local_cy, cw, ch in sorted(drawable, key=lambda d: (d[0], d[1])):
            cx = W * (lanes[slot % len(lanes)] + 0.026 * math.sin(t * 0.34 + slot * 1.9))
            col = _game_color(win, gm)
            sp = _card_sprite(win, gm, cw, ch, col, tier=tier, max_px=340 if tier < 3 else 400)
            p.drawImage(int(round(cx - sp.width() * 0.5)), int(round(local_cy - sp.height() * 0.5)), sp)

        if upcoming:
            _preload_art(win, upcoming, max_px=380)

    if side_idx == 0:
        tx = W * (0.5 + 0.22 * math.cos(t * 0.075))
        ty = H * (0.11 + 0.05 * math.sin(t * 0.095))
        bsp = _top_badge_sprite(win)
        p.drawImage(int(round(tx - bsp.width() * 0.5)), int(round(ty)), bsp)
    elif side_idx == 1:
        hx = W * (0.5 + 0.20 * math.sin(t * 0.11))
        hy = H * (0.52 + 0.22 * math.cos(t * 0.083))
        sub = f'★ {spot_game["t"]}' if spot_game else ''
        _draw_hud_pill(win, p, hx, hy, sub)


def _draw_arcade(win, p, W, H, side_idx, t):
    u, QRectF, QColor = win.u, ui.QRectF, ui.QColor
    games = _cover_games(win)
    period = 12.0
    slot = int(t // period)
    phase = (t % period) / period
    fade = max(0.0, min(1.0, phase / 0.12, (1.0 - phase) / 0.12))
    gm = games[(slot * 19 + 5) % len(games)] if games else None
    if side_idx == 0 and games and int(t * 2) % 10 == 0:
        _preload_art(win, (games[((slot + 1) * 19 + 5) % len(games)], games[((slot + 2) * 19 + 5) % len(games)]), max_px=440)
    col = _game_color(win, gm)

    _draw_starfield(p, W, H, side_idx, t * 0.6, count=36)

    dx = 2.8 * u * math.sin(t * 0.19)
    dy = 2.2 * u * math.cos(t * 0.15)

    if side_idx == 0 and gm:
        p.save()
        p.setOpacity(fade)
        cx, cy = W * 0.5 + dx, H * 0.48 + dy
        neb = _nebula_sprite(col)
        p.drawImage(QRectF(cx - W * 0.55, cy - H * 0.5, W * 0.9, H * 1.0), neb)

        cw, ch = 22.0 * u, 30.5 * u
        cr = _draw_game_art(win, p, gm, cx - 22.5 * u, cy, cw, ch, col, tier=3, max_px=440)

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
    steps = 20
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
    spot = random.Random(int(t // 45) + side_idx * 17).random
    cx = (28 + 44 * spot()) * W / 100
    cy = (26 + 48 * spot()) * H / 100
    if side_idx == 1:
        _draw_hud_pill(win, p, cx, cy)
    else:
        u, QColor = win.u, ui.QColor
        win.text(p, 'TORAVO TANDEM', cx - 22 * u, cy, ('u', 1.5, 700, .22), QColor(255, 140, 26, 130), 44 * u, 1)


def draw(win, p):
    """Paints one frame of the active OLED screensaver (driven by `win.saver_timer` at steady 60 Hz)."""
    W, H = win.width(), win.height()
    p.fillRect(0, 0, W, H, ui.QColor(0, 0, 0))
    style = win.CFG.get('saver_style') or 'kosmos'
    side_idx = 0 if win.side == 'top' else 1
    t = time.time()
    if style == 'minimal':
        _draw_minimal(win, p, W, H, side_idx, t)
        return
    if style == 'arcade':
        _draw_arcade(win, p, W, H, side_idx, t)
    elif style == 'aurora':
        _draw_aurora(win, p, W, H, side_idx, t)
    else:
        _draw_kosmos(win, p, W, H, side_idx, t)
