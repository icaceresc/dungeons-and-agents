//! The [effects](crate::effects) riding on the display list's figures, drawn on the
//! figure's own art grid: a look authored at [`LOOK_DENSITY`] where the figure
//! is drawn there with a head to set it on or beside, the base art's z and requires-action
//! mark beside its head, else its [shared look](crate::effects::look), a
//! layout cell per art cell block. A look stays whole down to [`LOOK_SOLID`].

use crate::sprite::Rgb;
use crate::sprite::format::Density;

use crate::display::Span;
use crate::display::pen::Pen;
use crate::effects::look::{
    BANNER_SHADE, IRON, Inks, LEATHER, REQUIRES_ACTION_MARK_1X, SLEEP_Z_1X, SLEEP_Z_MAX_RISE, WOOD,
    WOOD_LIT, plot_effect, sleep_z_fade, walking_dust_foot,
};
use crate::effects::{Banner, Effect, EffectKind};
use crate::layout::chrome::{Glyph, REQUIRES_ACTION_MARK};

/// The density this module's own looks are drawn at.
const LOOK_DENSITY: Density = Density::new(4).expect("nonzero");

/// A point on the art grid, which a look may hang past the buffer's top or
/// west edge.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) struct ArtPoint {
    pub(crate) x: i32,
    pub(crate) y: i32,
}

/// A figure's head on its art grid, which its riders set their looks by.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum Head {
    /// The base art's: its frame's top row over the head mark's column.
    Base(ArtPoint),
    /// A dressed frame's: its crest, the top of its hair over the head mark's
    /// column, and its brow.
    Dressed { crest: ArtPoint, brow: Brow },
}

impl Head {
    /// The head of the frame `key` draws, its 1x art `base`, with its top-left
    /// at `at`: its mark's column, turned with the frame, a dressed frame's on
    /// its crest and its brow on its mark's row, the base art's on its top row.
    pub(crate) fn of(
        key: &crate::character::CharacterKey,
        base: &crate::pack::DenseFrame<'_>,
        at: crate::layout::Point,
    ) -> Option<Self> {
        let d = key.frame.density.get();
        let column = |x: u16, d: i32| {
            let x = i32::from(x);
            let frame_w = i32::from(base.logical.0) * d;
            i32::from(at.x) * d + if key.frame.flip_x { frame_w - 1 - x } else { x }
        };
        match key.dress.as_ref() {
            Some(dress) => {
                let d = i32::from(d);
                let x = column(dress.head.x, d);
                let row = |y: i32| ArtPoint {
                    x,
                    y: i32::from(at.y) * d + y,
                };
                Some(Head::Dressed {
                    crest: row(dress.crest),
                    brow: Brow {
                        at: row(i32::from(dress.head.y)),
                        reach: dress.reach,
                    },
                })
            }
            None if d == 1 => base.head.map(|m| {
                Head::Base(ArtPoint {
                    x: column(m.x, 1),
                    y: i32::from(at.y),
                })
            }),
            None => None,
        }
    }
}

/// A dressed head's brow on the art grid: its mark and the columns it is drawn
/// across there ([`Dress::reach`](crate::character::Dress::reach)), which a
/// banner beside the head stands clear of.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) struct Brow {
    pub(crate) at: ArtPoint,
    pub(crate) reach: (i32, i32),
}

/// One effect on the figure it rides on.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) struct Riding {
    pub(crate) effect: Effect,
    /// The figure's head. `None` where its frame marks none to float a look
    /// beside.
    pub(crate) head: Option<Head>,
    /// The figure's own grid.
    pub(crate) pen: Pen,
    /// The theme's colours its look is drawn in.
    pub(crate) inks: Inks,
}

