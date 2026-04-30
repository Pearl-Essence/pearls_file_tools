"""Watch Folder Manager dialog for Pearl's File Tools."""

import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QListWidget, QListWidgetItem,
    QComboBox, QCheckBox, QFileDialog, QWidget, QSizePolicy,
    QHeaderView, QAbstractItemView,
)

from core.watch_service import HAS_WATCHDOG, WatchRule
from workers.watch_worker import WatchWorker


class WatchManagerDialog(QDialog):
    """Dialog for managing watch-folder rules and viewing the arrival log."""

    POLL_INTERVAL = 30  # seconds — used when watchdog is absent

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._worker: Optional[WatchWorker] = None
        self._update_indicator_cb = None  # callable(bool) injected by main window

        self.setWindowTitle("Watch Folder Manager")
        self.resize(780, 560)
        self._setup_ui()
        self.load_rules()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # ---- Rules table ------------------------------------------------
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Watch Folder", "Profile", "Enabled"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(self._table)

        # ---- Table buttons ----------------------------------------------
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Folder")
        add_btn.clicked.connect(self._add_rule)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ---- Watchdog status label --------------------------------------
        if HAS_WATCHDOG:
            status_text = "watchdog installed — real-time monitoring"
            status_color = "#4ec94e"
        else:
            status_text = (
                f"watchdog not installed — using polling ({self.POLL_INTERVAL}s interval)"
            )
            status_color = "#e0a030"

        wd_label = QLabel(status_text)
        wd_label.setStyleSheet(f"color: {status_color}; padding: 4px;")
        root.addWidget(wd_label)

        # ---- Arrival log ------------------------------------------------
        log_label = QLabel("Arrival Log:")
        root.addWidget(log_label)

        self._log = QListWidget()
        self._log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._log, stretch=1)

        # ---- Bottom bar -------------------------------------------------
        bottom = QHBoxLayout()

        self._start_stop_btn = QPushButton("Start Watching")
        self._start_stop_btn.setCheckable(True)
        self._start_stop_btn.clicked.connect(self._toggle_watching)
        bottom.addWidget(self._start_stop_btn)

        self._dot_label = QLabel("●  Not watching")
        self._dot_label.setStyleSheet("color: grey; font-size: 14px;")
        bottom.addWidget(self._dot_label)

        bottom.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.hide)
        bottom.addWidget(close_btn)

        root.addLayout(bottom)

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def _profiles(self) -> List[str]:
        """Return profile names from config."""
        raw = self._config.get('naming.profiles', [])
        names: List[str] = []
        for p in raw:
            if isinstance(p, dict):
                names.append(p.get('name', ''))
            elif isinstance(p, str):
                names.append(p)
        return [n for n in names if n]

    def _add_rule(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Watch Folder", str(Path.home())
        )
        if not directory:
            return
        self._insert_row(directory, '', True)

    def _remove_selected(self):
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            self._table.removeRow(row)

    def _insert_row(self, watch_dir: str, profile_name: str, enabled: bool):
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Column 0: folder path + browse button in a widget
        folder_widget = QWidget()
        folder_layout = QHBoxLayout(folder_widget)
        folder_layout.setContentsMargins(2, 2, 2, 2)
        folder_label = QLabel(watch_dir)
        folder_label.setToolTip(watch_dir)
        folder_layout.addWidget(folder_label, stretch=1)
        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(28)

        def make_browse(lbl: QLabel):
            def browse():
                d = QFileDialog.getExistingDirectory(
                    self, "Select Watch Folder", lbl.text() or str(Path.home())
                )
                if d:
                    lbl.setText(d)
                    lbl.setToolTip(d)
            return browse

        browse_btn.clicked.connect(make_browse(folder_label))
        folder_layout.addWidget(browse_btn)
        self._table.setCellWidget(row, 0, folder_widget)

        # Column 1: profile combo
        combo = QComboBox()
        combo.addItem("")  # no profile
        for name in self._profiles():
            combo.addItem(name)
        idx = combo.findText(profile_name)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        self._table.setCellWidget(row, 1, combo)

        # Column 2: enabled checkbox (centered)
        check_widget = QWidget()
        check_layout = QHBoxLayout(check_widget)
        check_layout.setContentsMargins(0, 0, 0, 0)
        check_layout.setAlignment(Qt.AlignCenter)
        cb = QCheckBox()
        cb.setChecked(enabled)
        check_layout.addWidget(cb)
        self._table.setCellWidget(row, 2, check_widget)

        self._table.setRowHeight(row, 32)

    def _folder_label_for_row(self, row: int) -> Optional[QLabel]:
        widget = self._table.cellWidget(row, 0)
        if widget is None:
            return None
        for child in widget.findChildren(QLabel):
            return child
        return None

    def _combo_for_row(self, row: int) -> Optional[QComboBox]:
        return self._table.cellWidget(row, 1)

    def _checkbox_for_row(self, row: int) -> Optional[QCheckBox]:
        widget = self._table.cellWidget(row, 2)
        if widget is None:
            return None
        for child in widget.findChildren(QCheckBox):
            return child
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_rules(self):
        """Populate table from config."""
        self._table.setRowCount(0)
        raw_rules = self._config.get('watch.rules', [])
        for r in raw_rules:
            if isinstance(r, dict):
                self._insert_row(
                    r.get('watch_dir', ''),
                    r.get('profile_name', ''),
                    bool(r.get('enabled', True)),
                )

    def save_rules(self):
        """Persist current table rows to config."""
        rules = []
        for row in range(self._table.rowCount()):
            lbl = self._folder_label_for_row(row)
            combo = self._combo_for_row(row)
            cb = self._checkbox_for_row(row)
            watch_dir = lbl.text() if lbl else ''
            profile_name = combo.currentText() if combo else ''
            enabled = cb.isChecked() if cb else True
            if watch_dir:
                rules.append({
                    'watch_dir': watch_dir,
                    'profile_name': profile_name,
                    'enabled': enabled,
                })
        self._config.set('watch.rules', rules)
        self._config.save_to_file()

    # ------------------------------------------------------------------
    # Watch toggle
    # ------------------------------------------------------------------

    def _build_rules(self) -> List[WatchRule]:
        rules: List[WatchRule] = []
        for row in range(self._table.rowCount()):
            lbl = self._folder_label_for_row(row)
            combo = self._combo_for_row(row)
            cb = self._checkbox_for_row(row)
            watch_dir = lbl.text() if lbl else ''
            profile_name = combo.currentText() if combo else ''
            enabled = cb.isChecked() if cb else True
            if watch_dir:
                rules.append(WatchRule(watch_dir, profile_name, enabled))
        return rules

    def _toggle_watching(self, checked: bool):
        if checked:
            self._start_watching()
        else:
            self._stop_watching()

    def _start_watching(self):
        self.save_rules()
        rules = self._build_rules()

        self._worker = WatchWorker(rules, self.POLL_INTERVAL)
        self._worker.file_arrived.connect(self._on_arrival)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        self._dot_label.setText("●  Watching")
        self._dot_label.setStyleSheet("color: #4ec94e; font-size: 14px;")
        self._start_stop_btn.setText("Stop Watching")
        if self._update_indicator_cb:
            self._update_indicator_cb(True)

    def _stop_watching(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            # worker calls emit_finished when done; we update UI there

    def _on_worker_finished(self, success: bool, message: str, result):
        self._dot_label.setText("●  Not watching")
        self._dot_label.setStyleSheet("color: grey; font-size: 14px;")
        self._start_stop_btn.setText("Start Watching")
        self._start_stop_btn.setChecked(False)
        if self._update_indicator_cb:
            self._update_indicator_cb(False)

    # ------------------------------------------------------------------
    # Arrival handler
    # ------------------------------------------------------------------

    def _on_arrival(self, path_str: str, profile_name: str):
        path = Path(path_str)
        ts = datetime.now().strftime('%H:%M:%S')
        label = f"[{ts}] \u25b6 {path.name}"
        if profile_name:
            label += f"  ({profile_name})"

        item = QListWidgetItem(label)
        item.setForeground(QColor('#4ec94e'))
        self._log.addItem(item)
        self._log.scrollToBottom()

        # Lint check if a profile is set
        if profile_name:
            try:
                from core.linter import FilenameLint
                lint = FilenameLint()
                issues = lint.lint_directory(path.parent)
                file_issues = [i for i in issues if i.filename == path.name]
                for issue in file_issues:
                    warn_item = QListWidgetItem(
                        f"    \u26a0 {issue.issue_type}: {issue.description}"
                    )
                    warn_item.setForeground(QColor('#e0c030'))
                    self._log.addItem(warn_item)
                    self._log.scrollToBottom()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        # Refresh profile combos when dialog is shown
        for row in range(self._table.rowCount()):
            combo = self._combo_for_row(row)
            if combo is None:
                continue
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            for name in self._profiles():
                combo.addItem(name)
            idx = combo.findText(current)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)

    def closeEvent(self, event):
        # Hide rather than destroy so a running worker is preserved
        event.ignore()
        self.hide()
