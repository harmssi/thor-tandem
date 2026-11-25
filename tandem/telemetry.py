"""Live hardware telemetry, PipeWire per-stream audio mixer, USB-C dock state, and Wake-on-LAN for Toravo Tandem.
Standard library + wpctl/mpv IPC only; safe on systems without battery/DRM sysfs (returns None/empty cleanly)."""
import glob, json, os, re, shutil, socket, subprocess, threading, time
from collections import deque
from pathlib import Path

import thor

BGM_SOCKET = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/tmp') / f'tandem-bgm-{os.getuid()}.sock'
ERA_BGM_DIR = Path(__file__).resolve().parent / 'ui/bgm'
ERA_TRACKS = {'8bit': 'era-8bit.ogg', '16bit': 'era-16bit.ogg', 'modern': 'era-modern.ogg'}
LOCK = threading.Lock()
_BGM_LOCK = threading.Lock()
_CPU_PREV = [0, 0]
_HIST = {'watts': deque(maxlen=36), 'cpu': deque(maxlen=36), 'temp': deque(maxlen=36), 'at': 0.0}
_BGM = {'proc': None, 'backend': '', 'path': '', 'track': '', 'playlist': [], 'idx': 0, 'paused': False, 'vol': 65, 'loop': False, 'era_auto': False, 'era_path': '', 'suspended': False}


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
    for sock_p in (BGM_SOCKET, Path(f'/tmp/tandem-bgm-{os.getuid()}.sock')):
        if not sock_p.exists():
            continue
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.6)
                s.connect(str(sock_p))
                s.sendall(json.dumps({'command': list(cmd)}).encode() + b'\n')
                raw = s.recv(4096)
                return json.loads(raw.splitlines()[0]) if raw else {'ok': True}
        except (OSError, ValueError, IndexError):
            continue
    return None


def _kill_stray_bgm_pids():
    """Terminate any orphaned tandem-bgm player (e.g. Flatpak bwrap mpv or ffplay) by exact PID only."""
    import signal as _sig
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen' or not os.path.isdir('/proc'):
        return
    skip = {os.getpid(), os.getppid()}
    targets = []
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in skip:
            continue
        try:
            comm = Path(f'/proc/{pid}/comm').read_text(errors='ignore').strip()
            if comm not in ('mpv', 'ffplay', 'bwrap'):
                continue
            cmd = Path(f'/proc/{pid}/cmdline').read_bytes()
            if b'tandem-bgm' in cmd or (comm == 'ffplay' and b'TANDEM_BGM_PROC=1' in Path(f'/proc/{pid}/environ').read_bytes()):
                targets.append(pid)
        except OSError:
            continue
    for pid in targets:
        try:
            os.kill(pid, _sig.SIGTERM)
        except OSError:
            pass
    if targets:
        time.sleep(0.05)
        for pid in targets:
            try:
                os.kill(pid, _sig.SIGKILL)
            except OSError:
                pass


def _stop_bgm_locked():
    import signal as _sig
    p = _BGM['proc']
    backend = _BGM.get('backend', '')
    _BGM.update(proc=None, backend='', path='', track='', paused=False, loop=False, era_auto=False, era_path='')
    if backend == 'mpv':
        _bgm_ipc('quit')
    if p is not None and p.poll() is None:
        try:
            os.killpg(p.pid, _sig.SIGTERM)
        except OSError:
            try: p.terminate()
            except OSError: pass
        try:
            p.wait(timeout=0.15)
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid, _sig.SIGKILL)
            except OSError:
                try: p.kill()
                except OSError: pass
            threading.Thread(target=p.wait, daemon=True).start()
    _kill_stray_bgm_pids()
    BGM_SOCKET.unlink(missing_ok=True)
    Path(f'/tmp/tandem-bgm-{os.getuid()}.sock').unlink(missing_ok=True)


def stop_all_bgm(suspend=True, dry=False):
    """Immediately silence and terminate all Tandem menu/background music before entering or resuming a game."""
    if dry or os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        with _BGM_LOCK:
            _BGM['suspended'] = bool(suspend)
            _BGM.update(proc=None, backend='', path='', track='', paused=False, loop=False, era_auto=False, era_path='')
        return {'ok': True, 'playing': False}
    with _BGM_LOCK:
        _BGM['suspended'] = bool(suspend)
        _stop_bgm_locked()
    return {'ok': True, 'playing': False}


