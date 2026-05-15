"""Sync Check + Watch Folders embedded as real tab panes.

These two destinations were previously launched as modal QDialogs from the
sidebar. v0.17 promotes them to first-class panes mounted in the main
QStackedWidget, so they live alongside the rest of the MAINTAIN section.

Strategy: instantiate the existing QDialog subclasses with no parent (so
they don't behave modally) and embed them as ordinary QWidgets inside a
TabHeader-decorated shell. The dialogs' internal Close buttons are hidden
since there's nothing to close — the user navigates away via the sidebar.
"""

from typing import Callable

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from ui.tabs.base_tab import BaseTab
from ui.widgets.tab_header import TabHeader


def _hide_close_button(widget: QWidget) -> None:
    """Walk children and hide any QPushButton labelled 'Close'."""
    for btn in widget.findChildren(QPushButton):
        if btn.text().strip().lower() == "close":
            btn.hide()


def _shell(host: QWidget, eyebrow: str, title: str, subtitle: str, inner: QWidget) -> QVBoxLayout:
    """Standard v0.17 outer layout — same helper used in studio_tabs."""
    root = QVBoxLayout(host)
    root.setContentsMargins(24, 20, 24, 20)
    root.setSpacing(16)
    root.addWidget(TabHeader(eyebrow=eyebrow, title=title, subtitle=subtitle))
    root.addWidget(inner, stretch=1)
    return root


# ─────────────────────────────────────────────────────────────────────────────
# Sync Check
# ─────────────────────────────────────────────────────────────────────────────


class SyncCheckTab(BaseTab):
    """Multi-site sync diff between two directory trees."""

    def get_tab_name(self) -> str:
        return "Sync Check"

    def setup_ui(self):
        # Lazy import keeps cycle-free imports between maintain_panes and the
        # dialogs (which don't depend on this file).
        from ui.dialogs.sync_dialog import SyncDialog

        # Pass parent=None so it doesn't become modal-anchored to the main window.
        self._inner = SyncDialog(self.config)
        _hide_close_button(self._inner)
        _shell(
            self,
            eyebrow="03 · MAINTAIN · SYNC CHECK",
            title="Sync Check",
            subtitle="Compare two directory trees and reconcile differences file-by-file.",
            inner=self._inner,
        )

    def load_settings(self):
        # SyncDialog has no persistent settings of its own.
        return

    def save_settings(self):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Watch Folders
# ─────────────────────────────────────────────────────────────────────────────


class WatchFoldersTab(BaseTab):
    """Manage watch-folder rules and view the arrival log."""

    def get_tab_name(self) -> str:
        return "Watch Folders"

    def setup_ui(self):
        from ui.dialogs.watch_manager_dialog import WatchManagerDialog

        self._inner = WatchManagerDialog(self.config)
        _hide_close_button(self._inner)
        _shell(
            self,
            eyebrow="03 · MAINTAIN · WATCH FOLDERS",
            title="Watch Folders",
            subtitle="Watch incoming directories and apply naming rules as files arrive.",
            inner=self._inner,
        )

    def set_indicator_callback(self, cb: Callable[[bool], None]) -> None:
        """Wire the status-bar watching dot. Called by main_window during mount."""
        self._inner._update_indicator_cb = cb

    def load_settings(self):
        # The dialog already calls load_rules() in its __init__, and it
        # handles its own persistence on closeEvent.
        return

    def save_settings(self):
        # Persist the watch rules table on app shutdown — the dialog's
        # closeEvent normally does this, but we never close it now.
        if hasattr(self._inner, "save_rules"):
            try:
                self._inner.save_rules()
            except Exception:
                pass
