# Toravo Tandem

**English:** a dual-screen front end for ArmadaOS on the AYN Thor – the game on the top screen, a companion made for it on
the bottom screen. Interface in English or German (Settings › Look › Language). Bring your own games.

Install on the Thor (desktop mode › Konsole, one line):

    curl -L https://github.com/harmssi/thor-tandem/releases/latest/download/get.sh | bash

New in 1.1.0 (**HyperDrive Ultra**): **1-Click Adreno 740 Mesa-Git Turnip Updater** (`Droid-Deck/Drivers` Linux ARM64 `glibc` builds with SHA-256 & ELF64 validation + `.prev` rollback, immediately selectable under `Performance › Turnip` and Quick Menu Pro), **Zero-Config Per-Game Smart Presets** (`720p SGSR` for heavy 3D Steam games, `Strict TSO` for sensitive Unity titles), **12 GB+ RAM-Pinning & Prime-Core Replay Affinity** (`DM_MEM_FILEBACK=0`, `DM_VK_PSO_SLOTS=4`, `DM_VK_AFF_REPLAY=0x80`), and `mitigations=off` ARM64 syscall tuning in the OS image.

New in 1.0.0 (**HyperDrive Edition**): **1-Tap `⚡ HyperDrive` Engine (`thor.py`, `thor_perf.py`)** combining live **Turnip WinNative 27.0 / Devel 27.0 / Stable** driver switching (with direct `VK_DRIVER_FILES` isolation stripping `llvmpipe` / ~120 MB LLVM RSS), **FEX Fast-JIT** (`TSOEnabled=0`, `Multiblock=1`, `X87ReducedPrecision=1` + automatic `proton-cachyos-11.0-arm64` ARM64EC wiring across all Steam games, PC ports & 3D emulators), live **SteamOS `scx_lavd` / `scx_cosmos` Kernel BPF Schedulers**, and **Asymmetric Dual-Screen Core Isolation** (Gold + Prime `CPU 3–7` + `nice -10` exclusively for games, Silver `CPU 0–2` for Tandem & the bottom-screen Companion = 0 % CPU tax); **4 Hardware Profiles** (`Eco`, `schedutil` `Balanced`, `Performance` with `300 MHz` UFS 4.0 boost, and **`Turbo` `2.96 GHz` + `680 MHz` Adreno 740 lock**), **Quick Menu Pro** (live CPU/GPU/RAM/scheduler readout, Adreno GPU clock lock `401/550/680 MHz`, Smart Fan `Auto/Quiet/Cool/Max`, and **1-Tap `720p Boost` / `900p SGSR` Super-Resolution**), native **Gamescope X11 Low-Latency Mode**, **OLED Color Vibrance** (`GAMESCOPE_COLOR_SDR_GAMUT_WIDENESS`) & 3D-LUT Night Mode, `lz4` ZRAM, **Ambient Stick-RGB** synced to game cover art, **11 curated OLED themes** (+Cyber Neon, Synthwave, Nord Frost, Crimson Ember, Emerald OLED, Midnight Gold), **tactile LRA console haptics** across all menus, and a 1-tap **Random Game** picker.

New in 0.6.0: **Automatic Game Companion Provisioner & Obtainium-Class Integrated Update Service (`thor_updater.py`, `ui/settings_view.py`, `remote.html`)** – automatically detects your installed Steam games (*FINAL FANTASY IX*, *Fallout 4*, *Persona 5 Royal*), GB/GBC/GBA ROMs (multi-region & ROM-hack matching against 32+ GBADuo v1.0.1 packs + automatic RetroArch UDP `55355` setup) and native PC ports, installing & updating their bottom-screen companions in the background; tracks upstream ARM64 AppImage releases (`DuckStation`, `ARMSX2`, `Azahar Enhanced`, `melonDS`, `Cemu`, `Eden`, plus custom `owner/repo` GitHub sources) via real SHA-256 digest comparison with **1-Tap `.prev` Rollback**, controller-mapping preservation, Flatpak updates and automatic Libretro ARM64 core downloads; **Integrated Linux & Tandem `.tar.zst` Backup + Live Retroactive Android Partition Shrinker (`thor_storage.py`)** reclaiming up to `+105 GiB` UFS 4.0 storage live into Linux Btrfs; **On-The-Go Battery Saver (`Eco + 60 Hz + LEDs off + auto-battery`) & USB-PD / PPS Fast-Charge Diagnostics**; direct native ARM64 launchers for **Claude Code** & **Google Antigravity (`agy`)** in `--dangerously-skip-permissions` mode with an AI terminal quick-bar; **Touchscreen 2.0** (120 Hz kinetic scrolling, fast-scrub bar, 1:1 Stage drag, tile long-press menu, bezel swipe gestures), menu-free **Last in-game** (`Zuletzt im Spiel`) scene previews, installed-only Steam library filtering, and a sprite-cached **60-FPS 28-cover `Thor Cosmos` OLED screensaver** with an orange-framed `Toravo Tandem` clock badge.

New in 0.5.0: Dual-Screen OLED Screensaver (`ui/screensaver.py`) across both OLED panels with pure `#000000` burn-in protection, featuring **Thor Cosmos (Original Box Art)** (floating original retail game boxes in their true SNES/N64/GBA/PS1/GameCube/Switch packaging proportions with subtle 3D case depth, smoothly crossing the hinge from top to bottom screen), **Arcade Showcase**, **Dual Aurora** and **Minimal OLED Clock**; automatic original retail box-art scraper (`libretro-thumbnails` + `GameTDB` Switch cases); Switch-2-inspired Universal **Mouse Mode** (`Maus` tab in `ui/decks/universal.py`, turning the bottom screen into a precision `/dev/uinput` trackpad in any game), Home-screen **Game Pinning** (`PIN` virtual game cards), **80 % / 90 % Battery Charge Care** & battery health/cycle telemetry, **Device Locator** (ascending chime + LRA haptic pulses from the web dashboard), optional subtle synthesized UI console sounds, and built-in **Peanuts Native & BananaNative** Switch game discovery, update uploader & on-device conversion panel.

New in 0.4.0: redesigned Bento Thor-key Quick Menu with live MangoHud FPS/frametime overlay toggle (`Off · FPS · Bar · Graph`) on the top screen, live battery wattage/runtime telemetry and 1-tap Fast Game Switcher; unified gamepad layout across every console & emulator (`Thor print`: Right A = Confirm / Bottom B = Back everywhere including PlayStation, PSP, Dreamcast, Wii, Wii U, GameCube, Switch, 3DS, DS & RetroArch, with optional `Xbox style` toggle); redesigned multi-view sidebar web dashboard (`remote.html`) with 7-day playtime analytics, top played games, Drag-&-Drop ROM/guide/pack upload and Time-Machine savegame restore; 55+ ES-DE console/computer systems (including `sfc` Super Famicom, `famicom`, `fds`, Neo Geo, CPS-1/2/3, Naomi/Atomiswave, 32X, PCE-CD, WonderSwan, Lynx, 3DO, Amiga, C64, DOS, ScummVM, PICO-8), `.m3u` multi-disc deduplication, `gamelist.xml` metadata (descriptions, year, genre, studio, playtime-to-beat), library sorting, custom collections & per-game emulator/core selector; true interactive Dual-Screen mode (`ui/decks/dualscreen.py`) for DS (`melonDS`), 3DS (`Azahar`) and Wii U (`Cemu`) with live X11 touch forwarding; Universal Companion Deck (`ui/decks/universal.py`) for every game with visual save-state thumbnails, finger-sketch pad & checklist notes, zoomable map/walkthrough & offline Wiki reader, independent PipeWire background-music mixer, and live hardware Cockpit; Moonlight/Chiaki precision trackpad & Wake-on-LAN deck (`ui/decks/pcstream.py`); closed-lid headphone music mode, and automatic USB-C TV/Dock OLED dimming.

New in 0.3.0: native YouTube and Plex dual-screen apps (`mpv` on top, touch/controller browser below) with QR-code phone sign-in (subscriptions, playlists, likes) and offline SD-card downloads; tactile 3D on-screen keyboard with LRA haptic feedback, floating key magnifier, hold-to-repeat, dedicated `@` key and X11 keysym injection; Stage carousel view, Cocoon platform frames, night mode, per-game scaling/FPS/power overrides, lid & charger-aware standby, Captures gallery, Bluetooth audio/gamepad pairing, volume hold-to-repeat & mute, and rolling SD + SSH savegame backups.

New in 0.2.0: English interface; Thor-key quick menu on the bottom screen (brightness, volume, power mode, stick lights,
frame generation, recording, screenshot); recording of both screens; a frame generation switch for Lossless Scaling (needs your own Lossless Scaling copy and the lsfg-vk layer installed);
WoW Forever signs in on its own (login stored on the device, like the Android launcher) and picks your game account.

