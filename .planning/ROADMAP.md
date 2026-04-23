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

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Audit and Harden Scaffold | 0/5 | Not started | - |
| 2. Methodology Freeze | 0/TBD | Not started | - |
| 3. Multi-Seed + Statistics | 0/TBD | Not started | - |
| 4. Runner Manifests + Tool-Allowlist Enforcement | 0/TBD | Not started | - |
| 5. Matrix Execution | 0/TBD | Not started | - |
| 6. Article Polish | 0/TBD | Not started | - |
| 7. CI Expansion + Onboarding Polish | 0/TBD | Not started | - |

---
*Roadmap created: 2026-04-23*
