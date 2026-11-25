"""iiSU × Cocoon Unified Square Visual Engine for Toravo Tandem on the AYN Thor.

Pure QPainter + authored SVG vector craft — zero QML, zero WebEngine, zero background CPU when resting:
1. Unified Square Tile Language (1:1 squircle tiles + luminous platform-hue gradient rims across all tabs & zoom levels).
2. Full-Width Frosted-Glass Console Menu Dock on the bottom screen + symmetrical Top-Screen Channel & Status Header.
3. 3D Physical Retail Packaging + Cartridge / Optical Disc Pop-Out centered cleanly on the top 120 Hz AMOLED stage.
4. Dual-Screen "Hinge-Bridge" 2-colour Aurora Continuity flowing seamlessly from top OLED across the hinge into bottom OLED.
5. Analytical under-damped Spring Physics (`spring`) that settles to 1.0 and never ticks during gameplay or at rest (0% idle CPU).
6. Authored uniform-stroke SVG Console Silhouettes & Navigation Icons (zero emoji substitutes).
7. 360 ms "Console Launch Ceremony" radial light-burst when starting a game (0 ms added launch latency).
"""
import colorsys, math, time
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient
try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    QSvgRenderer = None

ui = None  # bound by tandem_ui

# Authored 24x24 uniform 1.75px-stroke vector icons for consoles, unified menu dock & pods
SVGS = {
    'sys_handheld': (
        '<rect x="3" y="6" width="18" height="12" rx="3.2" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<rect x="7.5" y="8.2" width="9" height="7.6" rx="1" fill="none" stroke="currentColor" stroke-width="1.5"/>'
        '<path d="M5.3 11v2M4.3 12h2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'
        '<circle cx="18.6" cy="11.2" r=".9" fill="currentColor"/><circle cx="17.8" cy="13.2" r=".9" fill="currentColor"/>'
    ),
    'sys_dual': (
        '<rect x="5" y="3" width="14" height="8.2" rx="2" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<rect x="4" y="12.6" width="16" height="8.4" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<line x1="7" y1="11.9" x2="17" y2="11.9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
        '<rect x="8" y="14.6" width="8" height="4.4" rx=".8" fill="none" stroke="currentColor" stroke-width="1.3"/>'
    ),
    'sys_snes': (
        '<rect x="2.5" y="7" width="19" height="10" rx="5" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<path d="M7 10.5v3M5.5 12h3" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>'
        '<circle cx="16.2" cy="10.6" r=".95" fill="currentColor"/><circle cx="18" cy="12" r=".95" fill="currentColor"/>'
        '<circle cx="14.4" cy="12" r=".95" fill="currentColor"/><circle cx="16.2" cy="13.4" r=".95" fill="currentColor"/>'
    ),
    'sys_cube': (
        '<polygon points="12,3.2 20,7.8 20,16.2 12,20.8 4,16.2 4,7.8" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/>'
        '<polyline points="4,7.8 12,12.4 20,7.8" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        '<line x1="12" y1="12.4" x2="12" y2="20.8" stroke="currentColor" stroke-width="1.6"/>'
    ),
    'sys_disc': (
        '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<circle cx="12" cy="12" r="2.4" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        '<path d="M7.2 7.2a6.8 6.8 0 0 1 4.8-2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>'
    ),
    'sys_switch': (
        '<rect x="3.5" y="5" width="7.2" height="14" rx="3.2" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<rect x="13.3" y="5" width="7.2" height="14" rx="3.2" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<circle cx="7.1" cy="9" r="1.2" fill="currentColor"/><circle cx="16.9" cy="13.2" r="1.2" fill="currentColor"/>'
    ),
    'sys_steam': (
        '<circle cx="12" cy="12" r="8.6" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<circle cx="15" cy="9.4" r="2.3" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        '<circle cx="9.2" cy="15" r="1.8" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        '<path d="M4.5 13.5l4.2 1.5M10.6 13.8l3.1-2.6" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>'
    ),
    'sys_arcade': (
        '<rect x="3.5" y="14.5" width="17" height="5" rx="1.8" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<line x1="8.5" y1="14.5" x2="8.5" y2="8.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
        '<circle cx="8.5" cy="6.5" r="2.2" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<circle cx="14.5" cy="16.8" r=".95" fill="currentColor"/><circle cx="17.5" cy="16.4" r=".95" fill="currentColor"/>'
    ),
    'sys_collection': (
        '<path d="M12 3.8l2.5 5.1 5.6.8-4.1 4 1 5.6L12 16.7 7 19.3l1-5.6-4.1-4 5.6-.8z" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/>'
    ),
    'nav_home': (
        '<path d="M12 3.4l2.3 5.7 5.7 2.3-5.7 2.3L12 19.4l-2.3-5.7L4 11.4l5.7-2.3z" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/>'
    ),
    'nav_apps': (
        '<rect x="4" y="4" width="6.8" height="6.8" rx="1.8" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<rect x="13.2" y="4" width="6.8" height="6.8" rx="1.8" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<rect x="4" y="13.2" width="6.8" height="6.8" rx="1.8" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<rect x="13.2" y="13.2" width="6.8" height="6.8" rx="1.8" fill="none" stroke="currentColor" stroke-width="1.75"/>'
    ),
    'nav_search': (
        '<circle cx="10.8" cy="10.8" r="6.1" fill="none" stroke="currentColor" stroke-width="1.85"/>'
        '<line x1="15.3" y1="15.3" x2="19.8" y2="19.8" stroke="currentColor" stroke-width="1.95" stroke-linecap="round"/>'
    ),
    'nav_stage': (
        '<rect x="7.4" y="4.8" width="9.2" height="14.4" rx="2.1" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '<path d="M4.6 7.5H3.8A1.3 1.3 0 0 0 2.5 8.8v6.4a1.3 1.3 0 0 0 1.3 1.3h.8M19.4 7.5h.8a1.3 1.3 0 0 1 1.3 1.3v6.4a1.3 1.3 0 0 1-1.3 1.3h-.8" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round"/>'
    ),
    'nav_grid': (
        '<rect x="4.2" y="4.2" width="6.6" height="6.6" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '<rect x="13.2" y="4.2" width="6.6" height="6.6" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '<rect x="4.2" y="13.2" width="6.6" height="6.6" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '<rect x="13.2" y="13.2" width="6.6" height="6.6" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.8"/>'
    ),
    'nav_zoom': (
        '<rect x="3.8" y="3.8" width="6.8" height="6.8" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<rect x="13.4" y="3.8" width="6.8" height="6.8" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<rect x="3.8" y="13.4" width="6.8" height="6.8" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<path d="M16.8 14v5.6M14 16.8h5.6" stroke="currentColor" stroke-width="1.85" stroke-linecap="round"/>'
    ),
    'nav_sort': (
        '<path d="M8 5v14M8 5L5.2 7.8M8 5l2.8 2.8M16 19V5M16 19l-2.8-2.8M16 19l2.8-2.8" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    'nav_more': (
        '<circle cx="6.2" cy="12" r="1.55" fill="currentColor"/>'
        '<circle cx="12" cy="12" r="1.55" fill="currentColor"/>'
        '<circle cx="17.8" cy="12" r="1.55" fill="currentColor"/>'
    ),
    'pod_play': '<polygon points="8,5.5 19,12 8,18.5" fill="currentColor"/>',
    'pod_dice': (
        '<rect x="4" y="4" width="16" height="16" rx="3.4" fill="none" stroke="currentColor" stroke-width="1.75"/>'
        '<circle cx="8.5" cy="8.5" r="1.15" fill="currentColor"/><circle cx="15.5" cy="8.5" r="1.15" fill="currentColor"/>'
        '<circle cx="12" cy="12" r="1.15" fill="currentColor"/>'
        '<circle cx="8.5" cy="15.5" r="1.15" fill="currentColor"/><circle cx="15.5" cy="15.5" r="1.15" fill="currentColor"/>'
    ),
    'pod_spark': (
        '<path d="M12 3l2.2 6.2L20.5 12l-6.3 2.8L12 21l-2.2-6.2L3.5 12l6.3-2.8z" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/>'
    ),
}