---

Dual-Screen-Oberfläche für ArmadaOS auf dem AYN Thor: oben das ausgewählte oder laufende Spiel, unten Kacheln zum
Bedienen.

## Was es kann

- Liest ROMs im ES-DE-Aufbau (`ROMs/<system>/…`) aus `~/ROMs` und von eingehängten Karten (`/run/media/…/ROMs`).
- Nimmt Cover und Hintergrundbilder aus `ES-DE/downloaded_media` und `Cocoon/downloaded_media` neben dem ROM-Ordner –
  die Bilder der Cocoon-Bibliothek werden also weiterverwendet.
- Startet den passenden Emulator aus dem Armada Store (RetroArch, DuckStation, ARMSX2, Dolphin, PPSSPP, Azahar, melonDS,
  Flycast, Cemu, Ymir). Fehlt einer, steht oben, was zu installieren ist.
- Zeigt installierte Steam-Spiele und startet sie über Steam.
- Startet native Ports (Half-Life, Opposing Force, Blue Shift, Age of Kings, Red Alert 2, Command & Conquer, Red Alert, Heroes III, KKnD 2) mit eigenem Deck auf dem unteren Bildschirm, siehe „Native Ports“.
- Favoriten (Y), zuletzt gespielt und Spielzeit; „Spiel beenden“ auf dem unteren Bildschirm.
- Bedienung: Steuerkreuz/Stick, A starten, B zurück, LB/RB Reiter, Y Favorit; unten auch per Tippen.
- Aussehen: klare Schrift (Inter), viel Luft, runde Kacheln; die gewählte Kachel hebt sich weich an (Leuchten in der
  Farbe des Spiels, Ring, Glanz), oben blendet das Bild des Spiels über. Oben rechts eine Statuszeile wie beim 3DS
  (Datum, Uhrzeit, WLAN-Stärke, Akku mit Ladeblitz). Bewegung gibt es nur, wenn sich etwas ändert; im Leerlauf zeichnet
  nichts neu.
- OLED: Die Statuszeile ist gedimmt, liegt auf dem wechselnden Spielbild und wandert alle fünf Minuten um ein paar
  Pixel; „Spiel beenden“ ist nur getönt statt voll gefüllt (steht das ganze Spiel über da). Nach der Ruhezeit (Standard
  3 Minuten) wird es schwarz mit wandernder Uhr.

## Auf den Thor bringen

Voraussetzung: ArmadaOS läuft und ist im WLAN, Fernzugriff ist an (`sudo systemctl enable --now sshd`).

Auf dem Gerät (Desktop-Modus › Konsole, oder per SSH) diese eine Zeile ausführen. Sie lädt die neueste Version, prüft
ihre Prüfsumme und startet den Einrichtungsassistenten, der jeden Schritt vorher fragt:

    curl -L https://github.com/harmssi/thor-tandem/releases/latest/download/get.sh | bash

Danach hält sich Tandem selbst aktuell: Es sieht einmal täglich nach einer neuen Version und meldet sie; installiert
wird auf der Einstellungsseite unter „Gerät“ (dort lässt sich die Update-Quelle auch leeren = nie nachsehen).

Aus dem Quelltext statt aus einem Release:

    rsync -a tandem armada@armada.local:
    ssh armada@armada.local 'cd tandem && ./install.sh'

**Eigene Sitzung ohne Steam** (so läuft es auf dem Thor): `session-override` nach
`~/.config/gamescope-session-plus/sessions.d/steam` kopieren und `~/.config/tandem/own-session` anlegen. Dann startet
der Spielmodus Tandem statt Steam; Steam gibt es über Apps › „Steam starten“ für genau eine Sitzung. Zurück zum
Originalzustand: beide Dateien löschen.

Als Steam-Eintrag (wenn Steam die Oberfläche bleiben soll): `python3 addshortcut.py`, solange Steam nicht läuft.

Entfernen: `~/tandem/install.sh --remove`.

## Aufbau

| Datei | Zweck |
|---|---|
| `tandem.py` | Dienst: Bibliothek einlesen, Bilder ausliefern, Emulatoren starten und beenden, beide Fenster abgleichen |
| `ui/tandem_ui.py` | Oberfläche auf dem Thor: natives Programm (PySide6, QPainter), je Bildschirm ein Prozess (`--screen top\|bottom`) |
| `ui/decks/ffix.py` | Begleiter für Final Fantasy IX auf dem unteren Bildschirm (nativ) |
| `ui/decks/pipboy.py` | Pip-Boy für Fallout 4 auf dem unteren Bildschirm (nativ) |
| `ui/decks/pack.py` | Begleiter-Pakete für emulierte Spiele (mit `packlua.py`, `packmem.py`, `packcss.py`), siehe unten |
| `ui/decks/hev.py` | HEV-Deck für Half-Life, Opposing Force und Blue Shift auf dem unteren Bildschirm (nativ) |
| `ui/decks/portsocket.py` | Deck-Seite des Deck-Sockets für native Ports, siehe unten |
| `ports/tandem_deck.h` | Spiel-Seite des Deck-Sockets (eine C-Datei zum Einbinden) |
| `ports/halflife/` | Nativer Port Half-Life: `build.sh` (baut `dist/`), `run` (Starter) |
| `ui/decks/aok.py` | Befehlsdeck für Age of Kings auf dem unteren Bildschirm (nativ), im Aussehen des Spiels |
| `ports/aok/` | Nativer Port Age of Kings (Engine OpenAoK): `build.sh`, `run`, `deck_socket.inc` (Spiel-Seite des Decks) |
| `ui/decks/ra2.py` | Befehlsdeck für Red Alert 2 / Yuri's Revenge auf dem unteren Bildschirm (nativ): die Seitenleiste der eigenen Seite |
| `ports/ra2/` | Nativer Port Red Alert 2 (Engine Thor RA2): `build.sh`, `run`; die Spiel-Seite des Decks steckt in der Engine (`engine/thor.cpp`) |
| `ui/decks/cnc.py` | Befehlsdeck für Command & Conquer und Red Alert auf dem unteren Bildschirm (nativ): die Seitenleiste des Spiels |
| `ports/cnc/` | Nativer Port Command & Conquer / Red Alert (Engine Thor Conquer): `build.sh`, `run`; die Spiel-Seite des Decks steckt in der Engine (`common/thor_tandem.cpp`) |
| `ui/decks/homm3.py` | Deck für Heroes of Might and Magic III auf dem unteren Bildschirm (nativ), im Aussehen des Spiels |
| `ui/decks/kknd2.py` | Deck für KKnD 2: Krossfire auf dem unteren Bildschirm (nativ), im Aussehen der eigenen Fraktion |
| `ports/kknd2/` | Nativer Port KKnD 2 (OpenRA + OpenKrush, „KKND2 Thor“): `build.sh`, `run`; die Spiel-Seite des Decks steckt im Checkout (`thor/linux/TandemDeck.cs`) |
| `ports/homm3/` | Nativer Port Heroes III (VCMI-Fork „Heroes III Thor Edition“): `build.sh`, `run`, `setup.py` (macht aus der Steam HD Edition VCMI-Daten); die Spiel-Seite des Decks steckt im Fork (`client/thor/ThorDeck.cpp`) |
| `thor_perf.py` | Hardware- & HyperDrive-Engine: CPU-Cluster, Adreno-740-GPU-Lock (680 MHz), UFS-4.0-Boost, Big-Core-Isolierung, FEX/Turnip/Vulkan-Tuning |
| `ui/quick_view.py` | Quick Menu Pro auf der Thor-Taste: HyperDrive, Turnip-Wahl, GPU-Takt, Lüfter, 720p/900p-SGSR, Schnellwechsel, Ambient-RGB |
| `ui/themes/*.json` | 11 mitgelieferte OLED-Themes (Toravo, Cocoon, Cyber Neon, Synthwave, Nord Frost, Crimson Ember, Emerald OLED, Midnight Gold, Studio, OLED, Hell) |
| `ui/fonts/` | Schriften mit Lizenz (SIL OFL 1.1): Inter (Oberfläche, `Inter-OFL.txt`), Barlow (Begleiter, `OFL.txt`) |
| `ui/test_ui.py` | Selbsttest der nativen Oberfläche ohne Bildschirm: `QT_QPA_PLATFORM=offscreen python3 ui/test_ui.py` |
| `index.html` | Dieselbe Oberfläche als Seite: Vorschau mit Beispieldaten und Rückweg `TANDEM_UI=firefox` |
| `tandem-launch` | Startet Dienst und beide Fenster (nativ; mit `TANDEM_UI=firefox` oder ohne PySide6 Firefox) |
| `install.sh` | Kopiert alles nach `~/.local/share/tandem` und trägt Tandem in Steam ein |
| `test_tandem.py` | Selbsttest: `python3 test_tandem.py` |

