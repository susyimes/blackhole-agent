# Evolution Run: skill-route-discovery pass 2

- Source digest: `github-growth-20260707T162109.466559Z`
- Branch: `codex/blackhole-evolve/20260707T162143.430557-run-a-bounded-local-skill-route-discovery-lane-f`
- Rollback ref: `refs/rollback/blackhole-agent/20260707T162109Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260707T162109Z-skill-route-discovery-pass2/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: skill-shaped Codex/Agent workflow with `skills/reverse-flow`, local sandbox framing, install examples, and script examples. Treated as route pressure only.
- `https://github.com/Pluviobyte/rnskill`: generic Agent Skills collection with `skills`, docs, tools, marketplace metadata, and install examples. Treated as generic skill workflow evidence, not an installable package.
- `https://github.com/InternScience/Agents-A1`: general agent/model/evaluation project. Held behind local agent harness evaluation.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime substrate with reversible traces and supervision claims. Held behind local agent harness evaluation.

## Hypothesis

The active pass-2 slice needs a supervisor-visible recovery workflow tied to the current digest, not another standalone fixture. If the checkpoint exposes rollback, route recomputation, bounded skill replay, adjacent harness gating, and activation boundary phases as body-free metadata, the next scheduled pass can reason about activation readiness without importing upstream skill code or launching agent runtimes.

## Changes

- Added current-digest proposal binding for `github-growth-20260707T162109.466559Z`.
- Added `current_pass2_activation_recovery_workflow` inside `current_pass2_activation_checkpoint`.
- Added a regression test for the current digest and recovery workflow contract.
- Documented the pass-2 recovery workflow in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_proposal_eval.py -q -k "20260707T162109 or current_pass2_activation_checkpoint or skill_route_discovery"`: passed, 6 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route`: passed, 8 tests.
- `python -m pytest tests/test_proposal_eval.py -q`: passed, 35 tests.
- `git diff --check`: passed with line-ending warnings only.

## Review Notes

- The self-model was read and left unchanged. It already matches the current run policy and would be ornamental for this change.
- The new recovery workflow does not execute rollback, restart the kernel, promote/push, launch providers, run external harnesses, export raw upstream URLs, or export raw replay commands.
- Adjacent general-agent projects remain blocked until local `agent_harness_eval` evidence exists.
