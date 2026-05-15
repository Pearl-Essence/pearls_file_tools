"""Comprehensive tests for core/pattern_matching.py."""

import pytest
from core.pattern_matching import (
    detect_dominant_delimiter,
    PRESET_STANDARD,
    PRESET_AE_RENDER,
    SequenceGroup,
    detect_image_sequences,
    get_group_name,
    find_best_group,
    detect_common_prefixes,
    group_files_by_pattern,
    match_prefix,
    detect_common_suffixes,
    match_suffix,
    get_group_name_ae,
    group_files_by_preset,
)


# ── detect_dominant_delimiter ───────────────────────────────────────────────

class TestDetectDominantDelimiter:
    def test_underscore_dominant(self):
        files = ["HERO_clip_01.mov", "HERO_clip_02.mov", "other.txt"]
        assert detect_dominant_delimiter(files) == "_"

    def test_dash_dominant(self):
        files = ["HERO-clip-01.mov", "HERO-clip-02.mov"]
        assert detect_dominant_delimiter(files) == "-"

    def test_space_dominant(self):
        files = ["HERO clip 01.mov", "HERO clip 02.mov"]
        assert detect_dominant_delimiter(files) == " "

    def test_empty_list(self):
        assert detect_dominant_delimiter([]) == "_"

    def test_no_delimiters(self):
        files = ["clip.mov", "shot.mp4"]
        assert detect_dominant_delimiter(files) == "_"

    def test_tie_breaks_to_underscore(self):
        # One file has _, one has - → both count = 1, _ wins by priority
        files = ["A_B.mov", "C-D.mov"]
        assert detect_dominant_delimiter(files) == "_"

    def test_ignores_extension_dot(self):
        # Dot in extension shouldn't count; only stem matters
        files = ["clip.mov", "shot.mp4"]
        result = detect_dominant_delimiter(files)
        assert result == "_"  # fallback default

    def test_dot_in_stem_counts(self):
        files = ["clip.001.exr", "clip.002.exr", "clip.003.exr"]
        assert detect_dominant_delimiter(files) == "."

    def test_empty_strings_skipped(self):
        files = ["", "", "HERO_clip.mov"]
        assert detect_dominant_delimiter(files) == "_"


# ── SequenceGroup ───────────────────────────────────────────────────────────

class TestSequenceGroup:
    def test_label_basic(self):
        sg = SequenceGroup(base="HERO", extension=".exr",
                           frames=[1, 2, 3], missing=[], padding=4,
                           files=["HERO_0001.exr", "HERO_0002.exr", "HERO_0003.exr"])
        label = sg.label
        assert "HERO" in label
        assert "0001" in label
        assert "0003" in label
        assert "3 frames" in label

    def test_label_with_missing(self):
        sg = SequenceGroup(base="SHOT", extension=".dpx",
                           frames=[1, 3, 5], missing=[2, 4], padding=4,
                           files=["f1", "f3", "f5"])
        assert "2 missing" in sg.label

    def test_label_empty_frames(self):
        sg = SequenceGroup(base="EMPTY", extension=".exr",
                           frames=[], missing=[], padding=4, files=[])
        assert sg.label == "EMPTY"

    def test_label_no_base(self):
        sg = SequenceGroup(base="", extension=".png",
                           frames=[0, 1, 2], missing=[], padding=3,
                           files=["000.png", "001.png", "002.png"])
        assert "[000" in sg.label


# ── detect_image_sequences ──────────────────────────────────────────────────

