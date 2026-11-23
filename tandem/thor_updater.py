#!/usr/bin/env python3
"""Integrated Update & Automatic Game Companion Service for Toravo Tandem (Obtainium-class & beyond).

Keeps the entire AYN Thor software & companion ecosystem up to date automatically while idle:
1. Automatic Companion Provisioner (`sync_all_companions`):
   - Steam in-game companion mods (`harmssi/thor-ffix` -> FF IX Memoria `Assembly-CSharp.dll` + `[ThorStatus]`,
     `harmssi/thor-pipboy` -> Fallout 4 `ThorPipBoy.dll` + `ThorPipBoy.ini`,
     `harmssi/thor-p5r` -> Persona 5 Royal Steam `steam_api64.dll`) with SHA256SUMS verification & `.prev` backup.
   - GB / GBC / GBA companion packs (`khumam/gba-duo-companions`, multi-region & ROM-hack matching) + RetroArch UDP enable.
   - Dual-screen DS / 3DS / Wii U layout provisioning & native port companion status.
2. Obtainium-Superior Emulator, Core & System Updater:
   - Tracks direct upstream GitHub / Forgejo ARM64 AppImage releases (`DuckStation`, `ARMSX2`, `Azahar Enhanced`,
     `melonDS`, `Cemu`, `Eden`, `RPCS3`, `Vita3K`, `xemu` + optional user-defined custom repos in `updater-feeds.json`).
   - Compares real on-disk SHA-256 digests against GitHub release asset digests (works even for rolling tags like
     `drm-leasing` or `Nightly` without redundant re-downloads!), verifies ELF headers & checksums, keeps `.prev`
     1-tap rollback backups, and re-applies `controls.apply()` after updates.
   - Checks & updates Flatpak emulators (`RetroArch`, `Dolphin`, `PPSSPP`, `Flycast`, `Ymir`, `ScummVM`, `mpv`) and
     auto-fetches missing Libretro ARM64 cores for any ROM folders present on the device.
"""
import argparse
import glob
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'tandem'
UPD_STATE_FILE = STATE / 'updater-state.json'
CUSTOM_FEEDS_FILE = CONFIG_DIR / 'updater-feeds.json'
UA = 'Toravo-Tandem-Updater/0.6 (+https://github.com/harmssi/thor-tandem)'

_LOCK = threading.Lock()
_SHA_MEMO = {}  # path -> (mtime_ns, size, sha256)
_JOB = {
    'running': False,
    'step': '',
    'error': '',
    'result': '',
    'done_at': 0,
}

# Upstream ARM64 AppImage feeds (pre-configured out of the box; no manual Obtainium regex setup required)
APPIMAGE_FEEDS = (
    {
        'id': 'duckstation',
        'name': 'DuckStation (PS1)',
        'api': 'https://api.github.com/repos/stenzek/duckstation/releases?per_page=8',
        'asset': r'^DuckStation-arm64\.AppImage$',
        'file': 'DuckStation.AppImage',
        'systems': ('psx',),
    },
    {
        'id': 'armsx2',
        'name': 'ARMSX2 (PS2)',
        'api': 'https://api.github.com/repos/ARMSX2/ARMSX2/releases?per_page=10',
        'asset': r'Linux-arm64-4K-pages\.AppImage$',
        'file': 'ARMSX2.AppImage',
        'systems': ('ps2',),
    },
    {
        'id': 'azahar',
        'name': 'Azahar Enhanced (3DS Dual-Screen)',
        'api': 'https://api.github.com/repos/virtudude/Azahar-AppImage-Enhanced/releases/tags/drm-leasing',
        'asset': r'^Azahar-[0-9a-f]{6,}-anylinux-aarch64\.AppImage$',
        'file': 'Azahar-Enhanced.AppImage',
        'systems': ('n3ds',),
    },
    {
        'id': 'melonds',
        'name': 'melonDS (DS Dual-Screen)',
        'api': 'https://api.github.com/repos/virtudude/melonDS/releases/tags/drm-leasing',
        'asset': r'^melonDS-aarch64\.AppImage$',
        'file': 'melonDS.AppImage',
        'systems': ('nds',),
    },
    {
        'id': 'cemu',
        'name': 'Cemu (Wii U)',
        'api': 'https://api.github.com/repos/pkgforge-dev/Cemu-AppImage-Enhanced/releases?per_page=10',
        'asset': r'^Cemu_Nightly-.*-anylinux-aarch64\.AppImage$',
        'file': 'Cemu.AppImage',
        'systems': ('wiiu',),
    },
    {
        'id': 'eden',
        'name': 'Eden (Switch)',
        'api': 'https://git.eden-emu.dev/api/v1/repos/eden-emu/eden/releases?limit=1',
        'asset': r'^Eden-Linux-v[\d.]+-aarch64-gcc-standard\.AppImage$',
        'file': 'Eden.AppImage',
        'systems': ('switch',),
    },
    {
        'id': 'rpcs3',
        'name': 'RPCS3 (PS3)',
        'api': 'https://api.github.com/repos/RPCS3/rpcs3-binaries-linux-arm64/releases?per_page=10',
        'asset': r'^rpcs3-v[0-9].*_linux_aarch64\.AppImage$',
        'file': 'rpcs3.AppImage',
        'systems': ('ps3',),
        'optional': True,
    },
    {
        'id': 'vita3k',
        'name': 'Vita3K (PS Vita)',
        'api': 'https://api.github.com/repos/Vita3K/Vita3K/releases?per_page=8',
        'asset': r'^Vita3K-aarch64\.AppImage$',
        'file': 'Vita3K.AppImage',
        'systems': ('psvita',),
        'optional': True,
    },
    {
        'id': 'xemu',
        'name': 'xemu (Xbox)',
        'api': 'https://api.github.com/repos/xemu-project/xemu/releases?per_page=8',
        'asset': r'^xemu-[0-9][0-9.]*-[0-9]+-g[0-9a-f]+-aarch64\.AppImage$',
        'file': 'xemu.AppImage',
        'systems': ('xbox',),
        'optional': True,
    },
)

