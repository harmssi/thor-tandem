"""Universal game companion back-end for Toravo Tandem:
- Per-game notes, checklists & finger-sketch PNG storage
- Per-game offline guides/maps & Wikipedia lore/walkthrough fetcher
- Visual emulator save-state discovery (with screenshot thumbnails)
- Dual-screen secondary window configuration & X11 touch forwarding (melonDS, Azahar, Cemu)
- Virtual uinput relative trackpad/mouse (for Moonlight / PC streaming)
- Streaming wireless ROM / guide / companion-pack upload handler
Standard library + libX11 ctypes + /dev/uinput only."""
import ctypes, glob, json, os, re, shutil, struct, subprocess, sys, threading, time, urllib.parse, urllib.request, zipfile
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'tandem'

SAFE_ID = re.compile(r'^[A-Za-z0-9_\-]{2,64}$')
GUIDE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.txt', '.md'}

# Extension -> default ES-DE ROM folder when uploading with system='auto'
EXT_SYSTEM = {
    '.gb': 'gb', '.sgb': 'gb', '.gbc': 'gbc', '.gba': 'gba',
    '.nes': 'nes', '.unf': 'nes', '.fds': 'fds',
    '.sfc': 'snes', '.smc': 'snes', '.z64': 'n64', '.n64': 'n64', '.v64': 'n64',
    '.nds': 'nds', '.3ds': 'n3ds', '.3dsx': 'n3ds', '.cci': 'n3ds', '.cia': 'n3ds',
    '.gcm': 'gc', '.rvz': 'gc', '.wbfs': 'wii', '.wua': 'wiiu', '.wux': 'wiiu', '.rpx': 'wiiu',
    '.pbp': 'psx', '.cso': 'psp', '.zso': 'ps2', '.gdi': 'dreamcast', '.cdi': 'dreamcast',
    '.md': 'megadrive', '.gen': 'megadrive', '.smd': 'megadrive', '.32x': 'sega32x',
    '.sms': 'mastersystem', '.gg': 'gamegear', '.pce': 'pcengine', '.sgx': 'supergrafx',
    '.a26': 'atari2600', '.a52': 'atari5200', '.a78': 'atari7800', '.lnx': 'atarilynx', '.j64': 'atarijaguar',
    '.ws': 'wonderswan', '.wsc': 'wonderswancolor', '.ngp': 'ngp', '.ngc': 'ngpc', '.vb': 'virtualboy',
    '.adf': 'amiga', '.d64': 'c64', '.prg': 'c64', '.tzx': 'zxspectrum', '.tap': 'zxspectrum',
    '.dsk': 'amstradcpc', '.mx1': 'msx', '.mx2': 'msx2', '.p8': 'pico8', '.min': 'pokemini',
    '.col': 'colecovision', '.int': 'intellivision', '.vec': 'vectrex',
    '.nsp': 'switch', '.xci': 'switch', '.nsz': 'switch',
}


def _notes_dir():
    d = STATE / 'notes'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _guides_dir(gid):
    d = DATA_DIR / 'guides' / gid
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---- Per-game notes, checklists & finger sketch ----------------------------------------------------------------------
def notes_get(gid):
    if not SAFE_ID.fullmatch(str(gid or '')): return {'error': 'ungültige ID'}
    d = _notes_dir()
    jfile, pfile = d / f'{gid}.json', d / f'{gid}.png'
    try: data = json.loads(jfile.read_text(encoding='utf-8'))
    except (OSError, ValueError): data = {}
    checks = [c for c in (data.get('checks') or []) if isinstance(c, dict) and isinstance(c.get('t'), str)]
    return {'gid': gid, 'text': str(data.get('text') or ''), 'checks': checks[:60],
            'has_sketch': pfile.is_file(), 'sketch_mtime': int(pfile.stat().st_mtime) if pfile.is_file() else 0}


