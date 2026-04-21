"""Pattern matching and grouping utilities for Pearl's File Tools."""

from pathlib import Path
from typing import Tuple, Optional, Dict, List
from difflib import SequenceMatcher
from collections import defaultdict


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
