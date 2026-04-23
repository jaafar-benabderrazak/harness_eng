# Project Research Summary

**Project:** harness_eng
**Domain:** Controlled LLM agent-harness benchmarking experiment (portfolio piece)
**Researched:** 2026-04-23
**Confidence:** HIGH

## Executive Summary

harness_eng is a portfolio-grade controlled experiment: one frozen model (`claude-sonnet-4-6`, temperature 0, max_tokens 2048) evaluated across five hand-written harnesses (single_shot, react, plan_execute, reflexion, minimal) on a 5-fixture deterministic HTML-extraction benchmark. The independent variable is the harness itself; everything else — model, per-task prompts, tool registry, grader — must be held constant or the comparison collapses. Research converges: do not adopt Inspect AI, DSPy, or LangChain; all three homogenize the exact layer this experiment varies. Roll your own, keep the dep list small (`anthropic`, `bs4+lxml`, `pandas<3`, `matplotlib`, `pytest`), and treat the single-import-site seal for the `anthropic` SDK as an enforceable invariant (AST unit test), not a convention.

Scaffolding is already committed: `config.py`, `model.py`, `trace.py`, `tools.py`, `grader.py`, `tasks/{loader.py, tasks.jsonl, fixtures/*5}`, all five `harnesses/{base, single_shot, react, plan_execute, reflexion, minimal}.py`, `runner.py`, `cost_estimator.py`, `analysis.py`, `trace_viewer.py`, `pricing.py`, scripts, `tests/test_model_seal.py`, `.github/workflows/ci.yml`. Remaining work from research: (1) freeze the trace-event schema with `schema_version` and regression tests; (2) retrofit seeds-per-cell + Wilson-CI computation into runner/analysis; (3) add a git-tag-based harness-freeze gate to `runner.py`; (4) harden grader normalization for Unicode/locale determinism; (5) run the matrix under the freeze tag; (6) publish the article.

The failure modes that will embarrass this project post-publication are methodological, not technical: peek-and-patch harness tuning after seeing results (Pitfall 1), tool-result tokens silently omitted from cost accounting (Pitfall 2), trace survivorship bias on failed runs (Pitfall 3), and single-seed conclusions (Pitfall 7). Every one is preventable through structural enforcement in the runner and trace layer — not through discipline. The roadmap must front-load those enforcement gates before the matrix run.

## Key Findings

### Recommended Stack

Small, boring, frozen. `anthropic >=0.96,<1.0` as the only model client. `pandas` pinned below 3.0 (3.0 shipped breaking changes Jan 2026). `matplotlib` for static charts. `uv` for env, `ruff` for lint+format. OpenTelemetry GenAI semconv borrowed only for attribute names on the JSONL schema — no OTel SDK dep.

**Core technologies:**

- `anthropic >=0.96,<1.0` — sole model client, imported in exactly one file (`model.py`); manual tool-use loop, not `beta.tool_runner`
- `beautifulsoup4 >=4.12` + `lxml` — HTML parsing; parse speed irrelevant at 5-fixture scale
- `pandas >=2.2,<3.0` — aggregate CSV + chart data; must pin below 3.0
- `matplotlib >=3.10` — static frontier + heatmap PNGs
- `pytest >=8.3` — grader tests, trace-schema tests, AST seal test
- `uv` + `ruff` — env + lint; fast on Windows-bash

**What NOT to use:** Inspect AI, DSPy, LangChain/LangGraph, `anthropic.beta.tool_runner`, `tiktoken`, OpenTelemetry SDK, W&B/MLflow/Langfuse, Docker.

### Expected Features

**Must have (table stakes):**

- Single frozen-model routing through `model.call()` (built; seal test passing)
- Deterministic per-field normalized-exact-match grader (built; needs Unicode/locale hardening)
- JSONL traces from call 1 — append-only (built; needs line-buffering + fsync + `schema_version`)
- `temperature=0` plus multi-seed — minimum N=3 seeds per cell
- Per-call cost + latency + token accounting in trace; aggregated post-hoc
- All 5 harnesses frozen at a git tag before the matrix runs
- Cost estimator that gates the full run (built as hard gate in scripts/run_full.py)
- Summary CSV + success-rate-vs-cost frontier PNG (built)
- Per-field accuracy heatmap PNG (built)
- Auto-drafted article (built)
- Standalone HTML trace viewer (built)
- pytest suite covering seal, grader, trace schema, harness contract, tool whitelist
- GitHub Actions CI: pytest + one-task pilot (built — Linux only; add Windows matrix)
- README onboarding in 5 minutes; pre-registered hypothesis in README