def notes_save(gid, payload):
    if not SAFE_ID.fullmatch(str(gid or '')): return {'error': 'ungültige ID'}
    cur = notes_get(gid)
    text = str(payload.get('text', cur['text']))[:8000]
    checks = cur['checks']
    if isinstance(payload.get('checks'), list):
        checks = [{'t': str(c.get('t', '')).strip()[:160], 'done': bool(c.get('done'))}
                  for c in payload['checks'] if isinstance(c, dict) and str(c.get('t', '')).strip()][:60]
    if isinstance(payload.get('add_check'), str) and payload['add_check'].strip():
        checks.append({'t': payload['add_check'].strip()[:160], 'done': False})
    if isinstance(payload.get('toggle_idx'), int) and 0 <= payload['toggle_idx'] < len(checks):
        checks[payload['toggle_idx']]['done'] = not checks[payload['toggle_idx']]['done']
    if isinstance(payload.get('del_idx'), int) and 0 <= payload['del_idx'] < len(checks):
        checks.pop(payload['del_idx'])
    jfile = _notes_dir() / f'{gid}.json'
    tmp = jfile.with_suffix('.tmp')
    tmp.write_text(json.dumps({'text': text, 'checks': checks}, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, jfile)
    return notes_get(gid)


def sketch_bytes(gid):
    if not SAFE_ID.fullmatch(str(gid or '')): return None
    pfile = _notes_dir() / f'{gid}.png'
    return pfile.read_bytes() if pfile.is_file() else None


def sketch_save(gid, png_bytes):
    if not SAFE_ID.fullmatch(str(gid or '')): return {'error': 'ungültige ID'}
    pfile = _notes_dir() / f'{gid}.png'
    if not png_bytes:
        pfile.unlink(missing_ok=True)
        return {'ok': True, 'has_sketch': False}
    if len(png_bytes) > (4 << 20) or not png_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return {'error': 'Ungültiges PNG-Bild.'}
    tmp = pfile.with_suffix('.tmp')
    tmp.write_bytes(png_bytes)
    os.replace(tmp, pfile)
    return {'ok': True, 'has_sketch': True, 'sketch_mtime': int(pfile.stat().st_mtime)}


# ---- Per-game Guides, Maps & Web Wiki Reader -------------------------------------------------------------------------
def guides_list(gid, game=None):
    if not SAFE_ID.fullmatch(str(gid or '')): return {'items': []}
    items, seen = [], set()
    folders = [_guides_dir(gid)]
    if game and game.get('path'):
        rom = Path(game['path'])
        gdir = rom.parent / 'guides'
        if gdir.is_dir():
            for f in sorted(gdir.iterdir()):
                if f.is_file() and f.suffix.lower() in GUIDE_EXTS and f.stem.lower().startswith(rom.stem.lower()):
                    seen.add(str(f))
                    items.append({'name': f.name, 'title': f.stem.replace('_', ' '),
                                  'kind': 'image' if f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'} else 'text',
                                  'src': 'rom', 'size': f.stat().st_size})
    for folder in folders:
        if not folder.is_dir(): continue
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.suffix.lower() not in GUIDE_EXTS or str(f) in seen: continue
            items.append({'name': f.name, 'title': f.stem.replace('_', ' '),
                          'kind': 'image' if f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'} else 'text',
                          'src': 'local', 'size': f.stat().st_size})
    return {'gid': gid, 'items': items}


def guide_file(gid, name, game=None):
    if not SAFE_ID.fullmatch(str(gid or '')): return None
    safe = os.path.basename(str(name or ''))
    if not safe or Path(safe).suffix.lower() not in GUIDE_EXTS: return None
    cand = [_guides_dir(gid) / safe]
    if game and game.get('path'):
        cand.append(Path(game['path']).parent / 'guides' / safe)
    return next((p for p in cand if p.is_file()), None)


def guide_fetch_wiki(gid, query, lang='de'):
    """Fetch clean plain-text game overview, mechanics & lore from Wikipedia (DE fallback EN) and save offline in guides/<gid>/."""
    if not SAFE_ID.fullmatch(str(gid or '')): return {'error': 'ungültige ID'}
    q = str(query or '').strip()[:100]
    if not q: return {'error': 'Bitte Suchbegriff eingeben.'}
    langs = ('de', 'en') if lang != 'en' else ('en', 'de')
    for lg in langs:
        try:
            s_url = (f'https://{lg}.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch='
                     + urllib.parse.quote(f'{q} video game' if lg == 'en' else f'{q} Spiel'))
            req = urllib.request.Request(s_url, headers={'User-Agent': 'Tandem/0.4 (AYN Thor Companion)'})
            hits = (json.loads(urllib.request.urlopen(req, timeout=10).read()).get('query') or {}).get('search') or []
            if not hits:
                s_url2 = f'https://{lg}.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch=' + urllib.parse.quote(q)
                hits = (json.loads(urllib.request.urlopen(urllib.request.Request(s_url2, headers={'User-Agent': 'Tandem/0.4'}), timeout=10).read()).get('query') or {}).get('search') or []
            if not hits: continue
            title = hits[0]['title']
            e_url = (f'https://{lg}.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&format=json&titles='
                     + urllib.parse.quote(title))
            pages = ((json.loads(urllib.request.urlopen(urllib.request.Request(e_url, headers={'User-Agent': 'Tandem/0.4'}), timeout=10).read()).get('query') or {}).get('pages')) or {}
            page = next(iter(pages.values()), {})
            extract = (page.get('extract') or '').strip()
            if len(extract) < 80: continue
            safe_stem = re.sub(r'[^A-Za-z0-9ÄÖÜäöüß _\-]', '', title).strip()[:60] or 'Wiki'
            out_file = _guides_dir(gid) / f'{safe_stem} ({lg.upper()}).txt'
            out_file.write_text(f'{title}\n{"=" * len(title)}\n\n{extract}\n', encoding='utf-8')
            return {'ok': True, 'saved': out_file.name, 'title': title, **guides_list(gid)}
        except (OSError, ValueError):
            continue
    return {'error': f'Kein Artikel zu „{q}“ gefunden.'}


# ---- Visual Emulator Save-States -------------------------------------------------------------------------------------
def savestates_list(game, run, home=None):
    """Discover real save-state files + screenshot thumbnails for the running game."""
    if not game or not run: return {'slots': [], 'emu': ''}
    h = Path(home) if home else HOME
    emu = run.get('emu') or ''
    stem = Path(game['path']).stem if game.get('path') else ''
    slots = []
    if emu == 'RetroArch' and stem:
        states_root = h / '.var/app/org.libretro.RetroArch/config/retroarch/states'
        if not states_root.is_dir(): states_root = h / '.config/retroarch/states'
        candidates = list(states_root.glob(f'**/{glob.escape(stem)}.state*')) if states_root.is_dir() else []
        by_slot = {}
        for p in candidates:
            if p.suffix == '.png' or p.name.endswith('.bak'): continue
            suf = p.name[len(stem) + 6:]  # after '.state'
            if suf == '.auto': slot, lbl = -1, 'Auto-Speicherstand'
            elif suf == '': slot, lbl = 0, 'Slot 0 (Standard)'
            elif suf.isdigit(): slot, lbl = int(suf), f'Slot {suf}'
            else: continue
            png = Path(str(p) + '.png')
            st = p.stat()
            if slot not in by_slot or st.st_mtime > by_slot[slot]['mtime']:
                by_slot[slot] = {'slot': slot, 'label': lbl, 'mtime': int(st.st_mtime), 'size': st.st_size,
                                 'thumb': str(png) if png.is_file() else None}
        for s in (0, 1, 2, 3, 4, 5):
            if s in by_slot: slots.append(by_slot[s])
            else: slots.append({'slot': s, 'label': f'Slot {s}' + (' (Standard)' if s == 0 else ''), 'mtime': 0, 'size': 0, 'thumb': None})
        if -1 in by_slot: slots.insert(0, by_slot[-1])
    elif emu == 'DuckStation':
        sdir = h / '.local/share/duckstation/savestates'
        for p in sorted(sdir.glob('*.sav'), key=lambda x: -x.stat().st_mtime)[:12] if sdir.is_dir() else ():
            m = re.search(r'_(\d+)\.sav$', p.name)
            slot = int(m[1]) if m else 1
            png = p.with_suffix('.png')
            slots.append({'slot': slot, 'label': f'{p.stem}', 'mtime': int(p.stat().st_mtime), 'size': p.stat().st_size,
                          'thumb': str(png) if png.is_file() else None})
    elif emu == 'PPSSPP':
        sdir = h / '.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/PPSSPP_STATE'
        for p in sorted(sdir.glob('*.ppst'), key=lambda x: -x.stat().st_mtime)[:12] if sdir.is_dir() else ():
            jpg = p.with_suffix('.jpg')
            slots.append({'slot': 0, 'label': p.stem, 'mtime': int(p.stat().st_mtime), 'size': p.stat().st_size,
                          'thumb': str(jpg) if jpg.is_file() else None})
    elif emu == 'ARMSX2':
        sdir = h / '.config/ARMSX2/sstates'
        for p in sorted(sdir.glob('*.p2s'), key=lambda x: -x.stat().st_mtime)[:12] if sdir.is_dir() else ():
            slots.append({'slot': 0, 'label': p.stem, 'mtime': int(p.stat().st_mtime), 'size': p.stat().st_size, 'thumb': None})
    return {'emu': emu, 'slots': slots}


# ---- Dual-screen emulator configuration & X11 window touch bridge (DS, 3DS, Wii U) -----------------------------------
def ensure_retroarch_thumbnails(home=None):
    """Enable RetroArch savestate_thumbnail_enable so visual save-state cards get automatic PNG previews."""
    h = Path(home) if home else HOME
    cfg = h / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg'
    if not cfg.is_file(): return
    try:
        txt = cfg.read_text(errors='surrogateescape')
        if 'savestate_thumbnail_enable = "true"' in txt: return
        if 'savestate_thumbnail_enable' in txt:
            txt = re.sub(r'(?m)^savestate_thumbnail_enable\s*=.*$', 'savestate_thumbnail_enable = "true"', txt)
        else:
            txt = txt.rstrip('\n') + '\nsavestate_thumbnail_enable = "true"\n'
        cfg.write_text(txt, errors='surrogateescape')
    except OSError: pass


def setup_dual_emu(system, label, home=None):
    """Configure melonDS (DS) or Azahar (3DS) to open a separate bottom touch-screen window on :0 for Dual-Screen mode."""
    h = Path(home) if home else HOME
    if system == 'nds' and label == 'melonDS':
        cfg = h / '.config/melonDS/melonDS.toml'
        if not cfg.parent.is_dir(): return
        try: txt = cfg.read_text(errors='surrogateescape') if cfg.is_file() else ''
        except OSError: return
        if cfg.is_file() and not cfg.with_name('melonDS.toml.bak-tandem').exists():
            shutil.copy2(cfg, cfg.with_name('melonDS.toml.bak-tandem'))
        import controls
        # Window0: Top Only (ScreenSizing = 4), Window1: Bottom Only (ScreenSizing = 5, Enabled = true)
        for sec, pairs in (('Instance0.Window0', {'Enabled': 'true', 'ScreenSizing': '4'}),
                           ('Instance0.Window1', {'Enabled': 'true', 'ScreenSizing': '5'})):
            for k, v in pairs.items():
                txt = controls._set(txt, sec, k, v, ' = ')
        try: cfg.write_text(txt, errors='surrogateescape')
        except OSError: pass
    elif system == 'n3ds' and label == 'Azahar':
        cfg = h / '.config/azahar-emu/qt-config.ini'
        if not cfg.is_file(): return
        import controls
        try: txt = cfg.read_text(errors='surrogateescape')
        except OSError: return
        if not cfg.with_name('qt-config.ini.bak-tandem').exists():
            shutil.copy2(cfg, cfg.with_name('qt-config.ini.bak-tandem'))
        for sec, pairs in (('Layout', {'layout_option': '5', 'layout_option\\default': 'false'}),
                           ('UI', {'singleWindowMode': 'false', 'singleWindowMode\\default': 'false'})):
            for k, v in pairs.items():
                txt = controls._set(txt, sec, k, v, '=')
        try: cfg.write_text(txt, errors='surrogateescape')
        except OSError: pass


def _run_q(cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError): return ''


def find_secondary_window(system=''):
    """Find the X11 window ID of the secondary touch screen (Cemu GamePad View, Azahar Secondary Window, melonDS Window 2)."""
    env_disp = os.environ.get('DISPLAY') or ':0'
    out = _run_q(['xwininfo', '-display', env_disp, '-root', '-tree'])
    candidates = []
    for line in out.splitlines():
        m = re.match(r'^\s+(0x[0-9a-fA-F]+)\s+"([^"]*)".*?(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', line)
        if not m: continue
        wid, title, w, h = int(m[1], 16), m[2], int(m[3]), int(m[4])
        if w < 120 or h < 90 or 'Toravo Tandem' in title: continue
        tl = title.lower()
        if 'gamepad view' in tl:
            return {'wid': wid, 'title': title, 'w': w, 'h': h}
        if 'secondary' in tl or ('azahar' in tl and system == 'n3ds') or ('melonds' in tl and system == 'nds'):
            candidates.append({'wid': wid, 'title': title, 'w': w, 'h': h})
    if not candidates: return None
    # Secondary window in Azahar/melonDS is either explicitly titled 'Secondary' or the smaller/second window
    sec = next((c for c in candidates if 'secondary' in c['title'].lower() or 'bottom' in c['title'].lower() or '[2]' in c['title']), None)
    if sec: return sec
    if len(candidates) >= 2:
        return sorted(candidates, key=lambda c: c['w'] * c['h'])[0]
    return None


class _XButtonEvent(ctypes.Structure):
    _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong), ('send_event', ctypes.c_int),
                ('display', ctypes.c_void_p), ('window', ctypes.c_ulong), ('root', ctypes.c_ulong),
                ('subwindow', ctypes.c_ulong), ('time', ctypes.c_ulong), ('x', ctypes.c_int), ('y', ctypes.c_int),
                ('x_root', ctypes.c_int), ('y_root', ctypes.c_int), ('state', ctypes.c_uint),
                ('button', ctypes.c_uint), ('same_screen', ctypes.c_int), ('pad', ctypes.c_long * 8)]


