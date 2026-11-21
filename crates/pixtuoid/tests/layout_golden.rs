//! Layout geometry golden snapshots: the key fields of `SceneLayout` at fixed
//! buffer sizes, so any refactor to `compute` that
//! accidentally shifts desk positions, room bounds, or waypoint coords fails
//! immediately.
//!
//! Regenerating after an INTENTIONAL layout change: run the suite to produce
//! `*.snap.new`, eyeball the diff, then `cargo insta accept`. The same applies
//! to `walkable_golden.rs`.

use pixtuoid_scene::layout::{SceneLayout, Viewport};

#[test]
fn layout_standard_96x72_desks() {
    let l = SceneLayout::compute(Viewport::full(96, 72), Some(4), 11).unwrap();
    insta::assert_debug_snapshot!("desks_96x72", l.home_desks);
}

#[test]
fn layout_standard_96x72_waypoints() {
    let l = SceneLayout::compute(Viewport::full(96, 72), Some(4), 11).unwrap();
    insta::assert_debug_snapshot!("waypoints_96x72", l.waypoints);
}

#[test]
fn layout_standard_96x72_meeting() {
    let l = SceneLayout::compute(Viewport::full(96, 72), Some(4), 11).unwrap();
    insta::assert_debug_snapshot!("meeting_96x72", l.meeting_room_bounds(0));
}

#[test]
fn layout_standard_96x72_room_walls() {
    let l = SceneLayout::compute(Viewport::full(96, 72), Some(4), 11).unwrap();
    insta::assert_debug_snapshot!("room_walls_96x72", l.room_walls);
}

#[test]
fn layout_standard_96x72_zones() {
    let l = SceneLayout::compute(Viewport::full(96, 72), Some(4), 11).unwrap();
    insta::assert_debug_snapshot!("cubicle_band_96x72", l.cubicle_band);
    insta::assert_debug_snapshot!("cubicle_aisle_96x72", l.cubicle_aisle);
    insta::assert_debug_snapshot!("pantry_96x72", l.pantry.map(|p| p.bounds));
}

#[test]
fn layout_standard_192x160_desks() {
    let l = SceneLayout::compute(Viewport::full(192, 160), Some(8), 11).unwrap();
    insta::assert_debug_snapshot!("desks_192x160", l.home_desks);
}

#[test]
fn layout_standard_192x160_waypoints() {
    let l = SceneLayout::compute(Viewport::full(192, 160), Some(8), 11).unwrap();
    insta::assert_debug_snapshot!("waypoints_192x160", l.waypoints);
}

#[test]
fn layout_standard_192x160_meeting() {
    let l = SceneLayout::compute(Viewport::full(192, 160), Some(8), 11).unwrap();
    insta::assert_debug_snapshot!("meeting_192x160", l.meeting_room_bounds(0));
}

#[test]
fn layout_standard_192x160_room_walls() {
    let l = SceneLayout::compute(Viewport::full(192, 160), Some(8), 11).unwrap();
    insta::assert_debug_snapshot!("room_walls_192x160", l.room_walls);
}

/// Seed 2's office, checked for the open plan's shape, which the lounge shares;
/// `pixtuoid-scene`'s `the_layout_goldens_seeds_are_their_variants` pins which,
/// and that seed 11, the standard goldens', is the standard floor.
fn open_plan_seed2() -> SceneLayout {
    let l = SceneLayout::compute(Viewport::full(160, 120), Some(4), 2).unwrap();
    assert!(
        l.meeting_rooms.is_empty() && l.pantry.is_some(),
        "seed 2 lays out the open plan"
    );
    l
}

#[test]
fn layout_open_plan_seed2_desks() {
    let l = open_plan_seed2();
    insta::assert_debug_snapshot!("desks_open_plan_seed2", l.home_desks);
}

#[test]
fn layout_open_plan_seed2_waypoints() {
    let l = open_plan_seed2();
    insta::assert_debug_snapshot!("waypoints_open_plan_seed2", l.waypoints);
}

/// Seed 3's office, checked to be the dense floor (two meeting rooms, no
/// pantry) before a snapshot can take another variant's under its name.
fn dense_seed3() -> SceneLayout {
    let l = SceneLayout::compute(Viewport::full(192, 160), Some(4), 3).unwrap();
    assert!(
        l.meeting_rooms.len() == 2 && l.pantry.is_none(),
        "seed 3 lays out the dense floor"
    );
    l
}

#[test]
fn layout_dense_seed3_desks() {
    let l = dense_seed3();
    insta::assert_debug_snapshot!("desks_dense_seed3", l.home_desks);
}

#[test]
fn layout_dense_seed3_waypoints() {
    let l = dense_seed3();
    insta::assert_debug_snapshot!("waypoints_dense_seed3", l.waypoints);
}

#[test]
fn layout_dense_seed3_meeting() {
    let l = dense_seed3();
    insta::assert_debug_snapshot!("meeting_dense_seed3", l.meeting_room_bounds(0));
}

#[test]
fn layout_dense_seed3_room_walls() {
    let l = dense_seed3();
    insta::assert_debug_snapshot!("room_walls_dense_seed3", l.room_walls);
}

// A seed collision here makes adjacent floors look identical.

#[test]
fn floor_variant_hash_gives_unique_layouts_per_floor() {
    use std::collections::HashSet;

    let signatures: HashSet<_> = (0..5)
        .map(|i| {
            let seed = pixtuoid_scene::floor::floor_seed(i);
            let l = SceneLayout::compute(Viewport::full(192, 160), Some(4), seed).unwrap();
            (l.meeting_rooms.clone(), l.pantry, l.home_desks)
        })
        .collect();

    assert_eq!(
        signatures.len(),
        5,
        "floors 0..5 must produce 5 distinct layout variants, got {} unique",
        signatures.len(),
    );
}
