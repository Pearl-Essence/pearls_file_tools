"""Studio Tools tab for Pearl's File Tools.

Six inner sub-tabs:
  1. Stale Files     — detect and soft-delete stale/temp/zero-byte/empty items
  2. Storage         — storage usage report by subfolder and file category
  3. Trash           — view / restore / purge items in .pearls_trash/
  4. Cold Storage    — archive a project folder to a destination with manifest + verify
  5. NLE Backup      — backup project files for DaVinci, FCP, Premiere Pro, and more
  6. Export Watcher  — poll a folder for new video file arrivals and validate/log them
"""

import csv
import datetime
import hashlib
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QRadioButton, QSizePolicy, QSpinBox, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QWizard, QWizardPage,
)

from ui.tabs.base_tab import BaseTab
from ui.widgets.directory_selector import DirectorySelectorWidget
from workers.base_worker import BaseWorker
from core.trash import StudioTrash, TrashItem
from constants import ALL_EXTENSION_CATEGORIES


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

_STALE_MARKERS = re.compile(r'_WIP|_DRAFT|_TEST|_TEMP', re.IGNORECASE)

_CATEGORY_EXTS: Dict[str, set] = {
    cat: {e.lower() for e in exts}
    for cat, exts in ALL_EXTENSION_CATEGORIES.items()
}

_CATEGORY_ORDER = ['videos', 'images', 'audio', 'documents', 'archives', 'other']

_CATEGORY_COLORS = {
    'videos':    QColor('#82aaff'),
    'images':    QColor('#c3e88d'),
    'audio':     QColor('#c792ea'),
    'documents': QColor('#ffcb6b'),
    'archives':  QColor('#f78c6c'),
    'other':     QColor('#546e7a'),
}

_STRIP_PATTERNS = [
    re.compile(r'^\.'),
    re.compile(r'_WIP|_DRAFT|_TEMP|_TEST', re.IGNORECASE),
    re.compile(r'\.(tmp|bak|log)$', re.IGNORECASE),
    re.compile(r'__pycache__'),
    re.compile(r'Thumbs\.db$', re.IGNORECASE),
    re.compile(r'\.DS_Store$'),
]


def _file_category(suffix: str) -> str:
    s = suffix.lower()
    for cat, exts in _CATEGORY_EXTS.items():
        if s in exts:
            return cat
    return 'other'


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


def _md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open('rb') as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _should_strip(filepath: Path) -> bool:
    for part in filepath.parts:
        if part.startswith('.') and len(part) > 1:
            return True
        if part == '__pycache__':
            return True
    name = filepath.name
    for pat in _STRIP_PATTERNS:
        if pat.search(name):
            return True
    return False


def _gather_files(
    source_dir: Path,
    extra_exclude_patterns: List[str],
) -> Tuple[List[Path], List[Path]]:
    """Return (include_files, exclude_files) applying default + extra excludes."""
    extra_pats = [
        re.compile(p.replace('*', '.*'), re.IGNORECASE)
        for p in extra_exclude_patterns if p.strip()
    ]
    include: List[Path] = []
    exclude: List[Path] = []
    for fp in source_dir.rglob('*'):
        if not fp.is_file():
            continue
        if TRASH_DIR_NAME in fp.parts:
            continue
        strip = _should_strip(fp)
        if not strip:
            for pat in extra_pats:
                if pat.search(fp.name):
                    strip = True
                    break
        (exclude if strip else include).append(fp)
    return sorted(include), sorted(exclude)


TRASH_DIR_NAME = '.pearls_trash'

# ─────────────────────────────────────────────────────────────────────────────
# NLE project file format registry
# ─────────────────────────────────────────────────────────────────────────────

# Each entry: NLE name → set of extensions (lowercase, with dot)
_NLE_FORMATS: Dict[str, set] = {
    'DaVinci Resolve':     {'.drp'},
    'Final Cut Pro':       {'.fcpbundle', '.fcpxml'},
    'Premiere Pro':        {'.prproj'},
    'After Effects':       {'.aep', '.aet'},
    'Avid Media Composer': {'.avp', '.avs'},
    'Pro Tools':           {'.ptx', '.ptf'},
    'Vegas Pro':           {'.veg'},
    'Audition':            {'.sesx'},
    'Logic Pro':           {'.logicx'},
    'Kdenlive':            {'.kdenlive'},
}

# Extensions that are macOS package directories — back up by zipping
_PACKAGE_EXTS = {'.fcpbundle', '.logicx'}


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StaleFile:
    path: Path
    reason: str
    size_bytes: int
    is_dir: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Background workers
# ─────────────────────────────────────────────────────────────────────────────

