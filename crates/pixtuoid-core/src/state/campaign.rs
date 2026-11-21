//! Campaign seating: floor 0 is the camp, where agents rest, and the floors
//! above it are the dungeon, where working agents fight. An agent's activity
//! picks its ground, and it moves when that changes, taking a new desk and
//! walking in to it from the door.

use std::collections::BTreeSet;
use std::time::{Duration, SystemTime};

use super::{ActivityState, AgentSlot, FloorDesk, MAX_FLOORS, SceneState};

/// How a [`SceneState`] hands out its desks.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum SeatPolicy {
    /// The first free desk, floor 0 first, held for the agent's life.
    #[default]
    FloorFirst,
    /// Idle agents rest on [`CAMP_FLOOR`] and working ones fight on the floors
    /// above it; each ground overflows onto the other when it is full.
    Campaign,
}

/// The camp's floor under [`SeatPolicy::Campaign`].
pub const CAMP_FLOOR: usize = 0;

/// How long an idle agent stays in the dungeon before it leaves for the camp:
/// longer than the gap between two turns of a conversation, so an agent
/// answering its user doesn't bounce between the floors.
pub(crate) const REST_AFTER: Duration = Duration::from_secs(15);

/// Where an agent belongs under [`SeatPolicy::Campaign`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Ground {
    Camp,
    Dungeon,
}

impl Ground {
    fn of(floor: usize) -> Self {
        if floor == CAMP_FLOOR {
            Self::Camp
        } else {
            Self::Dungeon
        }
    }

    /// Its floors in the order it fills them: its own, then the other
    /// ground's as overflow.
    fn floors(self) -> [usize; MAX_FLOORS] {
        let first = match self {
            Self::Camp => CAMP_FLOOR,
            Self::Dungeon => CAMP_FLOOR + 1,
        };
        std::array::from_fn(|i| (first + i) % MAX_FLOORS)
    }
}

/// Where `slot` belongs at `now`, or `None` while it may stay where it sits:
/// an idle agent rests once it has been idle [`REST_AFTER`], and at once when
/// it holds no desk yet.
fn want(slot: &AgentSlot, now: SystemTime) -> Option<Ground> {
    match slot.state {
        ActivityState::Running { .. } | ActivityState::RequiresAction { .. } => {
            Some(Ground::Dungeon)
        }
        ActivityState::Idle => {
            let rested = (now.duration_since(slot.state_started_at)).is_ok_and(|d| d >= REST_AFTER);
            (slot.desk.is_none() || rested).then_some(Ground::Camp)
        }
    }
}

/// The first desk of `capacities` that `taken` leaves free on `ground`'s
/// floors, or on the other ground's too when `overflow`.
fn first_free(
    capacities: &[usize; MAX_FLOORS],
    taken: &BTreeSet<FloorDesk>,
    ground: Ground,
    overflow: bool,
) -> Option<FloorDesk> {
    ground
        .floors()
        .into_iter()
        .filter(|&floor| overflow || Ground::of(floor) == ground)
        .flat_map(|floor| (0..capacities[floor]).map(move |index| FloorDesk::new(floor, index)))
        .find(|desk| !taken.contains(desk))
}

/// How long a seated agent walks out to the door before it takes its desk on
/// another floor: the exit walk's own budget, which the scene's walk is
/// timed to.
const WALK_OUT: Duration = super::reducer::EXIT_GRACE_WINDOW;

/// A seated agent on its way to `to`, a desk of its other ground: it keeps its
/// old desk, walking out from it from `since`, and takes `to` once the walk
/// has had [`WALK_OUT`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) struct Move {
    to: FloorDesk,
    since: SystemTime,
}

impl Move {
    pub(super) fn since(&self) -> SystemTime {
        self.since
    }
}

/// Whether `slot` is still walking in to the desk it took: an agent that never
/// got there moves at once rather than walking out of a desk it never sat at.
fn walking_in(slot: &AgentSlot, now: SystemTime) -> bool {
    (slot.arrived_at).is_some_and(|at| now.duration_since(at).is_ok_and(|d| d < WALK_OUT))
}

