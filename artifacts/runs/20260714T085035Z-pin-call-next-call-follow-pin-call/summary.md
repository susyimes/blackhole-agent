# Run report: pin_call_next_call_follow_pin_call

- Digest: github-growth-20260714T084752.684674Z
- Proposal: prop-skill-reverse-flow-continue
- Hypothesis: After pin_call_next_call_follow_pin classifies a pin recipe, supervisors still re-compared nested pre/post pin packets. Packaging pin_call collapses those into one body-free call receipt.
- Rollback: refs/blackhole/rollback/20260714T085035Z / artifacts/rollback/20260714T085035Z-pin-call-next-call-follow-pin-call.md
- Validation: pytest focused suite passed (test_skill_route_discovery_focused_local_test_validation_after_unlocked_apply + test_docs_contracts)
- Safety: residual_export denied; runtime_action=none; no activation/push/remote
