#include "wide_affine.h"

#define SEAM_COLUMNS 8
#define BACKDROP 5

/* mGBA's colour arithmetic on its 32-bit colours (0x00BBGGRR), so the margins match its picture exactly */
static uint32_t brighten(uint32_t color, int y) {
    uint32_t c = 0, a;
    a = color & 0xFF;     c |= (a + ((0xFF - a) * y) / 16) & 0xFF;
    a = color & 0xFF00;   c |= (a + ((0xFF00 - a) * y) / 16) & 0xFF00;
    a = color & 0xFF0000; c |= (a + ((0xFF0000 - a) * y) / 16) & 0xFF0000;
    return c;
}

static uint32_t darken(uint32_t color, int y) {
    uint32_t c = 0, a;
    a = color & 0xFF;     c |= (a - (a * y) / 16) & 0xFF;
    a = color & 0xFF00;   c |= (a - (a * y) / 16) & 0xFF00;
    a = color & 0xFF0000; c |= (a - (a * y) / 16) & 0xFF0000;
    return c;
}

static uint32_t mix(int wa, uint32_t ca, int wb, uint32_t cb) {
    uint32_t c = 0, a, b;
    a = ca & 0xFF; b = cb & 0xFF;
    c |= ((a * wa + b * wb) / 16) & 0x1FF;
    if (c & 0x100) c = 0xFF;
    a = ca & 0xFF00; b = cb & 0xFF00;
    c |= ((a * wa + b * wb) / 16) & 0x1FF00;
    if (c & 0x10000) c = (c & 0xFF) | 0xFF00;
    a = ca & 0xFF0000; b = cb & 0xFF0000;
    c |= ((a * wa + b * wb) / 16) & 0x1FF0000;
    if (c & 0x1000000) c = (c & 0xFFFF) | 0xFF0000;
    return c;
}

/* The backgrounds this line shows: DISPCNT's enables, limited by the outside-window enables when a window is on. */
static unsigned shown_bgs(const struct WideAffineLine* l, bool* effects) {
    unsigned bgs = (l->dispcnt >> 8) & 0xF;
    *effects = true;
    if (l->dispcnt & 0xE000) {          /* window 0, 1 or the object window: the margins lie outside them */
        bgs &= l->winout & 0xF;
        *effects = (l->winout & 0x20) != 0;
    }
    return bgs;
}

bool wide_affine_usable(const struct WideAffineFrame* f) {
    if (!f->vram || !f->palette) return false;
    bool any = false;
    for (int y = 0; y < WIDE_FRAME_H; y++) {
        const struct WideAffineLine* l = &f->line[y];
        int mode = l->dispcnt & 7;
        if (mode != 1 && mode != 2) return false;
        if (l->dispcnt & 0x80) return false;          /* forced blank */
        bool effects;
        unsigned bgs = shown_bgs(l, &effects);
        if (mode == 1 && (bgs & 0x3)) return false;   /* text backgrounds can't be continued */
        if (bgs & 0xC) any = true;
    }
    return any;
}

/* The 256-colour palette index of affine background [k] (0 = BG2, 1 = BG3) at screen pixel [x] of line [l]; 0 = transparent. */
static int affine_index(const struct WideAffineFrame* f, const struct WideAffineLine* l, int k, int x) {
    uint16_t cnt = l->bgcnt[k];
    int size = cnt >> 14;
    int32_t sizeAdjusted = 0x8000 << size;
    int32_t px = l->sx[k] + (int32_t) l->pa[k] * x;
    int32_t py = l->sy[k] + (int32_t) l->pc[k] * x;
    if (cnt & 0x2000) {
        px &= sizeAdjusted - 1;
        py &= sizeAdjusted - 1;
    } else if ((px | py) & ~(sizeAdjusted - 1)) {
        return 0;
    }
    uint32_t screenBase = (uint32_t) ((cnt >> 8) & 0x1F) * 0x800u;
    uint32_t charBase = (uint32_t) ((cnt >> 2) & 3) * 0x4000u;
    uint32_t mapAddr = screenBase + (uint32_t) ((px >> 11) + (((py >> 7) & 0x7F0) << size));
    if (mapAddr >= 0x10000u) return 0;
    uint8_t mapData = f->vram[mapAddr];
    uint32_t pixAddr = charBase + ((uint32_t) mapData << 6) + (uint32_t) ((py & 0x700) >> 5) + (uint32_t) ((px & 0x700) >> 8);
    if (pixAddr >= 0x10000u) return 0;
    return f->vram[pixAddr];
}

