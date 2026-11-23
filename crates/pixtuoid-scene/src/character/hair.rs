//! Per-agent hairstyles: which of the pack's `[hairstyles]` an agent wears, the
//! class that style makes it, and a character frame dressed in it, its layers
//! laid mark on mark over the frame's head. A frame is dressed only at a
//! density of 2 and up ([`dress_for`]), so the classic 1x art never is.

use crate::pack::Hairstyle;
use crate::pack::OfficeArt;
use crate::pack::Piece;
use crate::sprite::format::Density;
use crate::sprite::{Frame, HeadMark, Pixel, Rgb, Sprite};
use pixtuoid_core::id::{fnv1a, splitmix64};
use pixtuoid_core::{AgentId, AgentSlot};
use strum::VariantArray as _;

/// Separates the pick's seed from the other per-agent draws that finalize the
/// same id through `splitmix64` (`physics`, `pose::pure`), so the style is no
/// function of theirs.
const HAIRSTYLE_SALT: u64 = 0x6861_6972_7374_796c;

/// The name of the style `agent` wears: its role's ([`Role::style`]) where its
/// working directory names a role and the pack draws that style, else the
/// style its id scores highest ([`rendezvous`]). It is picked by name, whatever
/// the density, so an agent keeps its style when the renderer lands on another.
fn pick<'p>(pack: &'p OfficeArt, agent: &AgentSlot) -> Option<&'p str> {
    let styles = || pack.inner().hairstyles().map(Hairstyle::name);
    let role = Role::of(agent).map(Role::style);
    role.and_then(|style| styles().find(|&name| name == style))
        .or_else(|| rendezvous(pack, agent.agent_id))
}

/// The style `agent`'s id scores highest under rendezvous hashing, so adding a
/// style to a pack moves only the agents that now prefer it.
fn rendezvous(pack: &OfficeArt, agent: AgentId) -> Option<&str> {
    let seed = splitmix64(splitmix64(agent.raw() ^ HAIRSTYLE_SALT));
    pack.inner()
        .hairstyles()
        .map(Hairstyle::name)
        .max_by_key(|name| splitmix64(seed ^ fnv1a(name.bytes().map(u64::from))))
}

/// What joins an Orca coworker's project and role in its title: the Orca
/// adapter's `Agent.compose` (icaceresc/pixtuoid-orca-windows, `oficina.py`).
const ROLE_SEPARATOR: &str = " \u{b7} ";

/// A coworker's role in an Orca office. The Orca adapter reports each coworker
/// through hooks and writes its role into the title it makes the basename of
/// the coworker's working directory, the one field every source carries:
/// `<project> · <role>` for a coworker of its own, `<role> · <project>` for one
/// under another, the role's word last in its part (`claude worker`, `Explore
/// subagent`) or first (`worker of antigravity`). A title with no separator
/// names none, as a directory outside Orca does.
#[derive(Debug, Clone, Copy, PartialEq, Eq, strum::VariantArray)]
enum Role {
    /// An Orca bot's own session: the owner's Strategic Companion.
    Companion,
    /// A session that dispatches workers.
    Orchestrator,
    /// A session another dispatched, at any depth.
    Worker,
    /// A subagent a session started.
    Subagent,
    /// A top-level session with none of the roles above.
    Agent,
}

/// An Orca coworker's title, read: its role, and its project, the rest of it.
struct Titled {
    role: Role,
    project: String,
}

impl Titled {
    /// `agent`'s title, where its working directory's basename is one. A
    /// child's title leads with its role and a top-level one ends with it, so
    /// that end is read first: a project named like a role never stands in for
    /// one.
    fn of(agent: &AgentSlot) -> Option<Self> {
        let title = pixtuoid_core::remote::cwd_basename(&agent.cwd)?;
        let parts: Vec<&str> = title.split(ROLE_SEPARATOR).collect();
        let last = parts.len().checked_sub(1).filter(|&last| last > 0)?;
        let ends = if agent.parent_id.is_some() {
            [0, last]
        } else {
            [last, 0]
        };
        let (at, role) = ends
            .into_iter()
            .find_map(|at| Role::of_part(parts[at]).map(|role| (at, role)))?;
        let rest: Vec<&str> = (parts.iter().enumerate())
            .filter(|&(i, _)| i != at)
            .map(|(_, part)| *part)
            .collect();
        Some(Self {
            role,
            project: rest.join(ROLE_SEPARATOR),
        })
    }
}

/// The project `agent` works in, as its outfit keys it: an Orca coworker's
/// title less its role, so a project's orchestrator, workers and subagents
/// match, else its working directory's basename.
pub(crate) fn project_of(agent: &AgentSlot) -> Option<String> {
    Titled::of(agent)
        .map(|titled| titled.project)
        .or_else(|| pixtuoid_core::remote::cwd_basename(&agent.cwd))
}

