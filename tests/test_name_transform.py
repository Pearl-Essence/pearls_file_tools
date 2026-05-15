"""Comprehensive tests for core/name_transform.py."""

from core.name_transform import (
    DEFAULT_TEMPLATE,
    ProductionTemplate,
    add_prefix,
    add_suffix,
    apply_case_transform,
    bump_version,
    detect_version,
    generate_new_filename,
    generate_sequential_filenames,
    is_valid_filename,
    move_prefix_to_suffix,
    move_suffix_to_prefix,
    rename_file,
    replace_prefix,
    replace_suffix,
)

# ── ProductionTemplate ──────────────────────────────────────────────────────

class TestProductionTemplate:
    def test_compose_all_tokens(self):
        t = ProductionTemplate(name="Test")
        result = t.compose({"PROJECT": "HERO", "EP": "01", "SHOT": "010", "DESC": "wide", "VER": "v01"})
        assert result == "HERO_01_010_wide_v01"

    def test_compose_skips_empty_tokens(self):
        t = ProductionTemplate(name="Test")
        result = t.compose({"PROJECT": "HERO", "EP": "", "SHOT": "010", "DESC": "", "VER": "v01"})
        assert result == "HERO_010_v01"

    def test_compose_custom_separator(self):
        t = ProductionTemplate(name="Test", separator="-")
        result = t.compose({"PROJECT": "HERO", "EP": "01"})
        assert result == "HERO-01"

    def test_compose_strips_whitespace(self):
        t = ProductionTemplate(name="Test", tokens=["A", "B"])
        result = t.compose({"A": " HERO ", "B": " v01 "})
        assert result == "HERO_v01"

    def test_to_dict_from_dict_roundtrip(self):
        t = ProductionTemplate(name="Custom", tokens=["A", "B"], separator="-",
                               version_format="v{:03d}", episode_format="E{:02d}")
        d = t.to_dict()
        t2 = ProductionTemplate.from_dict(d)
        assert t2.name == t.name
        assert t2.tokens == t.tokens
        assert t2.separator == t.separator
        assert t2.version_format == t.version_format

    def test_from_dict_defaults(self):
        t = ProductionTemplate.from_dict({})
        assert t.name == "Unnamed"
        assert t.separator == "_"

    def test_default_template(self):
        assert DEFAULT_TEMPLATE.name == "Studio Default"
        assert DEFAULT_TEMPLATE.separator == "_"


# ── apply_case_transform ────────────────────────────────────────────────────

class TestApplyCaseTransform:
    def test_upper(self):
        assert apply_case_transform("hello world", "upper") == "HELLO WORLD"

    def test_lower(self):
        assert apply_case_transform("HELLO WORLD", "lower") == "hello world"

    def test_title(self):
        assert apply_case_transform("hello world", "title") == "Hello World"

    def test_none(self):
        assert apply_case_transform("MiXeD", "none") == "MiXeD"

    def test_unknown_type(self):
        assert apply_case_transform("text", "bogus") == "text"

    def test_empty_string(self):
        assert apply_case_transform("", "upper") == ""


# ── add_prefix ──────────────────────────────────────────────────────────────

class TestAddPrefix:
    def test_basic(self):
        assert add_prefix("clip.mov", "HERO_") == "HERO_clip.mov"

    def test_empty_prefix(self):
        assert add_prefix("clip.mov", "") == "clip.mov"

    def test_no_extension(self):
        assert add_prefix("Makefile", "PRE_") == "PRE_Makefile"

    def test_compound_extension(self):
        assert add_prefix("data.tar.gz", "backup_") == "backup_data.tar.gz"


# ── add_suffix ──────────────────────────────────────────────────────────────

class TestAddSuffix:
    def test_basic(self):
        assert add_suffix("clip.mov", "_v01") == "clip_v01.mov"

    def test_empty_suffix(self):
        assert add_suffix("clip.mov", "") == "clip.mov"

    def test_no_extension(self):
        assert add_suffix("Makefile", "_bak") == "Makefile_bak"


# ── move_suffix_to_prefix ───────────────────────────────────────────────────

