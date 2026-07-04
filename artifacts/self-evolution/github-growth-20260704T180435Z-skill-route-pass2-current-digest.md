# Skill Route Discovery Pass 2: Current Digest Validation Lane

- Source digest: `github-growth-20260704T180435.622778Z`
- Capability slice: `skill-route-discovery`
- Pass: 2 of 4
- Rollback ref: `refs/blackhole-rollback/20260704T180435-skill-route-pass2`
- Rollback artifact: `artifacts/rollback/20260704T180435Z-skill-route-discovery-pass2-current-digest/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/QwenLM/Qwen-AgentWorld`

The evidence was used only as public repository-level route context. No clone,
install, script execution, provider runtime, external harness execution, remote
execution, profile write, or memory write was performed.

## Hypothesis

The current pass-2 window should expose an operator-visible local validation
lane for the actual active proposals instead of falling back to older
compass/game skill-route expectations. `zhengxi-views` and
`reverse-flow-skill` can be validated as bounded skill-route rows, while
`Qwen-AgentWorld` remains adjacent `agent_harness_eval_required` evidence.

## Change

- Added a source-digest-specific `github-growth-20260704T180435.622778Z`
  branch in `current_digest_pass2_local_validation_lane`.
- Added a frozen current-digest fixture covering:
  - `p1-skill-route-zhengxi-views`
  - `p2-skill-route-reverse-flow`
  - `p3-agent-harness-qwen-agentworld`
- Added regression coverage proving:
  - skill-route rows select only bounded local lanes;
  - reverse-flow keeps `skill_route_discovery_first`;
  - upstream install/runtime/provider pressure is downgraded;
  - Qwen-AgentWorld does not inherit `skill_route_discovery`;
  - raw URLs, replay commands, target paths, and upstream bodies are not exported.
- Updated `docs/skill-route-discovery.md` with the pass-2 current-digest handoff.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260704T180435`
  - Result: passed, `1 passed, 278 deselected`
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: passed, `279 passed`

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. Its current preference for
rollback-backed local behavior improvements over validation-report-only work
already matches this run.

## Review Notes

- The external repositories remain evidence-only. Activation, provider launch,
  external harness execution, remote execution, profile writes, and memory writes
  stay denied.
- The local import environment can resolve to a sibling installed checkout during
  ad hoc `python` commands; pytest uses this worktree through `tests/conftest.py`
  and `pyproject.toml` `pythonpath`.
