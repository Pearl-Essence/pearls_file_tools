"""Image viewer dialog for full-size image viewing."""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from pathlib import Path
from typing import List, Dict


class ImageViewerDialog(QDialog):
    """Full-screen dialog for viewing images with navigation."""

    def __init__(self, images: List[Dict], start_index: int = 0, parent=None):
        """
        Initialize the image viewer dialog.

        Args:
            images: List of image data dictionaries
            start_index: Index of the image to show first
            parent: Parent widget
        """
        super().__init__(parent)
        self.images = images
        self.current_index = start_index

        self.setWindowTitle("Image Viewer")
        self.setModal(True)
        self.resize(1200, 900)

        self.setup_ui()

        # Show first image
        if images:
            self.show_image(start_index)

    def setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout()

        # Header with image info
        self.header_label = QLabel()
        self.header_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px;")
        self.header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.header_label)

        # Image display
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(800, 600)
        self.image_label.setStyleSheet("background-color: #1a1a1a;")
        layout.addWidget(self.image_label, stretch=1)

        # Navigation controls
        nav_layout = QHBoxLayout()

        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.clicked.connect(self.show_previous)
        self.prev_btn.setShortcut(Qt.Key_Left)

        self.counter_label = QLabel()
        self.counter_label.setAlignment(Qt.AlignCenter)
        self.counter_label.setStyleSheet("font-size: 12px; color: #888;")

        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self.show_next)
        self.next_btn.setShortcut(Qt.Key_Right)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setShortcut(Qt.Key_Escape)

        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.counter_label, stretch=1)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addWidget(close_btn)

        layout.addLayout(nav_layout)

        self.setLayout(layout)

    def show_image(self, index: int):
        """Display the image at the given index."""
        if not self.images:
            self.image_label.setText("No images to display")
            return

        # Wrap index
        self.current_index = index % len(self.images)
        image_data = self.images[self.current_index]

        # Update header
        folder = image_data.get('folder', 'Unknown')
        name = image_data.get('name', 'Unknown')
        self.header_label.setText(f"{folder} / {name}")

        # Load and display image
        image_path = Path(image_data['path'])

        if not image_path.exists():
            self.image_label.setText(f"Image not found:\n{image_path}")
            return

        pixmap = QPixmap(str(image_path))

        if pixmap.isNull():
            self.image_label.setText(f"Failed to load image:\n{name}")
        else:
            # Scale to fit while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)

        # Update counter
        total = len(self.images)
        self.counter_label.setText(f"{self.current_index + 1} / {total}")

        # Enable/disable navigation buttons
        self.prev_btn.setEnabled(total > 1)
        self.next_btn.setEnabled(total > 1)

    def show_previous(self):
        """Show the previous image."""
        self.show_image(self.current_index - 1)

    def show_next(self):
        """Show the next image."""
        self.show_image(self.current_index + 1)

    def keyPressEvent(self, event):
        """Handle keyboard navigation."""
        if event.key() == Qt.Key_Left:
            self.show_previous()
        elif event.key() == Qt.Key_Right:
            self.show_next()
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        """Handle window resize."""
        super().resizeEvent(event)
        # Reload current image to fit new size
        if self.images and 0 <= self.current_index < len(self.images):
            self.show_image(self.current_index)
