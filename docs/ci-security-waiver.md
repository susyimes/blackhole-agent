# CI Security Waiver Validation

Source digest: `github-growth-20260618T092043.842756Z`

Reviewed evidence:

- `https://github.com/omnigent-ai/omnigent`
- `https://github.com/omnigent-ai/omnigent/pull/637`
- `https://github.com/omnigent-ai/omnigent/pull/637#pullrequestreview-4523361128`
- `https://github.com/omnigent-ai/omnigent/pull/637#pullrequestreview-4523494421`

The local lesson is a deterministic validation model for security-scan waivers.
It does not change this repository's live CI. It records the expected contract for
future CI integrations: a failed, missing, skipped, or timed-out security scan can
be bypassed only when the configured waiver label is present in the pull request
label snapshot for the same workflow rerun attempt.

## Local Contract

- Scan conclusion `success` passes without a waiver.
- Any non-success scan conclusion fails closed unless the exact label-only waiver
  condition is present.
- The waiver source is pull request label metadata only. Comments, commit
  messages, workflow inputs, environment variables, secrets, token values, and
  free-form text are not waiver sources.
- Reruns must use a label snapshot captured for the current run attempt. A stale
  label snapshot from an earlier attempt blocks the waiver path even if it
  contains the waiver label.
- Diagnostics record metadata reasons such as `missing_waiver_label` and
  `stale_label_snapshot_for_rerun`; they do not record credentials, private data,
  or raw CI logs.

This keeps the waiver behavior locally replayable while preserving the privacy
boundary from the source proposal.
