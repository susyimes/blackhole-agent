# Skill Route Discovery Pass 2 Route Priority

- Source digest: `github-growth-20260706T151555.739121Z`
- Branch: `codex/blackhole-evolve/20260706T151640.592748-add-a-bounded-skill-route-discovery-validation-f`
- Rollback ref: `refs/rollback/blackhole-agent/20260706T151554Z`
- Rollback artifact: `artifacts/rollback/20260706T151554Z-skill-route-discovery-pass2.md`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill` carried an explicit `skill_route_discovery` signal and local skill/workflow shape.
- `https://github.com/shepherd-agents/shepherd`, `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, and `https://github.com/TianhangZhuzth/Fundamental-Ava` were adjacent general-agent project signals without an explicit local skill route.

## Hypothesis

Mixed skill-route windows need an operator-visible priority queue before activation: explicit skill-route evidence should validate first through bounded local lanes, while adjacent general-agent projects remain queued behind agent-harness evaluation without inheriting skill-route permissions.

## Change

- Extended `build_skill_route_discovery_validation_route_packet` with:
  - `route_priority_policy`
  - `route_validation_queue`
  - `route_validation_queue_status`
  - `operator_next_action`
  - row-level `validation_priority`, `validation_order`, and `priority_reason`
- Added a current pass-2 fixture for the reverse-flow plus four general-agent project window.
- Added regression coverage proving route hints influence validation order without enabling runtime, remote execution, external harness execution, or direct implementation lanes for general-agent rows.
- Documented the pass-2 queue in `docs/skill-route-discovery.md`.

## Self-Model Decision

`docs/self-model.md` was left unchanged. Its current preference already covers the evidence-backed choice made here: prefer rollback-backed, locally validated behavior changes over standalone reports while keeping permission expansion out of route evidence.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "validation_route_packet or current_digest_pass2_prioritizes_route_hints"`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest_pass3_builds_agent_harness_intake"`: passed, 1 test.
- `python -m pytest tests/test_proposal_eval.py -q -k "route_hint_lane_map_is_bounded_metadata_only_for_skill_discovery or pass2_route_evidence_lane_source_uses_route_hints_and_classification"`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 341 tests.

## Review Notes

- The queue is metadata only. It does not install, enable, clone, execute, launch providers, export raw source URLs, or grant new permissions.
- General-agent projects still require bounded local agent-harness evaluation before documentation, test, or code_patch lanes can be selected.
