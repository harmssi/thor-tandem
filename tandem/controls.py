#!/usr/bin/env python3
"""Unified controller layout across all platforms under Tandem:
- Default style 'thor' (by physical print on the AYN Thor):
    Right (printed A)  = Confirm / Primary action everywhere (Nintendo A, PlayStation Cross, Dreamcast A, Wii/Wii U A, Xbox A)
    Bottom (printed B) = Back / Secondary action everywhere (Nintendo B, PlayStation Circle, Dreamcast B, Wii/Wii U B, Xbox B)
    Top (printed X)    = North action (Nintendo X, PlayStation Triangle, Dreamcast Y, Wii U X)
    Left (printed Y)   = West action (Nintendo Y, PlayStation Square, Dreamcast X, Wii U Y)
- Optional style 'xbox':
    Bottom = Confirm, Right = Back, Top = North, Left = West across every emulator.
python3 controls.py --check | --apply | --measure   (standard library only)"""
import json, os, re, shutil, sys
from pathlib import Path

# The Thor's map in InputPlumber (capability map ayn_type2, used by devices/50-ayn_thor.yaml) turns the kernel's NORTH
# (top) into West and WEST (left) into North on purpose, and the Xbox 360 target sends West as BTN_WEST (308), North as
# BTN_NORTH (307): the printed X on top arrives as 308, the printed Y on the left as 307.
BOTTOM, RIGHT, TOP, LEFT = 304, 305, 308, 307
IDX = {304: 0, 305: 1, 307: 2, 308: 3}  # SDL joystick index of the face codes (RetroArch udev, melonDS, Azahar, Eden, Flycast, Cemu)
SDL = {304: 'A', 305: 'B', 307: 'X', 308: 'Y'}  # SDL controller name (DuckStation, ARMSX2, Dolphin)
PPSSPP = {304: 189, 305: 190, 307: 191, 308: 188}  # PPSSPP's own numbers for the same four buttons
GUID = '030081b85e0400008e02000001000000'


def q(v): return f'"{v}"'


def _home(): return Path(os.environ.get('HOME') or '~').expanduser()


def current_style(style=None):
    if style in ('thor', 'xbox'): return style
    cfg = Path(os.environ.get('XDG_CONFIG_HOME') or (_home() / '.config')) / 'tandem/config.json'
    try: s = json.loads(cfg.read_text()).get('controls_style')
    except (OSError, ValueError): s = None
    return s if s in ('thor', 'xbox') else 'thor'


def _faces(style=None):
    """Return (CONFIRM, CANCEL, NORTH, WEST) evdev codes for the active layout style."""
    if current_style(style) == 'xbox':
        return BOTTOM, RIGHT, TOP, LEFT
    return RIGHT, BOTTOM, TOP, LEFT


def retroarch(style=None):
    ok, back, north, west = _faces(style)
    # AYN Thor recessed Hall-effect sticks reach ~70-75% at the circular shell gate:
    # sensitivity 1.42 + 8% deadzone unlocks 100% run speed in OoT, Link's Awakening, Mario 64, etc. without drift.
    k = {'input_autodetect_enable': q('false'), 'input_enable_hotkey_btn': q(6), 'input_exit_emulator_btn': q(7),
         'input_save_state_btn': q(5), 'input_load_state_btn': q(4), 'input_menu_toggle_btn': q(IDX[TOP]),
         'input_menu_toggle_gamepad_combo': q(2), 'menu_swap_ok_cancel_buttons': q('false'),
         'savestate_thumbnail_enable': q('true'),
         'input_analog_deadzone': q('0.080000'), 'input_analog_sensitivity': q('1.420000')}
    for n, v in {'a': IDX[ok], 'b': IDX[back], 'x': IDX[north], 'y': IDX[west], 'l': 4, 'r': 5, 'select': 6, 'start': 7, 'l3': 9, 'r3': 10}.items():
        k[f'input_player1_{n}_btn'] = q(v)
    for n in ('up', 'down', 'left', 'right'): k[f'input_player1_{n}_btn'] = q('h0' + n)
    for n, v in {'l2': '+2', 'r2': '+5', 'l_x_plus': '+0', 'l_x_minus': '-0', 'l_y_plus': '+1', 'l_y_minus': '-1',
                 'r_x_plus': '+3', 'r_x_minus': '-3', 'r_y_plus': '+4', 'r_y_minus': '-4'}.items():
        k[f'input_player1_{n}_axis'] = q(v)
    return {None: k}


