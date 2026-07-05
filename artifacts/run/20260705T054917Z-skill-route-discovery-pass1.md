# Skill Route Discovery Pass 1 Run

Source digest: `github-growth-20260705T054818.762095Z`

Rollback point:

- Artifact: `artifacts/rollback/20260705T054917Z-skill-route-discovery-pass1.txt`
- Ref: `refs/blackhole-rollback/20260705T054917Z-skill-route-discovery-pass1`
- Original HEAD: `347fbdb002b3cca693ebbebae77dc125c2755e99`

Evidence reviewed:

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`

Hypothesis:

The active pass-1 skill-route window needs an operator-visible route matrix before activation. Reverse-flow-style
Codex skill workflow evidence should prove `skill_route_discovery_first`, generic BioNeMo-style skill workflow
evidence should remain generic, and adjacent general-agent projects should stay in `agent_harness_eval_required`.

Changes:

- Added `current_pass1_skill_route_validation_matrix` to the proposal route map.
- Added negated Codex-gate handling so text such as "without Codex-specific workflow gates" remains a generic skill
  workflow signal.
- Added a regression test for the current pass-1 digest window.
- Documented the new pass-1 route matrix in `docs/skill-route-discovery.md`.

Validation:

- `pytest tests/test_github_growth.py -q -k current_pass1_skill_route_validation_matrix`
- `pytest tests/test_proposal_eval.py -q -k skill_route_discovery`
- `pytest tests/test_github_growth.py -q -k "current_pass1_skill_route_validation_matrix or current_pass2_skill_route_window_gates_codex_generic"`
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`
- `pytest tests/test_github_growth.py -q -k "skill_route or route_classifier"`
- `ruff check src/blackhole_agent/proposal_synthesis.py tests/test_github_growth.py`
- `git diff --check`

Review notes:

- No external skill code was installed, imported, cloned, or executed.
- Raw upstream URLs are used only in tests and artifact evidence notes; route outputs hash source URLs.
- Self-model was read and left unchanged because its current preference already matches this bounded local evolution.
