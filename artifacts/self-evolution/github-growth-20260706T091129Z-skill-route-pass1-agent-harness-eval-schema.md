# Self-Evolution Run: Skill Route Discovery Pass 1

Source digest: `github-growth-20260706T091129.696426Z`

Theme: `skill-route-discovery`

Hypothesis: general agent project trends should not open a direct implementation
or activation lane until the local `agent_harness_eval_lane` records the
candidate capabilities, required inputs, expected outputs, and pass/fail
criteria that a supervisor can replay.

Evidence reviewed:
- `https://github.com/InternScience/Agents-A1`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/shepherd-agents/shepherd`

Decision:
- Keep the current evidence in `agent_harness_eval_lane`, not
  `skill_route_discovery`.
- Add `agent_harness_eval_result_schema` to the implementation-readiness
  contract.
- Add a current-digest fixture for the four general agent projects.
- Leave `docs/self-model.md` unchanged because the current self-model already
  describes rollback-backed local evolution and is not behavior-shaping code.

Rollback:
- Rollback point: `artifacts/rollback/20260706T091229Z-skill-route-discovery-pass1-agent-harness-eval/rollback-point.md`
- Rollback ref: `refs/rollback/20260706T091229Z-skill-route-discovery-pass1-agent-harness-eval`

Validation:
- `python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or 20260706T091129"`: passed, 4 passed.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures or agent_harness_eval_lane"`: passed, 5 passed.

Review notes:
- No upstream code was imported or executed.
- Raw source URLs remain hashed or omitted from structured harness output.
- Runtime action, external agent activation, external harness execution,
  provider launch, and remote execution remain disabled.
