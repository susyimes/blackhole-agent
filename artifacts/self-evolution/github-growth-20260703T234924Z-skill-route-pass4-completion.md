# Skill Route Discovery Pass 4 Completion

Source digest: `github-growth-20260703T234924.826468Z`
Branch: `codex/blackhole-evolve/20260703T235021.681682-create-a-local-skill-route-discovery-validation-`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill` exposes a Codex/AI Agent skill package with `skills/reverse-flow`, local sandbox/CTF framing, and install or script examples. Local lesson: keep it behind `skill_route_discovery_first` and validate only bounded lanes before any workflow routing change.
- `https://github.com/lyra81604/zhengxi-views` is treated as generic/source-cited Agent Skill workflow evidence. Local lesson: document and validate the route shape without importing provider/runtime behavior.
- `https://github.com/Forsy-AI/agent-apprenticeship` and `https://github.com/QwenLM/Qwen-AgentWorld`, with the carried Fundamental-Ava proposal evidence, are general-agent signals. Local lesson: group them behind agent-harness evaluation rather than direct skill-route lanes.

## Hypothesis

The pass-4 completion should be operator-visible for the exact current digest, not only through older digest aliases. A ready handoff should map skill evidence to bounded local lanes, require rollback plus focused validation, and deny runtime, provider, remote, external activation, and raw upstream export paths.

## Change

- Added the `github-growth-20260703T234924.826468Z` pass-4 digest route to the existing current-digest completion helper.
- Added proposal-specific final-pass IDs for reverse-flow, zhengxi, and general-agent harness evaluation.
- Added a focused regression for the current digest final handoff.
- Documented the final-pass operator replay path in `docs/skill-route-discovery.md`.

## Rollback

Rollback point:
`artifacts/rollback/20260703T234924Z-skill-route-discovery-pass4-completion/rollback-point.md`

Rollback ref:
`refs/blackhole-rollback/20260703T234924Z-skill-route-discovery-pass4-completion`

## Self-Model

Left `docs/self-model.md` unchanged. The current self-model already states the relevant preference: try locally validated, rollback-backed behavior improvements instead of stopping at validation-report scaffolding, while keeping offensive, unauthorized, and privacy-leaking paths out of autonomous activation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260703T234924` passed: 1 passed, 232 deselected.
- `python -m pytest tests/test_skill_routing.py -q` passed: 233 passed.
- `python -m pytest tests/test_docs_contracts.py -q` passed: 11 passed.
