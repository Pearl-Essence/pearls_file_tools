"""Bulk File Renamer tab for Pearl's File Tools."""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
                            QPushButton, QRadioButton, QCheckBox, QScrollArea, QWidget,
                            QButtonGroup)
from PyQt5.QtCore import Qt
from pathlib import Path
from typing import List, Dict, Optional
from ui.tabs.base_tab import BaseTab
from ui.widgets.directory_selector import DirectorySelectorWidget
from ui.widgets.file_list_widget import FileListWidget
from constants import (ALL_EXTENSION_CATEGORIES, CASE_NONE, CASE_UPPER, CASE_LOWER,
                      CASE_TITLE, OP_TYPE_RENAME)
from core.file_utils import get_files_in_directory
from core.pattern_matching import detect_common_prefixes, match_prefix
from core.name_transform import generate_new_filename
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

        # Rename options
        rename_group = self.create_rename_options_group()
        layout.addWidget(rename_group)

        # Prefix detection section
        prefix_group = self.create_prefix_detection_group()
        layout.addWidget(prefix_group)

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

        self.undo_btn = QPushButton("Undo Last Operation")
        self.undo_btn.clicked.connect(self.undo_last_operation)
        self.undo_btn.setEnabled(False)
        button_layout.addWidget(self.undo_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        self.setLayout(layout)

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

    def create_prefix_detection_group(self) -> QGroupBox:
        """Create the prefix detection group."""
        group = QGroupBox("Prefix Detection (move prefix to suffix)")
        layout = QVBoxLayout()

        # Detect button and manual input
        top_layout = QHBoxLayout()

        self.detect_btn = QPushButton("Detect Prefixes")
        self.detect_btn.clicked.connect(self.detect_prefixes)
        top_layout.addWidget(self.detect_btn)

        top_layout.addWidget(QLabel("Manual prefix(es):"))
        self.manual_prefix_input = QLineEdit()
        self.manual_prefix_input.setPlaceholderText("e.g., DRAFT_, WIP_, TEMP_")
        top_layout.addWidget(self.manual_prefix_input, stretch=1)

        layout.addLayout(top_layout)

        # Scrollable prefix list
        scroll = QScrollArea()
        scroll.setMaximumHeight(100)
        scroll.setWidgetResizable(True)

        self.prefix_widget = QWidget()
        self.prefix_layout = QVBoxLayout()
        self.prefix_layout.setAlignment(Qt.AlignTop)
        self.prefix_widget.setLayout(self.prefix_layout)
        scroll.setWidget(self.prefix_widget)

        layout.addWidget(scroll)

        # Apply prefix-to-suffix button
        self.apply_prefix_suffix_btn = QPushButton("Apply Prefix → Suffix Transform")
        self.apply_prefix_suffix_btn.clicked.connect(self.apply_prefix_to_suffix)
        layout.addWidget(self.apply_prefix_suffix_btn)

        group.setLayout(layout)
        return group

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

    def detect_prefixes(self):
        """Detect common prefixes in current file list."""
        files = self.file_list.get_all_files()
        if not files:
            self.show_warning("No Files", "No files loaded to analyze.")
            return

        # Get just the filenames
        filenames = [f.name for f in files]

        # Detect common prefixes
        prefix_counts = detect_common_prefixes(filenames)

        if not prefix_counts:
            self.show_info("No Prefixes", "No common prefixes detected.")
            return

        # Clear existing prefix checkboxes
        self.clear_prefix_checkboxes()

        # Create checkboxes for detected prefixes
        for prefix in sorted(prefix_counts.keys(), key=lambda x: prefix_counts[x], reverse=True):
            count = prefix_counts[prefix]
            checkbox = QCheckBox(f'{prefix} ({count} file{"s" if count > 1 else ""})')
            checkbox.setChecked(True)
            self.prefix_checkboxes[prefix] = checkbox
            self.prefix_layout.addWidget(checkbox)

        self.show_info("Prefixes Detected",
                      f"Found {len(prefix_counts)} common prefix pattern(s).\n"
                      "Uncheck any you don't want to process.")

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
        """Apply rename operation."""
        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected for renaming.")
            return

        # Confirm
        if not self.confirm_action(
            "Confirm Rename",
            f"Are you sure you want to rename {len(selected_files)} file(s)?\n\n"
            "This operation can be undone using 'Undo Last Operation'."
        ):
            return

        # Create rename worker
        from workers.rename_worker import RenameWorker

        self.worker_thread = RenameWorker(
            selected_files,
            prefix=self.prefix_input.text(),
            suffix=self.suffix_input.text(),
            rename_to=self.rename_input.text(),
            case_transform=self.get_case_transform()
        )

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
            self.show_info("Rename Complete", message)
            self.refresh_file_list()
        else:
            self.show_error("Rename Failed", message)

        self.emit_status(message)

    def apply_prefix_to_suffix(self):
        """Apply prefix-to-suffix transformation."""
        prefixes = self.get_selected_prefixes()
        if not prefixes:
            self.show_warning("No Prefixes", "Please select or enter at least one prefix.")
            return

        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected.")
            return

        # Filter files that match the prefixes
        matching_files = []
        for filepath in selected_files:
            if match_prefix(filepath.name, prefixes):
                matching_files.append(filepath)

        if not matching_files:
            self.show_warning("No Matches", f"No files found starting with any of the selected prefixes.")
            return

        # Confirm
        if not self.confirm_action(
            "Confirm Prefix → Suffix",
            f"This will move prefixes to suffixes for {len(matching_files)} file(s).\n\n"
            "Continue?"
        ):
            return

        # Create worker for prefix-to-suffix
        from workers.rename_worker import RenameWorker

        self.worker_thread = RenameWorker(
            matching_files,
            prefix_to_suffix=prefixes
        )

        self.worker_thread.progress.connect(self.emit_status)
        self.worker_thread.finished.connect(self.on_rename_finished)
        self.worker_thread.start()

        self.enable_controls(False)

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
