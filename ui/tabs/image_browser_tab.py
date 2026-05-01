"""Browse Stills tab — v0.14 visual refresh.

Functional behavior unchanged: same ImageScanWorker, same sequence detection,
same context menu actions. Layout uses TabHeader + PathCard + a Panel for
filters and a scrollable grid below.
"""

from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ui.tabs.base_tab import BaseTab
from ui.widgets.panel import Panel
from ui.widgets.path_card import PathCard
from ui.widgets.tab_header import TabHeader


class ImageBrowserTab(BaseTab):
    """Tab for browsing image folders and stepping through sequences."""

    def __init__(self, config, parent=None):
        self.all_images: List[Dict] = []
        self.filtered_images: List[Dict] = []
        self.folders: Dict[str, int] = {}
        super().__init__(config, parent)

    def get_tab_name(self) -> str:
        return "Browse Stills"

    # ─────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addWidget(self._build_source())
        root.addWidget(self._build_filters())
        root.addWidget(self._build_status())
        root.addWidget(self._build_grid(), stretch=1)

    def _build_header(self) -> QWidget:
        header = TabHeader(
            eyebrow="02 · ORGANIZE · BROWSE STILLS",
            title="Browse Stills",
            subtitle="Scan a folder for images and step through sequences.",
        )
        self.refresh_btn = header.add_action(
            "Refresh (ignore cache)",
            on_click=self.refresh_directory,
            enabled=False,
        )
        self.scan_btn = header.add_action(
            "Scan", on_click=self.scan_directory, primary=True,
        )
        return header

    def _build_source(self) -> QWidget:
        self.path_card = PathCard("IMAGE FOLDER")
        self.path_card.path_changed.connect(self._on_path_changed)
        return self.path_card

    def _build_filters(self) -> QWidget:
        wrap = Panel()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        eye = QLabel("FILTERS")
        eye.setObjectName("eyebrow")
        v.addWidget(eye)

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by filename…")
        self.search_box.textChanged.connect(self.apply_filters)
        row1.addWidget(self.search_box, stretch=1)

        folder_lbl = QLabel("FOLDER")
        folder_lbl.setObjectName("eyebrow")
        row1.addWidget(folder_lbl)
        self.folder_combo = QComboBox()
        self.folder_combo.addItem("All folders")
        self.folder_combo.currentTextChanged.connect(self.apply_filters)
        self.folder_combo.setMinimumWidth(180)
        row1.addWidget(self.folder_combo)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        size_lbl = QLabel("THUMBNAIL")
        size_lbl.setObjectName("eyebrow")
        row2.addWidget(size_lbl)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(100, 400)
        self.size_spin.setValue(200)
        self.size_spin.setSuffix(" px")
        self.size_spin.valueChanged.connect(self.on_thumbnail_size_changed)
        row2.addWidget(self.size_spin)

        self.recursive_check = QCheckBox("Recursive scan")
        self.recursive_check.setChecked(True)
        row2.addWidget(self.recursive_check)
        row2.addStretch()
        v.addLayout(row2)

        return wrap

    def _build_status(self) -> QWidget:
        self.status_label = QLabel("Choose a folder and scan to load images.")
        self.status_label.setObjectName("cardSub")
        return self.status_label

    def _build_grid(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("stillsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(Panel().frameShape())  # match panel border
        # Wrap the grid in a Panel so it inherits the floating-card look.
        host = Panel()
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(8, 8, 8, 8)
        host_layout.setSpacing(0)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self.grid_widget)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        host_layout.addWidget(scroll)
        return host

    # ─────────────────────────────────────────────────────────────────────
    # Behavior — same as v1
    # ─────────────────────────────────────────────────────────────────────
    def _on_path_changed(self, directory: str):
        self.set_directory(directory)
        self.all_images.clear()
        self.filtered_images.clear()
        self.folders.clear()
        self.clear_grid()
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("Ready to scan.")

    def scan_directory(self):
        if not self.current_directory:
            self.show_warning("No folder", "Choose an image folder first.")
            return
        if not Path(self.current_directory).is_dir():
            self.show_error("Invalid folder", "The selected folder does not exist.")
            return
        self._launch_scan(use_cache=True, msg="Scanning for images…")

    def refresh_directory(self):
        if not self.current_directory:
            return
        self._launch_scan(use_cache=False, msg="Refreshing (ignoring cache)…")

    def _launch_scan(self, *, use_cache: bool, msg: str):
        self.scan_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.status_label.setText(msg)

        from workers.image_scan_worker import ImageScanWorker
        self.worker_thread = ImageScanWorker(
            self.current_directory,
            recursive=self.recursive_check.isChecked(),
            use_cache=use_cache,
        )
        self.worker_thread.progress.connect(self.update_scan_status)
        self.worker_thread.finished.connect(self.on_scan_finished)
        self.worker_thread.start()

    def update_scan_status(self, message: str):
        self.status_label.setText(message)

    def on_scan_finished(self, success: bool, message: str, images: List):
        self.scan_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)

        if not success:
            self.show_error("Scan failed", message)
            self.status_label.setText("Scan failed.")
            return

        self.all_images = images or []
        if not self.all_images:
            self.show_info("No images", "No images found in the selected folder.")
            self.status_label.setText("No images found.")
            return

        self.folders = {}
        for img in self.all_images:
            self.folders[img['folder']] = self.folders.get(img['folder'], 0) + 1

        self.folder_combo.clear()
        self.folder_combo.addItem("All folders")
        for folder_name in sorted(self.folders.keys()):
            self.folder_combo.addItem(f"{folder_name} ({self.folders[folder_name]})")

        self.apply_filters()

        seq_count = sum(1 for img in self.all_images if img.get('is_sequence_rep'))
        standalone = sum(1 for img in self.all_images if not img.get('in_sequence'))
        if seq_count:
            seq_frames = sum(
                img.get('sequence_total', 0)
                for img in self.all_images if img.get('is_sequence_rep')
            )
            self.emit_status(
                f"Found {standalone} image(s) + {seq_count} sequence(s) "
                f"({seq_frames} frames)"
            )
        else:
            self.emit_status(f"Found {len(self.all_images)} image(s)")

    def apply_filters(self):
        search_text = self.search_box.text().lower()
        selected_folder = self.folder_combo.currentText()
        if selected_folder != "All folders" and " (" in selected_folder:
            selected_folder = selected_folder.split(" (")[0]

        self.filtered_images = []
        for img in self.all_images:
            if img.get('in_sequence') and not img.get('is_sequence_rep'):
                continue
            if selected_folder != "All folders" and img['folder'] != selected_folder:
                continue
            if search_text:
                label = img.get('sequence_label', img['name']).lower()
                if search_text not in label and search_text not in img['name'].lower():
                    continue
            self.filtered_images.append(img)
        self.display_images()

    def display_images(self):
        self.clear_grid()
        if not self.filtered_images:
            self.status_label.setText("No images match the current filters.")
            return
        self.status_label.setText(f"Showing {len(self.filtered_images)} image(s).")

        from ui.widgets.image_card import ImageCard
        columns = 5
        thumbnail_size = self.size_spin.value()
        for i, img_data in enumerate(self.filtered_images):
            row, col = divmod(i, columns)
            card = ImageCard(img_data, thumbnail_size=thumbnail_size)
            card.clicked.connect(self.open_image_viewer)
            card.context_menu_requested.connect(self.show_image_context_menu)
            self.grid_layout.addWidget(card, row, col)

    def clear_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def on_thumbnail_size_changed(self, value: int):
        self.config.set_tab_setting('image_browser', 'thumbnail_size', value)
        if self.filtered_images:
            self.display_images()

    def open_image_viewer(self, img_data: Dict):
        from ui.dialogs.image_viewer_dialog import ImageViewerDialog
        if img_data.get('is_sequence_rep') and img_data.get('sequence_files'):
            folder = img_data.get('folder', '')
            frame_images = [
                {'name': Path(p).name, 'path': p, 'folder': folder, 'size': 0}
                for p in img_data['sequence_files']
            ]
            dialog = ImageViewerDialog(frame_images, 0, self)
            dialog.setWindowTitle(
                f"Sequence Viewer — {img_data.get('sequence_label', img_data['name'])}"
            )
        else:
            folder_images = [
                img for img in self.filtered_images
                if img['folder'] == img_data['folder']
            ]
            current_index = folder_images.index(img_data) if img_data in folder_images else 0
            dialog = ImageViewerDialog(folder_images, current_index, self)
        dialog.exec()

    # ── sequence reclassification ────────────────────────────────────────
    def show_image_context_menu(self, img_data: Dict, global_pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        if img_data.get('is_sequence_rep'):
            action = menu.addAction("Break Sequence")
            action.triggered.connect(lambda: self.break_sequence(img_data))
        else:
            action = menu.addAction("Force Detect as Sequence")
            action.triggered.connect(lambda: self.force_as_sequence(img_data))
        menu.exec(global_pos)

    def break_sequence(self, rep_data: Dict):
        seq_paths = set(rep_data.get('sequence_files', []))
        for img in self.all_images:
            if img['path'] in seq_paths or img is rep_data:
                for k in ('in_sequence', 'is_sequence_rep', 'sequence_key',
                          'sequence_label', 'sequence_total', 'sequence_files'):
                    img.pop(k, None)
        self.apply_filters()

    def force_as_sequence(self, img_data: Dict):
        from core.pattern_matching import detect_image_sequences
        folder = img_data['folder']
        folder_imgs = [img for img in self.all_images if img['folder'] == folder]
        for img in folder_imgs:
            for k in ('in_sequence', 'is_sequence_rep', 'sequence_key',
                      'sequence_label', 'sequence_total', 'sequence_files'):
                img.pop(k, None)

        filenames = [img['name'] for img in folder_imgs]
        sequences = detect_image_sequences(filenames, min_frames=2)
        if not sequences:
            self.show_info(
                "No sequence detected",
                f"No sequence pattern found for images in '{folder}'.\n"
                "Sequences require at least 2 files with a numeric frame number "
                "separated by _ . or - from the base name.",
            )
            self.apply_filters()
            return

        clicked_in_seq = False
        fname_to_key = {
            fname: key
            for key, seq in sequences.items()
            for fname in seq.files
        }
        for img in folder_imgs:
            fname = img['name']
            if fname not in fname_to_key:
                continue
            clicked_in_seq = clicked_in_seq or (img is img_data)
            seq_key = fname_to_key[fname]
            seq = sequences[seq_key]
            img['in_sequence'] = True
            img['sequence_key'] = seq_key
            if fname == seq.files[0]:
                parent = Path(img['path']).parent
                img['is_sequence_rep'] = True
                img['sequence_label'] = seq.label
                img['sequence_total'] = len(seq.files)
                img['sequence_files'] = [str(parent / f) for f in seq.files]

        if not clicked_in_seq:
            self.show_info(
                "No sequence detected",
                f"'{img_data['name']}' does not match any sequence pattern.\n"
                "Other sequences in the folder may have been detected.",
            )
        self.apply_filters()

    # ─────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────
    def load_settings(self):
        last_dir = self.config.get_tab_directory('image_browser')
        if last_dir:
            self.path_card.set_path(last_dir)
            self.set_directory(last_dir)
        thumbnail_size = self.config.get_tab_setting('image_browser', 'thumbnail_size', 200)
        self.size_spin.setValue(thumbnail_size)
        recursive = self.config.get_tab_setting('image_browser', 'recursive', True)
        self.recursive_check.setChecked(recursive)

    def save_settings(self):
        self.config.set_tab_setting('image_browser', 'thumbnail_size', self.size_spin.value())
        self.config.set_tab_setting('image_browser', 'recursive', self.recursive_check.isChecked())
