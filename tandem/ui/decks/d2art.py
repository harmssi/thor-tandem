"""Diablo II's own look for the D2 deck, read at runtime from the player's MPQs, as Thor D2 does it on Android (D2Mpq,
D2Sprites, D2Frame, D2Strings, D2LevelNames, D2Hud, D2DeckArt): the panel frames, the orbs, the game's fonts, skill icons and
names, item pictures, area and quest names. Nothing of the game is part of Tandem. Files once unpacked are kept under
~/.cache/tandem/d2 (per set of archives), so a later start does not unpack them again.

Plain Python except Art (QImage, QPainter); mpq_hash(), explode(), dc6() and Strings carry the logic worth testing.
"""
import hashlib, os, re, struct, threading, zlib
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

ARCHIVES = ('Patch_D2.mpq', 'd2exp.mpq', 'd2data.mpq', 'd2char.mpq')  # first found wins, as in the game
LANGUAGES = ('eng', 'esp', 'deu', 'fra', 'por', 'ita', 'jpn', 'kor', 'sin', 'chi', 'pol', 'rus')
M = 0xFFFFFFFF


def _crypt():
    table, seed = [0] * 0x500, 0x00100001
    for i in range(0x100):
        for k in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            high = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            table[i + k * 0x100] = high | (seed & 0xFFFF)
    return table


CRYPT = _crypt()


def mpq_hash(text, kind):
    s1, s2 = 0x7FED7FED, 0xEEEEEEEE
    for ch in text.upper().replace('/', '\\'):
        c = ord(ch) & 0xFF
        s1 = (CRYPT[(kind << 8) + c] ^ (s1 + s2)) & M
        s2 = (c + s1 + s2 + (s2 << 5) + 3) & M
    return s1


def decrypt(data, key):
    n = len(data) // 4
    out, seed = [], 0xEEEEEEEE
    for word in struct.unpack_from(f'<{n}I', data):
        seed = (seed + CRYPT[0x400 + (key & 0xFF)]) & M
        value = word ^ ((key + seed) & M)
        key = (((~key << 21) + 0x11111111) & M) | (key >> 11)
        seed = (value + seed + (seed << 5) + 3) & M
        out.append(value)
    return struct.pack(f'<{n}I', *out) + bytes(data[n * 4:])


# ---- PKWARE DCL explode (after blast.c by Mark Adler, zlib licence), with lookup tables instead of bit-by-bit decoding --
def _table(rep):
    lengths = [r & 15 for r in rep for _ in range((r >> 4) + 1)]
    table, code = [None] * (1 << 13), 0
    for n in range(1, 14):  # canonical codes, shortest first, symbols in order; blast reads them inverted, first bit first
        for sym in (s for s, l in enumerate(lengths) if l == n):
            raw = sum((1 - (code >> (n - 1 - i) & 1)) << i for i in range(n))
            for high in range(1 << (13 - n)): table[raw | high << n] = (sym, n)
            code += 1
        code <<= 1
    return table


LIT = _table([11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8, 9, 7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11,
              12, 6, 7, 22, 5, 7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12, 8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21,
              6, 10, 53, 8, 7, 24, 10, 27, 44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45, 44, 173])
LEN = _table([2, 35, 36, 53, 38, 23])
DIST = _table([2, 20, 53, 230, 247, 151, 248])
BASE = (3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264)
EXTRA = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8)


