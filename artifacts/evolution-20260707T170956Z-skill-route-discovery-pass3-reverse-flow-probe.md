# Evolution Run

Run: 20260707T170956Z-skill-route-discovery-pass3-reverse-flow-probe

Source digest: github-growth-20260707T090834.684862Z

Theme: skill-route-discovery, pass 3 of 4

## Evidence Review

- `lingbol088-spec/reverse-flow-skill` exposes a Codex and AI Agent skill repository shape with `skills/reverse-flow/SKILL.md`, references, scripts, local sandbox and CTF/crackme framing, install examples, run examples, and staged workflow language. Its reverse-analysis domain makes execution or installation inappropriate from trend evidence alone.
- `Pluviobyte/rnskill` exposes a generic AI Agent skills collection shape with skill packages, docs, tooling metadata, and manual install language. That is useful route evidence, but activation remains external and validation-gated.
- Adjacent general-agent project evidence remains outside skill-route discovery and requires a separate local agent-harness evaluation before documentation, test, or code_patch follow-up.

## Hypothesis

The current pass should expose an operator-visible validation lane for the active reverse-flow and rnskill proposals, rather than adding another standalone proposal replay fixture. The lane should prove that skill-like repository evidence maps only to documentation, config, test, or code_patch outputs with `local_validation_required=true`.

## Rollback

- Rollback artifact: `artifacts/rollback/20260707T170956Z-skill-route-discovery-pass3-reverse-flow-probe/rollback-point.md`
- Rollback ref: `refs/rollback/20260707T170956Z-skill-route-discovery-pass3-reverse-flow-probe`

## Material Actions

- Added a source-specific pass-3 lane in `src/blackhole_agent/skill_routing.py`.
- Added a current digest fixture for `github-growth-20260707T090834.684862Z`.
- Added a regression test for the pass-3 reverse-flow probe.
- Updated `docs/skill-route-discovery.md` with the accepted local decision path.
- Left `docs/self-model.md` unchanged because it already supports rollback-backed local experiments with narrow safety review.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T090834` passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T084834 or 20260707T090834 or 20260707T072834 or 20260707T060834"` passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed.

## Review Notes

- External evidence was reviewed only at the carried proposal URLs. No broad trend discovery was rerun.
- The pass-3 lane remains body-free and does not activate, install, run, or import external skill repositories.
- Adjacent general-agent evidence remains queued behind `agent_harness_eval_required`.