/// Whether `agent` is an Orca bot's own session, the owner's companion.
pub(crate) fn is_companion(agent: &AgentSlot) -> bool {
    Role::of(agent) == Some(Role::Companion)
}

impl Role {
    /// The role `agent`'s title names, if any ([`Titled::of`]).
    fn of(agent: &AgentSlot) -> Option<Self> {
        Titled::of(agent).map(|titled| titled.role)
    }

    /// The role `part` of a title names by its last word or, failing that, its
    /// first.
    fn of_part(part: &str) -> Option<Self> {
        let mut words = part.split_whitespace();
        let first = words.next()?;
        let last = words.next_back().unwrap_or(first);
        Self::of_word(last).or_else(|| Self::of_word(first))
    }

    fn of_word(word: &str) -> Option<Self> {
        Self::VARIANTS
            .iter()
            .copied()
            .find(|role| role.word() == word)
    }

    /// Its word in a title.
    fn word(self) -> &'static str {
        match self {
            Self::Companion => "companion",
            Self::Orchestrator => "orchestrator",
            Self::Worker => "worker",
            Self::Subagent => "subagent",
            Self::Agent => "agent",
        }
    }

    /// The style of its class ([`Class::of_style`]): the companion is a mage,
    /// an orchestrator a knight, a worker a berserker, and a subagent or a lone
    /// session a ranger.
    fn style(self) -> &'static str {
        match self {
            Self::Companion => "mage",
            Self::Orchestrator => "knight",
            Self::Worker => "berserker",
            Self::Subagent | Self::Agent => "ranger",
        }
    }
}

/// An adventurer's class. The style an agent wears names it, so the class an
/// agent fights as is the one it is seen dressed as.
#[derive(Debug, Clone, Copy, PartialEq, Eq, strum::VariantArray)]
pub(crate) enum Class {
    Mage,
    Knight,
    Ranger,
    Berserker,
}

impl Class {
    /// The class the style `name` marks. Any other style is a knight's, and so
    /// is none.
    fn of_style(name: Option<&str>) -> Self {
        match name {
            Some("mage") => Self::Mage,
            Some("ranger") => Self::Ranger,
            Some("berserker") => Self::Berserker,
            _ => Self::Knight,
        }
    }

    /// The class `agent` is in `pack`: the one its style names.
    pub(crate) fn of(pack: &OfficeArt, agent: &AgentSlot) -> Self {
        Self::of_style(pick(pack, agent))
    }

    /// The attack it plays at work, where an office worker types, seen from
    /// the front; a seat facing away turns it to its back view.
    pub(crate) fn attack(self) -> Piece {
        match self {
            Self::Mage => Piece::AttackMage,
            Self::Knight => Piece::AttackKnight,
            Self::Ranger => Piece::AttackRanger,
            Self::Berserker => Piece::AttackBerserker,
        }
    }
}

/// How a character frame is dressed: its head, the style its agent wears at
/// its density where the pack draws that style there, and where the dressed
/// figure's top lands.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub(crate) struct Dress {
    pub(crate) head: HeadMark,
    pub(crate) style: Option<String>,
    /// The dressed figure's topmost drawn row, counted from the frame's top:
    /// negative where it rises over it.
    pub(crate) crest: i32,
    /// Art columns the dressed head spans west and east of its mark's column,
    /// on its mark's row: what a banner beside the head stands clear of.
    pub(crate) reach: (i32, i32),
}

/// The [`Dress`] of `body`, frame `head`'s art at `density`, for `agent`:
/// `None` at 1x or on an unmarked frame, which is drawn as it is.
pub(crate) fn dress_for(
    pack: &OfficeArt,
    agent: &AgentSlot,
    body: &Frame,
    head: Option<HeadMark>,
    density: Density,
) -> Option<Dress> {
    let head = dressed_head(head, density)?;
    let style = pick(pack, agent).and_then(|name| pack.inner().hairstyle(name, density));
    Some(Dress::of(body, head, style))
}

/// The most any agent's [`Dress`] of `art` (as [`dress_for`] takes it) rises
/// over it: the headroom a canvas needs to hold every agent's figure uncut.
pub(crate) fn max_rise(pack: &OfficeArt, art: &crate::pack::DenseFrame<'_>) -> u16 {
    let Some(head) = dressed_head(art.head, art.density) else {
        return 0;
    };
    pack.inner()
        .hairstyles()
        .filter(|style| style.density() == art.density)
        .map(Some)
        .chain([None])
        .map(|style| Dress::of(art.frame, head, style).rise())
        .max()
        .unwrap_or(0)
}

