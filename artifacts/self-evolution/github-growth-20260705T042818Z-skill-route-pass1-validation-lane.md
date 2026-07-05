# Self-Evolution Run: Skill Route Discovery Pass 1

Source digest: `github-growth-20260705T042818.506501Z`
Branch: `codex/blackhole-evolve/20260705T042905.185543-add-or-run-a-bounded-local-skill-route-discovery`
Rollback ref: `refs/rollback/20260705T042905Z-skill-route-discovery-pass1`
Rollback artifact: `artifacts/rollback/20260705T042905Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow shape with `skills/reverse-flow`, `SKILL.md`, install examples, scripts, local sandbox/CTF framing, and runtime pressure.
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: public agent-skills toolkit shape with skills CLI install examples, `SKILL.md` directory convention, plugin/catalog packaging, scripts, and references.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general-agent world-model/benchmark project with evaluation benchmark and setup instructions, not a local skill route.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: workflow-usecase repository with Blender/Seedance and agent-guided usecase framing, not a local skill route.

## Hypothesis

The current pass-1 route should recognize skill-bearing repositories as bounded
local lanes before activation, while keeping general agent and workflow-usecase
repositories in `agent_harness_eval_required` until local harness evidence
exists.

## Local Change

- Added a named `github-growth-20260705T042818.506501Z` pass-1 validation lane in `src/blackhole_agent/skill_routing.py`.
- Added a frozen fixture for reverse-flow, BioNeMo, Qwen-AgentWorld, Fundamental-Ava, and Seedance workflow-usecase evidence.
- Added a regression test proving:
  - reverse-flow selects the local `test` lane and requires `skill_route_discovery_first`;
  - BioNeMo selects the bounded `code_patch` lane as generic skill workflow evidence;
  - Qwen-AgentWorld, Fundamental-Ava, and Seedance workflow-usecases remain `agent_harness_eval_required`;
  - install, runtime execution, provider launch, external harness execution, remote execution, raw URLs, raw commands, and upstream bodies are not exported or enabled.
- Updated `docs/skill-route-discovery.md` with the replayable pass-1 lane.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260705T042818`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`

## Review Notes

- No upstream repository was cloned, installed, executed, or activated.
- No provider runtime, external harness, remote execution, profile write, or memory write was enabled.
- The self-model was read and left unchanged. Its current preference for rollback-backed local evolution is consistent with this run, but the concrete behavior belongs in tests, docs, and controller surfaces rather than in the self-model.
