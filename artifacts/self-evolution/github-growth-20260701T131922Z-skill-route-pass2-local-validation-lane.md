# Skill Route Discovery Pass 2 Local Validation Lane

- Source digest: `github-growth-20260701T131922.972375Z`
- Branch: `codex/blackhole-evolve/20260701T132032.221033-add-or-run-a-bounded-local-skill-route-discovery`
- Rollback artifact: `artifacts/rollback-20260701T132032Z-skill-route-discovery-pass2.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260701T132032Z-skill-route-discovery-pass2`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`
- Public metadata observed: repository is public, contains `SKILL.md`, `skill.yml`, `references/`, `evals/`, and `scripts/`.
- Reusable lesson: skill-shaped public trend evidence should become bounded local route lanes before activation, especially when it carries source-citation and advice-boundary claims.

## Hypothesis

The active pass-2 digest should expose an operator-visible route split:
`zhengxi-views` enters only documentation, config, test, or code_patch lanes,
while Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`agent_harness_eval_required` rows until a local harness result exists.

## Local Change

- Added a digest-specific pass-2 fixture for `github-growth-20260701T131922.972375Z`.
- Added controller routing for the active proposal IDs:
  `p1-skill-route-discovery-zhengxi-views`,
  `p2-agent-harness-eval-for-general-agent-trends`,
  `p3-agent-automation-bug-route`, and
  `p4-route-metadata-consistency-check`.
- Kept automation-and-bug evidence review-only at the offensive-behavior boundary.
- Updated `docs/skill-route-discovery.md` with the pass-2 interpretation.

## Validation

- `python -m py_compile src/blackhole_agent/skill_routing.py`
- `python -m pytest tests/test_skill_routing.py -q -k "20260701T131922 or current_digest_20260630T090714_pass2 or current_digest_20260630T074714_pass2"`
- `python -m pytest tests/test_skill_routing.py -q`

All validations passed.
