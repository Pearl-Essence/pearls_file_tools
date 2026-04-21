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
from core.pattern_matching import group_files_by_pattern


class FileOrganizerTab(BaseTab):
    """Tab for organizing files into folders by naming patterns."""

    def __init__(self, config, parent=None):
        """Initialize the file organizer tab."""
        self.file_groups: Dict[str, Dict[str, List[Path]]] = {}
        self.unsorted_files: Dict[str, List[Path]] = {}

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

        if not self.file_groups and not self.unsorted_files:
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

        self.status_label.setText(
            f"Found {total_groups} groups ({total_grouped} files), {total_unsorted} unsorted files"
        )
        self.organize_btn.setEnabled(True)
        self.new_group_btn.setEnabled(True)

    def populate_tree(self):
        """Populate the tree widget with groups and files."""
        self.tree_widget.clear()

        # Combine all subdirectories
        all_subdirs = set(list(self.file_groups.keys()) + list(self.unsorted_files.keys()))

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
            subdir_item.setExpanded(True)

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

            # Rename group
            rename_action = menu.addAction("Rename Group")
            rename_action.triggered.connect(lambda: self.rename_group(subdir_path, group_name))

            # Merge with another group
            groups = [g for g in self.file_groups.get(subdir_path, {}).keys() if g != group_name]
            if groups:
                merge_menu = menu.addMenu("Merge with Group")
                for other_group in groups:
                    action = merge_menu.addAction(other_group)
                    action.triggered.connect(
                        lambda checked, og=other_group: self.merge_groups(subdir_path, group_name, og)
                    )

            # Delete group
            delete_action = menu.addAction("Delete Group (move files to unsorted)")
            delete_action.triggered.connect(lambda: self.delete_group(subdir_path, group_name))

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

        # Determine target
        if target_data[0] == 'group':
            _, target_subdir, target_group = target_data
        elif target_data[0] == 'unsorted':
            _, target_subdir = target_data
            target_group = None
        else:
            return

        # Move each file
        moved_count = 0
        for file_path in dropped_files:
            # Find where this file currently is
            current_group = None
            source_subdir = None

            # Search in file_groups
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

            # Search in unsorted_files if not found
            if not found:
                for subdir_path, files in self.unsorted_files.items():
                    if file_path in files:
                        current_group = None
                        source_subdir = subdir_path
                        found = True
                        break

            if not found:
                continue

            # Only allow moving within the same subdirectory
            if source_subdir != target_subdir:
                self.show_warning(
                    "Invalid Move",
                    f"Cannot move files between different subdirectories."
                )
                continue

            # Skip if dropping on same group
            if current_group == target_group:
                continue

            # Remove from source
            if current_group is None:
                # Moving from unsorted
                if source_subdir in self.unsorted_files and file_path in self.unsorted_files[source_subdir]:
                    self.unsorted_files[source_subdir].remove(file_path)
                    if not self.unsorted_files[source_subdir]:
                        del self.unsorted_files[source_subdir]
            else:
                # Moving from a group
                if source_subdir in self.file_groups and current_group in self.file_groups[source_subdir]:
                    if file_path in self.file_groups[source_subdir][current_group]:
                        self.file_groups[source_subdir][current_group].remove(file_path)
                        # Remove empty groups
                        if not self.file_groups[source_subdir][current_group]:
                            del self.file_groups[source_subdir][current_group]

            # Add to target
            if target_group is None:
                # Moving to unsorted
                if target_subdir not in self.unsorted_files:
                    self.unsorted_files[target_subdir] = []
                self.unsorted_files[target_subdir].append(file_path)
            else:
                # Moving to a group
                if target_subdir not in self.file_groups:
                    self.file_groups[target_subdir] = {}
                if target_group not in self.file_groups[target_subdir]:
                    self.file_groups[target_subdir][target_group] = []
                self.file_groups[target_subdir][target_group].append(file_path)

            moved_count += 1

        # Refresh the tree
        if moved_count > 0:
            self.populate_tree()
            dest = target_group if target_group else "[UNSORTED]"
            self.emit_status(f"Moved {moved_count} file(s) to {dest}")

    def organize_files(self):
        """Start organizing files into folders."""
        # Count files to organize
        total_to_organize = sum(
            len(files)
            for groups in self.file_groups.values()
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

        self.worker_thread = OrganizeWorker(self.file_groups, self.current_directory)
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
