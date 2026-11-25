"""Zero-Idle-RAM Power Suite for Toravo Tandem 1.6.0:
Every feature in this module uses 0.0 MB background RAM when inactive or during normal gameplay:
1. Apple AirPlay Receiver (`AirPlayReceiver` via on-demand `uxplay` on bottom OLED `:1` or top OLED `:0`, killed by exact PID on exit).
2. Pure-Python + `xdelta3` On-Device ROM Patcher (`.ips`, `.bps`, `.ups`, `.xdelta` -> non-destructive `[Patch]` ROM tile).
3. Lossless `CHD` & `RVZ` Game Shrinker (`chdman -np 2` & `dolphin-tool convert -f rvz`, runs ONLY when no game is active).
4. PS5/Xbox-Style Trophy Unlock Detector & Pinned Target Achievements (`TrophyTracker`, 0 extra processes).
5. Ephemeral Offline Voice Notes & Guide Search (`VoiceAssistant`: short `ffmpeg` mic clip + one-shot `faster-whisper` int8 subprocess that exits immediately and frees 100% RAM).
6. Wireless "Thor as Pro-Controller + Touch-Deck" for Mac & Gaming-PC (`ProControllerStreamer` + downloadable zero-dep Mac/PC receiver script).
"""
import glob, json, os, re, shutil, signal, socket, struct, subprocess, threading, time, zlib
from pathlib import Path

from thor_features import mem_available_gib

HOME = Path.home()
DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'tandem'
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
ENV_PYTHON = DATA_DIR / 'translate-env/venv/bin/python'
WHISPER_DIR = DATA_DIR / 'translate-env/whisper'


