# Evolution Run: Provider Runtime Control Pass 4

Source digest: github-growth-20260702T150626.682059Z
Capability theme: provider-runtime-control
Branch: codex/blackhole-evolve/20260702T150736.486792-create-a-bounded-local-skill-route-discovery-tes
Rollback ref: refs/blackhole-rollback/20260702T150625-provider-runtime-control-pass4
Rollback note: artifacts/rollback-20260702T150625Z-provider-runtime-control-pass4.md

## Evidence Reviewed

- https://github.com/lyra81604/zhengxi-views: carried by the source digest as bounded skill-route evidence; not used for external activation.
- https://github.com/QwenLM/Qwen-AgentWorld, https://github.com/TianhangZhuzth/Fundamental-Ava, and https://github.com/ksimback/looper: carried by the source digest as adjacent general-agent evidence; useful as validation-boundary pressure, not runtime execution.
- Local pass-1 and pass-2 artifacts showed provider-runtime recovery already emits body-free operator plans and diagnostic manifests, while `supervisor_readiness` remained less explicit about privacy-sensitive recovery.

## Hypothesis

The pass-4 completion should make provider-runtime recovery gates visible on the scheduler-facing handoff surface. If credential failover or other privacy-sensitive remediation is present, a supervisor should see the review requirement without parsing nested recovery steps or raw diagnostics.

## Change

- Added `privacy_sensitive_recovery_present`, `privacy_review_required_count`, `privacy_sensitive_auto_recovery_allowed`, and `operator_review_required` to `provider_runtime_supervisor_readiness`.
- Extended provider-runtime recovery summary tests for blocked privacy-sensitive recovery and degraded replay-only recovery.
- Documented the supervisor-visible privacy gate in `docs/skill-route-discovery.md`.

## Safety Boundary

The change does not launch providers, inspect credentials, perform credential failover, contact remote services, or export raw provider diagnostics, URLs, paths, commands, headers, tokens, reset values, response bodies, or environment values. It only promotes existing redacted recovery-hint metadata into the supervisor handoff.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "provider_runtime_recovery_summary"`: passed
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed
- `python -m pytest tests/test_harness_eval.py -q -k "provider_runtime_preflight or provider_runtime_recovery_summary"`: passed
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`: passed

## Self-Model

`docs/self-model.md` was left unchanged. It already supports rollback-backed provider/config preflight improvements and the narrow safety boundary used by this run.

## Review Notes

- Evidence URLs were treated as carried digest context; no upstream code was imported, cloned, or executed.
- Downstream consumers of `supervisor_readiness` should tolerate the new fields or assert them explicitly when privacy-sensitive recovery is relevant.
