#!/usr/bin/env python3
"""Battle.net as a non-Steam shortcut under the BNet compatibility tool (github.com/mrdidit/bnet-arm), Steam not running.
  battlenet.py add <Battle.net-Setup.exe>   shortcut "Battle.net" that runs Blizzard's installer once, tool mapping
  battlenet.py launcher                     after the install: the shortcut starts the launcher; drive D: = the card
  battlenet.py wow                          own entry "WoW Forever" on Proton-11-ARM64-WoW (Battle.net cannot start it)
Backups of shortcuts.vdf and config.vdf go to $BNET_BACKUP (default ~/thor-restore/bnet-<date>)."""
import glob, json, os, re, shutil, struct, sys, time, zlib
from pathlib import Path

# 17.11.: DroidDeck-Proton fixes WoW Forever ARM64 ('Game Initialization Failed: I'); its FEX dlls are swapped for Bnet1's, else D2R crashes
NAME, TOOL = 'Battle.net', 'DroidDeck-Proton-11-12.8'
STEAM = Path.home() / '.local/share/Steam'
# D2R hints from the Thor's Android port (vkd3d-proton without upload heap / DXR, a big shader cache); Battle.net ignores them
OPTIONS = 'LANG=de_DE.UTF-8 VKD3D_CONFIG=no_upload_hvv,nodxr MESA_SHADER_CACHE_MAX_SIZE=4096MB /usr/libexec/armada/armada-game-launch %command%'
# 17.11.: WoW Forever crashes in Mesa 26.2.6's Turnip (vkCreateGraphicsPipelines); a Mesa-main Turnip built in a container fixes it
TURNIP = Path.home() / 'turnip-main/share/vulkan/icd.d/freedreno_icd.aarch64.json'
if TURNIP.is_file(): OPTIONS = f'VK_ICD_FILENAMES={TURNIP} {OPTIONS}'
LIBRARY = Path('/run/media/armada/THOR/Battle.net')  # games on the card: as drive D:, Z: (read-only /) shows 0 bytes free
LAUNCHER = r'drive_c/Program Files (x86)/Battle.net/Battle.net Launcher.exe'


def s(key, val): return b'\x01' + key.encode() + b'\x00' + val.encode() + b'\x00'
def i(key, val): return b'\x02' + key.encode() + b'\x00' + struct.pack('<I', val & 0xffffffff)


def shortcuts_path():
    users = glob.glob(str(STEAM / 'userdata/[0-9]*'))
    if len(users) != 1: sys.exit(f'erwartet genau ein Steam-Konto, gefunden: {len(users)}')
    return Path(users[0]) / 'config/shortcuts.vdf'


def backup(*paths):
    folder = Path(os.environ.get('BNET_BACKUP') or Path.home() / f'thor-restore/bnet-{time.strftime("%Y%m%d")}')
    folder.mkdir(parents=True, exist_ok=True)
    for p in paths:
        if p.exists(): shutil.copy2(p, folder / f'{p.name}.{time.strftime("%H%M%S")}')


def write(path, data):
    tmp = path.with_name(path.name + '.tmp'); tmp.write_bytes(data); os.replace(tmp, path)


def steam_running():
    for pid in filter(str.isdigit, os.listdir('/proc')):
        try:
            if Path(f'/proc/{pid}/comm').read_text().strip() in ('steam', 'steamwebhelper'): return True
        except OSError: pass
    return False


def entry_of(data):
    """(start, end, appid) of the Battle.net entry in shortcuts.vdf; end is where its tags begin."""
    at = data.find(s('AppName', NAME))
    if at < 0: return None
    start = data.rfind(b'\x02appid\x00', 0, at)
    return start, data.index(b'\x00tags\x00', at), struct.unpack_from('<I', data, start + 7)[0]


