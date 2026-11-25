"""Savegame backup for Toravo Tandem: local rolling snapshots on the SD card plus optional SSH/rsync sync to a NAS/host
configured under Settings › Saved games. Standard library + rsync/ssh/tar only."""
import glob, json, os, shlex, shutil, subprocess, tarfile, tempfile, threading, time
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
STATUS_FILE = STATE / 'saves-backup.json'
DEFAULT_TARGET = ''
LOCK = threading.Lock()
EXCLUDE_NAMES = {'files', 'cl_dlls', 'dlls', 'cache', 'logs', 'temp', '__pycache__', 'Content'}


def all_candidates(home=None):
    """[(key, Path)] of every known save directory on this device, whether populated yet or not."""
    h = Path(home) if home else HOME
    ports = Path(os.environ.get('XDG_DATA_HOME', h / '.local/share')) / 'tandem-ports'
    candidates = [
        ('retroarch-saves', h / '.var/app/org.libretro.RetroArch/config/retroarch/saves'),
        ('retroarch-states', h / '.var/app/org.libretro.RetroArch/config/retroarch/states'),
        ('duckstation', h / '.local/share/duckstation/memcards'),
        ('armsx2', h / '.config/ARMSX2/memcards'),
        ('pcsx2', h / '.config/PCSX2/memcards'),
        ('dolphin-gc', h / '.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/GC'),
        ('dolphin-gc-local', h / '.local/share/dolphin-emu/GC'),
        ('dolphin-wii', h / '.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Wii'),
        ('dolphin-wii-local', h / '.local/share/dolphin-emu/Wii'),
        ('ppsspp', h / '.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SAVEDATA'),
        ('ppsspp-local', h / '.config/ppsspp/PSP/SAVEDATA'),
        ('azahar-3ds', h / '.local/share/azahar-emu/sdmc/Nintendo 3DS'),
        ('melonds', h / '.local/share/melonDS'),
        ('melonds-lower', h / '.local/share/melonds'),
        ('flycast', h / '.var/app/org.flycast.Flycast/data/flycast'),
        ('eden-switch', h / '.local/share/eden/nand/user/save'),
        ('cemu-wiiu', h / '.local/share/Cemu/mlc01/usr/save'),
        ('port-aok', ports / 'aok/data/OpenAoK'),
        ('port-cnc-ra', ports / 'cnc/data/ra/home'),
        ('port-cnc-td', ports / 'cnc/data/td/home'),
        ('port-d2', ports / 'd2/data/save'),
        ('port-hl-valve', ports / 'halflife/data/valve'),
        ('port-hl-gearbox', ports / 'halflife/data/gearbox'),
        ('port-hl-bshift', ports / 'halflife/data/bshift'),
        ('port-homm3', ports / 'homm3/data/vcmi'),
        ('port-kknd2', ports / 'kknd2/data/support'),
        ('port-ra2', ports / 'ra2/data/ra2engine'),
        ('steam-userdata', h / '.local/share/Steam/userdata'),
    ]
    for nroot, prefix in ((h / '.local/share/banananative', 'banananative'), (h / '.local/share/peanuts', 'peanuts')):
        if nroot.is_dir():
            for sub in sorted(nroot.iterdir()):
                if (sub / 'save').is_dir(): candidates.append((f'{prefix}-{sub.name}', sub / 'save'))
                if (sub / 'save.work').is_dir(): candidates.append((f'{prefix}-{sub.name}-work', sub / 'save.work'))
    return candidates


def sources(home=None):
    """[(key, Path)] of save folders that actually exist on this device (pure saves only, never shader caches or game data)."""
    out, seen = [], set()
    for key, path in all_candidates(home):
        if not path.is_dir(): continue
        try:
            rp = path.resolve()
            if rp in seen: continue
            if any(True for _ in path.iterdir()):
                seen.add(rp)
                out.append((key, path))
        except OSError: pass
    return out


def card_backup_dir():
    """Backup folder on an inserted SD card, if writable, else ~/.local/state/tandem/backups."""
    override = os.environ.get('TANDEM_SAVE_BACKUP_DIR')
    if override: return Path(override)
    for pat in ('/run/media/*/*', '/media/*/*'):
        for root in sorted(glob.glob(pat)):
            p = Path(root)
            if p.is_dir() and os.access(p, os.W_OK): return p / 'Backups/Tandem-Saves'
    return STATE / 'backups'


