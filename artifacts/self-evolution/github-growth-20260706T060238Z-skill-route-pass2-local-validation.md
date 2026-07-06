# Skill Route Discovery Pass 2 Local Validation

Source digest: `github-growth-20260706T060238.927687Z`
Theme: `skill-route-discovery`
Pass: 2 of 4

## Hypothesis

Mixed RepositoryTrend evidence should become an operator-visible local lane
before activation. Codex skill-workflow evidence can enter
`skill_route_discovery` with bounded local lanes, while general Python agent
projects require `agent_harness_eval_required` before any documentation, test,
or code_patch implementation lane opens.

## Evidence

- `lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow
  shape with `skills/reverse-flow`, `SKILL.md`, references, scripts, local
  sandbox/CTF framing, install examples, run examples, and staged workflow
  language.
- `InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
  `TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd`: general
  agent project or runtime evidence without a local skill-route hint or local
  harness evaluation result.

## Change

- Added a frozen pass-2 digest fixture for the current evidence window.
- Extended the pass-2 lane builder to recognize
  `github-growth-20260706T060238.927687Z` and bind:
  - `p2-skill-route-discovery-reverse-flow-skill` to the local test lane.
  - `p1-agent-harness-eval-trending-python-agents` to
    `agent_harness_eval_required`.
  - `p3-document-routing-boundaries-for-trend-items` to the documentation lane.
- Documented the route boundary and replay command.

## Rollback

Rollback artifact:
`artifacts/rollback/20260706T060237Z-skill-route-discovery-pass2/rollback-point.md`

## Validation

Focused validation passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260706T060238
# 1 passed, 325 deselected

python -m pytest tests/test_skill_routing.py -q -k "20260706T020239 or 20260706T032238 or 20260706T054239"
# 3 passed, 323 deselected

python -m pytest tests/test_docs_contracts.py -q
# 11 passed
```

## Review Notes

- No upstream code is installed, cloned, imported, or executed.
- Raw upstream URLs and replay commands remain omitted from generated lane
  packets.
- Runtime action, provider launch, external harness execution, external skill
  activation, external agent activation, and remote execution remain denied.
- Self-model was read and left unchanged because its current preference already
  matches this run's evidence-backed, rollback-backed local validation change.
