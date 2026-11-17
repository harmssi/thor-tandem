"""Installs Diablo II + Lord of Destruction 1.13d for the Thor D2 port, the way the Android app does it "without a PC":
Blizzard's own downloaders (downloader.battle.net) fetch the official 1.14b installers, their files are checked against
pinned SHA-256 values, the two installers run with the player's CD keys, LODPatch_113d.exe (ftp.blizzard.com, pinned
SHA-256) patches to 1.13d, and the result is checked against the 1.13d list. Everything Windows runs under the Proton of
the Steam installation (run sets WINEPREFIX etc.), unseen in a headless gamescope.

The CD keys: two lines in $XDG_RUNTIME_DIR/d2-keys (Diablo II, then Lord of Destruction; dashes and spaces are ignored).
The file is read and deleted at once; the keys stay in memory only and reach d2install.exe through a FIFO (0600, deleted
right after), which writes them into the installer's memory: they are in no file, log, or process list.
Without the file, setup downloads and checks the installers and then waits for it.

Progress: data/setup.json ({"step", "text", "percent", "error", "done"}, read by the deck) and data/setup.log.
  python3 setup.py               install if needed (run calls this), exit 0 when the game is ready
  python3 setup.py --selftest    checks of the plain logic
"""
import hashlib, json, os, struct, re, secrets, shutil, signal, subprocess, sys, threading, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent  # dist/
DATA = Path(os.environ.get('D2_DATA', HERE.parent / 'data'))
GAME, SAVES, INST = DATA / 'game', DATA / 'save', DATA / 'installers'
KEYS = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}') / 'd2-keys'
PRODUCTS = (('D2DV', 'Diablo II', 'd2data.mpq'), ('D2XP', 'Lord of Destruction', 'd2exp.mpq'))
LANGS = ('deDE', 'enUS')  # the languages with pinned installer checksums (installer-sha256-<lang>.txt)
DOWNLOADER = 'https://downloader.battle.net/download/getLegacy?os=win&locale={}&product={}'
PATCH_URL = 'http://ftp.blizzard.com/pub/diablo2exp/patches/PC/LODPatch_113d.exe'
PATCH_SHA256 = '918fa5141a4a98f826b1f1f5ea69bf6e20208162d67748baceceaff96e49ae30'
INSTALLER_ARGS = '--user=Player --silent=true --noui=true --skippostlaunch=true --nopatchnotes=true'
STALL = 600  # seconds without a downloaded byte: give up


class Failed(Exception): pass


# ---- plain logic (tested by --selftest) ---------------------------------------------------------------------------------
def clean_key(line):
    """A CD key as the installer wants it (16 or 26 letters and digits, upper case), or None."""
    key = re.sub(r'[\s-]', '', line).upper()
    return key if re.fullmatch(r'[A-Z0-9]{16}|[A-Z0-9]{26}', key) else None


def parse_sums(text):
    """'<sha256>  <name>' lines -> {name: sha256}; comments and anything else are skipped."""
    return {m[2]: m[1].lower() for m in re.finditer(r'(?m)^([0-9a-fA-F]{64})  (.+?)\s*$', text)}


def bdecode(d, i=0):
    c = d[i:i + 1]
    if c == b'i':
        e = d.index(b'e', i)
        return int(d[i + 1:e]), e + 1
    if c in (b'l', b'd'):
        i, out = i + 1, ([] if c == b'l' else {})
        while d[i:i + 1] != b'e':
            if c == b'l':
                v, i = bdecode(d, i)
                out.append(v)
            else:
                k, i = bdecode(d, i)
                out[k], i = bdecode(d, i)
        return out, i + 1
    colon = d.index(b':', i)
    n = int(d[i:colon])
    return d[colon + 1:colon + 1 + n], colon + 1 + n


def manifest(tail):
    """The file list the Blizzard downloader carries at its end: (folder name, [(relative path, length)])."""
    at = tail.rfind(b'd8:announce')
    if at < 0: raise Failed('kein Verzeichnis im Downloader')
    info = bdecode(tail, at)[0][b'info']
    files = []
    for f in info[b'files']:
        parts = [p.decode() for p in f[b'path']]
        if any(p in ('', '.', '..') or '/' in p or '\\' in p for p in parts): raise Failed('kaputtes Verzeichnis im Downloader')
        files.append(('/'.join(parts), f[b'length']))
    name = info[b'name'].decode()
    if '/' in name or name in ('.', '..'): raise Failed('kaputtes Verzeichnis im Downloader')
    return name, files


