"""Dependency-light PNG figures for reproducible report outputs."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "B1": "#355C7D",
    "B2": "#6C5B7B",
    "B2q": "#2A9D8F",
    "B3": "#99B898",
    "BID": "#E56B6F",
}


def _font(size: int = 14) -> ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def _series_label(row: Mapping[str, object], experiment: str) -> str:
    policy = str(row["policy"])
    if experiment == "exp4_communication" and policy == "BID":
        return f"BID/{row['communication']}"
    if experiment == "exp5_demand_knowledge" and policy == "BID":
        return f"BID/{row['demand_condition']}"
    return policy


def _series_color(label: str) -> str:
    if label.startswith("BID/"):
        suffix = label.split("/", 1)[1]
        return {"full": "#E56B6F", "radius-limited": "#C44569", "lossy": "#F08A5D", "none": "#8F3985", "learned": "#E56B6F", "oracle": "#F08A5D"}.get(suffix, COLORS["BID"])
    return COLORS.get(label, "#666666")


def plot_metric(
    rows: Sequence[Mapping[str, object]],
    experiment: str,
    metric: str,
    output: str | Path,
    title: str | None = None,
    y_label: str | None = None,
) -> bool:
    """Draw an x-level grouped line chart with percentile-bootstrap error bars."""
    selected = [row for row in rows if row.get("experiment") == experiment and row.get("metric") == metric]
    selected = [row for row in selected if row.get("mean") is not None]
    if not selected:
        return False
    levels = list(dict.fromkeys(str(row["level"]) for row in selected))
    labels = sorted({_series_label(row, experiment) for row in selected})
    data: dict[tuple[str, str], Mapping[str, object]] = {
        (str(row["level"]), _series_label(row, experiment)): row for row in selected
    }
    values = [
        float(row[key])
        for row in selected
        for key in ("ci95_low", "ci95_high", "mean")
        if row.get(key) is not None
    ]
    y_min, y_max = min(values), max(values)
    if y_min == y_max:
        padding = max(abs(y_min) * 0.08, 0.05)
    else:
        padding = (y_max - y_min) * 0.12
    y_min -= padding
    y_max += padding
    if metric == "service_rate":
        y_min = max(0.0, y_min)
        y_max = min(1.0, y_max)
    elif metric in {"mean_coverage", "utilization"}:
        y_min = max(0.0, y_min)
        y_max = min(1.0, y_max)
    if y_max <= y_min:
        y_max = y_min + 1.0

    scale = 2
    width, height = 1000, 590
    image = Image.new("RGB", (width * scale, height * scale), "white")
    draw = ImageDraw.Draw(image)

    def p(x: float, y: float) -> tuple[int, int]:
        return (round(x * scale), round(y * scale))

    left, right, top, bottom = 92, 34, 62, 135
    plot_width = width - left - right
    plot_height = height - top - bottom
    font = _font(16 * scale)
    small = _font(13 * scale)
    draw.text(p(left, 16), title or f"{experiment}: {metric}", fill="#172B4D", font=_font(22 * scale))
    draw.line((p(left, top), p(left, height - bottom), p(width - right, height - bottom)), fill="#2D3748", width=2 * scale)
    ticks = 5
    for index in range(ticks + 1):
        fraction = index / ticks
        y_value = y_min + fraction * (y_max - y_min)
        y_pixel = height - bottom - fraction * plot_height
        draw.line((p(left, y_pixel), p(width - right, y_pixel)), fill="#D9E0E8", width=scale)
        draw.text(p(6, y_pixel - 8), f"{y_value:.2f}", fill="#394B59", font=small)
    if len(levels) == 1:
        x_positions = {levels[0]: left + plot_width / 2}
    else:
        x_positions = {
            level: left + index * plot_width / (len(levels) - 1)
            for index, level in enumerate(levels)
        }
    y_span = y_max - y_min

    def y_pixel(value: float) -> float:
        return height - bottom - (value - y_min) / y_span * plot_height

    for level, x in x_positions.items():
        draw.text(p(x, height - bottom + 15), level, fill="#394B59", font=small, anchor="ma")
    for label in labels:
        points = []
        for level in levels:
            row = data.get((level, label))
            if row is None:
                continue
            mean = float(row["mean"])
            low = float(row["ci95_low"])
            high = float(row["ci95_high"])
            x = x_positions[level]
            y = y_pixel(mean)
            points.append((x, y))
            color = _series_color(label)
            x1, x2 = p(x, y_pixel(high)), p(x, y_pixel(low))
            draw.line((x1[0], x1[1], x2[0], x2[1]), fill=color, width=3 * scale)
            draw.line((p(x - 6, y_pixel(high)), p(x + 6, y_pixel(high))), fill=color, width=2 * scale)
            draw.line((p(x - 6, y_pixel(low)), p(x + 6, y_pixel(low))), fill=color, width=2 * scale)
            draw.ellipse((p(x - 5, y - 5), p(x + 5, y + 5)), fill=color, outline="white", width=scale)
        if len(points) > 1:
            draw.line([p(*point) for point in points], fill=_series_color(label), width=3 * scale)
    legend_y = height - 42
    x = left
    for label in labels:
        color = _series_color(label)
        draw.line((p(x, legend_y + 8), p(x + 22, legend_y + 8)), fill=color, width=4 * scale)
        draw.text(p(x + 28, legend_y), label, fill="#253858", font=small)
        x += 28 + draw.textlength(label, font=small) / scale + 24
    draw.text(p(width - right, 16), y_label or metric, fill="#52606D", font=small, anchor="ra")
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return True


def create_experiment_plots(rows: Sequence[Mapping[str, object]], output_dir: str | Path) -> tuple[Path, ...]:
    output_dir = Path(output_dir)
    experiments = sorted({str(row["experiment"]) for row in rows})
    outputs = []
    safe = re.compile(r"[^A-Za-z0-9_-]+")
    for experiment in experiments:
        for metric, label in (
            ("service_rate", "Service rate"),
            ("b3_cost_gap_relative", "Signed relative cost gap to heuristic B3"),
        ):
            filename = safe.sub("_", f"{experiment}_{metric}").strip("_") + ".png"
            target = output_dir / filename
            if plot_metric(rows, experiment, metric, target, y_label=label):
                outputs.append(target)
    # A contact sheet is a genuine snapshot of the generated result figures.
    if outputs:
        thumbnails = []
        for path in outputs:
            with Image.open(path) as chart:
                thumb = chart.convert("RGB")
                thumb.thumbnail((500, 295), Image.Resampling.LANCZOS)
                thumbnails.append((path.name, thumb.copy()))
        cols = 2
        cell_w, cell_h = 520, 330
        rows_count = (len(thumbnails) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w, rows_count * cell_h), "#F3F5F7")
        draw = ImageDraw.Draw(sheet)
        for index, (name, thumb) in enumerate(thumbnails):
            x = (index % cols) * cell_w + 10
            y = (index // cols) * cell_h + 25
            sheet.paste(thumb, (x, y))
            draw.text((x, y - 19), name, fill="#172B4D", font=_font(12))
        contact = output_dir / "results_contact_sheet.png"
        sheet.save(contact, format="PNG", optimize=True)
        outputs.append(contact)
    return tuple(outputs)

