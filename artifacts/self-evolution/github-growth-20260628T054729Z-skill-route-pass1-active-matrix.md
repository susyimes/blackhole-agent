# Skill Route Discovery Pass 1 Active Matrix

Source digest: `github-growth-20260628T054729.697946Z`

Rollback point: `artifacts/rollback/20260628T054728Z-skill-route-discovery-pass1.md`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: skill ecosystem and state-handoff route evidence.
- `https://github.com/lyra81604/zhengxi-views`: generic skill workflow route evidence.
- `https://github.com/majidmanzarpour/threejs-game-skills`: game/frontend skill workflow route evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`: adjacent general-agent project evidence; it stays in `agent_harness_eval_required`.

## Hypothesis

The active pass-1 proposal IDs should be visible as one replayable controller matrix before activation. Skill workflow evidence may open only local `documentation`, `config`, `test`, or `code_patch` lanes, while general-agent project evidence must first pass through the separate agent-harness eval route.

## Change

- Added `active_pass1_skill_route_discovery_matrix` to `build_skill_route_discovery_proposal_lane_map`.
- Added a frozen fixture for the current digest evidence shape.
- Added regression coverage for the active proposal IDs:
  - `p1-skill-route-discovery-regression`
  - `p2-skill-route-discovery-doc`
  - `p3-agent-harness-eval-fixtures`
  - `p4-route-proposal-schema-guard`
  - `p5-route-hint-to-lane-matrix-test`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k active_pass1_skill_route_discovery_matrix`: passed, 1 passed.
- `python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`: passed, 3 passed.
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`: passed, 57 passed.

## Review Notes

- The new matrix exports body-free metadata and hashes; raw source URLs and upstream bodies remain out of the controller surface.
- Qwen-AgentWorld-style general-agent evidence does not inherit `skill_route_discovery`, direct runtime authority, direct code-patch authority, or external harness execution.
- The self-model was left unchanged because the run produced a concrete behavior path and the existing self-model preference did not need correction.
