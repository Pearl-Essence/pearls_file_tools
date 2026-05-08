"""Operation record model for undo functionality in Pearl's File Tools."""

from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from constants import OP_TYPE_RENAME, OP_TYPE_ORGANIZE, OP_TYPE_EXTRACT, OP_TYPE_COPY


class OperationRecord:
    """Records an operation for undo functionality."""

    def __init__(self, operation_type: str, files_affected: List[Tuple[Path, Path]], metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize operation record.

        Args:
            operation_type: Type of operation ('rename', 'organize', 'extract')
            files_affected: List of ``(new_path, old_path)`` tuples — the path
                that exists *after* the operation comes first. The rename and
                history modules both rely on this order; do not flip it.
            metadata: Additional operation-specific data
        """
        self.timestamp = datetime.now()
        self.operation_type = operation_type
        self.files_affected = files_affected  # List of (new_path, old_path)
        self.metadata = metadata or {}

    def undo(self) -> Tuple[int, int, List[str]]:
        """Undo the operation.

        For rename/organize: reverse each file rename.
        For copy: delete each copied file (originals are untouched).

        ``files_affected`` is stored as ``[(new_path, old_path), ...]`` by the
        rename and organize workers — see core/history.py which documents
        and relies on the same convention.

        Returns:
            Tuple of (success_count, error_count, error_messages)
        """
        if self.operation_type == OP_TYPE_COPY:
            return self._undo_copy()
        return self._undo_rename()

    def _undo_copy(self) -> Tuple[int, int, List[str]]:
        success_count = 0
        error_count = 0
        errors: List[str] = []

        for copied_path, _original_path in reversed(self.files_affected):
            try:
                if not copied_path.exists():
                    errors.append(f"{copied_path.name}: copied file no longer exists")
                    error_count += 1
                    continue
                copied_path.unlink()
                success_count += 1
            except Exception as e:
                errors.append(f"{copied_path.name}: {e}")
                error_count += 1

        return success_count, error_count, errors

    def _undo_rename(self) -> Tuple[int, int, List[str]]:
        from core.file_utils import safe_rename, same_inode

        success_count = 0
        error_count = 0
        errors: List[str] = []

        for new_path, old_path in reversed(self.files_affected):
            try:
                if not new_path.exists():
                    errors.append(f"{new_path.name}: file no longer exists at renamed location")
                    error_count += 1
                    continue

                if old_path.exists() and not same_inode(new_path, old_path):
                    errors.append(
                        f"{old_path.name}: original location occupied by a different file"
                    )
                    error_count += 1
                    continue

                if safe_rename(new_path, old_path):
                    success_count += 1
                else:
                    errors.append(f"{new_path.name}: rename back failed")
                    error_count += 1
            except Exception as e:
                errors.append(f"{new_path.name}: {e}")
                error_count += 1

        return success_count, error_count, errors

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the operation record
        """
        return {
            'timestamp': self.timestamp.isoformat(),
            'operation_type': self.operation_type,
            # Stored as (new_path, old_path) — see __init__ docstring.
            'files_affected': [
                (str(new_path), str(old_path))
                for new_path, old_path in self.files_affected
            ],
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OperationRecord':
        """
        Create OperationRecord from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            OperationRecord instance
        """
        record = cls(
            operation_type=data['operation_type'],
            files_affected=[
                (Path(new_path), Path(old_path))
                for new_path, old_path in data['files_affected']
            ],
            metadata=data.get('metadata', {})
        )

        # Restore timestamp
        record.timestamp = datetime.fromisoformat(data['timestamp'])

        return record

    def get_summary(self) -> str:
        """
        Get a human-readable summary of the operation.

        Returns:
            Summary string
        """
        file_count = len(self.files_affected)
        time_str = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")

        if self.operation_type == OP_TYPE_RENAME:
            return f"Renamed {file_count} file(s) at {time_str}"
        elif self.operation_type == OP_TYPE_ORGANIZE:
            return f"Organized {file_count} file(s) at {time_str}"
        elif self.operation_type == OP_TYPE_EXTRACT:
            return f"Extracted {file_count} file(s) at {time_str}"
        elif self.operation_type == OP_TYPE_COPY:
            return f"Copied {file_count} file(s) at {time_str}"
        else:
            return f"Operation on {file_count} file(s) at {time_str}"
