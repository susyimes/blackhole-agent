# Skill Route Discovery Pass 1 Validation Batch

Source digest: `github-growth-20260704T122435.341572Z`

Rollback ref: `refs/blackhole-rollback/20260704T122432Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/Agent skill workflow evidence with a skill directory, local sandbox framing, scripts, and verification/report workflow language.
- `https://github.com/lyra81604/zhengxi-views`: Agent Skill workflow evidence with source-cited research, `SKILL.md`/`skill.yml`-style metadata, references, evals, and advice-boundary language.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent project evidence without a skill workflow route hint.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general-agent project evidence without a skill workflow route hint.

## Hypothesis

The active pass-1 slice should expose a replayable current-digest validation lane: skill/workflow evidence can enter only `documentation`, `config`, `test`, or `code_patch` lanes after local validation, while adjacent general-agent projects stay behind `agent_harness_eval_required`.

## Changes

- Added a `github-growth-20260704T122435.341572Z` pass-1 mapping in `src/blackhole_agent/skill_routing.py`.
- Exposed the full `active_pass1_evidence_lane` from `evaluate_skill_route_discovery_lane`.
- Added a focused regression test for the current evidence batch, including item-id-only evidence refs and no raw GitHub URLs in serialized lane output.

## Self-Model Decision

`docs/self-model.md` was left unchanged. Its current preference already matches this run: prefer rollback-backed, locally validated behavior paths over report-only work, while keeping offensive behavior and privacy leakage review-only.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "20260704T122435 or active_pass1_proposal_replay_lane"`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 10 tests.
- `python -m pytest tests/test_harness_eval.py -q -k current_digest_pass1_validation_lane`: no tests selected; selector was not useful.
- `python -m pytest tests/test_harness_eval.py -q -k pass1_validation_lane`: passed, 3 tests.
- `python -c "import blackhole_agent.harness_eval, blackhole_agent.skill_routing; print('imports ok')"`: passed.

## Review Notes

- The route remains metadata-only: no install, provider launch, external harness execution, remote execution, or upstream skill activation is enabled.
- The serialized validation lane omits raw GitHub URLs and replay commands; proposal evidence refs remain selected item IDs.
