#!/usr/bin/env python3
"""Adds Toravo Tandem as a non-Steam shortcut (Steam must not be running). Keeps existing shortcuts; makes a backup."""
import glob, os, shutil, struct, sys, zlib
NAME, EXE = 'Toravo Tandem', os.path.expanduser('~/.local/share/tandem/tandem-launch')
def s(key, val): return b'\x01' + key.encode() + b'\x00' + val.encode() + b'\x00'
def i(key, val): return b'\x02' + key.encode() + b'\x00' + struct.pack('<I', val & 0xffffffff)
appid = zlib.crc32((f'"{EXE}"' + NAME).encode()) | 0x80000000
entry = (i('appid', appid) + s('AppName', NAME) + s('Exe', f'"{EXE}"') + s('StartDir', f'"{os.path.dirname(EXE)}"') + s('icon', '')
         + s('ShortcutPath', '') + s('LaunchOptions', '') + i('IsHidden', 0) + i('AllowDesktopConfig', 1) + i('AllowOverlay', 1)
         + i('OpenVR', 0) + i('Devkit', 0) + s('DevkitGameID', '') + i('DevkitOverrideAppID', 0) + i('LastPlayTime', 0)
         + s('FlatpakAppID', '') + b'\x00tags\x00\x08')
users = glob.glob(os.path.expanduser('~/.local/share/Steam/userdata/[0-9]*'))
if len(users) != 1: sys.exit(f'erwartet genau ein Steam-Konto, gefunden: {len(users)}')
path = users[0] + '/config/shortcuts.vdf'
old = open(path, 'rb').read() if os.path.exists(path) else b'\x00shortcuts\x00\x08\x08'
if NAME.encode() in old: sys.exit('schon eingetragen')
if not old.startswith(b'\x00shortcuts\x00') or not old.endswith(b'\x08\x08'): sys.exit('unbekanntes Format, nichts geändert')
if os.path.exists(path): shutil.copy2(path, path + '.bak-tandem')
count = old.count(b'\x02appid\x00')
new = old[:-2] + b'\x00' + str(count).encode() + b'\x00' + entry + b'\x08' + b'\x08\x08'
os.makedirs(os.path.dirname(path), exist_ok=True)
open(path + '.tmp', 'wb').write(new); os.replace(path + '.tmp', path)
print(f'eingetragen als Nr. {count}, appid {appid}, {len(new)} Bytes')