_X_ERR = None


def send_window_touch(wid, nx, ny, phase):
    """Forward a normalized touch event (nx, ny in 0..1, phase='down'|'move'|'up') to X11 window `wid` on :0."""
    global _X_ERR
    try:
        x11 = ctypes.CDLL('libX11.so.6')
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        dpy = x11.XOpenDisplay((os.environ.get('DISPLAY') or ':0').encode())
        if not dpy: return {'error': 'kein X11'}
        try:
            _X_ERR = _X_ERR or ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(lambda *_: 0)
            x11.XSetErrorHandler(_X_ERR)
            root = ctypes.c_ulong()
            gx, gy = ctypes.c_int(), ctypes.c_int()
            gw, gh, gbw, gd = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
            x11.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                         ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                         ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
                                         ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
            if not x11.XGetGeometry(dpy, int(wid), ctypes.byref(root), ctypes.byref(gx), ctypes.byref(gy),
                                    ctypes.byref(gw), ctypes.byref(gh), ctypes.byref(gbw), ctypes.byref(gd)):
                return {'error': 'Fenster weg'}
            px = max(0, min(gw.value - 1, round(float(nx) * gw.value)))
            py = max(0, min(gh.value - 1, round(float(ny) * gh.value)))
            # Resolve deepest child widget at (px, py) (Qt/wxWidgets render inside a child XWindow!)
            target, tx, ty = ctypes.c_ulong(int(wid)), ctypes.c_int(px), ctypes.c_int(py)
            x11.XTranslateCoordinates.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                                  ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong)]
            for _ in range(5):
                child = ctypes.c_ulong(0)
                nx_c, ny_c = ctypes.c_int(), ctypes.c_int()
                if not x11.XTranslateCoordinates(dpy, target.value, target.value, tx.value, ty.value,
                                                 ctypes.byref(nx_c), ctypes.byref(ny_c), ctypes.byref(child)) or not child.value:
                    break
                x11.XTranslateCoordinates(dpy, target.value, child.value, tx.value, ty.value,
                                          ctypes.byref(tx), ctypes.byref(ty), ctypes.byref(ctypes.c_ulong()))
                target = child
            ev = _XButtonEvent()
            ev.display = dpy
            ev.window = target.value
            ev.root = root.value
            ev.time = int(time.monotonic() * 1000) & 0xFFFFFFFF
            ev.x, ev.y = tx.value, ty.value
            ev.x_root, ev.y_root = gx.value + px, gy.value + py
            ev.same_screen = 1
            x11.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]
            if phase == 'down':
                ev.type, ev.state, ev.button = 6, 0, 0  # MotionNotify first so cursor lands before click
                x11.XSendEvent(dpy, target.value, 1, 0x0040, ctypes.byref(ev))
                ev.type, ev.state, ev.button = 4, 0, 1  # ButtonPress Button1
                x11.XSendEvent(dpy, target.value, 1, 0x0004, ctypes.byref(ev))
            elif phase == 'move':
                ev.type, ev.state, ev.button = 6, 0x0100, 0  # MotionNotify + Button1Mask
                x11.XSendEvent(dpy, target.value, 1, 0x2040, ctypes.byref(ev))
            elif phase == 'up':
                ev.type, ev.state, ev.button = 5, 0x0100, 1  # ButtonRelease Button1
                x11.XSendEvent(dpy, target.value, 1, 0x0008, ctypes.byref(ev))
            x11.XFlush(dpy)
            return {'ok': True}
        finally:
            x11.XCloseDisplay(dpy)
    except Exception as e:
        return {'error': str(e)}


