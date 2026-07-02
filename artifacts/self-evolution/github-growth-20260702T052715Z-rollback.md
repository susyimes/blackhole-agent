# Rollback Point

- Source digest: `github-growth-20260702T052715.136537Z`
- Branch at start: `codex/blackhole-evolve/20260702T052801.389965-add-or-extend-local-tests-for-skill-route-discov`
- HEAD at start: `d601a28672dc991a0f141df14a782a27ec697b6a`
- Local rollback ref: `refs/rollback/github-growth-20260702T052715Z`

Recovery commands, if an operator explicitly chooses rollback:

```powershell
git update-ref refs/rollback/github-growth-20260702T052715Z d601a28672dc991a0f141df14a782a27ec697b6a
git reset --hard d601a28672dc991a0f141df14a782a27ec697b6a
```

This artifact records the recovery point for the pass-3 skill-route-discovery local validation change. It must not be deleted by the run that created it.
