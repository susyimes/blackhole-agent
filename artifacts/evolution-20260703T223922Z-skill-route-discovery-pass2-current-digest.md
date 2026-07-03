# Skill Route Discovery Pass 2 Current Digest

Source digest: `github-growth-20260703T223922.916308Z`

## Hypothesis

Current Codex-oriented skill workflow evidence should produce an operator-visible
bounded local lane before activation. Generic agent-project trend evidence from
the same digest should remain adjacent `agent_harness_eval_required` work until
a local harness fixture is declared.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI
  Agent skill package with local sandbox and workflow-gate framing.
- `https://github.com/Forsy-AI/agent-apprenticeship`: broader agent workflow
  loop and mentor-evaluation project, not a local skill workflow route by
  itself.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent world-model and
  benchmark project, not a local skill workflow route by itself.

## Change

- Added the current digest `20260703T223922` as an explicit pass-2
  skill-route-discovery window.
- Added a local harness fixture proving `reverse-flow-skill` maps to the
  `codex_workflow_gate` test lane, `zhengxi-views` maps to the documentation
  lane, and Agent Apprenticeship plus Qwen-AgentWorld remain blocked in the
  secondary harness fixture intake queue.
- Updated the local eval aggregate and focused regression coverage.
- Documented the current-digest pass-2 interpretation rule.

## Rollback

Rollback ref:
`refs/blackhole-rollback/20260703T223922-skill-route-discovery-pass2`

Rollback artifact:
`artifacts/rollback/20260703T223922Z-skill-route-discovery-pass2-current-digest.md`

## Validation

Attempted local checks:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_harness_eval.py -q -k 20260703T223922
$env:PYTHONPATH='src'; python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or 20260703T223922"
```

The focused pytest command timed out during the large `tests/test_harness_eval.py`
module run after both 120 seconds and 300 seconds in this environment.

Completed local checks:

```powershell
$env:PYTHONPATH='src'; <direct evaluator assertion script for tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260703T223922_pass2_fixture_intake_queue.json>
$env:PYTHONPATH='src'; python -m py_compile src/blackhole_agent/skill_routing.py src/blackhole_agent/harness_eval.py tests/test_harness_eval.py
```

Direct evaluator result:

```json
{
  "route_status": "passed",
  "lane_status": "ready",
  "proposal_ids": [
    "p1-skill-route-discovery-codex-workflow",
    "p2-generic-skill-workflow-route-discovery"
  ],
  "selected_local_lanes": ["documentation", "test"],
  "agent_harness_eval_required_count": 2,
  "fixture_report": {"fixture_count": 1, "pass_count": 1, "fail_count": 0}
}
```

## Review Notes

- No self-model edit was made. The current self-model already prefers
  rollback-backed local validation and does not grant permissions.
- No upstream code is installed, cloned, run, or activated.
- Raw source URLs are present only in fixture input evidence and are not exported
  by the evaluated controller surface.
