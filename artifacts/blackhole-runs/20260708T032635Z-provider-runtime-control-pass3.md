# Provider Runtime Control Pass 3

Source digest: `github-growth-20260708T032637.752122Z`

Rollback point:
`artifacts/rollback/20260708T032635Z-provider-runtime-control-pass3/rollback-point.md`

Evidence reviewed:
- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill package with `skills/reverse-flow`, `SKILL.md`, local sandbox framing, staged workflow, diagnostic scripts, and install/runtime wording.
- `https://github.com/Pluviobyte/rnskill`: generic `SKILL.md` skill collection for Codex, Claude Code, and other agents, with `skills`, docs, tools, marketplace metadata, and install examples.

Hypothesis:
Provider/runtime pressure from skill workflow trends should become a body-free
operator recovery workflow after the scope recompute gate, not a provider
launch, install, or external execution path.

Change:
- Added `skill_route_discovery_current_digest_20260708T032637_pass3_provider_runtime_recovery_workflow`.
- Added a frozen fixture with reverse-flow, rnskill, Shepherd, and a body-free provider preflight sample.
- Added focused regression coverage for sample readiness, recovery hint resolution, replay hashes, and activation denials.
- Documented the pass-3 operator path in `docs/skill-route-discovery.md`.

Self-model:
Unchanged. The existing self-model already supports rollback-backed local
behavior changes and did not need a new claim for this run.

Validation:
- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k "20260708T032637 or 20260708T024637"` passed.

Review notes:
- The workflow is local-replay-only and success claims remain denied until the
  referenced provider runtime preflight and recovery-summary tests are replayed.
- Raw replay commands, raw source URLs, raw evidence URLs, provider config,
  provider diagnostics, upstream bodies, provider launch, external harness
  execution, remote execution, promotion, push, and restart remain denied.