def explode(data, size):
    """Unpacks PKWARE 'implode' data (most files in the D2 MPQs) to at most size bytes."""
    if len(data) < 2 or data[0] > 1 or not 4 <= data[1] <= 6: raise ValueError('explode: bad header')
    lit, dic, buf, end, p, out = data[0], data[1], bytes(data) + bytes(4), len(data) * 8, 16, bytearray()

    def peek(at): return int.from_bytes(buf[at >> 3:(at >> 3) + 4], 'little') >> (at & 7)

    while len(out) < size:
        if p >= end: raise ValueError('explode: out of input')
        v = peek(p)
        if v & 1:
            hit = LEN[v >> 1 & 0x1FFF]
            if not hit: raise ValueError('explode: bad code')
            p += 1 + hit[1]
            n = BASE[hit[0]] + (peek(p) & ((1 << EXTRA[hit[0]]) - 1))
            p += EXTRA[hit[0]]
            if n == 519: break
            shift = 2 if n == 2 else dic
            hit = DIST[peek(p) & 0x1FFF]
            if not hit: raise ValueError('explode: bad code')
            p += hit[1]
            dist = (hit[0] << shift) + (peek(p) & ((1 << shift) - 1)) + 1
            p += shift
            if dist > len(out): raise ValueError('explode: distance too far back')
            n = min(n, size - len(out))
            if dist >= n: out += out[-dist:len(out) - dist + n]
            else:
                for _ in range(n): out.append(out[-dist])
        elif lit:
            hit = LIT[v >> 1 & 0x1FFF]
            if not hit: raise ValueError('explode: bad code')
            out.append(hit[0])
            p += 1 + hit[1]
        else:
            out.append(v >> 1 & 0xFF)
            p += 9
    if p > end + 7: raise ValueError('explode: out of input')
    return bytes(out)


class Mpq:
    """Reads files out of one MPQ archive (format 1, as Diablo II's)."""
    IMPLODE, COMPRESS, ENCRYPTED, FIX_KEY, SINGLE, EXISTS = 0x100, 0x200, 0x10000, 0x20000, 0x1000000, 0x80000000

    def __init__(self, path):
        self.file, self.lock = open(path, 'rb'), threading.Lock()
        size = os.path.getsize(path)
        self.base = next((at for at in range(0, min(size, 1 << 20), 512) if self.at(at, 4) == b'MPQ\x1a'), None)
        if self.base is None: self.file.close(); raise OSError(f'kein MPQ: {path}')
        head = self.at(self.base, 32)
        self.sector = 512 << struct.unpack_from('<H', head, 14)[0]
        hash_at, block_at, hashes, blocks = struct.unpack_from('<4I', head, 16)
        self.hashes = struct.unpack(f'<{hashes * 4}I', decrypt(self.at(self.base + hash_at, hashes * 16), mpq_hash('(hash table)', 3)))
        self.blocks = struct.unpack(f'<{blocks * 4}I', decrypt(self.at(self.base + block_at, blocks * 16), mpq_hash('(block table)', 3)))

    def at(self, pos, n):
        with self.lock:
            self.file.seek(pos)
            data = self.file.read(n)
        if len(data) != n: raise OSError('MPQ: Lesen über das Ende')
        return data

    def find(self, name):
        count = len(self.hashes) // 4
        index, a, b = mpq_hash(name, 0) & (count - 1), mpq_hash(name, 1), mpq_hash(name, 2)
        for n in range(count):
            at = ((index + n) & (count - 1)) * 4
            block = self.hashes[at + 3]
            if block == M: return -1
            if self.hashes[at] == a and self.hashes[at + 1] == b and block != M - 1: return block
        return -1

    def read(self, name):
        block = self.find(name)
        if block < 0 or block * 4 >= len(self.blocks): return None
        offset, packed, size, flags = self.blocks[block * 4:block * 4 + 4]
        if not flags & self.EXISTS: return None
        if size > 128 << 20: raise OSError(f'MPQ: {name} zu groß')
        key = 0
        if flags & self.ENCRYPTED:
            key = mpq_hash(name[name.rfind('\\') + 1:], 3)
            if flags & self.FIX_KEY: key = ((key + offset) & M) ^ size
        start = self.base + offset
        if flags & self.SINGLE:
            data = self.at(start, packed)
            if flags & self.ENCRYPTED: data = decrypt(data, key)
            return self.unpack(data, size, flags)
        sectors = (size + self.sector - 1) // self.sector
        compressed = flags & (self.IMPLODE | self.COMPRESS)
        if compressed:
            table = self.at(start, (sectors + 1) * 4)
            if flags & self.ENCRYPTED: table = decrypt(table, (key - 1) & M)
            starts = struct.unpack(f'<{sectors + 1}I', table)
        else: starts = [min(i * self.sector, size) for i in range(sectors + 1)]
        out = bytearray()
        for i in range(sectors):
            want, n = min(self.sector, size - i * self.sector), starts[i + 1] - starts[i]
            if n <= 0 or n > want: raise OSError('MPQ: Sektortabelle kaputt')
            data = self.at(start + starts[i], n)
            if flags & self.ENCRYPTED: data = decrypt(data, (key + i) & M)
            out += self.unpack(data, want, flags) if compressed and n < want else data[:want]
        return bytes(out)

    def unpack(self, data, size, flags):
        if flags & self.IMPLODE: return explode(data, size)
        if data[0] == 0x08: return explode(data[1:], size)
        if data[0] == 0x02: return zlib.decompress(data[1:])[:size]
        raise OSError(f'MPQ: Kompression {data[0]:#x} fehlt')  # Huffman/ADPCM: sound only, the deck needs none

    def close(self): self.file.close()


