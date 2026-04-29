"""PathCard — clickable source/destination card for ingest, delivery, archive.

Folder icon + name + full path + status pill + metrics line.
Whole card is the click target for opening a folder picker.
"""

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout

from ui.widgets.panel import Panel
from ui.widgets.pill import Pill, KIND_MUTED, KIND_OK


class PathCard(Panel):
    """Card representing a chosen source or destination folder.

    Emits ``path_changed(str)`` when the user picks a new folder.
    """

    path_changed = pyqtSignal(str)

    def __init__(self, role: str, parent=None):
        """``role`` is a label like 'SOURCE' or 'DESTINATION'."""
        super().__init__(parent)
        self._role = role
        self._path: Optional[Path] = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        eyebrow = QLabel(self._role)
        eyebrow.setObjectName("eyebrow")
        outer.addWidget(eyebrow)

        mid = QHBoxLayout()
        mid.setSpacing(12)

        # Glyph placeholder — swap for QIcon('icons/folder.svg') in Phase C
        self._icon = QLabel("▣")
        self._icon.setObjectName("cardIcon")
        self._icon.setFixedWidth(28)
        mid.addWidget(self._icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._name = QLabel("— No folder selected —")
        self._name.setObjectName("cardTitle")
        self._sub = QLabel("Click to choose a folder")
        self._sub.setObjectName("cardSub")
        text_col.addWidget(self._name)
        text_col.addWidget(self._sub)
        mid.addLayout(text_col, stretch=1)

        self._pill = Pill("EMPTY", KIND_MUTED)
        mid.addWidget(self._pill, alignment=Qt.AlignRight | Qt.AlignVCenter)
        outer.addLayout(mid)

        self._metrics = QLabel("")
        self._metrics.setObjectName("cardMetrics")
        outer.addWidget(self._metrics)

        self.setCursor(Qt.PointingHandCursor)

    # ── public API ────────────────────────────────────────────────────────
    def set_path(self, path: str):
        if not path:
            return
        p = Path(path)
        self._path = p
        self._name.setText(p.name or str(p))
        self._sub.setText(str(p))
        self._pill.set_state("PRESENT", KIND_OK)

    def set_metrics(self, text: str):
        self._metrics.setText(text)

    def get_path(self) -> Optional[Path]:
        return self._path

    # ── interaction ───────────────────────────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._browse()
        super().mousePressEvent(ev)

    def _browse(self):
        start = str(self._path) if self._path else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, f"Choose {self._role.lower()}", start
        )
        if chosen:
            self.set_path(chosen)
            self.path_changed.emit(chosen)
