# Skill Route Discovery Pass 1 Local Validation

Source digest: `github-growth-20260629T183904.255941Z`

Hypothesis: the active pass-1 skill-route slice should expose an
operator-visible local validation lane for the current proposal IDs, rather
than falling back to older proposal aliases. COMPASS and zhengxi-views can enter
`skill_route_discovery`; Qwen-AgentWorld and looper stay adjacent
`agent_harness_eval_required` rows until a separate local harness evaluation
characterizes them.

Evidence reviewed:

- `https://github.com/dongshuyan/compass-skills`: public skill ecosystem signal.
- `https://github.com/lyra81604/zhengxi-views`: public generic skill workflow signal.
- `https://github.com/QwenLM/Qwen-AgentWorld`: adjacent general-agent evaluation signal.
- `https://github.com/ksimback/looper`: adjacent general-agent loop/eval signal.

Changes:

- Added a rollback artifact and local rollback ref for this run.
- Added a frozen local harness fixture for
  `github-growth-20260629T183904.255941Z`.
- Extended pass-1 activation readiness to recognize the current digest and
  current proposal IDs.
- Added focused assertions that unsafe raw suggested lanes are stripped from
  exported local lanes and that adjacent general-agent rows do not inherit
  skill-route authority.
- Documented the current digest interpretation in `docs/skill-route-discovery.md`.

Self-model decision:

- `docs/self-model.md` was read and left unchanged. Its current preference
  already matches this run: apply rollback-backed, locally validated evolution
  while keeping offensive behavior, abuse, unauthorized access, and privacy
  leakage review-only.

Review notes:

- AutoCVE remains review-only in this pass; no offensive or vulnerability
  execution route was added.
- Raw source URLs and replay commands are used inside the fixture input but are
  not exported by the evaluated operator panel.
