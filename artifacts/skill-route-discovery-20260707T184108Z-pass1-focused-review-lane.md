# Skill Route Discovery Pass 1 Focused Review Lane

- Run: `20260707T184108Z`
- Source digest: `github-growth-20260707T184110.074943Z`
- Theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260707T184146.169587-run-a-bounded-skill-route-discovery-validation-f`
- Rollback point: `artifacts/rollback/20260707T184108Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/Pluviobyte/rnskill`
- `https://github.com/InternScience/Agents-A1`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/shepherd-agents/shepherd`

The reusable lesson is a mixed route boundary: Codex/skill workflow repositories should enter bounded local
`skill_route_discovery` lanes, while broad agent runtime or benchmark projects should remain in
`agent_harness_eval_required` until a local harness fixture exists.

## Hypothesis

If the active digest is represented as an operator-visible pass-1 focused review lane, the supervisor can replay the
current route decision without installing upstream skills, launching providers, executing external harnesses, or relying
on raw upstream URLs.

## Local Change

- Added `github-growth-20260707T184110.074943Z` to `current_pass1_focused_review_lane`.
- Bound current proposal IDs:
  - `p1-skill-route-discovery-reverse-flow`
  - `p2-skill-route-discovery-rnskill`
  - `p3-agent-harness-eval-general-projects`
  - `p4-route-classification-docs`
  - `trend:shepherd-agents/shepherd-1`
- Added a frozen fixture for reverse-flow, rnskill, Shepherd, Agents-A1, and Fundamental-Ava.
- Added regression coverage proving:
  - reverse-flow selects `test`;
  - rnskill selects `documentation`;
  - Shepherd, Agents-A1, and Fundamental-Ava remain behind `agent_harness_eval_required`;
  - runtime action, external activation, provider launch, remote execution, raw URLs, and raw replay commands stay disabled.
- Documented the new focused-review lane in `docs/architecture.md`.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. It already prefers rollback-backed local behavior changes over
ornamental report-only work, and this run produced a directly replayable behavior path.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T184110`
  - Passed: `1 passed, 389 deselected`
- `python -m pytest tests/test_skill_routing.py -q -k "validation_route_packet or 20260707T184110"`
  - Passed: `2 passed, 388 deselected`
- `python -m pytest tests/test_docs_contracts.py -q`
  - Passed: `20 passed`
- `python -m pytest tests/test_skill_routing.py -q`
  - Passed: `390 passed`

## Review Notes

- No external code was cloned, installed, executed, or activated.
- Reverse-flow contains reverse-engineering workflow and script pressure, so this run kept it in local route validation
  only.
- General-agent projects were not treated as skill repositories and received no direct implementation lane before local
  agent-harness evaluation.
