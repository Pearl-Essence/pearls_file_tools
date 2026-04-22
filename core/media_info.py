"""Media metadata reading for Pearl's File Tools.

Tries ffprobe first, falls back to pymediainfo, returns None if neither is available.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _check_ffprobe() -> bool:
    return shutil.which('ffprobe') is not None


HAS_FFPROBE: bool = _check_ffprobe()

try:
    import pymediainfo as _pymi  # noqa: F401
    HAS_PYMEDIAINFO = True
except ImportError:
    HAS_PYMEDIAINFO = False


@dataclass
class MediaInfo:
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    duration_secs: Optional[float] = None
    audio_channels: Optional[int] = None

    @property
    def resolution_str(self) -> Optional[str]:
        if self.width and self.height:
            return f"{self.width}\u00d7{self.height}"
        return None

    @property
    def duration_str(self) -> Optional[str]:
        if self.duration_secs is None:
            return None
        total = int(self.duration_secs)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @property
    def fps_str(self) -> Optional[str]:
        if self.fps is None:
            return None
        text = f"{self.fps:.3f}".rstrip('0').rstrip('.')
        return text

    def summary(self) -> str:
        """Single-line summary for tooltips."""
        parts = []
        if self.codec:
            parts.append(self.codec)
        if self.resolution_str:
            parts.append(self.resolution_str)
        if self.fps_str:
            parts.append(f"{self.fps_str} fps")
        if self.duration_str:
            parts.append(self.duration_str)
        if self.audio_channels:
            parts.append(f"{self.audio_channels}ch audio")
        return ', '.join(parts)


def get_media_info(filepath: Path) -> Optional[MediaInfo]:
    """Return MediaInfo for *filepath*, or None if no backend is available / file unreadable."""
    if HAS_FFPROBE:
        result = _via_ffprobe(filepath)
        if result is not None:
            return result
    if HAS_PYMEDIAINFO:
        return _via_pymediainfo(filepath)
    return None


def _has_data(info: MediaInfo) -> bool:
    return any(v is not None for v in (
        info.codec, info.width, info.duration_secs))


def _via_ffprobe(filepath: Path) -> Optional[MediaInfo]:
    try:
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            str(filepath),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
    except Exception:
        return None

    info = MediaInfo()
    for stream in data.get('streams', []):
        kind = stream.get('codec_type', '')
        if kind == 'video' and info.codec is None:
            info.codec = stream.get('codec_name')
            info.width = stream.get('width')
            info.height = stream.get('height')
            fps_raw = stream.get('r_frame_rate', '')
            if '/' in fps_raw:
                try:
                    num, den = fps_raw.split('/')
                    if int(den):
                        info.fps = round(int(num) / int(den), 3)
                except (ValueError, ZeroDivisionError):
                    pass
            dur = stream.get('duration')
            if dur:
                try:
                    info.duration_secs = float(dur)
                except ValueError:
                    pass
        elif kind == 'audio':
            ch = stream.get('channels')
            if ch:
                info.audio_channels = int(ch)
            if info.codec is None:
                info.codec = stream.get('codec_name')
            if info.duration_secs is None:
                dur = stream.get('duration')
                if dur:
                    try:
                        info.duration_secs = float(dur)
                    except ValueError:
                        pass

    return info if _has_data(info) else None


def _via_pymediainfo(filepath: Path) -> Optional[MediaInfo]:
    try:
        import pymediainfo
        mi = pymediainfo.MediaInfo.parse(str(filepath))
    except Exception:
        return None

    info = MediaInfo()
    for track in mi.tracks:
        if track.track_type == 'Video' and info.codec is None:
            info.codec = getattr(track, 'codec_id', None) or getattr(track, 'format', None)
            info.width = getattr(track, 'width', None)
            info.height = getattr(track, 'height', None)
            fps_raw = getattr(track, 'frame_rate', None)
            if fps_raw:
                try:
                    info.fps = float(fps_raw)
                except ValueError:
                    pass
            dur = getattr(track, 'duration', None)
            if dur:
                try:
                    info.duration_secs = float(dur) / 1000.0
                except ValueError:
                    pass
        elif track.track_type == 'Audio':
            ch = getattr(track, 'channel_s', None)
            if ch:
                try:
                    info.audio_channels = int(ch)
                except (ValueError, TypeError):
                    pass
            if info.codec is None:
                info.codec = getattr(track, 'codec_id', None) or getattr(track, 'format', None)
            if info.duration_secs is None:
                dur = getattr(track, 'duration', None)
                if dur:
                    try:
                        info.duration_secs = float(dur) / 1000.0
                    except ValueError:
                        pass

    return info if _has_data(info) else None
