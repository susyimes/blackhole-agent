"""Generate restructuring plane from resolution plane block."""
from __future__ import annotations

from pathlib import Path


def transform(src: str) -> str:
    # Self rename (resolution plane -> restructuring plane)
    pairs_self = [
        ("RESOLUTION_BUNDLE_SCHEMA", "RESTRUCTURING_BUNDLE_SCHEMA"),
        ("RESOLUTION_CERTIFICATE_SCHEMA", "RESTRUCTURING_CERTIFICATE_SCHEMA"),
        ("RESOLUTION_LOG_SCHEMA", "RESTRUCTURING_LOG_SCHEMA"),
        ("DEFAULT_RESOLUTION_BUNDLE_RELATIVE", "DEFAULT_RESTRUCTURING_BUNDLE_RELATIVE"),
        ("resolution-bundles", "restructuring-bundles"),
        ("proof-resolution", "proof-restructuring"),
        ("resolution-source-recovery", "restructuring-source-resolution"),
        ("capability.resolution-plane", "capability.restructuring-plane"),
        ("resolution_plane", "restructuring_plane"),
        ("run_resolution_plane", "run_restructuring_plane"),
        ("builtin_resolution_plane", "builtin_restructuring_plane"),
        ("BLACKHOLE_RESOLUTION_", "BLACKHOLE_RESTRUCTURING_"),
        ("min_resolutions", "min_restructurings"),
        ("want_resolutions", "want_restructurings"),
        ("resolution_count", "restructuring_count"),
        ("resolution_height", "restructuring_height"),
        ("resolution_root", "restructuring_root"),
        ("resolution_hash", "restructuring_hash"),
        ("resolution_log", "restructuring_log"),
        ("resolution_certificate", "restructuring_certificate"),
        ("resolution_plan_digest", "restructuring_plan_digest"),
        ("resolution_path", "restructuring_path"),
        ("resolution_n", "restructuring_n"),
        ("resolution_done_when", "restructuring_done_when"),
        ("resolution_ok", "restructuring_ok"),
        ("resolution_report", "restructuring_report"),
        ("tip_resolution_root", "tip_restructuring_root"),
        ("parent_resolution_root", "parent_restructuring_root"),
        ("parent_resolution_digest", "parent_restructuring_digest"),
        ("multi_resolution", "multi_restructuring"),
        ("single_resolution", "single_restructuring"),
        ("double-resolution", "double-restructuring"),
        ("double_resolution", "double_restructuring"),
        ("posted resolution", "posted restructuring"),
        ("resolution orders", "restructuring orders"),
        ("resolution order", "restructuring order"),
        ("resolution plan", "restructuring plan"),
        ("resolution actions", "restructuring actions"),
        ("resolution action", "restructuring action"),
        ("resolution adequacy", "restructuring adequacy"),
        ("resolution over recovery", "restructuring over resolution"),
        ("resolution for ", "restructuring for "),
        ("Closed resolution plane", "Closed restructuring plane"),
        ("resolution plane", "restructuring plane"),
        ("Resolution plane", "Restructuring plane"),
        ("empty_resolution_log", "empty_restructuring_log"),
        ("compute_resolution_root", "compute_restructuring_root"),
        ("compute_resolution_certificate_hash", "compute_restructuring_certificate_hash"),
        ("compute_resolution_bundle_hash", "compute_restructuring_bundle_hash"),
        ("compute_resolution_plan_digest", "compute_restructuring_plan_digest"),
        ("issue_resolution_certificate", "issue_restructuring_certificate"),
        ("verify_resolution_certificate", "verify_restructuring_certificate"),
        ("write_resolution_certificate", "write_restructuring_certificate"),
        ("_load_resolution_disk_evidence", "_load_restructuring_disk_evidence"),
        ("derive_resolution_specs_from_recovery", "derive_restructuring_specs_from_resolution"),
        ("apply_resolution_transition", "apply_restructuring_transition"),
        ("verify_resolution_chain", "verify_restructuring_chain"),
        ("apply_recovery_bundle_to_resolutions", "apply_resolution_bundle_to_restructurings"),
        ("build_resolution_bundle", "build_restructuring_bundle"),
        ("write_resolution_bundle", "write_restructuring_bundle"),
        ("load_resolution_bundle", "load_restructuring_bundle"),
        ("verify_resolution_bundle_integrity", "verify_restructuring_bundle_integrity"),
        ("rehydrate_resolution_bundle", "rehydrate_restructuring_bundle"),
        ("replay_resolutions_from_specs", "replay_restructurings_from_specs"),
        ("run_resolution_adversarial_checks", "run_restructuring_adversarial_checks"),
        ("default_resolution_bundle_dir", "default_restructuring_bundle_dir"),
        ('kind": "resolution_', 'kind": "restructuring_'),
        ('"resolution_log"', '"restructuring_log"'),
        ('"resolution_certificate"', '"restructuring_certificate"'),
        ('plane": "resolution"', 'plane": "restructuring"'),
        ('"plane": "resolution"', '"plane": "restructuring"'),
        ("resolutions_path", "restructurings_path"),
        ("resolutions", "restructurings"),
        ("resolved", "restructured"),
        ('"resolution"', '"restructuring"'),
        (" resolution ", " restructuring "),
        ("/resolution", "/restructuring"),
        ("resolution-", "restructuring-"),
    ]
    out = src
    for a, b in pairs_self:
        out = out.replace(a, b)

    # Parent rename (recovery -> resolution)
    pairs_parent = [
        ("BLACKHOLE_RECOVERY_", "BLACKHOLE_RESOLUTION_"),
        (
            "BLACKHOLE_RESTRUCTURING_RUN_RECOVERY",
            "BLACKHOLE_RESTRUCTURING_RUN_RESOLUTION",
        ),
        ("run_recovery_plane", "run_resolution_plane"),
        ("run_recovery", "run_resolution"),
        ("load_recovery_bundle", "load_resolution_bundle"),
        ("default_recovery_bundle_dir", "default_resolution_bundle_dir"),
        ("recovery-bundles", "resolution-bundles"),
        ("proof-restructuring-recovery", "proof-restructuring-resolution"),
        ("recovery_path", "resolution_path"),
        ("recovery_report", "resolution_report"),
        ("recovery_bundle", "resolution_bundle"),
        ("recovery_count", "resolution_count"),
        ("recovery_hash", "resolution_hash"),
        ("recovery_root", "resolution_root"),
        ("recovery_certificate", "resolution_certificate"),
        ("recovery_plan_digest", "resolution_plan_digest"),
        ("tip_recovery_root", "tip_resolution_root"),
        ("bound_recovery_root", "bound_resolution_root"),
        ("bound_recovery_height", "bound_resolution_height"),
        ("want_recoveries", "want_resolutions"),
        ("min_recoveries", "min_resolutions"),
        ("min_resiliences", "min_recoveries"),
        ("run_resilience", "run_recovery"),
        ("parent_recovered", "parent_resolved"),
        ("recoveries_path", "resolutions_path"),
        ("multi_recovery", "multi_resolution"),
        ("post_recovery", "post_resolution"),
        ("post_stress", "post_recovery"),
        ("wrong_recovery", "wrong_resolution"),
        ("wrong-recovery", "wrong-resolution"),
        ("recovered", "resolved"),
        ("recoveries", "resolutions"),
        ("recovery over", "resolution over"),
        ("recovery for restructuring", "resolution for restructuring"),
        ("recovery_source_failed", "resolution_source_failed"),
        ("recovery_apply_failed", "resolution_apply_failed"),
        ('"recovery"', '"resolution"'),
        (" recovery ", " resolution "),
        ("recovery_plane", "resolution_plane"),
        ("/recovery", "/resolution"),
        ("recovery-", "resolution-"),
        ("Recovery", "Resolution"),
        ("recovery", "resolution"),
    ]
    for a, b in pairs_parent:
        out = out.replace(a, b)

    fixes = [
        ("BLACKHOLE_RESOLUTION_MIN_RECOVERYS", "BLACKHOLE_RECOVERY_MIN_RECOVERIES"),
        ("resolution resolution", "resolution"),
        ("restructuring restructuring", "restructuring"),
        # Parent call: resolution plane needs run_recovery not a false run_resolution-only chain.
        # After transform, run_recovery=run_resolution is correct (flag name run_recovery param on
        # resolution plane was run_recovery -> we remapped run_resilience->run_recovery and
        # run_recovery->run_resolution). Call should have:
        #   run_recovery=run_resolution  (from run_resilience=run_recovery then renames)
        # Wait: run_resilience=run_recovery becomes run_recovery=run_resolution. Good.
        # And there was no separate run_recovery=True param on the call - the flag was run_resilience.
        # Signature of run_restructuring has run_resolution (from run_recovery). Good.
    ]
    for a, b in fixes:
        out = out.replace(a, b)
    return out