def helper_state(lines):
    """What d2install.log says (as D2InstallPlan.helperResult/helperState): 'wrong-key', 'ok', a problem, or None (still running)."""
    result = None
    for line in lines:
        parts = line.split()
        if len(parts) < 3: continue
        what, value = parts[1], parts[2]
        if what == 'wrong-key': return 'wrong-key'
        if what == 'child-ended': result = 'ok' if value == '0' else f'Installer endete mit {value}'
        elif what in ('start-failed', 'no-progress', 'start-menu', 'dialog-unknown') or what.startswith('pipe-'): result = result or what
    return result


DRIVE = 'p:'  # data/ as a drive of its own: Z: is the read-only system root, where Wine sees 0 bytes free (the patcher stops)


def dos(path):
    """A Windows path: under data/ on DRIVE, elsewhere on Z:."""
    try: return DRIVE.upper() + '\\' + str(Path(path).relative_to(DATA)).replace('/', '\\').lstrip('.')
    except ValueError: return 'Z:' + str(path).replace('/', '\\')


def patch_result(log, lines):
    """bnupdate.log and d2install.log of a patch run -> 'ok', 'failed: <why>', 'waiting: <windows>' or None (still running)."""
    if 'RESULT:' in log: return 'ok' if 'succeeded' in log.lower() else 'failed: ' + ' '.join(l.strip() for l in log.splitlines() if l.startswith(('ERROR', 'RESULT')))
    if any(' linger-done ' in l for l in lines): return 'failed: der Patcher endete ohne Ergebnis'
    windows = [l.split(' ', 3)[3] for l in lines if ' linger-windows ' in l and len(l.split(' ', 3)) > 3]
    return f'waiting: {windows[-1]}' if len(windows) >= 4 and '#32770' in windows[-1] else None  # a dialog for 90 s and more


