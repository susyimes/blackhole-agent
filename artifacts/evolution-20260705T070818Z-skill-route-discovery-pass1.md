# Evolution Run: skill-route-discovery pass 1

- Source digest: `github-growth-20260705T070818.682441Z`
- Branch: `codex/blackhole-evolve/20260705T070908.118958-add-or-run-a-bounded-local-skill-route-discovery`
- Rollback ref: `refs/rollback/20260705T070816Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260705T070816Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Agent/Codex skill workflow with `skills/reverse-flow`, `SKILL.md`, local CTF/sandbox framing, install examples, and scripts.
- `https://github.com/InternScience/Agents-A1`: general agent project with docs/evaluation/scripts shape, but no explicit skill-route hint in the reviewed surface.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent/world-model project with eval and prompt folders, but no explicit skill-route hint in the reviewed surface.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: autonomous-agent project with source, benchmarks, experiments, and tests, but no explicit skill-route hint in the reviewed surface.

## Hypothesis

The active window should expose a replayable local lane for the reverse-flow skill signal while keeping general agent projects in `agent_harness_eval_required`. This converts the public signal into bounded local documentation/test/code paths without importing, installing, or executing upstream repositories.

## Changes

- Added current digest recognition for `github-growth-20260705T070818.682441Z` in the pass-1 skill-route lane builder.
- Added a frozen current-digest fixture for reverse-flow plus Agents-A1, Qwen-AgentWorld, and Fundamental-Ava.
- Added a regression test that asserts bounded local lanes, `skill_route_discovery_first`, no runtime/external activation, and adjacent general-agent harness-eval gating.
- Documented the operator-visible replay route in `docs/skill-route-discovery.md`.

## Validation

- `pytest tests/test_skill_routing.py -q -k 20260705T070818` -> passed, 1 passed.
- `pytest tests/test_skill_routing.py -q` -> passed, 288 passed.
- `pytest tests/test_docs_contracts.py -q` -> passed, 11 passed.
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or agent_harness_eval_lane"` -> passed, 14 passed.

## Review Notes

- Self-model was read and left unchanged. Its current preference already supports rollback-backed, locally validated route experiments and does not need another ornamental revision.
- No external code was imported, cloned, installed, or executed.
- Raw upstream bodies, raw source URLs, replay commands, provider launch, external harness execution, external skill/agent activation, and remote execution remain denied in the lane output.
