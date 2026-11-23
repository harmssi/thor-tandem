"""Live hardware telemetry, PipeWire per-stream audio mixer, USB-C dock state, and Wake-on-LAN for Toravo Tandem.
Standard library + wpctl/mpv IPC only; safe on systems without battery/DRM sysfs (returns None/empty cleanly)."""
import glob, json, os, re, shutil, socket, subprocess, threading, time
from collections import deque
from pathlib import Path

import thor

BGM_SOCKET = Path(f'/tmp/tandem-bgm-{os.getuid()}.sock')
LOCK = threading.Lock()
_CPU_PREV = [0, 0]
_HIST = {'watts': deque(maxlen=36), 'cpu': deque(maxlen=36), 'temp': deque(maxlen=36), 'at': 0.0}
_BGM = {'proc': None, 'track': '', 'playlist': [], 'idx': 0, 'paused': False, 'vol': 65}


def _read_int(path):
    try: return int(Path(path).read_text().strip())
    except (OSError, ValueError): return None


def battery_detail(root='/sys/class/power_supply'):
    """Detailed battery telemetry: level %, charging/discharging, live watts, and remaining playtime in minutes."""
    base = Path(root)
    bat = next((p for p in sorted(base.glob('*')) if (p / 'type').is_file() and (p / 'type').read_text(errors='ignore').strip() == 'Battery'), None)
    if not bat:
        return None
    cap = _read_int(bat / 'capacity')
    status = (bat / 'status').read_text(errors='ignore').strip() if (bat / 'status').is_file() else ''
    v_uv = _read_int(bat / 'voltage_now')
    i_ua = _read_int(bat / 'current_now')
    p_uw = _read_int(bat / 'power_now')
    c_uah = _read_int(bat / 'charge_now')
    cf_uah = _read_int(bat / 'charge_full')
    e_uwh = _read_int(bat / 'energy_now')
    ef_uwh = _read_int(bat / 'energy_full')
    charging = status in ('Charging', 'Full')
    watts = None
    if v_uv and v_uv > 0 and i_ua is not None:
        watts = round(abs(i_ua) * v_uv / 1e12, 1)
    elif p_uw is not None and status == 'Discharging':
        w = round(abs(p_uw) / 1e6, 1)
        if 0.1 <= w <= 45.0: watts = w
    if status == 'Full' and (i_ua == 0 or watts and watts > 25):
        watts = 0.0
    mins_left = None
    if status == 'Discharging':
        if i_ua and abs(i_ua) > 50_000 and c_uah and c_uah > 0:
            mins_left = max(1, min(2400, round((c_uah / abs(i_ua)) * 60)))
        elif watts and watts >= 0.5 and e_uwh and e_uwh > 0:
            mins_left = max(1, min(2400, round(((e_uwh / 1e6) / watts) * 60)))
    wh_full = round(ef_uwh / 1e6, 1) if ef_uwh else (round((cf_uah * 3.85) / 1e6, 1) if cf_uah else None)
    soh = _read_int(bat / 'state_of_health')
    if soh is None and cf_uah and (cfd := _read_int(bat / 'charge_full_design')) and cfd > 0:
        soh = max(1, min(100, round(100 * cf_uah / cfd)))
    cycles = _read_int(bat / 'cycle_count')
    raw_t = _read_int(bat / 'temp')
    bat_temp = round(raw_t / 10.0, 1) if raw_t is not None and -100 < raw_t < 900 else None
    return {'level': cap if cap is not None else 0, 'status': status, 'charging': charging,
            'watts': watts, 'mins_left': mins_left, 'wh_full': wh_full,
            'health': soh, 'cycles': cycles, 'bat_temp': bat_temp}


def _active_usb_type(raw):
    m = re.search(r'\[([A-Za-z0-9_]+)\]', str(raw or ''))
    return m.group(1) if m else ''


