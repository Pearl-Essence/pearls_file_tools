"""Comprehensive tests for config.py."""

import json
from pathlib import Path

from config import Config, get_config_dir, get_data_dir


class TestGetConfigDir:
    def test_returns_path(self):
        result = get_config_dir()
        assert isinstance(result, Path)
        assert "pearls_file_tools" in str(result)

    def test_platform_appropriate(self):
        import sys

        result = get_config_dir()
        if sys.platform == "darwin":
            assert ".config" in str(result)
        elif sys.platform == "win32":
            assert "AppData" in str(result) or "pearls_file_tools" in str(result)


class TestGetDataDir:
    def test_returns_path(self):
        result = get_data_dir()
        assert isinstance(result, Path)
        assert "pearls_file_tools" in str(result)


class TestConfigSingleton:
    def test_singleton(self):
        a = Config()
        b = Config()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = Config()
        Config._instance = None
        b = Config()
        assert a is not b


class TestConfigDefaults:
    def test_has_window_defaults(self):
        cfg = Config()
        geom = cfg.get("window.geometry")
        assert geom is not None
        assert len(geom) == 4

    def test_has_theme_default(self):
        cfg = Config()
        assert cfg.get("preferences.theme") == "dark"

    def test_has_email_defaults(self):
        cfg = Config()
        assert cfg.get("email.smtp_port") == 587
        assert cfg.get("email.use_tls") is True

    def test_has_tab_settings(self):
        cfg = Config()
        assert cfg.get("tab_settings.bulk_renamer.recursive_default") is False
        assert cfg.get("tab_settings.organizer.confidence_threshold") == 0.4


class TestConfigGetSet:
    def test_get_simple(self):
        cfg = Config()
        assert cfg.get("version") == "1.0"

    def test_get_nested(self):
        cfg = Config()
        assert cfg.get("window.maximized") is False

    def test_get_missing_returns_default(self):
        cfg = Config()
        assert cfg.get("nonexistent.key") is None
        assert cfg.get("nonexistent.key", "fallback") == "fallback"

    def test_set_simple(self):
        cfg = Config()
        cfg.set("version", "2.0")
        assert cfg.get("version") == "2.0"

    def test_set_nested(self):
        cfg = Config()
        cfg.set("window.maximized", True)
        assert cfg.get("window.maximized") is True

    def test_set_creates_intermediate_keys(self):
        cfg = Config()
        cfg.set("new.nested.key", "value")
        assert cfg.get("new.nested.key") == "value"

    def test_set_overwrites(self):
        cfg = Config()
        cfg.set("preferences.theme", "light")
        assert cfg.get("preferences.theme") == "light"


class TestTabSettings:
    def test_get_tab_setting(self):
        cfg = Config()
        val = cfg.get_tab_setting("bulk_renamer", "recursive_default")
        assert val is False

    def test_set_tab_setting(self):
        cfg = Config()
        cfg.set_tab_setting("bulk_renamer", "recursive_default", True)
        assert cfg.get_tab_setting("bulk_renamer", "recursive_default") is True

    def test_get_tab_setting_default(self):
        cfg = Config()
        val = cfg.get_tab_setting("nonexistent_tab", "key", "default_val")
        assert val == "default_val"

    def test_get_tab_directory(self):
        cfg = Config()
        d = cfg.get_tab_directory("bulk_renamer")
        assert d == ""

    def test_set_tab_directory(self):
        cfg = Config()
        cfg.set_tab_directory("bulk_renamer", "/tmp/test")
        assert cfg.get_tab_directory("bulk_renamer") == "/tmp/test"
        assert cfg.get("directories.last_browse_directory") == "/tmp/test"


class TestConfigPersistence:
    def test_save_and_load(self, tmp_path):
        cfg = Config()
        cfg.set("preferences.theme", "light")
        path = tmp_path / "test_config.json"
        cfg.save_to_file(path)
        assert path.exists()

        # Reset and reload
        Config._instance = None
        cfg2 = Config()
        cfg2.load_from_file(path)
        assert cfg2.get("preferences.theme") == "light"

    def test_load_merges_with_defaults(self, tmp_path):
        path = tmp_path / "partial.json"
        path.write_text(json.dumps({"preferences": {"theme": "light"}}))
        cfg = Config()
        cfg.load_from_file(path)
        assert cfg.get("preferences.theme") == "light"
        # Default keys still present
        assert cfg.get("window.geometry") is not None

    def test_load_nonexistent_file(self, tmp_path):
        cfg = Config()
        result = cfg.load_from_file(tmp_path / "nonexistent.json")
        assert result is False

    def test_save_creates_parent_dirs(self, tmp_path):
        cfg = Config()
        path = tmp_path / "deep" / "path" / "config.json"
        cfg.save_to_file(path)
        assert path.exists()

    def test_config_path_property(self):
        cfg = Config()
        assert isinstance(cfg.config_path, Path)


class TestResetToDefaults:
    def test_reset(self):
        cfg = Config()
        cfg.set("preferences.theme", "light")
        cfg.reset_to_defaults()
        assert cfg.get("preferences.theme") == "dark"

    def test_reset_restores_all(self):
        cfg = Config()
        cfg.set("window.maximized", True)
        cfg.set("email.smtp_port", 999)
        cfg.reset_to_defaults()
        assert cfg.get("window.maximized") is False
        assert cfg.get("email.smtp_port") == 587


class TestMergeConfig:
    def test_deep_merge(self):
        cfg = Config()
        loaded = {
            "window": {"maximized": True},
            "preferences": {"theme": "light"},
        }
        cfg._merge_config(loaded)
        assert cfg.get("window.maximized") is True
        assert cfg.get("preferences.theme") == "light"
        # Original default keys preserved
        assert cfg.get("window.geometry") is not None

    def test_new_keys_added(self):
        cfg = Config()
        loaded = {"custom_key": "custom_value"}
        cfg._merge_config(loaded)
        assert cfg.get("custom_key") == "custom_value"

    def test_list_replaced_not_merged(self):
        cfg = Config()
        loaded = {"naming": {"bad_patterns": ["NEW_PATTERN"]}}
        cfg._merge_config(loaded)
        assert cfg.get("naming.bad_patterns") == ["NEW_PATTERN"]
