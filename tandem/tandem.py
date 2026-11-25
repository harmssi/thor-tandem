#!/usr/bin/env python3
"""Toravo Tandem: dual-screen game launcher for ArmadaOS (AYN Thor). Standard library only.

Serves the UI to two kiosk browser windows (#top / #bottom), keeps them in sync, scans ROM folders in the ES-DE
layout, finds cover art (ES-DE and Cocoon media folders), and starts emulators as child processes so they stay
inside the Steam shortcut that started Tandem.
"""
import argparse, glob, hashlib, json, os, queue, re, shutil, signal, subprocess, sys, threading, time, zipfile, zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import bluetooth  # BlueZ over D-Bus: headphones and a second gamepad, for the settings
import companion  # per-game notes/sketches, guides, visual save states, dual-screen touch, trackpad & uploads
import saves  # rolling local + SSH savegame backups (SD card + optional SSH host)
import telemetry  # battery wattage/playtime, CPU/RAM, PipeWire mixer, dock state & Wake-on-LAN
import thor  # the Thor's own hardware: stick lights, gyro, performance profile
import thor_airpods  # native Apple AirPods AAP (L2CAP 0x1001: ANC/Transparency/Adaptive, L/R/Case battery, ear detection) & BT Low-Latency
import thor_features  # 30s RAM Instant-Replay, 3x4 Macro Pad, Live Cheats, HLTB, Deep-Freeze, Netplay & Heroic GOG/Epic bridge
import thor_perf  # Snapdragon 8 Gen 2 / Adreno 740 performance engine (schedutil/Turbo, GPU lock, bypass charge, Vulkan/FEX env)
import thor_pro  # Zero-idle-RAM AirPlay (UxPlay), IPS/BPS/UPS ROM patcher, CHD/RVZ shrinker, Trophy tracker, Offline Whisper & Mac/PC Pro-Pad
import thor_storage  # integrated Linux/Tandem system backups & live retroactive Android partition shrinker
import thor_translate  # PlayTranslate-style real-time screen OCR & offline/hybrid German game translator
import thor_updater  # Obtainium-class integrated emulator/core updater & automatic game companion provisioner

HOME = Path.home()
HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
RA_REF = 'org.libretro.RetroArch'
RA_CORES = [HOME / '.var/app' / RA_REF / 'config/retroarch/cores', HOME / '.config/retroarch/cores']
# mGBA with gba-duo-wide's wide view (wide-core/). Same file name as the stock core, in a folder of its own: RetroArch
# finds a core's info file by that name, and without one GET_STATUS crashes it (1.22.2).
RA_WIDE_CORE = RA_CORES[0] / 'tandem-wide/mgba_libretro.so'
RA_WIDE = RA_CORES[0].parent / 'system/tandem-wide'  # what it reads: the pack's game.lua and the switch "on"
FLATPAK_DIRS = [Path('/var/lib/flatpak/app'), HOME / '.local/share/flatpak/app']
IMAGES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml'}
VIDEOS = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.mkv': 'video/x-matroska'}


def app(pattern, *args): return ('appimage', pattern, args)
def fp(ref, *args): return ('flatpak', ref, args)
def ra(*cores): return ('retroarch', cores, ())


# Folder name (ES-DE layout) -> display name, hue for tiles without art, file extensions, emulators in order of
# preference. Paths and install kinds follow the Armada Store catalog and docs (armadaos.dev/emulation).
SYSTEMS = {
    'gb': ('Game Boy', 40, 'gb sgb zip 7z', [('RetroArch', ra('gambatte', 'sameboy', 'mgba'))]),
    'gbc': ('Game Boy Color', 275, 'gbc gb zip 7z', [('RetroArch', ra('gambatte', 'sameboy', 'mgba'))]),
    'gba': ('Game Boy Advance', 255, 'gba zip 7z', [('RetroArch', ra('mgba', 'vba_next', 'gpsp'))]),
    'nes': ('NES', 0, 'nes fds unf unif zip 7z', [('RetroArch', ra('nestopia', 'fceumm', 'mesen'))]),
    'famicom': ('Famicom', 5, 'nes fds unf unif zip 7z', [('RetroArch', ra('nestopia', 'fceumm', 'mesen'))]),
    'fds': ('Famicom Disk System', 12, 'fds nes zip 7z', [('RetroArch', ra('nestopia', 'fceumm', 'mesen'))]),
    'snes': ('Super Nintendo', 285, 'sfc smc fig swc bs zip 7z', [('RetroArch', ra('snes9x', 'bsnes', 'snes9x2010'))]),
    'sfc': ('Super Famicom', 280, 'sfc smc fig swc bs zip 7z', [('RetroArch', ra('snes9x', 'bsnes', 'snes9x2010'))]),
    'n64': ('Nintendo 64', 130, 'z64 n64 v64 zip 7z', [('RetroArch', ra('mupen64plus_next', 'parallel_n64'))]),
    'virtualboy': ('Virtual Boy', 355, 'vb vboy zip 7z', [('RetroArch', ra('mednafen_vb'))]),
    'pokemini': ('Pokémon Mini', 50, 'min zip 7z', [('RetroArch', ra('pokemini'))]),
    'gameandwatch': ('Game & Watch', 35, 'mgw zip 7z', [('RetroArch', ra('gw'))]),
    'nds': ('Nintendo DS', 200, 'nds app zip 7z', [('melonDS', app('melonDS*.AppImage')), ('melonDS', fp('net.kuribo64.melonDS')),
                                                   ('RetroArch', ra('melondsds', 'desmume'))]),
    'n3ds': ('Nintendo 3DS', 350, '3ds 3dsx cci cxi cia', [('Azahar', app('Azahar*.AppImage'))]),
    'gc': ('GameCube', 265, 'iso rvz gcm gcz ciso wia', [('Dolphin', fp('org.DolphinEmu.dolphin-emu', '-b', '-e'))]),
    'wii': ('Wii', 190, 'iso rvz wbfs wad gcz ciso wia', [('Dolphin', fp('org.DolphinEmu.dolphin-emu', '-b', '-e'))]),
    'wiiu': ('Wii U', 195, 'wua wud wux rpx', [('Cemu', app('Cemu*.AppImage', '-f', '-g'))]),
    'psx': ('PlayStation', 220, 'chd cue m3u pbp iso img', [('DuckStation', app('DuckStation*.AppImage', '-batch')),
                                                           ('RetroArch', ra('swanstation', 'pcsx_rearmed'))]),
    'ps2': ('PlayStation 2', 235, 'chd iso cso zso', [('ARMSX2', app('ARMSX2*.AppImage'))]),
    'psp': ('PSP', 205, 'iso cso chd pbp', [('PPSSPP', fp('org.ppsspp.PPSSPP')), ('RetroArch', ra('ppsspp'))]),
    'dreamcast': ('Dreamcast', 20, 'chd cdi gdi cue m3u', [('Flycast', fp('org.flycast.Flycast')), ('RetroArch', ra('flycast'))]),
    'naomi': ('Sega NAOMI', 22, 'zip 7z lst bin dat', [('Flycast', fp('org.flycast.Flycast')), ('RetroArch', ra('flycast'))]),
    'atomiswave': ('Atomiswave', 26, 'zip 7z lst bin', [('Flycast', fp('org.flycast.Flycast')), ('RetroArch', ra('flycast'))]),
    'genesis': ('Genesis', 215, 'md gen bin smd zip 7z', [('RetroArch', ra('genesis_plus_gx', 'picodrive'))]),
    'megadrive': ('Mega Drive', 215, 'md gen bin smd zip 7z', [('RetroArch', ra('genesis_plus_gx', 'picodrive'))]),
    'sega32x': ('Sega 32X', 210, '32x bin md zip 7z', [('RetroArch', ra('picodrive'))]),
    'mastersystem': ('Master System', 215, 'sms zip 7z', [('RetroArch', ra('genesis_plus_gx', 'picodrive'))]),
    'sg-1000': ('SG-1000', 212, 'sg zip 7z', [('RetroArch', ra('genesis_plus_gx', 'bluemsx'))]),
    'gamegear': ('Game Gear', 150, 'gg zip 7z', [('RetroArch', ra('genesis_plus_gx'))]),
    'segacd': ('Sega CD', 215, 'chd cue iso m3u', [('RetroArch', ra('genesis_plus_gx', 'picodrive'))]),
    'saturn': ('Saturn', 300, 'chd cue iso m3u', [('Ymir', fp('io.github.strikerx3.ymir')), ('RetroArch', ra('mednafen_saturn', 'yabause'))]),
    'pcengine': ('PC Engine', 25, 'pce chd cue zip 7z', [('RetroArch', ra('mednafen_pce_fast', 'mednafen_pce'))]),
    'pcenginecd': ('PC Engine CD', 28, 'chd cue ccd m3u pce', [('RetroArch', ra('mednafen_pce_fast', 'mednafen_pce'))]),
    'supergrafx': ('SuperGrafx', 32, 'sgx pce zip 7z', [('RetroArch', ra('mednafen_supergrafx', 'mednafen_pce_fast'))]),
    'neogeo': ('Neo Geo', 42, 'zip 7z', [('RetroArch', ra('fbneo', 'mame2003_plus'))]),
    'neogeocd': ('Neo Geo CD', 44, 'chd cue iso m3u', [('RetroArch', ra('neocd', 'fbneo'))]),
    'ngp': ('Neo Geo Pocket', 180, 'ngp zip 7z', [('RetroArch', ra('mednafen_ngp'))]),
    'ngpc': ('Neo Geo Pocket Color', 185, 'ngc ngp zip 7z', [('RetroArch', ra('mednafen_ngp'))]),
    'wonderswan': ('WonderSwan', 202, 'ws zip 7z', [('RetroArch', ra('mednafen_wswan'))]),
    'wonderswancolor': ('WonderSwan Color', 208, 'wsc ws zip 7z', [('RetroArch', ra('mednafen_wswan'))]),
    'arcade': ('Arcade', 5, 'zip 7z', [('RetroArch', ra('fbneo', 'mame2003_plus'))]),
    'mame': ('MAME', 8, 'zip 7z', [('RetroArch', ra('mame2003_plus', 'mame', 'fbneo'))]),
    'fbneo': ('FinalBurn Neo', 5, 'zip 7z', [('RetroArch', ra('fbneo'))]),
    'fba': ('FinalBurn Alpha', 6, 'zip 7z', [('RetroArch', ra('fbneo', 'fbalpha2012'))]),
    'cps': ('Capcom CPS', 38, 'zip 7z', [('RetroArch', ra('fbneo', 'mame2003_plus'))]),
    'cps1': ('Capcom CPS-1', 38, 'zip 7z', [('RetroArch', ra('fbneo', 'mame2003_plus'))]),
    'cps2': ('Capcom CPS-2', 40, 'zip 7z', [('RetroArch', ra('fbneo', 'mame2003_plus'))]),
    'cps3': ('Capcom CPS-3', 42, 'zip 7z', [('RetroArch', ra('fbneo', 'mame2003_plus'))]),
    'atari2600': ('Atari 2600', 18, 'a26 bin zip 7z', [('RetroArch', ra('stella', 'stella2014'))]),
    'atari5200': ('Atari 5200', 16, 'a52 bin zip 7z', [('RetroArch', ra('atari800', 'a5200'))]),
    'atari7800': ('Atari 7800', 14, 'a78 bin zip 7z', [('RetroArch', ra('prosystem'))]),
    'atarilynx': ('Atari Lynx', 34, 'lnx zip 7z', [('RetroArch', ra('handy', 'mednafen_lynx'))]),
    'atarijaguar': ('Atari Jaguar', 2, 'j64 jag zip 7z', [('RetroArch', ra('virtualjaguar'))]),
    '3do': ('3DO', 45, 'chd iso cue m3u', [('RetroArch', ra('opera'))]),
    'colecovision': ('ColecoVision', 225, 'col rom zip 7z', [('RetroArch', ra('bluemsx', 'gearcoleco'))]),
    'intellivision': ('Intellivision', 48, 'int bin zip 7z', [('RetroArch', ra('freeintv'))]),
    'vectrex': ('Vectrex', 195, 'vec zip 7z', [('RetroArch', ra('vecx'))]),
    'odyssey2': ('Odyssey 2', 30, 'bin zip 7z', [('RetroArch', ra('o2em'))]),
    'msx': ('MSX', 218, 'rom mx1 dsk zip 7z', [('RetroArch', ra('bluemsx', 'fmsx'))]),
    'msx2': ('MSX2', 222, 'rom mx2 dsk zip 7z', [('RetroArch', ra('bluemsx', 'fmsx'))]),
    'amiga': ('Amiga', 165, 'adf lha hdf zip', [('RetroArch', ra('puae'))]),
    'amiga600': ('Amiga 600', 165, 'adf lha hdf zip', [('RetroArch', ra('puae'))]),
    'amiga1200': ('Amiga 1200', 168, 'adf lha hdf zip', [('RetroArch', ra('puae'))]),
    'amigacd32': ('Amiga CD32', 172, 'chd cue iso lha', [('RetroArch', ra('puae'))]),
    'c64': ('Commodore 64', 212, 'd64 t64 prg crt tap zip', [('RetroArch', ra('vice_x64sc', 'vice_x64'))]),
    'zxspectrum': ('ZX Spectrum', 340, 'tzx tap z80 sna zip', [('RetroArch', ra('fuse'))]),
    'amstradcpc': ('Amstrad CPC', 115, 'dsk sna cpr zip', [('RetroArch', ra('cap32', 'crocods'))]),
    'dos': ('MS-DOS', 60, 'dosz zip exe com bat conf', [('RetroArch', ra('dosbox_pure'))]),
    'scummvm': ('ScummVM', 142, 'scummvm svm', [('ScummVM', fp('org.scummvm.ScummVM')), ('RetroArch', ra('scummvm'))]),
    'doom': ('DOOM', 0, 'wad iwad pwad', [('RetroArch', ra('prboom'))]),
    'quake': ('Quake', 25, 'pak', [('RetroArch', ra('tyrquake'))]),
    'pico8': ('PICO-8', 325, 'p8 png zip', [('RetroArch', ra('fake08', 'retro8'))]),
    'switch': ('Switch', 355, 'nsp xci nsz', [('Eden', app('Eden*.AppImage', '-f', '-g'))]),  # not in the Armada Store: Tandem's own updater fetches it
    'port': ('Ports', 28, '', []),  # no folder of ROMs: the games in PORTS
}
# Native ports: games built for this device (ports/<folder>/build.sh), which install.sh puts next to Tandem's own folder.
# id -> (title, folder, argument for the folder's "run" script, the game's bottom screen in ui/decks or None).
# A port is listed once its folder is installed; its game data is the player's own and "run" finds it.
PORTS_DIR = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'tandem-ports'
PORTS = {'halflife': ('Half-Life', 'halflife', 'valve', 'hev'), 'opfor': ('Half-Life: Opposing Force', 'halflife', 'gearbox', 'hev'),
         'bshift': ('Half-Life: Blue Shift', 'halflife', 'bshift', 'hev'), 'aok': ('Age of Kings', 'aok', '', 'aok'),
         'ra2': ('Red Alert 2', 'ra2', 'ra2', 'ra2'), 'ra2yr': ("Red Alert 2: Yuri's Revenge", 'ra2', 'yr', 'ra2'),
         'cnc': ('Command & Conquer', 'cnc', 'td', 'cnc'), 'cncra': ('Command & Conquer: Red Alert', 'cnc', 'ra', 'cnc'),
         'homm3': ('Heroes of Might and Magic III', 'homm3', '', 'homm3'), 'kknd2': ('KKnD 2: Krossfire', 'kknd2', '', 'kknd2'),
         'd2': ('Diablo II', 'd2', '', 'd2')}
# The Steam release each port's data comes from: its artwork in Steam's library cache gives the port its tile.
PORT_ART = {'halflife': 70, 'opfor': 50, 'bshift': 130, 'aok': 221380, 'ra2': 2229850, 'ra2yr': 2229850, 'cnc': 2229830, 'cncra': 2229840,  # the 1995/96 originals (C&C Ultimate Collection), not the Remastered
           
            'homm3': 297000, 'kknd2': 1292180}
# Where a port's game listens for its deck (ports/tandem_deck.h, see README "Deck-Socket"); one game runs at a time.
DECK_SOCKET = Path(os.environ.get('XDG_RUNTIME_DIR') or STATE) / 'tandem-deck.sock'
# Apps offered in the Apps tab when installed: (label, kind, target, args)
APPS = [('Firefox', 'cmd', 'firefox', ()), ('Heroic', 'cmd', 'heroic', ('--no-sandbox',)), ('ES-DE', 'appimage', 'ES-DE*.AppImage', ()),
        ('Moonlight', 'flatpak', 'com.moonlight_stream.Moonlight', ()), ('Chiaki', 'flatpak', 'io.github.streetpea.Chiaki4deck', ()),
        ('RetroArch', 'flatpak', RA_REF, ()), ('Prism Launcher', 'flatpak', 'org.prismlauncher.PrismLauncher', ())]
# Media apps: mpv (Flathub io.mpv.Mpv) plays full screen on top, the app's deck (ui/decks/<deck>.py) browses and steers it
# over mpv's IPC socket and gets the controller's navigation. The socket is in /tmp: mpv's sandbox sees the host's /tmp.
MEDIA_SOCKET = Path(f'/tmp/tandem-mpv-{os.getuid()}.sock')
YT_FORMAT = 'bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/bv*[height<=1080]+ba/b[height<=1080]/b'  # = FORMAT in ui/decks/youtube.py
MPV_ARGS = ('--gpu-context=x11egl', '--idle=yes', '--force-window=yes', '--fullscreen', '--image-display-duration=inf', f'--input-ipc-server={MEDIA_SOCKET}', '--hwdec=v4l2m2m-copy', '--ytdl=yes', '--ytdl-format=' + YT_FORMAT,  # yt-dlp only when a direct load fails (YouTube pages)
            '--really-quiet', '--script-opts=osc-idlescreen=no', '--cache=yes', '--demuxer-max-bytes=150MiB', '--sub-auto=no')  # quiet: no addresses in launch.log
MEDIA_APPS = {'YouTube': 'youtube', 'Plex': 'plex', 'Aufnahmen': 'gallery'}
PCSTREAM_APPS = {'Moonlight', 'Chiaki'}
APPS += [(name, 'flatpak', 'io.mpv.Mpv', MPV_ARGS) for name in MEDIA_APPS]
def steam_apps(path):
    """Names, kinds and install folders from Steam's appinfo.vdf (binary). Only the first 'name', 'type' and 'installdir'
    of each entry are read; that is enough for a list of the library."""
    import struct
    try: data = Path(path).read_bytes()
    except OSError: return {}
    magic, _, = struct.unpack_from('<II', data, 0)
    pos, keys = 8, None
    if magic == 0x07564429:  # since 2024 the keys sit in a table at the end, values refer to them by number
        table, = struct.unpack_from('<q', data, 8); pos = 16
        count, = struct.unpack_from('<I', data, table)
        names = data[table + 4:].split(b'\0')[:count]
        keys = {k: b'\x01' + struct.pack('<I', names.index(k.encode())) for k in ('name', 'type', 'installdir') if k.encode() in names}
    elif magic in (0x07564427, 0x07564428): keys = {k: b'\x01' + k.encode() + b'\0' for k in ('name', 'type', 'installdir')}
    else: return {}
    head = 60 if magic != 0x07564427 else 40  # bytes between the size field and the entry's values
    apps = {}
    while pos + 8 <= len(data):
        appid, size = struct.unpack_from('<II', data, pos)
        if not appid: break
        blob = data[pos + 8 + head:pos + 8 + size]; pos += 8 + size
        entry = {}
        for key, mark in keys.items():
            at = blob.find(mark)
            if at >= 0: entry[key] = blob[at + len(mark):blob.index(b'\0', at + len(mark))].decode(errors='replace')
        if entry.get('name'): apps[str(appid)] = entry
    return apps


def steam_shortcuts(steam):
    """(appid, name, grid folder) of each non-Steam shortcut in Steam's shortcuts.vdf (binary), Tandem's own left out."""
    import struct
    found = []
    for path in glob.glob(str(steam / 'userdata/[0-9]*/config/shortcuts.vdf')):
        try: data = Path(path).read_bytes()
        except OSError: continue
        for m in re.finditer(rb'\x02appid\x00(.{4})\x01(?i:appname)\x00([^\x00]*)\x00', data, re.S):
            name = m[2].decode(errors='replace')
            if name != 'Toravo Tandem': found.append((str(struct.unpack('<I', m[1])[0]), name, Path(path).parent / 'grid'))
    return found


def shortcut_direct(vdf, appid):
    """Direct [exe, *args] for a native Linux shortcut (BananaNative) so Tandem runs it without booting Steam."""
    import shlex, struct
    try: data = Path(vdf).read_bytes()
    except OSError: return None
    mark = b'\x02appid\x00' + struct.pack('<I', int(appid))
    at = data.find(mark)
    if at < 0: return None
    nxt = data.find(b'\x02appid\x00', at + len(mark))
    chunk = data[at:nxt if nxt >= 0 else len(data)]
    exe_m = re.search(rb'\x01(?i:exe)\x00([^\x00]*)\x00', chunk)
    opt_m = re.search(rb'\x01(?i:launchoptions)\x00([^\x00]*)\x00', chunk)
    exe = exe_m[1].decode(errors='replace').strip().strip('"') if exe_m else ''
    low = exe.lower()
    if ('bananative' not in low and 'peanuts' not in low) or not os.access(exe, os.X_OK): return None
    opts = opt_m[1].decode(errors='replace') if opt_m else ''
    tail = opts.split('%command%', 1)[1] if '%command%' in opts else ''
    try: return [exe, *shlex.split(tail)]
    except ValueError: return [exe]


def app_icon(kind, target):
    """The app's own icon file (its .desktop Icon= in the hicolor theme, or the flatpak's exported one), biggest first."""
    name = target if kind == 'flatpak' else None
    if kind == 'cmd':
        for desktop in glob.glob('/usr/share/applications/*.desktop') + glob.glob(str(HOME / '.local/share/applications/*.desktop')):
            try: text = Path(desktop).read_text(errors='ignore')
            except OSError: continue
            exe, icon = re.search(r'^Exec=(\S+)', text, re.M), re.search(r'^Icon=(.+)$', text, re.M)
            if exe and icon and os.path.basename(exe[1]) == target: name = icon[1].strip(); break
    if not name: return None
    if name.startswith('/'): return name if Path(name).suffix.lower() in IMAGES and os.path.isfile(name) else None
    for theme in ('/usr/share/icons/hicolor', HOME / '.local/share/flatpak/exports/share/icons/hicolor', '/var/lib/flatpak/exports/share/icons/hicolor'):
        for size in ('512x512', '256x256', '128x128', 'scalable'):
            for ext in ('.png', '.svg'):
                if os.path.isfile(f := f'{theme}/{size}/apps/{name}{ext}'): return f
    return None


def steam_art(steam, appid, name):
    """A picture from Steam's librarycache: <appid>/<name>, <appid>_<name>, or (newer Steam) <appid>/<hash>/<name>, where
    the 600x900 cover is called library_capsule.jpg."""
    base = steam / 'appcache/librarycache'
    found = [base / appid / name, base / f'{appid}_{name}'] + sorted(glob.glob(str(base / appid / '*' / name)))
    if name == 'library_600x900.jpg': found += sorted(glob.glob(str(base / appid / '*/library_capsule.jpg')))
    return next((str(f) for f in found if os.path.isfile(f)), None)


STEAM_TOOLS = re.compile(r'^(Proton|Steam Linux Runtime|Steamworks Common|SteamVR|Steam Controller)', re.I)


def ident(*parts): return hashlib.sha1('\0'.join(parts).encode()).hexdigest()[:12]


def clean(stem):
    """'Golden Sun (Germany) [!]' -> 'Golden Sun'; 'Legend of Zelda, The - X' -> 'The Legend of Zelda - X'."""
    title = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', stem).strip(' -_.') or stem
    return re.sub(r'^(.*?), (The|Der|Die|Das|A|An)\b', r'\2 \1', title)


def which(name):
    for folder in os.environ.get('PATH', '/usr/bin').split(os.pathsep):
        if os.access(os.path.join(folder, name), os.X_OK): return os.path.join(folder, name)


def find_appimage(pattern):
    for folder in ('Applications', '.local/share/applications', '.local/bin', 'bin'):
        hits = sorted(glob.glob(str(HOME / folder / pattern)))
        if hits: return hits[-1]


def has_flatpak(ref): return any((d / ref).is_dir() for d in FLATPAK_DIRS)


def resolve(kind, target, args):
    """Command prefix for one emulator/app, or (None, reason)."""
    if kind == 'cmd':
        path = which(target)
        return ([path, *args], None) if path else (None, f'{target} ist nicht installiert')
    if kind == 'appimage':
        path = find_appimage(target)
        return ([path, *args], None) if path else (None, 'nicht installiert')
    if kind == 'flatpak':
        return (['flatpak', 'run', target, *args], None) if has_flatpak(target) else (None, 'nicht installiert')
    if not has_flatpak(RA_REF): return None, 'nicht installiert'
    for core in target:
        for folder in RA_CORES:
            if (folder / f'{core}_libretro.so').is_file():
                return ['flatpak', 'run', RA_REF, '-L', str(folder / f'{core}_libretro.so')], None
    return None, f'RetroArch-Core fehlt ({target[0]}): im RetroArch-Online-Updater laden'


def rom_identity(path):
    """(game code, CRC32) of a Game Boy or GBA ROM, as companion packs name them; (None, None) if it cannot be read."""
    try:
        if str(path).lower().endswith('.zip'):
            with zipfile.ZipFile(path) as z:
                info = max(z.infolist(), key=lambda i: i.file_size)
                with z.open(info) as f: head = f.read(0x150)
                crc = info.CRC
        else:
            with open(path, 'rb') as f:
                head = f.read(0x150)
                crc = zlib.crc32(head)
                while chunk := f.read(1 << 20): crc = zlib.crc32(chunk, crc)
    except (OSError, ValueError, zipfile.BadZipFile): return None, None
    text = lambda a, b: ''.join(chr(c) for c in head[a:b].split(b'\0')[0] if 0x20 <= c <= 0x7E).strip()
    if len(head) >= 0x150 and head[0x104:0x108] == b'\xce\xed\x66\x66':  # Game Boy: like mGBA's GBGetGameCode
        return ('CGB-' if head[0x143] == 0xC0 else 'DMG-') + (text(0x13F, 0x143).ljust(4, '?') if head[0x14B] == 0x33 else '????'), crc
    return text(0xAC, 0xB0), crc


def find_pack_info(game, assigned=None):
    """Return `(pack_id, other_region, candidates)` for a GB/GBC/GBA ROM using GBADuo v1.0.1 exact + multi-region rules."""
    packs = CONFIG.parent / 'packs'
    if game.get('s') not in ('gb', 'gbc', 'gba') or not game.get('path') or not packs.is_dir():
        return None, False, []
    if assigned == '__off__':
        return None, False, []
    installed = companion.list_installed_packs(CONFIG.parent)
    if not installed:
        return None, False, []
    code, crc = rom_identity(game['path'])
    if code is None:
        return None, False, []
    hint = f"{game.get('t', '')} {Path(game['path']).stem}"
    m = companion.match_packs_for_rom(code, crc, title_hint=hint, installed=installed, catalog=None)
    cands = [x['id'] for x in (m['exact_installed'] + m['other_installed'])]
    if assigned and assigned != '__art__':
        if (packs / assigned / 'manifest.json').is_file():
            is_other = any(x['id'] == assigned for x in m['other_installed']) or (assigned not in [x['id'] for x in m['exact_installed']])
            return assigned, is_other, cands
    return m['best_installed'], m['best_other_region'], cands


def find_pack(game):
    """The companion pack (a folder in ~/.config/tandem/packs) made for this ROM: exact match first, then GBADuo v1.0.1 multi-region."""
    return find_pack_info(game)[0]


def ensure_game_pack(game, assigned=None):
    """If the user launches a GB/GBC/GBA game whose companion pack is available in `khumam/gba-duo-companions`
    but not installed yet, download & unpack it immediately (<1 s) so it works on first launch."""
    if assigned == '__off__' or game.get('s') not in ('gb', 'gbc', 'gba') or not game.get('path'):
        return None, False, []
    pack, other_reg, cands = find_pack_info(game, assigned=assigned)
    if pack or not load_config().get('auto_packs', True):
        return pack, other_reg, cands
    code, crc = rom_identity(game['path'])
    if not code:
        return None, False, []
    catalog = companion.fetch_gbaduo_catalog(force=False, timeout=4)
    if not catalog:
        return None, False, []
    hint = f"{game.get('t', '')} {Path(game['path']).stem}"
    m = companion.match_packs_for_rom(code, crc, title_hint=hint, installed=[], catalog=catalog)
    if m['best_web']:
        wp, _ = m['best_web']
        res = companion.download_catalog_pack(wp, cfg_dir=CONFIG.parent, timeout=8)
        if res.get('ok'):
            return find_pack_info(game, assigned=assigned)
    return None, False, []


def wide_core(cmd, pack, on):
    """Wide view (gba-duo-wide's game.lua wide()): when the pack describes the game's world and the wide core is installed,
    leave the script and the switch where that core reads them (wide-core/README.md) and start it instead of mGBA.
    Returns (cmd, on); on is None when there is no wide view and the command stays as it was."""
    folder = CONFIG.parent / 'packs' / pack
    try:
        at = cmd.index('-L') + 1
        script = folder / Path(str(json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))['gameScript'])).name
        stock = Path(cmd[at]).name  # Game Boy games usually start in Gambatte; their wide view needs this mGBA
        if stock not in ('mgba_libretro.so', 'gambatte_libretro.so', 'sameboy_libretro.so') or not RA_WIDE_CORE.is_file(): return cmd, None
        if not re.search(r'^function\s+wide\s*\(', script.read_text(encoding='utf-8'), re.M): return cmd, None
        shutil.rmtree(RA_WIDE, ignore_errors=True)
        RA_WIDE.mkdir(parents=True)
        for lua in folder.glob('*.lua'): shutil.copy(lua, RA_WIDE)  # pack.require looks beside the script
        shutil.copy(script, RA_WIDE / 'game.lua')
        (RA_WIDE / 'on').write_text('1' if on else '0')
        if stock != 'mgba_libretro.so':  # RetroArch keeps saves per core: one file for both, so no progress is left behind
            saves = RA_CORES[0].parent / 'saves'
            old, new = (saves / {'g': 'Gambatte', 's': 'SameBoy'}[stock[0]] / (Path(cmd[-1]).stem + '.srm')), saves / 'mGBA' / (Path(cmd[-1]).stem + '.srm')
            if old.is_file() and not new.exists() and not new.is_symlink():
                new.parent.mkdir(parents=True, exist_ok=True); new.symlink_to(old)
    except (OSError, ValueError, KeyError): return cmd, None
    return cmd[:at] + [str(RA_WIDE_CORE)] + cmd[at + 1:], bool(on)


def emulators_for(system):
    """List every usable emulator / RetroArch core option for `system` -> [{'id', 'emu', 'label', 'cmd'}]."""
    if system not in SYSTEMS or system == 'port': return []
    out, seen = [], set()
    for label, (kind, target, args) in SYSTEMS[system][3]:
        if kind == 'retroarch':
            if not has_flatpak(RA_REF): continue
            for core in target:
                for folder in RA_CORES:
                    so = folder / f'{core}_libretro.so'
                    if so.is_file() and f'ra:{core}' not in seen:
                        seen.add(f'ra:{core}')
                        out.append({'id': f'ra:{core}', 'emu': 'RetroArch', 'label': f'RetroArch ({core})',
                                    'cmd': ['flatpak', 'run', RA_REF, '-L', str(so)]})
                        break
        else:
            cmd, _ = resolve(kind, target, args)
            if cmd and label not in seen:
                seen.add(label)
                out.append({'id': label, 'emu': label, 'label': label, 'cmd': cmd})
    return out


def emulator(system, prefer=None):
    """(label, command prefix) of the preferred or first usable emulator, or (None, what to install)."""
    if system == 'port': return 'Port', []
    emus = SYSTEMS[system][3]
    if not emus: return None, 'Für dieses System bietet der Armada Store keinen Emulator.'
    if prefer:
        hit = next((e for e in emulators_for(system) if e['id'] == prefer), None)
        if hit: return hit['emu'], hit['cmd']
    reasons = []
    for label, (kind, target, args) in emus:
        cmd, why = resolve(kind, target, args)
        if cmd: return label, cmd
        reasons.append(f'{label}: {why}')
    return None, 'Emulator fehlt (unter Apps oder im Armada Store installieren) – ' + '; '.join(dict.fromkeys(reasons))


MEDIA = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'tandem/media'  # art Tandem fetched itself
# Folder -> playlist name on thumbnails.libretro.com (free box art and screenshots, named after No-Intro/Redump sets)
LIBRETRO = {'gb': 'Nintendo - Game Boy', 'gbc': 'Nintendo - Game Boy Color', 'gba': 'Nintendo - Game Boy Advance',
            'nes': 'Nintendo - Nintendo Entertainment System', 'famicom': 'Nintendo - Nintendo Entertainment System',
            'fds': 'Nintendo - Family Computer Disk System',
            'snes': 'Nintendo - Super Nintendo Entertainment System', 'sfc': 'Nintendo - Super Nintendo Entertainment System',
            'n64': 'Nintendo - Nintendo 64', 'virtualboy': 'Nintendo - Virtual Boy', 'pokemini': 'Nintendo - Pokemon Mini',
            'nds': 'Nintendo - Nintendo DS', 'n3ds': 'Nintendo - Nintendo 3DS', 'gc': 'Nintendo - GameCube',
            'wii': 'Nintendo - Wii', 'wiiu': 'Nintendo - Wii U', 'psx': 'Sony - PlayStation', 'ps2': 'Sony - PlayStation 2',
            'psp': 'Sony - PlayStation Portable', 'dreamcast': 'Sega - Dreamcast', 'genesis': 'Sega - Mega Drive - Genesis',
            'megadrive': 'Sega - Mega Drive - Genesis', 'sega32x': 'Sega - 32X',
            'mastersystem': 'Sega - Master System - Mark III', 'sg-1000': 'Sega - SG-1000', 'gamegear': 'Sega - Game Gear',
            'segacd': 'Sega - Mega-CD - Sega CD', 'saturn': 'Sega - Saturn',
            'pcengine': 'NEC - PC Engine - TurboGrafx 16', 'pcenginecd': 'NEC - PC Engine CD - TurboGrafx-CD',
            'supergrafx': 'NEC - PC Engine SuperGrafx', 'neogeo': 'SNK - Neo Geo', 'neogeocd': 'SNK - Neo Geo CD',
            'ngp': 'SNK - Neo Geo Pocket', 'ngpc': 'SNK - Neo Geo Pocket Color',
            'wonderswan': 'Bandai - WonderSwan', 'wonderswancolor': 'Bandai - WonderSwan Color',
            'atari2600': 'Atari - 2600', 'atari5200': 'Atari - 5200', 'atari7800': 'Atari - 7800',
            'atarilynx': 'Atari - Lynx', 'atarijaguar': 'Atari - Jaguar', '3do': 'The 3DO Company - 3DO',
            'colecovision': 'Coleco - ColecoVision', 'intellivision': 'Mattel - Intellivision', 'vectrex': 'GCE - Vectrex',
            'odyssey2': 'Magnavox - Odyssey2', 'msx': 'Microsoft - MSX', 'msx2': 'Microsoft - MSX2',
            'amiga': 'Commodore - Amiga', 'amiga600': 'Commodore - Amiga', 'amiga1200': 'Commodore - Amiga',
            'amigacd32': 'Commodore -CD32', 'c64': 'Commodore - 64', 'zxspectrum': 'Sinclair - ZX Spectrum',
            'amstradcpc': 'Amstrad - CPC', 'dos': 'DOS', 'scummvm': 'ScummVM', 'doom': 'DOOM',
            'arcade': 'FBNeo - Arcade Games', 'fbneo': 'FBNeo - Arcade Games', 'fba': 'FBNeo - Arcade Games',
            'cps': 'FBNeo - Arcade Games', 'cps1': 'FBNeo - Arcade Games', 'cps2': 'FBNeo - Arcade Games', 'cps3': 'FBNeo - Arcade Games',
            'mame': 'MAME'}

