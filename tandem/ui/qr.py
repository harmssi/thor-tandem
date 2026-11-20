"""Compact pure-Python QR Code encoder (Byte mode, Versions 1-6, Error Correction L) + SVG and PNG helpers."""
import struct, zlib

# (total_codewords, ec_codewords_per_block, num_blocks, alignment_centers) for Versions 1..6 (EC level L)
VERSIONS = [
    None,
    (26, 7, 1, ()),              # v1: 21x21, up to 17 bytes
    (44, 10, 1, (6, 18)),        # v2: 25x25, up to 32 bytes
    (70, 15, 1, (6, 22)),        # v3: 29x29, up to 53 bytes
    (100, 20, 1, (6, 26)),       # v4: 33x33, up to 78 bytes
    (134, 26, 1, (6, 30)),       # v5: 37x37, up to 106 bytes
    (172, 18, 2, (6, 34)),       # v6: 41x41, up to 134 bytes
]

EXP, LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x
    LOG[_x] = _i
    _x = (_x << 1) ^ (0x11D if _x & 0x80 else 0)
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def _gf_mul(a, b):
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def _rs_encode(data, nsym):
    gen = [1]
    for i in range(nsym):
        nxt = [0] * (len(gen) + 1)
        for j, g in enumerate(gen):
            nxt[j] ^= g
            nxt[j + 1] ^= _gf_mul(g, EXP[i])
        gen = nxt
    rem = list(data) + [0] * nsym
    for i in range(len(data)):
        coef = rem[i]
        if coef:
            for j in range(1, len(gen)):
                rem[i + j] ^= _gf_mul(gen[j], coef)
    return rem[len(data):]


def _format_bits(ec_bits, mask):
    data = (ec_bits << 3) | mask
    rem = data << 10
    for i in range(4, -1, -1):
        if rem & (1 << (i + 10)):
            rem ^= 0x537 << i
    return ((data << 10) | rem) ^ 0x5412


