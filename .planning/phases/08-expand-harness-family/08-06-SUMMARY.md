---
phase: 08-expand-harness-family
plan: 06
subsystem: registry+tests+analysis
tags: [registry, integration, ast-seal, palette]
requires:
  - "08-02 (tree_of_thoughts, react_with_replan, cached_react)"
  - "08-03 (multi_agent, self_consistency)"
  - "08-04 (program_aided, tool_use_with_validation)"
  - "08-05 (streaming_react + Ollama verify)"
provides:
  - "HARNESSES dict with 16 entries (8 prior + 8 Phase 8)"
  - "HARNESSES_BY_TASK_TYPE: html_extract=11, code_gen=9 (streaming_react excluded per 08-05-VERIFY FAIL)"
  - "AST seal relaxation: tree.body walk allows deferred imports inside method bodies"
  - "HARNESS_COLORS palette extended to 16 distinguishable hex values"
  - "REQUIREMENTS.md: HARN-08..15 + BENCH-06 + RUN-07 + ANAL-06 marked complete; ART-05 added pending"
affects:
  - "src/harness_eng/harnesses/__init__.py"
  - "src/harness_eng/analysis.py"
  - "tests/test_harness_registry.py"
  - "tests/test_tool_allowlist.py"
  - "tests/test_model_seal.py"
  - "tests/test_code_tasks.py"
  - ".planning/REQUIREMENTS.md"
tech-stack:
  added: []
  patterns:
    - "Conditional registration via _streaming_ok() reading 08-05-VERIFY.md at module import"
    - "tree.body AST walk (not ast.walk) to scope module-level-only import detection"
    - "Defensive HARNESS_COLORS.get(name, fallback) in chart call sites"
key-files:
  created: []
  modified:
    - "src/harness_eng/harnesses/__init__.py"
    - "src/harness_eng/analysis.py"
    - "tests/test_harness_registry.py"
    - "tests/test_tool_allowlist.py"
    - "tests/test_model_seal.py"
    - "tests/test_code_tasks.py"
    - ".planning/REQUIREMENTS.md"
decisions:
  - "streaming_react registered in HARNESSES (so AST seal sees it) but EXCLUDED from HARNESSES_BY_TASK_TYPE (so the matrix skips it). Implements CONTEXT decision #7 skip-with-note path. Driven by 08-05-VERIFY.md outcome FAIL (Ollama OOM on glm-4.7-flash — host has 6.9 GiB, model declares 23.4 GiB)."
  - "AST seal scoped to tree.body (module-level statements only) instead of ast.walk. Deferred imports inside FunctionDef/AsyncFunctionDef bodies (e.g. streaming_react._stream_anthropic) no longer break the seal. Module-level `import anthropic` outside model.py still forbidden."
  - "test_code_gen_harness_lineup expectation widened from len==5 to set-equality with the 9 designed Phase 8 members (auto-fix Rule 1)."
metrics:
  duration_minutes: 4
  tasks_completed: 3
  files_modified: 7
  files_created: 0
  commits: 3
  completed: "2026-04-25T20:21:28Z"
---

# Phase 8 Plan 06: Register Phase 8 Harnesses + Update Tests + Palette Summary

Wired 8 new Phase 8 harnesses (`tree_of_thoughts`, `multi_agent`, `react_with_replan`, `self_consistency`, `program_aided`, `tool_use_with_validation`, `streaming_react`, `cached_react`) into `HARNESSES` and `HARNESSES_BY_TASK_TYPE`, relaxed the AST seal so deferred SDK imports inside method bodies are allowed (`streaming_react._stream_anthropic` legitimately calls `from anthropic import Anthropic`), extended `EXPECTED` whitelist invariants and `HARNESS_COLORS` palette to all 16 harnesses, and added 11 new requirements rows (HARN-08..15, BENCH-06, RUN-07, ANAL-06, ART-05).

## What landed

### `src/harness_eng/harnesses/__init__.py`

