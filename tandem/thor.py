"""The Thor's own hardware & ArmadaOS HyperDrive engine, reached without root through existing system interfaces:

- Armada Control Decky plugin (WebSocket on 127.0.0.1:1337, token from /auth/token):
  stick lights, gyro, sleep mode, AND HyperDrive game-tweaks (/etc/armada/game-tweaks.json + compat-applied.json:
  Turnip WinNative/Devel/Stable driver switching, FEX Fast-JIT profile, scx_lavd / scx_cosmos BPF gaming schedulers,
  Big-Core 3-7 isolation, and ARM64EC Proton-CachyOS auto-wiring across all Steam games).
- armada-powerd on the system bus (org.armada.Power, open to group wheel): performance profile, temperature, fan.

Everything answers None / an error text where a device lacks it; nothing here needs Steam to run.
"""
import base64, json, os, socket, struct, subprocess, threading
from pathlib import Path
import thor_perf

DECKY = ('127.0.0.1', 1337)
PLUGIN = 'Armada Control'
POWER = ['busctl', '--system', '--json=short']
POWER_OBJ = ['org.armada.Power', '/org/armada/Power', 'org.armada.Power1']
LOCK = threading.Lock()  # one call at a time: both screens ask together, and parallel calls lost answers on the Thor
PROFILES = {'Eco': 'Sparsam', 'Balanced': 'Ausgewogen', 'Performance': 'Leistung', 'Turbo': 'Turbo'}
_ACTIVE_PROFILE = ''
# Stick colours to choose from: name and RRGGBB as armada-rgb takes it
COLORS = [('Weiß', 'FFFFFF'), ('Rot', 'FF2000'), ('Orange', 'FF7A00'), ('Gelb', 'FFD000'), ('Grün', '20E040'), ('Türkis', '00D0C0'),
          ('Blau', '1060FF'), ('Lila', '9040FF'), ('Pink', 'FF30A0')]


def _token():
    with socket.create_connection(DECKY, timeout=3) as sock:
        sock.sendall(f'GET /auth/token HTTP/1.1\r\nHost: {DECKY[0]}:{DECKY[1]}\r\nConnection: close\r\n\r\n'.encode())
        data = b''
        while chunk := sock.recv(4096): data += chunk
    return data.split(b'\r\n\r\n', 1)[1].decode().strip()


def _exact(sock, n):
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk: raise OSError('Decky hat die Verbindung beendet')
        buf += chunk
    return buf


def decky(method, *args, timeout=10):
    """Calls one method of Armada Control and returns its result; raises OSError when that is not possible."""
    with LOCK: return _decky(method, *args, timeout=timeout)


