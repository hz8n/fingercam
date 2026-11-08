#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================"
echo "  FingerCam - Installation (Arch / Linux)"
echo "============================================"
echo

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "[ERROR] python3 was not found."
    echo "Install it with:  sudo pacman -S python python-pip"
    exit 1
fi

"$PYTHON" -c "import sys; print('Using Python', sys.version.split()[0])"

if [ ! -x .venv/bin/python ]; then
    echo
    echo "[1/3] Creating .venv ..."
    "$PYTHON" -m venv --system-site-packages .venv
else
    echo
    echo "[1/3] Reusing the existing .venv ..."
fi

echo
echo "[2/3] Updating pip ..."
.venv/bin/python -m pip install --upgrade pip

echo
if .venv/bin/python - <<'PY'
import importlib.util
import sys

missing = [
    name
    for name in ("cv2", "numpy", "mediapipe", "PIL")
    if importlib.util.find_spec(name) is None
]
if missing:
    print("Missing:", ", ".join(missing))
    sys.exit(1)
PY
then
    echo "[3/3] The heavy packages are already available in the system Python."
    .venv/bin/python -m pip install arabic-reshaper python-bidi
else
    echo "[3/3] Installing all requirements (this can take a few minutes) ..."
    .venv/bin/python -m pip install -r requirements.txt
fi

echo
echo "============================================"
echo "  Installation finished successfully!"
echo
echo "  Run:  ./run.sh"
echo "============================================"
