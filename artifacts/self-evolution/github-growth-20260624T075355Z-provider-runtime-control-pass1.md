# Provider Runtime Control Pass 1

- Source digest: `github-growth-20260624T075355.713548Z`
- Capability theme: `provider-runtime-control`
- Pass: 1 of 4
- Rollback artifact: `artifacts/rollback/20260624T075354Z-provider-runtime-control-pass1.md`
- Rollback ref: `refs/rollback/20260624T075354Z-provider-runtime-control-pass1`

## Evidence

- `https://github.com/omnigent-ai/omnigent/issues/1108` reports a codex-native terminal turn where an auth/error item was discarded and the parent saw completed empty output.
- `https://github.com/omnigent-ai/omnigent/pull/1107` was reviewed as adjacent gating context, but the directly reusable lesson came from the auth/error observability issue.
- The local repository already had a metadata-only `provider_runtime_preflight` lane with recovery hints and privacy-preserving fixtures.

## Hypothesis

A synthetic terminal-turn outcome check belongs in the existing provider runtime preflight lane. If a completed turn has empty assistant output plus auth/error metadata, the local harness should block with body-free diagnostics and a recovery hint instead of allowing an empty success state.

## Change

- Added `turn_outcome` classification inside `provider_runtime_preflight`.
- Added recovery hints for `provider_turn_auth_failed`, `provider_turn_error_item_reported`, and `provider_turn_empty_success_suspect`.
- Added a synthetic codex-native 401-like fixture that includes private sentinel bodies and asserts they are not exported.
- Documented the terminal-turn preflight contract in `docs/architecture.md`.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. The current preference already explicitly allows provider/config preflight checks and locally validated behavior changes when rollback-backed; this run did not reveal a better self-description than the existing one.

## Validation

- `pytest tests/test_harness_eval.py -q -k provider_runtime_preflight`
- `ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py`
- `pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`
- `pytest tests/test_harness_eval.py -q`

All validation commands passed.

## Review Notes

- No real provider credentials were used.
- Raw provider error body, assistant output, credential values, token labels, and private turn content remain omitted.
- The change does not restart or launch providers; it only improves local replay diagnostics and recovery hints.
