# Evolution: Skill Route Discovery Pass 2

- Source digest: `github-growth-20260705T084958.837379Z`
- Branch: `codex/blackhole-evolve/20260705T085055.206534-run-a-bounded-local-skill-route-discovery-lane-f`
- Rollback: `artifacts/rollback/20260705T084956Z-skill-route-discovery-pass2/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill` exposes a public `skills/reverse-flow`
  skill package with `SKILL.md`, references, scripts, Codex/AI Agent workflow
  language, install examples, and local sandbox/CTF framing.
- `QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`, and
  `InternScience/Agents-A1` are general agent/model projects. They may be useful
  local lessons, but this run did not find a direct skill workflow route hint or
  local harness evaluation result.

## Hypothesis

A digest-specific pass-2 lane should make the route split operator-visible:
reverse-flow skill evidence can enter bounded documentation/test local lanes,
while general agent projects stay in `agent_harness_eval_required` with ranking
inputs before any implementation lane can open.

## Change

- Added `current_digest_pass2_local_validation_lane` handling for
  `github-growth-20260705T084958.837379Z`.
- Added a frozen current digest fixture and regression coverage.
- Documented the pass-2 lane and replay command.
- Left `docs/self-model.md` unchanged because its current preference for
  rollback-backed, validated local behavior matched this run.

## Validation

Targeted validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260705T084958
```

Result: `1 passed, 292 deselected`.

Expanded validation:

```powershell
python -m pytest tests/test_skill_routing.py -q
python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or agent_harness_eval_lane"
python -m pytest tests/test_docs_contracts.py -q
python -m ruff check src\blackhole_agent\skill_routing.py tests\test_skill_routing.py
```

Results: `293 passed`; `14 passed, 227 deselected`; `11 passed`; `All checks passed!`.

## Review Notes

- No external repository code was cloned, installed, imported, or executed.
- Raw upstream URLs, replay commands, target paths, provider values, and upstream
  bodies are kept out of the operator lane.
- General agent projects remain blocked from direct runtime and code_patch
  routing until local harness evaluation exists.
