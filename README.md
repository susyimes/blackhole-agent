# blackhole-agent

[![Python](https://img.shields.io/badge/python-3.10%2B-111827?style=for-the-badge&logo=python)](https://www.python.org/)
[![Runtime](https://img.shields.io/badge/runtime-uv-111827?style=for-the-badge)](https://github.com/astral-sh/uv)
[![Kernel](https://img.shields.io/badge/kernel-Codex_CLI-111827?style=for-the-badge)](https://github.com/openai/codex)
[![Mode](https://img.shields.io/badge/mode-autonomous_local_evolution-111827?style=for-the-badge)](#autonomy-model)

> A GitHub trend-eating growth agent.
> It watches the public ecosystem, distills useful signals, and applies rollback-backed local self-improvements.

<p align="center">
  <img src="docs/assets/blackhole-agent-hero.svg" alt="blackhole-agent control loop" width="100%" />
</p>

## What It Is

`blackhole-agent` is a small controller for a larger idea:

- scan public GitHub trends on a schedule
- convert noisy repository activity into compact learning digests
- select useful patterns that could improve this agent
- create autonomous self-evolution tasks
- run a local Codex CLI kernel when explicitly requested
- preserve a rollback point before source mutation
- keep every material action traceable through artifacts

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
  -> autonomous local application / audit trail
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

Create an autonomous self-evolution plan without running Codex:

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
| Architecture docs | `docs/architecture.md` | Component boundaries and runtime policy |

## Persona Layer

The self-evolution task is not just a loose prompt. It includes a versioned persona layer from `blackhole_agent.persona`.

That layer defines:

- identity: ecosystem learner, not hidden publisher
- mission: watch GitHub momentum and learn safely
- selection policy: choose small, testable improvements
- self-modification protocol: one conceptual change per run
- rollback contract: preserve a universal recovery point before mutation
- restart contract: restart only through an external scheduler or supervisor
- autonomy contract: self-apply local changes when rollback-backed and validated

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

## Autonomy Model

This repo is designed for local autonomous evolution first. The agent should be able to change its own checkout, validate the change, and leave rollback artifacts as the control surface.

The default posture:

- observe, then mutate locally
- store evidence links and summaries, not raw noise
- create rollback before mutation
- self-apply small local improvements after validation
- record material filesystem and external actions as artifacts
- let runtime configuration define available capabilities

`codex` mode applies changes on a prepared evolution branch. Audit can happen after the fact; rollback is the escape hatch when startup or validation fails.

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
- external supervisor for hourly scheduling, restart, and health-based rollback
- autonomous application records for PR creation and Linear updates
- startup health checks that can trigger the rollback artifact

## North Star

The agent should feel like a black hole for useful public engineering momentum:

it absorbs signal, compresses it, and emits small, validated local improvements.

Less permission-slip paperwork. More gravity. More evolution. Still recoverable when the singularity bites back.
