"""Comprehensive tests for core/qdirstat_cache.py."""

import gzip

import pytest

from core.qdirstat_cache import (
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