def charger_detail(root='/sys/class/power_supply', typec_root='/sys/class/typec'):
    """Inspect USB-C PD / PPS fast-charging negotiation, voltage, input current limit, and cell charge ceiling."""
    base = Path(root)
    bat = next((p for p in sorted(base.glob('*')) if (p / 'type').is_file() and (p / 'type').read_text(errors='ignore').strip() == 'Battery'), None)
    usb_supplies = [p for p in sorted(base.glob('*')) if p != bat and (p / 'type').is_file() and (p / 'type').read_text(errors='ignore').strip() == 'USB']
    if not bat and not usb_supplies:
        return None

    online = False
    usb_v = 0.0
    usb_i_lim = 0.0
    usb_i_now = 0.0
    modes = []
    for u in usb_supplies:
        if _read_int(u / 'online') == 1:
            online = True
        ut = _active_usb_type((u / 'usb_type').read_text(errors='ignore') if (u / 'usb_type').is_file() else '')
        if ut and ut != 'Unknown':
            modes.append(ut)
        vn = _read_int(u / 'voltage_now') or _read_int(u / 'voltage_max') or 0
        if vn > 0:
            usb_v = max(usb_v, round(vn / 1e6, 2))
        il = _read_int(u / 'input_current_limit') or _read_int(u / 'current_max') or 0
        if il > 0:
            usb_i_lim = max(usb_i_lim, round(il / 1e6, 2))
        inow = _read_int(u / 'current_now') or 0
        if inow > 0 and vn > 0:
            usb_i_now = max(usb_i_now, round(inow / 1e6, 2))

    # Prefer highest negotiated protocol across UCSI + battmgr (PD_PPS > PD > DCP > CDP > C > SDP)
    prio = ('PD_PPS', 'PD_DRP', 'PD', 'DCP', 'ACA', 'CDP', 'C', 'SDP')
    protocol = next((m for m in prio if m in modes), (modes[0] if modes else ('Online' if online else 'Offline')))

    data_role = ''
    pd_partner = False
    tc = Path(typec_root)
    if (tc / 'port0/data_role').is_file():
        data_role = _active_usb_type((tc / 'port0/data_role').read_text(errors='ignore'))
    if (tc / 'port0-partner/supports_usb_power_delivery').is_file():
        pd_partner = (tc / 'port0-partner/supports_usb_power_delivery').read_text(errors='ignore').strip() == 'yes'

    cc_cur = _read_int(bat / 'constant_charge_current') if bat else None
    cc_max = _read_int(bat / 'constant_charge_current_max') if bat else None
    ttf = _read_int(bat / 'time_to_full_avg') if bat else None
    status = (bat / 'status').read_text(errors='ignore').strip() if (bat and (bat / 'status').is_file()) else ''
    cap = _read_int(bat / 'capacity') if bat else None

    max_w = round(usb_v * usb_i_lim, 1) if (usb_v and usb_i_lim) else None
    live_in_w = round(usb_v * usb_i_now, 1) if (usb_v and usb_i_now) else None
    fast_active = bool(online and (protocol in ('PD_PPS', 'PD', 'PD_DRP') and (usb_v >= 8.0 or (max_w and max_w >= 20.0))))
    pc_port = bool(online and (protocol == 'SDP' or (data_role == 'device' and usb_v <= 5.5)))

    if not online:
        state_lbl = 'Akkubetrieb (PD/PPS bis 27–35 W bereit)'
        hint = 'Für Schnellladen ein USB-PD- / PPS-Netzteil (9 V / 3 A, ab 27 W) anschließen.'
    elif status == 'Full' or (cap is not None and cap >= 99):
        state_lbl = f'Voll geladen · {"PC-Port (5 V)" if pc_port else protocol}'
        hint = 'Akku ist voll (Erhaltungsladung). Schnellladen greift im Bereich 5–85 % mit voller Leistung.'
    elif fast_active:
        state_lbl = f'✓ Schnellladen aktiv ({protocol} · {max_w or 27:g} W)'
        hint = 'USB-Power-Delivery-Hochvolt-Schnellladen ist aktiv.'
    elif pc_port:
        state_lbl = f'PC-Datenport ({usb_v or 5:g} V · langsam)'
        hint = 'Am Computer-USB-Port begrenzt 5 V die Ladeleistung. Für Schnellladen ein 27W+ USB-PD-Wandnetzteil nutzen.'
    else:
        state_lbl = f'Lädt ({protocol} · bis {max_w:g} W)' if max_w else f'Lädt ({protocol})'
        hint = 'Standardladung aktiv; für maximales Schnellladen ein PPS-/PD-Netzteil ab 27 W verwenden.'

    return {
        'online': online,
        'protocol': protocol,
        'pd_partner': pd_partner,
        'data_role': data_role,
        'voltage_v': usb_v or None,
        'current_limit_a': usb_i_lim or None,
        'live_input_w': live_in_w,
        'max_input_w': max_w,
        'cell_charge_a': round(cc_cur / 1e6, 2) if cc_cur else None,
        'cell_max_a': round(cc_max / 1e6, 2) if cc_max else None,
        'mins_to_full': round(ttf / 60) if (ttf and ttf > 0) else None,
        'fast_charging': fast_active,
        'pc_port': pc_port,
        'label': state_lbl,
        'hint': hint,
    }


