from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent.capability_bundle import export_capability_bundle
from blackhole_agent.capability_service import (
    InvocationError,
    import_bundle_http_request,
    invoke_capability,
    resolve_bundle_import,
)

_TOOL_PY = """\
import json
import sys

payload = json.loads(sys.stdin.read())
print(json.dumps({"shout_output": payload["text"].upper() + "!"}))
"""

_MANIFEST = {
    "schema_version": 1,
    "slug": "bundle-shout",
    "name": "Bundle shout",
    "version": "1.0.0",
    "command": ["python", "tool.py"],
    "requires": ["text"],
    "provides": ["shout_output"],
    "cases": [
        {"input": {"text": "hi"}, "expect": {"shout_output": "HI!"}},
        {"input": {"text": "ok"}, "expect": {"shout_output": "OK!"}},
    ],
}


def _source_workspace(root: Path) -> None:
    tool_root = root / "capabilities" / "absorbed" / "bundle-shout"
    tool_root.mkdir(parents=True)
    (tool_root / "absorption.json").write_text(json.dumps(_MANIFEST, indent=2), encoding="utf-8")
    (tool_root / "tool.py").write_text(_TOOL_PY, encoding="utf-8")
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "capabilities": {
                    "capability.absorbed-bundle-shout": {
                        "id": "capability.absorbed-bundle-shout",
                        "name": "Bundle shout",
                        "kind": "python",
                        "description": "Fixture shout tool.",
                        "last_proof_exit_code": 0,
                        "last_proved_at": "2026-09-13T00:00:00Z",
                    }
                },
                "schema_version": 1,
                "updated_at": "2026-09-13T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def test_resolve_bundle_import_flag_and_env() -> None:
    assert resolve_bundle_import(False, env={}) is False
    assert resolve_bundle_import(True, env={}) is True
    assert resolve_bundle_import(False, env={"BLACKHOLE_BUNDLE_IMPORT": "1"}) is True
    assert resolve_bundle_import(False, env={"BLACKHOLE_BUNDLE_IMPORT": "no"}) is False


def test_http_helper_refuses_when_disabled(tmp_path: Path) -> None:
    with pytest.raises(InvocationError) as exc:
        import_bundle_http_request(tmp_path, {"kind": "capability-bundle"}, enabled=False)
    assert exc.value.status == 400
    assert exc.value.error == "bundle_disabled"


def test_http_helper_imports_and_invokes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _source_workspace(source)
    export_capability_bundle(source, "capability.absorbed-bundle-shout", tmp_path / "bundle.json")
    bundle = json.loads((tmp_path / "bundle.json").read_text(encoding="utf-8"))

    outcome = import_bundle_http_request(target, bundle, enabled=True)
    assert outcome["ok"] is True
    assert outcome["imported"] is True
    assert outcome["capability_id"] == "capability.absorbed-bundle-shout"

    invoked = invoke_capability(
        target, "capability.absorbed-bundle-shout", {"text": "blackhole unbound"}
    )
    assert invoked["output"] == {"shout_output": "BLACKHOLE UNBOUND!"}


def test_http_helper_refuses_tampered_payload(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _source_workspace(source)
    export_capability_bundle(source, "capability.absorbed-bundle-shout", tmp_path / "bundle.json")
    bundle = json.loads((tmp_path / "bundle.json").read_text(encoding="utf-8"))
    record = bundle["files"]["tool.py"]
    record["content_b64"] = ("A" if record["content_b64"][0] != "A" else "B") + record["content_b64"][1:]

    with pytest.raises(InvocationError) as exc:
        import_bundle_http_request(target, bundle, enabled=True)
    assert exc.value.status == 400
    assert exc.value.error == "tampered"
    assert not (target / "capabilities" / "absorbed" / "bundle-shout").exists()
