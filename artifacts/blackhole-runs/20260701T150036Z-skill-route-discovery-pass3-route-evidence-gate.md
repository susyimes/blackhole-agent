# Skill Route Discovery Pass 3 Route Evidence Gate

- Source digest: `github-growth-20260701T145922.935225Z`
- Branch: `codex/blackhole-evolve/20260701T150036.361922-create-a-bounded-local-validation-lane-for-skill`
- Rollback artifact: `artifacts/rollback/20260701T150036Z-skill-route-discovery-pass3-local-lane.md`
- Rollback ref: `refs/rollback/20260701T150036Z-skill-route-discovery-pass3-local-lane`

## Hypothesis

Pass-3 skill-route evidence should expose an operator-visible route gate before activation review. The gate should make the controller recomputation boundary explicit: zhengxi-views-style skill evidence may enter only bounded local validation lanes, while general-agent and automation/reverse-engineering trend evidence stays behind `agent_harness_eval_required` unless a later controller pass assigns a bounded local lane.

## Change

- Added `route_evidence_activation_gate` to `current_digest_pass3_activation_review_lane`.
- Added a replay fixture for `github-growth-20260701T145922.935225Z`.
- Added a direct regression test for the fixture and updated aggregate local harness fixture counts.
- Documented the new pass-3 gate in `docs/skill-route-discovery.md`.

## Validation

- `pytest tests/test_harness_eval.py -q -k 20260701T145922`
- `pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or 20260701T145922"`
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery`
- `pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or 20260701T145922 or skill_route_discovery_lane"`

## Review Notes

- Self-model was read and left unchanged; it already matches this run's rollback-backed local evolution boundary and did not need a behavior-shaping edit.
- No upstream code, install commands, provider launch, external harness execution, or runtime route was added.
- open-reverselab remains non-executable trend pressure in this pass; it contributes only to the automation/reverse-engineering count in the pass-3 gate.
