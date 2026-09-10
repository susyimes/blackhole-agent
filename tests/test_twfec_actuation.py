from __future__ import annotations

from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.twfec_actuation import (
    DEFAULT_TWFECID,
    DEFAULT_TWFECDIGEST,
    ETHERNET_PW_TYPE,
    GEN_PWID_FEC_TYPE,
    PWID_FEC_TYPE,
    SENTINEL,
    TWFEC_ACTUATION_GOAL,
    TWFEC_ACTUATION_ID,
    TWFEC_LEFTOVER,
    builtin_twfec_actuation_proof,
    encode_typed_mapping,
    encode_typed_wildcard_fec,
    match_typed_wildcard,
    parse_fec_element,
    parse_ldp_pdu,
    run_twfec_workflow,
)


def test_rfc6667_typed_wildcard_matches_pwid_not_gen_pwid() -> None:
    pwid = {
        "kind": "pwid",
        "fec_type": PWID_FEC_TYPE,
        "pw_type": ETHERNET_PW_TYPE,
        "group_id": 1,
        "pw_id": DEFAULT_TWFECID,
        "twfecid": DEFAULT_TWFECID,
    }
    gen = {
        "kind": "gen_pwid",
        "fec_type": GEN_PWID_FEC_TYPE,
        "pw_id": DEFAULT_TWFECID,
        "twfecid": DEFAULT_TWFECID,
    }
    wildcard = parse_fec_element(encode_typed_wildcard_fec(fec_type=PWID_FEC_TYPE, pw_type=ETHERNET_PW_TYPE))[0]
    assert match_typed_wildcard(pwid, wildcard) is True
    assert match_typed_wildcard(gen, wildcard) is False


def test_typed_mapping_carries_twfecid() -> None:
    packet = parse_ldp_pdu(encode_typed_mapping(identity=SENTINEL, twfecid=DEFAULT_TWFECID))
    assert packet["typed"] is True
    assert packet["twfecid"] == DEFAULT_TWFECID
    assert packet["identity"] == SENTINEL


def test_live_typed_wildcard_cycle_seals_twfecdigest() -> None:
    live = run_twfec_workflow()
    assert live["ok"] is True
    assert live["twfecid"] == DEFAULT_TWFECID
    assert live["twfecdigest"] == DEFAULT_TWFECDIGEST
    assert live["sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()


def test_missing_twfecid_stays_forbidden() -> None:
    missing = run_twfec_workflow(with_twfecid=False)
    assert missing["ok"] is False
    assert missing["error"] == "missing_twfecid"


def test_builtin_proof_registers_capability() -> None:
    report = builtin_twfec_actuation_proof()
    assert report["ok"] is True
    assert report["action"] == "twfec_actuation"
    assert report["passed_count"] >= 12
    assert not report["used_skill_route_discovery"]
    assert report["mission_goal"] == TWFEC_ACTUATION_GOAL
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[TWFEC_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "twfecid" in capability.tags
    assert "rfc6667" in capability.tags
    assert "gtsmid-gated gtsmdigest" in TWFEC_LEFTOVER
