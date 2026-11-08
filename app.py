#!/usr/bin/env python3
"""FingerCam — raise a finger and its own meme/emoji sticker appears next to it.

Everything runs locally on your computer: the webcam feed is never recorded
or uploaded. The interface is Arabic and the app is designed for Windows
(but also runs on Linux/macOS). Press T to cycle through sticker packs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import shutil
import subprocess
import time
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_PIP_NAMES = {
    "cv2": "opencv-python",
    "numpy": "numpy",
    "PIL": "Pillow",
    "mediapipe": "mediapipe",
}

try:
    import cv2
    import numpy as np
    import mediapipe as mp
    from PIL import Image, ImageDraw, ImageFont  # noqa: F401
except ImportError as exc:  # pragma: no cover - depends on the machine
    _package = _PIP_NAMES.get(exc.name or "", exc.name or "unknown")
    print(f"[FingerCam] Missing Python package: {_package}")
    print("  Install everything with:  pip install -r requirements.txt")
    print("  On Windows, run install.bat first.")
    raise SystemExit(1)

from hand_logic import (  # noqa: E402
    FINGER_KEYS,
    FINGER_NAMES_AR,
    FINGER_PIPS,
    FINGER_TIPS,
    WRIST,
    FingerState,
    count_fingers,
    landmarks_to_points,
)
from ui import (  # noqa: E402
    ARABIC_SHAPING_AVAILABLE,
    TextRenderer,
    draw_connector,
    draw_frame_border,
    draw_keycap,
    draw_panel,
    draw_ring,
    draw_sparkle,
    draw_sticker_bubble,
    hex_to_bgr,
    load_image_rgba,
    paste_centered,
    paste_rgba,
)

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.json"
MODEL_PATH = PROJECT_DIR / "models" / "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
SNAPSHOT_DIR = PROJECT_DIR / "snapshots"
PICTURES_DIR = Path.home() / "Pictures" / "FingerCam"
PACKS_DIR = PROJECT_DIR / "assets" / "packs"
STATE_PATH = PROJECT_DIR / ".state.json"
WINDOW_NAME = "FingerCam"

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)

DEFAULT_CONFIG = {
    "finger_emojis": {
        "thumb": "👍",
        "index": "☝️",
        "middle": "🤟",
        "ring": "💍",
        "pinky": "🤘",
    },
    "finger_colors": {
        "thumb": "#FF6B6B",
        "index": "#FFA94D",
        "middle": "#69DB7C",
        "ring": "#4DABF7",
        "pinky": "#DA77F2",
    },
    "sticker_packs": [
        {
            "name": "ميمز 1",
            "stickers": {
                "thumb": "assets/thumb.png",
                "index": "assets/index.png",
                "middle": "assets/middle.png",
                "ring": "assets/ring.png",
                "pinky": "assets/pinky.png",
            },
        },
        {
            "name": "ميمز 2",
            "stickers": {
                "thumb": "assets/memes2/thumb.png",
                "index": "assets/memes2/index.png",
                "middle": "assets/memes2/middle.png",
                "ring": "assets/memes2/ring.png",
                "pinky": "assets/memes2/pinky.png",
            },
        },
        {
            "name": "إيموجي",
            "stickers": {
                "thumb": "assets/emoji/thumb.png",
                "index": "assets/emoji/index.png",
                "middle": "assets/emoji/middle.png",
                "ring": "assets/emoji/ring.png",
                "pinky": "assets/emoji/pinky.png",
            },
        },
    ],
    "active_pack": 0,
    "sticker_size": 72,
    "show_labels": True,
    "show_count": True,
    "show_skeleton": True,
    "mirror": True,
    "sound": False,
    "auto_packs": True,
    "remember_pack": True,
    "theme": "ليلي",
    "night_light": False,
    "night_light_strength": 0.65,
}

COUNT_WORDS_AR = ("صفر", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة")
CHALLENGE_TARGETS_AR = {
    1: "إصبع واحد",
    2: "إصبعين",
    3: "ثلاثة أصابع",
    4: "أربعة أصابع",
    5: "خمسة أصابع",
}
COUNT_COLORS = {
    0: (90, 90, 235),
    1: (60, 170, 255),
    2: (80, 220, 255),
    3: (100, 220, 120),
    4: (255, 180, 80),
    5: (230, 120, 220),
}

# Each theme only changes the interface chrome; the per-finger sticker colours
# stay the same so memes keep their identity.
THEMES = {
    "ليلي": {
        "panel_fill": (14, 14, 22),
        "panel_border": (70, 70, 90),
        "accent": (200, 200, 90),
        "skeleton": (215, 215, 215),
        "joint": (80, 190, 255),
        "text": (230, 230, 240),
        "key_fill": (50, 50, 66),
        "key_border": (110, 110, 135),
        "line": (58, 58, 76),
    },
    "نيون": {
        "panel_fill": (24, 8, 28),
        "panel_border": (255, 60, 200),
        "accent": (255, 200, 0),
        "skeleton": (255, 90, 220),
        "joint": (0, 255, 190),
        "text": (245, 240, 255),
        "key_fill": (40, 16, 52),
        "key_border": (180, 60, 220),
        "line": (90, 30, 110),
    },
    "غروب": {
        "panel_fill": (20, 12, 30),
        "panel_border": (80, 140, 255),
        "accent": (60, 180, 255),
        "skeleton": (170, 200, 255),
        "joint": (50, 130, 255),
        "text": (255, 240, 230),
        "key_fill": (52, 34, 42),
        "key_border": (140, 100, 90),
        "line": (90, 60, 70),
    },
}
THEME_ORDER = tuple(THEMES)
DEFAULT_THEME = THEMES["ليلي"]

CHALLENGE_DURATION = 8.0
CHALLENGE_HOLD = 0.55

# Real system sounds instead of a terminal beep. Missing files fall back to
# the terminal bell, so this never breaks the app.
SOUND_FILES = {
    "count": "/usr/share/sounds/freedesktop/stereo/message.oga",
    "pack": "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "snapshot": "/usr/share/sounds/freedesktop/stereo/camera-shutter.oga",
    "challenge": "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "error": "/usr/share/sounds/freedesktop/stereo/dialog-error.oga",
}
WINDOWS_SOUNDS = {
    "count": "SystemAsterisk",
    "pack": "SystemExclamation",
    "snapshot": "SystemAsterisk",
    "challenge": "SystemExclamation",
    "error": "SystemHand",
}
DEFAULT_FINGER_COLORS_BGR = {
    finger: hex_to_bgr(DEFAULT_CONFIG["finger_colors"][finger], (200, 200, 200))
    for finger in FINGER_KEYS
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def _default_config() -> dict:
    return deepcopy(DEFAULT_CONFIG)


def _validate_pack(raw_pack, index: int, fallback: dict) -> dict | None:
    """Validate one sticker pack, filling missing fingers from the fallback."""
    if not isinstance(raw_pack, dict):
        return None
    name = raw_pack.get("name")
    if isinstance(name, str) and name.strip():
        name = name.strip()
    else:
        name = f"حزمة {index + 1}"
    values = raw_pack.get("stickers")
    if not isinstance(values, dict):
        return None
    stickers = {}
    for finger in FINGER_KEYS:
        value = values.get(finger)
        if isinstance(value, str) and value.strip():
            stickers[finger] = value.strip()
        else:
            stickers[finger] = fallback[finger]
    return {"name": name, "stickers": stickers}


def _validate_config(raw) -> tuple[dict, bool]:
    config = _default_config()
    if not isinstance(raw, dict):
        return config, False
    for key in (
        "show_labels",
        "show_count",
        "show_skeleton",
        "mirror",
        "sound",
        "auto_packs",
        "remember_pack",
        "night_light",
    ):
        if isinstance(raw.get(key), bool):
            config[key] = raw[key]
    size = raw.get("sticker_size")
    if isinstance(size, (int, float)) and not isinstance(size, bool):
        config["sticker_size"] = int(max(32, min(120, size)))
    strength = raw.get("night_light_strength")
    if isinstance(strength, (int, float)) and not isinstance(strength, bool):
        config["night_light_strength"] = max(0.1, min(1.0, float(strength)))
    theme = raw.get("theme")
    if isinstance(theme, str) and theme.strip() in THEMES:
        config["theme"] = theme.strip()
    for key in ("finger_emojis", "finger_colors"):
        values = raw.get(key)
        if isinstance(values, dict):
            for finger in FINGER_KEYS:
                value = values.get(finger)
                if isinstance(value, str) and value.strip():
                    config[key][finger] = value.strip()

    packs = []
    raw_packs = raw.get("sticker_packs")
    if isinstance(raw_packs, list):
        for index, raw_pack in enumerate(raw_packs):
            pack = _validate_pack(raw_pack, index, config["finger_emojis"])
            if pack is not None:
                packs.append(pack)
    if not packs:
        packs = [
            {"name": "الافتراضي", "stickers": dict(config["finger_emojis"])}
        ]
    config["sticker_packs"] = packs

    active = raw.get("active_pack")
    if isinstance(active, int) and not isinstance(active, bool):
        config["active_pack"] = active
    return config, True


def load_config(path: Path = CONFIG_PATH) -> tuple[dict, str]:
    """Load config.json, creating it with defaults when missing."""
    path = Path(path)
    if not path.exists():
        try:
            path.write_text(
                json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"[FingerCam] Created default settings: {path}")
        except OSError as exc:
            print(f"[FingerCam] Could not create {path.name}: {exc}")
        return _default_config(), "created"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[FingerCam] Could not read {path.name}: {exc}")
        print("[FingerCam] Using built-in defaults for this run.")
        return _default_config(), "error"
    config, ok = _validate_config(raw)
    if not ok:
        print(f"[FingerCam] {path.name} must contain a JSON object. Using defaults.")
        return _default_config(), "error"
    return config, "loaded"


def load_state() -> dict:
    """Read the tiny remembered-state file (last pack/theme)."""
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"[FingerCam] Could not save {STATE_PATH.name}: {exc}")


def discover_extra_packs(config: dict) -> list[dict]:
    """Turn every complete folder under assets/packs/ into a sticker pack.

    Folder layout:
        assets/packs/<name>/thumb.png
        assets/packs/<name>/index.png
        assets/packs/<name>/middle.png
        assets/packs/<name>/ring.png
        assets/packs/<name>/pinky.png
    An optional pack.json can contain {"name": "اسم الحزمة"}.
    """
    if not config.get("auto_packs", True) or not PACKS_DIR.is_dir():
        return []

    known = {
        str(pack.get("name", "")).strip().casefold()
        for pack in config.get("sticker_packs", [])
        if isinstance(pack, dict)
    }
    discovered: list[dict] = []
    for folder in sorted(PACKS_DIR.iterdir(), key=lambda item: item.name.casefold()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        name = folder.name
        manifest = folder / "pack.json"
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    candidate = data.get("name") or data.get("title")
                    if isinstance(candidate, str) and candidate.strip():
                        name = candidate.strip()
            except Exception as exc:
                print(f"[FingerCam] Could not read {manifest.name} in {folder.name}: {exc}")
        if name.casefold() in known:
            continue

        stickers: dict[str, str] = {}
        for finger in FINGER_KEYS:
            matches = [
                item
                for item in folder.iterdir()
                if item.is_file()
                and item.stem.casefold() == finger
                and item.suffix.lower() in IMAGE_EXTENSIONS
            ]
            if matches:
                stickers[finger] = str(
                    sorted(matches, key=lambda item: item.name.casefold())[0]
                    .relative_to(PROJECT_DIR)
                )
        if len(stickers) == len(FINGER_KEYS):
            discovered.append({"name": name, "stickers": stickers})
            known.add(name.casefold())
            print(f"[FingerCam] Auto pack: {name} ({folder.name})")
        else:
            missing = [finger for finger in FINGER_KEYS if finger not in stickers]
            print(
                f"[FingerCam] Skipping pack folder '{folder.name}': "
                f"missing {', '.join(missing)}"
            )
    return discovered


@dataclass
class FingerSticker:
    kind: str          # "emoji" or "image"
    value: object      # emoji string or Path to an image
    fallback_emoji: str


@dataclass
class StickerPack:
    name: str
    stickers: dict[str, FingerSticker]


def resolve_stickers(
    config: dict, values: dict | None = None
) -> dict[str, FingerSticker]:
    """Turn each configured value into an emoji or an image path."""
    values = values if values is not None else config["finger_emojis"]
    stickers: dict[str, FingerSticker] = {}
    for finger in FINGER_KEYS:
        value = str(values[finger]).strip()
        fallback = DEFAULT_CONFIG["finger_emojis"][finger]
        extension = Path(value).suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            image_path = Path(value)
            if not image_path.is_absolute():
                image_path = PROJECT_DIR / image_path
            if image_path.is_file():
                stickers[finger] = FingerSticker("image", image_path, fallback)
                continue
            print(
                f"[FingerCam] Image for '{finger}' was not found: {image_path}\n"
                f"            Falling back to {fallback}."
            )
        stickers[finger] = FingerSticker("emoji", value, fallback)
    return stickers


def build_sticker_packs(config: dict) -> list[StickerPack]:
    """Build every pack once so switching at runtime is instant."""
    raw_packs = list(config["sticker_packs"])
    raw_packs.extend(discover_extra_packs(config))
    packs = [
        StickerPack(
            str(raw_pack["name"]),
            resolve_stickers(config, raw_pack["stickers"]),
        )
        for raw_pack in raw_packs
    ]
    if not packs:
        packs.append(StickerPack("الافتراضي", resolve_stickers(config)))
    return packs


# ---------------------------------------------------------------------------
# Model / camera / tracker
# ---------------------------------------------------------------------------


def ensure_model(path: Path = MODEL_PATH) -> Path:
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path
    print("[FingerCam] Hand model not found. Downloading about 8 MB...")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    try:
        request = urllib.request.Request(
            MODEL_URL, headers={"User-Agent": "FingerCam/1.0"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(temporary, "wb") as handle:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if total:
                        percent = int(done * 100 / total)
                        print(
                            f"\r  {percent:3d}%  ({done / 1e6:.1f}/{total / 1e6:.1f} MB)",
                            end="",
                            flush=True,
                        )
        print()
        temporary.replace(path)
    except Exception as exc:
        print()
        print(f"[FingerCam] Could not download the model: {exc}")
        print("  Download it manually from:")
        print(f"  {MODEL_URL}")
        print("  and save it as:")
        print(f"  {path}")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise SystemExit(1)
    return path


def open_camera(index: int, width: int, height: int):
    if platform.system() == "Windows":
        backends = [
            (cv2.CAP_DSHOW, "DirectShow"),
            (cv2.CAP_MSMF, "Media Foundation"),
            (cv2.CAP_ANY, "default"),
        ]
    else:
        backends = [(cv2.CAP_V4L2, "V4L2"), (cv2.CAP_ANY, "default")]

    for backend, name in backends:
        capture = cv2.VideoCapture(index, backend)
        if not capture.isOpened():
            capture.release()
            continue
        # Many webcams only expose 1280x720 through MJPG. Without this they
        # silently fall back to 640x480 (which makes a distant person tiny).
        if platform.system() != "Windows":
            try:
                capture.set(
                    cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")
                )
            except Exception:
                pass
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, 30)
        try:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        for _ in range(8):
            ok, frame = capture.read()
            if ok and frame is not None:
                actual_w = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_h = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(
                    f"[FingerCam] Camera opened with {name} "
                    f"at {actual_w}x{actual_h}."
                )
                return capture
        capture.release()
    return None


def print_camera_help(index: int) -> None:
    print(f"[FingerCam] Could not open camera {index}.")
    print("  - Close apps that may be using the camera (Zoom, Teams, browsers).")
    print("  - Windows: Settings > Privacy & security > Camera > enable camera access")
    print("    and 'Let desktop apps access your camera'.")
    print("  - Try another camera index:  python app.py --camera 1")


@dataclass
class HandObservation:
    landmarks: list
    handedness: str = "?"


class HandTracker:
    """Small wrapper around the MediaPipe Tasks HandLandmarker API."""

    def __init__(self, model_path: Path, max_hands: int = 2) -> None:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.vision import RunningMode

        self._vision = vision
        self._start = time.monotonic()
        self._last_timestamp = -1
        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_buffer=Path(model_path).read_bytes()
            ),
            running_mode=RunningMode.VIDEO,
            num_hands=max(1, min(2, int(max_hands))),
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def detect(self, rgb_frame: np.ndarray) -> list[HandObservation]:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        timestamp = int((time.monotonic() - self._start) * 1000)
        if timestamp <= self._last_timestamp:
            timestamp = self._last_timestamp + 1
        self._last_timestamp = timestamp
        result = self._landmarker.detect_for_video(image, timestamp)
        observations: list[HandObservation] = []
        for index, landmarks in enumerate(result.hand_landmarks):
            label = "?"
            if index < len(result.handedness) and result.handedness[index]:
                label = result.handedness[index][0].category_name or "?"
            observations.append(HandObservation(list(landmarks), label))
        return observations

    def close(self) -> None:
        try:
            self._landmarker.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def draw_skeleton(
    frame: np.ndarray,
    points,
    color: tuple = (215, 215, 215),
    joint_color: tuple = (80, 190, 255),
) -> None:
    for start, end in HAND_CONNECTIONS:
        p1 = (int(points[start][0]), int(points[start][1]))
        p2 = (int(points[end][0]), int(points[end][1]))
        cv2.line(frame, p1, p2, color, 2, cv2.LINE_AA)
    for index, point in enumerate(points):
        if index in FINGER_TIPS:
            continue
        center = (int(point[0]), int(point[1]))
        cv2.circle(frame, center, 4, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(frame, center, 4, joint_color, 1, cv2.LINE_AA)


def sticker_size_for(count: int, base: int) -> int:
    """Shrink stickers as more fingers appear so they do not pile up."""
    if count <= 1:
        return base
    if count == 2:
        return max(40, int(base * 0.95))
    if count == 3:
        return max(38, int(base * 0.85))
    if count == 4:
        return max(36, int(base * 0.76))
    return max(34, int(base * 0.68))


def place_sticker_center(
    points, finger_index: int, radius: int, width: int, height: int, bob: float
) -> tuple[int, int]:
    tip = points[FINGER_TIPS[finger_index]]
    pip = points[FINGER_PIPS[finger_index]]
    dx, dy = tip[0] - pip[0], tip[1] - pip[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        ux, uy = 0.0, -1.0
    else:
        ux, uy = dx / length, dy / length
    cx = tip[0] + ux * (radius + 24)
    cy = tip[1] + uy * (radius + 24) + bob
    margin = radius + 10
    cx = min(max(cx, margin), width - margin)
    # Keep the bubble below the top HUD.
    cy = min(max(cy, 120 + radius), height - margin)
    return int(cx), int(cy)


def spread_sticker_centers(
    centers: list[tuple[int, int]],
    min_distance: float,
    width: int,
    height: int,
    margin: int,
) -> list[tuple[int, int]]:
    """Push overlapping bubbles apart while keeping them near their fingers."""
    points = [[float(x), float(y)] for x, y in centers]
    if len(points) < 2:
        return [(int(round(x)), int(round(y))) for x, y in points]
    for _ in range(16):
        moved = False
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                dx = points[j][0] - points[i][0]
                dy = points[j][1] - points[i][1]
                distance = math.hypot(dx, dy)
                if distance >= min_distance:
                    continue
                if distance < 1e-6:
                    dx, dy = 1.0, 0.0
                    distance = 1.0
                push = (min_distance - distance) * 0.5
                ux, uy = dx / distance, dy / distance
                points[i][0] -= ux * push
                points[i][1] -= uy * push
                points[j][0] += ux * push
                points[j][1] += uy * push
                moved = True
        for point in points:
            point[0] = min(max(point[0], margin), width - margin)
            point[1] = min(max(point[1], 120 + margin), height - margin)
        if not moved:
            break
    return [(int(round(x)), int(round(y))) for x, y in points]


def draw_count_pill(
    frame: np.ndarray,
    renderer: TextRenderer,
    points,
    state: FingerState,
    width: int,
    height: int,
) -> None:
    number = renderer.render(
        str(state.count), 30, color=(255, 255, 255), bold=True, shape=False
    )
    word = renderer.render(
        COUNT_WORDS_AR[min(state.count, 5)], 16, color=(220, 220, 235), bold=True
    )
    if number is None or word is None:
        return
    pad_x, pad_y, gap = 14, 8, 10
    pill_w = pad_x * 2 + number.shape[1] + gap + word.shape[1]
    pill_h = max(number.shape[0], word.shape[0]) + pad_y * 2
    wrist_x, wrist_y = points[WRIST]
    if wrist_x < width / 2:
        x = wrist_x + 46
    else:
        x = wrist_x - 46 - pill_w
    x = min(max(x, 16), width - pill_w - 16)
    y = min(max(wrist_y - pill_h / 2, 120), height - pill_h - 16)
    color = COUNT_COLORS.get(state.count, COUNT_COLORS[5])
    draw_panel(
        frame,
        (x, y, x + pill_w, y + pill_h),
        radius=pill_h // 2,
        fill=(15, 15, 23),
        alpha=0.86,
        border=color,
        border_thickness=2,
    )
    paste_rgba(frame, number, x + pad_x, y + (pill_h - number.shape[0]) // 2)
    paste_rgba(
        frame,
        word,
        x + pad_x + number.shape[1] + gap,
        y + (pill_h - word.shape[0]) // 2,
    )


def draw_hand(
    frame: np.ndarray,
    renderer: TextRenderer,
    points,
    state: FingerState,
    *,
    colors: dict,
    stickers: dict,
    base_size: int,
    show_labels: bool,
    show_count: bool,
    now: float,
    seen: dict,
    hand_key: int,
    show_skeleton: bool,
    theme: dict | None = None,
) -> None:
    height, width = frame.shape[:2]
    theme = theme or DEFAULT_THEME
    if show_skeleton:
        draw_skeleton(
            frame,
            points,
            color=theme["skeleton"],
            joint_color=theme["joint"],
        )

    size = sticker_size_for(state.count, base_size)
    radius = max(18, size // 2)
    inner = max(16, int(size * 0.82))
    up_indices = [index for index, is_up in enumerate(state.fingers) if is_up]

    centers: list[tuple[int, int]] = []
    for finger_index in up_indices:
        bob = math.sin(now * 3.2 + finger_index * 1.9) * 4.0
        centers.append(
            place_sticker_center(points, finger_index, radius, width, height, bob)
        )
    centers = spread_sticker_centers(
        centers, 2 * radius + 10, width, height, radius + 10
    )

    for finger_index, center in zip(up_indices, centers):
        finger = FINGER_KEYS[finger_index]
        color = colors[finger]
        key = (hand_key, finger_index)
        if key not in seen:
            seen[key] = now
        age = now - seen[key]
        tip = points[FINGER_TIPS[finger_index]]

        # Pop-in animation: a small overshoot makes a newly raised finger feel
        # responsive instead of just snapping the sticker on screen.
        if 0.0 <= age < 0.38:
            t = age / 0.38
            pop = (
                0.55
                + 0.45 * (1.0 - (1.0 - t) ** 3)
                + 0.10 * math.sin(math.pi * t) * (1.0 - t)
            )
        else:
            pop = 1.0
        anim_radius = max(12, int(radius * pop))
        anim_inner = max(12, int(inner * pop))

        draw_connector(frame, tip, center, anim_radius, color)

        if 0.0 <= age < 0.45:
            progress = age / 0.45
            draw_ring(
                frame,
                center,
                radius + int(8 + 28 * progress),
                color,
                thickness=2,
                alpha=0.55 * (1.0 - progress),
            )

        if 0.0 <= age < 0.55:
            progress = age / 0.55
            for sparkle_index in range(4):
                angle = -math.pi / 2 + sparkle_index * math.pi / 2
                distance = anim_radius + 8 + 18 * progress
                draw_sparkle(
                    frame,
                    (
                        center[0] + math.cos(angle) * distance,
                        center[1] + math.sin(angle) * distance,
                    ),
                    max(2, int(4 * (1.0 - progress))),
                    color,
                    1,
                )

        sticker = stickers[finger]
        content = None
        if sticker.kind == "image":
            content = load_image_rgba(sticker.value, anim_inner)
        if content is None:
            content = renderer.render(sticker.value, anim_inner, emoji=True)
        if content is None:
            content = renderer.render(
                sticker.fallback_emoji, anim_inner, emoji=True
            )
        draw_sticker_bubble(frame, center, anim_radius, color, content)

        if show_labels and state.count <= 3:
            label = renderer.render(
                FINGER_NAMES_AR[finger_index], 14, color=(255, 255, 255), bold=True
            )
            if label is not None:
                pill_w = label.shape[1] + 16
                pill_h = label.shape[0] + 6
                px = center[0] - pill_w // 2
                py = center[1] + radius + 14
                px = min(max(px, 4), width - pill_w - 4)
                py = min(py, height - pill_h - 4)
                draw_panel(
                    frame,
                    (px, py, px + pill_w, py + pill_h),
                    radius=pill_h // 2,
                    fill=(18, 18, 26),
                    alpha=0.86,
                    border=color,
                    border_thickness=1,
                )
                paste_centered(frame, label, px + pill_w / 2, py + pill_h / 2)

    if show_count:
        draw_count_pill(frame, renderer, points, state, width, height)


def draw_hud(
    frame: np.ndarray,
    renderer: TextRenderer,
    fps: float,
    theme: dict | None = None,
) -> None:
    height, width = frame.shape[:2]
    theme = theme or DEFAULT_THEME
    draw_panel(
        frame,
        (14, 12, width - 14, 108),
        radius=20,
        fill=theme["panel_fill"],
        alpha=0.74,
        border=theme["panel_border"],
        border_thickness=1,
    )
    title = renderer.render("كاميرا الأصابع", 26, color=(255, 255, 255), bold=True)
    subtitle = renderer.render(
        "ارفع أي إصبع لتظهر صورته الخاصة", 15, color=theme["text"]
    )
    right = width - 34
    if title is not None:
        paste_rgba(frame, title, right - title.shape[1], 20)
    if subtitle is not None:
        paste_rgba(frame, subtitle, right - subtitle.shape[1], 64)
    # Small accent strip on the right edge of the HUD.
    cv2.rectangle(
        frame, (width - 22, 26), (width - 18, 94), theme["accent"], -1, cv2.LINE_AA
    )
    # Stats on the left.
    cv2.putText(
        frame,
        f"FPS {fps:4.1f}",
        (34, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        theme["text"],
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"{width}x{height}",
        (34, 82),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        theme["text"],
        1,
        cv2.LINE_AA,
    )


def draw_pack_badge(
    frame: np.ndarray,
    renderer: TextRenderer,
    pack_name: str,
    theme: dict | None = None,
) -> None:
    """Small persistent badge showing the active sticker pack."""
    _, width = frame.shape[:2]
    theme = theme or DEFAULT_THEME
    text = renderer.render(
        f"الحزمة: {pack_name}", 14, color=(255, 255, 255), bold=True
    )
    if text is None:
        return
    pill_w = min(width - 28, text.shape[1] + 28)
    pill_h = text.shape[0] + 12
    x1 = 14
    y1 = 118
    draw_panel(
        frame,
        (x1, y1, x1 + pill_w, y1 + pill_h),
        radius=pill_h // 2,
        fill=theme["panel_fill"],
        alpha=0.80,
        border=theme["accent"],
        border_thickness=1,
    )
    paste_centered(frame, text, x1 + pill_w / 2, y1 + pill_h / 2)


def draw_footer(
    frame: np.ndarray,
    renderer: TextRenderer,
    theme: dict | None = None,
) -> None:
    height, width = frame.shape[:2]
    theme = theme or DEFAULT_THEME
    gap = 9
    group_gap = 26
    pad = 17
    groups = (("H", "للمساعدة"), ("T", "تبديل الصور"), ("R", "للإعدادات"))
    rendered = []
    for key, label in groups:
        key_img = renderer.render(
            key, 14, color=(255, 255, 255), bold=True, shape=False
        )
        label_img = renderer.render(label, 16, color=theme["text"])
        if key_img is None or label_img is None:
            return
        key_w = key_img.shape[1] + 18
        key_h = key_img.shape[0] + 8
        group_w = key_w + gap + label_img.shape[1]
        rendered.append((key_img, label_img, key_w, key_h, group_w))
    content_w = sum(item[4] for item in rendered) + group_gap * (len(rendered) - 1)
    pill_w = content_w + pad * 2
    pill_h = max(
        max(item[3] for item in rendered),
        max(item[1].shape[0] for item in rendered),
    ) + 14
    x1 = (width - pill_w) // 2
    y1 = height - pill_h - 14
    draw_panel(
        frame,
        (x1, y1, x1 + pill_w, y1 + pill_h),
        radius=pill_h // 2,
        fill=theme["panel_fill"],
        alpha=0.74,
        border=theme["panel_border"],
        border_thickness=1,
    )
    x = x1 + pad
    for key_img, label_img, key_w, key_h, group_w in rendered:
        key_y = y1 + (pill_h - key_h) // 2
        draw_panel(
            frame,
            (x, key_y, x + key_w, key_y + key_h),
            radius=7,
            fill=theme["key_fill"],
            alpha=0.95,
            border=theme["key_border"],
            border_thickness=1,
        )
        paste_centered(frame, key_img, x + key_w / 2, key_y + key_h / 2)
        paste_rgba(
            frame,
            label_img,
            x + key_w + gap,
            y1 + (pill_h - label_img.shape[0]) // 2,
        )
        x += group_w + group_gap


def draw_no_hand(
    frame: np.ndarray,
    renderer: TextRenderer,
    now: float,
    theme: dict | None = None,
) -> None:
    height, width = frame.shape[:2]
    theme = theme or DEFAULT_THEME
    text_img = renderer.render(
        "ارفع يدك أمام الكاميرا", 24, color=theme["text"], bold=True
    )
    emoji_img = renderer.render("👋", 30, emoji=True)
    if text_img is None:
        return
    gap = 12
    emoji_w = emoji_img.shape[1] if emoji_img is not None else 0
    content_w = (emoji_w + gap if emoji_w else 0) + text_img.shape[1]
    pill_w = content_w + 44
    pill_h = max(64, text_img.shape[0] + 24)
    x1 = (width - pill_w) // 2
    y1 = (height - pill_h) // 2 - 6
    alpha = 0.66 + 0.07 * math.sin(now * 2.2)
    draw_panel(
        frame,
        (x1, y1, x1 + pill_w, y1 + pill_h),
        radius=pill_h // 2,
        fill=theme["panel_fill"],
        alpha=alpha,
        border=theme["panel_border"],
        border_thickness=1,
    )
    x = x1 + 22
    if emoji_img is not None:
        paste_centered(frame, emoji_img, x + emoji_w / 2, y1 + pill_h / 2)
        x += emoji_w + gap
    paste_centered(frame, text_img, x + text_img.shape[1] / 2, y1 + pill_h / 2)


def draw_help(
    frame: np.ndarray,
    renderer: TextRenderer,
    pack_name: str = "",
    theme: dict | None = None,
) -> None:
    height, width = frame.shape[:2]
    theme = theme or DEFAULT_THEME
    panel_w = min(650, width - 36)
    panel_h = min(470, height - 36)
    x1 = (width - panel_w) // 2
    y1 = (height - panel_h) // 2
    x2, y2 = x1 + panel_w, y1 + panel_h
    draw_panel(
        frame,
        (x1, y1, x2, y2),
        radius=24,
        fill=theme["panel_fill"],
        alpha=0.94,
        border=theme["panel_border"],
        border_thickness=2,
    )
    title = renderer.render("المساعدة", 27, color=(255, 255, 255), bold=True)
    paste_centered(frame, title, width / 2, y1 + 34)
    cv2.line(
        frame,
        (x1 + 34, y1 + 56),
        (x2 - 34, y1 + 56),
        theme["line"],
        1,
        cv2.LINE_AA,
    )
    rows = (
        ("Q / Esc", "خروج من البرنامج"),
        ("H", "إظهار أو إخفاء المساعدة"),
        ("S", "لقطة بعد 3 ثوانٍ"),
        ("C", "وضع التحدي"),
        ("Y", "تغيير الثيم"),
        ("L", "إظهار أو إخفاء هيكل اليد"),
        ("M", "عكس صورة الكاميرا"),
        ("P", "تشغيل أو إيقاف الصوت"),
        ("F", "ملء الشاشة"),
        ("T", "تبديل الصور والميمز"),
        ("1 – 3", "اختيار حزمة مباشرة"),
        ("R", "إعادة تحميل الإعدادات"),
    )
    key_w = 108
    row_gap = max(24, min(42, (panel_h - 165) // len(rows)))
    y = y1 + 74
    for key, description in rows:
        draw_keycap(
            frame,
            renderer,
            (x1 + 34, y, x1 + 34 + key_w, y + 28),
            key,
            font_size=13,
            fill=theme["key_fill"],
            border=theme["key_border"],
        )
        description_img = renderer.render(
            description, 17, color=theme["text"]
        )
        if description_img is not None:
            paste_rgba(
                frame,
                description_img,
                x1 + 34 + key_w + 20,
                y + (28 - description_img.shape[0]) // 2,
            )
        y += row_gap
    footer_text = (
        f"الحزمة الحالية: {pack_name}"
        if pack_name
        else "غيّر الصور أو أضف ميمز من ملف الإعدادات"
    )
    footer = renderer.render(
        footer_text,
        14,
        color=theme["text"],
    )
    cv2.line(
        frame,
        (x1 + 34, y2 - 48),
        (x2 - 34, y2 - 48),
        theme["line"],
        1,
        cv2.LINE_AA,
    )
    paste_centered(frame, footer, width / 2, y2 - 26)


def draw_toast(
    frame: np.ndarray,
    renderer: TextRenderer,
    text: str,
    color: tuple = (90, 200, 120),
) -> None:
    height, width = frame.shape[:2]
    image = renderer.render(text, 18, color=(255, 255, 255), bold=True)
    if image is None:
        return
    pill_w = image.shape[1] + 44
    pill_h = image.shape[0] + 16
    x1 = (width - pill_w) // 2
    y1 = 158
    draw_panel(
        frame,
        (x1, y1, x1 + pill_w, y1 + pill_h),
        radius=pill_h // 2,
        fill=(18, 18, 26),
        alpha=0.94,
        border=color,
        border_thickness=2,
    )
    paste_centered(frame, image, width / 2, y1 + pill_h / 2)


def draw_challenge_panel(
    frame: np.ndarray,
    renderer: TextRenderer,
    *,
    target: int,
    score: int,
    streak: int,
    remaining: float,
    duration: float,
    state: str = "playing",
    theme: dict | None = None,
) -> None:
    """Small game panel: raise the requested number of fingers in time."""
    height, width = frame.shape[:2]
    theme = theme or DEFAULT_THEME
    panel_w = min(320, width - 28)
    panel_h = 128
    x1 = width - panel_w - 14
    y1 = height - panel_h - 74
    x2, y2 = x1 + panel_w, y1 + panel_h
    if state == "success":
        color = (90, 220, 120)
    elif state == "timeout":
        color = (80, 80, 230)
    else:
        color = theme["accent"]
    draw_panel(
        frame,
        (x1, y1, x2, y2),
        radius=18,
        fill=theme["panel_fill"],
        alpha=0.90,
        border=color,
        border_thickness=2,
    )

    title = renderer.render(
        "وضع التحدي", 15, color=(255, 255, 255), bold=True
    )
    if title is not None:
        paste_rgba(frame, title, x1 + 16, y1 + 10)

    if state == "success":
        target_text = "صح! أحسنت"
    elif state == "timeout":
        target_text = "انتهى الوقت"
    else:
        target_text = f"ارفع {CHALLENGE_TARGETS_AR.get(target, str(target))}"
    target_img = renderer.render(
        target_text, 20, color=(255, 255, 255), bold=True
    )
    if target_img is not None:
        paste_rgba(frame, target_img, x1 + 16, y1 + 36)

    # Timer bar.
    bar_x1, bar_x2 = x1 + 16, x2 - 16
    bar_y = y1 + 78
    cv2.rectangle(
        frame, (bar_x1, bar_y), (bar_x2, bar_y + 8), (45, 45, 60), -1, cv2.LINE_AA
    )
    ratio = max(0.0, min(1.0, remaining / max(0.001, duration)))
    if ratio > 0.5:
        bar_color = (90, 220, 120)
    elif ratio > 0.22:
        bar_color = (60, 200, 255)
    else:
        bar_color = (80, 80, 230)
    fill_x2 = bar_x1 + int((bar_x2 - bar_x1) * ratio)
    if fill_x2 > bar_x1:
        cv2.rectangle(
            frame,
            (bar_x1, bar_y),
            (fill_x2, bar_y + 8),
            bar_color,
            -1,
            cv2.LINE_AA,
        )
    cv2.rectangle(
        frame,
        (bar_x1, bar_y),
        (bar_x2, bar_y + 8),
        theme["panel_border"],
        1,
        cv2.LINE_AA,
    )

    stats = renderer.render(
        f"النقاط: {score}    متتالية: {streak}", 13, color=theme["text"]
    )
    if stats is not None:
        paste_rgba(frame, stats, x1 + 16, y1 + 98)
    hint = renderer.render("C للإيقاف", 11, color=theme["text"])
    if hint is not None:
        paste_rgba(frame, hint, x2 - hint.shape[1] - 16, y1 + 100)


def draw_countdown(
    frame: np.ndarray,
    renderer: TextRenderer,
    remaining: float,
    total: float = 3.0,
    theme: dict | None = None,
) -> None:
    """Big 3-2-1 overlay used before saving a snapshot."""
    height, width = frame.shape[:2]
    theme = theme or DEFAULT_THEME
    center = (width // 2, height // 2)
    radius = max(54, min(86, width // 8))
    overlay = frame.copy()
    cv2.circle(overlay, center, radius, (8, 8, 14), -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)
    cv2.circle(frame, center, radius, theme["accent"], 3, cv2.LINE_AA)
    progress = max(0.0, min(1.0, remaining / max(0.001, total)))
    cv2.ellipse(
        frame,
        center,
        (radius + 8, radius + 8),
        0,
        -90,
        -90 + int(360 * progress),
        theme["accent"],
        5,
        cv2.LINE_AA,
    )
    number = str(max(1, int(math.ceil(remaining))))
    number_img = renderer.render(
        number, max(42, radius), color=(255, 255, 255), bold=True, shape=False
    )
    paste_centered(frame, number_img, center[0], center[1])
    label = renderer.render(
        "استعد للصورة", 18, color=theme["text"], bold=True
    )
    paste_centered(frame, label, center[0], center[1] + radius + 26)


def apply_night_light(frame: np.ndarray, strength: float) -> None:
    """Warm the preview and reduce blue light (like a screen night light)."""
    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 0.001:
        return
    warm = np.empty_like(frame)
    warm[..., 0] = 30   # blue
    warm[..., 1] = 150  # green
    warm[..., 2] = 255  # red
    alpha = 0.38 * strength
    cv2.addWeighted(frame, 1.0 - alpha, warm, alpha, 0, frame)
    # Slightly lower the brightness so late-night use is easier on the eyes.
    frame[:] = np.clip(
        frame.astype(np.float32) * (1.0 - 0.06 * strength), 0, 255
    ).astype(np.uint8)


def draw_night_badge(
    frame: np.ndarray,
    renderer: TextRenderer,
    strength: float,
    theme: dict | None = None,
) -> None:
    theme = theme or DEFAULT_THEME
    text = renderer.render(
        f"إضاءة ليلية {int(round(strength * 100))}%",
        12,
        color=(255, 255, 255),
        bold=True,
    )
    if text is None:
        return
    pill_w = text.shape[1] + 22
    pill_h = text.shape[0] + 8
    x1, y1 = 14, 154
    draw_panel(
        frame,
        (x1, y1, x1 + pill_w, y1 + pill_h),
        radius=pill_h // 2,
        fill=theme["panel_fill"],
        alpha=0.82,
        border=(30, 170, 255),
        border_thickness=1,
    )
    paste_centered(frame, text, x1 + pill_w / 2, y1 + pill_h / 2)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class FingerCamApp:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.window = WINDOW_NAME
        self.renderer = TextRenderer()
        self._closed = False

        self.config, self.config_status = load_config()
        self.active_pack_index = 0
        self.packs: list[StickerPack] = []
        self._sound_player = shutil.which("paplay") or shutil.which("pw-play")
        self.apply_config(reset_pack=True)
        if args.no_mirror:
            self.mirror = False
        if args.sound:
            self.sound_on = True
        print(f"[FingerCam] Settings: {CONFIG_PATH.name} ({self.config_status})")
        print(f"[FingerCam] Theme: {self.theme_name}")
        print(
            f"[FingerCam] Sticker pack: {self.active_pack.name} "
            f"({len(self.packs)} packs, press T to switch)"
        )

        self.model_path = ensure_model()
        print("[FingerCam] Loading hand model...")
        self.tracker = HandTracker(self.model_path, max_hands=args.max_hands)

        self.video_mode = bool(args.video)
        if self.video_mode:
            print(f"[FingerCam] Opening video: {args.video}")
            self.capture = cv2.VideoCapture(str(args.video))
            if not self.capture.isOpened():
                print(f"[FingerCam] Could not open video: {args.video}")
                self.tracker.close()
                raise SystemExit(1)
            actual_w = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[FingerCam] Video ready at {actual_w}x{actual_h}.")
        else:
            print("[FingerCam] Opening camera...")
            self.capture = open_camera(args.camera, args.width, args.height)
            if self.capture is None:
                print_camera_help(args.camera)
                self.tracker.close()
                raise SystemExit(1)
            actual_w = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[FingerCam] Camera {args.camera} ready at {actual_w}x{actual_h}.")
        print(
            "[FingerCam] Controls: Q/Esc quit, H help, S snapshot (3s), "
            "C challenge, Y theme, L skeleton, M mirror, P sound, F fullscreen, "
            "T next pack (Shift+T previous), 1-9 select pack, R reload settings"
        )

        self.finger_seen: dict[tuple[int, int], float] = {}
        self.last_counts: dict[int, int] = {}
        self.show_help = False
        self.fullscreen = args.fullscreen
        self.toast_text = ""
        self.toast_color = (90, 200, 120)
        self.toast_until = 0.0
        self.fps = 0.0
        self._last_time = time.perf_counter()

        # Challenge mode (C).
        self.challenge_on = False
        self.challenge_target = 3
        self.challenge_score = 0
        self.challenge_streak = 0
        self.challenge_state = "playing"
        self.challenge_deadline = 0.0
        self.challenge_hold = 0.0
        self.challenge_next_at = 0.0

        # Countdown snapshot (S).
        self.snapshot_pending = False
        self.snapshot_at = 0.0
        self.snapshot_started = 0.0
        self.snapshot_flash_until = 0.0

    @property
    def active_pack(self) -> StickerPack:
        return self.packs[self.active_pack_index]

    def apply_config(self, reset_pack: bool = False) -> None:
        self.sticker_base = int(self.config["sticker_size"])
        self.show_labels = bool(self.config["show_labels"])
        self.show_count = bool(self.config["show_count"])
        self.show_skeleton = bool(self.config["show_skeleton"])
        self.mirror = bool(self.config["mirror"])
        self.sound_on = bool(self.config["sound"])
        self.night_light = bool(self.config.get("night_light", False))
        self.night_light_strength = max(
            0.1,
            min(
                1.0,
                float(self.config.get("night_light_strength", 0.65)),
            ),
        )
        self.theme_name = str(self.config.get("theme", "ليلي"))
        if self.theme_name not in THEMES:
            self.theme_name = "ليلي"
        self.theme = THEMES[self.theme_name]
        self.packs = build_sticker_packs(self.config)
        if reset_pack:
            index = int(self.config.get("active_pack", 0))
            if self.config.get("remember_pack", True):
                state = load_state()
                saved_name = state.get("active_pack_name")
                found = next(
                    (
                        i
                        for i, pack in enumerate(self.packs)
                        if pack.name == saved_name
                    ),
                    None,
                )
                if found is not None:
                    index = found
                saved_theme = state.get("theme")
                if saved_theme in THEMES:
                    self.theme_name = saved_theme
                    self.theme = THEMES[saved_theme]
                saved_night = state.get("night_light")
                if isinstance(saved_night, bool):
                    self.night_light = saved_night
                saved_strength = state.get("night_light_strength")
                if isinstance(saved_strength, (int, float)) and not isinstance(
                    saved_strength, bool
                ):
                    self.night_light_strength = max(
                        0.1, min(1.0, float(saved_strength))
                    )
            self.active_pack_index = index
        self.active_pack_index = max(
            0, min(self.active_pack_index, len(self.packs) - 1)
        )
        self.stickers = self.active_pack.stickers
        self.finger_colors = {
            finger: hex_to_bgr(
                self.config["finger_colors"][finger],
                DEFAULT_FINGER_COLORS_BGR[finger],
            )
            for finger in FINGER_KEYS
        }

    def set_pack(self, index: int, announce: bool = True) -> None:
        """Switch to another sticker pack without reloading the app."""
        if not self.packs:
            return
        self.active_pack_index = index % len(self.packs)
        self.stickers = self.active_pack.stickers
        if hasattr(self, "finger_seen"):
            self.finger_seen.clear()
        print(f"[FingerCam] Sticker pack: {self.active_pack.name}")
        self._save_state()
        self.play_sound("pack")
        if announce:
            self.toast(f"الحزمة: {self.active_pack.name}")

    def cycle_pack(self, step: int = 1) -> None:
        self.set_pack(self.active_pack_index + step)

    def select_pack(self, index: int) -> None:
        if 0 <= index < len(self.packs):
            self.set_pack(index)

    def _save_state(self) -> None:
        if not self.config.get("remember_pack", True):
            return
        save_state(
            {
                "active_pack_name": self.active_pack.name,
                "theme": self.theme_name,
                "night_light": self.night_light,
                "night_light_strength": self.night_light_strength,
            }
        )

    def cycle_theme(self, step: int = 1) -> None:
        current = THEME_ORDER.index(self.theme_name)
        self.theme_name = THEME_ORDER[(current + step) % len(THEME_ORDER)]
        self.theme = THEMES[self.theme_name]
        self._save_state()
        self.play_sound("pack")
        self.toast(f"الثيم: {self.theme_name}")
        print(f"[FingerCam] Theme: {self.theme_name}")

    def toggle_night_light(self) -> None:
        self.night_light = not self.night_light
        self._save_state()
        self.play_sound("pack")
        self.toast(
            "الإضاءة الليلية تعمل"
            if self.night_light
            else "الإضاءة الليلية متوقفة"
        )
        print(
            "[FingerCam] Night light: "
            f"{'on' if self.night_light else 'off'} "
            f"({int(round(self.night_light_strength * 100))}%)"
        )

    def adjust_night_light(self, step: float) -> None:
        self.night_light_strength = max(
            0.1, min(1.0, self.night_light_strength + step)
        )
        if not self.night_light:
            self.night_light = True
        self._save_state()
        self.toast(
            f"شدة الإضاءة الليلية: "
            f"{int(round(self.night_light_strength * 100))}%"
        )
        print(
            "[FingerCam] Night light strength: "
            f"{int(round(self.night_light_strength * 100))}%"
        )

    def start_challenge(self) -> None:
        self.challenge_on = True
        self.challenge_score = 0
        self.challenge_streak = 0
        self.challenge_state = "playing"
        self.challenge_hold = 0.0
        self.challenge_target = random.randint(1, 5)
        self.challenge_deadline = time.time() + CHALLENGE_DURATION
        self.play_sound("challenge")
        self.toast("وضع التحدي: ارفع الأصابع المطلوبة")
        print(
            f"[FingerCam] Challenge started: target={self.challenge_target}"
        )

    def stop_challenge(self) -> None:
        self.challenge_on = False
        self.toast(f"انتهى التحدي — النقاط: {self.challenge_score}")
        print(
            f"[FingerCam] Challenge stopped: score={self.challenge_score}"
        )

    def _next_challenge_target(self) -> int:
        choices = [number for number in range(1, 6) if number != self.challenge_target]
        return random.choice(choices)

    def update_challenge(
        self, count: int | None, now: float, delta: float
    ) -> None:
        if not self.challenge_on:
            return
        if self.challenge_state in ("success", "timeout"):
            if now >= self.challenge_next_at:
                self.challenge_target = self._next_challenge_target()
                self.challenge_deadline = now + CHALLENGE_DURATION
                self.challenge_state = "playing"
                self.challenge_hold = 0.0
            return
        if now >= self.challenge_deadline:
            self.challenge_state = "timeout"
            self.challenge_streak = 0
            self.challenge_next_at = now + 1.0
            self.play_sound("error")
            print("[FingerCam] Challenge timeout")
            return
        if count is not None and count == self.challenge_target:
            self.challenge_hold += delta
            if self.challenge_hold >= CHALLENGE_HOLD:
                points = 10 + self.challenge_streak * 2
                self.challenge_score += points
                self.challenge_streak += 1
                self.challenge_state = "success"
                self.challenge_next_at = now + 0.9
                self.play_sound("challenge")
                self.toast(f"صح! +{points}", (90, 200, 120))
                print(
                    f"[FingerCam] Challenge success: +{points}, "
                    f"score={self.challenge_score}"
                )
        else:
            self.challenge_hold = max(0.0, self.challenge_hold - delta * 2.0)

    def reload_config(self) -> None:
        config, status = load_config()
        if status == "error":
            self.toast("خطأ في ملف الإعدادات", (80, 80, 230))
            return
        self.config = config
        self.apply_config(reset_pack=False)
        self.finger_seen.clear()
        self.toast("تم تحديث الإعدادات", (90, 200, 120))
        print(f"[FingerCam] Settings reloaded from {CONFIG_PATH.name}.")

    def toast(self, text: str, color: tuple = (90, 200, 120)) -> None:
        self.toast_text = text
        self.toast_color = color
        self.toast_until = time.time() + 2.0

    def play_sound(self, kind: str = "count") -> None:
        if not self.sound_on:
            return
        try:
            if os.name == "nt":
                import winsound

                alias = WINDOWS_SOUNDS.get(kind, "SystemAsterisk")
                winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
                return
            path = SOUND_FILES.get(kind, SOUND_FILES["count"])
            if self._sound_player and os.path.exists(path):
                subprocess.Popen(
                    [self._sound_player, path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            print("\a", end="", flush=True)
        except Exception:
            pass

    def begin_snapshot(self, now: float) -> None:
        if self.snapshot_pending:
            self.toast("اللقطة قيد العد التنازلي")
            return
        self.snapshot_pending = True
        self.snapshot_started = now
        self.snapshot_at = now + 3.0
        self.toast("استعد... 3")
        print("[FingerCam] Snapshot countdown started.")

    def finish_snapshot(self, frame: np.ndarray, now: float) -> None:
        self.snapshot_pending = False
        self.snapshot_flash_until = now + 0.18
        self._write_snapshot(frame)
        self.play_sound("snapshot")

    def _write_snapshot(self, frame: np.ndarray) -> None:
        try:
            target = PICTURES_DIR
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError:
                target = SNAPSHOT_DIR
                target.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            path = target / f"fingercam_{stamp}.png"
            ok, buffer = cv2.imencode(".png", frame)
            if ok:
                # write_bytes handles non-ASCII Windows paths, unlike imwrite.
                path.write_bytes(buffer.tobytes())
                print(f"[FingerCam] Snapshot saved: {path}")
                self.toast(f"تم حفظ اللقطة في {target.name}", (90, 200, 120))
            else:
                print("[FingerCam] Could not encode the snapshot.")
        except Exception as exc:
            print(f"[FingerCam] Could not save the snapshot: {exc}")

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        value = cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL
        try:
            cv2.setWindowProperty(self.window, cv2.WND_PROP_FULLSCREEN, value)
        except Exception:
            pass

    def run(self) -> None:
        if platform.system() == "Windows":
            try:
                import ctypes

                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        cv2.namedWindow(self.window, cv2.WINDOW_NORMAL)
        if self.fullscreen:
            cv2.setWindowProperty(
                self.window, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
            )
        try:
            while True:
                ok, frame = self.capture.read()
                if not ok or frame is None:
                    if self.video_mode:
                        print("[FingerCam] End of video.")
                    else:
                        print("[FingerCam] Lost the camera signal.")
                    break
                if self.mirror:
                    frame = cv2.flip(frame, 1)
                height, width = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                observations = self.tracker.detect(rgb)
                now = time.time()
                delta = now - self._last_time
                self._last_time = now
                if delta > 1e-6:
                    instant = 1.0 / delta
                    self.fps = (
                        instant if self.fps <= 0.0 else self.fps * 0.9 + instant * 0.1
                    )
                current_keys: set[tuple[int, int]] = set()
                primary_count = None

                for hand_index, observation in enumerate(observations):
                    points = landmarks_to_points(observation.landmarks, width, height)
                    state = count_fingers(points)
                    if primary_count is None:
                        primary_count = state.count
                    draw_hand(
                        frame,
                        self.renderer,
                        points,
                        state,
                        colors=self.finger_colors,
                        stickers=self.stickers,
                        base_size=self.sticker_base,
                        show_labels=self.show_labels,
                        show_count=self.show_count,
                        now=now,
                        seen=self.finger_seen,
                        hand_key=hand_index,
                        show_skeleton=self.show_skeleton,
                        theme=self.theme,
                    )
                    for finger_index, is_up in enumerate(state.fingers):
                        if is_up:
                            current_keys.add((hand_index, finger_index))
                    previous = self.last_counts.get(hand_index)
                    if previous is not None and previous != state.count:
                        self.play_sound("count")
                    self.last_counts[hand_index] = state.count

                self.finger_seen = {
                    key: value
                    for key, value in self.finger_seen.items()
                    if key in current_keys
                }
                if not observations:
                    self.last_counts.clear()

                self.update_challenge(primary_count, now, delta)

                if primary_count is not None:
                    draw_frame_border(
                        frame, COUNT_COLORS.get(primary_count, COUNT_COLORS[5])
                    )
                else:
                    draw_no_hand(frame, self.renderer, now, theme=self.theme)

                draw_hud(frame, self.renderer, self.fps, theme=self.theme)
                draw_pack_badge(
                    frame, self.renderer, self.active_pack.name, theme=self.theme
                )
                draw_footer(frame, self.renderer, theme=self.theme)
                if self.challenge_on:
                    draw_challenge_panel(
                        frame,
                        self.renderer,
                        target=self.challenge_target,
                        score=self.challenge_score,
                        streak=self.challenge_streak,
                        remaining=max(0.0, self.challenge_deadline - now),
                        duration=CHALLENGE_DURATION,
                        state=self.challenge_state,
                        theme=self.theme,
                    )
                if now < self.toast_until:
                    draw_toast(
                        frame, self.renderer, self.toast_text, self.toast_color
                    )
                if self.show_help:
                    draw_help(
                        frame,
                        self.renderer,
                        self.active_pack.name,
                        theme=self.theme,
                    )

                if self.snapshot_pending:
                    remaining = self.snapshot_at - now
                    if remaining <= 0:
                        self.finish_snapshot(frame, now)
                    else:
                        draw_countdown(
                            frame, self.renderer, remaining, theme=self.theme
                        )
                if now < self.snapshot_flash_until:
                    flash = 0.55 * (self.snapshot_flash_until - now) / 0.18
                    white = np.full_like(frame, 255)
                    frame[:] = cv2.addWeighted(
                        frame, 1.0 - flash, white, flash, 0
                    )

                if self.night_light:
                    apply_night_light(frame, self.night_light_strength)
                    draw_night_badge(
                        frame,
                        self.renderer,
                        self.night_light_strength,
                        theme=self.theme,
                    )

                cv2.imshow(self.window, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    break
                if key in (ord("h"), ord("H")):
                    self.show_help = not self.show_help
                elif key in (ord("s"), ord("S")):
                    self.begin_snapshot(now)
                elif key in (ord("c"), ord("C")):
                    if self.challenge_on:
                        self.stop_challenge()
                    else:
                        self.start_challenge()
                elif key in (ord("y"), ord("Y")):
                    self.cycle_theme()
                elif key in (ord("l"), ord("L")):
                    self.show_skeleton = not self.show_skeleton
                elif key in (ord("m"), ord("M")):
                    self.mirror = not self.mirror
                elif key in (ord("p"), ord("P")):
                    self.sound_on = not self.sound_on
                    self.toast("الصوت يعمل" if self.sound_on else "الصوت متوقف")
                    if self.sound_on:
                        self.play_sound("pack")
                elif key in (ord("f"), ord("F")):
                    self.toggle_fullscreen()
                elif key == ord("t"):
                    self.cycle_pack(1)
                elif key == ord("T"):
                    self.cycle_pack(-1)
                elif ord("1") <= key <= ord("9"):
                    self.select_pack(key - ord("1"))
                elif key in (ord("r"), ord("R")):
                    self.reload_config()
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.capture.release()
        except Exception:
            pass
        try:
            self.tracker.close()
        except Exception:
            pass
        cv2.destroyAllWindows()
        for _ in range(3):
            cv2.waitKey(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FingerCam: per-finger meme/emoji sticker packs from your webcam."
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera index (default: 0). Try 1 for an external camera.",
    )
    parser.add_argument(
        "--width", type=int, default=1280, help="Requested camera width."
    )
    parser.add_argument(
        "--height", type=int, default=720, help="Requested camera height."
    )
    parser.add_argument(
        "--max-hands",
        type=int,
        default=2,
        choices=(1, 2),
        help="Maximum number of hands (default: 2).",
    )
    parser.add_argument(
        "--video",
        type=str,
        default=None,
        help="Run on a video file instead of the webcam (useful for testing).",
    )
    parser.add_argument(
        "--no-mirror",
        action="store_true",
        help="Do not mirror the camera image.",
    )
    parser.add_argument(
        "--sound",
        action="store_true",
        help="Play a sound when the finger count changes.",
    )
    parser.add_argument(
        "--fullscreen", action="store_true", help="Start in fullscreen."
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not ARABIC_SHAPING_AVAILABLE:
        print(
            "[FingerCam] Warning: Arabic shaping libraries are missing. "
            "Install requirements.txt for correct Arabic text."
        )
    app = FingerCamApp(args)
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n[FingerCam] Interrupted.")
    finally:
        app.close()


if __name__ == "__main__":
    main()
