"""Thor D2's recipe book for the deck: the Horadric Cube's recipes from the game's own cubemain.bin, sorted as the Android
app sorts them (D2Rezepte, D2Gegenstaende, D2RezeptKatalog.recipe/category/visible/zutat/qualifiers/upgradeName, the
German texts of its rb_* strings). No Qt here: book(read, strings) -> [entry], read gives a file from the game's MPQs.

shortcut: no stat lines of the results (D2Werte) and no chains or other stash pages in the "ready" check
(D2RezeptBestand.chain, pages); upgrade from D2RezeptKatalog.addLines and D2RezeptBestand when the deck needs them.
"""
import re, struct

RECORD, INPUTS, OUTPUTS, MODS, ITEM_RECORD, TYPE_RECORD, PROPERTY_RECORD, RW_RECORD = 328, 7, 3, 5, 424, 228, 46, 288
IN_TYPE, IN_NOSOCKET, IN_SOCKETED, IN_ETHEREAL, IN_NOT_ETHEREAL, IN_UNIQUE_SET, IN_UPGRADED, IN_BASIC, IN_EXCEPTIONAL, IN_ELITE = \
    0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x80, 0x100, 0x200, 0x400
ANY = 0xFFFF
OUT_SOCKETS, OUT_UNSOCKET, OUT_EXCEPTIONAL, OUT_ELITE, OUT_REPAIR, OUT_RECHARGE = 0x2, 0x10, 0x80, 0x100, 0x200, 0x400
KIND_ITEM, KIND_TYPE, KIND_USETYPE, KIND_COW, KIND_PANDEMONIUM, KIND_FINALE = 0xFC, 0xFD, 0xFF, 1, 2, 3
Q_LOW, Q_NORMAL, Q_MAGIC, Q_SET, Q_RARE, Q_UNIQUE, Q_CRAFTED = 1, 2, 4, 5, 6, 7, 8
CAT_RUNES, CAT_GEMS, CAT_CRAFT, CAT_UPGRADE, CAT_QUEST, CAT_RUNEWORD = range(6)
CATEGORIES = ('Runen', 'Steine', 'Handwerk', 'Verbess.', 'Quest', 'Runenw.')
FAMILIES = ('Blut', 'Zauberer', 'Treffer', 'Sicherheit')
FAMILY_GEMS = ('gpr', 'gpv', 'gpb', 'gpg')
SLOT_TYPES = ('helm', 'tors', 'shld', 'glov', 'boot', 'belt', 'amul', 'ring', 'weap')
HIDDEN_OUTPUTS = ('amu', 'rin', 'jav', 'tax', 'aqv', 'cqv', 'yps')
TYPE_LABELS = {'weap': 'Waffe', 'armo': 'Rüstung', 'tors': 'Rüstung', 'helm': 'Helm', 'shld': 'Schild', 'any': 'beliebiger Gegenstand',
               'gem0': 'lädierter Edelstein', 'gem1': 'fehlerhafter Edelstein', 'gem2': 'Edelstein', 'gem3': 'makelloser Edelstein',
               'gem4': 'perfekter Edelstein', 'amul': 'Amulett', 'ring': 'Ring', 'axe': 'Axt', 'blun': 'Hiebwaffe', 'knif': 'Dolch',
               'rod': 'Stab oder Zauberstab', 'spea': 'Speer', 'staf': 'Stab', 'swor': 'Schwert', 'hpot': 'Heiltrank', 'mpot': 'Manatrank',
               'club': 'Keule', 'h2h': 'Klaue', 'hamm': 'Hammer', 'mace': 'Streitkolben', 'mele': 'Nahkampfwaffe', 'miss': 'Bogen oder Armbrust',
               'pala': 'Paladinschild', 'pole': 'Stangenwaffe', 'scep': 'Zepter', 'wand': 'Zauberstab', 'glov': 'Handschuhe',
               'boot': 'Stiefel', 'belt': 'Gürtel'}
