"""Pure geometry and finger-counting logic for FingerCam.

This module deliberately does not import MediaPipe so it can be unit-tested
without a camera. Landmark points must be *aspect-correct* (pixel) coordinates:
MediaPipe normalizes x and y independently, which distorts angles on non-square
camera frames.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

# MediaPipe Hands landmark indices.
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_DIP = 7
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_DIP = 11
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_DIP = 15
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20

FINGER_KEYS = ("thumb", "index", "middle", "ring", "pinky")
FINGER_NAMES_AR = ("الإبهام", "السبابة", "الوسطى", "البنصر", "الخنصر")
FINGER_TIPS = (THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
FINGER_PIPS = (THUMB_IP, INDEX_PIP, MIDDLE_PIP, RING_PIP, PINKY_PIP)

# (mcp, pip, tip) for the four non-thumb fingers.
_FINGER_JOINTS = (
    (INDEX_MCP, INDEX_PIP, INDEX_TIP),
    (MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP),
    (RING_MCP, RING_PIP, RING_TIP),
    (PINKY_MCP, PINKY_PIP, PINKY_TIP),
)

# Thresholds tuned for MediaPipe Hands. A finger is "up" when its middle joint
# is nearly straight AND its tip is clearly farther from the wrist than the PIP
# joint. Both tests together are rotation-invariant and reject curled fingers.
_PIP_STRAIGHT_ANGLE = 150.0
_TIP_PIP_DISTANCE_RATIO = 1.10
_THUMB_STRAIGHT_ANGLE = 140.0
_THUMB_PINKY_RATIO = 1.02


@dataclass(frozen=True)
class FingerState:
    """Which fingers are extended, in thumb..pinky order."""

    fingers: tuple[bool, ...]
    count: int

    def as_dict(self) -> dict[str, bool]:
        return dict(zip(FINGER_KEYS, self.fingers))

    def extended_names_ar(self) -> list[str]:
        return [name for name, up in zip(FINGER_NAMES_AR, self.fingers) if up]


def _xy(point) -> tuple[float, float]:
    """Accept either an (x, y) pair or an object with .x/.y attributes."""
    if hasattr(point, "x") and hasattr(point, "y"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def distance(a, b) -> float:
    ax, ay = _xy(a)
    bx, by = _xy(b)
    return math.hypot(ax - bx, ay - by)


def angle_degrees(a, vertex, c) -> float:
    """Return the angle ABC in degrees (the angle at ``vertex``)."""
    vx, vy = _xy(vertex)
    ax, ay = _xy(a)
    cx, cy = _xy(c)
    v1x, v1y = ax - vx, ay - vy
    v2x, v2y = cx - vx, cy - vy
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cosine = (v1x * v2x + v1y * v2y) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def landmarks_to_points(
    landmarks: Sequence, width: float, height: float
) -> list[tuple[float, float]]:
    """Convert normalized MediaPipe landmarks to pixel coordinates."""
    return [(float(lm.x) * width, float(lm.y) * height) for lm in landmarks]


def _finger_extended(points: Sequence, mcp: int, pip: int, tip: int) -> bool:
    pip_angle = angle_degrees(points[mcp], points[pip], points[tip])
    tip_distance = distance(points[tip], points[WRIST])
    pip_distance = distance(points[pip], points[WRIST])
    return (
        pip_angle > _PIP_STRAIGHT_ANGLE
        and tip_distance > pip_distance * _TIP_PIP_DISTANCE_RATIO
    )


def _thumb_extended(points: Sequence) -> bool:
    ip_angle = angle_degrees(points[THUMB_MCP], points[THUMB_IP], points[THUMB_TIP])
    tip_to_pinky = distance(points[THUMB_TIP], points[PINKY_MCP])
    mcp_to_pinky = distance(points[THUMB_MCP], points[PINKY_MCP])
    return (
        ip_angle > _THUMB_STRAIGHT_ANGLE
        and tip_to_pinky > mcp_to_pinky * _THUMB_PINKY_RATIO
    )


def count_fingers(points: Sequence) -> FingerState:
    """Detect which fingers are extended from 21 aspect-correct points."""
    if len(points) < 21:
        raise ValueError(f"Expected 21 hand landmarks, got {len(points)}")
    thumb = _thumb_extended(points)
    others = tuple(_finger_extended(points, *joints) for joints in _FINGER_JOINTS)
    fingers = (thumb,) + others
    return FingerState(fingers=fingers, count=sum(fingers))


def extended_tips(points: Sequence, state: FingerState) -> list[int]:
    """Landmark indices of extended fingertips (middle MCP for a fist)."""
    tips = [tip for tip, up in zip(FINGER_TIPS, state.fingers) if up]
    return tips or [MIDDLE_MCP]


def hand_center(points: Sequence) -> tuple[float, float]:
    xy = [_xy(point) for point in points]
    xs = [point[0] for point in xy]
    ys = [point[1] for point in xy]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def hand_bounds(points: Sequence) -> tuple[float, float, float, float]:
    """Return (left, top, right, bottom) of the hand landmarks."""
    xy = [_xy(point) for point in points]
    xs = [point[0] for point in xy]
    ys = [point[1] for point in xy]
    return min(xs), min(ys), max(xs), max(ys)
