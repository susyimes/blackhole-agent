# Skill Route Discovery Pass 4 Workflow Boundary

- Source digest: `github-growth-20260705T161641.350480Z`
- Branch: `codex/blackhole-evolve/20260705T161757.599424-run-a-bounded-skill-route-discovery-validation-l`
- Rollback point: `artifacts/rollback/20260705T161639Z-skill-route-discovery-pass4/rollback-point.md`
- Local rollback ref: `refs/rollback/20260705T161639Z-skill-route-discovery-pass4`

## Evidence

- `lingbol088-spec/reverse-flow-skill` exposes a Codex/AI Agent skill package shape with `skills/reverse-flow`, `SKILL.md`, scripts, local sandbox/CTF framing, and workflow pressure.
- `Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` exposes workflow/usecase evidence without an explicit skill package or skill-route signal.

## Hypothesis

Workflow-only trend evidence should not collapse into an undifferentiated ignored item. It should be visible as `workflow_usecase_without_skill_route_signal`, routed to `agent_harness_eval_required`, and kept out of direct runtime, direct code patch, external harness, provider launch, and remote execution lanes until local harness evaluation exists.

## Changes

- Added reusable workflow-usecase classification in `src/blackhole_agent/skill_routing.py`.
- Threaded optional workflow route class/hint into adjacent agent-harness rows.
- Added a focused regression in `tests/test_skill_routing.py`.
- Documented the current pass boundary in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k workflow_usecases_to_agent_harness_eval` passed.
- `python -m pytest tests/test_skill_routing.py -q -k "workflow_usecase or active_proposals_are_bounded or active_pass1_fixtures_queue_general_agent_evidence"` passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260705T153637 or 20260705T145637 or 20260705T141637"` passed.
- `python -m pytest tests/test_harness_eval.py -q -k "20260705T102958 or current_digest_pass4_local_kernel_handoff"` passed.
- `python -m pytest tests/test_skill_routing.py -q` passed.

## Review Notes

- The self-model was read and left unchanged because it already supports rollback-backed local experiments while keeping runtime policy external.
- No external skill was installed, cloned, enabled, or executed.
- No provider, external harness, remote execution, profile write, or memory write path was activated.