FLATPAK_TRACKED = (
    ('org.libretro.RetroArch', 'RetroArch'),
    ('org.DolphinEmu.dolphin-emu', 'Dolphin (GC/Wii)'),
    ('org.ppsspp.PPSSPP', 'PPSSPP (PSP)'),
    ('org.flycast.Flycast', 'Flycast (Dreamcast)'),
    ('io.github.strikerx3.ymir', 'Ymir (Saturn)'),
    ('org.scummvm.ScummVM', 'ScummVM'),
    ('io.mpv.Mpv', 'mpv Media'),
)

# Preferred Libretro core per ROM folder for automatic core provisioning
SYSTEM_LIBRETRO_CORE = {
    'gb': 'gambatte',
    'gbc': 'gambatte',
    'gba': 'mgba',
    'nes': 'nestopia',
    'famicom': 'nestopia',
    'fds': 'nestopia',
    'snes': 'snes9x',
    'sfc': 'snes9x',
    'n64': 'mupen64plus_next',
    'genesis': 'genesis_plus_gx',
    'megadrive': 'genesis_plus_gx',
    'mastersystem': 'genesis_plus_gx',
    'gamegear': 'genesis_plus_gx',
    'segacd': 'genesis_plus_gx',
    'sega32x': 'picodrive',
    'pcengine': 'mednafen_pce_fast',
    'pcenginecd': 'mednafen_pce_fast',
    'neogeo': 'fbneo',
    'arcade': 'fbneo',
    'fbneo': 'fbneo',
    'cps1': 'fbneo',
    'cps2': 'fbneo',
    'cps3': 'fbneo',
    'ngp': 'mednafen_ngp',
    'ngpc': 'mednafen_ngp',
    'wonderswan': 'mednafen_wswan',
    'wonderswancolor': 'mednafen_wswan',
    'atari2600': 'stella',
    'atarilynx': 'handy',
    'doom': 'prboom',
    'dos': 'dosbox_pure',
    'pico8': 'fake08',
}

# Steam games with official downloadable Thor bottom-screen companion plugins
STEAM_COMPANIONS = (
    {
        'id': 'ffix',
        'title': 'FINAL FANTASY IX · Memoria-Begleiter',
        'appid': '377840',
        'folder_names': ('FINAL FANTASY IX',),
        'repo': 'harmssi/thor-ffix',
        'target_rel': 'x64/FF9_Data/Managed/Assembly-CSharp.dll',
        'asset_name': 'Assembly-CSharp.dll',
        'requires_any': ('Memoria.ini', 'Ae.Dns.Client.dll'),
        'requires_note': 'Memoria-Mod zuerst im Spielordner einrichten',
    },
    {
        'id': 'pipboy',
        'title': 'Fallout 4 · Thor Pip-Boy',
        'appid': '377160',
        'folder_names': ('Fallout 4',),
        'repo': 'harmssi/thor-pipboy',
        'target_rel': 'Data/F4SE/Plugins/ThorPipBoy.dll',
        'asset_name': 'ThorPipBoy.dll',
        'extra_ini': ('ThorPipBoy.ini', 'Data/F4SE/Plugins/ThorPipBoy.ini'),
    },
    {
        'id': 'p5r_steam',
        'title': 'Persona 5 Royal (Steam) · Phantom-Deck',
        'appid': '1687950',
        'folder_names': ('P5R', 'Persona 5 Royal'),
        'repo': 'harmssi/thor-p5r',
        'target_rel': 'steam_api64.dll',
        'asset_name': 'steam_api64.dll',
    },
)

LIBRETRO_BUILDBOT = 'https://buildbot.libretro.com/nightly/linux/aarch64/latest'


def job_state():
    return dict(_JOB)


def load_state():
    try:
        return json.loads(UPD_STATE_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_state(data):
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = UPD_STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, UPD_STATE_FILE)


def load_custom_feeds():
    try:
        raw = json.loads(CUSTOM_FEEDS_FILE.read_text(encoding='utf-8'))
        if not isinstance(raw, list):
            return []
    except (OSError, ValueError):
        return []
    out = []
    for item in raw[:24]:
        if not isinstance(item, dict):
            continue
        fid = re.sub(r'[^a-z0-9_-]', '', str(item.get('id') or '').lower())[:32]
        name = str(item.get('name') or fid).strip()[:60]
        repo_or_url = str(item.get('api') or item.get('repo') or '').strip()
        asset = str(item.get('asset') or r'.*aarch64.*\.AppImage$|.*arm64.*\.AppImage$').strip()
        fname = os.path.basename(str(item.get('file') or f'{fid}.AppImage').strip())
        if not fid or not repo_or_url or not fname.endswith('.AppImage'):
            continue
        if re.fullmatch(r'[\w.-]+/[\w.-]+', repo_or_url):
            api = f'https://api.github.com/repos/{repo_or_url}/releases?per_page=8'
        elif repo_or_url.startswith('https://'):
            api = repo_or_url
        else:
            continue
        out.append({'id': 'custom-' + fid, 'name': name, 'api': api, 'asset': asset, 'file': fname, 'systems': (), 'custom': True})
    return out


