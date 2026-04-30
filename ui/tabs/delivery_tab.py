"""Delivery & Handoff tab for Pearl's File Tools.

Inner sub-tabs:
  1. Validator   — run DeliveryValidator against a folder
  2. Package     — create delivery .zip (only after validator passes)
  3. Duplicates  — find duplicate files by MD5
  4. Handoff     — colorist handoff checklist
  5. Manifest    — export shot list CSV
  6. QC Report   — generate HTML QC report
"""

import datetime
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
    QTabWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ui.tabs.base_tab import BaseTab
from ui.widgets.directory_selector import DirectorySelectorWidget
from workers.base_worker import BaseWorker


# ─────────────────────────────────────────────────────────────────────────────
# Colours
# ─────────────────────────────────────────────────────────────────────────────
_RED = QColor('#ff5370')
_YELLOW = QColor('#ffcb6b')
_GREEN = QColor('#c3e88d')
_GREY = QColor('#888888')


def _colored_item(text: str, color: QColor) -> QListWidgetItem:
    item = QListWidgetItem(text)
    item.setForeground(QBrush(color))
    return item


# ─────────────────────────────────────────────────────────────────────────────
# Background workers
# ─────────────────────────────────────────────────────────────────────────────

class _ValidateWorker(BaseWorker):
    finished = Signal(bool, str, object)  # success, msg, ValidationReport|None

    def __init__(self, directory: Path, profile):
        super().__init__()
        self.directory = directory
        self.profile = profile

    def emit_finished(self, success: bool, message: str, report=None):
        self.finished.emit(success, message, report)

    def run(self):
        from core.delivery import DeliveryValidator
        try:
            self.emit_progress("Scanning directory…")
            report = DeliveryValidator().validate(self.directory, self.profile)
            self.emit_finished(True, "Validation complete", report)
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


class _DuplicateWorker(BaseWorker):
    finished = Signal(bool, str, object)  # success, msg, List[DuplicateGroup]

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory

    def emit_finished(self, success: bool, message: str, groups=None):
        self.finished.emit(success, message, groups)

    def run(self):
        from core.delivery import find_duplicates
        try:
            self.emit_progress("Bucketing files by size…")
            groups = find_duplicates(
                self.directory,
                progress_cb=lambda msg, cur, tot: self.emit_progress(f"{msg} ({cur}/{tot})"),
                cancel_check=lambda: self.is_cancelled,
            )
            if self.is_cancelled:
                self.emit_finished(False, "Duplicate scan cancelled", None)
                return
            self.emit_finished(True, f"Found {len(groups)} duplicate group(s)", groups)
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


class _ZipWorker(BaseWorker):
    finished = Signal(bool, str, object)  # success, msg, zip_path|None

    def __init__(self, source_dir: Path, project_name: str, output_dir: Path):
        super().__init__()
        self.source_dir = source_dir
        self.project_name = project_name
        self.output_dir = output_dir

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        from core.delivery import create_delivery_zip
        try:
            self.emit_progress("Creating delivery zip…")
            path = create_delivery_zip(
                self.source_dir,
                self.project_name,
                self.output_dir,
                progress_cb=lambda msg, cur, tot: self.emit_progress(f"{msg} ({cur}/{tot})"),
                cancel_check=lambda: self.is_cancelled,
            )
            size_mb = path.stat().st_size / (1024 * 1024)
            self.emit_finished(True, f"Created {path.name} ({size_mb:.1f} MB)", path)
        except InterruptedError:
            self.emit_finished(False, "Zip cancelled by user", None)
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


class _ManifestWorker(BaseWorker):
    finished = Signal(bool, str, object)  # success, msg, output_path|None

    def __init__(self, source_dir: Path, output_path: Path):
        super().__init__()
        self.source_dir = source_dir
        self.output_path = output_path

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        from core.delivery import export_manifest
        try:
            self.emit_progress("Collecting file metadata…")
            count = export_manifest(self.source_dir, self.output_path)
            self.emit_finished(True, f"Exported {count} rows to {self.output_path.name}", self.output_path)
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


