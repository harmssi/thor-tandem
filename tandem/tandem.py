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
IMAGES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}


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
    'snes': ('Super Nintendo', 285, 'sfc smc fig swc bs zip 7z', [('RetroArch', ra('snes9x', 'bsnes'))]),
    'n64': ('Nintendo 64', 130, 'z64 n64 v64 zip 7z', [('RetroArch', ra('mupen64plus_next', 'parallel_n64'))]),
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
    'genesis': ('Genesis', 215, 'md gen bin smd zip 7z', [('RetroArch', ra('genesis_plus_gx', 'picodrive'))]),
    'megadrive': ('Mega Drive', 215, 'md gen bin smd zip 7z', [('RetroArch', ra('genesis_plus_gx', 'picodrive'))]),
    'mastersystem': ('Master System', 215, 'sms zip 7z', [('RetroArch', ra('genesis_plus_gx', 'picodrive'))]),
    'gamegear': ('Game Gear', 150, 'gg zip 7z', [('RetroArch', ra('genesis_plus_gx'))]),
    'segacd': ('Sega CD', 215, 'chd cue iso m3u', [('RetroArch', ra('genesis_plus_gx', 'picodrive'))]),
    'saturn': ('Saturn', 300, 'chd cue iso m3u', [('Ymir', fp('io.github.strikerx3.ymir')), ('RetroArch', ra('mednafen_saturn', 'yabause'))]),
    'pcengine': ('PC Engine', 25, 'pce chd cue zip 7z', [('RetroArch', ra('mednafen_pce_fast', 'mednafen_pce'))]),
    'arcade': ('Arcade', 5, 'zip 7z', [('RetroArch', ra('fbneo', 'mame2003_plus'))]),
    'fbneo': ('FinalBurn Neo', 5, 'zip 7z', [('RetroArch', ra('fbneo'))]),
    'switch': ('Switch', 355, 'nsp xci nsz', [('Eden', app('Eden*.AppImage', '-f', '-g'))]),  # not in the Armada Store: Tandem's own updater fetches it
}
# Apps offered in the Apps tab when installed: (label, kind, target, args)
APPS = [('Firefox', 'cmd', 'firefox', ()), ('Heroic', 'cmd', 'heroic', ('--no-sandbox',)), ('ES-DE', 'appimage', 'ES-DE*.AppImage', ()),
        ('Moonlight', 'flatpak', 'com.moonlight_stream.Moonlight', ()), ('Chiaki', 'flatpak', 'io.github.streetpea.Chiaki4deck', ()),
        ('RetroArch', 'flatpak', RA_REF, ()), ('Prism Launcher', 'flatpak', 'org.prismlauncher.PrismLauncher', ())]
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


def find_pack(game):
    """The companion pack (a folder in ~/.config/tandem/packs) made for this ROM: manifest.json names game codes and/or
    CRC32s (gba-duo-wide: the code must be listed, and the CRC too if any are; a pack without codes goes by CRC alone)."""
    packs = CONFIG.parent / 'packs'
    if game.get('s') not in ('gb', 'gbc', 'gba') or not game.get('path') or not packs.is_dir(): return None
    code = crc = None
    for manifest in sorted(packs.glob('*/manifest.json')):
        try:
            match = json.loads(manifest.read_text(encoding='utf-8'))['match']
            codes, crcs = [str(c) for c in match.get('gameCode') or []], [int(str(c), 16) for c in match.get('crc32') or []]
        except (OSError, ValueError, KeyError, AttributeError, TypeError): continue
        if code is None: code, crc = rom_identity(game['path'])  # read the ROM only when there is a pack at all
        if code is None: return None
        if (code in codes or 'AGB-' + code in codes if codes else bool(crcs)) and (not crcs or crc in crcs): return manifest.parent.name
    return None


def wide_core(cmd, pack, on):
    """Wide view (gba-duo-wide's game.lua wide()): when the pack describes the game's world and the wide core is installed,
    leave the script and the switch where that core reads them (wide-core/README.md) and start it instead of mGBA.
    Returns (cmd, on); on is None when there is no wide view and the command stays as it was."""
    folder = CONFIG.parent / 'packs' / pack
    try:
        at = cmd.index('-L') + 1
        script = folder / Path(str(json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))['gameScript'])).name
        if cmd[at] != str(RA_CORES[0] / 'mgba_libretro.so') or not RA_WIDE_CORE.is_file(): return cmd, None
        if not re.search(r'^function\s+wide\s*\(', script.read_text(encoding='utf-8'), re.M): return cmd, None
        shutil.rmtree(RA_WIDE, ignore_errors=True)
        RA_WIDE.mkdir(parents=True)
        for lua in folder.glob('*.lua'): shutil.copy(lua, RA_WIDE)  # pack.require looks beside the script
        shutil.copy(script, RA_WIDE / 'game.lua')
        (RA_WIDE / 'on').write_text('1' if on else '0')
    except (OSError, ValueError, KeyError): return cmd, None
    return cmd[:at] + [str(RA_WIDE_CORE)] + cmd[at + 1:], bool(on)