def save_custom_feed(repo, name='', asset_regex='', filename=''):
    repo = str(repo or '').strip()
    m = re.search(r'(?:github\.com/)?([\w.-]+/[\w.-]+)', repo)
    if not m:
        return {'error': 'Bitte ein GitHub-Repository im Format Besitzer/Projekt angeben.'}
    slug = m.group(1).removesuffix('.git')
    fid = re.sub(r'[^a-z0-9_-]', '-', slug.split('/')[-1].lower()).strip('-')[:28] or 'app'
    cur = [x for x in (json.loads(CUSTOM_FEEDS_FILE.read_text(encoding='utf-8')) if CUSTOM_FEEDS_FILE.is_file() else [])
           if isinstance(x, dict) and x.get('id') != fid]
    cur.append({
        'id': fid,
        'name': (name or slug.split('/')[-1]).strip()[:50],
        'repo': slug,
        'asset': (asset_regex or r'.*(?:aarch64|arm64).*\.AppImage$').strip(),
        'file': os.path.basename(filename.strip()) if filename.strip().endswith('.AppImage') else f'{slug.split("/")[-1]}.AppImage',
    })
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_FEEDS_FILE.write_text(json.dumps(cur, indent=2, ensure_ascii=False), encoding='utf-8')
    return {'ok': True, 'text': f'Update-Quelle {slug} hinzugefügt.'}


def remove_custom_feed(feed_id):
    fid = str(feed_id or '').removeprefix('custom-')
    if not CUSTOM_FEEDS_FILE.is_file():
        return {'ok': True}
    try:
        cur = [x for x in json.loads(CUSTOM_FEEDS_FILE.read_text(encoding='utf-8')) if isinstance(x, dict) and x.get('id') != fid]
        CUSTOM_FEEDS_FILE.write_text(json.dumps(cur, indent=2, ensure_ascii=False), encoding='utf-8')
    except (OSError, ValueError):
        pass
    return {'ok': True, 'text': 'Update-Quelle entfernt.'}


def all_appimage_feeds():
    return list(APPIMAGE_FEEDS) + load_custom_feeds()


def sha256_file(path):
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return ''
    key = str(p)
    cached = _SHA_MEMO.get(key)
    if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return cached[2]
    h = hashlib.sha256()
    try:
        with p.open('rb') as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
    except OSError:
        return ''
    digest = h.hexdigest()
    _SHA_MEMO[key] = (st.st_mtime_ns, st.st_size, digest)
    return digest


def _http_json(url, opener=None, timeout=15):
    open_fn = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with open_fn(req, timeout=timeout) as r:
        return json.loads(r.read(2 << 20))


def _http_bytes(url, opener=None, timeout=180, max_bytes=350 << 20):
    open_fn = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with open_fn(req, timeout=timeout) as r:
        return r.read(max_bytes)


def parse_sha256sums(text):
    """Parse standard `SHA256SUMS` lines (`<64-hex>  <filename>`) -> `{basename: hex}`."""
    out = {}
    for line in str(text or '').splitlines():
        m = re.match(r'^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$', line)
        if m:
            out[os.path.basename(m.group(2).strip())] = m.group(1).lower()
    return out


# ---- AppImage Release Inspection, Update & 1-Tap Rollback --------------------------------------------------------------
def resolve_feed_release(feed, opener=None):
    """Query a GitHub / Forgejo releases endpoint (list OR single tag object) and find the first release with a matching
    ARM64 AppImage asset. Returns `{'tag', 'asset_name', 'url', 'size', 'sha256', 'updated_at'}` or None."""
    data = _http_json(feed['api'], opener=opener)
    releases = [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])
    rx = re.compile(feed['asset'], re.I)
    for rel in releases:
        if not isinstance(rel, dict) or rel.get('draft'):
            continue
        for a in rel.get('assets') or ():
            aname = str(a.get('name') or '')
            dl = str(a.get('browser_download_url') or '')
            if rx.search(aname) and dl.startswith('https://'):
                dig = str(a.get('digest') or '')
                sha = dig.split(':', 1)[1].lower() if dig.startswith('sha256:') and len(dig) == 71 else ''
                return {
                    'tag': str(rel.get('tag_name') or rel.get('name') or 'latest'),
                    'asset_name': aname,
                    'url': dl,
                    'size': int(a.get('size') or 0),
                    'sha256': sha,
                    'updated_at': str(a.get('updated_at') or rel.get('published_at') or ''),
                }
    return None


