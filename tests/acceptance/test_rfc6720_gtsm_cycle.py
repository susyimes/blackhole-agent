"""Acceptance probe: RFC 6720 GTSM/TTL seals a gtsmid-gated gtsmdigest.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees.
"""

from __future__ import annotations

import json

observed: dict[str, object] = {"family": "rfc6720-ldp-gtsm-ttl"}
passed = False

try:
    import blackhole_agent.gtsm_actuation as gtsm
except Exception as error:  # pragma: no cover - baseline stub or missing module
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)

workflow = getattr(gtsm, "run_gtsm_workflow", None)
enforced = getattr(gtsm, "gtsm_enforced", None)
ttl_ok = getattr(gtsm, "ttl_accepted", None)
encode_hello = getattr(gtsm, "encode_common_hello_parms", None)
parse_hello = getattr(gtsm, "parse_common_hello_parms", None)
hop_limit = getattr(gtsm, "GTSM_HOP_LIMIT", None)
default_id = getattr(gtsm, "DEFAULT_GTSMID", 0)
default_digest = getattr(gtsm, "DEFAULT_GTSMDIGEST", 0)

if not all((workflow, enforced, ttl_ok, encode_hello, parse_hello, hop_limit)):
    observed["error"] = "rfc6720_cycle_unavailable"
    observed["detail"] = "GTSM/TTL LDP helpers are not implemented"
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)

basic = parse_hello(encode_hello(gtsm=True, targeted=False))
targeted = parse_hello(encode_hello(gtsm=True, targeted=True))
enforces_basic = bool(enforced(basic))
ignores_targeted = not bool(enforced(targeted))
accepts_255 = bool(ttl_ok(int(hop_limit), gtsm_on=True))
rejects_254 = not bool(ttl_ok(254, gtsm_on=True))
live = workflow()
observed.update(
    {
        "ok": bool(live.get("ok")),
        "gtsmid": int(live.get("gtsmid") or 0),
        "gtsmdigest": int(live.get("gtsmdigest") or 0),
        "sentinel": str(live.get("sentinel") or ""),
        "error": str(live.get("error") or ""),
        "enforces_basic_discovery": enforces_basic,
        "ignores_targeted_hello": ignores_targeted,
        "accepts_hop_limit_255": accepts_255,
        "rejects_hop_limit_254": rejects_254,
        "default_gtsmid": int(default_id or 0),
        "default_gtsmdigest": int(default_digest or 0),
    }
)
passed = bool(
    live.get("ok")
    and int(live.get("gtsmid") or 0) == int(default_id or 0)
    and int(live.get("gtsmdigest") or 0) == int(default_digest or 0)
    and int(live.get("gtsmdigest") or 0) > 0
    and enforces_basic
    and ignores_targeted
    and accepts_255
    and rejects_254
    and str(live.get("sentinel") or "") == "BH-GTSM-OK"
)
print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
