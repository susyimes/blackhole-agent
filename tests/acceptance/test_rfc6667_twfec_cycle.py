"""Acceptance probe: RFC 6667 TYPED/WILDCARD seals a twfecid-gated twfecdigest.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees.
"""

from __future__ import annotations

import json

observed: dict[str, object] = {"family": "rfc6667-ldp-typed-wildcard-fec"}
passed = False

try:
    import blackhole_agent.twfec_actuation as twfec
except Exception as error:  # pragma: no cover - baseline stub or missing module
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)

workflow = getattr(twfec, "run_twfec_workflow", None)
match_fn = getattr(twfec, "match_typed_wildcard", None)
encode_wildcard = getattr(twfec, "encode_typed_wildcard_fec", None)
parse_fec = getattr(twfec, "parse_fec_element", None)
pwid_type = getattr(twfec, "PWID_FEC_TYPE", None)
gen_type = getattr(twfec, "GEN_PWID_FEC_TYPE", None)
eth_type = getattr(twfec, "ETHERNET_PW_TYPE", None)
default_id = getattr(twfec, "DEFAULT_TWFECID", 0)
default_digest = getattr(twfec, "DEFAULT_TWFECDIGEST", 0)

if not all((workflow, match_fn, encode_wildcard, parse_fec, pwid_type, gen_type, eth_type)):
    observed["error"] = "rfc6667_cycle_unavailable"
    observed["detail"] = "TYPED/WILDCARD LDP helpers are not implemented"
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)

pwid = {
    "kind": "pwid",
    "fec_type": pwid_type,
    "pw_type": eth_type,
    "group_id": 1,
    "pw_id": int(default_id or 1),
    "twfecid": int(default_id or 1),
}
gen = {
    "kind": "gen_pwid",
    "fec_type": gen_type,
    "pw_id": int(default_id or 1),
    "twfecid": int(default_id or 1),
}
wildcard_eth = parse_fec(encode_wildcard(fec_type=pwid_type, pw_type=eth_type))[0]
wildcard_gen = parse_fec(encode_wildcard(fec_type=gen_type))[0]
matches_pwid = bool(match_fn(pwid, wildcard_eth))
rejects_gen = not bool(match_fn(gen, wildcard_eth)) and not bool(match_fn(pwid, wildcard_gen))
live = workflow()
observed.update(
    {
        "ok": bool(live.get("ok")),
        "twfecid": int(live.get("twfecid") or 0),
        "twfecdigest": int(live.get("twfecdigest") or 0),
        "sentinel": str(live.get("sentinel") or ""),
        "error": str(live.get("error") or ""),
        "matches_pwid": matches_pwid,
        "rejects_gen_pwid": rejects_gen,
        "default_twfecid": int(default_id or 0),
        "default_twfecdigest": int(default_digest or 0),
    }
)
passed = bool(
    live.get("ok")
    and int(live.get("twfecid") or 0) == int(default_id or 0)
    and int(live.get("twfecdigest") or 0) == int(default_digest or 0)
    and int(live.get("twfecdigest") or 0) > 0
    and matches_pwid
    and rejects_gen
    and str(live.get("sentinel") or "") == "BH-TWFEC-OK"
)
print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
