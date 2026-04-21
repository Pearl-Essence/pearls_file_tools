"""File list widget with checkboxes for Pearl's File Tools."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                            QLabel, QCheckBox, QScrollArea, QFrame)
from PyQt5.QtCore import Qt
from pathlib import Path
from typing import List, Dict, Optional


class FileListWidget(QWidget):
    """Reusable widget for displaying a list of files with checkboxes."""

    def __init__(self, parent=None):
        """
        Initialize the file list widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.file_items: List[Dict] = []  # List of {path: Path, var: bool, widget: QCheckBox}
        self.last_clicked_index: Optional[int] = None

        self.setup_ui()

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Control buttons
        controls_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        controls_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        controls_layout.addWidget(self.deselect_all_btn)

        self.invert_btn = QPushButton("Invert Selection")
        self.invert_btn.clicked.connect(self.invert_selection)
        controls_layout.addWidget(self.invert_btn)

        controls_layout.addStretch()

        self.count_label = QLabel("No files loaded")
        controls_layout.addWidget(self.count_label)

        layout.addLayout(controls_layout)

        # Scrollable file list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.list_widget = QFrame()
        self.list_layout = QVBoxLayout()
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_widget.setLayout(self.list_layout)

        scroll.setWidget(self.list_widget)
        layout.addWidget(scroll, stretch=1)

        self.setLayout(layout)

    def set_files(self, files: List[Path], relative_to: Optional[Path] = None):
        """
        Set the list of files to display.

        Args:
            files: List of file paths
            relative_to: Optional base path for displaying relative paths
        """
        # Clear existing items
        self.clear()

        # Add new items
        for idx, filepath in enumerate(files):
            # Determine display name
            if relative_to:
                try:
                    display_name = str(filepath.relative_to(relative_to))
                except ValueError:
                    display_name = filepath.name
            else:
                display_name = filepath.name

            # Create checkbox
            checkbox = QCheckBox(display_name)
            checkbox.setChecked(True)

            # Bind click event for shift-click support
            checkbox.mousePressEvent = lambda event, i=idx: self.on_file_click(event, i)

            self.list_layout.addWidget(checkbox)

            # Store item data
            self.file_items.append({
                'path': filepath,
                'checked': True,
                'widget': checkbox
            })

        self.update_count()

    def on_file_click(self, event, index: int):
        """
        Handle file checkbox click with shift-click support.

        Args:
            event: Mouse event
            index: Index of clicked item
        """
        # Check if shift key is pressed
        if event.modifiers() & Qt.ShiftModifier:
            if self.last_clicked_index is not None and self.last_clicked_index != index:
                # Toggle all items between last clicked and current
                start = min(self.last_clicked_index, index)
                end = max(self.last_clicked_index, index)

                # Determine target state (same as the clicked item will become)
                target_state = not self.file_items[index]['widget'].isChecked()

                for i in range(start, end + 1):
                    self.file_items[i]['widget'].setChecked(target_state)
                    self.file_items[i]['checked'] = target_state

        # Let the normal click behavior proceed
        QCheckBox.mousePressEvent(self.file_items[index]['widget'], event)
        self.file_items[index]['checked'] = self.file_items[index]['widget'].isChecked()

        self.last_clicked_index = index

    def select_all(self):
        """Select all files."""
        for item in self.file_items:
            item['widget'].setChecked(True)
            item['checked'] = True

    def deselect_all(self):
        """Deselect all files."""
        for item in self.file_items:
            item['widget'].setChecked(False)
            item['checked'] = False

    def invert_selection(self):
        """Invert the current selection."""
        for item in self.file_items:
            new_state = not item['widget'].isChecked()
            item['widget'].setChecked(new_state)
            item['checked'] = new_state

    def get_selected_files(self) -> List[Path]:
        """
        Get list of selected files.

        Returns:
            List of selected file paths
        """
        return [
            item['path']
            for item in self.file_items
            if item['widget'].isChecked()
        ]

    def get_all_files(self) -> List[Path]:
        """
        Get list of all files (selected or not).

        Returns:
            List of all file paths
        """
        return [item['path'] for item in self.file_items]

    def clear(self):
        """Clear all files from the list."""
        # Remove all widgets
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.file_items.clear()
        self.last_clicked_index = None
        self.update_count()

    def update_count(self):
        """Update the file count label."""
        total = len(self.file_items)
        selected = sum(1 for item in self.file_items if item['widget'].isChecked())
        self.count_label.setText(f"{selected}/{total} files selected")
