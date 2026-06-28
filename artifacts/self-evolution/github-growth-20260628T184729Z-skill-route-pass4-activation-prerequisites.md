# Skill Route Discovery Pass 4 Activation Prerequisites

Source digest: `github-growth-20260628T184729.576873Z`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/dongshuyan/compass-skills`

The focused lesson is that skill-route evidence should become replayable local
activation prerequisites before activation, not upstream package use.
zhengxi-views keeps source-cited or generic skill workflow evidence in a local
validation lane, Three.js Game Skills keeps frontend/game skill workflow behind
local frontend validation, and COMPASS-style handoff evidence stays
metadata-only until privacy, profile, and memory boundaries are locally proven.

## Hypothesis

Adding an operator-visible activation prerequisite lane to the current digest
pass-4 completion handoff improves replayability and recovery without widening
the allowed local lanes or granting external activation authority.

## Change

- Added `activation_prerequisite_lane` to the current digest pass-4 completion
  handoff.
- The lane is derived from existing completion rows and checks selected item
  IDs, validation gates, profile checklists, bounded lanes, rollback coverage,
  and denied runtime or export actions.
- Updated the focused regression test and skill-route-discovery documentation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_digest_pass4_completion_handoff`
  - Result: passed, 1 passed and 84 deselected.
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: passed, 85 passed.
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: passed, 11 passed.

## Review Notes

- Self-model left unchanged. It already favors rollback-backed, locally
  validated behavior changes over report-only artifacts, which matches this
  run.
- The new surface does not export raw GitHub URLs, replay commands, local
  target paths, or upstream bodies.
- Runtime action, upstream skill activation, external harness execution,
  provider launch, profile writes, memory writes, and remote execution remain
  denied.
