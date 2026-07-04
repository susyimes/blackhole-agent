# Blackhole Run: skill-route-discovery pass 2

- Source digest: github-growth-20260704T124434.742366Z
- Rollback artifact: artifacts/rollback/20260704T124432Z-skill-route-discovery-pass2.md
- Rollback ref: refs/blackhole-rollback/20260704T124432Z-skill-route-discovery-pass2
- External evidence reviewed: lingbol088-spec/reverse-flow-skill and lyra81604/zhengxi-views repository pages

## Hypothesis

Current reverse-flow-skill and zhengxi-views signals should deepen the existing
skill-route-discovery pass-2 lane rather than introduce external skill
activation. Reverse-flow evidence should validate as a Codex workflow-gate skill
candidate in the local test lane. Zhengxi evidence should remain a generic,
source-cited skill workflow documentation lane. Adjacent general-agent projects
should remain `agent_harness_eval_required` and not inherit skill-route lanes.

## Change

- Added a digest-specific pass-2 lane for `github-growth-20260704T124434.742366Z`.
- Added a frozen local fixture for the current evidence window.
- Added a focused regression test for bounded lanes, selected item IDs, denied
  runtime/provider/export paths, and adjacent harness routing.
- Documented the current pass in `docs/skill-route-discovery.md`.

## Validation

Run:

```bash
python -m pytest tests/test_skill_routing.py -q -k 20260704T124434
```

```bash
python -m pytest tests/test_skill_routing.py -q -k 20260704T124434
```

Result: 1 passed, 265 deselected.

```bash
python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: 2 passed, 9 deselected.

## Review Notes

- No upstream skill code was copied, installed, imported, or executed.
- Raw source URLs remain in the frozen fixture only; controller lane output is
  expected to export hashes and selected digest item IDs instead.
- Self-model was read and left unchanged because it already matched this run's
  rollback-backed local evolution policy and did not need to carry routing
  behavior.
