"""Preview dialog for Pearl's File Tools."""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                            QTextEdit, QLabel)
from PyQt5.QtCore import Qt
from typing import List, Tuple


class PreviewDialog(QDialog):
    """Dialog to preview filename changes before applying."""

    def __init__(self, preview_data: List[Tuple[str, str]], parent=None):
        """
        Initialize the preview dialog.

        Args:
            preview_data: List of (old_name, new_name) tuples
            parent: Parent widget
        """
        super().__init__(parent)
        self.preview_data = preview_data

        self.setWindowTitle("Preview Changes")
        self.setModal(True)
        self.resize(800, 500)

        self.setup_ui()
        self.populate_preview()

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()

        # Header
        header = QLabel(f"Preview of filename changes ({len(self.preview_data)} files):")
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header)

        # Text widget for preview
        self.text_widget = QTextEdit()
        self.text_widget.setReadOnly(True)
        self.text_widget.setFontFamily("Courier")
        layout.addWidget(self.text_widget, stretch=1)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def populate_preview(self):
        """Populate the preview text widget."""
        self.text_widget.clear()

        # Add header
        self.text_widget.append("=" * 80)
        self.text_widget.append("")

        # Add each file change
        for old_name, new_name in self.preview_data:
            # Check if name actually changed
            if old_name != new_name:
                self.text_widget.append(f"  {old_name}")
                self.text_widget.append(f"→ {new_name}")
                self.text_widget.append("")
            else:
                # Show unchanged files in gray/dimmed
                self.text_widget.append(f"  {old_name} (unchanged)")
                self.text_widget.append("")

        self.text_widget.append("=" * 80)

        # Scroll to top
        self.text_widget.moveCursor(self.text_widget.textCursor().Start)
