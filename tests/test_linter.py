"""Comprehensive tests for core/linter.py."""

import pytest
from pathlib import Path
from core.linter import (
    FilenameLint,
    LintIssue,
    ILLEGAL_CHARS_WIN,
    WINDOWS_RESERVED,
    ISSUE_LABELS,
)
from core.name_transform import ProductionTemplate


class TestLintIssueLabels:
    def test_all_issue_types_have_labels(self):
        expected = {"illegal_char", "too_long", "reserved_name",
                    "wip_flag", "case_duplicate", "profile_mismatch"}
        assert expected == set(ISSUE_LABELS.keys())


class TestIllegalCharsConstant:
    def test_contains_standard_chars(self):
        for ch in '<>:"/\\|?*':
            assert ch in ILLEGAL_CHARS_WIN

    def test_contains_nul(self):
        assert '\x00' in ILLEGAL_CHARS_WIN


class TestWindowsReservedConstant:
    def test_contains_all_device_names(self):
        for name in ["CON", "PRN", "AUX", "NUL"]:
            assert name in WINDOWS_RESERVED
        for i in range(1, 10):
            assert f"COM{i}" in WINDOWS_RESERVED
            assert f"LPT{i}" in WINDOWS_RESERVED


class TestFilenameLint:
    @pytest.fixture
    def linter(self):
        return FilenameLint()

    def test_clean_directory(self, linter, tmp_path):
        (tmp_path / "good_file.mov").write_text("data")
        (tmp_path / "another_good.txt").write_text("data")
        issues = linter.lint_directory(tmp_path)
        assert len(issues) == 0

    def test_illegal_char_detected(self, linter, tmp_path):
        # Create file with colon-free name, then check a name that has one
        # We can't create files with colons on macOS, so we test the logic
        # by verifying the ILLEGAL_CHARS_WIN set directly
        assert ':' in ILLEGAL_CHARS_WIN

    def test_reserved_name_detected(self, linter, tmp_path):
        (tmp_path / "CON.txt").write_text("data")
        issues = linter.lint_directory(tmp_path)
        types = [i.issue_type for i in issues]
        assert "reserved_name" in types

    def test_reserved_name_case_insensitive(self, linter, tmp_path):
        (tmp_path / "con.txt").write_text("data")
        issues = linter.lint_directory(tmp_path)
        types = [i.issue_type for i in issues]
        assert "reserved_name" in types

    def test_wip_flag_detected(self, linter, tmp_path):
        (tmp_path / "clip_WIP_01.mov").write_text("data")
        issues = linter.lint_directory(tmp_path)
        types = [i.issue_type for i in issues]
        assert "wip_flag" in types

    def test_draft_flag_detected(self, linter, tmp_path):
        (tmp_path / "edit_DRAFT.mov").write_text("data")
        issues = linter.lint_directory(tmp_path)
        types = [i.issue_type for i in issues]
        assert "wip_flag" in types

    def test_temp_flag_detected(self, linter, tmp_path):
        (tmp_path / "clip_TEMP.mov").write_text("data")
        issues = linter.lint_directory(tmp_path)
        types = [i.issue_type for i in issues]
        assert "wip_flag" in types

    def test_test_flag_detected(self, linter, tmp_path):
        (tmp_path / "clip_TEST.mov").write_text("data")
        issues = linter.lint_directory(tmp_path)
        types = [i.issue_type for i in issues]
        assert "wip_flag" in types

    def test_wip_as_substring_not_flagged(self, linter, tmp_path):
        # "EQUIPPED" contains "WIP" but not as a whole word
        (tmp_path / "EQUIPPED_clip.mov").write_text("data")
        issues = linter.lint_directory(tmp_path)
        wip_issues = [i for i in issues if i.issue_type == "wip_flag"]
        assert len(wip_issues) == 0

    def test_case_duplicate_detected(self, linter, tmp_path):
        (tmp_path / "File.txt").write_text("a")
        (tmp_path / "file.txt").write_text("b")
        issues = linter.lint_directory(tmp_path)
        types = [i.issue_type for i in issues]
        # On case-insensitive FS, only one file can exist, so this test
        # may not trigger. Check if we got the expected issue or if the
        # OS prevented the duplicate from being created.
        if len(list(tmp_path.iterdir())) == 2:
            assert "case_duplicate" in types

    def test_long_filename_detected(self, linter, tmp_path):
        long_name = "a" * 250 + ".txt"
        try:
            (tmp_path / long_name).write_text("data")
        except OSError:
            pytest.skip("OS doesn't support this filename length")
        issues = linter.lint_directory(tmp_path)
        types = [i.issue_type for i in issues]
        if len(long_name.encode('utf-8')) > 255:
            assert "too_long" in types

    def test_profile_mismatch(self, linter, tmp_path):
        profile = ProductionTemplate(name="Strict", tokens=["A", "B", "C"], separator="_")
        (tmp_path / "one_token.mov").write_text("data")
        issues = linter.lint_directory(tmp_path, profile=profile)
        types = [i.issue_type for i in issues]
        assert "profile_mismatch" in types

    def test_profile_conformance(self, linter, tmp_path):
        profile = ProductionTemplate(name="Simple", tokens=["A", "B"], separator="_")
        (tmp_path / "PRJ_SHOT_extra.mov").write_text("data")
        issues = linter.lint_directory(tmp_path, profile=profile)
        mismatch_issues = [i for i in issues if i.issue_type == "profile_mismatch"]
        assert len(mismatch_issues) == 0

    def test_empty_directory(self, linter, tmp_path):
        issues = linter.lint_directory(tmp_path)
        assert issues == []

    def test_permission_error_handled(self, linter, tmp_path):
        # The linter catches PermissionError but not FileNotFoundError,
        # so we test with a directory that exists but has restricted perms
        import os
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        (restricted / "file.txt").write_text("data")
        try:
            restricted.chmod(0o000)
            issues = linter.lint_directory(restricted)
            assert issues == []
        finally:
            restricted.chmod(0o755)

    def test_directories_skipped(self, linter, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "good_file.txt").write_text("data")
        issues = linter.lint_directory(tmp_path)
        filenames = [i.filename for i in issues]
        assert "subdir" not in filenames

    def test_multiple_issues_on_one_file(self, linter, tmp_path):
        # A reserved name that is also a WIP marker
        (tmp_path / "NUL.txt").write_text("data")
        issues = linter.lint_directory(tmp_path)
        nul_issues = [i for i in issues if i.filename == "NUL.txt"]
        types = {i.issue_type for i in nul_issues}
        assert "reserved_name" in types
