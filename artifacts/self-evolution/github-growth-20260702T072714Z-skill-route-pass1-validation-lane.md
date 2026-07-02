# Skill Route Discovery Pass 1 Validation Lane

- Source digest: `github-growth-20260702T072714.841318Z`
- Rollback ref: `refs/blackhole-rollback/20260702T072713Z`
- Capability window: `skill-route-discovery`, pass 1 of 4

## Hypothesis

The current digest carries enough bounded evidence to open a new pass-1 local validation lane:
`zhengxi-views` and `bionemo-agent-toolkit` are skill-route candidates, while
`Qwen-AgentWorld` and `Fundamental-Ava` are adjacent general-agent projects that must stay behind
`agent_harness_eval_required` before implementation lanes are selected.

## Change

- Added a digest-specific pass-1 selector for `github-growth-20260702T072714.841318Z`.
- Added a frozen fixture for the current digest item shapes.
- Added a focused regression test proving:
  - skill-route rows map only to `documentation`, `config`, `test`, and `code_patch`;
  - the selected local lane is `test`;
  - general-agent rows do not inherit `skill_route_discovery`;
  - runtime, provider launch, external harness execution, remote execution, and external skill activation remain denied;
  - raw GitHub URLs and replay commands are not exported from the lane surface.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260702T072714`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest -q`

All validation passed.

## Review Notes

- No upstream code, prompts, packages, or skills were imported or activated.
- `docs/self-model.md` was read and left unchanged; it already describes the run's rollback-backed,
  locally validated evolution preference and narrow safety boundary.
