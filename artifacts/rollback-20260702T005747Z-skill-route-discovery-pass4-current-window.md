# Rollback Point

- Source digest: `github-growth-20260702T005748.786759Z`
- Capability theme: `skill-route-discovery`
- Kernel branch: `codex/blackhole-evolve/20260702T005838.505791-add-or-run-a-bounded-local-skill-route-discovery`
- Original HEAD: `2ffc98dd7f143cada7280414c68366dd90e107a7`
- Local rollback ref: `refs/rollback/20260702T005747Z-skill-route-discovery-pass4-current-window`

Recovery commands, if an operator explicitly chooses destructive rollback:

```powershell
git update-ref refs/rollback/20260702T005747Z-skill-route-discovery-pass4-current-window 2ffc98dd7f143cada7280414c68366dd90e107a7
git reset --hard refs/rollback/20260702T005747Z-skill-route-discovery-pass4-current-window
```

This run must not execute the rollback commands. The ref records the original branch/head boundary for failed startup, broken imports, unsafe behavior, or post-activation recovery.
