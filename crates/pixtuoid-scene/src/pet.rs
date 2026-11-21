use std::time::SystemTime;

/// Duration (ms) the pet stays frozen in place after being petted.
pub(crate) const PET_DURATION_MS: u64 = 2000;

/// A floor's petting, which only [`crate::floor::OfficeSession::pet`] records:
/// outside this crate one is `None` or that session's borrow, never a copy.
#[derive(Debug)]
pub struct PetState {
    /// When the pet was last clicked — anchors the `PET_DURATION_MS` freeze.
    pub(crate) petted_at: SystemTime,
    /// Which pet was petted.
    pub(crate) kind: PetKind,
}

impl PetState {
    /// Whether the freeze/hearts effect is still playing at `now` (within `PET_DURATION_MS`).
    pub(crate) fn is_active(&self, now: SystemTime) -> bool {
        now.duration_since(self.petted_at)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(PET_DURATION_MS + 1)
            < PET_DURATION_MS
    }

    /// Milliseconds since the pet was clicked, saturating to 0 on a backward clock.
    pub(crate) fn elapsed_ms(&self, now: SystemTime) -> u64 {
        // `is_active` above deliberately does NOT use this helper: its
        // backward-clock fallback is `PET_DURATION_MS+1` (treat-as-expired),
        // not saturate-to-0.
        crate::anim::elapsed_ms(now, self.petted_at)
    }
}

/// The kind of pet: a campaign's creatures, which select their sprites and
/// idle-sleep behavior.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PetKind {
    /// An owlbear: a bear's body under an owl's head.
    Owlbear,
    /// A raven, which hops.
    Raven,
    /// A grey wolf.
    Wolf,
}

impl PetKind {
    /// Every pet kind, in the default `[[pets]]` order: floor 0, the
    /// campaign's camp, gets the first, the owlbear.
    pub const ALL: &'static [PetKind] = &[PetKind::Owlbear, PetKind::Raven, PetKind::Wolf];

    /// Its `[[pets]]` `kind` string, the one name table: every flag and error
    /// that names the kinds reads it.
    pub fn config_name(self) -> &'static str {
        match self {
            PetKind::Owlbear => "owlbear",
            PetKind::Raven => "raven",
            PetKind::Wolf => "wolf",
        }
    }

    /// The `kind` strings an older pixtuoid wrote for the creature now in
    /// this kind's place, still read so a config keeps its pets.
    fn legacy_config_name(self) -> Option<&'static str> {
        match self {
            PetKind::Owlbear => Some("dog"),
            PetKind::Wolf => Some("cat"),
            PetKind::Raven => None,
        }
    }

    /// Parses a `[[pets]]` `kind` string into a `PetKind`, its legacy name
    /// included; `None` if unknown.
    pub fn from_config_name(s: &str) -> Option<Self> {
        Self::ALL
            .iter()
            .copied()
            .find(|kind| kind.config_name() == s || kind.legacy_config_name() == Some(s))
    }

    /// Its walk.
    pub fn walk_anim(self) -> crate::pack::Walk {
        use crate::pack::Walk;
        match self {
            PetKind::Owlbear => Walk::OwlbearWalk,
            PetKind::Raven => Walk::RavenWalk,
            PetKind::Wolf => Walk::WolfWalk,
        }
    }

    /// Its sitting/resting pose.
    pub fn sit_anim(self) -> crate::pack::Piece {
        use crate::pack::Piece;
        match self {
            PetKind::Owlbear => Piece::OwlbearSit,
            PetKind::Raven => Piece::RavenSit,
            PetKind::Wolf => Piece::WolfSit,
        }
    }

    /// Its sleeping pose.
    pub fn sleep_anim(self) -> crate::pack::Piece {
        use crate::pack::Piece;
        match self {
            PetKind::Owlbear => Piece::OwlbearSleep,
            PetKind::Raven => Piece::RavenSleep,
            PetKind::Wolf => Piece::WolfSleep,
        }
    }

    /// Default display name shown in the hover tooltip when a `[[pets]]` stanza
    /// gives no `name`.
    pub fn default_name(self) -> &'static str {
        match self {
            PetKind::Owlbear => "Owlbear",
            PetKind::Raven => "Raven",
            PetKind::Wolf => "Wolf",
        }
    }

    /// What its hover says while a petting plays.
    pub fn reaction(self) -> &'static str {
        match self {
            PetKind::Owlbear => " hoo-hrrr! ",
            PetKind::Raven => " kraa! ",
            PetKind::Wolf => " awoo... ",
        }
    }

    /// Whether this kind curls up to sleep near idle agents (the wolf does).
    pub(crate) fn sleeps_near_idle(self) -> bool {
        match self {
            PetKind::Wolf => true,
            PetKind::Owlbear | PetKind::Raven => false,
        }
    }
}

