"""Main window for Pearl's File Tools."""

from PyQt5.QtWidgets import (QMainWindow, QTabWidget, QAction, QMessageBox,
                            QApplication, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from config import Config
from constants import DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT


class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""

    def __init__(self):
        """Initialize the main window."""
        super().__init__()

        # Initialize config
        self.config = Config()
        self.config.load_from_file()

        # Setup UI
        self.setup_ui()
        self.setup_menu_bar()
        self.setup_shortcuts()

        # Load window geometry
        self.load_window_state()

        # Connect tab change signal
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

    def setup_ui(self):
        """Setup the user interface."""
        self.setWindowTitle("Pearl's File Tools")

        # Allow the window to be resized freely regardless of tab content minimums.
        # Individual tabs may have large natural heights; the window should not be
        # locked to the tallest one.
        self.setMinimumSize(700, 500)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setMinimumSize(0, 0)  # don't let tab widget enforce child minimums
        self.setCentralWidget(self.tab_widget)

        # Add tabs
        from ui.tabs.bulk_renamer_tab import BulkRenamerTab
        from ui.tabs.file_organizer_tab import FileOrganizerTab
        from ui.tabs.archive_extractor_tab import ArchiveExtractorTab
        from ui.tabs.image_browser_tab import ImageBrowserTab
        from ui.tabs.ingest_tab import IngestTab
        from ui.tabs.delivery_tab import DeliveryTab
        from ui.tabs.studio_tools_tab import StudioToolsTab

        self.bulk_renamer_tab = BulkRenamerTab(self.config)
        self.tab_widget.addTab(self.bulk_renamer_tab, "Bulk Renamer")

        self.file_organizer_tab = FileOrganizerTab(self.config)
        self.tab_widget.addTab(self.file_organizer_tab, "File Organizer")

        self.archive_extractor_tab = ArchiveExtractorTab(self.config)
        self.tab_widget.addTab(self.archive_extractor_tab, "Archive Extractor")

        self.image_browser_tab = ImageBrowserTab(self.config)
        self.tab_widget.addTab(self.image_browser_tab, "Image Browser")

        self.ingest_tab = IngestTab(self.config)
        self.tab_widget.addTab(self.ingest_tab, "Ingest")

        self.delivery_tab = DeliveryTab(self.config)
        self.tab_widget.addTab(self.delivery_tab, "Delivery")

        self.studio_tools_tab = StudioToolsTab(self.config)
        self.tab_widget.addTab(self.studio_tools_tab, "Studio Tools")

        # Connect status signals
        self.bulk_renamer_tab.status_changed.connect(self.update_status)
        self.file_organizer_tab.status_changed.connect(self.update_status)
        self.archive_extractor_tab.status_changed.connect(self.update_status)
        self.image_browser_tab.status_changed.connect(self.update_status)
        self.ingest_tab.status_changed.connect(self.update_status)
        self.delivery_tab.status_changed.connect(self.update_status)
        self.studio_tools_tab.status_changed.connect(self.update_status)

        # Status bar
        self.statusBar().showMessage("Ready")

        # Watch indicator in status bar
        self.watch_indicator = QLabel("●  Not watching")
        self.watch_indicator.setStyleSheet("color: grey; padding: 0 6px;")
        self.statusBar().addPermanentWidget(self.watch_indicator)

        # Watch dialog (persistent so running worker is preserved)
        self._watch_dialog = None

    def setup_menu_bar(self):
        """Setup the menu bar."""
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        open_action = QAction("&Open Directory...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_directory)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menu_bar.addMenu("&Edit")

        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut(QKeySequence.Preferences)
        settings_action.triggered.connect(self.show_settings)
        edit_menu.addAction(settings_action)

        history_action = QAction("Rename &History...", self)
        history_action.triggered.connect(self.show_history)
        edit_menu.addAction(history_action)

        edit_menu.addSeparator()

        lint_action = QAction("&Lint Current Folder...", self)
        lint_action.setToolTip("Check filenames in the current directory for issues")
        lint_action.triggered.connect(self.lint_current_folder)
        edit_menu.addAction(lint_action)

        manage_profiles_action = QAction("&Manage Naming Profiles...", self)
        manage_profiles_action.triggered.connect(self.manage_profiles)
        edit_menu.addAction(manage_profiles_action)

        edit_menu.addSeparator()

        watch_action = QAction("Watch Folders\u2026", self)
        watch_action.triggered.connect(self.show_watch_manager)
        edit_menu.addAction(watch_action)

        sync_action = QAction("Sync Check\u2026", self)
        sync_action.triggered.connect(self.show_sync_dialog)
        edit_menu.addAction(sync_action)

        edit_menu.addSeparator()

        clear_cache_action = QAction("Clear All &Caches", self)
        clear_cache_action.triggered.connect(self.clear_caches)
        edit_menu.addAction(clear_cache_action)

        # View menu
        view_menu = menu_bar.addMenu("&View")

        refresh_action = QAction("&Refresh", self)
        refresh_action.setShortcut(QKeySequence.Refresh)
        refresh_action.triggered.connect(self.refresh_current_tab)
        view_menu.addAction(refresh_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Ctrl+Tab to switch tabs (handled by QTabWidget by default)

        # Ctrl+1-4 to switch to specific tabs
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence

        for i in range(min(9, self.tab_widget.count())):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i+1}"), self)
            shortcut.activated.connect(lambda idx=i: self.tab_widget.setCurrentIndex(idx))

        # Ctrl+W to close application
        close_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        close_shortcut.activated.connect(self.close)

    def load_window_state(self):
        """Load window geometry and state from config, clamped to available screen."""
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()

        geometry = self.config.get('window.geometry')
        if geometry and len(geometry) == 4:
            x, y, width, height = geometry
        else:
            width  = DEFAULT_WINDOW_WIDTH
            height = DEFAULT_WINDOW_HEIGHT
            x = screen.x() + (screen.width()  - width)  // 2
            y = screen.y() + (screen.height() - height) // 2

        # Clamp size — cap at 90% width and 85% height so there's always breathing room
        max_w = int(screen.width()  * 0.90)
        max_h = int(screen.height() * 0.85)
        width  = min(width,  max_w)
        height = min(height, max_h)
        # Clamp position so the window is fully on-screen
        x = max(screen.x(), min(x, screen.x() + screen.width()  - width))
        y = max(screen.y(), min(y, screen.y() + screen.height() - height))

        self.setGeometry(x, y, width, height)

        # Check if window was maximized
        if self.config.get('window.maximized', False):
            self.showMaximized()

        # Restore last active tab
        last_tab = self.config.get('window.last_active_tab', 0)
        if 0 <= last_tab < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(last_tab)

    def save_window_state(self):
        """Save window geometry and state to config."""
        # Save geometry
        geo = self.geometry()
        self.config.set('window.geometry', [geo.x(), geo.y(), geo.width(), geo.height()])

        # Save maximized state
        self.config.set('window.maximized', self.isMaximized())

        # Save last active tab
        self.config.set('window.last_active_tab', self.tab_widget.currentIndex())

        # Save config to file
        self.config.save_to_file()

    def closeEvent(self, event):
        """Handle window close event."""
        # Save all tab settings
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, 'save_settings'):
                tab.save_settings()

        # Save window state
        self.save_window_state()

        event.accept()

    def on_tab_changed(self, index):
        """
        Handle tab change event.

        Args:
            index: Index of the new tab
        """
        # Update status bar with current tab status
        if 0 <= index < self.tab_widget.count():
            tab = self.tab_widget.widget(index)
            if hasattr(tab, 'get_tab_name'):
                self.statusBar().showMessage(f"{tab.get_tab_name()} - Ready")

    def update_status(self, message: str):
        """
        Update the status bar.

        Args:
            message: Status message to display
        """
        self.statusBar().showMessage(message)

    def open_directory(self):
        """Open directory in the current tab."""
        current_tab = self.tab_widget.currentWidget()
        if hasattr(current_tab, 'browse_directory'):
            current_tab.browse_directory()

    def refresh_current_tab(self):
        """Refresh the current tab."""
        current_tab = self.tab_widget.currentWidget()
        if hasattr(current_tab, 'refresh'):
            current_tab.refresh()

    def show_settings(self):
        """Show settings dialog."""
        from ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self.config, self)
        result = dialog.exec_()

        if result == SettingsDialog.Accepted and dialog.settings_changed:
            QMessageBox.information(
                self,
                "Settings Saved",
                "Settings have been saved.\n\n"
                "Some changes may require restarting the application."
            )

    def clear_caches(self):
        """Clear all cached data."""
        reply = QMessageBox.question(
            self,
            "Clear Caches",
            "This will clear all cached data (image directory scans).\n\n"
            "Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            import os
            from pathlib import Path

            cleared_count = 0
            total_size = 0

            # Find and delete cache files
            cache_files = [
                '.image_browser_cache.json',
            ]

            # Search in user's home directory and common locations
            search_paths = [Path.home()]

            # Also search current working directory
            if hasattr(self, 'config') and self.config.config_path:
                search_paths.append(Path(self.config.config_path).parent)

            for search_path in search_paths:
                if not search_path.exists():
                    continue

                # Recursively find cache files
                for cache_file_name in cache_files:
                    for cache_file in search_path.rglob(cache_file_name):
                        try:
                            if cache_file.is_file():
                                size = cache_file.stat().st_size
                                cache_file.unlink()
                                cleared_count += 1
                                total_size += size
                        except Exception as e:
                            pass

            # Format size
            size_kb = total_size / 1024
            size_str = f"{size_kb:.2f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"

            if cleared_count > 0:
                QMessageBox.information(
                    self,
                    "Cache Cleared",
                    f"Cleared {cleared_count} cache file(s)\n"
                    f"Freed {size_str} of disk space"
                )
            else:
                QMessageBox.information(
                    self,
                    "No Caches Found",
                    "No cache files were found to clear."
                )

    def show_history(self):
        """Open the rename history dialog."""
        from ui.dialogs.history_dialog import HistoryDialog
        dialog = HistoryDialog(self)
        dialog.exec_()

    def lint_current_folder(self):
        """Delegate lint_folder to the active tab if it supports it."""
        tab = self.tab_widget.currentWidget()
        if hasattr(tab, 'lint_folder'):
            tab.lint_folder()

    def manage_profiles(self):
        """Open the naming profile manager."""
        from ui.dialogs.profile_dialog import ProfileDialog
        dialog = ProfileDialog(self.config, self)
        dialog.exec_()

    def update_watch_indicator(self, active: bool):
        """Update the status-bar watch indicator dot."""
        if active:
            self.watch_indicator.setText("●  Watching")
            self.watch_indicator.setStyleSheet("color: #4ec94e; padding: 0 6px;")
        else:
            self.watch_indicator.setText("●  Not watching")
            self.watch_indicator.setStyleSheet("color: grey; padding: 0 6px;")

    def show_watch_manager(self):
        """Show (or raise) the Watch Folder Manager dialog."""
        if self._watch_dialog is None:
            from ui.dialogs.watch_manager_dialog import WatchManagerDialog
            self._watch_dialog = WatchManagerDialog(self.config, self)
            self._watch_dialog._update_indicator_cb = self.update_watch_indicator
        self._watch_dialog.show()
        self._watch_dialog.raise_()
        self._watch_dialog.activateWindow()

    def show_sync_dialog(self):
        """Show the Multi-site Sync Check dialog."""
        from ui.dialogs.sync_dialog import SyncDialog
        dialog = SyncDialog(self.config, self)
        dialog.exec_()

    def show_about(self):
        """Show about dialog."""
        from __init__ import __version__

        QMessageBox.about(
            self,
            "About Pearl's File Tools",
            f"<h3>Pearl's File Tools</h3>"
            f"<p><b>Version {__version__}</b></p>"
            f"<p>A unified file management application combining:</p>"
            f"<ul>"
            f"<li><b>Bulk Renamer</b> - Rename multiple files with transformations</li>"
            f"<li><b>File Organizer</b> - Group files by naming patterns</li>"
            f"<li><b>Archive Extractor</b> - Extract archives with smart extraction</li>"
            f"<li><b>Image Browser</b> - Browse and view images</li>"
            f"</ul>"
            f"<p><b>Features:</b></p>"
            f"<ul>"
            f"<li>Dark theme interface</li>"
            f"<li>Persistent settings and directory history</li>"
            f"<li>Background workers for responsive UI</li>"
            f"<li>Undo functionality</li>"
            f"<li>Smart caching for performance</li>"
            f"</ul>"
            f"<p><b>Keyboard Shortcuts:</b><br>"
            f"Ctrl+1-4: Switch tabs<br>"
            f"Ctrl+O: Open directory<br>"
            f"Ctrl+R: Refresh<br>"
            f"Ctrl+W: Close</p>"
            f"<p style='margin-top:10px;'><i>Built with PyQt5</i></p>"
        )