Am Mac ausprobieren: `python3 tandem.py --roms <ordner>/ROMs --dry-run` und http://127.0.0.1:8377/ öffnen.

## Einstellungsseite und HTTPS

Die Seite läuft im Heimnetz über einfaches HTTP. Tandem merkt sich bis zu zehn Browser (nur die Prüfsumme des Schlüssels,
in `~/.config/tandem/devices.json`, nur für den Besitzer lesbar). Echtes HTTPS braucht ein Zertifikat für einen Namen, der
auf den Thor zeigt (eigene Domain), oder einen Reverse-Proxy davor (der `X-Forwarded-Proto: https` mitschickt). Liegen
`~/.config/tandem/tls.crt` und `tls.key` vor, liefert Tandem die Seite selbst über HTTPS aus und zeigt `https://` an. Ein
selbst gemachtes Zertifikat erzeugt Tandem absichtlich nicht: die Browser-Warnung wäre schlechter als HTTP im Heimnetz.

## Aussehen (Themes)

Ein Theme ist eine JSON-Datei. Mitgeliefert (`ui/themes/`): Toravo (Standard), Studio, OLED, Hell. Eigene Dateien nach
`~/.config/tandem/themes/<name>.json` legen – sie erscheinen in der Auswahl (Einstellungen › Aussehen, am
Gerät wie auf der Einstellungsseite). Alles ist freiwillig; was fehlt oder falsch ist, behält den Toravo-Wert:

    {
      "name": "Mein Theme",
      "colors": {"bg": "#0a0c13", "panel": "#141824", "raised": "#1e2434", "line": "#2c3449", "text": "#eef0f6",
                 "muted": "#8d94aa", "accent": "#ffb23e", "live": "#39d0b8", "warn": "#ff7a66"},
      "gradient": ["#8a5cf6", "#6f9be0", "#5ab0d0"],   Verlauf für Balken (2–4 Farben), sonst die Akzentfarbe
      "fonts": {"ui": ["Inter", "Adwaita Sans"],   Schrift der Oberfläche; erste vorhandene gilt
                "display": ["Barlow Condensed"], "body": ["Barlow", "Noto Sans"]},   Schriften, die Begleiter nutzen
      "radius": 1.0,          Eckenrundung als Faktor (0 = eckig, bis 3)
      "glow": 1.0,            Leuchten um die Auswahl (0 bis 1)
      "background": "bild.jpg",   Hintergrundbild neben der Datei (kostet Speicher: ein Bild in Bildschirmgröße)
      "gameAccent": true      Akzentfarbe aus dem Cover des gewählten oder laufenden Spiels (false = immer "accent")
    }

Farben nur als `#rrggbb`. Die Spielfarbe wird einmal je Cover aus einer 24-Pixel-Fassung bestimmt, auf lesbaren Kontrast
zum Hintergrund gebracht und in `~/.cache/tandem/accents.json` gemerkt. Eigene Begleiter (FF IX, Pip-Boy) behalten ihr Aussehen.

## Einstellungen

Aufgebaut wie die Einstellungen eines iPad: links die Bereiche, rechts der gewählte Bereich in Gruppen, oben erklärt der
obere Bildschirm die Zeile im Fokus (Name, Wert, ein Satz dazu). Jede Änderung wirkt sofort. Bedienung mit Controller und
Finger gleich: in der Liste ↑/↓ wählen, A oder → öffnen, B zurück zur Bibliothek; im Bereich ↑/↓ bewegen, ←/→ ändert
Werte (Regler, Auswahl, Farbe), A schaltet/öffnet, B zurück; „‹ Zurück“ steht immer oben links. Code: `ui/settings_view.py`.

| Bereich | Inhalt |
|---|---|
| Bildschirme & Ton | Helligkeit oben/unten, Lautstärke, Ruheschutz (OLED) |
| Controller & Tasten | Übersicht Tastenbelegung (`controls.TABLE`), „In allen Emulatoren angleichen“ (`controls.apply`), Gyro, Bildschirmtastatur |
| Beleuchtung | Stick-Ringe an/aus, Farbe, Helligkeit, mit dem Bildschirm koppeln |
| Leistung & Akku | Leistungsprofil Sparsam/Ausgewogen/Leistung (wird bei jedem Start wieder gesetzt), Akku, Temperatur, Lüfter |
| WLAN & Netzwerk, Konten, Aussehen, Bibliothek, Updates, Über den Thor, Ein / Aus | wie bisher, neu geordnet |

Die Einstellungsseite für Handy/PC (`remote.html`) hat dieselben Gruppen.

Thor-Funktionen ohne root (`thor.py`): `/run/armada/session.sock` kennt nur `game_launched` und `reapply_perf`. Stick-Licht
und Gyro gehen über ArmadaOS' Decky-Plugin „Armada Control“ (läuft als root; Aufruf über den Decky-Loader,
WebSocket auf 127.0.0.1:1337 mit Token von `/auth/token`, Methode `loader/call_plugin_method`). Antworten ordnet Decky
über alle Verbindungen nach der Aufruf-ID zu: jede Anfrage braucht eine zufällige ID. Leistungsprofil, Temperatur und Lüfter
kommen von armada-powerd (`org.armada.Power` auf dem Systembus, für die Gruppe wheel offen; `Profile` ist schreibbar,
`FanMode` nicht). Eine Ladegrenze bietet das Gerät nicht an (kein `charge_control_end_threshold`). Der Controller-Typ bleibt
unter Tandem fest Xbox 360 (`tandem-launch`), damit jede Belegung gleich liegt. Dienst: `GET/POST /api/thor`,
`GET/POST /api/controls`, `POST /api/selfupdate`.

## Begleiter je Spiel

Ein Spiel kann den unteren Bildschirm selbst füllen, solange es läuft. Als Seite: `decks/<appid>.html` (Firefox-Rückweg).
Nativ: ein Modul in `ui/decks/`, eingetragen in `DECKS` in `ui/tandem_ui.py`, mit `class Deck` (`__init__(window)`,
`paint(painter)`, `close()`). Es wird erst mit dem Spiel geladen und danach samt Bildern entladen. Vorhanden:
Final Fantasy IX (`ui/decks/ffix.py`, Steam 377840; braucht den Statusserver des Memoria-Builds auf Port 8766) und der
Pip-Boy für Fallout 4 (`ui/decks/pipboy.py`, Steam 377160; nur nativ, ohne Seite).

Fallout 4 braucht dafür im Spielordner dasselbe wie unter Android (Projekt thor-pipboy): F4SE 0.7.9 (`f4se_loader.exe`,
`f4se_1_11_240.dll`, `Data/Scripts`), die Address Library (`Data/F4SE/Plugins/version-1-11-240-0.bin`) und
`Data/F4SE/Plugins/ThorPipBoy.dll` (+ `.ini`); das Plugin lauscht auf `ws://127.0.0.1:8767`. Steam muss den Loader statt
des Launchers starten – Startoption des Spiels (in `localconfig.vdf`, Sicherung `localconfig.vdf.bak-tandem-fo4`):
`eval $(echo "/usr/libexec/armada/armada-game-launch %command%" | sed "s|Fallout4Launcher.exe|f4se_loader.exe|")`.

## Begleiter-Pakete für emulierte Spiele

Pakete im Format von gba-duo-wide (`manifest.json`, `layout.json`, `style.css`, `main.lua`, `assets/`; Beschreibung dort
unter `docs-packs/`) laufen auf dem unteren Bildschirm, solange ihr Spiel in RetroArch läuft (GB/GBC mit Gambatte, GBA mit
mGBA). Ablage: je Paket ein Ordner in `~/.config/tandem/packs/<name>/` (Zip vorher entpacken).

- **Zuordnung:** Beim Start liest der Dienst Spielcode und CRC32 aus dem ROM (auch im Zip) und nimmt das erste Paket, dessen
  `match` passt: Spielcode gelistet (und CRC, falls welche genannt sind); Pakete ohne Spielcode gehen allein nach CRC. Der
  Ordnername steht dann in `run.pack`. Ohne Paket bleibt die bisherige Ansicht im Spiel.
- **Reiter oben:** Begleiter · Erfolge (nur wenn es RetroAchievements zum Spiel gibt) · Steuerung (Helligkeit, Lautstärke,
  RetroArch-Tasten, Spiel beenden). Das Paket wird auf 538 × 468 (die Größe unter Android) gerechnet und eingepasst.
