# Skill Route Discovery Pass 1

Source digest: `github-growth-20260703T040049.885608Z`

Rollback ref: `refs/blackhole-rollback/20260703T040151-skill-route-discovery-pass1`

Evidence reviewed:

- `https://github.com/lingbol088-spec/reverse-flow-skill` exposed a public Codex/AI Agent skill package shape with `skills/reverse-flow/SKILL.md`, scripts, local sandbox/CTF/crackme workflow language, and install/runtime examples. This run treated it as route evidence only.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava` were kept as general-agent project evidence without skill-route inheritance.

Local change:

- Added a digest-specific pass-1 lane for `github-growth-20260703T040049.885608Z`.
- `p1-skill-route-discovery-codex-workflow` selects the local test lane, records `skill_route_discovery_first`, and keeps allowed lanes to documentation, config, test, and code_patch.
- `p2-generic-skill-workflow-discovery-doc` remains documentation triage for generic/source-cited skill workflow evidence.
- `Qwen-AgentWorld` and `Fundamental-Ava` route to `p3-agent-harness-eval-fixtures` as `agent_harness_eval_required` rows with no direct runtime or direct code_patch route.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k current_digest_20260703T040049` passed.
- `python -m pytest tests/test_skill_routing.py -q` passed.
- `python -m pytest tests/test_docs_contracts.py -q` passed.

Review notes:

- No external skill activation, provider launch, external harness execution, remote execution, raw URL export, replay command export, target path export, or upstream body export was added.
- The self-model was left unchanged because it already describes the local-evolution and validation boundary used by this run.
