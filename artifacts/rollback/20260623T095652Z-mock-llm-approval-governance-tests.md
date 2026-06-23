# Rollback Point: Mock LLM Approval Governance Tests

- Source digest: `github-growth-20260623T095652.910713Z`
- Original branch: `codex/blackhole-evolve/20260623T095818.496571-add-or-extend-local-tests-for-mock-llm-approval-`
- Original HEAD: `ef8dab8e6e267a288fcfb5bfbf4db371b0bfff77`
- Local rollback ref: `refs/rollback/blackhole-agent/20260623T095652Z`

Recovery commands, for an explicit human or supervisor rollback only:

```powershell
git reset --hard refs/rollback/blackhole-agent/20260623T095652Z
git clean -fd
```

Review note: rollback is destructive and must not be executed by this kernel
run without an external rollback decision.
