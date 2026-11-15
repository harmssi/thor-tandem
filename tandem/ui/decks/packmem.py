"""The running game's memory for companion packs, read through RetroArch's network commands (UDP 127.0.0.1:55355).

RetroArch answers one command per emulated frame (about 21 ms), however much it returns. So single bytes are never asked
for: memory is fetched in whole pages, neighbouring pages in one request, and the pages a pack used lately are fetched
together before its next update() runs. A page is read once per tick at most; ROM pages are kept. Read only: there is
no WRITE_CORE_MEMORY in here.
"""
import socket, struct, time, zlib
from collections import OrderedDict

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter


class Memory:
    def __init__(self, system, addr=('127.0.0.1', 55355), timeout=0.3):
        self.gba, self.addr, self.timeout = system == 'gba', addr, timeout
        self.page, self.span_max = (4096, 16384) if self.gba else (256, 4096)  # the cores' limits, measured on the Thor
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rom, self.live, self.hot, self.gaps, self.edges = OrderedDict(), {}, {}, {}, set()
        self.tick, self.offline, self.requests = 0, False, 0

    def close(self): self.sock.close()

    def ask(self, text, prefix):
        """One command, one answer (None: nobody answered – then this tick asks no more)."""
        self.requests += 1
        try:
            self.sock.sendto(text.encode(), self.addr)
            end = time.monotonic() + self.timeout
            while True:
                self.sock.settimeout(max(0.01, end - time.monotonic()))
                data = self.sock.recv(65536)
                if data.startswith(prefix): return data
                if time.monotonic() > end: raise socket.timeout  # only late answers to older questions arrived
        except OSError:
            self.offline = True
            return None

    def status(self):
        """GET_STATUS -> {'state', 'system', 'title', 'crc32'} or None."""
        reply = self.ask('GET_STATUS', b'GET_STATUS')
        self.offline = False
        if not reply: return None
        state, _, rest = reply.decode('utf-8', 'replace').strip()[11:].partition(' ')
        system, _, rest = rest.partition(',')
        title, _, crc = rest.rpartition(',crc32=')
        return {'state': state, 'system': system, 'title': title, 'crc32': crc.strip().lower()}

    def fetch(self, command, addr, n):
        reply = self.ask(f'{command} {addr:x} {n}', f'{command} {addr:x} '.encode())
        if reply is None: return None
        body = reply.split(None, 2)[2:]
        if not body or body[0].startswith(b'-1'): return b''  # no memory there
        try: return bytes.fromhex(body[0].decode())[:n]
        except ValueError: return b''

    def is_rom(self, page): return 0x08000000 <= page < 0x0E000000 if self.gba else page < 0x4000  # GB: bank 0 only

    def span(self, start, end):
        """The bytes from start to end, with as few requests as the memory's layout allows; None: no answer.
        RetroArch answers up to the end of one piece of memory (Game Boy: 0xC000-0xCFFF, 0xD000-0xDFFF, I/O, high RAM …):
        a short answer marks an edge, and from then on that place is asked for piece by piece. Where there is nothing
        at all (cartridge RAM with Gambatte), zeros stand in and the place is left alone for a while."""
        buf, at, P = bytearray(), start, self.page
        while at < end:
            gap = self.gaps.get(at)
            if gap and gap[1] >= self.tick:
                buf += bytes(gap[0] - at); at = gap[0]
                continue
            stop = min([end] + [e for e in self.edges if at < e < end] + [g for g, (_, until) in self.gaps.items() if at < g < end and until >= self.tick])
            data = self.fetch('READ_CORE_MEMORY', at, stop - at)
            if data is None: return None
            if not data:
                nxt = min(stop, at // P * P + P)
                self.gaps[at], data = (nxt, self.tick + 40), bytes(nxt - at)
            elif len(data) < stop - at: self.edges.add(at + len(data))
            buf += data; at += len(data)
        return bytes(buf[:end - start])

    def load(self, pages):
        """Fetches whole pages: neighbours travel in one request (GBA: also near neighbours – a hole in between costs
        less than a second request)."""
        P, runs = self.page, []
        for p in sorted(pages):
            if runs and p + P - runs[-1][0] <= self.span_max and p - runs[-1][1] <= (3 * P if self.gba and p >> 24 == runs[-1][0] >> 24 else 0): runs[-1][1] = p + P
            else: runs.append([p, p + P])
        for start, end in runs:
            data = self.span(start, end)
            if data is None: return
            for off in range(0, len(data), P): self.put(start + off, data[off:off + P])

    def put(self, page, data):
        if len(data) < self.page: data += bytes(self.page - len(data))
        if not self.is_rom(page): self.live[page] = data
        else:
            self.rom[page] = data
            while len(self.rom) > 384: self.rom.popitem(last=False)

    def begin(self):
        """A new tick: what the pack used lately is fetched again in one go. False: the emulator does not answer."""
        self.tick, self.offline, self.live = self.tick + 1, False, {}
        self.hot = {p: t for p, t in self.hot.items() if t >= self.tick - 4}
        self.load(self.hot)
        return not self.offline

    def read(self, addr, n):
        """n bytes from the bus address, or None when the emulator does not answer."""
        if self.offline: return None
        addr &= 0xFFFFFFFF
        P = self.page
        first = addr - addr % P
        pages = range(first, addr + n, P)
        need = [p for p in pages if p not in self.live and p not in self.rom]
        if need:
            self.load(need)
            if self.offline: return None
        out = []
        for p in pages:
            data = self.live.get(p)
            if data is None:
                data = self.rom.get(p)
                if data is None: return None
            else: self.hot[p] = self.tick
            out.append(data)
        blob = out[0] if len(out) == 1 else b''.join(out)
        return blob[addr - first:addr - first + n]

    def u(self, addr, n):
        data = self.read(addr, n)
        return None if data is None else int.from_bytes(data, 'little')

    def bank8(self, bank, addr):
        """GB/GBC: a byte from a given bank of work RAM (0xD000-0xDFFF), whatever bank the game has mapped right now.
        Gambatte's memory map is fixed: 0xD000 is always bank 1, and a Game Boy Color's banks 2-7 follow from 0x10000."""
        addr &= 0xFFFF
        if 0xD000 <= addr < 0xE000 and bank & 7 >= 2: addr = 0x10000 + ((bank & 7) - 2) * 0x1000 + addr - 0xD000
        return self.u(addr, 1)


class Gfx:
    """gfx.* of the pack API: pictures decoded from the game's memory, kept as QImage under a 'gfx:…' key."""
    LIMIT, PIXELS = 96, 4 * 1024 * 1024

    def __init__(self, mem): self.mem, self.images = mem, OrderedDict()

    def image(self, key): return self.images.get(key)

    def need(self, addr, n):
        data = self.mem.read(addr, n)
        if data is None: raise OSError('the emulator is not answering')
        return data

    def store(self, key, w, h, data, fmt=QImage.Format.Format_ARGB32):
        image = data if isinstance(data, QImage) else QImage(bytes(data), w, h, w * 4, fmt).copy()
        images = dict(self.images)  # the window reads this from its own thread: swap, never change in place
        images[key] = image
        while len(images) > self.LIMIT or sum(i.width() * i.height() for i in images.values()) > self.PIXELS: del images[next(iter(images))]
        self.images = images
        return key

    def key(self, *parts): return 'gfx:%08x' % zlib.crc32(repr(parts).encode())

    def palette(self, addr, banks=16):
        """BGR555 colours as the four bytes of an ARGB32 pixel."""
        return [bytes(((v >> 7) & 0xF8, (v >> 2) & 0xF8, (v << 3) & 0xF8, 255)) for v in struct.unpack(f'<{banks * 16}H', self.need(addr, banks * 32))]

    def lz77(self, addr):
        """GBA BIOS type 0x10 data at addr, unpacked."""
        head = self.need(addr, 4)
        size = int.from_bytes(head[1:4], 'little')
        if head[0] != 0x10 or size > 1024 * 1024: raise ValueError('no valid LZ77 data at 0x%08x' % addr)
        out, buf, pos, at = bytearray(), b'', 0, addr + 4
        def more():
            nonlocal buf, pos, at
            buf, pos, at = buf[pos:] + self.need(at, 4096), 0, at + 4096
        while len(out) < size:
            if pos + 17 > len(buf): more()  # one flag byte and up to eight two-byte tokens
            flags, pos = buf[pos], pos + 1
            for bit in (128, 64, 32, 16, 8, 4, 2, 1):
                if len(out) >= size: break
                if not flags & bit: out.append(buf[pos]); pos += 1
                else:
                    b0, b1, pos = buf[pos], buf[pos + 1], pos + 2
                    disp = ((b0 & 15) << 8 | b1) + 1
                    if disp > len(out): raise ValueError('no valid LZ77 data at 0x%08x' % addr)
                    for _ in range(min((b0 >> 4) + 3, size - len(out))): out.append(out[-disp])
        return bytes(out)

    @staticmethod
    def ints(t, names, default=None):
        out = []
        for name in names:
            v = t.get(name, default)
            if isinstance(v, float) and v == int(v): v = int(v)
            if not isinstance(v, int) or isinstance(v, bool): raise ValueError(f"field '{name}' must be an integer")
            out.append(v)
        return out

    @staticmethod
    def tile(data, at, pal, opaque=False):
        """An 8x8 4bpp tile as 8 rows of 8 pixels (4 bytes each); colour 0 is clear unless opaque."""
        rows, clear = [], bytes(4)
        for y in range(8):
            px = []
            for v in data[at + y * 4:at + y * 4 + 4].ljust(4, b'\0'):
                lo, hi = v & 15, v >> 4
                px.append(pal[lo] if lo or opaque else clear)
                px.append(pal[hi] if hi or opaque else clear)
            rows.append(px)
        return rows

    def decode(self, t):
        tiles, palette, w, h = self.ints(t, ('tiles', 'palette', 'width', 'height'))
        if t.get('bpp', 4) != 4: raise ValueError('only bpp=4 is supported')
        if w <= 0 or h <= 0 or w % 8 or h % 8 or w > 256 or h > 256: raise ValueError('width/height must be positive multiples of 8, at most 256')
        key = self.key('decode', tiles, palette, w, h, bool(t.get('lz77')))
        if key in self.images: return key
        data = self.lz77(tiles) if t.get('lz77') else self.need(tiles, w // 8 * (h // 8) * 32)
        pal, lines = self.palette(palette, 1), [[] for _ in range(h)]
        for n in range(w // 8 * (h // 8)):
            for y, row in enumerate(self.tile(data, n * 32, pal)): lines[n // (w // 8) * 8 + y].extend(row)
        return self.store(key, w, h, b''.join(b''.join(line) for line in lines))

    def tilemap(self, t):
        tiles, palette, at, w, h = self.ints(t, ('tiles', 'palette', 'map', 'width', 'height'))
        stride, = self.ints(t, ('stride',), 32)
        x0, y0 = self.ints(t, ('x', 'y'), 0)
        opaque, packed = bool(t.get('opaque')), bool(t.get('lz77'))
        if w <= 0 or h <= 0 or w % 8 or h % 8 or w > 256 or h > 256: raise ValueError('width/height must be positive multiples of 8, at most 256')
        if not 1 <= stride <= 256: raise ValueError('stride must be 1 to 256')
        if x0 < 0 or y0 < 0 or x0 + w // 8 > stride or y0 > 4096: raise ValueError('x/y outside the map')
        key = self.key('tilemap', tiles, palette, at, stride, x0, y0, w, h, opaque, packed)
        if key in self.images: return key
        cells = (y0 + h // 8) * stride
        if packed:
            tile_data, map_data = self.lz77(tiles), self.lz77(at)
            if cells * 2 > len(map_data): raise ValueError('x/y outside the map')
        else: tile_data, map_data = None, self.need(at, cells * 2)
        entries = struct.unpack_from(f'<{cells}H', map_data)
        if tile_data is None:  # raw: only the tiles the map names, in one read
            used = [entries[(y0 + ty) * stride + x0 + tx] & 0x3FF for ty in range(h // 8) for tx in range(w // 8)]
            base = min(used) * 32
            tile_data = bytes(base) + self.need(tiles + base, (max(used) + 1) * 32 - base)
        pal, lines, done = self.palette(palette), [[] for _ in range(h)], {}
        for ty in range(h // 8):
            for tx in range(w // 8):
                entry = entries[(y0 + ty) * stride + x0 + tx]
                rows = done.get(entry)
                if rows is None:
                    rows = self.tile(tile_data, (entry & 0x3FF) * 32, pal[(entry >> 12) * 16:(entry >> 12) * 16 + 16], opaque)
                    if entry & 0x400: rows = [row[::-1] for row in rows]
                    if entry & 0x800: rows = rows[::-1]
                    done[entry] = rows = [b''.join(row) for row in rows]
                for y in range(8): lines[ty * 8 + y].append(rows[y])
        return self.store(key, w, h, b''.join(b''.join(line) for line in lines))

    def sprite(self, t):
        tiles, palette, w, h = self.ints(t, ('tiles', 'palette', 'width', 'height'))
        parts = t.get('parts')
        if not 0 < w <= 256 or not 0 < h <= 256: raise ValueError('width/height must be 1 to 256')
        if not isinstance(parts, list) or not 1 <= len(parts) <= 32: raise ValueError('1 to 32 parts')
        todo = []
        for n, part in enumerate(parts):
            if not isinstance(part, dict): raise ValueError(f'part {n + 1} must be a table')
            x, y = self.ints(part, ('x', 'y'), 0)
            pw, ph, tile, bank = self.ints(part, ('w', 'h', 'tile', 'bank'))
            if pw not in (8, 16, 32, 64) or ph not in (8, 16, 32, 64) or not 0 <= tile <= 0xFFFF or not 0 <= bank <= 15 or not -64 <= x <= 256 or not -64 <= y <= 256:
                raise ValueError(f'part {n + 1} is invalid (w/h 8-64, tile 0-65535, bank 0-15)')
            todo.append((x, y, pw, ph, tile, bank, bool(part.get('hflip')), bool(part.get('vflip'))))
        key = self.key('sprite', tiles, palette, w, h, todo)
        if key in self.images: return key
        out, clear = [[bytes(4)] * w for _ in range(h)], bytes(4)
        for x, y, pw, ph, tile, bank, hflip, vflip in todo:
            pal, data = self.palette(palette + bank * 32, 1), self.need(tiles + tile * 32, pw // 8 * (ph // 8) * 32)
            for n in range(pw // 8 * (ph // 8)):
                for ry, row in enumerate(self.tile(data, n * 32, pal)):
                    for rx, px in enumerate(row):
                        sx, sy = n % (pw // 8) * 8 + rx, n // (pw // 8) * 8 + ry
                        dx, dy = x + (pw - 1 - sx if hflip else sx), y + (ph - 1 - sy if vflip else sy)
                        if px != clear and 0 <= dx < w and 0 <= dy < h and out[dy][dx] == clear: out[dy][dx] = px  # an earlier part stays on top
        return self.store(key, w, h, b''.join(b''.join(row) for row in out))

    def layers(self, t):
        """A picture of the game's live map (the layers a game.lua wide() describes), see wide.c wide_render."""
        w, h = self.ints(t, ('width', 'height'))
        scale, = self.ints(t, ('scale',), 1)
        x0, y0, palette = self.ints(t, ('x', 'y', 'palette'))
        layers = t.get('layers')
        if not 0 < w <= 512 or not 0 < h <= 512: raise ValueError('width/height must be 1 to 512')
        if not 1 <= scale <= 8: raise ValueError('scale must be 1 to 8')
        if not isinstance(layers, list) or not 1 <= len(layers) <= 3 or not all(isinstance(l, dict) for l in layers): raise ValueError("field 'layers' needs 1 to 3 tables")
        table = []
        for v in struct.unpack('<256H', self.need(palette, 512)):  # black reads as "outside", as in the app
            c = (v & 0x1F) << 19 | (v >> 5 & 0x1F) << 11 | (v >> 10 & 0x1F) << 3
            table.append(0xFF000000 | c | c >> 5 & 0x070707 if c else 0)
        canvas = QImage(w, h, QImage.Format.Format_ARGB32)
        canvas.fill(0)
        painter, stride = QPainter(canvas), (w + 3) & ~3
        try:
            for layer in layers:
                grid, cols, gw, gh, mask, meta, tiles = self.ints(layer, ('grid', 'stride', 'gridW', 'gridH', 'idMask', 'metatiles', 'tiles'))
                size, = self.ints(layer, ('cellBytes',), 2)
                special, plain = self.ints(layer, ('special', 'tileCells'), 0)
                if size not in (2, 4) or not 1 <= gw <= 1024 or not 1 <= gh <= 1024 or cols < gw: raise ValueError("the layers' grid sizes are out of range")
                unit = 8 if plain else 16
                # the picture's rows and columns as world pixels, and the part of them inside this layer's grid
                xs = [x0 + c * scale + scale // 2 for c in range(w)]
                ys = [y0 + r * scale + scale // 2 for r in range(h)]
                inside_x = [c for c, wx in enumerate(xs) if 0 <= wx < gw * unit]
                inside_y = [r for r, wy in enumerate(ys) if 0 <= wy < gh * unit]
                if not inside_x or not inside_y: continue
                c0, c1 = xs[inside_x[0]] // unit, xs[inside_x[-1]] // unit
                if table[0]: painter.fillRect(QRect(inside_x[0], inside_y[0], len(inside_x), len(inside_y)), QColor.fromRgba(table[0]))
                tile_data, done, rows_of, lines = self.need(tiles, 0x400 * 32), {}, {}, []
                metas = self.need(meta, (mask + 1) * 8) if not plain and mask <= 0x1FFF else None  # the whole table in one read
                def strip(entry, ty):  # one row of a tile as palette numbers; 0 = clear
                    rows = done.get(entry)
                    if rows is None:
                        at, bank, rows = (entry & 0x3FF) * 32, entry >> 8 & 0xF0, []
                        for y in range(8):
                            px = []
                            for v in tile_data[at + y * 4:at + y * 4 + 4]:
                                px.append(bank | v & 15 if v & 15 else 0); px.append(bank | v >> 4 if v >> 4 else 0)
                            rows.append(bytes(px[::-1] if entry & 0x400 else px))
                        done[entry] = rows = rows[::-1] if entry & 0x800 else rows
                    return rows[ty]
                pick = [xs[c] - c0 * unit for c in inside_x]
                for r in range(h):
                    wy = ys[r]
                    if not 0 <= wy < gh * unit: lines.append(bytes(stride)); continue
                    cy, py = wy // unit, wy % unit
                    line = rows_of.get((cy, py))
                    if line is None:
                        cells = self.need(grid + (cy * cols + c0) * size, (c1 - c0 + 1) * size)
                        ids, full = struct.unpack(f'<{c1 - c0 + 1}{"I" if size == 4 else "H"}', cells), []
                        for cell in ids:
                            if plain: full.append(strip(cell & 0xFFFF, py)); continue
                            if size == 2 and cell >= 0x4000 and special: cell = self.mem.u(special + (cell - 0x4000) * 2, 2) or 0
                            at = (cell & mask) * 8 + (py >> 3) * 4
                            a, b = struct.unpack_from('<2H', metas, at) if metas else struct.unpack('<2H', self.need(meta + at, 4))
                            full.append(strip(a, py & 7)); full.append(strip(b, py & 7))
                        full = b''.join(full)
                        rows_of[(cy, py)] = line = bytes(inside_x[0]) + bytes(full[p] for p in pick)
                    lines.append(line.ljust(stride, b'\0')[:stride])
                image = QImage(b''.join(lines), w, h, stride, QImage.Format.Format_Indexed8)
                image.setColorTable([0 if not n & 15 else c for n, c in enumerate(table)])
                painter.drawImage(0, 0, image)
        finally: painter.end()
        return self.store('gfx:%08x' % (zlib.crc32(bytes(canvas.constBits())) ^ (w << 16 | h) ^ 0x1a7e55), w, h, canvas)

    def call(self, kind, text):
        import json
        return getattr(self, kind)(json.loads(text))
