# Rollback Point

source_digest: github-growth-20260627T084310.628741Z
original_branch: codex/blackhole-evolve/20260627T084448.644202-add-or-extend-local-tests-that-verify-repositori
original_head: 8b0bfeee2ba684d1afccd56d9eddc99570add4ba
local_rollback_ref: refs/rollback/20260627T084310Z-skill-route-discovery-pass4
created_at: 2026-06-27T08:43:10Z

Recovery commands, explicit and destructive if used:

```powershell
git switch codex/blackhole-evolve/20260627T084448.644202-add-or-extend-local-tests-that-verify-repositori
git reset --hard refs/rollback/20260627T084310Z-skill-route-discovery-pass4
git clean -fd
```

Do not run these commands unless a human operator or external supervisor chooses rollback.
