# blackhole-agent

Linear issue: https://linear.app/svmes/issue/SVM-23/黑洞项目自动在github生长的agent每小时索取github更新的内容

This repository is the durable private GitHub artifact for SVM-23.

SVM-23 describes a "black hole" agent that periodically asks GitHub for updates, extracts useful signals, and uses those signals to improve itself. The implementation is now based on the small controller style from `susyimes/mini-swe-agent`, especially its GitHub growth loop, with a local Codex CLI kernel for bounded self-improvement runs.

This repo intentionally does not contain credentials, default scheduled jobs, GitHub write automation, or automatic self-push behavior.

## Core Loop

```text
hourly trigger
  -> GitHub intake with explicit repo allowlist
  -> relevance filter
  -> learning digest
  -> candidate improvement proposals
  -> local verification
  -> optional local Codex CLI kernel run
  -> approval gate before external writes
  -> optional PR / Linear update
```

## Current Implementation

- Python package: `blackhole_agent`
- CLI: `blackhole` or `blackhole-agent`
- GitHub growth controller: `blackhole_agent.github_growth`
- Local Codex CLI kernel: `blackhole_agent.kernels.codex_cli`
- Structured digest output follows `schemas/hourly-digest.schema.json`

Install and run locally:

```bash
uv run blackhole --help
```

Create a read-only digest:

```bash
uv run blackhole \
  --repos susyimes/blackhole-agent,susyimes/mini-swe-agent \
  --output-dir .blackhole-agent/github-growth
```

Create a reviewable self-evolution task without running Codex:

```bash
uv run blackhole \
  --repos susyimes/mini-swe-agent \
  --evolution-mode plan \
  --repo-path .
```

Run the local Codex CLI kernel on a prepared branch:

```bash
uv run blackhole \
  --repos susyimes/mini-swe-agent \
  --evolution-mode codex \
  --repo-path . \
  --branch-prefix codex/blackhole-evolve
```

`codex` mode creates a local branch, invokes `codex exec` with a bounded task, writes run artifacts under the output directory, and leaves the resulting diff for human review. It does not push or merge.

## Principles

- Observe before changing.
- Store summaries and evidence links, not raw noise.
- Prefer proposals over automatic self-modification.
- Require an approval gate before GitHub writes, Linear writes, deployments, or policy changes.
- Keep repo allowlists, tokens, and runtime configuration outside the repository.

## Repo Contents

- `src/blackhole_agent/`: executable package.
- `tests/`: unit tests for intake, digesting, planning, and the Codex CLI kernel wrapper.
- `docs/architecture.md`: recommended system shape and component boundaries.
- `schemas/hourly-digest.schema.json`: a small JSON schema for structured hourly digests.
- `docs/implementation-plan.md`: proposed milestones for turning this seed into code.

## Next Implementation Inputs

Before coding the live agent, decide:

- Which event types it may ingest: commits, PRs, issues, releases, workflow runs, or all activity.
- Whether the agent may open PRs, write Linear comments, or only produce local reports.
- Which runtime should schedule it: GitHub Actions, local daemon, serverless, or another scheduler.
- How approval should work for self-updates.

