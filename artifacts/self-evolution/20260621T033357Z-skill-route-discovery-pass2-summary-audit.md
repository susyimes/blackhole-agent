# Skill Route Discovery Pass 2 Summary Audit

- Source digest: `github-growth-20260620T193207.716885Z`
- Capability theme: `skill-route-discovery`
- Planned pass: 2 of 4
- Branch: `codex/blackhole-evolve/20260620T193308.068345-add-or-extend-local-validation-for-skill-route-d`
- Rollback ref: `refs/rollback/20260621T033357Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260621T033357Z-skill-route-discovery-pass2.txt`

## Evidence

The carried proposal window named COMPASS Skills, FableCodex, Three.js Game
Skills, and Omnigent as route-discovery evidence. Existing local routing already
bounded the basic lanes and classified mixed FableCodex-style evidence as
`skill_route_discovery_first`. The remaining pass-2 improvement was to make
repository-summary intake operator-visible before activation.

## Hypothesis

When skill-route evidence arrives as body-free repository summaries, the harness
should show which summaries became bounded local candidates and which were
ignored. A dedicated `summary_signal_audit` panel improves replayability for
COMPASS-style agent/skill/skills/workflow summaries without exposing raw source
URLs, exporting upstream bodies, or enabling external code.

## Change

- Added `summary_signal_audit` to `skill_route_discovery_lane`.
- Exposed summary registry counts when source input is `summaries`.
- Added a COMPASS-style summary fixture that accepts the skill ecosystem summary
  and ignores a generic Omnigent-style agent runtime summary.
- Documented the summary-audit panel and extended the docs contract.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "summary_signal_audit or skill_route_discovery_pass2_fixture"`: passed, 2 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 passed.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 passed.
- `python -m pytest tests/test_github_growth.py tests/test_proposal_eval.py tests/test_skill_routing.py -q -k "skill_route_discovery or mixed_skill_workflow or route_hint_lane_map"`: passed, 24 passed.
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures`: passed, 1 passed.
- `python -m pytest tests/test_harness_eval.py tests/test_docs_contracts.py tests/test_github_growth.py tests/test_proposal_eval.py tests/test_skill_routing.py -q -k "skill_route_discovery or summary_signal_audit or mixed_skill_workflow or route_hint_lane_map"`: passed, 54 passed.

## Review Notes

- No upstream repository body was fetched or executed.
- The self-model was read and left unchanged because it already matched the
  run's validated-local-evolution policy and did not need another ornamental
  note.
- The new panel remains metadata-only: runtime action, external skill
  activation, external skill code, external harness execution, provider launch,
  remote execution, raw source URL export, and upstream body export stay denied.
