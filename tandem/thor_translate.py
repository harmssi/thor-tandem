"""PlayTranslate-style real-time screen OCR & German game translator for Toravo Tandem.

Features:
- 1-Tap & Auto-Dialogue screen translation from the top OLED (:0) onto the bottom companion screen.
- Per-game crop presets ('bottom', 'top', 'full', or finger-drawn custom [nx, ny, nw, nh] box).
- Lightweight pixel-fingerprint change + typewriter-settle detector in Auto-Mode (0% CPU waste while static).
- Persistent Silver-Core (CPU 0-2) PaddleOCR + CTranslate2 Marian-NMT worker (`thor_ocr_worker.py`),
  supporting 100% offline translation (`en->de`, `ja->de`, `zh->de`, `es->de`, `fr->de`) and hybrid Wi-Fi mode.
- Word-tap dictionary lookup, 30-entry session dialogue log, and German TTS (`espeak-ng`).
"""
import json
import os
import platform
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request
import zipfile
from collections import deque
from pathlib import Path

import companion

HOME = Path.home()
DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share')) / 'tandem'
STATE_DIR = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'tandem'
ENV_DIR = DATA_DIR / 'translate-env'
MODELS_DIR = ENV_DIR / 'models'
PREFS_FILE = STATE_DIR / 'translate-prefs.json'
WORKER_SCRIPT = Path(__file__).with_name('thor_ocr_worker.py')

PRESET_CROPS = {
    'bottom': [0.04, 0.63, 0.92, 0.34],  # Classic JRPG / subtitle dialogue box at bottom
    'top':    [0.04, 0.03, 0.92, 0.33],  # Top-of-screen RPG speech box (Zelda / SNES / GBA)
    'full':   [0.00, 0.00, 1.00, 1.00],  # Entire 1920x1080 screen (menus, item descriptions, visual novels)
}

MODEL_CATALOG = {
    'en_de': ('Deutsch Basis (Englisch → Deutsch)', 'https://argos-net.com/v1/translate-en_de-1_3.argosmodel'),
    'ja_en': ('Japanisch → Deutsch (JRPG / Visual Novel)', 'https://argos-net.com/v1/translate-ja_en-1_1.argosmodel'),
    'zh_en': ('Chinesisch → Deutsch', 'https://argos-net.com/v1/translate-zh_en-1_9.argosmodel'),
    'es_en': ('Spanisch → Deutsch', 'https://argos-net.com/v1/translate-es_en-1_9.argosmodel'),
    'fr_en': ('Französisch → Deutsch', 'https://argos-net.com/v1/translate-fr_en-1_9.argosmodel'),
}

_LOCK = threading.Lock()
_WORKER_LOCK = threading.Lock()
_WORKER = {'proc': None, 'last_used': 0.0}
_INSTALL = {'running': False, 'step': '', 'error': '', 'done_at': 0}
_STATE = {
    'auto': False,
    'mode': 'auto',      # 'auto' (Hybrid) | 'offline' (100% lokal)
    'src': 'auto',       # 'auto' | 'en' | 'ja' | 'zh' | 'es' | 'fr'
    'target': 'de',
    'busy': False,
    'last': None,        # {'source', 'translated', 'reading', 'detected', 'engine', 'words', 'at'}
    'word_info': None,   # {'word', 'translation', 'reading', 'meanings'}
    'error': '',
    'seq': 0,
}
_HISTORY = deque(maxlen=30)
_AUTO_THREAD = None


def venv_python(env_dir=ENV_DIR):
    return Path(env_dir) / 'venv/bin/python'


def installed_models(models_dir=MODELS_DIR):
    mdir = Path(models_dir)
    if not mdir.is_dir():
        return []
    out = []
    for key in MODEL_CATALOG:
        p = mdir / key
        if p.is_dir() and any(p.rglob('model.bin')):
            out.append(key)
    return out


def engine_ready(env_dir=ENV_DIR, models_dir=MODELS_DIR):
    py = venv_python(env_dir)
    return py.is_file() and os.access(py, os.X_OK) and ('en_de' in installed_models(models_dir))


