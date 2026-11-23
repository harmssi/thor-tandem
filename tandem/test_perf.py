"""Unit tests for thor_perf.py (Snapdragon 8 Gen 2 / Adreno 740 performance engine)."""
from pathlib import Path
import thor_perf


def _mk_fake_hw(tmp_path: Path):
    cpu = tmp_path / 'cpufreq'
    for pol, hi in (('policy0', 2016000), ('policy3', 2803200), ('policy7', 2956800)):
        d = cpu / pol
        d.mkdir(parents=True)
        (d / 'scaling_available_governors').write_text('conservative ondemand performance schedutil\n')
        (d / 'scaling_governor').write_text('conservative\n')
        (d / 'cpuinfo_min_freq').write_text('307200\n')
        (d / 'cpuinfo_max_freq').write_text(f'{hi}\n')
        (d / 'scaling_max_freq').write_text('1555200\n')
        (d / 'scaling_cur_freq').write_text('1555200\n')
    gpu = tmp_path / 'gpu'
    gpu.mkdir(parents=True)
    (gpu / 'available_governors').write_text('userspace performance simple_ondemand\n')
    (gpu / 'governor').write_text('simple_ondemand\n')
    (gpu / 'min_freq').write_text('220000000\n')
    (gpu / 'max_freq').write_text('680000000\n')
    (gpu / 'cur_freq').write_text('220000000\n')
    batt = tmp_path / 'battery'
    batt.mkdir(parents=True)
    (batt / 'charge_control_end_threshold').write_text('100\n')
    (batt / 'charge_control_start_threshold').write_text('0\n')
    return cpu, gpu, batt


def test_balanced_upgrades_conservative_to_schedutil(tmp_path):
    cpu, gpu, _ = _mk_fake_hw(tmp_path)
    res = thor_perf.apply_profile('Balanced', cpu_base=cpu, gpu_base=gpu)
    assert res['ok'] and res['cpu_clusters'] == 3 and res['gpu_tuned']
    assert (cpu / 'policy7/scaling_governor').read_text().strip() == 'schedutil'
    assert int((cpu / 'policy7/scaling_max_freq').read_text()) == 2592000
    assert int((gpu / 'min_freq').read_text()) == 295000000


def test_turbo_locks_performance_and_680mhz_gpu(tmp_path):
    cpu, gpu, _ = _mk_fake_hw(tmp_path)
    res = thor_perf.apply_profile('Turbo', cpu_base=cpu, gpu_base=gpu)
    assert res['ok']
    assert (cpu / 'policy7/scaling_governor').read_text().strip() == 'performance'
    assert int((cpu / 'policy7/scaling_max_freq').read_text()) == 2956800
    assert (gpu / 'governor').read_text().strip() == 'performance'
    assert int((gpu / 'min_freq').read_text()) == 680000000


def test_gpu_clock_lock_and_auto(tmp_path):
    _, gpu, _ = _mk_fake_hw(tmp_path)
    assert thor_perf.set_gpu_clock(550, gpu_base=gpu)['ok']
    assert int((gpu / 'min_freq').read_text()) == 550000000
    assert thor_perf.set_gpu_clock(0, gpu_base=gpu)['ok']
    assert (gpu / 'governor').read_text().strip() == 'simple_ondemand'
    assert 'error' in thor_perf.set_gpu_clock(999, gpu_base=gpu)


def test_charge_limit_bypass(tmp_path):
    _, _, batt = _mk_fake_hw(tmp_path)
    assert thor_perf.set_charge_limit(80, batt_base=batt)['ok']
    assert int((batt / 'charge_control_end_threshold').read_text()) == 80
    assert int((batt / 'charge_control_start_threshold').read_text()) == 75
    assert 'error' in thor_perf.set_charge_limit(50, batt_base=batt)


def test_game_env_booster_flags():
    env = thor_perf.game_env({'FOO': '1'}, {'tu_deck_emu': True, 'fex_fast': True}, 'steam')
    assert env['FOO'] == '1'
    assert env['MESA_SHADER_CACHE_MAX_SIZE'] == '8G'
    assert env['DXVK_GPLASYNCCACHE'] == '1'
    assert env['PROTON_USE_NTSYNC'] == '1'
    assert env['FEX_TSOENABLED'] == '1'
    assert env['FEX_MULTIBLOCK'] == '1'
    assert 'deck_emu' in env['TU_DEBUG']


def test_telemetry_reads_all_clusters(tmp_path):
    cpu, gpu, batt = _mk_fake_hw(tmp_path)
    t = thor_perf.telemetry(cpu_base=cpu, gpu_base=gpu, batt_base=batt)
    assert t['cpu_gov'] == 'conservative'
    assert t['cpu_mhz']['prime'] == 1555
    assert t['gpu_mhz'] == 220
    assert t['charge_limit'] == 100