def bgm_playing():
    p = _BGM['proc']
    return bool(p and p.poll() is None and not _BGM['paused'] and _BGM['track'])


def bgm_status():
    p = _BGM['proc']
    alive = bool(p and p.poll() is None)
    if not alive:
        _BGM['backend'], _BGM['path'], _BGM['track'], _BGM['era_auto'], _BGM['era_path'] = '', '', '', False, ''
    return {'playing': alive and not _BGM['paused'] and bool(_BGM['track']), 'paused': bool(alive and _BGM['paused']),
            'track': _BGM['track'], 'vol': _BGM['vol'], 'loop': bool(_BGM.get('loop')),
            'era_auto': bool(_BGM.get('era_auto')), 'tracks': music_tracks()[:80], 'streams': audio_streams()}


def _spawn_ffplay_locked(path, vol, loop):
    env = {
        **os.environ,
        'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}',
        'TANDEM_BGM_PROC': '1',
        'PULSE_PROP': 'application.name=tandem-bgm media.name=tandem-bgm media.role=music',
        'PIPEWIRE_PROPS': '{ media.name = "tandem-bgm" node.name = "tandem-bgm" application.name = "tandem-bgm" }',
    }
    env.pop('SDL_AUDIODRIVER', None)
    cmd = ['ffplay', '-nodisp', '-vn', '-sn', '-loglevel', 'quiet',
           '-loop', '0' if loop else '1', '-autoexit', '-volume', str(max(0, min(100, int(vol)))), str(path)]
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, env=env)


def bgm_control(action, path='', vol=None, loop=False, era_auto=False):
    """action: 'play' | 'toggle' | 'next' | 'prev' | 'stop' | 'vol'."""
    import signal as _sig
    with _BGM_LOCK:
        if action == 'vol' and vol is not None:
            _BGM['vol'] = max(0, min(100, int(vol)))
            if _BGM.get('backend') == 'mpv':
                _bgm_ipc('set_property', 'volume', _BGM['vol'])
            elif _BGM['proc'] and _BGM['proc'].poll() is None:
                for st in audio_streams():
                    if st.get('bgm'):
                        set_stream_volume(st['id'], _BGM['vol'])
            return bgm_status()
        if action == 'stop':
            _stop_bgm_locked()
            return bgm_status()
        tracks = music_tracks()
        if action in ('next', 'prev') and tracks:
            cur = next((i for i, t in enumerate(tracks) if t['title'] == _BGM['track']), 0)
            pick = tracks[(cur + (1 if action == 'next' else -1)) % len(tracks)]
            action, path, loop, era_auto = 'play', pick['path'], False, False
        if action == 'toggle':
            p = _BGM['proc']
            if p and p.poll() is None:
                _BGM['paused'] = not _BGM['paused']
                if _BGM.get('backend') == 'mpv':
                    _bgm_ipc('set_property', 'pause', _BGM['paused'])
                else:
                    try: os.killpg(p.pid, _sig.SIGSTOP if _BGM['paused'] else _sig.SIGCONT)
                    except OSError: pass
                return bgm_status()
            if tracks:
                action, path, loop, era_auto = 'play', tracks[0]['path'], False, False
            else:
                return {**bgm_status(), 'error': 'Keine Musikdateien in ~/Music oder auf der Karte (Music/) gefunden.'}
        if action == 'play' and path:
            if era_auto and _BGM.get('suspended'):
                return bgm_status()
            if not os.path.isfile(path) and not path.startswith(('http://', 'https://')):
                return {'error': 'Datei nicht gefunden.'}
            if vol is not None:
                _BGM['vol'] = max(0, min(100, int(vol)))
            # Prefer native mpv (IPC), else native ffplay (zero Flatpak bwrap orphaning!), else Flatpak mpv
            if shutil.which('mpv'):
                if _BGM.get('backend') != 'mpv' or not (_BGM['proc'] and _BGM['proc'].poll() is None):
                    _stop_bgm_locked()
                    cmd = ['mpv', '--no-video', '--idle=yes', '--really-quiet', '--gapless-audio=yes',
                           f'--loop-file={"inf" if loop else "no"}', f'--volume={_BGM["vol"]}',
                           '--audio-client-name=tandem-bgm', f'--input-ipc-server={BGM_SOCKET}']
                    try:
                        _BGM['proc'] = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                        stderr=subprocess.DEVNULL, start_new_session=True)
                        _BGM['backend'] = 'mpv'
                    except OSError as e:
                        return {'error': f'Musik-Player nicht verfügbar ({e}).'}
                    for _ in range(25):
                        if BGM_SOCKET.exists(): break
                        time.sleep(0.05)
                _bgm_ipc('set_property', 'loop-file', 'inf' if loop else 'no')
                _bgm_ipc('set_property', 'volume', _BGM['vol'])
                _bgm_ipc('loadfile', path, 'replace')
                _bgm_ipc('set_property', 'pause', False)
            elif shutil.which('ffplay'):
                _stop_bgm_locked()
                try:
                    _BGM['proc'] = _spawn_ffplay_locked(path, _BGM['vol'], loop)
                    _BGM['backend'] = 'ffplay'
                except OSError as e:
                    return {'error': f'Musik-Player nicht verfügbar ({e}).'}
            else:
                _stop_bgm_locked()
                cmd = ['flatpak', 'run', '--filesystem=xdg-run', 'io.mpv.Mpv',
                       '--no-video', '--really-quiet', '--gapless-audio=yes',
                       f'--loop-file={"inf" if loop else "no"}', f'--volume={_BGM["vol"]}',
                       '--audio-client-name=tandem-bgm', f'--input-ipc-server={BGM_SOCKET}', str(path)]
                try:
                    _BGM['proc'] = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                    stderr=subprocess.DEVNULL, start_new_session=True)
                    _BGM['backend'] = 'mpv'
                except OSError as e:
                    return {'error': f'Musik-Player nicht verfügbar ({e}).'}
            _BGM['path'] = str(path)
            _BGM['paused'] = False
            _BGM['loop'] = bool(loop)
            _BGM['era_auto'] = bool(era_auto)
            _BGM['era_path'] = str(path) if era_auto else ''
            _BGM['track'] = Path(path).stem.replace('_', ' ') if not path.startswith('http') else path
        return bgm_status()


