# Skill Route Pass 2 Validation Lane

Source digest: `github-growth-20260707T084834.433829Z`
Capability slice: `skill-route-discovery`
Pass: 2 of 4

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/Pluviobyte/rnskill`
- `https://github.com/InternScience/Agents-A1`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/shepherd-agents/shepherd`

Reusable lesson: skill and workflow repository evidence can propose bounded
local documentation, config, test, or code_patch lanes, but install, run,
script execution, provider launch, external harness execution, and remote
execution remain diagnostic pressure until local validation or agent-harness
evidence exists.

## Local Change

- Added a current-digest pass-2 validation lane for
  `github-growth-20260707T084834.433829Z`.
- Added a fixture that binds the current proposal IDs to reverse-flow,
  rnskill, and adjacent general-agent route handling.
- Added tests that verify bounded lanes, no direct general-agent
  implementation lane before harness eval, no runtime action, and no raw URL or
  raw validation command export from controller output.
- Documented the operator-visible replay path.

## Rollback

Rollback artifact:
`artifacts/rollback/20260707T084929Z-skill-route-pass2-validation-lane.md`

Rollback ref:
`refs/blackhole-rollback/20260707T084929Z-skill-route-pass2-validation-lane`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T084834`
  - Initial run exposed a hash-format assertion mismatch after raw command
    export was removed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T054834 or 20260707T060834 or 20260707T082834 or 20260707T084834"`
  - Passed: 4 passed.
- `python -m pytest tests/test_skill_routing.py -q`
  - Passed: 370 passed.

## Review Notes

- Self-model was read and left unchanged; it already supports reversible,
  rollback-backed local behavior changes and did not need a new behavioral
  claim for this run.
- No upstream code was installed, cloned, or executed.
- No restart, push, promotion, provider launch, external harness execution, or
  remote execution was performed.
