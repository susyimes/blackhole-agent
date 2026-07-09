# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260709T003850.757195Z`
- Capability slice: `skill-route-discovery`
- Rollback ref: `refs/blackhole-rollback/20260709T003936Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260709T003936Z-skill-route-discovery-pass1.md`
- Self-model decision: unchanged; the existing note already favors rollback-backed local validation over ornamental reports.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill repository with `skills/reverse-flow` and workflow-gate signals.
- `https://github.com/Pluviobyte/rnskill`: public AI Agent Skills collection for Codex, Claude Code, and SKILL.md-compatible workflows.
- `https://github.com/eli-labz/Cognitive-Core-Skills`: public cognitive skills taxonomy with schemas, skill cards, benchmarks, and CI.

## Hypothesis

Mixed skill and benchmark evidence should stay in `skill_route_discovery_first`.
Benchmark wording can be recorded as a secondary validation hint only after local
skill-route validation, not as a direct `agent_harness_eval` or implementation
lane.

## Local Change

- Added secondary benchmark-hint metadata for skill repository candidates.
- Extended the active `20260709T003850` pass-1 focused review lane.
- Added a fixture-driven regression for reverse-flow, rnskill, and Cognitive-Core-Skills.
- Documented the local validation path for the active digest.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260709T003850` passed.
- `python -m pytest tests/test_skill_routing.py -q` passed.
- `python -m pytest tests/test_docs_contracts.py -q` passed.

## Review Notes

- No upstream code was cloned, installed, enabled, or run.
- No promotion, push, restart, provider launch, external harness execution, remote execution, profile write, or memory write was performed.
- Raw source URLs remain evidence inputs and are not exported in route packets.
