# Evolution Run: Provider Runtime Control Pass 2

Source digest: github-growth-20260702T142626.683072Z
Capability theme: provider-runtime-control
Branch: codex/blackhole-evolve/20260702T142727.611160-add-a-bounded-local-skill-route-discovery-valida
Rollback ref: refs/blackhole-rollback/20260702T142625-provider-runtime-control-pass2
Rollback note: artifacts/rollback-20260702T142625Z-provider-runtime-control-pass2.md

## Evidence Reviewed

- https://github.com/lyra81604/zhengxi-views: carried by the source digest as bounded skill-route evidence; useful as route evidence only, not runtime activation.
- https://github.com/QwenLM/Qwen-AgentWorld, https://github.com/TianhangZhuzth/Fundamental-Ava, and https://github.com/ksimback/looper: carried by the source digest as adjacent general-agent evidence that remains harness-eval material before implementation lanes.
- Local pass-1 artifact `artifacts/evolution-20260702T140844Z-provider-runtime-control-pass1.md`: provider-runtime recovery already emitted body-free replay plans, but privacy-sensitive recovery was only visible per recovery step.

## Hypothesis

Provider-runtime recovery should make privacy-sensitive remediation operator-visible at the top level. If a usage-limit preflight suggests credential-pool failover, the recovery plan should say that automated recovery and credential failover remain blocked without privacy review, while still preserving local replay commands and body-free diagnostics.

## Change

- Added `provider_runtime_hint_requires_privacy_review` and reused it in diagnostic manifests and operator recovery plans.
- Added top-level `privacy_sensitive_recovery_present`, `privacy_review_required_count`, and `privacy_sensitive_auto_recovery_allowed` to provider-runtime diagnostic manifests.
- Added top-level `privacy_sensitive_recovery_present`, `privacy_review_required_count`, `privacy_sensitive_auto_recovery_allowed`, `credential_failover_allowed_without_review`, and `operator_review_required` to provider-runtime operator recovery plans.
- Extended focused provider-runtime tests for wire API, usage-limit credential failover, and aggregated recovery summaries.
- Documented the new body-free privacy-sensitive recovery gate in `docs/skill-route-discovery.md`.

## Safety Boundary

The change does not launch providers, perform credential failover, read credential values, contact remote services, or export raw headers, token values, reset timestamps, response bodies, provider bodies, URLs, paths, or command bodies. Credential-pool failover remains privacy-review gated.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "provider_runtime_preflight_blocks_usage_limit_429_without_credential_or_body_export or provider_runtime_recovery_summary_aggregates_body_free_hints or provider_runtime_preflight_requires_chat_wire_api_route_evidence_before_launch"`: passed
- `python -m pytest tests/test_harness_eval.py -q -k "provider_runtime_preflight or provider_runtime_recovery_summary"`: passed
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`: passed

## Self-Model

`docs/self-model.md` was left unchanged. It already supports rollback-backed provider/config preflight improvements and did not need revision for this run.

## Review Notes

- The evidence URLs were used as carried digest context; no upstream code was imported or executed.
- The new fields are schema additions to local diagnostic dictionaries, so downstream exact-shape consumers should prefer explicit assertions for the new privacy gate where relevant.
