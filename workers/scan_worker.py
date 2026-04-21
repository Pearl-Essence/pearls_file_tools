"""Scan worker thread for Pearl's File Tools."""

from pathlib import Path
from typing import Dict, List
from PyQt5.QtCore import pyqtSignal
from workers.base_worker import BaseWorker
from core.pattern_matching import group_files_by_pattern


class ScanWorker(BaseWorker):
    """Worker thread for scanning directories and grouping files."""

    # Override finished signal to include results
    finished = pyqtSignal(bool, str, object, object)  # success, message, grouped_results, unsorted_results

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

    def run(self):
        """Execute the directory scan."""
        grouped_results: Dict[str, Dict[str, List[Path]]] = {}
        unsorted_results: Dict[str, List[Path]] = {}

        try:
            # Get all subdirectories
            subdirs = [d for d in self.root_dir.iterdir() if d.is_dir()]

            if not subdirs:
                self.emit_finished(True, "No subdirectories found", {}, {})
                return

            for subdir in subdirs:
                if self.is_cancelled:
                    self.emit_finished(False, "Scan cancelled", None, None)
                    return

                self.emit_progress(f"Scanning {subdir.name}...")

                # Get all files in this subdirectory (not recursive)
                files = [f for f in subdir.iterdir() if f.is_file()]

                if not files:
                    continue

                # Get just filenames for grouping
                filenames = [f.name for f in files]

                # Group files by pattern
                groups_dict, unsorted_list = group_files_by_pattern(
                    filenames,
                    self.confidence_threshold
                )

                # Convert filenames back to Path objects
                groups_with_paths = {}
                for group_name, group_filenames in groups_dict.items():
                    groups_with_paths[group_name] = [
                        subdir / filename for filename in group_filenames
                    ]

                unsorted_with_paths = [subdir / filename for filename in unsorted_list]

                # Store results
                if groups_with_paths:
                    grouped_results[str(subdir)] = groups_with_paths

                if unsorted_with_paths:
                    unsorted_results[str(subdir)] = unsorted_with_paths

            self.emit_progress("Scan complete!")
            self.emit_finished(True, "Scan completed successfully", grouped_results, unsorted_results)

        except Exception as e:
            self.emit_finished(False, f"Scan error: {str(e)}", None, None)
