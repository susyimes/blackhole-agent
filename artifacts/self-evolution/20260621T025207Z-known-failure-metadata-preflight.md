# Known-Failure Metadata Preflight

- Source digest: `github-growth-20260621T025207.809488Z`
- Capability theme: `skill-route-discovery`, pass 4 of 4
- Selected proposal: `p3-known-failure-test-state-preflight`
- Evidence URL: `https://github.com/omnigent-ai/omnigent`
- Branch: `codex/blackhole-evolve/20260621T025308.563341-introduce-a-local-preflight-or-config-check-for-`
- Rollback ref: `refs/rollback/20260621T025207Z-known-failure-preflight`
- Rollback artifact: `artifacts/rollback/20260621T025207Z-known-failure-preflight.txt`

## Evidence And Hypothesis

The public Omnigent repository presents a multi-agent meta-harness with policy,
sandboxing, and test-oriented workflow surfaces. The specific digest proposals
around removing known-failure metadata and generic pull request activity were
low-detail, so this run did not copy upstream behavior. The local reusable
lesson is a bounded preflight: before growth runs consume green test evidence,
they should know whether expected-failure metadata disappeared, emptied, or
changed without an explicit gate refresh.

Hypothesis: a deterministic `known_failure_metadata_preflight` behavior in the
local harness evaluator improves reliability by making stale expected-failure
assumptions operator-visible before activation, while preserving the existing
privacy boundary by exporting counts, hashes, diagnostics, and recovery hint
codes only.

## Changes

- Added `known_failure_metadata_preflight` to the supported local harness
  behaviors.
- Added metadata-only diagnostics for absent metadata, empty current metadata,
  removed expected failures, additions without local test evidence, unexplained
  removals, and missing expected-failure gate refresh records.
- Added supervisor handoff fields with replay command and recovery hint codes.
- Added a fixture for removed known-failure metadata and inline tests for absent
  and current metadata states.
- Documented the preflight in `docs/architecture.md` and
  `docs/upstream-evidence-interpretation.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k known_failure_metadata_preflight`: passed, 2 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k known_failure_metadata_preflight`: passed, 1 passed.
- `python -m ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py tests/test_docs_contracts.py`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or known_failure_metadata_preflight"`: passed, 3 passed.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 9 passed.
- `python -m pytest tests/test_harness_eval.py tests/test_docs_contracts.py -q`: passed, 125 passed.
- `git diff --check`: passed; only Windows line-ending conversion warnings were reported.

## Self-Model

Read `docs/self-model.md` and left it unchanged. Its current preference already
supports rollback-backed, locally validated provider/config/test preflight work
outside the narrow offensive/privacy boundary. This run needed an executable
local preflight and operator-facing docs rather than a revised self-description.

## Review Notes

- Raw known-failure IDs, raw test names, raw failure text, quarantine bodies,
  URLs, private paths, tokens, and credentials are not exported by the new
  preflight.
- The preflight does not edit known-failure metadata, remove quarantine entries,
  run tests, launch providers, perform remote execution, push, promote, or
  restart. It only reports whether expected-failure assumptions should be
  refreshed before test gating consumes evidence.
- Generic Omnigent PR/push movement remains weak evidence. It justified a local
  validation lane, not direct adoption of an upstream patch.