**Should have (differentiators):**

- Harness-as-variable framing in README + article
- Minimal harness enforces no-`read_html` structurally (whitelist), not via prompt (built)
- Retry/rate-limit failures logged as distinct trace events
- Wilson 95% CI error bars on frontier chart
- Cost-per-successful-extraction metric
- 2 held-out fixtures never used during harness development
- Freeze commit SHA cited in article methodology

**Defer (v1.x / v2+):**

- Multi-provider comparison (separate project)
- Task count expansion beyond 5
- SWE-bench / WebArena adoption
- LLM-as-judge
- OTel / W&B / MLflow / Streamlit dashboard
- Parallel matrix across machines
- Docker / devcontainer

### Architecture Approach

Single-process laptop-scale eval harness. Four hard invariants from PROJECT.md: (1) `anthropic` imported in exactly one file, (2) every harness routes through `model.call(...)`, (3) every model and tool call writes a trace event before returning, (4) tool availability per harness is a whitelist at the dispatcher. Decomposition mirrors Inspect AI's Task / Model / Solver / Scorer minus composable-solver machinery, plus a machine-checkable seal test.

**Major components (mostly implemented):**

1. `config.py` — frozen MODEL_ID, TEMPERATURE, MAX_TOKENS, paths
2. `model.py` — sole `anthropic` import site; lazy client; manual tool-use loop
3. `tools.py` — shared tool impls + whitelist-aware dispatcher
4. `trace.py` — append-only JSONL writer (needs line-buffering + fsync + schema_version upgrade)
5. `harnesses/base.py` — sealed template-method base; subclasses override `_execute` only
6. `harnesses/{single_shot, react, plan_execute, reflexion, minimal}.py` — the independent variable; `minimal` has a structurally-restricted whitelist
7. `runner.py` — matrix orchestration (needs `--seeds` and git-tag freeze gate retrofit)
8. `cost_estimator.py` — dry-run cost estimator sharing `pricing.py` with analysis
9. `analysis.py` — aggregate CSV + frontier chart + heatmap + article autogen (needs Wilson CIs)
10. `trace_viewer.py` — single HTML file, inline JS

### Critical Pitfalls

1. **Peek-and-patch (Pitfall 1)** — git-tag `harnesses-frozen` + runner pre-flight diff check; article cites freeze SHA. *Not yet enforced in runner.*
2. **Tool-result tokens omitted from cost (Pitfall 2)** — `model.py` records full `response.usage`; cost computed downstream summing all calls; regression test needed on synthetic multi-turn transcript
3. **Trace survivorship bias (Pitfall 3)** — add `buffering=1` + `fsync` per record to `trace.py`; try/except/finally writes `run_end` even on exception (already done in base.py)
4. **Single-seed conclusions (Pitfall 7)** — required `--seeds N` (N>=3) in runner; Wilson 95% CIs on binomial proportions in analysis; error bars on charts. *Not yet implemented; runner accepts seeds but no CI computation.*
5. **Tool-implementation drift (Pitfall 5)** — `tools.py` frozen under same git tag as harnesses; each harness declares allowlist by name (done); runner asserts API payload `tools` list matches allowlist

Secondary: prompt contamination across harnesses (4), grader Unicode/locale non-determinism (6), context overflow silently degrading multi-turn harnesses (8), rate-limit failures miscounted (9), fixture leakage (10).

## Implications for Roadmap

DAG forces order: **trace schema freeze → seal-test audit of existing scaffold → finish remaining harnesses → harness-freeze gate → cost estimator → full matrix run → analysis → article + viewer + CI.** Phases 1–2 retroactively validate committed code; phases 3+ build forward.

Because the two "missing" harnesses (reflexion, minimal) are already written during scaffold, the natural phase structure collapses relative to what the synthesizer proposed. Revised 7-phase split:

### Phase 1: Trace Schema Freeze + Scaffold Audit

**Rationale:** Most code is committed. Before adding anything on top, confirm the existing surface satisfies the invariants. Line-buffering + fsync retrofit, `schema_version` field, `run_start`/`run_end` invariant test, NFC + casefold grader hardening, `max_retries=0` on SDK client.
**Addresses:** Pitfalls 2, 3, 6, 11.

### Phase 2: Harness Freeze Gate + Pre-registration

**Rationale:** Tag `harnesses-frozen` + pre-registered hypothesis in README + HARNESSES_FROZEN.md with SHAs. Runner refuses to execute if harness files differ from the frozen tag.
**Addresses:** Pitfall 1 structurally.

