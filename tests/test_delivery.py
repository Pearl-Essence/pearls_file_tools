"""Comprehensive tests for core/delivery.py."""

import zipfile
from pathlib import Path

import pytest

from core.delivery import (
    DeliveryProfile,
    DeliveryValidator,
    DuplicateGroup,
    HandoffResult,
    HandoffRule,
    ValidationIssue,
    ValidationReport,
    create_delivery_zip,
    default_handoff_rules,
    find_case_collisions,
    find_duplicates,
    list_delivery_files,
    run_handoff_checks,
)

# ── DeliveryProfile ─────────────────────────────────────────────────────────

class TestDeliveryProfile:
    def test_defaults(self):
        p = DeliveryProfile()
        assert p.name == "Default"
        assert p.require_version_suffix is True
        assert p.min_video_size_bytes == 1024 * 1024
        assert "_WIP" in p.banned_terms

    def test_to_dict_from_dict_roundtrip(self):
        p = DeliveryProfile(name="Custom", banned_terms=["BAD"],
                           min_video_size_bytes=500, check_hidden_files=False)
        d = p.to_dict()
        p2 = DeliveryProfile.from_dict(d)
        assert p2.name == "Custom"
        assert p2.banned_terms == ["BAD"]
        assert p2.min_video_size_bytes == 500
        assert p2.check_hidden_files is False

    def test_from_dict_defaults(self):
        p = DeliveryProfile.from_dict({})
        assert p.name == "Default"


# ── ValidationReport ────────────────────────────────────────────────────────

class TestValidationReport:
    def test_passed_no_errors(self):
        report = ValidationReport(directory=Path("/test"), issues=[], total_files=5)
        assert report.passed is True

    def test_passed_with_warnings_only(self):
        issues = [ValidationIssue(filepath=Path("a"), rule="test",
                                  description="warn", severity="warning")]
        report = ValidationReport(directory=Path("/test"), issues=issues, total_files=5)
        assert report.passed is True

    def test_failed_with_errors(self):
        issues = [ValidationIssue(filepath=Path("a"), rule="test",
                                  description="err", severity="error")]
        report = ValidationReport(directory=Path("/test"), issues=issues, total_files=5)
        assert report.passed is False

    def test_issues_by_rule(self):
        issues = [
            ValidationIssue(filepath=Path("a"), rule="r1", description="a"),
            ValidationIssue(filepath=Path("b"), rule="r1", description="b"),
            ValidationIssue(filepath=Path("c"), rule="r2", description="c"),
        ]
        report = ValidationReport(directory=Path("/test"), issues=issues, total_files=3)
        by_rule = report.issues_by_rule()
        assert len(by_rule["r1"]) == 2
        assert len(by_rule["r2"]) == 1

    def test_error_count(self):
        issues = [
            ValidationIssue(filepath=Path("a"), rule="r", description="a", severity="error"),
            ValidationIssue(filepath=Path("b"), rule="r", description="b", severity="warning"),
        ]
        report = ValidationReport(directory=Path("/test"), issues=issues, total_files=2)
        assert report.error_count() == 1
        assert report.warning_count() == 1


# ── DuplicateGroup ──────────────────────────────────────────────────────────

class TestDuplicateGroup:
    def test_size_bytes(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"x" * 100)
        dg = DuplicateGroup(hash="abc", files=[f])
        assert dg.size_bytes() == 100

    def test_size_bytes_empty(self):
        dg = DuplicateGroup(hash="abc", files=[])
        assert dg.size_bytes() == 0

    def test_wasted_bytes(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"x" * 100)
        f2.write_bytes(b"x" * 100)
        dg = DuplicateGroup(hash="abc", files=[f1, f2])
        assert dg.wasted_bytes() == 100  # 1 duplicate × 100 bytes


# ── DeliveryValidator ───────────────────────────────────────────────────────

