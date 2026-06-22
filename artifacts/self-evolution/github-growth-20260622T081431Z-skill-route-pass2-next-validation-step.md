# Self-Evolution Run: skill-route pass 2 next validation step

- Source digest: `github-growth-20260622T081431.747128Z`
- Capability theme: `skill-route-discovery`
- Capability pass: 2 of 4
- Branch: `codex/blackhole-evolve/20260622T081530.946234-add-a-bounded-local-skill-route-discovery-valida`
- Rollback ref: `refs/blackhole/rollback/20260622T081430Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260622T081430Z-skill-route-discovery-pass2.md`

## Evidence And Hypothesis

The active window carried COMPASS Skills, FableCodex, and game/frontend skill
workflow proposals. Existing local coverage already bounded those repository
signals into documentation, config, test, and code_patch lanes with local
validation required. The remaining pass-2 gap was operator handoff: controllers
had row-level activation targets but no compact next-step selector for the
scheduled loop to replay before any activation.

Hypothesis: deriving one `next_validation_step` from the existing
`local_activation_targets` improves pass-2 route handoff without broadening
permissions. FableCodex-style workflow evidence should prioritize the
`skill_route_discovery_first` regression before secondary workflow handling;
game/frontend and COMPASS-style state handoff rows remain queued as bounded
local validation targets.

## Changes

- Added `next_validation_step` to `build_skill_route_discovery_proposal_lane_map`.
- Kept the new selector derived from existing local activation targets only.
- Added focused assertions to the current-window skill-route test.
- Documented the pass-2 handoff selector in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged; it already matched the run policy and did
  not need to shape this behavior.

## Material Actions

- Created rollback ref `refs/blackhole/rollback/20260622T081430Z-skill-route-discovery-pass2`.
- Wrote rollback artifact `artifacts/rollback/20260622T081430Z-skill-route-discovery-pass2.md`.
- No external network requests were made during the implementation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "current_window_matrix or mixed_codex_agent_workflow"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 28 tests.
- `python -m pytest tests/test_proposal_eval.py tests/test_github_growth.py -q -k "skill_route_discovery or mixed_skill_workflow or route_hint_lane_map"`: passed, 11 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `git diff --check`: passed with line-ending normalization warnings only.

## Review Notes

The selector is deliberately advisory and local. It exports candidate names,
bounded lanes, route profiles, validation target names, and replay commands,
but denies runtime action, external skill activation, external harness
execution, provider launch, remote execution, raw source URL export, raw
evidence URL export, and upstream body export.
