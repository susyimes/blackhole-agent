# Evolution: skill-route focused validation result recording

- UTC: 20260712T211454Z
- Digest: github-growth-20260712T211308.627162Z
- Proposal: prop-skill-reverse-flow-focused-test-validation
- Theme: skill-route-discovery (pass 4 complete; post-unlock result recording)
- Rollback: refs/blackhole-agent/rollback/20260712T211454Z-b3fcdc4

## Change summary
Added operator-visible result recording for reverse-flow focused local test validation:
- normalize_skill_route_discovery_focused_validation_command_results (body-free)
- record_skill_route_discovery_focused_local_test_validation_results (pipeline update)
- pipeline accepts focused_validation_command_results to close ready -> passed/failed
- focused validation commands now include the focused-validation pytest key
- proposal_track for focused surface: prop-skill-reverse-flow-focused-test-validation

## Validation
- pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation (and unlocked/pipeline): 8 passed
- pytest tests/test_docs_contracts.py -q -k skill_route: 24 passed
