# Provider Runtime Control Pass 3: Approval Re-park Preflight

- Source digest: `github-growth-20260622T160624.254593Z`
- Capability window: `provider-runtime-control`, pass 3 of 4
- Selected proposal: `p2-provider-config-preflight`
- Evidence reviewed: `https://github.com/omnigent-ai/omnigent/pull/927`
- Rollback artifact: `artifacts/rollback/20260623T000000Z-provider-runtime-approval-repark-preflight.md`

## Hypothesis

The reusable lesson from the upstream PR is that local optimistic approval state can become stale when a provider or hook retry re-parks the same elicitation as pending. For this repository, the matching control point is the body-free `provider_runtime_preflight` lane: a fresh pending snapshot should clear the stale verdict marker, block provider launch, and surface a recovery hint without exporting raw approval ids, verdicts, or snapshots.

## Change

- Added `approval_repark` metadata handling to `provider_runtime_preflight`.
- Added `provider_approval_repark_pending` as a blocked failure class with recovery hints.
- Added fixture and focused test coverage for stale verdict clearing when the same elicitation is pending in a fresh snapshot.
- Updated architecture documentation for the new body-free provider approval state gate.

## Validation

- `pytest tests/test_harness_eval.py -q -k provider_runtime_preflight` passed: 15 passed, 109 deselected.
- `pytest tests/test_harness_eval.py -q` passed: 124 passed.
- `pytest tests/test_docs_contracts.py -q` passed: 9 passed.

## Review Notes

- No offensive behavior, unauthorized access, or privacy-leakage route was introduced.
- The preflight is metadata-only and does not launch providers.
- Raw approval ids, local verdicts, and provider snapshots remain omitted from structured output.
- The self-model was read and left unchanged; it already supported rollback-backed provider/config preflight evolution, and this run did not reveal a mismatch.
