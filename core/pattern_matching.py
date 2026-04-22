"""Pattern matching and grouping utilities for Pearl's File Tools."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple, Optional, Dict, List
from difflib import SequenceMatcher
from collections import defaultdict


# ── Grouping presets ──────────────────────────────────────────────────────────

@dataclass
class GroupingPreset:
    """Describes how files are grouped during an organizer scan."""
    name: str
    description: str


PRESET_STANDARD = GroupingPreset(
    name="Standard",
    description="Group by underscore-delimited prefix (default behaviour)",
)

PRESET_AE_RENDER = GroupingPreset(
    name="AE Render Output",
    description="Strip trailing _#### frame numbers before grouping sequences",
)

ALL_PRESETS: List[GroupingPreset] = [PRESET_STANDARD, PRESET_AE_RENDER]

# Matches AE-style frame suffixes: Hero_Explosion_0001.exr → base='Hero_Explosion'
AE_FRAME_PATTERN = re.compile(r'^(.+?)_(\d{4,8})(\.\w+)$')

# Matches filenames like HERO_Explosion_0001.exr, shot010.0042.dpx,
# "HCESD11 - Card - STAR - 00000.png" (space-dash-space delimiter), or
# "HCESD11 - Card - Star-00000.png" (plain-dash delimiter).
# Requires an explicit delimiter (_  .  -  or  ' - ') before the frame number.
SEQUENCE_PATTERN = re.compile(r'^(.+?)(?:[._-]| - )(\d{2,8})(\.\w+)$')

# Matches filenames whose entire stem is a frame number, e.g. 000.png, 0042.exr
PURE_NUMBER_PATTERN = re.compile(r'^(\d{2,8})(\.\w+)$')


@dataclass
class SequenceGroup:
    """A detected image/frame sequence sharing a common base name."""
    base: str
    extension: str
    frames: List[int]
    missing: List[int]
    padding: int
    files: List[str]   # filenames only (no directory component)

    @property
    def label(self) -> str:
        """Human-readable label for display in tree widgets."""
        if not self.frames:
            return self.base or "(sequence)"
        first = str(self.frames[0]).zfill(self.padding)
        last = str(self.frames[-1]).zfill(self.padding)
        count = len(self.frames)
        missing_str = f", {len(self.missing)} missing" if self.missing else ""
        base_prefix = f"{self.base} " if self.base else ""
        return f"{base_prefix}[{first}\u2013{last}, {count} frames{missing_str}, {self.extension}]"


def detect_image_sequences(filenames: List[str],
                           min_frames: int = 3) -> Dict[str, 'SequenceGroup']:
    """Group filenames that form image/frame sequences.

    Handles three naming conventions:
    - Explicit delimiter:  HERO_Explosion_0001.exr  /  shot010.0042.dpx
    - Space-dash-space:   "HCESD11 - Card - STAR - 00000.png"
    - Plain-dash:         "HCESD11 - Card - Star-00000.png"
    - Pure numeric stem:  000.png  /  0001.exr

    Returns a dict keyed by '{base}{extension}' mapping to a SequenceGroup.
    min_frames controls the minimum group size (default 3); pass 2 to also
    surface pairs, e.g. when the user manually forces sequence detection.
    """
    candidates: Dict[str, List[Tuple[int, str, int]]] = defaultdict(list)

    for fname in filenames:
        m = SEQUENCE_PATTERN.match(fname)
        if m:
            base, frame_str, ext = m.groups()
            key = f"{base}{ext}"
            candidates[key].append((int(frame_str), fname, len(frame_str)))
            continue
        # Fall back to pure-numeric stem (e.g. 000.png → 481.png)
        m2 = PURE_NUMBER_PATTERN.match(fname)
        if m2:
            frame_str, ext = m2.groups()
            key = ext          # base is empty; key is just the extension
            candidates[key].append((int(frame_str), fname, len(frame_str)))

    sequences: Dict[str, SequenceGroup] = {}
    for key, items in candidates.items():
        if len(items) < min_frames:
            continue
        items.sort(key=lambda x: x[0])
        frames = [item[0] for item in items]
        files = [item[1] for item in items]
        padding = max(item[2] for item in items)

        # Recover base + ext from the first filename
        m = SEQUENCE_PATTERN.match(files[0])
        if m:
            base, _, ext = m.groups()
        else:
            m2 = PURE_NUMBER_PATTERN.match(files[0])
            base, ext = "", m2.group(2)  # type: ignore[union-attr]

        expected = set(range(frames[0], frames[-1] + 1))
        missing = sorted(expected - set(frames))
        sequences[key] = SequenceGroup(
            base=base,
            extension=ext,
            frames=frames,
            missing=missing,
            padding=padding,
            files=files,
        )

    return sequences


def get_group_name(filename: str, similarity_threshold: float = 0.6) -> Tuple[str, float]:
    """
    Extract a group name from a filename.
    First tries to use text before the second underscore.

    Args:
        filename: Filename to analyze
        similarity_threshold: Minimum confidence threshold

    Returns:
        Tuple of (group_name, confidence_level)
    """
    base_name = Path(filename).stem
    parts = base_name.split('_')

    if len(parts) >= 2:
        # Use text before second underscore
        group = '_'.join(parts[:2])
        return group, 1.0  # High confidence
    elif len(parts) == 1 and parts[0]:
        # Single word or no underscores
        return parts[0], 0.5  # Medium confidence
    else:
        return base_name, 0.3  # Low confidence


def find_best_group(filename: str, existing_groups: List[str], threshold: float = 0.6) -> Tuple[Optional[str], float]:
    """
    Find the best matching group for a file using fuzzy string matching.

    Args:
        filename: Filename to match
        existing_groups: List of existing group names
        threshold: Minimum similarity threshold

    Returns:
        Tuple of (group_name, similarity_score) or (None, 0) if no good match
    """
    base_name = Path(filename).stem
    best_match = None
    best_score = 0.0

    for group in existing_groups:
        # Calculate similarity between filename and group name
        ratio = SequenceMatcher(None, base_name.lower(), group.lower()).ratio()

        # Also check if group name is a prefix
        if base_name.lower().startswith(group.lower()):
            ratio = max(ratio, 0.8)

        if ratio > best_score and ratio >= threshold:
            best_score = ratio
            best_match = group

    return best_match, best_score


def detect_common_prefixes(filenames: List[str]) -> Dict[str, int]:
    """
    Detect common prefixes in a list of filenames.

    Args:
        filenames: List of filenames to analyze

    Returns:
        Dictionary mapping prefix to count of files with that prefix
    """
    prefix_counts = defaultdict(int)

    for filename in filenames:
        # Try different delimiters
        for delimiter in ['_', '-', ' ']:
            if delimiter in filename:
                potential_prefix = filename.split(delimiter)[0] + delimiter
                prefix_counts[potential_prefix] += 1
                break  # Only count first delimiter found

    # Filter prefixes that appear on multiple files (at least 2)
    common_prefixes = {
        prefix: count
        for prefix, count in prefix_counts.items()
        if count >= 2
    }

    return common_prefixes


def group_files_by_pattern(filenames: List[str], confidence_threshold: float = 0.4) -> Tuple[Dict[str, List[str]], List[str]]:
    """
    Group files by naming patterns.

    Args:
        filenames: List of filenames to group
        confidence_threshold: Minimum confidence to include in a group

    Returns:
        Tuple of (groups_dict, unsorted_files)
            - groups_dict: Dictionary mapping group names to list of filenames
            - unsorted_files: List of filenames that didn't fit into any group
    """
    groups = defaultdict(list)
    unsorted = []

    for filename in filenames:
        group_name, confidence = get_group_name(filename)

        if confidence >= confidence_threshold:
            # Good confidence - add to group
            groups[group_name].append(filename)
        else:
            # Low confidence - try fuzzy matching
            best_group, score = find_best_group(
                filename,
                list(groups.keys()),
                threshold=0.6
            )

            if best_group and score >= 0.6:
                groups[best_group].append(filename)
            else:
                # Mark as unsorted
                unsorted.append(filename)

    # Move single-file groups to unsorted
    final_groups = {}
    for group_name, files in groups.items():
        if len(files) >= 2:
            final_groups[group_name] = files
        else:
            unsorted.extend(files)

    return final_groups, unsorted


def match_prefix(filename: str, prefixes: List[str]) -> Optional[str]:
    """Check if filename starts with any of the given prefixes (case-sensitive)."""
    for prefix in prefixes:
        if filename.startswith(prefix):
            return prefix
    return None


def detect_common_suffixes(filenames: List[str]) -> Dict[str, int]:
    """Detect common suffix tokens (before the file extension) in a list of filenames.

    Returns a dict mapping suffix token (e.g. '_DRAFT') to the number of files
    whose stem ends with that token. Only tokens appearing on ≥2 files are returned.
    """
    suffix_counts: Dict[str, int] = defaultdict(int)
    for filename in filenames:
        stem = Path(filename).stem
        for delimiter in ['_', '-', ' ']:
            if delimiter in stem:
                token = stem.rsplit(delimiter, 1)[-1]
                if token:
                    suffix_counts[f"{delimiter}{token}"] += 1
                break
    return {s: c for s, c in suffix_counts.items() if c >= 2}


def match_suffix(filename: str, suffixes: List[str]) -> Optional[str]:
    """Check if the filename stem ends with any of the given suffix tokens.

    Matching is case-insensitive. Returns the matched token or None.
    """
    stem = Path(filename).stem
    for token in suffixes:
        if stem.lower().endswith(token.lower()):
            return token
    return None


def get_group_name_ae(filename: str) -> Tuple[str, float]:
    """AE Render Output preset: strip trailing _#### before deriving the group name."""
    m = AE_FRAME_PATTERN.match(filename)
    if m:
        return m.group(1), 1.0
    return get_group_name(filename)


def group_files_by_preset(
    filenames: List[str],
    preset: GroupingPreset,
    confidence_threshold: float = 0.4,
) -> Tuple[Dict[str, List[str]], List[str]]:
    """Group files using the specified GroupingPreset.

    Returns the same (groups_dict, unsorted_files) tuple as group_files_by_pattern.
    """
    if preset.name == PRESET_AE_RENDER.name:
        groups: Dict[str, List[str]] = defaultdict(list)
        unsorted: List[str] = []
        for fname in filenames:
            group_name, conf = get_group_name_ae(fname)
            if conf >= confidence_threshold:
                groups[group_name].append(fname)
            else:
                unsorted.append(fname)
        # Promote single-file groups to unsorted
        final_groups: Dict[str, List[str]] = {}
        for gn, files in groups.items():
            if len(files) >= 2:
                final_groups[gn] = files
            else:
                unsorted.extend(files)
        return final_groups, unsorted
    else:
        return group_files_by_pattern(filenames, confidence_threshold)