TYPE_PICTURES = {'weap': 'lsd', 'armo': 'qui', 'tors': 'qui', 'helm': 'cap', 'shld': 'lrg', 'gem0': 'gcv', 'gem1': 'gfv', 'gem2': 'gsv',
                 'gem3': 'gzv', 'gem4': 'gpv', 'amul': 'amu', 'ring': 'rin', 'axe': 'axe', 'blun': 'mac', 'knif': 'dgr', 'rod': 'wnd',
                 'spea': 'spr', 'staf': 'sst', 'swor': 'lsd', 'hpot': 'hp1', 'mpot': 'mp1', 'club': 'clb', 'h2h': 'ktr', 'hamm': 'whm',
                 'mace': 'mac', 'mele': 'lsd', 'miss': 'sbw', 'pala': 'pa1', 'pole': 'vou', 'scep': 'scp', 'wand': 'wnd'}
QUALITY = {Q_LOW: 'minderwertig', Q_NORMAL: 'normal', Q_MAGIC: 'magisch', Q_RARE: 'selten', Q_UNIQUE: 'einzigartig', Q_SET: 'Set'}
FLAGS = ((IN_BASIC, 'normale Stufe'), (IN_EXCEPTIONAL, 'exzeptionell'), (IN_ELITE, 'Elite'), (IN_ETHEREAL, 'ätherisch'),
         (IN_NOT_ETHEREAL, 'nicht ätherisch'), (IN_NOSOCKET, 'ohne Fassungen'), (IN_SOCKETED, 'mit Fassungen'))
# colours as D2RezeptKatalog's C_WHITE, C_ORANGE
WHITE, ORANGE, GOLD = 0xFFE8E8E8, 0xFFFFA800, 0xFFC7B377
STAT_SOCKETS, F_SOCKETS = 194, 14


def u16(b, at): return struct.unpack_from('<H', b, at)[0]
def s32(b, at): return struct.unpack_from('<i', b, at)[0]
def code(b, at): return b[at:at + 4].split(b'\0')[0].decode('latin-1').strip()


def table(b, size):
    n = s32(b, 0) if b and len(b) >= 4 else -1
    return n if n >= 0 and n * size + 4 == len(b) else -1


def recipes(b):
    """D2Rezepte.lesen: [(enabled, inputs [(flags, item, unique_set, quality, count)], first output)] or None."""
    n = table(b, RECORD)
    if n <= 0: return None
    out = []
    for r in range(n):
        at = 4 + r * RECORD
        if b[at + 0x10] > INPUTS or b[at] > 1: return None
        ins = []
        for k in range(INPUTS):
            i = at + 0x14 + k * 8
            flags, item = u16(b, i), u16(b, i + 2)
            if flags or item: ins.append((flags, item, u16(b, i + 4), b[i + 6], max(1, b[i + 7])))
        first = None
        for k in range(OUTPUTS):
            o = at + 0x4C + k * 84
            if not b[o + 8]: continue
            mods = [s32(b, o + 24 + m * 12) for m in range(MODS)]
            first = {'flags': u16(b, o), 'item': u16(b, o + 2), 'quality': b[o + 6], 'kind': b[o + 8],
                     'prefix': u16(b, o + 12), 'suffix': u16(b, o + 18), 'props': [p for p in mods if p >= 0]}
            break
        out.append((b[at] != 0, ins, first))
    return out


