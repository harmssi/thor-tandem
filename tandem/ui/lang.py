"""English for Tandem's German texts: tr('Spiel beenden') == 'Quit game'. The code stays German; texts are looked up where
they are drawn (tandem_ui.text and friends), so daemon messages and decks follow without changes at their call sites.
en.json holds exact texts and, for texts built at run time, rules (a regex for the whole text; {n} in the English is
group n, translated in turn). The settings web page uses the same file."""
import json, re
from pathlib import Path

_DATA = json.loads(Path(__file__).with_name('en.json').read_text(encoding='utf-8'))
TEXT = _DATA['text']
UPPER = {k.upper(): v.upper() for k, v in TEXT.items()}  # headers drawn with .upper()
RULES = [(re.compile(p), t) for p, t in _DATA['rules']]
_memo = {}


def tr(s):
    """English for a German text; anything unknown (game titles, names, numbers) comes back as it is."""
    if not s or not isinstance(s, str): return s
    hit = _memo.get(s)
    if hit is None:
        if len(_memo) > 5000: _memo.clear()  # clock and counters make new texts all the time
        hit = _memo[s] = _tr(s)
    return hit


def _tr(s):
    if s in TEXT: return TEXT[s]
    core = s.strip()
    if core != s: return s[:len(s) - len(s.lstrip())] + tr(core) + s[len(s.rstrip()):] if core else s
    if s in UPPER: return UPPER[s]
    for rx, t in RULES:
        m = rx.fullmatch(s)
        if m: return re.sub(r'\{(\d)\}', lambda g: tr(m[int(g[1])] or ''), t)
    return s
