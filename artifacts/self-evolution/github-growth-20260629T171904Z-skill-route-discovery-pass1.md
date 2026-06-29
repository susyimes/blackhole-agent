# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260629T171904.272271Z`
- Theme: `skill-route-discovery`
- Hypothesis: the current COMPASS and zhengxi skill evidence should produce a replayable pass-1 local validation lane, while Qwen-AgentWorld and looper remain adjacent harness-eval rows with no inherited skill-route authority.
- Evidence URLs reviewed: `https://github.com/dongshuyan/compass-skills`, `https://github.com/lyra81604/zhengxi-views`, `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/ksimback/looper`
- Rollback artifact: `artifacts/rollback/20260629T171904Z-skill-route-discovery-pass1.md`

## Change

Added a digest-specific pass-1 route surface for
`github-growth-20260629T171904.272271Z`. The lane maps
`p1-skill-route-discovery-compass` to the local test lane, maps
`p2-generic-skill-workflow-zhengxi` to the documentation lane, and keeps
Qwen-AgentWorld and looper as separate `agent_harness_eval_required` rows under
their active proposal IDs.

The new fixture is body-free and offline. It carries selected item IDs,
route-profile metadata, unsupported-lane pressure, and proposal IDs, but the
operator packet continues to deny runtime action, upstream skill activation,
external harness execution, provider launch, profile writes, memory writes,
remote execution, raw source URL export, raw evidence URL export, target-path
export, replay-command export, and upstream body export.

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference for
rollback-backed local evolution already matches this run; no narrower
self-description was needed to explain the selected change.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 171904
python -m pytest tests/test_skill_routing.py -q -k "current_digest_20260629T101324_pass1"
python -m pytest tests/test_skill_routing.py -q
git diff --check
```

`git diff --check` reported only working-copy LF-to-CRLF warnings for touched
text files.
