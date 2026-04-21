"""Organize worker thread for Pearl's File Tools."""

from pathlib import Path
from typing import Dict, List, Optional
from PyQt5.QtCore import pyqtSignal
from workers.base_worker import BaseWorker
from core.file_utils import resolve_name_conflict, safe_move


class OrganizeWorker(BaseWorker):
    """Worker thread for organizing files into folders."""

    # Additional signals
    progress = pyqtSignal(str, int, int)  # message, current, total
    confirm_needed = pyqtSignal(str, str, list)  # folder_name, subdir, files
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, file_groups: Dict[str, Dict[str, List[Path]]], root_dir: str):
        """
        Initialize the organize worker.

        Args:
            file_groups: Dictionary of subdirs -> groups -> files
            root_dir: Root directory
        """
        super().__init__()
        self.file_groups = file_groups
        self.root_dir = Path(root_dir)
        self.pending_response: Optional[str] = None
        self.apply_to_all: Optional[str] = None

    def run(self):
        """Execute the file organization."""
        try:
            total_files = sum(
                len(files)
                for subdir_groups in self.file_groups.values()
                for files in subdir_groups.values()
            )
            processed = 0

            for subdir_path, groups in self.file_groups.items():
                if self.is_cancelled:
                    self.finished.emit(False, "Operation cancelled by user")
                    return

                subdir = Path(subdir_path)

                for group_name, files in groups.items():
                    if self.is_cancelled:
                        self.finished.emit(False, "Operation cancelled by user")
                        return

                    # Skip empty groups
                    if not files:
                        continue

                    # Create target folder
                    target_folder = subdir / group_name

                    # Check if folder exists
                    if target_folder.exists():
                        # Need confirmation
                        if self.apply_to_all is None:
                            self.pending_response = None
                            file_names = [f.name for f in files]
                            self.confirm_needed.emit(group_name, str(subdir), file_names)

                            # Wait for response
                            while self.pending_response is None and not self.is_cancelled:
                                self.msleep(100)

                            if self.is_cancelled:
                                self.finished.emit(False, "Operation cancelled")
                                return

                            action = self.pending_response
                        else:
                            action = self.apply_to_all

                        if action == "skip":
                            self.progress.emit(
                                f"Skipped {group_name} (folder exists)",
                                processed,
                                total_files
                            )
                            processed += len(files)
                            continue
                        elif action != "merge":
                            self.finished.emit(False, "Operation cancelled")
                            return
                    else:
                        target_folder.mkdir(parents=True, exist_ok=True)

                    # Move files
                    for file_path in files:
                        if self.is_cancelled:
                            self.finished.emit(False, "Operation cancelled")
                            return

                        try:
                            target_path = target_folder / file_path.name

                            # Handle name conflicts
                            if target_path.exists():
                                target_path = resolve_name_conflict(target_path)
                                if target_path is None:
                                    # Skip this file
                                    processed += 1
                                    continue

                            # Move file
                            if safe_move(file_path, target_path):
                                processed += 1
                                self.progress.emit(
                                    f"Moved {file_path.name} → {group_name}/",
                                    processed,
                                    total_files
                                )
                            else:
                                self.progress.emit(
                                    f"Failed to move {file_path.name}",
                                    processed,
                                    total_files
                                )

                        except Exception as e:
                            self.progress.emit(
                                f"Error moving {file_path.name}: {str(e)}",
                                processed,
                                total_files
                            )

            self.finished.emit(True, f"Successfully organized {processed} files!")

        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")

    def cancel(self):
        """Cancel the operation."""
        super().cancel()
        # Also wake up any pending confirmation waits
        if self.pending_response is None:
            self.pending_response = "cancel"
