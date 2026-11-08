"""Drawing and text helpers for FingerCam.

Public colour arguments are BGR, matching OpenCV. Text is rendered with Pillow
so Arabic is shaped and joined correctly, then composited back onto the frame.
"""

from __future__ import annotations

import math
import os
from typing import Optional, Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from PIL import features as _pil_features

    _HAS_RAQM = bool(_pil_features.check("raqm"))
except Exception:  # pragma: no cover - very old Pillow
    _HAS_RAQM = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    _HAS_MANUAL_BIDI = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_MANUAL_BIDI = False

# Pillow with Raqm shapes Arabic by itself. The manual reshaper is only a
# fallback for Pillow builds without Raqm.
ARABIC_SHAPING_AVAILABLE = _HAS_RAQM or _HAS_MANUAL_BIDI


_WIN_FONTS = "C:/Windows/Fonts"

_LATIN_FONTS = [
    f"{_WIN_FONTS}/segoeui.ttf",
    f"{_WIN_FONTS}/arial.ttf",
    f"{_WIN_FONTS}/tahoma.ttf",
    f"{_WIN_FONTS}/calibri.ttf",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

_ARABIC_FONTS = [
    f"{_WIN_FONTS}/tahoma.ttf",
    f"{_WIN_FONTS}/segoeui.ttf",
    f"{_WIN_FONTS}/arial.ttf",
    "/usr/share/fonts/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/noto/NotoSansArabicUI-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

_LATIN_BOLD_FONTS = [
    f"{_WIN_FONTS}/segoeuib.ttf",
    f"{_WIN_FONTS}/arialbd.ttf",
    f"{_WIN_FONTS}/tahomabd.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

_ARABIC_BOLD_FONTS = [
    f"{_WIN_FONTS}/tahomabd.ttf",
    f"{_WIN_FONTS}/segoeuib.ttf",
    f"{_WIN_FONTS}/arialbd.ttf",
    "/usr/share/fonts/noto/NotoSansArabic-Bold.ttf",
    "/usr/share/fonts/noto/NotoSansArabicUI-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

_EMOJI_FONTS = [
    f"{_WIN_FONTS}/seguiemj.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
]


def _first_existing(paths: Sequence[str]) -> Optional[str]:
    for path in paths:
        try:
            if os.path.exists(path):
                return path
        except OSError:
            continue
    return None


def _contains_arabic(text: str) -> bool:
    for char in text:
        code = ord(char)
        if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
            return True
    return False


def shape_arabic(text: str) -> str:
    """Manual shaping fallback for Pillow builds without Raqm."""
    if not _HAS_MANUAL_BIDI:
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


class TextRenderer:
    """Renders (optionally shaped Arabic) text and emoji to BGRA numpy arrays.

    Results are cached, so callers can render the same label every frame
    without paying the Pillow cost again.
    """

    def __init__(self) -> None:
        self.latin = _first_existing(_LATIN_FONTS)
        self.arabic = _first_existing(_ARABIC_FONTS) or self.latin
        self.latin_bold = _first_existing(_LATIN_BOLD_FONTS) or self.latin
        self.arabic_bold = _first_existing(_ARABIC_BOLD_FONTS) or self.arabic
        self.emoji = _first_existing(_EMOJI_FONTS)
        self._cache: dict[tuple, Optional[np.ndarray]] = {}

    def _font_path(self, text: str, bold: bool, emoji: bool) -> Optional[str]:
        if emoji:
            return self.emoji
        if _contains_arabic(text):
            return self.arabic_bold if bold else self.arabic
        return self.latin_bold if bold else self.latin

    def _load_font(self, path: Optional[str], size: int):
        """Return (font, scale). scale < 1 when a bitmap font had to be shrunk."""
        if not path:
            try:
                return ImageFont.load_default(size=size), 1.0
            except Exception:
                return ImageFont.load_default(), 1.0
        try:
            return ImageFont.truetype(path, size), 1.0
        except Exception:
            # Noto Color Emoji and similar bitmap fonts only accept their
            # native size, so render large and scale down.
            native = 109
            try:
                return ImageFont.truetype(path, native), size / native
            except Exception:
                return None, 1.0

    def render(
        self,
        text: str,
        size: int,
        color: tuple = (255, 255, 255),
        *,
        bold: bool = False,
        emoji: bool = False,
        shape: bool = True,
    ) -> Optional[np.ndarray]:
        """Render text to a BGRA array (None if the font cannot draw it)."""
        if not text:
            return None
        size = max(6, int(size))
        key = (text, size, tuple(color), bool(bold), bool(emoji), bool(shape))
        if key in self._cache:
            return self._cache[key]

        path = self._font_path(text, bold, emoji)
        font, font_scale = self._load_font(path, size)
        if font is None:
            self._cache[key] = None
            return None

        if len(color) == 4:
            b, g, r, a = color
        else:
            b, g, r = color
            a = 255
        fill = (int(r), int(g), int(b), int(a))

        arabic = _contains_arabic(text)
        if emoji:
            display = text
            embedded = True
            text_kwargs: dict = {}
        elif arabic and shape and not _HAS_RAQM:
            display = shape_arabic(text)
            embedded = False
            text_kwargs = {}
        else:
            display = text
            embedded = False
            text_kwargs = {"direction": "rtl"} if (arabic and shape and _HAS_RAQM) else {}

        def draw_once(use_embedded: bool, use_kwargs: bool) -> Image.Image:
            bbox = font.getbbox(display)
            text_w = max(1, bbox[2] - bbox[0])
            text_h = max(1, bbox[3] - bbox[1])
            pad = 4
            image = Image.new("RGBA", (text_w + pad * 2, text_h + pad * 2), (0, 0, 0, 0))
            drawer = ImageDraw.Draw(image)
            kwargs = text_kwargs if use_kwargs else {}
            if use_embedded:
                drawer.text(
                    (pad - bbox[0], pad - bbox[1]),
                    display,
                    font=font,
                    embedded_color=True,
                    **kwargs,
                )
            else:
                drawer.text(
                    (pad - bbox[0], pad - bbox[1]),
                    display,
                    font=font,
                    fill=fill,
                    **kwargs,
                )
            if font_scale != 1.0:
                image = image.resize(
                    (
                        max(1, int(image.width * font_scale)),
                        max(1, int(image.height * font_scale)),
                    ),
                    Image.Resampling.LANCZOS,
                )
            return image

        try:
            image = draw_once(embedded, True)
        except Exception:
            # Last chance: some emoji fonts fail with embedded colour but work
            # as normal monochrome glyphs; some old Pillow builds reject the
            # direction keyword.
            try:
                image = draw_once(False, False)
            except Exception:
                self._cache[key] = None
                return None
        try:
            array = cv2.cvtColor(np.array(image), cv2.COLOR_RGBA2BGRA)
        except Exception:
            self._cache[key] = None
            return None

        if len(self._cache) > 400:
            self._cache.clear()
        self._cache[key] = array
        return array


def paste_rgba(dst: np.ndarray, src: Optional[np.ndarray], x: int, y: int) -> None:
    """Alpha-composite a BGRA image onto a BGR frame at (x, y)."""
    if src is None:
        return
    src_h, src_w = src.shape[:2]
    dst_h, dst_w = dst.shape[:2]
    x, y = int(x), int(y)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst_w, x + src_w), min(dst_h, y + src_h)
    if x1 <= x0 or y1 <= y0:
        return
    sx0, sy0 = x0 - x, y0 - y
    crop = src[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)]
    alpha = crop[..., 3:4].astype(np.float32) / 255.0
    roi = dst[y0:y1, x0:x1].astype(np.float32)
    blended = roi * (1.0 - alpha) + crop[..., :3].astype(np.float32) * alpha
    dst[y0:y1, x0:x1] = blended.astype(np.uint8)


def paste_centered(
    dst: np.ndarray, src: Optional[np.ndarray], cx: float, cy: float
) -> None:
    if src is None:
        return
    paste_rgba(
        dst,
        src,
        int(round(cx - src.shape[1] / 2.0)),
        int(round(cy - src.shape[0] / 2.0)),
    )


def _fill_round_rect(
    img: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    radius: int,
    color: tuple,
) -> None:
    x2 -= 1
    y2 -= 1
    if x2 <= x1 or y2 <= y1:
        return
    radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    if radius == 0:
        cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)
        return
    cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1)
    cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1)
    for cx, cy in (
        (x1 + radius, y1 + radius),
        (x2 - radius, y1 + radius),
        (x1 + radius, y2 - radius),
        (x2 - radius, y2 - radius),
    ):
        cv2.circle(img, (cx, cy), radius, color, -1, cv2.LINE_AA)


