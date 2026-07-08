# Evolution Run: skill-route-discovery pass 2 current window

- Source digest: `github-growth-20260708T181850.408978Z`
- Branch: `codex/blackhole-evolve/20260708T181934.820195-add-a-bounded-skill-route-discovery-validation-f`
- Rollback ref: `refs/rollback/20260709T021848Z-skill-route-discovery-pass2-current-window`
- Rollback artifact: `artifacts/rollback/20260709T021848Z-skill-route-discovery-pass2-current-window/rollback-point.md`
- Self-model decision: left `docs/self-model.md` unchanged because it already describes rollback-backed local validation and the narrow safety boundary used in this run.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow with `skills/reverse-flow`, local sandbox/CTF framing, staged workflow, install examples, and scripts. Treated as skill-route evidence only.
- `https://github.com/Pluviobyte/rnskill`: public AI Agent Skills / SKILL.md-style collection. Treated as generic skill workflow evidence only.
- `https://github.com/shepherd-agents/shepherd`: public general-agent runtime substrate. Kept behind `agent_harness_eval_required`.
- `https://github.com/Tencent-Hunyuan/Hy3`: public reasoning/agent model project. Kept behind `agent_harness_eval_required`.

## Hypothesis

The active pass-2 wake should expose a digest-specific operator-visible validation lane instead of falling through to the previous shared 20260707 surface. Reverse-flow and rnskill evidence can be replayed as bounded skill-route rows, while Shepherd and Hy3 must remain adjacent agent-harness rows until local harness validation selects any follow-up lane.

## Changes

- Added `github-growth-20260708T181850.408978Z` to the pass-2 skill-route dispatcher.
- Added `skill_route_discovery_current_digest_20260708T181850_pass2_validation_lane`.
- Added the frozen fixture `tests/fixtures/skill_route_discovery/current_digest_20260708T181850_pass2_validation_lane.json`.
- Added a focused regression asserting:
  - reverse-flow maps to `p1-skill-route-discovery-reverse-flow` in the bounded test lane;
  - rnskill maps to `p2-generic-skill-route-discovery-rnskill` in the documentation lane;
  - Shepherd maps to `p3-agent-harness-eval-shepherd`;
  - Hy3 maps to `p4-agent-harness-eval-hy3`;
  - p5 remains an operator-visible anchor without an invented row because no selected Blender/Seedance digest item was present;
  - runtime, install, provider launch, external harness execution, remote execution, raw URL/body/command export, profile writes, and memory writes remain disabled.
- Documented the pass-2 lane and added a docs-contract regression.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T181850`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T165850 or 20260708T171850 or 20260708T181850"`: passed, 3 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records_20260708T181850`: passed, 1 test.

## Review Notes

- No self-model edit was needed.
- No activation, restart, push, provider launch, external harness execution, install, clone, or remote execution was performed.
- The Blender/Seedance anchor remains evidence-incomplete for this digest and should get a row only when a selected digest item exists.
