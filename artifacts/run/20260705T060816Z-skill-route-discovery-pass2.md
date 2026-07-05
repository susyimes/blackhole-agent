# Skill Route Discovery Pass 2

Source digest: `github-growth-20260705T060819.666814Z`

## Hypothesis

The active reverse-flow and BioNeMo skill-workflow signals should be exposed as
one bounded, operator-visible pass-2 lane before activation. Reverse-flow-style
Codex workflow evidence must prove `skill_route_discovery_first`; generic
skills/toolkit/plugin evidence should stay generic unless it carries an actual
Codex or workflow-gate signal. General-agent trends remain adjacent
`agent_harness_eval_required` rows.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`

## Changes

- Added `current_pass2_skill_route_operator_lane` to the proposal route map.
- Narrowed Codex workflow-gate profile detection so generic plugin or skills
  catalog language does not become Codex-specific without Codex or workflow-gate
  evidence.
- Added a focused pass-2 regression for the current active window.
- Updated `docs/skill-route-discovery.md` with the pass-2 replay surface.

## Rollback

Rollback point:
`artifacts/rollback/20260705T060816Z-skill-route-discovery-pass2/rollback-point.md`

Rollback ref:
`refs/rollback/20260705T060816Z-skill-route-discovery-pass2`

## Validation

```powershell
python -m pytest tests/test_github_growth.py tests/test_skill_routing.py -q -k "current_pass2_skill_route_operator_lane or current_pass1_skill_route_validation_matrix or 20260705T052819 or bionemo"
```

Result: passed, `4 passed, 382 deselected`.

## Review Notes

- No self-model edit was made; the current self-model already matches this
  run's preference for rollback-backed, locally validated behavior changes.
- No activation, external skill execution, provider launch, remote execution, or
  raw evidence export was added.
