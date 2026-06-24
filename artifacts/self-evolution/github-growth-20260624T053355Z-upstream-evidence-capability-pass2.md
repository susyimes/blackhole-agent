# Upstream Evidence Capability Pass 2

Source digest: `github-growth-20260624T053355.607273Z`

Evidence reviewed:

- `https://github.com/baskduf/FableCodex`
- Carried current-window fixture evidence for `FableCodex`, `compass-skills`, `zhengxi-views`, and `threejs-game-skills`.

Hypothesis: public skill/workflow repositories should become an explicit local route classification for bounded
proposal lanes, not an inferred activation, harness, provider runtime, install, or execution route.

Change made:

- Added `external_skill_route_discovery_classification` as explicit `route_class` metadata on skill-route
  discovery registry entries, candidate inventory rows, proposal lanes, and the lane-map root.
- Added a fixture-backed regression using the current four-item skill/workflow evidence set to assert:
  - candidates stay disabled and classification-only;
  - route hints remain `skill_route_discovery`;
  - proposal lanes remain bounded to `documentation`, `config`, `test`, and `code_patch`;
  - route profiles select the expected local validation path for workflow gate, state handoff, domain research,
    and game/frontend skill evidence.

Rollback:

- Created `artifacts/rollback/20260624T133541Z-skill-route-discovery-evidence-capability.md`.
- Created ref `refs/rollback/blackhole-agent/20260624T133541Z-skill-route-discovery-evidence-capability`.

Self-model:

- Read `docs/self-model.md` and left it unchanged. Its current preference already supports rollback-backed,
  locally validated behavior changes and does not need new authority or structure for this pass.

Validation:

- `PYTHONPATH=src pytest tests/test_skill_routing.py -q -k "current_window_skill_workflow or proposal_lane_map_cites_only_item_evidence_urls or classifies_body_free_file_layout"`: passed
- `PYTHONPATH=src pytest tests/test_skill_routing.py -q -k "current_window_skill_workflow or downgrades_unsupported_lanes"`: passed
- `PYTHONPATH=src pytest -q`: passed, 414 tests
- `PYTHONPATH=src ruff check src tests`: passed

Review notes:

- This pass intentionally did not activate, install, clone, or execute upstream skill code.
- The route class is descriptive controller metadata; downstream consumers should still honor the existing
  `runtime_action: none` and local validation gates.
