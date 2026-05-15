"""Comprehensive tests for core/auto_launch.py."""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.auto_launch import (
    _get_launch_command,
    set_auto_launch,
    get_auto_launch,
)


class TestGetLaunchCommand:
    def test_returns_string(self):
        cmd = _get_launch_command()
        assert isinstance(cmd, str)
        assert len(cmd) > 0

    def test_contains_path(self):
        cmd = _get_launch_command()
        # Should reference either run.sh/run.bat or main.py
        assert "run" in cmd.lower() or "main.py" in cmd.lower()


class TestAutoLaunchMacOS:
    @pytest.fixture(autouse=True)
    def _force_macos(self):
        with patch.object(sys, "platform", "darwin"):
            yield

    def test_set_auto_launch_enable(self, tmp_path):
        plist_path = tmp_path / "test.plist"
        with patch("core.auto_launch._macos_plist_path", return_value=plist_path):
            set_auto_launch(True)
            assert plist_path.exists()
            content = plist_path.read_text()
            assert "RunAtLoad" in content
            assert "com.pearl.post-suite" in content

    def test_set_auto_launch_disable(self, tmp_path):
        plist_path = tmp_path / "test.plist"
        plist_path.write_text("<plist>test</plist>")
        with patch("core.auto_launch._macos_plist_path", return_value=plist_path):
            set_auto_launch(False)
            assert not plist_path.exists()

    def test_disable_nonexistent_plist(self, tmp_path):
        plist_path = tmp_path / "nonexistent.plist"
        with patch("core.auto_launch._macos_plist_path", return_value=plist_path):
            set_auto_launch(False)  # Should not crash

    def test_get_auto_launch_true(self, tmp_path):
        plist_path = tmp_path / "test.plist"
        plist_path.write_text("<plist/>")
        with patch("core.auto_launch._macos_plist_path", return_value=plist_path):
            assert get_auto_launch() is True

    def test_get_auto_launch_false(self, tmp_path):
        plist_path = tmp_path / "nonexistent.plist"
        with patch("core.auto_launch._macos_plist_path", return_value=plist_path):
            assert get_auto_launch() is False


class TestAutoLaunchLinux:
    @pytest.fixture(autouse=True)
    def _force_linux(self):
        with patch.object(sys, "platform", "linux"):
            yield

    def test_set_auto_launch_enable(self, tmp_path):
        desktop_path = tmp_path / "test.desktop"
        with patch("core.auto_launch._linux_desktop_path", return_value=desktop_path):
            set_auto_launch(True)
            assert desktop_path.exists()
            content = desktop_path.read_text()
            assert "[Desktop Entry]" in content
            assert "Pearl Post Suite" in content

    def test_set_auto_launch_disable(self, tmp_path):
        desktop_path = tmp_path / "test.desktop"
        desktop_path.write_text("[Desktop Entry]")
        with patch("core.auto_launch._linux_desktop_path", return_value=desktop_path):
            set_auto_launch(False)
            assert not desktop_path.exists()

    def test_get_auto_launch_true(self, tmp_path):
        desktop_path = tmp_path / "test.desktop"
        desktop_path.write_text("[Desktop Entry]")
        with patch("core.auto_launch._linux_desktop_path", return_value=desktop_path):
            assert get_auto_launch() is True

    def test_get_auto_launch_false(self, tmp_path):
        desktop_path = tmp_path / "nonexistent.desktop"
        with patch("core.auto_launch._linux_desktop_path", return_value=desktop_path):
            assert get_auto_launch() is False
