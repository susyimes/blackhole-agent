# Skill Route Discovery Pass 3

Source digest: `github-growth-20260624T095356.034961Z`
Capability window: `skill-route-discovery`, pass 3 of 4
Selected proposals: `P1`, `P2`, adjacent `P3`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`: public skill ecosystem with `skills/`, `SKILL.md`-style reusable workflows, scripts, and handoff/profile patterns.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill with `SKILL.md`, references, scripts, source-cited domain corpus, and explicit advice/citation boundaries.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public Codex/Claude skill workflow package with director routing, game workflow skills, QA/release checks, and packaged scripts.
- `https://github.com/omnigent-ai/omnigent`: broader agent framework/meta-harness evidence; useful for local harness evaluation, but not a skill-route candidate without concrete skill/workflow signals.

## Hypothesis

Pass-3 route discovery should give operators a compact handoff that joins the active skill-workflow evidence and adjacent general-agent evidence before activation. Skill repositories should stay inside documentation, config, test, or code_patch lanes with local validation required. General agent projects should remain `agent_harness_eval_required` and must not inherit `skill_route_discovery` because of generic agent, runtime, or meta-harness language.

## Change

- Added `skill_route_pass3_handoff` to `build_route_hint_lane_map`.
- Added a narrow negated-skill classifier rule so phrases such as `not skill discovery inheritance` do not create a skill-route signal unless the selected item also names a concrete skill artifact.
- Added focused proposal-eval tests for the current pass-3 evidence window and the negated-skill regression.
- Documented the new pass-3 handoff contract and classifier rule.
- Left `docs/self-model.md` unchanged; it already matches this run by preferring rollback-backed, locally validated behavior changes over report-only work.

## Rollback

- Artifact: `artifacts/rollback/20260624T095356Z-skill-route-discovery-pass3.md`
- Ref: `refs/rollback/blackhole-agent/20260624T095356Z-skill-route-discovery-pass3`

## Validation

- `PYTHONPATH=src python -m pytest tests/test_proposal_eval.py -q -k "pass3_skill_route_handoff or negated_skill_inheritance or route_hint_lane_map"`: passed, 3 tests.
- `PYTHONPATH=src python -m pytest tests/test_github_growth.py -q -k "general_agent_project_eval_lane or current_skill_route_window or mixed_skill_workflow or route_hint_lane_map"`: passed, 3 tests.
- `PYTHONPATH=src python -m pytest tests/test_proposal_eval.py -q -k "skill_route_discovery or route_hint_lane_map"`: passed, 6 tests.
- `PYTHONPATH=src python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.

## Review Notes

- No external code, packages, or scripts were installed or executed.
- The new controller surface exports selected item IDs and lane metadata only; it does not export raw source URLs or upstream bodies.
- The handoff grants no external skill activation, agent activation, harness execution, provider launch, remote execution, or runtime action.
