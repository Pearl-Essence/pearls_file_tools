"""Filename lint-results dialog for Pearl's File Tools."""

from pathlib import Path
from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

from core.linter import LintIssue, ISSUE_LABELS

_SEVERITY_ORDER = [
    'illegal_char', 'reserved_name', 'too_long',
    'case_duplicate', 'wip_flag', 'profile_mismatch',
]


class LintDialog(QDialog):
    """Non-modal, read-only dialog showing lint results for a directory."""

    def __init__(self, directory: Path, issues: List[LintIssue], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Lint Results")
        self.setMinimumSize(720, 420)
        self._build_ui(directory, issues)

    def _build_ui(self, directory: Path, issues: List[LintIssue]):
        layout = QVBoxLayout()

        count = len(issues)
        summary_text = (
            f"<b>{count} issue{'s' if count != 1 else ''}</b> found in "
            f"<code>{directory}</code>"
        )
        summary = QLabel(summary_text)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        if not issues:
            layout.addWidget(QLabel("\u2714 No issues found. All filenames look clean."))
        else:
            sorted_issues = sorted(
                issues,
                key=lambda x: (_SEVERITY_ORDER.index(x.issue_type)
                               if x.issue_type in _SEVERITY_ORDER else 99,
                               x.filename),
            )
            table = QTableWidget(len(sorted_issues), 3)
            table.setHorizontalHeaderLabels(["Filename", "Issue", "Description"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setAlternatingRowColors(True)

            for row, issue in enumerate(sorted_issues):
                table.setItem(row, 0, QTableWidgetItem(issue.filename))
                label = ISSUE_LABELS.get(issue.issue_type, issue.issue_type)
                table.setItem(row, 1, QTableWidgetItem(label))
                table.setItem(row, 2, QTableWidgetItem(issue.description))

            layout.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)
