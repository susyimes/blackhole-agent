# Run Notes

Source digest: `github-growth-20260627T230729.530583Z`
Branch: `codex/blackhole-evolve/20260627T230817.655800-add-or-extend-local-validation-for-generic-skill`
Rollback artifact: `artifacts/blackhole-runs/20260627T230848.608006Z/rollback.md`

## Evidence

Reviewed the carried proposal URLs only:

- `https://github.com/lyra81604/zhengxi-views`: public skill repository with `SKILL.md`, references, scripts, and evals; useful lesson is traceable, evidence-cited skill workflow validation, not upstream execution.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public skill package with director/sibling skills, browser checks, screenshot/canvas checks, mobile checks, QA, and credential boundaries; useful lesson is a game/frontend profile that still needs local validation lanes before activation.
- `https://github.com/dongshuyan/compass-skills`: public local-first skill ecosystem with task clarification, repo-local memory, handoff prompts, profile boundaries, redaction, and smoke validation; useful lesson is state-handoff metadata bounded to local config/docs/tests without memory/profile writes.
- `https://github.com/QwenLM/Qwen-AgentWorld`: adjacent general-agent benchmark/eval evidence; useful lesson is to route it to `agent_harness_eval_lane`, not inherit `skill_route_discovery`.

## Hypothesis

The existing pass-1 route matrix is useful for classification, but supervisors also need a compact activation-facing lane that says which active skill-route rows are ready for local replay and which adjacent agent-harness rows remain blocked. A derived `active_window_activation_candidate_lane` improves operator handoff without exporting raw evidence URLs or activating upstream code.

## Changes

- Added `active_window_activation_candidate_lane` to `skill_route_discovery_lane` output.
- Derived per-proposal activation status, supervisor replay step, blockers, selected bounded lanes, route profiles, selected item IDs, and source hashes from the existing active-window matrix.
- Kept runtime action, external skill activation, external harness execution, provider launch, remote execution, raw URL export, target path export, and upstream body export denied.
- Extended the active-window matrix test to assert the new activation candidate lane for three skill-route proposals plus one Qwen-style adjacent eval proposal.
- Documented the digest-specific behavior in `docs/skill-route-discovery.md`.

## Self-Model

Read `docs/self-model.md`. Left it unchanged because the file's current preference already matches this run: apply rollback-backed, locally validated behavior changes when they stay inside the safety boundary. No new evidence showed that the self-model needed to become more directive or less ornamental.

## Validation

- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_20260627_pass1_window_maps_profiles_to_bounded_lanes or skill_route_discovery_pass1_registry_handoff_gates_qwen_agentworld_as_adjacent_eval or skill_route_discovery_active_window_matrix_separates_skill_and_agent_lanes"`: passed, 3 passed.
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 10 passed.
- `ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py`: passed.

## Review Notes

The new lane is metadata-only and derived from existing validated matrix rows. It does not create a restart, push, promotion, provider call, external harness execution, memory write, profile write, install path, or remote execution path.
