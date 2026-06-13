# blackhole-agent

[![Python](https://img.shields.io/badge/python-3.10%2B-111827?style=for-the-badge&logo=python)](https://www.python.org/)
[![Runtime](https://img.shields.io/badge/runtime-uv-111827?style=for-the-badge)](https://github.com/astral-sh/uv)
[![Kernel](https://img.shields.io/badge/kernel-Codex_CLI-111827?style=for-the-badge)](https://github.com/openai/codex)
[![Mode](https://img.shields.io/badge/mode-review_gated-111827?style=for-the-badge)](#safety-model)

> A GitHub trend-eating growth agent.
> It watches the public ecosystem, distills useful signals, and prepares bounded self-improvements for human review.

```text
                         public GitHub momentum
                                  |
                                  v
                    .-----------------------------.
                 .-'   blackhole-agent event       '-.
               .'       horizon                      '.
              /                                           \
             |   trend search -> digest -> proposal       |
             |          -> persona -> Codex kernel        |
             |          -> rollback point -> review       |
              \                                           /
               '.                                       .'
                 '-._______________________________.-'
                                  |
                                  v
                     small, inspectable local diff
```

This repository is the durable private GitHub artifact for SVM-23:

`https://linear.app/svmes/issue/SVM-23/黑洞项目自动在github生长的agent每小时索取github更新的内容`

## What It Is

`blackhole-agent` is a small controller for a larger idea:

- scan public GitHub trends on a schedule
- convert noisy repository activity into compact learning digests
- select useful patterns that could improve this agent
- create reviewable self-evolution tasks
- run a local Codex CLI kernel when explicitly requested
- preserve a rollback point before source mutation
- keep external writes behind an approval gate

It borrows the deliberately small controller style of `susyimes/mini-swe-agent`, but this repository is its own bounded growth loop.

## Control Loop

```text
hourly trigger
  -> GitHub trend discovery
  -> recent event intake for discovered repos
  -> relevance and risk scoring
  -> structured learning digest
  -> candidate improvement proposals
  -> persona-layer task framing
  -> rollback point creation
  -> optional local Codex CLI kernel run
  -> local validation
  -> human review / external approval gate
```

GitHub does not expose an official Trending REST endpoint, so the controller approximates trends with repository search: recently created public repositories, minimum stars, optional query terms, and sorting by stars, forks, or updated time.

## Quickstart

Install dependencies and inspect the CLI:

```bash
uv run blackhole --help
```

Create a read-only public trend digest:

```bash
uv run blackhole \
  --trend-query "topic:ai" \
  --trend-window-days 7 \
  --trend-min-stars 25 \
  --trend-limit 10 \
  --output-dir .blackhole-agent/github-growth
```

Create a reviewable self-evolution plan without running Codex:

```bash
uv run blackhole \
  --trend-query "agent language:Python" \
  --evolution-mode plan \
  --repo-path .
```

Run the local Codex CLI kernel on a prepared branch:

```bash
uv run blackhole \
  --trend-query "agent language:Python" \
  --evolution-mode codex \
  --repo-path . \
  --branch-prefix codex/blackhole-evolve
```

Manual repository mode remains available for focused experiments:

```bash
uv run blackhole \
  --repos susyimes/mini-swe-agent,susyimes/blackhole-agent \
  --output-dir .blackhole-agent/github-growth
```

## System Map

| Layer | Module | Job |
| --- | --- | --- |
| CLI | `blackhole_agent.cli` | Typer entry point |
| Trend controller | `blackhole_agent.github_growth` | Search trends, fetch events, write digests, plan evolution |
| Persona layer | `blackhole_agent.persona` | Mission, selection policy, rollback contract, restart boundary |
| Codex kernel | `blackhole_agent.kernels.codex_cli` | Bounded `codex exec` wrapper |
| Digest schema | `schemas/hourly-digest.schema.json` | Structured output contract |
| Architecture docs | `docs/architecture.md` | Component boundaries and gates |

## Persona Layer

The self-evolution task is not just a loose prompt. It includes a versioned persona layer from `blackhole_agent.persona`.

That layer defines:

- identity: ecosystem learner, not hidden publisher
- mission: watch GitHub momentum and learn safely
- selection policy: choose small, testable improvements
- self-modification protocol: one conceptual change per run
- rollback contract: preserve a universal recovery point before mutation
- restart contract: restart only through an external scheduler or supervisor
- hard boundaries: no secrets, no silent writes, no permission expansion

See `docs/persona-layer.md`.

## Rollback First

Before `codex` mode switches to a self-evolution branch, the controller writes:

- `latest-rollback-point.json`
- `latest-rollback-point.md`

The rollback point records:

- original branch
- original HEAD
- local rollback ref
- pre-run dirty status
- explicit recovery commands

The recovery path is intentionally explicit because it can discard work:

```bash
git switch <original-branch>
git reset --hard <rollback-ref>
git clean -fd
```

This is the escape hatch if a future activation cannot start, imports break, or unsafe behavior appears.

## Safety Model

This repo intentionally does not contain credentials, default scheduled jobs, GitHub write automation, or automatic self-push behavior.

The default posture:

- observe before changing
- store evidence links and summaries, not raw noise
- create rollback before mutation
- prefer proposals over automatic self-modification
- require approval before GitHub writes, Linear writes, deployments, merges, or policy changes
- keep runtime configuration and tokens outside the repository

`codex` mode leaves a local diff for review. It does not push or merge.

## Output Artifacts

One run can write:

| Artifact | Meaning |
| --- | --- |
| `latest.json` | latest structured GitHub growth digest |
| `latest.md` | human-readable digest |
| `state.json` | cursor, seen events, trend star snapshots |
| `latest-self-evolution-plan.json` | structured self-evolution plan |
| `latest-self-evolution-plan.md` | Codex task with persona layer |
| `latest-rollback-point.json` | machine-readable recovery anchor |
| `latest-rollback-point.md` | human-readable rollback instructions |
| `latest-codex-run.json` | Codex kernel run metadata |

## Development

Run tests:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```

## Roadmap

- stronger trend scoring beyond stars and recency
- richer signal clustering across repositories
- automatic local validation plans per proposal type
- external supervisor for hourly scheduling and restart
- approval records for PR creation and Linear updates
- startup health checks that can trigger the rollback artifact

## North Star

The agent should feel like a black hole for useful public engineering momentum:

it absorbs signal, compresses it, and emits small, reviewable improvements.

No drama. No hidden writes. No mystery meat autonomy. Just a steady gravity well for making itself better.
