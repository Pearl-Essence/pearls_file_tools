"""Extract worker thread for Pearl's File Tools."""

import os
import datetime
from pathlib import Path
from typing import Dict
from PyQt5.QtCore import pyqtSignal
from workers.base_worker import BaseWorker
from core.file_utils import has_keyword
from core.archive_utils import extract_archive
from constants import PHOTO_KEYWORDS

BACKUP_DIR_NAME = ".archive_extractor_backups"


class ExtractWorker(BaseWorker):
    """Worker thread for extracting archives."""

    # Signals
    progress = pyqtSignal(str, int, int)  # message, current, total
    log_message = pyqtSignal(str)
    finished = pyqtSignal(bool, str, object)  # success, message, extraction_record

    def __init__(self, root_dir: str, settings: Dict):
        """
        Initialize the extract worker.

        Args:
            root_dir: Root directory to search
            settings: Dictionary of extraction settings
        """
        super().__init__()
        self.root_dir = Path(root_dir)
        self.settings = settings
        self.extraction_record = {
            'timestamp': datetime.datetime.now().isoformat(),
            'root_dir': str(root_dir),
            'extractions': [],
            'failed_extractions': []
        }

    def emit_finished(self, success: bool, message: str, record=None):
        """Emit finished signal with optional extraction record."""
        self.finished.emit(success, message, record)

    def get_archive_type(self, filepath: Path) -> str:
        """
        Determine archive type based on file extension.

        Args:
            filepath: Path to archive file

        Returns:
            Archive type ('zip', 'tar', 'rar', '7z') or None
        """
        filepath_lower = str(filepath).lower()

        # Check enabled formats from settings
        if self.settings['zip'] and filepath_lower.endswith('.zip'):
            return 'zip'

        if self.settings['tar']:
            tar_extensions = ['.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz']
            for ext in tar_extensions:
                if filepath_lower.endswith(ext):
                    return 'tar'

        if self.settings['rar'] and filepath_lower.endswith('.rar'):
            return 'rar'

        if self.settings['7z'] and filepath_lower.endswith('.7z'):
            return '7z'

        return None

    def run(self):
        """Execute the extraction process."""
        try:
            self.log_message.emit(f"Searching in: {self.root_dir}")

            if self.settings['keyword_filter']:
                self.log_message.emit(f"Keywords (case-insensitive): {', '.join(PHOTO_KEYWORDS)}")

            if self.settings['smart_extract']:
                self.log_message.emit("Smart extraction: Removing intermediate folders when possible")

            self.log_message.emit("-" * 70)

            # First pass: count total archives
            total_archives = []
            for dirpath, dirnames, filenames in os.walk(self.root_dir):
                if self.is_cancelled:
                    self.emit_finished(False, "Operation cancelled", None)
                    return

                for filename in filenames:
                    filepath = Path(dirpath) / filename

                    # Check keyword filter
                    if self.settings['keyword_filter']:
                        if not has_keyword(filename, PHOTO_KEYWORDS):
                            continue

                    # Check if it's a supported archive type
                    if self.get_archive_type(filepath):
                        total_archives.append(filepath)

            found_count = len(total_archives)
            extracted_count = 0

            if found_count == 0:
                self.log_message.emit("\nNo matching archives found.")
                self.emit_finished(True, "No matching archives found", self.extraction_record)
                return

            # Second pass: extract archives
            for idx, filepath in enumerate(total_archives):
                if self.is_cancelled:
                    self.log_message.emit("\nOperation cancelled by user.")
                    break

                self.log_message.emit(f"\n[{idx + 1}/{found_count}] {filepath.relative_to(self.root_dir)}")

                # Extract to the same directory as the archive
                extract_to = filepath.parent
                self.log_message.emit(f"  Extracting to: {extract_to.relative_to(self.root_dir)}")

                archive_type = self.get_archive_type(filepath)
                extracted_items = extract_archive(
                    filepath,
                    extract_to,
                    archive_type,
                    use_smart_extract=self.settings['smart_extract']
                )

                if extracted_items:
                    extracted_count += 1
                    self.log_message.emit("  ✓ Successfully extracted")

                    # Record the extraction
                    extraction_entry = {
                        'archive_path': str(filepath),
                        'extract_dir': str(extract_to),
                        'extracted_items': [str(item) for item in extracted_items],
                        'archive_deleted': False,
                        'backup_path': None
                    }

                    # Backup and delete archive if requested
                    if self.settings['delete_after']:
                        try:
                            import shutil

                            # Create backup directory
                            backup_dir = self.root_dir / BACKUP_DIR_NAME
                            backup_dir.mkdir(exist_ok=True)

                            # Backup archive with timestamp
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            backup_name = f"{filepath.stem}_{timestamp}{filepath.suffix}"
                            backup_path = backup_dir / backup_name

                            shutil.copy2(filepath, backup_path)
                            extraction_entry['backup_path'] = str(backup_path)

                            # Delete original
                            filepath.unlink()
                            extraction_entry['archive_deleted'] = True
                            self.log_message.emit("  ✓ Archive backed up and deleted")
                        except Exception as e:
                            self.log_message.emit(f"  ✗ Failed to backup/delete: {e}")

                    self.extraction_record['extractions'].append(extraction_entry)
                else:
                    self.log_message.emit("  ✗ Failed to extract")
                    # Record the failure
                    self.extraction_record['failed_extractions'].append({
                        'archive_path': str(filepath),
                        'extract_dir': str(extract_to)
                    })

                # Update progress
                self.progress.emit("", idx + 1, found_count)

            # Summary
            self.log_message.emit("\n" + "=" * 70)
            self.log_message.emit("Summary:")
            self.log_message.emit(f"  Archives found: {found_count}")
            self.log_message.emit(f"  Successfully extracted: {extracted_count}")
            self.log_message.emit(f"  Failed: {found_count - extracted_count}")

            message = f"Complete: {extracted_count}/{found_count} archives extracted successfully"
            self.emit_finished(True, message, self.extraction_record)

        except Exception as e:
            self.log_message.emit(f"\nError: {str(e)}")
            self.emit_finished(False, f"Error: {str(e)}", None)
