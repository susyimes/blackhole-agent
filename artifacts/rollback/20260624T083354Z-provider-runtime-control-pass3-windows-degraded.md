# Rollback Point: provider runtime control pass 3 Windows degraded preflight

- Created at: 2026-06-24T08:33:54Z source wake
- Working branch: `codex/blackhole-evolve/20260624T083510.584540-add-or-extend-local-validation-coverage-for-skil`
- Original HEAD: `d38acfe88d4bb1db34674ad5922c8ffbf8864b4c`
- Rollback ref: `refs/rollback/20260624T083354Z-provider-runtime-control-pass3`
- Source digest: `github-growth-20260624T083355.863054Z`

Recovery commands, for an explicit destructive rollback decision only:

```powershell
git reset --hard refs/rollback/20260624T083354Z-provider-runtime-control-pass3
git clean -fd
```

This artifact must not be deleted by the run that created it.
