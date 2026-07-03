# Reverse-Flow Skill Route Probe

- Source digest: `github-growth-20260703T000121.763879Z`
- Capability slice: provider-runtime-control pass 4 of 4, skill-route discovery probe
- Rollback ref: `refs/rollback/blackhole-evolve-20260703T000120Z`
- Evidence reviewed: public GitHub pages for `diaol/reverse-flow-skill`, `lingbol088-spec/reverse-flow-skill`, `netstat2016/reverse-flow-skill`, and `tallasd/reverse-flow-skill`

Hypothesis: a fork-heavy reverse-flow-style Codex skill package should be
recognized as skill-route discovery metadata only. It should create a local
validation candidate, not direct implementation evidence, runtime activation, or
external skill installation.

Change:

- Added `tests/fixtures/proposal_replay/reverse_flow_skill_route_probe.json`.
- Registered the fixture in `tests/fixtures/proposal_replay/manifest.json`.
- Added focused proposal replay assertions in `tests/test_proposal_eval.py`.
- Documented the current-run route boundary in `docs/skill-route-discovery.md`.

Self-model decision: left unchanged. The current self-model already says local
experiments are acceptable when rollback-backed and locally validated, while
offensive behavior, unauthorized access, and privacy leakage remain the narrow
review-only boundary. This run needed executable replay coverage rather than a
new self-description.

Review notes:

- The reverse-flow evidence is security-adjacent but framed by the upstream
  pages as local CTF, crackme, wargame, training, sandbox, and offline sample
  analysis workflow. This run does not import, install, execute, or activate the
  skill.
- Fork rows are intentionally truncated by the replay fixture and cannot be
  cited by accepted proposals.
- No provider runtime launch, external harness execution, remote execution, raw
  upstream body export, profile write, or memory write is introduced.
