# Self-Evolution Run

Digest: `github-growth-20260614T054932.510920Z`
Proposal: `trend:ClaudioDrews/memory-os-1`
Evidence: https://github.com/ClaudioDrews/memory-os

## Hypothesis

Memory OS emphasizes that injected context needs an explicit authority policy or agents waste time rediscovering existing context. The safest local lesson is to make blackhole-agent self-evolution tasks treat the digest and evidence URLs as primary context while avoiding broad trend rediscovery.

## Change

- Added a digest evidence policy to generated self-evolution tasks.
- Added regression assertions for the planner prompt.

## Validation

`uv run pytest tests\test_github_growth.py` passed with 19 tests.

## Rollback

Rollback artifacts were created before source edits:

- `.blackhole-agent/github-growth/latest-rollback-point.json`
- `.blackhole-agent/github-growth/latest-rollback-point.md`

