# Skill Route Discovery Pass 1 Current Window

- Source digest: `github-growth-20260704T174435.250220Z`
- Capability theme: `skill-route-discovery`
- Rollback ref: `refs/blackhole-rollback/20260704T174433Z-skill-route-discovery-pass1-current-window`

## Evidence Reviewed

- `820101274/reverse-flow-skill` and `lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent reverse-flow skill workflow shape with `skills/reverse-flow`, local sandbox/CTF framing, scripts, and install/runtime pressure that must remain diagnostic.
- `lyra81604/zhengxi-views`: public Agent Skill shape with source-cited workflow and advice-boundary metadata.
- `QwenLM/Qwen-AgentWorld` and `TianhangZhuzth/Fundamental-Ava`: general-agent evidence, routed to local harness evaluation before any implementation lane.

## Local Change

This run adds a pass-1 current-digest validation lane for the active proposal IDs. Reverse-flow fork evidence is collapsed into one lineage candidate, generic skill workflow evidence routes through `skill_route_discovery`, and general-agent evidence remains under `agent_harness_eval_required`.

## Review Notes

- No upstream skill was installed, executed, cloned, or activated.
- No provider, external harness, remote execution, push, promotion, restart, profile write, or memory write was enabled.
- The self-model was read and left unchanged because it already describes rollback-backed local evolution and does not need a new ornamental statement for this route.

## Validation

Completed focused replay:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704T174435
```

Completed broader checks:

```powershell
python -m pytest tests/test_skill_routing.py -q
python -m pytest tests/test_docs_contracts.py -q
```
