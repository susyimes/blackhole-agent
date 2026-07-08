# Evolution: skill-route-discovery pass 4 completion

Source digest: `github-growth-20260708T213850.601257Z`
Branch: `codex/blackhole-evolve/20260708T213940.882777-add-a-local-skill-route-discovery-validation-lan`

## Rollback

Rollback ref: `refs/rollback/20260708T213848Z-skill-route-discovery-pass4-local-validation-lanes`
Rollback artifact: `artifacts/rollback/20260708T213848Z-skill-route-discovery-pass4-local-validation-lanes/rollback-point.md`

Rollback execution remains an explicit destructive operator action only.

## Evidence

- `https://github.com/Pluviobyte/rnskill` presents a SKILL.md-compatible AI Agent Skills collection with `skills/`, docs, tools, plugin-style metadata, and install pressure.
- `https://github.com/lingbol088-spec/reverse-flow-skill` presents Codex/AI-agent reverse-flow skill workflow evidence with a skill package shape and workflow-gate pressure.
- `https://github.com/shepherd-agents/shepherd` and `https://github.com/Tencent-Hunyuan/Hy3` are broader agent/runtime/model projects, not selected skill workflow packages for direct adoption.

## Hypothesis

The current pass should expose an operator-visible pass-4 completion checkpoint rather than another standalone fixture. Skill-bearing repositories can map to bounded local documentation/test/config/code_patch lanes after validation, while adjacent general-agent projects must remain behind `agent_harness_eval_required`.

## Change

- Added `current_digest_20260708T213850_pass4_completion_checkpoint` to the skill route lane map.
- Added a frozen current digest fixture for reverse-flow, rnskill, Shepherd, and Hy3.
- Added a focused regression test for proposal-to-route mapping, adjacent harness holdback, rollback metadata, and body-free serialization.
- Documented the new checkpoint and replay command in `docs/skill-route-discovery.md`.

## Validation

Target command: `python -m pytest tests/test_skill_routing.py -q -k 20260708T213850`

Expected acceptance:
- `rnskill` maps to `p1-rnskill-skill-route-discovery` in the documentation lane.
- `reverse-flow-skill` maps to `p2-reverse-flow-codex-workflow-gate` in the test lane.
- Shepherd and Hy3 map to `p3-general-agent-harness-eval` with no direct lanes before local harness evaluation.
- Runtime action, external skill activation, provider launch, external harness execution, remote execution, promotion, and restart remain denied.

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference for rollback-backed local evolution with explicit uncertainty already matches this pass.
