"""Pill — small colored status badge.

The visual style comes from a Qt dynamic property ``pill`` ("ok", "warn",
"error", "muted") matched by selectors in pearl_dark.qss.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel


# Canonical kinds — keep in sync with QSS QLabel[pill="..."] selectors.
KIND_OK    = "ok"
KIND_WARN  = "warn"
KIND_ERROR = "error"
KIND_MUTED = "muted"


class Pill(QLabel):
    """Compact text label styled as a status pill."""

    def __init__(self, text: str = "", kind: str = KIND_MUTED, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_kind(kind)

    def set_kind(self, kind: str):
        """Change the pill's color category and trigger a restyle."""
        self.setProperty("pill", kind)
        # Dynamic-property changes don't auto-trigger restyle in Qt5.
        self.style().unpolish(self)
        self.style().polish(self)

    def set_state(self, text: str, kind: str):
        """Convenience — set both text and kind in one call."""
        self.setText(text)
        self.set_kind(kind)