def _penalty(grid):
    n, score = len(grid), 0
    for r in range(n):
        run_h, run_v = 1, 1
        for c in range(1, n):
            run_h = run_h + 1 if grid[r][c] == grid[r][c - 1] else 1
            if run_h == 5: score += 3
            elif run_h > 5: score += 1
            run_v = run_v + 1 if grid[c][r] == grid[c - 1][r] else 1
            if run_v == 5: score += 3
            elif run_v > 5: score += 1
    for r in range(n - 1):
        for c in range(n - 1):
            v = grid[r][c]
            if v == grid[r][c + 1] == grid[r + 1][c] == grid[r + 1][c + 1]:
                score += 3
    pat1, pat2 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    for r in range(n):
        row = [1 if x else 0 for x in grid[r]]
        col = [1 if grid[k][r] else 0 for k in range(n)]
        for c in range(n - 10):
            if row[c:c + 11] in (pat1, pat2): score += 40
            if col[c:c + 11] in (pat1, pat2): score += 40
    dark = sum(sum(1 for x in row if x) for row in grid)
    score += (abs(dark * 20 - n * n * 10) // (n * n)) * 10
    return score


def matrix(text):
    """Encode UTF-8 text (up to 134 bytes) into a square bool matrix (True = dark module)."""
    raw = text.encode('utf-8')
    ver = next((v for v in range(1, len(VERSIONS)) if len(raw) <= VERSIONS[v][0] - VERSIONS[v][1] * VERSIONS[v][2] - 2), 0)
    if not ver:
        raise ValueError('QR text too long')
    total_cw, ec_cw, blocks, aligns = VERSIONS[ver]
    data_cw = total_cw - ec_cw * blocks

    bits = [0, 1, 0, 0] + [(len(raw) >> i) & 1 for i in range(7, -1, -1)]
    for b in raw:
        bits.extend((b >> i) & 1 for i in range(7, -1, -1))
    bits.extend([0] * min(4, data_cw * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    codewords = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pads = (0xEC, 0x11)
    while len(codewords) < data_cw:
        codewords.append(pads[len(codewords) % 2])

    step = data_cw // blocks
    dblocks = [codewords[i * step:(i + 1) * step] for i in range(blocks)]
    eblocks = [_rs_encode(b, ec_cw) for b in dblocks]
    stream = [b[i] for i in range(step) for b in dblocks] + [e[i] for i in range(ec_cw) for e in eblocks]
    all_bits = [(cw >> i) & 1 for cw in stream for i in range(7, -1, -1)]

    size = 17 + 4 * ver
    grid = [[False] * size for _ in range(size)]
    used = [[False] * size for _ in range(size)]

    def set_mod(r, c, val):
        grid[r][c] = bool(val)
        used[r][c] = True

    for fr, fc in ((0, 0), (0, size - 7), (size - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = fr + dr, fc + dc
                if 0 <= r < size and 0 <= c < size:
                    in_outer = 0 <= dr <= 6 and 0 <= dc <= 6
                    on_ring = dr in (0, 6) or dc in (0, 6)
                    in_core = 2 <= dr <= 4 and 2 <= dc <= 4
                    set_mod(r, c, in_outer and (on_ring or in_core))

    for ar in aligns:
        for ac in aligns:
            if (ar < 9 and ac < 9) or (ar < 9 and ac > size - 10) or (ar > size - 10 and ac < 9):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    set_mod(ar + dr, ac + dc, max(abs(dr), abs(dc)) in (0, 2))

    for i in range(8, size - 8):
        if not used[6][i]: set_mod(6, i, i % 2 == 0)
        if not used[i][6]: set_mod(i, 6, i % 2 == 0)

    for i in range(9):
        if i != 6:
            used[8][i] = used[i][8] = True
    for i in range(8):
        used[8][size - 1 - i] = used[size - 1 - i][8] = True
    set_mod(size - 8, 8, True)

    bit_idx, upward, col = 0, True, size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for dc in (0, -1):
                c = col + dc
                if not used[r][c]:
                    grid[r][c] = bool(all_bits[bit_idx]) if bit_idx < len(all_bits) else False
                    bit_idx += 1
        upward = not upward
        col -= 2

    masks = (
        lambda r, c: (r + c) % 2 == 0,
        lambda r, c: r % 2 == 0,
        lambda r, c: c % 3 == 0,
        lambda r, c: (r + c) % 3 == 0,
        lambda r, c: (r // 2 + c // 3) % 2 == 0,
        lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
        lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
        lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
    )

    def apply_mask(m):
        cand = [row[:] for row in grid]
        fn = masks[m]
        for r in range(size):
            for c in range(size):
                if not used[r][c] and fn(r, c):
                    cand[r][c] = not cand[r][c]
        fmt = _format_bits(0b01, m)  # EC Level L = 01
        pts_a = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                 (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
        pts_b = [(size - 1 - i, 8) for i in range(7)] + [(8, size - 8 + i) for i in range(8)]
        for i in range(15):
            bit = bool((fmt >> (14 - i)) & 1)
            cand[pts_a[i][0]][pts_a[i][1]] = bit
            cand[pts_b[i][0]][pts_b[i][1]] = bit
        return cand

    return min((apply_mask(m) for m in range(8)), key=_penalty)


def svg(text, border=2):
    """Compact inline SVG string (crispEdges) for remote.html."""
    m = matrix(text)
    n = len(m) + 2 * border
    parts = [f'M{c + border},{r + border}h1v1h-1z' for r, row in enumerate(m) for c, v in enumerate(row) if v]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges">'
            f'<rect width="{n}" height="{n}" fill="#ffffff"/><path d="{"".join(parts)}" fill="#0b0b10"/></svg>')


def draw(p, rect, text, radius=16):
    """Draw a pixel-sharp QR card with white quiet zone onto QPainter p inside QRectF rect."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor
    m = matrix(text)
    n = len(m) + 6
    side = int(min(rect.width(), rect.height()))
    cell = max(2, side // n)
    card_s = cell * n
    ox = int(rect.x() + (rect.width() - card_s) / 2)
    oy = int(rect.y() + (rect.height() - card_s) / 2)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255))
    p.drawRoundedRect(QRectF(ox, oy, card_s, card_s), radius, radius)
    p.setRenderHint(p.RenderHint.Antialiasing, False)
    p.setBrush(QColor(11, 11, 16))
    bx, by = ox + 3 * cell, oy + 3 * cell
    for r, row in enumerate(m):
        for c, v in enumerate(row):
            if v:
                p.drawRect(bx + c * cell, by + r * cell, cell, cell)
    p.restore()


def png(text, scale=10, border=4, pad_w=0, pad_h=0, bg=(11, 11, 16)):
    """Grayscale/RGB PNG bytes; if pad_w/pad_h are given, centers a white QR card on a dark canvas (for mpv top screen)."""
    m = matrix(text)
    qn = (len(m) + 2 * border) * scale
    W, H = max(qn, pad_w), max(qn, pad_h)
    ox, oy = (W - qn) // 2, (H - qn) // 2
    white_row = b'\xff\xff\xff'
    dark_px = b'\x0b\x0b\x10'
    bg_px = bytes(bg)
    qr_rows = {}
    for qr_y in range(len(m) + 2 * border):
        r = qr_y - border
        if 0 <= r < len(m):
            line = white_row * (border * scale) + b''.join((dark_px if v else white_row) * scale for v in m[r]) + white_row * (border * scale)
        else:
            line = white_row * qn
        qr_rows[qr_y] = b'\x00' + bg_px * ox + line + bg_px * (W - ox - qn)
    empty = b'\x00' + bg_px * W
    raw = bytearray()
    for y in range(H):
        if oy <= y < oy + qn:
            raw.extend(qr_rows[(y - oy) // scale])
        else:
            raw.extend(empty)

    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xFFFFFFFF)

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(raw), 6))
            + chunk(b'IEND', b''))