def cpu_ram():
    """(cpu_percent, ram_used_gb, ram_total_gb) from /proc/stat and /proc/meminfo."""
    cpu_pct = None
    try:
        parts = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
        idle, total = parts[3] + (parts[4] if len(parts) > 4 else 0), sum(parts)
        with LOCK:
            p_idle, p_total = _CPU_PREV
            _CPU_PREV[0], _CPU_PREV[1] = idle, total
        if p_total and total > p_total:
            cpu_pct = round(100.0 * (1.0 - (idle - p_idle) / (total - p_total)), 1)
    except (OSError, ValueError, IndexError): pass
    used_gb = total_gb = None
    try:
        mem = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            m = re.match(r'^(\w+):\s+(\d+)', line)
            if m: mem[m[1]] = int(m[2])
        if 'MemTotal' in mem and 'MemAvailable' in mem:
            total_gb = round(mem['MemTotal'] / 1048576, 1)
            used_gb = round((mem['MemTotal'] - mem['MemAvailable']) / 1048576, 1)
    except OSError: pass
    return cpu_pct, used_gb, total_gb


def dock_state(drm_glob='/sys/class/drm/card*-*/status'):
    """Detect connected external USB-C DisplayPort / HDMI monitors (ignoring internal DSI/eDP/Writeback)."""
    ext = []
    for p in sorted(glob.glob(drm_glob)):
        name = Path(p).parent.name  # e.g. card1-DP-1, card1-HDMI-A-1
        if any(tag in name for tag in ('-DSI-', '-eDP-', '-Writeback-')): continue
        try:
            if Path(p).read_text().strip() == 'connected': ext.append(name.split('-', 1)[-1])
        except OSError: pass
    return {'connected': bool(ext), 'outputs': ext}


def headphones_active():
    """True when the active PipeWire default audio sink is headphones or Bluetooth audio (not the built-in speaker)."""
    if not shutil.which('wpctl'): return False
    try: out = subprocess.run(['wpctl', 'status'], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError): return False
    in_sinks = False
    for line in out.splitlines():
        if 'Sinks:' in line: in_sinks = True; continue
        if in_sinks and any(h in line for h in ('Sources:', 'Filters:', 'Streams:', 'Video')): break
        if in_sinks and '*' in line:
            low = line.lower()
            return any(k in low for k in ('headphone', 'headset', 'bluez', 'bluetooth', 'airpods', 'buds', 'usb')) and 'speaker' not in low
    return False


def audio_streams(status_text=None):
    """Parse PipeWire active playback streams from `wpctl status` -> [{'id', 'name', 'vol', 'muted', 'bgm'}]."""
    if status_text is None:
        if not shutil.which('wpctl'): return []
        try: status_text = subprocess.run(['wpctl', 'status'], capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError): return []
    streams, in_streams = [], False
    for line in status_text.splitlines():
        if 'Streams:' in line: in_streams = True; continue
        if in_streams and line and not line.startswith((' ', '\t', '│', '├', '└')): break
        if not in_streams: continue
        m = re.search(r'(\d+)\.\s+([^\[]+?)(?:\s+\[vol:\s*([0-9.]+)(\s+MUTED)?\])?\s*$', line)
        if not m: continue
        sid, name = int(m[1]), m[2].strip()
        if any(skip in name.lower() for skip in ('output_', 'input_', 'monitor', 'capture')): continue
        vol = round(float(m[3]) * 100) if m[3] else None
        is_bgm = 'tandem-bgm' in name.lower()
        streams.append({'id': sid, 'name': name, 'vol': vol, 'muted': bool(m[4]), 'bgm': is_bgm})
    return streams


def set_stream_volume(stream_id, pct):
    """Set volume (0..100) of a single PipeWire stream via wpctl."""
    if not shutil.which('wpctl'): return {'error': 'wpctl fehlt'}
    v = max(0, min(100, int(pct))) / 100.0
    try:
        subprocess.run(['wpctl', 'set-volume', str(int(stream_id)), f'{v:.2f}'], capture_output=True, timeout=3)
        return {'ok': True, 'id': int(stream_id), 'vol': round(v * 100)}
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return {'error': str(e)}