def copy_clean(src, dst):
    """Copy save files from src to dst, skipping symlinks, .so binaries, and cache folders."""
    for root, dirs, files in os.walk(src, followlinks=False):
        rel = Path(root).relative_to(src)
        dirs[:] = [d for d in dirs if d not in EXCLUDE_NAMES and not (Path(root) / d).is_symlink()]
        target_dir = dst / rel
        for f in files:
            fp = Path(root) / f
            if fp.is_symlink() or f.endswith(('.so', '.log', '.lock')): continue
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fp, target_dir / f)
            except OSError: pass


def snapshots(local_dir=None):
    """List local rolling save archives (newest first) -> [{'file', 'at', 'size', 'items'}]."""
    dest_dir = Path(local_dir) if local_dir else card_backup_dir()
    if not dest_dir.is_dir(): return []
    out = []
    for arc in sorted(dest_dir.glob('saves-*.tar.gz'), reverse=True)[:12]:
        try:
            st = arc.stat()
            items, at = [], int(st.st_mtime)
            with tarfile.open(arc, 'r:gz') as tar:
                try:
                    mf = tar.extractfile('saves/manifest.json')
                    if mf:
                        meta = json.loads(mf.read())
                        items = meta.get('items') or []
                        at = int(meta.get('at') or at)
                except (KeyError, ValueError): pass
            out.append({'file': arc.name, 'at': at, 'size': st.st_size, 'items': items})
        except (OSError, tarfile.TarError): continue
    return out


def status(local_dir=None):
    try: data = json.loads(STATUS_FILE.read_text())
    except (OSError, ValueError): data = {}
    return {'last': data.get('last', 0), 'count': data.get('count', 0), 'where': data.get('where', ''),
            'error': data.get('error', ''), 'sources': len(sources()), 'snapshots': snapshots(local_dir)}


def save_status(info):
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(info))
    os.replace(tmp, STATUS_FILE)


