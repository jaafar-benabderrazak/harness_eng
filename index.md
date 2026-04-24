---
layout: default
title: harness_eng
---

# harness_eng

**Same model, eight harnesses, two benchmarks.** A controlled experiment that holds one LLM constant and varies only the agent harness around it. Two task types (HTML extraction + Python code generation), 150 graded runs, one consistent methodology lesson.

## Read the writeup

**[→ Full combined article](writeup/article.html)** — one page, both experiments, all the forensics behind `<details>` toggles, Mermaid diagrams for every harness, and a cross-experiment conclusion.

**[→ LinkedIn-friendly version](writeup/article-linkedin.html)** — sharpened hook, plain-text flow, framework mapping (LangChain / LangGraph / CrewAI / Aider), and a "what this costs if you're paying by the token" extrapolation. Same data, different audience.

## The one-line finding

**On hard tasks, complex harnesses fail more than simple ones. On easy tasks, complex harnesses cost more than simple ones. `single_shot` won on wall-clock in both experiments.**

| experiment     | tasks | harnesses | ceiling | winner on accuracy | winner on wall-clock |
|----------------|-------|-----------|---------|--------------------|-----------------------|
| HTML extraction| 5     | 5         | 9/15 tied | single_shot / plan_execute | **single_shot** (217 s vs 1,957 s) |
| Code generation| 5     | 5         | 15/15 tied | all 5 harnesses | **single_shot** (283 s vs 598 s)   |

Both experiments converge: complex harnesses pay returns only where the base model's first-shot accuracy is both *below target* AND *multi-turn-recoverable*. Both conditions rarely hold at once on weak models. On `glm-4.7-flash`, neither experiment produced a case where a complex harness justified its extra tokens and time.

## Repository

- **Repo**: [github.com/jaafar-benabderrazak/harness-bench](https://github.com/jaafar-benabderrazak/harness-bench)
- **8 harnesses**: `single_shot`, `react`, `plan_execute`, `reflexion`, `minimal` (HTML family) + `chain_of_thought`, `test_driven`, `retry_on_fail` (code-gen family). `single_shot` and `react` run on both task types.
- **2 task types**: `html_extract` (per-field normalized exact match) + `code_gen` (pytest subprocess).
- **55 tests** pass offline (no API key). CI runs on Ubuntu + Windows.
- Freeze tag `harnesses-frozen` pins the comparison; the runner refuses to execute if any gated file has drifted.

## Reproduce either experiment

```bash
git clone https://github.com/jaafar-benabderrazak/harness-bench && cd harness-bench
pip install -e ".[dev]"
cp .env.example .env         # ollama + glm-4.7-flash default, no API key
ollama pull glm-4.7-flash:latest
pytest -q                    # 55 tests, all offline

# HTML extraction (~60 min)
python scripts/run_full.py --seeds 3 --yes

# Code generation (~25-35 min)
python scripts/run_code_benchmark.py --seeds 3 --yes

# Post-process — produces CSV, charts, trace viewer, article
python scripts/make_chart.py
```

Fully local. Zero dollars.
