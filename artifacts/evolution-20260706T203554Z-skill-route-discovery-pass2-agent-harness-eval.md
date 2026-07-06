# Evolution Run

Run: 20260706T203554Z-skill-route-discovery-pass2-agent-harness-eval
Source digest: github-growth-20260706T203555.443958Z
Branch: codex/blackhole-evolve/20260706T203642.127141-create-or-extend-a-local-agent-harness-evaluatio

## Evidence

- `lingbol088-spec/reverse-flow-skill`: public repository evidence shows a Codex/AI Agent skill workflow shape, so it remains bounded to local skill-route validation.
- `InternScience/Agents-A1`: public repository evidence exposes long-horizon agent and evaluation claims, so it needs local agent-harness evaluation before behavior adoption.
- `QwenLM/Qwen-AgentWorld`: public repository evidence exposes agent-world and evaluation framing, so it needs local agent-harness evaluation before behavior adoption.
- `TianhangZhuzth/Fundamental-Ava`: public repository evidence exposes collaborative general-agent framing, so it needs local agent-harness evaluation before behavior adoption.

## Hypothesis

Pass 2 of the skill-route-discovery slice should convert adjacent general-agent evidence into a fixture-ready local agent-harness queue instead of leaving it as only a broad review note.

## Change

- Added a digest-specific pass-2 queue surface: `agent_harness_eval_queue`.
- The queue declares scenario classes, required fixture fields, expected measurable outcome, rollback expectation, controller approval gate, validation propagation, and denied escalation flags.
- Added a frozen local fixture and regression test for `github-growth-20260706T203555.443958Z`.
- Updated `docs/skill-route-discovery.md` with replay instructions.

## Rollback

Rollback ref: `refs/rollback/20260706T203554Z-skill-route-discovery-pass2-agent-harness-eval`

Artifact: `artifacts/rollback/20260706T203554Z-skill-route-discovery-pass2-agent-harness-eval/rollback-point.md`

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260706T203555 or 20260706T201555"
```

Result: `2 passed, 348 deselected`.

```powershell
python -m ruff check src\blackhole_agent\skill_routing.py tests\test_skill_routing.py
```

Result: `All checks passed!`.

## Review Notes

- No self-model edit was needed; the existing preference for rollback-backed local validation matches this behavior change.
- No runtime, provider, external harness, external skill activation, remote execution, profile write, or memory write path was enabled.
- Raw source URLs and upstream bodies are not exported by the new queue surface.
