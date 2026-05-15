"""Comprehensive tests for constants.py."""

from constants import (
    ALL_EXTENSION_CATEGORIES,
    ARCHIVE_EXTENSIONS,
    AUDIO_EXTENSIONS,
    CAPTION_EXTENSIONS,
    CASE_LOWER,
    CASE_NONE,
    CASE_TITLE,
    CASE_UPPER,
    CONFLICT_COUNTER,
    CONFLICT_SKIP,
    CONFLICT_TIMESTAMP,
    DEFAULT_GRID_COLUMNS,
    DEFAULT_THUMBNAIL_SIZE,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    OP_TYPE_COPY,
    OP_TYPE_EXTRACT,
    OP_TYPE_ORGANIZE,
    OP_TYPE_RENAME,
    PHOTO_KEYWORDS,
    SIDECAR_EXTENSIONS,
    THEME_DARK,
    THEME_LIGHT,
    VIDEO_EXTENSIONS,
)


class TestExtensionSets:
    def test_image_extensions_are_lowercase(self):
        for ext in IMAGE_EXTENSIONS:
            assert ext == ext.lower()
            assert ext.startswith(".")

    def test_video_extensions_are_lowercase(self):
        for ext in VIDEO_EXTENSIONS:
            assert ext == ext.lower()
            assert ext.startswith(".")

    def test_audio_extensions_are_lowercase(self):
        for ext in AUDIO_EXTENSIONS:
            assert ext == ext.lower()
            assert ext.startswith(".")

    def test_document_extensions_are_lowercase(self):
        for ext in DOCUMENT_EXTENSIONS:
            assert ext == ext.lower()
            assert ext.startswith(".")

    def test_archive_extensions_are_lowercase(self):
        for ext in ARCHIVE_EXTENSIONS:
            assert ext == ext.lower()
            assert ext.startswith(".")

    def test_common_image_formats(self):
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"]:
            assert ext in IMAGE_EXTENSIONS

    def test_pro_image_formats(self):
        for ext in [".exr", ".dpx", ".tga", ".dng"]:
            assert ext in IMAGE_EXTENSIONS

    def test_common_video_formats(self):
        for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
            assert ext in VIDEO_EXTENSIONS

    def test_pro_video_formats(self):
        for ext in [".mxf", ".r3d", ".braw"]:
            assert ext in VIDEO_EXTENSIONS

    def test_common_audio_formats(self):
        for ext in [".mp3", ".wav", ".flac", ".aac", ".ogg"]:
            assert ext in AUDIO_EXTENSIONS

    def test_pro_audio_formats(self):
        for ext in [".aiff", ".aif", ".bwf", ".rf64"]:
            assert ext in AUDIO_EXTENSIONS

    def test_common_doc_formats(self):
        for ext in [".pdf", ".doc", ".docx", ".txt", ".csv", ".md"]:
            assert ext in DOCUMENT_EXTENSIONS

    def test_common_archive_formats(self):
        for ext in [".zip", ".rar", ".7z", ".tar"]:
            assert ext in ARCHIVE_EXTENSIONS

    def test_no_extension_overlap_between_categories(self):
        cats = [IMAGE_EXTENSIONS, DOCUMENT_EXTENSIONS, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, ARCHIVE_EXTENSIONS]
        for i, a in enumerate(cats):
            for j, b in enumerate(cats):
                if i < j:
                    overlap = a & b
                    # .dng appears in both images and videos — known exception
                    allowed_overlap = {".dng"}
                    assert (
                        overlap <= allowed_overlap
                    ), f"Unexpected overlap between categories {i} and {j}: {overlap - allowed_overlap}"


class TestAllExtensionCategories:
    def test_has_all_categories(self):
        assert "images" in ALL_EXTENSION_CATEGORIES
        assert "documents" in ALL_EXTENSION_CATEGORIES
        assert "videos" in ALL_EXTENSION_CATEGORIES
        assert "audio" in ALL_EXTENSION_CATEGORIES
        assert "archives" in ALL_EXTENSION_CATEGORIES

    def test_maps_to_correct_sets(self):
        assert ALL_EXTENSION_CATEGORIES["images"] is IMAGE_EXTENSIONS
        assert ALL_EXTENSION_CATEGORIES["videos"] is VIDEO_EXTENSIONS


class TestCaptionAndSidecar:
    def test_caption_extensions(self):
        for ext in [".srt", ".vtt", ".ttml"]:
            assert ext in CAPTION_EXTENSIONS

    def test_sidecar_extensions(self):
        for ext in [".xmp", ".thm", ".lrv", ".json"]:
            assert ext in SIDECAR_EXTENSIONS

    def test_srt_in_both(self):
        assert ".srt" in CAPTION_EXTENSIONS
        assert ".srt" in SIDECAR_EXTENSIONS


class TestOperationTypes:
    def test_values(self):
        assert OP_TYPE_RENAME == "rename"
        assert OP_TYPE_ORGANIZE == "organize"
        assert OP_TYPE_EXTRACT == "extract"
        assert OP_TYPE_COPY == "copy"

    def test_all_distinct(self):
        types = {OP_TYPE_RENAME, OP_TYPE_ORGANIZE, OP_TYPE_EXTRACT, OP_TYPE_COPY}
        assert len(types) == 4


class TestCaseTransforms:
    def test_values(self):
        assert CASE_NONE == "none"
        assert CASE_UPPER == "upper"
        assert CASE_LOWER == "lower"
        assert CASE_TITLE == "title"


class TestConflictStrategies:
    def test_values(self):
        assert CONFLICT_COUNTER == "counter"
        assert CONFLICT_TIMESTAMP == "timestamp"
        assert CONFLICT_SKIP == "skip"


class TestUIDefaults:
    def test_window_size(self):
        assert DEFAULT_WINDOW_WIDTH == 1200
        assert DEFAULT_WINDOW_HEIGHT == 800

    def test_thumbnail(self):
        assert DEFAULT_THUMBNAIL_SIZE == 200

    def test_grid(self):
        assert DEFAULT_GRID_COLUMNS == 5


class TestThemes:
    def test_values(self):
        assert THEME_DARK == "dark"
        assert THEME_LIGHT == "light"


class TestPhotoKeywords:
    def test_has_keywords(self):
        assert "photo" in PHOTO_KEYWORDS
        assert "image" in PHOTO_KEYWORDS
        assert "picture" in PHOTO_KEYWORDS
