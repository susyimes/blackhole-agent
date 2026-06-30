# Skill Route Discovery Pass 2 Agent Harness Readiness

Source digest: `github-growth-20260630T062715.310093Z`

Rollback point:

- `artifacts/rollback/20260630T062835Z-skill-route-discovery-pass2.md`
- `refs/blackhole-rollback/20260630T062835Z-skill-route-discovery-pass2`

Evidence reviewed:

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/ksimback/looper`
- `https://github.com/ziwang-Physics/AgentChat`

Hypothesis:

`zhengxi-views` remains usable as bounded skill-route evidence because the
carried digest describes explicit Agent Skill package signals. Qwen-AgentWorld,
looper, and AgentChat are more general agent-project evidence; they should not
inherit `skill_route_discovery`, but they should expose a concrete local
`agent_harness_eval` readiness contract before documentation, test, or
code_patch follow-up work is allowed.

Change:

- Added `implementation_readiness_contract` to `agent_harness_eval_lane`.
- The contract records candidate local capabilities, required preflight checks,
  pass criteria, fail criteria, allowed follow-up lanes, and denial booleans.
- Extended the existing general-agent fixture to assert that unmapped claims
  keep documentation, test, and code_patch follow-up blocked.
- Documented the current pass-2 route rule in `docs/skill-route-discovery.md`.

Self-model decision:

`docs/self-model.md` was read and left untouched. Its current preference already
matches this run: reversible local behavior with validation, narrow safety
boundaries, and uncertainty recorded in artifacts. The file would be ornamental
churn for this pass.

Validation:

- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
  - `3 passed, 190 deselected`
- `pytest tests/test_skill_routing.py -q -k "20260630T060714 or 20260630T054715 or current_digest_pass3_local_validation_lane"`
  - `3 passed, 118 deselected`
- `pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`
  - `1 passed, 192 deselected`
- `ruff check src\blackhole_agent\harness_eval.py`
  - `All checks passed`

Review notes:

- No external harness execution, provider launch, profile write, memory write,
  remote execution, or upstream skill activation was added.
- The new contract is a local readiness surface only. It blocks when any
  general-agent claim remains unmapped or when the route review queue is not
  ready.
