# Skill Route Discovery Pass 2 Fixture Intake Queue

- Source digest: `github-growth-20260703T211924.184160Z`
- Branch: `codex/blackhole-evolve/20260703T212021.390388-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback point: `artifacts/rollback/20260703T211924Z-skill-route-discovery-pass2/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill layout with `skills/reverse-flow`, local sandbox/CTF framing, scripts, and installation/runtime pressure.
- `https://github.com/lyra81604/zhengxi-views`: generic Agent Skill with source-citation and advice-boundary language, references, evals, and validation scripts.
- `https://github.com/Forsy-AI/agent-apprenticeship`: general agent workflow-loop project with mentor or human evaluation claims.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent benchmark/world-model project with evaluation benchmark claims.

## Hypothesis

Pass-2 skill-route discovery already maps skill repositories into bounded local lanes. The next useful operator surface is a local harness fixture intake queue for adjacent general-agent projects, so those projects can become replayable `agent_harness_eval_lane` work only after a local fixture declares scenario, output, pass/fail signal, rollback, and non-secret config.

## Change

- Added `local_harness_fixture_intake_queue` to `skill_route_discovery_pass2_secondary_harness_checklist`.
- Added per-row `fixture_intake` metadata with source hashes, topic reason codes, missing fixture fields, next local action, and denied implementation/runtime/external execution flags.
- Added a current-digest local harness fixture that asserts the queue blocks Agent Apprenticeship and Qwen-AgentWorld before implementation patches.
- Documented the new pass-2 surface in `docs/skill-route-discovery.md`.

## Validation

Validation was run with `PYTHONPATH=src` because plain `python`/`pytest` in this worktree resolved `blackhole_agent` to the sibling checkout at `C:\Users\svmes\Documents\Playground\blackhole-agent`.

```powershell
$env:PYTHONPATH='src'; pytest tests/test_harness_eval.py -q
```

Result: `236 passed in 2.38s`.

## Review Notes

- No upstream code was cloned or executed.
- Raw source URLs remain represented by hashes inside route output.
- General-agent evidence remains outside `skill_route_discovery` and cannot enable implementation patches, external harness execution, provider launch, or remote execution until local harness fixture evidence exists.
- `docs/self-model.md` was read and left unchanged. Its current preference for locally validated behavior changes over report-only scaffolding matched this run; no new self-description evidence required an edit.
