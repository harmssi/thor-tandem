"""Self-check for controls.py: python3 test_controls.py (standard library only)."""
import atexit, os, shutil, tempfile, unittest
from pathlib import Path

HOME = Path(tempfile.mkdtemp(prefix='controls-test-'))
atexit.register(shutil.rmtree, HOME, True)
os.environ['HOME'] = str(HOME)
import controls  # noqa: E402  (after HOME is redirected)

FILES = {
    '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg': 'video_driver = "vulkan"\ninput_menu_toggle_btn = "3"\ninput_player1_a_btn = "nul"\naudio_volume = "0.0"\n',
    '.local/share/duckstation/settings.ini': '[Main]\nSetupWizardIncomplete = false\n\n[GPU]\nRenderer = Vulkan\n',
    '.config/ARMSX2/inis/PCSX2.ini': '﻿[UI]\nConfirmShutdown = false\n',
    '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GCPadNew.ini': '[GCPad1]\nDevice = XInput2/0/Virtual core pointer\nButtons/A = `X`\n[GCPad2]\nDevice = x\n',
    '.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/controls.ini': '﻿[ControlMapping]\nCross = 1-54,10-189\nStart = 1-62,10-197\n',
    '.config/melonDS/melonDS.toml': '[Instance0.Joystick]\nB = 0\nX = 3\nUp = 257\n\n[Mic]\nInputType = 1\n',
    '.config/azahar-emu/qt-config.ini': '[Controls]\nprofile=0\nprofiles\\1\\button_a="old"\nprofiles\\1\\button_a\\default=false\n\n[Core]\nuse_cpu_jit=true\n',
    '.config/eden/qt-config.ini': '[Controls]\nplayer_0_button_a\\default=false\nplayer_0_button_a="engine:keyboard,code:67,toggle:0"\n[UI]\nShortcuts\\Main%20Window\\Exit%20Eden\\Controller_KeySeq=Home+Minus\n',
}


class Controls(unittest.TestCase):
    def test_not_installed_is_skipped(self):
        os.environ['HOME'] = tempfile.mkdtemp(dir=HOME)
        try: self.assertEqual((controls.apply(), controls.check()), ([], []))
        finally: os.environ['HOME'] = str(HOME)

    def test_apply_is_idempotent(self):
        for rel, text in FILES.items():
            path = HOME / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
        (HOME / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg.bak-tandem').write_text('mine')
        self.assertTrue(controls.check())
        names = controls.apply()
        self.assertEqual(sorted(names), ['ARMSX2', 'Azahar', 'Dolphin', 'DuckStation', 'Eden', 'PPSSPP', 'RetroArch', 'melonDS'])
        self.assertEqual(controls.check(), [])
        snapshot = {rel: (HOME / rel).read_bytes() for rel in FILES}
        self.assertEqual(controls.apply(), [])
        self.assertEqual(snapshot, {rel: (HOME / rel).read_bytes() for rel in FILES})
        # other keys stay, existing backups are not overwritten, new ones are made
        ra = (HOME / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg').read_text()
        self.assertIn('video_driver = "vulkan"', ra)
        self.assertIn('audio_volume = "0.0"', ra)
        self.assertIn('input_menu_toggle_btn = "3"', ra)  # Select + the top button (X)
        self.assertEqual((HOME / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg.bak-tandem').read_text(), 'mine')
        toml = (HOME / '.config/melonDS/melonDS.toml').read_text()
        self.assertIn('Up = 257', toml)
        self.assertIn('[Mic]\nInputType = 1', toml)
        self.assertTrue((HOME / '.config/melonDS/melonDS.toml.bak-tandem').is_file())
        self.assertEqual((HOME / '.config/melonDS/melonDS.toml.bak-tandem').read_text(), FILES['.config/melonDS/melonDS.toml'])
        self.assertTrue((HOME / '.config/ARMSX2/inis/PCSX2.ini').read_text().startswith('﻿[UI]'))
        self.assertIn('use_cpu_jit=true', (HOME / '.config/azahar-emu/qt-config.ini').read_text())
        self.assertTrue((HOME / '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/Hotkeys.ini').is_file())

    def test_table(self):
        self.assertTrue(all({'what', 'pad', 'where'} <= set(row) for row in controls.TABLE))

    def test_unified_styles_flycast_cemu_and_wii(self):
        sub = Path(tempfile.mkdtemp(dir=HOME))
        old_home = os.environ['HOME']
        os.environ['HOME'] = str(sub)
        try:
            for d in ('.local/share/duckstation', '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu',
                      '.var/app/org.flycast.Flycast/config/flycast', '.config/Cemu'):
                (sub / d).mkdir(parents=True, exist_ok=True)
            changed = controls.apply('thor')
            self.assertEqual(sorted(changed), ['Cemu', 'Dolphin', 'DuckStation', 'Flycast'])
            self.assertEqual(controls.check('thor'), [])
            # In unified 'thor' mode, PlayStation Cross is bound to physical Right (SDL-0/B), Circle to Bottom (SDL-0/A)
            ds = (sub / '.local/share/duckstation/settings.ini').read_text()
            self.assertIn('Cross = SDL-0/B', ds)
            self.assertIn('Circle = SDL-0/A', ds)
            # Wii Nunchuk & IR pointer configured
            wii = (sub / '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/WiimoteNew.ini').read_text()
            self.assertIn('Extension = Nunchuk', wii)
            # Switching to 'xbox' flips Cross/Circle and Cemu A/B cleanly across all emulators
            self.assertTrue(controls.check('xbox'))
            controls.apply('xbox')
            self.assertEqual(controls.check('xbox'), [])
            self.assertIn('Cross = SDL-0/A', (sub / '.local/share/duckstation/settings.ini').read_text())
            self.assertIn('AxisScale = 1.40', (sub / '.local/share/duckstation/settings.ini').read_text())
            self.assertIn('<range>1.40</range>', (sub / '.config/Cemu/controllerProfiles/controller0.xml').read_text())
            self.assertIn('GateRadius = 70.0', (sub / '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GCPadNew.ini').read_text())
        finally:
            os.environ['HOME'] = old_home

    def test_mupen64_and_retroarch_stick_full_range(self):
        sub = Path(tempfile.mkdtemp(dir=HOME))
        old_home = os.environ['HOME']
        os.environ['HOME'] = str(sub)
        try:
            (sub / '.var/app/org.libretro.RetroArch/config/retroarch/config/Mupen64Plus-Next').mkdir(parents=True, exist_ok=True)
            (sub / '.config/eden').mkdir(parents=True, exist_ok=True)
            (sub / '.config/azahar-emu').mkdir(parents=True, exist_ok=True)
            changed = controls.apply('thor')
            self.assertEqual(sorted(changed), ['Azahar', 'Eden', 'RetroArch'])
            ra = (sub / '.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg').read_text()
            self.assertIn('input_analog_sensitivity = "1.420000"', ra)
            m64 = (sub / '.var/app/org.libretro.RetroArch/config/retroarch/config/Mupen64Plus-Next/Mupen64Plus-Next.opt').read_text()
            self.assertIn('mupen64plus-astick-sensitivity = "130"', m64)
            ed = (sub / '.config/eden/qt-config.ini').read_text()
            self.assertIn('range:0.700000', ed)
            az = (sub / '.config/azahar-emu/qt-config.ini').read_text()
            self.assertIn('range:0.700000', az)
        finally:
            os.environ['HOME'] = old_home


if __name__ == '__main__':
    unittest.main()
