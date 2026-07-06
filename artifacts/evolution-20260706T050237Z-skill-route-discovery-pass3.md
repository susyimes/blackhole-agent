# Evolution Run

- Source digest: `github-growth-20260706T050238.819252Z`
- Theme: `skill-route-discovery`
- Pass: 3 of 4
- Rollback: `artifacts/rollback/20260706T050237Z-skill-route-discovery-pass3-current-digest/rollback-point.md`

## Evidence

Focused review used the proposal URLs only. `lingbol088-spec/reverse-flow-skill`
shows a Codex/AI Agent skill package shape with `skills/reverse-flow`,
`SKILL.md`, references, scripts, local sandbox/CTF framing, install examples,
and run examples. That evidence supports classification and local validation
lanes, not import or execution.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` are treated as general agent project evidence.
Without a selected local harness result, they remain
`agent_harness_eval_required` and cannot open direct runtime or code patch
routes.

## Change

The current digest is now recognized by
`current_digest_pass3_route_to_validation_lane`. The lane exposes:

- `p1-skill-route-discovery-reverse-flow` in the local test lane.
- `p2-agent-harness-eval-for-general-agent-trends` as the harness-gated
  adjacent general-agent lane.
- `p3-route-hint-documentation-contract` in the documentation lane.

The packet keeps runtime action, external skill or agent activation, external
harness execution, provider launch, remote execution, profile writes, memory
writes, raw source URLs, raw replay commands, target paths, and upstream bodies
disabled.

## Self-Model

Read before choosing the change. No edit was made: the file already states that
public agent projects should become rollback-backed, locally validated
experiments inside the narrow safety boundary, and this run followed that
description. The file remains descriptive rather than a permission source.

## Validation

Passed:

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T050238`
- `python -m pytest tests/test_skill_routing.py -q -k "20260706T050238 or 20260706T034238"`
