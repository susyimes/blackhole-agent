# Skill Route Discovery Pass 2: Agent Harness Promotion Gate

Source digest: `github-growth-20260707T030834.667753Z`

Rollback point:
`artifacts/rollback/20260707T030832Z-skill-route-discovery-pass2-agent-harness-eval/rollback-point.md`

## Hypothesis

General agent project trends should not move from trend evidence to local
behavior work until the agent harness lane exposes explicit pass/fail criteria,
per-project results, and bounded follow-up lanes. Skill workflow evidence stays
in `skill_route_discovery`; adjacent general-agent and workflow-topic evidence
uses `agent_harness_eval_lane`.

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: explicit skill
  workflow evidence for bounded skill-route lanes.
- `https://github.com/InternScience/Agents-A1`: general agent evaluation
  project evidence.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: autonomous/collaborative
  agent project evidence.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime and
  recovery workflow evidence.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`:
  workflow-topic evidence that still requires local harness evaluation before
  integration work.

## Change

- Added `implementation_readiness_contract.promotion_gate` to
  `agent_harness_eval_lane`.
- Added a current-window local harness fixture proving general-agent trend rows
  expose pass criteria, fail criteria, per-project result rows, bounded
  follow-up lanes, and disabled runtime/external execution before promotion.
- Updated architecture and skill-route-discovery docs for the route split.

## Validation

Passed:

```powershell
python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or 20260707T030834"
```

Result: 8 passed, 242 deselected.

## Review Notes

- No upstream code was cloned, installed, or executed.
- No provider, external harness, or remote execution path was activated.
- `docs/self-model.md` was left unchanged; its current preference already
  matches this run's behavior: use validation artifacts as gates for local
  evolution, not as the default final destination.
