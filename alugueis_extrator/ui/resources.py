"""Local image assets for the GUI (product logo and small drawn badges).

All images are either bundled with the application (the product logo) or
drawn at runtime with Pillow, so the interface never depends on a network
connection or on the development tree.
"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import sys
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont


PRODUCT_LOGO_FILENAME = "product_logo.png"


def assets_dir() -> Path:
    """Folder that holds the GUI assets in development and in the build."""

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "alugueis_extrator" / "ui" / "assets"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "assets"


def product_logo_path() -> Path:
    return assets_dir() / PRODUCT_LOGO_FILENAME


def _to_photo(master: tk.Misc, image: Image.Image) -> tk.PhotoImage:
    """Convert a Pillow image through PNG so only Tk's own loader is needed."""

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return tk.PhotoImage(master=master, data=base64.b64encode(buffer.getvalue()))


def load_product_logo(master: tk.Misc, height: int) -> tk.PhotoImage | None:
    """Load the project logo, trimmed of transparent margins only.

    The mark itself is not altered: aspect ratio, colors and transparency are
    preserved, and the image is never enlarged beyond its native resolution.
    """

    path = product_logo_path()
    try:
        with Image.open(path) as source:
            logo = source.convert("RGBA")
    except (OSError, ValueError):
        return None
    bbox = logo.getchannel("A").getbbox()
    if bbox:
        logo = logo.crop(bbox)
    height = max(1, min(height, logo.height))
    width = max(1, round(logo.width * height / logo.height))
    if (width, height) != logo.size:
        logo = logo.resize((width, height), Image.Resampling.LANCZOS)
    return _to_photo(master, logo)


# --------------------------------------------------------------------------
# Rounded-rectangle corners (antialiased) used by cards, fields and buttons.
# --------------------------------------------------------------------------

_SUPERSAMPLE = 4


def rounded_corner_images(
    master: tk.Misc, radius: int, fill: str, outline: str | None, background: str
) -> tuple[tk.PhotoImage, tk.PhotoImage, tk.PhotoImage, tk.PhotoImage]:
    """Return antialiased (top-left, top-right, bottom-left, bottom-right)."""

    toplevel = master.winfo_toplevel()
    cache = getattr(toplevel, "_ui_corner_cache", None)
    if cache is None:
        cache = {}
        setattr(toplevel, "_ui_corner_cache", cache)
    key = (radius, fill, outline, background)
    if key in cache:
        return cache[key]
    k = _SUPERSAMPLE
    size = 2 * radius + 2
    image = Image.new("RGB", (size * k, size * k), background)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, size * k - 1, size * k - 1),
        radius=radius * k,
        fill=fill,
        outline=outline if outline else None,
        width=k if outline else 0,
    )
    image = image.reduce(k)
    r = radius
    parts = (
        image.crop((0, 0, r, r)),
        image.crop((size - r, 0, size, r)),
        image.crop((0, size - r, r, size)),
        image.crop((size - r, size - r, size, size)),
    )
    photos = tuple(_to_photo(toplevel, part) for part in parts)
    cache[key] = photos  # type: ignore[assignment]
    return photos  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Small badges drawn with Pillow (own artwork; no third-party icon files).
