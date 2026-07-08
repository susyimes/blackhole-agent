# Skill Route Discovery Pass 4 Source Evidence Checklist

- Source digest: `github-growth-20260708T094635.494091Z`
- Capability slice: `skill-route-discovery`, pass 4 of 4
- Rollback ref: `refs/blackhole/rollback/20260708T094633Z-pass4-skill-route-discovery-lane`
- Rollback artifact: `artifacts/rollback/20260708T094633Z-pass4-skill-route-discovery-lane/rollback-point.md`

## Evidence

The focused review used the carried evidence URLs only:

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/Pluviobyte/rnskill`
- `https://github.com/shepherd-agents/shepherd`

Observed reusable lesson: route discovery needs an operator-visible checklist
before activation review. Reverse-flow emphasizes trigger and staged workflow
assumptions, rnskill emphasizes multi-skill repository and marketplace metadata
shape, and Shepherd emphasizes retained, reviewable outputs before acceptance.

## Change

Added `skill_route_discovery_source_evidence_checklist` as a body-free pass-4
surface. It is included in:

- `pass4_operator_replay_manifest`
- `active_pass4_operator_activation_packet`
- `active_pass4_operator_review_dossier`

The checklist covers manifest shape, invocation model, permission assumptions,
testability, rollback path, and whether runtime behavior is required. It exports
hashes and counts only.

## Changed Files

- `src/blackhole_agent/skill_routing.py`
- `tests/test_skill_routing.py`
- `docs/skill-route-discovery.md`
- `artifacts/rollback/20260708T094633Z-pass4-skill-route-discovery-lane/rollback-point.md`
- `artifacts/skill-route-discovery-20260708T094633Z-pass4-source-evidence-checklist.md`

## Validation

Focused validation passed:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k "pass4_completion_handoff_queues_adjacent_general_agent_evidence or current_run_pass4_completion_matrix_matches_proposals"
```

Result: `2 passed, 412 deselected`.

## Review Notes

- Self-model unchanged: it already supports rollback-backed local behavior
  changes and did not need a new preference for this run.
- No external skill, agent, harness, provider, promotion, push, restart, or
  remote execution path was enabled.
- Raw source URLs, evidence URLs, replay commands, target paths, candidate
  names, and upstream bodies remain outside the emitted checklist.
