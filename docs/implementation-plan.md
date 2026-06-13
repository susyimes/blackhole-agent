# Implementation Plan

## Phase 1: Local Read-Only Prototype

- [x] Add a GitHub client using a local token from environment.
- [x] Discover public GitHub trend repositories with bounded repository search.
- [x] Keep explicit repository lists available as a manual/debug mode.
- [x] Fetch recent GitHub repository events and normalize issues, pull requests, commits, releases, and related activity.
- [x] Persist a cursor, processed event IDs, first-seen trend repositories, and last observed trend star counts locally.
- [x] Persist lightweight memory for useful repositories, topics, and proposed lessons.
- [x] Generate hourly digest JSON and markdown files.
- [x] Add tests for deduplication, cursor handling, digest writing, and controller behavior.

## Phase 2: Structured Digest And Proposal Drafting

- [x] Emit digest JSON that follows `schemas/hourly-digest.schema.json`.
- [x] Add a proposal generator that maps digest items to follow-up actions.
- [x] Bias proposal ordering with the lightweight memory layer.
- [x] Keep generated patches local, rollback-backed, and autonomously applicable on an evolution branch.
- [x] Add tests for relevance scoring and proposal classification.

## Phase 2.5: Local Codex CLI Kernel

- [x] Add a `CodexCliKernel` wrapper around `codex exec`.
- [x] Pass long tasks through stdin instead of command-line arguments.
- [x] Capture Codex's final message and run metadata as local artifacts.
- [x] Add `--evolution-mode codex` to create a branch and run the kernel locally.
- [x] Write a rollback point before local self-evolution branch creation.
- [x] Add tests that verify Codex command construction without invoking the real CLI.

## Phase 3: Autonomous Application Records

- Add an explicit application record format.
- Allow configured PR creation for a configured target repository.
- Allow configured Linear comment creation.
- Record every external write with source digest, runtime capability, and result URL.

## Phase 4: Self-Improvement Boundary

- Allow the agent to propose changes to this repository.
- Allow autonomous local application on a prepared evolution branch after rollback point creation.
- Add regression tests that prevent unconfigured remote writes.
- Add a safety report that lists every policy and scope used by a run.

## Non-Goals

- No hidden credential storage.
- No unconfigured writes to GitHub or Linear.
- No automatic deployment.
- No automatic merge without a configured runtime policy.
- No implicit runtime capability expansion.

