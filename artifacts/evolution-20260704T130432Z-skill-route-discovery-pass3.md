# Evolution Run: skill-route-discovery pass 3

- Source digest: `github-growth-20260704T130435.072372Z`
- Branch: `codex/blackhole-evolve/20260704T130530.076760-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/rollback/blackhole-agent/20260704T130432Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260704T130432Z-skill-route-discovery-pass3/rollback-point.md`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex / AI Agent skill workflow with skill package layout, local sandbox and CTF framing, scripts, and install/runtime pressure. Interpreted only as skill-route evidence.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill package with source-cited research workflow and advice-boundary metadata. Interpreted as generic skill-workflow documentation evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: general agent projects without explicit skill workflow route hints. Interpreted as adjacent `agent_harness_eval_required` evidence.

## Hypothesis

The active pass-3 window needs a current-digest route-to-validation surface, not
another standalone fixture. If the current digest is recognized directly, the
operator packet can show that Codex skill workflow evidence routes through
`skill_route_discovery_first`, generic skill workflow evidence maps only to
documentation/config/test/code_patch, and general agent projects stay blocked
behind bounded harness evaluation before any implementation lane.

## Change

- Added the current digest to `current_digest_pass3_route_to_validation_lane`.
- Added a frozen evidence fixture for `github-growth-20260704T130435.072372Z`.
- Added a focused route split regression test for the current digest.
- Documented the wake-specific skill-route interpretation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260704T130435`: passed, 1 passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260704T130435 or 20260704T114435 or 20260704T102435"`: passed, 3 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route`: passed, 2 passed.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 267 passed.
- `git diff --check`: passed; only CRLF normalization warnings were emitted for touched tracked files.

## Review Notes

- No external skill code was installed, cloned, executed, or activated.
- Raw evidence URLs are present only in the frozen local fixture and run notes; operator packets continue to export hashes and IDs.
- `docs/self-model.md` was read and left unchanged because its current preference already matches this run's direct, rollback-backed local evolution posture.
