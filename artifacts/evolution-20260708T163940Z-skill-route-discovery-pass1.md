# Evolution Run: Skill Route Discovery Pass 1

Source digest: `github-growth-20260708T163850.664161Z`

Rollback point:
`artifacts/rollback/20260708T163940Z-skill-route-discovery-pass1-codex-workflow-gate/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill` presents a Codex/AI Agent skill workflow with a `skills/` layout, `SKILL.md`, sandbox/CTF framing, staged workflow text, install examples, and script examples.
- `Pluviobyte/rnskill` presents a generic AI Agent Skills collection with `skills`, docs, tools, marketplace metadata, manual install instructions, and SKILL.md-compatible workflow language.
- `Tencent-Hunyuan/Hy3` and `shepherd-agents/shepherd` are general agent/model/runtime projects. They do not provide selected skill-package evidence in this digest window.

## Hypothesis

The current pass-1 window should be visible through the existing validation and activation-readiness surfaces, not as a standalone report. Skill workflow evidence must stay limited to documentation, config, test, or code_patch lanes, while adjacent general-agent projects remain behind `agent_harness_eval_required`.

## Change

- Added current-digest-specific pass-1 route specs for `p1-skill-route-discovery-codex-workflow-gate` and `p2-generic-skill-route-discovery-config`.
- Added a focused fixture for `github-growth-20260708T163850.664161Z`.
- Added a regression test that validates the pass-1 validation lane and activation-readiness panel deny runtime, provider, external harness, and remote execution routes.
- Updated `docs/skill-route-discovery.md` with the operator replay note.

## Review Notes

No external activation, install, provider launch, external harness execution, remote execution, promotion, restart, profile write, or memory write is enabled by this change. The self-model was read and left unchanged because a concrete behavior path was available.