- **Lua:** `liblua-5.4.so` des Systems über ctypes, im Fensterprozess in einem eigenen Thread (kein zweiter Python-Prozess).
  Grenzen wie in der App: 1 Mio. Anweisungen je `update()`/Aktion, 5 Mio. beim Laden, 16 MB; ein Skript, das sie reißt,
  wird abgebrochen (auch durch eigenes `pcall` hindurch), der Bildschirm behält seinen Stand.
- **Speicher:** nur lesen (`READ_CORE_MEMORY`), seitenweise (GBA 4096, GB 256 Bytes); was das Skript zuletzt gebraucht hat,
  wird vor jedem Tick gebündelt geholt (eine Abfrage je zusammenhängendem Bereich), ROM-Seiten bleiben liegen.
  `mem.write*` antwortet `false` mit Grund. `mem.bank8` liest die GBC-Arbeitsspeicher-Bänke 2–7 ab `0x10000` (Gambattes
  feste Zuordnung; `0xD000` ist dort immer Bank 1, anders als am echten Bus).
- **Unterstützt:** alle Widgets (`box`, `row`, `column`, `text`, `image`, `bar`, `list`, `pages`, `tabs`, `button`,
  `spacer`), `visibleIf`, `classIf`, `bindStyle`, `onClick` (`set`, `navigate`, `back`, `call`), `ui` aus `update()`,
  `:pressed`; CSS wie beschrieben: Selektoren, `var()`, `@font-face`, `@media`, `calc()/min()/max()/clamp()`, Flexbox,
  Grid, `stack`, absolute Lage, Hintergrundbilder und `linear-gradient`, Rahmen, Radien, harte Schatten, Deckkraft,
  Textschatten; `gfx.decode/tilemap/sprite/layers`, `lz77`, `pack.require`, `log`.
- **Breitbild (GBA, GB, GBC):** Hat das Paket ein `game.lua` mit `wide()` und ist der Breitbild-Kern installiert
  (`wide-core/`, eigener Bau; liegt als `cores/tandem-wide/mgba_libretro.so`), startet das Spiel mit diesem Kern statt `mgba_libretro.so`. Der Dienst legt dazu `game.lua`
  und die Lua-Module des Pakets nach `…/retroarch/system/tandem-wide/` und den Schalter in die Datei `on` (`1`/`0`); der
  Kern liest ihn zweimal je Sekunde. Die reservierte Aktion `wideView` (`on`, `off`, `toggle`) schaltet über
  `POST /api/wide`, die Wahl bleibt je Spiel in `state.json` (anfangs aus, wie in der App). `_wide` und `_wideLabel`
  (`ON`, `OFF`, `N/A` ohne `wide()`) stimmen. Bild 284 × 160 (16:9), Game Boy 256 × 144; die Ränder zeigen sich nur, solange die Vorhersage
  der 16 Randspalten zu 85 % stimmt, sonst bleiben sie schwarz (Kampf, Menü). `frame()` läuft, Schreiben bleibt zu.
  Spielstände, Schnellspeicher und Kern-Optionen sind dieselben wie beim normalen mGBA-Kern (gleicher Name, gleicher
  Quellstand). Game-Boy-Spiele mit Breitbild-Paket laufen dafür in diesem mGBA statt in Gambatte; ihr bisheriger
  Spielstand wird als Verknüpfung übernommen (eine Datei für beide Kerne). Ohne Paket, ohne `wide()` oder ohne den Kern
  läuft alles wie bisher.
- **Nicht unterstützt:** Schreiben in
  den Spielspeicher, `values` im Manifest ohne Skript, `transition` (Wechsel sofort), `transform`, weiche Schatten
  (werden hart gezeichnet), `text.font` der alten Form. Geisterbereiche des GB (Echo-RAM, Modul-RAM) lesen sich als 0.
  Ohne eigene Schrift nimmt ein Paket Qts Standardschrift statt Roboto.
- Selbsttest: `ui/test_ui.py` mit einem eigenen Probe-Paket gegen einen UDP-Ersatz für RetroArch.

## Native Ports

Ein nativer Port ist ein Spiel, das für das Gerät selbst gebaut ist (kein Emulator, kein Steam). Er erscheint unter
Systeme › Ports und wird wie jedes andere Spiel gestartet und beendet. Die Spieldaten gehören dem Spieler und liegen nie
in diesem Projekt.

- **Bauen:** `ports/<name>/build.sh` baut in einem Debian-Container nach `ports/<name>/dist/` (nicht im Git). Für
  Half-Life: `SRC=<Checkout von Thor Half-Life> ports/halflife/build.sh` auf einem aarch64-Rechner mit Docker.
- **Installieren:** `install.sh` kopiert `dist/` und `run` jedes gebauten Ports nach `~/.local/share/tandem-ports/<name>/`.
  Das liegt neben Tandems eigenem Ordner, damit ein Update von Tandem den Port und seine Spielstände
  (`tandem-ports/<name>/data/`) nicht anfasst.
- **Eintragen:** eine Zeile in `PORTS` in `tandem.py`: Kennung → (Titel, Ordner, Argument für `run`, Deck in `ui/decks`
  oder `None`). Mehrere Spiele können denselben Ordner benutzen (Half-Life, Opposing Force und Blue Shift tun das).
- **Starten:** Tandem ruft `run <Argument>` auf und gibt `TANDEM_DECK_SOCKET` mit. `run` sucht die Spieldaten, legt den
  schreibbaren Ordner an und startet das Spiel. Beendet wird mit SIGTERM; das Spiel muss darauf sofort und sauber enden.
- **Half-Life-Spieldaten:** die eigene Steam-Kopie (`valve`, dazu `gearbox` und `bshift`). `run` nimmt `$HALFLIFE_DATA`,
  `~/Half-Life`, die Steam-Bibliothek im Home oder ein `steamapps/common/Half-Life` auf einer Karte; gelesen wird nur.
- **Age of Kings:** `SRC=<Checkout von OpenAoK> ports/aok/build.sh`. Die Spieldaten sind der Ordner, den die Werkzeuge der
  Engine aus der eigenen CD machen (`assets/`, `fonts/`, `original_game_1999/`). `run` nimmt `$OPENAOK_DATA`,
  `~/OpenAoK-data` oder einen Ordner `OpenAoK-data` auf einer Karte; gelesen wird nur. Profil, Spielstände und eigene
  Szenarien liegen in `tandem-ports/aok/data/OpenAoK/`. Der Controller spielt wie unter Android: linker Stick Zeiger,
  rechter Stick Karte, A/B Maustasten, X untätiger Dorfbewohner, Y Abbrechen, L Dorfzentrum, R untätiges Militär,
  Start Menü, Steuerkreuz Gruppen I–IV (mit ZR setzen), ZL Umschalt bzw. mit rechtem Stick Zoom.
- **Red Alert 2:** `SRC=<Checkout von Thor RA2> ports/ra2/build.sh` (baut die Engine mit `-DRA2_TANDEM` und legt das SDL2
  dazu, das sie selbst festschreibt: mit dem `sdl2-compat` des Geräts bleibt das Spielbild schwarz). Die Spieldaten sind
  der eigene Installationsordner mit `ra2.mix` und `ra2md.mix` (z. B. Steam: „Command & Conquer Red Alert II“). `run`
  nimmt `$RA2_DATA`, `~/RA2`, die Steam-Bibliothek im Home oder diesen Steam-Ordner auf einer Karte; gelesen wird nur.
  Einstellungen und Spielstände liegen in `tandem-ports/ra2/data/ra2engine/RA2/`. Zwei Einträge: „Red Alert 2“ (Yuri
  ist in der Gefechts-Lobby ausgeblendet) und „Yuri's Revenge“. Der Controller spielt wie unter Android: linker Stick
  Zeiger, A/B Maustasten, rechter Stick und Steuerkreuz Karte (in Menüs springt das Steuerkreuz von Knopf zu Knopf),
  Start Menü, Back Basis, X aufstellen, Y Stopp, L3 halten Feuer erzwingen, L2 alle vom Typ, R2 bewachen, R3 ganze
  Armee, L1/R1 Bau-Reiter des Decks. Das Deck fordert Radar, Cameos, Seitenleisten-Grafik und Schrift als Binärblöcke
  an (`radar`, `pic <schlüssel>`), die die Engine zur Laufzeit aus den Spieldaten liest.
