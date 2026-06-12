# Implementation Plan

## Phase 1: Local Read-Only Prototype

- Add a GitHub client using a local token from environment.
- Support an explicit repository allowlist.
- Fetch recent issues, pull requests, commits, releases, and workflow runs.
- Persist a cursor and processed event IDs locally.
- Generate an hourly digest markdown file.
- Add tests for deduplication, cursor handling, empty updates, and rate limit responses.

## Phase 2: Structured Digest And Proposal Drafting

- Emit digest JSON that follows `schemas/hourly-digest.schema.json`.
- Add a proposal generator that maps digest items to follow-up actions.
- Keep generated patches local until approval.
- Add tests for relevance scoring and proposal classification.

## Phase 3: Approval-Gated Writes

- Add an explicit approval record format.
- Allow approved PR creation for a configured target repository.
- Allow approved Linear comment creation.
- Record every external write with source digest, approval ID, and result URL.

## Phase 4: Self-Improvement Boundary

- Allow the agent to propose changes to this repository.
- Require PR review before merge.
- Add regression tests that prevent automatic self-push without approval.
- Add a safety report that lists every policy and scope used by a run.

## Non-Goals

- No hidden credential storage.
- No default writes to GitHub or Linear.
- No automatic deployment.
- No automatic merge.
- No automatic policy or token scope expansion.

