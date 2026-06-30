# github-growth-20260630T060714Z Skill Route Pass 1

## Rollback

- Original branch: `codex/blackhole-evolve/20260630T060809.436489-add-a-bounded-local-skill-route-discovery-valida`
- Original HEAD: `4c50e231a2e159291a14546b88f88af5f950a813`
- Rollback ref: `refs/blackhole-rollback/20260630T140835Z`
- Rollback artifact: `artifacts/rollback-20260630T140835Z.txt`

## Evidence Review

- `https://github.com/lyra81604/zhengxi-views` exposes an Agent Skill-style repository shape with `SKILL.md`, `skill.yml`, `references`, and `scripts`, so it is valid skill-route discovery evidence but not installable runtime authority.
- `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/ksimback/looper`, and `https://github.com/ziwang-Physics/AgentChat` are treated as general agent project evidence until local harness evaluation exists.
- `https://github.com/LING71671/open-reverselab` is automation and reverse-engineering context, so it is kept as adjacent `agent_harness_eval_required` evidence plus review-only security-adjacent context.

## Local Change

- Added digest-specific pass-1 handling for `github-growth-20260630T060714.387302Z`.
- Mapped `p1_skill_route_discovery_zhengxi_views` to the local test lane while preserving only documentation, config, test, and code_patch as allowed local lanes.
- Mapped Qwen-AgentWorld, looper, and AgentChat to `p2_agent_harness_eval_general_projects`.
- Mapped open-reverselab to `p3_automation_agent_eval_open_reverselab` with no route influence beyond review-only boundary metadata.

## Validation

- `python -m py_compile src/blackhole_agent/skill_routing.py`
- `pytest tests/test_harness_eval.py -q -k 20260630T060714`
- `pytest tests/test_skill_routing.py -q -k 20260630T060714`
- `pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`

All validation passed.
