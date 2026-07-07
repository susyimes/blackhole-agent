# Evolution: Skill Route Discovery Pass 2 Current Run

Source digest: `github-growth-20260707T100834.719723Z`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository presents a Codex/AI Agent skill with `skills/reverse-flow`, local sandbox/CTF defaults, scripts, install pressure, and workflow steps.
- `https://github.com/Pluviobyte/rnskill`: public repository describes an AI Agent Skills collection with Python/Shell project shape.
- `https://github.com/shepherd-agents/shepherd`: public repository describes a reversible execution trace runtime substrate for agent supervision and replay, not an explicit skill workflow.

## Hypothesis

The current-run pass-2 surface should bind this wake's route-family evidence directly:
reverse-flow and rnskill should become bounded local skill-route validation rows, while
Shepherd should remain an adjacent `agent_harness_eval_required` row before any
runtime or implementation behavior is adopted.

## Change

- Updated `current_run_pass2_local_validation_lane` to use the active proposal IDs:
  `p1-skill-route-discovery-reverse-flow`, `p2-skill-route-discovery-rnskill`, and
  `p3-agent-harness-eval-shepherd`.
- Added candidate-name scoping so the generic rnskill profile cannot satisfy the
  reverse-flow Codex workflow-gate row.
- Added explicit `skill_route_discovery_first` proof metadata to skill rows so the
  nested activation contract can verify ordering before activation.
- Replaced the current-run fixture with the active digest evidence and updated the
  focused regression and documentation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_run_pass2_local_validation_lane`
  - Passed: 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "current_run_pass2_local_validation_lane or 20260707T084834_pass2 or 20260707T054834_pass2 or 20260707T090834"`
  - Passed: 4 tests.
- `python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
  - Passed: 8 tests.

## Review Notes

- No external skill code was cloned, installed, imported, enabled, or executed.
- Raw source URLs and replay commands remain omitted from the controller output.
- Self-model was read and left unchanged; its existing preference for rollback-backed,
  locally validated behavior already matched this run.
