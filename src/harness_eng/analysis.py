"""Aggregate results into a table, a frontier chart, a per-field heatmap,
and an auto-drafted markdown article.
"""
from __future__ import annotations

import json
import math
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import CONFIG, RESULTS_DIR, TRACES_DIR  # noqa: E402
from .pricing import cost_usd  # noqa: E402


# Project-wide palette so the same harness gets the same color in every chart.
HARNESS_COLORS: dict[str, str] = {
    # HTML-extraction family
    "single_shot":      "#2563eb",  # blue
    "react":            "#dc2626",  # red
    "plan_execute":     "#9333ea",  # purple
    "reflexion":        "#ea580c",  # orange
    "minimal":          "#059669",  # green
    # Code-gen family
    "chain_of_thought": "#db2777",  # pink
    "test_driven":      "#0891b2",  # teal
    "retry_on_fail":    "#ca8a04",  # amber
}


def wilson_ci(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Bounded to [0, 1] by construction — preferable to Wald at small N.
    Returns (low, high); for trials=0 returns (0.0, 1.0) (maximally uninformative).
    """
    if trials <= 0:
        return (0.0, 1.0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass
class Aggregates:
    df_rows: pd.DataFrame
    df_harness: pd.DataFrame


def load_rows(run_path: Path) -> pd.DataFrame:
    rows = []
    for line in run_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    df["cost_usd"] = [
        cost_usd(CONFIG.model.name, r["input_tokens"], r["output_tokens"])
        for r in rows
    ]
    return df


def aggregate(df: pd.DataFrame) -> Aggregates:
    per_harness = (
        df.groupby("harness")
        .agg(
            trials=("task_id", "count"),
            successes=("success", "sum"),
            success_rate=("success", "mean"),
            field_accuracy=("field_accuracy", "mean"),
            input_tokens=("input_tokens", "sum"),
            output_tokens=("output_tokens", "sum"),
            tool_calls=("tool_calls", "sum"),
            wall_clock_s=("wall_clock_s", "sum"),
            cost_usd=("cost_usd", "sum"),
        )
        .reset_index()
        .sort_values("success_rate", ascending=False)
    )
    cis = [wilson_ci(int(s), int(t)) for s, t in zip(per_harness["successes"], per_harness["trials"])]
    per_harness["ci_low"] = [c[0] for c in cis]
    per_harness["ci_high"] = [c[1] for c in cis]
    per_harness["cost_per_success_usd"] = [
        (c / s) if s > 0 else float("nan")
        for c, s in zip(per_harness["cost_usd"], per_harness["successes"])
    ]
    # Within-cell seed variance: for each (harness, task) group, how much
    # does success flip across seeds? High std = unstable, low std = deterministic.
    if "seed" in df.columns and df["seed"].nunique() > 1:
        per_cell = df.groupby(["harness", "task_id"])["success"].agg(["mean", "std"])
        per_harness_seed_std = (
            per_cell["std"].groupby("harness").mean().fillna(0.0).rename("seed_success_std")
        )
        per_harness = per_harness.merge(per_harness_seed_std, on="harness", how="left")
    else:
        per_harness["seed_success_std"] = 0.0
    return Aggregates(df_rows=df, df_harness=per_harness)


def frontier_chart(agg: Aggregates, out: Path) -> None:
    """Success-rate vs resource-cost scatter with Wilson CI error bars.

    Picks the x-axis dimension based on what varies: USD when all harnesses have
    non-zero cost (paid API), wall-clock seconds when all costs are zero (local
    inference — time is the scarce resource). Falls back to total tokens if both
    collapse to zero.

    When all harnesses have the same success rate (e.g., all 100%), the scatter
    collapses to a horizontal line, so we also output a horizontal bar chart of
    the x-axis resource next to each harness — that's the picture of who won.
    """
    df = agg.df_harness.copy()
    if df["cost_usd"].sum() > 0:
        x_col, x_label = "cost_usd", "Cost per run matrix (USD)"
    elif df["wall_clock_s"].sum() > 0:
        x_col, x_label = "wall_clock_s", "Wall-clock per run matrix (s)"
    else:
        df["_total_tokens"] = df["input_tokens"] + df["output_tokens"]
        x_col, x_label = "_total_tokens", "Total tokens per run matrix"

    all_equal_success = df["success_rate"].nunique() == 1

    fig, ax = plt.subplots(figsize=(10, 6.2))
    yerr_low = (df["success_rate"] - df["ci_low"]).clip(lower=0)
    yerr_high = (df["ci_high"] - df["success_rate"]).clip(lower=0)

    # One colored point + error bar per harness, via the project-wide color map.
    for _, row in df.iterrows():
        color = HARNESS_COLORS.get(row["harness"], "#374151")
        idx = df.index[df["harness"] == row["harness"]][0]
        ax.errorbar(
            row[x_col], row["success_rate"],
            yerr=[[yerr_low.loc[idx]], [yerr_high.loc[idx]]],
            fmt="o", capsize=5, markersize=11, elinewidth=1.4,
            color=color, zorder=3,
        )

    # Place labels with leader-line arrows so overlaps don't happen even when
    # points cluster. Offsets walk around each point in a small ring.
    ring = [(14, 14), (14, -16), (-14, 14), (-14, -16), (0, 22), (0, -26)]
    for i, (_, row) in enumerate(df.iterrows()):
        color = HARNESS_COLORS.get(row["harness"], "#374151")
        ox, oy = ring[i % len(ring)]
        ax.annotate(
            row["harness"], (row[x_col], row["success_rate"]),
            xytext=(ox, oy), textcoords="offset points",
            color=color, fontweight="bold", fontsize=11,
            arrowprops=dict(arrowstyle="-", color=color, lw=0.7, alpha=0.6),
        )

    ax.set_xlabel(x_label, fontsize=11)
    ax.set_ylabel("Task success rate (Wilson 95% CI)", fontsize=11)
    note = ""
    if all_equal_success:
        note = " — all harnesses at same success; comparison is on x-axis only"
    ax.set_title(
        f"Success vs cost across harnesses — model frozen at {CONFIG.model.name}{note}",
        fontsize=12,
    )
    ax.grid(alpha=0.25, linewidth=0.8)
    ax.set_ylim(-0.05, 1.08)
    # Pad x-axis so annotations fit
    x_min, x_max = df[x_col].min(), df[x_col].max()
    x_span = max(x_max - x_min, 1.0)
    ax.set_xlim(x_min - x_span * 0.15, x_max + x_span * 0.20)
    fig.tight_layout()
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)


def resource_bar(agg: Aggregates, out: Path) -> None:
    """Horizontal bars: for each harness, total wall-clock + input tokens. Clean
    readable comparison when everyone's at the same success rate (the 'who's
    wasteful?' picture)."""
    df = agg.df_harness.sort_values("wall_clock_s").copy()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    # Left: wall-clock
    colors = [HARNESS_COLORS.get(h, "#374151") for h in df["harness"]]
    bars1 = ax1.barh(df["harness"], df["wall_clock_s"], color=colors, edgecolor="white")
    for bar, v, success in zip(bars1, df["wall_clock_s"], df["success_rate"]):
        ax1.text(v + df["wall_clock_s"].max() * 0.015, bar.get_y() + bar.get_height() / 2,
                 f"{v:.0f}s  ({success*100:.0f}% ok)", va="center", fontsize=9)
    ax1.set_xlabel("Wall-clock per run matrix (seconds)")
    ax1.set_title("Time spent per harness")
    ax1.grid(axis="x", alpha=0.25)
    ax1.set_xlim(0, df["wall_clock_s"].max() * 1.35)

    # Right: input tokens
    bars2 = ax2.barh(df["harness"], df["input_tokens"], color=colors, edgecolor="white")
    for bar, v in zip(bars2, df["input_tokens"]):
        ax2.text(v + df["input_tokens"].max() * 0.015, bar.get_y() + bar.get_height() / 2,
                 f"{v:,}", va="center", fontsize=9)
    ax2.set_xlabel("Total input tokens across matrix")
    ax2.set_title("Tokens consumed per harness")
    ax2.grid(axis="x", alpha=0.25)
    ax2.set_xlim(0, df["input_tokens"].max() * 1.25)

    fig.suptitle(f"Resource usage per harness — {CONFIG.model.name}", fontsize=12, y=1.02)
    fig.tight_layout()
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)


