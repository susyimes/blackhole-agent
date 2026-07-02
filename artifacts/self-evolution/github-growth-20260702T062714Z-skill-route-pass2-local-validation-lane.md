# Skill Route Discovery Pass 2 Local Validation Lane

Source digest: `github-growth-20260702T062714.806950Z`

Hypothesis:
Public repositories that advertise skill package structure should enter only
bounded local skill-route lanes, while general-agent projects in the same digest
must remain in a separate `agent_harness_eval_required` lane before any
implementation or runtime follow-up.

Focused evidence reviewed:
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: public skill
  directories, plugin marketplace metadata, workflows, and `skills.sh.json`.
- `https://github.com/lyra81604/zhengxi-views`: `SKILL.md`, `skill.yml`,
  references, scripts, evals, source-citation, and non-investment-advice
  boundaries.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent benchmark/model
  evidence without skill workflow route hints.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: autonomous-agent
  simulation evidence without skill workflow route hints.

Change:
- Added the current digest pass-2 case to the deterministic
  `current_digest_pass2_local_validation_lane` builder.
- Added a skill-route fixture and a local harness replay fixture for the current
  digest.
- Added route and harness assertions proving:
  - `p1_skill_route_discovery_docs_tests` maps only to documentation, config,
    test, or code_patch outputs and selects the local test lane.
  - `p3_route_metadata_documentation` stays documentation-only.
  - `p2_agent_harness_eval_cluster` keeps Qwen-AgentWorld and Fundamental-Ava
    in `agent_harness_eval_required`.
  - Runtime action, provider launch, external harness execution, remote
    execution, raw URL export, and replay-command export remain denied.
- Documented the current digest route split in `docs/skill-route-discovery.md`.

Rollback:
- Ref: `refs/blackhole-rollback/20260702T062713Z-skill-route-discovery-pass2-current-digest`
- Artifact: `artifacts/self-evolution/github-growth-20260702T062714Z-rollback.md`

Validation:
- `python -m pytest tests/test_skill_routing.py -q -k 20260702T062714`
- `python -m pytest tests/test_harness_eval.py -q -k "20260702T062714 or local_harness_eval_runs_pass_and_fail_fixtures"`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_harness_eval.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`

Review notes:
- No offensive-behavior, unauthorized-access, or privacy-leakage route was
  selected.
- No upstream code was installed, imported, cloned for execution, or run.
- The self-model was read and left unchanged because its current preference
  already supports this rollback-backed, locally validated behavior change.
