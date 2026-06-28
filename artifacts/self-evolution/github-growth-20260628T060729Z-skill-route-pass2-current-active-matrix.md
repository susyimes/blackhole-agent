# Skill Route Discovery Pass 2 Current Active Matrix

Source digest: `github-growth-20260628T060729.568458Z`

Hypothesis: the active pass-2 skill-route proposals should be visible to the
operator as one bounded local validation matrix before any activation path is
considered.

Rollback:

- Ref: `refs/blackhole-rollback/20260628T060728Z-skill-route-discovery-pass2`
- Artifact: `artifacts/rollback/20260628T060728Z-skill-route-discovery-pass2.md`

Changed behavior:

- Added `current_active_pass2_skill_route_validation_matrix` to the skill route
  proposal lane map.
- Mapped the active proposals to local lanes only:
  - `p1-skill-route-discovery-general`: test
  - `p2-game-frontend-skill-profile`: test
  - `p3-skill-ecosystem-state-handoff`: config
- Kept runtime action, external skill or agent activation, external harness
  execution, provider launch, profile writes, memory writes, remote execution,
  raw source URL export, raw evidence URL export, target path export, replay
  command export, and upstream body export denied.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k current_active_pass2_skill_route_validation_matrix`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`
- `git diff --check`

Review notes:

- The self-model was read and left unchanged. Its current preference for
  rollback-backed, locally validated evolution matched this run.
- The fixture is body-free and selected-item-id based. It does not import,
  install, execute, or activate upstream skill repositories.