def map_tool(appid):
    """CompatToolMapping in config.vdf (text): this shortcut runs under the BNet tool."""
    path = STEAM / 'config/config.vdf'
    text = path.read_text()
    if re.search(rf'"CompatToolMapping"\s*\{{[^}}]*?"{appid}"', text): return
    m = re.search(r'\n(\t*)"CompatToolMapping"\n\t*\{\n', text)
    if not m: sys.exit('CompatToolMapping nicht gefunden, nichts geändert')
    t = m[1] + '\t'
    block = f'{t}"{appid}"\n{t}{{\n{t}\t"name"\t\t"{TOOL}"\n{t}\t"config"\t\t""\n{t}\t"priority"\t\t"250"\n{t}}}\n'
    write(path, (text[:m.end()] + block + text[m.end():]).encode())


def add(setup):
    setup = str(Path(setup).resolve())
    path = shortcuts_path()
    old = path.read_bytes() if path.exists() else b'\x00shortcuts\x00\x08\x08'
    if entry_of(old): sys.exit('schon eingetragen')
    if not old.startswith(b'\x00shortcuts\x00') or not old.endswith(b'\x08\x08'): sys.exit('unbekanntes Format, nichts geändert')
    backup(path, STEAM / 'config/config.vdf')
    appid = zlib.crc32((f'"{setup}"' + NAME).encode()) | 0x80000000
    entry = (i('appid', appid) + s('AppName', NAME) + s('Exe', f'"{setup}"') + s('StartDir', f'"{os.path.dirname(setup)}"') + s('icon', '')
             + s('ShortcutPath', '') + s('LaunchOptions', OPTIONS + ' --lang=deDE') + i('IsHidden', 0) + i('AllowDesktopConfig', 1)
             + i('AllowOverlay', 1) + i('OpenVR', 0) + i('Devkit', 0) + s('DevkitGameID', '') + i('DevkitOverrideAppID', 0)
             + i('LastPlayTime', 0) + s('FlatpakAppID', '') + b'\x00tags\x00\x08')
    count = old.count(b'\x02appid\x00')
    write(path, old[:-2] + b'\x00' + str(count).encode() + b'\x00' + entry + b'\x08' + b'\x08\x08')
    map_tool(appid)
    print(f'eingetragen: appid {appid}, Spiel-ID {appid << 32 | 0x02000000}')


def launcher():
    path = shortcuts_path()
    data = path.read_bytes()
    found = entry_of(data)
    if not found: sys.exit('kein Battle.net-Eintrag')
    start, end, appid = found
    prefix = STEAM / f'steamapps/compatdata/{appid}/pfx'
    exe = prefix / LAUNCHER
    if not exe.is_file(): sys.exit(f'Battle.net ist noch nicht installiert ({exe} fehlt)')
    LIBRARY.mkdir(parents=True, exist_ok=True)
    drive = prefix / 'dosdevices/d:'
    if not drive.is_symlink() or os.readlink(drive) != str(LIBRARY): drive.unlink(missing_ok=True); drive.symlink_to(LIBRARY)
    # Its window is Chromium (CEF): with browser hardware acceleration it flickers under Wine + gamescope (WineHQ 50637)
    config = prefix / 'drive_c/users/steamuser/AppData/Roaming/Battle.net/Battle.net.config'
    settings = json.loads(config.read_text(encoding='utf-8-sig')) if config.is_file() else {}
    if settings.setdefault('Client', {}).get('HardwareAcceleration') != 'false':
        if config.is_file(): backup(config)
        settings['Client']['HardwareAcceleration'] = 'false'
        config.parent.mkdir(parents=True, exist_ok=True)
        write(config, json.dumps(settings, indent=4).encode())
    # One Wine desktop the size of the top screen holds all of Battle.net's windows (and the game's): on its own the
    # launcher's small login window and a full-screen helper window take turns in gamescope's picture (black/white flicker).
    # its background black instead of Wine's blue (OLED); Wine is not running here (Steam is not)
    reg = prefix.parent / 'pfx/user.reg'
    text = reg.read_text(errors='surrogateescape')
    dark = re.sub(r'(\[Control Panel\\\\Colors\][^\[]*?"Background"=)"[^"]*"', r'\1"0 0 0"', text, count=1)
    if dark != text: backup(reg); write(reg, dark.encode(errors='surrogateescape'))
    windows_path = 'C:\\' + LAUNCHER.removeprefix('drive_c/').replace('/', '\\')
    # --in-process-gpu: CEF's own GPU process hangs under Wine on the Thor, the window froze after a few clicks (WineHQ 57635)
    desktop = f'{OPTIONS} /desktop=Battle.net,1920x1080 "{windows_path}" --in-process-gpu'
    entry = data[start:end]
    for key, val in (('Exe', f'"{prefix / "drive_c/windows/explorer.exe"}"'), ('StartDir', f'"{exe.parent}"'), ('LaunchOptions', desktop)):
        entry = re.sub(rb'\x01' + key.encode() + rb'\x00[^\x00]*\x00', lambda _: s(key, val), entry, count=1)
    if entry != data[start:end]:
        backup(path)
        write(path, data[:start] + entry + data[end:])
    # 17.11.: owner wants the window to fill the top screen: Wine at 120 dpi (125 %), the launcher keeps itself maximised
    for name in ('user.reg', 'system.reg'):
        reg = prefix / name
        text = reg.read_text(errors='surrogateescape')
        big = text.replace('"LogPixels"=dword:00000060', '"LogPixels"=dword:00000078')
        if big != text: backup(reg); write(reg, big.encode(errors='surrogateescape'))
    print(f'Battle.net startet jetzt den Launcher; D: = {LIBRARY}')


