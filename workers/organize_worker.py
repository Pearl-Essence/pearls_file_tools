"""Organize worker thread for Pearl's File Tools."""

from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Signal

from core.file_utils import resolve_name_conflict, safe_move
from workers.base_worker import BaseWorker

_MSG_CANCELLED = "Operation cancelled"


class OrganizeWorker(BaseWorker):
    """Worker thread for organizing files into folders."""

    # Additional signals
    progress = Signal(str, int, int)  # message, current, total
    confirm_needed = Signal(str, str, list)  # folder_name, subdir, files
    finished = Signal(bool, str)  # success, message

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
                len(files) for subdir_groups in self.file_groups.values() for files in subdir_groups.values()
            )
            processed = 0

            for subdir_path, groups in self.file_groups.items():
                if self.is_cancelled:
                    self.finished.emit(False, _MSG_CANCELLED)
                    return

                subdir = Path(subdir_path)

                for group_name, files in groups.items():
                    if self.is_cancelled:
                        self.finished.emit(False, _MSG_CANCELLED)
                        return

                    if not files:
                        continue

                    target_folder = subdir / group_name

                    action = self._resolve_folder_action(group_name, subdir, files, target_folder)
                    if action is None:
                        # Cancelled
                        return

                    if action == "skip":
                        self.progress.emit(f"Skipped {group_name} (folder exists)", processed, total_files)
                        processed += len(files)
                        continue

                    processed = self._move_group_files(files, target_folder, group_name, processed, total_files)
                    if processed is None:
                        # Cancelled
                        return

            self.finished.emit(True, f"Successfully organized {processed} files!")

        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")

    def _resolve_folder_action(
        self, group_name: str, subdir: Path, files: List[Path], target_folder: Path
    ) -> Optional[str]:
        """Determine what to do when the target folder already exists.

        Returns:
            ``"merge"`` to merge into the existing folder,
            ``"skip"`` to skip the group,
            ``"create"`` if the folder didn't exist (newly created), or
            ``None`` if the operation was cancelled.
        """
        if not target_folder.exists():
            target_folder.mkdir(parents=True, exist_ok=True)
            return "create"

        if self.apply_to_all is None:
            self.pending_response = None
            file_names = [f.name for f in files]
            self.confirm_needed.emit(group_name, str(subdir), file_names)

            while self.pending_response is None and not self.is_cancelled:
                self.msleep(100)

            if self.is_cancelled:
                self.finished.emit(False, _MSG_CANCELLED)
                return None

            action = self.pending_response
        else:
            action = self.apply_to_all

        if action == "skip":
            return "skip"
        if action == "merge":
            return "merge"

        # Any other response (e.g. "cancel") → abort
        self.finished.emit(False, _MSG_CANCELLED)
        return None

    def _move_group_files(
        self,
        files: List[Path],
        target_folder: Path,
        group_name: str,
        processed: int,
        total_files: int,
    ) -> Optional[int]:
        """Move each file in *files* into *target_folder*.

        Returns the updated *processed* count, or ``None`` if cancelled.
        """
        for file_path in files:
            if self.is_cancelled:
                self.finished.emit(False, _MSG_CANCELLED)
                return None

            try:
                target_path = target_folder / file_path.name

                if target_path.exists():
                    target_path = resolve_name_conflict(target_path)
                    if target_path is None:
                        processed += 1
                        continue

                if safe_move(file_path, target_path):
                    processed += 1
                    self.progress.emit(f"Moved {file_path.name} → {group_name}/", processed, total_files)
                else:
                    self.progress.emit(f"Failed to move {file_path.name}", processed, total_files)

            except Exception as e:
                self.progress.emit(f"Error moving {file_path.name}: {str(e)}", processed, total_files)

        return processed

    def cancel(self):
        """Cancel the operation."""
        super().cancel()
        # Also wake up any pending confirmation waits
        if self.pending_response is None:
            self.pending_response = "cancel"
