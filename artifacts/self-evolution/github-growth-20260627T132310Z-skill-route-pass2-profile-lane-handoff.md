# Skill Route Discovery Pass 2 Profile Lane Handoff

Source digest: `github-growth-20260627T132310.624297Z`
Branch: `codex/blackhole-evolve/20260627T132423.841906-add-or-extend-local-validation-coverage-for-gene`
Rollback: `artifacts/rollback-20260627T132423Z.md`
Rollback ref: `refs/blackhole-agent/rollback/20260627T132423Z`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public skill repository with `SKILL.md`, references, scripts, evals, and source-cited advisory boundaries.
- `https://github.com/majidmanzarpour/threejs-game-skills`: agent-skill bundle for playable Three.js browser games, specialist workflows, QA, and optional asset generation.
- `https://github.com/dongshuyan/compass-skills`: personal alignment skills system with task/profile/state handoff language.

## Hypothesis

Pass-2 route evidence is already bounded by fixture validation, but operators need one compact handoff that maps active proposal IDs to profile-specific local lanes before later activation review. The handoff should show downgraded unsupported route pressure while preserving the no-runtime boundary.

## Local Change

- Added `pass2_profile_lane_handoff` to the skill-route proposal lane map.
- Carried downgraded unsupported lane names into candidate inventory for body-free operator review.
- Extended the pass-2 route classification test to validate proposal IDs, selected local lanes, replay command, downgraded lane names, source hashes, selected evidence IDs, and denied runtime/external actions.
- Documented the new pass-2 surface in `docs/skill-route-discovery.md`.

## Validation Plan

- `python -m pytest tests/test_skill_routing.py -q -k pass2_route_classification_fixture`
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`

## Validation Result

- `python -m pytest tests/test_skill_routing.py -q -k pass2_route_classification_fixture`: passed, 1 passed and 43 deselected.
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`: passed, 35 passed and 9 deselected.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 passed and 9 deselected.

## Review Notes

The self-model was read and left unchanged. The current text already prefers rollback-backed local evolution with explicit uncertainty; this run follows that preference without needing a new self-description.

No upstream code, installer, provider route, external harness, profile state, memory state, raw source URL export, or upstream body import was activated.