# 17.11.: WoW Forever's ARM64 client only runs on Proton 11 ARM64 with the copied-syscall ntdll patch
# (github.com/Zensenshi/thor-wow-arm64-proton, tool "Proton-11-ARM64-WoW"); Battle.net does not run on that tool, so WoW
# gets its own entry and asks for the login itself (owner's choice)
WOW_EXE = LIBRARY / 'World of Warcraft/_forever_/Wow-arm64.exe'
WOW_TOOL = 'Proton-11-ARM64-WoW'


def wow():
    path = shortcuts_path()
    old = path.read_bytes()
    if old.find(s('AppName', 'WoW Forever')) >= 0: sys.exit('schon eingetragen')
    if not WOW_EXE.is_file(): sys.exit(f'{WOW_EXE} fehlt')
    turnip = Path.home() / 'wow-arm64-work/turnip-root'
    lib = turnip / 'lib64' if (turnip / 'lib64').is_dir() else turnip / 'lib'
    opts = (f'VK_DRIVER_FILES={turnip}/share/vulkan/icd.d/freedreno_icd.aarch64.json LD_LIBRARY_PATH={lib} LANG=de_DE.UTF-8 '
            '/usr/libexec/armada/armada-game-launch %command% -d3d11')
    backup(path, STEAM / 'config/config.vdf')
    appid = zlib.crc32((f'"{WOW_EXE}"' + 'WoW Forever').encode()) | 0x80000000
    entry = (i('appid', appid) + s('AppName', 'WoW Forever') + s('Exe', f'"{WOW_EXE}"') + s('StartDir', f'"{WOW_EXE.parent}"') + s('icon', '')
             + s('ShortcutPath', '') + s('LaunchOptions', opts) + i('IsHidden', 0) + i('AllowDesktopConfig', 1) + i('AllowOverlay', 1)
             + i('OpenVR', 0) + i('Devkit', 0) + s('DevkitGameID', '') + i('DevkitOverrideAppID', 0) + i('LastPlayTime', 0)
             + s('FlatpakAppID', '') + b'\x00tags\x00\x08')
    write(path, old[:-2] + b'\x00' + str(old.count(b'\x02appid\x00')).encode() + b'\x00' + entry + b'\x08' + b'\x08\x08')
    global TOOL
    TOOL = WOW_TOOL
    map_tool(appid)
    print(f'WoW Forever eingetragen: appid {appid}')


if __name__ == '__main__':
    if steam_running(): sys.exit('Steam läuft – erst beenden (steam -shutdown)')
    if sys.argv[1:2] == ['add'] and len(sys.argv) == 3: add(sys.argv[2])
    elif sys.argv[1:] == ['launcher']: launcher()
    elif sys.argv[1:] == ['wow']: wow()
    else: sys.exit(__doc__)