def draw_panel(
    frame: np.ndarray,
    rect: tuple[int, int, int, int],
    *,
    radius: int = 18,
    fill: tuple = (18, 18, 26),
    alpha: float = 0.78,
    border: Optional[tuple] = None,
    border_thickness: int = 1,
) -> None:
    """Draw a translucent rounded panel, clipped to the frame."""
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = (int(v) for v in rect)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        return
    overlay = np.zeros((y2 - y1, x2 - x1, 3), dtype=np.uint8)
    radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    if border is not None and border_thickness > 0:
        _fill_round_rect(overlay, 0, 0, x2 - x1, y2 - y1, radius, border)
        inset = max(1, border_thickness)
        _fill_round_rect(
            overlay,
            inset,
            inset,
            x2 - x1 - inset,
            y2 - y1 - inset,
            max(0, radius - inset),
            fill,
        )
    else:
        _fill_round_rect(overlay, 0, 0, x2 - x1, y2 - y1, radius, fill)
    roi = frame[y1:y2, x1:x2]
    frame[y1:y2, x1:x2] = cv2.addWeighted(overlay, alpha, roi, 1.0 - alpha, 0)


def draw_glow_circle(
    frame: np.ndarray, center: tuple, radius: int, color: tuple, alpha: float
) -> None:
    """Draw a soft filled circle with transparency (corners stay untouched)."""
    height, width = frame.shape[:2]
    cx, cy = int(center[0]), int(center[1])
    radius = int(radius)
    x1, y1 = max(0, cx - radius), max(0, cy - radius)
    x2, y2 = min(width, cx + radius + 1), min(height, cy + radius + 1)
    if x2 <= x1 or y2 <= y1:
        return
    overlay = np.zeros((y2 - y1, x2 - x1, 3), dtype=np.uint8)
    mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
    local = (cx - x1, cy - y1)
    cv2.circle(overlay, local, radius, color, -1, cv2.LINE_AA)
    cv2.circle(mask, local, radius, 255, -1, cv2.LINE_AA)
    mask_f = (mask.astype(np.float32) / 255.0 * alpha)[..., None]
    roi = frame[y1:y2, x1:x2].astype(np.float32)
    blended = roi * (1.0 - mask_f) + overlay.astype(np.float32) * mask_f
    frame[y1:y2, x1:x2] = blended.astype(np.uint8)


