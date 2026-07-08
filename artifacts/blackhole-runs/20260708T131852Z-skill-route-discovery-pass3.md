# Skill Route Discovery Pass 3

- Source digest: `github-growth-20260708T131852.174738Z`
- Branch: `codex/blackhole-evolve/20260708T131954.392307-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/blackhole/rollback/20260708T131852Z-skill-route-discovery-pass3-current-window`
- Rollback artifact: `artifacts/rollback/20260708T131852Z-skill-route-discovery-pass3-current-window/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package with `skills/`, `SKILL.md`, local sandbox/CTF framing, staged workflow, install examples, and script examples.
- `https://github.com/Pluviobyte/rnskill`: public AI Agent Skills collection with `skills`, docs, tools, plugin/marketplace-style metadata, Codex/Claude compatibility, and install examples.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: workflow/use-case collection with Blender, Seedance, MCP, source-cited cases, and agent-guided workflow pressure.
- `https://github.com/Tencent-Hunyuan/Hy3`: model project with agent capability, API/MCP/provider/deployment pressure.

## Change

Added `skill_route_discovery_current_digest_20260708T131852_pass3_validation_lane` as an operator-visible pass-3 packet. It keeps reverse-flow in the bounded local test lane, keeps rnskill in the bounded documentation lane, and queues Shepherd, Hy3, and Blender/Seedance evidence behind `agent_harness_eval_required`.

The packet exports selected item IDs, proposal IDs, lane names, hashes, and activation denials only. Runtime action, install, provider launch, external skill activation, external harness execution, remote execution, raw source URLs, evidence URLs, replay commands, target paths, upstream bodies, promotion, and restart remain disabled.

## Self-Model Decision

`docs/self-model.md` was left unchanged. The current preference already supports rollback-backed, locally validated behavior changes and does not need a new behavior-shaping note for this pass.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T131852`
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T131852 or 20260708T125853 or 20260708T092635"`

Both commands passed.