def check_appimages(apps_dir=None, owned_systems=None, opener=None, network=True):
    """Inspect all tracked AppImage emulators (local state + optional upstream check)."""
    adir = Path(apps_dir) if apps_dir else (HOME / 'Applications')
    st = load_state()
    rec_map = st.setdefault('appimages', {})
    owned = set(owned_systems or ())
    results = []

    for feed in all_appimage_feeds():
        fid = feed['id']
        fpath = adir / feed['file']
        prev_path = adir / (feed['file'] + '.prev')
        installed = fpath.is_file()
        if feed.get('optional') and not installed and not (set(feed.get('systems') or ()) & owned) and not feed.get('custom'):
            continue
        local_sha = sha256_file(fpath) if installed else ''
        local_size = fpath.stat().st_size if installed else 0
        rec = dict(rec_map.get(fid) or {})

        remote = rec.get('remote')
        if network:
            try:
                remote = resolve_feed_release(feed, opener=opener)
                if remote:
                    rec['remote'] = remote
            except Exception:
                pass

        cur_ver = rec.get('installed_tag') or ('installiert' if installed else '')
        update_avail = False
        if remote:
            r_sha = remote.get('sha256') or ''
            r_tag = remote.get('tag') or ''
            if installed:
                if r_sha and local_sha:
                    if r_sha == local_sha:
                        cur_ver = r_tag
                        rec['installed_tag'] = r_tag
                        rec['installed_sha'] = local_sha
                    else:
                        update_avail = True
                elif rec.get('installed_sha') == local_sha and rec.get('installed_url') == remote.get('url') and rec.get('installed_updated') == remote.get('updated_at'):
                    cur_ver = rec.get('installed_tag') or r_tag
                elif remote.get('size') and local_size == remote['size'] and not rec.get('installed_tag'):
                    # Pre-existing AppImage matches exact upstream byte size on first check
                    cur_ver = r_tag
                    rec['installed_tag'] = r_tag
                    rec['installed_sha'] = local_sha
                    rec['installed_url'] = remote.get('url', '')
                    rec['installed_updated'] = remote.get('updated_at', '')
                else:
                    update_avail = True
            rec_map[fid] = rec

        results.append({
            'id': fid,
            'name': feed['name'],
            'file': feed['file'],
            'installed': installed,
            'has_rollback': prev_path.is_file(),
            'current_version': cur_ver,
            'latest_version': (remote or {}).get('tag', ''),
            'update_available': bool(installed and update_avail),
            'can_install': bool(not installed and remote),
            'custom': bool(feed.get('custom')),
        })

    if network:
        st['last_check'] = int(time.time())
        save_state(st)
    return results


def install_or_update_appimage(feed_id, apps_dir=None, opener=None):
    """Download, verify (ELF + SHA-256), backup `.prev`, and atomically install an ARM64 AppImage."""
    feed = next((f for f in all_appimage_feeds() if f['id'] == feed_id), None)
    if not feed:
        return {'error': f'Unbekannte App-Quelle: {feed_id}'}
    adir = Path(apps_dir) if apps_dir else (HOME / 'Applications')
    adir.mkdir(parents=True, exist_ok=True)
    try:
        remote = resolve_feed_release(feed, opener=opener)
    except Exception as e:
        return {'error': f'{feed["name"]}: Release-Abfrage fehlgeschlagen ({e}).'}
    if not remote:
        return {'error': f'{feed["name"]}: Kein passendes ARM64-Paket gefunden.'}

    target = adir / feed['file']
    if target.is_file() and remote.get('sha256') and sha256_file(target) == remote['sha256']:
        return {'ok': True, 'unchanged': True, 'version': remote['tag'], 'text': f'{feed["name"]} ({remote["tag"]}) ist bereits aktuell.'}

    tmp = adir / f'.part-{feed["file"]}'
    try:
        blob = _http_bytes(remote['url'], opener=opener, timeout=240)
        if len(blob) < 4096 or blob[:4] != b'\x7fELF':
            return {'error': f'{feed["name"]}: Ungültiges AppImage empfangen.'}
        got_sha = hashlib.sha256(blob).hexdigest()
        if remote.get('sha256') and got_sha != remote['sha256']:
            return {'error': f'{feed["name"]}: Prüfsumme stimmt nicht – abgebrochen.'}
        tmp.write_bytes(blob)
        os.chmod(tmp, 0o755)
        if target.is_file():
            prev = adir / (feed['file'] + '.prev')
            shutil.copy2(target, prev)
        os.replace(tmp, target)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        return {'error': f'{feed["name"]}: Schreibfehler ({e}).'}

    # Re-apply unified gamepad bindings so an updated emulator never loses Thor's button mapping
    try:
        import controls
        controls.apply()
    except Exception:
        pass

    st = load_state()
    st.setdefault('appimages', {})[feed_id] = {
        'installed_tag': remote['tag'],
        'installed_sha': got_sha,
        'installed_url': remote['url'],
        'installed_updated': remote.get('updated_at', ''),
        'updated_at': int(time.time()),
        'remote': remote,
    }
    save_state(st)
    return {'ok': True, 'version': remote['tag'], 'text': f'{feed["name"]} auf {remote["tag"]} aktualisiert.'}


def rollback_appimage(feed_id, apps_dir=None):
    """1-Tap Rollback: restore `<AppImage>.prev` if an upstream emulator update introduced a regression."""
    feed = next((f for f in all_appimage_feeds() if f['id'] == feed_id), None)
    if not feed:
        return {'error': 'Unbekannter Emulator.'}
    adir = Path(apps_dir) if apps_dir else (HOME / 'Applications')
    target = adir / feed['file']
    prev = adir / (feed['file'] + '.prev')
    if not prev.is_file():
        return {'error': f'Keine vorherige Version für {feed["name"]} vorhanden.'}
    tmp = adir / f'.rb-{feed["file"]}'
    shutil.copy2(prev, tmp)
    os.chmod(tmp, 0o755)
    os.replace(tmp, target)
    return {'ok': True, 'text': f'Vorherige Version von {feed["name"]} wiederhergestellt.'}


_FP_CACHE = {'at': 0.0, 'installed': {}}


