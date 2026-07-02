# Rollback Point

- Created at: 2026-07-02T10:47:13Z
- Source digest: github-growth-20260702T104714.732349Z
- Branch: codex/blackhole-evolve/20260702T104805.105578-run-a-bounded-local-skill-route-discovery-evalua
- Original HEAD: 4767cb188a9ca6b85f6b9d565ef1276d13e71614
- Rollback ref: refs/rollback/20260702T104713Z-skill-route-discovery-pass3
- Self-model snapshot: docs/self-model.md sha256 ea29207d6adaa8f3d655b972b5eb47e15d0706947867bb05c953ae64a5a830d5

Recovery commands, if an operator explicitly chooses destructive rollback:

```powershell
git reset --hard refs/rollback/20260702T104713Z-skill-route-discovery-pass3
git clean -fd
```

Do not run these commands as part of the kernel pass. They are destructive and
reserved for an external operator or supervisor policy.