def load_prefs(prefs_file=PREFS_FILE):
    try:
        return json.loads(Path(prefs_file).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_prefs(data, prefs_file=PREFS_FILE):
    pf = Path(prefs_file)
    try:
        pf.parent.mkdir(parents=True, exist_ok=True)
        tmp = pf.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, pf)
    except OSError:
        pass


def game_crop_spec(gid, prefs_file=PREFS_FILE):
    prefs = load_prefs(prefs_file)
    entry = (prefs.get('games') or {}).get(str(gid or 'default')) or {}
    region = entry.get('region') if entry.get('region') in ('bottom', 'top', 'full', 'custom') else 'full'
    box = entry.get('box')
    if region == 'custom' and isinstance(box, list) and len(box) == 4:
        crop = [max(0.0, min(1.0, float(v))) for v in box]
    else:
        crop = list(PRESET_CROPS.get(region, PRESET_CROPS['full']))
    return {'region': region, 'crop': crop}


def set_game_crop(gid, region, box=None, prefs_file=PREFS_FILE):
    if region not in ('bottom', 'top', 'full', 'custom'):
        return {'error': 'Ungültiger Bildbereich.'}
    prefs = load_prefs(prefs_file)
    games = prefs.setdefault('games', {})
    gkey = str(gid or 'default')
    entry = games.setdefault(gkey, {})
    entry['region'] = region
    if region == 'custom' and isinstance(box, (list, tuple)) and len(box) == 4:
        nx = max(0.0, min(0.92, float(box[0])))
        ny = max(0.0, min(0.92, float(box[1])))
        nw = max(0.08, min(1.0 - nx, float(box[2])))
        nh = max(0.08, min(1.0 - ny, float(box[3])))
        entry['box'] = [round(nx, 4), round(ny, 4), round(nw, 4), round(nh, 4)]
    save_prefs(prefs, prefs_file)
    return status(gid, prefs_file=prefs_file)


def status(gid='', env_dir=ENV_DIR, models_dir=MODELS_DIR, prefs_file=PREFS_FILE):
    cs = game_crop_spec(gid, prefs_file=prefs_file)
    mods = installed_models(models_dir)
    with _LOCK:
        return {
            'ready': engine_ready(env_dir, models_dir),
            'models': mods,
            'catalog': [{'id': k, 'title': v[0], 'installed': k in mods} for k, v in MODEL_CATALOG.items()],
            'install': dict(_INSTALL),
            'auto': _STATE['auto'],
            'mode': _STATE['mode'],
            'src': _STATE['src'],
            'target': _STATE['target'],
            'busy': _STATE['busy'],
            'last': _STATE['last'],
            'word_info': _STATE['word_info'],
            'error': _STATE['error'],
            'seq': _STATE['seq'],
            'region': cs['region'],
            'crop': cs['crop'],
            'history': list(_HISTORY),
            'tts_available': bool(shutil.which('espeak-ng')),
        }


