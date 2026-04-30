"""StubPane — empty-state placeholder for sidebar items not yet implemented."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class StubPane(QWidget):
    """Centered "Coming soon" pane for incomplete sidebar destinations."""

    def __init__(self, title: str, blurb: str = "Coming in Pearl 0.12", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        eyebrow = QLabel(blurb.upper())
        eyebrow.setObjectName("eyebrow")
        eyebrow.setAlignment(Qt.AlignCenter)

        h1 = QLabel(title)
        h1.setObjectName("h1")
        h1.setAlignment(Qt.AlignCenter)

        sub = QLabel("This destination is reserved. Functionality lands in a later release.")
        sub.setObjectName("h2")
        sub.setAlignment(Qt.AlignCenter)

        layout.addStretch(1)
        layout.addWidget(eyebrow)
        layout.addWidget(h1)
        layout.addWidget(sub)
        layout.addStretch(2)
