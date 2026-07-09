# Evolution: provider-runtime-control pass 1

## Evidence

- Source digest: github-growth-20260709T085527.278985Z
- Capability window: provider-runtime-control, pass 1 of 4
- Evidence reviewed:
  - https://github.com/Tencent-Hunyuan/Hy3/issues/1
  - https://github.com/Tencent-Hunyuan/Hy3/pull/30
  - https://github.com/Pluviobyte/rnskill
  - https://github.com/lingbol088-spec/reverse-flow-skill

Hy3 issue evidence asks for quickstart material that includes base URL, API key, model name, tool calls, streaming,
reasoning mode, and error handling. Hy3 PR evidence adds an MCP server over OpenAI-compatible inference APIs, client
configuration generation, and validation claims that config loading and request payload behavior were tested without
including API keys. Skill repository evidence continues to support bounded local skill-route lanes rather than direct
runtime activation.

## Hypothesis

Provider/API/MCP trend evidence should not enable runtime use until the local provider preflight can prove a complete,
body-free configuration shape. For Hy3-like OpenAI-compatible MCP candidates, endpoint, model, and key-variable metadata
are the minimum shape; missing shape should fail closed with recovery hints and replay commands, while raw endpoint,
model, key variable, provider config, and secret values remain unexported.

## Change

- Added `provider_config_shape` to `provider_runtime_preflight`.
- Added Hy3/OpenAI-compatible/MCP detection that requires endpoint, model, and key-variable metadata before launch.
- Added nested config resolution for `provider_config.openai.base_url`, `provider_config.openai.models.default`, and
  key-variable fields.
- Added `provider_config_shape_missing` recovery hints into the existing operator recovery plan, diagnostic manifest,
  and supervisor replay surfaces.
- Added focused tests for blocked and ready Hy3 config-shape preflight and body-free recovery-summary aggregation.

## Rollback

- Rollback ref: refs/blackhole-agent/rollback/20260709T085525Z-provider-runtime-control-pass1
- Rollback artifact: artifacts/rollback/20260709T085525Z-provider-runtime-control-pass1/rollback-point.md
- Original HEAD: 8b42203a02ba16e19c433f50e376c51d2fa5734f

Rollback is operator-explicit only; no destructive rollback command was run.

## Validation

- `pytest tests/test_harness_eval.py -q -k "provider_runtime_preflight_blocks_hy3_provider_config_shape_before_mcp_launch or provider_runtime_recovery_summary_includes_hy3_config_shape_hint_body_free"`: passed, 2 passed.
- `pytest tests/test_harness_eval.py -q -k "provider_runtime_preflight or provider_runtime_recovery_summary"`: passed, 36 passed.
- `pytest -q`: passed, 1018 passed.

## Self-Model

Left unchanged. The current self-model already favors rollback-backed local behavior changes over validation-report-only
work and explicitly names provider/config preflight as a valid evolution lane. This run produced a behavior-path change
with tests, so no self-model revision was needed.

## Review Notes

- The new preflight validates configuration shape only; it does not validate real Hy3 network connectivity or call
  external providers.
- Raw provider config, raw endpoints, raw model identifiers, key-variable names, and secret values are not exported.
- Runtime launch remains disabled in provider-runtime diagnostic and recovery surfaces until local replay passes.
