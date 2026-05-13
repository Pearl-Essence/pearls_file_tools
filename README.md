# Pearl Post Suite

A premium desktop application for DIT and post-production file management. Combines offloading, bulk renaming, file organization, archive extraction, media browsing, delivery validation, and storage reporting in a single dark-themed sidebar-driven interface.

Built with Python 3.10+ and PySide6. Runs on macOS and Windows.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Setup](#setup)
3. [Running the Application](#running-the-application)
4. [Application Layout](#application-layout)
5. [Modules](#modules)
6. [Keyboard Shortcuts](#keyboard-shortcuts)
7. [Projects](#projects)
8. [Configuration](#configuration)
9. [Troubleshooting](#troubleshooting)

---

## Requirements

The only thing you need to install manually is **Python 3.10 or later**. Everything else is handled by the setup script.

| Dependency | Required | Installed by setup script |
|---|---|---|
| Python 3.10+ | Yes | No — install once manually (see below) |
| PySide6 | Yes | Yes — automatically |
| rarfile | No — RAR support | Yes — prompted |
| py7zr | No — 7Z support | Yes — prompted |
| pymediainfo | No — media metadata columns | Yes — prompted |
| watchdog | No — watch folders | Yes — prompted |
| ffprobe / ffmpeg | No — media metadata + proxy generation | No — see note below |

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
- Install PySide6 automatically
- Ask yes/no for each optional dependency (RAR, 7Z, media metadata, watch folders)
- Check whether `ffprobe` is available and tell you how to install it if not
- Launch the app immediately when done

On subsequent launches, just run `./run.sh` — no setup needed again.

> **ffprobe (optional):** The setup script cannot install this because it is not a Python package. To enable metadata columns and proxy generation: `brew install ffmpeg`

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

The script does the same thing as the macOS version — creates a venv, installs PySide6, prompts for optional deps, and launches the app.

On subsequent launches, just run `run.bat`.

> **ffprobe (optional):** Download ffmpeg from https://ffmpeg.org/download.html and add its `bin\` folder to your system PATH.

---

## Running the Application

| Platform | First time | Subsequent launches |
|---|---|---|
| macOS | `./run.sh --setup` | `./run.sh` |
| Windows | `run.bat --setup` | `run.bat` |

Or run directly:

```bash
cd pearls_file_tools
.venv/bin/python main.py
```

Settings are saved automatically on exit to:
- **macOS:** `~/.config/pearls_file_tools/`
- **Windows:** `%APPDATA%\pearls_file_tools\`

---

## Application Layout

Pearl Post Suite uses a sidebar-driven shell. The left rail contains:

- **Brand strip** — app name and version
- **Project selector** — click to create, switch, or edit projects
- **Navigation sidebar** — all modules organized into five sections
- **User footer** — quick access to settings, profiles, and history

The right side is a stacked content area. Selecting a sidebar item loads the corresponding module. The app remembers your last active tab and window size between sessions.

---

## Modules

### 01 · Ingest

#### Offload

Copy and verify camera media from source to destination with MD5 hash verification.

- **Source / Destination cards** — drag-drop or click to select folders
- **Verify by hash** — MD5 integrity check after copy
- **Mirror to secondary destination** — parallel copy to a backup volume
- **Generate MHL** — write an MHL (Media Hash List) sidecar for third-party verification
- **Eject source on completion** — unmount the source volume when finished
- **Email completion report** — send a summary via SMTP (configure in Settings)
- **Live manifest table** — per-file status pills (QUEUED → HASHING → VERIFIED / MISMATCH)
- **Footer metrics** — throughput, ETA, progress bar, cancel button

#### Proxy Generation

Pair full-resolution and proxy files by matching stems across two directory trees.

---

### 02 · Organize

#### Bulk Rename

Rename multiple files at once with a live preview before committing any changes.

**Rename modes:**
- **Standard** — prefix, suffix, find-and-replace, case conversion (UPPER, lower, Title)
- **Sequential** — numbered series (`base_001.ext`, `base_002.ext`, …)
- **Template** — production tokens (PROJECT, EP, SHOT, DESC, VER) joined by a configurable separator

**Additional tools:**
- **Prefix / Suffix Transposition** — detect and move common prefixes or suffixes
- **Version Bump** — increment trailing `_v##` numbers across all selected files
- **Companion Files** — co-rename sidecars (`.xmp .thm .lrv .json`) and captions (`.srt .vtt .ttml`)
- **Normalize Incoming** — strip freelancer clutter patterns (`_COPY`, `Copy of `, `_OLD`)
- **Lint Folder** — scan for illegal characters, length violations, reserved names, WIP markers
- **Naming Profiles** — save and load reusable template configurations
- **Rename History** — every batch is logged to SQLite; browse or export as CSV

**Media metadata columns:**
Right-click the column header to show Codec, Resolution, Duration, or FPS columns (requires `ffprobe` or `pymediainfo`).

#### Group by Pattern

Analyze filenames in subdirectories and organize files into folders by naming pattern.

- Drag-and-drop files between groups, create/rename/merge/disband groups
- Automatic image sequence detection (`.exr`, `.dpx`, `.tga`) with frame range labels and gap reporting
- Undo stack for all organize operations

#### Extract Archives

Scan a directory tree for archives and extract them with smart folder collapsing.

- Supported: ZIP, TAR/GZ/BZ2/XZ (built-in), RAR (`rarfile`), 7Z (`py7zr`)
- Smart extraction collapses single top-level folders
- Optional keyword filter and post-extraction backup

#### File Browser

Thumbnail grid browser for images and video files organized by subfolder.

- Background scanning with progress
- Click thumbnails to open in a viewer dialog
- Scan results cached for instant repeat opens

---

### 03 · Maintain

#### Stale Files

Detect and soft-delete stale, temporary, zero-byte, or empty items. Deleted files go to a local `.pearls_trash/` folder for safe recovery.

#### Storage Report

Break down disk usage by subfolder and file category. Supports qDirStat `.cache.gz` import/export.

#### NLE Backup

Snapshot DaVinci Resolve, Final Cut Pro, and Premiere Pro project files to a safe location.

#### Export Watcher

Watch render output folders and automatically route incoming files by naming pattern.

#### Trash

View, restore, or permanently delete items from the local `.pearls_trash/` directory.

#### Sync Check

Compare two directory trees file-by-file and reconcile differences.

#### Watch Folders

Configure persistent watch-folder rules that trigger file routing when new files arrive (requires `watchdog`).

---

### 04 · Deliver

#### Spec Validator

Validate a delivery folder against configurable rules: codec checks, resolution requirements, naming conventions, file count minimums.

- Empty-state hero with folder picker
- Rule builder for custom validation profiles
- Pass/fail results with per-file detail
- Cross-tab wiring: a passing validation pre-fills the Package & Export tab

#### Package & Export

Prepare a delivery package with four sub-tabs:

- **Package** — assemble final deliverables into a structured folder
- **Duplicates** — detect and resolve duplicate files
- **Handoff** — generate a handoff manifest
- **Export** — export delivery bundles with manifests

---

### 05 · Archive

#### Cold Storage

*(Planned)* Archive finished projects to LTO or external storage with hash verification.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+1` | Jump to 01 · Ingest (Offload) |
| `Ctrl+2` | Jump to 02 · Organize (Bulk Rename) |
| `Ctrl+3` | Jump to 03 · Maintain (Stale Files) |
| `Ctrl+4` | Jump to 04 · Deliver (Spec Validator) |
| `Ctrl+5` | Jump to 05 · Archive (Cold Storage) |
| `Ctrl+O` | Open directory (active tab) |
| `Ctrl+R` | Refresh (active tab) |
| `Ctrl+,` | Open Settings |
| `Ctrl+W` | Close application |

---

## Projects

Pearl Post Suite supports named projects that persist between sessions.

- Click the **project selector** in the sidebar to create, switch, or edit projects
- Each project stores a name, description, and default paths (ingest source, destination, mirror)
- When a project is active, its default paths auto-populate PathCards in relevant tabs
- Project data is stored in the app config — no files are created inside your project folders

---

## Configuration

Settings are saved automatically when you close the application. You can also edit them via **Edit → Settings** or the user footer menu.

The configuration file is stored at:
- **macOS:** `~/.config/pearls_file_tools/pearls_file_tools_config.json`
- **Windows:** `%APPDATA%\pearls_file_tools\pearls_file_tools_config.json`

Key settings:

| Setting | Default | Description |
|---|---|---|
| `preferences.theme` | `dark` | UI theme |
| `settings.remember_window_size` | `true` | Restore window geometry on launch |
| `settings.remember_last_tab` | `true` | Reopen the last active tab on launch |
| `tab_settings.organizer.confidence_threshold` | `0.4` | Minimum pattern match score (0.0–1.0) |
| `tab_settings.extractor.delete_after_extraction` | `false` | Move archives to backup after extraction |
| `tab_settings.image_browser.thumbnail_size` | `200` | Thumbnail size in pixels |
| `naming.profiles` | `[]` | Saved naming profiles |
| `naming.active_profile` | `null` | Currently active naming profile |
| `naming.bad_patterns` | `['_COPY', '_BACKUP', ...]` | Patterns stripped by Normalize Incoming |
| `email.smtp_server` | `""` | SMTP server for offload email reports |

To reset all settings to defaults, delete the configuration file and relaunch the app.

---

## Troubleshooting

### App does not launch

Run setup — it installs everything automatically:

```bash
# macOS
./run.sh --setup

# Windows
run.bat --setup
```

### "python3: command not found"

Python 3 is not installed or not on your PATH.

```bash
# macOS
brew install python

# Linux
sudo apt install python3
```

Then re-run `./run.sh --setup`.

### RAR or 7Z files are not extracted

Re-run setup and answer **y** when prompted for RAR or 7Z support.

### Metadata columns show "—" for all files

Neither `ffprobe` nor `pymediainfo` is available. Install at least one:

```bash
# macOS
brew install ffmpeg

# Or install pymediainfo
.venv/bin/pip install pymediainfo
```

On Windows, download ffmpeg from https://ffmpeg.org/download.html and add its `bin\` folder to your system PATH.

### Images appear blank / thumbnails are black

RAW camera files (`.cr2`, `.nef`, `.arw`, `.braw`, `.r3d`) require system-level codec support that Qt does not provide natively. The files appear in the browser list but cannot be previewed without a dedicated RAW decoder.

### App window opens off-screen

Delete the configuration file to reset the saved window position:

- **macOS:** `~/.config/pearls_file_tools/pearls_file_tools_config.json`
- **Windows:** `%APPDATA%\pearls_file_tools\pearls_file_tools_config.json`

### Network / NAS paths are slow or produce permission errors

The app is hardened for network paths:
- Cache writes on read-only network shares are silently skipped.
- Directory stat errors (common on NFS/SMB mounts) are caught per-item.
- On Windows, UNC paths (`\\SERVER\Share\...`) are supported.

If scanning a network directory is very slow, consider disabling caching in Settings.

### Re-running setup

Setup is safe to run multiple times. It skips venv creation if `.venv/` already exists and only installs what you confirm. Use it whenever you want to add an optional dependency you skipped before.