/// A pet configured for the office: its [`PetKind`] plus the display name shown
/// in the hover tooltip. The name is resolved ONCE at construction, so the
/// render path never does a lookup or fallback.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Pet {
    /// Which animal.
    pub kind: PetKind,
    /// Display name shown in the hover tooltip.
    pub name: String,
}

impl Pet {
    /// A pet of `kind` with its default name — the no-custom-name case.
    pub fn defaulted(kind: PetKind) -> Self {
        Self {
            kind,
            name: kind.default_name().to_string(),
        }
    }
}

/// Picks the one pet for a floor from the office's pets (`floor_seed`-indexed);
/// `None` when none are configured.
#[deny(
    clippy::cast_possible_truncation,
    reason = "a hash picks through `crate::spread`, alike on every target"
)]
pub(crate) fn select_pet_for_floor(floor_seed: u64, pets: &[Pet]) -> Option<&Pet> {
    pets.get(crate::spread(floor_seed, pets.len()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_name_of_each_kind() {
        assert_eq!(PetKind::Owlbear.default_name(), "Owlbear");
        assert_eq!(PetKind::Raven.default_name(), "Raven");
        assert_eq!(PetKind::Wolf.default_name(), "Wolf");
    }

    /// A config an older pixtuoid wrote names the dog and the cat, whose
    /// places the owlbear and the wolf took: it keeps its pets.
    #[test]
    fn the_legacy_kind_names_still_read() {
        assert_eq!(PetKind::from_config_name("dog"), Some(PetKind::Owlbear));
        assert_eq!(PetKind::from_config_name("cat"), Some(PetKind::Wolf));
    }

    /// The default set puts the owlbear in the camp (floor 0), and the
    /// dungeon floors below it show the raven and the wolf.
    #[test]
    fn the_camp_gets_the_owlbear_and_the_dungeons_the_others() {
        let pets: Vec<Pet> = PetKind::ALL.iter().map(|&k| Pet::defaulted(k)).collect();
        let on = |floor| {
            select_pet_for_floor(crate::floor::floor_seed(floor), &pets)
                .map(|p| p.kind)
                .expect("a pet")
        };
        assert_eq!(on(0), PetKind::Owlbear);
        let below: std::collections::BTreeSet<_> =
            (1..=3).map(|floor| on(floor).config_name()).collect();
        assert!(
            below.contains("raven") && below.contains("wolf"),
            "the first dungeons show {below:?}"
        );
    }

    #[test]
    fn every_pet_kind_is_reachable_from_config() {
        for &kind in PetKind::ALL {
            assert_eq!(PetKind::from_config_name(kind.config_name()), Some(kind));
        }
    }

    #[test]
    fn from_config_name_unknown_returns_none() {
        assert_eq!(PetKind::from_config_name("hamster"), None);
    }

    #[test]
    fn select_pet_empty_returns_none() {
        assert_eq!(select_pet_for_floor(42, &[]), None);
    }

    #[test]
    fn select_pet_single_always_returns_it() {
        let pets = [Pet::defaulted(PetKind::Owlbear)];
        assert_eq!(
            select_pet_for_floor(0, &pets).map(|p| p.kind),
            Some(PetKind::Owlbear)
        );
        assert_eq!(
            select_pet_for_floor(99, &pets).map(|p| p.kind),
            Some(PetKind::Owlbear)
        );
    }

    #[test]
    fn select_pet_two_pets_alternates_by_seed() {
        let pets = vec![Pet::defaulted(PetKind::Wolf), Pet::defaulted(PetKind::Owlbear)];
        let floor0 = select_pet_for_floor(0, &pets).map(|p| p.kind);
        let floor1 = select_pet_for_floor(1, &pets).map(|p| p.kind);
        assert_ne!(floor0, floor1);
    }

    #[test]
    fn anim_names_match_kind() {
        for &kind in PetKind::ALL {
            let prefix = format!("{}_", kind.config_name());
            for piece in [kind.walk_anim().piece(), kind.sit_anim(), kind.sleep_anim()] {
                assert!(piece.name().starts_with(&prefix), "{}", piece.name());
            }
        }
    }

    #[test]
    fn only_the_wolf_sleeps_near_idle() {
        assert!(!PetKind::Owlbear.sleeps_near_idle());
        assert!(!PetKind::Raven.sleeps_near_idle());
        assert!(PetKind::Wolf.sleeps_near_idle());
    }

    #[test]
    fn is_active_true_within_window_false_after_and_on_a_backward_clock() {
        use std::time::Duration;
        let t0 = SystemTime::UNIX_EPOCH + Duration::from_secs(1_000_000);
        let pet = PetState {
            petted_at: t0,
            kind: PetKind::Wolf,
        };
        assert!(pet.is_active(t0 + Duration::from_millis(PET_DURATION_MS / 2)));
        assert!(!pet.is_active(t0 + Duration::from_millis(PET_DURATION_MS)));
        assert!(!pet.is_active(t0 + Duration::from_millis(PET_DURATION_MS + 500)));
        assert!(!pet.is_active(t0 - Duration::from_secs(1)));
    }
}
