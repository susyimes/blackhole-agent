# Skill Route Discovery Pass 1 Current Validation Lane

Source digest: `github-growth-20260701T235748.704258Z`

Rollback:
- Ref: `refs/blackhole/rollback/20260701T235747Z-skill-route-discovery-pass1`
- Artifact: `artifacts/rollback-20260701T235747Z-skill-route-discovery-pass1.md`

Focused evidence reviewed:
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/LING71671/open-reverselab`

Change:
- Added a current pass-1 lane for `github-growth-20260701T235748.704258Z`.
- Kept zhengxi-views as the only `skill_route_discovery` candidate, bounded to documentation, config, test, or code_patch lanes.
- Kept Qwen-AgentWorld and Fundamental-Ava behind `agent_harness_eval_required`.
- Recorded open-reverselab as review-only automation/reverse-engineering context at the offensive-behavior boundary.
- Denied runtime action, external activation, external harness execution, provider launch, remote execution, raw URL export, replay-command export, target-path export, and upstream-body export.

Validation:
- `python -m pytest tests/test_skill_routing.py -q -k 20260701T235748`
- `python -m pytest tests/test_skill_routing.py -q -k "20260701T223748 or 20260701T235748 or 20260701T231748"`
- `python -m pytest tests/test_proposal_eval.py -q -k "skill_route_discovery or route_classifier or agent_harness_eval_fixture"`

Self-model:
- Left unchanged. It already states the relevant preference for rollback-backed, locally validated evolution and is not needed as a permission source for this behavior change.
