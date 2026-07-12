# Rollback point

- Created: 20260713T041547Z
- Original branch: grok/blackhole-evolve/20260712T201402.254450-run-a-bounded-agent-harness-eval-local-compariso
- HEAD: 934918d9e65c279b344799e6c411e35ef9373d20
- Local rollback ref: refs/rollback/blackhole-agent/20260713T041547Z-skill-route-adjacent-fortress-handoff

## Recovery commands

```
git switch grok/blackhole-evolve/20260712T201402.254450-run-a-bounded-agent-harness-eval-local-compariso
git reset --hard refs/rollback/blackhole-agent/20260713T041547Z-skill-route-adjacent-fortress-handoff
```

Or:

```
git checkout refs/rollback/blackhole-agent/20260713T041547Z-skill-route-adjacent-fortress-handoff -- .
```

Do not delete this rollback artifact during the run that created it.
Rollback execution is explicit and destructive; a human operator or external supervisor must choose it.
