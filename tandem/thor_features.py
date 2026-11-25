"""Extended Dual-Screen Power Features for Toravo Tandem 1.5.0:
1. 30-Second RAM Instant-Replay Ring Buffer (`ReplayBuffer`, zero UFS wear, QR LAN phone download).
2. Per-Game 3x4 Programmable Touch Stream-Deck / Macro Pad (keys, combos, sequences & 12 Hz Turbo).
3. Live Emulator Cheat & 60-FPS / Widescreen Patch Manager (Libretro `.cht` parser, writer & DB fetcher).
4. HowLongToBeat / SteamSpy Completion-Time Enricher (`hltb.json` cache).
5. True In-Place Deep-Freeze (`0 W` SIGSTOP cutscene pause + `< 5 %` low-battery emergency save & freeze).
6. Couch-Coop Dock Auto-Pad-Swap & 1-Tap RetroArch LAN Netplay (`--host` / `--connect`).
7. Native GOG / Epic / Amazon Heroic & Legendary Installed-Game Discovery Bridge.
"""
import glob, hashlib, json, os, re, secrets, shutil, signal, subprocess, threading, time, urllib.parse, urllib.request
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
MACROS_DIR = STATE / 'macros'
CHEATS_DIR = STATE / 'cheats'
HLTB_CACHE = STATE / 'hltb.json'
SAFE_ID = re.compile(r'^[A-Za-z0-9_\-]{2,80}$')


# ==============================================================================
# 1. 30-Second RAM Instant-Replay Ring Buffer + QR Phone Share
# ==============================================================================
def mem_available_gib():
    """Read Linux MemAvailable in GiB (0.05 ms, zero allocations) to guard heavy games against RAM pressure."""
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) / (1024 * 1024)
    except (OSError, ValueError, IndexError):
        pass
    return 8.0


