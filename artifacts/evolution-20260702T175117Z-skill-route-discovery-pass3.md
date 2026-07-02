# Skill Route Discovery Pass 3

- Branch: `codex/blackhole-evolve/20260702T175217.343633-add-a-bounded-local-skill-route-discovery-valida`
- Source digest: `github-growth-20260702T175118.267162Z`
- Rollback artifact: `artifacts/rollback-20260702T175117Z-skill-route-discovery-pass3.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260702T175117Z-skill-route-discovery-pass3`
- Self-model: read and left unchanged. The current text already favors rollback-backed, locally validated behavior changes, and this run had stronger evidence for a route-controller surface than for revising descriptive self-text.

## Focused Evidence

- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill shape with `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation workflow, and non-investment-advice boundaries. Used only as bounded skill-route evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/ksimback/looper`: general-agent or loop-harness project evidence without skill-route activation. Kept behind local agent-harness evaluation.
- Workflow-only usecase evidence remains a route-boundary note: workflow topics without skill-route hints do not grant runtime workflow adoption.

## Hypothesis

The active pass-3 slice should expose an operator-visible activation-review lane for the current digest rather than another standalone fixture. The lane should keep zhengxi-views bounded to local skill-route validation, route general-agent projects through `agent_harness_eval_required`, and record workflow-only evidence as documentation triage with no runtime authority.

## Changes

- Added `github-growth-20260702T175118.267162Z` handling to `current_digest_pass3_activation_review_lane`.
- Added direct and local-harness fixtures for the pass-3 current digest.
- Added regression assertions for bounded skill-route lanes, adjacent agent-harness gating, workflow-only documentation triage, and body-free denial flags.
- Documented the current digest pass-3 route boundary.

## Validation

Passed:

- `python -m pytest tests/test_skill_routing.py -q -k 20260702T175118`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_harness_eval.py -q -k 20260702T175118`
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures`
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`

## Review Notes

- No upstream repository code, external skill, agent, provider, harness, or workflow was executed.
- Raw source URLs, evidence URLs, replay commands, target paths, upstream bodies, profile writes, memory writes, provider launch, external harness execution, remote execution, external skill activation, and external agent activation remain denied by the new surface.