# Console media packaging profiles: (aspect_w_over_h, spine_hex_or_None, media_kind: 'cart'|'card'|'disc'|'mini_disc'|'none')
MEDIA_PROFILES = {
    'switch': (0.62, '#e60012', 'card'),
    'banananative': (0.62, '#e60012', 'card'),
    'gba': (1.0, '#4f46e5', 'cart'),
    'gb': (1.0, '#64748b', 'cart'),
    'gbc': (1.0, '#0ea5e9', 'cart'),
    'nds': (1.10, '#e2e8f0', 'card'),
    'n3ds': (1.10, '#ef4444', 'card'),
    'snes': (1.36, '#dc2626', 'cart'),
    'sfc': (1.36, '#eab308', 'cart'),
    'nes': (0.73, '#dc2626', 'cart'),
    'n64': (1.38, '#16a34a', 'cart'),
    'md': (0.72, '#1d4ed8', 'cart'),
    'megadrive': (0.72, '#1d4ed8', 'cart'),
    'genesis': (0.72, '#dc2626', 'cart'),
    'psx': (1.0, '#cbd5e1', 'disc'),
    'ps1': (1.0, '#cbd5e1', 'disc'),
    'dc': (1.0, '#f97316', 'disc'),
    'dreamcast': (1.0, '#f97316', 'disc'),
    'saturn': (0.66, '#cbd5e1', 'disc'),
    'segacd': (0.72, '#38bdf8', 'disc'),
    'ps2': (0.71, '#1e3a8a', 'disc'),
    'gc': (0.71, '#6366f1', 'mini_disc'),
    'gamecube': (0.71, '#6366f1', 'mini_disc'),
    'wii': (0.71, '#e2e8f0', 'disc'),
    'wiiu': (0.71, '#0284c7', 'disc'),
    'psp': (0.58, '#cbd5e1', 'mini_disc'),
    'steam': (0.67, None, 'none'),
    'port': (0.67, None, 'none'),
}

_SVG_CACHE = {}


def is_light():
    """True when the active theme uses a bright daylight background (e.g. iiSU Pearl or Hell)."""
    c = ui.INK
    return (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) > 145


def spring(win, start, secs, bounce=0.16):
    """Under-damped spring 0 -> 1 with a crisp, subtle console settle; never ticks while playing or after t >= 1."""
    if secs <= 0 or not start or win.playing():
        return 1.0
    if win.CFG.get('motion') == 'reduced':
        return win.ease(start, secs * 0.5)
    t = (time.time() - start) / secs
    if t >= 1.0:
        return 1.0
    if t <= 0.0:
        ui.QTimer.singleShot(16, win.update)
        return 0.0
    ui.QTimer.singleShot(16, win.update)
    decay = math.exp(-5.8 * t)
    val = 1.0 - decay * (math.cos(4.7 * t) - bounce * math.sin(4.7 * t))
    if t > 0.88:
        k = (t - 0.88) / 0.12
        val = val * (1.0 - k) + 1.0 * k
    return max(0.0, min(1.05, val))


def draw_svg(p, name, rect, color):
    if not QSvgRenderer or name not in SVGS:
        return False
    key = (name, color.name(), color.alpha())
    ren = _SVG_CACHE.get(key)
    if ren is None:
        svg_txt = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" opacity="{color.alphaF():.3f}">'
            f'{SVGS[name].replace("currentColor", color.name())}</svg>'
        )
        ren = QSvgRenderer(QByteArray(svg_txt.encode('utf-8')))
        if len(_SVG_CACHE) > 128:
            _SVG_CACHE.clear()
        _SVG_CACHE[key] = ren
    ren.render(p, rect)
    return True


def console_svg_for(sys_id):
    s = str(sys_id or '').lower()
    if s.startswith('col:'):
        return 'sys_collection'
    if s in ('nds', 'n3ds', '3ds', 'wiiu'):
        return 'sys_dual'
    if s in ('gb', 'gbc', 'gba', 'gamegear', 'gg', 'lynx', 'ws', 'wsc', 'ngp', 'ngpc', 'psp', 'pokemini'):
        return 'sys_handheld'
    if s in ('switch', 'banananative'):
        return 'sys_switch'
    if s in ('steam', 'port', 'dos', 'scummvm'):
        return 'sys_steam'
    if s in ('gc', 'gamecube', 'n64'):
        return 'sys_cube'
    if s in ('psx', 'ps1', 'ps2', 'dc', 'dreamcast', 'saturn', 'wii', '3do', 'neogeocd', 'segacd', 'pcenginecd'):
        return 'sys_disc'
    if s in ('arcade', 'fbneo', 'fba', 'mame', 'neogeo', 'cps', 'cps1', 'cps2', 'cps3'):
        return 'sys_arcade'
    return 'sys_snes'


