"""File list widget with checkboxes and optional metadata columns."""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QHeaderView, QLabel,
    QMenu, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

try:
    from core.file_utils import format_file_size
except ImportError:
    def format_file_size(size: int) -> str:  # type: ignore[misc]
        for unit, threshold in (('GB', 1 << 30), ('MB', 1 << 20), ('KB', 1 << 10)):
            if size >= threshold:
                return f"{size / threshold:.1f} {unit}"
        return f"{size} B"


def _fmt_duration(secs: Optional[float]) -> str:
    if secs is None:
        return '\u2014'
    total = int(secs)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class FileListWidget(QWidget):
    """Scrollable file list with checkboxes and togglable media metadata columns.

    Public API (backward-compatible):
        set_files(files, relative_to=None)
        get_selected_files() -> List[Path]
        get_all_files() -> List[Path]
        clear()
        select_all() / deselect_all() / invert_selection()

    Metadata columns (Codec, Resolution, Duration, FPS) are hidden by default.
    Right-click the column header to toggle them. When hidden, metadata appears
    in the filename cell's tooltip after background loading completes.
    """

    COL_FILENAME = 0
    COL_SIZE = 1
    COL_CODEC = 2
    COL_RESOLUTION = 3
    COL_DURATION = 4
    COL_FPS = 5

    _HEADERS = ['Filename', 'Size', 'Codec', 'Resolution', 'Duration', 'FPS']
    _META_COLS = [COL_CODEC, COL_RESOLUTION, COL_DURATION, COL_FPS]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: List[Path] = []
        self._last_clicked: Optional[int] = None
        self._metadata_worker = None
        self._setup_ui()

    # ── UI setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Controls row
        ctrl = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        ctrl.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        ctrl.addWidget(self.deselect_all_btn)

        self.invert_btn = QPushButton("Invert Selection")
        self.invert_btn.clicked.connect(self.invert_selection)
        ctrl.addWidget(self.invert_btn)

        ctrl.addStretch()
        self.count_label = QLabel("No files loaded")
        ctrl.addWidget(self.count_label)
        layout.addLayout(ctrl)

        # Table
        self.table = QTableWidget(0, len(self._HEADERS))
        self.table.setHorizontalHeaderLabels(self._HEADERS)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(self.COL_FILENAME, QHeaderView.Stretch)
        for col in (self.COL_SIZE, *self._META_COLS):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        # Metadata columns hidden by default; right-click header to toggle
        for col in self._META_COLS:
            self.table.setColumnHidden(col, True)

        hdr.setContextMenuPolicy(Qt.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._header_menu)

        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.itemChanged.connect(self._on_item_changed)

        layout.addWidget(self.table, stretch=1)
        self.setLayout(layout)

    # ── public API ────────────────────────────────────────────────────────

    def set_files(self, files: List[Path], relative_to: Optional[Path] = None):
        """Populate the list. Cancels any running metadata background load."""
        self._cancel_metadata_worker()
        self._files = list(files)
        self._last_clicked = None

        self.table.blockSignals(True)
        self.table.setRowCount(len(files))

        for row, filepath in enumerate(files):
            if relative_to:
                try:
                    display = str(filepath.relative_to(relative_to))
                except ValueError:
                    display = filepath.name
            else:
                display = filepath.name

            # Filename cell with native checkbox
            fn_item = QTableWidgetItem(display)
            fn_item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable
            )
            fn_item.setCheckState(Qt.Checked)
            fn_item.setData(Qt.UserRole, filepath)
            fn_item.setToolTip(str(filepath))
            self.table.setItem(row, self.COL_FILENAME, fn_item)

            # Size (cheap stat — loaded immediately)
            try:
                size_str = format_file_size(filepath.stat().st_size)
            except OSError:
                size_str = '\u2014'
            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, self.COL_SIZE, size_item)

            # Placeholder metadata cells
            for col in self._META_COLS:
                ph = QTableWidgetItem('\u2014')
                ph.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, ph)

        self.table.blockSignals(False)
        self._update_count()

        # Start metadata load if any column is already visible
        if any(not self.table.isColumnHidden(c) for c in self._META_COLS):
            self._start_metadata_loading()

    def get_selected_files(self) -> List[Path]:
        result = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_FILENAME)
            if item and item.checkState() == Qt.Checked:
                result.append(item.data(Qt.UserRole))
        return result

    def get_all_files(self) -> List[Path]:
        result = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_FILENAME)
            if item:
                result.append(item.data(Qt.UserRole))
        return result

    def clear(self):
        self._cancel_metadata_worker()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)
        self._files.clear()
        self._last_clicked = None
        self._update_count()

    def select_all(self):
        self._set_all(Qt.Checked)

    def deselect_all(self):
        self._set_all(Qt.Unchecked)

    def invert_selection(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_FILENAME)
            if item:
                item.setCheckState(
                    Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                )
        self.table.blockSignals(False)
        self._update_count()

    # ── metadata columns ──────────────────────────────────────────────────

    def _header_menu(self, pos):
        menu = QMenu(self)
        for col in self._META_COLS:
            action = menu.addAction(self._HEADERS[col])
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(col))
            action.triggered.connect(
                lambda checked, c=col: self._toggle_meta_col(c, checked)
            )
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def _toggle_meta_col(self, col: int, show: bool):
        self.table.setColumnHidden(col, not show)
        if show and self._files:
            self._start_metadata_loading()

    def _start_metadata_loading(self):
        self._cancel_metadata_worker()
        from workers.metadata_worker import MetadataWorker
        self._metadata_worker = MetadataWorker(list(self._files))
        self._metadata_worker.metadata_ready.connect(self._on_metadata_ready)
        self._metadata_worker.start()

    def _cancel_metadata_worker(self):
        if self._metadata_worker and self._metadata_worker.isRunning():
            self._metadata_worker.is_cancelled = True
            self._metadata_worker = None

    def _on_metadata_ready(self, filepath_str: str, info: dict):
        target = Path(filepath_str)
        for row in range(self.table.rowCount()):
            fn_item = self.table.item(row, self.COL_FILENAME)
            if not fn_item or fn_item.data(Qt.UserRole) != target:
                continue

            codec = info.get('codec') or '\u2014'
            w, h = info.get('width'), info.get('height')
            res = f"{w}\u00d7{h}" if w and h else '\u2014'
            dur = _fmt_duration(info.get('duration_secs'))
            fps_raw = info.get('fps')
            fps = f"{fps_raw:.2f}" if fps_raw else '\u2014'

            self.table.item(row, self.COL_CODEC).setText(codec)
            self.table.item(row, self.COL_RESOLUTION).setText(res)
            self.table.item(row, self.COL_DURATION).setText(dur)
            self.table.item(row, self.COL_FPS).setText(fps)

            # Enrich tooltip even when columns are hidden
            meta_parts = [p for p in (
                codec if codec != '\u2014' else None,
                res if res != '\u2014' else None,
                f"{fps_raw:.2f} fps" if fps_raw else None,
                dur if dur != '\u2014' else None,
            ) if p]
            if meta_parts:
                fn_item.setToolTip(f"{target}\n{', '.join(meta_parts)}")
            break

    # ── selection helpers ─────────────────────────────────────────────────

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != self.COL_FILENAME:
            return
        row = item.row()
        # Extend selection on shift-click
        mods = QApplication.keyboardModifiers()
        if (mods & Qt.ShiftModifier and
                self._last_clicked is not None and
                self._last_clicked != row):
            new_state = item.checkState()
            self.table.blockSignals(True)
            lo, hi = sorted((self._last_clicked, row))
            for r in range(lo, hi + 1):
                fn = self.table.item(r, self.COL_FILENAME)
                if fn:
                    fn.setCheckState(new_state)
            self.table.blockSignals(False)
        self._last_clicked = row
        self._update_count()

    def _set_all(self, state):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_FILENAME)
            if item:
                item.setCheckState(state)
        self.table.blockSignals(False)
        self._update_count()

    def _update_count(self):
        total = self.table.rowCount()
        selected = sum(
            1 for r in range(total)
            if self.table.item(r, self.COL_FILENAME) and
            self.table.item(r, self.COL_FILENAME).checkState() == Qt.Checked
        )
        self.count_label.setText(f"{selected}/{total} files selected")
