"""One-shot validation for two-level nested-namespace class-static forage."""

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
    "two submodule levels down so sdists whose API is "
    "package.subpackage.submodule.Class.method rather than a "
    "two-level module function can be foraged the same way."
)


def main() -> int:
    root = Path(".")
    assert leftover_marker_ids(LEFTOVER) == (
        "capability.application-python-deep-nested-static-growth-plane",
    )
    assert leftover_is_open(LEFTOVER, root) is False
    ledger = load_ledger(default_ledger_path(root))
    cap = ledger.capabilities["capability.application-python-deep-nested-static-growth-plane"]
    assert cap.last_proof_exit_code == 0
    adapter = (root / "capabilities/absorbed/isbnlib/acquisition_adapter.py").read_text(encoding="utf-8")
    assert "dev.helpers.File.exists" in adapter
    manifest = json.loads(
        (root / "capabilities/absorbed/isbnlib/absorption.json").read_text(encoding="utf-8")
    )
    provides = manifest.get("provides")
    if isinstance(provides, list):
        assert "dev_helpers_file_exists_output" in provides
    else:
        assert provides == "dev_helpers_file_exists_output"
    proof = prove_absorbed_capability("isbnlib")
    assert proof.get("ok"), proof
    fetched = live_registry_archive(
        {"name": "isbnlib", "slug": "isbnlib", "registry": "pypi", "version": "3.10.14"}
    )
    assert fetched and fetched.get("ok"), fetched
    with tempfile.TemporaryDirectory(prefix="validate-isbnlib-") as tmp:
        inferred = infer_acquisition_spec(
            slug="isbnlib",
            name="isbnlib",
            source=Path(str(fetched["path"])),
            staging_root=Path(tmp),
            hint="isbnlib",
            close_deps=True,
        )
    assert inferred.get("ok"), inferred
    rec = inferred["record"]
    assert rec["winner"] == "dev.helpers.File.exists"
    assert rec["python_deep_nested_namespace_class_static"] is True
    assert rec["python_nested_namespace_class_static"] is False
    assert rec["python_deep_nested_namespace_function"] is False
    assert rec["python_class_instance"] is False
    print("ok", rec["winner"], rec["provides"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
