# Evolution Report: Skill Route Discovery Pass 1 Current Window

- Source digest: `github-growth-20260708T100635.467596Z`
- Capability slice: `skill-route-discovery`
- Rollback ref: `refs/rollback/20260708T100635Z-skill-route-discovery-pass1-current-window`
- Rollback artifact: `artifacts/rollback/20260708T100635Z-skill-route-discovery-pass1-current-window/rollback-point.md`

## Hypothesis

The current reverse-flow/rnskill evidence should become an operator-visible
local validation lane before activation. Reverse-flow-style Codex workflow-gate
evidence can select a bounded local test lane, generic rnskill-style skill
workflow evidence can select a bounded documentation lane, and Hy3 plus
workflow-usecase evidence must remain adjacent `agent_harness_eval_required`
without inheriting `skill_route_discovery`.

## Change Set

- Added current-digest route handling for `github-growth-20260708T100635.467596Z`
  in `src/blackhole_agent/skill_routing.py`.
- Added frozen local harness fixture
  `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260708T100635_pass1_validation_lane.json`.
- Added direct skill-routing and harness fixture regressions in
  `tests/test_skill_routing.py` and `tests/test_harness_eval.py`.
- Documented the operator-facing pass-1 lane in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T100635`
- `python -m pytest tests/test_harness_eval.py -q -k 20260708T100635`
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`

All validation commands passed.

## Review Notes

- No upstream code was imported, installed, cloned, executed, or activated.
- The fixture uses public evidence URLs only as local test input; controller
  surfaces continue to export hashes and item IDs rather than raw evidence URLs
  or upstream bodies.
- `docs/self-model.md` was read and left unchanged because its current
  preference already supports rollback-backed local behavior changes and did
  not conflict with this pass.
