"""Rename history viewer dialog for Pearl's File Tools."""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QLabel, QAbstractItemView, QMessageBox)
from PyQt5.QtCore import Qt, QTimer


class HistoryDialog(QDialog):
    """Searchable table of past rename operations sourced from SQLite history."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename History")
        self.resize(900, 550)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._run_search)
        self._setup_ui()
        self._load_recent()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Search bar
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by old or new path…")
        self.search_input.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_input, stretch=1)

        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.clicked.connect(self._clear_history)
        search_row.addWidget(self.clear_btn)
        layout.addLayout(search_row)

        # Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Old Name", "New Name", "Type"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.status_label)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _load_recent(self):
        try:
            from core.history import RenameHistory
            records = RenameHistory().get_recent(500)
            self._populate(records)
        except Exception as e:
            self.status_label.setText(f"Could not load history: {e}")

    def _on_search_changed(self):
        self._search_timer.start(250)

    def _run_search(self):
        query = self.search_input.text().strip()
        try:
            from core.history import RenameHistory
            records = RenameHistory().search(query) if query else RenameHistory().get_recent(500)
            self._populate(records)
        except Exception as e:
            self.status_label.setText(f"Search error: {e}")

    def _populate(self, records):
        self.table.setRowCount(0)
        for row in records:
            r = self.table.rowCount()
            self.table.insertRow(r)
            # Show only the filename portion for readability; full path in tooltip
            old_path = row.get('old_path', '')
            new_path = row.get('new_path', '')
            old_item = QTableWidgetItem(old_path.split('/')[-1].split('\\')[-1])
            old_item.setToolTip(old_path)
            new_item = QTableWidgetItem(new_path.split('/')[-1].split('\\')[-1])
            new_item.setToolTip(new_path)
            self.table.setItem(r, 0, QTableWidgetItem(row.get('timestamp', '')))
            self.table.setItem(r, 1, old_item)
            self.table.setItem(r, 2, new_item)
            self.table.setItem(r, 3, QTableWidgetItem(row.get('operation_type', '')))
        count = self.table.rowCount()
        self.status_label.setText(f"{count} record{'s' if count != 1 else ''}")

    def _clear_history(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Delete all rename history records? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                from core.history import RenameHistory
                RenameHistory().clear()
                self.table.setRowCount(0)
                self.status_label.setText("History cleared.")
            except Exception as e:
                self.status_label.setText(f"Error: {e}")
