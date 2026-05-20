"""Group by Pattern tab — v0.17 visual refresh.

Functional behavior unchanged: same ScanWorker, same OrganizeWorker, same
drag-and-drop tree, same context-menu actions, same undo stack. Only the
chrome was rewritten to v0.17 visual language.
"""

from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.pattern_matching import (
    ALL_PRESETS,
    PRESET_STANDARD,
    SequenceGroup,
    detect_image_sequences,
)
from ui.tabs.base_tab import BaseTab
from ui.widgets.panel import Panel
from ui.widgets.path_card import PathCard
from ui.widgets.tab_header import TabHeader

_UNSORTED = "[UNSORTED]"


class FileOrganizerTab(BaseTab):
    """Tab for organizing files into folders by naming patterns."""

    def __init__(self, config, parent=None):
        """Initialize the file organizer tab."""
        self.file_groups: Dict[str, Dict[str, List[Path]]] = {}
        self.unsorted_files: Dict[str, List[Path]] = {}
        # subdir_path → {seq_key: SequenceGroup}  (files stored as filenames)
        self.file_sequences: Dict[str, Dict[str, SequenceGroup]] = {}
        # Each entry is a list of (file_path, subdir, from_group, to_group) tuples
        self._move_undo_stack: List = []
        self._batch_root: Optional[Path] = None

        super().__init__(config, parent)

    def get_tab_name(self) -> str:
        return "Group by Pattern"

    # UI
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addWidget(self._build_source())
        root.addWidget(self._build_controls())
        root.addWidget(self._build_batch_panel())
        root.addWidget(self._build_tree(), stretch=1)
        root.addWidget(self._build_footer())

    # ── header ────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        header = TabHeader(
            eyebrow="02 · ORGANIZE · GROUP BY PATTERN",
            title="Group by Pattern",
            subtitle="Sort files into folders by their naming patterns.",
        )
        self.undo_move_btn = header.add_action(
            "Undo last move",
            on_click=self.undo_last_move,
            enabled=False,
            tooltip="Undo the most recent drag-and-drop or context-menu move",
        )
        self.new_group_btn = header.add_action(
            "Create group",
            on_click=self.create_new_group,
            enabled=False,
            tooltip="Create an empty group to drag files into",
        )
        self.organize_btn = header.add_action(
            "Organize files",
            on_click=self.organize_files,
            primary=True,
            enabled=False,
            tooltip="Move files into their assigned group folders on disk",
        )
        return header

    # ── source ────────────────────────────────────────────────────────────
    def _build_source(self) -> QWidget:
        # Wrapper so PathCard signal still calls the existing on_directory_changed.
        self.path_card = PathCard("FOLDER")
        self.path_card.path_changed.connect(self.on_directory_changed)
        # Keep a back-compat alias so any future code using dir_selector still works.
        self.dir_selector = self.path_card
        return self.path_card

    # ── controls (preset + batch toggle + scan) ──────────────────────────
    def _build_controls(self) -> QWidget:
        wrap = Panel()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        eye = QLabel("CONTROLS")
        eye.setObjectName("eyebrow")
        v.addWidget(eye)

        row = QHBoxLayout()
        row.setSpacing(14)

        preset_lbl = QLabel("Grouping preset")
        preset_lbl.setObjectName("cardSub")
        row.addWidget(preset_lbl)

        self.preset_combo = QComboBox()
        for p in ALL_PRESETS:
            self.preset_combo.addItem(p.name, userData=p)
        self.preset_combo.setToolTip(
            "Standard: group by underscore prefix\nAE Render Output: strip trailing _#### frame numbers before grouping"
        )
        self.preset_combo.setMinimumWidth(200)
        row.addWidget(self.preset_combo)

        row.addSpacing(16)
        self.batch_mode_chk = QCheckBox("Batch mode")
        self.batch_mode_chk.setToolTip("Process multiple first-level subdirectories in one run")
        self.batch_mode_chk.toggled.connect(self._on_batch_mode_toggled)
        row.addWidget(self.batch_mode_chk)

        row.addStretch()

        self.scan_btn = QPushButton("Scan subdirectories")
        self.scan_btn.setObjectName("ghostBtn")
        self.scan_btn.setToolTip("Analyze files in the selected folder and group them by naming pattern")
        self.scan_btn.clicked.connect(self.scan_directories)
        row.addWidget(self.scan_btn)

        v.addLayout(row)
        return wrap

    # ── batch panel (toggleable) ─────────────────────────────────────────
    def _build_batch_panel(self) -> QWidget:
        self.batch_panel = Panel()
        v = QVBoxLayout(self.batch_panel)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        eye = QLabel("BATCH MODE  ·  SELECT SUBDIRECTORIES TO PROCESS")
        eye.setObjectName("eyebrow")
        v.addWidget(eye)

        self.batch_root_selector = PathCard("ROOT FOLDER")
        self.batch_root_selector.path_changed.connect(self._on_batch_root_changed)
        v.addWidget(self.batch_root_selector)

        self.batch_subdir_list = QListWidget()
        self.batch_subdir_list.setMaximumHeight(160)
        self.batch_subdir_list.setToolTip("Check subdirectories to include in the batch")
        v.addWidget(self.batch_subdir_list)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.batch_check_all_btn = QPushButton("Check all")
        self.batch_check_all_btn.setObjectName("ghostBtn")
        self.batch_check_all_btn.setToolTip("Select all subdirectories for batch processing")
        self.batch_check_all_btn.clicked.connect(self._batch_check_all)
        btns.addWidget(self.batch_check_all_btn)
        self.batch_uncheck_all_btn = QPushButton("Uncheck all")
        self.batch_uncheck_all_btn.setObjectName("ghostBtn")
        self.batch_uncheck_all_btn.setToolTip("Deselect all subdirectories")
        self.batch_uncheck_all_btn.clicked.connect(self._batch_uncheck_all)
        btns.addWidget(self.batch_uncheck_all_btn)
        btns.addStretch()
        self.run_batch_btn = QPushButton("Run batch")
        self.run_batch_btn.setProperty("role", "primary")
        self.run_batch_btn.setToolTip("Organize files in each checked subdirectory")
        self.run_batch_btn.clicked.connect(self._run_batch)
        btns.addWidget(self.run_batch_btn)
        v.addLayout(btns)

        self.batch_panel.setVisible(False)
        return self.batch_panel

    # ── tree (file groups) ───────────────────────────────────────────────
    def _build_tree(self) -> QWidget:
        wrap = Panel()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        head = QHBoxLayout()
        eye = QLabel("FILE GROUPS")
        eye.setObjectName("eyebrow")
        head.addWidget(eye)
        head.addStretch()
        hint = QLabel("Right-click a row for options · drag and drop to move files")
        hint.setObjectName("cardSub")
        head.addWidget(hint)
        v.addLayout(head)

        from ui.widgets.draggable_tree import DraggableTreeWidget

        self.tree_widget = DraggableTreeWidget()
        self.tree_widget.setHeaderLabels(["Group / file", "Count / size", "Status"])
        self.tree_widget.setColumnWidth(0, 500)
        self.tree_widget.setColumnWidth(1, 110)
        self.tree_widget.setColumnWidth(2, 110)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.tree_widget.files_dropped.connect(self.handle_drop)
        v.addWidget(self.tree_widget, stretch=1)
        return wrap

    # ── footer (status + progress) ───────────────────────────────────────
    def _build_footer(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("footer")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(16)

        col = QVBoxLayout()
        col.setSpacing(4)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("Ready to scan.")
        self.status_label.setObjectName("cardSub")
        col.addWidget(self.progress_bar)
        col.addWidget(self.status_label)
        h.addLayout(col, stretch=1)

        return wrap

    def on_directory_changed(self, directory: str):
        """Handle directory change."""
        self.set_directory(directory)
        self.tree_widget.clear()
        self.organize_btn.setEnabled(False)
        self.new_group_btn.setEnabled(False)

    # ── batch mode helpers ────────────────────────────────────────────────────

    def _on_batch_mode_toggled(self, checked: bool):
        self.batch_panel.setVisible(checked)
        # Scan button label hints which scope it operates on; "Run batch" lives
        # inside the batch panel for the multi-folder case.
        self.scan_btn.setText("Scan single directory" if checked else "Scan subdirectories")

    def _on_batch_root_changed(self, directory: str):
        self._batch_root = Path(directory)
        self.batch_subdir_list.clear()
        if not self._batch_root.is_dir():
            return
        for d in sorted(self._batch_root.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
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
        """Iterate through each checked subdirectory and run organize on each."""
        if not self._batch_root:
            self.show_warning("No Root", "Please select a root folder in Batch Mode.")
            return

        checked_dirs = []
        for i in range(self.batch_subdir_list.count()):
            item = self.batch_subdir_list.item(i)
            if item.checkState() == Qt.Checked:
                checked_dirs.append(self._batch_root / item.text())

        if not checked_dirs:
            self.show_warning("None Selected", "Check at least one subdirectory.")
            return

        from PySide6.QtWidgets import QApplication, QProgressDialog

        progress = QProgressDialog("Running batch…", "Cancel", 0, len(checked_dirs), self)
        progress.setWindowTitle("Batch Organizer")
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
                self._organize_single_dir(str(subdir))
            except Exception as exc:
                errors.append(f"{subdir.name}: {exc}")

        progress.setValue(len(checked_dirs))

        if errors:
            self.show_warning("Batch Errors", "Some directories had errors:\n\n" + "\n".join(errors))
        else:
            self.show_info("Batch Complete", f"Processed {len(checked_dirs)} director(ies) successfully.")

    def _organize_single_dir(self, directory: str):
        """Synchronously scan and organize a single directory (used by batch mode)."""
        import shutil

        from core.pattern_matching import group_files_by_preset

        root = Path(directory)
        preset = self.preset_combo.currentData()
        confidence_threshold = self.config.get_tab_setting("organizer", "confidence_threshold", 0.4)

        files = [f for f in root.iterdir() if f.is_file()]
        if not files:
            return

        filenames = [f.name for f in files]
        groups_dict, _ = group_files_by_preset(filenames, preset, confidence_threshold)

        for group_name, fnames in groups_dict.items():
            target_dir = root / group_name
            target_dir.mkdir(exist_ok=True)
            for fname in fnames:
                src = root / fname
                dst = target_dir / fname
                if src.exists() and src != dst:
                    shutil.move(str(src), str(dst))

    # ── scan ─────────────────────────────────────────────────────────────────

    def scan_directories(self):
        """Start scanning directories for files to organize."""
        if not self.current_directory:
            self.show_warning("No Directory", "Please select a directory first.")
            return

        self.scan_btn.setEnabled(False)
        self.organize_btn.setEnabled(False)
        self.new_group_btn.setEnabled(False)
        self.undo_move_btn.setEnabled(False)
        self._move_undo_stack.clear()
        self.tree_widget.clear()
        self.status_label.setText("Scanning...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # Indeterminate

        # Start scan worker
        from workers.scan_worker import ScanWorker

        confidence_threshold = self.config.get_tab_setting("organizer", "confidence_threshold", 0.4)
        preset = self.preset_combo.currentData()

        self.worker_thread = ScanWorker(self.current_directory, confidence_threshold, preset=preset)
        self.worker_thread.progress.connect(self.update_scan_status)
        self.worker_thread.finished.connect(self.on_scan_finished)
        self.worker_thread.start()

    def update_scan_status(self, message: str):
        """Update scan status."""
        self.status_label.setText(message)

    def _strip_sequence_files(self, subdir_path: str, seq_filenames: set):
        if subdir_path in self.file_groups:
            cleaned: Dict[str, List[Path]] = {}
            for grp, files in self.file_groups[subdir_path].items():
                remaining = [f for f in files if f.name not in seq_filenames]
                if remaining:
                    cleaned[grp] = remaining
            self.file_groups[subdir_path] = cleaned

        if subdir_path in self.unsorted_files:
            self.unsorted_files[subdir_path] = [
                f for f in self.unsorted_files[subdir_path] if f.name not in seq_filenames
            ]

    def _extract_sequences(self):
        """Detect image sequences and strip them from grouped/unsorted buckets."""
        all_subdirs = set(list(self.file_groups.keys()) + list(self.unsorted_files.keys()))
        for subdir_path in all_subdirs:
            all_files: List[Path] = []
            for files in self.file_groups.get(subdir_path, {}).values():
                all_files.extend(files)
            all_files.extend(self.unsorted_files.get(subdir_path, []))

            if not all_files:
                continue

            sequences = detect_image_sequences([f.name for f in all_files])
            if not sequences:
                continue

            self.file_sequences[subdir_path] = sequences
            seq_filenames = {fname for seq in sequences.values() for fname in seq.files}
            self._strip_sequence_files(subdir_path, seq_filenames)

    def _build_scan_summary(self) -> str:
        """Return a human-readable summary of scan results."""
        total_groups = sum(len(groups) for groups in self.file_groups.values())
        total_grouped = sum(len(files) for groups in self.file_groups.values() for files in groups.values())
        total_unsorted = sum(len(files) for files in self.unsorted_files.values())
        total_sequences = sum(len(seqs) for seqs in self.file_sequences.values())
        total_seq_frames = sum(len(seq.files) for seqs in self.file_sequences.values() for seq in seqs.values())

        parts = []
        if total_groups:
            parts.append(f"{total_groups} groups ({total_grouped} files)")
        if total_sequences:
            parts.append(f"{total_sequences} sequences ({total_seq_frames} frames)")
        if total_unsorted:
            parts.append(f"{total_unsorted} unsorted")
        return "Found " + ", ".join(parts) if parts else "No files found"

    def on_scan_finished(
        self, success: bool, message: str, grouped_results: Dict = None, unsorted_results: Dict = None
    ):
        """Handle scan completion."""
        self.scan_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if not success:
            self.show_error("Scan Failed", message)
            self.status_label.setText("Scan failed")
            return

        self._apply_scan_results(grouped_results, unsorted_results)

    def _apply_scan_results(self, grouped_results: Dict = None, unsorted_results: Dict = None):
        self.file_groups = grouped_results or {}
        self.unsorted_files = unsorted_results or {}
        self.file_sequences = {}

        self._extract_sequences()

        if not self.file_groups and not self.unsorted_files and not self.file_sequences:
            self.show_info("Scan Complete", "No files to organize were found in subdirectories.")
            self.status_label.setText("No files found")
            return

        self.populate_tree()
        self.status_label.setText(self._build_scan_summary())
        self.organize_btn.setEnabled(True)
        self.new_group_btn.setEnabled(True)

    def _save_expansion_state(self) -> set:
        """Return the set of UserRole data tuples for every currently expanded item."""
        expanded = set()
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            top = root.child(i)
            if top.isExpanded():
                d = top.data(0, Qt.UserRole)
                if d:
                    expanded.add(d)
                for j in range(top.childCount()):
                    child = top.child(j)
                    if child.isExpanded():
                        d = child.data(0, Qt.UserRole)
                        if d:
                            expanded.add(d)
        return expanded

    def _restore_expansion_state(self, expanded: set, first_populate: bool):
        """Expand items whose data key is in *expanded*; expand all top-level on first populate."""
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            top = root.child(i)
            d = top.data(0, Qt.UserRole)
            if first_populate or (d and d in expanded):
                top.setExpanded(True)
            for j in range(top.childCount()):
                child = top.child(j)
                d = child.data(0, Qt.UserRole)
                if d and d in expanded:
                    child.setExpanded(True)

    def populate_tree(self):
        """Populate the tree widget with groups, sequences, and files."""
        expanded = self._save_expansion_state()
        first_populate = self.tree_widget.invisibleRootItem().childCount() == 0
        self.tree_widget.clear()

        all_subdirs = set(
            list(self.file_groups.keys()) + list(self.unsorted_files.keys()) + list(self.file_sequences.keys())
        )

        for subdir_path in sorted(all_subdirs):
            subdir_name = Path(subdir_path).name
            subdir_item = QTreeWidgetItem([subdir_name, "", ""])
            subdir_item.setFont(0, QFont("", -1, QFont.Bold))
            subdir_item.setData(0, Qt.UserRole, ("subdir", subdir_path))

            self._add_group_items(subdir_item, subdir_path)
            self._add_sequence_items(subdir_item, subdir_path)
            self._add_unsorted_items(subdir_item, subdir_path)

            self.tree_widget.addTopLevelItem(subdir_item)

        self._restore_expansion_state(expanded, first_populate)

    def _add_group_items(self, parent: QTreeWidgetItem, subdir_path: str):
        from core.file_utils import format_file_size

        groups = self.file_groups.get(subdir_path, {})
        for group_name, files in sorted(groups.items()):
            group_item = QTreeWidgetItem([group_name, f"{len(files)} files", "Grouped"])
            group_item.setForeground(2, QBrush(QColor(0, 150, 0)))
            group_item.setData(0, Qt.UserRole, ("group", subdir_path, group_name))

            for file_path in sorted(files, key=lambda f: f.name):
                size_str = format_file_size(file_path.stat().st_size)
                file_item = QTreeWidgetItem([file_path.name, size_str, ""])
                file_item.setData(0, Qt.UserRole, ("file", subdir_path, group_name, file_path))
                group_item.addChild(file_item)

            parent.addChild(group_item)

    def _add_sequence_items(self, parent: QTreeWidgetItem, subdir_path: str):
        sequences = self.file_sequences.get(subdir_path, {})
        for seq_key, seq in sorted(sequences.items()):
            seq_item = QTreeWidgetItem([seq.label, f"{len(seq.files)} frames", "Sequence"])
            seq_item.setForeground(0, QBrush(QColor(30, 144, 255)))
            seq_item.setForeground(2, QBrush(QColor(30, 144, 255)))
            seq_item.setData(0, Qt.UserRole, ("sequence", subdir_path, seq_key))
            if seq.missing:
                seq_item.setToolTip(
                    0,
                    f"Missing frames: {', '.join(str(f) for f in seq.missing[:20])}"
                    + (" …" if len(seq.missing) > 20 else ""),
                )
            self._add_sequence_frame_items(seq_item, subdir_path, seq_key, seq)
            parent.addChild(seq_item)

    def _add_sequence_frame_items(self, parent: QTreeWidgetItem, subdir_path: str, seq_key: str, seq: SequenceGroup):
        for fname in seq.files:
            fpath = Path(subdir_path) / fname
            try:
                from core.file_utils import format_file_size

                size_str = format_file_size(fpath.stat().st_size)
            except Exception:
                size_str = ""
            frame_item = QTreeWidgetItem([fname, size_str, ""])
            frame_item.setData(0, Qt.UserRole, ("file", subdir_path, seq_key, fpath))
            parent.addChild(frame_item)

    def _add_unsorted_items(self, parent: QTreeWidgetItem, subdir_path: str):
        unsorted = self.unsorted_files.get(subdir_path, [])
        if not unsorted:
            return

        from core.file_utils import format_file_size

        unsorted_item = QTreeWidgetItem([_UNSORTED, f"{len(unsorted)} files", "Unsorted"])
        unsorted_item.setForeground(0, QBrush(QColor(200, 100, 0)))
        unsorted_item.setForeground(2, QBrush(QColor(200, 100, 0)))
        unsorted_item.setFont(0, QFont("", -1, QFont.Bold))
        unsorted_item.setData(0, Qt.UserRole, ("unsorted", subdir_path))

        for file_path in sorted(unsorted, key=lambda f: f.name):
            size_str = format_file_size(file_path.stat().st_size)
            file_item = QTreeWidgetItem([file_path.name, size_str, ""])
            file_item.setData(0, Qt.UserRole, ("file", subdir_path, None, file_path))
            unsorted_item.addChild(file_item)

        parent.addChild(unsorted_item)

    def show_context_menu(self, position):
        """Show context menu on right-click."""
        item = self.tree_widget.itemAt(position)
        if not item:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        menu = QMenu()

        if data[0] == "group":
            self._build_group_context_menu(menu, data)
        elif data[0] == "file":
            self._build_file_context_menu(menu, data)

        if not menu.actions():
            return

        menu.exec(self.tree_widget.viewport().mapToGlobal(position))

    def _build_group_context_menu(self, menu: QMenu, data: tuple):
        _, subdir_path, group_name = data

        rename_action = menu.addAction("Rename Group")
        rename_action.triggered.connect(lambda checked=False, sp=subdir_path, gn=group_name: self.rename_group(sp, gn))

        groups = [g for g in self.file_groups.get(subdir_path, {}).keys() if g != group_name]
        if groups:
            merge_menu = menu.addMenu("Merge with Group")
            for other_group in sorted(groups):
                action = merge_menu.addAction(other_group)
                action.triggered.connect(
                    lambda checked=False, sp=subdir_path, gn=group_name, og=other_group: self.merge_groups(sp, gn, og)
                )

        delete_action = menu.addAction("Delete Group (move files to Unsorted)")
        delete_action.triggered.connect(lambda checked=False, sp=subdir_path, gn=group_name: self.delete_group(sp, gn))

    def _build_file_context_menu(self, menu: QMenu, data: tuple):
        _, file_subdir, file_group, file_path = data

        in_group = file_group is not None and file_group in self.file_groups.get(file_subdir, {})
        in_unsorted = file_group is None

        if in_group:
            self._build_grouped_file_menu(menu, file_path, file_subdir, file_group)
        elif in_unsorted:
            self._build_unsorted_file_menu(menu, file_path, file_subdir)

    def _build_grouped_file_menu(self, menu: QMenu, file_path: Path, file_subdir: str, file_group: str):
        to_unsorted = menu.addAction("Move to Unsorted")
        to_unsorted.triggered.connect(
            lambda checked=False, fp=file_path, sd=file_subdir, fg=file_group: self._move_file_and_record(
                fp, sd, fg, None
            )
        )

        other_groups = sorted(g for g in self.file_groups.get(file_subdir, {}).keys() if g != file_group)
        if other_groups:
            move_menu = menu.addMenu("Move to Group")
            for grp in other_groups:
                action = move_menu.addAction(grp)
                action.triggered.connect(
                    lambda checked=False, fp=file_path, sd=file_subdir, fg=file_group, tg=grp: (
                        self._move_file_and_record(fp, sd, fg, tg)
                    )
                )

    def _build_unsorted_file_menu(self, menu: QMenu, file_path: Path, file_subdir: str):
        groups = sorted(self.file_groups.get(file_subdir, {}).keys())
        if groups:
            move_menu = menu.addMenu("Move to Group")
            for grp in groups:
                action = move_menu.addAction(grp)
                action.triggered.connect(
                    lambda checked=False, fp=file_path, sd=file_subdir, tg=grp: self._move_file_and_record(
                        fp, sd, None, tg
                    )
                )

    def rename_group(self, subdir_path: str, old_name: str):
        """Rename a group."""
        new_name, ok = QInputDialog.getText(self, "Rename Group", "Enter new group name:", text=old_name)

        if ok and new_name and new_name != old_name:
            if subdir_path in self.file_groups and old_name in self.file_groups[subdir_path]:
                self.file_groups[subdir_path][new_name] = self.file_groups[subdir_path][old_name]
                del self.file_groups[subdir_path][old_name]
                self.populate_tree()
                self.emit_status(f"Renamed group '{old_name}' to '{new_name}'")

    def merge_groups(self, subdir_path: str, from_group: str, to_group: str):
        """Merge two groups."""
        if self.confirm_action("Confirm Merge", f"Merge '{from_group}' into '{to_group}'?"):
            if subdir_path in self.file_groups:
                from_files = self.file_groups[subdir_path].get(from_group, [])
                self.file_groups[subdir_path][to_group].extend(from_files)
                del self.file_groups[subdir_path][from_group]
                self.populate_tree()
                self.emit_status(f"Merged '{from_group}' into '{to_group}'")

    def delete_group(self, subdir_path: str, group_name: str):
        """Delete a group and move files to unsorted."""
        if self.confirm_action("Confirm Delete", f"Delete group '{group_name}' and move files to unsorted?"):
            if subdir_path in self.file_groups and group_name in self.file_groups[subdir_path]:
                files = self.file_groups[subdir_path][group_name]

                if subdir_path not in self.unsorted_files:
                    self.unsorted_files[subdir_path] = []
                self.unsorted_files[subdir_path].extend(files)

                del self.file_groups[subdir_path][group_name]
                self.populate_tree()
                self.emit_status(f"Deleted group '{group_name}'")

    # ── move helpers + undo ───────────────────────────────────────────────

    def _move_file(
        self,
        file_path: Path,
        subdir: str,
        source_group: Optional[str],
        target_group: Optional[str],
        _refresh: bool = True,
        _keep_empty_source: bool = False,
    ):
        """Move a single file between groups / unsorted. Does NOT push to undo stack.

        _keep_empty_source: when True, an empty source group is NOT deleted after the
        file is removed.  Used by undo so that a group the user deliberately created
        (and then filled) isn't silently erased when the fill is undone.
        """
        # Remove from source
        if source_group is None:
            lst = self.unsorted_files.get(subdir, [])
            if file_path in lst:
                lst.remove(file_path)
        else:
            grp_files = self.file_groups.get(subdir, {}).get(source_group, [])
            if file_path in grp_files:
                grp_files.remove(file_path)
                if not _keep_empty_source and not self.file_groups[subdir][source_group]:
                    del self.file_groups[subdir][source_group]

        # Add to target
        if target_group is None:
            self.unsorted_files.setdefault(subdir, []).append(file_path)
        else:
            self.file_groups.setdefault(subdir, {}).setdefault(target_group, []).append(file_path)

        if _refresh:
            self.populate_tree()

    def _move_file_and_record(
        self, file_path: Path, subdir: str, source_group: Optional[str], target_group: Optional[str]
    ):
        """Move a single file and push a one-item batch to the undo stack."""
        self._move_file(file_path, subdir, source_group, target_group)
        self._push_undo_batch([(file_path, subdir, source_group, target_group)])
        dest = target_group if target_group else _UNSORTED
        self.emit_status(f"Moved {file_path.name} \u2192 {dest}")

    def _push_undo_batch(self, records: list):
        """Push a list of move records onto the undo stack and enable the button."""
        if records:
            self._move_undo_stack.append(records)
            self.undo_move_btn.setEnabled(True)

    def undo_last_move(self):
        """Reverse the most recent batch of file moves."""
        if not self._move_undo_stack:
            return
        batch = self._move_undo_stack.pop()
        # Reverse all moves in the batch (in reverse order for correctness)
        for file_path, subdir, from_group, to_group in reversed(batch):
            self._move_file(file_path, subdir, to_group, from_group, _refresh=False, _keep_empty_source=True)
        self.populate_tree()
        n = len(batch)
        self.emit_status(f"Undone: moved {n} file{'s' if n > 1 else ''} back")
        if not self._move_undo_stack:
            self.undo_move_btn.setEnabled(False)

    def create_new_group(self):
        """Create a new empty group."""
        item = self.tree_widget.currentItem()
        if not item:
            self.show_info("Select Directory", "Please select a subdirectory first")
            return

        # Find the subdir
        while item.parent():
            item = item.parent()

        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "subdir":
            return

        subdir_path = data[1]

        group_name, ok = QInputDialog.getText(
            self, "Create New Group", f"Enter group name for {Path(subdir_path).name}:"
        )

        if ok and group_name:
            if subdir_path not in self.file_groups:
                self.file_groups[subdir_path] = {}

            if group_name in self.file_groups[subdir_path]:
                self.show_warning("Group Exists", f"Group '{group_name}' already exists")
                return

            self.file_groups[subdir_path][group_name] = []
            self.populate_tree()
            self.emit_status(f"Created empty group '{group_name}'")

    def handle_drop(self, dropped_files: List[Path], target_item: QTreeWidgetItem):
        """Handle drag and drop of files between groups."""
        target_data = target_item.data(0, Qt.UserRole)
        if not target_data:
            return

        target_subdir, target_group = self._parse_drop_target(target_data)
        if target_subdir is None:
            return

        records = []
        for file_path in dropped_files:
            source_subdir, current_group = self._find_file_location(file_path)

            if source_subdir is None:
                continue
            if source_subdir != target_subdir:
                self.show_warning("Invalid Move", "Cannot move files between different subdirectories.")
                continue
            if current_group == target_group:
                continue

            self._move_file(file_path, source_subdir, current_group, target_group, _refresh=False)
            records.append((file_path, source_subdir, current_group, target_group))

        if records:
            self.populate_tree()
            self._push_undo_batch(records)
            dest = target_group if target_group else _UNSORTED
            self.emit_status(f"Moved {len(records)} file(s) \u2192 {dest}")

    def _parse_drop_target(self, target_data: tuple) -> tuple:
        """Return (target_subdir, target_group) or (None, None) if invalid."""
        if target_data[0] == "group":
            return target_data[1], target_data[2]
        if target_data[0] == "unsorted":
            return target_data[1], None
        return None, None

    def _find_file_location(self, file_path: Path) -> tuple:
        """Return (subdir, group_name) for a file, or (None, None) if not found.

        group_name is None when the file is in the unsorted bucket.
        """
        for subdir_path, groups in self.file_groups.items():
            for group_name, files in groups.items():
                if file_path in files:
                    return subdir_path, group_name

        for subdir_path, files in self.unsorted_files.items():
            if file_path in files:
                return subdir_path, None

        return None, None

    def organize_files(self):
        """Start organizing files into folders."""
        # Merge sequences into file_groups so OrganizeWorker handles them uniformly
        merged_groups: Dict[str, Dict[str, List[Path]]] = {
            subdir: dict(groups) for subdir, groups in self.file_groups.items()
        }
        for subdir_path, seqs in self.file_sequences.items():
            if subdir_path not in merged_groups:
                merged_groups[subdir_path] = {}
            for seq_key, seq in seqs.items():
                folder_name = seq.base  # organize into a folder named by base
                if folder_name in merged_groups[subdir_path]:
                    folder_name = seq_key  # fallback to full key to avoid collision
                merged_groups[subdir_path][folder_name] = [Path(subdir_path) / fname for fname in seq.files]

        # Count files to organize
        total_to_organize = sum(len(files) for groups in merged_groups.values() for files in groups.values())

        if total_to_organize == 0:
            self.show_info(
                "No Files to Organize", "There are no grouped files to organize. Please group some files first."
            )
            return

        # ── Pre-flight conflict check ─────────────────────────────────────
        root_path = Path(self.current_directory)
        from ui.dialogs.preflight_dialog import PreflightDialog, check_conflicts

        conflicts = check_conflicts(
            {grp: files for groups in merged_groups.values() for grp, files in groups.items()},
            root_path,
        )
        if conflicts:
            dlg = PreflightDialog(conflicts, self)
            if dlg.exec() != PreflightDialog.Accepted:
                return  # user cancelled

        # Confirm action
        if not self.confirm_action(
            "Confirm Organization",
            f"This will move {total_to_organize} files into organized folders.\n"
            f"Unsorted files will remain in their current location.\n\n"
            f"Are you sure you want to proceed?",
        ):
            return

        self.organize_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.new_group_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Start organize worker
        from workers.organize_worker import OrganizeWorker

        self.worker_thread = OrganizeWorker(merged_groups, self.current_directory)
        self.worker_thread.progress.connect(self.update_organize_progress)
        self.worker_thread.confirm_needed.connect(self.handle_conflict)
        self.worker_thread.finished.connect(self.on_organize_finished)
        self.worker_thread.start()

    def update_organize_progress(self, message: str, current: int, total: int):
        """Update organization progress."""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def handle_conflict(self, folder_name: str, subdir: str, files: List[str]):
        """Handle folder conflict during organization."""
        from ui.dialogs.confirm_dialog import ConfirmDialog

        dialog = ConfirmDialog(folder_name, subdir, files, self)
        dialog.exec()  # Show dialog and wait for user response

        action, apply_to_all = dialog.get_result()

        if apply_to_all and self.worker_thread:
            self.worker_thread.apply_to_all = action

        if self.worker_thread:
            self.worker_thread.pending_response = action

    def on_organize_finished(self, success: bool, message: str):
        """Handle organization completion."""
        self.progress_bar.setVisible(False)
        self.organize_btn.setEnabled(True)
        self.scan_btn.setEnabled(True)
        self.new_group_btn.setEnabled(True)

        if success:
            self.show_info("Success", message)
            self.file_groups = {}
            self.unsorted_files = {}
            self.tree_widget.clear()
            self.status_label.setText("Organization complete")
        else:
            self.show_error("Error", message)
            self.status_label.setText("Organization failed")

    def load_settings(self):
        """Load tab-specific settings."""
        last_dir = self.config.get_tab_directory("organizer")
        if last_dir:
            self.path_card.set_path(last_dir)
            self.set_directory(last_dir)

        saved_preset = self.config.get_tab_setting("organizer", "grouping_preset", PRESET_STANDARD.name)
        for i in range(self.preset_combo.count()):
            if self.preset_combo.itemText(i) == saved_preset:
                self.preset_combo.setCurrentIndex(i)
                break

    def save_settings(self):
        """Save tab-specific settings."""
        self.config.set_tab_setting("organizer", "grouping_preset", self.preset_combo.currentText())
