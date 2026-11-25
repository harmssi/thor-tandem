"""Native Apple AirPods (AAP over Bluetooth L2CAP PSM 0x1001) & Low-Latency Bluetooth Audio Pro for Toravo Tandem.

Features:
- Automatic detection of Apple AirPods (1/2/3/4, Pro 1/2, Max) & Beats via BlueZ D-Bus (Vendor 0x004C / Apple UUID / Name).
- Direct L2CAP SEQPACKET (PSM 0x1001) AAP connection in pure Python stdlib `socket`:
  * AAP Handshake + Notification Subscription + Pro 2 / AirPods 4 Conversational Awareness capability unlock.
  * Live battery decoding (0-100% + charging state) for Left bud, Right bud, and MagSafe/Lightning Case.
  * Live Noise Control switching & hardware stem-press sync: Off (0x01), ANC (0x02), Transparency (0x03), Adaptive (0x04).
  * Conversational Awareness toggle (0x28: 0x01 On / 0x02 Off).
  * Real-time In-Ear Detection (0x06): optional auto-pause/resume of media & BGM when removing/inserting an AirPod.
- PipeWire / WirePlumber Gaming Low-Latency Bluetooth profile (SBC-XQ / AAC / mSBC + prevents 8 kHz HSP mic drop in games).
- 1-Tap Quick Audio Connect/Disconnect for AirPods or favourite Bluetooth headphones.
"""
import json, os, re, socket, subprocess, threading, time
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
PREFS_FILE = STATE / 'bt-audio-prefs.json'
WP_CONF = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'wireplumber/wireplumber.conf.d/51-tandem-bt-gaming.conf'

AAP_PSM = 0x1001  # 4097: Apple Accessory Protocol L2CAP PSM
APPLE_COMPANY_ID = 0x004C  # 76
APPLE_AAP_UUID = '74ec2172-0bad-4d01-8f77-997b2be0722a'

# Exact AAP protocol frames (LibrePods / MagicPods specification)
AAP_HANDSHAKE = bytes.fromhex('00000400010002000000000000000000')
AAP_ENABLE_NOTIFICATIONS = bytes.fromhex('040004000f00fffffeff')
AAP_UNLOCK_PRO_FEATURES = bytes.fromhex('040004004d00ff00000000000000')

NOISE_MODES = {
    'off': 0x01,
    'anc': 0x02,
    'transparency': 0x03,
    'adaptive': 0x04,
}
NOISE_FROM_BYTE = {v: k for k, v in NOISE_MODES.items()}

AIRPODS_NAME_RE = re.compile(r'(airpods|beats\s*(fit|studio|solo|flex|powerbeats))', re.I)


def build_aap_noise_packet(mode):
    val = NOISE_MODES.get(str(mode or '').lower())
    if val is None:
        return None
    return bytes([0x04, 0x00, 0x04, 0x00, 0x09, 0x00, 0x0D, val, 0x00, 0x00, 0x00])


def build_aap_conv_packet(enabled):
    val = 0x01 if enabled else 0x02
    return bytes([0x04, 0x00, 0x04, 0x00, 0x09, 0x00, 0x28, val, 0x00, 0x00, 0x00])


def parse_aap_packet(raw):
    """Parse one incoming AAP packet from L2CAP PSM 0x1001 into a structured event dict (or None)."""
    if not raw or len(raw) < 7 or raw[:4] != b'\x04\x00\x04\x00':
        return None
    opcode = raw[4] | (raw[5] << 8)
    # 1) Battery status packet: 04 00 04 00 04 00 <count> (<comp> 01 <lvl> <status> 01) ...
    if opcode == 0x0004 and len(raw) >= 7:
        count = raw[6]
        pos = 7
        batt = {}
        comp_names = {0x01: 'single', 0x02: 'right', 0x04: 'left', 0x08: 'case'}
        for _ in range(min(count, 6)):
            if pos + 5 > len(raw):
                break
            comp, _sp, lvl, st_flag, _term = raw[pos:pos + 5]
            pos += 5
            cname = comp_names.get(comp)
            if not cname:
                continue
            # Status: 0x01 charging, 0x02 discharging, 0x04 disconnected
            if st_flag == 0x04 or lvl > 100:
                batt[cname] = {'level': None, 'charging': False, 'connected': False}
            else:
                batt[cname] = {'level': max(0, min(100, int(lvl))), 'charging': st_flag == 0x01, 'connected': True}
        return {'kind': 'battery', 'battery': batt} if batt else None

    # 2) Ear detection packet: 04 00 04 00 06 00 <primary> <secondary>
    # Values: 0x00 = in-ear, 0x01 = out-of-ear, 0x02 = in-case
    if opcode == 0x0006 and len(raw) >= 8:
        p_st, s_st = raw[6], raw[7]
        return {
            'kind': 'ear',
            'primary_in_ear': p_st == 0x00,
            'secondary_in_ear': s_st == 0x00,
            'both_in_ear': p_st == 0x00 and s_st == 0x00,
            'any_in_ear': p_st == 0x00 or s_st == 0x00,
            'in_case': p_st == 0x02 and s_st == 0x02,
        }

    # 3) Control / Settings report: 04 00 04 00 09 00 <setting_id> <val> ...
    if opcode == 0x0009 and len(raw) >= 8:
        sub_id, val = raw[6], raw[7]
        if sub_id == 0x0D and val in NOISE_FROM_BYTE:
            return {'kind': 'noise_mode', 'mode': NOISE_FROM_BYTE[val]}
        if sub_id == 0x28 and val in (0x01, 0x02):
            return {'kind': 'conv_awareness', 'enabled': val == 0x01}
    return None