def era_bgm_path(era='modern', bgm_file=''):
    """Resolve shipped or custom loopable Era BGM audio file -> Path or None."""
    fname = os.path.basename(str(bgm_file or '').strip()) or ERA_TRACKS.get(str(era or 'modern'), 'era-modern.ogg')
    cand = ERA_BGM_DIR / fname
    if cand.is_file():
        return cand
    fallback = ERA_BGM_DIR / ERA_TRACKS.get(str(era or 'modern'), 'era-modern.ogg')
    return fallback if fallback.is_file() else None


def sync_era_bgm(era='modern', bgm_file='', enabled=True, vol=32, suspend_for_game=False, dry=False):
    """Start, seamlessly switch, or zero-RAM stop the loopable Era menu soundtrack (`8bit`, `16bit`, `modern`)."""
    if dry or os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        with _BGM_LOCK:
            _BGM['suspended'] = bool(suspend_for_game)
        return {'ok': True, 'dry': True}
    if not enabled or suspend_for_game:
        with _BGM_LOCK:
            _BGM['suspended'] = bool(suspend_for_game)
            if suspend_for_game or _BGM.get('era_auto') or (_BGM['proc'] and _BGM['proc'].poll() is None and not _BGM.get('track')):
                _stop_bgm_locked()
        return {'ok': True, 'playing': False}
    with _BGM_LOCK:
        _BGM['suspended'] = False
        p = _BGM['proc']
        alive = bool(p and p.poll() is None)
        # Respect manual user music playback from ~/Music while in menus
        if alive and not _BGM.get('era_auto') and _BGM.get('track'):
            return {'ok': True, 'user_music': True}
        target = era_bgm_path(era, bgm_file)
        if not target:
            return {'ok': False, 'missing': True}
        t_str = str(target)
        v_clamped = max(5, min(100, int(vol)))
        if alive and _BGM.get('era_auto') and _BGM.get('era_path') == t_str and not _BGM.get('paused'):
            if _BGM.get('vol') != v_clamped:
                _BGM['vol'] = v_clamped
                if _BGM.get('backend') == 'mpv':
                    _bgm_ipc('set_property', 'volume', v_clamped)
            return {'ok': True, 'playing': True, 'track': _BGM['track']}
    bgm_control('play', path=t_str, vol=v_clamped, loop=True, era_auto=True)
    return {'ok': True, 'playing': bgm_playing(), 'track': _BGM['track']}


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