SYS_ALIASES = {'sfc': ['snes'], 'snes': ['sfc'], 'famicom': ['nes'], 'nes': ['famicom'],
               'megadrive': ['genesis'], 'genesis': ['megadrive'], 'n3ds': ['3ds'], 'gc': ['gamecube'],
               'psx': ['ps1'], 'port': ['windows', 'pc'], 'fba': ['fbneo', 'arcade'],
               'cps': ['arcade', 'fbneo'], 'cps1': ['arcade', 'fbneo'], 'cps2': ['arcade', 'fbneo'], 'cps3': ['arcade', 'fbneo']}


def _box_candidates(stem):
    """Candidate No-Intro / Redump names on libretro-thumbnails (exact stem first, then German/European/US retail boxes)."""
    clean_n = lambda s: re.sub(r'[&*/:`<>?\\|"]', '_', s)
    out = [clean_n(stem)]
    s2 = re.sub(r'\s*(\((?:Rev\s*[\w.]+|v[\d.]+|Uncensored|Enhanced|Beta|Proto)\)|\[[^\]]*\])+\s*$', '', stem, flags=re.I).strip()
    if s2 and clean_n(s2) not in out: out.append(clean_n(s2))
    s3 = re.sub(r'\s*\([A-Z][a-z](?:,[A-Z][a-z])+\)', '', s2).strip()
    if s3 and clean_n(s3) not in out: out.append(clean_n(s3))
    base = re.sub(r'\s*\([^)]*\)', '', s3).strip()
    if base:
        for reg in ('(Germany)', '(Europe)', '(USA, Europe)', '(USA)', '(World)'):
            cand = clean_n(f'{base} {reg}')
            if cand not in out: out.append(cand)
    return out[:6]


def _norm_box_title(t):
    s = re.sub(r'\s*\((?:PeanutsNative|BananaNative)\)\s*$', '', str(t or ''), flags=re.I)
    s = s.replace('Evoli', 'Eevee').replace('’', "'")
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def _switch_box_index(fetch_url):
    """Download GameTDB's Switch XML once and return {normalized_title: 5-letter-code}, preferring ALL/EUR/DEU editions."""
    import io
    raw = fetch_url('https://www.gametdb.com/switchtdb.zip', timeout=12)
    if not raw or raw[:2] != b'PK': return {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            xml = zf.read(zf.namelist()[0]).decode('utf-8', errors='ignore')
    except (OSError, zipfile.BadZipFile, IndexError): return {}
    best = {}
    for blk in re.findall(r'<game name="[^"]+">.*?</game>', xml, re.S):
        cid = re.search(r'<id>([A-Z0-9]{4,6})</id>', blk)
        if not cid: continue
        code = cid.group(1)
        reg = (re.search(r'<region>([^<]+)</region>', blk) or [None, ''])[1].upper()
        gname = (re.search(r'<game name="([^"]+)"', blk) or [None, ''])[1]
        score = (3 if any(r in reg for r in ('ALL', 'EUR', 'DEU', 'GER')) else 2 if 'USA' in reg else 1)
        if '[' in gname or 'Edition' in gname or 'Double Pack' in gname: score -= 1
        for title in re.findall(r'<title>([^<]+)</title>', blk):
            nt = _norm_box_title(title)
            if nt and score > best.get(nt, (-9, ''))[0]:
                best[nt] = (score, code)
    return {k: v[1] for k, v in best.items()}


def scrape(games):
    """Fetch missing original retail boxart (and fallback covers/snaps) from libretro-thumbnails and GameTDB."""
    import concurrent.futures, urllib.parse, urllib.request
    miss_file = STATE / 'boxart-miss.json'
    now = int(time.time())
    try: miss = {k: int(v) for k, v in json.loads(miss_file.read_text()).items() if now - int(v) < 7 * 86400}
    except (OSError, ValueError, TypeError, AttributeError): miss = {}
    miss_lock = threading.Lock()

    def fetch_url(url, timeout=10):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Tandem/0.5 (game launcher)'})
            with urllib.request.urlopen(req, timeout=timeout) as reply:
                return reply.read()
        except OSError:
            return None

    def fetch_libretro(playlist, kind, cand):
        repo = urllib.parse.quote(playlist.replace(' ', '_'))
        enc = urllib.parse.quote(cand)
        for base_u in (f'https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/{kind}/{enc}.png',
                       f'https://thumbnails.libretro.com/{urllib.parse.quote(playlist)}/{kind}/{enc}.png'):
            data = fetch_url(base_u, timeout=8)
            if data and data[:4] == b'\x89PNG': return data
        return None

    def retro_job(game):
        playlist = LIBRETRO.get(game['s'])
        if not playlist or 'path' not in game: return 0
        stem = Path(game['path']).stem
        got = 0
        box_target = MEDIA / game['s'] / 'boxes' / f'{stem}.png'
        mkey = f'{game["s"]}:{stem}'
        if not game.get('box') and not box_target.is_file() and mkey not in miss:
            data = None
            for cand in _box_candidates(stem):
                data = fetch_libretro(playlist, 'Named_Boxarts', cand)
                if data: break
            if data:
                box_target.parent.mkdir(parents=True, exist_ok=True)
                box_target.write_bytes(data)
                got += 1
            else:
                with miss_lock: miss[mkey] = now
        if not game.get('cover'):
            cov_target = MEDIA / game['s'] / 'covers' / f'{stem}.png'
            if box_target.is_file() and not cov_target.is_file():
                cov_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(box_target, cov_target)
            snap_target = MEDIA / game['s'] / 'snaps' / f'{stem}.png'
            if not snap_target.is_file():
                sdata = fetch_libretro(playlist, 'Named_Snaps', _box_candidates(stem)[0])
                if sdata:
                    snap_target.parent.mkdir(parents=True, exist_ok=True)
                    snap_target.write_bytes(sdata)
        return got

    found = 0
    retro_todo = [g for g in games if LIBRETRO.get(g.get('s')) and 'path' in g and (not g.get('box') or not g.get('cover'))]
    if retro_todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            found += sum(pool.map(retro_job, retro_todo))

    sw_todo = [g for g in games if (g.get('s') == 'switch' or g.get('native_engine')) and not g.get('box')]
    if sw_todo:
        sw_idx = None
        for g in sw_todo:
            bkey = g.get('tid') or (Path(g['path']).stem if g.get('path') else g['id'])
            mkey = f'switch:{bkey}'
            if mkey in miss or any((MEDIA / 'switch/boxes' / f'{bkey}{ext}').is_file() for ext in ('.png', '.jpg')):
                continue
            if sw_idx is None: sw_idx = _switch_box_index(fetch_url)
            nt = _norm_box_title(g.get('t'))
            code = sw_idx.get(nt)
            if not code and len(nt) >= 12:
                code = next((c for k, c in sw_idx.items() if k.startswith(nt + ' ')), None)
            saved = False
            if code:
                for kind, ext, sig in (('box', '.png', b'\x89PNG'), ('coverM', '.jpg', b'\xff\xd8\xff')):
                    for lang in ('DE', 'EN', 'US', 'JA'):
                        data = fetch_url(f'https://art.gametdb.com/switch/{kind}/{lang}/{code}{ext}', timeout=8)
                        if data and data.startswith(sig):
                            out = MEDIA / 'switch/boxes' / f'{bkey}{ext}'
                            out.parent.mkdir(parents=True, exist_ok=True)
                            out.write_bytes(data)
                            found += 1; saved = True; break
                    if saved: break
            if not saved:
                miss[mkey] = now

    try:
        STATE.mkdir(parents=True, exist_ok=True)
        miss_file.write_text(json.dumps(miss))
    except OSError: pass
    return found


def _find_switch_box(keys):
    for key in keys:
        if not key: continue
        for ext in ('.png', '.jpg', '.jpeg', '.webp'):
            p = MEDIA / 'switch/boxes' / f'{key}{ext}'
            if p.is_file(): return str(p)
    return None


_LAST_ROOTS = []


class Library:
    def __init__(self, roots, steam):
        global _LAST_ROOTS
        _LAST_ROOTS = list(roots or [])
        self.roots, self.steam, self.media, self.games, self.lock = roots, steam, {}, {}, threading.Lock()

    def _media_index(self, folder, exts=IMAGES):
        """stem -> file for one media folder; Cocoon appends '__cocoon_edit_<n>_<hash>' to the ROM stem."""
        index = {}
        try:
            for entry in os.scandir(folder):
                if Path(entry.name).suffix.lower() in exts:
                    index[Path(entry.name).stem.split('__cocoon_edit_')[0]] = entry.path
        except OSError: pass
        return index

    def _art(self, root, system):
        base = Path(root).parent
        cover, box, hero, logo, shot, vid = {}, {}, {}, {}, {}, {}
        sys_names = list(reversed([system] + SYS_ALIASES.get(system, [])))  # primary system name wins over alias
        for sname in sys_names:
            for media, covers, boxes, heroes, logos, shots, vids in reversed((
                    (base / 'ES-DE/downloaded_media', ('covers', 'miximages', 'screenshots'), ('3dboxes', 'covers'), ('fanart', 'screenshots'), ('marquees', 'wheel'), ('screenshots',), ('videos',)),
                    (HOME / 'ES-DE/downloaded_media', ('covers', 'miximages', 'screenshots'), ('3dboxes', 'covers'), ('fanart', 'screenshots'), ('marquees', 'wheel'), ('screenshots',), ('videos',)),
                    (base / 'Cocoon/downloaded_media', ('icon', 'screenshot_title'), (), ('hero', 'screenshot_gameplay'), ('logo',), ('screenshot_gameplay', 'screenshot_title'), ('videos', 'video')),
                    (MEDIA, ('covers', 'boxes'), ('boxes', 'covers'), ('snaps',), (), ('snaps',), ()))):
                for kinds, target in ((covers, cover), (boxes, box), (heroes, hero), (logos, logo), (shots, shot)):
                    for kind in reversed(kinds):  # earlier names win
                        target.update(self._media_index(media / sname / kind))
                for vkind in reversed(vids):
                    vid.update(self._media_index(media / sname / vkind, VIDEOS))
        return cover, box, hero, logo, shot, vid

    def _gamelist(self, root, system):
        """stem -> {'name', 'desc', 'genre', 'dev', 'year', 'ttb'} from Cocoon or ES-DE gamelist.xml."""
        import xml.etree.ElementTree as ET
        base = Path(root).parent
        meta = {}
        sys_names = list(reversed([system] + SYS_ALIASES.get(system, [])))
        for sname in sys_names:
            for xml_path in (Path(root) / sname / 'gamelist.xml', base / f'ES-DE/gamelists/{sname}/gamelist.xml',
                             HOME / f'ES-DE/gamelists/{sname}/gamelist.xml', base / f'Cocoon/gamelists/{sname}/gamelist.xml'):
                if not xml_path.is_file(): continue
                try:
                    raw = xml_path.read_text(encoding='utf-8', errors='replace')
                    # Strip undeclared namespace prefixes (e.g. cocoon:timetobeathastily) so ElementTree parses cleanly
                    raw = re.sub(r'<(/?)[a-zA-Z0-9_]+:([a-zA-Z0-9_]+)', r'<\1\2', raw)
                    tree = ET.fromstring(raw)
                except (OSError, ET.ParseError): continue
                for g in tree.findall('game'):
                    p = (g.findtext('path') or '').strip()
                    if not p: continue
                    stem = Path(p).stem
                    info = meta.setdefault(stem, {})
                    for k, tag in (('name', 'name'), ('desc', 'desc'), ('genre', 'genre'), ('dev', 'developer')):
                        v = (g.findtext(tag) or '').strip()
                        if v: info[k] = v
                    if not info.get('dev'):
                        pub = (g.findtext('publisher') or '').strip()
                        if pub: info['dev'] = pub
                    rd = (g.findtext('releasedate') or '').strip()
                    if len(rd) >= 4 and rd[:4].isdigit() and int(rd[:4]) > 1971:
                        info['year'] = rd[:4]
                    ttb = (g.findtext('timetobeathastily') or '').strip()
                    if ttb.isdigit() and int(ttb) >= 600:
                        info['ttb'] = round(int(ttb) / 3600, 1)
        return meta

    def _system_art(self, system):
        """Platform artwork of a Cocoon theme on the card (assets/smart_folders/<pack>/smart_folders/by_platform/<system>/)."""
        names = [system] + SYS_ALIASES.get(system, [])
        for root in self.roots:
            for name in names:
                for folder in sorted(glob.glob(str(Path(root).parent / f'Cocoon/assets/smart_folders/*/smart_folders/by_platform/{name}'))):
                    art = {kind: str(Path(folder) / f'{kind}.png') for kind in ('icon', 'hero', 'logo') if (Path(folder) / f'{kind}.png').is_file()}
                    if art: return art
        return {}

    def _overlay_art(self, system):
        """Platform tile frame (mask.png + overlay.png) of a Cocoon icon-overlay pack on the card."""
        names = [system] + SYS_ALIASES.get(system, [])
        for root in self.roots:
            for name in names:
                for folder in sorted(glob.glob(str(Path(root).parent / f'Cocoon/assets/icon_overlays/*/icon_overlays/{name}'))):
                    mask, over = Path(folder) / 'mask.png', Path(folder) / 'overlay.png'
                    if mask.is_file() and over.is_file(): return {'mask': str(mask), 'overlay': str(over)}
        return {}

    def _image(self, path):
        if not path: return None
        try: stamp = os.path.getmtime(path)  # a replaced cover gets a new address: pages keep images for a day
        except OSError: stamp = 0
        token = ident(f'{path}:{stamp}') + Path(path).suffix.lower()
        self.media[token] = path
        return 'media/' + token

    @staticmethod
    def _norm_switch_key(text):
        s = re.sub(r'\s*\((?:PeanutsNative|BananaNative)\)\s*$', '', str(text or ''), flags=re.I)
        s = re.sub(r'\s*\[[^\]]*\]', '', s)
        return re.sub(r'[^a-z0-9]+', '', s.lower())

    def _match_switch_media(self, tid, title, media_map):
        if not media_map: return None
        tid_up = (tid or '').upper()
        if tid_up:
            for stem, fp in media_map.items():
                if tid_up in stem.upper():
                    return fp
        norm_t = self._norm_switch_key(title)
        if len(norm_t) >= 4:
            for stem, fp in media_map.items():
                ns = self._norm_switch_key(stem)
                if ns and (ns == norm_t or (len(ns) >= 7 and (ns.startswith(norm_t) or norm_t.startswith(ns)))):
                    return fp
        return None

    def scan(self):
        games, media = {}, {}
        self.media = media
        for root in self.roots:
            for system, (name, hue, exts, _) in SYSTEMS.items():
                folder = Path(root) / system
                if not folder.is_dir(): continue
                cover, box, hero, logo, shot, vid = self._art(root, system)
                gmeta = self._gamelist(root, system)
                wanted = {'.' + e for e in exts.split()}
                entries = sorted((e for e in os.scandir(folder) if not e.name.startswith('.') and e.is_file()), key=lambda e: e.name.lower())
                # Multi-disc .m3u playlists hide their individual disc files so multi-disc games appear once
                m3u_discs = set()
                if '.m3u' in wanted:
                    for e in entries:
                        if e.name.lower().endswith('.m3u'):
                            try:
                                for ln in Path(e.path).read_text(errors='ignore').splitlines():
                                    ln = ln.strip()
                                    if ln and not ln.startswith('#'): m3u_discs.add(os.path.basename(ln).lower())
                            except OSError: pass
                for entry in entries:
                    path = Path(entry.path)
                    if path.suffix.lower() not in wanted or entry.name.lower() in m3u_discs: continue
                    gid = ident(system, entry.name)
                    b_raw = box.get(path.stem)
                    if not b_raw and system == 'switch':
                        sw_tid = re.search(r'\[([0-9A-Fa-f]{16})\]', entry.name)
                        b_raw = _find_switch_box([sw_tid.group(1).upper() if sw_tid else '', path.stem])
                    c_img, h_img = self._image(cover.get(path.stem) or b_raw), self._image(hero.get(path.stem) or cover.get(path.stem) or b_raw)
                    b_img = self._image(b_raw)
                    l_img, s_img = self._image(logo.get(path.stem)), self._image(shot.get(path.stem))
                    v_file = self._image(vid.get(path.stem))
                    gm = gmeta.get(path.stem) or {}
                    title = clean(gm['name']) if gm.get('name') else clean(path.stem)
                    game = {'id': gid, 't': title, 's': system, 'path': entry.path, 'cover': c_img, 'hero': h_img}
                    if b_img: game['box'] = b_img
                    if l_img: game['logo'] = l_img
                    if s_img and s_img not in (h_img, c_img): game['shot'] = s_img
                    if v_file: game['video'] = v_file
                    for mk in ('desc', 'genre', 'dev', 'year', 'ttb'):
                        if gm.get(mk): game[mk] = gm[mk]
                    games[gid] = game
        for manifest in glob.glob(str(self.steam / 'steamapps/appmanifest_*.acf')):
            text = Path(manifest).read_text(errors='ignore')
            appid, name = re.search(r'"appid"\s+"(\d+)"', text), re.search(r'"name"\s+"([^"]+)"', text)
            if not appid or not name or STEAM_TOOLS.match(name[1]): continue
            number = lambda key: int((re.search(rf'"{key}"\s+"(\d+)"', text) or [0, 0])[1])
            loading = not number('StateFlags') & 4  # 4 = fully installed
            done, total = number('BytesDownloaded') + number('BytesStaged'), number('BytesToDownload') + number('BytesToStage')
            gid = 'steam' + appid[1]
            s_logo = self._image(steam_art(self.steam, appid[1], 'logo.png'))
            games[gid] = {'id': gid, 't': name[1], 's': 'steam', 'appid': appid[1], 'cover': self._image(steam_art(self.steam, appid[1], 'library_600x900.jpg')),
                          'hero': self._image(steam_art(self.steam, appid[1], 'library_hero.jpg')), **({'logo': s_logo} if s_logo else {})}
            if loading: games[gid].update(inst='load', pct=round(100 * done / total) if total else None)
        sw_cov, sw_box, sw_hero, sw_logo, sw_shot = {}, {}, {}, {}, {}
        for root in self.roots:
            c0, b0, h0, l0, s0, _ = self._art(root, 'switch')
            sw_cov.update(c0); sw_box.update(b0); sw_hero.update(h0); sw_logo.update(l0); sw_shot.update(s0)
        seen_native_dirs, seen_native_tids = set(), set()
        for appid, name, grid in steam_shortcuts(self.steam):  # Battle.net and other launchers: they want a login, keys go along
            art = lambda n: self._image(str(grid / n)) if (grid / n).is_file() else None
            direct = shortcut_direct(grid.parent / 'shortcuts.vdf', appid)
            sc_logo = art(f'{appid}_logo.png') or art(f'{appid}_logo.jpg')
            entry = {'id': 'steam' + appid, 't': name, 's': 'steam',
                     'cover': art(f'{appid}p.png') or art(f'{appid}p.jpg'), 'hero': art(f'{appid}_hero.png') or art(f'{appid}_hero.jpg'),
                     **({'logo': sc_logo} if sc_logo else {})}
            if direct:
                entry['direct'] = direct
                entry['native_engine'] = 'PeanutsNative' if 'peanuts' in direct[0].lower() else 'BananaNative'
                sc_tid = ''
                for arg in direct[1:]:
                    try: seen_native_dirs.add(str(Path(arg).resolve()))
                    except OSError: pass
                    for m in re.finditer(r'([0-9A-Fa-f]{16})-work', str(arg)):
                        sc_tid = m.group(1).upper()
                        seen_native_tids.add(sc_tid)
                if sc_tid:
                    entry['tid'] = sc_tid
                    sc_box = self._image(_find_switch_box([sc_tid, 'steam' + appid]) or self._match_switch_media(sc_tid, name, sw_box))
                    if sc_box: entry['box'] = sc_box
                    if not entry.get('cover'):
                        entry['cover'] = self._image(self._match_switch_media(sc_tid, name, sw_cov)) or sc_box
                    if not entry.get('hero'):
                        entry['hero'] = self._image(self._match_switch_media(sc_tid, name, sw_hero)) or entry.get('cover')
                    if not entry.get('logo'):
                        ml = self._image(self._match_switch_media(sc_tid, name, sw_logo))
                        if ml: entry['logo'] = ml
                    ms = self._image(self._match_switch_media(sc_tid, name, sw_shot))
                    if ms and ms not in (entry.get('hero'), entry.get('cover')): entry['shot'] = ms
            else: entry.update(appid=appid, gameid=str(int(appid) << 32 | 0x02000000), keys=True)
            games['steam' + appid] = entry
        for np in companion.discover_native_packs(self.roots, HOME):
            try: rdir = str(Path(np['dir']).resolve())
            except OSError: rdir = np['dir']
            try: pdir = str(Path(np.get('pack_dir') or np['dir']).resolve())
            except OSError: pdir = np.get('pack_dir') or np['dir']
            if rdir in seen_native_dirs or pdir in seen_native_dirs or np['tid'].upper() in seen_native_tids: continue
            seen_native_dirs.update((rdir, pdir))
            seen_native_tids.add(np['tid'].upper())
            nid = 'native-' + np['tid'].lower()
            tid_up = np['tid'].upper()
            hi_cov = self._image(self._match_switch_media(tid_up, np['title'], sw_cov))
            hi_hero = self._image(self._match_switch_media(tid_up, np['title'], sw_hero))
            hi_logo = self._image(self._match_switch_media(tid_up, np['title'], sw_logo))
            hi_shot = self._image(self._match_switch_media(tid_up, np['title'], sw_shot))
            np_cov = hi_cov or self._image(np['cover'])
            np_box = self._image(np.get('box') or _find_switch_box([tid_up, nid]) or self._match_switch_media(tid_up, np['title'], sw_box))
            ng = {'id': nid, 't': np['title'], 's': 'switch', 'tid': tid_up, 'direct': np['direct'],
                  'native_engine': np['engine'], 'cover': np_cov or np_box, 'hero': hi_hero or hi_shot or np_cov or np_box,
                  **({'box': np_box} if np_box else {}), **({'logo': hi_logo} if hi_logo else {})}
            if hi_shot and hi_shot != ng['hero']: ng['shot'] = hi_shot
            games[nid] = ng
        for port, (title, folder, _, deck) in PORTS.items():
            if not (PORTS_DIR / folder / 'run').is_file(): continue
            own = PORTS_DIR / folder / 'dist/art/cover.png'  # art the port brings itself (no Steam release to borrow from)
            art = lambda n: (lambda f: self._image(str(f)) if f.is_file() else None)(own if own.is_file() else self.steam / f'appcache/librarycache/{PORT_ART.get(port)}/{n}')
            mine = PORTS_DIR / 'art' / f'{port}.jpg'  # a cover of its own: Red Alert 2 and Yuri's Revenge share a folder and one Steam bundle (owner 19.11.)
            p_logo = self._image(steam_art(self.steam, str(PORT_ART.get(port)), 'logo.png')) if PORT_ART.get(port) else None
            games['port-' + port] = {'id': 'port-' + port, 't': title, 's': 'port', 'port': port,
                                     'cover': self._image(str(mine)) if mine.is_file() else art('library_600x900.jpg'), 'hero': art('library_hero.jpg'),
                                     **({'logo': p_logo} if p_logo else {})}
        # Only installed Steam games (from appmanifest_*.acf & shortcuts.vdf above) are shown in Tandem.
        for ext_g in thor_features.discover_external_pc_games(HOME):
            if ext_g['id'] not in games:
                cov_tok = self._image(ext_g.get('cover_path'))
                games[ext_g['id']] = {
                    'id': ext_g['id'], 't': ext_g['t'], 's': 'steam',
                    'store': ext_g['store'], 'direct': ext_g['direct'],
                    'cover': cov_tok, 'hero': cov_tok,
                }
        pdb = companion.load_protondb_cache()
        hltb = thor_features.load_hltb_cache()
        for gid, gm in games.items():
            if gm.get('appid') and (pdb.get(str(gm['appid'])) or {}).get('tier'):
                gm['protondb'] = pdb[str(gm['appid'])]['tier']
            if not gm.get('ttb') and gm.get('appid') and (hltb.get(str(gm['appid'])) or {}).get('ttb'):
                gm['ttb'] = hltb[str(gm['appid'])]['ttb']
            ca = companion.custom_art_paths(gid)
            if ca.get('cover'):
                gm['cover'] = self._image(ca['cover'])
            if ca.get('hero'):
                gm['hero'] = self._image(ca['hero'])
        moments_dir = STATE / 'moments'
        if moments_dir.is_dir():
            for gid, gm in games.items():
                mp = moments_dir / f'{gid}.jpg'
                if mp.is_file():
                    m_tok = self._image(str(mp))
                    gm['moment'] = m_tok
                    if not gm.get('hero'):
                        gm['hero'] = m_tok
        with self.lock: self.games = games
        return games

    def payload(self, saved):
        systems = {}
        for g in self.games.values():
            if g['s'] != 'steam': systems[g['s']] = systems.get(g['s'], 0) + 1
        info, overlays = {}, {}
        for s, n in systems.items():
            label, cmd = emulator(s)
            art = self._system_art(s)
            info[s] = {'name': SYSTEMS[s][0], 'hue': SYSTEMS[s][1], 'n': n, 'emu': label, 'missing': None if label else cmd,
                       'cover': self._image(art.get('icon') or art.get('logo')), 'hero': self._image(art.get('hero')),
                       **({'logo': self._image(art['logo'])} if art.get('logo') else {})}
        for s in (*systems.keys(), 'steam'):
            ov = self._overlay_art(s)
            if ov: overlays[s] = {'mask': self._image(ov['mask']), 'overlay': self._image(ov['overlay'])}
        apps = [{'id': 'app' + str(i), 't': a[0], 's': 'app', 'icon': self._image(app_icon(*a[1:3]) if a[0] not in MEDIA_APPS else None)}
                for i, a in enumerate(APPS) if resolve(*a[1:])[0]]
        emus = {s: [{'id': e['id'], 'label': e['label']} for e in emulators_for(s)] for s in systems}
        public = [{k: v for k, v in g.items() if k not in ('path', 'direct')} for g in self.games.values()]
        return {'systems': info, 'overlays': overlays, 'emulators': emus, 'games': public, 'apps': apps,
                'fav': saved.get('fav', []), 'pinned': saved.get('pinned', []), 'played': saved.get('played', {}),
                'sessions': saved.get('sessions', {}), 'collections': saved.get('collections', {}),
                'hidden': saved.get('hidden', []), 'sort': saved.get('sort', 'recent'),
                'gameopt': saved.get('gameopt', {}), 'extras': extras_state()}


def focused_window():
    """The window the top compositor currently shows (X id), or 0."""
    match = re.search(r'= (\d+)', run_quiet(['xprop', '-root', 'GAMESCOPE_FOCUSED_WINDOW']))
    return int(match[1]) if match else 0


def hide_steam(tandem):
    """The Steam client runs unseen for downloads and Steam games, but it opens its big window whenever it likes, and
    the compositor would show that instead of Tandem. Its main window is taken off the screen as soon as it gets
    there; Steam's dialogs (a licence to accept, a missing file) stay, they need an answer. For five minutes after a
    Steam game is started the main window stays too: some questions (cloud saves out of step) are asked in there."""
    seen = 0
    while True:
        time.sleep(1.5)
        window = focused_window()
        if not window or window == seen or time.time() < tandem.steam_show: continue
        seen = window
        props = run_quiet(['xprop', '-id', str(window), 'WM_CLASS', 'WM_NAME'])
        if '"steamwebhelper"' in props and re.search(r'WM_NAME\S* = "Steam"', props):
            x_window('unmap', window); seen = 0  # it may come back under the same number


X_QUIET = None  # kept alive for Xlib


def x_window(action, window):
    """Hide ('unmap'), show ('map') or politely close ('close' via WM_DELETE_WINDOW) another program's X11 window."""
    import ctypes
    try:
        x = ctypes.CDLL('libX11.so.6')
        x.XOpenDisplay.restype = ctypes.c_void_p
        display = x.XOpenDisplay((os.environ.get('DISPLAY') or ':0').encode())
        if not display: return False
        # Xlib's own reaction to an error (a window that is gone by now) is to end the whole program: replace it.
        global X_QUIET
        X_QUIET = X_QUIET or ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(lambda *_: 0)
        x.XSetErrorHandler(X_QUIET)
        if action == 'close':
            x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            x.XInternAtom.restype = ctypes.c_ulong
            wm_proto = x.XInternAtom(display, b'WM_PROTOCOLS', 0)
            wm_del = x.XInternAtom(display, b'WM_DELETE_WINDOW', 0)
            ev = (ctypes.c_long * 24)(33, 0, 1, 0, window, wm_proto, 32, wm_del, 0)  # ClientMessage = 33, format = 32
            x.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]
            x.XSendEvent(display, window, 0, 0, ctypes.byref(ev))
        else:
            call = x.XUnmapWindow if action == 'unmap' else x.XMapWindow
            call.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            call(display, window)
        x.XFlush.argtypes = x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XSync(display, 0); x.XCloseDisplay(display)  # XSync: errors arrive while the quiet handler is in place
        return True
    except OSError: return False


def x_windows_matching(*needles):
    """X11 window IDs on the top gamescope server whose WM_CLASS or WM_NAME contains any needle (case-insensitive)."""
    env = {**os.environ, 'DISPLAY': os.environ.get('DISPLAY') or ':0'}
    try: raw = subprocess.run(['xprop', '-root', 'GAMESCOPE_FOCUSABLE_WINDOWS'], env=env, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError): return []
    seen, found = set(), []
    for wid in re.findall(r'\d{5,}', raw):
        n = int(wid)
        if n in seen: continue
        seen.add(n)
        try: props = subprocess.run(['xprop', '-id', wid, 'WM_CLASS', 'WM_NAME'], env=env, capture_output=True, text=True, timeout=2).stdout.lower()
        except (OSError, subprocess.SubprocessError): continue
        if any(k.lower() in props for k in needles): found.append(n)
    return found


