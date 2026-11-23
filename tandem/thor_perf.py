"""Hardware performance engine for the AYN Thor (Snapdragon 8 Gen 2 / Adreno 740) under ArmadaOS.

Provides:
- 4 real hardware profiles: Eco, Balanced (upgraded from sluggish 'conservative' to 'schedutil'),
  Performance (full 2.02 / 2.80 / 2.96 GHz clocks + GPU min 401 MHz), and Turbo (all CPU clusters
  on 'performance' + Adreno 740 locked to 680 MHz).
- GPU clock lock (Auto / 401 / 550 / 680 MHz) via devfreq (root:wheel writable on ArmadaOS).
- Battery bypass / charge limit (80% / 85% / 100%) via charge_control_end_threshold.
- Per-game Vulkan / Mesa Turnip / DXVK / Proton / FEX environment booster.
- Live CPU cluster & GPU clock telemetry.
"""
from pathlib import Path

CPU_BASE = Path('/sys/devices/system/cpu/cpufreq')
GPU_BASE = Path('/sys/class/devfreq/3d00000.gpu')
BATT_BASE = Path('/sys/class/power_supply/battery')

# Snapdragon 8 Gen 2 (AYN Thor) cluster layout:
# policy0 = 3x Silver (max 2016000 kHz), policy3 = 4x Gold (max 2803200 kHz), policy7 = 1x Prime X3 (max 2956800 kHz)
POLICIES = ('policy0', 'policy3', 'policy7')

PROFILE_TUNING = {
    'Eco': {
        'armada': 'Eco',
        'cpu_gov': 'schedutil',
        'cpu_max': {'policy0': 1363200, 'policy3': 1670400, 'policy7': 1766400},
        'gpu_gov': 'simple_ondemand',
        'gpu_min': 220000000,
        'gpu_max': 475000000,
    },
    'Balanced': {
        'armada': 'Balanced',
        'cpu_gov': 'schedutil',
        'cpu_max': {'policy0': 1785600, 'policy3': 2361600, 'policy7': 2592000},
        'gpu_gov': 'simple_ondemand',
        'gpu_min': 295000000,
        'gpu_max': 680000000,
    },
    'Performance': {
        'armada': 'Performance',
        'cpu_gov': 'schedutil',
        'cpu_max': {'policy0': 2016000, 'policy3': 2803200, 'policy7': 2956800},
        'gpu_gov': 'simple_ondemand',
        'gpu_min': 401000000,
        'gpu_max': 680000000,
    },
    'Turbo': {
        'armada': 'Performance',
        'cpu_gov': 'performance',
        'cpu_max': {'policy0': 2016000, 'policy3': 2803200, 'policy7': 2956800},
        'gpu_gov': 'performance',
        'gpu_min': 680000000,
        'gpu_max': 680000000,
    },
}

GPU_CLOCKS_MHZ = (0, 401, 550, 680)
CHARGE_LIMITS = (80, 85, 100)
FAN_MODES = {'auto': ('Auto', 3, None), 'quiet': ('Leise', 1, 72), 'cool': ('Kühl', 1, 155), 'max': ('Max', 1, 235)}
HWMON_BASE = Path('/sys/class/hwmon')


def _find_pwmfan(hwmon_base=HWMON_BASE):
    try:
        for h in sorted(Path(hwmon_base).glob('hwmon*')):
            if _read(h / 'name') == 'pwmfan':
                return h
    except OSError:
        pass
    return None


def set_fan_mode(mode, hwmon_base=HWMON_BASE):
    """Set pwmfan curve: auto (hw auto), quiet (~28%), cool (~61%), max (~92%)."""
    spec = FAN_MODES.get(str(mode or '').lower())
    if not spec:
        return {'error': 'Unbekannter Lüfter-Modus.'}
    fdir = _find_pwmfan(hwmon_base)
    if not fdir:
        return {'error': 'Lüfter-Steuerung nicht verfügbar.'}
    _, en_val, pwm_val = spec
    ok = _write(fdir / 'pwm1_enable', en_val)
    if ok and pwm_val is not None:
        ok = _write(fdir / 'pwm1', pwm_val)
    if not ok:
        return {'error': 'Keine Schreibrechte für Lüfter (udev-Regel nötig).'}
    return {'ok': True, 'fan_mode': str(mode).lower()}


