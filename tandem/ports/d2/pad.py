#!/usr/bin/env python3
"""The controller for Diablo II exactly as Thor D2 (the Android app) has it: run starts this next to the game.

Diablo II has no controller support. Thor D2 reads the pad itself (D2GamepadInput, D2Gamepad, D2TouchOverlay) and plays
through the mod: the left stick walks (the mod's walk command), A attacks the monster the aim assist picks (the mod's
unit command) or takes what is close, the F-skills cast at a picked monster, the triggers drink through the mod, and in
the game's windows the stick moves the pointer. This is that logic in Python, kept as close to the Java as it goes:
names, constants and decisions follow D2Gamepad.java, D2PadTarget.java, D2AutoDrink.java and the pad parts of
D2TouchOverlay.java. Keys and mouse go to the game's X display (XTest), as Thor D2 sends them to its X server.

Layout (Xbox naming, A is the right face button; RB held is the second row):
  left stick walk · A attack/take/talk (RB: F7) · B take, back in windows (RB: F8) · X F1 (RB: F5) · Y F2 (RB: F6)
  R3 F3 (RB: F4; held with the inventory open: sort) · LB swap weapons · LT healing (RB: rejuvenation) · RT mana (RB: names)
  D-pad up map, down town portal, left/right belt 3/4 (RB: belt 4/3/1/2 to the mercenary) · Start game menu
  (held: Tandem's pause) · View inventory (held: the wheel of the game's windows, shown on the deck) · L3 run/walk

Data: the mod sends to D2MOD_APP_PORT (run sets 7957); every packet goes on unchanged to the deck on 7958, and to the
deck also 'D2PD' + (wheel open, entry) while the wheel shows. Commands go to the mod on 7959.
"""
import ctypes, fcntl, heapq, math, os, re, select, socket, struct, sys, time, urllib.request

MOD_IN, DECK, MOD_CMD = 7957, 7958, 7959

# ---- D2Gamepad ------------------------------------------------------------------------------------------------------
A, B, X, Y, LB, RB, VIEW, START, L3, R3, LT, RT, DPAD_LEFT, DPAD_RIGHT, DPAD_DOWN, DPAD_UP, COUNT = range(17)
NAMES = ['A', 'B', 'X', 'Y', 'LB', 'RB', 'View', 'Start', 'L3', 'R3', 'LT', 'RT', '←', '→', '↓', '↑']
# evdev codes of InputPlumber's "Microsoft X-Box 360 pad" on the Thor, measured (tandem.py PAD_KEYS): the Thor prints
# its face buttons Nintendo style, BTN_EAST is the printed A, the button Thor D2 calls A
EVDEV = {305: A, 304: B, 307: X, 308: Y, 310: LB, 311: RB, 314: VIEW, 315: START, 317: L3, 318: R3}
LAYER = RB
# D2TriggerAction
SKILL, HEAL, MANA, REJUV, TAKE, PORTAL, MAP, INVENTORY, ATTACK, NAMES_HELD, SKILL_F1 = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
ESC_MENU, APP_MENU, WEAPON_SWAP, RUN_TOGGLE, ATTACK_OR_TAKE, NOTHING = 18, 19, 20, 21, 22, -2


def default_action(button, layer2):
    """D2Gamepad.defaultAction: the fixed AYN Thor layout."""
    return {A: SKILL_F1 + 6 if layer2 else ATTACK_OR_TAKE, B: SKILL_F1 + 7 if layer2 else TAKE,
            X: SKILL_F1 + 4 if layer2 else SKILL_F1, Y: SKILL_F1 + 5 if layer2 else SKILL_F1 + 1,
            R3: SKILL_F1 + 3 if layer2 else SKILL_F1 + 2, LT: REJUV if layer2 else HEAL, RT: NAMES_HELD if layer2 else MANA,
            LB: WEAPON_SWAP, L3: RUN_TOGGLE, VIEW: INVENTORY}.get(button, NOTHING)


def is_skill_key(act): return SKILL_F1 <= act <= SKILL_F1 + 7


DEADZONE = 15  # DEADZONE_DEFAULT, in percent
TURN_FROM, TURN_DEGREES = .25, 8
LONG_MS = .7
CURSOR_SPEED = 80
POINTER_CROSS_MS, BOOST_AFTER_MS, BOOST_RAMP_MS, BOOST, FULL, RIGHT_STICK = 1200, 400, 600, 1.5, .95, .25
WALK_AFTER_POINTER_MS = .15
TAKE_REACH_OF_HEIGHT = .55
WALK_DISTANCE = .30
WHEEL_INVENTORY, WHEEL_CHARACTER, WHEEL_SKILLS, WHEEL_MAP, WHEEL_QUESTS, WHEEL_MERC, WHEEL_PAUSE, WHEEL_RECIPES = range(8)
ESC_MENU_X, ESC_MENU_HALF_W, ESC_MENU_HALF_H, ESC_MENU_Y, ESC_RETURN = 400, 245, 22, (210, 260, 310), 2
# D2Settings defaults (Thor D2 as installed): aim assist on, reach 25 % (melee) / 75 % of the height, cone 55°, 60° blind
# behind, potions from belt and inventory through the mod, automatic potions at 40 % life / 20 % mana / 20 % rejuvenation
AIM_MELEE, AIM_RANGE, AIM_CONE, AIM_BLIND = 25, 75, 55, 60
AUTO_LIFE, AUTO_MANA, AUTO_REJUV = 40, 20, 20
TELEPORT = 54
CORPSE_SKILLS = {70, 74, 80, 95, 131, 142, 150}  # D2TouchOverlay.CORPSE_SKILLS: cast on corpses, not on monsters
RING_HOLD, RING_STEP = .25, .1  # RING_HOLD_MS; RING_STEP_DP (14 dp) of the ring's radius on the Thor's top screen
NO_UNIT = 0xFFFFFFFF
CMD_NPC, NPC_RESURRECT = 8, 0x1507
# the ring's labels (D2ModState kinds: items ITEM_*, objects OBJECT_*)
ITEM_LABELS = ('Gegenstand', 'Gold', 'Trank', 'Rune', 'Edelstein')
OBJECT_LABELS = ('Objekt', 'Truhe', 'Schrein', 'Wegpunkt', 'Brunnen', 'Portal', 'Eingang', 'Leiche')


def hold_opens_ring(act, in_town, take_close, talking, npc_menu):
    """D2Gamepad.holdOpensRing: B (take) held, or A held in town next to something to take, opens the target ring."""
    if talking or npc_menu: return False
    return act == TAKE or (act == ATTACK_OR_TAKE and in_town and take_close)


def ring_point(x, y, dz=DEADZONE):
    m = math.hypot(x, y)
    if m <= dz / 100: return 0.0, 0.0
    k = min(1.0, m) / m
    return x * k, y * k


def ring_rank(t):
    """D2InteractRank (without the item details of D2ModItems: the state's kind and quality): corpses, travel, people,
    then items by quality, containers last."""
    if t['t'] == UNIT_MONSTER: return 700
    if t['t'] == UNIT_OBJECT: return {7: 900, 5: 800, 3: 800, 6: 800, 1: 100, 2: 100, 4: 100}.get(t['kind'], 0)
    if t['kind'] == 3 or t['q'] in (5, 7): return 600
    if t['q'] in (6, 8): return 500
    if t['q'] == 4: return 400
    return 300 if t['kind'] in (1, 2, 4) else 200


class RingChoice:
    """D2RingChoice: up to 8 targets around the ring; more in pages of 6, with 'next' right and 'back' left."""
    NONE, BACK, NEXT, PLACES = -1, -2, -3, (0, 1, 3, 4, 5, 7)

    def __init__(self, count): self.count, self.page, self.selected, self.armed = max(0, count), 0, -1, True
    def paged(self): return self.count > 8
    def pages(self): return (self.count + 5) // 6 if self.paged() else 1
    def places(self): return 8 if self.paged() else self.count

    def at(self, place):
        if place < 0 or place >= self.places(): return self.NONE
        if not self.paged(): return place
        if place == 2: return self.NEXT
        if place == 6: return self.BACK
        i = self.page * 6 + self.PLACES.index(place)
        return i if i < self.count else self.NONE

    def place_of(self, dx, dy, least):
        n = self.places()
        if n <= 0 or math.hypot(dx, dy) < least: return self.NONE
        return int(math.degrees(math.atan2(dx, -dy)) % 360 / (360 / n) + .5) % n

    def move(self, dx, dy, least):
        """0 nothing changed, 1 another target, 2 another page."""
        place = self.place_of(dx, dy, least)
        if place == self.NONE: self.armed = True
        now, result = self.at(place), 0
        if now in (self.NEXT, self.BACK) and self.armed:
            self.turn(1 if now == self.NEXT else -1)
            self.armed, result = False, 2
        if now != self.selected:
            self.selected = now
            result = result or 1
        return result

    def turn(self, step):
        if not self.paged(): return
        self.page, self.selected = (self.page + step) % self.pages(), self.NONE

    def target(self): return self.selected if self.selected >= 0 else self.NONE


class Stick:
    """D2Gamepad.Stick: a direction only after 25 % and a turn of 8°, so a resting thumb does not jitter the walk."""
    def __init__(self): self.active, self.has, self.dx, self.dy = False, False, 1.0, 0.0

    def update(self, x, y, dz=DEADZONE):
        length, was = math.hypot(x, y), self.active
        self.active = length > dz / 100
        if not self.active:
            self.has = False
            return was
        if length < max(TURN_FROM, dz / 100): return not was
        nx, ny = x / length, y / length
        if self.has and nx * self.dx + ny * self.dy >= math.cos(math.radians(TURN_DEGREES)): return not was
        self.dx, self.dy, self.has = nx, ny, True
        return True


def trigger_down(was, value): return value > .3 if was else value >= .5


def wheel_entry(x, y, dz=DEADZONE):
    if math.hypot(x, y) <= max(.2, dz / 100): return -1
    angle = math.degrees(math.atan2(x, -y)) % 360
    return int((angle + 22.5) / 45) % 8


def pointer_speed(m, vmax, full_for, right, dz=DEADZONE):
    if m <= dz / 100: return 0.0
    t = min(1.0, (m - dz / 100) / (1 - dz / 100))
    v = vmax * t * t
    if full_for > BOOST_AFTER_MS: v *= 1 + (BOOST - 1) * min(1.0, (full_for - BOOST_AFTER_MS) / BOOST_RAMP_MS)
    return v * RIGHT_STICK if right else v


