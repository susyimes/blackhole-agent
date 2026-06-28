# Blackhole Run: skill-route-discovery pass 3

- Source digest: github-growth-20260628T154729.643073Z
- Branch: codex/blackhole-evolve/20260628T154820.165345-add-or-extend-local-tests-that-verify-skill-rout
- Rollback ref: refs/blackhole-rollback/20260628T154903Z
- Rollback artifact: artifacts/rollback/20260628T154903Z-skill-route-discovery-pass3.md
- Evidence reviewed: proposal window URLs for COMPASS skills, zhengxi-views, threejs-game-skills, and Qwen-AgentWorld.

## Hypothesis

Pass-3 skill-route discovery should expose an operator-visible final scope and
validation gate surface recomputed from deterministic route evidence. Candidate
proposal scope or validation-gate text must not be trusted for activation.

## Change

- Added `skill_route_discovery_pass3_controller_recomputed_scope_gate` to the
  route-hint lane map pass-3 handoff.
- Skill workflow rows are mapped only to bounded local validation lanes.
- Adjacent general-agent rows are held as `pending_agent_harness_eval` until a
  local harness evaluation result exists.
- Candidate-supplied scope and validation gate metadata is marked ignored.

## Validation

```powershell
pytest tests/test_proposal_eval.py -q -k "route_hint_lane_map_exposes_current_pass3_skill_route_handoff or skill_route_discovery_enforces_lanes_refs_limits_and_uncertainty or route_hint_lane_map_is_bounded_metadata_only_for_skill_discovery"
pytest tests/test_proposal_eval.py -q
pytest tests/test_harness_eval.py -q -k "skill_route_discovery and pass3"
```

All validation commands passed.

## Self-Model

Left unchanged. The current text already matches this run's operating policy
and does not add route-specific claims that need to be corrected.
