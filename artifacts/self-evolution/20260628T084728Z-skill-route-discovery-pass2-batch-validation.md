# Skill Route Discovery Pass 2 Batch Validation

Source digest: `github-growth-20260628T084729.600885Z`
Branch: `codex/blackhole-evolve/20260628T084827.637210-add-or-run-a-bounded-local-skill-route-discovery`
Rollback artifact: `artifacts/rollback/20260628T084728Z-skill-route-discovery-pass2-local-lane.md`
Rollback ref: `refs/blackhole/rollback/20260628T084728Z-skill-route-discovery-pass2-local-lane`

## Evidence

- `dongshuyan/compass-skills`: skill ecosystem with task clarification, repo-local memory, handoff, and collaboration profile metadata. Local route: `skill_ecosystem_state_handoff`.
- `lyra81604/zhengxi-views`: source-cited public agent skill workflow with explicit research/advice boundary. Local route: `generic_skill_workflow` for this batch fixture.
- `majidmanzarpour/threejs-game-skills`: Three.js game skill bundle with frontend QA, screenshot, canvas, and asset/provider boundaries. Local route: `game_frontend_workflow`.
- `QwenLM/Qwen-AgentWorld`: general-agent benchmark and model/eval release evidence, not a skill workflow activation route. Local route: adjacent `agent_harness_eval_required`.
- `ksimback/looper`: loop-design and review-gated scheduling evidence, not direct runtime authority. Local route: adjacent `agent_harness_eval_required`.

## Hypothesis

The active pass-2 lane should not report ready unless all three skill/workflow profiles in the proposal are present and bounded to documentation, config, test, or code_patch lanes. Adjacent general-agent or loop-control evidence should be visible to operators as local harness-eval work only, without inheriting `skill_route_discovery` or runtime/controller authority.

## Change

- Tightened `current_pass2_validation_lane` readiness to require `generic_skill_workflow`, `game_frontend_workflow`, and `skill_ecosystem_state_handoff`.
- Propagated the source digest into that lane instead of using only the older fallback digest.
- Exposed `current_pass2_validation_lane` directly from `skill_route_discovery_lane` harness output.
- Added a current wake fixture with three skill-route candidates plus Qwen-AgentWorld and Looper as adjacent eval-only rows.
- Updated documentation and regressions for the stronger pass-2 contract.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "current_pass2_batch_validation_lane or local_harness_eval_runs_pass_and_fail_fixtures"`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k "current_pass2_validation_lane or bounded_route_profile_matrix"`: passed.
- `python -m pytest tests/test_harness_eval.py -q`: passed.
- `python -m pytest tests/test_skill_routing.py -q`: passed.
- `python -m pytest tests/test_docs_contracts.py -q`: passed.

## Review Notes

- No upstream repository code was cloned, installed, executed, or imported.
- Raw source URLs and upstream bodies remain outside the emitted pass-2 packet; source identity is carried by selected item IDs and hashes.
- Self-model unchanged: the existing preference already covers rollback-backed local evolution and narrow safety review boundaries.
