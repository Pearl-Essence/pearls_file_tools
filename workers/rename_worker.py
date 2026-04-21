"""Rename worker thread for Pearl's File Tools."""

from pathlib import Path
from typing import List, Optional
from PyQt5.QtCore import pyqtSignal
from workers.base_worker import BaseWorker
from core.name_transform import generate_new_filename, move_prefix_to_suffix
from core.file_utils import resolve_name_conflict, safe_rename
from core.pattern_matching import match_prefix
from models.operation_record import OperationRecord
from constants import OP_TYPE_RENAME


class RenameWorker(BaseWorker):
    """Worker thread for renaming files."""

    # Override finished signal to include operation record
    finished = pyqtSignal(bool, str, object)  # success, message, operation_record

    def __init__(self, files: List[Path],
                 prefix: str = "",
                 suffix: str = "",
                 rename_to: str = "",
                 case_transform: str = "none",
                 prefix_to_suffix: Optional[List[str]] = None):
        """
        Initialize the rename worker.

        Args:
            files: List of files to rename
            prefix: Prefix to add
            suffix: Suffix to add
            rename_to: Complete rename
            case_transform: Case transformation type
            prefix_to_suffix: List of prefixes to move to suffix (or None)
        """
        super().__init__()
        self.files = files
        self.prefix = prefix
        self.suffix = suffix
        self.rename_to = rename_to
        self.case_transform = case_transform
        self.prefix_to_suffix = prefix_to_suffix

    def run(self):
        """Execute the rename operation."""
        success_count = 0
        error_count = 0
        errors = []
        rename_operations = []

        total = len(self.files)

        for idx, filepath in enumerate(self.files):
            if self.is_cancelled:
                self.emit_finished(False, "Operation cancelled by user", None)
                return

            try:
                # Generate new filename
                if self.prefix_to_suffix:
                    # Prefix-to-suffix mode
                    matched_prefix = match_prefix(filepath.name, self.prefix_to_suffix)
                    if matched_prefix:
                        new_name = move_prefix_to_suffix(filepath.name, matched_prefix)
                    else:
                        # Skip files that don't match
                        continue
                else:
                    # Normal rename mode
                    new_name = generate_new_filename(
                        filepath.name,
                        prefix=self.prefix,
                        suffix=self.suffix,
                        rename_to=self.rename_to,
                        case_transform=self.case_transform
                    )

                # Check if name actually changed
                if new_name == filepath.name:
                    continue

                # Create new path
                new_path = filepath.parent / new_name

                # Resolve conflicts
                if new_path.exists() and new_path != filepath:
                    new_path = resolve_name_conflict(new_path)
                    if new_path is None:
                        errors.append(f"{filepath.name}: Target already exists")
                        error_count += 1
                        continue

                # Perform rename
                if safe_rename(filepath, new_path):
                    rename_operations.append((new_path, filepath))  # Store as (new, old) for undo
                    success_count += 1
                    self.emit_progress(f"Renamed: {filepath.name} → {new_name}")
                else:
                    errors.append(f"{filepath.name}: Rename failed")
                    error_count += 1

            except Exception as e:
                errors.append(f"{filepath.name}: {str(e)}")
                error_count += 1

            # Update progress
            if total > 0:
                percentage = int(((idx + 1) / total) * 100)
                self.emit_progress(f"Processing... {idx + 1}/{total} ({percentage}%)")

        # Create operation record for undo
        operation_record = None
        if rename_operations:
            operation_record = OperationRecord(
                operation_type=OP_TYPE_RENAME,
                files_affected=rename_operations,
                metadata={
                    'prefix': self.prefix,
                    'suffix': self.suffix,
                    'rename_to': self.rename_to,
                    'case_transform': self.case_transform
                }
            )

        # Build result message
        message = f"Successfully renamed {success_count} file(s)."
        if error_count > 0:
            message += f"\n{error_count} error(s) occurred."
            if errors:
                message += "\n\nFirst errors:\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    message += f"\n... and {len(errors) - 5} more"

        # Emit finished signal
        success = error_count == 0
        self.emit_finished(success, message, operation_record)
