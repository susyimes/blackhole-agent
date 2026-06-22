# Rollback Point: provider runtime control pass 1

- Source digest: `github-growth-20260622T152624.283851Z`
- Capability theme: `provider-runtime-control`, pass 1 of 4
- Original branch: `codex/blackhole-evolve/20260622T152912.304407-add-a-local-provider-config-preflight-lane-for-c`
- Original HEAD: `628be21b2a1a4a5cc49f5c46e6db5c1946986271`
- Local rollback ref: `refs/rollback/20260622T152623Z-provider-runtime-control-pass1`

Recovery commands, if an operator chooses destructive rollback:

```bash
git switch codex/blackhole-evolve/20260622T152912.304407-add-a-local-provider-config-preflight-lane-for-c
git reset --hard refs/rollback/20260622T152623Z-provider-runtime-control-pass1
```

This rollback point was created before editing provider runtime preflight behavior for a metadata-only configurable auth-header validation lane.
