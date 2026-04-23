# Harness Freeze Manifest

**Freeze date:** 2026-04-23
**Freeze commit SHA:** resolve with `git rev-parse harnesses-frozen` (tag pins an exact commit; self-referencing the SHA in this file is a chicken-and-egg problem, so the tag is the source of truth)
**Git tag:** `harnesses-frozen`

## Why this exists

The entire experiment depends on one invariant: the five harnesses, their shared tool dispatcher, and the single-import-site model client cannot be edited after results are seen. Without this discipline, the comparison is invalid — the classic "peek-and-patch" failure mode. The `harnesses-frozen` git tag plus the runner's `check_freeze_gate()` pre-flight make this discipline structural rather than procedural.

## Gated paths (runner refuses to execute if any of these have diverged from the tag)

- `src/harness_eng/harnesses/`
- `src/harness_eng/tools.py`
- `src/harness_eng/model.py`

## Per-file blob SHAs at freeze commit

| Path | Blob SHA |
|------|----------|
| `src/harness_eng/harnesses/base.py` | `15ce725022d41ec5eb9215f296690b702a7acdbf` |
| `src/harness_eng/harnesses/single_shot.py` | `c3291fe52907323f8cc7608794313725dd8a1907` |
| `src/harness_eng/harnesses/react.py` | `2ffce6543a69439c290250e54bc0ddf7e50788d1` |
| `src/harness_eng/harnesses/plan_execute.py` | `ae154a6a67baf0ca99c8e48c9c7c1d15b0c61479` |
| `src/harness_eng/harnesses/reflexion.py` | `375bd24946c56547b20971474ecbace932f6151c` |
| `src/harness_eng/harnesses/minimal.py` | `de2e162d68809573b928aef0e49323aca3832c56` |
| `src/harness_eng/tools.py` | `fddabd878b3314965074b231b5e75ed0dfd278c1` |
| `src/harness_eng/model.py` | `4d263754cecf50da47756ab2d19b58ee0da471f6` |

## What can still change post-freeze

- `src/harness_eng/runner.py` — the orchestration layer (adding seeds, manifests, tool-allowlist assertions) is outside the experimental control
- `src/harness_eng/analysis.py`, `src/harness_eng/trace_viewer.py` — read-only artifacts consuming the matrix output
- `src/harness_eng/cost_estimator.py`, `src/harness_eng/pricing.py` — estimation / cost math
- `src/harness_eng/config.py` — model id/temperature/max_tokens: not supposed to change, but not technically gated (change here would be visible in git history)
- `src/harness_eng/trace.py`, `src/harness_eng/grader.py` — already hardened in Phase 1; changes post-freeze are visible in git history

If any of the gated files need to change after freeze, the tag must be moved (which visibly invalidates the prior matrix run) and the article must document the reason. No quiet edits.

## Verification

At any time:

```bash
git diff harnesses-frozen HEAD -- src/harness_eng/harnesses/ src/harness_eng/tools.py src/harness_eng/model.py
```

An empty diff means the experiment is still valid. A non-empty diff either reflects a legitimate re-tag (with article-level justification) or a methodology violation.
