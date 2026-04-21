"""Archive handling utilities for Pearl's File Tools."""

import os
import zipfile
import tarfile
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

# Try importing optional libraries for additional archive formats
try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False

try:
    import py7zr
    HAS_PY7ZR = True
except ImportError:
    HAS_PY7ZR = False


def get_archive_type(filepath: Path) -> Optional[str]:
    """
    Determine archive type based on file extension.

    Args:
        filepath: Path to the archive file

    Returns:
        Archive type ('zip', 'tar', 'rar', '7z') or None if not supported
    """
    filepath_lower = str(filepath).lower()

    # Check for compound extensions first (.tar.gz, .tar.bz2, etc.)
    tar_extensions = ['.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz']
    for ext in tar_extensions:
        if filepath_lower.endswith(ext):
            return 'tar'

    if filepath_lower.endswith('.zip'):
        return 'zip'

    if filepath_lower.endswith('.rar') and HAS_RARFILE:
        return 'rar'

    if filepath_lower.endswith('.7z') and HAS_PY7ZR:
        return '7z'

    return None


def smart_extract(temp_dir: Path, final_dest: Path, use_smart_extract: bool = True) -> List[Path]:
    """
    Extract from temp dir to final destination.
    When use_smart_extract is True, collapses single intermediate folder.

    Args:
        temp_dir: Temporary extraction directory
        final_dest: Final destination directory
        use_smart_extract: Whether to collapse single-folder wrappers

    Returns:
        List of extracted file/folder paths
    """
    extracted_items = []

    try:
        items = list(temp_dir.iterdir())
        source_items = items

        # Smart mode: collapse single-folder wrapper
        if use_smart_extract and len(items) == 1 and items[0].is_dir():
            source_items = list(items[0].iterdir())

        for item in source_items:
            dest_path = final_dest / item.name

            if dest_path.exists():
                from core.file_utils import resolve_name_conflict
                dest_path = resolve_name_conflict(dest_path)

            if dest_path:
                shutil.move(str(item), str(dest_path))
                extracted_items.append(dest_path)

        return extracted_items
    except Exception as e:
        print(f"Error during smart extraction: {e}")
        return []


def extract_zip(archive_path: Path, extract_to: Path, use_smart_extract: bool = True) -> Optional[List[Path]]:
    """Extract ZIP archive."""
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="extract_")
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        extracted_items = smart_extract(Path(temp_dir), extract_to, use_smart_extract)
        return extracted_items if extracted_items else None
    except Exception as e:
        print(f"Error extracting ZIP {archive_path}: {e}")
        return None
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def extract_tar(archive_path: Path, extract_to: Path, use_smart_extract: bool = True) -> Optional[List[Path]]:
    """Extract TAR archive (including compressed variants)."""
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="extract_")
        with tarfile.open(archive_path, 'r:*') as tar_ref:
            tar_ref.extractall(temp_dir)
        extracted_items = smart_extract(Path(temp_dir), extract_to, use_smart_extract)
        return extracted_items if extracted_items else None
    except Exception as e:
        print(f"Error extracting TAR {archive_path}: {e}")
        return None
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def extract_rar(archive_path: Path, extract_to: Path, use_smart_extract: bool = True) -> Optional[List[Path]]:
    """Extract RAR archive."""
    if not HAS_RARFILE:
        print("rarfile library not installed - cannot extract RAR archives")
        return None
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="extract_")
        with rarfile.RarFile(archive_path, 'r') as rar_ref:
            rar_ref.extractall(temp_dir)
        extracted_items = smart_extract(Path(temp_dir), extract_to, use_smart_extract)
        return extracted_items if extracted_items else None
    except Exception as e:
        print(f"Error extracting RAR {archive_path}: {e}")
        return None
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def extract_7z(archive_path: Path, extract_to: Path, use_smart_extract: bool = True) -> Optional[List[Path]]:
    """Extract 7Z archive."""
    if not HAS_PY7ZR:
        print("py7zr library not installed - cannot extract 7Z archives")
        return None
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="extract_")
        with py7zr.SevenZipFile(archive_path, 'r') as sz_ref:
            sz_ref.extractall(temp_dir)
        extracted_items = smart_extract(Path(temp_dir), extract_to, use_smart_extract)
        return extracted_items if extracted_items else None
    except Exception as e:
        print(f"Error extracting 7Z {archive_path}: {e}")
        return None
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def extract_archive(
    archive_path: Path,
    extract_to: Path,
    archive_type: Optional[str] = None,
    use_smart_extract: bool = True
) -> Optional[List[Path]]:
    """
    Extract archive based on its type.

    Args:
        archive_path: Path to archive
        extract_to: Destination directory
        archive_type: Pre-determined archive type ('zip', 'tar', 'rar', '7z').
                      If None, auto-detected from file extension.
        use_smart_extract: Whether to collapse single-folder wrappers

    Returns:
        List of extracted items or None on failure
    """
    if archive_type is None:
        archive_type = get_archive_type(archive_path)

    if archive_type == 'zip':
        return extract_zip(archive_path, extract_to, use_smart_extract)
    elif archive_type == 'tar':
        return extract_tar(archive_path, extract_to, use_smart_extract)
    elif archive_type == 'rar':
        return extract_rar(archive_path, extract_to, use_smart_extract)
    elif archive_type == '7z':
        return extract_7z(archive_path, extract_to, use_smart_extract)
    else:
        return None
