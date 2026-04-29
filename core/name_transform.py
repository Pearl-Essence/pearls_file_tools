"""Filename transformation utilities for Pearl's File Tools."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from constants import CASE_NONE, CASE_UPPER, CASE_LOWER, CASE_TITLE


@dataclass
class ProductionTemplate:
    """A named naming convention profile for production files."""
    name: str
    tokens: List[str] = field(default_factory=lambda: ['PROJECT', 'EP', 'SHOT', 'DESC', 'VER'])
    separator: str = '_'
    version_format: str = 'v{:02d}'
    episode_format: str = 'EP{:02d}'

    def compose(self, token_values: Dict[str, str]) -> str:
        """Compose a filename stem from token values; empty tokens are omitted."""
        parts = [token_values.get(t, '').strip() for t in self.tokens]
        return self.separator.join(p for p in parts if p)

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'tokens': self.tokens,
            'separator': self.separator,
            'version_format': self.version_format,
            'episode_format': self.episode_format,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'ProductionTemplate':
        return cls(
            name=d.get('name', 'Unnamed'),
            tokens=d.get('tokens', ['PROJECT', 'EP', 'SHOT', 'DESC', 'VER']),
            separator=d.get('separator', '_'),
            version_format=d.get('version_format', 'v{:02d}'),
            episode_format=d.get('episode_format', 'EP{:02d}'),
        )


DEFAULT_TEMPLATE = ProductionTemplate(name='Studio Default')

# Matches filenames ending in a version token. Accepts a wide variety of
# real-world conventions:
#
#   HERO_v01.mov           — underscore, lowercase v, two digits
#   HERO-v01.mov           — dash separator
#   HERO V01.mov           — space separator, uppercase V
#   HERO  v003.mp4         — multiple spaces
#   HERO_-_v01.mov         — combined separators
#   shot_V0001.mp4         — uppercase V, 4-digit padding
#   HERO_v1.mov            — single digit
#   HERO.v01.mov           — dot separator (rarer but seen)
#
# Captures: stem, separator-as-found, v-letter-as-found, digits, extension —
# so we can preserve the user's existing punctuation and case on bump.
VERSION_PATTERN = re.compile(
    r'^(?P<stem>.+?)'
    r'(?P<sep>[_\-.\s]+)'
    r'(?P<vchar>[vV])'
    r'(?P<digits>\d+)'
    r'(?P<ext>\.[A-Za-z0-9]+)$'
)


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
    """Return ``(stem_without_version, version_number, extension)`` or None.

    The stem returned does *not* include the separator + ``v`` letter that
    preceded the digits — that information is preserved internally by
    :func:`bump_version` so a round-trip preserves the original punctuation.
    """
    match = VERSION_PATTERN.match(filename)
    if not match:
        return None
    return match.group('stem'), int(match.group('digits')), match.group('ext')


def bump_version(filename: str) -> str:
    """Increment the version suffix, preserving the user's chosen punctuation.

    Recognises a wide range of conventions (``_v##``, ``-v##``, `` V##``,
    ``-V0001``, ``.v01``, etc.). The new filename uses the *same* separator
    and ``v``/``V`` case that the input had, and at least the original
    zero-pad width.

    Returns the original filename unchanged if no version suffix is found.
    """
    match = VERSION_PATTERN.match(filename)
    if match is None:
        return filename
    stem = match.group('stem')
    sep = match.group('sep')
    vchar = match.group('vchar')
    digits = match.group('digits')
    ext = match.group('ext')

    new_num = int(digits) + 1
    pad = max(len(digits), len(str(new_num)))
    new_digits = str(new_num).zfill(pad)
    return f"{stem}{sep}{vchar}{new_digits}{ext}"


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