impl Riding {
    /// The logical cells it paints, sorted with the `carrier` figure it rides
    /// on; `None` when it paints nothing this frame.
    pub(crate) fn span(&self, carrier: Span) -> Option<Span> {
        let d = i32::from(self.pen.density().get());
        let mut cells: Option<(i32, i32, i32, i32)> = None;
        self.look(&mut |at, size, _, _| {
            let (x1, y1) = (at.x + size - 1, at.y + size - 1);
            cells = Some(cells.map_or((at.x, at.y, x1, y1), |(a, b, c, e)| {
                (a.min(at.x), b.min(at.y), c.max(x1), e.max(y1))
            }));
        });
        let (x0, y0, x1, y1) = cells?;
        let cell = |a: i32| u16::try_from(a.max(0).div_euclid(d)).unwrap_or(u16::MAX);
        let span = Span {
            x0: cell(x0),
            x1: cell(x1),
            y0: cell(y0),
            y1: cell(y1),
            depth: carrier.depth,
            layer: carrier.layer,
        };
        Some(span)
    }

    /// Its look, as squares of art pixels: each top-left, side, colour and the
    /// share of it covered.
    pub(crate) fn look(&self, emit: &mut impl FnMut(ArtPoint, i32, Rgb, f32)) {
        let (e, inks) = (self.effect, &self.inks);
        let d = self.pen.density();
        match self.head {
            Some(Head::Dressed { crest, brow }) if d == LOOK_DENSITY => {
                return dense_look(e, (crest, brow), inks, emit);
            }
            Some(Head::Base(head)) if d == Density::ONE && base_look(e, head, inks, emit) => return,
            _ => {}
        }
        let d = i32::from(d.get());
        plot_effect(&e, inks, &mut |x, y, c, alpha| {
            let at = ArtPoint {
                x: i32::from(x) * d,
                y: i32::from(y) * d,
            };
            emit(at, d, c, (alpha / LOOK_SOLID).min(1.0));
        });
    }
}

/// A sleeping head's moon, a crescent rising off the side of the head and
/// drifting away.
const SLEEP_Z: Glyph = Glyph::new(&[
    "..###.", //
    ".####.", //
    "###...", //
    "###...", //
    ".####.", //
    "..###.", //
]);

/// Art columns from the head mark to the west edge of what floats beside the
/// head: clear of the hair, and of the badge centred over it.
const BESIDE_DX: i32 = 9;
/// Art rows from the hair's top down to the bottom of what floats beside it.
const BESIDE_DY: i32 = 5;
/// The opacity down to which a look stays whole: a dither through a glyph a
/// stroke or two wide breaks it, so it dissolves only on its way out.
const LOOK_SOLID: f32 = 0.3;
/// Art rows a rising z drifts one column away from the head.
const SLEEP_Z_DRIFT: i32 = 4;

/// The walking dust's speckle, kicked up round a foot's sole.
const DUST: Glyph = Glyph::new(&[
    "..#.#..", //
    ".#.#.#.", //
    "#.#.#.#", //
]);

/// Columns from the base art's head to the west edge of what floats beside it:
/// past the head, and the badge centred over it.
const BESIDE_DX_1X: i32 = 5;
/// Rows from the head's top down to the bottom of what floats beside it.
const BESIDE_DY_1X: i32 = 1;

/// `e`'s look on the base art, from its rider's `head`, where the base art
/// has a look of its own: whether it drew one.
fn base_look(
    e: Effect,
    head: ArtPoint,
    inks: &Inks,
    emit: &mut impl FnMut(ArtPoint, i32, Rgb, f32),
) -> bool {
    match e.kind {
        EffectKind::SleepZ => {
            if let Some((alpha, t)) = sleep_z_fade(e.phase) {
                let rise = (t * f32::from(SLEEP_Z_MAX_RISE)) as i32;
                let top = head.y + BESIDE_DY_1X - i32::from(SLEEP_Z_1X.height()) - rise;
                let coverage = (alpha / LOOK_SOLID).min(1.0);
                stamp(
                    SLEEP_Z_1X,
                    head.x + BESIDE_DX_1X,
                    top,
                    emit,
                    (inks.sleep_z, coverage),
                );
            }
            true
        }
        EffectKind::RequiresActionMark => {
            let top = head.y + BESIDE_DY_1X - i32::from(REQUIRES_ACTION_MARK_1X.height());
            stamp(
                REQUIRES_ACTION_MARK_1X,
                head.x + BESIDE_DX_1X,
                top,
                emit,
                (inks.requires_action, 1.0),
            );
            true
        }
        _ => false,
    }
}

