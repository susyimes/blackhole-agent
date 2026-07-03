# Skill Route Discovery Pass 1 Current Window

Source digest: `github-growth-20260703T221922.915909Z`
Capability slice: `skill-route-discovery`
Branch: `codex/blackhole-evolve/20260703T222021.995688-create-or-extend-a-local-skill-route-discovery-v`
Rollback artifact: `artifacts/rollback/20260703T221922Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package evidence with a `skills/reverse-flow` layout, workflow language, install examples, and local sandbox/CTF framing. Interpreted as Codex workflow-gate evidence only.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill workflow evidence with source-cited/research framing and advice-boundary metadata. Interpreted as generic/source-cited skill workflow evidence only.
- `https://github.com/Forsy-AI/agent-apprenticeship`: public general-agent workflow-loop project without a local skill-route hint. Kept behind agent-harness evaluation.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general-agent/world-model project without a local skill-route hint. Kept behind agent-harness evaluation.

## Hypothesis

The current digest repeats a well-observed pattern: skill-like public repositories can produce local validation candidates, while general agent projects need a separate harness-eval lane. The useful improvement is to make the new digest window operator-visible in the existing controller surface instead of relying on older digest aliases.

## Local Change

- Added a current-digest pass-1 lane for `github-growth-20260703T221922.915909Z`.
- Bound `p1-skill-route-discovery-codex-workflow` to the local `test` lane with `skill_route_discovery_first`.
- Bound `p2-generic-skill-workflow-discovery` to the local `documentation` lane.
- Bound `p4-route-metadata-consistency-check` to a local `test` lane covering route hints, profiles, selected item IDs, and bounded lanes.
- Kept agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava behind `p3-agent-harness-eval-for-general-agent-projects`.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260703T221922
python -m pytest tests/test_skill_routing.py -q
python -m ruff check src\blackhole_agent\skill_routing.py tests\test_skill_routing.py
python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery
```

All commands passed.

## Review Notes

- Runtime action remains `none`.
- External skill activation, external agent activation, external harness execution, provider launch, remote execution, profile writes, and memory writes remain disabled.
- Controller outputs remain body-free: no raw source URLs, replay commands, target paths, evidence URLs, or upstream bodies are exported from the lane.
- `docs/self-model.md` was read and left unchanged because this run exercised its existing preference for rollback-backed, validated behavior change.
