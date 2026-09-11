from __future__ import annotations

from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.elbl_actuation import (
    DEFAULT_ELBLDIGEST,
    DEFAULT_ELBLID,
    DEFAULT_ENTROPY,
    ELBL_ACTUATION_GOAL,
    ELBL_ACTUATION_ID,
    ELBL_LEFTOVER,
    ELI_LABEL,
    REQUIRED_EL_TTL,
    SENTINEL,
    builtin_elbl_actuation_proof,
    eli_stack_accepted,
    encode_el_mapping,
    encode_eli_el_stack,
    encode_eli_mapping,
    parse_eli_el_stack,
    parse_ldp_pdu,
    run_elbl_workflow,
)


def test_rfc6790_eli_is_special_label_7_with_clear_bos() -> None:
    stack = parse_eli_el_stack(encode_eli_el_stack(entropy=DEFAULT_ENTROPY))
    assert stack["eli"]["label"] == ELI_LABEL
    assert stack["eli"]["bos"] is False
    assert stack["el"]["ttl"] == REQUIRED_EL_TTL
    assert eli_stack_accepted(stack, entropy=DEFAULT_ENTROPY) is True


def test_rfc6790_el_ttl_nonzero_is_rejected() -> None:
    stack = parse_eli_el_stack(encode_eli_el_stack(entropy=DEFAULT_ENTROPY, el_ttl=1))
    assert eli_stack_accepted(stack, entropy=DEFAULT_ENTROPY) is False


def test_el_mapping_carries_elblid() -> None:
    packet = parse_ldp_pdu(encode_el_mapping(identity=SENTINEL, elblid=DEFAULT_ELBLID))
    assert packet["el"] is True
    assert packet["elc"] is True
    assert packet["elblid"] == DEFAULT_ELBLID
    assert packet["identity"] == SENTINEL


def test_eli_mapping_carries_label_7() -> None:
    packet = parse_ldp_pdu(encode_eli_mapping(identity=SENTINEL, elblid=DEFAULT_ELBLID))
    assert packet["eli"] is True
    assert packet["label"] == ELI_LABEL
    assert packet["stack"] is not None
    assert eli_stack_accepted(packet["stack"], entropy=DEFAULT_ENTROPY)


def test_live_el_eli_cycle_seals_elbldigest() -> None:
    live = run_elbl_workflow()
    assert live["ok"] is True
    assert live["elblid"] == DEFAULT_ELBLID
    assert live["elbldigest"] == DEFAULT_ELBLDIGEST
    assert live["sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()


def test_missing_elblid_stays_forbidden() -> None:
    missing = run_elbl_workflow(with_elblid=False)
    assert missing["ok"] is False
    assert missing["error"] == "missing_elblid"


def test_builtin_proof_registers_capability() -> None:
    report = builtin_elbl_actuation_proof()
    assert report["ok"] is True, report.get("failed")
    assert report["action"] == "elbl_actuation"
    assert report["passed_count"] >= 12
    assert not report["used_skill_route_discovery"]
    assert report["mission_goal"] == ELBL_ACTUATION_GOAL
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[ELBL_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "elblid" in capability.tags
    assert "rfc6790" in capability.tags
    assert "inbldid-gated inbldigest" in ELBL_LEFTOVER
