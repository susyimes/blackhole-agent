import json

import pytest

from blackhole_agent.local_memory import LocalMemoryStore, MemoryPrivacyError
from blackhole_agent.tool_routing import ToolCompatibilityCache, local_memory_tool_descriptor


def test_local_memory_write_read_list_and_delete(tmp_path):
    store = LocalMemoryStore(tmp_path / "memory", namespace="run-a")

    written = store.execute(
        "write",
        key="proposal.memory.local",
        value="Prefer local JSON memory with explicit privacy guards.",
        tags=["proposal", "memory"],
    )
    read = store.execute("read", key="proposal.memory.local")
    listed = store.execute("list", tag="memory")
    deleted = store.execute("delete", key="proposal.memory.local")
    missing = store.execute("read", key="proposal.memory.local")

    assert written["status"] == "written"
    assert read["entry"]["value"] == "Prefer local JSON memory with explicit privacy guards."
    assert [entry["key"] for entry in listed["entries"]] == ["proposal.memory.local"]
    assert deleted == {"deleted": True, "status": "deleted"}
    assert missing == {"entry": None, "status": "missing"}


@pytest.mark.parametrize(
    "value",
    [
        "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz",
        "token: ghp_abcdefghijklmnopqrstuvwxyz123456",
        "-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----",
        "Contact person@example.com for the private account.",
        "SSN 123-45-6789",
    ],
)
def test_local_memory_rejects_secret_or_private_payloads_without_persisting(tmp_path, value):
    store = LocalMemoryStore(tmp_path / "memory", namespace="run-a")

    with pytest.raises(MemoryPrivacyError) as error:
        store.write("unsafe.memory", value)

    assert "memory write rejected by privacy guard" in str(error.value)
    assert value not in str(error.value)
    assert store.read("unsafe.memory") is None
    if store.path.exists():
        assert value not in store.path.read_text(encoding="utf-8")


def test_local_memory_namespaces_are_isolated_under_storage_root(tmp_path):
    root = tmp_path / "memory"
    run_a = LocalMemoryStore(root, namespace="digest-a")
    run_b = LocalMemoryStore(root, namespace="digest-b")

    run_a.write("lesson", "Namespace A stores its own lesson.")
    run_b.write("lesson", "Namespace B stores a different lesson.")

    assert run_a.path != run_b.path
    assert run_a.read("lesson").value == "Namespace A stores its own lesson."
    assert run_b.read("lesson").value == "Namespace B stores a different lesson."
    assert json.loads(run_a.path.read_text(encoding="utf-8"))["namespace"] == "digest-a"

    with pytest.raises(ValueError, match="memory namespace"):
        LocalMemoryStore(root, namespace="../outside")


def test_local_memory_descriptor_routes_with_full_schema_and_session_context():
    descriptor = local_memory_tool_descriptor(session_id="digest-1")
    cache = ToolCompatibilityCache()

    key = cache.set(descriptor, "local-memory-route")

    assert descriptor.name == "local_memory"
    assert descriptor.provider == "local"
    assert descriptor.parameters["properties"]["action"]["enum"] == ["write", "read", "list", "delete"]
    assert cache.get(descriptor) == "local-memory-route"
    assert key == descriptor.compatibility_key()
