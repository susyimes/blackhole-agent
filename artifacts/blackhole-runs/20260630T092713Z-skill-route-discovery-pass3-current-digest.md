# Skill Route Discovery Pass 3 Current Digest

- Source digest: `github-growth-20260630T092714.616189Z`
- Rollback ref: `refs/rollback/blackhole-agent/20260630T092713Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260630T092713Z-skill-route-discovery-pass3-current-digest.md`
- External evidence reviewed: `https://github.com/lyra81604/zhengxi-views`

## Hypothesis

The current pass-3 source digest should not fall back to older generic pass-3
proposal aliases. zhengxi-views should remain bounded skill-route evidence, the
route-policy proposal should be explicit as documentation, and Qwen-AgentWorld,
looper, and AgentChat should stay adjacent under `agent_harness_eval_required`
before implementation or runtime action.

## Material Actions

- Created rollback ref before edits.
- Updated the pass-3 activation review builder for
  `github-growth-20260630T092714.616189Z`.
- Added a frozen current-digest fixture for the pass-3 activation review lane.
- Added a focused skill-routing regression test.
- Updated `docs/skill-route-discovery.md` with the operator-visible route
  policy for this digest.

## Validation

- `pytest tests/test_skill_routing.py -q -k 20260630T092714`
- `pytest tests/test_skill_routing.py -q`
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_current_digest`
- `pytest tests/test_docs_contracts.py -q`

## Review Notes

The change grants no external skill activation, external agent activation,
external harness execution, provider launch, remote execution, profile writes,
memory writes, raw source URL export, replay-command export, target-path export,
or upstream-body export. The self-model was read and left unchanged because its
current preference already matches this run's rollback-backed, locally validated
behavior path.
