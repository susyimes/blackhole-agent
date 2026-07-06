# Evolution Run: skill-route-discovery pass 4

- Source digest: `github-growth-20260706T064239.027225Z`
- Branch: `codex/blackhole-evolve/20260706T064335.746119-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback artifact: `artifacts/rollback-20260706T064237Z-skill-route-discovery-pass4.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260706T064237Z-skill-route-discovery-pass4`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository exposes a Codex/AI Agent skill package shape with `skills/reverse-flow`, `SKILL.md`, references, scripts, install and run examples, local CTF/sandbox framing, and staged reverse-workflow language.
- `https://github.com/InternScience/Agents-A1`: public repository presents a general agentic model/evaluation project with evaluation code and long-horizon agent claims, not a local skill-route package.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public repository presents a general-agent world-model and AgentWorldBench evaluation release, not a local skill-route package.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: public repository presents a general autonomous-agent simulation framework, not a local skill-route package.

## Hypothesis

The final pass should expose the exact current digest as an operator-visible
completion handoff. Reverse-flow-style skill evidence should map only to
bounded local lanes, while adjacent general-agent projects and fork/issue
signals should remain behind local agent-harness evaluation before any
implementation route.

## Changes

- Registered `github-growth-20260706T064239.027225Z` in the existing pass-4 skill-route completion handoff.
- Added a frozen pass-4 fixture for the current digest.
- Added a focused regression proving reverse-flow maps only to documentation/config/test/code_patch, general-agent rows remain `agent_harness_eval_required`, and no runtime/provider/external execution or raw URL export is enabled.
- Documented the current digest replay path and the rule that ForkEvent and IssuesEvent evidence can prioritize harness work but cannot independently trigger runtime or implementation action.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T064239`: passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260706T040238 or 20260706T052238 or 20260706T062238 or 20260706T064239"`: passed.

## Review Notes

- No external code was installed, cloned, imported, or executed.
- Upstream evidence URLs were reviewed only for route-shape evidence.
- The self-model was left unchanged because its current preference already matches this run: direct local behavior improvement when rollback-backed and validated, with external constraints remaining authoritative.