class TestDeliveryValidator:
    @pytest.fixture
    def validator(self):
        return DeliveryValidator()

    def test_clean_directory(self, validator, tmp_path):
        (tmp_path / "clip_v01.mov").write_bytes(b"x" * (2 * 1024 * 1024))
        report = validator.validate(tmp_path)
        errors = [i for i in report.issues if i.severity == "error"]
        assert len(errors) == 0

    def test_banned_term_detected(self, validator, tmp_path):
        (tmp_path / "clip_WIP.mov").write_bytes(b"x" * (2 * 1024 * 1024))
        report = validator.validate(tmp_path)
        rules = [i.rule for i in report.issues]
        assert "banned_term" in rules

    def test_missing_version_suffix(self, validator, tmp_path):
        (tmp_path / "clip.mov").write_bytes(b"x" * (2 * 1024 * 1024))
        report = validator.validate(tmp_path)
        rules = [i.rule for i in report.issues]
        assert "missing_version_suffix" in rules

    def test_version_suffix_accepted(self, validator, tmp_path):
        (tmp_path / "clip_v02.mov").write_bytes(b"x" * (2 * 1024 * 1024))
        report = validator.validate(tmp_path)
        version_issues = [i for i in report.issues if i.rule == "missing_version_suffix"]
        assert len(version_issues) == 0

    def test_FINAL_suffix_accepted(self, validator, tmp_path):
        (tmp_path / "clip_FINAL.mov").write_bytes(b"x" * (2 * 1024 * 1024))
        report = validator.validate(tmp_path)
        version_issues = [i for i in report.issues if i.rule == "missing_version_suffix"]
        assert len(version_issues) == 0

    def test_small_video_flagged(self, validator, tmp_path):
        (tmp_path / "tiny_v01.mov").write_bytes(b"x" * 100)
        report = validator.validate(tmp_path)
        rules = [i.rule for i in report.issues]
        assert "small_file" in rules

    def test_hidden_file_warning(self, validator, tmp_path):
        (tmp_path / ".hidden").write_bytes(b"x")
        report = validator.validate(tmp_path)
        hidden_issues = [i for i in report.issues if i.rule == "hidden_file"]
        assert len(hidden_issues) == 1
        assert hidden_issues[0].severity == "warning"

    def test_custom_profile(self, validator, tmp_path):
        profile = DeliveryProfile(
            require_version_suffix=False,
            check_hidden_files=False,
            min_video_size_bytes=0,
            banned_terms=[],
        )
        (tmp_path / ".hidden").write_bytes(b"x")
        (tmp_path / "clip.mov").write_bytes(b"x")
        report = validator.validate(tmp_path, profile=profile)
        assert len(report.issues) == 0

    def test_total_files_count(self, validator, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        report = validator.validate(tmp_path)
        assert report.total_files == 2

    def test_recursive_scan(self, validator, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "clip_WIP.mov").write_bytes(b"x" * (2 * 1024 * 1024))
        report = validator.validate(tmp_path)
        banned = [i for i in report.issues if i.rule == "banned_term"]
        assert len(banned) == 1


# ── list_delivery_files ─────────────────────────────────────────────────────

class TestListDeliveryFiles:
    def test_excludes_hidden(self, tmp_path):
        (tmp_path / "visible.txt").write_text("ok")
        (tmp_path / ".hidden").write_text("hidden")
        files = list_delivery_files(tmp_path)
        names = [f.name for f in files]
        assert "visible.txt" in names
        assert ".hidden" not in names

    def test_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("ok")
        files = list_delivery_files(tmp_path)
        names = [f.name for f in files]
        assert "nested.txt" in names

    def test_sorted(self, tmp_path):
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "a.txt").write_text("a")
        files = list_delivery_files(tmp_path)
        assert files == sorted(files)

    def test_empty_dir(self, tmp_path):
        assert list_delivery_files(tmp_path) == []


# ── create_delivery_zip ─────────────────────────────────────────────────────

