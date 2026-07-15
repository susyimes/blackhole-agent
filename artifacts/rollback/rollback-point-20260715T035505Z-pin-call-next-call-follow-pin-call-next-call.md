# Rollback Point

- Created at (UTC): 20260715T035505Z
- Original branch: grok/blackhole-evolve/20260715T035229.057244-run-skill-route-discovery-against-pluviobyte-rns
- HEAD at creation: 8c3685d80111ce45487d8ffe44a79ab402702a3a
- Local rollback ref: refs/blackhole-rollback/20260715T035505Z-pin-call-next-call-follow-pin-call-next-call
- Rollback SHA: 8c3685d80111ce45487d8ffe44a79ab402702a3a
- Run theme: skill-route-discovery pin_call_next_call (pre/post next-invoke call receipt)
- Source digest: github-growth-20260715T035131.989105Z
- Prepared branch: grok/blackhole-evolve/20260715T035229.057244-run-skill-route-discovery-against-pluviobyte-rns

## Recovery commands

```powershell
git switch grok/blackhole-evolve/20260715T035229.057244-run-skill-route-discovery-against-pluviobyte-rns
git reset --hard refs/blackhole-rollback/20260715T035505Z-pin-call-next-call-follow-pin-call-next-call
# or: git reset --hard 8c3685d80111ce45487d8ffe44a79ab402702a3a
```

Do not run these automatically. Rollback is explicit and destructive; a human operator or external supervisor must choose it.
