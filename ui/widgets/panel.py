"""Panel — floating dark card with rounded corners and a soft drop shadow.

Set objectName='panel' (done automatically) so QSS rule
``QFrame#panel { ... }`` applies.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect


class Panel(QFrame):
    """Reusable raised-card container."""

    def __init__(self, parent=None, *, shadow: bool = True):
        super().__init__(parent)
        self.setObjectName("panel")
        if shadow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(24)
            effect.setColor(QColor(0, 0, 0, 160))
            effect.setOffset(0, 4)
            self.setGraphicsEffect(effect)
