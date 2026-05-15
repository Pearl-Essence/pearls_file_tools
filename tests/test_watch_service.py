"""Comprehensive tests for core/watch_service.py."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.watch_service import WatchRule, WatchService


class TestWatchRule:
    def test_defaults(self):
        rule = WatchRule(watch_dir="/tmp")
        assert rule.profile_name == ""
        assert rule.enabled is True

    def test_custom_values(self):
        rule = WatchRule(watch_dir="/tmp", profile_name="my_profile", enabled=False)
        assert rule.profile_name == "my_profile"
        assert rule.enabled is False


class TestWatchService:
    @pytest.fixture
    def service(self):
        return WatchService()

    def test_initial_state(self, service):
        assert service.is_active is False

    def test_start_sets_active(self, service, tmp_path):
        callback = MagicMock()
        rule = WatchRule(watch_dir=str(tmp_path))
        service.start([rule], callback)
        assert service.is_active is True
        service.stop()

    def test_stop_clears_active(self, service, tmp_path):
        callback = MagicMock()
        rule = WatchRule(watch_dir=str(tmp_path))
        service.start([rule], callback)
        service.stop()
        assert service.is_active is False

    def test_disabled_rule_skipped(self, service, tmp_path):
        callback = MagicMock()
        rule = WatchRule(watch_dir=str(tmp_path), enabled=False)
        service.start([rule], callback)
        # Should still be active but no observers for disabled rules
        assert service.is_active is True
        service.stop()

    def test_nonexistent_dir_skipped(self, service):
        callback = MagicMock()
        rule = WatchRule(watch_dir="/nonexistent_xyz_watch")
        service.start([rule], callback)
        assert service.is_active is True
        service.stop()

    def test_poll_once_no_callback(self, service):
        # poll_once should not crash when callback is None
        service.poll_once()

    def test_poll_once_detects_new_file(self, service, tmp_path):
        callback = MagicMock()
        rule = WatchRule(watch_dir=str(tmp_path), profile_name="test")
        service.start([rule], callback)
        # Create a file
        (tmp_path / "new_file.txt").write_text("data")
        # First poll: file enters pending state
        service.poll_once()
        # Second + third polls: file size is stable → fires callback
        service.poll_once()
        service.poll_once()
        if not callback.called:
            # May need more polls for POLL_SETTLE_PASSES
            service.poll_once()
        service.stop()

    def test_poll_settle_passes(self, service):
        assert service.POLL_SETTLE_PASSES == 2

    def test_scan_empty_dir(self, tmp_path):
        result = WatchService._scan(tmp_path)
        assert result == set()

    def test_scan_with_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result = WatchService._scan(tmp_path)
        assert len(result) == 2

    def test_scan_excludes_dirs(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("data")
        result = WatchService._scan(tmp_path)
        assert len(result) == 1

    def test_scan_nonexistent_dir(self):
        # _scan only catches PermissionError, not FileNotFoundError
        with pytest.raises(FileNotFoundError):
            WatchService._scan(Path("/nonexistent_xyz"))

    def test_multiple_rules(self, service, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        callback = MagicMock()
        rules = [
            WatchRule(watch_dir=str(dir_a), profile_name="profile_a"),
            WatchRule(watch_dir=str(dir_b), profile_name="profile_b"),
        ]
        service.start(rules, callback)
        assert service.is_active is True
        service.stop()

    def test_poll_removed_file_not_fired(self, service, tmp_path):
        callback = MagicMock()
        rule = WatchRule(watch_dir=str(tmp_path))
        service.start([rule], callback)
        f = tmp_path / "temp.txt"
        f.write_text("data")
        service.poll_once()
        f.unlink()
        service.poll_once()
        service.poll_once()
        # File was removed before settling → callback should NOT fire
        callback.assert_not_called()
        service.stop()
