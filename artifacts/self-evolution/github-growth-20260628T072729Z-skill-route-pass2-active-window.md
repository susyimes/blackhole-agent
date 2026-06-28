# Skill Route Discovery Pass 2 Active Window

Source digest: `github-growth-20260628T072729.647518Z`

Hypothesis: the active pass-2 skill-route window should expose the current
proposal IDs and carried repository evidence as one bounded operator replay lane
before any activation path is considered.

Rollback:

- Ref: `refs/blackhole-rollback/20260628T072728Z`
- Artifact: `artifacts/blackhole-runs/20260628T072728Z/rollback-point.md`

Evidence reviewed:

- `lyra81604/zhengxi-views`: public `SKILL.md`, references, scripts, and evals
  shape a source-cited skill workflow.
- `dongshuyan/compass-skills`: multiple local `SKILL.md` workflows, state
  handoff, task graph, and collaboration-profile signals require metadata-only
  validation before profile or memory routes.
- `majidmanzarpour/threejs-game-skills`: bundled game/frontend skills and
  browser/build validation language justify a documentation-first
  `game_frontend_workflow` lane.
- `QwenLM/Qwen-AgentWorld`: benchmark/model-eval shape remains adjacent
  `agent_harness_eval_required`, not inherited skill-route evidence.

Changed behavior:

- Updated `active_window_pass2_validation_lane` to use active proposal IDs:
  `p1-skill-route-discovery-generic`, `p2-game-skill-profile`, and
  `p3-agent-harness-eval`.
- Expanded the generic pass-2 lane to include COMPASS-style
  `skill_ecosystem_state_handoff` evidence alongside zhengxi-views
  source-cited evidence.
- Added an operator next action for replaying the active-window validation lane
  before activation.
- Kept runtime action, external skill or agent activation, external harness
  execution, provider launch, profile writes, memory writes, remote execution,
  raw source URL export, raw evidence URL export, target path export, and
  upstream body export denied.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k active_window_pass2_validation_lane`
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`

Review notes:

- The self-model was read and left unchanged. Its current preference for
  rollback-backed, locally validated behavior changes matched this run.
- The fixture is body-free and selected-item-id based. It does not import,
  install, execute, or activate upstream skill repositories.
