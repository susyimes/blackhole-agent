# Skill Route Discovery Pass 2 Local Validation Lane

- Source digest: `github-growth-20260705T141637.046693Z`
- Capability theme: `skill-route-discovery`
- Rollback point: `artifacts/rollback/20260705T141637Z-skill-route-discovery-pass2/rollback-point.md`
- Local rollback ref: `refs/blackhole-rollback/20260705T141637Z`

## Evidence

The active window carried one skill-like repository signal,
`lingbol088-spec/reverse-flow-skill`, plus three general-agent project signals:
`QwenLM/Qwen-AgentWorld`, `InternScience/Agents-A1`, and
`TianhangZhuzth/Fundamental-Ava`.

The reverse-flow signal was treated as body-free route evidence for a Codex/AI
Agent skill workflow. Its install, script, provider, vulnerability-analysis,
external harness, runtime, and remote-execution pressure was downgraded to
diagnostic metadata only.

The three general-agent signals lacked explicit skill workflow route evidence
or local harness results, so they stayed in `agent_harness_eval_required`.

## Hypothesis

Pass 2 should expose the active reverse-flow and general-agent proposals through
the operator-visible `current_digest_pass2_local_validation_lane`, rather than
falling through to older compass/game profile rows that block on unrelated
missing evidence.

## Changes

- Added a frozen current-window fixture for
  `github-growth-20260705T141637.046693Z`.
- Extended the July 5 reverse-flow/general-agent pass-2 route builder to
  recognize the current digest.
- Added active proposal IDs for:
  `p1-skill-route-discovery-reverse-flow`,
  `p2-agent-harness-eval-qwen-agentworld`,
  `p3-general-agent-project-batch-eval`, and
  `p4-route-classification-regression-coverage`.
- Added a focused regression test proving:
  reverse-flow maps only to bounded local skill lanes;
  Qwen-AgentWorld stays in the Qwen harness-eval proposal;
  Agents-A1 and Fundamental-Ava stay in the batch harness-eval proposal;
  runtime, provider, external harness, and remote execution remain denied.
- Updated `docs/skill-route-discovery.md` with the replay command and route
  interpretation.

## Validation

Passed:

```text
PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k 20260705T141637
```

## Self-Model

`docs/self-model.md` was read and left unchanged. It already describes the
preference applied here: use rollback-backed local validation to turn public
signals into bounded behavior changes, without treating the self-model as a
permission source.
