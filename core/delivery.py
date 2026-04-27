"""Delivery & handoff utilities for Pearl's File Tools."""

import datetime
import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DeliveryProfile:
    name: str = "Default"
    require_version_suffix: bool = True   # video must have _FINAL or _v##
    min_video_size_bytes: int = 1024 * 1024  # 1 MB
    banned_terms: List[str] = field(default_factory=lambda: [
        '_WIP', '_DRAFT', '_TEMP', '_v00', 'OFFLINE'
    ])
    check_hidden_files: bool = True
    check_case_duplicates: bool = True
    handoff_rules: List['HandoffRule'] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'require_version_suffix': self.require_version_suffix,
            'min_video_size_bytes': self.min_video_size_bytes,
            'banned_terms': self.banned_terms,
            'check_hidden_files': self.check_hidden_files,
            'check_case_duplicates': self.check_case_duplicates,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'DeliveryProfile':
        p = cls()
        p.name = d.get('name', p.name)
        p.require_version_suffix = d.get('require_version_suffix', p.require_version_suffix)
        p.min_video_size_bytes = d.get('min_video_size_bytes', p.min_video_size_bytes)
        p.banned_terms = d.get('banned_terms', p.banned_terms)
        p.check_hidden_files = d.get('check_hidden_files', p.check_hidden_files)
        p.check_case_duplicates = d.get('check_case_duplicates', p.check_case_duplicates)
        return p


@dataclass
class ValidationIssue:
    filepath: Path
    rule: str
    description: str
    severity: str = "error"   # "error" or "warning"


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


# ─────────────────────────────────────────────────────────────────────────────
# Built-in handoff rules factory
# ─────────────────────────────────────────────────────────────────────────────

