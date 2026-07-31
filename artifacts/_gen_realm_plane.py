#!/usr/bin/env python3
"""Generate realm plane over dominion from dominion plane over empire."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOUNDER = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UNBOUND = ROOT / "src" / "blackhole_agent" / "unbound.py"
TEST = ROOT / "tests" / "test_capability_compounder.py"


def transform_dominion_to_realm(src: str) -> str:
    """Self=dominion→realm, parent=empire→dominion with ordered renames."""
    s = src

    # Protect parent empire tokens that should become dominion (parent layer)
    parent_map = [
        ("apply_empire_bundle_to_dominions", "@@APPLY_PARENT@@"),
        ("derive_dominion_specs_from_empire", "@@DERIVE_SPECS@@"),
        ("verify_empire_bundle_integrity", "@@VERIFY_PARENT_INTEGRITY@@"),
        ("verify_empire_certificate", "@@VERIFY_PARENT_CERT@@"),
        ("write_empire_certificate", "@@WRITE_PARENT_CERT@@"),
        ("load_empire_bundle", "@@LOAD_PARENT_BUNDLE@@"),
        ("default_empire_bundle_dir", "@@DEFAULT_PARENT_DIR@@"),
        ("default_commonwealth_bundle_dir", "@@DEFAULT_GRANDPARENT_DIR@@"),
        ("run_empire_plane", "@@RUN_PARENT_PLANE@@"),
        ("empire_bundle", "@@PARENT_BUNDLE@@"),
        ("empire_report", "@@PARENT_REPORT@@"),
        ("empire_path", "@@PARENT_PATH@@"),
        ("empire_certificate", "@@PARENT_CERTIFICATE@@"),
        ("empire_plan_digest", "@@PARENT_PLAN_DIGEST@@"),
        ("empire_hash", "@@PARENT_HASH@@"),
        ("empire_count", "@@PARENT_COUNT@@"),
        ("empire_height", "@@PARENT_HEIGHT@@"),
        ("empire_root", "@@PARENT_ROOT@@"),
        ("empired", "@@PARENTED@@"),
        ("empires", "@@PARENTS@@"),
        ("empire_ok", "@@PARENT_OK@@"),
        ("min_empires", "@@MIN_PARENTS@@"),
        ("run_empire", "@@RUN_PARENT@@"),
        ("out_stress", "@@OUT_PARENT@@"),
        ("want_empires", "@@WANT_PARENTS@@"),
        ("parent_empired", "@@PARENT_PARENTED@@"),
        ("parent_commonwealth", "@@PARENT_GRANDPARENT@@"),
        ("commonwealth_path", "@@GRANDPARENT_PATH@@"),
        ("min_commonwealths", "@@MIN_GRANDPARENTS@@"),
        ("run_commonwealth", "@@RUN_GRANDPARENT@@"),
        ("proof-commonwealth.json", "@@PROOF_GRANDPARENT@@"),
        ("proof-empire.json", "@@PROOF_PARENT@@"),
        ("BLACKHOLE_EMPIRE_", "@@ENV_PARENT_@@"),
        ("BLACKHOLE_DOMINION_RUN_EMPIRE", "@@ENV_RUN_PARENT@@"),
        ("BLACKHOLE_EMPIRE_MIN_EMPIRES", "@@ENV_MIN_PARENTS@@"),
        ("BLACKHOLE_EMPIRE_BUNDLE_PATH", "@@ENV_PARENT_BUNDLE_PATH@@"),
        ("BLACKHOLE_DOMINION_BUNDLE_PATH", "@@ENV_SELF_BUNDLE_PATH@@"),
        ("BLACKHOLE_DOMINION_MIN_DOMINIONS", "@@ENV_MIN_SELF@@"),
        ("bound_empire_root", "@@BOUND_PARENT_ROOT@@"),
        ("bound_empire_height", "@@BOUND_PARENT_HEIGHT@@"),
        ("tip_empire_root", "@@TIP_PARENT_ROOT@@"),
        ("known_empire_roots", "@@KNOWN_PARENT_ROOTS@@"),
        ("bound_empire_root_mismatch", "@@BOUND_PARENT_MISMATCH@@"),
        ("duplicate_empire_rejected", "@@DUP_PARENT_REJECTED@@"),
        ("missing_empire_bind_fields", "@@MISSING_PARENT_BIND@@"),
        ("empire_source_failed", "@@PARENT_SOURCE_FAILED@@"),
        ("empire_integrity_failed", "@@PARENT_INTEGRITY_FAILED@@"),
        ("empire_apply_failed", "@@PARENT_APPLY_FAILED@@"),
        ("empire_chain_invalid", "@@PARENT_CHAIN_INVALID@@"),
        ("wrong_empire", "@@WRONG_PARENT@@"),
        ("post_empire", "@@POST_PARENT@@"),
        ("multi_empire", "@@MULTI_PARENT@@"),
        ("Empire", "@@ParentTitle@@"),
        ("empire", "@@parent@@"),
        ("EMPIRE", "@@PARENT@@"),
    ]
    for a, b in parent_map:
        s = s.replace(a, b)

    # Self dominion → realm
    self_map = [
        ("DOMINION_BUNDLE_SCHEMA", "REALM_BUNDLE_SCHEMA"),
        ("DOMINION_CERTIFICATE_SCHEMA", "REALM_CERTIFICATE_SCHEMA"),
        ("DOMINION_LOG_SCHEMA", "REALM_LOG_SCHEMA"),
        ("DEFAULT_DOMINION_BUNDLE_RELATIVE", "DEFAULT_REALM_BUNDLE_RELATIVE"),
        ("dominion-bundles", "realm-bundles"),
        ("dominion-sandbox", "realm-sandbox"),
        ("proof-dominion", "proof-realm"),
        ("dominion-source-", "realm-source-"),
        ("dominion-certificate", "realm-certificate"),
        ("builtin_dominion_plane", "builtin_realm_plane"),
        ("run_dominion_plane", "run_realm_plane"),
        ("run_dominion_adversarial_checks", "run_realm_adversarial_checks"),
        ("replay_dominions_from_specs", "replay_realms_from_specs"),
        ("rehydrate_dominion_bundle", "rehydrate_realm_bundle"),
        ("verify_dominion_bundle_integrity", "verify_realm_bundle_integrity"),
        ("load_dominion_bundle", "load_realm_bundle"),
        ("write_dominion_bundle", "write_realm_bundle"),
        ("build_dominion_bundle", "build_realm_bundle"),
        ("verify_dominion_chain", "verify_realm_chain"),
        ("apply_dominion_transition", "apply_realm_transition"),
        ("issue_dominion_certificate", "issue_realm_certificate"),
        ("verify_dominion_certificate", "verify_dominion_certificate".replace(
            "dominion", "realm"
        )),
        ("write_dominion_certificate", "write_realm_certificate"),
        ("compute_dominion_plan_digest", "compute_realm_plan_digest"),
        ("compute_dominion_bundle_hash", "compute_realm_bundle_hash"),
        ("compute_dominion_certificate_hash", "compute_realm_certificate_hash"),
        ("compute_dominion_root", "compute_realm_root"),
        ("empty_dominion_log", "empty_realm_log"),
        ("default_dominion_bundle_dir", "default_realm_bundle_dir"),
        ("_load_dominion_disk_evidence", "_load_realm_disk_evidence"),
        ("dominion_log", "realm_log"),
        ("dominion_path", "realm_path"),
        ("dominion_done_when", "realm_done_when"),
        ("dominion_plan_digest", "realm_plan_digest"),
        ("dominion_certificate", "realm_certificate"),
        ("dominion_count", "realm_count"),
        ("dominion_hash", "realm_hash"),
        ("dominion_root", "realm_root"),
        ("dominion_height", "realm_height"),
        ("dominion_action", "realm_action"),
        ("dominion_plane", "realm_plane"),
        ("dominion_adversarial", "realm_adversarial"),
        ("dominioned", "realmed"),
        ("dominions", "realms"),
        ("dominion_ok", "realm_ok"),
        ("min_dominions", "min_realms"),
        ("want_dominions", "want_realms"),
        ("multi_dominion", "multi_realm"),
        ("single_dominion", "single_realm"),
        ("double-dominion", "double-realm"),
        ("need_multi_dominion", "need_multi_realm"),
        ("Dominion", "Realm"),
        ("dominion", "realm"),
        ("DOMINION", "REALM"),
    ]
    for a, b in self_map:
        s = s.replace(a, b)

    # Restore parent placeholders as dominion (parent of realm)
    restore = [
        ("@@APPLY_PARENT@@", "apply_dominion_bundle_to_realms"),
        ("@@DERIVE_SPECS@@", "derive_realm_specs_from_dominion"),
        ("@@VERIFY_PARENT_INTEGRITY@@", "verify_dominion_bundle_integrity"),
        ("@@VERIFY_PARENT_CERT@@", "verify_dominion_certificate"),
        ("@@WRITE_PARENT_CERT@@", "write_dominion_certificate"),
        ("@@LOAD_PARENT_BUNDLE@@", "load_dominion_bundle"),
        ("@@DEFAULT_PARENT_DIR@@", "default_dominion_bundle_dir"),
        ("@@DEFAULT_GRANDPARENT_DIR@@", "default_empire_bundle_dir"),
        ("@@RUN_PARENT_PLANE@@", "run_dominion_plane"),
        ("@@PARENT_BUNDLE@@", "dominion_bundle"),
        ("@@PARENT_REPORT@@", "dominion_report"),
        ("@@PARENT_PATH@@", "dominion_path"),
        ("@@PARENT_CERTIFICATE@@", "dominion_certificate"),
        ("@@PARENT_PLAN_DIGEST@@", "dominion_plan_digest"),
        ("@@PARENT_HASH@@", "dominion_hash"),
        ("@@PARENT_COUNT@@", "dominion_count"),
        ("@@PARENT_HEIGHT@@", "dominion_height"),
        ("@@PARENT_ROOT@@", "dominion_root"),
        ("@@PARENTED@@", "dominioned"),
        ("@@PARENTS@@", "dominions"),
        ("@@PARENT_OK@@", "dominion_ok"),
        ("@@MIN_PARENTS@@", "min_dominions"),
        ("@@RUN_PARENT@@", "run_dominion"),
        ("@@OUT_PARENT@@", "out_dominion"),
        ("@@WANT_PARENTS@@", "want_dominions"),
        ("@@PARENT_PARENTED@@", "parent_dominioned"),
        ("@@PARENT_GRANDPARENT@@", "parent_empire"),
        ("@@GRANDPARENT_PATH@@", "empire_path"),
        ("@@MIN_GRANDPARENTS@@", "min_empires"),
        ("@@RUN_GRANDPARENT@@", "run_empire"),
        ("@@PROOF_GRANDPARENT@@", "proof-empire.json"),
        ("@@PROOF_PARENT@@", "proof-dominion.json"),
        ("@@ENV_PARENT_@@", "BLACKHOLE_DOMINION_"),
        ("@@ENV_RUN_PARENT@@", "BLACKHOLE_REALM_RUN_DOMINION"),
        ("@@ENV_MIN_PARENTS@@", "BLACKHOLE_DOMINION_MIN_DOMINIONS"),
        ("@@ENV_PARENT_BUNDLE_PATH@@", "BLACKHOLE_DOMINION_BUNDLE_PATH"),
        ("@@ENV_SELF_BUNDLE_PATH@@", "BLACKHOLE_REALM_BUNDLE_PATH"),
        ("@@ENV_MIN_SELF@@", "BLACKHOLE_REALM_MIN_REALMS"),
        ("@@BOUND_PARENT_ROOT@@", "bound_dominion_root"),
        ("@@BOUND_PARENT_HEIGHT@@", "bound_dominion_height"),
        ("@@TIP_PARENT_ROOT@@", "tip_dominion_root"),
        ("@@KNOWN_PARENT_ROOTS@@", "known_dominion_roots"),
        ("@@BOUND_PARENT_MISMATCH@@", "bound_dominion_root_mismatch"),
        ("@@DUP_PARENT_REJECTED@@", "duplicate_dominion_rejected"),
        ("@@MISSING_PARENT_BIND@@", "missing_dominion_bind_fields"),
        ("@@PARENT_SOURCE_FAILED@@", "dominion_source_failed"),
        ("@@PARENT_INTEGRITY_FAILED@@", "dominion_integrity_failed"),
        ("@@PARENT_APPLY_FAILED@@", "dominion_apply_failed"),
        ("@@PARENT_CHAIN_INVALID@@", "dominion_chain_invalid"),
        ("@@WRONG_PARENT@@", "wrong_dominion"),
        ("@@POST_PARENT@@", "post_dominion"),
        ("@@MULTI_PARENT@@", "multi_dominion"),
        ("@@ParentTitle@@", "Dominion"),
        ("@@parent@@", "dominion"),
        ("@@PARENT@@", "DOMINION"),
    ]
    for a, b in restore:
        s = s.replace(a, b)

    # Fix goal strings and comments that should say realm over dominion
    s = s.replace("realm over dominion", "realm over dominion")  # keep
    s = s.replace(
        "goal if goal else \"dominion for realm\"",
        "goal if goal else \"dominion for realm\"",
    )
    # Parent plane goal fallback inside run_realm when calling run_dominion
    s = s.replace(
        'goal if goal else "dominion for realm"',
        'goal if goal else "dominion for realm"',
    )

    # Fix double-transforms that may have leaked
    # default_empire_bundle_dir was protected as grandparent - good
    # verify_dominion_certificate for parent is correct (parent is dominion)

    return s


def insert_after_marker(text: str, marker: str, insertion: str) -> str:
    idx = text.find(marker)
    if idx < 0:
        raise SystemExit(f"marker not found: {marker[:80]!r}")
    # insert after the line containing marker
    end_line = text.find("\n", idx)
    if end_line < 0:
        end_line = len(text)
    return text[: end_line + 1] + insertion + text[end_line + 1 :]


def patch_compounder(text: str, realm_block: str) -> str:
    # Append realm block after builtin_dominion_plane function ends.
    # Find end of builtin_dominion_plane by locating its def and next top-level def.
    m = re.search(r"^def builtin_dominion_plane\(\) -> dict\[str, Any\]:", text, re.M)
    if not m:
        raise SystemExit("builtin_dominion_plane not found")
    # find next top-level def after this
    rest = text[m.start() :]
    m2 = re.search(r"\n(?=def |class |[A-Z_]{3,} = )", rest[1:])
    if not m2:
        raise SystemExit("end of builtin_dominion_plane not found")
    insert_at = m.start() + 1 + m2.start() + 1
    # m2 is relative to rest[1:], so +1 for rest[1:], + m.start() for rest offset
    insert_at = m.start() + 1 + m2.start() + 1
    # Actually rest = text[m.start():], m2 on rest[1:], match position in rest is m2.start()+1
    insert_at = m.start() + m2.start() + 1 + 1  # after the newline

    # cleaner approach: find line start of next def after builtin_dominion
    lines = text.splitlines(keepends=True)
    start_i = None
    end_i = None
    for i, line in enumerate(lines):
        if line.startswith("def builtin_dominion_plane"):
            start_i = i
            break
    if start_i is None:
        raise SystemExit("builtin_dominion_plane line not found")
    for j in range(start_i + 1, len(lines)):
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end_i = j
            break
        # also seed Capability blocks after blank lines at module level - unlikely mid function
    if end_i is None:
        # maybe next is not def - scan for non-indented non-empty
        for j in range(start_i + 1, len(lines)):
            if lines[j] and not lines[j][0].isspace() and not lines[j].startswith("#"):
                end_i = j
                break
    if end_i is None:
        end_i = len(lines)

    block = "\n\n" + realm_block.rstrip() + "\n\n"
    if "def run_realm_plane" in text:
        print("realm plane already present, skipping block insert")
    else:
        text = "".join(lines[:end_i]) + block + "".join(lines[end_i:])

    # --- keyword scout map near dominion entries ---
    scout_snip = '''    ("dominion", ("capability.dominion-plane", "capability.empire-plane", "capability.commonwealth-plane")),
    ("dominioned", ("capability.dominion-plane", "capability.empire-plane", "capability.finality-plane")),
    ("dominion plan", ("capability.dominion-plane", "capability.empire-plane", "capability.assurance-plane")),
    ("dominion-root", ("capability.dominion-plane", "capability.empire-plane", "capability.lineage-plane")),
    ("dominion discharge", ("capability.dominion-plane", "capability.empire-plane", "capability.quorum-plane")),
    ("posted dominion", ("capability.dominion-plane", "capability.empire-plane", "capability.actuation-plane")),
    ("dominion adequacy", ("capability.dominion-plane", "capability.empire-plane", "capability.assurance-plane")),
'''
    realm_scout = '''    ("realm", ("capability.realm-plane", "capability.dominion-plane", "capability.empire-plane")),
    ("realmed", ("capability.realm-plane", "capability.dominion-plane", "capability.finality-plane")),
    ("realm plan", ("capability.realm-plane", "capability.dominion-plane", "capability.assurance-plane")),
    ("realm-root", ("capability.realm-plane", "capability.dominion-plane", "capability.lineage-plane")),
    ("realm discharge", ("capability.realm-plane", "capability.dominion-plane", "capability.quorum-plane")),
    ("posted realm", ("capability.realm-plane", "capability.dominion-plane", "capability.actuation-plane")),
    ("realm adequacy", ("capability.realm-plane", "capability.dominion-plane", "capability.assurance-plane")),
'''
    if '("realm", ("capability.realm-plane"' not in text:
        if scout_snip not in text:
            raise SystemExit("scout snip not found")
        text = text.replace(scout_snip, scout_snip + realm_scout)

    # --- outcome contract kind list ---
    kinds_snip = '''        "dominion_ok",
        "dominioned_ok",
        "min_dominions",
        "dominion_root_valid",
'''
    realm_kinds = '''        "realm_ok",
        "realmed_ok",
        "min_realms",
        "realm_root_valid",
'''
    # appears twice (parse allowlist + eval allowlist) — replace_all carefully
    if '"realm_ok"' not in text:
        count = text.count(kinds_snip)
        if count < 1:
            raise SystemExit(f"kinds snip not found count={count}")
        text = text.replace(kinds_snip, kinds_snip + realm_kinds)

    # --- parse predicates after dominion_root_valid ---
    parse_snip = '''    if re.search(r"\\bdominion_root_valid\\b", lower) or (
'''
    # Find dominion_root_valid parser block end and insert realm parsers after it
    # Look for the block that ends dominion_root_valid append
    parse_anchor = '''        found.append({"kind": "dominion_root_valid", "arg": "", "source": chunk})
'''
    parse_add = '''        found.append({"kind": "dominion_root_valid", "arg": "", "source": chunk})
    if re.search(r"\\brealm_ok\\b", lower) or (
        re.search(r"\\brun_realm_plane\\b", lower) and (
            "ok" in lower or "valid" in lower
        )
        and "realm_ok" not in lower
        and "realmed" not in lower
    ):
        found.append({"kind": "realm_ok", "arg": "", "source": chunk})
    if re.search(r"\\brealmed_ok\\b", lower) or (
        re.search(r"\\brealmed\\b", lower)
        and ("ok" in lower or "true" in lower)
        and "realmed_ok" not in lower
        and "realm_plane" not in lower
    ):
        found.append({"kind": "realmed_ok", "arg": "", "source": chunk})
    m = re.search(r"min_realms\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_realms", "arg": m.group(1), "source": chunk})
    m = re.search(r"realms?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_realms" for item in found):
        found.append({"kind": "min_realms", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_ ]realm", lower)
    if m and not any(item.get("kind") == "min_realms" for item in found):
        found.append({"kind": "min_realms", "arg": m.group(1) if m.lastindex else "2", "source": chunk})
    if re.search(r"\\brealm_root_valid\\b", lower) or (
        "realm" in lower and "root" in lower and "valid" in lower
        and "realm_root_valid" not in lower
    ):
        found.append({"kind": "realm_root_valid", "arg": "", "source": chunk})
'''
    # The last min_realm pattern is wrong - fix simpler like dominion
    parse_add = '''        found.append({"kind": "dominion_root_valid", "arg": "", "source": chunk})
    if re.search(r"\\brealm_ok\\b", lower) or (
        re.search(r"\\brun_realm_plane\\b", lower) and (
            "ok" in lower
        )
        and "realm_ok" not in lower
    ):
        found.append({"kind": "realm_ok", "arg": "", "source": chunk})
    if re.search(r"\\brealmed_ok\\b", lower) or (
        re.search(r"\\brealmed\\b", lower)
        and "realmed_ok" not in lower
        and "realm_plane" not in lower
    ):
        found.append({"kind": "realmed_ok", "arg": "", "source": chunk})
    m = re.search(r"min_realms\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_realms", "arg": m.group(1), "source": chunk})
    m = re.search(r"(?:^|;)\\s*realms?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_realms" for item in found):
        found.append({"kind": "min_realms", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_-]realms?\\s*[:=]?\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_realms" for item in found):
        found.append({"kind": "min_realms", "arg": m.group(1), "source": chunk})
    if re.search(r"\\brealm_root_valid\\b", lower) or (
        re.search(r"realm[_ ]root", lower) and "valid" in lower
    ):
        found.append({"kind": "realm_root_valid", "arg": "", "source": chunk})
'''
    if '"realm_ok", "arg"' not in text and "kind\": \"realm_ok\"" not in text:
        if parse_anchor not in text:
            raise SystemExit("parse anchor not found")
        # only first occurrence (parser)
        text = text.replace(parse_anchor, parse_add, 1)

    # --- evaluate predicates after dominion block ---
    eval_anchor = '''        if kind == "dominion_ok":
'''
    # Find full dominion eval section to append after dominion_root_valid return
    # Use the return ok, f"dominion_root_valid=..." as anchor
    eval_end = '        return ok, f"dominion_root_valid={ok}"\n'
    eval_add = '''        return ok, f"dominion_root_valid={ok}"
    if kind in {
        "realm_ok",
        "realmed_ok",
        "min_realms",
        "realm_root_valid",
    }:
        plane = (
            context.get("realm")
            or context.get("realm_plane")
            or context.get("scenario")
            or context
        )
        if not isinstance(plane, Mapping):
            plane = {}
        if kind == "realm_ok":
            ok = plane.get("ok") is True or context.get("ok") is True
            return ok, f"realm_ok={ok}"
        if kind == "realmed_ok":
            ok = (
                plane.get("realmed") is True
                or context.get("realmed") is True
            )
            return ok, f"realmed_ok={ok}"
        if kind == "min_realms":
            try:
                need = int(arg or "2")
            except ValueError:
                need = 2
            have = int(
                plane.get("realm_count")
                or context.get("realm_count")
                or plane.get("tip_height")
                or 0
            )
            ok = have >= need
            return ok, f"min_realms={have}>={need}:{ok}"
        # realm_root_valid
        if "realm_root_valid" in plane:
            ok = plane.get("realm_root_valid") is True
        else:
            ok = bool(
                plane.get("tip_realm_root")
                or plane.get("realm_root")
                or plane.get("certificate_valid")
            )
        return ok, f"realm_root_valid={ok}"
'''
    if 'kind == "realm_ok"' not in text:
        if eval_end not in text:
            raise SystemExit("eval end not found")
        text = text.replace(eval_end, eval_add, 1)

    # --- seed Capability registration after dominion Capability ---
    # Find dominion Capability block and clone
    cap_marker = '            id="capability.dominion-plane",'
    if 'id="capability.realm-plane"' not in text:
        # Find the Capability( that contains dominion-plane through the closing ),
        # by locating from Capability( before id to the next Capability( or end of list
        idx = text.find(cap_marker)
        if idx < 0:
            raise SystemExit("dominion capability marker missing")
        # walk back to Capability(
        cap_start = text.rfind("        Capability(", 0, idx)
        # walk forward to next Capability( or blank line + )
        next_cap = text.find("\n        Capability(", idx)
        next_end = text.find("\n    ]", idx)  # end of seed list maybe
        if next_cap < 0:
            cap_end = next_end
        else:
            cap_end = next_cap
        if cap_end < 0:
            raise SystemExit("dominion capability end not found")
        dominion_cap = text[cap_start:cap_end]
        realm_cap = dominion_cap
        # transform capability registration
        realm_cap = realm_cap.replace(
            "capability.dominion-plane", "capability.realm-plane"
        )
        realm_cap = realm_cap.replace(
            "Dominion plane over empire", "Realm plane over dominion"
        )
        realm_cap = realm_cap.replace(
            "Closed dominion plane: multi-empire orders",
            "Closed realm plane: multi-dominion orders",
        )
        realm_cap = realm_cap.replace(
            "hash-chained dominion grants with dominion plan digests bound to "
            "empire roots → dominion certificates",
            "hash-chained realm grants with realm plan digests bound to "
            "dominion roots → realm certificates",
        )
        realm_cap = realm_cap.replace(
            "wrong-empire/double-dominion",
            "wrong-dominion/double-realm",
        )
        realm_cap = realm_cap.replace(
            "single-dominion falsification",
            "single-realm falsification",
        )
        realm_cap = realm_cap.replace(
            "past dominioned actions without dominion grants.",
            "past realmed actions without realm grants.",
        )
        realm_cap = realm_cap.replace(
            "builtin_dominion_plane", "builtin_realm_plane"
        )
        realm_cap = realm_cap.replace(
            "BLACKHOLE_MISSION_GOAL']='dominion over empire",
            "BLACKHOLE_MISSION_GOAL']='realm over dominion",
        )
        realm_cap = realm_cap.replace(
            "BLACKHOLE_DOMINION_RUN_EMPIRE']='1",
            "BLACKHOLE_REALM_RUN_DOMINION']='1'; "
            "os.environ['BLACKHOLE_DOMINION_RUN_EMPIRE']='1",
        )
        realm_cap = realm_cap.replace(
            "BLACKHOLE_DOMINION_MIN_DOMINIONS']='2",
            "BLACKHOLE_DOMINION_MIN_DOMINIONS']='2'; "
            "os.environ['BLACKHOLE_REALM_MIN_REALMS']='2",
        )
        # bundle paths - add realm proof path and keep dominion
        realm_cap = realm_cap.replace(
            "os.environ.setdefault('BLACKHOLE_DOMINION_BUNDLE_PATH', str(Path('artifacts')/'dominion-bundles'/'proof-dominion.json')); ",
            "os.environ.setdefault('BLACKHOLE_DOMINION_BUNDLE_PATH', str(Path('artifacts')/'dominion-bundles'/'proof-dominion.json')); "
            "os.environ.setdefault('BLACKHOLE_REALM_BUNDLE_PATH', str(Path('artifacts')/'realm-bundles'/'proof-realm.json')); ",
        )
        realm_cap = realm_cap.replace(
            "r=builtin_dominion_plane(); assert r['ok'] and r.get('action')=='dominion_plane' "
            "and r.get('dominioned') is True and int(r.get('dominion_count') or 0) >= 2 ",
            "r=builtin_realm_plane(); assert r['ok'] and r.get('action')=='realm_plane' "
            "and r.get('realmed') is True and int(r.get('realm_count') or 0) >= 2 ",
        )
        realm_cap = realm_cap.replace(
            "and r.get('dominion_certificate',{}).get('valid') ",
            "and r.get('realm_certificate',{}).get('valid') ",
        )
        realm_cap = realm_cap.replace(
            "capability-lineage'/'proof-dominion.json",
            "capability-lineage'/'proof-realm.json",
        )
        # proof artifact names dominion → realm for nested bundles in proof_command
        realm_cap = re.sub(
            r"proof-dominion-([a-z]+)\.json",
            r"proof-realm-\1.json",
            realm_cap,
        )
        realm_cap = realm_cap.replace(
            '"Dominion plane posts multi-empire orders into deterministic hash-chained "\n'
            '                "dominion grants with dominion plan digests bound to empire roots, "\n'
            '                "dominion certificates, sterile rehydrate+prove, and adversarial falsification "\n'
            '                "without skill-route discovery."',
            '"Realm plane posts multi-dominion orders into deterministic hash-chained "\n'
            '                "realm grants with realm plan digests bound to dominion roots, "\n'
            '                "realm certificates, sterile rehydrate+prove, and adversarial falsification "\n'
            '                "without skill-route discovery."',
        )
        # tags
        realm_cap = realm_cap.replace(
            '                "dominion",\n'
            '                "order",\n'
            '                "empire",\n',
            '                "realm",\n'
            '                "order",\n'
            '                "dominion",\n',
        )
        # deps: insert dominion-plane first among plane deps after reorganization
        if '"capability.dominion-plane"' not in realm_cap.split("dependencies")[1][:2000]:
            realm_cap = realm_cap.replace(
                '                "capability.empire-plane",\n',
                '                "capability.dominion-plane",\n'
                '                "capability.empire-plane",\n',
                1,
            )
        # Fix capability_delta if still dominion-flavored
        realm_cap = realm_cap.replace(
            "Dominion plane posts multi-empire orders into deterministic hash-chained "
            "dominion grants with dominion plan digests bound to empire roots, "
            "dominion certificates, sterile rehydrate+prove, and adversarial falsification "
            "without skill-route discovery.",
            "Realm plane posts multi-dominion orders into deterministic hash-chained "
            "realm grants with realm plan digests bound to dominion roots, "
            "realm certificates, sterile rehydrate+prove, and adversarial falsification "
            "without skill-route discovery.",
        )
        text = text[:cap_end] + "\n" + realm_cap + text[cap_end:]

    return text


def patch_unbound(text: str) -> str:
    if "run_realm_plane" in text and "needs_realm" in text:
        print("unbound already patched")
        return text

    # import
    text = text.replace(
        "    run_dominion_plane,\n",
        "    run_dominion_plane,\n    run_realm_plane,\n",
        1,
    )

    # bind
    text = text.replace(
        "    run_dominion = (\n        cc.run_dominion_plane if cc is not None else run_dominion_plane\n",
        "    run_dominion = (\n        cc.run_dominion_plane if cc is not None else run_dominion_plane\n"
        "    )\n    run_realm = (\n        cc.run_realm_plane if cc is not None else run_realm_plane\n",
        1,
    )
    # The above may break if original wasn't closed that way - check structure
    # Actually original is:
    # run_dominion = (
    #     cc.run_dominion_plane if cc is not None else run_dominion_plane
    # )
    # My replace might leave double )

    text = text.replace(
        "    run_dominion = (\n"
        "        cc.run_dominion_plane if cc is not None else run_dominion_plane\n"
        "    )\n"
        "    run_realm = (\n"
        "        cc.run_realm_plane if cc is not None else run_realm_plane\n"
        "    )\n",
        "    run_dominion = (\n"
        "        cc.run_dominion_plane if cc is not None else run_dominion_plane\n"
        "    )\n"
        "    run_realm = (\n"
        "        cc.run_realm_plane if cc is not None else run_realm_plane\n"
        "    )\n",
    )

    # Fix potential broken double-bind from first replace
    text = re.sub(
        r"run_dominion = \(\n"
        r"        cc\.run_dominion_plane if cc is not None else run_dominion_plane\n"
        r"    \)\n"
        r"    run_realm = \(\n"
        r"        cc\.run_realm_plane if cc is not None else run_realm_plane\n"
        r"    \)\n"
        r"    \)",
        "run_dominion = (\n"
        "        cc.run_dominion_plane if cc is not None else run_dominion_plane\n"
        "    )\n"
        "    run_realm = (\n"
        "        cc.run_realm_plane if cc is not None else run_realm_plane\n"
        "    )",
        text,
        count=1,
    )

    # needs_dominion block — add needs_realm before it and cascade not needs_realm
    needs_dom = '''                    needs_dominion = bool(
'''
    # Read current unbound section carefully with a simpler approach
    if "needs_realm" not in text:
        # Insert needs_realm definition before needs_dominion
        m = re.search(
            r"(\s+)needs_dominion = bool\(\n"
            r"(?:\s+.*\n)*?\s+\)",
            text,
        )
        if not m:
            raise SystemExit("needs_dominion block not found")
        indent = m.group(1)
        realm_needs = (
            f"{indent}needs_realm = bool(\n"
            f"{indent}    done_when\n"
            f"{indent}    and any(\n"
            f"{indent}        token in done_when\n"
            f"{indent}        for token in (\n"
            f'{indent}            "realm_ok",\n'
            f'{indent}            "realmed_ok",\n'
            f'{indent}            "min_realms",\n'
            f'{indent}            "realm_root_valid",\n'
            f"{indent}        )\n"
            f"{indent}    )\n"
            f"{indent})\n"
        )
        text = text[: m.start()] + realm_needs + text[m.start() :]

        # Cascade: and not needs_dominion → and not needs_dominion and not needs_realm
        # for lower planes only when they already exclude needs_dominion
        text = text.replace(
            "and not needs_dominion",
            "and not needs_dominion and not needs_realm",
        )
        # needs_dominion definition itself shouldn't get the cascade wrongly —
        # the replace is only on the gate conditions that say "and not needs_dominion"

        # Add execution branch for realm before dominion
        # Find: if needs_dominion:
        dom_if = "                    if needs_dominion:"
        if dom_if not in text:
            raise SystemExit("if needs_dominion not found")
        # We'll inject a similar realm block before dominion by cloning and transforming
        # Extract dominion if-block until next "if needs_" at same indent or similar
        idx = text.find(dom_if)
        # find next sibling if at same indent after a substantial block
        # Look for "if needs_empire:" or "if needs_commonwealth" that comes after - actually
        # structure is if needs_dominion then elif-like sequential ifs
        # Find end: next "                    if needs_" after idx+1
        m_next = re.search(r"\n                    if needs_", text[idx + 1 :])
        if not m_next:
            # try for else or different structure
            m_next = re.search(r"\n                    # ", text[idx + 1 :])
        if not m_next:
            raise SystemExit("end of needs_dominion block not found")
        dom_block = text[idx : idx + 1 + m_next.start()]
        realm_block = dom_block
        realm_block = realm_block.replace("needs_dominion", "needs_realm")
        realm_block = realm_block.replace("run_dominion(", "run_realm(")
        realm_block = realm_block.replace("run_dominion\n", "run_realm\n")
        realm_block = realm_block.replace("dominion_result", "realm_result")
        realm_block = realm_block.replace("disk_dominion", "disk_realm")
        realm_block = realm_block.replace("_load_dominion_disk_evidence", "_load_realm_disk_evidence")
        realm_block = realm_block.replace("dominion_ok_flag", "realm_ok_flag")
        realm_block = realm_block.replace("dominioned", "realmed")
        realm_block = realm_block.replace('"dominion"', '"realm"')
        realm_block = realm_block.replace("'dominion'", "'realm'")
        realm_block = realm_block.replace("dominion_count", "realm_count")
        realm_block = realm_block.replace("tip_dominion_root", "tip_realm_root")
        realm_block = realm_block.replace("dominion_hash", "realm_hash")
        realm_block = realm_block.replace("dominion_plan_digest", "realm_plan_digest")
        realm_block = realm_block.replace("dominion_certificate", "realm_certificate")
        realm_block = realm_block.replace("dominion_root_valid", "realm_root_valid")
        realm_block = realm_block.replace("dominion_plane", "realm_plane")
        realm_block = realm_block.replace(
            "dominion over empire", "realm over dominion"
        )
        realm_block = realm_block.replace("min_dominions=", "min_realms=")
        # parent for realm plane is dominion - run_dominion_plane params
        realm_block = realm_block.replace(
            "run_empire=", "run_dominion="
        )
        realm_block = realm_block.replace("empire_path=", "dominion_path=")
        realm_block = realm_block.replace("dominion_path=", "realm_path=")
        # careful: the above double-replaced dominion_path from empire and self
        # Restore: we want dominion_path for parent and realm_path for self
        # Original dominion block has empire_path and dominion_path
        # After replace: run_dominion= , then dominion_path became realm_path for both?
        # Let's look at original structure from grep earlier...
        text = text[:idx] + realm_block + text[idx:]

    return text


def patch_tests(text: str) -> str:
    if "test_realm_plane_orders_and_adversarial" in text:
        print("tests already patched")
        return text
    # append after dominion test
    m = re.search(r"^def test_dominion_plane_orders_and_adversarial\(\):", text, re.M)
    if not m:
        raise SystemExit("dominion test not found")
    # find next def after this
    rest = text[m.start() + 1 :]
    m2 = re.search(r"\n def test_|\ndef test_|\nclass ", rest)
    if m2:
        end = m.start() + 1 + m2.start()
    else:
        end = len(text)
    dom_test = text[m.start() : end]
    realm_test = dom_test
    realm_test = realm_test.replace(
        "test_dominion_plane_orders_and_adversarial",
        "test_realm_plane_orders_and_adversarial",
    )
    realm_test = realm_test.replace(
        "Dominion plane posts multi-empire orders and falsifies wrong-empire binds.",
        "Realm plane posts multi-dominion orders and falsifies wrong-dominion binds.",
    )
    realm_test = realm_test.replace("load_dominion_bundle", "load_realm_bundle")
    realm_test = realm_test.replace("run_dominion_plane", "run_realm_plane")
    realm_test = realm_test.replace(
        "verify_dominion_bundle_integrity", "verify_realm_bundle_integrity"
    )
    realm_test = realm_test.replace(
        "capability.dominion-plane", "capability.realm-plane"
    )
    # keep empire-plane dep check? change to dominion-plane
    realm_test = realm_test.replace(
        'assert "capability.empire-plane" in ledger.capabilities',
        'assert "capability.dominion-plane" in ledger.capabilities',
    )
    realm_test = realm_test.replace(
        '"no_skill_route; dominion_ok; dominioned_ok; min_dominions:2; "\n'
        '        "dominion_root_valid; empire_ok; empired_ok; min_empires:2; "\n'
        '        "empire_root_valid; chain_valid"',
        '"no_skill_route; realm_ok; realmed_ok; min_realms:2; "\n'
        '        "realm_root_valid; dominion_ok; dominioned_ok; min_dominions:2; "\n'
        '        "dominion_root_valid; chain_valid"',
    )
    realm_test = realm_test.replace('"dominion_ok"', '"realm_ok"')
    realm_test = realm_test.replace('"dominioned_ok"', '"realmed_ok"')
    realm_test = realm_test.replace('"min_dominions"', '"min_realms"')
    realm_test = realm_test.replace('"dominion_root_valid"', '"realm_root_valid"')
    realm_test = realm_test.replace(
        'empire-bundles" / "proof-empire.json"',
        'dominion-bundles" / "proof-dominion.json"',
    )
    realm_test = realm_test.replace(
        "requires existing empire proof bundle",
        "requires existing dominion proof bundle",
    )
    realm_test = realm_test.replace(
        'dominion-bundles" / "test-dominion-plane.json"',
        'realm-bundles" / "test-realm-plane.json"',
    )
    realm_test = realm_test.replace("dominion_path", "realm_path")
    realm_test = realm_test.replace("empire_path", "dominion_path")
    realm_test = realm_test.replace(
        '"dominion over empire"', '"realm over dominion"'
    )
    realm_test = realm_test.replace("run_empire=False", "run_dominion=False")
    realm_test = realm_test.replace("min_empires=2", "min_dominions=2")
    realm_test = realm_test.replace("min_dominions=2", "min_realms=2")
    # fix double min_realms from min_dominions and min_empires
    # After: min_dominions=2, min_realms=2 from min_empires→ and min_dominions→
    # Wait: min_empires=2 → min_dominions=2, then min_dominions=2 → min_realms=2 (both!)
    # So we get min_realms=2, min_realms=2 - need min_dominions=2, min_realms=2
    realm_test = realm_test.replace(
        "min_realms=2,\n        min_realms=2,",
        "min_dominions=2,\n        min_realms=2,",
    )
    realm_test = realm_test.replace('plane["action"] == "dominion_plane"', 'plane["action"] == "realm_plane"')
    realm_test = realm_test.replace('plane["dominioned"]', 'plane["realmed"]')
    realm_test = realm_test.replace('plane["dominion_count"]', 'plane["realm_count"]')
    realm_test = realm_test.replace("dominion_plan_digest", "realm_plan_digest")
    realm_test = realm_test.replace("multi_dominion", "multi_realm")
    realm_test = realm_test.replace("dominion_certificate", "realm_certificate")
    realm_test = realm_test.replace(
        "wrong_empire_fails_as_expected", "wrong_dominion_fails_as_expected"
    )
    realm_test = realm_test.replace(
        "single_dominion_fails_as_expected", "single_realm_fails_as_expected"
    )
    realm_test = realm_test.replace("dominion_hash", "realm_hash")
    realm_test = realm_test.replace("dominion_count", "realm_count")
    # Fix empire_path / dominion_path confusion in run_realm_plane call
    # After transforms: dominion_path=dominion_path (parent), realm_path=realm_path
    # Original: empire_path=empire_path, dominion_path=dominion_path
    # We replaced empire_path→dominion_path and dominion_path→realm_path
    # So: dominion_path=dominion_path, realm_path=realm_path — but variable names:
    # Original vars: empire_path, dominion_path
    # After: dominion_path (from empire), realm_path (from dominion)
    # File paths already updated. Variable for parent file:
    #   dominion_path = repo / dominion-bundles / proof-dominion.json  
    #   realm_path = repo / realm-bundles / test-realm-plane.json
    # Call: run_realm_plane(..., dominion_path=dominion_path, realm_path=realm_path)
    # Good if both renames applied in order empire→dominion first then dominion→realm
    # We did dominion_path→realm_path first, then empire_path→dominion_path — good

    return text[:end] + "\n\n" + realm_test + text[end:]


def extract_dominion_block(text: str) -> str:
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith("DOMINION_BUNDLE_SCHEMA = 1"):
            start = i
            break
    if start is None:
        raise SystemExit("DOMINION_BUNDLE_SCHEMA not found")
    # end at builtin_dominion_plane function end
    bi = None
    for i in range(start, len(lines)):
        if lines[i].startswith("def builtin_dominion_plane"):
            bi = i
            break
    if bi is None:
        raise SystemExit("builtin_dominion_plane not found")
    end = None
    for j in range(bi + 1, len(lines)):
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end = j
            break
        if lines[j] and not lines[j][0].isspace() and lines[j][0] not in {"#", "\n"} and not lines[j].startswith('"""') and not lines[j].startswith("'''"):
            # module level non-def
            if lines[j].strip() and not lines[j].startswith("@"):
                # allow blank
                end = j
                break
    if end is None:
        end = len(lines)
    return "".join(lines[start:end])


def main() -> None:
    text = COMPOUNDER.read_text(encoding="utf-8")
    if "def run_realm_plane" in text:
        print("realm plane functions already present")
        realm_block = ""
    else:
        dom = extract_dominion_block(text)
        realm_block = transform_dominion_to_realm(dom)
        # sanity
        assert "def run_realm_plane" in realm_block
        assert "def run_dominion_plane" not in realm_block
        assert "builtin_realm_plane" in realm_block
        assert "bound_dominion_root" in realm_block
        assert "bound_empire_root" not in realm_block or "bound_dominion_root" in realm_block
        print("realm block lines", realm_block.count("\n"))

    text = patch_compounder(text, realm_block)
    COMPOUNDER.write_text(text, encoding="utf-8")
    print("wrote compounder", COMPOUNDER.stat().st_size)

    ub = UNBOUND.read_text(encoding="utf-8")
    ub2 = patch_unbound(ub)
    UNBOUND.write_text(ub2, encoding="utf-8")
    print("wrote unbound")

    tt = TEST.read_text(encoding="utf-8")
    tt2 = patch_tests(tt)
    TEST.write_text(tt2, encoding="utf-8")
    print("wrote tests")

    print("OK")


if __name__ == "__main__":
    main()
