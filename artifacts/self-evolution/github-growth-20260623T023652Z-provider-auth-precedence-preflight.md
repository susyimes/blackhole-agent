# Provider Auth Precedence Preflight

Source digest: `github-growth-20260623T023652.304538Z`

Evidence reviewed:
- `https://github.com/omnigent-ai/omnigent/issues/962`

Hypothesis:
LiteLLM-backed Claude and Codex routes need a local, metadata-only preflight
that distinguishes generic missing provider environment from a more specific
auth-precedence failure: proxy or Bedrock auth was the expected route, but the
harness did not receive the required environment keys and could fall back to
native auth.

Rollback:
- Artifact: `artifacts/rollback/20260623T023753Z-provider-auth-env-inheritance.txt`
- Ref: `refs/blackhole/rollback/20260623T023753Z-provider-auth-env-inheritance`
- Original HEAD: `d93807fa3ff70d046223375a6756fc9d3c751b4a`

Local change:
- Added `auth_precedence` metadata evaluation to `provider_runtime_preflight`.
- Added failure mode and recovery hint:
  `provider_auth_precedence_fallback_risk`.
- Added regression coverage for a blocked Claude LiteLLM/Bedrock route and a
  ready Codex route.
- Documented the expected auth precedence and privacy constraints.

Privacy boundary:
The preflight exports route labels, key counts, key hashes, missing counts, and
recovery codes only. It does not export environment values, token values, proxy
URLs, or raw key names.

Self-model decision:
`docs/self-model.md` was left unchanged. The current self-model already prefers
rollback-backed local provider/config preflight improvements, and this run did
not produce evidence that its structure or safety boundary should change.

Validation:
- `pytest tests/test_harness_eval.py -q -k "provider_runtime_preflight_blocks_litellm_bedrock_auth_fallback_before_launch or provider_runtime_preflight"` passed.
- `pytest tests/test_docs_contracts.py -q` passed.

Review notes:
- The external evidence is an open upstream issue, not a merged upstream fix.
  The local implementation is therefore a reversible preflight experiment rather
  than a claim about upstream behavior.
- The route remains local replay only; it does not launch Claude, Codex,
  LiteLLM, Bedrock, or any provider harness.
