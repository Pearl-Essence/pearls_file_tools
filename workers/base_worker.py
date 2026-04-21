"""Base worker thread class for Pearl's File Tools."""

from PyQt5.QtCore import QThread, pyqtSignal


class BaseWorker(QThread):
    """Base class for all background worker threads.

    Cannot use ABC here — QThread's Qt metaclass (pyqtWrapperType) is
    incompatible with ABCMeta. Subclasses must implement run().
    """

    progress = pyqtSignal(str)       # status message
    finished = pyqtSignal(bool, str) # (success, message)

    def __init__(self):
        super().__init__()
        self.is_cancelled = False

    def cancel(self):
        """Signal the worker to stop at its next is_cancelled check."""
        self.is_cancelled = True

    def run(self):
        raise NotImplementedError("Subclasses must implement run()")

    def emit_progress(self, message: str):
        if not self.is_cancelled:
            self.progress.emit(message)

    def emit_finished(self, success: bool, message: str):
        self.finished.emit(success, message)
