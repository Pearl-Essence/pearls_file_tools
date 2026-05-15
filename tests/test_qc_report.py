"""Comprehensive tests for core/qc_report.py."""

import pytest
from pathlib import Path
from unittest.mock import patch
from core.qc_report import _flag_file, _fmt_size, generate_qc_report


# ── _fmt_size ───────────────────────────────────────────────────────────────

class TestFmtSize:
    def test_bytes(self):
        assert _fmt_size(500) == "500 B"

    def test_kilobytes(self):
        assert _fmt_size(1024) == "1.0 KB"

    def test_megabytes(self):
        assert _fmt_size(1024 ** 2) == "1.0 MB"

    def test_gigabytes(self):
        assert _fmt_size(1024 ** 3) == "1.00 GB"

    def test_zero(self):
        assert _fmt_size(0) == "0 B"

    def test_fractional_kb(self):
        assert _fmt_size(1536) == "1.5 KB"


# ── _flag_file ──────────────────────────────────────────────────────────────

class TestFlagFile:
    def test_normal_file_ok(self, tmp_path):
        f = tmp_path / "good.txt"
        f.write_bytes(b"x" * 1000)
        assert _flag_file(f, 1024 * 1024) is None

    def test_zero_byte_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        assert _flag_file(f, 1024 * 1024) == "zero-byte"

    def test_small_video(self, tmp_path):
        f = tmp_path / "tiny.mov"
        f.write_bytes(b"x" * 100)
        flag = _flag_file(f, 1024 * 1024)
        assert flag is not None
        assert "small" in flag

    def test_non_video_not_flagged_for_size(self, tmp_path):
        f = tmp_path / "tiny.txt"
        f.write_bytes(b"x" * 100)
        assert _flag_file(f, 1024 * 1024) is None

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope.txt"
        assert _flag_file(f, 1024 * 1024) == "unreadable"

    def test_large_video_ok(self, tmp_path):
        f = tmp_path / "big.mov"
        f.write_bytes(b"x" * (2 * 1024 * 1024))
        assert _flag_file(f, 1024 * 1024) is None


# ── generate_qc_report ─────────────────────────────────────────────────────

class TestGenerateQcReport:
    @patch("core.media_info.get_media_info", return_value=None)
    def test_generates_html(self, mock_media, tmp_path):
        (tmp_path / "clip.mov").write_bytes(b"x" * 100)
        (tmp_path / "doc.txt").write_text("text")
        report_path = generate_qc_report(tmp_path, "TestProject",
                                         include_thumbnails=False)
        assert report_path.exists()
        assert report_path.suffix == ".html"
        content = report_path.read_text()
        assert "TestProject" in content

    @patch("core.media_info.get_media_info", return_value=None)
    def test_report_contains_files(self, mock_media, tmp_path):
        (tmp_path / "file_a.txt").write_text("a")
        (tmp_path / "file_b.txt").write_text("b")
        report_path = generate_qc_report(tmp_path, "Test",
                                         include_thumbnails=False)
        content = report_path.read_text()
        assert "file_a.txt" in content
        assert "file_b.txt" in content

    @patch("core.media_info.get_media_info", return_value=None)
    def test_empty_directory(self, mock_media, tmp_path):
        report_path = generate_qc_report(tmp_path, "Empty",
                                         include_thumbnails=False)
        assert report_path.exists()
        content = report_path.read_text()
        assert "0" in content  # total files = 0

    @patch("core.media_info.get_media_info", return_value=None)
    def test_flagged_count(self, mock_media, tmp_path):
        (tmp_path / "empty.txt").write_bytes(b"")  # zero-byte → flagged
        report_path = generate_qc_report(tmp_path, "Test",
                                         include_thumbnails=False)
        content = report_path.read_text()
        assert "zero-byte" in content

    @patch("core.media_info.get_media_info", return_value=None)
    def test_report_filename_format(self, mock_media, tmp_path):
        report_path = generate_qc_report(tmp_path, "Test",
                                         include_thumbnails=False)
        assert report_path.name.startswith("QC_Report_")
        assert report_path.name.endswith(".html")