def _gamma(i): return 0 if i == 0 else min(255, int(12 + 243 * (i / 255) ** (1 / 1.2) + .5))


GAMMA = [_gamma(i) for i in range(256)]


def palette(pal):
    """pal.dat (BGR triples) -> 256 pixels as QImage.Format_ARGB32 bytes (B, G, R, A), with Thor D2's gamma lift."""
    return [bytes((GAMMA[pal[i * 3]], GAMMA[pal[i * 3 + 1]], GAMMA[pal[i * 3 + 2]], 255)) for i in range(256)]


def dc6(d, pal):
    """The frames of a DC6 picture: [(width, height, offset x, offset y, ARGB32 bytes)]."""
    if len(d) < 24 or struct.unpack_from('<i', d)[0] != 6: raise ValueError('kein DC6')
    dirs, per = struct.unpack_from('<2i', d, 16)
    frames = []
    for f in range(dirs * per):
        p = struct.unpack_from('<I', d, 24 + f * 4)[0]
        flip, w, h, ox, oy = struct.unpack_from('<5i', d, p)
        n = struct.unpack_from('<I', d, p + 28)[0]
        px, x, y, i, end = bytearray(max(1, w * h) * 4), 0, 0 if flip else h - 1, p + 32, min(len(d), p + 32 + n)
        while i < end and 0 <= y < h:
            b = d[i]
            i += 1
            if b == 0x80: x, y = 0, y + (1 if flip else -1)
            elif b & 0x80: x += b & 0x7F
            else:
                run = d[i:min(end, i + b)]
                i += b
                k = max(0, min(len(run), w - x))
                if k: px[(y * w + x) * 4:(y * w + x + k) * 4] = b''.join(pal[c] for c in run[:k])
                x += len(run)
        frames.append((max(1, w), max(1, h), ox, oy, px))
    return frames


class Strings:
    """The game's string tables (.tbl): by key ('qstsa1q1') or by number, patch before expansion before base."""
    def __init__(self, base, patch, expansion):
        self.tables, self.keys = [base, patch, expansion], [None] * 3

    @staticmethod
    def text(d, at, n):
        end = at
        while end < len(d) and end - at < max(n, 1) and d[end]: end += 1
        raw = d[at:end]
        try: s = raw.decode('utf-8')
        except UnicodeDecodeError: s = raw.decode('cp1252', 'replace')
        return re.sub('ÿc.', '', s)  # the game's colour codes

    def index(self, t):
        if self.keys[t] is None:
            d, keys = self.tables[t], {}
            if d and len(d) >= 21:
                count, slots = struct.unpack_from('<Hi', d, 2)
                for i in range(max(0, slots)):
                    node = 21 + count * 2 + i * 17
                    if node + 17 > len(d) or not d[node]: continue
                    key_at, at, n = struct.unpack_from('<IIH', d, node + 7)
                    end = d.find(b'\0', key_at)
                    if key_at < len(d) and end > 0: keys.setdefault(d[key_at:end].decode('cp1252', 'replace'), (at, n))
            self.keys[t] = keys
        return self.keys[t]

    def get(self, key):
        if isinstance(key, int): return self.by_number(key)
        for t in (1, 2, 0):
            hit = self.index(t).get(key)
            if hit: return self.text(self.tables[t], *hit) if hit[0] < len(self.tables[t]) else None
        return None

    def by_number(self, n):
        if n < 0: return None
        t = 0 if n < 10000 else 1 if n < 20000 else 2
        d, i = self.tables[t], n - t * 10000
        if not d or len(d) < 21: return None
        count = struct.unpack_from('<H', d, 2)[0]
        if i >= count or 23 + i * 2 > len(d): return None
        node = 21 + count * 2 + struct.unpack_from('<H', d, 21 + i * 2)[0] * 17
        if node + 17 > len(d) or not d[node]: return None
        at, n = struct.unpack_from('<IH', d, node + 11)
        return self.text(d, at, n) if at < len(d) else None


