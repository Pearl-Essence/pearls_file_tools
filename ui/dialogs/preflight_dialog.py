"""Pre-flight conflict check dialog for Pearl's File Tools."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)


@dataclass
class Conflict:
    filename: str
    existing_path: Path
    incoming_path: Path
    conflict_type: str  # 'already_exists' | 'name_collision'


def check_conflicts(groups: Dict[str, List[Path]], root: Path) -> List[Conflict]:
    """Return a list of Conflict objects for the proposed organize operation.

    Checks:
    - Target file already exists on disk (and is a different file)
    - Case-insensitive name collision within the same destination folder
    """
    conflicts: List[Conflict] = []

    for group_name, files in groups.items():
        target_dir = root / group_name

        # Track names we've already seen within this group (case-insensitive)
        seen_lower: Dict[str, Path] = {}

        for file_path in files:
            target_file = target_dir / file_path.name

            # File already exists at destination (and isn't itself)
            if target_file.exists() and target_file.resolve() != file_path.resolve():
                conflicts.append(Conflict(
                    filename=file_path.name,
                    existing_path=target_file,
                    incoming_path=file_path,
                    conflict_type='already_exists',
                ))

            # Case-insensitive duplicate within the same destination folder
            key = file_path.name.lower()
            if key in seen_lower:
                conflicts.append(Conflict(
                    filename=file_path.name,
                    existing_path=seen_lower[key],
                    incoming_path=file_path,
                    conflict_type='name_collision',
                ))
            else:
                seen_lower[key] = file_path

    return conflicts


class PreflightDialog(QDialog):
    """Modal dialog showing pre-flight conflict checks before an organize operation.

    After exec_(), call get_actions() to retrieve the user's per-file choices.
    Returns QDialog.Rejected if the user cancels (operation should be aborted).
    """

    ACTIONS = ['Rename with counter', 'Overwrite', 'Skip']

    def __init__(self, conflicts: List[Conflict], parent=None):
        super().__init__(parent)
        self.conflicts = conflicts
        self.combos: List[QComboBox] = []
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Pre-flight Check — Conflicts Detected")
        self.setMinimumSize(900, 420)
        layout = QVBoxLayout()

        summary = QLabel(
            f"<b>{len(self.conflicts)} conflict(s) detected.</b>  "
            "Choose an action for each, or use \"Apply to all\" then click OK to proceed."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        # Conflict table
        self.table = QTableWidget(len(self.conflicts), 4)
        self.table.setHorizontalHeaderLabels(
            ["Filename", "Existing Location", "Incoming", "Action"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        for row, conflict in enumerate(self.conflicts):
            self.table.setItem(row, 0, QTableWidgetItem(conflict.filename))
            existing_item = QTableWidgetItem(str(conflict.existing_path))
            existing_item.setToolTip(str(conflict.existing_path))
            self.table.setItem(row, 1, existing_item)
            incoming_item = QTableWidgetItem(str(conflict.incoming_path))
            incoming_item.setToolTip(str(conflict.incoming_path))
            self.table.setItem(row, 2, incoming_item)

            combo = QComboBox()
            combo.addItems(self.ACTIONS)
            self.table.setCellWidget(row, 3, combo)
            self.combos.append(combo)

        layout.addWidget(self.table)

        # Apply-to-all controls
        apply_group = QGroupBox("Apply to all conflicts")
        apply_layout = QHBoxLayout()
        self.apply_all_combo = QComboBox()
        self.apply_all_combo.addItems(self.ACTIONS)
        apply_layout.addWidget(self.apply_all_combo)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply_to_all)
        apply_layout.addWidget(apply_btn)
        apply_layout.addStretch()
        apply_group.setLayout(apply_layout)
        layout.addWidget(apply_group)

        # OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _apply_to_all(self):
        action = self.apply_all_combo.currentText()
        for combo in self.combos:
            combo.setCurrentText(action)

    def get_actions(self) -> Dict[str, str]:
        """Return {filename: chosen_action} for every conflict row."""
        return {
            self.conflicts[i].filename: self.combos[i].currentText()
            for i in range(len(self.conflicts))
        }
