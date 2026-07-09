# Rollback Point: provider-runtime-control pass 1

- Created at: 2026-07-09T08:55:25Z
- Original branch: codex/blackhole-evolve/20260709T085622.622182-add-or-extend-a-local-skill-route-discovery-prob
- Original HEAD: 8b42203a02ba16e19c433f50e376c51d2fa5734f
- Rollback ref: refs/blackhole-agent/rollback/20260709T085525Z-provider-runtime-control-pass1
- Source digest: github-growth-20260709T085527.278985Z
- Capability theme: provider-runtime-control

Recovery commands, for an explicit operator rollback only:

```powershell
git switch codex/blackhole-evolve/20260709T085622.622182-add-or-extend-a-local-skill-route-discovery-prob
git reset --hard refs/blackhole-agent/rollback/20260709T085525Z-provider-runtime-control-pass1
```

Do not run these commands automatically from inside the kernel.