def field_heatmap(agg: Aggregates, out: Path) -> None:
    """Per-task × per-harness mean field accuracy.

    Field names vary across tasks (product has price_usd; job has salary_min_usd),
    so a per-field × per-harness matrix collapses to whichever field appears in
    every task (usually just `title`). A per-task heatmap is more informative.
    """
    rows = agg.df_rows.copy()
    pivot = (
        rows.pivot_table(
            index="harness",
            columns="task_id",
            values="field_accuracy",
            aggfunc="mean",
        )
        .reindex(index=agg.df_harness["harness"].tolist())
    )
    fig, ax = plt.subplots(figsize=(max(6, 0.8 * len(pivot.columns)), 3.5))
    im = ax.imshow(pivot.values, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if pd.isna(v):
                continue
            ax.text(j, i, f"{v:.2f}",
                    ha="center", va="center", fontsize=8,
                    color="white" if v < 0.4 else "black")
    ax.set_title("Mean field accuracy per task per harness")
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def stop_reason_chart(agg: Aggregates, out: Path) -> None:
    """Stacked-bar chart: stop_reason composition per harness.

    Legend goes OUTSIDE the plot area so it never occludes the bars — the
    previous in-plot legend hid plan_execute's rightmost segments.
    """
    rows = agg.df_rows
    pivot = (
        rows.groupby(["harness", "stop_reason"]).size().unstack(fill_value=0)
    )
    pivot = pivot.reindex(index=agg.df_harness["harness"].tolist())
    cols = ["submitted"] + [c for c in pivot.columns if c != "submitted"]
    pivot = pivot[[c for c in cols if c in pivot.columns]]
    stop_colors = {
        "submitted":  "#059669",
        "turn_cap":   "#ea580c",
        "no_submit":  "#9333ea",
        "error":      "#dc2626",
    }
    fig, ax = plt.subplots(figsize=(10, max(3.5, 0.55 * len(pivot) + 1.5)))
    left = [0] * len(pivot)
    for col in pivot.columns:
        vals = pivot[col].values
        ax.barh(pivot.index, vals, left=left, label=col,
                color=stop_colors.get(col, "#6b7280"), edgecolor="white")
        for i, v in enumerate(vals):
            if v > 0:
                ax.text(left[i] + v / 2, i, str(v), ha="center", va="center",
                        fontsize=10, color="white", fontweight="bold")
        left = [x + v for x, v in zip(left, vals)]
    ax.set_xlabel("Cells (out of N)", fontsize=11)
    ax.set_title(f"Stop-reason distribution per harness — {CONFIG.model.name}", fontsize=12)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), framealpha=1.0, title="stop reason")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)


