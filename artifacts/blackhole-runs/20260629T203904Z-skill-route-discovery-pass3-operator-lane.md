# Skill Route Discovery Pass 3 Operator Lane

- Source digest: `github-growth-20260629T203904.306145Z`
- Theme: `skill-route-discovery`
- Capability pass: 3 of 4
- Rollback artifact: `artifacts/rollback-20260629T203903Z-skill-route-discovery-pass3.md`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: skill ecosystem and state-handoff style evidence.
- `https://github.com/lyra81604/zhengxi-views`: generic skill workflow evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`: adjacent general-agent evaluation evidence.
- `https://github.com/ksimback/looper`: adjacent general-agent loop/evaluation evidence.

## Hypothesis

The current pass should expose the active proposal names in an operator-visible
pass-3 lane instead of relying on older source-digest aliases. COMPASS-style and
generic skill workflow evidence can be accepted into bounded local test lanes,
while general-agent projects stay adjacent behind local harness-eval criteria.

## Local Change

- Added `github-growth-20260629T203904.306145Z` handling to
  `current_source_digest_pass3_operator_lane`.
- Added a fixture for the current digest.
- Added route tests proving:
  - COMPASS evidence maps to `p1-skill-route-discovery-compass-skills`.
  - Generic skill workflow evidence maps to
    `p2-skill-route-discovery-generic-skill-workflow`.
  - Qwen-AgentWorld and looper remain `agent_harness_eval_required`.
  - Allowed local lanes exclude install, provider runtime, and runtime execution.
- Updated `docs/skill-route-discovery.md` with the pass-3 operator lane note.

## Validation

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k "20260629T203904 or current_source_digest_pass3_operator_lane"
```

Result: `2 passed, 111 deselected`.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q
```

Result: `113 passed`.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_contracts.py -q
```

Result: `11 passed`.

## Review Notes

- Self-model left unchanged. It already favors bounded, rollback-backed local
  behavior improvements; this run did not produce evidence that its structure is
  behavior-shaping enough to revise.
- No external skill activation, provider launch, harness execution, profile
  write, memory write, remote execution, or restart was performed.