class TestDetectImageSequences:
    def test_basic_sequence(self):
        files = [f"HERO_Explosion_{str(i).zfill(4)}.exr" for i in range(1, 10)]
        seqs = detect_image_sequences(files)
        assert len(seqs) == 1
        key = list(seqs.keys())[0]
        assert seqs[key].base == "HERO_Explosion"
        assert seqs[key].frames == list(range(1, 10))
        assert seqs[key].missing == []

    def test_missing_frames_detected(self):
        files = ["SHOT_0001.exr", "SHOT_0002.exr", "SHOT_0005.exr"]
        seqs = detect_image_sequences(files)
        key = list(seqs.keys())[0]
        assert 3 in seqs[key].missing
        assert 4 in seqs[key].missing

    def test_pure_numeric_stem(self):
        files = [f"{str(i).zfill(3)}.png" for i in range(10)]
        seqs = detect_image_sequences(files)
        assert len(seqs) == 1
        sg = list(seqs.values())[0]
        assert sg.base == ""
        assert len(sg.frames) == 10

    def test_below_min_frames(self):
        files = ["HERO_0001.exr", "HERO_0002.exr"]
        seqs = detect_image_sequences(files, min_frames=3)
        assert len(seqs) == 0

    def test_min_frames_2(self):
        files = ["HERO_0001.exr", "HERO_0002.exr"]
        seqs = detect_image_sequences(files, min_frames=2)
        assert len(seqs) == 1

    def test_multiple_sequences(self):
        files = [f"A_{str(i).zfill(4)}.exr" for i in range(1, 5)]
        files += [f"B_{str(i).zfill(4)}.dpx" for i in range(1, 5)]
        seqs = detect_image_sequences(files)
        assert len(seqs) == 2

    def test_dot_delimiter(self):
        files = [f"shot.{str(i).zfill(4)}.dpx" for i in range(1, 5)]
        seqs = detect_image_sequences(files)
        assert len(seqs) == 1

    def test_dash_delimiter(self):
        files = [f"clip-{str(i).zfill(4)}.exr" for i in range(1, 5)]
        seqs = detect_image_sequences(files)
        assert len(seqs) == 1


# ── get_group_name ──────────────────────────────────────────────────────────

class TestGetGroupName:
    def test_two_parts(self):
        name, conf = get_group_name("HERO_clip_01.mov", delimiter="_")
        assert name == "HERO_clip"
        assert conf == 1.0

    def test_single_word(self):
        name, conf = get_group_name("clip.mov", delimiter="_")
        assert name == "clip"
        assert conf == 0.5

    def test_custom_delimiter(self):
        name, conf = get_group_name("HERO-clip-01.mov", delimiter="-")
        assert name == "HERO-clip"
        assert conf == 1.0

    def test_default_delimiter_is_underscore(self):
        name, conf = get_group_name("HERO_clip.mov")
        assert name == "HERO_clip"

    def test_no_delimiter_in_stem(self):
        name, conf = get_group_name("singleword.mov", delimiter="-")
        assert conf == 0.5


# ── find_best_group ─────────────────────────────────────────────────────────

class TestFindBestGroup:
    def test_exact_prefix_match(self):
        group, score = find_best_group("HERO_clip_01.mov", ["HERO_clip"])
        assert group == "HERO_clip"
        assert score >= 0.8

    def test_no_match(self):
        group, score = find_best_group("unrelated.mov", ["HERO_clip"])
        assert group is None

    def test_fuzzy_match(self):
        group, score = find_best_group("HERO_clipA.mov", ["HERO_clip"])
        assert group == "HERO_clip"
        assert score > 0.6

    def test_empty_groups(self):
        group, score = find_best_group("file.mov", [])
        assert group is None
        assert score == 0.0


# ── detect_common_prefixes ──────────────────────────────────────────────────

class TestDetectCommonPrefixes:
    def test_common_prefix(self):
        files = ["HERO_clip1.mov", "HERO_clip2.mov", "OTHER.mov"]
        result = detect_common_prefixes(files, delimiter="_")
        assert "HERO_" in result
        assert result["HERO_"] == 2

    def test_single_occurrence_excluded(self):
        files = ["HERO_clip.mov", "OTHER_clip.mov"]
        result = detect_common_prefixes(files, delimiter="_")
        assert all(v >= 2 for v in result.values())

    def test_auto_detect_delimiter(self):
        files = ["HERO_a.mov", "HERO_b.mov", "HERO_c.mov"]
        result = detect_common_prefixes(files)
        assert "HERO_" in result


# ── detect_common_suffixes ──────────────────────────────────────────────────

