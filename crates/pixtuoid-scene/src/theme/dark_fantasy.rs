use crate::sprite::Rgb;

use super::*;

/// The `dark-fantasy` dark theme: a torchlit stone keep under a night sky.
pub static DARK_FANTASY: Theme = Theme {
    camp: Some(&DARK_FANTASY_CAMP),
    ..KEEP
};

/// [`DARK_FANTASY`]'s camp: the keep's palette out on trampled earth inside a
/// rough wooden palisade, lit by fire.
pub(crate) static DARK_FANTASY_CAMP: Theme = Theme {
    name: "dark-fantasy-camp",
    display_name: "Dark Fantasy Camp",
    surface: SurfaceColors {
        // The palisade: split logs, their gaps the posts' darker grain.
        wall: Rgb {
            r: 66,
            g: 47,
            b: 31,
        },
        wall_trim: Rgb {
            r: 36,
            g: 25,
            b: 16,
        },
        // Trampled grass over dark earth.
        carpet_base: Rgb {
            r: 50,
            g: 54,
            b: 34,
        },
        carpet_light: Rgb {
            r: 70,
            g: 72,
            b: 42,
        },
        carpet_dark: Rgb {
            r: 34,
            g: 34,
            b: 23,
        },
        window_frame: Rgb {
            r: 44,
            g: 31,
            b: 20,
        },
        bg_fallback: Rgb {
            r: 20,
            g: 21,
            b: 15,
        },
    },
    office: OfficeColors {
        // The corridor's runner is the camp's beaten path.
        runner_base: Rgb {
            r: 74,
            g: 58,
            b: 40,
        },
        runner_stripe: Rgb {
            r: 88,
            g: 70,
            b: 48,
        },
        runner_edge: Rgb {
            r: 50,
            g: 39,
            b: 27,
        },
        ..KEEP.office
    },
    lighting: LightingColors {
        // Firelight: deeper and redder than the keep's lamps.
        floor_lamp_halo: Rgb {
            r: 255,
            g: 128,
            b: 44,
        },
        desk_lamp: Rgb {
            r: 255,
            g: 158,
            b: 66,
        },
        ..KEEP.lighting
    },
    furniture: FurnitureColors {
        // Every mat the camp lays is woven straw on the earth.
        rug_field: Rgb {
            r: 118,
            g: 98,
            b: 58,
        },
        rug_trim: Rgb {
            r: 80,
            g: 64,
            b: 38,
        },
        rug_accent: Rgb {
            r: 146,
            g: 124,
            b: 76,
        },
        ..KEEP.furniture
    },
    camp: None,
    // The camp's board is a wooden signboard, its words burnt in pale.
    board: Board::Plain {
        face: Rgb {
            r: 96,
            g: 68,
            b: 42,
        },
        frame: Rgb {
            r: 54,
            g: 37,
            b: 23,
        },
        ink: Rgb {
            r: 236,
            g: 214,
            b: 166,
        },
    },
    ..KEEP
};

