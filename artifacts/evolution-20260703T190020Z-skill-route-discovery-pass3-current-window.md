# Evolution Run: Skill Route Discovery Pass 3 Current Window

- Source digest: `github-growth-20260703T185923.990705Z`
- Branch: `codex/blackhole-evolve/20260703T190020.621321-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback point: `artifacts/rollback/20260703T190020Z-skill-route-discovery-pass3-current-window/rollback-point.md`
- Rollback ref: `rollback/20260703T190020Z-skill-route-discovery-pass3-current-window`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex / AI Agent skill workflow with `skills/reverse-flow`, local sandbox framing, workflow stages, and scripts.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill repository with `SKILL.md`, `skill.yml`, references, evals, scripts, source-cited workflow, and an investment-advice boundary.
- `https://github.com/Forsy-AI/agent-apprenticeship`: public general agent workflow/evaluation project without a skill-route discovery hint in the local fixture.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general agent benchmark/world-model project without a skill-route discovery hint in the local fixture.

## Hypothesis

The current pass-3 route-discovery window should no longer fall back to the generic historical pass-3 packet. It can expose an operator-visible acceptance packet for the active proposal IDs while preserving the existing safety boundary: skill-route candidates get only documentation/config/test/code_patch lanes, Codex workflow evidence proves `skill_route_discovery_first`, and general agent projects remain `agent_harness_eval_required` before any implementation route.

## Local Change

- Added a `github-growth-20260703T185923.990705Z` branch to `pass3_current_wake_acceptance_packet`.
- Mapped `p1-skill-route-discovery-codex-workflow` to the local test lane for `codex_workflow_gate`.
- Mapped `p2-generic-skill-workflow-discovery` to a bounded `code_patch` lane while preserving queued documentation/config/test lanes and `runtime_action: none`.
- Kept `p3-agent-harness-eval-fixtures` as adjacent `agent_harness_eval_required`.
- Added a frozen current-digest fixture and regression test.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260703T185923 or pass3_current_wake_acceptance_packet"`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 225 tests.
- `python -m pytest tests/test_harness_eval.py -q`: passed, 234 tests.

## Review Notes

- No self-model edit was made. The existing self-model already matched this run's evidence-backed preference for reversible local behavior changes over standalone validation reports.
- No upstream code was copied or executed.
- The packet intentionally does not export raw GitHub URLs, replay commands, `runtime_execution`, or `provider_runtime` strings.
- Activation, restart, promotion, push, and rollback execution remain external supervisor actions.
