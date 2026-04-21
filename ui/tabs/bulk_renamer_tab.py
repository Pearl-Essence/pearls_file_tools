"""Bulk File Renamer tab for Pearl's File Tools."""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
                            QPushButton, QRadioButton, QCheckBox, QScrollArea, QWidget,
                            QButtonGroup, QSpinBox, QStackedWidget)
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
                                  bump_version, move_suffix_to_prefix)
from models.operation_record import OperationRecord


class BulkRenamerTab(BaseTab):
    """Tab for bulk file renaming operations."""

    def __init__(self, config, parent=None):
        """Initialize the bulk renamer tab."""
        self.extension_checkboxes: Dict[str, QCheckBox] = {}
        self.prefix_checkboxes: Dict[str, QCheckBox] = {}
        self.undo_stack: List[OperationRecord] = []

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

        # Extension filters
        filter_group = self.create_extension_filter_group()
        layout.addWidget(filter_group)

        # ── Rename mode selector ──────────────────────────────────────────
        mode_group = QGroupBox("Rename Mode")
        mode_layout = QHBoxLayout()
        self.mode_btn_group = QButtonGroup()
        self.mode_standard_radio = QRadioButton("Standard")
        self.mode_sequential_radio = QRadioButton("Number Files")
        self.mode_btn_group.addButton(self.mode_standard_radio, 0)
        self.mode_btn_group.addButton(self.mode_sequential_radio, 1)
        self.mode_standard_radio.setChecked(True)
        self.mode_standard_radio.toggled.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_standard_radio)
        mode_layout.addWidget(self.mode_sequential_radio)
        mode_layout.addStretch()
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # ── Stacked rename options ────────────────────────────────────────
        self.rename_stack = QStackedWidget()
        self.rename_stack.addWidget(self.create_rename_options_group())    # page 0 — standard
        self.rename_stack.addWidget(self.create_sequential_options_group())  # page 1 — sequential
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

        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _on_mode_changed(self):
        is_standard = self.mode_standard_radio.isChecked()
        self.rename_stack.setCurrentIndex(0 if is_standard else 1)
        self.prefix_group_widget.setVisible(is_standard)
        self.preview_btn.setEnabled(is_standard)

    def create_extension_filter_group(self) -> QGroupBox:
        """Create the extension filter group."""
        group = QGroupBox("File Type Filters")
        layout = QVBoxLayout()

        # Preset filters
        preset_layout = QHBoxLayout()

        for category in ['images', 'documents', 'videos', 'audio', 'archives']:
            checkbox = QCheckBox(category.capitalize())
            checkbox.stateChanged.connect(self.refresh_file_list)
            self.extension_checkboxes[category] = checkbox
            preset_layout.addWidget(checkbox)

        preset_layout.addStretch()
        layout.addLayout(preset_layout)

        # Custom extensions
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

    def create_rename_options_group(self) -> QGroupBox:
        """Create the rename options group."""
        group = QGroupBox("Rename Options")
        layout = QVBoxLayout()

        # Prefix
        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("Prefix:"))
        self.prefix_input = QLineEdit()
        prefix_layout.addWidget(self.prefix_input, stretch=1)
        layout.addLayout(prefix_layout)

        # Suffix
        suffix_layout = QHBoxLayout()
        suffix_layout.addWidget(QLabel("Suffix:"))
        self.suffix_input = QLineEdit()
        suffix_layout.addWidget(self.suffix_input, stretch=1)
        layout.addLayout(suffix_layout)

        # Rename to
        rename_layout = QHBoxLayout()
        rename_layout.addWidget(QLabel("Rename to:"))
        self.rename_input = QLineEdit()
        rename_layout.addWidget(self.rename_input, stretch=1)
        layout.addLayout(rename_layout)

        # Case transformation
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

        preview_label = QLabel("Preview: HERO_001.mov, HERO_002.mov, …")
        preview_label.setStyleSheet("color: #888; font-style: italic;")
        self.seq_preview_label = preview_label
        layout.addWidget(preview_label)

        # Update preview label live
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
            f"Preview: {base}{sep}{n1}.ext, {base}{sep}{n2}.ext, …"
        )

    def create_companion_options_group(self) -> QGroupBox:
        """Checkboxes to control sidecar and caption co-renaming."""
        group = QGroupBox("Companion File Renaming")
        layout = QHBoxLayout()
        self.rename_sidecars_chk = QCheckBox("Rename sidecar files (.xmp, .thm, .lrv, …)")
        self.rename_sidecars_chk.setChecked(True)
        self.rename_sidecars_chk.setToolTip(
            "When renaming a file, also rename any same-stem sidecar files\n"
            "(.xmp, .thm, .lrv, .json, .srt, .vtt, .ttml)"
        )
        self.rename_captions_chk = QCheckBox("Rename caption/subtitle files (.srt, .vtt, .ttml, …)")
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

    def create_transposition_group(self) -> QGroupBox:
        """Bidirectional prefix ↔ suffix transposition panel."""
        group = QGroupBox("Prefix / Suffix Transposition")
        layout = QVBoxLayout()

        # Direction selector
        dir_row = QHBoxLayout()
        self.transpose_btn_group = QButtonGroup()
        self.transpose_p2s_radio = QRadioButton("Prefix → Suffix")
        self.transpose_s2p_radio = QRadioButton("Suffix → Prefix")
        self.transpose_btn_group.addButton(self.transpose_p2s_radio, 0)
        self.transpose_btn_group.addButton(self.transpose_s2p_radio, 1)
        self.transpose_p2s_radio.setChecked(True)
        self.transpose_p2s_radio.toggled.connect(self._on_transpose_direction_changed)
        dir_row.addWidget(self.transpose_p2s_radio)
        dir_row.addWidget(self.transpose_s2p_radio)
        dir_row.addStretch()
        layout.addLayout(dir_row)

        # Detect button + manual input
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

        # Scrollable detected token list
        scroll = QScrollArea()
        scroll.setMaximumHeight(90)
        scroll.setWidgetResizable(True)
        self.prefix_widget = QWidget()
        self.prefix_layout = QVBoxLayout()
        self.prefix_layout.setAlignment(Qt.AlignTop)
        self.prefix_widget.setLayout(self.prefix_layout)
        scroll.setWidget(self.prefix_widget)
        layout.addWidget(scroll)

        # Apply button
        self.apply_transpose_btn = QPushButton("Apply Prefix → Suffix")
        self.apply_transpose_btn.clicked.connect(self.apply_transposition)
        layout.addWidget(self.apply_transpose_btn)

        group.setLayout(layout)
        return group

    def _on_transpose_direction_changed(self):
        if self.transpose_p2s_radio.isChecked():
            self.manual_token_label.setText("Manual prefix(es):")
            self.manual_prefix_input.setPlaceholderText("e.g., DRAFT_, WIP_, TEMP_")
            self.apply_transpose_btn.setText("Apply Prefix → Suffix")
        else:
            self.manual_token_label.setText("Manual suffix(es):")
            self.manual_prefix_input.setPlaceholderText("e.g., _DRAFT, _WIP, _FINAL")
            self.apply_transpose_btn.setText("Apply Suffix → Prefix")
        self.clear_prefix_checkboxes()

    def on_directory_changed(self, directory: str):
        """Handle directory change."""
        self.set_directory(directory)
        self.refresh_file_list()

    def get_active_extensions(self) -> List[str]:
        """Get list of active file extensions based on filters."""
        extensions = []

        # Add preset category extensions
        for category, checkbox in self.extension_checkboxes.items():
            if checkbox.isChecked():
                extensions.extend(ALL_EXTENSION_CATEGORIES[category])

        # Add custom extensions
        custom = self.custom_ext_input.text().strip()
        if custom:
            custom_exts = [ext.strip() for ext in custom.split(',')]
            for ext in custom_exts:
                if ext and not ext.startswith('.'):
                    ext = '.' + ext
                if ext:
                    extensions.append(ext.lower())

        return extensions

    def refresh_file_list(self):
        """Refresh the file list based on current directory and filters."""
        if not self.current_directory:
            return

        directory = Path(self.current_directory)
        if not directory.exists():
            return

        # Get active extensions
        active_extensions = self.get_active_extensions()
        extensions = active_extensions if active_extensions else None

        # Get files
        recursive = self.dir_selector.is_recursive()
        files = get_files_in_directory(directory, extensions, recursive)

        # Update file list widget
        self.file_list.set_files(files, relative_to=directory if recursive else None)

        self.emit_status(f"Loaded {len(files)} files")

    def detect_tokens(self):
        """Detect common prefix or suffix tokens depending on selected direction."""
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

    # Keep old name as alias so existing callers don't break
    def detect_prefixes(self):
        self.detect_tokens()

    def clear_prefix_checkboxes(self):
        """Clear all prefix checkboxes."""
        for checkbox in self.prefix_checkboxes.values():
            checkbox.deleteLater()
        self.prefix_checkboxes.clear()

    def get_selected_prefixes(self) -> List[str]:
        """Get list of selected prefixes."""
        selected = []

        # From detected prefixes
        for prefix, checkbox in self.prefix_checkboxes.items():
            if checkbox.isChecked():
                selected.append(prefix)

        # From manual input
        manual_input = self.manual_prefix_input.text().strip()
        if manual_input:
            manual_prefixes = [p.strip() for p in manual_input.split(',') if p.strip()]
            selected.extend(manual_prefixes)

        return selected

    def get_case_transform(self) -> str:
        """Get the selected case transformation."""
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

    def preview_changes(self):
        """Preview rename changes."""
        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected for preview.")
            return

        # Generate preview
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

    def apply_rename(self):
        """Apply rename operation (standard or sequential mode)."""
        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected for renaming.")
            return

        from workers.rename_worker import RenameWorker

        # Sequential numbering mode
        if self.mode_sequential_radio.isChecked():
            base = self.seq_base_input.text().strip()
            if not base:
                self.show_warning("Base Name Required", "Enter a base name for sequential numbering.")
                return
            pairs = generate_sequential_filenames(
                [f.name for f in selected_files],
                base_name=base,
                start=self.seq_start_spin.value(),
                padding=self.seq_padding_spin.value(),
                separator=self.seq_separator_input.text(),
            )
            direct = [(selected_files[i], new_name) for i, (_, new_name) in enumerate(pairs)]
            preview_lines = "\n".join(f"  {old} → {new}" for old, new in pairs[:5])
            if len(pairs) > 5:
                preview_lines += f"\n  … and {len(pairs) - 5} more"
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
        # Skip files with no version suffix
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

    def on_rename_finished(self, success: bool, message: str, operation_record: Optional[OperationRecord] = None):
        """Handle rename operation completion."""
        self.enable_controls(True)

        if success and operation_record:
            self.undo_stack.append(operation_record)
            self.undo_btn.setEnabled(True)
            # Persist to history DB
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

    def apply_transposition(self):
        """Apply prefix→suffix or suffix→prefix transposition to selected files."""
        tokens = self.get_selected_prefixes()
        if not tokens:
            self.show_warning("No Tokens", "Please detect or enter at least one prefix/suffix.")
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
                self.show_warning("No Matches", "No files start with the selected prefix(es).")
                return
            if not self.confirm_action(
                "Confirm Prefix → Suffix",
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
                self.show_warning("No Matches", "No files end with the selected suffix(es).")
                return
            direct = [(f, move_suffix_to_prefix(f.name, match_suffix(f.name, tokens)))
                      for f in matching]
            direct = [(p, n) for p, n in direct if n != p.name]
            if not direct:
                self.show_warning("No Changes", "No files would be changed.")
                return
            if not self.confirm_action(
                "Confirm Suffix → Prefix",
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

    # Keep old name as alias
    def apply_prefix_to_suffix(self):
        self.apply_transposition()

    def open_latest_csv(self):
        """Open the most recent rename log CSV in the current directory."""
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

    def undo_last_operation(self):
        """Undo the last rename operation."""
        if not self.undo_stack:
            self.show_info("No Operations", "No operations to undo.")
            return

        record = self.undo_stack.pop()

        # Perform undo
        success_count, error_count, errors = record.undo()

        # Update UI
        if error_count == 0:
            self.show_info("Undo Complete", f"Successfully undone {success_count} rename(s).")
        else:
            error_msg = f"Undone {success_count} rename(s).\n{error_count} error(s):\n\n"
            error_msg += "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more"
            self.show_warning("Undo Complete with Errors", error_msg)

        # Disable undo button if stack is empty
        if not self.undo_stack:
            self.undo_btn.setEnabled(False)

        self.refresh_file_list()

    def load_settings(self):
        """Load tab-specific settings."""
        # Load last directory
        last_dir = self.config.get_tab_directory('bulk_renamer')
        if last_dir:
            self.dir_selector.set_directory(last_dir)
            self.set_directory(last_dir)

        # Load recursive setting
        recursive = self.config.get_tab_setting('bulk_renamer', 'recursive_default', False)
        self.dir_selector.set_recursive(recursive)

        # Load extension filters
        filters = self.config.get_tab_setting('bulk_renamer', 'extension_filters', {})
        for category, enabled in filters.items():
            if category in self.extension_checkboxes:
                self.extension_checkboxes[category].setChecked(enabled)

        # Load case transform default
        case_default = self.config.get_tab_setting('bulk_renamer', 'case_transform_default', 'none')
        if case_default == 'upper':
            self.case_upper_radio.setChecked(True)
        elif case_default == 'lower':
            self.case_lower_radio.setChecked(True)
        elif case_default == 'title':
            self.case_title_radio.setChecked(True)

    def save_settings(self):
        """Save tab-specific settings."""
        # Save recursive setting
        self.config.set_tab_setting('bulk_renamer', 'recursive_default',
                                   self.dir_selector.is_recursive())

        # Save extension filters
        filters = {
            category: checkbox.isChecked()
            for category, checkbox in self.extension_checkboxes.items()
        }
        self.config.set_tab_setting('bulk_renamer', 'extension_filters', filters)

        # Save case transform
        case_transform = self.get_case_transform()
        self.config.set_tab_setting('bulk_renamer', 'case_transform_default', case_transform)