def _read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _write(path, value):
    try:
        Path(path).write_text(str(value))
        return True
    except OSError:
        return False


def _clamp_freq(policy_dir, target_khz):
    """Clamp target frequency to the closest available/supported max on this hardware."""
    hw_max = _read(policy_dir / 'cpuinfo_max_freq')
    hw_min = _read(policy_dir / 'cpuinfo_min_freq')
    try:
        hi = int(hw_max) if hw_max else target_khz
        lo = int(hw_min) if hw_min else 0
        return max(lo, min(hi, int(target_khz)))
    except ValueError:
        return int(target_khz)


def apply_profile(profile, cpu_base=CPU_BASE, gpu_base=GPU_BASE):
    """Apply CPU cluster governors/ceilings and Adreno 740 devfreq tuning for one profile."""
    spec = PROFILE_TUNING.get(profile)
    if not spec:
        return {'error': 'Unbekanntes Leistungsprofil.'}
    applied_cpu = 0
    for pol in POLICIES:
        pdir = Path(cpu_base) / pol
        if not pdir.is_dir():
            continue
        avail = (_read(pdir / 'scaling_available_governors') or '').split()
        gov = spec['cpu_gov']
        if avail and gov not in avail:
            gov = 'performance' if 'performance' in avail else avail[0]
        ok_g = _write(pdir / 'scaling_governor', gov)
        target = _clamp_freq(pdir, spec['cpu_max'][pol])
        ok_m = _write(pdir / 'scaling_max_freq', target)
        if ok_g or ok_m:
            applied_cpu += 1

    gpu_ok = False
    gdir = Path(gpu_base)
    if gdir.is_dir():
        g_avail = (_read(gdir / 'available_governors') or '').split()
        ggov = spec['gpu_gov']
        if g_avail and ggov not in g_avail:
            ggov = 'simple_ondemand' if 'simple_ondemand' in g_avail else g_avail[0]
        # Write max before min when raising, min before max when lowering
        _write(gdir / 'max_freq', spec['gpu_max'])
        _write(gdir / 'min_freq', spec['gpu_min'])
        _write(gdir / 'max_freq', spec['gpu_max'])
        gpu_ok = _write(gdir / 'governor', ggov)

    return {'ok': True, 'profile': profile, 'cpu_clusters': applied_cpu, 'gpu_tuned': gpu_ok}


def set_gpu_clock(mhz, gpu_base=GPU_BASE):
    """Lock Adreno 740 to a fixed MHz (401/550/680) or 0 for dynamic auto scaling."""
    mhz = int(mhz or 0)
    if mhz not in GPU_CLOCKS_MHZ:
        return {'error': 'Ungültiger GPU-Takt.'}
    gdir = Path(gpu_base)
    if not gdir.is_dir():
        return {'error': 'GPU-Steuerung nicht verfügbar.'}
    if mhz == 0:
        _write(gdir / 'min_freq', 220000000)
        _write(gdir / 'max_freq', 680000000)
        ok = _write(gdir / 'governor', 'simple_ondemand')
    else:
        hz = mhz * 1000000
        _write(gdir / 'max_freq', 680000000)
        _write(gdir / 'min_freq', hz)
        _write(gdir / 'max_freq', hz)
        ok = _write(gdir / 'governor', 'performance')
    return {'ok': ok, 'gpu_clock': mhz} if ok else {'error': 'GPU-Takt ließ sich nicht setzen.'}


