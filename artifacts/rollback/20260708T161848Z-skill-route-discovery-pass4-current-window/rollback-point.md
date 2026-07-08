# Rollback Point

Run: `github-growth-20260708T161850.608560Z`

Theme: `skill-route-discovery`

Original branch: `codex/blackhole-evolve/20260708T161941.673308-add-or-extend-a-local-skill-route-discovery-test`

Original HEAD: `a8466ae68f71f27e6d5bb713c4f92ae5dffed04e`

Local rollback ref: `refs/rollback/20260708T161848Z-skill-route-discovery-pass4-current-window`

Recovery commands:

```powershell
git switch codex/blackhole-evolve/20260708T161941.673308-add-or-extend-a-local-skill-route-discovery-test
git reset --hard a8466ae68f71f27e6d5bb713c4f92ae5dffed04e
git clean -fd
```

Rollback execution is explicit and destructive; a human operator or external supervisor policy must choose it before these commands run.
