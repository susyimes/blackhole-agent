# Skill Route Discovery Pass 2 Local Lanes

Source digest: `github-growth-20260629T091323.954837Z`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/ksimback/looper`

The review stayed at repository-level route evidence. No upstream bodies were imported into runtime behavior, no external repositories were installed or executed, and no provider/runtime lane was added.

## Hypothesis

The active pass-2 slice should expose both skill-workflow evidence and adjacent general-agent evidence in one replayable local lane. COMPASS and zhengxi-views can validate bounded `skill_route_discovery` lanes, while Qwen-AgentWorld and looper should remain separate `agent_harness_eval_required` rows until a local harness characterization exists.

## Change

- Added `tests/fixtures/skill_route_discovery/current_digest_20260629T091323_pass2_local_skill_route_lane.json`.
- Updated `current_digest_pass2_local_validation_lane` so focused review emits distinct adjacent general-agent rows for Qwen-AgentWorld and looper.
- Kept same-project adjacent evidence deduplicated by proposal ID, so multiple Qwen records do not create duplicate proposal rows.
- Added regression coverage for the current pass-2 fixture.

## Boundary Notes

`skill_route_discovery` still maps only to `documentation`, `config`, `test`, or `code_patch`. Qwen-AgentWorld and looper do not inherit skill-route authority, direct runtime routing, direct code-patch authority, external harness execution, provider launch, or remote execution.

The AutoCVE proposal is security-adjacent and remains review-only under `offensive-behavior-human-review`. This run did not implement attack, exploit, malware, phishing, exfiltration, unauthorized-access, or offensive behavior.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260629T063941_pass2 or 20260629T091323_pass2 or current_digest_pass2_active_slice_review"` -> passed, 3 tests.
- `python -m pytest tests/test_skill_routing.py -q` -> passed, 100 tests.
