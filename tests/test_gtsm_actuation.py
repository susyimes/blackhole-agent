from __future__ import annotations

from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.gtsm_actuation import (
    DEFAULT_GTSMDIGEST,
    DEFAULT_GTSMID,
    GTSM_ACTUATION_GOAL,
    GTSM_ACTUATION_ID,
    GTSM_HOP_LIMIT,
    GTSM_LEFTOVER,
    SENTINEL,
    builtin_gtsm_actuation_proof,
    encode_common_hello_parms,
    encode_gtsm_hello,
    encode_ttl_init,
    gtsm_enforced,
    parse_common_hello_parms,
    parse_ldp_pdu,
    run_gtsm_workflow,
    ttl_accepted,
)


def test_rfc6720_g_flag_enforces_only_on_basic_discovery() -> None:
    basic = parse_common_hello_parms(encode_common_hello_parms(gtsm=True, targeted=False))
    targeted = parse_common_hello_parms(encode_common_hello_parms(gtsm=True, targeted=True))
    cleared = parse_common_hello_parms(encode_common_hello_parms(gtsm=False, targeted=False))
    assert gtsm_enforced(basic) is True
    assert gtsm_enforced(targeted) is False
    assert gtsm_enforced(cleared) is False


def test_rfc6720_ttl_requires_hop_limit_255() -> None:
    assert ttl_accepted(GTSM_HOP_LIMIT, gtsm_on=True) is True
    assert ttl_accepted(254, gtsm_on=True) is False
    assert ttl_accepted(GTSM_HOP_LIMIT, gtsm_on=False) is False


def test_hello_carries_gtsmid() -> None:
    packet = parse_ldp_pdu(encode_gtsm_hello(identity=SENTINEL, gtsmid=DEFAULT_GTSMID))
    assert packet["gtsm"] is True
    assert packet["gtsmid"] == DEFAULT_GTSMID
    assert packet["identity"] == SENTINEL


def test_ttl_init_carries_hop_limit() -> None:
    packet = parse_ldp_pdu(encode_ttl_init(identity=SENTINEL))
    assert packet["ttl"] is True
    assert packet["hop_limit"] == GTSM_HOP_LIMIT


def test_live_gtsm_ttl_cycle_seals_gtsmdigest() -> None:
    live = run_gtsm_workflow()
    assert live["ok"] is True
    assert live["gtsmid"] == DEFAULT_GTSMID
    assert live["gtsmdigest"] == DEFAULT_GTSMDIGEST
    assert live["sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()


def test_missing_gtsmid_stays_forbidden() -> None:
    missing = run_gtsm_workflow(with_gtsmid=False)
    assert missing["ok"] is False
    assert missing["error"] == "missing_gtsmid"


def test_builtin_proof_registers_capability() -> None:
    report = builtin_gtsm_actuation_proof()
    assert report["ok"] is True
    assert report["action"] == "gtsm_actuation"
    assert report["passed_count"] >= 12
    assert not report["used_skill_route_discovery"]
    assert report["mission_goal"] == GTSM_ACTUATION_GOAL
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[GTSM_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "gtsmid" in capability.tags
    assert "rfc6720" in capability.tags
    assert "elblid-gated elbldigest" in GTSM_LEFTOVER
