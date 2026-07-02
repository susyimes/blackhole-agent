# Skill Route Discovery Pass 3 Bounded Lanes

- Source digest: `github-growth-20260702T052715.136537Z`
- Branch: `codex/blackhole-evolve/20260702T052801.389965-add-or-extend-local-tests-for-skill-route-discov`
- Rollback artifact: `artifacts/self-evolution/github-growth-20260702T052715Z-rollback.md`
- Rollback ref: `refs/rollback/github-growth-20260702T052715Z`

## Evidence Reviewed

- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: public repository shows an agent skill catalog shape with skill directories, plugin marketplace metadata, workflow directories, and `skills.sh.json`, plus upstream install examples.
- `https://github.com/lyra81604/zhengxi-views`: public repository shows `SKILL.md`, `skill.yml`, `references/`, `scripts/`, `evals/`, source-cited research behavior, and a non-investment-advice boundary.

## Hypothesis

Agent-plus-skill trend repositories should improve local route discovery only as bounded lane evidence. The current pass-3 surface should name the current proposal IDs and selected item IDs, map BioNeMo and zhengxi-views only to documentation/config/test/code_patch lanes, and keep adjacent general-agent projects behind local harness evaluation.

## Local Change

- Added a digest-specific pass-3 activation review branch for `github-growth-20260702T052715.136537Z`.
- Added a frozen current-digest fixture with the two skill-workflow trend items plus adjacent Qwen-AgentWorld and Fundamental-Ava rows.
- Added a regression test asserting the exported lane is body-free, runtime-free, provider-free, and limited to documentation/config/test/code_patch for skill-route rows.
- Updated `docs/skill-route-discovery.md` to state that the selected skill-route item IDs are discovery input, not permission to import, install, execute, or activate upstream behavior.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260702T052715` passed: 1 passed, 157 deselected.
- `python -m pytest tests/test_skill_routing.py -q` passed: 158 passed.

## Review Notes

- Self-model left unchanged: its current preference already matches this run's rollback-backed, locally validated, bounded evolution rule.
- Qwen-AgentWorld and Fundamental-Ava remain `agent_harness_eval_required`; no runtime, provider, external harness, remote execution, profile write, memory write, or upstream activation path was added.
