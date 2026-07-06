# Skill Route Discovery Pass 3: Agent Harness Route Queue

- Source digest: github-growth-20260706T205555.489023Z
- Capability slice: skill-route-discovery
- Rollback ref: refs/blackhole/rollback/20260706T205554Z-skill-route-discovery-pass3
- Rollback artifact: artifacts/rollback/20260706T205554Z-skill-route-discovery-pass3/rollback-point.md

## Evidence Reviewed

- https://github.com/lingbol088-spec/reverse-flow-skill
- https://github.com/InternScience/Agents-A1
- https://github.com/QwenLM/Qwen-AgentWorld
- https://github.com/TianhangZhuzth/Fundamental-Ava
- https://github.com/shepherd-agents/shepherd

## Hypothesis

General agent trend repositories should not directly influence controller or runtime behavior. After local
`agent_harness_eval_lane` replay passes, the controller should expose a bounded, operator-visible follow-up queue that
lists only documentation, test, and code_patch lanes, with the harness replay command attached as validation.

## Safety Decision

The reverse-flow skill evidence is skill-shaped but includes reverse-engineering and local CTF execution pressure. It
remains bounded to discovery, documentation, config, test, or code_patch lanes and does not justify upstream install,
execution, provider launch, remote execution, or runtime activation in this pass.

The general agent evidence supports an offline harness route queue only. No upstream code was cloned or executed.

## Local Change

- Extended `general_agent_project_route_plan` with `post_eval_route_queue`.
- Added a current-digest offline fixture for Agents-A1, Qwen-AgentWorld, Fundamental-Ava, and Shepherd.
- Added focused regression coverage for the post-eval route queue.

## Validation Plan

- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
- `pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass`
