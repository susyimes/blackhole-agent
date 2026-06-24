# Skill Route Discovery Pass 4 Replay Contract

Source digest: `github-growth-20260624T045355.941398Z`

Rollback:

- Branch: `codex/blackhole-evolve/20260624T045457.758046-add-or-extend-local-tests-that-classify-skill-wo`
- HEAD before edits: `4d40a512209895265a5f4680752b69e285ff99fd`
- Rollback ref: `refs/blackhole-rollback/20260624T045354Z-skill-route-pass4`
- Rollback artifact: `artifacts/rollback/20260624T045354Z-skill-route-pass4.md`

Evidence:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/omnigent-ai/omnigent`
- `https://github.com/omnigent-ai/omnigent/pull/1084`

Hypothesis:

The pass-4 skill-route slice already exposes bounded route lanes, a final
manifest, a validation lane queue, and a secondary harness bridge. The remaining
operator risk is that those final panels can drift in the replay command they
present. A body-free replay-command contract in the completion consistency guard
makes that drift visible before supervisor handoff.

Change:

- Added `completion_consistency_guard.replay_contract`.
- The guard now checks that final skill-route surfaces carry the local
  `skill_route_discovery_lane` replay command.
- The secondary harness bridge must also carry the later
  `agent_harness_eval_lane` command, while still denying activation.
- Command values are exported as hashes in the contract; raw commands are not
  exported from the contract.
- Updated route-discovery documentation and tests for the ready and blocked
  replay-contract paths.

Validation:

- `python -m pytest tests/test_harness_eval.py -q -k "completion_guard or completion_report_surfaces_local_lane_closure or pass4_current_window"`: passed, 3 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`: passed, 23 tests.
- `python -m pytest tests/test_harness_eval.py -q`: passed, 146 tests.

Self-model:

Left unchanged. The current self-model is broad preference text and did not
need revision for this concrete pass-4 operator-surface change.

Review Notes:

- This pass does not adopt upstream code or run upstream projects.
- Omnigent-style harness evidence remains a secondary bridge blocked until local
  corroboration.
- The new contract strengthens replay consistency only; it does not authorize
  upstream skill activation, external harness execution, provider launch, remote
  execution, or restart.
