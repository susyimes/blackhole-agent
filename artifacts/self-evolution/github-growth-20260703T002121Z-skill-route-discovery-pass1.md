# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260703T002121.806126Z`
- Capability slice: `skill-route-discovery`, pass 1 of 4
- Rollback ref: `refs/rollback/blackhole-evolve-20260703T002121Z`
- Evidence reviewed:
  - `https://github.com/baojunxiong/reverse-flow-skill`
  - `https://github.com/lingbol088-spec/reverse-flow-skill`
  - `https://github.com/minxiang0101/reverse-flow-skill`
  - `https://github.com/lyra81604/zhengxi-views`

Hypothesis: reverse-flow-style Codex skill repositories should become a
bounded local skill-route validation lane before any workflow or code adoption.
The reusable lesson is the route shape, not external installation, runtime
execution, provider launch, or activation.

Change:

- Added a digest-specific pass-1 branch for
  `github-growth-20260703T002121.806126Z` in the skill-route lane builder.
- Added
  `tests/fixtures/skill_route_discovery/current_digest_20260703T002121_pass1_validation_lane.json`
  with three reverse-flow skill-route rows, zhengxi-views, general-agent rows,
  and workflow-only adjacent evidence.
- Added a regression test asserting reverse-flow rows select
  `skill_route_discovery` with only documentation, config, test, or code_patch
  allowed lanes, while general-agent and workflow-only evidence remains behind
  `agent_harness_eval_required`.
- Documented the current digest interpretation in
  `docs/skill-route-discovery.md`.

Self-model decision: left unchanged. The current self-model already supports
rollback-backed local experiments and keeps offensive behavior, unauthorized
access, and privacy leakage review-only. This run needed a replayable route
surface rather than a revised self-description.

Validation:

- `python -m py_compile src\blackhole_agent\skill_routing.py`
- `python -m pytest tests/test_skill_routing.py -q -k 20260703T002121`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`

Review notes:

- Reverse-flow evidence is security-adjacent, but this change does not import,
  install, execute, or activate external skill code.
- The pass-1 lane exports body-free route metadata only; raw GitHub URLs,
  replay commands, target paths, upstream bodies, provider launch, external
  harness execution, remote execution, profile writes, and memory writes remain
  denied.
- Workflow-only and general-agent evidence does not inherit
  `skill_route_discovery`; local harness evaluation is still required before
  documentation, test, or code_patch follow-up lanes are selected.
