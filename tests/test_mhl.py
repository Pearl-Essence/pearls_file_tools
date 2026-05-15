"""Comprehensive tests for core/mhl.py."""

import xml.etree.ElementTree as ET
import pytest
from pathlib import Path
from core.mhl import write_mhl_with_hashes


class TestWriteMhlWithHashes:
    def test_creates_mhl_file(self, tmp_path):
        entries = [
            {"filename": "clip01.mov", "size": 1000, "md5": "abc123"},
            {"filename": "clip02.mov", "size": 2000, "md5": "def456"},
        ]
        result = write_mhl_with_hashes(entries, tmp_path)
        assert result.exists()
        assert result.suffix == ".mhl"
        assert result.name.startswith("pearl_ingest_")

    def test_valid_xml(self, tmp_path):
        entries = [{"filename": "clip.mov", "size": 100, "md5": "abc"}]
        result = write_mhl_with_hashes(entries, tmp_path)
        content = result.read_bytes()
        root = ET.fromstring(content)
        assert root.tag == "hashlist"
        assert root.attrib["version"] == "1.1"

    def test_contains_entries(self, tmp_path):
        entries = [
            {"filename": "a.mov", "size": 100, "md5": "hash_a"},
            {"filename": "b.mov", "size": 200, "md5": "hash_b"},
        ]
        result = write_mhl_with_hashes(entries, tmp_path)
        root = ET.fromstring(result.read_bytes())
        hashes = root.findall("hash")
        assert len(hashes) == 2
        files = [h.find("file").text for h in hashes]
        assert "a.mov" in files
        assert "b.mov" in files

    def test_md5_stored(self, tmp_path):
        entries = [{"filename": "clip.mov", "size": 100, "md5": "deadbeef"}]
        result = write_mhl_with_hashes(entries, tmp_path)
        root = ET.fromstring(result.read_bytes())
        md5_elem = root.find(".//md5")
        assert md5_elem.text == "deadbeef"

    def test_size_stored(self, tmp_path):
        entries = [{"filename": "clip.mov", "size": 42, "md5": "abc"}]
        result = write_mhl_with_hashes(entries, tmp_path)
        root = ET.fromstring(result.read_bytes())
        size_elem = root.find(".//size")
        assert size_elem.text == "42"

    def test_creatorinfo(self, tmp_path):
        entries = [{"filename": "clip.mov", "size": 0, "md5": ""}]
        result = write_mhl_with_hashes(entries, tmp_path)
        root = ET.fromstring(result.read_bytes())
        creator = root.find("creatorinfo")
        assert creator.text == "Pearl Post Suite"

    def test_empty_entries(self, tmp_path):
        result = write_mhl_with_hashes([], tmp_path)
        assert result.exists()
        root = ET.fromstring(result.read_bytes())
        assert len(root.findall("hash")) == 0

    def test_creates_dest_dir(self, tmp_path):
        dest = tmp_path / "new" / "path"
        entries = [{"filename": "clip.mov", "size": 0, "md5": ""}]
        result = write_mhl_with_hashes(entries, dest)
        assert result.exists()

    def test_missing_dict_keys_use_defaults(self, tmp_path):
        entries = [{}]
        result = write_mhl_with_hashes(entries, tmp_path)
        root = ET.fromstring(result.read_bytes())
        file_elem = root.find(".//file")
        # ElementTree represents empty string as None for .text
        assert file_elem.text is None or file_elem.text == ""
        size_elem = root.find(".//size")
        assert size_elem.text == "0"
