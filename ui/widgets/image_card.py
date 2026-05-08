"""Image/video card widget for displaying thumbnails."""

import base64
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QBrush, QPixmap, QColor, QPainter, QFont, QPolygonF
from pathlib import Path
from typing import Dict


class ImageCard(QFrame):
    """A card widget displaying an image thumbnail and info."""

    clicked = Signal(object)               # Emits the image data dict
    context_menu_requested = Signal(object, object)  # img_data, QPoint (global)

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

        # Highlight sequence cards with a blue border
        if image_data.get('is_sequence_rep'):
            self.setStyleSheet("QFrame { border: 2px solid #1e90ff; border-radius: 4px; }")

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

        # Image name — use sequence label when available
        display_name = image_data.get('sequence_label') or image_data['name']
        name_label = QLabel(display_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 10px;")
        name_label.setMaximumHeight(40)
        name_label.setToolTip(display_name)

        layout.addWidget(self.thumbnail_label)
        layout.addWidget(name_label)
        layout.addStretch()

        self.setLayout(layout)

    def _load_thumbnail(self):
        """Load and display the thumbnail."""
        try:
            is_video = self.image_data.get('is_video', False)

            if is_video:
                pixmap = self._load_video_thumbnail()
            else:
                image_path = Path(self.image_data['path'])
                if not image_path.exists():
                    pixmap = self._create_error_placeholder()
                else:
                    pixmap = QPixmap(str(image_path))
                    if pixmap.isNull():
                        pixmap = self._create_error_placeholder()
                    else:
                        pixmap = pixmap.scaled(
                            self.thumbnail_size, self.thumbnail_size,
                            Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )

            # Overlay badges
            total = self.image_data.get('sequence_total')
            if total:
                pixmap = self._add_sequence_badge(pixmap, total)

            if is_video:
                pixmap = self._add_play_overlay(pixmap)
                dur = self.image_data.get('duration_secs')
                if dur is not None:
                    pixmap = self._add_duration_badge(pixmap, dur)

            self.thumbnail_label.setPixmap(pixmap)

        except Exception:
            self.thumbnail_label.setPixmap(self._create_error_placeholder())

    def _load_video_thumbnail(self) -> QPixmap:
        """Load video thumbnail from base64 data or create a placeholder."""
        b64 = self.image_data.get('thumbnail_b64')
        if b64:
            raw = base64.b64decode(b64)
            pixmap = QPixmap()
            pixmap.loadFromData(raw, 'PNG')
            if not pixmap.isNull():
                return pixmap.scaled(
                    self.thumbnail_size, self.thumbnail_size,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
        return self._create_video_placeholder()

    def _create_video_placeholder(self) -> QPixmap:
        """Dark rect with a centered play triangle."""
        pixmap = QPixmap(self.thumbnail_size, self.thumbnail_size)
        pixmap.fill(QColor("#1a1a2e"))
        return pixmap

    def _add_play_overlay(self, base_pixmap: QPixmap) -> QPixmap:
        """Add a semi-transparent play icon in the centre."""
        result = QPixmap(base_pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        cx = result.width() / 2
        cy = result.height() / 2
        r = min(result.width(), result.height()) * 0.15

        # Circle background
        painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), r * 1.4, r * 1.4)

        # Play triangle
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        tri = QPolygonF([
            QPointF(cx - r * 0.5, cy - r),
            QPointF(cx - r * 0.5, cy + r),
            QPointF(cx + r, cy),
        ])
        painter.drawPolygon(tri)
        painter.end()
        return result

    def _add_duration_badge(self, base_pixmap: QPixmap, secs: float) -> QPixmap:
        """Overlay a duration label in the bottom-right corner."""
        mins = int(secs) // 60
        remaining = int(secs) % 60
        text = f"{mins}:{remaining:02d}"
        result = QPixmap(base_pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        font = QFont("Arial", max(7, self.thumbnail_size // 22), QFont.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text) if hasattr(fm, 'horizontalAdvance') else fm.width(text)
        th = fm.height()
        pad = 4
        bw = tw + pad * 2
        bh = th + pad
        x = result.width() - bw - 4
        y = result.height() - bh - 4

        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(x, y, bw, bh), 4, 4)

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(x + pad, y + th - fm.descent(), text)
        painter.end()
        return result

    def _add_sequence_badge(self, base_pixmap: QPixmap, total: int) -> QPixmap:
        """Overlay a '▶ N frames' badge in the bottom-right of the pixmap."""
        result = QPixmap(base_pixmap)  # copy
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        badge_text = f"\u25b6 {total} frames"
        font = QFont("Arial", max(7, self.thumbnail_size // 22), QFont.Bold)
        painter.setFont(font)

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(badge_text) if hasattr(fm, 'horizontalAdvance') \
            else fm.width(badge_text)
        text_h = fm.height()
        padding = 4
        badge_w = text_w + padding * 2
        badge_h = text_h + padding
        x = result.width() - badge_w - 4
        y = result.height() - badge_h - 4

        # Dark semi-transparent pill background
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(x, y, badge_w, badge_h), 4, 4)

        # White text
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(x + padding, y + text_h - fm.descent(), badge_text)

        painter.end()
        return result

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
        elif event.button() == Qt.RightButton:
            self.context_menu_requested.emit(
                self.image_data, self.mapToGlobal(event.pos())
            )
