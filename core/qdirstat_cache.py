"""qDirStat / WinDirStat cache file support for Pearl's File Tools.

qDirStat cache format (.cache.gz):
  Line 1: [qdirstat 1.0 cache file]
  D <path>   — introduces a directory
  F\t<name>\t<size>\t<mtime>\t<blocks>\t<links>  — file inside current dir
"""

import gzip
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, Optional


def detect_qdirstat() -> Optional[str]:
    """Return the path to qDirStat or WinDirStat if installed, else None.

    Checks the system PATH first, then falls back to well-known macOS
    .app bundle locations (``shutil.which`` cannot find binaries inside
    /Applications/*.app/Contents/MacOS/).
    """
    for name in ("qdirstat", "windirstat", "WinDirStat"):
        path = shutil.which(name)
        if path:
            return path

    # macOS .app bundles are not on PATH — check common install locations.
    if sys.platform == "darwin":
        for app_path in (
            Path("/Applications/QDirStat.app/Contents/MacOS/qdirstat"),
            Path("/Applications/WinDirStat.app/Contents/MacOS/windirstat"),
            Path.home() / "Applications/QDirStat.app/Contents/MacOS/qdirstat",
        ):
            if app_path.is_file():
                return str(app_path)

    return None


def write_qdirstat_cache(data: Dict[str, Dict[str, int]], root_dir: Path, output_path: Path) -> None:
    """Write a storage scan result as a qDirStat .cache.gz file.

    Args:
        data: Mapping of {folder_name: {category: size_bytes}} as produced by
              _StorageWorker. The special key '__root__' maps to files directly
              inside root_dir.
        root_dir: The scanned root directory (used as the base path in the cache).
        output_path: Where to write the .cache.gz file.
    """
    lines = ["[qdirstat 1.0 cache file]\n"]
    now_epoch = int(time.time())

    for folder_name, cats in sorted(data.items()):
        if folder_name == "__root__":
            dir_path = str(root_dir)
        else:
            dir_path = str(root_dir / folder_name)
        lines.append(f"D {dir_path}\n")
        for cat, size in sorted(cats.items()):
            if size <= 0:
                continue
            blocks = (size + 511) // 512
            lines.append(f"F\t{cat}\t{size}\t0x{now_epoch:x}\t{blocks}\t1\n")

    raw = "".join(lines).encode("utf-8")
    with gzip.open(output_path, "wb") as f:
        f.write(raw)


def _build_ext_to_cat() -> Dict[str, str]:
    from constants import ALL_EXTENSION_CATEGORIES

    ext_to_cat = {}
    for cat, exts in ALL_EXTENSION_CATEGORIES.items():
        for ext in exts:
            ext_to_cat[ext.lower()] = cat
    return ext_to_cat


def _parse_dir_line(dir_path: str, root_path: Optional[str]):
    if root_path is None:
        return "__root__", dir_path
    try:
        rel = os.path.relpath(dir_path, root_path)
        return (rel if rel != "." else "__root__"), root_path
    except ValueError:
        return dir_path, root_path


def _parse_file_line(parts, current_folder, ext_to_cat, data):
    if len(parts) < 3:
        return
    fname = parts[1]
    try:
        size = int(parts[2])
    except ValueError:
        return
    ext = os.path.splitext(fname)[1].lower()
    cat = ext_to_cat.get(ext, "other")
    data.setdefault(current_folder, {})
    data[current_folder][cat] = data[current_folder].get(cat, 0) + size


def parse_qdirstat_cache(cache_path: Path) -> Dict[str, Dict[str, int]]:
    """Parse a qDirStat .cache.gz file into Pearl's storage data format.

    Returns:
        {folder_name: {category: size_bytes}} — folder_name is relative to the
        first D-line encountered, or '__root__' for files in the top directory.
    """
    with gzip.open(cache_path, "rt", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines or not lines[0].startswith("[qdirstat"):
        raise ValueError("Not a valid qDirStat cache file")

    ext_to_cat = _build_ext_to_cat()
    data: Dict[str, Dict[str, int]] = {}
    root_path: Optional[str] = None
    current_folder = "__root__"

    for line in lines[1:]:
        line = line.rstrip("\n")
        if line.startswith("D "):
            current_folder, root_path = _parse_dir_line(line[2:].strip(), root_path)
        elif line.startswith("F\t"):
            _parse_file_line(line.split("\t"), current_folder, ext_to_cat, data)

    return data
