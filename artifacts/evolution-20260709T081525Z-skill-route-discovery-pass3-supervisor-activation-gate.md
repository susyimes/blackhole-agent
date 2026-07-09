# Evolution Run: Skill Route Discovery Pass 3 Supervisor Activation Gate

- Source digest: `github-growth-20260709T081527.210846Z`
- Capability window: `skill-route-discovery`, pass 3 of 4
- Rollback ref: `refs/rollback/20260709T081525Z-skill-route-discovery-pass3-current-window`
- Rollback artifact: `artifacts/rollback/20260709T081525Z-skill-route-discovery-pass3-current-window/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/Pluviobyte/rnskill`
- `https://github.com/SmileLikeYe/agent-chief`
- `https://github.com/Tencent-Hunyuan/Hy3`

Reusable lesson: public skill-style repositories can expose mixed install,
workflow, docs, tools, scripts, and marketplace metadata, but blackhole-agent
should convert that evidence into bounded local lanes before activation.
General agent orchestration and provider/model evidence stays adjacent until
local harness evaluation or privacy review.

## Hypothesis

A pass-3 supervisor-visible gate for the active digest improves continuity
more than another standalone fixture. It gives the controller a replayable
surface that:

- maps `reverse-flow-skill` to the local `test` lane,
- maps `rnskill` to the local `documentation` lane,
- keeps allowed skill-route lanes to `documentation`, `config`, `test`, and
  `code_patch`,
- holds `agent-chief` behind `agent_harness_eval_required`,
- keeps Hy3 provider preflight review-only because provider config and
  credential handling cross the privacy boundary.

## Self-Model Decision

`docs/self-model.md` was left unchanged. The existing preference already says
to prefer rollback-backed, locally validated behavior changes over report-only
scaffolding while keeping offensive behavior and privacy leakage review-gated.
This run needed an operator-visible controller gate, not a revised
self-description.

## Material Actions

- Added `current_digest_20260709T081527_pass3_supervisor_activation_gate` to
  the skill-route proposal lane map.
- Added a focused test with synthetic current-window evidence for
  reverse-flow, rnskill, agent-chief, and Hy3.
- Updated `docs/skill-route-discovery.md` with the pass-3 replay contract.
- No install, run, provider launch, network provider call, promotion, push,
  restart, or remote execution was performed.

## Validation

Commands run:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260709T081527
python -m pytest tests/test_docs_contracts.py -q
```

Results:

- `tests/test_skill_routing.py -q -k 20260709T081527`: 1 passed, 458 deselected.
- `tests/test_docs_contracts.py -q`: 32 passed.

Raw replay commands are not exported by the controller packet; this artifact
records the local validation command for operator review.
