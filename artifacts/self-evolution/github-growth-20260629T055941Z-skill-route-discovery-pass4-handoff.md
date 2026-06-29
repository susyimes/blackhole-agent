# Skill Route Discovery Pass 4 Handoff

- Source digest: github-growth-20260629T055941.732014Z
- Theme: skill-route-discovery
- Capability pass: 4 of 4
- Rollback ref: refs/rollback/20260629T055940Z-skill-route-discovery-pass4
- Rollback artifact: artifacts/rollback/20260629T055940Z-skill-route-discovery-pass4.md

## Hypothesis

The current pass should finish with an operator-visible completion handoff, not
another isolated fixture. COMPASS-style skill ecosystem repositories should
produce a bounded documentation lane before any state/profile adoption, while
skill-like Python agent repositories should produce a local test lane. General
agent projects without skill workflow hints should remain adjacent
`agent_harness_eval_required` rows until a local harness evaluation profile is
assigned.

## Evidence Scope

Reviewed only the provided proposal evidence URLs and existing local routing
surfaces. The local fixture keeps raw repository URLs inside test input only;
the generated handoff continues to export hashes and selected item IDs rather
than raw URLs, replay commands, target paths, or upstream bodies.

## Local Change

- Added a current-digest specialization to
  `_skill_route_discovery_current_digest_pass4_completion_handoff` for
  `github-growth-20260629T055941.732014Z`.
- Added a replay fixture covering COMPASS-style state handoff, zhengxi-style
  Python agent skill evidence, and Qwen-AgentWorld/looper as adjacent general
  agent projects.
- Added a regression test proving bounded lanes, denial flags, selected
  proposal IDs, and adjacent harness-eval routing.
- Updated `docs/skill-route-discovery.md` with the pass-4 handoff note.
- Left `docs/self-model.md` unchanged because the run produced a concrete
  behavior improvement and did not change operating preferences.

## Validation

```powershell
python -m py_compile src\blackhole_agent\skill_routing.py
python -m pytest tests/test_skill_routing.py -q -k "20260629_pass4_completion_handoff or current_digest_pass4_completion_handoff_closes_window"
python -m pytest tests/test_skill_routing.py -q
python -m pytest tests/test_docs_contracts.py -q
```

All commands passed.

## Review Notes

No runtime action, install, provider launch, external harness execution, profile
write, memory write, remote execution, raw URL export, replay-command export, or
upstream body export was added. Qwen-AgentWorld and looper remain blocked from
direct local implementation lanes until harness evaluation exists.
