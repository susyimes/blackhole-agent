# Evolution: Skill Route Discovery Pass 3 Active Window Manifest

- Source digest: `github-growth-20260704T154434.930893Z`
- Capability slice: `skill-route-discovery`, pass 3 of 4
- Rollback artifact: `artifacts/rollback-20260704T154433Z-skill-route-discovery-pass3.md`
- Rollback ref: `refs/blackhole-rollback/20260704T154433Z-skill-route-discovery-pass3`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill workflow with local sandbox defaults, workflow phases, scripts, and installation pressure.
- `https://github.com/lyra81604/zhengxi-views`: traceable domain Agent Skill workflow that should remain a bounded local route candidate before activation.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent benchmark/environment evidence that should require harness evaluation before implementation routing.

## Hypothesis

The existing pass-3 replay lane is useful but too indirect for this wake: it exposes generic replay proposal IDs rather than the exact active proposal IDs. Adding an operator-visible manifest under the replay lane should make the current pass auditable without granting runtime authority or exporting raw upstream URLs.

## Change

- Added `current_pass3_active_window_proposal_manifest` under `current_pass3_skill_route_replay_lane`.
- Bound the active proposals to deterministic local route rows:
  - `p1-skill-route-discovery-zhenxi-views` remains `skill_route_discovery` with bounded local lanes.
  - `p2-codex-workflow-gate-reverse-flow-skill` confirms `skill_route_discovery_first` before broader Codex workflow handling.
  - `p3-agent-harness-eval-qwen-agentworld` remains `agent_harness_eval_required` with no direct implementation lanes before harness evaluation.
- Preserved `runtime_action: none` and disabled external skill, agent, harness, provider, remote, profile, and memory activation paths.
- Left `docs/self-model.md` unchanged because its current preference matched this run: locally validated reversible behavior changes are preferred over report-only scaffolding.

## Validation

```powershell
python -m pytest tests/test_proposal_eval.py -q -k "current_pass3_skill_route_replay_lane or current_pass3_active_window_manifest"
python -m pytest tests/test_proposal_eval.py -q
python -m pytest tests/test_skill_routing.py -q -k "codex_workflow_gate or current_digest_20260704 or active_window or skill_route_discovery"
python -m pytest -q
```

Result: all passed; full suite reported `760 passed`.

## Review Notes

- The manifest intentionally carries item IDs and bounded lane metadata, not raw upstream URLs, commands, or repository bodies.
- The proposal ID `p1-skill-route-discovery-zhenxi-views` preserves the active proposal spelling from the wake while the evidence item remains `trend:lyra81604/zhengxi-views-1`.
