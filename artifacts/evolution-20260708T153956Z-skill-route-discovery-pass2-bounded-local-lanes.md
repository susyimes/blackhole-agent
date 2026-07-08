# Evolution Run: Skill Route Discovery Pass 2

- Source digest: `github-growth-20260708T153850.626636Z`
- Branch: `codex/blackhole-evolve/20260708T153956.187633-add-or-extend-local-tests-for-skill-route-discov`
- Rollback ref: `refs/blackhole/rollback/20260708T153956Z-skill-route-discovery-pass2-bounded-local-lanes`
- Rollback artifact: `artifacts/rollback/20260708T153956Z-skill-route-discovery-pass2-bounded-local-lanes/rollback-point.md`

## Evidence Reviewed

- `https://github.com/Pluviobyte/rnskill`: public SKILL.md-compatible agent skill collection with skills, docs, tools, and marketplace metadata.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent reverse-flow skill workflow with local sandbox/CTF framing and diagnostic workflow pressure.
- `https://github.com/shepherd-agents/shepherd`: public general-agent runtime substrate evidence, not a skill package.

The evidence supports a bounded local lane rather than activation. Reverse-flow style evidence should route through `skill_route_discovery_first`; rnskill-style collection evidence should stay documentation-first; Shepherd and media workflow-usecase evidence should remain behind `agent_harness_eval_required`.

## Change

- Added `skill_route_discovery_current_digest_20260708T153850_pass2_validation_lane` for the active pass-2 window.
- Added a regression fixture that routes reverse-flow and rnskill into bounded documentation/config/test/code_patch lanes while holding Shepherd and media workflow-usecase evidence behind local agent-harness evaluation.
- Documented the new pass-2 lane and replay command.
- Left `docs/self-model.md` unchanged because its current preference already matches this run: rollback-backed local evolution with bounded validation and no activation from public trend evidence.

## Validation

- `python -m pytest tests/test_skill_routing.py -q`
- Result: `424 passed in 2.38s`

## Review Notes

- Runtime action remains `none`.
- Raw source URLs, evidence URLs, replay commands, target paths, and upstream bodies are not exported from the new lane.
- External skill activation, external harness execution, provider launch, remote execution, promotion, push, and restart remain disabled.
