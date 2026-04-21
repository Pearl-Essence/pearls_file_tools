"""Settings dialog for Pearl's File Tools."""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                            QTabWidget, QWidget, QLabel, QSpinBox, QGroupBox,
                            QCheckBox, QDoubleSpinBox, QMessageBox)
from PyQt5.QtCore import Qt
from pathlib import Path


class SettingsDialog(QDialog):
    """Dialog for application settings."""

    def __init__(self, config, parent=None):
        """
        Initialize the settings dialog.

        Args:
            config: Config instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.config = config
        self.settings_changed = False

        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(600, 500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout()

        # Tab widget for different setting categories
        self.tab_widget = QTabWidget()

        # General settings tab
        general_tab = self.create_general_tab()
        self.tab_widget.addTab(general_tab, "General")

        # File Organizer settings tab
        organizer_tab = self.create_organizer_tab()
        self.tab_widget.addTab(organizer_tab, "File Organizer")

        # Image Browser settings tab
        image_tab = self.create_image_tab()
        self.tab_widget.addTab(image_tab, "Image Browser")

        layout.addWidget(self.tab_widget)

        # Buttons
        button_layout = QHBoxLayout()

        self.restore_defaults_btn = QPushButton("Restore Defaults")
        self.restore_defaults_btn.clicked.connect(self.restore_defaults)
        button_layout.addWidget(self.restore_defaults_btn)

        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_settings)
        self.save_btn.setDefault(True)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def create_general_tab(self):
        """Create general settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Window settings
        window_group = QGroupBox("Window")
        window_layout = QVBoxLayout()

        self.remember_size_check = QCheckBox("Remember window size and position")
        self.remember_size_check.setChecked(True)
        window_layout.addWidget(self.remember_size_check)

        self.remember_tab_check = QCheckBox("Remember last active tab")
        self.remember_tab_check.setChecked(True)
        window_layout.addWidget(self.remember_tab_check)

        window_group.setLayout(window_layout)
        layout.addWidget(window_group)

        # Performance settings
        perf_group = QGroupBox("Performance")
        perf_layout = QVBoxLayout()

        cache_label = QLabel("Enable caching for better performance:")
        perf_layout.addWidget(cache_label)

        self.cache_image_scan_check = QCheckBox("Cache image directory scans")
        self.cache_image_scan_check.setChecked(True)
        self.cache_image_scan_check.setToolTip("Speeds up repeated scans of the same directory")
        perf_layout.addWidget(self.cache_image_scan_check)

        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def create_organizer_tab(self):
        """Create file organizer settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Pattern matching settings
        pattern_group = QGroupBox("Pattern Matching")
        pattern_layout = QVBoxLayout()

        confidence_layout = QHBoxLayout()
        confidence_label = QLabel("Confidence Threshold:")
        confidence_label.setToolTip("Minimum confidence (0.0-1.0) for grouping files by pattern")

        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.0, 1.0)
        self.confidence_spin.setSingleStep(0.1)
        self.confidence_spin.setValue(0.4)
        self.confidence_spin.setDecimals(2)

        confidence_layout.addWidget(confidence_label)
        confidence_layout.addWidget(self.confidence_spin)
        confidence_layout.addStretch()

        pattern_layout.addLayout(confidence_layout)

        help_label = QLabel(
            "Lower values (0.2-0.3): More aggressive grouping, may group unrelated files\n"
            "Medium values (0.4-0.6): Balanced grouping (recommended)\n"
            "Higher values (0.7-0.9): Conservative grouping, only groups very similar files"
        )
        help_label.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
        help_label.setWordWrap(True)
        pattern_layout.addWidget(help_label)

        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)

        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def create_image_tab(self):
        """Create image browser settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Display settings
        display_group = QGroupBox("Display")
        display_layout = QVBoxLayout()

        size_layout = QHBoxLayout()
        size_label = QLabel("Default Thumbnail Size:")

        self.default_thumb_size_spin = QSpinBox()
        self.default_thumb_size_spin.setRange(100, 400)
        self.default_thumb_size_spin.setSingleStep(50)
        self.default_thumb_size_spin.setValue(200)
        self.default_thumb_size_spin.setSuffix(" px")

        size_layout.addWidget(size_label)
        size_layout.addWidget(self.default_thumb_size_spin)
        size_layout.addStretch()

        display_layout.addLayout(size_layout)

        display_group.setLayout(display_layout)
        layout.addWidget(display_group)

        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def load_settings(self):
        """Load settings from config."""
        # General settings
        self.remember_size_check.setChecked(
            self.config.get('settings.remember_window_size', True)
        )
        self.remember_tab_check.setChecked(
            self.config.get('settings.remember_last_tab', True)
        )
        self.cache_image_scan_check.setChecked(
            self.config.get('settings.cache_image_scans', True)
        )

        # File Organizer settings
        self.confidence_spin.setValue(
            self.config.get_tab_setting('organizer', 'confidence_threshold', 0.4)
        )

        # Image Browser settings
        self.default_thumb_size_spin.setValue(
            self.config.get_tab_setting('image_browser', 'thumbnail_size', 200)
        )

    def save_settings(self):
        """Save settings to config."""
        # General settings
        self.config.set('settings.remember_window_size', self.remember_size_check.isChecked())
        self.config.set('settings.remember_last_tab', self.remember_tab_check.isChecked())
        self.config.set('settings.cache_image_scans', self.cache_image_scan_check.isChecked())

        # File Organizer settings
        self.config.set_tab_setting('organizer', 'confidence_threshold', self.confidence_spin.value())

        # Image Browser settings
        self.config.set_tab_setting('image_browser', 'thumbnail_size', self.default_thumb_size_spin.value())

        # Save to file
        self.config.save_to_file()

        self.settings_changed = True
        self.accept()

    def restore_defaults(self):
        """Restore default settings."""
        reply = QMessageBox.question(
            self,
            "Restore Defaults",
            "This will restore all settings to their default values.\n\n"
            "Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # General settings
            self.remember_size_check.setChecked(True)
            self.remember_tab_check.setChecked(True)
            self.cache_image_scan_check.setChecked(True)

            # File Organizer settings
            self.confidence_spin.setValue(0.4)

            # Image Browser settings
            self.default_thumb_size_spin.setValue(200)

            QMessageBox.information(
                self,
                "Defaults Restored",
                "Default settings have been restored.\n\n"
                "Click 'Save' to apply the changes."
            )