def attack_or_take(talking, npc_menu, in_town, aim_on, monster_picked, monster_in_reach, take_close):
    """D2Gamepad.attackOrTake (no right-bound attack skill on the Thor): 0 skip talk, 1 take line, 2 attack, 3 take."""
    if talking: return 0
    if npc_menu: return 1
    if in_town: return 3 if take_close else 2
    if monster_picked: return 2
    if aim_on and not monster_in_reach and take_close: return 3
    return 2


def iso(dx, dy): return math.hypot(dx, 2 * dy)


def choose(monsters, takes, stick, dx, dy, cone_cos, melee, reach, take_reach, previous):
    """D2PadTarget.choose: candidates are (key, ref, dx, dy, distance, monster, special, behind, first)."""
    KEEP, SPECIAL = 1.15, .9
    inner = inner_prev = None
    inner_score = prev_inner = float('inf')
    for m in monsters:
        if m[4] > melee: continue
        score = m[4] * (SPECIAL if m[6] else 1)
        if m[0] == previous: prev_inner, inner_prev = score, m
        if score < inner_score: inner_score, inner = score, m
    if inner: return ('attack', (inner_prev if inner_prev and prev_inner <= inner_score * KEEP else inner)[1])
    best, best_score, prev_score, prev_c = None, float('inf'), float('inf'), None
    if stick:
        for group, r in ((monsters, reach), (takes, take_reach)):
            for c in group:
                if c[4] > r: continue
                cos = (c[2] * dx + c[3] * dy) / math.hypot(c[2], c[3]) if c[4] > 1 else 1
                if cos < cone_cos: continue
                score = c[4] * (1.5 - cos) * (SPECIAL if c[6] else 1)
                if c[0] == previous: prev_score, prev_c = score, c
                if score < best_score: best_score, best = score, c
        if not best: return ('attack', None)
    else:
        for m in monsters:
            if m[4] > reach or m[7]: continue
            score = m[4] * (SPECIAL if m[6] else 1)
            if m[0] == previous: prev_score, prev_c = score, m
            if score < best_score: best_score, best = score, m
        take = next((t for t in takes if t[4] <= take_reach), None)
        if take and not take[8] and take[0] != previous:
            take = next((t for t in takes if t[0] == previous and t[4] <= take_reach and t[4] <= take[4] * KEEP), take)
        if take:
            if take[0] == previous: prev_score, prev_c = take[4], take
            if take[4] < best_score: best_score, best = take[4], take
        if not best: return ('attack', None)
    if prev_c and prev_score <= best_score * KEEP: best = prev_c
    return ('attack' if best[5] else 'take', best[1])


class AutoDrink:
    """D2AutoDrink.decide, the defaults of Thor D2 (life 40 %, mana 20 %, rejuvenation 20 %, inventory too, no stamina)."""
    def __init__(self):
        self.life_at = self.rejuv_at = self.mana_at = self.rejuv_missing_until = self.life_drunk = self.mana_drunk = -1e9
        self.rejuv_checked, self.life_ref, self.mana_ref, self.lives = True, -1, -1, []

    def decide(self, h, now):
        plan = {}
        self.lives = [(t, v) for t, v in self.lives if now - t <= 1.0] + [(now, h['life'])]
        fast = h['maxLife'] > 0 and (max(v for _, v in self.lives) - h['life']) * 100 >= 10 * h['maxLife']
        if not h['healW'] and now - self.life_at > 1: self.life_ref = -1
        elif h['healW'] and self.life_ref < 0: self.life_ref = h['life']
        if not h['manaW'] and now - self.mana_at > 1: self.mana_ref = -1
        elif h['manaW'] and self.mana_ref < 0: self.mana_ref = h['mana']
        hold = not h['tiers'] and now - self.rejuv_at < .3
        if not self.rejuv_checked and .2 < now - self.rejuv_at < 1 and h['lastDrink'] == 3:
            self.rejuv_checked, self.rejuv_missing_until = True, now + 1
        low_life = h['life'] * 100 < AUTO_LIFE * h['maxLife']
        emergency = h['life'] * 100 < AUTO_REJUV * h['maxLife']
        if low_life or emergency:
            healing = h['cb'][0] + h['ci'][0]
            rejuv = (h['rejuvBelt'] or h['rejuvInv'] != 0) and now > self.rejuv_missing_until and now - self.rejuv_at > .5
            if rejuv and (emergency or (low_life and healing == 0 and not h['healW'])):
                self.rejuv_at, self.rejuv_checked, plan['life'] = now, False, (2, False, False, False)
            elif low_life and healing > 0 and now - self.rejuv_at >= .3 and now - self.life_at > 1:
                low = emergency
                falling = h['healW'] and self.life_ref >= 0 and (self.life_ref - h['life']) * 100 >= 5 * h['maxLife']
                pressure = h['tiers'] and (low or falling or fast)
                drink = None
                if not h['healW']: drink = (0, False, pressure, False)
                elif pressure and 0 < h['tw'][0] < max(h['lb'][0], h['li'][0]): drink = (0, False, True, True)
                if drink: self.life_at = self.life_drunk = now; self.life_ref = h['life']; plan['life'] = drink
        if not hold and h['maxMana'] > 0 and h['mana'] * 100 < AUTO_MANA * h['maxMana'] and now - self.mana_at > 1:
            if h['cb'][1] + h['ci'][1] > 0:
                falling = h['manaW'] and self.mana_ref >= 0 and (self.mana_ref - h['mana']) * 100 >= 5 * h['maxMana']
                pressure = h['tiers'] and (h['mana'] * 200 < AUTO_MANA * h['maxMana'] or falling)
                drink = None
                if not h['manaW']: drink = (1, False, pressure, False)
                elif pressure and 0 < h['tw'][1] < max(h['lb'][1], h['li'][1]): drink = (1, False, True, True)
                if drink: self.mana_at = self.mana_drunk = now; self.mana_ref = h['mana']; plan['mana'] = drink
        return plan

    def tap_dropped(self, kind, now): return now - (self.life_drunk if kind == 0 else self.mana_drunk) < 1 if kind < 2 else False

    def manual(self, kind, now):
        if kind == 0: self.life_at, self.life_ref = now, -1
        elif kind == 1: self.mana_at, self.mana_ref = now, -1
        else: self.rejuv_at, self.rejuv_checked = now, False


# ---- the mod's packets (D2ModState, D2ModItems) ---------------------------------------------------------------------
UI_INVENTORY, UI_NPCMENU, UI_ESCMENU, UI_NPCSHOP = 0x01, 0x08, 0x09, 0x0C
PANELS = (0x01, 0x02, 0x03, 0x04, 0x05, 0x08, 0x09, 0x0B, 0x0C, 0x0E, 0x0F, 0x10, 0x14, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x21, 0x24, 0x25)
UNIT_MONSTER, UNIT_OBJECT, UNIT_ITEM = 1, 2, 4
OBJECT_CORPSE = 7


def parse_state(d):
    """D2ModState's constructor, as far as the pad needs it (to the potion tiers). None for anything else."""
    if len(d) < 8 or d[:4] != b'D2AM' or d[4] != 2 or d[5] != 2: return None
    at = [8]
    def take(fmt):
        v = struct.unpack_from('<' + fmt, d, at[0]); at[0] += struct.calcsize('<' + fmt)
        return v if len(v) > 1 else v[0]
    try:
        s = {}
        s['gw'], s['gh'], s['mx'], s['my'], low, high = take('HHhhII')
        s['ui'] = low | high << 32
        s['level'], s['town'], s['flags'], s['px'], s['py'] = take('HBBhh')
        s['town'] = s['town'] != 0
        take('BB'); take('B'); take('I')  # life and mana in percent, hover type and id
        s['lastDrink'], _ = take('BB')
        s['belt'] = list(take('16B'))
        take('B')
        s['monsters'] = []
        for _ in range(take('B')):
            mid, x, y, hp, flags, n = take('IhhBBB')
            name = d[at[0]:at[0] + n].decode('utf-8', 'replace')
            at[0] += n
            s['monsters'].append({'id': mid, 'x': x, 'y': y, 'flags': flags, 't': UNIT_MONSTER, 'name': name})
        for key, t in (('items', UNIT_ITEM), ('objects', UNIT_OBJECT)):
            s[key] = []
            for _ in range(take('B')):
                tid, x, y, kind, extra = take('IhhBB')
                s[key].append({'id': tid, 'x': x, 'y': y, 'kind': kind, 'q': extra, 't': t})
        s['class'], s['left'], s['right'] = -1, -1, -1
        s['hotkey'], s['hotleft'] = [-1] * 16, [False] * 16
        s.update(life=-1, maxLife=-1, mana=-1, maxMana=-1, talking=False, portals=-1, corpses=[], menu=[], menu_text=[], potions=False,
                 stamina=False, names_without_alt=False, tiers=False, direction=-1)
        if at[0] >= len(d): return s
        s['class'] = take('B')
        sk = lambda v: -1 if v == 0xFFFF else v
        s['left'], s['right'] = sk(take('H')), sk(take('H'))
        for i in range(16):
            v, left = take('HB')
            s['hotkey'][i], s['hotleft'][i] = sk(v), left != 0
        damaged = take('B')  # not in one line with at[0] +=: that reads at[0] before take moves it
        at[0] += 2 * damaged
        if at[0] >= len(d): return s
        s['life'], s['maxLife'], s['mana'], s['maxMana'], bits = take('HHHHB')
        s['talking'] = bits & 8 != 0
        s['portals'] = take('B') if at[0] < len(d) else -1
        if s['portals'] >= 0 and at[0] < len(d):
            for _ in range(take('B')):
                cid, x, y = take('Ihh')
                s['corpses'].append({'id': cid, 'x': x, 'y': y, 't': UNIT_MONSTER})
        lines = take('B') if s['portals'] >= 0 and at[0] < len(d) else 0
        for _ in range(lines):
            mid, n = take('HB')
            s['menu'].append(mid); s['menu_text'].append(d[at[0]:at[0] + n].decode('utf-8', 'replace'))
            at[0] += n
        s['potions'] = s['portals'] >= 0 and at[0] < len(d)
        if s['potions']:
            s['tb'], s['ti'], s['cb'], s['ci'] = [0, 0], [0, 0], [0, 0], [0, 0]
            for k in range(2): s['tb'][k], s['ti'][k], s['cb'][k], s['ci'][k] = take('BBBB')
        s['stamina'] = s['potions'] and at[0] < len(d)
        tier = hover = direction = False
        if s['stamina']:
            *_, sbits = take('HHBB')
            s['healW'], s['manaW'] = sbits & 4 != 0, sbits & 8 != 0
            tier, hover, direction = sbits & 32 != 0, sbits & 64 != 0, sbits & 128 != 0
        hands = s['stamina'] and at[0] < len(d)
        if hands:
            points = take('B'); take('HH')
            s['names_without_alt'] = points & 8 != 0
        s['tiers'] = hands and tier
        tail = (7 if s['tiers'] else 0) + (4 if hands and hover else 0) + (1 if hands and direction else 0)
        if hands and len(d) - at[0] - tail >= 20: at[0] += 20  # world position, mode, level, experience, gold
        if s['tiers']:
            s['lb'], s['li'], s['tw'] = [0, 0], [0, 0], [0, 0]
            for k in range(2): s['lb'][k], s['li'][k], s['tw'][k] = take('BBB')
            s['rejuvInv'] = take('B')
        if hands and hover: take('BBBB')
        if hands and direction:
            v = take('B')
            s['direction'] = v if v < 64 else -1
        return s
    except struct.error:
        return None