def main() -> None:
    path = Path("src/blackhole_agent/capability_compounder.py")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    start = end = None
    for i, line in enumerate(lines):
        if start is None and line.startswith("RESOLUTION_BUNDLE_SCHEMA = 1"):
            start = i
        if start is not None and line.startswith("def seed_bootstrap_capabilities"):
            end = i
            break
    assert start is not None and end is not None, (start, end)
    block = "".join(lines[start:end])
    print(f"block lines {end - start}, chars {len(block)}")

    new_block = transform(block)
    for must in [
        "def run_restructuring_plane",
        "def builtin_restructuring_plane",
        "run_resolution_plane",
        "load_resolution_bundle",
        "RESTRUCTURING_BUNDLE_SCHEMA",
        "min_restructurings",
        "restructured",
        "apply_resolution_bundle_to_restructurings",
        "bound_resolution_root",
    ]:
        print(("ok" if must in new_block else "MISSING"), must)

    print("recovery leftovers", new_block.count("recovery"))
    print("run_recovery leftovers", new_block.count("run_recovery"))
    print("min_recoveries leftovers", new_block.count("min_recoveries"))

    # Show parent invocation snippet
    nl = new_block.splitlines()
    for i, line in enumerate(nl):
        if "run_resolution_plane(" in line:
            print("--- parent call ---")
            print("\n".join(nl[i : i + 55]))
            break

    # Signature of run_restructuring_plane
    for i, line in enumerate(nl):
        if line.startswith("def run_restructuring_plane"):
            print("--- signature ---")
            print("\n".join(nl[i : i + 50]))
            break

    out_path = Path("artifacts/_gen_restructuring_plane.py")
    out_path.write_text(new_block, encoding="utf-8")
    print("wrote", out_path, len(new_block))


if __name__ == "__main__":
    main()
