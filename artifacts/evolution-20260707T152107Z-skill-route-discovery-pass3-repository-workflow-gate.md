# Evolution: Skill Route Discovery Pass 3 Repository Workflow Gate

- Source digest: `github-growth-20260707T152109.445461Z`
- Capability slice: `skill-route-discovery`
- Rollback ref: `refs/blackhole/rollback/20260707T152107Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260707T152107Z-skill-route-discovery-pass3/rollback-point.md`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/Pluviobyte/rnskill`
- `https://github.com/InternScience/Agents-A1`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/shepherd-agents/shepherd`

I reviewed only the carried evidence URLs needed for this pass. The
reverse-flow repository is a Codex/AI Agent skill package with `skills/`
layout, `SKILL.md`, local sandbox/CTF framing, an activation phrase, staged
workflow language, and script examples. That supports a local validation
contract, not external installation or execution.

## Hypothesis

The reusable repository-lane probe should expose a bounded workflow-gate
contract for reverse-flow-style skill repositories before any Codex workflow
gate can be treated as locally valid. Generic skill repositories should remain
generic documentation/config/test/code_patch candidates, and general-agent
projects should remain behind `agent_harness_eval_required`.

## Change

- Added a body-free `workflow_gate_validation_contract` for
  `codex_workflow_gate` repository-lane rows.
- Required activation-phrase, local-sandbox, staged-workflow, and diagnostic
  script markers for that contract to be ready.
- Included the contract in repository-lane probe readiness.
- Added a pass-3 fixture for the current digest covering reverse-flow, rnskill,
  Agents-A1, Fundamental-Ava, and Shepherd.
- Updated `docs/skill-route-discovery.md` with the operator-visible replay
  path.

## Safety Boundary

No external skill activation, clone, install, execution, provider launch,
external harness execution, memory/profile write, remote execution, raw
activation phrase export, raw source URL export, or upstream body export is
enabled by this change.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "repository_lane_probe or 20260707T152109"`: passed, 2 passed, 380 deselected.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 382 passed.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 16 passed.
