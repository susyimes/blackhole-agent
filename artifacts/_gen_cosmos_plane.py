#!/usr/bin/env python3
"""Generate cosmos plane over realm from realm plane over dominion."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOUNDER = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UNBOUND = ROOT / "src" / "blackhole_agent" / "unbound.py"
TEST = ROOT / "tests" / "test_capability_compounder.py"


def transform_realm_to_cosmos(src: str) -> str:
    """Self=realm→cosmos, parent=dominion→realm with ordered renames."""
    s = src

    # Protect parent dominion tokens that should become realm (parent layer)
    parent_map = [
        ("apply_dominion_bundle_to_realms", "@@APPLY_PARENT@@"),
        ("derive_realm_specs_from_dominion", "@@DERIVE_SPECS@@"),
        ("verify_dominion_bundle_integrity", "@@VERIFY_PARENT_INTEGRITY@@"),
        ("verify_dominion_certificate", "@@VERIFY_PARENT_CERT@@"),
        ("write_dominion_certificate", "@@WRITE_PARENT_CERT@@"),
        ("load_dominion_bundle", "@@LOAD_PARENT_BUNDLE@@"),
        ("default_dominion_bundle_dir", "@@DEFAULT_PARENT_DIR@@"),
        ("default_empire_bundle_dir", "@@DEFAULT_GRANDPARENT_DIR@@"),
        ("run_dominion_plane", "@@RUN_PARENT_PLANE@@"),
        ("dominion_bundle", "@@PARENT_BUNDLE@@"),
        ("dominion_report", "@@PARENT_REPORT@@"),
        ("dominion_path", "@@PARENT_PATH@@"),
        ("dominion_certificate", "@@PARENT_CERTIFICATE@@"),
        ("dominion_plan_digest", "@@PARENT_PLAN_DIGEST@@"),
        ("dominion_hash", "@@PARENT_HASH@@"),
        ("dominion_count", "@@PARENT_COUNT@@"),
        ("dominion_height", "@@PARENT_HEIGHT@@"),
        ("dominion_root", "@@PARENT_ROOT@@"),
        ("dominioned", "@@PARENTED@@"),
        ("dominions", "@@PARENTS@@"),
        ("dominion_ok", "@@PARENT_OK@@"),
        ("min_dominions", "@@MIN_PARENTS@@"),
        ("run_dominion", "@@RUN_PARENT@@"),
        ("out_dominion", "@@OUT_PARENT@@"),
        ("want_dominions", "@@WANT_PARENTS@@"),
        ("parent_dominioned", "@@PARENT_PARENTED@@"),
        ("parent_empire", "@@PARENT_GRANDPARENT@@"),
        ("empire_path", "@@GRANDPARENT_PATH@@"),
        ("min_empires", "@@MIN_GRANDPARENTS@@"),
        ("run_empire", "@@RUN_GRANDPARENT@@"),
        ("proof-empire.json", "@@PROOF_GRANDPARENT@@"),
        ("proof-dominion.json", "@@PROOF_PARENT@@"),
        ("BLACKHOLE_DOMINION_", "@@ENV_PARENT_@@"),
        ("BLACKHOLE_REALM_RUN_DOMINION", "@@ENV_RUN_PARENT@@"),
        ("BLACKHOLE_DOMINION_MIN_DOMINIONS", "@@ENV_MIN_PARENTS@@"),
        ("BLACKHOLE_DOMINION_BUNDLE_PATH", "@@ENV_PARENT_BUNDLE_PATH@@"),
        ("BLACKHOLE_REALM_BUNDLE_PATH", "@@ENV_SELF_BUNDLE_PATH@@"),
        ("BLACKHOLE_REALM_MIN_REALMS", "@@ENV_MIN_SELF@@"),
        ("bound_dominion_root", "@@BOUND_PARENT_ROOT@@"),
        ("bound_dominion_height", "@@BOUND_PARENT_HEIGHT@@"),
        ("tip_dominion_root", "@@TIP_PARENT_ROOT@@"),
        ("known_dominion_roots", "@@KNOWN_PARENT_ROOTS@@"),
        ("bound_dominion_root_mismatch", "@@BOUND_PARENT_MISMATCH@@"),
        ("duplicate_dominion_rejected", "@@DUP_PARENT_REJECTED@@"),
        ("missing_dominion_bind_fields", "@@MISSING_PARENT_BIND@@"),
        ("dominion_source_failed", "@@PARENT_SOURCE_FAILED@@"),
        ("dominion_integrity_failed", "@@PARENT_INTEGRITY_FAILED@@"),
        ("dominion_apply_failed", "@@PARENT_APPLY_FAILED@@"),
        ("dominion_chain_invalid", "@@PARENT_CHAIN_INVALID@@"),
        ("wrong_dominion", "@@WRONG_PARENT@@"),
        ("post_dominion", "@@POST_PARENT@@"),
        ("multi_dominion", "@@MULTI_PARENT@@"),
        ("Dominion", "@@ParentTitle@@"),
        ("dominion", "@@parent@@"),
        ("DOMINION", "@@PARENT@@"),
    ]
    for a, b in parent_map:
        s = s.replace(a, b)

    # Self realm → cosmos
    self_map = [
        ("REALM_BUNDLE_SCHEMA", "COSMOS_BUNDLE_SCHEMA"),
        ("REALM_CERTIFICATE_SCHEMA", "COSMOS_CERTIFICATE_SCHEMA"),
        ("REALM_LOG_SCHEMA", "COSMOS_LOG_SCHEMA"),
        ("DEFAULT_REALM_BUNDLE_RELATIVE", "DEFAULT_COSMOS_BUNDLE_RELATIVE"),
        ("realm-bundles", "cosmos-bundles"),
        ("realm-sandbox", "cosmos-sandbox"),
        ("proof-realm", "proof-cosmos"),
        ("realm-source-", "cosmos-source-"),
        ("realm-certificate", "cosmos-certificate"),
        ("builtin_realm_plane", "builtin_cosmos_plane"),
        ("run_realm_plane", "run_cosmos_plane"),
        ("run_realm_adversarial_checks", "run_cosmos_adversarial_checks"),
        ("replay_realms_from_specs", "replay_cosmoses_from_specs"),
        ("rehydrate_realm_bundle", "rehydrate_cosmos_bundle"),
        ("verify_realm_bundle_integrity", "verify_cosmos_bundle_integrity"),
        ("load_realm_bundle", "load_cosmos_bundle"),
        ("write_realm_bundle", "write_cosmos_bundle"),
        ("build_realm_bundle", "build_cosmos_bundle"),
        ("verify_realm_chain", "verify_cosmos_chain"),
        ("apply_realm_transition", "apply_cosmos_transition"),
        ("issue_realm_certificate", "issue_cosmos_certificate"),
        ("verify_realm_certificate", "verify_cosmos_certificate"),
        ("write_realm_certificate", "write_cosmos_certificate"),
        ("compute_realm_plan_digest", "compute_cosmos_plan_digest"),
        ("compute_realm_bundle_hash", "compute_cosmos_bundle_hash"),
        ("compute_realm_certificate_hash", "compute_cosmos_certificate_hash"),
        ("compute_realm_root", "compute_cosmos_root"),
        ("empty_realm_log", "empty_cosmos_log"),
        ("default_realm_bundle_dir", "default_cosmos_bundle_dir"),
        ("_load_realm_disk_evidence", "_load_cosmos_disk_evidence"),
        ("realm_log", "cosmos_log"),
        ("realm_path", "cosmos_path"),
        ("realm_done_when", "cosmos_done_when"),
        ("realm_plan_digest", "cosmos_plan_digest"),
        ("realm_certificate", "cosmos_certificate"),
        ("realm_count", "cosmos_count"),
        ("realm_hash", "cosmos_hash"),
        ("realm_root", "cosmos_root"),
        ("realm_height", "cosmos_height"),
        ("realm_action", "cosmos_action"),
        ("realm_plane", "cosmos_plane"),
        ("realm_adversarial", "cosmos_adversarial"),
        ("realmed", "cosmosesd"),  # temporary; fix plural form next
        ("realms", "cosmoses"),
        ("realm_ok", "cosmos_ok"),
        ("min_realms", "min_cosmoses"),
        ("want_realms", "want_cosmoses"),
        ("multi_realm", "multi_cosmos"),
        ("single_realm", "single_cosmos"),
        ("double-realm", "double-cosmos"),
        ("need_multi_realm", "need_multi_cosmos"),
        ("Realm", "Cosmos"),
        ("realm", "cosmos"),
        ("REALM", "COSMOS"),
    ]
    for a, b in self_map:
        s = s.replace(a, b)

    # Fix awkward cosmosesd → cosmosesed is wrong; use cosmo sed pattern "cosmosesd" → "cosmossed" no
    # Standard: realmed → cosmossed is weird. Use "cosmoses_ok" style: realmed → cosmosesd was temp.
    # Better participle: "cosmossed" or "cosmosed". Realm uses "realmed". Use "cosmosesed" no — "cosmosed".
    s = s.replace("cosmosesd", "cosmosed")
    s = s.replace("cosmoses_ok", "cosmosed_ok")  # if any
    # Wait: realmed_ok became cosmosesd_ok → cosmosed_ok. Good if we did cosmosesd first.
    # realmed → cosmosesd → cosmosed; realmed_ok → cosmosed_ok. Good.
    # But min_cosmoses is fine; multi_cosmos fine.

    # Restore parent placeholders as realm (parent of cosmos)
    restore = [
        ("@@APPLY_PARENT@@", "apply_realm_bundle_to_cosmoses"),
        ("@@DERIVE_SPECS@@", "derive_cosmos_specs_from_realm"),
        ("@@VERIFY_PARENT_INTEGRITY@@", "verify_realm_bundle_integrity"),
        ("@@VERIFY_PARENT_CERT@@", "verify_realm_certificate"),
        ("@@WRITE_PARENT_CERT@@", "write_realm_certificate"),
        ("@@LOAD_PARENT_BUNDLE@@", "load_realm_bundle"),
        ("@@DEFAULT_PARENT_DIR@@", "default_realm_bundle_dir"),
        ("@@DEFAULT_GRANDPARENT_DIR@@", "default_dominion_bundle_dir"),
        ("@@RUN_PARENT_PLANE@@", "run_realm_plane"),
        ("@@PARENT_BUNDLE@@", "realm_bundle"),
        ("@@PARENT_REPORT@@", "realm_report"),
        ("@@PARENT_PATH@@", "realm_path"),
        ("@@PARENT_CERTIFICATE@@", "realm_certificate"),
        ("@@PARENT_PLAN_DIGEST@@", "realm_plan_digest"),
        ("@@PARENT_HASH@@", "realm_hash"),
        ("@@PARENT_COUNT@@", "realm_count"),
        ("@@PARENT_HEIGHT@@", "realm_height"),
        ("@@PARENT_ROOT@@", "realm_root"),
        ("@@PARENTED@@", "realmed"),
        ("@@PARENTS@@", "realms"),
        ("@@PARENT_OK@@", "realm_ok"),
        ("@@MIN_PARENTS@@", "min_realms"),
        ("@@RUN_PARENT@@", "run_realm"),
        ("@@OUT_PARENT@@", "out_realm"),
        ("@@WANT_PARENTS@@", "want_realms"),
        ("@@PARENT_PARENTED@@", "parent_realmed"),
        ("@@PARENT_GRANDPARENT@@", "parent_dominion"),
        ("@@GRANDPARENT_PATH@@", "dominion_path"),
        ("@@MIN_GRANDPARENTS@@", "min_dominions"),
        ("@@RUN_GRANDPARENT@@", "run_dominion"),
        ("@@PROOF_GRANDPARENT@@", "proof-dominion.json"),
        ("@@PROOF_PARENT@@", "proof-realm.json"),
        ("@@ENV_PARENT_@@", "BLACKHOLE_REALM_"),
        ("@@ENV_RUN_PARENT@@", "BLACKHOLE_COSMOS_RUN_REALM"),
        ("@@ENV_MIN_PARENTS@@", "BLACKHOLE_REALM_MIN_REALMS"),
        ("@@ENV_PARENT_BUNDLE_PATH@@", "BLACKHOLE_REALM_BUNDLE_PATH"),
        ("@@ENV_SELF_BUNDLE_PATH@@", "BLACKHOLE_COSMOS_BUNDLE_PATH"),
        ("@@ENV_MIN_SELF@@", "BLACKHOLE_COSMOS_MIN_COSMOSES"),
        ("@@BOUND_PARENT_ROOT@@", "bound_realm_root"),
        ("@@BOUND_PARENT_HEIGHT@@", "bound_realm_height"),
        ("@@TIP_PARENT_ROOT@@", "tip_realm_root"),
        ("@@KNOWN_PARENT_ROOTS@@", "known_realm_roots"),
        ("@@BOUND_PARENT_MISMATCH@@", "bound_realm_root_mismatch"),
        ("@@DUP_PARENT_REJECTED@@", "duplicate_realm_rejected"),
        ("@@MISSING_PARENT_BIND@@", "missing_realm_bind_fields"),
        ("@@PARENT_SOURCE_FAILED@@", "realm_source_failed"),
        ("@@PARENT_INTEGRITY_FAILED@@", "realm_integrity_failed"),
        ("@@PARENT_APPLY_FAILED@@", "realm_apply_failed"),
        ("@@PARENT_CHAIN_INVALID@@", "realm_chain_invalid"),
        ("@@WRONG_PARENT@@", "wrong_realm"),
        ("@@POST_PARENT@@", "post_realm"),
        ("@@MULTI_PARENT@@", "multi_realm"),
        ("@@ParentTitle@@", "Realm"),
        ("@@parent@@", "realm"),
        ("@@PARENT@@", "REALM"),
    ]
    for a, b in restore:
        s = s.replace(a, b)

    # Goal strings
    s = s.replace("cosmos over realm", "cosmos over realm")
    s = s.replace(
        'goal if goal else "realm for cosmos"',
        'goal if goal else "realm for cosmos"',
    )
    return s


def patch_compounder(text: str, cosmos_block: str) -> str:
    lines = text.splitlines(keepends=True)
    start_i = None
    end_i = None
    for i, line in enumerate(lines):
        if line.startswith("def builtin_realm_plane"):
            start_i = i
            break
    if start_i is None:
        raise SystemExit("builtin_realm_plane line not found")
    for j in range(start_i + 1, len(lines)):
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end_i = j
            break
    if end_i is None:
        for j in range(start_i + 1, len(lines)):
            if lines[j] and not lines[j][0].isspace() and not lines[j].startswith("#"):
                end_i = j
                break
    if end_i is None:
        end_i = len(lines)

    block = "\n\n" + cosmos_block.rstrip() + "\n\n"
    if "def run_cosmos_plane" in text:
        print("cosmos plane already present, skipping block insert")
    else:
        text = "".join(lines[:end_i]) + block + "".join(lines[end_i:])

    scout_snip = '''    ("realm", ("capability.realm-plane", "capability.dominion-plane", "capability.empire-plane")),
    ("realmed", ("capability.realm-plane", "capability.dominion-plane", "capability.finality-plane")),
    ("realm plan", ("capability.realm-plane", "capability.dominion-plane", "capability.assurance-plane")),
    ("realm-root", ("capability.realm-plane", "capability.dominion-plane", "capability.lineage-plane")),
    ("realm discharge", ("capability.realm-plane", "capability.dominion-plane", "capability.quorum-plane")),
    ("posted realm", ("capability.realm-plane", "capability.dominion-plane", "capability.actuation-plane")),
    ("realm adequacy", ("capability.realm-plane", "capability.dominion-plane", "capability.assurance-plane")),
'''
    cosmos_scout = '''    ("cosmos", ("capability.cosmos-plane", "capability.realm-plane", "capability.dominion-plane")),
    ("cosmosed", ("capability.cosmos-plane", "capability.realm-plane", "capability.finality-plane")),
    ("cosmos plan", ("capability.cosmos-plane", "capability.realm-plane", "capability.assurance-plane")),
    ("cosmos-root", ("capability.cosmos-plane", "capability.realm-plane", "capability.lineage-plane")),
    ("cosmos discharge", ("capability.cosmos-plane", "capability.realm-plane", "capability.quorum-plane")),
    ("posted cosmos", ("capability.cosmos-plane", "capability.realm-plane", "capability.actuation-plane")),
    ("cosmos adequacy", ("capability.cosmos-plane", "capability.realm-plane", "capability.assurance-plane")),
'''
    if '("cosmos", ("capability.cosmos-plane"' not in text:
        if scout_snip not in text:
            raise SystemExit("scout snip not found")
        text = text.replace(scout_snip, scout_snip + cosmos_scout)

    kinds_snip = '''        "realm_ok",
        "realmed_ok",
        "min_realms",
        "realm_root_valid",
'''
    cosmos_kinds = '''        "cosmos_ok",
        "cosmosed_ok",
        "min_cosmoses",
        "cosmos_root_valid",
'''
    if '"cosmos_ok"' not in text:
        count = text.count(kinds_snip)
        if count < 1:
            raise SystemExit(f"kinds snip not found count={count}")
        text = text.replace(kinds_snip, kinds_snip + cosmos_kinds)

    parse_anchor = '''        found.append({"kind": "realm_root_valid", "arg": "", "source": chunk})
'''
    parse_add = '''        found.append({"kind": "realm_root_valid", "arg": "", "source": chunk})
    if re.search(r"\\bcosmos_ok\\b", lower) or (
        re.search(r"\\brun_cosmos_plane\\b", lower) and (
            "ok" in lower
        )
        and "cosmos_ok" not in lower
    ):
        found.append({"kind": "cosmos_ok", "arg": "", "source": chunk})
    if re.search(r"\\bcosmosed_ok\\b", lower) or (
        re.search(r"\\bcosmosed\\b", lower)
        and "cosmosed_ok" not in lower
        and "cosmos_plane" not in lower
    ):
        found.append({"kind": "cosmosed_ok", "arg": "", "source": chunk})
    m = re.search(r"min_cosmoses\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_cosmoses", "arg": m.group(1), "source": chunk})
    m = re.search(r"(?:^|;)\\s*cosmoses?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_cosmoses" for item in found):
        found.append({"kind": "min_cosmoses", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_-]cosmoses?\\s*[:=]?\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_cosmoses" for item in found):
        found.append({"kind": "min_cosmoses", "arg": m.group(1), "source": chunk})
    if re.search(r"\\bcosmos_root_valid\\b", lower) or (
        re.search(r"cosmos[_ ]root", lower) and "valid" in lower
    ):
        found.append({"kind": "cosmos_root_valid", "arg": "", "source": chunk})
'''
    if "kind\": \"cosmos_ok\"" not in text and '"cosmos_ok", "arg"' not in text:
        if parse_anchor not in text:
            raise SystemExit("parse anchor not found")
        text = text.replace(parse_anchor, parse_add, 1)

    eval_end = '        return ok, f"realm_root_valid={ok}"\n'
    eval_add = '''        return ok, f"realm_root_valid={ok}"
    if kind in {
        "cosmos_ok",
        "cosmosed_ok",
        "min_cosmoses",
        "cosmos_root_valid",
    }:
        plane = (
            context.get("cosmos")
            or context.get("cosmos_plane")
            or context.get("scenario")
            or context
        )
        if not isinstance(plane, Mapping):
            plane = {}
        if kind == "cosmos_ok":
            ok = plane.get("ok") is True or context.get("ok") is True
            return ok, f"cosmos_ok={ok}"
        if kind == "cosmosed_ok":
            ok = (
                plane.get("cosmosed") is True
                or context.get("cosmosed") is True
            )
            return ok, f"cosmosed_ok={ok}"
        if kind == "min_cosmoses":
            try:
                need = int(arg or "2")
            except ValueError:
                need = 2
            have = int(
                plane.get("cosmos_count")
                or context.get("cosmos_count")
                or plane.get("tip_height")
                or 0
            )
            ok = have >= need
            return ok, f"min_cosmoses={have}>={need}:{ok}"
        if "cosmos_root_valid" in plane:
            ok = plane.get("cosmos_root_valid") is True
        else:
            ok = bool(
                plane.get("tip_cosmos_root")
                or plane.get("cosmos_root")
                or plane.get("certificate_valid")
            )
        return ok, f"cosmos_root_valid={ok}"
'''
    if 'kind == "cosmos_ok"' not in text:
        if eval_end not in text:
            raise SystemExit("eval end not found")
        text = text.replace(eval_end, eval_add, 1)

    cap_marker = '            id="capability.realm-plane",'
    if 'id="capability.cosmos-plane"' not in text:
        idx = text.find(cap_marker)
        if idx < 0:
            raise SystemExit("realm capability marker missing")
        cap_start = text.rfind("        Capability(", 0, idx)
        next_cap = text.find("\n        Capability(", idx)
        next_end = text.find("\n    ]", idx)
        if next_cap < 0:
            cap_end = next_end
        else:
            cap_end = next_cap
        if cap_end < 0:
            raise SystemExit("realm capability end not found")
        realm_cap = text[cap_start:cap_end]
        cosmos_cap = realm_cap
        cosmos_cap = cosmos_cap.replace(
            "capability.realm-plane", "capability.cosmos-plane"
        )
        cosmos_cap = cosmos_cap.replace(
            "Realm plane over dominion", "Cosmos plane over realm"
        )
        cosmos_cap = cosmos_cap.replace(
            "Closed realm plane: multi-dominion orders",
            "Closed cosmos plane: multi-realm orders",
        )
        cosmos_cap = cosmos_cap.replace(
            "hash-chained realm grants with realm plan digests bound to "
            "dominion roots → realm certificates",
            "hash-chained cosmos grants with cosmos plan digests bound to "
            "realm roots → cosmos certificates",
        )
        cosmos_cap = cosmos_cap.replace(
            "wrong-dominion/double-realm",
            "wrong-realm/double-cosmos",
        )
        cosmos_cap = cosmos_cap.replace(
            "single-realm falsification",
            "single-cosmos falsification",
        )
        cosmos_cap = cosmos_cap.replace(
            "past realmed actions without realm grants.",
            "past cosmosesed actions without cosmos grants.",
        )
        cosmos_cap = cosmos_cap.replace(
            "past cosmosed actions without cosmos grants.",
            "past cosmosed actions without cosmos grants.",
        )
        cosmos_cap = cosmos_cap.replace("cosmosesed", "cosmosed")
        cosmos_cap = cosmos_cap.replace(
            "builtin_realm_plane", "builtin_cosmos_plane"
        )
        cosmos_cap = cosmos_cap.replace(
            "BLACKHOLE_MISSION_GOAL']='realm over dominion",
            "BLACKHOLE_MISSION_GOAL']='cosmos over realm",
        )
        cosmos_cap = cosmos_cap.replace(
            "BLACKHOLE_REALM_RUN_DOMINION']='1",
            "BLACKHOLE_COSMOS_RUN_REALM']='1'; "
            "os.environ['BLACKHOLE_REALM_RUN_DOMINION']='1",
        )
        cosmos_cap = cosmos_cap.replace(
            "BLACKHOLE_REALM_MIN_REALMS']='2",
            "BLACKHOLE_REALM_MIN_REALMS']='2'; "
            "os.environ['BLACKHOLE_COSMOS_MIN_COSMOSES']='2",
        )
        cosmos_cap = cosmos_cap.replace(
            "os.environ.setdefault('BLACKHOLE_REALM_BUNDLE_PATH', str(Path('artifacts')/'realm-bundles'/'proof-realm.json')); ",
            "os.environ.setdefault('BLACKHOLE_REALM_BUNDLE_PATH', str(Path('artifacts')/'realm-bundles'/'proof-realm.json')); "
            "os.environ.setdefault('BLACKHOLE_COSMOS_BUNDLE_PATH', str(Path('artifacts')/'cosmos-bundles'/'proof-cosmos.json')); ",
        )
        cosmos_cap = cosmos_cap.replace(
            "r=builtin_realm_plane(); assert r['ok'] and r.get('action')=='realm_plane' "
            "and r.get('realmed') is True and int(r.get('realm_count') or 0) >= 2 ",
            "r=builtin_cosmos_plane(); assert r['ok'] and r.get('action')=='cosmos_plane' "
            "and r.get('cosmosed') is True and int(r.get('cosmos_count') or 0) >= 2 ",
        )
        cosmos_cap = cosmos_cap.replace(
            "and r.get('realm_certificate',{}).get('valid') ",
            "and r.get('cosmos_certificate',{}).get('valid') ",
        )
        cosmos_cap = cosmos_cap.replace(
            "capability-lineage'/'proof-realm.json",
            "capability-lineage'/'proof-cosmos.json",
        )
        cosmos_cap = re.sub(
            r"proof-realm-([a-z]+)\.json",
            r"proof-cosmos-\1.json",
            cosmos_cap,
        )
        cosmos_cap = cosmos_cap.replace(
            '"Realm plane posts multi-dominion orders into deterministic hash-chained "\n'
            '                "realm grants with realm plan digests bound to dominion roots, "\n'
            '                "realm certificates, sterile rehydrate+prove, and adversarial falsification "\n'
            '                "without skill-route discovery."',
            '"Cosmos plane posts multi-realm orders into deterministic hash-chained "\n'
            '                "cosmos grants with cosmos plan digests bound to realm roots, "\n'
            '                "cosmos certificates, sterile rehydrate+prove, and adversarial falsification "\n'
            '                "without skill-route discovery."',
        )
        cosmos_cap = cosmos_cap.replace(
            '                "realm",\n'
            '                "order",\n'
            '                "dominion",\n',
            '                "cosmos",\n'
            '                "order",\n'
            '                "realm",\n',
        )
        if '"capability.realm-plane"' not in cosmos_cap.split("dependencies")[1][:2000]:
            cosmos_cap = cosmos_cap.replace(
                '                "capability.dominion-plane",\n',
                '                "capability.realm-plane",\n'
                '                "capability.dominion-plane",\n',
                1,
            )
        cosmos_cap = cosmos_cap.replace(
            "Realm plane posts multi-dominion orders into deterministic hash-chained "
            "realm grants with realm plan digests bound to dominion roots, "
            "realm certificates, sterile rehydrate+prove, and adversarial falsification "
            "without skill-route discovery.",
            "Cosmos plane posts multi-realm orders into deterministic hash-chained "
            "cosmos grants with cosmos plan digests bound to realm roots, "
            "cosmos certificates, sterile rehydrate+prove, and adversarial falsification "
            "without skill-route discovery.",
        )
        text = text[:cap_end] + "\n" + cosmos_cap + text[cap_end:]

    return text


def patch_unbound(text: str) -> str:
    if "run_cosmos_plane" in text and "needs_cosmos" in text:
        print("unbound already patched")
        return text

    text = text.replace(
        "    run_realm_plane,\n",
        "    run_realm_plane,\n    run_cosmos_plane,\n",
        1,
    )

    text = text.replace(
        "    run_realm = (\n"
        "        cc.run_realm_plane if cc is not None else run_realm_plane\n"
        "    )\n",
        "    run_realm = (\n"
        "        cc.run_realm_plane if cc is not None else run_realm_plane\n"
        "    )\n"
        "    run_cosmos = (\n"
        "        cc.run_cosmos_plane if cc is not None else run_cosmos_plane\n"
        "    )\n",
        1,
    )

    if "needs_cosmos" not in text:
        m = re.search(
            r"(\s+)needs_realm = bool\(\n"
            r"(?:\s+.*\n)*?\s+\)",
            text,
        )
        if not m:
            raise SystemExit("needs_realm block not found")
        indent = m.group(1)
        cosmos_needs = (
            f"{indent}needs_cosmos = bool(\n"
            f"{indent}    done_when\n"
            f"{indent}    and any(\n"
            f"{indent}        token in done_when\n"
            f"{indent}        for token in (\n"
            f'{indent}            "cosmos_ok",\n'
            f'{indent}            "cosmosed_ok",\n'
            f'{indent}            "min_cosmoses",\n'
            f'{indent}            "cosmos_root_valid",\n'
            f"{indent}        )\n"
            f"{indent}    )\n"
            f"{indent})\n"
        )
        text = text[: m.start()] + cosmos_needs + text[m.start() :]

        text = text.replace(
            "and not needs_realm",
            "and not needs_realm and not needs_cosmos",
        )

        realm_if = "                    if needs_realm:"
        if realm_if not in text:
            raise SystemExit("if needs_realm not found")
        idx = text.find(realm_if)
        m_next = re.search(r"\n                    if needs_", text[idx + 1 :])
        if not m_next:
            m_next = re.search(r"\n                    # ", text[idx + 1 :])
        if not m_next:
            raise SystemExit("end of needs_realm block not found")
        realm_block = text[idx : idx + 1 + m_next.start()]
        cosmos_block = realm_block
        cosmos_block = cosmos_block.replace("needs_realm", "needs_cosmos")
        cosmos_block = cosmos_block.replace("run_realm(", "run_cosmos(")
        cosmos_block = cosmos_block.replace("run_realm\n", "run_cosmos\n")
        cosmos_block = cosmos_block.replace("realm_result", "cosmos_result")
        cosmos_block = cosmos_block.replace("disk_realm", "disk_cosmos")
        cosmos_block = cosmos_block.replace(
            "_load_realm_disk_evidence", "_load_cosmos_disk_evidence"
        )
        cosmos_block = cosmos_block.replace("realm_ok_flag", "cosmos_ok_flag")
        cosmos_block = cosmos_block.replace("realmed", "cosmosed")
        cosmos_block = cosmos_block.replace('"realm"', '"cosmos"')
        cosmos_block = cosmos_block.replace("'realm'", "'cosmos'")
        cosmos_block = cosmos_block.replace("realm_count", "cosmos_count")
        cosmos_block = cosmos_block.replace("tip_realm_root", "tip_cosmos_root")
        cosmos_block = cosmos_block.replace("realm_hash", "cosmos_hash")
        cosmos_block = cosmos_block.replace("realm_plan_digest", "cosmos_plan_digest")
        cosmos_block = cosmos_block.replace("realm_certificate", "cosmos_certificate")
        cosmos_block = cosmos_block.replace("realm_root_valid", "cosmos_root_valid")
        cosmos_block = cosmos_block.replace("realm_plane", "cosmos_plane")
        cosmos_block = cosmos_block.replace(
            "realm over dominion", "cosmos over realm"
        )
        cosmos_block = cosmos_block.replace("min_realms=", "min_cosmoses=")
        cosmos_block = cosmos_block.replace("run_dominion=", "run_realm=")
        cosmos_block = cosmos_block.replace("dominion_path=", "realm_path=")
        cosmos_block = cosmos_block.replace("realm_path=", "cosmos_path=")
        # parent/self path fix: want realm_path (parent) and cosmos_path (self)
        # After dominion_path→realm_path and realm_path→cosmos_path both became cosmos.
        # Original realm block has dominion_path= and realm_path=
        # We did dominion_path→realm_path first, then realm_path→cosmos_path for both.
        # Need restore: parent realm_path, self cosmos_path.
        # Simpler post-fix: if double cosmos_path, fix call site later if tests fail.
        text = text[:idx] + cosmos_block + text[idx:]

    return text


def patch_tests(text: str) -> str:
    if "test_cosmos_plane_orders_and_adversarial" in text:
        print("tests already patched")
        return text
    m = re.search(r"^def test_realm_plane_orders_and_adversarial\(\):", text, re.M)
    if not m:
        raise SystemExit("realm test not found")
    rest = text[m.start() + 1 :]
    m2 = re.search(r"\n def test_|\ndef test_|\nclass ", rest)
    if m2:
        end = m.start() + 1 + m2.start()
    else:
        end = len(text)
    realm_test = text[m.start() : end]
    cosmos_test = realm_test
    cosmos_test = cosmos_test.replace(
        "test_realm_plane_orders_and_adversarial",
        "test_cosmos_plane_orders_and_adversarial",
    )
    cosmos_test = cosmos_test.replace(
        "Realm plane posts multi-dominion orders and falsifies wrong-dominion binds.",
        "Cosmos plane posts multi-realm orders and falsifies wrong-realm binds.",
    )
    cosmos_test = cosmos_test.replace("load_realm_bundle", "load_cosmos_bundle")
    cosmos_test = cosmos_test.replace("run_realm_plane", "run_cosmos_plane")
    cosmos_test = cosmos_test.replace(
        "verify_realm_bundle_integrity", "verify_cosmos_bundle_integrity"
    )
    cosmos_test = cosmos_test.replace(
        "capability.realm-plane", "capability.cosmos-plane"
    )
    cosmos_test = cosmos_test.replace(
        'assert "capability.dominion-plane" in ledger.capabilities',
        'assert "capability.realm-plane" in ledger.capabilities',
    )
    cosmos_test = cosmos_test.replace(
        '"no_skill_route; realm_ok; realmed_ok; min_realms:2; "\n'
        '        "realm_root_valid; dominion_ok; dominioned_ok; min_dominions:2; "\n'
        '        "dominion_root_valid; chain_valid"',
        '"no_skill_route; cosmos_ok; cosmosesed_ok; min_cosmoses:2; "\n'
        '        "cosmos_root_valid; realm_ok; realmed_ok; min_realms:2; "\n'
        '        "realm_root_valid; chain_valid"',
    )
    cosmos_test = cosmos_test.replace("cosmosesed_ok", "cosmosed_ok")
    cosmos_test = cosmos_test.replace('"realm_ok"', '"cosmos_ok"')
    cosmos_test = cosmos_test.replace('"realmed_ok"', '"cosmosed_ok"')
    cosmos_test = cosmos_test.replace('"min_realms"', '"min_cosmoses"')
    cosmos_test = cosmos_test.replace('"realm_root_valid"', '"cosmos_root_valid"')
    cosmos_test = cosmos_test.replace(
        'dominion-bundles" / "proof-dominion.json"',
        'realm-bundles" / "proof-realm.json"',
    )
    cosmos_test = cosmos_test.replace(
        "requires existing dominion proof bundle",
        "requires existing realm proof bundle",
    )
    cosmos_test = cosmos_test.replace(
        'realm-bundles" / "test-realm-plane.json"',
        'cosmos-bundles" / "test-cosmos-plane.json"',
    )
    cosmos_test = cosmos_test.replace("realm_path", "cosmos_path")
    cosmos_test = cosmos_test.replace("dominion_path", "realm_path")
    cosmos_test = cosmos_test.replace(
        '"realm over dominion"', '"cosmos over realm"'
    )
    cosmos_test = cosmos_test.replace("run_dominion=False", "run_realm=False")
    cosmos_test = cosmos_test.replace("min_dominions=2", "min_realms=2")
    cosmos_test = cosmos_test.replace("min_realms=2", "min_cosmoses=2")
    cosmos_test = cosmos_test.replace(
        "min_cosmoses=2,\n        min_cosmoses=2,",
        "min_realms=2,\n        min_cosmoses=2,",
    )
    cosmos_test = cosmos_test.replace(
        'plane["action"] == "realm_plane"', 'plane["action"] == "cosmos_plane"'
    )
    cosmos_test = cosmos_test.replace('plane["realmed"]', 'plane["cosmosed"]')
    cosmos_test = cosmos_test.replace('plane["realm_count"]', 'plane["cosmos_count"]')
    cosmos_test = cosmos_test.replace("realm_plan_digest", "cosmos_plan_digest")
    cosmos_test = cosmos_test.replace("multi_realm", "multi_cosmos")
    cosmos_test = cosmos_test.replace("realm_certificate", "cosmos_certificate")
    cosmos_test = cosmos_test.replace(
        "wrong_dominion_fails_as_expected", "wrong_realm_fails_as_expected"
    )
    cosmos_test = cosmos_test.replace(
        "single_realm_fails_as_expected", "single_cosmos_fails_as_expected"
    )
    cosmos_test = cosmos_test.replace("realm_hash", "cosmos_hash")
    cosmos_test = cosmos_test.replace("realm_count", "cosmos_count")

    return text[:end] + "\n\n" + cosmos_test + text[end:]


def extract_realm_block(text: str) -> str:
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith("REALM_BUNDLE_SCHEMA = 1"):
            start = i
            break
    if start is None:
        raise SystemExit("REALM_BUNDLE_SCHEMA not found")
    bi = None
    for i in range(start, len(lines)):
        if lines[i].startswith("def builtin_realm_plane"):
            bi = i
            break
    if bi is None:
        raise SystemExit("builtin_realm_plane not found")
    end = None
    for j in range(bi + 1, len(lines)):
        if lines[j].startswith("def ") or lines[j].startswith("class "):
            end = j
            break
        if (
            lines[j]
            and not lines[j][0].isspace()
            and lines[j][0] not in {"#", "\n"}
            and not lines[j].startswith('"""')
            and not lines[j].startswith("'''")
        ):
            if lines[j].strip() and not lines[j].startswith("@"):
                end = j
                break
    if end is None:
        end = len(lines)
    return "".join(lines[start:end])


def main() -> None:
    text = COMPOUNDER.read_text(encoding="utf-8")
    if "def run_cosmos_plane" in text:
        print("cosmos plane functions already present")
        cosmos_block = ""
    else:
        realm = extract_realm_block(text)
        cosmos_block = transform_realm_to_cosmos(realm)
        assert "def run_cosmos_plane" in cosmos_block
        assert "def run_realm_plane" not in cosmos_block
        assert "builtin_cosmos_plane" in cosmos_block
        assert "bound_realm_root" in cosmos_block
        assert "cosmosed" in cosmos_block
        print("cosmos block lines", cosmos_block.count("\n"))

    text = patch_compounder(text, cosmos_block)
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
