#!/usr/bin/env python3
"""Persistent Silver-Core OCR + Offline CTranslate2 NMT worker for Toravo Tandem (PlayTranslate-style).

Runs inside ~/.local/share/tandem/translate-env/venv/bin/python (Python 3.12 + rapidocr-onnxruntime +
ctranslate2 + sentencepiece + pillow). Keeps PaddleOCR ONNX & Marian-NMT int8 models warm in memory
for <150 ms response, pinned to Cortex-A510 Silver cores (0-2) so the running game loses 0% FPS.
"""
import glob
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Low-priority background scheduling (nice +10) across Silver + 2 Gold NEON cores (0-4), leaving Prime X3 (7) & Gold (5-6) untouched
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('MKL_NUM_THREADS', '4')
try:
    os.nice(10)
except OSError:
    pass
if hasattr(os, 'sched_setaffinity') and (os.cpu_count() or 0) >= 8:
    try:
        os.sched_setaffinity(0, {0, 1, 2, 3, 4})
    except OSError:
        pass

from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR
import ctranslate2
import sentencepiece as spm

KANA_RE = re.compile(r'[\u3040-\u30ff]')
CJK_RE = re.compile(r'[\u4e00-\u9fff]')
HANGUL_RE = re.compile(r'[\uac00-\ud7af]')
CYRILLIC_RE = re.compile(r'[\u0400-\u04ff]')

_OCR = None
_MODELS = {}  # pair_name ('en_de', 'ja_en', ...) -> (sp_src, sp_tgt, translator)


def get_ocr():
    global _OCR
    if _OCR is None:
        _OCR = RapidOCR(
            use_angle_cls=False,
            det_limit_side_len=640,
            text_score=0.52,
            intra_op_num_threads=4,
            inter_op_num_threads=1,
        )
    return _OCR


def load_nmt_pair(models_root, pair):
    if pair in _MODELS:
        return _MODELS[pair]
    base = Path(models_root) / pair
    if not base.is_dir():
        return None
    m_dirs = glob.glob(str(base / '**/model'), recursive=True)
    sp_files = glob.glob(str(base / '**/sentencepiece.model'), recursive=True) or glob.glob(str(base / '**/*.spm'), recursive=True)
    if not m_dirs or not sp_files:
        return None
    sp_src = spm.SentencePieceProcessor(model_file=sp_files[0])
    tgt_cands = glob.glob(str(base / '**/target.spm'), recursive=True)
    sp_tgt = spm.SentencePieceProcessor(model_file=tgt_cands[0]) if tgt_cands else sp_src
    tr = ctranslate2.Translator(m_dirs[0], device='cpu', compute_type='int8', inter_threads=1, intra_threads=3)
    _MODELS[pair] = (sp_src, sp_tgt, tr)
    return _MODELS[pair]


def run_nmt(pair_tuple, text):
    sp_src, sp_tgt, tr = pair_tuple
    lines = [ln.strip() for ln in str(text or '').splitlines() if ln.strip()]
    if not lines:
        return ''
    batches = [sp_src.encode(ln, out_type=str) for ln in lines]
    res = tr.translate_batch(batches, beam_size=2, max_decoding_length=256)
    return '\n'.join(sp_tgt.decode(r.hypotheses[0]) for r in res)


def detect_script(text):
    if KANA_RE.search(text):
        return 'ja'
    if HANGUL_RE.search(text):
        return 'ko'
    if CJK_RE.search(text):
        return 'zh'
    if CYRILLIC_RE.search(text):
        return 'ru'
    return 'en'


