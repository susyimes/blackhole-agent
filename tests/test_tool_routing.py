from pathlib import Path

from blackhole_agent.tool_routing import (
    ToolCompatibilityCache,
    ToolDescriptor,
    executable_tool_registry,
    load_single_file_agent_tool_descriptors,
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
