# Skill Route Discovery Pass 2 Activation Contract

- Source digest: github-growth-20260704T192436.767658Z
- Capability slice: skill-route-discovery
- Pass: 2 of 4
- Rollback point: `refs/rollback/20260704T192433Z-skill-route-discovery-pass2`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill workflow evidence with a `skills/reverse-flow` package, `SKILL.md`, local sandbox/CTF framing, scripts, install examples, and runtime pressure.
- `https://github.com/lyra81604/zhengxi-views`: source-cited Agent Skill evidence with `SKILL.md`, `skill.yml`, references, evals, scripts, WorkBuddy/MCP automation pressure, and a non-investment-advice boundary.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent world-model and benchmark evidence, not a skill package route.

## Hypothesis

Pass-2 route decisions need one operator-visible contract before pass 3:
skill-route rows stay inside documentation, config, test, or code_patch lanes;
Codex workflow-gate evidence proves `skill_route_discovery_first`; and
general-agent evidence is held in `agent_harness_eval_required` before any
local implementation follow-up.

## Local Change

- Added current digest recognition for `github-growth-20260704T192436.767658Z`.
- Added `route_activation_contract` to pass-2 skill-route surfaces.
- Added a body-free current digest fixture for reverse-flow, zhengxi-views, and Qwen-AgentWorld.
- Updated the route-discovery documentation with the new pass-2 replay path.

## Validation

Command:

```powershell
python -m pytest tests/test_skill_routing.py -q -k "current_run_pass2_local_validation_lane or 20260704T192436"
```

Result: passed, 2 tests selected.

## Review Notes

- No external repository was cloned or executed.
- Raw upstream bodies, source URLs, replay commands, and target paths remain out of the controller lane payload.
- Self-model was reviewed and left unchanged because the existing preference already matches this run's behavior and no new behavior-shaping self-description was needed.
