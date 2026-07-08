# Blackhole Run: skill-route-discovery pass 4

- Source digest: `github-growth-20260708T201850.924336Z`
- Branch: `codex/blackhole-evolve/20260708T201936.030239-run-a-bounded-skill-route-discovery-lane-for-rev`
- Rollback ref: `refs/blackhole-rollback/20260708T201848Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260708T201848Z-skill-route-discovery-pass4.md`

## Hypothesis

The final pass should expose the current reverse-flow/rnskill/Hy3/Shepherd
window through an operator-visible handoff rather than another isolated
fixture. Skill workflow rows should complete only through bounded local
documentation, config, test, or code_patch lanes, while general agent projects
remain queued behind local harness evaluation.

## Evidence Review

- `lingbol088-spec/reverse-flow-skill` presents a Codex/AI-agent skill layout
  with `skills/reverse-flow`, `SKILL.md`, local sandbox/CTF framing, staged
  workflow language, and scripts. Install/run/runtime wording is route pressure
  only.
- `Pluviobyte/rnskill` presents a generic SKILL.md-compatible skill collection
  and motivates documentation-first generic workflow criteria.
- `Tencent-Hunyuan/Hy3` and `shepherd-agents/shepherd` are general agent/model
  or runtime substrate projects, not skill workflow packages, so they stay in
  `agent_harness_eval_required` before any local implementation lane.

## Changes

- Added `current_digest_20260708T201850_pass4_operator_handoff` to the skill
  routing lane map and harness output.
- Added a frozen current-digest fixture and regression test for the pass-4
  operator handoff.
- Documented the pass-4 route interpretation.
- Left `docs/self-model.md` unchanged because it already describes the
  rollback-backed local validation preference used here.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260708T201850
python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py -q -k "20260708T201850 or 20260708T195850"
```

Results:

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T201850`: passed, 1 test.
- `python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py -q -k "20260708T201850 or 20260708T195850"`: passed, 3 tests.

## Review Notes

The handoff is metadata-only. It exports selected item IDs, lane names, proposal
IDs, hashes, rollback metadata, and activation denials. It does not export raw
source URLs, raw evidence URLs, replay commands, target paths, upstream bodies,
or permit install, provider launch, external harness execution, remote
execution, promotion, restart, or upstream skill activation.