# ---- Background music player (headless mpv --no-video, independent from top-screen game audio) ----
AUDIO_EXTS = {'.mp3', '.flac', '.ogg', '.opus', '.m4a', '.wav', '.aac'}


def music_tracks(extra_dirs=()):
    """Scan ~/Music and SD card Music/ folders for audio files -> [{'title', 'sub', 'path'}]."""
    roots = [Path.home() / 'Music', Path.home() / 'Musik', *(Path(p) for p in glob.glob('/run/media/*/*/Music')),
             *(Path(p) for p in glob.glob('/run/media/*/*/Musik')), *(Path(p) for p in extra_dirs)]
    tracks, seen = [], set()
    for r in roots:
        if not r.is_dir(): continue
        for dp, _, files in os.walk(r):
            for f in sorted(files):
                fp = Path(dp) / f
                if fp.suffix.lower() not in AUDIO_EXTS: continue
                rp = str(fp)
                if rp in seen: continue
                seen.add(rp)
                folder = fp.parent.name if fp.parent != r else 'Musik'
                tracks.append({'title': fp.stem.replace('_', ' '), 'sub': folder, 'path': rp})
                if len(tracks) >= 300: return tracks
    return tracks


def _bgm_ipc(*cmd):
    if not BGM_SOCKET.exists(): return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(str(BGM_SOCKET))
            s.sendall(json.dumps({'command': list(cmd)}).encode() + b'\n')
            return json.loads(s.recv(4096).splitlines()[0])
    except (OSError, ValueError, IndexError): return None


def bgm_playing():
    p = _BGM['proc']
    return bool(p and p.poll() is None and not _BGM['paused'] and _BGM['track'])


def bgm_status():
    p = _BGM['proc']
    alive = bool(p and p.poll() is None)
    if not alive: _BGM['track'] = ''
    return {'playing': alive and not _BGM['paused'] and bool(_BGM['track']), 'paused': bool(alive and _BGM['paused']),
            'track': _BGM['track'], 'vol': _BGM['vol'], 'tracks': music_tracks()[:80], 'streams': audio_streams()}


def bgm_control(action, path='', vol=None):
    """action: 'play' | 'toggle' | 'next' | 'prev' | 'stop' | 'vol'."""
    if action == 'vol' and vol is not None:
        _BGM['vol'] = max(0, min(100, int(vol)))
        _bgm_ipc('set_property', 'volume', _BGM['vol'])
        return bgm_status()
    if action == 'stop':
        p, _BGM['proc'], _BGM['track'], _BGM['paused'] = _BGM['proc'], None, '', False
        if p and p.poll() is None:
            p.terminate()
            threading.Thread(target=p.wait, daemon=True).start()
        BGM_SOCKET.unlink(missing_ok=True)
        return bgm_status()
    tracks = music_tracks()
    if action in ('next', 'prev') and tracks:
        cur = next((i for i, t in enumerate(tracks) if t['title'] == _BGM['track']), 0)
        pick = tracks[(cur + (1 if action == 'next' else -1)) % len(tracks)]
        action, path = 'play', pick['path']
    if action == 'toggle':
        if _BGM['proc'] and _BGM['proc'].poll() is None:
            _BGM['paused'] = not _BGM['paused']
            _bgm_ipc('set_property', 'pause', _BGM['paused'])
            return bgm_status()
        if tracks: action, path = 'play', tracks[0]['path']
        else: return {**bgm_status(), 'error': 'Keine Musikdateien in ~/Music oder auf der Karte (Music/) gefunden.'}
    if action == 'play' and path:
        if not os.path.isfile(path) and not path.startswith(('http://', 'https://')):
            return {'error': 'Datei nicht gefunden.'}
        if not (_BGM['proc'] and _BGM['proc'].poll() is None):
            BGM_SOCKET.unlink(missing_ok=True)
            cmd = (['mpv'] if shutil.which('mpv') else ['flatpak', 'run', 'io.mpv.Mpv']) + [
                '--no-video', '--idle=yes', '--really-quiet', f'--volume={_BGM["vol"]}',
                '--audio-client-name=tandem-bgm', f'--input-ipc-server={BGM_SOCKET}']
            try: _BGM['proc'] = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError as e: return {'error': f'Musik-Player nicht verfügbar ({e}).'}
            for _ in range(25):
                if BGM_SOCKET.exists(): break
                time.sleep(0.08)
        _bgm_ipc('loadfile', path, 'replace')
        _bgm_ipc('set_property', 'pause', False)
        _BGM['paused'] = False
        _BGM['track'] = Path(path).stem.replace('_', ' ') if not path.startswith('http') else path
    return bgm_status()


