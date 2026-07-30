"""Validate done_when for capability.restructuring-plane."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("BLACKHOLE_MISSION_GOAL", "restructuring over resolution")
os.environ.setdefault(
    "BLACKHOLE_DONE_WHEN",
    "min_capabilities:5;capability_exists:repo.import-health;no_skill_route",
)
os.environ.setdefault("BLACKHOLE_PROGRAM_MAX_STEPS", "3")
os.environ.setdefault("BLACKHOLE_RESTRUCTURING_RUN_RESOLUTION", "1")
os.environ.setdefault("BLACKHOLE_QUORUM_RUN_CONTINUITY", "0")
os.environ.setdefault("BLACKHOLE_CONTINUITY_RUN_RECON", "0")
os.environ.setdefault("BLACKHOLE_RESTRUCTURING_MIN_RESTRUCTURINGS", "2")
os.environ.setdefault("BLACKHOLE_RESOLUTION_MIN_RESOLUTIONS", "2")


def main() -> int:
    from blackhole_agent.capability_compounder import (
        builtin_restructuring_plane,
        ensure_seeded_ledger,
        evaluate_outcome_contract,
        parse_outcome_contract,
    )

    r = builtin_restructuring_plane()
    assert r.get("ok") is True, r
    assert r.get("action") == "restructuring_plane", r.get("action")
    assert r.get("restructured") is True, r.get("restructured")
    assert int(r.get("restructuring_count") or 0) >= 2, r.get("restructuring_count")
    assert int(r.get("tip_height") or 0) >= 2, r.get("tip_height")
    assert (r.get("restructuring_certificate") or {}).get("valid") is True
    assert (r.get("integrity") or {}).get("ok") is True
    assert (r.get("rehydrate") or {}).get("ok") is True
    assert (r.get("prove") or {}).get("ok") is True
    assert (r.get("chain") or {}).get("valid") is True
    assert (r.get("adversarial") or {}).get("ok") is True
    assert r.get("used_skill_route_discovery") is False

    path, ledger = ensure_seeded_ledger(ROOT)
    assert "capability.restructuring-plane" in ledger.capabilities, path
    cap = ledger.capabilities["capability.restructuring-plane"]
    assert cap.entry.endswith("builtin_restructuring_plane")

    kinds = [
        p["kind"]
        for p in (
            parse_outcome_contract(
                "restructuring_ok; restructured_ok; min_restructurings:2; restructuring_root_valid"
            ).get("predicates")
            or []
        )
    ]
    assert kinds == [
        "restructuring_ok",
        "restructured_ok",
        "min_restructurings",
        "restructuring_root_valid",
    ], kinds

    ctx = {
        "used_skill_route_discovery": False,
        "restructuring": {
            "ok": True,
            "restructured": True,
            "restructuring_count": int(r.get("restructuring_count") or 0),
            "tip_height": int(r.get("tip_height") or 0),
            "restructuring_root_valid": True,
            "certificate_valid": True,
        },
        "restructuring_plane": {
            "ok": True,
            "restructured": True,
            "restructuring_count": int(r.get("restructuring_count") or 0),
            "restructuring_root_valid": True,
        },
        "restructuring_count": int(r.get("restructuring_count") or 0),
        "resolution": {
            "ok": True,
            "resolved": True,
            "resolution_count": int(r.get("resolution_count") or 2),
            "resolution_root_valid": True,
        },
        "resolution_count": int(r.get("resolution_count") or 2),
        "chain": r.get("chain") or {"ok": True, "valid": True},
    }
    ev = evaluate_outcome_contract(
        ROOT,
        "no_skill_route; restructuring_ok; restructured_ok; min_restructurings:2; "
        "restructuring_root_valid; resolution_ok; resolved_ok; min_resolutions:2; "
        "resolution_root_valid; chain_valid; capability_exists:repo.import-health",
        context=ctx,
        run_programs=False,
    )
    assert ev.get("ok") is True and ev.get("met") is True, ev

    unbound_src = (ROOT / "src" / "blackhole_agent" / "unbound.py").read_text(
        encoding="utf-8"
    )
    assert "needs_restructuring" in unbound_src
    assert "run_restructuring_plane" in unbound_src
    assert "restructuring_ok" in unbound_src

    print(
        "OK",
        {
            "restructuring_count": r.get("restructuring_count"),
            "tip_height": r.get("tip_height"),
            "cert": (r.get("restructuring_certificate") or {}).get("certificate_hash"),
            "adversarial": (r.get("adversarial") or {}).get("ok"),
            "ledger": str(path),
            "final_contract_met": (r.get("final_contract") or {}).get("met"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
