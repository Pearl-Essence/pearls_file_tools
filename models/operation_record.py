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
            files_affected: List of (old_path, new_path) tuples
            metadata: Additional operation-specific data
        """
        self.timestamp = datetime.now()
        self.operation_type = operation_type
        self.files_affected = files_affected  # List of (old_path, new_path)
        self.metadata = metadata or {}

    def undo(self) -> Tuple[int, int, List[str]]:
        """
        Undo the operation by reversing file operations.

        Returns:
            Tuple of (success_count, error_count, error_messages)
        """
        success_count = 0
        error_count = 0
        errors = []

        # Reverse the operations (in reverse order)
        for old_path, new_path in reversed(self.files_affected):
            try:
                # Check if the new path still exists
                if not new_path.exists():
                    errors.append(f"{new_path.name}: File no longer exists")
                    error_count += 1
                    continue

                # Check if old path would conflict
                if old_path.exists():
                    errors.append(f"{old_path.name}: Original location already occupied")
                    error_count += 1
                    continue

                # Rename back to original
                new_path.rename(old_path)
                success_count += 1

            except Exception as e:
                errors.append(f"{new_path.name}: {str(e)}")
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
            'files_affected': [
                (str(old_path), str(new_path))
                for old_path, new_path in self.files_affected
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
                (Path(old_path), Path(new_path))
                for old_path, new_path in data['files_affected']
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
