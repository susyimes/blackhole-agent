# skill-route-discovery pass 1 run notes

- Source digest: `github-growth-20260706T054239.844393Z`
- Branch: `codex/blackhole-evolve/20260706T054331.222137-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/blackhole/rollback/20260706T054237Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260706T054237Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence And Hypothesis

The active window combines one explicit Codex/AI Agent skill workflow exemplar
(`lingbol088-spec/reverse-flow-skill`) with generic agent repositories
(`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd`).

Hypothesis: the reusable `skill_route_discovery_validation_route_packet` is the
right operator-visible pass-1 surface. It can validate that reverse-flow enters
only documentation, config, test, or code_patch lanes, while general agent
repositories require `agent_harness_eval_required` and expose no direct
runtime or code_patch route before local harness evaluation.

## Changes

- Added `tests/fixtures/skill_route_discovery/current_digest_20260706T054239_pass1_validation_lane.json`.
- Added a focused regression in `tests/test_skill_routing.py` for the mixed
  evidence packet.
- Added the current digest policy note to `docs/skill-route-discovery.md`.

## Material Actions

- Created rollback git ref with `git update-ref`.
- Read `docs/self-model.md`; left it unchanged because it already supports the
  selected rollback-backed, locally validated behavior path.
- Did not clone, install, run, or activate any upstream repository.
- Did not launch providers, external harnesses, remote execution, profile
  writes, or memory writes.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T054239`
  - Result: passed, `1 passed, 324 deselected`.
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: passed, `325 passed`.
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: passed, `11 passed`.

## Review Notes

- The generic pass-1 lane intentionally blocks absent route profiles for this
  digest; this run therefore validates the reusable route packet rather than
  forcing unrelated profile rows to appear ready.
- Upstream evidence was treated as body-free route metadata only. Raw upstream
  bodies and raw evidence URLs are not exported by the packet assertion.
