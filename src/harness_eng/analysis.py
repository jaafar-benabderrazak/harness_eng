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
    return Aggregates(df_rows=df, df_harness=per_harness)


def frontier_chart(agg: Aggregates, out: Path) -> None:
    df = agg.df_harness
    fig, ax = plt.subplots(figsize=(7, 5))
    yerr_low = (df["success_rate"] - df["ci_low"]).clip(lower=0)
    yerr_high = (df["ci_high"] - df["success_rate"]).clip(lower=0)
    ax.errorbar(
        df["cost_usd"], df["success_rate"],
        yerr=[yerr_low, yerr_high],
        fmt="o", capsize=4, markersize=8, elinewidth=1,
    )
    for _, row in df.iterrows():
        ax.annotate(row["harness"], (row["cost_usd"], row["success_rate"]),
                    xytext=(6, 6), textcoords="offset points")
    ax.set_xlabel("Cost per run matrix (USD)")
    ax.set_ylabel("Task success rate (Wilson 95% CI)")
    ax.set_title(f"Success vs cost across harnesses — model frozen at {CONFIG.model.name}")
    ax.grid(alpha=0.3)
    ax.set_ylim(-0.05, 1.05)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
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


def _failure_section(ts: TraceSummary) -> str:
    """Render a pre-populated failure-mode section from trace scan."""
    if not ts.stop_reasons:
        return "*No traces found — run `scripts/run_full.py` to populate `traces/`.*"
    lines = ["### Stop-reason distribution per harness", ""]
    lines.append("| harness | " + " | ".join(sorted({r for c in ts.stop_reasons.values() for r in c})) + " |")
    reasons = sorted({r for c in ts.stop_reasons.values() for r in c})
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
            lines.append(f"- **{harness}** most expensive cell: `{t}` — {tok:,} tokens — `{p}`")
        if lt and (not me or lt[1] != me[1]):
            t, p, tr = lt
            lines.append(f"- **{harness}** longest trace: `{t}` — {tr} model turns — `{p}`")

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
    cost_spread = (
        df["cost_usd"].max() / df["cost_usd"].min()
        if df["cost_usd"].min() > 0 else float("inf")
    )
    table_md = _df_to_markdown(df)
    body = f"""# Same model, five harnesses, one benchmark

## Hook

![success vs cost]({chart_rel})

Five agent harnesses. Same frozen model (`{CONFIG.model.name}`, temperature 0).
One deterministic HTML-extraction benchmark. Spread in task success rate:
**{success_spread:.2f}x**. Spread in cost: **{cost_spread:.2f}x**.

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
        "article": article_path,
    }
