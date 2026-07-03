# Skill Route Discovery Pass 2: Fork Cluster Validation

- Source digest: github-growth-20260703T070049.855381Z
- Capability slice: skill-route-discovery
- Pass: 2 of 4
- Rollback ref: refs/blackhole/rollback/20260703T070048Z-skill-route-discovery-pass2
- Rollback artifact: artifacts/rollback-20260703T070048Z-skill-route-discovery-pass2.md

## Evidence Interpreted

The carried reverse-flow-skill fork cluster exposes public Codex/AI Agent skill
package signals: `skills/reverse-flow/SKILL.md`, references, scripts, local
sandbox or CTF reverse-analysis framing, and workflow gate language. This is
route-discovery evidence only.

The focused external review of `lingbol088-spec/reverse-flow-skill` found
install/run style upstream workflow pressure, so this run kept the local route
body-free and non-executable. Fork activity is treated as correlated pressure,
not as additional implementation authority.

## Local Change

Added `github-growth-20260703T070049.855381Z` as an explicit pass-2
`current_digest_pass2_local_validation_lane`.

The lane maps:

- `p1-skill-route-discovery-codex-workflow` to the local `test` lane.
- `p2-generic-skill-route-discovery` to the local `documentation` lane.
- Qwen-AgentWorld and Fundamental-Ava to `p3-agent-harness-eval-baseline`.
- Workflow-only Seedance evidence to `p4-workflow-agent-eval-lane`.

All surfaces keep `runtime_action: none` and deny install, provider launch,
external skill activation, external harness execution, remote execution, raw URL
export, replay command export, target path export, and upstream body export.

## Validation

Focused validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260703T070049
```

Result: 1 passed, 204 deselected.

Shared skill-routing validation:

```powershell
python -m pytest tests/test_skill_routing.py -q
```

Result: 205 passed.

## Review Notes

The self-model was left unchanged. Its current preference for locally validated
evolution already matches this pass: use rollback-backed local changes while
keeping only unsafe or privacy-leaking routes review-only.
