#!/usr/bin/env python3
"""Controller layout under Tandem, the same everywhere: TABLE for the settings page, check() and apply() for the emulators.

Under Tandem InputPlumber presents the Thor as "Microsoft X-Box 360 pad" (evdev 304 bottom, 305 right, 307/308 the other two,
310/311 L1/R1, 314 Select, 315 Start, 317/318 L3/R3). The Thor is printed Nintendo style (A right, B bottom, X top, Y left),
so every system gets its buttons by position: Nintendo A right and B bottom, Sony cross bottom and circle right.
python3 controls.py --check | --apply | --measure   (standard library only)"""
import os, re, shutil, sys
from pathlib import Path

# The Thor's map in InputPlumber (capability map ayn_type2, used by devices/50-ayn_thor.yaml) turns the kernel's NORTH
# (top) into West and WEST (left) into North on purpose, and the Xbox 360 target sends West as BTN_WEST (308), North as
# BTN_NORTH (307) (InputPlumber src/input/event/evdev.rs): the printed X on top arrives as 308, the printed Y on the left as
# 307 – like a real Xbox 360 pad, whose left X is 307. `--measure` checks it by hand.
BOTTOM, RIGHT, TOP, LEFT = 304, 305, 308, 307
IDX = {304: 0, 305: 1, 307: 2, 308: 3}  # SDL joystick index of the face codes (RetroArch udev, melonDS, Azahar, Eden)
SDL = {304: 'A', 305: 'B', 307: 'X', 308: 'Y'}  # SDL controller name (DuckStation, ARMSX2, Dolphin)
PPSSPP = {304: 189, 305: 190, 307: 191, 308: 188}  # PPSSPP's own numbers for the same four buttons
# SDL's GUID of the pad: bus 3, CRC16 of its name, vendor 045e, product 028e, version 1 (Steam's own virtual pad has another one)
GUID = '030081b85e0400008e02000001000000'


def q(v): return f'"{v}"'


def retroarch():  # udev driver: raw button numbers; its stock autoconfig for this pad is turned off, it knows only Xbox labels
    k = {'input_autodetect_enable': q('false'), 'input_enable_hotkey_btn': q(6), 'input_exit_emulator_btn': q(7),
         'input_save_state_btn': q(5), 'input_load_state_btn': q(4), 'input_menu_toggle_btn': q(IDX[TOP]),
         'input_menu_toggle_gamepad_combo': q(2)}  # 2 = L3+R3
    for n, v in {'b': IDX[BOTTOM], 'a': IDX[RIGHT], 'x': IDX[TOP], 'y': IDX[LEFT], 'l': 4, 'r': 5, 'select': 6, 'start': 7, 'l3': 9, 'r3': 10}.items():
        k[f'input_player1_{n}_btn'] = q(v)
    for n in ('up', 'down', 'left', 'right'): k[f'input_player1_{n}_btn'] = q('h0' + n)
    for n, v in {'l2': '+2', 'r2': '+5', 'l_x_plus': '+0', 'l_x_minus': '-0', 'l_y_plus': '+1', 'l_y_minus': '-1',
                 'r_x_plus': '+3', 'r_x_minus': '-3', 'r_y_plus': '+4', 'r_y_minus': '-4'}.items():
        k[f'input_player1_{n}_axis'] = q(v)
    return {None: k}


def sdl_pad(prefix='SDL-0/'):  # DuckStation and ARMSX2 (PCSX2) bind the same way
    s = lambda n: prefix + n
    pad = {'Up': s('DPadUp'), 'Right': s('DPadRight'), 'Down': s('DPadDown'), 'Left': s('DPadLeft'),
           'Cross': s(SDL[BOTTOM]), 'Circle': s(SDL[RIGHT]), 'Triangle': s(SDL[TOP]), 'Square': s(SDL[LEFT]),
           'Select': s('Back'), 'Start': s('Start'), 'L1': s('LeftShoulder'), 'R1': s('RightShoulder'),
           'L2': s('+LeftTrigger'), 'R2': s('+RightTrigger'), 'L3': s('LeftStick'), 'R3': s('RightStick'),
           'LUp': s('-LeftY'), 'LDown': s('+LeftY'), 'LLeft': s('-LeftX'), 'LRight': s('+LeftX'),
           'RUp': s('-RightY'), 'RDown': s('+RightY'), 'RLeft': s('-RightX'), 'RRight': s('+RightX')}
    chord = lambda a, b: f'{s(a)} & {s(b)}'
    return pad, chord


