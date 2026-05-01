"""Studio Tools split — v0.15 visual refresh.

Six lightweight wrapper tabs that replace the single StudioToolsTab.
Each wrapper composes the corresponding inner pane class (kept byte-identical
in studio_tools_tab.py) and adds the v0.15 chrome (TabHeader strip).

  StaleFilesTab     — wraps _StaleFilesPane
  StorageReportTab  — wraps _StoragePane
  TrashTab          — wraps _TrashPane
  NLEBackupTab      — wraps _NLEBackupPane
  ExportWatcherTab  — wraps _ExportWatcherPane
  ColdStorageTab    — wraps _ArchivePane (lives under 05 ARCHIVE in the sidebar)

The inner panes own their own `dir_selector`, settings persistence, and
worker wiring; this file only adds presentational chrome and mounts the
panes into the v0.15 layout (24/20 padding, 16 spacing).
"""

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ui.tabs.base_tab import BaseTab
from ui.tabs.studio_tools_tab import (
    _ArchivePane, _ExportWatcherPane, _NLEBackupPane, _StaleFilesPane,
    _StoragePane, _TrashPane,
)
from ui.widgets.tab_header import TabHeader


# ─────────────────────────────────────────────────────────────────────────────
# Wrapper helpers
# ─────────────────────────────────────────────────────────────────────────────

def _shell(host: QWidget, eyebrow: str, title: str, subtitle: str,
           inner: QWidget) -> QVBoxLayout:
    """Standard v0.15 outer layout: 24/20 padding, header strip, then content."""
    root = QVBoxLayout(host)
    root.setContentsMargins(24, 20, 24, 20)
    root.setSpacing(16)
    root.addWidget(TabHeader(eyebrow=eyebrow, title=title, subtitle=subtitle))
    root.addWidget(inner, stretch=1)
    return root


# ─────────────────────────────────────────────────────────────────────────────
# 03 · MAINTAIN tabs
# ─────────────────────────────────────────────────────────────────────────────

class StaleFilesTab(BaseTab):
    """Detect and soft-delete stale, temp, zero-byte, or empty items."""

    def get_tab_name(self) -> str:
        return "Stale Files"

    def setup_ui(self):
        self._inner = _StaleFilesPane(self.config)
        _shell(
            self,
            eyebrow="03 · MAINTAIN · STALE FILES",
            title="Stale Files",
            subtitle="Detect and remove stale, temporary, zero-byte, or unused items.",
            inner=self._inner,
        )

    def load_settings(self):
        directory = self.config.get_tab_directory('studio_tools')
        if directory and Path(directory).is_dir():
            self._inner.dir_selector.set_directory(directory)

    def save_settings(self):
        directory = self._inner.dir_selector.get_directory()
        if directory:
            self.config.set_tab_directory('studio_tools', directory)


class StorageReportTab(BaseTab):
    """Storage usage report by subfolder and file category."""

    def get_tab_name(self) -> str:
        return "Storage Report"

    def setup_ui(self):
        self._inner = _StoragePane(self.config)
        _shell(
            self,
            eyebrow="03 · MAINTAIN · STORAGE REPORT",
            title="Storage Report",
            subtitle="Break down disk usage by subfolder and file category.",
            inner=self._inner,
        )

    def load_settings(self):
        directory = self.config.get_tab_directory('studio_tools')
        if directory and Path(directory).is_dir():
            self._inner.dir_selector.set_directory(directory)

    def save_settings(self):
        # Source dir is shared across studio tabs; StaleFilesTab persists it.
        return


class TrashTab(BaseTab):
    """View, restore, or purge items in .pearls_trash/."""

    def get_tab_name(self) -> str:
        return "Trash"

    def setup_ui(self):
        self._inner = _TrashPane(self.config)
        _shell(
            self,
            eyebrow="03 · MAINTAIN · TRASH",
            title="Trash",
            subtitle="Restore or permanently delete items from the local trash.",
            inner=self._inner,
        )

    def load_settings(self):
        directory = self.config.get_tab_directory('studio_tools')
        if directory and Path(directory).is_dir():
            self._inner.dir_selector.set_directory(directory)
            self._inner._load_trash(directory)

    def save_settings(self):
        return


class NLEBackupTab(BaseTab):
    """Backup project files for DaVinci, FCP, Premiere Pro, and more."""

    def get_tab_name(self) -> str:
        return "NLE Backup"

    def setup_ui(self):
        self._inner = _NLEBackupPane(self.config)
        _shell(
            self,
            eyebrow="03 · MAINTAIN · NLE BACKUP",
            title="NLE Backup",
            subtitle="Snapshot Resolve, FCP, and Premiere project files to a safe location.",
            inner=self._inner,
        )

    def load_settings(self):
        self._inner.load_settings()

    def save_settings(self):
        self._inner.save_settings()


class ExportWatcherTab(BaseTab):
    """Watch export folders and route incoming renders by name pattern."""

    def get_tab_name(self) -> str:
        return "Export Watcher"

    def setup_ui(self):
        self._inner = _ExportWatcherPane(self.config)
        _shell(
            self,
            eyebrow="03 · MAINTAIN · EXPORT WATCHER",
            title="Export Watcher",
            subtitle="Watch render output folders and route files by naming pattern.",
            inner=self._inner,
        )

    def load_settings(self):
        self._inner.load_settings()

    def save_settings(self):
        self._inner.save_settings()


# ─────────────────────────────────────────────────────────────────────────────
# 05 · ARCHIVE tabs
# ─────────────────────────────────────────────────────────────────────────────

class ColdStorageTab(BaseTab):
    """Archive a project folder to a destination with manifest + verify."""

    def get_tab_name(self) -> str:
        return "Cold Storage"

    def setup_ui(self):
        self._inner = _ArchivePane(self.config)
        _shell(
            self,
            eyebrow="05 · ARCHIVE · COLD STORAGE",
            title="Cold Storage",
            subtitle="Archive a finished project to LTO or external storage with hash verification.",
            inner=self._inner,
        )

    def load_settings(self):
        # _ArchivePane is wizard-based; nothing persistent at the tab level.
        return

    def save_settings(self):
        return
