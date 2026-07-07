# Skill Route Discovery Pass 3 Skill Workflow Probe

Source digest: `github-growth-20260707T232200.034561Z`

Rollback ref:
`refs/rollback/blackhole-agent/20260707T232158Z-skill-route-discovery-pass3`

Rollback artifact:
`artifacts/rollback/20260707T232158Z-skill-route-discovery-pass3/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`
- `https://github.com/Pluviobyte/rnskill`

## Hypothesis

Mixed public skill-workflow repositories should become bounded local route
lanes before activation. Codex-specific workflow-gate evidence needs a stricter
profile check, generic SKILL.md collection evidence should be documentable, and
domain-specific toolkit evidence should stay behind citation, advice, data, and
provider boundary validation.

## Local Change

- Added a frozen current-digest fixture for reverse-flow, rnskill, and BioNeMo.
- Extended `skill_route_discovery_current_pass3_proposal_lane` for this digest.
- Added focused tests for allowed lanes, route profiles, validation gates,
  local validation requirements, and runtime/activation denials.
- Documented the current pass-3 route in `docs/skill-route-discovery.md`.

## Self-Model Decision

`docs/self-model.md` stayed unchanged. The current self-model already supports
rollback-backed local behavior changes with narrow review boundaries, and this
run had a concrete behavior/test/documentation path.

## Activation Notes

No upstream code, install scripts, prompts, skills, providers, remote execution,
profile writes, memory writes, push, promotion, restart, or external harness
execution were activated. Runtime action remains `none`.

Replay:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260707T232200
python -m pytest tests/test_docs_contracts.py -q -k 20260707T232200
```
