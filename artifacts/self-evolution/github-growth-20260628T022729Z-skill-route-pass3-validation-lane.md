# Skill Route Discovery Pass 3 Validation Lane

Source digest: `github-growth-20260628T022729.498868Z`

Rollback point: `artifacts/rollback/20260628T022825Z-skill-route-discovery-pass3.md`

## Evidence

- `dongshuyan/compass-skills` presents a local skill ecosystem with `skills/`,
  `AGENTS.md`, `skills.sh.json`, and workflow/profile/handoff skill language.
- `lyra81604/zhengxi-views` presents a source-cited agent skill shape with
  citation and advisory-boundary pressure.
- `majidmanzarpour/threejs-game-skills` presents a Three.js/browser-game agent
  skill workflow with QA, scaffold, and optional asset-generation pressure.
- `QwenLM/Qwen-AgentWorld` is general-agent/evaluation evidence, not a skill
  workflow package for direct local activation.

## Hypothesis

The active pass-3 proposal set should produce one operator-visible lane that
keeps external skill-style evidence bounded to local documentation, config,
test, or code_patch validation candidates, while keeping general-agent evidence
behind `agent_harness_eval_required`.

## Change

- Added `current_run_pass3_validation_lane` to the skill-route proposal lane
  map.
- Added a negated-skill-signal guard so summaries like "without skill workflow"
  do not become skill-route candidates without layout or metadata evidence.
- Added a frozen current-run pass-3 fixture and regression test.
- Documented the pass-3 lane and boundary.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_run_pass3_validation_lane`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`

All validation passed.

## Review Notes

- The lane exports hashes and selected item IDs only; raw source URLs, raw
  evidence URLs, target paths, replay commands, and upstream bodies remain out
  of the operator packet.
- No runtime action, external skill activation, external agent activation,
  external harness execution, provider launch, profile write, memory write, or
  remote execution is allowed by this lane.
- The self-model was left unchanged because its current preference already
  matches this run: reversible local evolution with narrow safety review.
