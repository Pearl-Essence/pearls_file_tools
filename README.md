# Pearl's File Tools

A unified file management desktop application built for video production studios. Combines bulk renaming, file organization, archive extraction, and image browsing into a single dark-themed GUI.

Built with Python 3.7+ and PyQt5. Runs on macOS and Windows.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Setup](#setup)
3. [Running the Application](#running-the-application)
4. [Features](#features)
5. [Keyboard Shortcuts](#keyboard-shortcuts)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)

---

## Requirements

The only thing you need to install manually is **Python 3.7 or later**. Everything else is handled by the setup script.

| Dependency | Required | Installed by setup script |
|---|---|---|
| Python 3.7+ | Yes | No — install once manually (see below) |
| PyQt5 | Yes | Yes — automatically |
| rarfile | No — RAR support | Yes — prompted |
| py7zr | No — 7Z support | Yes — prompted |
| pymediainfo | No — media metadata columns | Yes — prompted |
| watchdog | No — watch folders | Yes — prompted |
| ffprobe / ffmpeg | No — media metadata columns | No — see note below |

---

## Setup

### macOS

**Step 1 — Install Python 3** (one time only)

```bash
# If you have Homebrew (recommended):
brew install python

# Or download the installer from https://www.python.org/downloads/
```

**Step 2 — Run the setup script**

```bash
cd /path/to/pearls_file_tools
./run.sh --setup
```

That's it. The script will:
- Create an isolated virtual environment in `.venv/`
- Install PyQt5 automatically
- Ask yes/no for each optional dependency (RAR, 7Z, media metadata, watch folders)
- Check whether `ffprobe` is available and tell you how to install it if not
- Launch the app immediately when done

On subsequent launches, just run `./run.sh` — no setup needed again.

> **ffprobe (optional):** The setup script cannot install this because it is not a Python package. To enable metadata columns in the file list: `brew install ffmpeg`

---

### Windows

**Step 1 — Install Python 3** (one time only)

Download and run the installer from https://www.python.org/downloads/

During installation, check **"Add Python to PATH"** before clicking Install.

**Step 2 — Run the setup script**

Open Command Prompt or PowerShell in the `pearls_file_tools` folder and run:

```cmd
run.bat --setup
```

The script does the same thing as the macOS version — creates a venv, installs PyQt5, prompts for optional deps, and launches the app.

On subsequent launches, just run `run.bat`.

> **ffprobe (optional):** Download ffmpeg from https://ffmpeg.org/download.html and add its `bin\` folder to your system PATH.

---

## Running the Application

| Platform | First time | Subsequent launches |
|---|---|---|
| macOS | `./run.sh --setup` | `./run.sh` |
| Windows | `run.bat --setup` | `run.bat` |

Settings are saved automatically on exit to:
- **macOS:** `~/.config/pearls_file_tools/`
- **Windows:** `%APPDATA%\pearls_file_tools\`

---

## Features

### Bulk Renamer

Rename multiple files at once with a live preview before committing any changes.

**How to use:**
1. Click **Browse** or type a path into the directory field.
2. Check **Recursive** to include files in subdirectories.
3. Use the **File Type Filters** checkboxes to narrow the file list to images, video, audio, documents, or archives. Enter custom extensions (comma-separated, e.g. `.r3d, .braw`) in the Custom field.
4. Choose a rename mode and set options (see modes below).
5. Click **Preview Changes** to see a side-by-side table of old → new names before anything is written to disk.
6. Click **Apply Rename** to execute. A confirmation dialog appears first.
7. Click **Undo Last Operation** to reverse the most recent rename batch.

**Standard mode:**
- **Prefix** — text prepended to every filename
- **Suffix** — text appended before the extension
- **Rename to** — replaces the entire base name (extension is preserved)
- **Case** — leave unchanged, convert to UPPERCASE, lowercase, or Title Case

**Sequential / Number Files mode:**
- Renames the selected files to a numbered series: `base_001.ext`, `base_002.ext`, …
- Configure base name, start number, zero-padding width, and separator character.

**Template mode:**
- Composes filenames from named production tokens (PROJECT, EP, SHOT, DESC, VER, etc.) joined by a separator.
- Single file → exact composed name; multiple files → base name + `_001`, `_002`, …
- Token fields and separator are drawn from the active **Naming Profile** (see below).

**Prefix / Suffix Transposition:**
- Click **Detect** to automatically find common prefixes or suffixes across the file list.
- Check the tokens you want to process, or type custom ones in the Manual field (comma-separated).
- Use the **Prefix → Suffix** / **Suffix → Prefix** radio buttons to control direction.
- Click **Apply Transform** to move the matched token.

**Version bumping:**
- Click **Bump Version (_v##)** to increment the trailing `_v##` version number on all selected files (e.g. `hero_v02.mov` → `hero_v03.mov`).

**Companion file renaming:**
- **Rename Sidecars** — renames matching `.xmp .thm .lrv .json` files alongside each primary file.
- **Rename Captions** — renames matching `.srt .vtt .ttml .sbv .ass .ssa` files alongside each primary file.

**Normalize Incoming:**
- Click **Normalize Incoming** to strip common freelancer-added clutter patterns (e.g. `_COPY`, `Copy of `, `_OLD`) from filenames.
- A preview dialog shows exactly which files will change and lets you edit or add patterns before applying.
- Check **Save patterns to config** to persist the pattern list for future sessions.

**Lint Folder:**
- Click **Lint Folder** (or use **Edit → Lint Current Folder…**) to scan all files in the current directory for naming issues.
- Results appear in a non-modal dialog showing: illegal characters (Windows-incompatible), filenames exceeding 255 characters, Windows reserved names (CON, NUL, COM1–COM9, LPT1–LPT9), WIP/DRAFT/TEMP/TEST markers, and case-only duplicate names.
- If a naming profile is active, files that don't conform to its token structure are also flagged.

**Naming Profiles:**
- The **Naming Profile** bar at the top of the tab lets you pick an active profile from a dropdown.
- Click **Save as Profile…** to save the current template settings as a new named profile.
- Click **Manage Profiles…** (or **Edit → Manage Naming Profiles…**) to open the profile editor: create, rename, delete, and set the active profile; configure tokens, separator, version format, and episode format per profile.
- The active profile is marked with ★ in the profile list and its settings populate the Template mode fields.

**Rename History:**
- Every completed rename batch is logged to a local SQLite database.
- Open **Edit → Rename History…** to browse past operations: old name, new name, timestamp, and operation type.
- The history dialog is searchable and includes a **Clear History** button.
- After each batch, a CSV log (`_pearls_rename_log_YYYYMMDD_HHMMSS.csv`) is also written to the target directory. Click **Open Latest CSV Log** to open the most recent one.

**Media metadata columns:**
- The file list table includes hidden columns: **Codec**, **Resolution**, **Duration**, **FPS**.
- **Right-click the column header** to toggle any metadata column on or off.
- When a column is shown, a background worker reads metadata for all listed files using `ffprobe` (preferred) or `pymediainfo`. At least one must be installed.
- When columns are hidden, metadata is still shown in the filename cell's **tooltip** after loading completes.

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
2. Click **Scan Subdirectories**. The scanner analyzes filenames and groups files that share a common naming pattern.
3. The tree view shows each subdirectory with its detected groups. Each group lists the files it contains along with their sizes.
4. **Adjust groupings before organizing:**
   - **Right-click** a group to rename it, merge it with another group, or disband it (moves files back to Unsorted).
   - **Drag and drop** files within the same subdirectory to move them between groups or to Unsorted.
   - Click **Create New Group** to make an empty group and drag files into it.
5. Click **Organize Files** to move all grouped files into named subfolders. Unsorted files are left in place. A conflict dialog appears if a destination folder already exists.

**Image sequence detection:**
- After scanning, the organizer automatically detects image and frame sequences (e.g. `.exr`, `.dpx`, `.tga` files sharing a common base name and sequential frame numbers).
- Sequences of **3 or more frames** are shown as collapsible blue items in the tree, labeled with the frame range and count:  
  `HERO_Explosion [0001–0200, 200 frames, .exr]`
- Missing frames (gaps in the sequence) are reported in the item's **tooltip**.
- When you click **Organize Files**, sequences are organized as a group using the sequence's base name as the destination folder.

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
| `naming.profiles` | `[]` | List of saved naming profiles (JSON array) |
| `naming.active_profile` | `null` | Name of the currently active naming profile |
| `naming.bad_patterns` | `['_COPY', '_BACKUP', '_OLD', 'Copy of ', 'copy_of_']` | Patterns stripped by Normalize Incoming |

To reset all settings to defaults, delete the configuration file and relaunch the app.

---

## Troubleshooting

### App does not launch / "PyQt5 is not installed"

Run setup — it installs everything automatically:

```bash
# macOS
./run.sh --setup

# Windows
run.bat --setup
```

### "python3: command not found" when running run.sh

Python 3 is not installed or not on your PATH.

```bash
# macOS
brew install python

# Linux
sudo apt install python3
```

Then re-run `./run.sh --setup`.

### RAR or 7Z files are not extracted

Re-run setup and answer **y** when prompted for RAR or 7Z support:

```bash
./run.sh --setup
```

### Metadata columns show "—" for all files

Neither `ffprobe` nor `pymediainfo` is available. Install at least one:

```bash
# macOS — installs ffprobe as part of ffmpeg
brew install ffmpeg

# Or install pymediainfo via pip inside the venv
.venv/bin/pip install pymediainfo
```

On Windows, download ffmpeg from https://ffmpeg.org/download.html and add its `bin\` folder to your system PATH, then restart the app.

### Re-running setup after the first time

Setup is safe to run multiple times. It skips virtual environment creation if `.venv/` already exists and only installs what you say yes to. Use it whenever you want to add an optional dependency you skipped the first time.

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
