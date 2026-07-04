# Skill Route Discovery Pass 3 Route-To-Validation

- Source digest: `github-growth-20260704T033308.879043Z`
- Capability slice: `skill-route-discovery`
- Pass: 3 of 4
- Branch: `codex/blackhole-evolve/20260704T033401.529540-add-a-bounded-local-skill-route-discovery-valida`
- Rollback ref: `refs/blackhole-rollback/20260704T033401-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260704T033401Z-skill-route-discovery-pass3/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/ptrhamon/reverse-flow-skill`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`

The reverse-flow repositories expose a Codex/AI Agent skill package shape with
`skills/reverse-flow/SKILL.md`, references, scripts, and local sandbox/CTF
workflow framing. The reusable local lesson is not to activate the skill, but
to classify it into bounded local validation lanes and preserve unsupported
install/runtime pressure as diagnostics.

## Local Change

- Added digest-specific pass-3 routing for `github-growth-20260704T033308.879043Z`.
- Added a frozen fixture for reverse-flow, zhengxi-views, workflow-only, and general-agent evidence.
- Added a regression proving:
  - reverse-flow skill evidence maps only to documentation, config, test, or code_patch;
  - `p1_reverse_flow_skill_route_discovery` selects the local test lane and keeps `skill_route_discovery_first`;
  - unsupported reverse-flow install/runtime pressure is downgraded to diagnostics, not allowed lanes;
  - general-agent and workflow-only projects remain `agent_harness_eval_required` with no direct lanes before local harness evaluation.
- Updated `docs/skill-route-discovery.md` with the current pass interpretation and replay command.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. Its current preference already matches this run: direct local behavior improvements are acceptable when rollback-backed and locally validated, while runtime activation remains outside the skill-route evidence lane.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260704T033308`
  - Result: passed, `1 passed, 242 deselected`
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: passed, `243 passed`
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: passed, `11 passed`

## Review Notes

- No external skill activation, provider launch, remote execution, restart, push, or promotion was performed.
- The new unsupported-pressure diagnostic propagation is scoped to this digest so older frozen replay contracts stay stable.
