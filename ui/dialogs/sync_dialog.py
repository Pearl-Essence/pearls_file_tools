"""Multi-site Sync Check dialog for Pearl's File Tools."""

import datetime
import shutil
import sys
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal, QDate
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QCheckBox, QDateEdit,
    QMenu, QAction, QSizePolicy, QApplication, QMessageBox,
)

from core.sync_check import SyncEntry, SyncReport, compare_directories
from ui.widgets.directory_selector import DirectorySelectorWidget
from workers.base_worker import BaseWorker


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _SyncWorker(BaseWorker):
    """Run compare_directories in a background thread."""

    finished = pyqtSignal(bool, str, object)   # shadows BaseWorker.finished

    def __init__(self, dir_a: Path, dir_b: Path, since: Optional[datetime.datetime]):
        super().__init__()
        self._dir_a = dir_a
        self._dir_b = dir_b
        self._since = since

    def emit_finished(self, success: bool, message: str, result=None):
        self.finished.emit(success, message, result)

    def run(self):
        try:
            report = compare_directories(self._dir_a, self._dir_b, self._since)
            self.emit_finished(True, "Done", report)
        except Exception as exc:
            self.emit_finished(False, str(exc), None)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

_STATUS_META = {
    'modified_both': ("Modified in Both",  '#e07830'),
    'a_newer':       ("A is Newer",        '#4080d0'),
    'b_newer':       ("B is Newer",        '#30b8c0'),
    'a_only':        ("Only in A",         '#4ec94e'),
    'b_only':        ("Only in B",         '#d04040'),
}

_STATUS_ORDER = ['modified_both', 'a_newer', 'b_newer', 'a_only', 'b_only']


def _fmt_size(n: int) -> str:
    if n == 0:
        return ''
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


def _fmt_mtime(ts: float) -> str:
    if ts == 0.0:
        return ''
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')