class TestMoveSuffixToPrefix:
    def test_basic(self):
        result = move_suffix_to_prefix("interview_DRAFT.mov", "_DRAFT")
        assert result == "DRAFT_interview.mov"

    def test_no_match(self):
        result = move_suffix_to_prefix("interview.mov", "_DRAFT")
        assert result == "interview.mov"

    def test_case_insensitive_match(self):
        result = move_suffix_to_prefix("interview_draft.mov", "_DRAFT")
        assert result == "DRAFT_interview.mov"

    def test_dash_separator(self):
        result = move_suffix_to_prefix("interview-DRAFT.mov", "-DRAFT")
        assert result == "DRAFT-interview.mov"


# ── move_prefix_to_suffix ───────────────────────────────────────────────────

class TestMovePrefixToSuffix:
    def test_basic(self):
        result = move_prefix_to_suffix("DRAFT_interview.mov", "DRAFT_")
        assert result == "interviewDRAFT.mov"

    def test_no_match(self):
        result = move_prefix_to_suffix("interview.mov", "DRAFT_")
        assert result == "interview.mov"

    def test_empty_prefix(self):
        result = move_prefix_to_suffix("file.txt", "")
        assert result == "file.txt"


# ── rename_file ─────────────────────────────────────────────────────────────

class TestRenameFile:
    def test_basic(self):
        assert rename_file("old_clip.mov", "new_clip") == "new_clip.mov"

    def test_empty_new_name(self):
        assert rename_file("clip.mov", "") == "clip.mov"

    def test_preserves_extension(self):
        assert rename_file("data.tar.gz", "backup") == "backup.gz"


# ── replace_prefix ──────────────────────────────────────────────────────────

class TestReplacePrefix:
    def test_basic(self):
        assert replace_prefix("OLD_clip.mov", "OLD_", "NEW_") == "NEW_clip.mov"

    def test_no_match(self):
        assert replace_prefix("clip.mov", "OLD_", "NEW_") == "clip.mov"

    def test_empty_find(self):
        assert replace_prefix("clip.mov", "", "NEW_") == "clip.mov"

    def test_empty_replace(self):
        assert replace_prefix("OLD_clip.mov", "OLD_", "") == "clip.mov"


# ── replace_suffix ──────────────────────────────────────────────────────────

class TestReplaceSuffix:
    def test_basic(self):
        assert replace_suffix("clip_v01.mov", "_v01", "_v02") == "clip_v02.mov"

    def test_no_match(self):
        assert replace_suffix("clip.mov", "_v01", "_v02") == "clip.mov"

    def test_empty_find(self):
        assert replace_suffix("clip.mov", "", "_v02") == "clip.mov"

    def test_remove_suffix(self):
        assert replace_suffix("clip_DRAFT.mov", "_DRAFT", "") == "clip.mov"


# ── generate_new_filename ───────────────────────────────────────────────────

class TestGenerateNewFilename:
    def test_rename_to_takes_priority(self):
        result = generate_new_filename("clip.mov", prefix="X_", suffix="_Y", rename_to="NEW")
        assert result == "NEW.mov"

    def test_prefix_and_suffix(self):
        result = generate_new_filename("clip.mov", prefix="HERO_", suffix="_v01")
        assert result == "HERO_clip_v01.mov"

    def test_case_transform_applied(self):
        result = generate_new_filename("clip.mov", case_transform="upper")
        assert result == "CLIP.mov"

    def test_no_transforms(self):
        result = generate_new_filename("clip.mov")
        assert result == "clip.mov"

    def test_rename_to_with_whitespace(self):
        result = generate_new_filename("clip.mov", rename_to="  NEW  ")
        assert result == "NEW.mov"

    def test_rename_to_with_case(self):
        result = generate_new_filename("clip.mov", rename_to="new", case_transform="upper")
        assert result == "NEW.mov"


# ── generate_sequential_filenames ───────────────────────────────────────────

class TestGenerateSequentialFilenames:
    def test_basic(self):
        files = ["clip01.mov", "clip02.mov"]
        pairs = generate_sequential_filenames(files, "HERO")
        assert pairs == [("clip01.mov", "HERO_001.mov"), ("clip02.mov", "HERO_002.mov")]

    def test_custom_start_and_padding(self):
        pairs = generate_sequential_filenames(["a.mov"], "SHOT", start=10, padding=4)
        assert pairs == [("a.mov", "SHOT_0010.mov")]

    def test_custom_separator(self):
        pairs = generate_sequential_filenames(["a.mov"], "SHOT", separator="-")
        assert pairs == [("a.mov", "SHOT-001.mov")]

    def test_empty_list(self):
        assert generate_sequential_filenames([], "HERO") == []

    def test_preserves_extension(self):
        pairs = generate_sequential_filenames(["audio.wav"], "SFX")
        assert pairs[0][1] == "SFX_001.wav"


