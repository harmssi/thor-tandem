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


def sources(home=None):
    """[(key, Path)] of save folders that actually exist on this device (pure saves only, never shader caches or game data)."""
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
    ]
    bn_root = h / '.local/share/banananative'
    if bn_root.is_dir():
        for sub in sorted(bn_root.iterdir()):
            if (sub / 'save').is_dir(): candidates.append((f'banananative-{sub.name}', sub / 'save'))
    out, seen = [], set()
    for key, path in candidates:
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


def status():
    try: data = json.loads(STATUS_FILE.read_text())
    except (OSError, ValueError): data = {}
    return {'last': data.get('last', 0), 'count': data.get('count', 0), 'where': data.get('where', ''),
            'error': data.get('error', ''), 'sources': len(sources())}


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
            old = sorted(dest_dir.glob('saves-*.tar.gz'))[:-5]
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
        return {**status(), 'ok': True, 'text': text}
    except (OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        save_status({**status(), 'error': str(error)})
        return {'error': f'Sicherung fehlgeschlagen: {error}'}
    finally:
        LOCK.release()
