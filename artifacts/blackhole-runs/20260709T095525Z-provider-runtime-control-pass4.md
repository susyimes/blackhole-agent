# Provider Runtime Control Pass 4

- Source digest: `github-growth-20260709T095527.226935Z`
- Capability theme: `provider-runtime-control`
- Rollback artifact: `artifacts/rollback/20260709T095525Z-provider-runtime-control-pass4/rollback-point.md`
- Rollback ref: `refs/blackhole-rollback/20260709T095525Z-provider-runtime-control-pass4`

## Evidence Review

Reviewed the carried evidence URLs only:

- `lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill package with `skills/reverse-flow/SKILL.md`, local sandbox framing, staged workflow, and diagnostic scripts.
- `Pluviobyte/rnskill`: generic SKILL.md-compatible skill collection with docs/tools/metadata signals.
- `Tencent-Hunyuan/Hy3` issue and PR evidence: API quickstart plus MCP server pressure, not a skill package route.

## Change

Added `current_digest_20260709T095527_pass4_provider_runtime_recovery_handoff`
to the skill-route lane map. The handoff closes this slice with an
operator-visible recovery workflow: skill-route rows stay bounded to local
lanes, general-agent rows require harness eval, and Hy3-style provider/MCP
evidence becomes body-free recovery hints and replay-command hashes only.

The self-model was left unchanged because its existing preference already
covers rollback-backed local evolution and the narrow safety boundary. This
run needed an operator surface, not a new self-description.

## Validation

Planned focused validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260709T095527
```

## Review Notes

- No provider, MCP server, external harness, network runtime, promotion, push, or restart was launched.
- Raw provider config, secret values, evidence URLs, replay commands, target paths, and upstream bodies remain unexported by the packet.
