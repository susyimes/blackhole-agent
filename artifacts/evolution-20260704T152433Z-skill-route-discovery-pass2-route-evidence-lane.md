# Evolution Run: skill-route-discovery pass 2 route evidence lane

Source digest: `github-growth-20260704T152434.856651Z`
Branch: `codex/blackhole-evolve/20260704T152532.150242-add-or-extend-local-tests-for-skill-route-discov`
Rollback ref: `refs/blackhole-rollback/20260704T152433Z-skill-route-discovery-pass2-route-evidence-lane`
Rollback artifact: `artifacts/rollback/20260704T152433Z-skill-route-discovery-pass2-route-evidence-lane/rollback-point.md`

## Evidence And Hypothesis

The carried reverse-flow-skill and zhengxi-views evidence supports skill-route
discovery, but it should not become upstream skill activation or generic
repository-label routing. Pass 2 should expose an operator-visible lane source
that proves selected skill-route rows came from controller-owned `route_hints`
and `route_classification`.

Narrow external evidence review:

- `https://github.com/ChenJsonx/reverse-flow-skill` is a public fork of
  `lingbol088-spec/reverse-flow-skill` and presents a Codex/AI Agent skill
  package with local CTF reverse-analysis workflow, install instructions, and
  scripts.
- `https://github.com/lingbol088-spec/reverse-flow-skill` presents the same
  reverse-flow skill package lineage.
- `https://github.com/lyra81604/zhengxi-views` presents an Agent Skill package
  with source-cited research/advice-boundary framing.
- `https://github.com/QwenLM/Qwen-AgentWorld` presents a general-agent project,
  so it remains adjacent harness-eval evidence rather than inheriting
  `skill_route_discovery`.

## Change

- Added `current_pass2_route_evidence_lane_source` to `current_pass2_lane_handoff`.
- The packet records item IDs, route hints, route class, reasons, route profiles,
  selected local lane, allowed local lanes, and denial booleans.
- Added regression coverage for reverse-flow and mixed skill workflow fixtures.
- Documented the pass-2 interpretation in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_proposal_eval.py -q -k "pass2_route_evidence_lane_source or reverse_flow_skill_route_probe or skill_route_discovery_enforces_lanes_refs_limits_and_uncertainty or route_hint_lane_map_is_bounded_metadata_only_for_skill_discovery"`: passed, 4 tests.
- `python -m pytest tests/test_proposal_eval.py -q -k "current_pass2_lane_handoff or skill_route_discovery"`: passed, 4 tests.
- `python -m pytest tests/test_proposal_eval.py -q`: passed, 30 tests.

## Review Notes

- Self-model was read and left unchanged; its current preference already matches
  this rollback-backed local behavior change.
- The new surface is metadata-only. It does not install, execute, launch
  providers, activate external skills, perform remote execution, export raw
  source URLs, or export upstream bodies.
- `skill_route_discovery_first_required` is true only when the classifier records
  mixed skill workflow pressure; all skill workflow rows still keep
  `skill_route_discovery` as the primary bounded route.