def mupen64_opt(_style=None):
    return {None: {'mupen64plus-astick-deadzone': q('8'), 'mupen64plus-astick-sensitivity': q('130')}}


def sdl_pad(style=None, prefix='SDL-0/'):  # Unified: PlayStation Cross = Confirm, Circle = Back, Triangle = North, Square = West
    ok, back, north, west = _faces(style)
    s = lambda n: prefix + n
    pad = {'Up': s('DPadUp'), 'Right': s('DPadRight'), 'Down': s('DPadDown'), 'Left': s('DPadLeft'),
           'Cross': s(SDL[ok]), 'Circle': s(SDL[back]), 'Triangle': s(SDL[north]), 'Square': s(SDL[west]),
           'Select': s('Back'), 'Start': s('Start'), 'L1': s('LeftShoulder'), 'R1': s('RightShoulder'),
           'L2': s('+LeftTrigger'), 'R2': s('+RightTrigger'), 'L3': s('LeftStick'), 'R3': s('RightStick'),
           'LUp': s('-LeftY'), 'LDown': s('+LeftY'), 'LLeft': s('-LeftX'), 'LRight': s('+LeftX'),
           'RUp': s('-RightY'), 'RDown': s('+RightY'), 'RLeft': s('-RightX'), 'RRight': s('+RightX'),
           'AxisScale': '1.40', 'Deadzone': '0.08'}
    chord = lambda a, b: f'{s(a)} & {s(b)}'
    return pad, chord


def duckstation(style=None):
    pad, chord = sdl_pad(style)
    return {'Main': {'ConfirmPowerOff': 'false'}, 'Pad1': pad,
            'Hotkeys': {'PowerOff': chord('Back', 'Start'), 'SaveGameState1': chord('Back', 'RightShoulder'),
                        'LoadGameState1': chord('Back', 'LeftShoulder'), 'OpenPauseMenu': chord('LeftStick', 'RightStick')}}


def armsx2(style=None):
    pad, chord = sdl_pad(style)
    return {'Pad1': {'Type': 'DualShock2', **pad},
            'Hotkeys': {'ShutdownVM': chord('Back', 'Start'), 'SaveStateToSlot1': chord('Back', 'RightShoulder'),
                        'LoadStateFromSlot1': chord('Back', 'LeftShoulder'), 'OpenPauseMenu': chord('LeftStick', 'RightStick')}}


def dolphin_pad(style=None):
    ok, back, north, west = _faces(style)
    b = lambda code: f'`Button {SDL[code]}`'
    return {'GCPad1': {'Device': 'SDL/0/Xbox 360 Controller', 'Buttons/A': b(ok), 'Buttons/B': b(back), 'Buttons/X': b(north),
                       'Buttons/Y': b(west), 'Buttons/Z': '`Shoulder R`', 'Buttons/Start': '`Start`',
                       'Main Stick/Up': '`Left Y+`', 'Main Stick/Down': '`Left Y-`', 'Main Stick/Left': '`Left X-`', 'Main Stick/Right': '`Left X+`',
                       'Main Stick/Dead Zone': '8.0', 'Main Stick/GateRadius': '70.0',
                       'C-Stick/Up': '`Right Y+`', 'C-Stick/Down': '`Right Y-`', 'C-Stick/Left': '`Right X-`', 'C-Stick/Right': '`Right X+`',
                       'C-Stick/Dead Zone': '8.0', 'C-Stick/GateRadius': '70.0',
                       'Triggers/L': '`Trigger L`', 'Triggers/R': '`Trigger R`', 'Triggers/L-Analog': '`Trigger L`', 'Triggers/R-Analog': '`Trigger R`',
                       'D-Pad/Up': '`Pad N`', 'D-Pad/Down': '`Pad S`', 'D-Pad/Left': '`Pad W`', 'D-Pad/Right': '`Pad E`'}}


