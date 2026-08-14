"""Tests for the capability absorption plane."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from blackhole_agent.capability_absorption import (
    ABSORBED_ROOT,
    FIXTURE_TOOL,
    PERSIST_PATH,
    REPO_ROOT,
    absorb_external_capability,
    absorbed_step_record,
    builtin_absorption_plane_proof,
    capability_id_for_slug,
    load_manifest,
    load_persisted_absorbed_steps,
    load_persisted_records,
    prove_absorbed_capability,
    record_digest,
    reseal_absorbed_records,
    run_absorption_cases,
    run_absorption_plane,
    run_absorption_scenario,
    tree_digest,
    upsert_persisted_record,
    verify_absorption_plane,
)
from blackhole_agent.capability_application import (
    build_application_registry,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_absorption import _absorption_task
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger


def test_manifest_loads_and_validates() -> None:
    manifest = load_manifest(FIXTURE_TOOL)
    assert manifest["slug"] == "text-reverser"
    assert manifest["provides"] == ["reversed_text"]
    assert len(manifest["cases"]) >= 2


def test_manifest_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="manifest not found"):
        load_manifest(tmp_path)


def test_manifest_rejects_bad_cases(tmp_path: Path) -> None:
    manifest = json.loads((FIXTURE_TOOL / "absorption.json").read_text(encoding="utf-8"))
    manifest["cases"] = [manifest["cases"][0]]
    (tmp_path / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="at least two"):
        load_manifest(tmp_path)


def test_manifest_rejects_undeclared_expect_keys(tmp_path: Path) -> None:
    manifest = json.loads((FIXTURE_TOOL / "absorption.json").read_text(encoding="utf-8"))
    manifest["cases"][0]["expect"] = {"unknown_key": 1}
    (tmp_path / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="undeclared provides"):
        load_manifest(tmp_path)


def test_cases_pass_against_fixture_source() -> None:
    manifest = load_manifest(FIXTURE_TOOL)
    result = run_absorption_cases(FIXTURE_TOOL, manifest)
    assert result["ok"], result
    assert result["case_count"] == len(manifest["cases"])


def test_tree_digest_stable_and_sensitive(tmp_path: Path) -> None:
    first = tree_digest(FIXTURE_TOOL)
    assert first == tree_digest(FIXTURE_TOOL)
    copied = tmp_path / "tool"
    shutil.copytree(FIXTURE_TOOL, copied)
    assert tree_digest(copied) == first
    (copied / "tool.py").write_text(
        (copied / "tool.py").read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8"
    )
    assert tree_digest(copied) != first


def test_tree_digest_ignores_tool_caches(tmp_path: Path) -> None:
    """Lint/test tooling must never break a vendored tree digest."""

    copied = tmp_path / "tool"
    shutil.copytree(FIXTURE_TOOL, copied)
    before = tree_digest(copied)
    for cache_dir in (".ruff_cache", ".mypy_cache", "__pycache__"):
        cache = copied / cache_dir
        cache.mkdir()
        (cache / "junk").write_text("tooling litter", encoding="utf-8")
    assert tree_digest(copied) == before


def test_absorb_registers_proves_and_persists() -> None:
    result = absorb_external_capability(FIXTURE_TOOL)
    assert result["ok"], result
    capability_id = capability_id_for_slug("text-reverser")
    assert result["capability_id"] == capability_id

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    capability = ledger.capabilities[capability_id]
    assert capability.last_proof_exit_code == 0
    assert "absorbed" in capability.tags

    vendored = ABSORBED_ROOT / "text-reverser"
    assert (vendored / "tool.py").is_file()
    assert (vendored / "absorption.json").is_file()
    assert tree_digest(vendored) == result["vendored_tree_digest"]

    records = {record["slug"]: record for record in load_persisted_records()}
    record = records["text-reverser"]
    assert record["record_digest"] == record_digest(record)

    # Idempotent: re-absorbing an unchanged tool rewrites nothing.
    before = PERSIST_PATH.read_text(encoding="utf-8")
    again = absorb_external_capability(FIXTURE_TOOL)
    assert again["ok"]
    assert PERSIST_PATH.read_text(encoding="utf-8") == before


def test_prove_absorbed_capability_live() -> None:
    absorb_external_capability(FIXTURE_TOOL)
    proof = prove_absorbed_capability("text-reverser")
    assert proof["ok"], proof
    assert proof["record_digest_match"] and proof["tree_digest_match"] and proof["cases_pass"]


def test_tampered_vendored_tree_fails_proof(tmp_path: Path) -> None:
    absorb_external_capability(FIXTURE_TOOL)
    tampered_root = tmp_path / "absorbed"
    shutil.copytree(ABSORBED_ROOT / "text-reverser", tampered_root / "text-reverser")
    tool_file = tampered_root / "text-reverser" / "tool.py"
    tool_file.write_text(tool_file.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    proof = prove_absorbed_capability("text-reverser", vendored_root=tampered_root)
    assert not proof["ok"]
    assert not proof["tree_digest_match"]


def test_drifted_tool_behavior_fails_proof(tmp_path: Path) -> None:
    """A tool whose behavior drifted (not just bytes appended) fails its cases."""

    drifted = tmp_path / "drifted"
    shutil.copytree(FIXTURE_TOOL, drifted)
    (drifted / "tool.py").write_text(
        "import json, sys\n"
        "state = json.load(sys.stdin)\n"
        "json.dump({'reversed_text': str(state['raw_text'])}, sys.stdout)\n",
        encoding="utf-8",
    )
    manifest = load_manifest(drifted)
    result = run_absorption_cases(drifted, manifest)
    assert not result["ok"]


def test_hand_edited_record_fails_digest(tmp_path: Path) -> None:
    absorb_external_capability(FIXTURE_TOOL)
    record = next(item for item in load_persisted_records() if item["slug"] == "text-reverser")
    forged = dict(record)
    forged["cases"] = [dict(record["cases"][0], expect={"reversed_text": "forged"})]
    assert record_digest(forged) != record["record_digest"]


def test_absorbed_steps_feed_the_planner() -> None:
    absorb_external_capability(FIXTURE_TOOL)
    capability_id = capability_id_for_slug("text-reverser")
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    record = next(item for item in load_persisted_records() if item["slug"] == "text-reverser")
    task = _absorption_task(record)

    steps = load_persisted_absorbed_steps()
    assert capability_id in steps

    # Pre-absorption honesty: hidden absorbed capability -> honestly unplannable.
    hidden_registry = build_application_registry(
        ledger, hide=[capability_id], include_synthesized=True, include_absorbed=True
    )
    assert capability_id not in hidden_registry
    assert plan_application_task(task, hidden_registry) is None

    # Grown registry: plans, executes, matches the oracle.
    grown_registry = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
    result = run_application_task(task, grown_registry)
    assert result["ok"], result
    assert capability_id in result["plan"]
    assert result["outcome"]["reversed_text"] == task.oracle["reversed_text"]


def test_absorption_plane_end_to_end(tmp_path: Path) -> None:
    result = run_absorption_plane(tmp_path / "report")
    assert result["ok"], result
    assert result["unplannable_before"]
    assert result["grown_plan_solved"]
    assert result["ablation_unplannable"]
    assert result["tamper_rejected"]
    assert result["forgery_rejected"]

    verification = verify_absorption_plane(tmp_path / "report")
    assert verification["ok"], verification

    # A tampered report fails verification.
    report_path = tmp_path / "report" / "text-reverser-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["verdicts"]["tamper_rejected"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert not verify_absorption_plane(tmp_path / "report")["ok"]


def test_absorption_scenario_by_slug(tmp_path: Path) -> None:
    absorb_external_capability(FIXTURE_TOOL)
    result = run_absorption_scenario("text-reverser", tmp_path / "scenario")
    assert result["ok"], result
    verification = verify_absorption_plane(tmp_path / "scenario", slug="text-reverser")
    assert verification["ok"], verification
    # Unknown slug fails honestly.
    missing = run_absorption_scenario("no-such-tool", tmp_path / "scenario")
    assert not missing["ok"]


def test_builtin_absorption_plane_proof() -> None:
    result = builtin_absorption_plane_proof()
    assert result["ok"], result
    assert result["verify_ok"]


def test_upsert_replaces_by_slug(tmp_path: Path) -> None:
    persist = tmp_path / "absorbed-steps.json"
    manifest = load_manifest(FIXTURE_TOOL)
    record = absorbed_step_record(manifest, "digest-one")
    assert upsert_persisted_record(record, persist)
    assert not upsert_persisted_record(record, persist)  # idempotent
    updated = absorbed_step_record(manifest, "digest-two")
    assert upsert_persisted_record(updated, persist)
    records = load_persisted_records(persist)
    assert len(records) == 1
    assert records[0]["vendored_tree_digest"] == "digest-two"


def test_sealed_tree_digests_are_checkout_reproducible() -> None:
    """Every persisted seal must match the vendored tree on disk.

    A seal that covers files git never tracks (packaging metadata, caches)
    can never prove again from a clean checkout — this guard fails that
    drift before a milestone does.
    """

    records = load_persisted_records()
    assert records, "expected persisted absorbed records"
    for record in records:
        slug = record["slug"]
        vendored_dir = ABSORBED_ROOT / slug
        assert vendored_dir.is_dir(), f"missing vendored tree: {slug}"
        skipped = [
            path
            for path in vendored_dir.rglob("*")
            if any(part.endswith((".egg-info", ".dist-info")) for part in path.parts)
        ]
        assert not skipped, f"{slug} vendors packaging metadata: {skipped[:3]}"
        assert tree_digest(vendored_dir) == record["vendored_tree_digest"], slug


def test_tree_digest_skips_packaging_metadata(tmp_path: Path) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "tool.py").write_text("print('ok')\n", encoding="utf-8")
    packaged = tmp_path / "packaged"
    shutil.copytree(bare, packaged)
    egg_info = packaged / "pkg.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text("Metadata-Version: 2.1\n", encoding="utf-8")
    dist_info = packaged / "pkg.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text("Metadata-Version: 2.1\n", encoding="utf-8")
    assert tree_digest(packaged) == tree_digest(bare)


def _scratch_drifted_record(tmp_path: Path) -> tuple[Path, Path]:
    """Scratch persist file + vendored tree with a stale (drifted) seal."""

    absorb_external_capability(FIXTURE_TOOL)
    record = next(item for item in load_persisted_records() if item["slug"] == "text-reverser")
    vendored_root = tmp_path / "absorbed"
    shutil.copytree(ABSORBED_ROOT / "text-reverser", vendored_root / "text-reverser")
    drifted = dict(record)
    drifted["vendored_tree_digest"] = "0" * 64
    drifted["record_digest"] = record_digest(drifted)
    persist = tmp_path / "absorbed-steps.json"
    upsert_persisted_record(drifted, persist)
    return persist, vendored_root


def test_reseal_repairs_drifted_record(tmp_path: Path) -> None:
    persist, vendored_root = _scratch_drifted_record(tmp_path)
    receipt = reseal_absorbed_records(
        persist_path=persist, vendored_root=vendored_root, output_dir=tmp_path / "artifacts"
    )
    assert receipt["ok"], receipt
    assert [entry["slug"] for entry in receipt["resealed"]] == ["text-reverser"]
    assert not receipt["refusals"]
    proof = prove_absorbed_capability(
        "text-reverser", persist_path=persist, vendored_root=vendored_root
    )
    assert proof["ok"], proof
    # Idempotent: a second reseal finds nothing drifted.
    again = reseal_absorbed_records(
        persist_path=persist, vendored_root=vendored_root, output_dir=tmp_path / "artifacts"
    )
    assert again["ok"] and not again["resealed"] and again["unchanged"] == ["text-reverser"]


def test_reseal_refuses_broken_behavior(tmp_path: Path) -> None:
    persist, vendored_root = _scratch_drifted_record(tmp_path)
    tool_file = vendored_root / "text-reverser" / "tool.py"
    tool_file.write_text(
        "import json, sys\n"
        "state = json.load(sys.stdin)\n"
        "json.dump({'reversed_text': 'broken'}, sys.stdout)\n",
        encoding="utf-8",
    )
    receipt = reseal_absorbed_records(
        persist_path=persist, vendored_root=vendored_root, output_dir=tmp_path / "artifacts"
    )
    assert not receipt["ok"]
    assert [entry["slug"] for entry in receipt["refusals"]] == ["text-reverser"]
    assert not receipt["resealed"]
    record = load_persisted_records(persist)[0]
    assert record["vendored_tree_digest"] == "0" * 64  # untouched
