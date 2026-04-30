"""Watch-folder worker thread for Pearl's File Tools."""

import time
from pathlib import Path
from typing import List

from PySide6.QtCore import Signal

from workers.base_worker import BaseWorker
from core.watch_service import WatchRule, WatchService, HAS_WATCHDOG


class WatchWorker(BaseWorker):
    """QThread that drives the WatchService.

    Signals:
        finished(bool, str, object): overrides base with extra result payload
        file_arrived(str, str): (absolute path string, profile_name)
    """

    finished = Signal(bool, str, object)   # shadows BaseWorker.finished
    file_arrived = Signal(str, str)        # path, profile_name

    def __init__(self, rules: List[WatchRule], poll_interval_secs: int = 30):
        super().__init__()
        self._rules = rules
        self._poll_interval_secs = poll_interval_secs

    # BaseWorker contract --------------------------------------------------

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        service = WatchService()

        def on_arrival(path: Path, profile_name: str):
            self.file_arrived.emit(str(path), profile_name)

        service.start(self._rules, on_arrival)

        try:
            if HAS_WATCHDOG:
                # watchdog observers run in their own threads; we just wait here.
                while not self.is_cancelled:
                    time.sleep(1)
            else:
                # Manual polling: sleep 1 s at a time so we check is_cancelled often.
                elapsed = 0
                while not self.is_cancelled:
                    time.sleep(1)
                    elapsed += 1
                    if elapsed >= self._poll_interval_secs:
                        service.poll_once()
                        elapsed = 0
        finally:
            service.stop()
            self.emit_finished(True, "Stopped", None)