# ---- Flatpak & Libretro Core Maintenance -------------------------------------------------------------------------------
def flatpak_status(check_remote=False):
    if not shutil.which('flatpak'):
        return {'supported': False, 'installed': [], 'updates': []}
    now = time.time()
    if check_remote or now - _FP_CACHE['at'] > 45:
        inst = {}
        for scope in ('--system', '--user'):
            try:
                r = subprocess.run(['flatpak', 'list', scope, '--app', '--columns=application,version'],
                                   capture_output=True, text=True, timeout=6)
                for ln in r.stdout.splitlines():
                    parts = ln.split('\t')
                    if parts and parts[0].strip():
                        inst[parts[0].strip()] = (parts[1].strip() if len(parts) > 1 else '')
            except Exception:
                pass
        _FP_CACHE.update(at=now, installed=inst)
    installed = _FP_CACHE['installed']
    st = load_state()
    updates = set(st.get('flatpak_updates') or ())
    if check_remote:
        updates = set()
        for scope in ('--system', '--user'):
            try:
                r = subprocess.run(['flatpak', 'remote-ls', scope, '--updates', '--app', '--columns=application'],
                                   capture_output=True, text=True, timeout=15)
                for ln in r.stdout.splitlines():
                    if ln.strip():
                        updates.add(ln.strip())
            except Exception:
                pass
        st['flatpak_updates'] = sorted(updates)
        save_state(st)
    tracked = [{
        'ref': ref,
        'name': label,
        'installed': ref in installed,
        'version': installed.get(ref, ''),
        'update_available': ref in updates,
    } for ref, label in FLATPAK_TRACKED if ref in installed or ref in updates]
    return {'supported': True, 'installed': tracked, 'updates': sorted(updates)}


def update_flatpaks():
    if not shutil.which('flatpak'):
        return {'ok': False, 'text': 'Flatpak nicht vorhanden.'}
    updated = 0
    for scope in ('--user', '--system'):
        try:
            r = subprocess.run(['flatpak', 'update', scope, '--noninteractive', '-y'],
                               capture_output=True, text=True, timeout=600)
            if r.returncode == 0 and ('Updating' in r.stdout or 'Aktualisierung' in r.stdout or 'Installing' in r.stdout):
                updated += 1
        except Exception:
            pass
    _FP_CACHE['at'] = 0.0
    st = load_state()
    st['flatpak_updates'] = []
    save_state(st)
    return {'ok': True, 'updated': updated, 'text': 'Flatpak-Pakete aktualisiert.' if updated else 'Alle Flatpak-Emulatoren sind aktuell.'}


def sync_retroarch_cores(owned_systems, home=None, opener=None):
    """Ensure every ROM system folder with games has its preferred Libretro ARM64 core installed."""
    h = Path(home) if home else HOME
    cores_dir = h / '.var/app/org.libretro.RetroArch/config/retroarch/cores'
    if not cores_dir.parent.is_dir():
        return []
    cores_dir.mkdir(parents=True, exist_ok=True)
    needed = sorted({SYSTEM_LIBRETRO_CORE[s] for s in (owned_systems or ()) if s in SYSTEM_LIBRETRO_CORE})
    installed_now = []
    for core in needed:
        so_file = cores_dir / f'{core}_libretro.so'
        if so_file.is_file():
            continue
        try:
            raw_zip = _http_bytes(f'{LIBRETRO_BUILDBOT}/{core}_libretro.so.zip', opener=opener, timeout=60, max_bytes=60 << 20)
            with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
                member = next((m for m in zf.namelist() if m.endswith('.so')), None)
                if not member:
                    continue
                data = zf.read(member)
                if data[:4] != b'\x7fELF':
                    continue
                tmp = cores_dir / f'.part-{core}.so'
                tmp.write_bytes(data)
                os.chmod(tmp, 0o755)
                os.replace(tmp, so_file)
                installed_now.append(core)
        except Exception:
            continue
    return installed_now


# ---- Automatic Game Companion Discovery, Installation & Updates --------------------------------------------------------
def _steam_common_dirs(home=None, roots=()):
    h = Path(home) if home else HOME
    dirs = []
    candidates = [h / '.local/share/Steam/steamapps/common']
    vdf = h / '.local/share/Steam/steamapps/libraryfolders.vdf'
    if vdf.is_file():
        for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(errors='ignore')):
            candidates.append(Path(m.group(1)) / 'steamapps/common')
    for root in (roots or ()):
        base = Path(root).parent
        candidates.append(base / 'SteamLibrary/steamapps/common')
        candidates.append(base / 'PC-Games/Steam')
    for pat in ('/run/media/*/*/SteamLibrary/steamapps/common', '/run/media/*/*/PC-Games/Steam'):
        for g in sorted(glob.glob(pat)):
            candidates.append(Path(g))
    seen = set()
    for d in candidates:
        if d.is_dir():
            try:
                rp = d.resolve()
            except OSError:
                rp = d
            if rp not in seen:
                seen.add(rp)
                dirs.append(d)
    return dirs


def _ensure_memoria_thor_status(ffix_dir):
    ini = Path(ffix_dir) / 'Memoria.ini'
    if not ini.is_file():
        return False
    txt = ini.read_text(encoding='utf-8', errors='replace')
    if '[ThorStatus]' in txt:
        if re.search(r'\[ThorStatus\][^\[]*Enabled\s*=\s*1', txt, re.S):
            return True
        txt = re.sub(r'(\[ThorStatus\][^\[]*?Enabled\s*=\s*)\d+', r'\g<1>1', txt, count=1, flags=re.S)
    else:
        nl = '\r\n' if '\r\n' in txt else '\n'
        txt = txt.rstrip() + f'{nl}{nl}[ThorStatus]{nl}Enabled = 1{nl}BindAddress = 127.0.0.1{nl}Port = 8766{nl}IntervalMs = 150{nl}'
    tmp = ini.with_suffix('.ini.tmp')
    tmp.write_text(txt, encoding='utf-8')
    os.replace(tmp, ini)
    return True


