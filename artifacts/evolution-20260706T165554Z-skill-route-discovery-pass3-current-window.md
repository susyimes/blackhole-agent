# Skill Route Discovery Pass 3 Current Window

- Source digest: `github-growth-20260706T165555.533885Z`
- Capability slice: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260706T165655.822416-add-or-extend-a-local-agent-harness-evaluation-l`
- Rollback point: `artifacts/rollback/20260706T165554Z-skill-route-discovery-pass3-current-window/rollback-point.md`
- Rollback ref: `refs/blackhole/rollback/20260706T165554Z-skill-route-discovery-pass3-current-window`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow shape with `skills/reverse-flow`, `SKILL.md`, scripts, local sandbox and CTF/crackme framing.
- `https://github.com/InternScience/Agents-A1`: broad general-agent project evidence with long-horizon agent/evaluation framing.
- `https://github.com/QwenLM/Qwen-AgentWorld`: broad general-agent benchmark/simulator evidence.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: broad autonomous and collaborative agent project evidence.

## Hypothesis

The current mixed evidence window needs a ready-state controller surface after
general-agent probe fields are present. Skill/workflow evidence should remain in
bounded `skill_route_discovery` lanes, while broad agent projects should expose
an explicit `agent_harness_eval_required` route plan before any behavior
adoption.

## Changes

- Added `general_agent_project_route_plan` to `agent_harness_eval_lane`.
- Added a current-window general-agent fixture with probe-complete records for
  Agents-A1, Qwen-AgentWorld, Fundamental-Ava, and Shepherd.
- Updated aggregate harness fixture counts and named result checks.
- Documented the ready follow-through surface in `docs/skill-route-discovery.md`
  and `docs/architecture.md`.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. Its current preference already
supports rollback-backed local behavior changes while keeping offensive behavior
and privacy leakage review-only; this run produced a controller route-plan
improvement rather than new self-model evidence.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or current_window_general_agent_projects"`: passed, 6 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or agent_harness_eval_lane or current_window_general_agent_projects"`: passed, 7 tests.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 11 tests.
- `git diff --check`: passed with expected CRLF warnings only.

## Review Notes

- No upstream repository code was installed, executed, activated, or imported.
- Raw upstream bodies and raw source URLs are not exported by the new route-plan
  surface; source URLs are represented with stable hashes in rows.
- General-agent rows expose no direct pre-eval implementation lane and may only
  continue to documentation, test, or code_patch after local harness evaluation.