def dolphin_wii(style=None):  # Wii + Nunchuk unified on the built-in controller (Left Stick = Nunchuk, Right Stick = IR pointer)
    ok, back, north, west = _faces(style)
    b = lambda code: f'`Button {SDL[code]}`'
    return {'Wiimote1': {'Device': 'SDL/0/Xbox 360 Controller', 'Source': '1', 'Extension': 'Nunchuk',
                         'Buttons/A': b(ok), 'Buttons/B': f'{b(back)} | `Trigger R`',
                         'Buttons/1': b(west), 'Buttons/2': b(north), 'Buttons/-': '`Back`', 'Buttons/+': '`Start`',
                         'D-Pad/Up': '`Pad N`', 'D-Pad/Down': '`Pad S`', 'D-Pad/Left': '`Pad W`', 'D-Pad/Right': '`Pad E`',
                         'IR/Up': '`Right Y+`', 'IR/Down': '`Right Y-`', 'IR/Left': '`Right X-`', 'IR/Right': '`Right X+`',
                         'Shake/X': '`Shoulder R`', 'Shake/Y': '`Shoulder R`', 'Shake/Z': '`Shoulder R`',
                         'Nunchuk/Buttons/C': '`Shoulder L`', 'Nunchuk/Buttons/Z': '`Trigger L`',
                         'Nunchuk/Stick/Up': '`Left Y+`', 'Nunchuk/Stick/Down': '`Left Y-`',
                         'Nunchuk/Stick/Left': '`Left X-`', 'Nunchuk/Stick/Right': '`Left X+`',
                         'Nunchuk/Stick/Dead Zone': '8.0', 'Nunchuk/Stick/GateRadius': '70.0'}}


def dolphin_keys(style=None):
    return {'Hotkeys': {'Device': 'SDL/0/Xbox 360 Controller', 'General/Stop': '`Back` & `Start`',
                        'Save State/Save State Slot 1': '`Back` & `Shoulder R`', 'Load State/Load State Slot 1': '`Back` & `Shoulder L`'}}


def ppsspp(style=None):
    ok, back, north, west = _faces(style)
    return {'ControlMapping': {'Cross': f'1-54,10-{PPSSPP[ok]}', 'Circle': f'1-52,10-{PPSSPP[back]}',
                               'Triangle': f'1-47,10-{PPSSPP[north]}', 'Square': f'1-29,10-{PPSSPP[west]}',
                               'Exit App': '10-196:10-197', 'Save State': '10-196:10-195', 'Load State': '10-196:10-194'}}


def melonds(style=None):
    ok, back, north, west = _faces(style)
    return {'Instance0.Joystick': {'A': IDX[ok], 'B': IDX[back], 'X': IDX[north], 'Y': IDX[west], 'HK_SwapScreens': 10}}


def azahar(style=None):
    ok, back, north, west = _faces(style)
    def btn(n, name): return q(f'api:controller,button:{n},engine:sdl,guid:{GUID},maptype:guid+port,name:{name},port:0')
    def trig(n, name): return q(f'api:controller,axis:{n},direction:+,engine:sdl,guid:{GUID},maptype:guid+port,name:{name},port:0,threshold:0.500000')
    def stick(x, nx, ny): return q(f'api:controller,axis_x:{x},axis_y:{x + 1},deadzone:0.080000,engine:sdl,guid:{GUID},maptype:guid+port,name_x:{nx} X,name_y:{ny} Y,port:0,range:0.700000')
    face = {304: 'A / ✖', 305: 'B / ●', 307: 'X / ■', 308: 'Y / ▲'}
    keys = {'button_a': btn(IDX[ok], face[ok]), 'button_b': btn(IDX[back], face[back]),
            'button_x': btn(IDX[north], face[north]), 'button_y': btn(IDX[west], face[west]),
            'button_select': btn(4, 'Back/Select'), 'button_start': btn(6, 'Start'),
            'button_home': btn(5, 'Guide/Home'), 'button_l': btn(9, 'LB'), 'button_r': btn(10, 'RB'),
            'button_up': btn(11, 'D-Pad Up'), 'button_down': btn(12, 'D-Pad Down'),
            'button_left': btn(13, 'D-Pad Left'), 'button_right': btn(14, 'D-Pad Right'),
            'button_zl': trig(4, 'Left Trigger'), 'button_zr': trig(5, 'Right Trigger'),
            'circle_pad': stick(0, 'Left Stick', 'Left Stick'), 'c_stick': stick(2, 'Right Stick', 'Right Stick')}
    out = {}
    for k, v in keys.items(): out[f'profiles\\1\\{k}'], out[f'profiles\\1\\{k}\\default'] = v, 'false'
    return {'Controls': out}