def dual_aurora_colors(accent_qcolor):
    """Derive a rich two-tone aurora pair (primary + shifted analogous hue) from the active accent colour."""
    r, g, b = accent_qcolor.red() / 255.0, accent_qcolor.green() / 255.0, accent_qcolor.blue() / 255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h2 = (h + 0.11) % 1.0
    r2, g2, b2 = colorsys.hsv_to_rgb(h2, min(1.0, max(0.55, s * 0.95)), min(1.0, max(0.72, v)))
    return accent_qcolor, QColor(round(r2 * 255), round(g2 * 255), round(b2 * 255))


def draw_hinge_bridge(win, p, side):
    """Paint the dual-screen Hinge-Bridge: twin aurora plumes aligned at 27% and 74% X across the physical hinge."""
    glow = ui.THEME.get('glow', 1.0)
    if glow <= 0.01:
        return
    W, H = win.width(), win.height()
    c1, c2 = dual_aurora_colors(ui.FOCUS)
    light = is_light()
    a1 = (0.13 if light else 0.20) * glow
    a2 = (0.10 if light else 0.16) * glow
    anchor_y = float(H) if side == 'top' else 0.0
    rad1, rad2 = W * 0.44, W * 0.38

    g1 = QRadialGradient(QPointF(W * 0.27, anchor_y), rad1)
    g1.setColorAt(0.0, ui.faded(c1, a1))
    g1.setColorAt(0.55, ui.faded(c1, a1 * 0.30))
    g1.setColorAt(1.0, ui.faded(c1, 0.0))
    p.fillRect(QRectF(0, max(0.0, H - rad1) if side == 'top' else 0.0, W, min(float(H), rad1)), QBrush(g1))

    g2 = QRadialGradient(QPointF(W * 0.74, anchor_y), rad2)
    g2.setColorAt(0.0, ui.faded(c2, a2))
    g2.setColorAt(0.55, ui.faded(c2, a2 * 0.28))
    g2.setColorAt(1.0, ui.faded(c2, 0.0))
    p.fillRect(QRectF(0, max(0.0, H - rad2) if side == 'top' else 0.0, W, min(float(H), rad2)), QBrush(g2))

    seam_y = H - 1.5 if side == 'top' else 0.0
    seam = QLinearGradient(W * 0.08, seam_y, W * 0.92, seam_y)
    seam.setColorAt(0.0, ui.faded(c1, 0.0))
    seam.setColorAt(0.28, ui.faded(c1, 0.40 * glow))
    seam.setColorAt(0.72, ui.faded(c2, 0.36 * glow))
    seam.setColorAt(1.0, ui.faded(c2, 0.0))
    p.fillRect(QRectF(0, seam_y, W, 1.5), QBrush(seam))


def glass_card(win, p, rect, radius, base_color=None, border_color=None, shadow=True, accent_tint=0.0):
    """Frutiger-Aero / Liquid-Glass surface with offset soft shadow, subtle sheen, and 1px top specular catchlight."""
    u = win.u
    light = is_light()
    r = min(rect.height() / 2, radius * ui.THEME['radius'])
    fill = base_color or ui.PANEL
    if shadow:
        for dy, expand, alpha in ((0.40 * u, 0.48 * u, 0.08 if light else 0.26),
                                  (0.16 * u, 0.16 * u, 0.05 if light else 0.16)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ui.rgba(12, 18, 32, alpha) if light else ui.rgba(0, 0, 0, alpha))
            p.drawRoundedRect(rect.adjusted(-expand, dy - expand * 0.35, expand, dy + expand), r + expand, r + expand)

    grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
    if light:
        top_c = win.lerp_color(fill, QColor('#ffffff'), 0.62)
        bot_c = win.lerp_color(fill, ui.RAISED, 0.24)
    else:
        top_c = win.lerp_color(fill, QColor('#ffffff'), 0.07)
        bot_c = win.lerp_color(fill, QColor('#000000'), 0.16)
    if accent_tint > 0:
        top_c = win.lerp_color(top_c, ui.FOCUS, accent_tint)
    grad.setColorAt(0.0, top_c)
    grad.setColorAt(1.0, bot_c)

    bcol = border_color or (ui.rgba(15, 23, 42, 0.11) if light else ui.rgba(255, 255, 255, 0.11))
    p.setPen(QPen(bcol, 1.0))
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(rect, r, r)

    if rect.width() > r * 2.4:
        rim_a = 0.75 if light else 0.16
        p.fillRect(QRectF(rect.x() + r * 0.85, rect.y() + 1.0, rect.width() - r * 1.7, 1.0),
                   ui.rgba(255, 255, 255, rim_a))


def draw_square_rim(win, p, rect, item, radius, on=False):
    """Unified Cocoon × iiSU 2-tone luminous squircle border for square tiles that have no external overlay.png."""
    u = win.u
    s = str(item.get('s') or '')
    hue = 212 if s == 'steam' else 198 if s in ('app', 'term') else (win.L['systems'].get(s) or {'hue': 205})['hue']
    c1 = QColor.fromHslF((hue % 360) / 360.0, 0.82, 0.58, 0.72 if on else 0.44)
    c2 = QColor.fromHslF(((hue + 44) % 360) / 360.0, 0.78, 0.52, 0.68 if on else 0.36)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, c1)
    grad.setColorAt(1.0, c2)
    r = radius * ui.THEME['radius']
    bw = max(1.3, 0.18 * u)
    inset = bw * 0.5
    p.setPen(QPen(QBrush(grad), bw))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset), max(1.0, r - inset), max(1.0, r - inset))


