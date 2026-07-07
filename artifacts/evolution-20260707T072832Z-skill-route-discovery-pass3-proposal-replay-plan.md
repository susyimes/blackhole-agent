# Skill Route Discovery Pass 3 Proposal Replay Plan

Source digest: `github-growth-20260707T072834.240470Z`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex and AI Agent skill workflow repository with `skills/reverse-flow/SKILL.md`, references, scripts, local sandbox and CTF/crackme framing, plus install/run examples that are treated as route pressure only.
- `https://github.com/Pluviobyte/rnskill`: AI Agent Skills collection signal for generic skill workflow routing.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime substrate evidence, routed through agent-harness evaluation rather than skill-route discovery.

## Hypothesis

The current pass should expose the active proposal queue as an operator-visible replay plan. Skill workflow evidence can be converted into bounded documentation, config, test, or code_patch lanes, while general-agent project evidence stays behind `agent_harness_eval_required` and raw URL expansion stays denied.

## Change

- Added `skill_route_discovery_current_digest_20260707T072834_pass3_proposal_replay_plan`.
- Added frozen fixture `current_digest_20260707T072834_pass3_proposal_replay_plan.json`.
- Added regression coverage for the Codex workflow-gate lane, generic skill workflow lane, agent-harness eval queue, and no external URL expansion guard.
- Updated `docs/skill-route-discovery.md` with the pass-3 interpretation and replay command.

## Rollback

Rollback ref:
`refs/rollback/blackhole-agent/20260707T072832Z-skill-route-discovery-pass3`

Rollback artifact:
`artifacts/rollback/20260707T072832Z-skill-route-discovery-pass3-proposal-replay-plan/rollback-point.md`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260707T072834 or 20260707T060834 or 20260707T054834"`: passed, 3 tests selected.

## Review Notes

- Self-model left unchanged. It already describes the intended rollback-backed local evolution preference and narrow safety boundary for this run.
- No external skill code was installed, copied, or executed.
- General-agent repositories remain behind `agent_harness_eval_required`.
- Raw source URL and evidence URL expansion remains denied in the operator-visible lane.
