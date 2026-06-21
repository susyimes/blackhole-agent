# Skill Route Discovery Pass 1 Handoff

- Source digest: `github-growth-20260621T015207.795979Z`
- Capability window: `skill-route-discovery`, pass 1 of 4
- Branch: `codex/blackhole-evolve/20260621T015328.995610-create-or-extend-local-skill-route-discovery-tes`
- Rollback artifact: `artifacts/rollback/20260621T015207Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/20260621T015207Z-skill-route-discovery-pass1`

## Evidence

The bounded evidence URLs reviewed for this pass were:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/omnigent-ai/omnigent`

The first three are skill/workflow route evidence for documentation, config,
test, or code_patch lanes only. Omnigent is adjacent general agent framework
evidence; it should stay behind `agent_harness_eval_lane` and should not inherit
skill-route discovery lanes.

## Hypothesis

Pass 1 should leave an operator-visible handoff packet that joins the selected
current bounded lane, queued bounded lanes, selected digest item IDs, replay
commands, and the adjacent Omnigent-style agent-harness gate. This improves
supervisor continuation without installing, running, cloning, activating, or
importing external skill or agent projects.

## Change

- Added `pass1_handoff_packet` to `skill_route_discovery_lane` output.
- The packet reports selected and queued bounded local lanes, selected item IDs,
  candidate source hashes, replay commands, provider-runtime replay commands,
  and a gated `adjacent_general_agent_project_eval` row.
- Documented the packet in `docs/skill-route-discovery.md`.
- Added focused harness and docs contract assertions.

## Validation

- `pytest tests/test_harness_eval.py -q -k "pass1_exposes_current_action or skill_route_discovery_lane"`: passed, 10 tests.
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`: passed, 3 tests.
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or agent_harness_eval_lane or proposal_interpretation"`: passed, 14 tests.

## Review Notes

- The self-model was left unchanged. Its current preference for reversible,
  locally validated behavior changes matches this run.
- The new packet is metadata-only and body-free. It exports hashes and selected
  item IDs, not raw upstream bodies or source URLs.
- Runtime action, external skill activation, external agent activation,
  external harness execution, provider launch, remote execution, and upstream
  body export remain denied.
