# Skill Route Discovery Pass 1: Agent Harness Activation Review

Source digest: `github-growth-20260623T145349.094182Z`

## Evidence

- Primary evidence URL reviewed: `https://github.com/omnigent-ai/omnigent`
- Evidence lesson: Omnigent presents a meta-harness pattern with multi-agent orchestration, provider/runtime choices, policy and sandbox controls, and session supervision. Those are useful route-shape claims, but generic movement and repository-level evidence should be mapped to local controller invariants before local eval activation.
- Weak movement proposal handling: generic pull/push events remain supporting context only unless locally corroborated.

## Hypothesis

Future skill-route discovery passes need one operator-visible surface that says why an adjacent `agent_harness_eval_lane` is ready, blocked, or review-only before activation. A compact activation review panel should make mapped claims, unmapped claims, project-shape readiness, weak evidence, and safety review notes visible without enabling external harness execution.

## Local Change

- Added `activation_review` to `agent_harness_eval_lane` output.
- The review panel records bounded activation lane count, claim counts, project-intake probe status, weak/generic evidence review need, safety review note count, required validation, and explicit denials for runtime action, external agent activation, external harness execution, provider launch, remote execution, and raw body/source export.
- Updated focused tests for ready, unmapped-claim blocked, and weak-evidence blocked states.
- Documented the new operator-facing contract in `docs/skill-route-discovery.md`.

## Rollback

- Rollback ref: `refs/rollback/blackhole-evolve-20260623T145349`
- Rollback artifact: `artifacts/rollback/20260623T145349Z-skill-route-discovery-pass1.md`

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
  - Result: passed, `3 passed, 140 deselected`
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`
  - Result: passed, `22 passed, 9 deselected`

## Review Notes

- Self-model was read and left unchanged. It already describes the current narrow safety boundary and rollback-backed local evolution preference.
- No upstream code, install command, provider launch, external harness execution, or remote execution was used.
- The new panel does not change the existing activation gate outcome; it makes the gate's review inputs inspectable for the supervisor.
