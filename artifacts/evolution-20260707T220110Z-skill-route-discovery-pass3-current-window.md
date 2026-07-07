# Evolution Artifact: Skill Route Discovery Pass 3 Current Window

- Source digest: `github-growth-20260707T220110.405293Z`
- Capability slice: `skill-route-discovery`
- Rollback ref: `refs/blackhole/rollback/20260707T220110Z-skill-route-discovery-pass3-current-window`
- Rollback artifact: `artifacts/rollback/20260707T220110Z-skill-route-discovery-pass3-current-window/rollback-point.md`
- Self-model: read and left unchanged

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill repository with `skills/reverse-flow`, `SKILL.md`, local sandbox framing, staged workflow, and diagnostic scripts.
- `https://github.com/Pluviobyte/rnskill`: public AI Agent Skills collection with skill directory and install/enable pressure that remains route evidence only.
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: public domain-specific agent toolkit described as BioNeMo skills, requiring local citation, data, advice, and provider boundary validation before activation.
- `https://github.com/InternScience/Agents-A1`: public general-agent project evidence without a selected skill workflow route, held behind local agent-harness evaluation.

## Hypothesis

The current pass-3 window should produce an operator-visible validation lane that converts skill-oriented repository evidence into bounded local documentation/config/test/code_patch lanes while keeping general-agent project evidence in `agent_harness_eval_required` before any runtime or workflow change.

## Changes

- Added current digest fixture `tests/fixtures/skill_route_discovery/current_digest_20260707T220110_pass3_current_window.json`.
- Extended `skill_route_discovery_current_pass3_proposal_lane` for `github-growth-20260707T220110.405293Z`.
- Added regression coverage for reverse-flow, rnskill, BioNeMo, and Agents-A1 route rows.
- Documented the pass-3 operator lane and replay command in `docs/skill-route-discovery.md`.

## Validation

- Passed: `python -m pytest tests/test_skill_routing.py -q -k 20260707T220110`

## Review Notes

- No upstream code was installed, cloned, run, or activated.
- Raw source URLs and upstream bodies are not exported by the lane output.
- `docs/self-model.md` was not changed because the existing text already supports rollback-backed local behavior changes and was not the bottleneck for this pass.
- Promotion, push, restart, provider launch, external harness execution, and remote execution were not performed.