- **Command & Conquer / Red Alert:** `SRC=<Checkout von Thor Conquer> ports/cnc/build.sh` (baut die Engine mit
  `-DTHOR_TANDEM=ON`; SDL2 und OpenAL sind die des Geräts). Die Spieldaten sind der Ordner `Data/CNCDATA` der eigenen
  C&C Remastered Collection (die originalen MIX-Dateien). `run` nimmt `$CNC_DATA`, `~/CNCDATA`, die Steam-Bibliothek im
  Home oder einen Steam-Ordner `CnCRemastered` auf einer Karte; gelesen wird nur (die Engine bekommt Verweise in
  `tandem-ports/cnc/data/<td|ra>/files`). Einstellungen und Spielstände liegen in `tandem-ports/cnc/data/<td|ra>/home`;
  `tandem-ports/cnc/data/settings` (optional) setzt z. B. `THOR_SKIP_MOVIES=1` oder `THOR_POINTER_SPEED=14`. Zwei
  Einträge: „Command & Conquer“ (Tiberian Dawn) und „Command & Conquer: Red Alert“. Der Controller spielt wie unter
  Android: linker Stick Zeiger (R2 beschleunigt), rechter Stick Karte, A/B Maustasten, Select Menü, Start Enter, X/Y
  Bewachen/Formation (G/F), Steuerkreuz Gruppen 1–4, L1/R1 Ring durch die Bau-Cameos des Decks (A baut das markierte),
  R3 nächste Einheit, L3 Basis. Das Deck fordert Radar, Cameos, Seitenleisten-Grafik und Schriften als Binärblöcke an
  (`radar`, `pic <schlüssel>`), die die Engine zur Laufzeit aus den Spieldaten liest.
- **Heroes of Might and Magic III:** `SRC=<Checkout der Heroes III Thor Edition, Zweig tandem-linux> ports/homm3/build.sh` (baut
  Client und Server des VCMI-Forks mit `-DTHOR_TANDEM`, ohne Launcher und Karteneditor; Boost, TBB, squish, ein SDL2_mixer
  ohne fremde Codecs und ein kleines FFmpeg für die Videos liegen in `dist/` bei, SDL2 ist das des Geräts). Die Spieldaten
  sind der eigene Steam-Ordner „Heroes of Might & Magic III - HD Edition“ (der mit `HOMM3 2.0.exe`). `run` nimmt
  `$HOMM3_DATA`, `~/HoMM3-HD`, die Steam-Bibliothek im Home oder diesen Steam-Ordner auf einer Karte; gelesen wird nur.
  Die HD Edition enthält nur Restoration of Erathia in der ersten Tabellenform; `dist/setup.py` macht daraus beim ersten
  Start mit den Werkzeugen des Forks (`roe-bridge`, wie die Android-Version auf dem Gerät) VCMI-Daten in
  `tandem-ports/homm3/data/vcmi`: Verweise auf Archive, Töne, Karten, Musik und Videos, dazu die umgeschriebenen
  Texttabellen und der Mod „roe-support“ mit den umgewandelten Kampagnen. Einstellungen liegen in
  `tandem-ports/homm3/data/config/vcmi`, Spielstände in `data/vcmi/Saves`, das Protokoll in `data/cache/vcmi`. Beim
  ersten Start schreibt `run` Fenstergröße, Oberflächengröße (so groß wie möglich, wie unter Android) und Sprache; VCMIs
  randloses Vollbild geht mit dem `sdl2-compat` des Geräts nicht (Bildgröße 0). Der Controller spielt mit VCMIs eigener
  Belegung (`config/keyBindingsConfig.json`, dieselbe wie unter Android): linker Stick Zeiger, rechter Stick Karte, X/Y
  Maustasten, A OK, B Abbrechen, L1/R1 nächster Held/Stadt, L2 erneut besuchen, R2 Zauberbuch, Select Zug beenden, Start
  Optionen. Das Deck fordert Grafik und Schriften als Binärblöcke an (`art <schlüssel>` → `#art:<schlüssel>`), die das
  Spiel zur Laufzeit aus den Spieldaten liest; die Minikarte kommt als Block `#json`.
- **KKnD 2: Krossfire:** `SRC=<Checkout von KKND2 Thor, Zweig tandem-linux> ports/kknd2/build.sh` (OpenRA mit dem Mod
  OpenKrush, wie die Android-Version; `thor/linux` im Checkout ist der Start unter Linux mit dem Deck-Socket in C#,
  `TandemDeck.cs`). Veröffentlicht für .NET 6 mit Laufzeit (das Gerät hat kein `dotnet`), Engine- und Mod-Dateien in
  `dist/game/`, Lua 5.1 in `dist/lib/` (das Gerät hat nur LuaJIT); SDL2, OpenAL und FreeType sind die des Geräts. Die
  Spieldaten sind der Ordner `Content` mit `openkrush_gen2/` (levels, music, fmv), so wie die Android-Version ihn aus
  der eigenen CD macht. `run` nimmt `$KKND2_DATA`, `~/KKND2/Content` oder einen solchen Ordner auf einer Karte; gelesen
  wird nur (`tandem-ports/kknd2/data/support/Content` ist ein Verweis). Einstellungen, Protokolle, Spielstände und die
  aus den Mehrspieler-Levels gemachten Karten liegen in `tandem-ports/kknd2/data/support/`; `launch-args.txt` dort
  (optional) setzt weitere OpenRA-Einstellungen. Gespielt werden Gefechte (wie unter Android). Der Controller spielt wie
  unter Android (`thor/android/ThorInput.cs`): linker Stick Zeiger, rechter Stick Karte, A/B Maustasten, X Stopp,
  Y Angriff, L3 Aufbauen, Steuerkreuz Gruppen 1–4, Select Menü, Start Enter, L2/R2 Seiten des Decks, L1/R1 Ring über
  die Karten des Decks (A baut die markierte). Das Deck fordert die Knöpfe und die Schrift der eigenen Fraktion
  (`art <fraktion>`), die Minikarte des Levels (`minimap`) und Bau-Icons (`icon <actor>`) als Binärblöcke an.
