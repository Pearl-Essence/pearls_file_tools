"""File operation utilities for Pearl's File Tools."""

import hashlib
import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from constants import (
    ALL_EXTENSION_CATEGORIES, CONFLICT_COUNTER, CONFLICT_TIMESTAMP, CONFLICT_SKIP
)


def has_keyword(filename: str, keywords: List[str]) -> bool:
    """
    Check if filename contains any of the specified keywords (case-insensitive).

    Args:
        filename: The filename to check
        keywords: List of keywords to search for

    Returns:
        True if any keyword is found, False otherwise
    """
    filename_lower = filename.lower()
    return any(keyword.lower() in filename_lower for keyword in keywords)


def get_extension_category(filepath: Path) -> Optional[str]:
    """
    Determine the category of a file based on its extension.

    Args:
        filepath: Path to the file

    Returns:
        Category name ('images', 'documents', 'videos', 'audio', 'archives') or None
    """
    ext = filepath.suffix.lower()

    for category, extensions in ALL_EXTENSION_CATEGORIES.items():
        if ext in extensions:
            return category

    return None


def resolve_name_conflict(target_path: Path, strategy: str = CONFLICT_COUNTER) -> Optional[Path]:
    """
    Resolve filename conflicts by generating a unique filename.

    Args:
        target_path: The desired target path
        strategy: Conflict resolution strategy ('counter', 'timestamp', 'skip')

    Returns:
        Unique path, or None if strategy is 'skip' and conflict exists
    """
    if not target_path.exists():
        return target_path

    if strategy == CONFLICT_SKIP:
        return None

    if strategy == CONFLICT_COUNTER:
        counter = 1
        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent

        while target_path.exists():
            if target_path.is_dir():
                target_path = parent / f"{stem}_{counter}"
            else:
                target_path = parent / f"{stem}_{counter}{suffix}"
            counter += 1

    elif strategy == CONFLICT_TIMESTAMP:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent

        if target_path.is_dir():
            target_path = parent / f"{stem}_{timestamp}"
        else:
            target_path = parent / f"{stem}_{timestamp}{suffix}"

        # If still exists (unlikely), fall back to counter
        if target_path.exists():
            return resolve_name_conflict(target_path, CONFLICT_COUNTER)

    return target_path


def format_file_size(size: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def calculate_directory_hash(directory: Path) -> str:
    """
    Calculate a hash based on directory structure for cache validation.

    Args:
        directory: Path to directory

    Returns:
        MD5 hash string
    """
    try:
        folders = []
        for item in directory.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                try:
                    folders.append(f"{item.name}:{item.stat().st_mtime}")
                except (PermissionError, OSError):
                    folders.append(f"{item.name}:0")
        folder_string = "|".join(sorted(folders))
        return hashlib.md5(folder_string.encode()).hexdigest()
    except Exception:
        return ""


def safe_rename(old_path: Path, new_path: Path) -> bool:
    """
    Safely rename a file with error handling.

    Args:
        old_path: Current file path
        new_path: Desired new file path

    Returns:
        True if successful, False otherwise
    """
    try:
        if not old_path.exists():
            return False

        if new_path.exists() and new_path != old_path:
            return False

        old_path.rename(new_path)
        return True
    except Exception as e:
        print(f"Error renaming {old_path} to {new_path}: {e}")
        return False


def safe_move(src_path: Path, dest_path: Path) -> bool:
    """
    Safely move a file with error handling.

    Args:
        src_path: Source file path
        dest_path: Destination file path

    Returns:
        True if successful, False otherwise
    """
    try:
        import shutil

        if not src_path.exists():
            return False

        if dest_path.exists():
            return False

        # Ensure destination directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(src_path), str(dest_path))
        return True
    except Exception as e:
        print(f"Error moving {src_path} to {dest_path}: {e}")
        return False


def get_files_in_directory(directory: Path,
                           extensions: Optional[List[str]] = None,
                           recursive: bool = False) -> List[Path]:
    """
    Get list of files in a directory, optionally filtered by extensions.

    Args:
        directory: Directory to search
        extensions: List of extensions to filter (e.g., ['.jpg', '.png'])
        recursive: Whether to search subdirectories

    Returns:
        List of file paths
    """
    files = []

    try:
        if recursive:
            for root, dirs, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = Path(root) / filename
                    if extensions is None or filepath.suffix.lower() in extensions:
                        files.append(filepath)
        else:
            for item in directory.iterdir():
                if item.is_file():
                    if extensions is None or item.suffix.lower() in extensions:
                        files.append(item)
    except Exception as e:
        print(f"Error reading directory {directory}: {e}")

    return sorted(files, key=lambda x: x.name.lower())