def is_open(s, ui): return s is not None and s['ui'] >> ui & 1 == 1
def panels(s): return 0 if s is None else sum(1 << p for p in PANELS if is_open(s, p))
def can_act(s): return s is not None and s['flags'] & 1 != 0
def can_walk(s): return s is not None and s['flags'] & 4 != 0
def npc_menu_open(s): return is_open(s, UI_NPCMENU) and not is_open(s, UI_NPCSHOP)


def cmd(c, payload=b''): return b'D2AC' + bytes((1, c)) + b'\0\0' + payload


TRACE = open(os.environ['D2PAD_TRACE'], 'a', buffering=1) if os.environ.get('D2PAD_TRACE') else None  # run: data/pad-trace switches it on


def trace(*what):
    if TRACE: TRACE.write(f'{time.monotonic():.3f} ' + ' '.join(map(str, what)) + '\n')


CMD_DRINK, CMD_UNIT, CMD_HIGHLIGHT, CMD_WALK, CMD_PAUSE, CMD_PORTAL, CMD_TAKE, CMD_SORT, CMD_SELL = 1, 2, 3, 4, 6, 7, 15, 24, 30
PHASE_DOWN, PHASE_HOLD, PHASE_UP, PHASE_CLICK = 0, 1, 2, 3


# ---- keys and mouse into the game's X display (XTest) ---------------------------------------------------------------
class Display:
    def __init__(self):
        self.x = ctypes.CDLL('libX11.so.6')
        self.t = ctypes.CDLL('libXtst.so.6')
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.x.XDefaultRootWindow.restype = ctypes.c_ulong
        self.x.XStringToKeysym.restype = ctypes.c_ulong
        self.d = ctypes.c_void_p(self.x.XOpenDisplay(None))
        if not self.d: raise OSError('no X display')
        self.root = ctypes.c_ulong(self.x.XDefaultRootWindow(self.d))
        self.w, self.h = self.x.XDisplayWidth(self.d, 0), self.x.XDisplayHeight(self.d, 0)
        self.codes = {}

    def key(self, name, down):
        trace('key', name, 'down' if down else 'up')
        if name not in self.codes: self.codes[name] = self.x.XKeysymToKeycode(self.d, ctypes.c_ulong(self.x.XStringToKeysym(name.encode())))
        self.t.XTestFakeKeyEvent(self.d, self.codes[name], 1 if down else 0, 0)
        self.x.XFlush(self.d)

    def button(self, n, down):
        trace('mouse', n, 'down' if down else 'up')
        self.t.XTestFakeButtonEvent(self.d, n, 1 if down else 0, 0)
        self.x.XFlush(self.d)

    def move(self, x, y):
        trace('move', int(x), int(y))
        self.t.XTestFakeMotionEvent(self.d, -1, int(max(0, min(self.w - 1, x))), int(max(0, min(self.h - 1, y))), 0)
        self.x.XFlush(self.d)

    def pointer(self):
        r, c = ctypes.c_ulong(), ctypes.c_ulong()
        rx, ry, wx, wy, m = ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_uint()
        self.x.XQueryPointer(self.d, self.root, ctypes.byref(r), ctypes.byref(c), ctypes.byref(rx), ctypes.byref(ry),
                             ctypes.byref(wx), ctypes.byref(wy), ctypes.byref(m))
        return rx.value, ry.value


# ---- the pad as Thor D2 plays it -------------------------------------------------------------------------------------
NONE_, WALK_, ATTACK_, SKILL_, PICKUP_ = range(5)


