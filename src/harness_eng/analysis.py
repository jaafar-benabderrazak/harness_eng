"""Aggregate results into a table, a frontier chart, a per-field heatmap,
and an auto-drafted markdown article.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import CONFIG, RESULTS_DIR  # noqa: E402
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
    rows = agg.df_rows.copy()
    # Explode per_field dict into one column per field.
    field_df = pd.json_normalize(rows["per_field"])
    field_df["harness"] = rows["harness"].values
    per_harness_field = field_df.groupby("harness").mean(numeric_only=True)
    fig, ax = plt.subplots(figsize=(max(6, 0.6 * len(per_harness_field.columns)), 3.5))
    im = ax.imshow(per_harness_field.values, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(per_harness_field.columns)))
    ax.set_xticklabels(per_harness_field.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(per_harness_field.index)))
    ax.set_yticklabels(per_harness_field.index)
    for i in range(per_harness_field.shape[0]):
        for j in range(per_harness_field.shape[1]):
            ax.text(j, i, f"{per_harness_field.values[i, j]:.2f}",
                    ha="center", va="center", fontsize=7, color="black")
    ax.set_title("Per-field accuracy by harness")
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def write_article(agg: Aggregates, chart_rel: str, heatmap_rel: str, out: Path) -> None:
    df = agg.df_harness
    best = df.iloc[0]
    worst = df.iloc[-1]
    success_spread = (
        best["success_rate"] / worst["success_rate"]
        if worst["success_rate"] > 0 else float("inf")
    )
    cost_spread = (
        df["cost_usd"].max() / df["cost_usd"].min()
        if df["cost_usd"].min() > 0 else float("inf")
    )
    table_md = df.to_markdown(index=False, floatfmt=".3f")
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

## What surprised me

*Write this section by hand after reviewing the traces.* The auto-drafter has
the numbers; the narrative — which harness failed in an embarrassing way, which
succeeded for the wrong reason — is yours to write.

Representative failure traces live in `traces/{{harness}}/{{task_id}}/*.jsonl`.
Open the trace viewer at `results/trace_viewer.html` for an annotatable view.

## Implications for harness design

Read off the chart, write 4–6 concrete takeaways. Frame each one as something a
reader can act on by 5pm tomorrow. Candidates: (1) cheaper harnesses that do
one thing well often beat clever ones, (2) reflexion only helps when the
critique is accurate, (3) a pruned context is a feature, not a bug, (4) raw
HTML in context is surprisingly expensive even when the task is small.

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
