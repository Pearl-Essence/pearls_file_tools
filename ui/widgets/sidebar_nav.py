"""SidebarNav — left rail with section headers, icon nav items, badges.

Driven by the NAV_TREE constant in branding.py. Emits ``activated(str)`` with
the factory_key when the user selects an item, so main_window can route the
selection without this widget knowing anything about tabs or dialogs.
"""

from typing import Dict, Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QListWidget, QListWidgetItem


_ROLE_KEY     = Qt.UserRole + 1   # the factory_key string, or "" for headers
_ROLE_ISHEAD  = Qt.UserRole + 2   # bool


class SidebarNav(QListWidget):
    """Left-rail navigation for the sidebar shell."""

    activated = Signal(str)   # factory_key

    def __init__(self, nav_tree, icons_dir, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setIconSize(QSize(16, 16))
        self.setFrameShape(QFrame.NoFrame)
        self.setSpacing(0)
        self.setUniformItemSizes(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._icons_dir = icons_dir
        self._key_to_row: Dict[str, int] = {}

        self._populate(nav_tree)
        self.currentRowChanged.connect(self._on_row_changed)

    # ── construction ──────────────────────────────────────────────────────
    def _populate(self, nav_tree):
        for section_label, items in nav_tree:
            self._add_header(section_label)
            for label, icon_filename, factory_key in items:
                self._add_item(label, icon_filename, factory_key)

    def _add_header(self, label: str):
        item = QListWidgetItem(label)
        item.setData(_ROLE_ISHEAD, True)
        item.setData(_ROLE_KEY, "")
        # Disable selection without disabling the row entirely (which would
        # apply the wrong QSS pseudo-state). Use NoItemFlags = unselectable.
        item.setFlags(Qt.NoItemFlags)
        self.addItem(item)

    def _add_item(self, label: str, icon_filename: str, factory_key: str):
        icon_path = self._icons_dir / icon_filename
        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        item = QListWidgetItem(icon, label)
        item.setData(_ROLE_ISHEAD, False)
        item.setData(_ROLE_KEY, factory_key)
        self._key_to_row[factory_key] = self.count()
        self.addItem(item)

    # ── public API ────────────────────────────────────────────────────────
    def set_badge(self, factory_key: str, count: Optional[int]):
        """Set or clear a numeric badge on a nav item.

        Implemented by appending '  (N)' to the label — minimal but works
        without custom delegates. Replace with a delegate in Phase C for
        the boxed gold pill look.
        """
        row = self._key_to_row.get(factory_key)
        if row is None:
            return
        item = self.item(row)
        # Strip any prior badge.
        base = item.text().split("   ·")[0].rstrip()
        item.setText(base if not count else f"{base}   · {count}")

    def select_key(self, factory_key: str):
        row = self._key_to_row.get(factory_key)
        if row is not None:
            self.setCurrentRow(row)

    def current_key(self) -> str:
        """Return the factory_key of the selected item, or '' if none."""
        item = self.currentItem()
        if item is None:
            return ""
        return item.data(_ROLE_KEY) or ""

    # ── slots ─────────────────────────────────────────────────────────────
    def _on_row_changed(self, row: int):
        if row < 0 or row >= self.count():
            return
        item = self.item(row)
        if item.data(_ROLE_ISHEAD):
            # Skip headers — user can't actually select these but be defensive.
            return
        key = item.data(_ROLE_KEY) or ""
        if key:
            self.activated.emit(key)