# ---- Virtual relative trackpad/mouse (/dev/uinput) for Moonlight / PC streaming --------------------------------------
class Mouse:
    """Virtual relative mouse (uinput) for the bottom-screen PC/Moonlight trackpad."""
    BTNS = {'left': 0x110, 'right': 0x111, 'middle': 0x112}

    def __init__(self): self.fd, self.lock = None, threading.Lock()

    def open(self):
        import fcntl
        fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(fd, 0x40045564, 1)  # UI_SET_EVBIT EV_KEY
        for code in self.BTNS.values(): fcntl.ioctl(fd, 0x40045565, code)  # UI_SET_KEYBIT
        fcntl.ioctl(fd, 0x40045564, 2)  # UI_SET_EVBIT EV_REL
        for rel in (0, 1, 8): fcntl.ioctl(fd, 0x40045566, rel)  # UI_SET_RELBIT: REL_X, REL_Y, REL_WHEEL
        fcntl.ioctl(fd, 0x405c5503, struct.pack('HHHH80sI', 3, 0x1209, 0x7a12, 1, b'Tandem Trackpad', 0))
        fcntl.ioctl(fd, 0x5501)  # UI_DEV_CREATE
        time.sleep(0.35)
        self.fd = fd

    def send(self, dx=0, dy=0, wheel=0, btn='', action='click'):
        with self.lock:
            try:
                if self.fd is None: self.open()
                pkts = b''
                if dx: pkts += struct.pack('llHHi', 0, 0, 2, 0, max(-400, min(400, int(dx))))
                if dy: pkts += struct.pack('llHHi', 0, 0, 2, 1, max(-400, min(400, int(dy))))
                if wheel: pkts += struct.pack('llHHi', 0, 0, 2, 8, max(-20, min(20, int(wheel))))
                if pkts:
                    pkts += struct.pack('llHHi', 0, 0, 0, 0, 0)
                    os.write(self.fd, pkts)
                if btn in self.BTNS:
                    code = self.BTNS[btn]
                    seq = (1, 0) if action == 'click' else (1,) if action == 'down' else (0,)
                    for v in seq:
                        os.write(self.fd, struct.pack('llHHi', 0, 0, 1, code, v) + struct.pack('llHHi', 0, 0, 0, 0, 0))
                return {'ok': True}
            except OSError as e:
                return {'error': f'Trackpad nicht verfügbar: {e}'}


