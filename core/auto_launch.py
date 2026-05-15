"""Platform-specific auto-launch (login item) management.

macOS  — LaunchAgent plist in ~/Library/LaunchAgents/
Windows — HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
Linux  — .desktop file in ~/.config/autostart/
"""

import sys
from pathlib import Path

_PLIST_NAME = "com.pearl.post-suite.plist"
_REG_KEY_NAME = "PearlPostSuite"
_DESKTOP_NAME = "pearl-post-suite.desktop"


def _get_launch_command() -> str:
    """Return the command that starts the application."""
    # Prefer run.sh / run.bat if they exist next to the package
    pkg_dir = Path(__file__).resolve().parent.parent  # pearls_file_tools/
    if sys.platform == "darwin" or sys.platform.startswith("linux"):
        run_sh = pkg_dir / "run.sh"
        if run_sh.is_file():
            return str(run_sh)
    elif sys.platform == "win32":
        run_bat = pkg_dir / "run.bat"
        if run_bat.is_file():
            return str(run_bat)
    # Fallback: direct python invocation
    return f'"{sys.executable}" "{pkg_dir / "main.py"}"'


# ── macOS ────────────────────────────────────────────────────────────────────


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / _PLIST_NAME


def _macos_set(enabled: bool) -> None:
    plist = _macos_plist_path()
    if enabled:
        cmd = _get_launch_command()
        content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.pearl.post-suite</string>
    <key>ProgramArguments</key>
    <array>
        <string>{cmd}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(content)
    else:
        if plist.is_file():
            plist.unlink()


def _macos_get() -> bool:
    return _macos_plist_path().is_file()


# ── Windows ──────────────────────────────────────────────────────────────────


def _windows_set(enabled: bool) -> None:
    try:
        import winreg
    except ImportError:
        return
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = _get_launch_command()
                winreg.SetValueEx(key, _REG_KEY_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, _REG_KEY_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass


def _windows_get() -> bool:
    try:
        import winreg
    except ImportError:
        return False
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _REG_KEY_NAME)
            return True
    except (FileNotFoundError, OSError):
        return False


# ── Linux ────────────────────────────────────────────────────────────────────


def _linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / _DESKTOP_NAME


def _linux_set(enabled: bool) -> None:
    desktop = _linux_desktop_path()
    if enabled:
        cmd = _get_launch_command()
        content = f"""\
[Desktop Entry]
Type=Application
Name=Pearl Post Suite
Exec={cmd}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text(content)
    else:
        if desktop.is_file():
            desktop.unlink()


def _linux_get() -> bool:
    return _linux_desktop_path().is_file()


# ── Public API ───────────────────────────────────────────────────────────────


def set_auto_launch(enabled: bool) -> None:
    """Enable or disable launching Pearl Post Suite at OS login."""
    if sys.platform == "darwin":
        _macos_set(enabled)
    elif sys.platform == "win32":
        _windows_set(enabled)
    else:
        _linux_set(enabled)


def get_auto_launch() -> bool:
    """Return whether Pearl Post Suite is configured to launch at OS login."""
    if sys.platform == "darwin":
        return _macos_get()
    elif sys.platform == "win32":
        return _windows_get()
    else:
        return _linux_get()
