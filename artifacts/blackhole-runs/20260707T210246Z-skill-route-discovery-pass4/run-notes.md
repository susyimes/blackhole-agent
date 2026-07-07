# Blackhole Run: skill-route-discovery pass 4

- Source digest: `github-growth-20260707T130110.277132Z`
- Branch: `codex/blackhole-evolve/20260707T130204.107908-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/rollback/blackhole-agent/20260707T210246Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260707T210246Z-skill-route-discovery-pass4/rollback-point.md`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: treated as Codex workflow-gate skill-route evidence only.
- `https://github.com/Pluviobyte/rnskill`: treated as a generic SKILL.md-compatible skill collection, not as an installable runtime package.
- `https://github.com/shepherd-agents/shepherd` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: treated as general-agent evidence requiring local harness evaluation before follow-up lanes.

## Hypothesis

The final pass should expose an operator-visible validation queue for the current digest instead of another standalone fixture. Skill/workflow repositories may enter only documentation, config, test, or code_patch lanes, while general-agent projects must remain behind `agent_harness_eval_required` with no direct implementation lane before local harness evaluation.

## Changes

- Added `current_digest_20260707T130110_pass4_completion.json` as a frozen current digest fixture.
- Added `skill_route_discovery_current_digest_20260707T130110_pass4_completion_handoff` to the route map.
- Added a focused regression asserting bounded lanes, disabled runtime action, disabled external activation, and general-agent harness gating.
- Documented the current pass-4 replay path in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged because it already states the rollback-backed local validation preference used in this run.

## Validation

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k 20260707T130110
```

Result: passed, 1 test.

## Review Notes

- No upstream skill code was installed, cloned, enabled, or executed.
- Controller output remains body-free: source URLs, evidence URLs, replay commands, target paths, and upstream bodies are not exported by the handoff.
- Restart, promotion, push, and external activation are left to the supervisor.
