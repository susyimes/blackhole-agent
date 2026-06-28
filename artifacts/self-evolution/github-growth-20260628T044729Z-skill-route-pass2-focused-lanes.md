# Skill Route Discovery Pass 2 Focused Lanes

- Source digest: `github-growth-20260628T044729.594506Z`
- Capability theme: `skill-route-discovery`
- Pass: 2 of 4
- Rollback artifact: `artifacts/rollback/20260628T044837Z-skill-route-discovery-pass2.md`
- Rollback ref: `refs/blackhole-agent/rollback/20260628T044837Z/skill-route-discovery-pass2`

## Evidence

The active window carried COMPASS Skills, zhengxi-views, and Three.js Game
Skills as public skill/workflow evidence. The reusable local lesson is that
skill-like repository evidence can classify route profiles before activation,
but it should not install, execute, scaffold, launch providers, write profile
or memory state, or export upstream bodies.

## Hypothesis

A focused pass-2 harness replay should preserve the route profiles from nested
`route_classification` metadata while proving that every generated local lane is
bounded to documentation, config, test, or code_patch. The operator-visible
handoff should remain in progress for pass 3 rather than becoming activation
authority.

## Change

- Added
  `tests/fixtures/local_harness_eval/skill_route_discovery_pass2_focused_route_classification_lanes.json`.
- Added a focused regression in `tests/test_harness_eval.py` for the pass-2
  handoff packet, evidence lane matrix, selected item ID mode, profile lane
  acceptance contract, and raw URL privacy boundary.
- Updated the local harness fixture inventory counts.
- Documented the digest-specific route-classification rule in
  `docs/skill-route-discovery.md`.

`docs/self-model.md` was left unchanged. Its current preference already matches
this run: apply rollback-backed local validation improvements while keeping
install, execution, provider launch, profile/memory writes, and privacy leakage
outside the autonomous lane.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "pass2_focused_route_classification_lanes or local_harness_eval_runs_pass_and_fail_fixtures"`:
  passed, 2 passed.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`:
  passed, 10 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`:
  passed, 2 passed.

## Review Notes

- The fixture validates route classification and bounded local lanes only. It
  does not assert upstream implementation parity.
- Unsupported pressure such as `provider_runtime`, `install`, and
  `runtime_execution` remains outside generated activation lanes.
- The pass-2 packet remains an operator-visible next-pass handoff, not a
  restart, promotion, remote execution, or external activation request.
