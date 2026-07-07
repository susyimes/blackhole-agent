# Rollback Point

- Original branch: codex/blackhole-evolve/20260707T001645.475452-add-or-strengthen-local-tests-for-provider-confi
- HEAD: 4781c1d31a8972bd5d0d4fc90b25caf449c8a728
- Local rollback ref: refs/rollback/20260707T001554Z-provider-cli-empty-envelope-preflight

Recovery commands (destructive, operator-run only):

```powershell
git switch codex/blackhole-evolve/20260707T001645.475452-add-or-strengthen-local-tests-for-provider-confi
git reset --hard 4781c1d31a8972bd5d0d4fc90b25caf449c8a728
git clean -fd
```
