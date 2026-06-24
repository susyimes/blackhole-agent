# Self-Evolution Run Notes

Source digest: `github-growth-20260624T155904.194675Z`
Branch: `codex/blackhole-evolve/20260624T160027.629159-add-or-extend-local-tests-that-exercise-the-agen`
Capability theme: `skill-route-discovery`
Planned pass: 2 of 4

## Rollback

- Artifact: `artifacts/rollback/20260624T155904Z-skill-route-pass2-replay-queue.md`
- Ref: `refs/rollback/20260624T155904Z-skill-route-pass2-replay-queue`
- Original HEAD: `6247cba45b4c998ceb550ae344b7e5f56951d3a7`

## Evidence Reviewed

- `https://github.com/omnigent-ai/omnigent`: public meta-harness with multi-agent orchestration, policy, sandbox, cloud, and provider/tool surfaces.
- `https://github.com/omnigent-ai/omnigent/pull/1131`: MCP server add/remove PR with explicit bundle round-trip tests and blocking review findings.
- `https://github.com/dongshuyan/compass-skills`: skill ecosystem with local task memory, handoff, profile, safety, and install guidance; used only as route-shape evidence.
- `https://github.com/lyra81604/zhengxi-views`: source-cited domain research skill signal with advice boundary; used only as bounded local validation evidence.

## Hypothesis

Pass-2 skill-route discovery already maps route profiles into bounded lanes, but the shared replay queue should expose the changed-file review contract directly. A supervisor should not have to infer local artifact targets from another panel before deciding whether a selected or queued lane is replayable.

## Change

- Added `skill_route_discovery_local_artifact_review_packet` to summarize the local artifact kind, target path hashes, review requirements, and runtime/external-action denials for a bounded lane.
- Threaded that packet into `skill_route_discovery_pass_validation_replay_queue`.
- Propagated it into pass-2 handoff checkpoints, bounded activation preview, and local lane acceptance gates.
- Updated tests to assert artifact-review readiness, hashed target paths, and operator review requirements.
- Documented the new pass-2 replay queue contract in `docs/skill-route-discovery.md`.

## Validation

- `python -m ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py` passed.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass2 or pass_validation_replay_queue or pass3_selects_bounded_lane"` passed: 3 passed, 150 deselected.
- `python -m pytest tests/test_harness_eval.py -q` passed: 153 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed: 2 passed, 9 deselected.

## Self-Model

Read `docs/self-model.md` before selecting the change. Left it unchanged because the current preference already favors rollback-backed, locally validated behavior changes over ornamental self-description edits, and this run had a concrete safe behavior path.

## Review Notes

- No upstream skill code, install scripts, prompt bodies, MCP server configs, providers, external harnesses, or remote actions were executed.
- The new packet exports only hashes, counts, lane names, and boolean denials; raw target paths, source URLs, evidence URLs, and upstream bodies remain omitted from replay surfaces.
- Provider/config preflight deployment evidence remains review-only where privacy leakage could be involved.