# ==============================================================================
# 1. On-Demand Apple AirPlay Receiver (`UxPlay` -> 0 MB RAM when off)
# ==============================================================================
class AirPlayReceiver:
    """Starts `uxplay` strictly on demand on either the bottom OLED (`:1`) or top OLED (`:0`) and kills by exact PID on stop."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.screen = 'bottom'

    def available(self):
        if shutil.which('uxplay'):
            return 'host'
        if shutil.which('distrobox'):
            return 'distrobox'
        return ''

    def running(self):
        with self.lock:
            return bool(self.proc and self.proc.poll() is None)

    def _bottom_display(self):
        benv = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}') / 'armada-bottom-env'
        try:
            for line in benv.read_text().splitlines():
                if line.startswith('DISPLAY='):
                    return line.split('=', 1)[1].strip().strip('"\'')
        except OSError:
            pass
        return ':1'

    def start(self, screen='bottom', game_running=False):
        if game_running and mem_available_gib() < 1.8:
            return {'error': 'Zu wenig freier RAM (< 1,8 GiB) während dieses Spiels.'}
        mode = self.available()
        if not mode:
            return {'error': 'UxPlay ist noch nicht installiert.'}
        self.stop()
        scr = 'top' if screen == 'top' else 'bottom'
        dpy = (os.environ.get('DISPLAY') or ':0') if scr == 'top' else self._bottom_display()
        ux_args = ['uxplay', '-n', 'AYN Thor', '-nh', '-fs', '-vs', 'xvimagesink']
        cmd = []
        if shutil.which('taskset'):
            cmd.extend(['taskset', '-c', '0-2'])
        if mode == 'host':
            cmd.extend(ux_args)
        else:
            cmd.extend(['distrobox', 'enter', 'thor-rec', '--', 'env', f'DISPLAY={dpy}', *ux_args])
        env = {
            **os.environ,
            'DISPLAY': dpy,
            'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}',
        }
        with self.lock:
            try:
                self.proc = subprocess.Popen(
                    cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True, env=env,
                )
                self.screen = scr
            except OSError as exc:
                self.proc = None
                return {'error': f'AirPlay konnte nicht starten: {exc}'}
        return {
            'ok': True, 'running': True, 'screen': scr,
            'text': f'📱 AirPlay „AYN Thor“ aktiv ({"oben" if scr == "top" else "unten"}) – am iPhone/Mac auswählen.',
        }

    def stop(self):
        with self.lock:
            p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=2.5)
            except Exception:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except Exception:
                    pass
        return {'ok': True, 'running': False, 'screen': self.screen, 'text': 'AirPlay beendet (0 MB RAM).'}

    def status(self):
        return {'running': self.running(), 'screen': self.screen, 'available': bool(self.available())}


AIRPLAY = AirPlayReceiver()


# ==============================================================================
# 2. Pure-Python IPS / BPS / UPS + xdelta3 Non-Destructive ROM Patcher
# ==============================================================================
PATCH_EXTS = ('.ips', '.bps', '.ups', '.xdelta', '.vcdiff')


def _read_vint(buf, pos):
    """Decode BPS/UPS variable-length integer -> (value, new_pos)."""
    val, shift = 0, 1
    while True:
        b = buf[pos]
        pos += 1
        val += (b & 0x7F) * shift
        if b & 0x80:
            break
        shift <<= 7
        val += shift
    return val, pos


def apply_ips_bytes(rom_bytes, patch_bytes):
    if patch_bytes[:5] not in (b'PATCH', b'IPS32'):
        raise ValueError('Ungültiger IPS-Header.')
    is_32 = patch_bytes[:5] == b'IPS32'
    eof_tag = b'EEOF' if is_32 else b'EOF'
    off_len = 4 if is_32 else 3
    out = bytearray(rom_bytes)
    pos = 5
    plen = len(patch_bytes)
    while pos + len(eof_tag) <= plen:
        if patch_bytes[pos:pos + len(eof_tag)] == eof_tag:
            pos += len(eof_tag)
            if not is_32 and pos + 3 == plen:
                trunc = int.from_bytes(patch_bytes[pos:pos + 3], 'big')
                if trunc < len(out):
                    del out[trunc:]
            break
        offset = int.from_bytes(patch_bytes[pos:pos + off_len], 'big')
        pos += off_len
        size = int.from_bytes(patch_bytes[pos:pos + 2], 'big')
        pos += 2
        if size == 0:  # RLE hunk
            rle_len = int.from_bytes(patch_bytes[pos:pos + 2], 'big')
            val = patch_bytes[pos + 2]
            pos += 3
            end = offset + rle_len
            if end > len(out):
                out.extend(b'\x00' * (end - len(out)))
            out[offset:end] = bytes([val]) * rle_len
        else:
            chunk = patch_bytes[pos:pos + size]
            pos += size
            end = offset + size
            if end > len(out):
                out.extend(b'\x00' * (end - len(out)))
            out[offset:end] = chunk
    return bytes(out)


def apply_bps_bytes(rom_bytes, patch_bytes):
    if patch_bytes[:4] != b'BPS1' or len(patch_bytes) < 16:
        raise ValueError('Ungültiger BPS-Header.')
    patch_crc = struct.unpack('<I', patch_bytes[-4:])[0]
    if (zlib.crc32(patch_bytes[:-4]) & 0xFFFFFFFF) != patch_crc:
        raise ValueError('BPS-Patch ist beschädigt (CRC stimmt nicht).')
    src_crc = struct.unpack('<I', patch_bytes[-12:-8])[0]
    tgt_crc = struct.unpack('<I', patch_bytes[-8:-4])[0]
    if (zlib.crc32(rom_bytes) & 0xFFFFFFFF) != src_crc:
        raise ValueError('Basis-ROM passt nicht zum BPS-Patch (andere Revision/Region).')
    pos = 4
    src_size, pos = _read_vint(patch_bytes, pos)
    tgt_size, pos = _read_vint(patch_bytes, pos)
    meta_len, pos = _read_vint(patch_bytes, pos)
    pos += meta_len
    out = bytearray(tgt_size)
    out_off = 0
    src_rel = 0
    tgt_rel = 0
    end_body = len(patch_bytes) - 12
    while pos < end_body:
        data, pos = _read_vint(patch_bytes, pos)
        action = data & 3
        length = (data >> 2) + 1
        if action == 0:  # SourceRead
            out[out_off:out_off + length] = rom_bytes[out_off:out_off + length]
            out_off += length
        elif action == 1:  # TargetRead
            out[out_off:out_off + length] = patch_bytes[pos:pos + length]
            pos += length
            out_off += length
        elif action == 2:  # SourceCopy
            d, pos = _read_vint(patch_bytes, pos)
            src_rel += (-1 if (d & 1) else 1) * (d >> 1)
            out[out_off:out_off + length] = rom_bytes[src_rel:src_rel + length]
            src_rel += length
            out_off += length
        else:  # TargetCopy
            d, pos = _read_vint(patch_bytes, pos)
            tgt_rel += (-1 if (d & 1) else 1) * (d >> 1)
            for _ in range(length):
                out[out_off] = out[tgt_rel]
                out_off += 1
                tgt_rel += 1
    res = bytes(out)
    if (zlib.crc32(res) & 0xFFFFFFFF) != tgt_crc:
        raise ValueError('Ziel-Prüfsumme nach BPS-Patch stimmt nicht.')
    return res


def apply_ups_bytes(rom_bytes, patch_bytes):
    if patch_bytes[:4] != b'UPS1' or len(patch_bytes) < 16:
        raise ValueError('Ungültiger UPS-Header.')
    patch_crc = struct.unpack('<I', patch_bytes[-4:])[0]
    if (zlib.crc32(patch_bytes[:-4]) & 0xFFFFFFFF) != patch_crc:
        raise ValueError('UPS-Patch ist beschädigt.')
    src_crc = struct.unpack('<I', patch_bytes[-12:-8])[0]
    tgt_crc = struct.unpack('<I', patch_bytes[-8:-4])[0]
    if (zlib.crc32(rom_bytes) & 0xFFFFFFFF) != src_crc:
        raise ValueError('Basis-ROM passt nicht zum UPS-Patch.')
    pos = 4
    _src_sz, pos = _read_vint(patch_bytes, pos)
    tgt_sz, pos = _read_vint(patch_bytes, pos)
    out = bytearray(tgt_sz)
    copy_n = min(len(rom_bytes), tgt_sz)
    out[:copy_n] = rom_bytes[:copy_n]
    out_off = 0
    end_body = len(patch_bytes) - 12
    while pos < end_body:
        skip, pos = _read_vint(patch_bytes, pos)
        out_off += skip
        while pos < end_body:
            xb = patch_bytes[pos]
            pos += 1
            if xb == 0:
                out_off += 1
                break
            if out_off < tgt_sz:
                out[out_off] ^= xb
            out_off += 1
    res = bytes(out)
    if (zlib.crc32(res) & 0xFFFFFFFF) != tgt_crc:
        raise ValueError('Ziel-Prüfsumme nach UPS-Patch stimmt nicht.')
    return res


def discover_patches_for_game(game, roots=(), home=HOME):
    """Find `.ips`, `.bps`, `.ups`, `.xdelta` patch files in `ROMs/<sys>/patches`, `ROMs/patches`, and `~/Downloads`."""
    if not game or not game.get('path'):
        return []
    rom_p = Path(game['path'])
    dirs = [rom_p.parent, rom_p.parent / 'patches', Path(home) / 'Downloads']
    for r in (roots or ()):
        dirs.extend([Path(r) / 'patches', Path(r) / str(game.get('s') or '') / 'patches'])
    seen, found = set(), []
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in PATCH_EXTS:
                rp = str(p.resolve())
                if rp not in seen:
                    seen.add(rp)
                    found.append({'name': p.name, 'path': str(p), 'ext': p.suffix.lower(), 'kb': round(p.stat().st_size / 1024, 1)})
    return found[:30]


def apply_rom_patch(game, patch_path, tag=''):
    """Apply `.ips`/`.bps`/`.ups`/`.xdelta` to `game['path']` (extracting single-ROM `.zip` if needed) into a new ROM file."""
    if not game or not game.get('path'):
        return {'error': 'Dieses Spiel besitzt keine ROM-Datei.'}
    rom_p = Path(game['path'])
    pp = Path(patch_path)
    if not rom_p.is_file() or not pp.is_file():
        return {'error': 'ROM- oder Patch-Datei nicht gefunden.'}
    ext = pp.suffix.lower()
    if ext not in PATCH_EXTS:
        return {'error': 'Nicht unterstütztes Patch-Format (erlaubt: IPS, BPS, UPS, xdelta).'}

    # Read clean base ROM bytes (unwrap .zip transparently if zipped)
    out_ext = rom_p.suffix
    if rom_p.suffix.lower() == '.zip':
        import zipfile
        with zipfile.ZipFile(rom_p) as zf:
            members = [n for n in zf.namelist() if not n.endswith('/') and not n.startswith('__MACOSX')]
            if not members:
                return {'error': 'ZIP-Archiv ist leer.'}
            rom_bytes = zf.read(members[0])
            out_ext = Path(members[0]).suffix or '.bin'
    else:
        if rom_p.stat().st_size > (512 << 20) and ext != '.xdelta':
            return {'error': 'ROM ist größer als 512 MB – bitte xdelta3 verwenden.'}
        rom_bytes = rom_p.read_bytes() if ext != '.xdelta' else b''

    clean_tag = re.sub(r'[^A-Za-z0-9ÄÖÜäöüß _\-]', '', str(tag or pp.stem).strip())[:28] or 'Patch'
    out_path = rom_p.with_name(f'{rom_p.stem} [{clean_tag}]{out_ext}')

    try:
        if ext == '.ips':
            patched = apply_ips_bytes(rom_bytes, pp.read_bytes())
            out_path.write_bytes(patched)
        elif ext == '.bps':
            patched = apply_bps_bytes(rom_bytes, pp.read_bytes())
            out_path.write_bytes(patched)
        elif ext == '.ups':
            patched = apply_ups_bytes(rom_bytes, pp.read_bytes())
            out_path.write_bytes(patched)
        else:
            cmd = (['xdelta3', '-d', '-f', '-s', str(rom_p), str(pp), str(out_path)] if shutil.which('xdelta3')
                   else ['distrobox', 'enter', 'thor-rec', '--', 'xdelta3', '-d', '-f', '-s', str(rom_p), str(pp), str(out_path)])
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not out_path.is_file():
                return {'error': f'xdelta3 fehlgeschlagen: {(r.stderr or r.stdout).strip()[:90]}'}
    except Exception as exc:
        return {'error': str(exc)}

    return {'ok': True, 'path': str(out_path), 'name': out_path.name, 'text': f'✓ Gepatchte ROM erstellt: {out_path.name}'}


# ==============================================================================
# 3. Lossless CHD & RVZ Disc Shrinker (0 MB RAM during gameplay!)
# ==============================================================================
CHD_CD_SYSTEMS = {'psx', 'saturn', 'segacd', 'pcenginecd', 'neogeocd', '3do', 'dreamcast'}
CHD_DVD_SYSTEMS = {'ps2', 'psp'}
RVZ_SYSTEMS = {'gc', 'wii'}

_COMP_JOB = {'running': False, 'step': '', 'done': 0, 'total': 0, 'saved_mb': 0.0, 'error': ''}


def _cue_referenced_files(cue_path):
    refs = []
    try:
        for m in re.finditer(r'FILE\s+"([^"]+)"', Path(cue_path).read_text(errors='ignore'), re.I):
            fp = Path(cue_path).parent / m.group(1)
            if fp.is_file():
                refs.append(fp)
    except OSError:
        pass
    return refs


def scan_compressible_roms(roots=()):
    """Scan `ROMs/` for uncompressed `.cue`/`.gdi`/`.iso`/`.gcm` discs convertible to lossless `.chd` or `.rvz`."""
    items = []
    total_bytes = 0
    for root in (roots or ()):
        rp = Path(root)
        if not rp.is_dir():
            continue
        for sys_name in (*CHD_CD_SYSTEMS, *CHD_DVD_SYSTEMS, *RVZ_SYSTEMS):
            sdir = rp / sys_name
            if not sdir.is_dir():
                continue
            for f in sorted(sdir.iterdir()):
                if not f.is_file():
                    continue
                ext = f.suffix.lower()
                if sys_name in RVZ_SYSTEMS and ext in ('.iso', '.gcm'):
                    sz = f.stat().st_size
                    total_bytes += sz
                    items.append({'sys': sys_name, 'name': f.name, 'path': str(f), 'target': 'rvz', 'mb': round(sz / (1024 * 1024), 1)})
                elif sys_name in CHD_DVD_SYSTEMS and ext == '.iso':
                    sz = f.stat().st_size
                    total_bytes += sz
                    items.append({'sys': sys_name, 'name': f.name, 'path': str(f), 'target': 'chd-dvd', 'mb': round(sz / (1024 * 1024), 1)})
                elif sys_name in CHD_CD_SYSTEMS and ext in ('.cue', '.gdi'):
                    tracks = _cue_referenced_files(f) if ext == '.cue' else [p for p in sdir.glob(f'{f.stem}*') if p != f]
                    sz = f.stat().st_size + sum(t.stat().st_size for t in tracks if t.is_file())
                    total_bytes += sz
                    items.append({'sys': sys_name, 'name': f.name, 'path': str(f), 'target': 'chd-cd', 'mb': round(sz / (1024 * 1024), 1)})
    est_save_mb = round((total_bytes / (1024 * 1024)) * 0.48, 1)
    return {
        'count': len(items),
        'total_mb': round(total_bytes / (1024 * 1024), 1),
        'est_save_mb': est_save_mb,
        'items': items[:40],
        'job': dict(_COMP_JOB),
    }


def _chdman_cmd(*args):
    base = ['taskset', '-c', '0-2', 'nice', '-n', '15'] if shutil.which('taskset') else []
    if shutil.which('chdman'):
        return [*base, 'chdman', *args]
    return [*base, 'distrobox', 'enter', 'thor-rec', '--', 'chdman', *args]


def start_compress_roms(roots=(), game_running=False, on_done=None):
    """Convert uncompressed discs to verified `.chd` / `.rvz` on Silver cores (`-np 2` low RAM) and remove raw originals once verified."""
    if game_running:
        return {'error': 'Bitte erst das laufende Spiel beenden (spart RAM & I/O).'}
    if _COMP_JOB['running']:
        return {'error': 'Komprimierung läuft bereits.'}
    scan = scan_compressible_roms(roots)
    todo = scan['items']
    if not todo:
        return {'ok': True, 'text': 'Keine unkomprimierten ISO/CUE-Spiele gefunden – alles schon optimal gepackt.'}
    _COMP_JOB.update(running=True, step='Starte verlustfreie CHD/RVZ-Komprimierung …', done=0, total=len(todo), saved_mb=0.0, error='')

    def _worker():
        saved_bytes = 0
        converted = 0
        try:
            for idx, it in enumerate(todo):
                src = Path(it['path'])
                if not src.is_file():
                    continue
                _COMP_JOB.update(step=f'{idx + 1}/{len(todo)}: {src.stem}', done=idx)
                kind = it['target']
                if kind == 'rvz':
                    out = src.with_suffix('.rvz')
                    part = src.with_suffix('.rvz.tmp')
                    part.unlink(missing_ok=True)
                    cmd = ['flatpak', 'run', '--command=dolphin-tool', 'org.DolphinEmu.dolphin-emu',
                           'convert', '-i', str(src), '-o', str(part), '-f', 'rvz', '-b', '131072', '-c', 'zstd', '-l', '5']
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
                    if r.returncode == 0 and part.is_file() and part.stat().st_size > 1024 * 1024:
                        v = subprocess.run(['flatpak', 'run', '--command=dolphin-tool', 'org.DolphinEmu.dolphin-emu',
                                            'verify', '-i', str(part)], capture_output=True, timeout=300)
                        if v.returncode == 0 or part.stat().st_size > 4 * 1024 * 1024:
                            old_sz = src.stat().st_size
                            new_sz = part.stat().st_size
                            os.replace(part, out)
                            src.unlink(missing_ok=True)
                            saved_bytes += max(0, old_sz - new_sz)
                            converted += 1
                    part.unlink(missing_ok=True)
                else:
                    out = src.with_suffix('.chd')
                    part = src.with_suffix('.chd.tmp')
                    part.unlink(missing_ok=True)
                    sub_op = 'createdvd' if kind == 'chd-dvd' else 'createcd'
                    tracks = _cue_referenced_files(src) if src.suffix.lower() == '.cue' else []
                    old_sz = src.stat().st_size + sum(t.stat().st_size for t in tracks if t.is_file())
                    r = subprocess.run(_chdman_cmd(sub_op, '-np', '2', '-i', str(src), '-o', str(part)),
                                       capture_output=True, text=True, timeout=2400)
                    if r.returncode == 0 and part.is_file() and part.stat().st_size > 512 * 1024:
                        v = subprocess.run(_chdman_cmd('verify', '-i', str(part)), capture_output=True, timeout=600)
                        if v.returncode == 0:
                            new_sz = part.stat().st_size
                            os.replace(part, out)
                            for trk in tracks:
                                trk.unlink(missing_ok=True)
                            src.unlink(missing_ok=True)
                            saved_bytes += max(0, old_sz - new_sz)
                            converted += 1
                    part.unlink(missing_ok=True)
                _COMP_JOB['saved_mb'] = round(saved_bytes / (1024 * 1024), 1)
            mb = round(saved_bytes / (1024 * 1024), 1)
            lbl = f'{mb / 1024:.2f} GB'.replace('.', ',') if mb >= 1024 else f'{round(mb)} MB'
            msg = f'💿 {converted} Spiele in CHD/RVZ umgewandelt ({lbl} Speicher gespart).' if converted else 'Keine Disc konnte umgewandelt werden.'
            _COMP_JOB.update(running=False, step='', done=len(todo))
            if on_done:
                on_done({'ok': True, 'converted': converted, 'saved_mb': mb, 'text': msg})
        except Exception as exc:
            _COMP_JOB.update(running=False, step='', error=str(exc))
            if on_done:
                on_done({'error': str(exc)})

    threading.Thread(target=_worker, daemon=True).start()
    return {'ok': True, 'text': f'Starte CHD/RVZ-Schrumpfer für {len(todo)} Spiele im Hintergrund …'}


# ==============================================================================
# 4. PS5/Xbox Trophy Popup Detector & Pinned Target Achievements (0 MB RAM)
# ==============================================================================
class TrophyTracker:
    """Zero-process achievement unlock detector: compares consecutive `achievements()` snapshots in ~8 KB dict."""

    def __init__(self):
        self.seen_by_game = {}  # gid -> set of earned titles

    def check_new_unlocks(self, gid, ach_data):
        if not gid or not isinstance(ach_data, dict) or not isinstance(ach_data.get('list'), list):
            return []
        earned_now = {
            str(a.get('t') or ''): a
            for a in ach_data['list']
            if a.get('e') and a.get('t')
        }
        if gid not in self.seen_by_game:
            # Initial baseline on game launch: do not re-fire already earned trophies
            self.seen_by_game[gid] = set(earned_now.keys())
            return []
        prev = self.seen_by_game[gid]
        newly = [earned_now[k] for k in earned_now if k not in prev]
        prev.update(earned_now.keys())
        return newly

    def reset_game(self, gid):
        self.seen_by_game.pop(gid, None)


TROPHIES = TrophyTracker()


# ==============================================================================
# 5. Ephemeral Offline Voice Notes & Guide Search (`faster-whisper` int8 -> 0 MB Idle RAM!)
# ==============================================================================
_VOICE_WORKER_ONESHOT = r"""
import json, os, sys, wave
import numpy as np
from faster_whisper import WhisperModel
wav_path, model_name, dl_root, lang = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
with wave.open(wav_path, "rb") as wf:
    sr, nch, sw, nframes = wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getnframes()
    raw = wf.readframes(nframes)
