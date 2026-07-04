# Skill Route Discovery Pass 1 Current Window

- Source digest: `github-growth-20260704T190435.517226Z`
- Theme: `skill-route-discovery`
- Rollback: `artifacts/rollback/20260704T190527Z-skill-route-discovery-pass1-current-window/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill`: public Codex / AI Agent skill workflow with `skills/reverse-flow`, `SKILL.md`, local sandbox and CTF framing, install examples, scripts, and runtime pressure.
- `zhengxi-views`: public Agent Skill workflow with source-cited research language, traceability requirements, and an explicit non-investment-advice boundary.
- `Qwen-AgentWorld`: public general-agent world-model and evaluation repository with no `skill_route_discovery` route hint.

## Hypothesis

The current pass-1 window should produce an operator-visible activation-readiness lane rather than a standalone fixture only. Reverse-flow should be routed to a bounded local test lane with `skill_route_discovery_first`, zhengxi-views should be routed to documentation as a generic/source-cited skill workflow probe, and Qwen-AgentWorld should remain adjacent `agent_harness_eval_required` before any direct implementation lane.

## Changes

- Added a `github-growth-20260704T190435.517226Z` branch to `current_run_pass1_activation_readiness`.
- Added a local harness replay fixture for the carried evidence.
- Added focused regression coverage and updated the aggregate local harness fixture count.
- Documented the current source digest route interpretation.

## Review Notes

- No upstream code was installed, cloned, executed, or imported.
- Raw source URLs, replay commands, target paths, and upstream bodies remain unexported from the operator panel.
- External skill activation, external agent activation, external harness execution, provider launch, remote execution, profile writes, and memory writes remain denied.
- Self-model unchanged; its current local-evolution preference already matches this run.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k 20260704T190435` -> 1 passed.
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs` -> 1 passed.
- `python -m pytest tests/test_skill_routing.py -q` -> 280 passed.
- `python -m pytest tests/test_harness_eval.py -q` -> 239 passed.
- `python -m pytest tests/test_docs_contracts.py -q` -> 11 passed.
