"""Unit checks for fail-closed inbound webhook configuration and HMAC."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent.invocation_webhooks import (
    WebhookConfigError,
    WebhookError,
    WebhookPlane,
    parse_hooks_path,
    parse_webhook_hook_clause,
    resolve_webhook_config,
    sign_webhook_body,
)


def test_parse_hooks_path_rejects_nested_and_root() -> None:
    assert parse_hooks_path("/hooks/shout") == "shout"
    assert parse_hooks_path("/hooks/") == ""
    assert parse_hooks_path("/hooks") == ""
    assert parse_hooks_path("/hooks/shout/extra") is None
    assert parse_hooks_path("/invoke") is None


def test_parse_clause_and_resolve_config() -> None:
    name, cap = parse_webhook_hook_clause("shout=capability.absorbed-webhook-shout")
    assert name == "shout"
    assert cap == "capability.absorbed-webhook-shout"
    config = resolve_webhook_config(
        "webhook-secret",
        ["shout=capability.absorbed-webhook-shout"],
        env={},
    )
    assert config.enabled is True
    assert config.capability_id("shout") == "capability.absorbed-webhook-shout"
    assert config.health() == {"webhook_hooks": True, "webhook_hook_count": 1}


def test_resolve_config_fail_closed_without_pair() -> None:
    assert resolve_webhook_config(None, None, env={}).enabled is False
    with pytest.raises(WebhookConfigError):
        resolve_webhook_config("webhook-secret", None, env={})
    with pytest.raises(WebhookConfigError):
        resolve_webhook_config(None, ["shout=capability.absorbed-webhook-shout"], env={})


def test_disabled_plane_is_404(tmp_path: Path) -> None:
    plane = WebhookPlane(tmp_path, resolve_webhook_config(env={}))
    with pytest.raises(WebhookError) as caught:
        plane.accept_post("shout", b'{"input":{}}', "sha256=dead")
    assert caught.value.status == 404
    assert caught.value.error == "webhook_disabled"


def test_wrong_signature_never_persists(tmp_path: Path) -> None:
    config = resolve_webhook_config(
        "webhook-secret",
        ["shout=capability.absorbed-webhook-shout"],
        env={},
    )
    plane = WebhookPlane(tmp_path, config, invoke=lambda *args, **kwargs: {"ok": True})
    body = json.dumps({"input": {"text": "hi"}}).encode("utf-8")
    with pytest.raises(WebhookError) as caught:
        plane.accept_post("shout", body, "sha256=00")
    assert caught.value.status == 401
    assert caught.value.error == "webhook_signature_invalid"
    runs = tmp_path / ".blackhole-agent" / "webhook-runs"
    assert not runs.exists() or list(runs.glob("*.json")) == []


def test_valid_signature_accepts_and_completes(tmp_path: Path) -> None:
    config = resolve_webhook_config(
        "webhook-secret",
        ["shout=capability.absorbed-webhook-shout"],
        env={},
    )

    def invoke(root, capability_id, provided_input, *, cancel_event=None):
        assert capability_id == "capability.absorbed-webhook-shout"
        assert provided_input == {"text": "hi"}
        return {
            "ok": True,
            "capability_id": capability_id,
            "output": {"shout_output": "HI!"},
            "invocation_id": "inv-1",
            "artifacts": [],
        }

    plane = WebhookPlane(tmp_path, config, invoke=invoke)
    body = json.dumps({"input": {"text": "hi"}}).encode("utf-8")
    accepted = plane.accept_post("shout", body, sign_webhook_body("webhook-secret", body))
    assert accepted["status"] == "accepted"
    run_id = accepted["run_id"]
    import time

    deadline = time.time() + 2
    record = plane.get_run(run_id)
    while record["status"] in {"accepted", "running"} and time.time() < deadline:
        time.sleep(0.02)
        record = plane.get_run(run_id)
    assert record["status"] == "completed"
    assert record["output"] == {"shout_output": "HI!"}
    assert record["invocation_id"] == "inv-1"
