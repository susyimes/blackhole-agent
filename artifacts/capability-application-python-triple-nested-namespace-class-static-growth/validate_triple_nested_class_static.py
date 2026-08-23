"""One-shot validation for three-level nested-namespace class-static forage."""

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
    "three submodule levels down so sdists whose API is "
    "package.subpackage.subpackage.submodule.Class.method rather than a "
    "two-level package.subpackage.submodule.Class.method can be foraged "
    "the same way."
)


def main() -> int:
    root = Path(".")
    assert leftover_marker_ids(LEFTOVER) == (
        "capability.application-python-triple-nested-static-growth-plane",
    )
    assert leftover_is_open(LEFTOVER, root) is False
    ledger = load_ledger(default_ledger_path(root))
    cap = ledger.capabilities["capability.application-python-triple-nested-static-growth-plane"]
    assert cap.last_proof_exit_code == 0
    adapter = (root / "capabilities/absorbed/docutils/acquisition_adapter.py").read_text(encoding="utf-8")
    assert "utils.math.math2html.Cloner.clone" in adapter
    manifest = json.loads(
        (root / "capabilities/absorbed/docutils/absorption.json").read_text(encoding="utf-8")
    )
    provides = manifest.get("provides")
    if isinstance(provides, list):
        assert "utils_math_math2html_cloner_clone_output" in provides
    else:
        assert provides == "utils_math_math2html_cloner_clone_output"
    proof = prove_absorbed_capability("docutils")
    assert proof.get("ok"), proof
    fetched = live_registry_archive(
        {"name": "docutils", "slug": "docutils", "registry": "pypi", "version": "0.23"}
    )
    assert fetched and fetched.get("ok"), fetched
    with tempfile.TemporaryDirectory(prefix="validate-docutils-") as tmp:
        inferred = infer_acquisition_spec(
            slug="docutils",
            name="docutils",
            source=Path(str(fetched["path"])),
            staging_root=Path(tmp),
            hint="docutils",
            close_deps=True,
        )
    assert inferred.get("ok"), inferred
    rec = inferred["record"]
    assert rec["winner"] == "utils.math.math2html.Cloner.clone"
    assert rec["python_triple_nested_namespace_class_static"] is True
    assert rec["python_deep_nested_namespace_class_static"] is False
    assert rec["python_nested_namespace_class_static"] is False
    assert rec["python_class_instance"] is False
    print("ok", rec["winner"], rec["provides"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