def backup(target=None, home=None, local_dir=None, run_rsync=True):
    """Collect all saves into a clean staging tree, keep rolling tar.gz snapshots locally, and rsync to target if reachable."""
    if not LOCK.acquire(blocking=False):
        return {'error': 'Sicherung läuft bereits.'}
    try:
        found = sources(home)
        if not found:
            return {'error': 'Noch keine Spielstände gefunden.'}
        dest_dir = Path(local_dir) if local_dir else card_backup_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        latest = dest_dir / 'latest'
        with tempfile.TemporaryDirectory(prefix='tandem-saves-') as tmp:
            stage = Path(tmp) / 'saves'
            stage.mkdir()
            for key, path in found:
                copy_clean(path, stage / key)
            manifest = {'at': int(time.time()), 'items': [k for k, _ in found]}
            (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2))
            if latest.exists(): shutil.rmtree(latest, ignore_errors=True)
            shutil.copytree(stage, latest)
            stamp = time.strftime('%Y%m%d-%H%M%S')
            archive = dest_dir / f'saves-{stamp}.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                tar.add(stage, arcname='saves')
            old = sorted(dest_dir.glob('saves-*.tar.gz'))[:-10]
            for f in old: f.unlink(missing_ok=True)
        places = ['Karte' if str(dest_dir).startswith(('/run/media', '/media')) else 'Gerät']
        remote = (DEFAULT_TARGET if target is None else target).strip()
        remote_err = ''
        if run_rsync and remote and shutil.which('rsync') and shutil.which('ssh'):
            ssh_cmd = 'ssh -o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new'
            host, _, rpath = remote.partition(':')
            if host and rpath:
                clean = rpath.rstrip('/')
                q = ('$HOME/' + shlex.quote(clean[2:]) if clean.startswith('~/') else '$HOME' if clean == '~' else shlex.quote(clean))
                mk = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=4', '-o', 'StrictHostKeyChecking=accept-new',
                                     host, f'mkdir -p {q}/latest {q}/snapshots'], capture_output=True, text=True, timeout=10)
                if mk.returncode == 0:
                    r1 = subprocess.run(['rsync', '-az', '--delete', '-e', ssh_cmd, str(latest) + '/', f'{host}:{clean}/latest/'],
                                        capture_output=True, text=True, timeout=60)
                    day_arc = dest_dir / f'saves-{stamp}.tar.gz'
                    r2 = subprocess.run(['rsync', '-az', '-e', ssh_cmd, str(day_arc), f'{host}:{clean}/snapshots/saves-{stamp[:8]}.tar.gz'],
                                        capture_output=True, text=True, timeout=60)
                    if r1.returncode == 0 and r2.returncode == 0:
                        places.insert(0, host.split('@')[-1].removesuffix('.local'))
                    else:
                        remote_err = 'Server beim Übertragen abgebrochen'
                else:
                    remote_err = 'Server gerade nicht erreichbar'
        where = ' + '.join(places)
        now = int(time.time())
        save_status({'last': now, 'count': len(found), 'where': where, 'error': remote_err})
        text = f'Spielstände gesichert: {len(found)} Ordner ({where}).'
        return {**status(local_dir), 'ok': True, 'text': text}
    except (OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        save_status({**status(local_dir), 'error': str(error)})
        return {'error': f'Sicherung fehlgeschlagen: {error}'}
    finally:
        LOCK.release()


def restore(archive_name, only_key=None, home=None, local_dir=None):
    """Restore saved games from a local snapshot archive (all folders or one specific key). Creates a safety backup first."""
    import re
    if not re.fullmatch(r'saves-[0-9]{8}-[0-9]{6}\.tar\.gz', str(archive_name or '')):
        return {'error': 'Ungültiges Sicherungsarchiv.'}
    dest_dir = Path(local_dir) if local_dir else card_backup_dir()
    arc = dest_dir / archive_name
    if not arc.is_file():
        return {'error': 'Sicherungsarchiv nicht gefunden.'}
    # Safety snapshot before overwriting live saves (best-effort, local only)
    if sources(home):
        backup(target='', home=home, local_dir=dest_dir, run_rsync=False)
    if not LOCK.acquire(blocking=False):
        return {'error': 'Sicherung läuft bereits.'}
    try:
        h = Path(home) if home else HOME
        targets = dict(all_candidates(h))
        restored = []
        with tempfile.TemporaryDirectory(prefix='tandem-restore-') as tmp:
            with tarfile.open(arc, 'r:gz') as tar:
                tar.extractall(tmp, filter='data')
            stage = Path(tmp) / 'saves'
            if not stage.is_dir():
                return {'error': 'Archiv enthält keine Spielstände.'}
            for sub in sorted(stage.iterdir()):
                if not sub.is_dir(): continue
                key = sub.name
                if only_key and key != only_key: continue
                dst = targets.get(key)
                if dst is None and key.startswith('banananative-'):
                    dst = h / '.local/share/banananative' / key.split('banananative-', 1)[1] / 'save'
                elif dst is None and key.startswith('peanuts-'):
                    dst = h / '.local/share/peanuts' / key.split('peanuts-', 1)[1] / 'save'
                if dst is None: continue
                dst.mkdir(parents=True, exist_ok=True)
                copy_clean(sub, dst)
                restored.append(key)
        if not restored:
            return {'error': 'Keine passenden Spielstände im Archiv gefunden.'}
        return {**status(local_dir), 'ok': True, 'restored': restored,
                'text': f'Spielstände wiederhergestellt: {len(restored)} Ordner aus {archive_name}.'}
    except (OSError, tarfile.TarError) as error:
        return {'error': f'Wiederherstellung fehlgeschlagen: {error}'}
    finally:
        LOCK.release()


def keys_for_game(game, emu_label=''):
    """Return the subset of save candidate keys relevant to `game` so pre-launch cloud sync takes < 0.8s and ~0 MB RAM."""
    if not game:
        return []
    s = str(game.get('s') or '')
    lbl = str(emu_label or '')
    if game.get('tid') and lbl in ('BananaNative', 'PeanutsNative'):
        pref = 'banananative' if lbl == 'BananaNative' else 'peanuts'
        tid = str(game['tid']).upper()
        return [f'{pref}-{tid}', f'{pref}-{tid}-work']
    if s == 'port':
        p = str(game.get('port') or '')
        pmap = {
            'aok': ['port-aok'], 'cnc': ['port-cnc-td'], 'ra': ['port-cnc-ra'], 'd2': ['port-d2'],
            'halflife': ['port-hl-valve'], 'opfor': ['port-hl-gearbox'], 'bshift': ['port-hl-bshift'],
            'homm3': ['port-homm3'], 'kknd2': ['port-kknd2'], 'ra2': ['port-ra2'], 'yr': ['port-ra2'],
        }
        return pmap.get(p, [])
    smap = {
        'psx': ['duckstation', 'retroarch-saves', 'retroarch-states'],
        'ps2': ['armsx2', 'pcsx2'],
        'gc': ['dolphin-gc', 'dolphin-gc-local'],
        'wii': ['dolphin-wii', 'dolphin-wii-local'],
        'psp': ['ppsspp', 'ppsspp-local'],
        'n3ds': ['azahar-3ds'],
        'nds': ['melonds', 'melonds-lower', 'retroarch-saves'],
        'dreamcast': ['flycast', 'retroarch-saves'],
        'switch': ['eden-switch'],
        'wiiu': ['cemu-wiiu'],
    }
    if s in smap:
        return smap[s]
    if s not in ('steam', 'app', 'term'):
        return ['retroarch-saves', 'retroarch-states']
    return []


def sync_before_launch(game, emu_label='', target=None, home=None):
    """Zero-daemon bidirectional Cloud-Save pull before game launch:
    pulls newer save files from `user@host:path/latest/<key>/` (backing up local files first on conflict)."""
    remote = str(DEFAULT_TARGET if target is None else target).strip()
    if not remote or ':' not in remote or not shutil.which('rsync') or not shutil.which('ssh'):
        return {'ok': True, 'pulled': 0}
    keys = keys_for_game(game, emu_label)
    if not keys:
        return {'ok': True, 'pulled': 0}
    if not LOCK.acquire(timeout=2.0):
        return {'ok': False, 'pulled': 0}
    try:
        h = Path(home) if home else HOME
        cand_map = dict(all_candidates(h))
        host, _, rpath = remote.partition(':')
        clean = rpath.rstrip('/')
        ssh_cmd = 'ssh -o BatchMode=yes -o ConnectTimeout=2 -o StrictHostKeyChecking=accept-new'
        pulled_files = 0
        for key in keys:
            dst = cand_map.get(key)
            if dst is None and key.startswith(('banananative-', 'peanuts-')):
                pref, rest = key.split('-', 1)
                sub_dir = 'save.work' if rest.endswith('-work') else 'save'
                tid = rest[:-5] if rest.endswith('-work') else rest
                dst = h / f'.local/share/{pref}' / tid / sub_dir
            if dst is None:
                continue
            # Dry-run rsync `--itemize-changes --update` to check if server actually has newer files
            probe = subprocess.run(
                ['rsync', '-azn', '--itemize-changes', '--update', '-e', ssh_cmd,
                 f'{host}:{clean}/latest/{key}/', str(dst) + '/'],
                capture_output=True, text=True, timeout=4,
            )
            if probe.returncode != 0:
                continue
            incoming = [ln for ln in probe.stdout.splitlines() if ln.startswith('>f')]
            if not incoming:
                continue
            # Safety conflict backup of existing local folder before pulling newer remote files
            if dst.is_dir() and any(True for _ in dst.iterdir()):
                bak_root = STATE / 'cloud-conflict-bak' / f'{key}-{time.strftime("%Y%m%d-%H%M%S")}'
                copy_clean(dst, bak_root)
                # Keep at most 6 conflict backups total
                all_baks = sorted((STATE / 'cloud-conflict-bak').glob('*'))
                for old_b in all_baks[:-6]:
                    shutil.rmtree(old_b, ignore_errors=True)
            dst.mkdir(parents=True, exist_ok=True)
            real = subprocess.run(
                ['rsync', '-az', '--update', '-e', ssh_cmd,
                 f'{host}:{clean}/latest/{key}/', str(dst) + '/'],
                capture_output=True, text=True, timeout=12,
            )
            if real.returncode == 0:
                pulled_files += len(incoming)
        if pulled_files > 0:
            return {'ok': True, 'pulled': pulled_files, 'text': f'☁️ Cloud-Save geladen ({pulled_files} neuere Datei{"en" if pulled_files != 1 else ""}).'}
        return {'ok': True, 'pulled': 0}
    except (OSError, subprocess.SubprocessError):
        return {'ok': False, 'pulled': 0}
    finally:
        LOCK.release()
