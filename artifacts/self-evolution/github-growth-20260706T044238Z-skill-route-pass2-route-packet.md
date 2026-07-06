# Skill Route Discovery Pass 2 Route Packet

Source digest: `github-growth-20260706T044238.826915Z`

Hypothesis: mixed public evidence needs one operator-visible packet before activation. Skill workflow repositories should map only into bounded local lanes, while general-agent projects should remain behind `agent_harness_eval_required` until a local harness result exists.

Evidence reviewed:
- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/agent skill workflow evidence with install/script/runtime pressure that should remain diagnostic.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, and `https://github.com/TianhangZhuzth/Fundamental-Ava`: general-agent project evidence that should not inherit skill-route authority.

Rollback point:
- `artifacts/rollback/20260706T044322Z-skill-route-discovery-pass2/rollback-point.md`
- Original branch: `codex/blackhole-evolve/20260706T044322.310755-add-or-run-a-local-skill-route-discovery-validat`
- Original HEAD: `c548af56f3ba41076b1724ada0d9a46173fc5c44`

Changed files:
- `src/blackhole_agent/skill_routing.py`: added `build_skill_route_discovery_validation_route_packet`, an activation-free mixed route packet.
- `src/blackhole_agent/harness_eval.py`: exposes `validation_route_packet` from `skill_route_discovery_lane` replay output.
- `tests/test_skill_routing.py`: added a direct regression for reverse-flow skill evidence plus three general-agent projects.
- `tests/test_harness_eval.py`: updated local harness fixture counts and added the new fixture to aggregate replay expectations.
- `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260706T044238_pass2_route_packet.json`: replay fixture for this pass.
- `docs/skill-route-discovery.md`: documented the pass-2 packet and replay command.

Self-model decision:
- `docs/self-model.md` was read and left unchanged. Its preference for locally validated, rollback-backed evolution matched this pass; no new self-description was needed.

Validation:
- `python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k "validation_route_packet or 20260706T044238"`: passed, `1 passed, 563 deselected`.
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`: passed, `1 passed, 241 deselected`.
- `python -m pytest tests/test_skill_routing.py -q`: passed, `322 passed`.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`: passed, `11 passed, 231 deselected`.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, `11 passed`.

Review notes:
- A first attempted pytest selector for the fixture name deselected all tests because the name is a fixture record rather than a test function; the aggregate local-harness test was run afterward and passed.
- No restart, provider launch, external harness execution, remote execution, or upstream repository execution was performed.