def duckstation():
    pad, chord = sdl_pad()
    return {'Main': {'ConfirmPowerOff': 'false'}, 'Pad1': pad,
            'Hotkeys': {'PowerOff': chord('Back', 'Start'), 'SaveGameState1': chord('Back', 'RightShoulder'),
                        'LoadGameState1': chord('Back', 'LeftShoulder'), 'OpenPauseMenu': chord('LeftStick', 'RightStick')}}


def armsx2():
    pad, chord = sdl_pad()
    return {'Pad1': {'Type': 'DualShock2', **pad},
            'Hotkeys': {'ShutdownVM': chord('Back', 'Start'), 'SaveStateToSlot1': chord('Back', 'RightShoulder'),
                        'LoadStateFromSlot1': chord('Back', 'LeftShoulder'), 'OpenPauseMenu': chord('LeftStick', 'RightStick')}}


def dolphin_pad():  # GameCube: A right, B bottom, X top, Y left, Z on R1, triggers analog
    b = lambda code: f'`Button {SDL[code]}`'
    return {'GCPad1': {'Device': 'SDL/0/Xbox 360 Controller', 'Buttons/A': b(RIGHT), 'Buttons/B': b(BOTTOM), 'Buttons/X': b(TOP),
                       'Buttons/Y': b(LEFT), 'Buttons/Z': '`Shoulder R`', 'Buttons/Start': '`Start`',
                       'Main Stick/Up': '`Left Y+`', 'Main Stick/Down': '`Left Y-`', 'Main Stick/Left': '`Left X-`', 'Main Stick/Right': '`Left X+`',
                       'C-Stick/Up': '`Right Y+`', 'C-Stick/Down': '`Right Y-`', 'C-Stick/Left': '`Right X-`', 'C-Stick/Right': '`Right X+`',
                       'Triggers/L': '`Trigger L`', 'Triggers/R': '`Trigger R`', 'Triggers/L-Analog': '`Trigger L`', 'Triggers/R-Analog': '`Trigger R`',
                       'D-Pad/Up': '`Pad N`', 'D-Pad/Down': '`Pad S`', 'D-Pad/Left': '`Pad W`', 'D-Pad/Right': '`Pad E`'}}


def dolphin_keys():
    return {'Hotkeys': {'Device': 'SDL/0/Xbox 360 Controller', 'General/Stop': '`Back` & `Start`',
                        'Save State/Save State Slot 1': '`Back` & `Shoulder R`', 'Load State/Load State Slot 1': '`Back` & `Shoulder L`'}}


def ppsspp():  # the keyboard part of each line stays as PPSSPP wrote it
    return {'ControlMapping': {'Cross': f'1-54,10-{PPSSPP[BOTTOM]}', 'Circle': f'1-52,10-{PPSSPP[RIGHT]}',
                               'Triangle': f'1-47,10-{PPSSPP[TOP]}', 'Square': f'1-29,10-{PPSSPP[LEFT]}',
                               'Exit App': '10-196:10-197', 'Save State': '10-196:10-195', 'Load State': '10-196:10-194'}}


def melonds():
    return {'Instance0.Joystick': {'B': IDX[BOTTOM], 'A': IDX[RIGHT], 'X': IDX[TOP], 'Y': IDX[LEFT]}}


