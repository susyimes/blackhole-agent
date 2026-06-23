# Rollback Point

Run: github-growth-20260623T043652.610653Z
Created: 2026-06-23T04:36:51Z
Original branch: `codex/blackhole-evolve/20260623T043827.246447-add-or-extend-local-validation-covering-provider`
Original HEAD: `46e5a6c5b4b53edb483cdd2385ece16e330d7681`
Local rollback ref: `refs/rollback/20260623T043651Z-provider-runtime-control-pass1-wire-api-chat`

Recovery commands, explicit and destructive:

```powershell
git switch codex/blackhole-evolve/20260623T043827.246447-add-or-extend-local-validation-covering-provider
git reset --hard refs/rollback/20260623T043651Z-provider-runtime-control-pass1-wire-api-chat
```

Do not run rollback unless a human operator or external supervisor policy chooses recovery.
