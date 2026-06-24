# Upstream Evidence Capability Pass 4

- Source digest: `github-growth-20260624T061355.549523Z`
- Capability theme: `upstream-evidence-capability`
- Selected proposal: `p1-skill-route-discovery`
- Rollback artifact: `artifacts/self-evolution/github-growth-20260624T061355Z-upstream-evidence-capability-pass4-rollback.md`
- Rollback ref: `refs/blackhole-rollback/20260624T061354Z`

## Evidence

- `https://github.com/baskduf/FableCodex` shows a Codex skill/workflow repository shape: plugin metadata, docs, evals, examples, and tests.
- `https://github.com/omnigent-ai/omnigent` remains a broader agent framework/meta-harness signal. It is relevant watchlist evidence, but generic movement is not enough to drive skill-route code changes without concrete route hints or local code matches.

## Hypothesis

The final pass for skill-route discovery should expose one body-free completion gate that says whether the current upstream evidence window has representative route-profile coverage before supervisor handoff. This turns upstream repository signals into a local capability check instead of another standalone note.

## Change

- Added `current_window_evidence_gate` to `skill_route_discovery_completion_report`.
- The gate checks required final-pass route profiles, selected digest evidence refs, and hashed evidence URL presence.
- Completion is blocked if an enforced final evidence window misses route profiles or evidence refs.
- The panel exports hashes only and keeps runtime action, external skill activation, external harness execution, provider launch, remote execution, raw URL export, and upstream body export denied.
- Documented the panel in `docs/skill-route-discovery.md`.

## Validation

- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_completion_report_surfaces_local_lane_closure or capability_window_handoff or completion_accepts_required_profile_coverage or profile_completion"`: passed, 3 tests.
- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.

## Review Notes

- Self-model was read and left unchanged. It already says locally validated behavior changes are preferred over validation-report-only work, which matches this run.
- No upstream code, skill bodies, provider runtime, external harness, or raw GitHub URL payloads were imported or activated.
- Omnigent generic movement remains supporting context for agent-harness review, not a skill-route activation signal.
