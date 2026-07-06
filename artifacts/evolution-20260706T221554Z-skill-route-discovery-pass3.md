# Evolution Run: skill-route-discovery pass 3

Source digest: `github-growth-20260706T221555.480207Z`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: inspected as a Codex-style skill/workflow package with `skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox and CTF/crackme framing, plus install/run examples that remain diagnostic only.
- `https://github.com/shepherd-agents/shepherd`: inspected as a general agent/runtime substrate signal with reversible trace, replay, fork, rollback, and supervision claims, requiring local harness evaluation before adoption.

## Hypothesis

The pass-3 operator replay lane should expose a current-window validation route packet that converts skill-route evidence into bounded local lanes while keeping general-agent projects behind `agent_harness_eval_required`. Evidence citations in the packet should remain selected `item_id` values only.

## Changes

- Added `current_window_validation_route_packet` to `current_pass3_skill_route_replay_lane`.
- Tightened negated skill-package detection so general-agent summaries with phrases such as "no selected skill package", "no SKILL.md evidence", or "no explicit skill workflow route signal" do not enter `skill_route_discovery`.
- Added proposal-eval regressions for the current reverse-flow plus Agents-A1/Qwen-AgentWorld/Fundamental-Ava/Shepherd route split.
- Documented the current pass-3 route packet in `docs/skill-route-discovery.md`.
- Added a docs contract assertion for the packet's item-id-only citation and harness-gating policy.

## Rollback

- Rollback ref: `refs/blackhole/rollback/20260706T221554Z`
- Rollback artifact: `artifacts/rollback-20260706T221554Z-skill-route-discovery-pass3.md`

## Validation

- `python -m pytest tests/test_proposal_eval.py -q -k "current_pass3_validation_route_packet or general_agent_negated_skill_package_text or current_pass3_skill_route_replay_lane"`: passed, 3 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k "skill_route_discovery_doc_records_current_pass3_validation_route_packet or skill_route_discovery_doc_records_route_discovery_catalog"`: passed, 2 tests.
- `python -m pytest tests/test_proposal_eval.py -q`: passed, 33 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest_20260706T141555_pass3_agent_harness_intake or agent_harness_eval_lane"`: passed, 7 tests.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 12 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 351 tests.

## Review Notes

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T221555` selected no tests because no skill-routing test currently uses that digest ID.
- The self-model was read and left unchanged. Its preference for rollback-backed local behavior changes matches this run; no evidence showed that editing it would shape behavior more than the code, tests, and docs changes.
- No upstream code, prompts, skill bodies, install commands, or runtime behavior were adopted.