def stop_worker():
    with _LOCK:
        _STATE['auto'] = False
    with _WORKER_LOCK:
        proc, _WORKER['proc'] = _WORKER['proc'], None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _call_worker(payload, env_dir=ENV_DIR, models_dir=MODELS_DIR):
    py = venv_python(env_dir)
    if not py.is_file():
        return {'error': 'Übersetzer-Engine ist noch nicht installiert.'}
    req = {**payload, 'models_dir': str(models_dir)}
    with _WORKER_LOCK:
        proc = _WORKER['proc']
        if proc is None or proc.poll() is not None:
            try:
                proc = subprocess.Popen(
                    [str(py), str(WORKER_SCRIPT)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, bufsize=1,
                )
            except OSError as exc:
                return {'error': f'Worker-Start fehlgeschlagen: {exc}'}
            _WORKER['proc'] = proc
        _WORKER['last_used'] = time.time()
        try:
            proc.stdin.write(json.dumps(req, ensure_ascii=False) + '\n')
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                _WORKER['proc'] = None
                return {'error': 'Übersetzer-Worker hat nicht geantwortet.'}
            return json.loads(line)
        except Exception as exc:
            try:
                proc.kill()
            except Exception:
                pass
            _WORKER['proc'] = None
            return {'error': str(exc)}


def _capture_top_screen():
    rt = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/tmp')
    out = rt / f'tandem-translate-{os.getuid()}.png'
    ok = companion.capture_screen_frame(out, display=os.environ.get('DISPLAY') or ':0')
    return out if ok else None


def preview_bytes():
    """Grab a fresh top-screen PNG for the interactive bottom-screen region selector."""
    p = _capture_top_screen()
    if p and p.is_file():
        try:
            return p.read_bytes()
        except OSError:
            return b''
    return b''


def translate_now(gid='', from_auto=False, target_override=None, env_dir=ENV_DIR, models_dir=MODELS_DIR, prefs_file=PREFS_FILE):
    """Capture the top screen, run OCR + German translation on Silver cores, and update dialogue history."""
    if not engine_ready(env_dir, models_dir):
        with _LOCK:
            _STATE['error'] = 'Bitte zuerst das Offline-Sprachpaket installieren (1 Klick).'
        return status(gid, env_dir, models_dir, prefs_file)
    with _LOCK:
        if _STATE['busy']:
            return status(gid, env_dir, models_dir, prefs_file)
        _STATE['busy'] = True
        if not from_auto:
            _STATE['error'] = ''
        mode = _STATE['mode']
        src = _STATE['src']
        target = target_override or _STATE['target']
        prev_src = (_STATE['last'] or {}).get('source', '') if from_auto else ''
    try:
        snap = _capture_top_screen()
        if not snap:
            with _LOCK:
                if not from_auto:
                    _STATE['error'] = 'Oberer Bildschirm konnte nicht gelesen werden.'
            return status(gid, env_dir, models_dir, prefs_file)
        cs = game_crop_spec(gid, prefs_file=prefs_file)
        res = _call_worker({
            'cmd': 'ocr_translate',
            'image': str(snap),
            'crop': cs['crop'],
            'src': src,
            'target': target,
            'mode': mode,
            'prev_source': prev_src,
        }, env_dir=env_dir, models_dir=models_dir)
        with _LOCK:
            if res.get('error'):
                if not from_auto:
                    _STATE['error'] = res['error']
            elif res.get('unchanged'):
                pass
            elif res.get('empty'):
                if not from_auto:
                    _STATE['error'] = 'Kein Text im gewählten Bildbereich erkannt.'
            elif res.get('translated'):
                entry = {
                    'source': res['source'],
                    'translated': res['translated'],
                    'reading': res.get('reading') or '',
                    'detected': res.get('detected') or '',
                    'engine': res.get('engine') or mode,
                    'words': res.get('words') or [],
                    'at': int(time.time()),
                }
                prev_last = _STATE['last']
                _STATE['last'] = entry
                _STATE['word_info'] = None
                _STATE['error'] = ''
                _STATE['seq'] += 1
                if not prev_last or prev_last.get('source') != entry['source']:
                    _HISTORY.appendleft(entry)
    finally:
        with _LOCK:
            _STATE['busy'] = False
    return status(gid, env_dir, models_dir, prefs_file)


def lookup_word(word, gid='', env_dir=ENV_DIR, models_dir=MODELS_DIR, prefs_file=PREFS_FILE):
    w = str(word or '').strip()[:80]
    if not w:
        return status(gid, env_dir, models_dir, prefs_file)
    with _LOCK:
        mode, src, target = _STATE['mode'], _STATE['src'], _STATE['target']
    res = _call_worker({'cmd': 'word', 'word': w, 'src': src, 'target': target, 'mode': mode},
                       env_dir=env_dir, models_dir=models_dir)
    with _LOCK:
        if res.get('ok'):
            _STATE['word_info'] = {
                'word': res.get('word', w),
                'translation': res.get('translation', ''),
                'reading': res.get('reading', ''),
                'meanings': res.get('meanings') or [],
            }
            _STATE['seq'] += 1
    return status(gid, env_dir, models_dir, prefs_file)


def speak(text, lang='de'):
    """Speak German translation aloud via espeak-ng -> PipeWire pw-play / aplay."""
    txt = str(text or '').strip()[:500]
    if not txt or not shutil.which('espeak-ng') or os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        return {'error': 'Sprachausgabe nicht verfügbar.'}
    voice = 'de' if lang == 'de' else 'en'

    def _run():
        try:
            wav = subprocess.run(['espeak-ng', '-v', voice, '-s', '162', '--stdout', txt],
                                 capture_output=True, timeout=8).stdout
            if wav and shutil.which('pw-play'):
                subprocess.run(['pw-play', '-'], input=wav, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            elif wav and shutil.which('aplay'):
                subprocess.run(['aplay', '-q', '-'], input=wav, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
    return {'ok': True}


def _crop_fingerprint(png_path, crop):
    """Tiny 24x12 grayscale fingerprint of the dialogue crop region for zero-overhead change/settle detection."""
    try:
        from PySide6.QtGui import QImage
        img = QImage(str(png_path))
        if img.isNull():
            return b''
        w, h = img.width(), img.height()
        nx, ny, nw, nh = crop
        sub = img.copy(round(nx * w), round(ny * h), max(8, round(nw * w)), max(8, round(nh * h)))
        tiny = sub.scaled(24, 12)
        out = bytearray(24 * 12)
        idx = 0
        for y in range(12):
            for x in range(24):
                px = tiny.pixel(x, y)
                out[idx] = (((px >> 16) & 255) * 3 + ((px >> 8) & 255) * 4 + (px & 255)) >> 3
                idx += 1
        return bytes(out)
    except Exception:
        return b''


def set_options(tandem_obj=None, auto=None, mode=None, src=None, clear_history=False):
    global _AUTO_THREAD
    with _LOCK:
        if isinstance(auto, bool):
            _STATE['auto'] = auto
        if mode in ('auto', 'offline'):
            _STATE['mode'] = mode
        if src in ('auto', 'en', 'ja', 'zh', 'es', 'fr'):
            _STATE['src'] = src
        if clear_history:
            _HISTORY.clear()
            _STATE['last'] = None
            _STATE['word_info'] = None
        want_auto = _STATE['auto']

    if want_auto and tandem_obj is not None and (_AUTO_THREAD is None or not _AUTO_THREAD.is_alive()):
        def _auto_loop():
            prev_fp = b''
            changed_pending = False
            while True:
                time.sleep(1.35)
                with _LOCK:
                    if not _STATE['auto']:
                        return
                run = getattr(tandem_obj, 'run', None)
                if not run or run.get('paused') or getattr(tandem_obj, 'dry', False):
                    continue
                gid = run.get('id') or ''
                snap = _capture_top_screen()
                if not snap:
                    continue
                fp = _crop_fingerprint(snap, game_crop_spec(gid)['crop'])
                if not fp:
                    translate_now(gid, from_auto=True)
                    continue
                diff = companion.frame_motion_diff(prev_fp, fp) if prev_fp else 99.0
                prev_fp = fp
                # Wait for typewriter animation to settle: trigger when frame changed (>2.4) and then stabilized (<3.2)
                if diff >= 2.4:
                    changed_pending = True
                elif changed_pending and diff < 3.2:
                    changed_pending = False
                    translate_now(gid, from_auto=True)

        _AUTO_THREAD = threading.Thread(target=_auto_loop, daemon=True)
        _AUTO_THREAD.start()
    gid_now = ((getattr(tandem_obj, 'run', None) or {}).get('id')) or ''
    return status(gid_now)


def download_model_pair(pair_id, models_dir=MODELS_DIR):
    spec = MODEL_CATALOG.get(pair_id)
    if not spec:
        return {'error': 'Unbekanntes Sprachpaket.'}
    title, url = spec
    mdir = Path(models_dir) / pair_id
    tmp_zip = Path(models_dir) / f'.{pair_id}.zip'
    try:
        Path(models_dir).mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'Toravo-Tandem/1.3'})
        with urllib.request.urlopen(req, timeout=120) as r:
            tmp_zip.write_bytes(r.read())
        shutil.rmtree(mdir, ignore_errors=True)
        mdir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp_zip) as zf:
            for member in zf.namelist():
                if '/stanza/' in member or member.endswith('/stanza'):
                    continue
                zf.extract(member, mdir)
        tmp_zip.unlink(missing_ok=True)
        return {'ok': True, 'id': pair_id, 'title': title}
    except Exception as exc:
        tmp_zip.unlink(missing_ok=True)
        return {'error': f'{title} fehlgeschlagen: {exc}'}


