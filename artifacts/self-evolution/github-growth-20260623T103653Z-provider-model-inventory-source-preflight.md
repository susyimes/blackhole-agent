# Provider Model Inventory Source Preflight

- Source digest: `github-growth-20260623T103653.044328Z`
- Branch: `codex/blackhole-evolve/20260623T103806.480368-add-a-local-provider-config-preflight-validation`
- Rollback artifact: `artifacts/rollback/20260623T103652Z-provider-config-preflight-source-reporting.md`
- Rollback ref: `refs/rollback/20260623T103652Z-provider-config-preflight-source-reporting`

## Evidence

- `https://github.com/omnigent-ai/omnigent/issues/998` reports a dispatchable
  `cursor-native` worker whose `sys_list_models` row shows `source: "none"`,
  misleading the driving agent into treating the worker as unusable.
- `https://github.com/baskduf/FableCodex` and
  `https://github.com/dongshuyan/compass-skills` continue to support the local
  skill-route rule: external workflow and skill signals should become bounded,
  locally validated lanes before activation.

## Hypothesis

Provider inventory source attribution is a bounded local preflight lane. If a
dispatchable worker row reports `source: none`, the controller should block
provider launch with an explicit recovery hint before runtime exposure.

## Change

- Added `evaluate_provider_model_inventory_preflight` to
  `provider_runtime_preflight`.
- Added `provider_model_source_none` and `provider_model_inventory_missing`
  recovery hints.
- Added focused regression coverage for a cursor-native-style dispatchable
  worker row with `source: none` and a passing concrete-source row.
- Documented the metadata-only model inventory source check in
  `docs/architecture.md`.

## Validation

- `pytest tests/test_harness_eval.py -q -k "provider_runtime_preflight_blocks_dispatchable_worker_inventory_with_none_source or provider_runtime_preflight_blocks_missing_or_malformed_model_command_before_launch"`
  - Result: 2 passed, 139 deselected.
- `pytest tests/test_harness_eval.py -q -k provider_runtime_preflight`
  - Result: 25 passed, 116 deselected.

## Self-Model Decision

`docs/self-model.md` was left unchanged. The current self-model already prefers
direct, rollback-backed local behavior changes over validation-only artifacts,
and this run followed that preference. No new evidence showed the file was
blocking or shaping behavior incorrectly.

## Review Notes

- The new check is metadata-only: worker labels, source labels, and model ids
  are hashed or counted rather than exported.
- No provider is launched, no upstream code is executed, and no external skill
  package is installed or enabled.
