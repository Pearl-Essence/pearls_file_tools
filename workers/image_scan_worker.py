"""Image/video scan worker thread for Pearl's File Tools."""

import base64
import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Signal

from constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from workers.base_worker import BaseWorker

CACHE_FILE_NAME = ".image_browser_cache.json"


class ImageScanWorker(BaseWorker):
    """Worker thread for scanning directories for images."""

    progress = Signal(str)
    finished = Signal(bool, str, object)  # success, message, images list

    def emit_finished(self, success: bool, message: str, images=None):
        self.finished.emit(success, message, images)

    def __init__(self, root_dir: str, recursive: bool = True, use_cache: bool = True, include_video: bool = True):
        super().__init__()
        self.root_dir = Path(root_dir)
        self.recursive = recursive
        self.use_cache = use_cache
        self.include_video = include_video
        self.cache_file = self.root_dir / CACHE_FILE_NAME
        self._valid_extensions = set(IMAGE_EXTENSIONS)
        if include_video:
            self._valid_extensions |= VIDEO_EXTENSIONS

    def run(self):
        """Execute the directory scan."""
        try:
            # Try to load from cache first
            if self.use_cache:
                cached_images = self._load_from_cache()
                if cached_images is not None:
                    # Re-annotate every time — cheap, ensures old caches get sequence data
                    self._annotate_sequences(cached_images)
                    self.emit_progress(f"Loaded {len(cached_images)} images from cache")
                    self.emit_finished(True, f"Loaded {len(cached_images)} images from cache", cached_images)
                    return

            self.emit_progress("Scanning directory for files...")

            if self.recursive:
                images = self._scan_recursive()
            else:
                images = self._scan_flat()

            if images is None:
                # Cancelled during scan
                return

            images.sort(key=lambda x: x["name"].lower())
            self._annotate_sequences(images)
            self._enrich_videos(images)
            self._emit_scan_summary(images)

            if images:
                self._save_to_cache(images)
                self.emit_progress("Cache saved")

            self.emit_finished(True, f"Found {len(images)} file(s)", images)

        except Exception as e:
            self.emit_finished(False, f"Error scanning directory: {str(e)}", None)

    def _scan_recursive(self) -> Optional[List[Dict]]:
        """Walk the directory tree and collect matching file entries.

        Returns None if cancelled, otherwise a list of image/video dicts.
        """
        images: List[Dict] = []
        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            if self.is_cancelled:
                self.emit_finished(False, "Scan cancelled", None)
                return None

            current_dir = Path(dirpath)
            relative_dir = current_dir.relative_to(self.root_dir)

            if any(part.startswith(".") for part in relative_dir.parts):
                continue

            folder_name = str(relative_dir) if str(relative_dir) != "." else "Root"
            self.emit_progress(f"Scanning: {folder_name}")

            for filename in filenames:
                entry = self._make_entry(current_dir / filename, folder_name)
                if entry is not None:
                    images.append(entry)

        return images

    def _scan_flat(self) -> Optional[List[Dict]]:
        """Scan the root directory (non-recursive) for matching files.

        Returns None if cancelled, otherwise a list of image/video dicts.
        """
        images: List[Dict] = []
        self.emit_progress(f"Scanning: {self.root_dir.name}")

        for file_path in self.root_dir.iterdir():
            if self.is_cancelled:
                self.emit_finished(False, "Scan cancelled", None)
                return None

            if not file_path.is_file():
                continue

            entry = self._make_entry(file_path, "Root")
            if entry is not None:
                images.append(entry)

        return images

    def _make_entry(self, file_path: Path, folder_name: str) -> Optional[Dict]:
        """Build a single image/video entry dict, or None if the file should be skipped."""
        ext = file_path.suffix.lower()
        if ext not in self._valid_extensions:
            return None

        try:
            if file_path.is_symlink() and not file_path.exists():
                self.emit_progress(f"Skipping broken symlink: {file_path.name}")
                return None
            size = file_path.stat().st_size
        except OSError as exc:
            self.emit_progress(f"Skipping {file_path.name}: {exc}")
            return None

        entry: Dict = {
            "name": file_path.name,
            "path": str(file_path),
            "folder": folder_name,
            "size": size,
        }
        if ext in VIDEO_EXTENSIONS:
            entry["is_video"] = True
        return entry

    def _enrich_videos(self, images: List[Dict]) -> None:
        """Populate thumbnail and duration fields for video entries."""
        video_entries = [e for e in images if e.get("is_video")]
        if not video_entries:
            return

        self.emit_progress(f"Generating thumbnails for {len(video_entries)} video(s)...")
        for entry in video_entries:
            if self.is_cancelled:
                break
            thumb_b64 = self._extract_video_thumbnail(entry["path"])
            if thumb_b64:
                entry["thumbnail_b64"] = thumb_b64
            duration = self._get_video_duration(entry["path"])
            if duration is not None:
                entry["duration_secs"] = duration

    def _emit_scan_summary(self, images: List[Dict]) -> None:
        """Emit a human-readable progress message summarising the scan results."""
        total_images = sum(1 for e in images if not e.get("is_video"))
        total_videos = sum(1 for e in images if e.get("is_video"))
        parts = []
        if total_images:
            parts.append(f"{total_images} image(s)")
        if total_videos:
            parts.append(f"{total_videos} video(s)")
        self.emit_progress(f"Found {' + '.join(parts) if parts else '0 files'}")

    @staticmethod
    def _annotate_sequences(images: List[Dict]):
        """Detect image sequences per folder and annotate each image dict in-place.

        For each detected sequence, every frame gets ``in_sequence=True``.
        The first frame of each sequence also gets:
          - ``is_sequence_rep=True``
          - ``sequence_label``  — human-readable range label
          - ``sequence_total``  — total frame count
          - ``sequence_files``  — ordered list of absolute path strings for all frames
        """
        try:
            from core.pattern_matching import detect_image_sequences
        except ImportError:
            return

        _SEQUENCE_KEYS = (
            "in_sequence",
            "is_sequence_rep",
            "sequence_key",
            "sequence_label",
            "sequence_total",
            "sequence_files",
        )
        for img in images:
            for k in _SEQUENCE_KEYS:
                img.pop(k, None)

        folder_map = ImageScanWorker._build_folder_map(images)

        for folder, indices in folder_map.items():
            filenames = [images[i]["name"] for i in indices]
            sequences = detect_image_sequences(filenames)
            if not sequences:
                continue
            fname_to_key = ImageScanWorker._build_fname_lookup(sequences)
            ImageScanWorker._apply_sequence_annotations(images, indices, sequences, fname_to_key)

    @staticmethod
    def _build_folder_map(images: List[Dict]) -> Dict[str, List[int]]:
        folder_map: Dict[str, List[int]] = {}
        for i, img in enumerate(images):
            if img.get("is_video"):
                continue
            folder_map.setdefault(img["folder"], []).append(i)
        return folder_map

    @staticmethod
    def _build_fname_lookup(sequences: dict) -> Dict[str, str]:
        fname_to_key: Dict[str, str] = {}
        for seq_key, seq in sequences.items():
            for fname in seq.files:
                fname_to_key[fname] = seq_key
        return fname_to_key

    @staticmethod
    def _apply_sequence_annotations(images, indices, sequences, fname_to_key):
        for i in indices:
            fname = images[i]["name"]
            if fname not in fname_to_key:
                continue
            seq_key = fname_to_key[fname]
            seq = sequences[seq_key]
            images[i]["in_sequence"] = True
            images[i]["sequence_key"] = seq_key

            if fname == seq.files[0]:
                parent_dir = Path(images[i]["path"]).parent
                images[i]["is_sequence_rep"] = True
                images[i]["sequence_label"] = seq.label
                images[i]["sequence_total"] = len(seq.files)
                images[i]["sequence_files"] = [str(parent_dir / f) for f in seq.files]

    @staticmethod
    def _extract_video_thumbnail(path: str) -> Optional[str]:
        """Extract a single frame from a video via ffmpeg and return as base64 PNG."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-i", path, "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return base64.b64encode(result.stdout).decode("ascii")
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    @staticmethod
    def _get_video_duration(path: str) -> Optional[float]:
        """Get video duration in seconds via ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, OSError):
            pass
        return None

    def _get_directory_hash(self) -> Optional[str]:
        """Generate a hash based on directory structure for cache validation."""
        try:
            # Get directory modification time and file count
            dir_stat = self.root_dir.stat()
            mtime = dir_stat.st_mtime

            if self.recursive:
                image_count = sum(
                    1 for _ in self.root_dir.rglob("*") if _.is_file() and _.suffix.lower() in self._valid_extensions
                )
            else:
                image_count = sum(
                    1 for f in self.root_dir.iterdir() if f.is_file() and f.suffix.lower() in self._valid_extensions
                )

            hash_string = f"{self.root_dir}:{mtime}:{image_count}:{self.recursive}:{self.include_video}"
            return hashlib.sha256(hash_string.encode()).hexdigest()
        except Exception:
            return None

    def _load_from_cache(self) -> Optional[List[Dict]]:
        """Load images from cache file if valid."""
        try:
            if not self.cache_file.exists():
                return None

            with open(self.cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Validate cache
            current_hash = self._get_directory_hash()
            if cache_data.get("directory_hash") != current_hash:
                self.emit_progress("Cache outdated, rescanning...")
                return None

            # Validate that cached image files still exist
            images = cache_data.get("images", [])
            valid_images = []
            for img in images:
                if Path(img["path"]).exists():
                    valid_images.append(img)

            # If too many missing images, rescan
            if len(valid_images) < len(images) * 0.9:  # If >10% missing
                self.emit_progress("Cache has missing files, rescanning...")
                return None

            return valid_images

        except Exception as e:
            self.emit_progress(f"Cache load error: {e}")
            return None

    def _save_to_cache(self, images: List[Dict]):
        """Save images to cache file. Silently skips if path is read-only (e.g. network share)."""
        try:
            cache_data = {
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
                "directory": str(self.root_dir),
                "directory_hash": self._get_directory_hash(),
                "recursive": self.recursive,
                "image_count": len(images),
                "images": images,
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except OSError:
            pass
        except Exception as e:
            self.emit_progress(f"Cache save error: {e}")
