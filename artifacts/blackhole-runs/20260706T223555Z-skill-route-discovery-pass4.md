# Skill Route Discovery Pass 4

- Source digest: `github-growth-20260706T223555.499005Z`
- Theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260706T223652.924540-add-or-extend-a-local-agent-harness-evaluation-m`
- Rollback ref: `refs/rollback/blackhole-evolve-20260706T223555-pass4`
- Rollback artifact: `artifacts/rollback/20260706T223555Z-skill-route-discovery-pass4/rollback-point.md`

## Evidence Interpretation

The carried reverse-flow evidence is a skill workflow route signal because the
digest describes a Codex/AI Agent package shape with `skills/reverse-flow`,
`SKILL.md`, references, scripts, local sandbox defaults, CTF/crackme framing,
and install or run wording. It remains a local test-lane candidate only; install,
run, script, provider, runtime, and external harness pressure is diagnostic.

The carried Agents-A1, Qwen-AgentWorld, Fundamental-Ava, and Shepherd evidence is
general-agent project evidence. Without an explicit skill workflow route hint and
without a local harness result, those rows enter `agent_harness_eval_required`
and expose no direct local implementation lane.

## Local Change

The current digest now routes through the existing
`current_digest_pass4_completion_handoff` surface. The handoff emits:

- `p2-skill-route-discovery-for-reverse-flow` in the bounded local test lane.
- `p1-agent-harness-eval-matrix` for general-agent project rows.
- `p3-trend-routing-decision-doc` for the operator-visible policy note.

The added fixture is body-free and replays only selected item IDs, route
metadata, lane names, and hashed replay commands.

## Validation

Planned focused validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260706T223555
```

Expected safety properties:

- External skill activation remains false.
- External agent activation remains false.
- External harness execution remains false.
- Provider launch and remote execution remain false.
- Raw source URLs, raw evidence URLs, upstream bodies, and raw replay commands are not exported.
