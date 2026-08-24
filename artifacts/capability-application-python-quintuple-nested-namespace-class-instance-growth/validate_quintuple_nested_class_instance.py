"""One-shot validation for five-level nested-namespace class-instance forage."""

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
    "five submodule levels down so sdists whose API is "
    "package.subpackage.subpackage.subpackage.subpackage.submodule.Class().method "
    "rather than a four-level nested Class.method static can be foraged the same way."
)
CALLABLE = "openid.connect.core.grant_types.authorization_code.AuthorizationCodeGrant.id_token_hash"
PROVIDES = "openid_connect_core_grant_types_authorization_code_authorization"


def main() -> int:
    root = Path(".")
    assert leftover_marker_ids(LEFTOVER) == (
        "capability.application-python-quint-nested-instance-growth-plane",
    )
    assert leftover_is_open(LEFTOVER, root) is False
    ledger = load_ledger(default_ledger_path(root))
    cap = ledger.capabilities["capability.application-python-quint-nested-instance-growth-plane"]
    assert cap.last_proof_exit_code == 0
    adapter = (root / "capabilities/absorbed/oauthlib/acquisition_adapter.py").read_text(encoding="utf-8")
    assert CALLABLE in adapter
    manifest = json.loads((root / "capabilities/absorbed/oauthlib/absorption.json").read_text(encoding="utf-8"))
    provides = manifest.get("provides")
    if isinstance(provides, list):
        assert PROVIDES in provides
    else:
        assert provides == PROVIDES
    proof = prove_absorbed_capability("oauthlib")
    assert proof.get("ok"), proof
    fetched = live_registry_archive(
        {"name": "oauthlib", "slug": "oauthlib", "registry": "pypi", "version": "3.3.1"}
    )
    assert fetched and fetched.get("ok"), fetched
    with tempfile.TemporaryDirectory(prefix="validate-oauthlib-") as tmp:
        inferred = infer_acquisition_spec(
            slug="oauthlib",
            name="oauthlib",
            source=Path(str(fetched["path"])),
            staging_root=Path(tmp),
            hint="oauthlib",
            runtime="python",
            close_deps=True,
        )
    assert inferred.get("ok"), inferred
    rec = inferred["record"]
    assert rec["winner"] == CALLABLE
    assert rec["python_quintuple_nested_namespace_class_instance"] is True
    assert rec["python_quintuple_nested_namespace_class_static"] is False
    assert rec["python_quadruple_nested_namespace_class_static"] is False
    assert rec["python_nested_namespace_class_instance"] is False
    assert rec["python_class_instance"] is False
    print("ok", rec["winner"], rec["provides"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
