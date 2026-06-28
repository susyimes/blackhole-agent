# Skill Route Discovery Pass 3 Acceptance Gates

- Source digest: `github-growth-20260628T090729.682480Z`
- Theme: `skill-route-discovery`
- Pass: 3 of 4
- Rollback ref: `refs/rollback/20260628T170919Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260628T170919Z-skill-route-discovery-pass3.md`

## Evidence

The active proposal window carries COMPASS Skills, zhengxi-views, and
Three.js Game Skills as skill-route evidence. It also carries Qwen-AgentWorld
and Looper-style general-agent evidence as adjacent harness-eval candidates.
The local lesson is to convert skill and route evidence into bounded local lanes
that can be checked before activation, not to import or execute upstream skill
or agent projects.

External review was limited to the carried public GitHub evidence pages:
COMPASS Skills exposes skill folders and local workflow/state-handoff skills;
Three.js Game Skills describes browser-game skill workflows with QA and optional
asset pressure; zhengxi-views describes source-cited research/advice-boundary
skill behavior; Qwen-AgentWorld presents a general-agent benchmark/world-model
project rather than a skill workflow route.

## Hypothesis

The pass-3 route lane should expose operator-visible acceptance gates, not only
classification rows. A supervisor can then see whether each proposal is ready
for pass-4 handoff based on bounded lane membership, selected evidence,
validation gates, and denied runtime/external actions.

## Change

- Added body-free local acceptance gates to
  `pass3_active_proposal_acceptance_lane`.
- Failed acceptance gates now become row activation blockers.
- Added top-level acceptance contract readiness, gate names, and failure counts.
- Extended the focused regression and skill-route documentation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k pass3_active_proposal_acceptance_lane`

## Review Notes

- No upstream code was installed, cloned, executed, or imported.
- The self-model was read and left unchanged; it already matches the run's
  rollback-backed, locally validated, non-runtime activation boundary.
- General-agent projects without skill workflow route signals remain outside
  `skill_route_discovery` and require agent-harness evaluation first.
