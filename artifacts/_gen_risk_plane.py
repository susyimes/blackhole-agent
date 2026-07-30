"""Generate risk plane over solvency by transforming the solvency plane block."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"


def transform(block: str) -> str:
    b = block
    # Phase 1: self-layer solvency → risk (longest first)
    self_reps = [
        ("SOLVENCY_BUNDLE_SCHEMA", "RISK_BUNDLE_SCHEMA"),
        ("SOLVENCY_CERTIFICATE_SCHEMA", "RISK_CERTIFICATE_SCHEMA"),
        ("SOLVENCY_LOG_SCHEMA", "RISK_LOG_SCHEMA"),
        ("DEFAULT_SOLVENCY_BUNDLE_RELATIVE", "DEFAULT_RISK_BUNDLE_RELATIVE"),
        ('Path("artifacts") / "solvency-bundles"', 'Path("artifacts") / "risk-bundles"'),
        ("solvency-bundles", "risk-bundles"),
        ("solvency_position_digest", "risk_assessment_digest"),
        ("parent_solvency_digest", "parent_risk_digest"),
        ("compute_solvency_position_digest", "compute_risk_assessment_digest"),
        ("default_solvency_bundle_dir", "default_risk_bundle_dir"),
        ("empty_solvency_log", "empty_risk_log"),
        ("compute_solvency_root", "compute_risk_root"),
        ("compute_solvency_certificate_hash", "compute_risk_certificate_hash"),
        ("compute_solvency_bundle_hash", "compute_risk_bundle_hash"),
        ("issue_solvency_certificate", "issue_risk_certificate"),
        ("verify_solvency_certificate", "verify_risk_certificate"),
        ("write_solvency_certificate", "write_risk_certificate"),
        ("_load_solvency_disk_evidence", "_load_risk_disk_evidence"),
        ("derive_solvency_specs_from_capital", "derive_risk_specs_from_solvency"),
        ("apply_solvency_transition", "apply_risk_transition"),
        ("verify_solvency_chain", "verify_risk_chain"),
        ("apply_capital_bundle_to_solvencies", "apply_solvency_bundle_to_risks"),
        ("build_solvency_bundle", "build_risk_bundle"),
        ("write_solvency_bundle", "write_risk_bundle"),
        ("load_solvency_bundle", "load_risk_bundle"),
        ("verify_solvency_bundle_integrity", "verify_risk_bundle_integrity"),
        ("rehydrate_solvency_bundle", "rehydrate_risk_bundle"),
        ("run_solvency_adversarial_checks", "run_risk_adversarial_checks"),
        ("run_solvency_plane", "run_risk_plane"),
        ("builtin_solvency_plane", "builtin_risk_plane"),
        ("proof-solvency", "proof-risk"),
        ("test-solvency", "test-risk"),
        ("tip_solvency_root", "tip_risk_root"),
        ("parent_solvency_root", "parent_risk_root"),
        ("solvency_root", "risk_root"),
        ("solvency_height", "risk_height"),
        ("solvency_hash", "risk_hash"),
        ("solvency_count", "risk_count"),
        ("solvency_certificate", "risk_certificate"),
        ("solvency_log", "risk_log"),
        ("solvency_plane", "risk_plane"),
        ("solvency_ok", "risk_ok"),
        ("solvency_done_when", "risk_done_when"),
        ("solvency_n", "risk_n"),
        ("solvency_path", "risk_path"),
        ("solvency_report", "risk_report"),
        ("min_solvencies", "min_risks"),
        ("want_solvencies", "want_risks"),
        ("multi_solvency", "multi_risk"),
        ("solvency_position", "risk_assessment"),
        ("solvencies", "risks"),
        ("solvency", "risk"),
        ("Solvency", "Risk"),
        ("SOLVENCY", "RISK"),
        ("solvent", "risked"),
        ("Solvent", "Risked"),
    ]
    for old, new in self_reps:
        b = b.replace(old, new)

    # Phase 2: parent capital → solvency
    parent_reps = [
        ("run_capital_plane", "run_solvency_plane"),
        ("load_capital_bundle", "load_solvency_bundle"),
        ("default_capital_bundle_dir", "default_solvency_bundle_dir"),
        ("capital_buffer_digest", "solvency_position_digest"),
        ("tip_capital_root", "tip_solvency_root"),
        ("bound_capital_root", "bound_solvency_root"),
        ("bound_capital_height", "bound_solvency_height"),
        ("capital_certificate_hash", "solvency_certificate_hash"),
        ("capital_certificate", "solvency_certificate"),
        ("capital_hash", "solvency_hash"),
        ("capital_count", "solvency_count"),
        ("capital_root", "solvency_root"),
        ("capital_height", "solvency_height"),
        ("capital_bundle", "solvency_bundle"),
        ("capital_report", "solvency_report"),
        ("capital_entries", "solvency_entries"),
        ("capital_path", "solvency_path"),
        ("capital_n", "solvency_n"),
        ("min_capitals", "min_solvencies"),
        ("want_capitals", "want_solvencies"),
        ("run_capital", "run_solvency"),
        ("post_capital", "post_solvency"),
        ("wrong_capital", "wrong_solvency"),
        ("capitalized", "solvent"),
        ("Capitalized", "Solvent"),
        ("parent_capitalized", "parent_solvent"),
        ("capitals", "solvencies"),
        ("capital", "solvency"),
        ("Capital", "Solvency"),
        ("CAPITAL", "SOLVENCY"),
    ]
    for old, new in parent_reps:
        b = b.replace(old, new)

    # Semantic / cleanup fixes
    fixes = [
        ("Closed risk plane: funding → multi-risk", "Closed risk plane: solvency → multi-risk"),
        ("Past risked positions", "Past solvent positions"),
        ("Past solvent positions: each solvency buffer", "Past solvent positions: each solvency position"),
        ("solvency buffers", "solvency positions"),
        ("margin-*.json", "risk-*.json"),
        ('candidates.extend(sorted(bundle_dir.glob("margin-*.json")', 'candidates.extend(sorted(bundle_dir.glob("risk-*.json")'),
        # return-dict: second self bundle key was "capital" then "solvency"; keep first parent, rename second
        # handled separately below
        ("duplicate_collateral_rejected", "duplicate_risk_rejected"),
        ("collateral_apply_failed", "risk_apply_failed"),
        ("missing_solvency_bind_fields", "missing_risk_bind_fields"),  # may already be missing_risk
        ("empty_risk_log", "empty_risk_log"),
        # goal mangling: "solvency over capital" became "risk over solvency" via solvency→risk, capital→solvency
        ('goal: str = "risk over solvency"', 'goal: str = "risk over solvency"'),
        ('or "risk over solvency"', 'or "risk over solvency"'),
        ('goal if goal else "solvency for risk"', 'goal if goal else "solvency for risk"'),
        # docstring for builtin
        (
            "Invocable capability: funding → multi-solvency deterministic buffers → prove.",
            "Invocable capability: solvency → multi-risk deterministic assessments → prove.",
        ),
        (
            "Invocable capability: funding → multi-risk deterministic buffers → prove.",
            "Invocable capability: solvency → multi-risk deterministic assessments → prove.",
        ),
        (
            "Invocable capability: solvency → multi-risk deterministic buffers → prove.",
            "Invocable capability: solvency → multi-risk deterministic assessments → prove.",
        ),
        # parent_margin variable is fine; fix parent_risk if needed
        ("parent_margin", "parent_risk"),
        ("parent_risk_stored", "parent_risk_stored"),
        # integrity keys from capital_certificate_valid became solvency_certificate_valid — good
        # risk_ok field from solvency_ok — good
        # BLACKHOLE_RISK_RUN_SOLVENCY from BLACKHOLE_SOLVENCY_RUN_CAPITAL: solvency→risk, capital→solvency
        # BLACKHOLE_RISK_MIN_RISKS from BLACKHOLE_SOLVENCY_MIN_SOLVENCIES
        # parent min: BLACKHOLE_CAPITAL_MIN_CAPITALS → BLACKHOLE_SOLVENCY_MIN_SOLVENCIES (good if CAPITAL→SOLVENCY and capitals→solvencies)
        # fix wrong: BLACKHOLE_SOLVENCY_MIN_SOLVENCIES for parent — capital's env was BLACKHOLE_CAPITAL_MIN_CAPITALS
        # After: BLACKHOLE_SOLVENCY_MIN_SOLVENCIES ✓
        # risk min was BLACKHOLE_SOLVENCY_MIN_SOLVENCIES → BLACKHOLE_RISK_MIN_RISKS ✓
        # BLACKHOLE_SOLVENCY_BUNDLE_PATH → BLACKHOLE_RISK_BUNDLE_PATH (self path)
        # parent capital path: BLACKHOLE_CAPITAL_BUNDLE_PATH → BLACKHOLE_SOLVENCY_BUNDLE_PATH
        # funding chain env left intact via capital plane's nested envs — they went through capital→solvency on some
    ]
    for old, new in fixes:
        b = b.replace(old, new)

    # Fix dual "solvency" keys in run_risk_plane return: parent report + self bundle.
    # Pattern after transform: first "solvency": None if solvency_report..., second "solvency": { ok: margin...
    # Rename the self-bundle key to "risk".
    marker = '"solvency": {\n            "ok": margin.get("ok"),'
    if marker in b:
        b = b.replace(marker, '"risk": {\n            "ok": margin.get("ok"),', 1)
    # Also handle if margin variable naming — leave as is (local var)

    # done_when should reference risk + solvency parent predicates
    old_dw = (
        '"no_skill_route; risk_ok; risked_ok; min_risks:2; '
        'risk_root_valid; solvency_ok; solvent_ok; min_solvencies:2; '
        'solvency_root_valid; chain_valid; capability_exists:repo.import-health"'
    )
    # After transform, solvency predicates became risk and capital→solvency:
    # "no_skill_route; risk_ok; risked_ok; min_risks:2; risk_root_valid; solvency_ok; solvent_ok; min_solvencies:2; solvency_root_valid; ..."
    # which is actually correct if solvent_ok came from capitalized_ok→solvent_ok.
    # capitalized_ok → solvent_ok (capitalized→solvent)
    # capital_ok → solvency_ok
    # capital_root_valid → solvency_root_valid
    # Good.

    # Fix position context key "position" → "assessment" for risk layer semantics
    b = b.replace(
        '"position": {\n            "ok": provisional_ok,\n            "risked": risked,\n            "risk_count": risk_n,\n            "risk_assessment_digest":',
        '"assessment": {\n            "ok": provisional_ok,\n            "risked": risked,\n            "risk_count": risk_n,\n            "risk_assessment_digest":',
    )

    # Fix facility/funding context that got partially mangled — leave mostly as inherited truthy context

    # Ensure file name pattern for risk bundles uses risk-hash
    b = b.replace(
        ' / f"margin-{margin.get(\'risk_hash\') or \'unknown\'}.json"',
        ' / f"risk-{margin.get(\'risk_hash\') or \'unknown\'}.json"',
    )
    b = b.replace(
        ' / f"margin-{margin.get(\'solvency_hash\') or \'unknown\'}.json"',
        ' / f"risk-{margin.get(\'risk_hash\') or \'unknown\'}.json"',
    )

    # Docstring accuracy
    b = b.replace(
        "multi-risk positions",
        "multi-risk assessments",
    )
    b = b.replace(
        "risk positions with risk assessment digests",
        "risk assessments with risk assessment digests",
    )
    b = b.replace(
        "Append one risk assessment bound to a solvency requirement root",
        "Append one risk assessment bound to a solvency position root",
    )
    b = b.replace(
        "Derive one risk assessment per solvency buffer",
        "Derive one risk assessment per solvency position",
    )
    b = b.replace(
        "multi-solvency required",
        "multi-solvency required",
    )
    b = b.replace(
        'outcome: "risked"',
        'outcome: "risked"',
    )
    b = b.replace(
        "plane\": \"risk\"",
        "plane\": \"risk\"",
    )

    # Fix missing_risk_bind_fields if double-mangled
    b = b.replace("missing_risk_bind_fields", "missing_risk_bind_fields")

    # parent_solvent from parent_capitalized — also parent_risked if solvent was in parent_capitalized? 
    # parent_capitalized → phase1 no change (no solvency) → phase2 capitalized→solvent → parent_solvent ✓

    # Fix env var chain for nested solvency plane in builtin:
    # Original solvency builtin:
    #   BLACKHOLE_SOLVENCY_RUN_CAPITAL → BLACKHOLE_RISK_RUN_SOLVENCY
    #   BLACKHOLE_CAPITAL_RUN_FUNDING → BLACKHOLE_SOLVENCY_RUN_FUNDING  (but solvency plane expects BLACKHOLE_SOLVENCY_RUN_CAPITAL for parent?)
    # Looking at solvency builtin:
    #   run_capital = BLACKHOLE_SOLVENCY_RUN_CAPITAL
    #   run_liquidity = BLACKHOLE_CAPITAL_RUN_FUNDING
    # After transform for risk:
    #   run_solvency = BLACKHOLE_RISK_RUN_SOLVENCY
    #   run_liquidity = BLACKHOLE_SOLVENCY_RUN_FUNDING  — WRONG, should remain BLACKHOLE_CAPITAL_RUN_FUNDING
    #   ...
    #   min_solvencies = BLACKHOLE_SOLVENCY_MIN_SOLVENCIES (from CAPITAL_MIN_CAPITALS)
    #   min_risks = BLACKHOLE_RISK_MIN_RISKS
    #   solvency_path = BLACKHOLE_SOLVENCY_BUNDLE_PATH (from CAPITAL)
    #   risk_path = BLACKHOLE_RISK_BUNDLE_PATH (from SOLVENCY)
    #
    # Nested envs that wrongly changed:
    # BLACKHOLE_CAPITAL_RUN_FUNDING → BLACKHOLE_SOLVENCY_RUN_FUNDING
    # BLACKHOLE_FUNDING_RUN_LIQUIDITY — unchanged (no capital/solvency)
    # Actually CAPITAL in BLACKHOLE_CAPITAL_RUN_FUNDING → SOLVENCY
    # We need to restore nested capital plane envs used by solvency plane.

    # Restore nested env names that risk plane should pass through unchanged to solvency plane
    env_restores = [
        ("BLACKHOLE_SOLVENCY_RUN_FUNDING", "BLACKHOLE_CAPITAL_RUN_FUNDING"),
        # solvency plane uses BLACKHOLE_SOLVENCY_RUN_CAPITAL for its parent; we call run_solvency_plane
        # with run_solvency= which is wrong param name - should be run_capital= for solvency plane API!
    ]
    for old, new in env_restores:
        b = b.replace(old, new)

    # CRITICAL: run_solvency_plane API still uses run_capital=, min_capitals=, capital_path=
    # Our transform renamed the *calls* parameters to run_solvency=, min_solvencies=, solvency_path=
    # which is WRONG for calling the existing solvency plane. Need to fix call-site kwargs to solvency plane.

    return b


def fix_parent_api_calls(b: str) -> str:
    """run_solvency_plane still expects capital-layer param names."""
    # Only fix within run_risk_plane's calls to run_solvency_plane — do surgical replacements
    # of kwargs that target the parent API.

    # The transformed call uses:
    #   run_solvency=run_solvency,  → should be run_capital=run_solvency
    #   min_solvencies=want_solvencies → min_capitals=want_solvencies? Wait solvency plane takes min_capitals for parent and min_solvencies for self
    # Looking at run_solvency_plane signature:
    #   run_capital, min_capitals, min_solvencies, capital_path, solvency_path
    # After risk transform, we call run_solvency_plane with:
    #   run_solvency=..., min_solvencies=want_solvencies (was min_capitals=want_capitals),
    #   min_risks=want_risks (was min_solvencies — EXTRA invalid kwarg!),
    #   solvency_path=out_solvency (was capital_path=out_capital),
    #   risk_path=... (was solvency_path — EXTRA)

    # Strategy: in run_risk_plane only, rewrite the parent invocation properly.
    # Easier: global fix of kwargs patterns that only appear in parent calls.

    # After transform, out_capital became out_solvency, capital_path param became solvency_path
    # run_risk_plane signature has: run_solvency, min_solvencies, min_risks, solvency_path, risk_path
    # When calling run_solvency_plane we need:
    #   run_capital=run_solvency
    #   min_capitals=want_solvencies  -- NO: solvency plane's min_capitals is capital count; min_solvencies is solvency count
    #   Parent of risk is solvency, so we want min_solvencies on parent call.
    #   Solvency plane signature: min_capitals (for capital layer), min_solvencies (for solvency self)
    #   So: min_capitals=want_solvencies is WRONG. We need min_solvencies=want_solvencies for parent self-count
    #   and min_capitals can stay default or we pass a separate want for capitals.

    # Looking at transformed run_risk_plane params:
    #   min_solvencies (parent count), min_risks (self count)
    #   want_solvencies, want_risks
    # Call to run_solvency_plane should be:
    #   min_capitals=want_solvencies? No - capital and solvency are different.
    #   Original solvency called capital with min_capitals=want_capitals
    #   Risk should call solvency with min_solvencies=want_solvencies
    #   And NOT pass min_risks to solvency plane.

    # Also capital_path=out_capital → solvency_path=out_solvency for parent output
    # But solvency_path in solvency plane is the OUTPUT solvency bundle path.
    # capital_path is the intermediate capital source path.
    # So for risk calling solvency:
    #   solvency_path=out_solvency (the parent bundle we need)
    #   capital_path can be default or a derived path

    # After naive transform:
    #   capital_path=out_capital → solvency_path=out_solvency
    #   solvency_path=solvency_path (param of run_risk) → risk_path=risk_path
    #   min_capitals=want_capitals → min_solvencies=want_solvencies
    #   min_solvencies=want_solvencies → min_risks=want_risks
    # So the call has min_solvencies=want_solvencies AND min_risks=want_risks
    # run_solvency_plane doesn't accept min_risks or risk_path → TypeError

    # Fix: remove min_risks= and risk_path= from parent calls; map correctly.

    import re

    def fix_call(match: re.Match[str]) -> str:
        call = match.group(0)
        # rename kwargs for parent API
        call = call.replace("run_solvency=", "run_capital=")
        # Parent solvency plane: its self is solvency, its parent is capital
        # We want min_solvencies=want_solvencies for multi solvency
        # After transform we have min_solvencies=want_solvencies (from min_capitals) 
        # and min_risks=want_risks (from min_solvencies) — remove min_risks
        call = re.sub(r",\s*min_risks=want_risks", "", call)
        call = re.sub(r",\s*risk_path=risk_path", "", call)
        call = re.sub(r",\s*risk_path=out_risk", "", call)
        # solvency_path=out_solvency is correct for parent output path
        # But wait: after transform capital_path=out_capital became solvency_path=out_solvency
        # and solvency_path=solvency_path became risk_path=risk_path (removed)
        # There might be solvency_path=out_solvency from capital_path - good for parent's solvency output
        # However run_solvency_plane also needs capital_path for intermediate - optional
        
        # Fix: min_solvencies=want_solvencies is correct for parent
        # But we also need min_capitals - the original risk call would have had min_capitals from
        # min_capitals=want_capitals → min_solvencies=want_solvencies, losing min_capitals.
        # Original solvency call to capital:
        #   min_liquidities=..., min_capitals=want_capitals  (no min_solvencies to capital)
        # Transformed risk call to solvency:
        #   min_solvencies=want_solvencies (was min_capitals), min_risks=want_risks (was min_solvencies)
        # After removing min_risks, we have min_solvencies=want_solvencies which is correct for solvency plane!
        # But we lost the ability to set min_capitals for the grandparent. Defaults to 2 which is fine.
        
        # One issue: run_capital=run_solvency means if run_solvency is True, solvency plane runs its capital parent. Good.
        # When run_solvency is False, solvency plane tries to load existing capital - hmm.
        # Actually for risk, run_solvency=True means run parent solvency plane which itself runs capital. Good.
        
        return call

    # Match run_solvency_plane( ... ) calls - non-greedy with nested parens is hard.
    # Simpler approach: line-based replacements that are unique to parent calls.
    
    # In run_risk_plane, parent is invoked as run_solvency_plane(
    # Fix kwargs globally for patterns unique to parent invocation:
    b = b.replace(
        "run_solvency_plane(\n            root,\n            goal if goal else \"solvency for risk\",\n",
        "run_solvency_plane(\n            root,\n            goal if goal else \"solvency for risk\",\n",
    )
    
    # Replace parameter names in ALL run_solvency_plane calls inside risk block
    # Use a state machine approach
    parts: list[str] = []
    i = 0
    needle = "run_solvency_plane("
    while True:
        j = b.find(needle, i)
        if j < 0:
            parts.append(b[i:])
            break
        parts.append(b[i:j])
        # find matching close paren
        k = j + len(needle)
        depth = 1
        while k < len(b) and depth:
            if b[k] == "(":
                depth += 1
            elif b[k] == ")":
                depth -= 1
            k += 1
        call = b[j:k]
        # transform kwargs inside call
        call = call.replace("run_solvency=", "run_capital=")
        # min_solvencies=want_solvencies stays (correct for solvency plane self count)
        # Remove invalid kwargs for solvency plane
        call = re.sub(r",\s*min_risks=want_risks", "", call)
        call = re.sub(r",\s*min_risks=min_risks", "", call)
        call = re.sub(r",\s*risk_path=risk_path", "", call)
        call = re.sub(r",\s*risk_path=out_[a-z_]+", "", call)
        # After transform, capital_path became solvency_path. For solvency plane:
        #   capital_path = intermediate capital bundle
        #   solvency_path = output solvency bundle
        # Transformed: capital_path=out_capital → solvency_path=out_solvency
        #              solvency_path=solvency_path → risk_path=risk_path (removed)
        # So we only have solvency_path=out_solvency which correctly sets parent output. Good.
        # But wait - is out_solvency the variable name?
        parts.append(call)
        i = k
    return "".join(parts)


def fix_builtin_env(b: str) -> str:
    """Ensure builtin_risk_plane env vars and kwargs match run_risk_plane."""
    # After transform, builtin should set:
    # run_solvency from BLACKHOLE_RISK_RUN_SOLVENCY
    # and call run_risk_plane(..., run_solvency=..., min_solvencies=..., min_risks=..., solvency_path=..., risk_path=...)
    
    # Nested envs for solvency plane when it runs should use original names.
    # solvency plane builtin uses BLACKHOLE_SOLVENCY_RUN_CAPITAL etc.
    # But we call run_solvency_plane() directly with kwargs, not builtin, so env only matters
    # for nested builtins if any. run_solvency_plane uses kwargs for capital, and capital plane
    # uses kwargs too. Nested env vars in builtin_risk are only for constructing kwargs.
    
    # Check: BLACKHOLE_CAPITAL_RUN_FUNDING was restored
    # BLACKHOLE_SOLVENCY_MIN_SOLVENCIES for min_solvencies parent count
    # After transform from BLACKHOLE_CAPITAL_MIN_CAPITALS:
    #   CAPITAL→SOLVENCY, capitals→solvencies? MIN_CAPITALS → MIN_SOLVENCIES via capitals→solvencies on CAPITALS
    #   BLACKHOLE_CAPITAL_MIN_CAPITALS → phase1 no → phase2 CAPITAL→SOLVENCY → BLACKHOLE_SOLVENCY_MIN_CAPITALS
    #   then CAPITALS in MIN_CAPITALS? "CAPITALS" as substring of MIN_CAPITALS - parent_reps has ("capitals", "solvencies") lowercase
    #   and ("CAPITAL", "SOLVENCY") would make MIN_CAPITALS → MIN_SOLVENCYS? 
    #   CAPITAL in MIN_CAPITALS → MIN_SOLVENCYS (CAPITAL→SOLVENCY leaves S) → MIN_SOLVENCYS 
    #   BUG: BLACKHOLE_SOLVENCY_MIN_SOLVENCYS should be BLACKHOLE_SOLVENCY_MIN_SOLVENCIES
    
    b = b.replace("MIN_SOLVENCYS", "MIN_SOLVENCIES")
    b = b.replace("MIN_RISKS", "MIN_RISKS")  # from MIN_SOLVENCIES via solvencies→risks: MIN_SOLVENCIES → phase1 solvencies→risks → MIN_RISKS? 
    # SOLVENCIES in MIN_SOLVENCIES: phase1 "solvencies"→"risks" lowercase only. Upper SOLVENCIES?
    # We had ("solvencies", "risks") and ("SOLVENCY", "RISK") 
    # MIN_SOLVENCIES → MIN_ + SOLVENCIES. SOLVENCY is prefix of SOLVENCIES → MIN_RISKIES 
    # BUG!
    b = b.replace("MIN_RISKIES", "MIN_RISKS")
    b = b.replace("MIN_SOLVENCIES", "MIN_SOLVENCIES")
    
    # Also SOLVENCIES alone becoming RISKIES?
    b = b.replace("RISKIES", "RISKS")
    b = b.replace("SOLVENCYS", "SOLVENCIES")
    
    return b


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    const_start = text.find("SOLVENCY_BUNDLE_SCHEMA = 1")
    seed_start = text.find("\ndef seed_bootstrap_capabilities")
    assert const_start > 0 and seed_start > const_start, (const_start, seed_start)
    solvency_block = text[const_start:seed_start]
    # Only take through end of builtin_solvency_plane (before seed)
    risk_block = transform(solvency_block)
    risk_block = fix_parent_api_calls(risk_block)
    risk_block = fix_builtin_env(risk_block)

    # Header note
    header = (
        "\n# --- Risk plane over solvency (generated capability layer) ---\n"
    )
    risk_block = header + risk_block
    if not risk_block.endswith("\n\n"):
        if risk_block.endswith("\n"):
            risk_block += "\n"
        else:
            risk_block += "\n\n"

    out = ROOT / "artifacts" / "_gen_risk_plane_block.py"
    out.write_text(risk_block, encoding="utf-8")

    # Validation prints
    checks = {
        "def run_risk_plane": risk_block.count("def run_risk_plane"),
        "def builtin_risk_plane": risk_block.count("def builtin_risk_plane"),
        "run_solvency_plane(": risk_block.count("run_solvency_plane("),
        "run_capital=": risk_block.count("run_capital="),
        "min_risks": risk_block.count("min_risks"),
        "risk_assessment_digest": risk_block.count("risk_assessment_digest"),
        "solvency_position_digest": risk_block.count("solvency_position_digest"),
        "BLACKHOLE_RISK_RUN_SOLVENCY": risk_block.count("BLACKHOLE_RISK_RUN_SOLVENCY"),
        "BLACKHOLE_RISK_MIN_RISKS": risk_block.count("BLACKHOLE_RISK_MIN_RISKS"),
        "BLACKHOLE_SOLVENCY_MIN_SOLVENCIES": risk_block.count("BLACKHOLE_SOLVENCY_MIN_SOLVENCIES"),
        "BLACKHOLE_CAPITAL_RUN_FUNDING": risk_block.count("BLACKHOLE_CAPITAL_RUN_FUNDING"),
        "wrong_solvency": risk_block.count("wrong_solvency"),
        "post_solvency": risk_block.count("post_solvency"),
        "risked": risk_block.count("risked"),
    }
    print("CHECKS", checks)
    leftovers = []
    for bad in [
        "run_capital_plane",
        "capital_buffer_digest",
        "capability.solvency-plane",
        "MIN_RISKIES",
        "MIN_SOLVENCYS",
        "min_risks=want_risks",  # should not be in parent calls - count overall ok
        "bound_capital",
        "tip_capital",
        "capitalized",
    ]:
        c = risk_block.count(bad)
        if c:
            leftovers.append((bad, c))
    print("LEFTOVERS", leftovers)
    print("wrote", out, "chars", len(risk_block), "lines", risk_block.count("\n"))


if __name__ == "__main__":
    main()
