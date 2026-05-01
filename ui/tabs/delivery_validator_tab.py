"""Spec Validator tab — v0.17 visual refresh.

Top-level sidebar destination split out of DeliveryTab. Reuses the existing
_ValidatorPane logic (worker contract, profile builder, results rendering)
via composition; only the chrome and empty-state hero are new.

The empty state shows the floating amber orb illustration that was the
showcase in the original mockup. Once a folder is picked, the orb hides
and the validation rules + results panels swap in.
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QPushButton,
    QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from branding import ICONS_DIR
from ui.tabs.base_tab import BaseTab
from ui.tabs.delivery_tab import _ValidatorPane
from ui.widgets.panel import Panel
from ui.widgets.path_card import PathCard
from ui.widgets.tab_header import TabHeader


# ─────────────────────────────────────────────────────────────────────────────
# Empty-state hero
# ─────────────────────────────────────────────────────────────────────────────

class _ValidatorHero(QWidget):
    """Amber-orb centered empty state shown before a folder is chosen."""

    folder_picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setSpacing(12)

        v.addStretch(2)

        orb_path = ICONS_DIR / "empty-validator.svg"
        if orb_path.exists():
            orb = QSvgWidget(str(orb_path))
            orb.setFixedSize(120, 120)
            v.addWidget(orb, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            placeholder = QLabel("◉")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #E8B547; font-size: 96px;")
            v.addWidget(placeholder)

        eye = QLabel("AWAITING A DELIVERY")
        eye.setObjectName("eyebrow")
        eye.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(eye)

        title = QLabel("Drop a delivery folder here.")
        title.setObjectName("h1")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        sub = QLabel(
            "We'll verify every filename, codec, hash, and sidecar against the chosen\n"
            "spec — and refuse to package what isn't ready."
        )
        sub.setObjectName("h2")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        v.addWidget(sub)

        # CTA — opens a folder picker via the path-card on the parent.
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cta = QPushButton("Choose folder…")
        cta.setProperty("role", "primary")
        cta.setMinimumHeight(34)
        cta.clicked.connect(self._on_choose)
        btn_row.addWidget(cta)
        btn_row.addStretch()
        v.addLayout(btn_row)

        v.addStretch(3)

    def _on_choose(self):
        from PySide6.QtWidgets import QFileDialog
        chosen = QFileDialog.getExistingDirectory(self, "Choose delivery folder")
        if chosen:
            self.folder_picked.emit(chosen)


# ─────────────────────────────────────────────────────────────────────────────
# SpecValidatorTab
# ─────────────────────────────────────────────────────────────────────────────

class SpecValidatorTab(BaseTab):
    """Spec Validator — v0.17 chrome around the existing validator logic."""

    # Re-emits the inner pane's pass/fail so PackageExportTab can listen.
    validation_passed = Signal(bool)

    def get_tab_name(self) -> str:
        return "Spec Validator"

    # ─────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addWidget(self._build_source())

        # The body swaps between hero (empty state) and the inner validator
        # pane (active state) via QStackedWidget.
        self._body = QStackedWidget()
        self._hero = _ValidatorHero()
        self._hero.folder_picked.connect(self._on_folder_picked)

        self._inner = _ValidatorPane(self.config)
        self._inner.validation_passed.connect(self.validation_passed)

        self._body.addWidget(self._hero)
        self._body.addWidget(self._inner)
        self._body.setCurrentWidget(self._hero)
        root.addWidget(self._body, stretch=1)

    def _build_header(self) -> QWidget:
        header = TabHeader(
            eyebrow="04 · DELIVER · SPEC VALIDATOR",
            title="Spec Validator",
            subtitle="Test the offering before it leaves the threshold.",
        )
        self.btn_run = header.add_action(
            "Run validation",
            on_click=self._run_validation,
            primary=True,
            enabled=False,
        )
        return header

    def _build_source(self) -> QWidget:
        self.path_card = PathCard("FOLDER TO VALIDATE")
        self.path_card.path_changed.connect(self._on_folder_picked)
        return self.path_card

    # ─────────────────────────────────────────────────────────────────────
    # Wiring
    # ─────────────────────────────────────────────────────────────────────
    def _on_folder_picked(self, path: str):
        if not path:
            return
        # Mirror selection into both surfaces (the path card + the inner
        # pane's own DirectorySelectorWidget so its _run() picks it up).
        self.path_card.set_path(path)
        self._inner.dir_selector.set_directory(path)
        self._body.setCurrentWidget(self._inner)
        self.btn_run.setEnabled(True)

    def _run_validation(self):
        self._inner._run()
        self.emit_status("Validation in progress…")

    def get_directory(self) -> str:
        """Forward to the inner pane so cross-tab callers can pre-fill Package."""
        return self._inner.dir_selector.get_directory()

    # ─────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────
    def load_settings(self):
        directory = self.config.get_tab_directory('delivery')
        if directory and Path(directory).is_dir():
            self._on_folder_picked(directory)

    def save_settings(self):
        directory = self._inner.dir_selector.get_directory()
        if directory and directory != str(Path.home()):
            self.config.set_tab_directory('delivery', directory)
