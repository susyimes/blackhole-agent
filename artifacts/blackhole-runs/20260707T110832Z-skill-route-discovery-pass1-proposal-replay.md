# Skill Route Discovery Pass 1 Proposal Replay

- Run: `20260707T110832Z-skill-route-discovery-pass1`
- Source digest: `github-growth-20260707T110834.493888Z`
- Rollback ref: `refs/blackhole/rollback/20260707T110832Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260707T110832Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill layout, `skills/reverse-flow`, local sandbox/CTF framing, install and script examples.
- `https://github.com/Pluviobyte/rnskill`: AI Agent Skills collection with `skills`, `.claude-plugin`, `SKILL.md` support, Codex/Claude install examples, and manual project skill copy instructions.
- `https://github.com/shepherd-agents/shepherd`: adjacent general-agent runtime substrate evidence, retained as harness-eval pressure only.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: adjacent general-agent evidence, retained as harness-eval pressure only.

## Change

Added a frozen proposal replay fixture for the active pass-1 proposal IDs:

- `p1_reverse_flow_skill_route_discovery`
- `p2_rnskill_generic_skill_route_discovery`
- `p3_skill_route_discovery_docs`

The fixture accepts only selected `item_id` citations for reverse-flow and
rnskill, rejects a repository URL citation, rejects a `follow_up_issue` lane
escape, and verifies controller-owned proposal controls keep all accepted work
inside documentation or test lanes with `runtime_action` remaining `none`.

The local routing documentation now states the same item-id-only and bounded
lane rule, with a docs contract assertion for the current digest.

## Self-Model

`docs/self-model.md` was read before choosing the change and left unchanged.
It already states the relevant preference for rollback-backed local validation
outside the narrow safety boundary, so editing it would have been ornamental.

## Validation

- `python -m pytest tests/test_proposal_eval.py -q` -> passed, 34 tests.
- `python -m pytest tests/test_docs_contracts.py -q` -> passed, 16 tests.

## Review Notes

- No runtime activation, upstream skill installation, external harness
  execution, provider launch, remote execution, push, promotion, or restart was
  performed.
- External evidence was reviewed only at repository-summary level; this change
  validates local route interpretation, not upstream package safety.
