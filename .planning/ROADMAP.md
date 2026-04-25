# Roadmap: harness_eng

## Overview

Most of the src/ scaffold is already committed: config, model, trace, tools, grader, tasks (5 fixtures), all five harnesses, runner, cost_estimator, analysis, pricing, trace_viewer, CI workflow, 19 passing pytest tests including an AST seal test. Remaining work is not greenfield — it is (1) retroactively auditing the existing surface against the methodology invariants, (2) laying the freeze rails so the experiment is tamper-evident, (3) adding multi-seed statistics so conclusions are defensible, (4) running the matrix, and (5) writing the article prose off the run. Phases are ordered so that anything expensive to re-do (matrix execution, statistics) happens after anything cheap to fix (schema, seals, gates).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Audit and Harden Scaffold** - Retroactively validate the committed surface; freeze trace schema v1; harden grader; decide held-out fixtures — `65ed6bd`
- [x] **Phase 2: Methodology Freeze** - Tag harnesses-frozen, record SHAs, pre-register hypothesis, add runner pre-flight diff check — `389c31b` `b2965cd` `3bd1556`
- [x] **Phase 3: Multi-Seed + Statistics** - Require N>=3 seeds, Wilson 95% CIs, cost-per-success, chart error bars — `9cd910a`
- [x] **Phase 4: Runner Manifests + Tool-Allowlist Enforcement** - Expected/completed manifests; runner asserts API tools payload matches each harness's declared allowlist — `bca26d4` `4eacafb`
- [ ] **Phase 5: Matrix Execution** - One-shot operational run of 5 harnesses x 5 tasks x N seeds under the freeze tag *(deferred to user — API spend gated)*
- [ ] **Phase 6: Article Polish** - Fill "what surprised me" from traces; embed 2-3 annotated failure traces; cite freeze SHA + run dir *(blocked on Phase 5)*
- [x] **Phase 7: CI Expansion + Onboarding Polish** - Windows matrix for grader determinism; README quickstart aligned with CI; .gitattributes for HTML/JSONL — `54f6285`
- [ ] **Phase 8: Expand Harness Family + Refresh Article** - Add 8 new harness strategies that map to popular agent patterns (CrewAI multi-agent, ToT paper, PaL paper, self-consistency, tool-use-with-validation, streaming early-termination, react-with-replan, cached-react); rerun both matrices; refresh article + Medium HTML.

## Phase Details

### Phase 1: Audit and Harden Scaffold
**Goal**: The committed scaffold satisfies every structural invariant before anything is layered on top. Trace schema is frozen at v1; grader is Unicode/locale-deterministic; SDK retries are disabled; tool-result token accounting is regression-tested; held-out fixture decision is recorded.
**Depends on**: Nothing (first phase — operates on committed code)
**Requirements**: INTG-01, INTG-02, INTG-03, HARN-01, HARN-02, HARN-03, HARN-04, HARN-05, HARN-06, BENCH-01, BENCH-02, BENCH-03, BENCH-04, TRACE-01, TRACE-02, TRACE-03, TRACE-04, TRACE-05, RUN-01, RUN-03, RUN-05, RUN-06, ANAL-01, ANAL-03, ANAL-04, ART-01, ART-02, VIEW-01, VIEW-02, VIEW-03, VIEW-04, TEST-01, TEST-02, ONB-03
**Success Criteria** (what must be TRUE):
  1. `trace.py` writes every event with `schema_version: 1`, uses `buffering=1` line buffering, and calls `flush()`+`fsync()` after each record; a kill-mid-write test leaves a readable partial trace ending on a complete JSON line.
  2. `grader.py` normalization pipeline is explicit (NFC -> strip -> casefold -> ASCII-only whitespace collapse); golden-trace pytest verifies byte-identical scores across 100 re-invocations on the same input.
  3. The anthropic SDK client in `model.py` is constructed with `max_retries=0`; a pytest regression confirms that and that `response.usage` is written verbatim (every field, no pre-aggregation) to the trace.
  4. A synthetic 3-turn transcript test confirms tool-result tokens are re-billed on each subsequent turn's `input_tokens` — cumulative input_tokens ≈ N × tool_output_tokens, not 1x.
  5. A `HELD_OUT.md` note (or entry in README) records which fixtures are held out of harness development vs used for piloting, OR records the explicit decision to not hold any out (with rationale). Decision is committed before Phase 2 freeze.
**Plans:** 5 plans
Plans:
- [ ] 01-01-PLAN.md — trace.py hardening (schema_version + buffering + fsync) + trace regression tests
- [ ] 01-02-PLAN.md — grader.py NFC + casefold normalization + determinism test
- [ ] 01-03-PLAN.md — model.py max_retries=0 + full usage blob + multi-turn re-billing test
- [ ] 01-04-PLAN.md — HELD_OUT.md decision doc (Phase 2 gate)
- [ ] 01-05-PLAN.md — audit-pass validation + AUDIT.md requirement-to-evidence matrix

