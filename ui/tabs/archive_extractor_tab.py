"""Archive Extractor tab — v0.17 visual refresh.

Functional behavior unchanged: same extraction worker, same undo stack, same
log filter logic. Layout uses the v0.17 chrome (TabHeader + Panel + status
pills + sticky footer with progress).
"""

from pathlib import Path
from typing import Dict

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from constants import PHOTO_KEYWORDS
from ui.tabs.base_tab import BaseTab
from ui.widgets.panel import Panel
from ui.widgets.path_card import PathCard
from ui.widgets.tab_header import TabHeader

# Optional libraries — same probes as before
try:
    import rarfile  # noqa: F401
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False

try:
    import py7zr  # noqa: F401
    HAS_PY7ZR = True
except ImportError:
    HAS_PY7ZR = False


class ArchiveExtractorTab(BaseTab):
    """Find archives under a folder and unpack them with optional backup + undo."""

    def __init__(self, config, parent=None):
        self.extraction_history = []
        self.full_log_lines = []
        super().__init__(config, parent)

    def get_tab_name(self) -> str:
        return "Extract Archives"

    # ─────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addWidget(self._build_source())
        root.addWidget(self._build_settings())
        root.addWidget(self._build_log(), stretch=1)
        root.addWidget(self._build_footer())

        # Surface missing-library warnings into the log on first paint
        if not HAS_RARFILE or not HAS_PY7ZR:
            missing = []
            if not HAS_RARFILE:
                missing.append("rarfile (RAR support)")
            if not HAS_PY7ZR:
                missing.append("py7zr (7Z support)")
            self.append_log(f"⚠ Missing optional libraries: {', '.join(missing)}")
            self.append_log(
                f"Install with: pip install {' '.join(m.split()[0] for m in missing)}\n"
            )

    # ── header ────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        self._header = TabHeader(
            eyebrow="02 · ORGANIZE · EXTRACT ARCHIVES",
            title="Extract Archives",
            subtitle="Find archives under a folder and unpack them safely.",
        )
        self.start_btn = self._header.add_action(
            "Start extraction", on_click=self.start_extraction, primary=True,
            tooltip="Find and extract all matching archives in the selected folder",
        )
        return self._header

    # ── source ────────────────────────────────────────────────────────────
    def _build_source(self) -> QWidget:
        self.path_card = PathCard("FOLDER TO SCAN")
        self.path_card.path_changed.connect(self._on_path_changed)
        return self.path_card

    # ── settings ──────────────────────────────────────────────────────────
    def _build_settings(self) -> QWidget:
        wrap = Panel()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(12)

        cols = QHBoxLayout()
        cols.setSpacing(28)

        # Formats column
        fc = QVBoxLayout()
        fc.setSpacing(6)
        fc_eye = QLabel("FORMATS")
        fc_eye.setObjectName("eyebrow")
        fc.addWidget(fc_eye)
        formats_row = QHBoxLayout()
        formats_row.setSpacing(14)
        self.zip_check = QCheckBox("ZIP")
        self.zip_check.setChecked(True)
        self.zip_check.setToolTip("Process .zip archives")
        self.tar_check = QCheckBox("TAR / TGZ / TBZ2")
        self.tar_check.setChecked(True)
        self.tar_check.setToolTip("Process .tar, .tar.gz, .tgz, .tar.bz2, and .tbz2 archives")
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
        for c in (self.zip_check, self.tar_check, self.rar_check, self.sevenz_check):
            formats_row.addWidget(c)
        formats_row.addStretch()
        fc.addLayout(formats_row)
        cols.addLayout(fc, stretch=1)

        # Options column
        oc = QVBoxLayout()
        oc.setSpacing(6)
        oc_eye = QLabel("OPTIONS")
        oc_eye.setObjectName("eyebrow")
        oc.addWidget(oc_eye)
        self.keyword_check = QCheckBox("Only extract archives with matching keywords in filename")
        self.keyword_check.setChecked(True)
        self.keyword_check.setToolTip("Skip archives whose filename doesn't contain at least one keyword")
        self.keyword_edit = QLineEdit(", ".join(PHOTO_KEYWORDS))
        self.keyword_edit.setToolTip("Comma-separated keywords to match against archive filenames (case-insensitive)")
        self.keyword_edit.setEnabled(self.keyword_check.isChecked())
        self.keyword_check.toggled.connect(self.keyword_edit.setEnabled)
        self.delete_check = QCheckBox("Delete archives after successful extraction (creates backup)")
        self.delete_check.setToolTip(
            "After extracting, move the archive to a timestamped backup folder\n"
            "in .archive_extractor_backups/ and then delete the original"
        )
        self.smart_extract_check = QCheckBox("Smart extraction (remove intermediate folders)")
        self.smart_extract_check.setChecked(True)
        self.smart_extract_check.setToolTip(
            "If archive contains only one folder, extract its contents directly"
        )
        for c in (self.keyword_check, self.keyword_edit, self.delete_check, self.smart_extract_check):
            oc.addWidget(c)
        cols.addLayout(oc, stretch=1)

        v.addLayout(cols)
        return wrap

    # ── log ───────────────────────────────────────────────────────────────
    def _build_log(self) -> QWidget:
        wrap = Panel()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        head = QHBoxLayout()
        eye = QLabel("EXTRACTION LOG")
        eye.setObjectName("eyebrow")
        head.addWidget(eye)
        head.addStretch()

        # Radio-style filter
        filt_label = QLabel("FILTER")
        filt_label.setObjectName("eyebrow")
        head.addWidget(filt_label)
        self.filter_all_check = QCheckBox("All")
        self.filter_all_check.setChecked(True)
        self.filter_all_check.setToolTip("Show all log entries")
        self.filter_failed_check = QCheckBox("Failed")
        self.filter_failed_check.setToolTip("Show only failed extraction entries")
        self.filter_success_check = QCheckBox("Success")
        self.filter_success_check.setToolTip("Show only successful extraction entries")
        for c in (self.filter_all_check, self.filter_failed_check, self.filter_success_check):
            c.clicked.connect(self.apply_log_filter)
            head.addWidget(c)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("ghostBtn")
        clear_btn.setToolTip("Clear the extraction log")
        clear_btn.clicked.connect(self.clear_log)
        head.addWidget(clear_btn)
        v.addLayout(head)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("JetBrains Mono", 10))
        v.addWidget(self.log_text, stretch=1)
        return wrap

    # ── footer ────────────────────────────────────────────────────────────
    def _build_footer(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("footer")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(16)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

        self.lbl_progress = QLabel("Idle")
        self.lbl_progress.setObjectName("cardSub")

        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(self.progress_bar)
        col.addWidget(self.lbl_progress)
        h.addLayout(col, stretch=1)

        self.undo_btn = QPushButton("Undo last extraction")
        self.undo_btn.setObjectName("ghostBtn")
        self.undo_btn.setEnabled(False)
        self.undo_btn.setToolTip("Delete extracted files and restore backed-up archives from the last batch")
        self.undo_btn.clicked.connect(self.undo_extraction)
        h.addWidget(self.undo_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("role", "danger")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setToolTip("Stop the current extraction (already-extracted files are kept)")
        self.cancel_btn.clicked.connect(self.cancel_extraction)
        h.addWidget(self.cancel_btn)

        return wrap

    # ─────────────────────────────────────────────────────────────────────
    # Behavior — preserved from v1
    # ─────────────────────────────────────────────────────────────────────
    def _on_path_changed(self, directory: str):
        self.set_directory(directory)

    def start_extraction(self):
        if not self.current_directory:
            self.show_warning("No folder", "Choose a folder to scan first.")
            return
        if not Path(self.current_directory).is_dir():
            self.show_error("Invalid folder", "The selected folder does not exist.")
            return

        keywords = [k.strip() for k in self.keyword_edit.text().split(',') if k.strip()]
        settings = {
            'zip':            self.zip_check.isChecked(),
            'tar':            self.tar_check.isChecked(),
            'rar':            self.rar_check.isChecked(),
            '7z':             self.sevenz_check.isChecked(),
            'keyword_filter': self.keyword_check.isChecked(),
            'keywords':       keywords,
            'delete_after':   self.delete_check.isChecked(),
            'smart_extract':  self.smart_extract_check.isChecked(),
        }
        if not any(settings[k] for k in ('zip', 'tar', 'rar', '7z')):
            self.show_warning("No formats selected",
                              "Pick at least one archive format to process.")
            return

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.path_card.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.lbl_progress.setText("Starting…")

        self.log_text.clear()
        self.full_log_lines.clear()

        from workers.extract_worker import ExtractWorker
        self.worker_thread = ExtractWorker(self.current_directory, settings)
        self.worker_thread.progress.connect(self.update_progress)
        self.worker_thread.log_message.connect(self.append_log)
        self.worker_thread.finished.connect(self.on_extraction_finished)
        self.worker_thread.start()
        self.emit_status("Extraction in progress…")

    def cancel_extraction(self):
        if self.worker_thread:
            self.worker_thread.cancel()
            self.cancel_btn.setEnabled(False)
            self.emit_status("Cancelling…")

    def update_progress(self, message: str, current: int, total: int):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            pct = int(100 * current / total)
            self.lbl_progress.setText(f"{pct}% · {current} / {total} · {message}")

    def append_log(self, message: str):
        self.full_log_lines.append(message)
        if self.should_display_log_line(message):
            self.log_text.append(message)
            sb = self.log_text.verticalScrollBar()
            sb.setValue(sb.maximum())

    def should_display_log_line(self, message: str) -> bool:
        if self.filter_all_check.isChecked():
            return True
        ctx = (message.startswith(("[", "Searching", "Keywords", "Smart", "Summary", "=")))
        if self.filter_failed_check.isChecked():
            return "✗" in message or "Failed" in message or "Error" in message or ctx
        if self.filter_success_check.isChecked():
            return "✓" in message or "Successfully" in message or ctx
        return True

    def apply_log_filter(self):
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
        if not (self.filter_all_check.isChecked() or
                self.filter_failed_check.isChecked() or
                self.filter_success_check.isChecked()):
            self.filter_all_check.setChecked(True)

        self.log_text.clear()
        for line in self.full_log_lines:
            if self.should_display_log_line(line):
                self.log_text.append(line)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def on_extraction_finished(self, success: bool, message: str,
                               extraction_record: Dict = None):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.path_card.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_progress.setText("Idle" if success else "Failed")

        if extraction_record and extraction_record.get('extractions'):
            self.extraction_history.append(extraction_record)
            self.undo_btn.setEnabled(True)

        self.emit_status(message)
        if success:
            self.show_info("Extraction complete", message)
        else:
            self.show_error("Extraction error", message)

    def undo_extraction(self):
        if not self.extraction_history:
            self.show_info("No history", "No extractions to undo.")
            return
        last = self.extraction_history[-1]
        n = len(last.get('extractions', []))
        if not self.confirm_action(
            "Confirm undo",
            f"Undo the last extraction batch?\n\n"
            f"  • {n} archive(s) extracted\n"
            f"  • Timestamp: {last.get('timestamp', 'Unknown')}\n\n"
            f"This will delete extracted files and restore any backups.",
        ):
            return

        self.append_log("\n" + "=" * 70)
        self.append_log("UNDOING LAST EXTRACTION")
        self.append_log("=" * 70)

        import shutil
        ok = fail = 0
        for extraction in last.get('extractions', []):
            archive_name = Path(extraction['archive_path']).name
            self.append_log(f"\nUndoing: {archive_name}")
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
                    fail += 1
            if extraction.get('archive_deleted') and extraction.get('backup_path'):
                try:
                    backup = Path(extraction['backup_path'])
                    original = Path(extraction['archive_path'])
                    if backup.exists():
                        shutil.copy2(backup, original)
                        backup.unlink()
                        self.append_log(f"  ✓ Restored archive: {original.name}")
                        ok += 1
                    else:
                        self.append_log(f"  ✗ Backup not found: {backup}")
                        fail += 1
                except Exception as e:
                    self.append_log(f"  ✗ Failed to restore archive: {e}")
                    fail += 1
            else:
                ok += 1

        self.extraction_history.pop()
        if not self.extraction_history:
            self.undo_btn.setEnabled(False)

        self.append_log("\n" + "=" * 70)
        self.append_log(f"Undo complete: {ok} succeeded, {fail} failed")
        self.append_log("=" * 70)
        self.emit_status(f"Undo complete: {ok} succeeded, {fail} failed")

    def clear_log(self):
        self.log_text.clear()
        self.full_log_lines.clear()
        self.emit_status("Log cleared")

    # ─────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────
    def load_settings(self):
        last_dir = self.config.get_tab_directory('archive_extractor')
        if last_dir:
            self.path_card.set_path(last_dir)
            self.set_directory(last_dir)

        s = self.config.get_tab_setting
        self.zip_check.setChecked(s('archive_extractor', 'zip_enabled', True))
        self.tar_check.setChecked(s('archive_extractor', 'tar_enabled', True))
        self.rar_check.setChecked(s('archive_extractor', 'rar_enabled', HAS_RARFILE))
        self.sevenz_check.setChecked(s('archive_extractor', '7z_enabled', HAS_PY7ZR))
        self.keyword_check.setChecked(s('archive_extractor', 'keyword_filter', True))
        saved_keywords = s('archive_extractor', 'custom_keywords', '')
        if saved_keywords:
            self.keyword_edit.setText(saved_keywords)
        self.delete_check.setChecked(s('archive_extractor', 'delete_after', False))
        self.smart_extract_check.setChecked(s('archive_extractor', 'smart_extract', True))

    def save_settings(self):
        s = self.config.set_tab_setting
        s('archive_extractor', 'zip_enabled',    self.zip_check.isChecked())
        s('archive_extractor', 'tar_enabled',    self.tar_check.isChecked())
        s('archive_extractor', 'rar_enabled',    self.rar_check.isChecked())
        s('archive_extractor', '7z_enabled',     self.sevenz_check.isChecked())
        s('archive_extractor', 'keyword_filter', self.keyword_check.isChecked())
        s('archive_extractor', 'custom_keywords', self.keyword_edit.text())
        s('archive_extractor', 'delete_after',   self.delete_check.isChecked())
        s('archive_extractor', 'smart_extract',  self.smart_extract_check.isChecked())
