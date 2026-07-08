# Evolution Run

Run: 20260708T130001Z-skill-route-discovery-pass2-reverse-flow-lane

Source digest: github-growth-20260708T125853.703350Z

Theme: skill-route-discovery, pass 2 of 4

## Evidence Review

- `lingbol088-spec/reverse-flow-skill` is a Codex/AI Agent skill workflow with a `skills/` layout, `SKILL.md`, local sandbox or CTF framing, staged workflow language, install/run examples, and diagnostic scripts. Those are useful workflow-gate signals but remain unsafe as direct activation or execution authority.
- `Pluviobyte/rnskill` is a generic AI Agent Skills collection with `SKILL.md`-compatible workflow evidence, skills, docs, tooling metadata, and manual install examples. It supports documentation-first route validation, not activation.
- `shepherd-agents/shepherd` is a reversible agent runtime substrate. It is adjacent agent-harness evidence, not a skill-route lane, and stays behind local `agent_harness_eval_required`.
- Hy3 and the Blender/Seedance workflow-usecase repository carry provider, MCP, model, and workflow-topic pressure only; they do not inherit `skill_route_discovery`.

## Hypothesis

The active pass should expose the current digest as a replayable pass-2 validation lane using the existing skill-route machinery, while binding this run's proposal IDs and adjacent harness rows explicitly for operator review.

## Rollback

- Rollback artifact: `artifacts/rollback/20260708T130001Z-skill-route-discovery-pass2-reverse-flow-lane/rollback-point.md`
- Rollback ref: `refs/blackhole/rollback/20260708T130001Z-skill-route-discovery-pass2-reverse-flow-lane`

## Material Actions

- Added `github-growth-20260708T125853.703350Z` to the pass-2 skill-route validation lane.
- Added a frozen body-free fixture for reverse-flow, rnskill, Shepherd, Hy3, and Blender/Seedance workflow-usecase evidence.
- Added regression coverage for active proposal IDs, selected local lanes, adjacent agent-harness rows, rollback metadata, and activation denials.
- Updated `docs/skill-route-discovery.md` with the operator-visible replay path.
- Left `docs/self-model.md` unchanged because it already supports rollback-backed local validation and does not need a run-specific rewrite.

## Validation

- `python -m py_compile src\blackhole_agent\skill_routing.py` passed.
- `python -m pytest tests\test_skill_routing.py -q -k 20260708T125853` passed.
- `python -m pytest tests\test_skill_routing.py -q -k "20260708T104635 or 20260708T125853 or 20260708T121852"` passed.
- `python -m pytest tests\test_docs_contracts.py -q -k skill_route_discovery` passed.
- `python -m pytest tests\test_skill_routing.py -q` passed.

## Review Notes

- External review was limited to the carried evidence URLs.
- No external repository was cloned, installed, imported, or executed.
- Runtime action, external skill activation, external agent activation, external harness execution, provider launch, memory/profile writes, promotion, restart, remote execution, raw URLs, raw replay commands, and upstream bodies remain denied in the lane output.
