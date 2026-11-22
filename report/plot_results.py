"""Regenerate high-resolution report figures and rates from completed CSVs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from ambulance_dispatch.metrics import bootstrap_mean_interval, paired_b3_gaps, summarize_by  # noqa: E402


COLORS = {
    "B1": "#35618A",
    "B2": "#8064A2",
    "B2q": "#2A9D8F",
    "B3": "#4E9A76",
    "BID": "#D64F61",
    "BID/full": "#D64F61",
    "BID/radius-limited": "#793B86",
    "BID/lossy": "#ED8B36",
    "BID/none": "#B02E65",
    "BID/learned": "#D64F61",
    "BID/oracle": "#ED8B36",
}

LEVEL_ORDER = {
    "exp1_ambulance_count": ["n=3", "n=5", "n=7", "n=10"],
    "exp2_total_demand": ["low:2.5/h", "medium:5/h", "high:10/h"],
    "exp3_demand_pattern": ["uniform", "hotspots", "shifting"],
    "exp4_communication": ["full", "radius-limited", "lossy", "none"],
    "exp5_demand_knowledge": ["learned", "oracle"],
    "exp6_criticality_mix": ["low-heavy", "balanced", "high-heavy"],
    "exp7_weight_tradeoff": ["coverage-light", "balanced", "coverage-heavy"],
    "exp8_weight_sensitivity": [
        "alpha=0.5", "alpha=1", "alpha=2",
        "beta=4", "beta=8", "beta=16",
        "gamma=4", "gamma=8", "gamma=16",
    ],
}

WEIGHT_AXIS_ORDER = {
    "alpha": ["alpha=0.5", "alpha=1", "alpha=2"],
    "beta": ["beta=4", "beta=8", "beta=16"],
    "gamma": ["gamma=4", "gamma=8", "gamma=16"],
}


def font(size: int) -> ImageFont.ImageFont:
    for path in (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
    return ImageFont.load_default()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def derive_rate_summaries(raw: list[dict[str, str]], resamples: int = 2000) -> list[dict[str, Any]]:
    derived = []
    for row in raw:
        n = int(row["n_incidents"])
        exp_rate = float(row.get("expired_rate", int(row["expired"]) / n if n else 0.0))
        dup_rate = float(row.get("duplicate_rate", int(row["duplicate_incidents"]) / n if n else 0.0))
        item = {
            **row,
            "duplicate_dispatch_rate": dup_rate,
            "expired_dispatch_rate": exp_rate,
            "missed_dispatch_rate": exp_rate,
        }
        derived.append(item)
    group_keys = ("experiment", "level", "policy", "communication", "demand_condition")
    summaries = []
    for metric in ("duplicate_dispatch_rate", "expired_dispatch_rate", "missed_dispatch_rate"):
        summaries.extend(summarize_by(derived, group_keys, metric, resamples=resamples, seed=491))
    return summaries


def label_for(row: dict[str, Any], experiment: str) -> str:
    policy = str(row["policy"])
    if experiment == "exp4_communication" and policy == "BID":
        return f"BID/{row['communication']}"
    if experiment == "exp5_demand_knowledge" and policy == "BID":
        return f"BID/{row['demand_condition']}"
    return policy


def chart(
    rows: list[dict[str, Any]],
    experiment: str,
    metric: str,
    output: Path,
    title: str,
    percent: bool = False,
    weight_factor: str | None = None,
) -> bool:
    selected = [
        r for r in rows
        if r.get("experiment") == experiment and r.get("metric") == metric
        and r.get("mean") not in (None, "")
        and (weight_factor is None or r.get("weight_factor") == weight_factor)
    ]
    if not selected:
        return False
    level_present = {str(r["level"]) for r in selected}
    preferred = WEIGHT_AXIS_ORDER[weight_factor] if weight_factor else LEVEL_ORDER.get(experiment, [])
    levels = [level for level in preferred if level in level_present]
    levels.extend(sorted(level_present - set(levels)))
    labels = sorted({label_for(row, experiment) for row in selected})
    data = {(str(row["level"]), label_for(row, experiment)): row for row in selected}
    values = [float(row[key]) for row in selected for key in ("mean", "ci95_low", "ci95_high") if row.get(key) not in (None, "")]
    low, high = min(values), max(values)
    pad = max((high - low) * 0.12, 0.02 if percent else max(abs(low), abs(high), 1.0) * 0.05)
    y_min, y_max = low - pad, high + pad
    if percent:
        y_min = max(0.0, y_min)
        y_max = min(1.0, y_max)
    if y_max <= y_min:
        y_max = y_min + 1.0

    width, height, scale = 1500, 920, 2
    canvas = Image.new("RGB", (width * scale, height * scale), "white")
    draw = ImageDraw.Draw(canvas)
    title_font = font(28 * scale)
    axis_font = font(20 * scale)
    small_font = font(17 * scale)
    left, right, top, bottom = 128, 46, 92, 180
    plot_w, plot_h = width - left - right, height - top - bottom

    def p(x: float, y: float) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    def yp(value: float) -> float:
        return height - bottom - (value - y_min) / (y_max - y_min) * plot_h

    draw.text(p(left, 28), title, fill="#17324D", font=title_font)
    draw.line((p(left, top), p(left, height - bottom), p(width - right, height - bottom)), fill="#243746", width=3 * scale)
    for tick in range(6):
        value = y_min + tick * (y_max - y_min) / 5
        y = yp(value)
        label = f"{100*value:.1f}%" if percent else f"{value:.2f}"
        draw.line((p(left, y), p(width - right, y)), fill="#DDE4EA", width=scale)
        draw.text(p(8, y - 12), label, fill="#3F5263", font=axis_font)
    if len(levels) == 1:
        x_pos = {levels[0]: left + plot_w / 2}
    else:
        x_pos = {level: left + i * plot_w / (len(levels) - 1) for i, level in enumerate(levels)}
    for level, x in x_pos.items():
        draw.text(p(x, height - bottom + 24), level, fill="#384D5C", font=small_font, anchor="ma")
    draw.text(p(left + plot_w / 2, height - 112), "Scenario level", fill="#3F5263", font=axis_font, anchor="ma")
    for label in labels:
        points = []
        color = COLORS.get(label, COLORS.get(label.split("/")[0], "#68727A"))
        for level in levels:
            row = data.get((level, label))
            if row is None:
                continue
            x = x_pos[level]
            mean, ci_low, ci_high = (float(row[key]) for key in ("mean", "ci95_low", "ci95_high"))
            points.append((x, yp(mean)))
            draw.line((p(x, yp(ci_high)), p(x, yp(ci_low))), fill=color, width=3 * scale)
            draw.line((p(x - 8, yp(ci_high)), p(x + 8, yp(ci_high))), fill=color, width=2 * scale)
            draw.line((p(x - 8, yp(ci_low)), p(x + 8, yp(ci_low))), fill=color, width=2 * scale)
            draw.ellipse((p(x - 7, yp(mean) - 7), p(x + 7, yp(mean) + 7)), fill=color, outline="white", width=scale)
        if len(points) > 1:
            draw.line([p(x, y) for x, y in points], fill=color, width=4 * scale)
    legend_x = left
    legend_y = height - 60
    for label in labels:
        color = COLORS.get(label, COLORS.get(label.split("/")[0], "#68727A"))
        draw.line((p(legend_x, legend_y + 8), p(legend_x + 38, legend_y + 8)), fill=color, width=4 * scale)
        draw.text(p(legend_x + 48, legend_y - 4), label, fill="#263B4C", font=small_font)
        legend_x += 65 + int(draw.textlength(label, font=small_font) / scale)
    canvas.resize((width, height), Image.Resampling.LANCZOS).save(output, format="PNG", optimize=True)
    return True


def build(run_dir: Path) -> list[Path]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    raw = read_csv(run_dir / "raw_results.csv")
    summary = read_csv(run_dir / "summary_metrics.csv")
    derived_summaries = derive_rate_summaries(raw, int(manifest.get("bootstrap_resamples", 2000)))
    write_csv(run_dir / "derived_rates_summary.csv", derived_summaries)
    report_dir = run_dir / "report_plots"
    report_dir.mkdir(exist_ok=True)
    all_summaries: list[dict[str, Any]] = [{**r, "mean": float(r["mean"]), "ci95_low": float(r["ci95_low"]), "ci95_high": float(r["ci95_high"])} for r in summary]
    all_summaries.extend(derived_summaries)
    metrics = (
        ("service_rate", "Service rate", True),
        ("b3_cost_gap_relative", "Signed cost gap vs heuristic B3", False),
        ("mean_response_minutes", "Mean response among served incidents (minutes)", False),
        ("critical_mean_response_minutes", "Critical-call response among served incidents (minutes)", False),
        ("mean_coverage", "Demand-weighted coverage", True),
        ("utilization", "Ambulance utilization", True),
        ("messages_per_incident", "Messages per incident", False),
        ("duplicate_dispatch_rate", "Duplicate-dispatch rate", True),
        ("expired_dispatch_rate", "Expired-dispatch rate", True),
        ("missed_dispatch_rate", "Missed-dispatch rate", True),
        ("demand_rmse", "Demand-rate RMSE", False),
    )
    outputs = []
    families = sorted({str(row["experiment"]) for row in all_summaries})
    for family in families:
        for metric, title, percent in metrics:
            factors = ("alpha", "beta", "gamma") if family == "exp8_weight_sensitivity" else (None,)
            for factor in factors:
                axis_title = f"{title}: {factor} sensitivity" if factor else title
                suffix = f"_{factor}" if factor else ""
                path = report_dir / f"{family}{suffix}_{metric}.png"
                if chart(all_summaries, family, metric, path, axis_title, percent, factor):
                    outputs.append(path)
    featured = [
        report_dir / "exp4_communication_service_rate.png",
        report_dir / "exp4_communication_b3_cost_gap_relative.png",
        report_dir / "exp4_communication_duplicate_dispatch_rate.png",
        report_dir / "exp4_communication_expired_dispatch_rate.png",
        report_dir / "exp4_communication_missed_dispatch_rate.png",
        report_dir / "exp5_demand_knowledge_service_rate.png",
        report_dir / "exp5_demand_knowledge_demand_rmse.png",
    ]
    if not any(path.exists() for path in featured):
        featured = [path for path in outputs if path.name.endswith("service_rate.png") or path.name.endswith("b3_cost_gap_relative.png")]
        featured = featured[:6]
    featured = [path for path in featured if path.exists()]
    thumbs = []
    for path in featured:
        with Image.open(path) as source:
            thumb = source.convert("RGB")
            thumb.thumbnail((720, 440), Image.Resampling.LANCZOS)
            thumbs.append((path.name, thumb.copy()))
    cols, cell_w, cell_h = 2, 750, 480
    rows_count = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows_count * cell_h), "#F3F6F8")
    draw = ImageDraw.Draw(sheet)
    for i, (name, thumb) in enumerate(thumbs):
        x = (i % cols) * cell_w + 15
        y = (i // cols) * cell_h + 30
        sheet.paste(thumb, (x, y))
        draw.text((x, y - 23), name, fill="#17324D", font=font(15))
    screenshot_sheet = run_dir / "screenshots" / "results_overview.png"
    screenshot_sheet.parent.mkdir(exist_ok=True)
    if thumbs:
        sheet.save(screenshot_sheet, format="PNG", optimize=True)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    outputs = build(args.run_dir.resolve())
    print(json.dumps({"plots": len(outputs), "output": str(args.run_dir.resolve() / "report_plots")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