def emulator(system):
    """(label, command prefix) of the first usable emulator, or (None, what to install)."""
    emus = SYSTEMS[system][3]
    if not emus: return None, 'Für dieses System bietet der Armada Store keinen Emulator.'
    reasons = []
    for label, (kind, target, args) in emus:
        cmd, why = resolve(kind, target, args)
        if cmd: return label, cmd
        reasons.append(f'{label}: {why}')
    return None, 'Emulator fehlt (unter Apps oder im Armada Store installieren) – ' + '; '.join(dict.fromkeys(reasons))


MEDIA = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'tandem/media'  # art Tandem fetched itself
# Folder -> playlist name on thumbnails.libretro.com (free box art and screenshots, named after No-Intro/Redump sets)
LIBRETRO = {'gb': 'Nintendo - Game Boy', 'gbc': 'Nintendo - Game Boy Color', 'gba': 'Nintendo - Game Boy Advance',
            'nes': 'Nintendo - Nintendo Entertainment System', 'snes': 'Nintendo - Super Nintendo Entertainment System',
            'n64': 'Nintendo - Nintendo 64', 'nds': 'Nintendo - Nintendo DS', 'n3ds': 'Nintendo - Nintendo 3DS', 'gc': 'Nintendo - GameCube',
            'wii': 'Nintendo - Wii', 'wiiu': 'Nintendo - Wii U', 'psx': 'Sony - PlayStation', 'ps2': 'Sony - PlayStation 2',
            'psp': 'Sony - PlayStation Portable', 'dreamcast': 'Sega - Dreamcast', 'genesis': 'Sega - Mega Drive - Genesis',
            'megadrive': 'Sega - Mega Drive - Genesis', 'mastersystem': 'Sega - Master System - Mark III', 'gamegear': 'Sega - Game Gear',
            'segacd': 'Sega - Mega-CD - Sega CD', 'saturn': 'Sega - Saturn', 'pcengine': 'NEC - PC Engine - TurboGrafx 16'}


def scrape(games):
    """Fetch missing covers (and a screenshot as background) from the libretro thumbnail server. Returns how many arrived."""
    import urllib.parse, urllib.request
    found = 0
    for game in games:
        playlist = LIBRETRO.get(game['s'])
        if game.get('cover') or not playlist or 'path' not in game: continue
        stem = Path(game['path']).stem
        name = re.sub(r'[&*/:`<>?\\|"]', '_', stem)  # the server's file naming rule
        for kind, folder in (('Named_Boxarts', 'covers'), ('Named_Snaps', 'snaps')):
            target = MEDIA / game['s'] / folder / f'{stem}.png'
            if target.is_file(): continue
            url = f'https://thumbnails.libretro.com/{urllib.parse.quote(playlist)}/{kind}/{urllib.parse.quote(name)}.png'
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Tandem/0.1 (game launcher)'}), timeout=15) as reply:
                    data = reply.read()
            except OSError: continue
            if data[:4] != b'\x89PNG': continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            found += kind == 'Named_Boxarts'
    return found


