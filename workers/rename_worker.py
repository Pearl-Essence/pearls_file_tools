"""Rename worker thread for Pearl's File Tools."""

import csv
import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from PySide6.QtCore import Signal
from workers.base_worker import BaseWorker
from core.name_transform import generate_new_filename, move_prefix_to_suffix, move_suffix_to_prefix
from core.file_utils import (
    resolve_name_conflict, safe_rename, same_inode,
    split_compound_suffix, is_hidden_file,
)
from core.pattern_matching import match_prefix, match_suffix
from models.operation_record import OperationRecord
from constants import OP_TYPE_RENAME, SIDECAR_EXTENSIONS, CAPTION_EXTENSIONS


class RenameWorker(BaseWorker):
    """Worker thread for renaming files."""

    finished = Signal(bool, str, object)  # success, message, operation_record

    def emit_finished(self, success: bool, message: str, record=None):
        self.finished.emit(success, message, record)

    def __init__(
        self,
        files: List[Path],
        prefix: str = "",
        suffix: str = "",
        rename_to: str = "",
        case_transform: str = "none",
        prefix_to_suffix: Optional[List[str]] = None,
        suffix_to_prefix: Optional[List[str]] = None,
        direct_renames: Optional[List[Tuple[Path, str]]] = None,
        rename_sidecars: bool = True,
        rename_captions: bool = True,
        write_manifest: bool = True,
        include_hidden: bool = False,
    ):
        """
        Args:
            files: Files to rename (ignored when direct_renames is provided).
            prefix/suffix/rename_to/case_transform: Standard transform options.
            prefix_to_suffix: Tokens to move from the beginning to the end.
                Combines with the standard transforms (prefix/suffix/case)
                so the user can do "strip DRAFT_" *and* "add HERO_" in one
                Apply Rename click — historically these were two separate
                button presses.
            suffix_to_prefix: Tokens to move from the end to the beginning.
                Same combination semantics as ``prefix_to_suffix``.
            direct_renames: Pre-computed [(Path, new_name)] pairs — bypasses all
                            transform logic (used by sequential numbering mode).
            rename_sidecars: Also rename same-stem sidecar files.
            rename_captions: Also rename same-stem caption/subtitle files.
            write_manifest: Write a CSV log of the batch to the target directory.
            include_hidden: When False (default), files whose name starts with
                ``.`` are silently dropped from the batch. Hidden files are
                almost always config/OS files (``.DS_Store``, ``.gitignore``)
                that the user does not intend to rename.
        """
        super().__init__()
        self.files = files
        self.prefix = prefix
        self.suffix = suffix
        self.rename_to = rename_to
        self.case_transform = case_transform
        self.prefix_to_suffix = prefix_to_suffix
        self.suffix_to_prefix = suffix_to_prefix
        self.direct_renames = direct_renames
        self.rename_sidecars = rename_sidecars
        self.rename_captions = rename_captions
        self.write_manifest = write_manifest
        self.include_hidden = include_hidden

    # ── helpers ──────────────────────────────────────────────────────────────

    def _companion_extensions(self) -> set:
        exts = set()
        if self.rename_sidecars:
            exts |= SIDECAR_EXTENSIONS
        if self.rename_captions:
            exts |= CAPTION_EXTENSIONS
        return exts

    def _find_companions(self, filepath: Path, new_stem: str) -> List[Tuple[Path, Path]]:
        """Return (old_companion, new_companion) pairs for same-stem sidecars/captions.

        Honours compound suffixes (``.en.srt``, ``.es.vtt``, ``.tar.gz``) so
        multi-language captions and similar siblings stay paired with the
        primary on rename. The sibling must (a) share the primary's "true
        stem" once the compound suffix is stripped and (b) end in a registered
        sidecar/caption tail.
        """
        companions: List[Tuple[Path, Path]] = []
        primary_stem, _ = split_compound_suffix(filepath.name)
        parent = filepath.parent
        valid_tails = self._companion_extensions()  # e.g. {'.srt', '.vtt', '.xmp', ...}

        try:
            siblings = list(parent.iterdir())
        except OSError:
            return companions

        for sibling in siblings:
            try:
                if not sibling.is_file() or sibling == filepath:
                    continue
            except OSError:
                continue
            sib_stem, sib_suffix = split_compound_suffix(sibling.name)
            if sib_stem != primary_stem or not sib_suffix:
                continue
            # Final dot-segment must be a registered sidecar/caption extension
            final_tail = '.' + sib_suffix.rsplit('.', 1)[-1]
            if final_tail.lower() not in valid_tails:
                continue
            companions.append((sibling, parent / f"{new_stem}{sib_suffix}"))
        return companions

    def _write_manifest(self, log_rows: List[Tuple[str, str]], target_dir: Path):
        """Write a CSV rename log to target_dir."""
        try:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = target_dir / f"_pearls_rename_log_{ts}.csv"
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['old_name', 'new_name', 'timestamp'])
                writer.writerows(log_rows)
        except Exception as e:
            self.emit_progress(f"Warning: could not write rename log — {e}")

    # ── main run ─────────────────────────────────────────────────────────────

    def run(self):
        """Execute the rename operation."""
        success_count = 0
        error_count = 0
        errors = []
        rename_operations = []   # (new_path, old_path) for OperationRecord / undo
        manifest_rows = []       # (old_name, new_name, timestamp) for CSV

        # Build the work list: [(Path, new_name_str), ...]
        if self.direct_renames is not None:
            work = list(self.direct_renames)
        else:
            work = self._build_work_list()

        total = len(work)

        for idx, (filepath, new_name) in enumerate(work):
            if self.is_cancelled:
                self.emit_finished(False, "Operation cancelled by user", None)
                return

            try:
                if new_name == filepath.name:
                    continue

                new_path = filepath.parent / new_name

                # On case-insensitive filesystems (APFS / NTFS), Path.exists()
                # for a target that differs from the source only by case will
                # return True (the OS resolves it to the source itself). Don't
                # treat that as a conflict — same_inode confirms it's the same
                # file viewed under a different case, and safe_rename handles
                # the two-step rename.
                if (
                    new_path.exists()
                    and new_path != filepath
                    and not same_inode(new_path, filepath)
                ):
                    new_path = resolve_name_conflict(new_path)
                    if new_path is None:
                        errors.append(f"{filepath.name}: target already exists")
                        error_count += 1
                        continue

                # Rename primary file
                if not safe_rename(filepath, new_path):
                    errors.append(f"{filepath.name}: rename failed")
                    error_count += 1
                    continue

                ts_str = datetime.datetime.now().isoformat(timespec='seconds')
                rename_operations.append((new_path, filepath))
                manifest_rows.append((filepath.name, new_path.name, ts_str))
                success_count += 1
                self.emit_progress(f"Renamed: {filepath.name} → {new_path.name}")

                # Rename companion sidecar / caption files
                new_stem, _ = split_compound_suffix(new_path.name)
                for old_comp, new_comp in self._find_companions(filepath, new_stem):
                    if (
                        new_comp.exists()
                        and new_comp != old_comp
                        and not same_inode(new_comp, old_comp)
                    ):
                        new_comp = resolve_name_conflict(new_comp)
                    if new_comp and safe_rename(old_comp, new_comp):
                        rename_operations.append((new_comp, old_comp))
                        manifest_rows.append((old_comp.name, new_comp.name, ts_str))
                        self.emit_progress(f"  + companion: {old_comp.name} → {new_comp.name}")

            except Exception as e:
                errors.append(f"{filepath.name}: {e}")
                error_count += 1

            if total > 0:
                pct = int(((idx + 1) / total) * 100)
                self.emit_progress(f"Processing… {idx + 1}/{total} ({pct}%)")

        # Write manifest CSV
        if self.write_manifest and manifest_rows:
            dirs = {p.parent for p, _ in rename_operations}
            target_dir = next(iter(dirs))  # use first directory
            self._write_manifest(manifest_rows, target_dir)

        # Build OperationRecord for undo
        operation_record = None
        if rename_operations:
            operation_record = OperationRecord(
                operation_type=OP_TYPE_RENAME,
                files_affected=rename_operations,
                metadata={
                    'prefix': self.prefix,
                    'suffix': self.suffix,
                    'rename_to': self.rename_to,
                    'case_transform': self.case_transform,
                }
            )

        message = f"Successfully renamed {success_count} file(s)."
        if error_count:
            message += f"\n{error_count} error(s):\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                message += f"\n… and {len(errors) - 5} more"

        self.emit_finished(error_count == 0, message, operation_record)

    def _build_work_list(self) -> List[Tuple[Path, str]]:
        """Convert self.files into ``(Path, new_name)`` pairs.

        Order of operations within a single Apply Rename:
          1. Skip dot-files unless ``include_hidden`` is True.
          2. If ``prefix_to_suffix`` matched, move that token first.
          3. If ``suffix_to_prefix`` matched, move that token first.
          4. Apply prefix / suffix / rename_to / case_transform in that
             order on the resulting name.

        This means the user can configure "strip ``DRAFT_`` prefix + add
        ``HERO_`` prefix" as one operation rather than two button clicks.
        """
        work: List[Tuple[Path, str]] = []
        for filepath in self.files:
            # Skip hidden files unless explicitly included
            if not self.include_hidden and is_hidden_file(filepath.name):
                continue

            current_name = filepath.name

            # Transposition pass — moves a leading or trailing token across
            if self.prefix_to_suffix:
                matched = match_prefix(current_name, self.prefix_to_suffix)
                if matched:
                    current_name = move_prefix_to_suffix(current_name, matched)
            if self.suffix_to_prefix:
                matched = match_suffix(current_name, self.suffix_to_prefix)
                if matched:
                    current_name = move_suffix_to_prefix(current_name, matched)

            # Standard transform pass — runs even after a transposition so
            # users can chain "remove DRAFT_" and "add HERO_" in one click.
            new_name = generate_new_filename(
                current_name,
                prefix=self.prefix,
                suffix=self.suffix,
                rename_to=self.rename_to,
                case_transform=self.case_transform,
            )
            work.append((filepath, new_name))
        return work