def set_charge_limit(pct, batt_base=BATT_BASE):
    """Set hardware battery bypass / charge stop threshold (80, 85, or 100 = off)."""
    pct = int(pct)
    if pct not in CHARGE_LIMITS:
        return {'error': 'Ungültiges Ladelimit.'}
    bdir = Path(batt_base)
    end_f = bdir / 'charge_control_end_threshold'
    start_f = bdir / 'charge_control_start_threshold'
    if not end_f.exists():
        return {'error': 'Ladelimit wird von diesem Kernel nicht unterstützt.'}
    ok_end = _write(end_f, pct)
    if ok_end and start_f.exists():
        _write(start_f, max(50, pct - 5) if pct < 100 else 0)
    if not ok_end:
        return {'error': 'Keine Schreibrechte für Ladelimit (udev-Regel nötig).'}
    return {'ok': True, 'charge_limit': pct}


def game_env(base_env=None, opt=None, system=''):
    """Build an optimized Vulkan / Turnip / DXVK / Proton / FEX environment for a game launch."""
    env = dict(base_env or {})
    opt = opt or {}
    # Universal safe performance wins on Snapdragon 8 Gen 2 / ARM64 Linux:
    env.setdefault('MESA_SHADER_CACHE_DISABLE', 'false')
    env.setdefault('MESA_SHADER_CACHE_MAX_SIZE', '8G')
    env.setdefault('DXVK_GPLASYNCCACHE', '1')
    env.setdefault('PROTON_USE_NTSYNC', '1')
    env.setdefault('WINEFSYNC', '1')
    env.setdefault('STAGING_SHARED_MEMORY', '1')

    # FEX translation tuning (safe TSO by default; optional fast-math/multiblock per game)
    env.setdefault('FEX_TSOENABLED', '1')
    if opt.get('fex_fast'):
        env['FEX_X87REDUCEDPRECISION'] = '1'
        env['FEX_MULTIBLOCK'] = '1'

    # Optional Mesa Turnip flags (per-game toggles)
    tu_flags = [f.strip() for f in env.get('TU_DEBUG', '').split(',') if f.strip()]
    if opt.get('tu_deck_emu') and 'deck_emu' not in tu_flags:
        tu_flags.append('deck_emu')
    if opt.get('tu_sysmem') and 'sysmem' not in tu_flags:
        tu_flags.append('sysmem')
    if tu_flags:
        env['TU_DEBUG'] = ','.join(tu_flags)

    return env


def telemetry(cpu_base=CPU_BASE, gpu_base=GPU_BASE, batt_base=BATT_BASE, hwmon_base=HWMON_BASE):
    """Live CPU cluster clocks, governor, GPU frequency, fan mode and battery bypass state."""
    out = {'cpu_gov': None, 'cpu_mhz': {}, 'gpu_mhz': None, 'gpu_gov': None, 'charge_limit': None, 'fan_mode': 'auto', 'fan_pwm': None}
    for name, pol in (('silver', 'policy0'), ('gold', 'policy3'), ('prime', 'policy7')):
        pdir = Path(cpu_base) / pol
        if not pdir.is_dir():
            continue
        if out['cpu_gov'] is None:
            out['cpu_gov'] = _read(pdir / 'scaling_governor')
        cur = _read(pdir / 'scaling_cur_freq') or _read(pdir / 'scaling_max_freq')
        if cur and cur.isdigit():
            out['cpu_mhz'][name] = round(int(cur) / 1000)
    gdir = Path(gpu_base)
    if gdir.is_dir():
        out['gpu_gov'] = _read(gdir / 'governor')
        gcur = _read(gdir / 'cur_freq')
        if gcur and gcur.isdigit():
            out['gpu_mhz'] = round(int(gcur) / 1000000)
    lim = _read(Path(batt_base) / 'charge_control_end_threshold')
    if lim and lim.isdigit():
        out['charge_limit'] = int(lim)
    fdir = _find_pwmfan(hwmon_base)
    if fdir:
        en = _read(fdir / 'pwm1_enable')
        pwm = _read(fdir / 'pwm1')
        if pwm and pwm.isdigit():
            out['fan_pwm'] = int(pwm)
        if en == '1' and out['fan_pwm'] is not None:
            out['fan_mode'] = 'quiet' if out['fan_pwm'] <= 105 else ('cool' if out['fan_pwm'] <= 195 else 'max')
        else:
            out['fan_mode'] = 'auto'
    return out
