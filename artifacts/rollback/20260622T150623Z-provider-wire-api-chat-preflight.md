# Rollback Point: provider wire API chat preflight

- Source digest: `github-growth-20260622T150624.464696Z`
- Capability theme: `skill-route-discovery`, pass 4 of 4
- Original branch: `codex/blackhole-evolve/20260622T150834.660318-add-or-strengthen-local-validation-for-provider-`
- Original HEAD: `764fe7f82a8cfeb859c55534dc6cfdc988a4ea8b`
- Local rollback ref: `refs/blackhole-rollback/20260622T150623Z-provider-wire-api-chat-preflight`

Recovery commands, if an operator chooses destructive rollback:

```bash
git switch codex/blackhole-evolve/20260622T150834.660318-add-or-strengthen-local-validation-for-provider-
git reset --hard refs/blackhole-rollback/20260622T150623Z-provider-wire-api-chat-preflight
```

This rollback point was created before editing provider runtime preflight behavior for a metadata-only `wire_api: chat` validation lane.
