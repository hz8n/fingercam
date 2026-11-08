#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# OpenCV's bundled Qt only ships the xcb plugin. Without this, launching
# from Hyprland tries the Wayland plugin and crashes. Force XWayland.
export QT_QPA_PLATFORM=xcb
if [ -z "${DISPLAY:-}" ]; then
    if [ -S /tmp/.X11-unix/X1 ]; then
        export DISPLAY=:1
    else
        export DISPLAY=:0
    fi
fi

# If FingerCam is already running, just show a notification instead of
# opening a second copy (the camera can only be used by one process).
if pgrep -f '[.]venv/bin/python.*app[.]py' >/dev/null 2>&1; then
    notify-send -a FingerCam "FingerCam" "التطبيق يعمل بالفعل" 2>/dev/null || true
    exit 0
fi

# Keep the log small; the app appends warnings from Qt/MediaPipe.
if [ -f fingercam.log ] && [ "$(stat -c%s fingercam.log 2>/dev/null || echo 0)" -gt 1048576 ]; then
    mv -f fingercam.log fingercam.log.old
fi

exec .venv/bin/python -u app.py >> fingercam.log 2>&1
