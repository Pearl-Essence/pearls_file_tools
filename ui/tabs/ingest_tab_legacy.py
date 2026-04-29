"""Ingest Tab for Pearl's File Tools.

Two sub-modes (inner QTabWidget):
  1. Ingest — copy camera-card/folder files to a destination with MD5 verification
  2. Proxy Match — pair full-res and proxy files by stem, report orphans, optionally rename proxies
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QPushButton, QSplitter, QTabWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ui.tabs.base_tab import BaseTab
from ui.widgets.directory_selector import DirectorySelectorWidget


# ─────────────────────────────────────────────────────────────────────────────
# Ingest sub-tab
# ─────────────────────────────────────────────────────────────────────────────

class _IngestPane(QWidget):
    """The camera-card ingest pane (copy + MD5 verify)."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker = None
        self._pairs: List[Tuple[Path, Path]] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Source / destination selectors
        src_group = QGroupBox("Source (camera card or folder)")
        src_layout = QVBoxLayout()
        self.src_selector = DirectorySelectorWidget(label_text="Source:")
        self.src_selector.directory_changed.connect(self._on_source_changed)
        src_layout.addWidget(self.src_selector)
        src_group.setLayout(src_layout)
        layout.addWidget(src_group)

        dst_group = QGroupBox("Destination")
        dst_layout = QVBoxLayout()
        self.dst_selector = DirectorySelectorWidget(label_text="Destination:")
        dst_layout.addWidget(self.dst_selector)
        dst_group.setLayout(dst_layout)
        layout.addWidget(dst_group)

        # Analyse button
        analyse_row = QHBoxLayout()
        self.analyse_btn = QPushButton("Analyze")
        self.analyse_btn.clicked.connect(self._analyze)
        self.analyse_btn.setStyleSheet("padding: 8px 20px;")
        analyse_row.addWidget(self.analyse_btn)
        self.file_count_label = QLabel("")
        analyse_row.addWidget(self.file_count_label)
        analyse_row.addStretch()
        layout.addLayout(analyse_row)

        # Preview tree
        preview_label = QLabel("Preview — source files → proposed destination:")
        preview_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        layout.addWidget(preview_label)

        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderLabels(["Source File", "→ Destination"])
        self.preview_tree.setColumnWidth(0, 400)
        self.preview_tree.setAlternatingRowColors(True)
        layout.addWidget(self.preview_tree, stretch=1)

        # Progress
        progress_group = QGroupBox("Progress")
        pg_layout = QVBoxLayout()
        self.overall_bar = QProgressBar()
        self.overall_bar.setFormat("Overall: %v / %m files")
        pg_layout.addWidget(QLabel("Overall:"))
        pg_layout.addWidget(self.overall_bar)
        progress_group.setLayout(pg_layout)
        layout.addWidget(progress_group)

        # Log
        log_label = QLabel("Log:")
        log_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(log_label)
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumHeight(160)
        self.log_widget.setFont(QFont("Courier New", 10))
        layout.addWidget(self.log_widget)

        # Action buttons
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Ingest")
        self.start_btn.clicked.connect(self._start_ingest)
        self.start_btn.setEnabled(False)
        self.start_btn.setStyleSheet(
            "padding: 10px 24px; font-size: 14px; font-weight: bold;"
        )
        btn_row.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        btn_row.addWidget(self.cancel_btn)

        self.eject_btn = QPushButton("Eject / Done")
        self.eject_btn.setEnabled(False)
        self.eject_btn.setToolTip("Available after 100% verification")
        self.eject_btn.setStyleSheet("padding: 10px 24px;")
        self.eject_btn.clicked.connect(self._eject)
        btn_row.addWidget(self.eject_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.setLayout(layout)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_source_changed(self, directory: str):
        self.preview_tree.clear()
        self.start_btn.setEnabled(False)
        self.eject_btn.setEnabled(False)
        self.file_count_label.setText("")

    def _analyze(self):
        src = self.src_selector.get_directory()
        dst = self.dst_selector.get_directory()
        if not src or src == str(Path.home()):
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Source", "Please select a source folder.")
            return
        if not dst or dst == str(Path.home()):
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Destination", "Please select a destination folder.")
            return

        src_path = Path(src)
        dst_path = Path(dst)

        # Collect all files from source (non-recursive to mirror card structure)
        files = sorted(f for f in src_path.rglob("*") if f.is_file())
        self.preview_tree.clear()
        self._pairs = []

        for f in files:
            rel = f.relative_to(src_path)
            dest = dst_path / rel
            item = QTreeWidgetItem([str(rel), str(dest)])
            item.setToolTip(0, str(f))
            item.setToolTip(1, str(dest))
            self.preview_tree.addTopLevelItem(item)
            self._pairs.append((f, dest))

        n = len(files)
        self.file_count_label.setText(f"{n} file(s) found")
        self.start_btn.setEnabled(n > 0)
        self._log_clear()

    def _start_ingest(self):
        if not self._pairs:
            return

        from workers.ingest_worker import IngestWorker

        self.start_btn.setEnabled(False)
        self.analyse_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.eject_btn.setEnabled(False)
        self.overall_bar.setMaximum(len(self._pairs))
        self.overall_bar.setValue(0)
        self._log_clear()

        self._worker = IngestWorker(self._pairs)
        self._worker.file_status.connect(self._on_file_status)
        self._worker.overall_progress.connect(self._on_overall_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    def _eject(self):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "Ingest Complete",
            "All files have been verified. You may safely eject the source card."
        )

    def _on_file_status(self, filename: str, verified: bool, message: str):
        color = "#00cc00" if verified else "#cc3333"
        self.log_widget.append(
            f'<span style="color:{color};">{message}</span>'
        )

    def _on_overall_progress(self, current: int, total: int):
        self.overall_bar.setMaximum(total)
        self.overall_bar.setValue(current)

    def _on_finished(self, success: bool, summary: str, results: list):
        self.cancel_btn.setEnabled(False)
        self.start_btn.setEnabled(True)
        self.analyse_btn.setEnabled(True)

        color = "#00cc00" if success else "#cc3333"
        self.log_widget.append(
            f'<br><b><span style="color:{color};">{summary}</span></b>'
        )

        all_verified = success and all(r.verified for r in results)
        self.eject_btn.setEnabled(all_verified)

        # Colour preview rows to reflect verified status
        result_map = {str(r.src): r.verified for r in results}
        for i in range(self.preview_tree.topLevelItemCount()):
            item = self.preview_tree.topLevelItem(i)
            src_str = item.toolTip(0)
            ok = result_map.get(src_str, None)
            if ok is True:
                item.setForeground(0, QBrush(QColor(0, 180, 0)))
            elif ok is False:
                item.setForeground(0, QBrush(QColor(200, 50, 50)))

    def _log_clear(self):
        self.log_widget.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Proxy Match sub-tab
# ─────────────────────────────────────────────────────────────────────────────

class _ProxyMatchPane(QWidget):
    """Pair full-resolution files with proxy files by stem name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_res_files: Dict[str, Path] = {}   # stem → path
        self._proxy_files: Dict[str, Path] = {}       # stem → path
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Folder selectors
        folders_group = QGroupBox("Folders")
        fl = QVBoxLayout()
        self.fullres_selector = DirectorySelectorWidget(label_text="Full-Res:")
        fl.addWidget(self.fullres_selector)
        self.proxy_selector = DirectorySelectorWidget(label_text="Proxy:   ")
        fl.addWidget(self.proxy_selector)
        folders_group.setLayout(fl)
        layout.addWidget(folders_group)

        # Match button
        btn_row = QHBoxLayout()
        self.match_btn = QPushButton("Match Files")
        self.match_btn.clicked.connect(self._run_match)
        self.match_btn.setStyleSheet("padding: 8px 20px;")
        btn_row.addWidget(self.match_btn)
        self.summary_label = QLabel("")
        btn_row.addWidget(self.summary_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Results tree
        results_label = QLabel("Results:")
        results_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        layout.addWidget(results_label)

        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Stem / File", "Full-Res Path", "Proxy Path"])
        self.results_tree.setColumnWidth(0, 260)
        self.results_tree.setColumnWidth(1, 320)
        self.results_tree.setAlternatingRowColors(True)
        layout.addWidget(self.results_tree, stretch=1)

        # Rename proxies option
        rename_row = QHBoxLayout()
        self.rename_proxies_btn = QPushButton("Rename Proxies to Match Full-Res")
        self.rename_proxies_btn.clicked.connect(self._rename_proxies)
        self.rename_proxies_btn.setEnabled(False)
        self.rename_proxies_btn.setToolTip(
            "Renames each proxy file to match its paired full-res filename, "
            "preserving the proxy extension."
        )
        rename_row.addWidget(self.rename_proxies_btn)
        rename_row.addStretch()
        layout.addLayout(rename_row)

        self.setLayout(layout)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _collect_by_stem(self, directory: str) -> Dict[str, Path]:
        p = Path(directory)
        result: Dict[str, Path] = {}
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if f.is_file():
                    result[f.stem.lower()] = f
        return result

    def _run_match(self):
        fullres_dir = self.fullres_selector.get_directory()
        proxy_dir = self.proxy_selector.get_directory()

        if fullres_dir == str(Path.home()) or proxy_dir == str(Path.home()):
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Select Folders", "Please select both folders first.")
            return

        self._full_res_files = self._collect_by_stem(fullres_dir)
        self._proxy_files = self._collect_by_stem(proxy_dir)

        self.results_tree.clear()

        matched_stems = set(self._full_res_files) & set(self._proxy_files)
        fullres_only = set(self._full_res_files) - set(self._proxy_files)
        proxy_only = set(self._proxy_files) - set(self._full_res_files)

        GREEN = QColor(0, 160, 0)
        ORANGE = QColor(200, 120, 0)
        RED = QColor(180, 40, 40)

        def _add_section(title: str, stems, color: QColor,
                         fr_files: Dict[str, Path], px_files: Dict[str, Path]):
            section = QTreeWidgetItem([title, "", ""])
            section.setFont(0, QFont("", -1, QFont.Bold))
            section.setForeground(0, QBrush(color))
            for stem in sorted(stems):
                fr = str(fr_files.get(stem, ""))
                px = str(px_files.get(stem, ""))
                child = QTreeWidgetItem([stem, fr, px])
                child.setToolTip(1, fr)
                child.setToolTip(2, px)
                section.addChild(child)
            self.results_tree.addTopLevelItem(section)
            section.setExpanded(True)

        _add_section(
            f"Matched pairs ({len(matched_stems)})", matched_stems,
            GREEN, self._full_res_files, self._proxy_files
        )
        _add_section(
            f"Full-res with no proxy ({len(fullres_only)})", fullres_only,
            ORANGE, self._full_res_files, {}
        )
        _add_section(
            f"Proxies with no full-res ({len(proxy_only)})", proxy_only,
            RED, {}, self._proxy_files
        )

        self.summary_label.setText(
            f"{len(matched_stems)} matched, "
            f"{len(fullres_only)} full-res orphans, "
            f"{len(proxy_only)} proxy orphans"
        )
        self.rename_proxies_btn.setEnabled(bool(matched_stems))

    def _rename_proxies(self):
        """Rename proxy files so their stem matches the full-res counterpart."""
        from PyQt5.QtWidgets import QMessageBox

        matched_stems = set(self._full_res_files) & set(self._proxy_files)
        if not matched_stems:
            return

        # Build rename plan
        plan: List[Tuple[Path, Path]] = []
        for stem in matched_stems:
            fr_path = self._full_res_files[stem]
            px_path = self._proxy_files[stem]
            new_name = fr_path.stem + px_path.suffix
            new_path = px_path.parent / new_name
            if new_path != px_path:
                plan.append((px_path, new_path))

        if not plan:
            QMessageBox.information(self, "No Renames Needed",
                                    "All proxy filenames already match their full-res counterparts.")
            return

        msg = "\n".join(f"{src.name}  →  {dst.name}" for src, dst in plan[:20])
        if len(plan) > 20:
            msg += f"\n… and {len(plan) - 20} more"

        reply = QMessageBox.question(
            self, "Confirm Proxy Rename",
            f"Rename {len(plan)} proxy file(s)?\n\n{msg}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        errors = []
        for src, dst in plan:
            try:
                src.rename(dst)
            except Exception as exc:
                errors.append(f"{src.name}: {exc}")

        if errors:
            QMessageBox.warning(
                self, "Some Renames Failed",
                "The following renames failed:\n\n" + "\n".join(errors)
            )
        else:
            QMessageBox.information(
                self, "Done",
                f"Renamed {len(plan)} proxy file(s) successfully."
            )

        # Refresh the match display
        self._run_match()


# ─────────────────────────────────────────────────────────────────────────────
# IngestTab (outer tab)
# ─────────────────────────────────────────────────────────────────────────────

class IngestTab(BaseTab):
    """Ingest & Proxy workflow tab."""

    def get_tab_name(self) -> str:
        return "Ingest"

    def setup_ui(self):
        layout = QVBoxLayout()

        self._inner_tabs = QTabWidget()

        self._ingest_pane = _IngestPane(self.config)
        self._inner_tabs.addTab(self._ingest_pane, "Ingest")

        self._proxy_pane = _ProxyMatchPane()
        self._inner_tabs.addTab(self._proxy_pane, "Proxy Match")

        layout.addWidget(self._inner_tabs)
        self.setLayout(layout)

    def load_settings(self):
        last_src = self.config.get_tab_setting('ingest', 'last_source', '')
        last_dst = self.config.get_tab_setting('ingest', 'last_dest', '')
        if last_src:
            self._ingest_pane.src_selector.set_directory(last_src)
        if last_dst:
            self._ingest_pane.dst_selector.set_directory(last_dst)

    def save_settings(self):
        src = self._ingest_pane.src_selector.get_directory()
        dst = self._ingest_pane.dst_selector.get_directory()
        self.config.set_tab_setting('ingest', 'last_source', src)
        self.config.set_tab_setting('ingest', 'last_dest', dst)
