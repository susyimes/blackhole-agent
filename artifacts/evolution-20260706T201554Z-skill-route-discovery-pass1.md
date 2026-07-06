# Evolution: skill-route-discovery pass 1

- Source digest: `github-growth-20260706T201555.949510Z`
- Theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260706T201644.803839-run-a-local-skill-route-discovery-validation-lan`
- Rollback ref: `refs/blackhole-rollback/20260706T201554Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260706T201554Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository exposes a Codex/AI Agent workflow skill shape, staged local reverse-analysis workflow, `skills/reverse-flow`, scripts, references, and install/run pressure.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, and `https://github.com/TianhangZhuzth/Fundamental-Ava`: public general-agent project claims without selected skill-route evidence for this pass.

## Hypothesis

The current window should turn explicit skill/workflow evidence into bounded local lanes while keeping general-agent project evidence with empty `route_hints` behind `agent_harness_eval_required` until a local harness task and approval gate are defined.

## Local Change

- Added a source-digest specialization for `github-growth-20260706T201555.949510Z`.
- Added `agent_harness_eval_intake_checklist` to the pass-1 lane output for the current digest.
- Added a frozen current-digest fixture and regression test for empty-route-hint general-agent projects.
- Documented the replay contract in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T201555` passed.

## Review Notes

- No upstream code was installed, copied, executed, or activated.
- Raw source URLs and upstream bodies are not exported in the evaluated lane output.
- General-agent projects remain proposal-only before harness evaluation; after that gate, allowed follow-up lanes remain documentation, test, or code_patch only.
- The self-model was read and left unchanged because it already permits rollback-backed, locally validated behavior changes and did not need new structure for this pass.
