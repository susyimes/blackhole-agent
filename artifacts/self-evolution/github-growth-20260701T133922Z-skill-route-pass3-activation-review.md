# Skill Route Discovery Pass 3 Activation Review

- Source digest: github-growth-20260701T133922.800774Z
- Capability theme: skill-route-discovery
- Pass: 3 of 4
- Rollback artifact: artifacts/rollback/20260701T133921Z-skill-route-discovery-pass3.md
- Rollback ref: refs/rollback/20260701T133921Z-skill-route-discovery-pass3

## Evidence Reviewed

- https://github.com/lyra81604/zhengxi-views
- https://github.com/QwenLM/Qwen-AgentWorld
- https://github.com/TianhangZhuzth/Fundamental-Ava
- https://github.com/ksimback/looper

The reusable lesson is route separation before activation: repository-level
skill package evidence can become only bounded local validation lanes, while
general agent projects without skill workflow signals remain behind
`agent_harness_eval_required`.

## Hypothesis

The current pass should expose an operator-visible activation-review lane for
the active digest without granting activation authority. zhengxi-views should
select local test and documentation lanes under `skill_route_discovery`.
Qwen-AgentWorld, Fundamental-Ava, and looper should stay adjacent general-agent
rows until a local harness-eval result exists.

## Local Change

- Added digest fixture:
  `tests/fixtures/skill_route_discovery/current_digest_20260701T133922_pass3_activation_review_lane.json`
- Extended `current_digest_pass3_activation_review_lane` for
  `github-growth-20260701T133922.800774Z`
- Added regression coverage in `tests/test_skill_routing.py`
- Documented the pass-3 route interpretation in `docs/skill-route-discovery.md`

## Boundary Notes

- Runtime action remains `none`.
- External skill and agent activation remain denied.
- External harness execution, provider launch, remote execution, profile writes,
  memory writes, raw URL export, replay-command export, target-path export, and
  upstream-body export remain denied.
- No push, promotion, restart, runner launch, provider launch, or remote
  execution was performed by this kernel run.

## Validation

Local gates run:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260701T133922
python -m pytest tests/test_skill_routing.py -q
python -m pytest tests/test_docs_contracts.py -q
```

Results:

- `1 passed, 130 deselected`
- `131 passed`
- `11 passed`
