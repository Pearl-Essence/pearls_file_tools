"""Image card widget for displaying image thumbnails."""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QColor, QPainter, QFont
from pathlib import Path
from typing import Dict


class ImageCard(QFrame):
    """A card widget displaying an image thumbnail and info."""

    clicked = pyqtSignal(object)  # Emits the image data dict

    def __init__(self, image_data: Dict, thumbnail_size: int = 200):
        """
        Initialize the image card.

        Args:
            image_data: Dictionary with 'name', 'path', 'folder', 'size'
            thumbnail_size: Size of the thumbnail in pixels
        """
        super().__init__()
        self.image_data = image_data
        self.thumbnail_size = thumbnail_size

        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setCursor(Qt.PointingHandCursor)

        # Set fixed size for consistent grid layout
        self.setFixedSize(thumbnail_size + 20, thumbnail_size + 60)

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(thumbnail_size, thumbnail_size)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("background-color: #2b2b2b; border: 1px solid #555;")

        # Load thumbnail
        self._load_thumbnail()

        # Image name
        name_label = QLabel(image_data['name'])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 10px;")
        name_label.setMaximumHeight(40)
        name_label.setToolTip(image_data['name'])

        layout.addWidget(self.thumbnail_label)
        layout.addWidget(name_label)
        layout.addStretch()

        self.setLayout(layout)

    def _load_thumbnail(self):
        """Load and display the thumbnail image."""
        try:
            image_path = Path(self.image_data['path'])

            if not image_path.exists():
                # Create an error placeholder
                pixmap = self._create_error_placeholder()
                self.thumbnail_label.setPixmap(pixmap)
                return

            # Load the image
            pixmap = QPixmap(str(image_path))

            if pixmap.isNull():
                # Create an error placeholder
                pixmap = self._create_error_placeholder()
                self.thumbnail_label.setPixmap(pixmap)
            else:
                # Scale to fit while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    self.thumbnail_size, self.thumbnail_size,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.thumbnail_label.setPixmap(scaled_pixmap)

        except Exception as e:
            # Create an error placeholder
            pixmap = self._create_error_placeholder()
            self.thumbnail_label.setPixmap(pixmap)

    def _create_error_placeholder(self):
        """Create a pixmap with an error indicator."""
        pixmap = QPixmap(self.thumbnail_size, self.thumbnail_size)
        pixmap.fill(QColor("#3b3b3b"))

        painter = QPainter(pixmap)
        painter.setPen(QColor("#ff6b6b"))

        font = QFont("Arial", 80, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "✗")
        painter.end()

        return pixmap

    def mousePressEvent(self, event):
        """Handle mouse click to open image viewer."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.image_data)