def azahar():  # Qt ini: every key also gets "<key>\default=false"; the 3DS buttons sit like the Thor's print
    def btn(n, name): return q(f'api:controller,button:{n},engine:sdl,guid:{GUID},maptype:guid+port,name:{name},port:0')
    def trig(n, name): return q(f'api:controller,axis:{n},direction:+,engine:sdl,guid:{GUID},maptype:guid+port,name:{name},port:0,threshold:0.500000')
    def stick(x, nx, ny): return q(f'api:controller,axis_x:{x},axis_y:{x + 1},deadzone:0.050000,engine:sdl,guid:{GUID},maptype:guid+port,name_x:{nx} X,name_y:{ny} Y,port:0')
    face = {304: 'A / ✖', 305: 'B / ●', 307: 'X / ■', 308: 'Y / ▲'}
    keys = {'button_a': btn(IDX[RIGHT], face[RIGHT]), 'button_b': btn(IDX[BOTTOM], face[BOTTOM]), 'button_x': btn(IDX[TOP], face[TOP]),
            'button_y': btn(IDX[LEFT], face[LEFT]), 'button_select': btn(4, 'Back/Select'), 'button_start': btn(6, 'Start'),
            'button_home': btn(5, 'Guide/Home'), 'button_l': btn(9, 'LB'), 'button_r': btn(10, 'RB'),
            'button_up': btn(11, 'D-Pad Up'), 'button_down': btn(12, 'D-Pad Down'), 'button_left': btn(13, 'D-Pad Left'),
            'button_right': btn(14, 'D-Pad Right'), 'button_zl': trig(4, 'Left Trigger'), 'button_zr': trig(5, 'Right Trigger'),
            'circle_pad': stick(0, 'Left Stick', 'Left Stick'),
            'c_stick': stick(2, 'Right Stick', 'Right Stick')}
    out = {}
    for k, v in keys.items(): out[f'profiles\\1\\{k}'], out[f'profiles\\1\\{k}\\default'] = v, 'false'
    return {'Controls': out}


def eden():  # Switch: A right, B bottom, X top, Y left; "Exit Eden" on Minus+Plus (Select+Start) instead of Home+Minus, Home is Tandem's
    def btn(n): return q(f'button:{n},engine:sdl,guid:{GUID},port:0')
    def hat(d): return q(f'direction:{d},engine:sdl,guid:{GUID},hat:0,port:0')
    def trig(n): return q(f'axis:{n},engine:sdl,guid:{GUID},invert:+,port:0,threshold:0.500000')
    def stick(x): return q(f'axis_x:{x},axis_y:{x + 1},deadzone:0.150000,engine:sdl,guid:{GUID},invert_x:+,invert_y:-,offset_x:0.000000,offset_y:0.000000,port:0,range:1.000000')
    keys = {'button_a': btn(IDX[RIGHT]), 'button_b': btn(IDX[BOTTOM]), 'button_x': btn(IDX[TOP]), 'button_y': btn(IDX[LEFT]),
            'button_lstick': btn(9), 'button_rstick': btn(10), 'button_l': btn(4), 'button_r': btn(5), 'button_zl': trig(2), 'button_zr': trig(5),
            'button_plus': btn(7), 'button_minus': btn(6), 'button_dleft': hat('left'), 'button_dup': hat('up'),
            'button_dright': hat('right'), 'button_ddown': hat('down'), 'lstick': stick(0), 'rstick': stick(3)}
    out = {}
    for k, v in keys.items(): out[f'player_0_{k}'], out[f'player_0_{k}\\default'] = v, 'false'
    exit_key = 'Shortcuts\\Main%20Window\\Exit%20Eden\\Controller_KeySeq'
    return {'Controls': out, 'UI': {exit_key: 'Minus+Plus', exit_key + '\\default': 'false'}}


# emulator, file below HOME, separator, sections
SPECS = [
    ('RetroArch', '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg', ' = ', retroarch),
    ('DuckStation', '.local/share/duckstation/settings.ini', ' = ', duckstation),
    ('ARMSX2', '.config/ARMSX2/inis/PCSX2.ini', ' = ', armsx2),
    ('Dolphin', '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GCPadNew.ini', ' = ', dolphin_pad),
    ('Dolphin', '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/Hotkeys.ini', ' = ', dolphin_keys),
    ('PPSSPP', '.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/controls.ini', ' = ', ppsspp),
    ('melonDS', '.config/melonDS/melonDS.toml', ' = ', melonds),
    ('Azahar', '.config/azahar-emu/qt-config.ini', '=', azahar),
    ('Eden', '.config/eden/qt-config.ini', '=', eden),
]


def _home(): return Path(os.environ.get('HOME') or '~').expanduser()


