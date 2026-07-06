# Rollback Point

- Run: github-growth-20260706T223555.499005Z
- Branch: codex/blackhole-evolve/20260706T223652.924540-add-or-extend-a-local-agent-harness-evaluation-m
- Original HEAD: f48e2eee9b5f568bb0ed0b40a198ae1e9fed72f3
- Rollback ref: refs/rollback/blackhole-evolve-20260706T223555-pass4

Recovery commands, if an operator explicitly chooses destructive rollback:

```powershell
git reset --hard refs/rollback/blackhole-evolve-20260706T223555-pass4
git clean -fd
```

This artifact must remain available for the run that created it.
