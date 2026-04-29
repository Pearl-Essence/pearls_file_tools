"""Preview dialog for Pearl's File Tools.

Two-column tree (Old → New) with alternating row colors, monospace font,
a top summary bar, and visual treatment so users can scan large rename
batches without losing track of which line maps to which.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)
from typing import List, Tuple


_CHANGE_COLOR = QColor('#c3e88d')   # green — actually different
_UNCHANGED_COLOR = QColor('#888888')  # grey — no-op rows
_HIDDEN_COLOR = QColor('#ffcb6b')   # amber — name starts with '.'


class PreviewDialog(QDialog):
    """Dialog to preview filename changes before applying."""

    def __init__(self, preview_data: List[Tuple[str, str]], parent=None):
        """
        Args:
            preview_data: List of (old_name, new_name) tuples.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.preview_data = preview_data

        self.setWindowTitle("Preview Changes")
        self.setModal(True)
        self.resize(900, 560)

        self.setup_ui()
        self.populate_preview()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # ── Top summary bar ─────────────────────────────────────────────────
        changed = sum(1 for o, n in self.preview_data if o != n)
        unchanged = len(self.preview_data) - changed
        hidden = sum(1 for o, _ in self.preview_data if o.startswith('.'))
        self.summary_label = QLabel(
            f"<b>{len(self.preview_data)}</b> file(s) selected  &nbsp;|&nbsp;  "
            f"<span style='color:#c3e88d'><b>{changed}</b> will change</span>  &nbsp;|&nbsp;  "
            f"<span style='color:#888'>{unchanged} unchanged</span>"
            + (f"  &nbsp;|&nbsp;  <span style='color:#ffcb6b'>{hidden} hidden</span>"
               if hidden else "")
        )
        self.summary_label.setStyleSheet(
            "padding: 6px 8px; background-color: #2b2b2b; border-radius: 4px;"
        )
        layout.addWidget(self.summary_label)

        # ── Two-column tree (Old → New) ────────────────────────────────────
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Original", "→", "New"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        # Tighten the arrow column; let Original / New share the rest.
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.setColumnWidth(1, 24)

        mono = QFont("Menlo", 11)
        mono.setStyleHint(QFont.Monospace)
        self.tree.setFont(mono)
        self.tree.setStyleSheet(
            "QTreeWidget::item { padding: 3px 6px; }"
            "QTreeWidget::item:alternate { background-color: #2a2a2a; }"
        )
        layout.addWidget(self.tree, stretch=1)

        # ── Bottom actions ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("padding: 6px 18px;")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def populate_preview(self):
        for old_name, new_name in self.preview_data:
            changed = old_name != new_name
            is_hidden = old_name.startswith('.')

            arrow = "→" if changed else "="
            new_display = new_name if changed else "(unchanged)"

            item = QTreeWidgetItem([old_name, arrow, new_display])
            item.setTextAlignment(1, Qt.AlignCenter)

            color: QColor
            if is_hidden:
                color = _HIDDEN_COLOR
                item.setToolTip(
                    0,
                    "Hidden file (name starts with '.'). Will be skipped "
                    "unless 'Include hidden files' is ticked."
                )
            elif changed:
                color = _CHANGE_COLOR
            else:
                color = _UNCHANGED_COLOR

            for col in range(3):
                item.setForeground(col, QBrush(color))

            self.tree.addTopLevelItem(item)