def install_engine(extra_pairs=('ja_en',), env_dir=ENV_DIR, models_dir=MODELS_DIR, blocking=False):
    """1-click installer for uv + standalone Python 3.12 + RapidOCR (PaddleOCR) + CTranslate2 + German models."""
    with _LOCK:
        if _INSTALL['running']:
            return {'ok': True, 'running': True, 'step': _INSTALL['step']}
        _INSTALL.update(running=True, step='Lade ARM64-Laufzeitumgebung (uv) …', error='')

    def _work():
        try:
            edir = Path(env_dir)
            bdir = edir / 'bin'
            bdir.mkdir(parents=True, exist_ok=True)
            uv_bin = bdir / 'uv'
            if not uv_bin.is_file():
                arch = 'aarch64' if platform.machine().lower() in ('aarch64', 'arm64') else 'x86_64'
                uv_url = f'https://github.com/astral-sh/uv/releases/latest/download/uv-{arch}-unknown-linux-gnu.tar.gz'
                tmp_tar = edir / 'uv.tar.gz'
                with urllib.request.urlopen(urllib.request.Request(uv_url, headers={'User-Agent': 'Toravo-Tandem/1.3'}), timeout=60) as r:
                    tmp_tar.write_bytes(r.read())
                with tarfile.open(tmp_tar, 'r:gz') as tf:
                    for m in tf.getmembers():
                        if Path(m.name).name in ('uv', 'uvx') and m.isfile():
                            fobj = tf.extractfile(m)
                            if fobj:
                                out_f = bdir / Path(m.name).name
                                out_f.write_bytes(fobj.read())
                                os.chmod(out_f, 0o755)
                tmp_tar.unlink(missing_ok=True)

            with _LOCK:
                _INSTALL['step'] = 'Richte Python 3.12 & PaddleOCR / CTranslate2 ein …'
            subprocess.run([str(uv_bin), 'venv', '--python', '3.12', '--allow-existing', str(edir / 'venv')],
                           check=True, capture_output=True, timeout=180)
            subprocess.run([str(uv_bin), 'pip', 'install', '--python', str(edir / 'venv/bin/python'),
                            'rapidocr-onnxruntime', 'ctranslate2', 'sentencepiece', 'pillow'],
                           check=True, capture_output=True, timeout=300)

            for pid in ('en_de', *(extra_pairs or ())):
                if pid not in installed_models(models_dir):
                    with _LOCK:
                        _INSTALL['step'] = f'Lade Offline-Sprachpaket: {MODEL_CATALOG[pid][0]} …'
                    r_m = download_model_pair(pid, models_dir=models_dir)
                    if r_m.get('error'):
                        raise RuntimeError(r_m['error'])

            with _LOCK:
                _INSTALL.update(running=False, step='Bereit (Deutsch & Japanisch Offline aktiv)', error='', done_at=int(time.time()))
        except Exception as exc:
            with _LOCK:
                _INSTALL.update(running=False, step='', error=str(exc))

    if blocking:
        _work()
    else:
        threading.Thread(target=_work, daemon=True).start()
    return {'ok': True, 'running': not blocking, 'step': _INSTALL['step']}