def is_airpods_device(props):
    """Detect whether a BlueZ org.bluez.Device1 property dict belongs to Apple AirPods / Beats."""
    if not isinstance(props, dict):
        return False
    name = str(props.get('Alias') or props.get('Name') or '')
    if AIRPODS_NAME_RE.search(name):
        return True
    uuids = [str(u).lower() for u in (props.get('UUIDs') or ())]
    if APPLE_AAP_UUID in uuids:
        return True
    mdata = props.get('ManufacturerData') or {}
    if APPLE_COMPANY_ID in mdata or str(APPLE_COMPANY_ID) in mdata:
        icon = str(props.get('Icon') or '')
        if 'audio' in icon or 'head' in icon:
            return True
    modalias = str(props.get('Modalias') or '').lower()
    if modalias.startswith('bluetooth:v004c') and 'audio' in str(props.get('Icon') or ''):
        return True
    return False


def load_prefs(path=PREFS_FILE):
    try:
        data = json.loads(Path(path).read_text())
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def save_prefs(update, path=PREFS_FILE):
    cur = load_prefs(path)
    cur.update(update)
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix('.tmp')
        tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, p)
    except OSError:
        pass
    return cur


def build_bt_low_latency_conf(enabled=True):
    """WirePlumber config enabling SBC-XQ / high-bitrate AAC / low A2DP latency & blocking HSP 8kHz mic profile drop."""
    if not enabled:
        return ''
    return """# Managed by Toravo Tandem (Bluetooth Gaming Low-Latency & AirPods AAC/SBC-XQ)
wireplumber.settings = {
  bluetooth.autoswitch-to-headset-profile = false
}

monitor.bluez.properties = {
  bluez5.enable-sbc-xq = true
  bluez5.enable-msbc = true
  bluez5.enable-hw-volume = true
  bluez5.a2dp.aac.bitratemode = 0
  bluez5.codecs = [ sbc sbc_xq aac ldac aptx aptx_hd aptx_ll faststream ]
}

monitor.bluez.rules = [
  {
    matches = [
      { node.name = "~bluez_output.*" }
    ]
    actions = {
      update-props = {
        node.latency = "512/48000"
        api.bluez5.a2dp-duplex = false
      }
    }
  }
]
"""


def apply_bt_low_latency(enabled=True, conf_path=WP_CONF, restart_wp=True):
    p = Path(conf_path)
    save_prefs({'bt_low_latency': bool(enabled)})
    changed = False
    if enabled:
        txt = build_bt_low_latency_conf(True)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.is_file() or p.read_text(errors='ignore') != txt:
            p.write_text(txt, encoding='utf-8')
            changed = True
    else:
        if p.is_file():
            p.unlink(missing_ok=True)
            changed = True
    if changed and restart_wp and os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
        try:
            subprocess.run(['systemctl', '--user', 'restart', 'wireplumber'], capture_output=True, timeout=6)
        except (OSError, subprocess.SubprocessError):
            pass
    return {'ok': True, 'bt_low_latency': bool(enabled), 'changed': changed}


