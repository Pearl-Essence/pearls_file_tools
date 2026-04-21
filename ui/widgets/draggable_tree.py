"""Draggable tree widget for file organization."""

from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData
from PyQt5.QtGui import QDrag
from pathlib import Path
from typing import List, Optional


class DraggableTreeWidget(QTreeWidget):
    """Tree widget with drag-and-drop support for file organization."""

    # Signal emitted when files are dropped
    files_dropped = pyqtSignal(list, object)  # files: List[Path], target_item: QTreeWidgetItem

    def __init__(self, parent=None):
        """Initialize the draggable tree widget."""
        super().__init__(parent)

        # Enable drag and drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.DragDrop)

        # Enable multiple selection
        self.setSelectionMode(QTreeWidget.ExtendedSelection)

    def startDrag(self, supportedActions):
        """
        Start drag operation.

        Args:
            supportedActions: Qt.DropActions supported
        """
        # Get selected items
        selected_items = self.selectedItems()
        if not selected_items:
            return

        # Only allow dragging file items (children), not group/subdir items
        file_items = []
        for item in selected_items:
            if item.parent() is not None:  # Has a parent, so it's a file item
                file_items.append(item)

        if not file_items:
            return

        # Create mime data with file paths
        mime_data = QMimeData()
        file_paths = []

        for item in file_items:
            file_path = item.data(0, Qt.UserRole)
            if file_path and isinstance(file_path, Path):
                file_paths.append(str(file_path))

        if not file_paths:
            return

        # Store paths as text (newline-separated)
        mime_data.setText('\n'.join(file_paths))

        # Create and execute drag
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec_(Qt.MoveAction)

    def dragEnterEvent(self, event):
        """
        Handle drag enter event.

        Args:
            event: QDragEnterEvent
        """
        # Accept if it has text mime data
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """
        Handle drag move event.

        Args:
            event: QDragMoveEvent
        """
        # Get the item under cursor
        item = self.itemAt(event.pos())

        # Only accept drops on group items (top-level or second-level)
        if item is not None:
            # Check if it's a group item (has no parent or parent is top-level)
            if item.parent() is None or item.parent().parent() is None:
                event.acceptProposedAction()
                return

        event.ignore()

    def dropEvent(self, event):
        """
        Handle drop event.

        Args:
            event: QDropEvent
        """
        # Get the target item
        target_item = self.itemAt(event.pos())

        if target_item is None:
            event.ignore()
            return

        # Ensure target is a group item (not a file item)
        # Groups have no parent or their parent is a top-level subdir
        if target_item.parent() is not None and target_item.parent().parent() is not None:
            # This is a file item, not a group
            event.ignore()
            return

        # Parse file paths from mime data
        mime_data = event.mimeData()
        if not mime_data.hasText():
            event.ignore()
            return

        file_paths_text = mime_data.text()
        file_paths = [Path(p) for p in file_paths_text.split('\n') if p.strip()]

        if not file_paths:
            event.ignore()
            return

        # Emit signal with dropped files and target
        self.files_dropped.emit(file_paths, target_item)

        event.acceptProposedAction()

    def mousePressEvent(self, event):
        """
        Handle mouse press event.

        Args:
            event: QMouseEvent
        """
        # If clicking on empty space, clear selection
        item = self.itemAt(event.pos())
        if item is None and event.button() == Qt.LeftButton:
            self.clearSelection()

        # Call parent implementation
        super().mousePressEvent(event)
