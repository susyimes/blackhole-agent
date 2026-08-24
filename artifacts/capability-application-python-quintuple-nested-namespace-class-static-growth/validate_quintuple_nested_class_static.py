"""One-shot validation for five-level nested-namespace class-static forage."""

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
    "five submodule levels down so sdists whose covering Class.method returns a "
    "cwd-independent JSON scalar, rather than an inherited path validator, can "
    "be foraged the same way."
)
CALLABLE = "create.via_global_ref.builtin.cpython.common.CPython.exe_stem"
PROVIDES = "create_via_global_ref_builtin_cpython_common_cpython_exe_stem_ou"


def main() -> int:
    root = Path(".")
    assert leftover_marker_ids(LEFTOVER) == (
        "capability.application-python-quint-nested-static-growth-plane",
    )
    assert leftover_is_open(LEFTOVER, root) is False
    ledger = load_ledger(default_ledger_path(root))
    cap = ledger.capabilities["capability.application-python-quint-nested-static-growth-plane"]
    assert cap.last_proof_exit_code == 0
    adapter = (root / "capabilities/absorbed/virtualenv/acquisition_adapter.py").read_text(encoding="utf-8")
    assert CALLABLE in adapter
    manifest = json.loads((root / "capabilities/absorbed/virtualenv/absorption.json").read_text(encoding="utf-8"))
    provides = manifest.get("provides")
    if isinstance(provides, list):
        assert PROVIDES in provides
    else:
        assert provides == PROVIDES
    assert list(manifest.get("requires") or []) == []
    proof = prove_absorbed_capability("virtualenv")
    assert proof.get("ok"), proof
    fetched = live_registry_archive(
        {"name": "virtualenv", "slug": "virtualenv", "registry": "pypi", "version": "21.7.4"}
    )
    assert fetched and fetched.get("ok"), fetched
    with tempfile.TemporaryDirectory(prefix="validate-virtualenv-") as tmp:
        inferred = infer_acquisition_spec(
            slug="virtualenv",
            name="virtualenv",
            source=Path(str(fetched["path"])),
            staging_root=Path(tmp),
            hint="virtualenv",
            runtime="python",
            close_deps=True,
        )
    assert inferred.get("ok"), inferred
    rec = inferred["record"]
    assert rec["winner"] == CALLABLE
    assert rec["python_quintuple_nested_namespace_class_static"] is True
    assert rec["python_quintuple_nested_namespace_class_instance"] is False
    assert rec["python_quadruple_nested_namespace_class_static"] is False
    assert rec["python_nested_namespace_class_static"] is False
    assert rec["python_class_static"] is False
    print("ok", rec["winner"], rec["provides"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
