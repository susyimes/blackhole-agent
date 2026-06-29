# Provider Runtime Control Pass 1

- Source digest: github-growth-20260629T155904.213690Z
- Theme: provider-runtime-control
- Rollback ref: refs/blackhole-rollback/20260629T155903Z-provider-runtime-control-pass1
- Rollback artifact: artifacts/rollback/20260629T155903Z-provider-runtime-control-pass1.md
- Self-model: read and left unchanged

## Evidence

- https://github.com/larlarua/AutoCVE/issues/5
- https://github.com/larlarua/AutoCVE/issues/6

The carried evidence points to provider failures around missing request parameters and model connection checks. I treated the issue details as narrow, provider-configuration evidence and avoided broad trend discovery.

## Hypothesis

Provider/runtime failures should be caught as body-free local preflight diagnostics before a larger autonomous task starts. A useful local behavior is to block provider launch when required temperature-like request metadata is absent or when model connectivity proof is missing or failed.

## Change

- Added provider request-parameter preflight output with hashed parameter metadata, temperature-like classification, and recovery hints.
- Added provider model-connectivity preflight output with checked/reachable state, status class, normalized error category, and recovery hints.
- Integrated both checks into the existing `provider_runtime_preflight` blocking order, diagnostics, output, recovery plan, and supervisor replay path.
- Added focused regression tests for missing temperature-like metadata, failed connectivity, unchecked connectivity, passing configurations, and raw value non-export.

## Validation

- `pytest tests/test_harness_eval.py -q -k provider_runtime_preflight`
  - Result: 32 passed, 146 deselected
- `ruff check src\blackhole_agent\harness_eval.py tests\test_harness_eval.py`
  - Result: All checks passed
- `pytest -q`
  - Result: 524 passed

## Review Notes

- The preflights are metadata-only and do not call providers.
- The output hashes parameter names and provider/model/endpoint labels, and explicitly marks request bodies, parameter values, model ids, endpoints, and error bodies as not exported.
- No offensive, unauthorized-access, or privacy-leakage route was added.
