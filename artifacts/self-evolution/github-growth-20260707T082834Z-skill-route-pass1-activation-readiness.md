# Skill Route Discovery Pass 1 Activation Readiness

- Source digest: `github-growth-20260707T082834.484151Z`
- Capability theme: `skill-route-discovery`
- Active pass: 1 of 4
- Rollback point: `artifacts/rollback/20260707T162940Z-skill-route-discovery-pass1/rollback-point.md`
- Local rollback ref: `refs/blackhole/rollback/20260707T162940Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `lingbol088-spec/reverse-flow-skill`: public GitHub repository with Codex/AI Agent skill workflow markers, `skills/reverse-flow/SKILL.md`, local sandbox and CTF framing, install examples, and script examples.
- `Pluviobyte/rnskill`: public GitHub repository with an AI Agent Skills collection, `skills`, docs, tools, plugin marketplace metadata, manual install shape, and SKILL.md-compatible workflow language.
- `InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd`: public general-agent project evidence without an explicit local skill route hint or local harness result.

## Hypothesis

The current window needs an operator-visible pass-1 activation readiness panel that keeps the two skill repositories in bounded local skill-route lanes while routing broader agent projects to agent harness evaluation before any implementation lane opens.

## Change

- Added candidate-name scoped proposal matching in `current_run_pass1_activation_readiness`.
- Added a frozen current-digest fixture for `github-growth-20260707T082834.484151Z`.
- Added regression coverage proving:
  - reverse-flow maps to the local test lane under `codex_workflow_gate`;
  - rnskill maps to the documentation lane under `generic_skill_workflow`;
  - Agents-A1, Fundamental-Ava, and Shepherd remain `agent_harness_eval_required`;
  - raw URLs, replay commands, installs, provider runtime, external harness execution, and remote execution remain unexported or denied.
- Updated `docs/skill-route-discovery.md` with the new replay surface.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260707T082834
```

Result: passed, `1 passed, 368 deselected`.

## Review Notes

- No upstream code was cloned, installed, executed, or imported.
- No provider runtime, external harness, remote execution, profile write, or memory write was enabled.
- The self-model was read and left unchanged because its current preference already matches this run: direct local evolution is acceptable when rollback-backed, locally validated, and bounded away from offensive behavior and privacy leakage.