def _read(path): return path.read_bytes().decode('utf-8', 'surrogateescape') if path.is_file() else ''


def _span(lines, section):
    """(first, end) line numbers of a section's body; the whole file for section None; None if there is no such section."""
    if section is None: return 0, len(lines)
    head = re.compile(r'^﻿?\[' + re.escape(section) + r'\]\s*$')
    s = next((i for i, l in enumerate(lines) if head.match(l)), None)
    if s is None: return None
    return s + 1, next((i for i in range(s + 1, len(lines)) if lines[i].startswith('[')), len(lines))


def _find(lines, span, key):
    pat = re.compile(r'^(' + re.escape(key) + r'\s*=\s*)(.*?)\s*$')
    for i in range(*span):
        m = pat.match(lines[i])
        if m: return i, m
    return None


def _get(text, section, key):
    lines = text.split('\n')
    span = _span(lines, section)
    hit = span and _find(lines, span, key)
    return hit[1].group(2) if hit else None


def _set(text, section, key, value, sep):
    lines = text.split('\n')
    span = _span(lines, section)
    if span is None:
        return (text.rstrip('\n') + '\n\n' if text.strip() else '') + f'[{section}]\n{key}{sep}{value}\n'
    hit = _find(lines, span, key)
    if hit: lines[hit[0]] = hit[1].group(1) + str(value)
    else:
        at = max([i for i in range(*span) if lines[i].strip()] or [span[0] - 1]) + 1
        lines.insert(at, f'{key}{sep}{value}')
    return '\n'.join(lines)


def _files():
    for emu, rel, sep, sections in SPECS:
        path = _home() / rel
        if path.parent.is_dir(): yield emu, rel, path, sep, sections()  # a missing folder = not installed


def check():
    """Deviations from the layout as [{'emu', 'file', 'key', 'ist', 'soll'}]; reads only."""
    out = []
    for emu, rel, path, sep, sections in _files():
        text = _read(path)
        for section, keys in sections.items():
            for key, want in keys.items():
                cur = _get(text, section, key)
                if cur != str(want): out.append({'emu': emu, 'file': rel, 'key': f'[{section}] {key}' if section else key, 'ist': cur, 'soll': str(want)})
    return out


def apply():
    """Writes the wanted values (only these keys; a copy *.bak-tandem of each file first); returns the names of the emulators changed."""
    changed = []
    for emu, rel, path, sep, sections in _files():
        old = _read(path)
        text = old
        for section, keys in sections.items():
            for key, want in keys.items():
                if _get(text, section, key) != str(want): text = _set(text, section, key, want, sep)
        if text == old: continue
        if path.is_file() and not path.with_name(path.name + '.bak-tandem').exists(): shutil.copy2(path, path.with_name(path.name + '.bak-tandem'))
        path.write_bytes(text.encode('utf-8', 'surrogateescape'))
        if emu not in changed: changed.append(emu)
    return changed


def _row(group, what, pad, where): return {'group': group, 'what': what, 'pad': pad, 'where': where}