def _decky(method, *args, timeout=10):
    token, key = _token(), base64.b64encode(os.urandom(16)).decode()
    call = int.from_bytes(os.urandom(6), 'big') + 1
    with socket.create_connection(DECKY, timeout=timeout) as sock:
        sock.sendall(f'GET /ws?auth={token} HTTP/1.1\r\nHost: {DECKY[0]}:{DECKY[1]}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                     f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
        head = b''
        while b'\r\n\r\n' not in head: head += _exact(sock, 1)
        if b' 101 ' not in head.split(b'\r\n', 1)[0]: raise OSError('Decky lehnt ab')
        payload, mask = json.dumps({'type': 0, 'id': call, 'route': 'loader/call_plugin_method', 'args': [PLUGIN, method, *args]}).encode(), os.urandom(4)
        n = len(payload)
        size = bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n)
        sock.sendall(b'\x81' + size + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        while True:
            b1, b2 = _exact(sock, 2)
            n = b2 & 0x7f
            if n == 126: n = struct.unpack('>H', _exact(sock, 2))[0]
            elif n == 127: n = struct.unpack('>Q', _exact(sock, 8))[0]
            data, op = _exact(sock, n), b1 & 0x0f
            if op == 8: raise OSError('Decky hat die Verbindung beendet')
            if op != 1: continue
            msg = json.loads(data)
            if msg.get('id') != call: continue
            if msg.get('type') == 1: return msg.get('result')
            raise OSError(str(msg.get('error') or 'Armada Control meldet einen Fehler'))


def _power(*args):
    try: return subprocess.run(POWER + list(args), capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError): return None


def power():
    """{'profile', 'profiles' [(id, label)], 'temp' (°C), 'fan' (rpm), 'perf'} or None without armada-powerd."""
    done = _power('call', *POWER_OBJ, 'GetStatus')
    try: data = {k: v['data'] for k, v in json.loads(done.stdout)['data'][0].items()}
    except (AttributeError, ValueError, KeyError, IndexError, TypeError): return None
    prof = _ACTIVE_PROFILE if (_ACTIVE_PROFILE == 'Turbo' and data.get('profile') == 'Performance') else data.get('profile')
    perf = thor_perf.telemetry()
    if _ACTIVE_FAN_MODE in ('silent', 'auto') and perf.get('fan_mode') == 'auto':
        perf['fan_mode'] = _ACTIVE_FAN_MODE
    return {'profile': prof, 'profiles': [[k, v] for k, v in PROFILES.items()], 'temp': data.get('temperature'),
            'fan': data.get('fan_rpm'), 'perf': perf}


_ACTIVE_FAN_MODE = 'auto'


def ensure_silent_profiles(state_dir=None, force=False):
    """Configure armada-powerd once for true 0-RPM semi-passive fan stop (< 52 C), smooth ramp-up (12),
    and mainline PELT 'schedutil' + released Adreno 740 minimum clock (0.0 = 220 MHz idle in menus)."""
    sdir = Path(state_dir) if state_dir else (Path.home() / '.local/state/tandem')
    stamp = sdir / 'silent-fan-1.7.0.stamp'
    if stamp.is_file() and not force:
        return True
    try:
        cfg = decky('get_config') or {}
        pw = cfg.get('power')
        if isinstance(pw, dict) and isinstance(pw.get('profiles'), dict):
            edited = False
            for pname in ('eco', 'balanced', 'performance'):
                p = pw['profiles'].get(pname)
                if not isinstance(p, dict):
                    continue
                if p.get('cpu_governor') != 'schedutil':
                    p['cpu_governor'] = 'schedutil'
                    edited = True
                if float(p.get('gpu_min') or 0.0) > 0.0:
                    p['gpu_min'] = 0.0
                    p.pop('gpu_min_mhz', None)
                    edited = True
                if pname == 'eco' and float(p.get('gpu_max') or 0.8) > 0.72:
                    p['gpu_max'] = 0.70
                    p.pop('gpu_max_mhz', None)
                    edited = True
            if edited:
                decky('save_power_config', pw)
        decky('save_fan_curves', thor_perf.SILENT_FAN_CURVES, thor_perf.SILENT_FAN_SETTINGS)
        _power('call', *POWER_OBJ, 'Reload')
        sdir.mkdir(parents=True, exist_ok=True)
        stamp.write_text('1.7.0\n')
        return True
    except Exception:
        return False


def suspend_power(on):
    """Clamp SM8550 to 307/499/595 MHz + 220 MHz GPU + 75 MHz UFS + 0-RPM fan in Standby (using armada-powerd Suspend
    only when /etc/armada/power-profiles.conf has fan_low_pwm=0, otherwise keeping 0-RPM Eco curve active + direct sysfs floor)."""
    has_zero_susp_fan = False
    try:
        pconf = Path('/etc/armada/power-profiles.conf')
        if pconf.is_file() and 'fan_low_pwm' in pconf.read_text(errors='ignore'):
            has_zero_susp_fan = True
    except OSError:
        pass
    if has_zero_susp_fan:
        _power('call', *POWER_OBJ, 'Suspend' if on else 'Resume')
    return thor_perf.set_standby_clocks(bool(on))


def set_companion_locked(locked):
    """Hardware DRM sleep + touch palm-lock for the bottom DSI-2 OLED via Gamescope (< 10 ms, 0 session disruption)."""
    val = '1' if locked else '0'
    env = {**os.environ, 'DISPLAY': os.environ.get('DISPLAY') or ':0'}
    try:
        r = subprocess.run(
            ['xprop', '-root', '-f', 'GAMESCOPE_COMPANION_LOCKED', '32c', '-set', 'GAMESCOPE_COMPANION_LOCKED', val],
            env=env, capture_output=True, timeout=3,
        )
        if r.returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        decky('set_companion_locked', bool(locked))
        return True
    except Exception:
        return False


def _extract_engine(config):
    """Summarize Armada Control's Turnip driver, FEX profile, BPF scheduler, core isolation & HyperDrive state."""
    tw = ((config.get('tweaks') or {}).get('global')) or {}
    drivers = config.get('turnipDrivers') or []
    drv_list = [[d['id'], f"{d.get('label', d['id'])}" + (f" ({d['version'].split('-')[0]})" if d.get('version') else '')]
                for d in drivers if isinstance(d, dict) and d.get('id')]
    cur_drv = tw.get('turnipDriver') or 'stable'
    cur_fex = tw.get('fexProfile') or 'default'
    cur_sched = tw.get('scheduler') or 'eevdf'
    cur_cores = tw.get('cores') or 'all'
    hyper = bool(cur_fex == 'fast' and cur_drv in ('winnative', 'devel') and cur_sched in ('lavd', 'cosmos') and cur_cores == 'big')
    return {
        'hyperdrive': hyper,
        'turnip': cur_drv,
        'turnip_drivers': drv_list or [['stable', 'Stable'], ['devel', 'Devel'], ['winnative', 'WinNative']],
        'fex_profile': cur_fex,
        'scheduler': cur_sched,
        'cores': cur_cores,
        'games': ((config.get('tweaks') or {}).get('games')) or {},
    }


def sync_steam_compat(config=None, proton_prefer='proton-cachyos-11.0-arm64'):
    """Ensure every installed Steam game has armada-game-launch + ARM64EC Proton-CachyOS enabled."""
    try:
        cfg = config or decky('get_config') or {}
        applied = decky('get_compat_applied') or {}
        existing = set(str(a) for a in (applied.get('appids') or []) if str(a).isdigit())
        installed = {str(g.get('appid')) for g in (cfg.get('installedGames') or []) if isinstance(g, dict) and str(g.get('appid', '')).isdigit()}
        protons = cfg.get('protonDefaults') or []
        chosen = proton_prefer if proton_prefer in protons else (applied.get('protonDefault') or (protons[-1] if protons else 'proton_11-arm64'))
        merged = sorted(existing | installed, key=int)
        if merged != sorted(existing, key=int) or applied.get('protonDefault') != chosen:
            return decky('save_compat_applied', merged, chosen)
        return applied
    except (OSError, ValueError, TypeError):
        return None


def state():
    """What the settings show: {'rgb', 'gyro', 'power', 'os', 'sleep_mode', 'bottom_enabled', 'engine'}; None where unavailable."""
    out = {'rgb': None, 'gyro': None, 'power': power(), 'os': None, 'sleep_mode': None, 'bottom_enabled': None, 'engine': None}
    try:
        config = decky('get_config')
        out['gyro'] = config['gyro'] if (config.get('gyro') or {}).get('supported') else None
        out['os'] = config.get('osVersion')
        if config.get('sleepMode') in ('s2idle', 'fake'):
            out['sleep_mode'] = config['sleepMode']
        if isinstance(config.get('bottomScreenEnabled'), bool):
            out['bottom_enabled'] = config['bottomScreenEnabled']
        if config.get('rgbSupported'):
            rgb = decky('get_rgb')
            out['rgb'] = {**rgb, 'level': rgb.get('maxBrightness' if rgb.get('linkBrightness') else 'brightness', 50)}
        out['engine'] = _extract_engine(config)
    except (OSError, ValueError, KeyError, TypeError, AttributeError): pass
    return out


def _update_global_tweaks(**updates):
    cfg = decky('get_config') or {}
    tweaks = cfg.get('tweaks') or {'global': {}, 'games': {}}
    glob = dict(tweaks.get('global') or {})
    for k, v in updates.items():
        if v is None:
            glob.pop(k, None)
        else:
            glob[k] = v
    decky('save_tweaks', {'global': glob, 'games': dict(tweaks.get('games') or {})})
    return cfg


def change(key, value):
    """Modify hardware or Armada HyperDrive engine settings without root."""
    global _ACTIVE_PROFILE
    try:
        if key == 'profile':
            if value not in PROFILES: return {'error': 'Unbekanntes Leistungsprofil.'}
            armada_prof = thor_perf.PROFILE_TUNING[value]['armada']
            done = _power('set-property', *POWER_OBJ, 'Profile', 's', armada_prof)
            if not done or done.returncode: return {'error': 'Das Leistungsprofil lässt sich gerade nicht ändern.'}
            _ACTIVE_PROFILE = value
            thor_perf.apply_profile(value)
        elif key == 'hyperdrive':
            on = bool(value)
            if on:
                cfg = decky('get_config') or {}
                drv_ids = [d.get('id') for d in (cfg.get('turnipDrivers') or []) if isinstance(d, dict)]
                best_drv = 'winnative' if 'winnative' in drv_ids else ('devel' if 'devel' in drv_ids else 'stable')
                _update_global_tweaks(
                    turnipDriver=best_drv,
                    fexProfile='fast',
                    scheduler='lavd',
                    cores='big',
                    gamescopeCores='little',
                    nice=-10,
                    wineTopology=True,
                    gamescopeVulkanRealtime=True,
                    thunks={'Vulkan': True, 'GL': True, 'drm': True},
                )
                sync_steam_compat(cfg, 'proton-cachyos-11.0-arm64')
                if _ACTIVE_PROFILE != 'Turbo':
                    _power('set-property', *POWER_OBJ, 'Profile', 's', 'Performance')
                    _ACTIVE_PROFILE = 'Performance'
                    thor_perf.apply_profile('Performance')
            else:
                _update_global_tweaks(
                    turnipDriver='stable',
                    fexProfile='default',
                    scheduler=None,
                    cores=None,
                    gamescopeCores=None,
                    nice=0,
                )
        elif key == 'turnip':
            _update_global_tweaks(turnipDriver=str(value or 'stable'))
        elif key == 'fex_profile':
            if value not in ('fast', 'default', 'compatible'): return {'error': 'Unbekanntes FEX-Profil.'}
            _update_global_tweaks(fexProfile=str(value))
            if value == 'fast':
                sync_steam_compat(None, 'proton-cachyos-11.0-arm64')
        elif key == 'scheduler':
            if value not in ('eevdf', 'lavd', 'cosmos'): return {'error': 'Unbekannter Scheduler.'}
            _update_global_tweaks(scheduler=None if value == 'eevdf' else str(value))
        elif key == 'core_mode':
            if value not in ('all', 'big'): return {'error': 'Unbekannter Kern-Modus.'}
            _update_global_tweaks(
                cores='big' if value == 'big' else None,
                gamescopeCores='little' if value == 'big' else None,
                nice=-10 if value == 'big' else 0,
                wineTopology=True,
            )
        elif key == 'gpu_clock':
            res = thor_perf.set_gpu_clock(value)
            if 'error' in res: return res
        elif key == 'charge_limit':
            res = thor_perf.set_charge_limit(value)
            if 'error' in res: return res
        elif key == 'fan_mode':
            global _ACTIVE_FAN_MODE
            m = str(value or '').lower()
            if m in ('silent', 'auto'):
                curves = thor_perf.ULTRA_SILENT_FAN_CURVES if m == 'silent' else thor_perf.SILENT_FAN_CURVES
                try:
                    decky('save_fan_curves', curves, thor_perf.SILENT_FAN_SETTINGS)
                    _power('call', *POWER_OBJ, 'Reload')
                except Exception:
                    pass
            res = thor_perf.set_fan_mode(m)
            if 'error' in res: return res
            _ACTIVE_FAN_MODE = m
        elif key == 'gyro':
            decky('set_gyro_enabled', bool(value))
        elif key == 'sleep_mode':
            if value not in ('s2idle', 'fake'): return {'error': 'Unbekannter Standby-Modus.'}
            decky('set_sleep_mode', str(value))
        elif key == 'bottom_screen':
            decky('set_bottom_screen_enabled', bool(value))
        elif key == 'rgb':
            if not isinstance(value, dict): return {'error': 'Ungültige Farbe.'}
            now = decky('get_rgb') or {}
            color = str(value.get('color', now.get('color', 'FFFFFF'))).lstrip('#').upper()
            if len(color) != 6 or any(c not in '0123456789ABCDEF' for c in color): return {'error': 'Ungültige Farbe.'}
            bright = max(0, min(100, int(value.get('brightness', now.get('brightness', 50)))))
            link = bool(value.get('linkBrightness', now.get('linkBrightness', False)))
            decky('set_rgb', bool(value.get('enabled', now.get('enabled', True))), link, color, int(now.get('saturation', 100)),
                  bright if link else int(now.get('maxBrightness', 50)), bright)
        else: return {'error': 'unbekannte Einstellung'}
    except (OSError, ValueError, TypeError) as error: return {'error': f'Der Thor nimmt das gerade nicht an ({error}).'}
    return state()