- All 8 new harness classes imported at module top.
- `HARNESSES` dict: **16 entries** (5 HTML baselines + 3 code-gen baselines + 8 Phase 8 agent-pattern family).
- `HARNESSES_BY_TASK_TYPE`:
  - `html_extract`: **11 harnesses** — `single_shot, react, plan_execute, reflexion, minimal, tree_of_thoughts, multi_agent, react_with_replan, self_consistency, tool_use_with_validation, cached_react`. `streaming_react` EXCLUDED per 08-05-VERIFY.md outcome FAIL.
  - `code_gen`: **9 harnesses** — `single_shot, react, chain_of_thought, test_driven, retry_on_fail, multi_agent, self_consistency, program_aided, tool_use_with_validation`.
- Conditional registration of `streaming_react` via `_streaming_ok()` which reads `.planning/phases/08-expand-harness-family/08-05-VERIFY.md` at import time and looks for `**Outcome:** PASS`. Currently returns `False` because the verify file shows `**Outcome:** FAIL` (OOM: glm-4.7-flash needs 23.4 GiB; host has 6.9 GiB). Future re-verification on a different backend will automatically flip the matrix membership at next import.

### `tests/test_harness_registry.py`

- `test_all_harnesses_registered`: expected set covers all 16.
- `test_harnesses_instantiate`: unchanged, runs on the 16-harness set.
- `test_no_harness_imports_anthropic_at_module_level`: replaces the previous string-grep check. Walks `tree.body` (module-level statements only) and asserts no `Import`/`ImportFrom` of `anthropic`. Deferred imports inside method bodies (which appear under `FunctionDef.body`, not `tree.body`) pass.

### `tests/test_tool_allowlist.py`

- `EXPECTED` dict extended with 8 new entries:
  - `tree_of_thoughts`: `{css_select, submit_answer}`
  - `multi_agent`: `{read_html, css_select, extract_text, check_syntax, run_tests, submit_answer}` (UNION across HTML+code-gen executor needs)
  - `react_with_replan`: `{read_html, css_select, extract_text, submit_answer}`
  - `self_consistency`: `{submit_answer}`
  - `program_aided`: `{run_python, submit_answer}`
  - `tool_use_with_validation`: `{read_html, css_select, extract_text, check_syntax, run_tests, submit_answer}` (UNION)
  - `streaming_react`: `{read_html, css_select, extract_text, submit_answer}`
  - `cached_react`: `{read_html, css_select, extract_text, submit_answer}`
- `test_every_harness_declares_whitelist` iterates `HARNESSES.items()` and looks each up — all 16 covered.
- `test_step_model_raises_on_extra_tool` and `test_step_model_accepts_subset_of_whitelist` unchanged.

### `tests/test_model_seal.py`

The seal previously used `ast.walk(tree)` which descends into every nested scope. Result: `streaming_react.py`'s legitimate deferred `from anthropic import Anthropic` inside `_stream_anthropic` (only executed when the Anthropic backend is selected) failed the seal.

New behavior: walks `tree.body` only — module-level statements. Module-level `import anthropic` outside `model.py` still forbidden. Deferred imports inside `FunctionDef`/`ClassDef`/`If`/`Try` bodies tolerated. Renamed helper `_imports_anthropic` → `_imports_anthropic_at_module_level` to make scope explicit.

### `src/harness_eng/analysis.py`

`HARNESS_COLORS` extended from 8 to 16 entries. New hex values:

| harness                    | color     | rationale       |
|----------------------------|-----------|-----------------|
| `tree_of_thoughts`         | `#7c3aed` | violet          |
| `multi_agent`              | `#0d9488` | teal-dark       |
| `react_with_replan`        | `#b91c1c` | red-dark        |
| `self_consistency`         | `#1d4ed8` | blue-dark       |
| `program_aided`            | `#a16207` | amber-dark      |
| `tool_use_with_validation` | `#16a34a` | green-mid       |
| `streaming_react`          | `#e11d48` | rose            |
| `cached_react`             | `#7e22ce` | purple-dark     |

All 16 colors distinct. The existing `.get(harness, "#374151")` defensive fallback in chart call sites already handles unknown names — no rendering-code changes needed.

