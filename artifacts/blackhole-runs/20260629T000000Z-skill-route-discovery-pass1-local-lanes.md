# Skill Route Discovery Pass 1 Local Lanes

- Source digest: `github-growth-20260628T174729.552272Z`
- Capability slice: `skill-route-discovery`
- Prepared branch: `codex/blackhole-evolve/20260628T174815.620918-add-or-exercise-a-local-skill-route-discovery-va`
- Rollback ref: `refs/rollback/20260629T000000Z-skill-route-discovery-pass1-local-lanes`
- Rollback artifact: `artifacts/rollback/20260629T000000Z-skill-route-discovery-pass1-local-lanes.md`

## Focused Evidence Review

Reviewed only the carried proposal evidence URLs:

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/QwenLM/Qwen-AgentWorld`

Local interpretation:

- zhengxi-views-style agent/skill evidence is a generic skill workflow route and selects the local test lane.
- Three.js game skill evidence is a `game_frontend_workflow` route and selects the local documentation lane before any frontend behavior change.
- COMPASS-style skill ecosystem handoff evidence is a `skill_ecosystem_state_handoff` route and selects the metadata/config lane.
- Qwen-AgentWorld remains adjacent `agent_harness_eval_required` evidence and does not inherit `skill_route_discovery`.

## Hypothesis

The active pass-1 proposal IDs should be replayable through the existing
`current_digest_pass1_validation_lane` surface before activation. Supporting
the exact `github-growth-20260628T174729.552272Z` aliases makes the controller
handoff auditable without adding install, runtime execution, provider runtime,
external harness execution, memory/profile writes, or raw source export.

## Changes

- Added digest-specific alias support for `p2-threejs-game-skill-routing` and
  adjacent `p4-agent-harness-eval`.
- Added a frozen body-free fixture for the active pass-1 evidence window.
- Added a regression test that verifies the active proposals map only to
  documentation, config, test, or code_patch lanes and keep activation denied.
- Updated route discovery documentation for the current digest pass-1 lane.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py
```

Result: `84 passed in 1.39s`.

## Review Notes

- The self-model was read and left unchanged. Its current preference for
  rollback-backed, locally validated, bounded behavior changes matched this run.
- The fixture remains body-free and cites selected item IDs. It does not import
  upstream bodies or execute external code.
- Unsupported lane pressure in the fixture (`provider_runtime`,
  `runtime_execution`, `install`) is stripped from allowed local lanes while
  deny flags remain visible.

