# Skill Route Discovery Pass 1 Validation Lane

Source digest: `github-growth-20260704T065309.891207Z`
Branch: `codex/blackhole-evolve/20260704T065409.415256-create-a-bounded-local-skill-route-discovery-val`
Rollback: `artifacts/rollback/20260704T065309Z-skill-route-discovery-pass1-current-window/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill repository with `skills/reverse-flow/SKILL.md`, local sandbox/CTF framing, scripts, and install/runtime examples.
- `lyra81604/zhengxi-views`: public Agent Skill repository with `SKILL.md`, `skill.yml`, references, evals, scripts, and source-citation/advice-boundary language.
- `QwenLM/Qwen-AgentWorld` and `TianhangZhuzth/Fundamental-Ava`: general agent projects without selected skill workflow route hints or local harness evaluation results.

## Hypothesis

The active pass-1 skill-route window should have a replayable local validation lane keyed to the current proposal IDs. Reverse-flow evidence should enter a bounded local test lane, generic skill workflow evidence should enter a documentation lane, and general agent projects should stay behind `agent_harness_eval_required` with no direct code_patch or runtime authority.

## Change

- Added `github-growth-20260704T065309.891207Z` handling to `current_digest_pass1_validation_lane`.
- Added a frozen body-free fixture for the active digest.
- Added a focused regression test for the current proposal IDs and lane boundaries.
- Documented the pass-1 validation path in `docs/skill-route-discovery.md`.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704T065309
python -m pytest tests/test_skill_routing.py -q -k "20260704T065309 or 20260704T061309"
python -m pytest tests/test_docs_contracts.py -q -k skill_route
```

## Review Notes

- No upstream code, skill body, script, provider, harness, or runtime path was imported or executed.
- The local lane exports proposal IDs, selected item IDs, route profiles, lane names, source hashes, and replay hashes only.
- The self-model was read and left unchanged; it already allows rollback-backed local evolution and adds no permission source.
