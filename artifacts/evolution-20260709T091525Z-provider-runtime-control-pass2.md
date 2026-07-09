# Provider Runtime Control Pass 2

Source digest: `github-growth-20260709T091527.196858Z`

Hypothesis: the current reverse-flow/rnskill/Hy3 window needs an operator-visible
classifier regression surface, not direct adoption. Skill-shaped repositories
should route through `skill_route_discovery` first, while general agent,
workflow, provider API, and MCP signals stay behind harness or provider
preflight checks.

Evidence reviewed:

- `lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill workflow with
  skill directory, local sandbox framing, staged workflow, diagnostic scripts,
  and install/run examples.
- `Pluviobyte/rnskill`: SKILL.md-compatible agent skills collection with
  skills, docs, tools, marketplace/plugin metadata, and install notes.
- `Tencent-Hunyuan/Hy3` issue and PR evidence: API quickstart and stdio MCP
  server work, which is provider/runtime evidence rather than skill package
  evidence.

Change:

- Added `current_digest_20260709T091527_pass2_validation_lane` to the skill
  route proposal map.
- Added regression coverage for two skill rows and three adjacent
  `agent_harness_eval_required` rows.
- Documented the pass-2 replay lane in `docs/skill-route-discovery.md`.

Rollback:

- Rollback ref:
  `refs/blackhole/rollback/20260709T091525Z-provider-runtime-control-pass2`
- Rollback artifact:
  `artifacts/rollback/20260709T091525Z-provider-runtime-control-pass2/rollback-point.md`
- Rollback execution remains an explicit destructive operator action.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k 20260709T091527`
  passed: 1 passed, 459 deselected.
- `python -m pytest tests/test_skill_routing.py -q -k "20260709T075527 or 20260709T081527 or 20260709T091527"`
  passed: 3 passed, 457 deselected.

Validation command recorded in the exported lane:
  `python -m pytest tests/test_skill_routing.py -q -k 20260709T091527`

Review notes:

- The first rollback artifact command had a PowerShell here-string syntax
  error and did not create the final rollback files. The rollback point was
  then created successfully with line-array output.
- Self-model decision: unchanged. The current self-model already says local
  evolution should be rollback-backed, locally validated, and explicit about
  uncertainty.
- Raw source URLs, evidence URLs, replay commands, upstream bodies, provider
  config, secret values, runtime action, promotion, restart, and remote
  execution remain denied in the exported lane.
