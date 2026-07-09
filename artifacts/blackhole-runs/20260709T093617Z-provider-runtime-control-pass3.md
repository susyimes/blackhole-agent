# Provider Runtime Control Pass 3

- Source digest: github-growth-20260709T093527.363752Z
- Branch: codex/blackhole-evolve/20260709T093617.942654-add-or-extend-local-validation-for-codex-oriente
- Rollback point: artifacts/rollback/20260709T093617Z-provider-runtime-control-pass3/rollback-point.md
- Self-model decision: docs/self-model.md left unchanged because the current preference already supports rollback-backed local validation and the narrow safety boundary.

## Evidence Reviewed

- https://github.com/lingbol088-spec/reverse-flow-skill
- https://github.com/Pluviobyte/rnskill
- https://github.com/Tencent-Hunyuan/Hy3/issues/1
- https://github.com/Tencent-Hunyuan/Hy3/pull/30

## Local Actions

- Added `current_digest_20260709T093527_pass3_provider_runtime_operator_packet` to the skill-route discovery lane map.
- Added a focused regression test for the pass-3 provider-runtime-control packet.
- Updated `docs/skill-route-discovery.md` with the current digest operator behavior.
- Created rollback point artifacts before source edits.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260709T093527`
- `python -m pytest tests/test_skill_routing.py -q -k "20260709T091527 or 20260709T093527"`
- `python -m pytest tests/test_docs_contracts.py -q`
- `python -m pytest tests/test_skill_routing.py -q -k "20260709T081527 or 20260709T091527 or 20260709T093527"`
- `python -m ruff check src\blackhole_agent\skill_routing.py tests\test_skill_routing.py`
- `python -m pytest tests/test_docs_contracts.py tests/test_skill_routing.py -q -k "docs_contracts or 20260709T081527 or 20260709T091527 or 20260709T093527"`

All validation commands passed.

## Review Notes

- Hy3 API and MCP evidence remains body-free provider preflight control, not provider launch authority.
- Adjacent general-agent projects keep `agent_harness_eval_required` and no direct implementation lanes before local harness evaluation.
- No raw source URLs, evidence URLs, replay commands, provider config bodies, secret values, upstream bodies, promotion, push, restart, or remote execution are exported by the new operator packet.