class _NLEBackupWorker(BaseWorker):
    """Backup NLE project files/packages from scan_dir to dest_dir with a timestamp suffix."""
    finished = pyqtSignal(bool, str, object)  # success, msg, List[dict]|None
    file_backed = pyqtSignal(str)             # name of each completed item

    def __init__(self, scan_dir: Path, dest_dir: Path, extensions: set):
        super().__init__()
        self.scan_dir = scan_dir
        self.dest_dir = dest_dir
        self.extensions = {e.lower() for e in extensions}

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def _find_projects(self) -> List[Path]:
        """Return all matching project files and package directories.

        Walks the tree manually rather than using :meth:`Path.rglob` so we
        can skip the *contents* of package directories (e.g. ``.fcpbundle``,
        ``.logicx``). Without this, a Final Cut scan that lists both
        ``.fcpbundle`` and ``.fcpxml`` extensions would harvest the
        ``CurrentVersion.fcpxml`` *inside* every bundle as a separate
        "project", duplicating work and confusing the manifest. It also
        avoids descending tens-of-thousands of internal files in real
        bundles, which is a major performance footgun.
        """
        found: List[Path] = []

        def walk(directory: Path) -> None:
            try:
                entries = list(directory.iterdir())
            except (PermissionError, OSError):
                return
            for child in entries:
                try:
                    suffix = child.suffix.lower()
                    if child.is_dir():
                        # A package directory we care about — register and
                        # do NOT descend into it.
                        if suffix in _PACKAGE_EXTS and suffix in self.extensions:
                            found.append(child)
                            continue
                        # Other apps' packages — opaque, also skip.
                        if suffix in _PACKAGE_EXTS:
                            continue
                        walk(child)
                    elif child.is_file():
                        if suffix in self.extensions and suffix not in _PACKAGE_EXTS:
                            found.append(child)
                except OSError:
                    continue

        walk(self.scan_dir)
        return sorted(found)

    def run(self):
        try:
            projects = self._find_projects()
            if not projects:
                self.emit_finished(True, "No matching project files found.", [])
                return
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            results = []
            for proj in projects:
                if self.is_cancelled:
                    break
                try:
                    if proj.is_dir():
                        # Package directory (e.g. .fcpbundle) — zip it
                        import zipfile
                        dest_name = f"{proj.stem}_{ts}.zip"
                        dest_path = self.dest_dir / dest_name
                        with zipfile.ZipFile(dest_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                            for fp in proj.rglob('*'):
                                if fp.is_file():
                                    zf.write(fp, fp.relative_to(proj.parent))
                        size = dest_path.stat().st_size
                    else:
                        dest_name = f"{proj.stem}_{ts}{proj.suffix}"
                        dest_path = self.dest_dir / dest_name
                        shutil.copy2(str(proj), str(dest_path))
                        size = dest_path.stat().st_size
                    results.append({
                        'name': proj.name, 'dest': dest_name,
                        'size': size, 'timestamp': ts, 'ok': True,
                    })
                    self.file_backed.emit(proj.name)
                except Exception as exc:
                    results.append({
                        'name': proj.name, 'error': str(exc),
                        'timestamp': ts, 'ok': False,
                    })
            ok = sum(1 for r in results if r.get('ok'))
            self.emit_finished(True, f"Backed up {ok}/{len(results)} project(s)", results)
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


class _StaleWorker(BaseWorker):
    finished = pyqtSignal(bool, str, object)

    def __init__(self, directory: Path, max_age_days: int, check_atime: bool):
        super().__init__()
        self.directory = directory
        self.max_age_days = max_age_days
        self.check_atime = check_atime

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        results: List[StaleFile] = []
        cutoff_ts = (
            datetime.datetime.now() - datetime.timedelta(days=self.max_age_days)
        ).timestamp()
        try:
            self.emit_progress("Scanning for stale files…")
            for item in self.directory.rglob('*'):
                if self.is_cancelled:
                    break
                if TRASH_DIR_NAME in item.parts:
                    continue
                try:
                    stat = item.stat()
                except OSError:
                    continue
                if item.is_file():
                    if _STALE_MARKERS.search(item.stem):
                        results.append(StaleFile(item, "WIP/Draft/Temp marker", stat.st_size))
                    elif stat.st_size == 0:
                        results.append(StaleFile(item, "Zero-byte file", 0))
                    elif self.check_atime and stat.st_atime < cutoff_ts:
                        days = int(
                            (datetime.datetime.now().timestamp() - stat.st_atime) / 86400
                        )
                        results.append(StaleFile(
                            item, f"Not accessed in {days} days", stat.st_size
                        ))
                elif item.is_dir():
                    if not any(True for _ in item.rglob('*') if _.is_file()):
                        results.append(StaleFile(item, "Empty folder", 0, is_dir=True))
            self.emit_finished(True, f"Found {len(results)} stale item(s)", results)
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


class _StorageWorker(BaseWorker):
    finished = pyqtSignal(bool, str, object)

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        data: Dict[str, Dict[str, int]] = {}
        try:
            self.emit_progress("Scanning storage usage…")
            for fp in self.directory.rglob('*'):
                if self.is_cancelled:
                    break
                if not fp.is_file():
                    continue
                if TRASH_DIR_NAME in fp.parts:
                    continue
                try:
                    size = fp.stat().st_size
                except OSError:
                    continue
                try:
                    rel = fp.relative_to(self.directory)
                    folder = rel.parts[0] if len(rel.parts) > 1 else '__root__'
                except ValueError:
                    folder = '__root__'
                cat = _file_category(fp.suffix)
                if folder not in data:
                    data[folder] = {c: 0 for c in _CATEGORY_ORDER}
                data[folder][cat] = data[folder].get(cat, 0) + size
            self.emit_finished(True, "Scan complete", data)
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


class _ManifestWorker(BaseWorker):
    finished = pyqtSignal(bool, str, object)
    file_hashed = pyqtSignal(str, int, int)

    def __init__(self, source_dir: Path, dest_dir: Path, include_files: List[Path]):
        super().__init__()
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.include_files = include_files

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        manifest = []
        total = len(self.include_files)
        try:
            self.emit_progress(f"Hashing {total} file(s)…")
            for i, fp in enumerate(self.include_files):
                if self.is_cancelled:
                    break
                try:
                    checksum = _md5(fp)
                    rel = str(fp.relative_to(self.source_dir))
                    size = fp.stat().st_size
                    mtime = datetime.datetime.fromtimestamp(
                        fp.stat().st_mtime
                    ).isoformat()
                    manifest.append({
                        'path': rel, 'md5': checksum,
                        'size': size, 'mtime': mtime,
                    })
                    self.file_hashed.emit(fp.name, i + 1, total)
                except Exception:
                    pass
            manifest_path = self.dest_dir / 'MANIFEST.json'
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        'source': str(self.source_dir),
                        'files': manifest,
                        'generated': datetime.datetime.now().isoformat(),
                    },
                    indent=2, ensure_ascii=False,
                ),
                encoding='utf-8',
            )
            self.emit_finished(
                True, f"Manifest created: {len(manifest)} file(s)",
                (manifest_path, manifest),
            )
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


class _CopyWorker(BaseWorker):
    finished = pyqtSignal(bool, str, object)
    file_copied = pyqtSignal(str, int, int)

    def __init__(
        self,
        source_dir: Path,
        dest_dir: Path,
        include_files: List[Path],
        as_zip: bool,
        flatten: bool,
    ):
        super().__init__()
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.include_files = include_files
        self.as_zip = as_zip
        self.flatten = flatten

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        total = len(self.include_files)
        try:
            if self.as_zip:
                import zipfile
                ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                zip_path = self.dest_dir / f"{self.source_dir.name}_{ts}.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for i, fp in enumerate(self.include_files):
                        if self.is_cancelled:
                            break
                        arcname = (
                            fp.name if self.flatten
                            else str(fp.relative_to(self.source_dir))
                        )
                        zf.write(str(fp), arcname)
                        self.file_copied.emit(fp.name, i + 1, total)
                self.emit_finished(True, f"Created {zip_path.name}", zip_path)
            else:
                for i, fp in enumerate(self.include_files):
                    if self.is_cancelled:
                        break
                    if self.flatten:
                        dst = self.dest_dir / fp.name
                    else:
                        dst = self.dest_dir / fp.relative_to(self.source_dir)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(fp), str(dst))
                    self.file_copied.emit(fp.name, i + 1, total)
                self.emit_finished(
                    True, f"Copied {total} file(s) to {self.dest_dir.name}",
                    self.dest_dir,
                )
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


