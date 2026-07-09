# Evolution Run: skill-route-discovery pass 2

- Source digest: `github-growth-20260709T075527.280528Z`
- Rollback artifact: `artifacts/rollback/20260709T075525Z-skill-route-discovery-pass2/rollback-point.md`
- Rollback ref: `refs/blackhole/rollback/20260709T075525Z-skill-route-discovery-pass2`
- Self-model decision: left unchanged; it already favors rollback-backed local validation over report-only evolution.

## Focused Evidence

- `lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow signal with a skill directory, activation phrase, local sandbox framing, staged workflow, and diagnostic scripts.
- `Pluviobyte/rnskill`: generic SKILL.md-compatible skills collection signal.
- `SmileLikeYe/agent-chief` and `Tencent-Hunyuan/Hy3`: general agent or model project signals without skill-package route evidence.

## Local Change

Added `current_digest_20260709T075527_pass2_validation_lane` to the skill-route discovery lane map. The lane keeps `reverse-flow-skill` in the local test lane, keeps `rnskill` in the documentation lane, and holds `agent-chief`/`Hy3` as adjacent `agent_harness_eval_required` rows with no direct local implementation lane before local harness evaluation.

The surface is metadata-only. It exports no raw source URLs, replay commands, target paths, upstream bodies, install/run/provider/runtime action, promotion, restart, or remote execution authority.

## Validation

Planned command:

```powershell
python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260709T075527
```
