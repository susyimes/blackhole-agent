# Skill Route Discovery Pass 4 Run

- Created at: 2026-07-09T01:40:00+08:00
- Source digest: github-growth-20260708T173850.570889Z
- Branch: codex/blackhole-evolve/20260708T173954.981326-add-or-extend-local-tests-for-skill-route-discov
- Rollback ref: refs/blackhole-rollback/20260709T014000Z-skill-route-discovery
- Rollback artifact: artifacts/rollback/rollback-point-20260709T014000Z-skill-route-discovery.md

## Evidence Review

Reviewed the carried evidence URLs narrowly:

- https://github.com/lingbol088-spec/reverse-flow-skill
- https://github.com/Pluviobyte/rnskill
- https://github.com/shepherd-agents/shepherd
- https://github.com/Tencent-Hunyuan/Hy3

Reusable lesson: skill-shaped public repositories can justify bounded local
documentation, config, test, or code_patch lanes only after local validation.
General agent or provider/model repositories remain behind
agent_harness_eval_required before implementation follow-up.

## Local Change

- Added `skill_route_discovery_current_digest_20260708T173850_pass4_operator_handoff`.
- Reused the existing pass-4 operator handoff builder with configurable skill
  row proposal IDs, adjacent row proposal IDs, and adjacent row count.
- Added a frozen fixture for the current 173850 pass-4 window.
- Documented the pass-4 completion and replay surface.
- Left `docs/self-model.md` unchanged because it already states the relevant
  preference: rollback-backed local validation before activation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T173850`
  - Result: 1 passed, 429 deselected.
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T145852 or 20260708T161850 or 20260708T173850"`
  - Result: 3 passed, 427 deselected.
- `python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
  - Result: 8 passed, 251 deselected.
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: 27 passed.

## Review Notes

- The new handoff is record-only and exports hashes, selected item IDs, proposal
  IDs, lane names, rollback metadata, and denial flags.
- It does not export raw source URLs, raw evidence URLs, raw replay commands,
  target paths, upstream bodies, install commands, provider launch, external
  harness execution, remote execution, promotion, restart, profile writes, or
  memory writes.
- No restart, push, promotion, or remote execution was performed by this kernel.
