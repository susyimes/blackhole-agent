# Skill Route Discovery Pass 2 Validation Lane

Source digest: `github-growth-20260703T143923.402501Z`
Capability slice: `skill-route-discovery`
Pass: 2 of 4

## Evidence Reviewed

- `https://github.com/Kylin2021/reverse-flow-skill`
- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/poker117/reverse-flow-skill`
- `https://github.com/lyra81604/zhengxi-views`

The reverse-flow repositories expose public AI Agent/Codex skill workflow
packaging, `skills/reverse-flow/SKILL.md`, scripts, local sandbox/CTF framing,
and install/runtime wording. The zhengxi-views repository exposes public Agent
Skill packaging with source-cited workflow and advice-boundary metadata.

## Hypothesis

Pass 2 should convert this evidence into a bounded operator-visible local
validation lane before activation. Reverse-flow fork pressure should select the
test lane and preserve `skill_route_discovery_first`; zhengxi-views should
select documentation; general agent projects without skill workflow signals
should remain behind `agent_harness_eval_required`.

## Change

- Added digest-specific pass-2 routing for
  `github-growth-20260703T143923.402501Z`.
- Added a frozen body-free fixture for the current digest.
- Added a regression test for bounded lanes, unsupported-lane downgrades,
  local validation requirements, and adjacent agent-harness gating.
- Updated `docs/skill-route-discovery.md` with the operator-visible decision
  path and replay command.

## Rollback

Rollback point:
`artifacts/rollback/20260703T143921Z-skill-route-discovery-pass2/rollback-point.json`

Rollback ref:
`refs/blackhole/rollback/20260703T143921Z-skill-route-discovery-pass2`

## Validation

Passed:

- `python -m pytest tests/test_skill_routing.py -q -k 20260703T143923`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m compileall -q src/blackhole_agent/skill_routing.py`

No restart, promotion, push, provider launch, external harness execution, or
remote execution is performed by this kernel run.