class Items:
    """D2Gegenstaende: weapons, armor and misc in one numbering, with the item types' parents."""
    def __init__(self, weapons, armor, misc, itemtypes):
        self.items, self.by_code = [], {}
        for t in (weapons, armor, misc):
            n = table(t, ITEM_RECORD)
            if n < 0: raise ValueError('Gegenstandstabellen fehlen')
            for i in range(n):
                at = 4 + i * ITEM_RECORD
                it = {'code': code(t, at + 0x80), 'norm': code(t, at + 0x84), 'uber': code(t, at + 0x88), 'ultra': code(t, at + 0x8C),
                      'name': u16(t, at + 0xF4), 'type': u16(t, at + 0x11E), 'type2': u16(t, at + 0x120), 'level': t[at + 0x13F]}
                self.items.append(it)
                if it['code']: self.by_code.setdefault(it['code'], it)
        n = table(itemtypes, TYPE_RECORD)
        if n <= 0: raise ValueError('itemtypes fehlt')
        self.types = [code(itemtypes, 4 + i * TYPE_RECORD) for i in range(n)]
        self.equiv = [(u16(itemtypes, 8 + i * TYPE_RECORD), u16(itemtypes, 10 + i * TYPE_RECORD)) for i in range(n)]

    def get(self, i): return self.by_code.get(i) if isinstance(i, str) else self.items[i] if 0 <= i < len(self.items) else None
    def type_code(self, t): return self.types[t] if 0 <= t < len(self.types) else None

    def is_type(self, t, ancestor, depth=0):
        if t <= 0 or t >= len(self.equiv) or depth > 8: return False
        return t == ancestor or any(self.is_type(e, ancestor, depth + 1) for e in self.equiv[t])

    def item_is(self, it, type_code): return self.item_is_index(it, self.types.index(type_code) if type_code in self.types else -1)
    def item_is_index(self, it, a): return a >= 0 and (self.is_type(it['type'], a) or self.is_type(it['type2'], a))

    @staticmethod
    def tier(it):
        """D2Gegenstaende.Item.tier: 0 normal, 1 exceptional, 2 elite, None without tiers."""
        c, n, u, e = it['code'], it['norm'], it['uber'], it['ultra']
        if not (n and u and e): return None
        if c == n and not (c == u and c == e): return 0
        if c == u and c != n: return 1
        if c == e and c != n and c != u: return 2
        return None


def socket_props(props):
    """The properties (D2Werte.stat) that add sockets: function 14 or the stat 194 in their first used slot."""
    n, found = table(props, PROPERTY_RECORD), set()
    for i in range(max(0, n)):
        at = 4 + i * PROPERTY_RECORD
        for k in range(7):
            func = props[at + 0x18 + k]
            if func:
                if func == F_SOCKETS or u16(props, at + 0x20 + 2 * k) == STAT_SOCKETS: found.add(i)
                break
    return found


def is_rune(c): return len(c) == 3 and c[0] == 'r' and c[1:].isdigit()
def is_gem(c): return len(c) == 3 and ((c[0] == 'g' and c[1] in 'cfslzp' and c[2] in 'vybgrw') or (c.startswith('sk') and c[2] in 'cfulz'))


def last_line(s):
    if not s: return None
    for line in reversed(s.split('\n')):
        t = clean(line)
        if t: return t
    return None


def clean(s):
    """The plain name (D2ItemLabel.plainBase): without the game's colour codes (ÿc + one character) and the German
    grammar tags ([ms], [fs], [pl] ...)."""
    if not s: return None
    s = re.sub(r'\[[a-z]{2}\]|ÿc.', '', s).replace('\n', ' ').strip()
    return s or None


def book(read, strings):
    """The cube's recipes and the runewords: {'entries': [{'cat', 'name', 'colour', 'parts', 'info'}], 'items'}; a part is
    {'n', 'label', 'codes', 'type', 'q', 'flags'} (D2RezeptKatalog.Zutat), a runeword's base also 'base' and 'sockets'."""
    x = 'data\\global\\excel\\'
    rows = recipes(read(x + 'cubemain.bin'))
    if rows is None: raise ValueError('cubemain fehlt')
    items = Items(read(x + 'weapons.bin'), read(x + 'armor.bin'), read(x + 'misc.bin'), read(x + 'itemtypes.bin'))
    sockets = socket_props(read(x + 'properties.bin'))
    name_of = lambda it: last_line(strings.get(it['name'])) or clean(last_line(strings.get(it['code']))) or it['code']
    out = []
    for enabled, ins, o in rows:
        if not enabled or o is None or not ins or o['prefix'] or o['suffix']: continue
        result = items.get(o['item']) if o['kind'] in (KIND_ITEM, KIND_TYPE) else None
        if result and result['code'] in HIDDEN_OUTPUTS: continue
        parts = []
        for flags, item, unique, quality, count in ins:
            part = {'n': count, 'codes': None, 'type': -1, 'q': quality, 'flags': flags}
            if item == ANY: label = 'beliebiger Gegenstand'
            elif flags & IN_TYPE:
                t = items.type_code(item)
                if t is None: break
                label, part['type'] = TYPE_LABELS.get(t, t), item
            else:
                it = items.get(item)
                if it is None: break
                label = name_of(it)
                part['codes'] = [it['norm'], it['uber'], it['ultra']] if flags & IN_UPGRADED and items.tier(it) is not None else [it['code']]
            q = [] if flags & IN_UNIQUE_SET and unique > 0 else ([QUALITY[quality]] if quality in QUALITY else []) + [t for f, t in FLAGS if flags & f]
            part['label'] = f'{label} ({", ".join(q)})' if q else label
            parts.append(part)
        else:
            out.append(entry(o, ins, parts, items, name_of, sockets))
    out += runewords(read(x + 'runes.bin'), items, strings, name_of)
    return {'entries': out, 'items': items}  # the item tables go along for status()


