# Skill Route Discovery Pass 1 Local Validation Lane

- Source digest: `github-growth-20260630T032714.526268Z`
- Capability slice: `skill-route-discovery`
- Proposal focus: `p1-skill-route-discovery-zhengxi-views`
- Rollback artifact: `artifacts/self-evolution/github-growth-20260630T032714Z-rollback.md`

## Evidence Review

The carried evidence URLs were reviewed only enough to identify route shape.
`zhengxi-views` has public Agent Skill package signals and is treated as bounded
skill-route evidence. `Qwen-AgentWorld` and `looper` are general agent projects,
so they remain adjacent `agent_harness_eval_required` evidence. `open-reverselab`
is security-adjacent reverse-engineering context and is recorded as review-only
at the offensive-behavior boundary.

## Local Change

The current digest now has a replayable pass-1 validation lane. It maps
`zhengxi-views` to the local test lane with allowed outputs limited to
documentation, config, test, and code_patch. The adjacent general-agent rows use
`p2-agent-harness-eval-agentworld` and `p3-general-agent-routing-coverage` and
deny runtime execution, direct code_patch, provider launch, external harness
execution, profile writes, memory writes, and remote execution before local
harness evaluation.

## Validation Plan

Run:

```powershell
pytest tests/test_harness_eval.py -q -k 20260630T032714
```

The broader local harness fixture inventory should continue to pass after its
fixture count is updated for this replay case.
