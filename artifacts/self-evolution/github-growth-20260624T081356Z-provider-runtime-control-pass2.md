# Provider Runtime Control Pass 2

- Source digest: `github-growth-20260624T081356.259922Z`
- Capability theme: `provider-runtime-control`
- Rollback artifact: `artifacts/rollback/20260624T081356Z-provider-runtime-control-pass2-windows-runner-preflight.md`
- Rollback ref: `refs/rollback/20260624T081356Z-provider-runtime-control-pass2-windows-runner-preflight`

## Evidence

Reviewed the current Omnigent evidence narrowly. The repository describes a multi-harness agent orchestration layer over Claude Code, Codex, Cursor, Pi, and custom agents. Issue `#1108` describes a provider/runtime observability failure where a `codex-native` auth or error turn can appear as an empty success. Pull request `#1107` shows a related validation-control pattern: use cheap detection to scope heavier checks, while failing open when the changed-file signal is unavailable.

## Hypothesis

The provider-runtime preflight lane should catch Windows-native runner mistakes before launch, using body-free diagnostics and recovery hints. This is the closest local continuation of the active slice because this wake is running on Windows/PowerShell and proposal `p3-windows-runner-preflight` specifically calls out path handling, shell assumptions, and workspace resolution.

## Changes

- Added `windows_runner` metadata evaluation inside `provider_runtime_preflight`.
- Blocks provider launch for unsupported Windows shell families, shell-body command strings, unquoted path arguments, unresolved/out-of-repo workspaces, or missing local replay proof.
- Added `provider_windows_runner_*` recovery hints for supervisor/operator replay.
- Added a regression test that proves private command, path, workspace, and shell executable values are not exported.
- Documented the preflight contract in `docs/architecture.md`.

## Validation

- `python -m compileall -q src/blackhole_agent/harness_eval.py`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k windows_runner`: passed, 1 passed.
- `python -m pytest tests/test_harness_eval.py -q -k provider_runtime_preflight`: passed, 28 passed.
- `python -m ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py`: passed.

## Self-Model

Read `docs/self-model.md` and left it unchanged. Its current preference already treats provider/config preflight checks and locally validated behavior changes as in-bounds when rollback-backed. This run found a concrete behavior path, so a self-description edit would be ornamental.

## Review Notes

- This does not execute Windows runner commands, launch providers, expose credentials, or change supervisor activation.
- The new lane is metadata-only. Raw command arguments, path values, workspace values, shell bodies, provider bodies, and secrets remain omitted or hashed.
