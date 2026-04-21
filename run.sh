#!/usr/bin/env bash
# Launch Pearl's File Tools on macOS / Linux
set -euo pipefail

# Change to the directory containing this script
cd "$(dirname "$0")"

# Prefer python3 explicitly; fall back to python
PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

if [ -z "$PYTHON" ]; then
    echo "Error: Python 3 not found. Install it via 'brew install python' or from https://python.org" >&2
    exit 1
fi

PY_VERSION=$("$PYTHON" -c 'import sys; print(sys.version_info.major)')
if [ "$PY_VERSION" -lt 3 ]; then
    echo "Error: Python 3 is required (found Python $PY_VERSION)." >&2
    exit 1
fi

# Check for PyQt5
if ! "$PYTHON" -c "import PyQt5" 2>/dev/null; then
    echo "PyQt5 not found. Install it with:" >&2
    echo "  pip3 install PyQt5" >&2
    exit 1
fi

# macOS: set the High-DPI / Retina environment flag before launching
if [ "$(uname)" = "Darwin" ]; then
    export QT_MAC_WANTS_LAYER=1
fi

exec "$PYTHON" main.py "$@"
