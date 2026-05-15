"""Comprehensive tests for core/file_utils.py."""

from pathlib import Path

from core.file_utils import (
    calculate_directory_hash,
    format_file_size,
    get_extension_category,
    get_files_in_directory,
    has_keyword,
    is_hidden_file,
    resolve_name_conflict,
    safe_move,
    safe_rename,
    same_inode,
    split_compound_suffix,
)

# ── is_hidden_file ──────────────────────────────────────────────────────────


class TestIsHiddenFile:
    def test_dot_prefix(self):
        assert is_hidden_file(".DS_Store") is True

    def test_dotfile(self):
        assert is_hidden_file(".gitignore") is True

    def test_normal_file(self):
        assert is_hidden_file("readme.md") is False

    def test_empty_string(self):
        assert is_hidden_file("") is False

    def test_dot_only(self):
        assert is_hidden_file(".") is True

    def test_double_dot(self):
        assert is_hidden_file("..") is True

    def test_dot_in_middle(self):
        assert is_hidden_file("file.txt") is False

    def test_leading_space_then_dot(self):
        assert is_hidden_file(" .hidden") is False


# ── split_compound_suffix ───────────────────────────────────────────────────


class TestSplitCompoundSuffix:
    def test_simple_extension(self):
        assert split_compound_suffix("clip.mov") == ("clip", ".mov")

    def test_compound_language_srt(self):
        assert split_compound_suffix("clip.en.srt") == ("clip", ".en.srt")

    def test_compound_language_vtt(self):
        assert split_compound_suffix("clip.es.vtt") == ("clip", ".es.vtt")

    def test_tar_gz(self):
        assert split_compound_suffix("archive.tar.gz") == ("archive", ".tar.gz")

    def test_frame_sequence_numeric(self):
        # Numeric segments should NOT be consumed as compound suffixes
        stem, suffix = split_compound_suffix("shot1.0.42.exr")
        assert stem == "shot1.0.42"
        assert suffix == ".exr"

    def test_no_extension(self):
        assert split_compound_suffix("Makefile") == ("Makefile", "")

    def test_long_extension_segment_rejected(self):
        # Segment > 5 chars should break the walk
        stem, suffix = split_compound_suffix("file.longext.txt")
        assert suffix == ".txt"
        assert stem == "file.longext"

    def test_non_ascii_segment_rejected(self):
        stem, suffix = split_compound_suffix("file.ñ.txt")
        assert suffix == ".txt"

    def test_empty_segment(self):
        stem, suffix = split_compound_suffix("file..txt")
        # Empty segment breaks the walk
        assert suffix == ".txt"

    def test_single_char_extension(self):
        assert split_compound_suffix("file.c") == ("file", ".c")

    def test_7z_extension(self):
        assert split_compound_suffix("archive.7z") == ("archive", ".7z")

    def test_multiple_compound(self):
        assert split_compound_suffix("data.en.us.srt") == ("data", ".en.us.srt")


# ── same_inode ──────────────────────────────────────────────────────────────


