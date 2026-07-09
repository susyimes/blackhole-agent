# Evolution Run: Skill Route Discovery Pass 3 Validation Lane

Run ID: 20260709T053525Z-skill-route-discovery-pass3-validation-lane
Source digest: github-growth-20260709T053527.306621Z
Branch: codex/blackhole-evolve/20260709T053612.587409-run-a-bounded-skill-route-discovery-validation-l

## Hypothesis

The current pass-3 skill-route window needs an operator-visible validation packet keyed to the active source digest.
Reverse-flow-style Codex skill evidence should route to a bounded local test lane, generic rnskill-style collection
evidence should route to a bounded documentation lane, and general agent/model projects should remain behind
agent_harness_eval before any implementation lane opens.

## Evidence Reviewed

- https://github.com/lingbol088-spec/reverse-flow-skill: public repository presents a Codex/AI Agent skill package under
  `skills/reverse-flow`, with SKILL.md, local sandbox framing, staged workflow, diagnostic scripts, install examples,
  and run pressure. Treated as skill-route evidence only.
- https://github.com/Pluviobyte/rnskill: public repository presents an AI Agent Skills collection. Treated as generic
  skill workflow evidence with missing-detail uncertainty until locally inspected.
- https://github.com/SmileLikeYe/agent-chief: public repository presents a local-first general agent attention/router
  project. Treated as adjacent general-agent evidence requiring agent_harness_eval.
- https://github.com/Tencent-Hunyuan/Hy3: public repository presents a reasoning/agent model project with provider/API
  pressure. Treated as adjacent general-agent/model evidence requiring agent_harness_eval.

## Local Change

- Added `current_digest_20260709T053527_pass3_validation_packet` to the skill-route proposal lane map.
- Added a regression that builds the current evidence mix and verifies:
  - reverse-flow routes to `test`;
  - rnskill routes to `documentation` and preserves uncertainty;
  - agent-chief and Hy3 route to `agent_harness_eval_required`;
  - no runtime, external harness, provider launch, remote execution, raw source URL, or replay command is exposed.

## Rollback

Rollback artifact: `artifacts/rollback/20260709T053525Z-skill-route-discovery-pass3-validation-lane/rollback-point.md`
Rollback ref: `refs/blackhole-rollback/20260709T053525Z-skill-route-discovery-pass3-validation-lane`

Rollback execution remains an explicit destructive operator action only.

## Self-Model Decision

`docs/self-model.md` was left unchanged. The existing self-model already describes the behavior selected in this run:
prefer rollback-backed, locally validated behavior changes over report-only scaffolding while keeping activation and
privacy boundaries external.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260709T053527`
- `python -m pytest tests/test_skill_routing.py -q -k "20260709T005850 or 20260709T053527"`
- `python -m pytest tests/test_skill_routing.py -q`

All passed.

## Review Notes

- No upstream code was cloned, installed, executed, or activated.
- The packet is body-free and hashes/omits raw source URLs in the emitted route surface.
- General agent and model projects remain evaluation inputs only until a local agent harness eval passes.
