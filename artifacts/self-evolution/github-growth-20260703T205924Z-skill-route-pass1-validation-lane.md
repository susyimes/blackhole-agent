# Skill Route Discovery Pass 1 Validation Lane

Source digest: `github-growth-20260703T205924.382214Z`

Hypothesis: Codex-adjacent skill workflow evidence should open a bounded
`skill_route_discovery` validation lane, while generic agent project evidence
without skill signals remains in `agent_harness_eval_required` until local
harness evaluation.

Rollback point:
`refs/rollback/20260704T000000Z-skill-route-discovery-pass1-current-window`

Rollback artifact:
`artifacts/rollback/20260704T000000Z-skill-route-discovery-pass1-current-window.txt`

Changed behavior:

- Added a current digest pass-1 route branch for
  `github-growth-20260703T205924.382214Z`.
- Routed `p1-skill-route-discovery-codex-workflow` to the local `test` lane
  with `skill_route_discovery_first`, bounded to documentation, config, test,
  and code_patch.
- Routed `p2-generic-skill-workflow-discovery-doc` to the documentation lane
  under the same bounded lane envelope.
- Kept agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava behind
  `p3-agent-harness-eval-fixtures` with no direct runtime, code_patch,
  provider launch, external harness execution, remote execution, or activation.

Validation:

- `pytest tests/test_skill_routing.py -q -k 20260703T205924`
- `pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`
- `pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260703T205924`
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery`
- `pytest tests/test_skill_routing.py -q`

External actions: no network calls were made. The run used the supplied digest
evidence and local frozen fixtures only.

Self-model: left unchanged. The current self-model already permits
rollback-backed, locally validated behavior changes and does not contradict
this lane.
