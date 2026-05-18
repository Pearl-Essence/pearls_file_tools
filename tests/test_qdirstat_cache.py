"""Comprehensive tests for core/qdirstat_cache.py."""

import gzip

import pytest

from core.qdirstat_cache import (
    _build_ext_to_cat,
    _parse_dir_line,
    _parse_file_line,
    parse_qdirstat_cache,
    write_qdirstat_cache,
)


class TestWriteQdirstatCache:
    def test_creates_gzip_file(self, tmp_path):
        data = {"__root__": {"images": 1000, "videos": 5000}}
        out = tmp_path / "test.cache.gz"
        write_qdirstat_cache(data, tmp_path, out)
        assert out.exists()
        # Verify it's valid gzip
        with gzip.open(out, "rt") as f:
            content = f.read()
        assert "[qdirstat 1.0 cache file]" in content

    def test_root_files(self, tmp_path):
        data = {"__root__": {"images": 1000}}
        out = tmp_path / "test.cache.gz"
        write_qdirstat_cache(data, tmp_path, out)
        with gzip.open(out, "rt") as f:
            content = f.read()
        assert f"D {tmp_path}" in content
        assert "images\t1000" in content

    def test_subfolder(self, tmp_path):
        data = {"subdir": {"videos": 5000}}
        out = tmp_path / "test.cache.gz"
        write_qdirstat_cache(data, tmp_path, out)
        with gzip.open(out, "rt") as f:
            content = f.read()
        assert "subdir" in content

    def test_skips_zero_size(self, tmp_path):
        data = {"__root__": {"images": 0, "videos": 100}}
        out = tmp_path / "test.cache.gz"
        write_qdirstat_cache(data, tmp_path, out)
        with gzip.open(out, "rt") as f:
            content = f.read()
        assert "images\t0" not in content
        assert "videos\t100" in content

    def test_empty_data(self, tmp_path):
        data = {}
        out = tmp_path / "test.cache.gz"
        write_qdirstat_cache(data, tmp_path, out)
        assert out.exists()


class TestParseQdirstatCache:
    def test_roundtrip(self, tmp_path):
        # write_qdirstat_cache writes category names as filenames (e.g. "images"),
        # but parse_qdirstat_cache categorizes by file extension. So the
        # category names without extensions map to "other" on re-parse.
        # We verify the structural roundtrip instead.
        original = {
            "__root__": {"images": 1000, "videos": 5000},
        }
        cache_path = tmp_path / "test.cache.gz"
        write_qdirstat_cache(original, tmp_path, cache_path)
        parsed = parse_qdirstat_cache(cache_path)
        assert "__root__" in parsed
        # Category names are extension-less → classified as "other"
        assert parsed["__root__"]["other"] == 6000

    def test_invalid_file(self, tmp_path):
        bad = tmp_path / "bad.cache.gz"
        with gzip.open(bad, "wt") as f:
            f.write("not a qdirstat file\n")
        with pytest.raises(ValueError, match="Not a valid"):
            parse_qdirstat_cache(bad)

    def test_empty_cache(self, tmp_path):
        cache = tmp_path / "empty.cache.gz"
        with gzip.open(cache, "wt") as f:
            f.write("[qdirstat 1.0 cache file]\n")
        parsed = parse_qdirstat_cache(cache)
        assert parsed == {}

    def test_categorizes_extensions(self, tmp_path):
        cache = tmp_path / "test.cache.gz"
        lines = [
            "[qdirstat 1.0 cache file]\n",
            f"D {tmp_path}\n",
            "F\tphoto.jpg\t1000\t0x60000000\t2\t1\n",
            "F\tclip.mov\t5000\t0x60000000\t10\t1\n",
        ]
        with gzip.open(cache, "wt") as f:
            f.writelines(lines)
        parsed = parse_qdirstat_cache(cache)
        assert "__root__" in parsed
        assert parsed["__root__"].get("images", 0) == 1000
        assert parsed["__root__"].get("videos", 0) == 5000

    def test_unknown_extension_goes_to_other(self, tmp_path):
        cache = tmp_path / "test.cache.gz"
        lines = [
            "[qdirstat 1.0 cache file]\n",
            f"D {tmp_path}\n",
            "F\tfile.xyz\t500\t0x60000000\t1\t1\n",
        ]
        with gzip.open(cache, "wt") as f:
            f.writelines(lines)
        parsed = parse_qdirstat_cache(cache)
        assert parsed["__root__"]["other"] == 500

    def test_multiple_directories(self, tmp_path):
        cache = tmp_path / "test.cache.gz"
        lines = [
            "[qdirstat 1.0 cache file]\n",
            f"D {tmp_path}\n",
            "F\ta.jpg\t100\t0x60000000\t1\t1\n",
            f"D {tmp_path / 'sub'}\n",
            "F\tb.mov\t200\t0x60000000\t1\t1\n",
        ]
        with gzip.open(cache, "wt") as f:
            f.writelines(lines)
        parsed = parse_qdirstat_cache(cache)
        assert "__root__" in parsed
        assert "sub" in parsed


