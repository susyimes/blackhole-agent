# Self-Evolution Run Notes

- Source digest: `github-growth-20260624T093355.858114Z`
- Branch: `codex/blackhole-evolve/20260624T093455.251305-add-or-strengthen-local-provider-config-prefligh`
- Capability window: `skill-route-discovery`, pass 2 of 4
- Selected proposal: `p4-idle-watchdog-root-cause-reporting`
- Evidence reviewed:
  - `https://github.com/omnigent-ai/omnigent/issues/1119`
  - `https://github.com/dongshuyan/compass-skills`

## Hypothesis

Idle-watchdog failures are more useful to operators when the local route records recent transport root-cause classes, such as `no_route_to_host`, alongside watchdog timing. The local lesson fits this skill-route-discovery pass because it converts upstream runner evidence into a bounded, body-free validation lane before any activation or restart path.

## Rollback

- Rollback ref: `refs/blackhole-rollback/20260624T093354Z-watchdog-root-cause-skill-route-pass2`
- Rollback artifact: `artifacts/rollback/20260624T093354Z-watchdog-root-cause-skill-route-pass2.md`
- Recovery remains explicit operator action only.

## Changed Files

- `src/blackhole_agent/harness_eval.py`: added body-free watchdog diagnostics for `agent_workflow_route`, including normalized transport-error classification and control-plane surfacing.
- `tests/test_harness_eval.py`: added regression coverage for a 240-second watchdog timeout preceded by a `No route to host` transport error, with private request data excluded from output.
- `docs/architecture.md`: documented the watchdog diagnostic contract.

## Self-Model

`docs/self-model.md` was left unchanged. It already favors rollback-backed local behavior changes while keeping privacy leakage review-only, and this run did not produce evidence that the file is currently shaping behavior beyond that useful preference.

## Validation

- `powershell`: `$env:PYTHONPATH='src'; uv run --with pytest python -m pytest tests/test_harness_eval.py -q -k agent_workflow_route`
  - Result: passed, 9 tests.
- `powershell`: `$env:PYTHONPATH='src'; uv run --with pytest python -m pytest tests/test_docs_contracts.py -q`
  - Result: passed, 11 tests.

## Review Notes

- `p1-provider-config-preflight-silent-fallback` remains review-only because its validation gate is `privacy-leakage-human-review`; no token, credential, secret, private chat, PII, URL body, request body, or header value was exposed.
- The watchdog route reports normalized failure classes and timing only. Raw transport errors and request data are not exported.
- No restart, push, promotion, or remote execution was performed by this kernel.
