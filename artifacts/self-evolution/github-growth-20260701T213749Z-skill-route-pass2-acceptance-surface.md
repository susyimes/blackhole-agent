# Skill Route Discovery Pass 2 Acceptance Surface

Source digest: `github-growth-20260701T213749.224965Z`
Capability window: `skill-route-discovery`, pass 2 of 4
Rollback artifact: `artifacts/rollback/20260701T213747Z-skill-route-discovery-pass2.md`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: README-level evidence exposes `SKILL.md`, `skill.yml`, `references/`, `scripts/`, `evals/`, source-cited answers, method-based inference labels, and non-investment-advice boundaries.
- `https://github.com/QwenLM/Qwen-AgentWorld`: README-level evidence describes a general-agent model and `AgentWorldBench` evaluation benchmark across multiple domains, not a skill-route package.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: repository-level evidence describes autonomous, collaborative, socially intelligent agents without a local skill-route manifest signal.
- `https://github.com/ksimback/looper`: repository-level evidence describes review-gated agent loops for Claude Code without a skill-route manifest signal.

## Hypothesis

Pass 2 should expose an operator-visible acceptance decision, not just a replay
fixture: accept the zhengxi progressive skill package as bounded local route
evidence while holding adjacent general-agent projects behind the separate
agent-harness evaluation lane.

## Local Change

- Added `skill_route_discovery_current_digest_pass2_acceptance_surface` to the
  pass-2 local validation lane.
- Specialized current digest proposal IDs for
  `github-growth-20260701T213749.224965Z`.
- Added a local harness fixture and direct regression coverage for the new
  acceptance surface.
- Updated `docs/skill-route-discovery.md` with the pass-2 operator contract.

## Boundaries

- No upstream repository code was cloned or executed.
- No external skill, agent, harness, provider, remote execution, profile write,
  or memory write was enabled.
- Outputs remain body-free: raw source URLs, raw evidence URLs, replay commands,
  target paths, and upstream bodies are not exported by the surface.

## Self-Model Decision

`docs/self-model.md` was left unchanged. The existing preference already covers
the chosen behavior: prefer locally validated implementation over another
validation-report-only artifact, with rollback and explicit uncertainty.

## Validation

Planned focused validation:

```powershell
python -m pytest tests/test_harness_eval.py -q -k "213749 or local_harness_eval_runs_pass"
python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k "current_digest_pass2 or progressive_skill_package"
```
