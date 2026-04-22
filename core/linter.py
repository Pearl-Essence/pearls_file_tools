"""Filename linting utilities for Pearl's File Tools."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

ILLEGAL_CHARS_WIN = frozenset('<>:"/\\|?*\x00')
WINDOWS_RESERVED = frozenset({
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
})
# Matches WIP/DRAFT/TEMP/TEST as whole "words" (separated by _, -, space, or at start/end of stem)
_WIP_PATTERN = re.compile(r'(?:^|[_\-\s])(WIP|DRAFT|TEMP|TEST)(?:[_\-\s]|$)', re.IGNORECASE)

ISSUE_LABELS: Dict[str, str] = {
    'illegal_char': 'Illegal Character',
    'too_long': 'Name Too Long',
    'reserved_name': 'Reserved Name',
    'wip_flag': 'Draft/WIP Marker',
    'case_duplicate': 'Case-Only Duplicate',
    'profile_mismatch': 'Profile Mismatch',
}


@dataclass
class LintIssue:
    filename: str
    issue_type: str
    description: str


class FilenameLint:
    """Checks filenames for common cross-platform and naming-convention issues."""

    def lint_directory(self, directory: Path, profile=None) -> List[LintIssue]:
        """Return issues found for all files directly inside *directory* (non-recursive)."""
        issues: List[LintIssue] = []
        try:
            entries = sorted(p for p in directory.iterdir() if p.is_file())
        except PermissionError:
            return issues

        seen_lower: Dict[str, str] = {}

        for p in entries:
            fname = p.name
            stem = p.stem

            bad_chars = [ch for ch in fname if ch in ILLEGAL_CHARS_WIN]
            if bad_chars:
                issues.append(LintIssue(fname, 'illegal_char',
                    "Contains character(s) illegal on Windows: "
                    + ', '.join(f"'{c}'" for c in bad_chars)))

            if len(fname.encode('utf-8')) > 255:
                issues.append(LintIssue(fname, 'too_long',
                    f"Filename is {len(fname)} characters (255-byte limit)"))

            if stem.upper() in WINDOWS_RESERVED:
                issues.append(LintIssue(fname, 'reserved_name',
                    f"'{stem}' is a reserved device name on Windows"))

            if _WIP_PATTERN.search(stem):
                issues.append(LintIssue(fname, 'wip_flag',
                    "Contains a draft/work-in-progress marker (WIP, DRAFT, TEMP, or TEST)"))

            lower = fname.lower()
            if lower in seen_lower:
                issues.append(LintIssue(fname, 'case_duplicate',
                    f"Case-only duplicate of '{seen_lower[lower]}' — "
                    "collision risk on case-insensitive filesystems (Windows/macOS)"))
            else:
                seen_lower[lower] = fname

            if profile is not None and not self._matches_profile(stem, profile):
                issues.append(LintIssue(fname, 'profile_mismatch',
                    f"Does not conform to '{profile.name}' naming convention "
                    f"(expected {len(profile.tokens)} '{profile.separator}'-separated tokens)"))

        return issues

    def _matches_profile(self, stem: str, profile) -> bool:
        """Rough conformance check: stem must have at least as many parts as profile tokens."""
        parts = stem.split(profile.separator)
        return len(parts) >= len(profile.tokens) and all(parts)