- **Diablo II + Lord of Destruction 1.13d:** `SRC=<Checkout von Thor D2, Zweig tandem-linux> APK=<ThorD2-0.1.7.apk>
  ports/d2/build.sh` (MinGW reicht, kein Docker). Das ist kein nativer Build: Thor D2 (Fork von D2Android) läuft als
  Windows-Spiel unter dem Proton (ARM64, mit FEX) der Steam-Installation, das `run` selbst sucht; ohne ein solches Proton
  startet nichts. Mod, Lader, D2DX und PlugY kommen unverändert aus der APK, `d2install.exe` aus dem Zweig. Spiel,
  Wine-Präfix und Spielstände liegen in `tandem-ports/d2/data/` (`game/`, `prefix/`, `save/`).
  Ist das Spiel nicht installiert, installiert `dist/setup.py` es wie die Android-App „ohne PC“: Blizzards Downloader
  (`downloader.battle.net`) laden die offiziellen 1.14b-Installer, deren Dateien werden gegen festgeschriebene SHA-256
  geprüft, die zwei Installer laufen mit den CD-Keys, `LODPatch_113d.exe` (SHA-256 festgeschrieben) patcht auf 1.13d, dann
  folgt die Prüfung gegen die 1.13d-Liste. Alles Windows läuft unsichtbar in einem eigenen kopflosen gamescope; den
  Fortschritt zeigt das Deck (aus `data/setup.json`, Protokoll `data/setup.log`). Sprache: `data/language` (`deDE`
  Vorgabe, oder `enUS`). Die **CD-Keys** kommen als Datei `$XDG_RUNTIME_DIR/d2-keys` (zwei Zeilen: Diablo II, dann Lord of
  Destruction; Bindestriche egal), z. B. per `ssh … 'umask 077; cat > "$XDG_RUNTIME_DIR/d2-keys"'`. `setup.py` liest die
  Datei sofort und löscht sie; die Keys gehen nur über ein FIFO (0600, gleich wieder weg) an `d2install.exe`, das sie dem
  Installer in den Speicher schreibt – in keiner Datei, keinem Protokoll, keiner Prozessliste. Ohne Datei lädt `setup.py`
  die Installer und wartet dann. Ein Fehler beim Installieren bricht ab und räumt `game/` weg; geprüfte Installer bleiben für den
  nächsten Versuch. Sind beide Installer durch (`game/.patch-pending`), braucht es keine Keys mehr: ein Fehler beim Patch
  lässt `game/` stehen, und der nächste Start wiederholt nur den Patch (die Dateien, die er ändern kann, liegen vorher in
  `game/.before-patch`). Wie unter Android ersetzt ein Platzhalter (Version 1.0.12) die 1.14b-`Game.exe`, die der Patch
  sonst als neuer ablehnt; das Ende erkennt `setup.py` an `bnupdate.log` (`RESULT:`) oder der 1.13d-`Game.exe`. `data/`
  ist im Präfix Laufwerk `P:` – auf `Z:` (das schreibgeschützte Systemwurzel) sieht Wine 0 Byte frei, und BNUpdate bliebe
  im Dialog „nicht genug Speicherplatz“ stehen. `winedevice.exe` überlebt unter diesem Proton `wineserver -k`; `setup.py`
  ist deshalb Subreaper und beendet übrig gebliebene Wine-Prozesse unter sich per PID (auch nach dem Spiel, `--play`). Damit 1.13d
  unter diesem Proton startet: Windows-Version `win7` nur für `Game.exe` (`run`, `data/d2.reg`; ab Windows 8, Wines Vorgabe,
  haben kritische Abschnitte keine Debug-Info, die Fog.dll prüft – sonst „Unrecoverable internal error“ und Stapelüberlauf;
  D2DX will mindestens Windows 7) und wie in der Android-App das `(attributes)` in `d2data/d2char/d2sfx.mpq` ausgeblendet
  (sonst „The file data is corrupt“). Beenden über Tandem speichert erst (PlugY-Speichern über den Mod, wie die Android-App)
  und beendet dann Wine; `--play` läuft dafür in eigener Sitzung. `data/fps` (leere Datei) zeigt die Bildrate (DXVK-HUD). Nach Erfolg werden die Installer gelöscht und Spielstände aus `data/saves-import/` (falls dort abgelegt) nach
  `save/` kopiert, ohne etwas zu überschreiben. Die **Steuerung** ist die von Thor D2: `dist/pad.py` (von `run` gestartet)
  liest das Pad von InputPlumber („Microsoft X-Box 360 pad“) und spielt wie `D2GamepadInput`/`D2TouchOverlay` der
  Android-App über den Mod – linker Stick läuft (Mod-Befehl Gehen), A greift das von der Zielhilfe gewählte Monster an
  oder nimmt/spricht in der Nähe, B nimmt (in Fenstern: zurück), X/Y/R3 F1–F3, mit gehaltenem RB X/Y/R3/A/B F5/F6/F4/F7/F8,
  LB Waffenwechsel, LT Heil-/RT Manatrank (RB+LT Verjüngung, RB+RT Gegenstandsnamen), Steuerkreuz oben Karte, unten
  Stadtportal, links/rechts Gürtel 3/4 (mit RB Gürtel 4/3/1/2 an den Söldner), Start Spielmenü (halten: Tandems Pause),
  View Inventar (halten: Fensterrad, gezeigt auf dem Deck), L3 Laufen/Gehen, R3 halten bei offenem Inventar sortiert;
  in Fenstern bewegt der Stick den Zeiger, A/X klicken links/rechts; automatische Tränke bei 40 % Leben / 20 % Mana /
  20 % Verjüngung wie die Android-Vorgaben. Tasten und Maus gehen per XTest an das Spiel. Der Mod sendet dazu an
  127.0.0.1:7957 (`D2MOD_APP_PORT`), `pad.py` reicht jedes Paket an das Deck auf 7958 weiter; `data/pad-trace` (leere
  Datei) protokolliert nach `data/pad.log`. Das **Deck** (`ui/decks/d2.py`, Spielgrafik über `ui/decks/d2art.py` zur
  Laufzeit aus den eigenen MPQs, Zwischenspeicher `~/.cache/tandem/d2`) ist das Deck von Thor D2: Charakter, Orbs,
  Widerstände, Attribute (+), Fertigkeiten, Effekte, Tabs Inventar/Fertigkeiten/Truhe/Würfel/Söldner/Quests,
  Wegpunkte, Gegenstände per Tippen/Ziehen, Inventar sortieren, Portal, Trank; Befehle an den Mod auf 7959.

### Deck-Socket

So spricht ein nativer Port mit seinem Deck auf dem unteren Bildschirm. Das Spiel ist der Server.

- **Ort:** ein Unix-Socket, dessen Pfad das Spiel in `TANDEM_DECK_SOCKET` bekommt (`$XDG_RUNTIME_DIR/tandem-deck.sock`).
  Fehlt die Variable, öffnet das Spiel nichts. Es läuft immer nur ein Spiel, also gibt es nur diesen einen Socket.
- **Spiel → Deck:** Zeilen, jede ein JSON-Objekt, mit `\n` beendet. Die erste Zeile ist der Inhalt von
  `TANDEM_DECK_HELLO`, falls `run` das gesetzt hat (bei Half-Life: `{"game":…,"data":…,"home":…}`, also Spielordner,
  Spieldaten und Spielstände). Danach kommt der Zustand des Spiels, höchstens zwanzigmal je Sekunde und nur, wenn er
  sich geändert hat. Jede Zustandszeile ist vollständig; das Deck braucht keine frühere Zeile.
- **Deck → Spiel:** Zeilen mit je einem Befehl als Text (`thor_select 3`). Das Spiel prüft jeden Befehl gegen seine
  eigene Liste und führt ihn auf seinem Spiel-Thread aus; Unbekanntes wird verworfen. Antworten gibt es nicht: die
  Wirkung steht im nächsten Zustand.
- **Binärblöcke (Spiel → Deck):** für alles, was kein Text ist (Karte, Radar, Icons). Eine Zeile `#<name> <länge>\n`,
  gefolgt von genau so vielen rohen Bytes; danach geht es mit Zeilen weiter. Der Name hat keine Leerzeichen; was die
  Bytes bedeuten, machen Spiel und Deck unter sich aus. Blöcke gehören nicht zum Zustand und werden nie von selbst
  wiederholt: Das Deck fordert sie mit einem Befehl an (so braucht ein neu verbundenes Deck nichts Besonderes) und
  merkt sie sich. Das Spiel schickt sie mit `TandemDeck_Block(name, daten, länge)` aus dem Zustands- oder dem
  Befehls-Callback heraus (nur dort: beide laufen auf dem Thread des Sockets, zwischen zwei Zeilen). Ein Deck ohne
  Block-Empfänger überspringt Blöcke.
- **Muster Age of Kings** (`ports/aok/deck_socket.inc`, `ui/decks/aok.py`): Der Zustand nennt für die Karte nur
  Seriennummer und Größe und für jeden Knopf nur die Nummer seines Icons. Ändert sich die Seriennummer, schickt das
  Deck `map` und bekommt den Block `map` (Breite × Höhe × 4 Bytes: Blau, Grün, Rot, Alpha – in Qt
  `QImage.Format_ARGB32`). Für ein Icon, das es noch nicht hat, schickt es `icon <slp> <bild>` und bekommt
  `icon:<slp>:<bild>`: Breite und Höhe (je 2 Bytes, niederwertiges zuerst), dann die Pixel wie bei der Karte; ein
  leerer Block heißt „gibt es nicht“. So reichen ein Radar und Cameos für andere Spiele ohne weitere Änderung am
  Protokoll: eigener Blockname, eigener Anforderungsbefehl.
- **Einbauen:** im Spiel `ports/tandem_deck.h` einbinden und einmal
  `TandemDeck_Start(zustand_schreiben, befehl_annehmen)` aufrufen. Im Deck
  `Link(pfad, gehört, block)` aus `ui/decks/portsocket.py` (`block(name, bytes)` ist freiwillig); den Pfad nennt
  `RUN['port']['socket']`.

## Battle.net (Steam-fremde Verknüpfung)

Steam-fremde Verknüpfungen aus Steams `shortcuts.vdf` (außer Tandem selbst) stehen im Steam-Reiter und starten über
`steam://rungameid/<Spiel-ID>`; Start, Pause und Beenden laufen wie bei Steam-Spielen (Prozesse unter
`reaper … AppId=<appid>`). Solange so ein Launcher läuft, zeigt der untere Bildschirm die Bildschirmtastatur des
Terminals (uinput, Layout umschaltbar) – zum Anmelden ohne echte Tastatur; geklickt wird per Touch oben.

Einrichtung (Steam beendet): Kompatibilitätswerkzeug **GE-Proton11-7-Bnet1 (ARM64)** aus
github.com/mrdidit/bnet-arm (Release BNet1, Prüfsumme prüfen, nach `~/.local/share/Steam/compatibilitytools.d/`
entpacken), Blizzards `Battle.net-Setup.exe` von downloader.battle.net, dann
`python3 battlenet.py add <Battle.net-Setup.exe>` (Verknüpfung + Werkzeug-Zuordnung in `config.vdf`, Sicherungen), einmal
aus Tandem starten und installieren, danach `python3 battlenet.py launcher` (startet ab dann den Launcher, Laufwerk
`D:` = `/run/media/armada/THOR/Battle.net` für Spiele: auf `Z:` sieht Wine 0 Byte frei). Startoptionen: Armadas
`armada-game-launch` plus `VKD3D_CONFIG=no_upload_hvv,nodxr MESA_SHADER_CACHE_MAX_SIZE=4096MB` (für Diablo II:
Resurrected, nach dem Android-Port auf dem Thor).

