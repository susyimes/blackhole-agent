# Skill Route Discovery Pass 4 Current Digest

- Source digest: `github-growth-20260707T194110.112744Z`
- Branch: `codex/blackhole-evolve/20260707T194144.089274-run-a-bounded-skill-route-discovery-lane-for-rev`
- Rollback ref: `refs/rollback/20260708T000000Z-skill-route-discovery-pass4-current-digest-194110`
- Rollback artifact: `artifacts/rollback/20260708T000000Z-skill-route-discovery-pass4-current-digest-194110/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill` presents a Codex/AI Agent skill workflow with `skills/reverse-flow`, `SKILL.md`, staged workflow, local sandbox/CTF framing, diagnostic scripts, and install/run pressure.
- `Pluviobyte/rnskill` presents a generic skill collection with SKILL-style repository signals and install/enable/run pressure.
- `shepherd-agents/shepherd`, `InternScience/Agents-A1`, and `TianhangZhuzth/Fundamental-Ava` are general-agent project signals, not skill-route lanes before local harness evaluation.

## Hypothesis

The fourth pass should expose an operator-visible completion handoff for the current digest instead of adding another standalone fixture. The handoff should keep reverse-flow in a bounded test lane, rnskill in a bounded documentation lane, and adjacent general-agent projects behind `agent_harness_eval_required`.

## Change

- Added `skill_route_discovery_current_digest_20260707T194110_pass4_completion_handoff`.
- Wired `github-growth-20260707T194110.112744Z` into the current digest pass-4 dispatcher.
- Added focused regression coverage using the existing current-window fixture with the new digest.
- Documented the pass-4 completion surface and self-model decision.

## Self-Model

`docs/self-model.md` was left unchanged. The current text already states the relevant behavior preference: make rollback-backed, locally validated improvements instead of ornamental self-description edits.

## Validation

Focused validation passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260707T194110
# 1 passed, 392 deselected

python -m pytest tests/test_docs_contracts.py -q -k 20260707T194110
# 1 passed, 20 deselected

python -m pytest tests/test_skill_routing.py -q -k "20260707T190110 or 20260707T194110"
# 3 passed, 390 deselected
```

## Review Notes

- No upstream code was cloned, installed, or executed.
- No provider, external harness, remote execution, promotion, restart, memory write, or profile write was performed.
- Raw upstream bodies, replay commands, target paths, and source URLs remain excluded from the pass-4 handoff output.
