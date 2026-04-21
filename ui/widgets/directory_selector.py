"""Directory selector widget for Pearl's File Tools."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFileDialog, QCheckBox
from PyQt5.QtCore import pyqtSignal
from pathlib import Path


class DirectorySelectorWidget(QWidget):
    """Reusable widget for selecting a directory."""

    # Signals
    directory_changed = pyqtSignal(str)  # Emits the selected directory path

    def __init__(self, label_text: str = "Directory:", show_recursive: bool = False, parent=None):
        """
        Initialize the directory selector widget.

        Args:
            label_text: Label text to display
            show_recursive: Whether to show recursive checkbox
            parent: Parent widget
        """
        super().__init__(parent)
        self.last_directory = str(Path.home())
        self.show_recursive = show_recursive

        self.setup_ui(label_text)

    def setup_ui(self, label_text: str):
        """Setup the user interface."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Label
        label = QLabel(label_text)
        layout.addWidget(label)

        # Directory path display
        self.path_label = QLabel("No directory selected")
        self.path_label.setStyleSheet("padding: 5px; background-color: #2b2b2b; border-radius: 3px;")
        layout.addWidget(self.path_label, stretch=1)

        # Browse button
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_directory)
        layout.addWidget(self.browse_button)

        # Recursive checkbox (optional)
        if self.show_recursive:
            self.recursive_checkbox = QCheckBox("Include subdirectories")
            layout.addWidget(self.recursive_checkbox)

        self.setLayout(layout)

    def browse_directory(self):
        """Open directory browser dialog."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory",
            self.last_directory
        )

        if directory:
            self.set_directory(directory)

    def set_directory(self, directory: str):
        """
        Set the current directory.

        Args:
            directory: Directory path
        """
        self.last_directory = directory
        self.path_label.setText(directory)
        self.directory_changed.emit(directory)

    def get_directory(self) -> str:
        """
        Get the current directory.

        Returns:
            Directory path
        """
        return self.last_directory

    def is_recursive(self) -> bool:
        """
        Check if recursive option is enabled.

        Returns:
            True if recursive checkbox is checked (or doesn't exist)
        """
        if self.show_recursive:
            return self.recursive_checkbox.isChecked()
        return False

    def set_recursive(self, recursive: bool):
        """
        Set the recursive checkbox state.

        Args:
            recursive: Whether to enable recursive
        """
        if self.show_recursive:
            self.recursive_checkbox.setChecked(recursive)
