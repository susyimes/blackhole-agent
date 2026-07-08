# Skill Route Discovery Pass 3

Source digest: `github-growth-20260708T143852.130540Z`

Branch: `codex/blackhole-evolve/20260708T144001.514858-add-or-extend-a-local-skill-route-discovery-vali`

Rollback:

- Ref: `refs/rollback/blackhole-evolve/20260708T143849Z-skill-route-discovery-pass3`
- Artifact: `artifacts/rollback/20260708T143849Z-skill-route-discovery-pass3/rollback-point.md`

Evidence reviewed:

- `https://github.com/Pluviobyte/rnskill`
- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/shepherd-agents/shepherd`
- `https://github.com/shepherd-agents/shepherd/pull/40`

Hypothesis:

The current digest should produce an operator-visible pass-3 lane that maps explicit skill/workflow evidence to bounded local lanes and keeps adjacent general agent/runtime evidence in `agent_harness_eval_required` until local harness validation exists.

Change:

- Added `github-growth-20260708T143852.130540Z` routing to the existing pass-3 reverse-flow/rnskill validation surface.
- Added a frozen current-digest fixture covering reverse-flow skill evidence, rnskill generic skill evidence, Shepherd task/workspace syntax pressure, Hy3 provider pressure, and Blender/Seedance workflow pressure.
- Added a regression test that verifies bounded local skill lanes, Shepherd holdback, rollback metadata, and non-exported raw activation surfaces.

Self-model decision:

`docs/self-model.md` was left unchanged. It already prefers rollback-backed local validation over report-only evolution, which matches this run.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T143852`
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T131852 or 20260708T143852 or current_digest_pass3_route_to_validation"`
- `python -m pytest tests/test_skill_routing.py -q`

Review notes:

- No external skill activation, external harness execution, provider runtime launch, restart, promotion, push, or remote execution was performed.
- The upstream evidence was treated as public route evidence only; raw source URLs are not exported in the generated lane payload.
