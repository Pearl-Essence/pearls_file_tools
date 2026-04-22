"""Configuration management for Pearl's File Tools."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from constants import CONFIG_FILE_NAME, THEME_DARK, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT


def get_config_dir() -> Path:
    """Return the platform-appropriate config directory."""
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home()))
    else:
        base = Path.home() / '.config'
    return base / 'pearls_file_tools'


def get_data_dir() -> Path:
    """Return the platform-appropriate data directory (for SQLite db, etc.)."""
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home()))
    else:
        base = Path.home() / '.local' / 'share'
    return base / 'pearls_file_tools'


class Config:
    """Singleton configuration manager for application settings."""

    _instance: Optional['Config'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._config_path = get_config_dir() / CONFIG_FILE_NAME
        self._data: Dict[str, Any] = {}
        self._load_defaults()

    def _load_defaults(self):
        """Load default configuration values."""
        self._data = {
            'version': '1.0',
            'window': {
                'geometry': [100, 100, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT],
                'maximized': False,
                'last_active_tab': 0
            },
            'directories': {
                'last_browse_directory': str(Path.home()),
                'tab_specific': {
                    'bulk_renamer': '',
                    'organizer': '',
                    'extractor': '',
                    'image_browser': ''
                }
            },
            'preferences': {
                'theme': THEME_DARK,
                'confirm_before_operations': True,
                'auto_refresh_after_operation': True
            },
            'naming': {
                'profiles': [],
                'active_profile': None,
                'bad_patterns': ['_COPY', '_BACKUP', '_OLD', 'Copy of ', 'copy_of_'],
            },
            'tab_settings': {
                'bulk_renamer': {
                    'recursive_default': False,
                    'case_transform_default': 'none',
                    'extension_filters': {
                        'images': False,
                        'documents': False,
                        'videos': False,
                        'audio': False,
                        'archives': False
                    }
                },
                'organizer': {
                    'confidence_threshold': 0.4,
                    'auto_merge_conflicts': False
                },
                'extractor': {
                    'delete_after_extraction': False,
                    'supported_formats': {
                        'zip': True,
                        'tar': True,
                        'rar': True,
                        '7z': True
                    }
                },
                'image_browser': {
                    'thumbnail_size': 200,
                    'columns': 5,
                    'cache_enabled': True,
                    'hierarchy_depth': 2
                }
            }
        }

    def load_from_file(self, path: Optional[Path] = None):
        """Load configuration from JSON file."""
        if path is None:
            path = self._config_path

        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    # Merge loaded data with defaults (in case new settings were added)
                    self._merge_config(loaded_data)
                return True
        except Exception as e:
            print(f"Error loading config: {e}")
            return False

        return False

    def save_to_file(self, path: Optional[Path] = None):
        """Save configuration to JSON file."""
        if path is None:
            path = self._config_path

        try:
            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def _merge_config(self, loaded_data: Dict[str, Any]):
        """Merge loaded configuration with defaults."""
        def merge_dict(default: dict, loaded: dict) -> dict:
            """Recursively merge dictionaries."""
            result = default.copy()
            for key, value in loaded.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = merge_dict(result[key], value)
                else:
                    result[key] = value
            return result

        self._data = merge_dict(self._data, loaded_data)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key (e.g., 'window.geometry')."""
        keys = key.split('.')
        value = self._data

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any):
        """Set configuration value by dot-notation key (e.g., 'window.geometry')."""
        keys = key.split('.')
        data = self._data

        # Navigate to the parent dictionary
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]

        # Set the final value
        data[keys[-1]] = value

    def get_tab_setting(self, tab_name: str, setting_key: str, default: Any = None) -> Any:
        """Get a specific tab setting."""
        return self.get(f'tab_settings.{tab_name}.{setting_key}', default)

    def set_tab_setting(self, tab_name: str, setting_key: str, value: Any):
        """Set a specific tab setting."""
        self.set(f'tab_settings.{tab_name}.{setting_key}', value)

    def get_tab_directory(self, tab_name: str) -> str:
        """Get the last used directory for a specific tab."""
        return self.get(f'directories.tab_specific.{tab_name}', '')

    def set_tab_directory(self, tab_name: str, directory: str):
        """Set the last used directory for a specific tab."""
        self.set(f'directories.tab_specific.{tab_name}', directory)
        # Also update the general last browse directory
        self.set('directories.last_browse_directory', directory)

    @property
    def config_path(self) -> Path:
        """Get the configuration file path."""
        return self._config_path

    def reset_to_defaults(self):
        """Reset configuration to default values."""
        self._load_defaults()
