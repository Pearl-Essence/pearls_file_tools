"""Delivery & handoff utilities for Pearl's File Tools."""

import datetime
import hashlib
import os
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional


def _long_path(p: Path) -> str:
    """Return a path string safe for >260-char paths on Windows.

    On macOS/Linux this is just ``str(p)``. On Windows we prepend ``\\\\?\\``
    (or ``\\\\?\\UNC\\`` for UNC paths) so ``open()`` and ``os.stat()`` work
    even when LongPathsEnabled is off in the registry — a common situation
    on locked-down studio Windows boxes.
    """
    if sys.platform != "win32":
        return str(p)
    s = os.fspath(p)
    if s.startswith("\\\\?\\"):
        return s
    abspath = os.path.abspath(s)
    if abspath.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abspath.lstrip("\\")
    return "\\\\?\\" + abspath


# Data models


@dataclass
class DeliveryProfile:
    name: str = "Default"
    require_version_suffix: bool = True  # video must have _FINAL or _v##
    min_video_size_bytes: int = 1024 * 1024  # 1 MB
    banned_terms: List[str] = field(default_factory=lambda: ["_WIP", "_DRAFT", "_TEMP", "_v00", "OFFLINE"])
    check_hidden_files: bool = True
    check_case_duplicates: bool = True
    handoff_rules: List["HandoffRule"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "require_version_suffix": self.require_version_suffix,
            "min_video_size_bytes": self.min_video_size_bytes,
            "banned_terms": self.banned_terms,
            "check_hidden_files": self.check_hidden_files,
            "check_case_duplicates": self.check_case_duplicates,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DeliveryProfile":
        p = cls()
        p.name = d.get("name", p.name)
        p.require_version_suffix = d.get("require_version_suffix", p.require_version_suffix)
        p.min_video_size_bytes = d.get("min_video_size_bytes", p.min_video_size_bytes)
        p.banned_terms = d.get("banned_terms", p.banned_terms)
        p.check_hidden_files = d.get("check_hidden_files", p.check_hidden_files)
        p.check_case_duplicates = d.get("check_case_duplicates", p.check_case_duplicates)
        return p


@dataclass
class ValidationIssue:
    filepath: Path
    rule: str
    description: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class ValidationReport:
    directory: Path
    issues: List[ValidationIssue]
    total_files: int

    @property
    def passed(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def issues_by_rule(self) -> Dict[str, List[ValidationIssue]]:
        result: Dict[str, List[ValidationIssue]] = {}
        for issue in self.issues:
            result.setdefault(issue.rule, []).append(issue)
        return result

    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


@dataclass
class DuplicateGroup:
    hash: str
    files: List[Path]

    def size_bytes(self) -> int:
        try:
            return self.files[0].stat().st_size if self.files else 0
        except OSError:
            return 0

    def wasted_bytes(self) -> int:
        return self.size_bytes() * (len(self.files) - 1)


@dataclass
class HandoffRule:
    name: str
    check_fn: Callable[[Path], bool]
    required: bool = True
    description: str = ""


@dataclass
class HandoffResult:
    rule: HandoffRule
    passed: bool
    detail: str = ""


# Built-in handoff rules factory


def _check_luts_folder(d: Path) -> bool:
    return any(p.is_dir() and p.name.lower() == "luts" for p in d.iterdir())


def _check_audio_stems(d: Path) -> bool:
    for name in ("audio", "stems", "audio_stems", "audio stems"):
        if any(p.is_dir() and p.name.lower() == name for p in d.iterdir()):
            return True
    return False


def _check_no_offline_files(d: Path) -> bool:
    return not any("OFFLINE" in p.name.upper() for p in d.rglob("*") if p.is_file())


def _check_no_tiny_video_files(d: Path) -> bool:
    from constants import VIDEO_EXTENSIONS

    for p in d.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
            try:
                if p.stat().st_size < 1024 * 1024:
                    return False
            except OSError:
                pass
    return True


def default_handoff_rules() -> List[HandoffRule]:
    """Return the standard colorist/delivery handoff rules."""
    return [
        HandoffRule(
            name="luts/ folder present",
            check_fn=_check_luts_folder,
            required=False,
            description="A 'luts' subfolder should exist for colorist handoff",
        ),
        HandoffRule(
            name="Audio stems folder present",
            check_fn=_check_audio_stems,
            required=False,
            description="An 'audio' or 'stems' subfolder should exist",
        ),
        HandoffRule(
            name="No OFFLINE files",
            check_fn=_check_no_offline_files,
            required=True,
            description="No files should contain 'OFFLINE' in their name",
        ),
        HandoffRule(
            name="No tiny video files (<1 MB)",
            check_fn=_check_no_tiny_video_files,
            required=True,
            description="All video files should be at least 1 MB",
        ),
    ]


# DeliveryValidator

_VERSION_RE = re.compile(r"_v\d+", re.IGNORECASE)
_FINAL_RE = re.compile(r"_FINAL", re.IGNORECASE)


class DeliveryValidator:
    """Validate a directory against a DeliveryProfile."""

    @staticmethod
    def _check_banned_terms(all_files: List[Path], profile: DeliveryProfile) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for fp in all_files:
            name_upper = fp.name.upper()
            for term in profile.banned_terms:
                if term.upper() in name_upper:
                    issues.append(
                        ValidationIssue(filepath=fp, rule="banned_term", description=f"Contains banned term '{term}'")
                    )
                    break
        return issues

    @staticmethod
    def _check_version_suffix(all_files: List[Path]) -> List[ValidationIssue]:
        from constants import VIDEO_EXTENSIONS

        issues: List[ValidationIssue] = []
        for fp in all_files:
            if fp.suffix.lower() in VIDEO_EXTENSIONS:
                stem = fp.stem
                if not (_VERSION_RE.search(stem) or _FINAL_RE.search(stem)):
                    issues.append(
                        ValidationIssue(
                            filepath=fp,
                            rule="missing_version_suffix",
                            description="Video file lacks _FINAL or _v## suffix",
                        )
                    )
        return issues

    @staticmethod
    def _check_case_duplicates(all_files: List[Path]) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        seen: Dict[str, Path] = {}
        for fp in all_files:
            key = fp.name.lower()
            if key in seen:
                issues.append(
                    ValidationIssue(
                        filepath=fp,
                        rule="case_duplicate",
                        description=f"Case-insensitive name collision with '{seen[key].name}'",
                    )
                )
            else:
                seen[key] = fp
        return issues

    @staticmethod
    def _check_small_videos(all_files: List[Path], profile: DeliveryProfile) -> List[ValidationIssue]:
        from constants import VIDEO_EXTENSIONS

        issues: List[ValidationIssue] = []
        thresh = profile.min_video_size_bytes
        thresh_mb = thresh / (1024 * 1024)
        for fp in all_files:
            if fp.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            try:
                size = fp.stat().st_size
                if size < thresh:
                    issues.append(
                        ValidationIssue(
                            filepath=fp,
                            rule="small_file",
                            description=f"Video is {size / 1024:.1f} KB (threshold {thresh_mb:.0f} MB — possible corrupt render)",
                        )
                    )
            except OSError:
                pass
        return issues

    @staticmethod
    def _check_hidden_files(all_files: List[Path]) -> List[ValidationIssue]:
        return [
            ValidationIssue(
                filepath=fp, rule="hidden_file", description="Hidden file (name starts with '.')", severity="warning"
            )
            for fp in all_files
            if fp.name.startswith(".")
        ]

    def validate(self, directory: Path, profile: Optional[DeliveryProfile] = None) -> ValidationReport:
        if profile is None:
            profile = DeliveryProfile()

        all_files = [p for p in directory.rglob("*") if p.is_file()]
        issues: List[ValidationIssue] = []

        issues.extend(self._check_banned_terms(all_files, profile))
        if profile.require_version_suffix:
            issues.extend(self._check_version_suffix(all_files))
        if profile.check_case_duplicates:
            issues.extend(self._check_case_duplicates(all_files))
        if profile.min_video_size_bytes > 0:
            issues.extend(self._check_small_videos(all_files, profile))
        if profile.check_hidden_files:
            issues.extend(self._check_hidden_files(all_files))

        return ValidationReport(directory=directory, issues=issues, total_files=len(all_files))


# Delivery package


def list_delivery_files(source_dir: Path) -> List[Path]:
    """Return files that would be included in a delivery zip (no hidden files)."""
    out: List[Path] = []
    for fp in source_dir.rglob("*"):
        try:
            if fp.is_file() and not fp.is_symlink() and not fp.name.startswith("."):
                out.append(fp)
        except OSError:
            continue
    return sorted(out)


def _zip_single_file(zf, fp, source_dir, idx, total, progress_cb):
    try:
        arcname = fp.relative_to(source_dir)
        zf.write(_long_path(fp), str(arcname))
    except (OSError, RuntimeError, ValueError) as exc:
        if progress_cb is not None:
            progress_cb(f"Skipping {fp.name}: {exc}", idx + 1, total)
        return
    if progress_cb is not None and (idx % 16 == 0 or idx == total - 1):
        progress_cb(f"Zipped {fp.name}", idx + 1, total)


def create_delivery_zip(
    source_dir: Path,
    project_name: str,
    output_dir: Path,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Path:
    """Create ``[PROJECT]_DELIVERY_[YYYYMMDD].zip`` and return its path."""
    date_str = datetime.date.today().strftime("%Y%m%d")
    safe_name = re.sub(r"[^\w\-]", "_", project_name)
    zip_path = output_dir / f"{safe_name}_DELIVERY_{date_str}.zip"

    files = list_delivery_files(source_dir)
    total = len(files)

    try:
        with zipfile.ZipFile(_long_path(zip_path), "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for idx, fp in enumerate(files):
                if cancel_check is not None and cancel_check():
                    raise InterruptedError("Cancelled mid-zip")
                _zip_single_file(zf, fp, source_dir, idx, total, progress_cb)
    except InterruptedError:
        try:
            zip_path.unlink()
        except OSError:
            pass
        raise

    return zip_path


# Duplicate detection


def _file_hash(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(_long_path(filepath), "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _bucket_by_size(directory: Path, cancel_check: Callable) -> Optional[List[Path]]:
    size_buckets: Dict[int, List[Path]] = defaultdict(list)
    for fp in directory.rglob("*"):
        if cancel_check():
            return None
        try:
            if not fp.is_file() or fp.is_symlink():
                continue
            size_buckets[fp.stat().st_size].append(fp)
        except OSError:
            continue
    return [fp for files in size_buckets.values() if len(files) > 1 for fp in files]


def _hash_candidates(
    candidates: List[Path],
    progress_cb: Optional[Callable],
    cancel_check: Callable,
) -> Optional[Dict[str, List[Path]]]:
    total = len(candidates)
    hash_map: Dict[str, List[Path]] = defaultdict(list)
    for idx, fp in enumerate(candidates):
        if cancel_check():
            return None
        try:
            digest = _file_hash(fp)
            hash_map[digest].append(fp)
        except OSError:
            continue
        if progress_cb is not None and (idx % 16 == 0 or idx == total - 1):
            progress_cb(f"Hashed {fp.name}", idx + 1, total)
    return hash_map


def find_duplicates(
    directory: Path,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[DuplicateGroup]:
    """Group files by content hash. Returns groups with 2+ files."""
    if cancel_check is None:

        def cancel_check():
            return False

    candidates = _bucket_by_size(directory, cancel_check)
    if candidates is None:
        return []

    hash_map = _hash_candidates(candidates, progress_cb, cancel_check)
    if hash_map is None:
        return []

    return [DuplicateGroup(hash=h, files=sorted(files)) for h, files in hash_map.items() if len(files) > 1]


def find_case_collisions(directory: Path) -> List[List[Path]]:
    """Return groups of files whose names differ only by case."""
    name_map: Dict[str, List[Path]] = {}
    for fp in directory.rglob("*"):
        if fp.is_file():
            name_map.setdefault(fp.name.lower(), []).append(fp)
    return [sorted(group) for group in name_map.values() if len(group) > 1]


# Colorist handoff validation


def run_handoff_checks(directory: Path, rules: Optional[List[HandoffRule]] = None) -> List[HandoffResult]:
    """Run handoff rules against *directory* and return results."""
    if rules is None:
        rules = default_handoff_rules()
    results = []
    for rule in rules:
        try:
            passed = rule.check_fn(directory)
            results.append(HandoffResult(rule=rule, passed=passed))
        except Exception as exc:
            results.append(HandoffResult(rule=rule, passed=False, detail=str(exc)))
    return results


# Manifest / shot list export


_MANIFEST_FIELDS = [
    "filename",
    "folder",
    "size_bytes",
    "extension",
    "codec",
    "resolution",
    "fps",
    "audio_channels",
    "duration_secs",
    "date_modified",
]


def _extract_media_fields(fp: Path) -> dict:
    from core.media_info import get_media_info

    fields = {"codec": "", "resolution": "", "fps": "", "audio_channels": "", "duration_secs": ""}
    try:
        info = get_media_info(fp)
        if info:
            if info.duration_secs is not None:
                fields["duration_secs"] = f"{info.duration_secs:.3f}"
            fields["codec"] = info.codec or ""
            fields["resolution"] = info.resolution_str or ""
            fields["fps"] = info.fps_str or ""
            fields["audio_channels"] = str(info.audio_channels) if info.audio_channels else ""
    except Exception:
        pass
    return fields


def _build_manifest_row(fp: Path, directory: Path) -> Optional[dict]:
    try:
        stat = fp.stat()
    except OSError:
        return None
    row = {
        "filename": fp.name,
        "folder": str(fp.parent.relative_to(directory)),
        "size_bytes": stat.st_size,
        "extension": fp.suffix.lower(),
        "date_modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }
    row.update(_extract_media_fields(fp))
    return row


def export_manifest(directory: Path, output_path: Path) -> int:
    """Write a CSV manifest of all files in *directory*. Returns file count."""
    import csv

    rows = []
    for fp in sorted(directory.rglob("*")):
        if not fp.is_file():
            continue
        row = _build_manifest_row(fp, directory)
        if row is not None:
            rows.append(row)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