class Pad:
    def __init__(self, out, display, send, now=time.monotonic):
        self.out, self.dpy, self.send_raw, self.now = out, display, send, now
        self.timers, self.seq = [], 0
        self.s, self.s_at, self.take_possible, self.sell_possible = None, 0, False, False
        self.down, self.layer2_at_press = [False] * COUNT, [False] * COUNT
        self.long_done, self.deferred, self.long_token = [False] * COUNT, [False] * COUNT, [0] * COUNT
        self.layer2 = False
        self.stick = Stick()
        self.lx = self.ly = self.rx = self.ry = 0.0
        self.trig = [0.0, 0.0]
        self.hat = [0, 0]
        self.joystick = self.has_dir = False
        self.dir = (1.0, 0.0)
        self.face = None
        self.action, self.walk_direct, self.attack_walking, self.direct = NONE_, False, False, False
        self.attack_id = self.skill_id = 0
        self.skill_left = self.skill_first_pending = False
        self.skill_early = -1
        self.skill_now, self.skill_owner, self.a_target, self.missing = -1, None, None, 0
        self.walk_token = self.alive_token = 0
        self.pickup_id, self.pickup_dir, self.pickup_start, self.pickup_token = 0, (1.0, 0.0), 0, 0
        self.lmb = self.rmb = self.shift = self.alt = False
        self.held = [None] * COUNT  # per button: what its release ends ('attack', 'skill', 'names', 'lmb', 'rmb')
        self.pointer_at = self.pointer_tick = self.pointer_full = 0
        self.rest = [0.0, 0.0]
        self.wheel_open, self.wheel = False, -1
        self.paused = False
        self.esc_seen = False
        self.end_talk = None  # [started, last, sent, signature, pending]
        self.esc_at = -1
        self.retarget_at = 0
        self.drink = AutoDrink()
        self.ticking = False
        self.attack_kind = -1
        self.on_corpses, self.corpse_at = False, 0  # skillOnCorpses, corpseClickAt
        self.ring, self.ring_targets, self.ring_owner, self.ring_act, self.ring_token = None, [], None, NOTHING, 0
        self.ring_by_a = self.ring_swallow_a = False  # padRingTakenByA, padRingSwallowA
        self.ring_npc, self.ring_lines = False, None  # the NPC ring: the menu lines (ids, texts) it shows
        self.ring_follow, self.follow = False, None  # D2NpcRing.Follow: (the chosen list's ids, until) for the next list
        self.lit, self.lit_at = NO_UNIT, 0  # what the mod highlights (D2TouchOverlay.updateHighlight), sent at

    # timers: (due, seq, fn)
    def later(self, delay, fn):
        self.seq += 1
        heapq.heappush(self.timers, (self.now() + delay, self.seq, fn))

    def run_due(self):
        while self.timers and self.timers[0][0] <= self.now(): heapq.heappop(self.timers)[2]()

    def next_due(self): return self.timers[0][0] - self.now() if self.timers else None

    # ---- output
    def send(self, c, payload=b''):
        if c != CMD_WALK and not (c == CMD_UNIT and payload[1] == PHASE_HOLD): trace('cmd', c, payload.hex())
        self.send_raw(cmd(c, payload))

    def walk(self, phase, dx=0, dy=0):
        if phase != PHASE_HOLD: trace('walk', phase, int(dx), int(dy))
        self.send(CMD_WALK, struct.pack('<BBhh', phase, 0, int(round(dx)), int(round(dy))))

    def unit(self, button, phase, kind, uid): self.send(CMD_UNIT, struct.pack('<BBBBII', button, phase, 0, 0, kind, uid & 0xFFFFFFFF))

    def press_key(self, name):
        if self.alt: self.dpy.key('Alt_L', False)
        self.dpy.key(name, True); self.dpy.key(name, False)
        if self.alt: self.dpy.key('Alt_L', True)

    def set_lmb(self, down):
        if self.lmb != down: self.lmb = down; self.dpy.button(1, down)

    def set_rmb(self, down):
        if self.rmb != down: self.rmb = down; self.dpy.button(3, down)

    def set_shift(self, down):
        if self.shift != down: self.shift = down; self.dpy.key('Shift_L', down)

    def deck(self): self.send_raw(b'D2PD' + bytes((1 if self.wheel_open else 0, self.wheel if self.wheel >= 0 else 255)), DECK)

    # game pixels <-> X pixels: D2DX scales the 960x540 game to the screen, kept in proportion and centred
    def mapping(self):
        s = self.s
        gw, gh = (s['gw'], s['gh']) if s and s['gw'] > 0 and s['gh'] > 0 else (960, 540)
        k = min(self.dpy.w / gw, self.dpy.h / gh)
        return k, (self.dpy.w - gw * k) / 2, (self.dpy.h - gh * k) / 2, gw, gh

    def to_desktop(self, gx, gy):
        k, ox, oy, _, _ = self.mapping()
        return ox + gx * k, oy + gy * k

    def aim_point(self, dx, dy, share):
        """D2TouchOverlay.aimPoint: from the middle of the picture, share x its height along the stick."""
        _, _, _, gw, gh = self.mapping()
        return self.to_desktop(gw / 2 + dx * gh * share, gh / 2 + dy * gh * share)

    def monster_point(self, m): return self.to_desktop(m['x'], m['y'] - 14)  # TARGET_LIFT

    # ---- state
    def packet(self, data):
        if len(data) >= 9 and data[:4] == b'D2AM' and data[5] == 4: self.take_possible, self.sell_possible = data[8] & 16 != 0, data[8] & 64 != 0
        kind = attack_kind(data)
        if kind is not None: self.attack_kind = kind
        s = parse_state(data)
        if s is None: return
        self.s, self.s_at = s, self.now()
        self.on_state(s)

    def fresh(self): return self.s if self.s is not None and self.now() - self.s_at < .5 else None

    def on_state(self, s):
        now = self.now()
        self.update_facing(s)
        if self.action == SKILL_ and self.on_corpses: self.track_corpse(s)
        elif self.action in (ATTACK_, SKILL_) and self.direct: self.track_direct(self.action == ATTACK_)
        if self.ring_npc: self.npc_ring_lines(s)
        elif self.follow_due(s):  # openNpcFollowRing: the game's next list follows in the ring, A takes
            self.ring, self.ring_targets, self.ring_npc, self.ring_lines, self.ring_follow = RingChoice(0), [], True, None, True
            self.npc_ring_lines(s)
        self.highlight()
        if self.action == PICKUP_ and not any(t['id'] == self.pickup_id for t in s['items'] + s['objects'] + s['monsters']):
            self.finish_pickup()
        open_ = is_open(s, UI_ESCMENU)
        if open_ and not self.esc_seen and not self.paused: self.esc_menu_to(ESC_RETURN)
        self.esc_seen = open_
        self.end_talk_step(s, now)
        if s['stamina'] and not s['town'] and not self.paused and not open_ and s['life'] > 0 and s['maxLife'] > 0:
            h = {'life': s['life'], 'maxLife': s['maxLife'], 'mana': s['mana'], 'maxMana': s['maxMana'], 'healW': s['healW'],
                 'manaW': s['manaW'], 'cb': s['cb'], 'ci': s['ci'], 'rejuvBelt': 3 in s['belt'], 'lastDrink': s['lastDrink'],
                 'tiers': s['tiers'], 'lb': s.get('lb', [0, 0]), 'li': s.get('li', [0, 0]), 'tw': s.get('tw', [0, 0]),
                 'rejuvInv': s.get('rejuvInv', -1)}
            plan = self.drink.decide(h, now)
            for drink in (plan.get('life'), plan.get('mana')):
                if drink: self.send(CMD_DRINK, bytes((drink[0], (1 if drink[1] else 0) | (4 if drink[2] else 0) | (8 if drink[3] else 0))))

    def update_facing(self, s):
        if s['town']: self.face = None; return
        if self.joystick and self.has_dir: self.face = self.dir; return
        if s['direction'] >= 0:
            a = s['direction'] * 2 * math.pi / 64 + math.pi / 4
            wx, wy = math.cos(a), math.sin(a)
            sx, sy = wx - wy, (wx + wy) / 2
            n = math.hypot(sx, sy)
            self.face = (sx / n, sy / n)

    # ---- aim assist (D2TouchOverlay.pickTarget, interactCandidates, closeTakeCandidate, padChoice)
    def melee(self, skill):
        return skill in H2H or (skill in BOTH and self.attack_kind == 0)

    def behind(self, dx, dy):
        n = math.hypot(dx, dy)
        if not self.face or n < 1: return False
        return -(dx * self.face[0] + dy * self.face[1]) / n >= math.cos(math.radians(AIM_BLIND / 2))

    def pick_target(self, skill):
        s = self.fresh()
        if s is None or s['town']: return None
        reach = s['gh'] * (AIM_MELEE if self.melee(skill) else AIM_RANGE) / 100
        cone = math.cos(math.radians(AIM_CONE))
        best, best_score = None, float('inf')
        for m in s['monsters']:
            if m['flags'] & 16: continue
            dx, dy = m['x'] - s['px'], m['y'] - s['py']
            dist = iso(dx, dy)
            if dist > reach: continue
            score = dist
            if self.joystick and self.has_dir and dist > 1:
                cos = (dx * self.dir[0] + dy * self.dir[1]) / math.hypot(dx, dy)
                if cos < cone: continue
                score = dist * (1.5 - cos)
            elif self.behind(dx, dy): continue
            if m['flags'] & 11: score *= .9
            if score < best_score: best, best_score = m, score
        return best

    def candidates(self):
        """interactCandidates(ORDER_TAP): items a little preferred, corpses first, town people, nearest first."""
        s = self.fresh()
        if s is None: return []
        reach, scored = s['gh'] * TAKE_REACH_OF_HEIGHT, []
        for t in s['items']:
            dist = iso(t['x'] - s['px'], t['y'] - s['py'])
            if dist <= reach: scored.append((dist * .8, t))
        for t in s['objects']:
            dist = iso(t['x'] - s['px'], t['y'] - s['py'])
            if dist <= reach: scored.append((-1 if t['kind'] == OBJECT_CORPSE else dist, t))
        for m in s['monsters']:
            if not s['town'] and not m['flags'] & 16: continue
            dist = iso(m['x'] - s['px'], m['y'] - s['py'])
            if dist <= reach: scored.append((dist, m))
        return [t for _, t in sorted(scored, key=lambda x: x[0])]

    def close_take(self):
        s = self.fresh()
        for t in self.candidates():
            if iso(t['x'] - s['px'], t['y'] - s['py']) <= s['gh'] * TAKE_REACH_OF_HEIGHT: return t
        return None

    def in_reach(self, skill):
        s = self.fresh()
        if s is None or s['town']: return False
        reach = s['gh'] * (AIM_MELEE if self.melee(skill) else AIM_RANGE) / 100
        return any(iso(m['x'] - s['px'], m['y'] - s['py']) <= reach for m in s['monsters'] if not m['flags'] & 16)

    def pad_choice(self):
        s = self.fresh()
        monsters, takes = [], []
        for m in s['monsters']:
            if m['flags'] & 16: continue
            dx, dy = m['x'] - s['px'], m['y'] - s['py']
            monsters.append(((1 << 32) | m['id'], m, dx, dy, iso(dx, dy), True, m['flags'] & 11 != 0, self.behind(dx, dy), False))
        for t in self.candidates():
            dx, dy = t['x'] - s['px'], t['y'] - s['py']
            takes.append(((t['t'] << 32) | t['id'], t, dx, dy, iso(dx, dy), False, False, False, t.get('kind') == OBJECT_CORPSE and t['t'] == UNIT_OBJECT))
        h = s['gh']
        return choose(monsters, takes, self.joystick and self.has_dir, self.dir[0], self.dir[1], math.cos(math.radians(AIM_CONE)),
                      h * AIM_MELEE / 100, h * (AIM_MELEE if self.melee(s['left']) else AIM_RANGE) / 100, h * TAKE_REACH_OF_HEIGHT, -1)

    # ---- modes
    def pointer_mode(self):
        """D2Gamepad.pointerMode: windows open, an NPC menu or the cursor holding an item -> the stick is a pointer."""
        if self.paused: return False
        s = self.fresh()
        return s is None or panels(s) != 0 or npc_menu_open(s)

    def may_take(self): return not self.paused and not self.pointer_mode()

    # ---- buttons (D2GamepadInput.press and D2TouchOverlay.padButton)
    def press(self, b, pressed):
        if self.down[b] == pressed: return
        if TRACE and self.s: trace('state', 'mouse', self.s['mx'], self.s['my'], 'x', *self.dpy.pointer(), 'panels', hex(panels(self.s)), 'level', self.s['level'], 'monsters', len(self.s['monsters']), 'age', round(self.now() - self.s_at, 2))
        trace('pad', NAMES[b], 'down' if pressed else 'up', 'RB' if self.down[LAYER] else '')
        self.down[b] = pressed
        if pressed and self.paused and b in (A, START):  # padResume: A or Start ends the pause
            self.set_paused(False)
            self.held[b] = 'swallowed'
            return
        if not pressed and self.held[b] == 'swallowed':
            self.held[b] = None
            return
        if b == LAYER:
            self.layer2 = pressed
            return
        if DPAD_LEFT <= b <= DPAD_UP:
            if pressed: self.belt(b - DPAD_LEFT, self.down[LAYER])
            return
        if b in (START, VIEW):
            self.long_or_short(b, pressed)
            return
        if pressed: self.layer2_at_press[b] = self.down[LAYER]
        if (pressed and b == R3 and is_open(self.fresh(), UI_INVENTORY)) or (not pressed and self.deferred[b]):
            self.held_sorts(b, pressed)
            return
        self.pad_button(b, default_action(b, self.layer2_at_press[b]), pressed)

    def long_or_short(self, b, pressed):
        if pressed:
            self.long_done[b] = False
            self.layer2_at_press[b] = self.down[LAYER]
            self.long_token[b] += 1
            token = self.long_token[b]
            def fire():
                if not self.down[b] or self.long_token[b] != token: return
                self.long_done[b] = True
                if b == VIEW: self.open_wheel()
                else: self.app_menu()
            self.later(LONG_MS, fire)
            return
        self.long_token[b] += 1
        if self.long_done[b]:
            if b == VIEW: self.close_wheel(True)
            return
        if b == START: self.fixed(ESC_MENU)
        else:
            act = default_action(b, self.layer2_at_press[b])
            self.pad_button(b, act, True); self.pad_button(b, act, False)

    def held_sorts(self, b, pressed):
        if pressed:
            self.deferred[b], self.long_done[b] = True, False
            self.long_token[b] += 1
            token = self.long_token[b]
            def fire():
                if not self.down[b] or self.long_token[b] != token: return
                self.long_done[b] = True
                self.sort()
            self.later(LONG_MS, fire)
            return
        self.deferred[b] = False
        self.long_token[b] += 1
        if self.long_done[b]: return
        act = default_action(b, self.layer2_at_press[b])
        self.pad_button(b, act, True); self.pad_button(b, act, False)

    def pad_button(self, b, act, down):
        if down and b == B and self.back(): return
        if not down and self.held[b] in ('lmb', 'rmb'):
            (self.set_lmb if self.held[b] == 'lmb' else self.set_rmb)(False)
            self.held[b] = None
            return
        if b == A and self.ring and self.ring_owner != A:  # A takes what the ring shows
            if down: self.ring_swallow_a = self.ring_by_a = True; self.ring_take()
            return
        if not down and b == A and self.ring_swallow_a:
            self.ring_swallow_a = False
            return
        click = {A: 1, X: 2}.get(b, 0)
        if down and click and self.pointer_mode():
            self.click(b, click)
            return
        if not down and self.ring_owner == b:
            self.take_release()
            return
        if down and self.paused: return
        if down and self.take_holds(act):
            self.take_press(b, act)
            return
        self.run_action(b, act, down)

    # ---- the target ring (padTakeHolds, padTakePress, openPadRing, padRingTake, padTakeRelease): B held shows what is
    # close around the player on the deck, the stick picks, the game highlights the pick, letting go (or A) takes it
    def take_holds(self, act):
        s = self.fresh()
        town = bool(s and s['town'])
        return hold_opens_ring(act, town, act == ATTACK_OR_TAKE and town and self.close_take() is not None,
                               bool(s and s['talking']), npc_menu_open(s))

    def take_press(self, b, act):
        self.ring_owner, self.ring_act, self.ring_by_a, self.held[b] = b, act, False, None
        self.ring_token += 1
        token = self.ring_token
        self.later(RING_HOLD, lambda: token == self.ring_token and self.ring_owner == b and self.open_ring())

    def open_ring(self):
        s = self.fresh()
        if self.ring or not self.may_take() or s is None or s['talking'] or npc_menu_open(s): return
        found = self.candidates()
        if found and found[0]['t'] == UNIT_MONSTER and s['town']:  # openNpcRing: talk to him, his menu lines follow
            self.ring, self.ring_targets, self.ring_npc, self.ring_lines = RingChoice(0), [], True, None
            trace('npc ring: talking to', found[0]['id'])
            self.pad_stick(False)
            self.start_pickup(found[0])
            return self.ring_deck()
        if len(found) < 2: return
        rank = {id(t): -ring_rank(t) * 100000 + min(iso(t['x'] - s['px'], t['y'] - s['py']), 99999) for t in found}
        self.ring_targets = sorted(found, key=lambda t: rank[id(t)])
        self.ring = RingChoice(len(found))
        trace('ring open', len(found), 'targets')
        self.pad_stick(False)
        self.ring_deck()

    def npc_ring_lines(self, s):
        """npcRingLines: the menu's lines (and 'cancel') around the ring once the game shows them; closed when the menu
        goes or shows other lines."""
        menu = npc_menu_open(s)
        if self.ring_lines and (not menu or self.ring_lines != (s['menu'], s['menu_text'])): return self.close_ring()
        if self.ring_lines or not menu or not s['menu']: return
        self.ring_lines = (s['menu'], s['menu_text'])
        self.ring_targets = list(range(len(s['menu']))) + [-1]
        self.ring = RingChoice(len(self.ring_targets))
        trace('npc ring:', len(s['menu']), 'lines')
        self.ring_deck()

    def ring_take(self):
        i = self.ring.target() if self.ring else -1
        chosen = self.ring_targets[i] if 0 <= i < len(self.ring_targets) else None
        if self.ring_npc: return self.npc_ring_take(chosen)
        self.close_ring()
        trace('ring', 'takes', chosen['id'] if chosen else 'nothing')
        if chosen: self.start_pickup(chosen)

    def follow_due(self, s):
        if not self.follow: return False
        if self.now() > self.follow[1] or s['talking'] or not npc_menu_open(s):
            self.follow = None
            return False
        if not s['menu'] or s['menu'] == self.follow[0]: return False
        self.follow = None
        return True

    def npc_ring_take(self, line):
        """npcRingTake: a line goes to the mod (it picks it in the game's menu); 'cancel' or nothing ends the talk."""
        shown, s = bool(self.ring_targets), self.fresh()
        if self.ring_follow and shown and line is None and npc_menu_open(s):  # nothing chosen: the next list stays
            self.ring = RingChoice(len(self.ring_targets))
            return self.ring_deck()
        self.close_ring()
        if not shown: return trace('npc ring: let go before the menu')
        if line is not None and line >= 0 and npc_menu_open(s):
            trace('npc ring: line', line)
            self.follow = (list(s['menu']), self.now() + 1.5)
            return self.send(CMD_NPC, bytes((line,)))
        if s and (npc_menu_open(s) or s['talking']): self.press_key('Escape')

    def close_ring(self):
        if self.ring is None: return
        self.ring, self.ring_targets, self.ring_npc, self.ring_lines, self.ring_follow = None, [], False, None, False
        self.highlight()
        self.ring_deck()

    def take_release(self):
        self.ring_token += 1
        self.ring_owner = None
        if self.ring_by_a: self.ring_by_a = False; return
        if self.ring: self.ring_take(); return
        if not self.may_take(): return
        if self.ring_act == TAKE: self.trigger(TAKE)
        else:
            close = self.close_take()
            if close: self.start_pickup(close)

    def ring_deck(self):
        """To the deck: b'D2PR' + open, then (places, page, pages) and per place (what, quality, chosen, length) + label;
        what is 0 empty, 1 next page, 2 page back, 3 item, 4 object, 5 person or monster."""
        r = self.ring
        if r is None: return self.send_raw(b'D2PR\0', DECK)
        out = bytearray(b'D2PR\1') + bytes((r.places(), r.page, r.pages()))
        for place in range(r.places()):
            i = r.at(place)
            label, what, q = b'', 0, 0
            if i == r.NEXT: what = 1
            elif i == r.BACK: what = 2
            elif i >= 0 and self.ring_npc:
                line = self.ring_targets[i]
                what = 4 if line < 0 else 5
                label = ('Abbrechen' if line < 0 else 'Wiederbeleben' if self.ring_lines[0][line] == NPC_RESURRECT else self.ring_lines[1][line]).encode()[:60]
            elif i >= 0:
                t = self.ring_targets[i]
                if t['t'] == UNIT_ITEM: what, q, label = 3, t['q'], ITEM_LABELS[t['kind']] if t['kind'] < len(ITEM_LABELS) else ITEM_LABELS[0]
                elif t['t'] == UNIT_OBJECT: what, label = 4, OBJECT_LABELS[t['kind']] if t['kind'] < len(OBJECT_LABELS) else OBJECT_LABELS[0]
                else: what, label = 5, t.get('name') or 'Person'
                label = label.encode()[:60]
            out += bytes((what, q, 1 if i >= 0 and i == r.selected else 0, len(label))) + label
        self.send_raw(bytes(out), DECK)

    def highlight(self):
        """updateHighlight for the ring: the mod marks the chosen target in the game, again every 300 ms while it holds."""
        i = self.ring.target() if self.ring and not self.ring_npc else -1
        want = self.ring_targets[i] if 0 <= i < len(self.ring_targets) else None
        uid, now = (want['id'] if want else NO_UNIT), self.now()
        if uid == self.lit and (want is None or now - self.lit_at < .3): return
        self.lit, self.lit_at = uid, now
        self.send(CMD_HIGHLIGHT, struct.pack('<II', want['t'] if want else 0, uid))

    def run_action(self, b, act, down):
        if not down:
            held, self.held[b] = self.held[b], None
            if held == 'skill': self.end_skill(b)
            elif held == 'attack': self.release_attack(b)
            elif held == 'names': self.set_alt(False)
            return
        self.held[b] = None
        if is_skill_key(act):
            self.held[b] = 'skill'
            self.start_skill(act - SKILL_F1, b)
        elif act == ATTACK_OR_TAKE:
            if self.attack_or_take(): self.held[b] = 'attack'; self.press_attack(b)
        elif act == NAMES_HELD:
            self.held[b] = 'names'
            self.set_alt(True)
        else: self.trigger(act)

    def set_alt(self, on):
        s = self.fresh()
        want = on and not (s and s['names_without_alt'])
        if want != self.alt: self.alt = want; self.dpy.key('Alt_L', want)

    def click(self, b, click):
        """padClick: in a talk A skips it, in an NPC menu A takes the line, a right click in a shop sells by the mod."""
        s = self.fresh()
        if click == 1 and s and s['talking']: self.press_key('Escape'); return
        if click == 1 and npc_menu_open(s): self.press_key('Return'); return
        self.held[b] = 'lmb' if click == 1 else 'rmb'
        (self.set_lmb if click == 1 else self.set_rmb)(True)

    def back(self):
        """D2PadBack: B closes the wheel, ends a talk (Esc, again until the NPC lets go), or closes the windows (Esc)."""
        s = self.fresh()
        npc = s is not None and (s['talking'] or is_open(s, UI_NPCMENU) or is_open(s, UI_NPCSHOP))
        if self.paused: return False
        if self.wheel_open: self.close_wheel(False); return True
        if self.ring: self.close_ring(); return True  # D2PadBack.RING
        # the game's own menus: B is back there too; in the main menu Esc does not quit (the mod unbinds it, unbindMainMenuEsc)
        if s is None and (self.s is None or self.now() - self.s_at > 2):
            self.press_key('Escape')
            return True
        if not npc and not panels(s): return False
        now = self.now()
        if self.end_talk or (self.esc_at >= 0 and now - self.esc_at < .35): return True  # repeatSwallowed
        self.esc_at = now
        if npc: self.end_talk = [now, now, 1, self.signature(s), True]
        self.press_key('Escape')
        if self.end_talk: self.end_talk[4] = False
        return True

    @staticmethod
    def signature(s):
        h = (1 if s['talking'] else 0) * 31 + panels(s)
        for i in s['menu']: h = h * 31 + i
        return h

    def end_talk_step(self, s, now):
        e = self.end_talk
        if not e: return
        npc = s['talking'] or is_open(s, UI_NPCMENU) or is_open(s, UI_NPCSHOP)
        if not npc or now - e[0] > 2 or e[2] >= 4: self.end_talk = None; return
        since, sig = now - e[1], self.signature(s)
        if since < .2 or (sig == e[3] and since < .35): return
        e[1], e[2], e[3] = now, e[2] + 1, sig
        self.press_key('Escape')

    # ---- fixed actions (triggerAction)
    def fixed(self, act):
        if self.paused and act != APP_MENU: return
        self.trigger(act)

    def trigger(self, act):
        s = self.fresh()
        if act in (HEAL, MANA, REJUV):
            if s is None: return
            kind = {HEAL: 0, MANA: 1, REJUV: 2}[act]
            if kind < 2 and self.drink.tap_dropped(kind, self.now()): return
            self.drink.manual(kind, self.now())
            self.send(CMD_DRINK, bytes((kind, 0)))  # POTIONS_ALL: belt and inventory
        elif act == TAKE:
            if s and s['talking']: self.press_key('Escape')
            elif npc_menu_open(s): self.press_key('Return')
            elif self.may_take():
                t = self.close_take() if s else None
                if t: self.start_pickup(t)
        elif act == PORTAL:
            if s: self.send(CMD_PORTAL, b'\0')
        elif act == MAP: self.press_key('Tab')
        elif act == INVENTORY: self.press_key('i')
        elif act == ESC_MENU: self.press_key('Escape')
        elif act == APP_MENU: self.app_menu()
        elif act == WEAPON_SWAP: self.press_key('w')
        elif act == RUN_TOGGLE: self.press_key('r')

    def app_menu(self):
        # Thor D2 opens its own app menu here; on the Thor under Tandem that is Tandem's pause (the game freezes, Tandem shows)
        try: urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8377/api/pause', data=b'{}', method='POST'), timeout=2).close()
        except OSError: pass

    def belt(self, row, merc):
        """padBelt: Thor D2's D-pad. With the Esc menu or an NPC menu up/down choose a line."""
        if self.paused: return
        s = self.fresh()
        if is_open(s, UI_ESCMENU) and row >= 2:
            k, ox, oy, gw, gh = self.mapping()
            px, py = self.dpy.pointer()
            gx, gy = (px - ox) / k, (py - oy) / k
            at = next((i for i, y in enumerate(ESC_MENU_Y) if abs(gx - ((gw - 800) / 2 + ESC_MENU_X)) <= ESC_MENU_HALF_W
                       and abs(gy - ((gh - 600) / 2 + y)) <= ESC_MENU_HALF_H), -1)
            self.esc_menu_to(ESC_RETURN if at < 0 else max(0, min(2, at + (-1 if row == 3 else 1))))
            return
        if is_open(s, UI_ESCMENU): return
        if npc_menu_open(s) and row >= 2:
            self.press_key('Down' if row == 2 else 'Up')
            return
        if not merc:
            if row >= 2:
                self.fixed(MAP if row == 3 else PORTAL)
                return
            row += 2
        shifted = self.shift
        if merc and not shifted: self.set_shift(True)
        self.press_key(str(row + 1))
        if merc and not shifted: self.set_shift(False)

    def esc_menu_to(self, entry):
        _, _, _, gw, gh = self.mapping()
        self.dpy.move(*self.to_desktop((gw - 800) / 2 + ESC_MENU_X, (gh - 600) / 2 + ESC_MENU_Y[entry]))

    def sort(self):
        s = self.fresh()
        if self.paused or not is_open(s, UI_INVENTORY): return
        self.release_current()
        self.send(CMD_SORT, bytes((0, 1)))

    def set_paused(self, on):
        if on == self.paused: return
        self.paused = on
        self.close_ring()
        self.release_current()
        self.send(CMD_PAUSE, bytes((1 if on else 0,)))

    def open_wheel(self):
        if self.paused: return
        self.wheel_open, self.wheel = True, -1
        self.deck()

    def close_wheel(self, choose):
        if not self.wheel_open: return
        entry, self.wheel_open, self.wheel = self.wheel, False, -1
        self.deck()
        if not choose or entry < 0 or self.paused: return
        if entry == WHEEL_INVENTORY: self.trigger(INVENTORY)
        elif entry == WHEEL_MAP: self.trigger(MAP)
        elif entry == WHEEL_CHARACTER: self.press_key('c')
        elif entry == WHEEL_SKILLS: self.press_key('t')
        elif entry == WHEEL_QUESTS: self.press_key('q')
        elif entry == WHEEL_MERC:
            s = self.fresh()
            self.press_key('o')
            if s and not is_open(s, UI_INVENTORY) and not is_open(s, 0x24): self.press_key('i')  # D2WorldTap.mercWithInventory
        elif entry == WHEEL_PAUSE: self.set_paused(True)
        elif entry == WHEEL_RECIPES: self.send_raw(b'D2PB', DECK)  # the deck opens its recipe book (D2RezeptOeffnen)

    # ---- the stick (padTick, padStick, padPointer)
    def sticks_active(self): return self.stick.active or math.hypot(self.rx, self.ry) > DEADZONE / 100 or (self.ring is not None and math.hypot(self.lx, self.ly) > 0)

    def axes(self, changed):
        right = math.hypot(self.rx, self.ry) > DEADZONE / 100
        if changed or right: self.tick()

    def tick(self):
        now = self.now()
        if self.ring:
            x, y = ring_point(self.lx, self.ly)
            if self.ring.move(x, y, RING_STEP):
                self.ring_deck()
                self.highlight()
            self.pad_stick(False)
        elif self.wheel_open:
            e = wheel_entry(self.rx, self.ry)
            if e < 0: e = wheel_entry(self.lx, self.ly)
            if e != self.wheel: self.wheel = e; self.deck()
            self.pad_stick(False)
        elif self.pointer_mode():
            self.pointer_at = now
            self.pad_stick(False)
            self.pad_pointer(now)
        else:
            self.pointer_tick = self.pointer_full = 0
            self.pad_stick(self.stick.active and now - self.pointer_at >= WALK_AFTER_POINTER_MS)
        if self.sticks_active() and not self.ticking:
            self.ticking = True
            def again():
                self.ticking = False
                if self.sticks_active(): self.tick()
                else: self.pad_stick(False)
            self.later(.016, again)

    def pad_pointer(self, now):
        s = self.fresh()
        if npc_menu_open(s): self.pointer_tick = 0; return
        dt = .016 if not self.pointer_tick else min(.05, now - self.pointer_tick)
        self.pointer_tick = now
        vmax = self.dpy.w * 1000 / POINTER_CROSS_MS * CURSOR_SPEED / 100
        ml, mr = math.hypot(self.lx, self.ly), math.hypot(self.rx, self.ry)
        if ml >= FULL: self.pointer_full = self.pointer_full or now
        else: self.pointer_full = 0
        vl = pointer_speed(ml, vmax, (now - self.pointer_full) * 1000 if self.pointer_full else 0, False)
        vr = pointer_speed(mr, vmax, 0, True)
        vx = (self.lx / ml * vl if ml else 0) + (self.rx / mr * vr if mr else 0)
        vy = (self.ly / ml * vl if ml else 0) + (self.ry / mr * vr if mr else 0)
        if not vx and not vy: self.rest = [0.0, 0.0]; return
        self.rest[0] += vx * dt; self.rest[1] += vy * dt
        mx, my = int(self.rest[0]), int(self.rest[1])
        self.rest[0] -= mx; self.rest[1] -= my
        if mx or my:
            px, py = self.dpy.pointer()
            self.dpy.move(px + mx, py + my)

    def pad_stick(self, active):
        st = self.stick
        if not active or self.paused:
            if self.joystick: self.joystick_released()
            return
        if not self.joystick: self.joystick, self.has_dir = True, False
        if st.has and (not self.has_dir or self.dir != (st.dx, st.dy)):
            self.dir, self.has_dir = (st.dx, st.dy), True
            self.direction_changed()

    def joystick_released(self):
        self.joystick = False
        if self.action == WALK_:
            self.stop_walk(); self.set_lmb(False); self.action = NONE_
        elif self.action == ATTACK_ and self.direct and self.attack_id < 0: self.attack_idle()
        elif self.attack_walking: self.stop_attack_walk()

    def direction_changed(self):
        if self.action in (ATTACK_, SKILL_) and self.direct:
            self.retarget(self.action == ATTACK_)
            if (self.attack_id if self.action == ATTACK_ else self.skill_id) < 0: self.attack_idle()
        if self.action == WALK_:
            if self.walk_direct: self.send_walk(PHASE_HOLD)
            else: self.dpy.move(*self.aim_point(*self.dir, .22))
        elif self.action == ATTACK_ and self.attack_id == 0:
            if self.walks_when_nobody(): self.attack_walk_from_place()
            else: self.dpy.move(*self.aim_point(*self.dir, .12))
        elif self.action == SKILL_ and self.skill_id == 0 and self.skill_owner is not None: self.dpy.move(*self.aim_point(*self.dir, .26))
        elif self.action == PICKUP_:
            away = self.pickup_dir[0] * self.dir[0] + self.pickup_dir[1] * self.dir[1] < math.cos(math.radians(50))
            if away and self.now() - self.pickup_start > .25: self.finish_pickup()
        elif self.action == NONE_: self.start_walk()

    # ---- walking
    def start_walk(self):
        if not self.joystick or not self.has_dir: return
        self.action = WALK_
        if can_walk(self.fresh()):
            self.walk_direct = True
            self.send_walk(PHASE_DOWN)
            self.keep_walking()
            return
        self.dpy.move(*self.aim_point(*self.dir, .22))
        self.set_lmb(True)

    def send_walk(self, phase):
        s = self.s
        dist = (s['gh'] if s else 600) * WALK_DISTANCE
        self.walk(phase, self.dir[0] * dist, self.dir[1] * dist)

    def keep_walking(self):
        self.walk_token = getattr(self, 'walk_token', 0) + 1
        token = self.walk_token
        def again():
            if token != self.walk_token or not self.walk_direct or (self.action != WALK_ and not self.attack_walking): return
            self.send_walk(PHASE_HOLD)
            self.later(.2, again)
        self.later(.2, again)

    def stop_walk(self):
        if not self.walk_direct: return
        self.walk_direct = False
        self.walk_token = getattr(self, 'walk_token', 0) + 1
        self.walk(PHASE_UP)

    def resume(self):
        if self.attack_walking: self.stop_attack_walk()
        self.action = NONE_
        if self.joystick: self.start_walk()

    def walks_when_nobody(self):
        s = self.fresh()
        return self.joystick and self.has_dir and can_walk(s) and can_act(s)

    def attack_idle(self):
        if not self.walks_when_nobody():
            if self.attack_walking: self.stop_attack_walk()
            if self.action == ATTACK_: self.attack_in_place()
            return
        if not self.attack_walking:
            self.attack_walking = self.walk_direct = True
            self.send_walk(PHASE_DOWN)
            self.keep_walking()
        else: self.send_walk(PHASE_HOLD)

    def attack_in_place(self):
        if self.action != ATTACK_ or self.attack_id > 0: return
        self.direct = False
        self.attack_id = 0
        self.set_shift(True)
        self.dpy.move(*self.aim_point(*self.dir, .12))
        self.later(.04, lambda: self.action == ATTACK_ and self.attack_id == 0 and self.set_lmb(True))

    def attack_walk_from_place(self):
        self.set_lmb(False); self.set_shift(False)
        self.direct, self.attack_id = True, -1
        self.keep_alive()
        self.attack_idle()

    def stop_attack_walk(self):
        self.attack_walking = False
        self.stop_walk()

    # ---- attack and skills
    def release_current(self):
        self.release_direct()
        self.attack_walking = False
        self.stop_walk()
        self.set_lmb(False); self.set_rmb(False); self.set_shift(False)
        self.action, self.skill_owner = NONE_, None
        self.attack_id = self.skill_id = 0
        self.skill_first_pending, self.skill_early, self.pickup_id = False, -1, 0
        self.on_corpses = False

    def attack_or_take(self):
        s = self.fresh()
        if s is None: return True
        if not s['town'] and not s['talking'] and not npc_menu_open(s):  # padChoiceApplies (aim assist is on)
            what, target = self.pad_choice()
            if what == 'take': self.start_pickup(target); return False
            self.a_target = target
            return True
        close = self.close_take()
        what = attack_or_take(s['talking'], npc_menu_open(s), s['town'], True, self.pick_target(s['left']) is not None,
                              self.in_reach(s['left']), close is not None)
        if what == 0: self.press_key('Escape'); return False
        if what == 1: self.press_key('Return'); return False
        if what == 3: self.start_pickup(close); return False
        return True

    def press_attack(self, b):
        self.release_current()
        self.action = ATTACK_
        s = self.fresh()
        chosen = getattr(self, 'a_target', None)
        self.a_target = None
        target = chosen if chosen and chosen.get('t') == UNIT_MONSTER else self.pick_target(s['left'] if s else -1)
        if target and can_act(s):
            self.direct, self.attack_id = True, target['id']
            self.unit(0, PHASE_DOWN, UNIT_MONSTER, target['id'])
            self.keep_alive()
            return
        if not target and self.walks_when_nobody():
            self.direct, self.attack_id = True, -1
            self.keep_alive()
            self.attack_idle()
            return
        if target:
            self.attack_id = target['id']
            self.dpy.move(*self.monster_point(target))
        else:
            self.attack_id = 0
            self.set_shift(True)
            self.dpy.move(*self.aim_point(*self.dir, .12))
        self.later(.04, lambda: self.action == ATTACK_ and self.set_lmb(True))

    def release_attack(self, b):
        if self.action == SKILL_ and self.skill_owner == b: self.end_skill(b); return
        if self.action != ATTACK_: return
        self.release_direct()
        self.set_lmb(False); self.set_shift(False)
        self.attack_id = 0
        self.resume()

    def keep_alive(self):
        self.alive_token = getattr(self, 'alive_token', 0) + 1
        token = self.alive_token
        def again():
            if token != self.alive_token or not self.direct or self.action not in (ATTACK_, SKILL_): return
            uid = self.attack_id if self.action == ATTACK_ else self.skill_id
            if uid > 0: self.unit(0 if self.action == ATTACK_ else self.skill_button(), PHASE_HOLD, UNIT_MONSTER, uid)
            self.later(.2, again)
        self.later(.2, again)

    def release_direct(self):
        if not self.direct: return
        self.direct = False
        self.alive_token = getattr(self, 'alive_token', 0) + 1
        uid = self.skill_id if self.action == SKILL_ else self.attack_id
        if uid > 0: self.unit(self.skill_button() if self.action == SKILL_ else 0, PHASE_UP, UNIT_MONSTER, uid)

    def skill_button(self): return 0 if self.skill_left else 1

    def track_direct(self, attack):
        uid = self.attack_id if attack else self.skill_id
        s = self.s
        if uid > 0 and any(m['id'] == uid for m in s['monsters']):
            self.missing = 0
            return
        self.missing = getattr(self, 'missing', 0) + 1
        if uid > 0 and self.missing < 3: return
        self.missing = 0
        nxt = self.pick_target(s['left'] if attack else self.skill_now)
        if attack: self.attack_id = nxt['id'] if nxt else -1
        else: self.skill_id = nxt['id'] if nxt else -1
        if nxt:
            if self.attack_walking: self.stop_attack_walk()
            self.unit(0 if attack else self.skill_button(), PHASE_DOWN, UNIT_MONSTER, nxt['id'])
        elif not self.attack_walking and attack: self.attack_idle()

    def retarget(self, attack):
        if not self.joystick or not self.has_dir or (not attack and self.on_corpses): return
        now = self.now()
        if now - self.retarget_at < .1: return  # D2Retarget.GAP_MS
        s = self.fresh()
        if s is None: return
        uid = self.attack_id if attack else self.skill_id
        nxt = self.pick_target(s['left'] if attack else self.skill_now)
        if not nxt or nxt['id'] == uid: return
        cur = next((m for m in s['monsters'] if m['id'] == uid), None)
        if cur:
            dx, dy = cur['x'] - s['px'], cur['y'] - s['py']
            n = math.hypot(dx, dy)
            if n <= 1 or (dx * self.dir[0] + dy * self.dir[1]) / n >= math.cos(math.radians(min(180, AIM_CONE + 10))): return
        self.retarget_at = now
        if attack: self.attack_id = nxt['id']
        else: self.skill_id = nxt['id']
        if self.attack_walking: self.stop_attack_walk()
        self.unit(0 if attack else self.skill_button(), PHASE_DOWN, UNIT_MONSTER, nxt['id'])

    def start_skill(self, index, owner):
        self.release_current()
        self.action, self.skill_owner = SKILL_, owner
        s = self.fresh()
        self.press_key(f'F{index + 1}')
        sent = self.now()
        skill = s['hotkey'][index] if s else -1
        self.skill_left = bool(s and skill >= 0 and s['hotleft'][index])
        self.skill_now = skill
        if skill in CORPSE_SKILLS and can_act(s) and s['portals'] >= 0:  # on the corpse the aim picks, again every 400 ms
            self.on_corpses = self.direct = self.skill_first_pending = True
            corpse = self.pick_corpse()
            self.skill_id, self.corpse_at, self.skill_early = (corpse['id'] if corpse else -1), self.now(), -1
            self.later(.02, lambda: self.after_key(sent, skill, lambda: self.first_cast(-1, PHASE_CLICK)))
            return
        # shortcut: Thor D2 teleports by the mod's own target (D2TeleportAim: ask, answer, press when the game shows it);
        # here teleport aims along the stick like any ground skill
        target = None if skill == TELEPORT else self.pick_target(skill)
        self.skill_id = target['id'] if target else 0
        self.missing = 0
        if target and can_act(s):
            self.direct, self.skill_first_pending, self.skill_early = True, True, -1
            uid = target['id']
            self.later(.02, lambda: self.after_key(sent, skill, lambda: self.first_cast(uid)))
            return
        if self.skill_left and not target: self.set_shift(True)
        if target: self.dpy.move(*self.monster_point(target))
        else: self.dpy.move(*self.aim_point(*self.dir, .26))
        def down():
            if self.action == SKILL_ and self.skill_owner == owner: (self.set_lmb if self.skill_left else self.set_rmb)(True)
        self.later(.03, down)

    def after_key(self, sent, skill, cast):
        """D2KeyWait: the first cast once the game shows the skill (80 ms at least, 300 ms at most)."""
        if self.action != SKILL_ or not self.skill_first_pending: return
        now, st = self.now(), self.fresh()
        current = st and (st['left'] if self.skill_left else st['right'])
        if now - sent < .3 and not (current == skill and now - sent >= .08):
            self.later(.02, lambda: self.after_key(sent, skill, cast))
            return
        cast()

    def first_cast(self, fallback, phase=PHASE_DOWN):
        self.skill_first_pending = False
        button = self.skill_button()
        early, self.skill_early = self.skill_early, -1
        if early > 0:
            self.unit(button, PHASE_CLICK, UNIT_MONSTER, early)
            self.resume()
            return
        if self.action != SKILL_ or not self.direct: return
        uid = self.skill_id if self.skill_id > 0 else fallback
        if uid <= 0: return
        if phase == PHASE_CLICK: self.corpse_at = self.now()
        self.unit(button, phase, UNIT_MONSTER, uid)
        if phase == PHASE_DOWN: self.keep_alive()

    def track_corpse(self, s):
        if not any(c['id'] == self.skill_id for c in s['corpses']):
            corpse = self.pick_corpse()
            self.skill_id = corpse['id'] if corpse else -1
        now = self.now()
        if self.skill_id > 0 and now - self.corpse_at > .4:
            self.corpse_at = now
            self.unit(self.skill_button(), PHASE_CLICK, UNIT_MONSTER, self.skill_id)

    def pick_corpse(self):
        """pickCorpse: the nearest corpse in the ranged reach, with the stick the best in its cone."""
        s = self.fresh()
        if s is None or s['town']: return None
        reach, cone = s['gh'] * AIM_RANGE / 100, math.cos(math.radians(AIM_CONE))
        best, best_score = None, float('inf')
        for c in s['corpses']:
            dx, dy = c['x'] - s['px'], c['y'] - s['py']
            dist = iso(dx, dy)
            if dist > reach: continue
            score = dist
            if self.joystick and self.has_dir and dist > 1:
                cos = (dx * self.dir[0] + dy * self.dir[1]) / math.hypot(dx, dy)
                if cos < cone: continue
                score = dist * (1.5 - cos)
            if score < best_score: best, best_score = c, score
        return best

    def end_skill(self, owner):
        if self.action != SKILL_ or self.skill_owner != owner: return
        if self.skill_first_pending and self.direct:  # let go before the first cast: one click on the target
            self.direct = False
            self.alive_token = getattr(self, 'alive_token', 0) + 1
            if self.skill_id > 0:
                self.skill_early, self.skill_owner = self.skill_id, None
                return
            self.skill_first_pending = False
        self.release_direct()
        self.skill_owner, self.skill_id = None, 0
        (self.set_lmb if self.skill_left else self.set_rmb)(False)
        self.set_rmb(False)
        if self.skill_left: self.set_shift(False)
        self.resume()

    # ---- taking (startPickup with the mod's take or unit click)
    def start_pickup(self, thing):
        self.release_current()
        self.action, self.pickup_id, self.pickup_dir, self.pickup_start = PICKUP_, thing['id'], self.dir, self.now()
        self.pickup_token += 1
        token = self.pickup_token
        self.later(8 if thing.get('kind') == 6 and thing['t'] == UNIT_OBJECT else 2.5,
                   lambda: self.action == PICKUP_ and self.pickup_token == token and self.finish_pickup())
        if can_act(self.fresh()):
            def take():
                if self.take_possible: self.send(CMD_TAKE, struct.pack('<BBBBI', thing['t'], 0, 0, 0, thing['id']))
                else: self.unit(0, PHASE_CLICK, thing['t'], thing['id'])
            self.later(.04, take)
            return
        self.dpy.move(*self.to_desktop(thing['x'], thing['y'] - (14 if thing['t'] == UNIT_MONSTER else 0)))
        self.later(.08, lambda: self.set_lmb(True))
        self.later(.13, lambda: self.set_lmb(False))

    def finish_pickup(self):
        if self.action != PICKUP_: return
        self.pickup_id = 0
        self.set_lmb(False)
        self.resume()

    def release_all(self):
        self.close_ring()
        for b in range(COUNT):
            if self.down[b]: self.press(b, False)
        self.lx = self.ly = self.rx = self.ry = 0
        if self.stick.active: self.stick.__init__(); self.tick()


