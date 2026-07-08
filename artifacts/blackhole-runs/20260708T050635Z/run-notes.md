# Run Notes

- Run: `20260708T050635Z`
- Branch: `codex/blackhole-evolve/20260708T050733.063611-add-or-update-a-local-skill-route-discovery-test`
- Source digest: `github-growth-20260708T050637.590875Z`
- Theme: `skill-route-discovery`
- Pass: 4 of 4

## Hypothesis

The current reverse-flow/rnskill/Shepherd/Hy3/workflow-usecase window is ready
for an operator-visible pass-4 completion handoff. Codex-oriented and generic
skill repositories should map only to bounded local lanes, while Shepherd, Hy3,
and workflow-usecase repositories should remain grouped behind
`agent_harness_eval_required` with no inherited skill-route hints or direct
implementation lanes before local harness evaluation.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/Pluviobyte/rnskill`
- `https://github.com/shepherd-agents/shepherd`
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`
- `https://github.com/Tencent-Hunyuan/Hy3`

External review was limited to proposal evidence URLs. The routing artifact is
body-free and records source hashes rather than raw URLs.

## Rollback

- Rollback ref: `refs/rollback/20260708T050635Z-skill-route-discovery-pass4-completion`
- Rollback artifact:
  `artifacts/rollback/20260708T050635Z-skill-route-discovery-pass4-completion/rollback-point.md`
- Original HEAD: `7ff202501dedbe47738cb225d00e5d11cd294c72`

Rollback is not executed by this kernel run.

## Changed Files

- `src/blackhole_agent/skill_routing.py`
- `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260708T050637_pass4_completion_handoff.json`
- `tests/test_skill_routing.py`
- `tests/test_harness_eval.py`
- `docs/skill-route-discovery.md`
- `artifacts/rollback/20260708T050635Z-skill-route-discovery-pass4-completion/rollback-point.md`

`docs/self-model.md` was left unchanged. The existing self-model preference for
rollback-backed, locally validated evolution already matches this run; the new
evidence justified a routing behavior and validation surface, not a
self-description change.

## Validation

- `$env:PYTHONPATH='src'; pytest tests/test_skill_routing.py -q -k 20260708T050637`
  - Passed: 1
- `$env:PYTHONPATH='src'; pytest tests/test_harness_eval.py -q -k 20260708T050637`
  - Passed: 1
- `$env:PYTHONPATH='src'; pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`
  - Passed: 1
- `$env:PYTHONPATH='src'; pytest tests/test_docs_contracts.py -q -k skill_route_discovery`
  - Passed: 17

## Review Notes

- No runtime execution, install, provider launch, external harness execution,
  remote execution, push, promotion, or restart was performed.
- Hy3 remains general-agent/provider-tooling pressure in this handoff, not a
  provider runtime activation lane.
- The completion handoff exports validation-command hashes, source hashes, and
  lane decisions only.
