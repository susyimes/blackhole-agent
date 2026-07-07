# Self-Evolution Run: skill-route pass 1 provider CLI empty envelope

- Source digest: `github-growth-20260707T001555.490520Z`
- Capability theme: `skill-route-discovery`
- Selected proposals: `p1_provider_config_preflight_cli_empty_envelope`, `p2_provider_preflight_documentation`, with `p3_skill_route_discovery_probe` preserved as the route boundary context
- Rollback point: `artifacts/rollback/20260707T001554Z-provider-cli-empty-envelope-preflight/rollback-point.md`

## Evidence

- `https://github.com/shepherd-agents/shepherd/issues/23` reports a CLI-backed provider lane that fails with `rc=1`, no model iterations, empty model usage, and an empty result envelope despite a green doctor check.
- `https://github.com/lingbol088-spec/reverse-flow-skill` presents as a Codex/AI Agent skill workflow repository with `skills/reverse-flow/SKILL.md`, local sandbox and CTF/crackme framing, references, scripts, install examples, and run examples. Those are route-discovery signals only, not activation authority.

## Hypothesis

Skill-route windows that carry provider/runtime pressure need a local preflight lane that turns CLI empty-envelope failures into bounded diagnostics before any agent lane runs. A distinct failure class is better than treating the case as a generic empty completion because the recovery path is provider CLI contract repair, not task-output review.

## Change

- Added `provider_cli_empty_envelope_refused` classification in `evaluate_provider_turn_outcome_preflight`.
- Added body-free metadata for CLI exit code, non-zero exit, refusal, empty result envelope, and explicit denial of raw stderr/envelope export.
- Added a local provider-runtime fixture for the Shepherd-style `rc=1` empty-envelope case.
- Documented the active digest expectation in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k cli_empty_envelope_refusal`
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures`
- `python -m pytest tests/test_harness_eval.py -q -k provider_runtime_preflight`

All validation passed.

## Review Notes

- No self-model edit was made. The current self-model already permits rollback-backed, locally validated runtime/provider improvements and did not conflict with this pass.
- The new fixture remains local-only and does not execute external providers, clone upstream repositories, export raw provider bodies, or activate external skills.
