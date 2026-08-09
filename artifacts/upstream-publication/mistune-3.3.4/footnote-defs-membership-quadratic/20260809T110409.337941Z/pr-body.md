## Summary

Inline footnote parsing does O(n) list membership per reference (quadratic DoS on n footnote references)

## Evidence

- Defect reproduced on the true upstream source at release tag `v3.3.4` (`reproduced_at_tag: True`).
- HEAD triage at time of verification: `unfixed_at_head` (ref `HEAD`).
- Pristine suite baseline: 1155 passed, 0 failed.
- Patched suite (this change + the regression test): 1156 passed, 0 failed.

The regression test `test_contribution_footnote_defs_membership_quadratic.py` is installed under the project's own test conventions and fails before the patch / passes after it.

## Reproduction

A minimized standalone repro (`footnote_defs_quadratic.py`) doubles the input size and measures the growth exponent; it flags superlinear growth pre-patch and passes post-patch.

## Provenance and disclosure

This pull request was prepared by an autonomous stewardship agent ([blackhole-agent](https://github.com/susyimes/blackhole-agent)). The defect was discovered, minimized, repaired, and verified by that agent; a human operator runs the mission runtime.

Sealed evidence bundle digests (sha256):

- `contribution.patch`: `8a758bb485f192f4fd12c0e1241b4b79f3fcf6b13a3856046a0821ebb0dbea37`
- `footnote_defs_quadratic.py`: `855ff503fd2fe4010a8b0fce332657479aa6fe24de29fdc6f9255b150c9b19d2`
- `test_contribution_footnote_defs_membership_quadratic.py`: `2588f06ca2b93548bdfb0ff13e9b75719e0128b1d7120334bcfbf22aa12194e3`

These digests seal the exact patch, regression test, and repro this PR carries, so the evidence chain can be re-checked byte-for-byte.
