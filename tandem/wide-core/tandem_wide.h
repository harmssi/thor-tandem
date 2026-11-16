// Wide view in the libretro core: the margins beside a GBA game's 240x160 (GB/GBC: 160x144) frame, painted from what the
// companion pack's game.lua describes (gbaduo/wide.h). Tandem leaves the script and an on/off switch in
// <system directory>/tandem-wide/ before it starts the game.

#ifndef TANDEM_WIDE_H
#define TANDEM_WIDE_H

#include <mgba/core/core.h>

#define TANDEM_WIDE_W 284    /* 16:9 at the GBA's 160 lines */
#define TANDEM_WIDE_GB_W 256 /* 16:9 at the Game Boy's 144 lines */

/** After the ROM is loaded: look for <systemDir>/tandem-wide/game.lua and the switch. */
void tandemWideLoad(struct mCore* core, const char* systemDir);
void tandemWideUnload(void);

/** The width the frontend gets for a picture [width] wide: TANDEM_WIDE_W while wide view is on. */
unsigned tandemWideWidth(unsigned width);

/**
 * After each emulated frame. [raw] is the core's own picture ([stride] pixels a row; NULL when the frame was
 * skipped), [shown] the same after post-processing. Returns the picture to show and updates [width] and [pitch].
 */
const mColor* tandemWideFrame(const mColor* raw, const mColor* shown, size_t stride, unsigned* width, unsigned height, size_t* pitch);

#endif