class Tandem:
    def __init__(self, library, dry=False):
        self.library, self.dry = library, dry
        self.ui, self.run, self.proc, self.clients, self.lock = {'tab': 0, 'sys': None, 'i': 0}, None, None, [], threading.Lock()
        self.power_open = False  # True while the long-press power menu sits in front: routes pad input to Tandem
        self.prompt_open = False  # True while the bottom screen's text prompt is open: routes pad input to its keyboard
        self.swkbd = None  # Active native Switch software-keyboard request waiting for the bottom screen
        self.swkbd_seq = 0
        self.steam_show = 0  # until when Steam's own window may show, see hide_steam
        self.mirror = None  # Wii U: the GamePad picture on the bottom screen
        self.home_window = 0  # Tandem's own top window, noted when a game starts
        self.moments = companion.MomentTracker(STATE)  # rolling gameplay snapshotter ("Zuletzt im Spiel", menu-free)
        self.setup = {'open': not SETUP_MARK.exists(), 'step': 0}  # the first-run assistant on the screens (see setup_info)
        STATE.mkdir(parents=True, exist_ok=True)
        try: self.saved = json.loads((STATE / 'state.json').read_text())
        except (OSError, ValueError): self.saved = {}
        if not self.saved.get('played') and not self.saved.get('fav'): self.ui['tab'] = 1  # nothing played yet: open on the systems

    def save(self):
        tmp = STATE / 'state.json.tmp'
        tmp.write_text(json.dumps(self.saved))
        os.replace(tmp, STATE / 'state.json')

    def snapshot(self):
        sk = {k: v for k, v in self.swkbd.items() if k != 'event'} if self.swkbd else None
        return {'ui': self.ui, 'run': self.run, 'setup': self.setup, 'doze': bool(DOZE), 'power': self.power_open, 'prompt': self.prompt_open, 'swkbd': sk}

    def sync_gba_packs_bg(self, force=False):
        """Automatically provision & update game companions (Steam mods, GBADuo packs, RetroArch UDP & dual-screen layouts)."""
        if self.dry:
            return
        cfg = load_config()
        if not cfg.get('auto_companions', True) and not cfg.get('auto_packs', True):
            return
        def work():
            res = thor_updater.sync_all_companions(
                list(self.library.games.values()), rom_identity,
                roots=self.library.roots, home=HOME, cfg_dir=CONFIG.parent,
                apply_updates=True, force_catalog=force,
            )
            changes = res.get('changes') or []
            self.publish('updater', updater_state(self))
            if changes:
                self.publish('library')
                self.publish('toast', {'text': f'Begleiter automatisch eingerichtet: {", ".join(changes[:3])}.'})
        threading.Thread(target=work, daemon=True).start()

    def ask_swkbd(self, data):
        with self.lock:
            if self.swkbd:
                self.swkbd['ok'] = False
                self.swkbd['event'].set()
            self.swkbd_seq += 1
            title = str(data.get('title') or '').strip()
            sub = str(data.get('sub') or '').strip()
            guide = str(data.get('guide') or '').strip()
            label = f'{title} — {sub}' if title and sub and sub != title else (title or sub or guide or 'Text eingeben')
            initial = str(data.get('initial') or '')
            max_c = max(0, int(data.get('max') or 0)) if isinstance(data.get('max'), (int, float)) else 0
            min_c = max(0, int(data.get('min') or 0)) if isinstance(data.get('min'), (int, float)) else 0
            if max_c and len(initial) > max_c:
                initial = initial[:max_c]
            ev = threading.Event()
            req = {'id': self.swkbd_seq, 'title': label[:90], 'guide': guide[:90], 'initial': initial,
                   'min': min_c, 'max': max_c, 'ok': False, 'text': '', 'event': ev}
            self.swkbd = req
            self.prompt_open = True
        if DOZE:
            doze(False, self)
        self.publish('swkbd', {'open': True, **{k: v for k, v in req.items() if k != 'event'}})
        ev.wait(timeout=600)
        with self.lock:
            if self.swkbd is req:
                self.swkbd = None
                self.prompt_open = False
        return {'ok': bool(req['ok']), 'text': req['text']}

    def finish_swkbd(self, req_id=None, ok=False, text=''):
        with self.lock:
            req = self.swkbd
            if not req or (req_id is not None and req['id'] != req_id):
                return {'ok': False}
            text = str(text or '')
            if req['max'] and len(text) > req['max']:
                text = text[:req['max']]
            req['ok'] = bool(ok)
            req['text'] = text if ok else ''
            self.swkbd = None
            self.prompt_open = False
            req['event'].set()
        self.publish('swkbd', {'open': False, 'id': req['id']})
        return {'ok': True}

    def publish(self, kind='state', data=None):
        message = json.dumps({'kind': kind, **(data if data is not None else self.snapshot())})
        for q in list(self.clients):
            try: q.put_nowait(message)
            except queue.Full: pass

    def command(self, game):
        if game.get('direct'): return game.get('native_engine') or 'BananaNative', game['direct']
        if game['s'] == 'steam': return 'Steam', ['steam', '-silent', f'steam://rungameid/{game.get("gameid") or game["appid"]}']  # no Steam window, only the game
        if game['s'] == 'port': return 'Port', [str(PORTS_DIR / PORTS[game['port']][1] / 'run'), PORTS[game['port']][2]]
        prefer = (self.saved.get('gameopt', {}).get(game['id']) or {}).get('emu')
        label, cmd = emulator(game['s'], prefer)
        return (label, cmd + [game['path']]) if label else (None, cmd)

    def launch(self, gid):
        if DOZE and not self.dry:
            doze(False, self)
        with self.lock:
            if self.run: return {'error': 'Es ist noch ein Spiel offen – erst fortsetzen oder beenden.' if self.run.get('paused') else 'Es läuft schon ein Spiel.'}
            if gid in ('term', 'ai:claude', 'ai:agy'):
                found = next(((which(name), args) for name, args in TERMINALS if which(name)), None)
                layout = region_layout()
                ai_tool = gid[3:] if gid.startswith('ai:') else ''
                title = ('Claude Code (Skip Permissions)' if ai_tool == 'claude'
                         else 'Google Antigravity · agy (Skip Permissions)' if ai_tool == 'agy'
                         else 'Terminal')
                game = {'id': gid, 't': title, 's': 'term', 'layout': layout, **({'ai': ai_tool} if ai_tool else {})}
                if found:
                    if ai_tool:
                        script = write_ai_launcher(ai_tool)
                        label, cmd = title, [found[0], *found[1], '-e', str(script)]
                    else:
                        label, cmd = 'Terminal', [found[0], *found[1]]
                    run_quiet(['setxkbmap', layout])  # the layout decides what the on-screen keys type
                else:
                    label, cmd = None, 'Kein Terminal-Programm gefunden.'
            elif gid == 'propad':
                game = {'id': 'propad', 't': 'Pro-Controller (Mac & PC)', 's': 'app', 'media': {'deck': 'propad', 'pad': False}}
                label, cmd = 'Pro-Pad', [sys.executable, '-c', 'import time\nwhile True: time.sleep(3600)']
                if not self.dry:
                    thor_pro.PROPAD.start()
            elif gid == 'airplay:top':
                if thor_pro.AIRPLAY.running():
                    res_ap = thor_pro.AIRPLAY.stop()
                else:
                    res_ap = thor_pro.AIRPLAY.start('top', game_running=False)
                return {'ok': True, 'cmd': [], 'tracked': False, 'text': res_ap.get('error') or res_ap.get('text', '')}
            elif gid.startswith('app') and gid[3:].isdigit() and int(gid[3:]) < len(APPS):
                entry = APPS[int(gid[3:])]
                game, (label, (cmd, why)) = {'id': gid, 't': entry[0], 's': 'app'}, (entry[0], resolve(*entry[1:]))
                if entry[0] in MEDIA_APPS: game['media'] = {'deck': MEDIA_APPS[entry[0]], 'socket': str(MEDIA_SOCKET), 'pad': True}
                elif entry[0] in PCSTREAM_APPS: game['media'] = {'deck': 'pcstream', 'pad': False}
                if not cmd: label, cmd = None, why
            else:
                game = self.library.games.get(gid)
                if not game: return {'error': 'Spiel nicht gefunden – Bibliothek neu einlesen.'}
                if game.get('inst') == 'load': return {'error': f'„{game["t"]}“ wird noch geladen.'}
                if game.get('inst') == 'no': return self.steam_install(game)
                label, cmd = self.command(game)
                if game['s'] == 'steam' and not game.get('direct'): self.steam_show = time.time() + 300
                if game['t'] == 'WoW Forever' and not self.dry: wow_login()  # its own login, as under Android (no Battle.net hand-over on ARM64)
                if game.get('keys'): game = {**game, 'layout': region_layout()}; run_quiet(['setxkbmap', game['layout']])  # as for the terminal
            if not label: return {'error': cmd}
            assigned_pack = self.saved.get('pack_assign', {}).get(gid)
            if label == 'RetroArch':
                pack, pack_other, pack_cands = (find_pack_info(game, assigned=assigned_pack) if self.dry
                                                else ensure_game_pack(game, assigned=assigned_pack))
            else:
                pack, pack_other, pack_cands = None, False, []
            if not self.dry and game.get('s') == 'steam' and str(game.get('appid') or '') in ('377840', '377160', '1687950') and load_config().get('auto_companions', True):
                st_comp = (thor_updater.load_state().get('steam_companions') or {})
                if not any(v.get('installed_sha') for v in st_comp.values() if isinstance(v, dict)):
                    try:
                        thor_updater.sync_steam_companions(home=HOME, roots=self.library.roots, apply_updates=True, only_appid=str(game.get('appid')))
                    except Exception:
                        pass
            wide = None
            if pack: cmd, wide = wide_core(cmd, pack, self.saved.get('wide', {}).get(gid, False))
            if not self.dry: self.home_window = focused_window()
            raw_opt = self.saved.get('gameopt', {}).get(gid) or {}
            opt = thor_perf.smart_game_opt(game, raw_opt)
            cfg_now = load_config()
            prof = opt.get('profile') or ('Turbo' if label in ('BananaNative', 'PeanutsNative') else ('Eco' if cfg_now.get('travel_mode') else ''))
            fps = opt.get('fps') if opt.get('fps') in FPS_LIMITS and opt.get('fps') else base_panel_hz(cfg_now)
            res_h = int(opt.get('res') or 0) if opt.get('res') in RENDER_RES else 0
            scale = opt.get('scale') if opt.get('scale') in SCALING_FILTERS else ('sgsr' if res_h else 'linear')
            low_lat = bool(cfg_now.get('low_latency', True))
            is_dual = bool((game['s'] == 'wiiu') or (game['s'] == 'nds' and label == 'melonDS') or (game['s'] == 'n3ds' and label == 'Azahar'))
            with open(STATE / 'launch.log', 'ab') as log:  # the child keeps its own copy of the handle
                log.write(f'\n== {time.strftime("%F %T")} {game["t"]}: {cmd}\n'.encode()); log.flush()
                if not self.dry:
                    if game.get('s') not in ('term', 'app') and load_config().get('cloud_saves', True):
                        cs_res = saves.sync_before_launch(game, label, load_config().get('save_target', saves.DEFAULT_TARGET))
                        if cs_res.get('pulled'):
                            self.publish('toast', {'text': cs_res['text']})
                    env = None
                    if label == 'RetroArch':
                        ra_res = companion.configure_retroarch(cfg_now, game=game, opt=opt)
                        if '--set-shader' not in cmd:
                            cmd = [*cmd[:-1], '--set-shader', ra_res.get('shader_path') or '', cmd[-1]]
                        np_args = thor_features.netplay_cli_args()
                        if np_args:
                            cmd = [*cmd[:-1], *np_args, cmd[-1]]
                    if is_dual:
                        env = {**os.environ, 'DISABLE_GAMESCOPE_WSI': '1'}
                        if game['s'] == 'wiiu': cemu_pad_window()
                        else: companion.setup_dual_emu(game['s'], label)
                    if game['s'] == 'port': env = {**os.environ, 'TANDEM_DECK_SOCKET': str(DECK_SOCKET)}
                    if label in ('BananaNative', 'PeanutsNative'):
                        env = {**os.environ, 'DISPLAY': os.environ.get('DISPLAY') or ':0',
                               'WAYLAND_DISPLAY': os.environ.get('WAYLAND_DISPLAY') or 'gamescope-0',
                               'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'}
                    if game.get('s') not in ('term', 'app'):
                        env = thor_perf.game_env(env if env is not None else os.environ, opt, game.get('s', ''), low_latency=low_lat, engine_label=label)
                        if game.get('s') == 'steam' and not game.get('direct'):
                            threading.Thread(target=thor.sync_steam_compat, daemon=True).start()
                        elif ARMADA_LAUNCH.is_file() and cmd and cmd[0] != str(ARMADA_LAUNCH) and game.get('s') in ('port', 'steam', 'ps2', 'wiiu', 'n3ds', 'psp'):
                            cmd = [str(ARMADA_LAUNCH), *cmd]
                        thor_perf.set_tandem_isolation(True)
                    if prof: thor.change('profile', prof)
                    if fps: apply_fps_limit(fps)
                    apply_low_latency(low_lat)
                    apply_render_res(res_h)
                    if scale != 'linear': apply_scaling_filter(scale)
                    stopping = getattr(self, 'steam_stopping', None)
                    if game['s'] == 'steam' and not game.get('direct') and stopping and stopping.is_alive():  # a start sent to a Steam that is shutting down is lost
                        stopping.join(60)
                        for _ in range(30):  # 'steam -shutdown' can return before the client is gone
                            try: alive = os.path.isdir('/proc/' + (HOME / '.steam/steam.pid').read_text().strip())
                            except OSError: alive = False
                            if not alive: break
                            time.sleep(1)
                    try: self.proc = subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, env=env)
                    except OSError as error:
                        thor_perf.set_tandem_isolation(False)
                        return {'error': f'Start fehlgeschlagen: {error}'}
                    if game.get('s') not in ('term', 'app'):
                        thor_perf.pin_game_tree(self.proc.pid, 'big')
                    if game.get('direct') or game['s'] not in ('steam', 'app'): (STATE / 'running').write_text(f'{self.proc.pid} {start_time(self.proc.pid)}')
            played = self.saved.setdefault('played', {}).setdefault(gid, {'secs': 0})
            played['last'] = int(time.time())
            self.save()
            tracked = game['s'] != 'app' or 'media' in game  # apps hand off to another process right away; the player stays
            if tracked:
                fp_id = cmd[2] if len(cmd) >= 3 and Path(cmd[0]).name == 'flatpak' and cmd[1] == 'run' else None
                comp_key = companion.resolve_native_companion(game)
                self.run = {'id': gid, 't': game['t'], 's': game['s'], 'emu': label, 'since': int(time.time()), 'hero': game.get('hero'),
                            'layout': game.get('layout'), 'appid': game.get('appid'), 'tid': game.get('tid'), 'keys': game.get('keys'),
                            'companion': comp_key,
                            'deck': f'deck/{game["appid"]}.html' if game.get('appid') and (HERE / f'decks/{game["appid"]}.html').is_file() else None,
                            'pack': pack, 'pack_other_region': pack_other, 'pack_candidates': pack_cands,
                            'pack_mode': 'art' if assigned_pack == '__art__' else 'pack',
                            'wide': wide, 'dual': is_dual, 'profile': prof, 'fps': fps, 'scale': scale, 'res': res_h,
                            'shader': opt.get('shader') or '',
                            **({'flatpak': fp_id} if fp_id else {}),
                            'port': game.get('media') or ({'deck': PORTS[game['port']][3], 'socket': str(DECK_SOCKET)} if game['s'] == 'port' else None)}
                if not self.dry: threading.Thread(target=self.watch, args=(self.proc, gid, game.get('appid')), daemon=True).start()
                if not self.dry and game['s'] not in ('app', 'term'):
                    self.moments.start(self, gid)
                    if load_config().get('replay_buffer', False):
                        dpys = _x11_displays()
                        thor_features.REPLAY.start(dpys[0] if dpys else ':0')
                if not self.dry and game['s'] == 'wiiu' and load_config().get('wiiu_ffplay'):
                    threading.Thread(target=self.mirror_pad, args=(gid,), daemon=True).start()
        self.publish()
        return {'ok': True, 'cmd': cmd, 'tracked': tracked}

    def gameopt(self, data):
        """Per-game emulator/core, performance profile, frame-rate cap and scaling filter: remembered in state.json."""
        gid_req = data.get('id') if isinstance(data.get('id'), str) else None
        with self.lock:
            run = self.run
            gid = gid_req or (run['id'] if run else None)
            if not gid: return {'error': 'Es läuft kein Spiel.'}
            game = self.library.games.get(gid)
            opt = self.saved.setdefault('gameopt', {}).setdefault(gid, {})
            emu_id, prof, fps, scale, res_h = data.get('emu'), data.get('profile'), data.get('fps'), data.get('scale'), data.get('res')
            if emu_id is not None and game:
                valid_ids = {e['id'] for e in emulators_for(game['s'])}
                if emu_id == '' or emu_id is False: opt.pop('emu', None)
                elif emu_id in valid_ids: opt['emu'] = emu_id
                else: return {'error': 'Unbekannter Emulator.'}
            if prof is not None:
                if prof not in ('', *thor.PROFILES): return {'error': 'Unbekanntes Leistungsprofil.'}
                if prof: opt['profile'] = prof
                else: opt.pop('profile', None)
                if run and run['id'] == gid:
                    run['profile'] = opt.get('profile') or ('Turbo' if run.get('emu') in ('BananaNative', 'PeanutsNative') else '')
            if fps is not None:
                if fps not in FPS_LIMITS: return {'error': 'unbekannte Einstellung'}
                if fps: opt['fps'] = int(fps)
                else: opt.pop('fps', None)
                if run and run['id'] == gid: run['fps'] = int(fps)
            if scale is not None:
                if scale not in SCALING_FILTERS: return {'error': 'unbekannte Einstellung'}
                if scale != 'linear': opt['scale'] = scale
                else: opt.pop('scale', None)
                if run and run['id'] == gid: run['scale'] = scale
            if res_h is not None:
                if res_h not in RENDER_RES: return {'error': 'unbekannte Einstellung'}
                if res_h: opt['res'] = int(res_h)
                else: opt.pop('res', None)
                if run and run['id'] == gid: run['res'] = int(res_h)
            shader = data.get('shader')
            if shader is not None:
                if shader not in ('', *companion.RA_SHADERS): return {'error': 'unbekannte Einstellung'}
                if shader: opt['shader'] = shader
                else: opt.pop('shader', None)
                if run and run['id'] == gid: run['shader'] = shader or ''
            for flag in ('tu_deck_emu', 'tu_sysmem', 'fex_fast', 'fex_tso'):
                if flag in data:
                    if data[flag]: opt[flag] = True
                    else: opt.pop(flag, None)
            if not opt: self.saved.get('gameopt', {}).pop(gid, None)
            self.save()
            active = bool(run and run['id'] == gid)
            target_prof = (run.get('profile') if active else opt.get('profile')) or load_config().get('perf_profile') or 'Balanced'
            target_fps = run.get('fps', 0) if active else opt.get('fps', 0)
            target_scale = run.get('scale', 'linear') if active else opt.get('scale', 'linear')
        if active:
            thor_res = None
            if prof is not None and not self.dry: thor_res = thor.change('profile', target_prof)
            if fps is not None and not self.dry: apply_fps_limit(target_fps)
            if scale is not None and not self.dry: apply_scaling_filter(target_scale)
            if res_h is not None and not self.dry: apply_render_res(int(res_h or 0))
            if thor_res and 'error' not in thor_res: self.publish('thor', {'thor': thor_res})
            self.publish()
        else:
            self.publish('library')
        out = {'ok': True, 'profile': opt.get('profile', ''), 'fps': opt.get('fps', 0), 'scale': opt.get('scale', 'linear')}
        if res_h is not None or opt.get('res'): out['res'] = opt.get('res', 0)
        if shader is not None or opt.get('shader'): out['shader'] = opt.get('shader', '')
        if emu_id is not None or opt.get('emu'): out['emu'] = opt.get('emu', '')
        return out

    def collection_act(self, data):
        """Manage custom collections, hidden games, and library sort order in state.json."""
        act = str(data.get('a') or '')
        gid = str(data.get('id') or '')
        name = str(data.get('name') or '').strip()[:40]
        with self.lock:
            cols = self.saved.setdefault('collections', {})
            hidden = self.saved.setdefault('hidden', [])
            pinned = self.saved.setdefault('pinned', [])
            if act == 'sort':
                s = str(data.get('sort') or 'recent')
                if s not in ('recent', 'az', 'time', 'year', 'short'): return {'error': 'unbekannte Sortierung'}
                self.saved['sort'] = s
            elif act == 'pin' and gid:
                if gid in pinned: pinned.remove(gid)
                else: pinned.insert(0, gid)
            elif act == 'hide' and gid:
                if gid in hidden: hidden.remove(gid)
                else: hidden.append(gid)
            elif act == 'toggle' and name and gid:
                lst = cols.setdefault(name, [])
                if gid in lst: lst.remove(gid)
                else: lst.append(gid)
                if not lst: cols.pop(name, None)
            elif act == 'create' and name:
                lst = cols.setdefault(name, [])
                if gid and gid not in lst: lst.append(gid)
            elif act == 'delete' and name:
                cols.pop(name, None)
            else:
                return {'error': 'unbekannte Aktion'}
            self.save()
        self.publish('library')
        return {'ok': True, 'collections': self.saved.get('collections', {}), 'pinned': self.saved.get('pinned', []),
                'hidden': self.saved.get('hidden', []), 'sort': self.saved.get('sort', 'recent')}

    def wide(self, on):
        """The Wide view switch of the running game's pack ('on', 'off', else toggle); the choice is kept per game."""
        with self.lock:
            run = self.run
            if not run or run.get('wide') is None: return {'error': 'Dieses Spiel hat kein Breitbild.'}
            run['wide'] = {'on': True, 'off': False}.get(on, not run['wide'])
            try: (RA_WIDE / 'on').write_text('1' if run['wide'] else '0')  # the core looks twice a second
            except OSError as error: return {'error': str(error)}
            self.saved.setdefault('wide', {})[run['id']] = run['wide']
            self.save()
        self.publish()
        return {'ok': True, 'wide': run['wide']}

    def steam_install(self, game):
        """Install a Steam game without Steam's own screens: a manifest that says "wanted, not there yet" makes the
        client download it, and the client runs unseen in the background."""
        apps = self.library.steam / 'steamapps'
        if not apps.is_dir(): return {'error': 'Steam ist hier nicht eingerichtet.'}
        manifest = apps / f'appmanifest_{game["appid"]}.acf'
        quote = lambda s: s.replace('\\', '').replace('"', '')
        if not manifest.exists():
            manifest.write_text('"AppState"\n{\n' + ''.join(f'\t"{k}"\t\t"{quote(v)}"\n' for k, v in (
                ('appid', game['appid']), ('Universe', '1'), ('name', game['t']), ('StateFlags', '1026'), ('installdir', game['dir']))) + '}\n')
        if not self.dry: threading.Thread(target=steam_background, args=(True,), daemon=True).start()
        self.library.scan(); self.publish('library')
        self.steam_watch()
        return {'ok': True, 'cmd': [], 'tracked': False, 'text': f'„{game["t"]}“ wird installiert. Der Fortschritt steht im Steam-Reiter.'}

    def steam_rest(self):
        """Steam takes about 2 GB of memory while it idles in the background: end it when nothing needs it."""
        if self.dry or (self.run and self.run.get('appid')) or any(g.get('inst') == 'load' for g in self.library.games.values()): return
        self.steam_stopping = threading.Thread(target=run_quiet, args=(['steam', '-shutdown'], 60), daemon=True)
        self.steam_stopping.start()

    def steam_watch(self):
        """While a Steam download runs, read its progress every 20 s and tell the pages."""
        if self.dry or getattr(self, 'steam_watching', False): return
        self.steam_watching = True
        def work():
            try:
                while True:
                    time.sleep(20)
                    self.library.scan(); self.publish('library')
                    if not any(g.get('inst') == 'load' for g in self.library.games.values()): break
            finally: self.steam_watching = False
            self.steam_rest()
        threading.Thread(target=work, daemon=True).start()

    def mirror_pad(self, gid):
        """Wii U: show Cemu's GamePad window on the bottom screen. Cemu can only open it next to the game on the top
        screen's display, so its picture is copied over (view only). That needs the window's content to exist in X,
        hence DISABLE_GAMESCOPE_WSI at launch. shortcut: no touch on the GamePad picture, a Cemu build that leases
        the bottom screen itself (as Azahar does) would be the upgrade."""
        for _ in range(90):
            time.sleep(1)
            with self.lock:
                if not self.run or self.run['id'] != gid or self.run.get('paused') or self.mirror: return
            ids = set(re.findall(r'\d{6,}', run_quiet(['xprop', '-root', 'GAMESCOPE_FOCUSABLE_WINDOWS'])))
            pad = next((w for w in ids if 'GamePad View' in run_quiet(['xprop', '-id', w, 'WM_NAME'])), None)
            if not pad: continue
            cmd = ['armada-run-bottom', '--defaults', '--', 'ffplay', '-hide_banner', '-loglevel', 'error', '-fflags', 'nobuffer', '-flags', 'low_delay',
                   '-probesize', '32', '-analyzeduration', '0', '-framedrop', '-an', '-fs', '-f', 'x11grab', '-framerate', '30', '-window_id', pad,
                   '-i', os.environ.get('DISPLAY', ':0')]
            with self.lock:
                if not self.run or self.run['id'] != gid or self.run.get('paused'): return
                try: self.mirror = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                except OSError: pass
            return

    def mirror_stop(self):
        mirror, self.mirror = self.mirror, None
        if mirror:
            try: os.killpg(mirror.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError): pass
            threading.Thread(target=mirror.wait, daemon=True).start()  # collect it, or it stays behind as a zombie

    def send(self, sig):
        """Signal the running game: its process group, or for a Steam game everything Steam started for it."""
        appid = self.run and self.run.get('appid')
        if not appid: return os.killpg(self.proc.pid, sig)
        pids = steam_pids(appid)
        if not pids: raise ProcessLookupError
        for pid in pids:
            try: os.kill(pid, sig)
            except (ProcessLookupError, PermissionError): pass

    def watch(self, proc, gid, appid=None):
        if not appid: proc.wait()
        else:  # 'steam steam://rungameid' returns at once; the game is what Steam starts for it, some time later
            there, gone, longest, deadline = 0, 0, 0, time.time() + 300
            while self.run and self.run['id'] == gid:
                if steam_pids(appid):
                    there, gone = there + 2, 0
                    longest = max(longest, there)
                    if there in (2, 6, 12):
                        thor_perf.pin_game_tree(None, 'big')
                    if longest >= SETUP_SECS: self.steam_show = 0  # the game itself is there: Steam's own window may go
                else: there, gone = 0, gone + 2
                # Asked to quit: the wait for a game that may still appear is over, whatever was seen of it so far.
                if steam_game_over(longest, gone, time.time() > deadline or self.run.get('quitting')): break
                time.sleep(2)
        self.finish(gid)

    def finish(self, gid):
        with self.lock:
            if not self.run or self.run['id'] != gid: return
            extra = max(0, int(time.time() - SLEEP_STATE['since'])) if SLEEP_STATE['since'] else 0
            SLEEP_STATE['since'], SLEEP_STATE['froze'] = 0.0, False
            delta = max(0, int(time.time()) - self.run['since'] - extra)
            self.saved['played'][gid]['secs'] += delta
            if delta > 0 and self.run.get('s') not in ('app', 'term'):
                sess = self.saved.setdefault('sessions', {})
                day_k = time.strftime('%Y-%m-%d')
                sess[day_k] = int(sess.get(day_k, 0)) + delta
                for old_k in sorted(sess)[:-60]: sess.pop(old_k, None)
            self.save()  # before the run is cleared: whoever sees "no game running" also finds the play time on disk
            steam, had_prof, had_fps = self.run.get('appid'), bool(self.run.get('profile')), bool(self.run.get('fps'))
            had_scale = self.run.get('scale', 'linear') != 'linear'
            is_game = self.run.get('s') not in ('app', 'term')
            self.run, self.proc = None, None
            (STATE / 'running').unlink(missing_ok=True)
            self.mirror_stop()
        if steam: self.steam_rest()
        cfg_end = load_config()
        if had_prof and not self.dry:
            thor.change('profile', 'Eco' if cfg_end.get('travel_mode') else (cfg_end.get('perf_profile') or 'Balanced'))
        if had_fps and not self.dry:
            apply_fps_limit(base_panel_hz(cfg_end))
        if had_scale and not self.dry: apply_scaling_filter('linear')
        if not self.dry:
            apply_render_res(0)
            thor_perf.set_tandem_isolation(False)
            thor_translate.stop_worker()
            thor_features.REPLAY.stop()
            thor_features.stop_turbo()
            thor_pro.PROPAD.stop()
            thor_pro.TROPHIES.reset_game(gid)
        if is_game and not self.dry:
            saved_moment = self.moments.finish(gid)
            if saved_moment and gid in self.library.games:
                m_tok = self.library._image(saved_moment)
                self.library.games[gid]['moment'] = m_tok
                if not self.library.games[gid].get('hero'):
                    self.library.games[gid]['hero'] = m_tok
                self.publish('library')
        if is_game and not self.dry and load_config().get('save_auto', True):
            trigger_saves_backup(self, quiet=True)
        self.publish()
        threading.Thread(target=self.come_home, daemon=True).start()

    def stats_payload(self):
        """Activity & playtime summary: total time, 7-day daily history, top played games, and recent games."""
        import datetime
        played = self.saved.get('played') or {}
        sessions = self.saved.get('sessions') or {}
        games = self.library.games
        total_secs = sum(int((v or {}).get('secs') or 0) for gid, v in played.items() if gid in games)
        played_count = sum(1 for gid, v in played.items() if gid in games and ((v or {}).get('secs') or (v or {}).get('last')))
        wd_names = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')
        today = datetime.date.today()
        days = []
        for back in range(6, -1, -1):
            d = today - datetime.timedelta(days=back)
            ds = d.isoformat()
            days.append({'day': wd_names[d.weekday()], 'date': ds, 'secs': int(sessions.get(ds) or 0)})
        week_secs = sum(x['secs'] for x in days)
        def entry(g):
            p = played.get(g['id']) or {}
            sys_lbl = 'Steam' if g['s'] == 'steam' else SYSTEMS.get(g['s'], (g['s'],))[0]
            return {'id': g['id'], 't': g['t'], 'sys': sys_lbl, 'secs': int(p.get('secs') or 0),
                    'last': int(p.get('last') or 0), 'cover': g.get('cover')}
        all_p = [entry(g) for g in games.values() if g['id'] in played and g.get('s') not in ('app', 'term')]
        top_games = sorted((x for x in all_p if x['secs'] > 0), key=lambda x: (-x['secs'], -x['last']))[:6]
        recent_games = sorted((x for x in all_p if x['last'] > 0), key=lambda x: -x['last'])[:5]
        return {'total_secs': total_secs, 'week_secs': week_secs, 'played_count': played_count,
                'total_games': len(games), 'fav_count': len(self.saved.get('fav') or []),
                'days': days, 'top_games': top_games, 'recent_games': recent_games}

    def come_home(self):
        """After a game the top compositor can be left with no window in front and keeps showing the game's last picture
        (seen with Fallout 4 ended from outside): hiding and showing Tandem's own window makes it take that again."""
        time.sleep(2)
        if self.dry or self.run or not self.home_window or focused_window(): return
        x_window('unmap', self.home_window); time.sleep(0.5); x_window('map', self.home_window)

    def quit(self):
        proc, run = self.proc, self.run
        if self.swkbd: self.finish_swkbd(ok=False)
        if not run: return {'ok': True}
        if not self.dry and run.get('s') not in ('app', 'term') and not run.get('paused'):
            self.moments.snapshot_now(run['id'])
        if run.get('login'): yt_login(self, 'cancel')  # the sign-in window goes with the app
        run['quitting'] = True
        if self.dry or not proc:
            self.finish(run['id'])
            return {'ok': True}
        sock_path = ((run.get('port') or {}).get('socket') if run.get('emu') in MEDIA_APPS else None)
        if sock_path:  # tell Flatpak mpv over its IPC socket to quit cleanly before bwrap can orphan it
            import socket
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5); s.connect(sock_path); s.sendall(b'{"command":["quit"]}\n')
            except OSError: pass
        try:
            if run.get('paused') or run.get('frozen') or SLEEP_STATE.get('froze'): self.send(signal.SIGCONT)  # a frozen program cannot react to being asked to quit
            self.send(signal.SIGTERM)
            def reap(group=proc.pid, appid=run.get('appid'), fp_id=run.get('flatpak')):
                # The sandbox's inner processes can outlive the outer one that Popen watches: after the grace period
                # whatever is left of the game's process group (and any Flatpak bwrap instance) has to go.
                for pid in steam_pids(appid) if appid else [-group]:  # a negative number means the whole group
                    try:
                        os.kill(pid, signal.SIGCONT)
                        os.kill(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError): pass
                if fp_id and self.run is None: run_quiet(['flatpak', 'kill', fp_id], timeout=3)
            threading.Timer(5, reap).start()
        except ProcessLookupError: pass
        return {'ok': True}

    def freeze_toggle(self, force=None):
        """In-place 0W Deep-Freeze (`SIGSTOP` / `SIGCONT`) for unpausable cutscenes, Souls games & low-battery guard."""
        with self.lock:
            run, proc = self.run, self.proc
            if not run or run.get('paused') or not proc:
                return {'error': 'Es läuft kein Spiel.'}
            want = (not bool(run.get('frozen'))) if force is None else bool(force)
            if want == bool(run.get('frozen')):
                return {'ok': True, 'frozen': want}
            if not self.dry:
                try:
                    self.send(signal.SIGSTOP if want else signal.SIGCONT)
                except ProcessLookupError:
                    return {'error': 'Das Spiel ist schon beendet.'}
            if want:
                run['frozen'] = True
                run['frozen_at'] = time.time()
            else:
                f_dur = max(0, int(time.time() - (run.pop('frozen_at', None) or time.time())))
                run['since'] += f_dur
                run.pop('frozen', None)
        self.publish()
        return {'ok': True, 'frozen': want,
                'text': '❄️ Spiel eingefroren (0 W CPU/GPU).' if want else '▶ Spiel läuft weiter.'}

    def pause(self):
        """Home button while a game runs: freeze it, hide its window, Tandem is in front again. Like the Switch's Home."""
        with self.lock:
            run, proc = self.run, self.proc
            if not run or run.get('paused') or self.dry or not proc: return {'error': 'Es läuft kein Spiel.'}
            if run.get('frozen'):
                f_dur = max(0, int(time.time() - (run.pop('frozen_at', None) or time.time())))
                run['since'] += f_dur
                run.pop('frozen', None)
            window = focused_window()
            if not window or window == self.home_window: return {'error': 'Das Spielfenster ist noch nicht da.'}
            try: self.send(signal.SIGSTOP)
            except ProcessLookupError: return {'error': 'Das Spiel ist schon beendet.'}
            windows = [window]
            x_window('unmap', window)
            for _ in range(6):  # a game with more windows (Cemu's GamePad view) would put the next one in front
                time.sleep(0.15)
                more = focused_window()
                if more and more != self.home_window and more not in windows:
                    x_window('unmap', more); windows.append(more)
            self.mirror_stop()  # Tandem's own bottom page is needed again
            run['paused'], run['windows'] = True, windows
            self.ui = {'tab': 0, 'sys': None, 'i': 0}  # the first page, where the paused game stands in front
        self.publish()
        return {'ok': True}

    def resume(self):
        with self.lock:
            run, proc = self.run, self.proc
            if not run or not run.get('paused') or not proc: return {'error': 'Es ist kein Spiel pausiert.'}
            for window in reversed(run['windows']): x_window('map', window)  # the game's main window last: it gets the screen
            try: self.send(signal.SIGCONT)
            except ProcessLookupError: pass
            run['paused'] = False
        if run['s'] == 'wiiu': threading.Thread(target=self.mirror_pad, args=(run['id'],), daemon=True).start()
        self.publish()
        return {'ok': True}

    def act(self, name):
        """Run a power/session action on behalf of this Tandem instance (keeps action(name) as a 1-arg hook for tests)."""
        if name == 'power_menu':
            self.power_open = not self.power_open
            self.publish()
            return {'ok': True, 'power': self.power_open}
        if name == 'power_close':
            if self.power_open:
                self.power_open = False
                self.publish()
            return {'ok': True, 'power': False}
        if self.power_open:
            self.power_open = False
        if not self.dry and name in ('suspend', 'sleep'): sleep_game(self, True)
        res = action(name)
        if not self.dry and name == 'wake': sleep_game(self, False)
        self.publish()
        return res

    def favourite(self, gid):
        fav = self.saved.setdefault('fav', [])
        fav.remove(gid) if gid in fav else fav.append(gid)
        self.save()
        self.publish('library')
        return {'fav': fav}


SETUP_SECS = 90  # Steam's first-start steps (install script, redistributables) run under the game's name for up to about a minute


def steam_game_over(longest, gone, late):
    """Whether a Steam game has ended: its processes are gone for ten seconds. Before the game itself was there
    (present for SETUP_SECS at a stretch) that only counts once the five minutes for starting are over (late): Steam's
    set-up step comes and goes first, and after it Steam may still ask something (licence, cloud saves) before the
    game appears."""
    return gone >= 10 and (longest >= SETUP_SECS or late) if longest else late


def steam_pids(appid):
    """Every process of a running Steam game: Steam starts it under 'reaper SteamLaunch AppId=<id>', the rest descends from that."""
    parents, found, mark = {}, set(), f'\0AppId={appid}\0'.encode()
    for entry in os.listdir('/proc'):
        if not entry.isdigit(): continue
        try:
            parents[int(entry)] = int(Path(f'/proc/{entry}/stat').read_text().rsplit(')', 1)[1].split()[1])
            if mark in Path(f'/proc/{entry}/cmdline').read_bytes(): found.add(int(entry))
        except (OSError, ValueError, IndexError): continue
    grown = True
    while grown:
        more = {pid for pid, parent in parents.items() if parent in found} - found
        grown = bool(more); found |= more
    return sorted(found)


def steam_background(restart=False):
    """Have the Steam client run unseen (downloads, and Steam games need it). A running client only notices a new
    manifest after a restart, hence the option."""
    try: running = os.path.isdir('/proc/' + (HOME / '.steam/steam.pid').read_text().strip())
    except OSError: running = False
    if running and not restart: return
    if running:
        run_quiet(['steam', '-shutdown'], timeout=60)
        time.sleep(8)
    try: subprocess.Popen(['steam', '-silent'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError: pass


def start_time(pid):
    try: return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError): return ''


def kill_stale():
    """A game that outlived the last session (the session was restarted under it) would run on unseen: end its group.
    The start time guards against the number having gone to another program since."""
    note = STATE / 'running'
    try: pid, started = note.read_text().split()
    except (OSError, ValueError): return
    if started and start_time(pid) == started:
        try: os.killpg(int(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, ValueError): pass
    note.unlink(missing_ok=True)


def cemu_pad_window():
    """Make Cemu open its separate GamePad window (off by default)."""
    path = HOME / '.config/Cemu/settings.xml'
    try: text = path.read_text()
    except OSError: return
    if '<open_pad>' in text: text = re.sub(r'<open_pad>\w*</open_pad>', '<open_pad>true</open_pad>', text, count=1)
    else: text = text.replace('<content>', '<content>\n    <open_pad>true</open_pad>', 1)
    path.write_text(text)


BACKLIGHTS = {'bt': 'ae96000.dsi.0', 'bb': 'ae94000.dsi.0'}  # AYN Thor: top and bottom panel
PRIV_WRITE = '/usr/bin/steamos-polkit-helpers/steamos-priv-write'  # ArmadaOS's helper; asks logind on behalf of the session
RA_COMMANDS = {'save': 'SAVE_STATE', 'load': 'LOAD_STATE', 'slot+': 'STATE_SLOT_PLUS', 'slot-': 'STATE_SLOT_MINUS', 'ff': 'FAST_FORWARD',
               'menu': 'MENU_TOGGLE', 'pause': 'PAUSE_TOGGLE', 'shot': 'SCREENSHOT', 'reset': 'RESET'}
ACTIONS = {'poweroff': ['systemctl', 'poweroff'], 'reboot': ['systemctl', 'reboot'], 'suspend': ['systemctl', 'suspend'],
           'desktop': ['steamos-session-select', 'desktop']}


def run_quiet(cmd, timeout=5):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError): return ''


def record(tandem, action):
    """Both screens and the sound into ~/Videos/Tandem (thor-record); both windows learn the state."""
    if action not in ('start', 'stop', 'status'): return {'error': 'unbekannte Aktion'}
    out = run_quiet([str(HERE / 'thor-record'), action], timeout=60).strip().splitlines()
    try: state = json.loads(out[-1])
    except (IndexError, ValueError): return {'error': 'Aufnahme nicht möglich'}
    if action != 'status' and 'error' not in state: tandem.publish('rec', {'rec': state})
    return state


def wow_folders():
    """WoW Forever's client folders (…/World of Warcraft/_forever_) on the card or in the home folder."""
    return [Path(p) for p in sorted(set(glob.glob('/run/media/*/*/Battle.net/World of Warcraft/_forever_') + glob.glob(str(HOME / '*/World of Warcraft/_forever_'))))]


def wow_pick_account(cfg, name):
    """Makes `name` the preselected game account: WoW keeps the list as SET accountList "A|!B|" ('!' = last chosen)."""
    if not cfg.exists(): return
    lines = cfg.read_text(errors='surrogateescape').splitlines()
    old = next((l for l in lines if l.startswith('SET accountList ')), None)
    names = [n.lstrip('!') for n in (old.split('"')[1] if old and old.count('"') >= 2 else '').split('|') if n]
    if name not in names: names.append(name)
    new = 'SET accountList "' + ''.join(('!' if n == name else '') + n + '|' for n in names) + '"'
    if old == new: return
    lines = [new if l == old else l for l in lines] if old else lines + [new]
    cfg.write_bytes(('\r\n'.join(lines) + '\r\n').encode(errors='surrogateescape'))


def wow_login(timeout=600):
    """Signs WoW Forever in the way its Android launcher does: the client reads <_forever_>/login.txt (e-mail, password,
    one per line) at start. The file holds the password in plain text, so it is overwritten and removed as soon as
    Connection.log shows the login form was sent (success or not), or after timeout. Returns False when no login is set up."""
    config = load_config()
    if not (config.get('bnet_email') and config.get('bnet_password')): return False
    files = []
    sent = lambda f: 'logon form submission' in ((f.parent / 'Logs/Connection.log').read_text(errors='replace') if (f.parent / 'Logs/Connection.log').exists() else '')
    for folder in wow_folders():
        if config.get('wow_account'): wow_pick_account(folder / 'WTF/Config.wtf', config['wow_account'])
        (folder / 'Logs/Connection.log').unlink(missing_ok=True)
        path = folder / 'login.txt'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle: handle.write(f'{config["bnet_email"]}\n{config["bnet_password"]}\n')
        files.append(path)

    def clean():
        until = time.time() + timeout
        while time.time() < until and not any(sent(f) for f in files):
            time.sleep(2)
        time.sleep(3)  # WoW reads the file a few times around the login
        for f in files:
            try:
                f.write_bytes(bytes(min(f.stat().st_size, 4096))); f.unlink()
            except OSError: pass
    threading.Thread(target=clean, daemon=True).start()
    want = config.get('wow_account')
    rows = [n.lstrip('!') for f in files for l in (f.parent / 'WTF/Config.wtf').read_text(errors='replace').splitlines()
            if l.startswith('SET accountList "') for n in l.split('"')[1].split('|') if n] if want else []
    if want in rows:  # the chooser always marks the first account (accountList's '!' is ignored), so pick it on screen
        import wowpick
        env = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}', 'WAYLAND_DISPLAY': 'gamescope-0'}
        threading.Thread(target=wowpick.pick, args=(rows.index(want), lambda c: KEYBOARD.press(c, []), env), daemon=True).start()
    return True


