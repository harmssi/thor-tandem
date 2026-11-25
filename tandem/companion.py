"""Universal game companion back-end for Toravo Tandem:
- Per-game notes, checklists & finger-sketch PNG storage
- Per-game offline guides/maps & Wikipedia lore/walkthrough fetcher
- Visual emulator save-state discovery (with screenshot thumbnails)
- Dual-screen secondary window configuration & X11 touch forwarding (melonDS, Azahar, Cemu)
- Virtual uinput relative trackpad/mouse (for Moonlight / PC streaming)
- Streaming wireless ROM / guide / companion-pack upload handler
Standard library + libX11 ctypes + /dev/uinput only."""
import ctypes, glob, hashlib, json, os, re, shutil, struct, subprocess, sys, threading, time, urllib.parse, urllib.request, zipfile
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'tandem'

SAFE_ID = re.compile(r'^[A-Za-z0-9_\-]{2,64}$')
GUIDE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.txt', '.md', '.pdf', '.cbz'}

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


# ---- Native Game Companion Registry, Persistent State & Live Gamepad Bridge ------------------------------------------
NATIVE_TID_DECKS = {
    '01001B300B9BE000': 'd3',          # Diablo III: Eternal Collection
    '01005CA01580E000': 'p5r',         # Persona 5 Royal
    '01006BB00C6F0000': 'zelda_la',    # The Legend of Zelda: Link's Awakening
    '0400486024DEC000': 'oot',         # The Legend of Zelda: Ocarina of Time
    '0100000000010000': 'odyssey',     # Super Mario Odyssey
    '010015100B514000': 'wonder',      # Super Mario Bros. Wonder
    '0400C3F00006E000': 'mkworld',     # Mario Kart World
    '0100152000022000': 'mkworld',     # Mario Kart 8 Deluxe
    '0100187003A36000': 'letsgo',      # Pokémon: Let's Go, Eevee!
    '010003F003A34000': 'letsgo',      # Pokémon: Let's Go, Pikachu!
    '01009AA000FAA000': 'mania',       # Sonic Mania Plus
    '0100606026F12000': 'ffres',       # FINAL FANTASY RESONANCE
    '010051F0207B2000': 'tomodachi',   # Tomodachi Life: Living the Dream
}

NATIVE_APPID_DECKS = {
    '1687950': 'p5r',                  # Persona 5 Royal (Steam)
    '2344520': 'd3',                   # Diablo IV / III family fallback if shortcutted
}

NATIVE_TITLE_PATTERNS = (
    ('diablo iii', 'd3'),
    ('diablo 3', 'd3'),
    ('persona 5', 'p5r'),
    ("link's awakening", 'zelda_la'),
    ('links awakening', 'zelda_la'),
    ('ocarina of time', 'oot'),
    ('mario odyssey', 'odyssey'),
    ('mario bros. wonder', 'wonder'),
    ('mario bros wonder', 'wonder'),
    ('mario wonder', 'wonder'),
    ('mario kart world', 'mkworld'),
    ('mario kart 8', 'mkworld'),
    ("let's go, eevee", 'letsgo'),
    ("let's go, evoli", 'letsgo'),
    ("let's go, pikachu", 'letsgo'),
    ('lets go eevee', 'letsgo'),
    ('lets go evoli', 'letsgo'),
    ('sonic mania', 'mania'),
    ('final fantasy resonance', 'ffres'),
    ('tomodachi life', 'tomodachi'),
    ('wow forever', 'wow'),
    ('world of warcraft', 'wow'),
    ('super mario sunshine', 'sunshine'),
    ("luigi's mansion", 'luigis_mansion'),
    ('luigis mansion', 'luigis_mansion'),
    ('thousand-year door', 'ttyd'),
    ('onentor', 'ttyd'),
    ('double dash', 'mkdd'),
    ('smash bros. melee', 'melee'),
    ('smash bros melee', 'melee'),
    ('animal crossing', 'ac_gc'),
    ('wrath of cortex', 'crash_woc'),
    ('zorn des cortex', 'crash_woc'),
)


def resolve_native_companion(game):
    """Return bespoke bottom-screen companion key ('d3', 'p5r', 'zelda_la', 'oot', 'odyssey', 'wonder',
    'mkworld', 'letsgo', 'mania', 'ffres', 'tomodachi') for a Native or matching game dict, or None."""
    if not isinstance(game, dict):
        return None
    tid = str(game.get('tid') or '').strip().upper()
    if not tid:
        gid = str(game.get('id') or '')
        if gid.startswith('native-') and len(gid) >= 23:
            tid = gid[7:23].upper()
        elif game.get('path'):
            m = re.search(r'\[([0-9A-Fa-f]{16})\]', str(game['path']))
            if m:
                tid = m.group(1).upper()
                if tid.endswith('800'):
                    tid = tid[:-3] + '000'
    if tid in NATIVE_TID_DECKS:
        return NATIVE_TID_DECKS[tid]
    appid = str(game.get('appid') or '').strip()
    if appid in NATIVE_APPID_DECKS:
        return NATIVE_APPID_DECKS[appid]
    title = str(game.get('t') or '').lower().replace('’', "'")
    for needle, deck_key in NATIVE_TITLE_PATTERNS:
        if needle in title:
            return deck_key
    return None


def _cstate_dir():
    d = STATE / 'cstate'
    d.mkdir(parents=True, exist_ok=True)
    return d


def cstate_get(key):
    if not SAFE_ID.fullmatch(str(key or '')):
        return {'error': 'ungültige ID'}
    f = _cstate_dir() / f'{key}.json'
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    return {'key': key, 'data': data}


def cstate_save(key, payload):
    if not SAFE_ID.fullmatch(str(key or '')):
        return {'error': 'ungültige ID'}
    cur = cstate_get(key).get('data') or {}
    if isinstance(payload, dict):
        if isinstance(payload.get('data'), dict):
            cur = dict(payload['data'])
        if isinstance(payload.get('patch'), dict):
            for k, v in payload['patch'].items():
                ks = str(k)[:80]
                if v is None:
                    cur.pop(ks, None)
                else:
                    cur[ks] = v
        if isinstance(payload.get('toggle'), str):
            tk = payload['toggle'][:80]
            done = dict(cur.get('done') or {})
            if done.get(tk):
                done.pop(tk, None)
            else:
                done[tk] = True
            cur['done'] = done
    raw = json.dumps(cur, ensure_ascii=False)
    if len(raw) > 262144:
        return {'error': 'Ungültige Dateigröße.'}
    f = _cstate_dir() / f'{key}.json'
    tmp = f.with_suffix('.tmp')
    tmp.write_text(raw, encoding='utf-8')
    os.replace(tmp, f)
    return {'ok': True, 'key': key, 'data': cur}


def send_native_pad(seq, port=8779):
    """Send a live button/chord/melody/shake sequence (e.g. 'R', 'PLUS,R', 'SHAKE', 'NOTE:RLeft,RUp,RRight')
    to the running PeanutsNative / BananaNative host on 127.0.0.1:8779 without stealing window focus."""
    import socket
    s = re.sub(r'[^A-Za-z0-9_+,:\-]', '', str(seq or ''))[:180]
    if not s:
        return {'error': 'ungültige ID'}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(s.encode('ascii'), ('127.0.0.1', int(port)))
        return {'ok': True, 'sent': s}
    except OSError as e:
        return {'error': str(e)}


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


# ---- Per-game Guides, Maps, PDF/CBZ Manuals & Web Wiki Reader -------------------------------------------------------
def _guide_kind(suffix):
    suf = suffix.lower()
    if suf in {'.pdf', '.cbz'}:
        return 'book'
    if suf in {'.png', '.jpg', '.jpeg', '.webp'}:
        return 'image'
    return 'text'


def _esde_manual_candidates(game):
    """Locate ES-DE / EmuDeck manuals (`downloaded_media/<sys>/manuals/<stem>.pdf` or `ROMs/<sys>/manuals/<stem>.pdf`)."""
    if not game or not game.get('path'):
        return []
    rom = Path(game['path'])
    sys_name = game.get('s') or rom.parent.name
    roots = [
        rom.parent / 'manuals',
        rom.parent.parent.parent / 'ES-DE/downloaded_media' / sys_name / 'manuals',
        HOME / 'ES-DE/downloaded_media' / sys_name / 'manuals',
    ]
    found = []
    for mdir in roots:
        if not mdir.is_dir():
            continue
        for ext in ('.pdf', '.cbz'):
            exact = mdir / (rom.stem + ext)
            if exact.is_file():
                found.append(exact)
    return found


