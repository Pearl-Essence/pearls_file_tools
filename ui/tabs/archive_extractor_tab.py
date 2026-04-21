"""Archive Extractor tab for Pearl's File Tools."""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                            QTextEdit, QProgressBar, QGroupBox, QCheckBox)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
from pathlib import Path
from typing import Dict, Any
from ui.tabs.base_tab import BaseTab
from ui.widgets.directory_selector import DirectorySelectorWidget


# Check for optional libraries
try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False

try:
    import py7zr
    HAS_PY7ZR = True
except ImportError:
    HAS_PY7ZR = False


class ArchiveExtractorTab(BaseTab):
    """Tab for extracting photo/image archives."""

    def __init__(self, config, parent=None):
        """Initialize the archive extractor tab."""
        self.extraction_history = []  # Stack of extraction records
        self.full_log_lines = []
        super().__init__(config, parent)

    def get_tab_name(self) -> str:
        """Get the tab name."""
        return "Archive Extractor"

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()

        # Directory selection
        self.dir_selector = DirectorySelectorWidget(label_text="Directory to Search:")
        self.dir_selector.directory_changed.connect(self.on_directory_changed)
        layout.addWidget(self.dir_selector)

        # Settings panel
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()

        # Archive format checkboxes
        formats_label = QLabel("Archive Formats:")
        formats_label.setFont(QFont("", -1, QFont.Bold))
        settings_layout.addWidget(formats_label)

        formats_layout = QHBoxLayout()
        self.zip_check = QCheckBox("ZIP")
        self.zip_check.setChecked(True)

        self.tar_check = QCheckBox("TAR/TGZ/TBZ2")
        self.tar_check.setChecked(True)

        self.rar_check = QCheckBox("RAR")
        self.rar_check.setChecked(HAS_RARFILE)
        self.rar_check.setEnabled(HAS_RARFILE)
        if not HAS_RARFILE:
            self.rar_check.setToolTip("Install 'rarfile' library for RAR support")

        self.sevenz_check = QCheckBox("7Z")
        self.sevenz_check.setChecked(HAS_PY7ZR)
        self.sevenz_check.setEnabled(HAS_PY7ZR)
        if not HAS_PY7ZR:
            self.sevenz_check.setToolTip("Install 'py7zr' library for 7Z support")

        formats_layout.addWidget(self.zip_check)
        formats_layout.addWidget(self.tar_check)
        formats_layout.addWidget(self.rar_check)
        formats_layout.addWidget(self.sevenz_check)
        formats_layout.addStretch()
        settings_layout.addLayout(formats_layout)

        # Options
        options_label = QLabel("Options:")
        options_label.setFont(QFont("", -1, QFont.Bold))
        settings_layout.addWidget(options_label)

        self.keyword_check = QCheckBox("Only extract archives with photo/image keywords in filename")
        self.keyword_check.setChecked(True)
        self.keyword_check.setToolTip("Keywords: photo, photos, image, images (case-insensitive)")
        settings_layout.addWidget(self.keyword_check)

        self.delete_check = QCheckBox("Delete archives after successful extraction (creates backup)")
        self.delete_check.setChecked(False)
        settings_layout.addWidget(self.delete_check)

        self.smart_extract_check = QCheckBox("Smart extraction (remove intermediate folders)")
        self.smart_extract_check.setChecked(True)
        self.smart_extract_check.setToolTip("If archive contains only one folder, extract its contents directly")
        settings_layout.addWidget(self.smart_extract_check)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Log window
        log_group = QGroupBox("Extraction Log")
        log_layout = QVBoxLayout()

        # Filter controls
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter:")

        self.filter_all_check = QCheckBox("All")
        self.filter_all_check.setChecked(True)
        self.filter_all_check.clicked.connect(self.apply_log_filter)

        self.filter_failed_check = QCheckBox("Failed Only")
        self.filter_failed_check.clicked.connect(self.apply_log_filter)

        self.filter_success_check = QCheckBox("Success Only")
        self.filter_success_check.clicked.connect(self.apply_log_filter)

        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_all_check)
        filter_layout.addWidget(self.filter_failed_check)
        filter_layout.addWidget(self.filter_success_check)
        filter_layout.addStretch()
        log_layout.addLayout(filter_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier New", 9))
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group, stretch=1)

        # Control buttons
        button_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Extraction")
        self.start_btn.clicked.connect(self.start_extraction)
        self.start_btn.setStyleSheet("padding: 10px; font-size: 14px; font-weight: bold;")
        button_layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_extraction)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)

        self.undo_btn = QPushButton("Undo Last Extraction")
        self.undo_btn.clicked.connect(self.undo_extraction)
        self.undo_btn.setEnabled(False)
        button_layout.addWidget(self.undo_btn)

        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        button_layout.addWidget(self.clear_log_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Show warning if optional libraries are missing
        if not HAS_RARFILE or not HAS_PY7ZR:
            missing = []
            if not HAS_RARFILE:
                missing.append("rarfile (for RAR support)")
            if not HAS_PY7ZR:
                missing.append("py7zr (for 7Z support)")

            self.append_log(f"⚠ Missing optional libraries: {', '.join(missing)}")
            self.append_log(f"Install with: pip install {' '.join([m.split()[0] for m in missing])}\n")

    def on_directory_changed(self, directory: str):
        """Handle directory change."""
        self.set_directory(directory)

    def start_extraction(self):
        """Start the extraction process."""
        if not self.current_directory:
            self.show_warning("No Directory", "Please select a directory first.")
            return

        if not Path(self.current_directory).is_dir():
            self.show_error("Invalid Directory", "The selected directory does not exist.")
            return

        # Gather settings
        settings = {
            'zip': self.zip_check.isChecked(),
            'tar': self.tar_check.isChecked(),
            'rar': self.rar_check.isChecked(),
            '7z': self.sevenz_check.isChecked(),
            'keyword_filter': self.keyword_check.isChecked(),
            'delete_after': self.delete_check.isChecked(),
            'smart_extract': self.smart_extract_check.isChecked()
        }

        # Check if at least one format is selected
        if not any([settings['zip'], settings['tar'], settings['rar'], settings['7z']]):
            self.show_warning("No Formats Selected", "Please select at least one archive format to process.")
            return

        # Disable controls
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.dir_selector.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        # Clear log
        self.log_text.clear()
        self.full_log_lines.clear()

        # Start worker
        from workers.extract_worker import ExtractWorker

        self.worker_thread = ExtractWorker(self.current_directory, settings)
        self.worker_thread.progress.connect(self.update_progress)
        self.worker_thread.log_message.connect(self.append_log)
        self.worker_thread.finished.connect(self.on_extraction_finished)
        self.worker_thread.start()

        self.emit_status("Extraction in progress...")

    def cancel_extraction(self):
        """Cancel the extraction process."""
        if self.worker_thread:
            self.worker_thread.cancel()
            self.cancel_btn.setEnabled(False)
            self.emit_status("Cancelling...")

    def update_progress(self, message: str, current: int, total: int):
        """Update progress bar."""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def append_log(self, message: str):
        """Append message to log."""
        # Store in full log
        self.full_log_lines.append(message)

        # Only display if it passes current filter
        if self.should_display_log_line(message):
            self.log_text.append(message)
            # Auto-scroll to bottom
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def should_display_log_line(self, message: str) -> bool:
        """Determine if a log line should be displayed based on current filter."""
        if self.filter_all_check.isChecked():
            return True
        elif self.filter_failed_check.isChecked():
            # Show failures and context
            return ("✗" in message or "Failed" in message or "Error" in message or
                    message.startswith("[") or message.startswith("Searching") or
                    message.startswith("Keywords") or message.startswith("Smart") or
                    message.startswith("Summary") or message.startswith("="))
        elif self.filter_success_check.isChecked():
            # Show successes and context
            return ("✓" in message or "Successfully" in message or
                    message.startswith("[") or message.startswith("Searching") or
                    message.startswith("Keywords") or message.startswith("Smart") or
                    message.startswith("Summary") or message.startswith("="))
        return True

    def apply_log_filter(self):
        """Apply the selected filter to the log display."""
        # Make checkboxes act like radio buttons
        sender = self.sender()
        if sender == self.filter_all_check:
            self.filter_failed_check.setChecked(False)
            self.filter_success_check.setChecked(False)
        elif sender == self.filter_failed_check:
            self.filter_all_check.setChecked(False)
            self.filter_success_check.setChecked(False)
        elif sender == self.filter_success_check:
            self.filter_all_check.setChecked(False)
            self.filter_failed_check.setChecked(False)

        # Rebuild log display with filter
        self.log_text.clear()
        for line in self.full_log_lines:
            if self.should_display_log_line(line):
                self.log_text.append(line)

        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_extraction_finished(self, success: bool, message: str, extraction_record: Dict = None):
        """Handle extraction completion."""
        # Re-enable controls
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.dir_selector.setEnabled(True)
        self.progress_bar.setVisible(False)

        # Save extraction record if there were successful extractions
        if extraction_record and extraction_record.get('extractions'):
            self.extraction_history.append(extraction_record)
            self.undo_btn.setEnabled(True)

        self.emit_status(message)

        if success:
            self.show_info("Extraction Complete", message)
        else:
            self.show_error("Extraction Error", message)

    def undo_extraction(self):
        """Undo the most recent extraction batch."""
        if not self.extraction_history:
            self.show_info("No History", "No extractions to undo.")
            return

        # Confirm with user
        last_record = self.extraction_history[-1]
        num_extractions = len(last_record.get('extractions', []))

        if not self.confirm_action(
            "Confirm Undo",
            f"This will undo the last extraction batch:\n\n"
            f"  • {num_extractions} archive(s) extracted\n"
            f"  • Timestamp: {last_record.get('timestamp', 'Unknown')}\n\n"
            f"This will:\n"
            f"  1. Delete all extracted files\n"
            f"  2. Restore backed up archives (if any)\n\n"
            f"Continue?"
        ):
            return

        self.append_log("\n" + "=" * 70)
        self.append_log("UNDOING LAST EXTRACTION")
        self.append_log("=" * 70)

        import shutil
        success_count = 0
        failed_count = 0

        for extraction in last_record.get('extractions', []):
            archive_name = Path(extraction['archive_path']).name
            self.append_log(f"\nUndoing: {archive_name}")

            # Delete extracted items
            for item_path in extraction.get('extracted_items', []):
                try:
                    item = Path(item_path)
                    if item.exists():
                        if item.is_dir():
                            shutil.rmtree(item)
                            self.append_log(f"  ✓ Removed folder: {item.name}")
                        else:
                            item.unlink()
                            self.append_log(f"  ✓ Removed file: {item.name}")
                except Exception as e:
                    self.append_log(f"  ✗ Failed to remove {item_path}: {e}")
                    failed_count += 1

            # Restore archive if it was deleted
            if extraction.get('archive_deleted') and extraction.get('backup_path'):
                try:
                    backup = Path(extraction['backup_path'])
                    original = Path(extraction['archive_path'])

                    if backup.exists():
                        shutil.copy2(backup, original)
                        backup.unlink()  # Remove backup after restore
                        self.append_log(f"  ✓ Restored archive: {original.name}")
                        success_count += 1
                    else:
                        self.append_log(f"  ✗ Backup not found: {backup}")
                        failed_count += 1
                except Exception as e:
                    self.append_log(f"  ✗ Failed to restore archive: {e}")
                    failed_count += 1
            else:
                success_count += 1

        # Remove from history
        self.extraction_history.pop()

        # Disable undo button if no more history
        if not self.extraction_history:
            self.undo_btn.setEnabled(False)

        self.append_log("\n" + "=" * 70)
        self.append_log(f"Undo complete: {success_count} succeeded, {failed_count} failed")
        self.append_log("=" * 70)

        self.emit_status(f"Undo complete: {success_count} succeeded, {failed_count} failed")

    def clear_log(self):
        """Clear the log window."""
        self.log_text.clear()
        self.full_log_lines.clear()
        self.emit_status("Log cleared")

    def load_settings(self):
        """Load tab-specific settings."""
        last_dir = self.config.get_tab_directory('archive_extractor')
        if last_dir:
            self.dir_selector.set_directory(last_dir)
            self.set_directory(last_dir)

        # Load checkbox states
        self.zip_check.setChecked(self.config.get_tab_setting('archive_extractor', 'zip_enabled', True))
        self.tar_check.setChecked(self.config.get_tab_setting('archive_extractor', 'tar_enabled', True))
        self.rar_check.setChecked(self.config.get_tab_setting('archive_extractor', 'rar_enabled', HAS_RARFILE))
        self.sevenz_check.setChecked(self.config.get_tab_setting('archive_extractor', '7z_enabled', HAS_PY7ZR))
        self.keyword_check.setChecked(self.config.get_tab_setting('archive_extractor', 'keyword_filter', True))
        self.delete_check.setChecked(self.config.get_tab_setting('archive_extractor', 'delete_after', False))
        self.smart_extract_check.setChecked(self.config.get_tab_setting('archive_extractor', 'smart_extract', True))

    def save_settings(self):
        """Save tab-specific settings."""
        self.config.set_tab_setting('archive_extractor', 'zip_enabled', self.zip_check.isChecked())
        self.config.set_tab_setting('archive_extractor', 'tar_enabled', self.tar_check.isChecked())
        self.config.set_tab_setting('archive_extractor', 'rar_enabled', self.rar_check.isChecked())
        self.config.set_tab_setting('archive_extractor', '7z_enabled', self.sevenz_check.isChecked())
        self.config.set_tab_setting('archive_extractor', 'keyword_filter', self.keyword_check.isChecked())
        self.config.set_tab_setting('archive_extractor', 'delete_after', self.delete_check.isChecked())
        self.config.set_tab_setting('archive_extractor', 'smart_extract', self.smart_extract_check.isChecked())