def s32(d, at): return struct.unpack_from('<i', d, at)[0]


def u16(d, at): return struct.unpack_from('<H', d, at)[0]


def image(frame):
    w, h, _, _, px = frame
    return QImage(bytes(px), w, h, w * 4, QImage.Format.Format_ARGB32).copy()


def cropped(img):
    """The picture without its empty border (D2Hud.cropped)."""
    w, h = img.width(), img.height()
    xs = [x for y in range(h) for x in range(w) if img.pixel(x, y) >> 24]
    if not xs: return img
    ys = [y for y in range(h) for x in range(w) if img.pixel(x, y) >> 24]
    return img.copy(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def mirror(img): return img.flipped(Qt.Orientation.Horizontal) if hasattr(img, 'flipped') else img.mirrored(True, False)


class Font:
    """A bitmap font of the game (DC6 glyphs, TBL widths), tinted per colour; size = height of a capital H."""
    def __init__(self, frames, tbl):
        self.widths = [tbl[12 + i * 14 + 3] for i in range(256)]
        self.atlas = QImage(sum(f[0] for f in frames[:256]), max(f[1] for f in frames[:256]), QImage.Format.Format_ARGB32_Premultiplied)
        self.atlas.fill(0)
        self.rects, x, p = [], 0, QPainter(self.atlas)
        for f in frames[:256]:
            self.rects.append(QRectF(x, 0, f[0], f[1]) if f[0] > 0 and f[1] > 0 else None)
            p.drawImage(x, 0, image(f))
            x += f[0]
        p.end()
        h = frames[ord('H')]
        rows = [y for y in range(h[1]) if any(h[4][(y * h[0] + x) * 4 + 3] for x in range(h[0]))]
        self.height, self.tints = max(1, rows[-1] - rows[0] + 1) if rows else h[1], {}

    @staticmethod
    def map(text):  # D2FontText: what the font lacks becomes a stand-in
        return ''.join(c if ord(c) <= 255 else {'“': '"', '”': '"', '„': '"', '‚': "'", '‘': "'", '’': "'", '–': '-', '—': '-', '→': '>',
                                                    '←': '<', '…': '...', '≡': '='}.get(c, '?') for c in text)

    def width(self, text, size):
        return sum(self.widths[ord(c)] for c in self.map(text)) * size / self.height

    def tinted(self, rgb):
        if rgb not in self.tints:
            img = self.atlas.copy()
            p = QPainter(img)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            p.fillRect(img.rect(), QColor.fromRgb(rgb))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            p.drawImage(0, 0, self.atlas)
            p.end()
            self.tints[rgb] = img
        return self.tints[rgb]

    def draw(self, p, text, x, y, size, rgb, align=0):
        """Glyph cells end at y; align 0 left, 1 centre, 2 right of x."""
        text, k = self.map(text), size / self.height
        if align: x -= self.width(text, size) / (2 if align == 1 else 1)
        atlas = self.tinted(rgb & 0xFFFFFF)
        for c in text:
            r = self.rects[ord(c)]
            if r: p.drawImage(QRectF(x, y - r.height() * k, r.width() * k, r.height() * k), atlas, r)
            x += self.widths[ord(c)] * k


class Frame:
    """The game's panel frame (ui/MENU/boxpieces.dc6), laid around any size as D2Frame does."""
    TILE, LINE = 12, 3

    def __init__(self, frames):
        def piece(i):
            img = image(frames[i])
            c = cropped(img)
            return c
        self.tl, self.tr, self.bl, self.br = (piece(i) for i in (0, 1, 8, 9))
        self.top, self.bottom = [piece(2 + i) for i in range(6)], [piece(16 + i) for i in range(6)]
        self.left, self.right = [piece(10 + i) for i in range(3)], [piece(13 + i) for i in range(3)]
        self.cache = {}

    @staticmethod
    def pick(variants, i, edge):
        return variants[(((i * 0x9E3779B1 + edge * 0x85EBCA6B) & M) >> 16) % len(variants)]

    def compose(self, w, h, fill):
        w, h = max(2 * self.LINE, w), max(2 * self.LINE, h)
        key = (w, h, fill)
        if key not in self.cache:
            if len(self.cache) > 64: self.cache.clear()
            img = QImage(w, h, QImage.Format.Format_ARGB32)
            img.fill(0)
            p = QPainter(img)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(1, 1, w - 2, h - 2, QColor.fromRgba(fill))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            T, L = self.TILE, self.LINE

            def put(img_, sx, sy, n, m, dx, dy):
                x0, y0 = max(0, -sx, -dx), max(0, -sy, -dy)
                x1, y1 = min(n, img_.width() - sx, w - dx), min(m, img_.height() - sy, h - dy)
                if x1 > x0 and y1 > y0: p.drawImage(dx + x0, dy + y0, img_, sx + x0, sy + y0, x1 - x0, y1 - y0)
            corner = max(L, min(T, w // 2, h // 2))
            for i, x in enumerate(range(corner, w - corner, T)):
                n = min(T, w - corner - x)
                put(self.pick(self.top, i, 1), 0, 0, n, L, x, 0)
                put(self.pick(self.bottom, i, 2), 0, 0, n, L, x, h - L)
            for i, y in enumerate(range(corner, h - corner, T)):
                n = min(T, h - corner - y)
                put(self.pick(self.left, i, 3), 0, 0, L, n, 0, y)
                put(self.pick(self.right, i, 4), 0, 0, L, n, w - L, y)
            put(self.tl, 0, 0, corner, corner, 0, 0)
            put(self.tr, T - corner, 0, corner, corner, w - corner, 0)
            put(self.bl, 0, T - corner, corner, corner, 0, h - corner)
            put(self.br, T - corner, T - corner, corner, corner, w - corner, h - corner)
            p.end()
            self.cache[key] = img
        return self.cache[key]


class Sprites:
    """The archives in the game's order, and a cache of what was unpacked."""
    def __init__(self, game_dir, cache_dir):
        names = {f.name.lower(): f for f in Path(game_dir).iterdir()} if Path(game_dir).is_dir() else {}
        self.mpqs = []
        for name in ARCHIVES:
            f = names.get(name.lower())
            if not f: continue
            try: self.mpqs.append(Mpq(f))
            except OSError:
                if name != 'd2char.mpq': raise
        if not self.mpqs: raise OSError(f'keine Archive in {game_dir}')
        stamp = '|'.join(f'{m.file.name}:{os.path.getsize(m.file.name)}:{os.path.getmtime(m.file.name)}' for m in self.mpqs)
        self.cache = Path(cache_dir) / hashlib.sha1(stamp.encode()).hexdigest()[:16]
        pal = self.read('data\\global\\palette\\ACT1\\pal.dat')
        if not pal or len(pal) < 768: raise OSError('keine Palette')
        self.pal = palette(pal)

    def read(self, name):
        cached = self.cache / name.lower().replace('\\', '/')
        try: return cached.read_bytes()
        except OSError: pass
        for mpq in self.mpqs:
            data = mpq.read(name)
            if data is not None:
                try:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    tmp = cached.with_suffix(cached.suffix + '.tmp')
                    tmp.write_bytes(data)
                    tmp.replace(cached)
                except OSError: pass
                return data
        return None

    def dc6(self, name):
        d = self.read(name)
        return dc6(d, self.pal) if d else None

    def close(self):
        for m in self.mpqs: m.close()


ITEM_RECORD = 424


class Art:
    """Everything the deck draws from the game (D2Hud + D2DeckArt, only what the deck uses). Raises when the files miss."""
    ICON_FILES = ('Am', 'So', 'Ne', 'Pa', 'Ba', 'Dr', 'As', '')

    def __init__(self, game_dir, cache_dir):
        s = self.s = Sprites(game_dir, cache_dir)

        def need(name, n):
            f = s.dc6(name)
            if not f or len(f) < n: raise OSError(f'fehlt: {name}')
            return f
        orbs, glass = need('data\\global\\ui\\PANEL\\hlthmana.dc6', 2), need('data\\global\\ui\\PANEL\\overlap.dc6', 2)
        self.orbs = [mirror(image(orbs[0])), mirror(image(orbs[1]))]
        self.glass = [mirror(image(glass[0])), mirror(image(glass[1]))]
        boxes = s.dc6('data\\global\\ui\\MENU\\boxpieces.dc6')
        self.frame = Frame(boxes) if boxes and len(boxes) >= 22 else None
        self.title, self.body = self.font('font30'), self.font('font16')
        try: self.small = self.font('font8')
        except OSError: self.small = None
        self.mini = [cropped(image(f)) for f in need('data\\global\\ui\\PANEL\\minipanelbtn.dc6', 16)]
        merc, cube = s.dc6('data\\global\\ui\\Hireables\\RogueIcon.dc6'), s.dc6('data\\global\\items\\invbox.dc6')
        self.merc_icon, self.cube_icon = (cropped(image(f[0])) if f else None for f in (merc, cube))
        use = s.read('data\\local\\use')
        wanted = LANGUAGES[use[0]] if use and use[0] < len(LANGUAGES) else 'eng'
        self.strings = None
        for lng in (wanted, 'eng'):
            base, exp = s.read(f'data\\local\\lng\\{lng}\\string.tbl'), s.read(f'data\\local\\lng\\{lng}\\expansionstring.tbl')
            if base and exp:
                self.strings = Strings(base, s.read(f'data\\local\\lng\\{lng}\\patchstring.tbl'), exp)
                break
        if not self.strings: raise OSError('keine Texttabellen')
        self.levels = self.level_keys(s.read('data\\global\\excel\\levels.bin'))
        self.read_skills(s.read('data\\global\\excel\\skills.bin'), s.read('data\\global\\excel\\skilldesc.bin'))
        self.icons = [None] * 8
        for i, cls in enumerate(self.ICON_FILES):
            f = s.dc6(f'data\\global\\ui\\SPELLS\\{cls}Skillicon.dc6')
            if f: self.icons[i] = [image(x) for x in f]
        self.inv_files = {}
        for table in ('weapons', 'armor', 'misc'):
            d = s.read(f'data\\global\\excel\\{table}.bin')
            n = s32(d, 0) if d and len(d) >= 4 else 0
            if n <= 0 or 4 + n * ITEM_RECORD > len(d): continue
            for i in range(n):
                at = 4 + i * ITEM_RECORD
                files = [d[at + o:at + o + 32].split(b'\0')[0].decode('latin-1') for o in (0x20, 0x40, 0x60)]
                self.inv_files[d[at + 0x80:at + 0x84].decode('latin-1').replace('\0', ' ').strip()] = [x if re.fullmatch('[A-Za-z0-9_]*', x) else '' for x in files]
        self.pictures, self.lock, self.wanted, self.loader = {}, threading.Lock(), [], None

    def font(self, name):
        f, tbl = self.s.dc6(f'data\\local\\font\\latin\\{name}.dc6'), self.s.read(f'data\\local\\font\\latin\\{name}.tbl')
        if not f or len(f) < 256 or not tbl or len(tbl) < 12 + 14 * 256: raise OSError(f'keine Schrift {name}')
        return Font(f, tbl)

    def text(self, key):
        return self.strings.get(key)

    def level_keys(self, d):
        rec = 544
        if not d or len(d) < 4 + 3 * rec or s32(d, 0) <= 2 or s32(d, 0) * rec + 4 != len(d): return None
        keys = []
        for i in range(s32(d, 0)):
            at = 4 + i * rec
            if u16(d, at) != i: return None
            keys.append(d[at + 0xF5:at + 0xF5 + 40].split(b'\0')[0].decode('latin-1'))
        return keys if keys[2] == 'Blood Moor' else None

    def level_name(self, level):
        if not self.levels or not 0 <= level < len(self.levels) or not self.levels[level]: return None
        return self.text(self.levels[level]) or self.levels[level]

    def read_skills(self, skills, descs):
        count = s32(skills, 0) if skills and len(skills) > 4 else 0
        dcount = s32(descs, 0) if descs and len(descs) > 4 else 0
        self.skill_class, self.skill_cel, self.skill_name, self.skill_short = [-1] * count, [-1] * count, [None] * count, [None] * count
        self.passive = None
        if count and count * 572 + 4 == len(skills) and count > 37:
            p = [s32(skills, 4 + i * 572 + 4) & 0x10 != 0 for i in range(count)]
            self.passive = p if p[37] and not p[36] else None  # Warmth passive, Fire Bolt not: the table is what we think
        self.state_skills = None
        if count and skills:
            n = u16(skills, 0)
            size = (len(skills) - 4) // n if n else 0
            if size >= 0x84:
                own, target = [-1] * 256, [-1] * 256
                pal = lambda i: skills[4 + i * size + 0x0C] == 3
                for i in range(n):
                    at = 4 + i * size
                    a, b = u16(skills, at + 0x80), u16(skills, at + 0x82)
                    if a < 256 and (own[a] < 0 or pal(i) and not pal(own[a])): own[a] = i
                    if b < 256 and (target[b] < 0 or pal(i) and not pal(target[b])): target[b] = i
                self.state_skills = (own, target)
        if not count or not dcount: return
        size, dsize = (len(skills) - 4) // count, (len(descs) - 4) // dcount
        for i in range(count):
            at = 4 + i * size
            self.skill_class[i] = struct.unpack_from('b', skills, at + 0x0C)[0]
            desc = u16(skills, at + 0x194)
            if desc < dcount:
                at2 = 4 + desc * dsize
                self.skill_cel[i] = descs[at2 + 7]
                self.skill_name[i] = self.strings.get(u16(descs, at2 + 8))
                self.skill_short[i] = self.strings.get(u16(descs, at2 + 10))

    def skill_icon(self, sid):
        if not 0 <= sid < len(self.skill_class): return None
        cls, cel = self.skill_class[sid], self.skill_cel[sid]
        icons = self.icons[cls if 0 <= cls < 7 else 7]
        return icons[cel] if icons and 0 <= cel < len(icons) else None

    def skill_passive(self, sid):
        return -1 if self.passive is None or not 0 <= sid < len(self.passive) else int(self.passive[sid])

    def picture(self, code, quality, done):
        """The inventory picture of an item, or None while it loads (done() runs once it is there)."""
        files = self.inv_files.get(code)
        if not files: return None
        name = files[1] if quality == 7 and files[1] else files[2] if quality == 5 and files[2] else files[0]
        if not name: return None
        with self.lock:
            if name in self.pictures: return self.pictures[name]
            self.pictures[name] = None
            self.wanted.append((name, done))
            if not self.loader or not self.loader.is_alive():
                self.loader = threading.Thread(target=self.load_pictures, daemon=True)
                self.loader.start()
        return None

    def load_pictures(self):
        while True:
            with self.lock:
                if not self.wanted: return
                name, done = self.wanted.pop(0)
            try:
                f = self.s.dc6(f'data\\global\\items\\{name}.dc6')
                img = image(f[0]) if f else None
            except (OSError, ValueError, struct.error): img = None
            with self.lock: self.pictures[name] = img
            if img is not None: done()
