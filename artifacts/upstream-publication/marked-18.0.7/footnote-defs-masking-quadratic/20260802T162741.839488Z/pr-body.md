## Summary

inlineTokens rebuilds the reflink-mask preamble per call (Object.keys over all link defs), making n refs + n defs O(n^2) (measured exponent 3.0, 24s at n=13000)

## Evidence

- Defect reproduced on the true upstream source at release tag `18.0.7` (`reproduced_at_tag: True`).
- HEAD triage at time of verification: `unfixed_at_head` (ref `HEAD`).
- Pristine suite baseline: 1955 passed, 0 failed.
- Patched suite (this change + the regression test): 1957 passed, 0 failed.

The regression test `inlineTokens-masking.test.js` is installed under the project's own test conventions and fails before the patch / passes after it.

## Reproduction

A minimized standalone repro (`footnote_defs.cjs`) doubles the input size and measures the growth exponent; it flags superlinear growth pre-patch and passes post-patch.

## Provenance and disclosure

This pull request was prepared by an autonomous stewardship agent ([blackhole-agent](https://github.com/susyimes/blackhole-agent)). The defect was discovered, minimized, repaired, and verified by that agent; a human operator runs the mission runtime.

Sealed evidence bundle digests (sha256):

- `contribution.patch`: `46c2d7c3b2a6e1f41ea3bd8f2ee7b0e0a0bb3e9a9367caa361f25ca974b87d20`
- `footnote_defs.cjs`: `606edf1f5e14e3fcc32da2912b9b230247361b87cf19464aee79a39a00df471f`
- `inlineTokens-masking.test.js`: `af5a9ef040cb19b55f9ea6a774ed54ab11d7149200314c1c310989b1f5ffd3a4`

These digests seal the exact patch, regression test, and repro this PR carries, so the evidence chain can be re-checked byte-for-byte.
