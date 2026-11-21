use crate::sprite::Rgb;

use super::*;

/// The `dark-fantasy` dark theme: a torchlit stone keep under a night sky.
pub static DARK_FANTASY: Theme = Theme {
    name: "dark-fantasy",
    display_name: "Dark Fantasy",
    kind: ThemeKind::Dark,
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
        runner_base: Rgb {
            r: 72,
            g: 30,
            b: 28,
        },
        runner_stripe: Rgb {
            r: 118,
            g: 92,
            b: 48,
        },
        runner_edge: Rgb {
            r: 40,
            g: 18,
            b: 18,
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
        rug_field: Rgb {
            r: 82,
            g: 30,
            b: 30,
        },
        rug_trim: Rgb {
            r: 40,
            g: 16,
            b: 16,
        },
        rug_accent: Rgb {
            r: 150,
            g: 118,
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
            r: 150,
            g: 190,
            b: 128,
        },
        label_ok: Rgb {
            r: 130,
            g: 172,
            b: 102,
        },
        label_requires_action: Rgb {
            r: 224,
            g: 178,
            b: 84,
        },
        label_warn: Rgb {
            r: 214,
            g: 84,
            b: 72,
        },
        label_idle: Rgb {
            r: 158,
            g: 160,
            b: 172,
        },
        label_exiting: Rgb {
            r: 144,
            g: 142,
            b: 152,
        },
        tooltip_bg: Rgb {
            r: 22,
            g: 20,
            b: 22,
        },
        tooltip_title: Rgb {
            r: 228,
            g: 216,
            b: 190,
        },
        tooltip_text: Rgb {
            r: 188,
            g: 180,
            b: 162,
        },
        tooltip_dim: Rgb {
            r: 124,
            g: 116,
            b: 104,
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
    // A source's hue is its brand's, so these are dracula's dark-plate set,
    // already cleared by the separation and badge-contrast guards.
    source: SourceColors {
        claude_code: Rgb {
            r: 0xff,
            g: 0xb8,
            b: 0x6c,
        },
        codex: Rgb {
            r: 0x8b,
            g: 0xe9,
            b: 0xfd,
        },
        reasonix: Rgb {
            r: 0xbd,
            g: 0x93,
            b: 0xf9,
        },
        antigravity: Rgb {
            r: 0x50,
            g: 0xfa,
            b: 0x7b,
        },
        codewhale: Rgb {
            r: 0x33,
            g: 0xb8,
            b: 0xa8,
        },
        opencode: Rgb {
            r: 0xff,
            g: 0x55,
            b: 0x55,
        },
        copilot: Rgb {
            r: 0xe0,
            g: 0x60,
            b: 0x9c,
        },
        cursor: Rgb {
            r: 0x96,
            g: 0xa0,
            b: 0xb9,
        },
        openclaw: Rgb {
            r: 0xff,
            g: 0xaa,
            b: 0x30,
        },
        hermes: Rgb {
            r: 0x68,
            g: 0x58,
            b: 0xe0,
        },
        omp: Rgb {
            r: 0x8a,
            g: 0xc8,
            b: 0x32,
        },
        grok: Rgb {
            r: 0x30,
            g: 0xd0,
            b: 0xe8,
        },
        kimi: Rgb {
            r: 0xc4,
            g: 0x46,
            b: 0xfe,
        },
        jcode: Rgb {
            r: 0x60,
            g: 0xc0,
            b: 0x80,
        },
        dsh: Rgb {
            r: 0x4d,
            g: 0x6b,
            b: 0xfe,
        },
    },
};
