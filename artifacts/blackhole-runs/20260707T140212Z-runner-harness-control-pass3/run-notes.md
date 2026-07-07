# Runner Harness Control Pass 3

Source digest: `github-growth-20260707T140109.483291Z`
Branch: `codex/blackhole-evolve/20260707T140212.771424-run-a-bounded-local-skill-route-discovery-lane-f`
Rollback point: `artifacts/rollback/20260707T140212Z-runner-harness-control-pass3/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill workflow with local sandbox, CTF framing, `skills/reverse-flow/SKILL.md`, references, scripts, and install pressure. Routed as bounded local skill-route discovery only.
- `Pluviobyte/rnskill`: generic AI Agent skills collection. Routed as generic skill workflow evidence, not an installable package.
- `InternScience/Agents-A1` and `shepherd-agents/shepherd`: general agent project evidence. Kept behind `agent_harness_eval_required` with no direct runtime or implementation lane before local harness evaluation.

## Hypothesis

Pass-3 skill-route discovery should expose one operator-visible runner workflow that ties intake, mid-flight state, recovery, replay, and report artifacts together while preserving the bounded local lane contract.

## Change

- Added `workflow_handoff` and `artifact_manifest` metadata to `skill_route_discovery_pass3_runner_harness_control_plane`.
- Tightened pass-3 active skill proposal classification so current general-agent trend anchors such as Shepherd, Agents-A1, and Fundamental-Ava stay adjacent instead of appearing as missing skill lanes.
- Added a current-digest local harness fixture and a named regression for `20260707T140109`.
- Documented the new pass-3 control-plane replay surface in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k 20260707T140109`
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or 20260707T140109"`
- `python -m pytest tests/test_harness_eval.py -q`

All validation passed.

## Review Notes

- No upstream code was cloned, installed, or executed.
- Raw source URLs and replay command bodies remain omitted or hashed in evaluator output.
- Self-model left unchanged because its current preference already matches this rollback-backed, locally validated route.
