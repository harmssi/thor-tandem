# Toravo Tandem

Dual-screen game launcher for ArmadaOS on the AYN Thor: the game on the top screen, controls and per-game companion
screens on the bottom one. A lean native program (Python + Qt), no browser, Steam stays out of sight.

Install on the device (desktop mode › console, or over SSH):

    curl -L https://github.com/harmssi/thor-tandem/releases/latest/download/get.sh | bash

The interface speaks English or German (Settings › Look › Language; the installer follows your system language).

New in 0.3.0:
- Native YouTube and Plex dual-screen apps (`mpv` on top, touch/controller deck below) with QR-code phone sign-in (subscriptions, playlists, liked videos) and Wi-Fi offline downloads onto the SD card.
- Tactile 3D on-screen keyboard with AYN Thor LRA haptic click feedback, floating key magnifier, slide-to-correct, backspace hold-to-repeat, dedicated `@` key and reliable X11 `AltGr` character injection.
- Stage carousel view and Cocoon platform frames alongside the 5-column grid, plus night mode (warm / night blue-light filter).
- Per-game overrides in the quick menu (power mode, FPS cap, scaling filter), volume hold-to-repeat & mute, Captures gallery for screenshots and dual-screen recordings, Bluetooth audio & gamepad pairing, lid-close / charger-aware standby, and rolling SD + optional SSH savegame backups.
- BananaNative integration (smooth Vulkan/Vsync pacing, automatic bottom-screen recovery, save backups).

Earlier in 0.2.0:
- English interface.
- Quick menu on the Thor key, on the bottom screen: brightness of both screens, volume, power mode, stick lights, frame
  generation, recording, screenshot, back to Tandem, quit game.
- Recording of both screens with sound (into Videos/Tandem on the SD card).
- Frame generation switch for Lossless Scaling (needs your own Lossless Scaling copy and the lsfg-vk layer).
- WoW Forever signs in on its own (login kept on the device, like the Android launcher does it) and picks your game account.
- Native port decks for Half-Life, Age of Kings, Red Alert 2, C&C, Heroes III, KKnD 2 and Diablo II.

Everything else (features, setup, companion packs, wide view, themes) is in [tandem/README.md](tandem/README.md) (German).

Bring your own games. No game files, BIOS files or keys are part of this project.
`tandem/wide-core/` is derived from mGBA (MPL 2.0) and GBA Duo (GPLv3); see the README there.
