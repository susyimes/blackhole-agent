# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260705T151637.013264Z`
- Branch: `codex/blackhole-evolve/20260705T151739.610463-add-or-run-a-bounded-agent-harness-evaluation-la`
- Rollback ref: `refs/blackhole-rollback/20260705T151739Z-skill-route-discovery-pass1-current-digest`
- Rollback artifact: `artifacts/rollback/20260705T151739Z-skill-route-discovery-pass1-current-digest/`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex / AI Agent skill workflow repository with `skills/reverse-flow`, `SKILL.md`, local sandbox/CTF framing, install examples, scripts, and vulnerability-analysis pressure.
- `https://github.com/InternScience/Agents-A1`: general agentic model / evaluation project with long-horizon trajectory and benchmark claims.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general language world model and AgentWorldBench evaluation project across agent interaction domains.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous agent simulation project with memory, collaboration, and population-level experiment claims.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: workflow-usecase repository with Blender/Seedance, MCP, skill install, and API-key setup pressure.

## Hypothesis

The current digest should open an operator-visible pass-1 validation lane: reverse-flow is bounded skill-route evidence, while general agent and workflow-usecase repositories stay behind `agent_harness_eval_required` until local harness validation proves a documentation, test, or code_patch follow-up is safe.

## Changes

- Registered `github-growth-20260705T151637.013264Z` in `current_digest_pass1_validation_lane`.
- Added a frozen current-digest fixture with one reverse-flow skill-route item, three general-agent project items, and one workflow-usecase item.
- Added a regression test asserting:
  - only documentation, config, test, and code_patch are allowed for skill-route discovery;
  - Agents-A1, Qwen-AgentWorld, and Fundamental-Ava cannot bypass `agent_harness_eval_required`;
  - Blender/Seedance workflow-usecase evidence remains harness-gated before tool, runner, provider, or workflow integration;
  - raw upstream URLs, replay commands, runtime execution, provider launch, external harness execution, and remote execution are not exported or enabled.
- Documented the pass-1 lane in `docs/skill-route-discovery.md`.

## Validation

- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k 20260705T151637`: passed.
- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k "20260705T151637 or 20260705T135637 or 20260705T122958"`: passed.

## Review Notes

- Self-model left unchanged. It already matches the local-validation-first behavior used in this run and did not need a new behavioral claim.
- No external skill installation, upstream script execution, provider launch, external harness execution, remote execution, profile write, or memory write was performed.
