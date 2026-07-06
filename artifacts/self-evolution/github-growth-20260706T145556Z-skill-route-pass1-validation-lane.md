# Skill Route Discovery Pass 1

Source digest: `github-growth-20260706T145556.011572Z`

Hypothesis: the current reverse-flow-skill signal is useful as a bounded local
skill-route discovery lane, while shepherd and the general agent projects must
remain behind local harness evaluation before any workflow, VCS, runtime,
provider, or code behavior is adopted.

Evidence reviewed:

- `https://github.com/lingbol088-spec/reverse-flow-skill` exposes a
  `skills/reverse-flow` package shape, `SKILL.md`, references, scripts,
  install examples, run examples, and local sandbox / CTF framing. This is
  enough for route classification, not activation.
- `https://github.com/shepherd-agents/shepherd` and
  `https://github.com/shepherd-agents/shepherd/pull/25` expose general agent
  runtime, reversible trace, workflow/VCS, and public-surface synchronization
  pressure. This is harness-evaluation evidence, not a direct local workflow
  route.
- `https://github.com/InternScience/Agents-A1` is general agent benchmark /
  long-horizon evidence and belongs in the same harness-evaluation queue.

Change made:

- Added a frozen pass-1 fixture for `github-growth-20260706T145556.011572Z`.
- Added a deterministic current-digest route mapping for that fixture.
- Added a focused replay test proving the generated packet is body-free,
  bounded to documentation/config/test/code_patch for skill evidence, and keeps
  adjacent general agent projects at `agent_harness_eval_required`.

Rollback point:

- `artifacts/rollback/20260706T145651Z-skill-route-discovery-pass1-current-window/rollback-point.md`
- `refs/blackhole-rollback/20260706T145651Z-skill-route-discovery-pass1-current-window`

Self-model decision:

- Left `docs/self-model.md` unchanged. It already prefers local reversible
  experiments over validation-report-only work and does not need a new
  category for this pass.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T145556`
  passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260706T145556 or 20260706T143556 or 20260706T103129"`
  passed.
