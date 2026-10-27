"""Small dependency-free (Pillow) chart helpers for evaluation artifacts.

Matplotlib is listed in requirements, but this build machine's Application
Control policy blocks its native ft2font DLL. Pillow is already a Streamlit
dependency and renders deterministic PNGs without native font extensions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1200
HEIGHT = 620
MARGIN_LEFT = 90
MARGIN_RIGHT = 40
MARGIN_TOP = 85
MARGIN_BOTTOM = 85
BACKGROUND = "#ffffff"
GRID = "#e4e7ec"
AXIS = "#475467"
TEXT = "#1f2933"
PALETTE = [
    "#175cd3",
    "#b42318",
    "#2f855a",
    "#b7791f",
    "#6941c6",
    "#0e7090",
    "#9b2c2c",
]

_FONT_PATHS = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _FONT_PATHS
    if bold:
        candidates = [
            path.replace("arial.ttf", "arialbd.ttf").replace("segoeui.ttf", "seguisb.ttf")
            for path in _FONT_PATHS
        ] + _FONT_PATHS
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _vertical_text(
    image: Image.Image, text: str, x: int, center_y: int
) -> None:
    font = _font(14)
    probe = ImageDraw.Draw(image)
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
    width, height = right - left + 4, bottom - top + 4
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((2, 2), text, fill=AXIS, font=font)
    rotated = layer.rotate(90, expand=True)
    image.paste(rotated, (x, center_y - rotated.height // 2), rotated)


def _canvas(title: str, ylabel: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.text((MARGIN_LEFT, 24), title, fill=TEXT, font=_font(24, bold=True))
    _vertical_text(
        image,
        ylabel,
        10,
        (MARGIN_TOP + (HEIGHT - MARGIN_BOTTOM)) // 2,
    )
    return image, draw


def _frame(
    draw: ImageDraw.ImageDraw,
    labels: Sequence[str],
    max_value: float,
    *,
    y_ticks: int = 5,
) -> tuple[int, int, int, int, float]:
    left, top = MARGIN_LEFT, MARGIN_TOP
    right, bottom = WIDTH - MARGIN_RIGHT, HEIGHT - MARGIN_BOTTOM
    clean_max = max(max_value, 1e-9)
    axis_max = max(clean_max * 1.12, 1.0)
    for tick in range(y_ticks + 1):
        value = axis_max * tick / y_ticks
        y = bottom - (bottom - top) * tick / y_ticks
        draw.line((left, y, right, y), fill=GRID, width=1)
        draw.text(
            (left - 12, y),
            f"{value:.2f}".rstrip("0").rstrip("."),
            fill=AXIS,
            font=_font(12),
            anchor="rm",
        )
    draw.line((left, top, left, bottom), fill=AXIS, width=2)
    draw.line((left, bottom, right, bottom), fill=AXIS, width=2)
    if labels:
        step = (right - left) / len(labels)
        for index, label in enumerate(labels):
            x = left + step * (index + 0.5)
            draw.text((x, bottom + 12), label, fill=AXIS, font=_font(13), anchor="ma")
    return left, top, right, bottom, axis_max


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def grouped_bar(
    path: Path,
    labels: Sequence[str],
    series: Sequence[tuple[str, Sequence[float], str]],
    *,
    title: str,
    ylabel: str,
    value_format: str = "{:.1f}",
) -> None:
    image, draw = _canvas(title, ylabel)
    left, top, right, bottom, axis_max = _frame(
        draw, labels, max(max(values) for _, values, _ in series)
    )
    group_width = (right - left) / max(len(labels), 1)
    bar_width = min(58.0, group_width * 0.74 / max(len(series), 1))
    for series_index, (_name, values, color) in enumerate(series):
        offset = (series_index - (len(series) - 1) / 2) * bar_width
        for index, value in enumerate(values):
            x = left + group_width * (index + 0.5) + offset
            y = bottom - (bottom - top) * value / axis_max
            draw.rectangle(
                (x - bar_width / 2 + 2, y, x + bar_width / 2 - 2, bottom),
                fill=color,
            )
            draw.text(
                (x, y - 4),
                value_format.format(value),
                fill=TEXT,
                font=_font(11, bold=True),
                anchor="mb",
            )
    # Legend
    legend_x = left
    for name, _values, color in series:
        draw.rectangle((legend_x, 58, legend_x + 16, 72), fill=color)
        draw.text((legend_x + 22, 58), name, fill=AXIS, font=_font(12))
        legend_x += 24 + int(draw.textlength(name, font=_font(12))) + 22
    _save(image, path)


def line_chart(
    path: Path,
    x_labels: Sequence[str],
    series: Sequence[tuple[str, Sequence[float], str]],
    *,
    title: str,
    ylabel: str,
    reference_value: float | None = None,
    reference_label: str = "",
) -> None:
    image, draw = _canvas(title, ylabel)
    max_value = max([max(values) for _, values, _ in series] + [reference_value or 0.0])
    left, top, right, bottom, axis_max = _frame(draw, x_labels, max_value)
    step = (right - left) / max(len(x_labels) - 1, 1)
    if reference_value is not None:
        y = bottom - (bottom - top) * reference_value / axis_max
        draw.line((left, y, right, y), fill="#b42318", width=2)
        draw.text(
            (right - 4, y - 6),
            reference_label,
            fill="#b42318",
            font=_font(12),
            anchor="rs",
        )
    for name, values, color in series:
        points = [
            (left + step * index, bottom - (bottom - top) * value / axis_max)
            for index, value in enumerate(values)
        ]
        if len(points) > 1:
            draw.line(points, fill=color, width=3)
        for x, y in points:
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color, outline=BACKGROUND, width=2)
        draw.text((points[-1][0] + 8, points[-1][1]), name, fill=color, font=_font(11))
    legend_x = left
    for name, _values, color in series:
        draw.rectangle((legend_x, 58, legend_x + 16, 72), fill=color)
        draw.text((legend_x + 22, 58), name, fill=AXIS, font=_font(12))
        legend_x += 24 + int(draw.textlength(name, font=_font(12))) + 22
    _save(image, path)


def simple_bar(
    path: Path,
    labels: Sequence[str],
    values: Sequence[float],
    colors: Sequence[str],
    *,
    title: str,
    ylabel: str,
    ranges: Sequence[tuple[float, float]] | None = None,
) -> None:
    image, draw = _canvas(title, ylabel)
    left, top, right, bottom, axis_max = _frame(draw, labels, max(values))
    group_width = (right - left) / max(len(labels), 1)
    bar_width = min(62.0, group_width * 0.55)
    for index, value in enumerate(values):
        x = left + group_width * (index + 0.5)
        y = bottom - (bottom - top) * value / axis_max
        draw.rectangle(
            (x - bar_width / 2, y, x + bar_width / 2, bottom),
            fill=colors[index],
        )
        draw.text(
            (x, y - 5),
            f"{value:.2f}".rstrip("0").rstrip("."),
            fill=TEXT,
            font=_font(13, bold=True),
            anchor="mb",
        )
        if ranges:
            low, high = ranges[index]
            low_y = bottom - (bottom - top) * low / axis_max
            high_y = bottom - (bottom - top) * high / axis_max
            draw.line((x, low_y, x, high_y), fill=TEXT, width=2)
            draw.line((x - 7, low_y, x + 7, low_y), fill=TEXT, width=2)
            draw.line((x - 7, high_y, x + 7, high_y), fill=TEXT, width=2)
    _save(image, path)