# --------------------------------------------------------------------------


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _canvas(size: int, k: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def _finish(image: Image.Image, size: int) -> Image.Image:
    return image.resize((size, size), Image.Resampling.LANCZOS)


def draw_check_badge(size: int, color: str) -> Image.Image:
    k = _SUPERSAMPLE
    image, draw = _canvas(size, k)
    s = size * k
    draw.ellipse((0, 0, s - 1, s - 1), fill=color)
    w = max(k * 2, round(s * 0.09))
    draw.line(
        [(s * 0.28, s * 0.52), (s * 0.44, s * 0.67), (s * 0.73, s * 0.36)],
        fill="white",
        width=w,
        joint="curve",
    )
    return _finish(image, size)


def draw_warning_badge(size: int, color: str) -> Image.Image:
    k = _SUPERSAMPLE
    image, draw = _canvas(size, k)
    s = size * k
    m = s * 0.04
    draw.polygon([(s / 2, m + s * 0.04), (s - m, s - m - s * 0.06), (m, s - m - s * 0.06)], fill=color)
    bar_w = s * 0.09
    draw.rounded_rectangle(
        (s / 2 - bar_w / 2, s * 0.36, s / 2 + bar_w / 2, s * 0.66), radius=bar_w / 2, fill="white"
    )
    dot = s * 0.055
    draw.ellipse((s / 2 - dot, s * 0.73 - dot, s / 2 + dot, s * 0.73 + dot), fill="white")
    return _finish(image, size)


def draw_error_badge(size: int, color: str) -> Image.Image:
    k = _SUPERSAMPLE
    image, draw = _canvas(size, k)
    s = size * k
    draw.ellipse((0, 0, s - 1, s - 1), fill=color)
    bar_w = s * 0.1
    draw.rounded_rectangle(
        (s / 2 - bar_w / 2, s * 0.24, s / 2 + bar_w / 2, s * 0.58), radius=bar_w / 2, fill="white"
    )
    dot = s * 0.06
    draw.ellipse((s / 2 - dot, s * 0.72 - dot, s / 2 + dot, s * 0.72 + dot), fill="white")
    return _finish(image, size)


def draw_file_badge(size: int, color: str, label: str) -> Image.Image:
    """Document sheet with a folded corner and a short label (PDF / XLS)."""

    k = _SUPERSAMPLE
    image, draw = _canvas(size, k)
    s = size * k
    left, right, top, bottom = s * 0.14, s * 0.86, s * 0.04, s * 0.96
    fold = s * 0.24
    draw.polygon(
        [(left, top), (right - fold, top), (right, top + fold), (right, bottom), (left, bottom)],
        fill=color,
    )
    draw.polygon(
        [(right - fold, top), (right, top + fold), (right - fold, top + fold)],
        fill=(255, 255, 255, 110),
    )
    font = _font(max(6, round(s * 0.27)))
    box = draw.textbbox((0, 0), label, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.text(
        ((left + right) / 2 - tw / 2 - box[0], s * 0.62 - th / 2 - box[1]),
        label,
        font=font,
        fill="white",
    )
    return _finish(image, size)


def draw_excel_badge(size: int, color: str) -> Image.Image:
    k = _SUPERSAMPLE
    image, draw = _canvas(size, k)
    s = size * k
    draw.rounded_rectangle((s * 0.06, s * 0.06, s * 0.94, s * 0.94), radius=s * 0.16, fill=color)
    w = max(k * 2, round(s * 0.11))
    draw.line([(s * 0.32, s * 0.28), (s * 0.68, s * 0.72)], fill="white", width=w)
    draw.line([(s * 0.68, s * 0.28), (s * 0.32, s * 0.72)], fill="white", width=w)
    return _finish(image, size)


def draw_app_badge(size: int, color: str) -> Image.Image:
    """Blue rounded tile with a white report sheet (section and window icon)."""

    k = _SUPERSAMPLE
    image, draw = _canvas(size, k)
    s = size * k
    draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.24, fill=color)
    left, right, top, bottom = s * 0.29, s * 0.71, s * 0.2, s * 0.8
    fold = s * 0.13
    draw.polygon(
        [(left, top), (right - fold, top), (right, top + fold), (right, bottom), (left, bottom)],
        fill="white",
    )
    line_w = max(k, round(s * 0.045))
    for y in (0.45, 0.56, 0.67):
        draw.line([(left + s * 0.07, s * y), (right - s * 0.07, s * y)], fill=color, width=line_w)
    return _finish(image, size)


class BadgeSet:
    """PhotoImages for the badges, kept alive for the lifetime of the window."""

    def __init__(self, master: tk.Misc, px) -> None:
        from . import theme as t

        self.master = master
        self.success = _to_photo(master, draw_check_badge(px(34), t.SUCCESS))
        self.warning = _to_photo(master, draw_warning_badge(px(34), t.WARNING))
        self.error = _to_photo(master, draw_error_badge(px(34), t.DANGER))
        self.pdf = _to_photo(master, draw_file_badge(px(18), t.PDF_RED, "PDF"))
        self.pdf_large = _to_photo(master, draw_file_badge(px(26), t.PDF_RED, "PDF"))
        self.excel = _to_photo(master, draw_excel_badge(px(18), t.EXCEL_GREEN))
        self.excel_large = _to_photo(master, draw_excel_badge(px(30), t.EXCEL_GREEN))
        self.section = _to_photo(master, draw_app_badge(px(36), t.PRIMARY))
        self.window_icons = [
            _to_photo(master, draw_app_badge(size, t.PRIMARY)) for size in (16, 32, 48, 64)
        ]
