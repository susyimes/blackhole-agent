# Skill Route Discovery Pass 1 Route Probe Metadata

Source digest: `github-growth-20260702T032714.646827Z`

Hypothesis:
Skill-related repository evidence is more useful to the supervisor when the pass-1 validation lane exposes a compact,
body-free route probe explaining why each repository was classified, while general agent projects remain adjacent
`agent_harness_eval_required` rows until local harness evaluation selects a follow-up route.

Evidence used:
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`

Change summary:
- Added `github-growth-20260702T032714.646827Z` pass-1 proposal IDs to the current digest lane.
- Added bounded `route_probe_metadata` to skill-route rows with hashed source identity, route profiles, layout signals,
  metadata signals, evidence item IDs, bounded allowed lanes, and local validation gates.
- Added adjacent general-agent route probe metadata for Qwen-AgentWorld and Fundamental-Ava that keeps them in
  `agent_harness_eval_required` with no direct skill-route inheritance.
- Added a frozen current-digest fixture and regression test.

Self-model decision:
`docs/self-model.md` was left unchanged. The current file already says local evolution should be rollback-backed,
locally validated, explicit about uncertainty, and not biased toward small diffs. This run followed that behavior; no
new self-description was needed.

Material actions:
- Created rollback ref `refs/blackhole-rollback/20260702T032713Z`.
- Added rollback artifact `artifacts/self-evolution/github-growth-20260702T032714Z-rollback.md`.
- Added fixture `tests/fixtures/skill_route_discovery/current_digest_20260702T032714_pass1_validation_lane.json`.
- Edited `src/blackhole_agent/skill_routing.py` and `tests/test_skill_routing.py`.
- No external content was fetched; the run used the supplied digest evidence and local repository files.

Validation:
- `python -m py_compile src\blackhole_agent\skill_routing.py`
- `pytest tests/test_skill_routing.py -q -k "20260702T032714 or 20260702T020714"` passed: 2 passed, 152 deselected.
- `pytest tests/test_skill_routing.py -q` passed: 154 passed.
- `ruff check src\blackhole_agent\skill_routing.py tests\test_skill_routing.py` passed.

Review notes:
- Unsupported upstream lane pressure such as runtime execution or provider runtime is intentionally not exported in the
  route probe metadata.
- Raw GitHub URLs and raw replay commands remain absent from the serialized pass-1 lane.
