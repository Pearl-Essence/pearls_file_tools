"""Comprehensive tests for core/media_info.py."""

from unittest.mock import MagicMock, patch

from core.media_info import MediaInfo, _has_data

# ── MediaInfo dataclass ─────────────────────────────────────────────────────


class TestMediaInfo:
    def test_resolution_str(self):
        info = MediaInfo(width=1920, height=1080)
        assert info.resolution_str == "1920×1080"

    def test_resolution_str_none_when_missing(self):
        info = MediaInfo()
        assert info.resolution_str is None

    def test_resolution_str_none_when_partial(self):
        info = MediaInfo(width=1920)
        assert info.resolution_str is None

    def test_duration_str_hours(self):
        info = MediaInfo(duration_secs=3723.0)
        assert info.duration_str == "1:02:03"

    def test_duration_str_minutes(self):
        info = MediaInfo(duration_secs=125.0)
        assert info.duration_str == "2:05"

    def test_duration_str_seconds_only(self):
        info = MediaInfo(duration_secs=45.0)
        assert info.duration_str == "0:45"

    def test_duration_str_none(self):
        info = MediaInfo()
        assert info.duration_str is None

    def test_fps_str_clean(self):
        info = MediaInfo(fps=24.0)
        assert info.fps_str == "24"

    def test_fps_str_fractional(self):
        info = MediaInfo(fps=23.976)
        assert info.fps_str == "23.976"

    def test_fps_str_trailing_zeros_stripped(self):
        info = MediaInfo(fps=30.0)
        assert info.fps_str == "30"

    def test_fps_str_none(self):
        info = MediaInfo()
        assert info.fps_str is None

    def test_summary_full(self):
        info = MediaInfo(codec="h264", width=1920, height=1080, fps=24.0, duration_secs=60.0, audio_channels=2)
        s = info.summary()
        assert "h264" in s
        assert "1920" in s
        assert "24" in s
        assert "1:00" in s
        assert "2ch audio" in s

    def test_summary_empty(self):
        info = MediaInfo()
        assert info.summary() == ""

    def test_summary_partial(self):
        info = MediaInfo(codec="prores")
        assert info.summary() == "prores"


# ── _has_data ───────────────────────────────────────────────────────────────


class TestHasData:
    def test_empty(self):
        assert _has_data(MediaInfo()) is False

    def test_codec_only(self):
        assert _has_data(MediaInfo(codec="h264")) is True

    def test_width_only(self):
        assert _has_data(MediaInfo(width=1920)) is True

    def test_duration_only(self):
        assert _has_data(MediaInfo(duration_secs=60.0)) is True

    def test_fps_only(self):
        # fps alone doesn't trigger _has_data (checks codec, width, duration_secs)
        assert _has_data(MediaInfo(fps=24.0)) is False

    def test_audio_only(self):
        assert _has_data(MediaInfo(audio_channels=2)) is False


# ── get_media_info (with mocking) ──────────────────────────────────────────


class TestGetMediaInfo:
    def test_returns_none_when_no_backends(self):
        with patch("core.media_info.HAS_FFPROBE", False), patch("core.media_info.HAS_PYMEDIAINFO", False):
            from core.media_info import get_media_info

            result = get_media_info(MagicMock())
            assert result is None

    def test_ffprobe_fallback_to_pymediainfo(self):
        with (
            patch("core.media_info.HAS_FFPROBE", True),
            patch("core.media_info.HAS_PYMEDIAINFO", True),
            patch("core.media_info._via_ffprobe", return_value=None),
            patch("core.media_info._via_pymediainfo", return_value=MediaInfo(codec="test")),
        ):
            from core.media_info import get_media_info

            result = get_media_info(MagicMock())
            assert result is not None
            assert result.codec == "test"

    def test_ffprobe_success_skips_pymediainfo(self):
        expected = MediaInfo(codec="h264", width=1920, height=1080)
        with (
            patch("core.media_info.HAS_FFPROBE", True),
            patch("core.media_info._via_ffprobe", return_value=expected) as ffprobe_mock,
            patch("core.media_info._via_pymediainfo") as pymi_mock,
        ):
            from core.media_info import get_media_info

            result = get_media_info(MagicMock())
            assert result == expected
            pymi_mock.assert_not_called()