class Library:
    def __init__(self, roots, steam):
        self.roots, self.steam, self.media, self.games, self.lock = roots, steam, {}, {}, threading.Lock()

    def _media_index(self, folder):
        """stem -> file for one media folder; Cocoon appends '__cocoon_edit_<n>_<hash>' to the ROM stem."""
        index = {}
        try:
            for entry in os.scandir(folder):
                if Path(entry.name).suffix.lower() in IMAGES:
                    index[Path(entry.name).stem.split('__cocoon_edit_')[0]] = entry.path
        except OSError: pass
        return index

    def _art(self, root, system):
        base = Path(root).parent
        cover, hero = {}, {}
        for media, covers, heroes in ((base / 'ES-DE/downloaded_media', ('covers', 'miximages', 'screenshots'), ('fanart', 'screenshots')),
                                     (HOME / 'ES-DE/downloaded_media', ('covers', 'miximages', 'screenshots'), ('fanart', 'screenshots')),
                                     (base / 'Cocoon/downloaded_media', ('icon', 'screenshot_title'), ('hero', 'screenshot_gameplay')),
                                     (MEDIA, ('covers',), ('snaps',))):
            for kinds, target in ((covers, cover), (heroes, hero)):
                for kind in reversed(kinds):  # earlier names win
                    target.update(self._media_index(media / system / kind))
        return cover, hero

    def _system_art(self, system):
        """Platform artwork of a Cocoon theme on the card (assets/smart_folders/<pack>/smart_folders/by_platform/<system>/)."""
        names = [system] + {'megadrive': ['genesis'], 'genesis': ['megadrive'], 'n3ds': ['3ds'], 'gc': ['gamecube'], 'psx': ['ps1']}.get(system, [])
        for root in self.roots:
            for name in names:
                for folder in sorted(glob.glob(str(Path(root).parent / f'Cocoon/assets/smart_folders/*/smart_folders/by_platform/{name}'))):
                    art = {kind: str(Path(folder) / f'{kind}.png') for kind in ('icon', 'hero', 'logo') if (Path(folder) / f'{kind}.png').is_file()}
                    if art: return art
        return {}

    def _image(self, path):
        if not path: return None
        token = ident(path) + Path(path).suffix.lower()
        self.media[token] = path
        return 'media/' + token

    def scan(self):
        games, media = {}, {}
        self.media = media
        for root in self.roots:
            for system, (name, hue, exts, _) in SYSTEMS.items():
                folder = Path(root) / system
                if not folder.is_dir(): continue
                cover, hero = self._art(root, system)
                wanted = {'.' + e for e in exts.split()}
                for entry in sorted(os.scandir(folder), key=lambda e: e.name.lower()):
                    path = Path(entry.path)
                    if entry.name.startswith('.') or not entry.is_file() or path.suffix.lower() not in wanted: continue
                    gid = ident(system, entry.name)
                    games[gid] = {'id': gid, 't': clean(path.stem), 's': system, 'path': entry.path,
                                  'cover': self._image(cover.get(path.stem)), 'hero': self._image(hero.get(path.stem) or cover.get(path.stem))}
        for manifest in glob.glob(str(self.steam / 'steamapps/appmanifest_*.acf')):
            text = Path(manifest).read_text(errors='ignore')
            appid, name = re.search(r'"appid"\s+"(\d+)"', text), re.search(r'"name"\s+"([^"]+)"', text)
            if not appid or not name or STEAM_TOOLS.match(name[1]): continue
            number = lambda key: int((re.search(rf'"{key}"\s+"(\d+)"', text) or [0, 0])[1])
            loading = not number('StateFlags') & 4  # 4 = fully installed
            done, total = number('BytesDownloaded') + number('BytesStaged'), number('BytesToDownload') + number('BytesToStage')
            art = lambda n: next((p for p in (self.steam / f'appcache/librarycache/{appid[1]}/{n}', self.steam / f'appcache/librarycache/{appid[1]}_{n}') if p.is_file()), None)
            gid = 'steam' + appid[1]
            games[gid] = {'id': gid, 't': name[1], 's': 'steam', 'appid': appid[1], 'cover': self._image(art('library_600x900.jpg') and str(art('library_600x900.jpg'))),
                          'hero': self._image(art('library_hero.jpg') and str(art('library_hero.jpg')))}
            if loading: games[gid].update(inst='load', pct=round(100 * done / total) if total else None)
        # The rest of the Steam library, read from Steam's own files: these can be installed from here.
        for appid, app in steam_apps(self.steam / 'appcache/appinfo.vdf').items():
            cover = self.steam / f'appcache/librarycache/{appid}/library_600x900.jpg'
            if 'steam' + appid in games or app.get('type', '').lower() != 'game' or not app.get('installdir') or not cover.is_file(): continue
            hero = self.steam / f'appcache/librarycache/{appid}/library_hero.jpg'
            games['steam' + appid] = {'id': 'steam' + appid, 't': app['name'], 's': 'steam', 'appid': appid, 'inst': 'no', 'dir': app['installdir'],
                                      'cover': self._image(str(cover)), 'hero': self._image(str(hero)) if hero.is_file() else None}
        with self.lock: self.games = games
        return games

    def payload(self, saved):
        systems = {}
        for g in self.games.values():
            if g['s'] != 'steam': systems[g['s']] = systems.get(g['s'], 0) + 1
        info = {}
        for s, n in systems.items():
            label, cmd = emulator(s)
            art = self._system_art(s)
            info[s] = {'name': SYSTEMS[s][0], 'hue': SYSTEMS[s][1], 'n': n, 'emu': label, 'missing': None if label else cmd,
                       'cover': self._image(art.get('icon') or art.get('logo')), 'hero': self._image(art.get('hero'))}
        apps = [{'id': 'app' + str(i), 't': a[0], 's': 'app'} for i, a in enumerate(APPS) if resolve(*a[1:])[0]]
        public = [{k: v for k, v in g.items() if k != 'path'} for g in self.games.values()]
        return {'systems': info, 'games': public, 'apps': apps, 'fav': saved.get('fav', []), 'played': saved.get('played', {}), 'extras': extras_state()}


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
    """Hide ('unmap') or show ('map') another program's window. Hiding the game's window is how Tandem comes to the front."""
    import ctypes
    try:
        x = ctypes.CDLL('libX11.so.6')
        x.XOpenDisplay.restype = ctypes.c_void_p
        display = x.XOpenDisplay(None)
        if not display: return False
        # Xlib's own reaction to an error (a window that is gone by now) is to end the whole program: replace it.
        global X_QUIET
        X_QUIET = X_QUIET or ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(lambda *_: 0)
        x.XSetErrorHandler(X_QUIET)
        call = x.XUnmapWindow if action == 'unmap' else x.XMapWindow
        call.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        call(display, window)
        x.XFlush.argtypes = x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XSync(display, 0); x.XCloseDisplay(display)  # XSync: errors arrive while the quiet handler is in place
        return True
    except OSError: return False