### Phase 2: Methodology Freeze
**Goal**: The methodology becomes tamper-evident. Harness files, tools.py, and model.py are pinned to a git tag; the pre-registered hypothesis is committed to README; the runner refuses to execute if any gated file differs from the freeze tag.
**Depends on**: Phase 1
**Requirements**: INTG-04, INTG-05, INTG-06, ONB-02
**Success Criteria** (what must be TRUE):
  1. Git tag `harnesses-frozen` exists on a specific commit SHA; `HARNESSES_FROZEN.md` records the freeze commit SHA, the freeze date, and the per-file SHAs of the five harness files, `tools.py`, and `model.py` at that commit.
  2. README contains a pre-registered hypothesis paragraph (expected direction and rough magnitude of the cross-harness spread) committed at or before the freeze tag; subsequent edits to that paragraph are forbidden by project discipline and visible in git history.
  3. Running the runner with a modified file under `src/harness_eng/harnesses/`, `src/harness_eng/tools.py`, or `src/harness_eng/model.py` (vs the freeze tag) aborts with a clear error naming the offending file — verified by a pytest that stages a mock diff.
  4. Running the runner with non-gated files changed (e.g., `runner.py`, `analysis.py`) proceeds normally — the gate is scoped, not total.
**Plans**: TBD

### Phase 3: Multi-Seed + Statistics
**Goal**: Claims published off this benchmark are statistically honest. Every matrix cell runs at N>=3 seeds; success rates ship with Wilson 95% confidence intervals; the frontier chart has error bars; cost-per-successful-extraction is a first-class published metric. Runner and analysis changes are explicitly post-freeze (they touch non-gated files).
**Depends on**: Phase 2
**Requirements**: RUN-02, ANAL-02, ANAL-05
**Success Criteria** (what must be TRUE):
  1. `runner.py` accepts a required `--seeds N` argument with default N=3, records the seed on every results row and trace event, and the runner pre-flight gate (Phase 2) still passes because only runner/analysis files changed.
  2. `analysis.py` computes a Wilson 95% score interval on binomial success per harness; `results/frontier.png` renders each harness as a point with visible vertical error bars.
  3. `results/summary.csv` includes a `cost_per_success_usd` column (total cost / successful extractions); value is `NaN` or ∞ for harnesses with zero successes (documented, not hidden).
  4. A dry-run pytest on a synthetic 15-trial fixture confirms the Wilson CI implementation matches a reference calculation to 1e-6.
**Plans**: TBD

### Phase 4: Runner Manifests + Tool-Allowlist Enforcement
**Goal**: The run is crash-resumable and tool-scope-auditable. Every (harness, task, seed) triple is recorded in an expected-runs manifest before execution and a completed-runs manifest after; missing cells are detectable by diff. Each harness asserts that the `tools` payload actually sent to the Anthropic API is exactly its declared allowlist — no prompt-level restriction, no accidental leakage.
**Depends on**: Phase 3
**Requirements**: HARN-07, RUN-04
**Success Criteria** (what must be TRUE):
  1. Before the matrix runs any cell, `runs/<id>/runs_expected.jsonl` contains one row per (harness, task, seed) triple; after each cell completes, `runs/<id>/runs_completed.jsonl` gains a row; diffing the two at end-of-run yields zero missing cells on a green run, and lists the exact triples to retry on a crashed run.
  2. Each harness declares `TOOL_WHITELIST` as a frozenset of tool names; runner or base class asserts `set(tools_payload_to_api) == harness.TOOL_WHITELIST` on every model call — violation raises, not warns.
  3. The `minimal` harness is structurally prevented (by allowlist assertion, not by prompt) from calling `read_html` or `extract_text`; a pytest simulates a model attempting the forbidden call and verifies a structured rejection + trace event.
  4. Re-invoking the runner after a partial crash with a `--resume <run_id>` flag (or equivalent) executes only the missing triples from the manifest diff — no double-billing.
**Plans**: TBD