def draw_top_header(win, p, items, dx=0.0, dy=0.0):
    """Top-left frosted-glass channel capsule mirroring the top-right status_bar on the exact same horizontal axis."""
    u = win.u
    light = is_light()
    P, RUN, S = win.playing(), win.RUN, win.S
    if P and RUN:
        svg_name = 'pod_play'
        lead_txt = 'Läuft'
        sub_txt = win.sys_name(RUN)
        icon_col = ui.LIVE
    elif S.get('q'):
        svg_name = 'nav_search'
        lead_txt = 'Suche'
        sub_txt = f'{len(items)} Eintrag' if len(items) == 1 else f'{len(items)} Einträge'
        icon_col = ui.FOCUS
    elif S.get('sys'):
        svg_name = console_svg_for(S['sys'])
        lead_txt = win.sys_name({'s': S['sys']})
        sub_txt = f'{len(items)} Eintrag' if len(items) == 1 else f'{len(items)} Spiele'
        icon_col = ui.FOCUS
    else:
        tab = S.get('tab', 0)
        svg_map = {0: 'nav_home', 1: 'sys_snes', 2: 'sys_steam', 3: 'nav_apps', 4: 'pod_spark'}
        svg_name = svg_map.get(tab, 'nav_home')
        lead_txt = ui.TABS[tab] if 0 <= tab < len(ui.TABS) else 'Toravo Tandem'
        if tab == 4:
            sub_txt = ui.settings_view.TITLES.get(ui.settings_view.page_of(win), '')
        else:
            sub_txt = f'{len(items)} Eintrag' if len(items) == 1 else (
                f'{len(items)} Spiele' if tab in (0, 2) else f'{len(items)} Einträge'
            )
        icon_col = ui.FOCUS

    fb, fm = ('u', 1.32, 700), ('u', 1.28, 500)
    h, pad, ic = 3.15 * u, 1.35 * u, 1.65 * u
    sep = '  ·  '
    w = (pad + ic + 0.75 * u + win.width_of(lead_txt, fb)
         + (win.width_of(sep, fm) + win.width_of(sub_txt, fm) if sub_txt else 0) + pad)
    rect = QRectF(4.2 * u + dx, 1.85 * u + dy, w, h)
    if light:
        ink, dim = ui.rgba(17, 24, 39, 0.94), ui.rgba(71, 85, 105, 0.84)
        win.capsule(p, rect, ui.rgba(255, 255, 255, 0.80), ui.rgba(15, 23, 42, 0.12))
    else:
        ink, dim = ui.rgba(241, 245, 249, 0.92), ui.rgba(203, 213, 225, 0.68)
        win.capsule(p, rect, ui.rgba(8, 11, 20, 0.58), ui.rgba(255, 255, 255, 0.13))

    draw_svg(p, svg_name, QRectF(rect.x() + pad, rect.center().y() - ic / 2, ic, ic), icon_col)
    tx = rect.x() + pad + ic + 0.75 * u
    ty = rect.y() + (h - 1.32 * u * 1.2) / 2
    win.text(p, lead_txt, tx, ty, fb, ink)
    tx += win.width_of(lead_txt, fb)
    if sub_txt:
        win.text(p, sep, tx, ty, fm, dim)
        tx += win.width_of(sep, fm)
        win.text(p, sub_txt, tx, ty, fm, dim)


