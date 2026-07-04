# Skill Route Discovery Pass 3

- Source digest: `github-growth-20260704T004924.800316Z`
- Branch: `codex/blackhole-evolve/20260704T005025.449430-create-or-extend-a-local-skill-route-discovery-v`
- Rollback ref: `refs/rollback/20260704T004923Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260704T004923Z-skill-route-discovery-pass3/rollback-point.json`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow with local sandbox/CTF reverse-analysis framing, scripts, and install/runtime pressure.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill workflow with source-cited research and advice-boundary language.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent benchmark/world-model evidence, useful only as a local harness-eval candidate before any implementation lane.

## Hypothesis

The active pass-3 window should expose an operator-visible route-to-validation
surface, not adopt external behavior. Reverse-flow-style Codex skill workflow
evidence should select a local test lane and prove `skill_route_discovery_first`.
Generic/source-cited skill workflow evidence should route to documentation.
General-agent or workflow-only trend evidence should stay behind
`agent_harness_eval_required` until local harness evaluation exists.

## Local Change

- Added a current-digest pass-3 branch in `src/blackhole_agent/skill_routing.py`.
- Added frozen fixture `tests/fixtures/skill_route_discovery/current_digest_20260704T004924_pass3_route_to_validation.json`.
- Added regression coverage in `tests/test_skill_routing.py`.
- Updated `docs/skill-route-discovery.md` with the pass-3 route interpretation.

## Validation

Focused replay passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704_pass3
```

Result: `1 passed, 235 deselected`.

Current-window replay passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704
```

Result: `3 passed, 233 deselected`.

## Review Notes

- Self-model was read and left unchanged. Its current preference already covers rollback-backed local experiments with offensive behavior and privacy leakage remaining review-only.
- Runtime action, external skill activation, external agent activation, external harness execution, provider launch, remote execution, profile writes, memory writes, raw source URL export, raw replay command export, target path export, and upstream body export remain denied in the pass-3 surface.
