# Skill Route Discovery Pass 1 Local Lanes

Source digest: `github-growth-20260709T073527.111052Z`

## Hypothesis

The current evidence window contains two skill-workflow repositories and two adjacent general-agent repositories. The reusable lesson is that skill and workflow evidence should become bounded local validation lanes, while general agent projects without skill route hints should remain behind `agent_harness_eval_required` before any documentation, test, or code patch follow-up.

## Evidence

- `trend:lingbol088-spec/reverse-flow-skill-1`: Codex/agent skill workflow signals; routed to `test`.
- `trend:Pluviobyte/rnskill-1`: generic agent/skill/skills workflow signals; routed to `documentation`.
- `trend:SmileLikeYe/agent-chief-1`: general agent project without skill route hints; gated to `agent_harness_eval_required`.
- `trend:Tencent-Hunyuan/Hy3-1`: general agent/model project without skill route hints; gated to `agent_harness_eval_required`.

Raw upstream bodies and raw evidence URLs are not exported by the lane.

## Changes

- Added `current_digest_20260709T073527_pass1_validation_lane` to `build_skill_route_discovery_proposal_lane_map`.
- Exposed the lane through `evaluate_skill_route_discovery_lane`.
- Added routing and harness tests for the current digest.
- Left `docs/self-model.md` unchanged because it already matches the run evidence: rollback-backed local validation was the useful path, not a self-description edit.

## Rollback

Rollback artifact: `artifacts/rollback/20260709T073525Z-skill-route-discovery-pass1-local-lanes/rollback-point.md`

Rollback ref: `refs/rollback/20260709T073525Z-skill-route-discovery-pass1-local-lanes`

Rollback remains explicit and destructive; no rollback command was run.

## Validation

- `python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260709T073527`
  - Result: `2 passed, 729 deselected`
- `python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k "20260709T073527 or 20260709T071527 or 20260709T061527"`
  - Result: `6 passed, 725 deselected`

## Review Notes

- No external skill activation, external harness execution, provider runtime launch, promotion, push, or restart was performed.
- General agent projects remain blocked from direct local lanes until a separate agent harness evaluation exists.
- This is pass 1 of 4 for the active skill-route-discovery window; the operator-visible next action is to replay the new pass-1 lane and continue to pass 2.