LSFG_LAYER = HOME / '.local/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json'


def frame_gen(on=None):
    """Lossless Scaling frame generation (lsfg-vk layer, profiles in ~/.config/lsfg-vk/conf.toml) on or off: the layer's
    file is set aside while off, so it counts from the next game start. None: only report."""
    off = LSFG_LAYER.with_suffix('.json.off')
    if on is not None:
        src, dst = (off, LSFG_LAYER) if on else (LSFG_LAYER, off)
        if src.exists(): src.rename(dst)
    return {'on': LSFG_LAYER.exists(), 'there': LSFG_LAYER.exists() or off.exists()}


YT_PROFILE = HOME / '.config/tandem/media/yt-browser'  # default path; runtime helpers follow CONFIG.parent for tests
YT_LOGIN_URL = 'https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fwww.youtube.com%2F'
YT_AUTH_NAMES = frozenset(('SAPISID', '__Secure-1PAPISID', '__Secure-3PAPISID', 'SID', '__Secure-1PSID', '__Secure-3PSID'))
YT_TV_DEVICE_URL, YT_TV_TOKEN_URL = 'https://www.youtube.com/o/oauth2/device/code', 'https://www.youtube.com/o/oauth2/token'
YT_TV_SCOPE = 'http://gdata.youtube.com https://www.googleapis.com/auth/youtube-paid-content'
YT_TV_UA = 'Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version'
YT_TV_CLIENT_RX = re.compile(r'clientId:"([0-9]+-[0-9a-zA-Z_\-]+\.apps\.googleusercontent\.com)",\w+:"([0-9a-zA-Z_\-]{16,48})"')
YT_BROWSER = None
YT_LOCK = threading.Lock()


def yt_paths():
    """(browser profile dir, exported Netscape cookies.txt, OAuth token json) inside CONFIG's media folder."""
    media_dir = CONFIG.parent / 'media'
    prof = YT_PROFILE if YT_PROFILE != HOME / '.config/tandem/media/yt-browser' else media_dir / 'yt-browser'
    return prof, prof.with_name('youtube-cookies.txt'), prof.with_name('youtube-auth.json')


def _write_priv_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f: json.dump(data, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def yt_tv_client():
    """Discover YouTube's public TVHTML5 OAuth client parameters from youtube.com/tv at runtime and cache locally (0600)."""
    import urllib.request
    cfile = yt_paths()[2].with_name('youtube-tv-client.json')
    try:
        cached = json.loads(cfile.read_text())
        if cached.get('id') and cached.get('secret'): return cached['id'], cached['secret']
    except (OSError, ValueError): pass
    try:
        req = urllib.request.Request('https://www.youtube.com/tv', headers={'User-Agent': YT_TV_UA})
        html = urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'replace')
        m = YT_TV_CLIENT_RX.search(html)
        if not m:
            for s in re.findall(r'src="(/s/_/kabuki/[^"]+\.js)"', html)[:2]:
                js = urllib.request.urlopen(urllib.request.Request('https://www.youtube.com' + s, headers={'User-Agent': YT_TV_UA}), timeout=12).read().decode('utf-8', 'replace')
                m = YT_TV_CLIENT_RX.search(js)
                if m: break
        if m:
            _write_priv_json(cfile, {'id': m[1], 'secret': m[2]})
            return m[1], m[2]
    except OSError: pass
    return None


def yt_auth_signed_in():
    """True when youtube-auth.json holds a valid OAuth refresh or access token (from QR / TV device sign-in)."""
    afile = yt_paths()[2]
    try: a = json.loads(afile.read_text())
    except (OSError, ValueError): return False
    return bool(isinstance(a, dict) and (a.get('refresh') or a.get('until', 0) > time.time() + 60))


def yt_qr_step(force_new=False):
    """Start or poll Google/YouTube's QR device-code sign-in (stdlib only; shares youtube-device.json & youtube-auth.json)."""
    import urllib.error, urllib.parse, urllib.request, uuid
    _, _, afile = yt_paths()
    dfile = afile.with_name('youtube-device.json')
    cfg = load_config()
    custom = (cfg['yt_client_id'], cfg['yt_client_secret']) if cfg.get('yt_client_id') and cfg.get('yt_client_secret') else None
    if yt_auth_signed_in() and not force_new:
        return {'ok': True, 'signed_in': True}
    pair = custom or yt_tv_client()
    if not pair:
        return {'error': 'Google ist nicht erreichbar.'}
    cid, secret = pair

    def post_f(url, fields, ua=None):
        hdr = {'User-Agent': ua} if ua else {}
        req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), headers=hdr, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read())
        except urllib.error.HTTPError as err:
            try: return json.loads(err.read())
            except ValueError: return {'error': f'http {err.code}'}
        except (OSError, ValueError): return {'error': 'Google ist nicht erreichbar.'}

    def qr_svg(url):
        try:
            if str(HERE / 'ui') not in sys.path: sys.path.insert(0, str(HERE / 'ui'))
            import qr
            return qr.svg(url)
        except Exception: return ''

    d = None
    if not force_new:
        try: d = json.loads(dfile.read_text())
        except (OSError, ValueError): d = None
    if d and time.time() < d.get('until', 0) and bool(d.get('custom')) == bool(custom):
        if time.time() - d.get('polled', 0) >= max(4, int(d.get('interval', 5)) - 1):
            d['polled'] = time.time()
            _write_priv_json(dfile, d)
            got = (post_f('https://oauth2.googleapis.com/token', {'client_id': cid, 'client_secret': secret, 'device_code': d['device_code'], 'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})
                   if custom else post_f(YT_TV_TOKEN_URL, {'client_id': cid, 'client_secret': secret, 'code': d['device_code'], 'grant_type': 'http://oauth.net/grant_type/device/1.0'}, YT_TV_UA))
            if got.get('access_token'):
                _write_priv_json(afile, {'access': got['access_token'], 'refresh': got.get('refresh_token'),
                                         'until': time.time() + int(got.get('expires_in', 3600)), 'tv': not custom})
                dfile.unlink(missing_ok=True)
                return {'ok': True, 'signed_in': True, 'just_signed_in': True, 'text': 'Bei YouTube angemeldet.'}
            if got.get('error') in ('invalid_client', 'unauthorized_client') and not custom:
                afile.with_name('youtube-tv-client.json').unlink(missing_ok=True)
            if got.get('error') not in ('authorization_pending', 'slow_down', None):
                dfile.unlink(missing_ok=True); d = None
        if d:
            return {'ok': True, 'signed_in': False, 'code': d['code'], 'link': d['link'], 'qr': d['qr'], 'svg': qr_svg(d['qr']), 'poll': max(5, int(d.get('interval', 5)))}
    got = (post_f('https://oauth2.googleapis.com/device/code', {'client_id': cid, 'scope': 'https://www.googleapis.com/auth/youtube.readonly'})
           if custom else post_f(YT_TV_DEVICE_URL, {'client_id': cid, 'scope': YT_TV_SCOPE, 'device_id': str(uuid.uuid4()), 'device_model': 'ytlr::'}, YT_TV_UA))
    if not got.get('user_code') and not custom:
        afile.with_name('youtube-tv-client.json').unlink(missing_ok=True)
    if not got.get('user_code'):
        return {'error': 'Google ist nicht erreichbar.'}
    code = got['user_code']
    qr_url = f'https://www.youtube.com/activate?user_code={urllib.parse.quote(code)}'
    link = 'youtube.com/activate'
    d = {'device_code': got['device_code'], 'code': code, 'link': link, 'qr': qr_url,
         'until': time.time() + int(got.get('expires_in', 1800)), 'interval': int(got.get('interval', 5)), 'polled': time.time(), 'custom': bool(custom)}
    _write_priv_json(dfile, d)
    return {'ok': True, 'signed_in': False, 'code': code, 'link': link, 'qr': qr_url, 'svg': qr_svg(qr_url), 'poll': max(5, d['interval'])}


def yt_firefox_rows(profile=None):
    """Read YouTube/Google cookies from Firefox's SQLite DB, copying -wal/-shm first so live uncheckpointed rows are seen."""
    import sqlite3, tempfile
    prof = Path(profile) if profile else yt_paths()[0]
    db = prof / 'cookies.sqlite'
    if not db.is_file(): return []
    with tempfile.TemporaryDirectory(prefix='tandem-ytck-') as tmp:
        dst = Path(tmp) / 'cookies.sqlite'
        for suf in ('', '-wal', '-shm'):
            src = Path(str(db) + suf)
            if src.is_file():
                try: shutil.copy2(src, Path(str(dst) + suf))
                except OSError: pass
        try:
            with sqlite3.connect(str(dst)) as con:
                cols = {r[1] for r in con.execute('PRAGMA table_info(moz_cookies)').fetchall()}
                if not {'name', 'host', 'value'} <= cols: return []
                sel = "name, value, host" + (", path" if 'path' in cols else ", '/'") + (", expiry" if 'expiry' in cols else ", 0") + (", isSecure" if 'isSecure' in cols else ", 1")
                where = ("originAttributes = '' AND " if 'originAttributes' in cols else '') + "(host LIKE '%youtube.com' OR host LIKE '%google.com')"
                return con.execute(f"SELECT {sel} FROM moz_cookies WHERE {where}").fetchall()
        except sqlite3.Error:
            return []


def write_yt_cookies(rows, dest=None):
    """Write [(domain, path, secure, expiry, name, value)] in Netscape cookies.txt format (0600); True when auth cookies exist."""
    target = Path(dest) if dest else yt_paths()[1]
    clean, has_yt_auth, google_by_name = [], False, {}
    default_exp = int(time.time()) + 365 * 86400
    for host, path, secure, exp, name, value in rows:
        host, name, value = str(host or '').strip(), str(name or '').strip(), str(value or '').strip()
        if not host or not name or '\n' in value or '\t' in value: continue
        if not any(host == d or host.endswith('.' + d) for d in ('youtube.com', 'google.com')): continue
        try: exp = int(exp or 0)
        except (TypeError, ValueError): exp = 0
        if exp > 10_000_000_000: exp //= 1000  # Firefox 128+ stores expiry in milliseconds
        if exp <= 0: exp = default_exp
        dom = host if host.startswith('.') else '.' + host
        clean.append((dom, str(path or '/'), bool(secure), exp, name, value))
        if name in YT_AUTH_NAMES and 'youtube.com' in dom: has_yt_auth = True
        if 'google.com' in dom and name in (YT_AUTH_NAMES | {'HSID', 'SSID', 'APISID', '__Secure-1PSIDTS', '__Secure-3PSIDTS'}):
            google_by_name[name] = (bool(secure), exp, value)
    if not has_yt_auth and (YT_AUTH_NAMES & google_by_name.keys()):
        # User tapped Fertig right after Google accepted credentials before youtube.com finished redirecting: mirror core SSO cookies
        for name, (sec, exp, val) in google_by_name.items():
            clean.append(('.youtube.com', '/', sec, exp, name, val))
        has_yt_auth = True
    if not has_yt_auth: return False
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    tmp = target.with_suffix('.tmp')
    lines = ['# Netscape HTTP Cookie File\n'] + [
        f'{dom}\t{"TRUE" if dom.startswith(".") else "FALSE"}\t{path}\t{"TRUE" if sec else "FALSE"}\t{exp}\t{name}\t{val}\n'
        for dom, path, sec, exp, name, val in clean
    ]
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f: f.writelines(lines)
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return True


def export_yt_cookies(profile=None, dest=None):
    rows = [(host, path, sec, exp, name, val) for name, val, host, path, exp, sec in yt_firefox_rows(profile)]
    return write_yt_cookies(rows, dest) if rows else False


def import_yt_cookies_text(raw, dest=None):
    """Parse pasted Netscape cookies.txt or JSON cookie array from browser extension; returns (ok, error_or_None)."""
    text = (raw or '').strip()
    if not text: return False, 'Keine Cookies eingefügt.'
    rows = []
    if text.startswith('['):
        try: items = json.loads(text)
        except ValueError: return False, 'Ungültiges JSON-Format.'
        for c in items if isinstance(items, list) else []:
            if isinstance(c, dict):
                rows.append((c.get('domain') or c.get('host'), c.get('path') or '/', bool(c.get('secure', True)),
                             c.get('expirationDate') or c.get('expiry') or 0, c.get('name'), c.get('value')))
    else:
        for line in text.splitlines():
            s = line.strip()
            if not s or (s.startswith('#') and not s.startswith('#HttpOnly_')): continue
            if s.startswith('#HttpOnly_'): s = s[len('#HttpOnly_'):]
            parts = s.split('\t')
            if len(parts) >= 7:
                rows.append((parts[0], parts[2], parts[3].upper() == 'TRUE', parts[4], parts[5], parts[6]))
    if not write_yt_cookies(rows, dest):
        return False, 'Keine gültigen YouTube-/Google-Anmeldecookies gefunden (z. B. SAPISID / __Secure-3PAPISID).'
    return True, None


def yt_cookie_signed_in():
    """True when either youtube-cookies.txt or the Firefox login profile holds valid YouTube auth cookies."""
    prof, cfile, _ = yt_paths()
    if cfile.is_file():
        try:
            for line in cfile.read_text(errors='replace').splitlines():
                parts = line.split('\t')
                if len(parts) >= 7 and 'youtube.com' in parts[0] and parts[5] in YT_AUTH_NAMES and parts[6].strip():
                    return True
        except OSError: pass
    return any(name in YT_AUTH_NAMES and ('youtube.com' in str(host) or 'google.com' in str(host)) for name, _, host, *_ in yt_firefox_rows(prof))


def _close_yt_browser(proc):
    if not proc or proc.poll() is not None: return
    for wid in x_windows_matching('firefox', 'navigator'):
        x_window('close', wid)
    try: proc.wait(4)
    except subprocess.TimeoutExpired:
        try: os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError): proc.terminate()
        try: proc.wait(5)
        except subprocess.TimeoutExpired:
            try: os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError): proc.kill()


def yt_login(tandem, action):
    """YouTube sign-in: 'qr'/'qr_new' runs Google's TV device-code QR flow (sign in on phone/PC); 'start'/'open'/'done'/'cancel'
    keep the optional on-device browser flow; 'logout' removes tokens, device state, and cookies."""
    global YT_BROWSER
    prof, cfile, afile = yt_paths()
    if action in ('qr', 'qr_new'):
        res = yt_qr_step(force_new=(action == 'qr_new'))
        if res.get('just_signed_in'):
            tandem.publish('config', {'config': public_config()})
            tandem.publish('toast', {'text': 'Bei YouTube angemeldet.'})
        return res
    if action == 'open':  # from Einstellungen › Konten or remote.html: launch YouTube first if nothing runs yet
        if tandem.run and tandem.run.get('emu') != 'YouTube':
            return {'error': 'Erst das laufende Spiel beenden.'}
        if DOZE and not tandem.dry: doze(False, tandem)
        if not tandem.run:
            yt_id = next(('app' + str(i) for i, a in enumerate(APPS) if a[0] == 'YouTube'), None)
            if not yt_id: return {'error': 'YouTube-App nicht gefunden.'}
            res = tandem.launch(yt_id)
            if isinstance(res, dict) and 'error' in res: return res
            if not tandem.dry: time.sleep(1.0)
        action = 'start'
    with YT_LOCK:
        run = tandem.run
        if action == 'start':
            if not run or run.get('emu') != 'YouTube': return {'error': 'Erst die YouTube-App öffnen.'}
            if YT_BROWSER and YT_BROWSER.poll() is None: return {'ok': True}
            prof.mkdir(parents=True, exist_ok=True)
            for folder in (prof.parent, prof): os.chmod(folder, 0o700)
            (prof / 'user.js').write_text(''.join(f'user_pref("{k}", {v});\n' for k, v in (
                ('browser.shell.checkDefaultBrowser', 'false'), ('browser.aboutwelcome.enabled', 'false'), ('signon.rememberSignons', 'false'),
                ('browser.startup.homepage_override.mstone', '"ignore"'), ('datareporting.policy.dataSubmissionEnabled', 'false'),
                ('toolkit.telemetry.reporting.policy.firstRun', 'false'), ('app.update.auto', 'false'), ('intl.accept_languages', '"de-DE, de, en"'),
                ('browser.tabs.closeWindowWithLastTab', 'true'), ('browser.tabs.warnOnClose', 'false'), ('browser.warnOnQuit', 'false'),
                ('browser.sessionstore.warnOnQuit', 'false'), ('browser.sessionstore.resume_from_crash', 'false'), ('layout.css.devPixelsPerPx', '"1.3"'))))
            hidden = []
            if not tandem.dry:
                for wid in x_windows_matching('mpv'):
                    if wid != tandem.home_window and x_window('unmap', wid): hidden.append(wid)
                env = {**os.environ, 'DISPLAY': os.environ.get('DISPLAY') or ':0', 'MOZ_ENABLE_WAYLAND': '0', 'GDK_BACKEND': 'x11',
                       'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'}
                try:
                    YT_BROWSER = subprocess.Popen(['firefox', '--kiosk', '--new-instance', '--profile', str(prof), YT_LOGIN_URL],
                                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                  start_new_session=True, env=env)
                except OSError as error:
                    for wid in hidden: x_window('map', wid)
                    return {'error': f'Firefox konnte nicht gestartet werden: {error}'}
            layout = region_layout()
            if not tandem.dry: run_quiet(['setxkbmap', layout])
            run.update(keys=True, login=True, layout=layout, yt_hidden=hidden)
            tandem.publish()
            if not tandem.dry and YT_BROWSER:
                proc = YT_BROWSER
                def watch_login():
                    while proc.poll() is None and tandem.run is run and run.get('login'):
                        time.sleep(1.5)
                        rows = yt_firefox_rows(prof)
                        if any(name in ('SAPISID', '__Secure-1PAPISID', '__Secure-3PAPISID') and 'youtube.com' in str(host) for name, _, host, *_ in rows):
                            time.sleep(2.0)  # let final YouTube companion cookies settle
                            export_yt_cookies(prof, cfile)
                            yt_login(tandem, 'done')
                            tandem.publish('toast', {'text': 'Bei YouTube angemeldet.'})
                            return
                    if proc.poll() is not None and tandem.run is run and run.get('login'):
                        yt_login(tandem, 'done')
                threading.Thread(target=watch_login, daemon=True).start()
            return {'ok': True, 'text': 'Anmeldung auf dem Thor geöffnet.'}
        proc, YT_BROWSER = YT_BROWSER, None
    if action == 'done' and not tandem.dry: export_yt_cookies(prof, cfile)  # snapshot WAL before closing
    if not tandem.dry: _close_yt_browser(proc)
    if action == 'done': export_yt_cookies(prof, cfile)  # and again after Firefox flushed on exit
    if action == 'logout':
        shutil.rmtree(prof, ignore_errors=True)
        cfile.unlink(missing_ok=True)
        afile.unlink(missing_ok=True)
        afile.with_name('youtube-device.json').unlink(missing_ok=True)
    run = tandem.run
    if run:
        for wid in reversed(run.pop('yt_hidden', None) or []):
            if not tandem.dry: x_window('map', wid)
        if run.pop('login', None): run.pop('keys', None)
    tandem.publish('config', {'config': public_config()})
    tandem.publish()
    return {'ok': True, 'signed_in': yt_auth_signed_in() or yt_cookie_signed_in(), 'text': 'Abgemeldet.' if action == 'logout' else ''}


def screenshot():
    """Both screens as PNG into ~/Pictures/Tandem (works via gamescopectl or ArmadaOS X11 x11grab)."""
    folder = HOME / 'Pictures/Tandem'
    folder.mkdir(parents=True, exist_ok=True)
    name = time.strftime('%Y%m%d-%H%M%S')
    top_png, bot_png = folder / f'{name}-oben.png', folder / f'{name}-unten.png'
    dpys = _x11_displays()
    companion.capture_screen_frame(top_png, display=dpys[0] if dpys else ':0')
    if len(dpys) > 1:
        companion.capture_screen_frame(bot_png, display=dpys[1])
    elif shutil.which('armada-run-bottom') and shutil.which('gamescopectl'):
        env = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}'}
        try: subprocess.run(['armada-run-bottom', '--', 'gamescopectl', 'screenshot', str(bot_png)], env=env, capture_output=True, timeout=8)
        except (OSError, subprocess.SubprocessError): pass
    if top_png.is_file() and top_png.stat().st_size > 1024:
        return {'ok': True, 'name': name}
    return {'error': 'Bildschirmfoto fehlgeschlagen'}


FPS_LIMITS = (0, 30, 40, 45, 60)
RENDER_RES = (0, 900, 720)
SCALING_FILTERS = ('linear', 'sgsr', 'fsr', 'pixel')
OLED_VIBRANCE = {'srgb': 0, 'natural': 50, 'vibrant': 85, 'ultra': 100}
NIGHT_MODES = {'off': None, 'warm': (1.0, 0.89, 0.72), 'night': (1.0, 0.78, 0.50)}
MUTED = {'on': False}
ARMADA_LAUNCH = Path('/usr/libexec/armada/armada-game-launch')


def _x11_displays():
    """Active XWayland displays (top :0 and optional bottom :1 from armada-bottom-env)."""
    out = [os.environ.get('DISPLAY') or ':0']
    benv = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}') / 'armada-bottom-env'
    try:
        for line in benv.read_text().splitlines():
            if line.startswith('DISPLAY='):
                d = line.split('=', 1)[1].strip().strip('"\'')
                if d and d not in out:
                    out.append(d)
    except OSError:
        pass
    return out


def _xprop_set(atom, value, fmt='32c', displays=None):
    if not shutil.which('xprop'):
        return
    for dpy in (displays or [os.environ.get('DISPLAY') or ':0']):
        env = {**os.environ, 'DISPLAY': dpy}
        try:
            if value is None:
                subprocess.run(['xprop', '-root', '-remove', atom], env=env, capture_output=True, timeout=3)
            else:
                subprocess.run(['xprop', '-root', '-f', atom, fmt, '-set', atom, str(value)],
                               env=env, capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass


def apply_fps_limit(hz):
    """Gamescope's frame limiter / panel refresh target on the top screen (0 = full 120 Hz, 60 = 60 Hz)."""
    _xprop_set('GAMESCOPE_FPS_LIMIT', int(hz))


def apply_low_latency(on=True):
    """Gamescope low-latency presentation path on the top screen (~15-25 ms lower lag than Android SurfaceFlinger)."""
    _xprop_set('GAMESCOPE_LOW_LATENCY', 1 if on else 0)


def apply_render_res(height=0):
    """Tell Gamescope / Steam the target internal game height (720 / 900 / 0=native 1080p)."""
    _xprop_set('GAMESCOPE_STEAM_MAX_HEIGHT', int(height) if height in (720, 900) else None)


def apply_oled_vibrance(mode='vibrant'):
    """Hardware KMS color gamut wideness on both OLED panels (Steam Deck OLED vibrant gamut pipeline, zero GPU cost)."""
    val = OLED_VIBRANCE.get(mode, 85)
    _xprop_set('GAMESCOPE_COLOR_SDR_GAMUT_WIDENESS', val, displays=_x11_displays())


def base_panel_hz(cfg=None):
    """0 = full 120 Hz, 60 = 60 Hz panel refresh when travel_mode or 60 Hz mode is enabled."""
    c = cfg if cfg is not None else load_config()
    return 60 if (c.get('travel_mode') or int(c.get('panel_hz') or 120) == 60) else 0


def write_ai_browser_wrapper():
    """Install a clean xdg-open / BROWSER wrapper for AI CLI sessions (agy / claude) so OAuth logins open
    in a readable X11 Firefox window on :0 without blocking the terminal and record the login URL."""
    ai_bin = STATE / 'ai-bin'
    ai_bin.mkdir(parents=True, exist_ok=True)
    prof = STATE / 'ai-browser-profile'
    prof.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(prof, 0o700)
    except OSError:
        pass
    user_js = prof / 'user.js'
    if not user_js.is_file():
        user_js.write_text(''.join(f'user_pref("{k}", {v});\n' for k, v in (
            ('browser.shell.checkDefaultBrowser', 'false'), ('browser.aboutwelcome.enabled', 'false'),
            ('browser.startup.homepage_override.mstone', '"ignore"'), ('datareporting.policy.dataSubmissionEnabled', 'false'),
            ('toolkit.telemetry.reporting.policy.firstRun', 'false'), ('app.update.auto', 'false'),
            ('intl.accept_languages', '"de-DE, de, en"'), ('browser.tabs.warnOnClose', 'false'),
            ('browser.warnOnQuit', 'false'), ('browser.sessionstore.warnOnQuit', 'false'),
            ('browser.sessionstore.resume_from_crash', 'false'), ('layout.css.devPixelsPerPx', '"1.3"'))), encoding='utf-8')
    url_file = STATE / 'ai-auth-url.txt'
    wrapper = ai_bin / 'ai-browser.sh'
    wrapper.write_text(f'''#!/bin/bash
URL="$1"
[ -z "$URL" ] && exit 0
case "$URL" in
  http://*|https://*)
    printf '%s\\n' "$URL" > {json.dumps(str(url_file))}
    if python3 -c "import json,sys,urllib.request; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8377/api/ai_auth', data=json.dumps({{'url': sys.argv[1]}}).encode(), headers={{'Content-Type':'application/json'}}), timeout=2)" "$URL" >/dev/null 2>&1; then
      exit 0
    fi
    DISPLAY="${{DISPLAY:-:0}}" MOZ_ENABLE_WAYLAND=0 GDK_BACKEND=x11 \\
      nohup firefox --profile {json.dumps(str(prof))} --new-tab "$URL" >/dev/null 2>&1 &
    exit 0
    ;;
esac
exec /usr/bin/xdg-open "$@"
''', encoding='utf-8')
    wrapper.chmod(0o755)
    xdg_link = ai_bin / 'xdg-open'
    try:
        if xdg_link.is_symlink() or xdg_link.exists():
            xdg_link.unlink()
        xdg_link.symlink_to(wrapper)
    except OSError:
        pass
    return wrapper


def write_ai_launcher(tool):
    """Create an executable launcher script in STATE that starts Claude Code or Google Antigravity (`agy`)
    directly in `--dangerously-skip-permissions` mode (auto-installing ARM64 binary on first run if needed)."""
    STATE.mkdir(parents=True, exist_ok=True)
    wrapper = write_ai_browser_wrapper()
    workdir = load_config().get('ai_workdir') or str(HOME)
    script = STATE / f'launch-ai-{tool}.sh'
    env_head = f'''#!/bin/bash
export PATH="{wrapper.parent}:$HOME/.local/bin:/usr/local/bin:$PATH"
export BROWSER={json.dumps(str(wrapper))}
export DISPLAY="${{DISPLAY:-:0}}"
export MOZ_ENABLE_WAYLAND=0
export GDK_BACKEND=x11
export COLORTERM=truecolor
export TERM="${{TERM:-xterm-256color}}"
cd {json.dumps(workdir)} 2>/dev/null || cd "$HOME"
'''
    if tool == 'claude':
        body = env_head + '''if ! command -v claude >/dev/null 2>&1; then
    echo "Installiere Claude Code (ARM64) ..."
    curl -fsSL https://claude.ai/install.sh | bash
fi
printf "\\033[1;38;5;214m▶ Claude Code (--dangerously-skip-permissions) · %s\\033[0m\\n" "$(pwd)"
claude --dangerously-skip-permissions
exec "${SHELL:-/bin/bash}" -l
'''
    else:
        body = env_head + '''if ! command -v agy >/dev/null 2>&1; then
    echo "Installiere Google Antigravity CLI (agy ARM64) ..."
    curl -fsSL https://antigravity.google/cli/install.sh | bash
fi
printf "\\033[1;38;5;39m▶ Google Antigravity · agy (--dangerously-skip-permissions) · %s\\033[0m\\n" "$(pwd)"
agy --dangerously-skip-permissions
exec "${SHELL:-/bin/bash}" -l
'''
    script.write_text(body, encoding='utf-8')
    script.chmod(0o755)
    return script


def apply_travel_effects(on, tandem=None):
    """Apply or restore hardware battery optimizations for On-The-Go (`Unterwegs-Modus`):
    - Power profile -> Eco (`Sparsam`)
    - Top OLED panel refresh rate -> 60 Hz (saves ~1.2–1.8 W vs 120 Hz)
    - Stick RGB rings -> off (restored on exit)
    - Gentle panel brightness cap if currently bright (> 45%)
    - Ends idle background Steam client (~2 GB RAM & background wakeups)"""
    if tandem and tandem.dry:
        return
    cfg = load_config()
    if on:
        st_cur = thor.state()
        rgb_was = bool((st_cur.get('rgb') or {}).get('enabled', True))
        prof_was = ((st_cur.get('power') or {}).get('profile')) or cfg.get('perf_profile') or 'Balanced'
        cur_set = settings()
        snap = {'profile': prof_was, 'rgb': rgb_was, 'bt': cur_set.get('bt'), 'bb': cur_set.get('bb')}
        try: (STATE / 'travel-prev.json').write_text(json.dumps(snap))
        except OSError: pass
        threading.Thread(target=thor.change, args=('profile', 'Eco'), daemon=True).start()
        threading.Thread(target=thor.change, args=('rgb', {'enabled': False}), daemon=True).start()
        if not (tandem and tandem.run and tandem.run.get('fps')):
            apply_fps_limit(60)
        if isinstance(cur_set.get('bt'), int) and cur_set['bt'] > 45:
            change('bt', 40)
        if isinstance(cur_set.get('bb'), int) and cur_set['bb'] > 38:
            change('bb', 30)
        if tandem:
            tandem.steam_rest()
            tandem.publish('settings', {'settings': settings()})
    else:
        snap = {}
        try:
            snap = json.loads((STATE / 'travel-prev.json').read_text())
            (STATE / 'travel-prev.json').unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        prof_to = snap.get('profile') or cfg.get('perf_profile') or 'Balanced'
        threading.Thread(target=thor.change, args=('profile', prof_to), daemon=True).start()
        if snap.get('rgb', True):
            threading.Thread(target=thor.change, args=('rgb', {'enabled': True}), daemon=True).start()
        if not (tandem and tandem.run and tandem.run.get('fps')):
            apply_fps_limit(base_panel_hz(cfg))
        if isinstance(snap.get('bt'), int):
            change('bt', snap['bt'])
        if isinstance(snap.get('bb'), int):
            change('bb', snap['bb'])
        if tandem:
            tandem.publish('settings', {'settings': settings()})


def apply_scaling_filter(mode):
    """Gamescope upscaling filter on the top screen (linear, sgsr, fsr, pixel) via X11 root atoms (+ gamescopectl fallback)."""
    if mode not in SCALING_FILTERS: return
    # GamescopeUpscaleFilter enum: 0 = LINEAR, 1 = NEAREST (pixel), 2 = FSR/SGSR, 3 = NIS
    atom_val = {'linear': 0, 'pixel': 1, 'fsr': 2, 'sgsr': 2}.get(mode, 0)
    _xprop_set('GAMESCOPE_SCALING_FILTER', atom_val)
    _xprop_set('GAMESCOPE_NEW_SCALING_FILTER', atom_val)
    if mode in ('sgsr', 'fsr'):
        _xprop_set('GAMESCOPE_FSR_SHARPNESS', 5)
    if shutil.which('gamescopectl'):
        env = {**os.environ, 'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}', 'WAYLAND_DISPLAY': 'gamescope-0'}
        try:
            subprocess.run(['gamescopectl', 'scaling_filter', mode], env=env, capture_output=True, timeout=3)
            if mode in ('sgsr', 'fsr'):
                subprocess.run(['gamescopectl', 'scaling_sharpness', '12'], env=env, capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError): pass


def apply_night_mode(mode):
    """Hardware 3D LUT blue-light filter on both Gamescope displays via GAMESCOPE_COLOR_LOOK_G22 X11 atom (zero GPU/CPU cost)."""
    if mode not in NIGHT_MODES: return
    gains = NIGHT_MODES[mode]
    cube_arg = ''
    if gains:
        cache = Path(os.environ.get('XDG_CACHE_HOME', HOME / '.cache')) / 'tandem'
        cache.mkdir(parents=True, exist_ok=True)
        cube = cache / f'look-{mode}.cube'
        if not cube.is_file():
            n = 9
            lines = [f'LUT_3D_SIZE {n}']
            for b in range(n):
                for g in range(n):
                    for r in range(n):
                        lines.append(f'{(r / (n - 1)) * gains[0]:.5f} {(g / (n - 1)) * gains[1]:.5f} {(b / (n - 1)) * gains[2]:.5f}')
            cube.write_text('\n'.join(lines) + '\n')
        cube_arg = str(cube)
    _xprop_set('GAMESCOPE_COLOR_LOOK_G22', cube_arg if cube_arg else None, fmt='8u', displays=_x11_displays())
    if shutil.which('gamescopectl'):
        rt = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}')
        for sock in sorted(rt.glob('gamescope-[0-9]*')):
            if not re.fullmatch(r'gamescope-\d+', sock.name): continue
            env = {**os.environ, 'XDG_RUNTIME_DIR': str(rt), 'WAYLAND_DISPLAY': sock.name, 'GAMESCOPE_WAYLAND_DISPLAY': sock.name}
            try: subprocess.run(['gamescopectl', 'set_look', cube_arg], env=env, capture_output=True, timeout=4)
            except (OSError, subprocess.SubprocessError): pass


def trigger_saves_backup(tandem, quiet=False):
    """Run savegame sync in the background and inform both screens."""
    def work():
        cfg = load_config()
        res = saves.backup(cfg.get('save_target', saves.DEFAULT_TARGET))
        tandem.publish('saves', {'saves': saves.status()})
        if res.get('error') and not quiet:
            tandem.publish('toast', {'text': res['error']})
        elif res.get('text') and not quiet:
            tandem.publish('toast', {'text': res['text']})
    threading.Thread(target=work, daemon=True).start()
    return {'ok': True}