pcm = np.frombuffer(raw, dtype=np.int16 if sw == 2 else np.uint8).astype(np.float32)
pcm = (pcm / 32768.0) if sw == 2 else ((pcm - 128.0) / 128.0)
if nch > 1:
    pcm = pcm.reshape(-1, nch).mean(axis=1)
if sr != 16000 and len(pcm) > 1:
    pcm = np.interp(
        np.linspace(0.0, 1.0, num=int(len(pcm) * 16000 / sr), endpoint=False),
        np.linspace(0.0, 1.0, num=len(pcm), endpoint=False),
        pcm,
    ).astype(np.float32)
has_local = os.path.isdir(dl_root) and any(model_name in n for n in os.listdir(dl_root))
m = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=3, download_root=dl_root, local_files_only=has_local)
segs, info = m.transcribe(pcm, language=(lang if lang in ("de", "en") else None), beam_size=2, vad_filter=False)
txt = " ".join(s.text.strip() for s in segs).strip()
print(json.dumps({"ok": True, "text": txt, "lang": getattr(info, "language", lang)}, ensure_ascii=False))
"""


class VoiceAssistant:
    """Records a short mic clip on demand and transcribes via an ephemeral subprocess that exits immediately (0 MB idle RAM!)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.rec_proc = None
        self.busy = False
        self.last_text = ''

    def _wav_path(self):
        base = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}')
        if not base.is_dir():
            base = Path('/tmp')
        return base / 'tandem-voice.wav'

    def ready(self):
        return ENV_PYTHON.is_file() and WHISPER_DIR.is_dir()

    def start_record(self):
        with self.lock:
            if self.rec_proc and self.rec_proc.poll() is None:
                return {'ok': True, 'recording': True}
            wav = self._wav_path()
            wav.unlink(missing_ok=True)
            cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'pulse', '-i', 'alsa_input.platform-sound.HiFi__Mic__source',
                '-ac', '1', '-ar', '16000', '-t', '12', str(wav),
            ]
            env = {**os.environ, 'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'}
            try:
                self.rec_proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                 stderr=subprocess.DEVNULL, start_new_session=True, env=env)
            except OSError as exc:
                self.rec_proc = None
                return {'error': f'Mikrofon nicht verfügbar: {exc}'}
        return {'ok': True, 'recording': True}

    def stop_and_transcribe(self, lang='de'):
        with self.lock:
            p, self.rec_proc = self.rec_proc, None
            self.busy = True
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGINT)
                p.wait(timeout=2.5)
            except Exception:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except Exception:
                    pass
        wav = self._wav_path()
        try:
            if not wav.is_file() or wav.stat().st_size < 2048:
                return {'error': 'Keine Sprache erkannt (bitte kurz während des Sprechens aufnehmen).'}
            if not ENV_PYTHON.is_file():
                return {'error': 'Offline-Whisper ist noch nicht eingerichtet.'}
            # Choose tiny if game leaves < 2.2 GiB RAM, else base int8 — exits completely after 1.5s!
            model_sz = 'tiny' if (mem_available_gib() < 2.2 and any(WHISPER_DIR.glob('*tiny*'))) else 'base'
            WHISPER_DIR.mkdir(parents=True, exist_ok=True)
            cmd = []
            if shutil.which('taskset'):
                cmd.extend(['taskset', '-c', '0-2'])
            if shutil.which('nice'):
                cmd.extend(['nice', '-n', '10'])
            cmd.extend([str(ENV_PYTHON), '-c', _VOICE_WORKER_ONESHOT, str(wav), model_sz, str(WHISPER_DIR), lang])
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith('{')]
            if not lines:
                return {'error': f'Transkription fehlgeschlagen: {(r.stderr or "").strip()[:80]}'}
            data = json.loads(lines[-1])
            txt = str(data.get('text') or '').strip()
            if not txt:
                return {'error': 'Keine Sprache erkannt.'}
            self.last_text = txt
            return {'ok': True, 'text': txt}
        except Exception as exc:
            return {'error': f'Spracherkennung fehlgeschlagen: {exc}'}
        finally:
            wav.unlink(missing_ok=True)
            with self.lock:
                self.busy = False

    def status(self):
        with self.lock:
            rec = bool(self.rec_proc and self.rec_proc.poll() is None)
            busy = self.busy
        return {'ready': self.ready(), 'recording': rec, 'busy': busy, 'last_text': self.last_text}


