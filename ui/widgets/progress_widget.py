"""Progress widget for Pearl's File Tools."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QLabel
from PyQt5.QtCore import Qt


class ProgressWidget(QWidget):
    """Reusable progress bar widget with status label."""

    def __init__(self, parent=None):
        """
        Initialize the progress widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def set_status(self, message: str):
        """
        Set the status message.

        Args:
            message: Status message to display
        """
        self.status_label.setText(message)

    def set_progress(self, current: int, total: int):
        """
        Set the progress value.

        Args:
            current: Current progress value
            total: Total/maximum progress value
        """
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setValue(0)

    def set_percentage(self, percentage: int):
        """
        Set progress as a percentage.

        Args:
            percentage: Progress percentage (0-100)
        """
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(percentage)

    def set_indeterminate(self, indeterminate: bool = True):
        """
        Set indeterminate mode (animated progress without specific value).

        Args:
            indeterminate: Whether to use indeterminate mode
        """
        if indeterminate:
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(0)
        else:
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(100)

    def reset(self):
        """Reset the progress bar to 0."""
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.status_label.setText("Ready")

    def show_progress(self, show: bool = True):
        """
        Show or hide the progress bar.

        Args:
            show: Whether to show the progress bar
        """
        self.progress_bar.setVisible(show)
