# Skill Route Discovery Pass 1

- Source digest: github-growth-20260706T030239.081375Z
- Branch: codex/blackhole-evolve/20260706T030335.104812-add-or-run-a-bounded-local-skill-route-discovery
- Rollback artifact: artifacts/rollback/20260706T030335Z-skill-route-discovery-pass1/rollback-point.md
- Rollback ref: refs/rollback/20260706T030335Z-skill-route-discovery-pass1

## Evidence

Reviewed the carried evidence URLs narrowly:

- `https://github.com/lingbol088-spec/reverse-flow-skill` presents an explicit Codex / AI Agent skill workflow repository with `skills/reverse-flow`, install examples, scripts, and local sandbox / CTF framing.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, and `https://github.com/TianhangZhuzth/Fundamental-Ava` are general agent project signals, not explicit local skill packages.

## Hypothesis

This digest should have its own replayable pass-1 lane. Explicit skill/workflow evidence may enter only bounded local lanes: documentation, config, test, or code_patch. General agent projects must remain `agent_harness_eval_required` and cannot inherit skill-route lanes or open runtime, provider, external harness, remote execution, or direct code-patch routes before local harness evidence exists.

## Change

- Added digest-specific pass-1 route specs for all five active proposal IDs.
- Added a frozen body-free fixture for `github-growth-20260706T030239.081375Z`.
- Added a regression test that verifies:
  - reverse-flow-skill maps to bounded skill-route lanes only;
  - install/run/runtime/provider/external harness pressure is not exported as an allowed lane;
  - Agents-A1, Qwen-AgentWorld, and Fundamental-Ava remain in `agent_harness_eval_required`;
  - the lane exports proposal IDs, selected item IDs, route profiles, and denial booleans without raw URLs or replay commands.

## Validation

```powershell
pytest tests/test_skill_routing.py -q -k 20260706T030239
pytest tests/test_skill_routing.py -q -k "20260706T030239 or 20260706T020239 or 20260706T022238"
pytest tests/test_skill_routing.py -q
```

Results:

- `1 passed, 316 deselected`
- `3 passed, 314 deselected`
- `317 passed`

## Self-Model

Left `docs/self-model.md` unchanged. The existing preference already matches this run: use rollback-backed local validation for behavior changes, keep offensive/privacy boundaries narrow, and preserve uncertainty through artifacts rather than treating trend evidence as activation authority.
