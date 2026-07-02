# Skill Route Discovery Pass 2

Source digest: `github-growth-20260702T185118.312777Z`

Rollback point: `artifacts/rollback/20260703T010625Z-skill-route-discovery-pass2.md`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: explicit Agent Skill packaging with `SKILL.md`, `skill.yml`, references, scripts, evals, source-citation framing, and non-investment-advice boundaries. Interpreted as bounded skill-route evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent world-model and benchmark evidence across multiple environment domains. Interpreted as adjacent agent-harness evidence requiring a local fixture before activation.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous/collaborative/social agent project with tests, benchmarks, and experiments. Interpreted as adjacent agent-harness evidence requiring a local fixture before activation.

## Hypothesis

Pass 2 should make secondary harness evidence operator-visible before activation. Adjacent general-agent projects must not inherit skill-route lanes; they need a local `agent_harness_eval_lane` fixture with a runnable scenario, expected output, pass/fail signal, rollback artifact, and non-secret configuration.

## Change

- Added `skill_route_discovery_pass2_secondary_harness_checklist` to the local harness evaluator.
- Attached the checklist to `pass2_handoff_packet` and `local_lane_acceptance_contract`.
- Added a current-digest fixture for the zhengxi/Qwen/Fundamental window.
- Documented the pass-2 secondary harness checklist in `docs/architecture.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "pass2_secondary_harness_checklist or 20260702T185118"`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or skill_route_discovery_pass2"`: passed.

## Review Notes

- No external skill activation, upstream harness execution, provider launch, remote execution, credential access, or raw upstream body export was added.
- `docs/self-model.md` was read and left unchanged; it already matches this run's preference for locally validated behavior over standalone validation reports.
