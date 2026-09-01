from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.experience_fuel import leftover_next_step
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.leftover_catalog_handoff import (
    HARVESTED_CATALOG_HANDOFF,
    LEFTOVER_CATALOG_HANDOFF_DONE_WHEN,
    LEFTOVER_CATALOG_HANDOFF_GOAL,
    LEFTOVER_CATALOG_HANDOFF_ID,
    UNRELATED_LEFTOVER,
    builtin_leftover_catalog_handoff_proof,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID


def test_catalog_handoff_is_not_leftover() -> None:
    assert leftover_next_step(HARVESTED_CATALOG_HANDOFF) == ""
    assert leftover_next_step("None. Mission complete. " + HARVESTED_CATALOG_HANDOFF) == ""
    assert leftover_next_step(UNRELATED_LEFTOVER) == UNRELATED_LEFTOVER
    assert leftover_marker_ids(LEFTOVER_CATALOG_HANDOFF_GOAL) == (LEFTOVER_CATALOG_HANDOFF_ID,)
    assert leftover_marker_ids(HARVESTED_CATALOG_HANDOFF) == (LEFTOVER_CATALOG_HANDOFF_ID,)
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)


def test_builtin_proof_drops_handoff_and_binds_tftp() -> None:
    report = builtin_leftover_catalog_handoff_proof()
    assert report["ok"] is True
    assert report["action"] == "leftover_catalog_handoff"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["harvest_drops_catalog_handoff"]
    assert report["checks"]["unrelated_leftover_stays_open"]
    assert report["checks"]["proved_closer_consumes_handoff"]
    assert report["checks"]["exhausted_catalog_binds_tftp"]
    assert report["checks"]["local_bind_fills_tftp"]
    assert report["mission_goal"] == LEFTOVER_CATALOG_HANDOFF_GOAL
    assert report["done_when"] == LEFTOVER_CATALOG_HANDOFF_DONE_WHEN
    assert LEFTOVER_CATALOG_HANDOFF_ID in LOCAL_DENYLIST
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[LEFTOVER_CATALOG_HANDOFF_ID]
    assert capability.last_proof_exit_code == 0
    assert "leftover" in capability.tags
    assert "tftp" in capability.tags
    assert TFTP_ACTUATION_ID not in ledger.capabilities
