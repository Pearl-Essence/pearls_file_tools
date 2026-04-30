"""Naming profile management dialog for Pearl's File Tools."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QGroupBox, QFormLayout, QLineEdit, QLabel, QDialogButtonBox,
    QMessageBox,
)
from core.name_transform import ProductionTemplate


class ProfileDialog(QDialog):
    """Create, edit, and delete naming profiles."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._profiles: list = self._load_profiles()
        self._active_name: str = config.get('naming.active_profile') or ''
        self.setWindowTitle("Manage Naming Profiles")
        self.setMinimumSize(640, 420)
        self._setup_ui()
        self._populate_list()

    # ── persistence ───────────────────────────────────────────────────────

    def _load_profiles(self):
        raw = self.config.get('naming.profiles', [])
        return [ProductionTemplate.from_dict(d) for d in raw]

    def _save_profiles(self):
        self.config.set('naming.profiles', [p.to_dict() for p in self._profiles])
        self.config.set('naming.active_profile',
                        self._active_name if self._active_name else None)

    # ── UI setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        main_layout = QHBoxLayout()

        # Left column — list
        left = QVBoxLayout()
        left.addWidget(QLabel("Profiles:"))
        self.profile_list = QListWidget()
        self.profile_list.currentRowChanged.connect(self._on_selection_changed)
        left.addWidget(self.profile_list, stretch=1)

        btn_row = QHBoxLayout()
        self.new_btn = QPushButton("New")
        self.delete_btn = QPushButton("Delete")
        self.set_active_btn = QPushButton("Set Active")
        self.new_btn.clicked.connect(self._new_profile)
        self.delete_btn.clicked.connect(self._delete_profile)
        self.set_active_btn.clicked.connect(self._set_active)
        btn_row.addWidget(self.new_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(self.set_active_btn)
        left.addLayout(btn_row)
        main_layout.addLayout(left, stretch=1)

        # Right column — editor
        right = QVBoxLayout()
        editor = QGroupBox("Edit Profile")
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.name_edit = QLineEdit()
        self.tokens_edit = QLineEdit()
        self.tokens_edit.setPlaceholderText("e.g. PROJECT, EP, SHOT, DESC, VER")
        self.separator_edit = QLineEdit("_")
        self.separator_edit.setMaximumWidth(60)
        self.version_edit = QLineEdit("v{:02d}")
        self.episode_edit = QLineEdit("EP{:02d}")

        form.addRow("Name:", self.name_edit)
        form.addRow("Tokens (comma-separated):", self.tokens_edit)
        form.addRow("Separator:", self.separator_edit)
        form.addRow("Version format:", self.version_edit)
        form.addRow("Episode format:", self.episode_edit)

        hint = QLabel(
            "<small>Version / episode format strings use Python format syntax: "
            "<code>v{:02d}</code> → <code>v01</code>, "
            "<code>EP{:03d}</code> → <code>EP001</code></small>"
        )
        hint.setWordWrap(True)
        form.addRow("", hint)

        editor.setLayout(form)
        right.addWidget(editor)

        save_btn = QPushButton("Save Changes to Profile")
        save_btn.clicked.connect(self._save_current)
        right.addWidget(save_btn)
        right.addStretch()
        main_layout.addLayout(right, stretch=2)

        outer = QVBoxLayout()
        outer.addLayout(main_layout)
        close_btns = QDialogButtonBox(QDialogButtonBox.Close)
        close_btns.rejected.connect(self.accept)
        outer.addWidget(close_btns)
        self.setLayout(outer)

    # ── helpers ───────────────────────────────────────────────────────────

    def _populate_list(self):
        self.profile_list.clear()
        for p in self._profiles:
            label = f"\u2605 {p.name}" if p.name == self._active_name else p.name
            self.profile_list.addItem(label)
        if self._profiles:
            self.profile_list.setCurrentRow(0)

    def _on_selection_changed(self, row: int):
        if 0 <= row < len(self._profiles):
            p = self._profiles[row]
            self.name_edit.setText(p.name)
            self.tokens_edit.setText(', '.join(p.tokens))
            self.separator_edit.setText(p.separator)
            self.version_edit.setText(p.version_format)
            self.episode_edit.setText(p.episode_format)

    def _save_current(self):
        row = self.profile_list.currentRow()
        if row < 0:
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Name Required", "Profile name cannot be empty.")
            return
        tokens = [t.strip() for t in self.tokens_edit.text().split(',') if t.strip()]
        if not tokens:
            QMessageBox.warning(self, "Tokens Required", "At least one token is required.")
            return
        old_name = self._profiles[row].name
        self._profiles[row] = ProductionTemplate(
            name=name,
            tokens=tokens,
            separator=self.separator_edit.text() or '_',
            version_format=self.version_edit.text() or 'v{:02d}',
            episode_format=self.episode_edit.text() or 'EP{:02d}',
        )
        if self._active_name == old_name:
            self._active_name = name
        self._save_profiles()
        self._populate_list()
        self.profile_list.setCurrentRow(row)

    def _new_profile(self):
        p = ProductionTemplate(name=f"Profile {len(self._profiles) + 1}")
        self._profiles.append(p)
        self._save_profiles()
        self._populate_list()
        self.profile_list.setCurrentRow(len(self._profiles) - 1)

    def _delete_profile(self):
        row = self.profile_list.currentRow()
        if row < 0:
            return
        name = self._profiles[row].name
        reply = QMessageBox.question(
            self, "Delete Profile", f"Delete profile '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if self._active_name == name:
            self._active_name = ''
        del self._profiles[row]
        self._save_profiles()
        self._populate_list()

    def _set_active(self):
        row = self.profile_list.currentRow()
        if row < 0:
            return
        self._active_name = self._profiles[row].name
        self._save_profiles()
        self._populate_list()
        # Keep selection on the same row
        self.profile_list.setCurrentRow(row)