def draw_console_dock(win, p, items, title=None, buttons=None):
    """Unified full-width Liquid-Glass Console Menu Bar on the bottom screen (`x0` to `x0 + cw`).
    Aligns outer edges to the exact pixel with the square tile grid below. Returns y below the bar."""
    u, W = win.u, win.width()
    x0, cw = 2.6 * u, W - 5.2 * u
    y, h = 2.1 * u, 5.6 * u
    bar = QRectF(x0, y, cw, h)
    light = is_light()
    glass_card(win, p, bar, h / 2, shadow=True)

    if title is not None:
        f = ('u', 1.95, 600)
        pad = 0.55 * u
        right = bar.right() - pad
        bh = h - 2 * pad
        for label, on, fn in reversed(buttons or ()):
            bw = win.width_of(label, f) + 3.4 * u
            right -= bw
            brect = QRectF(right, y + pad, bw, bh)
            win.capsule(p, brect, ui.FOCUS if on else ui.faded(ui.TEXT, 0.10),
                        None if on else ui.faded(ui.TEXT, 0.12))
            win.text(p, label, right, y + pad, f, ui.INK if on else ui.TEXT, bw, 1, bh / (f[1] * u))
            win.hit(brect, fn, name=label)
            right -= 0.7 * u
        win.text(p, title, x0 + 2.0 * u, y, ('u', 2.15, 700, -.01), ui.TEXT,
                 max(6 * u, right - x0 - 2.6 * u), lh=h / (2.15 * u))
        win.tabs_right = bar.right()
        return y + h + 2.0 * u

    # ---- Right-aligned unified icon-action cluster inside the dock ----
    pad = 0.55 * u
    bh = h - 2 * pad
    by = y + pad
    rx = bar.right() - pad
    actions = []  # [(kind, svg_name, badge_txt, active_bool, fn, hit_name)]
    tab = win.S['tab']
    in_games = bool(tab in (0, 2) or win.S['sys'])
    if in_games:
        actions.append(('icon', 'nav_more', '', False, win.open_game_menu, 'Optionen'))
        actions.append(('icon', 'pod_dice', '', False, win.pick_random, 'Zufall'))
        if win.CFG.get('view_mode') != 'stage':
            cols = win.grid_cols()
            actions.append(('zoom', 'nav_zoom', str(cols), cols != 5, win.cycle_cols, 'GridZoom'))
        stage_now = win.CFG.get('view_mode') == 'stage'
        vlabel = 'Kacheln' if stage_now else 'Bühne'
        actions.append(('icon', 'nav_grid' if stage_now else 'nav_stage', '', stage_now, win.toggle_view, vlabel))
    if tab in (0, 1, 2) or win.S['sys']:
        actions.append(('icon', 'nav_search', '', False, win.open_search, 'Suche'))

    btn_gap = 0.42 * u
    for kind_a, svg_n, btxt, is_act, fn, hname in actions:
        bw = (5.8 * u) if kind_a == 'zoom' else (4.35 * u)
        rx -= bw
        arect = QRectF(rx, by, bw, bh)
        bg = ui.faded(ui.FOCUS, 0.20) if is_act else (
            ui.rgba(15, 23, 42, 0.05) if light else ui.rgba(255, 255, 255, 0.055)
        )
        bd = ui.faded(ui.FOCUS, 0.48) if is_act else (
            ui.rgba(15, 23, 42, 0.09) if light else ui.rgba(255, 255, 255, 0.09)
        )
        win.capsule(p, arect, bg, bd)
        fg = ui.FOCUS if is_act else ui.TEXT
        if kind_a == 'zoom':
            ic_s = 2.05 * u
            draw_svg(p, svg_n, QRectF(arect.x() + 0.95 * u, arect.center().y() - ic_s / 2, ic_s, ic_s), fg)
            zf = ('u', 1.65, 700)
            win.text(p, btxt, arect.x() + 2.95 * u, arect.y(), zf, fg, bw - 3.3 * u, 1, bh / (1.65 * u))
        else:
            ic_s = 2.15 * u
            draw_svg(p, svg_n, QRectF(arect.center().x() - ic_s / 2, arect.center().y() - ic_s / 2, ic_s, ic_s), fg)
        win.hit(arect, fn, name=hname)
        rx -= btn_gap

    if len(actions) <= 1 and items:
        cf = ('u', 1.58, 600)
        cnt_lbl = f'{len(items)} Eintrag' if len(items) == 1 else f'{len(items)} Einträge'
        cw_lbl = win.width_of(cnt_lbl, cf) + 1.8 * u
        rx -= cw_lbl
        win.text(p, cnt_lbl, rx, by, cf, ui.MUTED, cw_lbl - 0.6 * u, 2, bh / (1.58 * u))

    if rx < bar.right() - 1.5 * u:
        div_x = rx - 0.35 * u
        p.fillRect(QRectF(div_x, y + 1.25 * u, 1.0, h - 2.5 * u),
                   ui.rgba(15, 23, 42, 0.10) if light else ui.rgba(255, 255, 255, 0.10))
        rx = div_x - 0.45 * u

    # ---- Left-aligned segmented L · Tabs · R inside the exact same dock ----
    cap = 3.1 * u
    avail_tabs_w = max(36 * u, rx - (bar.x() + pad) - 2 * cap)
    f = ('u', 1.92, 600)
    tab_pad = 2.35 * u
    need = sum(win.width_of(label, f) + tab_pad for label in ui.TABS)
    if need > avail_tabs_w:
        scale_f = avail_tabs_w / need
        f = ('u', max(1.45, round(1.92 * scale_f, 2)), 600)
        tab_pad = max(1.4 * u, tab_pad * scale_f)
    widths = [win.width_of(label, f) + tab_pad for label in ui.TABS]

    lx = bar.x() + pad
    rx_cap = lx + cap + sum(widths)
    for kx, key_lbl, act in ((lx, 'L', 'prev'), (rx_cap, 'R', 'next')):
        krect = QRectF(kx + 0.35 * u, y + 1.35 * u, cap - 0.7 * u, h - 2.7 * u)
        win.box(p, krect, 0.75 * u, ui.faded(ui.TEXT, 0.05), ui.faded(ui.MUTED, 0.42), 1.0)
        win.text(p, key_lbl, krect.x(), krect.y(), ('u', 1.32, 700), ui.MUTED,
                 krect.width(), 1, krect.height() / (1.32 * u))
        win.hit(QRectF(kx, y, cap, h), lambda a=act: win.go(a), name=act)

    active_idx = 1 if win.S['sys'] else win.S['tab']
    tx = lx + cap
    rects = []
    for n in range(len(ui.TABS)):
        rects.append(QRectF(tx, by, widths[n], bh))
        tx += widths[n]

    if 0 <= active_idx < len(rects):
        ar = rects[active_idx]
        ta = win.tab_anim
        if ta['key'] is None:
            ta.update(fx=ar.x(), fw=ar.width(), tx=ar.x(), tw=ar.width(), key=active_idx, t0=0.0)
        elif ta['key'] != active_idx:
            tt = spring(win, ta['t0'], win.dur(0.26)) if ta['t0'] else 1.0
            cx, cw_ = ta['fx'] + (ta['tx'] - ta['fx']) * tt, ta['fw'] + (ta['tw'] - ta['fw']) * tt
            ta.update(fx=cx, fw=cw_, tx=ar.x(), tw=ar.width(), key=active_idx, t0=time.time())
        tt = spring(win, ta['t0'], win.dur(0.26)) if ta['t0'] else 1.0
        px = ar.x() if win.CFG.get('motion') == 'reduced' else ta['fx'] + (ta['tx'] - ta['fx']) * tt
        pw = ar.width() if win.CFG.get('motion') == 'reduced' else ta['fw'] + (ta['tw'] - ta['fw']) * tt
        pill = QRectF(px, by, pw, bh)
        win.capsule(p, pill, ui.faded(ui.FOCUS, 0.22 if light else 0.20), ui.faded(ui.FOCUS, 0.55))

    for n, label in enumerate(ui.TABS):
        rect = rects[n]
        on = (n == active_idx)
        tf_tab = (f[0], f[1], 700 if on else 600)
        win.text(p, label, rect.x(), rect.y(), tf_tab, ui.FOCUS if (on and light) else (ui.TEXT if on else ui.MUTED),
                 rect.width(), 1, rect.height() / (f[1] * u))
        win.hit(rect, lambda n=n: win.open_tab(n), name=label)

    win.tabs_right = bar.right()
    return y + h + 2.0 * u