class _VerifyWorker(BaseWorker):
    finished = pyqtSignal(bool, str, object)
    file_verified = pyqtSignal(str, bool)

    def __init__(self, dest_dir: Path, manifest_data: list):
        super().__init__()
        self.dest_dir = dest_dir
        self.manifest_data = manifest_data

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        results = []
        try:
            self.emit_progress("Verifying…")
            for entry in self.manifest_data:
                if self.is_cancelled:
                    break
                rel = entry['path']
                expected = entry['md5']
                # Try relative path first, then flat name
                candidate = self.dest_dir / rel
                if not candidate.exists():
                    candidate = self.dest_dir / Path(rel).name
                if not candidate.exists():
                    results.append((rel, False, "Missing"))
                    self.file_verified.emit(rel, False)
                    continue
                ok = _md5(candidate) == expected
                results.append((rel, ok, "OK" if ok else "Checksum mismatch"))
                self.file_verified.emit(rel, ok)
            passed = sum(1 for _, ok, _ in results if ok)
            failed = len(results) - passed
            self.emit_finished(
                True, f"{passed}/{len(results)} verified, {failed} failed", results
            )
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


# ─────────────────────────────────────────────────────────────────────────────
# Storage proportional bar
# ─────────────────────────────────────────────────────────────────────────────

