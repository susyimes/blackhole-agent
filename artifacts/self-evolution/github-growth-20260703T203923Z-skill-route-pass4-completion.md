# Skill Route Discovery Pass 4 Completion

- Source digest: `github-growth-20260703T203923.819609Z`
- Theme: `skill-route-discovery`
- Rollback ref: `refs/rollback/blackhole-agent/20260703T203923-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260703T203923-skill-route-discovery-pass4/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository exposes a Codex / AI Agent reverse-flow skill layout with `skills/reverse-flow`, local sandbox or CTF workflow framing, and install/script examples. This supports a local route-discovery probe only; upstream install or runtime wording is not activation authority.
- `https://github.com/lyra81604/zhengxi-views`: public repository describes source-cited research skill material and an explicit non-investment-advice boundary. This supports documentation-lane route interpretation with citation/advice boundary metadata.
- `https://github.com/Forsy-AI/agent-apprenticeship`: public repository describes agent workflow loops, mentor/human evaluation, and reusable experience. Without a local harness result, it remains adjacent `agent_harness_eval_required` evidence rather than a direct skill-route lane.

## Local Change

The current digest pass-4 handoff now recognizes
`github-growth-20260703T203923.819609Z` and emits an operator-visible
`current_digest_pass4_completion_handoff`.

The handoff maps:

- `p3-codex-skill-workflow-probe` to the local `test` lane with
  `skill_route_discovery_first`.
- `p2-skill-route-discovery-zhengxi` to the `documentation` lane.
- `p1-agent-harness-eval-general-trends` to `agent_harness_eval_required`,
  with no direct lanes before local harness evaluation.

Runtime action, external skill or agent activation, external harness execution,
provider launch, remote execution, raw source URL export, raw replay command
export, target path export, and upstream body export remain denied.

## Validation

Validation run:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260703T203923
```

Result: passed, 1 test selected.

Broader routing validation:

```powershell
python -m pytest tests/test_skill_routing.py -q
```

Result: passed, 229 tests.

The self-model was read and left unchanged. Its current preference already
matches this pass: direct local behavior improvement is preferred when
rollback-backed and locally validated, while external activation remains denied.
