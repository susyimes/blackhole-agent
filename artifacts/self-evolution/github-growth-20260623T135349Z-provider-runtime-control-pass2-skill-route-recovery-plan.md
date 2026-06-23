# Provider Runtime Control Pass 2: Skill-Route Recovery Plan Projection

Source digest: `github-growth-20260623T135349.289611Z`
Branch: `codex/blackhole-evolve/20260623T135450.547098-add-or-run-a-bounded-local-skill-route-discovery`
Rollback artifact: `artifacts/rollback/20260623T135547Z-skill-route-provider-runtime-pass2.txt`
Rollback ref: `refs/rollback/20260623T135547Z-skill-route-provider-runtime-pass2`

## Evidence

- `https://github.com/dongshuyan/compass-skills` exposes a local skill ecosystem with task clarification, task memory, session handoff, and profile workflows.
- `https://github.com/baskduf/FableCodex` is Codex/workflow-shaped evidence that should enter skill-route discovery before any secondary harness lane.
- `https://github.com/majidmanzarpour/threejs-game-skills` is a frontend/game skill workflow signal that should remain bounded to documentation, config, test, or code_patch lanes until locally validated.

## Hypothesis

Provider-runtime-control windows should not stop at classifying skill repositories into safe lanes. When sampled provider/runtime preflights are blocked, the skill-route output should surface the existing body-free recovery plan directly in the skill-route diagnostic panel so operators can replay the fix without inspecting raw provider bodies.

## Change

- Projected `provider_runtime_recovery_summary.operator_recovery_plan` into `provider_runtime_replay_sample.operator_recovery_plan`.
- Exposed the projected recovery plan from `provider_runtime_diagnostic_panel` only when a provider-runtime replay sample is present.
- Preserved launch denial, remote-execution denial, and raw provider input/diagnostic redaction flags.
- Documented the projected `skill_route_provider_runtime_recovery_plan` in `docs/architecture.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane_blocks_on_provider_runtime_replay_sample or provider_runtime_recovery_summary"`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k "skill_route_discovery"`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary`: passed.

## Review Notes

- No provider was launched.
- No upstream repository was cloned, installed, or executed.
- Raw evidence URLs, provider input bodies, diagnostics, env key names, and env values remain omitted from the local recovery surface.
- `docs/self-model.md` was read and left unchanged because its current preference for direct rollback-backed local evolution matched this run.
