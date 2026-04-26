---
layout: default
title: harness_eng
---

# harness_eng

**Same model, sixteen harnesses, two tasks.** A controlled experiment that holds one LLM constant and varies only the agent harness around it. Two task types (HTML extraction + Python code generation). **Eight harnesses benchmarked end-to-end** (150 graded runs producing the published numbers); **eight more cataloged** in Phase 8, every common agent pattern named, mapped to its real-world framework analog, implemented + unit-tested against freeze tag `2af30fc`, matrix re-run gated on hardware (the configured model needs more memory than this host has). One consistent methodology lesson on the benchmarked half; a structured catalog on the cataloged half so a reader can map the design space without waiting for the rerun.

## Read the writeup

**[→ Full combined article](writeup/article.html)**, one page, both experiments, detailed per-harness breakdowns with framework analogs (LangChain / LangGraph / CrewAI / Aider / Cursor), forensics behind `<details>` toggles, Mermaid diagrams, dollar extrapolation at frontier-model list prices, and a cross-experiment conclusion.

**[→ Medium-ready HTML version](writeup/article-medium.html)**, same content rendered as clean HTML (no Mermaid, no collapsibles), suitable for import into Medium, Substack, or any editor that accepts HTML paste.

## The one-line finding

**On hard tasks, complex harnesses fail more than simple ones. On easy tasks, complex harnesses cost more than simple ones. `single_shot` won on wall-clock in both experiments.**

| experiment     | tasks | harnesses | ceiling | winner on accuracy | winner on wall-clock |
|----------------|-------|-----------|---------|--------------------|-----------------------|
| HTML extraction| 5     | 5         | 9/15 tied | single_shot / plan_execute | **single_shot** (217 s vs 1,957 s) |
| Code generation| 5     | 5         | 15/15 tied | all 5 harnesses | **single_shot** (283 s vs 598 s)   |

Both experiments converge: complex harnesses pay returns only where the base model's first-shot accuracy is both *below target* AND *multi-turn-recoverable*. Both conditions rarely hold at once on weak models. On `glm-4.7-flash`, neither experiment produced a case where a complex harness justified its extra tokens and time.

## Repository

- **Repo**: [github.com/jaafar-benabderrazak/harness-bench](https://github.com/jaafar-benabderrazak/harness-bench)
- **16 harnesses** across two families:
  - **Benchmarked (8)**: `single_shot`, `react`, `plan_execute`, `reflexion`, `minimal`, `chain_of_thought`, `test_driven`, `retry_on_fail`
  - **Cataloged (8)**: `multi_agent`, `self_consistency`, `tool_use_with_validation`, `tree_of_thoughts`, `react_with_replan`, `cached_react`, `program_aided`, `streaming_react` (registered in code but excluded from the matrix per Ollama OOM finding)
- Each harness maps to a real-world agent-engineering pattern (LangChain `AgentExecutor`, LangGraph plan-and-execute, CrewAI/AutoGen multi-agent, Reflexion paper, ToT paper, PaL paper, Wang et al. self-consistency, Aider/Cursor/Devin TDD loops, …). The article gives every analog explicitly.
- **2 task types**: `html_extract` (per-field normalized exact match) + `code_gen` (pytest subprocess).
- **87 tests** pass offline (no API key). CI runs on Ubuntu + Windows.
- Freeze tag `harnesses-frozen` (currently `2af30fc`) pins the comparison; the runner refuses to execute if any gated file has drifted.

## Reproduce either experiment

```bash
git clone https://github.com/jaafar-benabderrazak/harness-bench && cd harness-bench
pip install -e ".[dev]"
cp .env.example .env         # ollama + glm-4.7-flash default, no API key
ollama pull glm-4.7-flash:latest
pytest -q                    # 87 tests, all offline

# HTML extraction (~60 min)
python scripts/run_full.py --seeds 3 --yes

# Code generation (~25-35 min)
python scripts/run_code_benchmark.py --seeds 3 --yes

# Post-process, produces CSV, charts, trace viewer, article
python scripts/make_chart.py
```

Fully local. Zero dollars.
