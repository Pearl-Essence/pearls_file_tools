"""Draggable tree widget for file organization."""

from PyQt5.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData, QPoint
from PyQt5.QtGui import QDrag
from pathlib import Path
from typing import List, Optional


class DraggableTreeWidget(QTreeWidget):
    """Tree widget with drag-and-drop support for file organization.

    Selection model:
    - Click                → select single item
    - Shift+click          → range select
    - Ctrl+click           → toggle individual item
    - Click already-selected + drag  → drag ALL selected items (selection preserved)
    - Click already-selected + release (no drag) → collapse to that single item

    Drag is initiated manually so Qt's rubber-band selector never fires.
    """

    files_dropped = pyqtSignal(list, object)  # List[Path], QTreeWidgetItem

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        # DropOnly: Qt never starts its own drag, no rubber-band conflict.
        # Drop events still arrive through dragEnterEvent / dropEvent.
        self.setDragDropMode(QTreeWidget.DropOnly)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)

        self._drag_start_pos: Optional[QPoint] = None
        self._drag_started: bool = False
        self._deferred_click_item: Optional[QTreeWidgetItem] = None

    # ── mouse event overrides ─────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_started = False
            item = self.itemAt(event.pos())

            if item is None:
                # Click on empty space — clear selection immediately
                self._deferred_click_item = None
                self.clearSelection()
                super().mousePressEvent(event)

            elif (item.isSelected() and
                  not (event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier))):
                # Click on an already-selected item with no modifier key.
                # This MIGHT be the start of a drag — defer the selection collapse.
                # If no drag happens, mouseReleaseEvent will collapse to single item.
                self._deferred_click_item = item
                # Do NOT call super() — that would collapse the selection right now.

            else:
                # Normal click (unselected item, or modifier held) → update normally
                self._deferred_click_item = None
                super().mousePressEvent(event)

        else:
            self._drag_start_pos = None
            self._deferred_click_item = None
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.LeftButton and
                not self._drag_started and
                self._deferred_click_item is not None):
            # Deferred click: drag never started, so now apply the selection collapse
            item = self._deferred_click_item
            self.clearSelection()
            if item:
                item.setSelected(True)

        self._deferred_click_item = None
        self._drag_start_pos = None
        self._drag_started = False
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) and self._drag_start_pos is not None:
            # We own this gesture — never let super() touch it.
            # Super's mouseMoveEvent runs Qt's rubberband selector which would
            # reset the shift-click range selection to only the items under the cursor.
            if not self._drag_started:
                distance = (event.pos() - self._drag_start_pos).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    self._drag_started = True
                    self._deferred_click_item = None
                    self._drag_start_pos = None
                    self.startDrag(Qt.MoveAction)
            return  # consume without forwarding to super

        if not self._drag_started:
            super().mouseMoveEvent(event)

    # ── drag ──────────────────────────────────────────────────────────────

    def startDrag(self, supportedActions):
        """Collect all selected file items and begin a drag operation."""
        selected_items = self.selectedItems()
        if not selected_items:
            return

        # Only drag leaf file items (items that have a parent)
        file_paths: List[str] = []
        for item in selected_items:
            if item.parent() is None:
                continue
            data = item.data(0, Qt.UserRole)
            # File item data: ('file', subdir_path, group_name, Path)
            if (data and isinstance(data, tuple) and
                    data[0] == 'file' and len(data) >= 4 and
                    isinstance(data[3], Path)):
                file_paths.append(str(data[3]))

        if not file_paths:
            return

        mime_data = QMimeData()
        mime_data.setText('\n'.join(file_paths))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec_(Qt.MoveAction)

    # ── drop events ───────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        item = self.itemAt(event.pos())
        if item is not None:
            # Accept drops on subdir items (depth 0) and group/unsorted items (depth 1)
            if item.parent() is None or item.parent().parent() is None:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        target_item = self.itemAt(event.pos())
        if target_item is None:
            event.ignore()
            return

        # Reject drops onto file items (depth ≥ 2)
        if (target_item.parent() is not None and
                target_item.parent().parent() is not None):
            event.ignore()
            return

        if not event.mimeData().hasText():
            event.ignore()
            return

        file_paths = [
            Path(p) for p in event.mimeData().text().split('\n') if p.strip()
        ]
        if not file_paths:
            event.ignore()
            return

        self.files_dropped.emit(file_paths, target_item)
        event.acceptProposedAction()