Gemessen am Thor (16.11.2026):
- **Flackern:** Ohne eigenen Desktop zeigt gamescope abwechselnd das kleine Login-Fenster und ein bildschirmgroßes
  Hilfsfenster des Launchers (Bilder schwarz/weiß im Wechsel, Fokus springt auch zu Tandem). Abhilfe: Battle.net läuft
  in einem Wine-Desktop (`explorer.exe /desktop=Battle.net,1920x1080 "…\Battle.net Launcher.exe"`, schwarzer
  Hintergrund) – ein Fenster, Fokus bleibt, aufeinanderfolgende Bilder gleich. Dazu „Browser-Hardwarebeschleunigung“ aus
  (`Battle.net.config`: `Client.HardwareAcceleration = "false"`, WineHQ 50637).
- **Werkzeug schreibgeschützt:** Steam fragt bei jedem Start mit dem Werkzeug des Spiels den Grafiktreiber im
  gemeinsamen Präfix `compatdata/0` ab; wechselt das Werkzeug dort (z. B. Proton CachyOS), schreibt Wines Präfix-Update
  über die DLL-Verknüpfungen in das Werkzeug selbst. Am 16.11. hat das 1205 Dateien des BNet-Werkzeugs überschrieben
  (danach hing jedes `wineboot` mit `win32u.NtUserInitAnsiOem` fehlt). Abhilfe: Werkzeug neu entpacken, Prüfsummen
  prüfen (`sha256sum -c bnet/SHA256SUMS`), dann `chmod -R a-w files`.

## YouTube und Plex (Medien-Apps)

Oben läuft das Video im Vollbild (mpv), unten die Bedienung im Stil einer TV-App: große Vorschaubilder, „Läuft“ mit
Spulleiste, ±10/30 s, Untertitel, Tonspur und Lautstärke, eine Warteschlange und ein Mini-Player unter jeder Seite.
Bedienbar per Touch und per Controller (solange eine Medien-App läuft, gibt der Dienst die Navigation ans Deck):
Steuerkreuz wählt, A öffnet/spielt, B zurück, X Pause, Y in die Warteschlange, L/R wechseln die Reiter; in „Läuft“
spult links/rechts, oben/unten ändert die Lautstärke, Y schaltet die Untertitel durch.

- **Einrichten:** `flatpak install --user flathub io.mpv.Mpv` (aarch64 auf Flathub). Danach stehen YouTube und Plex
  unter Apps (`MEDIA_APPS` in `tandem.py`). mpv hört auf `/tmp/tandem-mpv-<uid>.sock` (sein Sandkasten sieht das
  `/tmp` des Systems) und wird mit `--really-quiet` gestartet, damit keine Adressen in `launch.log` landen.
- **Aufbau:** `ui/decks/media.py` (gemeinsame Oberfläche), `ui/decks/mpv.py` (JSON-IPC), `ui/decks/youtube.py` und
  `ui/decks/plex.py` (die Quellen, reines Python). Test: `python3 ui/test_media.py` (Plex und mpv als Attrappen).
- **YouTube:** Suche, Kanalseiten und Stream-Adressen über yt-dlp (lädt das Deck selbst nach
  `~/.local/share/tandem-media/yt-dlp` und hält es alle zwei Tage aktuell), ohne Google-Konto. Gemerkte Kanäle,
  Verlauf mit Position („Weiterschauen“) und letzte Suchen in `~/.config/tandem/media/youtube.json`. Bild: H.264 bis
  1080p, weil der Thor das in Hardware dekodiert (`--hwdec=v4l2m2m-copy`: ~5 % eines Kerns statt ~30 % in Software).
- **YouTube-Konto am Thor (19.11.):** Abos/Playlists/„Mag ich“ → „Anmelden“: oben Googles Seite in Firefox (eigenes
  Profil `~/.config/tandem/media/yt-browser`, 0700), unten die Bildschirmtastatur, „Fertig“ schließt Firefox
  (`/api/ytlogin` start/done/logout). yt-dlp liest die Feeds mit `--cookies-from-browser firefox:<Profil>`; Abspielen
  bleibt ohne Konto. „Abmelden“ (letzter Eintrag in den Konto-Tabs) löscht das Profil. Der alte OAuth-Weg greift nur,
  wenn in den Einstellungen ein Client eingetragen ist. Abspielen: mpv holt YouTube selbst (`--ytdl=yes`), weil
  YouTube die von yt-dlp ausgegebenen Adressen mit 403 ablehnt; `flatpak update io.mpv.Mpv` läuft alle zwei Tage mit.
- **Plex:** Anmeldung über plex.tv/link (das Deck zeigt einen Code, den man mit seinem Plex-Konto eingibt). Server
  und Adresse kommen aus dem Konto (lokale Verbindungen zuerst). Token und Server stehen in
  `~/.config/tandem/media/plex.json` (Rechte 0600); der Token geht nur als Kopfzeile `X-Plex-Token` raus, nie in
  einer Adresse. Gespielt wird die Datei direkt (Direct Play), der Stand geht alle 10 s und bei Pause/Stopp per
  `/:/timeline` an den Server, damit „Weiterschauen“ überall stimmt. Neu anmelden: `plex.json` löschen.

## Spielspeicher lesen über RetroArch (gemessen am Thor, 15.11.2026)

RetroArch 1.22.2 (Flatpak) nimmt Netzwerkbefehle auf
UDP 127.0.0.1:55355 an; eine Antwort kommt mit dem nächsten Bild, also nach rund 21 ms (höchstens etwa 45 Abfragen je Sekunde).

| Kern | `GET_STATUS` | `READ_CORE_MEMORY <adresse> <länge>` | `READ_CORE_RAM <offset> <länge>` |
|---|---|---|---|
| mGBA (GBA) | System, Titel, `crc32=` | Bus-Adressen: EWRAM `2000000`, IWRAM `3000000`, I/O `4000000`, Palette `5000000`, VRAM `6000000`, ROM `8000000`; bis 16384 Bytes je Abfrage | Offset 0 = IWRAM |
| Gambatte (GB/GBC) | ja | Feste Zuordnung in Stücken: ROM `0000`/`4000`, VRAM `8000`, WRAM `c000` und `d000` (immer Bank 1), OAM `fe00`, I/O `ff00`, HRAM `ff80`, GBC-Bänke 2–7 ab `10000`; eine Antwort endet am Stückende; Modul-RAM `a000` und Echo `e000` ohne Zuordnung (bei Super Mario Land); bis 4096 Bytes | Adressraum der RetroAchievements |
| Snes9x (SNES) | ja | „no memory map defined“ | Offset ins Arbeits-RAM (`9c2` = `7E09C2`) |

Nur gelesen, nie geschrieben (`WRITE_CORE_MEMORY` bleibt tabu: RetroAchievements, Spielstände). Tastatur und virtueller
Controller: ein nachträglich angelegtes Pad sieht RetroArch im Flatpak nicht; Tasten (X = A, Z = B, Enter = Start, Pfeile)
kommen an. Lua: auf dem Gerät gibt es `luajit` (5.1) und `liblua-5.4.so`, aber kein `lua`-5.4-Programm; die vorhandenen
Begleiter-Pakete nutzen `&`, `>>` und `//`, brauchen also Lua 5.3+.

## Stand 15.11.2026

Geprüft auf dem AYN Thor (ArmadaOS 20261109, intern installiert, eigene Sitzung ohne Steam):
- Beide Bildschirme: oben Großansicht, unten Raster; 396 Spiele von der Spielekarte, 393 mit Cover aus der Cocoon-Bibliothek.
- Steuerung per Controller (virtueller Xbox-Pad über uinput) und per API; Spielstart, Rückkehr und Spielzeit.
- Je ein Spiel gestartet und im Bild geprüft: GB, GBC, GBA, NES, SNES, N64, Mega Drive, PlayStation, PS2, PSP, GameCube,
  Wii, Wii U, 3DS, Dreamcast.
- 3DS: Azahar übernimmt während des Spiels den unteren Bildschirm selbst (DRM-Lease) und gibt ihn danach zurück.
- Unten im Spiel: Helligkeit oben/unten, Lautstärke, bei RetroArch Speichern/Laden/Slot/Vorspulen/Pause/Menü/Foto.
- RetroAchievements: Fortschritt und Liste zum laufenden Spiel (Titelabgleich); Cover-Abruf für Spiele ohne Bild.
- Wii U auf beiden Bildschirmen: Cemus GamePad-Fenster wird auf den unteren Bildschirm gespiegelt (nur Bild, kein Touch);
  Home pausiert und bringt Tandem zurück, Fortsetzen stellt beide Bilder wieder her (Mario Kart 8).