class _StorageBar(QWidget):
    """Horizontal stacked bar showing storage breakdown by file category."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: List[Tuple[str, int]] = []
        self._total = 0
        self.setMinimumHeight(22)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, segments: List[Tuple[str, int]]):
        self._segments = [(cat, sz) for cat, sz in segments if sz > 0]
        self._total = sum(sz for _, sz in self._segments)
        self.update()

    def paintEvent(self, event):
        if not self._total:
            return
        p = QPainter(self)
        w, h = self.width(), self.height()
        x = 0
        for cat, sz in self._segments:
            seg_w = max(1, int(w * sz / self._total))
            p.fillRect(x, 0, seg_w, h, _CATEGORY_COLORS.get(cat, _CATEGORY_COLORS['other']))
            x += seg_w
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# Stale Files pane
# ─────────────────────────────────────────────────────────────────────────────

class _StaleFilesPane(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker: Optional[_StaleWorker] = None
        self._stale_items: List[StaleFile] = []
        self._trash: Optional[StudioTrash] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.dir_selector = DirectorySelectorWidget(label_text="Folder:")
        layout.addWidget(self.dir_selector)

        opts = QGroupBox("Detection options")
        opts_layout = QFormLayout(opts)
        self.age_spin = QSpinBox()
        self.age_spin.setRange(1, 3650)
        self.age_spin.setValue(30)
        self.age_spin.setSuffix(" days")
        self.age_spin.setToolTip("Flag files not accessed in this many days")
        opts_layout.addRow("Unused for:", self.age_spin)
        self.chk_atime = QCheckBox("Flag files not accessed in N days")
        self.chk_atime.setChecked(True)
        self.chk_atime.setToolTip(
            "Uses file last-access time (atime). May be unreliable on some macOS volumes "
            "where noatime is set."
        )
        opts_layout.addRow(self.chk_atime)
        layout.addWidget(opts)

        self.result_list = QListWidget()
        self.result_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.result_list.setAlternatingRowColors(True)
        self.result_list.setMinimumHeight(120)
        layout.addWidget(self.result_list, stretch=1)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 2px 0;")
        layout.addWidget(self.summary_label)

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("Scan for Stale Files")
        self.scan_btn.setStyleSheet("padding: 8px 20px;")
        self.scan_btn.clicked.connect(self._scan)
        btn_row.addWidget(self.scan_btn)
        self.trash_btn = QPushButton("Send Checked to Trash")
        self.trash_btn.setEnabled(False)
        self.trash_btn.clicked.connect(self._trash_selected)
        btn_row.addWidget(self.trash_btn)
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
        self.trash_btn.setEnabled(False)
        self.result_list.clear()
        self.summary_label.setText("")
        self.status_label.setText("Scanning…")
        self._trash = StudioTrash(directory)

        self._worker = _StaleWorker(
            directory, self.age_spin.value(), self.chk_atime.isChecked()
        )
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, message: str, results):
        self.scan_btn.setEnabled(True)
        self.status_label.setText("")
        self._stale_items = results or []

        if not success:
            QMessageBox.critical(self, "Scan Error", message)
            return

        self.result_list.clear()
        if not self._stale_items:
            item = QListWidgetItem("✓  No stale files found")
            item.setForeground(QBrush(QColor('#c3e88d')))
            self.result_list.addItem(item)
        else:
            for sf in self._stale_items:
                prefix = "[DIR]  " if sf.is_dir else ""
                label = f"{prefix}{sf.path.name}  —  {sf.reason}"
                if sf.size_bytes:
                    label += f"  ({_fmt_size(sf.size_bytes)})"
                lwi = QListWidgetItem(label)
                lwi.setToolTip(str(sf.path))
                lwi.setCheckState(Qt.Checked)
                self.result_list.addItem(lwi)
            self.trash_btn.setEnabled(True)

        total_size = sum(sf.size_bytes for sf in self._stale_items)
        self.summary_label.setText(
            f"Found {len(self._stale_items)} stale item(s)  |  {_fmt_size(total_size)} total"
        )

    def _trash_selected(self):
        if not self._trash:
            return
        checked = [
            i for i in range(self.result_list.count())
            if self.result_list.item(i).checkState() == Qt.Checked
            and i < len(self._stale_items)
        ]
        if not checked:
            QMessageBox.information(self, "None Checked", "Check items to send to trash.")
            return
        selected = [self._stale_items[i] for i in checked]
        reply = QMessageBox.question(
            self, "Confirm Trash",
            f"Send {len(selected)} item(s) to .pearls_trash/?  They can be restored later.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        ok = sum(1 for sf in selected if self._trash.send_to_trash(sf.path))
        QMessageBox.information(self, "Done", f"Sent {ok}/{len(selected)} item(s) to trash.")
        self._scan()


# ─────────────────────────────────────────────────────────────────────────────
# Storage Report pane
# ─────────────────────────────────────────────────────────────────────────────

class _StoragePane(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker: Optional[_StorageWorker] = None
        self._data: Optional[Dict] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.dir_selector = DirectorySelectorWidget(label_text="Folder:")
        layout.addWidget(self.dir_selector)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Folder / Category", "Size", "% of Total"])
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 110)
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(120)
        layout.addWidget(self.tree, stretch=1)

        # Proportional bar
        self.bar = _StorageBar()
        layout.addWidget(self.bar)

        # Legend
        legend_row = QHBoxLayout()
        for cat in _CATEGORY_ORDER:
            swatch = QLabel("▮")
            swatch.setStyleSheet(
                f"color: {_CATEGORY_COLORS[cat].name()}; font-size: 16px;"
            )
            legend_row.addWidget(swatch)
            legend_row.addWidget(QLabel(cat.capitalize()))
            legend_row.addSpacing(6)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Storage Usage")
        self.scan_btn.setStyleSheet("padding: 8px 20px;")
        self.scan_btn.clicked.connect(self._scan)
        btn_row.addWidget(self.scan_btn)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_csv)
        btn_row.addWidget(self.export_btn)
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
        self.export_btn.setEnabled(False)
        self.tree.clear()
        self.status_label.setText("Scanning…")
        self._data = None

        self._worker = _StorageWorker(directory)
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, message: str, data):
        self.scan_btn.setEnabled(True)
        self.status_label.setText("")
        if not success:
            QMessageBox.critical(self, "Scan Error", message)
            return
        self._data = data
        self._populate(data)
        self.export_btn.setEnabled(bool(data))

    def _populate(self, data: Dict):
        self.tree.clear()
        if not data:
            self.tree.addTopLevelItem(QTreeWidgetItem(["No files found", "", ""]))
            return

        grand_total = sum(sum(cats.values()) for cats in data.values())
        if grand_total == 0:
            return

        cat_totals: Dict[str, int] = {c: 0 for c in _CATEGORY_ORDER}

        for folder, cats in sorted(
            data.items(), key=lambda kv: sum(kv[1].values()), reverse=True
        ):
            folder_total = sum(cats.values())
            pct = f"{100 * folder_total / grand_total:.1f}%"
            label = "(root files)" if folder == '__root__' else folder
            parent = QTreeWidgetItem([label, _fmt_size(folder_total), pct])
            self.tree.addTopLevelItem(parent)
            for cat in _CATEGORY_ORDER:
                sz = cats.get(cat, 0)
                if sz == 0:
                    continue
                cat_totals[cat] += sz
                child = QTreeWidgetItem([
                    f"  {cat.capitalize()}", _fmt_size(sz),
                    f"{100 * sz / grand_total:.1f}%",
                ])
                child.setForeground(
                    0, QBrush(_CATEGORY_COLORS.get(cat, _CATEGORY_COLORS['other']))
                )
                parent.addChild(child)

        total_item = QTreeWidgetItem(["TOTAL", _fmt_size(grand_total), "100%"])
        self.tree.addTopLevelItem(total_item)
        self.tree.expandAll()
        self.bar.set_data([(c, cat_totals[c]) for c in _CATEGORY_ORDER])

    def _export_csv(self):
        if not self._data:
            return
        dest_str, _ = QFileDialog.getSaveFileName(
            self, "Save Storage Report",
            str(Path(self.dir_selector.get_directory()) / "storage_report.csv"),
            "CSV Files (*.csv)",
        )
        if not dest_str:
            return
        try:
            with open(dest_str, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['Folder', 'Category', 'Size (bytes)', 'Size'])
                for folder, cats in sorted(self._data.items()):
                    for cat in _CATEGORY_ORDER:
                        sz = cats.get(cat, 0)
                        if sz:
                            w.writerow([folder, cat, sz, _fmt_size(sz)])
            QMessageBox.information(self, "Exported", f"Report saved:\n{dest_str}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Trash pane
# ─────────────────────────────────────────────────────────────────────────────

class _TrashPane(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._trash: Optional[StudioTrash] = None
        self._items: List[TrashItem] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.dir_selector = DirectorySelectorWidget(label_text="Project folder:")
        self.dir_selector.directory_changed.connect(self._load_trash)
        layout.addWidget(self.dir_selector)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Original Path", "Deleted At", "Size"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(1, 280)
        self.tree.setColumnWidth(2, 140)
        self.tree.setColumnWidth(3, 80)
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(120)
        layout.addWidget(self.tree, stretch=1)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 2px 0;")
        layout.addWidget(self.summary_label)

        btn_row = QHBoxLayout()
        self.restore_btn = QPushButton("Restore Selected")
        self.restore_btn.clicked.connect(self._restore_selected)
        btn_row.addWidget(self.restore_btn)
        self.purge_btn = QPushButton("Delete Selected Permanently")
        self.purge_btn.clicked.connect(self._purge_selected)
        btn_row.addWidget(self.purge_btn)
        self.empty_btn = QPushButton("Empty Trash")
        self.empty_btn.setStyleSheet("color: #ff5370;")
        self.empty_btn.clicked.connect(self._empty_trash)
        btn_row.addWidget(self.empty_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        self._update_buttons()

    def _load_trash(self, directory: str = ""):
        path_str = directory or self.dir_selector.get_directory()
        if not path_str:
            return
        path = Path(path_str)
        if not path.is_dir():
            return
        self._trash = StudioTrash(path)
        self._refresh()

    def _refresh(self):
        if not self._trash:
            return
        self._items = self._trash.list_trash()
        self.tree.clear()
        for item in self._items:
            orig = Path(item.original_path)
            twi = QTreeWidgetItem([
                orig.name,
                str(orig.parent),
                item.deleted_at[:19].replace('T', ' '),
                _fmt_size(item.size_bytes),
            ])
            twi.setToolTip(0, str(orig))
            self.tree.addTopLevelItem(twi)
        total_size = self._trash.total_size()
        self.summary_label.setText(
            f"{len(self._items)} item(s) in trash  |  {_fmt_size(total_size)} total"
        )
        self._update_buttons()

    def _update_buttons(self):
        has = bool(self._items)
        self.restore_btn.setEnabled(has)
        self.purge_btn.setEnabled(has)
        self.empty_btn.setEnabled(has)

    def _selected_items(self) -> List[TrashItem]:
        return [
            self._items[i]
            for i in range(self.tree.topLevelItemCount())
            if self.tree.topLevelItem(i).isSelected() and i < len(self._items)
        ]

    def _restore_selected(self):
        if not self._trash:
            return
        selected = self._selected_items()
        if not selected:
            QMessageBox.information(self, "None Selected", "Select items to restore.")
            return

        ok = 0
        renamed: List[str] = []   # items whose original location was occupied
        for item in selected:
            restored_to = self._trash.restore(item)
            if restored_to is None:
                continue
            ok += 1
            if Path(restored_to).name != Path(item.original_path).name:
                renamed.append(f"{Path(item.original_path).name} → {Path(restored_to).name}")

        msg = f"Restored {ok}/{len(selected)} item(s)."
        if renamed:
            msg += (
                "\n\nThe following item(s) were restored under a new name "
                "because the original location already contained a file:\n  • "
                + "\n  • ".join(renamed)
            )
        QMessageBox.information(self, "Restore", msg)
        self._refresh()

    def _purge_selected(self):
        if not self._trash:
            return
        selected = self._selected_items()
        if not selected:
            QMessageBox.information(self, "None Selected", "Select items to delete.")
            return
        reply = QMessageBox.question(
            self, "Permanent Delete",
            f"Permanently delete {len(selected)} item(s)? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        ok = sum(1 for item in selected if self._trash.purge(item))
        QMessageBox.information(self, "Deleted", f"Permanently deleted {ok} item(s).")
        self._refresh()

    def _empty_trash(self):
        if not self._trash or not self._items:
            return
        reply = QMessageBox.question(
            self, "Empty Trash",
            f"Permanently delete all {len(self._items)} item(s)?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for item in list(self._items):
            self._trash.purge(item)
        self._refresh()


# ─────────────────────────────────────────────────────────────────────────────
# Cold Storage Wizard pages
# ─────────────────────────────────────────────────────────────────────────────

class _SelectPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Select Folders")
        self.setSubTitle(
            "Choose the project folder to archive and where to save the output."
        )
        layout = QVBoxLayout(self)
        self.src = DirectorySelectorWidget(label_text="Project folder:")
        self.src.directory_changed.connect(self.completeChanged)
        layout.addWidget(self.src)
        self.dst = DirectorySelectorWidget(label_text="Destination:")
        self.dst.directory_changed.connect(self.completeChanged)
        layout.addWidget(self.dst)
        layout.addStretch()

    def isComplete(self) -> bool:
        src = Path(self.src.get_directory())
        dst = Path(self.dst.get_directory())
        return src.is_dir() and dst.is_dir() and src != dst

    def source_dir(self) -> Path:
        return Path(self.src.get_directory())

    def dest_dir(self) -> Path:
        return Path(self.dst.get_directory())


class _ReviewPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Review Exclusions")
        self.setSubTitle(
            "The following files will be EXCLUDED from the archive "
            "(hidden, temp, cache, and WIP markers)."
        )
        layout = QVBoxLayout(self)
        self.exclude_list = QListWidget()
        self.exclude_list.setAlternatingRowColors(True)
        layout.addWidget(self.exclude_list, stretch=1)
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("font-weight: bold; padding: 2px 0;")
        layout.addWidget(self.info_label)

    def initializePage(self):
        w: ColdStorageWizard = self.wizard()
        src = w.select_page.source_dir()
        include, exclude = _gather_files(src, [])
        w._include_files = include
        w._exclude_files = exclude

        self.exclude_list.clear()
        for fp in exclude:
            try:
                rel = str(fp.relative_to(src))
            except ValueError:
                rel = str(fp)
            self.exclude_list.addItem(rel)

        total_incl = sum(fp.stat().st_size for fp in include if fp.exists())
        self.info_label.setText(
            f"{len(include)} file(s) will be included ({_fmt_size(total_incl)})  |  "
            f"{len(exclude)} file(s) excluded"
        )


class _ConfigurePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Configure Output")
        self.setSubTitle("Choose the output format and structure.")
        layout = QFormLayout(self)

        fmt_grp = QGroupBox("Output format")
        fmt_layout = QHBoxLayout(fmt_grp)
        self.radio_folder = QRadioButton("Folder copy")
        self.radio_zip = QRadioButton("ZIP archive")
        self.radio_folder.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.radio_folder, 0)
        grp.addButton(self.radio_zip, 1)
        fmt_layout.addWidget(self.radio_folder)
        fmt_layout.addWidget(self.radio_zip)
        fmt_layout.addStretch()
        layout.addRow(fmt_grp)

        self.chk_flatten = QCheckBox("Flatten structure (all files in one folder)")
        layout.addRow(self.chk_flatten)

        self.exclude_edit = QLineEdit()
        self.exclude_edit.setPlaceholderText("e.g. *.tmp *.log (space-separated)")
        layout.addRow("Additional exclude patterns:", self.exclude_edit)

    def as_zip(self) -> bool:
        return self.radio_zip.isChecked()

    def flatten(self) -> bool:
        return self.chk_flatten.isChecked()

    def extra_excludes(self) -> List[str]:
        return [p.strip() for p in self.exclude_edit.text().split() if p.strip()]


class _ManifestPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Generate Manifest")
        self.setSubTitle("Computing MD5 checksums for all included files.")
        self._done = False
        self._worker: Optional[_ManifestWorker] = None
        layout = QVBoxLayout(self)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.log = QListWidget()
        self.log.setAlternatingRowColors(True)
        layout.addWidget(self.log, stretch=1)
        self.status_label = QLabel("Preparing…")
        layout.addWidget(self.status_label)

    def initializePage(self):
        self._done = False
        self.progress.setValue(0)
        self.log.clear()
        w: ColdStorageWizard = self.wizard()
        src = w.select_page.source_dir()
        dst = w.select_page.dest_dir()
        include = list(w._include_files)

        # Apply any extra excludes from the configure page
        extra = w.config_page.extra_excludes()
        if extra:
            extra_pats = [
                re.compile(p.replace('*', '.*'), re.IGNORECASE) for p in extra
            ]
            include = [
                fp for fp in include
                if not any(pat.search(fp.name) for pat in extra_pats)
            ]
        w._include_files = include
        self.progress.setMaximum(max(1, len(include)))

        self._worker = _ManifestWorker(src, dst, include)
        self._worker.file_hashed.connect(self._on_file)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_file(self, name: str, current: int, total: int):
        self.progress.setValue(current)
        self.status_label.setText(f"[{current}/{total}] {name}")
        item = QListWidgetItem(f"✓  {name}")
        item.setForeground(QBrush(QColor('#c3e88d')))
        self.log.addItem(item)
        self.log.scrollToBottom()

    def _on_done(self, success: bool, message: str, result):
        if success and result:
            manifest_path, manifest_data = result
            w: ColdStorageWizard = self.wizard()
            w._manifest_path = manifest_path
            w._manifest_data = manifest_data
        self.status_label.setText(f"{'✓' if success else '✗'}  {message}")
        self._done = success
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._done


class _ExecutePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Execute Archive")
        self.setSubTitle("Copying files to the destination.")
        self._done = False
        self._worker: Optional[_CopyWorker] = None
        layout = QVBoxLayout(self)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.log = QListWidget()
        self.log.setAlternatingRowColors(True)
        layout.addWidget(self.log, stretch=1)
        self.status_label = QLabel("Preparing…")
        layout.addWidget(self.status_label)

    def initializePage(self):
        self._done = False
        self.progress.setValue(0)
        self.log.clear()
        w: ColdStorageWizard = self.wizard()
        include = w._include_files
        self.progress.setMaximum(max(1, len(include)))

        self._worker = _CopyWorker(
            w.select_page.source_dir(),
            w.select_page.dest_dir(),
            include,
            w.config_page.as_zip(),
            w.config_page.flatten(),
        )
        self._worker.file_copied.connect(self._on_file)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_file(self, name: str, current: int, total: int):
        self.progress.setValue(current)
        self.status_label.setText(f"[{current}/{total}] {name}")
        self.log.addItem(f"  {name}")
        self.log.scrollToBottom()

    def _on_done(self, success: bool, message: str, result):
        w: ColdStorageWizard = self.wizard()
        w._copy_result = result
        self.status_label.setText(f"{'✓' if success else '✗'}  {message}")
        self._done = success
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._done


class _VerifyPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Verify")
        self.setSubTitle("Verifying destination files against the manifest.")
        self.setFinalPage(True)
        self._done = False
        self._worker: Optional[_VerifyWorker] = None
        layout = QVBoxLayout(self)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.log = QListWidget()
        self.log.setAlternatingRowColors(True)
        layout.addWidget(self.log, stretch=1)
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self.summary_label)

    def initializePage(self):
        self._done = False
        self.progress.setValue(0)
        self.log.clear()
        w: ColdStorageWizard = self.wizard()
        manifest_data = getattr(w, '_manifest_data', [])
        copy_result = getattr(w, '_copy_result', None)

        # ZIP output — skip per-file verify (can't easily hash inside zip without extracting)
        if w.config_page.as_zip():
            self.summary_label.setText(
                "ZIP archive created. Skipping in-archive checksum verification."
            )
            self.summary_label.setStyleSheet("font-weight: bold; padding: 4px; color: #ffcb6b;")
            self._done = True
            self.completeChanged.emit()
            return

        dest = copy_result if isinstance(copy_result, Path) and copy_result.is_dir() \
            else w.select_page.dest_dir()
        self.progress.setMaximum(max(1, len(manifest_data)))

        self._worker = _VerifyWorker(dest, manifest_data)
        self._worker.file_verified.connect(self._on_file)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_file(self, rel: str, ok: bool):
        item = QListWidgetItem(f"{'✓' if ok else '✗'}  {Path(rel).name}")
        item.setForeground(QBrush(QColor('#c3e88d' if ok else '#ff5370')))
        self.log.addItem(item)
        self.log.scrollToBottom()
        self.progress.setValue(self.progress.value() + 1)

    def _on_done(self, success: bool, message: str, results):
        passed = sum(1 for _, ok, _ in (results or []) if ok)
        total = len(results or [])
        color = '#c3e88d' if passed == total else '#ffcb6b'
        self.summary_label.setText(message)
        self.summary_label.setStyleSheet(
            f"font-weight: bold; padding: 4px; color: {color};"
        )
        self._done = True
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._done


class ColdStorageWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Archive to Cold Storage")
        self.setMinimumSize(680, 520)

        # Shared state between pages
        self._include_files: List[Path] = []
        self._exclude_files: List[Path] = []
        self._manifest_path: Optional[Path] = None
        self._manifest_data: List[dict] = []
        self._copy_result = None

        self.select_page = _SelectPage()
        self.review_page = _ReviewPage()
        self.config_page = _ConfigurePage()
        self.manifest_page = _ManifestPage()
        self.execute_page = _ExecutePage()
        self.verify_page = _VerifyPage()

        for page in (
            self.select_page, self.review_page, self.config_page,
            self.manifest_page, self.execute_page, self.verify_page,
        ):
            self.addPage(page)


# ─────────────────────────────────────────────────────────────────────────────
# Archive pane (wizard launcher)
# ─────────────────────────────────────────────────────────────────────────────

class _ArchivePane(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        desc = QLabel(
            "<b>Cold Storage Archiver</b><br><br>"
            "Archive a completed project folder to a NAS, external drive, or cloud mount "
            "with automatic file exclusion, MD5 manifest generation, and checksum verification."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        steps = QLabel(
            "The wizard will guide you through six steps:\n"
            "  1. Select source project folder and destination\n"
            "  2. Review files that will be excluded (hidden / temp / cache / WIP)\n"
            "  3. Configure output format (ZIP archive or folder copy)\n"
            "  4. Generate MANIFEST.json with MD5 checksums\n"
            "  5. Copy or zip files to the destination\n"
            "  6. Verify destination files against the manifest"
        )
        steps.setStyleSheet("color: #888; padding: 8px 16px;")
        layout.addWidget(steps)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.start_btn = QPushButton("Start Cold Storage Wizard…")
        self.start_btn.setStyleSheet(
            "padding: 10px 28px; font-weight: bold; font-size: 13px;"
        )
        self.start_btn.clicked.connect(self._launch)
        btn_row.addWidget(self.start_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

    def _launch(self):
        ColdStorageWizard(self).exec_()


# ─────────────────────────────────────────────────────────────────────────────
# NLE Backup pane
# ─────────────────────────────────────────────────────────────────────────────

class _NLEBackupPane(QWidget):
    """Backup NLE project files for any supported application."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker: Optional[_NLEBackupWorker] = None
        self._nle_checkboxes: Dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # NLE selection group
        nle_group = QGroupBox("NLE Applications to Backup")
        nle_layout = QVBoxLayout(nle_group)
        nle_layout.setSpacing(3)
        for nle_name, exts in sorted(_NLE_FORMATS.items()):
            ext_str = "  " + "  ".join(sorted(exts))
            chk = QCheckBox(f"{nle_name}{ext_str}")
            chk.setChecked(True)
            nle_layout.addWidget(chk)
            self._nle_checkboxes[nle_name] = chk
        layout.addWidget(nle_group)

        # Custom extensions
        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("Additional extensions:"))
        self.custom_ext_edit = QLineEdit()
        self.custom_ext_edit.setPlaceholderText("e.g. .rpp .als (space-separated)")
        self.custom_ext_edit.setToolTip("Extra file extensions to include, space-separated with leading dot")
        custom_row.addWidget(self.custom_ext_edit, stretch=1)
        layout.addLayout(custom_row)

        self.scan_selector = DirectorySelectorWidget(label_text="Scan folder:")
        layout.addWidget(self.scan_selector)

        self.dest_selector = DirectorySelectorWidget(label_text="Backup destination:")
        layout.addWidget(self.dest_selector)

        self.last_backup_label = QLabel("Last backup: never")
        self.last_backup_label.setStyleSheet("color: #888; font-size: 11px; padding: 2px 0;")
        layout.addWidget(self.last_backup_label)

        self.log = QListWidget()
        self.log.setAlternatingRowColors(True)
        self.log.setMinimumHeight(100)
        layout.addWidget(self.log, stretch=1)

        btn_row = QHBoxLayout()
        self.backup_btn = QPushButton("Backup Now")
        self.backup_btn.setStyleSheet("padding: 8px 20px;")
        self.backup_btn.clicked.connect(self._backup)
        btn_row.addWidget(self.backup_btn)
        self.status_label = QLabel("")
        btn_row.addWidget(self.status_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _collect_extensions(self) -> set:
        exts: set = set()
        for nle_name, chk in self._nle_checkboxes.items():
            if chk.isChecked():
                exts |= _NLE_FORMATS[nle_name]
        for token in self.custom_ext_edit.text().split():
            token = token.strip()
            if token and token.startswith('.'):
                exts.add(token.lower())
        return exts

    def _backup(self):
        scan = Path(self.scan_selector.get_directory())
        dest = Path(self.dest_selector.get_directory())
        if not scan.is_dir():
            QMessageBox.warning(self, "No Scan Folder", "Select a folder to scan.")
            return
        if not dest.is_dir():
            QMessageBox.warning(self, "No Destination", "Select a backup destination folder.")
            return
        exts = self._collect_extensions()
        if not exts:
            QMessageBox.warning(self, "No Formats", "Enable at least one NLE application.")
            return
        if self._worker and self._worker.isRunning():
            return

        self.backup_btn.setEnabled(False)
        self.status_label.setText("Backing up…")
        self._worker = _NLEBackupWorker(scan, dest, exts)
        self._worker.file_backed.connect(
            lambda name: self.status_label.setText(f"Copying {name}…")
        )
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, message: str, results):
        self.backup_btn.setEnabled(True)
        self.status_label.setText("")
        if not success:
            QMessageBox.critical(self, "Backup Failed", message)
            return

        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.last_backup_label.setText(f"Last backup: {now_str}")

        self.log.addItem(f"── Backup run: {now_str} ──")
        for r in (results or []):
            if r.get('ok'):
                item = QListWidgetItem(
                    f"  ✓  {r['name']}  →  {r['dest']}  ({_fmt_size(r['size'])})"
                )
                item.setForeground(QBrush(QColor('#c3e88d')))
            else:
                item = QListWidgetItem(f"  ✗  {r['name']}  —  {r.get('error', 'error')}")
                item.setForeground(QBrush(QColor('#ff5370')))
            self.log.addItem(item)
        self.log.scrollToBottom()

        self.config.set('nle_backup.scan_dir', self.scan_selector.get_directory())
        self.config.set('nle_backup.backup_dir', self.dest_selector.get_directory())
        self.config.set('nle_backup.last_backup', now_str)

    def load_settings(self):
        scan = self.config.get('nle_backup.scan_dir', '')
        if scan:
            self.scan_selector.set_directory(scan)
        dest = self.config.get('nle_backup.backup_dir', '')
        if dest:
            self.dest_selector.set_directory(dest)
        last = self.config.get('nle_backup.last_backup', '')
        if last:
            self.last_backup_label.setText(f"Last backup: {last}")
        enabled = self.config.get('nle_backup.enabled_nles', None)
        if enabled is not None:
            for nle_name, chk in self._nle_checkboxes.items():
                chk.setChecked(nle_name in enabled)
        custom = self.config.get('nle_backup.custom_exts', '')
        if custom:
            self.custom_ext_edit.setText(custom)

    def save_settings(self):
        scan = self.scan_selector.get_directory()
        if scan:
            self.config.set('nle_backup.scan_dir', scan)
        dest = self.dest_selector.get_directory()
        if dest:
            self.config.set('nle_backup.backup_dir', dest)
        enabled = [n for n, chk in self._nle_checkboxes.items() if chk.isChecked()]
        self.config.set('nle_backup.enabled_nles', enabled)
        self.config.set('nle_backup.custom_exts', self.custom_ext_edit.text())