MOUSE = Mouse()


# ---- Wireless Drag-&-Drop File Upload --------------------------------------------------------------------------------
def handle_upload(rfile, length, filename, kind, system, gid, roots, config_dir, valid_systems):
    """Stream an uploaded ROM, guide/map, or companion-pack .zip directly to disk without buffering in RAM."""
    if length <= 0 or length > (16 << 30):
        return {'error': 'Ungültige Dateigröße.'}
    safe = os.path.basename(urllib.parse.unquote(str(filename or '')).strip())
    safe = re.sub(r'[\x00-\x1f/\\]', '_', safe)
    if not safe or safe.startswith('.'):
        return {'error': 'Ungültiger Dateiname.'}
    ext = Path(safe).suffix.lower()

    if kind == 'guide':
        if not SAFE_ID.fullmatch(str(gid or '')) or ext not in GUIDE_EXTS:
            return {'error': 'Für Guides bitte Spiel wählen und PNG/JPG/WEBP/TXT/MD hochladen.'}
        dest_dir = _guides_dir(gid)
    elif kind == 'pack':
        if ext != '.zip':
            return {'error': 'Begleiter-Pakete müssen eine .zip-Datei sein.'}
        dest_dir = Path(config_dir) / 'packs'
        dest_dir.mkdir(parents=True, exist_ok=True)
    elif kind == 'switch_update':
        if ext not in ('.nsp', '.nsz', '.xci', '.xcz'):
            return {'error': 'Switch-Updates müssen .nsp, .nsz, .xci oder .xcz sein.'}
        rom_base = next((Path(r) for r in roots if str(r).startswith(('/run/media', '/media')) and os.access(r, os.W_OK)), None)
        if rom_base is None:
            rom_base = next((Path(r) for r in roots if os.access(r, os.W_OK)), HOME / 'ROMs')
        dest_dir = rom_base / 'switch/updates'
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        sys_id = str(system or 'auto').strip().lower()
        if sys_id == 'auto':
            sys_id = EXT_SYSTEM.get(ext, '')
        if sys_id not in valid_systems or sys_id in ('port', 'steam'):
            return {'error': f'System für „{ext or safe}“ bitte im Auswahlfeld angeben.'}
        # Prefer SD card ROMs folder if writable, else ~/ROMs
        rom_base = next((Path(r) for r in roots if str(r).startswith(('/run/media', '/media')) and os.access(r, os.W_OK)), None)
        if rom_base is None:
            rom_base = next((Path(r) for r in roots if os.access(r, os.W_OK)), HOME / 'ROMs')
        dest_dir = rom_base / sys_id
        dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        free = shutil.disk_usage(dest_dir).free
        if free < length + (128 << 20):
            return {'error': 'Nicht genug freier Speicherplatz auf dem Zielmedium.'}
    except OSError: pass

    target = dest_dir / safe
    part = dest_dir / ('.' + safe + '.part')
    left = length
    try:
        with open(part, 'wb') as out:
            while left > 0:
                chunk = rfile.read(min(262144, left))
                if not chunk:
                    raise OSError('Übertragung vorzeitig abgebrochen')
                out.write(chunk)
                left -= len(chunk)
        if kind == 'pack':
            pack_dir = dest_dir / Path(safe).stem
            with zipfile.ZipFile(part) as zf:
                names = zf.namelist()
                if any('..' in Path(n).parts or n.startswith('/') for n in names):
                    raise OSError('Unsichere Pfade im ZIP-Archiv')
                shutil.rmtree(pack_dir, ignore_errors=True)
                pack_dir.mkdir(parents=True, exist_ok=True)
                zf.extractall(pack_dir)
            part.unlink(missing_ok=True)
            return {'ok': True, 'kind': 'pack', 'text': f'Begleiter-Paket „{pack_dir.name}“ installiert.'}
        os.replace(part, target)
        return {'ok': True, 'kind': kind, 'path': str(target),
                'text': f'„{safe}“ übertragen ({dest_dir.parent.name}/{dest_dir.name}).'}
    except (OSError, zipfile.BadZipFile) as e:
        part.unlink(missing_ok=True)
        return {'error': f'Upload fehlgeschlagen: {e}'}