/// Seat `scene` by the campaign, oldest first: an unseated agent that is
/// staying takes the first free desk of its ground or, that ground full, of
/// the other, walking in from its `arrival`; a seated one off its ground moves
/// to a free desk of its ground, and otherwise stays where it overflowed to. A
/// move walks out first ([`Move`]) and walks in from when it takes the desk. A
/// desk is free while no slot that `holds` sits at it, nor a move heads to it.
pub(super) fn seat(
    scene: &mut SceneState,
    holds: impl Fn(&AgentSlot) -> bool,
    arrival: impl Fn(&AgentSlot) -> Option<SystemTime>,
    now: SystemTime,
) {
    #[cfg(test)]
    super::SEATINGS.with(|n| n.set(n.get() + 1));
    let SceneState {
        agents,
        floor_capacities: capacities,
        moves,
        ..
    } = scene;
    // A walk-out done takes its desk. An exit, a lost desk or a change of
    // ground ends a move where it is, and a cancelled walk-out walks back in.
    for (id, mv) in std::mem::take(moves) {
        let Some(slot) = agents.get_mut(&id) else {
            continue;
        };
        let ground = Ground::of(mv.to.floor);
        if slot.exiting_at.is_some()
            || slot.desk.is_none()
            || mv.to.index.0 >= capacities[mv.to.floor]
            || want(slot, now).is_some_and(|wanted| wanted != ground)
        {
            continue;
        }
        if now.duration_since(mv.since).is_ok_and(|d| d >= WALK_OUT) {
            slot.desk = Some(mv.to);
            slot.arrived_at = Some(now);
        } else {
            moves.insert(id, mv);
        }
    }
    let mut taken: BTreeSet<FloorDesk> = (agents.values())
        .filter(|slot| holds(slot))
        .filter_map(|slot| slot.desk)
        .chain(moves.values().map(|mv| mv.to))
        .collect();
    let mut movers: Vec<(&mut AgentSlot, Ground)> = (agents.values_mut())
        .filter(|slot| slot.exiting_at.is_none() && !moves.contains_key(&slot.agent_id))
        .filter_map(|slot| {
            let ground = want(slot, now)?;
            let off_ground = slot
                .desk
                .is_none_or(|desk| Ground::of(desk.floor) != ground);
            off_ground.then_some((slot, ground))
        })
        .collect();
    movers.sort_by_key(|(slot, _)| (slot.created_at, slot.agent_id));
    for (slot, ground) in movers {
        let Some(desk) = first_free(capacities, &taken, ground, slot.desk.is_none()) else {
            continue;
        };
        taken.insert(desk);
        match slot.desk {
            Some(_) if !walking_in(slot, now) => {
                moves.insert(
                    slot.agent_id,
                    Move {
                        to: desk,
                        since: now,
                    },
                );
            }
            Some(left) => {
                taken.remove(&left);
                slot.desk = Some(desk);
                slot.arrived_at = Some(now);
            }
            None => {
                slot.desk = Some(desk);
                slot.arrived_at = arrival(slot);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AgentId;
    use crate::state::tests::make_slot;

    const T0: SystemTime = SystemTime::UNIX_EPOCH;

    fn at(secs: u64) -> SystemTime {
        T0 + Duration::from_secs(secs)
    }

    const RUNNING: ActivityState = ActivityState::Running { item: None };

    /// A campaign scene of `capacities`, its slots `states`, unseated, each a
    /// second younger than the last and in its state since its creation.
    fn campaign(
        capacities: [usize; MAX_FLOORS],
        states: &[ActivityState],
    ) -> (SceneState, Vec<AgentId>) {
        let mut scene = SceneState::new(capacities).with_seat_policy(SeatPolicy::Campaign);
        let ids: Vec<AgentId> = (0..states.len())
            .map(|i| AgentId::from_transcript_path(&format!("/p/{i}.jsonl")))
            .collect();
        for (i, (&id, state)) in ids.iter().zip(states).enumerate() {
            let mut slot = make_slot(id, 0);
            slot.desk = None;
            slot.arrived_at = None;
            slot.state = state.clone();
            slot.created_at = at(i as u64);
            slot.state_started_at = slot.created_at;
            scene.agents.insert(id, slot);
        }
        (scene, ids)
    }

    fn desks(scene: &SceneState, ids: &[AgentId]) -> Vec<Option<FloorDesk>> {
        ids.iter().map(|id| scene.agents[id].desk).collect()
    }

    fn enter(scene: &mut SceneState, id: AgentId, state: ActivityState, now: SystemTime) {
        let slot = scene.agents.get_mut(&id).expect("a slot");
        slot.state = state;
        slot.state_started_at = now;
    }

    const CAPS: [usize; MAX_FLOORS] = [2, 2, 2, 0, 0, 0, 0, 0, 0, 0];

    #[test]
    fn a_new_idle_agent_rests_in_the_camp_and_a_working_one_fights_in_the_dungeon() {
        let (mut scene, ids) = campaign(CAPS, &[ActivityState::Idle, RUNNING]);
        scene.reseat(at(2));
        assert_eq!(
            desks(&scene, &ids),
            [Some(FloorDesk::new(0, 0)), Some(FloorDesk::new(1, 0))]
        );
        assert_eq!(
            scene.agents[&ids[1]].arrived_at,
            Some(at(2)),
            "it walks in on the floor it takes"
        );
    }

    /// Reseat `scene` at `now`, then once more when a walk-out begun then is
    /// done.
    fn settle(scene: &mut SceneState, now: SystemTime) {
        scene.reseat(now);
        scene.reseat(now + WALK_OUT);
    }

    #[test]
    fn an_agent_starting_work_walks_out_of_the_camp_then_takes_a_dungeon_desk() {
        let (mut scene, ids) = campaign(CAPS, &[ActivityState::Idle]);
        scene.reseat(at(1));
        enter(&mut scene, ids[0], RUNNING, at(10));
        scene.reseat(at(10));
        assert_eq!(
            desks(&scene, &ids),
            [Some(FloorDesk::new(0, 0))],
            "it holds its bedroll while it walks out"
        );
        assert_eq!(scene.relocating(ids[0]), Some(at(10)));
        scene.reseat(at(10) + WALK_OUT - Duration::from_millis(1));
        assert_eq!(desks(&scene, &ids), [Some(FloorDesk::new(0, 0))]);
        scene.reseat(at(10) + WALK_OUT);
        assert_eq!(desks(&scene, &ids), [Some(FloorDesk::new(1, 0))]);
        assert_eq!(
            scene.agents[&ids[0]].arrived_at,
            Some(at(10) + WALK_OUT),
            "it walks in from when it takes the desk"
        );
        assert_eq!(scene.relocating(ids[0]), None);
        let blocked = ActivityState::RequiresAction { reason: None };
        enter(&mut scene, ids[0], blocked, at(20));
        settle(&mut scene, at(20));
        assert_eq!(
            desks(&scene, &ids),
            [Some(FloorDesk::new(1, 0))],
            "a blocked agent keeps its place in the fight"
        );
    }

    #[test]
    fn one_still_walking_in_moves_at_once() {
        let (mut scene, ids) = campaign(CAPS, &[ActivityState::Idle]);
        scene.reseat(at(1));
        enter(&mut scene, ids[0], RUNNING, at(2));
        scene.reseat(at(2));
        assert_eq!(desks(&scene, &ids), [Some(FloorDesk::new(1, 0))]);
        assert_eq!(scene.relocating(ids[0]), None);
    }

    #[test]
    fn a_walk_out_reserves_the_desk_it_heads_to() {
        let caps = [1, 1, 0, 0, 0, 0, 0, 0, 0, 0];
        let (mut scene, ids) = campaign(caps, &[ActivityState::Idle]);
        scene.reseat(at(1));
        enter(&mut scene, ids[0], RUNNING, at(10));
        scene.reseat(at(10));
        let late = AgentId::from_transcript_path("/p/late.jsonl");
        let mut slot = make_slot(late, 0);
        (slot.desk, slot.arrived_at, slot.state) = (None, None, RUNNING);
        slot.created_at = at(10);
        scene.agents.insert(late, slot);
        scene.reseat(at(11));
        assert_eq!(
            scene.agents[&late].desk, None,
            "neither the dungeon desk it heads to nor the bedroll it holds is free"
        );
        scene.reseat(at(10) + WALK_OUT);
        assert_eq!(desks(&scene, &ids), [Some(FloorDesk::new(1, 0))]);
        assert_eq!(scene.agents[&late].desk, Some(FloorDesk::new(0, 0)));
    }

    #[test]
    fn a_change_of_heart_mid_walk_keeps_the_old_desk() {
        let (mut scene, ids) = campaign(CAPS, &[RUNNING]);
        scene.reseat(at(1));
        enter(&mut scene, ids[0], ActivityState::Idle, at(10));
        scene.reseat(at(10) + REST_AFTER);
        assert!(scene.relocating(ids[0]).is_some(), "premise: walking out");
        enter(&mut scene, ids[0], RUNNING, at(26));
        settle(&mut scene, at(26));
        assert_eq!(desks(&scene, &ids), [Some(FloorDesk::new(1, 0))]);
        assert_eq!(scene.relocating(ids[0]), None);
    }

    #[test]
    fn a_session_ending_mid_walk_leaves_from_its_old_desk() {
        let (mut scene, ids) = campaign(CAPS, &[ActivityState::Idle]);
        scene.reseat(at(1));
        enter(&mut scene, ids[0], RUNNING, at(10));
        scene.reseat(at(10));
        scene.agents.get_mut(&ids[0]).expect("a slot").exiting_at = Some(at(11));
        settle(&mut scene, at(11));
        assert_eq!(desks(&scene, &ids), [Some(FloorDesk::new(0, 0))]);
        assert_eq!(scene.relocating(ids[0]), None);
    }

    #[test]
    fn an_idle_agent_rests_only_once_it_has_been_idle_rest_after() {
        let (mut scene, ids) = campaign(CAPS, &[RUNNING]);
        scene.reseat(at(1));
        enter(&mut scene, ids[0], ActivityState::Idle, at(10));
        scene.reseat(at(10) + REST_AFTER - Duration::from_millis(1));
        assert_eq!(
            desks(&scene, &ids),
            [Some(FloorDesk::new(1, 0))],
            "a gap between turns stays in the dungeon"
        );
        assert_eq!(scene.relocating(ids[0]), None);
        settle(&mut scene, at(10) + REST_AFTER);
        assert_eq!(desks(&scene, &ids), [Some(FloorDesk::new(0, 0))]);
        assert_eq!(
            scene.agents[&ids[0]].arrived_at,
            Some(at(10) + REST_AFTER + WALK_OUT)
        );
    }

    #[test]
    fn work_resumed_within_rest_after_never_leaves_the_dungeon() {
        let (mut scene, ids) = campaign(CAPS, &[RUNNING]);
        scene.reseat(at(1));
        let arrived = scene.agents[&ids[0]].arrived_at;
        for turn in 0..5 {
            let gap = at(10 + 20 * turn);
            enter(&mut scene, ids[0], ActivityState::Idle, gap);
            scene.reseat(gap + REST_AFTER / 2);
            enter(&mut scene, ids[0], RUNNING, gap + REST_AFTER / 2);
            scene.reseat(gap + REST_AFTER / 2);
        }
        assert_eq!(desks(&scene, &ids), [Some(FloorDesk::new(1, 0))]);
        assert_eq!(
            scene.agents[&ids[0]].arrived_at, arrived,
            "it never walked in again"
        );
    }

    #[test]
    fn a_full_camp_overflows_into_the_dungeon_and_its_agents_come_home_when_a_bedroll_frees() {
        let idle = ActivityState::Idle;
        let (mut scene, ids) = campaign(CAPS, &[idle.clone(), idle.clone(), idle]);
        scene.reseat(at(3));
        assert_eq!(
            desks(&scene, &ids),
            [
                Some(FloorDesk::new(0, 0)),
                Some(FloorDesk::new(0, 1)),
                Some(FloorDesk::new(1, 0))
            ]
        );
        scene.reseat(at(30));
        assert_eq!(
            scene.agents[&ids[2]].desk,
            Some(FloorDesk::new(1, 0)),
            "no bedroll is free, so it stays where it overflowed to"
        );
        enter(&mut scene, ids[0], RUNNING, at(31));
        // The bedroll frees once the fighter has walked out; the sleeper then
        // walks out of the dungeon to it.
        settle(&mut scene, at(31));
        scene.reseat(at(31) + WALK_OUT * 2);
        assert_eq!(
            desks(&scene, &ids),
            [
                Some(FloorDesk::new(1, 1)),
                Some(FloorDesk::new(0, 1)),
                Some(FloorDesk::new(0, 0))
            ],
            "the fighter takes the free dungeon desk and the overflowed sleeper its bedroll"
        );
    }

    #[test]
    fn a_full_dungeon_overflows_onto_the_next_floor_then_into_the_camp() {
        let caps = [2, 1, 1, 0, 0, 0, 0, 0, 0, 0];
        let (mut scene, ids) = campaign(caps, &[RUNNING, RUNNING, RUNNING]);
        scene.reseat(at(3));
        assert_eq!(
            desks(&scene, &ids),
            [
                Some(FloorDesk::new(1, 0)),
                Some(FloorDesk::new(2, 0)),
                Some(FloorDesk::new(0, 0))
            ]
        );
        enter(&mut scene, ids[0], ActivityState::Idle, at(4));
        settle(&mut scene, at(4) + REST_AFTER);
        scene.reseat(at(4) + REST_AFTER + WALK_OUT * 2);
        assert_eq!(
            desks(&scene, &ids),
            [
                Some(FloorDesk::new(0, 1)),
                Some(FloorDesk::new(2, 0)),
                Some(FloorDesk::new(1, 0))
            ],
            "the overflowed fighter takes the desk the rester left"
        );
    }

    #[test]
    fn a_shrink_reseats_whoever_loses_a_desk_on_its_own_ground() {
        let (mut scene, ids) = campaign(CAPS, &[RUNNING, RUNNING]);
        scene.reseat(at(2));
        assert_eq!(scene.agents[&ids[1]].desk, Some(FloorDesk::new(1, 1)));
        scene.set_capacities([2, 1, 2, 0, 0, 0, 0, 0, 0, 0], at(9));
        assert_eq!(
            desks(&scene, &ids),
            [Some(FloorDesk::new(1, 0)), Some(FloorDesk::new(2, 0))]
        );
        assert_eq!(scene.agents[&ids[1]].arrived_at, Some(at(9)));
        assert_eq!(
            scene.agents[&ids[0]].arrived_at,
            Some(at(2)),
            "one whose desk stays never walks in again"
        );
    }

    #[test]
    fn one_walking_out_keeps_its_desk_whatever_it_was_doing() {
        let (mut scene, ids) = campaign(CAPS, &[RUNNING]);
        scene.reseat(at(1));
        enter(&mut scene, ids[0], ActivityState::Idle, at(2));
        scene.agents.get_mut(&ids[0]).expect("a slot").exiting_at = Some(at(2));
        scene.reseat(at(2) + REST_AFTER);
        assert_eq!(
            desks(&scene, &ids),
            [Some(FloorDesk::new(1, 0))],
            "it walks out from the dungeon"
        );
    }

    #[test]
    fn floor_first_never_moves_a_seated_agent() {
        let (mut scene, ids) = campaign(CAPS, &[RUNNING]);
        scene = scene.with_seat_policy(SeatPolicy::FloorFirst);
        scene.set_capacities(CAPS, at(1));
        enter(&mut scene, ids[0], ActivityState::Idle, at(2));
        scene.reseat(at(2) + REST_AFTER);
        assert_eq!(desks(&scene, &ids), [Some(FloorDesk::new(0, 0))]);
    }

    #[test]
    fn each_ground_fills_its_own_floors_before_the_others() {
        assert_eq!(Ground::Camp.floors(), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
        assert_eq!(Ground::Dungeon.floors(), [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]);
    }
}