- Switch (Eden, eigener Updater unter Apps): ein Spiel im Bild geprüft; Profil, Spielstände, Updates und Firmware aus der Sicherung liegen in `~/.local/share/eden/nand`.
- Einrichtung vom Handy oder Computer: `http://armada.local:8378` (der Gerätename; ersatzweise `http://<IP>:8378`, beides
  steht auf dem Thor unter Einstellungen › WLAN & Netzwerk), einmal die PIN vom Thor, dann Bild/Ton, RetroAchievements, WLAN, Tastatur, Bibliothek und
  Gerät. Der Browser bleibt ein Jahr angemeldet, auch über Neustarts; auf der Seite: „Dieses Gerät abmelden“, „Alle Geräte abmelden“.
- Einrichtungsassistent `python3 setup.py` (mit `--ja` ohne Rückfragen): Tandem, eigene Sitzung, Spielekarte, Emulatoren, RetroArch.
- Steuerung und Aufnahme vom Mac: `./thor shot|key|pad|rec start <name>|rec stop|sh` (Aufnahme: je Bildschirm ein Abschnitt pro Fenster).
- Rückfragen (Spiel beenden) stehen auf beiden Bildschirmen; ein Spiel, das einen Sitzungs-Neustart überlebt, wird beim nächsten Start beendet.

- Native Oberfläche statt Firefox (15.11.): beide Fenster zusammen rund 110–140 MB statt 1,4 GB (PSS gemessen). Der Dienst
  liest den Controller und schickt die Tasten als Ereignisse; beide Fenster laufen über X11 (auf den Wayland-Sockeln der
  beiden gamescope erscheint ein Qt-Fenster nicht). Im Bild geprüft: Start, Systeme, Spieleliste mit Rollen, Steam, Apps,
  System, Spielstart/Pause/Rückfrage/Beenden (Game Boy), Terminal-Tastatur, Lautstärke-Anzeige.
- Native Ports (16.11.2026): Half-Life, Opposing Force und Blue Shift aus Tandem gestartet, je ein neues Spiel und eine
  Karte im Bild geprüft (115–119 Bilder/s bei 1080p, Xash3D braucht 30–50 % eines Kerns). Das HEV-Deck zeigt Gesundheit,
  Panzerung, Waffen, Munition und Ort; Waffe wählen, Lampe, Schnellspeichern, Spielstände, Menü und Beenden wirken per
  Tippen (XTest) im Spiel.
- Command & Conquer und Red Alert (16.11.2026): beide aus Tandem gestartet, je ein Gefecht (Tiberian Dawn zusätzlich die
  erste GDI-Mission) im Bild geprüft: 60 Bilder/s, 7–12 % eines Kerns, 120–165 MB. Das Deck zeigt Geld, Strom, Radar,
  Cameos und die Seitenleisten-Grafik aus den Spieldaten; per Tippen (XTest) wirken Bauen, Anhalten, Platzieren (Klick
  oben), Radar antippen, Karten-Zoom, Verkaufsmodus, Optionen, Basis/Einheiten-Sprung, Tempo, Gruppe speichern (Red
  Alert), Schnellspeichern (Tiberian Dawn) und Beenden.
- Heroes of Might and Magic III (16.11.2026): aus Tandem gestartet, die HD-Edition-Daten wurden beim ersten Start
  umgewandelt (7 Kampagnen), ein Szenario („Alle für einen“) im Bild geprüft: 119 Bilder/s bei 1080p, 36 % eines Kerns,
  460–490 MB. Das Deck zeigt Rohstoffe, Datum, Minikarte, Helden, Städte, Armee und Heldenwerte mit der Grafik und den
  Schriften des Spiels; per Tippen (XTest) wirken Zug beenden (mit Rückfrage über „OK / Annehmen“), Stadt wählen, Held
  öffnen, Minikarte antippen, Fenster schließen, die Reiter und Beenden.
- KKnD 2: Krossfire (16.11.2026): aus Tandem gestartet, Vorspann, Hauptmenü und ein Gefecht (Survivors, Karte
  „KKND2 Multiplayer 01“) im Bild geprüft: 119 Bilder/s bei 1080p (das Spielbild füllt den oberen Bildschirm), 47 %
  eines Kerns bei 1,5-fachem Tempo, rund 680 MB; das Deck braucht 3 %. Das Deck zeigt Fraktion, Spielzeit, Tempo,
  Öl und Ölwirtschaft, Minikarte mit Einheiten und Ausschnitt, Auswahl, Bau-Karten mit Icons und Kosten, Gruppen und
  die Befehle in Knöpfen und Schrift der Fraktion; per Tippen (XTest) wirken Aufbauen (Außenposten), Gebäude wählen und
  oben platzieren, Minikarte antippen, Tempo, Menü (öffnet das Optionsmenü des Spiels) und Beenden (mit Rückfrage).
  Beenden über Tandem (SIGTERM) dauert 0,3 s.

Noch nicht geprüft:
- KKnD 2: der eingebaute Controller von Hand (er wird erkannt), Touch auf dem oberen Bildschirm, Forschung, Gruppe
  speichern mit echten Einheiten, ein ganzes Gefecht bis Sieg/Niederlage, Speichern und Laden, Ton.
- Heroes III: ein echter Kampf (die Kampfseite des Decks läuft nur im Selbsttest), Stadtseite, Abenteuerzauber, Armee
  umstellen am Gerät, der eingebaute Controller von Hand, Ton (ein Tonstrom ist offen, gehört wurde nichts), Videos,
  Kampagnen, Speichern und Laden.
- Command & Conquer / Red Alert: der eingebaute Controller von Hand (auch L1/R1-Ring, A, L3/R3), Touch auf dem oberen
  Bildschirm, Ton, Filme, Kampagne über die erste Mission hinaus, Spielstände laden, Mehrspieler.
- Half-Life-Ports: der eingebaute Controller im Spiel von Hand (das Spiel öffnet das Pad, die Belegung `thor` ist
  ungeprüft), echte Finger auf dem Deck, Ton, längeres Spielen und Kartenwechsel.
- Native Oberfläche: Tippen auf dem echten unteren Touchscreen (Antippen, Regler, Texteingabe und WLAN-Liste laufen nur
  im Selbsttest `ui/test_ui.py`), Erfolgsliste mit echten Einträgen, Steam-Kachel während eines Downloads.
- Touch auf dem unteren Bildschirm (nur per API und Controller bedient), echter eingebauter Controller.
- DS (keine Spiele auf der Karte), Switch-Spielstände im Spiel selbst, Steam-Spiele (Konto ist angemeldet, es ist aber noch kein Spiel installiert).
- Lautstärke-Anzeige über dem laufenden Spiel oben: ein Overlay-Fenster (GAMESCOPE_EXTERNAL_OVERLAY) erschien im Test nicht; die Anzeige steht unten.
- Aufwachen per Ein/Aus-Taste (Standby selbst und Aufwachen per Zeitschaltung sind geprüft: beide Bildschirme und Tandem kommen zurück).

Bekannte Grenzen:
- `steamos-add-to-steam` fehlt in ArmadaOS: `python3 addshortcut.py` trägt Tandem ein (Steam darf dabei nicht laufen), sonst von Hand als Steam-fremdes Spiel.
- Der Start von einer USB-SSD scheitert an einem bekannten ArmadaOS-Fehler (#606); es geht nur über eine microSD.
- Startet ArmadaOS von der SD-Karte, ist der Kartenplatz belegt – die Spielekarte ist dann nicht erreichbar (ROMs nach `~/ROMs`
  kopieren oder ArmadaOS intern installieren).
- Für Switch gibt es im Armada Store keinen Emulator: Eden kommt über Tandems eigenen Updater.
- Ohne Steam fehlen dessen Schnellmenü und Systemupdates: Helligkeit und Lautstärke hat Tandem selbst, Updates laufen über eine Steam-Sitzung.
- ArmadaOS hängt exFAT-Karten nicht von selbst ein: Eintrag in `/etc/fstab` nötig (über `setup.py` einrichtbar).
- Firefox stürzt im unteren Bildschirm über Wayland ab, deshalb startet das untere Fenster über X11 (gilt für den Rückweg).
- Ist der untere Bildschirm aus, zeigt Firefox beide Ansichten oben; die native Oberfläche hat keine gemeinsame Ansicht.
- Standby, Neustart, Ausschalten und Desktop fragen in der nativen Oberfläche auf beiden Bildschirmen nach; in der
  Firefox-Seite wirken sie sofort.
