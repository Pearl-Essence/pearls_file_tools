"""Confirmation dialog for file organization conflicts."""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QCheckBox, QListWidget)
from PyQt5.QtCore import Qt
from typing import List


class ConfirmDialog(QDialog):
    """Dialog for confirming file organization actions when folder exists."""

    def __init__(self, folder_name: str, subdir: str, files: List[str], parent=None):
        """
        Initialize the confirm dialog.

        Args:
            folder_name: Name of the target folder
            subdir: Subdirectory path
            files: List of filenames to be moved
            parent: Parent widget
        """
        super().__init__(parent)
        self.folder_name = folder_name
        self.subdir = subdir
        self.files = files
        self.selected_action = None
        self.apply_to_all = False

        self.setup_ui()

    def setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle("Folder Exists")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout()

        # Message
        message = QLabel(
            f"<b>The folder '{self.folder_name}' already exists in:</b><br>"
            f"{self.subdir}<br><br>"
            f"What would you like to do with these files?"
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        # File list
        file_list_label = QLabel(f"<b>Files to organize ({len(self.files)}):</b>")
        layout.addWidget(file_list_label)

        self.file_list = QListWidget()
        self.file_list.addItems(self.files)
        layout.addWidget(self.file_list)

        # Apply to all checkbox
        self.apply_to_all_checkbox = QCheckBox("Apply this choice to all remaining conflicts")
        layout.addWidget(self.apply_to_all_checkbox)

        # Buttons
        button_layout = QHBoxLayout()

        self.merge_button = QPushButton("Merge")
        self.merge_button.setToolTip("Move files into the existing folder")
        self.merge_button.clicked.connect(self.on_merge)
        button_layout.addWidget(self.merge_button)

        self.skip_button = QPushButton("Skip")
        self.skip_button.setToolTip("Don't move these files")
        self.skip_button.clicked.connect(self.on_skip)
        button_layout.addWidget(self.skip_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Cancel the entire operation")
        self.cancel_button.clicked.connect(self.on_cancel)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Set focus to merge button
        self.merge_button.setFocus()

    def on_merge(self):
        """Handle merge button click."""
        self.selected_action = "merge"
        self.apply_to_all = self.apply_to_all_checkbox.isChecked()
        self.accept()

    def on_skip(self):
        """Handle skip button click."""
        self.selected_action = "skip"
        self.apply_to_all = self.apply_to_all_checkbox.isChecked()
        self.accept()

    def on_cancel(self):
        """Handle cancel button click."""
        self.selected_action = "cancel"
        self.apply_to_all = False
        self.reject()

    def get_result(self):
        """
        Get the user's choice.

        Returns:
            Tuple of (action: str, apply_to_all: bool)
        """
        return self.selected_action, self.apply_to_all
