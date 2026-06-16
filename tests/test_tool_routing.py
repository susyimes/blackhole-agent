from pathlib import Path

from blackhole_agent.tool_routing import (
    ProviderHarness,
    ToolCompatibilityCache,
    ToolDescriptor,
    discover_provider_harnesses,
    executable_tool_registry,
    load_single_file_agent_tool_descriptors,
    select_provider_harness,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_tool_cache_distinguishes_same_name_with_different_parameter_schema():
    cache = ToolCompatibilityCache()
    search_by_query = ToolDescriptor(
        name="search",
        description="Search public evidence.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    search_by_url = ToolDescriptor(
        name="search",
        description="Search public evidence.",
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"],
        },
    )

    query_key = cache.set(search_by_query, "query-runner")
    url_key = cache.set(search_by_url, "url-runner")

    assert query_key != url_key
    assert len(cache) == 2
    assert cache.get(search_by_query) == "query-runner"
    assert cache.get(search_by_url) == "url-runner"


def test_tool_cache_distinguishes_same_named_tools_by_provider_and_session_context():
    cache = ToolCompatibilityCache()
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    local_read = ToolDescriptor(name="read_file", parameters=parameters, provider="local", session_id="session-a")
    remote_read = ToolDescriptor(name="read_file", parameters=parameters, provider="mcp", session_id="session-a")
    next_session_read = ToolDescriptor(name="read_file", parameters=parameters, provider="local", session_id="session-b")

    cache.set(local_read, "local-session-a")
    cache.set(remote_read, "mcp-session-a")
    cache.set(next_session_read, "local-session-b")

    assert len(cache) == 3
    assert cache.get(local_read) == "local-session-a"
    assert cache.get(remote_read) == "mcp-session-a"
    assert cache.get(next_session_read) == "local-session-b"


def test_tool_call_metadata_retains_json_schema_parameters():
    parameters = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1},
            "topic": {"type": "string"},
        },
        "required": ["topic"],
        "additionalProperties": False,
    }
    descriptor = ToolDescriptor(
        name="summarize",
        description="Summarize evidence.",
        parameters=parameters,
        provider="local",
        session_id="run-1",
    )

    metadata = descriptor.to_call_metadata()

    assert metadata["name"] == "summarize"
    assert metadata["parameters"] == parameters
    assert metadata["parameters"]["properties"]["limit"]["minimum"] == 1
    assert metadata["session_id"] == "run-1"


def test_single_file_yaml_function_tool_reaches_executable_registry():
    descriptors = load_single_file_agent_tool_descriptors(
        FIXTURE_DIR / "single_file_function_agent.yaml",
        session_id="digest-378",
    )

    assert len(descriptors) == 1
    descriptor = descriptors[0]
    assert descriptor.name == "hindsight_retain"
    assert descriptor.provider == "function"
    assert descriptor.tool_type == "function"
    assert descriptor.callable_path == "hindsight_omnigent.tools.retain"
    assert descriptor.parameters == {
        "type": "object",
        "properties": {"content": {"type": "string"}},
        "required": ["content"],
        "additionalProperties": False,
    }

    registry = executable_tool_registry(descriptors)

    assert registry == {
        "hindsight_retain": {
            "name": "hindsight_retain",
            "description": "Store information in long-term memory.",
            "provider": "function",
            "session_id": "digest-378",
            "type": "function",
            "callable": "hindsight_omnigent.tools.retain",
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
                "additionalProperties": False,
            },
        }
    }


def test_provider_harness_selection_uses_deterministic_fallback_order():
    harnesses = [
        ProviderHarness(name="cursor-sdk", provider="cursor", priority=30, optional_extra_modules=("cursor_agent",)),
        ProviderHarness(name="function-agent", provider="function", priority=90),
        ProviderHarness(name="copilot-sdk", provider="copilot", priority=20, optional_extra_modules=("github_copilot",)),
    ]

    selection = select_provider_harness(
        harnesses,
        installed_modules={"cursor_agent", "github_copilot"},
        available_commands=set(),
        environ={},
        platform="linux",
    )

    assert selection.selected.name == "copilot-sdk"
    assert [status.harness.name for status in selection.statuses] == [
        "copilot-sdk",
        "cursor-sdk",
        "function-agent",
    ]


def test_provider_harness_skips_missing_optional_extra_with_clear_reason():
    harnesses = [
        ProviderHarness(name="cursor-sdk", provider="cursor", priority=10, optional_extra_modules=("cursor_agent",)),
        ProviderHarness(name="function-agent", provider="function", priority=20),
    ]

    selection = select_provider_harness(
        harnesses,
        installed_modules=set(),
        available_commands=set(),
        environ={},
        platform="linux",
    )

    assert selection.selected.name == "function-agent"
    assert selection.statuses[0].available is False
    assert selection.statuses[0].skip_reasons == ("missing_optional_extra:cursor_agent",)


def test_provider_harness_discovery_reports_disabled_runner_missing_dependency_env_and_platform():
    harness = ProviderHarness(
        name="copilot-sdk",
        provider="copilot",
        priority=10,
        enabled=False,
        required_modules=("copilot_core",),
        required_commands=("node",),
        required_env=("COPILOT_TOKEN",),
        supported_platforms=("darwin",),
    )

    (status,) = discover_provider_harnesses(
        [harness],
        installed_modules=set(),
        available_commands=set(),
        environ={},
        platform="linux",
    )

    assert status.available is False
    assert status.skip_reasons == (
        "disabled_runner",
        "unsupported_platform:linux",
        "missing_dependency:copilot_core",
        "missing_dependency:node",
        "missing_env:COPILOT_TOKEN",
    )


def test_provider_harness_selection_exports_body_free_diagnostics_without_env_values():
    selection = select_provider_harness(
        [
            ProviderHarness(
                name="private-provider",
                provider="private",
                priority=10,
                required_env=("PRIVATE_PROVIDER_TOKEN",),
            )
        ],
        installed_modules=set(),
        available_commands=set(),
        environ={"PRIVATE_PROVIDER_TOKEN": "secret-token-value"},
        platform="linux",
    )

    payload = selection.to_dict()

    assert payload["selected"] == "private-provider"
    assert "secret-token-value" not in str(payload)
    assert payload["statuses"] == [
        {
            "available": True,
            "name": "private-provider",
            "priority": 10,
            "provider": "private",
            "skip_reasons": [],
        }
    ]