def runewords(b, items, strings, name_of):
    """D2Runenwoerter.lesen + D2RezeptKatalog.runeword: the complete runewords, their runes and the base they go in."""
    n, out = table(b, RW_RECORD), []
    for r in range(max(0, n)):
        at = 4 + r * RW_RECORD
        if not b[at + 0x80]: continue
        name = clean(strings.get(b[at:at + 64].split(b'\0')[0].decode('latin-1')))
        runes = [items.get(s32(b, at + 0x98 + 4 * k)) for k in range(6) if s32(b, at + 0x98 + 4 * k) > 0]
        if not name or not runes or None in runes: continue
        types = [t for t in (u16(b, at + 0x86 + 2 * k) for k in range(6)) if t > 0]
        base = '/'.join(TYPE_LABELS.get(items.type_code(t), items.type_code(t) or '?') for t in types)
        parts = [{'n': 1, 'label': name_of(rune), 'codes': [rune['code']], 'type': -1, 'q': 0, 'flags': 0} for rune in runes]
        parts.append({'n': 1, 'label': f'{base}, {len(runes)} Fassungen', 'codes': None, 'type': -1, 'q': 0, 'flags': 0, 'base': types, 'sockets': len(runes)})
        info = f"Stufe {max(rune['level'] for rune in runes)}" + (' · Ladder' if b[at + 0x81] else '')
        # a ladder runeword is not made in single player (D2RezeptBuch: ladderOn)
        out.append({'cat': CAT_RUNEWORD, 'name': name, 'colour': GOLD, 'parts': parts, 'info': info, 'doable': not b[at + 0x81]})
    return out


