#!/usr/bin/env python3
"""Pearl Post Suite — entry point."""

import sys

from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from branding import APP_NAME, ICONS_DIR, ORG_NAME, QSS_PATH
from ui.main_window import MainWindow

# Qt6 has High-DPI scaling on by default — the AA_* flags are removed/no-ops.

# Preferred serifs in order of taste; first one actually installed wins.
_SERIF_CHAIN = [
    "Iowan Old Style",      # macOS classic
    "Source Serif Pro",     # if shipped via Homebrew or bundled
    "New York",             # macOS 11+
    "Charter",              # macOS
    "Cambria",              # Windows
    "Georgia",              # universal
]


def _resolve_serif() -> str:
    """Return the first installed family from _SERIF_CHAIN, defaulting to 'serif'."""
    families = set(QFontDatabase.families())
    for name in _SERIF_CHAIN:
        if name in families:
            return name
    return "serif"


def _apply_theme(app: QApplication):
    app.setStyle("Fusion")
    if not QSS_PATH.exists():
        return
    qss = QSS_PATH.read_text(encoding="utf-8")
    # Substitute the brand serif token in the QSS with whatever's actually
    # available on this machine, so Qt doesn't waste 200ms probing missing
    # families on startup. Token: __BRAND_SERIF__
    serif = _resolve_serif()
    qss = qss.replace("__BRAND_SERIF__", f'"{serif}"')
    app.setStyleSheet(qss)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    # App icon — falls through to default if the SVG isn't there yet
    icon_path = ICONS_DIR / "pearl-mark.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    _apply_theme(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
