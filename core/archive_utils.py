"""Archive handling utilities for Pearl's File Tools."""

import os
import re
import zipfile
import tarfile
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Path-traversal defense (Zip Slip)
# ─────────────────────────────────────────────────────────────────────────────
# Modern CPython sanitises ``..`` and absolute paths inside zipfile.extractall
# but py7zr / rarfile / older Python builds do not always. We add a
# pre-extraction validation pass that refuses any archive containing an
# obviously-malicious entry, and a post-extraction sanity check that every
# resulting file lives strictly under the destination root.

# Matches a path component that would escape (.. or ../ or absolute prefix)
_TRAVERSAL_RE = re.compile(r'(^|[\\/])\.\.([\\/]|$)')


def _is_unsafe_archive_path(name: str) -> bool:
    """Return True if *name* looks like an attempt to escape the extract dir.

    Catches: relative traversal (``../foo``, ``a/../../b``), absolute paths
    (``/etc/passwd``, ``\\server\\share``, ``C:\\Windows\\...``), and Windows
    drive letters.
    """
    if not name:
        return True
    n = name.replace('\\', '/')
    if n.startswith('/'):
        return True
    # Windows drive letter: 'C:foo' or 'C:/foo'
    if len(n) >= 2 and n[1] == ':' and n[0].isalpha():
        return True
    if _TRAVERSAL_RE.search(n):
        return True
    return False


def _safe_path_under(root: Path, candidate: Path) -> bool:
    """True iff *candidate* (after resolving) is contained in *root*."""
    try:
        root_r = root.resolve(strict=False)
        cand_r = candidate.resolve(strict=False)
    except OSError:
        return False
    try:
        cand_r.relative_to(root_r)
        return True
    except ValueError:
        return False


def _validate_zip_entries(archive_path: Path) -> Optional[str]:
    """Pre-flight check zip entries for traversal. Returns error string or None."""
    try:
        with zipfile.ZipFile(archive_path, 'r') as zf:
            for info in zf.infolist():
                if _is_unsafe_archive_path(info.filename):
                    return f"Refusing to extract: archive contains unsafe path {info.filename!r}"
                # Reject zip-symlink entries too — they're a known escape vector
                # (Unix ext attr stores file mode in the high 16 bits).
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    return f"Refusing to extract: archive contains a symlink entry {info.filename!r}"
    except zipfile.BadZipFile as exc:
        return f"Not a valid zip: {exc}"
    return None


def _validate_tar_entries(archive_path: Path) -> Optional[str]:
    """Pre-flight check tar entries for traversal."""
    try:
        with tarfile.open(archive_path, 'r:*') as tf:
            for member in tf.getmembers():
                if _is_unsafe_archive_path(member.name):
                    return f"Refusing to extract: archive contains unsafe path {member.name!r}"
                if member.issym() or member.islnk():
                    if _is_unsafe_archive_path(member.linkname):
                        return f"Refusing to extract: archive symlink target escapes ({member.name!r} → {member.linkname!r})"
    except tarfile.TarError as exc:
        return f"Not a valid tar: {exc}"
    return None


def _scrub_extracted(temp_dir: Path) -> Iterable[Path]:
    """After extraction, yield only entries that resolve inside *temp_dir*.

    Files that resolve outside (which can only happen if the underlying
    extractor honoured a malicious path despite our validator) are deleted.
    """
    temp_root = temp_dir.resolve(strict=False)
    for p in list(temp_dir.rglob('*')):
        if not _safe_path_under(temp_root, p):
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass

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
    """Extract ZIP archive with path-traversal validation."""
    err = _validate_zip_entries(archive_path)
    if err:
        print(f"Error extracting ZIP {archive_path}: {err}")
        return None
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="extract_")
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        # Belt-and-braces — drop any entry the underlying extractor placed
        # outside our temp root.
        _scrub_extracted(Path(temp_dir))
        extracted_items = smart_extract(Path(temp_dir), extract_to, use_smart_extract)
        return extracted_items if extracted_items else None
    except Exception as e:
        print(f"Error extracting ZIP {archive_path}: {e}")
        return None
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def extract_tar(archive_path: Path, extract_to: Path, use_smart_extract: bool = True) -> Optional[List[Path]]:
    """Extract TAR archive (including compressed variants) with traversal validation."""
    err = _validate_tar_entries(archive_path)
    if err:
        print(f"Error extracting TAR {archive_path}: {err}")
        return None
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="extract_")
        with tarfile.open(archive_path, 'r:*') as tar_ref:
            # Python 3.12+ exposes a ``filter='data'`` arg that rejects unsafe
            # members (absolute paths, ``..``, device files, dangerous symlinks).
            # Fall back to the legacy call on older Pythons — our pre-flight
            # validator above already rejected the malicious cases.
            try:
                tar_ref.extractall(temp_dir, filter='data')
            except TypeError:
                tar_ref.extractall(temp_dir)
        _scrub_extracted(Path(temp_dir))
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
