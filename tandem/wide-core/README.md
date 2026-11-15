# mgba_wide_libretro: mGBA mit Breitbild für Begleiter-Pakete

Ein libretro-Kern für RetroArch: der mGBA-Kern von libretro (derselbe Quellstand wie der Kern aus RetroArchs
Online-Updater, daher dieselben Spielstände, Schnellspeicher und Optionen), ergänzt um die „Wide view“ aus
[gba-duo](https://github.com/khumam/gba-duo). Neben dem 240 × 160 großen Bild eines GBA-Spiels zeigt er links und rechts
mehr von der Spielwelt (284 × 160, also 16:9), so wie es das `game.lua` eines Begleiter-Pakets in `wide(view)` beschreibt
(Format: `docs-packs/game-script.md` in gba-duo).

## Was der Kern liest

Im Systemordner von RetroArch (`…/retroarch/system/tandem-wide/`), von Tandem beim Spielstart abgelegt:

| Datei | Inhalt |
|---|---|
| `game.lua` | das Skript des Pakets; `pack.require("name")` lädt `name.lua` aus demselben Ordner |
| `on` | `1` = Breitbild an, sonst aus; wird alle 30 Bilder neu gelesen |

Fehlt `game.lua`, ist das Spiel kein GBA-Spiel oder hat das Skript kein `wide()`, verhält sich der Kern wie der normale.

## Wie es arbeitet

Nach jedem Bild fragt der Kern `wide(view)` (nur lesend, 100 000 Lua-Anweisungen und 2 ms je Aufruf, nach fünf Fehlern in
Folge aus), sagt die 16 Randspalten des Spielbilds voraus und vergleicht sie mit dem, was mGBA gezeichnet hat. Unter 85 %
über vier Bilder bleiben die Ränder schwarz (Kampf, Menü, unbekannte Karte), nach vier guten Bildern kommen sie wieder.
`{ affine = 1 }` setzt die Dreh-/Zoom-Hintergründe (Modus 1 und 2) zeilenweise fort. `frame(view)` läuft, darf aber nie
schreiben. Figuren stehen nicht in den Rändern (sie gehören nicht zur Karte).

Unterschiede zur Android-App: feste Breite 284 statt „bis 400 nach Bildschirm“; der Kern zeichnet in RGB565, die Ränder
werden dafür umgerechnet; Farbkorrektur und Zwischenbild-Mischung des Kerns wirken nur auf das Spielbild, nicht auf die
Ränder; kein Breitbild für GB/GBC; kein Schreiben in den Spielspeicher.

## Bauen

`./build.sh` (braucht Docker auf einem aarch64-Rechner) baut in einem Debian-12-Container und legt
`dist/mgba_wide_libretro.so` ab; `../install.sh` kopiert die Datei als `cores/tandem-wide/mgba_libretro.so` zu den RetroArch-Kernen. Der Name ist
absichtlich der des normalen Kerns: RetroArch sucht die Kern-Beschreibung (`.info`) nach dem Dateinamen, und ohne sie
stürzt RetroArch 1.22.2 beim Netzwerkbefehl `GET_STATUS` ab. Das Skript holt
libretro/mgba (fester Commit) und Lua 5.4.7 (Prüfsumme) und wendet an:

- `mgba-libretro.diff`: die Einhängepunkte in `src/platform/libretro/libretro.c`
- `tandem_wide.c`, `tandem_wide.h`: Speicherzugriff für das Skript, Ränder, Schalter (nach gba-duos `core.c`)
- `gbaduo/`: unverändert aus gba-duo (`app/src/main/cpp`, Commit a5d648d): `wide.c`, `wide_affine.c`, `script.c`
  (Lua-Sandbox), `memwrite.c` und ihre Header
- `lua-pattern-hook.diff`: gba-duos kleine Änderung an Luas `lstrlib.c` (Zeitgrenze auch in Mustern)

## Lizenz

Der gebaute Kern steht als Ganzes unter der GPLv3: gba-duo ist GPLv3 (`gbaduo/LICENSE`), `tandem_wide.c` folgt dessen
`core.c`. mGBA steht unter der MPL 2.0 (verträglich mit der GPLv3), Lua unter der MIT-Lizenz. Wer das Binary weitergibt,
gibt diese Quellen mit.
