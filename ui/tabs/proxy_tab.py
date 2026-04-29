"""Proxy Generation tab — pair full-resolution and proxy files by stem.

Lifted out of the legacy IngestTab._ProxyMatchPane and adapted to the v0.11
visual language (eyebrow/h1/h2 header, PathCard for each folder, Panel
around the results tree, primary CTA in the header bar).
"""

from pathlib import Path
from typing import Dict, List, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from branding import Palette
from ui.tabs.base_tab import BaseTab
from ui.widgets.panel import Panel
from ui.widgets.path_card import PathCard


class _ProxyPane(QWidget):
    """The Proxy Generation screen."""

    def __init__(self, config, status_emit, parent=None):
        super().__init__(parent)
        self.config = config
        self._emit_status = status_emit
        self._full_res_files: Dict[str, Path] = {}
        self._proxy_files: Dict[str, Path] = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        root.addLayout(self._build_header())
        root.addLayout(self._build_path_row())
        root.addWidget(self._build_results(), stretch=1)
        root.addLayout(self._build_actions_row())

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(2)
        eye = QLabel("01 · INGEST · PROXY GENERATION")
        eye.setObjectName("eyebrow")
        title = QLabel("Proxy Generation")
        title.setObjectName("h1")
        sub = QLabel("Pair full-resolution clips with their proxy counterparts and align filenames.")
        sub.setObjectName("h2")
        col.addWidget(eye)
        col.addWidget(title)
        col.addWidget(sub)
        row.addLayout(col, stretch=1)

        self.btn_match = QPushButton("Match files")
        self.btn_match.setProperty("role", "primary")
        self.btn_match.setMinimumHeight(34)
        self.btn_match.clicked.connect(self._run_match)
        row.addWidget(self.btn_match, alignment=Qt.AlignVCenter)
        return row

    def _build_path_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        self.card_full = PathCard("FULL-RESOLUTION")
        self.card_proxy = PathCard("PROXY")
        row.addWidget(self.card_full, stretch=1)
        row.addWidget(self.card_proxy, stretch=1)
        return row

    def _build_results(self) -> QWidget:
        wrap = Panel()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        head = QHBoxLayout()
        h_eye = QLabel("RESULTS")
        h_eye.setObjectName("eyebrow")
        self.lbl_summary = QLabel("Run a match to see results.")
        self.lbl_summary.setObjectName("cardSub")
        head.addWidget(h_eye)
        head.addStretch()
        head.addWidget(self.lbl_summary)
        v.addLayout(head)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Stem / file", "Full-res path", "Proxy path"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 320)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(16)
        v.addWidget(self.tree, stretch=1)
        return wrap

    def _build_actions_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.btn_rename = QPushButton("Rename proxies to match full-resolution")
        self.btn_rename.setEnabled(False)
        self.btn_rename.setToolTip(
            "Renames each proxy file to match its paired full-res filename, "
            "preserving the proxy extension."
        )
        self.btn_rename.clicked.connect(self._rename_proxies)
        row.addWidget(self.btn_rename)
        row.addStretch()
        return row

    # ── helpers ───────────────────────────────────────────────────────────
    def _collect_by_stem(self, directory: Path) -> Dict[str, Path]:
        result: Dict[str, Path] = {}
        if directory and directory.is_dir():
            for f in sorted(directory.iterdir()):
                if f.is_file():
                    result[f.stem.lower()] = f
        return result

    def _run_match(self):
        full_dir = self.card_full.get_path()
        proxy_dir = self.card_proxy.get_path()
        if not full_dir or not proxy_dir:
            QMessageBox.warning(self, "Choose folders", "Select both folders first.")
            return

        self._full_res_files = self._collect_by_stem(full_dir)
        self._proxy_files = self._collect_by_stem(proxy_dir)
        self.tree.clear()

        matched = set(self._full_res_files) & set(self._proxy_files)
        full_only = set(self._full_res_files) - set(self._proxy_files)
        proxy_only = set(self._proxy_files) - set(self._full_res_files)

        OK     = QColor(Palette.OK)
        WARN   = QColor(Palette.WARN)
        ERROR  = QColor(Palette.ERROR)

        def add_section(title: str, stems, color: QColor,
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
            self.tree.addTopLevelItem(section)
            section.setExpanded(True)

        add_section(f"Matched pairs ({len(matched)})", matched, OK,
                    self._full_res_files, self._proxy_files)
        add_section(f"Full-res with no proxy ({len(full_only)})", full_only, WARN,
                    self._full_res_files, {})
        add_section(f"Proxies with no full-res ({len(proxy_only)})", proxy_only, ERROR,
                    {}, self._proxy_files)

        self.lbl_summary.setText(
            f"{len(matched)} matched · {len(full_only)} full-res orphans "
            f"· {len(proxy_only)} proxy orphans"
        )
        self.btn_rename.setEnabled(bool(matched))
        self._emit_status(f"Proxy match: {len(matched)} pairs found")

    def _rename_proxies(self):
        matched = set(self._full_res_files) & set(self._proxy_files)
        if not matched:
            return

        plan: List[Tuple[Path, Path]] = []
        for stem in matched:
            fr = self._full_res_files[stem]
            px = self._proxy_files[stem]
            new_name = fr.stem + px.suffix
            new_path = px.parent / new_name
            if new_path != px:
                plan.append((px, new_path))

        if not plan:
            QMessageBox.information(self, "No renames needed",
                                    "All proxy filenames already match their full-res counterparts.")
            return

        preview = "\n".join(f"{src.name}  →  {dst.name}" for src, dst in plan[:20])
        if len(plan) > 20:
            preview += f"\n… and {len(plan) - 20} more"

        reply = QMessageBox.question(
            self, "Confirm proxy rename",
            f"Rename {len(plan)} proxy file(s)?\n\n{preview}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
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
            QMessageBox.warning(self, "Some renames failed",
                                "The following renames failed:\n\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Done",
                                    f"Renamed {len(plan)} proxy file(s) successfully.")
        self._run_match()


# ─────────────────────────────────────────────────────────────────────────────
# Public ProxyTab
# ─────────────────────────────────────────────────────────────────────────────

class ProxyTab(BaseTab):
    """Proxy Generation workflow."""

    def get_tab_name(self) -> str:
        return "Proxy Generation"

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._pane = _ProxyPane(self.config, self.emit_status)
        layout.addWidget(self._pane)

    def load_settings(self):
        last_full  = self.config.get_tab_setting('proxy', 'last_full', '')
        last_proxy = self.config.get_tab_setting('proxy', 'last_proxy', '')
        if last_full:
            self._pane.card_full.set_path(last_full)
        if last_proxy:
            self._pane.card_proxy.set_path(last_proxy)

    def save_settings(self):
        full  = self._pane.card_full.get_path()
        proxy = self._pane.card_proxy.get_path()
        self.config.set_tab_setting('proxy', 'last_full',  str(full)  if full  else '')
        self.config.set_tab_setting('proxy', 'last_proxy', str(proxy) if proxy else '')
