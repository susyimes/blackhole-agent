from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent.capability_bundle import (
    BundleError,
    export_capability_bundle,
    import_capability_bundle,
    verify_capability_bundle,
)
from blackhole_agent.capability_service import invoke_capability, load_invocable_capabilities

_TOOL_PY = """\
import json
import sys

payload = json.loads(sys.stdin.read())
print(json.dumps({"reversed_text": payload["raw_text"][::-1]}))
"""

_MANIFEST = {
    "schema_version": 1,
    "slug": "text-reverser",
    "name": "Text Reverser (external fixture tool)",
    "version": "1.0.0",
    "origin": {"kind": "fixture", "source": "tests", "commit": ""},
    "command": ["python", "tool.py"],
    "requires": ["raw_text"],
    "provides": ["reversed_text"],
    "cases": [
        {"input": {"raw_text": "blackhole"}, "expect": {"reversed_text": "elohkcalb"}},
        {"input": {"raw_text": "unbound"}, "expect": {"reversed_text": "dnuobnu"}},
    ],
}


def _source_workspace(root: Path, *, proof_exit_code: int = 0) -> None:
    tool_root = root / "capabilities" / "absorbed" / "text-reverser"
    tool_root.mkdir(parents=True)
    (tool_root / "absorption.json").write_text(json.dumps(_MANIFEST, indent=2), encoding="utf-8")
    (tool_root / "tool.py").write_text(_TOOL_PY, encoding="utf-8")
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "capabilities": {
                    "capability.absorbed-text-reverser": {
                        "id": "capability.absorbed-text-reverser",
                        "name": "Absorbed external capability: Text Reverser",
                        "kind": "python",
                        "description": "Absorbed fixture tool.",
                        "last_proof_exit_code": proof_exit_code,
                        "last_proved_at": "2026-09-13T00:00:00Z",
                    }
                },
                "schema_version": 1,
                "updated_at": "2026-09-13T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def test_export_import_roundtrip_invocable(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _source_workspace(source)

    exported = export_capability_bundle(
        source, "capability.absorbed-text-reverser", tmp_path / "bundle.json"
    )
    assert exported["ok"] is True
    assert exported["file_count"] == 2

    summary = verify_capability_bundle(tmp_path / "bundle.json")
    assert summary["capability_id"] == "capability.absorbed-text-reverser"
    assert summary["bundle_digest"] == exported["bundle_digest"]

    imported = import_capability_bundle(tmp_path / "bundle.json", target)
    assert imported["ok"] is True
    invocable = load_invocable_capabilities(target)
    assert "capability.absorbed-text-reverser" in invocable

    outcome = invoke_capability(target, "capability.absorbed-text-reverser", {"raw_text": "portable"})
    assert outcome["output"] == {"reversed_text": "elbatrop"}


def test_export_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _source_workspace(source)
    first = export_capability_bundle(source, "capability.absorbed-text-reverser", tmp_path / "a.json")
    second = export_capability_bundle(source, "capability.absorbed-text-reverser", tmp_path / "b.json")
    assert first["bundle_digest"] == second["bundle_digest"]


def test_export_refuses_unproved_capability(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _source_workspace(source, proof_exit_code=1)
    with pytest.raises(BundleError, match="not proved"):
        export_capability_bundle(source, "capability.absorbed-text-reverser", tmp_path / "bundle.json")


def test_export_refuses_unknown_capability(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _source_workspace(source)
    with pytest.raises(BundleError, match="unknown capability"):
        export_capability_bundle(source, "capability.absorbed-missing", tmp_path / "bundle.json")


def test_import_refuses_tampered_bundle_without_writing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _source_workspace(source)
    export_capability_bundle(source, "capability.absorbed-text-reverser", tmp_path / "bundle.json")

    bundle = json.loads((tmp_path / "bundle.json").read_text(encoding="utf-8"))
    record = bundle["files"]["tool.py"]
    record["content_b64"] = ("A" if record["content_b64"][0] != "A" else "B") + record["content_b64"][1:]
    (tmp_path / "tampered.json").write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(BundleError) as caught:
        import_capability_bundle(tmp_path / "tampered.json", target)
    assert caught.value.verdict == "tampered"
    assert not (target / "capabilities").exists()


def test_import_refuses_duplicate_registration(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _source_workspace(source)
    export_capability_bundle(source, "capability.absorbed-text-reverser", tmp_path / "bundle.json")
    import_capability_bundle(tmp_path / "bundle.json", target)
    with pytest.raises(BundleError, match="already registers"):
        import_capability_bundle(tmp_path / "bundle.json", target)
    again = import_capability_bundle(tmp_path / "bundle.json", target, overwrite=True)
    assert again["ok"] is True


def test_import_refuses_traversal_paths(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _source_workspace(source)
    export_capability_bundle(source, "capability.absorbed-text-reverser", tmp_path / "bundle.json")

    bundle = json.loads((tmp_path / "bundle.json").read_text(encoding="utf-8"))
    payload = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    payload["files"]["../escape.py"] = payload["files"].pop("tool.py")
    # Re-seal so only the path safety check can refuse it.
    import hashlib

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload["bundle_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    (tmp_path / "traversal.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BundleError) as caught:
        import_capability_bundle(tmp_path / "traversal.json", target)
    assert caught.value.verdict == "unsafe_path"
    assert not (target.parent / "escape.py").exists()
