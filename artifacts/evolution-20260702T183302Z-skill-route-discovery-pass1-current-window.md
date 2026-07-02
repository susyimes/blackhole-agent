# Skill Route Discovery Pass 1 Current Window

- Source digest: `github-growth-20260702T183119.073308Z`
- Rollback artifact: `artifacts/rollback-20260702T183302Z-skill-route-discovery-pass1-current-window.md`
- Rollback ref: `refs/blackhole-agent/rollback/20260702T183302Z-skill-route-discovery-pass1-current-window`
- Evidence reviewed: `https://github.com/lyra81604/zhengxi-views`

## Hypothesis

The active pass needs an operator-visible pass-1 lane for the current digest, not another borrowed fixture alias.
`zhengxi-views` can enter `skill_route_discovery` only through bounded local lanes, while Qwen-AgentWorld,
Fundamental-Ava, and looper remain `agent_harness_eval_required`; a workflow-only repository remains in the same
agent-harness gate unless an explicit skill workflow signal is present.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. Its current preference for locally validated evolution already
matches this pass; the file remains descriptive rather than a permission source.

## Material Actions

- Added a digest-specific pass-1 controller lane for `github-growth-20260702T183119.073308Z`.
- Added frozen skill-route and local-harness fixtures for the current digest.
- Added direct unit coverage and updated local harness aggregate expectations.
- Created rollback ref and rollback artifact before source edits.

## Validation

- `pytest tests/test_skill_routing.py -q -k 20260702T183119`
- `pytest tests/test_harness_eval.py -q -k "20260702T183119 or local_harness_eval_runs_pass"`
- `pytest tests/test_skill_routing.py -q -k "20260702T183119 or 20260702T181118 or 20260702T175118"`
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest_20260702T183119 or local_harness_eval_runs_pass"`
- `pytest tests/test_skill_routing.py -q`
- `pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass`

All validation commands passed.

## Review Notes

- No external skill activation, provider runtime launch, external harness execution, profile write, memory write, or remote execution is enabled.
- Output surfaces keep raw source URLs, raw evidence URLs, raw replay commands, target paths, and upstream bodies unexported.
