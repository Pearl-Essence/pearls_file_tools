"""Image scan worker thread for Pearl's File Tools."""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from PyQt5.QtCore import pyqtSignal
from workers.base_worker import BaseWorker
from constants import IMAGE_EXTENSIONS

CACHE_FILE_NAME = '.image_browser_cache.json'


class ImageScanWorker(BaseWorker):
    """Worker thread for scanning directories for images."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str, object)  # success, message, images list

    def emit_finished(self, success: bool, message: str, images=None):
        self.finished.emit(success, message, images)

    def __init__(self, root_dir: str, recursive: bool = True, use_cache: bool = True):
        """
        Initialize the image scan worker.

        Args:
            root_dir: Root directory to scan
            recursive: Whether to scan subdirectories
            use_cache: Whether to use cached results
        """
        super().__init__()
        self.root_dir = Path(root_dir)
        self.recursive = recursive
        self.use_cache = use_cache
        self.cache_file = self.root_dir / CACHE_FILE_NAME

    def run(self):
        """Execute the directory scan."""
        try:
            images = []

            # Try to load from cache first
            if self.use_cache:
                cached_images = self._load_from_cache()
                if cached_images is not None:
                    self.emit_progress(f"Loaded {len(cached_images)} images from cache")
                    self.emit_finished(True, f"Loaded {len(cached_images)} images from cache", cached_images)
                    return

            # Cache not available, scan directory
            self.emit_progress("Scanning directory for images...")

            if self.recursive:
                # Recursive scan
                for dirpath, dirnames, filenames in os.walk(self.root_dir):
                    if self.is_cancelled:
                        self.emit_finished(False, "Scan cancelled", None)
                        return

                    current_dir = Path(dirpath)
                    relative_dir = current_dir.relative_to(self.root_dir)

                    # Skip hidden directories
                    if any(part.startswith('.') for part in relative_dir.parts):
                        continue

                    folder_name = str(relative_dir) if str(relative_dir) != '.' else 'Root'
                    self.emit_progress(f"Scanning: {folder_name}")

                    for filename in filenames:
                        if Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
                            file_path = current_dir / filename
                            images.append({
                                'name': filename,
                                'path': str(file_path),
                                'folder': folder_name,
                                'size': file_path.stat().st_size
                            })
            else:
                # Non-recursive scan (only root directory)
                self.emit_progress(f"Scanning: {self.root_dir.name}")

                for file_path in self.root_dir.iterdir():
                    if self.is_cancelled:
                        self.emit_finished(False, "Scan cancelled", None)
                        return

                    if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
                        images.append({
                            'name': file_path.name,
                            'path': str(file_path),
                            'folder': 'Root',
                            'size': file_path.stat().st_size
                        })

            # Sort images by name
            images.sort(key=lambda x: x['name'].lower())

            self.emit_progress(f"Found {len(images)} images")

            # Save to cache
            if images:
                self._save_to_cache(images)
                self.emit_progress("Cache saved")

            message = f"Found {len(images)} images"
            self.emit_finished(True, message, images)

        except Exception as e:
            self.emit_finished(False, f"Error scanning directory: {str(e)}", None)

    def _get_directory_hash(self) -> str:
        """Generate a hash based on directory structure for cache validation."""
        try:
            # Get directory modification time and file count
            dir_stat = self.root_dir.stat()
            mtime = dir_stat.st_mtime

            # Count image files
            if self.recursive:
                image_count = sum(
                    1 for _ in self.root_dir.rglob('*')
                    if _.is_file() and _.suffix.lower() in IMAGE_EXTENSIONS
                )
            else:
                image_count = sum(
                    1 for f in self.root_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
                )

            # Create hash from directory info
            hash_string = f"{self.root_dir}:{mtime}:{image_count}:{self.recursive}"
            return hashlib.md5(hash_string.encode()).hexdigest()
        except Exception:
            return None

    def _load_from_cache(self) -> List[Dict]:
        """Load images from cache file if valid."""
        try:
            if not self.cache_file.exists():
                return None

            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # Validate cache
            current_hash = self._get_directory_hash()
            if cache_data.get('directory_hash') != current_hash:
                self.emit_progress("Cache outdated, rescanning...")
                return None

            # Validate that cached image files still exist
            images = cache_data.get('images', [])
            valid_images = []
            for img in images:
                if Path(img['path']).exists():
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
                'version': '1.0',
                'timestamp': datetime.now().isoformat(),
                'directory': str(self.root_dir),
                'directory_hash': self._get_directory_hash(),
                'recursive': self.recursive,
                'image_count': len(images),
                'images': images
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
        except (PermissionError, OSError):
            pass
        except Exception as e:
            self.emit_progress(f"Cache save error: {e}")
