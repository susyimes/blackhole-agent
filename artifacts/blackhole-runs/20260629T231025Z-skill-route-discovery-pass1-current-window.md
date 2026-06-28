# Skill Route Discovery Pass 1 Current Window

- Source digest: `github-growth-20260628T230729.580958Z`
- Theme: `skill-route-discovery`
- Rollback ref: `refs/rollback/20260629T231025Z-skill-route-discovery-pass1-current-window`
- Rollback artifact: `artifacts/rollback/20260629T231025Z-skill-route-discovery-pass1-current-window.md`

## Evidence Decision

The carried evidence supports an operator-visible behavior change rather than
another standalone report. zhengxi-views is treated as bounded
`generic_skill_workflow` evidence, Three.js Game Skills as
`game_frontend_workflow`, and COMPASS Skills as metadata-only state handoff
evidence. Qwen-AgentWorld remains adjacent `agent_harness_eval_required`
evidence and does not inherit `skill_route_discovery`. The looper anchor is
kept as an anchoring proposal ID because no body-free local evidence URL was
carried in this run.

## Changed Files

- `src/blackhole_agent/skill_routing.py`
- `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_230729_pass1_current_window.json`
- `tests/test_harness_eval.py`
- `tests/test_skill_routing.py`
- `docs/skill-route-discovery.md`
- `artifacts/rollback/20260629T231025Z-skill-route-discovery-pass1-current-window.md`

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "current_digest_230729_pass1_current_window or local_harness_eval_runs_pass_and_fail_fixtures"`
- `python -m pytest tests/test_skill_routing.py -q -k current_digest_230729_pass1_current_window`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_harness_eval.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`
- `git diff --check`
- `python -m pytest -q`

## Review Notes

- No runtime action, upstream skill activation, external harness execution,
  provider launch, profile write, memory write, or remote execution was added.
- The new readiness panel exports hashed replay commands only.
- `docs/self-model.md` was read and left unchanged because the current
  preference already matches rollback-backed, locally validated behavior
  changes and this run produced a concrete operator-visible behavior path.
