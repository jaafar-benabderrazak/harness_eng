---
layout: default
title: harness_eng
---

# harness_eng

**Same model, five harnesses, one benchmark.** A controlled experiment that holds one LLM constant and varies only the agent harness around it, measuring the spread in success rate and wall-clock.

## Read the writeup

**[article-glm-20260423 — seeds=3 production run](writeup/article-glm-20260423.html)** *(opens the article rendered with Jekyll; the Markdown source is [`writeup/article-glm-20260423.md`](https://github.com/jaafar-benabderrazak/harness-bench/blob/main/writeup/article-glm-20260423.md) in the repo)*

## Headline finding

On `glm-4.7-flash:latest` (Ollama, local inference), 75-cell matrix (5 harnesses × 5 tasks × 3 seeds):

| harness      | success | Wilson 95% CI | wall-clock |
|--------------|--------:|---------------|-----------:|
| single_shot  | 9/15    | 0.36 – 0.80   | 217 s      |
| plan_execute | 9/15    | 0.36 – 0.80   | 1,957 s    |
| reflexion    | 7/15    | 0.25 – 0.70   | 1,269 s    |
| minimal      | 4/15    | 0.11 – 0.52   | 858 s      |
| react        | 2/15    | **0.04 – 0.38** | 220 s    |

- `single_shot` ties for best success rate at **1/9th the wall-clock** of `plan_execute`.
- `react` is the only harness whose Wilson CI is non-overlapping with the top tier — statistically reliable worst-of-five.
- `plan_execute` hits `turn_cap` on 60% of cells; `reflexion` hits SDK-boundary errors on 33%.
- The `seeds=1` pilot would have ranked `minimal` tied for best; at `seeds=3` it's second-worst. **3 of 5 rankings flipped** between N=5 and N=15.

Full methodology + trace evidence + six concrete implications in [the writeup](writeup/article-glm-20260423.html).

## Repository layout

- [`README.md`](https://github.com/jaafar-benabderrazak/harness-bench/blob/main/README.md) — quickstart, pre-registered hypothesis, reproduce steps
- [`HELD_OUT.md`](HELD_OUT.html) — held-out fixture decision + rationale
- [`HARNESSES_FROZEN.md`](HARNESSES_FROZEN.html) — freeze manifest + tag-move log
- [`writeup/`](https://github.com/jaafar-benabderrazak/harness-bench/tree/main/writeup) — dated article + charts
- [GitHub repo](https://github.com/jaafar-benabderrazak/harness-bench) — source, tests, harness implementations, offline demo

## Reproduce

```bash
git clone https://github.com/jaafar-benabderrazak/harness-bench && cd harness-bench
pip install -e ".[dev]"
cp .env.example .env     # HARNESS_BACKEND=ollama, HARNESS_MODEL=glm-4.7-flash:latest
ollama pull glm-4.7-flash:latest
pytest -q                # 49 tests offline, no API key required
python scripts/run_full.py --seeds 3 --yes
python scripts/make_chart.py
```

All tests pass offline. Matrix run is local and free.
