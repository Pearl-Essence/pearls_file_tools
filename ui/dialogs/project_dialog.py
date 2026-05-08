"""Project create/edit dialog for Pearl Post Suite."""

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout,
)

from models.project import Project
from ui.widgets.path_card import PathCard


class ProjectDialog(QDialog):
    """Create or edit a Project."""

    # Keys that appear as PathCards
    PATH_KEYS = [
        ("ingest_source",  "INGEST SOURCE"),
        ("ingest_dest",    "INGEST DESTINATION"),
        ("mirror_dest",    "MIRROR DESTINATION"),
        ("export_output",  "EXPORT OUTPUT"),
        ("media_folder",   "MEDIA FOLDER"),
    ]

    def __init__(self, project=None, parent=None):
        """
        Args:
            project: Existing Project to edit, or None for new.
            parent:  Parent widget.
        """
        super().__init__(parent)
        self.project = project
        self.result_project = None
        self.setWindowTitle("Edit Project" if project else "New Project")
        self.setModal(True)
        self.resize(560, 520)
        self._build()
        if project:
            self._populate(project)

    def _build(self):
        layout = QVBoxLayout(self)

        # Identity
        id_group = QGroupBox("Project")
        form = QFormLayout()
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("e.g. ACME Commercial 2026")
        form.addRow("Name:", self.edit_name)

        self.edit_desc = QTextEdit()
        self.edit_desc.setPlaceholderText("Optional description…")
        self.edit_desc.setMaximumHeight(60)
        form.addRow("Description:", self.edit_desc)
        id_group.setLayout(form)
        layout.addWidget(id_group)

        # Default paths
        paths_group = QGroupBox("Default Locations")
        paths_layout = QVBoxLayout()
        note = QLabel(
            "These paths auto-populate when the project is active. "
            "Leave blank to skip."
        )
        note.setObjectName("cardSub")
        note.setWordWrap(True)
        paths_layout.addWidget(note)

        self._path_cards = {}
        for key, role in self.PATH_KEYS:
            card = PathCard(role)
            self._path_cards[key] = card
            paths_layout.addWidget(card)

        paths_group.setLayout(paths_layout)
        layout.addWidget(paths_group)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _populate(self, p: Project):
        self.edit_name.setText(p.name)
        self.edit_desc.setPlainText(p.description)
        for key, card in self._path_cards.items():
            val = p.default_paths.get(key, "")
            if val:
                card.set_path(val)

    def _save(self):
        name = self.edit_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Enter a project name.")
            return

        paths = {}
        for key, card in self._path_cards.items():
            p = card.get_path()
            if p:
                paths[key] = str(p)

        if self.project:
            self.project.name = name
            self.project.description = self.edit_desc.toPlainText().strip()
            self.project.default_paths = paths
            self.result_project = self.project
        else:
            self.result_project = Project(
                name=name,
                description=self.edit_desc.toPlainText().strip(),
                default_paths=paths,
            )
        self.accept()