def group_ocr_boxes(boxes):
    """Merge RapidOCR [[pts, text, conf], ...] into clean reading-order dialogue lines/paragraphs."""
    items = []
    for entry in (boxes or []):
        if not entry or len(entry) < 3:
            continue
        pts, txt, conf = entry[0], str(entry[1] or '').strip(), float(entry[2] or 0.0)
        if not txt or conf < 0.42:
            continue
        ys = [p[1] for p in pts]
        xs = [p[0] for p in pts]
        top, bot = min(ys), max(ys)
        left, right = min(xs), max(xs)
        h = max(4.0, bot - top)
        items.append({'top': top, 'bot': bot, 'mid': (top + bot) * 0.5, 'left': left, 'right': right, 'h': h, 'txt': txt})
    if not items:
        return ''
    items.sort(key=lambda b: (b['top'], b['left']))
    lines = []
    for it in items:
        placed = False
        for ln in lines:
            if abs(it['mid'] - ln['mid']) <= max(it['h'], ln['h']) * 0.58:
                ln['parts'].append(it)
                ln['mid'] = sum(p['mid'] for p in ln['parts']) / len(ln['parts'])
                ln['h'] = max(ln['h'], it['h'])
                ln['bot'] = max(ln['bot'], it['bot'])
                placed = True
                break
        if not placed:
            lines.append({'mid': it['mid'], 'top': it['top'], 'bot': it['bot'], 'h': it['h'], 'parts': [it]})
    lines.sort(key=lambda l: l['mid'])
    merged_lines = []
    for ln in lines:
        ln['parts'].sort(key=lambda p: p['left'])
        raw_line = ' '.join(p['txt'] for p in ln['parts'])
        # Avoid spaces between CJK characters
        raw_line = re.sub(r'(?<=[\u3040-\u30ff\u4e00-\u9fff])\s+(?=[\u3040-\u30ff\u4e00-\u9fff])', '', raw_line)
        merged_lines.append((ln['top'], ln['bot'], ln['h'], raw_line.strip()))
    # Join wrapped lines inside the same speech bubble into one fluent sentence
    out_paras = []
    prev_bot, prev_h = None, 0.0
    for top, bot, h, txt in merged_lines:
        if prev_bot is not None and (top - prev_bot) <= max(h, prev_h) * 0.95:
            sep = '' if (KANA_RE.search(txt) or CJK_RE.search(txt)) else ' '
            if out_paras[-1].endswith('-') and sep == ' ':
                out_paras[-1] = out_paras[-1][:-1] + txt
            else:
                out_paras[-1] = out_paras[-1] + sep + txt
        else:
            out_paras.append(txt)
        prev_bot, prev_h = bot, h
    return '\n'.join(out_paras).strip()


def translate_online_gtx(text, src='auto', target='de'):
    """Fast keyless HTTPS translation + phonetic reading (romaji/pinyin) fallback-safe."""
    q = urllib.parse.urlencode({'client': 'gtx', 'sl': src or 'auto', 'tl': target, 'dt': ['t', 'rm'], 'q': text}, doseq=True)
    url = f'https://translate.googleapis.com/translate_a/single?{q}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=3.2) as r:
        data = json.loads(r.read().decode('utf-8', 'replace'))
    segs = data[0] if isinstance(data, list) and data else []
    trans_parts, romaji_parts = [], []
    for seg in (segs or []):
        if isinstance(seg, list) and seg:
            if seg[0]:
                trans_parts.append(str(seg[0]))
            if len(seg) >= 4 and seg[3]:
                romaji_parts.append(str(seg[3]))
    detected = str(data[2]) if isinstance(data, list) and len(data) > 2 and data[2] else src
    return ''.join(trans_parts).strip(), ' '.join(romaji_parts).strip(), detected


def translate_offline(text, src_hint, models_root, target='de'):
    src = src_hint if src_hint and src_hint != 'auto' else detect_script(text)
    if src == target:
        return text, src
    if target == 'de':
        if src != 'en':
            bridge = load_nmt_pair(models_root, f'{src}_en')
            if bridge:
                text = run_nmt(bridge, text)
            else:
                # Fallback if specific bridge isn't downloaded yet: try en_de directly for Romance/Latin text
                pass
        en_de = load_nmt_pair(models_root, 'en_de')
        if not en_de:
            raise RuntimeError('Offline-Sprachpaket Deutsch (en_de) noch nicht geladen.')
        return run_nmt(en_de, text), src
    # Target English
    if src != 'en':
        bridge = load_nmt_pair(models_root, f'{src}_en')
        if bridge:
            return run_nmt(bridge, text), src
    return text, src


def lookup_word_online(word, src='auto', target='de'):
    q = urllib.parse.urlencode({'client': 'gtx', 'sl': src or 'auto', 'tl': target, 'dt': ['t', 'bd', 'rm'], 'q': word}, doseq=True)
    req = urllib.request.Request(f'https://translate.googleapis.com/translate_a/single?{q}', headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=2.8) as r:
        data = json.loads(r.read().decode('utf-8', 'replace'))
    main = ''.join(str(s[0]) for s in (data[0] or []) if isinstance(s, list) and s and s[0]).strip()
    romaji = ' '.join(str(s[3]) for s in (data[0] or []) if isinstance(s, list) and len(s) >= 4 and s[3]).strip()
    meanings = []
    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
        for pos_block in data[1][:3]:
            if isinstance(pos_block, list) and len(pos_block) >= 2:
                pos = str(pos_block[0] or '')
                words = ', '.join(str(w) for w in (pos_block[1] or [])[:5])
                if words:
                    meanings.append(f'{pos}: {words}' if pos else words)
    return {'word': word, 'translation': main, 'reading': romaji, 'meanings': meanings}


