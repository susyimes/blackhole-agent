# Provider Runtime Skill-Route Control

Source digest: `github-growth-20260620T161207.697144Z`
Capability window: `provider-runtime-control`, pass 4 of 4
Rollback artifact: `artifacts/rollback/20260620T161206Z-provider-runtime-skill-route-control.txt`
Rollback ref: `refs/rollback/20260620T161206Z-provider-runtime-skill-route-control`

## Evidence

The carried proposal set connected skill-route discovery evidence from public
skill/workflow repositories with provider/runtime preflight control. The
relevant evidence URLs were:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/Yunqicc/compass-skills`

No external network fetch was needed during this run. The local repository
already contained replay fixtures and documentation for the skill-route and
provider-runtime-control slice.

## Hypothesis

Provider-runtime samples inside skill-route discovery should distinguish
blocked preflights from degraded-only local replay. A degraded mock/provider
diagnostic can be replayable and useful for recovery, but it must not be
reported as supervisor promotion success.

## Change

- `src/blackhole_agent/harness_eval.py` now marks degraded-only provider-runtime
  recovery summaries as `ready_for_local_replay: true` while keeping
  `ready_for_supervisor_promotion: false`, `degraded_replay_only: true`, and
  `success_claim_allowed: false`.
- The skill-route sample gate exports the same body-free readiness fields so
  operator surfaces can replay diagnostics without launching a provider.
- `tests/fixtures/local_harness_eval/skill_route_discovery_provider_runtime_degraded_sample.json`
  replays a FableCodex-style skill-route candidate with a degraded mock-auth
  provider-runtime sample.
- `docs/skill-route-discovery.md` documents the degraded-only sample behavior.

## Validation

- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`
- `pytest tests/test_harness_eval.py -q -k "provider_runtime_preflight or provider_runtime_recovery_summary or skill_route_discovery_lane"`
- `pytest tests/test_harness_eval.py -q`
- `pytest tests/test_skill_routing.py -q`
- `pytest tests/test_proposal_eval.py -q`
- `pytest tests/test_docs_contracts.py -q`
- `pytest -q`

Final result: `355 passed in 1.89s`.

## Review Notes

The self-model was read and left unchanged. It already matched this run's
preference for rollback-backed, locally validated behavior improvements and did
not add an unsupported permission source.

Blocked provider-runtime samples still block skill-route completion as
`provider_runtime_replay_not_ready`. Degraded-only samples are local replay
signals, not promotion success.
