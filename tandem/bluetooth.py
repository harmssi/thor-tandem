"""Bluetooth for Tandem's settings: BlueZ on the system D-Bus through python3-dbus (ArmadaOS ships it), no other tools.

state()            adapter on/scanning and the known and nearby devices (name, kind, paired, connected, battery)
scan()             looks for devices for SCAN seconds (BlueZ ends a scan when the asking connection goes, so the daemon holds it)
act(addr, what)    pair | connect | disconnect | forget, in a thread; the answer is a German text for a toast

Headphones: once connected, WirePlumber makes them the output by itself (its Bluetooth nodes have priority 1010, the
Thor's speaker 1009, and Tandem never pins a default sink); the volume keys follow @DEFAULT_AUDIO_SINK@.
Gamepads: paired, trusted (so they come back by themselves) and connected; the emulators see them as the next pad."""
import threading

SCAN = 30
BLUEZ, ADAPTER, DEVICE = 'org.bluez', 'org.bluez.Adapter1', 'org.bluez.Device1'
KINDS = {'audio-headset': 'audio', 'audio-headphones': 'audio', 'audio-card': 'audio', 'input-gaming': 'pad',
         'input-keyboard': 'input', 'input-mouse': 'input', 'input-tablet': 'input', 'phone': 'phone'}
_bus, _lock = [None], threading.Lock()


def bus():
    """A private system-bus connection served by a GLib loop thread: the pairing agent must answer BlueZ's questions."""
    with _lock:
        if _bus[0] is None:
            import dbus, dbus.bus, dbus.mainloop.glib
            from gi.repository import GLib
            _bus[0] = dbus.bus.BusConnection(dbus.bus.BUS_SYSTEM, mainloop=dbus.mainloop.glib.DBusGMainLoop())
            threading.Thread(target=GLib.MainLoop().run, daemon=True).start()
        return _bus[0]


def objects(b=None):
    b = b or bus()
    return b.get_object(BLUEZ, '/').GetManagedObjects(dbus_interface='org.freedesktop.DBus.ObjectManager')


def kind(icon, klass=0):
    if icon in KINDS: return KINDS[icon]
    major = (int(klass or 0) >> 8) & 0x1f  # Class of Device: 4 audio, 5 peripheral (minor 0x08-0x0c: joystick/gamepad)
    return 'audio' if major == 4 else 'pad' if major == 5 and (int(klass) >> 2) & 0x0f in (1, 2) else 'input' if major == 5 else 'other'


def state(objs=None):
    try: objs = objects() if objs is None else objs
    except Exception: return {'error': 'Bluetooth antwortet nicht.', 'devices': []}
    adapter = next(((str(p), i[ADAPTER]) for p, i in objs.items() if ADAPTER in i), None)
    if not adapter: return {'error': 'Kein Bluetooth-Adapter gefunden.', 'devices': []}
    devices = []
    for path, ifs in objs.items():
        d = ifs.get(DEVICE)
        if not d or not str(path).startswith(adapter[0] + '/'): continue
        addr, name = str(d.get('Address', '')), str(d.get('Name') or '')
        paired = bool(d.get('Paired'))
        if not name and not paired: continue  # nameless devices nearby (beacons, TVs …) only clutter the list
        battery = ifs.get('org.bluez.Battery1', {}).get('Percentage')
        devices.append({'addr': addr, 'name': str(d.get('Alias') or name or addr), 'kind': kind(str(d.get('Icon', '')), d.get('Class', 0)),
                        'paired': paired, 'connected': bool(d.get('Connected')), 'battery': int(battery) if battery is not None else None,
                        'rssi': int(d['RSSI']) if 'RSSI' in d else None})
    devices.sort(key=lambda d: (not d['connected'], not d['paired'], -(d['rssi'] or -999), d['name'].lower()))
    a = adapter[1]
    return {'powered': bool(a.get('Powered')), 'scanning': bool(a.get('Discovering')), 'devices': devices[:30]}


def _adapter(b):
    path = next(str(p) for p, i in objects(b).items() if ADAPTER in i)
    return b.get_object(BLUEZ, path), path


def power(on, b=None):
    import dbus
    b = b or bus()
    obj, _ = _adapter(b)
    obj.Set(ADAPTER, 'Powered', dbus.Boolean(bool(on)), dbus_interface='org.freedesktop.DBus.Properties')
    return {'ok': True}


