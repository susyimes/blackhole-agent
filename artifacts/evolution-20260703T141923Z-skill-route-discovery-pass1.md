# Evolution Run: skill-route-discovery pass 1

- Source digest: `github-growth-20260703T141923.320717Z`
- Branch: `codex/blackhole-evolve/20260703T142019.150381-add-or-extend-local-tests-for-skill-route-discov`
- Rollback artifact: `artifacts/rollback-20260703T141923Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260703T141923Z-skill-route-discovery-pass1`

## Evidence

- `https://github.com/Kylin2021/reverse-flow-skill`, `https://github.com/lingbol088-spec/reverse-flow-skill`, and `https://github.com/poker117/reverse-flow-skill`: public fork cluster exposing AI Agent/Codex skill packaging, `skills/reverse-flow/SKILL.md`, scripts, local sandbox/CTF framing, and install/runtime wording.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill evidence with `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation framing, and advice-boundary metadata.

## Hypothesis

The current pass should make the reverse-flow fork cluster operator-visible as one bounded local validation lane, not three implementation targets. Skill/workflow evidence may select documentation, config, test, or code_patch only; adjacent general-agent projects remain behind `agent_harness_eval_required` until local harness evaluation exists.

## Changes

- Added `current_digest_20260703T141923_pass1_validation_lane.json` as the frozen current-digest fixture.
- Extended `current_digest_pass1_validation_lane` to route this digest through `p1-skill-route-discovery-validation`, `p2-skill-workflow-docs`, and `p3-agent-harness-eval-fixtures`.
- Added regression coverage for bounded reverse-flow fork routing, downgraded install/runtime pressure, and the general-agent harness boundary.
- Documented the current digest lane in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260703T141923`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260703T141923 or 20260703T104050 or 20260703T064052"`: passed, 3 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 214 tests.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`: passed.

## Review Notes

- No upstream skill package was installed, executed, or imported.
- Raw source URLs, replay command bodies, target paths, and upstream bodies remain out of the route output.
- The self-model was read and left unchanged; it already supports rollback-backed local validation over report-only churn.
