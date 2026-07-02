# Skill Route Discovery Pass 1 Validation Lane

- source_digest: `github-growth-20260702T100715.355760Z`
- rollback_ref: `refs/blackhole-rollback/20260702T100713Z`
- branch: `codex/blackhole-evolve/20260702T100810.154246-run-a-bounded-skill-route-discovery-lane-for-the`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public repository exposes `SKILL.md`, `skill.yml`, `references/`, `scripts/`, `evals/`, source-citation behavior, and a non-investment-advice boundary. Interpreted as `skill_route_discovery` evidence only.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general-agent project evidence without an explicit skill route hint in this digest. Interpreted as adjacent `agent_harness_eval_required`.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: public general-agent project evidence without an explicit skill route hint in this digest. Interpreted as adjacent `agent_harness_eval_required`.
- `https://github.com/ksimback/looper`: public review-gated loop project evidence without an explicit skill route hint in this digest. Interpreted as adjacent `agent_harness_eval_required`.

## Change

Added a digest-specific pass-1 branch for `github-growth-20260702T100715.355760Z` so the current proposal IDs route through `current_digest_pass1_validation_lane` instead of falling back to older current-window aliases.

The new fixture keeps zhengxi-views in the local test lane with allowed local lanes limited to documentation, config, test, and code_patch. Qwen-AgentWorld, Fundamental-Ava, and looper remain harness-gated with `skill_route_discovery_inherited: false`, direct runtime disabled, and direct code patch disabled.

The self-model was read and left unchanged. It already describes rollback-backed local evolution and a narrow safety boundary; this run needed executable routing evidence rather than a revised self-description.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "20260702T100715 or local_harness_eval_runs_pass_and_fail_fixtures"`
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records`

Both validation commands passed.

## Review Notes

- No upstream code was cloned, installed, imported, or executed.
- No provider runtime, external harness execution, remote execution, external skill activation, profile write, memory write, raw source URL export, raw evidence URL export, target path export, replay command body export, or upstream body export was added.
- The general-agent anchors remain pending local `agent_harness_eval_required` evidence before any bounded follow-up lane is selected.
