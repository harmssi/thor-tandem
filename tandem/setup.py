#!/usr/bin/env python3
"""Toravo Tandem – Einrichtungsassistent für ArmadaOS (AYN Thor und andere Dual-Screen-Geräte).

Auf dem Gerät ausführen (Desktop-Modus › Konsole oder per SSH):   python3 setup.py
Ohne Rückfragen mit den Vorgaben:                                  python3 setup.py --ja

Jeder Schritt lässt sich überspringen und der Assistent kann beliebig oft laufen: Vorhandenes bleibt, wie es ist.
"""
import os, re, shutil, subprocess, sys, urllib.request
from pathlib import Path

HOME, HERE = Path.home(), Path(__file__).resolve().parent
AUTO = '--ja' in sys.argv or '--yes' in sys.argv
STORE = HOME / 'homebrew/plugins/armada-store/py_modules'
EMULATORS = ['retroarch', 'duckstation', 'dolphin', 'ppsspp', 'armsx2', 'azahar', 'melonds', 'flycast', 'ymir', 'cemu']
CORES = ['gambatte', 'mgba', 'nestopia', 'mesen', 'fceumm', 'snes9x', 'mupen64plus_next', 'parallel_n64', 'genesis_plus_gx', 'picodrive',
         'swanstation', 'pcsx_rearmed', 'fbneo', 'mame2003_plus', 'mednafen_pce_fast', 'mednafen_saturn', 'melondsds', 'flycast']
RA = HOME / '.var/app/org.libretro.RetroArch/config/retroarch'
EN = not os.environ.get('LANG', 'de').lower().startswith('de')  # the terminal's language; Tandem starts in it too (see language)
sys.path.insert(0, str(HERE / 'ui'))
from lang import tr  # noqa: E402


def say(text=''): print(tr(text) if EN else text, flush=True)


def ask(question, default=True):
    if AUTO: return default
    answer = input(f'{tr(question) if EN else question} [{("Y/n" if default else "y/N") if EN else "J/n" if default else "j/N"}] ').strip().lower()
    return default if not answer else answer in ('j', 'ja', 'y', 'yes')


def run(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, **kw)


def sudo(cmd, stdin=None):
    """Run one command as root. Asks for the password on the terminal once if needed."""
    return subprocess.run(['sudo', *cmd], input=stdin, text=True).returncode == 0


def step(title):
    say(); say(f'── {title}')


def install_tandem():
    step('Toravo Tandem installieren')
    done = run(['bash', str(HERE / 'install.sh')])
    say(done.stdout.strip().splitlines()[0] if done.stdout.strip() else done.stderr.strip())


def language():
    sys.path.insert(0, str(HERE))
    import tandem
    if 'lang' not in tandem.load_config(): tandem.save_config({'lang': 'en' if EN else 'de'})


def own_session():
    step('Eigene Sitzung')
    say('Tandem kann den Spielmodus ganz übernehmen: Das Gerät startet direkt in Tandem, Steam läuft nicht im Hintergrund.')
    say('Steam gibt es dann über Apps › „Steam starten“ für jeweils eine Sitzung.')
    target, flag = HOME / '.config/gamescope-session-plus/sessions.d/steam', HOME / '.config/tandem/own-session'
    if ask('Tandem als eigenes System einrichten?'):
        target.parent.mkdir(parents=True, exist_ok=True); flag.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / 'session-override', target); flag.touch()
        say('Eingerichtet. Gilt ab dem nächsten Start des Spielmodus.')
    else:
        flag.unlink(missing_ok=True)
        run(['python3', str(HERE / 'addshortcut.py')])
        say('Tandem steht als Eintrag in Steam (Bibliothek › Steam-fremd).')


def game_card():
    step('Spielekarte')
    parts = [l.split() for l in run(['lsblk', '-rno', 'NAME,FSTYPE,LABEL,MOUNTPOINT']).stdout.splitlines()]
    cards = [p for p in parts if len(p) >= 3 and p[0].startswith('mmcblk') and p[1] in ('exfat', 'vfat') and len(p) == 3]
    if not cards: return say('Keine nicht eingehängte exFAT-/FAT-Karte gefunden (ext4-Karten hängt ArmadaOS selbst ein).')
    _, fstype, label = cards[0]
    say(f'Gefunden: Karte „{label}“ ({fstype}). ArmadaOS hängt solche Karten nicht von selbst ein.')
    if f'LABEL={label} ' in Path('/etc/fstab').read_text(): return say('Ist schon dauerhaft eingetragen.')
    if not ask('Dauerhaft einhängen (Eintrag in /etc/fstab, mit Sicherungskopie)?'): return
    line = f'LABEL={label} /run/media/{os.environ.get("USER", "armada")}/{label} {fstype} uid={os.getuid()},gid={os.getgid()},umask=0022,noatime,nofail,x-systemd.device-timeout=8 0 0\n'
    script = f'cp -n /etc/fstab /etc/fstab.bak-tandem && cat >> /etc/fstab && systemctl daemon-reload && mkdir -p /run/media/{os.environ.get("USER", "armada")}/{label} && mount /run/media/{os.environ.get("USER", "armada")}/{label}'
    say('Eingehängt.' if sudo(['sh', '-c', script], stdin=line) else 'Das hat nicht geklappt – bitte von Hand prüfen.')


