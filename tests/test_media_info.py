"""Comprehensive tests for core/media_info.py."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.media_info import MediaInfo, _has_data, _pymi_duration_ms, _via_ffprobe, _via_pymediainfo, get_media_info


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
        assert _has_data(MediaInfo(fps=24.0)) is False

    def test_audio_only(self):
        assert _has_data(MediaInfo(audio_channels=2)) is False


class TestGetMediaInfo:
    def test_returns_none_when_no_backends(self):
        with patch("core.media_info.HAS_FFPROBE", False), patch("core.media_info.HAS_PYMEDIAINFO", False):
            result = get_media_info(MagicMock())
            assert result is None

    def test_ffprobe_fallback_to_pymediainfo(self):
        with (
            patch("core.media_info.HAS_FFPROBE", True),
            patch("core.media_info.HAS_PYMEDIAINFO", True),
            patch("core.media_info._via_ffprobe", return_value=None),
            patch("core.media_info._via_pymediainfo", return_value=MediaInfo(codec="test")),
        ):
            result = get_media_info(MagicMock())
            assert result is not None
            assert result.codec == "test"

    def test_ffprobe_success_skips_pymediainfo(self):
        expected = MediaInfo(codec="h264", width=1920, height=1080)
        with (
            patch("core.media_info.HAS_FFPROBE", True),
            patch("core.media_info._via_ffprobe", return_value=expected),
            patch("core.media_info._via_pymediainfo") as pymi_mock,
        ):
            result = get_media_info(MagicMock())
            assert result == expected
            pymi_mock.assert_not_called()

    def test_pymediainfo_only(self):
        expected = MediaInfo(codec="aac", duration_secs=120.0)
        with (
            patch("core.media_info.HAS_FFPROBE", False),
            patch("core.media_info.HAS_PYMEDIAINFO", True),
            patch("core.media_info._via_pymediainfo", return_value=expected),
        ):
            result = get_media_info(MagicMock())
            assert result == expected


class TestViaFfprobe:
    """Tests for _via_ffprobe by mocking subprocess.run."""

    def _make_proc(self, returncode, stdout=""):
        proc = SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")
        return proc

    def _ffprobe_output(self, streams):
        return json.dumps({"streams": streams})

    def test_nonzero_returncode(self):
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(1)):
            assert _via_ffprobe(Path("/fake/video.mp4")) is None

    def test_exception_returns_none(self):
        with patch("core.media_info.subprocess.run", side_effect=OSError("no ffprobe")):
            assert _via_ffprobe(Path("/fake/video.mp4")) is None

    def test_video_stream_basic(self):
        streams = [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "24000/1001",
                "duration": "120.5",
            }
        ]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/video.mp4"))
            assert result is not None
            assert result.codec == "h264"
            assert result.width == 1920
            assert result.height == 1080
            assert result.fps == round(24000 / 1001, 3)
            assert result.duration_secs == 120.5

    def test_video_stream_no_fps_slash(self):
        streams = [{"codec_type": "video", "codec_name": "prores", "width": 3840, "height": 2160, "r_frame_rate": ""}]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/video.mov"))
            assert result is not None
            assert result.fps is None

    def test_video_stream_fps_zero_denominator(self):
        streams = [{"codec_type": "video", "codec_name": "h265", "width": 1920, "height": 1080, "r_frame_rate": "0/0"}]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/video.mp4"))
            assert result is not None
            assert result.fps is None

    def test_video_stream_fps_invalid(self):
        streams = [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "bad/data"}
        ]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/video.mp4"))
            assert result is not None
            assert result.fps is None

    def test_video_stream_duration_invalid(self):
        streams = [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "duration": "not_a_number"}
        ]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/video.mp4"))
            assert result is not None
            assert result.duration_secs is None

    def test_audio_only_stream(self):
        streams = [{"codec_type": "audio", "codec_name": "aac", "channels": 6, "duration": "300.0"}]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/audio.m4a"))
            assert result is not None
            assert result.codec == "aac"
            assert result.audio_channels == 6
            assert result.duration_secs == 300.0

    def test_audio_stream_invalid_duration(self):
        streams = [{"codec_type": "audio", "codec_name": "flac", "channels": 2, "duration": "nope"}]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/audio.flac"))
            assert result is not None
            assert result.duration_secs is None

    def test_video_plus_audio_streams(self):
        streams = [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "duration": "60.0",
            },
            {"codec_type": "audio", "codec_name": "aac", "channels": 2, "duration": "60.0"},
        ]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/video.mp4"))
            assert result is not None
            assert result.codec == "h264"
            assert result.audio_channels == 2
            assert result.duration_secs == 60.0

    def test_empty_streams_returns_none(self):
        stdout = self._ffprobe_output([])
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            assert _via_ffprobe(Path("/fake/empty.mp4")) is None

    def test_no_useful_data_returns_none(self):
        streams = [{"codec_type": "subtitle"}]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            assert _via_ffprobe(Path("/fake/subs.mkv")) is None

    def test_second_video_stream_ignored(self):
        streams = [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
            {"codec_type": "video", "codec_name": "h265", "width": 3840, "height": 2160},
        ]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/multi.mkv"))
            assert result.codec == "h264"
            assert result.width == 1920

    def test_audio_codec_used_when_no_video(self):
        streams = [{"codec_type": "audio", "codec_name": "mp3", "channels": 2, "duration": "180.0"}]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/song.mp3"))
            assert result.codec == "mp3"

    def test_audio_duration_not_overwritten_by_second_audio(self):
        streams = [
            {"codec_type": "audio", "codec_name": "aac", "channels": 2, "duration": "100.0"},
            {"codec_type": "audio", "codec_name": "aac", "channels": 6, "duration": "200.0"},
        ]
        stdout = self._ffprobe_output(streams)
        with patch("core.media_info.subprocess.run", return_value=self._make_proc(0, stdout)):
            result = _via_ffprobe(Path("/fake/dual.m4a"))
            assert result.duration_secs == 100.0
            assert result.audio_channels == 6


class TestViaPymediainfo:
    """Tests for _via_pymediainfo by mocking pymediainfo.MediaInfo.parse."""

    def _make_track(self, track_type, **kwargs):
        track = SimpleNamespace(track_type=track_type, **kwargs)
        return track

    def _make_parse_result(self, tracks):
        result = SimpleNamespace(tracks=tracks)
        return result

    def test_video_track_full(self):
        tracks = [
            self._make_track(
                "Video", codec_id="avc1", format="AVC", width=1920, height=1080, frame_rate="23.976", duration=120000
            )
        ]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/video.mp4"))
            assert result is not None
            assert result.codec == "avc1"
            assert result.width == 1920
            assert result.height == 1080
            assert result.fps == 23.976
            assert result.duration_secs == 120.0

    def test_video_track_format_fallback(self):
        track = self._make_track("Video", format="ProRes", width=3840, height=2160)
        delattr(track, "codec_id") if hasattr(track, "codec_id") else None
        tracks = [track]
        parse_result = self._make_parse_result(tracks)

        class FakeTrack:
            track_type = "Video"
            format = "ProRes"
            width = 3840
            height = 2160

        fake_track = FakeTrack()
        parse_result = self._make_parse_result([fake_track])
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/video.mov"))
            assert result is not None
            assert result.codec == "ProRes"

    def test_video_track_invalid_fps(self):
        tracks = [self._make_track("Video", codec_id="h264", width=1920, height=1080, frame_rate="variable")]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/video.mp4"))
            assert result is not None
            assert result.fps is None

    def test_video_track_invalid_duration(self):
        tracks = [self._make_track("Video", codec_id="h264", width=1920, height=1080, duration="unknown")]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/video.mp4"))
            assert result is not None
            assert result.duration_secs is None

    def test_audio_track_only(self):
        tracks = [self._make_track("Audio", codec_id="A_AAC", format="AAC", channel_s=6, duration=300000)]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/audio.m4a"))
            assert result is not None
            assert result.codec == "A_AAC"
            assert result.audio_channels == 6
            assert result.duration_secs == 300.0

    def test_audio_channel_invalid(self):
        tracks = [self._make_track("Audio", codec_id="mp3", format="MP3", channel_s="stereo", duration=60000)]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/audio.mp3"))
            assert result is not None
            assert result.audio_channels is None

    def test_audio_duration_invalid(self):
        tracks = [self._make_track("Audio", codec_id="flac", format="FLAC", channel_s=2, duration="bad")]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/audio.flac"))
            assert result is not None
            assert result.duration_secs is None

    def test_parse_exception_returns_none(self):
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.side_effect = RuntimeError("parse failed")
            result = _via_pymediainfo(Path("/fake/bad.mp4"))
            assert result is None

    def test_empty_tracks_returns_none(self):
        parse_result = self._make_parse_result([])
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            assert _via_pymediainfo(Path("/fake/empty.mp4")) is None

    def test_video_plus_audio(self):
        tracks = [
            self._make_track("Video", codec_id="hevc", width=3840, height=2160, frame_rate="60.0", duration=30000),
            self._make_track("Audio", codec_id="A_AAC", format="AAC", channel_s=2, duration=30000),
        ]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/video.mp4"))
            assert result is not None
            assert result.codec == "hevc"
            assert result.audio_channels == 2
            assert result.duration_secs == 30.0

    def test_second_video_track_ignored(self):
        tracks = [
            self._make_track("Video", codec_id="h264", width=1920, height=1080),
            self._make_track("Video", codec_id="h265", width=3840, height=2160),
        ]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/multi.mkv"))
            assert result.codec == "h264"
            assert result.width == 1920

    def test_audio_duration_not_overwritten(self):
        tracks = [
            self._make_track("Audio", codec_id="aac", channel_s=2, duration=100000),
            self._make_track("Audio", codec_id="aac", channel_s=6, duration=200000),
        ]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/dual.m4a"))
            assert result.duration_secs == 100.0
            assert result.audio_channels == 6

    def test_audio_no_duration_attribute(self):
        tracks = [self._make_track("Audio", codec_id="aac", channel_s=2)]
        parse_result = self._make_parse_result(tracks)
        with patch.dict("sys.modules", {"pymediainfo": MagicMock()}):
            import pymediainfo

            pymediainfo.MediaInfo.parse.return_value = parse_result
            result = _via_pymediainfo(Path("/fake/nodur.m4a"))
            assert result is not None
            assert result.duration_secs is None


class TestPymiDurationMs:
    def test_none_input(self):
        assert _pymi_duration_ms(None) is None

    def test_zero_input(self):
        assert _pymi_duration_ms(0) is None

    def test_valid_input(self):
        assert _pymi_duration_ms(60000) == 60.0

    def test_invalid_input(self):
        assert _pymi_duration_ms("bad") is None