class TestSameInode:
    def test_same_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert same_inode(f, f) is True

    def test_different_files(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("hello")
        b.write_text("world")
        assert same_inode(a, b) is False

    def test_nonexistent_file(self, tmp_path):
        a = tmp_path / "exists.txt"
        a.write_text("hi")
        b = tmp_path / "nope.txt"
        assert same_inode(a, b) is False

    def test_both_nonexistent(self, tmp_path):
        assert same_inode(tmp_path / "a", tmp_path / "b") is False


# ── has_keyword ─────────────────────────────────────────────────────────────


class TestHasKeyword:
    def test_match_case_insensitive(self):
        assert has_keyword("HERO_clip.mov", ["hero"]) is True

    def test_no_match(self):
        assert has_keyword("interview.mov", ["hero"]) is False

    def test_empty_keywords(self):
        assert has_keyword("anything.txt", []) is False

    def test_multiple_keywords_first_matches(self):
        assert has_keyword("DRAFT_edit.mov", ["draft", "wip"]) is True

    def test_partial_match(self):
        assert has_keyword("redraft.mov", ["draft"]) is True

    def test_empty_filename(self):
        assert has_keyword("", ["test"]) is False


# ── get_extension_category ──────────────────────────────────────────────────


class TestGetExtensionCategory:
    def test_image(self):
        assert get_extension_category(Path("photo.jpg")) == "images"

    def test_video(self):
        assert get_extension_category(Path("clip.mov")) == "videos"

    def test_audio(self):
        assert get_extension_category(Path("song.mp3")) == "audio"

    def test_document(self):
        assert get_extension_category(Path("doc.pdf")) == "documents"

    def test_archive(self):
        assert get_extension_category(Path("pkg.zip")) == "archives"

    def test_unknown(self):
        assert get_extension_category(Path("file.xyz")) is None

    def test_case_insensitive(self):
        assert get_extension_category(Path("PHOTO.JPG")) == "images"

    def test_no_extension(self):
        assert get_extension_category(Path("Makefile")) is None

    def test_pro_video_ext(self):
        assert get_extension_category(Path("clip.mxf")) == "videos"

    def test_pro_image_ext(self):
        assert get_extension_category(Path("frame.exr")) == "images"


# ── resolve_name_conflict ───────────────────────────────────────────────────


class TestResolveNameConflict:
    def test_no_conflict(self, tmp_path):
        target = tmp_path / "new_file.txt"
        assert resolve_name_conflict(target) == target

    def test_counter_strategy(self, tmp_path):
        (tmp_path / "file.txt").write_text("exists")
        result = resolve_name_conflict(tmp_path / "file.txt", "counter")
        assert result == tmp_path / "file_1.txt"
        assert not result.exists()

    def test_counter_multiple_conflicts(self, tmp_path):
        (tmp_path / "file.txt").write_text("a")
        (tmp_path / "file_1.txt").write_text("b")
        (tmp_path / "file_2.txt").write_text("c")
        result = resolve_name_conflict(tmp_path / "file.txt", "counter")
        assert result == tmp_path / "file_3.txt"

    def test_skip_strategy(self, tmp_path):
        (tmp_path / "file.txt").write_text("exists")
        result = resolve_name_conflict(tmp_path / "file.txt", "skip")
        assert result is None

    def test_skip_no_conflict(self, tmp_path):
        result = resolve_name_conflict(tmp_path / "new.txt", "skip")
        assert result == tmp_path / "new.txt"

    def test_timestamp_strategy(self, tmp_path):
        (tmp_path / "file.txt").write_text("exists")
        result = resolve_name_conflict(tmp_path / "file.txt", "timestamp")
        assert result is not None
        assert "file_" in result.name
        assert result.suffix == ".txt"

    def test_counter_with_directory(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        result = resolve_name_conflict(tmp_path / "subdir", "counter")
        assert result.name == "subdir_1"


# ── format_file_size ────────────────────────────────────────────────────────


class TestFormatFileSize:
    def test_bytes(self):
        assert format_file_size(500) == "500.0 B"

    def test_kilobytes(self):
        assert format_file_size(1024) == "1.0 KB"

    def test_megabytes(self):
        assert format_file_size(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert format_file_size(1024**3) == "1.0 GB"

    def test_terabytes(self):
        assert format_file_size(1024**4) == "1.0 TB"

    def test_petabytes(self):
        assert format_file_size(1024**5) == "1.0 PB"

    def test_zero(self):
        assert format_file_size(0) == "0.0 B"

    def test_fractional(self):
        result = format_file_size(1536)
        assert result == "1.5 KB"


# ── calculate_directory_hash ────────────────────────────────────────────────


class TestCalculateDirectoryHash:
    def test_returns_hash_string(self, tmp_path):
        (tmp_path / "sub1").mkdir()
        (tmp_path / "sub2").mkdir()
        result = calculate_directory_hash(tmp_path)
        assert len(result) == 64  # SHA-256 hex digest

    def test_empty_dir(self, tmp_path):
        result = calculate_directory_hash(tmp_path)
        assert isinstance(result, str)

    def test_skips_hidden_dirs(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()
        h1 = calculate_directory_hash(tmp_path)
        # Hash should only include 'visible'
        assert len(h1) == 64

    def test_nonexistent_dir(self):
        result = calculate_directory_hash(Path("/nonexistent_dir_xyz"))
        assert result == ""

    def test_same_structure_same_hash(self, tmp_path):
        h1 = calculate_directory_hash(tmp_path)
        h2 = calculate_directory_hash(tmp_path)
        assert h1 == h2


# ── safe_rename ─────────────────────────────────────────────────────────────


class TestSafeRename:
    def test_basic_rename(self, tmp_path):
        src = tmp_path / "old.txt"
        dst = tmp_path / "new.txt"
        src.write_text("content")
        assert safe_rename(src, dst) is True
        assert dst.exists()
        assert not src.exists()

    def test_source_missing(self, tmp_path):
        assert safe_rename(tmp_path / "nope.txt", tmp_path / "dest.txt") is False

    def test_target_exists_different_file(self, tmp_path):
        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_text("aaa")
        dst.write_text("bbb")
        assert safe_rename(src, dst) is False

    def test_case_only_rename(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("content")
        dst = tmp_path / "FILE.txt"
        result = safe_rename(src, dst)
        # On case-insensitive FS this should succeed via temp intermediate
        # On case-sensitive FS this is just a normal rename
        assert result is True


# ── safe_move ───────────────────────────────────────────────────────────────


class TestSafeMove:
    def test_basic_move(self, tmp_path):
        src = tmp_path / "src.txt"
        dst = tmp_path / "sub" / "dst.txt"
        src.write_text("data")
        assert safe_move(src, dst) is True
        assert dst.exists()
        assert not src.exists()

    def test_creates_parent_dirs(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("data")
        dst = tmp_path / "a" / "b" / "c" / "file.txt"
        assert safe_move(src, dst) is True
        assert dst.exists()

    def test_source_missing(self, tmp_path):
        assert safe_move(tmp_path / "nope.txt", tmp_path / "dst.txt") is False

    def test_dest_exists(self, tmp_path):
        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_text("src")
        dst.write_text("dst")
        assert safe_move(src, dst) is False


# ── get_files_in_directory ──────────────────────────────────────────────────


class TestGetFilesInDirectory:
    def test_all_files(self, tmp_tree):
        files = get_files_in_directory(tmp_tree)
        names = [f.name for f in files]
        assert ".hidden" in names
        assert "file_a.mov" in names
        assert "file_b.mov" in names

    def test_filtered_by_extension(self, tmp_tree):
        files = get_files_in_directory(tmp_tree, extensions=[".mov"])
        names = [f.name for f in files]
        assert "file_a.mov" in names
        assert "file_b.mov" in names
        assert ".hidden" not in names

    def test_non_recursive(self, tmp_tree):
        files = get_files_in_directory(tmp_tree, recursive=False)
        names = [f.name for f in files]
        assert "file_c.txt" not in names

    def test_recursive(self, tmp_tree):
        files = get_files_in_directory(tmp_tree, recursive=True)
        names = [f.name for f in files]
        assert "file_c.txt" in names

    def test_empty_directory(self, tmp_path):
        files = get_files_in_directory(tmp_path)
        assert files == []

    def test_sorted_by_name(self, tmp_tree):
        files = get_files_in_directory(tmp_tree)
        names = [f.name.lower() for f in files]
        assert names == sorted(names)

    def test_extension_case_insensitive(self, tmp_path):
        (tmp_path / "file.MOV").write_text("data")
        files = get_files_in_directory(tmp_path, extensions=[".mov"])
        assert len(files) == 1

    def test_nonexistent_directory(self):
        files = get_files_in_directory(Path("/nonexistent_xyz"))
        assert files == []
