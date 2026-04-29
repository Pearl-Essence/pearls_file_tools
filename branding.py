"""Brand identity constants for Pearl Post Suite.

Single source of truth for app name, palette hex codes, asset paths.
Reference these everywhere instead of hardcoding strings or colors.
"""

from pathlib import Path

# ── Identity ────────────────────────────────────────────────────────────────
APP_NAME       = "Pearl Post Suite"
APP_NAME_SHORT = "Pearl"
APP_TAGLINE    = "POST SUITE · V0.11"
ORG_NAME       = "Pearl"

# ── Resource paths ──────────────────────────────────────────────────────────
RESOURCES_DIR = Path(__file__).parent / "resources"
STYLES_DIR    = RESOURCES_DIR / "styles"
ICONS_DIR     = RESOURCES_DIR / "icons"
QSS_PATH      = STYLES_DIR / "pearl_dark.qss"

# ── Palette (mirror of pearl_dark.qss — for code that needs raw QColor) ─────
class Palette:
    BG_VOID       = "#0B0B0D"   # app shell, behind everything
    BG_PANEL      = "#15161A"   # floating panel base
    BG_PANEL_HI   = "#1C1E24"   # hovered row, raised surface
    BG_INPUT      = "#0F1013"   # text fields, log

    STROKE_SOFT   = "#2A2C33"
    STROKE_STRONG = "#3A3D46"

    TEXT_PRIMARY   = "#E8E6DF"
    TEXT_SECONDARY = "#9A958A"
    TEXT_MUTED     = "#5C5950"

    GOLD     = "#E8B547"
    GOLD_HI  = "#F0C766"
    GOLD_LO  = "#B8862E"

    OK    = "#6FBF73"
    WARN  = "#E8B547"   # reuse gold
    ERROR = "#E5484D"
    INFO  = "#7C9CBF"


# ── Sidebar navigation tree (sections + items) ──────────────────────────────
# Each item: (label, icon_filename, factory_key)
# factory_key is consumed by main_window.py to look up which tab class /
# dialog opener to mount. Keeping it as a string keeps this file dependency-free.
NAV_TREE = [
    ("01 · INGEST", [
        ("Offload",            "ingest.svg",          "offload"),
        ("Proxy Generation",   "proxy.svg",           "proxy"),
    ]),
    ("02 · ORGANIZE", [
        ("Bulk Rename",        "rename.svg",          "rename"),
        ("Group by Pattern",   "group.svg",           "organize"),
        ("Extract Archives",   "archive-extract.svg", "extract"),
        ("Browse Stills",      "stills.svg",          "stills"),
    ]),
    ("03 · MAINTAIN", [
        ("Studio Tools",       "health.svg",          "studio"),
        ("Sync Check",         "sync.svg",            "sync_dialog"),
        ("Watch Folders",      "watch.svg",           "watch_dialog"),
    ]),
    ("04 · DELIVER", [
        ("Delivery",           "validator.svg",       "delivery"),
    ]),
    ("05 · ARCHIVE", [
        ("LTO / Cold Storage", "archive-cold.svg",    "stub:lto"),
    ]),
]