def draw_ring(
    frame: np.ndarray,
    center: tuple,
    radius: int,
    color: tuple,
    *,
    thickness: int = 2,
    alpha: float = 1.0,
) -> None:
    """Draw a thin ring, optionally translucent."""
    if alpha >= 0.999:
        cv2.circle(
            frame,
            (int(center[0]), int(center[1])),
            int(radius),
            color,
            thickness,
            cv2.LINE_AA,
        )
        return
    height, width = frame.shape[:2]
    cx, cy = int(center[0]), int(center[1])
    radius = int(radius)
    margin = radius + thickness + 3
    x1, y1 = max(0, cx - margin), max(0, cy - margin)
    x2, y2 = min(width, cx + margin), min(height, cy + margin)
    if x2 <= x1 or y2 <= y1:
        return
    overlay = np.zeros((y2 - y1, x2 - x1, 3), dtype=np.uint8)
    mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
    local = (cx - x1, cy - y1)
    cv2.circle(overlay, local, radius, color, thickness, cv2.LINE_AA)
    cv2.circle(mask, local, radius, 255, thickness, cv2.LINE_AA)
    mask_f = (mask.astype(np.float32) / 255.0 * alpha)[..., None]
    roi = frame[y1:y2, x1:x2].astype(np.float32)
    blended = roi * (1.0 - mask_f) + overlay.astype(np.float32) * mask_f
    frame[y1:y2, x1:x2] = blended.astype(np.uint8)