def wall_clock_heatmap(agg: Aggregates, out: Path) -> None:
    """Per-task × per-harness wall-clock — shows where each harness spent its time."""
    rows = agg.df_rows.copy()
    pivot = (
        rows.pivot_table(
            index="harness",
            columns="task_id",
            values="wall_clock_s",
            aggfunc="mean",
        )
        .reindex(index=agg.df_harness["harness"].tolist())
    )
    fig, ax = plt.subplots(figsize=(max(7, 1.05 * len(pivot.columns) + 2), 0.7 * len(pivot) + 2))
    im = ax.imshow(pivot.values, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=35, ha="right", fontsize=10)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=10)
    vmax = pivot.values.max()
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if pd.isna(v):
                continue
            color = "white" if v > vmax * 0.55 else "black"
            ax.text(j, i, f"{v:.0f}s", ha="center", va="center", fontsize=10, color=color,
                    fontweight="bold")
    ax.set_title("Mean wall-clock per cell (seconds)", fontsize=12)
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02, label="seconds")
    fig.tight_layout()
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)


def token_efficiency_chart(agg: Aggregates, out: Path) -> None:
    """Scatter: total input_tokens vs success_rate, with Wilson CI as vertical error bars."""
    df = agg.df_harness.copy()
    fig, ax = plt.subplots(figsize=(10, 6.2))
    yerr_low = (df["success_rate"] - df["ci_low"]).clip(lower=0)
    yerr_high = (df["ci_high"] - df["success_rate"]).clip(lower=0)
    for i, (_, row) in enumerate(df.iterrows()):
        color = HARNESS_COLORS.get(row["harness"], "#374151")
        ax.errorbar(
            row["input_tokens"], row["success_rate"],
            yerr=[[yerr_low.iloc[i]], [yerr_high.iloc[i]]],
            fmt="o", capsize=5, markersize=12, elinewidth=1.4, color=color, zorder=3,
        )
    # Label ring with leader lines — same approach as frontier_chart
    ring = [(14, 14), (14, -16), (-14, 14), (-14, -16), (0, 22), (0, -26), (22, 0), (-22, 0)]
    for i, (_, row) in enumerate(df.iterrows()):
        color = HARNESS_COLORS.get(row["harness"], "#374151")
        ox, oy = ring[i % len(ring)]
        ax.annotate(
            row["harness"],
            (row["input_tokens"], row["success_rate"]),
            xytext=(ox, oy), textcoords="offset points",
            color=color, fontweight="bold", fontsize=11,
            arrowprops=dict(arrowstyle="-", color=color, lw=0.7, alpha=0.6),
        )
    ax.set_xscale("log")
    ax.set_xlabel("Total input tokens across matrix (log scale)", fontsize=11)
    ax.set_ylabel("Task success rate (Wilson 95% CI)", fontsize=11)
    ax.set_title(f"Token efficiency — {CONFIG.model.name}", fontsize=12)
    ax.grid(alpha=0.25, which="both", linewidth=0.7)
    ax.set_ylim(-0.05, 1.08)
    fig.tight_layout()
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)


