"""The Thor's own hardware under ArmadaOS, reached without root through the interfaces the system already has:

- stick lights and gyro: Armada Control, ArmadaOS's Decky plugin. It runs as root and its methods can be called by any
  local program through the Decky loader (WebSocket on 127.0.0.1:1337, token from /auth/token), exactly as the Steam
  side panel calls them. (/run/armada/session.sock only knows game_launched and reapply_perf.)
- performance profile, temperature and fan: armada-powerd on the system bus (org.armada.Power, open to group wheel).

Everything answers None / an error text where a device lacks it; nothing here needs Steam to run.
"""
import base64, json, os, socket, struct, subprocess, threading

DECKY = ('127.0.0.1', 1337)
PLUGIN = 'Armada Control'
POWER = ['busctl', '--system', '--json=short']
POWER_OBJ = ['org.armada.Power', '/org/armada/Power', 'org.armada.Power1']
LOCK = threading.Lock()  # one call at a time: both screens ask together, and parallel calls lost answers on the Thor
PROFILES = {'Eco': 'Sparsam', 'Balanced': 'Ausgewogen', 'Performance': 'Leistung'}
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
    # Decky matches replies to calls by id across all connections: a small counter would get another caller's answer
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
    """{'profile', 'profiles' [(id, label)], 'temp' (°C), 'fan' (rpm)} or None without armada-powerd."""
    done = _power('call', *POWER_OBJ, 'GetStatus')
    try: data = {k: v['data'] for k, v in json.loads(done.stdout)['data'][0].items()}
    except (AttributeError, ValueError, KeyError, IndexError, TypeError): return None
    return {'profile': data.get('profile'), 'profiles': [[k, v] for k, v in PROFILES.items()], 'temp': data.get('temperature'), 'fan': data.get('fan_rpm')}


def state():
    """What the settings show: {'rgb', 'gyro', 'power', 'os', 'sleep_mode', 'bottom_enabled'}; None where unavailable."""
    out = {'rgb': None, 'gyro': None, 'power': power(), 'os': None, 'sleep_mode': None, 'bottom_enabled': None}
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
            out['rgb'] = {**rgb, 'level': rgb.get('maxBrightness' if rgb.get('linkBrightness') else 'brightness', 50)}  # what the one slider shows
    except (OSError, ValueError, KeyError, TypeError, AttributeError): pass
    return out


def change(key, value):
    """One setting: 'profile' (Eco|Balanced|Performance), 'gyro' (bool), 'sleep_mode' (s2idle|fake),
    'bottom_screen' (bool) or 'rgb' (dict). Returns the new state() or {'error': text}."""
    try:
        if key == 'profile':
            if value not in PROFILES: return {'error': 'Unbekanntes Leistungsprofil.'}
            done = _power('set-property', *POWER_OBJ, 'Profile', 's', value)
            if not done or done.returncode: return {'error': 'Das Leistungsprofil lässt sich gerade nicht ändern.'}
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
            # with the link on, armada-rgb follows the screen up to maxBrightness: the slider then sets that ceiling
            decky('set_rgb', bool(value.get('enabled', now.get('enabled', True))), link, color, int(now.get('saturation', 100)),
                  bright if link else int(now.get('maxBrightness', 50)), bright)
        else: return {'error': 'unbekannte Einstellung'}
    except (OSError, ValueError, TypeError) as error: return {'error': f'Der Thor nimmt das gerade nicht an ({error}).'}
    return state()