def draw_sticker_bubble(
    frame: np.ndarray,
    center: tuple,
    radius: int,
    color: tuple,
    content: Optional[np.ndarray],
) -> None:
    """A dark floating bubble with a coloured ring and an emoji/image inside."""
    draw_glow_circle(frame, center, radius + 9, color, 0.20)
    draw_glow_circle(frame, center, radius, (14, 14, 22), 0.78)
    cv2.circle(
        frame,
        (int(center[0]), int(center[1])),
        int(radius),
        color,
        3,
        cv2.LINE_AA,
    )
    paste_centered(frame, content, center[0], center[1])


def draw_connector(
    frame: np.ndarray, tip: tuple, center: tuple, radius: int, color: tuple
) -> None:
    """Thin line + dot linking a fingertip to its sticker."""
    tx, ty = int(tip[0]), int(tip[1])
    cx, cy = int(center[0]), int(center[1])
    dx, dy = cx - tx, cy - ty
    length = math.hypot(dx, dy)
    if length > radius + 6:
        ux, uy = dx / length, dy / length
        start = (int(tx + ux * 5), int(ty + uy * 5))
        end = (int(cx - ux * (radius + 3)), int(cy - uy * (radius + 3)))
        cv2.line(frame, start, end, color, 2, cv2.LINE_AA)
    cv2.circle(frame, (tx, ty), 5, color, -1, cv2.LINE_AA)
    cv2.circle(frame, (tx, ty), 5, (255, 255, 255), 1, cv2.LINE_AA)


def draw_keycap(
    frame: np.ndarray,
    renderer: TextRenderer,
    rect: tuple[int, int, int, int],
    key: str,
    *,
    font_size: int = 14,
    fill: tuple = (48, 48, 64),
    border: tuple = (115, 115, 140),
) -> None:
    x1, y1, x2, y2 = rect
    draw_panel(
        frame,
        rect,
        radius=8,
        fill=fill,
        alpha=0.95,
        border=border,
        border_thickness=1,
    )
    image = renderer.render(key, font_size, color=(255, 255, 255), bold=True, shape=False)
    paste_centered(frame, image, (x1 + x2) / 2, (y1 + y2) / 2)


_IMAGE_CACHE: dict[tuple, Optional[np.ndarray]] = {}


def load_image_rgba(path, max_size: int) -> Optional[np.ndarray]:
    """Load an image (PNG/JPG/WebP/...) as BGRA, scaled to fit max_size."""
    path = os.fspath(path)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    key = (path, mtime, int(max_size))
    if key in _IMAGE_CACHE:
        return _IMAGE_CACHE[key]
    try:
        data = np.fromfile(path, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    except Exception:
        image = None
    if image is None:
        _IMAGE_CACHE[key] = None
        return None
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    elif image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        return None
    scale = min(max_size / float(width), max_size / float(height))
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    image = cv2.resize(image, (new_w, new_h), interpolation=interpolation)
    if len(_IMAGE_CACHE) > 64:
        _IMAGE_CACHE.clear()
    _IMAGE_CACHE[key] = image
    return image


def hex_to_bgr(value: str, fallback: tuple) -> tuple:
    """Convert '#RRGGBB' to a BGR tuple, returning fallback on bad input."""
    if not isinstance(value, str):
        return fallback
    text = value.strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
    except ValueError:
        return fallback
    return (b, g, r)


def draw_sparkle(
    frame: np.ndarray, center: tuple, size: float, color: tuple, thickness: int = 2
) -> None:
    x, y = int(center[0]), int(center[1])
    size = max(3, int(size))
    cv2.line(frame, (x - size, y), (x + size, y), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (x, y - size), (x, y + size), color, thickness, cv2.LINE_AA)
    cv2.circle(frame, (x, y), max(2, size // 4), (255, 255, 255), -1, cv2.LINE_AA)


def draw_frame_border(frame: np.ndarray, color: tuple, thickness: int = 4) -> None:
    height, width = frame.shape[:2]
    cv2.rectangle(
        frame, (2, 2), (width - 3, height - 3), color, thickness, cv2.LINE_AA
    )
