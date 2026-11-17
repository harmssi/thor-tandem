"""Self-check for controls.py: python3 test_controls.py (standard library only)."""
import os, tempfile, unittest
from pathlib import Path

HOME = Path(tempfile.mkdtemp(prefix='controls-test-'))
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


if __name__ == '__main__':
    unittest.main()