class TestDetectCommonSuffixes:
    def test_common_suffix(self):
        files = ["clip_DRAFT.mov", "edit_DRAFT.mov", "other.mov"]
        result = detect_common_suffixes(files, delimiter="_")
        assert "_DRAFT" in result
        assert result["_DRAFT"] == 2

    def test_single_occurrence_excluded(self):
        files = ["clip_DRAFT.mov", "edit_FINAL.mov"]
        result = detect_common_suffixes(files, delimiter="_")
        assert all(v >= 2 for v in result.values())


# ── match_prefix ────────────────────────────────────────────────────────────

class TestMatchPrefix:
    def test_match(self):
        assert match_prefix("HERO_clip.mov", ["HERO_", "SHOT_"]) == "HERO_"

    def test_no_match(self):
        assert match_prefix("OTHER_clip.mov", ["HERO_", "SHOT_"]) is None

    def test_case_sensitive(self):
        assert match_prefix("hero_clip.mov", ["HERO_"]) is None

    def test_empty_prefixes(self):
        assert match_prefix("file.mov", []) is None


# ── match_suffix ────────────────────────────────────────────────────────────

class TestMatchSuffix:
    def test_match(self):
        assert match_suffix("clip_DRAFT.mov", ["_DRAFT", "_FINAL"]) == "_DRAFT"

    def test_case_insensitive(self):
        assert match_suffix("clip_draft.mov", ["_DRAFT"]) == "_DRAFT"

    def test_no_match(self):
        assert match_suffix("clip.mov", ["_DRAFT"]) is None

    def test_empty_suffixes(self):
        assert match_suffix("file.mov", []) is None


# ── group_files_by_pattern ──────────────────────────────────────────────────

class TestGroupFilesByPattern:
    def test_groups_by_delimiter(self):
        files = ["HERO_clip_01.mov", "HERO_clip_02.mov",
                 "SHOT_wide_01.mov", "SHOT_wide_02.mov",
                 "random.mov"]
        groups, unsorted = group_files_by_pattern(files, delimiter="_")
        assert "HERO_clip" in groups
        assert "SHOT_wide" in groups
        assert "random.mov" in unsorted

    def test_single_file_groups_go_unsorted(self):
        files = ["A_1.mov", "A_2.mov", "B_1.mov"]
        groups, unsorted = group_files_by_pattern(files, delimiter="_")
        # B has only one file → goes to unsorted
        assert "B_1" not in groups
        assert "B_1.mov" in unsorted

    def test_empty_input(self):
        groups, unsorted = group_files_by_pattern([])
        assert groups == {}
        assert unsorted == []


# ── get_group_name_ae ───────────────────────────────────────────────────────

class TestGetGroupNameAE:
    def test_ae_render(self):
        name, conf = get_group_name_ae("Hero_Explosion_0001.exr")
        assert name == "Hero_Explosion"
        assert conf == 1.0

    def test_no_frame_number(self):
        name, conf = get_group_name_ae("clip.mov")
        assert conf == 0.5  # falls back to get_group_name

    def test_8_digit_frame(self):
        name, conf = get_group_name_ae("VFX_Shot_00000001.exr")
        assert name == "VFX_Shot"
        assert conf == 1.0


# ── group_files_by_preset ───────────────────────────────────────────────────

class TestGroupFilesByPreset:
    def test_standard_preset(self):
        files = ["HERO_clip_01.mov", "HERO_clip_02.mov",
                 "SHOT_wide_01.mov", "SHOT_wide_02.mov"]
        groups, unsorted = group_files_by_preset(files, PRESET_STANDARD, delimiter="_")
        assert "HERO_clip" in groups
        assert "SHOT_wide" in groups

    def test_ae_preset(self):
        files = ["Hero_Explosion_0001.exr", "Hero_Explosion_0002.exr",
                 "BG_Sky_0001.exr", "BG_Sky_0002.exr"]
        groups, unsorted = group_files_by_preset(files, PRESET_AE_RENDER)
        assert "Hero_Explosion" in groups
        assert "BG_Sky" in groups

    def test_ae_single_file_goes_unsorted(self):
        files = ["Hero_Explosion_0001.exr", "Hero_Explosion_0002.exr",
                 "Lone_Shot_0001.exr"]
        groups, unsorted = group_files_by_preset(files, PRESET_AE_RENDER)
        assert "Lone_Shot_0001.exr" in unsorted