def guides_list(gid, game=None):
    if not SAFE_ID.fullmatch(str(gid or '')): return {'items': []}
    items, seen = [], set()
    for mf in _esde_manual_candidates(game):
        rp = str(mf.resolve())
        if rp not in seen:
            seen.add(rp)
            items.append({'name': '__manual__' + mf.name, 'title': f'Handbuch · {mf.stem.replace("_", " ")}',
                          'kind': 'book', 'src': 'manual', 'size': mf.stat().st_size})
    folders = [_guides_dir(gid)]
    if game and game.get('path'):
        rom = Path(game['path'])
        gdir = rom.parent / 'guides'
        if gdir.is_dir():
            for f in sorted(gdir.iterdir()):
                if f.is_file() and f.suffix.lower() in GUIDE_EXTS and f.stem.lower().startswith(rom.stem.lower()):
                    seen.add(str(f.resolve()))
                    items.append({'name': f.name, 'title': f.stem.replace('_', ' '),
                                  'kind': _guide_kind(f.suffix),
                                  'src': 'rom', 'size': f.stat().st_size})
    for folder in folders:
        if not folder.is_dir(): continue
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.suffix.lower() not in GUIDE_EXTS or str(f.resolve()) in seen: continue
            items.append({'name': f.name, 'title': f.stem.replace('_', ' '),
                          'kind': _guide_kind(f.suffix),
                          'src': 'local', 'size': f.stat().st_size})
    return {'gid': gid, 'items': items}


def guide_file(gid, name, game=None):
    if not SAFE_ID.fullmatch(str(gid or '')): return None
    raw_name = str(name or '')
    if raw_name.startswith('__manual__'):
        want = os.path.basename(raw_name[len('__manual__'):])
        for mf in _esde_manual_candidates(game):
            if mf.name == want:
                return mf
        return None
    safe = os.path.basename(raw_name)
    if not safe or Path(safe).suffix.lower() not in GUIDE_EXTS: return None
    cand = [_guides_dir(gid) / safe]
    if game and game.get('path'):
        cand.append(Path(game['path']).parent / 'guides' / safe)
    return next((p for p in cand if p.is_file()), None)


def book_info(path):
    """Return {'pages': N, 'format': 'pdf'|'cbz'} for a PDF or CBZ game manual."""
    p = Path(path)
    suf = p.suffix.lower()
    if suf == '.cbz':
        try:
            with zipfile.ZipFile(p) as zf:
                imgs = [n for n in zf.namelist() if not n.startswith('__MACOSX') and Path(n).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}]
            return {'ok': True, 'pages': len(imgs), 'format': 'cbz'}
        except Exception as exc:
            return {'error': f'CBZ-Fehler: {exc}'}
    if suf == '.pdf':
        if shutil.which('pdfinfo'):
            out = _run_q(['pdfinfo', str(p)])
            m = re.search(r'(?m)^Pages:\s*(\d+)', out)
            if m:
                return {'ok': True, 'pages': int(m[1]), 'format': 'pdf'}
        try:
            from PySide6.QtGui import QGuiApplication
            if QGuiApplication.instance() is not None and threading.current_thread() is threading.main_thread():
                from PySide6.QtPdf import QPdfDocument
                doc = QPdfDocument()
                doc.load(str(p))
                cnt = doc.pageCount()
                doc.close()
                if cnt > 0:
                    return {'ok': True, 'pages': cnt, 'format': 'pdf'}
        except Exception:
            pass
        # Fallback regex scan for /Type /Page
        try:
            raw = p.read_bytes()
            cnt = len(re.findall(rb'/Type\s*/Page\b', raw))
            return {'ok': True, 'pages': max(1, cnt), 'format': 'pdf'}
        except OSError as exc:
            return {'error': str(exc)}
    return {'error': 'Nicht unterstütztes Buchformat.'}


