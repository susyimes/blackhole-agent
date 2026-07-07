# Evolution Run: skill-route-discovery pass 1 validation lane

- Source digest: `github-growth-20260707T160109.409581Z`
- Branch: `codex/blackhole-evolve/20260707T160211.073696-add-or-refine-local-tests-that-exercise-skill-ro`
- Rollback artifact: `artifacts/rollback/20260707T160107Z-skill-route-discovery-pass1/rollback-point.md`
- Rollback ref: `refs/blackhole-rollback/20260707T160107Z-skill-route-discovery-pass1`

## Evidence

The current window carries skill-route evidence for `reverse-flow-skill` and
`rnskill`, plus adjacent general-agent evidence for `Agents-A1`,
`Fundamental-Ava`, and `shepherd`. The reusable lesson is to expose a bounded,
operator-visible pass-1 packet before activation: skill-oriented repositories
may become documentation, config, test, or code_patch lanes after local
validation, while general-agent projects require an agent-harness evaluation
before any implementation lane is selected.

## Change

- Added `skill_route_discovery_current_digest_20260707T160109_pass1_validation_lane`.
- Added a frozen fixture for the current digest.
- Added focused regression coverage proving:
  - reverse-flow-style Codex workflow evidence selects the local test lane;
  - generic skill collection evidence selects the documentation lane;
  - general-agent projects remain `agent_harness_eval_required`;
  - raw URLs, replay commands, runtime lanes, provider lanes, memory writes, and
    activation routes stay out of controller output.
- Documented the pass-1 route interpretation in `docs/skill-route-discovery.md`.

The self-model was left unchanged because it already states the active
preference for rollback-backed local validation over ornamental self-model
edits.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T160109`
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T160109 or 20260707T150109 or 20260707T154109"`

Both validation commands passed.