/// `head`, where a frame at `density` is dressed at all.
fn dressed_head(head: Option<HeadMark>, density: Density) -> Option<HeadMark> {
    head.filter(|_| density.get() > 1)
}

impl Dress {
    /// `body`, its head `head`, dressed in `style`.
    pub(crate) fn of(body: &Frame, head: HeadMark, style: Option<&Hairstyle>) -> Self {
        Dress {
            head,
            style: style.map(|s| s.name().to_owned()),
            crest: crest(body, head, style),
            reach: reach(body, head, style),
        }
    }

    /// How many art rows the dressed frame rises over the frame as drawn.
    pub(crate) fn rise(&self) -> u16 {
        u16::try_from((-self.crest).max(0)).unwrap_or(0)
    }
}

/// The first row of `f` holding an opaque pixel.
fn opaque_top(f: &Frame) -> Option<u16> {
    (0..f.height()).find(|&y| (0..f.width()).any(|x| f.get(x, y).copied().flatten().is_some()))
}

/// `body`, then `style`'s layers for its head's view, each with its offset on
/// the body.
fn laid<'a>(
    body: &'a Frame,
    head: HeadMark,
    style: Option<&'a Hairstyle>,
) -> impl Iterator<Item = (&'a Frame, i32, i32)> {
    let layers = style
        .and_then(|s| s.layers(head.view))
        .into_iter()
        .flat_map(|layers| [layers.behind(), layers.over()].into_iter().flatten())
        .filter_map(move |layer| layer.laid_on(head));
    std::iter::once((body, 0, 0)).chain(layers)
}

/// [`Dress::crest`] of `body` dressed in `style`: its hair's top or its own,
/// and the outline's row above that.
fn crest(body: &Frame, head: HeadMark, style: Option<&Hairstyle>) -> i32 {
    let top = laid(body, head, style)
        .filter_map(|(f, _, dy)| Some(dy + i32::from(opaque_top(f)?)))
        .min();
    top.map_or(0, |top| top - 1)
}

/// [`Dress::reach`] of `body` dressed in `style`, as far as the body's sides,
/// where [`dress`] cuts a layer. Fitted rather than one size, so a banner's pole
/// stands clear of every hair and helm: a mop never reaches it, a crop leaves
/// no gap to it.
fn reach(body: &Frame, head: HeadMark, style: Option<&Hairstyle>) -> (i32, i32) {
    let (row, mark) = (i32::from(head.y), i32::from(head.x));
    let xs = laid(body, head, style).flat_map(|(f, dx, dy)| {
        let y = u16::try_from(row - dy).ok().filter(|&y| y < f.height());
        y.into_iter().flat_map(move |y| {
            (0..f.width())
                .filter(move |&x| f.get(x, y).copied().flatten().is_some())
                .map(move |x| i32::from(x) + dx)
        })
    });
    let (west, east) = xs
        .filter(|x| (0..i32::from(body.width())).contains(x))
        .fold((mark, mark), |(lo, hi), x| (lo.min(x), hi.max(x)));
    (mark - west, east - mark)
}

/// `body` dressed as `dress` says: `style`'s behind layer for its head's view,
/// the body, the over layer, then one `outline` round the union, so no line runs
/// between hair and face. A bare head, with no style or none for its view, gets
/// the outline alone. The layers take the body's own recolor `overrides`, so the
/// hair wears the agent's colour. The frame grows [`Dress::rise`] rows upward;
/// its width is the body's.
pub(crate) fn dress(
    body: &Frame,
    dress: &Dress,
    style: Option<&Hairstyle>,
    overrides: &[(char, Pixel)],
    line: Rgb,
) -> Frame {
    let (head, up) = (dress.head, dress.rise());
    let layers = style.and_then(|s| s.layers(head.view));
    let (w, h) = (body.width(), body.height().saturating_add(up));
    let mut px: Vec<Pixel> = vec![None; usize::from(w) * usize::from(h)];
    let mut lay = |f: &Frame, dx: i32, dy: i32| {
        for y in 0..f.height() {
            for x in 0..f.width() {
                let Some(c) = f.get(x, y).copied().flatten() else {
                    continue;
                };
                let (tx, ty) = (i32::from(x) + dx, i32::from(y) + dy + i32::from(up));
                if let (Ok(tx), Ok(ty)) = (u16::try_from(tx), u16::try_from(ty))
                    && tx < w
                    && ty < h
                {
                    px[usize::from(ty) * usize::from(w) + usize::from(tx)] = Some(c);
                }
            }
        }
    };
    let dressed = |layer: Option<&Sprite>| {
        let sprite = layer?;
        let (_, dx, dy) = sprite.laid_on(head)?;
        Some((sprite.recolorable_at(0).recolored(overrides), dx, dy))
    };
    if let Some((f, dx, dy)) = dressed(layers.and_then(|l| l.behind())) {
        lay(&f, dx, dy);
    }
    lay(body, 0, 0);
    if let Some((f, dx, dy)) = dressed(layers.and_then(|l| l.over())) {
        lay(&f, dx, dy);
    }
    let (w_i, h_i) = (i32::from(w), i32::from(h));
    let idx = |x: i32, y: i32| y as usize * usize::from(w) + x as usize;
    let opaque = |px: &[Pixel], x: i32, y: i32| {
        (0..w_i).contains(&x) && (0..h_i).contains(&y) && px[idx(x, y)].is_some()
    };
    let cells = || (0..h_i).flat_map(move |y| (0..w_i).map(move |x| (x, y)));
    let edge: Vec<usize> = outline(cells(), |x, y| opaque(&px, x, y))
        .map(|(x, y)| idx(x, y))
        .collect();
    for i in edge {
        px[i] = Some(line);
    }
    // A gap the line closes to one pixel takes the line too: a style laid
    // on a body it was not drawn against can leave one between chin and
    // hair, and no author can see it to close it.
    let holes: Vec<usize> = cells()
        .filter(|&(x, y)| {
            !opaque(&px, x, y) && SIDES.iter().all(|(dx, dy)| opaque(&px, x + dx, y + dy))
        })
        .map(|(x, y)| idx(x, y))
        .collect();
    for i in holes {
        px[i] = Some(line);
    }
    Frame::from_pixels(w, h, px)
}

