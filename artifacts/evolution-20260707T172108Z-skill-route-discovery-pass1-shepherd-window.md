# Skill Route Discovery Pass 1 - Shepherd Window

- source_digest: `github-growth-20260707T172109.646188Z`
- rollback_ref: `refs/rollback/20260707T172108Z-skill-route-discovery-pass1`
- rollback_artifact: `artifacts/rollback/20260707T172108Z-skill-route-discovery-pass1/rollback-point.md`
- self_model_changed: false

## Evidence Reviewed

- `https://github.com/shepherd-agents/shepherd`: reversible, inspectable agent traces, retained outputs, replay, permissions, and external selection/apply/discard workflow.
- `https://github.com/shepherd-agents/shepherd/pull/35`: maintainer release-gate discipline through formatting parity before tag cut.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill package with local sandbox framing, staged reverse-analysis workflow, scripts, and install/run pressure.
- `https://github.com/Pluviobyte/rnskill`: generic `SKILL.md` collection for Codex/Claude workflows with skills directory, docs, tools, and marketplace/manual install metadata.

## Hypothesis

This wake should not import or run any upstream skill or harness. The useful local improvement is to make the current pass-1 route split replayable: reverse-flow goes to the bounded local test lane, rnskill goes to the bounded documentation lane, and Shepherd-style workflow evidence is held as an agent-harness prerequisite with a visible runner control plane.

## Local Change

- Specialized `current_run_pass1_activation_readiness` for `github-growth-20260707T172109.646188Z`.
- Added a regression that builds a body-free registry from the current window evidence and verifies bounded lanes, Shepherd `agent_harness_eval_required` routing, the five runner stages, and no raw URL/replay/runtime/install leakage in controller output.
- Documented the replay surface in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T172109` passed.

## Review Notes

- The self-model was left unchanged because it already prefers rollback-backed local validation over ornamental self-description edits.
- Shepherd remains evidence for a bounded local harness lane only; no upstream activation, provider launch, external harness execution, remote execution, restart, promotion, or rollback execution was performed.
