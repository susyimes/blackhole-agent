# Blackhole Run: skill-route-discovery pass 2 fixture acceptance

- Source digest: `github-growth-20260707T230110.418986Z`
- Branch: `codex/blackhole-evolve/20260707T230155.051454-create-or-extend-a-local-skill-route-discovery-v`
- Starting HEAD: `1e7c9da78bc710fa4317dd8ecef81e0f01cd80ec`
- Rollback ref: `refs/rollback/blackhole-agent/20260707T230108-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260707T230108Z-skill-route-discovery-pass2.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/agent skill repository with `skills/reverse-flow`, workflow language, scripts, install examples, and local sandbox framing.
- `https://github.com/Pluviobyte/rnskill`: SKILL.md-compatible skill collection with skills, docs, tools, marketplace/install paths.
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: domain skill toolkit with structured instructions, scripts, references, workflows, and license/data-source boundary notes.
- `https://github.com/InternScience/Agents-A1`: general agentic model/evaluation project with serving examples and benchmark claims rather than a local skill route.

## Hypothesis

Pass-2 skill-route discovery should expose whether adjacent general-agent evidence has the minimum local harness fixture fields before any behavior, controller, provider, or runtime route can proceed. This should be visible in the pass-2 handoff while remaining body-free and non-activating.

## Changes

- Added `fixture_acceptance_summary` to `skill_route_discovery_pass2_secondary_harness_checklist`.
- Mirrored that summary in `pass2_handoff_packet.secondary_harness_fixture_acceptance_summary`.
- Preserved sanitized local harness fixture presence metadata from adjacent general-agent evidence; raw fixture paths and rollback paths are not exported.
- Added a current-digest fixture for `github-growth-20260707T230110.418986Z` covering reverse-flow, BioNeMo, rnskill, Agents-A1, and Shepherd-style evidence.
- Added a targeted regression plus aggregate fixture-count updates.
- Documented the new pass-2 fixture acceptance summary in `docs/architecture.md`.

## Validation

```bash
$env:PYTHONPATH='src'; python -m pytest tests/test_harness_eval.py::test_skill_route_discovery_current_digest_20260707T230110_pass2_fixture_acceptance_summary -q
# 1 passed in 2.18s

$env:PYTHONPATH='src'; python -m pytest tests/test_harness_eval.py::test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs -q
# 1 passed in 1.17s

$env:PYTHONPATH='src'; python -m pytest tests/test_harness_eval.py::test_skill_route_discovery_pass2_secondary_harness_checklist_gates_adjacent_agent_projects -q
# 1 passed in 0.09s
```

## Review Notes

- `pass2_handoff_packet.status` remains `blocked` for the new `20260707T230110` fixture because the digest does not yet have a ready profile replay queue. The new behavior is the inspectable secondary harness fixture acceptance gate, not activation.
- A broad serialized-output substring assertion for `runtime_execution` was intentionally avoided because the evaluator can retain downgraded suggested-lane terms while explicit runtime, provider, remote, and external harness permission fields remain false.
- `docs/self-model.md` was left unchanged: its current preference for rollback-backed local evolution and narrow safety boundaries matches this run, and no new behavior-shaping self-description was needed.
