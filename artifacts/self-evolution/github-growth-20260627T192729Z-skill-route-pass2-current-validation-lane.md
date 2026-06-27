# Skill Route Discovery Pass 2 Current Validation Lane

- Source digest: `github-growth-20260627T192729.517144Z`
- Branch: `codex/blackhole-evolve/20260627T192820.276177-add-or-run-a-local-skill-route-discovery-validat`
- Rollback artifact: `artifacts/rollback/20260627T192729Z-skill-route-discovery-pass2-current-window.md`
- Rollback ref: `refs/blackhole-rollback/20260627T192729-skill-route-discovery-pass2`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public agent skill repository shape with `SKILL.md`, skill metadata, references, evals, scripts, source-citation claims, and advice-boundary language.
- `https://github.com/majidmanzarpour/threejs-game-skills`: browser-game skill package shape with `skills/`, scripts, Three.js/gameplay/QA language, scaffold helpers, and optional asset workflow pressure.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent benchmark/project evidence. Its benchmark material names evaluation dimensions such as format, factuality, consistency, realism, and quality, but it is not a skill workflow route.

## Hypothesis

The current pass-2 slice should expose one operator-visible validation lane that keeps skill repositories in bounded local documentation/config/test/code_patch lanes while routing adjacent general-agent benchmark evidence to `agent_harness_eval_required` before it can influence runner, scheduling, memory, or controller behavior.

## Changes

- Added `current_pass2_validation_lane` to the skill-route proposal lane map.
- Added a fixture for generic skill workflow, game/frontend skill workflow, and Qwen-style adjacent general-agent evidence.
- Added regression coverage that verifies selected item IDs, validation gates, bounded lanes, no runtime action, no external activation, and no raw GitHub URL export.
- Documented the new pass-2 lane and agent-harness boundary.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "current_pass2_validation_lane or current_pass2_focused_evidence_review or active_pass1_fixtures_queue_general_agent_evidence"`: passed
- `python -m pytest tests/test_skill_routing.py -q`: passed
- `python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`: passed
- `python -m pytest tests/test_docs_contracts.py -q`: passed

## Review Notes

- Self-model left unchanged. It already says validation reports are not the default destination, and this run added a behavior surface plus tests rather than revising that preference.
- No upstream skill code was imported, installed, executed, or enabled.
- Qwen-AgentWorld evidence remains adjacent to skill-route discovery and cannot grant runtime, controller, memory, provider, remote-execution, or external-harness authority without a separate local agent-harness evaluation.
