# Evolution Run: skill-route-discovery pass 1

- Source digest: `github-growth-20260705T122958.181363Z`
- Branch: `codex/blackhole-evolve/20260705T123054.527367-run-a-bounded-skill-route-discovery-validation-f`
- Rollback artifact: `artifacts/rollback-20260705T122958Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260705T122958Z-skill-route-discovery-pass1`
- Self-model: read and left unchanged. It already supports rollback-backed, locally validated local evolution and this run did not add a new self-description rule.

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository exposes `skills/reverse-flow`, `SKILL.md`, references, scripts, local CTF/sandbox framing, staged reverse workflow, install examples, and vulnerability-analysis pressure. Interpreted only as bounded skill-route evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/InternScience/Agents-A1`: treated as adjacent general-agent project evidence requiring local `agent_harness_eval_required` before implementation lanes.

## Hypothesis

The active pass should expose a replayable pass-1 validation lane for the current digest. Reverse-flow skill evidence may map only to documentation, config, test, or code_patch lanes after focused local validation, while adjacent general-agent projects remain in harness evaluation with no direct runtime or code_patch route.

## Changes

- Added current digest `20260705T122958` handling to `current_digest_pass1_validation_lane`.
- Added frozen fixture `current_digest_20260705T122958_pass1_validation_lane.json`.
- Added regression coverage for allowed lanes, proposal IDs, adjacent harness rows, body-free serialization, and denied activation surfaces.
- Documented the current digest route surface in `docs/skill-route-discovery.md`.

## Validation

- `$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k 20260705T122958`: passed, 1 test.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`: passed.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q`: passed, 303 tests.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 2 tests.

## Review Notes

- No external skill activation, install, provider launch, harness execution, remote execution, profile write, memory write, raw URL export, replay-command export, or upstream-body export was added.
- The workflow-usecase proposal ID is represented as a documentation boundary. This pass had no separate workflow-usecase evidence URL, so it remains an operator-visible rule rather than a direct route candidate.
