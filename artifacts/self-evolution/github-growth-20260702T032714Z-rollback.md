# Rollback Point

Source digest: `github-growth-20260702T032714.646827Z`
Run started: `2026-07-02T03:27:14.646827Z`

Original branch:
`codex/blackhole-evolve/20260702T032810.373386-add-or-extend-local-tests-that-verify-repositori`

Original HEAD:
`a73c11fb9f20505ca031a038c7a21585d509e715`

Local rollback ref:
`refs/blackhole-rollback/20260702T032713Z`

Recovery commands, if an operator chooses destructive rollback:

```powershell
git switch codex/blackhole-evolve/20260702T032810.373386-add-or-extend-local-tests-that-verify-repositori
git reset --hard refs/blackhole-rollback/20260702T032713Z
```

Notes:
- This run must not delete this artifact or the rollback ref.
- Rollback is explicit and destructive; no automatic reset is performed by the kernel.
