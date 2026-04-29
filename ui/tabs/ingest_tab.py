"""Offload (ingest) tab — Pearl Post Suite v0.11.

Single-screen tab. Source/destination cards, options row, live manifest table
with status pills, sticky footer with progress + cancel.

Worker contract is unchanged: IngestWorker emits ``file_status``,
``overall_progress``, ``finished``. Proxy matching is now its own sidebar
destination — see ui/tabs/proxy_tab.py.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from branding import Palette
from ui.tabs.base_tab import BaseTab
from ui.widgets.panel import Panel
from ui.widgets.path_card import PathCard
from ui.widgets.pill import Pill, KIND_OK, KIND_WARN, KIND_ERROR, KIND_MUTED


# ── Manifest row state vocabulary ───────────────────────────────────────────
STATE_QUEUED   = "queued"
STATE_RUNNING  = "running"
STATE_VERIFIED = "verified"
STATE_FAILED   = "failed"

# (display_text, pill_kind)
PILL_FOR_STATE = {
    STATE_QUEUED:   ("QUEUED",   KIND_MUTED),
    STATE_RUNNING:  ("HASHING",  KIND_WARN),
    STATE_VERIFIED: ("VERIFIED", KIND_OK),
    STATE_FAILED:   ("MISMATCH", KIND_ERROR),
}


# ─────────────────────────────────────────────────────────────────────────────
# Offload pane
# ─────────────────────────────────────────────────────────────────────────────

class _OffloadPane(QWidget):
    """The full Offload screen."""

    def __init__(self, config, status_emit, parent=None):
        super().__init__(parent)
        self.config = config
        self._emit_status = status_emit
        self._worker = None
        self._pairs: List[Tuple[Path, Path]] = []
        self._row_for_src: Dict[str, int] = {}
        self._build()

    # ── construction ──────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        root.addLayout(self._build_header())
        root.addLayout(self._build_path_row())
        root.addLayout(self._build_options_row())
        root.addWidget(self._build_manifest(), stretch=1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        col = QVBoxLayout()
        col.setSpacing(2)
        eyebrow = QLabel("01 · INGEST · OFFLOAD")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Offload")
        title.setObjectName("h1")
        sub = QLabel("Copy and verify camera media into the destination volume.")
        sub.setObjectName("h2")
        col.addWidget(eyebrow)
        col.addWidget(title)
        col.addWidget(sub)
        row.addLayout(col, stretch=1)

        self.btn_preset = QPushButton("Preset · NETFLIX_4K_SDR")
        self.btn_preset.setObjectName("ghostBtn")
        self.btn_preset.setEnabled(False)
        self.btn_preset.setToolTip("Delivery presets — coming in Pearl v0.12")

        self.btn_analyze = QPushButton("Analyze")
        self.btn_analyze.setObjectName("ghostBtn")
        self.btn_analyze.clicked.connect(self._analyze)

        self.btn_start = QPushButton("Start ingest")
        self.btn_start.setProperty("role", "primary")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._start)

        for b in (self.btn_preset, self.btn_analyze, self.btn_start):
            b.setMinimumHeight(34)
            row.addWidget(b, alignment=Qt.AlignVCenter)
        return row

    def _build_path_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        self.card_src = PathCard("SOURCE")
        self.card_src.path_changed.connect(self._on_source_changed)

        arrow = QLabel("→")
        arrow.setObjectName("flowArrow")
        arrow.setAlignment(Qt.AlignCenter)
        arrow.setFixedWidth(48)

        self.card_dst = PathCard("DESTINATION")
        self.card_dst.path_changed.connect(lambda _p: self._refresh_start_state())

        row.addWidget(self.card_src, stretch=1)
        row.addWidget(arrow)
        row.addWidget(self.card_dst, stretch=1)
        return row

    def _build_options_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(20)
        self.opt_verify = QCheckBox("Verify by hash (xxHash3-128)")
        self.opt_verify.setChecked(True)
        self.opt_mirror = QCheckBox("Mirror to secondary destination")
        self.opt_mhl    = QCheckBox("Generate MHL")
        self.opt_mhl.setChecked(True)
        self.opt_eject  = QCheckBox("Eject source on completion")
        self.opt_email  = QCheckBox("Email completion report")
        for c in (self.opt_verify, self.opt_mirror, self.opt_mhl,
                  self.opt_eject, self.opt_email):
            row.addWidget(c)
        row.addStretch()
        return row

    def _build_manifest(self) -> QWidget:
        wrap = Panel()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        head_row = QHBoxLayout()
        h_eye = QLabel("MANIFEST")
        h_eye.setObjectName("eyebrow")
        self.lbl_summary = QLabel("0 files")
        self.lbl_summary.setObjectName("cardSub")
        head_row.addWidget(h_eye)
        head_row.addWidget(self.lbl_summary)
        head_row.addStretch()
        self.lbl_counts = QLabel("")
        self.lbl_counts.setObjectName("cardSub")
        head_row.addWidget(self.lbl_counts)
        v.addLayout(head_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "FILENAME", "SIZE", "HASH", "STATE"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 44)
        self.table.setColumnWidth(2, 92)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 120)

        v.addWidget(self.table, stretch=1)
        return wrap

    def _build_footer(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("footer")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(16)

        self.lbl_throughput = QLabel("— GB/s")
        self.lbl_throughput.setObjectName("metricBig")
        self.lbl_eta = QLabel("ETA —")
        self.lbl_eta.setObjectName("metricSub")
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(self.lbl_throughput)
        col.addWidget(self.lbl_eta)
        h.addLayout(col)

        bar_col = QVBoxLayout()
        bar_col.setSpacing(4)
        self.bar = QProgressBar()
        self.bar.setMaximum(1)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.lbl_pct = QLabel("0% · 0 / 0 files")
        self.lbl_pct.setObjectName("cardSub")
        bar_col.addWidget(self.bar)
        bar_col.addWidget(self.lbl_pct)
        h.addLayout(bar_col, stretch=1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setProperty("role", "danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        h.addWidget(self.btn_cancel)
        return wrap

    # ── slots ─────────────────────────────────────────────────────────────
    def _on_source_changed(self, _path: str):
        self._analyze(silent=True)

    def _refresh_start_state(self):
        self.btn_start.setEnabled(bool(self._pairs and self.card_dst.get_path()))

    def _analyze(self, silent: bool = False):
        src = self.card_src.get_path()
        if not src:
            if not silent:
                QMessageBox.warning(self, "No source", "Choose a source folder first.")
            return

        files = sorted(f for f in src.rglob("*") if f.is_file())
        self._pairs = []
        self.table.setRowCount(0)
        self._row_for_src.clear()

        dst_root = self.card_dst.get_path()
        total_bytes = 0
        for i, f in enumerate(files, start=1):
            rel = f.relative_to(src)
            dest = (dst_root / rel) if dst_root else (Path("<destination>") / rel)
            self._pairs.append((f, dest))
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            total_bytes += size
            self._add_manifest_row(i, f, size)

        gb = total_bytes / (1024 ** 3)
        self.lbl_summary.setText(f"{len(files)} files · {gb:.1f} GB")
        self.card_src.set_metrics(f"{len(files)} files · {gb:.1f} GB")
        self._update_counts()
        self._refresh_start_state()
        self._emit_status(f"Analyzed source: {len(files)} files, {gb:.1f} GB")

    def _add_manifest_row(self, idx: int, path: Path, size: int):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._row_for_src[str(path)] = row

        idx_item = QTableWidgetItem(str(idx))
        idx_item.setTextAlignment(Qt.AlignCenter)
        idx_item.setForeground(QBrush(QColor(Palette.TEXT_MUTED)))
        self.table.setItem(row, 0, idx_item)

        self.table.setItem(row, 1, QTableWidgetItem(path.name))

        size_item = QTableWidgetItem(_human_bytes(size))
        size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        size_item.setForeground(QBrush(QColor(Palette.TEXT_SECONDARY)))
        self.table.setItem(row, 2, size_item)

        hash_item = QTableWidgetItem("—")
        hash_item.setForeground(QBrush(QColor(Palette.TEXT_MUTED)))
        hash_item.setFont(QFont("JetBrains Mono", 10))
        self.table.setItem(row, 3, hash_item)

        text, kind = PILL_FOR_STATE[STATE_QUEUED]
        pill = Pill(text, kind)
        self.table.setCellWidget(row, 4, _wrap_pill(pill))

    def _update_counts(self):
        counts = {STATE_QUEUED: 0, STATE_RUNNING: 0, STATE_VERIFIED: 0, STATE_FAILED: 0}
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 4)
            if not w:
                continue
            pill = w.findChild(Pill)
            if not pill:
                continue
            kind = pill.property("pill")
            for state, (_t, k) in PILL_FOR_STATE.items():
                if k == kind:
                    counts[state] += 1
                    break
        bits = []
        if counts[STATE_VERIFIED]: bits.append(f"{counts[STATE_VERIFIED]} verified")
        if counts[STATE_RUNNING]:  bits.append(f"{counts[STATE_RUNNING]} hashing")
        if counts[STATE_FAILED]:   bits.append(f"{counts[STATE_FAILED]} mismatch")
        if counts[STATE_QUEUED]:   bits.append(f"{counts[STATE_QUEUED]} queued")
        self.lbl_counts.setText(" · ".join(bits))

    def _set_row_state(self, row: int, state: str, hash_str: Optional[str] = None):
        w = self.table.cellWidget(row, 4)
        if w:
            pill = w.findChild(Pill)
            if pill:
                text, kind = PILL_FOR_STATE[state]
                pill.set_state(text, kind)
        if hash_str is not None:
            item = self.table.item(row, 3)
            if item:
                item.setText(hash_str)
                item.setForeground(QBrush(QColor(Palette.TEXT_SECONDARY)))
        self._update_counts()

    # ── ingest lifecycle ──────────────────────────────────────────────────
    def _start(self):
        if not self._pairs:
            return
        from workers.ingest_worker import IngestWorker

        self.btn_start.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.bar.setMaximum(len(self._pairs))
        self.bar.setValue(0)
        for row in range(self.table.rowCount()):
            self._set_row_state(row, STATE_QUEUED)

        self._worker = IngestWorker(self._pairs)
        self._worker.file_status.connect(self._on_file_status)
        self._worker.overall_progress.connect(self._on_overall_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()
        self._emit_status("Offload in progress…")

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    def _on_file_status(self, filename: str, verified: bool, message: str):
        row = self._row_for_src.get(filename)
        if row is None:
            return
        hash_hint = None
        if "hash=" in message:
            try:
                hash_hint = message.split("hash=", 1)[1].split()[0][:16] + "…"
            except Exception:
                hash_hint = None
        self._set_row_state(
            row, STATE_VERIFIED if verified else STATE_FAILED, hash_hint
        )

    def _on_overall_progress(self, current: int, total: int):
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(current)
        pct = int(100 * current / total) if total else 0
        self.lbl_pct.setText(f"{pct}% · {current} / {total} files")

    def _on_finished(self, success: bool, summary: str, results: list):
        self.btn_cancel.setEnabled(False)
        self.btn_start.setEnabled(True)
        self.btn_analyze.setEnabled(True)
        self._emit_status(summary)
        for r in results:
            row = self._row_for_src.get(str(r.src))
            if row is not None:
                self._set_row_state(row, STATE_VERIFIED if r.verified else STATE_FAILED)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _human_bytes(n: int) -> str:
    if n <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:,.1f} {unit}" if unit != "B" else f"{n:,} B"
        n /= 1024
    return f"{n:,.1f} PB"


def _wrap_pill(pill: Pill) -> QWidget:
    holder = QWidget()
    h = QHBoxLayout(holder)
    h.setContentsMargins(6, 4, 6, 4)
    h.setSpacing(0)
    h.addWidget(pill, alignment=Qt.AlignCenter)
    return holder


# ─────────────────────────────────────────────────────────────────────────────
# Public IngestTab — same external API as the v2 tab
# ─────────────────────────────────────────────────────────────────────────────

class IngestTab(BaseTab):
    """Offload workflow."""

    def get_tab_name(self) -> str:
        return "Offload"

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._pane = _OffloadPane(self.config, self.emit_status)
        layout.addWidget(self._pane)

    def load_settings(self):
        last_src = self.config.get_tab_setting('ingest', 'last_source', '')
        last_dst = self.config.get_tab_setting('ingest', 'last_dest', '')
        if last_src:
            self._pane.card_src.set_path(last_src)
        if last_dst:
            self._pane.card_dst.set_path(last_dst)

    def save_settings(self):
        src = self._pane.card_src.get_path()
        dst = self._pane.card_dst.get_path()
        self.config.set_tab_setting('ingest', 'last_source', str(src) if src else '')
        self.config.set_tab_setting('ingest', 'last_dest', str(dst) if dst else '')
