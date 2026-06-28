# Skill Route Discovery Pass 4 Route Completion

- Source digest: `github-growth-20260628T104729.721650Z`
- Branch: `codex/blackhole-evolve/20260628T104836.166336-add-or-run-a-bounded-local-skill-route-discovery`
- Rollback ref: `refs/rollback/20260628T104728Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260628T104728Z-skill-route-discovery-pass4.md`

## Hypothesis

The active skill-route-discovery slice already had several validation fixtures
and pass-4 packets, but the current proposal aliases were not exposed as one
final operator-visible completion lane. A controller-facing completion surface
should map the active generic/source-cited, game/frontend, and state-handoff
skill evidence into bounded local lanes while keeping adjacent general-agent
projects outside skill-route authority.

## Change

- Added `current_window_pass4_route_completion_lane` to the skill-route proposal
  lane map.
- Added a fixture for the current digest window carrying zhengxi-views,
  threejs-game-skills, COMPASS Skills, Qwen-AgentWorld, and Looper-style
  adjacent general-agent evidence.
- Added regression coverage proving the three active proposal aliases complete
  as bounded documentation/config/test/code_patch lanes only.
- Documented the current pass-4 route completion interpretation.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q
python -m pytest -q
```

Results:

- `74 passed in 0.28s`
- `480 passed in 8.02s`

## Review Notes

- The completion lane exports proposal IDs, selected item IDs, route profiles,
  source hashes, bounded lane names, validation gates, and replay command
  hashes only.
- It does not export raw source URLs, raw evidence URLs, raw target paths, raw
  replay commands, or upstream bodies.
- Runtime action, install, upstream skill activation, external harness
  execution, provider launch, profile writes, memory writes, remote execution,
  and direct code_patch selection for adjacent general-agent evidence remain
  denied.
- The self-model was read and left unchanged because it already describes the
  local-evolution preference and narrow safety boundary used by this run; it did
  not need a new behavior-shaping rule.
