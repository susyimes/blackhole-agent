# Self-Evolution Run Notes: skill-route-discovery pass 3 local proof

- Source digest: `github-growth-20260628T062729.695489Z`
- Capability theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260628T062843.121848-add-or-run-a-local-validation-lane-for-generic-s`
- Rollback ref: `refs/blackhole-rollback/20260628T062918Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260628T062918Z-skill-route-discovery-pass3.md`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public skill repository with `SKILL.md`, `skill.yml`, source-cited research data, validation scripts, and explicit advice-boundary language.
- `https://github.com/dongshuyan/compass-skills`: public skill ecosystem with `skills/`, `AGENTS.md`, `skills.sh.json`, and workflows for repo-local task memory, conversation handoff, and local collaboration profile.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public Three.js game skill package with `skills/`, scripts, bundled scaffold, QA/browser validation language, and provider asset boundary notes.

The reusable lesson is that pass-3 should expose local proof requirements before pass-4 handoff, not another activation-like route. Public skill packages are evidence for bounded local lanes only.

## Hypothesis

If `skill_route_discovery` emits an operator-visible pass-3 proof lane for the current proposal IDs, the supervisor can verify generic skill workflow, game frontend workflow, and state handoff candidates before pass-4 activation handoff without granting runtime permissions, exporting raw upstream URLs, or importing upstream skill bodies.

## Changes

- Added `current_active_pass3_local_activation_proof_lane` to `build_skill_route_discovery_proposal_lane_map`.
- Added local proof rows for:
  - `p1-skill-route-discovery-general` as a focused test or fixture proof.
  - `p2-game-frontend-skill-profile` as a frontend validation boundary proof.
  - `p3-skill-ecosystem-state-handoff` as a metadata-only config proof.
- Added regression coverage that checks selected item IDs, profile validation requirements, hashed replay commands, bounded lanes, and denied runtime/export fields.
- Documented the pass-3 proof lane in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged; its current preference already matches the evidence-backed local behavior change and is not the active control surface.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "current_active_pass3_local_activation_proof_lane or current_active_pass2_skill_route_validation_matrix"`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 68 tests.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 11 tests.

## Review Notes

- No upstream skill install, clone, execution, provider launch, profile write, memory write, restart, push, or remote execution was performed.
- The new surface uses selected item IDs, source hashes, validation gate names, proof artifact names, and hashed replay commands only.
- Remaining uncertainty is upstream implementation parity. The lane intentionally treats repository-level evidence as local validation stimulus, not activation approval.
