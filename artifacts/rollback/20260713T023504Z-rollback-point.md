# Rollback Point

- Created at: 20260713T023504Z
- Original branch: grok/blackhole-evolve/20260712T183354.303688-select-hy3-as-the-agent-harness-eval-cluster-loc
- Prepared evolution branch: grok/blackhole-evolve/20260712T183354.303688-select-hy3-as-the-agent-harness-eval-cluster-loc
- HEAD at rollback: ed7015bad45a2a91da36b775752b431f31544007
- Local rollback ref: refs/blackhole/rollback/20260713T023504Z

## Recovery commands

```text
git switch grok/blackhole-evolve/20260712T183354.303688-select-hy3-as-the-agent-harness-eval-cluster-loc
git reset --hard refs/blackhole/rollback/20260713T023504Z
# or: git reset --hard ed7015bad45a2a91da36b775752b431f31544007
```

Rollback is explicit and destructive. A human operator or external supervisor must choose it before reset or clean commands run. Do not delete this artifact during the run that created it.