class _QCWorker(BaseWorker):
    finished = Signal(bool, str, object)

    def __init__(self, source_dir: Path, project_name: str, min_size: int, thumbnails: bool):
        super().__init__()
        self.source_dir = source_dir
        self.project_name = project_name
        self.min_size = min_size
        self.thumbnails = thumbnails

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        from core.qc_report import generate_qc_report
        try:
            self.emit_progress("Generating QC report…")
            path = generate_qc_report(
                self.source_dir,
                self.project_name,
                min_flag_size_bytes=self.min_size,
                include_thumbnails=self.thumbnails,
            )
            self.emit_finished(True, f"Report saved: {path.name}", path)
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: open file/folder in system viewer
# ─────────────────────────────────────────────────────────────────────────────

def _open_path(path: Path):
    try:
        if sys.platform == 'darwin':
            subprocess.Popen(['open', str(path)])
        elif sys.platform == 'win32':
            subprocess.Popen(['explorer', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Layout helper
# ─────────────────────────────────────────────────────────────────────────────

def _options_scroll(inner: QWidget) -> QScrollArea:
    """Wrap *inner* in a scroll area that sizes to content and scrolls when compressed."""
    sa = QScrollArea()
    sa.setWidget(inner)
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    sa.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    sa.setMinimumHeight(40)
    return sa


# ─────────────────────────────────────────────────────────────────────────────
# Validator pane
# ─────────────────────────────────────────────────────────────────────────────

class _ValidatorPane(QWidget):
    validation_passed = Signal(bool)   # emitted after each run

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker: Optional[_ValidateWorker] = None
        self._last_report = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Top pinned: directory ─────────────────────────────────────────────
        self.dir_selector = DirectorySelectorWidget(label_text="Folder:")
        layout.addWidget(self.dir_selector)

        # ── Scrollable options ────────────────────────────────────────────────
        opts_widget = QGroupBox("Validation rules")
        opts_layout = QFormLayout(opts_widget)
        self.chk_version = QCheckBox("Video files must have _FINAL or _v## suffix")
        self.chk_version.setChecked(True)
        opts_layout.addRow(self.chk_version)
        self.chk_hidden = QCheckBox("Flag hidden files (starting with '.')")
        self.chk_hidden.setChecked(True)
        opts_layout.addRow(self.chk_hidden)
        self.chk_case_dup = QCheckBox("Flag case-insensitive name collisions")
        self.chk_case_dup.setChecked(True)
        opts_layout.addRow(self.chk_case_dup)
        self.spn_min_mb = QSpinBox()
        self.spn_min_mb.setRange(0, 10000)
        self.spn_min_mb.setValue(1)
        self.spn_min_mb.setSuffix(" MB")
        self.spn_min_mb.setToolTip("Flag video files smaller than this (0 = disabled)")
        opts_layout.addRow("Min video file size:", self.spn_min_mb)
        layout.addWidget(_options_scroll(opts_widget))

        # ── Results (fills remaining space) ───────────────────────────────────
        self.result_list = QListWidget()
        self.result_list.setAlternatingRowColors(True)
        self.result_list.setMinimumHeight(120)
        layout.addWidget(self.result_list, stretch=1)

        # ── Bottom pinned: summary + run button ───────────────────────────────
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 2px 0;")
        layout.addWidget(self.summary_label)

        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Run Validation")
        self.run_btn.setStyleSheet("padding: 8px 20px;")
        self.run_btn.clicked.connect(self._run)
        btn_row.addWidget(self.run_btn)
        self.status_label = QLabel("")
        btn_row.addWidget(self.status_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _build_profile(self):
        from core.delivery import DeliveryProfile
        p = DeliveryProfile()
        p.require_version_suffix = self.chk_version.isChecked()
        p.check_hidden_files = self.chk_hidden.isChecked()
        p.check_case_duplicates = self.chk_case_dup.isChecked()
        p.min_video_size_bytes = self.spn_min_mb.value() * 1024 * 1024
        return p

    def _run(self):
        directory = Path(self.dir_selector.get_directory())
        if not directory.is_dir():
            QMessageBox.warning(self, "No Folder", "Please select a valid folder.")
            return
        if self._worker and self._worker.isRunning():
            return

        self.run_btn.setEnabled(False)
        self.result_list.clear()
        self.summary_label.setText("")
        self.status_label.setText("Scanning…")

        self._worker = _ValidateWorker(directory, self._build_profile())
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, message: str, report):
        self.run_btn.setEnabled(True)
        self.status_label.setText("")
        self._last_report = report

        if not success or report is None:
            self.result_list.addItem(_colored_item(f"Error: {message}", _RED))
            self.validation_passed.emit(False)
            return

        self.result_list.clear()
        if not report.issues:
            self.result_list.addItem(_colored_item("✓  No issues found", _GREEN))
        else:
            for issue in report.issues:
                color = _RED if issue.severity == "error" else _YELLOW
                label = "[ERROR]" if issue.severity == "error" else "[WARN]"
                self.result_list.addItem(_colored_item(
                    f"{label}  {issue.filepath.name}  —  {issue.description}", color
                ))

        passed = report.passed
        errs = report.error_count()
        warns = report.warning_count()
        color = _GREEN if passed else _RED
        status = "PASSED" if passed else "FAILED"
        self.summary_label.setText(
            f"{status}  |  {report.total_files} files  |  {errs} error(s)  |  {warns} warning(s)"
        )
        self.summary_label.setStyleSheet(
            f"font-weight: bold; padding: 4px; color: {'#c3e88d' if passed else '#ff5370'};"
        )
        self.validation_passed.emit(passed)


# ─────────────────────────────────────────────────────────────────────────────
# Package pane
# ─────────────────────────────────────────────────────────────────────────────

class _PackagePane(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker: Optional[_ZipWorker] = None
        self._source_dir: Optional[Path] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Top pinned: source, destination, project name ─────────────────────
        self.src_selector = DirectorySelectorWidget(label_text="Source:")
        self.src_selector.directory_changed.connect(self._update_source)
        layout.addWidget(QLabel("<b>Source folder</b> (must pass validation first)"))
        layout.addWidget(self.src_selector)

        self.dst_selector = DirectorySelectorWidget(label_text="Destination:")
        layout.addWidget(QLabel("<b>Output folder</b>"))
        layout.addWidget(self.dst_selector)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Project name:"))
        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("e.g. PROJECT_S01E03")
        self.project_edit.textChanged.connect(self._update_preview)
        self.src_selector.directory_changed.connect(self._update_preview)
        name_row.addWidget(self.project_edit)
        layout.addLayout(name_row)

        self.preview_label = QLabel("")
        self.preview_label.setStyleSheet("color: #888; font-style: italic; padding: 2px 0;")
        layout.addWidget(self.preview_label)

        # ── Log (fills remaining space) ───────────────────────────────────────
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        layout.addWidget(self.log, stretch=1)

        # ── Bottom pinned: action button ──────────────────────────────────────
        btn_row = QHBoxLayout()
        self.zip_btn = QPushButton("Create Delivery Zip")
        self.zip_btn.setStyleSheet("padding: 8px 20px;")
        self.zip_btn.clicked.connect(self._create_zip)
        btn_row.addWidget(self.zip_btn)
        self.status_label = QLabel("")
        btn_row.addWidget(self.status_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _update_source(self, path: str):
        self._source_dir = Path(path) if path else None

    def _update_preview(self):
        name = self.project_edit.text().strip()
        if name:
            date_str = datetime.date.today().strftime('%Y%m%d')
            import re
            safe = re.sub(r'[^\w\-]', '_', name)
            self.preview_label.setText(f"Output file: {safe}_DELIVERY_{date_str}.zip")
        else:
            self.preview_label.setText("")

    def set_source_from_validator(self, path: str):
        """Called by DeliveryTab when validation passes."""
        self.src_selector.set_directory(path)
        self._source_dir = Path(path)

    def _create_zip(self):
        src = Path(self.src_selector.get_directory())
        dst = Path(self.dst_selector.get_directory())
        name = self.project_edit.text().strip()

        if not src.is_dir():
            QMessageBox.warning(self, "Missing Source", "Please select the source folder.")
            return
        if not dst.is_dir():
            QMessageBox.warning(self, "Missing Destination", "Please select a destination folder.")
            return
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a project name.")
            return
        if self._worker and self._worker.isRunning():
            return

        # Preview what will be included
        from core.delivery import list_delivery_files
        files = list_delivery_files(src)
        total_mb = sum(f.stat().st_size for f in files if f.exists()) / (1024 * 1024)
        reply = QMessageBox.question(
            self, "Confirm Delivery Zip",
            f"This will include {len(files)} file(s) ({total_mb:.1f} MB).\n\nProceed?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        self.zip_btn.setEnabled(False)
        self.log.append("Creating zip…")
        self._worker = _ZipWorker(src, name, dst)
        self._worker.progress.connect(lambda m: self.log.append(m))
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, message: str, zip_path):
        self.zip_btn.setEnabled(True)
        if success and zip_path:
            self.log.append(f"✓ {message}")
            reply = QMessageBox.information(
                self, "Zip Created",
                f"{message}\n\nOpen containing folder?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                _open_path(zip_path.parent)
        else:
            self.log.append(f"✗ {message}")
            QMessageBox.critical(self, "Zip Failed", message)


# ─────────────────────────────────────────────────────────────────────────────
# Duplicates pane
# ─────────────────────────────────────────────────────────────────────────────

class _DuplicatesPane(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker: Optional[_DuplicateWorker] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Top pinned: directory ─────────────────────────────────────────────
        self.dir_selector = DirectorySelectorWidget(label_text="Folder:")
        layout.addWidget(self.dir_selector)

        # ── Results tree (fills remaining space) ──────────────────────────────
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File / Group", "Size", "MD5 (first 8)"])
        self.tree.setColumnWidth(0, 500)
        self.tree.setColumnWidth(1, 100)
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(120)
        layout.addWidget(self.tree, stretch=1)

        # ── Bottom pinned: summary + scan button ──────────────────────────────
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 2px 0;")
        layout.addWidget(self.summary_label)

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("Find Duplicates")
        self.scan_btn.setStyleSheet("padding: 8px 20px;")
        self.scan_btn.clicked.connect(self._scan)
        btn_row.addWidget(self.scan_btn)
        self.status_label = QLabel("")
        btn_row.addWidget(self.status_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _scan(self):
        directory = Path(self.dir_selector.get_directory())
        if not directory.is_dir():
            QMessageBox.warning(self, "No Folder", "Please select a valid folder.")
            return
        if self._worker and self._worker.isRunning():
            return

        self.scan_btn.setEnabled(False)
        self.tree.clear()
        self.summary_label.setText("")
        self.status_label.setText("Hashing…")

        self._worker = _DuplicateWorker(directory)
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, message: str, groups):
        self.scan_btn.setEnabled(True)
        self.status_label.setText("")

        if not success or groups is None:
            self.summary_label.setText(f"Error: {message}")
            return

        self.tree.clear()
        wasted = 0

        # Sequence-aware presentation. A duplicate group whose files all live
        # in the same folder *and* form a contiguous image sequence
        # (e.g. 36 EXR frames of a render that looped on a hold frame) is
        # collapsed into a single row labeled with the sequence's range,
        # rather than 36 separate "duplicate" rows. Real production users
        # have the same primitive intuition: that's a sequence, not 36
        # accidentally-duplicate files.
        from collections import defaultdict
        from core.pattern_matching import detect_image_sequences
        sequence_groups: List = []
        regular_groups: List = []
        for grp in groups:
            by_dir: Dict[Path, List[Path]] = defaultdict(list)
            for fp in grp.files:
                by_dir[fp.parent].append(fp)
            # A sequence group: every file shares the same parent and the
            # filenames form a single detected image sequence.
            if len(by_dir) == 1:
                parent_dir, members = next(iter(by_dir.items()))
                fnames = [p.name for p in members]
                seqs = detect_image_sequences(fnames, min_frames=2)
                if seqs and len(next(iter(seqs.values())).files) == len(members):
                    sequence_groups.append((grp, parent_dir, next(iter(seqs.values()))))
                    continue
            regular_groups.append(grp)

        def _fmt(n):
            if n < 1024:
                return f"{n} B"
            if n < 1024 ** 2:
                return f"{n / 1024:.1f} KB"
            return f"{n / 1024 ** 2:.1f} MB"

        # Render sequence-collapsed rows first so they're visually distinct
        for grp, parent_dir, seq in sequence_groups:
            sz = grp.size_bytes()
            waste = grp.wasted_bytes()
            wasted += waste
            label = (
                f"Image sequence ({len(grp.files)} identical frames)  —  "
                f"{seq.label}"
            )
            parent_item = QTreeWidgetItem([label, _fmt(sz), grp.hash[:8]])
            parent_item.setForeground(0, QBrush(_GREY))
            parent_item.setToolTip(
                0,
                "All files in this duplicate group form a contiguous image "
                "sequence with identical content — typically a hold frame "
                "render or a stalled NLE export. Collapsed for readability."
            )
            child = QTreeWidgetItem([str(parent_dir), "", ""])
            parent_item.addChild(child)
            self.tree.addTopLevelItem(parent_item)
            parent_item.setExpanded(False)

        for grp in regular_groups:
            sz = grp.size_bytes()
            waste = grp.wasted_bytes()
            wasted += waste

            parent_item = QTreeWidgetItem([
                f"Duplicate group ({len(grp.files)} copies)",
                _fmt(sz),
                grp.hash[:8],
            ])
            parent_item.setForeground(0, QBrush(_YELLOW))
            for fp in grp.files:
                child = QTreeWidgetItem([str(fp), _fmt(fp.stat().st_size if fp.exists() else 0), ""])
                parent_item.addChild(child)
            self.tree.addTopLevelItem(parent_item)
            parent_item.setExpanded(True)

        if not groups:
            root = QTreeWidgetItem(["No duplicates found", "", ""])
            root.setForeground(0, QBrush(_GREEN))
            self.tree.addTopLevelItem(root)
            self.summary_label.setText("No duplicates found.")
        else:
            def _fmt(n):
                if n < 1024 ** 2:
                    return f"{n / 1024:.1f} KB"
                return f"{n / 1024 ** 2:.1f} MB"
            self.summary_label.setText(
                f"{len(groups)} duplicate group(s)  |  {_fmt(wasted)} wasted"
            )
            self.summary_label.setStyleSheet("font-weight: bold; color: #ffcb6b; padding: 2px 0;")


# ─────────────────────────────────────────────────────────────────────────────
# Handoff pane
# ─────────────────────────────────────────────────────────────────────────────

class _HandoffPane(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Top pinned: directory ─────────────────────────────────────────────
        self.dir_selector = DirectorySelectorWidget(label_text="Folder:")
        layout.addWidget(self.dir_selector)

        # ── Scrollable options: rule description note ─────────────────────────
        note_widget = QWidget()
        note_layout = QVBoxLayout(note_widget)
        note_layout.setContentsMargins(0, 0, 0, 0)
        note = QLabel(
            "Default rules check for luts/ folder, audio stems, no OFFLINE files, "
            "and no tiny video files (<1 MB). Required rules must pass; optional rules "
            "show a warning."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 11px;")
        note_layout.addWidget(note)
        layout.addWidget(_options_scroll(note_widget))

        # ── Results (fills remaining space) ───────────────────────────────────
        self.result_list = QListWidget()
        self.result_list.setAlternatingRowColors(True)
        self.result_list.setMinimumHeight(120)
        layout.addWidget(self.result_list, stretch=1)

        # ── Bottom pinned: run button ─────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Run Handoff Checks")
        self.run_btn.setStyleSheet("padding: 8px 20px;")
        self.run_btn.clicked.connect(self._run)
        btn_row.addWidget(self.run_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _run(self):
        directory = Path(self.dir_selector.get_directory())
        if not directory.is_dir():
            QMessageBox.warning(self, "No Folder", "Please select a valid folder.")
            return

        from core.delivery import run_handoff_checks
        self.result_list.clear()
        try:
            results = run_handoff_checks(directory)
        except Exception as exc:
            self.result_list.addItem(_colored_item(f"Error: {exc}", _RED))
            return

        all_passed = True
        for res in results:
            if res.passed:
                icon = "✓"
                color = _GREEN
            else:
                icon = "✗"
                color = _RED if res.rule.required else _YELLOW
                if res.rule.required:
                    all_passed = False

            req_str = " [required]" if res.rule.required else " [optional]"
            detail = f"  — {res.detail}" if res.detail else ""
            self.result_list.addItem(_colored_item(
                f"{icon}  {res.rule.name}{req_str}{detail}", color
            ))

        sep = QListWidgetItem("")
        self.result_list.addItem(sep)
        if all_passed:
            self.result_list.addItem(_colored_item("All required checks PASSED", _GREEN))
        else:
            self.result_list.addItem(_colored_item("One or more required checks FAILED", _RED))


# ─────────────────────────────────────────────────────────────────────────────
# Combined Export pane (CSV Manifest OR HTML QC Report, toggled by radio)
# ─────────────────────────────────────────────────────────────────────────────

_MODE_CSV = 0
_MODE_QC  = 1


class _ExportPane(QWidget):
    """Single pane that toggles between CSV Manifest and HTML QC Report."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Top pinned: directory, project name, format toggle ────────────────
        self.dir_selector = DirectorySelectorWidget(label_text="Folder:")
        layout.addWidget(self.dir_selector)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Project name:"))
        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("e.g. PROJECT_S01E03  (used by QC Report; optional for CSV)")
        name_row.addWidget(self.project_edit)
        layout.addLayout(name_row)

        toggle_group = QGroupBox("Output format")
        toggle_layout = QHBoxLayout()
        self._radio_csv = QRadioButton("CSV Manifest")
        self._radio_qc  = QRadioButton("HTML QC Report")
        self._radio_csv.setChecked(True)
        self._btn_group = QButtonGroup(self)
        self._btn_group.addButton(self._radio_csv, _MODE_CSV)
        self._btn_group.addButton(self._radio_qc,  _MODE_QC)
        toggle_layout.addWidget(self._radio_csv)
        toggle_layout.addWidget(self._radio_qc)
        toggle_layout.addStretch()
        toggle_group.setLayout(toggle_layout)
        layout.addWidget(toggle_group)

        # ── Scrollable format-specific options ────────────────────────────────
        self._stack = QStackedWidget()

        # Page 0 — CSV options
        csv_page = QWidget()
        csv_layout = QVBoxLayout(csv_page)
        csv_layout.setContentsMargins(4, 4, 4, 4)
        csv_note = QLabel(
            "Writes filename, folder, size_bytes, extension, duration_secs, date_modified.\n"
            "duration_secs is populated when ffprobe or pymediainfo is available."
        )
        csv_note.setWordWrap(True)
        csv_note.setStyleSheet("color: #888; font-size: 11px;")
        csv_layout.addWidget(csv_note)

        # Page 1 — QC Report options
        qc_page = QWidget()
        qc_layout = QFormLayout(qc_page)
        qc_layout.setContentsMargins(4, 4, 4, 4)
        self.spn_min_mb = QSpinBox()
        self.spn_min_mb.setRange(0, 10000)
        self.spn_min_mb.setValue(1)
        self.spn_min_mb.setSuffix(" MB")
        self.spn_min_mb.setToolTip("Flag video files smaller than this (0 = disabled)")
        qc_layout.addRow("Flag threshold:", self.spn_min_mb)
        self.chk_thumbs = QCheckBox("Include first-frame thumbnails (requires ffmpeg)")
        self.chk_thumbs.setChecked(True)
        qc_layout.addRow(self.chk_thumbs)

        from core.qc_report import _HAS_FFMPEG
        if not _HAS_FFMPEG:
            no_ffmpeg = QLabel("ffmpeg not found — thumbnails will be skipped.")
            no_ffmpeg.setStyleSheet("color: #ffcb6b; font-size: 11px;")
            qc_layout.addRow(no_ffmpeg)
            self.chk_thumbs.setChecked(False)
            self.chk_thumbs.setEnabled(False)

        self._stack.addWidget(csv_page)
        self._stack.addWidget(qc_page)
        layout.addWidget(_options_scroll(self._stack))

        self._btn_group.idClicked.connect(self._on_mode_changed)

        # ── Log (fills remaining space) ───────────────────────────────────────
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(100)
        layout.addWidget(self.log, stretch=1)

        # ── Bottom pinned: export button ──────────────────────────────────────
        btn_row = QHBoxLayout()
        self.export_btn = QPushButton("Export CSV Manifest")
        self.export_btn.setStyleSheet("padding: 8px 20px;")
        self.export_btn.clicked.connect(self._export)
        btn_row.addWidget(self.export_btn)
        self.status_label = QLabel("")
        btn_row.addWidget(self.status_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_mode_changed(self, mode_id: int):
        self._stack.setCurrentIndex(mode_id)
        if mode_id == _MODE_CSV:
            self.export_btn.setText("Export CSV Manifest")
        else:
            self.export_btn.setText("Generate HTML QC Report")

    def _current_mode(self) -> int:
        return self._btn_group.checkedId()

    def set_directory(self, path: str):
        self.dir_selector.set_directory(path)

    def get_directory(self) -> str:
        return self.dir_selector.get_directory()

    # ── Export dispatcher ─────────────────────────────────────────────────────

    def _export(self):
        src = Path(self.dir_selector.get_directory())
        if not src.is_dir():
            QMessageBox.warning(self, "No Folder", "Please select a valid folder.")
            return
        if self._worker and self._worker.isRunning():
            return

        if self._current_mode() == _MODE_CSV:
            self._run_csv(src)
        else:
            self._run_qc(src)

    def _run_csv(self, src: Path):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dest_str, _ = QFileDialog.getSaveFileName(
            self, "Save Manifest CSV",
            str(src / f"manifest_{ts}.csv"),
            "CSV Files (*.csv)",
        )
        if not dest_str:
            return

        self.export_btn.setEnabled(False)
        self.status_label.setText("Exporting…")
        self._worker = _ManifestWorker(src, Path(dest_str))
        self._worker.progress.connect(lambda m: self.log.append(m))
        self._worker.finished.connect(self._on_csv_done)
        self._worker.start()

    def _on_csv_done(self, success: bool, message: str, output_path):
        self.export_btn.setEnabled(True)
        self.status_label.setText("")
        if success:
            self.log.append(f"✓ {message}")
            reply = QMessageBox.information(
                self, "Manifest Exported", message + "\n\nOpen file?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes and output_path:
                _open_path(output_path)
        else:
            self.log.append(f"✗ {message}")
            QMessageBox.critical(self, "Export Failed", message)

    def _run_qc(self, src: Path):
        name = self.project_edit.text().strip() or src.name
        self.export_btn.setEnabled(False)
        self.status_label.setText("Working…")
        self._worker = _QCWorker(
            src, name,
            self.spn_min_mb.value() * 1024 * 1024,
            self.chk_thumbs.isChecked(),
        )
        self._worker.progress.connect(lambda m: self.log.append(m))
        self._worker.finished.connect(self._on_qc_done)
        self._worker.start()

    def _on_qc_done(self, success: bool, message: str, report_path):
        self.export_btn.setEnabled(True)
        self.status_label.setText("")
        if success:
            self.log.append(f"✓ {message}")
            reply = QMessageBox.information(
                self, "QC Report Ready", message + "\n\nOpen in browser?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes and report_path:
                _open_path(report_path)
        else:
            self.log.append(f"✗ {message}")
            QMessageBox.critical(self, "Report Failed", message)


# ─────────────────────────────────────────────────────────────────────────────
# Main DeliveryTab
# ─────────────────────────────────────────────────────────────────────────────

class DeliveryTab(BaseTab):
    """Delivery & handoff tab."""

    def get_tab_name(self) -> str:
        return "Delivery"

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._inner_tabs = QTabWidget()

        self._validator_pane = _ValidatorPane(self.config)
        self._package_pane = _PackagePane(self.config)
        self._dupes_pane = _DuplicatesPane(self.config)
        self._handoff_pane = _HandoffPane(self.config)
        self._export_pane = _ExportPane(self.config)

        self._inner_tabs.addTab(self._validator_pane, "Validator")
        self._inner_tabs.addTab(self._package_pane, "Package")
        self._inner_tabs.addTab(self._dupes_pane, "Duplicates")
        self._inner_tabs.addTab(self._handoff_pane, "Handoff")
        self._inner_tabs.addTab(self._export_pane, "Export")

        layout.addWidget(self._inner_tabs)

        # When validator passes, pre-fill the Package pane source and switch to it
        self._validator_pane.validation_passed.connect(self._on_validation_result)

    def _on_validation_result(self, passed: bool):
        if passed:
            src = self._validator_pane.dir_selector.get_directory()
            self._package_pane.set_source_from_validator(src)
            self.emit_status("Validation passed — delivery zip is now available")
        else:
            self.emit_status("Validation found issues — fix before packaging")

    def load_settings(self):
        directory = self.config.get_tab_directory('delivery')
        if directory and Path(directory).is_dir():
            self._validator_pane.dir_selector.set_directory(directory)
            self._dupes_pane.dir_selector.set_directory(directory)
            self._handoff_pane.dir_selector.set_directory(directory)
            self._export_pane.set_directory(directory)

    def save_settings(self):
        directory = self._validator_pane.dir_selector.get_directory()
        if directory:
            self.config.set_tab_directory('delivery', directory)
