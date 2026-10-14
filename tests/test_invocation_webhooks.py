"""Unit checks for fail-closed inbound webhook configuration and HMAC."""

from __future__ import annotations

import hashlib
import json
import time
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


def _config():
    return resolve_webhook_config(
        "webhook-secret",
        ["shout=capability.absorbed-webhook-shout"],
        env={},
    )


def _body(text: str) -> bytes:
    return json.dumps({"input": {"text": text}}, separators=(",", ":")).encode("utf-8")


def _invoke_ok(root, capability_id, provided_input, *, cancel_event=None):
    return {
        "ok": True,
        "capability_id": capability_id,
        "output": {"echo_output": provided_input.get("text")},
        "invocation_id": "inv-1",
        "artifacts": [],
    }


def _wait_completed(plane: WebhookPlane, run_id: str) -> dict:
    deadline = time.time() + 2
    record = plane.get_run(run_id)
    while record["status"] in {"accepted", "running"} and time.time() < deadline:
        time.sleep(0.02)
        record = plane.get_run(run_id)
    return record


def test_identical_body_is_refused_across_process_restart(tmp_path: Path) -> None:
    calls: list[dict] = []

    def invoke(root, capability_id, provided_input, *, cancel_event=None):
        calls.append(dict(provided_input))
        return _invoke_ok(root, capability_id, provided_input, cancel_event=cancel_event)

    config = _config()
    plane = WebhookPlane(tmp_path, config, invoke=invoke)
    assert plane.health()["webhook_replay_guard"] is True
    body = _body("once")
    signature = sign_webhook_body("webhook-secret", body)
    accepted = plane.accept_post("shout", body, signature)
    assert _wait_completed(plane, accepted["run_id"])["status"] == "completed"
    with pytest.raises(WebhookError) as replayed:
        plane.accept_post("shout", body, signature)
    assert replayed.value.status == 409
    assert replayed.value.error == "webhook_replayed"
    restarted = WebhookPlane(tmp_path, config, invoke=invoke)
    with pytest.raises(WebhookError) as persisted:
        restarted.accept_post("shout", body, signature)
    assert persisted.value.status == 409
    fresh = _body("twice")
    second = restarted.accept_post("shout", fresh, sign_webhook_body("webhook-secret", fresh))
    assert second["run_id"] != accepted["run_id"]
    assert _wait_completed(restarted, second["run_id"])["output"] == {"echo_output": "twice"}
    assert calls == [{"text": "once"}, {"text": "twice"}]


def test_failed_signature_and_unknown_hook_do_not_burn_the_body(tmp_path: Path) -> None:
    config = _config()
    plane = WebhookPlane(tmp_path, config, invoke=_invoke_ok)
    body = _body("later")
    signature = sign_webhook_body("webhook-secret", body)
    with pytest.raises(WebhookError) as wrong:
        plane.accept_post("shout", body, "sha256=00")
    assert wrong.value.status == 401
    with pytest.raises(WebhookError) as unknown:
        plane.accept_post("other", body, signature)
    assert unknown.value.status == 404
    invalid = b"not-json"
    with pytest.raises(WebhookError) as malformed:
        plane.accept_post("shout", invalid, sign_webhook_body("webhook-secret", invalid))
    assert malformed.value.status == 400
    accepted = plane.accept_post("shout", body, signature)
    assert accepted["status"] == "accepted"
    store = json.loads((tmp_path / ".blackhole-agent" / "webhook-deliveries.json").read_text(encoding="utf-8"))
    fingerprints = store["fingerprints"]
    assert hashlib.sha256(body).hexdigest() in fingerprints
    assert hashlib.sha256(invalid).hexdigest() not in fingerprints


def test_oldest_fingerprint_is_evicted(tmp_path: Path) -> None:
    config = _config()
    plane = WebhookPlane(tmp_path, config, invoke=_invoke_ok, delivery_limit=2)
    bodies = [_body(text) for text in ("a", "b", "c")]
    signatures = [sign_webhook_body("webhook-secret", body) for body in bodies]
    for body, signature in zip(bodies, signatures, strict=True):
        assert plane.accept_post("shout", body, signature)["status"] == "accepted"
    again = plane.accept_post("shout", bodies[0], signatures[0])
    assert again["status"] == "accepted"
    with pytest.raises(WebhookError) as still_held:
        plane.accept_post("shout", bodies[2], signatures[2])
    assert still_held.value.status == 409
    assert still_held.value.error == "webhook_replayed"


def test_disabled_plane_reports_replay_guard_off(tmp_path: Path) -> None:
    plane = WebhookPlane(tmp_path, resolve_webhook_config(env={}))
    assert plane.health()["webhook_replay_guard"] is False
