"""Normalize Incoming Files dialog for Pearl's File Tools."""

from pathlib import Path
from typing import List, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QDialogButtonBox,
)


def _strip_patterns(filename: str, patterns: List[str]) -> str:
    """Strip matching patterns from both ends of the filename stem (case-insensitive).

    Iterates until no further stripping is possible, then trims stray separators.
    Returns the original filename unchanged if the stem would become empty.
    """
    stem = Path(filename).stem
    ext = Path(filename).suffix
    changed = True
    while changed:
        changed = False
        for pat in patterns:
            if not pat:
                continue
            p_lower = pat.lower()
            s_lower = stem.lower()
            if s_lower.startswith(p_lower):
                stem = stem[len(pat):]
                changed = True
            elif s_lower.endswith(p_lower):
                stem = stem[: len(stem) - len(pat)]
                changed = True
    stem = stem.strip('_- ')
    return f"{stem}{ext}" if stem else filename


class NormalizeDialog(QDialog):
    """Preview and apply pattern-stripping to incoming filenames."""

    def __init__(self, files: List[Path], config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Normalize Incoming Files")
        self.setMinimumSize(720, 500)
        self._files = files
        self._config = config
        self._pairs: List[Tuple[Path, str]] = []
        self._setup_ui()
        self._refresh_preview()

    def _setup_ui(self):
        layout = QVBoxLayout()

        layout.addWidget(QLabel(
            "Strip common bad prefixes / suffixes from filenames.\n"
            "Only files whose names actually change are shown in the preview."
        ))

        patterns_row = QHBoxLayout()
        patterns_row.addWidget(QLabel("Patterns to strip:"))
        self.patterns_edit = QLineEdit()
        bad = self._config.get('naming.bad_patterns', [])
        self.patterns_edit.setText(', '.join(bad))
        self.patterns_edit.setPlaceholderText("e.g. _COPY, _BACKUP, Copy of ")
        self.patterns_edit.textChanged.connect(self._refresh_preview)
        patterns_row.addWidget(self.patterns_edit, stretch=1)
        layout.addLayout(patterns_row)

        self.save_chk = QCheckBox("Save these patterns to config for future use")
        self.save_chk.setChecked(True)
        layout.addWidget(self.save_chk)

        layout.addWidget(QLabel("Preview:"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Original Name", "New Name"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.count_label = QLabel("")
        layout.addWidget(self.count_label)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Apply Renames")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.setLayout(layout)

    def _get_patterns(self) -> List[str]:
        return [p.strip() for p in self.patterns_edit.text().split(',') if p.strip()]

    def _refresh_preview(self):
        patterns = self._get_patterns()
        self._pairs = []
        for f in self._files:
            new_name = _strip_patterns(f.name, patterns)
            if new_name != f.name:
                self._pairs.append((f, new_name))

        self.table.setRowCount(len(self._pairs))
        for row, (path, new_name) in enumerate(self._pairs):
            self.table.setItem(row, 0, QTableWidgetItem(path.name))
            self.table.setItem(row, 1, QTableWidgetItem(new_name))

        if self._pairs:
            self.count_label.setText(f"{len(self._pairs)} file(s) will be renamed.")
        else:
            self.count_label.setText("No files match the current patterns.")

    def _on_accept(self):
        if self.save_chk.isChecked():
            self._config.set('naming.bad_patterns', self._get_patterns())
        self.accept()

    def get_rename_pairs(self) -> List[Tuple[Path, str]]:
        return self._pairs