# skills.txt's range column of 1.13d (Patch_D2.mpq): "h2h" skills use the melee reach of the aim assist, "both" ones
# (Attack, Left Hand Swing) when the weapon strikes (D2AimReach.melee)
H2H = {1, 10, 13, 14, 18, 19, 24, 29, 30, 34, 73, 96, 97, 106, 111, 116, 126, 131, 133, 139, 142, 144, 147, 150, 152, 232, 233,
       238, 239, 242, 248, 254, 255, 259, 260, 265, 269, 270, 274, 280, 326, 344, 347}
BOTH = {0, 5}


def attack_kind(d):
    """The mod's attack kind from packet 6 (D2Points.parseAttack): 0 strikes, 1 shoots, -1 unknown."""
    if len(d) < 10 or d[:4] != b'D2AM' or d[5] != 6: return None
    at = 10 + d[9] * 6 + 1 + 16 + 2
    if len(d) <= at: return -1
    at += 1 + d[at] + 16
    if len(d) <= at or d[at] < 98 or len(d) < at + 1 + d[at]: return -1
    return d[at + 98] if d[at + 98] in (0, 1) else -1


# ---- evdev input --------------------------------------------------------------------------------------------------------
PAD_NAMES = ('Microsoft X-Box 360 pad', 'Tandem Testpad')


