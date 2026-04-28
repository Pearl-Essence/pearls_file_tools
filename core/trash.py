"""Soft-delete (studio recycle bin) for Pearl's File Tools.

Files are moved to .pearls_trash/ inside the project root.
Metadata (original path, size, deletion timestamp) is stored in .meta.json
inside the trash dir so items can be restored or permanently purged.
"""

import datetime
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List

TRASH_DIR_NAME = '.pearls_trash'
_META_FILENAME = '.meta.json'


@dataclass
class TrashItem:
    trash_name: str      # filename inside .pearls_trash/
    original_path: str   # absolute path before deletion
    deleted_at: str      # ISO 8601 timestamp
    size_bytes: int


class StudioTrash:
    """Per-directory soft-delete manager backed by .pearls_trash/."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.trash_dir = root_dir / TRASH_DIR_NAME
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        self._meta_file = self.trash_dir / _META_FILENAME

    # ── metadata ──────────────────────────────────────────────────────────

    def _load(self) -> List[dict]:
        if not self._meta_file.exists():
            return []
        try:
            return json.loads(self._meta_file.read_text(encoding='utf-8'))
        except Exception:
            return []

    def _save(self, records: List[dict]):
        try:
            self._meta_file.write_text(
                json.dumps(records, indent=2, ensure_ascii=False),
                encoding='utf-8',
            )
        except Exception:
            pass

    # ── public API ────────────────────────────────────────────────────────

    def send_to_trash(self, filepath: Path) -> bool:
        """Move *filepath* into the trash dir, recording its original path."""
        try:
            size = filepath.stat().st_size if filepath.is_file() else 0
            trash_name = f"{uuid.uuid4().hex}_{filepath.name}"
            shutil.move(str(filepath), str(self.trash_dir / trash_name))
            records = self._load()
            records.append({
                'trash_name': trash_name,
                'original_path': str(filepath),
                'deleted_at': datetime.datetime.now().isoformat(),
                'size_bytes': size,
            })
            self._save(records)
            return True
        except Exception:
            return False

    def list_trash(self) -> List[TrashItem]:
        return [TrashItem(**r) for r in self._load()]

    def restore(self, item: TrashItem) -> Path:
        """Move item back to its original location.

        Returns the actual restored path (which may differ from the
        original if a new file with the same name was created in the
        meantime — in that case the restored copy gets a ``_restored``
        / ``_restored_N`` suffix so the user's current file is preserved).

        Returns ``None`` on failure.
        """
        from core.file_utils import resolve_name_conflict

        src = self.trash_dir / item.trash_name
        dst = Path(item.original_path)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)

            # If a file already exists at the original path, do NOT overwrite —
            # the user has likely created a new file there in the meantime.
            # Pick a non-colliding name and restore beside it.
            if dst.exists():
                stem = dst.stem
                suffix = dst.suffix
                candidate = dst.with_name(f"{stem}_restored{suffix}")
                if candidate.exists():
                    candidate = resolve_name_conflict(candidate)
                if candidate is None:
                    return None
                dst = candidate

            shutil.move(str(src), str(dst))
            self._save([r for r in self._load() if r['trash_name'] != item.trash_name])
            return dst
        except Exception:
            return None

    def purge(self, item: TrashItem) -> bool:
        """Permanently delete item from the trash dir."""
        src = self.trash_dir / item.trash_name
        try:
            if src.is_file():
                src.unlink()
            elif src.is_dir():
                shutil.rmtree(str(src))
            self._save([r for r in self._load() if r['trash_name'] != item.trash_name])
            return True
        except Exception:
            return False

    def auto_purge(self, days: int = 30):
        """Permanently delete items that have been in the trash longer than *days*."""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        for item in self.list_trash():
            try:
                if datetime.datetime.fromisoformat(item.deleted_at) < cutoff:
                    self.purge(item)
            except Exception:
                pass

    def total_size(self) -> int:
        return sum(item.size_bytes for item in self.list_trash())
