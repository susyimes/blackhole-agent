"""One-shot validation for two-level nested-namespace class-instance forage."""

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
    "Optional later work is reflecting Python nested-namespace class instance methods "
    "two submodule levels down so sdists whose API is "
    "package.subpackage.submodule.Class(opts).method rather than "
    "package.submodule.Class(opts).method can be foraged the same way."
)


def main() -> int:
    root = Path(".")
    assert leftover_marker_ids(LEFTOVER) == (
        "capability.application-python-deep-nested-instance-growth-plane",
    )
    assert leftover_is_open(LEFTOVER, root) is False
    ledger = load_ledger(default_ledger_path(root))
    cap = ledger.capabilities["capability.application-python-deep-nested-instance-growth-plane"]
    assert cap.last_proof_exit_code == 0
    adapter = (root / "capabilities/absorbed/html5lib/acquisition_adapter.py").read_text(
        encoding="utf-8"
    )
    assert "filters.sanitizer.Filter.allowed_token" in adapter
    manifest = json.loads(
        (root / "capabilities/absorbed/html5lib/absorption.json").read_text(encoding="utf-8")
    )
    provides = manifest.get("provides")
    if isinstance(provides, list):
        assert "filters_sanitizer_filter_allowed_token_output" in provides
    else:
        assert provides == "filters_sanitizer_filter_allowed_token_output"
    proof = prove_absorbed_capability("html5lib")
    assert proof.get("ok"), proof
    fetched = live_registry_archive(
        {"name": "html5lib", "slug": "html5lib", "registry": "pypi", "version": "1.1"}
    )
    assert fetched and fetched.get("ok"), fetched
    with tempfile.TemporaryDirectory(prefix="validate-html5lib-") as tmp:
        inferred = infer_acquisition_spec(
            slug="html5lib",
            name="html5lib",
            source=Path(str(fetched["path"])),
            staging_root=Path(tmp),
            hint="html5lib",
            close_deps=True,
        )
    assert inferred.get("ok"), inferred
    rec = inferred["record"]
    assert rec["winner"] == "filters.sanitizer.Filter.allowed_token"
    assert rec["python_deep_nested_namespace_class_instance"] is True
    assert rec["python_nested_namespace_class_instance"] is False
    print("ok", rec["winner"], rec["provides"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