# ── _build_ext_to_cat ──────────────────────────────────────────────────────


class TestBuildExtToCat:
    def test_returns_dict(self):
        result = _build_ext_to_cat()
        assert isinstance(result, dict)

    def test_maps_known_extensions(self):
        result = _build_ext_to_cat()
        assert result.get(".jpg") == "images"
        assert result.get(".mov") == "videos"
        assert result.get(".mp3") == "audio"
        assert result.get(".pdf") == "documents"
        assert result.get(".zip") == "archives"

    def test_keys_are_lowercase(self):
        result = _build_ext_to_cat()
        for key in result:
            assert key == key.lower()

    def test_values_are_category_strings(self):
        result = _build_ext_to_cat()
        expected_cats = {"images", "videos", "audio", "documents", "archives"}
        for val in result.values():
            assert val in expected_cats

    def test_no_empty_keys(self):
        result = _build_ext_to_cat()
        assert "" not in result


# ── _parse_dir_line ────────────────────────────────────────────────────────


class TestParseDirLine:
    def test_first_dir_returns_root(self):
        folder, root = _parse_dir_line("/some/path", None)
        assert folder == "__root__"
        assert root == "/some/path"

    def test_subsequent_dir_relative(self):
        folder, root = _parse_dir_line("/some/path/sub", "/some/path")
        assert folder == "sub"
        assert root == "/some/path"

    def test_same_dir_as_root(self):
        folder, root = _parse_dir_line("/some/path", "/some/path")
        assert folder == "__root__"
        assert root == "/some/path"

    def test_nested_subdir(self):
        folder, root = _parse_dir_line("/root/a/b/c", "/root")
        import os

        expected = os.path.join("a", "b", "c")
        assert folder == expected

    def test_value_error_on_different_drives(self):
        # On POSIX relpath won't raise ValueError, but the function handles it
        # On Windows with different drives it would raise ValueError
        # On POSIX this just returns a relative path with ".."
        folder, root = _parse_dir_line("/other/path", "/some/root")
        assert isinstance(folder, str)
        assert root == "/some/root"


# ── _parse_file_line ───────────────────────────────────────────────────────


class TestParseFileLine:
    def test_valid_file_line(self):
        ext_to_cat = {".jpg": "images", ".mov": "videos"}
        data = {}
        parts = ["F", "photo.jpg", "1000", "0x60000000", "2", "1"]
        _parse_file_line(parts, "__root__", ext_to_cat, data)
        assert data["__root__"]["images"] == 1000

    def test_accumulates_sizes(self):
        ext_to_cat = {".jpg": "images"}
        data = {"__root__": {"images": 500}}
        parts = ["F", "photo2.jpg", "300", "0x60000000", "1", "1"]
        _parse_file_line(parts, "__root__", ext_to_cat, data)
        assert data["__root__"]["images"] == 800

    def test_unknown_extension_goes_to_other(self):
        ext_to_cat = {".jpg": "images"}
        data = {}
        parts = ["F", "file.xyz", "100", "0x60000000", "1", "1"]
        _parse_file_line(parts, "sub", ext_to_cat, data)
        assert data["sub"]["other"] == 100

    def test_too_few_parts_ignored(self):
        ext_to_cat = {}
        data = {}
        parts = ["F", "name.txt"]  # missing size
        _parse_file_line(parts, "__root__", ext_to_cat, data)
        assert data == {}

    def test_invalid_size_ignored(self):
        ext_to_cat = {}
        data = {}
        parts = ["F", "name.txt", "not_a_number", "0x60000000", "1", "1"]
        _parse_file_line(parts, "__root__", ext_to_cat, data)
        assert data == {}

    def test_no_extension(self):
        ext_to_cat = {".jpg": "images"}
        data = {}
        parts = ["F", "Makefile", "200", "0x60000000", "1", "1"]
        _parse_file_line(parts, "__root__", ext_to_cat, data)
        assert data["__root__"]["other"] == 200
