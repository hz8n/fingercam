"""Unit tests for the pure finger-counting geometry.

Run with:  python test_hand_logic.py
No camera, MediaPipe or extra packages are required.
"""

from __future__ import annotations

import math
import unittest

from hand_logic import (
    FINGER_TIPS,
    INDEX_TIP,
    MIDDLE_MCP,
    MIDDLE_TIP,
    THUMB_CMC,
    THUMB_IP,
    THUMB_MCP,
    THUMB_TIP,
    WRIST,
    angle_degrees,
    count_fingers,
    extended_tips,
    hand_bounds,
    hand_center,
    landmarks_to_points,
)


class Point:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


def _rotate(points: list[Point], degrees: float, cx: float, cy: float) -> list[Point]:
    angle = math.radians(degrees)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    rotated = []
    for point in points:
        dx, dy = point.x - cx, point.y - cy
        rotated.append(
            Point(
                cx + dx * cos_a - dy * sin_a,
                cy + dx * sin_a + dy * cos_a,
            )
        )
    return rotated


def make_hand(
    extended: tuple[bool, bool, bool, bool, bool] = (True, True, True, True, True),
    rotation: float = 0.0,
) -> list[Point]:
    """Build a synthetic 21-landmark hand in a 1000x1000 coordinate space."""
    points = [Point(0.0, 0.0) for _ in range(21)]
    wrist = (500.0, 900.0)
    points[WRIST] = Point(*wrist)

    # Thumb: CMC, MCP, IP, TIP.
    points[THUMB_CMC] = Point(410, 780)
    points[THUMB_MCP] = Point(380, 720)
    if extended[0]:
        points[THUMB_IP] = Point(350, 675)
        points[THUMB_TIP] = Point(315, 635)
    else:
        # A straight thumb lying across the palm: the IP angle stays wide, so
        # the distance-to-pinky-MCP test is what rejects it.
        points[THUMB_IP] = Point(420, 690)
        points[THUMB_TIP] = Point(480, 650)

    # Index, middle, ring, pinky: MCP, PIP, DIP, TIP.
    bases = (
        ((420, 600), extended[1]),
        ((480, 590), extended[2]),
        ((540, 590), extended[3]),
        ((600, 600), extended[4]),
    )
    for offset, ((mcp_x, mcp_y), is_up) in enumerate(bases):
        mcp = 5 + offset * 4
        pip = mcp + 1
        dip = mcp + 2
        tip = mcp + 3
        points[mcp] = Point(mcp_x, mcp_y)
        if is_up:
            points[pip] = Point(mcp_x, mcp_y - 70)
            points[dip] = Point(mcp_x, mcp_y - 115)
            points[tip] = Point(mcp_x, mcp_y - 150)
        else:
            inward = 15 if mcp_x < 500 else -15
            points[pip] = Point(mcp_x, mcp_y - 45)
            points[dip] = Point(mcp_x + inward * 0.5, mcp_y - 20)
            points[tip] = Point(mcp_x + inward, mcp_y + 5)

    return _rotate(points, rotation, *wrist)


class AngleTests(unittest.TestCase):
    def test_straight_angle(self) -> None:
        self.assertAlmostEqual(
            angle_degrees((0, 0), (1, 0), (2, 0)), 180.0, places=4
        )

    def test_right_angle(self) -> None:
        self.assertAlmostEqual(
            angle_degrees((0, 1), (0, 0), (1, 0)), 90.0, places=4
        )

    def test_degenerate_angle(self) -> None:
        self.assertEqual(angle_degrees((0, 0), (0, 0), (1, 0)), 0.0)


class CountTests(unittest.TestCase):
    CASES = (
        ((True, True, True, True, True), 5),
        ((False, False, False, False, False), 0),
        ((True, False, False, False, False), 1),
        ((False, True, False, False, False), 1),
        ((False, True, True, False, False), 2),
        ((True, True, True, False, False), 3),
        ((False, True, True, True, True), 4),
        ((False, False, False, False, True), 1),
    )

    def test_cases(self) -> None:
        for extended, expected in self.CASES:
            with self.subTest(extended=extended):
                state = count_fingers(make_hand(extended))
                self.assertEqual(state.count, expected)
                self.assertEqual(state.fingers, extended)

    def test_rotation_invariance(self) -> None:
        for extended, expected in self.CASES:
            for rotation in (30, 90, 180, 270):
                with self.subTest(extended=extended, rotation=rotation):
                    state = count_fingers(make_hand(extended, rotation))
                    self.assertEqual(state.count, expected)
                    self.assertEqual(state.fingers, extended)

    def test_extended_tips(self) -> None:
        points = make_hand((False, True, True, False, False))
        state = count_fingers(points)
        self.assertEqual(extended_tips(points, state), [INDEX_TIP, MIDDLE_TIP])

    def test_fist_falls_back_to_middle_mcp(self) -> None:
        points = make_hand((False, False, False, False, False))
        state = count_fingers(points)
        self.assertEqual(extended_tips(points, state), [MIDDLE_MCP])

    def test_state_helpers(self) -> None:
        state = count_fingers(make_hand((True, True, False, False, False)))
        self.assertEqual(
            state.as_dict(),
            {
                "thumb": True,
                "index": True,
                "middle": False,
                "ring": False,
                "pinky": False,
            },
        )
        self.assertEqual(state.extended_names_ar(), ["الإبهام", "السبابة"])

    def test_too_few_landmarks(self) -> None:
        with self.assertRaises(ValueError):
            count_fingers(make_hand()[:20])


class ConversionTests(unittest.TestCase):
    def test_landmarks_to_points(self) -> None:
        class Landmark:
            def __init__(self, x: float, y: float) -> None:
                self.x = x
                self.y = y

        points = landmarks_to_points([Landmark(0.5, 0.25)], 1000, 800)
        self.assertEqual(points, [(500.0, 200.0)])

    def test_hand_center_and_bounds(self) -> None:
        points = make_hand()
        center = hand_center(points)
        bounds = hand_bounds(points)
        self.assertGreater(center[0], 0)
        self.assertGreater(center[1], 0)
        self.assertLess(bounds[0], bounds[2])
        self.assertLess(bounds[1], bounds[3])
        self.assertEqual(len(points), 21)
        self.assertEqual(len(FINGER_TIPS), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