def snapshot(sample=True):
    """Combined telemetry snapshot for the in-game Cockpit tab & battery/charger diagnostics."""
    bat = battery_detail()
    chg = charger_detail()
    cpu, ram_u, ram_t = cpu_ram()
    pwr = thor.power() or {}
    dock = dock_state()
    now = time.time()
    if sample and now - _HIST['at'] >= 1.5:
        _HIST['at'] = now
        if bat and bat.get('watts') is not None: _HIST['watts'].append(bat['watts'])
        if cpu is not None: _HIST['cpu'].append(cpu)
        if pwr.get('temp') is not None: _HIST['temp'].append(pwr['temp'])
    return {'battery': bat, 'charger': chg, 'cpu': cpu, 'ram_used': ram_u, 'ram_total': ram_t,
            'temp': pwr.get('temp'), 'fan': pwr.get('fan'), 'profile': pwr.get('profile'),
            'dock': dock, 'hist': {k: list(_HIST[k]) for k in ('watts', 'cpu', 'temp')}}


def wake_on_lan(mac, broadcast='255.255.255.255', port=9):
    """Send a 102-byte Wake-on-LAN magic UDP packet to wake a sleeping PC (e.g. for Moonlight streaming)."""
    clean = re.sub(r'[:\-\.\s]', '', str(mac or '')).upper()
    if not re.fullmatch(r'[0-9A-F]{12}', clean):
        return {'error': 'Bitte eine gültige MAC-Adresse eintragen (z. B. AA:BB:CC:DD:EE:FF).'}
    pkt = b'\xff' * 6 + bytes.fromhex(clean) * 16
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(pkt, (broadcast, int(port)))
        return {'ok': True, 'text': 'Aufweck-Signal (Wake-on-LAN) gesendet.'}
    except OSError as e:
        return {'error': f'Wake-on-LAN fehlgeschlagen: {e}'}


# ---- Top-screen Gamescope / mangoapp FPS & Performance HUD -----------------------------------------------------------
HUD_PRESETS = {
    0: 'no_display\n',
    1: 'legacy_layout=false\nhorizontal\nhud_no_margin\nbackground_alpha=0.45\nround_corners=8\nfont_scale=1.05\nfps\nframetime=0\n',
    2: 'legacy_layout=false\nhorizontal\nhud_no_margin\nbackground_alpha=0.52\nround_corners=8\nfont_scale=0.95\nfps\ncpu_stats\ngpu_stats\nbattery\nbattery_watt\nframe_timing=0\n',
    3: 'legacy_layout=false\nposition=top-left\nbackground_alpha=0.58\nround_corners=10\nfps\ncpu_stats\ncpu_temp\ngpu_stats\ngpu_temp\nram\nbattery\nbattery_watt\nbattery_time\nframe_timing=1\n',
}


def mangohud_files(tmp_dir='/tmp'):
    """Locate active mangoapp MANGOHUD_CONFIGFILE(s) via /proc (no pgrep) plus recent user-owned /tmp/mangohud.* files."""
    found = []
    uid = os.getuid()
    for comm in glob.glob('/proc/[0-9]*/comm'):
        try:
            p = Path(comm)
            if p.stat().st_uid != uid or p.read_text(errors='ignore').strip() != 'mangoapp':
                continue
            env = (p.parent / 'environ').read_bytes().split(b'\0')
            for item in env:
                if item.startswith(b'MANGOHUD_CONFIGFILE='):
                    cf = Path(item.split(b'=', 1)[1].decode('utf-8', 'ignore'))
                    if cf.is_file() and cf not in found: found.append(cf)
        except OSError:
            continue
    if not found:
        cand = []
        for f in Path(tmp_dir).glob('mangohud.*'):
            try:
                st = f.stat()
                if st.st_uid == uid and f.is_file(): cand.append((st.st_mtime, f))
            except OSError: pass
        if cand:
            found.append(max(cand, key=lambda x: x[0])[1])
    return found


def set_hud(level, tmp_dir='/tmp'):
    """Write preset `level` (0=Off, 1=FPS, 2=Bar, 3=Full Graph) in-place so mangoapp's inotify watch reloads immediately."""
    lvl = int(level) if level in (0, 1, 2, 3) else 0
    preset = HUD_PRESETS[lvl]
    files = mangohud_files(tmp_dir)
    wrote = 0
    for f in files:
        try:
            with open(f, 'w', encoding='utf-8') as out:
                out.write(preset)
            wrote += 1
        except OSError:
            pass
    return {'ok': True, 'level': lvl, 'active': bool(wrote)}


