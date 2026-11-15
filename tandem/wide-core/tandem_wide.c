// Wide view glue between the libretro core and gba-duo's wide.c / wide_affine.c / script.c.
// The bus backend and the margin painting follow gba-duo's app/src/main/cpp/core.c (GPLv3), without JNI.
//
// The libretro core draws RGB565 while wide.c works in mGBA's 32-bit colours, so the game's frame is
// copied into a 32-bit work buffer for the edge check and the margins are converted back for output.

#include "tandem_wide.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <mgba/internal/gba/gba.h>
#include <mgba/internal/gba/io.h>
#include <mgba/internal/gba/renderers/video-software.h>

#include "bus.h"
#include "script.h"
#include "wide.h"
#include "wide_affine.h"

#define LOGE(...) (fprintf(stderr, "[tandem-wide] " __VA_ARGS__), fputc('\n', stderr))
#define SWITCH_POLL_FRAMES 30

_Static_assert(sizeof(mColor) == 2, "the wide core is built for RGB565 output");

struct TandemWideState {
    struct mCore* core;
    uint32_t* videoBuffer;    /* 32-bit work picture, TANDEM_WIDE_W x 160 */
    unsigned videoWidth;
    unsigned videoHeight;
    unsigned wideLeft;
    unsigned frameW, frameH;
    struct WideGate wideGate;
    float wideMatch;
    bool wideBlank;           /* the margins are already zeroed */
    int wideErrorLogCountdown;
};

static struct TandemWideState g_state;
static uint16_t* g_out;       /* the RGB565 picture handed to the frontend */
static char g_dir[PATH_MAX];
static bool g_pending;        /* game.lua is loaded with the first frame: its top level may read the game's memory */
static bool g_on, g_hasWide, g_hasFrame;
static unsigned g_poll;

/* ---- bus.h backend: script.c's mem.* and wide.c go through these ---------------- */

int gbaduo_bus_platform(void) {
    return g_state.core ? GBADUO_BUS_GBA : GBADUO_BUS_NONE;
}

uint8_t gbaduo_bus_read8(uint32_t address) {
    return g_state.core ? (uint8_t) g_state.core->rawRead8(g_state.core, address, -1) : 0;
}

uint8_t gbaduo_bus_view8(uint32_t address, int bank) {
    return g_state.core ? (uint8_t) g_state.core->rawRead8(g_state.core, address, bank) : 0;
}

uint16_t gbaduo_bus_read16(uint32_t address) {
    return g_state.core ? (uint16_t) g_state.core->rawRead16(g_state.core, address, -1) : 0;
}

uint32_t gbaduo_bus_read32(uint32_t address) {
    return g_state.core ? (uint32_t) g_state.core->rawRead32(g_state.core, address, -1) : 0;
}

/* This core never opens script.c's write window, so nothing gets here; it stays read-only regardless. */
void gbaduo_bus_write8(uint32_t address, uint8_t value) {
    (void) address;
    (void) value;
}

/* ---- wide view: the margins beside the frame, from game.lua's wide() (as core.c) ---------- */

static void blank_wide_margins(void) {
    unsigned right = g_state.videoWidth - g_state.frameW - g_state.wideLeft;
    for (unsigned row = 0; row < g_state.videoHeight; row++) {
        uint32_t* line = g_state.videoBuffer + (size_t) row * g_state.videoWidth;
        memset(line, 0, g_state.wideLeft * sizeof(uint32_t));
        memset(line + g_state.wideLeft + g_state.frameW, 0, right * sizeof(uint32_t));
    }
    g_state.wideBlank = true;
}

/* The affine state of the frame mGBA just drew: its software renderer keeps every line's video
 * registers (cache[y].io) and affine start point (cache[y].scale). NULL when that renderer isn't in use. */
static struct WideAffineFrame g_affine;

