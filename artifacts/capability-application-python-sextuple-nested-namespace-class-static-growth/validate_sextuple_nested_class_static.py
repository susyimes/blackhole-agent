"""One-shot validation for six-level nested-namespace class-static forage."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from blackhole_agent.capability_absorption import prove_absorbed_capability
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_targets import live_registry_archive
from blackhole_agent.capability_foraging import infer_acquisition_spec
from blackhole_agent.kernel_leftover import leftover_is_open, leftover_marker_ids

LEFTOVER = (
    "Optional later work is reflecting Python nested-namespace class statics "
    "six submodule levels down so sdists whose covering API is a six-level "
    "nested Class.method static rather than a five-level nested Class.method "
    "static can be foraged the same way."
)
CALLABLE = (
    "ads.googleads.v25.services.services.account_budget_proposal_service."
    "AccountBudgetProposalServiceClient.common_billing_account_path"
)
PROVIDES = "ads_googleads_v25_services_services_account_budget_proposal_serv"


def main() -> int:
    root = Path(".")
    assert leftover_marker_ids(LEFTOVER) == (
        "capability.application-python-sext-nested-static-growth-plane",
    )
    assert leftover_is_open(LEFTOVER, root) is False
    ledger = load_ledger(default_ledger_path(root))
    cap = ledger.capabilities["capability.application-python-sext-nested-static-growth-plane"]
    assert cap.last_proof_exit_code == 0
    adapter = (root / "capabilities/absorbed/google-ads/acquisition_adapter.py").read_text(encoding="utf-8")
    assert CALLABLE in adapter
    manifest = json.loads((root / "capabilities/absorbed/google-ads/absorption.json").read_text(encoding="utf-8"))
    provides = manifest.get("provides")
    if isinstance(provides, list):
        assert PROVIDES in provides
    else:
        assert provides == PROVIDES
    assert list(manifest.get("requires") or []) == ["billing_account"]
    proof = prove_absorbed_capability("google-ads")
    assert proof.get("ok"), proof
    fetched = live_registry_archive(
        {"name": "google-ads", "slug": "google-ads", "registry": "pypi", "version": "31.4.0"}
    )
    assert fetched and fetched.get("ok"), fetched
    with tempfile.TemporaryDirectory(prefix="validate-google-ads-") as tmp:
        inferred = infer_acquisition_spec(
            slug="google-ads",
            name="google-ads",
            source=Path(str(fetched["path"])),
            staging_root=Path(tmp),
            hint="google-ads",
            runtime="python",
            close_deps=True,
        )
    assert inferred.get("ok"), inferred
    rec = inferred["record"]
    assert rec["winner"] == CALLABLE
    assert rec["python_sextuple_nested_namespace_class_static"] is True
    assert rec["python_quintuple_nested_namespace_class_static"] is False
    assert rec["python_quadruple_nested_namespace_class_static"] is False
    assert rec["python_nested_namespace_class_static"] is False
    assert rec["python_class_static"] is False
    print("ok", rec["winner"], rec["provides"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
