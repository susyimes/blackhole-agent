# Skill Route Discovery Pass 3 Operator Validation Queue

Source digest: `github-growth-20260705T143637.069684Z`
Capability slice: `skill-route-discovery`
Pass: 3 of 4

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
  - Public repository exposes a `skills/reverse-flow` package shape, `SKILL.md`,
    references, scripts, local CTF/sandbox framing, staged reverse workflow,
    install examples, and vulnerability-analysis pressure.
  - Local interpretation: route evidence only; map to bounded local test lane
    before any activation.
- `https://github.com/QwenLM/Qwen-AgentWorld`
  - Public repository exposes benchmark/world-model/evaluation claims and an
    `eval` surface, but no local skill workflow route.
  - Local interpretation: keep in `agent_harness_eval_required`.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
  - Public repository exposes autonomous multi-agent simulation, memory,
    benchmarks, experiments, and tests, but no local skill workflow route.
  - Local interpretation: keep in `agent_harness_eval_required`.
- `InternScience/Agents-A1` remained adjacent window context from the digest.

No upstream code was installed or executed.

## Hypothesis

The current pass-3 slice should expose an operator-visible queue that binds
reverse-flow skill-route evidence to a bounded local validation lane while
keeping adjacent general-agent projects in agent-harness evaluation before any
runtime, provider, remote, or code_patch activation.

## Changes

- Added digest-specific handling for `github-growth-20260705T143637.069684Z` in
  `current_digest_pass3_route_to_validation_lane`.
- Added a frozen metadata fixture for the current digest.
- Added a regression test for the pass-3 operator validation queue.
- Documented the pass-3 handoff in `docs/skill-route-discovery.md`.
- Created rollback point:
  `refs/rollback/20260705T143635Z-skill-route-discovery-pass3`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260705T143637 or 20260705T141637_pass2 or current_digest_pass3_route_to_validation_lane"`
  - Result: `2 passed, 306 deselected`
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: `308 passed`

## Review Notes

- Self-model was read and left unchanged. Its current preference for
  rollback-backed local behavior changes over validation-report-only work is
  consistent with this run.
- The new packet remains body-free: raw upstream URLs, replay command bodies,
  target paths, and upstream bodies are not exported from the operator surface.
- Runtime action, external skill activation, external harness execution,
  provider launch, and remote execution remain denied.
