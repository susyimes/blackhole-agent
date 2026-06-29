# Skill Route Discovery Pass 3 Operator Lane

Source digest: `github-growth-20260629T175904.233445Z`

## Focused Evidence Review

- `https://github.com/dongshuyan/compass-skills`: treated as public skill ecosystem handoff evidence. Local lesson: route to bounded test validation for skill/profile/task-memory boundaries, not install or execution.
- `https://github.com/lyra81604/zhengxi-views`: treated as generic skill workflow evidence. Local lesson: route to bounded documentation/config/test/code_patch lanes with validation retained.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/ksimback/looper`: treated as adjacent general-agent project evidence. Local lesson: require `agent_harness_eval_required` before any documentation, test, or code_patch follow-up; do not inherit skill-route authority.

## Change

- Added a frozen pass-3 current-digest fixture at `tests/fixtures/skill_route_discovery/current_digest_20260629T175904_pass3_operator_lane.json`.
- Updated `current_source_digest_pass3_operator_lane` to expose the current COMPASS and zhengxi route rows plus Qwen-AgentWorld and looper eval-only adjacency.
- Updated `docs/skill-route-discovery.md` with the pass-3 interpretation.
- Left `docs/self-model.md` unchanged because it already describes bounded, rollback-backed local evolution and no new self-description evidence was needed.

## Rollback

- Rollback artifact: `artifacts/self-evolution/github-growth-20260629T175904Z-rollback.md`
- Rollback ref: `refs/blackhole-agent/rollback/20260629T175903Z`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_source_digest_pass3_operator_lane`: passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k "current_source_digest_pass3_operator_lane or current_digest_20260629T173904_pass2_routes_current_skill_lane"`: passed.

## Review Notes

- No upstream code was installed, cloned, executed, or imported.
- Raw upstream URLs remain out of the operator lane packet; source and replay references are hashed.
- General-agent projects remain blocked from runtime/controller behavior until a local harness evaluation fixture exists.
