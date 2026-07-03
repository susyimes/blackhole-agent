# Skill Route Discovery Pass 1 Validation Lane

- source_digest: `github-growth-20260703T181923.507461Z`
- capability_theme: `skill-route-discovery`
- selected_proposals: `p1-skill-route-discovery-reverse-flow`, `p2-skill-route-discovery-zhengxi`, `p3-agent-harness-eval-general-projects`
- rollback_point: `artifacts/rollback/20260703T181923Z-skill-route-discovery-pass1/rollback-point.md`
- local_ref: `refs/rollback/20260703T181923Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `lingbol088-spec/reverse-flow-skill`: public Codex and AI Agent skill package with `skills/reverse-flow/SKILL.md`, scripts, local sandbox/CTF framing, workflow gate language, and install/runtime pressure that must remain downgraded.
- `lyra81604/zhengxi-views`: public Agent Skill shape with `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation language, and a non-investment-advice boundary.
- `Forsy-AI/agent-apprenticeship`, `QwenLM/Qwen-AgentWorld`, and `TianhangZhuzth/Fundamental-Ava`: general agent or benchmark projects without a skill workflow route hint or local harness result.

## Hypothesis

A pass-1 controller lane for this digest should make the active route split operator-visible:
Codex skill workflow evidence enters a local test lane only after `skill_route_discovery_first`;
generic source-cited skill workflow evidence enters documentation first; general agent projects
remain `agent_harness_eval_required` before any documentation, test, or code_patch follow-up.

## Local Change

- Added a frozen body-free fixture for the current digest.
- Added routing support for `github-growth-20260703T181923.507461Z` in `current_digest_pass1_validation_lane`.
- Added a regression test that verifies bounded lanes, denied external activation, denied provider/runtime execution, and no raw URL or replay command export.
- Documented the new replay path in `docs/skill-route-discovery.md`.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260703T181923
```

Result: `1 passed, 222 deselected`.

## Review Notes

- No self-model edit was made. The current self-model preference for rollback-backed local evolution matched this run and did not need clarification.
- No external skill, agent harness, provider runtime, remote execution, install, push, promotion, or restart was activated.
- The lane still relies on body-free summaries rather than cloning or executing upstream repositories.