def _draw_media_peek(win, p, box_rect, media_kind, spine_col, art_img, t_pop):
    """Draw the physical Cartridge, Switch Game Card, or Optical Disc peeking out from behind the 3D retail case."""
    if media_kind == 'none' or t_pop <= 0.02:
        return
    u = win.u
    bw, bh = box_rect.width(), box_rect.height()
    slide = (.22 if 'disc' in media_kind else .19) * bw * t_pop

    p.save()
    if 'disc' in media_kind:
        scale_d = 0.74 if media_kind == 'mini_disc' else 0.86
        diam = min(bh * scale_d, bw * 0.94)
        cx = box_rect.right() - diam * 0.35 + slide
        cy = box_rect.center().y()
        drect = QRectF(cx - diam / 2, cy - diam / 2, diam, diam)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ui.rgba(0, 0, 0, 0.38))
        p.drawEllipse(drect.translated(0.25 * u, 0.45 * u))

        disc_path = QPainterPath()
        disc_path.addEllipse(drect)
        hole = QPainterPath()
        hole.addEllipse(QPointF(cx, cy), diam * 0.15, diam * 0.15)
        disc_ring = disc_path.subtracted(hole)

        dgrad = QLinearGradient(drect.topLeft(), drect.bottomRight())
        dgrad.setColorAt(0.0, QColor('#e2e8f0'))
        dgrad.setColorAt(0.28, ui.faded(spine_col, 0.92))
        dgrad.setColorAt(0.52, QColor('#f8fafc'))
        dgrad.setColorAt(0.76, QColor('#38bdf8'))
        dgrad.setColorAt(1.0, QColor('#94a3b8'))
        p.fillPath(disc_ring, QBrush(dgrad))

        if art_img and not art_img.isNull():
            p.save()
            p.setClipPath(disc_ring)
            p.setOpacity(0.42)
            p.drawImage(drect, art_img)
            p.restore()

        p.setPen(QPen(ui.rgba(255, 255, 255, 0.55), max(1.0, 0.12 * u)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(drect)
        p.setPen(QPen(ui.rgba(255, 255, 255, 0.45), max(1.0, 0.22 * u)))
        p.drawEllipse(QPointF(cx, cy), diam * 0.22, diam * 0.22)
    else:
        is_card = (media_kind == 'card')
        cw = bw * (0.44 if is_card else 0.54)
        ch = bh * (0.56 if is_card else 0.66)
        cx = box_rect.right() - cw * 0.64 + slide
        cy = box_rect.center().y() - ch * 0.46
        crect = QRectF(cx, cy, cw, ch)
        crad = (0.9 if is_card else 1.1) * u

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ui.rgba(0, 0, 0, 0.42))
        p.drawRoundedRect(crect.translated(0.25 * u, 0.45 * u), crad, crad)

        shell = QColor('#1f2937') if is_card else QColor('#334155')
        sh_grad = QLinearGradient(crect.topLeft(), crect.topRight())
        sh_grad.setColorAt(0.0, shell.lighter(125))
        sh_grad.setColorAt(1.0, shell.darker(118))
        p.setPen(QPen(ui.rgba(255, 255, 255, 0.22), 1.0))
        p.setBrush(QBrush(sh_grad))
        p.drawRoundedRect(crect, crad, crad)

        for ri in range(3):
            ry = crect.y() + (0.65 + ri * 0.42) * u
            p.fillRect(QRectF(crect.x() + 1.0 * u, ry, crect.width() - 2.0 * u, 0.18 * u), ui.rgba(255, 255, 255, 0.14))

        lbl = crect.adjusted(0.8 * u, 2.3 * u, -0.8 * u, -1.5 * u)
        if lbl.width() > 2 * u and lbl.height() > 2 * u:
            lclip = QPainterPath()
            lclip.addRoundedRect(lbl, 0.55 * u, 0.55 * u)
            p.save()
            p.setClipPath(lclip)
            p.fillRect(lbl, spine_col)
            if art_img and not art_img.isNull():
                p.drawImage(lbl.adjusted(0, 0.9 * u, 0, 0), art_img)
            p.restore()
            p.setPen(QPen(ui.rgba(255, 255, 255, 0.28), 0.9))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(lbl, 0.55 * u, 0.55 * u)
    p.restore()


def draw_3d_showcase(win, p, it, t_enter, has_moment, shot_img):
    """iiSU-style 3D Retail Box + Cartridge/Disc Pop-Out centered vertically in the right showcase stage."""
    u, W, H = win.u, win.width(), win.height()
    if not it:
        return None
    sys_id = str(it.get('s') or '').lower()
    if it.get('kind') == 'sys' or sys_id in ('app', 'term'):
        return None

    ar_default, spine_hex, media_kind = MEDIA_PROFILES.get(sys_id, (0.72, None, 'cart'))
    spine_col = QColor(spine_hex) if spine_hex else QColor(ui.FOCUS)

    art_src = it.get('box') or it.get('cover')
    max_h = round(35.0 * u)
    max_w = round(28.5 * u)
    box_img = win.images.get(art_src, max_w, max_h, False) if art_src else False
    if box_img and not getattr(box_img, 'isNull', lambda: True)() and box_img.width() > 0 and box_img.height() > 0:
        ar = max(0.56, min(1.38, box_img.width() / box_img.height()))
    else:
        box_img = None
        ar = ar_default

    bh = 30.5 * u if ar <= 0.84 else (24.5 * u if ar <= 1.10 else 20.8 * u)
    bw = min(26.5 * u, bh * ar)
    bh = bw / ar

    t_sp = spring(win, win.hero['kt'], win.dur(0.42), bounce=0.18)
    glide_x = 0.0 if win.CFG.get('motion') == 'reduced' else (1.0 - t_sp) * 2.0 * u
    glide_y = 0.0 if win.CFG.get('motion') == 'reduced' else (1.0 - t_sp) * 0.8 * u
    # Leave room on the right so the peeking cartridge/disc aligns cleanly inside the 4.2u outer console margin
    peek_extra = (0.38 * bw if 'disc' in media_kind else (0.36 if media_kind == 'card' else 0.40) * bw) if media_kind != 'none' else 0.0
    right_margin = 4.2 * u + peek_extra
    bx = W - right_margin - bw + glide_x
    by = max(7.2 * u, min(H - 4.4 * u - bh, H * 0.52 - bh * 0.50)) + glide_y
    brect = QRectF(bx, by, bw, bh)
    rad = 1.15 * u

    p.save()
    light = is_light()
    # Smooth radial ambient shadow + glow (no concentric stepped bands)
    sh_rad = max(bw, bh) * 0.78
    sh_cx, sh_cy = brect.center().x() + peek_extra * 0.25, brect.center().y() + 0.9 * u
    amb_sh = QRadialGradient(QPointF(sh_cx, sh_cy), sh_rad)
    amb_sh.setColorAt(0.0, ui.rgba(15, 23, 42, 0.26) if light else ui.rgba(0, 0, 0, 0.55))
    amb_sh.setColorAt(0.58, ui.rgba(15, 23, 42, 0.10) if light else ui.rgba(0, 0, 0, 0.22))
    amb_sh.setColorAt(1.0, ui.rgba(0, 0, 0, 0.0))
    p.fillRect(QRectF(sh_cx - sh_rad, sh_cy - sh_rad, 2 * sh_rad, 2 * sh_rad), QBrush(amb_sh))

    if ui.THEME.get('glow', 1.0) > 0:
        puddle = QRadialGradient(QPointF(brect.center().x(), brect.bottom() + 0.5 * u), bw * 0.80)
        puddle.setColorAt(0.0, ui.faded(ui.FOCUS, (0.18 if light else 0.26) * ui.THEME['glow']))
        puddle.setColorAt(1.0, ui.faded(ui.FOCUS, 0.0))
        p.fillRect(QRectF(brect.x() - 6 * u, brect.bottom() - 4 * u, bw + 14 * u, 9 * u), QBrush(puddle))

    t_media = max(0.0, min(1.0, (t_sp - 0.16) / 0.84))
    _draw_media_peek(win, p, brect, media_kind, spine_col, box_img, t_media)

    # Single crisp contact shadow directly behind the case
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(ui.rgba(15, 23, 42, 0.18) if light else ui.rgba(0, 0, 0, 0.42))
    p.drawRoundedRect(brect.adjusted(-0.22 * u, 0.28 * u, 0.28 * u, 0.52 * u), rad + 0.25 * u, rad + 0.25 * u)

    sp_w = 1.3 * u
    spine_poly = QPolygonF([
        QPointF(brect.x() - sp_w, brect.y() + 0.65 * u),
        QPointF(brect.x() + 0.25 * u, brect.y()),
        QPointF(brect.x() + 0.25 * u, brect.bottom()),
        QPointF(brect.x() - sp_w, brect.bottom() - 0.55 * u),
    ])
    sp_grad = QLinearGradient(brect.x() - sp_w, brect.y(), brect.x() + 0.25 * u, brect.y())
    sp_grad.setColorAt(0.0, spine_col.darker(145))
    sp_grad.setColorAt(0.65, spine_col)
    sp_grad.setColorAt(1.0, spine_col.lighter(120))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(sp_grad))
    p.drawPolygon(spine_poly)

    clip = QPainterPath()
    clip.addRoundedRect(brect, rad, rad)
    p.save()
    p.setClipPath(clip)
    if box_img:
        p.drawImage(brect, box_img)
    elif shot_img:
        p.drawImage(brect, shot_img)
    else:
        p.fillRect(brect, QBrush(win.paint_of(it, brect)))
        draw_svg(p, console_svg_for(sys_id), QRectF(brect.center().x() - 4 * u, brect.center().y() - 4 * u, 8 * u, 8 * u),
                 ui.rgba(255, 255, 255, 0.86))

    if shot_img and box_img:
        pw_pip, ph_pip = min(bw * 0.76, 15.5 * u), min(bh * 0.36, 8.8 * u)
        pip_r = QRectF(brect.right() - pw_pip - 0.85 * u, brect.bottom() - ph_pip - 0.85 * u, pw_pip, ph_pip)
        p.fillRect(pip_r.adjusted(-0.25 * u, -0.25 * u, 0.25 * u, 0.25 * u), ui.rgba(6, 8, 14, 0.85))
        pclip = QPainterPath()
        pclip.addRoundedRect(pip_r, 0.65 * u, 0.65 * u)
        p.save()
        p.setClipPath(pclip)
        p.drawImage(pip_r, shot_img)
        p.restore()
        p.setPen(QPen(ui.FOCUS if has_moment else ui.rgba(255, 255, 255, 0.45), max(1.0, 0.12 * u)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(pip_r, 0.65 * u, 0.65 * u)

    sheen = QLinearGradient(brect.topLeft(), QPointF(brect.x() + bw * 0.65, brect.y() + bh * 0.55))
    sheen.setColorAt(0.0, ui.rgba(255, 255, 255, 0.22))
    sheen.setColorAt(0.38, ui.rgba(255, 255, 255, 0.05))
    sheen.setColorAt(1.0, ui.rgba(255, 255, 255, 0.0))
    p.fillRect(brect, QBrush(sheen))
    p.restore()

    p.setPen(QPen(ui.rgba(255, 255, 255, 0.28), 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(brect, rad, rad)
    p.fillRect(QRectF(brect.x() + 0.55 * u, brect.y() + 0.3 * u, 1.0, bh - 0.6 * u), ui.rgba(255, 255, 255, 0.18))

    if has_moment:
        blbl = '● Zuletzt im Spiel'
        bf = ('u', 1.18, 700, .02)
        b_w = win.width_of(blbl, bf) + 2.0 * u
        b_h = 2.35 * u
        b_rect = QRectF(brect.x() + 0.85 * u, brect.y() + 0.85 * u, b_w, b_h)
        win.capsule(p, b_rect, ui.rgba(8, 11, 18, 0.84), ui.faded(ui.FOCUS, 0.55))
        win.text(p, blbl, b_rect.x(), b_rect.y(), bf, ui.FOCUS, b_w, 1, b_h / (1.18 * u))

    p.restore()
    hit_r = brect.adjusted(-sp_w, 0, 3.0 * u if media_kind != 'none' else 0, 0)
    win.hit(hit_r, lambda: win.post('api/uikey', {'a': 'ok'}), name='pad:shot')
    return hit_r


def draw_system_tile_art(win, p, rect, item):
    """Draw a rich branded platform world with authored SVG console silhouette when a system has no custom photo cover."""
    u = win.u
    s = str(item.get('s') or '')
    svg_name = console_svg_for(s)
    wm_sz = rect.width() * 0.68
    draw_svg(p, svg_name, QRectF(rect.right() - wm_sz * 0.86, rect.y() + rect.height() * 0.06, wm_sz, wm_sz),
             ui.rgba(255, 255, 255, 0.11))
    ic_sz = rect.width() * 0.34
    badge_r = QRectF(rect.x() + 1.2 * u, rect.y() + 1.2 * u, ic_sz + 1.2 * u, ic_sz + 1.2 * u)
    win.box(p, badge_r, 1.1 * u, ui.rgba(255, 255, 255, 0.14), ui.rgba(255, 255, 255, 0.22))
    draw_svg(p, svg_name, badge_r.adjusted(0.6 * u, 0.6 * u, -0.6 * u, -0.6 * u), QColor('#ffffff'))


def draw_home_pods(win, p, items, x0, cw, y):
    """Optional Cocoon 3.0 modular Pods row (3 symmetrical cards aligned to the grid width when toggled on in Look)."""
    if not items:
        return y
    u = win.u
    gap = 2.0 * u
    pod_h = 15.2 * u
    w_hero = (cw - 2 * gap) * 0.46
    w_side = (cw - 2 * gap - w_hero) / 2

    hero_gm = items[0]
    played = (win.L.get('played') or {}).get(hero_gm['id']) or {}
    p1 = QRectF(x0, y, w_hero, pod_h)
    glass_card(win, p, p1, 2.0 * u, accent_tint=0.10)
    art_tok = hero_gm.get('moment') or hero_gm.get('hero') or hero_gm.get('cover')
    art = win.thumbs.get(art_tok, max(96, round(w_hero)), max(64, round(pod_h))) if art_tok else None
    if art and not getattr(art, 'isNull', lambda: True)():
        clip = QPainterPath()
        clip.addRoundedRect(p1, 2.0 * u * ui.THEME['radius'], 2.0 * u * ui.THEME['radius'])
        p.save()
        p.setClipPath(clip)
        p.drawImage(p1, art)
        scrim = QLinearGradient(p1.left(), p1.top(), p1.left(), p1.bottom())
        scrim.setColorAt(0.0, ui.rgba(6, 9, 16, 0.20))
        scrim.setColorAt(1.0, ui.rgba(6, 9, 16, 0.90))
        p.fillRect(p1, QBrush(scrim))
        p.restore()
        fg_main, fg_sub = QColor('#f8fafc'), ui.rgba(226, 234, 248, 0.84)
    else:
        fg_main, fg_sub = ui.TEXT, ui.MUTED
    draw_square_rim(win, p, p1, hero_gm, 2.0 * u, True)

    play_lbl = 'Fortsetzen' if (win.RUN and win.RUN.get('paused') and win.RUN['id'] == hero_gm['id']) else 'Weiterspielen'
    pf = ('u', 1.55, 700)
    pw_btn = win.width_of(play_lbl, pf) + 4.0 * u
    pbtn = QRectF(p1.x() + 1.4 * u, p1.y() + 1.3 * u, pw_btn, 3.7 * u)
    win.capsule(p, pbtn, ui.FOCUS)
    draw_svg(p, 'pod_play', QRectF(pbtn.x() + 1.0 * u, pbtn.y() + 0.85 * u, 2.0 * u, 2.0 * u), ui.INK)
    win.text(p, play_lbl, pbtn.x() + 2.1 * u, pbtn.y(), pf, ui.INK, pw_btn - 2.4 * u, 1, 3.7 / 1.55)
    win.text(p, hero_gm['t'], p1.x() + 1.5 * u, p1.bottom() - 5.4 * u, ('u', 2.0, 700, -.015), fg_main, w_hero - 3.0 * u)
    p_secs = int(played.get('secs') or 0)
    meta_parts = [win.sys_name(hero_gm)] + ([ui.hours(p_secs)] if p_secs else [])
    win.text(p, '  ·  '.join(meta_parts), p1.x() + 1.5 * u, p1.bottom() - 2.8 * u, ('u', 1.45, 500), fg_sub, w_hero - 3.0 * u)
    win.hit(p1, lambda g=hero_gm: win.start(g), name='pod:continue')

    p2 = QRectF(p1.right() + gap, y, w_side, pod_h)
    glass_card(win, p, p2, 2.0 * u)
    draw_square_rim(win, p, p2, {'s': 'switch'}, 2.0 * u, False)
    ic_r2 = QRectF(p2.x() + 1.4 * u, y + 1.4 * u, 4.2 * u, 4.2 * u)
    win.box(p, ic_r2, 1.1 * u, ui.faded(ui.FOCUS, 0.18), ui.faded(ui.FOCUS, 0.35))
    draw_svg(p, 'pod_dice', ic_r2.adjusted(0.8 * u, 0.8 * u, -0.8 * u, -0.8 * u), ui.FOCUS)
    short_gm = next((g for g in (win.L.get('games') or [])
                     if g['id'] != hero_gm['id'] and 0 < float(g.get('ttb') or 0) <= 5.5 and g.get('inst') != 'no'), None)
    win.text(p, 'Überrasch mich', p2.x() + 1.5 * u, p2.bottom() - 5.4 * u, ('u', 1.85, 700), ui.TEXT, w_side - 3.0 * u)
    sub2 = f'Kurz-Tipp: {short_gm["t"]}' if short_gm else 'Zufälliges Spiel aus deiner Sammlung'
    win.text(p, sub2, p2.x() + 1.5 * u, p2.bottom() - 2.8 * u, ('u', 1.42, 500), ui.MUTED, w_side - 3.0 * u)
    win.hit(p2, win.pick_random, name='pod:discover')

    p3 = QRectF(p2.right() + gap, y, w_side, pod_h)
    glass_card(win, p, p3, 2.0 * u)
    draw_square_rim(win, p, p3, {'s': 'steam'}, 2.0 * u, False)
    ic_r3 = QRectF(p3.x() + 1.4 * u, y + 1.4 * u, 4.2 * u, 4.2 * u)
    win.box(p, ic_r3, 1.1 * u, ui.faded(ui.LIVE, 0.18), ui.faded(ui.LIVE, 0.35))
    draw_svg(p, 'pod_spark', ic_r3.adjusted(0.8 * u, 0.8 * u, -0.8 * u, -0.8 * u), ui.LIVE)
    total_games = sum(1 for g in (win.L.get('games') or []) if g.get('s') not in ('app', 'term') and g.get('inst') != 'no')
    total_secs = sum(int((v or {}).get('secs') or 0) for v in (win.L.get('played') or {}).values())
    win.text(p, f'{total_games} Spiele bereit', p3.x() + 1.5 * u, p3.bottom() - 5.4 * u, ('u', 1.85, 700), ui.TEXT, w_side - 3.0 * u)
    sub3 = (f'{ui.hours(total_secs)} gespielt · Kosmos starten' if total_secs >= 60 else '3D-Kosmos-Schaufenster öffnen')
    win.text(p, sub3, p3.x() + 1.5 * u, p3.bottom() - 2.8 * u, ('u', 1.42, 500), ui.MUTED, w_side - 3.0 * u)
    win.hit(p3, lambda: win.post('api/saver', {'open': True}), name='pod:showcase')

    return y + pod_h + 2.0 * u


def draw_launch_ceremony(win, p):
    """360 ms Nintendo/iiSU-style Console Launch Ceremony while the game process spins up (never ticks once playing)."""
    la = getattr(win, 'LAUNCH_FX', None)
    if not la:
        return
    age = time.time() - la['at']
    dur = 0.36
    if age >= dur or win.playing() or win.CFG.get('motion') == 'reduced':
        win.LAUNCH_FX = None
        return
    ui.QTimer.singleShot(16, win.update)
    t = age / dur
    ease = 1.0 - (1.0 - t) ** 3
    W, H, u = win.width(), win.height(), win.u

    p.save()
    ring_r = max(W, H) * (0.12 + 0.85 * ease)
    bloom = QRadialGradient(QPointF(W * 0.5, H * 0.5), ring_r)
    alpha_c = (1.0 - t) * 0.48
    bloom.setColorAt(0.0, ui.faded(ui.FOCUS, alpha_c))
    bloom.setColorAt(0.55, ui.faded(ui.FOCUS, alpha_c * 0.32))
    bloom.setColorAt(1.0, ui.rgba(0, 0, 0, min(0.80, t * 0.92)))
    p.fillRect(QRectF(0, 0, W, H), QBrush(bloom))

    if win.side == 'top' and la.get('title'):
        scale = 1.0 + 0.06 * ease
        p.translate(W * 0.5, H * 0.5)
        p.scale(scale, scale)
        p.translate(-W * 0.5, -H * 0.5)
        p.setOpacity(max(0.0, 1.0 - t * 1.15))
        win.text(p, la['title'], W * 0.1, H * 0.46, ('u', 4.2, 700, -.025), QColor('#ffffff'), W * 0.8, 1)
    p.restore()
