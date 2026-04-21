# Pearl's File Tools

A unified file management desktop application built for video production studios. Combines bulk renaming, file organization, archive extraction, and image browsing into a single dark-themed GUI.

Built with Python 3.7+ and PyQt5. Runs on macOS and Windows.

---

## Table of Contents

1. [Requirements](#requirements)
2. [macOS Setup](#macos-setup)
3. [Windows Setup](#windows-setup)
4. [Running the Application](#running-the-application)
5. [Features](#features)
6. [Keyboard Shortcuts](#keyboard-shortcuts)
7. [Configuration](#configuration)
8. [Optional Dependencies](#optional-dependencies)
9. [Troubleshooting](#troubleshooting)

---

## Requirements

| Dependency | Version | Required |
|---|---|---|
| Python | 3.7 or later | Yes |
| PyQt5 | 5.15.0 or later | Yes |
| rarfile | 4.0 or later | No — RAR support only |
| py7zr | 0.20.0 or later | No — 7Z support only |
| pymediainfo | 6.0.0 or later | No — media metadata only |
| watchdog | 3.0.0 or later | No — watch folders only |
| ffprobe / ffmpeg | any | No — video thumbnails & metadata only |

---

## macOS Setup

### Step 1 — Install Python 3

Check if Python 3 is already installed:

```bash
python3 --version
```

If the command is not found, install Python via Homebrew (recommended) or the official installer.

**Option A — Homebrew (recommended):**

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python
```

**Option B — Official installer:**

Download and run the macOS installer from https://www.python.org/downloads/

### Step 2 — Create a virtual environment (recommended)

A virtual environment keeps Pearl's File Tools dependencies isolated from your system Python.

```bash
# Navigate to the project directory
cd /path/to/pearls_file_tools

# Create the virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate
```

You will see `(.venv)` at the start of your terminal prompt when the environment is active. You must activate it each time you open a new terminal session before running the app.

### Step 3 — Install required dependencies

With the virtual environment active:

```bash
pip install PyQt5>=5.15.0
```

### Step 4 — (Optional) Install optional dependencies

Install only the ones you need:

```bash
# RAR archive support
pip install rarfile

# 7Z archive support
pip install py7zr

# Media metadata reading
pip install pymediainfo

# Watch folder automation
pip install watchdog

# ffprobe/ffmpeg for video thumbnails (via Homebrew)
brew install ffmpeg
```

### Step 5 — Verify the installation

```bash
python3 -c "import PyQt5; print('PyQt5 OK')"
```

You should see `PyQt5 OK` with no errors.

### Step 6 — Launch the application

```bash
# Using the launch script (handles environment checks automatically)
./run.sh

# Or directly
python3 main.py
```

> **Retina displays:** High-DPI scaling is enabled automatically. The app renders sharply on all Retina/Pro Display XDR screens.

---

## Windows Setup

### Step 1 — Install Python 3

Download and run the installer from https://www.python.org/downloads/

During installation, check **"Add Python to PATH"** before clicking Install.

Verify in Command Prompt or PowerShell:

```cmd
python --version
```

### Step 2 — Create a virtual environment (recommended)

```cmd
cd C:\path\to\pearls_file_tools
python -m venv .venv
.venv\Scripts\activate
```

You will see `(.venv)` in your prompt when the environment is active.

### Step 3 — Install required dependencies

```cmd
pip install PyQt5>=5.15.0
```

### Step 4 — (Optional) Install optional dependencies

```cmd
pip install rarfile
pip install py7zr
pip install pymediainfo
pip install watchdog
```

For ffprobe, download a Windows build from https://ffmpeg.org/download.html and add the `bin` folder to your system PATH.

### Step 5 — Launch the application

```cmd
run.bat
```

Or directly:

```cmd
python main.py
```

---

## Running the Application

| Platform | Command |
|---|---|
| macOS / Linux | `./run.sh` |
| Windows | `run.bat` or `python main.py` |

Both launch scripts automatically check that Python 3 and PyQt5 are available and print a clear error message if they are not.

Settings and configuration are saved automatically on exit. On macOS they are stored in `~/.config/pearls_file_tools/`. On Windows they are stored in `%APPDATA%\pearls_file_tools\`.

---

## Features

### Bulk Renamer

Rename multiple files at once with a live preview before committing any changes.

**How to use:**
1. Click **Browse** or type a path into the directory field.
2. Check **Recursive** to include files in subdirectories.
3. Use the **File Type Filters** checkboxes to narrow the file list to images, video, audio, documents, or archives. Enter custom extensions (comma-separated, e.g. `.r3d, .braw`) in the Custom field.
4. Set any combination of rename options:
   - **Prefix** — text prepended to every filename
   - **Suffix** — text appended before the extension
   - **Rename to** — replaces the entire base name (extension is preserved)
   - **Case** — leave unchanged, convert to UPPERCASE, lowercase, or Title Case
5. Click **Preview Changes** to see a side-by-side table of old → new names before anything is written to disk.
6. Click **Apply Rename** to execute. A confirmation dialog appears first.
7. Click **Undo Last Operation** to reverse the most recent rename batch.

**Prefix → Suffix transform:**
- Click **Detect Prefixes** to automatically find common prefixes across the file list (e.g. `DRAFT_`, `WIP_`).
- Check the prefixes you want to process, or type custom ones in the Manual field (comma-separated).
- Click **Apply Prefix → Suffix Transform** to move the matched prefix to the end of the base name.

**Supported file categories (including professional formats):**
- **Video:** `.mp4 .mov .mkv .avi .mxf .r3d .braw .prores .mts .m2ts .cine .ari` and more
- **Image:** `.jpg .png .tiff .exr .dpx .tga .hdr .raw .cr2 .nef .arw .dng` and more
- **Audio:** `.wav .flac .mp3 .aiff .aif .bwf .rf64` and more
- **Archives:** `.zip .rar .7z .tar .gz` and variants
- **Documents:** `.pdf .docx .xlsx .pptx .csv .md` and more

---

### File Organizer

Groups files inside subdirectories by naming patterns and moves them into organized folders.

**How to use:**
1. Select a **root directory** that contains one or more subdirectories with files to organize.
2. Click **Scan Subdirectories**. The scanner analyzes filenames and groups files that share a common naming pattern (prefix or keyword).
3. The tree view shows each subdirectory with its detected groups. Each group lists the files it contains, along with their sizes.
4. **Adjust groupings before organizing:**
   - **Right-click** a group to rename it, merge it with another group, or disband it (moves files back to Unsorted).
   - **Drag and drop** files within the same subdirectory to move them between groups or to Unsorted.
   - Click **Create New Group** to make an empty group and drag files into it.
5. Click **Organize Files** to move all grouped files into named subfolders. Unsorted files are left in place. A conflict dialog appears if a destination folder already exists.

---

### Archive Extractor

Scans a directory tree for archives and extracts them with smart folder collapsing.

**How to use:**
1. Select the **root directory** to scan.
2. Choose which archive formats to process (ZIP, TAR/GZ/BZ2/XZ, RAR, 7Z).
3. **Smart Extraction** (enabled by default) — when an archive contains a single top-level folder, its contents are moved up one level to avoid unnecessary nesting (e.g. `archive/archive/file.mov` becomes `archive/file.mov`).
4. **Keyword Filter** — when enabled, only extracts archives whose filename contains photo/image-related keywords.
5. **Delete after extraction** — backs up the original archive to a `.archive_extractor_backups` folder inside the root directory before deleting it.
6. The log panel shows each archive processed, success/failure status, and a summary at the end.

**Supported formats:**
| Format | Library required |
|---|---|
| ZIP | Built-in (always available) |
| TAR / TGZ / TBZ2 / TXZ | Built-in (always available) |
| RAR | `rarfile` (optional) |
| 7Z | `py7zr` (optional) |

If a library is not installed, that format's checkbox is disabled with an informational tooltip.

---

### Image Browser

Browses a directory tree for images and displays them as a thumbnail grid, organized by subfolder.

**How to use:**
1. Select a directory. The scanner runs in the background.
2. Use the folder panel on the left to filter by subfolder.
3. Click any thumbnail to open the full image in a viewer dialog.
4. The browser caches scan results in a hidden `.image_browser_cache.json` file so repeat opens of the same directory are instant. The cache is automatically invalidated when files change.
5. Use **Edit → Clear All Caches** to manually wipe cached scan data.

**Supported image formats:** `.jpg .jpeg .png .gif .bmp .webp .tiff .tif .svg .ico .heic .heif .exr .dpx .tga .hdr .raw .cr2 .nef .arw .dng`

> **Note:** RAW camera formats (`.cr2 .nef .arw .dng .r3d .braw`) may not render thumbnails without additional system support. They will appear in the file list but the preview may be blank.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+1` | Switch to Bulk Renamer tab |
| `Ctrl+2` | Switch to File Organizer tab |
| `Ctrl+3` | Switch to Archive Extractor tab |
| `Ctrl+4` | Switch to Image Browser tab |
| `Ctrl+O` | Open directory (active tab) |
| `Ctrl+R` | Refresh (active tab) |
| `Ctrl+,` | Open Settings |
| `Ctrl+W` | Close application |

---

## Configuration

Settings are saved automatically when you close the application. You can also edit them manually via **Edit → Settings**.

The configuration file is stored at:
- **macOS:** `~/.config/pearls_file_tools/pearls_file_tools_config.json`
- **Windows:** `%APPDATA%\pearls_file_tools\pearls_file_tools_config.json`

Key settings:

| Setting | Default | Description |
|---|---|---|
| `preferences.theme` | `dark` | UI theme (`dark` or `light`) |
| `preferences.confirm_before_operations` | `true` | Show confirmation dialog before rename/organize |
| `preferences.auto_refresh_after_operation` | `true` | Refresh file list after a rename completes |
| `tab_settings.organizer.confidence_threshold` | `0.4` | Minimum pattern match score to group files (0.0–1.0) |
| `tab_settings.extractor.delete_after_extraction` | `false` | Move archives to backup folder after extraction |
| `tab_settings.image_viewer.thumbnail_size` | `200` | Thumbnail size in pixels |
| `tab_settings.image_viewer.cache_enabled` | `true` | Enable image scan caching |

To reset all settings to defaults, delete the configuration file and relaunch the app.

---

## Optional Dependencies

Install any of these to unlock additional functionality:

```bash
# RAR archive extraction
pip install rarfile

# 7Z archive extraction
pip install py7zr

# Media metadata (codec, resolution, fps, duration)
pip install pymediainfo

# Watch folder automation (future feature)
pip install watchdog

# Video thumbnails and metadata via ffprobe (external tool)
# macOS:
brew install ffmpeg
# Windows: download from https://ffmpeg.org/download.html and add to PATH
```

The app detects missing optional libraries at startup. Features that require an unavailable library are disabled with a tooltip explaining what to install — the app never crashes due to a missing optional dependency.

---

## Troubleshooting

### App does not launch / "ModuleNotFoundError: No module named 'PyQt5'"

PyQt5 is not installed in the current Python environment.

```bash
pip install PyQt5
```

If you are using a virtual environment, make sure it is activated first (`source .venv/bin/activate` on macOS).

### "python3: command not found" when running run.sh

Python 3 is not on your PATH. Install it via Homebrew (`brew install python`) or the official installer and then try again.

### Archive Extractor tab does not load / crashes on open

This was a known bug fixed in Phase 1. If you have an older version, update to the current codebase.

### RAR or 7Z files are not extracted

Install the optional library for the format you need:

```bash
pip install rarfile   # RAR
pip install py7zr     # 7Z
```

Then relaunch the app.

### Images appear blank / thumbnails are black

This usually happens with RAW camera files (`.cr2`, `.nef`, `.arw`, `.braw`, `.r3d`). These formats require system-level codec support that Qt does not provide natively. The files will appear in the browser list but cannot be previewed without a dedicated RAW decoder.

### App window opens off-screen

Delete the configuration file to reset the saved window position:

- **macOS:** `~/.config/pearls_file_tools/pearls_file_tools_config.json`
- **Windows:** `%APPDATA%\pearls_file_tools\pearls_file_tools_config.json`

### Network / NAS paths are slow or produce permission errors

The app is hardened for network paths:
- Cache writes on read-only network shares are silently skipped rather than crashing.
- Directory stat errors (common on NFS/SMB mounts) are caught per-item.
- On Windows, UNC paths (`\\SERVER\Share\...`) are supported — do not use mapped drive letters if the share may be temporarily disconnected.

If scanning a network directory is very slow, disable caching in Settings or under `tab_settings.image_viewer.cache_enabled`.

### Settings are not saved between sessions

Check that the config directory is writable:

```bash
# macOS
ls -la ~/.config/pearls_file_tools/
```

If the directory does not exist, the app will create it on first save. If it exists but is owned by root or another user, fix the permissions:

```bash
sudo chown -R $(whoami) ~/.config/pearls_file_tools/
```
