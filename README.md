# SVM-23 GitHub Growth Agent

Linear issue: https://linear.app/svmes/issue/SVM-23/黑洞项目自动在github生长的agent每小时索取github更新的内容

This repository is the durable private GitHub artifact for SVM-23.

SVM-23 describes a "black hole" agent that periodically asks GitHub for updates, extracts useful signals, and uses those signals to improve itself. The first Symphony pass produced a no-code architecture handoff because the Linear issue did not specify an implementation repository, GitHub scope, runtime, digest destination, approval policy, or credential model.

This repo turns that handoff into a stable project seed. It intentionally does not contain credentials, scheduled jobs, GitHub write automation, or self-modifying code.

## Core Loop

```text
hourly trigger
  -> GitHub intake with explicit repo allowlist
  -> relevance filter
  -> learning digest
  -> candidate improvement proposals
  -> local verification
  -> approval gate
  -> optional PR / Linear update
```

## Principles

- Observe before changing.
- Store summaries and evidence links, not raw noise.
- Prefer proposals over automatic self-modification.
- Require an approval gate before GitHub writes, Linear writes, deployments, or policy changes.
- Keep repo allowlists, tokens, and runtime configuration outside the repository.

## Repo Contents

- `docs/architecture.md`: recommended system shape and component boundaries.
- `schemas/hourly-digest.schema.json`: a small JSON schema for structured hourly digests.
- `docs/implementation-plan.md`: proposed milestones for turning this seed into code.

## Next Implementation Inputs

Before coding the live agent, decide:

- Which GitHub owner/repositories it may read.
- Which event types it may ingest: commits, PRs, issues, releases, workflow runs, or all activity.
- Where digests should be stored.
- Whether the agent may open PRs, write Linear comments, or only produce local reports.
- Which runtime should schedule it: GitHub Actions, local daemon, serverless, or another scheduler.
- How approval should work for self-updates.