### Phase 5: Matrix Execution
**Goal**: The full 5 x 5 x N matrix runs end-to-end under the freeze tag, producing one canonical `runs/<id>/` directory with complete traces, results, summary CSV, frontier chart, and heatmap. This is an operational phase, not a code phase.
**Depends on**: Phase 4
**Requirements**: (operational — no requirement IDs; exercises all prior phase requirements)
**Success Criteria** (what must be TRUE):
  1. `python -m harness_eng.cost_estimator` runs and prints projected USD per harness + total with a safety margin; user confirms before the full run proceeds.
  2. The full matrix completes with every expected cell in `runs_completed.jsonl` (manifest diff empty); any rate-limited or context-overflowed runs are tagged with `failure_mode` in the trace, not silently dropped.
  3. `runs/<id>/summary.csv`, `runs/<id>/frontier.png`, `runs/<id>/heatmap.png`, and `runs/<id>/article.md` are produced; chart shows visible spread between at least two harnesses with non-overlapping error bars (or, if no such spread, the honest result is still publishable — the article section reflects reality).
  4. Post-run sanity: `HEAD` at matrix-execution time is `harnesses-frozen` or a descendant that touched no gated file; verified by `git diff harnesses-frozen HEAD -- src/harness_eng/harnesses/ src/harness_eng/tools.py src/harness_eng/model.py` being empty.
**Plans**: TBD

### Phase 6: Article Polish
**Goal**: The drafted article becomes the publishable article. The "what surprised me" section is filled in from actual trace reading (not fabricated); 2-3 annotated failure traces are embedded or linked; the freeze commit SHA and the specific `runs/<id>/` directory are cited in methodology.
**Depends on**: Phase 5
**Requirements**: INTG-07, ART-03, ART-04
**Success Criteria** (what must be TRUE):
  1. `results/article.md` (or `runs/<id>/article.md`) contains a populated "What surprised me" section written by the human after reading traces — prose references specific trace file paths and specific failure modes, not generic observations.
  2. 2-3 annotated failure traces are either embedded as collapsible viewer excerpts or linked to the standalone `trace_viewer.html` with deep links that filter to the failing (harness, task, seed); each annotation explains what went wrong in one paragraph.
  3. The article's methodology section cites the freeze commit SHA (from `HARNESSES_FROZEN.md`) and the `runs/<id>/` directory path used for the published numbers; all numeric claims in prose are interpolated from `summary.csv`, not hand-typed.
  4. Every number in the article prose can be re-derived by running `python -m harness_eng.analysis` against the cited run directory (reproducibility check passes).
**Plans**: TBD

### Phase 7: CI Expansion + Onboarding Polish
**Goal**: A stranger can clone and reproduce the pilot in under 5 minutes. Grader determinism is proven on both Linux and Windows in CI. HTML and JSONL files are not silently mangled by line-ending normalization on Windows clones.
**Depends on**: Phase 6
**Requirements**: BENCH-05, TEST-03, ONB-01
**Success Criteria** (what must be TRUE):
  1. GitHub Actions CI matrix runs pytest on `ubuntu-latest` and `windows-latest`; grader determinism tests (golden-trace fixture) pass identically on both; PR check is green.
  2. `.gitattributes` pins `*.html` and `*.jsonl` as `-text` (binary) so Windows clones don't alter content-derived token counts or grader inputs via CRLF conversion; verified by a pytest that hashes a fixture and compares to a committed hash.
  3. README quickstart is the exact command sequence that CI runs (install -> pytest -> 1-task pilot -> viewer open), verbatim; a fresh-clone onboarding attempt hits no undocumented env vars beyond `ANTHROPIC_API_KEY` (present in `.env.example`).
  4. README onboarding is timed (by the author or a friend) at under 5 minutes install-to-pilot-chart on a clean Windows + Git Bash machine.
**Plans**: TBD

