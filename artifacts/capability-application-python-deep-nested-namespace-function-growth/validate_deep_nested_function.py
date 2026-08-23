"""One-shot validation for two-level nested-namespace module-function forage."""

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
    "Optional later work is reflecting functions exported two submodule levels down "
    "so sdists whose API is package.subpackage.submodule.func rather than "
    "package.submodule.func can be foraged the same way."
)


def main() -> int:
    root = Path(".")
    assert leftover_marker_ids(LEFTOVER) == (
        "capability.application-python-deep-nested-function-growth-plane",
    )
    assert leftover_is_open(LEFTOVER, root) is False
    ledger = load_ledger(default_ledger_path(root))
    cap = ledger.capabilities["capability.application-python-deep-nested-function-growth-plane"]
    assert cap.last_proof_exit_code == 0
    adapter = (root / "capabilities/absorbed/python-stdnum/acquisition_adapter.py").read_text(
        encoding="utf-8"
    )
    assert "ad.nrt.compact" in adapter
    manifest = json.loads(
        (root / "capabilities/absorbed/python-stdnum/absorption.json").read_text(encoding="utf-8")
    )
    provides = manifest.get("provides")
    if isinstance(provides, list):
        assert "ad_nrt_compact_output" in provides
    else:
        assert provides == "ad_nrt_compact_output"
    proof = prove_absorbed_capability("python-stdnum")
    assert proof.get("ok"), proof
    fetched = live_registry_archive(
        {"name": "python-stdnum", "slug": "python-stdnum", "registry": "pypi", "version": "2.2"}
    )
    assert fetched and fetched.get("ok"), fetched
    with tempfile.TemporaryDirectory(prefix="validate-python-stdnum-") as tmp:
        inferred = infer_acquisition_spec(
            slug="python-stdnum",
            name="python-stdnum",
            source=Path(str(fetched["path"])),
            staging_root=Path(tmp),
            hint="stdnum",
            close_deps=True,
        )
    assert inferred.get("ok"), inferred
    rec = inferred["record"]
    assert rec["winner"] == "ad.nrt.compact"
    assert rec["python_deep_nested_namespace_function"] is True
    assert rec["python_nested_namespace_function"] is False
    assert rec["python_class_instance"] is False
    print("ok", rec["winner"], rec["provides"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
