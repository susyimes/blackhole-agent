# Rollback point

- Created at: 20260713T121417Z
- Original branch: grok/blackhole-evolve/20260713T041209.269566-bound-skill-route-discovery-against-lingbol088-s
- HEAD: 89389c9192566dbce57e4e09c8061ea7221a68a4
- Local rollback ref: refs/blackhole-rollback/20260713T121417Z
- Purpose: reverse-flow continue binding + partial command-hash retention before residual export

## Recovery

`
git switch grok/blackhole-evolve/20260713T041209.269566-bound-skill-route-discovery-against-lingbol088-s
git reset --hard refs/blackhole-rollback/20260713T121417Z
`

Or:

`
git checkout refs/blackhole-rollback/20260713T121417Z -- .
`

Rollback execution is explicit and destructive; only run when an operator chooses recovery.