class Tandem:
    def __init__(self, library, dry=False):
        self.library, self.dry = library, dry
        self.ui, self.run, self.proc, self.clients, self.lock = {'tab': 0, 'sys': None, 'i': 0}, None, None, [], threading.Lock()
        self.steam_show = 0  # until when Steam's own window may show, see hide_steam
        self.mirror = None  # Wii U: the GamePad picture on the bottom screen
        self.home_window = 0  # Tandem's own top window, noted when a game starts
        self.setup = {'open': not SETUP_MARK.exists(), 'step': 0}  # the first-run assistant on the screens (see setup_info)
        STATE.mkdir(parents=True, exist_ok=True)
        try: self.saved = json.loads((STATE / 'state.json').read_text())
        except (OSError, ValueError): self.saved = {}
        if not self.saved.get('played') and not self.saved.get('fav'): self.ui['tab'] = 1  # nothing played yet: open on the systems

    def save(self):
        tmp = STATE / 'state.json.tmp'
        tmp.write_text(json.dumps(self.saved))
        os.replace(tmp, STATE / 'state.json')

    def snapshot(self): return {'ui': self.ui, 'run': self.run, 'setup': self.setup}

    def publish(self, kind='state', data=None):
        message = json.dumps({'kind': kind, **(data if data is not None else self.snapshot())})
        for q in list(self.clients):
            try: q.put_nowait(message)
            except queue.Full: pass

    def command(self, game):
        if game['s'] == 'steam': return 'Steam', ['steam', '-silent', f'steam://rungameid/{game["appid"]}']  # no Steam window, only the game
        label, cmd = emulator(game['s'])
        return (label, cmd + [game['path']]) if label else (None, cmd)

    def launch(self, gid):
        with self.lock:
            if self.run: return {'error': 'Es ist noch ein Spiel offen – erst fortsetzen oder beenden.' if self.run.get('paused') else 'Es läuft schon ein Spiel.'}
            if gid == 'term':
                found = next(((which(name), args) for name, args in TERMINALS if which(name)), None)
                layout = region_layout()
                game = {'id': 'term', 't': 'Terminal', 's': 'term', 'layout': layout}
                label, cmd = ('Terminal', [found[0], *found[1]]) if found else (None, 'Kein Terminal-Programm gefunden.')
                if found: run_quiet(['setxkbmap', layout])  # the layout decides what the on-screen keys type
            elif gid.startswith('app') and gid[3:].isdigit() and int(gid[3:]) < len(APPS):
                entry = APPS[int(gid[3:])]
                game, (label, (cmd, why)) = {'id': gid, 't': entry[0], 's': 'app'}, (entry[0], resolve(*entry[1:]))
                if not cmd: label, cmd = None, why
            else:
                game = self.library.games.get(gid)
                if not game: return {'error': 'Spiel nicht gefunden – Bibliothek neu einlesen.'}
                if game.get('inst') == 'load': return {'error': f'„{game["t"]}“ wird noch geladen.'}
                if game.get('inst') == 'no': return self.steam_install(game)
                label, cmd = self.command(game)
                if game['s'] == 'steam': self.steam_show = time.time() + 300
            if not label: return {'error': cmd}
            pack, wide = find_pack(game) if label == 'RetroArch' else None, None  # the native bottom screen runs it (ui/decks/pack.py)
            if pack and game['s'] == 'gba': cmd, wide = wide_core(cmd, pack, self.saved.get('wide', {}).get(gid, False))
            if not self.dry: self.home_window = focused_window()
            with open(STATE / 'launch.log', 'ab') as log:  # the child keeps its own copy of the handle
                log.write(f'\n== {time.strftime("%F %T")} {game["t"]}: {cmd}\n'.encode()); log.flush()
                if not self.dry:
                    env = None
                    if game['s'] == 'wiiu': env = {**os.environ, 'DISABLE_GAMESCOPE_WSI': '1'}; cemu_pad_window()  # see mirror_pad
                    try: self.proc = subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, env=env)
                    except OSError as error: return {'error': f'Start fehlgeschlagen: {error}'}
                    if game['s'] not in ('steam', 'app'): (STATE / 'running').write_text(f'{self.proc.pid} {start_time(self.proc.pid)}')
            played = self.saved.setdefault('played', {}).setdefault(gid, {'secs': 0})
            played['last'] = int(time.time())
            self.save()
            tracked = game['s'] != 'app'  # apps hand off to another process right away
            if tracked:
                self.run = {'id': gid, 't': game['t'], 's': game['s'], 'emu': label, 'since': int(time.time()), 'hero': game.get('hero'),
                            'layout': game.get('layout'), 'appid': game.get('appid'),
                            'deck': f'deck/{game["appid"]}.html' if game.get('appid') and (HERE / f'decks/{game["appid"]}.html').is_file() else None,
                            'pack': pack, 'wide': wide}
                if not self.dry: threading.Thread(target=self.watch, args=(self.proc, gid, game.get('appid')), daemon=True).start()
                if not self.dry and game['s'] == 'wiiu': threading.Thread(target=self.mirror_pad, args=(gid,), daemon=True).start()
        self.publish()
        return {'ok': True, 'cmd': cmd, 'tracked': tracked}

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
        threading.Thread(target=run_quiet, args=(['steam', '-shutdown'], 60), daemon=True).start()

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
                    if longest >= SETUP_SECS: self.steam_show = 0  # the game itself is there: Steam's own window may go
                else: there, gone = 0, gone + 2
                # Asked to quit: the wait for a game that may still appear is over, whatever was seen of it so far.
                if steam_game_over(longest, gone, time.time() > deadline or self.run.get('quitting')): break
                time.sleep(2)
        self.finish(gid)

    def finish(self, gid):
        with self.lock:
            if not self.run or self.run['id'] != gid: return
            self.saved['played'][gid]['secs'] += int(time.time()) - self.run['since']
            self.save()  # before the run is cleared: whoever sees "no game running" also finds the play time on disk
            steam = self.run.get('appid')
            self.run, self.proc = None, None
            (STATE / 'running').unlink(missing_ok=True)
            self.mirror_stop()
        if steam: self.steam_rest()
        self.publish()
        threading.Thread(target=self.come_home, daemon=True).start()

    def come_home(self):
        """After a game the top compositor can be left with no window in front and keeps showing the game's last picture
        (seen with Fallout 4 ended from outside): hiding and showing Tandem's own window makes it take that again."""
        time.sleep(2)
        if self.dry or self.run or not self.home_window or focused_window(): return
        x_window('unmap', self.home_window); time.sleep(0.5); x_window('map', self.home_window)

    def quit(self):
        proc, run = self.proc, self.run
        if not run: return {'ok': True}
        run['quitting'] = True
        if self.dry or not proc:
            self.finish(run['id'])
            return {'ok': True}
        try:
            if run.get('paused'): self.send(signal.SIGCONT)  # a frozen program cannot react to being asked to quit
            self.send(signal.SIGTERM)
            def reap(group=proc.pid, appid=run.get('appid')):
                # The sandbox's inner processes can outlive the outer one that Popen watches: after the grace period
                # whatever is left of the game's process group has to go, or it keeps running unseen.
                for pid in steam_pids(appid) if appid else [-group]:  # a negative number means the whole group
                    try: os.kill(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError): pass
            threading.Timer(5, reap).start()
        except ProcessLookupError: pass
        return {'ok': True}

    def pause(self):
        """Home button while a game runs: freeze it, hide its window, Tandem is in front again. Like the Switch's Home."""
        with self.lock:
            run, proc = self.run, self.proc
            if not run or run.get('paused') or self.dry or not proc: return {'error': 'Es läuft kein Spiel.'}
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