# ─────────────────────────────────────────────────────────────────────────────
# Export folder watcher pane
# ─────────────────────────────────────────────────────────────────────────────

class _ExportWatcherPane(QWidget):
    _WATCH_EXTS = {'.mov', '.mp4', '.mxf', '.m4v', '.avi', '.mkv'}

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._known_files: set = set()
        self._watching = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.dir_selector = DirectorySelectorWidget(label_text="Watch folder:")
        layout.addWidget(self.dir_selector)

        opts = QGroupBox("Options")
        opts_layout = QFormLayout(opts)

        self.profile_combo = QComboBox()
        self.profile_combo.addItem("(None)")
        self.profile_combo.setToolTip(
            "When a new file arrives, its filename is checked against this profile's "
            "naming convention and any issues are logged."
        )
        opts_layout.addRow("Check against profile:", self.profile_combo)

        self.chk_validate = QCheckBox(
            "Run delivery validation on watch folder after each arrival"
        )
        opts_layout.addRow(self.chk_validate)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 3600)
        self.interval_spin.setValue(30)
        self.interval_spin.setSuffix(" seconds")
        opts_layout.addRow("Poll interval:", self.interval_spin)
        layout.addWidget(opts)

        self.log = QListWidget()
        self.log.setAlternatingRowColors(True)
        self.log.setMinimumHeight(120)
        layout.addWidget(self.log, stretch=1)

        btn_row = QHBoxLayout()
        self.status_label = QLabel("Not watching.")
        btn_row.addWidget(self.status_label, stretch=1)
        self.toggle_btn = QPushButton("Start Watching")
        self.toggle_btn.setStyleSheet("padding: 8px 20px;")
        self.toggle_btn.clicked.connect(self._toggle)
        btn_row.addWidget(self.toggle_btn)
        layout.addLayout(btn_row)

    def _load_profiles(self):
        self.profile_combo.blockSignals(True)
        current = self.profile_combo.currentText()
        self.profile_combo.clear()
        self.profile_combo.addItem("(None)")
        for p in self.config.get('naming.profiles', []):
            name = p.get('name', '')
            if name:
                self.profile_combo.addItem(name)
        idx = self.profile_combo.findText(current)
        self.profile_combo.setCurrentIndex(max(0, idx))
        self.profile_combo.blockSignals(False)

    def showEvent(self, event):
        super().showEvent(event)
        self._load_profiles()

    def _toggle(self):
        if self._watching:
            self._stop()
        else:
            self._start()

    def _start(self):
        directory = Path(self.dir_selector.get_directory())
        if not directory.is_dir():
            QMessageBox.warning(self, "No Folder", "Select a valid watch folder.")
            return
        self._known_files = {
            fp for fp in directory.rglob('*')
            if fp.is_file() and fp.suffix.lower() in self._WATCH_EXTS
        }
        self._watching = True
        self._timer.start(self.interval_spin.value() * 1000)
        self.toggle_btn.setText("Stop Watching")
        self.interval_spin.setEnabled(False)
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        self._log(
            f"[{ts}]  Started watching: {directory.name}"
            f"  ({len(self._known_files)} existing file(s) ignored)",
            '#c3e88d',
        )
        self.status_label.setText(f"Watching: {directory}")

    def _stop(self):
        self._timer.stop()
        self._watching = False
        self.toggle_btn.setText("Start Watching")
        self.interval_spin.setEnabled(True)
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        self._log(f"[{ts}]  Watching stopped.", '#888888')
        self.status_label.setText("Not watching.")

    def _poll(self):
        directory = Path(self.dir_selector.get_directory())
        if not directory.is_dir():
            self._stop()
            return
        current = {
            fp for fp in directory.rglob('*')
            if fp.is_file() and fp.suffix.lower() in self._WATCH_EXTS
        }
        new_files = current - self._known_files
        self._known_files = current
        for fp in sorted(new_files):
            self._on_arrival(fp, directory)

    def _on_arrival(self, fp: Path, watch_dir: Path):
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        try:
            size = fp.stat().st_size
        except OSError:
            size = 0
        self._log(f"[{ts}]  ▶  New file: {fp.name}  ({_fmt_size(size)})", '#82aaff')

        # Profile conformance check
        profile_name = self.profile_combo.currentText()
        if profile_name != "(None)":
            for p in self.config.get('naming.profiles', []):
                if p.get('name') == profile_name:
                    try:
                        from core.name_transform import ProductionTemplate
                        from core.linter import FilenameLint
                        template = ProductionTemplate.from_dict(p)
                        issues = FilenameLint().lint_directory(fp.parent, profile=template)
                        file_issues = [i for i in issues if i.filename == fp.name]
                        if file_issues:
                            for issue in file_issues:
                                self._log(f"       ⚠  {issue.description}", '#ffcb6b')
                        else:
                            self._log(f"       ✓  Conforms to profile '{profile_name}'", '#c3e88d')
                    except Exception:
                        pass
                    break

        # Optional delivery validation
        if self.chk_validate.isChecked():
            try:
                from core.delivery import DeliveryValidator, DeliveryProfile
                report = DeliveryValidator().validate(watch_dir, DeliveryProfile())
                color = '#c3e88d' if report.passed else '#ff5370'
                status = "PASSED" if report.passed else "FAILED"
                self._log(
                    f"       Validation {status}: {report.error_count()} error(s), "
                    f"{report.warning_count()} warning(s)",
                    color,
                )
            except Exception as exc:
                self._log(f"       Validation error: {exc}", '#ff5370')

    def _log(self, text: str, color_hex: str = '#e0e0e0'):
        item = QListWidgetItem(text)
        item.setForeground(QBrush(QColor(color_hex)))
        self.log.addItem(item)
        self.log.scrollToBottom()

    def load_settings(self):
        d = self.config.get('export_watcher.watch_dir', '')
        if d:
            self.dir_selector.set_directory(d)

    def save_settings(self):
        d = self.dir_selector.get_directory()
        if d:
            self.config.set('export_watcher.watch_dir', d)