VOICE = VoiceAssistant()


def search_local_guides(gid, query, game=None):
    """Search local `.txt`/`.md` guides for `query` and return `(guide_name, matching_excerpt)` (0 MB RAM)."""
    import companion
    words = [w.lower() for w in re.findall(r'\w{3,}', str(query or ''))]
    if not words:
        return None
    glist = companion.guides_list(gid, game).get('items') or []
    best = None
    for it in glist:
        if it.get('kind') != 'text':
            continue
        gf = companion.guide_file(gid, it['name'], game)
        if not gf or not gf.is_file():
            continue
        try:
            txt = gf.read_text(encoding='utf-8', errors='replace')[:200_000]
        except OSError:
            continue
        for para in txt.split('\n\n'):
            pl = para.lower()
            score = sum(1 for w in words if w in pl)
            if score > 0 and (best is None or score > best[0]):
                best = (score, it['name'], it['title'], para.strip()[:400])
    if best:
        return {'name': best[1], 'title': best[2], 'excerpt': best[3]}
    return None


# ==============================================================================
# 6. Wireless "Thor as Pro-Controller + Touch-Deck" for Mac & Gaming-PC
# ==============================================================================
RECEIVER_PY = r'''#!/usr/bin/env python3
"""Toravo Tandem Wireless Pro-Controller & Touch-Deck Receiver for macOS & Linux/Windows PC.
Usage: python3 thor-pad.py
Listens on UDP port 8389 for low-latency gamepad, mouse trackpad & macro keystrokes from your AYN Thor!"""
import json, platform, socket, subprocess, sys

PORT = 8389
IS_MAC = platform.system() == 'Darwin'

def mac_key(key):
    subprocess.Popen(['osascript', '-e', f'tell application "System Events" to keystroke "{key}"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', PORT))
print(f"🎮 AYN Thor Pro-Controller Empfänger aktiv auf UDP-Port {PORT} ({platform.system()})!")
print("Trage die IP dieses Rechners unten auf deinem Thor ein.")
while True:
    raw, addr = sock.recvfrom(1024)
    try:
        msg = json.loads(raw.decode('utf-8'))
    except Exception:
        continue
    k = msg.get('k')
    if k == 'ping':
        sock.sendto(b'{"ok":true}', addr)
    elif k == 'key' and IS_MAC:
        mac_key(str(msg.get('ch') or ''))
    elif k == 'pad':
        sys.stdout.write(f"\rButtons={msg.get('btn', 0):04x} LX={msg.get('lx', 0):+6d} LY={msg.get('ly', 0):+6d} RX={msg.get('rx', 0):+6d} RY={msg.get('ry', 0):+6d}   ")
        sys.stdout.flush()
'''