static const struct WideAffineFrame* capture_affine(void) {
    struct GBA* gba = g_state.core->board;
    struct GBAVideoSoftwareRenderer* sw = (struct GBAVideoSoftwareRenderer*) gba->video.renderer;
    if (!sw || sw->d.drawScanline == NULL || !sw->d.vram || !sw->d.palette) return NULL;
    for (int y = 0; y < WIDE_FRAME_H; y++) {
        const uint16_t* io = sw->cache[y].io;
        struct WideAffineLine* l = &g_affine.line[y];
        l->dispcnt = io[GBA_REG(DISPCNT)];
        l->bgcnt[0] = io[GBA_REG(BG2CNT)];
        l->bgcnt[1] = io[GBA_REG(BG3CNT)];
        l->pa[0] = (int16_t) io[GBA_REG(BG2PA)];
        l->pc[0] = (int16_t) io[GBA_REG(BG2PC)];
        l->pa[1] = (int16_t) io[GBA_REG(BG3PA)];
        l->pc[1] = (int16_t) io[GBA_REG(BG3PC)];
        l->sx[0] = sw->cache[y].scale[0][0];
        l->sy[0] = sw->cache[y].scale[0][1];
        l->sx[1] = sw->cache[y].scale[1][0];
        l->sy[1] = sw->cache[y].scale[1][1];
        l->winout = io[GBA_REG(WINOUT)];
        l->bldcnt = io[GBA_REG(BLDCNT)];
        l->bldalpha = io[GBA_REG(BLDALPHA)];
        l->bldy = io[GBA_REG(BLDY)];
    }
    g_affine.vram = (const uint8_t*) sw->d.vram;
    g_affine.palette = sw->d.palette;
    return &g_affine;
}

/* After each emulated frame: ask game.lua for the world, check its prediction against the
 * edge columns mGBA just drew, and paint the margins only while it holds up. */
static void paint_wide_margins(void) {
    int width = (int) g_state.videoWidth;
    int left = (int) g_state.wideLeft;
    int right = width - (int) g_state.frameW - left;
    uint32_t* buf = g_state.videoBuffer;

    struct WideWorld world;
    bool have = gbaduo_game_enabled() && gbaduo_game_wide(width, left, g_state.wideMatch, &world);
    if (!have) {
        const char* error = gbaduo_game_last_error();
        if (error[0] && g_state.wideErrorLogCountdown-- <= 0) {
            g_state.wideErrorLogCountdown = 300;
            LOGE("game.lua: %s", error);
        }
        g_state.wideMatch = 0.0f;
    }
    const struct WideAffineFrame* affine = NULL;
    if (have && world.affine) {
        affine = capture_affine();
        have = affine && wide_affine_usable(affine);
        g_state.wideMatch = have ? wide_affine_seam_match(affine, buf, width, left) : 0.0f;
    } else if (have) {
        g_state.wideMatch = wide_seam_match(&world, buf, width, left);
    }

    if (!wide_gate_step(&g_state.wideGate, have, g_state.wideMatch)) {
        if (!g_state.wideBlank) {
            blank_wide_margins();
        }
        return;
    }
    if (affine) {
        wide_affine_paint(affine, buf, width, left, right);
    } else {
        wide_paint(&world, buf, width, left, right);
    }
    g_state.wideBlank = false;
}

/* ---- the switch and the script --------------------------------------------------- */

static void set_wide(bool on) {
    if (on == g_on) return;
    g_on = on;
    memset(&g_state.wideGate, 0, sizeof(g_state.wideGate));
    g_state.wideMatch = 0.0f;
    g_state.wideBlank = false; /* blanked again before the margins are next shown */
}

/* The file "on" holds '1' while the player has wide view switched on. */
static bool read_switch(void) {
    char path[PATH_MAX + 8];
    snprintf(path, sizeof(path), "%s/on", g_dir);
    FILE* f = fopen(path, "rb");
    int c = f ? fgetc(f) : '0';
    if (f) fclose(f);
    return c == '1';
}

static void load_script(void) {
    g_pending = false;
    char path[PATH_MAX + 16];
    snprintf(path, sizeof(path), "%s/game.lua", g_dir);
    FILE* f = fopen(path, "rb");
    char* source = NULL;
    if (f && fseek(f, 0, SEEK_END) == 0) {
        long size = ftell(f);
        rewind(f);
        source = size >= 0 ? calloc(1, (size_t) size + 1) : NULL;
        if (source && fread(source, 1, (size_t) size, f) != (size_t) size) {
            free(source);
            source = NULL;
        }
    }
    if (f) fclose(f);
    bool ok = source && gbaduo_game_load(source, g_dir);
    if (!ok) {
        LOGE("game.lua did not load: %s", source ? gbaduo_game_last_error() : path);
    }
    free(source);
    if (!ok) {
        tandemWideUnload();
        return;
    }
    g_hasWide = gbaduo_game_has("wide");
    g_hasFrame = gbaduo_game_has("frame");
    set_wide(g_on && g_hasWide);
}

