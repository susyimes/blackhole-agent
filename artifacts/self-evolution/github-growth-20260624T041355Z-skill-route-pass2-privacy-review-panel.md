# Skill Route Discovery Pass 2 Privacy Review Panel

- Source digest: `github-growth-20260624T041355.319894Z`
- Capability theme: `skill-route-discovery`
- Rollback ref: `refs/blackhole-rollback/20260624T041354Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260624T041354Z-skill-route-discovery-pass2.md`

## Evidence Reviewed

- `https://github.com/omnigent-ai/omnigent`: generic harness/runtime movement kept as secondary context only for this pass.
- `https://github.com/omnigent-ai/omnigent/pull/1084`: provider-token and usage-tracking evidence kept review-only at the privacy boundary.
- `https://github.com/baskduf/FableCodex`: Codex workflow skill evidence kept in bounded local lanes.
- `https://github.com/dongshuyan/compass-skills`: state/profile handoff evidence mapped to a local config lane with privacy review.

## Hypothesis

The active pass should make privacy-sensitive skill-route evidence visible in
the same lane-map artifact that already exposes bounded local validation lanes.
This gives the supervisor a concrete review surface for state/profile and
domain/advice boundaries without logging sensitive values or activating external
skills.

## Actions

- Added `privacy_review_panel` to `build_skill_route_discovery_proposal_lane_map`.
- Derived review rows only from existing candidate inventory, route profiles,
  state/profile boundary metadata, and domain research boundary metadata.
- Kept rows body-free: candidate sources are hashed and raw source URLs,
  evidence URLs, target paths, upstream bodies, and sensitive values are not
  exported.
- Added regression coverage using the pass-2 four-item evidence fixture.
- Documented the panel in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged because it already describes this
  rollback-backed local evolution preference and the privacy-leakage review
  boundary.

## Validation

Focused validation passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k privacy_review_panel
python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery
python -m pytest tests/test_skill_routing.py -q
```

## Review Notes

- Privacy-leakage proposals remain review-only; this run did not expose, log,
  print, upload, publish, or share tokens, credentials, secrets, private keys,
  private chats, PII, or personal data.
- The new panel is not an activation grant. Runtime action, external skill
  activation, external harness execution, provider launch, profile writes,
  memory writes, remote execution, raw source URL export, raw evidence URL
  export, raw target path export, upstream body export, and sensitive value
  export remain denied.
