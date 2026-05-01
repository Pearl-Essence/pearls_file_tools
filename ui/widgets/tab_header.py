"""TabHeader — standard top strip for v0.14 tabs.

Layout:

    01 · INGEST · OFFLOAD                  [ghost btn] [ghost] [PRIMARY]
    Offload
    Copy and verify camera media …

Use:
    header = TabHeader(eyebrow="01 · INGEST · OFFLOAD",
                       title="Offload",
                       subtitle="Copy and verify camera media…")
    header.add_action("Analyze",     on_click=self._analyze)
    header.add_action("Start ingest", on_click=self._start, primary=True,
                      object_name="btn_start")
"""

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class TabHeader(QWidget):
    """Reusable eyebrow + h1 + h2 + right-aligned action-button strip."""

    def __init__(
        self,
        eyebrow: str,
        title: str,
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(8)

        col = QVBoxLayout()
        col.setSpacing(2)
        self._eyebrow = QLabel(eyebrow)
        self._eyebrow.setObjectName("eyebrow")
        self._title = QLabel(title)
        self._title.setObjectName("h1")
        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("h2")
        if not subtitle:
            self._subtitle.hide()
        col.addWidget(self._eyebrow)
        col.addWidget(self._title)
        col.addWidget(self._subtitle)
        self._row.addLayout(col, stretch=1)

        # Actions are appended to the right of the stretch.
        self._action_widgets: list[QPushButton] = []

    # ── public API ────────────────────────────────────────────────────────
    def set_eyebrow(self, text: str) -> None:
        self._eyebrow.setText(text)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

    def add_action(
        self,
        label: str,
        on_click: Optional[Callable[[], None]] = None,
        *,
        primary: bool = False,
        danger: bool = False,
        enabled: bool = True,
        tooltip: str = "",
        object_name: str = "",
    ) -> QPushButton:
        """Append an action button. Returns the button so callers can wire state."""
        btn = QPushButton(label)
        btn.setMinimumHeight(34)
        if primary:
            btn.setProperty("role", "primary")
        elif danger:
            btn.setProperty("role", "danger")
        else:
            btn.setObjectName("ghostBtn")
        if object_name:
            btn.setObjectName(object_name)
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setEnabled(enabled)
        if on_click is not None:
            btn.clicked.connect(on_click)
        self._row.addWidget(btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._action_widgets.append(btn)
        return btn
