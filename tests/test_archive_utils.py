"""Comprehensive tests for core/archive_utils.py."""

import tarfile
import zipfile
from pathlib import Path

from core.archive_utils import (
    _is_unsafe_archive_path,
    _safe_path_under,
    _scrub_extracted,
    _validate_tar_entries,
    _validate_zip_entries,
    extract_archive,
    extract_tar,
    extract_zip,
    get_archive_type,
    smart_extract,
)

# ── _is_unsafe_archive_path ─────────────────────────────────────────────────

class TestIsUnsafeArchivePath:
    def test_safe_path(self):
        assert _is_unsafe_archive_path("dir/file.txt") is False

    def test_simple_relative(self):
        assert _is_unsafe_archive_path("dir/subdir/file.txt") is False

    def test_empty(self):
        assert _is_unsafe_archive_path("") is True

    def test_dot_dot(self):
        assert _is_unsafe_archive_path("../etc/passwd") is True

    def test_nested_dot_dot(self):
        assert _is_unsafe_archive_path("dir/../../etc/passwd") is True

    def test_absolute_unix(self):
        assert _is_unsafe_archive_path("/etc/passwd") is True

    def test_absolute_windows(self):
        assert _is_unsafe_archive_path("C:\\Windows\\System32") is True

    def test_windows_drive_forward_slash(self):
        assert _is_unsafe_archive_path("C:/Users/file") is True

    def test_backslash_dot_dot(self):
        assert _is_unsafe_archive_path("dir\\..\\secret") is True

    def test_just_dot_dot(self):
        assert _is_unsafe_archive_path("..") is True

    def test_dot_dot_slash(self):
        assert _is_unsafe_archive_path("../") is True

    def test_safe_with_dots_in_name(self):
        assert _is_unsafe_archive_path("file.v2.1.txt") is False

    def test_unc_path(self):
        assert _is_unsafe_archive_path("\\\\server\\share") is True


# ── _safe_path_under ────────────────────────────────────────────────────────

class TestSafePathUnder:
    def test_child_is_safe(self, tmp_path):
        child = tmp_path / "sub" / "file.txt"
        assert _safe_path_under(tmp_path, child) is True

    def test_sibling_is_unsafe(self, tmp_path):
        sibling = tmp_path.parent / "other"
        assert _safe_path_under(tmp_path, sibling) is False

    def test_root_itself(self, tmp_path):
        assert _safe_path_under(tmp_path, tmp_path) is True

    def test_parent_is_unsafe(self, tmp_path):
        assert _safe_path_under(tmp_path, tmp_path.parent) is False


# ── _validate_zip_entries ───────────────────────────────────────────────────

class TestValidateZipEntries:
    def test_safe_zip(self, tmp_path):
        zip_path = tmp_path / "safe.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("dir/file.txt", "hello")
        assert _validate_zip_entries(zip_path) is None

    def test_zip_with_traversal(self, tmp_path):
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../../etc/passwd", "hacked")
        result = _validate_zip_entries(zip_path)
        assert result is not None
        assert "unsafe path" in result

    def test_zip_with_absolute_path(self, tmp_path):
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("/etc/passwd", "hacked")
        result = _validate_zip_entries(zip_path)
        assert result is not None

    def test_invalid_zip(self, tmp_path):
        bad_path = tmp_path / "bad.zip"
        bad_path.write_bytes(b"not a zip file")
        result = _validate_zip_entries(bad_path)
        assert result is not None
        assert "Not a valid zip" in result

    def test_zip_with_symlink_entry(self, tmp_path):
        zip_path = tmp_path / "symlink.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            info = zipfile.ZipInfo("link.txt")
            # Set symlink mode in external_attr
            info.external_attr = (0o120000 | 0o755) << 16
            zf.writestr(info, "/etc/passwd")
        result = _validate_zip_entries(zip_path)
        assert result is not None
        assert "symlink" in result


# ── _validate_tar_entries ───────────────────────────────────────────────────

class TestValidateTarEntries:
    def test_safe_tar(self, tmp_path):
        tar_path = tmp_path / "safe.tar"
        txt_file = tmp_path / "hello.txt"
        txt_file.write_text("hello")
        with tarfile.open(tar_path, "w") as tf:
            tf.add(txt_file, arcname="hello.txt")
        assert _validate_tar_entries(tar_path) is None

    def test_tar_with_traversal(self, tmp_path):
        tar_path = tmp_path / "evil.tar"
        txt_file = tmp_path / "hello.txt"
        txt_file.write_text("hello")
        with tarfile.open(tar_path, "w") as tf:
            info = tarfile.TarInfo(name="../../../etc/passwd")
            info.size = 5
            import io
            tf.addfile(info, io.BytesIO(b"hello"))
        result = _validate_tar_entries(tar_path)
        assert result is not None
        assert "unsafe path" in result

    def test_invalid_tar(self, tmp_path):
        bad_path = tmp_path / "bad.tar"
        bad_path.write_bytes(b"not a tar")
        result = _validate_tar_entries(bad_path)
        assert result is not None


# ── _scrub_extracted ────────────────────────────────────────────────────────

