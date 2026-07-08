# Evolution Report

- Source digest: `github-growth-20260708T104635.460026Z`
- Capability slice: `skill-route-discovery`, pass 2 of 4
- Rollback ref: `refs/blackhole/rollback/20260708T104633Z-skill-route-discovery-pass2-bounded-local-lanes`
- Self-model: unchanged

## Evidence

Focused public evidence review used the carried proposal URLs only:

- `lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill workflow evidence with local sandbox framing, staged workflow language, scripts, install examples, and reverse-engineering domain pressure.
- `Pluviobyte/rnskill`: generic AI Agent Skills collection evidence with SKILL.md-compatible workflow and install/activation pressure.
- `shepherd-agents/shepherd`: general agent runtime substrate evidence, kept outside skill-route inheritance until local harness evaluation.

## Hypothesis

Pass-2 skill-route discovery should expose an operator-visible checklist for the bounded local lanes before pass 3. The checklist should make the validation requirements explicit while preserving `runtime_action: none` and activation denials.

## Changes

- Added `operator_validation_checklist` to the current pass-2 skill-route validation lane.
- Added the current digest `github-growth-20260708T104635.460026Z` to the pass-2 route dispatcher.
- Added a frozen current-digest fixture for reverse-flow, rnskill, Shepherd, Hy3, and workflow-usecase evidence.
- Added regression coverage for the checklist, uncertainty recording, adjacent agent-harness queue, rollback ref, and activation denials.
- Updated `docs/skill-route-discovery.md` with the replay surface.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T104635`
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T090635 or 20260708T092635 or 20260708T104635"`
- `python -m pytest tests/test_skill_routing.py -q`

All validation passed.

## Review Notes

- The checklist is body-free and exports no raw source URLs, replay commands, target paths, evidence URLs, or upstream bodies.
- Generic rnskill-style evidence records `upstream_body_not_locally_inspected` uncertainty.
- Shepherd-style runtime-substrate evidence remains `agent_harness_eval_required` and opens no direct implementation lane before local evaluation.