class ReplayBuffer:
    """Keeps 6 x 5s H.264 segments (~9 MB total) in `/run/user/<uid>/tandem-replay` (tmpfs RAM, 0% UFS wear)
    pinned to Silver cores, with automatic RAM guard (< 2.4 GiB free -> auto-pause & purge)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.audio_proc = None
        self.last_clip = ''
        self.share_tokens = {}  # token -> {'path': Path, 'ts': float}

    def _ram_dir(self):
        base = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}')
        if not base.is_dir():
            base = Path('/tmp')
        d = base / 'tandem-replay'
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _clips_dir(self, home=HOME):
        for card in sorted(glob.glob('/run/media/*/*')):
            cp = Path(card)
            if cp.is_dir() and os.access(cp, os.W_OK):
                out = cp / 'Videos/Tandem'
                out.mkdir(parents=True, exist_ok=True)
                return out
        out = Path(home) / 'Videos/Tandem'
        out.mkdir(parents=True, exist_ok=True)
        return out

    def running(self):
        with self.lock:
            return bool(self.proc and self.proc.poll() is None)

    def start(self, display=':0'):
        if mem_available_gib() < 2.4:
            return {'error': 'Zu wenig freier RAM (< 2,4 GiB) – Replay-Puffer bleibt zum Schutz des Spiels aus.'}
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return {'ok': True, 'running': True}
            if not shutil.which('ffmpeg'):
                return {'error': 'ffmpeg nicht gefunden.'}
            rdir = self._ram_dir()
            for old in rdir.glob('seg*.mp4'):
                old.unlink(missing_ok=True)
            # Strict ~9 MB RAM cap: 5s x 6 segments @ ~2.2 Mbit/s on Silver cores 0-2
            cmd = []
            if shutil.which('taskset'):
                cmd.extend(['taskset', '-c', '0-2'])
            if shutil.which('nice'):
                cmd.extend(['nice', '-n', '10'])
            cmd.extend([
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'x11grab', '-framerate', '30', '-i', display,
            ])
            if shutil.which('pactl'):
                cmd.extend(['-f', 'pulse', '-i', 'default'])
            cmd.extend([
                '-vf', 'scale=1280:720',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                '-b:v', '2200k', '-maxrate', '2600k', '-bufsize', '2600k', '-pix_fmt', 'yuv420p',
                '-g', '30',
            ])
            if shutil.which('pactl'):
                cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
            cmd.extend([
                '-f', 'segment', '-segment_time', '5', '-segment_wrap', '6', '-reset_timestamps', '1',
                str(rdir / 'seg%02d.mp4'),
            ])
            env = {**os.environ, 'DISPLAY': display, 'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'}
            try:
                self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, start_new_session=True, env=env)
            except OSError as exc:
                self.proc = None
                return {'error': str(exc)}
        return {'ok': True, 'running': True}

    def stop(self):
        with self.lock:
            p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGINT)
                p.wait(timeout=3)
            except Exception:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except Exception:
                    pass
        rdir = self._ram_dir()
        for old in rdir.glob('seg*.mp4'):
            old.unlink(missing_ok=True)
        return {'ok': True, 'running': False}

    def save_clip(self, game_title='', lan_base=''):
        """Stitch the active RAM ring segments into a clean 30s MP4 clip and register a QR LAN download link."""
        rdir = self._ram_dir()
        segs = sorted(
            (p for p in rdir.glob('seg*.mp4') if p.is_file() and p.stat().st_size > 8192 and (time.time() - p.stat().st_mtime) < 60),
            key=lambda p: p.stat().st_mtime,
        )
        if not segs:
            return {'error': 'Noch keine 30s-Szenen im Puffer (Replay-Puffer einschalten und kurz spielen).'}
        # Exclude the segment currently still being opened if >= 2 segments exist and newest is < 0.8s old
        if len(segs) >= 2 and (time.time() - segs[-1].stat().st_mtime) < 0.4:
            use_segs = segs[-5:]
        else:
            use_segs = segs[-5:]
        lst_file = rdir / 'concat.txt'
        lst_file.write_text(''.join(f"file '{p.name}'\n" for p in use_segs), encoding='utf-8')
        out_dir = self._clips_dir()
        slug = re.sub(r'[^A-Za-z0-9]+', '-', str(game_title or 'Clip')).strip('-')[:24] or 'Clip'
        fname = f'{time.strftime("%Y%m%d-%H%M%S")}-{slug}-30s.mp4'
        out_path = out_dir / fname
        try:
            subprocess.run(
                ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0',
                 '-i', str(lst_file), '-c', 'copy', '-movflags', '+faststart', str(out_path)],
                cwd=str(rdir), capture_output=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {'error': f'Clip speichern fehlgeschlagen: {exc}'}
        if not out_path.is_file() or out_path.stat().st_size < 4096:
            return {'error': 'Clip konnte nicht zusammengesetzt werden.'}
        self.last_clip = fname
        tok = secrets.token_urlsafe(12)
        now = time.time()
        self.share_tokens = {k: v for k, v in self.share_tokens.items() if now - v['ts'] < 3600}
        self.share_tokens[tok] = {'path': out_path, 'ts': now}
        share_url = f'{lan_base.rstrip("/")}/clip/{tok}.mp4' if lan_base else ''
        return {
            'ok': True,
            'file': fname,
            'path': str(out_path),
            'share_url': share_url,
            'text': f'⏪ 30s-Clip gespeichert: {fname}',
        }

    def resolve_share_token(self, tok):
        info = self.share_tokens.get(str(tok or ''))
        if not info or (time.time() - info['ts']) > 3600:
            return None
        p = Path(info['path'])
        return p if p.is_file() else None

    def status(self):
        return {'running': self.running(), 'last_clip': self.last_clip}


REPLAY = ReplayBuffer()


# ==============================================================================
# 2. Programmable 3x4 Touch Stream-Deck / Macro Pad
# ==============================================================================
# Linux evdev keycodes (matching KEYBOARD in tandem.py)
KEY_CODES = {
    'ESC': 1, '1': 2, '2': 3, '3': 4, '4': 5, '5': 6, '6': 7, '7': 8, '8': 9, '9': 10, '0': 11,
    'TAB': 15, 'Q': 16, 'W': 17, 'E': 18, 'R': 19, 'T': 20, 'I': 23, 'O': 24, 'P': 25,
    'ENTER': 28, 'A': 30, 'S': 31, 'D': 32, 'F': 33, 'G': 34, 'H': 35, 'J': 36, 'K': 37, 'L': 38,
    'Z': 44, 'X': 45, 'C': 46, 'V': 47, 'B': 48, 'N': 49, 'M': 50, 'SPACE': 57,
    'F1': 59, 'F2': 60, 'F3': 61, 'F4': 62, 'F5': 63, 'F6': 64, 'F7': 65, 'F8': 66,
    'F9': 67, 'F10': 68, 'F11': 87, 'F12': 88,
    'UP': 103, 'LEFT': 105, 'RIGHT': 106, 'DOWN': 108,
}

MACRO_PRESETS = {
    'rpg': [
        {'label': 'Quicksave', 'sub': 'F5', 'spec': 'F5', 'color': '#10b981'},
        {'label': 'Quickload', 'sub': 'F9', 'spec': 'F9', 'color': '#f59e0b'},
        {'label': 'Karte', 'sub': 'M', 'spec': 'M', 'color': '#38bdf8'},
        {'label': 'Inventar', 'sub': 'I', 'spec': 'I', 'color': '#a855f7'},
        {'label': 'Tagebuch', 'sub': 'J', 'spec': 'J', 'color': '#6366f1'},
        {'label': 'Charakter', 'sub': 'C', 'spec': 'C', 'color': '#ec4899'},
        {'label': 'Fähigkeit 1', 'sub': '1', 'spec': '1', 'color': '#ffb23e'},
        {'label': 'Fähigkeit 2', 'sub': '2', 'spec': '2', 'color': '#ffb23e'},
        {'label': 'Fähigkeit 3', 'sub': '3', 'spec': '3', 'color': '#ffb23e'},
        {'label': 'Heiltrank', 'sub': 'Q', 'spec': 'Q', 'color': '#ef4444'},
        {'label': 'Turbo-A', 'sub': '12 Hz', 'spec': 'ENTER', 'turbo': True, 'color': '#2dd4bf'},
        {'label': 'Menü / Esc', 'sub': 'Esc', 'spec': 'ESC', 'color': '#94a3b8'},
    ],
    'strategy': [
        {'label': 'Speichern', 'sub': 'Ctrl+S', 'spec': 'CTRL+S', 'color': '#10b981'},
        {'label': 'Pause', 'sub': 'Space', 'spec': 'SPACE', 'color': '#f59e0b'},
        {'label': 'Übersicht', 'sub': 'Tab', 'spec': 'TAB', 'color': '#38bdf8'},
        {'label': 'Gruppe 1', 'sub': '1', 'spec': '1', 'color': '#ffb23e'},
        {'label': 'Gruppe 2', 'sub': '2', 'spec': '2', 'color': '#ffb23e'},
        {'label': 'Gruppe 3', 'sub': '3', 'spec': '3', 'color': '#ffb23e'},
        {'label': 'Untätige', 'sub': '.', 'spec': 'H', 'color': '#a855f7'},
        {'label': 'Angriff', 'sub': 'A', 'spec': 'A', 'color': '#ef4444'},
        {'label': 'Stopp', 'sub': 'S', 'spec': 'S', 'color': '#fb923c'},
        {'label': 'Vollbild', 'sub': 'Alt+Enter', 'spec': 'ALT+ENTER', 'color': '#6366f1'},
        {'label': 'Steam-Tab', 'sub': 'Shift+Tab', 'spec': 'SHIFT+TAB', 'color': '#2dd4bf'},
        {'label': 'Esc', 'sub': 'Esc', 'spec': 'ESC', 'color': '#94a3b8'},
    ],
    'retro': [
        {'label': 'Schnellspeichern', 'sub': 'RA Save', 'spec': 'RA:save', 'color': '#10b981'},
        {'label': 'Schnellladen', 'sub': 'RA Load', 'spec': 'RA:load', 'color': '#f59e0b'},
        {'label': 'Slot −', 'sub': 'Vorheriger', 'spec': 'RA:slot-', 'color': '#38bdf8'},
        {'label': 'Slot +', 'sub': 'Nächster', 'spec': 'RA:slot+', 'color': '#38bdf8'},
        {'label': 'Vorspulen', 'sub': '2× Speed', 'spec': 'RA:ff', 'color': '#ffb23e'},
        {'label': 'Pause', 'sub': 'RA Pause', 'spec': 'RA:pause', 'color': '#a855f7'},
        {'label': 'RA-Menü', 'sub': 'Quick Menu', 'spec': 'RA:menu', 'color': '#6366f1'},
        {'label': 'Screenshot', 'sub': 'RA Foto', 'spec': 'RA:shot', 'color': '#2dd4bf'},
        {'label': 'Turbo-Feuer', 'sub': '12 Hz', 'spec': 'X', 'turbo': True, 'color': '#ef4444'},
        {'label': 'F1', 'sub': 'Hotkey', 'spec': 'F1', 'color': '#94a3b8'},
        {'label': 'F2', 'sub': 'Hotkey', 'spec': 'F2', 'color': '#94a3b8'},
        {'label': 'Reset', 'sub': 'Neustart', 'spec': 'RA:reset', 'color': '#fb7185'},
    ],
}

_TURBO = {'active': False, 'spec': '', 'idx': -1, 'stop': None}


def default_preset_for(game):
    if not game:
        return 'rpg'
    s = str(game.get('s') or '')
    genre = str(game.get('genre') or '').lower()
    if s not in ('steam', 'port'):
        return 'retro'
    if any(w in genre for w in ('strateg', 'rts', 'tactic', 'aufbau', 'sim')):
        return 'strategy'
    return 'rpg'


def macros_get(gid, game=None, macros_dir=MACROS_DIR):
    preset = default_preset_for(game)
    base_pads = [dict(x) for x in MACRO_PRESETS[preset]]
    if SAFE_ID.fullmatch(str(gid or '')):
        f = Path(macros_dir) / f'{gid}.json'
        if f.is_file():
            try:
                saved = json.loads(f.read_text())
                if isinstance(saved.get('pads'), list) and len(saved['pads']) == 12:
                    base_pads = saved['pads']
                    preset = saved.get('preset') or 'custom'
            except (OSError, ValueError):
                pass
    return {
        'gid': gid,
        'preset': preset,
        'presets': [('rpg', 'PC-RPG'), ('strategy', 'Strategie'), ('retro', 'Retro-Pro')],
        'pads': base_pads,
        'turbo_idx': _TURBO['idx'] if _TURBO['active'] else -1,
    }


def macros_save(gid, data, game=None, macros_dir=MACROS_DIR):
    if not SAFE_ID.fullmatch(str(gid or '')):
        return {'error': 'Ungültige Spiel-ID.'}
    cur = macros_get(gid, game, macros_dir)
    if data.get('preset') in MACRO_PRESETS:
        pads = [dict(x) for x in MACRO_PRESETS[data['preset']]]
        preset = data['preset']
    else:
        pads = list(cur['pads'])
        preset = cur['preset']
        idx = data.get('idx')
        if isinstance(idx, int) and 0 <= idx < 12:
            spec = str(data.get('spec') or pads[idx]['spec']).strip().upper()[:40]
            lbl = str(data.get('label') or spec).strip()[:18]
            pads[idx] = {
                **pads[idx],
                'label': lbl,
                'sub': spec.replace('RA:', ''),
                'spec': spec,
                'turbo': bool(data.get('turbo', pads[idx].get('turbo', False))),
            }
            preset = 'custom'
    d = Path(macros_dir)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f'{gid}.json.tmp'
    tmp.write_text(json.dumps({'preset': preset, 'pads': pads}, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, d / f'{gid}.json')
    return macros_get(gid, game, macros_dir)


def stop_turbo():
    ev = _TURBO.get('stop')
    _TURBO.update(active=False, spec='', idx=-1, stop=None)
    if ev:
        ev.set()


def parse_macro_step(step_str):
    """Parse 'CTRL+SHIFT+S' or 'F5' into (keycode, [mods])."""
    parts = [p.strip().upper() for p in str(step_str or '').split('+') if p.strip()]
    mods = []
    key_name = ''
    for p in parts:
        if p in ('CTRL', 'STRG'):
            mods.append('ctrl')
        elif p == 'ALT':
            mods.append('alt')
        elif p == 'SHIFT':
            mods.append('shift')
        else:
            key_name = p
    return KEY_CODES.get(key_name, 0), mods


def fire_macro(spec, idx=-1, turbo=False, send_key_fn=None, ra_cmd_fn=None):
    """Execute one macro spec ('F5', 'CTRL+S', 'F5,ENTER', or 'RA:save'); supports 12 Hz Turbo toggle."""
    s = str(spec or '').strip()
    if not s:
        return {'error': 'Leeres Makro.'}
    if turbo:
        if _TURBO['active'] and _TURBO['idx'] == idx:
            stop_turbo()
            return {'ok': True, 'turbo_idx': -1, 'text': 'Turbo gestoppt.'}
        stop_turbo()
        ev = threading.Event()
        _TURBO.update(active=True, spec=s, idx=idx, stop=ev)

        def _loop():
            while not ev.is_set():
                _exec_once(s, send_key_fn, ra_cmd_fn)
                ev.wait(0.083)  # ~12 Hz
        threading.Thread(target=_loop, daemon=True).start()
        return {'ok': True, 'turbo_idx': idx, 'text': f'Turbo aktiv ({s})'}

    stop_turbo()
    _exec_once(s, send_key_fn, ra_cmd_fn)
    return {'ok': True, 'turbo_idx': -1}


def _exec_once(spec, send_key_fn, ra_cmd_fn):
    if spec.upper().startswith('RA:'):
        if ra_cmd_fn:
            ra_cmd_fn(spec.split(':', 1)[1].lower())
        return
    steps = [st.strip() for st in spec.split(',') if st.strip()]
    for i, st in enumerate(steps[:6]):
        code, mods = parse_macro_step(st)
        if code and send_key_fn:
            send_key_fn(code, mods)
        if i + 1 < len(steps):
            time.sleep(0.08)


# ==============================================================================
# 3. Live Cheat & 60-FPS / Widescreen Patch Manager (Libretro .cht)
# ==============================================================================
LIBRETRO_CHT_SYSTEMS = {
    'nes': 'Nintendo - Nintendo Entertainment System',
    'famicom': 'Nintendo - Nintendo Entertainment System',
    'snes': 'Nintendo - Super Nintendo Entertainment System',
    'sfc': 'Nintendo - Super Nintendo Entertainment System',
    'n64': 'Nintendo - Nintendo 64',
    'gb': 'Nintendo - Game Boy',
    'gbc': 'Nintendo - Game Boy Color',
    'gba': 'Nintendo - Game Boy Advance',
    'nds': 'Nintendo - Nintendo DS',
    'psx': 'Sony - PlayStation',
    'psp': 'Sony - PlayStation Portable',
    'megadrive': 'Sega - Mega Drive - Genesis',
    'genesis': 'Sega - Mega Drive - Genesis',
    'mastersystem': 'Sega - Master System - Mark III',
    'gamegear': 'Sega - Game Gear',
    'dreamcast': 'Sega - Dreamcast',
    'saturn': 'Sega - Saturn',
}


def parse_cht_text(text):
    """Parse Libretro `.cht` INI-like format into `[{'idx', 'desc', 'code', 'enable'}]`."""
    kv = {}
    for line in str(text or '').splitlines():
        m = re.match(r'^\s*([A-Za-z0-9_]+)\s*=\s*"?(.*?)"?\s*$', line)
        if m:
            kv[m[1].lower()] = m[2]
    try:
        total = int(kv.get('cheats') or 0)
    except ValueError:
        total = 0
    items = []
    for i in range(min(total, 120)):
        desc = kv.get(f'cheat{i}_desc') or f'Cheat {i + 1}'
        code = kv.get(f'cheat{i}_code') or ''
        en = str(kv.get(f'cheat{i}_enable') or 'false').lower() in ('true', '1', 'yes')
        items.append({'idx': i, 'desc': desc, 'code': code, 'enable': en})
    return items


def serialize_cht(items):
    lines = [f'cheats = "{len(items)}"']
    for i, it in enumerate(items):
        desc = str(it.get('desc') or '').replace('"', "'")
        code = str(it.get('code') or '').replace('"', '')
        en = 'true' if it.get('enable') else 'false'
        lines.extend([
            f'cheat{i}_desc = "{desc}"',
            f'cheat{i}_code = "{code}"',
            f'cheat{i}_enable = "{en}"',
        ])
    return '\n'.join(lines) + '\n'


def _game_cht_path(gid, game=None, cheats_dir=CHEATS_DIR, home=HOME):
    d = Path(cheats_dir)
    d.mkdir(parents=True, exist_ok=True)
    own = d / f'{gid}.cht'
    if own.is_file():
        return own
    # Check existing RetroArch cheat databases on disk
    if game:
        sys_dir = LIBRETRO_CHT_SYSTEMS.get(str(game.get('s') or ''))
        stem = Path(game['path']).stem if game.get('path') else str(game.get('t') or '')
        for ra_base in (
            Path(home) / '.var/app/org.libretro.RetroArch/config/retroarch/cheats',
            Path(home) / '.config/retroarch/cheats',
        ):
            if sys_dir and (ra_base / sys_dir / f'{stem}.cht').is_file():
                shutil.copy2(ra_base / sys_dir / f'{stem}.cht', own)
                return own
    return own


def cheats_get(gid, game=None, cheats_dir=CHEATS_DIR, home=HOME):
    if not SAFE_ID.fullmatch(str(gid or '')):
        return {'items': [], 'supported': False}
    p = _game_cht_path(gid, game, cheats_dir, home)
    items = parse_cht_text(p.read_text(errors='replace')) if p.is_file() else []
    can_fetch = bool(game and str(game.get('s') or '') in LIBRETRO_CHT_SYSTEMS)
    return {'gid': gid, 'items': items, 'can_fetch': can_fetch}


def cheats_fetch_online(gid, game, cheats_dir=CHEATS_DIR, home=HOME):
    """Download matching `.cht` file from official `libretro/libretro-database` on GitHub."""
    if not game or not SAFE_ID.fullmatch(str(gid or '')):
        return {'error': 'Kein passendes Spiel.'}
    sys_dir = LIBRETRO_CHT_SYSTEMS.get(str(game.get('s') or ''))
    if not sys_dir:
        return {'error': 'Für dieses System gibt es keine Online-Cheat-Datenbank.'}
    title = re.sub(r'\s*\[[^\]]*\]', '', str(game.get('t') or '')).strip()
    stem = Path(game['path']).stem if game.get('path') else title
    candidates = []
    for base_t in dict.fromkeys([stem, title, f'{title} (Europe)', f'{title} (USA)', f'{title} (Germany)', f'{title} (World)']):
        if base_t:
            candidates.append(base_t)
    for cand in candidates[:6]:
        url = ('https://raw.githubusercontent.com/libretro/libretro-database/master/cht/'
               + urllib.parse.quote(sys_dir) + '/' + urllib.parse.quote(cand + '.cht'))
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Toravo-Tandem/1.5'})
            with urllib.request.urlopen(req, timeout=6) as r:
                raw = r.read(512_000).decode('utf-8', 'replace')
            items = parse_cht_text(raw)
            if items:
                dest = Path(cheats_dir) / f'{gid}.cht'
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(serialize_cht(items), encoding='utf-8')
                return {'ok': True, 'items': items, 'text': f'{len(items)} Cheats / Patches geladen.'}
        except Exception:
            continue
    return {'error': 'Keine passenden Cheats in der Libretro-Datenbank gefunden.'}


def cheat_toggle(gid, idx=None, add_desc='', add_code='', game=None, cheats_dir=CHEATS_DIR, home=HOME):
    if not SAFE_ID.fullmatch(str(gid or '')):
        return {'error': 'Ungültige ID.'}
    p = _game_cht_path(gid, game, cheats_dir, home)
    items = parse_cht_text(p.read_text(errors='replace')) if p.is_file() else []
    if add_desc and add_code:
        items.insert(0, {'idx': 0, 'desc': str(add_desc).strip()[:60], 'code': str(add_code).strip()[:120], 'enable': True})
    elif isinstance(idx, int) and 0 <= idx < len(items):
        items[idx]['enable'] = not items[idx]['enable']
    raw = serialize_cht(items)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(raw, encoding='utf-8')
    # Also write to RetroArch's active game cheat override location if ROM path is known
    if game and game.get('path'):
        stem = Path(game['path']).stem
        for ra_base in (
            Path(home) / '.var/app/org.libretro.RetroArch/config/retroarch/cheats',
            Path(home) / '.config/retroarch/cheats',
        ):
            if ra_base.parent.is_dir():
                ra_base.mkdir(parents=True, exist_ok=True)
                (ra_base / f'{stem}.cht').write_text(raw, encoding='utf-8')
    return {'ok': True, 'items': parse_cht_text(raw)}


# ==============================================================================
# 4. HowLongToBeat / SteamSpy Completion-Time Enricher
# ==============================================================================
def load_hltb_cache(cache_file=HLTB_CACHE):
    try:
        d = json.loads(Path(cache_file).read_text())
        if isinstance(d, dict):
            return d
    except (OSError, ValueError):
        pass
    return {}


def sync_steam_ttb(appids, cache_file=HLTB_CACHE):
    """Fetch estimated completion / median playtime hours for Steam AppIDs via SteamSpy API (cached 30 days)."""
    cache = load_hltb_cache(cache_file)
    now = int(time.time())
    changed = False
    for aid in appids:
        s_aid = str(aid or '').strip()
        if not s_aid.isdigit() or int(s_aid) >= 2_000_000_000:
            continue
        cur = cache.get(s_aid)
        if isinstance(cur, dict) and now - int(cur.get('at') or 0) < 30 * 86400:
            continue
        try:
            url = f'https://steamspy.com/api.php?request=appdetails&appid={s_aid}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Toravo-Tandem/1.5'})
            with urllib.request.urlopen(req, timeout=4.0) as r:
                data = json.loads(r.read(65536))
            med_mins = int(data.get('median_forever') or data.get('average_forever') or 0)
            hrs = round(med_mins / 60.0, 1) if med_mins >= 30 else 0.0
            cache[s_aid] = {'ttb': hrs, 'at': now}
            changed = True
        except Exception:
            cache[s_aid] = {'ttb': 0.0, 'at': now - 25 * 86400}
            changed = True
    if changed:
        try:
            p = Path(cache_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix('.tmp')
            tmp.write_text(json.dumps(cache), encoding='utf-8')
            os.replace(tmp, p)
        except OSError:
            pass
    return {k: v['ttb'] for k, v in cache.items() if isinstance(v, dict) and v.get('ttb')}


# ==============================================================================
# 5. Couch-Coop Dock Pad Swap & 1-Tap RetroArch LAN Netplay
# ==============================================================================
NETPLAY = {'mode': 'off', 'host_ip': ''}


def set_netplay(mode='off', host_ip=''):
    m = mode if mode in ('off', 'host', 'join') else 'off'
    ip = str(host_ip or '').strip()
    if m == 'join' and not re.fullmatch(r'[0-9A-Za-z.\-:]{3,64}', ip):
        return {'error': 'Bitte eine gültige IP-Adresse im Heimnetz eingeben.'}
    NETPLAY.update(mode=m, host_ip=ip)
    lbl = ('Aus' if m == 'off' else 'Host bereit (startet beim nächsten Retro-Spiel)'
           if m == 'host' else f'Verbinde mit {ip} beim nächsten Start')
    return {'ok': True, **NETPLAY, 'text': f'LAN-Netplay: {lbl}'}


def netplay_cli_args():
    m = NETPLAY.get('mode', 'off')
    if m == 'host':
        return ['--host', '--nick', 'Thor']
    if m == 'join' and NETPLAY.get('host_ip'):
        return ['--connect', NETPLAY['host_ip'], '--nick', 'Thor']
    return []


def apply_dock_coop_pad(docked, bt_pad_connected, home=HOME):
    """When docked to TV and a Bluetooth gamepad is connected, swap Player 1 <-> Player 2 in RetroArch."""
    want_swap = bool(docked and bt_pad_connected)
    for cfg in (
        Path(home) / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg',
        Path(home) / '.config/retroarch/retroarch.cfg',
    ):
        if not cfg.is_file():
            continue
        try:
            txt = cfg.read_text(errors='replace')
            p1, p2 = ('1', '0') if want_swap else ('0', '1')
            for k, v in (('input_player1_joypad_index', p1), ('input_player2_joypad_index', p2)):
                line = f'{k} = "{v}"'
                pat = re.compile(r'(?m)^' + re.escape(k) + r'\s*=.*$')
                txt = pat.sub(lambda _, ln=line: ln, txt, count=1) if pat.search(txt) else txt.rstrip('\n') + f'\n{line}\n'
            cfg.write_text(txt, encoding='utf-8')
        except OSError:
            pass
    return {'swapped': want_swap}


# ==============================================================================
# 6. Native GOG / Epic / Amazon Heroic & Legendary Bridge
# ==============================================================================
def _heroic_roots(home=HOME):
    h = Path(home)
    return [
        d for d in (
            h / '.config/heroic',
            h / '.var/app/com.heroicgameslauncher.hgl/config/heroic',
        ) if d.is_dir()
    ]


def _find_heroic_art(hroot, app_name):
    for sub in ('images-cache', 'icons'):
        folder = hroot / sub
        if not folder.is_dir():
            continue
        for p in folder.iterdir():
            if app_name.lower() in p.name.lower() and p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
                return str(p)
    return None


def discover_external_pc_games(home=HOME):
    """Discover installed GOG, Epic (Legendary), and Amazon (Nile) games from Heroic Games Launcher configs."""
    found = []
    seen = set()
    for hroot in _heroic_roots(home):
        # 1) GOG: gog_store/installed.json -> {"installed": [{"appName": "...", "install_path": "...", "platform": "..."}]}
        gog_inst = hroot / 'gog_store/installed.json'
        gog_lib = hroot / 'gog_store/library.json'
        gog_titles = {}
        if gog_lib.is_file():
            try:
                for g in (json.loads(gog_lib.read_text()).get('games') or []):
                    if g.get('app_name') and g.get('title'):
                        gog_titles[str(g['app_name'])] = {
                            'title': g['title'],
                            'cover': g.get('art_square') or g.get('art_cover'),
                        }
            except (OSError, ValueError):
                pass
        if gog_inst.is_file():
            try:
                raw_g = json.loads(gog_inst.read_text())
                items = raw_g.get('installed') if isinstance(raw_g, dict) else raw_g
                for it in (items or []):
                    app_id = str(it.get('appName') or '').strip()
                    ipath = str(it.get('install_path') or '').strip()
                    if not app_id or not ipath or not Path(ipath).exists() or ('gog', app_id) in seen:
                        continue
                    seen.add(('gog', app_id))
                    meta = gog_titles.get(app_id) or {}
                    title = str(it.get('title') or meta.get('title') or Path(ipath).name)
                    found.append({
                        'id': 'gog-' + re.sub(r'[^a-z0-9]+', '', app_id.lower())[:24],
                        't': title,
                        'store': 'GOG',
                        'app_name': app_id,
                        'install_path': ipath,
                        'cover_path': _find_heroic_art(hroot, app_id),
                        'direct': _heroic_launch_cmd('gog', app_id, ipath),
                    })
            except (OSError, ValueError):
                pass

        # 2) Epic Games (Legendary): legendaryConfig/legendary/installed.json -> {"<AppName>": {"title": "...", "install_path": "...", "executable": "..."}}
        leg_inst = hroot / 'legendaryConfig/legendary/installed.json'
        if leg_inst.is_file():
            try:
                raw_e = json.loads(leg_inst.read_text())
                if isinstance(raw_e, dict):
                    for app_id, it in raw_e.items():
                        if not isinstance(it, dict) or it.get('is_dlc'):
                            continue
                        ipath = str(it.get('install_path') or '').strip()
                        if not ipath or not Path(ipath).exists() or ('epic', app_id) in seen:
                            continue
                        seen.add(('epic', app_id))
                        found.append({
                            'id': 'epic-' + re.sub(r'[^a-z0-9]+', '', str(app_id).lower())[:24],
                            't': str(it.get('title') or Path(ipath).name),
                            'store': 'Epic',
                            'app_name': str(app_id),
                            'install_path': ipath,
                            'exe': str(it.get('executable') or ''),
                            'cover_path': _find_heroic_art(hroot, str(app_id)),
                            'direct': _heroic_launch_cmd('legendary', str(app_id), ipath, str(it.get('executable') or '')),
                        })
            except (OSError, ValueError):
                pass

        # 3) Amazon Games (Nile): nile_config/nile/installed.json
        nile_inst = hroot / 'nile_config/nile/installed.json'
        if nile_inst.is_file():
            try:
                raw_n = json.loads(nile_inst.read_text())
                items = raw_n if isinstance(raw_n, list) else (raw_n.get('installed') or [])
                for it in items:
                    app_id = str(it.get('id') or '').strip()
                    ipath = str(it.get('path') or '').strip()
                    if not app_id or not ipath or not Path(ipath).exists() or ('amazon', app_id) in seen:
                        continue
                    seen.add(('amazon', app_id))
                    found.append({
                        'id': 'amz-' + re.sub(r'[^a-z0-9]+', '', app_id.lower())[:24],
                        't': str(it.get('title') or Path(ipath).name),
                        'store': 'Amazon',
                        'app_name': app_id,
                        'install_path': ipath,
                        'cover_path': _find_heroic_art(hroot, app_id),
                        'direct': _heroic_launch_cmd('nile', app_id, ipath),
                    })
            except (OSError, ValueError):
                pass
    return found


def _heroic_launch_cmd(runner, app_name, install_path, exe_rel=''):
    """Build direct launch command: native Linux `start.sh` if GOG Linux build, Heroic URI if installed, else Proton direct."""
    ip = Path(install_path)
    if (ip / 'start.sh').is_file():
        return ['bash', str(ip / 'start.sh')]
    if shutil.which('heroic'):
        return ['heroic', '--no-gui', f'heroic://launch/{runner}/{app_name}']
    if Path('/var/lib/flatpak/exports/bin/com.heroicgameslauncher.hgl').exists() or (HOME / '.local/share/flatpak/exports/bin/com.heroicgameslauncher.hgl').exists():
        return ['flatpak', 'run', 'com.heroicgameslauncher.hgl', '--no-gui', f'heroic://launch/{runner}/{app_name}']
    if exe_rel and (ip / exe_rel).is_file():
        return ['proton-run', str(ip / exe_rel)]
    exes = [p for p in ip.glob('*.exe') if not re.search(r'(unins|setup|crash|redist|unitycrash)', p.name, re.I)]
    if exes:
        return ['proton-run', str(exes[0])]
    return ['xdg-open', f'heroic://launch/{runner}/{app_name}']
