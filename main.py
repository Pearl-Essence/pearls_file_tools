#!/usr/bin/env python3
"""
Pearl's File Tools - Unified file management application.

Entry point for the application.
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt
from ui.main_window import MainWindow
from constants import THEME_DARK


def apply_dark_theme(app: QApplication):
    """
    Apply dark theme to the application.

    Args:
        app: QApplication instance
    """
    app.setStyle("Fusion")

    # Create dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)

    app.setPalette(palette)


def main():
    """Main entry point for Pearl's File Tools."""
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("Pearl's File Tools")
    app.setOrganizationName("Pearl")

    # Apply dark theme
    apply_dark_theme(app)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run application
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