def book_page_png(path, page_idx=0, max_width=1280):
    """Render 0-based `page_idx` of a `.pdf` or `.cbz` manual to PNG/image bytes (with fast tmpfs cache)."""
    p = Path(path)
    suf = p.suffix.lower()
    idx = max(0, int(page_idx))
    rt = Path(os.environ.get('XDG_RUNTIME_DIR') or '/tmp') / 'tandem-books'
    rt.mkdir(parents=True, exist_ok=True)
    st = p.stat()
    ckey = f'{hashlib.sha1(f"{p}:{st.st_mtime_ns}:{max_width}".encode()).hexdigest()[:14]}-p{idx}.png'
    cached = rt / ckey
    if cached.is_file() and cached.stat().st_size > 256:
        return cached.read_bytes(), 'image/png'

    if suf == '.cbz':
        try:
            with zipfile.ZipFile(p) as zf:
                imgs = sorted(n for n in zf.namelist() if not n.startswith('__MACOSX') and Path(n).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'})
                if not imgs:
                    return b'', 'image/png'
                pick = imgs[min(idx, len(imgs) - 1)]
                ext = Path(pick).suffix.lower()
                mime = 'image/png' if ext == '.png' else ('image/webp' if ext == '.webp' else 'image/jpeg')
                return zf.read(pick), mime
        except Exception:
            return b'', 'image/png'

    if suf == '.pdf':
        if shutil.which('pdftoppm'):
            p1 = str(idx + 1)
            prefix = rt / f'.ppm-{ckey}'
            try:
                subprocess.run(['pdftoppm', '-png', '-f', p1, '-l', p1, '-scale-to-x', str(max_width), '-scale-to-y', '-1',
                                str(p), str(prefix)], capture_output=True, timeout=10)
                outs = sorted(rt.glob(f'.ppm-{ckey}*.png'))
                if outs:
                    raw = outs[0].read_bytes()
                    for o in outs:
                        o.unlink(missing_ok=True)
                    cached.write_bytes(raw)
                    return raw, 'image/png'
            except Exception:
                pass
        try:
            from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
            if QGuiApplication.instance() is not None and threading.current_thread() is threading.main_thread():
                from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
                from PySide6.QtPdf import QPdfDocument
                doc = QPdfDocument()
                doc.load(str(p))
                cnt = doc.pageCount()
                if cnt > 0:
                    pno = min(idx, cnt - 1)
                    pt_sz = doc.pagePointSize(pno)
                    pw = max(1.0, pt_sz.width())
                    ph = max(1.0, pt_sz.height())
                    tw = int(max_width)
                    th = max(64, round(tw * (ph / pw)))
                    qimg = doc.render(pno, QSize(tw, th))
                    doc.close()
                    if not qimg.isNull():
                        paper = QImage(qimg.width(), qimg.height(), QImage.Format.Format_RGB32)
                        paper.fill(QColor('#f8f8f6'))
                        qp = QPainter(paper)
                        qp.drawImage(0, 0, qimg)
                        qp.end()
                        ba = QByteArray()
                        buf = QBuffer(ba)
                        buf.open(QIODevice.OpenModeFlag.WriteOnly)
                        paper.save(buf, 'PNG')
                        raw = bytes(ba)
                        if raw:
                            cached.write_bytes(raw)
                            return raw, 'image/png'
                else:
                    doc.close()
        except Exception:
            pass
    return b'', 'image/png'


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


# ---- ProtonDB Compatibility Cache & On-Device Artwork Picker (SteamGridDB / Libretro / Steam CDN) --------------------
PROTONDB_CACHE_FILE = STATE / 'protondb.json'
CUSTOM_ART_DIR = DATA_DIR / 'custom_art'

LIBRETRO_REPO_MAP = {
    'nes': 'Nintendo_-_Nintendo_Entertainment_System',
    'famicom': 'Nintendo_-_Family_Computer_Disk_System',
    'fds': 'Nintendo_-_Family_Computer_Disk_System',
    'snes': 'Nintendo_-_Super_Nintendo_Entertainment_System',
    'sfc': 'Nintendo_-_Super_Nintendo_Entertainment_System',
    'n64': 'Nintendo_-_Nintendo_64',
    'gb': 'Nintendo_-_Game_Boy',
    'gbc': 'Nintendo_-_Game_Boy_Color',
    'gba': 'Nintendo_-_Game_Boy_Advance',
    'nds': 'Nintendo_-_Nintendo_DS',
    'n3ds': 'Nintendo_-_Nintendo_3DS',
    'gc': 'Nintendo_-_GameCube',
    'wii': 'Nintendo_-_Wii',
    'wiiu': 'Nintendo_-_Wii_U',
    'switch': 'Nintendo_-_Nintendo_Switch',
    'psx': 'Sony_-_PlayStation',
    'ps2': 'Sony_-_PlayStation_2',
    'psp': 'Sony_-_PlayStation_Portable',
    'megadrive': 'Sega_-_Mega_Drive_-_Genesis',
    'genesis': 'Sega_-_Mega_Drive_-_Genesis',
    'mastersystem': 'Sega_-_Master_System_-_Mark_III',
    'gamegear': 'Sega_-_Game_Gear',
    'saturn': 'Sega_-_Saturn',
    'dreamcast': 'Sega_-_Dreamcast',
    'pcengine': 'NEC_-_PC_Engine_-_TurboGrafx_16',
    'neogeo': 'SNK_-_Neo_Geo',
    'arcade': 'FBNeo_-_Arcade_Games',
    'fbneo': 'FBNeo_-_Arcade_Games',
}


def load_protondb_cache(cache_file=PROTONDB_CACHE_FILE):
    try:
        return json.loads(Path(cache_file).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def sync_protondb(appids, cache_file=PROTONDB_CACHE_FILE):
    """Fetch & cache ProtonDB tier ('platinum', 'gold', 'silver', 'bronze', 'borked') for installed Steam AppIDs."""
    cache = load_protondb_cache(cache_file)
    now = int(time.time())
    changed = False
    for aid in appids:
        s_aid = str(aid or '').strip()
        if not s_aid.isdigit() or int(s_aid) > 2_000_000_000:
            continue
        cur = cache.get(s_aid)
        if isinstance(cur, dict) and now - int(cur.get('at') or 0) < 14 * 86400:
            continue
        url = f'https://www.protondb.com/api/v1/reports/summaries/{s_aid}.json'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Toravo-Tandem/1.4'})
            with urllib.request.urlopen(req, timeout=4.5) as r:
                data = json.loads(r.read().decode('utf-8', 'replace'))
            tier = str(data.get('tier') or data.get('trendingTier') or '').lower()
            if tier in ('platinum', 'gold', 'silver', 'bronze', 'borked', 'pending'):
                cache[s_aid] = {'tier': tier, 'score': data.get('score'), 'total': data.get('total', 0), 'at': now}
                changed = True
        except Exception:
            # Negative cache for 2 days so non-existent/unlisted IDs aren't hammered
            cache[s_aid] = {'tier': '', 'at': now - 12 * 86400}
            changed = True
    if changed:
        try:
            Path(cache_file).parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(cache_file).with_suffix('.tmp')
            tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
            os.replace(tmp, cache_file)
        except OSError:
            pass
    return {k: v['tier'] for k, v in cache.items() if isinstance(v, dict) and v.get('tier')}


def custom_art_paths(gid, art_dir=CUSTOM_ART_DIR):
    """Return {'cover': str, 'hero': str} for user-overridden artwork in custom_art/."""
    out = {}
    base = Path(art_dir)
    if not base.is_dir() or not SAFE_ID.fullmatch(str(gid or '')):
        return out
    for slot in ('cover', 'hero'):
        for ext in ('.png', '.jpg', '.webp'):
            p = base / f'{gid}-{slot}{ext}'
            if p.is_file():
                out[slot] = str(p)
                break
    return out


def artwork_candidates(game, query=''):
    """Build candidate Cover & Hero artwork URLs from Steam CDN & Libretro Thumbnails for on-device Cover Picker."""
    if not game:
        return {'items': []}
    q = (str(query or '').strip() or str(game.get('t') or '').strip())
    clean_q = re.sub(r'\s*\((?:PeanutsNative|BananaNative)\)\s*$', '', q).strip()
    s = str(game.get('s') or '')
    appid = str(game.get('appid') or '')
    cands = []

    if appid.isdigit() and int(appid) < 2_000_000_000:
        cands.extend([
            {'label': 'Steam Hochformat-Cover', 'slot': 'cover',
             'url': f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900_2x.jpg'},
            {'label': 'Steam Breitbild-Header', 'slot': 'cover',
             'url': f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg'},
            {'label': 'Steam Bühnen-Hintergrund (Hero)', 'slot': 'hero',
             'url': f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_hero.jpg'},
        ])

    repo = LIBRETRO_REPO_MAP.get(s)
    if repo and clean_q:
        safe_t = re.sub(r'[&*/:`<>?\\|"]', '_', clean_q)
        variants = [safe_t]
        for reg in (' (Europe)', ' (USA)', ' (Germany)', ' (World)', ' (Japan)'):
            if '(' not in safe_t:
                variants.append(safe_t + reg)
        for v in variants[:3]:
            enc = urllib.parse.quote(v + '.png')
            reg_tag = v[len(safe_t):].strip() or 'Standard'
            cands.append({
                'label': f'Original-Verpackung · {reg_tag}', 'slot': 'cover',
                'url': f'https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/Named_Boxarts/{enc}',
            })
        enc0 = urllib.parse.quote(variants[1 if len(variants) > 1 else 0] + '.png')
        cands.append({
            'label': 'Titelbild (Named_Titles)', 'slot': 'cover',
            'url': f'https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/Named_Titles/{enc0}',
        })
        cands.append({
            'label': 'Spielszene als Hero (Named_Snaps)', 'slot': 'hero',
            'url': f'https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/Named_Snaps/{enc0}',
        })

    # Probe which candidate URLs actually exist (HEAD/Range check in parallel, fast 2.5s timeout)
    verified = []
    lock = threading.Lock()

    def _probe(item):
        try:
            req = urllib.request.Request(item['url'], method='HEAD', headers={'User-Agent': 'Toravo-Tandem/1.4'})
            with urllib.request.urlopen(req, timeout=2.8) as r:
                if r.status == 200:
                    with lock:
                        verified.append(item)
        except Exception:
            pass

    threads = [threading.Thread(target=_probe, args=(it,), daemon=True) for it in cands]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)
    # Keep deterministic order matching `cands`
    ok_urls = {v['url'] for v in verified}
    ordered = [it for it in cands if it['url'] in ok_urls]
    return {'gid': game.get('id'), 'query': clean_q, 'has_custom': bool(custom_art_paths(game.get('id'))), 'items': ordered}


def apply_custom_artwork(gid, url, slot='cover', art_dir=CUSTOM_ART_DIR):
    """Download `url` and save it as custom cover or hero for `gid`."""
    if not SAFE_ID.fullmatch(str(gid or '')) or slot not in ('cover', 'hero'):
        return {'error': 'Ungültige Anfrage.'}
    u = str(url or '').strip()
    if not u.startswith('https://'):
        return {'error': 'Nur https-Bildquellen erlaubt.'}
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'Toravo-Tandem/1.4'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read(12 << 20)
        ext = '.png' if data[:8] == b'\x89PNG\r\n\x1a\n' else ('.jpg' if data[:3] == b'\xff\xd8\xff' else '.webp')
        base = Path(art_dir)
        base.mkdir(parents=True, exist_ok=True)
        for old_ext in ('.png', '.jpg', '.webp'):
            (base / f'{gid}-{slot}{old_ext}').unlink(missing_ok=True)
        dest = base / f'{gid}-{slot}{ext}'
        tmp = dest.with_suffix('.tmp')
        tmp.write_bytes(data)
        os.replace(tmp, dest)
        return {'ok': True, 'slot': slot, 'path': str(dest), 'text': 'Neues Bild gespeichert.'}
    except Exception as exc:
        return {'error': f'Download fehlgeschlagen: {exc}'}


def reset_custom_artwork(gid, art_dir=CUSTOM_ART_DIR):
    if not SAFE_ID.fullmatch(str(gid or '')):
        return {'error': 'Ungültige ID.'}
    base = Path(art_dir)
    removed = 0
    if base.is_dir():
        for slot in ('cover', 'hero'):
            for ext in ('.png', '.jpg', '.webp'):
                p = base / f'{gid}-{slot}{ext}'
                if p.is_file():
                    p.unlink(missing_ok=True)
                    removed += 1
    return {'ok': True, 'removed': removed, 'text': 'Standard-Cover wiederhergestellt.'}


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


# ---- Dual-screen emulator configuration, Zero-Lag RetroArch & Offline OLED Shaders ----------------------------------
RA_SHADERS = ('sharp', 'auto', 'crt', 'lcd')
RA_ZEROLAG_2D = frozenset((
    'nes', 'famicom', 'fds', 'snes', 'sfc', 'gb', 'gbc', 'gba', 'megadrive', 'genesis',
    'mastersystem', 'sg-1000', 'gamegear', 'pcengine', 'supergrafx', 'atarilynx',
    'ngp', 'ngpc', 'wonderswan', 'wonderswancolor', 'atari2600', 'atari7800',
    'colecovision', 'pokemini', 'vectrex',
))
RA_LCD_SYSTEMS = frozenset((
    'gb', 'gbc', 'gba', 'gamegear', 'atarilynx', 'ngp', 'ngpc', 'wonderswan', 'wonderswancolor', 'pokemini',
))
RA_CRT_SYSTEMS = frozenset((
    'nes', 'famicom', 'fds', 'snes', 'sfc', 'megadrive', 'genesis', 'mastersystem', 'sg-1000',
    'pcengine', 'supergrafx', 'pcenginecd', 'segacd', 'sega32x', 'neogeo', 'neogeocd',
    'arcade', 'fbneo', 'fba', 'cps', 'cps1', 'cps2', 'cps3', 'mame', 'atari2600', 'atari7800',
    'psx', 'n64', 'saturn', '3do', 'colecovision', 'intellivision',
))

CRT_OLED_SLANG = """#version 450
layout(push_constant) uniform Push {
    vec4 SourceSize;
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
} params;
layout(std140, set = 0, binding = 0) uniform UBO {
    mat4 MVP;
} global;

#pragma stage vertex
layout(location = 0) in vec4 Position;
layout(location = 1) in vec2 TexCoord;
layout(location = 0) out vec2 vTexCoord;
void main() {
    gl_Position = global.MVP * Position;
    vTexCoord = TexCoord;
}

#pragma stage fragment
layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 FragColor;
layout(set = 0, binding = 2) uniform sampler2D Source;

void main() {
    // Crisp band-limited texel sampling (zero shimmer on non-integer 1080p scaling)
    vec2 tex = vTexCoord * params.SourceSize.xy - 0.5;
    vec2 idx = floor(tex);
    vec2 f = fract(tex);
    vec2 sharp_f = smoothstep(0.5 - 0.32, 0.5 + 0.32, f);
    vec2 uv = (idx + sharp_f + 0.5) * params.SourceSize.zw;
    vec3 col = texture(Source, uv).rgb;

    // Luminance-adaptive Trinitron scanlines (bright highlights bloom naturally)
    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    float wave = 0.5 + 0.5 * cos(6.2831853 * (vTexCoord.y * params.SourceSize.y - 0.5));
    float strength = mix(0.28, 0.08, luma);
    float scan = mix(1.0 - strength, 1.0 + 0.10 * strength, wave);

    // Subtle 1080p OLED aperture grille triad
    float triad = mod(floor(gl_FragCoord.x), 3.0);
    vec3 mask = vec3(1.0);
    if (triad < 0.5) mask = vec3(1.05, 0.96, 0.96);
    else if (triad < 1.5) mask = vec3(0.96, 1.05, 0.96);
    else mask = vec3(0.96, 0.96, 1.05);

    FragColor = vec4(clamp(col * scan * mask * 1.06, 0.0, 1.0), 1.0);
}
"""

HANDHELD_LCD_SLANG = """#version 450
layout(push_constant) uniform Push {
    vec4 SourceSize;
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
} params;
layout(std140, set = 0, binding = 0) uniform UBO {
    mat4 MVP;
} global;

#pragma stage vertex
layout(location = 0) in vec4 Position;
layout(location = 1) in vec2 TexCoord;
layout(location = 0) out vec2 vTexCoord;
void main() {
    gl_Position = global.MVP * Position;
    vTexCoord = TexCoord;
}

#pragma stage fragment
layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 FragColor;
layout(set = 0, binding = 2) uniform sampler2D Source;

void main() {
    vec2 tex = vTexCoord * params.SourceSize.xy;
    vec2 cell = fract(tex);
    vec2 uv = (floor(tex) + 0.5) * params.SourceSize.zw;
    vec3 raw = texture(Source, uv).rgb;

    // Gentle handheld LCD gamma & warm color balance for wide-gamut OLED
    vec3 lin = pow(max(raw, vec3(0.0)), vec3(2.2));
    mat3 lcd_mat = mat3(
        0.88, 0.09, 0.03,
        0.06, 0.87, 0.07,
        0.03, 0.11, 0.86
    );
    vec3 col = pow(clamp(lcd_mat * lin, 0.0, 1.0), vec3(1.0 / 2.2));

    // Crisp subpixel LCD cell border
    float gx = smoothstep(0.0, 0.11, cell.x) * (1.0 - smoothstep(0.89, 1.0, cell.x));
    float gy = smoothstep(0.0, 0.11, cell.y) * (1.0 - smoothstep(0.89, 1.0, cell.y));
    float grid = mix(0.80, 1.04, gx * gy);

    FragColor = vec4(clamp(col * grid, 0.0, 1.0), 1.0);
}
"""


def ensure_retroarch_shaders(home=None):
    """Write self-contained offline Vulkan Slang presets ('crt-oled' & 'handheld-lcd') for RetroArch."""
    h = Path(home) if home else HOME
    roots = [h / '.var/app/org.libretro.RetroArch/config/retroarch']
    if (h / '.config/retroarch').is_dir():
        roots.append(h / '.config/retroarch')
    primary = None
    for base in roots:
        sdir = base / 'shaders/toravo'
        try:
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / 'crt-oled.slang').write_text(CRT_OLED_SLANG, encoding='utf-8')
            (sdir / 'crt-oled.slangp').write_text(
                'shaders = "1"\nshader0 = "crt-oled.slang"\nfilter_linear0 = "false"\nscale_type0 = "viewport"\n',
                encoding='utf-8',
            )
            (sdir / 'handheld-lcd.slang').write_text(HANDHELD_LCD_SLANG, encoding='utf-8')
            (sdir / 'handheld-lcd.slangp').write_text(
                'shaders = "1"\nshader0 = "handheld-lcd.slang"\nfilter_linear0 = "false"\nscale_type0 = "viewport"\n',
                encoding='utf-8',
            )
            if primary is None:
                primary = sdir
        except OSError:
            continue
    if primary is None:
        return {}
    return {'crt': str(primary / 'crt-oled.slangp'), 'lcd': str(primary / 'handheld-lcd.slangp')}


def resolve_retroarch_shader(pref, system=''):
    """Resolve ('sharp' | 'auto' | 'crt' | 'lcd') to the concrete preset ('sharp' | 'crt' | 'lcd')."""
    p = str(pref or 'sharp').lower()
    if p in ('crt', 'lcd', 'sharp'):
        return p
    if p == 'auto':
        s = str(system or '').lower()
        if s in RA_LCD_SYSTEMS:
            return 'lcd'
        if s in RA_CRT_SYSTEMS:
            return 'crt'
    return 'sharp'


def _set_ra_kv(txt, key, val):
    line = f'{key} = "{val}"'
    pat = re.compile(r'(?m)^' + re.escape(key) + r'\s*=.*$')
    return pat.sub(lambda _: line, txt, count=1) if pat.search(txt) else txt.rstrip('\n') + '\n' + line + '\n'


def configure_retroarch(cfg=None, game=None, opt=None, home=None):
    """Apply RetroArch Zero-Lag (~55 ms lower latency), Auto-Save/Auto-Resume, thumbnails & offline OLED shaders."""
    h = Path(home) if home else HOME
    c = cfg or {}
    o = opt or {}
    system = (game or {}).get('s') or ''
    presets = ensure_retroarch_shaders(h)
    raw_pref = o.get('shader') or c.get('ra_shader') or 'sharp'
    smode = resolve_retroarch_shader(raw_pref, system)
    spath = presets.get(smode, '') if smode in ('crt', 'lcd') else ''

    zerolag = bool(c.get('ra_zerolag', True))
    autoresume = bool(c.get('ra_autoresume', True))
    preempt = bool(zerolag and system in RA_ZEROLAG_2D)

    ra_cfg = h / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg'
    if not ra_cfg.is_file() and (h / '.config/retroarch/retroarch.cfg').is_file():
        ra_cfg = h / '.config/retroarch/retroarch.cfg'
    if ra_cfg.is_file():
        try:
            if not ra_cfg.with_name('retroarch.cfg.bak-tandem').exists():
                shutil.copy2(ra_cfg, ra_cfg.with_name('retroarch.cfg.bak-tandem'))
            txt = ra_cfg.read_text(errors='surrogateescape')
            pairs = [
                ('savestate_thumbnail_enable', 'true'),
                ('network_cmd_enable', 'true'),
                ('video_max_swapchain_images', '2' if zerolag else '3'),
                ('audio_latency', '28' if zerolag else '64'),
                ('video_frame_delay_auto', 'true' if zerolag else 'false'),
                ('preemptive_frames_enable', 'true' if preempt else 'false'),
                ('run_ahead_frames', '1'),
                ('run_ahead_secondary_instance', 'true'),
                ('savestate_auto_save', 'true' if autoresume else 'false'),
                ('savestate_auto_load', 'true' if autoresume else 'false'),
                ('video_shader_enable', 'true' if spath else 'false'),
            ]
            for k, v in pairs:
                txt = _set_ra_kv(txt, k, v)
            ra_cfg.write_text(txt, errors='surrogateescape')
        except OSError:
            pass
    return {'shader_mode': smode, 'shader_path': spath, 'zerolag': zerolag, 'preemptive': preempt, 'autoresume': autoresume}


def ensure_retroarch_thumbnails(home=None):
    """Enable RetroArch savestate_thumbnail_enable so visual save-state cards get automatic PNG previews."""
    configure_retroarch({}, home=home)


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


# ---- GBADuo v1.0.1 Companion Catalog, Multi-Region Matcher & Automatic Pack Sync -------------------------------------
GBADUO_REPO = 'khumam/gba-duo-companions'
GBADUO_CATALOG_URL = f'https://raw.githubusercontent.com/{GBADUO_REPO}/main/companions.json'
GBADUO_RAW_BASE = f'https://raw.githubusercontent.com/{GBADUO_REPO}/main/'
PACK_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_\-]{1,63}$')
HACK_PACK_KEYWORDS = {
    'pokemon-unbound-companion': ('unbound',),
    'pokemon-light-platinum-companion': ('light platinum', 'lightplatinum'),
    'pokemon-monomyth-companion': ('monomyth',),
}
WILDCARD_PACK_KEYWORDS = {
    'mario-land-2-companion': ('mario land 2', '6 golden coins', 'supermarioland2'),
    'super-mario-land-2-companion': ('mario land 2', '6 golden coins', 'supermarioland2'),
}
_PACK_SYNC_LOCK = threading.Lock()
_LAST_AUTO_SYNC = 0.0


def packs_dir(cfg_dir=None):
    base = Path(cfg_dir) if cfg_dir else Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'tandem'
    d = base / 'packs'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_dir():
    d = Path(os.environ.get('XDG_CACHE_HOME', HOME / '.cache')) / 'tandem'
    d.mkdir(parents=True, exist_ok=True)
    return d


def same_gba_game(code_a, code_b):
    """GBADuo v1.0.1 multi-region rule: 4-letter GBA codes share their 3-letter game stem across regions
    (e.g. BPRE US == BPRD DE == BPRP EU == BPRJ JP). GB/GBC 'DMG-'/'CGB-' headers never cross-match."""
    x = str(code_a or '').strip().upper().removeprefix('AGB-')
    y = str(code_b or '').strip().upper().removeprefix('AGB-')
    return len(x) == 4 and len(y) == 4 and '-' not in x and '-' not in y and '?' not in x and '?' not in y and x[:3] == y[:3]


def _ver_tuple(ver):
    return tuple(int(p) if p.isdigit() else 0 for p in re.findall(r'\d+', str(ver or '0'))[:4]) or (0,)


def resolve_overview_url(raw_ov):
    if not isinstance(raw_ov, str) or not raw_ov.strip():
        return None
    s = raw_ov.strip()
    if s.startswith('https://'):
        return s
    if s.startswith('http://') or '..' in s.split('/') or s.startswith('/'):
        return None
    return GBADUO_RAW_BASE + s.lstrip('./')


def parse_gbaduo_catalog(data):
    if not isinstance(data, dict) or not isinstance(data.get('companions'), list):
        return []
    out = []
    for item in data['companions']:
        if not isinstance(item, dict):
            continue
        pid = str(item.get('id') or '').strip().lower()
        dl = str(item.get('download') or '').strip()
        if not PACK_ID_RE.fullmatch(pid) or not dl.startswith('https://'):
            continue
        games = [g for g in (item.get('games') or []) if isinstance(g, dict) and g.get('gameCode')]
        codes = [str(g['gameCode']).strip().upper() for g in games if g.get('gameCode')]
        crcs = []
        for g in games:
            if g.get('crc32'):
                try:
                    crcs.append(int(str(g['crc32']), 16))
                except ValueError:
                    pass
        out.append({
            'id': pid,
            'title': str(item.get('title') or pid)[:100],
            'description': str(item.get('description') or '')[:400],
            'version': str(item.get('version') or '0.1.0')[:24],
            'author': str(item.get('author') or '')[:60],
            'official': bool(item.get('official')),
            'download': dl,
            'codes': codes,
            'crcs': crcs,
            'pages': [str(p)[:30] for p in (item.get('pages') or []) if isinstance(p, str)][:10],
            'tags': [str(t)[:24] for t in (item.get('tags') or []) if isinstance(t, str)][:12],
            'canModifyGame': bool(item.get('canModifyGame')),
            'overview': resolve_overview_url(item.get('overview')),
        })
    return out


def fetch_gbaduo_catalog(force=False, timeout=10, opener=None):
    """Return parsed list of official & community packs from khumam/gba-duo-companions (cached 6h on disk)."""
    cfile = _cache_dir() / 'gbaduo-companions.json'
    if not force and cfile.is_file():
        try:
            age = time.time() - cfile.stat().st_mtime
            if age < 6 * 3600:
                cached = parse_gbaduo_catalog(json.loads(cfile.read_text(encoding='utf-8')))
                if cached:
                    return cached
        except (OSError, ValueError):
            pass
    open_fn = opener or urllib.request.urlopen
    try:
        req = urllib.request.Request(GBADUO_CATALOG_URL, headers={'User-Agent': 'ToravoTandem/1.0'})
        with open_fn(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
        parsed = parse_gbaduo_catalog(json.loads(raw))
        if parsed:
            tmp = cfile.with_suffix('.tmp')
            tmp.write_text(raw, encoding='utf-8')
            os.replace(tmp, cfile)
            return parsed
    except Exception:
        pass
    if cfile.is_file():
        try:
            return parse_gbaduo_catalog(json.loads(cfile.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
    return []


def _title_matches_special_pack(pack_id, title_hint):
    low = str(title_hint or '').lower().replace('_', ' ').replace('-', ' ')
    if pack_id in HACK_PACK_KEYWORDS:
        return any(k in low for k in HACK_PACK_KEYWORDS[pack_id])
    if pack_id in WILDCARD_PACK_KEYWORDS:
        return any(k in low for k in WILDCARD_PACK_KEYWORDS[pack_id])
    return True


def list_installed_packs(cfg_dir=None):
    pdir = packs_dir(cfg_dir)
    items = []
    for mf in sorted(pdir.glob('*/manifest.json')):
        try:
            m = json.loads(mf.read_text(encoding='utf-8'))
            match = m.get('match') or {}
            codes = [str(c).strip().upper() for c in (match.get('gameCode') or [])]
            crcs = [int(str(c), 16) for c in (match.get('crc32') or [])]
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        ov_dir = mf.parent / 'overview'
        local_ov = None
        if ov_dir.is_dir():
            pics = sorted(f for f in ov_dir.iterdir()
                          if f.is_file() and not f.name.startswith('.') and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'})
            if pics:
                local_ov = str(pics[0])
        items.append({
            'id': mf.parent.name,
            'manifest_id': str(m.get('id') or mf.parent.name),
            'title': str(m.get('name') or mf.parent.name),
            'version': str(m.get('version') or '0.1.0'),
            'author': str(m.get('author') or ''),
            'formatVersion': int(m.get('formatVersion') or 1),
            'codes': codes,
            'crcs': crcs,
            'has_wide': bool(m.get('gameScript')),
            'overview_file': local_ov,
        })
    return items


def match_packs_for_rom(code, crc, title_hint='', installed=None, catalog=None):
    """Return {'exact_installed', 'other_installed', 'exact_web', 'other_web', 'best_installed', 'best_web'}
    implementing GBADuo v1.0.1 exact + multi-region matching while keeping hack/wildcard packs accurate."""
    res = {'exact_installed': [], 'other_installed': [], 'exact_web': [], 'other_web': [],
           'best_installed': None, 'best_other_region': False, 'best_web': None}
    if not code:
        return res
    u_code = str(code).strip().upper()
    norm_codes = lambda cs: [str(c).strip().upper() for c in cs]

    for it in (installed if installed is not None else list_installed_packs()):
        cs, crcs = norm_codes(it['codes']), it['crcs']
        is_wildcard = bool(cs) and all('?' in c for c in cs)
        if is_wildcard and not crcs and not _title_matches_special_pack(it['id'], title_hint):
            continue
        exact_code = (u_code in cs or ('AGB-' + u_code) in cs) if cs else bool(crcs)
        if exact_code and (not crcs or crc in crcs):
            res['exact_installed'].append(it)
        elif not crcs and not is_wildcard and any(same_gba_game(c, u_code) for c in cs):
            res['other_installed'].append(it)

    any_hack_hit = any(_title_matches_special_pack(hpid, title_hint) for hpid in HACK_PACK_KEYWORDS)

    def _rank_pack(p):
        pid = p['id']
        is_hack = pid in HACK_PACK_KEYWORDS
        hack_ok = _title_matches_special_pack(pid, title_hint)
        if any_hack_hit:
            pref = 0 if (is_hack and hack_ok) else 1
        else:
            pref = 2 if is_hack else 0
        has_crc = 0 if p.get('crcs') else 1
        return (has_crc, pref, pid)

    res['exact_installed'].sort(key=_rank_pack)
    res['other_installed'].sort(key=_rank_pack)
    if res['exact_installed']:
        res['best_installed'] = res['exact_installed'][0]['id']
        res['best_other_region'] = False
    elif res['other_installed']:
        res['best_installed'] = res['other_installed'][0]['id']
        res['best_other_region'] = True

    if catalog is not None:
        for wp in catalog:
            cs, crcs = norm_codes(wp['codes']), wp['crcs']
            is_wildcard = bool(cs) and all('?' in c for c in cs)
            if is_wildcard and not crcs and not _title_matches_special_pack(wp['id'], title_hint):
                continue
            if wp['id'] in HACK_PACK_KEYWORDS and not _title_matches_special_pack(wp['id'], title_hint):
                continue
            exact_code = (u_code in cs or ('AGB-' + u_code) in cs) if cs else bool(crcs)
            if exact_code and (not crcs or crc in crcs):
                res['exact_web'].append(wp)
            elif not crcs and not is_wildcard and any(same_gba_game(c, u_code) for c in cs):
                res['other_web'].append(wp)
        res['exact_web'].sort(key=_rank_pack)
        res['other_web'].sort(key=_rank_pack)
        if res['exact_web']:
            res['best_web'] = (res['exact_web'][0], False)
        elif res['other_web']:
            res['best_web'] = (res['other_web'][0], True)
    return res


def install_zip_pack(zip_bytes, expected_id=None, cfg_dir=None):
    """Validate and atomically unpack a GBADuo companion `.zip` archive into `~/.config/tandem/packs/<id>`."""
    import io, tempfile
    if not zip_bytes or len(zip_bytes) > (32 << 20):
        return {'error': 'Ungültige Dateigröße.'}
    pdir = packs_dir(cfg_dir)
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return {'error': 'Beschädigtes ZIP-Archiv.'}
    with zf:
        names = [n for n in zf.namelist() if not n.endswith('/') and not Path(n).name.startswith('.')]
        if not names or sum(zf.getinfo(n).file_size for n in names) > (64 << 20):
            return {'error': 'Ungültige Dateigröße.'}
        m_entries = [n for n in names if Path(n).name == 'manifest.json' and len(Path(n).parts) <= 2]
        if not m_entries:
            return {'error': 'manifest.json fehlt im Begleiter-Paket.'}
        m_entry = sorted(m_entries, key=lambda s: len(Path(s).parts))[0]
        prefix = m_entry[:-len('manifest.json')]
        try:
            manifest = json.loads(zf.read(m_entry).decode('utf-8'))
        except (ValueError, KeyError):
            return {'error': 'manifest.json ist ungültig.'}
        pid = str(expected_id or manifest.get('id') or Path(prefix.rstrip('/')).name).strip().lower()
        if not PACK_ID_RE.fullmatch(pid):
            return {'error': 'ungültige ID'}
        with tempfile.TemporaryDirectory(dir=str(pdir)) as tmp:
            tpath = Path(tmp) / 'stage'
            tpath.mkdir()
            t_res = tpath.resolve()
            for n in names:
                if prefix and not n.startswith(prefix):
                    continue
                rel = n[len(prefix):] if prefix else n
                if not rel or '..' in Path(rel).parts or rel.startswith('/'):
                    continue
                dst = (tpath / rel).resolve()
                if t_res not in dst.parents:
                    return {'error': 'Ungültiger Pfad im Paket.'}
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(zf.read(n))
            if not (tpath / 'manifest.json').is_file():
                return {'error': 'manifest.json fehlt im Begleiter-Paket.'}
            final_dir = pdir / pid
            old_dir = pdir / f'.old-{pid}-{os.getpid()}'
            shutil.rmtree(old_dir, ignore_errors=True)
            if final_dir.exists():
                os.replace(final_dir, old_dir)
            try:
                os.replace(tpath, final_dir)
            finally:
                shutil.rmtree(old_dir, ignore_errors=True)
    return {'ok': True, 'id': pid, 'version': str(manifest.get('version') or '0.1.0'),
            'title': str(manifest.get('name') or pid)}


def download_catalog_pack(pack_entry, cfg_dir=None, timeout=25, opener=None):
    open_fn = opener or urllib.request.urlopen
    dl = pack_entry.get('download') or ''
    if not dl.startswith('https://'):
        return {'error': 'Ungültige Download-Adresse.'}
    try:
        req = urllib.request.Request(dl, headers={'User-Agent': 'ToravoTandem/1.0'})
        with open_fn(req, timeout=timeout) as resp:
            raw = resp.read(32 << 20)
        return install_zip_pack(raw, expected_id=pack_entry['id'], cfg_dir=cfg_dir)
    except Exception as e:
        return {'error': str(e)}


def cached_rom_identities(games_iter, rom_id_fn):
    """Fast persistent `(mtime, size) -> (code, crc)` cache so checking 60+ GB/GBC/GBA ROMs takes < 2 ms."""
    cfile = _cache_dir() / 'rom-ids.json'
    try:
        cache = json.loads(cfile.read_text(encoding='utf-8'))
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    dirty = False
    out = []
    for g in games_iter:
        if g.get('s') not in ('gb', 'gbc', 'gba') or not g.get('path'):
            continue
        p = str(g['path'])
        try:
            st = os.stat(p)
            sig = f'{int(st.st_mtime)}:{st.st_size}'
        except OSError:
            continue
        hit = cache.get(p)
        if isinstance(hit, list) and len(hit) == 3 and hit[0] == sig:
            code, crc = hit[1], hit[2]
        else:
            code, crc = rom_id_fn(p)
            cache[p] = [sig, code, crc]
            dirty = True
        if code:
            out.append((g, code, crc))
    if dirty:
        try:
            tmp = cfile.with_suffix('.tmp')
            tmp.write_text(json.dumps(cache), encoding='utf-8')
            os.replace(tmp, cfile)
        except OSError:
            pass
    return out


def sync_owned_gba_packs(games_iter, rom_id_fn, cfg_dir=None, force_catalog=False, opener=None):
    """Automatically download & update GBADuo v1.0.1 companion packs from `khumam/gba-duo-companions`
    for every GB/GBC/GBA game present in the user's library (exact + multi-region matches)."""
    global _LAST_AUTO_SYNC
    if not _PACK_SYNC_LOCK.acquire(blocking=False):
        return {'busy': True, 'installed': [], 'updated': []}
    try:
        _LAST_AUTO_SYNC = time.time()
        roms = cached_rom_identities(games_iter, rom_id_fn)
        if not roms:
            return {'ok': True, 'installed': [], 'updated': [], 'owned_roms': 0}
        catalog = fetch_gbaduo_catalog(force=force_catalog, opener=opener)
        if not catalog:
            return {'ok': False, 'installed': [], 'updated': [], 'owned_roms': len(roms)}
        installed = {p['id']: p for p in list_installed_packs(cfg_dir)}
        wanted = {}
        for g, code, crc in roms:
            m = match_packs_for_rom(code, crc, title_hint=f"{g.get('t', '')} {Path(g.get('path', '')).stem}",
                                    installed=list(installed.values()), catalog=catalog)
            if m['best_web']:
                wp, _other = m['best_web']
                wanted[wp['id']] = wp
        added, updated = [], []
        for pid, wp in wanted.items():
            cur = installed.get(pid)
            if cur and _ver_tuple(cur['version']) >= _ver_tuple(wp['version']):
                continue
            res = download_catalog_pack(wp, cfg_dir=cfg_dir, opener=opener)
            if res.get('ok'):
                (updated if cur else added).append(pid)
        return {'ok': True, 'installed': added, 'updated': updated, 'owned_roms': len(roms), 'catalog_count': len(catalog)}
    finally:
        _PACK_SYNC_LOCK.release()


def gba_shelf_status(games_iter, rom_id_fn, saved_assign=None, cfg_dir=None):
    """Build the GBADuo v1.0.1 Companion Shelf overview: installed packs, catalog packs, and owned-game matches."""
    installed = list_installed_packs(cfg_dir)
    inst_map = {p['id']: p for p in installed}
    catalog = fetch_gbaduo_catalog(force=False)
    roms = cached_rom_identities(games_iter, rom_id_fn)
    assign = saved_assign or {}
    owned_matches = []
    for g, code, crc in roms:
        hint = f"{g.get('t', '')} {Path(g.get('path', '')).stem}"
        m = match_packs_for_rom(code, crc, title_hint=hint, installed=installed, catalog=catalog)
        if m['exact_installed'] or m['other_installed'] or m['exact_web'] or m['other_web']:
            chosen = assign.get(g['id']) or m['best_installed']
            owned_matches.append({
                'gid': g['id'],
                'title': g.get('t', ''),
                'system': g.get('s', 'gba'),
                'gameCode': code,
                'assigned': chosen,
                'otherRegion': bool(m['best_other_region'] if chosen == m['best_installed'] else
                                    any(x['id'] == chosen for x in m['other_installed'])),
                'installedPacks': [x['id'] for x in (m['exact_installed'] + m['other_installed'])],
                'webPacks': [x['id'] for x in (m['exact_web'] + m['other_web']) if x['id'] not in inst_map],
            })
    return {
        'source': f'https://github.com/{GBADUO_REPO}',
        'installed': installed,
        'catalog': [{**c, 'installedVersion': inst_map[c['id']]['version'] if c['id'] in inst_map else None,
                     'updateAvailable': c['id'] in inst_map and _ver_tuple(c['version']) > _ver_tuple(inst_map[c['id']]['version'])}
                    for c in catalog],
        'games': owned_matches,
    }


# ---- Smart Gameplay Moment Capture ("Zuletzt im Spiel" without Save/Pause Menus) ---------------------------------------
def score_gameplay_frame_rgb(w, h, rgb):
    """Pure-Python fast visual classifier on a ~160x90 RGB24 thumbnail (<3 ms).
    Auto-crops 4:3/3:2 black pillarbox/letterbox bars, rejects black/white/fade frames, and detects & rejects
    save-slot / pause / system menus (like Final Fantasy save screens, RPG status menus, or RetroArch overlays)
    by measuring flat UI-panel area (`flat_ratio`), long horizontal box-fill runs (`long_run_ratio`), and 8x6 spatial
    palette diversity (`unique_ratio`)."""
    if w < 16 or h < 12 or len(rgb) < w * h * 3:
        return {'score': 0.0, 'is_menu': True, 'reason': 'invalid', 'fp': b''}

    # Precompute integer luma (0..255) per pixel
    mv = memoryview(rgb)
    luma = [0] * (w * h)
    idx = 0
    for i in range(w * h):
        luma[i] = (mv[idx] * 77 + mv[idx + 1] * 150 + mv[idx + 2] * 29) >> 8
        idx += 3

    # Trim black pillarboxes (left/right) and letterboxes (top/bottom) so 4:3/3:2 retro games score fairly
    x0, x1 = 0, w
    while x0 < w // 3:
        col_vals = [luma[y * w + x0] for y in range(0, h, 2)]
        if sum(col_vals) / len(col_vals) < 8 and max(col_vals) < 24:
            x0 += 1
        else:
            break
    while x1 > w - w // 3:
        col_vals = [luma[y * w + (x1 - 1)] for y in range(0, h, 2)]
        if sum(col_vals) / len(col_vals) < 8 and max(col_vals) < 24:
            x1 -= 1
        else:
            break
    y0, y1 = 0, h
    while y0 < h // 4:
        row_vals = luma[y0 * w + x0:y0 * w + x1:2]
        if row_vals and sum(row_vals) / len(row_vals) < 8 and max(row_vals) < 24:
            y0 += 1
        else:
            break
    while y1 > h - h // 4:
        row_vals = luma[(y1 - 1) * w + x0:(y1 - 1) * w + x1:2]
        if row_vals and sum(row_vals) / len(row_vals) < 8 and max(row_vals) < 24:
            y1 -= 1
        else:
            break

    aw, ah = x1 - x0, y1 - y0
    if aw < w * 0.35 or ah < h * 0.35:
        return {'score': 0.0, 'is_menu': True, 'reason': 'black_bars', 'fp': b''}

    # Build 16x9 motion fingerprint over active viewport
    fp = bytearray(16 * 9)
    for fy in range(9):
        sy = y0 + (fy * ah) // 9
        for fx in range(16):
            sx = x0 + (fx * aw) // 16
            fp[fy * 16 + fx] = luma[sy * w + sx]

    total_px = aw * ah
    sum_l = 0
    sum_l2 = 0
    flat_px = 0
    interior_px = max(1, (aw - 1) * (ah - 1))
    long_run_px = 0
    min_run = max(10, int(aw * 0.18))
    grad_sum = 0

    for y in range(y0, y1):
        row_off = y * w
        b0_start = (row_off + x0) * 3
        run_r, run_g, run_b = mv[b0_start], mv[b0_start + 1], mv[b0_start + 2]
        run_len = 1
        for x in range(x0, x1):
            lv = luma[row_off + x]
            sum_l += lv
            sum_l2 += lv * lv
            b_off = (row_off + x) * 3
            r0, g0, b0 = mv[b_off], mv[b_off + 1], mv[b_off + 2]
            if x > x0:
                if abs(r0 - run_r) <= 2 and abs(g0 - run_g) <= 2 and abs(b0 - run_b) <= 2:
                    run_len += 1
                else:
                    if run_len >= min_run:
                        long_run_px += run_len
                    run_r, run_g, run_b = r0, g0, b0
                    run_len = 1
            if x + 1 < x1 and y + 1 < y1:
                r_r, g_r, b_r = mv[b_off + 3], mv[b_off + 4], mv[b_off + 5]
                b_dn = b_off + w * 3
                r_d, g_d, b_d = mv[b_dn], mv[b_dn + 1], mv[b_dn + 2]
                dx = max(abs(r0 - r_r), abs(g0 - g_r), abs(b0 - b_r))
                dy = max(abs(r0 - r_d), abs(g0 - g_d), abs(b0 - b_d))
                grad_sum += dx + dy
                if dx <= 1 and dy <= 1:
                    flat_px += 1
        if run_len >= min_run:
            long_run_px += run_len

    mean_l = sum_l / total_px
    var_l = max(0.0, (sum_l2 / total_px) - mean_l * mean_l)
    std_l = var_l ** 0.5
    if mean_l < 14.0 or mean_l > 242.0 or std_l < 13.0:
        return {'score': 0.0, 'is_menu': True, 'reason': 'fade_or_blank', 'fp': bytes(fp)}

    flat_ratio = flat_px / interior_px
    long_run_ratio = long_run_px / total_px
    mean_grad = grad_sum / (2.0 * interior_px)

    # 8x6 spatial color+texture diversity across the active viewport
    buckets = set()
    gx, gy = 8, 6
    for ty in range(gy):
        by0 = y0 + (ty * ah) // gy
        by1 = max(by0 + 1, y0 + ((ty + 1) * ah) // gy)
        for tx in range(gx):
            bx0 = x0 + (tx * aw) // gx
            bx1 = max(bx0 + 1, x0 + ((tx + 1) * aw) // gx)
            sr = sg = sb = cnt = 0
            lmin, lmax = 255, 0
            for yy in range(by0, by1):
                for xx in range(bx0, bx1):
                    p3 = (yy * w + xx) * 3
                    sr += mv[p3]
                    sg += mv[p3 + 1]
                    sb += mv[p3 + 2]
                    lv = luma[yy * w + xx]
                    if lv < lmin: lmin = lv
                    if lv > lmax: lmax = lv
                    cnt += 1
            if cnt:
                buckets.add(((sr // cnt) >> 5, (sg // cnt) >> 5, (sb // cnt) >> 5, min(3, (lmax - lmin) // 28)))
    unique_ratio = len(buckets) / float(gx * gy)

    # Save screens & pause menus have large flat panel fills + long horizontal slot runs + low tile variety
    is_menu = bool(
        flat_ratio > 0.56
        or (long_run_ratio > 0.46 and unique_ratio < 0.38)
        or (flat_ratio > 0.44 and long_run_ratio > 0.52)
        or unique_ratio < 0.21
    )

    richness = (
        0.42 * min(1.0, unique_ratio / 0.68)
        + 0.28 * max(0.0, 1.0 - flat_ratio / 0.65)
        + 0.18 * max(0.0, 1.0 - long_run_ratio / 0.62)
        + 0.12 * min(1.0, mean_grad / 18.0)
    )
    score = round(richness * (0.18 if is_menu else 1.0), 4)
    return {
        'score': score,
        'is_menu': is_menu,
        'flat_ratio': round(flat_ratio, 3),
        'long_run_ratio': round(long_run_ratio, 3),
        'unique_ratio': round(unique_ratio, 3),
        'fp': bytes(fp),
    }


def frame_motion_diff(fp_a, fp_b):
    if not fp_a or not fp_b or len(fp_a) != len(fp_b):
        return 10.0
    return sum(abs(a - b) for a, b in zip(fp_a, fp_b)) / float(len(fp_a))


def load_rgb_thumb(image_path, tw=160, th=90):
    p = Path(image_path)
    if not p.is_file():
        return None
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        img = QImage(str(p))
        if not img.isNull():
            sub = img.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            sub = sub.convertToFormat(QImage.Format.Format_RGB888)
            ptr = sub.constBits()
            stride = sub.bytesPerLine()
            if stride == tw * 3:
                return bytes(ptr[:tw * th * 3])
            rows = bytearray()
            for y in range(th):
                rows.extend(ptr[y * stride:y * stride + tw * 3])
            return bytes(rows)
    except Exception:
        pass
    if shutil.which('ffmpeg'):
        res = subprocess.run(
            ['ffmpeg', '-v', 'error', '-i', str(p), '-vf', f'scale={tw}:{th}', '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
            capture_output=True, timeout=8,
        )
        if res.returncode == 0 and len(res.stdout) >= tw * th * 3:
            return res.stdout[:tw * th * 3]
    return None


def score_gameplay_frame(image_path):
    rgb = load_rgb_thumb(image_path, 160, 90)
    if not rgb:
        return {'score': 0.0, 'is_menu': True, 'reason': 'unreadable', 'fp': b''}
    return score_gameplay_frame_rgb(160, 90, rgb)


def pick_best_moment(entries, quit_at, min_pre_quit_secs=25.0):
    """Given captured gameplay frames `[{'path', 'at', 'score', 'is_menu', 'motion'}]` and `quit_at`,
    choose the best real in-world scene from BEFORE the player opened the save/pause menu to quit.
    Returns the chosen dict or None if only menus/fades were seen."""
    valid = [e for e in (entries or ()) if not e.get('is_menu') and float(e.get('score') or 0) >= 0.34 and Path(e['path']).is_file()]
    if not valid:
        return None
    pre_menu = [e for e in valid if (quit_at - float(e['at'])) >= min_pre_quit_secs]
    pool = pre_menu if pre_menu else valid
    newest_t = max(float(e['at']) for e in pool)
    def rank(e):
        recency = max(0.0, 1.0 - (newest_t - float(e['at'])) / 180.0)
        mot_bonus = 0.08 * min(1.0, float(e.get('motion') or 0.0) / 10.0)
        return float(e['score']) + mot_bonus + 0.07 * recency
    return max(pool, key=rank)


class MomentTracker:
    """Captures rolling top-screen gameplay frames via `gamescopectl screenshot` while playing and commits
    the best non-menu pre-quit scene to `~/.local/state/tandem/moments/<gid>.jpg` when the game exits."""

def capture_screen_frame(out_path, display=None, wayland='gamescope-0'):
    """Capture one screenshot frame into `out_path` using gamescopectl, ArmadaOS X11 ffmpeg x11grab, or ImageMagick."""
    out = Path(out_path)
    out.unlink(missing_ok=True)
    rt_dir = os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'
    dpy = display or os.environ.get('DISPLAY') or ':0'
    if shutil.which('gamescopectl') and (dpy == ':0' or not display):
        env = {**os.environ, 'XDG_RUNTIME_DIR': rt_dir, 'WAYLAND_DISPLAY': wayland}
        try:
            subprocess.run(['gamescopectl', 'screenshot', str(out)], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
            for _ in range(12):
                if out.is_file() and out.stat().st_size > 2048:
                    return True
                time.sleep(0.05)
        except Exception:
            pass
    if shutil.which('ffmpeg'):
        try:
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'x11grab', '-i', dpy, '-frames:v', '1', str(out)],
                           env={**os.environ, 'DISPLAY': dpy, 'XDG_RUNTIME_DIR': rt_dir},
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
            if out.is_file() and out.stat().st_size > 2048:
                return True
        except Exception:
            pass
    if shutil.which('import'):
        try:
            subprocess.run(['import', '-display', dpy, '-window', 'root', str(out)],
                           env={**os.environ, 'DISPLAY': dpy, 'XDG_RUNTIME_DIR': rt_dir},
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
            if out.is_file() and out.stat().st_size > 2048:
                return True
        except Exception:
            pass
    return out.is_file() and out.stat().st_size > 2048


class MomentTracker:
    """Samples live gameplay frames on `:0` (`gamescopectl` or ArmadaOS `x11grab`) into a 6-frame tmpfs ring buffer
    and commits only a real non-menu gameplay moment into `~/.local/state/tandem/moments/<gid>.jpg`."""
    def __init__(self, state_dir):
        self.moments_dir = Path(state_dir) / 'moments'
        self._lock = threading.Lock()
        self._sessions = {}

    def moment_path(self, gid):
        p = self.moments_dir / f'{gid}.jpg'
        return str(p) if p.is_file() else None

    def start(self, tandem_obj, gid):
        if getattr(tandem_obj, 'dry', False) or not (shutil.which('gamescopectl') or shutil.which('ffmpeg') or shutil.which('import')):
            return
        rt_dir = os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'
        work_dir = Path(rt_dir) / 'tandem-snaps' / re.sub(r'[^a-zA-Z0-9_-]', '_', gid)
        shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        sess = {'gid': gid, 'work_dir': work_dir, 'entries': [], 'committed': None, 'active': True}
        with self._lock:
            self._sessions[gid] = sess
        threading.Thread(target=self._loop, args=(tandem_obj, sess), daemon=True).start()

    def _capture_once(self, out_png):
        return capture_screen_frame(out_png, display=os.environ.get('DISPLAY') or ':0')

    def snapshot_now(self, gid):
        """Grab one immediate frame right before pause/quit if the session has no non-menu frame yet (for Game Switcher)."""
        with self._lock:
            sess = self._sessions.get(gid)
            if not sess or not sess.get('active'):
                return False
            if any(not e.get('is_menu') and e.get('score', 0) >= 0.40 for e in sess.get('entries', ())):
                return True
            raw_png = sess['work_dir'] / 'snap-switch.png'
        if not self._capture_once(raw_png):
            return False
        info = score_gameplay_frame(raw_png)
        if info['is_menu'] or info['score'] < 0.32:
            return False
        with self._lock:
            if sess.get('active'):
                sess['entries'].append({'path': str(raw_png), 'at': time.time() - 30.0,
                                        'score': info['score'], 'is_menu': False, 'motion': 2.5})
        return True

    def _loop(self, tandem_obj, sess):
        gid = sess['gid']
        # Skip the first 14 seconds (boot logos / BIOS splash)
        for _ in range(14):
            time.sleep(1.0)
            if not sess['active'] or not tandem_obj.run or tandem_obj.run.get('id') != gid:
                return
        slot = 0
        last_fp = b''
        prev_good = None
        while sess['active']:
            run = tandem_obj.run
            if not run or run.get('id') != gid:
                return
            if not run.get('paused') and not run.get('quitting'):
                raw_png = sess['work_dir'] / f'ring-{slot % 6}.png'
                if self._capture_once(raw_png):
                    now = time.time()
                    info = score_gameplay_frame(raw_png)
                    mot = frame_motion_diff(last_fp, info.get('fp') or b'')
                    if info.get('fp'):
                        last_fp = info['fp']
                    entry = {'path': str(raw_png), 'at': now, 'score': info['score'],
                             'is_menu': info['is_menu'], 'motion': round(mot, 2)}
                    with self._lock:
                        # Keep only entries whose ring slot was not overwritten
                        sess['entries'] = [e for e in sess['entries'] if e['path'] != str(raw_png)]
                        sess['entries'].append(entry)
                        # Promote the PREVIOUS good moving gameplay frame to committed anchor (so even 5+ minutes
                        # inside a pause/save menu never clobbers the last real world scene!)
                        if not entry['is_menu'] and entry['score'] >= 0.44:
                            if prev_good and Path(prev_good['path']).is_file():
                                anchor_png = sess['work_dir'] / 'committed.png'
                                try:
                                    shutil.copy2(prev_good['path'], anchor_png)
                                    sess['committed'] = {**prev_good, 'path': str(anchor_png)}
                                except OSError:
                                    pass
                            if mot >= 2.2 or prev_good is None:
                                prev_good = dict(entry)
                    slot += 1
            for _ in range(20):
                time.sleep(1.0)
                if not sess['active'] or not tandem_obj.run or tandem_obj.run.get('id') != gid:
                    return

    def finish(self, gid):
        with self._lock:
            sess = self._sessions.pop(gid, None)
            if not sess:
                return None
            sess['active'] = False
            pool = list(sess['entries'])
            if sess.get('committed'):
                pool.append(sess['committed'])
        try:
            winner = pick_best_moment(pool, quit_at=time.time(), min_pre_quit_secs=25.0)
            if not winner or not Path(winner['path']).is_file():
                return None
            self.moments_dir.mkdir(parents=True, exist_ok=True)
            dest = self.moments_dir / f'{gid}.jpg'
            tmp_dest = self.moments_dir / f'.tmp-{gid}.jpg'
            saved_ok = False
            try:
                from PySide6.QtGui import QImage
                img = QImage(winner['path'])
                if not img.isNull():
                    saved_ok = bool(img.save(str(tmp_dest), 'JPG', 92))
            except Exception:
                saved_ok = False
            if not saved_ok and shutil.which('ffmpeg'):
                r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', winner['path'], '-q:v', '2', str(tmp_dest)],
                                   capture_output=True, timeout=10)
                saved_ok = (r.returncode == 0 and tmp_dest.is_file())
            if saved_ok and tmp_dest.is_file():
                os.replace(tmp_dest, dest)
                return str(dest)
            tmp_dest.unlink(missing_ok=True)
            return None
        finally:
            shutil.rmtree(sess['work_dir'], ignore_errors=True)



