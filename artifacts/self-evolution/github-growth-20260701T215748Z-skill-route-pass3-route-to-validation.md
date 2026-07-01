# Skill Route Discovery Pass 3 Route-To-Validation

- Source digest: `github-growth-20260701T215748.459700Z`
- Capability slice: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260701T215838.588520-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/blackhole-rollback/20260701T215747Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/self-evolution/github-growth-20260701T215748Z-rollback.md`

## Focused Evidence Review

Reviewed only the carried proposal URLs:

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/ksimback/looper`

Observed lesson: zhengxi-views exposes a visible Agent Skill package shape
(`SKILL.md`, `skill.yml`, `references/`, `scripts/`, `evals/`) and source
citation / non-investment-advice boundaries. Qwen-AgentWorld, Fundamental-Ava,
and looper are general-agent project signals and should remain behind
`agent_harness_eval_required` before any follow-up implementation lane opens.

## Hypothesis

The current pass should be operator-visible as a route-to-validation surface:
skill-route evidence may enter bounded documentation/test lanes, while adjacent
general-agent repositories remain gated by local harness evaluation with no
runtime action.

## Local Changes

- Added `github-growth-20260701T215748.459700Z` handling to the pass-3
  activation review lane in `src/blackhole_agent/skill_routing.py`.
- Added a local harness fixture for the current digest:
  `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260701T215748_pass3_route_to_validation.json`.
- Added direct and aggregate assertions in `tests/test_harness_eval.py`.
- Updated `docs/skill-route-discovery.md` with the current digest route policy.
- Left `docs/self-model.md` unchanged because its current content is a broad
  preference note, not a route policy; this run's route behavior is encoded in
  tests, source, docs, and rollback artifacts instead.

## Validation

- `pytest tests/test_harness_eval.py -q -k "20260701T215748 or local_harness_eval_runs_pass"`:
  2 passed, 209 deselected.
- `pytest tests/test_proposal_eval.py -q -k "skill_route_discovery or agent_harness_eval_fixture"`:
  5 passed, 20 deselected.

## Review Notes

- No activation, provider launch, external harness execution, remote execution,
  raw source URL export, or upstream body export is enabled.
- The open-reverselab anchor is recorded as review context only because it is
  outside this pass's carried evidence URLs and touches the automation/bug
  safety boundary.
