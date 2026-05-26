#!/usr/bin/env bash
# Pearl's File Tools — launcher + one-command setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

cd "$SCRIPT_DIR"

# ── helpers ──────────────────────────────────────────────────────────────────

find_python3() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            major=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo 0)
            if [[ "$major" -ge 3 ]]; then
                echo "$cmd"
                return
            fi
        fi
    done
    echo ""
}

pip_install() {
    "$VENV_DIR/bin/pip" install --quiet --upgrade "$@"
}

ask() {
    # ask <prompt> → returns 0 (yes) or 1 (no)
    local prompt="$1"
    local yn
    read -r -p "  $prompt [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]]
}

# ── setup ─────────────────────────────────────────────────────────────────────

run_setup() {
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   Pearl's File Tools — First-Time Setup  ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""

    # 1. Locate Python 3
    BASE_PYTHON=$(find_python3)
    if [[ -z "$BASE_PYTHON" ]]; then
        echo "ERROR: Python 3 not found on this system." >&2
        echo ""
        echo "Install it with one of these methods:"
        echo "  macOS  → brew install python"
        echo "  Linux  → sudo apt install python3  (or equivalent for your distro)"
        echo ""
        exit 1
    fi

    PY_VERSION=$("$BASE_PYTHON" --version 2>&1)
    echo "Using $PY_VERSION"
    echo ""

    # 2. Create virtual environment
    if [[ -d "$VENV_DIR" ]]; then
        echo "Virtual environment already exists — skipping creation."
    else
        echo "Creating virtual environment in .venv/ ..."
        "$BASE_PYTHON" -m venv "$VENV_DIR"
        echo "  Done."
    fi
    echo ""

    # 3. Upgrade pip silently
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip

    # 4. Required dependency
    echo "Installing required dependency..."
    pip_install "PySide6>=6.11.1"
    echo "  ✓  PySide6"
    echo ""

    # 5. Optional dependencies
    echo "Optional dependencies — press Enter to skip any:"
    echo ""

    if ask "RAR archive support (rarfile)?"; then
        pip_install rarfile && echo "    ✓  rarfile" || echo "    ✗  rarfile failed — check your internet connection"
    fi

    if ask "7Z archive support (py7zr)?"; then
        pip_install py7zr && echo "    ✓  py7zr" || echo "    ✗  py7zr failed"
    fi

    if ask "Media metadata — codec/fps/duration (pymediainfo)?"; then
        pip_install pymediainfo && echo "    ✓  pymediainfo" || echo "    ✗  pymediainfo failed"
    fi

    if ask "Watch folder automation (watchdog)?"; then
        pip_install watchdog && echo "    ✓  watchdog" || echo "    ✗  watchdog failed"
    fi

    echo ""

    # 6. Check ffprobe (external tool, not pip)
    if command -v ffprobe &>/dev/null; then
        echo "  ✓  ffprobe detected — video thumbnail & metadata features available."
    else
        echo "  ℹ  ffprobe not found (optional)."
        echo "     Install ffmpeg to enable video thumbnails:"
        if [[ "$(uname)" = "Darwin" ]]; then
            echo "       brew install ffmpeg"
        else
            echo "       sudo apt install ffmpeg"
        fi
    fi

    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║          Setup complete! Launching…       ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
}

# ── entry point ───────────────────────────────────────────────────────────────

if [[ "${1:-}" = "--setup" ]]; then
    run_setup
fi

# Resolve the Python to use: prefer the venv, fall back to system Python 3
if [[ -f "$VENV_DIR/bin/python" ]]; then
    PYTHON="$VENV_DIR/bin/python"
else
    PYTHON=$(find_python3)
    if [[ -z "$PYTHON" ]]; then
        echo "ERROR: Python 3 not found." >&2
        echo "Run setup first:  ./run.sh --setup"
        exit 1
    fi
fi

# Check PySide6 is present before trying to launch
if ! "$PYTHON" -c "import PySide6" 2>/dev/null; then
    echo "ERROR: PySide6 is not installed." >&2
    echo ""
    echo "Run setup to install everything automatically:"
    echo "  ./run.sh --setup"
    exit 1
fi

# macOS: required for Qt layer-backed views
if [[ "$(uname)" = "Darwin" ]]; then
    export QT_MAC_WANTS_LAYER=1
fi

exec "$PYTHON" main.py "$@"