static uint32_t color_of(const struct WideAffineFrame* f, int index) {
    return wide_color(f->palette[index]);
}

/* The colour of screen pixel [x] (any value, also outside 0..239) of line [y]: the affine backgrounds by
 * priority over the backdrop, then the line's colour effect. */
static uint32_t affine_pixel(const struct WideAffineFrame* f, int y, int x) {
    const struct WideAffineLine* l = &f->line[y];
    bool effects;
    unsigned bgs = shown_bgs(l, &effects);

    /* BG2 and BG3 in drawing order: lower priority number first, BG2 before BG3 on a tie */
    int order[2] = {0, 1};
    if ((l->bgcnt[1] & 3) < (l->bgcnt[0] & 3)) { order[0] = 1; order[1] = 0; }

    int ids[2] = {BACKDROP, BACKDROP};
    uint32_t colors[2] = {color_of(f, 0), color_of(f, 0)};
    int found = 0;
    for (int i = 0; i < 2 && found < 2; i++) {
        int k = order[i];
        if (!(bgs & (4u << k))) continue;
        if ((l->dispcnt & 7) == 1 && k == 1) continue;  /* mode 1 has no BG3 */
        int index = affine_index(f, l, k, x);
        if (index == 0) continue;
        ids[found] = 2 + k;
        colors[found] = color_of(f, index);
        found++;
    }

    uint32_t top = colors[0];
    if (!effects) return top;
    int effect = (l->bldcnt >> 6) & 3;
    bool firstTarget = (l->bldcnt >> ids[0]) & 1;
    if (!firstTarget) return top;
    if (effect == 1) {
        bool secondTarget = (l->bldcnt >> (8 + ids[1])) & 1;
        if (ids[0] == BACKDROP || !secondTarget) return top;
        int a = l->bldalpha & 0x1F, b = (l->bldalpha >> 8) & 0x1F;
        if (a > 16) a = 16;
        if (b > 16) b = 16;
        return mix(a, top, b, colors[1]);
    }
    int evy = l->bldy & 0x1F;
    if (evy > 16) evy = 16;
    if (effect == 2) return brighten(top, evy);
    if (effect == 3) return darken(top, evy);
    return top;
}

void wide_affine_paint(const struct WideAffineFrame* f, uint32_t* buf, int stride, int left, int right) {
    for (int y = 0; y < WIDE_FRAME_H; y++) {
        uint32_t* line = buf + (size_t) y * (size_t) stride;
        for (int c = 0; c < left; c++) line[c] = affine_pixel(f, y, c - left);
        uint32_t* after = line + left + WIDE_FRAME_W;
        for (int c = 0; c < right; c++) after[c] = affine_pixel(f, y, WIDE_FRAME_W + c);
    }
}

float wide_affine_seam_match(const struct WideAffineFrame* f, const uint32_t* buf, int stride, int left) {
    int same = 0;
    for (int y = 0; y < WIDE_FRAME_H; y++) {
        const uint32_t* line = buf + (size_t) y * (size_t) stride + left;
        for (int k = 0; k < SEAM_COLUMNS; k++) {
            if ((line[k] & 0x00FFFFFFu) == (affine_pixel(f, y, k) & 0x00FFFFFFu)) same++;
            int x = WIDE_FRAME_W - SEAM_COLUMNS + k;
            if ((line[x] & 0x00FFFFFFu) == (affine_pixel(f, y, x) & 0x00FFFFFFu)) same++;
        }
    }
    return (float) same / (float) (WIDE_FRAME_H * 2 * SEAM_COLUMNS);
}