void tandemWideLoad(struct mCore* core, const char* systemDir) {
    tandemWideUnload();
    if (!systemDir || core->platform(core) != mPLATFORM_GBA) return;
    snprintf(g_dir, sizeof(g_dir), "%s/tandem-wide", systemDir);
    char path[PATH_MAX + 16];
    snprintf(path, sizeof(path), "%s/game.lua", g_dir);
    FILE* f = fopen(path, "rb");
    if (!f) return; /* no pack with a game.lua: the plain core */
    fclose(f);

    g_state.videoWidth = TANDEM_WIDE_W;
    g_state.videoHeight = g_state.frameH = WIDE_FRAME_H;
    g_state.frameW = WIDE_FRAME_W;
    g_state.wideLeft = (TANDEM_WIDE_W - WIDE_FRAME_W) / 2;
    g_state.videoBuffer = calloc((size_t) TANDEM_WIDE_W * WIDE_FRAME_H, sizeof(uint32_t));
    g_out = calloc((size_t) TANDEM_WIDE_W * WIDE_FRAME_H, sizeof(uint16_t));
    if (!g_state.videoBuffer || !g_out) {
        tandemWideUnload();
        return;
    }
    g_state.core = core;
    g_pending = g_hasWide = true; /* until the script says otherwise, so the first geometry is already wide */
    g_on = read_switch();
}

void tandemWideUnload(void) {
    gbaduo_game_unload();
    free(g_state.videoBuffer);
    free(g_out);
    g_out = NULL;
    memset(&g_state, 0, sizeof(g_state));
    g_pending = g_on = g_hasWide = g_hasFrame = false;
    g_poll = 0;
}

unsigned tandemWideWidth(unsigned width) {
    return g_state.core && g_on && width == WIDE_FRAME_W ? TANDEM_WIDE_W : width;
}

/* RGB565 as this core draws it (mColorFrom555: red in the top bits) to the GBA's BGR555 and back. */
static uint16_t to555(uint16_t c) {
    return (uint16_t) ((c >> 11) | ((c >> 6) & 0x1F) << 5 | (c & 0x1F) << 10);
}

static uint16_t to565(uint32_t c) {
    return (uint16_t) ((c & 0xF8) << 8 | ((c >> 11) & 0x1F) << 6 | ((c >> 19) & 0x1F));
}

const mColor* tandemWideFrame(const mColor* raw, const mColor* shown, size_t stride, unsigned* width, unsigned height, size_t* pitch) {
    if (!g_state.core) return shown;
    if (g_pending) {
        load_script();
        if (!g_state.core) return shown;
    }
    if (g_hasFrame) {
        /* frame() may look, never write: the write window stays shut */
        gbaduo_game_frame((int64_t) g_state.core->frameCounter(g_state.core), (int) tandemWideWidth(*width),
                          g_on ? (int) g_state.wideLeft : 0, false);
    }
    if (++g_poll % SWITCH_POLL_FRAMES == 0) {
        set_wide(g_hasWide && read_switch());
    }
    if (!g_on || *width != WIDE_FRAME_W || height != WIDE_FRAME_H) return shown;

    *width = TANDEM_WIDE_W;
    *pitch = TANDEM_WIDE_W * sizeof(mColor);
    if (!raw) return g_out;

    unsigned left = g_state.wideLeft;
    for (unsigned y = 0; y < WIDE_FRAME_H; y++) {
        const mColor* src = raw + y * stride;
        uint32_t* line = g_state.videoBuffer + (size_t) y * TANDEM_WIDE_W + left;
        for (unsigned x = 0; x < WIDE_FRAME_W; x++) line[x] = wide_color(to555(src[x]));
    }
    paint_wide_margins();
    for (unsigned y = 0; y < WIDE_FRAME_H; y++) {
        const uint32_t* line = g_state.videoBuffer + (size_t) y * TANDEM_WIDE_W;
        uint16_t* out = g_out + (size_t) y * TANDEM_WIDE_W;
        for (unsigned c = 0; c < left; c++) out[c] = to565(line[c]);
        memcpy(out + left, shown + y * stride, WIDE_FRAME_W * sizeof(mColor));
        for (unsigned c = left + WIDE_FRAME_W; c < TANDEM_WIDE_W; c++) out[c] = to565(line[c]);
    }
    return g_out;
}
