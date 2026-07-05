# Rollback Point

- Source digest: `github-growth-20260705T110958.050064Z`
- Branch before edits: `codex/blackhole-evolve/20260705T111052.831748-create-or-extend-a-local-agent-harness-evaluatio`
- HEAD before edits: `aa48fb8ec7e2c675cc4fccabc0278e7f14075365`
- Local rollback ref: `refs/rollback/blackhole-agent/20260705T110956Z`

Recovery commands, if an operator chooses destructive rollback:

```powershell
git reset --hard refs/rollback/blackhole-agent/20260705T110956Z
git clean -fd
```

This artifact is retained by the run that created it. Rollback execution is explicit and destructive.
