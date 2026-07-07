# Self-Evolution Run

- Source digest: `github-growth-20260707T074834.250116Z`
- Capability theme: `skill-route-discovery`
- Pass: 4 of 4
- Rollback point: `artifacts/rollback/20260707T074832Z-skill-route-discovery-pass4-local-skill-route-discovery/rollback-point.md`

## Hypothesis

Reverse-flow-style skill repositories and generic `SKILL.md` collections should
be converted into bounded local lanes before any runtime adoption. General
agent runtime projects, including Shepherd-style reversible execution systems,
should remain queued for local agent-harness evaluation until runnable
entrypoints, isolation, permission boundaries, reproducible tasks, measurable
behavior, and rollback artifacts are present.

## Evidence Reviewed

- `lingbol088-spec/reverse-flow-skill`: public repository shape includes
  `skills/reverse-flow`, `SKILL.md`, local sandbox and CTF framing, an
  activation phrase, install examples, and scripts. Runtime and script wording
  is route pressure only.
- `Pluviobyte/rnskill`: public repository shape includes multiple skills,
  docs, tools, plugin metadata, manual install examples, and `SKILL.md`
  compatible workflow language. Install and plugin wording is route pressure
  only.
- `shepherd-agents/shepherd`: public repository describes reversible,
  reviewable execution traces and retained outputs, which supports an
  agent-harness queue rather than direct controller adoption.

## Change

Added a digest-specific pass-4 local route discovery packet exposed through
`current_digest_pass4_completion_handoff`. The packet records bounded skill
lanes, an adjacent general-agent harness queue, supervisor replay requirements,
and body-free export guards. It performs no install, clone, provider launch,
external harness execution, remote execution, profile write, memory write, or
runtime activation.

## Self-Model

Reviewed `docs/self-model.md` before the change. It already expresses the
current preference for local, rollback-backed, validated evolution and does not
need a revision for this run.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260707T074834
# 1 passed, 367 deselected

python -m pytest tests/test_skill_routing.py -q -k "20260707T072834 or 20260707T074834"
# 2 passed, 366 deselected

python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py
# All checks passed
```
