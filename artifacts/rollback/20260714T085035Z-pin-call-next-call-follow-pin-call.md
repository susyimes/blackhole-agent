# Rollback point

- Created (UTC): 20260714T085035Z
- Original branch: grok/blackhole-evolve/20260714T084850.949443-continue-reverse-flow-skill-route-discovery-agai
- HEAD: 07638abf7d0a50dd0dae29527c9b8d6f6854e269
- Local rollback ref: refs/blackhole/rollback/20260714T085035Z
- Source digest: github-growth-20260714T084752.684674Z
- Hypothesis: After pin_call_next_call_follow_pin classifies a pin recipe, supervisors still re-compare nested pre/post pin packets after continue wakes. Package pin_call_next_call_follow_pin_call as a body-free pre→post pin call receipt so supervisors pin one call receipt instead of re-deriving pin transitions.

## Recovery commands

```
git checkout grok/blackhole-evolve/20260714T084850.949443-continue-reverse-flow-skill-route-discovery-agai
git reset --hard refs/blackhole/rollback/20260714T085035Z
# or: git reset --hard 07638abf7d0a50dd0dae29527c9b8d6f6854e269
```

Do not run recovery unless an operator or supervisor explicitly chooses rollback.
