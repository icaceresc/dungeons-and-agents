#!/usr/bin/env python3
"""Author the bundled pack's generated sprite art: the cutaway profile's `@Nx`
pieces (N = `S`), and the 1x pieces drawn from the same layout: the classic
profile's desks, the cutaway's base-density back-view sofa, and the city's
building bases; and the dungeon floors' `dungeon_*` stand-ins, which
`dungeon.toml` registers over the office pieces they redraw.

Draws in PALETTE-KEY space, so the output is .sprite text and the recolor keys
(H/B/S/P and their [ramps] shades) survive per-agent recoloring. The .sprite
files it writes are committed; edit this, not them, and rerun:

    just gen-art

`--check` writes nothing and fails if a sprite it draws is missing or differs
from the committed one, or if a sprite carrying the provenance line is no longer
drawn here (a write deletes those).

It resolves no colour itself: the engine owns the palette and its ramps, so look
at the result through the real renderer: `cargo run --release --example
cutaway_snapshot -- <out.png>` for the `@Nx` art (`--scale 1` for the base-density
sofa), `cargo run --release --example snapshot -- --crop-furniture desk <out.png>`
for the 1x desk.
"""

import argparse
import difflib
import inspect
import itertools
import math
import pathlib
import random
import sys
import tempfile
import tomllib
from typing import NamedTuple

S = 4  # the cutaway art's density

# ---- palette keys ---------------------------------------------------------
# recolor bases and their shades (bases in [palette], shades in [ramps])
HAIR, HAIR_SH, HAIR_LT, HAIR_HI = "H", "h", "Y", "Z"
SKIN, SKIN_SH, SKIN_DK = "S", "s", "i"
SHIRT, SHIRT_SH, SHIRT_LT, SHIRT_OUT = "B", "v", "W", "U"
PANTS, PANTS_SH, PANTS_LT = "P", "p", "("
# fixed colours, named by role
OUTLINE, WHITE = "n", "&"
EYE = "e"
SHOE, SHOE_HI = ";", ":"
# The knight's armour: iron (its helm, and its mail as rings of the iron's
# shades) and the leather of its belt; one base each in [palette], the rest
# their [ramps].
IRON, IRON_LT, IRON_SH, IRON_DK, IRON_HI = "Σ", "μ", "υ", "ϑ", "ϖ"
LEATHER, LEATHER_SH = "г", "ғ"
# A berserker's pelt: one base in [palette], its shades in [ramps].
FUR, FUR_LT, FUR_SH, FUR_DK = "ϝ", "ϛ", "ϟ", "ϡ"
WOOD, WOOD_SH, WOOD_LT, WOOD_HI, WOOD_DK, POOL = "D", "d", "O", "σ", "ψ", "ω"
BEZEL, SLATE, SHADOW = "M", "3", "4"
# The desk monitor's screen: the cutaway relights these keys, so only desk art
# draws them.
GLASS, GLASS_TXT = "j", "J"
# Any other screen's glass.
DISPLAY, DISPLAY_SHEEN = "Ξ", "Ж"
KEY_DK, KEYCAP, GREY = "k", "φ", "6"
LAMP, LAMP_HI, BULB = "7", "Θ", "9"
OFFWHITE, OFFWHITE_SH, PRINT = "¤", "!", "$"
MUG, MUG_SH = "V", "%"
CHAIR, CHAIR_RIM, CHAIR_BASE = "T", "I", "/"
# The @Nx art's one outline, round each piece's whole silhouette whatever its
# material, and a bun's rim where it sits on the head (`ball`); pack.toml's
# `[characters] outline` names it for the renderer.
SILHOUETTE = "κ"
COFFEE = "ρ"
# furniture materials
LEAF, LEAF_SH, LEAF_HI, LEAF_DK = "l", "L", "Φ", "Ψ"
POT, POT_SH, POT_HI = "g", "Γ", "δ"
ALU, ALU_DK = "Π", "θ"
FABRIC, FABRIC_HI, FABRIC_SH, FABRIC_SEAM = "C", "G", "Λ", "Ω"
# fixed hues, named by hue: the 1x art's own keys, lent to the furniture
INK, CYAN, RED, DARK_RED, VERMILION, BLUE, GOLD, TAN, BROWN, PINK, GREEN = (
    "q",
    "c",
    "r",
    "N",
    "o",
    "b",
    "y",
    "x",
    "z",
    "^",
    "λ",
)
PETAL_R, PETAL_Y, PETAL_HI = RED, GOLD, "ζ"
T = "."


def require(holds, why):
    """Fail with `why` unless `holds`: an explicit check, where an `assert`
    is compiled away under `-O`."""
    if not holds:
        raise ValueError(why)


def doc(draw) -> str:
    """`draw`'s docstring, the header its sprite carries."""
    return draw.__doc__ or ""


class Draws:
    """A seeded stream of draws built on `random()` alone: the one sequence
    the `random` docs keep across Python versions ("Notes on
    Reproducibility"), where `randrange` and `choice` may change, and the
    committed art must not."""

    def __init__(self, seed):
        self._rng = random.Random(seed)

    def random(self):
        return self._rng.random()

    def randrange(self, start, stop=None):
        if stop is None:
            start, stop = 0, start
        return start + int(self._rng.random() * (stop - start))

    def choice(self, seq):
        return seq[self.randrange(len(seq))]


def canvas(w, h):
    return [[T] * w for _ in range(h)]


def put(g, x, y, k):
    if 0 <= y < len(g) and 0 <= x < len(g[0]):
        g[y][x] = k


def rect(g, x0, y0, x1, y1, k):
    for y in range(max(0, y0), min(len(g), y1)):
        for x in range(max(0, x0), min(len(g[0]), x1)):
            g[y][x] = k


def outline(g, inside, out):
    h, w = len(g), len(g[0])
    marks = []
    for y in range(h):
        for x in range(w):
            if g[y][x] != T:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h and g[yy][xx] in inside:
                    marks.append((x, y))
                    break
    for x, y in marks:
        g[y][x] = out


# ---- the desk: one skeleton, drawn at 1x (classic) and at `S` (cutaway) -----
# Logical units. Both drawings scale every row and column below by their own
# density, so the `@Nx` art cannot drift from the 1x it redraws.
#
# Rust owns these facts; the copies here are pinned against the generated art
# by `pack`'s `a_desks_rows_follow_the_layout` and `effects`'s
# `the_glow_lands_on_the_desk_arts_monitor`.
#
# The desk `FurnitureDef`'s visual width (`desk_sprite_width_tracks_the_footprint_overhang`).
DESK_ART_W = 14
# `pack`'s `DESK_BEZEL_RAISE`: the monitor's row above the wood.
DESK_BEZEL_RAISE = 1
# `layout`'s `DESK_SURFACE_ROWS`, `DESK_FRONT_ROWS`, `DESK_LEG_ROWS`.
DESK_SURFACE_ROWS, DESK_FRONT_ROWS, DESK_LEG_ROWS = 5, 1, 2
# The back-turned desk's extra rows, all above, so the occupant (who y-sorts in
# FRONT of the desk) leaves the upper screen row clear. Its lower screen row
# sits inside the wood, flanked by it: the owner picked a monitor standing on
# its desk over one floating clear of every head.
DESK_NORTH_LIFT = 2
DESK_LEG_W = 2
# The monitor box: its columns (half-open), and from the sprite's top the first
# glass row and the chin row — casing above the glass, glass down to the chin —
# where the classic painter's glow lands (`pixel_painter::effects`'s `SCREEN_*`).
DESK_MONITOR_X0, DESK_MONITOR_X1 = 3, 11
DESK_GLASS_Y0, DESK_CHIN_Y = 2, 4
# The one arrangement every desk places its lamp and props by, in 1x columns
# from the art's west edge as the viewer-facing desk shows them: the lamp's
# bulb, the cup's and the token tower's west columns. The lamp is west, the cup
# beside it and the tower on the east wing. Each density draws its own rows.
# `display::compose`'s `every_desk_follows_the_one_arrangement` holds both
# densities to it.
DESK_ARRANGEMENT = {"bulb": 1, "cup": 2, "tower": 11}
# The desks seen from the sitter's side, the same desk turned round: their
# arrangement mirrors the one above, their props stand mirrored, and each prop's
# mark is its bottom-RIGHT cell (`pack::desk_props_mirrored`).
DESK_PROPS_MIRRORED = {"desk_north"}


def desk_arrangement(base):
    """`base`'s columns for its lamp's bulb and each prop's west edge."""
    if base not in DESK_PROPS_MIRRORED:
        return DESK_ARRANGEMENT
    bulb = DESK_ART_W - 1 - DESK_ARRANGEMENT["bulb"]
    return {"bulb": bulb} | {
        prop: DESK_ART_W - DESK_ARRANGEMENT[prop] - w
        for prop, w in DESK_PROP_W_1X.items()
    }


def desk_prop_mark_col(base, prop, scale):
    """The column `base`'s mark for `prop` names, on a grid `scale` to the 1x
    column: the prop's west column, or its east on a desk that mirrors it."""
    col = desk_arrangement(base)[prop]
    if base in DESK_PROPS_MIRRORED:
        return (col + DESK_PROP_W_1X[prop]) * scale - 1
    return col * scale


def desk_rows(lift):
    """The wood's rows for a desk `lift` rows taller above: `(top, lip, legs,
    height)`, the first rows of the surface, the front lip and the legs."""
    top = DESK_BEZEL_RAISE + lift
    lip = top + DESK_SURFACE_ROWS
    legs = lip + DESK_FRONT_ROWS
    return top, lip, legs, legs + DESK_LEG_ROWS


def desk_1x(lift, base):
    """The classic desk's wood: a lit back edge, a bright front lip, and legs
    dark on their inner side, with open floor between them so the carpet and
    anyone walking behind the desk show through, and the task lamp on the wing
    `desk_arrangement(base)` puts it on: a two-cell shade over its bulb, the
    shade's second cell toward the desk's edge. The cup and the paper tower are
    pieces of their own, stood at the art's marks."""
    top, lip, legs, h = desk_rows(lift)
    g = canvas(DESK_ART_W, h)
    rect(g, 0, top, DESK_ART_W, lip, WOOD)
    rect(g, 0, top, DESK_ART_W, top + 1, WOOD_LT)
    rect(g, 0, lip, DESK_ART_W, legs, WOOD_HI)
    for x0, inner in (
        (0, DESK_LEG_W - 1),
        (DESK_ART_W - DESK_LEG_W, DESK_ART_W - DESK_LEG_W),
    ):
        rect(g, x0, legs, x0 + DESK_LEG_W, h, WOOD_SH)
        rect(g, inner, legs, inner + 1, h, WOOD_DK)
    bulb = desk_arrangement(base)["bulb"]
    edge = -1 if bulb < DESK_ART_W // 2 else 1
    rect(g, min(bulb, bulb + edge), top, max(bulb, bulb + edge) + 1, top + 1, LAMP_HI)
    put(g, bulb, top + 1, BULB)
    return g


def monitor_stand_1x(g):
    """The chin under the monitor, the stand's shadow either side of it."""
    rect(
        g, DESK_MONITOR_X0 + 1, DESK_CHIN_Y, DESK_MONITOR_X1 - 1, DESK_CHIN_Y + 1, BEZEL
    )
    for x in (DESK_MONITOR_X0 + 1, DESK_MONITOR_X1 - 2):
        put(g, x, DESK_CHIN_Y, SHADOW)


def south_monitor_1x(g):
    """The viewer-facing desk's monitor at 1x: its back, lit along its top edge,
    on its stand."""
    rect(g, DESK_MONITOR_X0, 0, DESK_MONITOR_X1, DESK_CHIN_Y, BEZEL)
    rect(g, DESK_MONITOR_X0, 0, DESK_MONITOR_X1, 1, SLATE)
    monitor_stand_1x(g)


def desk_south_1x():
    """The viewer-facing desk at 1x: the monitor's back, lit along its top
    edge. Its glass rows stay casing: a viewer-facing seat never shows a
    screen, though the glow still lights them where a pack ships no
    `desk_north` and this art stands in for it."""
    g = desk_1x(0, "desk")
    south_monitor_1x(g)
    return g


def front_layer(art, monitor):
    """`art` where `monitor` paints on a blank canvas its size, clear elsewhere:
    what of a desk stands between the viewer and the sitter's props, drawn over
    them on the desk's own canvas (`pack::desk_front`)."""
    m = canvas(len(art[0]), len(art))
    monitor(m)
    return [
        [c if k != T else T for c, k in zip(row, mrow)] for row, mrow in zip(art, m)
    ]


def desk_front_1x():
    """The viewer-facing desk's front at 1x: its monitor, which hides the part
    of a sitter's cup behind it."""
    return front_layer(desk_south_1x(), south_monitor_1x)


def desk_north_1x():
    """The back-turned desk at 1x: the raised monitor, its casing outlined in
    grey so it reads against a dark carpet, two lines of dim text on its glass,
    and a keyboard a row clear of the stand so the two never merge into one
    dark base."""
    g = desk_1x(DESK_NORTH_LIFT, "desk_north")
    x0, x1 = DESK_MONITOR_X0, DESK_MONITOR_X1
    rect(g, x0, 0, x1, DESK_CHIN_Y, SLATE)
    rect(g, x0 + 1, 1, x1 - 1, DESK_CHIN_Y, BEZEL)
    rect(g, x0 + 1, DESK_GLASS_Y0, x1 - 1, DESK_CHIN_Y, GLASS)
    rect(g, x0 + 2, DESK_GLASS_Y0, x0 + 6, DESK_GLASS_Y0 + 1, GLASS_TXT)
    rect(g, x0 + 2, DESK_GLASS_Y0 + 1, x0 + 4, DESK_GLASS_Y0 + 2, GLASS_TXT)
    monitor_stand_1x(g)
    keys = DESK_CHIN_Y + 2
    rect(g, x0 + 1, keys, x1 - 1, keys + 1, GREY)
    for x in (x0 + 1, x1 - 2):
        put(g, x, keys, KEY_DK)
    return g


# The row each prop's foot stands on at 1x, from the art's top, per view: the
# cup on the sitter's side of the monitor, behind it as they face the viewer and
# before it once they turn their back; the tower beside the monitor.
DESK_PROP_FOOT_1X = {
    "desk": {"cup": 2, "tower": 4},
    "desk_north": {"cup": 6, "tower": 6},
}
# `token_meter`'s `MAX_TIER`: the tower's frames, one per tier.
TOKEN_MAX_TIER = 3
# The 1x tower's width and rows a tier, which both looks blit.
TOKEN_W_1X, TOKEN_ROWS_PER_TIER_1X = 3, 2


def desk_marks_1x(base):
    """A 1x desk's prop marks."""
    return [
        (prop, desk_prop_mark_col(base, prop, 1), row)
        for prop, row in DESK_PROP_FOOT_1X[base].items()
    ]


def desk_cup_1x():
    """The desk's coffee cup at 1x: its rim over its shadowed body."""
    return [[MUG, MUG], [MUG_SH, MUG_SH]]


# Each prop's 1x columns, which a mirrored desk's arrangement and marks turn on.
DESK_PROP_W_1X = {"cup": len(desk_cup_1x()[0]), "tower": TOKEN_W_1X}


def token_tower_1x():
    """The token meter's paper tower at 1x, a frame per tier: reams stacked
    two rows each, sheet over shade, the full tower's top sheet teetering a
    column east."""
    frames = []
    for tier in range(1, TOKEN_MAX_TIER + 1):
        h = tier * TOKEN_ROWS_PER_TIER_1X
        g = canvas(TOKEN_W_1X + 1, h)
        for i in range(h):
            dx = 1 if tier == TOKEN_MAX_TIER and i == h - 1 else 0
            rect(
                g,
                dx,
                h - 1 - i,
                dx + TOKEN_W_1X,
                h - i,
                OFFWHITE_SH if i % 2 else OFFWHITE,
            )
        frames.append(g)
    return frames


def token_sheet_1x():
    """The sheet falling onto the token tower at 1x."""
    return [[OFFWHITE] * TOKEN_W_1X]


# ---- the meeting sofas: one layout for both views and densities, in logical rows ----
# `Furniture::MeetingSofaBody`'s visual box
# (`every_hover_size_is_its_painted_sprite_size`).
SOFA_W, SOFA_H = 20, 7
# The back view's seat rows, under its sitter; the backrest below draws over
# their lap. `pack`'s `NORTH_SOFA_SEAT_ROWS`
# (`the_north_sofas_backrest_starts_on_its_lit_ridge`).
SOFA_SEAT_ROWS = 3
SOFA_RIDGE_ROWS = 1  # the backrest's lit top, then its back panel to the foot
# The front view's backrest rows, above its seam: `meeting_sofa.sprite`'s.
SOFA_BACK_ROWS = 3
# The three seats' centres (the seat waypoints' `SEAT_DX` about the sofa's
# centre column), on column boundaries, and half the pitch between them: where
# one cushion ends and the next begins.
SOFA_SEAT_COLS = (4, 10, 16)
SOFA_SEAT_HALF = 3


def meeting_sofa_north_1x():
    """The north-facing sofa at base density: lit cushion tops, a seam where the
    seat meets the backrest, its lit ridge, and the back panel shading down."""
    ridge = SOFA_SEAT_ROWS
    g = canvas(SOFA_W, SOFA_H)
    rect(g, 0, 1, SOFA_W, SOFA_H - 1, FABRIC)
    rect(g, 2, 1, SOFA_W - 1, 2, FABRIC_HI)
    for c in SOFA_SEAT_COLS[1:]:  # a seam midway between each two seat centres
        put(g, c - SOFA_SEAT_HALF, 1, OUTLINE)
    rect(g, 1, ridge - 1, SOFA_W - 1, ridge, OUTLINE)
    rect(g, 1, ridge, SOFA_W - 1, ridge + SOFA_RIDGE_ROWS, FABRIC_HI)
    rect(g, 1, SOFA_H - 2, SOFA_W - 1, SOFA_H - 1, FABRIC_SH)
    for y in range(1, SOFA_H - 1):
        put(g, 0, y, OUTLINE)
        put(g, SOFA_W - 1, y, OUTLINE)
    put(g, 1, 1, OUTLINE)
    rect(g, 1, 0, SOFA_W - 1, 1, OUTLINE)
    rect(g, 1, SOFA_H - 1, SOFA_W - 1, SOFA_H, OUTLINE)
    return g


# ---- the characters ----------------------------------------------------------
# A chibi figure: a big head over a small body, one near-black line round the
# whole silhouette. Every pose is a bald BODY, the face or the back of the head
# but never a scalp, that a hairstyle's layers dress per view: `behind` under
# the body, `over` on top. Neither is outlined here: the renderer outlines the
# dressed union, so no line runs between hair and face.
FIG_W = 8 * S
FIG_CX = FIG_W / 2  # sampled at pixel centres (x + 0.5): x mirrors to FIG_W - 1 - x
# Each pose's height in logical rows, the frame height its 1x base shares.
STANDING_ROWS, TYPING_ROWS, SEATED_ROWS, COUCH_ROWS = 12, 11, 10, 9
# Rows every standing and front- or back-view seated pose shares: the face
# (the eyes and mouth hang off it) and the shoulders.
FACE_TOP, FACE_BOTTOM, SHOULDER_Y = 12, 26, 26
# A seated tabard ends on the seat, where the base's hand row starts; a
# standing one is belted where the legs begin.
SEAT_Y, BELT_Y = 36, 38
# Where a sleeve ends and a hanging hand begins.
CUFF_Y = 34
SKIN_KEYS = {SKIN, SKIN_SH}


def grounded(frames):
    """`frames` moved down together until their lowest drawn row is the canvas's
    last: both painters ground and sort a piece on its box's bottom row."""
    blank = min(
        next((i for i, row in enumerate(reversed(g)) if any(c != T for c in row)), 0)
        for g in frames
    )
    return [[[T] * len(g[0])] * blank + g[: len(g) - blank] for g in frames]


def union_outline(g, k=SILHOUETTE):
    """One line round everything drawn, whatever its material."""
    outline(g, {c for row in g for c in row} - {T, k}, k)


def ellipse(g, cx, cy, rx, ry, k=HAIR):
    for y in range(max(0, int(cy - ry) - 1), min(len(g), int(cy + ry) + 2)):
        for x in range(1, len(g[0]) - 1):
            if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1:
                g[y][x] = k


def disc(g, cx, cy, r, k=HAIR):
    ellipse(g, cx, cy, r, r, k)


def tuft(g, bx, by, ang, length, half):
    """A tapered tuft from (bx, by) along `ang` degrees (screen: -90 is up)."""
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    for y in range(len(g)):
        for x in range(1, len(g[0]) - 1):
            dx, dy = x + 0.5 - bx, y + 0.5 - by
            u, v = dx * ux + dy * uy, -dx * uy + dy * ux
            if 0 <= u <= length and abs(v) <= half * (1 - u / length) + 0.35:
                g[y][x] = HAIR


def lock(g, x0, y0, x1, y1, w0, w1):
    """A lock from (x0, y0) to (x1, y1), `w0` wide at the root tapering to `w1`:
    long hair's fall and a ponytail's tail."""
    n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
    for i in range(n + 1):
        t = i / n
        cx, cy, hw = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, (w0 + (w1 - w0) * t) / 2
        for y in range(int(cy) - 1, int(cy) + 2):
            for x in range(int(cx - hw) - 1, int(cx + hw) + 2):
                if (
                    1 <= x < len(g[0]) - 1
                    and 0 <= y < len(g)
                    and abs(x + 0.5 - cx) <= hw
                    and abs(y + 0.5 - cy) <= 0.8
                ):
                    g[y][x] = HAIR


def curl(g, cx, cy, r):
    """One round curl lit on its own top-left, its lower-right rim in shade:
    drawn back to front, each stands apart from the one behind it."""
    for y in range(max(0, int(cy - r) - 1), min(len(g), int(cy + r) + 2)):
        for x in range(max(1, int(cx - r) - 1), min(len(g[0]) - 1, int(cx + r) + 2)):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            d = math.hypot(dx, dy)
            if d <= r:
                t = (dx + dy) / r
                g[y][x] = (
                    HAIR_SH
                    if (d > r - 1.1 and t > -0.1)
                    else HAIR_LT
                    if t < -0.5
                    else HAIR
                )


def rim_light(g, strands=(), sparkle=(), lit_top=True):
    """Every bump's top-left edge catches the light and its lower-right edge
    falls into shade, so a silhouette reads as locks rather than a helmet. A
    fringe passes `lit_top=False`: its top edge sits under the mop, unlit."""
    mop = {(x, y) for y in range(len(g)) for x in range(len(g[0])) if g[y][x] == HAIR}
    for x, y in mop:
        top_open = (x, y - 2) not in mop
        if (lit_top or not top_open) and (
            (x - 1, y - 1) not in mop or top_open or (x - 2, y) not in mop
        ):
            g[y][x] = HAIR_LT
        elif (x + 1, y + 1) not in mop or (x + 2, y) not in mop:
            g[y][x] = HAIR_SH
    for x, y in strands:
        if (x, y) in mop:
            g[y][x] = HAIR_SH
    for x, y in sparkle:
        if (x, y) in mop:
            g[y][x] = HAIR_HI
    return g


def terminator(g, cx, cy, r, from_y=0):
    """A head turning from the light: hair past a circle offset up and west,
    toward the light, drops a shade, so the mop reads as a ball."""
    lx, ly = cx - 3.0, cy - 3.5
    for y in range(from_y, len(g)):
        for x in range(len(g[0])):
            if g[y][x] == HAIR and math.hypot(x + 0.5 - lx, y + 0.5 - ly) > r:
                g[y][x] = HAIR_SH


def comb(g, lines, dy=0):
    """Comb lines in hair shade."""
    for pts in lines:
        for (x0, y0), (x1, y1) in itertools.pairwise(pts):
            n = max(abs(x1 - x0), abs(y1 - y0))
            for i in range(n + 1):
                x, y = round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n) + dy
                if g[y][x] in (HAIR, HAIR_LT):
                    g[y][x] = HAIR_SH


def fringe(g, tips, top, dy=0):
    """A fringe cut straight: per column, hair from `top` down to its tip row."""
    for x, tip in tips.items():
        for y in range(top + dy, tip + dy):
            g[y][x] = HAIR


def fringe_locks(g, locks, top, dy=0):
    """A fringe of separate locks, each a wedge from the hairline to its tip, so
    the brow shows between them."""
    for cx, tip, half in locks:
        tip = round(tip) + dy
        for y in range(top + dy, tip):
            w = half * (tip - y) / (tip - top - dy)
            for x in range(int(cx - w - 0.5), int(cx + w + 1.5)):
                if 1 <= x < len(g[0]) - 1 and abs(x + 0.5 - cx) <= w + 0.5:
                    g[y][x] = HAIR


def ball(g, cx, cy, r):
    """A bun: a round of its own, its rim dark where it sits on the head."""
    for y in range(len(g)):
        for x in range(1, len(g[0]) - 1):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if (
                r <= d < r + 1.0
                and g[y][x] != T
                and (y + 0.5 > cy + 1 or x + 0.5 > cx + 1 and cy > 8)
            ):
                g[y][x] = SILHOUETTE
    curl(g, cx, cy, r)


def paste(dst, src, dx=0, dy=0):
    """`src`'s opaque pixels onto `dst`, moved `dx` columns and `dy` rows."""
    for y in range(len(src)):
        for x in range(len(src[0])):
            if src[y][x] != T and 0 <= y + dy < len(dst) and 0 <= x + dx < len(dst[0]):
                dst[y + dy][x + dx] = src[y][x]


# ---- hairstyles ----------------------------------------------------------------
# Each style draws four views on its own layer canvas, the tallest pose's rows
# plus HAIR_HEADROOM above for a bun or a tuft: `front` and `side` as
# (behind, over) pairs, `back` and `crown` as one layer over the body. Every
# coordinate below is on the pose grid; `LIFT` shifts it onto the layer.
HAIR_HEADROOM = 6
LAYER_H = STANDING_ROWS * S + HAIR_HEADROOM
LIFT = HAIR_HEADROOM
# The skull in profile, and the head seen from above as it lies on the arms.
SIDE_CX, SIDE_CY = 14.0, 12.5
CROWN_CX, CROWN_CY, CROWN_R = FIG_CX, 16.5, 10.0


def layer():
    return canvas(FIG_W, LAYER_H)


def front_fringe(tips):
    f = layer()
    fringe(f, tips, FACE_TOP - 4, LIFT)
    return rim_light(f, lit_top=False)


def front_locks(locks):
    f = layer()
    fringe_locks(f, locks, FACE_TOP - 4, LIFT)
    return rim_light(f, lit_top=False)


def side_locks(locks, top=8):
    f = layer()
    fringe_locks(f, locks, top, LIFT)
    return rim_light(f, lit_top=False)


def nape_cut(g, half=6, rows=(20, 23)):
    """Hair gathered up leaves the nape bare: clear its middle so the neck shows."""
    for y in range(rows[0] + LIFT, rows[1] + LIFT):
        for x in range(1, FIG_W - 1):
            if g[y][x] != T and abs(x + 0.5 - FIG_CX) < half:
                g[y][x] = T


def crown_base(r_extra=0.0):
    c = layer()
    disc(c, CROWN_CX, CROWN_CY + LIFT, CROWN_R + r_extra)
    return c


def crown_finish(c, r=CROWN_R):
    rim_light(c)
    terminator(c, CROWN_CX, CROWN_CY + LIFT, r + 1.5)
    return c


MOP_PUFFS = [
    (FIG_CX, 12.0, 10.8),
    (6.8, 6.0, 3.6),
    (10.6, 3.8, 3.4),
    (15.2, 2.9, 3.4),
    (19.8, 3.4, 3.4),
    (24.2, 5.8, 3.6),
    (4.6, 10.6, 3.6),
    (26.4, 10.6, 3.6),
    (4.4, 15.0, 3.4),
    (26.6, 15.0, 3.4),
    (5.6, 18.6, 2.8),
    (25.4, 18.6, 2.8),
]


def style_mop():
    """A round cloud of a mop."""
    b = layer()
    for px, py, r in MOP_PUFFS:
        disc(b, px, py + LIFT, r)
    rim_light(
        b,
        [
            (11, 7 + LIFT),
            (12, 8 + LIFT),
            (19, 6 + LIFT),
            (19, 7 + LIFT),
            (23, 10 + LIFT),
            (7, 10 + LIFT),
        ],
        [(9, 3 + LIFT), (10, 3 + LIFT), (14, 2 + LIFT), (15, 2 + LIFT)],
    )
    back = layer()
    for px, py, r in MOP_PUFFS + [
        (10.5, 21.5, 3.2),
        (15.5, 22.2, 3.2),
        (20.5, 21.5, 3.2),
    ]:
        disc(back, px, py + (0.5 if r > 10 else 0) + LIFT, r)
    rim_light(back, [], [(9, 3 + LIFT), (10, 3 + LIFT), (14, 2 + LIFT), (15, 2 + LIFT)])
    terminator(back, FIG_CX, 12.5 + LIFT, 12.5, 8 + LIFT)
    comb(back, [((11, 7), (12, 10)), ((19, 6), (18, 9)), ((15, 11), (16, 14))], LIFT)
    sb = layer()
    for px, py, r in (
        (SIDE_CX, SIDE_CY, 11.2),
        (8, 5, 3.6),
        (13, 3, 3.6),
        (18.5, 3.5, 3.4),
        (22.5, 6.2, 3.2),
        (4.5, 11, 3.8),
        (4.5, 16, 3.6),
        (6.5, 20, 3.2),
        (10, 21.5, 3.0),
    ):
        disc(sb, px, py + LIFT, r)
    rim_light(
        sb,
        [(10, 8 + LIFT), (16, 7 + LIFT), (8, 14 + LIFT)],
        [(12, 2 + LIFT), (13, 2 + LIFT)],
    )
    c = crown_base(1.2)
    for a in range(0, 360, 40):
        disc(
            c,
            CROWN_CX + math.cos(math.radians(a)) * CROWN_R,
            CROWN_CY + LIFT + math.sin(math.radians(a)) * CROWN_R,
            3.2,
        )
    return {
        "front": (
            b,
            front_fringe(
                {
                    7: 16,
                    8: 15,
                    9: 14,
                    10: 13,
                    11: 13,
                    12: 14,
                    13: 13,
                    14: 12,
                    15: 13,
                    16: 13,
                    17: 12,
                    18: 13,
                    19: 14,
                    20: 13,
                    21: 13,
                    22: 14,
                    23: 15,
                    24: 16,
                }
            ),
        ),
        "back": back,
        "side": (
            sb,
            side_locks([(19.5, 13, 2.2), (22.5, 12.5, 2.2), (24.5, 11.5, 1.6)]),
        ),
        "crown": crown_finish(c, CROWN_R + 1.2),
        "ears": False,
    }


MESSY_TUFTS = (
    (8.5, 5.0, -125, 3.2, 2.8),
    (12.0, 2.8, -100, 2.8, 2.6),
    (16.0, 2.4, -80, 2.8, 2.6),
    (20.0, 3.2, -60, 3.2, 2.8),
    (23.5, 6.0, -35, 3.0, 2.6),
    (6.0, 8.5, -150, 2.6, 2.4),
    (26.0, 9.8, -8, 2.4, 2.2),
)


def style_messy():
    """The mop with short tufts breaking its top and sides."""
    b = layer()
    for px, py, r in (
        (FIG_CX, 12.5, 10.6),
        (5.4, 13.0, 3.9),
        (26.0, 13.0, 3.9),
        (5.8, 17.4, 3.0),
        (25.6, 17.4, 3.0),
    ):
        disc(b, px, py + LIFT, r)
    for t in MESSY_TUFTS:
        tuft(b, t[0], t[1] + LIFT, *t[2:])
    back = [row[:] for row in b]
    for t in (
        (10.0, 21.0, 100, 3.0, 2.2),
        (14.0, 22.0, 85, 3.4, 2.4),
        (18.0, 22.0, 95, 3.2, 2.4),
        (22.0, 21.0, 80, 3.0, 2.2),
    ):
        tuft(back, t[0], t[1] + LIFT, *t[2:])
    for px, py, r in ((6.0, 17.6, 3.0), (25.4, 17.6, 3.0)):
        disc(back, px, py + LIFT, r)
    strands = [
        (12, 6 + LIFT),
        (13, 7 + LIFT),
        (18, 5 + LIFT),
        (18, 6 + LIFT),
        (21, 7 + LIFT),
        (9, 8 + LIFT),
    ]
    rim_light(
        b, strands, [(10, 3 + LIFT), (11, 3 + LIFT), (15, 2 + LIFT), (16, 2 + LIFT)]
    )
    rim_light(
        back,
        strands + [(10, 12 + LIFT), (16, 15 + LIFT)],
        [(10, 3 + LIFT), (11, 3 + LIFT), (15, 2 + LIFT), (16, 2 + LIFT)],
    )
    sb = layer()
    for px, py, r in ((SIDE_CX, SIDE_CY, 11.0), (4.8, 13, 3.8), (6.2, 18.5, 3.2)):
        disc(sb, px, py + LIFT, r)
    for t in (
        (9, 4, -135, 3.4, 2.8),
        (13.5, 2.4, -105, 3.0, 2.6),
        (18.5, 2.8, -75, 3.0, 2.6),
        (22.5, 5.5, -40, 3.0, 2.4),
        (4.5, 8.5, -165, 3.0, 2.4),
        (5.5, 19.5, 160, 3.0, 2.2),
    ):
        tuft(sb, t[0], t[1] + LIFT, *t[2:])
    rim_light(sb, [(11, 7 + LIFT), (17, 6 + LIFT)], [(12, 2 + LIFT), (13, 2 + LIFT)])
    c = crown_base(1.2)
    for a in range(200, 350, 30):
        tuft(
            c,
            CROWN_CX + math.cos(math.radians(a)) * CROWN_R * 0.9,
            CROWN_CY + LIFT + math.sin(math.radians(a)) * CROWN_R * 0.9,
            a,
            3.2,
            2.6,
        )
    return {
        "front": (
            b,
            front_fringe(
                {
                    7: 16,
                    8: 15,
                    9: 13,
                    10: 13,
                    11: 14,
                    12: 16,
                    13: 13,
                    14: 12,
                    15: 12,
                    16: 13,
                    17: 13,
                    18: 15,
                    19: 13,
                    20: 12,
                    21: 13,
                    22: 14,
                    23: 15,
                    24: 16,
                }
            ),
        ),
        "back": back,
        "side": (sb, side_locks([(19.5, 13.5, 2.2), (22.5, 12, 2.2), (25, 13, 1.6)])),
        "crown": crown_finish(c, CROWN_R + 1.2),
        "ears": False,
    }


def style_side_part():
    """Less volume, parted west of centre, the fringe swept east in one sheet."""
    b = layer()
    for px, py, r in (
        (FIG_CX, 12.5, 10.2),
        (6.0, 14.0, 3.6),
        (25.0, 14.0, 3.8),
        (6.4, 18.0, 2.6),
        (24.8, 18.2, 2.8),
    ):
        disc(b, px, py + LIFT, r)
    rim_light(
        b,
        [
            (11, 2 + LIFT),
            (11, 3 + LIFT),
            (11, 4 + LIFT),
            (10, 5 + LIFT),
            (10, 6 + LIFT),
        ],
        [(15, 3 + LIFT), (16, 3 + LIFT)],
    )
    back = layer()
    for px, py, r in (
        (FIG_CX, 12.8, 10.4),
        (6.0, 14.0, 3.6),
        (25.0, 14.0, 3.8),
        (7.0, 18.4, 3.0),
        (24.2, 18.4, 3.2),
    ):
        disc(back, px, py + LIFT, r)
    rect(back, 9, 18 + LIFT, 23, 22 + LIFT, HAIR)
    rim_light(back, [], [(15, 3 + LIFT), (16, 3 + LIFT)])
    terminator(back, FIG_CX, 12.8 + LIFT, 12.0, 8 + LIFT)
    comb(back, [((12, 4), (10, 9), (9, 14)), ((17, 4), (19, 9), (21, 13))], LIFT)
    sb = layer()
    disc(sb, SIDE_CX, SIDE_CY + LIFT, 10.8)
    ellipse(sb, 7, 17 + LIFT, 4, 5)
    rim_light(
        sb,
        [(10, 5 + LIFT), (8, 9 + LIFT), (7, 13 + LIFT)],
        [(15, 2 + LIFT), (16, 2 + LIFT)],
    )
    c = crown_finish(crown_base())
    for y in range(
        int(CROWN_CY - CROWN_R) + 1 + LIFT, int(CROWN_CY) + 2 + LIFT
    ):  # the part
        if c[y][int(CROWN_CX) - 2] != T:
            c[y][int(CROWN_CX) - 2] = HAIR_SH
    return {
        "front": (
            b,
            front_fringe(
                {
                    7: 14,
                    8: 13,
                    9: 12,
                    10: 12,
                    11: 12,
                    12: 12,
                    13: 13,
                    14: 13,
                    15: 13,
                    16: 14,
                    17: 14,
                    18: 14,
                    19: 15,
                    20: 15,
                    21: 15,
                    22: 16,
                    23: 16,
                    24: 17,
                }
            ),
        ),
        "back": back,
        "side": (
            sb,
            side_locks(
                [(18.5, 11.5, 2.4), (21.5, 12.5, 2.6), (24.5, 13.5, 2.2)], top=7
            ),
        ),
        "crown": c,
        "ears": False,
    }


def style_long():
    """Long and parted in the middle, falling behind the shoulders to the
    chest in pointed ends."""
    b = layer()
    ellipse(b, FIG_CX, 12.0 + LIFT, 11.2, 11.0)
    for y in range(12 + LIFT, 35 + LIFT):
        spread = (y - 12 - LIFT) / 23
        rect(b, int(3 - spread * 1.5), y, int(29 + spread * 1.5), y + 1, HAIR)
    for x0 in (1, 5, 9, 22, 26, 30):
        for i in range(3):
            rect(
                b,
                max(1, x0 - 2 + i),
                35 + LIFT + i,
                min(FIG_W - 1, x0 + 2 - i),
                36 + LIFT + i,
                HAIR,
            )
    rim_light(
        b,
        [
            (9, 6 + LIFT),
            (10, 7 + LIFT),
            (21, 6 + LIFT),
            (22, 7 + LIFT),
            (4, 22 + LIFT),
            (4, 26 + LIFT),
            (27, 22 + LIFT),
            (27, 26 + LIFT),
        ],
        [(10, 3 + LIFT), (11, 3 + LIFT)],
    )
    back = layer()
    ellipse(back, FIG_CX, 12.2 + LIFT, 11.2, 11.0)
    # The fall narrows below the head so the shoulders show either side of it:
    # the shirt is how a viewer tells one long-haired back from another.
    for y in range(12 + LIFT, 37 + LIFT):
        spread = (y - 12 - LIFT) / 25
        narrow = min(1.0, (y - 12 - LIFT) / 10) * 4
        rect(back, int(4 + narrow - spread), y, int(28 - narrow + spread), y + 1, HAIR)
    for x0 in (9, 13, 17, 21, 25):
        for i in range(3):
            rect(
                back,
                max(1, x0 - 2 + i),
                37 + LIFT + i,
                min(FIG_W - 1, x0 + 2 - i),
                38 + LIFT + i,
                HAIR,
            )
    rim_light(back, [], [(10, 3 + LIFT), (11, 3 + LIFT)])
    terminator(back, FIG_CX, 20.0 + LIFT, 19.0, 20 + LIFT)
    for x in range(7, 25):  # a band of sheen across the crown
        y = 7 + LIFT + abs(x - 15) // 4
        if back[y][x] == HAIR:
            back[y][x] = HAIR_LT
    comb(
        back,
        [
            ((9, 12), (8, 22), (7, 33)),
            ((15, 14), (15, 24), (14, 35)),
            ((21, 12), (22, 22), (23, 33)),
            ((12, 26), (11, 34)),
            ((19, 26), (20, 34)),
        ],
        LIFT,
    )
    sb = layer()
    disc(sb, SIDE_CX, SIDE_CY + LIFT, 11.0)
    lock(sb, 8.5, 12 + LIFT, 6.0, 38 + LIFT, 11, 6)  # full enough to meet the neck
    rim_light(
        sb,
        [(9, 18 + LIFT), (8, 24 + LIFT), (7, 30 + LIFT), (11, 7 + LIFT)],
        [(14, 2 + LIFT), (15, 2 + LIFT)],
    )
    so = side_locks([(19.5, 13, 2.2), (22.5, 12.5, 2.2), (24.5, 12, 1.6)])
    strand = layer()
    lock(strand, 14.5, 14 + LIFT, 15.0, 24 + LIFT, 3, 2)  # its west edge on the face's
    paste(so, rim_light(strand))
    c = layer()
    ellipse(c, CROWN_CX, CROWN_CY + 4 + LIFT, 12.5, 13.5)
    disc(c, CROWN_CX, CROWN_CY + LIFT, CROWN_R)
    crown_finish(c)
    for x0 in (6, 11, 16, 21, 26):
        for y in range(int(CROWN_CY + 4) + LIFT, int(CROWN_CY + 16) + LIFT):
            if c[y][x0] in (HAIR, HAIR_LT):
                c[y][x0] = HAIR_SH
    return {
        "front": (
            b,
            front_fringe(
                {
                    7: 20,
                    8: 17,
                    9: 15,
                    10: 14,
                    11: 13,
                    12: 12,
                    13: 12,
                    14: 11,
                    17: 11,
                    18: 12,
                    19: 12,
                    20: 13,
                    21: 14,
                    22: 15,
                    23: 17,
                    24: 20,
                }
            ),
        ),
        "back": back,
        "side": (sb, so),
        "crown": c,
        "ears": False,
    }


def style_bun():
    """Pulled back tight into a bun on the crown: combed lines run up to it, the ears show, the
    bun rises into the headroom."""
    b = layer()
    ellipse(b, FIG_CX, 13.0 + LIFT, 10.4, 9.6)
    rim_light(b, [(11, 6 + LIFT), (11, 8 + LIFT), (20, 6 + LIFT), (20, 8 + LIFT)])
    ball(b, FIG_CX, 2.6 + LIFT, 4.0)
    back = layer()
    ellipse(back, FIG_CX, 13.0 + LIFT, 10.2, 9.6)
    nape_cut(back)
    rim_light(back)
    terminator(back, FIG_CX, 13.0 + LIFT, 11.5, 8 + LIFT)
    comb(
        back,
        [
            ((8, 17), (10, 12), (13, 8)),
            ((15, 19), (15, 13), (15, 8)),
            ((23, 17), (21, 12), (18, 8)),
        ],
        LIFT,
    )
    ball(back, FIG_CX, 2.6 + LIFT, 4.0)
    sb = layer()
    disc(sb, SIDE_CX, SIDE_CY + 0.5 + LIFT, 10.2)
    rim_light(sb, [(10, 6 + LIFT), (8, 10 + LIFT), (16, 5 + LIFT)])
    ball(sb, 5.0, 5.5 + LIFT, 4.0)
    c = crown_finish(crown_base())
    curl(c, CROWN_CX, CROWN_CY - CROWN_R + 3.5 + LIFT, 3.8)
    return {
        "front": (
            b,
            front_fringe(
                {
                    7: 12,
                    8: 11,
                    9: 11,
                    10: 10,
                    11: 10,
                    12: 10,
                    13: 10,
                    14: 10,
                    15: 10,
                    16: 10,
                    17: 10,
                    18: 10,
                    19: 10,
                    20: 10,
                    21: 10,
                    22: 11,
                    23: 11,
                    24: 12,
                }
            ),
        ),
        "back": back,
        "side": (sb, side_locks([(20.5, 11, 2.6), (23.5, 11, 2.2)], top=7)),
        "crown": c,
        "ears": True,
    }


def style_crop():
    """Short and close to the skull, the fringe cut in points, the ears
    showing."""
    b = layer()
    ellipse(b, FIG_CX, 13.0 + LIFT, 10.2, 9.6)
    rim_light(b, [(12, 6 + LIFT), (19, 6 + LIFT)], [(12, 5 + LIFT), (13, 5 + LIFT)])
    back = layer()
    ellipse(back, FIG_CX, 13.2 + LIFT, 10.2, 9.4)
    for y in range(20 + LIFT, 24 + LIFT):  # the nape tapers
        for x in range(1, FIG_W - 1):
            if back[y][x] == HAIR and abs(x + 0.5 - FIG_CX) > 7 - (y - 20 - LIFT):
                back[y][x] = T
    rim_light(
        back,
        [(12, 7 + LIFT), (19, 7 + LIFT), (15, 12 + LIFT)],
        [(12, 5 + LIFT), (13, 5 + LIFT)],
    )
    sb = layer()
    disc(sb, SIDE_CX, SIDE_CY + 0.6 + LIFT, 10.0)
    for y in range(18 + LIFT, 24 + LIFT):
        for x in range(1, FIG_W - 1):
            if sb[y][x] == HAIR and x > 11 - (y - 18 - LIFT):
                sb[y][x] = T
    rim_light(sb, [(10, 7 + LIFT), (16, 5 + LIFT)], [(13, 3 + LIFT), (14, 3 + LIFT)])
    return {
        "front": (
            b,
            front_locks(
                [
                    (8.5, 13, 1.8),
                    (11.5, 13.5, 2.0),
                    (14.5, 12.5, 2.0),
                    (17.5, 13.5, 2.0),
                    (20.5, 12.5, 2.0),
                    (23.0, 13, 1.6),
                ]
            ),
        ),
        "back": back,
        "side": (sb, side_locks([(20.5, 11.5, 2.0), (23.5, 11.5, 1.8)])),
        "crown": crown_finish(crown_base()),
        "ears": True,
    }


def style_curls():
    """Tight curls in a close cap: rows of small rounds, each lit on its own."""
    b = layer()
    ellipse(b, FIG_CX, 12.5 + LIFT, 10.6, 10.0)
    rim_light(b)
    for cy, xs in (
        (2.8, (10.0, 13.5, 17.0, 20.5)),
        (5.2, (7.2, 10.6, 14.0, 17.4, 20.8, 24.0)),
        (8.0, (5.4, 8.6, 12.0, 15.5, 19.0, 22.4, 25.6)),
        (11.2, (4.6, 26.4)),
        (14.4, (4.6, 26.4)),
    ):
        for cx in xs:
            curl(b, cx, cy + LIFT, 2.3)
    f = layer()
    for cx in (8.4, 11.6, 14.8, 18.0, 21.2, 23.8):
        curl(f, cx, 11.0 + LIFT, 2.0)
    back = layer()
    ellipse(back, FIG_CX, 13.2 + LIFT, 10.4, 9.8)
    rim_light(back)
    for cy, xs in (
        (2.8, (10.0, 13.5, 17.0, 20.5)),
        (5.2, (7.2, 10.6, 14.0, 17.4, 20.8, 24.0)),
        (8.0, (5.4, 8.6, 12.0, 15.5, 19.0, 22.4, 25.6)),
        (11.2, (4.6, 7.8, 11.2, 14.6, 18.0, 21.4, 24.6)),
        (14.4, (4.8, 8.2, 11.6, 15.0, 18.4, 21.8, 25.2)),
        (17.6, (6.4, 9.8, 13.2, 16.6, 20.0, 23.6)),
        (20.4, (9.6, 13.0, 16.4, 19.8)),
    ):
        for cx in xs:
            curl(back, cx, cy + LIFT, 2.3)
    sb = layer()
    disc(sb, SIDE_CX, SIDE_CY + LIFT, 10.8)
    rim_light(sb)
    for cy, xs in (
        (3.0, (9.5, 13, 16.5, 20)),
        (5.8, (6.5, 10, 13.5, 17, 20.5, 23.5)),
        (8.8, (4.5, 7.8, 11.2, 14.6, 18, 21.4)),
        (12, (4, 7.2, 10.6)),
        (15.2, (4.2, 7.6, 11)),
        (18.4, (5.4, 8.8)),
        (21, (8, 11.2)),
    ):
        for cx in xs:
            curl(sb, cx, cy + LIFT, 2.3)
    so = layer()
    for cx in (20.5, 23.5):
        curl(so, cx, 10.5 + LIFT, 2.0)
    c = crown_finish(crown_base())
    for rr, n in ((0, 1), (4.5, 6), (8.2, 10)):
        for i in range(n):
            a = 2 * math.pi * i / n
            curl(
                c, CROWN_CX + math.cos(a) * rr, CROWN_CY + LIFT + math.sin(a) * rr, 2.3
            )
    return {"front": (b, f), "back": back, "side": (sb, so), "crown": c, "ears": False}


def style_shaggy():
    """A shaggy mop whose fringe falls in locks to the eyes."""
    b = layer()
    for px, py, r in (
        (FIG_CX, 12.0, 10.8),
        (5.2, 14.5, 3.8),
        (26.2, 14.5, 3.8),
        (5.6, 19.0, 2.8),
        (25.8, 19.0, 2.8),
    ):
        disc(b, px, py + LIFT, r)
    for t in (
        (9, 4.5, -120, 2.6, 2.6),
        (14.5, 2.4, -95, 2.4, 2.6),
        (20, 3.2, -65, 2.6, 2.6),
    ):
        tuft(b, t[0], t[1] + LIFT, *t[2:])
    back = [row[:] for row in b]
    for px, py, r in ((FIG_CX, 12.4, 10.8), (5.8, 19.0, 3.0), (25.6, 19.0, 3.0)):
        disc(back, px, py + LIFT, r)
    for t in (
        (8.0, 20.5, 105, 4.0, 2.4),
        (12.0, 21.5, 92, 4.4, 2.6),
        (16.0, 22.0, 88, 4.6, 2.6),
        (20.0, 21.5, 85, 4.4, 2.6),
        (24.0, 20.5, 75, 4.0, 2.4),
    ):
        tuft(back, t[0], t[1] + LIFT, *t[2:])
    rim_light(b, [(12, 5 + LIFT), (18, 5 + LIFT)], [(12, 3 + LIFT), (13, 3 + LIFT)])
    rim_light(
        back,
        [
            (12, 6 + LIFT),
            (18, 6 + LIFT),
            (10, 18 + LIFT),
            (14, 19 + LIFT),
            (18, 19 + LIFT),
            (22, 18 + LIFT),
        ],
        [(12, 3 + LIFT), (13, 3 + LIFT)],
    )
    sb = layer()
    for px, py, r in (
        (SIDE_CX, SIDE_CY, 11.0),
        (4.8, 13.5, 3.8),
        (6, 19, 3.2),
        (10, 21.5, 2.8),
    ):
        disc(sb, px, py + LIFT, r)
    for t in (
        (10, 3.5, -125, 2.8, 2.6),
        (15, 2.2, -95, 2.6, 2.6),
        (20, 3.4, -65, 2.6, 2.4),
    ):
        tuft(sb, t[0], t[1] + LIFT, *t[2:])
    rim_light(
        sb,
        [(11, 7 + LIFT), (17, 6 + LIFT), (8, 14 + LIFT)],
        [(13, 2 + LIFT), (14, 2 + LIFT)],
    )
    c = crown_base(1.2)
    for a in range(200, 350, 30):
        tuft(
            c,
            CROWN_CX + math.cos(math.radians(a)) * CROWN_R * 0.9,
            CROWN_CY + LIFT + math.sin(math.radians(a)) * CROWN_R * 0.9,
            a,
            3.2,
            2.6,
        )
    return {
        "front": (
            b,
            front_locks(
                [
                    (7.5, 18, 1.8),
                    (10.0, 16.5, 2.2),
                    (13.0, 17.5, 2.4),
                    (16.2, 16.5, 2.4),
                    (19.2, 17.5, 2.4),
                    (22.0, 16.5, 2.2),
                    (24.4, 18, 1.8),
                ]
            ),
        ),
        "back": back,
        "side": (
            sb,
            side_locks(
                [(17.5, 16, 2.2), (20.5, 17.5, 2.4), (23.5, 16.5, 2.2), (25.5, 15, 1.4)]
            ),
        ),
        "crown": crown_finish(c, CROWN_R + 1.2),
        "ears": False,
    }


def style_ponytail():
    """Gathered into a ponytail swept over the east shoulder."""
    b = layer()
    ellipse(b, FIG_CX, 12.5 + LIFT, 10.6, 10.2)
    rim_light(b, [(12, 5 + LIFT), (13, 6 + LIFT)], [(11, 3 + LIFT), (12, 3 + LIFT)])
    f = front_fringe(
        {
            7: 15,
            8: 14,
            9: 13,
            10: 12,
            11: 12,
            12: 12,
            13: 12,
            14: 12,
            15: 12,
            16: 12,
            17: 12,
            18: 12,
            19: 13,
            20: 13,
            21: 14,
            22: 15,
            23: 16,
            24: 17,
        }
    )
    paste(f, tail(25, 17, 27, 33, 18))
    back = layer()
    ellipse(back, FIG_CX, 12.8 + LIFT, 10.6, 10.0)
    nape_cut(back)
    rim_light(back)
    terminator(back, FIG_CX, 12.8 + LIFT, 12.0, 8 + LIFT)
    comb(
        back,
        [
            ((8, 9), (14, 12), (22, 16)),
            ((10, 16), (16, 17), (22, 17)),
            ((13, 5), (18, 9), (23, 15)),
        ],
        LIFT,
    )
    paste(back, tail(24, 16, 27, 30, 17))
    sb = layer()
    disc(sb, SIDE_CX, SIDE_CY + 0.4 + LIFT, 10.4)
    rim_light(sb, [(10, 6 + LIFT), (8, 10 + LIFT), (13, 9 + LIFT), (16, 12 + LIFT)])
    so = side_locks([(20.5, 11.5, 2.4), (23.5, 12, 2.0)])
    paste(so, tail(9, 17, 10, 33, 18))
    c = crown_finish(crown_base())
    paste(
        c, tail(CROWN_CX + 8, CROWN_CY + 2, CROWN_CX + 13, CROWN_CY + 12, CROWN_CY + 3)
    )
    return {"front": (b, f), "back": back, "side": (sb, so), "crown": c, "ears": False}


def clip_rows(g, keep):
    """Clear every row of `g` (on the pose grid) that `keep` does not hold."""
    for y in range(LAYER_H):
        if not keep(y - LIFT):
            g[y] = [T] * FIG_W


def iron_lit(g, cx, cy, r, glints=()):
    """Iron lit as a ball: past a circle offset up and west, toward the light,
    it drops a shade, its upper-west edge catches the light, and `glints` (on
    the pose grid) shine."""
    lx, ly = cx - 3.0, cy - 3.5 + LIFT
    metal = {(x, y) for y in range(LAYER_H) for x in range(FIG_W) if g[y][x] == IRON}
    for x, y in metal:
        if math.hypot(x + 0.5 - lx, y + 0.5 - ly) > r:
            g[y][x] = IRON_SH
        elif (x - 1, y) not in metal or (x, y - 1) not in metal:
            g[y][x] = IRON_LT
    for x, y in glints:
        put(g, x, y + LIFT, IRON_HI)


def plume(g, x, y, sweep):
    """A horsehair plume in the agent's hair colour from an iron socket at
    (x, y) on the pose grid: seen from the front or behind (`sweep` 0) a full
    tuft rising over the bowl, in profile swept `sweep` columns back and
    falling."""
    if sweep:
        lock(g, x, y + LIFT, x - sweep * 0.6, y - 4.5 + LIFT, 5.0, 4.0)
        lock(g, x - sweep * 0.6, y - 4.5 + LIFT, x - sweep, y + LIFT, 4.0, 2.0)
    else:
        ellipse(g, x, y - 2.0 + LIFT, 3.0, 4.0)
        lock(g, x, y + 1 + LIFT, x, y - 2 + LIFT, 2.4, 4.4)
    rim_light(g)
    rect(g, int(x) - 2, int(y) + LIFT, int(x) + 2, int(y) + 2 + LIFT, IRON_DK)


def coif(g, cx, cy, rx, ry, shoulders):
    """The mail hood under the helm: an oval round the head, and where it falls
    onto the shoulders, `shoulders`, `(x0, y0, x1, y1)` on the pose grid."""
    ring = layer()
    ellipse(ring, cx, cy + LIFT, rx, ry, IRON)
    for y in range(LAYER_H):
        for x in range(FIG_W):
            x0, y0, x1, y1 = shoulders
            if ring[y][x] != T or (x0 <= x < x1 and y0 <= y - LIFT < y1):
                g[y][x] = IRON_DK if (x + y - LIFT) % 2 else IRON_SH


def style_knight_helm():
    """An open-faced iron helm: a rounded bowl lit as a ball, a riveted brow
    band, a nasal bar down between the eyes, a mail coif round the face and
    over the neck, and a plume in the agent's hair colour."""
    rim_rows = (12, 15)  # the brow band's rows, half-open: under them the face
    bowl = (FIG_CX, 13.0, 10.8, 10.2)
    rivets = (8, 12, 20, 24)

    def band(g, cols, rivet_cols):
        for y in range(*rim_rows):
            for x in cols:
                if g[y + LIFT][x] != T:
                    g[y + LIFT][x] = IRON_DK if y == rim_rows[1] - 1 else IRON_SH
        for x in rivet_cols:
            put(g, x, rim_rows[0] + LIFT, IRON_LT)

    b = layer()
    coif(b, FIG_CX, 17.5, 11.2, 10.6, (9, 22, 23, 28))
    f = layer()
    ellipse(f, bowl[0], bowl[1] + LIFT, bowl[2], bowl[3], IRON)
    clip_rows(f, lambda y: y < rim_rows[1])
    iron_lit(f, bowl[0], bowl[1], bowl[2] - 1.5, [(10, 6), (11, 5)])
    band(f, range(FIG_W), rivets)
    rect(f, 15, rim_rows[1] + LIFT, 17, 21 + LIFT, IRON)  # the nasal
    rect(f, 16, rim_rows[1] + LIFT, 17, 21 + LIFT, IRON_SH)
    put(f, 15, rim_rows[1] + LIFT, IRON_LT)
    plume(f, FIG_CX, 3.0, 0)

    back = layer()
    coif(back, FIG_CX, 17.5, 10.8, 10.0, (9, 22, 23, 28))
    shell = layer()
    ellipse(shell, bowl[0], bowl[1] + LIFT, bowl[2] - 0.2, bowl[3], IRON)
    clip_rows(shell, lambda y: y < rim_rows[1] + 1)
    iron_lit(shell, bowl[0], bowl[1], bowl[2] - 1.5, [(10, 6), (11, 5)])
    paste(back, shell)
    for y in range(rim_rows[0] + 1, rim_rows[1] + 1):
        for x in range(FIG_W):
            if back[y + LIFT][x] in (IRON, IRON_LT, IRON_SH, IRON_HI):
                back[y + LIFT][x] = IRON_DK if y == rim_rows[1] else IRON_SH
    plume(back, FIG_CX, 3.0, 0)

    sb = layer()
    coif(sb, 12.5, 16.5, 10.0, 11.0, (6, 22, 20, 28))
    so = layer()
    coif(so, 15.5, 19.0, 3.6, 8.0, (12, 22, 20, 28))  # over the cheek and jaw
    shell = layer()
    disc(shell, SIDE_CX, SIDE_CY + LIFT, 11.0, IRON)
    clip_rows(shell, lambda y: y < rim_rows[1] - 1)
    iron_lit(shell, SIDE_CX, SIDE_CY, 10.5, [(9, 5), (10, 4)])
    paste(so, shell)
    for y in range(rim_rows[0] - 1, rim_rows[1] - 1):
        for x in range(FIG_W):
            if so[y + LIFT][x] in (IRON, IRON_LT, IRON_SH, IRON_HI):
                so[y + LIFT][x] = IRON_DK if y == rim_rows[1] - 2 else IRON_SH
    for x in (8, 13, 18, 23):
        if so[rim_rows[0] - 1 + LIFT][x] != T:
            put(so, x, rim_rows[0] - 1, IRON_LT)
    rect(so, 25, rim_rows[1] - 2 + LIFT, 27, 19 + LIFT, IRON)  # the nasal
    rect(so, 26, rim_rows[1] - 2 + LIFT, 27, 19 + LIFT, IRON_SH)
    plume(so, SIDE_CX - 1.0, 2.0, 8)

    c = layer()
    disc(c, CROWN_CX, CROWN_CY + LIFT, CROWN_R, IRON)
    iron_lit(c, CROWN_CX, CROWN_CY, CROWN_R + 1.5, [(11, 10), (12, 9)])
    for y in range(LAYER_H):
        for x in range(FIG_W):
            d = math.hypot(x + 0.5 - CROWN_CX, y + 0.5 - CROWN_CY - LIFT)
            if c[y][x] != T and d > CROWN_R - 1.2:
                c[y][x] = IRON_DK
    crest = layer()
    top, tail = CROWN_CY - CROWN_R + 1.5 + LIFT, CROWN_CY + 3 + LIFT
    lock(crest, CROWN_CX, top, CROWN_CX, tail, 3.6, 2.2)
    rim_light(crest)
    paste(c, crest)
    return {
        "front": (b, f),
        "back": back,
        "side": (sb, so),
        "crown": c,
        "ears": False,
    }


# ---- the adventurers' classes ---------------------------------------------------
# Each class is a hairstyle whose layers reach past the head: its headgear, and
# the mantle, cape, robe or pelt it lays over the one shared body (the knight's
# tabard and mail). A view's layer is laid on every pose of that view, so a
# front layer leaves to the body what some front pose animates: the torso's
# middle, where a mug is held, and each hand's swing.
# The front poses' animated zones, on the pose grid as (x0, y0, x1, y1),
# half-open: the mug and the hands holding it (both hands, or carried east
# while walking), then each hanging hand's swing. A weapon would be held in
# a hand zone, on a per-pose hand mark no frame carries yet.
MUG_ZONE = (10, 29, 25, 36)
HAND_ZONES = ((3, 33, 9, 41), (23, 33, 29, 41))


def region(g, inside, key):
    """Every layer pixel whose centre, on the pose grid, `inside(x, y)` holds,
    in `key`."""
    for y in range(LAYER_H):
        for x in range(1, FIG_W - 1):
            if inside(x + 0.5, y - LIFT + 0.5):
                g[y][x] = key


def in_oval(cx, cy, rx, ry):
    return lambda x, y: ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1


def box(x0, y0, x1, y1):
    return lambda x, y: x0 <= x < x1 and y0 <= y < y1


def clear(g, zones):
    """Leave `zones` (pose-grid boxes, half-open) to the body."""
    for x0, y0, x1, y1 in zones:
        region(g, box(x0, y0, x1, y1), T)


CLOTH_KEYS = (SHIRT, SHIRT_LT, SHIRT_SH, SHIRT_OUT)


def cloth(g, east=20.0):
    """The cloth (`B`) lit as the tabard is: its west edge catches the light,
    past column `east` it turns away, and its foot is hemmed dark."""
    drawn = {(x, y) for y in range(LAYER_H) for x in range(FIG_W) if g[y][x] == SHIRT}
    for x, y in drawn:
        if x + 0.5 > east:
            g[y][x] = SHIRT_SH
        elif (x - 1, y) not in drawn:
            g[y][x] = SHIRT_LT
    for x, y in drawn:
        if (x, y + 1) not in drawn:
            g[y][x] = SHIRT_OUT


def hood_shadow(g, opening, rows):
    """The hood's shade on the brow: inside `opening` over pose rows `rows`
    (half-open), above the eyes, the hood's own darkest cloth fading through
    the darkest skin into the face."""
    region(g, lambda x, y: opening(x, y) and rows[0] <= y < rows[1] - 1, SHIRT_OUT)
    region(g, lambda x, y: opening(x, y) and rows[1] - 1 <= y < rows[1], SKIN_DK)


def lining(g, opening, key=HAIR):
    """The hood's lining, a line in `key` round the inside of its `opening`."""
    edge = [
        (x, y)
        for y in range(LAYER_H)
        for x in range(1, FIG_W - 1)
        if g[y][x] in CLOTH_KEYS
        and any(
            opening(x + dx + 0.5, y + dy - LIFT + 0.5)
            for dx, dy in ((1, 0), (-1, 0), (0, 1))
        )
    ]
    for x, y in edge:
        g[y][x] = key


def fur(g, inside, ragged=3):
    """A pelt where `inside` holds, its lower edge torn into tufts up to
    `ragged` rows long, lit along its top, dappled with darker locks."""
    region(g, inside, FUR)
    pelt = {(x, y) for y in range(LAYER_H) for x in range(FIG_W) if g[y][x] == FUR}
    for x, y in sorted(pelt):
        if (x, y + 1) not in pelt:
            for d in range(1, 1 + (x * 7 + 3) % (ragged + 1)):
                put(g, x, y + d, FUR_SH)
    pelt = {
        (x, y) for y in range(LAYER_H) for x in range(FIG_W) if g[y][x] in (FUR, FUR_SH)
    }
    for x, y in pelt:
        if (x, y - 1) not in pelt:
            g[y][x] = FUR_LT
        elif (x, y + 1) not in pelt or (x * 3 + y * 5) % 11 == 0:
            g[y][x] = FUR_DK


def shoulders(top, bottom):
    """A pelt's lie over the shoulders: from pose row `top` at the neck to
    `bottom`, both falling a few rows toward each arm."""

    def inside(x, y):
        drop = 3.0 * ((x - FIG_CX) / 14.0) ** 2
        return 2 <= x < 30 and top + drop <= y < bottom + drop

    return inside


def bare_arms(g, zones, wraps):
    """Bare arms over the body's sleeves in `zones`, each shaded down its east
    side, bandaged across the pose rows in `wraps`."""
    for x0, y0, x1, y1 in zones:
        region(g, box(x0, y0, x1, y1), SKIN)
        region(g, box(x1 - 1, y0, x1, y1), SKIN_SH)
        for wy in wraps:
            region(g, box(x0, wy, x1, wy + 1), OFFWHITE)
            region(g, box(x0, wy + 1, x1, wy + 2), OFFWHITE_SH)


def quiver(g, top, bottom, width=4.0):
    """A leather quiver from `top` to `bottom` (pose grid), shaded down its
    east side, its arrows' fletching, in the agent's hair colour, standing out
    of its mouth."""
    (tx, ty), (bx, by) = top, bottom
    length = math.hypot(bx - tx, by - ty)
    ux, uy = (bx - tx) / length, (by - ty) / length
    for y in range(LAYER_H):
        for x in range(1, FIG_W - 1):
            px, py = x + 0.5 - tx, y - LIFT + 0.5 - ty
            u, v = px * ux + py * uy, -px * uy + py * ux
            if -3.5 <= u < 0 and abs(v) <= width / 2 - 0.5:
                g[y][x] = HAIR_LT if (x + y) % 3 else HAIR
            elif 0 <= u < 1.2 and abs(v) <= width / 2:
                g[y][x] = LEATHER_SH
            elif 0 <= u <= length and abs(v) <= width / 2:
                g[y][x] = LEATHER_SH if v < -(width / 2 - 1.2) else LEATHER


def strap(g, a, b, key=LEATHER_SH):
    """A strap two pixels wide from `a` to `b` on the pose grid."""
    (x0, y0), (x1, y1) = a, b
    n = int(max(abs(x1 - x0), abs(y1 - y0))) * 2 + 1
    for i in range(n + 1):
        x = round(x0 + (x1 - x0) * i / n)
        y = round(y0 + (y1 - y0) * i / n)
        put(g, x, y + LIFT, key)
        put(g, x + 1, y + LIFT, key)


def hood(g, crown, opening):
    """A hood: the cloth inside `crown` but its face `opening`."""
    region(g, lambda x, y: crown(x, y) and not opening(x, y), SHIRT)


def robe(top, bottom, x0, x1, flare):
    """A robe's skirt from pose row `top` to `bottom`, columns `x0`..`x1` at its
    top, widening a column each side every `flare` rows."""
    return lambda x, y: (
        top <= y < bottom and x0 - (y - top) / flare <= x < x1 + (y - top) / flare
    )


def style_mage():
    """A mage: a deep hood lined and trimmed in the agent's hair colour, its
    shade on the brow, a mantle with wide sleeves over the shoulders, the robe
    falling to the ankles, its stole in the hair colour too; seen from behind,
    the robe whole."""
    b = layer()
    region(b, in_oval(FIG_CX, 12.5, 12.6, 13.4), SHIRT)
    cloth(b)
    opening = in_oval(FIG_CX, 18.4, 8.4, 8.8)
    f = layer()
    hood(f, in_oval(FIG_CX, 13.5, 12.2, 13.6), opening)
    region(f, box(3, 25, 29, 29), SHIRT)  # the mantle over the shoulders
    region(f, box(3, 29, 9, 33), SHIRT)  # its sleeves
    region(f, box(23, 29, 29, 33), SHIRT)
    region(f, robe(38, 45, 8, 24, 3), SHIRT)
    clear(f, (MUG_ZONE, *HAND_ZONES))
    cloth(f)
    lining(f, opening)
    hood_shadow(f, opening, (9, 16))
    region(f, box(15, 27, 17, 29), GOLD)  # the mantle's clasp
    region(f, box(15, 38, 17, 44), HAIR)  # the robe's stole, in the accent

    back = layer()
    region(back, in_oval(FIG_CX, 12.5, 12.0, 13.4), SHIRT)
    region(back, box(4, 24, 28, 34), SHIRT)
    region(back, robe(34, 45, 8, 24, 4), SHIRT)
    cloth(back)
    for x, y0 in ((11, 27), (16, 30), (21, 27)):  # the robe's folds
        region(back, box(x, y0, x + 1, 44), SHIRT_SH)
    region(back, box(7, 24, 25, 25), HAIR)  # the hood's trim

    sb = layer()
    region(sb, in_oval(11.5, 14.0, 11.0, 12.0), SHIRT)
    cloth(sb, east=99)
    side_opening = in_oval(23.5, 18.0, 5.4, 8.6)
    so = layer()
    hood(so, in_oval(13.5, 13.5, 12.0, 12.4), side_opening)
    region(so, box(5, 24, 18, 37), SHIRT)  # the mantle down the back
    region(so, box(15, 29, 24, 34), SHIRT)  # the near sleeve, reaching
    region(so, box(8, 36, 28, 40), SHIRT)  # the robe over the lap
    cloth(so, east=99)
    lining(so, side_opening)
    hood_shadow(so, side_opening, (9, 15))

    c = layer()
    region(c, box(3, 18, 29, 31), SHIRT)  # mantle and sleeves, across the back
    region(c, in_oval(CROWN_CX, CROWN_CY, CROWN_R + 1.2, CROWN_R + 1.2), SHIRT)
    region(c, box(1, 20, 6, 24), T)  # the hands stay the body's
    region(c, box(27, 20, 31, 24), T)
    cloth(c)
    hooded = in_oval(CROWN_CX, CROWN_CY, CROWN_R + 1.2, CROWN_R + 1.2)
    for x in (13, 19):  # the hood's seams, crown to brow
        region(c, box(x, 9, x + 1, 18), SHIRT_SH)
    region(c, lambda x, y: box(4, 18, 28, 19)(x, y) and not hooded(x, y), HAIR)
    return {"front": (b, f), "back": back, "side": (sb, so), "crown": c, "ears": False}


def style_ranger():
    """A ranger: a close hood over a fringe of the agent's hair, a short cape,
    leather bracers, a quiver strapped across the chest, its fletching over
    the shoulder; seen from behind, the quiver on the cape."""
    b = layer()
    quiver(b, (26.5, 4.0), (22.0, 27.0))
    region(b, in_oval(FIG_CX, 13.5, 11.8, 11.6), SHIRT)
    cloth(b)
    opening = in_oval(FIG_CX, 17.8, 8.8, 9.0)
    f = layer()
    hood(f, in_oval(FIG_CX, 14.0, 11.6, 11.8), opening)
    region(f, box(4, 25, 28, 29), SHIRT)  # the cape's collar over the shoulders
    cloth(f)
    region(f, box(3, 29, 9, 33), LEATHER)  # the bracers
    region(f, box(23, 29, 29, 33), LEATHER)
    region(f, box(3, 31, 9, 32), LEATHER_SH)
    region(f, box(23, 31, 29, 32), LEATHER_SH)
    strap(f, (22, 25), (8, 30))  # above the mug a front pose may hold
    clear(f, HAND_ZONES)
    locks = [(10.5, 13.5, 2.2), (13.5, 14.5, 2.2), (17.0, 13.5, 2.4), (20.5, 14.0, 2.0)]
    fringe_locks(f, locks, 9, LIFT)
    rim_light(f, lit_top=False)

    back = layer()
    region(back, in_oval(FIG_CX, 13.5, 11.4, 11.6), SHIRT)
    region(back, robe(24, 37, 5, 27, 6), SHIRT)
    cloth(back)
    quiver(back, (22.0, 4.5), (12.0, 31.0), 5.0)

    sb = layer()
    quiver(sb, (5.0, 6.0), (9.0, 30.0))
    region(sb, in_oval(12.0, 13.5, 10.6, 11.4), SHIRT)
    cloth(sb, east=99)
    side_opening = in_oval(23.0, 17.8, 5.6, 8.4)
    so = layer()
    hood(so, in_oval(13.5, 13.0, 11.4, 11.8), side_opening)
    region(so, box(5, 23, 13, 35), SHIRT)  # the cape down the back
    cloth(so, east=99)
    region(so, box(16, 30, 23, 34), LEATHER)  # the near bracer
    strap(so, (18, 27), (12, 35))
    fringe_locks(so, [(19.5, 13.5, 2.0), (22.5, 13.0, 2.0)], 9, LIFT)
    rim_light(so, lit_top=False)

    c = layer()
    region(c, box(4, 18, 28, 29), SHIRT)  # the cape across the shoulders
    cloth(c)
    quiver(c, (25.0, 9.0), (7.0, 30.0), 5.0)
    region(c, in_oval(CROWN_CX, CROWN_CY, CROWN_R + 0.8, CROWN_R + 0.8), SHIRT)
    cloth(c)
    return {"front": (b, f), "back": back, "side": (sb, so), "crown": c, "ears": False}


def style_berserker():
    """A berserker: a wild mane and a beard in the agent's hair colour, a pelt
    over the shoulders, bare arms bound in bandages."""
    mane = style_messy()
    b = [row[:] for row in mane["front"][0]]
    f = [row[:] for row in mane["front"][1]]
    bare_arms(f, ((3, 28, 9, 33), (23, 28, 29, 33)), (31,))
    fur(f, shoulders(23, 27))
    clear(f, HAND_ZONES)
    beard = layer()
    region(beard, lambda x, y: in_oval(FIG_CX, 21.0, 8.4, 7.0)(x, y) and y > 22.5, HAIR)
    region(beard, box(14, 22, 18, 24), T)  # the mouth stays clear
    rim_light(beard, lit_top=False)
    paste(f, beard)

    back = [row[:] for row in mane["back"]]
    bare_arms(back, ((3, 28, 8, 35), (24, 28, 29, 35)), (32,))
    fur(back, shoulders(22, 29))

    sb = [row[:] for row in mane["side"][0]]
    so = [row[:] for row in mane["side"][1]]
    side_beard = layer()
    region(
        side_beard, lambda x, y: in_oval(21.0, 21.5, 5.4, 5.4)(x, y) and y > 22.5, HAIR
    )
    rim_light(side_beard, lit_top=False)
    paste(so, side_beard)
    fur(so, box(5, 24, 17, 30))
    bare_arms(so, ((17, 30, 24, 34),), (31,))

    c = layer()
    fur(c, box(3, 18, 29, 25))
    bare_arms(c, ((1, 24, 10, 31), (22, 24, 30, 31), (10, 26, 22, 31)), (27,))
    region(c, box(1, 20, 6, 24), T)  # the hands stay the body's
    region(c, box(27, 20, 31, 24), T)
    paste(c, mane["crown"])
    return {"front": (b, f), "back": back, "side": (sb, so), "crown": c, "ears": False}


def tail(x0, y0, x1, y1, tie_y):
    """A ponytail's tail, lit on its own, with its tie."""
    t = layer()
    lock(t, x0, y0 + LIFT, x1, y1 + LIFT, 5, 2)
    rim_light(
        t,
        [
            (round(x0 + (x1 - x0) * f), round(y0 + (y1 - y0) * f) + LIFT)
            for f in (0.4, 0.7)
        ],
    )
    for x in range(int(min(x0, x1)) - 2, int(max(x0, x1)) + 3):
        if 0 <= x < FIG_W and t[int(tie_y) + LIFT][x] != T:
            t[int(tie_y) + LIFT][x] = HAIR_SH
    return t


# Per-agent hairstyles, by the name a pack registers them under: each an
# adventurer's class, so every agent is one of the four.
HAIRSTYLES = {
    "knight": style_knight_helm,
    "mage": style_mage,
    "ranger": style_ranger,
    "berserker": style_berserker,
}
# The modern styles, written to no sprite: kept as parts for the classes (the
# berserker's mane is `style_messy`'s) and for classes to come.
UNWORN_HAIRSTYLES = {
    "mop": style_mop,
    "messy": style_messy,
    "side_part": style_side_part,
    "long": style_long,
    "bun": style_bun,
    "crop": style_crop,
    "curls": style_curls,
    "shaggy": style_shaggy,
    "ponytail": style_ponytail,
}


# ---- bodies ------------------------------------------------------------------------
# Drawn on the pose grid, shifted down `dy` rows onto a taller canvas (a hair
# layer's).
def mitt(g, x, y, wrist_west=False):
    """A hand: a skin block, shaded along its foot, rounded at the bottom but
    for a corner its wrist joins: rounded there, it leaves a notch against the
    sleeve that the outline closes over a pinhole."""
    rect(g, x, y, x + S, y + S, SKIN)
    rect(g, x, y + S - 1, x + S, y + S, SKIN_SH)
    if not wrist_west:
        g[y + S - 1][x] = T
    g[y + S - 1][x + S - 1] = T


def ears_front(g, dy):
    for x, inner in ((5, 6), (25, 25)):
        rect(g, x, FACE_TOP + 5 + dy, x + 2, FACE_TOP + 9 + dy, SKIN)
        rect(g, inner, FACE_TOP + 6 + dy, inner + 1, FACE_TOP + 8 + dy, SKIN_SH)


def ears_back(g, dy):
    for x in (5, 25):
        rect(g, x, 17 + dy, x + 2, 21 + dy, SKIN)
        rect(
            g,
            x + (1 if x < 16 else 0),
            18 + dy,
            x + (2 if x < 16 else 1),
            20 + dy,
            SKIN_SH,
        )


def ear_side(g, dy):
    rect(g, 12, 16 + dy, 15, 20 + dy, SKIN)
    rect(g, 13, 17 + dy, 14, 19 + dy, SKIN_SH)


def face_front(g, dy):
    """The face: round, shaded east and along the chin, two tall eyes and a
    small mouth."""
    for y in range(FACE_TOP - 2, FACE_BOTTOM):
        for x in range(7, 25):
            nx = (x + 0.5 - FIG_CX) / 9.0
            ny = max(0.0, (y + 0.5 - (FACE_TOP + 6)) / (FACE_BOTTOM - FACE_TOP - 6))
            if nx * nx + ny * ny <= 1.0:
                g[y + dy][x] = SKIN_SH if (x >= 21 or y >= FACE_BOTTOM - 2) else SKIN
    eye_y = FACE_TOP + 5 + dy
    rect(g, 11, eye_y, 13, eye_y + 4, EYE)
    rect(g, 19, eye_y, 21, eye_y + 4, EYE)
    rect(g, 15, FACE_BOTTOM - 4 + dy, 17, FACE_BOTTOM - 3 + dy, SKIN_DK)


def nape(g, dy):
    """The back of the head under the hair: its round and the neck."""
    ellipse(g, FIG_CX, 17.0 + dy, 9.0, 8.6, SKIN_SH)
    rect(g, 12, 23 + dy, 20, 27 + dy, SKIN_DK)
    rect(g, 13, 23 + dy, 19, 26 + dy, SKIN_SH)


def side_face(g, dy):
    """The profile, facing east: brow, a nose bump, the mouth, a chin rounding
    back to the jaw, one eye."""
    rows = {
        10: (15, 24),
        11: (14, 25),
        12: (13, 25),
        13: (13, 25),
        14: (13, 25),
        15: (13, 26),
        16: (13, 27),
        17: (13, 27),
        18: (13, 26),
        19: (13, 25),
        20: (13, 25),
        21: (13, 25),
        22: (14, 25),
        23: (15, 24),
        24: (16, 23),
        25: (17, 21),
    }
    for y, (x0, x1) in rows.items():
        for x in range(x0, x1):
            g[y + dy][x] = SKIN_SH if (y >= 24 or x < 15) else SKIN
    rect(g, 21, 15 + dy, 23, 19 + dy, EYE)
    rect(g, 23, 22 + dy, 25, 23 + dy, SKIN_DK)
    rect(g, 13, 24 + dy, 19, 28 + dy, SKIN_DK)  # the neck


def neck_shadow(g, dy):
    """The mail collar's shadow under the chin, where the shoulders begin."""
    rect(g, 12, SHOULDER_Y + dy, 20, SHOULDER_Y + 1 + dy, IRON_DK)


# ---- the knight's garb: iron mail under a cloth tabard in the agent's colour
# (`B` and its ramp), a leather belt, the agent's leggings (`P`), leather boots.
# The tabard's columns, half-open: the mail shows at its sides and on the arms.
TABARD_X0, TABARD_X1 = 9, 23
# A standing tabard's foot, over the thighs; a seated one ends on the seat.
TABARD_HEM = 41


def mail(g, x0, y0, x1, y1, dy, shade=False):
    """Mail from (x0, y0) to (x1, y1) on the pose grid: its rings a checker of
    two iron shades, one shade darker turned from the light. The checker is
    the pose grid's, not the canvas's, so a bobbing walk's rings ride with the
    body instead of shimmering."""
    ring, gap = (IRON_SH, IRON_DK) if shade else (IRON, IRON_SH)
    for y in range(y0, y1):
        for x in range(x0, x1):
            put(g, x, y + dy, gap if (x + y) % 2 else ring)


def belt(g, y, dy, x0=6, x1=26, buckle=True):
    """A leather belt two rows deep from row `y`, its lower edge shaded, an
    iron buckle at the front."""
    rect(g, x0, y + dy, x1, y + 2 + dy, LEATHER)
    rect(g, x0, y + 1 + dy, x1, y + 2 + dy, LEATHER_SH)
    if buckle:
        rect(g, 14, y + dy, 18, y + 2 + dy, IRON_LT)
        rect(g, 15, y + dy, 17, y + 1 + dy, IRON_SH)


def tabard(g, dy, bottom, back=False, sleeves=True, hem=None):
    """Mail from the shoulders to `bottom`, its sleeves hanging at the sides,
    and over it the tabard to `hem` (`bottom` unless it hangs past the belt),
    lit on the west and trimmed along its foot, belted just above `bottom`;
    the mail collar's shadow, and in front the tabard's neck opening."""
    hem = bottom if hem is None else hem
    mail(g, 9, SHOULDER_Y, 23, SHOULDER_Y + 1, dy)
    mail(g, 6, SHOULDER_Y + 1, 26, bottom, dy)
    if sleeves:
        mail(g, 5, SHOULDER_Y + 2, TABARD_X0, CUFF_Y, dy)
        mail(g, TABARD_X1, SHOULDER_Y + 2, 27, CUFF_Y, dy, shade=True)
    rect(g, TABARD_X0, SHOULDER_Y + 1 + dy, TABARD_X1, hem + dy, SHIRT)
    rect(g, TABARD_X1 - 3, SHOULDER_Y + 1 + dy, TABARD_X1, hem + dy, SHIRT_SH)
    rect(g, TABARD_X0, SHOULDER_Y + 1 + dy, TABARD_X0 + 1, hem + dy, SHIRT_LT)
    rect(g, TABARD_X0, hem - 1 + dy, TABARD_X1, hem + dy, SHIRT_OUT)
    neck_shadow(g, dy)
    if not back:
        mail(g, 13, SHOULDER_Y + 1, 19, SHOULDER_Y + 2, dy, shade=True)
    belt(g, min(bottom, BELT_Y) - 2, dy, buckle=not back)


def hands_level(g, dy):
    for x in (4, 24):
        mitt(g, x, SEAT_Y + dy)


def hands_typing(frame):
    """Both hands low on the keys, one pressing lower than the other, swapping
    each frame as the base frames do."""

    def draw(g, dy):
        up, down = (4, 24) if frame == 0 else (24, 4)
        mail(g, down, SEAT_Y, down + S, SEAT_Y + 2, dy, shade=True)
        mitt(g, up, SEAT_Y + dy)
        mitt(g, down, SEAT_Y + 2 + dy)

    return draw


def elbows_typing(frame):
    """Typing seen from behind, where the chair's arm pads hide most of the
    hands' press: the reaching arm's elbow juts out past the chair, swapping
    sides each frame as the hands do."""
    hands = hands_typing(frame)

    def draw(g, dy):
        hands(g, dy)
        west = frame == 0
        x0 = 2 if west else FIG_W - 5
        mail(g, x0, SHOULDER_Y + 3, x0 + 3, CUFF_Y, dy, shade=not west)

    return draw


# ---- the walk -------------------------------------------------------------------
# One gait drives both densities, each drawn in its own figure's proportions: the
# pets' 4x was drawn to scale down to their 1x, the people's chibi was not, so the
# table is shared and the shapes are per density.
class Foot(NamedTuple):
    lift: int  # art pixels clear of the ground
    out: int  # pixels stepped outward
    toe: bool  # heel up, standing on its toe


PLANT, LEAD, HEEL = Foot(0, 0, False), Foot(0, 1, False), Foot(1, 0, True)


def swinging(lift):
    return Foot(lift, 0, False)


class Step(NamedTuple):
    phase: str
    bob: int  # art rows the body sinks
    west: Foot
    east: Foot
    swing: int  # the west hand's, forward positive; the east hand swings opposite


# The struck foot holds the ground through the next three frames while the other
# swings past it, so no foot slides back while it is planted.
WALK_CYCLE = [
    Step("the east foot strikes, the west trails on its toe", 1, HEEL, LEAD, 2),
    Step("the west foot lifts", 0, swinging(1), PLANT, 1),
    Step("the west foot passes", 0, swinging(2), PLANT, 0),
    Step("the west foot reaches", 0, swinging(1), PLANT, -1),
    Step("the west foot strikes, the east trails on its toe", 1, LEAD, HEEL, -2),
    Step("the east foot lifts", 0, PLANT, swinging(1), -1),
    Step("the east foot passes", 0, PLANT, swinging(2), 0),
    Step("the east foot reaches", 0, PLANT, swinging(1), 1),
]
STAND = Step("standing", 0, PLANT, PLANT, 0)


def legs(g, dy, step, view):
    """Hips, two legs in leggings and leather boots, each turned down in a cuff:
    a lifted foot rides up its leg with the ground showing under it, the
    leading foot plants a pixel outward, a heel-up foot shows only its toe
    (front) or its sole (back)."""
    rect(g, 8, BELT_Y + dy, 24, BELT_Y + 2 + dy, PANTS)
    for (side, x0), foot in zip(((-1, 8), (1, 17)), (step.west, step.east)):
        x0 += side * foot.out
        ground = STANDING_ROWS * S - foot.lift
        top = ground - (2 if foot.toe else 3)
        rect(g, x0, BELT_Y + 2 + dy, x0 + 7, top, PANTS)
        rect(g, x0 + 5, BELT_Y + dy, x0 + 7, top, PANTS_SH)
        rect(g, x0 - 1, top, x0 + 7, ground, SHOE)
        rect(g, x0, top - 1, x0 + 7, top, LEATHER)
        if view == "front":
            rect(g, x0, top, x0 + 6, top + 1, SHOE_HI)
        elif foot.toe:
            rect(g, x0, ground - 1, x0 + 6, ground, SHOE_HI)


def arms_swinging(g, dy, swing, mug_east=False):
    """Sleeves down the sides; a hand swinging forward hangs lower and comes a
    pixel in toward the body, one swinging back rises and goes a pixel out. A
    mug held east keeps that arm still."""
    for (side, x0), sw in zip(((-1, 4), (1, 24)), (swing, -swing)):
        if side > 0 and mug_east:
            continue
        x0 -= side * ((sw > 0) - (sw < 0))
        mail(
            g,
            x0 + (1 if side < 0 else 0),
            SHOULDER_Y + 2,
            x0 + (4 if side < 0 else 3),
            CUFF_Y + sw,
            dy,
            shade=side > 0,
        )
        mitt(g, x0, CUFF_Y + sw + dy)
    if mug_east:
        mail(g, 24, SHOULDER_Y + 2, 27, 32, dy, shade=True)
        mail(g, 21, 29, 26, 33, dy, shade=True)
        mug(g, 16, 27 + dy)
        mitt(g, 21, 29 + dy)


def mug(g, x, y):
    """A mug with coffee showing, shaded east, its handle east, steam rising."""
    rect(g, x, y, x + 6, y + 7, MUG)
    rect(g, x + 4, y, x + 6, y + 7, MUG_SH)
    rect(g, x + 1, y, x + 5, y + 1, COFFEE)
    rect(g, x + 6, y + 2, x + 8, y + 5, MUG_SH)
    g[y + 3][x + 6] = T
    for sx, sy in ((2, -2), (3, -3), (2, -4)):
        g[y + sy][x + sx] = OFFWHITE


def arms_mug_both(g, dy):
    for x0 in (5, 25):  # upper arms bent in at the elbow
        mail(g, x0, SHOULDER_Y + 2, x0 + 3, 32, dy, shade=x0 > 16)
    mail(g, 7, 31, 12, 35, dy)
    mail(g, 20, 31, 25, 35, dy, shade=True)
    mug(g, 13, 29 + dy)
    mitt(g, 10, 31 + dy)
    mitt(g, 19, 31 + dy)


def side_body(g, dy):
    """Seated in profile: a narrow torso in its tabard, belted, the near arm's
    mail reaching forward, the lap to the knee."""
    rect(g, 9, 27 + dy, 22, SEAT_Y + dy, SHIRT)
    rect(g, 13, 27 + dy, 19, 28 + dy, IRON_DK)  # the mail collar
    rect(g, 9, 27 + dy, 11, SEAT_Y + dy, SHIRT_LT)
    rect(g, 19, 28 + dy, 22, SEAT_Y + dy, SHIRT_SH)
    belt(g, SEAT_Y - 2, dy, 9, 22, buckle=False)
    mail(g, 12, 28, 17, 32, dy, shade=True)
    mail(g, 16, 30, 24, 34, dy)
    rect(g, 16, 33 + dy, 24, 34 + dy, IRON_SH)
    mitt(g, 24, 30 + dy, wrist_west=True)
    rect(g, 9, SEAT_Y + dy, 28, SEATED_ROWS * S + dy, PANTS)
    rect(g, 9, SEAT_Y + dy, 28, SEAT_Y + 1 + dy, PANTS_LT)
    rect(g, 25, SEAT_Y + 1 + dy, 28, SEATED_ROWS * S + dy, PANTS_SH)


def asleep_body(g, dy, lean):
    """Face down on folded arms: the tabard's shoulders rising behind the head,
    mailed forearms crossed under it on the desk, hands tucked at the elbows,
    the torso behind the arms, the thighs at the chair's edge."""
    mail(g, 4 + lean, 18, 28 + lean, 26, dy)
    rect(g, 7 + lean, 18 + dy, 25 + lean, 26 + dy, SHIRT)
    rect(g, 21 + lean, 18 + dy, 25 + lean, 26 + dy, SHIRT_SH)
    rect(g, 7 + lean, 18 + dy, 8 + lean, 26 + dy, SHIRT_LT)
    mail(g, 1, 23, 10, 31, dy)
    mail(g, 22, 23, 31, 31, dy, shade=True)
    mail(g, 8, 26, 24, 31, dy)
    rect(g, 8, 30 + dy, 24, 31 + dy, IRON_DK)
    rect(g, 15, 26 + dy, 17, 31 + dy, IRON_DK)
    mitt(g, 1, 20 + dy)
    mitt(g, 27, 20 + dy)
    mail(g, 4, 31, 28, 36, dy)
    rect(g, 7, 31 + dy, 25, 36 + dy, SHIRT)
    rect(g, 21, 31 + dy, 25, 36 + dy, SHIRT_SH)
    rect(g, 1, 34 + dy, 9, 38 + dy, PANTS)
    rect(g, 23, 34 + dy, 31, 38 + dy, PANTS_SH)


# ---- poses -------------------------------------------------------------------------
def seated_front(hands):
    return lambda g, dy: (tabard(g, dy, SEAT_Y), hands(g, dy))


def seated_rear(hands):
    return lambda g, dy: (tabard(g, dy, SEAT_Y, back=True), hands(g, dy))


def standing_body(view, step=STAND, arms=None, mug_east=False):
    """On its feet at `step` of the gait, its arms swinging with it unless `arms`
    holds them."""

    def draw(g, dy):
        legs(g, dy, step, view)
        tabard(g, dy, BELT_Y, back=view == "back", sleeves=False, hem=TABARD_HEM)
        if arms:
            arms(g, dy)
        else:
            arms_swinging(g, dy, step.swing, mug_east)

    return draw


def couch_back(g, dy):
    """The tabard's back square over the seat back, mail on the shoulders and
    arms."""
    top, foot = SHOULDER_Y + 1, COUCH_ROWS * S
    mail(g, 9, SHOULDER_Y, 23, top, dy)
    mail(g, 5, top, TABARD_X0, foot, dy)
    mail(g, TABARD_X1, top, 27, foot, dy, shade=True)
    rect(g, TABARD_X0, top + dy, TABARD_X1, foot + dy, SHIRT)
    rect(g, TABARD_X1 - 3, top + dy, TABARD_X1, foot + dy, SHIRT_SH)
    rect(g, TABARD_X0, top + dy, TABARD_X0 + 1, foot + dy, SHIRT_LT)
    neck_shadow(g, dy)


# name: (height in logical rows, view, body, the sprite's header).
POSES = {
    "seated": (
        SEATED_ROWS,
        "front",
        seated_front(hands_level),
        "Front view at rest, both hands level.",
    ),
    "typing_0": (
        TYPING_ROWS,
        "front",
        seated_front(hands_typing(0)),
        "Front view, typing, frame 0: the west hand level, the east pressing.",
    ),
    "typing_1": (
        TYPING_ROWS,
        "front",
        seated_front(hands_typing(1)),
        "Front view, typing, frame 1: the hands swap.",
    ),
    "seated_back": (
        SEATED_ROWS,
        "back",
        seated_rear(hands_level),
        "Back view at rest, both hands level.",
    ),
    "typing_back_0": (
        TYPING_ROWS,
        "back",
        seated_rear(elbows_typing(0)),
        "Back view, typing, frame 0.",
    ),
    "typing_back_1": (
        TYPING_ROWS,
        "back",
        seated_rear(elbows_typing(1)),
        "Back view, typing, frame 1.",
    ),
    "back_couch": (
        COUCH_ROWS,
        "back",
        couch_back,
        "On the couch, facing the windows: shoulders square over the seat back.",
    ),
    "standing": (
        STANDING_ROWS,
        "front",
        standing_body("front"),
        "Standing: arms at the sides.",
    ),
    "holding_coffee": (
        STANDING_ROWS,
        "front",
        standing_body("front", arms=arms_mug_both),
        "Standing with a steaming mug in both hands.",
    ),
    "side_seated": (
        SEATED_ROWS,
        "side",
        lambda g, dy: side_body(g, dy),
        "Seated in profile, facing east, one arm reaching forward.",
    ),
    "seated_sleeping": (
        SEATED_ROWS,
        "crown",
        lambda g, dy: asleep_body(g, dy, 0),
        "Asleep face-down on folded arms.",
    ),
    "seated_sleeping_alt": (
        SEATED_ROWS,
        "crown",
        lambda g, dy: asleep_body(g, dy, 3),
        "Dozed off, slumped east.",
    ),
}
# The walks: name -> (view, holds a mug east, title).
WALKS = {
    "walking": ("front", False, "Walking"),
    "walking_back": ("back", False, "Walking away"),
    "walking_coffee": ("front", True, "Walking with a mug"),
}
POSES |= {
    f"{name}_{i}": (
        STANDING_ROWS,
        view,
        standing_body(view, step, mug_east=mug),
        f"{title}, frame {i}: {step.phase}.",
    )
    for name, (view, mug, title) in WALKS.items()
    for i, step in enumerate(WALK_CYCLE)
}

# The typing loop's length: the hands swap once a frame.
TYPING_FRAMES = 2


# ---- the attacks: what a working adventurer does in place of typing ---------------
# Drawn in the body frames, so a class layer dresses them as it dresses the
# typist; nothing reaches the canvas's edge columns, which the outline needs.
# A seat facing the viewer shows only what rises over its lair, so a front
# view's blow lands high; a back view's flies over the head, at the foe.
#
# The knight swings a sword. Per frame, on the pose grid: the sword hand's
# top-left, the blade's tip, the slash trailing the cut (empty for none) and
# where the blow lands in sparks (None for none). Frame 0 is the guard a
# resting beat shows (`typing_frame`). A seat facing the viewer shows only
# what rises over its lair, so its cut and its hit are drawn high.
class Swing(NamedTuple):
    hand: tuple
    tip: tuple
    slash: tuple
    sparks: tuple | None
    title: str


STRIKE_FRONT = [
    Swing((24, 25), (27, 3), (), None, "on guard, the blade upright beside the head"),
    Swing((25, 9), (3, 2), (), None, "the blade raised back over the head"),
    Swing(
        (17, 27),
        (14, 43),
        ((28, 1), (30, 12), (28, 23), (20, 30)),
        None,
        "the cut, down at the foe, a slash trailing it",
    ),
    Swing((20, 27), (16, 43), (), (13, 31), "the blow landing in sparks"),
]
STRIKE_BACK = [
    Swing((24, 28), (27, 5), (), None, "on guard, the blade upright beside the head"),
    Swing((24, 9), (29, 27), (), None, "the blade cocked back over the shoulder"),
    Swing(
        (24, 18),
        (19, 6),
        ((30, 4), (24, 0), (12, 0), (3, 5)),
        None,
        "the cut, over the head at the foe, a slash trailing it",
    ),
    Swing((24, 20), (18, 8), (), (8, 2), "the blow landing in sparks beyond the head"),
]


def sword(g, hand, tip, dy):
    """The sword in the fist at `hand`: an iron blade lit along one edge from
    its crossguard to `tip`, the guard across it and a leather grip in the
    fist."""
    hx, hy = hand[0] + S / 2, hand[1] + S / 2 + dy
    tx, ty = tip[0] + 0.5, tip[1] + 0.5 + dy
    length = math.hypot(tx - hx, ty - hy)
    ux, uy = (tx - hx) / length, (ty - hy) / length
    gx, gy = hx + ux * 3, hy + uy * 3
    stem(g, [(gx, gy), (tx, ty)], 1.0, IRON)
    stem(g, [(gx + uy * 0.8, gy - ux * 0.8), (tx, ty)], 0.4, IRON_LT)
    stem(g, [(gx - uy * 3, gy + ux * 3), (gx + uy * 3, gy - ux * 3)], 0.7, IRON_SH)
    stem(g, [(hx - ux, hy - uy), (gx, gy)], 0.7, LEATHER)


def slash(g, pts, dy):
    """The cut's trail: a pale arc through `pts`, brightest at its head."""
    shifted = [(x + 0.5, y + 0.5 + dy) for x, y in pts]
    stem(g, shifted, 0.5, IRON_HI)
    stem(g, shifted[-2:], 0.6, WHITE)


def sparks(g, x, y, dy):
    """A blow's sparks bursting from (x, y): a white heart, gold rays."""
    rect(g, x, y + dy, x + 2, y + 2 + dy, WHITE)
    for ax, ay in (
        (-2, -2),
        (3, -2),
        (-2, 3),
        (3, 3),
        (0, -3),
        (0, 4),
        (-3, 0),
        (4, 1),
    ):
        put(g, x + ax, y + ay + dy, GOLD)


# Where each arm's sleeve leaves the shoulder, on the pose grid.
WEST_SHOULDER, EAST_SHOULDER = (6.5, SHOULDER_Y + 3.5), (25.5, SHOULDER_Y + 3.5)


def mail_arm(g, shoulder, hand, dy):
    """A mailed sleeve from `shoulder` (on the pose grid) to the fist at
    `hand`, its rings the pose grid's checker as `mail` lays them, in the
    shade an arm turned from the light takes."""
    sleeve = canvas(len(g[0]), len(g))
    sx, sy = shoulder
    stem(sleeve, [(sx, sy + dy), (hand[0] + 2, hand[1] + 2)], 1.6, IRON)
    for y, row in enumerate(sleeve):
        for x, k in enumerate(row):
            if k != T:
                mail(g, x, y - dy, x + 1, y - dy + 1, dy, shade=True)


def armed(view, hands, weapon, behind_head=False):
    """A seated adventurer's frame with its fists at `hands` (west, east),
    each a fist's top-left on the pose grid, or None for the west hand
    resting on its knee, and `weapon(g, dy)` drawn between the sleeves and
    the fists; `behind_head` passes the sleeves and the weapon behind the
    head, which a raised arm or a shouldered haft would otherwise draw
    across the face."""

    def draw(g, dy):
        tabard(g, dy, SEAT_Y, back=view == "back", sleeves=False)
        west, east = hands
        if west is None:
            mail(g, 5, SHOULDER_Y + 2, TABARD_X0, CUFF_Y, dy)
            mitt(g, 4, SEAT_Y + dy)
        else:
            mail_arm(g, WEST_SHOULDER, (west[0], west[1] + dy), dy)
        mail_arm(g, EAST_SHOULDER, (east[0], east[1] + dy), dy)
        weapon(g, dy)
        if behind_head:
            bald_head(view, g, dy)
        for fist in hands:
            if fist is not None:
                mitt(g, fist[0], fist[1] + dy)

    return draw


def striking(view, swing):
    """A seated swordsman's frame: the off hand on its knee, the sword in the
    east fist at `swing.hand`, the slash and the sparks over all."""

    def weapon(g, dy):
        sword(g, swing.hand, swing.tip, dy)
        if swing.slash:
            slash(g, swing.slash, dy)
        if swing.sparks:
            sparks(g, *swing.sparks, dy)

    return armed(view, (None, swing.hand), weapon)


# The mage thrusts a staff and looses a spell: per frame, its east fist, the
# staff's foot and head, and the spell at the head (0 none, 1 gathering,
# 2 the flash and its bolt, 3 the afterglow).
class Cast(NamedTuple):
    hand: tuple
    foot: tuple
    head: tuple
    spell: int


CAST = {
    "front": [
        Cast((25, 22), (28, 34), (27, 3), 0),
        Cast((25, 12), (28, 26), (27, 2), 1),
        Cast((25, 20), (28, 33), (27, 3), 2),
        Cast((25, 22), (28, 34), (27, 3), 3),
    ],
    "back": [
        Cast((25, 24), (28, 36), (27, 4), 0),
        Cast((25, 14), (28, 28), (27, 2), 1),
        Cast((25, 22), (28, 34), (27, 3), 2),
        Cast((25, 24), (28, 36), (27, 4), 3),
    ],
}
# Where the flash's bolt strikes, per view: down the staff's side at the foe
# before a seat facing the viewer; a back-turned seat's foe is beyond the
# hood, so its flash looses no bolt anyone would see.
BOLT_TO = {"front": (30, 32), "back": None}


def staff(g, foot, head, dy):
    """A wooden staff from `foot` to `head`, lit along one side, an orb of
    pale crystal set at its head."""
    (fx, fy), (hx, hy) = foot, head
    stem(g, [(fx + 0.5, fy + 0.5 + dy), (hx + 0.5, hy + 0.5 + dy)], 0.8, WOOD)
    stem(g, [(fx, fy + dy), (hx, hy + dy)], 0.3, WOOD_LT)
    disc(g, hx + 0.5, hy + 0.5 + dy, 2.2, CYAN)
    put(g, hx, hy - 1 + dy, WHITE)


def spell(g, head, phase, bolt_to, dy):
    """The spell at the staff's `head`: motes gathering, a flash ringed in
    blue with its bolt jagging to `bolt_to`, or a fading afterglow."""
    hx, hy = head[0] + 0.5, head[1] + 0.5 + dy
    if phase == 1:
        for ax, ay in ((-3, -2), (3, -1), (-2, 3), (2, 3)):
            put(g, int(hx + ax), int(hy + ay), CYAN)
    elif phase == 2:
        if bolt_to is not None:
            bx, by = bolt_to
            pts = [(hx, hy)]
            for t in (0.3, 0.6, 1.0):
                jag = 1 if len(pts) % 2 else -1
                pts.append(
                    (hx + (bx - hx) * t + jag * (t < 1), hy + (by + dy - hy) * t)
                )
            stem(g, pts, 0.6, CYAN)
        for ax, ay in ((-3, 0), (3, 0), (0, 3), (-2, -2), (2, -2), (-2, 2), (2, 2)):
            put(g, int(hx + ax), int(hy + ay), BLUE)
        disc(g, hx, hy, 2.4, WHITE)
    elif phase == 3:
        for ax, ay in ((-3, -3), (3, -2), (0, -4)):
            put(g, int(hx + ax), int(hy + ay), BLUE)


def casting(view, cast):
    """A seated mage's frame: the staff in the east fist, the spell at its
    head."""

    def weapon(g, dy):
        staff(g, cast.foot, cast.head, dy)
        spell(g, cast.head, cast.spell, BOLT_TO[view], dy)

    return armed(view, (None, cast.hand), weapon)


# The ranger draws and looses: per frame, the bow fist (west), the string
# fist (east; None resting), whether the string is drawn to it, and a loosed
# arrow's tail and head (None for none).
class Shot(NamedTuple):
    bow_hand: tuple
    string_hand: tuple | None
    drawn: bool
    flight: tuple | None
    behind_head: bool = False


SHOT = {
    "front": [
        Shot((2, 18), None, False, None),
        Shot((2, 18), (8, 18), True, None, behind_head=True),
        Shot((2, 18), None, False, ((3, 25), (1, 32))),
        Shot((2, 16), (4, 16), True, None, behind_head=True),
    ],
    "back": [
        Shot((2, 18), None, False, None),
        Shot((2, 18), (6, 18), True, None),
        Shot((2, 18), None, False, ((3, 6), (3, 0))),
        Shot((2, 16), (4, 16), True, None),
    ],
}
# The rows from the bow's grip to each limb's tip.
BOW_HALF = 12


def bow(g, grip, string, dy):
    """A wooden bow held at `grip` (its fist's top-left), its limbs curving
    west of the string; the string straight, or drawn back to `string` with
    an arrow nocked on it."""
    gx, gy = grip[0] + 1.5, grip[1] + 2 + dy
    top, bottom = (gx + 1, gy - BOW_HALF), (gx + 1, gy + BOW_HALF)
    stem(g, [top, (gx - 1, gy - 6), (gx, gy)], 0.6, WOOD)
    stem(g, [(gx, gy), (gx - 1, gy + 6), bottom], 0.6, WOOD)
    if string is None:
        stem(g, [top, bottom], 0.3, OFFWHITE_SH)
        return
    sx, sy = string[0] + 1.5, string[1] + 2 + dy
    stem(g, [top, (sx, sy), bottom], 0.3, OFFWHITE_SH)
    stem(g, [(sx, sy), (gx - 1, sy)], 0.4, WOOD_LT)  # the arrow
    rect(g, int(gx) - 2, int(sy), int(gx), int(sy) + 1, IRON_LT)
    put(g, int(sx) + 1, int(sy) - 1, RED)  # its fletching
    put(g, int(sx) + 1, int(sy) + 1, RED)


def arrow_flight(g, tail, head, dy):
    """A loosed arrow flying from `tail` to `head`, a streak trailing it."""
    (tx, ty), (hx, hy) = tail, head
    stem(g, [(tx + 0.5, ty + 0.5 + dy), (hx + 0.5, hy + 0.5 + dy)], 0.4, WOOD_LT)
    put(g, hx, hy + dy, IRON_LT)
    put(g, tx, ty + dy, RED)
    back = (tx + (tx - hx) / 2 + 0.5, ty + (ty - hy) / 2 + 0.5 + dy)
    stem(g, [(tx + 0.5, ty + 0.5 + dy), back], 0.3, IRON_HI)


def shooting(view, shot):
    """A seated archer's frame: the bow in the west fist, the string fist
    drawing, loosed or reaching back for the next arrow."""

    def weapon(g, dy):
        bow(g, shot.bow_hand, shot.string_hand if shot.drawn else None, dy)
        if shot.flight:
            arrow_flight(g, *shot.flight, dy)

    hands = (shot.bow_hand, shot.string_hand or (24, SEAT_Y))
    return armed(view, hands, weapon, shot.behind_head)


# The berserker chops with a two-handed axe: per frame, both fists on the
# haft (west, east), the haft's butt and the axe head's centre, the slash its
# fall trails and where it lands in sparks.
class Chop(NamedTuple):
    hands: tuple
    butt: tuple
    head: tuple
    slash: tuple
    sparks: tuple | None
    behind_head: bool = False


CHOP = {
    "front": [
        Chop(((19, 26), (24, 22)), (16, 34), (25, 9), (), None, behind_head=True),
        Chop(((12, 8), (17, 6)), (15, 22), (15, 2), (), None, behind_head=True),
        Chop(
            ((12, 28), (17, 29)),
            (16, 16),
            (16, 37),
            ((18, 0), (27, 5), (28, 14), (26, 22)),
            None,
            behind_head=True,
        ),
        Chop(((12, 28), (17, 29)), (16, 17), (16, 38), (), (15, 31), behind_head=True),
    ],
    "back": [
        Chop(((19, 28), (24, 24)), (16, 36), (25, 6), (), None),
        Chop(((18, 12), (23, 9)), (18, 22), (24, 1), (), None),
        Chop(
            ((11, 12), (19, 12)),
            (15, 24),
            (15, -1),
            ((29, 4), (24, 0), (8, 0), (3, 3)),
            None,
        ),
        Chop(((11, 14), (19, 14)), (15, 26), (15, 0), (), (5, 1)),
    ],
}


def axe(g, butt, head, dy):
    """A two-handed axe: a long haft from `butt` to `head` and there a broad
    iron bit swept toward the figure's middle, so it stays on the canvas, its
    edge lit."""
    (bx, by), (hx, hy) = butt, head
    stem(g, [(bx + 0.5, by + 0.5 + dy), (hx + 0.5, hy + 0.5 + dy)], 0.8, WOOD_SH)
    length = math.hypot(hx - bx, hy - by)
    ux, uy = (hx - bx) / length, (hy - by) / length
    px, py = -uy, ux  # across the haft
    side = 1 if px * (FIG_CX - hx) >= 0 else -1  # swept toward the middle
    cx, cy = hx + 0.5, hy + 0.5 + dy
    edge = 6
    for t in range(edge + 1):
        reach = 2.5 + t / edge
        a = (cx - ux * reach + px * side * t, cy - uy * reach + py * side * t)
        b = (cx + ux * reach + px * side * t, cy + uy * reach + py * side * t)
        stem(g, [a, b], 0.6, IRON_LT if t == edge else IRON)
    disc(g, cx, cy, 1.2, IRON_SH)


def chopping(view, chop):
    """A seated berserker's frame: both fists on the axe's haft, the slash
    and the sparks over all."""

    def weapon(g, dy):
        axe(g, chop.butt, chop.head, dy)
        if chop.slash:
            slash(g, chop.slash, dy)
        if chop.sparks:
            sparks(g, *chop.sparks, dy)

    return armed(view, chop.hands, weapon, chop.behind_head)


# Each class's attack: the bodies of its frames seen from a view, a working
# adventurer's in place of the typist's (`Class::attack` picks it by the style
# an agent wears). pack.toml registers `attack_<class>` and `attack_<class>_back`
# by hand, @Sx and 1x, each listing a file per frame.
def attack_mage(view):
    """The mage's attack: the staff held, raised as the spell gathers,
    thrust as it flashes and looses its bolt, and its afterglow."""
    return [casting(view, c) for c in CAST[view]]


def attack_knight(view):
    """The knight's attack: guard, the blade raised, the cut and its slash,
    the blow landing in sparks."""
    swings = STRIKE_FRONT if view == "front" else STRIKE_BACK
    return [striking(view, sw) for sw in swings]


def attack_ranger(view):
    """The ranger's attack: the bow held, drawn, loosed with the arrow
    flying at the foe, and the hand reaching back for the next."""
    return [shooting(view, shot) for shot in SHOT[view]]


def attack_berserker(view):
    """The berserker's attack: the axe held across, heaved overhead, chopped
    down with its slash, and the blow landing in sparks."""
    return [chopping(view, c) for c in CHOP[view]]


ATTACKS = {
    "mage": attack_mage,
    "knight": attack_knight,
    "ranger": attack_ranger,
    "berserker": attack_berserker,
}
# A view's suffix on a sprite's name.
VIEW_SUFFIX = {"front": "", "back": "_back"}
POSES |= {
    f"attack_{cls}{suffix}_{i}": (
        TYPING_ROWS,
        view,
        body,
        f"The {cls}'s attack, {view} view, frame {i}.",
    )
    for cls, attack in ATTACKS.items()
    for view, suffix in VIEW_SUFFIX.items()
    for i, body in enumerate(attack(view))
}
# How far each pose's body sinks below its canvas top, its head mark with it.
POSE_BOB = {
    f"{name}_{i}": step.bob for name in WALKS for i, step in enumerate(WALK_CYCLE)
}


# ---- the base art's person ----------------------------------------------------------
def figure_1x():
    """The base art's person, standing: shirt on top, pants below the waist, hands
    at the arms' ends so the arms read as hanging at the sides."""
    return master("""
        .nHHHHn.
        nHHHHHHn
        HHSSSSHH
        HSeSSeSH
        .SSSmSS.
        .nSSSSn.
        .BBBBBB.
        BBBBBBBB
        SBBBBBBS
        .PPPPPP.
        .PPPPPP.
        .P....P.
    """)


def head_mark_1x(view):
    """The base art's head mark seen from `view`: its middle column on its face's
    first row, the brow a subagent's cap sits on, where a back view keeps the
    front's rows."""
    g = figure_1x()
    return (view, len(g[0]) // 2, next(y for y, row in enumerate(g) if SKIN in row))


def back_head_1x():
    """The base art's head from behind: hair where the face was."""
    return master("""
        .nHHHHn.
        nHHHHHHn
        HHHHHHHH
        HHHHHHHH
        .HHHHHH.
        .nHHHHn.
    """)


def typing_head_1x():
    """The base art's head at the keys: the face lit full width by the screen."""
    return master("""
        .nHHHHn.
        nHHHHHHn
        HSSSSSSH
        HSeSSeSH
        .SSSmSS.
        .nSSSSn.
    """)


# The base art's typist under the head, a frame each: the west hand forward,
# then the east.
TYPING_HANDS_1X = (
    """
    .BBBBBB.
    BBBBBBBB
    BBBBBBBB
    SBBBBBB.
    ......S.
    """,
    """
    .BBBBBB.
    BBBBBBBB
    BBBBBBBB
    .BBBBBBS
    .S......
    """,
)


def typing_1x(view, frame):
    """The base art's typist seen from `view` at `frame`: the head, hair where
    the face was from behind, over hands that move as the front's do, so a
    back-turned typist reads as the same action and not as an idle desk."""
    require(len(TYPING_HANDS_1X) == TYPING_FRAMES, "a 1x hand pose a typing frame")
    head = typing_head_1x() if view == "front" else back_head_1x()
    return head + master(TYPING_HANDS_1X[frame])


def walk_1x(view, step, mug_east=False):
    """The base art's person at `step` of the gait: the 4x walk's feet and hands
    quantized to the 1x cell. A foot lifted half a cell or more clears the ground
    row, the leading foot steps out a column, a hand at half a cell's swing or
    more moves a row; the bob, a quarter cell, settles away."""
    g = figure_1x()
    if view == "back":
        head = back_head_1x()
        g[: len(head)] = head
    ground, hands = len(g) - 1, CUFF_Y // S
    feet = [x for x, k in enumerate(g[ground]) if k != T]
    for (side, x), foot in zip(zip((-1, 1), feet), (step.west, step.east)):
        if foot.lift * 2 >= S:
            g[ground][x] = T
        if foot.out:
            g[ground][x + side] = PANTS
    sides = [x for x, k in enumerate(g[hands]) if k == SKIN]
    for (side, x), sw in zip(zip((-1, 1), sides), (step.swing, -step.swing)):
        if (side > 0 and mug_east) or abs(sw) * 2 < S:
            continue
        g[hands][x] = SHIRT
        g[hands + (1 if sw > 0 else -1)][x] = SKIN
    if mug_east:
        for y in (hands - 1, hands):
            g[y][4:6] = [MUG, MUG]
    return g


def gait_of(pose):
    """The step `pose`'s 4x frame draws, measured off its pixels against the
    standing frame's: each foot's lift, outward step and toe, and the west
    hand's swing."""

    def feet(g):
        found = []
        for half in (range(FIG_W // 2), range(FIG_W // 2, FIG_W)):
            shoe = [
                (x, y)
                for y, row in enumerate(g)
                for x in half
                if row[x] in (SHOE, SHOE_HI)
            ]
            found.append(
                (
                    max(y for _, y in shoe),
                    min(y for _, y in shoe),
                    min(x for x, _ in shoe),
                    max(x for x, _ in shoe),
                )
            )
        return found

    def west_hand(g):
        return max(
            y
            for y, row in enumerate(g)
            for x in range(FIG_W // 4)
            if y > SHOULDER_Y and row[x] in (SKIN, SKIN_SH)
        )

    rest, _ = body_frame("standing")
    g, _ = body_frame(pose)
    measured = []
    for side, (low, top, x0, x1), (rlow, rtop, rx0, rx1) in zip(
        (-1, 1), feet(g), feet(rest)
    ):
        out = (rx0 - x0) if side < 0 else (x1 - rx1)
        measured.append(Foot(rlow - low, out, (low - top) < (rlow - rtop)))
    swing = west_hand(g) - west_hand(rest) - POSE_BOB.get(pose, 0)
    return Step("measured", POSE_BOB.get(pose, 0), measured[0], measured[1], swing)


def check_walks():
    """Every walk's 1x frame shows what its 4x frame draws, quantized: the two
    densities share the gait, so neither may be drawn off it."""
    for name, (view, mug, _) in WALKS.items():
        for i, step in enumerate(WALK_CYCLE):
            drawn = gait_of(f"{name}_{i}")
            require(
                walk_1x(view, drawn, mug) == walk_1x(view, step, mug),
                f"{name}_{i}: its 4x draws {drawn}, not {step}",
            )


# Where a face-down head lies, as an offset from the crown's rest.
CROWN_SHIFT = {"seated_sleeping": (0, 0), "seated_sleeping_alt": (1, 1)}


# Where every view's hair is laid: this point on a body, and the same point on
# a layer, whose canvas stands HAIR_HEADROOM rows taller.
HEAD_MARK = (16, FACE_TOP)
EARS = {"front": ears_front, "back": ears_back, "side": ear_side}


def bald_head(view, g, dy):
    """The head a view's body shows under the hair: the face, the back of the
    head, or the profile. The ears are the hairstyle's to show or cover."""
    if view == "front":
        face_front(g, dy)
    elif view == "back":
        nape(g, dy)
    elif view == "side":
        side_face(g, dy)


def body_frame(pose):
    """`pose`'s bald body, unoutlined (the renderer outlines the dressed union),
    and its head mark `(view, x, y)`."""
    rows, view, body, _ = POSES[pose]
    g = canvas(FIG_W, rows * S)
    # The head, then the body in front of it: a collar over the neck, a raised
    # mug and its steam over the chin.
    bob = POSE_BOB.get(pose, 0)
    bald_head(view, g, bob)
    body(g, bob)
    dx, dy = CROWN_SHIFT.get(pose, (0, 0))
    return g, (view, HEAD_MARK[0] + dx, HEAD_MARK[1] + dy + bob)


def finished(lyr, skin, cover):
    """`lyr` shaded where it meets bare skin in the dressed frame: `skin` holds
    the view's bald head, `cover` the layer that will lie over this one. Skin
    is bare where nothing lies over it: for the over layer, where the layer
    itself does not; for the behind layer, which the body lies over, where the
    over layer does not."""
    out = [row[:] for row in lyr]
    top = lyr if cover is None else cover
    for y in range(LAYER_H):
        for x in range(1, FIG_W - 1):
            if lyr[y][x] not in (HAIR, HAIR_LT):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if ny < LAYER_H and skin[ny][nx] in SKIN_KEYS and top[ny][nx] == T:
                    out[y][x] = HAIR_SH
                    break
    return out


def hair_layers(style):
    """`style`'s layers per view as the renderer lays them: `(behind, over)`,
    each shaded where it meets bare skin, and the ears where the style leaves
    them bare: drawn over the behind layer, or in profile, where the ear lies on
    the face, under the over layer's hair."""
    look = HAIRSTYLES[style]()
    views = {}
    for view in ("front", "back", "side", "crown"):
        behind, over = look[view] if view in ("front", "side") else (None, look[view])
        if look["ears"] and view in EARS:
            ears = layer()
            EARS[view](ears, LIFT)
            if view == "side":
                paste(ears, over)
                over = ears
            else:
                if behind is not None:
                    paste(ears, behind)
                    EARS[view](ears, LIFT)
                behind = ears
        skin = layer()
        if view == "crown":
            asleep_body(skin, LIFT, 0)
        else:
            bald_head(view, skin, LIFT)
        views[view] = (
            finished(behind, skin, over) if behind is not None else None,
            finished(over, skin, None),
        )
    return views


def desk_chair():
    """The task chair from behind: a padded back, rounded and lit along its top,
    a centre seam; the arm pads; the gas stem and a five-star base on casters."""
    g = canvas(FIG_W, 5 * S)
    for y in range(12):
        for x in range(7, 25):
            if ((x + 0.5 - FIG_CX) / 8.5) ** 2 + (max(0, 5 - y) / 5.5) ** 2 <= 1:
                g[y][x] = CHAIR
    for y in range(12):
        for x in range(FIG_W):
            if g[y][x] == CHAIR and (y == 0 or g[y - 1][x] == T):
                g[y][x] = CHAIR_RIM
    rect(g, 15, 2, 17, 11, SHADOW)
    for x0 in (3, 25):
        rect(g, x0, 7, x0 + 4, 11, CHAIR_BASE)
        rect(g, x0, 7, x0 + 4, 8, CHAIR_RIM)
    rect(g, 8, 11, 24, 13, CHAIR_BASE)
    rect(g, 15, 13, 17, 16, SHADOW)
    rect(g, 6, 16, 26, 17, CHAIR_BASE)
    for x0 in (5, 14, 24):
        rect(g, x0, 17, x0 + 3, 19, KEY_DK)
    union_outline(g)
    return g


# ---- the desks ---------------------------------------------------------------
# The @Nx desk's own detail, in art pixels: the 1x desk has none of it.
#
# The top's grain: a seam between boards this many rows deep, and a few short
# streaks inside the boards, sparse enough to read as wood, not stripes.
DESK_BOARD_ROWS = 12
DESK_STREAKS = 3
# The drawer pedestal under the east end, and the one slim leg west of the open
# floor: a leg as wide as the 1x desk's would read as a second pedestal.
DESK_PEDESTAL_W = 16
DESK_WEST_LEG_W = 4


def desk_wood(lift, seed):
    """The desk's wood, inset a column each side so its outline fits the
    canvas: a top lit along its far edge with one board seam and a few grain
    streaks, its near edge catching the light over a shaded apron, a
    two-drawer pedestal east and one leg west, open floor between."""
    top, lip, legs, rows = desk_rows(lift)
    w, h = DESK_ART_W * S, rows * S
    ty, ly, gy = top * S, lip * S, legs * S
    x0, x1 = 1, w - 1
    g = canvas(w, h)
    rng = Draws(seed)
    rect(g, x0, ty, x1, ly, WOOD)
    rect(g, x0, ty, x1, ty + 1, WOOD_LT)
    for y in range(ty + DESK_BOARD_ROWS, ly - 2, DESK_BOARD_ROWS):
        rect(g, x0, y, x1, y + 1, WOOD_SH)
    for _ in range(DESK_STREAKS):
        y = rng.randrange(ty + 3, ly - 3)
        if (y - ty) % DESK_BOARD_ROWS == 0:
            continue
        sx = rng.randrange(4, w - 12)
        rect(g, sx, y, sx + rng.randrange(5, 9), y + 1, WOOD_SH)
    rect(g, x0, ly, x1, gy, WOOD_SH)  # the apron
    rect(g, x0, ly, x1, ly + 1, WOOD_HI)  # the top's near edge
    ped = w - DESK_PEDESTAL_W
    rect(g, ped, ly + 1, x1, h - 1, WOOD)
    rect(g, x1 - 2, ly + 1, x1, h - 1, WOOD_SH)
    rect(g, ped, ly + 1, ped + 1, h - 1, WOOD_DK)
    mid = (ly + 1 + h - 1) // 2
    rect(g, ped + 1, mid, x1, mid + 1, WOOD_DK)  # between the drawers
    for y0 in (ly + 1, mid + 1):  # a pull on each drawer
        rect(g, ped + 5, y0 + 2, ped + 9, y0 + 3, GREY)
    rect(g, x0, gy, x0 + DESK_WEST_LEG_W, h - 1, WOOD_DK)
    rect(g, x0, gy, x0 + 1, h - 1, WOOD_SH)
    return g, (w, h, ty, ly, gy)


def lamp_pool(g, cx, cy, rx, ry, y_min):
    """The lamp's warm pool on the wood: a bright core ringed by lit wood."""
    for y in range(max(y_min, int(cy - ry)), int(cy + ry) + 1):
        for x in range(int(cx - rx), int(cx + rx) + 1):
            if 0 <= y < len(g) and 0 <= x < len(g[0]) and g[y][x] == WOOD:
                d = math.hypot((x - cx) / rx, (y - cy) / ry)
                if d < 0.55:
                    g[y][x] = POOL
                elif d < 1.0:
                    g[y][x] = WOOD_LT


def lamp_base_x(base):
    """The `@Nx` lamp's base column for `desk_arrangement(base)`: its shade,
    tipped toward the desk's middle, hangs the bulb in the arrangement's cell."""
    bulb = desk_arrangement(base)["bulb"]
    return bulb * S + (1 if bulb < DESK_ART_W // 2 else 2)


# The back-turned desk's mouse, in art pixels across.
DESK_MOUSE_W = 4
# How far the lamp's pool lies from its base, toward the desk's middle.
LAMP_POOL_DX = 4


def desk_lamp(g, bx, by, facing):
    """A black articulated lamp standing at (bx, by): a weighted base, a jointed
    arm, a shade tipped toward `facing` (-1 west, 1 east) with its bulb glowing
    under it."""
    rect(g, bx - 3, by, bx + 3, by + 2, LAMP)
    rect(g, bx - 3, by, bx + 3, by + 1, LAMP_HI)
    for t in range(6):  # the arm rising, then the elbow
        put(g, bx + (t // 3) * -facing, by - 1 - t, LAMP_HI)
    ex, ey = bx - 2 * facing, by - 7
    for t in range(4):
        put(g, ex + t * facing, ey - t // 2, LAMP_HI)
    sx = ex + 4 * facing
    rect(g, sx - 3, ey - 4, sx + 3, ey - 1, LAMP)
    rect(g, sx - 2, ey - 5, sx + 2, ey - 4, LAMP)
    rect(g, sx - 3, ey - 4, sx + 3, ey - 3, LAMP_HI)
    rect(g, sx - 2, ey - 1, sx + 2, ey, BULB)
    return sx, ey


# The rows, from the wood's top, each `@Nx` prop's outlined foot stands on, per
# view, on the sides `DESK_PROP_FOOT_1X` puts them.
DESK_PROP_ROWS = {
    "desk": {"cup": 9, "tower": 12},
    "desk_north": {"cup": 18, "tower": 12},
}


def desk_marks(base, lift):
    """An `@Nx` desk's prop marks at its arrangement's columns, `lift` rows
    taller above."""
    return [
        (prop, desk_prop_mark_col(base, prop, S), (DESK_BEZEL_RAISE + lift) * S + row)
        for prop, row in DESK_PROP_ROWS[base].items()
    ]


DESK_MARKS = {
    "desk": desk_marks("desk", 0),
    "desk_north": desk_marks("desk_north", DESK_NORTH_LIFT),
}
# The `@Nx` tower's reams fill its frame, `S` times the 1x tier's rows: the
# bottom ream gives up the outline's two rows.
TOKEN_REAM_ROWS = TOKEN_ROWS_PER_TIER_1X * S
TOKEN_W = TOKEN_W_1X * S - 2
# How far the full tower's top ream teeters east.
TOKEN_TEETER = 2


def desk_cup():
    """The desk's coffee cup: a mug with coffee showing, its handle east."""
    g = canvas(2 * S, 2 * S)
    desk_mug(g, 1, 2)
    union_outline(g)
    return g


def token_tower():
    """The token meter's paper tower, a frame per tier: reams stacked, each a
    lit top sheet over its page edges, the full tower's top ream teetering
    east."""
    frames = []
    for tier in range(1, TOKEN_MAX_TIER + 1):
        h = tier * TOKEN_REAM_ROWS
        g = canvas((TOKEN_W_1X + 1) * S, h)
        foot = h - 1
        for r in range(tier):
            top = foot - (TOKEN_REAM_ROWS - (2 if r == 0 else 0))
            x0 = 1 + (TOKEN_TEETER if tier == TOKEN_MAX_TIER and r == tier - 1 else 0)
            for y in range(top, foot):
                rect(
                    g,
                    x0,
                    y,
                    x0 + TOKEN_W,
                    y + 1,
                    OFFWHITE if (foot - y) % 2 else OFFWHITE_SH,
                )
            rect(g, x0, top, x0 + TOKEN_W, top + 1, OFFWHITE)
            rect(g, x0, foot - 1, x0 + TOKEN_W, foot, OFFWHITE_SH)
            foot = top
        union_outline(g)
        frames.append(g)
    return frames


def token_sheet():
    """The sheet falling onto the token tower."""
    g = canvas(TOKEN_W + 2, 4)
    rect(g, 1, 1, TOKEN_W + 1, 2, OFFWHITE)
    rect(g, 1, 2, TOKEN_W + 1, 3, OFFWHITE_SH)
    union_outline(g)
    return g


def desk_mug(g, x, y):
    rect(g, x, y, x + 4, y + 4, MUG)
    rect(g, x + 3, y, x + 4, y + 4, MUG_SH)
    rect(g, x + 1, y, x + 3, y + 1, COFFEE)
    put(g, x + 4, y + 1, MUG_SH)
    put(g, x + 4, y + 2, MUG_SH)


def monitor_stand(g, mid, chin):
    rect(g, mid - 2, chin, mid + 2, chin + 2, SHADOW)
    rect(g, mid - 6, chin + 2, mid + 6, chin + 4, BEZEL)
    rect(g, mid - 6, chin + 2, mid + 6, chin + 3, SLATE)


def desk_south():
    """The viewer-facing desk: the monitor turns its back to us (casing, vents,
    a badge) on its stand, a lamp west pooling light on the wood; the cup and
    papers stand where its arrangement marks them."""
    g, (_w, _h, ty, _ly, _gy) = desk_wood(0, 5)
    bx = lamp_base_x("desk")
    lamp_pool(g, bx + LAMP_POOL_DX, ty + 9, 11, 6, ty + 1)
    south_monitor(g)
    desk_lamp(g, bx, ty + 10, 1)
    union_outline(g)
    return g


def south_monitor(g):
    """The viewer-facing desk's monitor: its back (casing, vents, a badge) on
    its stand."""
    mx0, mx1, chin = DESK_MONITOR_X0 * S, DESK_MONITOR_X1 * S, DESK_CHIN_Y * S
    mid = (mx0 + mx1) // 2
    rect(g, mx0, 0, mx1, chin - 1, BEZEL)
    rect(g, mx0, 0, mx1, 1, SLATE)
    rect(g, mx0, 0, mx0 + 1, chin - 1, SLATE)
    rect(g, mx0 + 1, chin - 2, mx1, chin - 1, SHADOW)
    for vy in (4, 6):
        rect(g, mx0 + 8, vy, mx1 - 8, vy + 1, SHADOW)
    rect(g, mid - 2, 9, mid + 2, 11, SLATE)
    monitor_stand(g, mid, chin - 1)


def desk_front():
    """The viewer-facing desk's front: its monitor, which hides the part of a
    sitter's cup behind it."""
    return front_layer(desk_south(), south_monitor)


def desk_north():
    """The back-turned desk: its raised monitor's glass with a few lines of
    code, a keyboard and mouse before it, a lamp east; the cup and papers stand
    where its arrangement marks them."""
    g, (_w, _h, ty, _ly, _gy) = desk_wood(DESK_NORTH_LIFT, 3)
    mx0, mx1, chin = DESK_MONITOR_X0 * S, DESK_MONITOR_X1 * S, DESK_CHIN_Y * S
    mid = (mx0 + mx1) // 2
    bx = lamp_base_x("desk_north")
    lamp_pool(g, bx - LAMP_POOL_DX, ty + 11, 11, 6, ty + 1)
    rect(g, mx0, 0, mx1, chin, BEZEL)
    rect(g, mx0, 0, mx1, 1, SLATE)
    rect(g, mx0 + 2, 2, mx1 - 2, chin - 2, GLASS)
    for i, (dx, ln) in enumerate(((1, 12), (3, 8), (3, 14), (1, 6), (3, 10))):
        rect(g, mx0 + 3 + dx, 3 + i * 2, mx0 + 3 + dx + ln, 4 + i * 2, GLASS_TXT)
    rect(g, mx0, chin - 1, mx1, chin, SHADOW)
    monitor_stand(g, mid, chin)
    ky = chin + 6
    # the mouse just west of the cup, the keyboard a column short of it
    mouse = desk_arrangement("desk_north")["cup"] * S - DESK_MOUSE_W
    rect(g, mx0 + 3, ky, mouse - 1, ky + 3, KEY_DK)
    rect(g, mx0 + 4, ky + 1, mouse - 2, ky + 2, KEYCAP)
    rect(g, mouse, ky, mouse + DESK_MOUSE_W - 1, ky + 3, KEYCAP)
    desk_lamp(g, bx, ty + 12, -1)
    union_outline(g)
    return g


# ---- the sofas ---------------------------------------------------------------
def meeting_sofa():
    """The south-facing sofa: the backrest, arms, three seat cushions
    with their fronts, feet."""
    w, h = SOFA_W * S, SOFA_H * S
    seat = SOFA_BACK_ROWS * S  # the backrest's foot, the seat's back
    g = canvas(w, h)
    # backrest
    rect(g, 3, 1, w - 3, seat, FABRIC)
    rect(g, 3, 1, w - 3, 4, FABRIC_HI)
    rect(g, 3, seat - 2, w - 3, seat, FABRIC_SH)
    # seat cushions, the seam showing between them as it does from behind
    rect(g, 6, seat, w - 6, h - 4, FABRIC_SEAM)
    for c in SOFA_SEAT_COLS:
        x0, x1 = (c - SOFA_SEAT_HALF) * S + 1, (c + SOFA_SEAT_HALF) * S - 1
        x0, x1 = max(x0, 6), min(x1, w - 6)
        rect(g, x0, seat, x1, h - 4, FABRIC)
        rect(g, x0 + 1, seat + 1, x1 - 1, seat + 3, FABRIC_HI)
        rect(g, x0, h - 6, x1, h - 4, FABRIC_SH)
    rect(g, 5, seat, w - 5, seat + 1, FABRIC_SEAM)
    # arms, a column in from each edge so the outline fits the canvas
    for ax, inner in ((1, 6), (w - 7, w - 7)):
        rect(g, ax, 3, ax + 6, h - 3, FABRIC)
        rect(g, ax, 3, ax + 6, 6, FABRIC_HI)
        rect(g, inner, 6, inner + 1, h - 3, FABRIC_SEAM)
    # front rail, feet
    rect(g, 6, h - 4, w - 6, h - 3, FABRIC_SEAM)
    rect(g, 3, h - 2, 6, h, KEY_DK)
    rect(g, w - 6, h - 2, w - 3, h, KEY_DK)
    union_outline(g)
    return g


def fade_into_shade(g, x0, x1, y0, y1):
    """Fabric dithering into shade from row `y0`, solid shade its last two rows."""
    for y in range(y0, y1):
        for x in range(x0, x1):
            if y >= y1 - 2 or (x + y) % 2 == 0:
                g[y][x] = FABRIC_SH


def meeting_sofa_north():
    """The north-facing sofa: three cushions beyond the backrest, its lit
    ridge, a back panel dithering into shade, arms, feet."""
    w, h = SOFA_W * S, SOFA_H * S
    seat, ridge_end = SOFA_SEAT_ROWS * S, (SOFA_SEAT_ROWS + SOFA_RIDGE_ROWS) * S
    panel_end = h - 2
    g = canvas(w, h)
    rect(g, 5, 2, w - 5, seat, FABRIC_SEAM)
    for c in SOFA_SEAT_COLS:
        x0, x1 = (
            max((c - SOFA_SEAT_HALF) * S + 1, 5),
            min((c + SOFA_SEAT_HALF) * S - 1, w - 5),
        )
        rect(g, x0, 2, x1, seat, FABRIC)
        rect(g, x0 + 1, 3, x1 - 1, 5, FABRIC_HI)
        rect(g, x0, seat - 2, x1, seat, FABRIC_SH)
    # the seam closes the seat, so the backrest band opens on its lit ridge
    rect(g, 3, seat - 1, w - 3, seat, FABRIC_SEAM)
    rect(g, 3, seat, w - 3, ridge_end, FABRIC_HI)
    rect(g, 3, ridge_end - 1, w - 3, ridge_end, FABRIC)
    # back panel, dithering into shade in its lower half
    rect(g, 1, ridge_end, w - 1, panel_end, FABRIC)
    shade = ridge_end + (panel_end - ridge_end) // 2
    fade_into_shade(g, 1, w - 1, shade, panel_end)
    # arms, a column in from each edge so the outline fits the canvas
    for ax, inner in ((1, 6), (w - 7, w - 7)):
        rect(g, ax, 1, ax + 6, panel_end, FABRIC)
        rect(g, ax, 1, ax + 6, 4, FABRIC_HI)
        fade_into_shade(g, ax, ax + 6, shade, panel_end)
        rect(g, inner, 4, inner + 1, panel_end, FABRIC_SEAM)
    rect(g, 3, panel_end, 6, h, KEY_DK)
    rect(g, w - 6, panel_end, w - 3, h, KEY_DK)
    union_outline(g)
    return g


# ---- the plants ----------------------------------------------------------------
LEAF_KEYS = (LEAF, LEAF_SH, LEAF_HI, LEAF_DK)


def blade(g, x0, y0, ang, length, width, lit_side=1, rib=True, keys=LEAF_KEYS):
    """One leaf from (x0, y0) along `ang` (radians), drawn over the leaves
    behind it: lit on the half facing the window, a dark rim along its
    lower-right edge so it parts from the leaf it covers, a midrib if long.
    `keys` are its body, shade, light and rim."""
    body, shade, light, rim = keys
    ca, sa = math.cos(ang), math.sin(ang)
    mask = set()
    for y in range(len(g)):
        for x in range(len(g[0])):
            dx, dy = x + 0.5 - x0, y + 0.5 - y0
            u, v = dx * ca + dy * sa, -dx * sa + dy * ca
            t = u / length  # widest a third of the way out, tapering to a point
            if 0 <= t <= 1 and abs(v) <= width * 2.2 * t**0.6 * (1 - t):
                mask.add((x, y, u, v))
    cells = {(x, y) for x, y, _, _ in mask}
    for x, y, u, v in mask:
        if (x + 1, y) not in cells or (x, y + 1) not in cells:
            g[y][x] = rim
        elif rib and abs(v) < 0.6 and 1.5 < u < length - 1.5:
            g[y][x] = shade if (v > 0) == (lit_side > 0) else rim
        elif (v > 0) == (lit_side > 0):
            g[y][x] = light if u < length * 0.55 and abs(v) > width * 0.35 else body
        else:
            g[y][x] = shade


def planter(g, cx, top, bot, half_top, half_bot, dark=False):
    """A pot tapering from its rim down: lit west, shaded east, a rim a pixel
    proud of the body with its top edge lit."""
    body, lit_, shade, rim = (
        (SHADOW, SLATE, KEY_DK, SLATE) if dark else (POT, POT_HI, POT_SH, POT_HI)
    )
    for y in range(top + 2, bot):
        t = (y - top - 2) / max(1, bot - top - 3)
        half = half_top + (half_bot - half_top) * t
        for x in range(len(g[0])):
            d = x + 0.5 - cx
            if abs(d) <= half:
                g[y][x] = (
                    lit_ if d < -half * 0.5 else shade if d > half * 0.45 else body
                )
    rect(g, int(cx - half_top - 1), top, int(cx + half_top + 1) + 1, top + 2, body)
    rect(g, int(cx - half_top - 1), top, int(cx + half_top + 1) + 1, top + 1, rim)


def bush_pot(g):
    """The lobby ficus's terracotta pot, and its holiday stand-in's."""
    planter(g, 12, 17, 27, 6.0, 4.5)


def tall_pot(g):
    """The tall plant's dark pot, and its holiday stand-in's."""
    planter(g, 12, 30, 39, 6.0, 4.8, dark=True)


def flower_pot(g):
    """The flower's terracotta pot, and its holiday stand-in's."""
    planter(g, 12, 15, 23, 4.5, 3.5)


def plant_bush():
    """A leafy bush in terracotta: long pointed leaves fanning up and out from
    the pot, every tip clear of its neighbours."""
    g = canvas(6 * S, 7 * S)
    for ang, ln, wd, side in (
        (-2.95, 10.0, 2.4, 1),
        (-0.2, 10.0, 2.4, -1),
        (-2.55, 12.0, 2.6, 1),
        (-0.6, 12.0, 2.6, -1),
        (-1.35, 14.5, 2.6, -1),
        (-1.8, 14.0, 2.6, 1),
        (-2.2, 12.0, 2.6, 1),
        (-0.95, 12.0, 2.6, -1),
        (-1.57, 10.0, 2.4, 1),
    ):
        blade(g, 12, 18.5, ang, ln, wd, side)
    bush_pot(g)
    union_outline(g)
    return g


def plant_tall():
    """A tall palm in a dark pot: a slim trunk, and long leaves fanning out from
    its crown and from one joint below it."""
    g = canvas(6 * S, 10 * S)
    rect(g, 11, 10, 13, 31, BROWN)
    rect(g, 12, 10, 13, 31, WOOD_DK)
    for ang, ln, side, y in (
        (-2.5, 10.0, 1, 21),
        (-0.64, 10.0, -1, 21),
        (-2.95, 10.5, 1, 11),
        (-0.2, 10.5, -1, 11),
        (-2.45, 11.5, 1, 11),
        (-0.7, 11.5, -1, 11),
        (-1.9, 11.0, 1, 11),
        (-1.25, 11.0, -1, 11),
    ):
        blade(g, 12, y, ang, ln, 2.4, side, rib=False)
    tall_pot(g)
    union_outline(g)
    return g


def stem(g, pts, r, key):
    """Stroke a polyline of radius `r`: a flower's stem."""
    for (x0, y0), (x1, y1) in itertools.pairwise(pts):
        steps = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
        for i in range(steps + 1):
            t = i / steps
            px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            for y in range(int(py - r) - 1, int(py + r) + 2):
                for x in range(int(px - r) - 1, int(px + r) + 2):
                    if (x + 0.5 - px) ** 2 + (y + 0.5 - py) ** 2 <= r * r:
                        put(g, x, y, key)


def plant_flower():
    """Potted flowers: a cluster of red and gold blooms over two leaves."""
    g = canvas(6 * S, 6 * S)
    blooms = [
        (8.5, 7.0, PETAL_R),
        (15.5, 6.0, PETAL_Y),
        (12, 3.5, PETAL_R),
        (6.5, 11.0, PETAL_Y),
        (17.5, 10.5, PETAL_R),
        (12, 9.5, PETAL_Y),
    ]
    for bx, by, _ in blooms:
        stem(g, [(12, 16), (bx, by + 1)], 0.5, LEAF_DK)
    blade(g, 12, 16, -2.55, 7.5, 2.6, 1, rib=False)
    blade(g, 12, 16, -0.6, 7.5, 2.6, -1, rib=False)
    for bx, by, col in blooms:
        disc(g, bx, by, 2.4, col)
        put(g, int(bx) - 1, int(by) - 1, PETAL_HI)
        put(g, int(bx), int(by), GOLD if col == PETAL_R else DARK_RED)
    flower_pot(g)
    union_outline(g)
    return g


def plant_succulent():
    """A succulent rosette in a wide shallow pot: plump pointed leaves, the
    inner ones standing up over the outer."""
    g = canvas(5 * S, 4 * S)
    for i in range(7):
        ang = -math.pi + 0.15 + i * (math.pi - 0.3) / 6
        blade(g, 10, 10, ang, 7.0, 2.6, 1 if i < 3 else -1, rib=False)
    for ang in (-2.05, -1.1):
        blade(g, 10, 10, ang, 6.0, 2.4, 1 if ang < -1.57 else -1, rib=False)
    planter(g, 10, 9, 15, 6.5, 5.0)
    union_outline(g)
    return g


# ---- the holiday stand-ins -----------------------------------------------------
# Each is drawn on the canvas of the plant it stands in for, its base where the
# plant's pot stands, so the plant's footprint holds. A tree's lights are two
# strings lit in turn, in BULB, which glows of its own after dark.
BRACT_KEYS = (RED, DARK_RED, VERMILION, DARK_RED)


def bough(g, cx, apex, base, half):
    """One tier of a fir: a triangle from `apex` down to `base`, `half` wide
    there, lit west and shaded east, its hem two dark rows, the lower
    scalloped into points, so it parts from the tier under it."""
    for y in range(apex, base + 1):
        w = half * (y - apex + 1) / (base - apex + 1)
        for x in range(len(g[0])):
            d = x + 0.5 - cx
            if abs(d) > w:
                continue
            if y == base and x % 3 == 1:
                continue
            if y >= base - 1:
                g[y][x] = LEAF_DK
            elif d < -w * 0.5:
                g[y][x] = LEAF_HI
            elif d < w * 0.35:
                g[y][x] = LEAF
            else:
                g[y][x] = LEAF_SH


def star(g, cx, top):
    """The tree's gold star over `cx`, its heart a bulb."""
    x = int(cx)
    rect(g, x - 1, top, x + 1, top + 5, GOLD)
    rect(g, x - 3, top + 2, x + 3, top + 3, GOLD)
    rect(g, x - 2, top + 1, x + 2, top + 4, GOLD)
    rect(g, x - 1, top + 2, x + 1, top + 3, BULB)


def tree_frames(w, h, tiers, trunk, bulbs, draw_pot):
    """A fir's two frames: its `tiers` of (apex, base, half), a `trunk` of
    (top, bottom), two strings of 2x2 `bulbs` lit in turn, and its pot."""
    frames = []
    for lit in range(2):
        g = canvas(w, h)
        cx = w / 2
        rect(g, int(cx) - 1, trunk[0], int(cx) + 1, trunk[1], BROWN)
        rect(g, int(cx), trunk[0], int(cx) + 1, trunk[1], WOOD_DK)
        for apex, base, half in tiers:
            bough(g, cx, apex, base, half)
        for string, cells in enumerate(bulbs):
            bulb = BULB if string == lit else (RED, BLUE)[string]
            for x, y in cells:
                rect(g, x, y, x + 2, y + 2, bulb)
        star(g, cx, 0)
        draw_pot(g)
        union_outline(g)
        frames.append(g)
    return frames


def christmas_tree():
    """A Christmas tree in the tall plant's dark pot: three tiers of fir under
    a gold star, two strings of lights twinkling in turn."""
    return tree_frames(
        6 * S,
        10 * S,
        ((4, 13, 5.5), (9, 21, 8.5), (15, 29, 11.5)),
        (28, 31),
        (
            ((10, 9), (14, 16), (6, 22), (15, 25)),
            ((12, 12), (8, 17), (12, 21), (9, 26)),
        ),
        tall_pot,
    )


def christmas_tree_short():
    """A short Christmas tree in the lobby ficus's terracotta pot: two tiers of
    fir under a gold star, two strings of lights twinkling in turn."""
    return tree_frames(
        6 * S,
        7 * S,
        ((4, 11, 7.0), (8, 17, 11.5)),
        (16, 18),
        (
            ((9, 8), (14, 13)),
            ((13, 9), (7, 14)),
        ),
        bush_pot,
    )


def poinsettia():
    """A poinsettia in the flower's terracotta pot: a star of red bracts over
    green leaves, a gold heart."""
    g = canvas(6 * S, 6 * S)
    for ang, side in ((-2.7, 1), (-0.45, -1)):
        blade(g, 12, 14, ang, 9.0, 2.6, side, rib=False)
    for i in range(6):
        ang = -math.pi / 2 + i * math.tau / 6
        blade(g, 12, 8, ang, 7.0, 2.4, 1 if math.cos(ang) < 0 else -1, keys=BRACT_KEYS)
    disc(g, 12, 8, 1.6, GOLD)
    put(g, 11, 7, PETAL_HI)
    flower_pot(g)
    union_outline(g)
    return g


def gift(g, x0, y0, x1, y1, wrap, wrap_sh, ribbon):
    """A wrapped box from (x0, y0) to (x1, y1): shaded east, tied both ways
    with `ribbon`."""
    rect(g, x0, y0, x1, y1, wrap)
    rect(g, x1 - (x1 - x0) // 3, y0, x1, y1, wrap_sh)
    mx, my = (x0 + x1) // 2, (y0 + y1) // 2
    rect(g, mx - 1, y0, mx + 1, y1, ribbon)
    rect(g, x0, my - 1, x1, my, ribbon)


def presents():
    """Wrapped presents where the succulent stood: a red box tied in gold
    under its bow, and a smaller blue one beside it."""
    g = canvas(5 * S, 4 * S)
    gift(g, 3, 6, 13, 16, RED, DARK_RED, GOLD)
    gift(g, 13, 10, 19, 16, BLUE, INK, CYAN)
    for x0 in (4, 9):
        rect(g, x0, 3, x0 + 3, 6, GOLD)
        put(g, x0 + 1, 4, DARK_RED)
    rect(g, 7, 4, 9, 6, GOLD)
    union_outline(g)
    return g


# ---- furniture: fixtures, boards, shelves, screens, the pantry -------------------
CORK, CORK_SH, STEEL, STEEL_SH = "Δ", "π", "K", "ξ"
BOOKS = (RED, BLUE, GOLD, FABRIC, TAN, DARK_RED, VERMILION, GREEN)


# `Furniture::FloorLamp`'s visual box.
LAMP_W, LAMP_H = 4, 12


def floor_lamp():
    """A floor lamp: a weighted base, a slim pole with its pull chain, a
    tapered drum shade lit from within, dithered warmer toward the bulb glowing
    at its open foot, the east side in shade."""
    w, h = LAMP_W * S, LAMP_H * S
    g = canvas(w, h)
    rect(g, 3, h - 5, w - 3, h - 2, LAMP)
    rect(g, 3, h - 5, w - 3, h - 4, LAMP_HI)
    rect(g, 7, 12, 9, h - 5, LAMP)
    rect(g, 7, 12, 8, h - 5, LAMP_HI)
    rect(g, 4, 1, w - 4, 3, OFFWHITE)
    rect(g, 3, 3, w - 3, 6, OFFWHITE)
    rect(g, 2, 6, w - 2, 11, OFFWHITE)
    for y in range(1, 11):  # the shade's east side, turned from the light
        east = w - 4 if y < 3 else w - 3 if y < 6 else w - 2
        rect(g, east - 3, y, east, y + 1, OFFWHITE_SH)
    for y in (8, 9):  # warming toward the bulb
        for x in range(2, w - 2):
            if (x + y) % 2:
                put(g, x, y, BULB)
    rect(g, 2, 10, w - 2, 11, BULB)
    rect(g, 5, 11, w - 5, 12, BULB)
    rect(g, 11, 11, 12, 15, GREY)  # the pull chain
    union_outline(g)
    return g


def floor_lamp_1x():
    """The floor lamp at 1x: a dark shade with the bulb's warm glow in it, the
    slim pole, the chrome base."""
    g = canvas(LAMP_W, LAMP_H)
    rect(g, 1, 0, 3, 1, BEZEL)
    rect(g, 0, 1, LAMP_W, 3, BEZEL)
    rect(g, 1, 1, 3, 3, GOLD)
    rect(g, 1, 3, 3, 4, BEZEL)
    rect(g, 2, 4, 3, LAMP_H - 1, OUTLINE)
    rect(g, 1, LAMP_H - 1, 3, LAMP_H, STEEL)
    return g


def filing_cabinet():
    """A steel filing cabinet: three drawers, each with a pull and a label slot,
    the top catching the light."""
    g = canvas(4 * S, 6 * S)
    rect(g, 1, 1, 15, 23, STEEL)
    rect(g, 1, 1, 15, 2, WHITE)
    rect(g, 12, 2, 15, 23, STEEL_SH)
    for i in range(3):
        y0 = 3 + i * 7
        if i < 2:  # between drawers; the last one's foot is the cabinet's
            rect(g, 2, y0 + 6, 15, y0 + 7, SHADOW)
        rect(g, 5, y0 + 2, 11, y0 + 3, OFFWHITE)
        rect(g, 6, y0 + 4, 10, y0 + 5, KEY_DK)
    union_outline(g)
    return g


def bulletin_board():
    """A corkboard in a wooden frame, notes pinned across it."""
    g = canvas(10 * S, 6 * S)
    rect(g, 1, 1, 39, 23, WOOD)
    rect(g, 1, 1, 39, 2, WOOD_LT)
    rect(g, 3, 3, 37, 21, CORK)
    for x, y in ((6, 5), (14, 17), (22, 8), (30, 15), (33, 5), (9, 12), (27, 19)):
        put(g, x, y, CORK_SH)
    for x0, y0, c in (
        (5, 5, GOLD),
        (13, 4, CYAN),
        (22, 6, PINK),
        (30, 4, OFFWHITE),
        (8, 13, OFFWHITE),
        (18, 13, GOLD),
        (27, 13, CYAN),
    ):
        rect(g, x0, y0, x0 + 6, y0 + 6, c)
        rect(g, x0 + 1, y0 + 2, x0 + 5, y0 + 3, PRINT)
        rect(g, x0 + 1, y0 + 4, x0 + 4, y0 + 5, PRINT)
        put(g, x0 + 3, y0, RED)
    union_outline(g)
    return g


EXIT_GLYPHS = {
    "E": ("111", "100", "110", "100", "111"),
    "X": ("101", "101", "010", "101", "101"),
    "I": ("1",) * 5,
    "T": ("111", "010", "010", "010", "010"),
}


def exit_sign():
    """A lit EXIT sign: dark red letters on a warm-lit panel in a red frame."""
    w, h = 5 * S, 3 * S
    g = canvas(w, h)
    rect(g, 1, 1, w - 1, h - 1, RED)
    rect(g, 2, 2, w - 2, h - 2, BULB)
    x = 4
    for letter in "EXIT":
        rows = EXIT_GLYPHS[letter]
        for r, row in enumerate(rows):
            for c, bit in enumerate(row):
                if bit == "1":
                    put(g, x + c, 3 + r, DARK_RED)
        x += len(rows[0]) + 1
    union_outline(g)
    return g


def whiteboard():
    """A mobile whiteboard: an aluminium frame round a sprint board of sticky
    notes and a burndown line, a marker tray, a wheeled stand."""
    g = canvas(14 * S, 11 * S)
    rect(g, 1, 1, 55, 30, ALU)
    rect(g, 1, 1, 55, 2, WHITE)
    rect(g, 1, 29, 55, 30, ALU_DK)
    rect(g, 3, 3, 53, 28, OFFWHITE)
    rect(g, 3, 26, 53, 28, OFFWHITE_SH)
    for i, x0 in enumerate((6, 20, 34)):
        rect(g, x0, 5, x0 + 11, 6, INK)
        for r in range(2 + (i != 1)):
            c = (GOLD, CYAN, PINK)[(i + r) % 3]
            rect(g, x0 + 1, 8 + r * 6, x0 + 8, 13 + r * 6, c)
            rect(g, x0 + 2, 10 + r * 6, x0 + 6, 11 + r * 6, PRINT)
    for x in (17, 31):
        rect(g, x, 5, x + 1, 25, INK)
    for t in range(12):
        put(g, 42 + t, 10 + t + (t % 3 == 1), RED)
    rect(g, 12, 30, 44, 32, ALU_DK)
    rect(g, 16, 30, 20, 31, RED)
    rect(g, 22, 30, 26, 31, BLUE)
    for lx in (10, 44):
        rect(g, lx, 32, lx + 2, 41, ALU_DK)
        rect(g, lx - 3, 41, lx + 5, 43, KEY_DK)
    rect(g, 10, 36, 46, 37, ALU_DK)
    union_outline(g)
    return g


def bookshelf():
    """A wooden bookshelf: three shelves of books, one leaning, a potted sprig
    and a box on the top shelf, a cabinet below."""
    g = canvas(8 * S, 12 * S)
    rect(g, 1, 1, 31, 46, WOOD)
    rect(g, 1, 1, 31, 2, WOOD_LT)
    rect(g, 28, 2, 31, 46, WOOD_SH)
    rect(g, 3, 3, 29, 34, WOOD_DK)
    rng = Draws(21)
    for shelf in range(3):
        floor_y = 12 + shelf * 11
        x = 4
        while x < 27:
            bw = rng.choice((2, 2, 3))
            bh = rng.randrange(6, 9)
            col = BOOKS[rng.randrange(len(BOOKS))]
            if shelf == 0 and x > 18:
                break
            rect(g, x, floor_y - bh, min(27, x + bw), floor_y, col)
            put(g, x, floor_y - bh, WHITE if col in (BLUE, DARK_RED, FABRIC) else PRINT)
            x += bw + (1 if rng.random() < 0.25 else 0)
        if shelf == 1:
            for t in range(7):  # a book leaning on its neighbour
                put(g, 24 + t // 3, floor_y - 1 - t, RED)
                put(g, 25 + t // 3, floor_y - 1 - t, RED)
        rect(g, 3, floor_y, 29, floor_y + 2, WOOD)
        rect(g, 3, floor_y, 29, floor_y + 1, WOOD_LT)
    rect(g, 21, 7, 26, 12, POT)  # a potted sprig and a box on the top shelf
    rect(g, 21, 7, 26, 8, POT_HI)
    for x, y in ((22, 5), (23, 4), (24, 5), (25, 3), (23, 6)):
        put(g, x, y, LEAF)
    rect(g, 4, 9, 9, 12, TAN)
    rect(g, 3, 35, 29, 45, WOOD)
    rect(g, 3, 35, 29, 36, WOOD_LT)
    rect(g, 15, 36, 16, 45, WOOD_DK)
    rect(g, 12, 39, 14, 41, GREY)
    rect(g, 17, 39, 19, 41, GREY)
    union_outline(g)
    return g


SLIDE_BAR_PITCH = 4


def slide(g, x0, y0, x1, y1):
    """A lit slide sized to its screen: a title bar, bullet lines, a bar chart."""
    rect(g, x0, y0, x1, y1, DISPLAY)
    rect(g, x0 + 2, y0 + 2, x1 - 2, y0 + 4, CYAN)
    w = x1 - x0
    for i in range(3):
        put(g, x0 + 3, y0 + 7 + i * 3, GREY)
        rect(
            g,
            x0 + 5,
            y0 + 7 + i * 3,
            x0 + 5 + w * (3 if i % 2 else 4) // 10,
            y0 + 8 + i * 3,
            GREY,
        )
    bars = (0.4, 0.65, 0.5, 0.85)
    # the chart hangs from the glass's east edge, so a narrow screen keeps it
    bx, base = x1 - 2 - len(bars) * SLIDE_BAR_PITCH, y1 - 3
    for i, frac in enumerate(bars):
        top = base - int((base - y0 - 8) * frac)
        x = bx + i * SLIDE_BAR_PITCH
        rect(g, x, top, x + SLIDE_BAR_PITCH - 1, base, BLUE if i % 2 else LEAF)
    rect(g, bx - 1, base, x1 - 2, base + 1, GREY)
    for y in range(y0, y1):  # a soft sheen across the glass
        for x in range(x0, x1):
            if (x + y) % 23 == 0 and g[y][x] == DISPLAY:
                g[y][x] = DISPLAY_SHEEN


def meeting_screen():
    """A wall-mounted widescreen showing a slide, on its bracket."""
    g = canvas(14 * S, 12 * S)
    rect(g, 1, 3, 55, 39, SHADOW)
    rect(g, 1, 3, 55, 4, SLATE)
    slide(g, 3, 5, 53, 37)
    rect(g, 22, 39, 34, 42, BEZEL)
    rect(g, 26, 42, 30, 47, SHADOW)
    union_outline(g)
    return g


def fridge(g, x0, y0, w, h):
    """A fridge: a freezer door over the main one, each with a steel handle,
    two magnets, the east side in shade."""
    seam = y0 + h * 2 // 5
    rect(g, x0, y0, x0 + w, y0 + h, OFFWHITE)
    rect(g, x0 + w - max(2, w // 7), y0, x0 + w, y0 + h, OFFWHITE_SH)
    rect(g, x0, y0, x0 + w, y0 + 1, WHITE)
    rect(g, x0, seam, x0 + w, seam + 1, OFFWHITE_SH)
    hx = x0 + w - max(2, w // 7) - 3
    rect(g, hx, y0 + 3, hx + 1, seam - 2, STEEL)
    rect(g, hx, seam + 3, hx + 1, seam + 3 + (y0 + h - seam) // 2, STEEL)
    rect(g, x0 + 3, y0 + h - 9, x0 + 5, y0 + h - 7, CYAN)
    rect(g, x0 + 7, y0 + h - 8, x0 + 9, y0 + h - 6, RED)


def counter(g, x0, x1, top, bottom):
    """A counter: a lit top edge, cabinet doors with pulls below it."""
    rect(g, x0, top, x1, bottom, WOOD)
    rect(g, x0, top, x1, top + 2, WOOD_HI)
    rect(g, x0, top + 2, x1, top + 3, WOOD_SH)
    for cx in range(x0 + 10, x1 - 4, 12):
        rect(g, cx, top + 4, cx + 1, bottom - 1, WOOD_DK)
        rect(g, cx - 3, top + 6, cx - 1, top + 7, STEEL)
        rect(g, cx + 2, top + 6, cx + 4, top + 7, STEEL)


def espresso(g, x0, y0):
    rect(g, x0, y0, x0 + 12, y0 + 12, STEEL)
    rect(g, x0, y0, x0 + 12, y0 + 1, WHITE)
    rect(g, x0 + 9, y0, x0 + 12, y0 + 12, STEEL_SH)
    rect(g, x0 + 2, y0 + 2, x0 + 7, y0 + 4, CYAN)
    rect(g, x0 + 4, y0 + 6, x0 + 8, y0 + 7, SHADOW)
    rect(g, x0 + 4, y0 + 8, x0 + 7, y0 + 11, MUG)


def microwave(g, x0, y0, w):
    rect(g, x0, y0, x0 + w, y0 + 10, BEZEL)
    rect(g, x0, y0, x0 + w, y0 + 1, SLATE)
    rect(g, x0 + 2, y0 + 2, x0 + w - 6, y0 + 8, INK)
    rect(g, x0 + 3, y0 + 3, x0 + 6, y0 + 4, DISPLAY_SHEEN)
    rect(g, x0 + w - 4, y0 + 2, x0 + w - 1, y0 + 4, CYAN)
    rect(g, x0 + w - 4, y0 + 5, x0 + w - 1, y0 + 6, KEYCAP)
    rect(g, x0 + w - 4, y0 + 7, x0 + w - 1, y0 + 8, KEYCAP)


def bottle(g, x0, y0, col):
    rect(g, x0, y0 + 3, x0 + 3, y0 + 10, col)
    rect(g, x0 + 1, y0, x0 + 2, y0 + 3, col)
    rect(g, x0, y0 + 4, x0 + 1, y0 + 9, WHITE)


def pantry():
    """The office pantry: a fridge, an espresso counter with mugs, a microwave
    counter with bottles."""
    g = canvas(32 * S, 10 * S)
    fridge(g, 1, 1, 26, 38)
    counter(g, 32, 76, 16, 39)
    espresso(g, 38, 4)
    for x in (54, 60):
        desk_mug(g, x, 12)
    counter(g, 82, 127, 16, 39)
    microwave(g, 86, 5, 22)
    bottle(g, 112, 6, GOLD)
    bottle(g, 117, 6, RED)
    bottle(g, 122, 6, LEAF)
    union_outline(g)
    return g


def pantry_small():
    """The compact pantry: a vending machine lit from within, a mini fridge, a
    coffee-and-microwave counter."""
    g = canvas(20 * S, 8 * S)
    rect(g, 1, 1, 15, 31, BEZEL)
    rect(g, 1, 1, 15, 2, SLATE)
    rect(g, 3, 3, 12, 22, INK)
    for r in range(4):
        for c in range(3):
            rect(
                g,
                4 + c * 3,
                4 + r * 5,
                6 + c * 3,
                7 + r * 5,
                (RED, GOLD, BLUE, LEAF)[(r + c) % 4],
            )
    rect(g, 13, 6, 14, 10, CYAN)
    rect(g, 3, 24, 12, 27, KEY_DK)
    fridge(g, 18, 9, 14, 22)
    counter(g, 36, 79, 14, 31)
    espresso(g, 40, 2)
    microwave(g, 56, 4, 20)
    union_outline(g)
    return g


def snack_shelf():
    """A wooden rack of snack packets, three shelves, a drawer below."""
    g = canvas(7 * S, 10 * S)
    rect(g, 1, 1, 27, 40, WOOD)
    rect(g, 1, 1, 27, 2, WOOD_LT)
    rect(g, 24, 2, 27, 40, WOOD_SH)
    rect(g, 3, 3, 24, 30, WOOD_DK)
    rng = Draws(33)
    for shelf in range(3):
        yb = 11 + shelf * 9
        x = 4
        while x < 22:
            pw = rng.choice((3, 4))
            ph = rng.randrange(4, 7)
            col = (GOLD, RED, BLUE, LEAF, CYAN, VERMILION)[rng.randrange(6)]
            rect(g, x, yb - ph, min(24, x + pw), yb, col)
            rect(g, x, yb - ph, min(24, x + pw), yb - ph + 1, WHITE)
            x += pw + 1
        rect(g, 3, yb, 24, yb + 2, WOOD)
        rect(g, 3, yb, 24, yb + 1, WOOD_LT)
    rect(g, 3, 31, 24, 37, WOOD)
    rect(g, 11, 33, 16, 34, STEEL)
    union_outline(g)
    return g


def tv_stand():
    """A lit TV on a slim neck over a low media cabinet."""
    g = canvas(10 * S, 10 * S)
    rect(g, 1, 1, 39, 24, SHADOW)
    rect(g, 1, 1, 39, 2, SLATE)
    slide(g, 3, 3, 37, 22)
    rect(g, 18, 24, 22, 29, BEZEL)
    rect(g, 4, 29, 36, 40, WOOD)
    rect(g, 4, 29, 36, 30, WOOD_LT)
    rect(g, 4, 38, 36, 40, WOOD_SH)
    rect(g, 19, 31, 20, 37, WOOD_DK)
    rect(g, 15, 33, 18, 34, STEEL)
    rect(g, 22, 33, 25, 34, STEEL)
    union_outline(g)
    return g


# `Furniture::PhoneBooth`'s visual box.
BOOTH_W, BOOTH_H = 7, 15


def phone_booth():
    """A glass privacy pod: a dark frame round tinted glass with streaks of
    reflection, a transom across it, a shelf and a stool inside, the door's
    steel pull on its east edge, a wood kick panel, its occupied light on the
    roof."""
    w, h = BOOTH_W * S, BOOTH_H * S
    mid = w // 2
    g = canvas(w, h)
    rect(g, 1, 1, w - 1, h - 1, BEZEL)
    rect(g, 1, 1, w - 1, 2, SLATE)
    rect(g, mid - 3, 2, mid + 3, 4, BULB)
    gx0, gy0, gx1, gy1 = 3, 6, w - 3, 47
    rect(g, gx0, gy0, gx1, gy1, CYAN)
    rect(g, gx0 + 4, 31, gx1 - 4, 33, WOOD)  # the shelf inside
    rect(g, gx0 + 4, 33, gx1 - 4, 34, WOOD_SH)
    rect(g, mid - 3, 39, mid + 3, 41, SHADOW)  # a stool
    rect(g, mid - 1, 41, mid + 1, gy1, SHADOW)
    for y in range(gy0, gy1):
        for x in range(gx0, gx1):
            if (x - y * 0.6) % 15 < 1.5:
                g[y][x] = WHITE
    rect(g, gx0, 24, gx1, 26, BEZEL)  # the transom
    rect(g, gx1 - 3, 30, gx1 - 1, 38, STEEL)  # the door's pull
    rect(g, gx0, gy1, gx1, h - 3, WOOD)
    rect(g, gx0, gy1, gx1, gy1 + 1, WOOD_LT)
    rect(g, gx0, h - 4, gx1, h - 3, WOOD_SH)
    union_outline(g)
    return g


def phone_booth_1x():
    """The phone booth at 1x: the roof's occupied light, cyan glass walls with
    a streak of reflection over the transom, the shelf and stool inside, the
    door's pull, the wood kick panel, in a dark frame."""
    w, h = BOOTH_W, BOOTH_H
    mid = w // 2
    g = canvas(w, h)
    rect(g, 1, 0, w - 1, 1, OUTLINE)
    rect(g, 0, 1, w, h - 1, OUTLINE)
    rect(g, 1, h - 1, w - 1, h, OUTLINE)
    rect(g, mid - 1, 1, mid + 2, 2, GOLD)
    rect(g, 1, 2, w - 1, h - 3, CYAN)
    put(g, 1, 3, WHITE)
    put(g, 2, 4, WHITE)
    rect(g, 1, 5, w - 1, 6, BEZEL)
    rect(g, 2, 7, w - 2, 8, WOOD)
    rect(g, mid - 1, 9, mid + 2, 10, SHADOW)
    rect(g, mid, 10, mid + 1, h - 3, SHADOW)
    rect(g, w - 2, 8, w - 1, 10, STEEL)
    rect(g, 1, h - 3, w - 1, h - 1, WOOD)
    return g


def standing_desk():
    """A sit-stand desk with a lit laptop, on slim legs."""
    g = canvas(8 * S, 8 * S)
    rect(g, 1, 1, 31, 17, WOOD)
    rect(g, 1, 1, 31, 2, WOOD_LT)
    rect(g, 1, 15, 31, 17, WOOD_SH)
    rect(g, 7, 3, 25, 11, BEZEL)
    rect(g, 8, 4, 24, 10, CYAN)
    rect(g, 9, 5, 17, 6, WHITE)
    rect(g, 9, 7, 14, 8, WHITE)
    rect(g, 6, 11, 26, 14, KEYCAP)
    rect(g, 6, 11, 26, 12, GREY)
    for lx in (4, 26):
        rect(g, lx, 17, lx + 2, 29, STEEL_SH)
        rect(g, lx - 2, 29, lx + 4, 31, KEY_DK)
    union_outline(g)
    return g


# ---- the corridor appliances and the meeting table ---------------------------------
# Drawn in the theme's appliance keys (pack::appliance_overrides).
VEND_BODY, VEND_BODY_LT, VEND_BODY_SH = "Б", "Ъ", "ъ"
VEND_PANEL, VEND_PANEL_LT = "П", "п"
VEND_DRINKS = ("Ч", "Ш", "Щ", "Э")
VEND_TRIM, VEND_DARK = "Ф", "Ы"
PRN_BODY, PRN_BODY_SH = "Ю", "ю"
PRN_TOP, PRN_TOP_LT = "Я", "я"
PRN_GLASS = "Ё"
PRN_PAPER, PRN_PAPER_SH = "Й", "й"
PRN_TRAY = "Ц"
LED_ON = GREEN
# A vend, one loop per drink: the panel flashes as the pick's can leaves its
# shelf, falls past the shelf below, and waits in the tray until it is taken.
VEND_STEPS = 6  # rest, falling, three in the tray, taken
PRINT_STEPS = 8


# `Furniture::VendingMachine`'s and `Furniture::Printer`'s visual boxes.
VEND_W, VEND_H = 7, 13
PRN_W, PRN_H = 7, 8


def vend_can(g, x, y, drink):
    """A can standing on its shelf, its lid catching the light."""
    rect(g, x, y, x + VEND_CAN_W, y + VEND_CAN_H, drink)
    put(g, x, y, WHITE)


def vend_can_lying(g, x, y, drink):
    """A can on its side in the tray, its lid to the west."""
    rect(g, x, y, x + VEND_CAN_H, y + VEND_CAN_W - 1, drink)
    put(g, x, y, WHITE)


# The vending machine's glass, in canvas coordinates: 4 columns x 4 shelves of
# cans; the rows below the last shelf are where a vend drops.
VEND_GLASS = (3, 11, 20, 38)  # x0, y0, x1, y1
VEND_CAN_W, VEND_CAN_H = 3, 4
VEND_CAN_COLS = (4, 8, 12, 16)
VEND_SHELVES = (12, 18, 24, 30)  # each shelf's can tops; its lip runs under them
VEND_TRAY = (4, 41, 19, 46)  # x0, y0, x1, y1: the pickup recess
VEND_EAST = 25  # the shaded east side's first column
# The glass's glint: a short diagonal down the column no can stands in.
VEND_GLINT = ((3, 12), (3, 13), (3, 14), (19, 35), (19, 36))


def vend_drink(shelf, col):
    """The drink stocked at `shelf`, `col`: each shelf the last one's rotation."""
    return VEND_DRINKS[(shelf * 3 + col) % len(VEND_DRINKS)]


def vend_pick(drink):
    """The (column, shelf) a vend of `drink` comes from: a different shelf each."""
    col = next(
        c
        for c in range(len(VEND_CAN_COLS))
        if vend_drink(drink, c) == VEND_DRINKS[drink]
    )
    return VEND_CAN_COLS[col], VEND_SHELVES[drink]


def vending_body():
    """The machine at rest: a lit brand panel over a glass front of cans on
    four shelves, the selection display, keypad, coin plate and note slot in
    the column beside it, the pickup flap and a vented plinth below, the east
    side in shade."""
    w, h = VEND_W * S, VEND_H * S
    g = canvas(w, h)
    rect(g, 1, 1, w - 1, h - 1, VEND_BODY)
    rect(g, 1, 1, w - 1, 2, VEND_BODY_LT)
    rect(g, VEND_EAST, 2, w - 1, h - 1, VEND_BODY_SH)
    rect(g, 2, 2, VEND_EAST - 1, 9, VEND_PANEL)
    rect(g, 2, 2, VEND_EAST - 1, 3, VEND_PANEL_LT)
    rect(g, 5, 5, 19, 6, WHITE)  # the brand's wordmark
    rect(g, 7, 6, 15, 7, VEND_PANEL_LT)
    x0, y0, x1, y1 = VEND_GLASS
    rect(g, x0, y0, x1, y1, VEND_DARK)
    for si, sy in enumerate(VEND_SHELVES):
        for ci, cx in enumerate(VEND_CAN_COLS):
            vend_can(g, cx, sy, vend_drink(si, ci))
        rect(g, x0, sy + VEND_CAN_H, x1, sy + VEND_CAN_H + 1, SLATE)  # the shelf's lip
    for x, y in VEND_GLINT:
        put(g, x, y, VEND_BODY_LT)
    rect(g, 21, 12, 24, 14, CYAN)  # the selection display
    for ky in (16, 18, 20):  # the keypad
        put(g, 21, ky, KEYCAP)
        put(g, 23, ky, KEYCAP)
    rect(g, 21, 24, 24, 30, VEND_TRIM)  # the coin plate, a slit through it
    rect(g, 22, 25, 23, 28, VEND_DARK)
    rect(g, 21, 32, 24, 33, VEND_DARK)  # the note slot
    tx0, ty0, tx1, ty1 = VEND_TRAY
    rect(g, tx0 - 1, ty0 - 1, tx1 + 1, ty0, VEND_BODY_SH)
    rect(g, tx0, ty0, tx1, ty1, VEND_DARK)
    rect(g, 1, h - 5, w - 1, h - 1, VEND_BODY_SH)  # the plinth, vented
    for x in range(3, VEND_EAST - 1, 2):
        rect(g, x, h - 4, x + 1, h - 2, VEND_DARK)
    return g


def vending_machine():
    """A vending machine: at rest, then a vend per drink, the panel flashing
    as the pick's can leaves its shelf, drops past the shelves below and lands
    on its side in the tray."""
    rest = vending_body()
    frames = [rest]
    for drink in range(len(VEND_DRINKS)):
        col, shelf = vend_pick(drink)
        for step in range(VEND_STEPS):
            g = [row[:] for row in rest]
            if 1 <= step <= 4:  # its slot stands empty
                rect(g, col, shelf, col + VEND_CAN_W, shelf + VEND_CAN_H, VEND_DARK)
                rect(
                    g, 2, 2, VEND_EAST - 1, 3, WHITE
                )  # the panel flashes while it vends
            if step == 1:  # dropping in front of the bottom shelf
                vend_can(g, col, VEND_GLASS[3] - VEND_CAN_H, VEND_DRINKS[drink])
            if 2 <= step <= 4:
                tx0, _, _, ty1 = VEND_TRAY
                vend_can_lying(
                    g, tx0 + 2 + drink * 2, ty1 - VEND_CAN_W + 1, VEND_DRINKS[drink]
                )
            frames.append(g)
    return [union_outlined(f) for f in frames]


def union_outlined(g):
    union_outline(g)
    return g


def vending_machine_1x():
    """The vending machine at 1x: its lit panel over three shelves of drinks,
    the display, keypad and coin plate beside them, the pickup tray and the
    plinth, the east side in shade; a vend darkens the pick's cell and shows
    its can in the tray."""
    shelves = (2, 4, 6)
    tray_y = 10

    def body():
        g = canvas(VEND_W, VEND_H)
        rect(g, 0, 0, VEND_W, VEND_H, VEND_BODY)
        rect(g, 0, 0, VEND_W - 2, 1, VEND_PANEL_LT)
        rect(g, 0, 1, VEND_W - 2, 2, VEND_PANEL)
        rect(g, 1, shelves[0], VEND_W - 2, shelves[-1] + 2, VEND_DARK)
        for si, sy in enumerate(shelves):
            for ci in range(VEND_W - 3):
                put(g, 1 + ci, sy, vend_drink(si, ci))
            rect(g, 1, sy + 1, VEND_W - 2, sy + 2, SLATE)
        put(g, VEND_W - 2, 2, CYAN)
        put(g, VEND_W - 2, 3, KEYCAP)
        put(g, VEND_W - 2, 5, VEND_TRIM)
        rect(g, 1, tray_y, VEND_W - 2, tray_y + 1, VEND_DARK)
        rect(g, VEND_W - 1, 1, VEND_W, VEND_H, VEND_BODY_SH)
        rect(g, 0, VEND_H - 1, VEND_W, VEND_H, VEND_BODY_SH)
        return g

    rest = body()
    frames = [rest]
    for drink in range(len(VEND_DRINKS)):
        shelf = drink % len(shelves)
        col = next(
            c for c in range(VEND_W - 3) if vend_drink(shelf, c) == VEND_DRINKS[drink]
        )
        for step in range(VEND_STEPS):
            g = [row[:] for row in rest]
            if 1 <= step <= 4:
                put(g, 1 + col, shelves[shelf], VEND_DARK)
            if 2 <= step <= 4:
                put(g, 2, tray_y, VEND_DRINKS[drink])
            frames.append(g)
    return frames


PRN_GLASS_SPAN = (4, 18)  # the scanner glass's columns, half-open
PRN_LID_FRONT = 5  # the lid's front face, under its lit top
PRN_BAY = (3, 8, 22, 14)  # x0, y0, x1, y1: the output bay under the scanner
PRN_SLOT_Y = 8
PRN_STACK_Y = 11
PRN_EAST = 23  # the shaded east side's first column
PRN_DRAWERS = (15, 21)  # each paper drawer's top row
PRN_DRAWER_H = 6


def printer_body(scan=None, led=False, page=0):
    """The printer: a dark lid with its scanner glass, status light and keys,
    the output bay under it with the printed stack, and the light chassis with
    two paper drawers on casters. `scan` lights the glass's column under the
    scan bar, `led` the status light, `page` the rows of a page slid out of the
    slot at the back of the bay."""
    w, h = PRN_W * S, PRN_H * S
    g = canvas(w, h)
    rect(g, 1, PRN_LID_FRONT, w - 1, h - 3, PRN_BODY)
    rect(g, PRN_EAST, PRN_LID_FRONT, w - 1, h - 3, PRN_BODY_SH)
    rect(g, 1, 1, w - 1, PRN_LID_FRONT, PRN_TOP)
    rect(g, 1, 1, w - 1, 2, PRN_TOP_LT)
    rect(g, 1, PRN_LID_FRONT, w - 1, PRN_LID_FRONT + 2, SHADOW)
    gx0, gx1 = PRN_GLASS_SPAN
    rect(g, gx0, 2, gx1, 4, PRN_GLASS)
    if scan is not None:
        rect(g, scan, 2, scan + 1, 4, WHITE)
    put(g, 20, 3, LED_ON if led else KEY_DK)
    rect(g, 22, 2, 25, 4, KEYCAP)
    bx0, by0, bx1, by1 = PRN_BAY
    rect(g, bx0, by0, bx1, by1, SHADOW)
    rect(g, bx0, by1 - 1, bx1, by1 + 1, PRN_TRAY)
    rect(g, bx0 + 3, PRN_STACK_Y, bx1 - 3, by1 - 1, PRN_PAPER)
    rect(g, bx0 + 3, by1 - 2, bx1 - 3, by1 - 1, PRN_PAPER_SH)
    for r in range(page):
        rect(g, bx0 + 4, PRN_SLOT_Y + r, bx1 - 4, PRN_SLOT_Y + 1 + r, PRN_PAPER)
        if r % 2:
            rect(g, bx0 + 5, PRN_SLOT_Y + r, bx1 - 7, PRN_SLOT_Y + 1 + r, PRINT)
    for dy in PRN_DRAWERS:
        rect(
            g, 2, dy + PRN_DRAWER_H - 1, PRN_EAST, dy + PRN_DRAWER_H, SHADOW
        )  # its seam
        rect(g, 8, dy + 2, 16, dy + 3, PRN_BODY_SH)  # its pull
        rect(g, 8, dy + 3, 16, dy + 4, SHADOW)
    for cx in (3, w - 7):
        rect(g, cx, h - 3, cx + 4, h - 1, KEY_DK)  # the casters
    return g


def printer():
    """A printer: at rest, then a print: the scan bar sweeps the glass as the
    page feeds out onto the stack, the status light blinking."""
    gx0, gx1 = PRN_GLASS_SPAN
    sweep = [gx0 + (gx1 - gx0 - 1) * i // 3 for i in range(4)]
    busy = [
        {"scan": sweep[0], "led": True},
        {"scan": sweep[1], "led": False, "page": 1},
        {"scan": sweep[2], "led": True, "page": 2},
        {"scan": sweep[3], "led": False, "page": 3},
        {"led": True, "page": 3},
        {"led": False, "page": 3},
        {"led": True, "page": 3},
        {"led": False},
    ]
    require(len(busy) == PRINT_STEPS, "the printer's busy art fills its PRINT_STEPS")
    return [union_outlined(printer_body(**f)) for f in [{}] + busy]


def printer_1x():
    """The printer at 1x: a dark lid lit along its west end over its glass
    strip and status light, the output bay with its stack, the light chassis
    shaded east with a drawer's pull, on a dark plinth; a print sweeps a light
    across the glass as a page feeds out into the bay, printed as it goes."""

    def body(scan=None, page=0, led=False):
        g = canvas(PRN_W, PRN_H)
        rect(g, 0, 0, PRN_W, 1, PRN_TOP)
        put(g, 0, 0, PRN_TOP_LT)
        rect(g, 0, 1, PRN_W, 2, PRN_TOP)
        rect(g, 1, 1, 5, 2, PRN_GLASS)
        put(g, 5, 1, LED_ON if led else KEY_DK)
        rect(g, 0, 2, PRN_W, PRN_H - 1, PRN_BODY)
        rect(g, PRN_W - 1, 2, PRN_W, PRN_H - 1, PRN_BODY_SH)
        rect(g, 1, 2, 5, 3, PRN_TRAY)
        rect(g, 1, 3, 5, 4, PRN_PAPER)
        rect(g, 2, 5, 5, 6, PRN_TRAY)
        rect(g, 0, PRN_H - 1, PRN_W, PRN_H, KEY_DK)
        if scan is not None:
            put(g, scan, 1, WHITE)
        if page >= 1:  # the page's edge out of the slot
            rect(g, 1, 2, 5, 3, PRN_PAPER)
        if page >= 2:  # printed as it goes
            put(g, 2, 2, PRINT)
        return g

    steps = [
        {"scan": 1, "led": True},
        {"scan": 2, "page": 1},
        {"scan": 3, "page": 2, "led": True},
        {"scan": 4, "page": 2},
        {"page": 2, "led": True},
        {"page": 2},
        {"page": 1, "led": True},
        {},
    ]
    require(len(steps) == PRINT_STEPS, "the printer's steps fill its PRINT_STEPS")
    return [body()] + [body(**f) for f in steps]


# `Furniture::MeetingTable`'s visual box.
TABLE_W, TABLE_H = 11, 5
# The props on the @4x table, (x0, y0, x1, y1) half-open: the grain keeps clear
# of each.
TABLE_LAPTOP = (5, 4, 15, 10)
TABLE_PAD = (19, 5, 30, 12)  # the notepad, its shaded edge and the pen
TABLE_MUG = (34, 5, 39, 9)


def meeting_table():
    """The meeting table: a wood top lit along its far edge with a board seam
    and grain, its near edge catching the light over the front face; a closed
    laptop, a notepad with a pen, and a mug, set well apart."""
    w, h = TABLE_W * S, TABLE_H * S
    g = canvas(w, h)
    rng = Draws(11)
    front = h - 4
    rect(g, 1, 1, w - 1, front, WOOD)
    rect(g, 1, 1, w - 1, 2, WOOD_LT)
    rect(g, 1, front // 2, w - 1, front // 2 + 1, WOOD_SH)
    clear = [
        (x0 - 1, y0 - 1, x1 + 1, y1 + 1)
        for x0, y0, x1, y1 in (TABLE_LAPTOP, TABLE_PAD, TABLE_MUG)
    ]
    for _ in range(6):
        y = rng.randrange(3, front - 2)
        sx = rng.randrange(4, w - 12)
        ex = sx + rng.randrange(5, 9)
        if y == front // 2 or any(
            y0 <= y < y1 and sx < x1 and ex > x0 for x0, y0, x1, y1 in clear
        ):
            continue
        rect(g, sx, y, ex, y + 1, WOOD_SH)
    rect(g, 1, front, w - 1, h - 1, WOOD_SH)
    rect(g, 1, front, w - 1, front + 1, WOOD_HI)
    x0, y0, x1, y1 = TABLE_LAPTOP  # shut
    rect(g, x0, y0, x1, y1, BEZEL)
    rect(g, x0, y0, x1, y0 + 1, SLATE)
    put(g, (x0 + x1) // 2, (y0 + y1) // 2, GREY)
    x0, y0, x1, y1 = TABLE_PAD  # the pad, then its pen
    rect(g, x0, y0, x1 - 4, y1, OFFWHITE)
    rect(g, x1 - 4, y0 + 1, x1 - 3, y1, OFFWHITE_SH)
    for i in range(3):
        rect(g, x0 + 1, y0 + 2 + i * 2, x1 - 5 - (i % 2) * 2, y0 + 3 + i * 2, PRINT)
    rect(g, x1 - 2, y0 + 1, x1 - 1, y1 - 1, BLUE)
    desk_mug(g, TABLE_MUG[0], TABLE_MUG[1])
    union_outline(g)
    return g


def meeting_table_1x():
    """The meeting table at 1x: the lit far edge, the top, a notepad and a cup
    of coffee apart on it, the near edge in shade."""
    g = canvas(TABLE_W, TABLE_H)
    rect(g, 0, 0, TABLE_W, TABLE_H - 1, WOOD)
    rect(g, 0, 0, TABLE_W, 1, WOOD_LT)
    rect(g, 0, TABLE_H - 1, TABLE_W, TABLE_H, WOOD_SH)
    put(g, 3, 2, OFFWHITE)
    put(g, 8, 1, COFFEE)
    return g


# ---- the fixtures: the pantry's island and corner, the lounge, the meeting room, the wall -
# Recoloured from the theme (pack::fixture_overrides).
TANK_WATER, TANK_WATER_DP, TANK_LINE = "Д", "д", "З"
TANK_FISH, TANK_FISH_SH, TANK_FISH_ALT, TANK_FISH_ALT_SH = "И", "и", "Л", "л"
TANK_PLANT, TANK_PLANT_SH = "Ь", "ь"
TRIM_DARK, TRIM_DARK_LT = "ж", "ν"
COOLER, COOLER_LT, COOLER_SH = "б", "в", "ё"
MAGAZINE, MAGAZINE_EDGE = "ы", "э"
COATS, COATS_SH = ("ч", "ш", "щ"), ("α", "β", "γ")
CLOCK_RIM, CLOCK_RIM_LT, CLOCK_FACE, CLOCK_FACE_SH, CLOCK_HAND = "ф", "η", "ц", "ε", "з"
# Un-themed: the cooler's bottle in the classic's own blue, the bin in the pack's nearest greys.
WATER, WATER_SH = "χ", "τ"
BIN, BIN_RIM, BIN_SH = "φ", "6", "7"
DOOR_FRAME, CHROME = "E", "K"


# `Furniture::KitchenIsland`'s visual box; its top two rows are the counter.
ISLAND_W, ISLAND_H = 20, 7
ISLAND_TOP_ROWS = 2


def kitchen_island():
    """The kitchen island: a lit wood counter overhanging its cabinets, a fruit
    bowl and a mug on it, four doors with their pulls, the toe-kick in shade."""
    w, h = ISLAND_W * S, ISLAND_H * S
    g = canvas(w, h)
    top = ISLAND_TOP_ROWS * S
    # the cabinets, a logical column in under the counter's overhang
    rect(g, S + 1, top, w - S - 1, h - 3, WOOD)
    rect(
        g, w - S - 4, top, w - S - 1, h - 3, WOOD_SH
    )  # the east face turned from the light
    rect(
        g, S + 1, top, w - S - 1, top + 1, WOOD_DK
    )  # the counter's shadow on the doors
    doors = 4
    span = (w - 2 * S - 2) // doors
    for i in range(doors):
        x0 = S + 1 + i * span
        rect(g, x0 + 2, top + 3, x0 + span - 2, h - 6, WOOD_SH)  # the recessed panel
        rect(g, x0 + 3, top + 4, x0 + span - 3, h - 7, WOOD)
        if i:
            rect(g, x0, top + 1, x0 + 1, h - 3, WOOD_DK)  # the seam between doors
        px = (
            x0 + span - 4 if i % 2 == 0 else x0 + 3
        )  # the pulls face the seam they share
        rect(g, px, top + 6, px + 1, top + 10, LAMP_HI)
    rect(g, S + 1, h - 5, w - S - 1, h - 3, SHADOW)  # the toe-kick
    # the counter: lit top, its far edge catching the light, its lip in shade
    rect(g, 1, 1, w - 1, top + 2, WOOD_LT)
    rect(g, 1, 1, w - 1, 2, WOOD_HI)
    rect(g, 1, top, w - 1, top + 2, WOOD)
    rect(g, 1, top + 1, w - 1, top + 2, WOOD_SH)
    for x, y in ((1, 1), (w - 2, 1), (1, top + 1), (w - 2, top + 1)):
        put(g, x, y, T)  # rounded corners
    rect(g, 9, 3, 21, 7, OFFWHITE)
    rect(g, 10, 7, 20, 8, OFFWHITE_SH)
    for x, y, k in (
        (10, 2, RED),
        (13, 2, GREEN),
        (16, 2, VERMILION),
        (12, 4, GOLD),
        (15, 4, RED),
    ):
        rect(g, x, y, x + 3, y + 3, k)
        put(g, x, y, WHITE)
    # a mug, east, clear of the bowl
    desk_mug(g, w - 16, 3)
    union_outline(g)
    return g


def kitchen_island_1x():
    """The kitchen island at 1x: the counter lit along its far edge with the
    fruit and a mug on it, the cabinets under its overhang split into two doors
    with their pulls, the base in shade."""
    g = canvas(ISLAND_W, ISLAND_H)
    rect(g, 0, 0, ISLAND_W, 1, WOOD_HI)
    rect(g, 0, 1, ISLAND_W, ISLAND_TOP_ROWS, WOOD_LT)
    rect(g, 1, ISLAND_TOP_ROWS, ISLAND_W - 1, ISLAND_H - 1, WOOD)
    rect(g, 1, ISLAND_H - 1, ISLAND_W - 1, ISLAND_H, WOOD_SH)
    for x, y in ((0, 0), (ISLAND_W - 1, 0)):
        put(g, x, y, T)
    mid = ISLAND_W // 2
    rect(g, mid, ISLAND_TOP_ROWS, mid + 1, ISLAND_H - 1, WOOD_DK)
    put(g, mid - 2, 3, WOOD_DK)
    put(g, mid + 2, 3, WOOD_DK)
    put(g, 3, 0, RED)
    put(g, 4, 0, GOLD)
    put(g, ISLAND_W - 5, 0, MUG)
    return g


# `Furniture::LoungeSideTable`'s visual box.
SIDE_TABLE_W, SIDE_TABLE_H = 7, 4


def side_table():
    """The lounge side table: a lit wood top with a magazine lying on a second,
    its front edge in shade on two legs."""
    w, h = SIDE_TABLE_W * S, SIDE_TABLE_H * S
    g = canvas(w, h)
    rect(g, 1, 1, w - 1, 11, WOOD_LT)
    rect(g, 1, 1, w - 1, 2, WOOD_HI)
    rect(g, 1, 10, w - 1, 12, WOOD)
    rect(g, 1, 11, w - 1, 12, WOOD_SH)
    for x0 in (3, w - 6):
        rect(g, x0, 12, x0 + 3, h - 1, WOOD_DK)
        rect(g, x0, 12, x0 + 1, h - 1, WOOD_SH)
    # the magazines: the lower one askew, the upper with its title band
    rect(g, 10, 4, 22, 9, MAGAZINE_EDGE)
    rect(g, 7, 3, 19, 9, MAGAZINE)
    rect(g, 7, 8, 19, 9, MAGAZINE_EDGE)
    rect(g, 9, 4, 17, 5, WHITE)
    rect(g, 9, 6, 13, 7, OFFWHITE)
    union_outline(g)
    return g


def side_table_1x():
    """The side table at 1x: its lit top with a magazine on it, the front edge
    in shade."""
    g = canvas(SIDE_TABLE_W, SIDE_TABLE_H)
    rect(g, 0, 0, SIDE_TABLE_W, 1, WOOD_HI)
    rect(g, 0, 1, SIDE_TABLE_W, SIDE_TABLE_H - 1, WOOD_LT)
    rect(g, 0, SIDE_TABLE_H - 1, SIDE_TABLE_W, SIDE_TABLE_H, WOOD_SH)
    cx, cy = SIDE_TABLE_W // 2, SIDE_TABLE_H // 2
    rect(g, cx - 1, cy - 1, cx + 2, cy, MAGAZINE)
    rect(g, cx - 1, cy, cx + 2, cy + 1, MAGAZINE_EDGE)
    return g


# `layout::WATER_COOLER`: `PantryRoom::water_cooler_rect`'s size.
COOLER_W, COOLER_H = 4, 9
# The glug: a bubble climbs the bottle, then the water stills.
GLUG_STEPS = 5
COOLER_BOTTLE_Y1 = 14  # the bottle's rows end here, over the neck
COOLER_CABINET_Y = 16


def water_cooler():
    """A water cooler: the upturned bottle, ribbed, lit down its west side, its
    neck in the cabinet's collar; the hot and cold taps over the drip tray in
    the lit cabinet, a vent grille on its door, the east side in shade; a
    bubble glugs up the bottle, then the water stills."""

    def body(bubble):
        w, h = COOLER_W * S, COOLER_H * S
        g = canvas(w, h)
        rect(g, 2, 2, w - 2, COOLER_BOTTLE_Y1, WATER)  # the bottle, upside down
        rect(g, 3, 1, w - 3, 2, WATER)
        rect(g, w - 5, 2, w - 2, COOLER_BOTTLE_Y1, WATER_SH)
        for ry in (6, 10):  # its ribs
            rect(g, 2, ry, w - 2, ry + 1, WATER_SH)
        rect(g, 4, 3, 5, 12, CYAN)  # its glint
        put(g, 5, 2, CYAN)
        rect(g, 5, COOLER_BOTTLE_Y1, w - 5, COOLER_CABINET_Y, WATER_SH)  # the neck
        rect(g, 1, COOLER_CABINET_Y, w - 1, h - 1, COOLER)
        rect(g, 1, COOLER_CABINET_Y, w - 1, COOLER_CABINET_Y + 1, COOLER_LT)
        rect(g, w - 4, COOLER_CABINET_Y + 1, w - 1, h - 1, COOLER_SH)
        rect(g, 3, 19, w - 4, 26, SHADOW)  # the dispensing alcove
        rect(g, 4, 19, 6, 21, RED)
        rect(g, w - 7, 19, w - 5, 21, BLUE)
        rect(g, 3, 25, w - 4, 26, GREY)  # the drip tray
        for vy in range(28, h - 2, 2):  # the door's vent grille
            rect(g, 4, vy, w - 6, vy + 1, COOLER_SH)
        if bubble is not None:
            bx, by = bubble
            rect(g, bx, by, bx + 2, by + 2, TANK_LINE)
        union_outline(g)
        return g

    rises = [(7, 11), (7, 4)]
    return [body(rises[i] if i < len(rises) else None) for i in range(GLUG_STEPS)]


def water_cooler_1x():
    """The water cooler at 1x: the bottle, glinting west, over the cabinet shaded
    east, its hot and cold taps over the alcove; a bubble glugs up the bottle,
    then the water stills."""
    bottle = 3

    def body(bubble_y):
        g = canvas(COOLER_W, COOLER_H)
        rect(g, 0, 0, COOLER_W, bottle, WATER)
        rect(g, COOLER_W - 1, 0, COOLER_W, bottle, WATER_SH)
        put(g, 0, 0, CYAN)
        rect(g, 0, bottle, COOLER_W, COOLER_H, COOLER)
        rect(g, 0, bottle, COOLER_W, bottle + 1, COOLER_LT)
        rect(g, COOLER_W - 1, bottle, COOLER_W, COOLER_H, COOLER_SH)
        put(g, 1, bottle + 1, RED)
        put(g, 2, bottle + 1, BLUE)
        rect(g, 1, bottle + 2, 3, bottle + 3, SHADOW)
        if bubble_y is not None:
            put(g, 1, bubble_y, TANK_LINE)
        return g

    rises = [2, 1]
    return [body(rises[i] if i < len(rises) else None) for i in range(GLUG_STEPS)]


# `PantryRoom::trash_bin_rect`'s size.
BIN_W, BIN_H = 4, 5


def trash_bin():
    """The pantry's trash bin: its rim lit, the bag's liner folded over it with a crumpled
    sheet on top, the ribbed body shaded east."""
    w, h = BIN_W * S, BIN_H * S
    g = canvas(w, h)
    rect(g, 2, 7, w - 2, h - 1, BIN)  # the body
    rect(g, 3, 15, w - 3, h - 1, BIN)
    rect(g, 2, 15, 3, h - 1, T)
    rect(g, w - 3, 15, w - 2, h - 1, T)
    rect(g, 2, 7, 4, 15, BIN_RIM)
    rect(g, w - 4, 7, w - 2, 15, BIN_SH)
    for x in range(5, w - 4, 3):
        rect(g, x, 8, x + 1, h - 2, BIN_SH)  # ribs
    rect(g, 1, 3, w - 1, 7, BIN_RIM)  # the rim
    rect(g, 3, 4, w - 3, 7, OFFWHITE)  # the liner inside it
    rect(g, 3, 6, w - 3, 7, OFFWHITE_SH)
    rect(g, 7, 1, 11, 5, OFFWHITE)  # a crumpled sheet
    put(g, 9, 2, OFFWHITE_SH)
    put(g, 8, 3, OFFWHITE_SH)
    put(g, 10, 4, OFFWHITE_SH)
    union_outline(g)
    return g


def trash_bin_1x():
    """The trash bin at 1x: the rim round the liner, the bag's fill, the body
    shaded east."""
    g = canvas(BIN_W, BIN_H)
    rect(g, 0, 0, BIN_W, 1, BIN_RIM)
    rect(g, 1, 0, BIN_W - 1, 1, OFFWHITE)
    rect(g, 0, 1, BIN_W, BIN_H, BIN)
    rect(g, 1, 1, BIN_W - 1, 2, OFFWHITE_SH)
    rect(g, BIN_W - 1, 2, BIN_W, BIN_H, BIN_SH)
    return g


# `Furniture::FishTank`'s visual box.
TANK_W, TANK_H = 14, 11
TANK_WATER_ROWS = (1, 8)  # half-open: the surface line, then water, the gravel last
TANK_CABINET_Y = 9
# The fish patrol: each swims its lane to the far wall and back, one column a step,
# the second TANK_FISH_LAG steps behind the first so the pair never mirror.
TANK_LANES = (3, 5)
TANK_SPAN = TANK_W - 5
TANK_STEPS = 2 * TANK_SPAN
TANK_FISH_LAG = 7
TANK_FISH_LEN = 3
# A bubble climbs from the gravel to the surface, then the next one starts.
TANK_BUBBLE_X = TANK_W - 3
TANK_BUBBLE_ROWS = (6, 5, 4, 3, 2, None)
TANK_PLANT_AT = ((2, 5), (2, 6), (2, 7), (3, 6))
require(TANK_STEPS % len(TANK_BUBBLE_ROWS) == 0, "the bubble cycle divides TANK_STEPS")


def tank_fish_at(step):
    """Where a fish starts its lane and which way it swims, `step` of its lap."""
    step %= TANK_STEPS
    if step < TANK_SPAN:
        return 1 + step, 1
    return 1 + TANK_STEPS - step, -1


def fish_tank():
    """An aquarium on its cabinet: two fish patrolling opposite lanes past the
    swaying weed, a bubble rising from the gravel, the surface rippling, the
    glass catching the light."""
    w, h = TANK_W * S, TANK_H * S
    top, bottom = TANK_WATER_ROWS[0] * S, TANK_WATER_ROWS[1] * S
    frames = []
    for step in range(TANK_STEPS):
        g = canvas(w, h)
        rect(g, 1, 1, w - 1, bottom + S, TRIM_DARK)  # the frame
        rect(g, 1, 1, w - 1, 2, TRIM_DARK_LT)
        rect(g, 4, top, w - 4, bottom - S, TANK_WATER)
        for y in range(top + 2 * S, bottom - S):  # the deep water, dithered in
            for x in range(4, w - 4):
                deep = (
                    y - (top + 2 * S) >= 2 * S
                    or (x + y) % 2 == 0
                    and y - (top + 2 * S) >= S
                )
                if deep:
                    put(g, x, y, TANK_WATER_DP)
        for x in range(4, w - 4):  # the surface, rippling
            put(g, x, top, TANK_LINE)
            if (x + step) % 6 < 2:
                put(g, x, top + 1, TANK_LINE)
        for x in range(4, w - 4):  # the gravel bed
            for y in range(bottom - S, bottom):
                put(g, x, y, (TAN, BROWN, GOLD, BROWN)[(x * 3 + y * 5) % 4])
        # the weed, its tips swaying with the water
        sway = (0, 1, 1, 0, -1, -1)[step % 6]
        for x0, y0, tall in ((7, bottom - S, 16), (w - 12, bottom - S, 10)):
            for i in range(tall):
                dx = sway if i > tall // 2 else 0
                put(g, x0 + dx, y0 - i, TANK_PLANT)
                put(g, x0 + dx + 1, y0 - i, TANK_PLANT_SH)
                if i % 4 == 2:
                    put(g, x0 + dx - 1, y0 - i, TANK_PLANT)
        for lane, lag, body, shade in (
            (TANK_LANES[0], 0, TANK_FISH, TANK_FISH_SH),
            (TANK_LANES[1], TANK_FISH_LAG, TANK_FISH_ALT, TANK_FISH_ALT_SH),
        ):
            start, heading = tank_fish_at(step + lag)
            x0, y0 = start * S, lane * S
            fl = TANK_FISH_LEN * S - 2
            rect(g, x0 + 1, y0, x0 + fl, y0 + 3, body)
            rect(g, x0 + 2, y0 - 1, x0 + fl - 2, y0, body)
            rect(g, x0 + 1, y0 + 2, x0 + fl, y0 + 3, shade)
            tail = x0 if heading > 0 else x0 + fl
            rect(g, tail, y0 - 1, tail + 1, y0 + 4, shade)  # the tail fin, flicking
            if step % 2:
                put(g, tail, y0 - 1, TANK_WATER)
            head = x0 + fl - 2 if heading > 0 else x0 + 2
            put(g, head, y0, KEY_DK)
        row = TANK_BUBBLE_ROWS[step % len(TANK_BUBBLE_ROWS)]
        if row is not None:
            bx, by = TANK_BUBBLE_X * S, row * S + 1
            rect(g, bx, by, bx + 2, by + 2, TANK_LINE)
        for x, y in ((6, top + 3), (5, top + 4), (5, top + 5)):
            put(g, x, y, WHITE)  # the glass's glint
        rect(g, 1, TANK_CABINET_Y * S, w - 1, h - 1, WOOD)
        rect(g, 1, TANK_CABINET_Y * S, w - 1, TANK_CABINET_Y * S + 1, WOOD_HI)
        rect(g, 1, h - 3, w - 1, h - 1, WOOD_SH)
        mid = w // 2
        rect(g, mid, TANK_CABINET_Y * S + 1, mid + 1, h - 1, WOOD_DK)
        put(g, mid - 3, TANK_CABINET_Y * S + 3, LAMP_HI)
        put(g, mid + 3, TANK_CABINET_Y * S + 3, LAMP_HI)
        union_outline(g)
        frames.append(g)
    return frames


def fish_tank_1x():
    """The aquarium at 1x: the frame lit along its top, the surface line, two
    fish patrolling their lanes, a bubble rising, a weed sprig on the gravel,
    the cabinet under it."""
    frames = []
    for step in range(TANK_STEPS):
        g = canvas(TANK_W, TANK_H)
        rect(g, 0, 0, TANK_W, TANK_WATER_ROWS[1] + 1, TRIM_DARK)
        rect(g, 0, 0, TANK_W, 1, TRIM_DARK_LT)
        rect(g, 1, TANK_WATER_ROWS[0], TANK_W - 1, TANK_WATER_ROWS[1] - 1, TANK_WATER)
        rect(g, 1, TANK_WATER_ROWS[0], TANK_W - 1, TANK_WATER_ROWS[0] + 1, TANK_LINE)
        for x in range(1, TANK_W - 1):
            put(g, x, TANK_WATER_ROWS[1] - 1, BROWN if x % 2 == 0 else TAN)
        for lane, lag, body in (
            (TANK_LANES[0], 0, TANK_FISH),
            (TANK_LANES[1], TANK_FISH_LAG, TANK_FISH_ALT),
        ):
            start, _ = tank_fish_at(step + lag)
            rect(g, start, lane, start + TANK_FISH_LEN, lane + 1, body)
        row = TANK_BUBBLE_ROWS[step % len(TANK_BUBBLE_ROWS)]
        if row is not None:
            put(g, TANK_BUBBLE_X, row, TANK_LINE)
        for x, y in TANK_PLANT_AT:  # last, so the fish swim behind it
            put(g, x, y, TANK_PLANT)
        rect(g, 0, TANK_CABINET_Y, TANK_W, TANK_H - 1, WOOD_LT)
        put(g, TANK_W // 2, TANK_CABINET_Y, WOOD_DK)
        rect(g, 0, TANK_H - 1, TANK_W, TANK_H, WOOD_SH)
        frames.append(g)
    return frames


# `coat_rack_rect_at`'s box around the pole, and where its coats hang: the
# layout's `COAT_HOOK_DX`, `COAT_W`, `COAT_RACK_BASE_DY`.
COAT_HOOK_DX, COAT_W, COAT_RACK_BASE_DY = 1, 2, 11
COAT_REACH = COAT_HOOK_DX + COAT_W - 1
RACK_W, RACK_H = 2 * COAT_REACH + 1, COAT_RACK_BASE_DY + 1


COAT_DROP = 3  # a coat's length at @Nx, in logical rows


def coat_hooks():
    """Each coat's (x0, y0) in logical units: alternating sides down the pole."""
    return [
        (0 if i % 2 == 0 else COAT_REACH + COAT_HOOK_DX, 1 + i * 2)
        for i in range(len(COATS))
    ]


def coat_rack():
    """A coat rack: a turned wood pole with a hat on its top and a foot, three
    coats hung on alternating pegs, each sloping from its collar to square
    shoulders and falling straight to a flared hem, a sleeve down its outer
    side, its front edge closed, the side away from the light in shade."""
    w, h = RACK_W * S, RACK_H * S
    g = canvas(w, h)
    mid = COAT_REACH * S + S // 2
    rect(g, mid - 1, 3, mid + 1, h - 3, WOOD)  # the pole
    rect(g, mid - 1, 3, mid, h - 3, WOOD_LT)
    rect(g, mid - 2, 1, mid + 2, 3, BROWN)  # a hat on its top
    put(g, mid - 2, 1, TAN)
    rect(g, mid - 4, 3, mid + 4, 4, BROWN)
    rect(g, 3, h - 4, w - 3, h - 2, WOOD)  # its foot
    rect(g, 3, h - 4, w - 3, h - 3, WOOD_LT)
    for (lx, ly), coat, shade in zip(coat_hooks(), COATS, COATS_SH):
        west = lx == 0
        x0, y0 = lx * S, ly * S
        peg = x0 + COAT_W * S - 1 if west else x0
        rect(g, min(peg, mid), y0, max(peg, mid) + 1, y0 + 1, WOOD_DK)  # the peg
        top, hem = y0 + 1, y0 + COAT_DROP * S + 1
        cx = peg - 1 if west else peg + 1
        outer = -1 if west else 1
        for y in range(top, hem):
            t = y - top
            half = min(t + 1, 3) + (t >= (hem - top) * 2 // 3)
            rect(g, cx - half, y, cx + half + 1, y + 1, coat)
            put(g, cx + half, y, shade)  # the east side, turned from the light
            if 2 <= t < (hem - top) * 2 // 3:
                put(g, cx + outer * 2, y, shade)  # the sleeve's seam
        rect(
            g, cx - 1, top, cx + 2, top + 1, WHITE if coat != COATS[2] else OFFWHITE_SH
        )  # the collar
        for y in range(top + 1, hem - 1):
            put(g, cx, y, shade)  # the front edge
        rect(g, cx - 4, hem - 1, cx + 5, hem, shade)  # the hem
    union_outline(g)
    return g


def coat_rack_1x():
    """The coat rack at 1x: the pole with its knob and foot, three coats on
    alternating hooks, each lit at its shoulders and shaded at its hem."""
    g = canvas(RACK_W, RACK_H)
    rect(g, COAT_REACH, 0, COAT_REACH + 1, RACK_H, WOOD_SH)
    put(g, COAT_REACH, 0, WOOD_LT)
    rect(g, COAT_REACH - 1, RACK_H - 1, COAT_REACH + 2, RACK_H, WOOD)
    for (x0, y0), coat, shade in zip(coat_hooks(), COATS, COATS_SH):
        rect(g, x0, y0, x0 + COAT_W, y0 + 1, coat)
        rect(g, x0, y0 + 1, x0 + COAT_W, y0 + 2, shade)
    return g


# `MeetingRoom::notice_board_rect`'s size.
BOARD_W, BOARD_H = 8, 5


def notice_board():
    """A meeting room's notice board: cork in a wood frame lit along its top, a
    sticky note, an agenda and a card pinned to it."""
    w, h = BOARD_W * S, BOARD_H * S
    g = canvas(w, h)
    rect(g, 1, 1, w - 1, h - 1, WOOD)
    rect(g, 1, 1, w - 1, 2, WOOD_LT)
    rect(g, 1, h - 2, w - 1, h - 1, WOOD_SH)
    rect(g, 3, 3, w - 3, h - 3, CORK)
    for x, y in ((5, 14), (12, 4), (19, 15), (26, 6), (9, 9)):
        put(g, x, y, CORK_SH)
    rect(g, 4, 5, 9, 10, PINK)  # a sticky note
    rect(g, 5, 7, 8, 8, PRINT)
    rect(g, 12, 6, 19, 15, OFFWHITE)  # the agenda
    for i in range(3):
        rect(g, 13, 8 + i * 2, 18 - (i % 2) * 2, 9 + i * 2, PRINT)
    rect(g, 22, 5, 27, 10, GOLD)  # a card
    rect(g, 23, 7, 26, 8, PRINT)
    for x, y in ((6, 5), (15, 6), (24, 5)):
        put(g, x, y, RED)  # the pins
    union_outline(g)
    return g


def notice_board_1x():
    """The notice board at 1x: cork in a wood frame, a sticky note and a sheet
    pinned to it."""
    g = canvas(BOARD_W, BOARD_H)
    rect(g, 0, 0, BOARD_W, BOARD_H, WOOD)
    rect(g, 0, 0, BOARD_W, 1, WOOD_LT)
    rect(g, 1, 1, BOARD_W - 1, BOARD_H - 1, CORK)
    put(g, 2, 1, PINK)
    rect(g, 4, 2, 6, 3, OFFWHITE)
    return g


# `layout::CLOCK`. The dial only: the painter draws the hands from the time, which
# as art would be 720 frames.
CLOCK_W, CLOCK_H = 7, 7
# Art pixels from the dial's edge to its face: the outline and the rim.
CLOCK_RIM_PX = 3
CLOCK_1X = ("..RRR..", ".RFFFR.", "RFFFFFR", "RFFFFFR", "RFFFFFR", ".RFFFR.", "..RRR..")


def wall_clock():
    """The wall clock's dial: the rim lit on its upper west, the face shaded
    round its lower east, the hour ticks and the centre pin the hands turn on."""
    w, h = CLOCK_W * S, CLOCK_H * S
    g = canvas(w, h)
    c = (w / 2, h / 2)
    r_out, r_face = w / 2 - 1, w / 2 - CLOCK_RIM_PX
    for y in range(h):
        for x in range(w):
            dx, dy = x + 0.5 - c[0], y + 0.5 - c[1]
            d = math.hypot(dx, dy)
            if d > r_out:
                continue
            if d > r_face:
                put(g, x, y, CLOCK_RIM_LT if dx + dy < -r_face * 0.6 else CLOCK_RIM)
            elif d > r_face - 1.5 and dx + dy > r_face * 0.8:
                put(g, x, y, CLOCK_FACE_SH)
            else:
                put(g, x, y, CLOCK_FACE)
    for i in range(12):
        a = i * math.pi / 6
        major = i % 3 == 0
        for rr in (r_face - 1.5, r_face - 3.5) if major else (r_face - 1.5,):
            put(
                g,
                int(c[0] + rr * math.sin(a)),
                int(c[1] - rr * math.cos(a)),
                CLOCK_HAND,
            )
    rect(g, int(c[0]) - 1, int(c[1]) - 1, int(c[0]) + 1, int(c[1]) + 1, CLOCK_HAND)
    union_outline(g)
    return g


def wall_clock_1x():
    """The wall clock's dial at 1x: the rim lit along its top, the face, the
    centre pin the hands turn on."""
    g = canvas(CLOCK_W, CLOCK_H)
    for y, row in enumerate(CLOCK_1X):
        for x, ch in enumerate(row):
            if ch != ".":
                put(g, x, y, CLOCK_RIM if ch == "R" else CLOCK_FACE)
    for x in range(2, 5):
        put(g, x, 0, CLOCK_RIM_LT)
    put(g, CLOCK_W // 2, CLOCK_H // 2, CLOCK_HAND)
    return g


# `Furniture::MeetingChair`'s visual box, drawn for a sitter facing east.
CHAIR_W, CHAIR_H = 7, 7
CHAIR_SEAT_ROWS = (1, 5)  # half-open
CHAIR_LEG_COLS = (1, 5)


def meeting_chair():
    """A head-of-table meeting chair in the sofas' fabric: its back to the
    west, the seat cushion lit along its far edge and shaded at its front, on
    four wood legs."""
    w, h = CHAIR_W * S, CHAIR_H * S
    g = canvas(w, h)
    y0, y1 = CHAIR_SEAT_ROWS[0] * S, CHAIR_SEAT_ROWS[1] * S
    for lx in CHAIR_LEG_COLS:
        rect(g, lx * S, y1, lx * S + 3, h - 1, WOOD_DK)
        rect(g, lx * S, y1, lx * S + 1, h - 1, WOOD_SH)
    rect(g, S, y0, w - 2, y1, FABRIC)  # the seat
    rect(g, S, y0, w - 2, y0 + 2, FABRIC_HI)
    rect(g, S, y1 - 3, w - 2, y1, FABRIC_SH)
    rect(g, S + 2, y0 + 3, w - 4, y1 - 4, FABRIC)  # its cushion's welt
    rect(g, S + 1, y0 + 2, S + 2, y1 - 3, FABRIC_SEAM)
    rect(g, 1, 1, S, y1, FABRIC)  # the back
    rect(g, 1, 1, S, 3, FABRIC_HI)
    rect(g, 1, 1, 2, y1, FABRIC_HI)
    rect(g, S - 1, 3, S, y1, FABRIC_SEAM)
    union_outline(g)
    return g


def meeting_chair_1x():
    """The meeting chair at 1x: its back to the west in the seat's fabric, the
    seat lit along its far edge, two legs showing."""
    g = canvas(CHAIR_W, CHAIR_H)
    rect(g, 0, 0, 1, CHAIR_SEAT_ROWS[1], FABRIC_SH)
    rect(g, 1, CHAIR_SEAT_ROWS[0], CHAIR_W - 1, CHAIR_SEAT_ROWS[1], FABRIC)
    rect(g, 1, CHAIR_SEAT_ROWS[0], CHAIR_W - 1, CHAIR_SEAT_ROWS[0] + 1, FABRIC_HI)
    for lx in CHAIR_LEG_COLS:
        rect(g, lx, CHAIR_SEAT_ROWS[1], lx + 1, CHAIR_H, WOOD_DK)
    return g


# The 1x `door.sprite`'s size, its panels' rows, and each frame's gap.
DOOR_W, DOOR_H = 16, 14
DOOR_PANEL_ROWS = (3, 13)  # half-open
DOOR_GAPS = (0, 4, 8)  # shut, half-open, open: the shaft columns showing


def elevator_door():
    """The elevator: a brushed-steel frame lit along its top and west, the
    floor display, and the chrome doors: shut, parting, open on a car lit
    from its ceiling, its handrail and floor."""
    w, h = DOOR_W * S, DOOR_H * S
    frames = []
    for gap in DOOR_GAPS:
        g = canvas(w, h)
        rect(g, 1, 1, w - 1, h - 1, DOOR_FRAME)
        rect(g, 1, 1, w - 1, 2, ALU)
        rect(g, 1, 1, 2, h - 1, ALU)
        rect(g, 4, 4, w - 4, 8, CYAN)  # the display
        rect(g, 4, 4, w - 4, 5, WHITE)
        for x in range(8, 13):  # the floor arrow
            put(g, x, 6 - min(x - 8, 12 - x) // 2, GOLD)
        rect(g, 16, 6, 18, 7, GOLD)
        rect(g, 20, 6, 22, 7, GOLD)
        p0, p1 = DOOR_PANEL_ROWS[0] * S, DOOR_PANEL_ROWS[1] * S
        x0, x1 = S, w - S
        mid = w // 2
        half = gap * S // 2
        if gap:  # the car, lit from its ceiling
            rect(g, mid - half, p0, mid + half, p1, LAMP)
            rect(g, mid - half, p0, mid + half, p0 + 2, BULB)
            rect(g, mid - half, p0 + 2, mid + half, p0 + 4, LAMP_HI)
            rect(g, mid - half, p0 + 22, mid + half, p0 + 23, GREY)  # the handrail
            rect(g, mid - half, p1 - 4, mid + half, p1, SLATE)
        for a, b in ((x0, mid - half), (mid + half, x1)):
            if b - a <= 0:
                continue
            rect(g, a, p0, b, p1, CHROME)
            rect(g, a, p0, a + 1, p1, WHITE)  # the lit edge of each leaf
            rect(g, b - 2, p0, b, p1, STEEL_SH)
            for x in range(a + 4, b - 3, 5):
                rect(g, x, p0 + 3, x + 1, p1 - 8, STEEL_SH)  # the brushing
            rect(g, a, p1 - 6, b, p1, STEEL_SH)  # the kick plate
        if not gap:
            rect(g, mid - 1, p0, mid + 1, p1, SHADOW)  # the doors' meeting line
        rect(g, 1, p1, w - 1, p1 + 1, ALU)  # the sill
        union_outline(g)
        frames.append(g)
    return frames


# ---- the city behind the windows: its buildings ------------------------------------
# Drawn only in the [city] materials: a painter colours each by its depth and the
# sky, so no drawing here carries a colour of its own. Each is drawn at `S`; its base
# is that drawing read at 1x, block by block (`city_base`).
CITY_FACADE, CITY_SHADE, CITY_ROOF, CITY_GLASS, CITY_MULLION, CITY_DETAIL, CITY_SIGN = (
    "+",
    "-",
    "~",
    "0",
    "|",
    "*",
    "=",
)
# pack.toml's `[city]` names these keys; `--check` fails where the two differ.
CITY = {
    "facade": CITY_FACADE,
    "shade": CITY_SHADE,
    "roof": CITY_ROOF,
    "glass": CITY_GLASS,
    "mullion": CITY_MULLION,
    "detail": CITY_DETAIL,
    "sign": CITY_SIGN,
}


def panes(g, x0, y0, x1, y1, w, h, px, py):
    """A grid of `w`x`h` windows at pitch `px`,`py` inside the rect."""
    for y in range(y0, y1 - h + 1, py):
        for x in range(x0, x1 - w + 1, px):
            rect(g, x, y, x + w, y + h, CITY_GLASS)


def shade_east(g):
    """The east third of each mass on each row turned from the light."""
    for row in g:
        x = 0
        while x < len(row):
            if row[x] == T:
                x += 1
                continue
            end = x
            while end < len(row) and row[end] != T:
                end += 1
            for i in range(x + (end - x) * 2 // 3, end):
                if row[i] == CITY_FACADE:
                    row[i] = CITY_SHADE
            x = end


def building_setback():
    """A slim tower stepping in twice toward a mast."""
    w, h = 6 * S, 16 * S
    g = canvas(w, h)
    for x0, y0 in ((0, 7 * S), (S, 4 * S), (2 * S, 2 * S)):
        rect(g, x0, y0, w - x0, h, CITY_FACADE)
        rect(g, x0, y0, w - x0, y0 + 1, CITY_ROOF)
    rect(g, w // 2 - 1, 0, w // 2 + 1, 2 * S, CITY_DETAIL)
    panes(g, 2, 7 * S + 2, w - 2, h - 2, 2, 2, 3, 4)
    panes(g, S + 2, 4 * S + 2, w - S - 2, 7 * S - 1, 2, 2, 3, 4)
    panes(g, 2 * S + 2, 2 * S + 2, w - 2 * S - 2, 4 * S - 1, 2, 2, 3, 4)
    shade_east(g)
    return g


def building_curtain():
    """A glass curtain wall: bands of glass between thin spandrels."""
    w, h = 6 * S, 15 * S
    g = canvas(w, h)
    rect(g, 0, S, w, h, CITY_FACADE)
    rect(g, 0, S, w, S + 2, CITY_ROOF)
    for y in range(S + 4, h - 1, 3):
        rect(g, 1, y, w - 1, y + 2, CITY_GLASS)
        for x in range(1, w - 1, 4):
            rect(g, x, y, x + 1, y + 2, CITY_MULLION)
    shade_east(g)
    return g


def building_walkup():
    """An old walk-up, its water tank on legs on the roof."""
    w, h = 5 * S, 10 * S
    g = canvas(w, h)
    rect(g, 0, 3 * S, w, h, CITY_FACADE)
    rect(g, 0, 3 * S, w, 3 * S + 2, CITY_ROOF)
    rect(g, 11, 2, 18, 8, CITY_DETAIL)
    rect(g, 11, 1, 18, 2, CITY_ROOF)
    for x in (12, 16):
        rect(g, x, 8, x + 1, 3 * S, CITY_DETAIL)
    panes(g, 2, 3 * S + 4, w - 2, h - 2, 3, 3, 5, 5)
    shade_east(g)
    return g


def building_dome():
    """A civic block under a dome, tall windows between its piers."""
    w, h = 7 * S, 11 * S
    g = canvas(w, h)
    base = 5 * S
    rect(g, 0, base, w, h, CITY_FACADE)
    rect(g, 0, base, w, base + 2, CITY_ROOF)
    for y in range(2 * S, base):
        for x in range(w):
            if (x + 0.5 - w / 2) ** 2 + ((y + 0.5 - base) * 1.1) ** 2 <= 9.5**2:
                g[y][x] = CITY_ROOF if y < base - 7 else CITY_FACADE
    rect(g, w // 2 - 1, S + 2, w // 2 + 1, 2 * S + 3, CITY_DETAIL)
    for x in range(3, w - 3, 5):
        rect(g, x, base + 4, x + 2, h - 3, CITY_GLASS)
    shade_east(g)
    return g


def building_sign():
    """A wide mid-rise carrying a sign on its roof, lit after dark."""
    w, h = 7 * S, 9 * S
    g = canvas(w, h)
    rect(g, 0, 3 * S, w, h, CITY_FACADE)
    rect(g, 0, 3 * S, w, 3 * S + 2, CITY_ROOF)
    rect(g, S, S, w - S, 2 * S + 2, CITY_SIGN)
    rect(g, S, S, w - S, S + 1, CITY_MULLION)
    for x in (S + 3, w - S - 4):
        rect(g, x, 2 * S + 2, x + 1, 3 * S, CITY_DETAIL)
    panes(g, 2, 3 * S + 4, w - 2, h - 2, 4, 2, 6, 4)
    shade_east(g)
    return g


def building_spire():
    """A tower crowned by a stepped spire and a mast."""
    w, h = 4 * S, 18 * S
    g = canvas(w, h)
    rect(g, 0, 8 * S, w, h, CITY_FACADE)
    for i, y in enumerate(range(7 * S, 3 * S, -S)):  # tiers narrowing upward
        rect(g, 1 + i, y, w - 1 - i, y + S, CITY_FACADE)
        rect(g, 1 + i, y, w - 1 - i, y + 1, CITY_ROOF)
    rect(g, w // 2 - 1, 0, w // 2 + 1, 4 * S, CITY_DETAIL)  # down onto the top tier
    panes(g, 2, 8 * S + 3, w - 2, h - 2, 1, 3, 3, 5)
    shade_east(g)
    return g


def building_low():
    """A low block, its roof crowded with plant."""
    w, h = 6 * S, 6 * S
    g = canvas(w, h)
    rect(g, 0, 2 * S, w, h, CITY_FACADE)
    rect(g, 0, 2 * S, w, 2 * S + 2, CITY_ROOF)
    for x0, y0, x1 in ((3, 3, 8), (12, 4, 15), (18, 2, 20)):
        rect(g, x0, y0, x1, 2 * S, CITY_DETAIL)
    panes(g, 2, 2 * S + 4, w - 2, h - 2, 3, 2, 5, 4)
    shade_east(g)
    return g


def building_twin():
    """Twin towers joined by a skybridge, each crowned by a short mast."""
    w, h = 6 * S, 17 * S
    g = canvas(w, h)
    for x0 in (0, 4 * S):
        rect(g, x0, 2 * S, x0 + 2 * S, h, CITY_FACADE)
        rect(g, x0, 2 * S, x0 + 2 * S, 2 * S + 2, CITY_ROOF)
        rect(g, x0 + S - 1, 0, x0 + S + 1, 2 * S, CITY_DETAIL)
        panes(g, x0 + 1, 2 * S + 4, x0 + 2 * S - 1, h - 2, 2, 2, 3, 4)
    rect(g, 2 * S, 8 * S, 4 * S, 9 * S, CITY_FACADE)  # the skybridge
    rect(g, 2 * S, 8 * S + 1, 4 * S, 9 * S - 1, CITY_GLASS)
    shade_east(g)
    return g


def building_slab():
    """A wide slab tower in bands of glass, a lit crown along its top."""
    w, h = 8 * S, 15 * S
    g = canvas(w, h)
    rect(g, 0, S, w, h, CITY_FACADE)
    rect(g, 0, S, w, S + 2, CITY_ROOF)
    rect(g, 2, S + 3, w - 2, S + 5, CITY_SIGN)  # the crown's light strip
    for y in range(3 * S, h - 1, 4):
        rect(g, 1, y, w - 1, y + 2, CITY_GLASS)
        for x in range(5, w - 1, 6):
            rect(g, x, y, x + 1, y + 2, CITY_MULLION)
    shade_east(g)
    return g


def block_read(g, pick):
    """`g`, drawn at `S`, read at 1x: each `S`x`S` block's cells, with the
    block's column and row, to `pick`, which names the 1x cell's key or leaves
    it empty with `None`."""
    h, w = len(g) // S, len(g[0]) // S
    out = canvas(w, h)
    for by in range(h):
        for bx in range(w):
            k = pick(
                [g[by * S + y][bx * S + x] for y in range(S) for x in range(S)], bx, by
            )
            if k is not None:
                out[by][bx] = k
    return out


def city_cell(cells, bx, by):
    """A building's block at 1x: a thin part running through it (a sign, then
    plant or a mast, then a roof line) wins it; a block less than half drawn is
    sky; one holding glass on an odd row and column is glass, the lit-dot grid a
    1x city is read by (the scene's `skyline::block_window`); any other takes
    whichever of facade and shade it holds more of."""
    thin = next(
        (k for k in (CITY_SIGN, CITY_DETAIL, CITY_ROOF) if cells.count(k) >= S), None
    )
    if thin:
        return thin
    if (len(cells) - cells.count(T)) * 2 < len(cells):
        return None
    if CITY_GLASS in cells and bx % 2 == 1 and by % 2 == 1:
        return CITY_GLASS
    return max((CITY_FACADE, CITY_SHADE), key=cells.count)


def city_base(g):
    """A building drawn at `S`, read at 1x."""
    return block_read(g, city_cell)


# Each building, registered in pack.toml's `[buildings]` by hand with the planes it
# stands in (`every_bundled_sprite_is_a_frame_the_pack_loads` fails on one left out).
BUILDINGS = {
    "setback": building_setback,
    "curtain": building_curtain,
    "spire": building_spire,
    "twin": building_twin,
    "slab": building_slab,
    "walkup": building_walkup,
    "dome": building_dome,
    "sign": building_sign,
    "low": building_low,
}


# ---- the creatures: each species' master placed by hand at `S`, its 1x read from it
# Every frame of a walk faces east: `sim::pet_placement` flips a walk heading west; a
# sit or a sleep faces west, never flipped. A master is the art itself, key by key; the
# 1x frame is that master read block by block (`creature_cell`), with `CREATURE_FIXES`
# setting the cells the reading gets wrong, so the classic and the cutaway draw one
# animal. The campaign's creatures ride the office's pet and mascot slots, which keep
# their names: the owlbear is the dog's, the wolf the cat's, the raven the gateway
# mascot's (the lobster's), drawn facing us because a mascot is never flipped.
# The owlbear: a bear's body and paws under an owl's head, face disc, ear tufts and
# feathered chest.
OB_FUR, OB_FUR_LT, OB_FUR_SH, OB_FUR_DK = "ƀ", "Ɓ", "Ƃ", "Ɗ"
OB_FEATHER, OB_FEATHER_LT, OB_FEATHER_SH = "ƃ", "Ƅ", "ƅ"
OB_DISC, OB_DISC_SH, OB_BEAK, OB_BEAK_SH = "Ɔ", "Ƈ", "ƈ", "Ɖ"
# The grey wolf: a dark saddle, a pale throat and belly, amber eyes.
WOLF, WOLF_LT, WOLF_SH, WOLF_DK, WOLF_PALE, WOLF_EYE = "Ƌ", "ƌ", "ƍ", "Ǝ", "Ə", "Ɛ"
# The raven: black with a blue sheen, its beak and feet a lighter slate.
RAVEN, RAVEN_SH, RAVEN_SHEEN, RAVEN_BEAK = "Ƒ", "ƕ", "Ɠ", "Ɩ"
OWLBEAR_WALK = [
    """
    .................κƅκ.κƄκ........
    ..................κƅκκƄƃκ.......
    ..................κƅƅκƄƃκκ......
    ..................κƅƅƅƅƅƅƅκ.....
    .................κκƅƅƅƃƃƅƇƇκ....
    .......κκκκκ..κκκƁƅƅƃƃƃƇƇƆƆƇκ...
    ..κκ.κκƁƁƁƁƁκκƁƁƁƀƅƅƃƃƃƇƆƆƆƆƇκ..
    .κƄƃκƁƁƀƀƀƀƀƁƁƀƀƀƀƅƃƃƃƇƇƆ&eƆƇκ..
    .κƄƃƁƀƀƀƀƀƀƀƀƀƀƀƀƀƅƃƃƃƇƆƆeeƆƈƈκ.
    κƅƅƅƁƀƀƀƀƀƀƀƀƂƀƀƀƀƃƃƃƃƇƆƆƆƆƆƈƈƈκ
    .κƅƁƀƀƀƀƂƀƀƀƀƀƂƀƀƀƃƃƃƃƃƇƆƆƆƆƉƉƉκ
    ..κƁƀƀƀƀƀƂƀƀƀƀƀƀƂƀƅƃƃƃƃƇƇƆƆƇκκκ.
    ...κƂƀƀƀƀƀƀƂƀƀƀƀƀƀƅƃƄƄƄƄƇƇƇκ....
    ...κƂƂƀƀƀƀƁƀƀƀƀƀƀƀƃƃƃƃƃƃƄκκ.....
    ....κƂƂƁƀƀƀƂƂƂƂƂƂƁƅƃƃƃƅƃƄκ......
    .....κƂƁƀƀƀƂƂƂƂƂƂƁƀƃƃƄƄƄκ.......
    ......κƁƀƀƀƂƊκκκκκƁƀƄƄƄκ........
    .......κƁƀƀƂƊκ...κƁƀƀƂƊκ........
    .......κƁƀƀƀƂκ...κƁƀƀƂκ.........
    ........κƁƀƀƂκ...κƁƀƀƂκ.........
    ........κƁƀƂƊκ...κƁƀƀƂƊκ........
    ........κƂƂƂƂƂκ..κƂƂƂƂƂ!κ.......
    ........κƊƊƊ!Ɗ¤κ.κƊƊƊ!Ɗ¤κ.......
    .........κκκκκκ...κκκκκκ........
    """,
    """
    .................κƅκ.κƄκ........
    ..................κƅκκƄƃκ.......
    ..................κƅƅκƄƃκκ......
    ..................κƅƅƅƅƅƅƅκ.....
    .................κκƅƅƅƃƃƅƇƇκ....
    .......κκκκκ..κκκƁƅƅƃƃƃƇƇƆƆƇκ...
    ..κκ.κκƁƁƁƁƁκκƁƁƁƀƅƅƃƃƃƇƆƆƆƆƇκ..
    .κƄƃκƁƁƀƀƀƀƀƁƁƀƀƀƀƅƃƃƃƇƇƆ&eƆƇκ..
    .κƄƃƁƀƀƀƀƀƀƀƀƀƀƀƀƀƅƃƃƃƇƆƆeeƆƈƈκ.
    κƅƅƅƁƀƀƀƀƀƀƀƀƂƀƀƀƀƃƃƃƃƇƆƆƆƆƆƈƈƈκ
    .κƅƁƀƀƀƀƂƀƀƀƀƀƂƀƀƀƃƃƃƃƃƇƆƆƆƆƉƉƉκ
    ..κƁƀƀƀƀƀƂƀƀƀƀƀƀƂƀƅƃƃƃƃƇƇƆƆƇκκκ.
    ...κƂƀƀƀƀƀƀƂƀƀƀƀƀƀƅƃƄƄƄƄƇƇƇκ....
    ...κƂƂƀƀƀƀƁƀƀƀƀƀƀƀƃƃƃƃƃƃƄκκ.....
    ....κƂƂƁƀƀƂƀƂƂƂƂƂƁƅƃƃƃƅƃƄκ......
    .....κƂƁƀƀƀƂƂƂƂƂƂƁƀƃƃƄƄƄκ.......
    ......κƁƀƀƀƂƊκκκκƁƀƀƄƄƄƊκ.......
    .......κƁƀƀƂƊκ..κƁƀƀƀƂƂƊκ.......
    .......κƁƀƀƂƊκ..κƁƀƀƀƂƂƊκ.......
    .......κƁƀƀƂκ...κƁƀƀƀƂƊƊƊκ......
    .......κƁƀƀƂκ...κƁƀƀƀƂƊ!Ɗ!κ.....
    .......κƂƂƂƂƂκ..κƂƂƂƂƂκκκκ......
    .......κƊƊƊ!Ɗ¤κ.κƊƊƊ!Ɗ¤κ........
    ........κκκκκκ...κκκκκκ.........
    """,
    """
    ..................κƅκκƄƃκ.......
    ..................κƅƅκƄƃκκ......
    ..................κƅƅƅƅƅƅƅκ.....
    .................κκƅƅƅƃƃƅƇƇκ....
    .......κκκκκ..κκκƁƅƅƃƃƃƇƇƆƆƇκ...
    ..κκ.κκƁƁƁƁƁκκƁƁƁƀƅƅƃƃƃƇƆƆƆƆƇκ..
    .κƄƃκƁƁƀƀƀƀƀƁƁƀƀƀƀƅƃƃƃƇƇƆ&eƆƇκ..
    .κƄƃƁƀƀƀƀƀƀƀƀƀƀƀƀƀƅƃƃƃƇƆƆeeƆƈƈκ.
    κƅƅƅƁƀƀƀƀƀƀƀƀƂƀƀƀƀƃƃƃƃƇƆƆƆƆƆƈƈƈκ
    .κƅƁƀƀƀƀƂƀƀƀƀƀƂƀƀƀƃƃƃƃƃƇƆƆƆƆƉƉƉκ
    ..κƁƀƀƀƀƀƂƀƀƀƀƀƀƂƀƅƃƃƃƃƇƇƆƆƇκκκ.
    ...κƂƀƀƀƀƀƀƂƀƀƀƀƀƀƅƃƄƄƄƄƇƇƇκ....
    ...κƂƂƀƀƀƀƀƀƀƀƀƀƀƀƃƃƅƃƃƃƄκκ.....
    ....κƂƂƁƀƀƂƀƂƂƂƂƂƁƃƃƃƃƃƃƄκ......
    .....κƂƁƀƀƂƂƂƂƂƂƂƁƀƃƃƄƄƄƊκ......
    ......κƁƀƀƂƂƊκκκκƁƀƀƄƄƄƂƊκ......
    ......κƁƀƀƀƂκ...κƁƀƀƂƂƂƂƊκ......
    ......κƁƀƀƀƂκ...κƁƀƀƂƂƂƂƂƊκ.....
    ......κƁƀƀƀƂκ...κƁƀƀƂƂƂƂƂƊκ.....
    ......κƁƀƀƀƂκ...κƁƀƀƂκƂƂƂƊκ.....
    ......κƊƁƀƀƂκ...κƁƀƀƂκƂƂƊκκ.....
    ......κƊƂƂƂƂƂκ..κƂƂƂƂƂƊƊƊƊƊκ....
    .......κƊƊƊ!Ɗ¤κ.κƊƊƊ!Ɗ¤ƊƊ!Ɗ!κ...
    ........κκκκκκ...κκκκκκκκκκκ....
    """,
    """
    ..................κƅκκƄƃκ.......
    ..................κƅƅκƄƃκκ......
    ..................κƅƅƅƅƅƅƅκ.....
    .................κκƅƅƅƃƃƅƇƇκ....
    .......κκκκκ..κκκƁƅƅƃƃƃƇƇƆƆƇκ...
    ..κκ.κκƁƁƁƁƁκκƁƁƁƀƅƅƃƃƃƇƆƆƆƆƇκ..
    .κƄƃκƁƁƀƀƀƀƀƁƁƀƀƀƀƅƃƃƃƇƇƆ&eƆƇκ..
    .κƄƃƁƀƀƀƀƀƀƀƀƀƀƀƀƀƅƃƃƃƇƆƆeeƆƈƈκ.
    κƅƅƅƁƀƀƀƀƀƀƀƀƂƀƀƀƀƃƃƃƃƇƆƆƆƆƆƈƈƈκ
    .κƅƁƀƀƀƀƂƀƀƀƀƀƂƀƀƀƃƃƃƃƃƇƆƆƆƆƉƉƉκ
    ..κƁƀƀƀƀƀƂƀƀƀƀƀƀƂƀƅƃƃƃƃƇƇƆƆƇκκκ.
    ...κƂƀƀƀƀƀƀƂƀƀƀƀƀƀƅƃƄƄƄƄƇƇƇκ....
    ...κƂƂƀƀƀƀƀƀƀƀƀƀƀƁƃƃƅƃƃƃƄκκ.....
    ....κƂƂƁƀƀƂƀƀƂƂƂƂƁƃƃƃƃƃƃƄκ......
    .....κƂƁƀƀƂƀƀƂƂƂƂƁƀƃƃƄƄƄƊκ......
    ......κƁƀƀƂƂƂƊκκκƁƀƀƄƄƄƂƊκ......
    ......κƁƀƀƂƂƂƊκ.κƁƀƀƂƂƂƂƊκ......
    ......κƁƀƀƂƂƂƊκκƁƀƀƀƂƂƂƂƊκ......
    ......κƁƀƀƂƂƂƊκκƁƀƀƀƂƂƂƂƊκ......
    ......κƁƀƀƂƊƊƊκκƁƀƀƂκƂƂƂƊκ......
    ......κƁƀƀƂƊ!Ɗ!κƁƀƀƂκƂƂƂƊκ......
    ......κƂƂƂƂƂκκκκƂƂƂƂƂƊƊƊƊƊκ.....
    ......κƊƊƊ!Ɗ¤κ.κƊƊƊ!Ɗ¤ƊƊ!Ɗ!κ....
    .......κκκκκκ...κκκκκκκκκκκ.....
    """,
    """
    .................κƅκ.κƄκ........
    ..................κƅκκƄƃκ.......
    ..................κƅƅκƄƃκκ......
    ..................κƅƅƅƅƅƅƅκ.....
    .................κκƅƅƅƃƃƅƇƇκ....
    .......κκκκκ..κκκƁƅƅƃƃƃƇƇƆƆƇκ...
    ..κκ.κκƁƁƁƁƁκκƁƁƁƀƅƅƃƃƃƇƆƆƆƆƇκ..
    .κƄƃκƁƁƀƀƀƀƀƁƁƀƀƀƀƅƃƃƃƇƇƆ&eƆƇκ..
    .κƄƃƁƀƀƀƀƀƀƀƀƀƀƀƀƀƅƃƃƃƇƆƆeeƆƈƈκ.
    κƅƅƅƁƀƀƀƀƀƀƀƀƂƀƀƀƀƃƃƃƃƇƆƆƆƆƆƈƈƈκ
    .κƅƁƀƀƀƀƂƀƀƀƀƀƂƀƀƀƃƃƃƃƃƇƆƆƆƆƉƉƉκ
    ..κƁƀƀƀƀƀƂƀƀƀƀƀƀƂƀƅƃƃƃƃƇƇƆƆƇκκκ.
    ...κƂƀƀƀƀƀƀƂƀƀƀƀƀƀƅƃƄƄƄƄƇƇƇκ....
    ...κƂƂƀƀƀƀƀƀƀƀƀƀƀƁƃƃƃƃƃƃƄκκ.....
    ....κƂƂƁƀƀƂƀƀƀƂƂƂƁƅƃƃƃƅƃƄκ......
    .....κƂƁƀƀƂƀƀƀƂƂƂƁƀƃƃƄƄƄκ.......
    .....κƁƀƀƀƂƂƂƂƊκƁƀƀƀƄƄƄƂƊκ......
    .....κƁƀƀƀƂƂƂƂƊκƁƀƀƂƂƂƂƂƊκ......
    .....κƁƀƀƀƂƂƂƂƊƁƀƀƀƂƂƂƂƂƊκ......
    .....κƁƀƀƀƂƂƂƂƂƊƁƀƀƂƂƂƂƂƊκ......
    .....κƁƀƀƂκƂƂƂƊƂƂƂƂƂκƂƂƂƊκ......
    .....κƂƂƂƂƂκƊƊƊƊƊƊ!Ɗ¤ƊƊƊƊƊκ.....
    .....κƊƊƊ!Ɗ¤ƊƊƊ!Ɗ!κκκƊƊƊ!Ɗ!κ....
    ......κκκκκκκκκκκκ...κκκκκκ.....
    """,
    """
    .................κƅκ.κƄκ........
    ..................κƅκκƄƃκ.......
    ..................κƅƅκƄƃκκ......
    ..................κƅƅƅƅƅƅƅκ.....
    .................κκƅƅƅƃƃƅƇƇκ....
    .......κκκκκ..κκκƁƅƅƃƃƃƇƇƆƆƇκ...
    ..κκ.κκƁƁƁƁƁκκƁƁƁƀƅƅƃƃƃƇƆƆƆƆƇκ..
    .κƄƃκƁƁƀƀƀƀƀƁƁƀƀƀƀƅƃƃƃƇƇƆ&eƆƇκ..
    .κƄƃƁƀƀƀƀƀƀƀƀƀƀƀƀƀƅƃƃƃƇƆƆeeƆƈƈκ.
    κƅƅƅƁƀƀƀƀƀƀƀƀƂƀƀƀƀƃƃƃƃƇƆƆƆƆƆƈƈƈκ
    .κƅƁƀƀƀƀƂƀƀƀƀƀƂƀƀƀƃƃƃƃƃƇƆƆƆƆƉƉƉκ
    ..κƁƀƀƀƀƀƂƀƀƀƀƀƀƂƀƅƃƃƃƃƇƇƆƆƇκκκ.
    ...κƂƀƀƀƀƀƀƂƀƀƀƀƀƀƅƃƄƄƄƄƇƇƇκ....
    ...κƂƂƀƁƀƀƀƀƀƀƀƀƀƀƃƃƃƃƃƃƄκκ.....
    ....κƂƂƁƀƀƂƀƀƂƂƂƂƁƅƃƃƃƅƃƄκ......
    .....κƁƀƀƀƂƀƀƂƂƂƂƁƀƃƃƄƄƄκ.......
    .....κƁƀƀƀƂƂƂƊκκκƁƀƀƄƄƄƊκ.......
    .....κƁƀƀƂƂƂƂƂƊκκƁƀƀƀƂƂƊκ.......
    .....κƁƀƀƂƂƂƂƂƊκκƁƀƀƀƂƂƊκ.......
    .....κƁƀƀƂκƂƂƂƊκκƂƂƂƂƂƂƊκ.......
    .....κƁƀƀƂκƂƂƂƊκκƊƊƊ!Ɗ¤Ɗκ.......
    ....κƂƂƂƂƂκƊƊƊƊƊκκκκƊƊƊƊƊκ......
    ....κƊƊƊ!Ɗ¤ƊƊƊ!Ɗ!κ.κƊƊƊ!Ɗ!κ.....
    .....κκκκκκκκκκκκ...κκκκκκ......
    """,
    """
    ..................κƅκκƄƃκ.......
    ..................κƅƅκƄƃκκ......
    ..................κƅƅƅƅƅƅƅκ.....
    .................κκƅƅƅƃƃƅƇƇκ....
    .......κκκκκ..κκκƁƅƅƃƃƃƇƇƆƆƇκ...
    ..κκ.κκƁƁƁƁƁκκƁƁƁƀƅƅƃƃƃƇƆƆƆƆƇκ..
    .κƄƃκƁƁƀƀƀƀƀƁƁƀƀƀƀƅƃƃƃƇƇƆ&eƆƇκ..
    .κƄƃƁƀƀƀƀƀƀƀƀƀƀƀƀƀƅƃƃƃƇƆƆeeƆƈƈκ.
    κƅƅƅƁƀƀƀƀƀƀƀƀƂƀƀƀƀƃƃƃƃƇƆƆƆƆƆƈƈƈκ
    .κƅƁƀƀƀƀƂƀƀƀƀƀƂƀƀƀƃƃƃƃƃƇƆƆƆƆƉƉƉκ
    ..κƁƀƀƀƀƀƂƀƀƀƀƀƀƂƀƅƃƃƃƃƇƇƆƆƇκκκ.
    ...κƂƀƀƀƀƀƀƂƀƀƀƀƀƀƅƃƄƄƄƄƇƇƇκ....
    ...κƂƂƀƁƀƀƀƀƀƀƀƀƀƀƃƃƅƃƃƃƄκκ.....
    ....κƂƁƀƀƀƂƀƀƂƂƂƂƁƃƃƃƃƃƃƄκ......
    .....κƁƀƀƀƂƀƀƂƂƂƂƂƁƃƃƄƄƄκ.......
    .....κƁƀƀƀƂƂƂƊκκκκƁƀƄƄƄƊκ.......
    .....κƁƀƀƂƂƂƂƊκ..κƁƀƀƀƂƊκ.......
    ....κƁƀƀƀƂƂƂƂƊκ...κƁƀƀƂƊκ.......
    ....κƁƀƀƂκƂƂƂƊκ...κƁƀƀƂƊκ.......
    .....κƁƀƂκƂƂƂƊκ...κƁƀƀƀƂκ.......
    ....κƂƂƂƂƂƂƂƂƊκ...κƁƀƀƂκκ.......
    ....κƊƊƊ!Ɗ¤ƊƊƊƊκ..κƊƂƂƂƂƂκ......
    .....κκκκκƊƊƊ!Ɗ!κ.κƊƊƊƊ!Ɗ¤κ.....
    ..........κκκκκκ...κκκκκκκ......
    """,
    """
    ..................κƅκκƄƃκ.......
    ..................κƅƅκƄƃκκ......
    ..................κƅƅƅƅƅƅƅκ.....
    .................κκƅƅƅƃƃƅƇƇκ....
    .......κκκκκ..κκκƁƅƅƃƃƃƇƇƆƆƇκ...
    ..κκ.κκƁƁƁƁƁκκƁƁƁƀƅƅƃƃƃƇƆƆƆƆƇκ..
    .κƄƃκƁƁƀƀƀƀƀƁƁƀƀƀƀƅƃƃƃƇƇƆ&eƆƇκ..
    .κƄƃƁƀƀƀƀƀƀƀƀƀƀƀƀƀƅƃƃƃƇƆƆeeƆƈƈκ.
    κƅƅƅƁƀƀƀƀƀƀƀƀƂƀƀƀƀƃƃƃƃƇƆƆƆƆƆƈƈƈκ
    .κƅƁƀƀƀƀƂƀƀƀƀƀƂƀƀƀƃƃƃƃƃƇƆƆƆƆƉƉƉκ
    ..κƁƀƀƀƀƀƂƀƀƀƀƀƀƂƀƅƃƃƃƃƇƇƆƆƇκκκ.
    ...κƂƀƀƀƀƀƀƂƀƀƀƀƀƀƅƃƄƄƄƄƇƇƇκ....
    ...κƂƂƀƀƀƀƀƀƀƀƀƀƀƀƃƃƅƃƃƃƄκκ.....
    ....κƂƂƁƀƀƂƀƀƂƂƂƂƁƃƃƃƃƃƃƄκ......
    .....κƂƁƀƀƂƀƀƂƂƂƂƁƀƃƃƄƄƄκ.......
    ......κƁƀƀƂƂƂƊκκκκƁƀƄƄƄƊκ.......
    ......κƁƀƀƂƂƂƊκ..κƁƀƀƂƊκ........
    ......κƁƀƀƂƂƂƊκ..κƁƀƀƀƂκ........
    ......κƁƀƀƂƂƂƊκ..κƁƀƀƀƂκ........
    ......κƂƂƂƂƂƂƊκ...κƁƀƀƂκ........
    ......κƊƊƊ!Ɗ¤Ɗκ...κƁƀƀƂκ........
    .......κκƊƊƊƊƊκ..κƊƂƂƂƂƂκ.......
    ........κƊƊƊ!Ɗ!κ.κƊƊƊƊ!Ɗ¤κ......
    .........κκκκκκ...κκκκκκκ.......
    """,
]
OWLBEAR_SIT = [
    """
    .....κƄκ........κƅκ.....
    .....κƄκ.κκκκκκ.κƅκ.....
    .....κƄƃκƅƅƅƅƅƅκƅƅκ.....
    .....κƄƃƅƅƅƅƅƅƅƃƅƅκ.....
    ......κƅƅƃƃƃƃƃƃƃƃκ......
    .....κƅƅƇƇƇƃƃƇƇƇƃƃκ.....
    .....κƅƇƆƆƆƇƇƆƆƆƇƃκ.....
    .....κƅƆƆ&eƆƆ&eƆƆƄκ.....
    .....κƃƆƆeeƆƆeeƆƆƄκ.....
    .....κƃƇƆƆƆƈƈƆƆƆƇƄκ.....
    ......κƇƇƆƆƈƉƆƆƇƇκ......
    ......κƃƃƃƃƉƃƄƄƄƄκ......
    .....κƁƁƂƄƄƄƄƄƄƂƁƁκ.....
    ....κƀƀƀƂƅƅƃƃƃƃƀƀƀƂκ....
    ....κƀƀƀƂƅƃƃƃƅƃƀƀƀƂκ....
    ...κƁƀƀƀƂƃƃƃƃƃƃƀƀƂƀƁκ...
    ...κƁƀƀƀƂƃƃƅƃƃƃƀƀƂƀƂκ...
    ..κƁƀƀƀƀƀƂƃƃƃƃƀƀƀƂƀƀƁκ..
    .κ¤Ɗ!ƀƀƀƀƂƃƃƃƅƀƀƀƂƀ¤Ɗ!κ.
    .κƊƂƊƊƀƀƀƂƃƃƃƄƀƀƂƀƊƊƂƊκ.
    κƊƊƂƂƊƂƂƂƂƄƄƄƄƂƂƂƂƊƂƂƊƊκ
    .κƊƂƂƊƂƂƂƂƂƂƂƂƂƂƂƂƊƂƂƊκ.
    ..κƊƊκ¤Ɗ¤ƊƂƂƂƂ¤Ɗ¤ƊκƊƊκ..
    ...κκ.κκκκκκκκκκκκ.κκ...
    """,
    """
    .....κƄκ.κκκκκκ.κƅκ.....
    .....κƄƃκƅƅƅƅƅƅκƅƅκ.....
    .....κƄƃƅƅƅƅƅƅƅƃƅƅκ.....
    ......κƅƅƃƃƃƃƃƃƃƃκ......
    .....κƅƅƇƇƇƃƃƇƇƇƃƃκ.....
    .....κƅƇƆƆƆƇƇƆƆƆƇƃκ.....
    .....κƅƆƆ&eƆƆ&eƆƆƄκ.....
    .....κƃƆƆeeƆƆeeƆƆƄκ.....
    .....κƃƇƆƆƆƈƈƆƆƆƇƄκ.....
    ......κƇƇƆƆƈƉƆƆƇƇκ......
    ......κƃƃƃƃƉƃƄƄƄƄκ......
    .....κƁƁƂƄƄƄƄƄƄƂƁƁκ.....
    ....κƀƀƀƂƅƅƅƃƅƃƀƀƀƂκ....
    ...κƁƀƀƀƂƅƃƃƃƃƃƀƀƀƂƁκ...
    ...κƁƀƀƀƂƅƃƃƃƅƃƀƀƂƀƂκ...
    ...κƀƀƀƀƂƃƃƃƃƃƃƀƀƂƀƂκ...
    ...κƀƀƀƀƀƂƃƅƃƃƀƀƀƂƀƂκ...
    ..κƁƀƀƀƀƀƂƃƃƃƃƀƀƀƂƀƀƁκ..
    .κ¤Ɗ!ƀƀƀƀƂƃƃƃƅƀƀƀƂƀ¤Ɗ!κ.
    .κƊƂƊƊƀƀƀƂƃƄƄƄƀƀƂƀƊƊƂƊκ.
    κƊƊƂƂƊƂƂƂƂƄƄƄƄƂƂƂƂƊƂƂƊƊκ
    .κƊƂƂƊƂƂƂƂƂƂƂƂƂƂƂƂƊƂƂƊκ.
    ..κƊƊκ¤Ɗ¤ƊƂƂƂƂ¤Ɗ¤ƊκƊƊκ..
    ...κκ.κκκκκκκκκκκκ.κκ...
    """,
    """
    .....κƄκ.κκκκκκ.κƅκ.....
    .....κƄƃκƅƅƅƅƅƅκƅƅκ.....
    .....κƄƃƅƅƅƅƅƅƅƃƅƅκ.....
    ......κƅƅƃƃƃƃƃƃƃƃκ......
    .....κƅƅƇƇƇƃƃƇƇƇƃƃκ.....
    .....κƅƇƆƆƆƇƇƆƆƆƇƃκ.....
    .....κƅƆƆ&eƆƆ&eƆƆƄκ.....
    .....κƃƆƆeeƆƆeeƆƆƄκ.....
    .....κƃƇƆƆƆƈƈƆƆƆƇƄκ.....
    ......κƇƇƆƆƈƉƆƆƇƇκ......
    ......κƃƃƃƃƉƃƄƄƄƄκ......
    .....κƁƁƂƄƄƄƄƄƄƂƁƁκ.....
    ....κƀƀƀƂƅƅƅƃƅƃƀƀƀƂκ....
    ...κƁƀƀƀƂƅƃƃƃƃƃƀƀƀƂƁκ...
    ...κƁƀƀƀƂƅƃƃƃƅƃƀƀƂƀƂκ...
    ...κƀƀƀƀƂƃƃƃƃƃƃƀƀƂƀƂκ...
    ...κƀƀƀƀƀƂƃƅƃƃƀƀƀƂƀƂκ...
    ..κƁƀƀƀƀƀƂƃƃƃƃƀƀƀƂƀƀƁκ..
    .κ¤Ɗ!ƀƀƀƀƂƃƃƃƅƀƀƀƂƀ¤Ɗ!κ.
    .κƊƂƊƊƀƀƀƂƃƄƄƄƀƀƂƀƊƊƂƊκ.
    κƊƊƂƂƊƂƂƂƂƄƄƄƄƂƂƂƂƊƂƂƊƊκ
    .κƊƂƂƊƂƂƂƂƂƂƂƂƂƂƂƂƊƂƂƊκ.
    ..κƊƊκ¤Ɗ¤ƊƂƂƂƂ¤Ɗ¤ƊκƊƊκ..
    ...κκ.κκκκκκκκκκκκ.κκ...
    """,
    """
    .....κƄκ........κƅκ.....
    .....κƄκ.κκκκκκ.κƅκ.....
    .....κƄƃκƅƅƅƅƅƅκƅƅκ.....
    .....κƄƃƅƅƅƅƅƅƅƃƅƅκ.....
    ......κƅƅƃƃƃƃƃƃƃƃκ......
    .....κƅƅƇƇƇƃƃƇƇƇƃƃκ.....
    .....κƅƇƆƆƆƇƇƆƆƆƇƃκ.....
    .....κƅƆƆƆƆƆƆƆƆƆƆƄκ.....
    .....κƃƆƆeeƆƆeeƆƆƄκ.....
    .....κƃƇƆƆƆƈƈƆƆƆƇƄκ.....
    ......κƇƇƆƆƈƉƆƆƇƇκ......
    ......κƃƃƃƃƉƃƄƄƄƄκ......
    .....κƁƁƂƄƄƄƄƄƄƂƁƁκ.....
    ....κƀƀƀƂƅƅƃƃƃƃƀƀƀƂκ....
    ....κƀƀƀƂƅƃƃƃƅƃƀƀƀƂκ....
    ...κƁƀƀƀƂƃƃƃƃƃƃƀƀƂƀƁκ...
    ...κƁƀƀƀƂƃƃƅƃƃƃƀƀƂƀƂκ...
    ..κƁƀƀƀƀƀƂƃƃƃƃƀƀƀƂƀƀƁκ..
    .κ¤Ɗ!ƀƀƀƀƂƃƃƃƅƀƀƀƂƀ¤Ɗ!κ.
    .κƊƂƊƊƀƀƀƂƃƃƃƄƀƀƂƀƊƊƂƊκ.
    κƊƊƂƂƊƂƂƂƂƄƄƄƄƂƂƂƂƊƂƂƊƊκ
    .κƊƂƂƊƂƂƂƂƂƂƂƂƂƂƂƂƊƂƂƊκ.
    ..κƊƊκ¤Ɗ¤ƊƂƂƂƂ¤Ɗ¤ƊκƊƊκ..
    ...κκ.κκκκκκκκκκκκ.κκ...
    """,
]
OWLBEAR_SLEEP = [
    """
    ........................
    ........................
    ........κ...............
    ......κκƄκκ.............
    ....κκƄƃƃκƅκ............
    ...κƅƅƅƅƅƅƅκκκκκκκκ...κκ
    ..κƅƇƃƃƅƃƁƁƁƁƁƁƁƁƁƁκκκƄƃ
    .κƇƆƆƇƇƃƃƃƀƀƀƀƀƀƀƀƀƁƁƃƃκ
    κƅƆƆƆƆƇƃƃƃƃƀƂƀƀƀƀƀƀƀƀƁκ.
    κƇƆeeƆƇƃƃƃƄƀƀƀƀƀƂƀƀƀƀƂκ.
    κƈƆƆƆƆƇƃƃƄƄƀƀƀƀƀƀƀƂƀƀƂκ.
    κƉƈƆƆƆƇƃƄƄƀƀƀƀƂƀƀƀƀƀƂƂκ.
    .κκƇƇƇƄƄƄƂƀƀƀƀƂƂƂƂƂƂƂκ..
    κƂƂƂƂƄƄƂƂƂƂƂƂƂƂƂƂƂƂƂκ...
    κ¤Ɗ¤Ɗ!ƊƊƊƊƂƂƂƂƂƂƂƂƂκ....
    .κκκκκκκκκκκκκκκκκκ.....
    """,
    """
    ........................
    ........................
    ........κ...............
    ......κκƄκκ.............
    ....κκƄƃƃκƅκκκκκκκ....κκ
    ...κƅƅƅƅƅƅƅƁƁƁƁƁƁƁκκκκƄƃ
    ..κƅƇƃƃƅƃƀƀƀƀƀƀƀƀƀƁƁƄƃƃκ
    .κƇƆƆƇƇƃƃƃƀƀƀƀƀƀƀƀƀƀƁƃκ.
    κƅƆƆƆƆƇƃƃƃƃƀƂƀƀƀƀƀƀƀƀƁκ.
    κƇƆeeƆƇƃƃƃƄƀƀƀƀƀƂƀƀƀƀƂκ.
    κƈƆƆƆƆƇƃƃƄƄƀƀƀƀƀƀƀƂƀƀƂκ.
    κƉƈƆƆƆƇƃƄƄƀƀƀƀƂƀƀƀƀƂƂƂκ.
    .κκƇƇƇƄƄƄƂƀƀƀƀƂƂƂƂƂƂƂκ..
    κƂƂƂƂƄƄƂƂƂƂƂƂƂƂƂƂƂƂƂκ...
    κ¤Ɗ¤Ɗ!ƊƊƊƊƂƂƂƂƂƂƂƂƂκ....
    .κκκκκκκκκκκκκκκκκκ.....
    """,
    """
    ........................
    ........................
    ........κ...............
    ......κκƄκκ.............
    ....κκƄƃƃκƅκκκκκκκ....κκ
    ...κƅƅƅƅƅƅƅƁƁƁƁƁƁƁκκκκƄƃ
    ..κƅƇƃƃƅƃƀƀƀƀƀƀƀƀƀƁƁƄƃƃκ
    .κƇƆƆƇƇƃƃƃƀƀƀƀƀƀƀƀƀƀƁƃκ.
    κƅƆƆƆƆƇƃƃƃƃƀƂƀƀƀƀƀƀƀƀƁκ.
    κƇƆeeƆƇƃƃƃƄƀƀƀƀƀƂƀƀƀƀƂκ.
    κƈƆƆƆƆƇƃƃƄƄƀƀƀƀƀƀƀƂƀƀƂκ.
    κƉƈƆƆƆƇƃƄƄƀƀƀƀƂƀƀƀƀƂƂƂκ.
    .κκƇƇƇƄƄƄƂƀƀƀƀƂƂƂƂƂƂƂκ..
    κƂƂƂƂƄƄƂƂƂƂƂƂƂƂƂƂƂƂƂκ...
    κ¤Ɗ¤Ɗ!ƊƊƊƊƂƂƂƂƂƂƂƂƂκ....
    .κκκκκκκκκκκκκκκκκκ.....
    """,
    """
    ........................
    ........................
    ........κ...............
    ......κκƄκκ.............
    ....κκƄƃƃκƅκ............
    ...κƅƅƅƅƅƅƅκκκκκκκκ...κκ
    ..κƅƇƃƃƅƃƁƁƁƁƁƁƁƁƁƁκκκƄƃ
    .κƇƆƆƇƇƃƃƃƀƀƀƀƀƀƀƀƀƁƁƃƃκ
    κƅƆƆƆƆƇƃƃƃƃƀƂƀƀƀƀƀƀƀƀƁκ.
    κƇƆeeƆƇƃƃƃƄƀƀƀƀƀƂƀƀƀƀƂκ.
    κƈƆƆƆƆƇƃƃƄƄƀƀƀƀƀƀƀƂƀƀƂκ.
    κƉƈƆƆƆƇƃƄƄƀƀƀƀƂƀƀƀƀƀƂƂκ.
    .κκƇƇƇƄƄƄƂƀƀƀƀƂƂƂƂƂƂƂκ..
    κƂƂƂƂƄƄƂƂƂƂƂƂƂƂƂƂƂƂƂκ...
    κ¤Ɗ¤Ɗ!ƊƊƊƊƂƂƂƂƂƂƂƂƂκ....
    .κκκκκκκκκκκκκκκκκκ.....
    """,
]
WOLF_WALK = [
    """
    .....................κƍκƍκ......
    .....................κƍκƋƍκ.....
    .....................κƍƍƋƍκ.....
    .....................κƋƋƋƋƋκ....
    ....................κƋƋƋƎƎƋκ....
    ....................κƋƋƋƋƐƋƋκκκ.
    ........κκ........κκƍƋƋƋƋƋƋƋƋƋeκ
    .....κκκƍƍκκκκκκκκƍƍƍƋƋƋƋƋƋƋƋƋƎκ
    ....κƍƍƍƍƍƍƍƍƍƍƍƍƍƍƍƋƋƏƏƍκκκκκκ.
    ...κƍƍƍƍƋƋƍƍƍƍƍƍƍƍƋƋƋƏƏƏκ.......
    ..κƍƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƏƏƏκ.......
    κƎƎƋƍκƋƋƍƋƋƏƏƏƏƏƏƋƋƋƋƍƋƋκ.......
    κƎƎƍκ.κƋƍƎκκκκκκκƏƋƋƍƋƋƎκ.......
    κƎƍκ..κƋƍƎκ......κƋƋƍƍƍƎκ.......
    .κκ...κƋƍƎκ......κƋƋƍκƍƍƎκ......
    .....κƍƋƍκ.......κƋƋƍκƍƍƎκ......
    .....κƍƋƋƍκ......κƋƍƍκκƍƎκ......
    .....κƍƋƋƍκ......κƋƍκ.κƍƎκ......
    ......κƍƋƋƍκ....κƋƋƍκ.κƍƍƎκ.....
    ......κƍƎƋƍκκκ..κƋƍκκ..κƍƎκκ....
    ......κƎƎƎƍƍƍƎκ.κƍƍƍƎκ.κƎƎƎƎκ...
    .......κκκκκκκ...κκκκ...κκκκ....
    """,
    """
    .....................κƍκƍκ......
    .....................κƍκƋƍκ.....
    .....................κƍƍƋƍκ.....
    .....................κƋƋƋƋƋκ....
    ....................κƋƋƋƎƎƋκ....
    ....................κƋƋƋƋƐƋƋκκκ.
    ........κκ........κκƍƋƋƋƋƋƋƋƋƋeκ
    .....κκκƍƍκκκκκκκκƍƍƍƋƋƋƋƋƋƋƋƋƎκ
    ....κƍƍƍƍƍƍƍƍƍƍƍƍƍƍƍƋƋƏƏƍκκκκκκ.
    ...κƍƍƍƍƋƋƍƍƍƍƍƍƍƍƋƋƋƏƏƏκ.......
    ..κƍƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    ..κƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƍƋƋƏƏƏκ.......
    κƍƍƋƍκƋƋƍƋƋƏƏƏƏƏƏƋƋƋƋƍƋƋκ.......
    κƎƎƍκκƋƋƍƎκκκκκκκƏƋƋƍƋƋƎκ.......
    κƎƎƍκκƋƋƍƎκ......κƋƋƍƍƍƎκ.......
    κƎκκ.κƋƋƍκ.......κƋƋƍƍƍƎκ.......
    .κ...κƋƋƍκ.......κƍƍκκƍƎκ.......
    .....κƋƋƍκ......κƋƋƍκκƍƎκ.......
    .....κƍƋƋƍκ.....κƋƍκ.κƍƍƎκ......
    .....κƍƋƋƍκ.....κƋƍκ.κƍƍƎκ......
    .....κƎƎƋƍκκκ..κƍƍƍƎκ.κƍƎκκ.....
    ......κκκƍƍƍƎκ..κκκκ..κƎƎƎƎκ....
    .........κκκκ..........κκκκ.....
    """,
    """
    .....................κƍκƋƍκ.....
    .....................κƍƍƋƍκ.....
    .....................κƋƋƋƋƋκ....
    ....................κƋƋƋƎƎƋκ....
    ....................κƋƋƋƋƐƋƋκκκ.
    ........κκ........κκƍƋƋƋƋƋƋƋƋƋeκ
    .....κκκƍƍκκκκκκκκƍƍƍƋƋƋƋƋƋƋƋƋƎκ
    ....κƍƍƍƍƍƍƍƍƍƍƍƍƍƍƍƋƋƏƏƍκκκκκκ.
    ...κƍƍƍƍƋƋƍƍƍƍƍƍƍƍƋƋƋƏƏƏκ.......
    ..κƍƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƍƋƋƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƏƏƏκ.......
    κƎƎƋƍκƋƋƍƋƋƏƏƏƏƏƏƋƋƋƋƍƋƋκ.......
    κƎƎƍκκƋƋƍƍƎκκκκκκƏƋƋƍƋƋƎκ.......
    κƎƍκ.κƋƋƍƎκ......κκƋƍƍƍƎκ.......
    .κκ..κƋƋƍƎκ.......κƋƍƍƍƎκ.......
    .....κƋƍƎκ........κƋƍƍƍƎκ.......
    .....κƋƍƍƎκ.......κƋƍƍƍƎκ.......
    .....κƋƍƍƎκ......κƋƋƍƍƍƎκ.......
    .....κƋƋƍƎκκ.....κƋƍκƍƍƎκ.......
    ......κƋƍƎƎƎκ....κƍƍƍƎƍƎκ.......
    ......κƋƍκκκ......κκκƍƍƎκ.......
    ......κƍƍƍƎκ........κƎƎƎƎκ......
    .......κκκκ..........κκκκ.......
    """,
    """
    .....................κƍκƍκ......
    .....................κƍκƋƍκ.....
    .....................κƍƍƋƍκ.....
    .....................κƋƋƋƋƋκ....
    ....................κƋƋƋƎƎƋκ....
    ....................κƋƋƋƋƐƋƋκκκ.
    ........κκ........κκƍƋƋƋƋƋƋƋƋƋeκ
    .....κκκƍƍκκκκκκκκƍƍƍƋƋƋƋƋƋƋƋƋƎκ
    ....κƍƍƍƍƍƍƍƍƍƍƍƍƍƍƍƋƋƏƏƍκκκκκκ.
    ...κƍƍƍƍƋƋƍƍƍƍƍƍƍƍƋƋƋƏƏƏκ.......
    ..κƍƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƍƋƋƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƏƏƏκ.......
    κƎƎƋƍκƋƋƍƋƋƏƏƏƏƏƏƋƋƋƋƍƋƏκ.......
    κƎƎƍκκƋƋƍƍƎκκκκκκƏƏƋƋƍƋκ........
    κƎƍκ.κƋƍƍƍƎκ.....κκƋƋƍƎκ........
    .κκ.κƋƋƍƍƎκ.......κƋƋƍƎκ........
    ....κƋƋƍƍƍƎκ.......κƋƍƎκ........
    ....κƋƍκκƍƍƎκ......κƋƍƎκ........
    ....κƋƋƍκκƍƎκκ.....κƋƍƎκ........
    .....κƋƍκκƎƎƎƎκ....κƍƍƍƎκ.......
    .....κƋƍκκκκκκ.....κƍƎκκ........
    .....κƍƍƍƎκ........κƎƎƎƎκ.......
    ......κκκκ..........κκκκ........
    """,
    """
    .....................κƍκƍκ......
    .....................κƍκƋƍκ.....
    .....................κƍƍƋƍκ.....
    .....................κƋƋƋƋƋκ....
    ....................κƋƋƋƎƎƋκ....
    ....................κƋƋƋƋƐƋƋκκκ.
    ........κκ........κκƍƋƋƋƋƋƋƋƋƋeκ
    .....κκκƍƍκκκκκκκκƍƍƍƋƋƋƋƋƋƋƋƋƎκ
    ....κƍƍƍƍƍƍƍƍƍƍƍƍƍƍƍƋƋƏƏƍκκκκκκ.
    ...κƍƍƍƍƋƋƍƍƍƍƍƍƍƍƋƋƋƏƏƏκ.......
    ..κƍƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƍƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƏƏƏκ.......
    κƎƎƋƍκƋƋƍƋƋƏƏƏƏƏƏƋƋƋƋƍƋƏκ.......
    κƎƎƍκƋƋƋƍƍƎκκκκκκƏƏƋƋƍƋκ........
    κƎƍκκƋƋƍκƍƎκ.....κκƋƋƍƎκ........
    .κκ.κƋƋƍκƍƎκ.......κƋƋƍκ........
    ...κƋƋƍκκƍƎκ.......κƋƋƍκ........
    ...κƋƋƍκκƍƍƎκ......κƍƋƍκ........
    ...κƋƋƍκκƍƍƍƎκ.....κƍƋƍκ........
    ....κƋƍκ.κκƍƎκ....κƍƍƋƋƍκ.......
    ....κƋƍκκ..κƎκκκ..κƍƎκƋƍκκ......
    ....κƍƍƍƎκ.κƎƎƎƎκ.κƎƎƎƍƍƍƎκ.....
    .....κκκκ...κκκκ...κκκκκκκ......
    """,
    """
    .....................κƍκƍκ......
    .....................κƍκƋƍκ.....
    .....................κƍƍƋƍκ.....
    .....................κƋƋƋƋƋκ....
    ....................κƋƋƋƎƎƋκ....
    ....................κƋƋƋƋƐƋƋκκκ.
    ........κκ........κκƍƋƋƋƋƋƋƋƋƋeκ
    .....κκκƍƍκκκκκκκκƍƍƍƋƋƋƋƋƋƋƋƋƎκ
    ....κƍƍƍƍƍƍƍƍƍƍƍƍƍƍƍƋƋƏƏƍκκκκκκ.
    ...κƍƍƍƍƋƋƍƍƍƍƍƍƍƍƋƋƋƏƏƏκ.......
    ..κƍƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    ..κƍƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƏƏƏκ.......
    κƍƍƋƍκƋƋƍƋƋƏƏƏƏƏƏƋƋƋƋƍƋƏκ.......
    κƎƎƍκƋƋƍƍƍƎκκκκκκƏƏƋƋƍƋκ........
    κƎƎƍκƋƋƍƍƍƎκ.....κκƋƋƍƎκ........
    κƎκκƋƋƍκƍƍƎκ......κƋƋƍƎκ........
    .κ.κƋƋƍκƍƍƎκ.......κƋƍκ.........
    ...κƋƍκκƍƍƎκ......κƍƋƍκ.........
    ...κƋƍκ.κƍƍƎκ.....κƍƋƋƍκ........
    ...κƋƍκκ.κƍƎκ.....κƍƋƋƍκ........
    ...κƍƍƍƎκκƍƎκκκ..κƎƎƎƋƍκκ.......
    ....κκκκ..κƎƎƎƎκ..κκκƍƍƍƎκ......
    ...........κκκκ......κκκκ.......
    """,
    """
    .....................κƍκƋƍκ.....
    .....................κƍƍƋƍκ.....
    .....................κƋƋƋƋƋκ....
    ....................κƋƋƋƎƎƋκ....
    ....................κƋƋƋƋƐƋƋκκκ.
    ........κκ........κκƍƋƋƋƋƋƋƋƋƋeκ
    .....κκκƍƍκκκκκκκκƍƍƍƋƋƋƋƋƋƋƋƋƎκ
    ....κƍƍƍƍƍƍƍƍƍƍƍƍƍƍƍƋƋƏƏƍκκκκκκ.
    ...κƍƍƍƍƋƋƍƍƍƍƍƍƍƍƋƋƋƏƏƏκ.......
    ..κƍƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƍƋƋƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƏƏƏκ.......
    κƎƎƋƍκƋƋƍƋƋƏƏƏƏƏƏƋƋƋƋƍƋƏκ.......
    κƎƎƍκκƋƋƍƍƎκκκκκκƏƏƋƋƍƋκ........
    κƎƍκκƋƋƍƍƍƎκ.....κκƋƋƍƎκ........
    .κκ.κƋƋƍƍƎκ.......κƋƋƍƎκ........
    ....κƋƍƍƍƎκ.......κƋƋƍƎκ........
    ....κƋƋƍƍƎκ.......κƋƋƍƎκ........
    .....κƋƍƍƎκ.......κƋƋƍƎκ........
    .....κƋƍƍƍƎκ......κƋƋƍκκ........
    .....κƍƍƍƎƎκ......κƋƋƍƎƎκ.......
    ......κκκƍƎκκ.....κƋƋƍκκ........
    ........κƎƎƎƎκ....κƍƍƍƎκ........
    .........κκκκ......κκκκ.........
    """,
    """
    .....................κƍκƍκ......
    .....................κƍκƋƍκ.....
    .....................κƍƍƋƍκ.....
    .....................κƋƋƋƋƋκ....
    ....................κƋƋƋƎƎƋκ....
    ....................κƋƋƋƋƐƋƋκκκ.
    ........κκ........κκƍƋƋƋƋƋƋƋƋƋeκ
    .....κκκƍƍκκκκκκκκƍƍƍƋƋƋƋƋƋƋƋƋƎκ
    ....κƍƍƍƍƍƍƍƍƍƍƍƍƍƍƍƋƋƏƏƍκκκκκκ.
    ...κƍƍƍƍƋƋƍƍƍƍƍƍƍƍƋƋƋƏƏƏκ.......
    ..κƍƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƍƋƋƍƋƋƋƋƋƋƋƋƋƋƋƋƋƋƏƏƏƍκ......
    .κƍƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƏƏƏκ.......
    κƎƎƋƍκƋƋƍƋƋƏƏƏƏƏƏƋƋƋƋƍƋƋκ.......
    κƎƎƍκκƋƋƍƍƎκκκκκκƏƋƋƍƋƋƎκ.......
    κƎƍκ.κƋƋƍƎκ......κκƋƍƍƍƎκ.......
    .κκ..κƋƍƍƎκ.......κƋƍƍƍƎκ.......
    .....κƋƋƍƎκ.......κƋƍκƍƎκ.......
    .....κƋƋƋƍκ.......κƋƍκƍƎκ.......
    ......κƍƋƍκκ......κƋƍκƍƎκκ......
    .......κƍƍƍƎκ....κƋƋƍκƎƎƎƎκ.....
    .......κƍƎκκ.....κƋƍκκκκκκ......
    .......κƎƎƎƎκ....κƍƍƍƎκ.........
    ........κκκκ......κκκκ..........
    """,
]
WOLF_SIT = [
    """
    .........κκκƍκ..........
    ........κƋƍκƍκ..........
    ........κƋƍκƍκ..........
    ........κƋƋƍƍκ..........
    .......κƋƋƋƋƋκ..........
    ......κκƋƎƎƋƋƋκ.........
    ....κκƋƋƋƐƋƋƋƋκ.........
    ...κeƋƋƋƋƋƋƋƋκ..........
    ...κƎƋƏκκƏƏƏƋƍκ.........
    ....κκκκƏƏƏƋƋƋƍκ........
    .......κƏƏƏƋƋƋƋκ........
    ........κƏƏƋƋƋƋƍκ.......
    .......κƋƋƍƋƋƋƋƋƍκ......
    .......κƋƋƍƋƋƋƋƋƋƍκκ....
    .......κƋƋƍƋƋƋƋƋƋƋƍƍκ...
    .......κƋƋƍƋƋƋƋƋƋƋƋƋƍκ..
    .......κƋƋƍƋƋƋƋƋƋƋƋƋƋκ..
    .......κƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    .......κƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    ....κκκκƋƍƋƋƋƋƋƋƋƋƍƋƋκ..
    ...κƎƎƎƎƋƍƋƋƋƋƋƋƋƋƍƋκ...
    ...κƎƎƎƎƋƍƋƋƋƋƋƋƋƋƍκκκκ.
    ....κκƎƍƍƍƎƎƎκκκκƍƍƍƍƍƎκ
    ......κκκκκκκ....κκκκκκ.
    """,
    """
    ........κƋƍκƍκ..........
    ........κƋƍκƍκ..........
    ........κƋƋƍƍκ..........
    .......κƋƋƋƋƋκ..........
    ......κκƋƎƎƋƋƋκ.........
    ....κκƋƋƋƐƋƋƋƋκ.........
    ...κeƋƋƋƋƋƋƋƋκ..........
    ...κƎƋƏκκƏƏƏƋƍκ.........
    ....κκκκƏƏƏƋƋƋƍκ........
    .......κƏƏƏƋƋƋƋκ........
    ........κƏƏƋƋƋƋƍκ.......
    .......κƋƋƍƋƋƋƋƋκ.......
    .......κƋƋƍƋƋƋƋƋƍκ......
    .......κƋƋƍƋƋƋƋƋƋƍκκ....
    .......κƋƋƍƋƋƋƋƋƋƋƍƍκ...
    .......κƋƋƍƋƋƋƋƋƋƋƋƋƍκ..
    .......κƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    .......κƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    .......κƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    ....κκκκƋƍƋƋƋƋƋƋƋƋƍƋƋκ..
    ...κƎƎƎƎƋƍƋƋƋƋƋƋƋƋƍƋκ...
    ...κƎƎƎƎƋƍƋƋƋƋƋƋƋƋƍκκκκ.
    ....κκƎƍƍƍƎƎƎκκκκƍƍƍƍƍƎκ
    ......κκκκκκκ....κκκκκκ.
    """,
    """
    ........κƋƍκƍκ..........
    ........κƋƍκƍκ..........
    ........κƋƋƍƍκ..........
    .......κƋƋƋƋƋκ..........
    ......κκƋƎƎƋƋƋκ.........
    ....κκƋƋƋƐƋƋƋƋκ.........
    ...κeƋƋƋƋƋƋƋƋκ..........
    ...κƎƋƏκκƏƏƏƋƍκ.........
    ....κκκκƏƏƏƋƋƋƍκ........
    .......κƏƏƏƋƋƋƋκ........
    ........κƏƏƋƋƋƋƍκ.......
    .......κƋƋƍƋƋƋƋƋκ.......
    .......κƋƋƍƋƋƋƋƋƍκ......
    .......κƋƋƍƋƋƋƋƋƋƍκκ....
    .......κƋƋƍƋƋƋƋƋƋƋƍƍκ...
    .......κƋƋƍƋƋƋƋƋƋƋƋƋƍκ..
    .......κƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    .......κƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    .......κƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    ....κκκκƋƍƋƋƋƋƋƋƋƋƍƋƋκ..
    ...κƎƎƎƎƋƍƋƋƋƋƋƋƋƋƍƋκ...
    ...κƎƎƎƎƋƍƋƋƋƋƋƋƋƋƍκκκκ.
    ....κκƎƍƍƍƎƎƎκκκκƍƍƍƍƍƎκ
    ......κκκκκκκ....κκκκκκ.
    """,
    """
    .........κκκƍκ..........
    ........κƋƍκƍκ..........
    ........κƋƍκƍκ..........
    ........κƋƋƍƍκ..........
    .......κƋƋƋƋƋκ..........
    ......κκƋƎƎƋƋƋκ.........
    ....κκƋƋƋƐƋƋƋƋκ.........
    ...κeƋƋƋƋƋƋƋƋκ..........
    ...κƎƋƏκκƏƏƏƋƍκ.........
    ....κκκκƏƏƏƋƋƋƍκ........
    .......κƏƏƏƋƋƋƋκ........
    ........κƏƏƋƋƋƋƍκ.......
    .......κƋƋƍƋƋƋƋƋƍκ......
    .......κƋƋƍƋƋƋƋƋƋƍκκ....
    .......κƋƋƍƋƋƋƋƋƋƋƍƍκ...
    .......κƋƋƍƋƋƋƋƋƋƋƋƋƍκ..
    .......κƋƋƍƋƋƋƋƋƋƋƋƋƋκ..
    ...κκ..κƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    ..κƎƎκκκƋƍƋƋƋƋƋƋƋƋƋƋƋκ..
    .κƎƎƎƎƎƎƋƍƋƋƋƋƋƋƋƋƍƋƋκ..
    ..κκƎƎƎƎƋƍƋƋƋƋƋƋƋƋƍƋκ...
    ....κκƎƎƋƍƋƋƋƋƋƋƋƋƍκκκκ.
    .....κƎƍƍƍƎƎƎκκκκƍƍƍƍƍƎκ
    ......κκκκκκκ....κκκκκκ.
    """,
]
WOLF_SLEEP = [
    """
    ........................
    ........................
    ........................
    ........................
    ........................
    ......κκκκκ.............
    ....κκƍƍƍƍƍκκκκκ........
    ...κƋƋƋƋƋκκκƍƍƍƍκκκκ....
    ...κƋƋƋƋƋƍƍƍƍƍƍƍƍƍƍƍκκ..
    κκκƋƋƎƎƋƋƋƍƍƋƋƋƋƍƍƍƍƍƍκ.
    eƋƋƋƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƍƍƍκ
    ƎƋƋƋƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƍƍκ
    κκκκκκƎƎƎƎƋƋƋƋƋƋƋƋƋƋƋƍκ.
    ...κƎƎƎƎƎƎƋƋƋƋƋƋƋƋƋƋƋƍκ.
    ...κƎƎƎƎƎƎƋƋƋƋƋƋƍκκκκκ..
    ....κκκκκκκκκκκκκ.......
    """,
    """
    ........................
    ........................
    ........................
    ........................
    ........................
    ......κκκκκ.κκκκ........
    ....κκƍƍƍƍƍκƍƍƍƍκκκκ....
    ...κƋƋƋƋƋƍƍƍƍƍƍƍƍƍƍƍκκ..
    ...κƋƋƋƋƋƍƍƍƋƋƋƋƍƍƍƍƍƍκ.
    κκκƋƋƎƎƋƋƋƍƋƋƋƋƋƋƋƋƋƍƍƍκ
    eƋƋƋƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƍκ
    ƎƋƋƋƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƍƏκ
    κκκκκκƎƎƎƎƋƋƋƋƋƋƋƋƋƋƋƍκ.
    ...κƎƎƎƎƎƎƋƋƋƋƋƋƋƋƋƋƋƍκ.
    ...κƎƎƎƎƎƎƋƋƋƋƋƋƍκκκκκ..
    ....κκκκκκκκκκκκκ.......
    """,
    """
    ........................
    ........................
    ........................
    ........................
    ........................
    ......κκκκκ.κκκκ........
    ....κκƍƍƍƍƍκƍƍƍƍκκκκ....
    ...κƋƋƋƋƋƍƍƍƍƍƍƍƍƍƍƍκκ..
    ...κƋƋƋƋƋƍƍƍƋƋƋƋƍƍƍƍƍƍκ.
    κκκƋƋƎƎƋƋƋƍƋƋƋƋƋƋƋƋƋƍƍƍκ
    eƋƋƋƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƋƍκ
    ƎƋƋƋƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƍƏκ
    κκκκκκƎƎƎƎƋƋƋƋƋƋƋƋƋƋƋƍκ.
    ...κƎƎƎƎƎƎƋƋƋƋƋƋƋƋƋƋƋƍκ.
    ...κƎƎƎƎƎƎƋƋƋƋƋƋƍκκκκκ..
    ....κκκκκκκκκκκκκ.......
    """,
    """
    ........................
    ........................
    ........................
    ........................
    ........................
    ......κκκκκ.............
    ....κκƍƍƍƍƍκκκκκ........
    ...κƋƋƋƋƋκκκƍƍƍƍκκκκ....
    ...κƋƋƋƋƋƍƍƍƍƍƍƍƍƍƍƍκκ..
    κκκƋƋƎƎƋƋƋƍƍƋƋƋƋƍƍƍƍƍƍκ.
    eƋƋƋƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƍƍƍκ
    ƎƋƋƋƋƋƋƋƋƋƍƋƋƋƋƋƋƋƋƋƋƍƍκ
    κκκκκκƎƎƎƎƋƋƋƋƋƋƋƋƋƋƋƍκ.
    ...κƎƎƎƎƎƎƋƋƋƋƋƋƋƋƋƋƋƍκ.
    ...κƎƎƎƎƎƎƋƋƋƋƋƋƍκκκκκ..
    ....κκκκκκκκκκκκκ.......
    """,
]
RAVEN_WALK = [
    """
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ...........................κκκκκκ.......................
    ..........................κƑƓƓƑƑƑκ......................
    .........................κƑƓƑƑƑƑƑƑκ.....................
    ........................κƑƑƓƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑ&ƑƕƑƑƕƑ&Ƒκ....................
    ........................κƑeƑƖ&ƖƖƑeƑκ....................
    .........................κƑƑƖƖƖƕƑƑκ.....................
    ..........................κƑƖƖƖƕƑκ......................
    ........................κκƕƑƑƖƕƑƑƑκκ....................
    .......................κƓƑƑƑƑƖƕƕƑƑƑƓκ...................
    .......................κƓƑƑƑƑƖƕƑƑƑƑƓκ...................
    .......................κƓƑƑƑƑƑƑƑƑƑƑƓκ...................
    .......................κƑƓƑƑƕƕƕƕƑƑƓƑκ...................
    .......................κƕƓƑƑƑƑƑƑƑƑƓƓκ...................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƕƕƕƑƑƕƕƕƑκ....................
    .........................κƕƕƕƑƑƕƕƕκ.....................
    ..........................κƕƕƑƑƕƕκ......................
    ..........................κƖƕƑƑƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    .........................κκƖƕƕƕƕƖκκ.....................
    ........................κƖƖƖƖƕƕƖƖƖƖκ....................
    .........................κκκκκκκκκκ.....................
    """,
    """
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ...........................κκκκκκ.......................
    ..........................κƑƓƓƑƑƑκ......................
    ................κ.κκ.....κƑƓƑƑƑƑƑƑκ.....κκ.κ............
    ...............κƑκƓƓκ...κƑƑƓƑƑƑƑƑƑƑκ...κƓƓκƑκ...........
    ................κƑƑƓκ...κƑƑƑƑƑƑƑƑƑƑκ...κƓƑƑκ............
    ...............κκƑƑƑƓκ..κƑ&ƑƕƑƑƕƑ&Ƒκ..κƓƑƑƑκκ...........
    ..............κƕƕƕƕƑƑƓκκκƑeƑƖ&ƖƖƑeƑκκκƓƑƑƕƕƕƕκ..........
    ...............κκƑƑƑƑƓƓƑκκƑƑƖƖƖƕƑƑκκƑƓƓƑƑƑƑκκ...........
    ..............κƑƑƑƑƑƑƑƓƓƑκƑƑƖƖƖƕƑƑκƑƓƓƑƑƑƑƑƑƑκ..........
    .............κƑƕκκκƑƑƑƑƓƑƑκƕƑƖƕƑƕκƑƑƓƑƑƑƑκκκƕƑκ.........
    .............κƕƕκ..κƑƑƑƓƓƑƕƑƑƖƕƑƑƑƑƓƓƑƑƑκ..κƕƕκ.........
    ............κƕƕκ...κƑƑƑƑƓƕƑƑƑƖƕƕƑƑƑƓƑƑƑƑκ...κƕƕκ........
    ...........κƕƕκ.....κƑƑƑƑƑƑƑƑƑƕƑƑƑƑƑƑƑƑκ.....κƕƕκ.......
    ...........κƕκ.......κƑƑƕƑƑƑƑƑƑƑƑƑƑƑƑƑκ.......κƕκ.......
    ............κ........κƑƑƕƑƑƑƕƕƕƕƑƑƑƑƑƑκ........κ........
    ......................κκƕƑƑƕƑƑƑƑƑƑƑƓκκ..................
    ........................κƑƕƑƑƑƑƑƑƑƑκ....................
    ........................κƑƕƑƑƑƑƑƑƑƓκ....................
    .........................κƕƑƑƑƑƑƑƑκ.....................
    .........................κƑƑƑƑƑƑƑƑκ.....................
    ..........................κƑƑƑƑƑƑκ......................
    ...........................κƑƑƑƑκ.......................
    ...........................κƕƕƕƕκ.......................
    ...........................κƕƕƕƕκ.......................
    ...........................κƕƕƕƕκ.......................
    ...........................κƕƕƕƕκ.......................
    ..........................κκκκκκκκ......................
    .........................κƖƖκ..κƖƖκ.....................
    ..........................κκ....κκ......................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    """,
    """
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ...........................κκκκκκ.......................
    ..........................κƑƓƓƑƑƑκ......................
    .........................κƑƓƑƑƑƑƑƑκ.....................
    ........................κƑƑƓƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑ&ƑƕƑƑƕƑ&Ƒκ....................
    ........................κƑeƑƖ&ƖƖƑeƑκ....................
    ................κ.κκ.....κƑƑƖƖƖƕƑƑκ.....κκ.κ............
    ...............κƑκƑƓκκκκ.κƑƑƖƖƖƕƑƑκ.κκκκƓƑκƑκ...........
    ................κƑƑƑƓƓƓƑκκκƕƑƖƕƑƕκκκƑƓƓƓƑƑƑκ............
    ...............κκƑƑƑƑƑƓƓƓƑƕƑƑƖƕƑƑƑƑƓƓƓƑƑƑƑƑκκ...........
    ..............κƕƕƕƕƑƑƑƑƑƓƕƑƑƑƖƕƕƑƑƑƓƑƑƑƑƑƕƕƕƕκ..........
    ...............κκκƑƑƑƑƑƑƑƑƑƑƑƑƕƑƑƑƑƑƑƑƑƑƑƑκκκ...........
    ..............κƑƑƑκκƑƑƑƑƕƑƑƑƑƑƑƑƑƑƑƑƑƑƑƑκκƑƑƑκ..........
    .............κƑƕκκ..κκƑƑƕƑƑƑƕƕƕƕƑƑƑƑƑƑκκ..κκƕƑκ.........
    .............κƕƕκ.....κƑƕƑƑƕƑƑƑƑƑƑƑƓƑκ.....κƕƕκ.........
    ............κƕƕκ.......κκƑƕƑƑƑƑƑƑƑƑκκ.......κƕƕκ........
    ...........κƕƕκ.........κƑƕƑƑƑƑƑƑƑƓκ.........κƕƕκ.......
    ...........κƕκ...........κƕƑƑƑƑƑƑƑκ...........κƕκ.......
    ............κ............κƑƑƑƑƑƑƑƑκ............κ........
    ..........................κƑƑƑƑƑƑκ......................
    ...........................κƑƑƑƑκ.......................
    ...........................κƕƕƕƕκ.......................
    ...........................κƕƕƕƕκ.......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖκκκκƖκ......................
    .........................κκƖκ..κƖκκ.....................
    ........................κƖƖƖƖκκƖƖƖƖκ....................
    .........................κκκκ..κκκκ.....................
    """,
    """
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ...........................κκκκκκ.......................
    ..........................κƑƓƓƑƑƑκ......................
    .........................κƑƓƑƑƑƑƑƑκ.....................
    ........................κƑƑƓƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑ&ƑƕƑƑƕƑ&Ƒκ....................
    ........................κƑeƑƖ&ƖƖƑeƑκ....................
    .........................κƑƑƖƖƖƕƑƑκ.....................
    .........................κƑƑƖƖƖƕƑƑκ.....................
    ..........................κƕƑƖƕƑƕκ......................
    ........................κκƕƑƑƖƕƑƑƑκκ....................
    .......................κƓƑƑƑƑƖƕƕƑƑƑƓκ...................
    .......................κƓƑƑƑƑƑƕƑƑƑƑƓκ...................
    .......................κƓƑƑƑƑƑƑƑƑƑƑƓκ...................
    .......................κƑƓƑƑƕƕƕƕƑƑƓƑκ...................
    .......................κƕƓƑƑƑƑƑƑƑƑƓƓκ...................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƕƕƕƑƑƕƕƕƑκ....................
    .........................κƕƕƕƑƑƕƕƕκ.....................
    ..........................κƕƕƑƑƕƕκ......................
    ..........................κƕƕƑƑƕƕκ......................
    ...........................κƕƕƕƕκ.......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    .........................κκƖκκκκƖκκ.....................
    ........................κƖƖƖƖκκƖƖƖƖκ....................
    .........................κκκκ..κκκκ.....................
    """,
]
RAVEN_REST = [
    """
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ...........................κκκκκκ.......................
    ..........................κƑƓƓƑƑƑκ......................
    .........................κƑƓƑƑƑƑƑƑκ.....................
    ........................κƑƑƓƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑ&ƑƕƑƑƕƑ&Ƒκ....................
    ........................κƑeƑƖ&ƖƖƑeƑκ....................
    .........................κƑƑƖƖƖƕƑƑκ.....................
    .........................κƑƑƖƖƖƕƑƑκ.....................
    ..........................κƕƑƖƕƑƕκ......................
    ........................κκƕƑƑƖƕƑƑƑκκ....................
    .......................κƓƑƑƑƑƖƕƕƑƑƑƓκ...................
    .......................κƓƑƑƑƑƑƕƑƑƑƑƓκ...................
    .......................κƓƑƑƑƑƑƑƑƑƑƑƓκ...................
    .......................κƑƓƑƑƕƕƕƕƑƑƓƑκ...................
    .......................κƕƓƑƑƑƑƑƑƑƑƓƓκ...................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƕƕƕƑƑƕƕƕƑκ....................
    .........................κƕƕƕƑƑƕƕƕκ.....................
    ..........................κƕƕƑƑƕƕκ......................
    ..........................κƕƕƑƑƕƕκ......................
    ...........................κƕƕƕƕκ.......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    .........................κκƖκκκκƖκκ.....................
    ........................κƖƖƖƖκκƖƖƖƖκ....................
    .........................κκκκ..κκκκ.....................
    """,
    """
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ...........................κκκκκ........................
    ..........................κƓƓƑƑƑκ.......................
    .........................κƓƑƑƑƑƑƑκ......................
    ........................κƑƓƑƑƑƑƑƑƑκ.....................
    .......................κƑƑƑƑƑƑƑƑƑƑκ.....................
    .......................κƑ&ƕƑƑƕƑ&ƑƑκ.....................
    ........................κeƖ&ƖƖƑeƑƑκ.....................
    ........................κƑƖƖƖƕƑƑƑƑκ.....................
    .........................κƖƖƖƕƑƑƑκ......................
    ..........................κƖƕƑƑƑƕκ......................
    ........................κκƕƖƕƑƑƑƑƑκκ....................
    .......................κƓƑƑƖƕƑƕƑƑƑƑƓκ...................
    .......................κƓƑƑƑƑƕƑƑƑƑƑƓκ...................
    .......................κƓƑƑƑƑƑƑƑƑƑƑƓκ...................
    .......................κƑƓƑƑƕƕƕƕƑƑƓƑκ...................
    .......................κƕƓƑƑƑƑƑƑƑƑƓƓκ...................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƕƕƕƑƑƕƕƕƑκ....................
    .........................κƕƕƕƑƑƕƕƕκ.....................
    ..........................κƕƕƑƑƕƕκ......................
    ..........................κƕƕƑƑƕƕκ......................
    ...........................κƕƕƕƕκ.......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    .........................κκƖκκκκƖκκ.....................
    ........................κƖƖƖƖκκƖƖƖƖκ....................
    .........................κκκκ..κκκκ.....................
    """,
    """
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ...........................κκκκκκ.......................
    ..........................κƑƓƓƑƑƑκ......................
    .........................κƑƓƑƑƑƑƑƑκ.....................
    ........................κƑƑƓƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƕƑƑƕƑƑƑκ....................
    ........................κƑƕƑƖ&ƖƖƑƕƑκ....................
    .........................κƑƑƖƖƖƕƑƑκ.....................
    .........................κƑƑƖƖƖƕƑƑκ.....................
    ..........................κƕƑƖƕƑƕκ......................
    ........................κκƕƑƑƖƕƑƑƑκκ....................
    .......................κƓƑƑƑƑƖƕƕƑƑƑƓκ...................
    .......................κƓƑƑƑƑƑƕƑƑƑƑƓκ...................
    .......................κƓƑƑƑƑƑƑƑƑƑƑƓκ...................
    .......................κƑƓƑƑƕƕƕƕƑƑƓƑκ...................
    .......................κƕƓƑƑƑƑƑƑƑƑƓƓκ...................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƕƕƕƑƑƕƕƕƑκ....................
    .........................κƕƕƕƑƑƕƕƕκ.....................
    ..........................κƕƕƑƑƕƕκ......................
    ..........................κƕƕƑƑƕƕκ......................
    ...........................κƕƕƕƕκ.......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    .........................κκƖκκκκƖκκ.....................
    ........................κƖƖƖƖκκƖƖƖƖκ....................
    .........................κκκκ..κκκκ.....................
    """,
    """
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ........................................................
    ............................κκκκκ.......................
    ...........................κƑƓƓƑƑκ......................
    ..........................κƑƓƑƑƑƑƑκ.....................
    .........................κƑƑƓƑƑƑƑƑƑκ....................
    .........................κƑƑƑƑƑƑƑƑƑƑκ...................
    .........................κƑƑ&ƑƕƑƑƕ&Ƒκ...................
    .........................κƑƑeƑƖ&ƖƖeκ....................
    .........................κƑƑƑƑƖƖƖƕƑκ....................
    ..........................κƑƑƑƖƖƖƕκ.....................
    ..........................κƕƑƑƑƖƕƕκ.....................
    ........................κκƕƑƑƑƑƖƕƑκκ....................
    .......................κƓƑƑƑƑƑƕƖƕƑƑƓκ...................
    .......................κƓƑƑƑƑƑƑƕƑƑƑƓκ...................
    .......................κƓƑƑƑƑƑƑƑƑƑƑƓκ...................
    .......................κƑƓƑƑƕƕƕƕƑƑƓƑκ...................
    .......................κƕƓƑƑƑƑƑƑƑƑƓƓκ...................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƑƑƑƑƑƑƑƑƑκ....................
    ........................κƑƕƕƕƑƑƕƕƕƑκ....................
    .........................κƕƕƕƑƑƕƕƕκ.....................
    ..........................κƕƕƑƑƕƕκ......................
    ..........................κƕƕƑƑƕƕκ......................
    ...........................κƕƕƕƕκ.......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    ..........................κƖƕƕƕƕƖκ......................
    .........................κκƖκκκκƖκκ.....................
    ........................κƖƖƖƖκκƖƖƖƖκ....................
    .........................κκκκ..κκκκ.....................
    """,
]

# The share of a block, outline counted, that makes it a 1x cell: under half,
# so a slim leg or tail still stands.
CREATURE_COVER = (3, 8)
# The features a 1x cell keeps from fewer of its block's pixels than the rest:
# each key's least count. A creature's eye is its face; a raven's slate beak and
# feet are all that part it from the dark.
CREATURE_FEATURES = {EYE: 3, RAVEN_BEAK: 3}
# Each ramp read as its base: at 1x a shade is a speck, not a form.
CREATURE_RAMPS = {
    OB_FUR_LT: OB_FUR,
    OB_FUR_SH: OB_FUR,
    OB_FUR_DK: OB_FUR,
    OB_FEATHER_LT: OB_FEATHER,
    OB_FEATHER_SH: OB_FEATHER,
    OB_DISC_SH: OB_DISC,
    OB_BEAK_SH: OB_BEAK,
    WOLF_LT: WOLF,
    WOLF_SH: WOLF,
    WOLF_DK: WOLF,
    RAVEN_SH: RAVEN,
}


def creature_cell(cells, _bx, _by):
    """A creature's block at 1x: drawn to `CREATURE_COVER`, so the silhouette
    holds; then a feature it shows, else its commonest material inside the
    outline."""
    need, of = CREATURE_COVER
    if (len(cells) - cells.count(T)) * of < len(cells) * need:
        return None
    inside = [CREATURE_RAMPS.get(k, k) for k in cells if k not in (T, SILHOUETTE)]
    if not inside:
        return None
    feature = next(
        (k for k, least in CREATURE_FEATURES.items() if cells.count(k) >= least), None
    )
    return feature or max(dict.fromkeys(inside), key=inside.count)


# Per frame, the master rows its bob lifts it: a 1x cell is `S` rows, so the
# 1x reads the frame settled back, or the bob would jump it a whole cell.
CREATURE_BOB = {"cat_walk_2": 1, "cat_walk_6": 1} | {
    f"dog_walk_{i}": b for i, b in enumerate((0, 0, 1, 1, 0, 0, 1, 1)) if b
}
# Per frame, the 1x cells set by hand where the reading misses: `(x, y, key)`.
CREATURE_FIXES = {
    # the eye, a speck its block outvotes; the legs, which the read joins into
    # one bar, apart between the hind and the fore pair and where a paw swings
    **{
        f"dog_walk_{i}": [(6, 1, EYE), (3, 5, T)] + legs
        for i, legs in enumerate(
            (
                [],
                [],
                [(4, 5, T), (6, 5, T)],
                [(6, 5, T)],
                [(6, 5, T)],
                [(4, 5, T), (6, 5, T)],
                [(4, 5, T)],
                [],
            )
        )
    },
    # both eyes, open but for the blink of the last frame
    **{f"dog_sit_{i}": [(2, 1, EYE), (3, 1, EYE)] for i in range(3)},
    # the eye, a single amber pixel, read as an eye; the legs apart as the
    # trot sets them
    **{
        f"cat_walk_{i}": [(6, 1, EYE)] + [(x, 5, T) for x in gap]
        for i, gap in enumerate(
            (
                (3,),
                (3, 6),
                (3, 6),
                (3,),
                (3,),
                (3, 6),
                (3, 6),
                (3,),
            )
        )
    },
    **{f"cat_sit_{i}": [(2, 1, EYE)] for i in range(4)},
}


# The most cells a frame's fixes may draw or clear: past it, the 1x is no
# longer its master read, and the master should change instead.
CREATURE_FIX_MOST = 4


def creature_base(name, g):
    """Frame `name`'s 1x: its master `g`, settled from its bob, read at 1x,
    then its fixes."""
    bob = CREATURE_BOB.get(name, 0)
    out = block_read([[T] * len(g[0])] * bob + g[: len(g) - bob], creature_cell)
    reshaped = 0
    for x, y, k in CREATURE_FIXES.get(name, ()):
        reshaped += (out[y][x] == T) != (k == T)
        out[y][x] = k
    require(
        reshaped <= CREATURE_FIX_MOST,
        f"{name}: {reshaped} cells fixed past its master's silhouette",
    )
    return out


def master(text):
    return [list(row) for row in inspect.cleandoc(text).split("\n")]


CREATURES = {
    "cat_walk": ("The wolf walking, east: a trot.", WOLF_WALK),
    "dog_walk": ("The owlbear walking, east: a heavy, rolling gait.", OWLBEAR_WALK),
    "cat_sit": ("The wolf sitting: breathing, and once a loop a tail flick.", WOLF_SIT),
    "cat_sleep": ("The wolf asleep, curled up under its brush: breathing.", WOLF_SLEEP),
    "dog_sit": (
        "The owlbear sitting, facing us: breathing, and once a loop a blink.",
        OWLBEAR_SIT,
    ),
    "dog_sleep": (
        "The owlbear asleep, its head on its paws: breathing.",
        OWLBEAR_SLEEP,
    ),
    "lobster_rest": (
        "The raven at rest, facing us: turning its head, and once a loop a blink.",
        RAVEN_REST,
    ),
    "lobster_walk": (
        "The raven hopping, facing us: a crouch, a flap aloft, a landing.",
        RAVEN_WALK,
    ),
}


# ---- the camp: a campaign's floor 0, drawn on the office's own canvases --------
# Each piece stands in for the office piece of the same name and size, so the
# layout, footprints and reachability never see the camp: `camp.toml` lays each
# `camp_<piece>` over its office piece for floor 0 alone.

# The office canvases, in 1x cells, that the camp's stand-ins keep.
CAMP_CANVAS = {
    "desk": (DESK_ART_W, 9),
    "desk_north": (DESK_ART_W, 11),
    "desk_front": (DESK_ART_W, 9),
    "desk_chair": (8, 5),
    "seated_sleeping": (8, 10),
    "side_table": (SIDE_TABLE_W, SIDE_TABLE_H),
    "floor_lamp": (LAMP_W, LAMP_H),
    "meeting_sofa": (20, 7),
    "phone_booth": (7, 15),
    "door": (16, 14),
}
# The fire's keys, hottest first: its core glows of its own, as a bulb does.
FLAME_CORE, FLAME, FLAME_ROOT = BULB, VERMILION, DARK_RED
TENT, TENT_SH, TENT_DK = OFFWHITE_SH, PRINT, GREY
STONE, STONE_LT, STONE_SH = GREY, LAMP_HI, SLATE


def camp_canvas(piece):
    """The office piece's own `@Nx` canvas."""
    w, h = CAMP_CANVAS[piece]
    return canvas(w * S, h * S)


def oval(g, cx, cy, rx, ry, k, only=None):
    """An ellipse of `k`, painted over the `only` keys when given."""
    for y in range(len(g)):
        for x in range(len(g[0])):
            if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1 and (
                only is None or g[y][x] in only
            ):
                g[y][x] = k


def stroke(g, x0, y0, x1, y1, k):
    """A one-pixel line from `(x0, y0)` to `(x1, y1)`."""
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(n + 1):
        put(g, round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n), k)


def flame(g, cx, base, h, half):
    """A tongue of flame up `h` rows from its root row `base`, `half` wide at
    the root: an ember root, a vermilion body round a glowing core."""
    for i in range(h):
        t = i / h
        w = half * (1 - t) ** 0.7
        for x in range(round(cx - w) - 1, round(cx + w) + 2):
            d = abs(x + 0.5 - cx)
            if d > w + 0.2:
                continue
            core = d < w * 0.5 and t < 0.75
            put(g, x, base - i, FLAME_CORE if core else FLAME_ROOT if i == 0 else FLAME)


def lantern(g, x, y):
    """A small iron lantern, its flame in the bulb key: `(x, y)` is the left
    end of its four-pixel flame row, where the desk's bulb is read."""
    rect(g, x, y - 2, x + 4, y, IRON_DK)
    rect(g, x + 1, y - 3, x + 3, y - 2, IRON)
    rect(g, x, y, x + 4, y + 2, BULB)
    rect(g, x, y + 2, x + 4, y + 3, IRON_DK)


def lantern_stake(g, x, y, ground):
    """A stake driven in the ground, its lantern hung with its flame row at
    `(x, y)`."""
    rect(g, x + 1, y + 3, x + 3, ground, WOOD)
    rect(g, x + 1, y + 3, x + 2, ground, WOOD_LT)
    lantern(g, x, y)


def bedroll(g, x0, y0, x1, y1, pillow_west=True):
    """A bedroll laid out on the ground, seen from above: a quilted mat, its
    red wool blanket turned down, the rolled end a pillow; a desk is not
    recoloured per sitter, so the blanket is the camp's own colour."""
    rect(g, x0, y0, x1, y1, TAN)
    rect(g, x0, y1 - 2, x1, y1, BROWN)
    for x in range(x0 + 5, x1 - 2, 6):  # the quilting
        rect(g, x, y0 + 1, x + 1, y1 - 2, BROWN)
    third = (x1 - x0) // 3
    bx0, bx1 = (x0 + third, x1) if pillow_west else (x0, x1 - third)
    rect(g, bx0, y0 - 1, bx1, y1, RED)
    rect(g, bx0, y0 - 1, bx1, y0 + 1, VERMILION)
    rect(g, bx0, y1 - 2, bx1, y1, DARK_RED)
    fold = bx0 if pillow_west else bx1 - 4  # the turned-down edge
    rect(g, fold, y0 - 1, fold + 4, y1, VERMILION)
    edge = fold + 3 if pillow_west else fold
    rect(g, edge, y0 - 1, edge + 1, y1, WOOD_DK)
    px = x0 if pillow_west else x1 - 7
    rect(g, px, y0 - 2, px + 7, y1 + 1, OFFWHITE_SH)
    rect(g, px, y0 - 2, px + 7, y0, OFFWHITE)
    rect(g, px + 3, y0, px + 4, y1, PRINT)
    rect(g, px, y1 - 1, px + 7, y1 + 1, PRINT)


def pack_bag(g, x0, y0):
    """A leather pack standing on its base: its flap buckled, a rolled cloak
    strapped over the top, lit on its west."""
    w, h = 12, 15
    rect(g, x0 + 1, y0, x0 + w - 1, y0 + h, LEATHER)
    rect(g, x0, y0 + 2, x0 + w, y0 + h, LEATHER)
    rect(g, x0, y0 + 2, x0 + 1, y0 + h, WOOD_LT)
    rect(g, x0 + w - 2, y0 + 2, x0 + w, y0 + h, LEATHER_SH)
    rect(g, x0 + 1, y0, x0 + w - 1, y0 + 6, WOOD)
    rect(g, x0 + 1, y0 + 6, x0 + w - 1, y0 + 7, LEATHER_SH)
    rect(g, x0 + 5, y0 + 5, x0 + 7, y0 + 8, GOLD)
    rect(g, x0 - 1, y0 - 3, x0 + w + 1, y0, FABRIC_SH)
    rect(g, x0 - 1, y0 - 3, x0 + w + 1, y0 - 2, FABRIC)
    for x in (x0 + 2, x0 + w - 3):
        rect(g, x, y0 - 3, x + 1, y0 + 4, LEATHER_SH)


def camp_desk():
    """The camp's sleeping spot, where the viewer-facing desk stands: a
    bedroll on the ground under a red wool blanket, a pack at its
    east end and a lantern on a stake west, where the desk lamp glows; the cup
    and the tower stand where the desk's arrangement marks them."""
    g = camp_canvas("desk")
    bedroll(g, 10, 20, 52, 34)
    pack_bag(g, 38, 19)
    lantern_stake(g, 5, 6, 34)
    union_outline(g)
    return g


def camp_desk_north():
    """The back-turned sleeping spot: the bedroll seen past its sleeper, the
    pack at its far west end, the lantern on its stake east, where that desk's
    lamp glows."""
    g = camp_canvas("desk_north")
    bedroll(g, 4, 28, 45, 42, pillow_west=False)
    pack_bag(g, 6, 25)
    lantern_stake(g, 46, 16, 42)
    union_outline(g)
    return g


def camp_desk_front():
    """The sleeping spot's front: the pack, which hides the part of a
    sleeper's cup behind it."""
    g = camp_canvas("desk_front")
    pack_bag(g, 38, 19)
    union_outline(g)
    return g


def camp_desk_chair():
    """A log stump for a seat: its sawn top lit and ringed, the bark falling
    into shade, roots spreading at its foot."""
    g = camp_canvas("desk_chair")
    w = len(g[0])
    rect(g, 7, 6, w - 7, 17, WOOD_SH)
    rect(g, 7, 6, 9, 17, WOOD)
    for x in range(11, w - 9, 4):  # the bark's furrows
        rect(g, x, 9, x + 1, 17, WOOD_DK)
    rect(g, w - 9, 6, w - 7, 17, WOOD_DK)
    for x0, x1 in ((3, 9), (w - 9, w - 3), (13, 19)):  # the roots
        rect(g, x0, 16, x1, 19, WOOD_SH)
        rect(g, x0, 16, x1, 17, WOOD)
    oval(g, w / 2, 6, 9.5, 4.6, WOOD_LT)
    oval(g, w / 2, 6, 7.0, 3.2, WOOD_HI)
    oval(g, w / 2, 6, 4.6, 2.0, WOOD_LT)
    oval(g, w / 2, 6, 2.0, 0.9, WOOD)
    union_outline(g)
    return g


def blanket_sleeper(head_x, head_y):
    """An adventurer asleep on the ground, seen from above, curled on their
    side under a blanket in their colour: its folds in shade, the knees drawn
    up, a hand at its hem; the head at the crown mark, which the pack's
    hairstyle dresses."""
    g = camp_canvas("seated_sleeping")
    cx = len(g[0]) / 2
    oval(g, cx, 26, 13.5, 12.0, SHIRT)
    oval(g, cx + 4, 33, 9.0, 6.0, SHIRT)
    oval(g, cx - 3, 22, 10, 8, SHIRT_LT, only={SHIRT})
    oval(g, cx + 4, 31, 10, 7, SHIRT_SH, only={SHIRT})
    for fold in ((9, 25, 15, 32), (18, 22, 21, 31), (12, 35, 20, 37)):
        stroke(g, *fold, SHIRT_OUT)
    rect(g, round(cx) + 3, 18, round(cx) + 7, 21, SKIN)
    put(g, round(cx) + 6, 20, SKIN_SH)
    disc(g, head_x, head_y, 5.0, SKIN)
    union_outline(g)
    return g


def camp_sleeper():
    """An adventurer asleep, curled under a blanket in their colour."""
    return blanket_sleeper(16, 12)


def camp_sleeper_alt():
    """The other sleeper, curled the other way."""
    return [list(reversed(row)) for row in blanket_sleeper(15, 13)]


# The campfire's flicker: per frame, each tongue's height.
CAMP_FIRE_FLICKER = ((14, 8, 9), (12, 9, 7), (13, 7, 10), (11, 8, 8))


def camp_fire():
    """The campfire: a ring of stones lit along their tops, split logs crossed
    in it, flames rising from the embers and flickering."""
    return [camp_fire_frame(heights) for heights in CAMP_FIRE_FLICKER]


def camp_fire_1x():
    """The campfire at 1x: its ring of stones, embers, and flames flickering
    as the cutaway's do; the 1x is its own drawing, so the two densities keep
    one frame count."""
    frames = []
    for heights in CAMP_FIRE_FLICKER:
        g = canvas(SIDE_TABLE_W, SIDE_TABLE_H)
        for x in range(SIDE_TABLE_W):
            put(g, x, 3, STONE_LT if x % 2 else STONE)
        for x, k in ((0, STONE), (1, FLAME_ROOT), (5, FLAME_ROOT), (6, STONE)):
            put(g, x, 2, k)
        # the tongues as CAMP_FIRE_FLICKER lists them: centre, west, east
        for x, (hh, tall) in zip((3, 2, 4), zip(heights, (13, 8, 9))):
            rows = 2 + (hh >= tall) if x == 3 else 1 + (hh >= tall)
            for i in range(rows):
                put(g, x, 2 - i, FLAME_CORE if i == 0 and x == 3 else FLAME)
        frames.append(g)
    return frames


def camp_fire_frame(heights):
    """The campfire with its three tongues of flame `heights` tall."""
    g = camp_canvas("side_table")
    w, h = len(g[0]), len(g)
    oval(g, w / 2, h - 5, 12, 3.6, SHADOW)
    for x0, y0, x1, y1 in ((5, h - 4, 22, h - 8), (6, h - 8, 22, h - 4)):
        stroke(g, x0, y0, x1, y1, WOOD)
        stroke(g, x0, y0 + 1, x1, y1 + 1, WOOD_DK)
    for (cx, half), hh in zip(((14, 4.4), (9.5, 2.4), (18.5, 2.6)), heights):
        flame(g, cx, h - 6, hh, half)
    for sx in (2, w - 6):  # the ring's back stones
        rect(g, sx, h - 9, sx + 4, h - 6, STONE)
        rect(g, sx, h - 9, sx + 4, h - 8, STONE_LT)
    for i, sx in enumerate(range(1, w - 3, 4)):  # and its front row
        y = h - 4 + (1 if 0 < i < 5 else 0)
        rect(g, sx, y - 1, sx + 4, y + 2, STONE)
        rect(g, sx, y - 1, sx + 4, y, STONE_LT)
        rect(g, sx + 3, y, sx + 4, y + 2, STONE_SH)
    union_outline(g)
    return g


def camp_torch():
    """A torch on a pole driven into the ground: pitch-soaked wrappings, a
    flame whose glow is the lamp's, stones wedged at its foot."""
    g = camp_canvas("floor_lamp")
    h = len(g)
    rect(g, 7, 15, 9, h - 3, WOOD)
    rect(g, 7, 15, 8, h - 3, WOOD_LT)
    rect(g, 4, h - 4, 12, h - 1, STONE)
    rect(g, 4, h - 4, 12, h - 3, STONE_LT)
    rect(g, 5, 11, 11, 16, LEATHER)
    for y in (12, 14):
        rect(g, 5, y, 11, y + 1, LEATHER_SH)
    flame(g, 8, 10, 10, 3.4)
    flame(g, 10.5, 8, 5, 1.4)
    union_outline(g)
    return g


def log_bench(north):
    """A felled log for a bench: its bark lit along the top where a sitter
    sits, furrowed and knotted, a branch stub, both sawn ends showing their
    rings."""
    w, h = (c * S for c in CAMP_CANVAS["meeting_sofa"])
    g = canvas(w, h)
    top, bot = 9, h - 2
    rect(g, 6, top, w - 6, bot, WOOD_SH)
    rect(g, 6, top, w - 6, top + 3, WOOD)
    rect(g, 6, top, w - 6, top + 1, WOOD_LT)
    rect(g, 6, bot - 3, w - 6, bot, WOOD_DK)
    for x in range(10, w - 10, 7):  # the bark's furrows
        off = (x // 7) % 3
        rect(g, x, top + 5 + off, x + 4, top + 6 + off, WOOD_DK)
    kx, ky = (24, top + 8) if north else (52, top + 7)
    oval(g, kx, ky, 3, 2, WOOD_DK)
    oval(g, kx, ky, 1.4, 0.8, WOOD)
    stub = 60 if north else 18
    rect(g, stub, top - 5, stub + 4, top + 1, WOOD)
    rect(g, stub, top - 5, stub + 1, top + 1, WOOD_LT)
    for cx in (6, w - 6):  # the sawn ends
        oval(g, cx, (top + bot) / 2, 4.5, (bot - top) / 2, WOOD_LT)
        oval(g, cx, (top + bot) / 2, 3.0, (bot - top) / 2 - 2.5, WOOD_HI)
        oval(g, cx, (top + bot) / 2, 1.4, 2.0, WOOD)
    union_outline(g)
    return g


def camp_log():
    """The log bench a south-facing seat sits on."""
    return log_bench(north=False)


def camp_log_north():
    """The log bench a north-facing seat sits on, its knot and stub turned."""
    return log_bench(north=True)


# A raven perched facing west, by its pixels from the foot of its perch.
RAVEN_PERCHED = (
    (0, -1, RAVEN_BEAK),
    (2, -1, RAVEN_BEAK),
    *((x, -2, RAVEN) for x in range(-1, 4)),
    (4, -2, RAVEN_SH),
    *((x, -3, RAVEN) for x in range(-1, 5)),
    (1, -3, RAVEN_SHEEN),
    (5, -3, RAVEN_SH),
    (6, -4, RAVEN_SH),
    *((x, -4, RAVEN) for x in range(-1, 3)),
    *((x, -5, RAVEN) for x in range(-2, 1)),
    (-1, -5, RAVEN_SHEEN),
    (-1, -6, RAVEN),
    (0, -6, RAVEN),
    (-3, -5, RAVEN_BEAK),
    (-4, -5, RAVEN_BEAK),
)


def camp_tent():
    """A pointed canvas tent seen from its front: its west panel lit, its east
    in shade, the flaps tied back on the dark inside, the ridge pole standing
    proud with a raven perched on it, stakes at its corners."""
    g = camp_canvas("phone_booth")
    w, h = len(g[0]), len(g)
    apex, base = 12, h - 2
    for y in range(apex, base):
        t = (y - apex) / (base - apex)
        half = 2 + t * (w / 2 - 2)
        x0, x1 = round(w / 2 - half), round(w / 2 + half)
        rect(g, x0, y, x1, y + 1, TENT)
        rect(g, w // 2, y, x1, y + 1, TENT_SH)
        put(g, x0, y, OFFWHITE)
        if y > apex + 14:  # the door's dark inside, opening downward
            d = (y - apex - 14) / (base - apex - 14) * half * 0.55
            rect(g, round(w / 2 - d), y, round(w / 2 + d), y + 1, SHADOW)
            for side in (-1, 1):  # the flaps folded back
                put(g, round(w / 2 + side * d) - (side < 0), y, TENT_DK)
    rect(g, w // 2 - 1, apex - 6, w // 2 + 1, apex + 2, WOOD)
    for x in (2, w - 5):
        rect(g, x, base - 1, x + 3, base + 1, WOOD_DK)
    union_outline(g)
    for dx, dy, k in RAVEN_PERCHED:
        put(g, w // 2 + dx, apex - 6 + dy, k)
    outline(g, {RAVEN, RAVEN_SH, RAVEN_SHEEN, RAVEN_BEAK}, SILHOUETTE)
    return g


def camp_gate():
    """The camp's gate in a palisade of pointed stakes: shut, swinging open,
    and open on the trail into the dark woods."""
    w, h = (c * S for c in CAMP_CANVAS["door"])
    inner0, inner1 = 16, w - 16
    leaf_w = (inner1 - inner0) // 2
    frames = []
    for shown in (leaf_w, leaf_w // 2, 4):
        g = canvas(w, h)
        for x in [*range(0, 12, 4), *range(w - 12, w, 4)]:  # the palisade
            rect(g, x, 8, x + 4, h, WOOD_SH)
            rect(g, x, 8, x + 1, h, WOOD)
            rect(g, x + 1, 6, x + 3, 8, WOOD_SH)
        rect(g, inner0, 9, inner1, h, SHADOW)  # beyond: the trail at night
        for y in range(9, h):
            half = 2 + (y - 9) / (h - 9) * 9
            rect(g, round(w / 2 - half), y, round(w / 2 + half), y + 1, SLATE)
        for x0 in (inner0 + 1, inner1 - 8):
            for y in range(12, 34):
                half = (y - 12) / 22 * 3.5
                rect(
                    g,
                    round(x0 + 3.5 - half),
                    y,
                    round(x0 + 3.5 + half) + 1,
                    y + 1,
                    LEAF_DK,
                )
        for x in (12, w - 16):  # the posts and the beam across them
            rect(g, x, 2, x + 4, h, WOOD)
            rect(g, x, 2, x + 1, h, WOOD_LT)
            rect(g, x + 3, 2, x + 4, h, WOOD_SH)
        rect(g, 10, 4, w - 10, 9, WOOD)
        rect(g, 10, 4, w - 10, 5, WOOD_LT)
        rect(g, 10, 8, w - 10, 9, WOOD_DK)
        for side in (0, 1):  # the leaves, swinging in toward us
            x0 = inner0 if side == 0 else inner1 - shown
            pitch = 4 if shown == leaf_w else 2
            for x in range(x0, x0 + shown, pitch):
                rect(g, x, 10, x + pitch, h, WOOD)
                put(g, x, 10, WOOD_LT)
                rect(g, x, 11, x + 1, h, WOOD_LT if pitch > 2 else WOOD_SH)
            rect(g, x0, 18, x0 + shown, 20, WOOD_DK)
            rect(g, x0, h - 14, x0 + shown, h - 12, WOOD_DK)
        frames.append(g)
    return frames


# The skyline seen from camp: the office's buildings, key for key and canvas for
# canvas, redrawn as pines, mountains and a ruined watchtower in the city's
# materials, which the backdrop colours by depth and sky.
def pine(g, cx, top, bottom, half):
    """A pine's silhouette: tiers of boughs widening downward over a trunk."""
    tiers = 4
    span = (bottom - top - 3) / tiers
    for i in range(tiers):
        y0 = top + i * span
        for y in range(round(y0), min(bottom - 3, round(y0 + span * 1.6))):
            t = (y - y0) / (span * 1.6)
            reach = half * (0.4 + 0.6 * (i + 1) / tiers) * t
            rect(g, round(cx - reach), y, round(cx + reach) + 1, y + 1, CITY_FACADE)
    rect(g, round(cx) - 1, bottom - 4, round(cx) + 1, bottom, CITY_SHADE)


def mountain(g, peaks):
    """Mountains: each `(x, height)` peak's slopes down to the canvas's foot,
    snow along its upper ridges in the roof key."""
    w, h = len(g[0]), len(g)
    for px, ph in peaks:
        for x in range(w):
            top = h - ph + abs(x + 0.5 - px) * 1.3
            if top >= h:
                continue
            for y in range(max(0, round(top)), h):
                g[y][x] = CITY_FACADE
            if top < h - ph + 8:
                put(g, x, max(0, round(top)), CITY_ROOF)


def watchtower(cw, ch):
    """A ruined watchtower: a tapering stone shaft, its crenellations broken,
    two arrow slits lit by a fire within."""
    g = canvas(cw, ch)
    tw = min(cw - 2, 22)
    x0 = (cw - tw) // 2
    for y in range(10, ch):
        half = tw / 2 * (0.75 + 0.25 * (y - 10) / (ch - 10))
        rect(g, round(cw / 2 - half), y, round(cw / 2 + half), y + 1, CITY_FACADE)
    for dx, top in ((0, 5), (5, 5), (10, 8)):
        rect(g, x0 + dx, top, x0 + dx + 3, 11, CITY_FACADE)
    rect(g, x0, 10, x0 + tw, 12, CITY_ROOF)
    for y0 in (17, 27):
        rect(g, cw // 2 - 1, y0, cw // 2 + 1, y0 + 5, CITY_GLASS)
    shade_east(g)
    return g


def camp_skyline():
    """Each office building's key redrawn for the camp, on its own canvas."""
    out = {}
    for name, (cw, ch) in CAMP_BUILDING_SIZE.items():
        g = canvas(cw, ch)
        if name in ("slab", "setback"):
            mountain(g, ((cw * 0.35, ch * 0.95), (cw * 0.8, ch * 0.7)))
        elif name == "dome":
            mountain(g, ((cw * 0.5, ch * 0.9),))
        elif name == "sign":
            g = watchtower(cw, ch)
        else:
            n = max(1, cw // 12)
            for i in range(n):
                pine(g, (i + 0.5) * cw / n, (i % 2) * ch // 6 + 1, ch, cw / n / 2)
        if name != "sign":
            shade_east(g)
        out[name] = g
    return out


# The office skyline's `@Nx` canvases, which `camp_skyline` keeps key for key.
CAMP_BUILDING_SIZE = {
    "curtain": (24, 60),
    "dome": (28, 44),
    "low": (24, 24),
    "setback": (24, 64),
    "sign": (28, 36),
    "slab": (32, 60),
    "spire": (16, 72),
    "twin": (24, 68),
    "walkup": (20, 40),
}

# The rest of the camp: every office piece the lounge floor still shows, redrawn
# on its own @Nx canvas, in `S` pixels.
PROP_CANVAS = {
    "filing_cabinet": (16, 24),
    "whiteboard": (56, 44),
    "bulletin_board": (40, 24),
    "notice_board": (32, 20),
    "meeting_screen": (56, 48),
    "tv_stand": (40, 40),
    "pantry": (128, 40),
    "pantry_small": (80, 32),
    "kitchen_island": (80, 28),
    "vending_machine": (28, 52),
    "printer": (28, 32),
    "water_cooler": (16, 36),
    "coat_rack": (20, 48),
    "bookshelf": (32, 48),
    "snack_shelf": (28, 40),
    "plant": (24, 28),
    "plant_tall": (24, 40),
    "plant_flower": (24, 24),
    "plant_succulent": (20, 16),
    "exit_sign": (20, 12),
    "wall_clock": (28, 28),
    "pantry_bin": (16, 20),
    "fish_tank": (56, 44),
    "meeting_table": (44, 20),
    "meeting_chair": (28, 28),
    "desk_cup": (8, 8),
    "token_tower": (16, 16),
    "token_sheet": (12, 4),
    "standing_desk": (32, 32),
}
PARCHMENT, PARCHMENT_SH, PARCHMENT_INK = OFFWHITE_SH, PRINT, INK
BARREL_WATER, BARREL_WATER_LT = BLUE, CYAN
COIN, COIN_SH = GOLD, BROWN


def prop_canvas(piece):
    """The office piece's own `@Nx` canvas, in pixels."""
    return canvas(*PROP_CANVAS[piece])


def plank_box(g, x0, y0, x1, y1, lid=3):
    """A wooden crate seen from the front and a little above: its lid lit, its
    planks seamed, a frame of darker boards with a cross brace."""
    rect(g, x0, y0, x1, y0 + lid, WOOD_LT)
    rect(g, x0, y0, x1, y0 + 1, WOOD_HI)
    rect(g, x0, y0 + lid, x1, y1, WOOD)
    for y in range(y0 + lid + 3, y1 - 1, 3):
        rect(g, x0 + 1, y, x1 - 1, y + 1, WOOD_SH)
    for x in (x0, x1 - 2):
        rect(g, x, y0 + lid, x + 2, y1, WOOD_SH)
    rect(g, x0, y1 - 2, x1, y1, WOOD_DK)
    stroke(g, x0 + 2, y0 + lid + 1, x1 - 3, y1 - 3, WOOD_SH)


def barrel(g, x0, y0, x1, y1):
    """A barrel standing: its lid an ellipse, staves lit west and shaded east,
    two iron hoops."""
    w = x1 - x0
    rect(g, x0, y0 + 2, x1, y1, WOOD)
    rect(g, x0, y0 + 2, x0 + 2, y1, WOOD_LT)
    rect(g, x1 - 3, y0 + 2, x1, y1, WOOD_SH)
    for x in range(x0 + 4, x1 - 3, 4):
        rect(g, x, y0 + 4, x + 1, y1 - 1, WOOD_SH)
    for y in (y0 + 5, y1 - 5):
        rect(g, x0, y, x1, y + 2, IRON_SH)
        rect(g, x0, y, x1, y + 1, IRON)
    oval(g, x0 + w / 2, y0 + 2.5, w / 2, 2.5, WOOD_LT)
    oval(g, x0 + w / 2, y0 + 2.5, w / 2 - 2, 1.4, WOOD)


def parchment(g, x0, y0, x1, y1, lines=3, seal=False):
    """A pinned sheet of parchment with lines of writing, its foot curling."""
    rect(g, x0, y0, x1, y1, PARCHMENT)
    rect(g, x0, y1 - 1, x1, y1, PARCHMENT_SH)
    for i in range(lines):
        y = y0 + 2 + 2 * i
        if y < y1 - 2:
            rect(g, x0 + 1, y, x1 - 1 - (i % 2) * 2, y + 1, PARCHMENT_SH)
    put(g, (x0 + x1) // 2, y0, IRON_DK)
    if seal:
        rect(g, x1 - 3, y1 - 4, x1 - 1, y1 - 2, DARK_RED)


def camp_crates():
    """Supply crates, one stacked on the other."""
    g = prop_canvas("filing_cabinet")
    w, h = len(g[0]), len(g)
    plank_box(g, 1, h - 12, w - 1, h - 1)
    plank_box(g, 2, 2, w - 2, h - 12)
    union_outline(g)
    return g


def camp_quest_board():
    """A quest board on two posts under a little plank roof: notices, a bounty
    sealed in red, a wanted sketch."""
    g = prop_canvas("whiteboard")
    w, h = len(g[0]), len(g)
    for x in (5, w - 9):
        rect(g, x, 3, x + 4, h - 1, WOOD_SH)
        rect(g, x, 3, x + 1, h - 1, WOOD)
    rect(g, 2, 1, w - 2, 5, WOOD_DK)
    rect(g, 2, 1, w - 2, 2, WOOD)
    rect(g, 4, 7, w - 4, 31, WOOD)
    for y in range(10, 31, 4):
        rect(g, 4, y, w - 4, y + 1, WOOD_SH)
    rect(g, 4, 30, w - 4, 32, WOOD_DK)
    parchment(g, 8, 9, 20, 22, lines=5)
    parchment(g, 23, 11, 33, 28, lines=6, seal=True)
    parchment(g, 36, 9, 48, 20, lines=1)
    oval(g, 42, 14.5, 3, 3, PARCHMENT_SH)  # the wanted sketch's face
    put(g, 41, 14, PARCHMENT_INK)
    put(g, 43, 14, PARCHMENT_INK)
    union_outline(g)
    return g


def camp_hide_map():
    """A map inked on a stretched hide, lashed to a frame of sticks: a trail
    dashed across it to a red cross."""
    g = prop_canvas("bulletin_board")
    w, h = len(g[0]), len(g)
    rect(g, 1, 1, w - 1, 3, WOOD)
    rect(g, 1, h - 3, w - 1, h - 1, WOOD)
    rect(g, 1, 1, 3, h - 1, WOOD_SH)
    rect(g, w - 3, 1, w - 1, h - 1, WOOD_SH)
    oval(g, w / 2, h / 2, w / 2 - 4, h / 2 - 3.5, TAN)
    oval(g, w / 2 - 2, h / 2 - 1.5, w / 2 - 9, h / 2 - 6, OFFWHITE_SH, only={TAN})
    for x, y in ((8, 15), (11, 13), (14, 12), (17, 13), (20, 11), (23, 9), (26, 10)):
        put(g, x, y, PARCHMENT_INK)
    stroke(g, 28, 7, 31, 10, RED)
    stroke(g, 31, 7, 28, 10, RED)
    for x, y in ((6, 8), (9, 7), (12, 8)):  # mountains, inked
        put(g, x, y, BROWN)
        put(g, x - 1, y + 1, BROWN)
        put(g, x + 1, y + 1, BROWN)
    for x, y in ((4, 4), (w - 5, 4), (4, h - 5), (w - 5, h - 5)):  # the lashings
        put(g, x, y, LEATHER)
        put(g, x + 1, y + 1, LEATHER)
    union_outline(g)
    return g


def camp_notices():
    """A small board of notices nailed to the palisade."""
    g = prop_canvas("notice_board")
    w, h = len(g[0]), len(g)
    rect(g, 1, 1, w - 1, h - 1, WOOD)
    for y in range(4, h - 1, 4):
        rect(g, 1, y, w - 1, y + 1, WOOD_SH)
    rect(g, 1, h - 2, w - 1, h - 1, WOOD_DK)
    parchment(g, 4, 3, 14, 16, lines=5)
    parchment(g, 17, 4, 28, 14, lines=4, seal=True)
    union_outline(g)
    return g


def banner(g, x0, x1, top, drop, cloth, cloth_sh, trim):
    """A cloth banner hung from a pole at `top`, `drop` long, its foot cut in
    a swallowtail, a gold device of three rising chevrons."""
    rect(g, x0 - 2, top - 2, x1 + 2, top, WOOD_DK)
    rect(g, x0, top, x1, top + drop, cloth)
    rect(g, x1 - 2, top, x1, top + drop, cloth_sh)
    rect(g, x0, top, x0 + 1, top + drop, trim)
    rect(g, x1 - 1, top, x1, top + drop, trim)
    mid = (x0 + x1) / 2
    for y in range(top + drop - 5, top + drop):
        cut = (y - (top + drop - 5)) * 0.9
        rect(g, round(mid - cut), y, round(mid + cut) + 1, y + 1, T)
    for i in range(3):
        y = top + 6 + 4 * i
        half = (x1 - x0) / 2 - 3
        stroke(g, round(mid - half), y + 3, round(mid), y, trim)
        stroke(g, round(mid), y, round(mid + half), y + 3, trim)


def camp_standard():
    """The company's standard between two poles: a red banner with a gold
    device of rising chevrons, the poles wedged in stones."""
    g = prop_canvas("meeting_screen")
    w, h = len(g[0]), len(g)
    for x in (8, w - 11):
        rect(g, x, 2, x + 3, h - 3, WOOD)
        rect(g, x, 2, x + 1, h - 3, WOOD_LT)
        rect(g, x - 3, h - 5, x + 6, h - 1, STONE)
        rect(g, x - 3, h - 5, x + 6, h - 4, STONE_LT)
    banner(g, 13, w - 13, 5, 30, RED, DARK_RED, GOLD)
    union_outline(g)
    return g


def camp_pennant():
    """A banner on a single pole with a crossbar: slate cloth, a gold device,
    the pole's foot in a ring of stones."""
    g = prop_canvas("tv_stand")
    w, h = len(g[0]), len(g)
    rect(g, w // 2 - 1, 1, w // 2 + 2, h - 3, WOOD)
    rect(g, w // 2 - 1, 1, w // 2, h - 3, WOOD_LT)
    banner(g, 10, w - 10, 4, 24, FABRIC, FABRIC_SH, GOLD)
    rect(g, w // 2 - 6, h - 5, w // 2 + 7, h - 1, STONE)
    rect(g, w // 2 - 6, h - 5, w // 2 + 7, h - 4, STONE_LT)
    union_outline(g)
    return g


def cook_fire(g, cx, ground):
    """A cooking fire: a tripod of poles over it, a pot hung on its chain,
    steam rising."""
    oval(g, cx, ground - 2, 9, 2.5, SHADOW)
    for dx in (-6, -2, 2, 6):
        rect(g, round(cx + dx - 1), ground - 3, round(cx + dx + 2), ground, STONE)
        put(g, round(cx + dx), ground - 3, STONE_LT)
    flame(g, cx - 2.5, ground - 3, 6, 2.0)
    flame(g, cx + 2.5, ground - 3, 7, 2.2)
    top = ground - 26
    stroke(g, round(cx), top, round(cx - 10), ground, WOOD_SH)
    stroke(g, round(cx), top, round(cx + 10), ground, WOOD)
    stroke(g, round(cx), top, round(cx + 1), ground - 1, WOOD_DK)
    for y in range(top + 1, ground - 15):
        put(g, round(cx), y, IRON_DK)
    oval(g, cx, ground - 11, 6, 4.5, IRON_SH)
    oval(g, cx - 1, ground - 12, 4, 3, IRON, only={IRON_SH})
    rect(g, round(cx) - 6, ground - 15, round(cx) + 7, ground - 13, IRON_DK)
    rect(g, round(cx) - 5, ground - 15, round(cx) + 6, ground - 14, BROWN)  # the stew
    for x, y in ((cx - 2, top + 3), (cx + 1, top + 1), (cx + 3, top + 4)):
        put(g, round(x), y, OFFWHITE_SH)


def sack(g, x0, y0, w, h):
    """A grain sack, tied at its neck, slumped on the ground."""
    oval(g, x0 + w / 2, y0 + h * 0.6, w / 2, h * 0.42, TAN)
    oval(g, x0 + w / 2 + 1, y0 + h * 0.66, w / 2 - 2, h * 0.3, BROWN, only={TAN})
    oval(g, x0 + w / 2 - 1, y0 + h * 0.55, w / 2 - 3, h * 0.28, TAN)
    rect(g, round(x0 + w / 2) - 2, y0, round(x0 + w / 2) + 2, y0 + 3, TAN)
    rect(g, round(x0 + w / 2) - 2, y0 + 3, round(x0 + w / 2) + 2, y0 + 4, LEATHER)


def chopping_block(g, x0, y0):
    """A chopping block, a cleaver bitten into its top."""
    rect(g, x0, y0 + 3, x0 + 12, y0 + 12, WOOD_SH)
    rect(g, x0, y0 + 3, x0 + 2, y0 + 12, WOOD)
    oval(g, x0 + 6, y0 + 3, 6, 2.5, WOOD_LT)
    rect(g, x0 + 5, y0 - 5, x0 + 10, y0 + 2, IRON)
    rect(g, x0 + 5, y0 - 5, x0 + 10, y0 - 4, IRON_LT)
    rect(g, x0 + 9, y0 - 9, x0 + 11, y0 - 4, WOOD_DK)


def camp_kitchen():
    """The camp kitchen: a pot on a tripod over its fire, a chopping block, a
    crate of turnips and sacks of grain."""
    g = prop_canvas("pantry")
    h = len(g)
    cook_fire(g, 30, h - 2)
    chopping_block(g, 52, h - 14)
    plank_box(g, 72, h - 18, 92, h - 2)
    for x in (75, 80, 85):
        oval(g, x + 1.5, h - 18, 2.2, 1.6, PINK)
        put(g, x + 1, h - 20, LEAF)
    sack(g, 96, h - 22, 13, 20)
    sack(g, 108, h - 18, 12, 16)
    union_outline(g)
    return g


def camp_kitchen_small():
    """A small cooking fire: a pot on its tripod and a sack beside it."""
    g = prop_canvas("pantry_small")
    h = len(g)
    cook_fire(g, 28, h - 2)
    sack(g, 48, h - 18, 12, 16)
    chopping_block(g, 62, h - 13)
    union_outline(g)
    return g


def wheel(g, cx, cy, r):
    """A spoked cart wheel: its iron tyre, wooden felloe, spokes and hub."""
    oval(g, cx, cy, r, r, IRON_DK)
    oval(g, cx, cy, r - 1, r - 1, WOOD)
    oval(g, cx, cy, r - 2.5, r - 2.5, T)
    for ang in range(0, 360, 45):
        stroke(
            g,
            round(cx),
            round(cy),
            round(cx + (r - 1.5) * math.cos(math.radians(ang))),
            round(cy + (r - 1.5) * math.sin(math.radians(ang))),
            WOOD_SH,
        )
    oval(g, cx, cy, 1.6, 1.6, IRON)


def camp_cart():
    """A supply cart: its load lashed under a canvas cover, side boards,
    spoked wheels, the shafts resting on a stone."""
    g = prop_canvas("kitchen_island")
    w, h = len(g[0]), len(g)
    rect(g, 2, h - 10, 12, h - 8, WOOD_SH)  # the shafts, west
    rect(g, 1, h - 6, 6, h - 2, STONE)
    rect(g, 10, h - 16, w - 4, h - 8, WOOD)
    rect(g, 10, h - 16, w - 4, h - 15, WOOD_LT)
    for x in range(14, w - 4, 8):
        rect(g, x, h - 15, x + 1, h - 8, WOOD_SH)
    rect(g, 10, h - 9, w - 4, h - 8, WOOD_DK)
    oval(g, (w + 6) / 2, h - 16, (w - 18) / 2, 9, TENT)  # the covered load
    oval(g, (w + 6) / 2 + 6, h - 14, (w - 18) / 2 - 6, 6, TENT_SH, only={TENT})
    for x in (26, 44, 62):
        rect(g, x, h - 25, x + 1, h - 15, LEATHER)
    wheel(g, 24, h - 7, 6.5)
    wheel(g, w - 18, h - 7, 6.5)
    union_outline(g)
    return g


# The frame counts of the office's animated pieces, which a camp stand-in must
# match: the pack loader holds a density variant to its base's count.
OFFICE_FRAMES = {
    "vending_machine": 25,
    "printer": 9,
    "water_cooler": 5,
    "fish_tank": 18,
}


def busy_loop(piece, idle, busy):
    """An appliance's frames at the office's count: `idle` first, then `busy`
    round and round."""
    n = OFFICE_FRAMES[piece]
    return [idle] + [busy[i % len(busy)] for i in range(n - 1)]


def camp_stores():
    """Stores stacked by the fire: a barrel on a crate beside a second barrel;
    when someone helps themselves, the top barrel's lid lifts."""
    frames = []
    for lid in (0, 1, 2):
        g = prop_canvas("vending_machine")
        w, h = len(g[0]), len(g)
        plank_box(g, 1, h - 18, 17, h - 1)
        barrel(g, 17, h - 20, w - 1, h - 1)
        barrel(g, 3, h - 38 - lid, 16, h - 18)
        if lid:
            rect(g, 4, h - 37, 15, h - 36, SHADOW)
        plank_box(g, 16, h - 32, w - 2, h - 20)
        union_outline(g)
        frames.append(g)
    idle, ajar, open_ = frames
    return busy_loop("vending_machine", idle, [ajar, open_, open_, ajar])


def camp_anvil():
    """An anvil on its stump; at work, a bar glows on it and sparks fly."""
    sparks = (
        (),
        ((6, 8), (21, 6)),
        ((4, 5), (23, 9), (12, 3)),
        ((8, 2), (19, 4)),
        ((24, 6), (5, 9)),
    )
    frames = []
    for i, flying in enumerate(sparks):
        g = prop_canvas("printer")
        w, h = len(g[0]), len(g)
        rect(g, 7, h - 12, w - 7, h - 1, WOOD_SH)
        rect(g, 7, h - 12, 9, h - 1, WOOD)
        oval(g, w / 2, h - 12, 7, 2, WOOD_LT)
        rect(g, 9, h - 18, w - 9, h - 13, IRON_SH)  # the waist and feet
        rect(g, 12, h - 21, w - 12, h - 17, IRON_SH)
        rect(g, 4, h - 25, w - 6, h - 21, IRON)  # the face, its horn west
        rect(g, 4, h - 25, w - 6, h - 24, IRON_LT)
        rect(g, 1, h - 24, 5, h - 22, IRON)
        put(g, 0, h - 23, IRON_SH)
        rect(g, w - 6, h - 25, w - 4, h - 22, IRON_SH)
        if i:
            rect(g, 10, h - 26, 20, h - 25, VERMILION)
            rect(g, 12, h - 26, 17, h - 25, BULB)
        union_outline(g)
        for x, y in flying:
            put(g, x, y, BULB)
            put(g, x + 1, y + 1, GOLD)
        frames.append(g)
    return busy_loop("printer", frames[0], frames[1:])


# Where the light glints on the water barrel's surface, frame by frame.
CAMP_WATER_GLINTS = (4, 6, 8, 7, 5)


def camp_water_barrel():
    """A water barrel, its lid off, a ladle hung on its rim, light glinting on
    the water as it stirs."""
    require(
        len(CAMP_WATER_GLINTS) == OFFICE_FRAMES["water_cooler"],
        "the water barrel loops as many frames as the water cooler",
    )
    frames = []
    for glint in CAMP_WATER_GLINTS:
        g = prop_canvas("water_cooler")
        w, h = len(g[0]), len(g)
        barrel(g, 1, h - 22, w - 1, h - 1)
        oval(g, w / 2, h - 19.5, w / 2 - 2, 1.4, BARREL_WATER)
        put(g, glint, h - 20, BARREL_WATER_LT)
        rect(g, w - 5, h - 26, w - 4, h - 19, WOOD_DK)
        oval(g, w - 4, h - 26, 1.8, 1.4, IRON)
        union_outline(g)
        frames.append(g)
    return frames


def camp_armour_stand():
    """An armour stand: a cross of poles wearing a mail shirt under a
    breastplate, an open helm on top, a round shield leant at its foot."""
    g = prop_canvas("coat_rack")
    w, h = len(g[0]), len(g)
    rect(g, w // 2 - 1, 10, w // 2 + 1, h - 3, WOOD)
    rect(g, 4, h - 3, w - 4, h - 1, WOOD_SH)
    rect(g, 2, 15, w - 2, 17, WOOD_SH)
    rect(g, 4, 16, w - 4, 34, IRON_SH)  # the mail
    for y in range(18, 34, 2):
        for x in range(5 + (y // 2) % 2, w - 4, 2):
            put(g, x, y, IRON_DK)
    rect(g, 5, 16, w - 5, 27, IRON)  # the breastplate
    rect(g, 5, 16, 7, 27, IRON_LT)
    rect(g, w // 2, 17, w // 2 + 1, 26, IRON_SH)
    disc(g, w / 2, 7.5, 5, IRON)
    rect(g, w // 2 - 5, 9, w // 2 + 5, 11, IRON_DK)
    rect(g, w // 2 - 3, 8, w // 2 + 3, 9, SHADOW)
    put(g, w // 2 - 3, 4, IRON_LT)
    oval(g, w - 6, h - 10, 5, 7, WOOD)  # the shield
    oval(g, w - 6, h - 10, 2, 2, IRON)
    union_outline(g)
    return g


def camp_weapon_rack():
    """A weapon rack: two uprights and rails holding a spear, a sword, an axe
    and a bow."""
    g = prop_canvas("bookshelf")
    w, h = len(g[0]), len(g)
    for x in (2, w - 4):
        rect(g, x, 6, x + 2, h - 1, WOOD_SH)
        rect(g, x, 6, x + 1, h - 1, WOOD)
    rect(g, 1, 12, w - 1, 14, WOOD)
    rect(g, 1, h - 9, w - 1, h - 7, WOOD)
    rect(g, 7, 2, 9, h - 3, WOOD_DK)  # the spear
    rect(g, 6, 1, 10, 5, IRON_LT)
    put(g, 8, 0, IRON_LT)
    rect(g, 13, 6, 15, h - 10, IRON)  # the sword
    rect(g, 13, 6, 14, h - 10, IRON_LT)
    rect(g, 11, h - 10, 17, h - 9, GOLD)
    rect(g, 13, h - 9, 15, h - 3, LEATHER)
    rect(g, 20, 6, 22, h - 3, WOOD)  # the axe
    rect(g, 22, 6, 26, 14, IRON)
    rect(g, 25, 5, 27, 15, IRON_LT)
    stroke(g, 27, 18, 29, 26, WOOD_LT)  # the bow
    stroke(g, 29, 26, 27, 36, WOOD_LT)
    stroke(g, 27, 18, 27, 36, OFFWHITE_SH)
    union_outline(g)
    return g


def camp_provisions():
    """Provisions: sacks of grain heaped on a crate."""
    g = prop_canvas("snack_shelf")
    w, h = len(g[0]), len(g)
    plank_box(g, 1, h - 14, w - 1, h - 1)
    sack(g, 1, h - 30, 14, 18)
    sack(g, 12, h - 32, 14, 20)
    sack(g, 6, h - 40, 13, 14)
    union_outline(g)
    return g


def bush(g, clumps):
    """A bush: round clumps of leaves, each lit on its upper west."""
    for cx, cy, r in clumps:
        disc(g, cx, cy, r, LEAF_SH)
        disc(g, cx - r * 0.25, cy - r * 0.25, r * 0.7, LEAF)
        disc(g, cx - r * 0.45, cy - r * 0.45, r * 0.3, LEAF_HI)


def camp_bush():
    """A wild bush, a few red berries in it."""
    g = prop_canvas("plant")
    h = len(g)
    bush(g, ((8, h - 9, 6.5), (16, h - 10, 7), (12, h - 15, 6.5)))
    for x, y in ((7, h - 10), (15, h - 14), (18, h - 7)):
        put(g, x, y, RED)
    union_outline(g)
    return g


def camp_sapling():
    """A young pine: tiers of needles over a slim trunk."""
    g = prop_canvas("plant_tall")
    w, h = len(g[0]), len(g)
    rect(g, w // 2 - 1, h - 8, w // 2 + 1, h - 1, WOOD_SH)
    for top, reach in ((2, 5), (9, 7), (17, 9), (24, 10)):
        for y in range(top, top + 10):
            half = reach * (y - top) / 10
            rect(g, round(w / 2 - half), y, round(w / 2 + half) + 1, y + 1, LEAF_SH)
            if half > 1:
                rect(g, round(w / 2 - half), y, round(w / 2 - half / 3), y + 1, LEAF)
    union_outline(g)
    return g


def camp_fern():
    """A fern: fronds arching out from its root."""
    g = prop_canvas("plant_flower")
    w, h = len(g[0]), len(g)
    for tip, k in (
        ((2, 10), LEAF_SH),
        ((21, 9), LEAF_SH),
        ((7, 3), LEAF),
        ((16, 2), LEAF),
        ((12, 5), LEAF_HI),
    ):
        stroke(g, w // 2, h - 2, tip[0], tip[1], k)
        stroke(g, w // 2 + 1, h - 2, tip[0] + 1, tip[1], k)
        for i in range(1, 6):  # its leaflets
            x = round(w / 2 + (tip[0] - w / 2) * i / 6)
            y = round(h - 2 + (tip[1] - h + 2) * i / 6)
            put(g, x - 1, y, k)
            put(g, x + 2, y, k)
    union_outline(g)
    return g


def camp_rocks():
    """A cluster of rocks, moss on their tops."""
    g = prop_canvas("plant_succulent")
    h = len(g)
    for cx, cy, rx, ry in (
        (6, h - 5, 5.5, 4.5),
        (14, h - 4, 5, 3.5),
        (10, h - 9, 4, 3.5),
    ):
        oval(g, cx, cy, rx, ry, STONE)
        oval(g, cx - 1, cy - 1, rx - 1.5, ry - 1.5, STONE_LT, only={STONE})
        oval(g, cx + 1.5, cy + 1, rx - 1.5, ry - 1.8, STONE_SH, only={STONE, STONE_LT})
    for x in (8, 9, 10, 11):
        put(g, x, h - 12, LEAF)
    union_outline(g)
    return g


def camp_sconce():
    """A lantern hung from an iron bracket on the palisade."""
    g = prop_canvas("exit_sign")
    rect(g, 2, 2, 14, 3, IRON_DK)
    rect(g, 2, 2, 3, 6, IRON_DK)
    put(g, 13, 4, IRON_DK)
    rect(g, 11, 5, 17, 6, IRON_DK)
    rect(g, 11, 6, 17, 10, BULB)
    rect(g, 11, 6, 12, 10, IRON_SH)
    rect(g, 16, 6, 17, 10, IRON_SH)
    rect(g, 11, 10, 17, 11, IRON_DK)
    union_outline(g)
    return g


def camp_hanging_lantern():
    """A big lantern hung on a hook in the palisade, its glass glowing.
    The engine draws a clock's hands as long as the face key reaches out from
    the centre along the middle row; a lone face-key pixel at the centre gives
    them no length, so none are drawn."""
    g = prop_canvas("wall_clock")
    w, h = len(g[0]), len(g)
    put(g, w // 2, 0, IRON_DK)
    rect(g, w // 2 - 1, 1, w // 2 + 1, 4, IRON_DK)
    rect(g, 8, 4, w - 8, 7, IRON)
    rect(g, 6, 7, w - 6, 9, IRON_DK)
    rect(g, 7, 9, w - 7, h - 5, BULB)
    for x in (7, w // 2 - 1, w - 9):
        rect(g, x, 9, x + 2, h - 5, IRON_SH)
    rect(g, 6, h - 5, w - 6, h - 2, IRON_DK)
    rect(g, 9, h - 2, w - 9, h, IRON)
    put(g, w // 2, h // 2, CLOCK_FACE)
    union_outline(g)
    return g


def camp_bucket():
    """A wooden bucket bound in iron, its rope handle up."""
    g = prop_canvas("pantry_bin")
    w, h = len(g[0]), len(g)
    barrel(g, 2, h - 13, w - 2, h - 1)
    oval(g, w / 2, h - 10.5, w / 2 - 4, 1.2, BARREL_WATER)
    stroke(g, 3, h - 11, 6, h - 18, LEATHER)
    stroke(g, 6, h - 18, 10, h - 18, LEATHER)
    stroke(g, 10, h - 18, 13, h - 11, LEATHER)
    union_outline(g)
    return g


def camp_woodpile():
    """A woodpile: split logs stacked with their sawn ends out, an axe in
    the chopping block beside it."""
    g = prop_canvas("fish_tank")
    h = len(g)
    rect(g, 4, h - 22, 38, h - 2, WOOD_DK)
    for row in range(4):
        for i in range(5 - (row % 2)):
            cx = 7.5 + i * 7 + (row % 2) * 3.5
            cy = h - 5.5 - row * 6
            oval(g, cx, cy, 3.4, 3.0, WOOD_LT)
            oval(g, cx, cy, 1.8, 1.5, WOOD_HI)
            put(g, round(cx), round(cy), WOOD)
    chopping_block(g, 42, h - 14)
    union_outline(g)
    # the office's tank loops its frames; the pile holds still through them
    return [g] * OFFICE_FRAMES["fish_tank"]


def camp_trestle():
    """A plank table on trestles, a candle stub and a bowl on it."""
    g = prop_canvas("meeting_table")
    w, h = len(g[0]), len(g)
    rect(g, 2, 3, w - 2, 11, WOOD_LT)
    for y in (5, 8):
        rect(g, 2, y, w - 2, y + 1, WOOD)
    rect(g, 2, 11, w - 2, 13, WOOD_SH)
    for x in (6, w - 9):
        stroke(g, x, 13, x - 2, h - 1, WOOD_DK)
        stroke(g, x + 2, 13, x + 4, h - 1, WOOD_DK)
    rect(g, 10, 2, 12, 5, OFFWHITE)
    put(g, 11, 1, BULB)
    oval(g, 30, 6, 3.5, 1.8, WOOD_DK)
    oval(g, 30, 5.6, 2.5, 1.0, BROWN)
    union_outline(g)
    return g


def camp_map_table():
    """A scout's map table on crossed legs: a map unrolled across it, weighted
    by a stone, a candle burning at its corner."""
    g = prop_canvas("standing_desk")
    w, h = len(g[0]), len(g)
    for x in (6, w - 9):
        stroke(g, x, 14, x + 4, h - 1, WOOD_DK)
        stroke(g, x + 4, 14, x, h - 1, WOOD_SH)
    rect(g, 2, 7, w - 2, 13, WOOD_LT)
    rect(g, 2, 12, w - 2, 15, WOOD_SH)
    rect(g, 5, 6, w - 8, 12, PARCHMENT)
    rect(g, 5, 11, w - 8, 12, PARCHMENT_SH)
    for x, y in ((8, 9), (11, 8), (14, 9), (17, 8)):
        put(g, x, y, PARCHMENT_INK)
    put(g, 19, 9, RED)
    rect(g, 6, 5, 9, 7, STONE)
    rect(g, w - 6, 4, w - 4, 8, OFFWHITE)
    put(g, w - 5, 3, BULB)
    union_outline(g)
    return g


def camp_stool():
    """A short log for a seat, its sawn top lit and ringed."""
    g = prop_canvas("meeting_chair")
    w, h = len(g[0]), len(g)
    rect(g, 6, 10, w - 6, h - 3, WOOD_SH)
    rect(g, 6, 10, 8, h - 3, WOOD)
    rect(g, w - 8, 10, w - 6, h - 3, WOOD_DK)
    oval(g, w / 2, 10, 8, 4, WOOD_LT)
    oval(g, w / 2, 10, 5, 2.4, WOOD_HI)
    oval(g, w / 2, 10, 2, 1, WOOD)
    union_outline(g)
    return g


def camp_tin_cup():
    """A dented tin cup."""
    g = prop_canvas("desk_cup")
    rect(g, 1, 2, 6, 7, IRON)
    rect(g, 1, 2, 6, 3, IRON_LT)
    rect(g, 4, 3, 6, 7, IRON_SH)
    rect(g, 6, 3, 7, 6, IRON_SH)
    union_outline(g)
    return g


def camp_loot():
    """A sitter's takings: a heap of coins, a frame per tier of the office's
    tower and on its canvas, taller with each."""
    frames = []
    for tier in range(1, TOKEN_MAX_TIER + 1):
        h = tier * TOKEN_REAM_ROWS
        g = canvas((TOKEN_W_1X + 1) * S, h)
        w = len(g[0])
        layers = (h - 2) // 2
        for i in range(layers):
            y = h - 3 - 2 * i
            half = round(6 - 4 * i / max(1, layers - 1))
            rect(g, w // 2 - half, y, w // 2 + half, y + 2, COIN)
            rect(g, w // 2 - half, y + 1, w // 2 + half, y + 2, COIN_SH)
        put(g, w // 2 - 1, h - 2 * layers - 1, WHITE)
        union_outline(g)
        frames.append(g)
    return frames


def camp_coin():
    """A coin, falling."""
    g = prop_canvas("token_sheet")
    rect(g, 4, 0, 8, 4, COIN)
    rect(g, 5, 1, 7, 3, COIN_SH)
    return g


# Where each camp desk stands the sitter's cup and tower: on the bedroll, by
# its pillow and by its pack.
CAMP_DESK_MARKS = {
    "desk": (("cup", 20, 31), ("tower", 32, 31)),
    "desk_north": (("cup", 36, 40), ("tower", 24, 40)),
}
# Each sleeper's crown mark, where the head is drawn and the hairstyle dresses.
CAMP_HEADS = {
    "seated_sleeping": ("crown", 16, 12),
    "seated_sleeping_alt": ("crown", 17, 13),
}
# The office piece each camp drawing stands in for: its drawing, and whether
# that draws every frame (else one).
CAMP = {
    "desk": (camp_desk, False),
    "desk_north": (camp_desk_north, False),
    "desk_front": (camp_desk_front, False),
    "desk_chair": (camp_desk_chair, False),
    "seated_sleeping": (camp_sleeper, False),
    "seated_sleeping_alt": (camp_sleeper_alt, False),
    "side_table": (camp_fire, True),
    "floor_lamp": (camp_torch, False),
    "meeting_sofa": (camp_log, False),
    "meeting_sofa_north": (camp_log_north, False),
    "phone_booth": (camp_tent, False),
    "door": (camp_gate, True),
    "filing_cabinet": (camp_crates, False),
    "whiteboard": (camp_quest_board, False),
    "bulletin_board": (camp_hide_map, False),
    "notice_board": (camp_notices, False),
    "meeting_screen": (camp_standard, False),
    "tv_stand": (camp_pennant, False),
    "pantry": (camp_kitchen, False),
    "pantry_small": (camp_kitchen_small, False),
    "kitchen_island": (camp_cart, False),
    "vending_machine": (camp_stores, True),
    "printer": (camp_anvil, True),
    "water_cooler": (camp_water_barrel, True),
    "coat_rack": (camp_armour_stand, False),
    "bookshelf": (camp_weapon_rack, False),
    "snack_shelf": (camp_provisions, False),
    "plant": (camp_bush, False),
    "plant_tall": (camp_sapling, False),
    "plant_flower": (camp_fern, False),
    "plant_succulent": (camp_rocks, False),
    "exit_sign": (camp_sconce, False),
    "wall_clock": (camp_hanging_lantern, False),
    "pantry_bin": (camp_bucket, False),
    "fish_tank": (camp_woodpile, True),
    "meeting_table": (camp_trestle, False),
    "meeting_chair": (camp_stool, False),
    "desk_cup": (camp_tin_cup, False),
    "token_tower": (camp_loot, True),
    "token_sheet": (camp_coin, False),
    "standing_desk": (camp_map_table, False),
}


# ---- output -----------------------------------------------------------------
# ---- the dungeon: the campaign's floors below the camp -------------------------
# Stand-ins drawn on the office pieces' own canvases, so the layout, its
# footprints and its reachability never see the dungeon: `dungeon.toml`
# registers each `dungeon_<piece>` over the piece it replaces on a dungeon
# floor, and the office's 1x art stays its base.
DUNGEON = "dungeon_"
# Rough stone, a monster's hide, a spider's chitin, bone and a torch's flame:
# one base each in [palette], the rest their [ramps].
ROCK, ROCK_LT, ROCK_HI, ROCK_SH, ROCK_DK = "ɢ", "ɣ", "ɦ", "ɧ", "ɨ"
HIDE, HIDE_LT, HIDE_SH, HIDE_DK = "ɐ", "ɑ", "ɒ", "ɓ"
CHITIN, CHITIN_LT, CHITIN_HI, CHITIN_SH = "ɔ", "ɕ", "ɖ", "ɗ"
BONE, BONE_SH, BONE_DK = "ɘ", "ə", "ɚ"
TORCH_FLAME, TORCH_TIP = "ɛ", "ɜ"


def boulder(g, cx, cy, rx, ry, seed):
    """A rough boulder: its edge broken by a seeded wobble, lit on its upper
    west, shaded east and along its foot, one dark crack."""
    rng = Draws(seed)
    phase = rng.random() * math.tau
    rock = set()
    for y in range(len(g)):
        for x in range(1, len(g[0]) - 1):
            nx, ny = (x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry
            ang = math.atan2(ny, nx)
            edge = 1.0 + 0.12 * math.sin(3 * ang + phase) + 0.07 * math.sin(7 * ang)
            if nx * nx + ny * ny <= edge * edge:
                lit = -(0.62 * nx + 0.78 * ny)
                g[y][x] = (
                    ROCK_HI
                    if lit > 0.62
                    else ROCK_LT
                    if lit > 0.25
                    else ROCK
                    if lit > -0.4
                    else ROCK_SH
                )
                rock.add((x, y))
    sx = int(cx + rx * 0.4 * (rng.random() - 0.5))
    sy = int(cy - ry * 0.2)
    for i in range(4):
        x, y = sx + i // 2, sy + i
        if (x, y) in rock:
            g[y][x] = ROCK_DK
    return rock


def torch(g, x, top, foot):
    """A torch stood in the rock at column `x`: a wooden haft from `foot` up
    to its cloth-wound head at `top`, and on it the flame, its core in the
    lamp's bulb key so the light pools round it."""
    rect(g, x, top, x + 2, foot, WOOD_SH)
    rect(g, x, top, x + 1, foot, WOOD)
    rect(g, x - 1, top, x + 3, top + 2, LEATHER)
    rect(g, x - 1, top + 1, x + 3, top + 2, LEATHER_SH)
    flame = master("""
        ..o..
        .ɛo..
        .ɛɛo.
        ɛɛ9ɛ.
        ɛ99ɛɛ
        ɛ999ɛ
        .ɛ9ɛ.
    """)
    for fy, row in enumerate(flame):
        for fx, k in enumerate(row):
            if k != T:
                put(
                    g,
                    x - 1 + fx,
                    top - len(flame) + fy,
                    TORCH_TIP if k == VERMILION else k,
                )


def bones(g, x, y, flip=False):
    """A bone lying on the floor at (x, y), its knuckled ends, and beside it
    a small skull."""
    d = -1 if flip else 1
    rect(g, min(x, x + 6 * d), y, max(x, x + 6 * d) + 1, y + 1, BONE)
    for ex in (x, x + 6 * d):
        rect(g, ex - 1, y - 1, ex + 1, y + 2, BONE)
        put(g, ex - 1, y + 1, BONE_SH)
    sx = x + 9 * d
    rect(g, sx - 2, y - 2, sx + 2, y + 2, BONE)
    rect(g, sx - 1, y + 2, sx + 1, y + 3, BONE_SH)
    put(g, sx - 1, y - 1, ROCK_DK)
    put(g, sx + 1 - (d < 0), y - 1, ROCK_DK)


def spider_leg(g, hip, knee, foot):
    """A spider's leg: a thick segment rising from the body to the knee, a
    thinner one down to the floor, its knee catching the light."""
    stem(g, [hip, knee], 1.4, CHITIN)
    stem(g, [hip, knee], 0.5, CHITIN_LT)
    stem(g, [knee, foot], 1.0, CHITIN)
    kx, ky = knee
    put(g, int(kx), int(ky) - 1, CHITIN_HI)


def lit_ball(g, keys, cx, cy, rx, ry):
    """The `keys[0]` pixels inside the ellipse at (cx, cy) shaded as a ball
    lit from the upper west: `keys` is (base, lit, highlight, shade)."""
    base, lit, hi, shade = keys
    for y in range(len(g)):
        for x in range(len(g[0])):
            if g[y][x] != base:
                continue
            nx, ny = (x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry
            if (nx + 0.4) ** 2 + (ny + 0.45) ** 2 < 0.1:
                g[y][x] = hi
            elif (nx + 0.3) ** 2 + (ny + 0.35) ** 2 < 0.38:
                g[y][x] = lit
            elif nx * nx + ny * ny > 0.6 and (nx > 0.15 or ny > 0.3):
                g[y][x] = shade


CHITIN_KEYS = (CHITIN, CHITIN_LT, CHITIN_HI, CHITIN_SH)
HIDE_KEYS = (HIDE, HIDE_LT, HIDE_LT, HIDE_SH)


def spider_eyes(g, cx, top):
    """The spider's eyes, in the desk's screen keys so its foe's tool lights
    them: a big pair in the middle, each with a glint, and three smaller ones
    either side."""
    for side in (-1, 1):
        x0 = int(cx) + (1 if side > 0 else -4)
        rect(g, x0, top, x0 + 3, top + 3, GLASS)
        put(g, x0 + (0 if side < 0 else 1), top, GLASS_TXT)
        put(g, x0 + (1 if side < 0 else 2), top, GLASS_TXT)
        for dx, dy, size in ((5, -1, 2), (8, 1, 2), (6, 3, 1)):
            ex = int(cx) + side * dx - (size if side < 0 else 0)
            rect(g, ex, top + dy, ex + size, top + dy + size, GLASS)
            put(g, ex, top + dy, GLASS_TXT)


def lair_north():
    """The north seat's lair, beyond its back-turned occupant: a giant spider
    facing them and the viewer, its eyes over their head and its legs arched
    out either side, between a boulder heaped with loot west and one with a
    torch and the potion east."""
    lift = DESK_NORTH_LIFT
    w, h = DESK_ART_W * S, desk_rows(lift)[3] * S
    g = canvas(w, h)
    for side in (-1, 1):
        for hip, knee, foot in (
            ((21, 5), (9, 1), (2, 26)),
            ((20, 7), (5, 6), (1, 36)),
            ((20, 9), (7, 14), (5, 43)),
            ((21, 11), (12, 20), (12, 43)),
        ):
            m = (lambda p: p) if side < 0 else (lambda p: (w - 1 - p[0], p[1]))
            spider_leg(g, m(hip), m(knee), m(foot))
    boulder(g, 6.0, 35.0, 6.5, 9.5, 21)
    boulder(g, 48.0, 38.0, 7.5, 6.5, 22)
    ellipse(g, 28.0, 7.0, 10.0, 7.0, CHITIN)  # the head
    lit_ball(g, CHITIN_KEYS, 28.0, 7.0, 10.0, 7.0)
    for side in (-1, 1):  # the fangs, folded under the head
        x = 28 + side * 3 - (side < 0)
        rect(g, x, 12, x + 1, 16, CHITIN_SH)
        put(g, x, 16, BONE)
    spider_eyes(g, 28.0, 1)
    torch(g, lamp_base_x("desk_north") - 2, 26, 34)
    bones(g, 22, 42)
    union_outline(g)
    return g


# The orc's back: its sigil's centre, glowing between its shoulder blades.
ORC_SIGIL = (28, 20)


def orc_back(g):
    """An orc seen from behind, facing its foe: the back of its head with a
    dark topknot, ears swept out, a hunched back over a broad belt, its legs
    planted, a crude axe hanging from its east fist, and between its
    shoulder blades a sigil in the desk's screen keys, which its foe's tool
    lights."""
    ellipse(g, 28.0, 23.0, 14.0, 9.0, HIDE)  # the back
    ellipse(g, 28.0, 17.0, 16.5, 5.5, HIDE)  # the shoulders
    for x0 in (19, 31):  # the legs, under the belt
        rect(g, x0, 30, x0 + 6, 35, HIDE_SH)
        rect(g, x0 - 1, 34, x0 + 7, 36, WOOD_DK)
    for sx, hx, hy in ((13, 10, 27), (43, 46, 26)):  # the arms
        stem(g, [(sx, 17), (hx + 2, hy)], 3.0, HIDE)
        rect(g, hx, hy, hx + 5, hy + 4, HIDE_SH)
    lit_ball(g, HIDE_KEYS, 28.0, 20.0, 17.0, 13.0)
    head = canvas(len(g[0]), len(g))  # the back of the head, over a creased nape
    ellipse(head, 28.0, 8.0, 6.0, 6.0, HIDE)
    for side in (-1, 1):  # the ears, swept up and out
        for i in range(6):
            x = 28 + side * (5 + i) - (side < 0)
            put(head, x, 7 - i // 2, HIDE)
            put(head, x, 8 - i // 2, HIDE_SH)
    lit_ball(head, HIDE_KEYS, 28.0, 8.0, 6.0, 6.0)
    paste(g, head)
    ellipse(g, 28.0, 2.0, 3.2, 2.2, WOOD_DK)  # the topknot
    rect(g, 26, 3, 30, 4, LEATHER)
    rect(g, 14, 28, 42, 31, LEATHER)  # the belt
    rect(g, 14, 30, 42, 31, LEATHER_SH)
    stem(g, [(18, 12), (37, 28)], 0.9, LEATHER)  # the harness strap
    for sx, sy in ((21, 15), (34, 25)):
        put(g, sx, sy, IRON_LT)
    rect(g, 47, 24, 49, 34, WOOD_SH)  # the axe's haft, and its head
    rect(g, 49, 28, 54, 34, IRON)
    rect(g, 49, 28, 54, 29, IRON_LT)
    put(g, 53, 33, IRON_SH)
    rect(g, 22, 13, 34, 14, HIDE_DK)  # the nape's crease under the skull
    sx, sy = ORC_SIGIL  # the sigil: a lozenge pierced by a stroke
    for dy in range(-4, 5):
        half = 3 - abs(dy) * 3 // 4
        put(g, sx - half, sy + dy, GLASS_TXT)
        put(g, sx + half, sy + dy, GLASS_TXT)
        if half > 1:
            rect(g, sx - half + 1, sy + dy, sx + half, sy + dy + 1, GLASS)
    rect(g, sx, sy - 6, sx + 1, sy + 7, GLASS_TXT)


def lair_south():
    """The south seat's lair, as the seat faces it: an orc from behind,
    squaring up to its occupant between two boulders, a torch burning on the
    west one; the occupant's potion and loot stand where the desk's
    arrangement marks them."""
    w, h = DESK_ART_W * S, desk_rows(0)[3] * S
    g = canvas(w, h)
    boulder(g, 6.0, 25.0, 6.5, 11.5, 11)
    boulder(g, 50.0, 27.0, 6.5, 9.5, 12)
    orc_back(g)
    torch(g, lamp_base_x("desk"), 9, 16)
    union_outline(g)
    return g


def lair_south_front():
    """The south lair's front: the orc, which stands before whatever of its
    occupant's props it overlaps."""
    return front_layer(lair_south(), orc_back)


# ---- the dungeon's props, chair and stairs --------------------------------------
def potion():
    """The occupant's potion at the cup's mark: a round-bellied flask of red
    draught, its glass in the cup's keys, stoppered with a cork."""
    g = canvas(2 * S, 2 * S)
    ellipse(g, 4.0, 5.0, 3.0, 2.6, MUG)
    rect(g, 3, 1, 5, 3, MUG)
    rect(g, 3, 0, 5, 1, WOOD_LT)
    for y in range(4, 8):
        for x in range(1, 7):
            if g[y][x] == MUG:
                g[y][x] = RED if x < 5 else DARK_RED
    put(g, 2, 4, WHITE)
    put(g, 5, 3, MUG_SH)
    union_outline(g)
    return g


def coin_heap(g, cx, foot, half, rows, seed):
    """A heap of coins `half` wide either side of `cx` and `rows` tall on
    `foot`: gold, shaded east, its coins' rims catching the light in the
    paper's keys in staggered rows, a gem or two."""
    rng = Draws(seed)
    for y in range(foot - rows, foot):
        reach = half * math.sqrt(max(0.0, 1 - ((foot - y) / rows) ** 2))
        x0, x1 = int(cx - reach), math.ceil(cx + reach)
        for x in range(x0, x1):
            rim = (y - foot) % 3 == 0 and (x + (y // 3) * 2) % 4 == 0
            if x < cx + reach * 0.45:
                put(g, x, y, OFFWHITE if rim else GOLD)
            else:
                put(g, x, y, OFFWHITE_SH if rim or x == x1 - 1 else GOLD)
    for _ in range(2):
        put(g, int(cx) + rng.randrange(-2, 3), foot - rng.randrange(2, rows), RED)


def loot_pile():
    """The token meter's loot, a frame per tier: a heap of coins growing with
    each tier, the full heap's top coin teetering east."""
    frames = []
    for tier in range(1, TOKEN_MAX_TIER + 1):
        h = tier * TOKEN_REAM_ROWS
        g = canvas((TOKEN_W_1X + 1) * S, h)
        coin_heap(g, 7.0, h - 1, 3.0 + 2 * tier, h - 2, 40 + tier)
        if tier == TOKEN_MAX_TIER:
            rect(g, 7 + TOKEN_TEETER, 1, 11 + TOKEN_TEETER, 2, OFFWHITE)
            rect(g, 7 + TOKEN_TEETER, 2, 11 + TOKEN_TEETER, 3, GOLD)
        union_outline(g)
        frames.append(g)
    return frames


def falling_coin():
    """The coin falling onto the loot heap."""
    g = canvas(TOKEN_W + 2, 4)
    rect(g, 4, 1, 8, 2, OFFWHITE)
    rect(g, 4, 2, 8, 3, GOLD)
    union_outline(g)
    return g


def dropped_shield():
    """A round wooden shield set down on its rim where the office's chair
    stood: planks inside an iron rim, a boss at its middle."""
    g = canvas(FIG_W, 5 * S)
    ellipse(g, FIG_CX, 11.0, 11.0, 8.5, IRON_SH)
    ellipse(g, FIG_CX, 11.0, 9.5, 7.2, WOOD)
    for x in range(8, 25, 4):
        rect(g, x, 3, x + 1, 19, WOOD_SH)
    for y in range(len(g)):
        for x in range(len(g[0])):
            if g[y][x] == WOOD and x < 12 and y < 9:
                g[y][x] = WOOD_LT
    ellipse(g, FIG_CX, 11.0, 2.6, 2.2, IRON)
    put(g, 15, 10, IRON_HI)
    rect(g, 6, 19, 26, 20, SHADOW)
    union_outline(g)
    return g


# The stair archway's steps, from the threshold down into the dark.
STAIR_STEPS = 5


def stair_arch():
    """The stairs down, in the elevator's place: a stone archway over steps
    sinking into the dark, behind an iron portcullis: down, half raised, and
    up, by the same entry progress that opened the doors; a torch burns
    either side, its flame in the bulb key as the lift car's light was."""
    w, h = DOOR_W * S, DOOR_H * S
    frames = []
    for gap in DOOR_GAPS:
        g = canvas(w, h)
        rect(g, 1, 1, w - 1, h - 1, ROCK)
        for y in range(1, h - 1, 6):  # the coursed blocks
            rect(g, 1, y, w - 1, y + 1, ROCK_SH)
            off = 4 if (y // 6) % 2 else 10
            for x in range(off, w - 1, 12):
                rect(g, x, y, x + 1, y + 6, ROCK_SH)
        rect(g, 1, 1, w - 1, 2, ROCK_LT)
        rect(g, 1, 1, 2, h - 1, ROCK_LT)
        x0, x1, top, foot = 10, w - 10, 14, h - 2
        mid = (x0 + x1) / 2
        for y in range(top - 10, foot):  # the arch's opening
            for x in range(x0, x1):
                if (
                    y >= top
                    or ((x + 0.5 - mid) / ((x1 - x0) / 2)) ** 2
                    + ((y + 0.5 - top) / 10) ** 2
                    <= 1
                ):
                    g[y][x] = SHADOW
        step_h = (foot - top) // STAIR_STEPS
        for i in range(STAIR_STEPS):  # from the threshold down: narrower, darker
            y = foot - (i + 1) * step_h
            inset = i * 2
            tread, riser = (
                (ROCK_HI, ROCK_SH),
                (ROCK_LT, ROCK_DK),
                (ROCK, ROCK_DK),
                (ROCK_SH, SHADOW),
                (ROCK_DK, SHADOW),
            )[i]
            rect(g, x0 + inset, y, x1 - inset, y + 3, tread)
            rect(g, x0 + inset, y + 3, x1 - inset, y + step_h, riser)
        for side in (-1, 1):  # the voussoirs round the arch
            for t in range(9):
                a = math.pi * (0.5 + side * t / 16)
                vx = mid + math.cos(a) * ((x1 - x0) / 2 + 2)
                vy = top - math.sin(a) * 12
                put(g, int(vx), int(vy), ROCK_HI)
        rect(g, x0 - 2, top, x0, foot, ROCK_LT)
        rect(g, x1, top, x1 + 2, foot, ROCK_SH)
        raised = gap * (foot - top + 10) // DOOR_GAPS[-1]
        bottom = foot - raised

        for x in range(x0, x1, 4):  # the portcullis, its bars spiked at the foot
            for y in range(top - 10, bottom):
                if y >= top or g[y][x] == SHADOW:  # inside the arch
                    g[y][x] = IRON_SH
            put(g, x, bottom, IRON_DK)
        for y in range(top - 6, bottom, 6):  # its cross bars, lit where they cross
            for x in range(x0, x1):
                if y >= top or g[y][x] == SHADOW:  # inside the arch
                    g[y][x] = IRON if g[y][x] == IRON_SH else IRON_SH
        rect(g, 1, foot, w - 1, foot + 1, ROCK_LT)  # the threshold
        for tx in (4, w - 7):  # a torch either side, lighting the way down
            torch(g, tx, 22, 30)
        union_outline(g)
        frames.append(g)
    return frames


# ---- the dungeon's furnishings, on the office fixtures' canvases ------------------
def cask():
    """A cask where the office's filing cabinet stood: wooden staves bellied
    between iron hoops, its lid catching the light."""
    w, h = 4 * S, 6 * S
    g = canvas(w, h)
    for y in range(2, h - 1):
        bulge = 1 if 6 <= y <= 17 else 0
        rect(g, 2 - bulge, y, w - 2 + bulge, y + 1, WOOD)
    for x in (5, 9, 12):
        rect(g, x, 3, x + 1, h - 1, WOOD_SH)
    for y in range(2, h - 1):
        put(g, 2 - (1 if 6 <= y <= 17 else 0), y, WOOD_LT)
    for hy in (4, 11, 19):
        rect(g, 1, hy, w - 1, hy + 2, IRON_SH)
        rect(g, 1, hy, w - 1, hy + 1, IRON)
    rect(g, 2, 1, w - 2, 3, WOOD_LT)
    rect(g, 3, 1, w - 3, 2, WOOD_HI)
    union_outline(g)
    return g


def mushrooms():
    """A cluster of pale cave mushrooms in place of the bushy pot plant: three
    pale caps on bone-white stems, a stone at their foot."""
    g = canvas(6 * S, 7 * S)
    boulder(g, 12.0, 24.0, 9.0, 3.5, 31)
    for cx, top, r, stem_h in ((8, 9, 5.0, 9), (16, 3, 6.0, 13), (19, 15, 3.5, 6)):
        rect(g, cx - 1, top + 3, cx + 1, top + 3 + stem_h, BONE)
        put(g, cx, top + 3 + stem_h - 1, BONE_SH)
        ellipse(g, cx, top + 2.5, r, r * 0.55, CYAN)
        rect(g, int(cx - r) + 1, top + 3, int(cx + r), top + 4, BLUE)
        put(g, cx - 2, top + 1, WHITE)
    union_outline(g)
    return g


def stalagmite():
    """A stalagmite in place of the tall pot plant: a tapering spire of rock
    rising from a heap of rubble, a shorter one leaning on it."""
    g = canvas(6 * S, 10 * S)
    for cx, top, half in ((10.5, 1, 7.0), (17.5, 16, 5.0)):
        for y in range(top, 38):
            reach = half * ((y - top) / (38 - top)) ** 0.8 + 0.5
            for x in range(int(cx - reach), math.ceil(cx + reach)):
                put(
                    g,
                    x,
                    y,
                    ROCK_LT
                    if x < cx - reach / 3
                    else ROCK
                    if x < cx + reach / 3
                    else ROCK_SH,
                )
        for y in range(top + 4, 36, 6):
            put(g, int(cx), y, ROCK_DK)
    boulder(g, 12.0, 37.0, 11.0, 3.0, 32)
    union_outline(g)
    return g


def skull(g, x, y):
    """A skull facing the viewer, its top-left at (x, y): a dome over two
    dark sockets, a nose notch and its teeth."""
    rect(g, x + 1, y, x + 6, y + 1, BONE)
    rect(g, x, y + 1, x + 7, y + 5, BONE)
    rect(g, x + 1, y + 5, x + 6, y + 7, BONE_SH)
    rect(g, x + 1, y + 2, x + 3, y + 4, ROCK_DK)
    rect(g, x + 4, y + 2, x + 6, y + 4, ROCK_DK)
    put(g, x + 3, y + 4, BONE_DK)
    for tx in (x + 2, x + 4):
        put(g, tx, y + 6, BONE_DK)
    put(g, x + 1, y + 1, WHITE)


def bone_pile():
    """A heap of bones crowned with a skull, in place of the flowering pot."""
    g = canvas(6 * S, 6 * S)
    rng = Draws(33)
    for _ in range(9):
        y = rng.randrange(13, 22)
        x = rng.randrange(3, 15)
        ln = rng.randrange(4, 8)
        rect(g, x, y, x + ln, y + 1, BONE)
        rect(g, x, y + 1, x + ln, y + 2, BONE_SH)
        for ex in (x, x + ln - 1):
            put(g, ex, y - 1, BONE)
            put(g, ex, y + 2, BONE_SH)
    boulder(g, 12.0, 22.0, 10.0, 2.0, 34)
    skull(g, 8, 6)
    union_outline(g)
    return g


def rubble():
    """Two stones and a skull in place of the small succulent."""
    g = canvas(5 * S, 4 * S)
    boulder(g, 6.0, 11.0, 5.0, 4.0, 35)
    boulder(g, 14.5, 12.5, 4.0, 2.5, 36)
    skull(g, 9, 3)
    union_outline(g)
    return g


def wall_torch():
    """A torch in an iron sconce on the wall, in place of the exit sign: its
    flame's core in the lit sign's key, so it burns at any hour."""
    g = canvas(5 * S, 3 * S)
    rect(g, 8, 8, 12, 11, IRON_SH)  # the bracket
    rect(g, 8, 8, 12, 9, IRON)
    rect(g, 9, 5, 11, 9, WOOD_SH)
    rect(g, 9, 5, 10, 9, WOOD)
    for fx, fy, k in (
        (9, 0, TORCH_TIP),
        (8, 1, TORCH_FLAME),
        (9, 1, TORCH_FLAME),
        (10, 1, TORCH_TIP),
        (8, 2, TORCH_FLAME),
        (9, 2, BULB),
        (10, 2, TORCH_FLAME),
        (11, 2, TORCH_FLAME),
        (8, 3, TORCH_FLAME),
        (9, 3, BULB),
        (10, 3, BULB),
        (11, 3, TORCH_FLAME),
        (8, 4, TORCH_FLAME),
        (9, 4, BULB),
        (10, 4, TORCH_FLAME),
    ):
        put(g, fx, fy, k)
    union_outline(g)
    return g


# The brazier's flames per frame, as each tongue's height: the first frame
# its embers at rest, then its busy loop flickering.
BRAZIER_FLAMES = [
    None,
    (5, 9, 6),
    (7, 11, 5),
    (6, 8, 8),
    (8, 12, 6),
    (5, 10, 7),
    (7, 9, 9),
    (6, 12, 5),
    (8, 10, 7),
]


def brazier():
    """A brazier in the printer's place: an iron bowl of coals on three legs,
    embers glowing at rest and, while in use, flames flickering up from it,
    their hearts in the bulb key."""
    require(
        len(BRAZIER_FLAMES) == PRINT_STEPS + 1, "the brazier fills the printer's frames"
    )
    frames = []
    for flames in BRAZIER_FLAMES:
        g = canvas(7 * S, 8 * S)
        for x0, x1 in ((7, 4), (14, 14), (21, 24)):  # the legs
            stem(g, [(x0, 20), (x1, 31)], 0.8, IRON_SH)
        for y in range(14, 21):  # the bowl
            half = 11 - (y - 14) * 0.9
            rect(
                g, int(14 - half), y, int(14 + half), y + 1, IRON if y < 16 else IRON_SH
            )
        rect(g, 3, 14, 25, 15, IRON_LT)
        rect(g, 4, 12, 24, 14, DARK_RED)  # the coals
        for x in range(5, 23, 3):
            put(g, x, 12, VERMILION)
            put(g, x + 1, 13, BULB if flames else VERMILION)
        if flames:
            for cx, height in zip((9, 14, 19), flames):
                for i in range(height):
                    half = max(0, (height - i) // 3)
                    k = (
                        BULB
                        if i < height // 2
                        else TORCH_FLAME
                        if i < height - 1
                        else TORCH_TIP
                    )
                    rect(g, cx - half, 11 - i, cx + half + 1, 12 - i, k)
                    if half and i < height // 2:
                        put(g, cx - half, 11 - i, TORCH_FLAME)
                        put(g, cx + half, 11 - i, TORCH_FLAME)
        union_outline(g)
        frames.append(g)
    return frames


# The chest's lid per busy step: how far it stands open, 0 shut to 2 thrown
# back, and the glint on the gold inside.
CHEST_STEPS = [(1, None), (2, 0), (2, 1), (2, 2), (2, None), (1, None)]


def chest_body(lid, glint):
    """A treasure chest on a stack of two crates: iron-bound wood, a lock
    plate, the lid shut (0), ajar (1) or thrown back (2) over its gold."""
    w, h = 7 * S, 13 * S
    g = canvas(w, h)
    for top in (h - 13, h - 25):  # the crates
        rect(g, 2, top, w - 2, top + 12, WOOD_SH)
        rect(g, 2, top, w - 2, top + 1, WOOD)
        for x in (2, w - 4):
            rect(g, x, top, x + 2, top + 12, WOOD)
        stem(g, [(4.5, top + 1.5), (w - 4.5, top + 10.5)], 0.7, WOOD)
    base = h - 25
    rect(g, 1, base - 11, w - 1, base, WOOD)  # the chest's body
    rect(g, 1, base - 11, w - 1, base - 10, WOOD_LT)
    for x in (3, w - 5):
        rect(g, x, base - 11, x + 2, base, IRON_SH)
    rect(g, 12, base - 9, 16, base - 4, IRON)  # the lock plate
    put(g, 14, base - 7, SHADOW)
    lid_top = base - 11
    if lid == 0:
        rect(g, 1, lid_top - 6, w - 1, lid_top, WOOD)
        rect(g, 1, lid_top - 6, w - 1, lid_top - 5, WOOD_HI)
        for x in (3, w - 5):
            rect(g, x, lid_top - 6, x + 2, lid_top, IRON_SH)
    else:
        rect(g, 2, lid_top - 2, w - 2, lid_top, GOLD)  # the gold inside
        rect(g, 3, lid_top - 3, w - 3, lid_top - 2, GOLD)
        for x in range(4, w - 4, 4):
            put(g, x, lid_top - 2, OFFWHITE)
        back = 10 if lid == 2 else 6
        rect(g, 1, lid_top - 3 - back, w - 1, lid_top - 3, WOOD_SH)  # the lid's inside
        rect(g, 1, lid_top - 3 - back, w - 1, lid_top - 2 - back, WOOD)
        if glint is not None:
            gx = 6 + glint * 7
            put(g, gx, lid_top - 4, WHITE)
            put(g, gx - 1, lid_top - 3, WHITE)
            put(g, gx + 1, lid_top - 3, WHITE)
    union_outline(g)
    return g


def treasure_chest():
    """A treasure chest in the vending machine's place: shut at rest; while
    in use, the lid thrown back on its gold for each of the machine's vends,
    a glint moving over the coins."""
    frames = [chest_body(0, None)]
    for _ in range(len(VEND_DRINKS)):
        frames.extend(chest_body(lid, glint) for lid, glint in CHEST_STEPS)
    require(len(CHEST_STEPS) == VEND_STEPS, "a chest's take fills a vend's steps")
    return frames


def weapon_rack():
    """A weapon rack in the bookshelf's place: a wooden frame holding two
    swords, a spear and an axe upright, a round shield hung on its side."""
    g = canvas(8 * S, 12 * S)
    for x in (2, 28):  # the uprights
        rect(g, x, 4, x + 3, 47, WOOD)
        rect(g, x + 2, 4, x + 3, 47, WOOD_SH)
    for y in (10, 36):  # the rails
        rect(g, 2, y, 31, y + 2, WOOD)
        rect(g, 2, y + 1, 31, y + 2, WOOD_SH)
    for x, tip in ((8, 6), (12, 8)):  # the swords, point up
        rect(g, x, tip, x + 2, 34, IRON)
        put(g, x, tip, IRON_LT)
        rect(g, x - 2, 34, x + 4, 35, IRON_SH)
        rect(g, x, 35, x + 2, 40, LEATHER)
    rect(g, 18, 1, 19, 44, WOOD_SH)  # the spear
    rect(g, 17, 1, 20, 6, IRON)
    put(g, 18, 0, IRON_LT)
    rect(g, 23, 6, 24, 44, WOOD_SH)  # the axe
    rect(g, 24, 7, 27, 14, IRON)
    rect(g, 24, 7, 25, 14, IRON_LT)
    ellipse(g, 27.0, 26.0, 4.5, 6.0, WOOD)  # the shield
    ellipse(g, 27.0, 26.0, 1.5, 1.5, IRON)
    union_outline(g)
    return g


def poster_sheet(g, x0, y0, x1, y1):
    """A sheet of poster_sheet, its west edge lit and its foot curling."""
    rect(g, x0, y0, x1, y1, TAN)
    rect(g, x0, y0, x0 + 1, y1, OFFWHITE)
    rect(g, x0, y1 - 1, x1, y1, BROWN)


def map_board():
    """A map pinned to a board on legs, in the whiteboard's place: a coast,
    a river, a dotted road and a red cross where the treasure lies."""
    w, h = 14 * S, 11 * S
    g = canvas(w, h)
    for x in (6, w - 8):  # the legs
        rect(g, x, 30, x + 2, h, WOOD_SH)
    rect(g, 2, 2, w - 2, 32, WOOD)
    rect(g, 2, 2, w - 2, 3, WOOD_LT)
    poster_sheet(g, 5, 5, w - 5, 30)
    coast = [(8, 20), (14, 14), (22, 16), (30, 9), (40, 12), (48, 8)]
    stem(g, coast, 0.4, BROWN)
    stem(g, [(26, 15), (28, 22), (24, 27)], 0.4, BLUE)
    for x in range(12, 44, 3):
        put(g, x, 24 - (x // 9), BROWN)
    for d in (-1, 0, 1):
        put(g, 40 + d, 22 + d, RED)
        put(g, 40 + d, 22 - d, RED)
    union_outline(g)
    return g


def wanted(g, x0, y0, w, h):
    """A wanted poster: a poster_sheet with a crude face drawn on it and lines of
    script under."""
    poster_sheet(g, x0, y0, x0 + w, y0 + h)
    cx = x0 + w // 2
    ellipse(g, cx + 0.5, y0 + 5.0, 2.6, 3.0, BROWN)
    ellipse(g, cx + 0.5, y0 + 5.0, 1.6, 2.0, TAN)
    put(g, cx - 1, y0 + 4, BROWN)
    put(g, cx + 1, y0 + 4, BROWN)
    for i in range(2):
        rect(g, x0 + 2, y0 + 10 + i * 2, x0 + w - 2, y0 + 11 + i * 2, BROWN)
    put(g, cx, y0 + 1, IRON_SH)  # its nail


def poster_board(w1x, h1x, posters):
    """A plank board with `posters` pinned up: each `(x, y, w, h)`."""
    w, h = w1x * S, h1x * S
    g = canvas(w, h)
    rect(g, 1, 1, w - 1, h - 1, WOOD)
    for y in range(1, h - 1, 5):
        rect(g, 1, y, w - 1, y + 1, WOOD_SH)
    rect(g, 1, 1, w - 1, 2, WOOD_LT)
    for p in posters:
        wanted(g, *p)
    union_outline(g)
    return g


def wanted_board():
    """The bulletin board's place: a plank board of wanted posters."""
    return poster_board(10, 6, ((3, 3, 10, 16), (15, 4, 10, 15), (28, 3, 9, 16)))


def notice_planks():
    """The notice board's place: planks with two wanted posters."""
    return poster_board(8, 5, ((3, 2, 11, 15), (18, 3, 11, 14)))


# ---- the call to arms: the dungeon's `seated`, held while its sitter waits ------
def horn(g, pts, dy):
    """A curved war horn along `pts`, from its mouthpiece widening to its
    bell: bone banded in gold, the bell's dark mouth."""
    pts = [(x, y + dy) for x, y in pts]
    for (x0, y0), (x1, y1), r in zip(pts, pts[1:], (0.7, 1.0, 1.4, 1.9)):
        stem(g, [(x0, y0), (x1, y1)], r, BONE)
    stem(g, pts[1:3], 0.5, BONE_SH)
    bx, by = pts[-1]
    rect(g, int(bx) - 2, int(by) - 2, int(bx) + 3, int(by) + 3, GOLD)
    rect(g, int(bx) - 1, int(by) - 1, int(bx) + 2, int(by) + 2, BONE_DK)


def sounding(view):
    """Seated, sounding a war horn for help: the east hand lifts the horn to
    the lips, its bell high beside the head; from behind, the bell rises past
    the helm."""

    def draw(g, dy):
        tabard(g, dy, SEAT_Y, back=view == "back", sleeves=False)
        mail(g, 5, SHOULDER_Y + 2, TABARD_X0, CUFF_Y, dy)
        mitt(g, 4, SEAT_Y + dy)
        hand = (20, 22) if view == "front" else (24, 16)
        mail_arm(g, EAST_SHOULDER, (hand[0], hand[1] + dy), dy)
        if view == "front":
            horn(g, [(16, 23), (22, 24), (26, 20), (27, 13), (26, 6)], dy)
        else:
            horn(g, [(20, 14), (25, 14), (27, 11), (27, 7), (26, 3)], dy)
        mitt(g, hand[0], hand[1] + dy)

    return draw


POSES |= {
    f"{DUNGEON}seated": (
        SEATED_ROWS,
        "front",
        sounding("front"),
        "Front view at rest: sounding a war horn for help.",
    ),
    f"{DUNGEON}seated_back": (
        SEATED_ROWS,
        "back",
        sounding("back"),
        "Back view at rest: sounding a war horn for help.",
    ),
}


# ---- the floor indicator's arrows: stairs ---------------------------------------
def stair_icon(up):
    """The floor indicator's arrow as a flight of stairs in its text's ink:
    climbing east for the floor above, descending east for the one below,
    the top step's edge lit."""
    rows = (
        ["...", "...", "...", "..ϊ", ".ιι", "ιιι", "...", "..."]
        if up
        else ["...", "...", "...", "ϊ..", "ιι.", "ιιι", "...", "..."]
    )
    return [list(r) for r in rows]


# ---- the dungeon's stand-ins for the rest of the office ---------------------------
# Every office piece a dungeon floor's layouts can place, so none reads as an
# office: each on the canvas `prop_canvas`/`camp_canvas` gives that piece, and
# its frame count where the office's art plays a loop.
DNG_JARS = (LEAF, BLUE, RED, GOLD)


def dng_slab(g, x0, y0, x1, y1, top=3):
    """A dressed stone block: its top lit, shaded east and along its foot, a
    joint or two."""
    rect(g, x0, y0, x1, y1, ROCK)
    rect(g, x0, y0, x1, y0 + top, ROCK_LT)
    rect(g, x0, y0, x1, y0 + 1, ROCK_HI)
    rect(g, x1 - 2, y0 + top, x1, y1, ROCK_SH)
    rect(g, x0, y1 - 1, x1, y1, ROCK_SH)
    for jx in range(x0 + 9, x1 - 4, 13):
        rect(g, jx, y0 + top, jx + 1, y1 - 1, ROCK_DK)


def dng_candle(g, x, foot):
    """A stub of candle standing on `foot` at column `x`, its flame's heart in
    the bulb key."""
    rect(g, x, foot - 3, x + 2, foot, BONE)
    put(g, x + 1, foot - 3, BONE_SH)
    put(g, x, foot - 4, BULB)
    put(g, x, foot - 5, TORCH_FLAME)


def dng_jar(g, x, foot, h, liquid):
    """A glass jar of `liquid` on `foot`: a cork, the glass's glint."""
    rect(g, x, foot - h, x + 4, foot, liquid)
    rect(g, x + 1, foot - h - 1, x + 3, foot - h, WOOD_LT)
    put(g, x, foot - h, WHITE)


def dng_chain(g, x, y0, y1):
    """An iron chain hanging at column `x`, link over link."""
    for y in range(y0, y1):
        put(g, x, y, IRON if y % 2 else IRON_SH)


def dng_haunch(g, cx, top):
    """A haunch of meat hung by its bone from `top`."""
    put(g, cx, top, BONE)
    put(g, cx, top + 1, BONE)
    ellipse(g, cx + 0.5, top + 6.0, 2.6, 4.2, RED)
    rect(g, cx + 1, top + 4, cx + 3, top + 10, DARK_RED)


def dng_cauldron(g, cx, foot, half):
    """An iron cauldron on `foot`: its belly, its rim, a bubbling green brew."""
    ellipse(g, cx, foot - half * 0.6, half, half * 0.65, IRON_SH)
    rect(
        g,
        int(cx - half),
        int(foot - half * 1.1),
        int(cx + half),
        int(foot - half * 0.9),
        IRON,
    )
    rect(
        g,
        int(cx - half) + 2,
        int(foot - half * 1.1),
        int(cx + half) - 2,
        int(foot - half * 1.1) + 1,
        LEAF_HI,
    )
    put(g, int(cx) - 2, int(foot - half * 1.1) - 1, LEAF_HI)


def dng_rune_disc():
    """A carved stone disc in the wall clock's place, runes round its rim. The
    engine draws a clock's hands as far as the face key reaches out from the
    centre along the middle row; a lone face-key pixel there gives them no
    length, so none are drawn."""
    g = prop_canvas("wall_clock")
    w, h = len(g[0]), len(g)
    c = w / 2
    ellipse(g, c, c, 13.0, 13.0, ROCK)
    lit_ball(g, (ROCK, ROCK_LT, ROCK_HI, ROCK_SH), c, c, 13.0, 13.0)
    for i in range(12):
        a = math.tau * i / 12
        put(g, int(c + math.cos(a) * 10), int(c + math.sin(a) * 10), ROCK_DK)
        if i % 3 == 0:
            put(g, int(c + math.cos(a) * 7), int(c + math.sin(a) * 7), ROCK_DK)
    ellipse(g, c, c, 3.0, 3.0, ROCK_SH)
    put(g, w // 2, h // 2, CLOCK_FACE)
    union_outline(g)
    return g


def dng_rune_tablet():
    """A stone tablet hung on the wall in the meeting screen's place: three
    lines of carved runes, a few of them glowing."""
    g = prop_canvas("meeting_screen")
    w, h = len(g[0]), len(g)
    dng_slab(g, 3, 4, w - 3, h - 2, top=2)
    rect(g, 7, 8, w - 7, h - 6, ROCK_SH)
    rng = Draws(51)
    for row in range(3):
        y = 12 + row * 9
        x = 10
        while x < w - 12:
            glyph = rng.randrange(0, 4)
            k = CYAN if rng.random() < 0.15 else ROCK_DK
            rect(g, x, y, x + 1, y + 5, k)
            if glyph == 1:
                rect(g, x, y, x + 4, y + 1, k)
            elif glyph == 2:
                rect(g, x, y + 4, x + 4, y + 5, k)
            elif glyph == 3:
                put(g, x + 2, y + 2, k)
                put(g, x + 3, y + 1, k)
            x += 6
    union_outline(g)
    return g


def dng_idol():
    """A squat stone idol on a plinth in the screen stand's place, its eyes
    two red gems."""
    g = prop_canvas("tv_stand")
    w, h = len(g[0]), len(g)
    dng_slab(g, 4, h - 9, w - 4, h - 1)
    ellipse(g, w / 2, 23.0, 11.0, 9.0, ROCK)
    ellipse(g, w / 2, 10.0, 7.5, 7.5, ROCK)
    lit_ball(g, (ROCK, ROCK_LT, ROCK_HI, ROCK_SH), w / 2, 18.0, 12.0, 15.0)
    for ex in (w // 2 - 4, w // 2 + 2):
        rect(g, ex, 9, ex + 2, 11, RED)
    rect(g, w // 2 - 3, 14, w // 2 + 3, 15, ROCK_DK)
    rect(g, w // 2 - 8, 22, w // 2 + 8, 23, ROCK_DK)
    union_outline(g)
    return g


def dng_lectern():
    """A stone lectern in the standing desk's place: a pillar under an open
    tome, a candle burning at its corner."""
    g = prop_canvas("standing_desk")
    w, h = len(g[0]), len(g)
    dng_slab(g, 6, h - 5, w - 6, h - 1, top=1)
    dng_slab(g, 12, 13, 20, h - 5, top=1)
    rect(g, 4, 8, w - 4, 13, WOOD)
    rect(g, 5, 5, w // 2 - 1, 11, TAN)
    rect(g, w // 2 + 1, 5, w - 5, 11, TAN)
    for y in (7, 9):
        rect(g, 7, y, w // 2 - 3, y + 1, BROWN)
        rect(g, w // 2 + 3, y, w - 7, y + 1, BROWN)
    dng_candle(g, w - 6, 8)
    union_outline(g)
    return g


def dng_cage():
    """An iron cage in the booth's place: bars under a domed top hung from a
    ring, bones on its floor."""
    w, h = CAMP_CANVAS["phone_booth"][0] * S, CAMP_CANVAS["phone_booth"][1] * S
    g = canvas(w, h)
    dng_slab(g, 1, h - 6, w - 1, h - 1, top=1)
    ellipse(g, w / 2, 10.0, 12.0, 6.0, IRON_SH)
    rect(g, 2, 10, w - 2, 12, IRON)
    rect(g, w // 2 - 1, 1, w // 2 + 1, 4, IRON_LT)
    for x in range(3, w - 2, 4):
        rect(g, x, 12, x + 1, h - 6, IRON_SH if x > w // 2 else IRON)
    rect(g, 2, h - 9, w - 2, h - 7, IRON)
    bones(g, 7, h - 11)
    union_outline(g)
    return g


def dng_bench(front):
    """A stone bench in the sofa's place: seen from the front, a backrest of
    stacked stones over the seat slab; from behind, the seat on top and the
    backrest's lit ridge over the stones of its back."""
    w, h = 20 * S, 7 * S
    g = canvas(w, h)
    if front:
        for i, x in enumerate(range(1, w - 1, 13)):  # the backrest's stones
            dng_slab(g, x, 1 + (i % 2), min(x + 13, w - 1), 13, top=2)
        dng_slab(g, 1, 12, w - 1, h - 1, top=5)
    else:
        dng_slab(g, 1, 1, w - 1, 12, top=8)
        rect(g, 1, 12, w - 1, 14, ROCK_HI)
        for i, x in enumerate(range(1, w - 1, 13)):
            dng_slab(g, x, 14, min(x + 13, w - 1), h - 1, top=1)
    union_outline(g)
    return g


def dng_bench_front():
    """The stone bench seen from the front."""
    return dng_bench(True)


def dng_bench_back():
    """The stone bench seen from behind."""
    return dng_bench(False)


def dng_rough_table():
    """A rough table in the meeting table's place: planks on trestles, a
    skull with a candle on it, a dagger."""
    g = prop_canvas("meeting_table")
    w, h = len(g[0]), len(g)
    rect(g, 2, 3, w - 2, 12, WOOD)
    rect(g, 2, 3, w - 2, 4, WOOD_LT)
    for x in range(11, w - 2, 10):
        rect(g, x, 4, x + 1, 12, WOOD_SH)
    rect(g, 2, 12, w - 2, 14, WOOD_SH)
    for x in (5, w - 8):
        rect(g, x, 14, x + 3, h, WOOD_DK)
    skull(g, 7, 2)
    dng_candle(g, 10, 3)
    stem(g, [(26, 8), (36, 6)], 0.5, IRON_LT)
    rect(g, 24, 8, 27, 9, LEATHER)
    union_outline(g)
    return g


def dng_stone_seat():
    """A stone seat in the meeting chair's place, its back to the west."""
    g = prop_canvas("meeting_chair")
    w, h = len(g[0]), len(g)
    dng_slab(g, 3, 4, 10, h - 1, top=2)
    dng_slab(g, 9, 13, w - 3, h - 1, top=4)
    union_outline(g)
    return g


def dng_chain_post():
    """A post hung with chains and shackles in the coat rack's place, a skull
    set on its top."""
    g = prop_canvas("coat_rack")
    w, h = len(g[0]), len(g)
    rect(g, 8, 6, 12, h - 2, WOOD)
    rect(g, 11, 6, 12, h - 2, WOOD_SH)
    rect(g, 4, h - 2, 16, h, WOOD_DK)
    rect(g, 2, 9, w - 2, 11, WOOD_DK)
    for x in (3, w - 4):
        dng_chain(g, x, 11, 27)
        rect(g, x - 1, 27, x + 2, 30, IRON_LT)
        put(g, x, 28, T)
    skull(g, 6, 0)
    union_outline(g)
    return g


def dng_candle_block():
    """A stone block in the side table's place, three candles burning on it."""
    w, h = CAMP_CANVAS["side_table"][0] * S, CAMP_CANVAS["side_table"][1] * S
    g = canvas(w, h)
    dng_slab(g, 3, 7, w - 3, h - 1)
    for x in (7, 13, 19):
        dng_candle(g, x, 8)
    union_outline(g)
    return g


def dng_candelabrum():
    """A tall iron candelabrum in the floor lamp's place: a pole on three feet
    under a dish of flame, its heart in the bulb key so its light pools."""
    w, h = CAMP_CANVAS["floor_lamp"][0] * S, CAMP_CANVAS["floor_lamp"][1] * S
    g = canvas(w, h)
    rect(g, 7, 12, 9, h - 3, IRON_SH)
    rect(g, 7, 12, 8, h - 3, IRON)
    for fx in (2, 7, 13):
        stem(g, [(8, h - 4), (fx + 0.5, h - 0.5)], 0.6, IRON_SH)
    rect(g, 3, 10, 13, 12, IRON)
    torch_core = master("""
        ...ɜ...
        ..ɛɜ...
        .ɛɛɛɜ..
        .ɛ99ɛ..
        ɛ9999ɛ.
        ɛɛ99ɛɛ.
    """)
    paste(g, torch_core, 4, 4)
    union_outline(g)
    return g


# The vat's bubbles: each lane's column and the frame it starts rising on.
DNG_VAT_LANES = ((16, 0), (27, 6), (38, 12))
DNG_VAT_FRAMES = 18


def dng_vat():
    """A great glass vat of green brew in the fish tank's place, on a stone
    base, bubbles rising through it in turn."""
    blank = prop_canvas("fish_tank")
    w, h = len(blank[0]), len(blank)
    frames = []
    surface, bottom = 9, 32
    for f in range(DNG_VAT_FRAMES):
        g = canvas(w, h)
        dng_slab(g, 2, bottom, w - 2, h - 1)
        rect(g, 6, 4, w - 6, bottom, IRON_SH)
        rect(g, 8, surface, w - 8, bottom, LEAF)
        rect(g, 8, surface, w - 8, surface + 1, LEAF_HI)
        rect(g, w - 14, surface + 1, w - 8, bottom, LEAF_SH)
        rect(g, 9, 6, 11, bottom - 2, WHITE)
        rect(g, 4, 3, w - 4, 5, IRON)
        for x, start in DNG_VAT_LANES:
            rise = (f - start) % DNG_VAT_FRAMES
            y = bottom - 2 - rise * 2
            if surface < y:
                put(g, x, y, LEAF_HI)
                put(g, x + 1, y, LEAF_HI)
        union_outline(g)
        frames.append(g)
    return frames


# The font's drip, per frame: the drop's row under the spout, None at rest.
DNG_DRIPS = (None, 4, 8, 11, None)


def dng_font():
    """A stone font in the water cooler's place: a basin of water on a pillar,
    a drop falling into it from the cave's roof while in use."""
    blank = prop_canvas("water_cooler")
    w, h = len(blank[0]), len(blank)
    frames = []
    for drip in DNG_DRIPS:
        g = canvas(w, h)
        dng_slab(g, 5, 16, 11, h - 1, top=1)
        dng_slab(g, 3, h - 4, 13, h - 1, top=1)
        rect(g, 1, 11, w - 1, 17, ROCK)
        rect(g, 1, 16, w - 1, 17, ROCK_SH)
        rect(g, 2, 11, w - 2, 13, BLUE)
        rect(g, 3, 11, w - 5, 12, CYAN)
        if drip is not None:
            put(g, 8, drip, CYAN)
            if drip >= 11:
                put(g, 6, 11, WHITE)
                put(g, 10, 11, WHITE)
        union_outline(g)
        frames.append(g)
    return frames


def dng_jar_shelf():
    """A wooden shelf of jars in the snack shelf's place: brews in four
    colours, a skull, a candle."""
    g = prop_canvas("snack_shelf")
    w, h = len(g[0]), len(g)
    for x in (1, w - 3):
        rect(g, x, 1, x + 2, h, WOOD_SH)
    for i, y in enumerate((13, 26, h - 2)):
        rect(g, 1, y, w - 1, y + 2, WOOD)
        if i == 0:
            skull(g, 4, y - 7)
            dng_jar(g, 14, y, 6, DNG_JARS[0])
            dng_candle(g, 21, y)
        elif i == 1:
            for j, x in enumerate((4, 10, 16, 21)):
                dng_jar(g, x, y, 5 + j % 2 * 2, DNG_JARS[j])
        else:
            dng_jar(g, 5, y, 7, DNG_JARS[2])
            rect(g, 12, y - 6, 22, y, TAN)
            rect(g, 12, y - 6, 22, y - 5, BROWN)
    union_outline(g)
    return g


def dng_larder(piece):
    """A larder in the pantry's place: a stone hearth with a cauldron on its
    fire west, a counter of sacks and jars, haunches hung from a rack over
    it."""
    g = prop_canvas(piece)
    w, h = len(g[0]), len(g)
    hearth = 28
    dng_slab(g, 2, 6, hearth, h - 1, top=2)
    rect(g, 6, h - 16, hearth - 4, h - 3, SHADOW)
    for x in range(8, hearth - 6, 3):
        put(g, x, h - 4, VERMILION)
        put(g, x + 1, h - 5, BULB)
    dng_cauldron(g, (hearth + 2) / 2, h - 5, 7.0)
    top = h - 14
    dng_slab(g, hearth, top, w - 2, h - 1)
    rect(g, hearth + 2, 2, w - 3, 4, WOOD_DK)
    for x in range(hearth + 6, w - 6, 12):
        dng_haunch(g, x, 4)
    rng = Draws(len(piece))
    x = hearth + 4
    while x < w - 10:
        if rng.random() < 0.5:
            dng_jar(g, x, top, 5, DNG_JARS[rng.randrange(0, len(DNG_JARS))])
            x += 7
        else:
            ellipse(g, x + 4.0, top - 3.5, 4.0, 3.5, TAN)
            put(g, x + 4, top - 7, BROWN)
            x += 10
    union_outline(g)
    return g


def dng_larder_large():
    """The larder, the wide pantry's."""
    return dng_larder("pantry")


def dng_larder_small():
    """The larder, the narrow pantry's."""
    return dng_larder("pantry_small")


def dng_butcher_block():
    """A butcher's block in the kitchen island's place: a long scarred table,
    a haunch, a cleaver and bones on it."""
    g = prop_canvas("kitchen_island")
    w, h = len(g[0]), len(g)
    rect(g, 2, 6, w - 2, 18, WOOD)
    rect(g, 2, 6, w - 2, 7, WOOD_LT)
    for x in range(14, w - 4, 15):
        rect(g, x, 7, x + 1, 18, WOOD_SH)
    rect(g, 2, 18, w - 2, 20, WOOD_SH)
    for x in (5, w - 9):
        rect(g, x, 20, x + 4, h, WOOD_DK)
    ellipse(g, 18.0, 9.0, 6.0, 3.5, RED)
    rect(g, 22, 8, 27, 10, BONE)
    rect(g, 40, 6, 48, 11, IRON)
    rect(g, 40, 6, 48, 7, IRON_LT)
    rect(g, 48, 8, 54, 10, WOOD_DK)
    bones(g, 60, 10)
    union_outline(g)
    return g


def dng_urn():
    """A clay urn in the bin's place, bones sticking out of it."""
    g = prop_canvas("pantry_bin")
    w, h = len(g[0]), len(g)
    ellipse(g, w / 2, h - 7.0, 6.5, 6.5, POT)
    rect(g, 4, 5, w - 4, 8, POT)
    rect(g, 3, 5, w - 3, 6, POT_HI)
    for y in range(len(g)):
        for x in range(w):
            if g[y][x] == POT and x > w / 2 + 2:
                g[y][x] = POT_SH
    rect(g, 5, 1, 7, 6, BONE)
    rect(g, 9, 0, 11, 6, BONE_SH)
    put(g, 4, 1, BONE)
    put(g, 11, 0, BONE)
    union_outline(g)
    return g


# ---- the dungeon's holidays: a festive stand-in for each office one ------------
def dng_twinkle(frames, spots):
    """`frames` with crystals at `spots` glinting in turn, frame by frame."""
    for f, g in enumerate(frames):
        for i, (x, y) in enumerate(spots):
            put(g, x, y, WHITE if (i + f) % 2 else CYAN)
    return frames


def dng_crystal_spire():
    """The tall holiday stand-in: the stalagmite set with crystals that glint
    in turn."""
    return dng_twinkle(
        [stalagmite() for _ in range(2)],
        ((10, 8), (8, 16), (13, 22), (18, 26), (6, 30)),
    )


def dng_crystal_mushrooms():
    """The short holiday stand-in: the cave mushrooms with glinting motes."""
    return dng_twinkle(
        [mushrooms() for _ in range(2)], ((3, 6), (21, 4), (12, 1), (22, 14))
    )


def dng_red_caps():
    """The flowering holiday stand-in: red-capped mushrooms on a stone."""
    g = canvas(6 * S, 6 * S)
    boulder(g, 12.0, 20.0, 9.0, 3.5, 37)
    for cx, top, r in ((8, 6, 4.5), (15, 2, 5.5)):
        rect(g, cx - 1, top + 3, cx + 1, 19, BONE)
        ellipse(g, cx, top + 2.5, r, r * 0.6, RED)
        put(g, cx - 2, top + 1, WHITE)
        put(g, cx + 1, top + 2, WHITE)
    union_outline(g)
    return g


def dng_sacks():
    """The presents' stand-in: two sacks of treasure tied with gold cord."""
    g = canvas(5 * S, 4 * S)
    for cx, r in ((7.0, 5.0), (14.0, 4.0)):
        ellipse(g, cx, 16 - r, r, r, TAN)
        rect(
            g, int(cx) - 1, int(16 - 2 * r) - 1, int(cx) + 1, int(16 - 2 * r) + 1, GOLD
        )
    put(g, 10, 15, GOLD)
    union_outline(g)
    return g


# The dungeon's stand-ins, each drawn on the canvas of the piece it replaces.
DUNGEON_PIECES = {
    "desk": lair_south,
    "desk_north": lair_north,
    "desk_chair": dropped_shield,
    "desk_cup": potion,
    "token_tower": loot_pile,
    "token_sheet": falling_coin,
    "door": stair_arch,
    "filing_cabinet": cask,
    "plant": mushrooms,
    "plant_tall": stalagmite,
    "plant_flower": bone_pile,
    "plant_succulent": rubble,
    "exit_sign": wall_torch,
    "printer": brazier,
    "vending_machine": treasure_chest,
    "bookshelf": weapon_rack,
    "whiteboard": map_board,
    "bulletin_board": wanted_board,
    "notice_board": notice_planks,
    "wall_clock": dng_rune_disc,
    "meeting_screen": dng_rune_tablet,
    "tv_stand": dng_idol,
    "standing_desk": dng_lectern,
    "phone_booth": dng_cage,
    "meeting_sofa": dng_bench_front,
    "meeting_sofa_north": dng_bench_back,
    "meeting_table": dng_rough_table,
    "meeting_chair": dng_stone_seat,
    "coat_rack": dng_chain_post,
    "side_table": dng_candle_block,
    "floor_lamp": dng_candelabrum,
    "fish_tank": dng_vat,
    "water_cooler": dng_font,
    "snack_shelf": dng_jar_shelf,
    "pantry": dng_larder_large,
    "pantry_small": dng_larder_small,
    "kitchen_island": dng_butcher_block,
    "pantry_bin": dng_urn,
    "christmas_tree": dng_crystal_spire,
    "christmas_tree_short": dng_crystal_mushrooms,
    "poinsettia": dng_red_caps,
    "presents": dng_sacks,
}


PROVENANCE = "Generated by scripts/gen-art.py: edit the generator, not this file."
ENCODING = (
    "utf-8"  # the keys include σ/ψ/Θ, and the locale's encoding need not be the file's
)


def render_sprite(header, frames, heads=(), marks=()):
    """A .sprite file: the header as comments, then each frame, marked with its
    `heads` entry `(view, x, y)` where it has one; the first frame also carries
    `marks`, each `(name, x, y)`."""
    text = inspect.cleandoc(header) + "\n" + PROVENANCE
    lines = [f"# {line}" if line else "#" for line in text.split("\n")]
    body = []
    for i, g in enumerate(frames):
        body.append(f"@frame {i}")
        if i < len(heads) and heads[i] is not None:
            view, x, y = heads[i]
            body.append(f"@mark head.{view} {x} {y}")
        if i == 0:
            body.extend(f"@mark {name} {x} {y}" for name, x, y in marks)
        body.extend(" ".join(r) for r in g)
    return "\n".join(lines + body) + "\n"


def hair_file(style, view, part):
    """The sprite a hairstyle's layer is written to, named as `[hairstyles]` lists it."""
    return f"hair_{style}_{view}_{part}@{S}x.sprite"


def orphans(pack, sprites):
    """The generated sprites on disk that `sprites` no longer draws."""
    return sorted(
        p.name
        for p in pack.glob("*.sprite")
        if p.name not in sprites
        and f"# {PROVENANCE}" in p.read_text(encoding=ENCODING).splitlines()
    )


def manifest_drift(pack):
    """Why pack.toml names other keys than the ones drawn in, or None."""
    manifest = pack / "pack.toml"
    if not manifest.is_file():
        return None
    toml = tomllib.loads(manifest.read_text(encoding=ENCODING))
    named = toml.get("city")
    if named != CITY:
        return f"gen-art --check: pack.toml [city] {named} is not the keys drawn in, {CITY}"
    outline = toml.get("characters", {}).get("outline")
    if outline != SILHOUETTE:
        return (
            f"gen-art --check: pack.toml [characters] outline {outline!r} is not the art's, "
            f"{SILHOUETTE!r}"
        )
    return None


def check(pack, sprites):
    """Why the committed pack is not what `sprites` draws, or None when it is."""
    drift = manifest_drift(pack)
    if drift:
        return drift
    stale = sorted(
        name
        for name, text in sprites.items()
        if not (pack / name).is_file()
        or (pack / name).read_text(encoding=ENCODING) != text
    )
    gone = orphans(pack, sprites)
    if not stale and not gone:
        return None
    lines = [f"gen-art --check: stale {stale}, orphaned {gone} — run `just gen-art`"]
    if stale and (pack / stale[0]).is_file():
        committed = (pack / stale[0]).read_text(encoding=ENCODING).splitlines()
        drawn = sprites[stale[0]].splitlines()
        diff = difflib.unified_diff(
            committed,
            drawn,
            f"committed/{stale[0]}",
            f"drawn/{stale[0]}",
            n=0,
            lineterm="",
        )
        lines.extend(list(diff)[:20])
    return "\n".join(lines)


def write(pack, sprites):
    for name in orphans(pack, sprites):
        (pack / name).unlink()
        print("deleted", name)
    for name, text in sprites.items():
        (pack / name).write_text(text, encoding=ENCODING)
        print("wrote", name)


def selftest(sprites):
    """A drift gate that cannot fail is no gate."""
    with tempfile.TemporaryDirectory() as tmp:
        pack = pathlib.Path(tmp)
        write(pack, sprites)
        require(check(pack, sprites) is None, "a freshly drawn pack must pass")
        first = min(sprites)
        (pack / first).write_text(sprites[first] + ". .\n", encoding=ENCODING)
        require(check(pack, sprites) is not None, "an edited sprite must fail")
        (pack / first).unlink()
        require(check(pack, sprites) is not None, "a missing sprite must fail")
        write(pack, sprites)
        (pack / "gone@4x.sprite").write_text(f"# {PROVENANCE}\n", encoding=ENCODING)
        require(check(pack, sprites) is not None, "an orphan must fail")
        write(pack, sprites)
        require(check(pack, sprites) is None, "a write must delete the orphan")
        (pack / "hand.sprite").write_text(
            f"# copied from {first}: {PROVENANCE}\n@frame 0\n.\n", encoding=ENCODING
        )
        require(
            check(pack, sprites) is None,
            "hand art quoting the provenance is not an orphan",
        )
        city = "[city]\n" + "".join(f'{k} = "{v}"\n' for k, v in CITY.items())
        outline = f'[characters]\noutline = "{SILHOUETTE}"\n'
        (pack / "pack.toml").write_text(
            city + '[characters]\noutline = "n"\n', encoding=ENCODING
        )
        require(
            check(pack, sprites) is not None,
            "an outline the art does not draw must fail",
        )
        (pack / "pack.toml").write_text(city, encoding=ENCODING)
        require(check(pack, sprites) is not None, "a pack naming no outline must fail")
        (pack / "pack.toml").write_text(outline, encoding=ENCODING)
        require(check(pack, sprites) is not None, "a pack naming no city must fail")
        (pack / "pack.toml").write_text(city + outline, encoding=ENCODING)
        require(check(pack, sprites) is None, "the art's own city and outline pass")
    print(f"gen-art --selftest: OK ({len(sprites)} sprites)")


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "pack",
        nargs="?",
        type=pathlib.Path,
        help="the pack directory to write or check",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="fail on drift; write nothing"
    )
    mode.add_argument(
        "--selftest", action="store_true", help="prove the check can fail"
    )
    args = parser.parse_args()
    if not args.selftest and args.pack is None:
        parser.error("a pack directory is required")
    pieces = {
        "plant": (doc(plant_bush), [plant_bush()]),
        "plant_tall": (doc(plant_tall), [plant_tall()]),
        "plant_flower": (doc(plant_flower), [plant_flower()]),
        "plant_succulent": (doc(plant_succulent), [plant_succulent()]),
        "christmas_tree": (doc(christmas_tree), christmas_tree()),
        "christmas_tree_short": (doc(christmas_tree_short), christmas_tree_short()),
        "poinsettia": (doc(poinsettia), [poinsettia()]),
        "presents": (doc(presents), [presents()]),
        "floor_lamp": (doc(floor_lamp), [floor_lamp()]),
        "filing_cabinet": (doc(filing_cabinet), [filing_cabinet()]),
        "bulletin_board": (doc(bulletin_board), [bulletin_board()]),
        "exit_sign": (doc(exit_sign), [exit_sign()]),
        "whiteboard": (doc(whiteboard), [whiteboard()]),
        "bookshelf": (doc(bookshelf), [bookshelf()]),
        "meeting_screen": (doc(meeting_screen), [meeting_screen()]),
        "pantry": (doc(pantry), [pantry()]),
        "pantry_small": (doc(pantry_small), [pantry_small()]),
        "snack_shelf": (doc(snack_shelf), [snack_shelf()]),
        "tv_stand": (doc(tv_stand), [tv_stand()]),
        "phone_booth": (doc(phone_booth), [phone_booth()]),
        "standing_desk": (doc(standing_desk), [standing_desk()]),
        "desk_chair": (doc(desk_chair), [desk_chair()]),
        "desk_cup": (doc(desk_cup), [desk_cup()]),
        "token_tower": (doc(token_tower), token_tower()),
        "token_sheet": (doc(token_sheet), [token_sheet()]),
        "desk": (doc(desk_south), [desk_south()]),
        "desk_north": (doc(desk_north), [desk_north()]),
        "meeting_sofa": (doc(meeting_sofa), [meeting_sofa()]),
        "meeting_sofa_north": (doc(meeting_sofa_north), [meeting_sofa_north()]),
        "vending_machine": (doc(vending_machine), vending_machine()),
        "printer": (doc(printer), printer()),
        "meeting_table": (doc(meeting_table), [meeting_table()]),
        "kitchen_island": (doc(kitchen_island), [kitchen_island()]),
        "side_table": (doc(side_table), [side_table()]),
        "water_cooler": (doc(water_cooler), water_cooler()),
        "pantry_bin": (doc(trash_bin), [trash_bin()]),
        "fish_tank": (doc(fish_tank), fish_tank()),
        "coat_rack": (doc(coat_rack), [coat_rack()]),
        "notice_board": (doc(notice_board), [notice_board()]),
        "wall_clock": (doc(wall_clock), [wall_clock()]),
        "meeting_chair": (doc(meeting_chair), [meeting_chair()]),
        "door": (doc(elevator_door), elevator_door()),
    }
    classic = {
        "meeting_sofa_north": (
            doc(meeting_sofa_north_1x),
            [meeting_sofa_north_1x()],
        ),
        "desk": (doc(desk_south_1x), [desk_south_1x()]),
        "desk_north": (doc(desk_north_1x), [desk_north_1x()]),
        "desk_cup": (doc(desk_cup_1x), [desk_cup_1x()]),
        "token_tower": (doc(token_tower_1x), token_tower_1x()),
        "token_sheet": (doc(token_sheet_1x), [token_sheet_1x()]),
        "vending_machine": (doc(vending_machine_1x), vending_machine_1x()),
        "floor_lamp": (doc(floor_lamp_1x), [floor_lamp_1x()]),
        "phone_booth": (doc(phone_booth_1x), [phone_booth_1x()]),
        "printer": (doc(printer_1x), printer_1x()),
        "meeting_table": (doc(meeting_table_1x), [meeting_table_1x()]),
        "kitchen_island": (doc(kitchen_island_1x), [kitchen_island_1x()]),
        "side_table": (doc(side_table_1x), [side_table_1x()]),
        "water_cooler": (doc(water_cooler_1x), water_cooler_1x()),
        "pantry_bin": (doc(trash_bin_1x), [trash_bin_1x()]),
        "fish_tank": (doc(fish_tank_1x), fish_tank_1x()),
        "coat_rack": (doc(coat_rack_1x), [coat_rack_1x()]),
        "notice_board": (doc(notice_board_1x), [notice_board_1x()]),
        "wall_clock": (doc(wall_clock_1x), [wall_clock_1x()]),
        "meeting_chair": (doc(meeting_chair_1x), [meeting_chair_1x()]),
    }
    sprites = {
        f"{base}@{S}x.sprite": render_sprite(
            header, grounded(frames), marks=DESK_MARKS.get(base, ())
        )
        for base, (header, frames) in pieces.items()
    }
    for pose, (*_, header) in POSES.items():
        body, head = body_frame(pose)
        sprites[f"{pose}@{S}x.sprite"] = render_sprite(
            header + "\nBald: the pack's [hairstyles] dress it.", [body], [head]
        )
    for style in HAIRSTYLES:
        for view, parts in hair_layers(style).items():
            for part, lyr in zip(("behind", "over"), parts):
                if lyr is not None and any(c != T for row in lyr for c in row):
                    sprites[hair_file(style, view, part)] = render_sprite(
                        f"The {style} hairstyle, {view} view: the layer {part} the body.",
                        [lyr],
                        [(view, HEAD_MARK[0], HEAD_MARK[1] + LIFT)],
                    )
    check_walks()
    sprites["standing.sprite"] = render_sprite(
        doc(figure_1x), [figure_1x()], [head_mark_1x("front")]
    )
    for name, (view, mug, title) in WALKS.items():
        for i, step in enumerate(WALK_CYCLE):
            sprites[f"{name}_{i}.sprite"] = render_sprite(
                f"{title}, frame {i}: {step.phase}. "
                "The base art's person (`standing`) at this step.",
                [walk_1x(view, step, mug)],
                [head_mark_1x(view)],
            )
    for view, suffix in VIEW_SUFFIX.items():
        for i in range(TYPING_FRAMES):
            sprites[f"typing{suffix}_{i}.sprite"] = render_sprite(
                f"Typing, {view} view, frame {i}.\n\n{doc(typing_1x)}",
                [typing_1x(view, i)],
                [head_mark_1x(view)],
            )
        for cls, attack in ATTACKS.items():
            for i in range(len(attack(view))):
                sprites[f"attack_{cls}{suffix}_{i}.sprite"] = render_sprite(
                    f"The {cls}'s attack, {view} view, frame {i}: the base art's "
                    "typist, which the classic profile draws for every class.",
                    [typing_1x(view, i % TYPING_FRAMES)],
                    [head_mark_1x(view)],
                )
    classic_marks = {
        "desk": desk_marks_1x("desk"),
        "desk_north": desk_marks_1x("desk_north"),
    }
    sprites |= {
        f"{base}.sprite": render_sprite(
            header, grounded(frames), marks=classic_marks.get(base, ())
        )
        for base, (header, frames) in classic.items()
    }
    # A front layer is drawn at its desk's top-left on the desk's own canvas, so
    # it is not grounded on its own rows, and the desk under it must not move.
    for desk, front, suffix in (
        (desk_south_1x, desk_front_1x, ""),
        (desk_south, desk_front, f"@{S}x"),
    ):
        art = desk()
        require(grounded([art]) == [art], f"desk{suffix} moves when grounded")
        sprites[f"desk_front{suffix}.sprite"] = render_sprite(doc(front), [front()])
    for base, draw in DUNGEON_PIECES.items():
        art = draw()
        frames = art if isinstance(art[0][0], list) else [art]
        sprites[f"{DUNGEON}{base}@{S}x.sprite"] = render_sprite(
            doc(draw), grounded(frames), marks=DESK_MARKS.get(base, ())
        )
    require(
        grounded([lair_south()]) == [lair_south()], "the south lair moves when grounded"
    )
    for up, name in ((True, "floor_up"), (False, "floor_down")):
        sprites[f"{DUNGEON}icon_{name}.sprite"] = render_sprite(
            doc(stair_icon), [stair_icon(up)]
        )
    sprites[f"{DUNGEON}desk_front@{S}x.sprite"] = render_sprite(
        doc(lair_south_front), [lair_south_front()]
    )
    for anim, (header, texts) in CREATURES.items():
        for i, g in enumerate(grounded([master(t) for t in texts])):
            sprites[f"{anim}_{i}@{S}x.sprite"] = render_sprite(header, [g])
            sprites[f"{anim}_{i}.sprite"] = render_sprite(
                header + "\n\nIts base: the master read at 1x.",
                [creature_base(f"{anim}_{i}", g)],
            )
    for piece, (draw, animated) in CAMP.items():
        frames = draw() if animated else [draw()]
        # a front layer keeps its desk's canvas, so it is not grounded
        if piece != "desk_front":
            frames = grounded(frames)
        head = CAMP_HEADS.get(piece)
        sprites[f"camp_{piece}@{S}x.sprite"] = render_sprite(
            doc(draw),
            frames,
            heads=[head] if head else (),
            marks=CAMP_DESK_MARKS.get(piece, ()),
        )
    require(grounded([camp_desk()]) == [camp_desk()], "camp_desk moves when grounded")
    sprites["camp_side_table.sprite"] = render_sprite(
        doc(camp_fire_1x), grounded(camp_fire_1x())
    )
    for name, art in camp_skyline().items():
        sprites[f"camp_building_{name}@{S}x.sprite"] = render_sprite(
            doc(camp_skyline), [art]
        )
        sprites[f"camp_building_{name}.sprite"] = render_sprite(
            doc(camp_skyline) + "\n\nIts base: the drawing read at 1x.",
            [city_base(art)],
        )
    for name, draw in BUILDINGS.items():
        art = draw()
        sprites[f"building_{name}@{S}x.sprite"] = render_sprite(doc(draw), [art])
        sprites[f"building_{name}.sprite"] = render_sprite(
            doc(draw) + "\n\nIts base: the drawing read at 1x.", [city_base(art)]
        )
    if args.selftest:
        selftest(sprites)
    elif args.check:
        problem = check(args.pack, sprites)
        if problem:
            sys.exit(problem)
        print(f"gen-art --check: OK ({len(sprites)} sprites)")
    else:
        write(args.pack, sprites)


if __name__ == "__main__":
    main()
