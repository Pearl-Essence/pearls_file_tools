"""Ingest worker for Pearl's File Tools.

Copies files from a source (camera card / folder) to a destination, verifies
each copy with an MD5 checksum, and reports per-file status via signals.
Source files are NEVER deleted — ingest is always copy-only.
"""

import hashlib
import shutil
import time
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

    # ── Stability / settle tuning ────────────────────────────────────────────
    # Wait for the source file size to remain unchanged across SETTLE_PASSES
    # consecutive observations spaced SETTLE_INTERVAL_SECS apart, before we
    # consider the file safe to copy. SETTLE_TIMEOUT_SECS bounds how long we
    # are willing to block per file (a 60-min export still settles in time;
    # this is a safety hatch against a stuck writer).
    SETTLE_INTERVAL_SECS = 1.0
    SETTLE_PASSES = 3
    SETTLE_TIMEOUT_SECS = 3600

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

    def _wait_for_stable(self, src: Path) -> bool:
        """Block (in this worker thread) until *src* stops growing.

        Returns True once the file's size has been observed unchanged for
        SETTLE_PASSES consecutive polls; False if the worker is cancelled,
        the file disappears, or SETTLE_TIMEOUT_SECS elapses with the file
        still growing. Uses ``self.msleep`` so cancel signals are honoured.
        """
        deadline = time.monotonic() + self.SETTLE_TIMEOUT_SECS
        last_size = -1
        passes = 0
        announced = False
        while time.monotonic() < deadline:
            if self.is_cancelled:
                return False
            try:
                size = src.stat().st_size
            except FileNotFoundError:
                return False
            if size == last_size:
                passes += 1
                if passes >= self.SETTLE_PASSES:
                    return True
            else:
                if not announced and last_size != -1:
                    self.emit_progress(f"Waiting for {src.name} to settle…")
                    announced = True
                passes = 0
                last_size = size
            self.msleep(int(self.SETTLE_INTERVAL_SECS * 1000))
        return False

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

            # 1. Wait for the source to stop growing (handles NLE renders
            #    still being written when ingest fires from a watcher).
            if not self._wait_for_stable(src):
                # Distinguish cancellation from settle-timeout / disappearance —
                # a misleading "settle timeout" message used to mask user cancels.
                if self.is_cancelled:
                    break
                fail_count += 1
                err = (
                    "Source still growing — settle timeout"
                    if src.exists() else "Source vanished before ingest"
                )
                self._results.append(
                    IngestResult(src=src, dst=dst, verified=False, error=err)
                )
                self.file_status.emit(src.name, False, f"✗ {src.name}: {err}")
                continue

            self.emit_progress(f"Copying {src.name} ({idx + 1}/{total})…")

            try:
                dst.parent.mkdir(parents=True, exist_ok=True)

                pre_size = src.stat().st_size
                shutil.copy2(src, dst)

                # 2. Cross-check: if src grew during copy, the snapshot is
                #    inconsistent. Surface this clearly instead of letting
                #    a stale "Checksum mismatch" mislead the operator.
                post_size = src.stat().st_size
                if post_size != pre_size or post_size != dst.stat().st_size:
                    raise IOError(
                        "Source size changed during copy "
                        f"({pre_size:,} → {post_size:,}); writer not finished"
                    )

                src_md5 = self._md5(src)
                dst_md5 = self._md5(dst)
                verified = src_md5 == dst_md5

                result = IngestResult(src=src, dst=dst, verified=verified)
                if verified:
                    success_count += 1
                    self.file_status.emit(src.name, True, f"✓ Verified → {dst}")
                else:
                    fail_count += 1
                    result.error = "Checksum mismatch (source likely still being written)"
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