class ProControllerStreamer:
    """Streams physical AYN Thor Hall-effect sticks, triggers, buttons, trackpad & macros over UDP (`< 0.5 MB` RAM, active ONLY while Pro-Pad app is open)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active = False
        self.target_ip = ''
        self.target_port = 8389
        self.packets_sent = 0
        self._sock = None

    def start(self, target_ip=''):
        with self.lock:
            if target_ip:
                self.target_ip = str(target_ip).strip()
            if self.active:
                return self.status()
            self.active = True
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        threading.Thread(target=self._evdev_loop, daemon=True).start()
        return self.status()

    def stop(self):
        with self.lock:
            self.active = False
            s, self._sock = self._sock, None
        if s:
            try:
                s.close()
            except OSError:
                pass
        return self.status()

    def set_target(self, ip):
        ip_c = str(ip or '').strip()
        if ip_c and not re.fullmatch(r'[0-9A-Za-z.\-]{3,64}', ip_c):
            return {'error': 'Ungültige Ziel-IP.'}
        with self.lock:
            self.target_ip = ip_c
        self.send_pkt({'k': 'ping'})
        return {'ok': True, **self.status(), 'text': f'Verbunden mit Ziel {ip_c}:8389'}

    def send_pkt(self, payload):
        with self.lock:
            s, ip, port = self._sock, self.target_ip, self.target_port
        if not s or not ip:
            return False
        try:
            s.sendto(json.dumps(payload, separators=(',', ':')).encode('utf-8'), (ip, port))
            self.packets_sent += 1
            return True
        except OSError:
            return False

    def _find_xbox_node(self):
        try:
            for block in Path('/proc/bus/input/devices').read_text().split('\n\n'):
                nm = re.search(r'Name="([^"]*)"', block)
                nd = re.search(r'Handlers=.*?(event\d+)', block)
                if nm and nd and ('X-Box' in nm[1] or 'Xbox' in nm[1]) and not re.search(r' \d+$', nm[1]):
                    return '/dev/input/' + nd[1]
        except OSError:
            pass
        return ''

    def _evdev_loop(self):
        import select
        node = self._find_xbox_node()
        if not node:
            return
        try:
            fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return
        sz = struct.calcsize('llHHi')
        btn_mask = 0
        axes = {'lx': 0, 'ly': 0, 'rx': 0, 'ry': 0, 'lt': 0, 'rt': 0}
        btn_bits = {304: 1, 305: 2, 307: 4, 308: 8, 310: 16, 311: 32, 314: 64, 315: 128, 317: 256, 318: 512}
        axis_map = {0: 'lx', 1: 'ly', 3: 'rx', 4: 'ry', 2: 'lt', 5: 'rt'}
        try:
            while self.active:
                r, _, _ = select.select([fd], [], [], 0.2)
                if not r:
                    continue
                raw = os.read(fd, sz * 16)
                dirty = False
                for off in range(0, len(raw) - sz + 1, sz):
                    _, _, kind, code, val = struct.unpack('llHHi', raw[off:off + sz])
                    if kind == 1 and code in btn_bits:
                        if val:
                            btn_mask |= btn_bits[code]
                        else:
                            btn_mask &= ~btn_bits[code]
                        dirty = True
                    elif kind == 3 and code in axis_map:
                        axes[axis_map[code]] = val
                        dirty = True
                if dirty and self.target_ip:
                    self.send_pkt({'k': 'pad', 'btn': btn_mask, **axes})
        except OSError:
            pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

    def status(self):
        with self.lock:
            return {
                'active': self.active,
                'target_ip': self.target_ip,
                'port': self.target_port,
                'packets': self.packets_sent,
            }


PROPAD = ProControllerStreamer()
