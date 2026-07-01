# Skill Route Discovery Pass 3 Activation Review

- Source digest: `github-growth-20260701T202302.440528Z`
- Capability slice: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260701T202354.689911-add-or-run-a-bounded-skill-route-discovery-valid`
- Rollback: `artifacts/rollback-20260701T202301Z-skill-route-discovery-pass3-current-window.md`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public repository exposes explicit Skill package signals
  including `SKILL.md`, `skill.yml`, references, evals, and scripts.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent project evidence; no skill route activation.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous agent project evidence; no skill route activation.
- `https://github.com/ksimback/looper`: review-gated agent loop project evidence; no skill route activation.
- `open-reverselab` proposal remains review-only at the offensive-behavior boundary.

## Hypothesis

Mixed trend windows that contain one explicit Skill-shaped repository and several general agent projects should expose a
pass-3 operator lane before activation. The lane should allow only bounded local skill-route work
(`documentation`, `config`, `test`, `code_patch`), keep adjacent agent projects behind `agent_harness_eval_required`,
and keep automation/bug/security-adjacent evidence review-only.

## Changes

- Added `github-growth-20260701T202302.440528Z` recognition to the pass-3 activation review lane.
- Added review-only anchor metadata for `p3-agent-automation-bug-eval-open-reverselab`.
- Added direct and harness replay fixtures for the current digest.
- Added direct regression coverage and harness regression coverage.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260701T202302`
- `python -m pytest tests/test_harness_eval.py -q -k 20260701T202302`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs or 20260701T202302"`
- `python -m pytest tests/test_harness_eval.py -q`

All validation passed.

## Review Notes

- No runtime execution, provider launch, external harness execution, raw upstream body export, or skill activation was
  added.
- `open-reverselab` remains review-only; this pass records the boundary but does not implement security automation or
  bug-analysis behavior.
- `docs/self-model.md` was read and left unchanged because it already matches the current run: it is descriptive only
  and external policy remains authoritative.
