//! Lay a floor role's manifest over the bundled `pack.toml`, as `build.rs`
//! does before it embeds that role's pack: a role's manifest names only what
//! it redraws, so everything else is the office's.

/// `over` laid over `base`: a table merges into the base's key by key, and
/// any other value, an array included, replaces the base's whole, so a role
/// that redraws an animation's `frames` keeps its `frame_ms`.
pub(crate) fn overlay(base: &mut serde_json::Value, over: serde_json::Value) {
    match (base, over) {
        (serde_json::Value::Object(base), serde_json::Value::Object(over)) => {
            for (key, value) in over {
                match base.get_mut(&key) {
                    Some(into) => overlay(into, value),
                    None => {
                        base.insert(key, value);
                    }
                }
            }
        }
        (base, over) => *base = over,
    }
}

#[cfg(test)]
mod tests {
    use super::overlay;

    #[test]
    fn a_table_merges_and_any_other_value_replaces() {
        let mut base = serde_json::json!({
            "animations": {
                "desk": { "frames": ["desk.sprite", "desk_1.sprite"], "frame_ms": 600 },
                "door": { "frames": ["door.sprite"], "frame_ms": 999_999 },
            },
            "palette": { "D": "#4a3422" },
        });
        overlay(
            &mut base,
            serde_json::json!({
                "animations": { "desk": { "frames": ["camp_desk.sprite"] } },
                "palette": { "q": "#102030" },
                "walls": { "windows": false },
            }),
        );
        assert_eq!(
            base,
            serde_json::json!({
                "animations": {
                    "desk": { "frames": ["camp_desk.sprite"], "frame_ms": 600 },
                    "door": { "frames": ["door.sprite"], "frame_ms": 999_999 },
                },
                "palette": { "D": "#4a3422", "q": "#102030" },
                "walls": { "windows": false },
            })
        );
    }
}
