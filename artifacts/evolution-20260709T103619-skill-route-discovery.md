# Evolution Run: 20260709T103619 Skill Route Discovery

Source digest: github-growth-20260709T103527.169759Z

Branch: codex/blackhole-evolve/20260709T103619.464464-add-or-run-a-local-skill-route-discovery-validat

Rollback ref: refs/blackhole-agent/rollback/20260709T103619-skill-route-discovery

Rollback artifact: artifacts/rollback-20260709T103619-skill-route-discovery.md

## Hypothesis

The active skill-route-discovery pass should expose an operator-visible pass-2
validation lane for the current reverse-flow/rnskill evidence instead of only
relying on earlier digest lanes. External skill/workflow repositories should
map to bounded local lanes only, while unhinted agent or workflow repositories
remain behind agent harness evaluation.

## Evidence

- `trend:lingbol088-spec/reverse-flow-skill-1` is skill/workflow evidence for
  a local test lane.
- `trend:Pluviobyte/rnskill-1` is generic SKILL.md-compatible workflow evidence
  for a local documentation lane.
- `trend:Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases-1`,
  `trend:SmileLikeYe/agent-chief-1`, and `trend:Tencent-Hunyuan/Hy3-1` are
  adjacent general-agent/workflow/model evidence and require local
  `agent_harness_eval_required` before follow-up lanes.

## Changes

- Added `current_digest_20260709T103527_pass2_skill_route_validation_lane` to
  the skill-route proposal lane map.
- Added a regression fixture for the current pass-2 digest shapes.
- Documented the current pass-2 interpretation rule.
- Left `docs/self-model.md` unchanged because its existing rollback-backed
  local validation posture matches this run.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260709T103527`
  - Result: 1 passed, 463 deselected
- `python -m pytest tests/test_skill_routing.py -q -k "20260709T103527 or 20260709T101527"`
  - Result: 2 passed, 462 deselected
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: 32 passed

## Safety Notes

- No external skill install, enable, run, clone, provider launch, external
  harness execution, promotion, push, restart, or remote execution was added.
- Packet output exports item IDs, hashes, lane names, rollback metadata, and
  activation denials only.
- Raw source URLs, evidence URLs, replay commands, target paths, and upstream
  bodies remain disabled in the new packet.