# ---- Switch-2-style synthesized UI sounds & Thor Locator (zero external audio files) ----------------------------------
_WAV_CACHE = {}


def synth_wav(notes, rate=24000):
    """Synthesize a clean 16-bit mono PCM WAV in memory from [(freq_hz, dur_sec, vol_0_1), ...]."""
    import math, struct
    key = (tuple(notes), rate)
    if key in _WAV_CACHE:
        return _WAV_CACHE[key]
    samples = bytearray()
    for freq, dur, vol in notes:
        n = max(1, int(rate * dur))
        attack = max(1, min(int(rate * 0.004), n // 4))
        for i in range(n):
            if freq <= 0:
                val = 0.0
            else:
                env = (i / attack) if i < attack else math.exp(-3.6 * (i - attack) / max(1, n - attack))
                t = i / rate
                val = vol * env * (0.82 * math.sin(2 * math.pi * freq * t) + 0.18 * math.sin(4 * math.pi * freq * t))
            s = max(-32767, min(32767, int(val * 32767)))
            samples += struct.pack('<h', s)
    data_len = len(samples)
    hdr = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + data_len, b'WAVE', b'fmt ', 16, 1, 1,
                      rate, rate * 2, 2, 16, b'data', data_len)
    wav = hdr + bytes(samples)
    _WAV_CACHE[key] = wav
    return wav


SOUNDS = {
    'tick': [(1180, 0.018, 0.16)],
    'ok': [(880, 0.036, 0.22), (1320, 0.055, 0.24)],
    'back': [(980, 0.032, 0.20), (660, 0.048, 0.18)],
    'launch': [(587, 0.045, 0.24), (880, 0.050, 0.26), (1175, 0.095, 0.28)],
    'alert': [(1046, 0.07, 0.30), (1318, 0.09, 0.32), (1568, 0.14, 0.32)],
    'locator': [(1046, 0.11, 0.55), (1318, 0.11, 0.58), (1568, 0.11, 0.62), (2093, 0.22, 0.68),
                (0, 0.10, 0.0), (1046, 0.11, 0.55), (1318, 0.11, 0.58), (1568, 0.11, 0.62), (2093, 0.26, 0.72)],
}


def play_sound(kind='tick'):
    notes = SOUNDS.get(kind)
    if not notes or os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        return False
    player = ['pw-play', '-'] if shutil.which('pw-play') else (['aplay', '-q', '-'] if shutil.which('aplay') else None)
    if not player:
        return False
    wav = synth_wav(notes)
    def run():
        try:
            subprocess.run(player, input=wav, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
    threading.Thread(target=run, daemon=True).start()
    return True


def _haptic_burst(pulses=4, hold_s=0.14, gap_s=0.12):
    """Trigger rhythmic LRA vibration pulses on the AYN Thor's qcom-hv-haptics device."""
    import fcntl, struct
    try:
        raw = Path('/proc/bus/input/devices').read_text(errors='ignore')
    except OSError:
        return False
    fd = -1
    for block in raw.split('\n\n'):
        if 'haptic' not in block.lower():
            continue
        m = re.search(r'Handlers=.*?(event\d+)', block)
        if m:
            try:
                fd = os.open('/dev/input/' + m.group(1), os.O_RDWR | os.O_NONBLOCK)
                break
            except OSError:
                pass
    if fd < 0:
        return False
    try:
        buf = bytearray(struct.pack('HhHHHHH', 0x50, -1, 0, 0, int(hold_s * 1000), 0, 0x7000) + b'\x00' * 34)
        fcntl.ioctl(fd, 0x40304580, buf)
        eid = struct.unpack_from('h', buf, 2)[0]
        for i in range(pulses):
            os.write(fd, struct.pack('llHHi', 0, 0, 0x15, eid, 1))
            time.sleep(hold_s + (gap_s if i + 1 < pulses else 0.02))
    except OSError:
        pass
    finally:
        try: os.close(fd)
        except OSError: pass
    return True


def locator_ping():
    """Switch-2-style 'Find My Thor / Controller': plays an ascending chime and vibrates the Thor rhythmically."""
    play_sound('locator')
    threading.Thread(target=_haptic_burst, kwargs={'pulses': 4}, daemon=True).start()
    return {'ok': True, 'text': 'Der Thor klingelt und vibriert jetzt.'}