/// A cell's four sides, as the steps to its neighbours there.
const SIDES: [(i32, i32); 4] = [(1, 0), (-1, 0), (0, 1), (0, -1)];

/// The cells of `area` a shape leaves empty but touches along a side, the
/// shape being the cells `opaque` holds: where one line round it runs, as a
/// dressed figure's and a banner's do.
pub(crate) fn outline(
    area: impl Iterator<Item = (i32, i32)>,
    opaque: impl Fn(i32, i32) -> bool,
) -> impl Iterator<Item = (i32, i32)> {
    area.filter(move |&(x, y)| !opaque(x, y) && SIDES.iter().any(|(dx, dy)| opaque(x + dx, y + dy)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::display::pen::test_density;
    use crate::pack::validate::PieceKind;
    use crate::pack::{Piece, load_filled_pack};

    const H: Rgb = Rgb {
        r: 200,
        g: 100,
        b: 50,
    };
    const S: Rgb = Rgb {
        r: 240,
        g: 192,
        b: 160,
    };
    const LINE: Rgb = Rgb { r: 1, g: 1, b: 1 };
    const TWO: Density = test_density(2);

    /// A pack of `body` marked `head` (the `head.front` mark's column and row),
    /// outlined, and the styles `styles` at 2x, each a front-view over layer of
    /// one pixel a row above its mark.
    fn pack_of(body: &str, head: (u16, u16), styles: &[&str]) -> OfficeArt {
        let mut toml = String::from(
            "[palette]\n\".\"=\"transparent\"\n\"H\"=\"#c86432\"\n\"S\"=\"#f0c0a0\"\n\
             \"k\"=\"#010101\"\n[characters]\noutline=\"k\"\n\
             [animations.seated]\nframes=[\"b.sprite\"]\nframe_ms=100\n",
        );
        for s in styles {
            toml.push_str(&format!(
                "[hairstyles.\"{s}@2x\"]\nfront={{ over=\"o.sprite\" }}\n"
            ));
        }
        let body = format!("@frame 0\n@mark head.front {} {}\n{body}", head.0, head.1);
        crate::pack::test_office_with(
            &toml,
            &[
                ("b.sprite", body.as_str()),
                ("o.sprite", "@frame 0\n@mark head.front 0 1\nH\n. \n"),
            ],
        )
    }

    /// The one-skin-pixel body the tests dress.
    const BODY: &str = ". . .\n. . .\n. S .\n. . .\n";

    /// An idle agent of id `agent`, working in a directory outside Orca.
    fn slot(agent: AgentId) -> AgentSlot {
        crate::character::test_support::make_slot(agent, pixtuoid_core::state::ActivityState::Idle)
    }

    /// An agent working in `cwd`, a child when `child`.
    fn in_cwd(cwd: &str, child: bool) -> AgentSlot {
        AgentSlot {
            cwd: std::sync::Arc::from(std::path::Path::new(cwd)),
            parent_id: child.then(|| AgentId::from_parts("claude-code", "lead")),
            ..slot(AgentId::from_parts("claude-code", cwd))
        }
    }

    /// `pack`'s body dressed as it would be for `agent` at 2x.
    fn dressed(pack: &OfficeArt, agent: AgentId) -> (Dress, Frame) {
        let sprite = pack.piece(Piece::Seated);
        let body = sprite.first();
        let dress =
            dress_for(pack, &slot(agent), body, sprite.head(0), TWO).expect("a marked 2x frame");
        let style = dress
            .style
            .as_deref()
            .and_then(|n| pack.inner().hairstyle(n, TWO));
        let f = super::dress(
            body,
            &dress,
            style,
            &[('H', Some(H))],
            pack.inner().character_outline(),
        );
        (dress, f)
    }

    #[test]
    fn a_pick_is_stable_and_adding_a_style_only_moves_who_prefers_it() {
        let few = pack_of(BODY, (1, 0), &["mop", "bun", "crop"]);
        let more = pack_of(BODY, (1, 0), &["mop", "bun", "crop", "curls"]);
        let mut moved = 0;
        for i in 0..200u64 {
            let id = AgentId::from_parts("claude-code", &i.to_string());
            let before = rendezvous(&few, id).expect("a style");
            assert_eq!(rendezvous(&few, id), Some(before), "stable");
            let after = rendezvous(&more, id).expect("a style");
            if after != before {
                assert_eq!(after, "curls", "an agent only ever moves to the new style");
                moved += 1;
            }
        }
        assert!(
            (20..=80).contains(&moved),
            "about a quarter move to the new style: {moved}"
        );
    }

    /// Each class's style names it; any other style, and none, is a knight's.
    #[test]
    fn a_style_names_its_class_and_any_other_is_a_knight() {
        for (style, class) in [
            (Some("mage"), Class::Mage),
            (Some("knight"), Class::Knight),
            (Some("ranger"), Class::Ranger),
            (Some("berserker"), Class::Berserker),
            (Some("knight_helm"), Class::Knight),
            (Some("mop"), Class::Knight),
            (None, Class::Knight),
        ] {
            assert_eq!(Class::of_style(style), class, "{style:?}");
        }
    }

    /// An agent's class is the one its own style names, so a pack of the four
    /// classes' styles fields every class, each agent always the same one.
    #[test]
    fn an_agent_is_the_class_its_style_names() {
        let pack = pack_of(BODY, (1, 0), &["mage", "knight", "ranger", "berserker"]);
        let mut seen = Vec::new();
        for i in 0..64u64 {
            let agent = slot(AgentId::from_parts("claude-code", &i.to_string()));
            let class = Class::of(&pack, &agent);
            assert_eq!(class, Class::of_style(pick(&pack, &agent)));
            assert_eq!(Class::of(&pack, &agent), class, "stable");
            if !seen.contains(&class) {
                seen.push(class);
            }
        }
        assert_eq!(
            seen.len(),
            Class::VARIANTS.len(),
            "every class takes the field"
        );
    }

    /// An Orca coworker's title names its role at the end its place leads
    /// with: a child's first, a top-level one's last, the other end then.
    #[test]
    fn a_title_names_its_role_at_the_end_its_place_reads_first() {
        for (cwd, child, role) in [
            ("/w/my-repo · orchestrator", false, Some(Role::Orchestrator)),
            ("/w/punky · companion", false, Some(Role::Companion)),
            ("/w/my-repo · agent", false, Some(Role::Agent)),
            ("/w/worker · my-repo", true, Some(Role::Worker)),
            ("/w/claude worker · my-repo", true, Some(Role::Worker)),
            ("/w/Explore subagent · my-repo", true, Some(Role::Subagent)),
            ("/w/subagent · my-repo", true, Some(Role::Subagent)),
            // A worker whose dispatcher Pixtuoid cannot draw it under is a root.
            (
                "/w/worker of antigravity · my-repo",
                false,
                Some(Role::Worker),
            ),
            // Projects named like a role.
            ("/w/worker · orchestrator", false, Some(Role::Orchestrator)),
            ("/w/worker · orchestrator", true, Some(Role::Worker)),
            ("/w/worker", false, None),
            ("/w/my-repo", false, None),
            ("/w/my-repo · reviewer", false, None),
        ] {
            assert_eq!(
                Role::of(&in_cwd(cwd, child)),
                role,
                "{cwd} (child: {child})"
            );
        }
    }

    /// A title's project is the title less its role; a folder outside Orca is
    /// its own project.
    #[test]
    fn a_titles_project_is_the_title_less_its_role() {
        for (cwd, child, project) in [
            ("/w/my-repo · orchestrator", false, "my-repo"),
            ("/w/claude worker · my-repo", true, "my-repo"),
            ("/w/worker of antigravity · my-repo", false, "my-repo"),
            ("/w/Explore subagent · my-repo", true, "my-repo"),
            ("/w/my-repo", false, "my-repo"),
            ("/w/my-repo · reviewer", false, "my-repo · reviewer"),
        ] {
            assert_eq!(
                project_of(&in_cwd(cwd, child)).as_deref(),
                Some(project),
                "{cwd}"
            );
        }
    }

    /// A role wears its class's style; no role, or a pack without that style,
    /// keeps the style the agent's id picks.
    #[test]
    fn a_role_wears_its_class_and_no_role_keeps_the_hashed_style() {
        let classes = pack_of(BODY, (1, 0), &["mage", "knight", "ranger", "berserker"]);
        for (cwd, child, class) in [
            ("/w/punky · companion", false, Class::Mage),
            ("/w/my-repo · orchestrator", false, Class::Knight),
            ("/w/worker · my-repo", true, Class::Berserker),
            ("/w/Explore subagent · my-repo", true, Class::Ranger),
            ("/w/my-repo · agent", false, Class::Ranger),
        ] {
            assert_eq!(Class::of(&classes, &in_cwd(cwd, child)), class, "{cwd}");
        }
        let plain = in_cwd("/w/my-repo", false);
        assert_eq!(pick(&classes, &plain), rendezvous(&classes, plain.agent_id));
        let modern = pack_of(BODY, (1, 0), &["mop", "bun"]);
        let worker = in_cwd("/w/worker · my-repo", true);
        assert_eq!(pick(&modern, &worker), rendezvous(&modern, worker.agent_id));
    }

    /// Each class attacks in a pose of its own, a character's, which loops on
    /// the beat as the typist's does.
    #[test]
    fn each_class_attacks_in_a_looping_character_pose_of_its_own() {
        let attacks: std::collections::HashSet<Piece> =
            Class::VARIANTS.iter().map(|c| c.attack()).collect();
        assert_eq!(attacks.len(), Class::VARIANTS.len());
        for attack in attacks {
            assert_eq!(attack.kind(), PieceKind::Character, "{}", attack.name());
            assert_eq!(attack.min_frames(), Piece::Typing.min_frames());
        }
    }

    #[test]
    fn a_frame_is_dressed_only_at_2x_and_up_and_where_it_marks_a_head() {
        let pack = pack_of(BODY, (1, 0), &["mop"]);
        let sprite = pack.piece(Piece::Seated);
        let body = sprite.first();
        let agent = &slot(AgentId::from_parts("x", "y"));
        assert!(dress_for(&pack, agent, body, sprite.head(0), Density::ONE).is_none());
        assert!(dress_for(&pack, agent, body, None, TWO).is_none());
        let four = test_density(4);
        let bare = dress_for(&pack, agent, body, sprite.head(0), four).expect("marked at 4x");
        assert_eq!(bare.style, None, "no style at 4x: the head is bare");
    }

    #[test]
    fn a_dressed_frame_lays_the_hair_mark_on_mark_and_outlines_the_union() {
        let pack = pack_of(BODY, (1, 0), &["mop"]);
        let (dress, f) = dressed(&pack, AgentId::from_parts("x", "y"));
        // The layer's pixel sits a row above its mark, so above the body's top:
        // the frame rises a row for the hair and one more for its outline.
        assert_eq!(dress.rise(), 2);
        assert_eq!((f.width(), f.height()), (3, 6));
        let at = |x, y| f.get(x, y).copied().flatten();
        assert_eq!(
            at(1, 1),
            Some(H),
            "the hair, in the agent's colour, over the mark"
        );
        assert_eq!(at(1, 0), Some(LINE), "the outline above the hair");
        assert_eq!(at(0, 1), Some(LINE), "and beside it");
        assert_eq!(at(1, 4), Some(S), "the body, moved down with it");
        assert_eq!(
            at(1, 3),
            Some(LINE),
            "one outline round hair and body alike"
        );
    }

    /// A reach spans the head as dressed across its mark's row, the hair as
    /// well as the skin, as far as the body's sides, where `dress` cuts a
    /// layer; a row the mark is not on counts for nothing.
    #[test]
    fn a_reach_spans_the_dressed_head_across_its_marks_row() {
        let pack = crate::pack::test_office_with(
            "[palette]\n\".\"=\"transparent\"\n\"H\"=\"#c86432\"\n\"S\"=\"#f0c0a0\"\n\
             \"k\"=\"#010101\"\n[characters]\noutline=\"k\"\n\
             [animations.seated]\nframes=[\"b.sprite\"]\nframe_ms=100\n\
             [hairstyles.\"wide@2x\"]\nfront={ over=\"o.sprite\" }\n",
            &[
                (
                    "b.sprite",
                    "@frame 0\n@mark head.front 2 1\nS S S S S\n. . S . .\n",
                ),
                ("o.sprite", "@frame 0\n@mark head.front 1 0\nH H H H H H\n"),
            ],
        );
        let sprite = pack.piece(Piece::Seated);
        let (body, head) = (sprite.first(), sprite.head(0).expect("marked"));
        let style = pack.inner().hairstyles().next();
        assert_eq!(Dress::of(body, head, style).reach, (1, 2));
        assert_eq!(Dress::of(body, head, None).reach, (0, 0));
    }

    #[test]
    fn a_bare_head_is_outlined_as_a_dressed_one_is() {
        let pack = pack_of(". S .\n. . .\n", (1, 0), &[]);
        let (dress, f) = dressed(&pack, AgentId::from_parts("x", "y"));
        assert_eq!(
            (dress.style.clone(), dress.rise()),
            (None, 1),
            "a row for the line alone"
        );
        let at = |x, y| f.get(x, y).copied().flatten();
        assert_eq!(at(1, 1), Some(S));
        assert_eq!(
            (at(1, 0), at(0, 1), at(1, 2)),
            (Some(LINE), Some(LINE), Some(LINE))
        );
    }

    /// A body whose skin tops its frame, with a 2x variant drawn of it, the
    /// styles `styles` at 2x and `extra` tables beside: the seated frame a
    /// renderer at 2x takes.
    fn seated_at_2x(
        styles: &[&str],
        extra: &str,
    ) -> (&'static OfficeArt, crate::pack::DenseFrame<'static>) {
        let mut toml = format!(
            "[palette]\n\".\"=\"transparent\"\n\"H\"=\"#c86432\"\n\"S\"=\"#f0c0a0\"\n\
             \"k\"=\"#010101\"\n[characters]\noutline=\"k\"\n\
             [animations.seated]\nframes=[\"b.sprite\"]\nframe_ms=100\n\
             [animations.\"seated@2x\"]\nframes=[\"b2.sprite\"]\nframe_ms=100\n{extra}"
        );
        for s in styles {
            toml.push_str(&format!(
                "[hairstyles.\"{s}@2x\"]\nfront={{ over=\"o.sprite\" }}\n"
            ));
        }
        let pack = crate::pack::test_office_with(
            &toml,
            &[
                ("b.sprite", "@frame 0\n@mark head.front 1 0\n. S .\n. . .\n"),
                (
                    "b2.sprite",
                    "@frame 0\n@mark head.front 2 0\n\
                     . . S S . .\n. . S S . .\n. . . . . .\n. . . . . .\n",
                ),
                ("o.sprite", "@frame 0\n@mark head.front 0 1\nH\n. \n"),
                ("o4.sprite", "@frame 0\n@mark head.front 0 3\nH\nH\nH\n. \n"),
            ],
        );
        let pack: &'static OfficeArt = Box::leak(Box::new(pack));
        let scale = crate::render_scale::RenderScale::new(2).expect("nonzero");
        let art = crate::pack::densest_frame(pack, Piece::Seated, 0, scale);
        assert_eq!(art.density, TWO, "premise: the 2x variant is drawn");
        (pack, art)
    }

    #[test]
    fn the_headroom_holds_a_bare_head_in_a_pack_with_no_styles() {
        let (pack, art) = seated_at_2x(&[], "");
        assert_eq!(max_rise(pack, &art), 1, "a row for the outline alone");
    }

    #[test]
    fn the_headroom_counts_only_the_styles_drawn_at_the_frames_density() {
        let (pack, art) = seated_at_2x(
            &["mop"],
            "[hairstyles.\"mop@4x\"]\nfront={ over=\"o4.sprite\" }\n",
        );
        let at_2x = pack.inner().hairstyle("mop", TWO);
        let head = art.head.expect("premise: the 2x frame marks a head");
        assert_eq!(
            max_rise(pack, &art),
            Dress::of(art.frame, head, at_2x).rise(),
            "the taller 4x layer never sizes a 2x frame's headroom"
        );
    }

    #[test]
    fn a_base_frame_needs_no_headroom() {
        let (pack, _) = seated_at_2x(&["mop"], "");
        let art = crate::pack::densest_frame(
            pack,
            Piece::Seated,
            0,
            crate::render_scale::RenderScale::ONE,
        );
        assert_eq!(max_rise(pack, &art), 0, "base art is never dressed");
    }

    #[test]
    fn a_gap_the_outline_closes_to_one_pixel_takes_the_line() {
        // Four pixels two apart round a centre none of them touches: the line
        // round each walls the centre in.
        let pack = pack_of(
            ". . S . .\n. . . . .\nS . . . S\n. . . . .\n. . S . .\n",
            (2, 4),
            &["mop"],
        );
        let (dress, f) = dressed(&pack, AgentId::from_parts("x", "y"));
        assert_eq!(
            f.get(2, 2 + dress.rise()).copied().flatten(),
            Some(LINE),
            "the centre, walled in"
        );
    }

    #[test]
    fn dress_drops_hair_past_a_side_as_validation_flags_and_past_the_bottom_unflagged() {
        let (side, mark) = (4u16, 1u16);
        let reach = 2 * side + 1;
        let rows = |n: u16, key: &dyn Fn(u16, u16) -> &'static str| -> String {
            (0..n)
                .map(|y| (0..n).map(|x| key(x, y)).collect::<Vec<_>>().join(" ") + "\n")
                .collect()
        };
        let body = format!(
            "@frame 0\n@mark head.front {mark} {mark}\n{}",
            rows(side, &|_, _| "S")
        );
        let toml = "[palette]\n\".\"=\"transparent\"\n\"H\"=\"#c86432\"\n\"S\"=\"#f0c0a0\"\n\
                    [animations.seated]\nframes=[\"one.sprite\"]\nframe_ms=100\n\
                    [animations.\"seated@2x\"]\nframes=[\"b.sprite\"]\nframe_ms=100\n\
                    [hairstyles.\"mop@2x\"]\nfront={ over=\"o.sprite\" }\n";
        let (mut flagged_seen, mut bottom_seen) = (false, false);
        for hy in 0..reach {
            for hx in 0..reach {
                let pixel = |x, y| if (x, y) == (hx, hy) { "H" } else { "." };
                let hair = format!(
                    "@frame 0\n@mark head.front {side} {side}\n{}",
                    rows(reach, &pixel)
                );
                let pack = load_filled_pack(
                    toml,
                    &[
                        ("one.sprite", "@frame 0\nS S\nS S"),
                        ("b.sprite", &body),
                        ("o.sprite", &hair),
                    ],
                )
                .expect("the test pack loads");
                let sprite = &pack.variants_of(Piece::Seated)[&test_density(2)];
                let (frame, head) = (sprite.first(), sprite.head(0).expect("marked"));
                let style = pack.hairstyles().next();
                let f = dress(
                    frame,
                    &Dress::of(frame, head, style),
                    style,
                    &[],
                    pack.character_outline(),
                );
                let dropped = !(0..f.height())
                    .any(|y| (0..f.width()).any(|x| f.get(x, y).copied().flatten() == Some(H)));
                let flagged = !crate::pack::validate::validate_pack(&pack)
                    .overhanging_hair
                    .is_empty();
                let below = hy + mark >= side + side;
                flagged_seen |= flagged;
                bottom_seen |= below && !flagged;
                assert_eq!(dropped, flagged || below, "hair at ({hx}, {hy})");
            }
        }
        assert!(flagged_seen && bottom_seen);
    }

    /// Every bundled variant character frame, bare and dressed in every style,
    /// keeps its one outline whole: nothing but the line on a side edge, where
    /// the line has no column left to run in, and no pinhole inside it. A
    /// dressed frame first exists here, at runtime, so no generator check can
    /// see it.
    #[test]
    fn every_bundled_character_dressed_in_every_style_keeps_its_outline_whole() {
        let pack = crate::pack::test_office();
        let line = pack.inner().character_outline();
        let (mut dressed, mut flaws) = (0, Vec::new());
        let arts = Piece::VARIANTS
            .iter()
            .filter(|p| p.kind() == PieceKind::Character)
            .flat_map(|&p| {
                pack.inner()
                    .variants_of(p)
                    .iter()
                    .map(move |(d, s)| (format!("{}@{d}x", p.name()), s))
            });
        for (name, sprite) in arts {
            for (i, body) in sprite.frames().iter().enumerate() {
                let Some(head) = sprite.head(i) else {
                    continue;
                };
                let styles = pack.inner().hairstyles().map(Some).chain([None]);
                for style in styles {
                    let d = Dress::of(body, head, style);
                    let f = dress(body, &d, style, &[], line);
                    let (w, h) = (f.width(), f.height());
                    let at = |x: u16, y: u16| f.get(x, y).copied().flatten();
                    let mut flaw = |what: &str, x: u16, y: u16| {
                        flaws.push(format!(
                            "{name}[{i}] in {}: {what} at ({x}, {y})",
                            style.map_or("no style", Hairstyle::name)
                        ));
                    };
                    for y in 0..h {
                        for x in [0, w - 1] {
                            if at(x, y).is_some() && at(x, y) != Some(line) {
                                flaw("unoutlined on the edge", x, y);
                            }
                        }
                    }
                    for y in 1..h - 1 {
                        for x in 1..w - 1 {
                            let walled = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
                                .iter()
                                .all(|&(nx, ny)| at(nx, ny).is_some());
                            if at(x, y).is_none() && walled {
                                flaw("a pinhole", x, y);
                            }
                        }
                    }
                    dressed += 1;
                }
            }
        }
        assert!(flaws.is_empty(), "{flaws:#?}");
        assert!(dressed > 0, "the bundled pack dresses its characters");
    }
}
