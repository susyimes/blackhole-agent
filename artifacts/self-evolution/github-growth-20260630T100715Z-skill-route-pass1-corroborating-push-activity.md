# Skill Route Discovery Pass 1: Corroborating Push Activity

Source digest: `github-growth-20260630T100715.128640Z`

Capability window: `skill-route-discovery`, pass 1 of 4

Rollback point:

- Branch: `codex/blackhole-evolve/20260630T100817.990596-create-a-bounded-skill-route-discovery-validatio`
- HEAD: `19cf5da80c7b4a9707054c9c472325ff9750d685`
- Ref: `refs/blackhole-rollback/20260630T100713Z-skill-route-discovery-pass1`
- Artifact: `artifacts/rollback-20260630T100713Z-skill-route-discovery-pass1.md`

Focused evidence review:

- Reviewed the carried zhengxi-views evidence URL only for route shape.
- Reusable lesson: explicit public Agent Skill workflow evidence can justify a bounded local validation lane, but generic related push activity should remain corroborating freshness evidence.
- No upstream code was imported, installed, executed, exported, or activated.

Local change:

- `skill_route_activity_pressure` now separates independent implementation evidence item IDs from low-detail push activity item IDs.
- Low-detail push events are marked `low_detail_pushes_independent_implementation_evidence_allowed: false`.
- Added a zhengxi-shaped regression proving one repository trend plus two related generic push events stays in bounded `skill_route_discovery` lanes and rejects push-only implementation proposals.

Validation:

```powershell
pytest tests/test_proposal_eval.py -q -k "zhengxi_skill_route_push_activity or skill_route_discovery_enforces_lanes_refs_limits_and_uncertainty or route_hint_lane_map_is_bounded_metadata_only_for_skill_discovery"
```

Result: passed, 3 passed and 22 deselected.

Self-model:

- Read before modification selection.
- Left unchanged because the current preference already permits rollback-backed local behavior changes and does not conflict with corroborating-only push handling.