def settings():
    """Brightness of both panels and the volume, each 0-100, or None where the device has no such control."""
    out = {}
    for key, name in BACKLIGHTS.items():
        try:
            base = Path('/sys/class/backlight') / name
            out[key] = round(100 * int((base / 'brightness').read_text()) / int((base / 'max_brightness').read_text()))
        except (OSError, ValueError, ZeroDivisionError): out[key] = None
    volume = re.search(r'Volume: ([0-9.]+)', run_quiet(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@']))
    out['vol'] = round(100 * float(volume[1])) if volume else None
    return out


def change(key, value):
    value = max(0, min(100, int(value)))
    if key in BACKLIGHTS:
        base = Path('/sys/class/backlight') / BACKLIGHTS[key]
        try: raw = max(1, round(int((base / 'max_brightness').read_text()) * value / 100))  # never fully dark
        except (OSError, ValueError): return {'error': 'Diese Helligkeit lässt sich hier nicht einstellen.'}
        if key == 'bt': run_quiet([PRIV_WRITE, str(base / 'brightness'), str(raw)])
        # ArmadaOS's helper steers every backlight write to the top panel; the bottom one goes to logind directly.
        else: run_quiet(['busctl', '--system', 'call', 'org.freedesktop.login1', '/org/freedesktop/login1/session/auto',
                         'org.freedesktop.login1.Session', 'SetBrightness', 'ssu', 'backlight', BACKLIGHTS[key], str(raw)])
    elif key == 'vol':
        run_quiet(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', f'{value}%'])
    else: return {'error': 'unbekannte Einstellung'}
    return settings()


def retroarch(name):
    """One of RetroArch's network commands (needs network_cmd_enable in retroarch.cfg); UDP, no answer expected."""
    if name not in RA_COMMANDS: return {'error': 'unbekannter Befehl'}
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock: sock.sendto(RA_COMMANDS[name].encode(), ('127.0.0.1', 55355))
    return {'ok': True}


def action(name):
    if name == 'steam':  # one session with Steam (PC games, system updates); the next start is Tandem again
        flag = HOME / '.config/tandem/steam-once'
        flag.parent.mkdir(parents=True, exist_ok=True); flag.touch()
        cmd = ['sudo', '-n', 'systemctl', 'restart', 'sddm']
    elif name in ACTIONS: cmd = ACTIONS[name]
    else: return {'error': 'unbekannte Aktion'}
    try: subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as error: return {'error': f'Geht hier nicht: {error}'}
    return {'ok': True}


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
    if data.get('kb_layout') in ('de', 'us'): config['kb_layout'] = data['kb_layout']
    if data.get('theme') in [t['id'] for t in themes()]: config['theme'] = data['theme']
    if data.get('rest_min') in (0, 1, 3, 10): config['rest_min'] = data['rest_min']  # minutes until the screens go black to spare the OLED, 0 = never
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
    extra = {}
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
    return {'ra_user': config.get('ra_user', ''), 'ra_key_set': bool(config.get('ra_key')), 'ra_login': bool(config.get('ra_token')),
            'kb_layout': config.get('kb_layout', ''), 'remote_url': config.get('remote_url', ''), 'rest_min': config.get('rest_min', 3), 'version': VERSION, 'update_url': config.get('update_url', UPDATE_URL), 'theme': config.get('theme') if config.get('theme') in [t['id'] for t in looks] else 'toravo', 'themes': looks}


RA_CONSOLES = {'megadrive': 1, 'genesis': 1, 'n64': 2, 'snes': 3, 'gb': 4, 'gba': 5, 'gbc': 6, 'nes': 7, 'pcengine': 8, 'segacd': 9,
               'mastersystem': 11, 'psx': 12, 'gamegear': 15, 'gc': 16, 'nds': 18, 'wii': 19, 'ps2': 21, 'arcade': 27, 'saturn': 39,
               'dreamcast': 40, 'psp': 41, 'n3ds': 62}
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
    if not config.get('ra_key') or not config.get('ra_user'): return {'note': 'RetroAchievements ist nicht eingerichtet (System › Konto).'}
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


KEYBOARD = Keyboard()
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


def battery():
    for supply in glob.glob('/sys/class/power_supply/*/capacity'):
        try:
            status = Path(supply).with_name('status').read_text().strip()
            return {'level': int(Path(supply).read_text()), 'charging': status in ('Charging', 'Full')}
        except (OSError, ValueError): pass
    return None


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
            if path == '/api/state': return self.send(200, {**tandem.snapshot(), 'battery': battery(), 'settings': settings(), 'config': public_config(), 'pair': pair_info()})
            if path.startswith('/media/'):
                file = tandem.library.media.get(path[7:])  # only files the scan indexed, never a path from the request
                if file and os.path.isfile(file): return self.send(200, Path(file).read_bytes(), IMAGES[Path(file).suffix.lower()], 'max-age=86400')
                return self.send(404, {'error': 'kein Bild'})
            if path == '/api/setup': return self.send(200, {**tandem.setup, **setup_info(tandem)})
            if path == '/api/system': return self.send(200, system_info(tandem.library.roots, 'scan' in self.path))
            if path == '/api/achievements':
                run = tandem.run and tandem.library.games.get(tandem.run['id'])
                return self.send(200, achievements(run) if run else {'note': 'Es läuft kein Spiel.'})
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
            try: data = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
            except ValueError: return self.send(400, {'error': 'kein JSON'})
            path = urlparse(self.path).path
            if path == '/api/ui':
                system = data.get('sys')
                tandem.ui = {'tab': int(data.get('tab', 0)), 'sys': system if isinstance(system, str) and system in SYSTEMS else None, 'i': int(data.get('i', 0))}
                tandem.publish('state', {**tandem.snapshot(), 'from': data.get('from')})  # the sender skips its own echo
                return self.send(200, {'ok': True})
            if path == '/api/launch':
                result = tandem.launch(str(data.get('id', '')))
                if 'error' in result: tandem.publish('toast', {'text': result['error']})
                elif not result['tracked']: tandem.publish('toast', {'text': result.get('text') or 'Gestartet – zurück geht es über die Home-Taste.'})
                return self.send(200, result)
            if path == '/api/confirm':  # pass a question on to the other screen's page
                tandem.publish('confirm', {'open': bool(data.get('open')), 'then': data.get('then'), 'action': data.get('action') if data.get('action') in ACTIONS else None, 'from': data.get('from')})
                return self.send(200, {'ok': True})
            if path == '/api/quit': return self.send(200, tandem.quit())
            if path == '/api/pause': return self.send(200, tandem.pause())
            if path == '/api/resume': return self.send(200, tandem.resume())
            if path == '/api/set':
                result = change(str(data.get('key', '')), data.get('value', 0) if isinstance(data.get('value', 0), (int, float)) else 0)
                if 'error' not in result: tandem.publish('settings', {'settings': result, 'from': data.get('from')})
                return self.send(200, result)
            if path == '/api/wifi': return self.send(200, wifi_connect(str(data.get('ssid', '')), str(data.get('password', ''))))
            if path == '/api/update':
                def work(key=str(data.get('id', ''))):
                    tandem.publish('toast', {'text': update_extra(key, tandem.library.roots)})
                    tandem.publish('library')
                threading.Thread(target=work, daemon=True).start()
                return self.send(200, {'ok': True})
            if path == '/api/key':
                code = data.get('code')
                return self.send(200, KEYBOARD.press(code if isinstance(code, int) else 0, [m for m in data.get('mods', []) if isinstance(m, str)]))
            if path == '/api/layout':  # switch the on-screen keyboard's layout while the terminal is open
                result = save_config({'kb_layout': data.get('layout')})
                layout = region_layout()
                run_quiet(['setxkbmap', layout])
                if tandem.run and tandem.run.get('s') == 'term': tandem.run['layout'] = layout
                tandem.publish()
                return self.send(200, {**result, 'layout': layout})
            if path == '/api/config':
                result = save_config(data)
                tandem.publish('config', {'config': public_config()})  # both screens follow (theme)
                return self.send(200, result)
            if path == '/api/wide': return self.send(200, tandem.wide(str(data.get('on', ''))))
            if path == '/api/retroarch': return self.send(200, retroarch(str(data.get('name', ''))))
            if path == '/api/action': return self.send(200, action(str(data.get('name', ''))))
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
_REMOTE = (HERE / 'remote.html').read_text().split('<!--SPLIT-->')
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
            path = urlparse(self.path).path
            if path == '/api/all':
                if not self.allowed(): return self.reply(401, {'error': 'nicht angemeldet'}, 'application/json')
                run = tandem.run and tandem.library.games.get(tandem.run['id'])
                return self.reply(200, {'settings': settings(), 'config': public_config(), 'layout': region_layout(), 'battery': battery(),
                                        'system': system_info(tandem.library.roots), 'games': len(tandem.library.games),
                                        'run': (run or {}).get('name') or (tandem.run or {}).get('id')}, 'application/json')
            self.reply(200, REMOTE_PAGE if self.allowed() else PAIR_PAGE.replace('__MSG__', ''))

        def do_POST(self):
            import hmac, secrets, urllib.parse
            raw = self.rfile.read(min(int(self.headers.get('Content-Length') or 0), 4096))
            path = urlparse(self.path).path
            if not path.startswith('/api/'):  # the PIN form
                form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(errors='replace')).items()}
                if not hmac.compare_digest(form.get('pin', ''), PAIR['pin']):
                    PAIR['tries'] += 1
                    if PAIR['tries'] >= 5: new_pin(); tandem.publish()  # a fresh PIN after five wrong ones
                    return self.reply(200, PAIR_PAGE.replace('__MSG__', '<p><b>Die PIN stimmt nicht.</b></p>'))
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
                result = save_config(data); tandem.publish('config', {'config': public_config()})
            elif what == 'layout': result = save_config({'kb_layout': data.get('layout')})
            elif what == 'set':
                result = change(str(data.get('key', '')), data.get('value', 0) if isinstance(data.get('value', 0), (int, float)) else 0)
                if 'error' not in result: tandem.publish('settings', {'settings': result})
            elif what == 'wifi': result = wifi_connect(str(data.get('ssid', '')), str(data.get('password', '')))
            elif what == 'rescan':
                tandem.library.scan()
                if scrape(list(tandem.library.games.values())): tandem.library.scan()
                tandem.publish('library'); result = {'text': f'{len(tandem.library.games)} Spiele gefunden.'}
            elif what == 'update':
                result = {'text': update_extra(data.get('id') if data.get('id') in EXTRAS else 'eden', tandem.library.roots)}; tandem.publish('library')
            elif what == 'quit': result = tandem.quit()
            elif what == 'selfupdate': result = self_update(bool(data.get('apply')))
            elif what in ('logout', 'logout-all'):
                mine = token_hash(re.search(r'tandem=([0-9a-f]{32})', self.headers.get('Cookie') or '')[1])
                save_devices([h for h in devices() if h != mine] if what == 'logout' else [])
                return self.reply(200, {'text': 'Abgemeldet.'}, 'application/json', (self.cookie('', 0),))
            elif what == 'action' and data.get('name') in ('suspend', 'reboot', 'poweroff'): result = action(data['name'])
            else: return self.reply(404, {'error': 'unbekannt'}, 'application/json')
            self.reply(200, result, 'application/json')
    return Pair


# Controller buttons as measured on the Thor (evdev codes of the emulated "Microsoft X-Box 360 pad"; the Thor prints them
# Nintendo-style, so BTN_EAST is the printed A): A ok, B back, X close, Y favourite, LB/RB previous/next tab.
PAD_KEYS = {305: 'ok', 304: 'back', 307: 'close', 308: 'fav', 310: 'prev', 311: 'next'}


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
    """Volume keys, the Thor's Back and Home buttons and the controller's navigation. Steam used to handle them; here the
    service does, at all times. Where they arrive was measured on the device: volume up on 'gpio-keys', volume down on
    'pmic_resin', Back as F14 on InputPlumber's keyboard (through buttons-profile.yaml), Home as the Guide button of the
    emulated controller. Navigation goes out as 'key' events while no game has the controller."""
    import fcntl, select, struct
    # Steam's own virtual pads ("… pad 0", vendor 28de) repeat the real one: listening to both would count twice.
    wanted = lambda name: name in ('InputPlumber Keyboard', 'gpio-keys', 'pmic_resin') or (('X-Box' in name or 'Xbox' in name or 'DualSense' in name) and not re.search(r' \d+$', name))
    fds, nodes, scanned = {}, {}, 0  # fd -> PadNav (None for key devices), node -> fd
    size = struct.calcsize('llHHi')
    nav = lambda actions: [tandem.publish('key', {'a': a}) for a in actions if not tandem.run or tandem.run.get('paused')]
    while True:
        now = time.time()
        if now - scanned > 2:  # controllers come and go (InputPlumber sets its pad up after the service has started)
            scanned = now
            try: blocks = Path('/proc/bus/input/devices').read_text().split('\n\n')
            except OSError: return
            for block in blocks:
                name, node = re.search(r'Name="([^"]*)"', block), re.search(r'Handlers=.*?(event\d+)', block)
                if not (name and node and wanted(name[1])) or node[1] in nodes: continue
                try: fd = os.open('/dev/input/' + node[1], os.O_RDONLY | os.O_NONBLOCK)
                except OSError: continue  # a new device is not readable in its first moment: the next scan gets it
                span = None
                if 'pad' in name[1].lower() or 'DualSense' in name[1]:
                    try: span = struct.unpack('6i', fcntl.ioctl(fd, 0x80184540, bytes(24)))[2]  # EVIOCGABS(ABS_X): maximum
                    except OSError: span = 32767
                nodes[node[1]], fds[fd] = fd, PadNav(span) if span is not None else None
        pads = [p for p in fds.values() if p]
        wait = min([max(0.01, p.due - now) for p in pads if p.dir] + [2])
        for fd in select.select(list(fds), [], [], wait)[0]:
            try: data = os.read(fd, size * 32)
            except BlockingIOError: continue
            except OSError:
                os.close(fd); del fds[fd]; nodes = {n: f for n, f in nodes.items() if f != fd}; continue
            for start in range(0, len(data) - size + 1, size):
                _, _, kind, code, value = struct.unpack('llHHi', data[start:start + size])
                if fds[fd]: nav(fds[fd].event(kind, code, value, time.time()))
                if kind != 1 or value == 0: continue
                if code in (114, 115):  # volume down / up, repeats while held
                    vol = settings().get('vol')
                    if vol is not None:
                        tandem.publish('settings', {'settings': change('vol', vol + (5 if code == 115 else -5)), 'osd': 'vol'})
                elif value == 1 and code == 184:  # Back
                    if not tandem.run or tandem.run.get('paused'): tandem.publish('key', {'a': 'back'})
                elif value == 1 and code in (185, 316):  # Home: freeze the game and show Tandem; again: back into the game
                    if tandem.run and tandem.run.get('paused'): tandem.resume()
                    elif tandem.run:
                        result = tandem.pause()
                        if 'error' in result: tandem.publish('toast', {'text': result['error']})
                    else: tandem.publish('key', {'a': 'home'})
        for pad in pads: nav(pad.tick(time.time()))


def rom_roots(extra):
    found = [p for p in extra if os.path.isdir(p)]
    for pattern in (str(HOME / 'ROMs'), '/run/media/*/*/ROMs', '/run/media/*/ROMs', '/media/*/*/ROMs'):
        found += [p for p in sorted(glob.glob(pattern)) if p not in found]
    return found


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
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(tandem))
    server.daemon_threads = True
    threading.Thread(target=watch_buttons, args=(tandem,), daemon=True).start()
    def look_for_update():  # once a day, and only where the owner entered a source: says so, installs nothing by itself
        while True:
            time.sleep(120)
            found = self_update()
            if found.get('new'): tandem.publish('toast', {'text': found['text'] + ' Installieren: Einstellungsseite › Gerät.'})
            time.sleep(86400)
    threading.Thread(target=look_for_update, daemon=True).start()
    if not args.dry_run: threading.Thread(target=hide_steam, args=(tandem,), daemon=True).start()
    new_pin()
    if not args.dry_run: kill_stale()
    if any(g.get('inst') == 'load' for g in library.games.values()): (tandem.steam_watch(), threading.Thread(target=steam_background, daemon=True).start())  # a download from before goes on
    try:
        pair = ThreadingHTTPServer(('0.0.0.0', args.port + 1), pair_handler(tandem))
        pair.daemon_threads = True
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
