"""Shared fixtures for Pearl Post Suite tests."""

import os
import sys
import pytest
from pathlib import Path

# Ensure the package root is on sys.path so `import constants` etc. work
# the same way they do when the app runs from pearls_file_tools/.
PKG_ROOT = Path(__file__).resolve().parent.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


@pytest.fixture
def tmp_tree(tmp_path):
    """Create a small file tree for testing.

    Returns tmp_path with:
        file_a.mov  (100 bytes)
        file_b.mov  (100 bytes)
        sub/file_c.txt (50 bytes)
        .hidden      (10 bytes)
    """
    (tmp_path / "file_a.mov").write_bytes(b"x" * 100)
    (tmp_path / "file_b.mov").write_bytes(b"y" * 100)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "file_c.txt").write_bytes(b"z" * 50)
    (tmp_path / ".hidden").write_bytes(b"h" * 10)
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_config_singleton():
    """Reset the Config singleton between tests so state doesn't leak."""
    from config import Config
    Config._instance = None
    yield
    Config._instance = None