class AirPodsManager:
    """Background AAP L2CAP (0x1001) session & Bluetooth audio quick-manager."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sock = None
        self._addr = ''
        self._name = ''
        self._connected = False
        self._aap_ready = False
        self._battery = {}  # {'left': {...}, 'right': {...}, 'case': {...}}
        self._noise_mode = 'off'
        self._conv_awareness = False
        self._ear = {'both_in_ear': True, 'any_in_ear': True}
        self._ear_paused_bgm = False
        self._cached = {'active': False, 'battery_pct': None, 'is_airpods': False}
        self._tandem = None
        self._running = False

    def start(self, tandem=None):
        self._tandem = tandem
        if self._running:
            return
        self._running = True
        prefs = load_prefs()
        if prefs.get('bt_low_latency', True):
            threading.Thread(target=apply_bt_low_latency, args=(True,), kwargs={'restart_wp': False}, daemon=True).start()
        threading.Thread(target=self._loop, daemon=True).start()

    def _scan_bt_audio(self):
        """Return (connected_airpods, connected_other_audio, paired_audio_list) from BlueZ."""
        try:
            import bluetooth
            objs = bluetooth.objects()
        except Exception:
            return None, None, []
        airpods_conn, other_conn, paired_list = None, None, []
        for _path, ifs in objs.items():
            d = ifs.get('org.bluez.Device1')
            if not d or not d.get('Paired'):
                continue
            addr = str(d.get('Address') or '')
            name = str(d.get('Alias') or d.get('Name') or addr)
            is_ap = is_airpods_device(d)
            k = 'audio' if is_ap else bluetooth.kind(str(d.get('Icon', '')), d.get('Class', 0))
            if k != 'audio':
                continue
            bz_batt = ifs.get('org.bluez.Battery1', {}).get('Percentage')
            item = {
                'addr': addr,
                'name': name,
                'is_airpods': is_ap,
                'connected': bool(d.get('Connected')),
                'battery': int(bz_batt) if bz_batt is not None else None,
            }
            paired_list.append(item)
            if item['connected']:
                if is_ap and not airpods_conn:
                    airpods_conn = item
                elif not other_conn:
                    other_conn = item
        return airpods_conn, other_conn, paired_list

    def _loop(self):
        while self._running:
            ap, other, _paired = self._scan_bt_audio()
            if ap:
                save_prefs({'fav_addr': ap['addr'], 'fav_name': ap['name'], 'fav_airpods': True})
                if self._addr != ap['addr'] or self._sock is None:
                    self._connect_aap(ap['addr'], ap['name'])
            else:
                if other:
                    save_prefs({'fav_addr': other['addr'], 'fav_name': other['name'], 'fav_airpods': False})
                self._close_sock()
            try:
                self._cached = self.status(ap_scan=(ap, other, _paired))
            except Exception:
                pass
            time.sleep(4.0)

    def _close_sock(self):
        with self._lock:
            s, self._sock = self._sock, None
            self._connected = False
            self._aap_ready = False
            self._addr = ''
        if s:
            try:
                s.close()
            except OSError:
                pass

    def _connect_aap(self, addr, name):
        self._close_sock()
        if not hasattr(socket, 'AF_BLUETOOTH') or not hasattr(socket, 'BTPROTO_L2CAP'):
            return
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
            s.settimeout(5.0)
            s.connect((addr, AAP_PSM))
            s.sendall(AAP_HANDSHAKE)
            time.sleep(0.12)
            s.sendall(AAP_ENABLE_NOTIFICATIONS)
            time.sleep(0.08)
            s.sendall(AAP_UNLOCK_PRO_FEATURES)
            s.settimeout(2.0)
        except OSError:
            try:
                s.close()
            except Exception:
                pass
            return
        with self._lock:
            self._sock = s
            self._addr = addr
            self._name = name
            self._connected = True
            self._aap_ready = True
        prefs = load_prefs()
        saved_nm = prefs.get('last_noise_mode')
        if saved_nm in NOISE_MODES:
            self.set_noise_mode(saved_nm, persist=False)
        threading.Thread(target=self._reader, args=(s, addr), daemon=True).start()

    def _reader(self, s, addr):
        while self._running and self._sock is s:
            try:
                raw = s.recv(512)
                if not raw:
                    break
            except socket.timeout:
                continue
            except OSError:
                break
            ev = parse_aap_packet(raw)
            if not ev:
                continue
            if ev['kind'] == 'battery':
                with self._lock:
                    self._battery.update(ev['battery'])
            elif ev['kind'] == 'noise_mode':
                with self._lock:
                    self._noise_mode = ev['mode']
                if self._tandem:
                    lbl = {'off': 'Aus', 'anc': 'ANC aktiv', 'transparency': 'Transparenz', 'adaptive': 'Adaptiv'}.get(ev['mode'], ev['mode'])
                    self._tandem.publish('toast', {'text': f'🎧 AirPods: {lbl}'})
            elif ev['kind'] == 'conv_awareness':
                with self._lock:
                    self._conv_awareness = ev['enabled']
            elif ev['kind'] == 'ear':
                self._on_ear_event(ev)
        if self._sock is s:
            self._close_sock()

    def _on_ear_event(self, ev):
        prefs = load_prefs()
        with self._lock:
            was_both = self._ear.get('both_in_ear', True)
            self._ear = ev
        if not prefs.get('ear_pause', True):
            return
        try:
            import telemetry
            if was_both and not ev['both_in_ear']:
                st = telemetry.bgm_status()
                if st.get('playing'):
                    telemetry.bgm_control('pause')
                    self._ear_paused_bgm = True
            elif not was_both and ev['both_in_ear'] and self._ear_paused_bgm:
                self._ear_paused_bgm = False
                telemetry.bgm_control('resume')
        except Exception:
            pass

    def set_noise_mode(self, mode, persist=True):
        pkt = build_aap_noise_packet(mode)
        if not pkt:
            return {'error': 'Unbekannter AirPods-Modus.'}
        with self._lock:
            s = self._sock
            self._noise_mode = mode
        if persist:
            save_prefs({'last_noise_mode': mode})
        if not s:
            return {'ok': True, 'queued': True, 'noise_mode': mode, 'text': 'Modus vorgemerkt (AirPods verbinden).'}
        try:
            s.sendall(pkt)
            lbl = {'off': 'Aus', 'anc': 'Geräuschunterdrückung (ANC)', 'transparency': 'Transparenz', 'adaptive': 'Adaptiv'}.get(mode, mode)
            return {'ok': True, 'noise_mode': mode, 'text': f'AirPods: {lbl}'}
        except OSError as exc:
            return {'error': f'AirPods nicht erreichbar: {exc}'}

    def set_conv_awareness(self, enabled):
        pkt = build_aap_conv_packet(bool(enabled))
        with self._lock:
            s = self._sock
            self._conv_awareness = bool(enabled)
        save_prefs({'conv_awareness': bool(enabled)})
        if s:
            try:
                s.sendall(pkt)
            except OSError:
                pass
        return {'ok': True, 'conv_awareness': bool(enabled)}

    def set_ear_pause(self, enabled):
        save_prefs({'ear_pause': bool(enabled)})
        return {'ok': True, 'ear_pause': bool(enabled)}

    def quick_toggle_connect(self, addr=''):
        """1-tap connect/disconnect of AirPods or favorite paired Bluetooth headphones."""
        import bluetooth
        ap, other, paired = self._scan_bt_audio()
        prefs = load_prefs()
        target = addr
        if not target:
            if ap:
                return bluetooth.act(ap['addr'], 'disconnect')
            if other:
                return bluetooth.act(other['addr'], 'disconnect')
            fav = prefs.get('fav_addr')
            if fav and any(d['addr'] == fav for d in paired):
                target = fav
            elif paired:
                # Prefer paired AirPods first
                ap_p = next((d for d in paired if d['is_airpods']), paired[0])
                target = ap_p['addr']
        if not target:
            return {'error': 'Noch keine Bluetooth-Kopfhörer gekoppelt.'}
        dev = next((d for d in paired if d['addr'] == target), None)
        what = 'disconnect' if (dev and dev.get('connected')) else 'connect'
        return bluetooth.act(target, what)

    def cached_status(self):
        return dict(self._cached)

    def status(self, ap_scan=None):
        prefs = load_prefs()
        ap, other, paired = ap_scan if ap_scan is not None else self._scan_bt_audio()
        with self._lock:
            b = dict(self._battery)
            nm = self._noise_mode
            ca = self._conv_awareness
            aap_ok = self._aap_ready
            ear = dict(self._ear)
        active = ap or other
        # Compute unified headphone battery % for status bar (min of active L/R buds, else single/BlueZ battery)
        bud_lvls = [b[k]['level'] for k in ('left', 'right', 'single') if isinstance(b.get(k), dict) and b[k].get('level') is not None]
        head_pct = min(bud_lvls) if bud_lvls else ((active or {}).get('battery'))
        fav_addr = prefs.get('fav_addr') or (paired[0]['addr'] if paired else '')
        fav_name = prefs.get('fav_name') or (paired[0]['name'] if paired else '')
        return {
            'active': bool(active),
            'addr': (active or {}).get('addr') or fav_addr,
            'name': (active or {}).get('name') or fav_name,
            'is_airpods': bool(ap) or (not active and bool(prefs.get('fav_airpods'))),
            'aap_connected': bool(ap and aap_ok),
            'battery_pct': head_pct,
            'pods': {
                'left': b.get('left'),
                'right': b.get('right'),
                'case': b.get('case'),
            },
            'noise_mode': nm,
            'conv_awareness': ca,
            'ear_pause': bool(prefs.get('ear_pause', True)),
            'bt_low_latency': bool(prefs.get('bt_low_latency', True)),
            'ear': ear,
            'paired_audio': paired,
        }


MANAGER = AirPodsManager()
