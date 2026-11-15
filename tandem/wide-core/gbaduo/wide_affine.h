// Wide view for the GBA's rotation/scaling modes (mode 1 and 2): the margins beside the frame,
// drawn by carrying each scanline of the affine backgrounds on past the 240 pixels the game shows.
//
// An affine background line is a straight line through its 8bpp map: pixel x of line y samples the
// map at (sx + pa * x, sy + pc * x), with sx/sy/pa/pc as the game left them for that line. Games that
// change them per line (Golden Sun's curved world map, Mode 7-like floors) still have a straight line
// per row, so extending x below 0 and past 239 continues the same picture. The per-line registers
// come from mGBA's software renderer, which keeps them for every line of the frame it just drew
// (core.c fills a WideAffineFrame from it). Sprites are not drawn in the margins.
//
// No Android, no mGBA: compiled into the app and into the desktop harness, like wide.c.

#ifndef GBADUO_WIDE_AFFINE_H
#define GBADUO_WIDE_AFFINE_H

#include <stdbool.h>
#include <stdint.h>

#include "wide.h"

/** The video registers of one scanline, as they were when that line was drawn. */
struct WideAffineLine {
    uint16_t dispcnt;
    uint16_t bgcnt[2];      /* BG2CNT, BG3CNT */
    int16_t pa[2], pc[2];   /* BG2PA/BG2PC, BG3PA/BG3PC: the step per pixel, 8.8 fixed point */
    int32_t sx[2], sy[2];   /* the map position of pixel 0 of this line, 8.8 fixed point */
    uint16_t winout;
    uint16_t bldcnt, bldalpha, bldy;
};

/** One frame's worth of affine state, plus the video memory to sample. */
struct WideAffineFrame {
    struct WideAffineLine line[WIDE_FRAME_H];
    const uint8_t* vram;    /* 96 KB */
    const uint16_t* palette; /* BG palette: 256 BGR555 colours */
};

/** True when this frame can be extended: every line in mode 1 or 2 with only affine backgrounds showing. */
bool wide_affine_usable(const struct WideAffineFrame* f);

/** Fills the [left] columns before the frame and the [right] after it, rows 0..159 (see wide_paint). */
void wide_affine_paint(const struct WideAffineFrame* f, uint32_t* buf, int stride, int left, int right);

/** The share (0..1) of the 16 edge columns of the frame that the extension predicts exactly (see wide_seam_match). */
float wide_affine_seam_match(const struct WideAffineFrame* f, const uint32_t* buf, int stride, int left);

#endif
