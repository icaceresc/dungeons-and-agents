//! Each effect's look in layout cells, which every painter draws it from;
//! [`super`] decides only when and where one shows.

use crate::sprite::Rgb;

use super::{Banner, Effect, EffectKind, HEART_LIFE_MS, SLEEP_Z_RISE_MS, STEAM_CYCLE_MS};
use crate::composite::WHITE;
use crate::layout::chrome::Glyph;
use crate::layout::{Point, WALKING_Y_OFF};
use crate::theme::Theme;

/// The scanline's color over a screen glowing `tint`.
pub(crate) fn scanline_color(tint: Rgb) -> Rgb {
    tint.mix(WHITE, 0.7)
}

/// The theme's colours the effects are drawn in, resolved where a look is
/// built, so drawing it reads no theme.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) struct Inks {
    pub(crate) sleep_z: Rgb,
    pub(crate) requires_action: Rgb,
    pub(crate) dust: Rgb,
    pub(crate) steam: Rgb,
}

impl Inks {
    /// `theme`'s effect colours.
    pub(crate) fn of(theme: &Theme) -> Self {
        let e = &theme.effects;
        Self {
            sleep_z: e.sleep_z,
            requires_action: e.requires_action_bubble,
            dust: e.walking_dust,
            steam: e.coffee_steam,
        }
    }
}

/// `e`'s look in layout cells: each one `plot` gets is painted its colour over
/// `alpha` of what lies there, a whole cell at `1.0`.
pub(crate) fn plot_effect(e: &Effect, inks: &Inks, plot: &mut impl FnMut(u16, u16, Rgb, f32)) {
    match e.kind {
        EffectKind::SleepZ => plot_sleep_z(plot, e.at, e.phase, inks),
        EffectKind::RequiresActionMark => plot_requires_action_mark(plot, e.at, inks),
        EffectKind::WalkingDust => plot_walking_dust(plot, e.at, e.phase, inks),
        EffectKind::PetHeart => plot_pet_heart(plot, e.at, e.phase),
        EffectKind::SteamPuff => plot_steam_puff(plot, e.at, e.phase, inks),
        EffectKind::MascotBubble => plot_mascot_bubble(plot, e.at, e.phase),
        EffectKind::SubagentBanner(cap) => plot_subagent_banner(plot, e.at, cap),
    }
}

/// The sleep z on the base art, a layout cell per art cell: the classic's and
/// the cutaway's at 1x.
pub(crate) const SLEEP_Z_1X: Glyph = Glyph::new(&[
    "##", //
    ".#", //
    "##", //
]);

/// The requires-action mark on the base art, as [`SLEEP_Z_1X`] is.
pub(crate) const REQUIRES_ACTION_MARK_1X: Glyph = Glyph::new(&[
    "###", //
    "..#", //
    ".#.", //
    ".#.", //
]);

/// A subagent's banner on the base art, as [`SLEEP_Z_1X`] is, its pole the last
/// column: cloth `l` lit, `b` base and `s` shade, `w` wood. The 4x look draws
/// the same banner finer (`display::effects::banner_look`).
const BANNER_1X: [&str; 3] = ["lllw", "bbsw", ".bsw"];
/// Cells from the head mark west to the pole: just clear of the body's edge.
pub(crate) const BANNER_1X_POLE_DX: i32 = 5;
/// Cells the cloth's top stands over the brow, so its ring is the frame's top
/// row and the badge over the frame stays clear.
const BANNER_1X_RISE: i32 = 1;
/// Cells from the brow down to where the pole ends: the shoulder, which a strap
/// two cells long crosses one row above.
const BANNER_1X_FOOT: i32 = 6;
const BANNER_1X_STRAP_LEN: i32 = 2;
/// The one shade a banner draws its shading in, one ramp step down: the
/// darkest ink's shade still reads against the banner's ring
/// (`every_banner_shade_reads_as_a_graphic_against_its_ring`).
pub(crate) const BANNER_SHADE: i8 = -1;
/// The pack's wood (`O`, `D`), iron (`Σ`) and dark leather (`г`), which every
/// banner's pole, tip and strap are drawn in (`banner_materials_are_the_packs`).
pub(crate) const WOOD_LIT: Rgb = Rgb {
    r: 0x7a,
    g: 0x5a,
    b: 0x3a,
};
/// See [`WOOD_LIT`].
pub(crate) const WOOD: Rgb = Rgb {
    r: 0x5e,
    g: 0x41,
    b: 0x28,
};
/// See [`WOOD_LIT`].
pub(crate) const IRON: Rgb = Rgb {
    r: 0x7e,
    g: 0x83,
    b: 0x8c,
};
/// See [`WOOD_LIT`].
pub(crate) const LEATHER: Rgb = Rgb {
    r: 0x4a,
    g: 0x30,
    b: 0x20,
};

