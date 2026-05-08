"""Main window for Pearl Post Suite — v0.20 sidebar shell.

Replaces the legacy QTabWidget with a left sidebar (SidebarNav) and a right
QStackedWidget. Each existing tab class is mounted unchanged into the stack;
sidebar items that point to dialogs (Sync Check, Watch Folders) intercept
the activation and open the dialog without changing the current pane.
"""

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QCursor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QMessageBox, QPushButton, QSplitter, QStackedWidget, QVBoxLayout,
    QWidget,
)

from branding import APP_NAME, APP_TAGLINE, ICONS_DIR, NAV_TREE
from config import Config
from constants import DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT
from ui.widgets.sidebar_nav import SidebarNav


class MainWindow(QMainWindow):
    """Sidebar-driven main window."""

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.config.load_from_file()

        # Holds factory_key -> mount_index in self.stack
        self._stack_index_for_key: Dict[str, int] = {}
        # All tab instances we constructed (so we can save_settings on close)
        self._tab_instances: list = []

        self._setup_ui()
        self._setup_menu_bar()
        self._setup_shortcuts()
        self._load_window_state()

    # ─────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 600)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(0)
        splitter.setChildrenCollapsible(False)

        # Left rail: brand + project context + sidebar + footer
        left = self._build_left_rail()
        splitter.addWidget(left)

        # Right: stacked content
        self.stack = QStackedWidget()
        self._mount_tabs()
        splitter.addWidget(self.stack)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        # Status bar
        self.statusBar().showMessage("Ready")
        self.watch_indicator = QLabel("●  Not watching")
        self.watch_indicator.setStyleSheet("color: #5C5950; padding: 0 6px;")
        self.statusBar().addPermanentWidget(self.watch_indicator)

    def _build_left_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("leftRail")
        rail.setFixedWidth(240)
        v = QVBoxLayout(rail)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        v.addWidget(self._build_brand())
        v.addWidget(self._build_project_strip())

        self.sidebar = SidebarNav(NAV_TREE, ICONS_DIR)
        self.sidebar.activated.connect(self._on_nav_activated)
        v.addWidget(self.sidebar, stretch=1)

        v.addWidget(self._build_user_footer())
        return rail

    def _build_brand(self) -> QWidget:
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(18, 16, 18, 4)
        h.setSpacing(10)

        mark = QLabel()
        mark_path = ICONS_DIR / "pearl-mark.svg"
        if mark_path.exists():
            mark.setPixmap(QIcon(str(mark_path)).pixmap(QSize(20, 20)))
        else:
            mark.setText("●")
            mark.setStyleSheet("color: #E8B547; font-size: 18px;")

        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel("Pearl")
        name.setObjectName("brandName")
        # Styling lives in pearl_dark.qss under QLabel#brandName so the
        # serif resolves through the __BRAND_SERIF__ substitution.
        tag = QLabel(APP_TAGLINE)
        tag.setObjectName("eyebrow")
        col.addWidget(name)
        col.addWidget(tag)

        h.addWidget(mark)
        h.addLayout(col)
        h.addStretch()
        return wrap

    def _build_project_strip(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("projectStrip")
        wrap.setStyleSheet(
            "QFrame#projectStrip { border-bottom: 1px solid #1C1E24; }"
        )
        v = QVBoxLayout(wrap)
        v.setContentsMargins(18, 8, 18, 14)
        v.setSpacing(2)

        self._proj_label = QLabel("No project loaded")
        self._proj_label.setStyleSheet(
            "color: #E8E6DF; font-size: 12px; font-weight: 600;"
        )
        self._proj_meta = QLabel("—")
        self._proj_meta.setObjectName("cardMetrics")

        btn = QPushButton()
        btn.setFlat(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { text-align: left; border: none; padding: 0; }"
            "QPushButton:hover { background: transparent; }"
        )
        btn_layout = QVBoxLayout(btn)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(2)
        btn_layout.addWidget(self._proj_label)
        btn_layout.addWidget(self._proj_meta)
        btn.setToolTip("Click to switch project or create a new one")
        btn.clicked.connect(self._show_project_menu)

        v.addWidget(btn)

        # Apply active project on start
        self._refresh_project_strip()
        return wrap

    def _build_user_footer(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("userFooter")
        wrap.setStyleSheet(
            "QFrame#userFooter { border-top: 1px solid #1C1E24; }"
        )
        h = QHBoxLayout(wrap)
        h.setContentsMargins(18, 12, 18, 12)
        h.setSpacing(10)

        # Clickable user area — opens a quick-access menu
        user_btn = QPushButton()
        user_btn.setFlat(True)
        user_btn.setCursor(Qt.PointingHandCursor)
        user_btn.setStyleSheet(
            "QPushButton { border: none; padding: 0; text-align: left; }"
            "QPushButton:hover { background: transparent; }"
        )
        user_btn.setToolTip("Settings, profiles, and more")
        user_btn.clicked.connect(self._show_user_menu)

        btn_h = QHBoxLayout(user_btn)
        btn_h.setContentsMargins(0, 0, 0, 0)
        btn_h.setSpacing(10)

        avatar = QLabel("LK")
        avatar.setFixedSize(22, 22)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            "background:#2A2418; color:#E8B547; border-radius:11px;"
            "font-size:10px; font-weight:700;"
        )
        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel(self.config.get('user.name', 'Levi K.'))
        name.setStyleSheet("color: #E8E6DF; font-size: 11px;")
        self._crumb = QLabel("—")
        self._crumb.setObjectName("eyebrow")
        col.addWidget(name)
        col.addWidget(self._crumb)
        btn_h.addWidget(avatar)
        btn_h.addLayout(col)
        btn_h.addStretch()

        h.addWidget(user_btn)
        h.addStretch()
        return wrap

    def _mount_tabs(self):
        """Construct every tab class and register them in the stack."""
        # Lazy imports keep startup time predictable and avoid circular deps.
        from ui.tabs.ingest_tab import IngestTab
        from ui.tabs.proxy_tab import ProxyTab
        from ui.tabs.bulk_renamer_tab import BulkRenamerTab
        from ui.tabs.file_organizer_tab import FileOrganizerTab
        from ui.tabs.archive_extractor_tab import ArchiveExtractorTab
        from ui.tabs.image_browser_tab import ImageBrowserTab
        from ui.tabs.studio_tabs import (
            ColdStorageTab, ExportWatcherTab, NLEBackupTab,
            StaleFilesTab, StorageReportTab, TrashTab,
        )
        from ui.tabs.maintain_panes import SyncCheckTab, WatchFoldersTab
        from ui.tabs.delivery_validator_tab import SpecValidatorTab
        from ui.tabs.delivery_package_tab import PackageExportTab

        # factory_key -> tab instance
        validator_tab = SpecValidatorTab(self.config)
        package_tab   = PackageExportTab(self.config)
        # Cross-tab wire: when validator emits pass, pre-fill the package tab.
        validator_tab.validation_passed.connect(
            lambda passed: package_tab.set_source_from_validator(
                validator_tab.get_directory()
            ) if passed else None
        )

        watch_folders_tab = WatchFoldersTab(self.config)
        # Wire the watching-dot indicator that lives in the status bar.
        watch_folders_tab.set_indicator_callback(self._update_watch_indicator)

        tabs = {
            "offload":         IngestTab(self.config),
            "proxy":           ProxyTab(self.config),
            "rename":          BulkRenamerTab(self.config),
            "organize":        FileOrganizerTab(self.config),
            "extract":         ArchiveExtractorTab(self.config),
            "stills":          ImageBrowserTab(self.config),
            "stale":           StaleFilesTab(self.config),
            "storage":         StorageReportTab(self.config),
            "nle_backup":      NLEBackupTab(self.config),
            "export_watcher":  ExportWatcherTab(self.config),
            "trash":           TrashTab(self.config),
            "sync_check":      SyncCheckTab(self.config),
            "watch_folders":   watch_folders_tab,
            "validator":       validator_tab,
            "package":         package_tab,
            "cold_storage":    ColdStorageTab(self.config),
        }
        for key, tab in tabs.items():
            tab.status_changed.connect(self._update_status)
            self._tab_instances.append(tab)
            self._stack_index_for_key[key] = self.stack.addWidget(tab)

        # Default to Offload
        self.sidebar.select_key("offload")

    # ─────────────────────────────────────────────────────────────────
    # Navigation routing
    # ─────────────────────────────────────────────────────────────────
    def _on_nav_activated(self, factory_key: str):
        # All destinations are now real panes in the QStackedWidget.
        idx = self._stack_index_for_key.get(factory_key)
        if idx is not None:
            self.stack.setCurrentIndex(idx)
            # Update breadcrumb
            for section_label, items in NAV_TREE:
                for label, _icon, key in items:
                    if key == factory_key:
                        self._crumb.setText(f"{section_label.split('·')[0].strip()} · {label.upper()}")
                        return

    # ─────────────────────────────────────────────────────────────────
    # Menu bar (slimmer — Sync/Watch are in the sidebar now)
    # ─────────────────────────────────────────────────────────────────
    def _setup_menu_bar(self):
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        open_act = QAction("&Open Folder…", self)
        open_act.setShortcut(QKeySequence.Open)
        open_act.triggered.connect(self._open_directory)
        file_menu.addAction(open_act)
        file_menu.addSeparator()
        exit_act = QAction("E&xit", self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        edit_menu = bar.addMenu("&Edit")
        settings_act = QAction("&Settings…", self)
        settings_act.setShortcut(QKeySequence.Preferences)
        settings_act.triggered.connect(self._show_settings)
        edit_menu.addAction(settings_act)
        history_act = QAction("Rename &History…", self)
        history_act.triggered.connect(self._show_history)
        edit_menu.addAction(history_act)
        profiles_act = QAction("&Naming Profiles…", self)
        profiles_act.triggered.connect(self._manage_profiles)
        edit_menu.addAction(profiles_act)
        edit_menu.addSeparator()
        clear_act = QAction("Clear All &Caches", self)
        clear_act.triggered.connect(self._clear_caches)
        edit_menu.addAction(clear_act)

        view_menu = bar.addMenu("&View")
        refresh_act = QAction("&Refresh", self)
        refresh_act.setShortcut(QKeySequence.Refresh)
        refresh_act.triggered.connect(self._refresh_current)
        view_menu.addAction(refresh_act)

        help_menu = bar.addMenu("&Help")
        about_act = QAction("&About", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _setup_shortcuts(self):
        # Cmd/Ctrl + 1..5 jumps to the first item of each section
        section_first_keys = ["offload", "rename", "stale", "validator", "cold_storage"]
        for i, key in enumerate(section_first_keys):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda k=key: self.sidebar.select_key(k))
        QShortcut(QKeySequence("Ctrl+W"), self).activated.connect(self.close)

    # ─────────────────────────────────────────────────────────────────
    # Window state persistence
    # ─────────────────────────────────────────────────────────────────
    def _load_window_state(self):
        screen = QApplication.primaryScreen().availableGeometry()
        remember_size = self.config.get('settings.remember_window_size', True)

        geo = self.config.get('window.geometry') if remember_size else None
        if geo and len(geo) == 4:
            x, y, w, h = geo
        else:
            w = DEFAULT_WINDOW_WIDTH
            h = DEFAULT_WINDOW_HEIGHT
            x = screen.x() + (screen.width() - w) // 2
            y = screen.y() + (screen.height() - h) // 2
        max_w = int(screen.width() * 0.90)
        max_h = int(screen.height() * 0.85)
        w = min(w, max_w); h = min(h, max_h)
        x = max(screen.x(), min(x, screen.x() + screen.width() - w))
        y = max(screen.y(), min(y, screen.y() + screen.height() - h))
        self.setGeometry(x, y, w, h)
        if remember_size and self.config.get('window.maximized', False):
            self.showMaximized()

        remember_tab = self.config.get('settings.remember_last_tab', True)
        last_key = self.config.get('window.last_nav', 'offload') if remember_tab else 'offload'
        self.sidebar.select_key(last_key)

    def _save_window_state(self):
        geo = self.geometry()
        self.config.set('window.geometry', [geo.x(), geo.y(), geo.width(), geo.height()])
        self.config.set('window.maximized', self.isMaximized())
        key = self.sidebar.current_key()
        if key:
            self.config.set('window.last_nav', key)
        self.config.save_to_file()

    def closeEvent(self, event):
        for tab in self._tab_instances:
            if hasattr(tab, 'save_settings'):
                tab.save_settings()
        self._save_window_state()
        event.accept()

    # ─────────────────────────────────────────────────────────────────
    # Status / misc
    # ─────────────────────────────────────────────────────────────────
    def _update_status(self, message: str):
        self.statusBar().showMessage(message)

    def _update_watch_indicator(self, active: bool):
        if active:
            self.watch_indicator.setText("●  Watching")
            self.watch_indicator.setStyleSheet("color: #6FBF73; padding: 0 6px;")
        else:
            self.watch_indicator.setText("●  Not watching")
            self.watch_indicator.setStyleSheet("color: #5C5950; padding: 0 6px;")

    def _open_directory(self):
        cur = self.stack.currentWidget()
        if hasattr(cur, 'browse_directory'):
            cur.browse_directory()

    def _refresh_current(self):
        cur = self.stack.currentWidget()
        if hasattr(cur, 'refresh'):
            cur.refresh()

    def _show_settings(self):
        from ui.dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == SettingsDialog.Accepted and getattr(dlg, 'settings_changed', False):
            QMessageBox.information(self, "Settings saved",
                                    "Some changes may require restarting the application.")

    def _show_history(self):
        from ui.dialogs.history_dialog import HistoryDialog
        HistoryDialog(self).exec()

    def _manage_profiles(self):
        from ui.dialogs.profile_dialog import ProfileDialog
        ProfileDialog(self.config, self).exec()

    def _clear_caches(self):
        reply = QMessageBox.question(
            self, "Clear caches",
            "Clear all cached data (image directory scans)?\n\nAre you sure?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        from pathlib import Path as _P
        cleared = 0
        total = 0
        names = ['.image_browser_cache.json']
        roots = [_P.home()]
        if self.config.config_path:
            roots.append(_P(self.config.config_path).parent)
        for root in roots:
            if not root.exists():
                continue
            for name in names:
                for f in root.rglob(name):
                    try:
                        if f.is_file():
                            total += f.stat().st_size
                            f.unlink()
                            cleared += 1
                    except OSError:
                        pass
        if cleared:
            kb = total / 1024
            sz = f"{kb:.2f} KB" if kb < 1024 else f"{kb/1024:.2f} MB"
            QMessageBox.information(self, "Cache cleared",
                                    f"Cleared {cleared} cache file(s)\nFreed {sz} of disk space")
        else:
            QMessageBox.information(self, "No caches found",
                                    "No cache files were found to clear.")

    def _show_about(self):
        from __init__ import __version__
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>{APP_NAME}</h3>"
            f"<p><b>Version {__version__}</b></p>"
            f"<p>A premium post-production file management suite.</p>"
            f"<p><b>Modules:</b></p>"
            f"<ul>"
            f"<li><b>Ingest</b> — offload + verify, proxy generation</li>"
            f"<li><b>Organize</b> — rename, group, extract, browse stills</li>"
            f"<li><b>Maintain</b> — studio tools, sync check, watch folders</li>"
            f"<li><b>Deliver</b> — spec validation + packaging</li>"
            f"<li><b>Archive</b> — LTO / cold storage <i>(planned)</i></li>"
            f"</ul>"
            f"<p style='margin-top:10px;'><i>Built with PySide6</i></p>"
        )

    # ─────────────────────────────────────────────────────────────────
    # User footer context menu
    # ─────────────────────────────────────────────────────────────────
    def _show_user_menu(self):
        menu = QMenu(self)
        menu.addAction("Settings…", self._show_settings)
        menu.addAction("Naming Profiles…", self._manage_profiles)
        menu.addAction("Rename History…", self._show_history)
        menu.addSeparator()
        menu.addAction("About Pearl Post Suite", self._show_about)
        menu.exec(QCursor.pos())

    # ─────────────────────────────────────────────────────────────────
    # Project management
    # ─────────────────────────────────────────────────────────────────
    def _get_projects(self) -> list:
        """Return list of Project dicts from config."""
        return self.config.get('projects', [])

    def _save_projects(self, projects: list):
        self.config.set('projects', projects)
        self.config.save_to_file()

    def _get_active_project_name(self) -> Optional[str]:
        return self.config.get('active_project', None)

    def _set_active_project(self, name: Optional[str]):
        self.config.set('active_project', name)
        self.config.save_to_file()
        self._refresh_project_strip()
        self._apply_project_defaults()

    def _refresh_project_strip(self):
        name = self._get_active_project_name()
        if name:
            self._proj_label.setText(name)
            # Find description
            for p in self._get_projects():
                if p.get('name') == name:
                    desc = p.get('description', '')
                    self._proj_meta.setText(desc if desc else "Active project")
                    return
            self._proj_meta.setText("Active project")
        else:
            self._proj_label.setText("No project loaded")
            self._proj_meta.setText("Click to create or select a project")

    def _show_project_menu(self):
        menu = QMenu(self)
        projects = self._get_projects()
        active = self._get_active_project_name()

        if projects:
            for p in projects:
                name = p.get('name', 'Untitled')
                act = menu.addAction(
                    f"{'★ ' if name == active else ''}{name}"
                )
                act.triggered.connect(
                    lambda checked, n=name: self._set_active_project(n)
                )
            menu.addSeparator()

        menu.addAction("No Project", lambda: self._set_active_project(None))
        menu.addSeparator()
        menu.addAction("New Project…", self._new_project)
        if active:
            menu.addAction("Edit Current Project…", self._edit_current_project)
            menu.addAction("Delete Current Project", self._delete_current_project)

        menu.exec(QCursor.pos())

    def _new_project(self):
        from ui.dialogs.project_dialog import ProjectDialog
        dlg = ProjectDialog(parent=self)
        if dlg.exec() == ProjectDialog.Accepted and dlg.result_project:
            projects = self._get_projects()
            projects.append(dlg.result_project.to_dict())
            self._save_projects(projects)
            self._set_active_project(dlg.result_project.name)

    def _edit_current_project(self):
        from models.project import Project
        from ui.dialogs.project_dialog import ProjectDialog

        active = self._get_active_project_name()
        if not active:
            return

        projects = self._get_projects()
        for i, p in enumerate(projects):
            if p.get('name') == active:
                proj = Project.from_dict(p)
                dlg = ProjectDialog(project=proj, parent=self)
                if dlg.exec() == ProjectDialog.Accepted and dlg.result_project:
                    projects[i] = dlg.result_project.to_dict()
                    self._save_projects(projects)
                    self._set_active_project(dlg.result_project.name)
                return

    def _delete_current_project(self):
        active = self._get_active_project_name()
        if not active:
            return
        reply = QMessageBox.question(
            self, "Delete project",
            f"Delete project '{active}'?\n\n"
            "This removes the project definition only — no files are deleted.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        projects = [p for p in self._get_projects() if p.get('name') != active]
        self._save_projects(projects)
        self._set_active_project(None)

    def _apply_project_defaults(self):
        """Auto-populate PathCards in tabs from the active project's default_paths."""
        from models.project import Project

        active = self._get_active_project_name()
        if not active:
            return

        for p in self._get_projects():
            if p.get('name') == active:
                proj = Project.from_dict(p)
                paths = proj.default_paths

                # Find tabs by factory key and apply defaults
                for tab in self._tab_instances:
                    tab_name = getattr(tab, 'get_tab_name', lambda: '')()
                    if tab_name == "Offload" and hasattr(tab, '_pane'):
                        pane = tab._pane
                        if paths.get('ingest_source') and not pane.card_src.get_path():
                            pane.card_src.set_path(paths['ingest_source'])
                        if paths.get('ingest_dest') and not pane.card_dst.get_path():
                            pane.card_dst.set_path(paths['ingest_dest'])
                        if paths.get('mirror_dest') and not pane.card_mirror.get_path():
                            pane.card_mirror.set_path(paths['mirror_dest'])
                return
