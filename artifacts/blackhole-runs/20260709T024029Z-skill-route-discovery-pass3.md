# Skill Route Discovery Pass 3

- Source digest: `github-growth-20260708T183850.458999Z`
- Theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260708T183941.839220-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/blackhole/rollback/20260709T024029Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260709T024029Z-skill-route-discovery-pass3/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill package with `skills/reverse-flow`, staged reverse-flow workflow, local sandbox framing, and script examples. Treated as skill-route evidence only.
- `https://github.com/Pluviobyte/rnskill`: generic AI Agent skills collection. Treated as generic skill workflow evidence with preserved uncertainty because local repository internals were not inspected.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime substrate with reversible traces/fork/replay claims. Kept behind `agent_harness_eval_required`.
- `https://github.com/Tencent-Hunyuan/Hy3`: reasoning/agent model project with provider/runtime pressure. Kept behind `agent_harness_eval_required`.

## Hypothesis

The active pass-3 window needs an operator-visible activation packet, not another isolated fixture. Skill repositories can be converted into bounded local lanes (`documentation`, `config`, `test`, `code_patch`) only after local validation, while adjacent general-agent/model projects must remain blocked from implementation routes until agent-harness evaluation is present.

## Changes

- Added `current_digest_20260708T183850_pass3_activation_packet` to the skill-route lane map.
- Exposed the packet through `evaluate_skill_route_discovery_lane`.
- Added a local harness fixture for the active digest.
- Added focused harness and direct classifier tests.

## Validation

- `pytest tests/test_harness_eval.py tests/test_skill_routing.py -q -k 20260708T183850`
- `pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`
- `pytest tests/test_skill_routing.py -q`
- `pytest tests/test_harness_eval.py -q -k "20260708T183850 or local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`

All validation commands passed.

## Review Notes

- Self-model left unchanged; it already says reversible local behavior changes are preferred when validation and rollback cover them.
- No external skill install, clone, execution, provider launch, restart, push, or promotion was performed.
- The packet exports source and replay metadata as hashes or artifact paths only; raw evidence URLs and raw replay commands are not exported from the packet.