def settings():
    """Brightness of both panels and the volume, each 0-100, or None where the device has no such control."""
    out = {}
    for key, name in BACKLIGHTS.items():
        try:
            base = Path('/sys/class/backlight') / name
            out[key] = round(100 * int((base / 'brightness').read_text()) / int((base / 'max_brightness').read_text()))
        except (OSError, ValueError, ZeroDivisionError): out[key] = None
    vol_out = run_quiet(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@']) if shutil.which('wpctl') else ''
    volume = re.search(r'Volume: ([0-9.]+)', vol_out)
    out['vol'] = round(100 * float(volume[1])) if volume else None
    if vol_out: MUTED['on'] = '[MUTED]' in vol_out
    return out


def mute(mode='toggle'):
    """Speaker / headphone mute via PipeWire ('toggle', True, False)."""
    if shutil.which('wpctl'):
        arg = 'toggle' if mode == 'toggle' else ('1' if mode else '0')
        run_quiet(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', arg])
        MUTED['on'] = '[MUTED]' in run_quiet(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
    else:
        MUTED['on'] = (not MUTED['on']) if mode == 'toggle' else bool(mode)
    return {'ok': True, 'muted': MUTED['on']}


def change(key, value):
    value = max(0, min(100, int(value)))
    if key in BACKLIGHTS:
        base = Path('/sys/class/backlight') / BACKLIGHTS[key]
        try: raw = max(1, round(int((base / 'max_brightness').read_text()) * value / 100))  # never fully dark
        except (OSError, ValueError): return {'error': 'Diese Helligkeit lässt sich hier nicht einstellen.'}
        set_raw(key, raw)
    elif key == 'vol':
        if shutil.which('wpctl'):
            run_quiet(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '0'])
            run_quiet(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', f'{value}%'])
    else: return {'error': 'unbekannte Einstellung'}
    return settings()


def retroarch(name):
    """One of RetroArch's network commands (needs network_cmd_enable in retroarch.cfg); UDP, no answer expected."""
    if name not in RA_COMMANDS: return {'error': 'unbekannter Befehl'}
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock: sock.sendto(RA_COMMANDS[name].encode(), ('127.0.0.1', 55355))
    return {'ok': True}


def retroarch_slot_act(tandem, slot, mode):
    """Switch RetroArch to `slot` (0..5) and trigger 'save' or 'load' over UDP."""
    if mode not in ('save', 'load'): return {'error': 'unbekannte Aktion'}
    run = tandem.run
    if not run or run.get('emu') != 'RetroArch':
        return {'error': 'Direkte Slot-Steuerung wird aktuell von RetroArch unterstützt.'}
    target = max(0, min(9, int(slot)))
    cur = int(run.get('ra_slot', 0))
    step_cmd = 'slot+' if target > cur else 'slot-'
    for _ in range(abs(target - cur)):
        retroarch(step_cmd)
        time.sleep(0.03)
    run['ra_slot'] = target
    retroarch(mode)
    return {'ok': True, 'slot': target, 'mode': mode}


# panel -> raw brightness before a doze; empty while awake. Kept in a file too: a Tandem restart during a doze left both
# panels at 0 with nothing to wake them (17.11.)
DOZE_FILE = Path(os.environ.get('XDG_RUNTIME_DIR') or '/tmp') / 'tandem-doze.json'
try: DOZE = {k: int(v) for k, v in json.loads(DOZE_FILE.read_text()).items()}
except (OSError, ValueError, AttributeError): DOZE = {}
SLEEP_STATE = {'since': 0.0, 'froze': False, 'muted': None, 'profile': None}
FAKE_SUSPEND_FLAG = Path('/run/armada/fake-suspend.active')


def on_power():
    """True while a charger or a computer feeds the Thor over USB."""
    for supply in Path('/sys/class/power_supply').glob('*'):
        try:
            if supply.name != 'battery' and (supply / 'online').read_text().strip() == '1': return True
        except OSError: pass
    return False


def seat_session():
    """Active logind session on seat0, so backlight changes also work when tandem.py was restarted over SSH."""
    m = re.search(r'"(/org/freedesktop/login1/session/[^"]+)"',
                  run_quiet(['busctl', '--system', 'get-property', 'org.freedesktop.login1',
                             '/org/freedesktop/login1/seat/seat0', 'org.freedesktop.login1.Seat', 'ActiveSession']))
    return m[1] if m else '/org/freedesktop/login1/session/auto'


def set_raw(key, raw):
    run_quiet(['busctl', '--system', 'call', 'org.freedesktop.login1', seat_session(),
               'org.freedesktop.login1.Session', 'SetBrightness', 'ssu', 'backlight', BACKLIGHTS[key], str(raw)])


_SET_RAW = set_raw


def lit(key, raw):
    """A brightness worth waking to: a panel that was already dark when the doze began (a second doze, a slider at 0)
    would otherwise wake dark too – the owner pressed power 4× on 18.11. and nothing lit up. Falls back to 75 % of max."""
    try:
        mx = int((Path('/sys/class/backlight') / BACKLIGHTS[key] / 'max_brightness').read_text())
        return raw if raw >= max(1, mx // 20) else max(1, mx * 3 // 4)
    except (OSError, ValueError, KeyError): return raw if raw > 0 else 1


def panel_sleep(on):
    """Put both Gamescope internal panels into DRM sleep (or wake them), matching Armada's fake-suspend."""
    if not shutil.which('gamescopectl'): return
    rt = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}')
    for sock in sorted(rt.glob('gamescope-[0-9]*')):
        if not re.fullmatch(r'gamescope-\d+', sock.name): continue
        env = {**os.environ, 'XDG_RUNTIME_DIR': str(rt), 'WAYLAND_DISPLAY': sock.name, 'GAMESCOPE_WAYLAND_DISPLAY': sock.name}
        try: subprocess.run(['gamescopectl', 'drm_sleep_internal_screen', '1' if on else '0'], env=env, capture_output=True, timeout=4)
        except (OSError, subprocess.SubprocessError): pass


def sleep_game(tandem, on):
    """Freeze a running game on standby entry (even for fake-suspend, whose app.slice check misses Tandem's child session)
    and thaw it on wake while shifting 'since' forward so slept hours never count as play time."""
    if on:
        if not SLEEP_STATE['since']: SLEEP_STATE['since'] = time.time()
        if tandem and tandem.run and not tandem.run.get('paused') and not tandem.dry and tandem.proc and not SLEEP_STATE['froze']:
            try:
                tandem.send(signal.SIGSTOP)
                SLEEP_STATE['froze'] = True
            except ProcessLookupError: pass
    else:
        since, froze = SLEEP_STATE['since'], SLEEP_STATE['froze']
        SLEEP_STATE['since'], SLEEP_STATE['froze'] = 0.0, False
        if tandem and tandem.run:
            if since: tandem.run['since'] += max(0, int(time.time() - since))
            if froze and not tandem.run.get('paused') and not tandem.dry and tandem.proc:
                try: tandem.send(signal.SIGCONT)
                except ProcessLookupError: pass


def doze(on, tandem=None, keep_audio=False):
    """Standby on a charger (or closed-lid music mode when keep_audio=True): panels asleep, stick lights off, Eco profile."""
    hw = (set_raw is _SET_RAW) and not (tandem and tandem.dry)
    if on and not DOZE:
        if not keep_audio:
            sleep_game(tandem, True)
        for key, name in BACKLIGHTS.items():
            try: DOZE[key] = lit(key, int((Path('/sys/class/backlight') / name / 'brightness').read_text()))
            except (OSError, ValueError): continue
            set_raw(key, 0)
        if keep_audio: DOZE['music'] = 1
        try: DOZE_FILE.write_text(json.dumps(DOZE))
        except OSError: pass
        if hw:
            panel_sleep(True)
            if not keep_audio and shutil.which('wpctl'):
                SLEEP_STATE['muted'] = '[MUTED]' in run_quiet(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
                run_quiet(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '1'])
                telemetry.stop_speaker_dsp()
            if shutil.which('armada-rgb'): run_quiet(['armada-rgb', 'sleep'])
            if shutil.which(thor.POWER[0]):
                SLEEP_STATE['profile'] = ((thor.state().get('power') or {}).get('profile')) or load_config().get('perf_profile') or 'Balanced'
                thor.change('profile', 'Eco')
        if tandem:
            tandem.power_open = False
            tandem.publish()
    elif not on:
        was = bool(DOZE)
        if was and hw: panel_sleep(False)
        for key, raw in list(DOZE.items()):
            if key in BACKLIGHTS: set_raw(key, lit(key, raw))
        DOZE.clear()
        DOZE_FILE.unlink(missing_ok=True)
        if hw:
            if was and shutil.which('armada-rgb'): run_quiet(['armada-rgb', 'wake'])
            if was and SLEEP_STATE['muted'] is False and shutil.which('wpctl'):
                run_quiet(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '0'])
            prof = ((tandem.run or {}).get('profile') if tandem else '') or SLEEP_STATE['profile'] or load_config().get('perf_profile')
            if prof and shutil.which(thor.POWER[0]):
                threading.Thread(target=thor.change, args=('profile', prof), daemon=True).start()
            night = load_config().get('night_mode', 'off')
            if night in ('warm', 'night'):
                threading.Thread(target=apply_night_mode, args=(night,), daemon=True).start()
            dsp_m = load_config().get('speaker_dsp', 'cinema')
            if dsp_m in telemetry.SPEAKER_DSP_MODES and dsp_m != 'off':
                threading.Thread(target=telemetry.apply_speaker_dsp, args=(dsp_m,), daemon=True).start()
        SLEEP_STATE['muted'], SLEEP_STATE['profile'] = None, None
        sleep_game(tandem, False)
        if tandem:
            tandem.power_open = False
            tandem.publish()
    return {'ok': True, 'doze': bool(DOZE)}


def action(name):
    if name == 'suspend' and on_power() and load_config().get('charger_standby', 'doze') != 'sleep':
        return doze(True)
    if name == 'wake': return doze(False)
    if name == 'sleep':
        if DOZE: doze(False)  # restore panel brightness before fake-suspend records and sleeps
        name = 'suspend'  # a real suspend even on a charger
    if name == 'steam':  # one session with Steam (PC games, system updates); the next start is Tandem again
        flag = HOME / '.config/tandem/steam-once'
        flag.parent.mkdir(parents=True, exist_ok=True); flag.touch()
        cmd = ['sudo', '-n', 'systemctl', 'restart', 'sddm']
    elif name in ACTIONS: cmd = ACTIONS[name]
    else: return {'error': 'unbekannte Aktion'}
    try: subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as error: return {'error': f'Geht hier nicht: {error}'}
    return {'ok': True, 'doze': False}


CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'tandem/config.json'


def load_config():
    try: return json.loads(CONFIG.read_text())
    except (OSError, ValueError): return {}


def save_config(data):
    """RetroAchievements account. The key stays in a file only its owner can read and never goes back to the page."""
    config = load_config()
    for key in ('ra_user', 'ra_key'):
        value = data.get(key)
        if isinstance(value, str) and value.strip(): config[key] = value.strip()[:80]
    # Battle.net login for WoW Forever's login.txt (see wow_login); like ra_key it never goes back to the page
    for key in ('bnet_email', 'bnet_password'):
        value = data.get(key)
        if isinstance(value, str) and value.strip() and '\n' not in value: config[key] = value.strip()[:128]
    if data.get('bnet_forget'): config.pop('bnet_email', None); config.pop('bnet_password', None)
    # Google OAuth client ("TV and Limited Input devices") for YouTube's sign-in (decks/youtube.py); never goes back to a page
    for key, pattern in (('yt_client_id', r'[0-9A-Za-z\-]{8,90}\.apps\.googleusercontent\.com'), ('yt_client_secret', r'[0-9A-Za-z_\-]{8,80}')):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            if not re.fullmatch(pattern, value.strip()): return {**public_config(), 'error': 'Die Client-ID oder das Client-Secret sieht nicht richtig aus.'}
            config[key] = value.strip()
    if data.get('yt_forget'):
        config.pop('yt_client_id', None); config.pop('yt_client_secret', None)
        prof, cfile, afile = yt_paths()
        shutil.rmtree(prof, ignore_errors=True); cfile.unlink(missing_ok=True); afile.unlink(missing_ok=True)
        afile.with_name('youtube-device.json').unlink(missing_ok=True)
    extra = {}
    if isinstance(data.get('yt_cookies'), str):
        ok, err = import_yt_cookies_text(data['yt_cookies'])
        if not ok: return {**public_config(), 'error': err}
        extra['text'] = 'YouTube-Cookies gespeichert.'
    if isinstance(data.get('kb_layout'), str) and data.get('kb_layout') in ('de', 'us'): config['kb_layout'] = data['kb_layout']
    if data.get('controls_style') in ('thor', 'xbox'):
        config['controls_style'] = data['controls_style']
    if data.get('hud_level') in (0, 1, 2, 3):
        config['hud_level'] = int(data['hud_level'])
        telemetry.set_hud(config['hud_level'])
    if isinstance(data.get('kb_haptics'), bool): config['kb_haptics'] = data['kb_haptics']
    if isinstance(data.get('ui_haptics'), bool): config['ui_haptics'] = data['ui_haptics']
    if data.get('rgb_mode') in telemetry.RGB_MODES:
        config['rgb_mode'] = data['rgb_mode']
        config['rgb_sync'] = (data['rgb_mode'] != 'static')
    elif isinstance(data.get('rgb_sync'), bool):
        config['rgb_sync'] = data['rgb_sync']
        config['rgb_mode'] = ('cover' if data['rgb_sync'] else 'static') if config.get('rgb_mode') in (None, 'cover', 'static') else ('static' if not data['rgb_sync'] else config['rgb_mode'])
    if data.get('lang') in ('de', 'en'): config['lang'] = data['lang']
    if data.get('theme') in [t['id'] for t in themes()]: config['theme'] = data['theme']
    if data.get('view_mode') in ('grid', 'stage'): config['view_mode'] = data['view_mode']
    if isinstance(data.get('overlays'), bool): config['overlays'] = data['overlays']
    if data.get('motion') in ('full', 'reduced'): config['motion'] = data['motion']
    if data.get('rest_min') in (0, 1, 3, 5, 10): config['rest_min'] = data['rest_min']
    if data.get('saver_style') in ('kosmos', 'arcade', 'aurora', 'minimal'): config['saver_style'] = data['saver_style']
    if data.get('charge_alert') in (0, 80, 90): config['charge_alert'] = int(data['charge_alert'])
    if data.get('ui_sounds') in ('off', 'subtle'): config['ui_sounds'] = data['ui_sounds']
    if isinstance(data.get('lid_sleep'), bool): config['lid_sleep'] = data['lid_sleep']
    if isinstance(data.get('lid_music'), bool): config['lid_music'] = data['lid_music']
    if isinstance(data.get('dock_dim'), bool): config['dock_dim'] = data['dock_dim']
    if isinstance(data.get('wol_mac'), str):
        mac = data['wol_mac'].strip()
        if not mac: config.pop('wol_mac', None)
        elif re.fullmatch(r'[0-9A-Fa-f]{2}([:\-][0-9A-Fa-f]{2}){5}', mac): config['wol_mac'] = mac.upper().replace('-', ':')
        else: return {**public_config(), 'error': 'Bitte eine gültige MAC-Adresse eintragen (z. B. AA:BB:CC:DD:EE:FF).'}
    if data.get('charger_standby') in ('doze', 'sleep'): config['charger_standby'] = data['charger_standby']
    if data.get('night_mode') in NIGHT_MODES:
        config['night_mode'] = data['night_mode']
        threading.Thread(target=apply_night_mode, args=(data['night_mode'],), daemon=True).start()
    if data.get('oled_vibrance') in OLED_VIBRANCE:
        config['oled_vibrance'] = data['oled_vibrance']
        threading.Thread(target=apply_oled_vibrance, args=(data['oled_vibrance'],), daemon=True).start()
    if isinstance(data.get('low_latency'), bool):
        config['low_latency'] = data['low_latency']
        threading.Thread(target=apply_low_latency, args=(data['low_latency'],), daemon=True).start()
    if data.get('speaker_dsp') in telemetry.SPEAKER_DSP_MODES:
        config['speaker_dsp'] = data['speaker_dsp']
        threading.Thread(target=telemetry.apply_speaker_dsp, args=(data['speaker_dsp'],), daemon=True).start()
    ra_changed = False
    if isinstance(data.get('ra_zerolag'), bool):
        config['ra_zerolag'] = data['ra_zerolag']
        ra_changed = True
    if isinstance(data.get('ra_autoresume'), bool):
        config['ra_autoresume'] = data['ra_autoresume']
        ra_changed = True
    if data.get('ra_shader') in companion.RA_SHADERS:
        config['ra_shader'] = data['ra_shader']
        ra_changed = True
    if ra_changed:
        threading.Thread(target=companion.configure_retroarch, args=(dict(config),), daemon=True).start()
    if isinstance(data.get('save_auto'), bool): config['save_auto'] = data['save_auto']
    if isinstance(data.get('cloud_saves'), bool): config['cloud_saves'] = data['cloud_saves']
    if isinstance(data.get('replay_buffer'), bool):
        config['replay_buffer'] = data['replay_buffer']
        if not data['replay_buffer']:
            thor_features.REPLAY.stop()
    if isinstance(data.get('dock_pad_swap'), bool): config['dock_pad_swap'] = data['dock_pad_swap']
    if isinstance(data.get('bt_low_latency'), bool):
        config['bt_low_latency'] = data['bt_low_latency']
        threading.Thread(target=thor_airpods.apply_bt_low_latency, args=(data['bt_low_latency'],), daemon=True).start()
    if isinstance(data.get('airpods_ear_pause'), bool):
        config['airpods_ear_pause'] = data['airpods_ear_pause']
        thor_airpods.MANAGER.set_ear_pause(data['airpods_ear_pause'])
    if isinstance(data.get('auto_update'), bool): config['auto_update'] = data['auto_update']
    if isinstance(data.get('auto_companions'), bool): config['auto_companions'] = data['auto_companions']
    travel_changed = None
    if isinstance(data.get('travel_mode'), bool) and data['travel_mode'] != config.get('travel_mode', False):
        config['travel_mode'] = data['travel_mode']
        travel_changed = data['travel_mode']
    if isinstance(data.get('auto_travel'), bool): config['auto_travel'] = data['auto_travel']
    hz_changed = False
    if data.get('panel_hz') in (60, 120):
        config['panel_hz'] = int(data['panel_hz'])
        hz_changed = True
    if isinstance(data.get('ai_workdir'), str):
        wd = data['ai_workdir'].strip()
        if not wd: config.pop('ai_workdir', None)
        elif len(wd) <= 180 and '\n' not in wd: config['ai_workdir'] = wd
    if isinstance(data.get('save_target'), str):
        st = data['save_target'].strip()
        if not st: config['save_target'] = ''
        elif re.fullmatch(r'[A-Za-z0-9._\-@]+:[A-Za-z0-9._\-~/]{1,140}', st): config['save_target'] = st
        else: return {**public_config(), 'error': 'Das Sicherungsziel muss die Form benutzer@server:pfad haben.'}
    if data.get('perf_profile') in thor.PROFILES: config['perf_profile'] = data['perf_profile']  # set again at every start  # minutes until the screens go black to spare the OLED, 0 = never
    source = data.get('update_url')  # where Tandem looks for new versions of itself (see self_update)
    if isinstance(source, str):
        source = source.strip().rstrip('/')
        if not source: config['update_url'] = ''  # empty: never look (no entry at all: the project's releases)
        elif re.fullmatch(r'(https|file)://[A-Za-z0-9.\-_~:/\[\]%]{3,190}', source): config['update_url'] = source
        else: return {**public_config(), 'error': 'Die Update-Quelle muss mit https:// beginnen.'}
    own = data.get('remote_url')  # an address of the owner's own under which the settings page is reachable (reverse proxy)
    if isinstance(own, str):
        own = own.strip().rstrip('/')
        if not own: config.pop('remote_url', None)
        elif re.fullmatch(r'https?://[A-Za-z0-9.\-_~:/\[\]%]{3,92}', own): config['remote_url'] = own
        else: return {**public_config(), 'error': 'Die Adresse muss mit https:// oder http:// beginnen (höchstens 100 Zeichen).'}
    password = data.get('ra_password')
    if isinstance(password, str) and password:
        if not config.get('ra_user'): return {**public_config(), 'error': 'Bitte auch den Benutzernamen eintragen.'}
        token, why = ra_login(config['ra_user'], password)
        if not token: return {**public_config(), 'error': why}
        config['ra_token'] = token
        extra['applied'] = apply_ra(config['ra_user'], token)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle: json.dump(config, handle)
    os.replace(tmp, CONFIG)
    if data.get('controls_style') in ('thor', 'xbox'):
        try:
            import controls
            done = controls.apply(config['controls_style'])
            if done: extra['text'] = 'Angeglichen: ' + ', '.join(done)
        except Exception: pass
    if travel_changed is not None:
        apply_travel_effects(travel_changed)
        extra['text'] = 'Unterwegs-Sparmodus aktiviert (Eco · 60 Hz · LEDs aus).' if travel_changed else 'Unterwegs-Sparmodus beendet (volle Leistung).'
    elif hz_changed:
        apply_fps_limit(base_panel_hz(config))
    return {**public_config(), **extra}


def ra_login(user, password):
    """Sign in to RetroAchievements; returns (token, None) or (None, why). The password is used for this one request only."""
    import urllib.parse, urllib.request, urllib.error
    request = urllib.request.Request('https://retroachievements.org/dorequest.php',
                                     data=urllib.parse.urlencode({'r': 'login2', 'u': user, 'p': password}).encode(),
                                     headers={'User-Agent': 'Tandem/0.1 (game launcher)'})
    try:
        with urllib.request.urlopen(request, timeout=20) as reply: data = json.loads(reply.read() or b'{}')
    except urllib.error.HTTPError as error:
        try: data = json.loads(error.read() or b'{}')
        except ValueError: data = {}
    except (OSError, ValueError): return None, 'RetroAchievements ist gerade nicht erreichbar.'
    if data.get('Success') and data.get('Token'): return data['Token'], None
    return None, 'Benutzername oder Passwort stimmt nicht.' if data.get('Code') == 'invalid_credentials' else 'Anmeldung abgelehnt.'


def set_ini(path, section, pairs):
    """Set keys in one section of an ini file (created if missing); everything else stays as it is."""
    text = path.read_text(errors='replace') if path.is_file() else ''
    head = re.search(r'(?m)^\[' + re.escape(section) + r'\][ \t]*$', text)
    if not head:
        text = text.rstrip('\n') + ('\n\n' if text.strip() else '') + f'[{section}]\n'
        head = re.search(r'(?m)^\[' + re.escape(section) + r'\][ \t]*$', text)
    nxt = re.search(r'(?m)^\[', text[head.end():])
    end = head.end() + nxt.start() if nxt else len(text)
    body = text[head.end():end]
    for key, value in pairs:
        line, pattern = f'{key} = {value}', re.compile(r'(?m)^' + re.escape(key) + r'[ \t]*=.*$')
        body = pattern.sub(lambda _: line, body, count=1) if pattern.search(body) else '\n' + line + body
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text[:head.end()] + body + text[end:])


def apply_ra(user, token):
    """Hand the RetroAchievements sign-in to every installed emulator. Hardcore stays off so save states keep working."""
    done, stamp = [], str(int(time.time()))
    cfg = HOME / '.var/app' / RA_REF / 'config/retroarch/retroarch.cfg'
    if cfg.is_file():
        text = cfg.read_text(errors='replace')
        for key, value in (('cheevos_enable', 'true'), ('cheevos_username', user), ('cheevos_token', token), ('cheevos_password', ''),
                           ('cheevos_hardcore_mode_enable', 'false')):
            line, pattern = f'{key} = "{value}"', re.compile(r'(?m)^' + re.escape(key) + r' = .*$')
            text = pattern.sub(lambda _: line, text, count=1) if pattern.search(text) else text.rstrip('\n') + '\n' + line + '\n'
        cfg.write_text(text); done.append('RetroArch')
    for name, path, section, pairs in (
            ('DuckStation', HOME / '.local/share/duckstation/settings.ini', 'Cheevos',
             [('Enabled', 'true'), ('ChallengeMode', 'false'), ('Username', user), ('Token', token), ('LoginTimestamp', stamp)]),
            ('PS2', HOME / '.config/ARMSX2/inis/PCSX2.ini', 'Achievements',
             [('Enabled', 'true'), ('ChallengeMode', 'false'), ('Username', user), ('Token', token), ('LoginTimestamp', stamp)]),
            ('PSP', HOME / '.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/ppsspp.ini', 'Achievements',
             [('AchievementsEnable', 'True'), ('AchievementsChallengeMode', 'False'), ('AchievementsUserName', user)]),
            ('Dolphin', HOME / '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/RetroAchievements.ini', 'Achievements',
             [('Enabled', 'True'), ('HardcoreEnabled', 'False'), ('Username', user), ('ApiToken', token)])):
        if not path.parent.is_dir(): continue
        set_ini(path, section, pairs); done.append(name)
        if name == 'PSP':  # PPSSPP keeps the token in its own file next to the settings
            secret = path.with_name('ppsspp_retroachievements.dat')
            fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as handle: handle.write(token)
    return done


def themes():
    """The looks to choose from: [{'id', 'name'}]. A theme is one JSON file (format: README); the ones that come with
    Tandem lie in ui/themes, the user's own in ~/.config/tandem/themes and win over a shipped one of the same file name."""
    found = {}
    for folder in (HERE / 'ui/themes', CONFIG.parent / 'themes'):
        for file in sorted(folder.glob('*.json')):
            try: name = json.loads(file.read_text()).get('name')
            except (OSError, ValueError, AttributeError): continue  # a broken file is no theme
            found[file.stem] = {'id': file.stem, 'name': name if isinstance(name, str) and name.strip() else file.stem}
    return sorted(found.values(), key=lambda t: (t['id'] != 'toravo', t['name'].lower()))


UPDATE_URL = 'https://github.com/harmssi/thor-tandem/releases/latest/download'  # manifest.json and the archive are release assets
VERSION = (HERE / 'VERSION').read_text().strip() if (HERE / 'VERSION').is_file() else '0'


def self_update(apply=False):
    """Looks at <update_url>/manifest.json ({"version", "file", "sha256"}) and, with apply, installs that release: the
    archive must match the checksum, the running installation is kept in tandem.prev and comes back if the new
    version's install.sh or self-test fails. No address configured: does nothing."""
    # shortcut: the checksum comes from the same server as the archive (guards against damage, not against a taken-over
    # server), sign the manifest before pointing this at a public address
    import io, shutil, tarfile, tempfile, urllib.request
    url, number = load_config().get('update_url', UPDATE_URL), lambda v: tuple(int(n) for n in re.findall(r'\d+', str(v)))
    if not url: return {'version': VERSION, 'text': 'Keine Update-Quelle eingetragen.'}
    try:
        with urllib.request.urlopen(url + '/manifest.json', timeout=15) as reply: manifest = json.loads(reply.read(100000))
        new, name = str(manifest['version']), os.path.basename(str(manifest['file']))
        if number(new) <= number(VERSION): return {'version': VERSION, 'text': f'Tandem {VERSION} ist aktuell.'}
        if not apply: return {'version': VERSION, 'new': new, 'text': f'Version {new} ist verfügbar.'}
        with urllib.request.urlopen(f'{url}/{name}', timeout=120) as reply: data = reply.read(200 << 20)
    except (OSError, ValueError, KeyError, TypeError): return {'version': VERSION, 'error': 'Die Update-Quelle ist nicht erreichbar oder liefert kein gültiges Manifest.'}
    if hashlib.sha256(data).hexdigest() != manifest.get('sha256'): return {'version': VERSION, 'error': 'Das Update ist beschädigt (Prüfsumme stimmt nicht) – nichts geändert.'}
    prev = HERE.parent / 'tandem.prev'
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with tarfile.open(fileobj=io.BytesIO(data)) as tar: tar.extractall(tmp, filter='data')
            shutil.rmtree(prev, ignore_errors=True); shutil.copytree(HERE, prev, symlinks=True, ignore=shutil.ignore_patterns('ff-*', '__pycache__'))  # ff-*: browser profiles of the old front end
            done = subprocess.run(['bash', str(Path(tmp) / 'tandem/install.sh')], capture_output=True, text=True, timeout=300, env={**os.environ, 'TANDEM_DEST': str(HERE)})
            ok = done.returncode == 0 and 'Selbsttest: ok' in done.stdout
        except (OSError, tarfile.TarError, subprocess.SubprocessError): ok = False
        if not ok:
            if prev.is_dir(): shutil.copytree(prev, HERE, dirs_exist_ok=True)
            return {'version': VERSION, 'error': 'Das Update ließ sich nicht installieren – die bisherige Version ist wieder da.'}
    return {'version': VERSION, 'new': new, 'text': f'Version {new} ist installiert und gilt ab dem nächsten Start von Tandem.'}


def public_config():
    config, looks = load_config(), themes()
    plex_ok = False
    try: plex_ok = bool(json.loads((CONFIG.parent / 'media/plex.json').read_text()).get('token'))
    except (OSError, ValueError, AttributeError): pass
    yt_oauth = bool(config.get('yt_client_id') and config.get('yt_client_secret'))
    yt_cookie = yt_cookie_signed_in()
    yt_auth = yt_auth_signed_in()
    return {'ra_user': config.get('ra_user', ''), 'ra_key_set': bool(config.get('ra_key')), 'ra_login': bool(config.get('ra_token')),
            'bnet_set': bool(config.get('bnet_email') and config.get('bnet_password')),
            'yt_set': yt_auth or yt_cookie, 'yt_auth': yt_auth, 'yt_cookie': yt_cookie, 'yt_oauth': yt_oauth,
            'plex_set': plex_ok, 'lid_sleep': config.get('lid_sleep', True),
            'lid_music': config.get('lid_music', True), 'dock_dim': config.get('dock_dim', True),
            'wol_mac': config.get('wol_mac', ''),
            'charger_standby': config.get('charger_standby') if config.get('charger_standby') in ('doze', 'sleep') else 'doze',
            'night_mode': config.get('night_mode') if config.get('night_mode') in NIGHT_MODES else 'off',
            'oled_vibrance': config.get('oled_vibrance') if config.get('oled_vibrance') in OLED_VIBRANCE else 'vibrant',
            'low_latency': config.get('low_latency', True),
            'speaker_dsp': config.get('speaker_dsp') if config.get('speaker_dsp') in telemetry.SPEAKER_DSP_MODES else 'cinema',
            'ra_zerolag': bool(config.get('ra_zerolag', True)),
            'ra_autoresume': bool(config.get('ra_autoresume', True)),
            'ra_shader': config.get('ra_shader') if config.get('ra_shader') in companion.RA_SHADERS else 'sharp',
            'replay_buffer': bool(config.get('replay_buffer', False)),
            'dock_pad_swap': bool(config.get('dock_pad_swap', True)),
            'bt_low_latency': bool(config.get('bt_low_latency', True)),
            'airpods_ear_pause': bool(config.get('airpods_ear_pause', True)),
            'save_auto': config.get('save_auto', True),
            'cloud_saves': bool(config.get('cloud_saves', True)),
            'auto_update': config.get('auto_update', True),
            'auto_companions': config.get('auto_companions', True),
            'travel_mode': bool(config.get('travel_mode', False)),
            'auto_travel': bool(config.get('auto_travel', False)),
            'panel_hz': 60 if int(config.get('panel_hz') or 120) == 60 else 120,
            'ai_workdir': config.get('ai_workdir', ''),
            'save_target': config.get('save_target', saves.DEFAULT_TARGET),
            'view_mode': config.get('view_mode') if config.get('view_mode') in ('grid', 'stage') else 'grid',
            'overlays': config.get('overlays', True),
            'motion': config.get('motion') if config.get('motion') in ('full', 'reduced') else 'full',
            'kb_layout': config.get('kb_layout', ''), 'kb_haptics': config.get('kb_haptics', True),
            'ui_haptics': config.get('ui_haptics', True),
            'rgb_mode': config['rgb_mode'] if config.get('rgb_mode') in telemetry.RGB_MODES else ('cover' if config.get('rgb_sync', True) else 'static'),
            'rgb_sync': (config['rgb_mode'] != 'static') if config.get('rgb_mode') in telemetry.RGB_MODES else config.get('rgb_sync', True),
            'controls_style': config.get('controls_style') if config.get('controls_style') in ('thor', 'xbox') else 'thor',
            'hud_level': int(config['hud_level']) if config.get('hud_level') in (0, 1, 2, 3) else 0,
            'saver_style': config.get('saver_style') if config.get('saver_style') in ('kosmos', 'arcade', 'aurora', 'minimal') else 'kosmos',
            'charge_alert': int(config['charge_alert']) if config.get('charge_alert') in (0, 80, 90) else 0,
            'ui_sounds': config.get('ui_sounds') if config.get('ui_sounds') in ('off', 'subtle') else 'off',
            'lang': 'en' if config.get('lang') == 'en' else 'de', 'remote_url': config.get('remote_url', ''), 'rest_min': config.get('rest_min', 3), 'version': VERSION, 'update_url': config.get('update_url', UPDATE_URL), 'theme': config.get('theme') if config.get('theme') in [t['id'] for t in looks] else 'toravo', 'themes': looks}


RA_CONSOLES = {'megadrive': 1, 'genesis': 1, 'n64': 2, 'snes': 3, 'sfc': 3, 'gb': 4, 'gba': 5, 'gbc': 6,
               'nes': 7, 'famicom': 7, 'fds': 7, 'pcengine': 8, 'supergrafx': 8, 'segacd': 9, 'sega32x': 10,
               'mastersystem': 11, 'sg-1000': 33, 'psx': 12, 'atarilynx': 13, 'ngp': 14, 'ngpc': 14,
               'gamegear': 15, 'gc': 16, 'nds': 18, 'wii': 19, 'ps2': 21, 'pokemini': 24, 'atari2600': 25,
               'arcade': 27, 'fbneo': 27, 'fba': 27, 'neogeo': 27, 'cps': 27, 'cps1': 27, 'cps2': 27, 'cps3': 27, 'mame': 27,
               'virtualboy': 28, 'msx': 29, 'msx2': 29, 'saturn': 39, 'dreamcast': 40, 'psp': 41, '3do': 43,
               'colecovision': 44, 'intellivision': 45, 'vectrex': 46, 'atari7800': 51,
               'wonderswan': 53, 'wonderswancolor': 53, 'neogeocd': 56, 'n3ds': 62, 'pcenginecd': 76}
RA_CACHE = {}  # (kind, id) -> (time, data)


def ra_call(name, **query):
    config = load_config()
    if not config.get('ra_key'): return None
    import urllib.parse, urllib.request
    query['y'] = config['ra_key']
    request = urllib.request.Request(f'https://retroachievements.org/API/{name}.php?{urllib.parse.urlencode(query)}',
                                     headers={'User-Agent': 'Tandem/0.1 (game launcher)'})  # the default Python agent is refused
    try:
        with urllib.request.urlopen(request, timeout=15) as reply: return json.loads(reply.read() or b'null')
    except (OSError, ValueError): return None


def ra_norm(title):
    """'Legend of Zelda, The: The Minish Cap' and 'The Legend of Zelda - The Minish Cap' compare equal."""
    title = re.sub(r'^(.*?), (The|A|An)\b', r'\2 \1', title)
    return re.sub(r'[^a-z0-9]+', '', title.lower())


def achievements(game):
    """Progress for one game: {'total', 'earned', 'points', 'list'} or {'note': why there is nothing to show}."""
    config = load_config()
    console = RA_CONSOLES.get(game.get('s'))
    if not config.get('ra_key') or not config.get('ra_user'): return {'note': 'RetroAchievements ist nicht eingerichtet (Einstellungen › Konten).'}
    if not console: return {'note': 'Für dieses System gibt es hier keine Erfolge.'}
    now = time.time()
    cached = RA_CACHE.get(('list', console))
    if not cached or now - cached[0] > 86400:
        data = ra_call('API_GetGameList', i=console, f=1)
        if not isinstance(data, list): return {'note': 'RetroAchievements ist gerade nicht erreichbar.'}
        cached = RA_CACHE[('list', console)] = (now, {ra_norm(g.get('Title', '')): g.get('ID') for g in data})
    game_id = cached[1].get(ra_norm(game['t']))
    if not game_id: return {'note': 'Kein passender Eintrag bei RetroAchievements gefunden.'}
    progress = RA_CACHE.get(('game', game_id))
    if not progress or now - progress[0] > 120:
        data = ra_call('API_GetGameInfoAndUserProgress', g=game_id, u=config['ra_user'])
        if not isinstance(data, dict): return {'note': 'RetroAchievements ist gerade nicht erreichbar.'}
        items = sorted((data.get('Achievements') or {}).values(), key=lambda a: (not a.get('DateEarned'), a.get('DisplayOrder') or 0))
        result = {'total': len(items), 'earned': sum(1 for a in items if a.get('DateEarned')),
                  'points': sum(int(a.get('Points') or 0) for a in items if a.get('DateEarned')),
                  'list': [{'t': a.get('Title', ''), 'd': a.get('Description', ''), 'p': a.get('Points', 0), 'e': bool(a.get('DateEarned'))} for a in items[:80]]}
        progress = RA_CACHE[('game', game_id)] = (now, result)
    return progress[1]


# Emulators the Armada Store does not carry. Tandem fetches them from the project's own release page and keeps them current.
EXTRAS = {'eden': {'name': 'Eden (Switch)', 'api': 'https://git.eden-emu.dev/api/v1/repos/eden-emu/eden/releases?limit=1',
                   'asset': r'^Eden-Linux-v[\d.]+-aarch64-gcc-standard\.AppImage$', 'file': 'Eden.AppImage',
                   'keys': ('BIOS/switch', '.local/share/eden/keys'), 'slot': 'eden'},
          # The project's nightly builds: same program file, so choosing one replaces the other. The release there has
          # no attached files; the download address stands in its text.
          'eden-nightly': {'name': 'Eden (Switch) Nightly', 'api': 'https://git.eden-emu.dev/api/v1/repos/eden-ci/nightly/releases?limit=1',
                           'body': r'https://nightly\.eden-emu\.dev/[\w./-]+aarch64-gcc-standard\.AppImage', 'file': 'Eden.AppImage',
                           'keys': ('BIOS/switch', '.local/share/eden/keys'), 'slot': 'eden'}}


def extras_state():
    versions = load_config().get('versions', {})
    return [{'id': key, 'name': e['name'], 'installed': (HOME / 'Applications' / e['file']).is_file(), 'version': versions.get(e.get('slot', key))}
            for key, e in EXTRAS.items()]


def update_extra(key, roots=()):
    """Install or update one extra emulator. Returns a sentence for the screen."""
    import urllib.request
    extra = EXTRAS.get(key)
    if not extra: return 'Unbekanntes Paket.'
    agent = {'User-Agent': 'Tandem/0.1 (game launcher)'}
    try:
        with urllib.request.urlopen(urllib.request.Request(extra['api'], headers=agent), timeout=20) as reply: release = json.loads(reply.read())[0]
    except (OSError, ValueError, IndexError, KeyError): return f"{extra['name']}: Die Release-Seite ist nicht erreichbar."
    if 'body' in extra: url = (re.search(extra['body'], str(release.get('body', ''))) or [''])[0]
    else:
        asset = next((a for a in release.get('assets', []) if re.match(extra['asset'], a.get('name', ''))), None)
        url = (asset or {}).get('browser_download_url', '')
    if not url.startswith('https://'): return f"{extra['name']}: Kein passendes Paket für dieses Gerät gefunden."
    target, tag = HOME / 'Applications' / extra['file'], str(release.get('tag_name', ''))
    config = load_config()
    slot = extra.get('slot', key)  # what is installed is remembered per program file, not per source
    if target.is_file() and config.get('versions', {}).get(slot) == tag: return f"{extra['name']} {tag} ist aktuell."
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix('.part')
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=agent), timeout=60) as reply, open(part, 'wb') as out:
            while chunk := reply.read(1 << 20): out.write(chunk)
        with open(part, 'rb') as check:
            if check.read(4) != b'\x7fELF': raise OSError('kein Programm')
    except OSError as error:
        part.unlink(missing_ok=True)
        return f"{extra['name']}: Download fehlgeschlagen ({error})."
    part.chmod(0o755)
    os.replace(part, target)
    config = load_config(); config.setdefault('versions', {})[slot] = tag
    tmp = CONFIG.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle: json.dump(config, handle)
    os.replace(tmp, CONFIG)
    source, dest = extra.get('keys', (None, None))
    for root in roots if source else ():  # the user's own key files from the card, if the emulator has none yet
        folder = Path(root).parent / source
        for file in folder.glob('*.keys') if folder.is_dir() else ():
            (HOME / dest).mkdir(parents=True, exist_ok=True)
            if not (HOME / dest / file.name).exists(): (HOME / dest / file.name).write_bytes(file.read_bytes())
    if slot == 'eden':
        # shortcut: on the Thor the software renderer is Vulkan device 0 and the Adreno is device 1; Eden defaults to 0.
        # Upgrade when Eden can be told to prefer a hardware GPU by name.
        set_ini(HOME / '.config/eden/qt-config.ini', 'Renderer', [('vulkan_device\\default', 'false'), ('vulkan_device', '1')])
    return f"{extra['name']} {tag} ist installiert."