### Phase 8: Expand Harness Family + Refresh Article
**Goal**: The harness library expands from 8 to 16 distinct strategies, each mapping to a recognizable agent pattern (CrewAI, AutoGen, ToT-paper, PaL-paper, self-consistency, retry-with-replan, streaming-early-termination, tool-result-caching). The full matrix re-runs on the expanded set under a new `harnesses-frozen` tag move. The article and Medium HTML are updated to integrate every new harness into the per-harness description block, framework-mapping section, and findings tables.
**Depends on**: Phase 7
**Requirements**: HARN-08, HARN-09, HARN-10, HARN-11, HARN-12, HARN-13, HARN-14, HARN-15, BENCH-06, RUN-07, ANAL-06, ART-05
**Success Criteria** (what must be TRUE):
  1. Eight new harness files exist under `src/harness_eng/harnesses/` with `TOOL_WHITELIST`, `harness_id`, and a `task_type` set (`html_extract`, `code_gen`, or both). All eight pass the AST seal test, tool-allowlist enforcement, freeze-gate diff check, and a per-harness pytest fixture (model-mocked) that asserts the control flow follows the documented pattern.
  2. The eight harnesses are: **`tree_of_thoughts`** (HTML — proposes N=3 candidate selectors, scores each against partial HTML, picks highest); **`multi_agent`** (both — distinct planner / executor / critic system prompts with structured handoffs); **`react_with_replan`** (HTML — detects loop signatures in its own trace and triggers a `replan` model call when it stalls); **`self_consistency`** (both — wraps single_shot, samples N=5 at temperature > 0, majority-vote over normalized answers); **`program_aided`** (code-gen — model emits Python it executes via `run_python` tool to verify intermediate values, then submits final answer; distinct from `test_driven` because execution is *during reasoning*, not *as grading*); **`tool_use_with_validation`** (both — every tool call is JSON-schema-validated by the harness; on schema mismatch the harness emits a structured error tool_result and retries up to 3 times before failing the cell); **`streaming_react`** (HTML — uses streaming responses; harness terminates the stream as soon as a `submit_answer` token sequence is detected, not waiting for the full response); **`cached_react`** (HTML — memoizes `(html_hash, selector)` → result tuples in a process-local dict so repeated selectors within a cell return cached results; documented determinism caveat: cache is cell-scoped, not run-scoped, so seeds remain independent).
  3. `runner.py` registers the new harnesses in `HARNESSES_BY_TASK_TYPE` and the matrix reflects the expanded set without breaking pre-existing harnesses. Runner pre-flight gate (Phase 2) still passes — only `harnesses/`, `runner.py` registration, and `tools.py` (if a new tool is added for `program_aided`) change in this phase.
  4. The freeze tag `harnesses-frozen` moves forward to a single commit AFTER all eight harnesses are merged but BEFORE the matrix re-runs against them. The move is logged in `HARNESSES_FROZEN.md` with reason "Phase 8 harness expansion" and the per-file SHAs at the new tag.
  5. Both matrices re-run end-to-end via `python scripts/run_full.py --seeds 3 --yes` (HTML, ~12 harnesses × 5 tasks × 3 seeds = ~180 cells) and `python scripts/run_code_benchmark.py --seeds 3 --yes` (~9 harnesses × 5 tasks × 3 seeds = ~135 cells). All cells appear in `runs_completed.jsonl`; manifest diff is empty; Wilson 95% CIs computed per harness.
  6. `writeup/article.md` updated: each new harness gets a structured description block matching the existing template (what-it-does / in-production / strengths / weaknesses / use-when / Mermaid diagram). Framework-mapping bullets gain entries for `multi_agent → CrewAI/AutoGen`, `tree_of_thoughts → ToT paper (Yao et al. 2023)`, `program_aided → PaL paper (Gao et al. 2022)`, `self_consistency → Wang et al. 2022`, `tool_use_with_validation → Pydantic-style validation pattern`, `streaming_react → early-termination on tool-use streams`, `cached_react → in-memory result memoization`, `react_with_replan → loop-detection + recovery`. Numerical findings folded into Part 1 (HTML) and Part 2 (code-gen) tables and prose.
  7. `writeup/article-medium.html` regenerated via `scripts/build_medium_html.py`. Diagram PNGs for the eight new harnesses exist under `writeup/diagrams/`. The matrix tables in the HTML reflect the expanded harness set.
  8. The dollar-extrapolation table in the article is recomputed against the new token-cost rows for the expanded harness set, holding the same frontier-model list-prices ($2.50/M input, $10/M output) constant for comparability.
**Plans:** 8 plans
Plans:
- [ ] 08-01-PLAN.md — Foundation: jsonschema dep + run_python tool + temperature kwarg in model.py and base.py
- [ ] 08-02-PLAN.md — HTML react-derivatives: tree_of_thoughts + react_with_replan + cached_react (cell-scoped local cache)
- [ ] 08-03-PLAN.md — Cross-task harnesses: multi_agent (isolated histories) + self_consistency (N=5 @ T=0.7)
- [ ] 08-04-PLAN.md — Infrastructure-using harnesses: program_aided (run_python) + tool_use_with_validation (jsonschema)
- [ ] 08-05-PLAN.md — streaming_react implementation + Ollama compatibility verification (gated checkpoint)
- [ ] 08-06-PLAN.md — Registration + tests + analysis colors: wire all 8 into HARNESSES + HARNESSES_BY_TASK_TYPE
- [ ] 08-07-PLAN.md — Freeze-tag move + HARNESSES_FROZEN.md update (gated checkpoint before matrix runs)
- [ ] 08-08-PLAN.md — Article + Medium HTML refresh (gated on user-triggered matrix re-runs)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Audit and Harden Scaffold | 0/5 | Not started | - |
| 2. Methodology Freeze | 0/TBD | Not started | - |
| 3. Multi-Seed + Statistics | 0/TBD | Not started | - |
| 4. Runner Manifests + Tool-Allowlist Enforcement | 0/TBD | Not started | - |
| 5. Matrix Execution | 0/TBD | Not started | - |
| 6. Article Polish | 0/TBD | Not started | - |
| 7. CI Expansion + Onboarding Polish | 0/TBD | Not started | - |
| 8. Expand Harness Family + Refresh Article | 0/8 | Not started | - |

---
*Roadmap created: 2026-04-23*
