# Skill Route Discovery Pass 1 Automation/Bug Checklist

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill repository metadata includes `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation constraints, and a non-investment-advice boundary.
- `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/ksimback/looper`: adjacent general-agent evidence that requires `agent_harness_eval` before any local follow-up lane.
- `https://github.com/LING71671/open-reverselab`: automation, bug, CTF, reverse-engineering, and MCP-tool evidence. It is useful only as review-gated evaluation pressure; no upstream tools, samples, runners, or automation are executed.

## Hypothesis

The skill-route lane already validates zhengxi-style skill evidence and general-agent adjacency. The missing operator-visible surface is a reusable checklist for automation-or-bug-themed agent evidence so it cannot influence runner, controller, provider, or code-patch behavior before local harness evaluation and safety review.

## Change

- Added `automation_bug_agent_eval_checklist` to the `skill_route_discovery_lane` harness output.
- The checklist hashes names and item IDs, exports no raw URLs or upstream bodies, and requires `agent_harness_eval_lane` replay plus offensive-behavior review.
- The checklist denies runtime action, controller influence, direct code-patch routing, external harness execution, provider launch, and remote execution.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "20260701T211748 or skill_route_discovery_lane"` passed: 11 passed, 198 deselected.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed: 2 passed, 9 deselected.
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs` passed: 1 passed, 208 deselected.
- `python -m pytest tests/test_harness_eval.py -q` passed: 209 passed.
- `git diff --check` passed.
- `python -m pytest tests/test_proposal_eval.py -q -k skill_route_discovery` passed: 4 passed, 21 deselected.

## Review Notes

The change implements no offensive, exploit, malware, phishing, exfiltration, unauthorized-access, reverse-engineering execution, provider launch, or external harness behavior. open-reverselab remains review-only evidence.
