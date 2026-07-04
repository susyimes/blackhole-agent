# Evolution Run: skill-route-discovery pass 1

Source digest: `github-growth-20260704T000924.757419Z`

## Hypothesis

The active pass-1 window should expose an operator-visible validation lane for
explicit skill workflow evidence before any activation path. Reverse-flow-skill
and zhengxi-views can be mapped to bounded local lanes, while Qwen-AgentWorld,
Fundamental-Ava, and workflow-only usecase evidence remain behind local
`agent_harness_eval_required` checks.

## Rollback

Rollback point recorded in
`artifacts/rollback-20260704T000923Z-skill-route-discovery-pass1.md`.

Local rollback ref:
`refs/blackhole-rollback/20260704T000923Z-skill-route-discovery-pass1`.

## Changes

- Added a `github-growth-20260704T000924.757419Z` branch to the current digest
  pass-1 skill-route validation lane.
- Added a frozen body-free fixture for the active proposal and trend IDs.
- Added a regression test that verifies skill-route rows select only
  documentation, config, test, or code_patch lanes and adjacent general-agent or
  workflow-only rows remain `agent_harness_eval_required`.
- Documented the new pass-1 lane and its activation boundary.

## Self-Model Decision

`docs/self-model.md` was left unchanged. The existing preference for reversible,
locally validated behavior changes already matched this run; the file did not
need a new category to justify the bounded lane extension.

## Material Actions

- Created rollback ref and rollback artifact.
- Edited local source, test, fixture, documentation, and run-note artifacts.
- Did not clone, install, run, or activate upstream repositories.
- Did not restart the agent or request supervisor promotion.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260704_pass1_validation_lane or current_digest_pass1_validation_lane or active_pass1_lane_uses_current_source_digest"`:
  passed, 3 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 234 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records`:
  passed, 2 tests.

## Review Notes

- The lane records unsupported upstream pressure such as install or runtime
  execution only as downgraded evidence; selected lanes and allowed lanes remain
  bounded.
- General agent and workflow-only evidence is not converted into
  implementation work without local harness evidence.
- Activation remains external-supervisor work after validation; this run did
  not perform activation, push, restart, provider launch, remote execution, or
  profile or memory writes.
