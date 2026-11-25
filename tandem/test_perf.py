import tempfile
import unittest
from pathlib import Path

import thor_perf


class PerfEngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cpu = self.root / 'cpu'
        self.gpu = self.root / 'gpu'
        self.ufs = self.root / 'ufs'
        self.batt = self.root / 'batt'
        self.hwmon = self.root / 'hwmon'
        for pol, hi in (('policy0', 2016000), ('policy3', 2803200), ('policy7', 2956800)):
            d = self.cpu / pol
            d.mkdir(parents=True)
            (d / 'scaling_available_governors').write_text('conservative schedutil performance\n')
            (d / 'scaling_governor').write_text('conservative\n')
            (d / 'cpuinfo_min_freq').write_text('307200\n')
            (d / 'cpuinfo_max_freq').write_text(f'{hi}\n')
            (d / 'scaling_max_freq').write_text('2054400\n')
            (d / 'scaling_cur_freq').write_text('1500000\n')
        self.gpu.mkdir(parents=True)
        (self.gpu / 'available_governors').write_text('simple_ondemand performance\n')
        (self.gpu / 'governor').write_text('simple_ondemand\n')
        (self.gpu / 'min_freq').write_text('220000000\n')
        (self.gpu / 'max_freq').write_text('680000000\n')
        (self.gpu / 'cur_freq').write_text('295000000\n')
        self.ufs.mkdir(parents=True)
        (self.ufs / 'governor').write_text('simple_ondemand\n')
        (self.ufs / 'cur_freq').write_text('300000000\n')
        self.batt.mkdir(parents=True)
        (self.batt / 'charge_control_end_threshold').write_text('100\n')
        (self.batt / 'charge_control_start_threshold').write_text('0\n')
        f = self.hwmon / 'hwmon0'
        f.mkdir(parents=True)
        (f / 'name').write_text('pwmfan\n')
        (f / 'pwm1_enable').write_text('3\n')
        (f / 'pwm1').write_text('60\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_balanced_uses_schedutil_and_ufs(self):
        res = thor_perf.apply_profile('Balanced', cpu_base=self.cpu, gpu_base=self.gpu, ufs_base=self.ufs)
        self.assertTrue(res['ok'])
        self.assertEqual((self.cpu / 'policy7/scaling_governor').read_text(), 'schedutil')
        self.assertEqual((self.ufs / 'governor').read_text(), 'simple_ondemand')

    def test_turbo_locks_max_cpu_gpu_and_ufs(self):
        res = thor_perf.apply_profile('Turbo', cpu_base=self.cpu, gpu_base=self.gpu, ufs_base=self.ufs)
        self.assertTrue(res['ok'])
        self.assertEqual((self.cpu / 'policy7/scaling_governor').read_text(), 'performance')
        self.assertEqual((self.cpu / 'policy7/scaling_max_freq').read_text(), '2956800')
        self.assertEqual((self.gpu / 'governor').read_text(), 'performance')
        self.assertEqual((self.gpu / 'min_freq').read_text(), '680000000')
        self.assertEqual((self.ufs / 'governor').read_text(), 'performance')

    def test_gpu_clock_lock_and_auto(self):
        self.assertTrue(thor_perf.set_gpu_clock(550, gpu_base=self.gpu)['ok'])
        self.assertEqual((self.gpu / 'min_freq').read_text(), '550000000')
        self.assertEqual((self.gpu / 'governor').read_text(), 'performance')
        self.assertTrue(thor_perf.set_gpu_clock(0, gpu_base=self.gpu)['ok'])
        self.assertEqual((self.gpu / 'governor').read_text(), 'simple_ondemand')

    def test_charge_limit_and_fan(self):
        self.assertTrue(thor_perf.set_charge_limit(80, batt_base=self.batt)['ok'])
        self.assertEqual((self.batt / 'charge_control_end_threshold').read_text(), '80')
        self.assertEqual((self.batt / 'charge_control_start_threshold').read_text(), '75')
        self.assertTrue(thor_perf.set_fan_mode('cool', hwmon_base=self.hwmon)['ok'])
        self.assertEqual((self.hwmon / 'hwmon0/pwm1').read_text(), '155')

    def test_hyperdrive_game_env_defaults_to_fast_fex_and_superres(self):
        env = thor_perf.game_env({}, {'res': 720, 'tu_deck_emu': True}, 'steam')
        self.assertEqual(env['MESA_SHADER_CACHE_MAX_SIZE'], '8G')
        self.assertEqual(env['FEX_TSOENABLED'], '0')
        self.assertEqual(env['FEX_MULTIBLOCK'], '1')
        self.assertEqual(env['FEX_X87REDUCEDPRECISION'], '1')
        self.assertEqual(env['STEAM_COMPAT_FEX_CONFIG'], 'Multiblock:1,TSOEnabled:0')
        self.assertEqual(env['WINE_FULLSCREEN_FSR'], '1')
        self.assertEqual(env['WINE_FULLSCREEN_FSR_CUSTOM_MODE'], '1280x720')
        self.assertEqual(env['GAMESCOPE_WSI_MIN_IMAGE_COUNT'], '2')
        self.assertIn('deck_emu', env['TU_DEBUG'])

    def test_strict_tso_override(self):
        env = thor_perf.game_env({}, {'fex_tso': True}, 'steam')
        self.assertEqual(env['FEX_TSOENABLED'], '1')
        self.assertEqual(env['STEAM_COMPAT_FEX_CONFIG'], 'Multiblock:1,TSOEnabled:1')

    def test_telemetry_reads_ram_ufs_and_scx(self):
        scx = self.root / 'scx_ops'
        scx.write_text('lavd_1.0\n')
        mem = self.root / 'meminfo'
        mem.write_text('MemTotal:       12058624 kB\nMemAvailable:    8703180 kB\n')
        t = thor_perf.telemetry(cpu_base=self.cpu, gpu_base=self.gpu, batt_base=self.batt,
                                hwmon_base=self.hwmon, ufs_base=self.ufs, scx_ops=scx, meminfo=mem)
        self.assertEqual(t['scheduler'], 'lavd')
        self.assertEqual(t['ufs_mhz'], 300)
        self.assertEqual(t['ram_free_gib'], 8.3)
        self.assertEqual(t['ram_total_gib'], 11.5)

    def test_smart_presets_and_banananative_ram_boost(self):
        opt = thor_perf.smart_game_opt({'appid': '377160', 's': 'steam'}, {})
        self.assertEqual(opt['res'], 720)
        self.assertEqual(opt['scale'], 'sgsr')
        # User override always wins
        opt2 = thor_perf.smart_game_opt({'appid': '377160', 's': 'steam'}, {'res': 0})
        self.assertEqual(opt2['res'], 0)
        # BananaNative defaults on startup to 720p + SGSR + Turbo + FrameGen, and blocks white-screen flags & double LSFG
        bn_opt = thor_perf.smart_game_opt({'t': 'Ocarina of Time', 's': 'steam', 'direct': True}, {}, engine_label='BananaNative')
        self.assertEqual((bn_opt['res'], bn_opt['scale'], bn_opt['profile'], bn_opt['framegen']), (720, 'sgsr', 'Turbo', True))
        # 12 GB Thor: PeanutsNative disables fileback; Switch-2 BananaNative (6.2 GB heap) keeps fileback headroom until 16 GB Thor Max
        mem12 = self.root / 'meminfo12'
        mem12.write_text('MemTotal:       12058624 kB\nMemAvailable:    8500000 kB\n')
        env_p = thor_perf.game_env({}, {}, 'switch', engine_label='PeanutsNative', meminfo=mem12)
        self.assertEqual(env_p['DM_MEM_FILEBACK'], '0')
        self.assertEqual(env_p['DISABLE_LSFGVK'], '1')
        env_b12 = thor_perf.game_env({}, bn_opt, 'steam', engine_label='BananaNative', meminfo=mem12)
        self.assertNotIn('DM_MEM_FILEBACK', env_b12)
        self.assertEqual(env_b12['DISABLE_LSFGVK'], '1')
        self.assertEqual(env_b12['NX_FRAMEGEN'], '1')
        self.assertEqual(env_b12['DM_OPMODE'], 'handheld')
        self.assertEqual(env_b12['DM_GRAPHICS_SCALE'], '2')
        self.assertEqual(env_b12['DM_VK_MESH'], '0')
        self.assertEqual(env_b12['DM_VK_DIRECT_GMEM'], '0')
        self.assertEqual(env_b12['DM_VK_CS_ASYNC'], '1')
        self.assertEqual(env_b12['DM_VK_CS_WAIT_MS'], '12')
        self.assertEqual(env_b12['DM_VK_IMG_PSI'], '0')
        self.assertEqual(env_b12['DM_VK_PSO_SLOTS'], '4')
        mem16 = self.root / 'meminfo16'
        mem16.write_text('MemTotal:       16000000 kB\nMemAvailable:   12000000 kB\n')
        env_b16 = thor_perf.game_env({}, {}, 'steam', engine_label='BananaNative', meminfo=mem16)
        self.assertEqual(env_b16['DM_MEM_FILEBACK'], '0')
        self.assertEqual(env_b16['DXVK_STATE_CACHE'], '1')
        self.assertEqual(env_b16['PROTON_FORCE_LARGE_ADDRESS_AWARE'], '1')

    def test_ensure_mpv_hwdec(self):
        mhome = self.root / 'mpv-home'
        (mhome / '.var/app/io.mpv.Mpv/config/mpv').mkdir(parents=True)
        written = thor_perf.ensure_mpv_hwdec(mhome)
        self.assertEqual(len(written), 2)
        self.assertIn('hwdec=auto-safe', (mhome / '.config/mpv/mpv.conf').read_text())
        self.assertIn('hwdec=auto-safe', (mhome / '.var/app/io.mpv.Mpv/config/mpv/mpv.conf').read_text())
        # Idempotent when hwdec is already configured
        self.assertEqual(thor_perf.ensure_mpv_hwdec(mhome), [])

    def test_silent_fan_auto_eco_and_whisper_fifo(self):
        # 0 dB semi-passive fan mode sets pwm1_enable=3 and pwm1=0
        self.assertTrue(thor_perf.set_fan_mode('silent', hwmon_base=self.hwmon)['ok'])
        self.assertEqual((self.hwmon / 'hwmon0/pwm1_enable').read_text(), '3')
        self.assertEqual((self.hwmon / 'hwmon0/pwm1').read_text(), '0')
        # Auto-Eco per console class
        gba_opt = thor_perf.smart_game_opt({'s': 'gba'}, {}, auto_eco=True, on_battery=True)
        self.assertEqual((gba_opt['profile'], gba_opt['fps'], gba_opt['vsync_strict']), ('Eco', 60, True))
        ps2_opt = thor_perf.smart_game_opt({'s': 'ps2'}, {}, auto_eco=True, on_battery=False)
        self.assertEqual((ps2_opt['profile'], ps2_opt['fps']), ('Balanced', 60))
        # Whisper mode on heavy Steam game -> Balanced + 40 FPS Golden Mode + FIFO VSync + DXVK frame cap
        wh_opt = thor_perf.smart_game_opt({'appid': '377160', 's': 'steam'}, {}, auto_eco=True, whisper_mode=True, on_battery=True)
        self.assertEqual((wh_opt['profile'], wh_opt['fps'], wh_opt['res'], wh_opt['vsync_strict']), ('Balanced', 40, 720, True))
        wh_env = thor_perf.game_env({}, wh_opt, 'steam')
        self.assertEqual(wh_env['MESA_VK_WSI_PRESENT_MODE'], 'fifo')
        self.assertEqual(wh_env['DXVK_FRAME_RATE'], '40')
        self.assertEqual(wh_env['VKD3D_FRAME_RATE'], '40')
        self.assertEqual(wh_env['PROTON_DXVK_LOWLATENCY'], '0')
        self.assertEqual(wh_env['PIPEWIRE_LATENCY'], '512/48000')
        # 16 GB Thor Max disables file-backed flash thrashing & low-RAM clamp for BananaNative, while 12 GB keeps fileback safety
        mem16 = self.root / 'meminfo-16g'
        mem16.write_text('MemTotal:       15800000 kB\nMemAvailable:   11400000 kB\n')
        bn_env = thor_perf.game_env({}, {}, 'banananative', engine_label='BananaNative', meminfo=mem16)
        self.assertEqual(bn_env['DM_MEM_FILEBACK'], '0')
        self.assertEqual(bn_env['DM_VK_LOW_RAM'], '0')
        self.assertEqual(bn_env['DM_VK_MESH'], '0')
        # WirePlumber 3s audio codec suspend drop-in
        ahome = self.root / 'audio-home'
        wp_conf = thor_perf.ensure_audio_powersave(ahome)
        self.assertTrue(wp_conf.endswith('52-tandem-power-save.conf'))
        self.assertIn('session.suspend-timeout-seconds = 3', Path(wp_conf).read_text())


if __name__ == '__main__':
    unittest.main()