/// What [`DARK_FANTASY`] and its camp share.
const KEEP: Theme = Theme {
    name: "dark-fantasy",
    display_name: "Dark Fantasy",
    kind: ThemeKind::Dark,
    camp: None,
    // The keep's board is a stone plaque in an iron frame, its words carved.
    board: Board::Plain {
        face: Rgb {
            r: 56,
            g: 58,
            b: 64,
        },
        frame: Rgb {
            r: 104,
            g: 108,
            b: 116,
        },
        ink: Rgb {
            r: 206,
            g: 198,
            b: 176,
        },
    },
    surface: SurfaceColors {
        wall: Rgb {
            r: 62,
            g: 66,
            b: 76,
        },
        wall_trim: Rgb {
            r: 34,
            g: 37,
            b: 46,
        },
        carpet_base: Rgb {
            r: 58,
            g: 54,
            b: 50,
        },
        carpet_light: Rgb {
            r: 78,
            g: 72,
            b: 62,
        },
        carpet_dark: Rgb {
            r: 38,
            g: 36,
            b: 34,
        },
        window_frame: Rgb {
            r: 28,
            g: 29,
            b: 34,
        },
        bg_fallback: Rgb {
            r: 22,
            g: 23,
            b: 28,
        },
    },
    office: OfficeColors {
        room_wall_trim_light: Rgb {
            r: 84,
            g: 90,
            b: 102,
        },
        room_wall_trim_dark: Rgb {
            r: 30,
            g: 31,
            b: 36,
        },
        // The corridor's runner is a worn flagstone path.
        runner_base: Rgb {
            r: 70,
            g: 66,
            b: 60,
        },
        runner_stripe: Rgb {
            r: 84,
            g: 79,
            b: 70,
        },
        runner_edge: Rgb {
            r: 44,
            g: 42,
            b: 40,
        },
        neon_panel_bg: Rgb {
            r: 26,
            g: 22,
            b: 22,
        },
        building_dark: Rgb {
            r: 12,
            g: 13,
            b: 20,
        },
        building_light: Rgb {
            r: 32,
            g: 35,
            b: 48,
        },
        city_lit_windows: [
            Rgb {
                r: 104,
                g: 70,
                b: 40,
            },
            Rgb {
                r: 84,
                g: 58,
                b: 36,
            },
            Rgb {
                r: 124,
                g: 90,
                b: 52,
            },
        ],
        city_dark_window: Rgb {
            r: 16,
            g: 17,
            b: 24,
        },
        clock_rim: Rgb {
            r: 140,
            g: 112,
            b: 58,
        },
        clock_face: Rgb {
            r: 204,
            g: 190,
            b: 160,
        },
        clock_hand: Rgb {
            r: 30,
            g: 24,
            b: 20,
        },
        shadow: Rgb {
            r: 12,
            g: 12,
            b: 16,
        },
    },
    lighting: LightingColors {
        day_sky_a: Rgb {
            r: 104,
            g: 112,
            b: 128,
        },
        day_sky_b: Rgb {
            r: 78,
            g: 88,
            b: 108,
        },
        night_sky_a: Rgb {
            r: 22,
            g: 26,
            b: 44,
        },
        night_sky_b: Rgb {
            r: 10,
            g: 12,
            b: 26,
        },
        twilight_a: Rgb {
            r: 128,
            g: 62,
            b: 48,
        },
        twilight_b: Rgb {
            r: 72,
            g: 42,
            b: 62,
        },
        sun_spill: Rgb {
            r: 220,
            g: 150,
            b: 80,
        },
        floor_lamp_halo: Rgb {
            r: 240,
            g: 150,
            b: 60,
        },
        desk_lamp: Rgb {
            r: 255,
            g: 182,
            b: 92,
        },
        night_tint: Rgb {
            r: 12,
            g: 10,
            b: 22,
        },
        sun_core: Rgb {
            r: 232,
            g: 172,
            b: 100,
        },
        moon_core: Rgb {
            r: 190,
            g: 200,
            b: 222,
        },
    },
    furniture: FurnitureColors {
        wood_top: Rgb {
            r: 74,
            g: 52,
            b: 34,
        },
        wood_trim: Rgb {
            r: 44,
            g: 30,
            b: 20,
        },
        // Every mat is trodden dark earth.
        rug_field: Rgb {
            r: 66,
            g: 55,
            b: 43,
        },
        rug_trim: Rgb {
            r: 42,
            g: 35,
            b: 28,
        },
        rug_accent: Rgb {
            r: 92,
            g: 78,
            b: 58,
        },
        magazine: Rgb {
            r: 116,
            g: 74,
            b: 46,
        },
        magazine_trim: Rgb {
            r: 66,
            g: 42,
            b: 28,
        },
        chair_trim: Rgb {
            r: 36,
            g: 28,
            b: 22,
        },
        coffee_cup: Rgb {
            r: 112,
            g: 110,
            b: 106,
        },
        coffee_cup_shadow: Rgb {
            r: 78,
            g: 76,
            b: 74,
        },
        tank_water: Rgb {
            r: 28,
            g: 48,
            b: 54,
        },
        tank_water_line: Rgb {
            r: 120,
            g: 160,
            b: 150,
        },
        tank_fish: Rgb {
            r: 200,
            g: 140,
            b: 60,
        },
        tank_fish_alt: Rgb {
            r: 150,
            g: 60,
            b: 50,
        },
        tank_plant: Rgb {
            r: 60,
            g: 92,
            b: 50,
        },
        paper: Rgb {
            r: 214,
            g: 200,
            b: 168,
        },
        paper_shade: Rgb {
            r: 176,
            g: 160,
            b: 126,
        },
    },
    effects: EffectColors {
        monitor_frame_lit: Rgb {
            r: 90,
            g: 96,
            b: 112,
        },
        monitor_idle: Rgb {
            r: 44,
            g: 52,
            b: 72,
        },
        sleep_z: Rgb {
            r: 170,
            g: 182,
            b: 212,
        },
        coffee_steam: Rgb {
            r: 150,
            g: 150,
            b: 160,
        },
        walking_dust: Rgb {
            r: 72,
            g: 68,
            b: 62,
        },
        requires_action_bubble: Rgb {
            r: 224,
            g: 178,
            b: 84,
        },
    },
    tool_glow: ToolGlowColors {
        edit: Rgb {
            r: 110,
            g: 168,
            b: 204,
        },
        read: Rgb {
            r: 204,
            g: 162,
            b: 90,
        },
        bash: Rgb {
            r: 222,
            g: 110,
            b: 60,
        },
        agent: Rgb {
            r: 168,
            g: 120,
            b: 210,
        },
        grep: Rgb {
            r: 112,
            g: 178,
            b: 108,
        },
        default: Rgb {
            r: 200,
            g: 196,
            b: 184,
        },
    },
    ui: UiColors {
        label_running: Rgb {
            r: 168,
            g: 192,
            b: 120,
        },
        label_ok: Rgb {
            r: 140,
            g: 176,
            b: 110,
        },
        label_requires_action: Rgb {
            r: 232,
            g: 176,
            b: 72,
        },
        label_warn: Rgb {
            r: 206,
            g: 86,
            b: 70,
        },
        label_idle: Rgb {
            r: 170,
            g: 160,
            b: 140,
        },
        label_exiting: Rgb {
            r: 178,
            g: 166,
            b: 146,
        },
        tooltip_bg: Rgb {
            r: 62,
            g: 44,
            b: 29,
        },
        tooltip_title: Rgb {
            r: 232,
            g: 214,
            b: 170,
        },
        tooltip_text: Rgb {
            r: 196,
            g: 182,
            b: 152,
        },
        tooltip_dim: Rgb {
            r: 138,
            g: 124,
            b: 102,
        },
        neon_brand: Rgb {
            r: 184,
            g: 56,
            b: 48,
        },
        neon_star: Rgb {
            r: 192,
            g: 152,
            b: 72,
        },
        neon_alert: Rgb {
            r: 232,
            g: 182,
            b: 84,
        },
    },
    appliance: ApplianceColors {
        vending_body: Rgb {
            r: 40,
            g: 36,
            b: 34,
        },
        vending_panel: Rgb {
            r: 130,
            g: 40,
            b: 36,
        },
        vending_drinks: [
            Rgb {
                r: 172,
                g: 50,
                b: 50,
            },
            Rgb {
                r: 60,
                g: 132,
                b: 92,
            },
            Rgb {
                r: 72,
                g: 92,
                b: 172,
            },
            Rgb {
                r: 202,
                g: 162,
                b: 62,
            },
        ],
        vending_trim: Rgb {
            r: 150,
            g: 118,
            b: 58,
        },
        vending_dark: Rgb {
            r: 18,
            g: 16,
            b: 16,
        },
        printer_body: Rgb {
            r: 150,
            g: 146,
            b: 138,
        },
        printer_top: Rgb {
            r: 60,
            g: 58,
            b: 56,
        },
        printer_glass: Rgb {
            r: 70,
            g: 90,
            b: 110,
        },
        printer_paper: Rgb {
            r: 222,
            g: 208,
            b: 178,
        },
        printer_tray: Rgb {
            r: 110,
            g: 106,
            b: 100,
        },
        coats: [
            Rgb {
                r: 112,
                g: 32,
                b: 30,
            },
            Rgb {
                r: 52,
                g: 62,
                b: 82,
            },
            Rgb {
                r: 122,
                g: 100,
                b: 70,
            },
        ],
    },
    // A source's hue is its brand's, muted to a torch-lit keep's metals and
    // dyes and held apart from the others and against the plate by the
    // separation and badge-contrast guards.
    source: SourceColors {
        claude_code: Rgb {
            r: 0xde,
            g: 0x92,
            b: 0x4c,
        },
        codex: Rgb {
            r: 0x7e,
            g: 0xbe,
            b: 0xc8,
        },
        reasonix: Rgb {
            r: 0xac,
            g: 0x8c,
            b: 0xd6,
        },
        antigravity: Rgb {
            r: 0x76,
            g: 0xc4,
            b: 0x70,
        },
        codewhale: Rgb {
            r: 0x40,
            g: 0xa4,
            b: 0x98,
        },
        opencode: Rgb {
            r: 0xd6,
            g: 0x5c,
            b: 0x54,
        },
        copilot: Rgb {
            r: 0xd4,
            g: 0x70,
            b: 0x98,
        },
        cursor: Rgb {
            r: 0x96,
            g: 0xa0,
            b: 0xb8,
        },
        openclaw: Rgb {
            r: 0xe6,
            g: 0xd0,
            b: 0x5a,
        },
        hermes: Rgb {
            r: 0x84,
            g: 0x76,
            b: 0xe8,
        },
        omp: Rgb {
            r: 0x96,
            g: 0xbe,
            b: 0x4a,
        },
        grok: Rgb {
            r: 0x46,
            g: 0xbe,
            b: 0xd2,
        },
        kimi: Rgb {
            r: 0xb0,
            g: 0x5c,
            b: 0xe6,
        },
        jcode: Rgb {
            r: 0xc0,
            g: 0xd4,
            b: 0xa8,
        },
        dsh: Rgb {
            r: 0x5a,
            g: 0x8c,
            b: 0xf0,
        },
    },
};
