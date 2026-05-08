"""Offload (ingest) tab — Pearl Post Suite v0.20.

Single-screen tab. Source/destination cards, options row, live manifest table
with status pills, sticky footer with progress + cancel.

All five option checkboxes are functional:
  - Verify by hash (MD5)
  - Mirror to secondary destination
  - Generate MHL sidecar
  - Eject source on completion
  - Email completion report
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
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
        self._mirror_worker = None
        self._pairs: List[Tuple[Path, Path]] = []
        self._row_for_src: Dict[str, int] = {}
        self._last_results: list = []
        self._build()

    # ── construction ──────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        root.addWidget(self._build_header())
        root.addLayout(self._build_path_row())
        root.addLayout(self._build_mirror_row())
        root.addLayout(self._build_options_row())
        root.addWidget(self._build_manifest(), stretch=1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        from ui.widgets.tab_header import TabHeader
        header = TabHeader(
            eyebrow="01 · INGEST · OFFLOAD",
            title="Offload",
            subtitle="Copy and verify camera media into the destination volume.",
        )
        self.btn_preset = header.add_action(
            "Preset · NETFLIX_4K_SDR",
            enabled=False,
            tooltip="Select a delivery preset for this offload session",
        )
        self.btn_analyze = header.add_action(
            "Analyze", on_click=self._analyze,
            tooltip="Scan the source folder and populate the manifest table",
        )
        self.btn_start = header.add_action(
            "Start ingest", on_click=self._start, primary=True, enabled=False,
            tooltip="Copy all files from source to destination and verify by hash",
        )
        return header

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

    def _build_mirror_row(self) -> QHBoxLayout:
        """Mirror destination card — visible only when mirror is checked."""
        row = QHBoxLayout()
        row.setSpacing(16)
        self.card_mirror = PathCard("MIRROR DESTINATION")
        self.card_mirror.setToolTip(
            "Secondary volume that receives a parallel copy of all ingested files"
        )
        self.card_mirror.setVisible(False)
        row.addWidget(self.card_mirror, stretch=1)
        return row

    def _build_options_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(20)
        self.opt_verify = QCheckBox("Verify by hash (MD5)")
        self.opt_verify.setChecked(True)
        self.opt_verify.setToolTip(
            "Compute and compare MD5 hashes after copy to ensure data integrity"
        )
        self.opt_mirror = QCheckBox("Mirror to secondary destination")
        self.opt_mirror.setToolTip(
            "Copy files to a second destination as a backup after primary ingest"
        )
        self.opt_mirror.toggled.connect(self.card_mirror.setVisible)
        self.opt_mhl = QCheckBox("Generate MHL")
        self.opt_mhl.setChecked(True)
        self.opt_mhl.setToolTip(
            "Write an MHL (Media Hash List) sidecar for third-party verification"
        )
        self.opt_eject = QCheckBox("Eject source on completion")
        self.opt_eject.setToolTip(
            "Unmount the source volume once all files are copied and verified"
        )
        self.opt_email = QCheckBox("Email completion report")
        self.opt_email.setToolTip(
            "Send a summary email when the offload finishes.\n"
            "Configure SMTP settings in Edit → Settings → Email."
        )
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
        self.btn_cancel.setToolTip("Stop the current offload (files already copied are kept)")
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

        self._worker = IngestWorker(
            self._pairs,
            verify=self.opt_verify.isChecked(),
        )
        self._worker.file_status.connect(self._on_file_status)
        self._worker.overall_progress.connect(self._on_overall_progress)
        self._worker.finished.connect(self._on_primary_finished)
        self._worker.start()
        self._emit_status("Offload in progress…")

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        if self._mirror_worker and self._mirror_worker.isRunning():
            self._mirror_worker.cancel()

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

    def _on_primary_finished(self, success: bool, summary: str, results: list):
        self._last_results = results

        # Update manifest table
        for r in results:
            row = self._row_for_src.get(str(r.src))
            if row is not None:
                self._set_row_state(row, STATE_VERIFIED if r.verified else STATE_FAILED)

        # Mirror — run a second worker if mirror is enabled + has a path
        if self.opt_mirror.isChecked():
            mirror_dir = self.card_mirror.get_path()
            if mirror_dir:
                self._start_mirror(results, mirror_dir)
                return  # _on_mirror_finished will handle post-ingest

        self._emit_status(summary)
        self._post_ingest(results)

    def _start_mirror(self, results: list, mirror_dir: Path):
        """Run a second IngestWorker to copy files to the mirror destination."""
        from workers.ingest_worker import IngestWorker

        # Build mirror pairs from successful results
        src_root = self.card_src.get_path()
        mirror_pairs = []
        for r in results:
            if r.verified and src_root:
                try:
                    rel = r.src.relative_to(src_root)
                    mirror_pairs.append((r.src, mirror_dir / rel))
                except ValueError:
                    mirror_pairs.append((r.src, mirror_dir / r.src.name))

        if not mirror_pairs:
            self._post_ingest(results)
            return

        self._emit_status(f"Mirroring {len(mirror_pairs)} files to {mirror_dir.name}…")
        self.lbl_pct.setText("Mirroring…")

        self._mirror_worker = IngestWorker(
            mirror_pairs,
            verify=self.opt_verify.isChecked(),
        )
        self._mirror_worker.overall_progress.connect(self._on_overall_progress)
        self._mirror_worker.finished.connect(self._on_mirror_finished)
        self._mirror_worker.start()

    def _on_mirror_finished(self, success: bool, summary: str, mirror_results: list):
        self._emit_status(f"Mirror complete — {summary}")
        self._post_ingest(self._last_results)

    # ── post-ingest actions ──────────────────────────────────────────────

    def _post_ingest(self, results: list):
        """Run MHL, eject, and email after all copying is done."""
        self.btn_cancel.setEnabled(False)
        self.btn_start.setEnabled(True)
        self.btn_analyze.setEnabled(True)

        dst_dir = self.card_dst.get_path()

        # MHL sidecar
        if self.opt_mhl.isChecked() and dst_dir:
            self._generate_mhl(results, dst_dir)

        # Eject source
        if self.opt_eject.isChecked():
            self._eject_source()

        # Email report
        if self.opt_email.isChecked():
            self._send_email_report(results)

    def _generate_mhl(self, results: list, dst_dir: Path):
        """Write an MHL sidecar from ingest results."""
        try:
            from core.mhl import write_mhl_with_hashes

            entries = []
            for r in results:
                if r.verified:
                    try:
                        size = r.dst.stat().st_size
                    except OSError:
                        size = 0
                    entries.append({
                        "filename": r.dst.name,
                        "size": size,
                        "md5": getattr(r, 'md5', ''),
                    })

            if entries:
                mhl_path = write_mhl_with_hashes(entries, dst_dir)
                self._emit_status(f"MHL written → {mhl_path.name}")
        except Exception as exc:
            self._emit_status(f"MHL write failed: {exc}")

    def _eject_source(self):
        """Attempt to eject/unmount the source volume."""
        src = self.card_src.get_path()
        if not src:
            return

        if sys.platform == 'darwin':
            # Walk up to find the volume mount point
            volume = _find_volume_root(src)
            if volume and volume != Path("/"):
                try:
                    result = subprocess.run(
                        ['diskutil', 'eject', str(volume)],
                        capture_output=True, text=True, timeout=15,
                    )
                    if result.returncode == 0:
                        self._emit_status(f"Source ejected: {volume.name}")
                    else:
                        self._emit_status(
                            f"Eject failed: {result.stderr.strip() or 'unknown error'}"
                        )
                except Exception as exc:
                    self._emit_status(f"Eject failed: {exc}")
            else:
                self._emit_status("Eject skipped — source is not on a removable volume")
        elif sys.platform == 'win32':
            self._emit_status(
                "Eject on Windows requires manual action — "
                "please safely remove the drive from the system tray"
            )
        else:
            # Linux — try udisksctl
            volume = _find_volume_root(src)
            if volume and volume != Path("/"):
                try:
                    result = subprocess.run(
                        ['udisksctl', 'unmount', '-b', str(volume)],
                        capture_output=True, text=True, timeout=15,
                    )
                    if result.returncode == 0:
                        self._emit_status(f"Source unmounted: {volume.name}")
                    else:
                        self._emit_status(f"Unmount failed: {result.stderr.strip()}")
                except Exception as exc:
                    self._emit_status(f"Unmount failed: {exc}")

    def _send_email_report(self, results: list):
        """Send an email completion report using SMTP config from Settings."""
        server = self.config.get('email.smtp_server', '')
        port = self.config.get('email.smtp_port', 587)
        use_tls = self.config.get('email.use_tls', True)
        from_addr = self.config.get('email.from_address', '')
        to_addr = self.config.get('email.to_address', '')

        if not server or not from_addr or not to_addr:
            self._emit_status(
                "Email skipped — configure SMTP in Settings → Email"
            )
            return

        import os
        import smtplib
        from email.mime.text import MIMEText

        verified = sum(1 for r in results if r.verified)
        failed = sum(1 for r in results if not r.verified)

        body = (
            f"Pearl Post Suite — Offload Report\n"
            f"{'=' * 40}\n\n"
            f"Source: {self.card_src.get_path()}\n"
            f"Destination: {self.card_dst.get_path()}\n\n"
            f"Total files: {len(results)}\n"
            f"Verified: {verified}\n"
            f"Failed: {failed}\n"
        )
        if failed:
            body += f"\nFailed files:\n"
            for r in results:
                if not r.verified:
                    body += f"  • {r.src.name}: {r.error}\n"

        msg = MIMEText(body)
        msg["Subject"] = f"Pearl Offload: {verified} verified, {failed} failed"
        msg["From"] = from_addr
        msg["To"] = to_addr

        try:
            password = os.environ.get("PEARL_SMTP_PASSWORD", "")
            with smtplib.SMTP(server, port, timeout=30) as smtp:
                if use_tls:
                    smtp.starttls()
                if password:
                    smtp.login(from_addr, password)
                smtp.send_message(msg)
            self._emit_status(f"Email sent to {to_addr}")
        except Exception as exc:
            self._emit_status(f"Email failed: {exc}")


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


def _find_volume_root(path: Path) -> Optional[Path]:
    """Walk up from *path* to find the mount point / volume root.

    On macOS, volumes are under /Volumes/<name>. On Linux, mount points
    vary but we detect them by checking if the parent is on a different device.
    Returns the volume path, or None if *path* is on the root filesystem.
    """
    path = path.resolve()
    if sys.platform == 'darwin':
        # /Volumes/<VolumeName>/...  → /Volumes/<VolumeName>
        parts = path.parts
        if len(parts) >= 3 and parts[1] == "Volumes":
            return Path("/") / parts[1] / parts[2]
        return None
    else:
        # Linux heuristic: walk up until st_dev changes
        try:
            dev = path.stat().st_dev
            current = path
            while current.parent != current:
                parent = current.parent
                if parent.stat().st_dev != dev:
                    return current
                current = parent
        except OSError:
            pass
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public IngestTab
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
        last_mirror = self.config.get_tab_setting('ingest', 'last_mirror', '')
        if last_src:
            self._pane.card_src.set_path(last_src)
        if last_dst:
            self._pane.card_dst.set_path(last_dst)
        if last_mirror:
            self._pane.card_mirror.set_path(last_mirror)

    def save_settings(self):
        src = self._pane.card_src.get_path()
        dst = self._pane.card_dst.get_path()
        mirror = self._pane.card_mirror.get_path()
        self.config.set_tab_setting('ingest', 'last_source', str(src) if src else '')
        self.config.set_tab_setting('ingest', 'last_dest', str(dst) if dst else '')
        self.config.set_tab_setting('ingest', 'last_mirror', str(mirror) if mirror else '')
