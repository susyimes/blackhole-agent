# Skill Route Discovery Pass 2 Current Window

Source digest: `github-growth-20260702T214709.510460Z`

Rollback:

- Artifact: `artifacts/rollback-20260703T010625Z-skill-route-discovery-pass2-current-window.md`
- Ref: `refs/blackhole-rollback/20260703T010625Z-skill-route-discovery-pass2-current-window`

## Evidence

- `https://github.com/lyra81604/zhengxi-views` exposes public Agent Skill shape: `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation workflow, and advice-boundary language.
- `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/ksimback/looper` are generic agent or agent-loop evidence without a local skill-route hint in this run.

## Hypothesis

The active pass-2 window should expose a digest-specific local validation lane. Skill-package evidence can route only to bounded documentation, config, test, or code_patch lanes. Generic agent-project evidence must remain behind `agent_harness_eval_required` before implementation scope is chosen.

## Change

- Added digest-specific pass-2 routing for `github-growth-20260702T214709.510460Z`.
- Added regression coverage for the controller lane and harness output.
- Documented the route contract for this digest.

The self-model was read and left unchanged. Its current preference already matches this run: try a rollback-backed, locally validated behavior path while keeping runtime activation, external execution, and privacy-sensitive routes outside this change.

## Review Notes

- No upstream code was installed, cloned, executed, or imported.
- No provider launch, external harness execution, remote execution, restart, push, profile write, memory write, or external skill activation path was added.
- The evidence is repository-level and public; the local claim is limited to route classification and harness-eval gating.
