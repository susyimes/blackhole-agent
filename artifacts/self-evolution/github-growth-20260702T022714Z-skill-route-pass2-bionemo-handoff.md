# Skill Route Discovery Pass 2: BioNeMo Handoff

- Source digest: `github-growth-20260702T022714.857893Z`
- Capability window: `skill-route-discovery`, pass 2 of 4
- Rollback artifact: `artifacts/rollback-20260702T022810Z-skill-route-discovery-pass2.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260702T022810Z-skill-route-discovery-pass2`

## Evidence Reviewed

- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`

BioNeMo exposes agent-skill repository structure, plugin marketplace metadata,
workflow directories, and a skills catalog. zhengxi-views remains the
source-cited Agent Skill comparison case. Qwen-AgentWorld remains general-agent
project evidence without a skill-route hint.

## Change

- Added a current pass-2 fixture for `github-growth-20260702T022714.857893Z`.
- Extended `current_digest_pass2_local_validation_lane` to use the current
  proposal IDs and supervisor handoff for BioNeMo-style skill evidence.
- Added a regression test that verifies skill rows stay bounded to
  documentation, config, test, and code_patch, while Qwen-AgentWorld and
  Fundamental-Ava remain behind `agent_harness_eval_required`.
- Updated `docs/skill-route-discovery.md` with the current pass-2 behavior.

The lane remains body-free and denies install, runtime execution, provider
launch, external harness execution, remote execution, raw URL export, replay
command export, target-path export, and upstream-body export.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260702T022714 or 20260702T020714"
python -m pytest tests/test_skill_routing.py -q -k "current_digest_pass2_local_validation_lane or 20260702T022714"
python -m pytest tests/test_skill_routing.py -q
```

Result: all passed; final full module run reported `151 passed`.

## Review Notes

- The self-model was read and left unchanged. It already supports the current
  behavior: reversible, locally validated route evolution with a narrow safety
  boundary.
- No external repositories were cloned or executed.
- No activation, restart, push, provider launch, or remote execution was
  performed.
