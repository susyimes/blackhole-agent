# Skill Route Discovery Pass 3 Route-To-Validation

- Source digest: `github-growth-20260704T170435.079487Z`
- Theme: `skill-route-discovery`
- Rollback ref: `refs/rollback/20260704T170433Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260704T170433Z-skill-route-discovery-pass3/rollback-point.md`

## Evidence

Reviewed the bounded proposal evidence URLs:

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`

Reusable lesson: public repositories that expose skill workflow artifacts can
justify a local validation lane, but the lane remains bounded to documentation,
config, test, or code_patch. General agent projects without a skill route hint
remain behind `agent_harness_eval_required` until local harness evidence exists.

## Hypothesis

The active pass-3 digest should produce an operator-visible route-to-validation
lane instead of relying on prior fixtures. `zhengxi-views` should validate the
generic/source-cited skill lane, `reverse-flow-skill` should validate the Codex
workflow gate with `skill_route_discovery_first`, and Qwen-AgentWorld plus
Fundamental-Ava should remain adjacent harness-eval evidence with no direct
runtime or code_patch route.

## Local Change

- Added source digest recognition for `github-growth-20260704T170435.079487Z`.
- Added the frozen fixture
  `tests/fixtures/skill_route_discovery/current_digest_20260704T170435_pass3_route_to_validation.json`.
- Added focused regression coverage for the active proposal IDs, bounded lanes,
  Codex workflow-gate ordering, body-free output, and adjacent agent-harness
  gating.
- Documented the current handling path in `docs/skill-route-discovery.md`.

## Validation

`python -m pytest tests/test_skill_routing.py -q -k 20260704T170435`

Result: passed.

## Review Notes

- Self-model left unchanged; it already favors rollback-backed local behavior
  improvements over validation-report-only work, and this run's useful gap was
  in the operator-visible pass-3 route surface.
- No external skill activation, external agent activation, external harness
  execution, provider launch, remote execution, profile write, memory write,
  push, promotion, or restart was performed.
