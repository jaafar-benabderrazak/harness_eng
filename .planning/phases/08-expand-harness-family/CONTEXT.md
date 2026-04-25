# Phase 8 Context — User Decisions

Captured 2026-04-25 via inline `/gsd:discuss-phase` substitute. All design choices below are LOCKED for this phase; the planner and implementers must respect them.

## Architectural decisions (8 harnesses)

### 1. `multi_agent` — message history scope: **isolated**

Each of planner / executor / critic has its own message history. Structured handoff messages are explicitly copied between them via the harness orchestration code, not via shared state.

- **Why:** faithful to CrewAI / AutoGen semantics. The whole *point* of multi-agent harnesses is that each agent has a focused context — a shared log defeats that.
- **Cost implication:** ~3× the tokens of a single-log harness. Document this in the article's per-harness `weaknesses` section.
- **Implementation note:** the harness owns the orchestration loop; each agent call gets only the messages relevant to its role.

### 2. `tree_of_thoughts` — candidate scoring: **heuristic**

Score each candidate selector by `(num_matched_nodes / mean_text_length_per_match)`, normalized. Deterministic — no extra model call to rank.

- **Why:** keeps the harness comparable on cost. A model-judged variant doubles per-cell cost and complicates the wall-clock comparison.
- **Trade-off accepted:** less faithful to the original ToT paper (which uses model self-evaluation). Document this in the harness's `weaknesses` block as "scoring is heuristic, not model-judged — a paper-faithful variant would be a separate harness."

### 3. `react_with_replan` — loop-detection trigger: **two consecutive NO_MATCH on same selector**

When the executor fires the same CSS selector twice in a row and both return NO_MATCH, trigger a `replan` model call before continuing the ReAct loop.

- **Why:** cheapest signal that catches the most common stall pattern observed in the existing `react` traces (selector-retry-without-revision).
- **Implementation note:** detection lives in the harness loop body, comparing the most-recent two tool_call args. Replan call shares the same message context.

### 4. `self_consistency` — HTML voting: **per-field majority**

For HTML extraction (field dicts), compute majority independently per field across N=5 samples. Final answer = `{field_k: majority(samples[*][field_k]) for k in fields}`.

- **Why:** resilient. One wrong field on one sample doesn't tank the whole record.
- **Code-gen voting:** for code-gen, the majority is over the full submitted code string after AST normalization (whitespace + comment stripping). Document this asymmetry in the article.

### 5. `program_aided` — execution sandbox: **subprocess.run with 5s timeout**

Add a `run_python` tool that writes the submitted code to a tempfile and executes via `subprocess.run` with a 5-second timeout. Capture stdout/stderr. Return both to the model as the tool result.

- **Why:** matches the existing `test_driven` security model (`run_tests` is also subprocess-based). Reuses the safety pattern. Killable by timeout.
- **Tool addition:** the new `run_python` tool added to `tools.py` is a Phase 8 file change — counts as a freeze-tag move, requires `harnesses-frozen` re-anchor.

### 6. `tool_use_with_validation` — schema source: **tools.py existing schemas**

Validate every tool call against the JSON schema already declared for that tool in `tools.py`. No per-harness override.

- **Why:** zero new infrastructure. The schemas already exist; validation is just running them. Easy to keep in sync.
- **Implementation:** add a JSON-schema validator (jsonschema lib already a transitive dep, or add it explicitly) to the harness's tool-call handler. On schema violation, return a structured error tool_result and retry up to 3 times before failing the cell with a documented `failure_mode = "schema_validation_exhausted"`.

### 7. `streaming_react` — Ollama compatibility: **skip-with-note**

If Ollama streaming tool-use semantics don't match Anthropic's 1:1 (i.e., `submit_answer` token sequences can't be reliably detected mid-stream on Ollama), the harness is excluded from the local-model matrix and documented as Anthropic-only.

- **Verification step (must run during planning):** test Ollama's streaming tool-use behavior against the existing model wrapper. If it works, run `streaming_react` in the matrix. If not, mark it `task_type = []` (excluded from matrix) and document in HARNESSES_FROZEN.md why.
- **Why this matters:** running an Anthropic-only harness in a glm-4.7-flash comparison is apples-to-oranges. Better to exclude with a note than mislead the matrix.
- **Implementation note:** if Ollama-incompatible, the harness file still exists with full implementation against the Anthropic backend. It just isn't registered in `HARNESSES_BY_TASK_TYPE` for the local-model run. Could be enabled in a future Anthropic-backend run.

### 8. `cached_react` — cache scoping: **cell-scoped**

The `(html_hash, selector)` → result cache lives only for the duration of one (harness, task, seed) cell. It is reset between cells.

- **Why:** seed independence. If the cache leaked across seeds, sample N+1 would benefit from sample N's tool calls — that breaks the statistical model.
- **What it amortizes:** within a cell, if the model retries the *same* selector multiple times in a single ReAct loop (which the existing `minimal` and `plan_execute` traces show happens often), the cached version returns instantly without re-executing the CSS selector. The article framing: this harness shows what `react` *would* cost if tool calls were free.

## Cross-cutting decisions

### Freeze tag move

The freeze tag `harnesses-frozen` moves forward exactly once during this phase: AFTER all eight harnesses are merged AND `tools.py` (with the new `run_python` tool) is finalized AND the runner has been updated to register them, but BEFORE any matrix run against them. Logged in `HARNESSES_FROZEN.md` with reason "Phase 8 harness expansion" and per-file SHAs.

### Matrix runs are gated on user confirmation

The matrix re-run is operationally expensive (~3 hours of local CPU on glm-4.7-flash). The implementation phase ends at "harnesses + freeze move + tests green." The user explicitly triggers the matrix re-runs (via existing `scripts/run_full.py` and `scripts/run_code_benchmark.py`) — Phase 8's plans should NOT auto-run the matrix.

### Article refresh happens AFTER matrix run

Article and Medium-HTML updates are downstream of fresh numbers. Plans for the article work should be sequenced so they execute only after the matrix re-runs produce updated `runs/<id>/` outputs.

### Test coverage requirement

Every new harness must ship with:
1. AST seal test — passes the existing `test_harness_registry.py` discovery + tool-allowlist enforcement.
2. Per-harness control-flow pytest — model-mocked, asserts the documented control flow (e.g., for `multi_agent`, asserts that planner is called before executor, that exactly 3 distinct system prompts appear).
3. Freeze-gate test — passes the runner pre-flight diff check.

## Out of scope

- **Cross-backend matrix on Anthropic.** This phase's matrix runs on the existing default backend (Ollama + glm-4.7-flash). An Anthropic-backend run is a separate operational phase, deferred.
- **`streaming_react` faithfulness on Ollama.** If the verification step in decision #7 finds Ollama incompatible, that's documented and accepted. No work to make Ollama streaming match Anthropic.
- **Cost-savings claims for `cached_react`.** The cell-scoped cache is intentionally narrow. Article should not claim cross-run cost savings — only within-cell amortization.