class Keyboard:
    """A virtual keyboard (uinput) for the on-screen keys of the terminal tile. Created on first use."""
    MODS = {'shift': 42, 'ctrl': 29, 'alt': 56, 'altgr': 100}

    def __init__(self): self.fd, self.lock = None, threading.Lock()

    def open(self):
        import fcntl, struct
        fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(fd, 0x40045564, 1)                       # UI_SET_EVBIT EV_KEY
        for code in range(1, 128): fcntl.ioctl(fd, 0x40045565, code)  # UI_SET_KEYBIT: the whole main block
        fcntl.ioctl(fd, 0x405c5503, struct.pack('HHHH80sI', 3, 0x1209, 0x7a11, 1, b'Tandem on-screen keyboard', 0))  # UI_DEV_SETUP
        fcntl.ioctl(fd, 0x5501)                               # UI_DEV_CREATE
        time.sleep(0.6)                                       # the compositor needs a moment to adopt it
        self.fd = fd

    def press(self, code, mods):
        import struct
        if not 1 <= code < 128: return {'error': 'unbekannte Taste'}
        with self.lock:
            try:
                if self.fd is None: self.open()
                held = [self.MODS[m] for m in mods if m in self.MODS]
                for seq in ([(c, 1) for c in held], [(code, 1), (code, 0)], [(c, 0) for c in reversed(held)]):
                    for key, value in seq:
                        os.write(self.fd, struct.pack('llHHi', 0, 0, 1, key, value) + struct.pack('llHHi', 0, 0, 0, 0, 0))
                    time.sleep(0.03)  # shorter gaps lose AltGr combinations
            except OSError as error: return {'error': f'Tastatur nicht verfügbar: {error}'}
        return {'ok': True}

    def type_text(self, text, layout='de'):
        """Type a short ASCII snippet (such as '@', '.com', 'gmail.com') via evdev keycodes matching the active XKB layout."""
        base = {'a': 30, 'b': 48, 'c': 46, 'd': 32, 'e': 18, 'f': 33, 'g': 34, 'h': 35, 'i': 23, 'j': 36, 'k': 37, 'l': 38,
                'm': 50, 'n': 49, 'o': 24, 'p': 25, 'q': 16, 'r': 19, 's': 31, 't': 20, 'u': 22, 'v': 47, 'w': 17, 'x': 45,
                'y': 44 if layout == 'de' else 21, 'z': 21 if layout == 'de' else 44,
                '1': 2, '2': 3, '3': 4, '4': 5, '5': 6, '6': 7, '7': 8, '8': 9, '9': 10, '0': 11, '.': 52, '-': 53 if layout == 'de' else 12}
        for ch in str(text)[:64]:
            if ch == '@': res = self.press(16, ['altgr']) if layout == 'de' else self.press(3, ['shift'])
            elif ch == '_': res = self.press(53 if layout == 'de' else 12, ['shift'])
            elif ch.lower() in base: res = self.press(base[ch.lower()], ['shift'] if ch.isupper() else [])
            else: continue
            if isinstance(res, dict) and 'error' in res: return res
        return {'ok': True}


KEYBOARD = Keyboard()


def x11(display=None):
    """Open libX11 with proper 64-bit ctypes signatures and a quiet error handler. Returns (lib, dpy) or (None, None)."""
    import ctypes
    try:
        lib = ctypes.CDLL('libX11.so.6')
    except OSError:
        return None, None
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib.XFlush.argtypes = [ctypes.c_void_p]
    lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    lib.XKeysymToKeycode.restype = ctypes.c_ubyte
    lib.XKeycodeToKeysym.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int]
    lib.XKeycodeToKeysym.restype = ctypes.c_ulong
    global X_QUIET
    X_QUIET = X_QUIET or ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(lambda *_: 0)
    lib.XSetErrorHandler(X_QUIET)
    dpy_name = display if isinstance(display, bytes) else (str(display or os.environ.get('DISPLAY') or ':0').encode())
    dpy = lib.XOpenDisplay(dpy_name)
    if not dpy:
        return lib, None
    return lib, dpy


def x_press_code(code, mods=(), display=b':0'):
    """Inject an evdev keycode (1..127) + optional modifiers straight into :0's Xwayland via XTestFakeKeyEvent.
    More reliable than /dev/uinput when dual gamescope instances are active because it always targets the top screen."""
    import ctypes
    if not isinstance(code, int) or not 1 <= code < 128:
        return False
    lib, dpy = x11(display)
    if not dpy:
        return False
    try:
        xtst = ctypes.CDLL('libXtst.so.6')
        xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        held = [Keyboard.MODS[m] + 8 for m in mods if m in Keyboard.MODS]
        kc = code + 8  # standard Xorg / Xwayland evdev keycode offset
        for m in held:
            xtst.XTestFakeKeyEvent(dpy, m, 1, 0)
        xtst.XTestFakeKeyEvent(dpy, kc, 1, 0)
        xtst.XTestFakeKeyEvent(dpy, kc, 0, 0)
        for m in reversed(held):
            xtst.XTestFakeKeyEvent(dpy, m, 0, 0)
        lib.XSync(dpy, 0)
        return True
    except OSError:
        return False
    finally:
        lib.XCloseDisplay(dpy)


def x_type_char(ch, display=b':0'):
    """Inject a single character (including '@', '€', umlauts, '-', '.') straight into :0's Xwayland via XTestFakeKeyEvent,
    looking up the live X11 keycode and modifier level (Shift / ISO_Level3_Shift) so seat focus on :1 or gamescope's us
    uinput keymap never drops or mangles '@'. Returns True when sent."""
    import ctypes
    if not ch or len(ch) != 1: return False
    code_pt = ord(ch)
    sym = 0x20AC if ch == '€' else code_pt if 0x20 <= code_pt <= 0xFF else (0x01000000 | code_pt)
    lib, dpy = x11(display)
    if not dpy: return False
    try:
        xtst = ctypes.CDLL('libXtst.so.6')
        xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        kc = lib.XKeysymToKeycode(dpy, sym)
        if not kc: return False
        levels = [lib.XKeycodeToKeysym(dpy, kc, i) for i in range(8)]
        if sym not in levels: return False
        idx = levels.index(sym)
        mods = []
        if idx in (2, 3, 4, 5):
            lvl3 = lib.XKeysymToKeycode(dpy, 0xFE03) or 108  # XK_ISO_Level3_Shift (AltGr)
            if lvl3: mods.append(lvl3)
        if idx in (1, 3, 5):
            sh = lib.XKeysymToKeycode(dpy, 0xFFE1) or 50    # XK_Shift_L
            if sh: mods.append(sh)
        for m in mods: xtst.XTestFakeKeyEvent(dpy, m, 1, 0)
        xtst.XTestFakeKeyEvent(dpy, kc, 1, 0)
        xtst.XTestFakeKeyEvent(dpy, kc, 0, 0)
        for m in reversed(mods): xtst.XTestFakeKeyEvent(dpy, m, 0, 0)
        lib.XSync(dpy, 0)
        return True
    except OSError:
        return False
    finally:
        lib.XCloseDisplay(dpy)


def x_type_seq(seq):
    s = str(seq)[:512]
    delay = 0.005 if len(s) > 40 else 0.012
    for ch in s:
        if not x_type_char(ch): return False
        time.sleep(delay)
    return True


AI_AUTH = {'url': '', 'token': '', 'ts': 0.0, 'open': False}
AI_AUTH_TTL = 900  # 15 minutes


def ai_auth_state():
    """Current AI CLI QR-login bridge state (short LAN QR URL + whether an OAuth URL is ready)."""
    now = time.time()
    if AI_AUTH['token'] and now - AI_AUTH['ts'] > AI_AUTH_TTL:
        AI_AUTH.update(url='', token='', ts=0.0, open=False)
    ip = lan_address()
    scheme = 'https' if PAIR.get('tls') else 'http'
    port = PAIR.get('port') or 8378
    qr_url = f'{scheme}://{ip}:{port}/ai-login/{AI_AUTH["token"]}' if (ip and AI_AUTH['token']) else ''
    return {'open': bool(AI_AUTH['open']), 'has_url': bool(AI_AUTH['url']), 'qr': qr_url,
            'host': f'{ip}:{port}' if ip else '', 'ts': int(AI_AUTH['ts'])}


def ai_auth_register(tandem, url='', open_ui=True):
    """Record an OAuth login URL from agy/claude and publish the short QR bridge URL to the screens."""
    import secrets
    now = time.time()
    if not AI_AUTH['token'] or now - AI_AUTH['ts'] > AI_AUTH_TTL:
        AI_AUTH['token'] = secrets.token_hex(8)
    if url:
        AI_AUTH['url'] = str(url).strip()
        try:
            STATE.mkdir(parents=True, exist_ok=True)
            (STATE / 'ai-auth-url.txt').write_text(AI_AUTH['url'] + '\n', encoding='utf-8')
        except OSError:
            pass
    AI_AUTH['ts'] = now
    AI_AUTH['open'] = bool(open_ui)
    st = ai_auth_state()
    if tandem is not None:
        tandem.publish('ai_auth', st)
        if url:
            tandem.publish('toast', {'text': 'QR-Code für KI-Anmeldung bereit.'})
    return {'ok': True, **st}


def ai_auth_open_browser(tandem):
    """Open the captured OAuth URL directly in a clean X11 Firefox window on the Thor's top screen."""
    url = AI_AUTH.get('url') or ''
    if not url:
        try:
            url = (STATE / 'ai-auth-url.txt').read_text(encoding='utf-8').strip()
        except OSError:
            url = ''
    if not url:
        return {'error': 'Noch kein Anmeldelink vorhanden.'}
    AI_AUTH['open'] = False
    if tandem is not None:
        tandem.publish('ai_auth', ai_auth_state())
    if tandem is not None and tandem.dry:
        return {'ok': True, 'url': url}
    write_ai_browser_wrapper()
    prof = STATE / 'ai-browser-profile'
    env = {**os.environ, 'DISPLAY': os.environ.get('DISPLAY') or ':0', 'MOZ_ENABLE_WAYLAND': '0', 'GDK_BACKEND': 'x11',
           'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'}
    try:
        subprocess.Popen(['firefox', '--profile', str(prof), '--new-tab', url],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, env=env)
        return {'ok': True}
    except OSError as err:
        return {'error': f'Browser konnte nicht gestartet werden: {err}'}


def ai_auth_submit(tandem, text):
    """Receive either a localhost OAuth callback URL or a copy-paste auth code from the phone QR page."""
    val = str(text or '').strip()
    if not val:
        return {'error': 'Bitte zuerst den Code oder Link einfügen.'}
    if re.match(r'^https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?/', val, re.I):
        if tandem is None or not tandem.dry:
            try:
                urllib.request.urlopen(val, timeout=8).read(2048)
            except Exception as err:
                return {'error': f'Lokaler Callback fehlgeschlagen: {err}'}
        AI_AUTH['open'] = False
        if tandem is not None:
            tandem.publish('ai_auth', ai_auth_state())
            tandem.publish('toast', {'text': 'KI-Anmeldung bestätigt.'})
        return {'ok': True, 'mode': 'callback', 'text': 'Anmeldung lokal bestätigt.'}
    if tandem is None or not tandem.dry:
        terms = x_windows_matching('konsole', 'foot', 'xterm')
        browsers = x_windows_matching('firefox', 'chromium', 'chrome')
        for wid in browsers:
            x_window('unmap', wid)
        for wid in terms:
            x_window('map', wid)
        time.sleep(0.15)
        if not x_type_seq(val):
            KEYBOARD.type_text(val, (tandem.run or {}).get('layout') or region_layout() if tandem else 'de')
        x_press_code(28) or KEYBOARD.press(28, [])
    AI_AUTH['open'] = False
    if tandem is not None:
        tandem.publish('ai_auth', ai_auth_state())
        tandem.publish('toast', {'text': 'Anmeldecode an Terminal gesendet.'})
    return {'ok': True, 'mode': 'code', 'text': 'Code an das Terminal auf dem Thor gesendet.'}