# ---- status ----------------------------------------------------------------------------------------------------------
def say(step, text, percent=None, error=None, done=False):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / 'setup.json.part'
    tmp.write_text(json.dumps({'step': step, 'text': text, 'percent': percent, 'error': error, 'done': done, 'at': int(time.time())}))
    tmp.replace(DATA / 'setup.json')
    mark = (step, error, (percent or 0) // 10, text if percent is None and step != 'install' else None)
    if mark == say.__dict__.get('last'): return  # the log gets a line per step and per 10 %, the deck every change
    say.last = mark
    with open(DATA / 'setup.log', 'a') as log: log.write(f'{time.strftime("%F %T")} {step}: {text}{" – " + error if error else ""}\n')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()


def fetch(url, target, limit, https_host=None):
    if https_host and not url.startswith(f'https://{https_host}/'): raise Failed(f'nicht von https://{https_host}')
    part = target.with_name(target.name + '.part')
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as r, open(part, 'wb') as out:
        if r.status != 200 or (https_host and urllib.request.urlparse(r.geturl()).netloc != https_host): raise Failed(f'HTTP {r.status} von {url}')
        got = 0
        while block := r.read(1 << 16):
            got += len(block)
            if got > limit: raise Failed(f'{target.name} zu groß')
            out.write(block)
    part.replace(target)


# ---- Windows programs, unseen ------------------------------------------------------------------------------------------
class Hidden:
    """A Windows program in a headless gamescope of its own (the installers want a display); ended with the prefix."""
    def __init__(self, args, cwd=None):
        env = {k: v for k, v in os.environ.items() if k not in ('DISPLAY', 'WAYLAND_DISPLAY')}
        self.p = subprocess.Popen(['gamescope', '--backend', 'headless', '-w', '1024', '-h', '768', '--', 'wine', *args], cwd=cwd, env=env,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def running(self): return self.p.poll() is None

    def end(self):
        reap()
        try: self.p.wait(10)
        except subprocess.TimeoutExpired: pass


def descendants(pid):
    """Every process below pid, by the kernel's lists of children."""
    out = []
    for task in Path(f'/proc/{pid}/task').glob('*'):
        try: kids = [int(k) for k in (task / 'children').read_text().split()]
        except (OSError, ValueError): continue
        for kid in kids: out += [kid] + descendants(kid)
    return out


def reap():
    """Ends this prefix's Wine and whatever is left below setup.py. Under the Thor's Proton (ARM64) winedevice.exe
    outlives wineserver -k in a session of its own, and gamescope waits for it forever; setup.py is a subreaper (see
    main), so such leftovers are its descendants and go by their PIDs."""
    try: subprocess.run(['wineserver', '-k'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except subprocess.TimeoutExpired: pass
    time.sleep(2)
    for pid in descendants(os.getpid()):
        try: os.kill(pid, signal.SIGKILL)
        except OSError: pass
    try:
        while os.waitpid(-1, os.WNOHANG)[0]: pass  # orphans handed to us: no zombies
    except ChildProcessError: pass


def wine(*args, timeout=120):
    return subprocess.run(['wine', *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout).returncode


# ---- the steps -----------------------------------------------------------------------------------------------------------
def language():
    lang = (DATA / 'language').read_text().strip() if (DATA / 'language').is_file() else 'deDE'
    if lang not in LANGS: raise Failed(f'Sprache {lang} wird nicht unterstützt ({", ".join(LANGS)})')
    return lang


def download(lang, code, title, n, sums):
    folder = INST / code
    if (folder / 'verified').is_file() and (folder / 'verified').read_text() == lang: return
    if folder.exists(): shutil.rmtree(folder)  # another language, or an unfinished download: start clean
    say('download', f'{title}: Blizzard-Downloader wird geholt', 0)
    exe = folder / f'Downloader_{code}.exe'
    fetch(DOWNLOADER.format(lang, code), exe, 32 << 20, 'downloader.battle.net')
    if not 512 << 10 < exe.stat().st_size or exe.read_bytes()[:2] != b'MZ': raise Failed('Downloader unplausibel')
    name, files = manifest(exe.read_bytes()[-(4 << 20):])
    total = sum(length for _, length in files)
    base = folder / name
    run = Hidden([exe.name, f'--saveas={dos(folder)}', '--autolaunch=0'], cwd=folder)
    try:
        last, moved = -1, time.time()
        while True:
            have = sum((base / p).stat().st_size if (base / p).is_file() else (base / (p + '.part')).stat().st_size if (base / (p + '.part')).is_file() else 0
                       for p, _ in files)
            complete = all((base / p).is_file() and (base / p).stat().st_size == length for p, length in files)
            if have != last: last, moved = have, time.time()
            say('download', f'{title} wird geladen ({n}/2): {have >> 20} von {total >> 20} MB', round(100 * have / max(total, 1)))
            if complete: break
            if time.time() - moved > STALL: raise Failed(f'{title}: seit {STALL // 60} Minuten kein Fortschritt beim Laden (Netz?)')
            if not run.running(): raise Failed(f'{title}: der Blizzard-Downloader hat aufgehört')
            time.sleep(3)
    finally:
        run.end()
    say('download', f'{title}: Prüfsummen werden verglichen', 100)
    for key, want in sums.items():
        if key.startswith(code + '/') and sha256(base / key[len(code) + 1:]) != want: raise Failed(f'Prüfsumme falsch: {key} – Download wird verworfen')
    (folder / 'verified').write_text(lang)


def key_pipe(key):
    """A FIFO (0600) in the runtime folder that hands the key over once and is gone right after."""
    path = KEYS.parent / f'd2k-{secrets.token_hex(12)}'
    os.mkfifo(path, 0o600)

    def write():
        try:
            with open(path, 'w') as f: f.write(key + '\n')
        except OSError: pass
        finally:
            try: path.unlink()
            except OSError: pass
    threading.Thread(target=write, daemon=True).start()
    return path


def tools():
    tools = Path(os.environ['WINEPREFIX']) / 'drive_c/D2Install'
    tools.mkdir(parents=True, exist_ok=True)
    for name in ('d2install.exe', 'placeholder-game.exe'): shutil.copy(HERE / 'install' / name, tools / name)
    return tools


def prefix():
    """The Wine prefix, made once, and data/ as its own drive (DRIVE)."""
    if not (Path(os.environ['WINEPREFIX']) / 'system.reg').is_file():
        # a fresh prefix: Proton's wineboot never signals completion on the Thor (an arm32 rundll32 fails), so the
        # first wine call waits forever. The prefix is usable after a few minutes; end the hung boot and go on.
        try: wine('wineboot', '-u', timeout=300)
        except subprocess.TimeoutExpired: pass
        subprocess.run(['wineserver', '-k'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    drive = Path(os.environ['WINEPREFIX']) / 'dosdevices' / DRIVE
    if not drive.is_symlink() or os.readlink(drive) != str(DATA):
        drive.parent.mkdir(parents=True, exist_ok=True)
        drive.unlink(missing_ok=True)
        drive.symlink_to(DATA)


def install_path():
    """Where the second installer and the patch find the game (as the Android app writes it)."""
    for key in (r'HKLM\Software\Blizzard Entertainment\Diablo II', r'HKLM\Software\Wow6432Node\Blizzard Entertainment\Diablo II',
                r'HKCU\Software\Blizzard Entertainment\Diablo II'):
        wine('reg', 'add', key, '/v', 'InstallPath', '/d', dos(GAME) + '\\', '/f')


def run_installer(code, title, n, key, lang):
    folder = INST / code
    exe = next(folder.glob('*/Installer.exe'), None)
    if not exe: raise Failed(f'{title}: Installer.exe fehlt')
    log = tools() / 'd2install.log'
    log.unlink(missing_ok=True)
    pipe = key_pipe(key)
    args = ['C:\\D2Install\\d2install.exe', '1800', '--no-start', '180', '--key-from', dos(pipe), '--run', dos(exe), *INSTALLER_ARGS.split(),
            f'--destination={dos(GAME)}']
    run = Hidden(args, cwd=exe.parent)
    expected = next(f for c, _, f in PRODUCTS if c == code)
    try:
        while run.running():
            state = helper_state(log.read_text('latin-1').splitlines() if log.is_file() else [])
            if state: break  # 'ok' too: under the Thor's Proton (ARM64) the wine process never exits by itself
            size = sum(f.stat().st_size for f in GAME.rglob('*') if f.is_file())
            say('install', f'{title} wird installiert ({n}/2): {size >> 20} MB', None)
            time.sleep(3)
    finally:
        run.end()
        try: pipe.unlink()
        except OSError: pass
    state = helper_state(log.read_text('latin-1').splitlines() if log.is_file() else [])
    if state == 'wrong-key': raise Failed(f'Der CD-Key für {title} wurde abgelehnt – bitte prüfen und neu eingeben.')
    if state in ('no-progress', 'start-menu'): raise Failed(f'Der Installer von {title} hat mit dem Key nicht angefangen (falscher Key oder Key für das andere Spiel?).')
    if not (GAME / expected).is_file(): raise Failed(f'{title}: Installation unvollständig ({state or "kein Ergebnis"})')


def patch_113d(lang):
    """LODPatch_113d.exe (Blizzard PrePatch, then BNUpdate.exe, which writes bnupdate.log) on the 1.14b installation.
    As in the Android app a placeholder (version 1.0.12) stands in for the 1.14b Game.exe, which the patcher would refuse
    as newer; BNUpdate writes the 1.13d Game.exe. The files the patch may change are kept in .before-patch first, and a
    second try puts them back: the patch step can be repeated without the keys."""
    patch = INST / 'LODPatch_113d.exe'
    if not (patch.is_file() and sha256(patch) == PATCH_SHA256):
        say('patch', 'Patch 1.13d wird geladen', None)
        fetch(PATCH_URL, patch, 32 << 20)
        if sha256(patch) != PATCH_SHA256: patch.unlink(); raise Failed('Prüfsumme des Patches 1.13d falsch')
    say('patch', 'Patch 1.13d wird eingespielt', None)
    keep = GAME / '.before-patch'
    small = lambda f: f.is_file() and (not f.name.lower().endswith('.mpq') or f.name.lower() == 'patch_d2.mpq')
    if not (keep / 'names').is_file():
        keep.mkdir(exist_ok=True)
        for f in GAME.iterdir():
            if small(f): shutil.copy2(f, keep / f.name)
        (keep / 'names').write_text('\n'.join(sorted(f.name for f in GAME.iterdir() if f.name != keep.name)))
    else:  # an earlier try: back to the installed state
        names = set((keep / 'names').read_text().splitlines())
        for f in GAME.iterdir():
            if f.name not in names and f.name != keep.name and f.is_file(): f.unlink()
        for f in keep.iterdir():
            if f.name != 'names': shutil.copy2(f, GAME / f.name)
    shutil.copy(tools() / 'placeholder-game.exe', GAME / 'Game.exe')
    shutil.copy(patch, GAME / 'LODPatch_113d.exe')
    log, blog = tools() / 'd2install.log', GAME / 'bnupdate.log'
    log.unlink(missing_ok=True); blog.unlink(missing_ok=True)
    run = Hidden(['C:\\D2Install\\d2install.exe', '600', '--linger', '--run', dos(GAME / 'LODPatch_113d.exe')], cwd=GAME)
    try:
        deadline, result = time.time() + 600, None
        while time.time() < deadline and not (result := patch_result(blog.read_text('latin-1') if blog.is_file() else '',
                                                                     log.read_text('latin-1').splitlines() if log.is_file() else [])):
            time.sleep(3)
        time.sleep(3)  # BNUpdate closes its files after the log line
    finally:
        run.end()
    (GAME / 'LODPatch_113d.exe').unlink(missing_ok=True)
    sums = parse_sums((HERE / 'install' / ('checksums-113d.txt' if lang == 'enUS' else f'checksums-113d-{lang}.txt')).read_text())
    if result != 'ok' and sha256(GAME / 'Game.exe') == sums.get('Game.exe'): result = 'ok'  # as the Android app: the 1.13d Game.exe counts too
    if result is None: raise Failed('Patch 1.13d: nach 10 Minuten kein Ergebnis')
    if result.startswith('waiting'): raise Failed(f'Patch 1.13d wartet auf einen unbekannten Dialog ({result[9:]})')
    if result != 'ok': raise Failed(f'Patch 1.13d fehlgeschlagen – {result[8:]}')


M32 = 0xFFFFFFFF


def _crypt_table():
    t, seed = [0] * 0x500, 0x00100001
    for i in range(0x100):
        for j in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            a = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            t[i + 0x100 * j] = a | (seed & 0xFFFF)
    return t


CRYPT = _crypt_table()


def mpq_hash(name, kind):
    s1, s2 = 0x7FED7FED, 0xEEEEEEEE
    for ch in name.upper().encode('ascii'):
        s1 = CRYPT[kind * 0x100 + ch] ^ ((s1 + s2) & M32)
        s2 = (ch + s1 + s2 + (s2 << 5) + 3) & M32
    return s1


def mpq_crypt(words, key, decrypt):
    seed, out = 0xEEEEEEEE, []
    for w in words:
        seed = (seed + CRYPT[0x400 + (key & 0xFF)]) & M32
        ch = w ^ ((key + seed) & M32)
        out.append(ch)
        key = ((((~key & M32) << 0x15) + 0x11111111) & M32) | (key >> 0x0B)
        seed = ((ch if decrypt else w) + seed + (seed << 5) + 3) & M32
    return out


def hide_attributes(archive):
    """As D2MpqAttributes in the Android app: the 1.14b archives carry an (attributes) file with checksums that 1.13d's
    Storm checks and rejects ("The file data is corrupt"); its hash entry is marked deleted. True if it was there."""
    with open(archive, 'r+b') as f:
        head = f.read(32)
        if struct.unpack_from('<I', head)[0] != 0x1A51504D: raise Failed(f'{archive.name}: kein MPQ')
        pos, count = struct.unpack_from('<I', head, 16)[0], struct.unpack_from('<I', head, 24)[0]
        if count <= 0 or count & (count - 1) or count > 1 << 20: raise Failed(f'{archive.name}: unplausible Hash-Tabelle')
        f.seek(pos)
        raw = f.read(count * 16)
        key = mpq_hash('(hash table)', 3)
        table = mpq_crypt(struct.unpack(f'<{count * 4}I', raw), key, True)
        a, b, i = mpq_hash('(attributes)', 1), mpq_hash('(attributes)', 2), mpq_hash('(attributes)', 0) & (count - 1)
        for _ in range(count):
            block = table[i * 4 + 3]
            if block == 0xFFFFFFFF: return False
            if table[i * 4] == a and table[i * 4 + 1] == b and block != 0xFFFFFFFE:
                table[i * 4 + 3] = 0xFFFFFFFE
                f.seek(pos)
                f.write(struct.pack(f'<{count * 4}I', *mpq_crypt(table, key, False)))
                return True
            i = (i + 1) & (count - 1)
    return False


def check(lang):
    """The 1.13d list: every program file byte for byte, every archive present."""
    sums = parse_sums((HERE / 'install' / ('checksums-113d.txt' if lang == 'enUS' else f'checksums-113d-{lang}.txt')).read_text())
    for name, want in sums.items():
        f = GAME / name
        if not f.is_file(): raise Failed(f'nach dem Patch fehlt {name}')
        if not name.lower().endswith('.mpq') and sha256(f) != want: raise Failed(f'nach dem Patch stimmt {name} nicht (kein 1.13d)')


def import_saves():
    """Saved games put next to data/ beforehand (data/saves-import) are copied in once; nothing is overwritten."""
    src = DATA / 'saves-import'
    if not src.is_dir() or any(SAVES.glob('*.d2s')): return
    SAVES.mkdir(parents=True, exist_ok=True)
    for f in src.rglob('*'):
        rel = f.relative_to(src)
        if f.is_dir() or rel.name.startswith('.d2android-') or (SAVES / rel).exists(): continue
        (SAVES / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, SAVES / rel)
    say('saves', f'Spielstände übernommen: {len(list(SAVES.glob("*.d2s")))} Charaktere', 100)


def wait_for_keys():
    say('keys', 'Alles bereit – es fehlen nur noch die zwei CD-Keys.', None)
    while not KEYS.exists(): time.sleep(1)
    time.sleep(0.5)  # the writer may still be at it
    try: lines = KEYS.read_text().splitlines()
    finally: KEYS.unlink(missing_ok=True)
    keys = [k for k in (clean_key(line) for line in lines) if k]
    if len(keys) != 2: raise Failed('In d2-keys stehen nicht genau zwei gültige CD-Keys (16 oder 26 Zeichen).')
    return keys


def patched_pending():
    """Both installers went through (the keys are no longer needed); the patch step may be repeated."""
    return (GAME / '.patch-pending').is_file() and all((GAME / f).is_file() for _, _, f in PRODUCTS)


def installed():
    return (GAME / '.installed').is_file()


def main():
    if installed(): return 0
    import ctypes
    ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER: orphaned Wine services stay below us, see reap()
    try:
        lang = language()
        sums = parse_sums((HERE / 'install' / f'installer-sha256-{lang}.txt').read_text())
        for n, (code, title, _) in enumerate(PRODUCTS, 1): download(lang, code, title, n, sums)
        prefix()
        if not patched_pending():  # installed by both installers before: only the patch step is left
            keys = wait_for_keys()
            if GAME.exists(): shutil.rmtree(GAME)  # leftovers of a stopped try: never saves (they live in data/save)
            GAME.mkdir(parents=True)
            (GAME / '.installing').write_text(lang)
            install_path()
            for n, ((code, title, _), key) in enumerate(zip(PRODUCTS, keys), 1): run_installer(code, title, n, key, lang)
            keys = key = None
            (GAME / '.patch-pending').write_text(lang)
        install_path()
        patch_113d(lang)
        say('check', 'Spieldateien werden geprüft', None)
        for name in ('d2data.mpq', 'd2char.mpq', 'd2sfx.mpq'): hide_attributes(GAME / name)  # as the Android app (VARYING there)
        check(lang)
        for name in ('.installing', '.patch-pending'): (GAME / name).unlink(missing_ok=True)
        shutil.rmtree(GAME / '.before-patch', ignore_errors=True)
        (GAME / '.installed').write_text(lang)
        shutil.rmtree(INST, ignore_errors=True)  # 2 GB that are not needed any more
        import_saves()
        say('done', 'Diablo II ist installiert.', 100, done=True)
        return 0
    except (Failed, OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        say('error', 'Installation angehalten', None, error=str(error) or type(error).__name__)
        return 1
    finally:
        reap()
        if not installed() and not patched_pending() and GAME.exists(): shutil.rmtree(GAME, ignore_errors=True)  # a second try starts clean


def play():
    """The game (run calls this once everything is in place, with the registry in data/d2.reg): the mod's loader starts Game.exe and ends; the game is over
    when no Game.exe is left below us. Then Wine and its leftover services go (reap)."""
    import ctypes
    ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER, see reap()
    game = lambda: any(b'Game.exe' in Path(f'/proc/{pid}/cmdline').read_bytes() for pid in descendants(os.getpid()) if Path(f'/proc/{pid}').exists())
    try:
        for name in ('d2data.mpq', 'd2char.mpq', 'd2sfx.mpq'): hide_attributes(GAME / name)  # installs from before this step
        wine('regedit', '/S', dos(DATA / 'd2.reg'))  # install and save path (run writes the file)
        subprocess.run(['wine', 'D2Android.exe', '-3dfx'], cwd=GAME)
        started, seen, gone = time.time(), False, 0
        while not (seen and gone >= 3 or not seen and time.time() - started > 60):  # 60 s for Game.exe to show up at all
            time.sleep(1)
            try: up = game()
            except OSError: continue  # a process ended while we looked
            seen, gone = seen or up, 0 if up else gone + 1
    finally:
        try: up = game()
        except OSError: up = True
        if up: save_before_quit()
        reap()
    return 0


def save_before_quit(wait=6):
    """Quit while the game runs (Tandem's Beenden): first the save the Android app does before it exits (PlugY save through
    the mod, command 10 with 0x24), confirmed by a newer character file; without a game in progress nothing is written."""
    newest = lambda: max((f.stat().st_mtime for f in SAVES.glob('*.d2s')), default=0)
    before, end = newest(), time.time() + wait
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s: s.sendto(b'D2AC\x01\x0a\0\0\x24', ('127.0.0.1', 7959))
    while time.time() < end and newest() <= before: time.sleep(.2)
    time.sleep(.5)  # the stash file follows the character


def selftest():
    assert clean_key('abcd-efgh-ijkl-mnop') == 'ABCDEFGHIJKLMNOP' and clean_key('A' * 26) == 'A' * 26
    assert clean_key('A' * 20) is None and clean_key('ABCD-EFGH-IJKL-MNO!') is None and clean_key('') is None
    assert parse_sums('# x\n' + 'a' * 64 + '  D2DV/Installer Tome.mpq\nnonsense\n') == {'D2DV/Installer Tome.mpq': 'a' * 64}
    tail = b'junk d8:announce3:url4:infod5:filesld6:lengthi5e4:pathl1:a5:b.exeeee4:name3:dir12:piece lengthi16384eee'
    assert manifest(tail) == ('dir', [('a/b.exe', 5)])
    try: manifest(b'd8:announce1:u4:infod5:filesld6:lengthi1e4:pathl2:..eee4:name1:xee'); raise AssertionError('.. passed')
    except Failed: pass
    assert helper_state(['1 started 4', '2 child-ended 0']) == 'ok' and helper_state(['1 wrong-key 0']) == 'wrong-key'
    assert helper_state(['1 started 4']) is None and helper_state(['1 no-progress 180']) == 'no-progress'
    assert dos('/var/home/a b') == 'Z:\\var\\home\\a b' and dos(GAME / 'x y.exe') == 'P:\\game\\x y.exe' and dos(DATA) == 'P:\\'
    blog = "This patch upgrades ...\nERROR: unable to open archive 'P:\\game\\Patch_D2.mpq'\nRESULT: Patch failed\n"
    assert patch_result(blog, []) == "failed: ERROR: unable to open archive 'P:\\game\\Patch_D2.mpq' RESULT: Patch failed"
    assert patch_result('RESULT: Patch succeeded', []) == 'ok' and patch_result('', ['1 started 2', '2 child-ended 0']) is None
    assert patch_result('', ['1 linger-done 2']).startswith('failed') and patch_result('', ['1 linger-windows 0 BNUpdateWndClass|B'] * 5) is None
    assert patch_result('', ['1 linger-windows 0 #32770|Blizzard_Updater_v2.72'] * 4) == 'waiting: #32770|Blizzard_Updater_v2.72'
    assert hex(mpq_hash('(hash table)', 3)) == '0xc3af3770' and hex(mpq_hash('(block table)', 3)) == '0xec83b3a3'  # the known MPQ keys
    assert mpq_crypt(mpq_crypt([1, 2, 0xFFFFFFFF], 0x1234, False), 0x1234, True) == [1, 2, 0xFFFFFFFF]
    print('setup.py: ok')
    return 0


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # Tandem's quit: the finally blocks end Wine and clean up
    sys.exit(selftest() if sys.argv[1:] == ['--selftest'] else play() if sys.argv[1:] == ['--play'] else main())
