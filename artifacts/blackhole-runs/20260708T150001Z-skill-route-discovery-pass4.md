# Skill Route Discovery Pass 4

- Source digest: `github-growth-20260708T145852.089110Z`
- Branch: `codex/blackhole-evolve/20260708T150001.620054-add-or-extend-local-tests-for-skill-route-discov`
- Rollback ref: `refs/blackhole/rollback/20260708T150001Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260708T150001Z-skill-route-discovery-pass4/rollback-point.md`

## Evidence

- `Pluviobyte/rnskill` presents a public `SKILL.md`-compatible skills collection with install pressure; local handling keeps it in the documentation lane.
- `lingbol088-spec/reverse-flow-skill` presents a Codex/AI Agent skill workflow with local sandbox and staged workflow signals; local handling keeps it in the test lane.
- `shepherd-agents/shepherd` presents runtime substrate and replay/fork claims; local handling keeps it behind `agent_harness_eval_required`.

## Change

- Added `skill_route_discovery_current_digest_20260708T145852_pass4_operator_handoff`.
- Added a frozen current-digest fixture and regression for pass-4 operator handoff behavior.
- Documented the pass-4 handoff in `docs/skill-route-discovery.md`.

## Safety And Activation

- Runtime action remains `none`.
- External skill activation, external harness execution, provider launch, remote execution, promotion, restart, and push remain disabled.
- Raw source URLs, evidence URLs, replay commands, target paths, and upstream bodies are not exported by the operator handoff.
- `docs/self-model.md` was left unchanged because it already states the relevant preference for rollback-backed, locally validated evolution and narrow safety boundaries.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260708T145852
python -m pytest tests/test_skill_routing.py -q -k "20260708T145852 or 20260708T143852 or 20260708T121852"
```