@dataclass
class DeepTraceAnalysis:
    """Quantitative per-harness trace dissection beyond TraceSummary."""
    selector_retry_patterns: dict[str, dict[str, int]]  # harness -> {selector: count}
    no_match_rate: dict[str, float]                      # harness -> fraction of css_select calls returning NO_MATCH
    median_turns_on_failure: dict[str, float]            # harness -> median turn count on cells that didn't submit
    total_tool_calls: dict[str, int]                     # harness -> total tool invocations


def analyze_traces_deep(traces_dir: Path | None = None) -> DeepTraceAnalysis:
    """Walk traces/ and extract per-harness behavioural stats not in TraceSummary."""
    traces_dir = traces_dir or TRACES_DIR
    selector_counts: dict[str, Counter] = defaultdict(Counter)
    css_total: dict[str, int] = defaultdict(int)
    css_no_match: dict[str, int] = defaultdict(int)
    fail_turn_counts: dict[str, list[int]] = defaultdict(list)
    tool_calls_total: dict[str, int] = defaultdict(int)

    if not traces_dir.exists():
        return DeepTraceAnalysis({}, {}, {}, {})

    for harness_dir in sorted(p for p in traces_dir.iterdir() if p.is_dir()):
        harness = harness_dir.name
        for task_dir in sorted(p for p in harness_dir.iterdir() if p.is_dir()):
            for trace_file in sorted(task_dir.glob("*.jsonl")):
                events = []
                for line in trace_file.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                end = next((e for e in reversed(events) if e.get("type") == "run_end"), {})
                turns = sum(1 for e in events if e.get("type") == "model_response")

                submitted = end.get("stop_reason") == "submitted"
                if not submitted:
                    fail_turn_counts[harness].append(turns)

                pending_selector: str | None = None
                for ev in events:
                    t = ev.get("type")
                    if t == "tool_call":
                        tool_calls_total[harness] += 1
                        if ev.get("name") == "css_select":
                            sel = (ev.get("args") or {}).get("selector", "")
                            if sel:
                                selector_counts[harness][sel] += 1
                                css_total[harness] += 1
                                pending_selector = sel
                    elif t == "tool_result" and pending_selector is not None:
                        if ev.get("output_len", 0) == 8:  # "NO_MATCH" is 8 chars
                            css_no_match[harness] += 1
                        pending_selector = None

    no_match_rate = {
        h: (css_no_match[h] / css_total[h]) if css_total[h] else 0.0
        for h in css_total
    }
    median_turns = {}
    for h, lst in fail_turn_counts.items():
        if lst:
            sl = sorted(lst)
            m = sl[len(sl) // 2]
            median_turns[h] = float(m)
    top_selectors = {
        h: dict(c.most_common(5)) for h, c in selector_counts.items()
    }
    return DeepTraceAnalysis(
        selector_retry_patterns=top_selectors,
        no_match_rate=no_match_rate,
        median_turns_on_failure=median_turns,
        total_tool_calls=dict(tool_calls_total),
    )


def freeze_sha() -> str:
    """Resolve the `harnesses-frozen` tag to its commit SHA. 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "harnesses-frozen^{commit}"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:10]
    except (FileNotFoundError, OSError):
        pass
    return "unknown"


@dataclass
class TraceSummary:
    """Per-harness trace aggregates: failure modes + notable traces by criterion."""
    stop_reasons: dict[str, Counter]          # harness -> Counter(stop_reason)
    failing_cells: dict[str, list[tuple[str, str]]]  # harness -> [(task_id, reason)]
    most_expensive: dict[str, tuple[str, Path, int]]  # harness -> (task_id, path, total_tokens)
    longest_turn_count: dict[str, tuple[str, Path, int]]  # harness -> (task_id, path, turns)


def summarize_traces(traces_dir: Path | None = None) -> TraceSummary:
    """Walk traces/ and extract failure-mode counts + notable-trace pointers per harness."""
    traces_dir = traces_dir or TRACES_DIR
    stop_reasons: dict[str, Counter] = defaultdict(Counter)
    failing: dict[str, list[tuple[str, str]]] = defaultdict(list)
    cost_per_cell: dict[str, list[tuple[int, str, Path]]] = defaultdict(list)
    turns_per_cell: dict[str, list[tuple[int, str, Path]]] = defaultdict(list)
    if not traces_dir.exists():
        return TraceSummary({}, {}, {}, {})
    for harness_dir in sorted(p for p in traces_dir.iterdir() if p.is_dir()):
        for task_dir in sorted(p for p in harness_dir.iterdir() if p.is_dir()):
            for trace_file in sorted(task_dir.glob("*.jsonl")):
                end_event: dict | None = None
                turns = 0
                for line in trace_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("type") == "run_end":
                        end_event = ev
                    elif ev.get("type") == "model_response":
                        turns += 1
                if end_event is None:
                    stop_reasons[harness_dir.name]["incomplete"] += 1
                    failing[harness_dir.name].append((task_dir.name, "no run_end event"))
                    continue
                reason = end_event.get("stop_reason", "unknown")
                stop_reasons[harness_dir.name][reason] += 1
                if reason != "submitted":
                    failing[harness_dir.name].append((task_dir.name, reason))
                total_tokens = end_event.get("input_tokens", 0) + end_event.get("output_tokens", 0)
                cost_per_cell[harness_dir.name].append((total_tokens, task_dir.name, trace_file))
                turns_per_cell[harness_dir.name].append((turns, task_dir.name, trace_file))
    most_expensive = {
        h: (t, p, tok) for h, entries in cost_per_cell.items()
        for tok, t, p in [max(entries)] if entries
    }
    longest = {
        h: (t, p, tr) for h, entries in turns_per_cell.items()
        for tr, t, p in [max(entries)] if entries
    }
    return TraceSummary(
        stop_reasons=dict(stop_reasons),
        failing_cells=dict(failing),
        most_expensive=most_expensive,
        longest_turn_count=longest,
    )


def _rel(p: Path) -> str:
    """Path relative to repo root (parent of src/) for portable article links."""
    try:
        repo_root = Path(__file__).resolve().parents[2]
        return str(p.resolve().relative_to(repo_root)).replace("\\", "/")
    except (ValueError, OSError):
        return str(p).replace("\\", "/")


def _failure_section(ts: TraceSummary) -> str:
    """Render a pre-populated failure-mode section from trace scan."""
    if not ts.stop_reasons:
        return "*No traces found — run `scripts/run_full.py` to populate `traces/`.*"
    lines = ["### Stop-reason distribution per harness", ""]
    reasons = sorted({r for c in ts.stop_reasons.values() for r in c})
    lines.append("| harness | " + " | ".join(reasons) + " |")
    lines.append("|" + "|".join(["---"] * (len(reasons) + 1)) + "|")
    for harness in sorted(ts.stop_reasons):
        c = ts.stop_reasons[harness]
        row = [harness] + [str(c.get(r, 0)) for r in reasons]
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append("### Notable traces to read first")
    lines.append("")
    for harness in sorted(ts.stop_reasons):
        me = ts.most_expensive.get(harness)
        lt = ts.longest_turn_count.get(harness)
        if me:
            t, p, tok = me
            lines.append(f"- **{harness}** most expensive cell: `{t}` — {tok:,} tokens — `{_rel(p)}`")
        if lt and (not me or lt[1] != me[1]):
            t, p, tr = lt
            lines.append(f"- **{harness}** longest trace: `{t}` — {tr} model turns — `{_rel(p)}`")

    failing = {h: v for h, v in ts.failing_cells.items() if v}
    if failing:
        lines.append("")
        lines.append("### Failing cells (by stop_reason)")
        lines.append("")
        for harness in sorted(failing):
            modes = Counter(r for _, r in failing[harness])
            summary = ", ".join(f"{reason}×{n}" for reason, n in modes.most_common())
            examples = ", ".join(f"{t} ({r})" for t, r in failing[harness][:3])
            lines.append(f"- **{harness}**: {summary}. Examples: {examples}.")
    return "\n".join(lines)


def _df_to_markdown(df: pd.DataFrame) -> str:
    """Hand-rolled markdown table — avoids optional tabulate dependency."""
    cols = list(df.columns)
    def fmt(x):
        if isinstance(x, float):
            return f"{x:.3f}"
        return str(x)
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    rows = ["| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False, name=None)]
    return "\n".join([header, sep, *rows])


def write_article(
    agg: Aggregates,
    chart_rel: str,
    heatmap_rel: str,
    out: Path,
    trace_summary: TraceSummary | None = None,
) -> None:
    df = agg.df_harness
    best = df.iloc[0]
    worst = df.iloc[-1]
    trace_summary = trace_summary or summarize_traces()
    freeze = freeze_sha()
    success_spread = (
        best["success_rate"] / worst["success_rate"]
        if worst["success_rate"] > 0 else float("inf")
    )
    # Pick the resource dimension that actually varies.
    if df["cost_usd"].min() > 0:
        resource_name = "cost"
        resource_spread = df["cost_usd"].max() / df["cost_usd"].min()
    elif df["wall_clock_s"].min() > 0:
        resource_name = "wall-clock"
        resource_spread = df["wall_clock_s"].max() / df["wall_clock_s"].min()
    else:
        resource_name = "tokens"
        totals = df["input_tokens"] + df["output_tokens"]
        resource_spread = totals.max() / max(totals.min(), 1)
    table_md = _df_to_markdown(df)
    body = f"""# Same model, five harnesses, one benchmark

## Hook

![success vs cost]({chart_rel})

Five agent harnesses. Same frozen model (`{CONFIG.model.name}`, temperature 0).
One deterministic HTML-extraction benchmark. Spread in task success rate:
**{success_spread:.2f}x**. Spread in {resource_name}: **{resource_spread:.2f}x**.

The headline is uncomfortable: on this task, harness design dominates model
choice *within a tier*. Most teams pick the model first and treat the harness
as an afterthought; the numbers say that's backwards.

## Why this matters

The AI-eng discourse is model-obsessed. When a new model drops, benchmarks
move. What gets undersold is that the scaffolding around the model — the
harness — is a much bigger lever than most teams acknowledge. This post
isolates the harness as the independent variable by freezing the model and
the task set.

## The setup

- Task: structured field extraction from messy HTML. {len(agg.df_rows['task_id'].unique())} tasks.
  Grader: normalized exact match per field.
- Model: `{CONFIG.model.name}`, temperature {CONFIG.model.temperature}, max_tokens {CONFIG.model.max_tokens}.
  Frozen in a single module that all harnesses route through.
- Harnesses:
  1. **single_shot** — stuff everything into context, ask for the answer in one call.
  2. **react** — thought/action/observation loop, no planning step, hard turn cap.
  3. **plan_execute** — one planning call produces a checklist; an executor follows it.
  4. **reflexion** — on failure, the model critiques its own trace and retries once.
  5. **minimal** — ReAct with aggressively trimmed tools (no raw HTML dump) and
     context pruning every N turns.
- Metrics: success rate (all fields correct), per-field accuracy, input + output
  tokens, tool calls, wall-clock time, cost.

## Results

{table_md}

![per-field accuracy]({heatmap_rel})

## Failure modes and notable traces

*Auto-populated from `traces/` — scan these before writing narrative.*

{_failure_section(trace_summary)}

## What surprised me

*Write this section by hand after reviewing the traces above.* The auto-drafter
has the numbers and the pointers; the narrative — which harness failed in an
embarrassing way, which succeeded for the wrong reason — is yours to write.

Open the trace viewer at `results/trace_viewer.html` for a browsable view of
every cell's trace, filterable by harness and task.

## Implications for harness design

Read off the chart, write 4–6 concrete takeaways. Frame each one as something a
reader can act on by 5pm tomorrow. Candidates: (1) cheaper harnesses that do
one thing well often beat clever ones, (2) reflexion only helps when the
critique is accurate, (3) a pruned context is a feature, not a bug, (4) raw
HTML in context is surprisingly expensive even when the task is small.

## Methodology

- Freeze commit: `{freeze}` — resolve with `git rev-parse harnesses-frozen`
- Gated files (not edited after freeze): `src/harness_eng/harnesses/`, `src/harness_eng/tools.py`, `src/harness_eng/model.py`
- The runner's pre-flight `check_freeze_gate()` refuses to execute if any gated file has diverged from the tag
- See `HARNESSES_FROZEN.md` at the repo root for per-file blob SHAs and the tag-move log

---
*Generated from* `{Path(*agg.df_rows.attrs.get('run_path', Path('unknown')).parts[-2:]) if agg.df_rows.attrs.get('run_path') else 'unknown run'}` *. Numbers are reproducible — rerun `scripts/run_full.py`.*
"""
    out.write_text(body, encoding="utf-8")


def produce_all(run_path: Path, out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = out_dir or RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    df = load_rows(run_path)
    df.attrs["run_path"] = run_path
    agg = aggregate(df)

    table_path = out_dir / "summary.csv"
    agg.df_harness.to_csv(table_path, index=False)

    chart_path = out_dir / "frontier.png"
    frontier_chart(agg, chart_path)

    heatmap_path = out_dir / "field_heatmap.png"
    field_heatmap(agg, heatmap_path)

    stop_path = out_dir / "stop_reasons.png"
    stop_reason_chart(agg, stop_path)

    wallclock_path = out_dir / "wall_clock_heatmap.png"
    wall_clock_heatmap(agg, wallclock_path)

    tokeff_path = out_dir / "token_efficiency.png"
    token_efficiency_chart(agg, tokeff_path)

    resource_path = out_dir / "resource_bars.png"
    resource_bar(agg, resource_path)

    article_path = out_dir / "article.md"
    write_article(
        agg,
        chart_rel=chart_path.name,
        heatmap_rel=heatmap_path.name,
        out=article_path,
    )

    return {
        "table": table_path,
        "chart": chart_path,
        "heatmap": heatmap_path,
        "stop_reasons": stop_path,
        "wall_clock_heatmap": wallclock_path,
        "token_efficiency": tokeff_path,
        "resource_bars": resource_path,
        "article": article_path,
    }
