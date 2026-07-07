# Evolution Run

- source_digest: `github-growth-20260707T174109.873436Z`
- branch: `codex/blackhole-evolve/20260707T174210.893778-add-or-run-a-local-skill-route-discovery-probe-f`
- rollback_ref: `refs/rollback/20260708T014108Z-skill-route-discovery-pass2-current-window`
- rollback_artifact: `artifacts/rollback/20260708T014108Z-skill-route-discovery-pass2-current-window/rollback-point.md`

## Hypothesis

The active pass-2 skill-route-discovery window should expose an
operator-visible local validation lane for the carried reverse-flow and
rnskill evidence before any activation path. Reverse-flow-style Codex workflow
skills should remain in the local test lane, generic SKILL.md collections
should remain in the documentation lane, and Shepherd or other general-agent
projects should remain behind `agent_harness_eval_required`.

## Changes

- Added `github-growth-20260707T174109.873436Z` to the pass-2 skill-route
  dispatcher.
- Added `skill_route_discovery_current_digest_20260707T174109_pass2_validation_lane`
  with current proposal IDs, rollback metadata, and hashed validation metadata.
- Added a frozen body-free fixture for reverse-flow, rnskill, Shepherd,
  Agents-A1, and Fundamental-Ava.
- Added a regression test proving skill-route lanes remain bounded to
  documentation, config, test, or code_patch and general-agent projects receive
  no direct local lanes before harness evaluation.
- Documented the new replay surface in `docs/skill-route-discovery.md`.

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference already
matches this run's behavior: prefer rollback-backed local validation and direct
behavior surfaces over ornamental self-model edits.

## Validation

- `python -m py_compile src/blackhole_agent/skill_routing.py`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k 20260707T174109`: passed,
  1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T174109 or 20260707T172109 or 20260707T150109"`:
  passed, 4 tests.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 19 tests.

Attempted `python -m black src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`,
but `black` is not installed in this environment.

## Review Notes

- No external evidence was fetched during this run; the fixture uses body-free
  metadata from the supplied source digest and proposal window.
- Runtime action, external skill activation, external agent activation,
  external harness execution, provider launch, memory/profile writes, remote
  execution, promotion, restart, and rollback execution remain disabled.
- Rollback execution remains an explicit destructive operator action.
