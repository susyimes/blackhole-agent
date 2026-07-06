# Blackhole Run: skill-route-discovery pass 2

- Source digest: github-growth-20260706T215555.476919Z
- Branch: codex/blackhole-evolve/20260706T215648.909557-create-or-extend-a-local-agent-harness-evaluatio
- Rollback artifact: artifacts/rollback/20260706T215554Z-skill-route-discovery-pass2.md
- Rollback ref: refs/rollback/blackhole-agent/20260706T215554Z-skill-route-discovery-pass2

## Evidence Reviewed

- https://github.com/lingbol088-spec/reverse-flow-skill
- https://github.com/InternScience/Agents-A1
- https://github.com/QwenLM/Qwen-AgentWorld
- https://github.com/TianhangZhuzth/Fundamental-Ava
- https://github.com/shepherd-agents/shepherd

The reusable lesson was route separation: a repository with a Codex skill/workflow layout can enter a bounded
skill-route lane, while general agent projects first need local agent-harness fixtures with declared probe fields.
No upstream code was cloned, installed, or executed.

## Hypothesis

Pass-2 skill-route discovery should expose a single operator-visible probe that confirms whether the current window is
ready to replay both bounded skill-route lanes and adjacent agent-harness fixtures before any local behavior is adopted.

## Changes

- Added `pass2_route_probe` to `skill_route_discovery_lane` output.
- Added a no-network current-digest fixture for reverse-flow-skill plus Agents-A1, Qwen-AgentWorld, Fundamental-Ava,
  and shepherd.
- Added regression coverage for bounded lanes, ready probe fields, closed runtime/provider/remote execution flags, and
  no raw source URL export.
- Documented the pass-2 probe in `docs/architecture.md`.

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference already matches the evidence from this run:
prefer locally validated behavior paths, keep direct runtime adoption closed, and record uncertainty explicitly.

## Validation

```powershell
pytest tests/test_harness_eval.py -q -k "20260706T215555_pass2_route_probe or skill_route_discovery_current_pass2_batch_validation_lane"
pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane
pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane
pytest tests/test_harness_eval.py -q
pytest -q
```

Result: all commands passed; full suite reported `853 passed`.

## Review Notes

- External execution remains disabled: no install, clone, provider launch, remote execution, or upstream body export.
- The probe is intentionally pass-2 scoped; non-pass-2 windows report a diagnostic instead of claiming readiness.