def entry(o, ins, parts, items, name_of, sockets):
    """D2RezeptKatalog.recipe: category, the result's name and colour."""
    portal = o['kind'] in (KIND_COW, KIND_PANDEMONIUM, KIND_FINALE)
    result = items.get(o['item']) if o['kind'] == KIND_ITEM else None
    c = result['code'] if result else ''
    cat = CAT_QUEST if portal else (CAT_RUNES if is_rune(c) else CAT_GEMS if is_gem(c) or c in ('rvs', 'rvl') else CAT_QUEST) if o['kind'] == KIND_ITEM \
        else CAT_CRAFT if o['kind'] == KIND_USETYPE and o['quality'] == Q_CRAFTED else CAT_UPGRADE
    flags0, item0 = ins[0][0], ins[0][1]
    if item0 != ANY and not flags0 & IN_TYPE: first = items.get(item0)
    else: first = items.get(TYPE_PICTURES.get(items.type_code(item0) or '', '') if flags0 & IN_TYPE else '')
    info = None
    if cat == CAT_CRAFT:
        codes = {(items.get(i) or {}).get('code') for f, i, *_ in ins if not f & IN_TYPE and i != ANY}
        fam = next((k for k, gem in enumerate(FAMILY_GEMS) if gem in codes), 0)
        slot = next((t for t in SLOT_TYPES if first and items.item_is(first, t)), None)
        info = TYPE_LABELS[slot] if slot else 'beliebiger Gegenstand'
        name, colour = f'{FAMILIES[fam]}-{info}', ORANGE
    elif portal: name, colour = {KIND_COW: 'Portal zum Kuhlevel', KIND_PANDEMONIUM: 'Portal des Pandämonium-Ereignisses'}.get(o['kind'], 'Portal zum Pandämonium-Finale'), WHITE
    elif result: name, colour = name_of(result), ORANGE if is_rune(c) else WHITE
    else:
        f, q, use = o['flags'], o['quality'], o['kind'] == KIND_USETYPE
        name = ('Fassungen leeren (zerstört die Steckteile)' if f & OUT_UNSOCKET else 'Neue magische Eigenschaften' if use and q == Q_MAGIC
                else 'Neue seltene Eigenschaften' if use and q == Q_RARE else 'Elite machen' if f & OUT_ELITE else 'Exzeptionell machen' if f & OUT_EXCEPTIONAL
                else 'Reparieren und aufladen' if f & OUT_RECHARGE else 'Reparieren' if f & OUT_REPAIR
                else 'Fassungen hinzufügen' if f & OUT_SOCKETS or sockets & set(o['props']) else 'Neue magische Eigenschaften' if q == Q_MAGIC
                else 'Neue seltene Eigenschaften' if q == Q_RARE else 'Normale Qualität' if q == Q_NORMAL else 'Verbessern')
        colour = WHITE
    return {'cat': cat, 'name': name, 'colour': colour, 'parts': parts, 'info': info, 'doable': not o['flags'] & (OUT_REPAIR | OUT_RECHARGE)}


def ingredients(e): return ' + '.join(f"{p['n']}x {p['label']}" if p['n'] > 1 else p['label'] for p in e['parts'])


# ---- "what you carry makes it" (D2RezeptBestand.fits/computeLage): the deck's items in inventory, cube and stash
NONE, ALMOST, READY = 0, 1, 4
F_ETHEREAL, F_SOCKETED, F_RUNEWORD = 1, 2, 8


def fits(part, it, items):
    """D2RezeptBestand.fits: it is the deck's item ({'code', 'q', 'flags'}). shortcut: the deck's items carry no socket
    count, so a runeword base only needs to be socketed, empty sockets are not checked; upgrade with D2ItemDetails."""
    base = items.get(it['code'])
    if 'base' in part:
        return bool(base) and 1 <= it['q'] <= 3 and not it['flags'] & F_RUNEWORD and it['flags'] & F_SOCKETED != 0 \
            and any(items.item_is_index(base, t) for t in part['base'])
    if part['codes'] is not None and it['code'] not in part['codes']: return False
    if part['codes'] is None and part['type'] >= 0 and not (base and items.item_is_index(base, part['type'])): return False
    if part['q'] and it['q'] != part['q']: return False
    f, sock, eth = part['flags'], it['flags'] & F_SOCKETED, it['flags'] & F_ETHEREAL
    if f & IN_NOSOCKET and sock or f & IN_SOCKETED and not sock or f & IN_ETHEREAL and not eth or f & IN_NOT_ETHEREAL and eth: return False
    tier = items.tier(base) if base else None
    if f & IN_BASIC and tier != 0 or f & IN_EXCEPTIONAL and tier != 1 or f & IN_ELITE and tier != 2: return False
    return not f & IN_UNIQUE_SET


def status(e, carried, items):
    """computeLage without other stash pages and chains: READY when everything is there, ALMOST when one kind is missing."""
    if not e['doable']: return NONE
    used, lacking = set(), set()
    for k, part in enumerate(e['parts']):
        have = 0
        for i, it in enumerate(carried):
            if have >= part['n']: break
            if i not in used and fits(part, it, items): used.add(i); have += 1
        if have < part['n']: lacking.add(part['codes'][0] if part['codes'] and len(part['codes']) == 1 else f'#{k}')
    return READY if not lacking else ALMOST if len(lacking) == 1 else NONE