def default_handoff_rules() -> List[HandoffRule]:
    """Return the standard colorist/delivery handoff rules."""

    def has_luts_folder(d: Path) -> bool:
        return any(p.is_dir() and p.name.lower() == 'luts' for p in d.iterdir())

    def has_audio_stems(d: Path) -> bool:
        for name in ('audio', 'stems', 'audio_stems', 'audio stems'):
            if any(p.is_dir() and p.name.lower() == name for p in d.iterdir()):
                return True
        return False

    def no_offline_files(d: Path) -> bool:
        return not any(
            'OFFLINE' in p.name.upper()
            for p in d.rglob('*') if p.is_file()
        )

    def no_tiny_video_files(d: Path) -> bool:
        from constants import VIDEO_EXTENSIONS
        for p in d.rglob('*'):
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
                try:
                    if p.stat().st_size < 1024 * 1024:
                        return False
                except OSError:
                    pass
        return True

    return [
        HandoffRule(
            name="luts/ folder present",
            check_fn=has_luts_folder,
            required=False,
            description="A 'luts' subfolder should exist for colorist handoff",
        ),
        HandoffRule(
            name="Audio stems folder present",
            check_fn=has_audio_stems,
            required=False,
            description="An 'audio' or 'stems' subfolder should exist",
        ),
        HandoffRule(
            name="No OFFLINE files",
            check_fn=no_offline_files,
            required=True,
            description="No files should contain 'OFFLINE' in their name",
        ),
        HandoffRule(
            name="No tiny video files (<1 MB)",
            check_fn=no_tiny_video_files,
            required=True,
            description="All video files should be at least 1 MB",
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# DeliveryValidator
# ─────────────────────────────────────────────────────────────────────────────

_VERSION_RE = re.compile(r'_v\d+', re.IGNORECASE)
_FINAL_RE = re.compile(r'_FINAL', re.IGNORECASE)


class DeliveryValidator:
    """Validate a directory against a DeliveryProfile."""

    def validate(self, directory: Path, profile: Optional[DeliveryProfile] = None) -> ValidationReport:
        if profile is None:
            profile = DeliveryProfile()

        issues: List[ValidationIssue] = []
        all_files: List[Path] = []

        for p in directory.rglob('*'):
            if p.is_file():
                all_files.append(p)

        # 1. Banned terms
        for fp in all_files:
            name_upper = fp.name.upper()
            for term in profile.banned_terms:
                if term.upper() in name_upper:
                    issues.append(ValidationIssue(
                        filepath=fp,
                        rule="banned_term",
                        description=f"Contains banned term '{term}'",
                    ))
                    break

        # 2. Video files must have _FINAL or _v## suffix
        if profile.require_version_suffix:
            from constants import VIDEO_EXTENSIONS
            for fp in all_files:
                if fp.suffix.lower() in VIDEO_EXTENSIONS:
                    stem = fp.stem
                    if not (_VERSION_RE.search(stem) or _FINAL_RE.search(stem)):
                        issues.append(ValidationIssue(
                            filepath=fp,
                            rule="missing_version_suffix",
                            description="Video file lacks _FINAL or _v## suffix",
                        ))

        # 3. Case-insensitive name collisions
        if profile.check_case_duplicates:
            seen: Dict[str, Path] = {}
            for fp in all_files:
                key = fp.name.lower()
                if key in seen:
                    issues.append(ValidationIssue(
                        filepath=fp,
                        rule="case_duplicate",
                        description=f"Case-insensitive name collision with '{seen[key].name}'",
                    ))
                else:
                    seen[key] = fp

        # 4. Video files smaller than threshold
        if profile.min_video_size_bytes > 0:
            from constants import VIDEO_EXTENSIONS
            for fp in all_files:
                if fp.suffix.lower() in VIDEO_EXTENSIONS:
                    try:
                        size = fp.stat().st_size
                        if size < profile.min_video_size_bytes:
                            thresh_mb = profile.min_video_size_bytes / (1024 * 1024)
                            issues.append(ValidationIssue(
                                filepath=fp,
                                rule="small_file",
                                description=(
                                    f"Video is {size / 1024:.1f} KB "
                                    f"(threshold {thresh_mb:.0f} MB — possible corrupt render)"
                                ),
                            ))
                    except OSError:
                        pass

        # 5. Hidden files
        if profile.check_hidden_files:
            for fp in all_files:
                if fp.name.startswith('.'):
                    issues.append(ValidationIssue(
                        filepath=fp,
                        rule="hidden_file",
                        description="Hidden file (name starts with '.')",
                        severity="warning",
                    ))

        return ValidationReport(
            directory=directory,
            issues=issues,
            total_files=len(all_files),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Delivery package
# ─────────────────────────────────────────────────────────────────────────────

def list_delivery_files(source_dir: Path) -> List[Path]:
    """Return files that would be included in a delivery zip (no hidden files)."""
    return sorted(
        fp for fp in source_dir.rglob('*')
        if fp.is_file() and not fp.name.startswith('.')
    )


def create_delivery_zip(source_dir: Path, project_name: str, output_dir: Path) -> Path:
    """Create [PROJECT]_DELIVERY_[YYYYMMDD].zip and return its path."""
    date_str = datetime.date.today().strftime('%Y%m%d')
    safe_name = re.sub(r'[^\w\-]', '_', project_name)
    zip_name = f"{safe_name}_DELIVERY_{date_str}.zip"
    zip_path = output_dir / zip_name

    files = list_delivery_files(source_dir)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in files:
            arcname = fp.relative_to(source_dir)
            zf.write(fp, arcname)

    return zip_path


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate detection
# ─────────────────────────────────────────────────────────────────────────────

def _md5(filepath: Path) -> str:
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(directory: Path) -> List[DuplicateGroup]:
    """Group files by MD5 hash. Returns groups with 2+ files."""
    hash_map: Dict[str, List[Path]] = {}

    for fp in directory.rglob('*'):
        if not fp.is_file():
            continue
        try:
            digest = _md5(fp)
            hash_map.setdefault(digest, []).append(fp)
        except OSError:
            pass

    return [
        DuplicateGroup(hash=h, files=sorted(files))
        for h, files in hash_map.items()
        if len(files) > 1
    ]


def find_case_collisions(directory: Path) -> List[List[Path]]:
    """Return groups of files whose names differ only by case."""
    name_map: Dict[str, List[Path]] = {}
    for fp in directory.rglob('*'):
        if fp.is_file():
            name_map.setdefault(fp.name.lower(), []).append(fp)
    return [sorted(group) for group in name_map.values() if len(group) > 1]


# ─────────────────────────────────────────────────────────────────────────────
# Colorist handoff validation
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Manifest / shot list export
# ─────────────────────────────────────────────────────────────────────────────

def export_manifest(directory: Path, output_path: Path) -> int:
    """Write a CSV manifest of all files in *directory*. Returns file count."""
    import csv

    from core.media_info import get_media_info

    rows = []
    for fp in sorted(directory.rglob('*')):
        if not fp.is_file():
            continue
        try:
            stat = fp.stat()
        except OSError:
            continue

        duration_secs = ''
        try:
            info = get_media_info(fp)
            if info and info.duration_secs is not None:
                duration_secs = f"{info.duration_secs:.3f}"
        except Exception:
            pass

        rows.append({
            'filename': fp.name,
            'folder': str(fp.parent.relative_to(directory)),
            'size_bytes': stat.st_size,
            'extension': fp.suffix.lower(),
            'duration_secs': duration_secs,
            'date_modified': datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=['filename', 'folder', 'size_bytes', 'extension', 'duration_secs', 'date_modified'],
        )
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
