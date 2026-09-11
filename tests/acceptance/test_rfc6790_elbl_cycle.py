"""Acceptance probe: RFC 6790 EL/ELI seals an elblid-gated elbldigest.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees.
"""

from __future__ import annotations

import json

observed: dict[str, object] = {"family": "rfc6790-mpls-el-eli"}
passed = False

try:
    import blackhole_agent.elbl_actuation as elbl
except Exception as error:  # pragma: no cover - baseline stub or missing module
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)

workflow = getattr(elbl, "run_elbl_workflow", None)
accepted = getattr(elbl, "eli_stack_accepted", None)
encode_stack = getattr(elbl, "encode_eli_el_stack", None)
parse_stack = getattr(elbl, "parse_eli_el_stack", None)
eli_label = getattr(elbl, "ELI_LABEL", None)
required_ttl = getattr(elbl, "REQUIRED_EL_TTL", None)
default_id = getattr(elbl, "DEFAULT_ELBLID", 0)
default_digest = getattr(elbl, "DEFAULT_ELBLDIGEST", 0)
default_entropy = getattr(elbl, "DEFAULT_ENTROPY", 0)

if not all((workflow, accepted, encode_stack, parse_stack, eli_label is not None, required_ttl is not None)):
    observed["error"] = "rfc6790_cycle_unavailable"
    observed["detail"] = "EL/ELI MPLS helpers are not implemented"
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)

legal = parse_stack(encode_stack(entropy=int(default_entropy)))
illegal_ttl = parse_stack(encode_stack(entropy=int(default_entropy), el_ttl=1))
eli_is_7 = int(legal["eli"]["label"]) == int(eli_label)
eli_bos_clear = legal["eli"]["bos"] is False
el_ttl_zero = int(legal["el"]["ttl"]) == int(required_ttl)
accepts_legal = bool(accepted(legal, entropy=int(default_entropy)))
rejects_ttl = not bool(accepted(illegal_ttl, entropy=int(default_entropy)))
live = workflow()
observed.update(
    {
        "ok": bool(live.get("ok")),
        "elblid": int(live.get("elblid") or 0),
        "elbldigest": int(live.get("elbldigest") or 0),
        "sentinel": str(live.get("sentinel") or ""),
        "error": str(live.get("error") or ""),
        "eli_is_special_label_7": eli_is_7,
        "eli_bos_clear": eli_bos_clear,
        "el_ttl_zero": el_ttl_zero,
        "accepts_legal_stack": accepts_legal,
        "rejects_nonzero_el_ttl": rejects_ttl,
        "default_elblid": int(default_id or 0),
        "default_elbldigest": int(default_digest or 0),
    }
)
passed = bool(
    live.get("ok")
    and int(live.get("elblid") or 0) == int(default_id or 0)
    and int(live.get("elbldigest") or 0) == int(default_digest or 0)
    and int(live.get("elbldigest") or 0) > 0
    and eli_is_7
    and eli_bos_clear
    and el_ttl_zero
    and accepts_legal
    and rejects_ttl
    and str(live.get("sentinel") or "") == "BH-ELBL-OK"
)
print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
