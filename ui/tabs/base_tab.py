"""Base tab class for Pearl's File Tools."""

from abc import ABCMeta, abstractmethod
from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.QtCore import pyqtSignal, QObject
from typing import Optional


# Create a metaclass that combines PyQt5's metaclass with ABCMeta
class QABCMeta(type(QObject), ABCMeta):
    """Metaclass that combines Qt's metaclass with ABC's metaclass."""
    pass


class BaseTab(QWidget, metaclass=QABCMeta):
    """Abstract base class for all tabs in the application."""

    # Signals
    status_changed = pyqtSignal(str)  # Status message
    operation_completed = pyqtSignal(str, bool)  # (message, success)

    def __init__(self, config, parent=None):
        """
        Initialize the base tab.

        Args:
            config: Config instance for settings management
            parent: Parent widget
        """
        super().__init__(parent)
        self.config = config
        self.current_directory = ""
        self.worker_thread: Optional[object] = None

        # Setup UI (implemented by subclass)
        self.setup_ui()

        # Load saved settings
        self.load_settings()

    @abstractmethod
    def setup_ui(self):
        """
        Setup the tab's user interface.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def load_settings(self):
        """
        Load tab-specific settings from config.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def save_settings(self):
        """
        Save tab-specific settings to config.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def get_tab_name(self) -> str:
        """
        Get the display name for this tab.
        Must be implemented by subclasses.

        Returns:
            Tab name string
        """
        pass

    def set_directory(self, path: str):
        """
        Set the current working directory for this tab.

        Args:
            path: Directory path
        """
        self.current_directory = path
        # Save to config
        tab_name = self.get_tab_name().lower().replace(' ', '_')
        self.config.set_tab_directory(tab_name, path)

    def get_directory(self) -> str:
        """
        Get the current working directory for this tab.

        Returns:
            Directory path
        """
        return self.current_directory

    def emit_status(self, message: str):
        """
        Emit a status update message.

        Args:
            message: Status message
        """
        self.status_changed.emit(message)

    def show_error(self, title: str, message: str):
        """
        Show an error message dialog.

        Args:
            title: Dialog title
            message: Error message
        """
        QMessageBox.critical(self, title, message)

    def show_info(self, title: str, message: str):
        """
        Show an information message dialog.

        Args:
            title: Dialog title
            message: Information message
        """
        QMessageBox.information(self, title, message)

    def show_warning(self, title: str, message: str):
        """
        Show a warning message dialog.

        Args:
            title: Dialog title
            message: Warning message
        """
        QMessageBox.warning(self, title, message)

    def confirm_action(self, title: str, message: str) -> bool:
        """
        Show a confirmation dialog.

        Args:
            title: Dialog title
            message: Confirmation message

        Returns:
            True if user confirmed, False otherwise
        """
        reply = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes

    def enable_controls(self, enabled: bool):
        """
        Enable or disable controls during operations.
        Subclasses can override to disable specific controls.

        Args:
            enabled: Whether to enable controls
        """
        self.setEnabled(enabled)

    def cleanup_worker(self):
        """Clean up worker thread if it exists."""
        if self.worker_thread:
            if self.worker_thread.isRunning():
                self.worker_thread.cancel()
                self.worker_thread.wait()
            self.worker_thread = None