/// `e`'s look at [`LOOK_DENSITY`], from its rider's crest, `head`, and its `brow`.
fn dense_look(
    e: Effect,
    (head, brow): (ArtPoint, Brow),
    inks: &Inks,
    emit: &mut impl FnMut(ArtPoint, i32, Rgb, f32),
) {
    let d = i32::from(LOOK_DENSITY.get());
    match e.kind {
        EffectKind::SleepZ => {
            let Some((alpha, t)) = sleep_z_fade(e.phase) else {
                return;
            };
            let rise = (t * f32::from(SLEEP_Z_MAX_RISE) * d as f32) as i32;
            let x = head.x + BESIDE_DX + rise / SLEEP_Z_DRIFT;
            let top = head.y + BESIDE_DY - i32::from(SLEEP_Z.height()) - rise;
            let coverage = (alpha / LOOK_SOLID).min(1.0);
            stamp(SLEEP_Z, x, top, emit, (inks.sleep_z, coverage));
        }
        EffectKind::RequiresActionMark => {
            let top = head.y + BESIDE_DY - i32::from(REQUIRES_ACTION_MARK.height());
            stamp(
                REQUIRES_ACTION_MARK,
                head.x + BESIDE_DX,
                top,
                emit,
                (inks.requires_action, 1.0),
            );
        }
        EffectKind::WalkingDust => {
            let foot = walking_dust_foot(e.at, e.phase);
            let x = i32::from(foot.x) * d + d / 2 - i32::from(DUST.width()) / 2;
            let y = i32::from(foot.y) * d - 1;
            stamp(DUST, x, y, emit, (inks.dust, 1.0));
        }
        EffectKind::SubagentBanner(banner) => banner_look(banner, head, brow, emit),
        // A creature's riders have no head, so `look` plots them as the classic
        // does; steam isn't drawn here.
        EffectKind::PetHeart | EffectKind::SteamPuff | EffectKind::MascotBubble => {}
    }
}

