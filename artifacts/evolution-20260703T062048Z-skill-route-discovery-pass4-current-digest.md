# Evolution Run: skill-route-discovery pass 4 current digest

- Source digest: `github-growth-20260703T062050.658036Z`
- Branch: `codex/blackhole-evolve/20260703T062233.603889-create-or-extend-local-tests-that-feed-skill-rel`
- Rollback artifact: `artifacts/rollback-20260703T062048Z-skill-route-discovery-pass4-current-digest.md`
- Rollback ref: `refs/blackhole-agent/rollback/20260703T062048Z-skill-route-discovery-pass4-current-digest`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: carried as skill workflow evidence with Codex workflow gate and generic skill-route profiles.
- `https://github.com/lyra81604/zhengxi-views`: carried as source-cited skill workflow evidence with local documentation/test lane pressure.
- `https://github.com/QwenLM/Qwen-AgentWorld`: carried as adjacent general-agent evidence, not a skill-route lane.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: retained as workflow evidence pressure for bounded local lanes, with no runtime activation in this pass.

## Hypothesis

The final skill-route pass should close skill-route proposals while keeping adjacent general-agent proposals in `agent_harness_eval_required`. Treating every anchoring proposal as a skill-route proposal makes mixed final-pass windows block on correctly gated adjacent agent evidence. Splitting final-pass proposal closure into skill-route anchors and adjacent agent-harness anchors gives the supervisor an operator-visible handoff without granting runtime, install, provider, or remote-execution authority.

## Changes

- Updated `skill_route_discovery_current_pass_profile_closure` to separate adjacent `agent_harness_eval` anchoring proposals from skill-route proposal matching.
- Added `final_pass_operator_replay_manifest` to the local kernel handoff, exposing source digest, matched skill-route proposal IDs, adjacent agent-harness proposal count, selected lanes, replay hashes, and denial flags.
- Added a current-digest pass-4 local harness fixture for `github-growth-20260703T062050.658036Z`.
- Updated the local harness aggregate fixture counts and assertion list.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. Its current preference for rollback-backed, locally validated behavior changes already fits this run; no new evidence showed that the self-model itself was shaping or blocking behavior.

## Validation

- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or 20260703T062050"`: passed, 10 tests.
- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py::test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs -q`: passed, 1 test.
- `PYTHONPATH=src python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 2 tests.

## Review Notes

- No upstream code, external harness, provider runtime, remote execution, raw source URLs, or raw upstream bodies were activated or exported.
- The new fixture uses body-free local summaries for adjacent Qwen-AgentWorld evidence so it can be evaluated by the local route boundary without becoming a skill candidate.