### `.planning/REQUIREMENTS.md`

Added 11 new requirement rows in the v1 section:

- `HARN-08` (tree_of_thoughts) — Complete
- `HARN-09` (multi_agent) — Complete
- `HARN-10` (react_with_replan) — Complete
- `HARN-11` (self_consistency) — Complete
- `HARN-12` (program_aided) — Complete
- `HARN-13` (tool_use_with_validation) — Complete
- `HARN-14` (streaming_react) — Complete
- `HARN-15` (cached_react) — Complete
- `BENCH-06` (Phase 8 matrix integration) — Complete
- `RUN-07` (registry wired into runner; whitelist enforcement covers 16) — Complete
- `ANAL-06` (HARNESS_COLORS palette covers 16) — Complete
- `ART-05` (article refresh covers 16-harness matrix) — Pending (08-08)

Coverage line updated: 49 → 60 total v1 requirements (mapped 60, unmapped 0).

## Test outcomes

- Pre-task baseline: **86 pass / 1 fail** (`test_model_seal::test_only_model_py_imports_anthropic` failing on `streaming_react.py` per Plan 08-05's deferred-items.md note).
- Post-Task-2 (after seal relaxation + EXPECTED + registry): full suite **87/87 GREEN**.
- Post-Task-3 (after HARNESS_COLORS): full suite **87/87 GREEN**.

This is the freeze-tag-move precondition: green tree with the expanded registry.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_code_tasks.py::test_code_gen_harness_lineup` hard-coded lineup size of 5**

- **Found during:** Task 2 full-suite verification.
- **Issue:** The test asserted `len(HARNESSES_BY_TASK_TYPE['code_gen']) == 5`. Phase 8 design (per plan must-haves) widens code_gen to 9 members (adds `multi_agent, self_consistency, program_aided, tool_use_with_validation`). The hard-coded 5 was a Phase 1-7 invariant that needed to track the new design.
- **Fix:** Changed to set-equality against the 9 designed members. Each name is also asserted to be in `HARNESSES`. Docstring updated to state both the historical (5) and current (9) sizes and the rationale.
- **Files modified:** `tests/test_code_tasks.py`
- **Commit:** `199db9b`

**2. [Plan-out-of-scope but listed in important_constraints] Relaxation of `tests/test_model_seal.py`, not just `tests/test_harness_registry.py`**

The plan body referenced relaxing the AST seal in `test_harness_registry.py` only. The user's `important_constraints` block flagged that `test_model_seal.py` is also an AST seal that's currently RED on `streaming_react.py`. Both files were updated with the same `tree.body`-scoped walk pattern. This is the test that was failing in baseline (`86 pass / 1 fail`) — relaxing only `test_harness_registry.py` would have left the suite RED.

### Auth gates

None.

## Self-Check: PASSED

Verified all claimed artifacts exist and all claimed commits are in `git log`:

- `src/harness_eng/harnesses/__init__.py` FOUND (16 entries; html_extract=11, code_gen=9)
- `src/harness_eng/analysis.py` FOUND (HARNESS_COLORS has 16 entries, all distinct)
- `tests/test_harness_registry.py` FOUND (uses tree.body walk; 3 tests)
- `tests/test_tool_allowlist.py` FOUND (EXPECTED has 16 entries)
- `tests/test_model_seal.py` FOUND (tree.body walk; 1 test)
- `tests/test_code_tasks.py` FOUND (lineup test updated to set-equality)
- `.planning/REQUIREMENTS.md` FOUND (11 new rows; HARN-08..15 + BENCH-06 + RUN-07 + ANAL-06 marked Complete; ART-05 Pending)
- Commit `9aa9be8` FOUND (`feat(08-06): register 8 new harnesses + conditional streaming_react`)
- Commit `199db9b` FOUND (`test(08-06): expand registry/allowlist/seal tests for 16 harnesses`)
- Commit `2b92835` FOUND (`feat(08-06): extend HARNESS_COLORS palette to 16 harnesses`)
- `pytest -q` confirmed GREEN: 87/87 tests pass.
