"""One-shot validation for nested-namespace module-function forage."""

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
    "Optional later work is reflecting functions exported only on nested submodules "
    "so sdists whose API is package.subpackage.submodule.func rather than a "
    "class method can be foraged the same way."
)


def main() -> int:
    root = Path(".")
    assert leftover_marker_ids(LEFTOVER) == (
        "capability.application-python-nested-function-growth-plane",
    )
    assert leftover_is_open(LEFTOVER, root) is False
    ledger = load_ledger(default_ledger_path(root))
    cap = ledger.capabilities["capability.application-python-nested-function-growth-plane"]
    assert cap.last_proof_exit_code == 0
    adapter = (root / "capabilities/absorbed/packaging/acquisition_adapter.py").read_text(
        encoding="utf-8"
    )
    assert "utils.canonicalize_name" in adapter
    manifest = json.loads(
        (root / "capabilities/absorbed/packaging/absorption.json").read_text(encoding="utf-8")
    )
    provides = manifest.get("provides")
    if isinstance(provides, list):
        assert "utils_canonicalize_name_output" in provides
    else:
        assert provides == "utils_canonicalize_name_output"
    proof = prove_absorbed_capability("packaging")
    assert proof.get("ok"), proof
    fetched = live_registry_archive(
        {"name": "packaging", "slug": "packaging", "registry": "pypi", "version": "26.3"}
    )
    assert fetched and fetched.get("ok"), fetched
    with tempfile.TemporaryDirectory(prefix="validate-packaging-") as tmp:
        inferred = infer_acquisition_spec(
            slug="packaging",
            name="packaging",
            source=Path(str(fetched["path"])),
            staging_root=Path(tmp),
            hint="packaging",
            close_deps=True,
        )
    assert inferred.get("ok"), inferred
    rec = inferred["record"]
    assert rec["winner"] == "utils.canonicalize_name"
    assert rec["python_nested_namespace_function"] is True
    assert rec["python_deep_nested_namespace_function"] is False
    assert rec["python_class_instance"] is False
    print("ok", rec["winner"], rec["provides"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
