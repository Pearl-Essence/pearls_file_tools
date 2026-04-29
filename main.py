#!/usr/bin/env python3
"""Pearl Post Suite — entry point."""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from branding import APP_NAME, ICONS_DIR, ORG_NAME, QSS_PATH
from ui.main_window import MainWindow

# High-DPI / Retina before QApplication is constructed
if hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def _apply_theme(app: QApplication):
    app.setStyle("Fusion")
    if QSS_PATH.exists():
        app.setStyleSheet(QSS_PATH.read_text(encoding="utf-8"))


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
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
