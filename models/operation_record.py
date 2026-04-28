"""Operation record model for undo functionality in Pearl's File Tools."""

from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from constants import OP_TYPE_RENAME, OP_TYPE_ORGANIZE, OP_TYPE_EXTRACT


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
        """Undo the operation by reversing each file rename in turn.

        ``files_affected`` is stored as ``[(new_path, old_path), ...]`` by the
        rename and organize workers — see core/history.py which documents
        and relies on the same convention. Earlier versions of this method
        unpacked the tuple in the opposite order, which made every undo
        either a no-op (existence guard tripped) or, worse, a silent re-do of
        the original rename. This implementation matches the storage order
        and routes the rename through :func:`core.file_utils.safe_rename` so
        case-only renames on case-insensitive filesystems also undo cleanly.

        Returns:
            Tuple of (success_count, error_count, error_messages)
        """
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

                # An unrelated file genuinely occupying the original path blocks undo.
                # A same-inode hit is the case-flip case and is OK — safe_rename handles it.
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
        else:
            return f"Operation on {file_count} file(s) at {time_str}"