/// Layout rows a sleep z rises over its life.
pub(crate) const SLEEP_Z_MAX_RISE: u16 = 4;

/// How opaque a sleep z `phase_ms` into its rise is, and how far through the
/// rise it is; `None` once it is too faint to see.
pub(crate) fn sleep_z_fade(phase_ms: u64) -> Option<(f32, f32)> {
    // The height-coupled fade (`1.0 - t`) is what keeps the z from reading as a
    // solid mark parked over the sprite: it is only briefly visible near the
    // head, then dissolves.
    const FADE_IN_MS: f32 = 150.0;
    const PEAK_ALPHA: f32 = 0.9;
    let t = phase_ms as f32 / SLEEP_Z_RISE_MS as f32;
    // Ramp-in avoids a hard pop when a fresh z spawns at the head.
    let fade_in = (phase_ms as f32 / FADE_IN_MS).min(1.0);
    let alpha = PEAK_ALPHA * fade_in * (1.0 - t);
    (alpha >= 0.06).then_some((alpha, t))
}

fn plot_sleep_z(plot: &mut impl FnMut(u16, u16, Rgb, f32), at: Point, phase_ms: u64, inks: &Inks) {
    let z_color = inks.sleep_z;
    let Some((alpha, t)) = sleep_z_fade(phase_ms) else {
        return;
    };
    let rise = (t * f32::from(SLEEP_Z_MAX_RISE)) as u16;
    let z_y = at.y.saturating_sub(rise + 3);
    for (dx, dy) in SLEEP_Z_1X.inked() {
        plot(at.x + 5 + dx, z_y + dy, z_color, alpha);
    }
}

/// How long a steam puff holds each row of its rise: one Full beat, so it
/// rises evenly.
const STEAM_ROW_MS: u64 = crate::anim::FULL_TICK_MS;
/// How long it holds each side of its wiggle, in whole beats.
const STEAM_WIGGLE_MS: u64 = 2 * crate::anim::FULL_TICK_MS;

fn plot_steam_puff(
    plot: &mut impl FnMut(u16, u16, Rgb, f32),
    spout: Point,
    phase: u64,
    inks: &Inks,
) {
    let rise = (phase / STEAM_ROW_MS) as u16;
    let alpha = 1.0 - phase as f32 / STEAM_CYCLE_MS as f32;
    if alpha < 0.15 {
        return;
    }
    let wiggle = if (phase / STEAM_WIGGLE_MS).is_multiple_of(2) {
        0
    } else {
        1
    };
    let px = spout.x + wiggle;
    let py = spout.y.saturating_sub(rise + 2);
    plot(px, py, inks.steam, alpha * 0.55);
}

/// The cell under planted foot `foot` ([`planted_foot`](super::planted_foot)) of a
/// walker whose top-left is `walker_top_left`, where its dust rises.
pub(crate) fn walking_dust_foot(walker_top_left: Point, foot: u64) -> Point {
    Point {
        x: walker_top_left.x + if foot == 0 { 6 } else { 1 },
        y: walker_top_left.y + WALKING_Y_OFF,
    }
}

