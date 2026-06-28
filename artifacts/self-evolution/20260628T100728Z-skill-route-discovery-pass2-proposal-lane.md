# Skill Route Discovery Pass 2 Proposal Lane

- Source digest: `github-growth-20260628T100729.595957Z`
- Capability window: `skill-route-discovery`, pass 2 of 4
- Rollback artifact: `artifacts/rollback/20260628T100728Z-skill-route-discovery-pass2.md`
- Rollback ref: `refs/rollback/20260628T100728Z-skill-route-discovery-pass2`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public skill repository with `SKILL.md`, `skill.yml`, `evals`, `references`, and `scripts`; repository README frames the behavior as source-cited research with an investment-advice boundary.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public Three.js game skill package with director/sibling skills, scaffold helpers, QA/release scripts, browser checks, mobile checks, and provider asset-generation boundaries.
- `https://github.com/dongshuyan/compass-skills`: public local-first skill ecosystem with `skills/`, `AGENTS.md`, `skills.sh.json`, task memory, session handoff, user profile, and explicit local/privacy boundaries.

## Hypothesis

The active pass-2 proposal aliases should become one operator-visible local lane
before activation. That lane should map zhengxi-views, Three.js Game Skills,
and COMPASS Skills to bounded local lanes while keeping adjacent general-agent
evidence in agent-harness evaluation only.

## Change

- Added `current_active_pass2_proposal_lane` to the skill-route proposal lane map.
- Added a frozen fixture for this wake's active proposal aliases and adjacent Qwen-AgentWorld evidence.
- Added a focused regression test for proposal alias routing, selected local lanes, adjacent eval-only handling, and hash-only serialization.
- Documented the new pass-2 surface in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_active_pass2_proposal_lane`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`

All validation passed.

## Review Notes

- No self-model edit was made. The existing self-model already prefers reversible, locally validated behavior changes over validation-report-only work.
- The new surface exports proposal IDs, aliases, selected item IDs, source hashes, bounded lanes, validation gates, and replay-command hashes only.
- Runtime action, install, upstream skill or agent activation, external harness execution, provider launch, profile writes, memory writes, remote execution, raw source URLs, raw evidence URLs, target paths, replay-command bodies, and upstream bodies remain denied.
