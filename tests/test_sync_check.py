"""Comprehensive tests for core/sync_check.py."""

import datetime
from pathlib import Path

from core.sync_check import (
    SyncEntry,
    SyncReport,
    _build_entry,
    _determine_status,
    _file_hash,
    _index_dir,
    compare_directories,
)

# ── _file_hash ────────────────────────────────────────────────────────────────────


class TestMd5:
    def test_consistent_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        h1 = _file_hash(f)
        h2 = _file_hash(f)
        assert h1 == h2
        assert len(h1) == 64

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"bbb")
        assert _file_hash(f1) != _file_hash(f2)

    def test_nonexistent_file(self, tmp_path):
        result = _file_hash(tmp_path / "nope.txt")
        assert result == ""

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        h = _file_hash(f)
        assert len(h) == 64


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


# ── _determine_status ─────────────────────────────────────────────────────


class TestDetermineStatus:
    def test_a_only(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_bytes(b"data")
        status = _determine_status(f, None, 1000.0, 0.0)
        assert status == "a_only"

    def test_b_only(self, tmp_path):
        f = tmp_path / "b.txt"
        f.write_bytes(b"data")
        status = _determine_status(None, f, 0.0, 1000.0)
        assert status == "b_only"

    def test_modified_both(self, tmp_path):
        fa = tmp_path / "a.txt"
        fb = tmp_path / "b.txt"
        fa.write_bytes(b"version a")
        fb.write_bytes(b"version b")
        status = _determine_status(fa, fb, 1000.0, 1000.0)
        assert status == "modified_both"

    def test_a_newer_same_content(self, tmp_path):
        fa = tmp_path / "a.txt"
        fb = tmp_path / "b.txt"
        fa.write_bytes(b"same")
        fb.write_bytes(b"same")
        status = _determine_status(fa, fb, 2000.0, 1000.0)
        assert status == "a_newer"

    def test_b_newer_same_content(self, tmp_path):
        fa = tmp_path / "a.txt"
        fb = tmp_path / "b.txt"
        fa.write_bytes(b"same")
        fb.write_bytes(b"same")
        status = _determine_status(fa, fb, 1000.0, 2000.0)
        assert status == "b_newer"

    def test_both_none(self):
        # Edge case: both paths None → b_only (since path_a is falsy)
        status = _determine_status(None, None, 0.0, 0.0)
        assert status == "b_only"


# ── _build_entry ──────────────────────────────────────────────────────────


class TestBuildEntry:
    def test_a_only_entry(self, tmp_path):
        fa = tmp_path / "a.txt"
        fa.write_bytes(b"data")
        index_a = {"file.txt": fa}
        index_b = {}
        entry = _build_entry("file.txt", index_a, index_b, None)
        assert entry is not None
        assert entry.status == "a_only"
        assert entry.rel_path == "file.txt"
        assert entry.path_a == fa
        assert entry.path_b is None
        assert entry.size_a > 0
        assert entry.size_b == 0

    def test_b_only_entry(self, tmp_path):
        fb = tmp_path / "b.txt"
        fb.write_bytes(b"data")
        index_a = {}
        index_b = {"file.txt": fb}
        entry = _build_entry("file.txt", index_a, index_b, None)
        assert entry is not None
        assert entry.status == "b_only"
        assert entry.path_b == fb

    def test_both_present_different_content(self, tmp_path):
        fa = tmp_path / "a.txt"
        fb = tmp_path / "b.txt"
        fa.write_bytes(b"version a content")
        fb.write_bytes(b"version b content")
        index_a = {"file.txt": fa}
        index_b = {"file.txt": fb}
        entry = _build_entry("file.txt", index_a, index_b, None)
        assert entry is not None
        assert entry.status == "modified_both"

    def test_filtered_by_since(self, tmp_path):
        fa = tmp_path / "a.txt"
        fa.write_bytes(b"data")
        index_a = {"file.txt": fa}
        index_b = {}
        # Set since_ts far in the future so it filters out the entry
        future_ts = fa.stat().st_mtime + 10000
        entry = _build_entry("file.txt", index_a, index_b, future_ts)
        assert entry is None

    def test_not_filtered_when_newer(self, tmp_path):
        fa = tmp_path / "a.txt"
        fa.write_bytes(b"data")
        index_a = {"file.txt": fa}
        index_b = {}
        # Set since_ts in the past so entry passes through
        past_ts = fa.stat().st_mtime - 10000
        entry = _build_entry("file.txt", index_a, index_b, past_ts)
        assert entry is not None

    def test_since_none_includes_all(self, tmp_path):
        fa = tmp_path / "a.txt"
        fa.write_bytes(b"data")
        index_a = {"file.txt": fa}
        index_b = {}
        entry = _build_entry("file.txt", index_a, index_b, None)
        assert entry is not None
