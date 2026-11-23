# Toravo Tandem OS (ArmadaOS + Toravo Tandem Flash-Image)

Fertiges, bootfähiges **AYN Thor**-Systemabbild auf Basis von **ArmadaOS** (`ghcr.io/armada-os/armada:beta`) mit vorinstalliertem **Toravo Tandem** — kein Terminal, kein manuelles `curl`, kein Gefummel.

> **Warum `.img.xz` statt `.iso`?**
> Der AYN Thor startet über **OpenABL (ARM64 UEFI)** direkt von GPT-Disk-Images auf SD-Karte oder USB-Stick/SSD (nicht von x86-CD-ISOs). Jedes Standard-Tool (**Balena Etcher**, **Raspberry Pi Imager**, **Rufus**) schreibt `.img.xz` direkt ohne Entpacken.

## Installation in 3 Schritten
1. **`toravo-tandem-os-<version>-arm64.img.xz`** herunterladen.
2. Mit **Balena Etcher**, **Raspberry Pi Imager** oder **Rufus** (oder `sudo ./os/flash-thor.sh …`) auf eine SD-Karte oder einen USB-Stick (ab 16 GB) schreiben.
3. In den AYN Thor stecken und über **OpenABL** starten:
   - Beim ersten Start richtet `toravo-tandem-firstboot` automatisch **Toravo Tandem** als Dual-Screen-Oberfläche ein.
   - Der eingebaute **Toravo-Assistent** führt durch WLAN, Tastatur & Spielordner.
   - Über **Einstellungen › System & interner Speicher** (oder den Armada-Installer) lässt sich das System bei Bedarf auf den internen UFS-Speicher übertragen und Android auf bis zu `8 GiB` verkleinern.
   - **Updates bleiben erhalten:** ArmadaOS-Systemupdates laufen normal weiter (`bootc upgrade`), und Tandem, Emulatoren & Begleiter aktualisieren sich automatisch über den integrierten Update-Dienst.

## Selbst bauen (auf ARM64 Linux mit Docker, z. B. DGX Spark)
```bash
./os/build-image.sh            # baut bootc OCI-Image + dist/toravo-tandem-os-<ver>-arm64.img.xz
./os/build-image.sh --oci-only # baut nur das bootc OCI-Image
```
