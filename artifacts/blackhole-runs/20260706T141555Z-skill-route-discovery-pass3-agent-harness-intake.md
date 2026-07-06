# Blackhole Run: skill-route-discovery pass 3 agent harness intake

- Branch: `codex/blackhole-evolve/20260706T141633.504062-create-or-extend-a-local-agent-harness-evaluatio`
- Source digest: `github-growth-20260706T141555.983852Z`
- Rollback artifact: `artifacts/rollback/20260706T141555Z-skill-route-discovery-pass3-agent-harness-intake.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260706T141555Z-skill-route-discovery-pass3`
- Self-model changed: no

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: skill/workflow repository shape with `skills/reverse-flow`, local sandbox/CTF framing, scripts, and install/run pressure. Interpreted only as bounded skill-route evidence.
- `https://github.com/InternScience/Agents-A1`: general agent/model project with evaluation code, long-horizon trajectories, tool use, and heterogeneous agent abilities. Interpreted as agent-harness-eval evidence before implementation.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime substrate with reversible trace, fork, replay, and retained output review claims. Interpreted as agent-harness-eval evidence before runtime adoption.
- `https://github.com/shepherd-agents/shepherd/pull/24`: merged controller extraction and strict typecheck gate activity. Interpreted as local harness evaluation pressure, not direct adoption authority.

## Hypothesis

The existing route-family matrix separates skill/workflow rows from adjacent general-agent projects, but pass 3 needs an operator-visible bridge into concrete local harness intake. A body-free `route_family_agent_harness_intake` surface should make the next action explicit: declare or validate the required `agent_harness_eval_lane` project-shape fields before any documentation, test, or code_patch follow-up is considered for general-agent trends.

## Changes

- Added `skill_route_discovery_route_family_agent_harness_intake` to `skill_route_discovery_lane` output.
- Added a current-digest pass-3 fixture for reverse-flow plus Agents-A1/Qwen-AgentWorld/Fundamental-Ava/Shepherd mixed evidence.
- Added a focused regression test and updated the local harness fixture-suite count.
- Documented the new intake surface in `docs/architecture.md` and `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest_20260706T141555_pass3_agent_harness_intake or skill_route_discovery_20260706_pass1_route_family_eval_matrix or agent_harness_eval_lane"`: passed, 5 passed.
- `python -m pytest tests/test_harness_eval.py::test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs -q`: passed, 1 passed.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 11 passed.
- `python -m ruff check src\blackhole_agent\harness_eval.py tests\test_harness_eval.py`: passed.
- `python -m black src\blackhole_agent\harness_eval.py tests\test_harness_eval.py`: not run; `black` is not installed in this environment.
- `python -m ruff format src\blackhole_agent\harness_eval.py tests\test_harness_eval.py`: attempted, then reverted because it rewrote unrelated formatting across the files. Final diff keeps only the intended local edits and passes `ruff check`.

## Review Notes

- No upstream repository was cloned, installed, executed, or activated.
- The new intake queue exports hashes and route metadata only; raw source URLs and upstream bodies remain omitted from evaluator output.
- General-agent rows remain blocked before local harness probe fields exist and do not inherit `skill_route_discovery`.