def eden(style=None):
    ok, back, north, west = _faces(style)
    def btn(n): return q(f'button:{n},engine:sdl,guid:{GUID},port:0')
    def hat(d): return q(f'direction:{d},engine:sdl,guid:{GUID},hat:0,port:0')
    def trig(n): return q(f'axis:{n},engine:sdl,guid:{GUID},invert:+,port:0,threshold:0.500000')
    def stick(x): return q(f'axis_x:{x},axis_y:{x + 1},deadzone:0.090000,engine:sdl,guid:{GUID},invert_x:+,invert_y:-,offset_x:0.000000,offset_y:0.000000,port:0,range:0.700000')
    keys = {'button_a': btn(IDX[ok]), 'button_b': btn(IDX[back]), 'button_x': btn(IDX[north]), 'button_y': btn(IDX[west]),
            'button_lstick': btn(9), 'button_rstick': btn(10), 'button_l': btn(4), 'button_r': btn(5),
            'button_zl': trig(2), 'button_zr': trig(5), 'button_plus': btn(7), 'button_minus': btn(6),
            'button_dleft': hat('left'), 'button_dup': hat('up'), 'button_dright': hat('right'), 'button_ddown': hat('down'),
            'lstick': stick(0), 'rstick': stick(3)}
    out = {}
    for k, v in keys.items(): out[f'player_0_{k}'], out[f'player_0_{k}\\default'] = v, 'false'
    exit_key = 'Shortcuts\\Main%20Window\\Exit%20Eden\\Controller_KeySeq'
    return {'Controls': out, 'UI': {exit_key: 'Minus+Plus', exit_key + '\\default': 'false'}}


def flycast(style=None):  # Dreamcast / Naomi / Atomiswave: A = Confirm, B = Cancel, Y = Top, X = Left
    ok, back, north, west = _faces(style)
    return {'emulator': {'mapping_name': 'Xbox 360 Controller', 'version': '3'},
            'digital': {'bind0': f'{IDX[ok]}:btn_a',
                        'bind1': f'{IDX[back]}:btn_b', 'bind2': f'{IDX[west]}:btn_x', 'bind3': f'{IDX[north]}:btn_y',
                        'bind4': '4:btn_trigger_left', 'bind5': '5:btn_trigger_right',
                        'bind6': '6:btn_menu', 'bind7': '7:btn_start',
                        'bind8': '256:btn_dpad1_up', 'bind9': '257:btn_dpad1_down',
                        'bind10': '258:btn_dpad1_left', 'bind11': '259:btn_dpad1_right'},
            'analog': {'bind0': '0-:axis_left', 'bind1': '0+:axis_right', 'bind2': '1-:axis_up', 'bind3': '1+:axis_down',
                       'bind4': '2+:axis_trigger_left', 'bind5': '5+:axis_trigger_right',
                       'bind6': '3-:axis2_left', 'bind7': '3+:axis2_right', 'bind8': '4-:axis2_up', 'bind9': '4+:axis2_down'}}


def _cemu_xml(style=None):
    ok, back, north, west = _faces(style)
    # SDL GameController button IDs in Cemu: 0=A(South), 1=B(East), 2=X(West), 3=Y(North), 4=Back, 6=Start, 7=LS, 8=RS, 9=LB, 10=RB, 11..14=DPad
    c_sdl = {BOTTOM: 0, RIGHT: 1, LEFT: 2, TOP: 3}
    mappings = [
        (1, c_sdl[ok]),     # Wii U A (Confirm)
        (2, c_sdl[back]),   # Wii U B (Cancel)
        (3, c_sdl[north]),  # Wii U X (Top)
        (4, c_sdl[west]),   # Wii U Y (Left)
        (5, 9), (6, 10),    # L, R
        (7, 42), (8, 43),   # ZL, ZR (axes +trigger)
        (9, 6), (10, 4),    # Plus (Start), Minus (Back)
        (11, 11), (12, 12), (13, 13), (14, 14),  # Up, Down, Left, Right
        (15, 7), (16, 8),   # Stick clicks
        (17, 39), (18, 45), (19, 44), (20, 38),  # Left stick U/D/L/R
        (21, 41), (22, 47), (23, 46), (24, 40),  # Right stick U/D/L/R
    ]
    entries = '\n            '.join(f'<entry>\n                <mapping>{m}</mapping>\n                <button>{b}</button>\n            </entry>' for m, b in mappings)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<emulated_controller>
    <type>Wii U GamePad</type>
    <controller>
        <api>SDLController</api>
        <uuid>0_{GUID}</uuid>
        <display_name>Xbox 360 Controller</display_name>
        <axis>
            <deadzone>0.09</deadzone>
            <range>1.40</range>
        </axis>
        <rotation>
            <deadzone>0.09</deadzone>
            <range>1.40</range>
        </rotation>
        <trigger>
            <deadzone>0.12</deadzone>
            <range>1</range>
        </trigger>
        <mappings>
            {entries}
        </mappings>
    </controller>