def scan(b=None):
    b = b or bus()
    obj, _ = _adapter(b)
    try: obj.StartDiscovery(dbus_interface=ADAPTER)
    except Exception as error:
        if 'InProgress' not in str(error): return {'error': 'Suche nicht möglich.'}
    def stop():
        try: obj.StopDiscovery(dbus_interface=ADAPTER)
        except Exception: pass
    threading.Timer(SCAN, stop).start()
    return {'ok': True}


def act(addr, what, b=None):
    """One action on one device; returns {'text'} or {'error'} (German, for a toast)."""
    import dbus
    if what not in ('pair', 'connect', 'disconnect', 'forget'): return {'error': 'unbekannt'}
    b = b or bus()
    objs = objects(b)
    path = next((str(p) for p, i in objs.items() if DEVICE in i and str(i[DEVICE].get('Address')) == addr), None)
    if not path: return {'error': 'Gerät nicht mehr in Reichweite.'}
    dev, props = b.get_object(BLUEZ, path), objs[path][DEVICE]
    name = str(props.get('Alias') or props.get('Name') or addr)
    try:
        if what == 'forget':
            _adapter(b)[0].RemoveDevice(dbus.ObjectPath(path), dbus_interface=ADAPTER)
            return {'text': f'{name} vergessen.'}
        if what == 'disconnect':
            dev.Disconnect(dbus_interface=DEVICE, timeout=20)
            return {'text': f'{name} getrennt.'}
        if what == 'pair' and not props.get('Paired'):
            Agent.on(b)
            try: dev.Pair(dbus_interface=DEVICE, timeout=60)
            finally: Agent.off(b)
        dev.Set(DEVICE, 'Trusted', dbus.Boolean(True), dbus_interface='org.freedesktop.DBus.Properties')  # comes back by itself
        dev.Connect(dbus_interface=DEVICE, timeout=30)
        return {'text': f'{name} verbunden.'}
    except Exception as error:
        text = str(getattr(error, 'get_dbus_message', lambda: error)() or error)
        hint = ' – Gerät in den Kopplungsmodus bringen.' if what == 'pair' else ''
        return {'error': f'{name}: {"Zeit abgelaufen" if "Timeout" in text or "NoReply" in text else "fehlgeschlagen"}{hint}'}


class Agent:
    """BlueZ's pairing agent for "just works" pairing (headphones, gamepads), registered only while Tandem pairs."""
    PATH = '/de/toravo/tandem/agent'
    _obj = None

    @classmethod
    def on(cls, b):
        import dbus.service
        if cls._obj is None:
            class Impl(dbus.service.Object):
                I = 'org.bluez.Agent1'
                @dbus.service.method(I, in_signature='', out_signature='')
                def Release(self): pass
                @dbus.service.method(I, in_signature='os', out_signature='')
                def AuthorizeService(self, device, uuid): pass
                @dbus.service.method(I, in_signature='o', out_signature='s')
                def RequestPinCode(self, device): return '0000'
                @dbus.service.method(I, in_signature='o', out_signature='u')
                def RequestPasskey(self, device): return dbus.UInt32(0)
                @dbus.service.method(I, in_signature='ouq', out_signature='')
                def DisplayPasskey(self, device, passkey, entered): pass
                @dbus.service.method(I, in_signature='os', out_signature='')
                def DisplayPinCode(self, device, pincode): pass
                @dbus.service.method(I, in_signature='ou', out_signature='')
                def RequestConfirmation(self, device, passkey): pass
                @dbus.service.method(I, in_signature='o', out_signature='')
                def RequestAuthorization(self, device): pass
                @dbus.service.method(I, in_signature='', out_signature='')
                def Cancel(self): pass
            cls._obj = Impl(b, cls.PATH)
        b.get_object(BLUEZ, '/org/bluez').RegisterAgent(cls.PATH, 'NoInputNoOutput', dbus_interface='org.bluez.AgentManager1')

    @classmethod
    def off(cls, b):
        try: b.get_object(BLUEZ, '/org/bluez').UnregisterAgent(cls.PATH, dbus_interface='org.bluez.AgentManager1')
        except Exception: pass
