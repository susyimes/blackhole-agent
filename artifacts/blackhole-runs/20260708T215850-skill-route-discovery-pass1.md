# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260708T215850.675323Z`
- Theme: `skill-route-discovery`
- Rollback ref: `refs/blackhole-rollback/20260708T215850-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260708T215850-skill-route-discovery-pass1.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill repository with a `skills/reverse-flow` layout, staged local reverse-analysis workflow, local sandbox framing, and script examples.
- `https://github.com/Pluviobyte/rnskill`: public SKILL.md-compatible skill collection for Codex, Claude Code, and agent workflows, with skills, docs, tools, and marketplace/install pressure.
- `https://github.com/shepherd-agents/shepherd`: public general agent runtime substrate with reversible trace, fork, replay, retained-output, and supervision claims.

## Hypothesis

Skill/workflow repositories should become bounded local route lanes only after local skill-route discovery confirms their integration shape. Adjacent general-agent runtime projects should remain in `agent_harness_eval_required` until a local harness evaluation exists.

## Local Change

- Added a 215850 pass-1 replay key: `current_digest_20260708T215850_pass1_validation_lane`.
- Reused the existing pass-1 route probe with digest-specific rollback, artifact, and validation metadata.
- Added a focused fixture and regression test for the active reverse-flow/rnskill/Shepherd/Hy3 window.
- Documented the operator-visible replay contract.

## Boundary

No upstream repository was cloned, installed, imported, or executed. External skill activation, external harness execution, provider launch, remote execution, promotion, and restart remain disabled.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260708T215850
```

Result: passed, 1 test passed and 438 deselected.

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260708T203850 or 20260708T215850 or current_run_pass1_activation_readiness"
```

Result: passed, 2 tests passed and 437 deselected.

```powershell
python -m pytest tests/test_skill_routing.py -q
```

Result: passed, 439 tests passed.
