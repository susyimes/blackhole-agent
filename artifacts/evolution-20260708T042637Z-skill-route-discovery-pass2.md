# Evolution Run: Skill Route Discovery Pass 2

- Source digest: `github-growth-20260708T042637.744153Z`
- Rollback artifact: `artifacts/rollback-20260708T042637Z-skill-route-discovery-pass2.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260708T042637Z-skill-route-discovery-pass2`

## Evidence

- `https://github.com/Pluviobyte/rnskill`: public generic `SKILL.md` collection with skills, docs, tools, plugin metadata, and install examples.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent reverse-flow skill workflow with `skills/reverse-flow` shape and local workflow-gate pressure.
- `https://github.com/shepherd-agents/shepherd`: public general-agent runtime substrate with reversible trace and replay claims.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: public workflow-usecase collection with agent-guided Blender/Seedance/MCP pressure.

## Hypothesis

The active pass-2 window needs one operator-visible checkpoint before activation:
skill workflow repositories may enter only bounded documentation, config, test,
or code-patch lanes, while adjacent general-agent and workflow projects remain
behind `agent_harness_eval_required` until a local harness evaluation path exists.

## Change

- Added `skill_route_discovery_current_digest_20260708T042637_pass2_route_activation_checkpoint`.
- Added a fixture for the current source digest covering reverse-flow, rnskill,
  Shepherd, Hy3, and Blender/Seedance workflow-usecase evidence.
- Added regression assertions that the packet exports only hashes/counts/lanes,
  keeps rnskill in documentation, keeps reverse-flow in test with
  `skill_route_discovery_first`, and blocks inherited skill-route lanes for
  adjacent general-agent rows.
- Documented the checkpoint in `docs/skill-route-discovery.md`.

## Validation

```bash
python -m pytest tests/test_skill_routing.py -q -k 20260708T042637
```

Passed: 1 test, 408 deselected.

```bash
python -m pytest tests/test_skill_routing.py -q -k "current_pass2_scope_recompute_gate or 20260708T024637 or 20260708T032637 or 20260708T042637"
```

Passed: 4 tests, 405 deselected.

## Review Notes

- No external skill activation, install, provider launch, external harness
  execution, remote execution, raw URL export, raw command export, target path
  export, or upstream body export was added.
- The self-model was read and left unchanged because it already supports
  rollback-backed local validation and did not need to shape this specific route
  checkpoint.