class SyncDialog(QDialog):
    """Diff-style dialog for comparing two directory trees."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._worker: Optional[_SyncWorker] = None
        self._report: Optional[SyncReport] = None

        self.setWindowTitle("Multi-site Sync Check")
        self.resize(900, 620)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # ---- Site selectors --------------------------------------------
        self._sel_a = DirectorySelectorWidget("Site A:", parent=self)
        self._sel_b = DirectorySelectorWidget("Site B:", parent=self)
        root.addWidget(self._sel_a)
        root.addWidget(self._sel_b)

        # ---- Since filter -----------------------------------------------
        since_row = QHBoxLayout()
        self._since_cb = QCheckBox("Only show changes since:")
        since_row.addWidget(self._since_cb)
        self._since_date = QDateEdit()
        self._since_date.setCalendarPopup(True)
        self._since_date.setDate(QDate.currentDate().addDays(-7))
        self._since_date.setEnabled(False)
        self._since_cb.toggled.connect(self._since_date.setEnabled)
        since_row.addWidget(self._since_date)

        since_row.addStretch()

        self._compare_btn = QPushButton("Compare")
        self._compare_btn.clicked.connect(self._start_compare)
        since_row.addWidget(self._compare_btn)
        root.addLayout(since_row)

        # ---- Results tree -----------------------------------------------
        self._tree = QTreeWidget()
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(
            ["File", "Status", "Size A", "Size B", "Modified A", "Modified B"]
        )
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, self._tree.header().Stretch)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        root.addWidget(self._tree, stretch=1)

        # ---- Status + Close --------------------------------------------
        bottom = QHBoxLayout()
        self._status_label = QLabel("Select two directories and click Compare.")
        bottom.addWidget(self._status_label, stretch=1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

    # ------------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------------

    def _start_compare(self):
        dir_a = Path(self._sel_a.get_directory())
        dir_b = Path(self._sel_b.get_directory())

        if not dir_a.is_dir():
            self._status_label.setText("Site A is not a valid directory.")
            return
        if not dir_b.is_dir():
            self._status_label.setText("Site B is not a valid directory.")
            return

        since: Optional[datetime.datetime] = None
        if self._since_cb.isChecked():
            qd = self._since_date.date()
            since = datetime.datetime(qd.year(), qd.month(), qd.day())

        self._compare_btn.setEnabled(False)
        self._status_label.setText("Scanning…")
        self._tree.clear()

        self._worker = _SyncWorker(dir_a, dir_b, since)
        self._worker.finished.connect(self._on_compare_done)
        self._worker.start()

    def _on_compare_done(self, success: bool, message: str, result):
        self._compare_btn.setEnabled(True)
        if not success:
            self._status_label.setText(f"Error: {message}")
            return

        self._report = result
        self._populate_tree(result)
        total = len(result.entries)
        self._status_label.setText(
            f"Found {total} difference(s).  Generated {result.generated.strftime('%H:%M:%S')}"
        )

    def _populate_tree(self, report: SyncReport):
        self._tree.clear()
        for status_key in _STATUS_ORDER:
            entries = report.by_status(status_key)
            if not entries:
                continue
            label, color = _STATUS_META[status_key]
            group = QTreeWidgetItem(self._tree, [f"{label} ({len(entries)})"])
            group.setExpanded(True)
            qcol = QColor(color)
            for col in range(6):
                group.setForeground(col, qcol)

            for entry in entries:
                child = QTreeWidgetItem(group)
                child.setText(0, entry.rel_path)
                child.setText(1, label)
                child.setText(2, _fmt_size(entry.size_a))
                child.setText(3, _fmt_size(entry.size_b))
                child.setText(4, _fmt_mtime(entry.mtime_a))
                child.setText(5, _fmt_mtime(entry.mtime_b))
                child.setForeground(1, qcol)
                # Store SyncEntry for context menu
                child.setData(0, Qt.UserRole, entry)

        self._tree.resizeColumnToContents(1)
        self._tree.resizeColumnToContents(2)
        self._tree.resizeColumnToContents(3)
        self._tree.resizeColumnToContents(4)
        self._tree.resizeColumnToContents(5)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return
        entry: Optional[SyncEntry] = item.data(0, Qt.UserRole)
        if entry is None:
            return  # group header

        menu = QMenu(self)

        keep_a = QAction("Keep A  (copy A → B)", self)
        keep_a.triggered.connect(lambda: self._keep_a(entry, item))
        keep_a.setEnabled(entry.path_a is not None and self._report is not None)
        menu.addAction(keep_a)

        keep_b = QAction("Keep B  (copy B → A)", self)
        keep_b.triggered.connect(lambda: self._keep_b(entry, item))
        keep_b.setEnabled(entry.path_b is not None and self._report is not None)
        menu.addAction(keep_b)

        skip = QAction("Skip", self)
        skip.triggered.connect(lambda: self._remove_item(item))
        menu.addAction(skip)

        menu.addSeparator()

        open_in_finder = QAction(
            "Open in Finder" if sys.platform == 'darwin' else "Open in Explorer", self
        )
        open_in_finder.triggered.connect(lambda: self._open_in_finder(entry))
        menu.addAction(open_in_finder)

        menu.exec_(self._tree.viewport().mapToGlobal(pos))

    def _keep_a(self, entry: SyncEntry, item: QTreeWidgetItem):
        if self._report is None or entry.path_a is None:
            return
        dest = self._report.dir_b / entry.rel_path
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry.path_a, dest)
            self._remove_item(item)
        except Exception as exc:
            QMessageBox.warning(self, "Copy Failed", str(exc))

    def _keep_b(self, entry: SyncEntry, item: QTreeWidgetItem):
        if self._report is None or entry.path_b is None:
            return
        dest = self._report.dir_a / entry.rel_path
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry.path_b, dest)
            self._remove_item(item)
        except Exception as exc:
            QMessageBox.warning(self, "Copy Failed", str(exc))

    def _remove_item(self, item: QTreeWidgetItem):
        parent = item.parent()
        if parent is None:
            idx = self._tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self._tree.takeTopLevelItem(idx)
        else:
            parent.removeChild(item)
            # Update group header count
            remaining = parent.childCount()
            text = parent.text(0)
            import re
            new_text = re.sub(r'\(\d+\)', f'({remaining})', text)
            parent.setText(0, new_text)
            if remaining == 0:
                idx = self._tree.indexOfTopLevelItem(parent)
                if idx >= 0:
                    self._tree.takeTopLevelItem(idx)

    def _open_in_finder(self, entry: SyncEntry):
        path = entry.path_a or entry.path_b
        if path is None:
            return
        import subprocess
        if sys.platform == 'darwin':
            subprocess.run(['open', '-R', str(path)], check=False)
        elif sys.platform == 'win32':
            subprocess.run(['explorer', '/select,', str(path)], check=False)
        else:
            subprocess.run(['xdg-open', str(path.parent)], check=False)
