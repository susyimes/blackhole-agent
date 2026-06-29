# Skill Route Discovery Pass 1: Progressive Package Contract

- Source digest: `github-growth-20260629T081941.626098Z`
- Capability theme: `skill-route-discovery`
- Rollback artifact: `artifacts/rollback/20260629T170627Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260629T170627Z-skill-route-discovery-pass1`

## Evidence Reviewed

- Primary proposal evidence: `https://github.com/lyra81604/zhengxi-views`
- Reusable pattern extracted: a skill package can expose a root skill entry point, root manifest, references directory, and validation scripts. That shape should be validated through bounded local lanes before activation.
- Narrow metadata check: the public repository tree contains `SKILL.md`, `skill.yml`, `references/`, and `scripts/` paths. No upstream bodies were imported or executed.

## Hypothesis

If body-free route discovery can recognize a root-manifest-plus-references skill package, the controller can surface a progressive validation contract before activation instead of treating the package as a generic skill workflow or relying on later operator inference.

## Local Change

- Added `reference_directory`, `skill_manifest`, and `progressive_skill_package` source signals.
- Added `progressive_skill_package_contract` to candidate inventory and proposal lane rows when the body-free source shape supports it.
- Kept the contract bounded to documentation, config, and test preferences, with runtime action and external activation denied.
- Added a regression test with a zhengxi-views-shaped repository summary.
- Updated `docs/skill-route-discovery.md` with the pass-1 interpretation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q` passed: 99 tests.

## Review Notes

- The self-model was read and left unchanged. It already supports rollback-backed local behavior changes and did not need a new permission or preference structure.
- `Qwen-AgentWorld` and `looper` stayed adjacent general-agent evidence for this pass. They were not used as direct skill-route activation evidence.
- No upstream repository bodies, target paths, raw evidence URLs, external harnesses, provider runtimes, or remote execution paths are exported or activated by this change.