def find_pads():
    try: blocks = open('/proc/bus/input/devices').read().split('\n\n')
    except OSError: return []
    found = []
    for block in blocks:
        name, node = re.search(r'Name="([^"]*)"', block), re.search(r'Handlers=.*?(event\d+)', block)
        if name and node and name[1] in PAD_NAMES: found.append(node[1])
    return found


def absmax(fd, code):
    try: return struct.unpack('6i', fcntl.ioctl(fd, 0x80184540 + code, bytes(24)))[2] or 1  # EVIOCGABS(code): maximum
    except OSError: return 32767 if code in (0, 1, 3, 4) else 255


class Input:
    """D2GamepadInput: buttons, triggers as buttons (30 %/50 %), the D-pad hat as buttons, both sticks."""
    def __init__(self, pad): self.pad, self.fds, self.nodes, self.scanned, self.max = pad, {}, {}, 0, {}

    def scan(self):
        now = time.monotonic()
        if now - self.scanned < 2: return
        self.scanned = now
        for node in find_pads():
            if node in self.nodes: continue
            try: fd = os.open('/dev/input/' + node, os.O_RDONLY | os.O_NONBLOCK)
            except OSError: continue
            self.nodes[node], self.fds[fd] = fd, node
            self.max[fd] = {c: absmax(fd, c) for c in (0, 1, 2, 3, 4, 5)}

    def read(self, fd):
        size = struct.calcsize('llHHi')
        try: data = os.read(fd, size * 64)
        except BlockingIOError: return
        except OSError:
            os.close(fd); self.nodes.pop(self.fds.pop(fd), None); self.pad.release_all(); return
        p, changed = self.pad, False
        for at in range(0, len(data) - size + 1, size):
            _, _, kind, code, value = struct.unpack_from('llHHi', data, at)
            if kind == 1 and code in EVDEV and value in (0, 1): p.press(EVDEV[code], value == 1)
            elif kind == 3:
                if code in (2, 5):
                    i, b = (0, LT) if code == 2 else (1, RT)
                    v = value / self.max[fd][code]
                    if trigger_down(p.down[b], v) != p.down[b]: p.press(b, not p.down[b])
                elif code in (16, 17):
                    lo, hi = (DPAD_LEFT, DPAD_RIGHT) if code == 16 else (DPAD_UP, DPAD_DOWN)
                    if (value < 0) != p.down[lo]: p.press(lo, value < 0)
                    if (value > 0) != p.down[hi]: p.press(hi, value > 0)
                elif code in (0, 1, 3, 4):
                    v = max(-1.0, min(1.0, value / self.max[fd][code]))
                    if code == 0: p.lx = v
                    elif code == 1: p.ly = v
                    elif code == 3: p.rx = v
                    else: p.ry = v
                    changed = True
        if changed: p.axes(p.stick.update(p.lx, p.ly))


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', int(os.environ.get('D2MOD_APP_PORT', MOD_IN))))
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    def send(data, port=MOD_CMD):
        try: out.sendto(data, ('127.0.0.1', port))
        except OSError: pass
    display = None
    while display is None:  # the game's X display comes up with the game
        try: display = Display()
        except OSError: time.sleep(1)
    pad = Pad(out, display, send)
    inp = Input(pad)
    while True:
        inp.scan()
        pad.run_due()
        wait = pad.next_due()
        wait = 1.0 if wait is None else max(0.0, min(1.0, wait))
        for fd in select.select([sock] + list(inp.fds), [], [], wait)[0]:
            if fd is sock:
                try: data = sock.recv(65535)
                except OSError: continue
                send(data, DECK)
                pad.packet(data)
            else: inp.read(fd)


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        st = Stick()
        assert st.update(.1, 0) is False and not st.active and st.update(.9, 0) and st.has and (st.dx, st.dy) == (1, 0)
        assert st.update(.9, .05) is False and st.update(0, .9) and abs(st.dy - 1) < 1e-9 and st.update(0, 0) and not st.active
        assert wheel_entry(0, -1) == 0 and wheel_entry(1, 0) == 2 and wheel_entry(0, 1) == 4 and wheel_entry(-1, 0) == 6 and wheel_entry(.1, .1) == -1
        assert default_action(A, False) == ATTACK_OR_TAKE and default_action(A, True) == SKILL_F1 + 6 and default_action(R3, True) == SKILL_F1 + 3
        assert default_action(LT, True) == REJUV and default_action(RT, True) == NAMES_HELD and default_action(VIEW, False) == INVENTORY
        assert attack_or_take(False, False, True, True, False, False, True) == 3 and attack_or_take(False, False, False, True, False, False, True) == 3
        assert attack_or_take(False, False, False, True, True, False, True) == 2 and attack_or_take(True, False, False, True, True, True, True) == 0
        m = lambda k, d, special=False: (k, {'id': k}, d, 0, d, True, special, False, False)
        assert choose([m(1, 100), m(2, 50)], [], False, 1, 0, .5, 120, 400, 300, -1) == ('attack', {'id': 2})
        assert choose([m(1, 100), m(2, 95)], [], False, 1, 0, .5, 120, 400, 300, 1) == ('attack', {'id': 1})  # keeps the previous within 15 %
        t = (9, {'id': 9}, 30, 0, 30, False, False, False, False)
        assert choose([m(1, 200)], [t], False, 1, 0, .5, 120, 400, 300, -1) == ('take', {'id': 9})
        assert choose([m(1, 200)], [], True, -1, 0, .57, 120, 400, 300, -1) == ('attack', None)  # nothing in the cone
        assert pointer_speed(.1, 1000, 0, False) == 0 and abs(pointer_speed(1, 1000, 0, False) - 1000) < 1e-6
        assert abs(pointer_speed(1, 1000, 1000, False) - 1500) < 1e-6 and abs(pointer_speed(1, 1000, 0, True) - 250) < 1e-6
        dr = AutoDrink()
        h = {'life': 30, 'maxLife': 100, 'mana': 50, 'maxMana': 50, 'healW': False, 'manaW': False, 'cb': [2, 1], 'ci': [0, 0],
             'rejuvBelt': False, 'lastDrink': 0, 'tiers': False, 'lb': [0, 0], 'li': [0, 0], 'tw': [0, 0], 'rejuvInv': -1}
        assert dr.decide(h, 10.0) == {'life': (0, False, False, False)} and dr.decide(h, 10.5) == {} and dr.tap_dropped(0, 10.6)
        h.update(life=10, rejuvBelt=True)
        assert dr.decide(h, 12.0)['life'][0] == 2  # under 20 %: rejuvenation
        cmdw = cmd(CMD_WALK, struct.pack('<BBhh', PHASE_DOWN, 0, -162, 0))
        assert cmdw == b'D2AC\x01\x04\x00\x00\x00\x00^\xff\x00\x00'
        hot = struct.pack('<BHH', 4, 0, 126) + struct.pack('<HB', 0xFFFF, 0) * 16
        st = b'D2AM\2\2\0\0' + struct.pack('<HHhhIIHBBhhBBBIBB', 960, 540, 0, 0, 0, 0, 2, 0, 47, 480, 254, 100, 100, 0, 0, 0, 0) + bytes(16) + bytes(4)
        for dmg in (b'\0', b'\1\3\1'):  # durability warnings: none, one
            got = parse_state(st + hot + dmg + struct.pack('<HHHHBB', 59, 59, 12, 12, 0, 2) + bytes(2))
            assert (got['life'], got['maxMana'], got['portals'], got['corpses'], got['menu']) == (59, 12, 2, [], []), got
        got = parse_state(st + hot + b'\0' + struct.pack('<HHHHBB', 59, 59, 12, 12, 0, 2) + b'\0\1' + struct.pack('<HB', 0x0D44, 7) + b'Handeln')
        assert (got['menu'], got['menu_text']) == ([0x0D44], ['Handeln'])
        r = RingChoice(3)
        assert r.move(0, -1, .1) == 1 and r.target() == 0 and r.move(.87, .5, .1) == 1 and r.target() == 1 and r.move(0, 0, .1) == 1 and r.target() == -1
        r = RingChoice(10)
        assert r.pages() == 2 and r.move(1, 0, .1) == 2 and r.page == 1 and r.at(0) == 6 and r.at(1) == 7 and r.at(3) == 8 and r.at(4) == 9 and r.at(5) == -1
        assert hold_opens_ring(TAKE, False, False, False, False) and not hold_opens_ring(TAKE, False, False, True, False)
        assert hold_opens_ring(ATTACK_OR_TAKE, True, True, False, False) and not hold_opens_ring(ATTACK_OR_TAKE, False, True, False, False)
        print('pad.py: ok')
        sys.exit(0)
    main()