def sync_steam_companions(home=None, roots=(), apply_updates=True, only_appid='', opener=None):
    """Detect installed Steam games that have a Thor companion plugin (`FF IX`, `Fallout 4`, `Persona 5 Royal`),
    verify SHA256SUMS against the latest GitHub release, and automatically install or update the companion DLL/config!"""
    common_dirs = _steam_common_dirs(home=home, roots=roots)
    st = load_state()
    comp_state = st.setdefault('steam_companions', {})
    found = []
    updated = []

    for spec in STEAM_COMPANIONS:
        if only_appid and str(only_appid) != spec['appid']:
            continue
        game_dir = None
        for cdir in common_dirs:
            acf = cdir.parent / f'appmanifest_{spec["appid"]}.acf'
            extra_names = []
            if acf.is_file():
                m_dir = re.search(r'"installdir"\s+"([^"]+)"', acf.read_text(errors='ignore'))
                if m_dir:
                    extra_names.append(m_dir.group(1))
            for fname in tuple(extra_names) + spec['folder_names']:
                cand = cdir / fname
                if cand.is_dir():
                    game_dir = cand
                    break
            if game_dir:
                break
        if not game_dir:
            continue

        cid = spec['id']
        if spec.get('requires_any') and not any((game_dir / req).exists() for req in spec['requires_any']):
            found.append({
                'id': cid,
                'title': spec['title'],
                'installed': False,
                'status': spec.get('requires_note', 'Voraussetzung fehlt'),
                'version': '',
                'update_available': False,
            })
            continue

        target = game_dir / spec['target_rel']
        local_sha = sha256_file(target) if target.is_file() else ''
        rec = dict(comp_state.get(cid) or {})

        rel_tag = rec.get('latest_tag', '')
        expected_sha = rec.get('expected_sha', '')
        asset_url = ''
        extra_url = ''
        try:
            rel = _http_json(f'https://api.github.com/repos/{spec["repo"]}/releases/latest', opener=opener)
            if isinstance(rel, dict):
                rel_tag = str(rel.get('tag_name') or '')
                assets = {str(a.get('name') or ''): str(a.get('browser_download_url') or '') for a in (rel.get('assets') or ())}
                asset_url = assets.get(spec['asset_name'], '')
                if spec.get('extra_ini'):
                    extra_url = assets.get(spec['extra_ini'][0], '')
                if 'SHA256SUMS' in assets:
                    sums_raw = _http_bytes(assets['SHA256SUMS'], opener=opener, timeout=20, max_bytes=262144).decode('utf-8', errors='replace')
                    expected_sha = parse_sha256sums(sums_raw).get(spec['asset_name'], '')
        except Exception:
            pass

        needs_install = bool(asset_url and expected_sha and local_sha != expected_sha)
        if not target.is_file() and asset_url and not expected_sha:
            needs_install = True

        status_txt = 'aktiv'
        if needs_install and apply_updates:
            try:
                blob = _http_bytes(asset_url, opener=opener, timeout=120, max_bytes=64 << 20)
                got_sha = hashlib.sha256(blob).hexdigest()
                if expected_sha and got_sha != expected_sha:
                    status_txt = 'Prüfsummenfehler'
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.is_file():
                        orig_bak = target.with_name(target.name + '.thor-bak')
                        if not orig_bak.exists():
                            shutil.copy2(target, orig_bak)
                        shutil.copy2(target, target.with_name(target.name + '.prev'))
                    tmp = target.with_name('.part-' + target.name)
                    tmp.write_bytes(blob)
                    os.replace(tmp, target)
                    local_sha = got_sha
                    needs_install = False
                    if spec.get('extra_ini') and extra_url:
                        ini_dest = game_dir / spec['extra_ini'][1]
                        if not ini_dest.is_file():
                            ini_blob = _http_bytes(extra_url, opener=opener, timeout=20, max_bytes=65536)
                            ini_dest.write_bytes(ini_blob)
                    if cid == 'ffix':
                        _ensure_memoria_thor_status(game_dir)
                    updated.append(f'{spec["title"]} ({rel_tag})')
                    rec.update(installed_tag=rel_tag, installed_sha=got_sha, updated_at=int(time.time()))
            except Exception as e:
                status_txt = f'Fehler: {e}'
        elif cid == 'ffix' and target.is_file():
            _ensure_memoria_thor_status(game_dir)

        if expected_sha and local_sha == expected_sha and rel_tag:
            rec['installed_tag'] = rel_tag
            rec['installed_sha'] = local_sha
        rec.update(latest_tag=rel_tag, expected_sha=expected_sha)
        comp_state[cid] = rec

        found.append({
            'id': cid,
            'title': spec['title'],
            'installed': target.is_file() and (not expected_sha or local_sha == expected_sha),
            'version': rec.get('installed_tag') or (rel_tag if local_sha and local_sha == expected_sha else ('installiert' if target.is_file() else '')),
            'latest_version': rel_tag,
            'update_available': bool(needs_install),
            'status': status_txt,
        })

    save_state(st)
    return {'items': found, 'updated': updated}


def ensure_retroarch_udp_companion(home=None):
    """Ensure RetroArch allows `READ_CORE_MEMORY` on `127.0.0.1:55355` so all GB/GBC/GBA live memory companions work out of the box."""
    h = Path(home) if home else HOME
    cfg = h / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg'
    if not cfg.is_file():
        return False
    txt = cfg.read_text(encoding='utf-8', errors='replace')
    if re.search(r'^\s*network_cmd_enable\s*=\s*"true"', txt, re.M):
        return True
    if re.search(r'^\s*network_cmd_enable\s*=', txt, re.M):
        txt = re.sub(r'^\s*network_cmd_enable\s*=.*$', 'network_cmd_enable = "true"', txt, count=1, flags=re.M)
    else:
        txt = txt.rstrip() + '\nnetwork_cmd_enable = "true"\nnetwork_cmd_port = "55355"\n'
    tmp = cfg.with_suffix('.cfg.tmp')
    tmp.write_text(txt, encoding='utf-8')
    os.replace(tmp, cfg)
    return True


