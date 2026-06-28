# Skill Route Discovery Pass 3 Profile Proof Checklist

Source digest: `github-growth-20260628T050729.790102Z`
Branch: `codex/blackhole-evolve/20260628T050826.944217-add-or-extend-local-tests-that-exercise-skill-ro`
Rollback ref: `refs/blackhole-rollback/20260628T050729Z-skill-route-discovery-pass3`
Rollback artifact: `artifacts/rollback/20260628T050729Z-skill-route-discovery-pass3.md`

## Evidence

- `https://github.com/dongshuyan/compass-skills` exposes a public skill ecosystem with skills, handoff, task memory, and collaboration profile signals.
- `https://github.com/lyra81604/zhengxi-views` exposes source-cited skill workflow and advice-boundary signals.
- `https://github.com/majidmanzarpour/threejs-game-skills` exposes Three.js browser-game skill workflow, QA, scaffold, and optional asset-workflow signals.

## Hypothesis

Pass-3 validation rows should not only say which lane is selected. They should also expose the profile-specific proof an operator must validate before activation, using local route-profile contracts instead of upstream skill bodies.

## Change

- Added derived `profile_validation_requirements` rows to `current_window_pass3_validation_cases`.
- Added regression coverage for game frontend and state handoff proof targets.
- Documented the current digest's profile proof checklist.

## Review Notes

- No upstream skill code, installer, scaffold, provider, or external harness was executed.
- Raw source URLs, evidence URLs, target paths, replay commands, and upstream bodies remain outside the pass-3 handoff.
- The self-model was read and left unchanged because the current preference already supports rollback-backed, locally validated behavior changes.
