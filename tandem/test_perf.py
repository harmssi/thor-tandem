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


if __name__ == '__main__':
    unittest.main()