TABLE = [
    _row('Tandem', 'Bestätigen', 'A', 'in Tandem'), _row('Tandem', 'Zurück', 'B', 'in Tandem'),
    _row('Tandem', 'Beenden', 'X', 'in Tandem'), _row('Tandem', 'Favorit', 'Y', 'in Tandem'),
    _row('Tandem', 'Spiele suchen', 'Select', 'in Tandem'),
    _row('Tandem', 'Reiter wechseln', 'L1 / R1', 'in Tandem'),
    _row('Tandem', 'Tandem zeigen oder Spiel pausieren', 'Home-Taste', 'überall'),
    _row('Tandem', 'Schnellmenü öffnen', 'Thor-Taste', 'überall'),
    _row('Tandem', 'Standby / Aufwecken', 'Ein-Taste (kurz)', 'überall'),
    _row('Tandem', 'Ein-/Aus-Menü', 'Ein-Taste (halten)', 'überall'),
    _row('In jedem Spiel', 'Tasten nach Position: A rechts, B unten, X oben, Y links', 'A / B / X / Y', 'Nintendo-Systeme, Switch, 3DS, DS'),
    _row('In jedem Spiel', 'Kreuz unten, Kreis rechts, Dreieck oben, Viereck links', 'B / A / X / Y', 'PlayStation, PS2, PSP'),
    _row('In jedem Spiel', 'Wie ein Xbox-Controller: „A“ unten, „B“ rechts', 'B / A (gedruckt)', 'Steam-Spiele und Ports'),
    _row('Hotkeys', 'Spiel beenden', 'Select + Start', 'RetroArch, DuckStation, PS2, Dolphin, PPSSPP, Switch'),
    _row('Hotkeys', 'Schnellspeichern', 'Select + R1', 'RetroArch, DuckStation, PS2, Dolphin, PPSSPP'),
    _row('Hotkeys', 'Schnellladen', 'Select + L1', 'RetroArch, DuckStation, PS2, Dolphin, PPSSPP'),
    _row('Hotkeys', 'Menü des Emulators', 'L3 + R3', 'RetroArch, DuckStation, PS2'),
    _row('Besonderheiten', 'Menü zusätzlich', 'Select + X', 'RetroArch'),
    _row('Besonderheiten', 'Switch: nur Beenden, der Emulator hat keine Schnellstände', 'Select + Start', 'Eden'),
    _row('Besonderheiten', 'Keine Hotkeys auf dem Controller möglich, nur die Tasten', '–', 'Azahar (3DS), melonDS (DS)'),
    _row('Besonderheiten', 'Wii-Spiele: Zeiger und Nunchuk noch nicht auf dem Controller', '–', 'Dolphin (Wii)'),
    _row('Besonderheiten', 'Belegung nur im Emulator selbst einstellbar', '–', 'Flycast (Dreamcast), Cemu (Wii U)'),
    _row('Besonderheiten', 'Spielt wie Xbox: A springen, B ducken, X nachladen, Y benutzen, L1/R1 Waffe wechseln', 'B / A / X / Y', 'Half-Life'),
    _row('Besonderheiten', 'Linker Stick Zeiger, A/B Maustasten, Start Menü oder Enter, Beenden über Home', 'Sticks, A / B', 'Age of Kings, Red Alert 2, C&C, Heroes III, KKnD 2'),
    _row('Besonderheiten', 'Eigene Belegung (nur lesen): linker Stick läuft, A Angriff, B nehmen, X/Y Fertigkeiten, Start Spielmenü', 'A / B / X / Y', 'Diablo II'),
]


def measure():
    """Asks for the four face buttons one by one and says which evdev code each one sends (run on the Thor with no game running)."""
    import select, struct, time
    dev = re.search(r'Name="Microsoft X-Box 360 pad"\n(?:.*\n)*?H: Handlers=.*?(event\d+)', Path('/proc/bus/input/devices').read_text())
    if not dev: sys.exit('Kein „Microsoft X-Box 360 pad“ gefunden (läuft Tandem?).')
    fd, size, seen = os.open('/dev/input/' + dev.group(1), os.O_RDONLY | os.O_NONBLOCK), struct.calcsize('llHHi'), {}
    for name in ('A (rechts)', 'B (unten)', 'X (oben)', 'Y (links)'):
        print(f'Drücke gedrucktes {name} ...', flush=True)
        end, code = time.time() + 30, None
        while code is None and time.time() < end:
            if select.select([fd], [], [], 1)[0]:
                for i in range(0, len(data := os.read(fd, size * 16)) - size + 1, size):
                    _, _, t, c, v = struct.unpack_from('llHHi', data, i)
                    if t == 1 and v == 1 and code is None: code = c
        seen[name] = code
    print(seen, '\nPasst zu controls.py:' , seen == {'A (rechts)': RIGHT, 'B (unten)': BOTTOM, 'X (oben)': TOP, 'Y (links)': LEFT})


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg == '--check':
        for d in check(): print(f"{d['emu']}: {d['file']}: {d['key']}: ist {d['ist']!r}, soll {d['soll']!r}")
    elif arg == '--apply': print('angepasst:', ', '.join(apply()) or 'nichts')
    elif arg == '--measure': measure()
    else: sys.exit(__doc__)
