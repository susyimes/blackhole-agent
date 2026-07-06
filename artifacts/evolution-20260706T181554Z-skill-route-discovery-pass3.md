# Evolution Run: skill-route-discovery pass 3 replay packet

- Source digest: `github-growth-20260706T181555.593867Z`
- Branch: `codex/blackhole-evolve/20260706T181647.444923-create-a-bounded-local-validation-lane-for-skill`
- Rollback ref: `refs/rollback/blackhole-agent/20260706T181554Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260706T181554Z-skill-route-discovery-pass3/rollback-point.md`
- Self-model: read and left unchanged. The file already supports rollback-backed, locally validated evolution and this run had stronger evidence for a route-surface improvement than for changing self-description text.

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: interpreted as skill/workflow route evidence only. Install, run, script, runtime, provider, and external-harness wording remains downgraded route pressure.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/shepherd-agents/shepherd`: interpreted as general-agent project evidence requiring local `agent_harness_eval_required` before any implementation lane.

## Hypothesis

The active pass-3 slice should expose an operator-visible replay packet for the exact digest, not only a lower-level route-priority queue. The packet should bind reverse-flow skill route discovery, the route-policy documentation proposal, and adjacent general-agent harness gates into one body-free surface that can be validated before activation.

## Change

- Added `current_digest_pass3_replay_packet` to the skill-route proposal lane map.
- Added a digest-specific fixture for `github-growth-20260706T181555.593867Z`.
- Added a focused regression proving:
  - reverse-flow skill evidence maps only to documentation, config, test, or code_patch lanes;
  - general-agent projects remain in `agent_harness_eval_required`;
  - no runtime action, provider launch, external harness execution, remote execution, raw source URL export, raw replay command export, or upstream body export is enabled.
- Documented the pass-3 replay packet in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T181555`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260706T181555 or 20260706T175555 or 20260706T173555"`: passed, 3 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 2 tests.
- `git diff --check`: passed, with line-ending warnings only.

## Review Notes

- No external activation, provider launch, push, promotion, restart, or remote execution was performed.
- The packet is intentionally specific to the current source digest and returns `not_applicable` for unrelated digests.
- Raw upstream bodies and raw URLs remain out of the replay packet; it exports hashes and selected item IDs only.
