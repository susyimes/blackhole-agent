# Skill Route Discovery Pass 4

Run: `20260704T160433Z`
Source digest: `github-growth-20260704T160434.504032Z`
Branch: `codex/blackhole-evolve/20260704T160537.161857-run-a-bounded-local-discovery-lane-for-reverse-f`

## Hypothesis

Reverse-flow-style skill workflow evidence should complete through the existing
pass-4 skill-route-discovery handoff instead of another isolated fixture. The
operator-visible packet should prove that:

- reverse-flow skill evidence maps to a bounded local test lane first;
- reverse-flow fork evidence is lineage pressure, not separate activation
  authority;
- zhengxi-views remains a bounded skill-workflow documentation lane;
- general agent projects remain `agent_harness_eval_required` before any direct
  implementation lane.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/iamcaozhi/reverse-flow-skill`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`

The reverse-flow evidence shows a public Agent/Codex skill package with
`skills/reverse-flow`, scripts, install examples, and local sandbox/CTF reverse
workflow framing. The `iamcaozhi` repository is a fork of the lingbol088-spec
repository, so it is treated as route pressure only.

## Rollback

Rollback artifact:
`artifacts/rollback/20260704T160433Z-skill-route-discovery-pass4/rollback-point.md`

Rollback ref:
`refs/rollback/20260704T160433Z-skill-route-discovery-pass4`

## Changes

- Added an explicit pass-4 dispatcher branch for
  `github-growth-20260704T160434.504032Z`.
- Added a frozen current-digest fixture for the reverse-flow, zhengxi, and
  general-agent evidence set.
- Added a focused regression that checks bounded lanes, item-ID evidence,
  record-only activation readiness, and harness-eval separation.
- Documented the operator replay rule for this source digest.

## Validation

Planned command:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T160434`

Self-model decision: left unchanged. The existing self-model already prefers
rollback-backed local behavior improvements over validation-report-only work,
and this run's gap was in the pass-4 routing surface rather than the
self-description.
