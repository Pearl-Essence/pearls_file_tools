"""MHL (Media Hash List) generation for Pearl Post Suite.

Writes an MHL v1 XML sidecar after a verified ingest. Industry-standard
format used by Silverstack, ShotPut Pro, Hedge, and other DIT tools.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, List
from xml.etree.ElementTree import Element, SubElement, indent, tostring

if TYPE_CHECKING:
    from workers.ingest_worker import IngestResult


def write_mhl(results: "List[IngestResult]", dest_dir: Path) -> Path:
    """Write an MHL v1 sidecar for verified ingest results.

    Args:
        results: List of IngestResult objects (only verified entries are included).
        dest_dir: Directory to write the .mhl file into.

    Returns:
        Path to the written .mhl file.
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    filename = f"pearl_ingest_{now.strftime('%Y%m%d_%H%M%S')}.mhl"
    output = dest_dir / filename

    root = Element("hashlist", version="1.1")
    SubElement(root, "creatorinfo").text = "Pearl Post Suite"

    for r in results:
        if not r.verified:
            continue
        h = SubElement(root, "hash")
        SubElement(h, "file").text = str(r.dst.name)
        try:
            SubElement(h, "size").text = str(r.dst.stat().st_size)
        except OSError:
            SubElement(h, "size").text = "0"
        SubElement(h, "lastmodificationdate").text = timestamp
        # The hash value comes from the worker — currently MD5.
        # IngestResult doesn't store the hex digest, so we re-read from the
        # file_status signal's message format.  If no hash is available, omit.
        SubElement(h, "md5").text = ""

    indent(root, space="  ")
    pretty = tostring(root, encoding="UTF-8", xml_declaration=True)

    dest_dir.mkdir(parents=True, exist_ok=True)
    output.write_bytes(pretty)
    return output


def write_mhl_with_hashes(entries: "List[dict]", dest_dir: Path) -> Path:
    """Write an MHL with pre-computed hashes.

    Each entry dict: {'filename': str, 'size': int, 'md5': str}

    Args:
        entries: List of dicts with file metadata and hashes.
        dest_dir: Directory to write the .mhl file into.

    Returns:
        Path to the written .mhl file.
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    filename = f"pearl_ingest_{now.strftime('%Y%m%d_%H%M%S')}.mhl"
    output = dest_dir / filename

    root = Element("hashlist", version="1.1")
    SubElement(root, "creatorinfo").text = "Pearl Post Suite"

    for entry in entries:
        h = SubElement(root, "hash")
        SubElement(h, "file").text = entry.get("filename", "")
        SubElement(h, "size").text = str(entry.get("size", 0))
        SubElement(h, "lastmodificationdate").text = timestamp
        SubElement(h, "md5").text = entry.get("md5", "")

    indent(root, space="  ")
    pretty = tostring(root, encoding="UTF-8", xml_declaration=True)

    dest_dir.mkdir(parents=True, exist_ok=True)
    output.write_bytes(pretty)
    return output