</emulated_controller>
'''


# emulator, file below HOME, check_dir below HOME, separator, sections
SPECS = [
    ('RetroArch', '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg', '.var/app/org.libretro.RetroArch/config/retroarch', ' = ', retroarch),
    ('RetroArch', '.var/app/org.libretro.RetroArch/config/retroarch/config/Mupen64Plus-Next/Mupen64Plus-Next.opt', '.var/app/org.libretro.RetroArch/config/retroarch/config/Mupen64Plus-Next', ' = ', mupen64_opt),
    ('DuckStation', '.local/share/duckstation/settings.ini', '.local/share/duckstation', ' = ', duckstation),
    ('ARMSX2', '.config/ARMSX2/inis/PCSX2.ini', '.config/ARMSX2/inis', ' = ', armsx2),
    ('Dolphin', '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GCPadNew.ini', '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu', ' = ', dolphin_pad),
    ('Dolphin', '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/WiimoteNew.ini', '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu', ' = ', dolphin_wii),
    ('Dolphin', '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/Hotkeys.ini', '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu', ' = ', dolphin_keys),
    ('PPSSPP', '.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/controls.ini', '.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM', ' = ', ppsspp),
    ('melonDS', '.config/melonDS/melonDS.toml', '.config/melonDS', ' = ', melonds),
    ('Azahar', '.config/azahar-emu/qt-config.ini', '.config/azahar-emu', '=', azahar),
    ('Eden', '.config/eden/qt-config.ini', '.config/eden', '=', eden),
    ('Flycast', '.var/app/org.flycast.Flycast/config/flycast/mappings/SDL_Xbox 360 Controller.cfg', '.var/app/org.flycast.Flycast/config/flycast', ' = ', flycast),
]


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


def _files(style=None):
    st = current_style(style)
    h = _home()
    for emu, rel, chk, sep, sections in SPECS:
        if (h / chk).is_dir():
            yield emu, rel, h / rel, sep, sections(st)


def check(style=None):
    """Deviations from the unified layout as [{'emu', 'file', 'key', 'ist', 'soll'}]; reads only."""
    st = current_style(style)
    out = []
    for emu, rel, path, sep, sections in _files(st):
        text = _read(path)
        for section, keys in sections.items():
            for key, want in keys.items():
                cur = _get(text, section, key)
                if cur != str(want): out.append({'emu': emu, 'file': rel, 'key': f'[{section}] {key}' if section else key, 'ist': cur, 'soll': str(want)})
    cemu_dir = _home() / '.config/Cemu'
    if cemu_dir.is_dir():
        cpath = cemu_dir / 'controllerProfiles/controller0.xml'
        want_xml = _cemu_xml(st)
        if _read(cpath) != want_xml:
            out.append({'emu': 'Cemu', 'file': '.config/Cemu/controllerProfiles/controller0.xml', 'key': 'Wii U GamePad', 'ist': 'abweichend', 'soll': st})
    return out


def apply(style=None):
    """Writes the unified layout across all installed emulators (backing up *.bak-tandem once); returns changed emulator names."""
    st = current_style(style)
    changed = []
    for emu, rel, path, sep, sections in _files(st):
        old = _read(path)
        text = old
        for section, keys in sections.items():
            for key, want in keys.items():
                if _get(text, section, key) != str(want): text = _set(text, section, key, want, sep)
        if text == old: continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and not path.with_name(path.name + '.bak-tandem').exists():
            shutil.copy2(path, path.with_name(path.name + '.bak-tandem'))
        path.write_bytes(text.encode('utf-8', 'surrogateescape'))
        if emu not in changed: changed.append(emu)
    cemu_dir = _home() / '.config/Cemu'
    if cemu_dir.is_dir():
        cpath = cemu_dir / 'controllerProfiles/controller0.xml'
        want_xml = _cemu_xml(st)
        if _read(cpath) != want_xml:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            if cpath.is_file() and not cpath.with_name('controller0.xml.bak-tandem').exists():
                shutil.copy2(cpath, cpath.with_name('controller0.xml.bak-tandem'))
            cpath.write_text(want_xml, encoding='utf-8')
            changed.append('Cemu')
    return changed


def _row(group, what, pad, where): return {'group': group, 'what': what, 'pad': pad, 'where': where}


def table(style=None):
    xbox = current_style(style) == 'xbox'
    ok_lbl = 'B (unten · Xbox-A)' if xbox else 'A (rechts)'
    back_lbl = 'A (rechts · Xbox-B)' if xbox else 'B (unten)'
    uni_desc = ('Hauptaktion / Bestätigen liegt immer unten, Zurück immer rechts'
                if xbox else 'Hauptaktion / Bestätigen liegt immer rechts (A), Zurück immer unten (B)')
    ps_desc = ('PlayStation Kreuz = Unten, Kreis = Rechts, Dreieck = Oben, Viereck = Links'
               if xbox else 'PlayStation Kreuz = A (rechts), Kreis = B (unten), Dreieck = X (oben), Viereck = Y (links)')
    return [
        _row('Tandem', 'Bestätigen', 'A (rechts)', 'in Tandem'),
        _row('Tandem', 'Zurück', 'B (unten)', 'in Tandem'),
        _row('Tandem', 'Optionen / Spiel-Menü', 'Start', 'in Tandem'),
        _row('Tandem', 'Favorit', 'Y (links)', 'in Tandem'),
        _row('Tandem', 'Spiele suchen', 'Select', 'in Tandem'),
        _row('Tandem', 'Reiter wechseln', 'L1 / R1', 'in Tandem'),
        _row('Tandem', 'Tandem zeigen oder Spiel pausieren', 'Home-Taste', 'überall'),
        _row('Tandem', 'Schnellmenü & FPS-Overlay öffnen', 'Thor-Taste', 'überall'),
        _row('Tandem', 'Standby / Aufwecken', 'Ein-Taste (kurz)', 'überall'),
        _row('Tandem', 'Ein-/Aus-Menü', 'Ein-Taste (halten)', 'überall'),
        _row('Einheitlich in allen Systemen', f'Bestätigen: {ok_lbl} · Zurück: {back_lbl}', 'A / B / X / Y', 'in allen Emulatoren'),
        _row('Einheitlich in allen Systemen', uni_desc, 'A / B / X / Y', 'Nintendo, PlayStation, PSP, Dreamcast, Wii, Wii U, Switch, 3DS, DS'),
        _row('Einheitlich in allen Systemen', ps_desc, 'A / B / X / Y', 'DuckStation (PS1), ARMSX2 (PS2), PPSSPP (PSP)'),
        _row('Einheitlich in allen Systemen', 'Wii Nunchuk auf linkem Stick, Zeiger auf rechtem Stick, Z/B auf L2/R2', 'Sticks, L2/R2', 'Dolphin (Wii)'),
        _row('Hotkeys', 'Spiel beenden', 'Select + Start', 'RetroArch, DuckStation, PS2, Dolphin, PPSSPP, Switch'),
        _row('Hotkeys', 'Schnellspeichern', 'Select + R1', 'RetroArch, DuckStation, PS2, Dolphin, PPSSPP'),
        _row('Hotkeys', 'Schnellladen', 'Select + L1', 'RetroArch, DuckStation, PS2, Dolphin, PPSSPP'),
        _row('Hotkeys', 'Menü des Emulators', 'L3 + R3', 'RetroArch, DuckStation, PS2'),
        _row('Hotkeys', 'Bildschirme tauschen (DS / 3DS)', 'R3', 'melonDS, Azahar'),
    ]


TABLE = table('thor')


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
    print(seen, '\nPasst zu controls.py:', seen == {'A (rechts)': RIGHT, 'B (unten)': BOTTOM, 'X (oben)': TOP, 'Y (links)': LEFT})


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg == '--check':
        for d in check(): print(f"{d['emu']}: {d['file']}: {d['key']}: ist {d['ist']!r}, soll {d['soll']!r}")
    elif arg == '--apply': print('angepasst:', ', '.join(apply()) or 'nichts')
    elif arg == '--measure': measure()
    else: sys.exit(__doc__)
