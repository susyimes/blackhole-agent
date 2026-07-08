# Provider Runtime Control Pass 2

- Source digest: `github-growth-20260708T024637.613270Z`
- Branch: `codex/blackhole-evolve/20260708T024721.722474-add-or-run-a-bounded-local-skill-route-discovery`
- Rollback artifact: `artifacts/rollback/20260708T024721Z-skill-route-discovery-pass2-provider-runtime-control/rollback-point.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260708T024721Z-skill-route-discovery-pass2-provider-runtime-control`
- Self-model: unchanged

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository presents a Codex/AI Agent skill workflow with `skills/reverse-flow`, `SKILL.md`, local sandbox framing, staged workflow, diagnostic scripts, and install/runtime wording.
- `https://github.com/Pluviobyte/rnskill`: public repository presents a generic skill collection with `SKILL.md`-style skills, docs, tools, marketplace metadata, and install/enable examples.
- `https://github.com/shepherd-agents/shepherd`: public repository presents a reversible agent runtime substrate with trace, fork, replay, revert, and supervision claims.

## Hypothesis

The active provider-runtime-control pass should not create another standalone skill-route fixture only. The useful operator-visible improvement is to project provider/runtime pressure from the skill-route gate into body-free diagnostics and recovery hints, while preserving the existing bounded local lanes and denying runtime activation.

## Change

- Added `skill_route_discovery_current_pass2_provider_runtime_control` inside the existing `skill_route_discovery_current_pass2_scope_recompute_gate`.
- The panel reports `provider_runtime_preflight_sample_missing` when runtime/provider pressure is present but no body-free preflight sample is attached.
- The panel exports recovery hint codes and replay command hashes only.
- Provider launch, external harness execution, remote execution, raw provider config, raw provider diagnostics, raw source URLs, raw evidence URLs, raw replay commands, and upstream bodies remain denied.
- Added a focused fixture for `github-growth-20260708T024637.613270Z`.
- Documented the pass-2 diagnostic behavior in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260708T024637 or current_pass2_scope_recompute_gate"`: `2 passed, 403 deselected`
- `python -m pytest tests/test_skill_routing.py -q`: `405 passed`
- `python -m pytest tests/test_docs_contracts.py -q`: `26 passed`

## Review Notes

- No external skill activation, install, upstream code execution, provider launch, external harness execution, remote execution, promotion, restart, profile write, or memory write was performed.
- `docs/self-model.md` was left unchanged because it already says to prefer rollback-backed, locally validated behavior improvements and this run had a concrete controller behavior path.