# ── VERSION_PATTERN and detect_version ──────────────────────────────────────

class TestDetectVersion:
    def test_underscore_lowercase(self):
        result = detect_version("HERO_v01.mov")
        assert result == ("HERO", 1, ".mov")

    def test_dash_lowercase(self):
        result = detect_version("HERO-v01.mov")
        assert result == ("HERO", 1, ".mov")

    def test_uppercase_V(self):
        result = detect_version("shot_V0001.mp4")
        assert result == ("shot", 1, ".mp4")

    def test_space_separator(self):
        result = detect_version("HERO V01.mov")
        assert result == ("HERO", 1, ".mov")

    def test_dot_separator(self):
        result = detect_version("HERO.v01.mov")
        assert result == ("HERO", 1, ".mov")

    def test_no_version(self):
        assert detect_version("clip.mov") is None

    def test_no_extension(self):
        assert detect_version("HERO_v01") is None

    def test_single_digit(self):
        result = detect_version("HERO_v1.mov")
        assert result == ("HERO", 1, ".mov")

    def test_many_digits(self):
        result = detect_version("shot_V0001.mp4")
        assert result[1] == 1


# ── bump_version ────────────────────────────────────────────────────────────

class TestBumpVersion:
    def test_basic_bump(self):
        assert bump_version("HERO_v01.mov") == "HERO_v02.mov"

    def test_preserves_padding(self):
        assert bump_version("shot_V0001.mp4") == "shot_V0002.mp4"

    def test_preserves_case(self):
        assert bump_version("HERO-V01.mov") == "HERO-V02.mov"

    def test_preserves_separator(self):
        assert bump_version("HERO.v01.mov") == "HERO.v02.mov"

    def test_no_version_returns_original(self):
        assert bump_version("clip.mov") == "clip.mov"

    def test_rollover_padding(self):
        assert bump_version("clip_v99.mov") == "clip_v100.mov"

    def test_rollover_preserves_min_pad(self):
        assert bump_version("clip_v999.mov") == "clip_v1000.mov"

    def test_single_digit(self):
        assert bump_version("HERO_v1.mov") == "HERO_v2.mov"

    def test_space_separator(self):
        assert bump_version("HERO v01.mov") == "HERO v02.mov"


# ── is_valid_filename ───────────────────────────────────────────────────────

class TestIsValidFilename:
    def test_valid(self):
        assert is_valid_filename("good_file.mov") is True

    def test_illegal_char_colon(self):
        assert is_valid_filename("file:name.mov") is False

    def test_illegal_char_pipe(self):
        assert is_valid_filename("file|name.mov") is False

    def test_illegal_char_question(self):
        assert is_valid_filename("file?.mov") is False

    def test_illegal_char_asterisk(self):
        assert is_valid_filename("file*.mov") is False

    def test_illegal_char_angle_brackets(self):
        assert is_valid_filename("<file>.mov") is False

    def test_illegal_char_quote(self):
        assert is_valid_filename('file"name.mov') is False

    def test_illegal_char_backslash(self):
        assert is_valid_filename("file\\name.mov") is False

    def test_reserved_CON(self):
        assert is_valid_filename("CON.txt") is False

    def test_reserved_PRN(self):
        assert is_valid_filename("PRN.txt") is False

    def test_reserved_AUX(self):
        assert is_valid_filename("AUX.txt") is False

    def test_reserved_NUL(self):
        assert is_valid_filename("NUL.txt") is False

    def test_reserved_COM1(self):
        assert is_valid_filename("COM1.txt") is False

    def test_reserved_LPT1(self):
        assert is_valid_filename("LPT1.txt") is False

    def test_reserved_case_insensitive(self):
        assert is_valid_filename("con.txt") is False

    def test_trailing_dot(self):
        assert is_valid_filename("file.") is False

    def test_trailing_space(self):
        assert is_valid_filename("file ") is False

    def test_empty_not_reserved(self):
        # Empty stem doesn't match any reserved name
        assert is_valid_filename(".txt") is True

    def test_similar_but_not_reserved(self):
        assert is_valid_filename("CONSOLE.txt") is True

    def test_reserved_name_as_part_of_filename(self):
        assert is_valid_filename("CON_backup.txt") is True
