"""Ingest worker for Pearl's File Tools.

Copies files from a source (camera card / folder) to a destination, verifies
each copy with an MD5 checksum, and reports per-file status via signals.
Source files are NEVER deleted — ingest is always copy-only.
"""

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from PyQt5.QtCore import pyqtSignal

from workers.base_worker import BaseWorker


@dataclass
class IngestResult:
    src: Path
    dst: Path
    verified: bool
    error: str = ""


class IngestWorker(BaseWorker):
    """Copy files and verify each one with MD5.

    Signals:
        finished(bool, str, list)  — (all_ok, summary_message, List[IngestResult])
        file_status(str, bool, str) — (src_filename, verified, log_message)
        overall_progress(int, int)  — (current_index, total)
    """

    finished = pyqtSignal(bool, str, list)
    file_status = pyqtSignal(str, bool, str)
    overall_progress = pyqtSignal(int, int)

    def __init__(self, pairs: List[Tuple[Path, Path]]):
        """
        Args:
            pairs: List of (source_path, destination_path) tuples.
        """
        super().__init__()
        self.pairs = pairs
        self._results: List[IngestResult] = []

    def emit_finished(self, success: bool, message: str):
        self.finished.emit(success, message, self._results)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _md5(path: Path) -> str:
        h = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()

    # ── main loop ─────────────────────────────────────────────────────────────

    def run(self):
        total = len(self.pairs)
        if total == 0:
            self.finished.emit(True, "No files to ingest.", [])
            return

        success_count = 0
        fail_count = 0

        for idx, (src, dst) in enumerate(self.pairs):
            if self.is_cancelled:
                break

            self.overall_progress.emit(idx, total)
            self.emit_progress(f"Copying {src.name} ({idx + 1}/{total})…")

            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

                src_md5 = self._md5(src)
                dst_md5 = self._md5(dst)
                verified = src_md5 == dst_md5

                result = IngestResult(src=src, dst=dst, verified=verified)
                if verified:
                    success_count += 1
                    self.file_status.emit(src.name, True, f"✓ Verified → {dst}")
                else:
                    fail_count += 1
                    result.error = "Checksum mismatch"
                    self.file_status.emit(src.name, False, f"✗ Checksum mismatch: {src.name}")

            except Exception as exc:
                fail_count += 1
                result = IngestResult(src=src, dst=dst, verified=False, error=str(exc))
                self.file_status.emit(src.name, False, f"✗ Error: {exc}")

            self._results.append(result)

        self.overall_progress.emit(total, total)

        cancelled = self.is_cancelled
        all_ok = fail_count == 0 and not cancelled
        if cancelled:
            summary = f"Ingest cancelled — {success_count} verified, {fail_count} failed"
        else:
            summary = f"Ingest complete — {success_count} verified, {fail_count} failed"

        self.finished.emit(all_ok, summary, self._results)
