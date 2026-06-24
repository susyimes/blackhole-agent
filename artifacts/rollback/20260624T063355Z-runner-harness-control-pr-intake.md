# Rollback Point: Runner Harness Control PR Intake

- Created at: `2026-06-24T06:33:55Z`
- Original branch: `codex/blackhole-evolve/20260624T063500.912461-document-a-local-validation-checklist-for-pull-r`
- Original HEAD: `9eee7af9a053c741f3fa146806b4b9b3ab8efc99`
- Rollback ref: `refs/blackhole-rollback/20260624T063355Z-runner-harness-control-pr-intake`
- Source digest: `github-growth-20260624T063355.562521Z`

## Recovery Commands

Rollback is explicit and destructive. Run only after operator approval:

```powershell
git switch codex/blackhole-evolve/20260624T063500.912461-document-a-local-validation-checklist-for-pull-r
git reset --hard refs/blackhole-rollback/20260624T063355Z-runner-harness-control-pr-intake
git clean -fd
```

## Notes

This rollback point was created before modifying runner-harness-control PR intake behavior, fixtures, docs, or run artifacts.
