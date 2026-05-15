"""Bulk Rename tab — v0.17 visual refresh.

Functional behavior unchanged: same RenameWorker, same template/sequential/
standard mode logic, same prefix/suffix transposition, same companion-file
co-renames, same lint / normalize / undo / CSV / version-bump utilities.
Only the chrome was rewritten to v0.17 visual language.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from constants import (
    ALL_EXTENSION_CATEGORIES,
    CASE_LOWER,
    CASE_NONE,
    CASE_TITLE,
    CASE_UPPER,
)
from core.file_utils import get_files_in_directory
from core.name_transform import (
    DEFAULT_TEMPLATE,
    ProductionTemplate,
    bump_version,
    generate_new_filename,
    generate_sequential_filenames,
    replace_prefix,
    replace_suffix,
)
from core.pattern_matching import (
    detect_common_prefixes,
    detect_common_suffixes,
)
from models.operation_record import OperationRecord
from ui.tabs.base_tab import BaseTab
from ui.widgets.file_list_widget import FileListWidget
from ui.widgets.panel import Panel
from ui.widgets.path_card import PathCard
from ui.widgets.tab_header import TabHeader


def _make_section(eyebrow: str) -> Tuple[Panel, QVBoxLayout]:
    """Return (panel, content-layout) — panel has an eyebrow header at top."""
    panel = Panel()
    v = QVBoxLayout(panel)
    v.setContentsMargins(16, 14, 16, 14)
    v.setSpacing(10)
    eye = QLabel(eyebrow)
    eye.setObjectName("eyebrow")
    v.addWidget(eye)
    return panel, v


class BulkRenamerTab(BaseTab):
    """Tab for bulk file renaming operations."""

    def __init__(self, config, parent=None):
        """Initialize the bulk renamer tab."""
        self.extension_checkboxes: Dict[str, QCheckBox] = {}
        self.prefix_checkboxes: Dict[str, QCheckBox] = {}
        self.undo_stack: List[OperationRecord] = []
        self._current_template: Optional[ProductionTemplate] = None
        self.template_inputs: Dict[str, QLineEdit] = {}
        # Ordered list of extra directories added to the rename queue
        self._queued_dirs: List[Path] = []
        self._batch_root: Optional[Path] = None

        super().__init__(config, parent)

    def get_tab_name(self) -> str:
        return "Bulk Rename"

    # ─────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addWidget(self._build_source())

        # Most config sections live in a scrollable host so the file list and
        # footer stay pinned. Each section is its own Panel.
        root.addWidget(self._build_options_scroll(), stretch=1)

        # File list and footer live below the scroll, always visible.
        root.addWidget(self._build_file_list_panel(), stretch=1)
        root.addWidget(self._build_footer())

    # ── header ────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        header = TabHeader(
            eyebrow="02 · ORGANIZE · BULK RENAME",
            title="Bulk Rename",
            subtitle="Rename many files at once with detection, templates, sequencing, and transposition.",
        )
        self.preview_btn = header.add_action(
            "Preview changes", on_click=self.preview_changes,
        )
        self.apply_btn = header.add_action(
            "Apply rename", on_click=self.apply_rename, primary=True,
        )
        return header

    # ── source ────────────────────────────────────────────────────────────
    def _build_source(self) -> QWidget:
        wrap = Panel()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        self.path_card = PathCard("FOLDER")
        self.path_card.path_changed.connect(self.on_directory_changed)
        # Compatibility alias for any caller that used the old attribute name.
        self.dir_selector = self.path_card
        v.addWidget(self.path_card)

        opts_row = QHBoxLayout()
        opts_row.setSpacing(12)
        self.recursive_check = QCheckBox("Recursive scan")
        self.recursive_check.setChecked(False)
        self.recursive_check.setToolTip("Include files from all subfolders, not just the top level")
        self.recursive_check.stateChanged.connect(lambda _s: self.refresh_file_list())
        opts_row.addWidget(self.recursive_check)
        opts_row.addStretch()
        v.addLayout(opts_row)
        return wrap

    # ── options scroll area ──────────────────────────────────────────────
    def _build_options_scroll(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("optsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        v.addWidget(self._build_queue_panel())
        v.addWidget(self._build_batch_section())
        v.addWidget(self.create_profile_bar())
        v.addWidget(self.create_extension_filter_group())
        v.addWidget(self._build_mode_panel())

        # Stacked rename options — one Panel per mode.
        self.rename_stack = QStackedWidget()
        self.rename_stack.addWidget(self.create_rename_options_group())      # 0 — standard
        self.rename_stack.addWidget(self.create_sequential_options_group())  # 1 — sequential
        self.rename_stack.addWidget(self.create_template_options_group())    # 2 — template
        v.addWidget(self.rename_stack)

        v.addWidget(self.create_companion_options_group())
        v.addWidget(self._build_copy_mode_section())
        self.prefix_group_widget = self.create_transposition_group()
        v.addWidget(self.prefix_group_widget)
        v.addStretch()

        scroll.setWidget(host)
        return scroll

    # ── queue panel (sub-section of options scroll) ──────────────────────
    def _build_queue_panel(self) -> QWidget:
        panel, v = _make_section(
            "DIRECTORY QUEUE  ·  OPTIONAL — FILES FROM ALL QUEUED DIRS ARE MERGED"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.add_dir_btn = QPushButton("Add current to queue")
        self.add_dir_btn.setObjectName("ghostBtn")
        self.add_dir_btn.setToolTip("Add the directory shown above to the multi-directory queue")
        self.add_dir_btn.clicked.connect(self._add_dir_to_queue)
        btn_row.addWidget(self.add_dir_btn)
        self.remove_dir_btn = QPushButton("Remove selected")
        self.remove_dir_btn.setObjectName("ghostBtn")
        self.remove_dir_btn.setToolTip("Remove the selected directory from the queue")
        self.remove_dir_btn.clicked.connect(self._remove_queued_dir)
        btn_row.addWidget(self.remove_dir_btn)
        self.clear_queue_btn = QPushButton("Clear queue")
        self.clear_queue_btn.setObjectName("ghostBtn")
        self.clear_queue_btn.setToolTip("Remove all directories from the queue")
        self.clear_queue_btn.clicked.connect(self._clear_queue)
        btn_row.addWidget(self.clear_queue_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self.queue_list = QListWidget()
        self.queue_list.setMaximumHeight(90)
        self.queue_list.setToolTip("Files from all directories below are merged into the file list")
        v.addWidget(self.queue_list)
        return panel

    # ── batch mode section ───────────────────────────────────────────────
    def _build_batch_section(self) -> QWidget:
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self.batch_mode_chk = QCheckBox("Batch mode — process first-level subdirectories")
        self.batch_mode_chk.setToolTip(
            "Select a root folder and check which subdirectories to process in one run"
        )
        self.batch_mode_chk.toggled.connect(self._on_batch_mode_toggled)
        v.addWidget(self.batch_mode_chk)

        self.batch_panel, bp_layout = _make_section("BATCH MODE OPTIONS")
        self.batch_root_selector = PathCard("ROOT FOLDER")
        self.batch_root_selector.path_changed.connect(self._on_batch_root_changed)
        bp_layout.addWidget(self.batch_root_selector)

        self.batch_subdir_list = QListWidget()
        self.batch_subdir_list.setMaximumHeight(140)
        bp_layout.addWidget(self.batch_subdir_list)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        self.batch_check_all_btn = QPushButton("Check all")
        self.batch_check_all_btn.setObjectName("ghostBtn")
        self.batch_check_all_btn.setToolTip("Select all subdirectories for batch renaming")
        self.batch_check_all_btn.clicked.connect(self._batch_check_all)
        ctrl_row.addWidget(self.batch_check_all_btn)
        self.batch_uncheck_all_btn = QPushButton("Uncheck all")
        self.batch_uncheck_all_btn.setObjectName("ghostBtn")
        self.batch_uncheck_all_btn.setToolTip("Deselect all subdirectories")
        self.batch_uncheck_all_btn.clicked.connect(self._batch_uncheck_all)
        ctrl_row.addWidget(self.batch_uncheck_all_btn)
        ctrl_row.addStretch()
        self.run_batch_btn = QPushButton("Run batch rename")
        self.run_batch_btn.setProperty("role", "primary")
        self.run_batch_btn.setToolTip("Apply the current rename settings to each checked subdirectory")
        self.run_batch_btn.clicked.connect(self._run_batch)
        ctrl_row.addWidget(self.run_batch_btn)
        bp_layout.addLayout(ctrl_row)

        self.batch_panel.setVisible(False)
        v.addWidget(self.batch_panel)
        return host

    # ── rename mode panel ────────────────────────────────────────────────
    def _build_mode_panel(self) -> QWidget:
        panel, v = _make_section("RENAME MODE")
        row = QHBoxLayout()
        row.setSpacing(20)
        self.mode_btn_group = QButtonGroup()
        self.mode_standard_radio = QRadioButton("Standard")
        self.mode_standard_radio.setToolTip("Add/remove prefix, suffix, case changes, and replace operations")
        self.mode_sequential_radio = QRadioButton("Number files")
        self.mode_sequential_radio.setToolTip("Replace filenames with a base name plus sequential numbers")
        self.mode_template_radio = QRadioButton("Template")
        self.mode_template_radio.setToolTip("Build filenames from production tokens (project, episode, shot, etc.)")
        self.mode_btn_group.addButton(self.mode_standard_radio, 0)
        self.mode_btn_group.addButton(self.mode_sequential_radio, 1)
        self.mode_btn_group.addButton(self.mode_template_radio, 2)
        self.mode_standard_radio.setChecked(True)
        for r in (self.mode_standard_radio, self.mode_sequential_radio, self.mode_template_radio):
            r.toggled.connect(self._on_mode_changed)
            row.addWidget(r)
        row.addStretch()
        v.addLayout(row)
        return panel

    # ── file list panel ──────────────────────────────────────────────────
    def _build_file_list_panel(self) -> QWidget:
        panel, v = _make_section("FILES")
        self.file_list = FileListWidget()
        self.file_list.setMinimumHeight(120)
        v.addWidget(self.file_list)
        return panel

    # ── footer (utility buttons) ─────────────────────────────────────────
    def _build_footer(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("footer")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(8)

        self.bump_version_btn = QPushButton("Bump version")
        self.bump_version_btn.setObjectName("ghostBtn")
        self.bump_version_btn.setToolTip(
            "Increment the trailing version token on all selected files.\n"
            "Recognises _v##, -v##, ' v##', _V##, .v##, etc."
        )
        self.bump_version_btn.clicked.connect(self.apply_bump_version)
        h.addWidget(self.bump_version_btn)

        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setObjectName("ghostBtn")
        self.undo_btn.setToolTip("Reverse the most recent rename operation")
        self.undo_btn.clicked.connect(self.undo_last_operation)
        self.undo_btn.setEnabled(False)
        h.addWidget(self.undo_btn)

        self.open_csv_btn = QPushButton("Open latest CSV")
        self.open_csv_btn.setObjectName("ghostBtn")
        self.open_csv_btn.setToolTip("Open the most recent rename log CSV in this directory")
        self.open_csv_btn.clicked.connect(self.open_latest_csv)
        h.addWidget(self.open_csv_btn)

        self.normalize_btn = QPushButton("Normalize incoming")
        self.normalize_btn.setObjectName("ghostBtn")
        self.normalize_btn.setToolTip(
            "Strip common bad prefixes/suffixes from selected files "
            "(e.g. '_COPY', 'Copy of ')"
        )
        self.normalize_btn.clicked.connect(self.normalize_incoming)
        h.addWidget(self.normalize_btn)

        self.lint_btn = QPushButton("Lint folder")
        self.lint_btn.setObjectName("ghostBtn")
        self.lint_btn.setToolTip("Check filenames in the current directory for issues")
        self.lint_btn.clicked.connect(self.lint_folder)
        h.addWidget(self.lint_btn)

        h.addStretch()
        return wrap

    # ── profile bar ───────────────────────────────────────────────────────

    def create_profile_bar(self) -> Panel:
        """Naming profile selector + management buttons."""
        panel, v = _make_section("NAMING PROFILE")
        row = QHBoxLayout()
        row.setSpacing(10)

        active_lbl = QLabel("Active")
        active_lbl.setObjectName("cardSub")
        row.addWidget(active_lbl)

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.setToolTip(
            "The active profile drives the Template rename mode and "
            "the conformance check in Lint Folder."
        )
        self.profile_combo.addItem("(None)")
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        row.addWidget(self.profile_combo)

        row.addStretch()

        save_btn = QPushButton("Save as profile\u2026")
        save_btn.setObjectName("ghostBtn")
        save_btn.setToolTip("Save the current template settings as a new named profile")
        save_btn.clicked.connect(self._save_as_profile)
        row.addWidget(save_btn)

        manage_btn = QPushButton("Manage profiles\u2026")
        manage_btn.setObjectName("ghostBtn")
        manage_btn.clicked.connect(self._manage_profiles)
        row.addWidget(manage_btn)

        v.addLayout(row)
        return panel

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
        from PySide6.QtWidgets import QInputDialog
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
        dialog.exec()
        active = self.config.get('naming.active_profile')
        self._load_profile_combo()
        if active:
            idx = self.profile_combo.findText(active)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        self._rebuild_template_panel(self._get_active_profile())

    # ── template mode panel ───────────────────────────────────────────────

    def create_template_options_group(self) -> Panel:
        """Token-field panel that composes filenames from the active profile."""
        panel, layout = _make_section("TEMPLATE TOKENS")

        # Scrollable token input area — rebuilt when profile changes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(165)
        self.template_tokens_widget = QWidget()
        self.template_tokens_layout = QFormLayout()
        self.template_tokens_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self.template_tokens_widget.setLayout(self.template_tokens_layout)
        scroll.setWidget(self.template_tokens_widget)
        layout.addWidget(scroll)

        self.template_preview_label = QLabel("Preview: \u2014")
        self.template_preview_label.setObjectName("cardSub")
        layout.addWidget(self.template_preview_label)

        self._rebuild_template_panel(None)
        return panel

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
        # Preview now works in every mode — Standard, Number Files, and
        # Template all compute their own "what-would-rename-to" projection
        # and feed it to the same PreviewDialog. Disabling the button in
        # non-Standard modes was the source of the "preview doesn't pop up"
        # confusion the user reported.
        self.preview_btn.setEnabled(True)

    # ── extension filters ─────────────────────────────────────────────────

    def create_extension_filter_group(self) -> Panel:
        """Create the extension filter panel."""
        panel, v = _make_section("FILE TYPE FILTERS")

        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(14)
        for category in ['images', 'documents', 'videos', 'audio', 'archives']:
            checkbox = QCheckBox(category.capitalize())
            checkbox.stateChanged.connect(self.refresh_file_list)
            self.extension_checkboxes[category] = checkbox
            preset_layout.addWidget(checkbox)
        preset_layout.addStretch()
        v.addLayout(preset_layout)

        custom_layout = QHBoxLayout()
        custom_layout.setSpacing(8)
        custom_lbl = QLabel("Custom extensions")
        custom_lbl.setObjectName("cardSub")
        custom_layout.addWidget(custom_lbl)
        self.custom_ext_input = QLineEdit()
        self.custom_ext_input.setPlaceholderText("e.g., .txt, .py, .md")
        custom_layout.addWidget(self.custom_ext_input, stretch=1)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("ghostBtn")
        apply_btn.clicked.connect(self.refresh_file_list)
        custom_layout.addWidget(apply_btn)
        v.addLayout(custom_layout)

        return panel

    # ── standard rename panel ─────────────────────────────────────────────

    def create_rename_options_group(self) -> Panel:
        """Create the standard rename options panel."""
        panel, v = _make_section("STANDARD RENAME")

        def _row(label: str, w):
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setObjectName("cardSub")
            lbl.setFixedWidth(60)
            row.addWidget(lbl)
            row.addWidget(w, stretch=1)
            return row

        self.rename_input = QLineEdit()
        self.rename_input.setPlaceholderText(
            "Replace entire base name (prefix/suffix still applied)"
        )
        v.addLayout(_row("Rename to", self.rename_input))

        self.prefix_input = QLineEdit()
        v.addLayout(_row("Prefix", self.prefix_input))

        self.suffix_input = QLineEdit()
        v.addLayout(_row("Suffix", self.suffix_input))

        case_layout = QHBoxLayout()
        case_lbl = QLabel("Case")
        case_lbl.setObjectName("cardSub")
        case_lbl.setFixedWidth(60)
        case_layout.addWidget(case_lbl)
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
        for r in (self.case_none_radio, self.case_upper_radio,
                  self.case_lower_radio, self.case_title_radio):
            case_layout.addWidget(r)
        case_layout.addStretch()
        v.addLayout(case_layout)

        # Replace prefix
        rp_eye = QLabel("REPLACE PREFIX")
        rp_eye.setObjectName("eyebrow")
        v.addWidget(rp_eye)
        rp_row = QHBoxLayout()
        rp_row.setSpacing(8)
        rp_find_lbl = QLabel("Find")
        rp_find_lbl.setObjectName("cardSub")
        rp_find_lbl.setFixedWidth(60)
        rp_row.addWidget(rp_find_lbl)
        self.replace_prefix_find = QLineEdit()
        self.replace_prefix_find.setPlaceholderText("e.g. OLD_")
        self.replace_prefix_find.setToolTip("Text at the start of the stem to find and replace")
        rp_row.addWidget(self.replace_prefix_find, stretch=1)
        rp_repl_lbl = QLabel("Replace")
        rp_repl_lbl.setObjectName("cardSub")
        rp_row.addWidget(rp_repl_lbl)
        self.replace_prefix_with = QLineEdit()
        self.replace_prefix_with.setPlaceholderText("e.g. NEW_")
        self.replace_prefix_with.setToolTip("Replacement text (leave empty to remove the prefix)")
        rp_row.addWidget(self.replace_prefix_with, stretch=1)
        v.addLayout(rp_row)

        # Replace suffix
        rs_eye = QLabel("REPLACE SUFFIX")
        rs_eye.setObjectName("eyebrow")
        v.addWidget(rs_eye)
        rs_row = QHBoxLayout()
        rs_row.setSpacing(8)
        rs_find_lbl = QLabel("Find")
        rs_find_lbl.setObjectName("cardSub")
        rs_find_lbl.setFixedWidth(60)
        rs_row.addWidget(rs_find_lbl)
        self.replace_suffix_find = QLineEdit()
        self.replace_suffix_find.setPlaceholderText("e.g. _v01")
        self.replace_suffix_find.setToolTip("Text at the end of the stem to find and replace")
        rs_row.addWidget(self.replace_suffix_find, stretch=1)
        rs_repl_lbl = QLabel("Replace")
        rs_repl_lbl.setObjectName("cardSub")
        rs_row.addWidget(rs_repl_lbl)
        self.replace_suffix_with = QLineEdit()
        self.replace_suffix_with.setPlaceholderText("e.g. _v02")
        self.replace_suffix_with.setToolTip("Replacement text (leave empty to remove the suffix)")
        rs_row.addWidget(self.replace_suffix_with, stretch=1)
        v.addLayout(rs_row)

        return panel

    # ── sequential numbering panel ────────────────────────────────────────

    def create_sequential_options_group(self) -> Panel:
        """Create the sequential-numbering options panel."""
        panel, layout = _make_section("NUMBER FILES")

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        base_lbl = QLabel("Base name")
        base_lbl.setObjectName("cardSub")
        base_lbl.setFixedWidth(70)
        row1.addWidget(base_lbl)
        self.seq_base_input = QLineEdit()
        self.seq_base_input.setPlaceholderText("e.g. HERO or SCENE_01")
        row1.addWidget(self.seq_base_input, stretch=1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        start_lbl = QLabel("Start at")
        start_lbl.setObjectName("cardSub")
        start_lbl.setFixedWidth(70)
        row2.addWidget(start_lbl)
        self.seq_start_spin = QSpinBox()
        self.seq_start_spin.setRange(0, 99999)
        self.seq_start_spin.setValue(1)
        row2.addWidget(self.seq_start_spin)
        row2.addSpacing(20)
        pad_lbl = QLabel("Padding")
        pad_lbl.setObjectName("cardSub")
        row2.addWidget(pad_lbl)
        self.seq_padding_spin = QSpinBox()
        self.seq_padding_spin.setRange(1, 8)
        self.seq_padding_spin.setValue(3)
        row2.addWidget(self.seq_padding_spin)
        row2.addSpacing(20)
        sep_lbl = QLabel("Separator")
        sep_lbl.setObjectName("cardSub")
        row2.addWidget(sep_lbl)
        self.seq_separator_input = QLineEdit("_")
        self.seq_separator_input.setMaximumWidth(60)
        row2.addWidget(self.seq_separator_input)
        row2.addStretch()
        layout.addLayout(row2)

        preview_label = QLabel("Preview: HERO_001.mov, HERO_002.mov, \u2026")
        preview_label.setObjectName("cardSub")
        self.seq_preview_label = preview_label
        layout.addWidget(preview_label)

        for widget in (self.seq_base_input, self.seq_separator_input):
            widget.textChanged.connect(self._update_seq_preview)
        for widget in (self.seq_start_spin, self.seq_padding_spin):
            widget.valueChanged.connect(self._update_seq_preview)

        return panel

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

    def create_companion_options_group(self) -> Panel:
        """Checkboxes to control sidecar / caption co-rename, hidden-file inclusion,
        and the prefix/suffix delimiter override."""
        panel, layout = _make_section("RENAME BEHAVIOUR")

        # Row 1 \u2014 sidecar / caption companion renaming
        comp_row = QHBoxLayout()
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
        comp_row.addWidget(self.rename_sidecars_chk)
        comp_row.addWidget(self.rename_captions_chk)
        comp_row.addStretch()
        layout.addLayout(comp_row)

        # Row 2 \u2014 hidden-file opt-in + delimiter override
        opts_row = QHBoxLayout()
        self.include_hidden_chk = QCheckBox("Include hidden files (start with '.')")
        self.include_hidden_chk.setChecked(False)
        self.include_hidden_chk.setToolTip(
            "By default, files whose name starts with '.' are skipped during\n"
            "rename \u2014 they are usually OS / config files (.DS_Store, .gitignore,\n"
            ".env) that you didn't mean to touch. Tick this to include them."
        )
        opts_row.addWidget(self.include_hidden_chk)

        opts_row.addSpacing(20)
        delim_lbl = QLabel("Delimiter for prefix/suffix detection")
        delim_lbl.setObjectName("cardSub")
        opts_row.addWidget(delim_lbl)
        self.delimiter_combo = QComboBox()
        # Order matters \u2014 first item is the default. 'auto' uses the
        # dataset's most-common delimiter via detect_dominant_delimiter.
        self.delimiter_combo.addItem("auto", "auto")
        self.delimiter_combo.addItem("_  (underscore)", "_")
        self.delimiter_combo.addItem("-  (dash)", "-")
        self.delimiter_combo.addItem("space", " ")
        self.delimiter_combo.addItem(".  (dot)", ".")
        self.delimiter_combo.setToolTip(
            "Controls how the Detect button finds common prefixes / suffixes.\n"
            "'auto' (default) picks the delimiter that appears in the most\n"
            "filenames in the current folder."
        )
        opts_row.addWidget(self.delimiter_combo)
        opts_row.addStretch()
        layout.addLayout(opts_row)

        return panel

    # ── copy mode section ────────────────────────────────────────────────

    def _build_copy_mode_section(self) -> QWidget:
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self.copy_mode_chk = QCheckBox("Copy files with new names instead of renaming")
        self.copy_mode_chk.setToolTip(
            "Instead of renaming in place, copy each file to a destination\n"
            "folder with the new name. Originals stay untouched."
        )
        self.copy_mode_chk.toggled.connect(self._on_copy_mode_toggled)
        v.addWidget(self.copy_mode_chk)

        self.copy_dest_card = PathCard("COPY DESTINATION")
        self.copy_dest_card.setVisible(False)
        v.addWidget(self.copy_dest_card)
        return host

    def _on_copy_mode_toggled(self, checked: bool):
        self.copy_dest_card.setVisible(checked)

    # ── transposition panel ───────────────────────────────────────────────

    def create_transposition_group(self) -> Panel:
        """Bidirectional prefix ↔ suffix transposition panel."""
        panel, layout = _make_section("PREFIX / SUFFIX TRANSPOSITION")

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
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.prefix_widget = QWidget()
        self.prefix_layout = QVBoxLayout()
        self.prefix_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.prefix_widget.setLayout(self.prefix_layout)
        scroll.setWidget(self.prefix_widget)
        layout.addWidget(scroll)

        # No standalone apply button \u2014 tokens checked here ride along with the
        # next "Apply Rename" so the user can compose transposition with
        # prefix / suffix / case changes in one click.
        hint = QLabel(
            "Selected tokens will be moved as part of the next Apply rename "
            "(combined with Prefix / Suffix / Rename / Case settings above)."
        )
        hint.setWordWrap(True)
        hint.setObjectName("cardSub")
        layout.addWidget(hint)

        return panel

    def _on_transpose_direction_changed(self):
        if self.transpose_p2s_radio.isChecked():
            self.manual_token_label.setText("Manual prefix(es):")
            self.manual_prefix_input.setPlaceholderText("e.g., DRAFT_, WIP_, TEMP_")
        else:
            self.manual_token_label.setText("Manual suffix(es):")
            self.manual_prefix_input.setPlaceholderText("e.g., _DRAFT, _WIP, _FINAL")
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
        recursive = self.recursive_check.isChecked()

        # Primary directory
        all_dirs = [directory] + [d for d in self._queued_dirs if d != directory]

        if len(all_dirs) == 1:
            files = get_files_in_directory(directory, extensions, recursive)
            self.file_list.set_files(files, relative_to=directory if recursive else None)
        else:
            # Multi-directory: load from each dir; display paths relative to
            # the nearest common ancestor so the folder name acts as a prefix.
            all_files: List[Path] = []
            for d in all_dirs:
                if d.exists():
                    all_files.extend(get_files_in_directory(d, extensions, recursive))
            try:
                rel_root: Optional[Path] = all_dirs[0].parent
                for d in all_dirs[1:]:
                    while not str(d).startswith(str(rel_root)):
                        rel_root = rel_root.parent
            except Exception:
                rel_root = None
            self.file_list.set_files(all_files, relative_to=rel_root)

        n = self.file_list.table.rowCount()
        dir_suffix = f" from {len(all_dirs)} directories" if len(all_dirs) > 1 else ""
        self.emit_status(f"Loaded {n} files{dir_suffix}")

    # ── multi-directory queue ─────────────────────────────────────────────

    def _add_dir_to_queue(self):
        if not self.current_directory:
            self.show_warning("No Directory", "Select a directory first.")
            return
        p = Path(self.current_directory)
        if p in self._queued_dirs:
            return
        self._queued_dirs.append(p)
        item = QListWidgetItem(str(p))
        item.setToolTip(str(p))
        self.queue_list.addItem(item)
        self.refresh_file_list()

    def _remove_queued_dir(self):
        row = self.queue_list.currentRow()
        if row < 0:
            return
        self.queue_list.takeItem(row)
        self._queued_dirs.pop(row)
        self.refresh_file_list()

    def _clear_queue(self):
        self._queued_dirs.clear()
        self.queue_list.clear()
        self.refresh_file_list()

    # ── batch mode ────────────────────────────────────────────────────────

    def _on_batch_mode_toggled(self, checked: bool):
        self.batch_panel.setVisible(checked)

    def _on_batch_root_changed(self, directory: str):
        self._batch_root = Path(directory)
        self.batch_subdir_list.clear()
        if not self._batch_root.is_dir():
            return
        for d in sorted(self._batch_root.iterdir()):
            if d.is_dir() and not d.name.startswith('.'):
                item = QListWidgetItem(d.name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self.batch_subdir_list.addItem(item)

    def _batch_check_all(self):
        for i in range(self.batch_subdir_list.count()):
            self.batch_subdir_list.item(i).setCheckState(Qt.Checked)

    def _batch_uncheck_all(self):
        for i in range(self.batch_subdir_list.count()):
            self.batch_subdir_list.item(i).setCheckState(Qt.Unchecked)

    def _run_batch(self):
        """Run the current rename settings across each checked subdirectory."""
        if not self._batch_root:
            self.show_warning("No Root", "Select a root folder in Batch Mode.")
            return

        checked_dirs = []
        for i in range(self.batch_subdir_list.count()):
            item = self.batch_subdir_list.item(i)
            if item.checkState() == Qt.Checked:
                checked_dirs.append(self._batch_root / item.text())

        if not checked_dirs:
            self.show_warning("None Selected", "Check at least one subdirectory.")
            return

        from PySide6.QtWidgets import QProgressDialog

        from workers.rename_worker import RenameWorker

        active_extensions = self.get_active_extensions()
        extensions = active_extensions if active_extensions else None
        mode = self.mode_btn_group.checkedId()

        progress = QProgressDialog(
            "Running batch rename…", "Cancel", 0, len(checked_dirs), self
        )
        progress.setWindowTitle("Batch Rename")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        errors = []
        for idx, subdir in enumerate(checked_dirs):
            if progress.wasCanceled():
                break
            progress.setLabelText(f"Processing {subdir.name}…")
            progress.setValue(idx)
            QApplication.processEvents()

            try:
                files = get_files_in_directory(subdir, extensions, False)
                if not files:
                    continue

                if mode == 1:
                    base = self.seq_base_input.text().strip()
                    if not base:
                        errors.append(f"{subdir.name}: no base name set")
                        continue
                    pairs_seq = generate_sequential_filenames(
                        [f.name for f in files],
                        base_name=base,
                        start=self.seq_start_spin.value(),
                        padding=self.seq_padding_spin.value(),
                        separator=self.seq_separator_input.text(),
                    )
                    direct = [(files[i], new) for i, (_, new) in enumerate(pairs_seq)]
                elif mode == 2:
                    composed = self._get_template_composed_name()
                    if not composed:
                        errors.append(f"{subdir.name}: template incomplete")
                        continue
                    sep = self._current_template.separator if self._current_template else '_'
                    direct = [
                        (f, f"{composed}{sep}{str(j + 1).zfill(3)}{f.suffix}")
                        for j, f in enumerate(files)
                    ]
                else:
                    direct = None

                if direct is not None:
                    worker = RenameWorker(
                        [],
                        direct_renames=direct,
                        rename_sidecars=self.rename_sidecars_chk.isChecked(),
                        rename_captions=self.rename_captions_chk.isChecked(),
                    )
                else:
                    worker = RenameWorker(
                        files,
                        prefix=self.prefix_input.text(),
                        suffix=self.suffix_input.text(),
                        rename_to=self.rename_input.text(),
                        case_transform=self.get_case_transform(),
                        find_prefix=self.replace_prefix_find.text(),
                        replace_prefix_with=self.replace_prefix_with.text(),
                        find_suffix=self.replace_suffix_find.text(),
                        replace_suffix_with=self.replace_suffix_with.text(),
                        rename_sidecars=self.rename_sidecars_chk.isChecked(),
                        rename_captions=self.rename_captions_chk.isChecked(),
                    )

                # Run synchronously in the worker thread and wait
                worker.run()

            except Exception as exc:
                errors.append(f"{subdir.name}: {exc}")

        progress.setValue(len(checked_dirs))

        if errors:
            self.show_warning(
                "Batch Errors",
                "Some directories had errors:\n\n" + "\n".join(errors)
            )
        else:
            self.show_info("Batch Complete",
                           f"Processed {len(checked_dirs)} director(ies) successfully.")

        self.refresh_file_list()

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
        """Show the would-be rename results for the active mode.

        Works in all three rename modes (Standard / Number Files / Template),
        and applies the same hidden-file filter and prefix→suffix /
        suffix→prefix transposition tokens that ``Apply Rename`` will use.
        """
        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected for preview.")
            return

        # Apply the dot-file skip the same way Apply Rename does, so what
        # the user sees in the preview matches what will actually happen.
        include_hidden = self.include_hidden_chk.isChecked()
        if not include_hidden:
            from core.file_utils import is_hidden_file
            selected_files = [f for f in selected_files if not is_hidden_file(f.name)]
        if not selected_files:
            self.show_info(
                "All Files Hidden",
                "All selected files are hidden (start with '.').\n"
                "Tick 'Include hidden files' to rename them."
            )
            return

        from ui.dialogs.preview_dialog import PreviewDialog
        mode = self.mode_btn_group.checkedId()
        preview_data: List[Tuple[str, str]] = []

        if mode == 1:
            # Number Files mode
            base = self.seq_base_input.text().strip()
            if not base:
                self.show_warning(
                    "Base Name Required",
                    "Enter a base name for sequential numbering before previewing."
                )
                return
            pairs = generate_sequential_filenames(
                [f.name for f in selected_files],
                base_name=base,
                start=self.seq_start_spin.value(),
                padding=self.seq_padding_spin.value(),
                separator=self.seq_separator_input.text(),
            )
            preview_data = list(pairs)

        elif mode == 2:
            # Template mode
            base = self._get_template_composed_name()
            if not base:
                self.show_warning(
                    "Incomplete Template",
                    "Fill in at least one template token before previewing."
                )
                return
            sep = self._current_template.separator if self._current_template else '_'
            if len(selected_files) == 1:
                preview_data = [
                    (selected_files[0].name, f"{base}{selected_files[0].suffix}")
                ]
            else:
                preview_data = [
                    (f.name, f"{base}{sep}{str(i + 1).zfill(3)}{f.suffix}")
                    for i, f in enumerate(selected_files)
                ]

        else:
            # Standard mode — including any prefix→suffix / suffix→prefix
            # tokens currently selected in the transposition group. Mirrors
            # RenameWorker._build_work_list so what you see is what you get.
            from core.name_transform import move_prefix_to_suffix, move_suffix_to_prefix
            from core.pattern_matching import match_prefix, match_suffix
            tokens = self.get_selected_prefixes()
            is_p2s = self.transpose_p2s_radio.isChecked()
            fp_find = self.replace_prefix_find.text()
            fp_repl = self.replace_prefix_with.text()
            fs_find = self.replace_suffix_find.text()
            fs_repl = self.replace_suffix_with.text()
            for filepath in selected_files:
                current = filepath.name
                if tokens:
                    if is_p2s:
                        m = match_prefix(current, tokens)
                        if m:
                            current = move_prefix_to_suffix(current, m)
                    else:
                        m = match_suffix(current, tokens)
                        if m:
                            current = move_suffix_to_prefix(current, m)
                if fp_find:
                    current = replace_prefix(current, fp_find, fp_repl)
                if fs_find:
                    current = replace_suffix(current, fs_find, fs_repl)
                new_name = generate_new_filename(
                    current,
                    prefix=self.prefix_input.text(),
                    suffix=self.suffix_input.text(),
                    rename_to=self.rename_input.text(),
                    case_transform=self.get_case_transform(),
                )
                preview_data.append((filepath.name, new_name))

        dialog = PreviewDialog(preview_data, self)
        dialog.exec()

    # ── apply rename ──────────────────────────────────────────────────────

    def apply_rename(self):
        """Apply rename — dispatches to standard, sequential, or template mode."""
        selected_files = self.file_list.get_selected_files()
        if not selected_files:
            self.show_warning("No Files", "No files selected for renaming.")
            return

        from workers.rename_worker import RenameWorker

        copy_mode = self.copy_mode_chk.isChecked()
        copy_dest = None
        if copy_mode:
            dest_text = self.copy_dest_card.get_path()
            if not dest_text or not Path(dest_text).is_dir():
                self.show_warning(
                    "No destination",
                    "Choose a valid destination folder for the copies.",
                )
                return
            copy_dest = Path(dest_text)

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
                copy_mode=copy_mode,
                copy_dest=copy_dest,
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
                copy_mode=copy_mode,
                copy_dest=copy_dest,
                rename_sidecars=self.rename_sidecars_chk.isChecked(),
                rename_captions=self.rename_captions_chk.isChecked(),
            )

        else:
            # Standard mode — picks up any transposition tokens checked in
            # the Prefix / Suffix Transposition group, plus the hidden-file
            # opt-in. There is no separate "Apply Prefix → Suffix" path
            # anymore; everything funnels through this one Apply Rename.
            tokens = self.get_selected_prefixes()
            is_p2s = self.transpose_p2s_radio.isChecked()
            prefix_to_suffix = tokens if (tokens and is_p2s) else None
            suffix_to_prefix = tokens if (tokens and not is_p2s) else None

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
                prefix_to_suffix=prefix_to_suffix,
                suffix_to_prefix=suffix_to_prefix,
                find_prefix=self.replace_prefix_find.text(),
                replace_prefix_with=self.replace_prefix_with.text(),
                find_suffix=self.replace_suffix_find.text(),
                replace_suffix_with=self.replace_suffix_with.text(),
                copy_mode=copy_mode,
                copy_dest=copy_dest,
                include_hidden=self.include_hidden_chk.isChecked(),
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
            self.show_info(
                "No Versions Found",
                "None of the selected files have a recognisable trailing version "
                "token. Supported formats: _v##, -v##, ' v##', _V##, .v##."
            )
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

    # The standalone apply_transposition / apply_prefix_to_suffix flow was
    # removed \u2014 transposition tokens now ride along with Apply Rename via
    # RenameWorker(prefix_to_suffix=..., suffix_to_prefix=...). One Undo
    # entry, one CSV log, one click.

    # ── CSV log ───────────────────────────────────────────────────────────

    def open_latest_csv(self):
        import glob
        import subprocess
        import sys
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
        if dialog.exec() != NormalizeDialog.Accepted:
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
            self.path_card.set_path(last_dir)
            self.set_directory(last_dir)

        recursive = self.config.get_tab_setting('bulk_renamer', 'recursive_default', False)
        self.recursive_check.setChecked(recursive)

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
                                    self.recursive_check.isChecked())
        filters = {
            category: checkbox.isChecked()
            for category, checkbox in self.extension_checkboxes.items()
        }
        self.config.set_tab_setting('bulk_renamer', 'extension_filters', filters)
        self.config.set_tab_setting('bulk_renamer', 'case_transform_default',
                                    self.get_case_transform())
