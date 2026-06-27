# Skill Route Discovery Pass 3 Preflight Queue

Source digest: `github-growth-20260627T134310.685675Z`
Branch: `codex/blackhole-evolve/20260627T134428.207400-add-a-bounded-local-skill-route-discovery-valida`
Rollback artifact: `artifacts/rollback/20260627T134310Z-skill-route-discovery-pass3.md`
Rollback ref: `refs/blackhole-rollback/20260627T134310Z-skill-route-discovery-pass3`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public repository exposes `SKILL.md`, `skill.yml`, references, scripts, evals, source-cited research behavior, and advisory boundary language.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public repository describes agent skills for Three.js browser games, gameplay/QA workflows, and optional generated asset boundaries.
- `https://github.com/dongshuyan/compass-skills`: public repository describes a personal alignment skills OS with task control, profile, memory, and handoff language.

## Hypothesis

Pass 3 already had route indexing and activation handoff surfaces, but operators still needed one compact preflight queue that combines required route-profile coverage, selected bounded local lanes, replay commands, and blocked proposal IDs before final-pass replay. The queue should stay body-free and should block summary-only evidence that lacks frozen selected item IDs.

## Local Change

- Added `pass3_preflight_queue` to the skill-route proposal lane map.
- The queue requires `source_cited_domain_research`, `game_frontend_workflow`, and `skill_ecosystem_state_handoff` coverage before final-pass replay.
- It reports selected local lanes, replay commands, proposal blockers, and candidate source hashes while denying runtime action, provider launch, remote execution, external activation, profile writes, memory writes, raw URL export, target path export, and upstream body export.
- Extended tests for summary-only blocked preflight and frozen pass-3 fixture ready preflight.
- Documented the new operator surface in `docs/skill-route-discovery.md`.

## Validation Result

- `python -m pytest tests/test_skill_routing.py -q -k "pass3_route_discovery_index or current_pass_validation_cases"`: passed, 2 passed and 42 deselected.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 passed and 9 deselected.
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`: passed, 35 passed and 9 deselected.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery`: passed, 46 passed and 110 deselected.

## Self-Model

Read `docs/self-model.md` and left it unchanged. The current text already supports rollback-backed local evolution with explicit uncertainty, which matches this run.

## Review Notes

No upstream code was installed, cloned, executed, or activated. No provider/runtime route, external harness execution, profile write, memory write, raw evidence URL export, raw source URL export, raw target path export, or upstream body import was added.

