"""Filename transformation utilities for Pearl's File Tools."""

import re
from pathlib import Path
from typing import List, Tuple, Optional
from constants import CASE_NONE, CASE_UPPER, CASE_LOWER, CASE_TITLE

# Matches filenames ending in _v## (e.g. HERO_v01.mov, clip_v003.mp4)
VERSION_PATTERN = re.compile(r'^(.+?)_v(\d+)(\.\w+)$', re.IGNORECASE)


def apply_case_transform(text: str, transform_type: str) -> str:
    """
    Apply case transformation to text.

    Args:
        text: Text to transform
        transform_type: Type of transformation ('none', 'upper', 'lower', 'title')

    Returns:
        Transformed text
    """
    if transform_type == CASE_UPPER:
        return text.upper()
    elif transform_type == CASE_LOWER:
        return text.lower()
    elif transform_type == CASE_TITLE:
        return text.title()
    else:  # CASE_NONE or unknown
        return text


def add_prefix(filename: str, prefix: str) -> str:
    """
    Add prefix to filename (before the stem, preserving extension).

    Args:
        filename: Original filename
        prefix: Prefix to add

    Returns:
        New filename with prefix
    """
    if not prefix:
        return filename

    path = Path(filename)
    stem = path.stem
    suffix = path.suffix

    return f"{prefix}{stem}{suffix}"


def add_suffix(filename: str, suffix_text: str) -> str:
    """
    Add suffix to filename (after the stem, before extension).

    Args:
        filename: Original filename
        suffix_text: Suffix to add

    Returns:
        New filename with suffix
    """
    if not suffix_text:
        return filename

    path = Path(filename)
    stem = path.stem
    suffix = path.suffix

    return f"{stem}{suffix_text}{suffix}"


def move_suffix_to_prefix(filename: str, suffix_token: str) -> str:
    """Move a suffix token (e.g. '_DRAFT') from the end of the stem to the front.

    Example: ('interview_DRAFT.mov', '_DRAFT') → 'DRAFT_interview.mov'
    Returns the original filename if the stem does not end with suffix_token.
    """
    path = Path(filename)
    stem = path.stem
    ext = path.suffix

    if not stem.lower().endswith(suffix_token.lower()):
        return filename

    new_stem = stem[:len(stem) - len(suffix_token)]
    separator = suffix_token[0] if suffix_token and suffix_token[0] in '_- ' else '_'
    token_text = suffix_token.lstrip('_- ')

    return f"{token_text}{separator}{new_stem}{ext}"


def move_prefix_to_suffix(filename: str, prefix: str) -> str:
    """
    Move prefix from beginning to end (as suffix before extension).

    Args:
        filename: Original filename with prefix
        prefix: Prefix to move

    Returns:
        New filename with prefix moved to suffix position
    """
    if not prefix or not filename.startswith(prefix):
        return filename

    # Remove prefix from start
    name_without_prefix = filename[len(prefix):]

    path = Path(name_without_prefix)
    stem = path.stem
    suffix = path.suffix

    # Add original prefix as suffix
    return f"{stem}{prefix.rstrip('_- ')}{suffix}"


def rename_file(filename: str, new_name: str) -> str:
    """
    Complete rename of file (preserving extension).

    Args:
        filename: Original filename
        new_name: New name (without extension)

    Returns:
        New filename with original extension
    """
    if not new_name:
        return filename

    path = Path(filename)
    suffix = path.suffix

    return f"{new_name}{suffix}"


def generate_new_filename(original_filename: str,
                         prefix: str = "",
                         suffix: str = "",
                         rename_to: str = "",
                         case_transform: str = CASE_NONE) -> str:
    """
    Generate new filename based on transformation options.

    Args:
        original_filename: Original filename
        prefix: Prefix to add (empty string = no prefix)
        suffix: Suffix to add (empty string = no suffix)
        rename_to: Complete rename (empty string = keep original)
        case_transform: Case transformation to apply

    Returns:
        New filename after all transformations
    """
    path = Path(original_filename)
    stem = path.stem
    extension = path.suffix

    # If rename_to is provided, use it as the new stem
    if rename_to.strip():
        new_stem = rename_to.strip()
    else:
        # Otherwise, apply prefix and suffix to original stem
        new_stem = f"{prefix}{stem}{suffix}"

    # Apply case transformation
    new_stem = apply_case_transform(new_stem, case_transform)

    return f"{new_stem}{extension}"


def generate_sequential_filenames(
    filenames: List[str],
    base_name: str,
    start: int = 1,
    padding: int = 3,
    separator: str = "_"
) -> List[Tuple[str, str]]:
    """Return (original, new) pairs with sequential numbering.

    Example: base_name='HERO', start=1, padding=3
      → [('clip01.mov', 'HERO_001.mov'), ('clip02.mov', 'HERO_002.mov'), ...]
    """
    pairs = []
    for i, original in enumerate(filenames):
        ext = Path(original).suffix
        number = str(start + i).zfill(padding)
        new_name = f"{base_name}{separator}{number}{ext}"
        pairs.append((original, new_name))
    return pairs


def detect_version(filename: str) -> Optional[Tuple[str, int, str]]:
    """Return (stem_without_version, version_number, extension) or None."""
    match = VERSION_PATTERN.match(filename)
    if not match:
        return None
    stem, version_str, ext = match.groups()
    return stem, int(version_str), ext


def bump_version(filename: str) -> str:
    """Increment the _v## suffix, preserving zero-padding width.

    Returns the original filename unchanged if no version suffix is found.
    """
    result = detect_version(filename)
    if result is None:
        return filename
    stem, version_num, ext = result
    # Determine original zero-pad width from the matched digits
    match = VERSION_PATTERN.match(filename)
    original_digits = match.group(2)
    pad = max(len(original_digits), len(str(version_num + 1)))
    new_version = str(version_num + 1).zfill(pad)
    return f"{stem}_v{new_version}{ext}"


def is_valid_filename(filename: str) -> bool:
    """
    Check if a filename is valid (doesn't contain illegal characters).

    Args:
        filename: Filename to validate

    Returns:
        True if valid, False otherwise
    """
    # Illegal characters for Windows filenames
    illegal_chars = '<>:"/\\|?*'

    # Check for illegal characters
    if any(char in filename for char in illegal_chars):
        return False

    # Check for reserved names on Windows
    reserved_names = [
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    ]

    name_upper = Path(filename).stem.upper()
    if name_upper in reserved_names:
        return False

    # Check for trailing dots or spaces (not allowed on Windows)
    if filename.endswith('.') or filename.endswith(' '):
        return False

    return True
