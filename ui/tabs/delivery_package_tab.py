"""Package & Export tab — v0.16 visual refresh.

Top-level sidebar destination split out of DeliveryTab. Wraps the four
non-validator panes (Package, Duplicates, Handoff, Export) in an inner
QTabWidget under a single TabHeader.

Cross-tab wiring: when SpecValidatorTab emits validation_passed(True),
main_window forwards the validator's source directory here via
``set_source_from_validator()`` so the user's first stop in this tab is
already pre-filled.
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from ui.tabs.base_tab import BaseTab
from ui.tabs.delivery_tab import (
    _DuplicatesPane, _ExportPane, _HandoffPane, _PackagePane,
)
from ui.widgets.tab_header import TabHeader


class PackageExportTab(BaseTab):
    """Package & Export — wraps the four non-validator delivery panes."""

    def get_tab_name(self) -> str:
        return "Package & Export"

    # ─────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        root.addWidget(self._build_header())

        self._inner_tabs = QTabWidget()
        self._inner_tabs.setObjectName("packageInnerTabs")

        self._package_pane = _PackagePane(self.config)
        self._dupes_pane = _DuplicatesPane(self.config)
        self._handoff_pane = _HandoffPane(self.config)
        self._export_pane = _ExportPane(self.config)

        self._inner_tabs.addTab(self._package_pane, "Package")
        self._inner_tabs.addTab(self._dupes_pane,   "Duplicates")
        self._inner_tabs.addTab(self._handoff_pane, "Handoff")
        self._inner_tabs.addTab(self._export_pane,  "Export")

        root.addWidget(self._inner_tabs, stretch=1)

    def _build_header(self) -> QWidget:
        header = TabHeader(
            eyebrow="04 · DELIVER · PACKAGE & EXPORT",
            title="Package & Export",
            subtitle="Build delivery zips, find duplicates, generate handoff sheets and CSV manifests.",
        )
        return header

    # ─────────────────────────────────────────────────────────────────────
    # Cross-tab API
    # ─────────────────────────────────────────────────────────────────────
    def set_source_from_validator(self, path: str):
        """Pre-fill all four panes' source directory + activate Package tab."""
        if not path or not Path(path).is_dir():
            return
        self._package_pane.set_source_from_validator(path)
        self._dupes_pane.dir_selector.set_directory(path)
        self._handoff_pane.dir_selector.set_directory(path)
        self._export_pane.set_directory(path)
        self._inner_tabs.setCurrentWidget(self._package_pane)
        self.emit_status("Validation passed — delivery zip is now available")

    # ─────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────
    def load_settings(self):
        directory = self.config.get_tab_directory('delivery')
        if directory and Path(directory).is_dir():
            self._dupes_pane.dir_selector.set_directory(directory)
            self._handoff_pane.dir_selector.set_directory(directory)
            self._export_pane.set_directory(directory)
            self._package_pane.set_source_from_validator(directory)

    def save_settings(self):
        # Source directory is owned by SpecValidatorTab; nothing to save here
        # beyond what the inner panes' own callers persisted via the shared
        # 'delivery' tab-directory key.
        return
