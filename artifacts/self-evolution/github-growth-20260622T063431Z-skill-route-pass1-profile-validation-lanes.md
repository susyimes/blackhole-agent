# Self-Evolution Run: skill-route pass 1 profile validation lanes

- Source digest: github-growth-20260622T063431.555811Z
- Theme: skill-route-discovery
- Capability slice: Convert skill and route evidence into bounded local lanes that can be validated before activation.
- Rollback ref: refs/rollback/20260622T063430Z-skill-route-discovery-pass1
- Rollback artifact: artifacts/rollback/20260622T063430Z-skill-route-discovery-pass1.md
- Starting HEAD: 061912f30d1ff998a9451eca6e52d31f172060e0

## Evidence Reviewed

- https://github.com/dongshuyan/compass-skills
- https://github.com/majidmanzarpour/threejs-game-skills
- https://github.com/baskduf/FableCodex

The reviewed pages support the existing local interpretation: COMPASS is a
state/handoff skill ecosystem signal, Three.js Game Skills is a game/frontend
specialist workflow signal, and FableCodex is a Codex workflow-gate signal. The
evidence was used only as body-free route evidence; no upstream code, prompts,
installers, scaffolds, or runtime actions were adopted.

## Hypothesis

Pass-1 skill-route discovery is more operator-visible if the existing
profile-lane acceptance contract is summarized directly in the pass-1 validation
queue. The queue should show the profile-specific local lane for COMPASS,
Three.js, and FableCodex while preserving the bounded lane and no-runtime-action
contract.

## Change

- Added `profile_validation_lanes` to `pass1_validation_queue`.
- Each profile lane reports route profile, selected bounded lane, validation
  gate, proposal IDs, replay commands, first-route requirements, and explicit
  denial of runtime action, external skill activation, harness execution,
  provider launch, remote execution, raw source URL export, and upstream body
  export.
- Updated the focused pass-1 regression and documentation contract.
- Documented the new pass-1 lane panel in `docs/skill-route-discovery.md`.

## Validation

- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane"`: 9 passed, 111 deselected
- `pytest tests/test_skill_routing.py -q`: 27 passed
- `pytest tests/test_docs_contracts.py -q -k "skill_route_discovery"`: 2 passed, 7 deselected
- `git diff --check`: passed with existing CRLF conversion warnings only

## Review Notes

- Self-model decision: left `docs/self-model.md` unchanged. Its current
  preference for rollback-backed local behavior changes already matches this
  run, and the file remains descriptive rather than behavior-shaping.
- Remaining uncertainty: evidence is still repository-level public metadata.
  This change improves local handoff visibility; it does not claim upstream
  implementation parity or activate any external skill route.
