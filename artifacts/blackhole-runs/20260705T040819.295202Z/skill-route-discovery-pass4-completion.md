# Skill Route Discovery Pass 4

Source digest: `github-growth-20260705T040819.295202Z`
Branch: `codex/blackhole-evolve/20260705T041118.865142-add-or-extend-local-skill-route-discovery-valida`
Rollback ref: `refs/blackhole-rollback/20260705T041118.865142`
Rollback artifact: `artifacts/blackhole-runs/20260705T040819.295202Z/rollback.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex-oriented reverse-flow skill workflow evidence with install/runtime pressure that remains diagnostic.
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: generic agent-plus-skills workflow evidence suitable for bounded local route normalization.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent project, routed to agent harness evaluation before implementation lanes.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous-agent project, routed to agent harness evaluation before implementation lanes.

## Hypothesis

The final pass should expose an operator-visible `current_digest_pass4_completion_handoff`
for the current digest. Codex skill workflow evidence should remain
`skill_route_discovery_first`, generic agent-plus-skills evidence should route
through bounded documentation/config/test/code_patch lanes, and general-agent
projects should stay behind `agent_harness_eval_required`.

## Changes

- Added `current_digest_20260705T040819_pass4_completion.json` as a frozen current digest fixture.
- Wired `github-growth-20260705T040819.295202Z` into the specialized pass-4 completion handoff path.
- Added a regression proving:
  - `reverse-flow-skill` maps to `p1-skill-route-discovery-codex-workflow` in the local test lane and preserves `skill_route_discovery_first`.
  - `bionemo-agent-toolkit` maps to `p2-generic-skill-workflow-routing` in the bounded local code_patch lane.
  - Qwen-AgentWorld and Fundamental-Ava remain `agent_harness_eval_required`.
  - The handoff exports no raw GitHub URLs, replay commands, target paths, or upstream bodies.
- Updated `docs/skill-route-discovery.md` with the current pass-4 completion contract.

## Validation

- `python -m py_compile src\blackhole_agent\skill_routing.py`: passed.
- `python -m pytest tests\test_skill_routing.py -q -k 20260705T040819`: passed, 1 test.
- `python -m pytest tests\test_skill_routing.py -q -k "20260705T040819 or 20260704T184436 or 20260704T172435 or 20260704T144434"`: passed, 4 tests.
- `python -m pytest tests\test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 2 tests.
- `git diff --check`: passed; PowerShell reported expected LF-to-CRLF working-copy warnings.

## Review Notes

Self-model was read and left unchanged. It already matches this run's behavior:
prefer rollback-backed, locally validated behavior improvements while keeping
external activation, provider launch, remote execution, and private data export
denied.

No push, promotion, restart, provider launch, external harness execution, or
remote execution was performed. Activation remains a supervisor responsibility.