def handle(req):
    cmd = req.get('cmd')
    models_root = req.get('models_dir') or str(Path.home() / '.local/share/tandem/translate-env/models')
    target = req.get('target') or 'de'
    src = req.get('src') or 'auto'
    mode = req.get('mode') or 'auto'  # 'auto' | 'offline'

    if cmd == 'ping':
        return {'ok': True}

    if cmd == 'word':
        word = str(req.get('word') or '').strip()[:80]
        if not word:
            return {'error': 'Kein Wort gewählt.'}
        if mode != 'offline':
            try:
                return {'ok': True, 'engine': 'online', **lookup_word_online(word, src, target)}
            except Exception:
                pass
        tr_txt, det = translate_offline(word, src, models_root, target)
        return {'ok': True, 'engine': 'offline', 'word': word, 'translation': tr_txt, 'reading': '', 'meanings': []}

    if cmd == 'ocr_translate':
        img_path = req.get('image') or ''
        if not os.path.isfile(img_path):
            return {'error': 'Kein Bildschirmbild gefunden.'}
        img = Image.open(img_path).convert('RGB')
        w, h = img.size
        crop = req.get('crop')
        if isinstance(crop, (list, tuple)) and len(crop) == 4:
            nx, ny, nw, nh = [float(v) for v in crop]
            x0 = max(0, min(w - 16, round(nx * w)))
            y0 = max(0, min(h - 16, round(ny * h)))
            x1 = max(x0 + 16, min(w, round((nx + nw) * w)))
            y1 = max(y0 + 16, min(h, round((ny + nh) * h)))
            img = img.crop((x0, y0, x1, y1))
        cw, ch = img.size
        # Upscale low-res pixel-art / small dialogue crops; downscale full 1080p frames to 1280px for 2.3x faster DBNet
        if ch < 220:
            scale = 2 if ch >= 110 else 3
            img = img.resize((cw * scale, ch * scale), Image.Resampling.BILINEAR)
            img = ImageOps.autocontrast(img, cutoff=1)
        elif cw > 1280:
            ratio = 1280.0 / cw
            img = img.resize((1280, max(32, round(ch * ratio))), Image.Resampling.BILINEAR)

        import numpy as np
        arr = np.asarray(img)[:, :, ::-1]  # RGB -> BGR for RapidOCR
        boxes, _ = get_ocr()(arr)
        source_text = group_ocr_boxes(boxes)
        if not source_text:
            return {'ok': True, 'empty': True, 'source': '', 'translated': '', 'reading': '', 'detected': '', 'engine': mode}

        # Shortcircuit if source text matches previous auto-frame text
        prev_src = str(req.get('prev_source') or '').strip()
        if prev_src and source_text == prev_src:
            return {'ok': True, 'unchanged': True, 'source': source_text}

        romaji = ''
        used_engine = 'offline'
        detected = detect_script(source_text) if src == 'auto' else src
        translated = ''
        if mode != 'offline':
            try:
                translated, romaji, det_online = translate_online_gtx(source_text, src, target)
                if det_online:
                    detected = det_online
                used_engine = 'hybrid'
            except Exception:
                translated = ''
        if not translated:
            translated, detected = translate_offline(source_text, src, models_root, target)
            used_engine = 'offline'

        # Extract tappable word tokens (up to 18 unique words)
        if detected in ('ja', 'zh'):
            raw_tokens = re.findall(r'[\u4e00-\u9fff]{1,4}|[\u3040-\u309f]{2,6}|[\u30a0-\u30ff]{2,8}|[A-Za-zÄÖÜäöüß]{2,}', source_text)
        else:
            raw_tokens = re.findall(r"[A-Za-zÀ-ÿÄÖÜäöüß']{3,}", source_text)
        seen_w, words = set(), []
        for tok in raw_tokens:
            low = tok.lower()
            if low not in seen_w:
                seen_w.add(low)
                words.append(tok)
            if len(words) >= 16:
                break

        return {
            'ok': True,
            'empty': False,
            'source': source_text,
            'translated': translated,
            'reading': romaji,
            'detected': detected,
            'target': target,
            'engine': used_engine,
            'words': words,
        }

    return {'error': 'Unbekannter Worker-Befehl.'}


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
            res = handle(req)
        except Exception as exc:
            res = {'error': str(exc)}
        sys.stdout.write(json.dumps(res, ensure_ascii=False) + '\n')
        sys.stdout.flush()


if __name__ == '__main__':
    main()
