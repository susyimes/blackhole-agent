# Evolution: skill-route-discovery pass 2

Digest: github-growth-20260712T191308.244484Z
Generated: 2026-07-12T19:13:08.244484Z
Branch: grok/blackhole-evolve/20260712T191351.135705-compound-skill-route-discovery-capability-pipeli
Rollback ref: refs/rollback/blackhole-agent/20260712T191447Z-skill-route-discovery-pass2

## Selected lesson

Compound skill_route_discovery_capability_pipeline pass work for reverse-flow-skill:
lock `codex_workflow_gate` + `skill_route_discovery_first` into a bounded local
test validation lane before any apply unlock (`prop-skill-pipeline-reverse-flow-test`).

- reverse-flow-skill → criteria-driven `skill_route_discovery_local_comparison`
- comparison stages: classifier / route_profiles / bounded_local_apply_lanes
- unlock only the preferred local `test` lane when criteria pass
- rnskill stays a companion `generic_skill_workflow` documentation profile on the same pipeline
- fortress remains adjacent `agent_harness_eval_required`
- agent-chief remains `privacy_boundary_review_only`
- `runtime_action=none`; external skill execution, provider launch, remote apply denied

## Local capability

- `evaluate_skill_route_discovery_local_comparison` — body-free criteria packet
- `build_skill_route_discovery_reverse_flow_test_validation_lane` — pass-2 operator surface
- Nested on `skill_route_discovery_capability_pipeline` as `local_comparison` and
  `reverse_flow_test_validation_lane`
- `apply_local_comparison=False` preserves the pass-1 `ready_for_local_comparison` gate

## Self-model

Updated Skill Route Discovery Habit from pass 1 establishment to pass 2 reverse-flow
local test validation lane; kept upstream-evidence habit as completed template.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k "skill_route_discovery_capability_pipeline or skill_route_discovery_local_comparison or self_evolution_plan_carries_skill_route or architecture_links or skill_route_discovery_doc_records_capability_pipeline"
```

Result: 7 passed, 138 deselected.

## Review notes

- Pass 3 should deepen rnskill documentation / config-gate operator surfaces without
  splitting into isolated fixtures.
- Fortress remains harness-eval only; do not inherit skill-route lanes.
- Agent-chief remains review-only; no raw evidence URL export.
- Activation, push, promotion, provider launch, external skill execution, remote
  execution, and restart remain supervisor-owned and denied by this surface.
