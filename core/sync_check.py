"""Multi-site directory sync check for Pearl's File Tools."""

import datetime
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SyncEntry:
    rel_path: str
    status: str   # 'modified_both' | 'a_newer' | 'b_newer' | 'a_only' | 'b_only'
    path_a: Optional[Path]
    path_b: Optional[Path]
    size_a: int = 0
    size_b: int = 0
    mtime_a: float = 0.0
    mtime_b: float = 0.0


@dataclass
class SyncReport:
    dir_a: Path
    dir_b: Path
    entries: List[SyncEntry]
    generated: datetime.datetime

    def by_status(self, status: str) -> List[SyncEntry]:
        return [e for e in self.entries if e.status == status]


def _md5(path: Path) -> str:
    """Return hex MD5 of the file at *path*."""
    h = hashlib.md5()
    try:
        with open(path, 'rb') as fh:
            for chunk in iter(lambda: fh.read(65536), b''):
                h.update(chunk)
    except OSError:
        return ''
    return h.hexdigest()


def _index_dir(root: Path) -> Dict[str, Path]:
    """Walk *root* and return {relative_path_str: absolute_Path} for all files.

    Skips the .pearls_trash directory.
    """
    index: Dict[str, Path] = {}
    if not root.is_dir():
        return index
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        # Skip .pearls_trash anywhere in the path
        if '.pearls_trash' in p.parts:
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        index[str(rel)] = p
    return index


def compare_directories(
    dir_a: Path,
    dir_b: Path,
    since: Optional[datetime.datetime] = None,
) -> SyncReport:
    """Compare two directory trees and return a SyncReport.

    For files in both:
        * MD5 differs          → 'modified_both'
        * MD5 same, mtime_a > mtime_b → 'a_newer'
        * MD5 same, otherwise  → 'b_newer'
    Files only in A → 'a_only'
    Files only in B → 'b_only'

    If *since* is provided, only include entries where
    ``max(mtime_a, mtime_b) > since.timestamp()``.
    """
    since_ts: Optional[float] = since.timestamp() if since is not None else None

    index_a = _index_dir(dir_a)
    index_b = _index_dir(dir_b)

    all_keys = set(index_a) | set(index_b)
    entries: List[SyncEntry] = []

    for rel in sorted(all_keys):
        in_a = rel in index_a
        in_b = rel in index_b

        path_a = index_a.get(rel)
        path_b = index_b.get(rel)

        size_a = path_a.stat().st_size if path_a else 0
        size_b = path_b.stat().st_size if path_b else 0
        mtime_a = path_a.stat().st_mtime if path_a else 0.0
        mtime_b = path_b.stat().st_mtime if path_b else 0.0

        max_mtime = max(mtime_a, mtime_b)
        if since_ts is not None and max_mtime <= since_ts:
            continue

        if in_a and in_b:
            md5_a = _md5(path_a)
            md5_b = _md5(path_b)
            if md5_a != md5_b:
                status = 'modified_both'
            elif mtime_a > mtime_b:
                status = 'a_newer'
            else:
                status = 'b_newer'
        elif in_a:
            status = 'a_only'
        else:
            status = 'b_only'

        entries.append(SyncEntry(
            rel_path=rel,
            status=status,
            path_a=path_a,
            path_b=path_b,
            size_a=size_a,
            size_b=size_b,
            mtime_a=mtime_a,
            mtime_b=mtime_b,
        ))

    return SyncReport(
        dir_a=dir_a,
        dir_b=dir_b,
        entries=entries,
        generated=datetime.datetime.now(),
    )
