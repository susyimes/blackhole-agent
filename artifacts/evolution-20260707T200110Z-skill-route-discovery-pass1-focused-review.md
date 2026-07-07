# Skill Route Discovery Pass 1 Focused Review

Source digest: `github-growth-20260707T200110.283498Z`

Rollback point: `artifacts/rollback/20260707T200110-skill-route-discovery-pass1/rollback-point.md`

Rollback ref: `refs/blackhole/rollback/20260707T200110-skill-route-discovery-pass1`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository presents a Codex/AI Agent skill package shape with `skills/reverse-flow`, `SKILL.md`, local sandbox/CTF framing, workflow steps, install examples, and diagnostic scripts.
- `https://github.com/Pluviobyte/rnskill`: public repository presents a generic AI Agent skills collection with `skills/`, docs, tools, plugin metadata, and Codex/Claude-style `SKILL.md` workflow language.
- `https://github.com/InternScience/Agents-A1`: public repository presents a general agent/model project with evaluation code and long-horizon agent claims, not a selected local skill package.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: public repository presents a general autonomous-agent simulation project with tests/benchmarks, not a selected local skill package.

## Hypothesis

The current pass should deepen the skill-route-discovery slice with an operator-visible pass-1 lane, not another standalone fixture. Skill-shaped repositories may enter bounded local lanes, while general agent projects must remain behind `agent_harness_eval_required` until a local harness result exists.

## Local Change

- Added `github-growth-20260707T200110.283498Z` to the pass-1 focused review lane.
- Added a current digest fixture and regression test for reverse-flow, rnskill, Agents-A1, and Fundamental-Ava.
- Documented the current pass and rollback metadata in `docs/skill-route-discovery.md`.

## Safety And Activation Notes

- External skill activation: not allowed.
- External agent activation: not allowed.
- External harness execution: not allowed.
- Provider launch: not allowed.
- Remote execution: not allowed.
- Promotion, push, restart, and rollback execution: not performed by this kernel run.
- Self-model: unchanged; the run had a concrete behavior path and did not need an ornamental self-description edit.

## Validation

Focused validation passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260707T200110
```

Result: `1 passed, 393 deselected`.

Neighboring pass-1 regression validation passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260707T184110 or 20260707T094834 or 20260707T052834"
```

Result: `3 passed, 391 deselected`.

Final combined rerun after proposal ID alignment:

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260707T200110 or 20260707T184110 or 20260707T094834 or 20260707T052834"
```

Result: `4 passed, 390 deselected`.
