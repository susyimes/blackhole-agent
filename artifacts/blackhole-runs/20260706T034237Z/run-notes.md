# Run Notes

## Source

- Source digest: `github-growth-20260706T034238.736996Z`
- Capability slice: `skill-route-discovery`, pass 3 of 4
- Rollback artifact: `artifacts/blackhole-runs/20260706T034237Z/rollback.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill-workflow shape with `skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox/CTF framing, install examples, and vulnerability-analysis pressure.
- `https://github.com/InternScience/Agents-A1`: general agent/model and evaluation project without explicit local skill-workflow routing evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent benchmark/world-model project without explicit local skill-workflow routing evidence.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general agent project without explicit local skill-workflow routing evidence.

## Hypothesis

Current pass-3 evidence should become an operator-visible route-to-validation
lane before activation. Reverse-flow-skill may enter bounded
`skill_route_discovery_first` lanes, while general agent projects remain
`agent_harness_eval_required` with no direct documentation, test, code_patch,
runtime, provider, external harness, or remote-execution lane before a local
harness result exists.

## Changes

- Added `tests/fixtures/skill_route_discovery/current_digest_20260706T034238_pass3_route_to_validation.json`.
- Extended `src/blackhole_agent/skill_routing.py` so
  `github-growth-20260706T034238.736996Z` emits
  `current_digest_pass3_route_to_validation_lane` with:
  - `p1_skill_route_discovery_reverse_flow` in the local test lane.
  - `p3_document_route_policy_for_trend_evidence` in the documentation lane.
  - `p2_agent_harness_eval_trending_agent_projects` as the shared adjacent
    general-agent harness-eval gate.
- Added a focused regression in `tests/test_skill_routing.py`.
- Documented the current pass-3 route split in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T034238`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260706T034238 or 20260706T032238 or 20260706T022238"`: passed, 3 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.

## Review Notes

- No self-model edit was made. The existing self-model already matches this
  run's narrow safety boundary and preference for rollback-backed local
  behavior changes over validation-report-only artifacts.
- No external code was cloned, installed, imported, or executed.
- Raw upstream URLs and replay commands remain absent from the pass-3 lane
  output; evidence item IDs are retained for local replay.