/// A subagent's banner on the 4x look's art grid, its pole the last two
/// columns. Cloth: `l` lit, `b` base, `s` shade, the fold a shade column that
/// steps over once down the cloth. Wood: `O` lit, `D` shaded. Iron: `i`, `I`
/// lit.
const BANNER: [&str; 17] = [
    "..........II",
    "........iIIi",
    "..........ii",
    "iOOOOOOOOOOD",
    "iDDDDDDDDDOD",
    "..llllllllOD",
    "..lbbsbbbsOD",
    "..lbbsbbbsOD",
    "..lbbsbbbsOD",
    "..lbbbsbbsOD",
    "..lbbbsbbsOD",
    "..lbbsbbbsOD",
    "..lbbsbbbsOD",
    "..lbbs.bbsOD",
    "...bbs.bs.OD",
    "...bs..bs.OD",
    "....s..s..OD",
];
/// The pole's width in [`BANNER`]'s last columns.
const POLE_W: i32 = 2;
/// Art rows the banner's top stands over the crest: its iron tip over the hair.
const BANNER_RISE: i32 = 9;
/// Art columns between the head's outline and the pole, whose own ring takes
/// the one.
const BANNER_GAP: i32 = 3;
/// Art rows from the brow down to where the pole ends: the shoulder.
const SHOULDER_DROP: i32 = 15;
/// The strap that holds the pole to the shoulder: rows, and its columns on
/// the first row, each row one column longer toward the body.
const STRAP_ROWS: i32 = 3;
const STRAP_LEN: i32 = 4;
/// `banner` carried on its figure's back: its pole stands beside the head's
/// west, whichever way the figure faces, clear of every hair and helm, and ends
/// at a strap on the shoulder. Ringed in its line as a dressed figure is.
pub(crate) fn banner_look(
    banner: Banner,
    crest: ArtPoint,
    brow: Brow,
    emit: &mut impl FnMut(ArtPoint, i32, Rgb, f32),
) {
    let west = if banner.flip {
        brow.reach.1
    } else {
        brow.reach.0
    };
    let width = BANNER[0].len() as i32;
    let pole = brow.at.x - west - BANNER_GAP;
    let (left, top) = (pole + POLE_W - width, crest.y - BANNER_RISE);
    let mut px = std::collections::BTreeMap::new();
    for (row, line) in (top..).zip(BANNER) {
        for (col, key) in (left..).zip(line.chars()) {
            let ink = match key {
                'b' => banner.ink,
                'l' => banner.ink.ramp(1),
                's' => banner.ink.ramp(BANNER_SHADE),
                'O' => WOOD_LIT,
                'D' => WOOD,
                'i' => IRON,
                'I' => IRON.ramp(1),
                _ => continue,
            };
            px.insert((col, row), ink);
        }
    }
    let foot = brow.at.y + SHOULDER_DROP;
    for row in top + BANNER.len() as i32..=foot {
        px.insert((pole, row), WOOD_LIT);
        px.insert((pole + 1, row), WOOD);
    }
    for k in 0..STRAP_ROWS {
        for col in 0..STRAP_LEN + k {
            px.insert((pole + POLE_W + col, foot - STRAP_ROWS + 1 + k), LEATHER);
        }
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
    for (x, y) in crate::character::outline(around, |x, y| px.contains_key(&(x, y))) {
        emit(ArtPoint { x, y }, 1, banner.line, 1.0);
    }
    for (&(x, y), &ink) in &px {
        emit(ArtPoint { x, y }, 1, ink, 1.0);
    }
}

/// Emit each of `glyph`'s inked cells from `(x, y)` in colour `c` at `coverage`.
fn stamp(
    glyph: Glyph,
    x: i32,
    y: i32,
    emit: &mut impl FnMut(ArtPoint, i32, Rgb, f32),
    (c, coverage): (Rgb, f32),
) {
    for (dx, dy) in glyph.inked() {
        let at = ArtPoint {
            x: x + i32::from(dx),
            y: y + i32::from(dy),
        };
        emit(at, 1, c, coverage);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::render_scale::RenderScale;

    /// A banner's pole, tip and strap are the pack's own wood, iron and leather.
    #[test]
    fn banner_materials_are_the_packs() {
        let pack = crate::pack::test_office();
        for (key, ink) in [('O', WOOD_LIT), ('D', WOOD), ('Σ', IRON), ('г', LEATHER)] {
            assert_eq!(pack.palette().get(key).flatten(), Some(ink), "key {key:?}");
        }
    }

    /// A banner stands over the crest and clear of the head's west side,
    /// whichever way its figure is turned: where the figure is mirrored, the
    /// head's screen west is its east reach.
    #[test]
    fn a_banner_stands_clear_of_the_head_it_is_carried_beside() {
        let theme = crate::theme::theme_by_name("normal").expect("theme");
        let line = Rgb { r: 1, g: 1, b: 1 };
        let at = ArtPoint { x: 40, y: 40 };
        let crest = ArtPoint { x: 40, y: 30 };
        let reach = (10, 6);
        for flip in [false, true] {
            let banner = Banner {
                ink: Rgb {
                    r: 0xa8,
                    g: 0x32,
                    b: 0x32,
                },
                line,
                flip,
            };
            let riding = Riding {
                effect: crate::effects::subagent_banner(
                    crate::layout::Point { x: 10, y: 10 },
                    banner,
                ),
                head: Some(Head::Dressed {
                    crest,
                    brow: Brow { at, reach },
                }),
                pen: Pen::new(RenderScale::new(4).expect("nonzero"), LOOK_DENSITY)
                    .expect("a density divides itself"),
                inks: Inks::of(theme),
            };
            let mut drawn = Vec::new();
            riding.look(&mut |p, _, c, _| {
                if c != line {
                    drawn.push(p);
                }
            });
            let west = if flip { reach.1 } else { reach.0 };
            let beside_head = drawn.iter().filter(|p| p.y < at.y);
            assert!(
                beside_head.clone().all(|p| p.x < at.x - west),
                "flip {flip}: the banner leans on the head"
            );
            assert_eq!(
                drawn.iter().map(|p| p.y).min(),
                Some(crest.y - BANNER_RISE),
                "flip {flip}: the tip is off the crest"
            );
        }
    }
}
