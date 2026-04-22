"""File Organizer tab for Pearl's File Tools."""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                            QTreeWidget, QTreeWidgetItem, QProgressBar, QInputDialog,
                            QMenu)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor, QBrush
from pathlib import Path
from typing import Dict, List, Optional
from ui.tabs.base_tab import BaseTab
from ui.widgets.directory_selector import DirectorySelectorWidget
from core.pattern_matching import group_files_by_pattern, detect_image_sequences, SequenceGroup


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

        super().__init__(config, parent)

    def get_tab_name(self) -> str:
        """Get the tab name."""
        return "File Organizer"

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()

        # Directory selection
        self.dir_selector = DirectorySelectorWidget(label_text="Directory:")
        self.dir_selector.directory_changed.connect(self.on_directory_changed)
        layout.addWidget(self.dir_selector)

        # Scan button
        self.scan_btn = QPushButton("Scan Subdirectories")
        self.scan_btn.clicked.connect(self.scan_directories)
        self.scan_btn.setStyleSheet("padding: 10px; font-size: 14px;")
        layout.addWidget(self.scan_btn)

        # Status label
        self.status_label = QLabel("Ready to scan")
        self.status_label.setStyleSheet("color: #888; padding: 5px; font-style: italic;")
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Tree widget label
        tree_label = QLabel("File Groups (Right-click for options, Drag & Drop to move files):")
        tree_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(tree_label)

        # Tree widget for file groups
        from ui.widgets.draggable_tree import DraggableTreeWidget
        self.tree_widget = DraggableTreeWidget()
        self.tree_widget.setHeaderLabels(["Group/File", "Count/Size", "Status"])
        self.tree_widget.setColumnWidth(0, 500)
        self.tree_widget.setColumnWidth(1, 100)
        self.tree_widget.setColumnWidth(2, 100)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.tree_widget.files_dropped.connect(self.handle_drop)
        layout.addWidget(self.tree_widget, stretch=1)

        # Action buttons
        button_layout = QHBoxLayout()

        self.new_group_btn = QPushButton("Create New Group")
        self.new_group_btn.clicked.connect(self.create_new_group)
        self.new_group_btn.setEnabled(False)
        button_layout.addWidget(self.new_group_btn)

        self.undo_move_btn = QPushButton("Undo Last Move")
        self.undo_move_btn.setToolTip("Undo the most recent drag-and-drop or context-menu move")
        self.undo_move_btn.clicked.connect(self.undo_last_move)
        self.undo_move_btn.setEnabled(False)
        button_layout.addWidget(self.undo_move_btn)

        self.organize_btn = QPushButton("Organize Files")
        self.organize_btn.clicked.connect(self.organize_files)
        self.organize_btn.setEnabled(False)
        self.organize_btn.setStyleSheet("padding: 10px; font-size: 14px; font-weight: bold;")
        button_layout.addWidget(self.organize_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def on_directory_changed(self, directory: str):
        """Handle directory change."""
        self.set_directory(directory)
        self.tree_widget.clear()
        self.organize_btn.setEnabled(False)
        self.new_group_btn.setEnabled(False)

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

        confidence_threshold = self.config.get_tab_setting('organizer', 'confidence_threshold', 0.4)

        self.worker_thread = ScanWorker(self.current_directory, confidence_threshold)
        self.worker_thread.progress.connect(self.update_scan_status)
        self.worker_thread.finished.connect(self.on_scan_finished)
        self.worker_thread.start()

    def update_scan_status(self, message: str):
        """Update scan status."""
        self.status_label.setText(message)

    def on_scan_finished(self, success: bool, message: str, grouped_results: Dict = None, unsorted_results: Dict = None):
        """Handle scan completion."""
        self.scan_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if not success:
            self.show_error("Scan Failed", message)
            self.status_label.setText("Scan failed")
            return

        self.file_groups = grouped_results or {}
        self.unsorted_files = unsorted_results or {}
        self.file_sequences = {}

        # Detect image sequences across all files in each subdir, then remove
        # sequence files from the regular grouped / unsorted buckets.
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

            # Strip sequence files from file_groups
            if subdir_path in self.file_groups:
                cleaned: Dict[str, List[Path]] = {}
                for grp, files in self.file_groups[subdir_path].items():
                    remaining = [f for f in files if f.name not in seq_filenames]
                    if remaining:
                        cleaned[grp] = remaining
                self.file_groups[subdir_path] = cleaned

            # Strip from unsorted
            if subdir_path in self.unsorted_files:
                self.unsorted_files[subdir_path] = [
                    f for f in self.unsorted_files[subdir_path]
                    if f.name not in seq_filenames
                ]

        if not self.file_groups and not self.unsorted_files and not self.file_sequences:
            self.show_info("Scan Complete", "No files to organize were found in subdirectories.")
            self.status_label.setText("No files found")
            return

        self.populate_tree()

        total_groups = sum(len(groups) for groups in self.file_groups.values())
        total_grouped = sum(
            len(files)
            for groups in self.file_groups.values()
            for files in groups.values()
        )
        total_unsorted = sum(len(files) for files in self.unsorted_files.values())
        total_sequences = sum(len(seqs) for seqs in self.file_sequences.values())
        total_seq_frames = sum(
            len(seq.files)
            for seqs in self.file_sequences.values()
            for seq in seqs.values()
        )

        parts = []
        if total_groups:
            parts.append(f"{total_groups} groups ({total_grouped} files)")
        if total_sequences:
            parts.append(f"{total_sequences} sequences ({total_seq_frames} frames)")
        if total_unsorted:
            parts.append(f"{total_unsorted} unsorted")
        self.status_label.setText("Found " + ", ".join(parts) if parts else "No files found")
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
        first_populate = (self.tree_widget.invisibleRootItem().childCount() == 0)
        self.tree_widget.clear()

        all_subdirs = set(
            list(self.file_groups.keys()) +
            list(self.unsorted_files.keys()) +
            list(self.file_sequences.keys())
        )

        for subdir_path in sorted(all_subdirs):
            subdir_name = Path(subdir_path).name
            subdir_item = QTreeWidgetItem([subdir_name, "", ""])
            subdir_item.setFont(0, QFont("", -1, QFont.Bold))
            subdir_item.setData(0, Qt.UserRole, ('subdir', subdir_path))

            # Add groups
            groups = self.file_groups.get(subdir_path, {})
            for group_name, files in sorted(groups.items()):
                group_item = QTreeWidgetItem([group_name, f"{len(files)} files", "Grouped"])
                group_item.setForeground(2, QBrush(QColor(0, 150, 0)))
                group_item.setData(0, Qt.UserRole, ('group', subdir_path, group_name))

                for file_path in sorted(files, key=lambda f: f.name):
                    from core.file_utils import format_file_size
                    size = file_path.stat().st_size
                    size_str = format_file_size(size)
                    file_item = QTreeWidgetItem([file_path.name, size_str, ""])
                    file_item.setData(0, Qt.UserRole, ('file', subdir_path, group_name, file_path))
                    group_item.addChild(file_item)

                subdir_item.addChild(group_item)

            # Add image sequences
            sequences = self.file_sequences.get(subdir_path, {})
            for seq_key, seq in sorted(sequences.items()):
                seq_item = QTreeWidgetItem([
                    seq.label,
                    f"{len(seq.files)} frames",
                    "Sequence",
                ])
                seq_item.setForeground(0, QBrush(QColor(30, 144, 255)))   # dodger blue
                seq_item.setForeground(2, QBrush(QColor(30, 144, 255)))
                seq_item.setData(0, Qt.UserRole, ('sequence', subdir_path, seq_key))
                if seq.missing:
                    seq_item.setToolTip(
                        0,
                        f"Missing frames: {', '.join(str(f) for f in seq.missing[:20])}"
                        + (' …' if len(seq.missing) > 20 else '')
                    )
                for fname in seq.files:
                    fpath = Path(subdir_path) / fname
                    try:
                        from core.file_utils import format_file_size
                        size_str = format_file_size(fpath.stat().st_size)
                    except Exception:
                        size_str = ''
                    frame_item = QTreeWidgetItem([fname, size_str, ""])
                    frame_item.setData(0, Qt.UserRole, ('file', subdir_path, seq_key, fpath))
                    seq_item.addChild(frame_item)
                subdir_item.addChild(seq_item)

            # Add unsorted files section
            unsorted = self.unsorted_files.get(subdir_path, [])
            if unsorted:
                unsorted_item = QTreeWidgetItem(["[UNSORTED]", f"{len(unsorted)} files", "Unsorted"])
                unsorted_item.setForeground(0, QBrush(QColor(200, 100, 0)))
                unsorted_item.setForeground(2, QBrush(QColor(200, 100, 0)))
                unsorted_item.setFont(0, QFont("", -1, QFont.Bold))
                unsorted_item.setData(0, Qt.UserRole, ('unsorted', subdir_path))

                for file_path in sorted(unsorted, key=lambda f: f.name):
                    from core.file_utils import format_file_size
                    size = file_path.stat().st_size
                    size_str = format_file_size(size)
                    file_item = QTreeWidgetItem([file_path.name, size_str, ""])
                    file_item.setData(0, Qt.UserRole, ('file', subdir_path, None, file_path))
                    unsorted_item.addChild(file_item)

                subdir_item.addChild(unsorted_item)

            self.tree_widget.addTopLevelItem(subdir_item)

        self._restore_expansion_state(expanded, first_populate)

    def show_context_menu(self, position):
        """Show context menu on right-click."""
        item = self.tree_widget.itemAt(position)
        if not item:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        menu = QMenu()

        if data[0] == 'group':
            _, subdir_path, group_name = data

            rename_action = menu.addAction("Rename Group")
            rename_action.triggered.connect(
                lambda checked=False, sp=subdir_path, gn=group_name:
                    self.rename_group(sp, gn)
            )

            groups = [g for g in self.file_groups.get(subdir_path, {}).keys() if g != group_name]
            if groups:
                merge_menu = menu.addMenu("Merge with Group")
                for other_group in sorted(groups):
                    action = merge_menu.addAction(other_group)
                    action.triggered.connect(
                        lambda checked=False, sp=subdir_path, gn=group_name, og=other_group:
                            self.merge_groups(sp, gn, og)
                    )

            delete_action = menu.addAction("Delete Group (move files to Unsorted)")
            delete_action.triggered.connect(
                lambda checked=False, sp=subdir_path, gn=group_name:
                    self.delete_group(sp, gn)
            )

        elif data[0] == 'file':
            _, file_subdir, file_group, file_path = data

            # Only show move options for files in regular groups or in unsorted.
            # Sequence frame items report a seq_key as file_group — skip those
            # since sequences are managed as a unit.
            in_group = (file_group is not None and
                        file_group in self.file_groups.get(file_subdir, {}))
            in_unsorted = (file_group is None)

            if in_group:
                to_unsorted = menu.addAction("Move to Unsorted")
                to_unsorted.triggered.connect(
                    lambda checked=False, fp=file_path, sd=file_subdir, fg=file_group:
                        self._move_file_and_record(fp, sd, fg, None)
                )

                other_groups = sorted(
                    g for g in self.file_groups.get(file_subdir, {}).keys()
                    if g != file_group
                )
                if other_groups:
                    move_menu = menu.addMenu("Move to Group")
                    for grp in other_groups:
                        action = move_menu.addAction(grp)
                        action.triggered.connect(
                            lambda checked=False, fp=file_path, sd=file_subdir, fg=file_group, tg=grp:
                                self._move_file_and_record(fp, sd, fg, tg)
                        )

            elif in_unsorted:
                # File is in Unsorted — offer to move into a group
                groups = sorted(self.file_groups.get(file_subdir, {}).keys())
                if groups:
                    move_menu = menu.addMenu("Move to Group")
                    for grp in groups:
                        action = move_menu.addAction(grp)
                        action.triggered.connect(
                            lambda checked=False, fp=file_path, sd=file_subdir, tg=grp:
                                self._move_file_and_record(fp, sd, None, tg)
                        )

        # Don't show an empty menu
        if not menu.actions():
            return

        menu.exec_(self.tree_widget.viewport().mapToGlobal(position))

    def rename_group(self, subdir_path: str, old_name: str):
        """Rename a group."""
        new_name, ok = QInputDialog.getText(
            self, "Rename Group", "Enter new group name:", text=old_name
        )

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
        if self.confirm_action(
            "Confirm Delete",
            f"Delete group '{group_name}' and move files to unsorted?"
        ):
            if subdir_path in self.file_groups and group_name in self.file_groups[subdir_path]:
                files = self.file_groups[subdir_path][group_name]

                if subdir_path not in self.unsorted_files:
                    self.unsorted_files[subdir_path] = []
                self.unsorted_files[subdir_path].extend(files)

                del self.file_groups[subdir_path][group_name]
                self.populate_tree()
                self.emit_status(f"Deleted group '{group_name}'")

    # ── move helpers + undo ───────────────────────────────────────────────

    def _move_file(self, file_path: Path, subdir: str,
                   source_group: Optional[str], target_group: Optional[str],
                   _refresh: bool = True, _keep_empty_source: bool = False):
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

    def _move_file_and_record(self, file_path: Path, subdir: str,
                               source_group: Optional[str], target_group: Optional[str]):
        """Move a single file and push a one-item batch to the undo stack."""
        self._move_file(file_path, subdir, source_group, target_group)
        self._push_undo_batch([(file_path, subdir, source_group, target_group)])
        dest = target_group if target_group else "[UNSORTED]"
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
            self._move_file(file_path, subdir, to_group, from_group,
                            _refresh=False, _keep_empty_source=True)
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
        if not data or data[0] != 'subdir':
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

        if target_data[0] == 'group':
            _, target_subdir, target_group = target_data
        elif target_data[0] == 'unsorted':
            _, target_subdir = target_data
            target_group = None
        else:
            return

        records = []  # (file_path, subdir, from_group, to_group) — for undo

        for file_path in dropped_files:
            # Locate the file in the current data model
            source_subdir = None
            current_group = None
            found = False

            for subdir_path, groups in self.file_groups.items():
                for group_name, files in groups.items():
                    if file_path in files:
                        current_group = group_name
                        source_subdir = subdir_path
                        found = True
                        break
                if found:
                    break

            if not found:
                for subdir_path, files in self.unsorted_files.items():
                    if file_path in files:
                        current_group = None
                        source_subdir = subdir_path
                        found = True
                        break

            if not found:
                continue

            if source_subdir != target_subdir:
                self.show_warning("Invalid Move",
                                  "Cannot move files between different subdirectories.")
                continue

            if current_group == target_group:
                continue

            self._move_file(file_path, source_subdir, current_group, target_group,
                            _refresh=False)
            records.append((file_path, source_subdir, current_group, target_group))

        if records:
            self.populate_tree()
            self._push_undo_batch(records)
            dest = target_group if target_group else "[UNSORTED]"
            self.emit_status(f"Moved {len(records)} file(s) \u2192 {dest}")

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
                merged_groups[subdir_path][folder_name] = [
                    Path(subdir_path) / fname for fname in seq.files
                ]

        # Count files to organize
        total_to_organize = sum(
            len(files)
            for groups in merged_groups.values()
            for files in groups.values()
        )

        if total_to_organize == 0:
            self.show_info(
                "No Files to Organize",
                "There are no grouped files to organize. Please group some files first."
            )
            return

        # Confirm action
        if not self.confirm_action(
            "Confirm Organization",
            f"This will move {total_to_organize} files into organized folders.\n"
            f"Unsorted files will remain in their current location.\n\n"
            f"Are you sure you want to proceed?"
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
        dialog.exec_()  # Show dialog and wait for user response

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
        last_dir = self.config.get_tab_directory('organizer')
        if last_dir:
            self.dir_selector.set_directory(last_dir)
            self.set_directory(last_dir)

    def save_settings(self):
        """Save tab-specific settings."""
        pass  # Settings are saved via config automatically
