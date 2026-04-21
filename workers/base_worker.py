"""Base worker thread class for Pearl's File Tools."""

from abc import ABC, abstractmethod
from PyQt5.QtCore import QThread, pyqtSignal


class BaseWorker(QThread, ABC):
    """Abstract base class for all background worker threads."""

    # Signals
    progress = pyqtSignal(str)  # Status message
    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self):
        """Initialize the worker thread."""
        super().__init__()
        self.is_cancelled = False

    def cancel(self):
        """
        Cancel the running operation.
        Subclasses should check is_cancelled periodically in their run() method.
        """
        self.is_cancelled = True

    @abstractmethod
    def run(self):
        """
        Main worker execution method.
        Must be implemented by subclasses.
        Should check self.is_cancelled periodically and emit signals for progress.
        """
        pass

    def emit_progress(self, message: str):
        """
        Safely emit a progress message.

        Args:
            message: Progress message to emit
        """
        if not self.is_cancelled:
            self.progress.emit(message)

    def emit_finished(self, success: bool, message: str):
        """
        Safely emit the finished signal.

        Args:
            success: Whether the operation was successful
            message: Final status message
        """
        self.finished.emit(success, message)
