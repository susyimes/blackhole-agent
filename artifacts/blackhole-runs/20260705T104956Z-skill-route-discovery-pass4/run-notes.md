# Skill Route Discovery Pass 4

Source digest: `github-growth-20260705T104958.052264Z`
Branch: `codex/blackhole-evolve/20260705T105054.296436-add-a-bounded-local-validation-lane-for-reverse-`
Rollback ref: `refs/blackhole/rollback/20260705T185127Z-skill-route-discovery-pass4`
Rollback artifact: `artifacts/rollback/20260705T185127Z-skill-route-discovery-pass4.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill repository with `skills/reverse-flow`, local sandbox/CTF framing, install examples, and script/runtime pressure. Interpreted as skill-route evidence only.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent/world-model benchmark evidence. Interpreted as adjacent `agent_harness_eval_required`, not a skill route.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous/social agent evidence. Interpreted as adjacent `agent_harness_eval_required`.
- `https://github.com/InternScience/Agents-A1`: general long-horizon agent evidence. Interpreted as adjacent `agent_harness_eval_required`.

## Hypothesis

The pass-4 slice should finish with an operator-visible local handoff for the current digest. Reverse-flow fork-lineage evidence should collapse into one bounded skill-route validation lane, selected only as `test` plus documentation support, while adjacent general-agent projects are queued for local harness evaluation before any implementation lane.

## Changes

- Added a frozen current digest fixture for `20260705T104958` with reverse-flow fork-lineage item IDs and adjacent general-agent rows.
- Wired the digest into the existing pass-4 completion handoff so it emits:
  - `p1_reverse_flow_skill_route_discovery` in the `test` lane.
  - `p2_skill_discovery_docs_and_fixture` in the `documentation` lane.
  - `p3_agent_harness_eval_queue` as `agent_harness_eval_required`.
- Added a regression test proving the handoff is ready, body-free, denied for runtime/external activation, and preserves selected evidence item IDs without exporting raw URLs or replay commands.

## Self-Model

Read `docs/self-model.md` and left it unchanged. Its current preference already covers this run: prefer rollback-backed local behavior changes over report-only scaffolding, with runtime policy and rollback rules remaining external constraints.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_digest_20260705T104958`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "current_digest_20260705T080817 or current_digest_20260705T092958 or current_digest_20260705T104958"`: passed, 3 tests.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`: passed.

## Review Notes

- Upstream install, script, runtime, provider launch, remote execution, and direct general-agent implementation remain denied.
- The rollback point was created before source edits and was not removed.
