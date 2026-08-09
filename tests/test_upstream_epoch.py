"""Unit tests for the upstream epoch plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent import upstream_epoch as ue
from blackhole_agent import upstream_fleet as uf


def test_builtin_proof_green() -> None:
    result = ue.builtin_upstream_epoch_proof()
    assert result["ok"]
    assert result["multi_wave_progressed"]
    assert result["feedback_retires_work"]
    assert result["seal_verified"]
    assert result["tamper_detected"]
    assert result["idle_short_circuits"]
    assert result["budget_stops"]
    assert result["rank_only"]
    assert result["terminal_feedback_idles"]
    assert result["empty_refused"]
    assert result["no_progress_stops"]
    assert not result["used_skill_route_discovery"]


def test_default_feedback_retires_campaignable(tmp_path: Path) -> None:
    stew = tmp_path / "stew"
    stew.mkdir()
    uf._proof_target(
        stew,
        name="a",
        version="1.0.0",
        defects=[{
            "id": "a-1",
            "title": "a",
            "kind": "complexity",
            "patch": "patches/a.patch",
            "repro": "repros/a.py",
        }],
    )
    uf._proof_target(
        stew,
        name="b",
        version="2.0.0",
        defects=[{
            "id": "b-1",
            "title": "b",
            "kind": "complexity",
            "patch": "patches/b.patch",
            "repro": "repros/b.py",
        }],
    )
    campaign = ue._proof_campaign_runner(tmp_path / "camps")
    epoch = ue.run_epoch(
        stewardship_root=stew,
        portfolio=None,
        max_waves=3,
        per_wave_dispatch_limit=1,
        dispatch=True,
        campaign_runner=campaign,
        out_root=tmp_path / "epochs",
    )
    assert epoch["ok"]
    assert epoch["total_dispatched_ok"] == 2
    assert epoch["stop_reason"] == "epoch_idle"
    # Second wave must not re-dispatch the first target.
    first_name = epoch["waves"][0]["dispatches"][0]["name"]
    second_name = epoch["waves"][1]["dispatches"][0]["name"]
    assert first_name != second_name


def test_verify_detects_wave_digest_tamper(tmp_path: Path) -> None:
    stew = tmp_path / "stew"
    stew.mkdir()
    uf._proof_target(
        stew,
        name="m",
        version="1.0.0",
        defects=[{
            "id": "m-1",
            "title": "m",
            "kind": "correctness",
            "patch": "patches/m.patch",
            "repro": "repros/m.py",
        }],
    )
    portfolio = uf._proof_portfolio([{
        "name": "m",
        "version": "1.0.0",
        "defect_id": "m-1",
        "outcome": "impact_merged",
        "impact_digest": "d" * 64,
        "ok": True,
    }])
    epoch = ue.run_epoch(
        stewardship_root=stew,
        portfolio=portfolio,
        max_waves=2,
        dispatch=False,
        out_root=tmp_path / "epochs",
    )
    assert ue.verify_epoch_receipt(Path(epoch["epoch_dir"]))["ok"]
    path = Path(epoch["epoch_dir"]) / "epoch.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["wave_digests"] = ["0" * 64]
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    checked = ue.verify_epoch_receipt(Path(epoch["epoch_dir"]))
    assert not checked["ok"]
    assert "wave_digests" in (checked.get("mismatched") or [])


def test_dispatch_budget_caps_attempts(tmp_path: Path) -> None:
    stew = tmp_path / "stew"
    stew.mkdir()
    for i in range(3):
        uf._proof_target(
            stew,
            name=f"t{i}",
            version="1.0.0",
            defects=[{
                "id": f"d{i}",
                "title": f"d{i}",
                "kind": "complexity",
                "patch": f"patches/d{i}.patch",
                "repro": f"repros/d{i}.py",
            }],
        )
    campaign = ue._proof_campaign_runner(tmp_path / "camps")
    epoch = ue.run_epoch(
        stewardship_root=stew,
        max_waves=10,
        per_wave_dispatch_limit=1,
        dispatch_budget=2,
        dispatch=True,
        campaign_runner=campaign,
        out_root=tmp_path / "epochs",
    )
    assert epoch["total_dispatched"] == 2
    assert epoch["stop_reason"] == "dispatch_budget"
