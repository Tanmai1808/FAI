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
    "exp4b_communication_radius": ["r=2", "r=4", "r=6", "r=8", "r=12", "full", "none"],
    "exp4b_radius_sweep": ["r=2", "r=4", "r=6", "r=8", "r=12", "full", "none"],
    "exp4c_communication_loss": ["p=0", "p=0.1", "p=0.25", "p=0.5", "p=0.75", "p=1", "p=1.0", "full", "none"],
    "exp4c_loss_sweep": ["p=0", "p=0.1", "p=0.25", "p=0.5", "p=0.75", "p=1", "p=1.0", "full", "none"],
    "exp5_demand_knowledge": ["learned", "oracle"],
    "exp5b_learning_shifting": ["learned", "oracle"],
    "exp5b_shifting_demand": ["learned", "oracle"],
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
    for path in (
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
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
        n = int(row.get("n_incidents", 0))
        exp_rate = float(row.get("expired_rate", int(row.get("expired", 0)) / n if n else 0.0))
        dup_rate = float(row.get("duplicate_rate", int(row.get("duplicate_incidents", 0)) / n if n else 0.0))
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
        return f"BID/{row.get('communication', '')}"
    if experiment == "exp5_demand_knowledge" and policy == "BID":
        return f"BID/{row.get('demand_condition', '')}"
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


def chart_stacked_cost(raw: list[dict[str, str]], output: Path) -> bool:
    """Stacked cost-component chart for B1, B2, B3, BID at N=7 and N=10."""
    target_levels = ["n=7", "n=10"]
    target_policies = ["B1", "B2", "B3", "BID"]
    components = [
        ("response_cost", "Response Delay", "#35618A"),
        ("external_coverage_cost", "Coverage Loss", "#2A9D8F"),
        ("home_demand_cost", "Home Demand", "#E9C46A"),
        ("expiration_cost", "Expiration Penalty", "#D64F61"),
    ]

    # Check data availability
    e1_rows = [r for r in raw if r.get("experiment") == "exp1_ambulance_count"]
    if not e1_rows:
        return False

    means: dict[tuple[str, str, str], float] = {}
    total_means: dict[tuple[str, str], float] = {}
    max_total = 0.0

    for lvl in target_levels:
        for pol in target_policies:
            rows = [r for r in e1_rows if r.get("level") == lvl and r.get("policy") == pol]
            t_sum = 0.0
            for comp, _, _ in components:
                vals = [float(r[comp]) for r in rows if r.get(comp) not in (None, "", "NA")]
                m = sum(vals) / len(vals) if vals else 0.0
                means[(lvl, pol, comp)] = m
                t_sum += m
            total_means[(lvl, pol)] = t_sum
            if t_sum > max_total:
                max_total = t_sum

    if max_total <= 0:
        return False

    width, height, scale = 1500, 920, 2
    canvas = Image.new("RGB", (width * scale, height * scale), "white")
    draw = ImageDraw.Draw(canvas)
    title_font = font(28 * scale)
    axis_font = font(20 * scale)
    small_font = font(17 * scale)
    legend_font = font(16 * scale)

    left, right, top, bottom = 140, 50, 100, 180
    plot_w, plot_h = width - left - right, height - top - bottom
    y_max = max_total * 1.15

    def p(x: float, y: float) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    def yp(value: float) -> float:
        return height - bottom - (value / y_max) * plot_h

    draw.text(p(left, 32), "Cost Breakdown by Component (Fleet Size N=7 vs N=10)", fill="#17324D", font=title_font)
    draw.line((p(left, top), p(left, height - bottom), p(width - right, height - bottom)), fill="#243746", width=3 * scale)

    # Grid & ticks
    for tick in range(6):
        val = tick * y_max / 5
        y = yp(val)
        draw.line((p(left, y), p(width - right, y)), fill="#DDE4EA", width=scale)
        draw.text(p(12, y - 12), f"{val:.0f}", fill="#3F5263", font=axis_font)

    # Clusters
    cluster_w = plot_w / len(target_levels)
    bar_w = 48
    bar_gap = 14

    for c_idx, lvl in enumerate(target_levels):
        c_center = left + (c_idx + 0.5) * cluster_w
        total_cluster_bars_w = len(target_policies) * bar_w + (len(target_policies) - 1) * bar_gap
        start_x = c_center - total_cluster_bars_w / 2

        draw.text(p(c_center, height - bottom + 65), f"Ambulances {lvl}", fill="#17324D", font=axis_font, anchor="ma")

        for b_idx, pol in enumerate(target_policies):
            bx = start_x + b_idx * (bar_w + bar_gap)
            cur_y_val = 0.0
            for comp, _, color in components:
                m_val = means.get((lvl, pol, comp), 0.0)
                y_bot = yp(cur_y_val)
                y_top = yp(cur_y_val + m_val)
                draw.rectangle((p(bx, y_top), p(bx + bar_w, y_bot)), fill=color, outline="#243746", width=scale)
                cur_y_val += m_val

            # Policy label
            draw.text(p(bx + bar_w / 2, height - bottom + 20), pol, fill="#384D5C", font=small_font, anchor="ma")

    # Legend
    leg_x = left
    leg_y = height - 60
    for _, name, color in components:
        draw.rectangle((p(leg_x, leg_y), p(leg_x + 24, leg_y + 18)), fill=color, outline="#243746", width=scale)
        draw.text(p(leg_x + 32, leg_y - 2), name, fill="#263B4C", font=legend_font)
        leg_x += 45 + int(draw.textlength(name, font=legend_font) / scale)

    canvas.resize((width, height), Image.Resampling.LANCZOS).save(output, format="PNG", optimize=True)
    return True


def chart_communication_sweeps(raw: list[dict[str, str]], output_dir: Path) -> list[Path]:
    """Two multi-panel communication-sweep figures: radius sweep (4b) and loss sweep (4c)."""
    outputs = []
    sweeps = [
        (
            ("exp4b_communication_radius", "exp4b_radius_sweep"),
            ["r=2", "r=4", "r=6", "r=8", "r=12"],
            "Communication Radius (minutes)",
            "Radius Sweep: Coordination Degradation (Exp 4b)",
            output_dir / "exp4b_radius_sweep.png",
        ),
        (
            ("exp4c_communication_loss", "exp4c_loss_sweep"),
            ["p=0", "p=0.1", "p=0.25", "p=0.5", "p=0.75", "p=1", "p=1.0"],
            "Packet Loss Probability",
            "Packet Loss Sweep: Coordination Degradation (Exp 4c)",
            output_dir / "exp4c_loss_sweep.png",
        ),
    ]

    for exp_ids, preferred_levels, x_axis_title, fig_title, out_path in sweeps:
        exp_rows = [r for r in raw if r.get("experiment") in exp_ids and r.get("policy") == "BID"]
        if not exp_rows:
            continue

        levels_in_data = [lvl for lvl in preferred_levels if any(r.get("level") == lvl for r in exp_rows)]
        if not levels_in_data:
            levels_in_data = sorted({r.get("level", "") for r in exp_rows if r.get("level")})
        if not levels_in_data:
            continue

        # Data for Duplicate rate and Expired rate
        dup_stats = {}
        exp_stats = {}
        for lvl in levels_in_data:
            lvl_rows = [r for r in exp_rows if r.get("level") == lvl]
            dup_vals = [float(r["duplicate_rate"]) for r in lvl_rows if r.get("duplicate_rate") not in (None, "", "NA")]
            exp_vals = [float(r["expired_rate"]) for r in lvl_rows if r.get("expired_rate") not in (None, "", "NA")]
            dup_stats[lvl] = bootstrap_mean_interval(dup_vals, resamples=1000)[:3] if dup_vals else (0.0, 0.0, 0.0)
            exp_stats[lvl] = bootstrap_mean_interval(exp_vals, resamples=1000)[:3] if exp_vals else (0.0, 0.0, 0.0)

        # Draw 2-panel figure side by side
        width, height, scale = 1600, 720, 2
        canvas = Image.new("RGB", (width * scale, height * scale), "white")
        draw = ImageDraw.Draw(canvas)
        title_font = font(26 * scale)
        subtitle_font = font(20 * scale)
        axis_font = font(18 * scale)
        small_font = font(16 * scale)

        def p(x: float, y: float) -> tuple[int, int]:
            return round(x * scale), round(y * scale)

        draw.text(p(60, 24), fig_title, fill="#17324D", font=title_font)

        panels = [
            ("Panel A: Duplicate-Dispatch Rate", dup_stats, "#D64F61", 60, width // 2 - 30),
            ("Panel B: Expired-Dispatch Rate", exp_stats, "#793B86", width // 2 + 30, width - 60),
        ]

        top, bottom = 110, 120
        plot_h = height - top - bottom

        for p_title, p_stats, color, p_left, p_right in panels:
            p_w = p_right - p_left
            draw.text(p(p_left + 40, top - 36), p_title, fill="#243746", font=subtitle_font)

            all_vals = [v for s in p_stats.values() for v in s]
            max_v = max(all_vals) if all_vals else 0.5
            y_max = max(0.2, min(1.0, max_v * 1.25))

            def yp_panel(val: float) -> float:
                return height - bottom - (val / y_max) * plot_h

            # Axes
            draw.line((p(p_left + 60, top), p(p_left + 60, height - bottom), p(p_right, height - bottom)), fill="#243746", width=2 * scale)

            # Ticks
            for tick in range(5):
                val = tick * y_max / 4
                y = yp_panel(val)
                draw.line((p(p_left + 60, y), p(p_right, y)), fill="#E2E7EC", width=scale)
                draw.text(p(p_left + 10, y - 10), f"{val * 100:.0f}%", fill="#3F5263", font=small_font)

            # X points
            n_pts = len(levels_in_data)
            x_step = (p_w - 90) / (n_pts - 1) if n_pts > 1 else (p_w - 90) / 2
            pts = []
            for i, lvl in enumerate(levels_in_data):
                x = p_left + 75 + i * x_step
                mean, low, high = p_stats[lvl]
                pts.append((x, yp_panel(mean)))
                # Error bar
                draw.line((p(x, yp_panel(high)), p(x, yp_panel(low))), fill=color, width=3 * scale)
                draw.line((p(x - 6, yp_panel(high)), p(x + 6, yp_panel(high))), fill=color, width=2 * scale)
                draw.line((p(x - 6, yp_panel(low)), p(x + 6, yp_panel(low))), fill=color, width=2 * scale)
                draw.ellipse((p(x - 6, yp_panel(mean) - 6), p(x + 6, yp_panel(mean) + 6)), fill=color, outline="white", width=scale)
                # Label
                draw.text(p(x, height - bottom + 18), lvl, fill="#384D5C", font=small_font, anchor="ma")

            if len(pts) > 1:
                draw.line([p(x, y) for x, y in pts], fill=color, width=3 * scale)

            draw.text(p(p_left + p_w / 2, height - bottom + 60), x_axis_title, fill="#3F5263", font=axis_font, anchor="ma")

        canvas.resize((width, height), Image.Resampling.LANCZOS).save(out_path, format="PNG", optimize=True)
        outputs.append(out_path)

    return outputs


def chart_rmse_timeseries(rmse_ts_path: Path, output: Path) -> bool:
    """RMSE-over-time figure for exp5b shifting demand with vertical line at t=3000."""
    if not rmse_ts_path.exists():
        return False
    rows = read_csv(rmse_ts_path)
    if not rows:
        return False

    exp5b_rows = [r for r in rows if r.get("experiment") in ("exp5b_shifting_demand", "exp5_demand_knowledge")]
    if not exp5b_rows:
        exp5b_rows = rows

    by_minute_learned: dict[float, list[float]] = defaultdict(list)
    by_minute_oracle: dict[float, list[float]] = defaultdict(list)

    for r in exp5b_rows:
        t = float(r["time_minutes"])
        rmse = float(r["rmse"])
        lvl = r.get("level", "learned")
        if lvl == "oracle" or r.get("policy_oracle_input") in ("True", "true", "1"):
            by_minute_oracle[t].append(rmse)
        else:
            by_minute_learned[t].append(rmse)

    if not by_minute_learned and not by_minute_oracle:
        return False

    times = sorted(set(by_minute_learned.keys()) | set(by_minute_oracle.keys()))
    if not times:
        return False

    learned_means = [(t, sum(by_minute_learned[t]) / len(by_minute_learned[t])) for t in times if t in by_minute_learned]
    oracle_means = [(t, sum(by_minute_oracle[t]) / len(by_minute_oracle[t])) for t in times if t in by_minute_oracle]

    all_vals = [v for _, v in learned_means] + [v for _, v in oracle_means]
    max_v = max(all_vals) if all_vals else 1.0
    y_max = max_v * 1.25
    x_max = max(times) if times else 6000.0

    width, height, scale = 1500, 850, 2
    canvas = Image.new("RGB", (width * scale, height * scale), "white")
    draw = ImageDraw.Draw(canvas)
    title_font = font(28 * scale)
    axis_font = font(20 * scale)
    small_font = font(17 * scale)

    def p(x: float, y: float) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    left, right, top, bottom = 120, 50, 100, 140
    plot_w, plot_h = width - left - right, height - top - bottom

    def xp(t: float) -> float:
        return left + (t / x_max) * plot_w

    def yp(val: float) -> float:
        return height - bottom - (val / y_max) * plot_h

    draw.text(p(left, 32), "Online Demand Learning: Rate RMSE Over Time (Shift at t=3000)", fill="#17324D", font=title_font)
    draw.line((p(left, top), p(left, height - bottom), p(width - right, height - bottom)), fill="#243746", width=3 * scale)

    # Grid & Y ticks
    for tick in range(6):
        val = tick * y_max / 5
        y = yp(val)
        draw.line((p(left, y), p(width - right, y)), fill="#DDE4EA", width=scale)
        draw.text(p(16, y - 12), f"{val:.2f}", fill="#3F5263", font=axis_font)

    # X ticks (every 1000 min)
    step = 1000
    for t_val in range(0, int(x_max) + 1, step):
        x = xp(t_val)
        draw.line((p(x, height - bottom), p(x, height - bottom + 8)), fill="#243746", width=2 * scale)
        draw.text(p(x, height - bottom + 18), str(t_val), fill="#384D5C", font=small_font, anchor="ma")

    draw.text(p(left + plot_w / 2, height - bottom + 65), "Simulation Time (minutes)", fill="#3F5263", font=axis_font, anchor="ma")

    # Shift line at t=3000
    shift_t = 3000.0
    if 0 <= shift_t <= x_max:
        sx = xp(shift_t)
        # Dashed line
        dash_len = 10
        cur_y = top
        while cur_y < height - bottom:
            draw.line((p(sx, cur_y), p(sx, min(cur_y + dash_len, height - bottom))), fill="#8064A2", width=3 * scale)
            cur_y += dash_len * 2
        draw.text(p(sx, top - 32), "Demand Shift (t=3000)", fill="#8064A2", font=axis_font, anchor="ma")

    # Curves
    if learned_means:
        pts = [p(xp(t), yp(v)) for t, v in learned_means]
        if len(pts) > 1:
            draw.line(pts, fill="#D64F61", width=4 * scale)

    if oracle_means:
        pts = [p(xp(t), yp(v)) for t, v in oracle_means]
        if len(pts) > 1:
            draw.line(pts, fill="#4E9A76", width=3 * scale)

    # Legend
    leg_x = width - right - 320
    leg_y = top + 20
    draw.line((p(leg_x, leg_y + 10), p(leg_x + 35, leg_y + 10)), fill="#D64F61", width=4 * scale)
    draw.text(p(leg_x + 45, leg_y), "BID Online Learned", fill="#17324D", font=small_font)
    if oracle_means:
        draw.line((p(leg_x, leg_y + 40), p(leg_x + 35, leg_y + 40)), fill="#4E9A76", width=3 * scale)
        draw.text(p(leg_x + 45, leg_y + 30), "BID Oracle Demand", fill="#17324D", font=small_font)

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
        ("total_cost", "Total scenario cost", False),
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

    # 1. Stacked cost chart
    stacked_cost_path = report_dir / "cost_breakdown_stacked_n7_n10.png"
    if chart_stacked_cost(raw, stacked_cost_path):
        outputs.append(stacked_cost_path)

    # 2. Communication sweeps
    outputs.extend(chart_communication_sweeps(raw, report_dir))

    # 3. RMSE time series
    rmse_ts_path = run_dir / "learning_rmse_timeseries.csv"
    rmse_fig_path = report_dir / "exp5b_learning_rmse_timeseries.png"
    if chart_rmse_timeseries(rmse_ts_path, rmse_fig_path):
        outputs.append(rmse_fig_path)

    featured = [
        report_dir / "exp4_communication_service_rate.png",
        report_dir / "exp4_communication_b3_cost_gap_relative.png",
        report_dir / "exp4_communication_duplicate_dispatch_rate.png",
        report_dir / "exp4_communication_expired_dispatch_rate.png",
        report_dir / "exp4b_radius_sweep.png",
        report_dir / "exp4c_loss_sweep.png",
        report_dir / "cost_breakdown_stacked_n7_n10.png",
        report_dir / "exp5b_learning_rmse_timeseries.png",
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