class TestScrubExtracted:
    def test_safe_files_kept(self, tmp_path):
        (tmp_path / "good.txt").write_text("ok")
        _scrub_extracted(tmp_path)
        assert (tmp_path / "good.txt").exists()

    def test_files_in_subdirs_kept(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").write_text("ok")
        _scrub_extracted(tmp_path)
        assert (sub / "file.txt").exists()


# ── get_archive_type ────────────────────────────────────────────────────────

class TestGetArchiveType:
    def test_zip(self):
        assert get_archive_type(Path("file.zip")) == "zip"

    def test_tar(self):
        assert get_archive_type(Path("file.tar")) == "tar"

    def test_tar_gz(self):
        assert get_archive_type(Path("file.tar.gz")) == "tar"

    def test_tgz(self):
        assert get_archive_type(Path("file.tgz")) == "tar"

    def test_tar_bz2(self):
        assert get_archive_type(Path("file.tar.bz2")) == "tar"

    def test_tar_xz(self):
        assert get_archive_type(Path("file.tar.xz")) == "tar"

    def test_tbz2(self):
        assert get_archive_type(Path("file.tbz2")) == "tar"

    def test_txz(self):
        assert get_archive_type(Path("file.txz")) == "tar"

    def test_unknown(self):
        assert get_archive_type(Path("file.txt")) is None

    def test_case_insensitive(self):
        assert get_archive_type(Path("file.ZIP")) == "zip"

    def test_tar_gz_uppercase(self):
        assert get_archive_type(Path("file.TAR.GZ")) == "tar"


# ── smart_extract ───────────────────────────────────────────────────────────

class TestSmartExtract:
    def test_collapses_single_folder(self, tmp_path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        wrapper = temp_dir / "wrapper"
        wrapper.mkdir()
        (wrapper / "file.txt").write_text("content")

        dest = tmp_path / "dest"
        dest.mkdir()

        result = smart_extract(temp_dir, dest, use_smart_extract=True)
        assert len(result) == 1
        assert (dest / "file.txt").exists()

    def test_no_collapse_when_multiple_items(self, tmp_path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        (temp_dir / "file1.txt").write_text("a")
        (temp_dir / "file2.txt").write_text("b")

        dest = tmp_path / "dest"
        dest.mkdir()

        result = smart_extract(temp_dir, dest, use_smart_extract=True)
        assert len(result) == 2

    def test_no_collapse_when_disabled(self, tmp_path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        wrapper = temp_dir / "wrapper"
        wrapper.mkdir()
        (wrapper / "file.txt").write_text("content")

        dest = tmp_path / "dest"
        dest.mkdir()

        result = smart_extract(temp_dir, dest, use_smart_extract=False)
        assert len(result) == 1
        assert (dest / "wrapper").exists()

    def test_conflict_resolution(self, tmp_path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        (temp_dir / "file.txt").write_text("new")

        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "file.txt").write_text("existing")

        result = smart_extract(temp_dir, dest, use_smart_extract=True)
        assert len(result) == 1
        # Should have created file_1.txt or similar
        assert result[0].exists()


# ── extract_zip ─────────────────────────────────────────────────────────────

class TestExtractZip:
    def test_basic_extract(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("hello.txt", "hello world")

        dest = tmp_path / "output"
        dest.mkdir()

        result = extract_zip(zip_path, dest)
        assert result is not None
        assert any(p.name == "hello.txt" for p in result)

    def test_nested_files(self, tmp_path):
        zip_path = tmp_path / "nested.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("dir/file1.txt", "a")
            zf.writestr("dir/file2.txt", "b")

        dest = tmp_path / "output"
        dest.mkdir()

        result = extract_zip(zip_path, dest)
        assert result is not None

    def test_rejects_traversal(self, tmp_path):
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../../etc/passwd", "hacked")

        dest = tmp_path / "output"
        dest.mkdir()

        result = extract_zip(zip_path, dest)
        assert result is None


# ── extract_tar ─────────────────────────────────────────────────────────────

class TestExtractTar:
    def test_basic_extract(self, tmp_path):
        tar_path = tmp_path / "test.tar"
        txt = tmp_path / "hello.txt"
        txt.write_text("hello")

        with tarfile.open(tar_path, "w") as tf:
            tf.add(txt, arcname="hello.txt")

        dest = tmp_path / "output"
        dest.mkdir()

        result = extract_tar(tar_path, dest)
        assert result is not None
        assert any(p.name == "hello.txt" for p in result)

    def test_tar_gz_extract(self, tmp_path):
        tar_path = tmp_path / "test.tar.gz"
        txt = tmp_path / "hello.txt"
        txt.write_text("hello")

        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(txt, arcname="hello.txt")

        dest = tmp_path / "output"
        dest.mkdir()

        result = extract_tar(tar_path, dest)
        assert result is not None


# ── extract_archive (dispatcher) ────────────────────────────────────────────

class TestExtractArchive:
    def test_dispatches_zip(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file.txt", "data")

        dest = tmp_path / "out"
        dest.mkdir()

        result = extract_archive(zip_path, dest)
        assert result is not None

    def test_dispatches_tar(self, tmp_path):
        tar_path = tmp_path / "test.tar"
        txt = tmp_path / "f.txt"
        txt.write_text("hi")
        with tarfile.open(tar_path, "w") as tf:
            tf.add(txt, arcname="f.txt")

        dest = tmp_path / "out"
        dest.mkdir()

        result = extract_archive(tar_path, dest)
        assert result is not None

    def test_unknown_type_returns_none(self, tmp_path):
        txt = tmp_path / "file.txt"
        txt.write_text("not an archive")

        dest = tmp_path / "out"
        dest.mkdir()

        result = extract_archive(txt, dest)
        assert result is None

    def test_explicit_type_override(self, tmp_path):
        zip_path = tmp_path / "disguised.dat"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("inner.txt", "hidden")

        dest = tmp_path / "out"
        dest.mkdir()

        result = extract_archive(zip_path, dest, archive_type="zip")
        assert result is not None
