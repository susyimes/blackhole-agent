# Skill Route Discovery Pass 1

Source digest: github-growth-20260624T091355.812671Z

## Evidence

- https://github.com/dongshuyan/compass-skills exposes a skill ecosystem with `skills/`, `AGENTS.md`, `PUBLICATION_AUDIT.md`, `SECURITY.md`, and `skills.sh.json` repository shapes.
- https://github.com/lyra81604/zhengxi-views presents as a source-cited domain research agent skill with explicit advice-boundary language.
- https://github.com/majidmanzarpour/threejs-game-skills presents as a Three.js browser game skill bundle with workflow, QA, scaffold, and asset/provider boundary signals.
- https://github.com/omnigent-ai/omnigent presents as a general agent framework and meta-harness, supporting the local distinction between skill-route discovery and agent-harness evaluation.

## Hypothesis

Skill-oriented public repositories should become bounded local proposal lanes only. The harness should make it visible that route-hinted skill evidence is not expanding evidence URLs beyond selected digest evidence and is not becoming runtime execution, provider launch, or external skill activation.

## Change

- Added `skill_route_discovery_evidence_url_expansion_policy` to the skill-route harness output.
- Exposed evidence-item registry counts in the harness registry summary.
- Added a focused current-pass fixture for `compass-skills`, `zhengxi-views`, and `threejs-game-skills`.
- Added regression coverage that the current pass routes only to documentation/config/test/code_patch lanes, hashes or suppresses raw URLs, and reports zero URL expansion.

## Rollback

- Rollback artifact: `artifacts/rollback/20260624T091355Z-skill-route-discovery-pass1.txt`
- Rollback ref: `refs/rollback/blackhole-agent/20260624T091355-skill-route-discovery-pass1`

## Validation

- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_pass_skill_shapes or local_harness_eval_runs_pass_and_fail_fixtures or agent_harness_eval_lane_maps_general_agent_project_claims"`: passed
- `pytest tests/test_skill_routing.py -q -k "evidence_urls or current_window_skill_workflow_signals or classifies_body_free"`: passed
- `pytest tests/test_harness_eval.py tests/test_skill_routing.py -q`: 185 passed

## Review Notes

- Self-model left unchanged. It already prefers rollback-backed, locally validated behavior changes over validation-report-only work.
- No upstream code was imported, installed, executed, or enabled.
- Raw evidence URLs remain omitted or hashed in harness outputs.