def sync_all_companions(games_list, rom_id_fn, roots=(), home=None, cfg_dir=None, apply_updates=True, force_catalog=False, opener=None):
    """Single-call Automatic Companion Provisioner across ALL game ecosystems on the Thor:
    1) Steam Companion Plugins (`FF IX`, `Fallout 4`, `Persona 5 Royal`)
    2) GB / GBC / GBA Companion Packs (`khumam/gba-duo-companions`) + RetroArch UDP memory bridge
    3) Dual-Screen DS / 3DS / Wii U emulator layouts (`melonDS`, `Azahar`, `Cemu`)
    4) Installed Native Port companions (`Half-Life`, `Age of Kings`, `Red Alert 2`, `C&C`, `Heroes III`, `KKnD 2`, `Diablo II`)
    """
    import companion
    h = Path(home) if home else HOME
    cdir = Path(cfg_dir) if cfg_dir else CONFIG_DIR

    # 1) Steam companions
    steam_res = sync_steam_companions(home=h, roots=roots, apply_updates=apply_updates, opener=opener)

    # 2) GB/GBC/GBA companion packs + RetroArch UDP bridge
    ensure_retroarch_udp_companion(home=h)
    gba_res = {'installed': [], 'updated': [], 'owned_roms': 0}
    if apply_updates:
        gba_res = companion.sync_owned_gba_packs(games_list, rom_id_fn, cfg_dir=cdir, force_catalog=force_catalog, opener=opener)
    shelf = companion.gba_shelf_status(games_list, rom_id_fn, cfg_dir=cdir)

    # 3) Dual-screen DS / 3DS layout provisioning when those games exist
    owned_sys = {g.get('s') for g in (games_list or ()) if isinstance(g, dict)}
    dual_ready = []
    if apply_updates:
        if 'nds' in owned_sys:
            companion.setup_dual_emu('nds', 'melonDS')
            dual_ready.append('Nintendo DS (melonDS)')
        if 'n3ds' in owned_sys:
            companion.setup_dual_emu('n3ds', 'Azahar')
            dual_ready.append('Nintendo 3DS (Azahar)')

    # 4) Native ports & built-in companions summary
    ports_dir = Path(os.environ.get('XDG_DATA_HOME', h / '.local/share')) / 'tandem-ports'
    installed_ports = sorted(p.name for p in ports_dir.iterdir() if (p / 'run').is_file()) if ports_dir.is_dir() else []

    changes = list(steam_res.get('updated') or [])
    for pid in (gba_res.get('installed') or []):
        changes.append(f'GBA-Paket {pid}')
    for pid in (gba_res.get('updated') or []):
        changes.append(f'GBA-Paket {pid} aktualisiert')

    summary = {
        'steam': steam_res['items'],
        'gba_installed_packs': len(shelf.get('installed') or []),
        'gba_matched_games': len(shelf.get('games') or []),
        'ports_ready': installed_ports,
        'dual_screen': dual_ready,
        'universal_active': True,
        'changes': changes,
        'checked_at': int(time.time()),
    }
    st = load_state()
    st['companions'] = summary
    save_state(st)
    return summary


# ---- Unified Overview & One-Click "Update Everything" Job Runner -------------------------------------------------------
def overview(games_list=(), rom_id_fn=None, roots=(), self_version='0', self_new=''):
    st = load_state()
    owned_sys = {g.get('s') for g in (games_list or ()) if isinstance(g, dict)}
    apps = check_appimages(owned_systems=owned_sys, network=False)
    fp = flatpak_status()
    comp = st.get('companions')
    if not comp and rom_id_fn is not None:
        import companion
        shelf = companion.gba_shelf_status(games_list, rom_id_fn, cfg_dir=CONFIG_DIR)
        comp = {
            'steam': (st.get('steam_companions') and [
                {'id': k, 'title': k, 'installed': bool(v.get('installed_sha')), 'version': v.get('installed_tag', ''), 'update_available': False}
                for k, v in st['steam_companions'].items()
            ]) or [],
            'gba_installed_packs': len(shelf.get('installed') or []),
            'gba_matched_games': len(shelf.get('games') or []),
            'ports_ready': [],
            'universal_active': True,
        }
    pending_apps = sum(1 for a in apps if a.get('update_available'))
    pending_fp = len(fp.get('updates') or [])
    pending_comp = sum(1 for c in ((comp or {}).get('steam') or ()) if c.get('update_available'))
    total_pending = pending_apps + pending_fp + pending_comp + (1 if self_new else 0)
    return {
        'tandem_version': self_version,
        'tandem_new': self_new or '',
        'last_check': st.get('last_check', 0),
        'pending_count': total_pending,
        'appimages': apps,
        'flatpaks': fp,
        'companions': comp or {},
        'job': job_state(),
    }


