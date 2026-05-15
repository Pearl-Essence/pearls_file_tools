"""Settings dialog for Pearl Post Suite."""

import sys

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    """Dialog for application settings."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.settings_changed = False

        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(620, 520)

        self._setup_ui()
        self._load_settings()

    # ── UI construction ──────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout()

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_general_tab(), "General")
        self.tab_widget.addTab(self._create_organizer_tab(), "File Organizer")
        self.tab_widget.addTab(self._create_browser_tab(), "File Browser")
        self.tab_widget.addTab(self._create_email_tab(), "Email")
        self.tab_widget.addTab(self._create_about_tab(), "About")
        layout.addWidget(self.tab_widget)

        # Buttons
        btn_row = QHBoxLayout()
        restore_btn = QPushButton("Restore Defaults")
        restore_btn.setToolTip("Reset all settings on this page to their defaults")
        restore_btn.clicked.connect(self._restore_defaults)
        btn_row.addWidget(restore_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_settings)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)
        self.setLayout(layout)

    # ── Tab: General ─────────────────────────────────────────────────────

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        # Window behaviour
        win_group = QGroupBox("Window")
        win_layout = QVBoxLayout()

        self.chk_remember_size = QCheckBox("Remember window size and position")
        self.chk_remember_size.setToolTip("Restore the last window geometry on launch instead of using defaults")
        win_layout.addWidget(self.chk_remember_size)

        self.chk_remember_tab = QCheckBox("Remember last active sidebar destination")
        self.chk_remember_tab.setToolTip("Return to the same tab on next launch instead of starting at Offload")
        win_layout.addWidget(self.chk_remember_tab)

        win_group.setLayout(win_layout)
        layout.addWidget(win_group)

        # Performance
        perf_group = QGroupBox("Performance")
        perf_layout = QVBoxLayout()

        self.chk_cache_scans = QCheckBox("Cache media directory scans")
        self.chk_cache_scans.setToolTip("Write a hidden JSON cache so repeated scans of the same folder are instant")
        perf_layout.addWidget(self.chk_cache_scans)

        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        # Startup
        startup_group = QGroupBox("Startup")
        startup_layout = QVBoxLayout()

        self.chk_auto_launch = QCheckBox("Launch Pearl Post Suite at login")
        self.chk_auto_launch.setToolTip(
            "Automatically start the application when you log in to your computer.\n"
            "Useful when running Export Watcher or Watch Folders unattended."
        )
        startup_layout.addWidget(self.chk_auto_launch)

        startup_group.setLayout(startup_layout)
        layout.addWidget(startup_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ── Tab: File Organizer ──────────────────────────────────────────────

    def _create_organizer_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        pattern_group = QGroupBox("Pattern Matching")
        pattern_layout = QVBoxLayout()

        row = QHBoxLayout()
        lbl = QLabel("Confidence Threshold:")
        lbl.setToolTip("Minimum confidence (0.0–1.0) for grouping files by pattern")

        self.spin_confidence = QDoubleSpinBox()
        self.spin_confidence.setRange(0.0, 1.0)
        self.spin_confidence.setSingleStep(0.1)
        self.spin_confidence.setDecimals(2)
        self.spin_confidence.setValue(0.4)

        row.addWidget(lbl)
        row.addWidget(self.spin_confidence)
        row.addStretch()
        pattern_layout.addLayout(row)

        help_lbl = QLabel(
            "Lower values (0.2–0.3): More aggressive grouping, may group unrelated files\n"
            "Medium values (0.4–0.6): Balanced grouping (recommended)\n"
            "Higher values (0.7–0.9): Conservative grouping, only groups very similar files"
        )
        help_lbl.setObjectName("cardSub")
        help_lbl.setWordWrap(True)
        pattern_layout.addWidget(help_lbl)

        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ── Tab: File Browser ────────────────────────────────────────────────

    def _create_browser_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        display_group = QGroupBox("Display")
        display_layout = QVBoxLayout()

        row = QHBoxLayout()
        lbl = QLabel("Default Thumbnail Size:")

        self.spin_thumb_size = QSpinBox()
        self.spin_thumb_size.setRange(100, 400)
        self.spin_thumb_size.setSingleStep(50)
        self.spin_thumb_size.setValue(200)
        self.spin_thumb_size.setSuffix(" px")

        row.addWidget(lbl)
        row.addWidget(self.spin_thumb_size)
        row.addStretch()
        display_layout.addLayout(row)

        display_group.setLayout(display_layout)
        layout.addWidget(display_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ── Tab: Email ───────────────────────────────────────────────────────

    def _create_email_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        smtp_group = QGroupBox("SMTP Configuration")
        smtp_group.setToolTip("Configure an SMTP server for sending ingest completion reports")
        smtp_layout = QVBoxLayout()

        # Server
        row_server = QHBoxLayout()
        row_server.addWidget(QLabel("SMTP Server:"))
        self.edit_smtp_server = QLineEdit()
        self.edit_smtp_server.setPlaceholderText("e.g. smtp.gmail.com")
        row_server.addWidget(self.edit_smtp_server, stretch=1)
        smtp_layout.addLayout(row_server)

        # Port + TLS
        row_port = QHBoxLayout()
        row_port.addWidget(QLabel("Port:"))
        self.spin_smtp_port = QSpinBox()
        self.spin_smtp_port.setRange(1, 65535)
        self.spin_smtp_port.setValue(587)
        row_port.addWidget(self.spin_smtp_port)
        row_port.addSpacing(20)
        self.chk_use_tls = QCheckBox("Use TLS")
        self.chk_use_tls.setChecked(True)
        row_port.addWidget(self.chk_use_tls)
        row_port.addStretch()
        smtp_layout.addLayout(row_port)

        # From
        row_from = QHBoxLayout()
        row_from.addWidget(QLabel("From:"))
        self.edit_from = QLineEdit()
        self.edit_from.setPlaceholderText("sender@example.com")
        row_from.addWidget(self.edit_from, stretch=1)
        smtp_layout.addLayout(row_from)

        # To
        row_to = QHBoxLayout()
        row_to.addWidget(QLabel("To:"))
        self.edit_to = QLineEdit()
        self.edit_to.setPlaceholderText("recipient@example.com")
        row_to.addWidget(self.edit_to, stretch=1)
        smtp_layout.addLayout(row_to)

        smtp_group.setLayout(smtp_layout)
        layout.addWidget(smtp_group)

        note = QLabel(
            "Credentials are not stored — the SMTP server must accept "
            "unauthenticated relay from this machine, or use an app-specific "
            "password via environment variable PEARL_SMTP_PASSWORD."
        )
        note.setObjectName("cardSub")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ── Tab: About ───────────────────────────────────────────────────────

    def _create_about_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        import PySide6

        from __init__ import __version__

        info_group = QGroupBox("Application Info")
        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel(f"Pearl Post Suite v{__version__}"))
        info_layout.addWidget(QLabel(f"Python {sys.version.split()[0]}"))
        info_layout.addWidget(QLabel(f"PySide6 {PySide6.__version__}"))
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        future = QLabel("Additional settings will appear here as features are added.")
        future.setObjectName("cardSub")
        future.setWordWrap(True)
        layout.addWidget(future)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ── Load / Save ──────────────────────────────────────────────────────

    def _load_settings(self):
        # General
        self.chk_remember_size.setChecked(self.config.get("settings.remember_window_size", True))
        self.chk_remember_tab.setChecked(self.config.get("settings.remember_last_tab", True))
        self.chk_cache_scans.setChecked(self.config.get("settings.cache_image_scans", True))

        # Auto-launch — read actual OS state, not config
        from core.auto_launch import get_auto_launch

        self.chk_auto_launch.setChecked(get_auto_launch())

        # File Organizer
        self.spin_confidence.setValue(self.config.get_tab_setting("organizer", "confidence_threshold", 0.4))

        # File Browser
        self.spin_thumb_size.setValue(self.config.get_tab_setting("image_browser", "thumbnail_size", 200))

        # Email
        self.edit_smtp_server.setText(self.config.get("email.smtp_server", ""))
        self.spin_smtp_port.setValue(self.config.get("email.smtp_port", 587))
        self.chk_use_tls.setChecked(self.config.get("email.use_tls", True))
        self.edit_from.setText(self.config.get("email.from_address", ""))
        self.edit_to.setText(self.config.get("email.to_address", ""))

    def _save_settings(self):
        # General
        self.config.set("settings.remember_window_size", self.chk_remember_size.isChecked())
        self.config.set("settings.remember_last_tab", self.chk_remember_tab.isChecked())
        self.config.set("settings.cache_image_scans", self.chk_cache_scans.isChecked())

        # Auto-launch — apply to OS
        from core.auto_launch import set_auto_launch

        set_auto_launch(self.chk_auto_launch.isChecked())

        # File Organizer
        self.config.set_tab_setting("organizer", "confidence_threshold", self.spin_confidence.value())

        # File Browser
        self.config.set_tab_setting("image_browser", "thumbnail_size", self.spin_thumb_size.value())

        # Email
        self.config.set("email.smtp_server", self.edit_smtp_server.text().strip())
        self.config.set("email.smtp_port", self.spin_smtp_port.value())
        self.config.set("email.use_tls", self.chk_use_tls.isChecked())
        self.config.set("email.from_address", self.edit_from.text().strip())
        self.config.set("email.to_address", self.edit_to.text().strip())

        self.config.save_to_file()
        self.settings_changed = True
        self.accept()

    def _restore_defaults(self):
        reply = QMessageBox.question(
            self,
            "Restore Defaults",
            "This will restore all settings to their default values.\n\n" "Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # General
        self.chk_remember_size.setChecked(True)
        self.chk_remember_tab.setChecked(True)
        self.chk_cache_scans.setChecked(True)
        self.chk_auto_launch.setChecked(False)

        # File Organizer
        self.spin_confidence.setValue(0.4)

        # File Browser
        self.spin_thumb_size.setValue(200)

        # Email
        self.edit_smtp_server.clear()
        self.spin_smtp_port.setValue(587)
        self.chk_use_tls.setChecked(True)
        self.edit_from.clear()
        self.edit_to.clear()

        QMessageBox.information(
            self,
            "Defaults Restored",
            "Default settings have been restored.\n\n" "Click 'Save' to apply the changes.",
        )
