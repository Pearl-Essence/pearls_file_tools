"""Scan worker thread for Pearl's File Tools."""

from pathlib import Path
from typing import Dict, List
from PyQt5.QtCore import pyqtSignal
from workers.base_worker import BaseWorker
from core.pattern_matching import group_files_by_pattern


class ScanWorker(BaseWorker):
    """Worker thread for scanning directories and grouping files."""

    finished = pyqtSignal(bool, str, object, object)  # success, message, grouped_results, unsorted_results

    def emit_finished(self, success: bool, message: str, grouped=None, unsorted=None):
        self.finished.emit(success, message, grouped, unsorted)

    def __init__(self, root_dir: str, confidence_threshold: float = 0.4):
        """
        Initialize the scan worker.

        Args:
            root_dir: Root directory to scan
            confidence_threshold: Minimum confidence for grouping
        """
        super().__init__()
        self.root_dir = Path(root_dir)
        self.confidence_threshold = confidence_threshold

    def _scan_one_dir(self, directory: Path,
                      grouped_results: Dict, unsorted_results: Dict):
        """Scan a single directory and merge results into the provided dicts."""
        files = [f for f in directory.iterdir() if f.is_file()]
        if not files:
            return
        filenames = [f.name for f in files]
        groups_dict, unsorted_list = group_files_by_pattern(
            filenames, self.confidence_threshold
        )
        groups_with_paths = {
            grp: [directory / fn for fn in fns]
            for grp, fns in groups_dict.items()
        }
        unsorted_with_paths = [directory / fn for fn in unsorted_list]
        if groups_with_paths:
            grouped_results[str(directory)] = groups_with_paths
        if unsorted_with_paths:
            unsorted_results[str(directory)] = unsorted_with_paths

    def run(self):
        """Execute the directory scan."""
        grouped_results: Dict[str, Dict[str, List[Path]]] = {}
        unsorted_results: Dict[str, List[Path]] = {}

        try:
            # Scan files directly in the root directory first so that selecting
            # a flat folder (e.g. Desktop) still shows its files.
            self.emit_progress(f"Scanning: {self.root_dir.name}...")
            self._scan_one_dir(self.root_dir, grouped_results, unsorted_results)

            # Then scan each immediate subdirectory
            subdirs = [d for d in self.root_dir.iterdir() if d.is_dir()]

            for subdir in subdirs:
                if self.is_cancelled:
                    self.emit_finished(False, "Scan cancelled", None, None)
                    return

                self.emit_progress(f"Scanning {subdir.name}...")
                self._scan_one_dir(subdir, grouped_results, unsorted_results)

            self.emit_progress("Scan complete!")
            self.emit_finished(True, "Scan completed successfully", grouped_results, unsorted_results)

        except Exception as e:
            self.emit_finished(False, f"Scan error: {str(e)}", None, None)
