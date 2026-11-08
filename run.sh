#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# OpenCV's bundled Qt only ships the xcb plugin. Force XWayland so the app
# also starts correctly from a Wayland terminal.
export QT_QPA_PLATFORM=xcb
if [ -z "${DISPLAY:-}" ]; then
    if [ -S /tmp/.X11-unix/X1 ]; then
        export DISPLAY=:1
    else
        export DISPLAY=:0
    fi
fi

if [ ! -x .venv/bin/python ]; then
    echo "FingerCam is not installed yet."
    echo "Run ./install.sh first."
    exit 1
fi

exec .venv/bin/python app.py "$@"