def ai_login_page(token, msg='', ok=False):
    """Compact mobile-friendly HTML page opened by scanning the Thor's AI-login QR code."""
    import html as _html
    url = AI_AUTH.get('url') or ''
    safe_url = _html.escape(url, quote=True)
    safe_tok = _html.escape(token, quote=True)
    banner = (f'<div class="msg {"ok" if ok else "err"}">{_html.escape(msg)}</div>' if msg else '')
    step1 = (f'<a class="btn go" href="{safe_url}" target="_blank" rel="noopener">1. Anmeldung im Browser öffnen ↗</a>'
             if url else
             '<div class="wait">Warte auf Anmeldelink vom Thor … (Seite lädt automatisch neu)</div><script>setTimeout(()=>location.reload(),2000)</script>')
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Toravo Tandem · KI-Anmeldung</title><style>
body{{margin:0;background:#090b10;color:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,Inter,sans-serif;padding:20px}}
.card{{max-width:460px;margin:0 auto;background:#141720;border:1px solid #2b2f3d;border-radius:18px;padding:22px}}
h1{{margin:0 0 8px;font-size:21px;color:#ff9f38}}p{{color:#a2a6b5;font-size:14px;line-height:1.45;margin:0 0 16px}}
.btn{{display:block;width:100%;box-sizing:border-box;text-align:center;text-decoration:none;border:0;border-radius:12px;padding:15px 16px;font-size:16px;font-weight:700;cursor:pointer}}
.go{{background:#ff8c1a;color:#090b10;margin-bottom:18px}}.send{{background:#34d399;color:#090b10;margin-top:12px}}
textarea{{width:100%;box-sizing:border-box;min-height:92px;border-radius:12px;border:1px solid #353949;background:#0c0e14;color:#f5f5f7;padding:12px;font-size:15px;font-family:ui-monospace,monospace}}
.msg{{padding:12px 14px;border-radius:10px;margin-bottom:14px;font-size:14px;font-weight:600}}
.ok{{background:#123528;color:#6ee7b7;border:1px solid #225e46}}.err{{background:#3a1919;color:#fca5a5;border:1px solid #6b2626}}
.wait{{padding:14px;border-radius:12px;background:#1d2130;color:#cbd5e1;font-size:14px;margin-bottom:18px}}
</style></head><body><div class="card"><h1>Toravo Tandem · KI-Anmeldung</h1>
<p>Melde dich bequem auf dem Handy an (Google / Claude) und sende danach den angezeigten Code oder die Callback-URL direkt an den Thor.</p>
{banner}{step1}
<form method="post" action="/ai-login/{safe_tok}">
<label for="code" style="display:block;font-size:13px;color:#cbd5e1;margin-bottom:6px;font-weight:600">2. Code oder Callback-URL hier einfügen:</label>
<textarea id="code" name="code" placeholder="4/0A... oder http://localhost:..." autocapitalize="off" autocomplete="off" spellcheck="false" required></textarea>
<button class="btn send" type="submit">An Thor senden ✓</button>
</form></div></body></html>'''


def ai_window_act(tandem, action):
    """Switch between browser (Firefox) and terminal (Konsole), close browser, or paste cleanly on :0."""
    if tandem.dry:
        return {'ok': True, 'action': action}
    if action == 'paste':
        wid = focused_window()
        props = run_quiet(['xprop', '-id', str(wid), 'WM_CLASS']).lower() if wid else ''
        mods = ['ctrl', 'shift'] if any(t in props for t in ('konsole', 'foot', 'xterm', 'alacritty', 'kitty')) else ['ctrl']
        if x_press_code(47, mods):
            return {'ok': True}
        return KEYBOARD.press(47, mods)
    browsers = x_windows_matching('firefox', 'chromium', 'chrome')
    terms = x_windows_matching('konsole', 'foot', 'xterm')
    if action == 'close_browser':
        for wid in browsers:
            x_window('close', wid)
        for wid in terms:
            x_window('map', wid)
        return {'ok': True, 'closed': len(browsers)}
    if action == 'toggle':
        cur = focused_window()
        if cur in browsers and terms:
            for wid in browsers:
                x_window('unmap', wid)
            for wid in terms:
                x_window('map', wid)
            return {'ok': True, 'active': 'term'}
        if browsers:
            for wid in browsers:
                x_window('map', wid)
            return {'ok': True, 'active': 'browser'}
        return {'ok': False, 'error': 'Kein Browser-Fenster offen.'}
    return {'error': 'Unbekannte Fenster-Aktion.'}


# Wine ignores AltGr from a virtual keyboard (@ came out as q in Battle.net's login): such a character goes in by pasting.
CLIP = '''import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication(sys.argv); app.clipboard().setText(sys.argv[1]); QTimer.singleShot(30000, app.quit); app.exec()'''


def paste(text):
    try: subprocess.Popen(['python3', '-c', CLIP, text], env={**os.environ, 'DISPLAY': ':0', 'QT_QPA_PLATFORM': 'xcb'},
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as error: return {'error': f'Einfügen geht nicht: {error}'}
    time.sleep(0.6)
    return KEYBOARD.press(47, ['ctrl'])
TERMINALS = [('konsole', ('--hide-menubar', '--hide-tabbar', '-p', 'Font=Monospace,17')), ('foot', ()), ('xterm', ('-fa', 'monospace', '-fs', '16'))]


SETUP_MARK = CONFIG.parent / 'setup-done'  # there: the first-run assistant has been through (or was skipped to its end)
STORE = HOME / 'homebrew/plugins/armada-store/py_modules'
STORE_IDS = {'RetroArch': 'retroarch', 'DuckStation': 'duckstation', 'Dolphin': 'dolphin', 'PPSSPP': 'ppsspp', 'ARMSX2': 'armsx2', 'Azahar': 'azahar',
             'melonDS': 'melonds', 'Flycast': 'flycast', 'Ymir': 'ymir', 'Cemu': 'cemu'}  # emulator -> its name in the Armada Store


def setup_info(tandem):
    """What the first-run assistant shows: the game folders with their systems, the systems that have games but no
    emulator, whether Tandem can install those itself, and the state of account, Wi-Fi and keyboard."""
    games = [g for g in tandem.library.games.values() if g.get('path')]
    folders = []
    for root in tandem.library.roots:
        counts = {}
        for g in games:
            if g['path'].startswith(str(root).rstrip('/') + '/'): counts[g['s']] = counts.get(g['s'], 0) + 1
        folders.append({'root': str(root), 'systems': [{'name': SYSTEMS[s][0], 'n': n} for s, n in sorted(counts.items(), key=lambda c: -c[1])]})
    missing = []
    for system in sorted({g['s'] for g in games}):
        if emulator(system)[0]: continue
        label = SYSTEMS[system][3][0][0] if SYSTEMS[system][3] else ''
        missing.append({'s': system, 'name': SYSTEMS[system][0], 'n': sum(1 for g in games if g['s'] == system), 'emu': label, 'store': STORE_IDS.get(label), 'extra': 'eden' if label == 'Eden' else None})
    config = public_config()
    return {'folders': folders, 'missing': missing, 'install': install_possible(), 'ra_user': config['ra_user'], 'ra_login': config['ra_login'],
            'wifi': system_info(tandem.library.roots)['ssid'], 'layout': region_layout()}


def install_possible():
    """Whether the Armada Store can be driven from here: its job runner needs root, so this only works where sudo lets
    this user run python3 without asking for a password. Tandem does not change that."""
    if not STORE.is_dir(): return False
    try: return subprocess.run(['sudo', '-n', '-l', 'python3'], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError): return False


def install_missing(tandem):
    """Installs the emulators that the library's systems lack: from the Armada Store (as setup.py does), Eden through
    Tandem's own updater. Runs in the background and says what came of it."""
    info = setup_info(tandem)
    apps, extras = sorted({m['store'] for m in info['missing'] if m['store']}), sorted({m['extra'] for m in info['missing'] if m['extra']})
    if apps and not info['install']: return {'error': 'Das geht hier nur mit Passwort: bitte im Desktop-Modus den Armada Store öffnen und dort installieren.'}
    if not apps and not extras: return {'text': 'Es fehlt nichts.'}
    code = f'''
import sys, time
sys.path.insert(0, {str(STORE)!r})
from armada_store import catalog, jobs
for app in {apps!r}:
    if catalog.installed_map().get(app, {{}}).get("installed"): continue
    jobs.start(app, "install")
    for _ in range(360):
        time.sleep(5)
        mine = [j for j in jobs.status() if j.get("appId") == app]
        if not mine or mine[0].get("phase") in ("done", "error", "failed", "cancelled"): break
    try: jobs.dismiss(app)
    except Exception: pass
'''
    def work():
        if apps and not tandem.dry: run_quiet(['sudo', '-n', 'python3', '-c', code], timeout=3600)
        for key in extras:
            if not tandem.dry: update_extra(key, tandem.library.roots)
        tandem.library.scan()
        left = [m['name'] for m in setup_info(tandem)['missing']]
        tandem.publish('library')
        tandem.publish('toast', {'text': 'Emulatoren sind installiert.' if not left else 'Noch ohne Emulator: ' + ', '.join(left)})
    threading.Thread(target=work, daemon=True).start()
    return {'text': 'Installation läuft – das dauert einige Minuten.', 'apps': apps, 'extras': extras}


def setup_command(tandem, data):
    """The assistant's moves, from either screen: open it (again), go to a step, finish it (sets the marker)."""
    if data.get('install'): return install_missing(tandem)
    if isinstance(data.get('step'), int) and not isinstance(data.get('step'), bool): tandem.setup['step'] = max(0, min(9, data['step']))
    if data.get('open') is True: tandem.setup.update(open=True, step=0)
    if data.get('done') or data.get('open') is False:
        tandem.setup.update(open=False, step=0)
        if data.get('done'):
            SETUP_MARK.parent.mkdir(parents=True, exist_ok=True); SETUP_MARK.touch()
            tandem.ui = {'tab': 0, 'sys': None, 'i': 0}
    tandem.publish()
    return {'ok': True, **tandem.setup}


def region_layout():
    """Keyboard layout for the terminal tile from the system language: German gets QWERTZ, everything else US."""
    chosen = load_config().get('kb_layout')
    if chosen in ('de', 'us'): return chosen
    language = (os.environ.get('LC_ALL') or os.environ.get('LANG') or '').lower()
    if not language or language.startswith(('c.', 'posix')):
        match = re.search(r'LANG=(\w+)', run_quiet(['localectl', 'status']))
        language = match[1].lower() if match else ''
    if language.startswith('de'): return 'de'
    # Handhelds are often left on the default language; the time zone still tells the region.
    zone = run_quiet(['timedatectl', 'show', '-p', 'Timezone', '--value']).strip()
    return 'de' if zone in ('Europe/Berlin', 'Europe/Vienna', 'Europe/Zurich', 'Europe/Busingen', 'Europe/Vaduz') else 'us'


WIFI = {'at': 0, 'networks': [], 'ssid': ''}  # the last answer about Wi-Fi, see system_info


def system_info(roots=(), rescan=False):
    """Wi-Fi state, visible networks and storage, for the System tab and the settings page. The Wi-Fi part is asked
    for at most every 15 s and never waits for a scan unless one is wanted (rescan): 'nmcli dev wifi list' on its own
    starts or waits for one now and then, which made a single answer take over 8 s."""
    if rescan or time.time() - WIFI['at'] > 15:
        networks, ssid = wifi_state(rescan)
        if networks or rescan or not WIFI['networks']: WIFI.update(networks=networks, ssid=ssid)  # no answer in time: the last one stays
        WIFI['at'] = time.time()
    storage = []
    for name, path in [('Intern', HOME)] + [(Path(r).parent.name or 'Karte', Path(r).parent) for r in roots if str(r).startswith(('/run/media', '/media'))][:1]:
        try:
            stat = os.statvfs(path)
            storage.append({'name': name, 'total': stat.f_blocks * stat.f_frsize, 'free': stat.f_bavail * stat.f_frsize})
        except OSError: pass
    return {'ssid': WIFI['ssid'], 'networks': WIFI['networks'], 'storage': storage, 'host': lan_address()}


def wifi_state(rescan=False):
    """(visible networks, name of the connected one)."""
    split = lambda line: [part.replace('\\:', ':') for part in re.split(r'(?<!\\):', line)]
    known = {split(l)[0] for l in run_quiet(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'], timeout=3).splitlines() if l.endswith('wireless')}
    found = {}  # one row per network name: a name is often sent by several access points
    scan, limit = (['--rescan', 'yes'], 25) if rescan else (['--rescan', 'no'], 3)  # a fresh scan takes a few seconds: only when the list is opened
    for line in run_quiet(['nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list', *scan], timeout=limit).splitlines():
        parts = split(line)
        if len(parts) < 4 or not parts[1]: continue
        entry = found.setdefault(parts[1], {'ssid': parts[1], 'active': False, 'signal': 0, 'secure': bool(parts[3].strip('-')), 'known': parts[1] in known})
        entry['active'] = entry['active'] or parts[0] == 'yes'
        entry['signal'] = max(entry['signal'], int(parts[2] or 0))
    networks = sorted(found.values(), key=lambda n: (not n['active'], -n['signal']))
    active = [split(l) for l in run_quiet(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show', '--active'], timeout=3).splitlines() if l.endswith('wireless')]
    return networks[:14], active[0][0] if active else ''


def wifi_connect(ssid, password=''):
    if not ssid or len(ssid) > 64: return {'error': 'Kein Netz gewählt.'}
    known = any(l.split(':')[0] == ssid for l in run_quiet(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show']).splitlines())
    cmd = ['nmcli', 'connection', 'up', 'id', ssid] if known and not password else ['nmcli', 'dev', 'wifi', 'connect', ssid] + (['password', password] if password else [])
    try: done = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError): return {'error': 'Verbinden hat zu lange gedauert.'}
    return {'ok': True} if done.returncode == 0 else {'error': 'Verbinden fehlgeschlagen – Passwort prüfen.'}


LINK = {'at': 0, 'value': None}


def wifi_link():
    """{'ssid', 'signal' 0-100} of the Wi-Fi link for the status bar, None without Wi-Fi. 'iw … link' asks the driver
    (a few ms, never a scan); the answer is kept for 20 s because both screens ask every 30 s."""
    if time.time() - LINK['at'] < 20: return LINK['value']
    iface = next((Path(d).parent.name for d in sorted(glob.glob('/sys/class/net/*/wireless'))), None)
    value = None
    if iface:
        out = run_quiet(['iw', 'dev', iface, 'link'], timeout=2)
        ssid, dbm = re.search(r'SSID: (.*)', out), re.search(r'signal: (-?\d+)', out)
        value = {'ssid': ssid[1].strip() if ssid else '', 'signal': max(0, min(100, 2 * (int(dbm[1]) + 100))) if dbm else 0}
    LINK.update(at=time.time(), value=value)
    return value


def battery():
    for supply in glob.glob('/sys/class/power_supply/*/capacity'):
        try:
            status = Path(supply).with_name('status').read_text().strip()
            return {'level': int(Path(supply).read_text()), 'charging': status in ('Charging', 'Full')}
        except (OSError, ValueError): pass
    return None


def thor_change(tandem, data):
    """One Thor setting from either screen or the settings page; both screens hear the new state."""
    key = str(data.get('key', ''))
    result = thor.change(key, data.get('value'))
    if 'error' not in result:
        if key == 'profile': save_config({'perf_profile': data.get('value')})
        tandem.publish('thor', {'thor': result})
    return result


def bluetooth_post(tandem, data):
    """Scan, power, or pair/connect/disconnect/forget one device; a device action runs in the background (pairing takes
    up to a minute) and ends with a toast on both screens."""
    try:
        if data.get('scan'): return bluetooth.scan()
        if 'power' in data: return bluetooth.power(bool(data['power']))
    except Exception: return {'error': 'Bluetooth antwortet nicht.'}
    addr, what = str(data.get('addr', '')), str(data.get('do', ''))
    if not re.fullmatch(r'[0-9A-F]{2}(:[0-9A-F]{2}){5}', addr) or what not in ('pair', 'connect', 'disconnect', 'forget'): return {'error': 'unbekannt'}
    def work():
        try: r = bluetooth.act(addr, what)
        except Exception: r = {'error': 'Bluetooth antwortet nicht.'}
        tandem.publish('toast', {'text': r.get('error') or r.get('text', '')})
    threading.Thread(target=work, daemon=True).start()
    return {'ok': True}


def controls_info():
    """The one button layout for everything under Tandem (controls.py) and where an emulator still differs."""
    try: import controls
    except ImportError: return {'table': [], 'off': []}
    try: off = controls.check()
    except Exception: off = []  # an unreadable emulator file must not cost the overview
    return {'table': controls.table(), 'off': off, 'style': controls.current_style()}


def controls_apply():
    try:
        import controls
        done = controls.apply()
    except ImportError: return {'error': 'Die Tastenbelegung ist in dieser Version nicht enthalten.'}
    except OSError as error: return {'error': f'Angleichen fehlgeschlagen: {error}'}
    return {'text': ('Angeglichen: ' + ', '.join(done)) if done else 'Alle Emulatoren haben schon die Tandem-Belegung.'}


def sysbackup_state(tandem=None):
    steam_dir = tandem.library.steam if tandem else (HOME / '.local/share/Steam')
    roots = tandem.library.roots if tandem else _LAST_ROOTS
    cl = {k: v for k, v in thor_storage.scan_storage_cleanup(HOME, steam_dir).items() if k != '_targets'}
    return {
        'backups': thor_storage.backup_overview(),
        'storage': thor_storage.storage_layout(),
        'cleanup': cl,
        'compress': thor_pro.scan_compressible_roms(roots),
    }


def updater_state(tandem):
    return thor_updater.overview(list(tandem.library.games.values()), rom_identity, tandem.library.roots, VERSION)


def handle_updater(tandem, data):
    act = str(data.get('action') or 'check')
    games = list(tandem.library.games.values())
    if act in ('check', 'update_all', 'update_app'):
        apply_upd = (act == 'update_all')
        target_app = str(data.get('id') or '') if act == 'update_app' else ''
        def _done_upd(r):
            if r.get('updated'):
                tandem.library.scan()
                tandem.publish('library')
            tandem.publish('updater', updater_state(tandem))
            tandem.publish('toast', {'text': r.get('error') or r.get('text', '')})
        res = thor_updater.start_update_job(
            games, rom_identity, roots=tandem.library.roots,
            apply_updates=apply_upd, target_app=target_app,
            self_update_fn=self_update, on_done=_done_upd,
        )
        tandem.publish('updater', updater_state(tandem))
        return res
    if act == 'sync_companions':
        def _work_comp():
            res_c = thor_updater.sync_all_companions(
                games, rom_identity, roots=tandem.library.roots,
                home=HOME, cfg_dir=CONFIG.parent, apply_updates=True, force_catalog=True,
            )
            tandem.publish('library')
            tandem.publish('updater', updater_state(tandem))
            changes = res_c.get('changes') or []
            msg = ('Begleiter aktualisiert: ' + ', '.join(changes[:4]) + '.') if changes else 'Alle Spiel-Begleiter sind aktuell und eingerichtet.'
            tandem.publish('toast', {'text': msg})
        threading.Thread(target=_work_comp, daemon=True).start()
        return {'ok': True, 'text': 'Prüfe & installiere Spiel-Begleiter …'}
    if act == 'rollback':
        res = thor_updater.rollback_appimage(str(data.get('id') or ''))
        tandem.publish('updater', updater_state(tandem))
        return res
    if act == 'rollback_turnip':
        res = thor_updater.rollback_turnip()
        tandem.publish('updater', updater_state(tandem))
        return res
    if act == 'add_feed':
        res = thor_updater.save_custom_feed(data.get('repo', ''), data.get('name', ''), data.get('asset', ''), data.get('file', ''))
        tandem.publish('updater', updater_state(tandem))
        return res
    if act == 'remove_feed':
        res = thor_updater.remove_custom_feed(data.get('id', ''))
        tandem.publish('updater', updater_state(tandem))
        return res
    return {'error': 'unbekannt'}


def handle_sysbackup(tandem, data):
    act = str(data.get('action') or 'backup')
    if act == 'backup':
        mode = 'full' if data.get('mode') == 'full' else 'profile'
        ssh_target = str(data.get('ssh') or load_config().get('save_target') or '')
        def _done_bk(r):
            tandem.publish('sysbackup', sysbackup_state())
            tandem.publish('toast', {'text': r.get('error') or r.get('text', '')})
        res = thor_storage.start_backup_async(mode=mode, ssh_target=ssh_target, on_done=_done_bk)
        tandem.publish('sysbackup', sysbackup_state())
        return res
    if act == 'restore':
        try: saves.backup(run_rsync=False)
        except Exception: pass
        res = thor_storage.restore_system_backup(data.get('file'))
        if res.get('ok'):
            tandem.library.scan()
            tandem.publish('library')
            tandem.publish('sysbackup', sysbackup_state())
        return res
    if act == 'check_sudo':
        return thor_storage.check_sudo(data.get('password') or None)
    if act == 'prompt_shrink':
        gib = int(data.get('gib') or 8)
        tandem.ui = {'tab': 4, 'sys': None, 'i': 3, 'page': 'library>storage', 'pane': 1, 'dev': ''}
        tandem.publish('state', tandem.snapshot())
        tandem.publish('open_shrink', {'gib': gib})
        return {'ok': True}
    if act == 'shrink_android':
        try: gib = int(data.get('gib') or 24)
        except (TypeError, ValueError): return {'error': 'Ungültige Größe.'}
        def _done_sh(r):
            tandem.publish('sysbackup', sysbackup_state())
            tandem.publish('toast', {'text': r.get('error') or r.get('text', '')})
        res = thor_storage.start_shrink_async(gib, sudo_password=data.get('password') or None, on_done=_done_sh)
        tandem.publish('sysbackup', sysbackup_state())
        return res
    if act == 'cleanup':
        which = str(data.get('which') or 'all')
        res = thor_storage.run_storage_cleanup(which, HOME, tandem.library.steam)
        tandem.publish('sysbackup', sysbackup_state())
        return res
    if act == 'compress_roms':
        def _done_cmp(r):
            if r.get('converted'):
                tandem.library.scan()
                tandem.publish('library')
            tandem.publish('sysbackup', sysbackup_state())
            tandem.publish('toast', {'text': r.get('error') or r.get('text', '')})
        res = thor_pro.start_compress_roms(tandem.library.roots, game_running=bool(tandem.run), on_done=_done_cmp)
        tandem.publish('sysbackup', sysbackup_state())
        return res
    return {'error': 'unbekannt'}


def handler(tandem):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args): pass

        def send(self, code, body, kind='application/json', cache='no-store'):
            body = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            for key, value in (('Content-Type', kind), ('Content-Length', str(len(body))), ('Cache-Control', cache)): self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ('/', '/index.html'):
                boot = json.dumps({'library': tandem.library.payload(tandem.saved), **tandem.snapshot(), 'battery': battery(), 'settings': settings(), 'config': public_config()}).replace('</', '<\\/')
                page = (HERE / 'index.html').read_text().replace('/*BOOT*/', f'window.BOOT={boot};', 1)
                return self.send(200, page.encode(), 'text/html; charset=utf-8')
            if path == '/api/library': return self.send(200, tandem.library.payload(tandem.saved))
            if re.fullmatch(r'/deck/\d+\.html', path):  # a game's own page for the bottom screen
                file = HERE / 'decks' / path[6:]
                return self.send(200, file.read_bytes(), 'text/html; charset=utf-8') if file.is_file() else self.send(404, {'error': 'kein Begleiter'})
            if path == '/api/state': return self.send(200, {**tandem.snapshot(), 'battery': battery(), 'wifi': wifi_link(), 'settings': settings(), 'muted': MUTED['on'], 'config': public_config(), 'pair': pair_info(), 'dock': telemetry.dock_state(), 'bt_audio': thor_airpods.MANAGER.cached_status()})
            if path.startswith('/media/'):
                file = tandem.library.media.get(path[7:])  # only files the scan indexed, never a path from the request
                if file and os.path.isfile(file):
                    ext = Path(file).suffix.lower()
                    if ext in VIDEOS:
                        size = os.path.getsize(file)
                        rng = re.match(r'bytes=(\d+)-(\d*)', self.headers.get('Range') or '')
                        start = int(rng[1]) if rng else 0
                        end = min(size - 1, int(rng[2]) if rng and rng[2] else size - 1)
                        if start >= size: return self.send(416, b'', VIDEOS[ext])
                        with open(file, 'rb') as vf:
                            vf.seek(start)
                            chunk = vf.read(end - start + 1)
                        self.send_response(206 if rng else 200)
                        for hk, hv in (('Content-Type', VIDEOS[ext]), ('Content-Length', str(len(chunk))),
                                       ('Accept-Ranges', 'bytes'), *((('Content-Range', f'bytes {start}-{end}/{size}'),) if rng else ())):
                            self.send_header(hk, hv)
                        self.end_headers(); self.wfile.write(chunk)
                        return
                    return self.send(200, Path(file).read_bytes(), IMAGES[ext], 'max-age=86400')
                return self.send(404, {'error': 'kein Bild'})
            if path == '/api/setup': return self.send(200, {**tandem.setup, **setup_info(tandem)})
            if path == '/api/system': return self.send(200, system_info(tandem.library.roots, 'scan' in self.path))
            if path == '/api/thor': return self.send(200, thor.state())
            if path == '/api/perf': return self.send(200, thor_perf.telemetry())
            if path == '/api/record': return self.send(200, record(tandem, 'status'))
            if path == '/api/framegen': return self.send(200, frame_gen())
            if path == '/api/controls': return self.send(200, controls_info())
            if path == '/api/bluetooth': return self.send(200, bluetooth.state())
            if path == '/api/saves': return self.send(200, saves.status())
            if path == '/api/sysbackup': return self.send(200, sysbackup_state())
            if path == '/api/updater': return self.send(200, updater_state(tandem))
            if path == '/api/stats': return self.send(200, tandem.stats_payload())
            if path == '/api/hud': return self.send(200, {'level': public_config()['hud_level']})
            if path == '/api/telemetry': return self.send(200, telemetry.snapshot())
            if path == '/api/switch_native':
                return self.send(200, companion.switch_native_info(tandem.library.games, tandem.library.roots, HOME))
            if path == '/api/bgm': return self.send(200, telemetry.bgm_status())
            if path == '/api/dualwin':
                sys_id = (tandem.run or {}).get('s', '')
                return self.send(200, companion.find_secondary_window(sys_id) or {'wid': 0})
            if path == '/api/savestates':
                run = tandem.run
                game = run and tandem.library.games.get(run['id'])
                st = companion.savestates_list(game, run)
                for s in st.get('slots', ()):
                    if s.get('thumb'): s['thumb'] = tandem.library._image(s['thumb'])
                return self.send(200, st)
            if path == '/api/notes':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                return self.send(200, companion.notes_get(gid))
            if path == '/api/cstate':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                ckey = (qs.get('key') or [(tandem.run or {}).get('companion') or (tandem.run or {}).get('id', '')])[0]
                return self.send(200, companion.cstate_get(ckey))
            if path == '/api/packs':
                return self.send(200, companion.gba_shelf_status(
                    list(tandem.library.games.values()), rom_identity,
                    saved_assign=tandem.saved.get('pack_assign'), cfg_dir=CONFIG.parent))
            if path == '/api/sketch':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                raw_png = companion.sketch_bytes(gid)
                return self.send(200, raw_png, 'image/png') if raw_png else self.send(404, {'error': 'keine Skizze'})
            if path == '/api/guides':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                return self.send(200, companion.guides_list(gid, tandem.library.games.get(gid)))
            if path == '/api/guide_file':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                name = (qs.get('name') or [''])[0]
                gf = companion.guide_file(gid, name, tandem.library.games.get(gid))
                if not gf: return self.send(404, {'error': 'nicht gefunden'})
                ext = gf.suffix.lower()
                if ext in IMAGES: return self.send(200, gf.read_bytes(), IMAGES[ext])
                return self.send(200, {'name': gf.name, 'text': gf.read_text(encoding='utf-8', errors='replace')[:250000]})
            if path == '/api/book_info':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                name = (qs.get('name') or [''])[0]
                gf = companion.guide_file(gid, name, tandem.library.games.get(gid))
                return self.send(200, companion.book_info(gf)) if gf else self.send(404, {'error': 'nicht gefunden'})
            if path == '/api/book_page':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                name = (qs.get('name') or [''])[0]
                try: page_n = int((qs.get('page') or ['0'])[0])
                except ValueError: page_n = 0
                gf = companion.guide_file(gid, name, tandem.library.games.get(gid))
                if not gf: return self.send(404, {'error': 'nicht gefunden'})
                raw_p, mime = companion.book_page_png(gf, page_n)
                return self.send(200, raw_p, mime, 'max-age=3600') if raw_p else self.send(404, {'error': 'kein Bild'})
            if path == '/api/artwork':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [''])[0]
                q = (qs.get('q') or [''])[0]
                gm = tandem.library.games.get(gid)
                return self.send(200, companion.artwork_candidates(gm, q)) if gm else self.send(404, {'error': 'nicht gefunden'})
            if path == '/api/achievements':
                run = tandem.run and tandem.library.games.get(tandem.run['id'])
                if not run:
                    return self.send(200, {'note': 'Es läuft kein Spiel.'})
                ach_res = dict(achievements(run))
                gid_r = tandem.run['id']
                ach_res['pinned'] = list((tandem.saved.get('ach_pins') or {}).get(gid_r) or [])
                for u_ach in thor_pro.TROPHIES.check_new_unlocks(gid_r, ach_res):
                    if not tandem.dry:
                        telemetry.play_sound('launch')
                    tandem.publish('trophy', {'title': u_ach.get('t', ''), 'desc': u_ach.get('d', ''), 'points': u_ach.get('p', 0)})
                return self.send(200, ach_res)
            if path == '/api/airplay':
                return self.send(200, thor_pro.AIRPLAY.status())
            if path == '/api/patch':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [''])[0]
                gm = tandem.library.games.get(gid)
                return self.send(200, {'items': thor_pro.discover_patches_for_game(gm, tandem.library.roots, HOME)})
            if path == '/api/voice':
                return self.send(200, thor_pro.VOICE.status())
            if path == '/api/propad':
                return self.send(200, thor_pro.PROPAD.status())
            if path == '/api/translate':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                return self.send(200, thor_translate.status(gid))
            if path == '/api/translate_preview':
                raw_png = thor_translate.preview_bytes()
                return self.send(200, raw_png, 'image/png') if raw_png else self.send(404, {'error': 'kein Bild'})
            if path == '/api/airpods':
                return self.send(200, thor_airpods.MANAGER.status())
            if path == '/api/replay':
                return self.send(200, {**thor_features.REPLAY.status(), 'enabled': public_config()['replay_buffer']})
            if path == '/api/macros':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                return self.send(200, thor_features.macros_get(gid, tandem.library.games.get(gid)))
            if path == '/api/cheats':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                return self.send(200, thor_features.cheats_get(gid, tandem.library.games.get(gid)))
            if path == '/api/netplay':
                return self.send(200, thor_features.NETPLAY)
            if path == '/api/events': return self.events()
            self.send(404, {'error': 'unbekannt'})

        def events(self):
            self.send_response(200)
            for key, value in (('Content-Type', 'text/event-stream'), ('Cache-Control', 'no-store'), ('Connection', 'close')): self.send_header(key, value)
            self.end_headers()
            q = queue.Queue(maxsize=50)
            tandem.clients.append(q)
            try:
                self.wfile.write(f'data: {json.dumps({"kind": "state", **tandem.snapshot()})}\n\n'.encode()); self.wfile.flush()
                while True:
                    try: message = q.get(timeout=20)
                    except queue.Empty: message = None
                    self.wfile.write(f'data: {message}\n\n'.encode() if message else b': ping\n\n'); self.wfile.flush()
            except OSError: pass
            finally: tandem.clients.remove(q)

        def do_POST(self):
            # Only the two kiosk windows may give orders: a page from another origin must not start programs.
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != self.headers.get('Host'): return self.send(403, {'error': 'fremde Herkunft'})
            path = urlparse(self.path).path
            if path == '/api/sketch':
                from urllib.parse import parse_qs
                qs = parse_qs(urlparse(self.path).query)
                gid = (qs.get('id') or [(tandem.run or {}).get('id', '')])[0]
                ln = min(int(self.headers.get('Content-Length') or 0), 4 << 20)
                return self.send(200, companion.sketch_save(gid, self.rfile.read(ln) if ln > 0 else b''))
            if path == '/api/upload':
                ln = int(self.headers.get('Content-Length') or 0)
                res = companion.handle_upload(self.rfile, ln, self.headers.get('X-File-Name'), self.headers.get('X-Kind', 'rom'),
                                              self.headers.get('X-System', 'auto'), self.headers.get('X-Game', ''),
                                              tandem.library.roots, CONFIG.parent, set(SYSTEMS))
                if res.get('ok'):
                    tandem.library.scan(); tandem.publish('library')
                return self.send(200, res)
            try: data = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
            except ValueError: return self.send(400, {'error': 'kein JSON'})
            if path == '/api/ui':
                system = data.get('sys')
                page = data.get('page')  # the settings: which page and whether the focus is on its list (0) or on the page (1)
                q = data.get('q').strip()[:60] if isinstance(data.get('q'), str) else ''
                valid_sys = isinstance(system, str) and (system in SYSTEMS or system == '_hidden' or (system.startswith('col:') and len(system) <= 44))
                tandem.ui = {'tab': int(data.get('tab', 0)), 'sys': system if valid_sys else None, 'i': int(data.get('i', 0)),
                             'page': page if isinstance(page, str) and re.fullmatch(r'[a-z>]{0,30}', page) else '', 'pane': 1 if data.get('pane') == 1 else 0,
                             'dev': data['dev'] if isinstance(data.get('dev'), str) and re.fullmatch(r'[0-9A-F]{2}(:[0-9A-F]{2}){5}', data['dev']) else '',
                             **({'q': q} if q else {})}  # the Bluetooth device a settings page shows; q = library search
                tandem.publish('state', {**tandem.snapshot(), 'from': data.get('from')})  # the sender skips its own echo
                return self.send(200, {'ok': True})
            if path == '/api/uikey':
                a = str(data.get('a') or '')
                if a == 'quick':
                    tandem.publish('quick', {})
                elif a in ('ok', 'back', 'left', 'right', 'up', 'down', 'prev', 'next', 'fav', 'close', 'menu', 'search', 'home'):
                    tandem.publish('key', {'a': a})
                return self.send(200, {'ok': True})
            if path == '/api/launch':
                result = tandem.launch(str(data.get('id', '')))
                if 'error' in result: tandem.publish('toast', {'text': result['error']})
                elif not result['tracked']: tandem.publish('toast', {'text': result.get('text') or 'Gestartet – zurück geht es über die Home-Taste.'})
                return self.send(200, result)
            if path == '/api/confirm':  # pass a question on to the other screen's page
                act = data.get('action')
                tandem.publish('confirm', {'open': bool(data.get('open')), 'then': data.get('then'), 'action': act if act in (*ACTIONS, 'sleep') else None, 'from': data.get('from')})
                return self.send(200, {'ok': True})
            if path == '/api/prompt':  # bottom screen's text prompt is open/closed: keep controller navigation off the library
                tandem.prompt_open = bool(data.get('open'))
                tandem.publish('prompt', {'open': tandem.prompt_open, 'from': data.get('from')})
                return self.send(200, {'ok': True})
            if path == '/api/swkbd':  # native Switch game software keyboard: blocks until bottom screen confirms or cancels
                return self.send(200, tandem.ask_swkbd(data))
            if path == '/api/swkbd_done':
                rid = int(data['id']) if isinstance(data.get('id'), (int, float)) else None
                return self.send(200, tandem.finish_swkbd(rid, bool(data.get('ok')), str(data.get('text') or '')))
            if path == '/api/ytlogin':
                act = data.get('a') if data.get('a') in ('qr', 'qr_new', 'start', 'open', 'done', 'cancel', 'logout') else 'done'
                return self.send(200, yt_login(tandem, act))
            if path == '/api/quit': return self.send(200, tandem.quit())
            if path == '/api/pause': return self.send(200, tandem.pause())
            if path == '/api/record': return self.send(200, record(tandem, data.get('action')))
            if path == '/api/shot': return self.send(200, screenshot())
            if path == '/api/freeze': return self.send(200, tandem.freeze_toggle(data.get('on')))
            if path == '/api/airpods':
                act = str(data.get('action') or 'status')
                if act == 'toggle':
                    addr = str(data.get('addr') or '')
                    def _do_ap():
                        r = thor_airpods.MANAGER.quick_toggle_connect(addr)
                        tandem.publish('toast', {'text': r.get('error') or r.get('text', '')})
                    threading.Thread(target=_do_ap, daemon=True).start()
                    return self.send(200, {'ok': True})
                if act == 'noise':
                    return self.send(200, thor_airpods.MANAGER.set_noise_mode(str(data.get('mode') or 'off')))
                if act == 'conv':
                    return self.send(200, thor_airpods.MANAGER.set_conv_awareness(bool(data.get('on'))))
                if act == 'ear':
                    save_config({'airpods_ear_pause': bool(data.get('on'))})
                    tandem.publish('config', {'config': public_config()})
                    return self.send(200, thor_airpods.MANAGER.status())
                if act == 'low_latency':
                    save_config({'bt_low_latency': bool(data.get('on'))})
                    tandem.publish('config', {'config': public_config()})
                    return self.send(200, thor_airpods.MANAGER.status())
                return self.send(200, thor_airpods.MANAGER.status())
            if path == '/api/replay':
                act = str(data.get('action') or 'save')
                if act == 'toggle':
                    want = not public_config()['replay_buffer']
                    save_config({'replay_buffer': want})
                    if want and tandem.run and not tandem.run.get('paused') and tandem.run.get('s') not in ('app', 'term') and not tandem.dry:
                        dpys = _x11_displays()
                        thor_features.REPLAY.start(dpys[0] if dpys else ':0')
                    tandem.publish('config', {'config': public_config()})
                    return self.send(200, {**thor_features.REPLAY.status(), 'enabled': want})
                pinfo = pair_info()
                lan_base = pinfo.get('ip_url') or pinfo.get('url') or ''
                res = thor_features.REPLAY.save_clip((tandem.run or {}).get('t', ''), lan_base)
                return self.send(200, res)
            if path == '/api/macros':
                gid = str(data.get('id') or (tandem.run or {}).get('id', ''))
                if data.get('action') == 'fire':
                    return self.send(200, thor_features.fire_macro(
                        data.get('spec', ''), int(data.get('idx', -1)), bool(data.get('turbo')),
                        send_key_fn=lambda c, m: (not tandem.dry and x_press_code(c, m)) or KEYBOARD.press(c, m),
                        ra_cmd_fn=retroarch,
                    ))
                return self.send(200, thor_features.macros_save(gid, data, tandem.library.games.get(gid)))
            if path == '/api/cheats':
                gid = str(data.get('id') or (tandem.run or {}).get('id', ''))
                gm = tandem.library.games.get(gid)
                if data.get('action') == 'fetch':
                    return self.send(200, thor_features.cheats_fetch_online(gid, gm))
                return self.send(200, thor_features.cheat_toggle(
                    gid, data.get('idx'), str(data.get('desc') or ''), str(data.get('code') or ''), gm))
            if path == '/api/netplay':
                return self.send(200, thor_features.set_netplay(str(data.get('mode') or 'off'), str(data.get('host_ip') or '')))
            if path == '/api/airplay':
                act = str(data.get('action') or 'toggle')
                scr = str(data.get('screen') or 'bottom')
                if act == 'stop' or (act == 'toggle' and thor_pro.AIRPLAY.running()):
                    return self.send(200, thor_pro.AIRPLAY.stop())
                return self.send(200, thor_pro.AIRPLAY.start(scr, game_running=bool(tandem.run)))
            if path == '/api/patch':
                gid = str(data.get('id') or '')
                gm = tandem.library.games.get(gid)
                res = thor_pro.apply_rom_patch(gm, str(data.get('patch') or ''), str(data.get('tag') or ''))
                if res.get('ok'):
                    tandem.library.scan()
                    tandem.publish('library')
                return self.send(200, res)
            if path == '/api/ach_pin':
                gid = str(data.get('id') or (tandem.run or {}).get('id', ''))
                title_p = str(data.get('title') or '').strip()
                if not gid or not title_p:
                    return self.send(400, {'error': 'Ungültige Anfrage.'})
                with tandem.lock:
                    pins = tandem.saved.setdefault('ach_pins', {}).setdefault(gid, [])
                    if title_p in pins:
                        pins.remove(title_p)
                    else:
                        pins.insert(0, title_p)
                        del pins[3:]
                    tandem.save()
                return self.send(200, {'ok': True, 'pinned': list(pins)})
            if path == '/api/voice':
                act = str(data.get('action') or 'status')
                gid = str(data.get('id') or (tandem.run or {}).get('id', ''))
                if act == 'start':
                    return self.send(200, thor_pro.VOICE.start_record())
                if act == 'stop':
                    res = thor_pro.VOICE.stop_and_transcribe(public_config()['lang'])
                    if not res.get('ok'):
                        return self.send(200, res)
                    txt = res['text']
                    mode = str(data.get('mode') or 'note')
                    if mode == 'note':
                        cur_n = companion.notes_get(gid)
                        prev_t = (cur_n.get('text') or '').rstrip()
                        stamp = time.strftime('%H:%M')
                        merged = (prev_t + '\n' if prev_t else '') + f'[🎙️ {stamp}] {txt}'
                        saved_n = companion.notes_save(gid, {'text': merged})
                        return self.send(200, {'ok': True, 'text': txt, 'notes': saved_n, 'toast': f'🎙️ Notiert: {txt[:60]}'})
                    gm = tandem.library.games.get(gid)
                    hit = thor_pro.search_local_guides(gid, txt, gm)
                    if hit:
                        return self.send(200, {'ok': True, 'text': txt, 'hit': hit, 'toast': f'🎙️ Gefunden in {hit["title"]}'})
                    wres = companion.guide_fetch_wiki(gid, txt, public_config()['lang'])
                    return self.send(200, {'ok': True, 'text': txt, 'wiki': wres,
                                           'toast': f'🎙️ Wiki geladen: {txt[:40]}' if wres.get('ok') else f'🎙️ Gesucht: {txt[:40]}'})
                return self.send(200, thor_pro.VOICE.status())
            if path == '/api/propad':
                act = str(data.get('action') or 'status')
                if act == 'target':
                    return self.send(200, thor_pro.PROPAD.set_target(data.get('ip', '')))
                if act == 'key':
                    thor_pro.PROPAD.send_pkt({'k': 'key', 'ch': str(data.get('ch') or '')})
                    return self.send(200, thor_pro.PROPAD.status())
                if act == 'mouse':
                    thor_pro.PROPAD.send_pkt({'k': 'mouse', 'dx': data.get('dx', 0), 'dy': data.get('dy', 0), 'click': data.get('click', '')})
                    return self.send(200, thor_pro.PROPAD.status())
                return self.send(200, thor_pro.PROPAD.status())
            if path == '/api/framegen': return self.send(200, frame_gen(bool(data.get('on'))))
            if path == '/api/hud':
                lvl = data.get('level', 0)
                res = save_config({'hud_level': lvl if lvl in (0, 1, 2, 3) else 0})
                tandem.publish('config', {'config': public_config()})
                return self.send(200, {'ok': True, 'level': res['hud_level']})
            if path == '/api/mute':
                mode = data.get('on') if isinstance(data.get('on'), bool) else 'toggle'
                result = mute(mode)
                tandem.publish('mute', {'muted': result['muted']})
                return self.send(200, result)
            if path == '/api/gameopt': return self.send(200, tandem.gameopt(data))
            if path == '/api/resume': return self.send(200, tandem.resume())
            if path == '/api/set':
                result = change(str(data.get('key', '')), data.get('value', 0) if isinstance(data.get('value', 0), (int, float)) else 0)
                if 'error' not in result:
                    if str(data.get('key', '')) == 'vol' and MUTED['on']:
                        MUTED['on'] = False
                        tandem.publish('mute', {'muted': False})
                    tandem.publish('settings', {'settings': result, 'from': data.get('from')})
                return self.send(200, result)
            if path == '/api/bluetooth': return self.send(200, bluetooth_post(tandem, data))
            if path == '/api/wifi': return self.send(200, wifi_connect(str(data.get('ssid', '')), str(data.get('password', ''))))
            if path == '/api/update':
                def work(key=str(data.get('id', ''))):
                    tandem.publish('toast', {'text': update_extra(key, tandem.library.roots)})
                    tandem.publish('library')
                threading.Thread(target=work, daemon=True).start()
                return self.send(200, {'ok': True})
            if path == '/api/quick':  # the Thor key's menu, for scripted takes (the daemon reads only the Thor's own keys)
                tandem.publish('quick', {}); return self.send(200, {'ok': True})
            if path == '/api/key':
                is_wine = bool((tandem.run or {}).get('keys') and not (tandem.run or {}).get('login'))
                if isinstance(data.get('seq'), str) and data['seq']:
                    if data['seq'] == '@' and is_wine:
                        return self.send(200, paste('@'))
                    if not tandem.dry and x_type_seq(data['seq']):
                        if data.get('enter'):
                            x_press_code(28) or KEYBOARD.press(28, [])
                        return self.send(200, {'ok': True})
                    layout = (tandem.run or {}).get('layout') or region_layout()
                    res_k = KEYBOARD.type_text(data['seq'], layout)
                    if data.get('enter') and not tandem.dry:
                        x_press_code(28) or KEYBOARD.press(28, [])
                    return self.send(200, res_k)
                code = data.get('code')
                mods, text = [m for m in data.get('mods', []) if isinstance(m, str)], data.get('text')
                if 'altgr' in mods and isinstance(text, str) and len(text) == 1 and is_wine:
                    return self.send(200, paste(text))
                if not tandem.dry and not ({'ctrl', 'alt'} & set(mods)) and isinstance(text, str) and len(text) == 1 and text != ' ' and x_type_char(text):
                    return self.send(200, {'ok': True})
                if not tandem.dry and isinstance(code, int) and x_press_code(code, mods):
                    return self.send(200, {'ok': True})
                return self.send(200, KEYBOARD.press(code if isinstance(code, int) else 0, mods))
            if path == '/api/ai_window':
                return self.send(200, ai_window_act(tandem, str(data.get('action') or 'toggle')))
            if path == '/api/ai_auth':
                if data.get('url'):
                    return self.send(200, ai_auth_register(tandem, data.get('url'), open_ui=True))
                act = str(data.get('action') or '')
                if act == 'open':
                    return self.send(200, ai_auth_register(tandem, '', open_ui=True))
                if act == 'close':
                    AI_AUTH['open'] = False
                    st = ai_auth_state()
                    tandem.publish('ai_auth', st)
                    return self.send(200, {'ok': True, **st})
                if act == 'browser':
                    return self.send(200, ai_auth_open_browser(tandem))
                if data.get('code'):
                    return self.send(200, ai_auth_submit(tandem, data.get('code')))
                return self.send(200, ai_auth_state())
            if path == '/api/layout':  # switch the on-screen keyboard's layout while the terminal is open
                result = save_config({'kb_layout': data.get('layout')})
                layout = region_layout()
                run_quiet(['setxkbmap', layout])
                if tandem.run and (tandem.run.get('s') == 'term' or tandem.run.get('keys')): tandem.run['layout'] = layout
                tandem.publish()
                return self.send(200, {**result, 'layout': layout})
            if path == '/api/config':
                result = save_config(data)
                tandem.publish('config', {'config': public_config()})  # both screens follow (theme)
                return self.send(200, result)
            if path == '/api/thor': return self.send(200, thor_change(tandem, data))
            if path == '/api/controls': return self.send(200, controls_apply())
            if path == '/api/saves': return self.send(200, trigger_saves_backup(tandem, quiet=False))
            if path == '/api/saves_restore':
                res = saves.restore(data.get('file'), data.get('only'))
                if res.get('ok'): tandem.publish('saves', {'saves': saves.status()})
                return self.send(200, res)
            if path == '/api/sysbackup':
                return self.send(200, handle_sysbackup(tandem, data))
            if path == '/api/collection': return self.send(200, tandem.collection_act(data))
            if path == '/api/savestates':
                return self.send(200, retroarch_slot_act(tandem, data.get('slot', 0), str(data.get('mode', 'load'))))
            if path == '/api/notes':
                gid = str(data.get('id') or (tandem.run or {}).get('id', ''))
                return self.send(200, companion.notes_save(gid, data))
            if path == '/api/cstate':
                ckey = str(data.get('key') or (tandem.run or {}).get('companion') or (tandem.run or {}).get('id', ''))
                return self.send(200, companion.cstate_save(ckey, data))
            if path == '/api/npad':
                return self.send(200, companion.send_native_pad(data.get('seq', '')))
            if path == '/api/packs':
                act = str(data.get('action') or 'sync')
                if act == 'sync':
                    res = companion.sync_owned_gba_packs(list(tandem.library.games.values()), rom_identity,
                                                         cfg_dir=CONFIG.parent, force_catalog=True)
                    if res.get('installed') or res.get('updated'):
                        tandem.publish('library')
                    return self.send(200, res)
                if act == 'install':
                    pid = str(data.get('id') or '').strip().lower()
                    cat = companion.fetch_gbaduo_catalog(force=False)
                    hit = next((c for c in cat if c['id'] == pid), None)
                    if not hit:
                        return self.send(404, {'error': 'nicht gefunden'})
                    res = companion.download_catalog_pack(hit, cfg_dir=CONFIG.parent)
                    if res.get('ok'):
                        tandem.publish('library')
                    return self.send(200, res)
                if act == 'assign':
                    gid = str(data.get('gid') or (tandem.run or {}).get('id') or '')
                    val = str(data.get('pack') or '').strip()
                    if not gid:
                        return self.send(400, {'error': 'ungültige ID'})
                    pa = tandem.saved.setdefault('pack_assign', {})
                    if not val or val == 'auto':
                        pa.pop(gid, None)
                    else:
                        pa[gid] = val
                    tandem.save()
                    if tandem.run and tandem.run.get('id') == gid:
                        gm = tandem.library.games.get(gid) or {}
                        pk, pk_other, pk_cands = find_pack_info(gm, assigned=pa.get(gid))
                        tandem.run.update(pack=pk, pack_other_region=pk_other, pack_candidates=pk_cands,
                                          pack_mode='art' if val == '__art__' else 'pack')
                        tandem.publish('run', {'run': tandem.run})
                    return self.send(200, {'ok': True, 'gid': gid, 'assigned': pa.get(gid)})
                if act == 'remove':
                    pid = str(data.get('id') or '').strip().lower()
                    if not companion.PACK_ID_RE.fullmatch(pid):
                        return self.send(400, {'error': 'ungültige ID'})
                    shutil.rmtree(companion.packs_dir(CONFIG.parent) / pid, ignore_errors=True)
                    tandem.publish('library')
                    return self.send(200, {'ok': True, 'removed': pid})
                return self.send(400, {'error': 'unbekannt'})
            if path == '/api/guides':
                gid = str(data.get('id') or (tandem.run or {}).get('id', ''))
                return self.send(200, companion.guide_fetch_wiki(gid, data.get('q', ''), public_config()['lang']))
            if path == '/api/artwork':
                gid = str(data.get('id') or '')
                act = str(data.get('action') or 'apply')
                res = (companion.reset_custom_artwork(gid) if act == 'reset'
                       else companion.apply_custom_artwork(gid, str(data.get('url') or ''), str(data.get('slot') or 'cover')))
                if res.get('ok'):
                    tandem.library.scan()
                    tandem.publish('library')
                return self.send(200, res)
            if path == '/api/translate':
                gid = str(data.get('id') or (tandem.run or {}).get('id', ''))
                act = str(data.get('action') or 'now')
                if act == 'now':
                    return self.send(200, thor_translate.translate_now(gid))
                if act == 'options':
                    return self.send(200, thor_translate.set_options(
                        tandem, auto=data.get('auto'), mode=data.get('mode'),
                        src=data.get('src'), clear_history=bool(data.get('clear')),
                    ))
                if act == 'crop':
                    return self.send(200, thor_translate.set_game_crop(gid, str(data.get('region') or 'full'), data.get('box')))
                if act == 'word':
                    return self.send(200, thor_translate.lookup_word(data.get('word', ''), gid))
                if act == 'speak':
                    thor_translate.speak(data.get('text', ''), 'de')
                    return self.send(200, thor_translate.status(gid))
                if act == 'install':
                    thor_translate.install_engine()
                    return self.send(200, thor_translate.status(gid))
                if act == 'model':
                    pid = str(data.get('id') or '')
                    threading.Thread(target=thor_translate.download_model_pair, args=(pid,), daemon=True).start()
                    return self.send(200, thor_translate.status(gid))
                return self.send(200, thor_translate.status(gid))
            if path == '/api/bgm':
                if data.get('action') == 'stream_vol':
                    return self.send(200, telemetry.set_stream_volume(data.get('id', 0), data.get('vol', 80)))
                return self.send(200, telemetry.bgm_control(str(data.get('action', 'toggle')), str(data.get('path', '')), data.get('vol')))
            if path == '/api/dualtouch':
                return self.send(200, companion.send_window_touch(data.get('wid', 0), data.get('x', 0.5), data.get('y', 0.5), data.get('phase', 'down')))
            if path == '/api/mouse':
                return self.send(200, companion.MOUSE.send(data.get('dx', 0), data.get('dy', 0), data.get('wheel', 0), str(data.get('btn', '')), str(data.get('action', 'click'))))
            if path == '/api/wol':
                mac = str(data.get('mac') or load_config().get('wol_mac') or '')
                return self.send(200, telemetry.wake_on_lan(mac))
            if path == '/api/locate':
                res = telemetry.locator_ping()
                tandem.publish('toast', {'text': res['text']})
                return self.send(200, res)
            if path == '/api/saver':
                tandem.publish('saver', {'open': bool(data.get('open', True))})
                return self.send(200, {'ok': True, 'open': bool(data.get('open', True))})
            if path == '/api/sound':
                if public_config().get('ui_sounds') == 'subtle':
                    telemetry.play_sound(str(data.get('kind', 'tick')))
                return self.send(200, {'ok': True})
            if path == '/api/switch_native':
                gm = tandem.library.games.get(str(data.get('id', '')))
                def _on_conv(ok, msg):
                    if ok:
                        tandem.library.scan()
                        tandem.publish('library')
                    tandem.publish('toast', {'text': msg})
                res = companion.switch_native_convert(gm, tandem.library.roots, HOME, _on_conv)
                if res.get('text'):
                    tandem.publish('toast', {'text': res['text']})
                return self.send(200, res)
            if path == '/api/selfupdate': return self.send(200, self_update(bool(data.get('apply'))))
            if path == '/api/updater': return self.send(200, handle_updater(tandem, data))
            if path == '/api/wide': return self.send(200, tandem.wide(str(data.get('on', ''))))
            if path == '/api/retroarch': return self.send(200, retroarch(str(data.get('name', ''))))
            if path == '/api/action': return self.send(200, tandem.act(str(data.get('name', ''))))
            if path == '/api/setup': return self.send(200, setup_command(tandem, data))
            if path == '/api/fav': return self.send(200, tandem.favourite(str(data.get('id', ''))))
            if path == '/api/rescan':
                tandem.library.scan()
                new = scrape(list(tandem.library.games.values()))  # only games still without a cover are asked for
                if new: tandem.library.scan()
                tandem.publish('library')
                return self.send(200, {'games': len(tandem.library.games), 'covers': new})
            self.send(404, {'error': 'unbekannt'})
    return Handler


PAIR = {'pin': '', 'tries': 0, 'port': 8378, 'tls': False}
DEVICES = CONFIG.parent / 'devices.json'  # browsers that may use the settings page: the SHA-256 of each one's token, never the token
TLS_FILES = (CONFIG.parent / 'tls.crt', CONFIG.parent / 'tls.key')  # both there: the settings page is served over HTTPS
# The settings page for phone and computer lives in remote.html: shared head, then the PIN view, then the page itself.
_REMOTE = (HERE / 'remote.html').read_text().replace('__EN__', (HERE / 'ui/en.json').read_text()).split('<!--SPLIT-->')
PAIR_PAGE, REMOTE_PAGE = _REMOTE[0] + _REMOTE[1], _REMOTE[0] + _REMOTE[2]


def new_pin():
    import secrets
    PAIR.update(pin=f'{secrets.randbelow(10**6):06d}', tries=0)


def lan_address():
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('10.255.255.255', 1))  # no packet is sent; this only picks the outgoing interface
            return sock.getsockname()[0]
    except OSError: return None


def pair_info():
    """What the screens show for the settings page: the PIN and its addresses: the owner's own one first if there is
    one (own), then by name (mDNS, url) and by number (ip_url)."""
    import socket
    scheme, port, ip = 'https' if PAIR['tls'] else 'http', PAIR['port'], lan_address()
    name = socket.gethostname().split('.')[0]
    return {'pin': PAIR['pin'], 'host': ip, 'own': load_config().get('remote_url') or None, 'url': f'{scheme}://{name}.local:{port}' if name and ip else None, 'ip_url': f'{scheme}://{ip}:{port}' if ip else None}


def devices():
    try: return [h for h in json.loads(DEVICES.read_text()) if isinstance(h, str)]
    except (OSError, ValueError): return []


def save_devices(hashes):
    """Oldest first, at most ten; the file is readable by the owner only."""
    DEVICES.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEVICES.with_suffix('.tmp')
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as file: json.dump(hashes[-10:], file)
    os.chmod(tmp, 0o600)
    os.replace(tmp, DEVICES)


def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()


def pair_handler(tandem):
    """A second, small server reachable from the home network: the settings page for phone and computer. The PIN shown
    on the Thor opens it once; after that the browser holds a cookie for a year, and the service remembers that browser
    across restarts (see DEVICES)."""
    class Pair(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def reply(self, code, body, kind='text/html; charset=utf-8', extra=()):
            body = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
            self.send_response(code)
            for key, value in (('Content-Type', kind), ('Content-Length', str(len(body))), ('Cache-Control', 'no-store'), *extra): self.send_header(key, value)
            self.end_headers(); self.wfile.write(body)

        def allowed(self):
            cookie = re.search(r'(?:^|;\s*)tandem=([0-9a-f]{32})', self.headers.get('Cookie') or '')
            return bool(cookie) and token_hash(cookie[1]) in devices()

        def cookie(self, token, age):
            secure = '; Secure' if PAIR['tls'] or self.headers.get('X-Forwarded-Proto') == 'https' else ''
            return ('Set-Cookie', f'tandem={token}; Max-Age={age}; HttpOnly; SameSite=Strict; Path=/{secure}')

        def do_GET(self):
            import hmac
            path = urlparse(self.path).path
            if path == '/thor-pad.py':
                return self.reply(200, thor_pro.RECEIVER_PY, 'text/x-python; charset=utf-8')
            if path.startswith('/clip/') and path.endswith('.mp4'):
                tok = path[len('/clip/'):-4]
                clip_p = thor_features.REPLAY.resolve_share_token(tok)
                if clip_p:
                    return self.reply(200, clip_p.read_bytes(), 'video/mp4',
                                      extra=(('Content-Disposition', f'attachment; filename="{clip_p.name}"'),))
                return self.reply(404, {'error': 'Clip abgelaufen'}, 'application/json')
            if path.startswith('/ai-login/'):
                tok = path.split('/ai-login/', 1)[1].strip('/')
                if tok and AI_AUTH['token'] and (time.time() - AI_AUTH['ts'] <= AI_AUTH_TTL) and hmac.compare_digest(tok, AI_AUTH['token']):
                    return self.reply(200, ai_login_page(tok))
                return self.reply(403, ai_login_page('', 'Dieser QR-Link ist abgelaufen. Bitte am Thor erneut QR-Login öffnen.', ok=False))
            if path == '/api/all':
                if not self.allowed(): return self.reply(401, {'error': 'nicht angemeldet'}, 'application/json')
                run = tandem.run and tandem.library.games.get(tandem.run['id'])
                sys_opts = [{'id': s, 'name': SYSTEMS[s][0]} for s in sorted(SYSTEMS, key=lambda k: SYSTEMS[k][0].lower()) if s != 'port']
                game_opts = [{'id': g['id'], 't': f"{g['t']} ({SYSTEMS.get(g['s'], ('Steam',))[0]})"} for g in sorted(tandem.library.games.values(), key=lambda x: x['t'].lower())[:500]]
                return self.reply(200, {'settings': settings(), 'config': public_config(), 'layout': region_layout(), 'battery': battery(),
                                        'battery_detail': telemetry.battery_detail(), 'charger': telemetry.charger_detail(),
                                        'thor': thor.state(), 'controls': controls_info(),
                                        'system': system_info(tandem.library.roots), 'games': len(tandem.library.games), 'saves': saves.status(),
                                        'sysbackup': sysbackup_state(), 'updater': updater_state(tandem),
                                        'stats': tandem.stats_payload(), 'systems_list': sys_opts, 'games_list': game_opts, 'dock': telemetry.dock_state(),
                                        'switch_native': companion.switch_native_info(tandem.library.games, tandem.library.roots, HOME),
                                        'run': (tandem.run or {}).get('t') or (run or {}).get('t') or (tandem.run or {}).get('id')}, 'application/json')
            self.reply(200, (REMOTE_PAGE if self.allowed() else PAIR_PAGE.replace('__MSG__', '')).replace('__LANG__', public_config()['lang']))

        def do_POST(self):
            import hmac, secrets, urllib.parse
            path = urlparse(self.path).path
            if path == '/api/upload':
                if not self.allowed(): return self.reply(401, {'error': 'nicht angemeldet'}, 'application/json')
                origin = self.headers.get('Origin')
                if origin and urlparse(origin).netloc != self.headers.get('Host'): return self.reply(403, {'error': 'fremde Herkunft'}, 'application/json')
                ln = int(self.headers.get('Content-Length') or 0)
                res = companion.handle_upload(self.rfile, ln, self.headers.get('X-File-Name'), self.headers.get('X-Kind', 'rom'),
                                              self.headers.get('X-System', 'auto'), self.headers.get('X-Game', ''),
                                              tandem.library.roots, CONFIG.parent, set(SYSTEMS))
                if res.get('ok'):
                    tandem.library.scan(); tandem.publish('library')
                    tandem.publish('toast', {'text': res['text']})
                return self.reply(200, res, 'application/json')
            raw = self.rfile.read(min(int(self.headers.get('Content-Length') or 0), 262144))
            if path.startswith('/ai-login/'):
                tok = path.split('/ai-login/', 1)[1].strip('/')
                if not (tok and AI_AUTH['token'] and (time.time() - AI_AUTH['ts'] <= AI_AUTH_TTL) and hmac.compare_digest(tok, AI_AUTH['token'])):
                    return self.reply(403, ai_login_page('', 'Dieser QR-Link ist abgelaufen. Bitte am Thor erneut QR-Login öffnen.', ok=False))
                form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(errors='replace')).items()}
                res = ai_auth_submit(tandem, form.get('code', ''))
                if res.get('ok'):
                    return self.reply(200, ai_login_page(tok, '✓ ' + (res.get('text') or 'An Thor gesendet – du kannst dieses Fenster schließen.'), ok=True))
                return self.reply(400, ai_login_page(tok, res.get('error') or 'Senden fehlgeschlagen.', ok=False))
            if not path.startswith('/api/'):  # the PIN form
                form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(errors='replace')).items()}
                if not hmac.compare_digest(form.get('pin', ''), PAIR['pin']):
                    PAIR['tries'] += 1
                    if PAIR['tries'] >= 5: new_pin(); tandem.publish()  # a fresh PIN after five wrong ones
                    return self.reply(200, PAIR_PAGE.replace('__MSG__', '<p><b>Die PIN stimmt nicht.</b></p>').replace('__LANG__', public_config()['lang']))
                token = secrets.token_hex(16)
                save_devices(devices() + [token_hash(token)]); new_pin(); tandem.publish()  # one PIN, one use
                return self.reply(303, b'', extra=(('Location', '/'), self.cookie(token, 365 * 86400)))
            if not self.allowed(): return self.reply(401, {'error': 'nicht angemeldet'}, 'application/json')
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != self.headers.get('Host'): return self.reply(403, {'error': 'fremde Herkunft'}, 'application/json')
            try: data = json.loads(raw or b'{}')
            except ValueError: return self.reply(400, {'error': 'kein JSON'}, 'application/json')
            what = path[5:]
            if what == 'config':
                # Secrets and session cookies only over an encrypted way (TLS or the owner's https proxy); plain http in Wi-Fi could be read along
                if (data.get('bnet_password') or data.get('yt_cookies')) and not (PAIR['tls'] or self.headers.get('X-Forwarded-Proto') == 'https'):
                    return self.reply(403, {'error': 'Zugangsdaten und Cookies nur über die https-Adresse übertragen.'}, 'application/json')
                result = save_config(data); tandem.publish('config', {'config': public_config()})
            elif what == 'ytlogin':
                act = data.get('a') if data.get('a') in ('qr', 'qr_new', 'open', 'done', 'cancel', 'logout') else 'qr'
                result = yt_login(tandem, act)
            elif what == 'layout': result = save_config({'kb_layout': data.get('layout')})
            elif what == 'set':
                result = change(str(data.get('key', '')), data.get('value', 0) if isinstance(data.get('value', 0), (int, float)) else 0)
                if 'error' not in result:
                    if str(data.get('key', '')) == 'vol' and MUTED['on']:
                        MUTED['on'] = False
                        tandem.publish('mute', {'muted': False})
                    tandem.publish('settings', {'settings': result})
            elif what == 'wifi': result = wifi_connect(str(data.get('ssid', '')), str(data.get('password', '')))
            elif what == 'rescan':
                tandem.library.scan()
                if scrape(list(tandem.library.games.values())): tandem.library.scan()
                tandem.sync_gba_packs_bg(force=False)
                tandem.publish('library'); result = {'text': f'{len(tandem.library.games)} Spiele gefunden.'}
            elif what == 'update':
                result = {'text': update_extra(data.get('id') if data.get('id') in EXTRAS else 'eden', tandem.library.roots)}; tandem.publish('library')
            elif what == 'quit': result = tandem.quit()
            elif what == 'thor': result = thor_change(tandem, data)
            elif what == 'controls': result = controls_apply()
            elif what == 'saves':
                result = saves.backup(load_config().get('save_target', saves.DEFAULT_TARGET))
                tandem.publish('saves', {'saves': saves.status()})
            elif what == 'saves_restore':
                result = saves.restore(data.get('file'), data.get('only'))
                if result.get('ok'): tandem.publish('saves', {'saves': saves.status()})
            elif what == 'sysbackup':
                if data.get('password') and not (PAIR['tls'] or self.headers.get('X-Forwarded-Proto') == 'https'):
                    return self.reply(403, {'error': 'Zugangsdaten und Cookies nur über die https-Adresse übertragen.'}, 'application/json')
                result = handle_sysbackup(tandem, data)
            elif what == 'updater':
                result = handle_updater(tandem, data)
            elif what == 'wol':
                mac = str(data.get('mac') or load_config().get('wol_mac') or '')
                result = telemetry.wake_on_lan(mac)
            elif what == 'locate':
                result = telemetry.locator_ping()
                tandem.publish('toast', {'text': result['text']})
            elif what == 'saver':
                tandem.publish('saver', {'open': bool(data.get('open', True))})
                result = {'ok': True, 'text': 'Bildschirmschoner gestartet.'}
            elif what == 'switch_native':
                gm = tandem.library.games.get(str(data.get('id', '')))
                def _on_conv(ok, msg):
                    if ok:
                        tandem.library.scan()
                        tandem.publish('library')
                    tandem.publish('toast', {'text': msg})
                result = companion.switch_native_convert(gm, tandem.library.roots, HOME, _on_conv)
                if result.get('text'):
                    tandem.publish('toast', {'text': result['text']})
            elif what == 'selfupdate': result = self_update(bool(data.get('apply')))
            elif what in ('logout', 'logout-all'):
                mine = token_hash(re.search(r'tandem=([0-9a-f]{32})', self.headers.get('Cookie') or '')[1])
                save_devices([h for h in devices() if h != mine] if what == 'logout' else [])
                return self.reply(200, {'text': 'Abgemeldet.'}, 'application/json', (self.cookie('', 0),))
            elif what == 'action' and data.get('name') in ('suspend', 'sleep', 'wake', 'reboot', 'poweroff'): result = tandem.act(data['name'])
            else: return self.reply(404, {'error': 'unbekannt'}, 'application/json')
            self.reply(200, result, 'application/json')
    return Pair


# Controller buttons as they arrive (evdev codes of the emulated "Microsoft X-Box 360 pad"; the Thor prints them
# Nintendo-style): A ok (right, BTN_EAST), B back (bottom, BTN_SOUTH), X close (top: 308, the Thor's InputPlumber map swaps
# top and left like a real Xbox pad, see controls.py), Y favourite (left: 307), LB/RB previous/next tab, Select (314) search.
PAD_KEYS = {305: 'ok', 304: 'back', 308: 'close', 307: 'fav', 310: 'prev', 311: 'next', 314: 'search', 315: 'menu'}


class PowerKey:
    """Short press on KEY_POWER (116) toggles standby; holding >= 0.8 s opens the power menu; closing the lid (EV_SW=5,
    SW_LID=0) enters standby and opening wakes doze. A short guard window after sleep/wake prevents wake-press bounce."""
    HOLD = 0.8

    def __init__(self, lid_closed=False):
        self.down_at, self.long_fired, self.lid_closed, self.guard_until = 0.0, False, bool(lid_closed), 0.0

    def event(self, kind, code, value, now, dozing, lid_sleep=True):
        if kind == 5 and code == 0:  # SW_LID: 1 = closed, 0 = open
            if value == 1:
                self.lid_closed, self.down_at, self.long_fired = True, 0.0, False
                if lid_sleep and not dozing:
                    self.guard_until = now + 0.6
                    return 'standby'
            elif value == 0:
                was, self.lid_closed = self.lid_closed, False
                if was and dozing:
                    self.guard_until = now + 0.6
                    return 'wake'
            return None
        if kind != 1 or code != 116: return None
        if self.lid_closed or now < self.guard_until:
            if value == 0: self.down_at, self.long_fired = 0.0, False
            return None
        if dozing:
            if value == 1:
                self.down_at, self.long_fired, self.guard_until = 0.0, True, now + 0.5
                return 'wake'
            return None
        if value == 1:
            self.down_at, self.long_fired = now, False
            return None
        if value == 0:
            held, fired = (now - self.down_at) if self.down_at else 0.0, self.long_fired
            self.down_at, self.long_fired = 0.0, False
            if fired or held <= 0: return None
            if held >= self.HOLD: return 'power'
            self.guard_until = now + 0.6
            return 'standby'
        return None

    def tick(self, now, dozing):
        if self.down_at and not self.long_fired and not dozing and not self.lid_closed and now - self.down_at >= self.HOLD:
            self.long_fired = True
            return 'power'
        return None

    def resumed(self, now):
        self.down_at, self.long_fired, self.guard_until = 0.0, False, now + 1.2
        return 'wake'


class VolRepeat:
    """Repeats Volume Down (114, pmic_resin) and Volume Up (115, gpio-keys) while held; neither kernel node sets EV_REP."""
    FIRST, REPEAT = 0.35, 0.09

    def __init__(self): self.code, self.due = 0, 0.0

    def event(self, kind, code, value, now):
        if kind != 1 or code not in (114, 115): return 0
        if value == 1:
            self.code, self.due = code, now + self.FIRST
            return 5 if code == 115 else -5
        if value == 0 and self.code == code: self.code, self.due = 0, 0.0
        return 0

    def tick(self, now):
        if not self.code or now < self.due: return 0
        self.due = now + self.REPEAT
        return 5 if self.code == 115 else -5

    def clear(self): self.code, self.due = 0, 0.0


class PadNav:
    """Turns one controller's raw events into Tandem's navigation actions: buttons once per press, the D-pad and the
    left stick (dead zone 60 %) with key repeat while held."""
    FIRST, REPEAT = 0.4, 0.12

    def __init__(self, span=32767): self.span, self.hat, self.stick, self.dir, self.due = span or 32767, [0, 0], [0, 0], '', 0

    def event(self, kind, code, value, now):
        if kind == 1: return [PAD_KEYS[code]] if value == 1 and code in PAD_KEYS else []
        if kind != 3 or code not in (0, 1, 16, 17): return []
        if code >= 16: self.hat[code - 16] = value
        else: self.stick[code] = value / self.span  # shortcut: assumes a stick centred on 0, read min/max per axis if a pad reports 0..255
        x, y = self.hat[0] or self.stick[0], self.hat[1] or self.stick[1]
        direction = 'left' if x < -.6 else 'right' if x > .6 else 'up' if y < -.6 else 'down' if y > .6 else ''
        if direction == self.dir: return []
        self.dir, self.due = direction, now + self.FIRST
        return [direction] if direction else []

    def tick(self, now):
        if not self.dir or now < self.due: return []
        self.due = now + self.REPEAT
        return [self.dir]


def watch_buttons(tandem):
    """Power key, lid switch, volume keys, the Thor's Back and Home buttons and the controller's navigation. Steam used to
    handle them; here the service does, at all times. Where they arrive was measured on the device: power on 'pmic_pwrkey',
    lid on 'gpio-keys-lid', volume up on 'gpio-keys', volume down on 'pmic_resin', Back as F14 on InputPlumber's keyboard
    (through buttons-profile.yaml), Home as the Guide button of the emulated controller."""
    import fcntl, select, struct
    # Steam's own virtual pads ("… pad 0", vendor 28de) repeat the real one: listening to both would count twice.
    wanted = lambda name: name in ('InputPlumber Keyboard', 'gpio-keys', 'gpio-keys-lid', 'pmic_resin', 'pmic_pwrkey') or (('X-Box' in name or 'Xbox' in name or 'DualSense' in name) and not re.search(r' \d+$', name))
    fds, nodes, scanned = {}, {}, 0  # fd -> PadNav (None for key devices), node -> fd
    size = struct.calcsize('llHHi')
    free = lambda: (tandem.power_open or tandem.prompt_open or not tandem.run or tandem.run.get('paused')
                    or tandem.run.get('keys') or tandem.run.get('s') == 'term' or (tandem.run.get('port') or {}).get('pad'))
    nav = lambda actions: [tandem.publish('key', {'a': a}) for a in actions if free()]
    slept = lambda: time.clock_gettime(time.CLOCK_BOOTTIME) - time.monotonic()  # grows by real kernel suspend
    asleep, fake_asleep, pwr, vol_rep = slept(), FAKE_SUSPEND_FLAG.exists(), PowerKey(), VolRepeat()
    def lid_music_ok():
        cfg = load_config()
        if not cfg.get('lid_music', True): return False
        playing_media = bool((tandem.run and (tandem.run.get('port') or {}).get('deck') in ('youtube', 'plex')) or telemetry.bgm_playing())
        return playing_media and telemetry.headphones_active()
    def run_pwr(act, from_lid=False):
        if act == 'standby':
            if from_lid and lid_music_ok(): return doze(True, tandem, keep_audio=True)
            return tandem.act('suspend')
        if act == 'wake': return doze(False, tandem)
        if act == 'power': return tandem.act('power_menu')
    def step_vol(delta):
        if not delta: return
        vol = settings().get('vol')
        if vol is None: return
        if delta > 0 and MUTED['on']:
            MUTED['on'] = False
            tandem.publish('mute', {'muted': False})
        tandem.publish('settings', {'settings': change('vol', vol + delta), 'osd': 'vol'})
    while True:
        now = time.time()
        fake_now = FAKE_SUSPEND_FLAG.exists()
        if slept() - asleep > 1 or (fake_asleep and not fake_now):  # back from kernel suspend or Armada's fake-suspend
            asleep = slept()
            pwr.resumed(now); vol_rep.clear()
            doze(False, tandem)
        fake_asleep = fake_now
        if now - scanned > 2:  # controllers come and go (InputPlumber sets its pad up after the service has started)
            scanned = now
            try: blocks = Path('/proc/bus/input/devices').read_text().split('\n\n')
            except OSError: return
            for block in blocks:
                name, node = re.search(r'Name="([^"]*)"', block), re.search(r'Handlers=.*?(event\d+)', block)
                if not (name and node and wanted(name[1])) or node[1] in nodes: continue
                try: fd = os.open('/dev/input/' + node[1], os.O_RDONLY | os.O_NONBLOCK)
                except OSError: continue  # a new device is not readable in its first moment: the next scan gets it
                if name[1] == 'gpio-keys-lid':
                    try: pwr.lid_closed = bool(fcntl.ioctl(fd, 0x8008451b, bytes(8))[0] & 1)  # EVIOCGSW(8): bit 0 = SW_LID
                    except OSError: pass
                span = None
                if 'pad' in name[1].lower() or 'DualSense' in name[1]:
                    try: span = struct.unpack('6i', fcntl.ioctl(fd, 0x80184540, bytes(24)))[2]  # EVIOCGABS(ABS_X): maximum
                    except OSError: span = 32767
                nodes[node[1]], fds[fd] = fd, PadNav(span) if span is not None else None
        pads = [p for p in fds.values() if p]
        pwr_wait = [max(0.01, pwr.down_at + pwr.HOLD - now)] if pwr.down_at and not pwr.long_fired else []
        vol_wait = [max(0.01, vol_rep.due - now)] if vol_rep.code else []
        wait = min([max(0.01, p.due - now) for p in pads if p.dir] + pwr_wait + vol_wait + [0.5 if fake_asleep else 2])
        for fd in select.select(list(fds), [], [], wait)[0]:
            try: data = os.read(fd, size * 32)
            except BlockingIOError: continue
            except OSError:
                os.close(fd); del fds[fd]; nodes = {n: f for n, f in nodes.items() if f != fd}; continue
            for start in range(0, len(data) - size + 1, size):
                _, _, kind, code, value = struct.unpack('llHHi', data[start:start + size])
                t_ev = time.time()
                if (kind == 5 and code == 0) or (kind == 1 and code == 116):
                    vol_rep.clear()
                    run_pwr(pwr.event(kind, code, value, t_ev, bool(DOZE), load_config().get('lid_sleep', True)), from_lid=(kind == 5))
                    continue
                if pwr.lid_closed:
                    if DOZE.get('music') and kind == 1 and code in (114, 115):
                        step_vol(vol_rep.event(kind, code, value, t_ev)); continue
                    vol_rep.clear(); continue  # nothing wakes or navigates while the clamshell is shut
                if DOZE:
                    vol_rep.clear()
                    if kind == 1 and value == 1 and t_ev >= pwr.guard_until:
                        pwr.guard_until = t_ev + 0.4
                        doze(False, tandem)
                    continue  # any button ends the doze and does nothing else
                if fds[fd]: nav(fds[fd].event(kind, code, value, t_ev))
                if kind == 1 and code in (114, 115):
                    step_vol(vol_rep.event(kind, code, value, t_ev))
                    continue
                if kind != 1 or value == 0: continue
                if value == 1 and code == 184:  # Back
                    if free(): tandem.publish('key', {'a': 'back'})
                elif value == 1 and code == 185:  # the Thor key: its quick menu on the bottom screen (Zu Tandem is in there)
                    tandem.publish('quick', {})
                elif value == 1 and code == 316:  # Home (a pad's guide button): freeze the game and show Tandem; again: back into the game
                    if tandem.power_open: tandem.act('power_close')
                    elif tandem.run and tandem.run.get('paused'): tandem.resume()
                    elif tandem.run:
                        result = tandem.pause()
                        if 'error' in result: tandem.publish('toast', {'text': result['error']})
                    else: tandem.publish('key', {'a': 'home'})
        now = time.time()
        run_pwr(pwr.tick(now, bool(DOZE)))
        step_vol(vol_rep.tick(now))
        for pad in pads: nav(pad.tick(now))


def rom_roots(extra):
    found = [p for p in extra if os.path.isdir(p)]
    for pattern in (str(HOME / 'ROMs'), '/run/media/*/*/ROMs', '/run/media/*/ROMs', '/media/*/*/ROMs'):
        found += [p for p in sorted(glob.glob(pattern)) if p not in found]
    return found


class QuietHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError, TimeoutError)): return
        super().handle_error(request, client_address)


def main():
    parser = argparse.ArgumentParser(description='Tandem dual-screen launcher')
    parser.add_argument('--port', type=int, default=8377)
    parser.add_argument('--roms', action='append', default=[], help='extra ROM folder (ES-DE layout), repeatable')
    parser.add_argument('--steam', default=str(HOME / '.local/share/Steam'))
    parser.add_argument('--dry-run', action='store_true', help='do not start programs, only log the command')
    args = parser.parse_args()
    library = Library(rom_roots(args.roms + os.environ.get('TANDEM_ROMS', '').split(os.pathsep)), Path(args.steam))
    library.scan()
    tandem = Tandem(library, args.dry_run)
    tandem.sync_gba_packs_bg(force=False)
    def sync_protondb_bg():
        appids = [g['appid'] for g in library.games.values() if g.get('appid') and g.get('inst') != 'no']
        if not appids:
            return
        res = companion.sync_protondb(appids[:60])
        ttb_res = thor_features.sync_steam_ttb(appids[:60])
        if res.get('updated') or ttb_res:
            library.scan()
            tandem.publish('library')
    if not args.dry_run:
        threading.Thread(target=sync_protondb_bg, daemon=True).start()
        thor_airpods.MANAGER.start(tandem)
    if DOZE and not args.dry_run: doze(False, tandem)  # restarted during a doze: bring the panels back right away
    server = QuietHTTPServer(('127.0.0.1', args.port), handler(tandem))
    threading.Thread(target=watch_buttons, args=(tandem,), daemon=True).start()
    def watch_dock():
        prev, dimmed, charge_notified, low_batt_froze, prev_on_bat, last_bifrost, tick = False, {}, False, False, None, '', 0
        while True:
            time.sleep(4)
            tick += 1
            if not DOZE:
                rm = public_config().get('rgb_mode', 'cover')
                if rm in ('battery', 'thermal', 'ambilight'):
                    st_rgb = (thor.state().get('rgb') or {})
                    if st_rgb.get('enabled', True):
                        hc_b = None
                        if rm == 'battery':
                            b_now = battery()
                            chg_d = telemetry.charger_detail() if (b_now and b_now.get('charging')) else {}
                            hc_b = telemetry.bifrost_rgb_color('battery', b_now, fast_chg=bool(chg_d.get('fast_charging')))
                        elif rm == 'thermal':
                            pw_now = thor.power() or {}
                            hc_b = telemetry.bifrost_rgb_color('thermal', temp_c=pw_now.get('temp'))
                        elif rm == 'ambilight' and tandem.run and not tandem.run.get('paused'):
                            ambi_png = Path(f'/run/user/{os.getuid()}/tandem-ambi.png')
                            dpys = _x11_displays()
                            if companion.capture_screen_frame(ambi_png, display=dpys[0] if dpys else ':0'):
                                hc_b = telemetry.sample_ambilight_hex(ambi_png)
                        if hc_b and hc_b != last_bifrost:
                            last_bifrost = hc_b
                            thor.change('rgb', {'color': hc_b, 'enabled': True})
                else:
                    last_bifrost = ''
            st = telemetry.dock_state()
            now_dock = bool(st.get('connected'))
            if now_dock != prev:
                prev = now_dock
                tandem.publish('dock', {'dock': st})
                tandem.publish('toast', {'text': 'TV / Monitor verbunden (Dock-Modus).' if now_dock else 'TV / Monitor getrennt.'})
                if not args.dry_run and load_config().get('dock_dim', True):
                    if now_dock:
                        for k, nm in BACKLIGHTS.items():
                            try:
                                dimmed[k] = lit(k, int((Path('/sys/class/backlight') / nm / 'brightness').read_text()))
                                set_raw(k, lit(k, min(15, dimmed[k])))
                            except (OSError, ValueError): pass
                    elif dimmed:
                        for k, v in dimmed.items(): set_raw(k, lit(k, v))
                        dimmed.clear()
            if tick % 3 == 0:
                if tandem.run and thor_features.REPLAY.running() and thor_features.mem_available_gib() < 2.2:
                    thor_features.REPLAY.stop()
                    tandem.publish('toast', {'text': '🛡️ RAM-Schutz: 30s-Puffer pausiert (volle RAM-Reserve fürs Spiel).'})
                cfg_w = load_config()
                b = battery()
                if b and not b.get('charging') and 0 < b.get('level', 100) <= 5:
                    if not low_batt_froze and tandem.run and not tandem.run.get('paused') and not tandem.run.get('frozen'):
                        low_batt_froze = True
                        if tandem.run.get('emu') == 'RetroArch':
                            retroarch('save')
                            time.sleep(0.25)
                        tandem.freeze_toggle(True)
                        tandem.publish('toast', {'text': f'⚠️ Akku kritisch ({b["level"]} %) – Spiel gesichert & eingefroren!'})
                elif not b or b.get('charging') or b.get('level', 100) >= 8:
                    low_batt_froze = False
                if cfg_w.get('dock_pad_swap', True):
                    try:
                        bt_st = bluetooth.state()
                        bt_pad = any(d.get('kind') == 'pad' and d.get('connected') for d in (bt_st.get('devices') or []))
                        thor_features.apply_dock_coop_pad(now_dock, bt_pad)
                    except Exception:
                        pass
                if b and cfg_w.get('auto_travel'):
                    on_bat = not b.get('charging')
                    if prev_on_bat is not None and on_bat != prev_on_bat:
                        save_config({'travel_mode': on_bat})
                        tandem.publish('config', {'config': public_config()})
                        tandem.publish('thor', {'thor': thor.state()})
                        tandem.publish('toast', {'text': 'Unterwegs-Sparmodus automatisch aktiv (Akkubetrieb).' if on_bat else 'Netzteil erkannt – volle Leistung (120 Hz) aktiv.'})
                    prev_on_bat = on_bat
                else:
                    prev_on_bat = (not b.get('charging')) if b else None
            if tick % 5 == 0:
                limit = int(load_config().get('charge_alert') or 0)
                if limit in (80, 90):
                    b = battery()
                    if b and b.get('charging') and b.get('level', 0) >= limit:
                        if not charge_notified:
                            charge_notified = True
                            telemetry.play_sound('alert')
                            tandem.publish('toast', {'text': f'Akku-Schutz: {b["level"]} % erreicht – Ladegerät kann getrennt werden.'})
                    elif not b or not b.get('charging') or b.get('level', 0) < limit - 3:
                        charge_notified = False
    if not args.dry_run: threading.Thread(target=watch_dock, daemon=True).start()
    init_hz = base_panel_hz()
    if init_hz and not args.dry_run:
        threading.Thread(target=apply_fps_limit, args=(init_hz,), daemon=True).start()
    def look_for_update():  # Integrated idle update & auto-companion daemon (runs 90s after boot, then every 6h while idle)
        first = True
        while True:
            time.sleep(90 if first else 21600)
            first = False
            if args.dry_run or tandem.run or DOZE:
                continue
            cfg = load_config()
            b = battery()
            power_ok = (b is None) or b.get('charging') or b.get('level', 100) >= 25
            if cfg.get('auto_update', True) and power_ok:
                def _on_auto(r):
                    if r.get('updated'):
                        tandem.library.scan()
                        tandem.publish('library')
                        tandem.publish('toast', {'text': r['text']})
                    elif (r.get('tandem') or {}).get('new'):
                        tandem.publish('toast', {'text': r['tandem']['text'] + ' Installieren: Einstellungsseite › Gerät.'})
                    tandem.publish('updater', updater_state(tandem))
                thor_updater.start_update_job(
                    list(tandem.library.games.values()), rom_identity,
                    roots=tandem.library.roots, apply_updates=True,
                    self_update_fn=self_update, on_done=_on_auto,
                )
            else:
                if cfg.get('auto_companions', True):
                    tandem.sync_gba_packs_bg(force=False)
                found = self_update()
                if found.get('new'):
                    tandem.publish('toast', {'text': found['text'] + ' Installieren: Einstellungsseite › Gerät.'})
    threading.Thread(target=look_for_update, daemon=True).start()
    profile = load_config().get('perf_profile')  # armada-powerd forgets it over a restart
    if profile and not args.dry_run: threading.Thread(target=thor.change, args=('profile', profile), daemon=True).start()
    night = load_config().get('night_mode', 'off')
    if night in ('warm', 'night') and not args.dry_run: threading.Thread(target=apply_night_mode, args=(night,), daemon=True).start()
    hud_lvl = load_config().get('hud_level', 0)
    if hud_lvl in (1, 2, 3) and not args.dry_run: threading.Thread(target=telemetry.set_hud, args=(hud_lvl,), daemon=True).start()
    if not args.dry_run:
        threading.Thread(target=thor_perf.ensure_mpv_hwdec, daemon=True).start()
        threading.Thread(target=companion.configure_retroarch, args=(load_config(),), daemon=True).start()
        init_dsp = load_config().get('speaker_dsp', 'cinema')
        if init_dsp in telemetry.SPEAKER_DSP_MODES and init_dsp != 'off':
            threading.Thread(target=telemetry.apply_speaker_dsp, args=(init_dsp,), daemon=True).start()
    if not args.dry_run: threading.Thread(target=hide_steam, args=(tandem,), daemon=True).start()
    new_pin()
    if not args.dry_run: kill_stale()
    if any(g.get('inst') == 'load' for g in library.games.values()): (tandem.steam_watch(), threading.Thread(target=steam_background, daemon=True).start())  # a download from before goes on
    try:
        pair = QuietHTTPServer(('0.0.0.0', args.port + 1), pair_handler(tandem))
        PAIR['port'] = args.port + 1
        if all(f.is_file() for f in TLS_FILES):  # the owner put a certificate there: HTTPS instead of plain HTTP
            import ssl
            try:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(*map(str, TLS_FILES))
                pair.socket = context.wrap_socket(pair.socket, server_side=True)  # shortcut: the handshake runs in the accepting thread, a stalled client delays the next one; wrap per connection if that ever shows
                PAIR['tls'] = True
            except (ssl.SSLError, OSError) as error: print(f'TLS-Zertifikat nicht nutzbar, Einstellungsseite bleibt bei HTTP: {error}', flush=True)
        threading.Thread(target=pair.serve_forever, daemon=True).start()
    except OSError: pass  # port taken: the account can still be entered on the device itself
    print(f'Toravo Tandem: {len(library.games)} Spiele aus {library.roots or "keinem ROM-Ordner"} – http://127.0.0.1:{args.port}/', flush=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try: server.serve_forever()
    finally:
        proc = tandem.proc
        tandem.quit()
        if proc:  # the session is ending: the reaper's grace period would never run out, so end the game's group now
            time.sleep(1)
            try: os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError): pass


if __name__ == '__main__':
    main()
