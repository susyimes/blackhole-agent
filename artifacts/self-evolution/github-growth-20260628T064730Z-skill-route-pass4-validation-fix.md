# Skill Route Discovery Pass 4 Validation Fix

Source digest: `github-growth-20260628T064730.025611Z`
Branch: `codex/blackhole-evolve/20260628T064826.414487-add-a-local-skill-route-discovery-validation-fix`
Rollback artifact: `artifacts/rollback/20260628T064826Z-skill-route-discovery-pass4-local-validation-fix.txt`
Rollback ref: `refs/rollback/20260628T064826Z-skill-route-discovery-pass4-local-validation-fix`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/majidmanzarpour/threejs-game-skills`

The evidence was used only as public repository-level route context. No upstream
skill body was imported, installed, executed, or activated.

## Hypothesis

The final pass should expose a supervisor-visible validation-fix lane that keeps
generic/source-cited skill workflow, game/frontend workflow, and skill ecosystem
handoff proposals separate while proving they remain inside documentation,
config, test, and code_patch local lanes before activation.

## Change

- Added `current_pass4_route_discovery_validation_fix` to the skill-route
  proposal lane map.
- Added a frozen current-pass fixture covering zhengxi-views, Three.js game
  skills, and COMPASS Skills route profiles.
- Added regression coverage that verifies selected lanes, profile requirements,
  source hashing, item-id citation, no runtime action, no external activation,
  and no raw GitHub URL or replay command export.
- Documented the pass-4 validation-fix packet and its game/frontend and
  state-handoff boundaries.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_pass4_route_discovery_validation_fix`
  - Result: passed, `1 passed, 68 deselected`
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: passed, `69 passed`
- `python -m pytest -q`
  - Result: passed, `472 passed`

## Review Notes

- `docs/self-model.md` was read and left unchanged. It already expresses the
  current run preference for rollback-backed local evolution and does not need
  more ornamental structure for this pass.
- Unsupported install/runtime pressure in the frozen fixture is stripped before
  the final pass-4 validation-fix packet, so the packet records bounded lanes
  rather than downgrade details.
- Activation, restart, provider launch, external harness execution, profile
  writes, memory writes, raw source URL export, raw evidence URL export, raw
  target path export, and upstream body export remain denied.