def emulators():
    step('Emulatoren')
    if not STORE.is_dir(): return say('Der Armada Store ist nicht installiert – Emulatoren bitte dort einrichten.')
    say('Vorgesehen: ' + ', '.join(EMULATORS))
    if not ask('Diese Emulatoren über den Armada Store installieren (dauert einige Minuten, braucht das Passwort)?'): return
    code = f'''
import json, sys, time
sys.path.insert(0, {str(STORE)!r})
from armada_store import catalog, jobs
for app in {EMULATORS!r}:
    if catalog.installed_map().get(app, {{}}).get("installed"): print(app, "ist schon da", flush=True); continue
    jobs.start(app, "install")
    for _ in range(360):
        time.sleep(5)
        mine = [j for j in jobs.status() if j.get("appId") == app]
        if not mine or mine[0].get("phase") in ("done", "error", "failed", "cancelled"): break
    try: jobs.dismiss(app)
    except Exception: pass
    print(app, "installiert" if catalog.installed_map().get(app, {{}}).get("installed") else "NICHT installiert", flush=True)
'''
    sudo(['python3', '-c', code])


def retroarch():
    step('RetroArch einrichten')
    if not (RA / 'retroarch.cfg').is_file(): return say('RetroArch ist nicht installiert – übersprungen.')
    cores = RA / 'cores'; cores.mkdir(parents=True, exist_ok=True)
    missing = [c for c in CORES if not (cores / f'{c}_libretro.so').is_file()]
    if missing and ask(f'{len(missing)} Cores für die gängigen Systeme laden?'):
        import io, zipfile
        for core in missing:
            try:
                data = urllib.request.urlopen(f'https://buildbot.libretro.com/nightly/linux/aarch64/latest/{core}_libretro.so.zip', timeout=120).read()
                zipfile.ZipFile(io.BytesIO(data)).extractall(cores); say(f'  {core}')
            except Exception: say(f'  {core}: nicht verfügbar')
    text = (RA / 'retroarch.cfg').read_text(errors='replace')
    if not (RA / 'retroarch.cfg.bak-tandem').exists(): shutil.copy2(RA / 'retroarch.cfg', RA / 'retroarch.cfg.bak-tandem')
    # Tandem's on-screen buttons need the network commands; Vulkan and Select-based hotkeys suit the handheld.
    wanted = {'network_cmd_enable': 'true', 'network_cmd_port': '55355', 'video_driver': 'vulkan', 'video_fullscreen': 'true',
              'input_enable_hotkey_btn': '6', 'input_exit_emulator_btn': '7', 'input_save_state_btn': '5', 'input_load_state_btn': '4',
              'input_menu_toggle_gamepad_combo': '2', 'pause_nonactive': 'false'}
    for key, value in wanted.items():
        line, pattern = f'{key} = "{value}"', re.compile(r'(?m)^' + re.escape(key) + r' = .*$')
        text = pattern.sub(lambda _: line, text, count=1) if pattern.search(text) else text.rstrip('\n') + '\n' + line + '\n'
    (RA / 'retroarch.cfg').write_text(text)
    say('RetroArch: Tasten auf dem unteren Bildschirm aktiv, Kürzel Select+Start (Beenden), Select+R1/L1 (Speichern/Laden).')


def quiet_first_runs():
    step('Erststart-Dialoge der Emulatoren abstellen')
    policy = HOME / '.config/auto-updates-policy'; policy.mkdir(parents=True, exist_ok=True); (policy / 'no_updatecheck').touch()
    dolphin = HOME / '.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/Dolphin.ini'
    if dolphin.is_file() and 'PermissionAsked' not in dolphin.read_text():
        dolphin.write_text(dolphin.read_text().replace('[Analytics]', '[Analytics]\nPermissionAsked = True\nEnabled = False', 1))
    shortcut = HOME / '.local/share/applications/org.duckstation.DuckStation.desktop'
    if (HOME / 'Applications/DuckStation.AppImage').is_file() and not shortcut.exists():
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        shortcut.write_text(f'[Desktop Entry]\nType=Application\nName=DuckStation\nExec={HOME}/Applications/DuckStation.AppImage %f\nTerminal=false\nCategories=Game;\n')
    say('Erledigt (Update-Fragen der AppImages, Dolphin-Statistikfrage, DuckStation-Verknüpfung).')


def main():
    say('Toravo Tandem – Einrichtung'); say('Jeder Schritt fragt vorher. Abbrechen mit Strg+C.')
    if not shutil.which('armada-run-bottom'): say('Hinweis: Das sieht nicht nach ArmadaOS aus. Tandem selbst läuft trotzdem.')
    for part in (install_tandem, language, own_session, game_card, emulators, retroarch, quiet_first_runs):
        try: part()
        except KeyboardInterrupt: say('\nAbgebrochen.'); return
        except Exception as error: say(f'Dieser Schritt ist fehlgeschlagen: {error}')
    step('Fertig')
    say('Spielmodus neu starten (oder Gerät neu starten), dann erscheint Tandem.')
    say('Konto für RetroAchievements, WLAN und Tastatur stellst du in Tandem unter „Einstellungen“ ein – oder vom Handy/PC über die dort gezeigte Adresse.')


if __name__ == '__main__':
    main()
