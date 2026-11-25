#!/usr/bin/env python3
"""Integrated Tandem & Linux System Backup + Retroactive Android Partition Shrinker for AYN Thor (ArmadaOS).

Features:
1. Multi-tier Linux & Tandem Backup / Restore (`profile` ~1-4 GB zstd archive of all Tandem state, 32+ GBA packs,
   native ports, BananaNative/Peanuts runtimes, emulator configs/BIOS/keys/saves, Steam shortcuts & SSH/system configs;
   `full` 1:1 complete `/var/home/armada` archive/mirror onto SD card, USB SSD, or SSH server like `harmssi-ai`).
   Uses `.tar.zst` on exFAT SD cards so POSIX permissions, symlinks, and 0600 keys survive 100% intact.
2. Retroactive In-Place Android `userdata` Shrinker (`shrink_android_live`):
   Shrinks unmounted Android `userdata` (`sda17`, default 113 GiB -> down to 8..96 GiB) right from running ArmadaOS Linux,
   saves GPT & savegame backups first, creates a 1-MiB-aligned `ARMADA_DATA` partition in the freed UFS 4.0 space without
   touching `/boot/efi`, `/boot`, or `ARMADA_ROOT`, updates kernel mappings online via `partx` (`BLKPG`), resets Android
   `userdata`/`metadata` headers cleanly like `armada-installer`, and expands `/var/home` live via `btrfs device add`.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
BACKUP_STATUS_FILE = STATE / 'system-backup.json'
MIB = 1024 ** 2
GIB = 1024 ** 3
ANDROID_MIN_GIB = 8
LINUX_PART_TYPE = '0fc63daf-8483-4772-8e79-3d69d8477de4'

_JOB_LOCK = threading.Lock()
_JOB = {
    'running': False,
    'kind': '',       # 'backup' | 'restore' | 'resize'
    'mode': '',
    'step': '',
    'error': '',
    'done_at': 0,
    'result': '',
}

# Profile backup paths relative to $HOME (captures 100% of Tandem, saves, emulators, BIOS, keys, ports & runtimes,
# while skipping regenerable shader caches and giant Steam/ROM binaries).
PROFILE_REL_PATHS = (
    '.config/tandem',
    '.local/share/tandem',
    '.local/share/tandem-ports',
    '.local/state/tandem',
    '.local/opt/bananative',
    '.local/opt/peanuts',
    '.local/share/banananative',
    '.local/share/peanuts',
    '.switch',
    '.ssh',
    '.config/ARMSX2',
    '.config/PCSX2',
    '.config/Cemu',
    '.config/ppsspp',
    '.config/melonDS',
    '.config/azahar-emu',
    '.config/eden',
    '.config/gamescope-session-plus',
    '.local/share/duckstation',
    '.local/share/dolphin-emu',
    '.local/share/Cemu',
    '.local/share/eden',
    '.local/share/azahar-emu',
    '.local/share/melonDS',
    '.local/share/melonds',
    '.local/share/applications',
    '.local/share/Steam/userdata',
    '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg',
    '.var/app/org.libretro.RetroArch/config/retroarch/config',
    '.var/app/org.libretro.RetroArch/config/retroarch/saves',
    '.var/app/org.libretro.RetroArch/config/retroarch/states',
    '.var/app/org.libretro.RetroArch/config/retroarch/cores',
    '.var/app/org.libretro.RetroArch/config/retroarch/system',
    '.var/app/org.DolphinEmu.dolphin-emu/config',
    '.var/app/org.DolphinEmu.dolphin-emu/data',
    '.var/app/org.ppsspp.PPSSPP/config',
    '.var/app/org.flycast.Flycast/config',
    '.var/app/org.flycast.Flycast/data',
    '.var/app/org.azahar_emu.Azahar/config',
    '.var/app/org.azahar_emu.Azahar/data',
)

FULL_EXCLUDES = (
    '.cache',
    '*/cache/*',
    '*/Cache/*',
    '*/shadercache/*',
    '*/shader_cache/*',
    '*/GPUCache/*',
    '*/Code Cache/*',
    '*/mesa_shader_cache*',
    '.local/share/Trash',
    'Games/BananaNative/*/*-work/android-shaders',
)


def job_state():
    return dict(_JOB)


# ---- Safe Storage Cleaner (Orphaned Proton Prefixes, Stale Shader Caches & Temp Leftovers) ---------------------------
def _dir_bytes(path):
    total = 0
    try:
        for root, _, files in os.walk(path, followlinks=False):
            for f in files:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _installed_steam_ids(steam_dir):
    """Collect all installed Steam AppIDs AND non-Steam shortcut AppIDs/GameIDs so active prefixes are NEVER touched."""
    keep = set()
    sdir = Path(steam_dir)
    for acf in sdir.glob('steamapps/appmanifest_*.acf'):
        m = re.search(r'appmanifest_(\d+)\.acf$', acf.name)
        if m:
            keep.add(m[1])
    # Always keep Proton / Steam Linux Runtime / Steamworks Common Redistributables (228980)
    keep.update({'228980', '1391110', '1628350', '1493710', '1887720', '2180100', '2348590', '2805730'})
    for vdf in sdir.glob('userdata/[0-9]*/config/shortcuts.vdf'):
        try:
            data = vdf.read_bytes()
            for m in re.finditer(rb'\x02appid\x00(.{4})', data, re.S):
                aid = struct.unpack('<I', m[1])[0] if 'struct' in globals() else int.from_bytes(m[1], 'little')
                keep.add(str(aid))
                keep.add(str((aid << 32) | 0x02000000))
        except OSError:
            pass
    return keep


def scan_storage_cleanup(home=None, steam_dir=None):
    """Analyze safely reclaimable disk space: orphaned Steam compatdata, stale shadercache, Trash & temp files."""
    h = Path(home) if home else HOME
    sdir = Path(steam_dir) if steam_dir else (h / '.local/share/Steam')
    keep_ids = _installed_steam_ids(sdir) if sdir.is_dir() else set()

    orphan_compat = []
    compat_root = sdir / 'steamapps/compatdata'
    if compat_root.is_dir() and keep_ids:
        for d in sorted(compat_root.iterdir()):
            if d.is_dir() and d.name.isdigit() and d.name != '0' and d.name not in keep_ids:
                sz = _dir_bytes(d)
                if sz > 0:
                    orphan_compat.append({'id': d.name, 'path': str(d), 'bytes': sz})

    orphan_shaders = []
    shader_root = sdir / 'steamapps/shadercache'
    if shader_root.is_dir() and keep_ids:
        for d in sorted(shader_root.iterdir()):
            if d.is_dir() and d.name.isdigit() and d.name not in keep_ids:
                sz = _dir_bytes(d)
                if sz > 0:
                    orphan_shaders.append({'id': d.name, 'path': str(d), 'bytes': sz})

    trash_bytes = 0
    trash_dir = h / '.local/share/Trash'
    if trash_dir.is_dir():
        trash_bytes = _dir_bytes(trash_dir)

    temp_bytes = 0
    temp_paths = []
    for cand in (
        *glob.glob(str(h / '.cache/tandem/*.tmp')),
        *glob.glob(str(h / '.cache/tandem/*.part')),
        *glob.glob(str(h / '.local/state/tandem/*.tmp')),
        *glob.glob(str(sdir / 'steamapps/downloading/*')),
    ):
        # Never touch active Steam downloads if stateflags manifest exists in downloading
        p = Path(cand)
        if 'downloading' in str(p):
            aid_m = re.match(r'^(\d+)$', p.name)
            if aid_m and (sdir / f'steamapps/appmanifest_{aid_m[1]}.acf').is_file():
                continue
        sz = _dir_bytes(p) if p.is_dir() else (p.stat().st_size if p.is_file() else 0)
        if sz > 0:
            temp_bytes += sz
            temp_paths.append(str(p))

    c_bytes = sum(x['bytes'] for x in orphan_compat)
    s_bytes = sum(x['bytes'] for x in orphan_shaders)
    t_cnt = (1 if trash_bytes else 0) + len(temp_paths)
    t_mb = round((trash_bytes + temp_bytes) / MIB, 1)
    total = c_bytes + s_bytes + trash_bytes + temp_bytes
    c_dict = {'id': 'compatdata', 'title': 'Verwaiste Proton-Prefixe', 'count': len(orphan_compat),
              'bytes': c_bytes, 'mb': round(c_bytes / MIB, 1), 'items': [x['id'] for x in orphan_compat],
              'desc': 'Windows-Umgebungen bereits deinstallierter Steam-Spiele (aktive Spiele & Spielstände bleiben unberührt).'}
    s_dict = {'id': 'shadercache', 'title': 'Alte Steam-Shader-Caches', 'count': len(orphan_shaders),
              'bytes': s_bytes, 'mb': round(s_bytes / MIB, 1),
              'desc': 'Nicht mehr benötigte Vulkan-/DXVK-Shader-Ordner deinstallierter Steam-Titel.'}
    t_dict = {'id': 'trash', 'title': 'Papierkorb & Temp-Reste', 'count': t_cnt,
              'bytes': trash_bytes + temp_bytes, 'mb': t_mb,
              'desc': 'Gelöschte Dateien im Linux-Papierkorb und abgebrochene temporäre Downloads.'}
    return {
        'total_bytes': total,
        'total_mb': round(total / MIB, 1),
        'total_gib': round(total / GIB, 2),
        'compatdata': c_dict,
        'shadercache': s_dict,
        'trash': t_dict,
        'temp': t_dict,
        'categories': [c_dict, s_dict, t_dict],
        '_targets': {
            'compatdata': [x['path'] for x in orphan_compat],
            'shadercache': [x['path'] for x in orphan_shaders],
            'trash': ([str(trash_dir / 'files'), str(trash_dir / 'info')] if trash_bytes else []) + temp_paths,
        },
    }


def run_storage_cleanup(which='all', home=None, steam_dir=None):
    """Delete selected ('all' | 'compatdata' | 'shadercache' | 'trash') safely reclaimable directories."""
    if which == 'temp':
        which = 'trash'
    scan = scan_storage_cleanup(home=home, steam_dir=steam_dir)
    targets_map = scan.get('_targets') or {}
    keys = ('compatdata', 'shadercache', 'trash') if which == 'all' else ((which,) if which in targets_map else ())
    freed = 0
    removed = 0
    for k in keys:
        for p_str in targets_map.get(k, ()):
            p = Path(p_str)
            sz = _dir_bytes(p) if p.is_dir() else (p.stat().st_size if p.is_file() else 0)
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                elif p.exists():
                    p.unlink(missing_ok=True)
                freed += sz
                removed += 1
            except OSError:
                pass
    after = scan_storage_cleanup(home=home, steam_dir=steam_dir)
    after.pop('_targets', None)
    mb = round(freed / MIB, 1)
    lbl = f'{freed / GIB:.2f} GiB'.replace('.', ',') if freed >= 512 * MIB else f'{mb:g} MB'.replace('.', ',')
    return {'ok': True, 'freed_bytes': freed, 'removed': removed,
            'text': f'Speicher bereinigt: {lbl} freigegeben.' if freed else 'Alles bereits sauber.', 'cleanup': after}


def _align_up_1m(byte_offset):
    return ((int(byte_offset) + MIB - 1) // MIB) * MIB


def external_backup_dir():
    """Find writable SD card or external USB drive (`/run/media/*/*`), else fallback to `~/.local/state/tandem/system-backups`."""
    override = os.environ.get('TANDEM_SYS_BACKUP_DIR')
    if override:
        return Path(override)
    for pat in ('/run/media/*/*', '/media/*/*'):
        for root in sorted(glob.glob(pat)):
            p = Path(root)
            if p.is_dir() and os.access(p, os.W_OK):
                return p / 'Backups/Thor-Linux'
    return STATE / 'system-backups'


def _meta_path(arc_path):
    return Path(re.sub(r'\.tar\.(?:zst|gz)$', '.meta.json', str(arc_path)))


def list_system_backups(dest_dir=None):
    """List local `.tar.zst` / `.tar.gz` system backups (newest first)."""
    d = Path(dest_dir) if dest_dir else external_backup_dir()
    if not d.is_dir():
        return []
    out = []
    arcs = [p for p in d.iterdir()
            if p.name.startswith(('thor-profile-', 'thor-full-')) and p.name.endswith(('.tar.zst', '.tar.gz'))]
    for f in sorted(arcs, key=lambda p: p.stat().st_mtime, reverse=True)[:16]:
        try:
            st = f.stat()
        except OSError:
            continue
        kind = 'full' if f.name.startswith('thor-full-') else 'profile'
        meta = {}
        meta_file = _meta_path(f)
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                meta = {}
        out.append({
            'file': f.name,
            'path': str(f),
            'kind': kind,
            'at': int(meta.get('at') or st.st_mtime),
            'size': st.st_size,
            'size_gb': round(st.st_size / GIB, 2),
            'items': int(meta.get('count') or 0),
        })
    return out


def backup_overview(dest_dir=None):
    d = Path(dest_dir) if dest_dir else external_backup_dir()
    try:
        saved = json.loads(BACKUP_STATUS_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = {}
    free_bytes = 0
    try:
        target_probe = d if d.exists() else d.parent if d.parent.exists() else HOME
        st = os.statvfs(target_probe)
        free_bytes = st.f_bavail * st.f_frsize
    except OSError:
        pass
    return {
        'dest': str(d),
        'dest_on_card': str(d).startswith(('/run/media/', '/media/')),
        'dest_free_gib': round(free_bytes / GIB, 1),
        'last': saved.get('last', 0),
        'last_mode': saved.get('mode', ''),
        'last_where': saved.get('where', ''),
        'archives': list_system_backups(d),
        'job': job_state(),
    }


def _save_backup_meta(info):
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = BACKUP_STATUS_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(info), encoding='utf-8')
    os.replace(tmp, BACKUP_STATUS_FILE)


def run_system_backup(mode='profile', ssh_target='', home=None, dest_dir=None, keep=4, on_step=None):
    """Create a compressed `.tar.zst` (or `.tar.gz` fallback) backup of Tandem + Linux user state (`profile` or `full`),
    preserving 100% of symlinks and POSIX permissions even on exFAT SD cards, plus optional rsync to `ssh_target`."""
    h = Path(home) if home else HOME
    out_dir = Path(dest_dir) if dest_dir else external_backup_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = 'full' if mode == 'full' else 'profile'
    use_zst = bool(shutil.which('zstd'))
    ext = 'tar.zst' if use_zst else 'tar.gz'
    stamp = time.strftime('%Y%m%d-%H%M%S')
    arc_name = f'thor-{mode}-{stamp}.{ext}'
    arc_path = out_dir / arc_name
    tmp_arc = out_dir / f'.part-{arc_name}'

    def step(msg):
        _JOB['step'] = msg
        if on_step:
            on_step(msg)

    if mode == 'profile':
        rel_items = [rel for rel in PROFILE_REL_PATHS if (h / rel).exists()]
        if not rel_items:
            return {'error': 'Keine Profil-Dateien zum Sichern gefunden.'}
    else:
        rel_items = ['.']

    # Check free disk space on local destination before writing
    try:
        stv = os.statvfs(out_dir)
        avail = stv.f_bavail * stv.f_frsize
        min_need = (18 * GIB) if mode == 'full' else (512 * MIB)
        if avail < min_need and not (mode == 'full' and ssh_target and ':' in ssh_target):
            return {'error': f'Zu wenig Platz am Sicherungsort ({avail // GIB} GiB frei).'}
    except OSError:
        avail = 0

    places = []
    local_written = False
    if mode == 'profile' or avail >= 18 * GIB or not (ssh_target and ':' in ssh_target):
        step('Packe Linux- & Tandem-Archiv (zstd) …' if mode == 'profile' else 'Packe Komplett-Backup des Linux-Systems (kann einige Minuten dauern) …')
        tar_cmd = ['tar', '--zstd' if use_zst else '-z']
        for pat in FULL_EXCLUDES:
            tar_cmd.append(f'--exclude={pat}')
        if mode == 'profile':
            tar_cmd.append('--exclude=.local/share/eden/nand/*/Contents')
        tar_cmd += [f'--exclude={out_dir}', '-cf', str(tmp_arc), '-C', str(h), *rel_items]
        tar_env = {**os.environ, 'ZSTD_CLEVEL': '3', 'ZSTD_NBTHREADS': '0'}
        proc = subprocess.run(tar_cmd, capture_output=True, text=True, env=tar_env)
        # tar exit code 1 means "some files changed as we read them" (harmless on live home), >=2 is fatal
        if proc.returncode >= 2 or not tmp_arc.is_file():
            tmp_arc.unlink(missing_ok=True)
            return {'error': (proc.stderr or 'Archivierung fehlgeschlagen.').strip()[:180]}
        os.replace(tmp_arc, arc_path)
        meta = {'at': int(time.time()), 'mode': mode, 'count': len(rel_items), 'items': rel_items[:40]}
        _meta_path(arc_path).write_text(json.dumps(meta, indent=2), encoding='utf-8')
        # Prune old archives of same mode
        same = sorted([p for p in out_dir.iterdir()
                       if p.name.startswith(f'thor-{mode}-') and p.name.endswith(('.tar.zst', '.tar.gz'))],
                      key=lambda p: p.stat().st_mtime)
        for old in same[:-max(1, int(keep))]:
            old.unlink(missing_ok=True)
            _meta_path(old).unlink(missing_ok=True)
        local_written = True
        places.append('SD-Karte' if str(out_dir).startswith(('/run/media/', '/media/')) else 'Gerät')

    remote = (ssh_target or '').strip()
    if remote and ':' in remote and shutil.which('rsync') and shutil.which('ssh'):
        step(f'Übertrage Sicherung per SSH nach {remote.split(":", 1)[0]} …')
        ssh_opt = 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new'
        host, _, rpath = remote.partition(':')
        sub_rpath = rpath.rstrip('/') + ('/thor-linux-full' if mode == 'full' and not local_written else '/thor-linux-backups')
        subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', host, f'mkdir -p {shlex.quote(sub_rpath)}'],
                       capture_output=True, timeout=15)
        if local_written:
            r_cmd = ['rsync', '-az', '-e', ssh_opt, str(arc_path), str(_meta_path(arc_path)), f'{host}:{sub_rpath}/']
        else:
            r_cmd = ['rsync', '-aHAX', '--delete', *[f'--exclude={p}' for p in FULL_EXCLUDES], '-e', ssh_opt, f'{h}/', f'{host}:{sub_rpath}/']
        r_res = subprocess.run(r_cmd, capture_output=True, text=True, timeout=3600)
        if r_res.returncode == 0:
            places.append('Server')
        elif not local_written:
            return {'error': f'SSH-Sicherung fehlgeschlagen: {(r_res.stderr or "").strip()[:140]}'}

    where = ' + '.join(places) or 'lokal'
    size_gb = round(arc_path.stat().st_size / GIB, 2) if local_written and arc_path.is_file() else 0.0
    info = {'last': int(time.time()), 'mode': mode, 'where': where, 'file': arc_name if local_written else remote}
    _save_backup_meta(info)
    label = 'Komplett-Backup' if mode == 'full' else 'System-Profil'
    return {
        'ok': True,
        'file': arc_name if local_written else remote,
        'where': where,
        'size_gb': size_gb,
        'text': f'{label} gesichert ({where}' + (f', {size_gb:g} GB).' if size_gb else ').'),
    }


def restore_system_backup(archive_name, home=None, dest_dir=None):
    """Safely unpack a `thor-profile-*.tar.*` or `thor-full-*.tar.*` archive back into `$HOME`."""
    h = Path(home) if home else HOME
    d = Path(dest_dir) if dest_dir else external_backup_dir()
    safe_name = Path(str(archive_name or '')).name
    arc = d / safe_name
    if not safe_name.startswith(('thor-profile-', 'thor-full-')) or not arc.is_file():
        return {'error': 'Sicherungsarchiv nicht gefunden.'}
    # Verify archive paths never escape $HOME
    use_zst = safe_name.endswith('.tar.zst')
    z_flag = '--zstd' if use_zst else '-z'
    chk = subprocess.run(['tar', z_flag, '-tf', str(arc)], capture_output=True, text=True, timeout=300)
    if chk.returncode != 0:
        return {'error': 'Beschädigtes Sicherungsarchiv.'}
    for line in chk.stdout.splitlines():
        p = Path(line)
        if p.is_absolute() or '..' in p.parts:
            return {'error': 'Ungültiger Pfad im Paket.'}
    res = subprocess.run(['tar', z_flag, '-xf', str(arc), '-C', str(h)], capture_output=True, text=True, timeout=1800)
    if res.returncode >= 2:
        return {'error': (res.stderr or 'Wiederherstellung fehlgeschlagen.').strip()[:180]}
    return {'ok': True, 'text': f'System-Sicherung {safe_name} erfolgreich wiederhergestellt.'}


def start_backup_async(mode='profile', ssh_target='', on_done=None):
    if not _JOB_LOCK.acquire(blocking=False):
        return {'error': 'Sicherung läuft bereits.'}
    _JOB.update(running=True, kind='backup', mode=mode, step='Bereite Sicherung vor …', error='', result='')

    def worker():
        try:
            res = run_system_backup(mode=mode, ssh_target=ssh_target)
            if res.get('ok'):
                _JOB.update(running=False, step='Fertig', result=res.get('text', ''), done_at=int(time.time()))
            else:
                _JOB.update(running=False, step='Fehlgeschlagen', error=res.get('error', 'Fehler'))
            if on_done:
                on_done(res)
        finally:
            _JOB_LOCK.release()

    threading.Thread(target=worker, daemon=True).start()
    return {'ok': True, 'text': 'Komplett-Backup im Hintergrund gestartet …' if mode == 'full' else 'System-Profil-Sicherung gestartet …'}


# ---- Internal UFS Dual-Boot Layout & Retroactive Android Partition Shrinker -------------------------------------------
def _sysfs_partitions(disk_name, sys_block='/sys/class/block'):
    """Read partition start/size (in bytes) & PARTLABEL from sysfs + udev without needing root!"""
    base = Path(sys_block) / disk_name
    if not base.is_dir():
        return None
    try:
        total_bytes = int((base / 'size').read_text().strip()) * 512
        logical_bs = int((base / f'queue/logical_block_size').read_text().strip())
    except (OSError, ValueError):
        return None
    by_label = {}
    if Path('/dev/disk/by-partlabel').is_dir():
        for link in Path('/dev/disk/by-partlabel').iterdir():
            try:
                by_label[Path(os.readlink(link)).name] = link.name
            except OSError:
                pass
    parts = []
    prefix = disk_name + ('p' if disk_name[-1].isdigit() else '')
    for child in sorted(base.iterdir()):
        if not child.name.startswith(prefix):
            continue
        tail = child.name[len(prefix):]
        if not tail.isdigit():
            continue
        try:
            start_b = int((child / 'start').read_text().strip()) * 512
            size_b = int((child / 'size').read_text().strip()) * 512
        except (OSError, ValueError):
            continue
        label = by_label.get(child.name, '')
        if not label and (child / 'uevent').is_file():
            for ln in (child / 'uevent').read_text(errors='replace').splitlines():
                if ln.startswith('PARTNAME='):
                    label = ln.split('=', 1)[1].strip()
        parts.append({
            'num': int(tail),
            'node': f'/dev/{child.name}',
            'name': label,
            'start_bytes': start_b,
            'size_bytes': size_b,
            'end_bytes': start_b + size_b,
        })
    parts.sort(key=lambda x: x['start_bytes'])
    return {'disk': f'/dev/{disk_name}', 'disk_name': disk_name, 'total_bytes': total_bytes, 'sector_size': logical_bs, 'parts': parts}


def storage_layout(sys_block='/sys/class/block', home_mount='/var/home'):
    """Inspect the AYN Thor's internal UFS dual-boot storage split (Android `userdata` vs ArmadaOS Linux Btrfs) without root."""
    found = None
    for entry in sorted(Path(sys_block).iterdir()) if Path(sys_block).is_dir() else ():
        if not re.fullmatch(r'(?:sd[a-z]|nvme\d+n\d+)', entry.name):
            continue
        info = _sysfs_partitions(entry.name, sys_block=sys_block)
        if info and any(p['name'] == 'userdata' for p in info['parts']):
            found = info
            break
    if not found:
        return {'supported': False, 'reason': 'Keine interne Dual-Boot-Partitionstabelle (userdata) gefunden.'}

    ud = next(p for p in found['parts'] if p['name'] == 'userdata')
    after = [p for p in found['parts'] if p['start_bytes'] >= ud['end_bytes']]
    linux_parts = [p for p in after if p['name'].startswith('ARMADA')]
    android_gib = round(ud['size_bytes'] / GIB, 1)
    linux_part_gib = round(sum(p['size_bytes'] for p in (linux_parts or after)) / GIB, 1)

    linux_total_gib = linux_part_gib
    linux_free_gib = 0.0
    linux_used_gib = 0.0
    try:
        stv = os.statvfs(home_mount if Path(home_mount).exists() else '/')
        linux_total_gib = round((stv.f_blocks * stv.f_frsize) / GIB, 1)
        linux_free_gib = round((stv.f_bavail * stv.f_frsize) / GIB, 1)
        linux_used_gib = round(max(0.0, linux_total_gib - linux_free_gib), 1)
    except OSError:
        pass

    cur_int = int(ud['size_bytes'] // GIB)
    presets = [g for g in (8, 12, 16, 24, 32, 48, 64) if ANDROID_MIN_GIB <= g <= cur_int - 4]
    return {
        'supported': True,
        'disk': found['disk'],
        'sector_size': found['sector_size'],
        'total_gib': round(found['total_bytes'] / GIB, 1),
        'userdata_node': ud['node'],
        'userdata_num': ud['num'],
        'android_gib': android_gib,
        'android_min_gib': ANDROID_MIN_GIB,
        'android_max_shrink_to_gib': max(ANDROID_MIN_GIB, cur_int - 4),
        'presets_gib': presets,
        'linux_total_gib': linux_total_gib,
        'linux_used_gib': linux_used_gib,
        'linux_free_gib': linux_free_gib,
        'reclaimable_max_gib': max(0, cur_int - ANDROID_MIN_GIB),
        'extra_chunks': [p['node'] for p in linux_parts if p['name'].startswith('ARMADA_DATA')],
        'job': job_state(),
    }


def build_shrink_sfdisk_plan(sfdisk_json, target_android_gib):
    """Pure, deterministic GPT planner (unit-tested without touching real disks!):
    Takes `sfdisk --json` dict + desired `target_android_gib`, validates all safety invariants, shrinks ONLY `userdata`,
    and inserts a 1-MiB-aligned `ARMADA_DATA` Linux partition in the newly freed space right after `userdata` while keeping
    every other partition (including mounted `ARMADA`, `ARMADA_BOOT`, `ARMADA_ROOT`) 100% byte-for-byte identical!"""
    pt = sfdisk_json['partitiontable']
    if pt.get('label') != 'gpt' or pt.get('unit') != 'sectors':
        raise ValueError('Erwartet GPT-Partitionstabelle in Sektoren.')
    sector = int(pt['sectorsize'])
    if sector not in (512, 4096):
        raise ValueError(f'Unbekannte Sektorgröße: {sector}')
    device = pt['device']
    entry_max = int(pt.get('table-length') or 128)
    sep = 'p' if device[-1].isdigit() else ''

    parts = []
    used_nums = set()
    for p in pt.get('partitions') or []:
        if p.get('type') == '00000000-0000-0000-0000-000000000000':
            continue
        m = re.fullmatch(re.escape(device) + sep + r'([1-9][0-9]*)', p['node'])
        if not m:
            raise ValueError(f'Ungültiger Partitionsknoten: {p.get("node")}')
        num = int(m.group(1))
        used_nums.add(num)
        parts.append({
            'num': num,
            'node': p['node'],
            'start': int(p['start']),
            'size': int(p['size']),
            'end': int(p['start']) + int(p['size']),
            'type': str(p['type']).lower(),
            'uuid': str(p.get('uuid') or '').lower(),
            'name': str(p.get('name') or ''),
            'attrs': p.get('attrs', ''),
        })

    ud_list = [p for p in parts if p['name'] == 'userdata']
    if len(ud_list) != 1:
        raise ValueError('Android-Partition „userdata“ nicht eindeutig gefunden.')
    ud = ud_list[0]
    cur_gib = (ud['size'] * sector) // GIB
    target_gib = int(target_android_gib)
    if target_gib < ANDROID_MIN_GIB or target_gib > cur_gib - 2:
        raise ValueError(f'Android-Größe muss zwischen {ANDROID_MIN_GIB} und {cur_gib - 2} GiB liegen (aktuell {cur_gib} GiB).')

    # Find the very next partition starting at or after userdata.end (e.g. sda18 ARMADA, or sda21 ARMADA_DATA from an earlier shrink)
    after = sorted((p for p in parts if p['start'] >= ud['end']), key=lambda p: p['start'])
    if not after:
        raise ValueError('Keine ArmadaOS-Partition hinter userdata gefunden.')
    ceiling_lba = after[0]['start']

    ud_aligned_start_b = _align_up_1m(ud['start'] * sector)
    new_ud_end_b = _align_up_1m(ud_aligned_start_b + target_gib * GIB)
    new_ud_end_lba = new_ud_end_b // sector
    if new_ud_end_lba <= ud['start'] or new_ud_end_lba >= ceiling_lba:
        raise ValueError('Ungültige Partitionsgrenzen für userdata.')

    extra_start_lba = _align_up_1m(new_ud_end_lba * sector) // sector
    extra_end_lba = (ceiling_lba * sector // MIB * MIB) // sector
    gained_bytes = (extra_end_lba - extra_start_lba) * sector
    if gained_bytes < 2 * GIB:
        raise ValueError('Freigegebener Bereich ist kleiner als 2 GiB.')

    free_nums = [n for n in range(1, entry_max + 1) if n not in used_nums]
    if not free_nums:
        raise ValueError('Kein freier GPT-Partitionsplatz verfügbar.')
    # Prefer the first free slot after the highest existing partition (e.g. 21) so numbering stays intuitive
    high_free = [n for n in free_nums if n > max(used_nums)]
    new_num = high_free[0] if high_free else free_nums[0]
    existing_data_names = {p['name'] for p in parts if p['name'].startswith('ARMADA_DATA')}
    new_label = 'ARMADA_DATA' if 'ARMADA_DATA' not in existing_data_names else f'ARMADA_DATA{len(existing_data_names) + 1}'
    new_node = f'{device}{sep}{new_num}'

    new_part = {
        'num': new_num,
        'node': new_node,
        'start': extra_start_lba,
        'size': extra_end_lba - extra_start_lba,
        'end': extra_end_lba,
        'type': LINUX_PART_TYPE,
        'uuid': '',
        'name': new_label,
        'attrs': '',
    }

    lines = [
        'label: gpt',
        f'label-id: {pt["id"].lower()}',
        'unit: sectors',
        f'first-lba: {pt["firstlba"]}',
        f'last-lba: {pt["lastlba"]}',
        f'sector-size: {sector}',
        f'table-length: {entry_max}',
    ]
    final_parts = []
    for p in parts:
        if p['num'] == ud['num']:
            upd = dict(p, size=new_ud_end_lba - ud['start'], end=new_ud_end_lba)
            final_parts.append(upd)
        else:
            final_parts.append(p)
    final_parts.append(new_part)
    final_parts.sort(key=lambda x: x['num'])

    # Verify zero overlap across all sorted extents
    by_start = sorted(final_parts, key=lambda x: x['start'])
    for a, b in zip(by_start, by_start[1:]):
        if a['end'] > b['start']:
            raise ValueError(f'Überlappende Partitionen verhindert ({a["node"]} -> {b["node"]}).')

    for p in final_parts:
        esc_name = re.sub(r'["\\\x00-\x1f]', lambda m: f'\\x{ord(m[0]):02x}', p['name'])
        fields = [f'start={p["start"]}', f'size={p["size"]}', f'type={p["type"]}', f'name="{esc_name}"']
        if p['uuid']:
            fields.append(f'uuid={p["uuid"]}')
        if p['attrs']:
            fields.append(f'attrs={json.dumps(p["attrs"])}')
        lines.append(f'{p["node"]}: ' + ', '.join(fields))

    return {
        'device': device,
        'sector_size': sector,
        'userdata_num': ud['num'],
        'userdata_node': ud['node'],
        'userdata_start': ud['start'],
        'userdata_new_size': new_ud_end_lba - ud['start'],
        'new_num': new_num,
        'new_node': new_node,
        'new_label': new_label,
        'new_start': extra_start_lba,
        'new_size': extra_end_lba - extra_start_lba,
        'gained_gib': round(gained_bytes / GIB, 1),
        'android_new_gib': round(((new_ud_end_lba - ud['start']) * sector) / GIB, 1),
        'script': '\n'.join(lines) + '\n',
    }


def _run_sudo(cmd, sudo_password=None, input_text=None, timeout=120):
    """Execute a privileged root command cleanly; feeds `sudo_password` only when not already root and `sudo -n` needs it.
    When `input_text` is also supplied (e.g. `sfdisk` script), passes `input_text` via a 0600 temp file so `sudo -S` never
    consumes or buffers the child command's stdin."""
    if os.geteuid() == 0:
        return subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=timeout)
    probe = subprocess.run(['sudo', '-n', 'true'], capture_output=True, text=True, timeout=5)
    if probe.returncode == 0:
        return subprocess.run(['sudo', '-n', *cmd], input=input_text, capture_output=True, text=True, timeout=timeout)
    if not sudo_password:
        return subprocess.CompletedProcess(cmd, 1, '', 'PASSWORT_ERFORDERLICH')
    if input_text is not None:
        fd, tmp_path = tempfile.mkstemp(prefix='thor-gpt-', text=True)
        try:
            os.chmod(tmp_path, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(input_text)
            return subprocess.run(
                ['sudo', '-S', '-p', '', 'sh', '-c', 'exec "$@" < "$0"', tmp_path, *cmd],
                input=f'{sudo_password}\n', capture_output=True, text=True, timeout=timeout,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return subprocess.run(['sudo', '-S', '-p', '', *cmd], input=f'{sudo_password}\n',
                          capture_output=True, text=True, timeout=timeout)


def check_sudo(sudo_password=None):
    res = _run_sudo(['true'], sudo_password=sudo_password, timeout=10)
    if res.returncode == 0:
        return {'ok': True}
    if 'PASSWORT_ERFORDERLICH' in (res.stderr or ''):
        return {'need_password': True}
    return {'error': 'Passwort falsch oder sudo nicht erlaubt.'}


def shrink_android_live(target_android_gib, sudo_password=None, btrfs_mount='/var/home', on_step=None):
    """Execute the full verified retroactive Android `userdata` shrink + live online Btrfs `/var/home` expansion!"""
    def step(msg):
        _JOB['step'] = msg
        if on_step:
            on_step(msg)

    auth = check_sudo(sudo_password)
    if not auth.get('ok'):
        return auth

    lay = storage_layout(home_mount=btrfs_mount)
    if not lay.get('supported'):
        return {'error': lay.get('reason', 'Nicht unterstützt.')}
    device = lay['disk']

    # 1) Ensure userdata is completely unmounted and has zero holders/swaps
    ud_node = lay['userdata_node']
    st_ud = os.stat(ud_node).st_rdev
    maj_min = f'{os.major(st_ud)}:{os.minor(st_ud)}'
    mounted = {ln.split()[2] for ln in Path('/proc/self/mountinfo').read_text().splitlines() if len(ln.split()) > 2}
    holders = Path(f'/sys/dev/block/{maj_min}/holders')
    if maj_min in mounted or (holders.is_dir() and any(holders.iterdir())):
        return {'error': f'{ud_node} ist eingehängt – kann nicht verkleinert werden.'}

    # 2) Read exact live GPT via sfdisk --json and build deterministic plan
    step('Prüfe GPT-Partitionstabelle …')
    sf_res = _run_sudo(['sfdisk', '--json', device], sudo_password=sudo_password, timeout=20)
    if sf_res.returncode != 0:
        return {'error': f'sfdisk konnte nicht gelesen werden: {(sf_res.stderr or "").strip()[:140]}'}
    try:
        plan = build_shrink_sfdisk_plan(json.loads(sf_res.stdout), int(target_android_gib))
    except (ValueError, KeyError) as e:
        return {'error': str(e)}

    # 3) Save automatic GPT dump + binary backup + quick savegame backup BEFORE touching a single sector!
    step('Sichere Spielstände & GPT-Partitionstabelle …')
    try:
        import saves
        saves.backup(run_rsync=False)
    except Exception:
        pass
    stamp = time.strftime('%Y%m%d-%H%M%S')
    for bdir in (STATE / 'gpt-backups', external_backup_dir() / 'gpt-backups'):
        try:
            bdir.mkdir(parents=True, exist_ok=True)
            dump = _run_sudo(['sfdisk', '--dump', device], sudo_password=sudo_password, timeout=15)
            if dump.returncode == 0 and dump.stdout:
                (bdir / f'sfdisk-{Path(device).name}-{stamp}.dump').write_text(dump.stdout, encoding='utf-8')
            _run_sudo(['sgdisk', f'--backup={bdir / f"gpt-{Path(device).name}-{stamp}.bin"}', device],
                      sudo_password=sudo_password, timeout=15)
        except OSError:
            pass

    # 4) Write new GPT without BLKRRPART (mounted ARMADA_ROOT stays untouched!), then update kernel via BLKPG (`partx`)
    step(f'Verkleinere Android auf {plan["android_new_gib"]:g} GiB & lege {plan["new_label"]} (+{plan["gained_gib"]:g} GiB) an …')
    wr = _run_sudo(['sfdisk', '--no-reread', '--no-tell-kernel', '--wipe=never', '--wipe-partitions=never', device],
                   sudo_password=sudo_password, input_text=plan['script'], timeout=30)
    if wr.returncode != 0:
        return {'error': f'GPT-Schreibfehler: {(wr.stderr or "").strip()[:160]}'}

    u1 = _run_sudo(['partx', '-u', '--nr', f'{plan["userdata_num"]}:{plan["userdata_num"]}', device],
                   sudo_password=sudo_password, timeout=20)
    u2 = _run_sudo(['partx', '-a', '--nr', f'{plan["new_num"]}:{plan["new_num"]}', device],
                   sudo_password=sudo_password, timeout=20)
    _run_sudo(['udevadm', 'settle'], sudo_password=sudo_password, timeout=20)
    if u1.returncode != 0 or u2.returncode != 0 or not Path(plan['new_node']).is_block_device():
        # Fallback to partprobe if partx reported an already-known node
        _run_sudo(['partprobe', device], sudo_password=sudo_password, timeout=20)
        _run_sudo(['udevadm', 'settle'], sudo_password=sudo_password, timeout=20)
    if not Path(plan['new_node']).is_block_device():
        return {'error': f'Kernel-Knoten {plan["new_node"]} erschien nicht nach partx.'}

    # Verify sysfs byte offsets match the exact plan before writing to either partition!
    sec = plan['sector_size']
    new_sys = Path(f'/sys/class/block/{Path(device).name}/{Path(plan["new_node"]).name}')
    actual_start_b = int((new_sys / 'start').read_text().strip()) * 512
    actual_size_b = int((new_sys / 'size').read_text().strip()) * 512
    if actual_start_b != plan['new_start'] * sec or actual_size_b != plan['new_size'] * sec:
        return {'error': 'Kernel-Partitionsgrenzen weichen vom Plan ab – abgebrochen!'}

    # 5) Cleanly reset Android `userdata` + `metadata` headers (exact `armada-installer` method) so Android formats cleanly on next boot
    step('Initialisiere neue Android-Partition für sauberen Android-Start …')
    _run_sudo(['wipefs', '-a', plan['userdata_node']], sudo_password=sudo_password, timeout=20)
    _run_sudo(['dd', 'if=/dev/zero', f'of={plan["userdata_node"]}', 'bs=1M', 'count=8', 'conv=fsync', 'status=none'],
              sudo_password=sudo_password, timeout=30)
    meta_link = Path('/dev/disk/by-partlabel/metadata')
    if meta_link.exists():
        _run_sudo(['dd', 'if=/dev/zero', f'of={meta_link.resolve()}', 'bs=1M', 'count=4', 'conv=fsync', 'status=none'],
                  sudo_password=sudo_password, timeout=20)

    # 6) Add the newly freed UFS 4.0 partition online to ArmadaOS's live Btrfs pool (`/var/home`)!
    step(f'Binde +{plan["gained_gib"]:g} GiB live in Linux-Speicher ({btrfs_mount}) ein …')
    _run_sudo(['wipefs', '-a', plan['new_node']], sudo_password=sudo_password, timeout=20)
    bt = _run_sudo(['btrfs', 'device', 'add', '-f', plan['new_node'], btrfs_mount],
                   sudo_password=sudo_password, timeout=60)
    if bt.returncode != 0:
        return {'error': f'Btrfs-Erweiterung fehlgeschlagen: {(bt.stderr or bt.stdout or "").strip()[:160]}'}
    os.sync()

    updated = storage_layout(home_mount=btrfs_mount)
    msg = (f'Erfolg! +{plan["gained_gib"]:g} GiB für Linux & Tandem freigegeben '
           f'(Linux jetzt {updated.get("linux_total_gib")} GiB, Android {updated.get("android_gib")} GiB).')
    return {'ok': True, 'text': msg, 'layout': updated, 'plan': {k: v for k, v in plan.items() if k != 'script'}}


def start_shrink_async(target_android_gib, sudo_password=None, on_done=None):
    auth = check_sudo(sudo_password)
    if not auth.get('ok'):
        return auth
    if not _JOB_LOCK.acquire(blocking=False):
        return {'error': 'Ein Speichervorgang läuft bereits.'}
    _JOB.update(running=True, kind='resize', mode=str(target_android_gib), step='Starte Partitionierung …', error='', result='')

    def worker():
        try:
            res = shrink_android_live(target_android_gib, sudo_password=sudo_password)
            if res.get('ok'):
                _JOB.update(running=False, step='Fertig', result=res.get('text', ''), done_at=int(time.time()))
            else:
                _JOB.update(running=False, step='Fehlgeschlagen', error=res.get('error', 'Fehler'))
            if on_done:
                on_done(res)
        finally:
            _JOB_LOCK.release()

    threading.Thread(target=worker, daemon=True).start()
    return {'ok': True, 'text': f'Android wird live auf {target_android_gib} GiB verkleinert …'}


def main():
    ap = argparse.ArgumentParser(description='Toravo Thor Linux Backup & Retroactive Android Partition Shrinker')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status', help='Show dual-boot UFS storage layout & system backups')
    bp = sub.add_parser('backup', help='Run Linux & Tandem backup')
    bp.add_argument('--mode', choices=('profile', 'full'), default='profile')
    bp.add_argument('--ssh', default='', help='Optional SSH target (e.g. harmssi-ai:~/thor-backups)')
    rp = sub.add_parser('restore', help='Restore a system backup archive')
    rp.add_argument('archive', help='Archive filename in Backups/Thor-Linux')
    sp = sub.add_parser('shrink-android', help='Retroactively shrink Android userdata & expand Linux Btrfs live')
    sp.add_argument('--gib', type=int, required=True, help='New Android userdata size in GiB (min 8)')
    sp.add_argument('--yes', action='store_true', help='Confirm Android userdata reset')
    args = ap.parse_args()

    if args.cmd == 'status':
        print(json.dumps({'storage': storage_layout(), 'backups': backup_overview()}, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == 'backup':
        res = run_system_backup(mode=args.mode, ssh_target=args.ssh, on_step=lambda m: print(m, flush=True))
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    if args.cmd == 'restore':
        res = restore_system_backup(args.archive)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    if args.cmd == 'shrink-android':
        lay = storage_layout()
        if not args.yes:
            ans = input(f'ACHTUNG: Android userdata ({lay.get("android_gib")} GiB -> {args.gib} GiB) wird zurückgesetzt, '
                        f'Linux wächst live um ~{round(lay.get("android_gib", 0) - args.gib, 1)} GiB! Fortfahren? [j/N]: ')
            if ans.strip().lower() not in ('j', 'ja', 'y', 'yes'):
                print('Abgebrochen.')
                return 0
        res = shrink_android_live(args.gib, on_step=lambda m: print(m, flush=True))
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
