# Run notes: reverse-flow residual selection hold

- Digest: github-growth-20260713T031123.591532Z
- Branch: grok/blackhole-evolve/20260713T031208.074727-continue-reverse-flow-skill-route-discovery-on-t
- Proposal: prop-reverse-flow-skill-route-test (residual fortress adjacent)
- Rollback: refs/blackhole-rollback/20260713T111443Z

## Hypothesis

While reverse-flow focused validation is ready/unrecorded, residual stage
packets still pre-exported fortress selected_residual_proposal_id even though
render suppressed residual selection. Operators and automated consumers reading
residual apply/comparison packets could treat fortress as selected before
reverse-flow record/close and activation-external acceptance.

## Change

Suppress residual fortress/Hy3 selection export until residual work is residual-active.
Extend residual hold active while reverse-flow focused validation is failed.

## Validation

pytest tests/test_github_growth.py -q -k skill_route_discovery → 17 passed
pytest tests/test_docs_contracts.py -q -k skill_route → 24 passed