class TestCreateDeliveryZip:
    def test_creates_zip(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("content")
        out = tmp_path / "out"
        out.mkdir()
        zip_path = create_delivery_zip(src, "TestProject", out)
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        assert "TestProject" in zip_path.stem

    def test_zip_contains_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("content")
        out = tmp_path / "out"
        out.mkdir()
        zip_path = create_delivery_zip(src, "Test", out)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "file.txt" in names

    def test_progress_callback(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("content")
        out = tmp_path / "out"
        out.mkdir()
        progress_calls = []
        create_delivery_zip(src, "Test", out,
                           progress_cb=lambda msg, cur, tot: progress_calls.append((msg, cur, tot)))
        assert len(progress_calls) > 0

    def test_cancel_check(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("content")
        out = tmp_path / "out"
        out.mkdir()
        with pytest.raises(InterruptedError):
            create_delivery_zip(src, "Test", out, cancel_check=lambda: True)

    def test_special_chars_in_name(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("content")
        out = tmp_path / "out"
        out.mkdir()
        zip_path = create_delivery_zip(src, "Test Project (2024)", out)
        assert zip_path.exists()


# ── find_duplicates ─────────────────────────────────────────────────────────

class TestFindDuplicates:
    def test_finds_exact_duplicates(self, tmp_path):
        (tmp_path / "a.txt").write_bytes(b"same content")
        (tmp_path / "b.txt").write_bytes(b"same content")
        dups = find_duplicates(tmp_path)
        assert len(dups) == 1
        assert len(dups[0].files) == 2

    def test_no_duplicates(self, tmp_path):
        (tmp_path / "a.txt").write_bytes(b"content a")
        (tmp_path / "b.txt").write_bytes(b"content b")
        dups = find_duplicates(tmp_path)
        assert len(dups) == 0

    def test_same_size_different_content(self, tmp_path):
        (tmp_path / "a.txt").write_bytes(b"aaaa")
        (tmp_path / "b.txt").write_bytes(b"bbbb")
        dups = find_duplicates(tmp_path)
        assert len(dups) == 0

    def test_cancel_check(self, tmp_path):
        (tmp_path / "a.txt").write_bytes(b"content")
        dups = find_duplicates(tmp_path, cancel_check=lambda: True)
        assert dups == []

    def test_empty_dir(self, tmp_path):
        dups = find_duplicates(tmp_path)
        assert dups == []

    def test_skips_symlinks(self, tmp_path):
        real = tmp_path / "real.txt"
        real.write_bytes(b"content")
        link = tmp_path / "link.txt"
        try:
            link.symlink_to(real)
        except OSError:
            pytest.skip("Symlinks not supported")
        dups = find_duplicates(tmp_path)
        assert len(dups) == 0


# ── find_case_collisions ───────────────────────────────────────────────────

class TestFindCaseCollisions:
    def test_detects_collisions(self, tmp_path):
        (tmp_path / "File.txt").write_text("a")
        (tmp_path / "file.txt").write_text("b")
        # On case-insensitive FS only one file survives
        if len(list(tmp_path.iterdir())) == 2:
            groups = find_case_collisions(tmp_path)
            assert len(groups) >= 1

    def test_no_collisions(self, tmp_path):
        (tmp_path / "alpha.txt").write_text("a")
        (tmp_path / "beta.txt").write_text("b")
        groups = find_case_collisions(tmp_path)
        assert len(groups) == 0


# ── default_handoff_rules ──────────────────────────────────────────────────

class TestDefaultHandoffRules:
    def test_returns_list(self):
        rules = default_handoff_rules()
        assert len(rules) == 4
        assert all(isinstance(r, HandoffRule) for r in rules)

    def test_luts_folder_check(self, tmp_path):
        rules = default_handoff_rules()
        luts_rule = [r for r in rules if "luts" in r.name.lower()][0]
        assert luts_rule.check_fn(tmp_path) is False
        (tmp_path / "luts").mkdir()
        assert luts_rule.check_fn(tmp_path) is True

    def test_audio_stems_check(self, tmp_path):
        rules = default_handoff_rules()
        audio_rule = [r for r in rules if "audio" in r.name.lower()][0]
        assert audio_rule.check_fn(tmp_path) is False
        (tmp_path / "audio").mkdir()
        assert audio_rule.check_fn(tmp_path) is True

    def test_no_offline_check(self, tmp_path):
        rules = default_handoff_rules()
        offline_rule = [r for r in rules if "offline" in r.name.lower()][0]
        (tmp_path / "good.txt").write_text("ok")
        assert offline_rule.check_fn(tmp_path) is True
        (tmp_path / "clip_OFFLINE.mov").write_text("bad")
        assert offline_rule.check_fn(tmp_path) is False


# ── run_handoff_checks ──────────────────────────────────────────────────────

class TestRunHandoffChecks:
    def test_all_pass(self, tmp_path):
        (tmp_path / "luts").mkdir()
        (tmp_path / "audio").mkdir()
        (tmp_path / "good.txt").write_text("ok")
        results = run_handoff_checks(tmp_path)
        assert all(isinstance(r, HandoffResult) for r in results)

    def test_custom_rules(self, tmp_path):
        rule = HandoffRule(name="test", check_fn=lambda d: True)
        results = run_handoff_checks(tmp_path, rules=[rule])
        assert len(results) == 1
        assert results[0].passed is True

    def test_exception_in_rule(self, tmp_path):
        rule = HandoffRule(name="bad_rule", check_fn=lambda d: 1/0)
        results = run_handoff_checks(tmp_path, rules=[rule])
        assert results[0].passed is False
        assert "division by zero" in results[0].detail
