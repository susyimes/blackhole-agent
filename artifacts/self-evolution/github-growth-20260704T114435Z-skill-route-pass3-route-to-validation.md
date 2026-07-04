# github-growth-20260704T114435Z skill-route pass 3

## Evidence reviewed

- Source digest: `github-growth-20260704T114435.950310Z`
- External evidence reviewed narrowly:
  - `https://github.com/lingbol088-spec/reverse-flow-skill`
  - `https://github.com/lyra81604/zhengxi-views`
  - `https://github.com/QwenLM/Qwen-AgentWorld`
  - `https://github.com/TianhangZhuzth/Fundamental-Ava`

The evidence supports a split route: Codex/Agent skill repositories stay in
`skill_route_discovery` bounded lanes, while general-agent projects without
skill workflow signals stay in `agent_harness_eval_required`.

## Hypothesis

The current pass-3 wake should expose an operator-visible route-to-validation
lane, not just another standalone fixture. A frozen digest fixture plus route
specialization can prove the Codex skill and generic skill rows map only to
documentation, config, test, or code_patch lanes, and that general-agent items
cannot bypass agent harness evaluation.

## Rollback

- Rollback artifact:
  `artifacts/rollback/20260704T114435Z-skill-route-discovery-pass3/rollback-point.md`
- Rollback ref:
  `refs/rollback/blackhole-agent/20260704T114435-skill-route-pass3`

## Changed surfaces

- `src/blackhole_agent/skill_routing.py` recognizes
  `github-growth-20260704T114435.950310Z` in the pass-3
  route-to-validation lane.
- `tests/fixtures/skill_route_discovery/current_digest_20260704T114435_pass3_route_to_validation.json`
  freezes the current body-free digest shape.
- `tests/test_skill_routing.py` asserts the skill lanes, harness rows, denial
  booleans, and body-free operator packet.
- `docs/skill-route-discovery.md` records the replay path.

## Validation

Focused validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704T114435
```

Result: `1 passed, 263 deselected`.

Regression validation:

```powershell
python -m pytest tests/test_skill_routing.py -q
```

Result: `264 passed`.

The self-model was left unchanged because its current preference already
matches this run: prefer rollback-backed, locally validated behavior changes
over validation-report-only work while keeping offensive behavior and privacy
leakage review-only.
