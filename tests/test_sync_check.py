"""Comprehensive tests for core/sync_check.py."""

import datetime
from pathlib import Path

from core.sync_check import (
    SyncEntry,
    SyncReport,
    _index_dir,
    _md5,
    compare_directories,
)

# ── _md5 ────────────────────────────────────────────────────────────────────


class TestMd5:
    def test_consistent_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        h1 = _md5(f)
        h2 = _md5(f)
        assert h1 == h2
        assert len(h1) == 32

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"bbb")
        assert _md5(f1) != _md5(f2)

    def test_nonexistent_file(self, tmp_path):
        result = _md5(tmp_path / "nope.txt")
        assert result == ""

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        h = _md5(f)
        assert len(h) == 32


# ── _index_dir ──────────────────────────────────────────────────────────────


class TestIndexDir:
    def test_indexes_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("b")
        index = _index_dir(tmp_path)
        assert "a.txt" in index
        assert str(Path("sub") / "b.txt") in index or "sub/b.txt" in index

    def test_skips_pearls_trash(self, tmp_path):
        trash = tmp_path / ".pearls_trash"
        trash.mkdir()
        (trash / "deleted.txt").write_text("gone")
        (tmp_path / "keep.txt").write_text("ok")
        index = _index_dir(tmp_path)
        assert "keep.txt" in index
        assert not any(".pearls_trash" in k for k in index)

    def test_empty_dir(self, tmp_path):
        assert _index_dir(tmp_path) == {}

    def test_nonexistent_dir(self):
        assert _index_dir(Path("/nonexistent_xyz")) == {}

    def test_skips_directories(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("data")
        index = _index_dir(tmp_path)
        assert len(index) == 1


# ── SyncReport ──────────────────────────────────────────────────────────────


class TestSyncReport:
    def test_by_status(self):
        entries = [
            SyncEntry("a.txt", "a_only", Path("a"), None),
            SyncEntry("b.txt", "b_only", None, Path("b")),
            SyncEntry("c.txt", "a_only", Path("c"), None),
        ]
        report = SyncReport(Path("/a"), Path("/b"), entries, datetime.datetime.now())
        assert len(report.by_status("a_only")) == 2
        assert len(report.by_status("b_only")) == 1
        assert len(report.by_status("modified_both")) == 0


# ── compare_directories ────────────────────────────────────────────────────


class TestCompareDirectories:
    def test_identical_dirs(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "file.txt").write_bytes(b"same")
        (dir_b / "file.txt").write_bytes(b"same")
        report = compare_directories(dir_a, dir_b)
        assert len(report.entries) == 1
        # Same content → b_newer (same md5, mtime comparison)
        assert report.entries[0].status in ("a_newer", "b_newer")

    def test_a_only(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "only_in_a.txt").write_text("a")
        report = compare_directories(dir_a, dir_b)
        assert len(report.entries) == 1
        assert report.entries[0].status == "a_only"

    def test_b_only(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_b / "only_in_b.txt").write_text("b")
        report = compare_directories(dir_a, dir_b)
        assert len(report.entries) == 1
        assert report.entries[0].status == "b_only"

    def test_modified_both(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "file.txt").write_bytes(b"version_a")
        (dir_b / "file.txt").write_bytes(b"version_b")
        report = compare_directories(dir_a, dir_b)
        assert report.entries[0].status == "modified_both"

    def test_since_filter(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "old.txt").write_text("old")
        (dir_b / "old.txt").write_text("old")
        # Set since to the future → everything filtered out
        future = datetime.datetime.now() + datetime.timedelta(hours=1)
        report = compare_directories(dir_a, dir_b, since=future)
        assert len(report.entries) == 0

    def test_empty_dirs(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        report = compare_directories(dir_a, dir_b)
        assert len(report.entries) == 0

    def test_report_metadata(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        report = compare_directories(dir_a, dir_b)
        assert report.dir_a == dir_a
        assert report.dir_b == dir_b
        assert isinstance(report.generated, datetime.datetime)

    def test_nested_files(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        sub_a = dir_a / "sub"
        sub_a.mkdir()
        (sub_a / "nested.txt").write_text("data")
        report = compare_directories(dir_a, dir_b)
        a_only = report.by_status("a_only")
        assert len(a_only) == 1
