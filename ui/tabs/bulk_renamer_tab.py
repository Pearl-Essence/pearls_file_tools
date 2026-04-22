"""Bulk File Renamer tab for Pearl's File Tools."""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
                            QPushButton, QRadioButton, QCheckBox, QScrollArea, QWidget,
                            QButtonGroup, QSpinBox, QStackedWidget, QFormLayout, QComboBox)
from PyQt5.QtCore import Qt
from pathlib import Path
from typing import List, Dict, Optional
from ui.tabs.base_tab import BaseTab
from ui.widgets.directory_selector import DirectorySelectorWidget
from ui.widgets.file_list_widget import FileListWidget
from constants import (ALL_EXTENSION_CATEGORIES, CASE_NONE, CASE_UPPER, CASE_LOWER,
                      CASE_TITLE, OP_TYPE_RENAME)
from core.file_utils import get_files_in_directory
from core.pattern_matching import (detect_common_prefixes, match_prefix,
                                   detect_common_suffixes, match_suffix)
from core.name_transform import (generate_new_filename, generate_sequential_filenames,
                                  bump_version, move_suffix_to_prefix,
                                  ProductionTemplate, DEFAULT_TEMPLATE)
from models.operation_record import OperationRecord


class BulkRenamerTab(BaseTab):
    """Tab for bulk file renaming operations."""

    def __init__(self, config, parent=None):
        """Initialize the bulk renamer tab."""
        self.extension_checkboxes: Dict[str, QCheckBox] = {}
        self.prefix_checkboxes: Dict[str, QCheckBox] = {}
        self.undo_stack: List[OperationRecord] = []
        self._current_template: Optional[ProductionTemplate] = None
        self.template_inputs: Dict[str, QLineEdit] = {}

        super().__init__(config, parent)

    def get_tab_name(self) -> str:
        """Get the tab name."""
        return "Bulk Renamer"

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()

        # Directory selection
        self.dir_selector = DirectorySelectorWidget(
            label_text="Directory:",
            show_recursive=True
        )
        self.dir_selector.directory_changed.connect(self.on_directory_changed)
        layout.addWidget(self.dir_selector)

        # Naming profile bar
        layout.addWidget(self.create_profile_bar())

        # Extension filters
        filter_group = self.create_extension_filter_group()
        layout.addWidget(filter_group)

        # ── Rename mode selector ──────────────────────────────────────────
        mode_group = QGroupBox("Rename Mode")
        mode_layout = QHBoxLayout()
        self.mode_btn_group = QButtonGroup()
        self.mode_standard_radio = QRadioButton("Standard")
        self.mode_sequential_radio = QRadioButton("Number Files")
        self.mode_template_radio = QRadioButton("Template")
        self.mode_btn_group.addButton(self.mode_standard_radio, 0)
        self.mode_btn_group.addButton(self.mode_sequential_radio, 1)
        self.mode_btn_group.addButton(self.mode_template_radio, 2)
        self.mode_standard_radio.setChecked(True)
        self.mode_standard_radio.toggled.connect(self._on_mode_changed)
        self.mode_sequential_radio.toggled.connect(self._on_mode_changed)
        self.mode_template_radio.toggled.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_standard_radio)
        mode_layout.addWidget(self.mode_sequential_radio)
        mode_layout.addWidget(self.mode_template_radio)
        mode_layout.addStretch()
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # ── Stacked rename options ────────────────────────────────────────
        self.rename_stack = QStackedWidget()
        self.rename_stack.addWidget(self.create_rename_options_group())      # 0 — standard
        self.rename_stack.addWidget(self.create_sequential_options_group())  # 1 — sequential
        self.rename_stack.addWidget(self.create_template_options_group())    # 2 — template
        layout.addWidget(self.rename_stack)

        # Companion file options (visible in all modes)
        companion_group = self.create_companion_options_group()
        layout.addWidget(companion_group)

        # Prefix/suffix transposition (standard mode only)
        self.prefix_group_widget = self.create_transposition_group()
        layout.addWidget(self.prefix_group_widget)

        # File list
        self.file_list = FileListWidget()
        layout.addWidget(self.file_list, stretch=1)

        # Action buttons
        button_layout = QHBoxLayout()

        self.preview_btn = QPushButton("Preview Changes")
        self.preview_btn.clicked.connect(self.preview_changes)
        button_layout.addWidget(self.preview_btn)

        self.apply_btn = QPushButton("Apply Rename")
        self.apply_btn.clicked.connect(self.apply_rename)
        button_layout.addWidget(self.apply_btn)

        self.bump_version_btn = QPushButton("Bump Version (_v##)")
        self.bump_version_btn.setToolTip(
            "Increment the _v## suffix on all selected files (e.g. HERO_v01.mov → HERO_v02.mov)"
        )
        self.bump_version_btn.clicked.connect(self.apply_bump_version)
        button_layout.addWidget(self.bump_version_btn)

        self.undo_btn = QPushButton("Undo Last Operation")
        self.undo_btn.clicked.connect(self.undo_last_operation)
        self.undo_btn.setEnabled(False)
        button_layout.addWidget(self.undo_btn)

        self.open_csv_btn = QPushButton("Open Latest CSV Log")
        self.open_csv_btn.setToolTip("Open the most recent rename log CSV in this directory")
        self.open_csv_btn.clicked.connect(self.open_latest_csv)
        button_layout.addWidget(self.open_csv_btn)

        self.normalize_btn = QPushButton("Normalize Incoming")
        self.normalize_btn.setToolTip(
            "Strip common bad prefixes/suffixes from selected files "
            "(e.g. '_COPY', 'Copy of ')"
        )
        self.normalize_btn.clicked.connect(self.normalize_incoming)
        button_layout.addWidget(self.normalize_btn)

        self.lint_btn = QPushButton("Lint Folder")
        self.lint_btn.setToolTip("Check filenames in the current directory for issues")
        self.lint_btn.clicked.connect(self.lint_folder)
        button_layout.addWidget(self.lint_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    # ── profile bar ───────────────────────────────────────────────────────

    def create_profile_bar(self) -> QGroupBox:
        """Naming profile selector + management buttons."""
        group = QGroupBox("Naming Profile")
        row = QHBoxLayout()
        row.addWidget(QLabel("Active:"))

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(180)
        self.profile_combo.setToolTip(
            "The active profile drives the Template rename mode and "
            "the conformance check in Lint Folder."
        )
        self.profile_combo.addItem("(None)")
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        row.addWidget(self.profile_combo)

        save_btn = QPushButton("Save as Profile\u2026")
        save_btn.setToolTip("Save the current template settings as a new named profile")
        save_btn.clicked.connect(self._save_as_profile)
        row.addWidget(save_btn)

        manage_btn = QPushButton("Manage Profiles\u2026")
        manage_btn.clicked.connect(self._manage_profiles)
        row.addWidget(manage_btn)

        row.addStretch()
        group.setLayout(row)
        return group

    def _load_profile_combo(self):
        """Re-populate the profile combo from config without firing callbacks."""
        self.profile_combo.blockSignals(True)
        current = self.profile_combo.currentText()
        self.profile_combo.clear()
        self.profile_combo.addItem("(None)")
        for d in self.config.get('naming.profiles', []):
            name = d.get('name', '')
            if name:
                self.profile_combo.addItem(name)
        idx = self.profile_combo.findText(current)
        self.profile_combo.setCurrentIndex(max(0, idx))
        self.profile_combo.blockSignals(False)

    def _get_active_profile(self) -> Optional[ProductionTemplate]:
        name = self.profile_combo.currentText()
        if name == "(None)":
            return None
        for d in self.config.get('naming.profiles', []):
            if d.get('name') == name:
                return ProductionTemplate.from_dict(d)
        return None

    def _on_profile_changed(self, name: str):
        self.config.set('naming.active_profile',
                        name if name != "(None)" else None)
        self._rebuild_template_panel(self._get_active_profile())

    def _save_as_profile(self):
        from PyQt5.QtWidgets import QInputDialog
        profile = self._get_active_profile() or DEFAULT_TEMPLATE
        name, ok = QInputDialog.getText(self, "Save as Profile", "Profile name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        profiles = list(self.config.get('naming.profiles', []))
        if any(p.get('name') == name for p in profiles):
            self.show_warning("Duplicate Name", f"A profile named '{name}' already exists.")
            return
        profiles.append({
            'name': name,
            'tokens': profile.tokens,
            'separator': profile.separator,
            'version_format': profile.version_format,
            'episode_format': profile.episode_format,
        })
        self.config.set('naming.profiles', profiles)
        self._load_profile_combo()
        idx = self.profile_combo.findText(name)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

    def _manage_profiles(self):
        from ui.dialogs.profile_dialog import ProfileDialog
        dialog = ProfileDialog(self.config, self)
        dialog.exec_()
        active = self.config.get('naming.active_profile')
        self._load_profile_combo()
        if active:
            idx = self.profile_combo.findText(active)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        self._rebuild_template_panel(self._get_active_profile())

    # ── template mode panel ───────────────────────────────────────────────

    def create_template_options_group(self) -> QGroupBox:
        """Token-field panel that composes filenames from the active profile."""
        group = QGroupBox("Template Options")
        layout = QVBoxLayout()

        # Scrollable token input area — rebuilt when profile changes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(165)
        self.template_tokens_widget = QWidget()
        self.template_tokens_layout = QFormLayout()
        self.template_tokens_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.template_tokens_widget.setLayout(self.template_tokens_layout)
        scroll.setWidget(self.template_tokens_widget)
        layout.addWidget(scroll)

        self.template_preview_label = QLabel("Preview: \u2014")
        self.template_preview_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.template_preview_label)

        group.setLayout(layout)
        self._rebuild_template_panel(None)
        return group

    def _rebuild_template_panel(self, profile: Optional[ProductionTemplate] = None):
        """Rebuild token QLineEdits for *profile* (or DEFAULT_TEMPLATE)."""
        if not hasattr(self, 'template_tokens_layout'):
            return
        template = profile if profile is not None else DEFAULT_TEMPLATE
        self._current_template = template

        while self.template_tokens_layout.count():
            item = self.template_tokens_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.template_inputs.clear()

        for token in template.tokens:
            edit = QLineEdit()
            if token == 'VER':
                try:
                    placeholder = f"e.g. {template.version_format.format(1)}"
                except Exception:
                    placeholder = "e.g. v01"
            elif token in ('EP', 'EPISODE'):
                try:
                    placeholder = f"e.g. {template.episode_format.format(1)}"
                except Exception:
                    placeholder = "e.g. EP01"
            else:
                placeholder = f"\u2014 {token} \u2014"
            edit.setPlaceholderText(placeholder)
            edit.textChanged.connect(self._update_template_preview)
            self.template_tokens_layout.addRow(token + ":", edit)
            self.template_inputs[token] = edit

        self._update_template_preview()

    def _update_template_preview(self):
        if not hasattr(self, 'template_preview_label') or self._current_template is None:
            return
        values = {t: e.text().strip() for t, e in self.template_inputs.items()}
        composed = self._current_template.compose(values)
        if composed:
            self.template_preview_label.setText(f"Preview: {composed}.ext")
        else:
            self.template_preview_label.setText("Preview: (fill in tokens above)")

    def _get_template_composed_name(self) -> str:
        if self._current_template is None:
            return ""
        values = {t: e.text().strip() for t, e in self.template_inputs.items()}
        return self._current_template.compose(values)

    # ── mode switching ────────────────────────────────────────────────────

    def _on_mode_changed(self):
        mode = self.mode_btn_group.checkedId()
        self.rename_stack.setCurrentIndex(mode)
        is_standard = (mode == 0)
        self.prefix_group_widget.setVisible(is_standard)
        self.preview_btn.setEnabled(is_standard)

    # ── extension filters ─────────────────────────────────────────────────

    def create_extension_filter_group(self) -> QGroupBox:
        """Create the extension filter group."""
        group = QGroupBox("File Type Filters")
        layout = QVBoxLayout()

        preset_layout = QHBoxLayout()
        for category in ['images', 'documents', 'videos', 'audio', 'archives']:
            checkbox = QCheckBox(category.capitalize())
            checkbox.stateChanged.connect(self.refresh_file_list)
            self.extension_checkboxes[category] = checkbox
            preset_layout.addWidget(checkbox)
        preset_layout.addStretch()
        layout.addLayout(preset_layout)

        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("Custom extensions:"))
        self.custom_ext_input = QLineEdit()
        self.custom_ext_input.setPlaceholderText("e.g., .txt, .py, .md")
        custom_layout.addWidget(self.custom_ext_input, stretch=1)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.refresh_file_list)
        custom_layout.addWidget(apply_btn)
        layout.addLayout(custom_layout)

        group.setLayout(layout)
        return group

    # ── standard rename panel ─────────────────────────────────────────────

    def create_rename_options_group(self) -> QGroupBox:
        """Create the rename options group."""
        group = QGroupBox("Rename Options")
        layout = QVBoxLayout()

        rename_layout = QHBoxLayout()
        rename_layout.addWidget(QLabel("Rename to:"))
        self.rename_input = QLineEdit()
        self.rename_input.setPlaceholderText("Replace entire base name (prefix/suffix still applied)")
        rename_layout.addWidget(self.rename_input, stretch=1)
        layout.addLayout(rename_layout)

        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("Prefix:"))
        self.prefix_input = QLineEdit()
        prefix_layout.addWidget(self.prefix_input, stretch=1)
        layout.addLayout(prefix_layout)

        suffix_layout = QHBoxLayout()
        suffix_layout.addWidget(QLabel("Suffix:"))
        self.suffix_input = QLineEdit()
        suffix_layout.addWidget(self.suffix_input, stretch=1)
        layout.addLayout(suffix_layout)

        case_layout = QHBoxLayout()
        case_layout.addWidget(QLabel("Case:"))
        self.case_group = QButtonGroup()
        self.case_none_radio = QRadioButton("No change")
        self.case_upper_radio = QRadioButton("UPPERCASE")
        self.case_lower_radio = QRadioButton("lowercase")
        self.case_title_radio = QRadioButton("Title Case")
        self.case_group.addButton(self.case_none_radio, 0)
        self.case_group.addButton(self.case_upper_radio, 1)
        self.case_group.addButton(self.case_lower_radio, 2)
        self.case_group.addButton(self.case_title_radio, 3)
        self.case_none_radio.setChecked(True)
        case_layout.addWidget(self.case_none_radio)
        case_layout.addWidget(self.case_upper_radio)
        case_layout.addWidget(self.case_lower_radio)
        case_layout.addWidget(self.case_title_radio)
        case_layout.addStretch()
        layout.addLayout(case_layout)

        group.setLayout(layout)
        return group

    # ── sequential numbering panel ────────────────────────────────────────

    def create_sequential_options_group(self) -> QGroupBox:
        """Create the sequential-numbering options panel."""
        group = QGroupBox("Sequential Numbering Options")
        layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Base name:"))
        self.seq_base_input = QLineEdit()
        self.seq_base_input.setPlaceholderText("e.g. HERO or SCENE_01")
        row1.addWidget(self.seq_base_input, stretch=1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Start at:"))
        self.seq_start_spin = QSpinBox()
        self.seq_start_spin.setRange(0, 99999)
        self.seq_start_spin.setValue(1)
        row2.addWidget(self.seq_start_spin)
        row2.addSpacing(20)
        row2.addWidget(QLabel("Padding (digits):"))
        self.seq_padding_spin = QSpinBox()
        self.seq_padding_spin.setRange(1, 8)
        self.seq_padding_spin.setValue(3)
        row2.addWidget(self.seq_padding_spin)
        row2.addSpacing(20)
        row2.addWidget(QLabel("Separator:"))
        self.seq_separator_input = QLineEdit("_")
        self.seq_separator_input.setMaximumWidth(40)
        row2.addWidget(self.seq_separator_input)
        row2.addStretch()
        layout.addLayout(row2)

        preview_label = QLabel("Preview: HERO_001.mov, HERO_002.mov, \u2026")
        preview_label.setStyleSheet("color: #888; font-style: italic;")
        self.seq_preview_label = preview_label
        layout.addWidget(preview_label)

        for widget in (self.seq_base_input, self.seq_separator_input):
            widget.textChanged.connect(self._update_seq_preview)
        for widget in (self.seq_start_spin, self.seq_padding_spin):
            widget.valueChanged.connect(self._update_seq_preview)

        group.setLayout(layout)
        return group

    def _update_seq_preview(self):
        base = self.seq_base_input.text() or "BASE"
        sep = self.seq_separator_input.text()
        start = self.seq_start_spin.value()
        pad = self.seq_padding_spin.value()
        n1 = str(start).zfill(pad)
        n2 = str(start + 1).zfill(pad)
        self.seq_preview_label.setText(
            f"Preview: {base}{sep}{n1}.ext, {base}{sep}{n2}.ext, \u2026"
        )

    # ── companion file options ────────────────────────────────────────────

    def create_companion_options_group(self) -> QGroupBox:
        """Checkboxes to control sidecar and caption co-renaming."""
        group = QGroupBox("Companion File Renaming")
        layout = QHBoxLayout()
        self.rename_sidecars_chk = QCheckBox("Rename sidecar files (.xmp, .thm, .lrv, \u2026)")
        self.rename_sidecars_chk.setChecked(True)
        self.rename_sidecars_chk.setToolTip(
            "When renaming a file, also rename any same-stem sidecar files\n"
            "(.xmp, .thm, .lrv, .json, .srt, .vtt, .ttml)"
        )
        self.rename_captions_chk = QCheckBox("Rename caption/subtitle files (.srt, .vtt, .ttml, \u2026)")
        self.rename_captions_chk.setChecked(True)
        self.rename_captions_chk.setToolTip(
            "When renaming a video, also rename any same-stem subtitle files\n"
            "(.srt, .vtt, .ttml, .sbv, .ass, .ssa)"
        )
        layout.addWidget(self.rename_sidecars_chk)
        layout.addWidget(self.rename_captions_chk)
        layout.addStretch()
        group.setLayout(layout)
        return group

    # ── transposition panel ───────────────────────────────────────────────

    def create_transposition_group(self) -> QGroupBox:
        """Bidirectional prefix ↔ suffix transposition panel."""
        group = QGroupBox("Prefix / Suffix Transposition")
        layout = QVBoxLayout()

        dir_row = QHBoxLayout()
        self.transpose_btn_group = QButtonGroup()
        self.transpose_p2s_radio = QRadioButton("Prefix \u2192 Suffix")
        self.transpose_s2p_radio = QRadioButton("Suffix \u2192 Prefix")
        self.transpose_btn_group.addButton(self.transpose_p2s_radio, 0)
        self.transpose_btn_group.addButton(self.transpose_s2p_radio, 1)
        self.transpose_p2s_radio.setChecked(True)
        self.transpose_p2s_radio.toggled.connect(self._on_transpose_direction_changed)
        dir_row.addWidget(self.transpose_p2s_radio)
        dir_row.addWidget(self.transpose_s2p_radio)
        dir_row.addStretch()
        layout.addLayout(dir_row)

        top_layout = QHBoxLayout()
        self.detect_btn = QPushButton("Detect")
        self.detect_btn.clicked.connect(self.detect_tokens)
        top_layout.addWidget(self.detect_btn)
        self.manual_token_label = QLabel("Manual prefix(es):")
        top_layout.addWidget(self.manual_token_label)
        self.manual_prefix_input = QLineEdit()
        self.manual_prefix_input.setPlaceholderText("e.g., DRAFT_, WIP_, TEMP_")
        top_layout.addWidget(self.manual_prefix_input, stretch=1)
        layout.addLayout(top_layout)

        scroll = QScrollArea()
        scroll.setMaximumHeight(90)
        scroll.setWidgetResizable(True)
        self.prefix_widget = QWidget()
        self.prefix_layout = QVBoxLayout()
        self.prefix_layout.setAlignment(Qt.AlignTop)
        self.prefix_widget.setLayout(self.prefix_layout)
        scroll.setWidget(self.prefix_widget)
        layout.addWidget(scroll)

        self.apply_transpose_btn = QPushButton("Apply Prefix \u2192 Suffix")
        self.apply_transpose_btn.clicked.connect(self.apply_transposition)
        layout.addWidget(self.apply_transpose_btn)

        group.setLayout(layout)
        return group

    def _on_transpose_direction_changed(self):
        if self.transpose_p2s_radio.isChecked():
            self.manual_token_label.setText("Manual prefix(es):")
            self.manual_prefix_input.setPlaceholderText("e.g., DRAFT_, WIP_, TEMP_")
            self.apply_transpose_btn.setText("Apply Prefix \u2192 Suffix")
        else:
            self.manual_token_label.setText("Manual suffix(es):")
            self.manual_prefix_input.setPlaceholderText("e.g., _DRAFT, _WIP, _FINAL")
            self.apply_transpose_btn.setText("Apply Suffix \u2192 Prefix")
        self.clear_prefix_checkboxes()

    # ── directory / file list ─────────────────────────────────────────────

    def on_directory_changed(self, directory: str):
        self.set_directory(directory)
        self.refresh_file_list()

    def get_active_extensions(self) -> List[str]:
        extensions = []
        for category, checkbox in self.extension_checkboxes.items():
            if checkbox.isChecked():
                extensions.extend(ALL_EXTENSION_CATEGORIES[category])
        custom = self.custom_ext_input.text().strip()
        if custom:
            for ext in custom.split(','):
                ext = ext.strip()
                if ext and not ext.startswith('.'):
                    ext = '.' + ext
                if ext:
                    extensions.append(ext.lower())
        return extensions

    def refresh_file_list(self):
        if not self.current_directory:
            return
        directory = Path(self.current_directory)
        if not directory.exists():
            return
        active_extensions = self.get_active_extensions()
        extensions = active_extensions if active_extensions else None
        recursive = self.dir_selector.is_recursive()
        files = get_files_in_directory(directory, extensions, recursive)
        self.file_list.set_files(files, relative_to=directory if recursive else None)
        self.emit_status(f"Loaded {len(files)} files")

    # ── token detection (transposition) ──────────────────────────────────

    def detect_tokens(self):
        files = self.file_list.get_all_files()
        if not files:
            self.show_warning("No Files", "No files loaded to analyze.")
            return
        filenames = [f.name for f in files]
        is_prefix_mode = self.transpose_p2s_radio.isChecked()
        if is_prefix_mode:
            counts = detect_common_prefixes(filenames)
            label = "prefix"
        else:
            counts = detect_common_suffixes(filenames)
            label = "suffix"
        if not counts:
            self.show_info(f"No {label.capitalize()}es Found",
                           f"No common {label} patterns detected.")
            return
        self.clear_prefix_checkboxes()
        for token in sorted(counts.keys(), key=lambda x: counts[x], reverse=True):
            count = counts[token]
            cb = QCheckBox(f'{token}  ({count} file{"s" if count > 1 else ""})')
            cb.setChecked(True)
            self.prefix_checkboxes[token] = cb
            self.prefix_layout.addWidget(cb)
        self.show_info(f"{label.capitalize()}es Detected",
                       f"Found {len(counts)} common {label} pattern(s).\n"
                       "Uncheck any you don't want to process.")

    def detect_prefixes(self):
        self.detect_tokens()

    def clear_prefix_checkboxes(self):
        for checkbox in self.prefix_checkboxes.values():
            checkbox.deleteLater()
        self.prefix_checkboxes.clear()

    def get_selected_prefixes(self) -> List[str]:
        selected = []
        for prefix, checkbox in self.prefix_checkboxes.items():
            if checkbox.isChecked():
                selected.append(prefix)
        manual_input = self.manual_prefix_input.text().strip()
        if manual_input:
            selected.extend(p.strip() for p in manual_input.split(',') if p.strip())
        return selected

    def get_case_transform(self) -> str:
        button_id = self.case_group.checkedId()
        if button_id == 0:
            return CASE_NONE
        elif button_id == 1:
            return CASE_UPPER
        elif button_id == 2:
            return CASE_LOWER
        elif button_id == 3:
            return CASE_TITLE
        return CASE_NONE

    # ── preview ───────────────────────────────────────────────────────────

    def preview_changes(self):
        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected for preview.")
            return
        from ui.dialogs.preview_dialog import PreviewDialog
        preview_data = []
        for filepath in selected_files:
            new_name = generate_new_filename(
                filepath.name,
                prefix=self.prefix_input.text(),
                suffix=self.suffix_input.text(),
                rename_to=self.rename_input.text(),
                case_transform=self.get_case_transform()
            )
            preview_data.append((filepath.name, new_name))
        dialog = PreviewDialog(preview_data, self)
        dialog.exec_()

    # ── apply rename ──────────────────────────────────────────────────────

    def apply_rename(self):
        """Apply rename — dispatches to standard, sequential, or template mode."""
        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected for renaming.")
            return

        from workers.rename_worker import RenameWorker
        mode = self.mode_btn_group.checkedId()

        if mode == 1:
            # Sequential numbering
            base = self.seq_base_input.text().strip()
            if not base:
                self.show_warning("Base Name Required",
                                  "Enter a base name for sequential numbering.")
                return
            pairs = generate_sequential_filenames(
                [f.name for f in selected_files],
                base_name=base,
                start=self.seq_start_spin.value(),
                padding=self.seq_padding_spin.value(),
                separator=self.seq_separator_input.text(),
            )
            direct = [(selected_files[i], new_name) for i, (_, new_name) in enumerate(pairs)]
            preview_lines = "\n".join(f"  {old} \u2192 {new}" for old, new in pairs[:5])
            if len(pairs) > 5:
                preview_lines += f"\n  \u2026 and {len(pairs) - 5} more"
            if not self.confirm_action(
                "Confirm Sequential Rename",
                f"Rename {len(selected_files)} file(s) as:\n\n{preview_lines}\n\n"
                "This can be undone using 'Undo Last Operation'."
            ):
                return
            self.worker_thread = RenameWorker(
                selected_files,
                direct_renames=direct,
                rename_sidecars=self.rename_sidecars_chk.isChecked(),
                rename_captions=self.rename_captions_chk.isChecked(),
            )

        elif mode == 2:
            # Template mode
            base = self._get_template_composed_name()
            if not base:
                self.show_warning("Incomplete Template",
                                  "Fill in at least one template token.")
                return
            sep = self._current_template.separator if self._current_template else '_'
            if len(selected_files) == 1:
                direct = [(selected_files[0],
                           f"{base}{selected_files[0].suffix}")]
            else:
                direct = [
                    (f, f"{base}{sep}{str(i + 1).zfill(3)}{f.suffix}")
                    for i, f in enumerate(selected_files)
                ]
            preview_lines = "\n".join(
                f"  {p.name} \u2192 {n}" for p, n in direct[:5]
            )
            if len(direct) > 5:
                preview_lines += f"\n  \u2026 and {len(direct) - 5} more"
            if not self.confirm_action(
                "Confirm Template Rename",
                f"Rename {len(selected_files)} file(s):\n\n{preview_lines}\n\n"
                "This can be undone using 'Undo Last Operation'."
            ):
                return
            self.worker_thread = RenameWorker(
                selected_files,
                direct_renames=direct,
                rename_sidecars=self.rename_sidecars_chk.isChecked(),
                rename_captions=self.rename_captions_chk.isChecked(),
            )

        else:
            # Standard mode
            if not self.confirm_action(
                "Confirm Rename",
                f"Rename {len(selected_files)} file(s)?\n\n"
                "This can be undone using 'Undo Last Operation'."
            ):
                return
            self.worker_thread = RenameWorker(
                selected_files,
                prefix=self.prefix_input.text(),
                suffix=self.suffix_input.text(),
                rename_to=self.rename_input.text(),
                case_transform=self.get_case_transform(),
                rename_sidecars=self.rename_sidecars_chk.isChecked(),
                rename_captions=self.rename_captions_chk.isChecked(),
            )

        self.worker_thread.progress.connect(self.emit_status)
        self.worker_thread.finished.connect(self.on_rename_finished)
        self.worker_thread.start()
        self.enable_controls(False)

    def apply_bump_version(self):
        """Bump the _v## suffix on all selected files."""
        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected.")
            return
        direct = [(f, bump_version(f.name)) for f in selected_files]
        direct = [(path, new) for path, new in direct if new != path.name]
        if not direct:
            self.show_info("No Versions Found",
                           "None of the selected files have a _v## version suffix.")
            return
        if not self.confirm_action(
            "Confirm Bump Version",
            f"Increment version suffix on {len(direct)} file(s)?\n\n"
            "This can be undone using 'Undo Last Operation'."
        ):
            return
        from workers.rename_worker import RenameWorker
        self.worker_thread = RenameWorker([], direct_renames=direct)
        self.worker_thread.progress.connect(self.emit_status)
        self.worker_thread.finished.connect(self.on_rename_finished)
        self.worker_thread.start()
        self.enable_controls(False)

    def on_rename_finished(self, success: bool, message: str,
                           operation_record: Optional[OperationRecord] = None):
        self.enable_controls(True)
        if success and operation_record:
            self.undo_stack.append(operation_record)
            self.undo_btn.setEnabled(True)
            try:
                from core.history import RenameHistory
                RenameHistory().log_operation(operation_record)
            except Exception:
                pass
            self.show_info("Rename Complete", message)
            self.refresh_file_list()
        elif not success:
            self.show_error("Rename Failed", message)
        else:
            self.show_info("Rename Complete", message)
            self.refresh_file_list()
        self.emit_status(message)

    # ── transposition ─────────────────────────────────────────────────────

    def apply_transposition(self):
        tokens = self.get_selected_prefixes()
        if not tokens:
            self.show_warning("No Tokens",
                              "Please detect or enter at least one prefix/suffix.")
            return
        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected.")
            return
        is_prefix_mode = self.transpose_p2s_radio.isChecked()
        from workers.rename_worker import RenameWorker
        if is_prefix_mode:
            matching = [f for f in selected_files if match_prefix(f.name, tokens)]
            if not matching:
                self.show_warning("No Matches",
                                  "No files start with the selected prefix(es).")
                return
            if not self.confirm_action(
                "Confirm Prefix \u2192 Suffix",
                f"Move prefix to suffix for {len(matching)} file(s)?\n\nThis can be undone."
            ):
                return
            self.worker_thread = RenameWorker(
                matching,
                prefix_to_suffix=tokens,
                rename_sidecars=self.rename_sidecars_chk.isChecked(),
                rename_captions=self.rename_captions_chk.isChecked(),
            )
        else:
            matching = [f for f in selected_files if match_suffix(f.name, tokens)]
            if not matching:
                self.show_warning("No Matches",
                                  "No files end with the selected suffix(es).")
                return
            direct = [(f, move_suffix_to_prefix(f.name, match_suffix(f.name, tokens)))
                      for f in matching]
            direct = [(p, n) for p, n in direct if n != p.name]
            if not direct:
                self.show_warning("No Changes", "No files would be changed.")
                return
            if not self.confirm_action(
                "Confirm Suffix \u2192 Prefix",
                f"Move suffix to prefix for {len(direct)} file(s)?\n\nThis can be undone."
            ):
                return
            self.worker_thread = RenameWorker(
                [],
                direct_renames=direct,
                rename_sidecars=self.rename_sidecars_chk.isChecked(),
                rename_captions=self.rename_captions_chk.isChecked(),
            )
        self.worker_thread.progress.connect(self.emit_status)
        self.worker_thread.finished.connect(self.on_rename_finished)
        self.worker_thread.start()
        self.enable_controls(False)

    def apply_prefix_to_suffix(self):
        self.apply_transposition()

    # ── CSV log ───────────────────────────────────────────────────────────

    def open_latest_csv(self):
        import subprocess
        import sys
        import glob
        if not self.current_directory:
            self.show_warning("No Directory", "No directory selected.")
            return
        pattern = str(Path(self.current_directory) / "_pearls_rename_log_*.csv")
        matches = sorted(glob.glob(pattern))
        if not matches:
            self.show_info("No CSV Found",
                           "No rename log CSV files found in the current directory.\n"
                           "A CSV is written after each successful rename batch.")
            return
        latest = matches[-1]
        try:
            if sys.platform == 'darwin':
                subprocess.Popen(['open', latest])
            elif sys.platform == 'win32':
                subprocess.Popen(['start', '', latest], shell=True)
            else:
                subprocess.Popen(['xdg-open', latest])
            self.emit_status(f"Opened: {Path(latest).name}")
        except Exception as e:
            self.show_error("Could Not Open File", str(e))

    # ── undo ──────────────────────────────────────────────────────────────

    def undo_last_operation(self):
        if not self.undo_stack:
            self.show_info("No Operations", "No operations to undo.")
            return
        record = self.undo_stack.pop()
        success_count, error_count, errors = record.undo()
        if error_count == 0:
            self.show_info("Undo Complete",
                           f"Successfully undone {success_count} rename(s).")
        else:
            error_msg = f"Undone {success_count} rename(s).\n{error_count} error(s):\n\n"
            error_msg += "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more"
            self.show_warning("Undo Complete with Errors", error_msg)
        if not self.undo_stack:
            self.undo_btn.setEnabled(False)
        self.refresh_file_list()

    # ── Phase 3 features ──────────────────────────────────────────────────

    def lint_folder(self):
        """Lint filenames in the current directory and show a LintDialog."""
        if not self.current_directory:
            self.show_warning("No Directory", "No directory selected.")
            return
        from core.linter import FilenameLint
        from ui.dialogs.lint_dialog import LintDialog
        directory = Path(self.current_directory)
        profile = self._get_active_profile()
        self.emit_status("Linting filenames\u2026")
        issues = FilenameLint().lint_directory(directory, profile)
        self.emit_status(
            f"Lint complete: {len(issues)} issue(s) found in {directory.name}"
        )
        dialog = LintDialog(directory, issues, self)
        dialog.show()

    def normalize_incoming(self):
        """Strip configurable bad patterns from selected (or all) files."""
        selected = self.file_list.get_selected_files()
        files = selected if selected else self.file_list.get_all_files()
        if not files:
            self.show_warning("No Files", "No files loaded.")
            return
        from ui.dialogs.normalize_dialog import NormalizeDialog
        dialog = NormalizeDialog(files, self.config, self)
        if dialog.exec_() != NormalizeDialog.Accepted:
            return
        pairs = dialog.get_rename_pairs()
        if not pairs:
            self.show_info("No Changes", "No files matched the current patterns.")
            return
        from workers.rename_worker import RenameWorker
        self.worker_thread = RenameWorker(
            [],
            direct_renames=pairs,
            rename_sidecars=self.rename_sidecars_chk.isChecked(),
            rename_captions=self.rename_captions_chk.isChecked(),
        )
        self.worker_thread.progress.connect(self.emit_status)
        self.worker_thread.finished.connect(self.on_rename_finished)
        self.worker_thread.start()
        self.enable_controls(False)

    # ── settings ──────────────────────────────────────────────────────────

    def load_settings(self):
        """Load tab-specific settings."""
        last_dir = self.config.get_tab_directory('bulk_renamer')
        if last_dir:
            self.dir_selector.set_directory(last_dir)
            self.set_directory(last_dir)

        recursive = self.config.get_tab_setting('bulk_renamer', 'recursive_default', False)
        self.dir_selector.set_recursive(recursive)

        filters = self.config.get_tab_setting('bulk_renamer', 'extension_filters', {})
        for category, enabled in filters.items():
            if category in self.extension_checkboxes:
                self.extension_checkboxes[category].setChecked(enabled)

        case_default = self.config.get_tab_setting(
            'bulk_renamer', 'case_transform_default', 'none')
        if case_default == 'upper':
            self.case_upper_radio.setChecked(True)
        elif case_default == 'lower':
            self.case_lower_radio.setChecked(True)
        elif case_default == 'title':
            self.case_title_radio.setChecked(True)

        # Restore active profile
        self._load_profile_combo()
        active = self.config.get('naming.active_profile')
        if active:
            idx = self.profile_combo.findText(active)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)

    def save_settings(self):
        """Save tab-specific settings."""
        self.config.set_tab_setting('bulk_renamer', 'recursive_default',
                                    self.dir_selector.is_recursive())
        filters = {
            category: checkbox.isChecked()
            for category, checkbox in self.extension_checkboxes.items()
        }
        self.config.set_tab_setting('bulk_renamer', 'extension_filters', filters)
        self.config.set_tab_setting('bulk_renamer', 'case_transform_default',
                                    self.get_case_transform())
