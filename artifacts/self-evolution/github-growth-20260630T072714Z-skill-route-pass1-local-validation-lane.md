# Skill Route Discovery Pass 1 Local Validation Lane

- Source digest: `github-growth-20260630T072714.658769Z`
- Capability window: `skill-route-discovery`, pass 1 of 4
- Rollback artifact: `artifacts/rollback-20260630T072808Z-skill-route-discovery-pass1-bounded-lanes.md`
- Rollback ref: `refs/blackhole-rollback/20260630T072808Z-skill-route-discovery-pass1-bounded-lanes`

## Evidence Read

- `https://github.com/lyra81604/zhengxi-views` exposes a public Agent Skill-shaped repository with `SKILL.md`, `skill.yml`, references, and scripts.
- `https://github.com/QwenLM/Qwen-AgentWorld` is general-agent evaluation evidence for an agent harness lane.
- `https://github.com/ksimback/looper` is kept as adjacent agent-loop evidence for local harness evaluation in this digest.
- `https://github.com/LING71671/open-reverselab` is automation and reverse-engineering-adjacent evidence, so it remains review-only at the offensive-behavior boundary.

## Hypothesis

The active digest should replay as a pass-1 local validation lane: zhengxi-views maps to bounded `skill_route_discovery` test work, while Qwen-AgentWorld and looper remain `agent_harness_eval_required` and open-reverselab has no route influence beyond review-only context.

## Changes

- Added a digest-specific local harness fixture for `github-growth-20260630T072714.658769Z`.
- Added proposal alias handling for the active hyphenated proposal IDs in the pass-1 lane builder.
- Added direct and aggregate harness regression coverage.
- Documented the pass-1 lane and denial boundary in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged because its current preference already matches this run: reversible local validation, bounded lanes, and review-only handling for offensive/security-adjacent evidence.

## Validation

- `pytest tests/test_harness_eval.py -q -k 20260630T072714` passed.
- `pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs` passed.
- `pytest tests/test_harness_eval.py -q` passed.
- `pytest tests/test_skill_routing.py -q` passed.
- `git diff --check` passed.

## Review Notes

- This change does not install, clone, execute, or activate any upstream repository.
- It does not export raw upstream URLs, replay command bodies, target paths, or upstream bodies through the lane surface.
- It keeps external skill activation, external agent activation, external harness execution, provider launch, remote execution, profile writes, and memory writes denied.