def synth_wav(notes, rate=24000, wave='sine'):
    """Synthesize a clean 16-bit mono PCM WAV in memory from [(freq_hz, dur_sec, vol_0_1), ...] ('sine'|'square'|'16bit')."""
    import math, struct
    key = (tuple(notes), rate, wave)
    if key in _WAV_CACHE:
        return _WAV_CACHE[key]
    samples = bytearray()
    for freq, dur, vol in notes:
        n = max(1, int(rate * dur))
        attack = max(1, min(int(rate * (0.002 if wave == 'square' else 0.004)), n // 4))
        for i in range(n):
            if freq <= 0:
                val = 0.0
            else:
                decay_k = 2.4 if wave == 'square' else (3.1 if wave == '16bit' else 3.6)
                env = (i / attack) if i < attack else math.exp(-decay_k * (i - attack) / max(1, n - attack))
                t = i / rate
                ph = (freq * t) % 1.0
                if wave == 'square':
                    # Authentic 2A03 25% pulse duty cycle for unmistakable NES/Famicom chiptune character
                    raw = 0.78 if ph < 0.25 else -0.26
                    val = vol * env * raw
                elif wave == '16bit':
                    # Warm SPC700 / YM2612 bell-chime FM partial blend
                    val = vol * env * (0.62 * math.sin(2 * math.pi * freq * t)
                                       + 0.26 * math.sin(4 * math.pi * freq * t)
                                       + 0.12 * math.sin(6 * math.pi * freq * t))
                else:
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
    'tick': [(1180, 0.018, 0.15)],
    'ok': [(880, 0.034, 0.21), (1320, 0.055, 0.24)],
    'back': [(988, 0.030, 0.19), (659, 0.048, 0.18)],
    'launch': [(523, 0.042, 0.22), (659, 0.042, 0.24), (784, 0.048, 0.26), (1047, 0.065, 0.28), (1319, 0.115, 0.30)],
    'zoom': [(784, 0.025, 0.16), (1047, 0.038, 0.19)],
    'alert': [(1046, 0.07, 0.30), (1318, 0.09, 0.32), (1568, 0.14, 0.32)],
    'locator': [(1046, 0.11, 0.55), (1318, 0.11, 0.58), (1568, 0.11, 0.62), (2093, 0.22, 0.68),
                (0, 0.10, 0.0), (1046, 0.11, 0.55), (1318, 0.11, 0.58), (1568, 0.11, 0.62), (2093, 0.26, 0.72)],
}

SOUNDS_8BIT = {
    'tick': [(1047, 0.016, 0.16)],
    'ok': [(988, 0.040, 0.22), (1319, 0.085, 0.24)],
    'back': [(784, 0.032, 0.18), (523, 0.052, 0.18)],
    'launch': [(523, 0.042, 0.22), (659, 0.042, 0.22), (784, 0.042, 0.24), (1047, 0.048, 0.25), (1319, 0.055, 0.26), (1568, 0.130, 0.28)],
    'zoom': [(659, 0.024, 0.18), (988, 0.040, 0.20)],
}

SOUNDS_16BIT = {
    'tick': [(880, 0.022, 0.16), (1320, 0.018, 0.12)],
    'ok': [(659, 0.035, 0.20), (988, 0.038, 0.22), (1319, 0.075, 0.24)],
    'back': [(880, 0.032, 0.19), (587, 0.058, 0.18)],
    'launch': [(440, 0.040, 0.20), (554, 0.040, 0.22), (659, 0.042, 0.24), (880, 0.048, 0.26), (1109, 0.055, 0.27), (1319, 0.135, 0.29)],
    'zoom': [(587, 0.026, 0.17), (880, 0.042, 0.20)],
}


def play_sound(kind='tick', era='modern'):
    era_s = str(era or 'modern')
    bank = SOUNDS_8BIT if era_s == '8bit' else (SOUNDS_16BIT if era_s == '16bit' else SOUNDS)
    notes = bank.get(kind) or SOUNDS.get(kind)
    if not notes or os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        return False
    player = ['pw-play', '-'] if shutil.which('pw-play') else (['aplay', '-q', '-'] if shutil.which('aplay') else None)
    if not player:
        return False
    wave = 'square' if era_s == '8bit' else ('16bit' if era_s == '16bit' else 'sine')
    wav = synth_wav(notes, wave=wave if kind in bank else 'sine')
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


# ---- Thor Audio-DSP (Psychoacoustic Speaker Pipeline via PipeWire filter-chain) ---------------------------------------
SPEAKER_SINK = 'alsa_output.platform-sound.HiFi__Speaker__sink'
SPEAKER_DSP_MODES = ('off', 'cinema', 'clear', 'night')
SPEAKER_DSP_BANDS = {
    # Sub-105 Hz excursion high-pass + 168 Hz psychoacoustic upper-bass punch + de-boxiness @ 480 Hz + airy 5.2 kHz shelf
    'cinema': (
        ('pre', 'bq_highshelf', 20.0, 0.707, -3.0),
        ('hpf', 'bq_highpass', 105.0, 0.707, 0.0),
        ('warmth', 'bq_peaking', 168.0, 1.05, 4.2),
        ('debox', 'bq_peaking', 480.0, 1.20, -2.2),
        ('presence', 'bq_peaking', 2600.0, 1.10, 1.8),
        ('air', 'bq_highshelf', 5200.0, 0.707, 2.6),
    ),
    # Crisp dialogue, RPG voices & podcast intelligibility
    'clear': (
        ('pre', 'bq_highshelf', 20.0, 0.707, -2.5),
        ('hpf', 'bq_highpass', 120.0, 0.707, 0.0),
        ('mud', 'bq_peaking', 360.0, 1.15, -2.8),
        ('voice', 'bq_peaking', 2800.0, 1.00, 3.6),
        ('air', 'bq_highshelf', 5800.0, 0.707, 1.8),
    ),
    # Late-night play: low-cut so sound never carries through walls + gentle treble roll-off
    'night': (
        ('pre', 'bq_highshelf', 20.0, 0.707, -3.0),
        ('hpf', 'bq_highpass', 155.0, 0.707, 0.0),
        ('mid', 'bq_peaking', 1800.0, 0.90, 2.2),
        ('soft', 'bq_highshelf', 5000.0, 0.707, -2.5),
    ),
}
_DSP_LOCK = threading.Lock()
_DSP = {'proc': None, 'mode': 'off'}


def _dsp_pidfile():
    rt = Path(os.environ.get('XDG_RUNTIME_DIR') or '/tmp')
    return rt / f'tandem-dsp-{os.getuid()}.pid'


def build_speaker_dsp_conf(mode='cinema', target_sink=SPEAKER_SINK):
    """Build a zero-dependency PipeWire filter-chain config targeting ONLY the internal stereo speakers."""
    bands = SPEAKER_DSP_BANDS.get(mode)
    if not bands:
        return ''
    nodes, links = [], []
    for name, label, freq, q, gain in bands:
        ctrl = f'"Freq" = {freq:.1f} "Q" = {q:.3f}' + (f' "Gain" = {gain:.2f}' if label != 'bq_highpass' else '')
        nodes.append(f'{{ type = builtin name = {name} label = {label} control = {{ {ctrl} }} }}')
    for i in range(len(bands) - 1):
        links.append(f'{{ output = "{bands[i][0]}:Out" input = "{bands[i + 1][0]}:In" }}')
    nl = '\n                    '
    return f"""context.properties = {{
    log.level = 0
}}
context.spa-libs = {{
    audio.convert.* = audioconvert/libspa-audioconvert
    support.*       = support/libspa-support
}}
context.modules = [
    {{ name = libpipewire-module-rt flags = [ ifexists nofail ] }}
    {{ name = libpipewire-module-protocol-native }}
    {{ name = libpipewire-module-client-node }}
    {{ name = libpipewire-module-adapter }}
    {{ name = libpipewire-module-filter-chain
        args = {{
            node.description = "Thor Speaker Audio-DSP ({mode})"
            media.name       = "Thor Speaker Audio-DSP ({mode})"
            filter.graph = {{
                nodes = [
                    {nl.join(nodes)}
                ]
                links = [
                    {nl.join(links)}
                ]
            }}
            capture.props = {{
                node.name      = "toravo_speaker_dsp"
                media.class    = Audio/Sink
                audio.channels = 2
                audio.position = [ FL FR ]
            }}
            playback.props = {{
                node.name      = "toravo_speaker_dsp.output"
                target.object  = "{target_sink}"
                node.passive   = true
                stream.dont-remix = true
                audio.channels = 2
                audio.position = [ FL FR ]
            }}
        }}
    }}
]
"""


def _parse_sink_ids(status_text):
    """Extract {'dsp': id, 'speaker': id} from `wpctl status` Audio Sinks & Filters sections."""
    out, in_audio_nodes = {}, False
    for line in (status_text or '').splitlines():
        s = line.strip()
        if s in ('Video', 'Settings'):
            break
        if 'Sinks:' in line or 'Filters:' in line:
            in_audio_nodes = True
            continue
        if in_audio_nodes and ('Sources:' in line or 'Streams:' in line):
            in_audio_nodes = False
            continue
        if not in_audio_nodes:
            continue
        m = re.search(r'(\d+)\.\s+(.+)$', line)
        if not m:
            continue
        sid, rest = int(m[1]), m[2].strip().lower()
        name_part = rest.split('[', 1)[0].strip()
        if ('thor speaker audio-dsp' in name_part or name_part == 'toravo_speaker_dsp') and '.output' not in name_part:
            if '[stream/' not in rest:
                out['dsp'] = sid
        elif 'built-in audio speaker' in name_part or 'hifi__speaker__sink' in name_part or ('speaker' in name_part and 'dsp' not in name_part and '.output' not in name_part):
            out['speaker'] = sid
    return out


def _kill_dsp_pid(pid):
    import signal
    try:
        cmd = Path(f'/proc/{int(pid)}/cmdline').read_bytes().decode('utf-8', 'ignore')
        if 'thor-dsp.conf' not in cmd:
            return
        os.kill(int(pid), signal.SIGTERM)
        for _ in range(15):
            if not Path(f'/proc/{int(pid)}').exists():
                return
            time.sleep(0.05)
        os.kill(int(pid), signal.SIGKILL)
    except (OSError, ValueError):
        pass


def stop_speaker_dsp():
    """Cleanly stop the PipeWire speaker DSP sidecar by exact PID and restore hardware speaker sink if active."""
    with _DSP_LOCK:
        proc, _DSP['proc'], _DSP['mode'] = _DSP['proc'], None, 'off'
        pf = _dsp_pidfile()
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if pf.is_file():
            try:
                _kill_dsp_pid(int(pf.read_text().strip()))
            except (OSError, ValueError):
                pass
            pf.unlink(missing_ok=True)
        if shutil.which('wpctl') and os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
            try:
                st = subprocess.run(['wpctl', 'status'], capture_output=True, text=True, timeout=2).stdout
                sids = _parse_sink_ids(st)
                if sids.get('speaker') and not headphones_active():
                    subprocess.run(['wpctl', 'set-default', str(sids['speaker'])], capture_output=True, timeout=2)
            except (OSError, subprocess.SubprocessError):
                pass
    return {'ok': True, 'mode': 'off'}


def ensure_speaker_sink_ready():
    """When toravo_speaker_dsp sits in front of the hardware speaker sink, keep the underlying
    hardware speaker sink unmuted at unity (1.00) so volume/mute on @DEFAULT_AUDIO_SINK@ always works."""
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen' or not shutil.which('wpctl'):
        return
    try:
        st = subprocess.run(['wpctl', 'status'], capture_output=True, text=True, timeout=2).stdout
        sids = _parse_sink_ids(st)
        spk = sids.get('speaker')
        if spk and sids.get('dsp'):
            subprocess.run(['wpctl', 'set-mute', str(spk), '0'], capture_output=True, timeout=2)
            subprocess.run(['wpctl', 'set-volume', str(spk), '1.00'], capture_output=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        pass


def apply_speaker_dsp(mode='cinema'):
    """Start or switch the Thor Speaker Audio-DSP filter-chain ('off', 'cinema', 'clear', 'night')."""
    mode = str(mode or 'off').lower()
    if mode not in SPEAKER_DSP_MODES or mode == 'off':
        return stop_speaker_dsp()
    conf_txt = build_speaker_dsp_conf(mode)
    cdir = Path(os.environ.get('XDG_CACHE_HOME') or (Path.home() / '.cache')) / 'tandem'
    conf_path = cdir / 'thor-dsp.conf'
    try:
        cdir.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(conf_txt, encoding='utf-8')
    except OSError as exc:
        return {'error': str(exc)}
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen' or not shutil.which('pipewire') or not shutil.which('wpctl'):
        return {'ok': True, 'mode': mode, 'written': str(conf_path), 'active': False}
    try:
        st0 = subprocess.run(['wpctl', 'status'], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return {'ok': True, 'mode': mode, 'written': str(conf_path), 'active': False}
    sids0 = _parse_sink_ids(st0)
    if not sids0.get('speaker') and SPEAKER_SINK.lower() not in st0.lower():
        return {'ok': True, 'mode': mode, 'written': str(conf_path), 'active': False}
    # Preserve current volume across sink transition
    cur_vol = None
    try:
        vout = subprocess.run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'], capture_output=True, text=True, timeout=2).stdout
        vm = re.search(r'([0-9]+(?:\.[0-9]+)?)', vout or '')
        if vm:
            cur_vol = max(0.0, min(1.0, float(vm[1])))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    stop_speaker_dsp()
    with _DSP_LOCK:
        if sids0.get('speaker'):
            # Ensure hardware speaker sink underneath toravo_speaker_dsp is never stuck muted or double-attenuated
            subprocess.run(['wpctl', 'set-mute', str(sids0['speaker']), '0'], capture_output=True, timeout=2)
            subprocess.run(['wpctl', 'set-volume', str(sids0['speaker']), '1.00'], capture_output=True, timeout=2)
        env = {**os.environ, 'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'}
        try:
            proc = subprocess.Popen(['pipewire', '-c', str(conf_path)], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        except OSError as exc:
            return {'error': str(exc)}
        _DSP['proc'], _DSP['mode'] = proc, mode
        try:
            _dsp_pidfile().write_text(str(proc.pid))
        except OSError:
            pass
        if hasattr(os, 'sched_setaffinity') and (os.cpu_count() or 0) >= 8:
            try:
                os.sched_setaffinity(proc.pid, {0, 1, 2})
            except OSError:
                pass
        dsp_id = None
        for _ in range(16):
            if proc.poll() is not None:
                break
            time.sleep(0.06)
            try:
                st = subprocess.run(['wpctl', 'status'], capture_output=True, text=True, timeout=2).stdout
                dsp_id = _parse_sink_ids(st).get('dsp')
                if dsp_id:
                    break
            except (OSError, subprocess.SubprocessError):
                pass
        if dsp_id:
            subprocess.run(['wpctl', 'set-mute', str(dsp_id), '0'], capture_output=True, timeout=2)
            if cur_vol is not None:
                subprocess.run(['wpctl', 'set-volume', str(dsp_id), f'{cur_vol:.2f}'], capture_output=True, timeout=2)
            if not headphones_active():
                subprocess.run(['wpctl', 'set-default', str(dsp_id)], capture_output=True, timeout=2)
        return {'ok': True, 'mode': mode, 'written': str(conf_path), 'active': bool(dsp_id)}


# ---- Bifrost-Style Smart Stick-LED Engine (Cover, Live-Ambilight, Battery Gauge, Thermal Guard) ----------------------
RGB_MODES = ('cover', 'ambilight', 'battery', 'thermal', 'static')


def bifrost_rgb_color(mode, battery_info=None, temp_c=None, fast_chg=False):
    """Compute RRGGBB hex color for battery or thermal Bifrost stick-LED modes."""
    if mode == 'battery':
        b = battery_info or {}
        lvl = int(b.get('level') if b.get('level') is not None else 100)
        if b.get('charging'):
            return '00D0C0' if fast_chg else '20E040'
        if lvl > 50:
            return '20E040'
        if lvl > 25:
            return 'FFD000'
        if lvl > 15:
            return 'FF7A00'
        return 'FF2000'
    if mode == 'thermal':
        t = float(temp_c if temp_c is not None else 42.0)
        if t < 48:
            return '00D0C0'
        if t < 58:
            return '20E040'
        if t < 68:
            return 'FFD000'
        if t < 75:
            return 'FF7A00'
        return 'FF2000'
    return None


def sample_ambilight_hex(png_path):
    """Extract a vivid dominant scene color from a top-screen capture for Bifrost Live-Ambilight stick rings."""
    try:
        from PySide6.QtGui import QImage
        img = QImage(str(png_path))
        if img.isNull():
            return None
        tiny = img.scaled(20, 12)
        r_sum = g_sum = b_sum = w_sum = 0.0
        for y in range(12):
            for x in range(20):
                px = tiny.pixel(x, y)
                r, g, b = (px >> 16) & 255, (px >> 8) & 255, px & 255
                mx, mn = max(r, g, b), min(r, g, b)
                if mx < 24:
                    continue
                sat = (mx - mn) / max(1, mx)
                weight = 0.25 + sat * 2.5
                r_sum += r * weight
                g_sum += g * weight
                b_sum += b * weight
                w_sum += weight
        if w_sum <= 0.01:
            return None
        rr, gg, bb = int(r_sum / w_sum), int(g_sum / w_sum), int(b_sum / w_sum)
        peak = max(rr, gg, bb, 1)
        # Normalize brightness so LED rings stay vivid
        scale = min(2.2, 235.0 / peak)
        return '%02X%02X%02X' % (min(255, round(rr * scale)), min(255, round(gg * scale)), min(255, round(bb * scale)))
    except Exception:
        return None


# ---- Wi-Fi 7 (ath12k), PCIe Runtime-PM & 1-Tap Airplane Mode (Silent & Endurance Suite) ----------------------------
_NET_PM = {'wifi_ps': None}


def set_wifi_powersave(on=True):
    """Dynamically toggle IEEE 802.11 power-save + PCIe Runtime-PM (on in menu/standby/offline games, off while streaming)."""
    target = bool(on)
    with LOCK:
        if _NET_PM['wifi_ps'] is target:
            return {'ok': True, 'wifi_powersave': target}
        _NET_PM['wifi_ps'] = target
    # 1. PCIe Runtime-PM (ath12k root port & endpoint) where writable by wheel
    for ctrl in glob.glob('/sys/bus/pci/devices/*/power/control'):
        try:
            Path(ctrl).write_text('auto' if target else 'on')
        except OSError:
            pass
    # 2. NetworkManager per-connection 802-11-wireless.powersave (3 = enabled, 2 = disabled)
    if shutil.which('nmcli'):
        try:
            out = subprocess.run(['nmcli', '-t', '-f', 'UUID,TYPE', 'connection', 'show', '--active'],
                                 capture_output=True, text=True, timeout=3).stdout
            for line in out.splitlines():
                if line.endswith(':802-11-wireless') or line.endswith(':wireless'):
                    uuid = line.split(':', 1)[0]
                    if uuid:
                        subprocess.run(['nmcli', 'connection', 'modify', uuid, '802-11-wireless.powersave', '3' if target else '2'],
                                       capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass
    # 3. Direct mac80211 iw fallback where permitted
    if shutil.which('iw'):
        for net in glob.glob('/sys/class/net/wl*'):
            iface = Path(net).name
            try:
                subprocess.run(['iw', 'dev', iface, 'set', 'power_save', 'on' if target else 'off'],
                               capture_output=True, timeout=2)
            except (OSError, subprocess.SubprocessError):
                pass
    return {'ok': True, 'wifi_powersave': target}


def airplane_state():
    """Return {'on': bool, 'wifi_blocked': bool, 'bt_blocked': bool} from /sys/class/rfkill (0 subprocess cost!)."""
    wifi_b = bt_b = False
    seen_w = seen_b = False
    for rdir in glob.glob('/sys/class/rfkill/rfkill*'):
        try:
            rtype = (Path(rdir) / 'type').read_text().strip()
            soft = (Path(rdir) / 'soft').read_text().strip() == '1'
            if rtype == 'wlan':
                seen_w = True
                wifi_b = wifi_b or soft
            elif rtype == 'bluetooth':
                seen_b = True
                bt_b = bt_b or soft
        except OSError:
            continue
    on = bool((seen_w or seen_b) and (not seen_w or wifi_b) and (not seen_b or bt_b))
    return {'on': on, 'wifi_blocked': wifi_b, 'bt_blocked': bt_b}


def set_airplane_mode(on):
    """Toggle Wi-Fi + Bluetooth radios via rfkill (/dev/rfkill seat ACL -> no root required, saves 1.5-2.5 W on travel)."""
    target = bool(on)
    if not shutil.which('rfkill'):
        return {'error': 'rfkill nicht verfügbar.'}
    act = 'block' if target else 'unblock'
    ok = False
    for kind in ('wifi', 'wlan', 'bluetooth'):
        try:
            r = subprocess.run(['rfkill', act, kind], capture_output=True, timeout=3)
            if r.returncode == 0:
                ok = True
        except (OSError, subprocess.SubprocessError):
            pass
    if shutil.which('nmcli'):
        try:
            subprocess.run(['nmcli', 'radio', 'wifi', 'off' if target else 'on'], capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass
    st = airplane_state()
    if not ok and st['on'] != target:
        return {'error': 'Flugmodus konnte nicht umgeschaltet werden.'}
    return {'ok': True, **st}