# ─────────────────────────────────────────────────────────────────────────────
# Main StudioToolsTab
# ─────────────────────────────────────────────────────────────────────────────

class StudioToolsTab(BaseTab):
    """Studio utilities: stale files, storage report, trash, cold storage, NLE backup, export watcher."""

    def get_tab_name(self) -> str:
        return "Studio Tools"

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._inner_tabs = QTabWidget()

        self._stale_pane = _StaleFilesPane(self.config)
        self._storage_pane = _StoragePane(self.config)
        self._trash_pane = _TrashPane(self.config)
        self._archive_pane = _ArchivePane(self.config)
        self._nle_pane = _NLEBackupPane(self.config)
        self._watcher_pane = _ExportWatcherPane(self.config)

        self._inner_tabs.addTab(self._stale_pane, "Stale Files")
        self._inner_tabs.addTab(self._storage_pane, "Storage Report")
        self._inner_tabs.addTab(self._trash_pane, "Trash")
        self._inner_tabs.addTab(self._archive_pane, "Cold Storage")
        self._inner_tabs.addTab(self._nle_pane, "NLE Backup")
        self._inner_tabs.addTab(self._watcher_pane, "Export Watcher")

        layout.addWidget(self._inner_tabs)

    def load_settings(self):
        directory = self.config.get_tab_directory('studio_tools')
        if directory and Path(directory).is_dir():
            self._stale_pane.dir_selector.set_directory(directory)
            self._storage_pane.dir_selector.set_directory(directory)
            self._trash_pane.dir_selector.set_directory(directory)
            self._trash_pane._load_trash(directory)
        self._nle_pane.load_settings()
        self._watcher_pane.load_settings()

    def save_settings(self):
        directory = self._stale_pane.dir_selector.get_directory()
        if directory:
            self.config.set_tab_directory('studio_tools', directory)
        self._nle_pane.save_settings()
        self._watcher_pane.save_settings()