fn plot_walking_dust(
    plot: &mut impl FnMut(u16, u16, Rgb, f32),
    walker_top_left: Point,
    foot: u64,
    inks: &Inks,
) {
    let cell = walking_dust_foot(walker_top_left, foot);
    plot(cell.x, cell.y, inks.dust, 0.45);
}

/// One floating heart for the "pet the wolf" interaction.
fn plot_pet_heart(plot: &mut impl FnMut(u16, u16, Rgb, f32), at: Point, phase_ms: u64) {
    let heart_color = Rgb {
        r: 255,
        g: 100,
        b: 100,
    };
    let t = phase_ms as f32 / HEART_LIFE_MS as f32;
    let rise = (t * 6.0) as u16;
    let alpha = 1.0 - t;
    if alpha < 0.05 {
        return;
    }
    let hy = at.y.saturating_sub(4 + rise);
    for dy in 0..2u16 {
        for ddx in 0..2u16 {
            plot(at.x + ddx, hy + dy, heart_color, alpha * 0.8);
        }
    }
}

/// One "running" bubble over a running gateway mascot, `rise` rows up.
fn plot_mascot_bubble(plot: &mut impl FnMut(u16, u16, Rgb, f32), at: Point, rise: u64) {
    let bubble = Rgb {
        r: 0xd6,
        g: 0xf2,
        b: 0xf8,
    };
    plot(at.x, at.y.saturating_sub(rise as u16), bubble, 1.0);
}

fn plot_requires_action_mark(
    plot: &mut impl FnMut(u16, u16, Rgb, f32),
    top_left: Point,
    inks: &Inks,
) {
    let fg = inks.requires_action;
    let by = top_left.y.saturating_sub(5) & !1u16;
    for (dx, dy) in REQUIRES_ACTION_MARK_1X.inked() {
        plot(top_left.x + 2 + dx, by + dy, fg, 1.0);
    }
}

/// `banner` on the base art, its pole beside the head mark at `brow`, ringed in
/// its line.
fn plot_subagent_banner(plot: &mut impl FnMut(u16, u16, Rgb, f32), brow: Point, banner: Banner) {
    let mut px = std::collections::BTreeMap::new();
    let width = BANNER_1X[0].len() as i32;
    for (row, line) in (-BANNER_1X_RISE..).zip(BANNER_1X) {
        for (col, key) in (-BANNER_1X_POLE_DX - width + 1..).zip(line.chars()) {
            let ink = match key {
                'l' => banner.ink.ramp(1),
                'b' => banner.ink,
                's' => banner.ink.ramp(BANNER_SHADE),
                'w' => WOOD,
                _ => continue,
            };
            px.insert((col, row), ink);
        }
    }
    for row in BANNER_1X.len() as i32 - BANNER_1X_RISE..BANNER_1X_FOOT {
        px.insert((-BANNER_1X_POLE_DX, row), WOOD);
    }
    for col in 1..=BANNER_1X_STRAP_LEN {
        px.insert((col - BANNER_1X_POLE_DX, BANNER_1X_FOOT - 2), LEATHER);
    }
    let (Some(x0), Some(x1), Some(y0), Some(y1)) = (
        px.keys().map(|&(x, _)| x).min(),
        px.keys().map(|&(x, _)| x).max(),
        px.keys().map(|&(_, y)| y).min(),
        px.keys().map(|&(_, y)| y).max(),
    ) else {
        return;
    };
    let around = (y0 - 1..=y1 + 1).flat_map(|y| (x0 - 1..=x1 + 1).map(move |x| (x, y)));
    let ring = crate::character::outline(around, |x, y| px.contains_key(&(x, y)));
    let cells = ring
        .map(|cell| (cell, banner.line))
        .chain(px.iter().map(|(&cell, &ink)| (cell, ink)));
    for ((dx, dy), c) in cells {
        let (x, y) = (i32::from(brow.x) + dx, i32::from(brow.y) + dy);
        if let (Ok(x), Ok(y)) = (u16::try_from(x), u16::try_from(y)) {
            plot(x, y, c, 1.0);
        }
    }
}