def run_full_update(games_list, rom_id_fn, roots=(), apply_updates=True, self_update_fn=None, on_step=None):
    """Check (and with `apply_updates=True`, install) updates across:
    1) Game companions (Steam mods + GBADuo packs + RetroArch UDP + DS/3DS dual-screen)
    2) Missing Libretro cores for owned ROM folders
    3) All installed ARM64 Emulator AppImages (`DuckStation`, `ARMSX2`, `Azahar`, `melonDS`, `Cemu`, `Eden`, custom feeds)
    4) Flatpak emulators
    5) Toravo Tandem self-update check (and apply when requested)"""
    def step(msg):
        _JOB['step'] = msg
        if on_step:
            on_step(msg)

    owned_sys = {g.get('s') for g in (games_list or ()) if isinstance(g, dict)}
    done_items = []

    step('Prüfe & installiere Spiel-Begleiter (Steam & GBA) …')
    comp = sync_all_companions(games_list, rom_id_fn, roots=roots, apply_updates=apply_updates, force_catalog=True)
    done_items.extend(comp.get('changes') or [])

    if apply_updates:
        step('Prüfe RetroArch-Kerne für deine Systeme …')
        new_cores = sync_retroarch_cores(owned_sys)
        for c in new_cores:
            done_items.append(f'Core {c}')

    step('Prüfe ARM64-Emulatoren (GitHub & Forgejo) …')
    apps = check_appimages(owned_systems=owned_sys, network=True)
    if apply_updates:
        for a in apps:
            if a.get('update_available'):
                step(f'Aktualisiere {a["name"]} …')
                r = install_or_update_appimage(a['id'])
                if r.get('ok') and not r.get('unchanged'):
                    done_items.append(f'{a["name"]} {r.get("version", "")}'.strip())

    step('Prüfe Flatpak-Emulatoren …')
    fp = flatpak_status(check_remote=True)
    if apply_updates and fp.get('updates'):
        step('Aktualisiere Flatpak-Emulatoren …')
        fpr = update_flatpaks()
        if fpr.get('updated'):
            done_items.append('Flatpaks')

    if apply_updates:
        for cli_bin, cli_args, cli_lbl in ((HOME / '.local/bin/agy', ['update'], 'Antigravity CLI'),
                                           (HOME / '.local/bin/claude', ['update'], 'Claude Code')):
            if cli_bin.is_file():
                try:
                    r_cli = subprocess.run([str(cli_bin), *cli_args], capture_output=True, text=True, timeout=90)
                    if r_cli.returncode == 0 and any(w in (r_cli.stdout or '').lower() for w in ('updated', 'installed', 'upgraded')):
                        done_items.append(cli_lbl)
                except Exception:
                    pass

    tandem_res = {}
    if self_update_fn:
        step('Prüfe Toravo Tandem Release …')
        tandem_res = self_update_fn(False) or {}

    st = load_state()
    st['last_check'] = int(time.time())
    st['last_summary'] = done_items[:20]
    save_state(st)

    if done_items:
        txt = 'Aktualisiert: ' + ', '.join(done_items[:5]) + (f' (+{len(done_items) - 5} weitere)' if len(done_items) > 5 else '') + '.'
    else:
        avail = sum(1 for a in check_appimages(owned_systems=owned_sys, network=False) if a.get('update_available'))
        if not apply_updates and avail:
            txt = f'{avail} Emulator-Updates verfügbar.'
        elif tandem_res.get('new'):
            txt = f'Tandem {tandem_res["new"]} verfügbar – alle Begleiter & Emulatoren aktuell.'
        else:
            txt = 'Alles aktuell – Begleiter, Emulatoren und Kerne sind auf dem neuesten Stand.'
    return {'ok': True, 'updated': done_items, 'tandem': tandem_res, 'text': txt}


def start_update_job(games_list, rom_id_fn, roots=(), apply_updates=True, target_app='', self_update_fn=None, on_done=None):
    if not _LOCK.acquire(blocking=False):
        return {'error': 'Update-Dienst läuft bereits im Hintergrund.'}
    _JOB.update(running=True, step='Starte Update-Prüfung …', error='', result='')

    def worker():
        try:
            if target_app:
                _JOB['step'] = f'Lade {target_app} …'
                res = install_or_update_appimage(target_app)
            else:
                res = run_full_update(games_list, rom_id_fn, roots=roots, apply_updates=apply_updates, self_update_fn=self_update_fn)
            if res.get('ok'):
                _JOB.update(running=False, step='Fertig', result=res.get('text', ''), done_at=int(time.time()))
            else:
                _JOB.update(running=False, step='Fehler', error=res.get('error', 'Fehler'))
            if on_done:
                on_done(res)
        finally:
            _LOCK.release()

    threading.Thread(target=worker, daemon=True).start()
    return {'ok': True, 'text': 'Update-Dienst gestartet …'}


def main():
    ap = argparse.ArgumentParser(description='Toravo Tandem Integrated Updater & Auto-Companion Service')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status', help='Show current update & companion state')
    cp = sub.add_parser('check', help='Check all upstream sources without modifying files')
    up = sub.add_parser('update', help='Sync all game companions & update emulators/cores')
    rb = sub.add_parser('rollback', help='Rollback an AppImage emulator to .prev')
    rb.add_argument('id')
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tandem
    lib = tandem.Library(tandem.rom_roots([]), HOME / '.local/share/Steam')
    games = list(lib.scan().values())
    if args.cmd == 'status':
        print(json.dumps(overview(games, tandem.rom_identity, lib.roots, tandem.VERSION), indent=2, ensure_ascii=False))
        return 0
    if args.cmd in ('check', 'update'):
        res = run_full_update(games, tandem.rom_identity, roots=lib.roots, apply_updates=(args.cmd == 'update'),
                              self_update_fn=tandem.self_update, on_step=lambda m: print(m, flush=True))
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    if args.cmd == 'rollback':
        res = rollback_appimage(args.id)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
