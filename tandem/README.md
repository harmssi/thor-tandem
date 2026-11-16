# Toravo Tandem

Dual-Screen-Oberfläche für ArmadaOS auf dem AYN Thor: oben das ausgewählte oder laufende Spiel, unten Kacheln zum
Bedienen.

## Was es kann

- Liest ROMs im ES-DE-Aufbau (`ROMs/<system>/…`) aus `~/ROMs` und von eingehängten Karten (`/run/media/…/ROMs`).
- Nimmt Cover und Hintergrundbilder aus `ES-DE/downloaded_media` und `Cocoon/downloaded_media` neben dem ROM-Ordner –
  die Bilder der Cocoon-Bibliothek werden also weiterverwendet.
- Startet den passenden Emulator aus dem Armada Store (RetroArch, DuckStation, ARMSX2, Dolphin, PPSSPP, Azahar, melonDS,
  Flycast, Cemu, Ymir). Fehlt einer, steht oben, was zu installieren ist.
- Zeigt installierte Steam-Spiele und startet sie über Steam.
- Favoriten (Y), zuletzt gespielt und Spielzeit; „Spiel beenden“ auf dem unteren Bildschirm.
- Bedienung: Steuerkreuz/Stick, A starten, B zurück, LB/RB Reiter, Y Favorit; unten auch per Tippen.

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
| `ui/themes/*.json` | Mitgelieferte Themes (Toravo, Studio, OLED, Hell) |
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
`~/.config/tandem/themes/<name>.json` legen – sie erscheinen in der Auswahl (System-Reiter: „Wechseln“ oder A am
Controller; Einstellungsseite: Bild & Ton). Alles ist freiwillig; was fehlt oder falsch ist, behält den Toravo-Wert:

    {
      "name": "Mein Theme",
      "colors": {"bg": "#0a0c13", "panel": "#141824", "raised": "#1e2434", "line": "#2c3449", "text": "#eef0f6",
                 "muted": "#8d94aa", "accent": "#ffb23e", "live": "#39d0b8", "warn": "#ff7a66"},
      "gradient": ["#8a5cf6", "#6f9be0", "#5ab0d0"],   Verlauf für Balken (2–4 Farben), sonst die Akzentfarbe
      "fonts": {"display": ["Barlow Condensed"], "body": ["Barlow", "Noto Sans"]},   Schriftfamilien, erste vorhandene gilt
      "radius": 1.0,          Eckenrundung als Faktor (0 = eckig, bis 3)
      "glow": 1.0,            Leuchten um die Auswahl (0 bis 1)
      "background": "bild.jpg",   Hintergrundbild neben der Datei (kostet Speicher: ein Bild in Bildschirmgröße)
      "gameAccent": true      Akzentfarbe aus dem Cover des gewählten oder laufenden Spiels (false = immer "accent")
    }

Farben nur als `#rrggbb`. Die Spielfarbe wird einmal je Cover aus einer 24-Pixel-Fassung bestimmt, auf lesbaren Kontrast
zum Hintergrund gebracht und in `~/.cache/tandem/accents.json` gemerkt. Eigene Begleiter (FF IX, Pip-Boy) behalten ihr Aussehen.

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
  steht auf dem Thor unter System), einmal die PIN vom Thor, dann Bild/Ton, RetroAchievements, WLAN, Tastatur, Bibliothek und
  Gerät. Der Browser bleibt ein Jahr angemeldet, auch über Neustarts; auf der Seite: „Dieses Gerät abmelden“, „Alle Geräte abmelden“.
- Einrichtungsassistent `python3 setup.py` (mit `--ja` ohne Rückfragen): Tandem, eigene Sitzung, Spielekarte, Emulatoren, RetroArch.
- Steuerung und Aufnahme vom Mac: `./thor shot|key|pad|rec start <name>|rec stop|sh` (Aufnahme: je Bildschirm ein Abschnitt pro Fenster).
- Rückfragen (Spiel beenden) stehen auf beiden Bildschirmen; ein Spiel, das einen Sitzungs-Neustart überlebt, wird beim nächsten Start beendet.

- Native Oberfläche statt Firefox (15.11.): beide Fenster zusammen rund 110–140 MB statt 1,4 GB (PSS gemessen). Der Dienst
  liest den Controller und schickt die Tasten als Ereignisse; beide Fenster laufen über X11 (auf den Wayland-Sockeln der
  beiden gamescope erscheint ein Qt-Fenster nicht). Im Bild geprüft: Start, Systeme, Spieleliste mit Rollen, Steam, Apps,
  System, Spielstart/Pause/Rückfrage/Beenden (Game Boy), Terminal-Tastatur, Lautstärke-Anzeige.

Noch nicht geprüft:
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
- ArmadaOS hängt exFAT-Karten nicht von selbst ein: Eintrag in `/etc/fstab` nötig (siehe HANDOFF-LOG).
- Firefox stürzt im unteren Bildschirm über Wayland ab, deshalb startet das untere Fenster über X11 (gilt für den Rückweg).
- Ist der untere Bildschirm aus, zeigt Firefox beide Ansichten oben; die native Oberfläche hat keine gemeinsame Ansicht.
- Standby, Neustart, Ausschalten und Desktop fragen in der nativen Oberfläche auf beiden Bildschirmen nach; in der
  Firefox-Seite wirken sie sofort.
