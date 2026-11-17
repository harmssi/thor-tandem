#!/usr/bin/env python3
"""setup.py <HD Edition folder> <VCMI data folder> <VCMI config folder>: makes VCMI data out of the player's Steam
"Heroes III HD Edition", the way the Android port "Heroes III Thor Edition" does it on the device (HdImport.java,
RoeSetup.java), with the fork's own tools next to this file (roe-bridge/, see build.sh).

The HD Edition has only Restoration of Erathia, in the game's first table layout; VCMI expects Shadow of Death's.
- Links (nothing is copied, the player's files are only read): the archives, sounds, maps, music and videos VCMI needs,
  under the names it looks for; the localized archive of the system's language wins (else the first one there).
- Written into the data folder: the text tables in VCMI's layout, the hero screen, and the mod "roe-support" with the
  campaigns converted from the player's own files; the mod is switched on in modSettings.json.
Runs on every start and does the conversion once (a marker holds its version and the folder it was made from).
"""
import json, os, shutil, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = '9'  # RoeBridge.VERSION of the Android port: what the conversion puts out


def plan(hd, lang):
    """(source, target folder, name) for every file VCMI gets, as HdImport.list; later entries replace earlier ones."""
    def child(folder, name):
        return next((f for f in sorted(folder.iterdir()) if f.name.lower() == name.lower()), None) if folder and folder.is_dir() else None

    def files(folder, target, *exts):
        return [(f, target, f.name) for f in sorted(folder.iterdir()) if f.is_file() and f.suffix.lower() in exts] if folder and folder.is_dir() else []
    data = child(hd, 'data')
    out = [(child(data, name), 'Data', to) for name, to in (('H3BITMAP.LOD', 'H3bitmap.lod'), ('H3SPRITE.LOD', 'H3sprite.lod'), ('HEROES3.SND', 'Heroes3.snd'))]
    out += files(child(data, 'maps'), 'Maps', '.h3m', '.tut') + files(child(data, 'mp3'), 'Mp3', '.mp3') + files(child(data, 'VIDEO'), 'Video', '.ogv')
    langs = [d for d in sorted(child(data, 'LOC').iterdir()) if d.is_dir()] if child(data, 'LOC') else []
    loc = next((d for d in langs if d.name.lower() == lang.lower()), langs[0] if langs else None)
    if loc:
        out += [(child(loc, 'h3bitmap.lod'), 'Data', 'H3pbitma.lod'), (child(loc, 'heroes3cd.snd'), 'Data', 'Heroes3-cd2.snd')]
        out += files(loc, 'Video', '.ogv') + files(child(child(data, 'maps'), loc.name), 'Maps', '.h3m', '.tut')
    return [entry for entry in out if entry[0]]


def enable_mod(settings):
    """'roe-support' into the active preset of modSettings.json (as RoeSetup.enableMod); True if the file changed."""
    try: o = json.loads(settings.read_text())
    except (OSError, ValueError): o = {'activePreset': 'default', 'presets': {'default': {'mods': ['vcmi', 'core']}}}
    mods = o.setdefault('presets', {}).setdefault(o.get('activePreset', 'default'), {}).setdefault('mods', [])
    if 'roe-support' in mods: return False
    mods.append('roe-support')
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(o, indent=1))
    return True


def main(hd, root, config):
    for source, target, name in plan(hd, os.environ.get('LANG', 'en')[:2]):
        link = root / target / name
        link.parent.mkdir(parents=True, exist_ok=True)
        if not (link.is_symlink() and link.readlink() == source):
            link.unlink(missing_ok=True)
            link.symlink_to(source)
    data, marker = root / 'Data', root / 'Data/.thor-roe-bridge'
    if not (data / 'H3bitmap.lod').exists(): sys.exit(f'{hd}: no data/H3BITMAP.LOD')
    if marker.exists() and marker.read_text().split('\n') == [VERSION, str(hd)]:
        enable_mod(config / 'modSettings.json')  # stays on whatever rewrote the file
        return
    os.environ['VCMI_CONFIG'] = str(HERE / 'config')  # VCMI's own tables, read by the bridge
    sys.path.insert(0, str(HERE / 'roe-bridge'))
    import campaigns, convert
    from legacy import lod_files
    convert.selfcheck(convert.convert(str(data), str(data)))  # stops on anything but Restoration of Erathia tables
    mod = root / 'Mods/roe-support'
    shutil.rmtree(mod, ignore_errors=True)
    zipfile.ZipFile(HERE / 'roe-bridge/roe_support.zip').extractall(mod)
    tables = lod_files(str(data / 'H3bitmap.lod'))
    if (data / 'H3pbitma.lod').exists(): tables.update(lod_files(str(data / 'H3pbitma.lod')))
    made = campaigns.build(tables, str(mod / 'content/data'))
    enable_mod(config / 'modSettings.json')
    marker.write_text(VERSION + '\n' + str(hd))
    print(f'Heroes III: HD Edition (Restoration of Erathia) set up for VCMI, {len(made)} campaigns')


if __name__ == '__main__':
    if len(sys.argv) != 4: sys.exit(__doc__)
    main(*(Path(p) for p in sys.argv[1:]))
