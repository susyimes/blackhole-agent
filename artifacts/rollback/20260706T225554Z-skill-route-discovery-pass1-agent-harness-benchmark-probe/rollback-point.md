# Rollback Point

Run started from branch:
`codex/blackhole-evolve/20260706T225644.580557-create-or-extend-a-local-agent-harness-evaluatio`

Original HEAD:
`542267ab20ad5b250c6f2751dfc81c4516567b19`

Rollback ref:
`refs/blackhole/rollback/20260706T225554Z`

Recovery commands, if an external supervisor chooses destructive rollback:

```powershell
git fetch . refs/blackhole/rollback/20260706T225554Z
git reset --hard refs/blackhole/rollback/20260706T225554Z
```

This artifact must not be deleted by the run that created it.