### Phase 3: Multi-seed + Wilson CIs

**Rationale:** `--seeds N` required (N>=3); Wilson score interval on binomial proportions; error bars on frontier chart; cost-per-success secondary metric.
**Addresses:** Pitfall 7, 14.

### Phase 4: Cost Estimator Polish + Run Manifests

**Rationale:** Expected/completed manifests per matrix cell; rerun missing cells idempotently; shared cost function between estimator and analysis.
**Addresses:** Pitfall 3, 13.

### Phase 5: Matrix Execution

**Rationale:** One-shot operational run under the freeze tag.

### Phase 6: Article Polish

**Rationale:** Auto-drafted article already produced by analysis; this phase fills in the "what surprised me" prose after reading traces; cites freeze SHA + `runs/<id>/` path; embeds 2–3 annotated failure traces.

### Phase 7: CI Expansion + Onboarding Polish

**Rationale:** Add Windows matrix to CI (grader determinism); `.gitattributes` pinning HTML/JSONL as binary; README quickstart mirrors CI command sequence; hypothesis pre-registered in README.

### Phase Ordering Rationale

- Trace/schema hardening before new work: a trace bug discovered post-matrix is HIGH recovery cost; pre-matrix it's an afternoon
- Harness-freeze gate before any `--seeds` work: multi-seed code touches runner; freeze must be tagged *before* runner changes so the tag actually means "frozen"
- Analysis changes (Wilson CIs) before matrix: re-running matrix is expensive; getting analysis right before spending API tokens is cheap
- Article prose last: needs the actual traces and numbers to write the surprising-failures section honestly

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core libraries verified via PyPI + Anthropic docs; roll-your-own vs Inspect AI argued from PROJECT.md invariants |
| Features | HIGH | Table stakes convergent across Inspect AI, lm-eval-harness, OpenAI Evals, Anthropic docs |
| Architecture | HIGH | Hard invariants explicit in PROJECT.md; decomposition mirrors Inspect AI; AST seal test already in repo |
| Pitfalls | HIGH | Methodology pitfalls textbook (BIG-bench, HELM, SWE-bench post-mortems); SDK pitfalls verified against documented `usage` semantics |

**Overall confidence:** HIGH.

### Gaps to Address

- **Trace schema:** freeze one `schema_version: 1` JSONL shape in Phase 1 and write `test_trace_schema.py` against it
- **Output channel decision (Pitfall 12):** `submit_answer` tool is already the universal output channel for every harness — lock this in as explicit design doc
- **Held-out fixtures (Pitfall 10):** 5 fixtures total; holding 2 out leaves 3 for development. If too constraining, pilot on synthetic HTML and save all 5 for matrix. Decide in Phase 1.
- **Prompt caching:** `cache_control` could materially change cost numbers; recommendation — do NOT enable in v1, document as explicit v1 constraint. Experiment is about harness differences, not caching differences.

## Sources

### Primary (HIGH confidence)

- `.planning/PROJECT.md` — authoritative for hard constraints, invariants, scope
- [anthropic SDK on PyPI (0.96.0, 2026-04-16)](https://pypi.org/project/anthropic/)
- [Claude tool-use docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [Claude Sonnet 4.6 announcement](https://www.anthropic.com/news/claude-sonnet-4-6)
- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [Inspect AI (UK AISI)](https://inspect.aisi.org.uk/) ; [inspect_ai GitHub](https://github.com/UKGovernmentBEIS/inspect_ai)
- [pandas 3.0 whatsnew](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html)
- [uv docs](https://docs.astral.sh/uv/)

### Secondary (MEDIUM confidence)

- [OpenTelemetry GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- Training-data knowledge of HELM, OpenAI Evals, DSPy decomposition

### Tertiary (LOW confidence)

- Community discourse on LangChain / AutoGPT eval post-mortems — convergent themes, pattern evidence only

### Detailed research files

- `.planning/research/STACK.md` — library selection, pins, what-not-to-use
- `.planning/research/FEATURES.md` — table-stakes/differentiator/anti-feature split + prioritization matrix
- `.planning/research/ARCHITECTURE.md` — component responsibilities, build-order DAG, anti-patterns, Inspect AI comparison
- `.planning/research/PITFALLS.md` — 16 pitfalls with phase-mapping, warning signs, recovery strategies

---
*Research completed: 2026-04-23*
*Ready for roadmap: yes*