# ---- Native Switch Runtimes (BananaNative & Peanuts Native) discovery & converter ------------------------------------
_PROBE_CACHE = {}
_NATIVE_JOB = {'running': False, 'id': '', 'title': '', 'step': '', 'error': '', 'done_at': 0}


def _runtime_version(source_file):
    try:
        for ln in Path(source_file).read_text(errors='ignore').splitlines():
            if ln.startswith('version '):
                return ln.split(' ', 1)[1].strip()
    except OSError:
        pass
    return None


def _parse_game_tsv(tsv_path):
    meta = {}
    try:
        for ln in Path(tsv_path).read_text(encoding='utf-8', errors='ignore').splitlines():
            if not ln or ln.startswith('#') or '\t' not in ln:
                continue
            k, v = ln.split('\t', 1)
            meta.setdefault(k.strip(), v.strip())
    except OSError:
        pass
    return meta


def discover_native_packs(roots=(), home=None):
    """Discover prepared BananaNative & Peanuts Native packs under ~/Games and <SD>/Games without needing Steam shortcuts."""
    h = Path(home) if home else HOME
    app_bn = h / '.local/opt/bananative/AppDir/AppRun'
    app_pn = h / '.local/opt/peanuts/AppDir/AppRun'
    search_bases = [h / 'Games'] + [Path(r).parent / 'Games' for r in roots]
    seen_dirs, seen_tids, out = set(), set(), []
    for base in search_bases:
        for folder_name, label, runner in (('BananaNative', 'BananaNative', app_bn), ('PeanutsNative', 'PeanutsNative', app_pn)):
            cat_dir = base / folder_name
            if not cat_dir.is_dir():
                continue
            for game_dir in sorted(cat_dir.iterdir()):
                if not game_dir.is_dir():
                    continue
                try:
                    real = game_dir.resolve()
                except OSError:
                    real = game_dir
                if real in seen_dirs:
                    continue
                packs = sorted(game_dir.glob('*-work/android-pack/game.tsv'))
                if not packs:
                    continue
                seen_dirs.add(real)
                pack_dir = packs[0].parent
                meta = _parse_game_tsv(packs[0])
                tid = (meta.get('title_id') or pack_dir.parent.name.split('-')[0]).upper()
                if tid in seen_tids:
                    continue
                seen_tids.add(tid)
                title = meta.get('name') or game_dir.name
                icon = next((str(p) for p in sorted(game_dir.glob('*.png')) if p.stem.lower() != 'box'), None)
                box = next((str(p) for p in sorted(game_dir.iterdir())
                            if p.is_file() and p.stem.lower() == 'box' and p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')), None)
                game_file = next((str(p) for p in sorted(game_dir.iterdir())
                                  if p.is_file() and p.suffix.lower() in ('.nup', '.nsp', '.xci')), None)
                exe = runner if runner.is_file() and os.access(runner, os.X_OK) else (app_bn if app_bn.is_file() else None)
                if not exe:
                    continue
                out.append({
                    'tid': tid,
                    'title': f'{title} ({label})',
                    'raw_title': title,
                    'engine': label,
                    'dir': str(game_dir),
                    'pack_dir': str(pack_dir),
                    'direct': [str(exe), str(pack_dir), *([game_file] if game_file else [])],
                    'cover': icon,
                    'box': box,
                })
    return out


def peanuts_catalog(home=None):
    """Return {TITLE_ID: {'name': ..., 'companion': bool}} from installed Peanuts Native builder."""
    h = Path(home) if home else HOME
    tsv = h / '.local/opt/peanuts/builder/peanuts/games.tsv'
    cat = {}
    if not tsv.is_file():
        return cat
    try:
        for ln in tsv.read_text(encoding='utf-8', errors='ignore').splitlines():
            if not ln or ln.startswith('#'):
                continue
            parts = ln.split('\t')
            if len(parts) >= 2 and re.fullmatch(r'[0-9A-Fa-f]{16}', parts[0].strip()):
                cat[parts[0].strip().upper()] = {
                    'name': parts[1].strip(),
                    'companion': len(parts) >= 4 and parts[3].strip().lower() == 'yes',
                }
    except OSError:
        pass
    return cat


def _switch_keys_path(home=None):
    h = Path(home) if home else HOME
    for p in (h / '.local/share/eden/keys/prod.keys', h / '.switch/prod.keys'):
        if p.is_file():
            return p
    return None


def _probe_title_id(rom_path, home=None):
    """Extract 16-hex Switch base title ID from filename `[0100...]` or via fast `nximport_cli probe`."""
    p = Path(rom_path)
    m = re.search(r'\[([0-9A-Fa-f]{16})\]', p.name)
    if m:
        tid = m.group(1).upper()
        return tid[:-3] + '000' if tid.endswith('800') else tid
    try:
        st = p.stat()
    except OSError:
        return ''
    ckey = (str(p), int(st.st_mtime), st.st_size)
    if ckey in _PROBE_CACHE:
        return _PROBE_CACHE[ckey]
    h = Path(home) if home else HOME
    cli = h / '.local/opt/peanuts/builder/peanuts/.build/nximport/nximport_cli'
    keys = _switch_keys_path(h)
    tid = ''
    if cli.is_file() and keys:
        try:
            r = subprocess.run([str(cli), '--keys', str(keys), 'probe', str(p)],
                               capture_output=True, text=True, timeout=5)
            m2 = re.search(r'\bapp\s+([0-9a-fA-F]{16})\b', r.stdout)
            if m2:
                tid = m2.group(1).upper()
        except (OSError, subprocess.SubprocessError):
            pass
    _PROBE_CACHE[ckey] = tid
    return tid


def switch_native_info(games_dict, roots=(), home=None):
    """Status of BananaNative & Peanuts Native plus convertible Switch 1 games on the device."""
    h = Path(home) if home else HOME
    bn_ver = _runtime_version(h / '.local/opt/bananative/AppDir/usr/share/banananative/source')
    pn_ver = _runtime_version(h / '.local/opt/peanuts/AppDir/usr/share/banananative/source')
    builder_ok = (h / '.local/opt/peanuts/builder/peanuts/scripts/peanuts_build.py').is_file() and bool(_switch_keys_path(h))
    cat = peanuts_catalog(h)
    packed_tids = {p['tid'] for p in discover_native_packs(roots, h)}
    # Also check existing BananaNative/Peanuts packs in ~/Games/BananaNative
    for wdir in (h / 'Games/BananaNative').glob('*/*-work'):
        packed_tids.add(wdir.name.split('-')[0].upper())

    # Scan uploaded update files in ROMs/switch/updates and <SD>/Switch-Updates
    upd_tids = set()
    for r in roots:
        for udir in (Path(r) / 'switch/updates', Path(r).parent / 'Switch-Updates'):
            if udir.is_dir():
                for uf in udir.iterdir():
                    if uf.is_file() and uf.suffix.lower() in ('.nsp', '.nsz', '.xci', '.xcz'):
                        ut = _probe_title_id(uf, h)
                        if ut:
                            upd_tids.add(ut)

    candidates = []
    for g in sorted(games_dict.values(), key=lambda x: x.get('t', '').lower()):
        if g.get('s') != 'switch' or not g.get('path'):
            continue
        tid = _probe_title_id(g['path'], h)
        if not tid:
            continue
        sup = cat.get(tid)
        host_ok = (h / f'.local/opt/peanuts/AppDir/usr/bin/nxhost_{tid}').is_file()
        candidates.append({
            'id': g['id'],
            't': g['t'],
            'tid': tid,
            'supported': bool(sup),
            'host_ready': host_ok,
            'companion': bool(sup and sup.get('companion')),
            'converted': tid in packed_tids,
            'has_update': tid in upd_tids,
        })
    return {
        'banana_version': bn_ver,
        'peanuts_version': pn_ver,
        'catalog_count': len(cat),
        'builder_ready': builder_ok,
        'games': candidates,
        'job': dict(_NATIVE_JOB),
    }


def switch_native_convert(game, roots=(), home=None, on_done=None):
    """Start background conversion of a Switch 1 dump into a native Peanuts Native pack."""
    if _NATIVE_JOB['running']:
        return {'error': f'Umwandlung läuft bereits für „{_NATIVE_JOB["title"]}“.'}
    if not game or game.get('s') != 'switch' or not game.get('path'):
        return {'error': 'Kein Switch-Spiel gewählt.'}
    h = Path(home) if home else HOME
    builder = h / '.local/opt/peanuts/builder/peanuts/scripts/peanuts_build.py'
    keys = _switch_keys_path(h)
    packer_env = h / '.local/share/peanuts/packer'
    if not builder.is_file() or not keys or not (packer_env / 'venv/bin/python').is_file():
        return {'error': 'Peanuts-Builder oder prod.keys fehlt auf dem Thor.'}
    tid = _probe_title_id(game['path'], h)
    if not tid or tid not in peanuts_catalog(h):
        return {'error': 'Dieses Switch-Spiel wird von Peanuts Native noch nicht unterstützt.'}

    # Find any matching update/DLC NSPs in ROMs/switch/updates or <SD>/Switch-Updates
    inputs = [str(game['path'])]
    seen_inp = {str(Path(game['path']).resolve())}
    for r in roots:
        for udir in (Path(r) / 'switch/updates', Path(r).parent / 'Switch-Updates'):
            if udir.is_dir():
                for uf in sorted(udir.iterdir()):
                    if uf.is_file() and uf.suffix.lower() in ('.nsp', '.nsz', '.xci', '.xcz'):
                        rp = str(uf.resolve())
                        if rp not in seen_inp and _probe_title_id(uf, h) == tid:
                            seen_inp.add(rp)
                            inputs.append(str(uf))

    # Choose destination with >= 18 GB free (prefer SD card Games/PeanutsNative, else ~/Games/PeanutsNative)
    safe_folder = re.sub(r'[^A-Za-z0-9._-]+', '_', game['t']).strip('_') or tid
    dest_root = None
    for cand in ([Path(r).parent / 'Games/PeanutsNative' for r in roots if str(r).startswith(('/run/media', '/media'))]
                 + [h / 'Games/PeanutsNative']):
        try:
            cand.parent.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(cand.parent).free >= (16 << 30):
                dest_root = cand / safe_folder
                break
        except OSError:
            continue
    if dest_root is None:
        return {'error': 'Mindestens 16 GB freier Speicherplatz für die native Umwandlung erforderlich.'}

    _NATIVE_JOB.update(running=True, id=game['id'], title=game['t'], step='Starte Import (.nup) …', error='', done_at=0)

    def worker():
        try:
            dest_root.mkdir(parents=True, exist_ok=True)
            env = {
                **os.environ,
                'DOTNET_ROOT': str(packer_env / 'dotnet'),
                'DOTNET_MULTILEVEL_LOOKUP': '0',
                'PATH': f'{h / ".local/bin"}:{packer_env / "dotnet"}:{os.environ.get("PATH", "/usr/bin:/bin")}',
                'XLATE': str(h / '.local/opt/peanuts/builder/dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate-linux'),
            }
            cmd = [
                str(packer_env / 'venv/bin/python'),
                str(builder),
                *inputs,
                '--keys', str(keys),
                '--nup', str(dest_root),
                '--any-version',
                '--', '-j', '4', '-J', '6', '--shader-python', sys.executable,
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            last_line = ''
            for line in proc.stdout:
                s = line.strip()
                if not s:
                    continue
                last_line = s
                if 'shader' in s.lower():
                    _NATIVE_JOB['step'] = 'Übersetze Vulkan-Shader …'
                elif 'rewrite' in s.lower() or 'patched' in s.lower():
                    _NATIVE_JOB['step'] = 'Schreibe ARM64-Code nativ um …'
                elif 'nup' in s.lower() or 'unpack' in s.lower():
                    _NATIVE_JOB['step'] = 'Entpacke & baue .nup-Container …'
            rc = proc.wait()
            if rc != 0:
                _NATIVE_JOB.update(running=False, error=last_line or f'Fehlercode {rc}', step='Fehlgeschlagen')
                if on_done:
                    on_done(False, f'Umwandlung fehlgeschlagen: {_NATIVE_JOB["error"][:120]}')
                return
            # Free intermediate SPIR-V build scratch (~1-3.5 GB) now that dmsh_vk.lib is inside android-pack
            shutil.rmtree(dest_root / f'{tid}-work/android-shaders', ignore_errors=True)
            _NATIVE_JOB.update(running=False, step='Fertig!', error='', done_at=int(time.time()))
            if on_done:
                on_done(True, f'„{game["t"]}“ ist jetzt als natives Switch-Spiel bereit!')
        except Exception as e:
            _NATIVE_JOB.update(running=False, error=str(e), step='Fehlgeschlagen')
            if on_done:
                on_done(False, f'Umwandlung fehlgeschlagen: {e}')

    threading.Thread(target=worker, daemon=True).start()
    return {'ok': True, 'text': f'Native Umwandlung für „{game["t"]}“ im Hintergrund gestartet.'}

