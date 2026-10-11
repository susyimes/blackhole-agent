"""Unit checks for fail-closed invocation artifact paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from blackhole_agent.invocation_artifacts import (
    ArtifactError,
    list_invocation_artifacts,
    prepare_artifact_dir,
    read_invocation_artifact,
    serve_invocation_artifact,
)


def test_read_rejects_parent_escape(tmp_path: Path) -> None:
    ident = "abc123def456"
    dest = prepare_artifact_dir(tmp_path, ident)
    (dest / "report.txt").write_text("ok", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(ArtifactError) as caught:
        read_invocation_artifact(tmp_path, ident, "../secret.txt")
    assert caught.value.status == 400


def test_unknown_invocation_is_404(tmp_path: Path) -> None:
    with pytest.raises(ArtifactError) as caught:
        list_invocation_artifacts(tmp_path, "missing-id")
    assert caught.value.status == 404


def test_serve_lists_and_reads(tmp_path: Path) -> None:
    ident = "feedfacecafe"
    dest = prepare_artifact_dir(tmp_path, ident)
    (dest / "report.txt").write_bytes(b"hello")
    status, content_type, body, _headers = serve_invocation_artifact(tmp_path, ident, "")
    assert status == 200
    assert content_type == "application/json"
    assert b"report.txt" in body
    status, content_type, body, headers = serve_invocation_artifact(
        tmp_path, ident, "report.txt"
    )
    assert status == 200
    assert body == b"hello"
    assert "attachment" in headers.get("Content-Disposition", "")
