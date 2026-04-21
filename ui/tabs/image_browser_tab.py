"""Image Browser tab for Pearl's File Tools."""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                            QLineEdit, QScrollArea, QGridLayout, QCheckBox,
                            QComboBox, QSpinBox, QGroupBox)
from PyQt5.QtCore import Qt
from pathlib import Path
from typing import List, Dict
from ui.tabs.base_tab import BaseTab
from ui.widgets.directory_selector import DirectorySelectorWidget


class ImageBrowserTab(BaseTab):
    """Tab for browsing and viewing images in a directory."""

    def __init__(self, config, parent=None):
        """Initialize the image browser tab."""
        self.all_images = []  # List of ImageData objects
        self.filtered_images = []  # Currently displayed images
        self.folders = {}  # folder_name -> count
        super().__init__(config, parent)

    def get_tab_name(self) -> str:
        """Get the tab name."""
        return "Image Browser"

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()

        # Directory selection
        self.dir_selector = DirectorySelectorWidget(
            label_text="Image Directory:",
            show_recursive=True
        )
        self.dir_selector.directory_changed.connect(self.on_directory_changed)
        layout.addWidget(self.dir_selector)

        # Control bar
        controls_group = QGroupBox("Controls")
        controls_layout = QHBoxLayout()

        self.scan_btn = QPushButton("Scan for Images")
        self.scan_btn.clicked.connect(self.scan_directory)
        self.scan_btn.setStyleSheet("padding: 8px; font-weight: bold;")
        controls_layout.addWidget(self.scan_btn)

        self.refresh_btn = QPushButton("Refresh (Ignore Cache)")
        self.refresh_btn.clicked.connect(self.refresh_directory)
        self.refresh_btn.setEnabled(False)
        controls_layout.addWidget(self.refresh_btn)

        controls_layout.addStretch()

        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # Filters
        filter_group = QGroupBox("Filters")
        filter_layout = QVBoxLayout()

        # Row 1: Search and folder filter
        row1 = QHBoxLayout()

        search_label = QLabel("Search:")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by filename...")
        self.search_box.textChanged.connect(self.apply_filters)

        folder_label = QLabel("Folder:")
        self.folder_combo = QComboBox()
        self.folder_combo.addItem("All Folders")
        self.folder_combo.currentTextChanged.connect(self.apply_filters)

        row1.addWidget(search_label)
        row1.addWidget(self.search_box, stretch=1)
        row1.addWidget(folder_label)
        row1.addWidget(self.folder_combo)

        # Row 2: Thumbnail size
        row2 = QHBoxLayout()

        size_label = QLabel("Thumbnail Size:")
        self.size_spin = QSpinBox()
        self.size_spin.setRange(100, 400)
        self.size_spin.setValue(200)
        self.size_spin.setSuffix(" px")
        self.size_spin.valueChanged.connect(self.on_thumbnail_size_changed)

        row2.addWidget(size_label)
        row2.addWidget(self.size_spin)
        row2.addStretch()

        filter_layout.addLayout(row1)
        filter_layout.addLayout(row2)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # Status label
        self.status_label = QLabel("Select a directory and scan for images")
        self.status_label.setStyleSheet("padding: 5px; font-style: italic; color: #888;")
        layout.addWidget(self.status_label)

        # Scroll area for image grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        from PyQt5.QtWidgets import QWidget
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)
        self.grid_widget.setLayout(self.grid_layout)

        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll, stretch=1)

        self.setLayout(layout)

    def on_directory_changed(self, directory: str):
        """Handle directory change."""
        self.set_directory(directory)
        self.all_images.clear()
        self.filtered_images.clear()
        self.folders.clear()
        self.clear_grid()
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("Ready to scan")

    def scan_directory(self):
        """Start scanning directory for images."""
        if not self.current_directory:
            self.show_warning("No Directory", "Please select a directory first.")
            return

        if not Path(self.current_directory).is_dir():
            self.show_error("Invalid Directory", "The selected directory does not exist.")
            return

        self.scan_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("Scanning for images...")

        # Get recursive setting
        recursive = self.dir_selector.is_recursive()

        # Start scan worker
        from workers.image_scan_worker import ImageScanWorker

        self.worker_thread = ImageScanWorker(
            self.current_directory,
            recursive=recursive,
            use_cache=True
        )
        self.worker_thread.progress.connect(self.update_scan_status)
        self.worker_thread.finished.connect(self.on_scan_finished)
        self.worker_thread.start()

    def refresh_directory(self):
        """Refresh directory, ignoring cache."""
        if not self.current_directory:
            return

        self.scan_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("Refreshing (ignoring cache)...")

        recursive = self.dir_selector.is_recursive()

        from workers.image_scan_worker import ImageScanWorker

        self.worker_thread = ImageScanWorker(
            self.current_directory,
            recursive=recursive,
            use_cache=False
        )
        self.worker_thread.progress.connect(self.update_scan_status)
        self.worker_thread.finished.connect(self.on_scan_finished)
        self.worker_thread.start()

    def update_scan_status(self, message: str):
        """Update scan status."""
        self.status_label.setText(message)

    def on_scan_finished(self, success: bool, message: str, images: List):
        """Handle scan completion."""
        self.scan_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)

        if not success:
            self.show_error("Scan Failed", message)
            self.status_label.setText("Scan failed")
            return

        self.all_images = images or []

        if not self.all_images:
            self.show_info("No Images", "No images found in the selected directory.")
            self.status_label.setText("No images found")
            return

        # Build folder list
        self.folders = {}
        for img in self.all_images:
            folder_name = img['folder']
            self.folders[folder_name] = self.folders.get(folder_name, 0) + 1

        # Populate folder filter
        self.folder_combo.clear()
        self.folder_combo.addItem("All Folders")
        for folder_name in sorted(self.folders.keys()):
            self.folder_combo.addItem(f"{folder_name} ({self.folders[folder_name]})")

        # Apply filters and display
        self.apply_filters()

        self.emit_status(f"Found {len(self.all_images)} images")

    def apply_filters(self):
        """Filter images based on search and filter criteria."""
        search_text = self.search_box.text().lower()
        selected_folder = self.folder_combo.currentText()

        # Extract folder name from "FolderName (count)" format
        if selected_folder != "All Folders" and " (" in selected_folder:
            selected_folder = selected_folder.split(" (")[0]

        self.filtered_images = []

        for img in self.all_images:
            # Apply folder filter
            if selected_folder != "All Folders" and img['folder'] != selected_folder:
                continue

            # Apply search filter
            if search_text and search_text not in img['name'].lower():
                continue

            self.filtered_images.append(img)

        self.display_images()

    def display_images(self):
        """Display the filtered images in the grid."""
        self.clear_grid()

        if not self.filtered_images:
            self.status_label.setText("No images found matching the current filters")
            return

        self.status_label.setText(f"Showing {len(self.filtered_images)} image(s)")

        # Add image cards to grid
        columns = 5  # Number of columns in grid
        thumbnail_size = self.size_spin.value()

        for i, img_data in enumerate(self.filtered_images):
            row = i // columns
            col = i % columns

            from ui.widgets.image_card import ImageCard
            card = ImageCard(img_data, thumbnail_size=thumbnail_size)
            card.clicked.connect(self.open_image_viewer)
            self.grid_layout.addWidget(card, row, col)

    def clear_grid(self):
        """Clear all widgets from the grid layout."""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def on_thumbnail_size_changed(self, value: int):
        """Handle thumbnail size change."""
        # Save to config
        self.config.set_tab_setting('image_browser', 'thumbnail_size', value)

        # Refresh display if images are loaded
        if self.filtered_images:
            self.display_images()

    def open_image_viewer(self, img_data: Dict):
        """Open the full image viewer."""
        from ui.dialogs.image_viewer_dialog import ImageViewerDialog

        # Find all images in the same folder for navigation
        folder_images = [
            img for img in self.filtered_images
            if img['folder'] == img_data['folder']
        ]

        # Find current index
        current_index = folder_images.index(img_data) if img_data in folder_images else 0

        dialog = ImageViewerDialog(folder_images, current_index, self)
        dialog.exec_()

    def load_settings(self):
        """Load tab-specific settings."""
        last_dir = self.config.get_tab_directory('image_browser')
        if last_dir:
            self.dir_selector.set_directory(last_dir)
            self.set_directory(last_dir)

        # Load thumbnail size
        thumbnail_size = self.config.get_tab_setting('image_browser', 'thumbnail_size', 200)
        self.size_spin.setValue(thumbnail_size)

    def save_settings(self):
        """Save tab-specific settings."""
        self.config.set_tab_setting('image_browser', 'thumbnail_size', self.size_spin.value())
