# Skill Route Discovery Pass 2 Local Validation Lane

Source digest: `github-growth-20260701T143923.018624Z`

Rollback point:
- Original branch: `codex/blackhole-evolve/20260701T144035.793450-add-or-extend-local-tests-for-skill-route-discov`
- Original HEAD: `b300b4c1b292e778b234540179104266d1b9f198`
- Rollback ref: `refs/blackhole-agent/rollback/20260701T143921Z-skill-route-discovery-pass2`
- Rollback artifact: `.blackhole-agent/rollback/20260701T143921Z-skill-route-discovery-pass2.json`

Evidence reviewed:
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/LING71671/open-reverselab`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`

Hypothesis:
The current pass-2 window should become replayable as a bounded local lane:
zhengxi-views-style Agent Skill evidence may enter documentation, config, test,
or code_patch work with `runtime_action: none`; adjacent general-agent projects
must stay in `agent_harness_eval_required` until local harness evaluation
passes.

Changed surfaces:
- `src/blackhole_agent/skill_routing.py`: recognizes the
  `20260701T143923.018624Z` pass-2 digest, current proposal IDs, adjacent
  harness-eval proposal ID, and open-reverselab review-only anchor.
- `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260701T143923_pass2_local_validation_lane.json`:
  frozen body-free replay fixture.
- `tests/test_skill_routing.py`: direct route-map assertions for the new digest.
- `tests/test_harness_eval.py`: direct harness replay assertions plus aggregate
  fixture count update.
- `docs/skill-route-discovery.md`: operator-visible lane interpretation.

Validation:
- `pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k "20260701T143923 or current_digest_20260701T143923"`: passed, 2 tests.
- `pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures"`: passed, 1 test.
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.

Review notes:
- Self-model was read and left unchanged; its current preference already matches
  this run's rollback-backed, locally validated behavior path.
- open-reverselab remains review-boundary evidence only; it does not influence
  runtime, external harness execution, provider launch, remote execution, or
  source/body export.
- Restart, push, promotion, and commit handoff remain supervisor-owned.
