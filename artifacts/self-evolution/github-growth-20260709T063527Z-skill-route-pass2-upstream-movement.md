# Evolution Run: skill-route-discovery pass 2 upstream movement lane

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex / AI Agent skill workflow with `skills/reverse-flow`, local sandbox framing, scripts, install examples, and staged reverse-analysis language.
- `https://github.com/lingbol088-spec/reverse-flow-skill/issues/1`: sparse issue movement only; it does not provide enough local design evidence to authorize a runtime or implementation lane.
- `https://github.com/Pluviobyte/rnskill`: public AI Agent Skills collection for Codex, Claude Code, and other `SKILL.md` workflows, with skills, docs, tools, plugin metadata, and install examples.

## Hypothesis

The active pass-2 operator lane should distinguish repository-level skill route evidence from sparse upstream issue/comment movement. Repository evidence may enter bounded local validation lanes; issue/comment movement should stay visible as low-confidence pressure with no accepted output lane before local corroboration.

## Changes

- Added `upstream_movement_rows` to `current_pass2_skill_route_operator_lane`.
- Added the active `github-growth-20260709T063527.172428Z` proposal ID binding.
- Kept issue/comment movement out of `skill_route_local_lane_candidates`.
- Added a regression for reverse-flow, rnskill, sparse issue movement, and adjacent general-agent rows.
- Documented the pass-2 operator behavior in `docs/skill-route-discovery.md`.

## Self-Model Decision

`docs/self-model.md` was left unchanged. Its current preference for locally validated behavior over report-only changes matches this run, and the new operator lane is behavior-shaping in code rather than a self-description update.

## Validation

- `python -m pytest tests/test_proposal_eval.py -q -k "sparse_issue_movement or current_pass2_operator_lane"`: passed, 2 tests.
- `python -m pytest tests/test_proposal_eval.py -q -k "skill_route_discovery or route_hint_lane_map or current_pass2_activation_checkpoint or current_pass2_operator_lane"`: passed, 10 tests.
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T090635 or upstream_movement or operator_lane"`: passed, 9 tests.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 32 tests.

## Review Notes

- The issue/comment row is body-free and exports only a source hash.
- No upstream skill code is installed, executed, cloned, or activated.
- General-agent rows still require `agent_harness_eval_required` before implementation lanes.
