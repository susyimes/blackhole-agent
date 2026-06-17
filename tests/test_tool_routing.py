from pathlib import Path

from blackhole_agent.tool_routing import (
    DENIED_TOOL_ROUTE,
    EXECUTABLE_TOOL_ROUTE,
    ProviderHarness,
    REVIEW_ONLY_TOOL_ROUTE,
    UNSUPPORTED_TOOL_ROUTE,
    ToolCompatibilityCache,
    ToolCallPolicyResult,
    ToolDescriptor,
    build_tool_routing_preflight,
    discover_provider_harnesses,
    executable_tool_registry,
    load_single_file_agent_tool_descriptors,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    route_tool_descriptors,
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


def test_local_memory_tool_route_is_executable_local_route():
    descriptor = local_memory_tool_descriptor(session_id="digest-1")

    decision = route_tool_descriptor(descriptor)
    registry = executable_tool_registry([descriptor])

    assert decision.route == EXECUTABLE_TOOL_ROUTE
    assert decision.executable is True
    assert decision.to_dict() == {
        "name": "local_memory",
        "provider": "local",
        "route": "executable",
        "reasons": [],
        "risk_flags": [],
        "type": None,
    }
    assert "local_memory" in registry
    assert registry["local_memory"]["provider"] == "local"


def test_review_only_risk_flags_keep_tool_out_of_executable_registry():
    descriptor = ToolDescriptor(
        name="security_probe_review",
        description="Review-only security-adjacent route metadata.",
        provider="local",
        risk_flags=("offensive-behavior",),
    )

    decision = route_tool_descriptor(descriptor)
    registry = executable_tool_registry([descriptor])

    assert decision.route == REVIEW_ONLY_TOOL_ROUTE
    assert decision.executable is False
    assert decision.reasons == ("review_only_risk:offensive-behavior",)
    assert decision.to_dict()["risk_flags"] == ["offensive-behavior"]
    assert registry == {}


def test_tool_call_policy_evaluator_allows_executable_descriptor():
    descriptor = ToolDescriptor(name="summarize", provider="local")

    decision = route_tool_descriptor(descriptor, tool_call_policy_evaluator=lambda _descriptor: True)
    registry = executable_tool_registry([descriptor], tool_call_policy_evaluator=lambda _descriptor: True)

    assert decision.route == EXECUTABLE_TOOL_ROUTE
    assert decision.executable is True
    assert registry["summarize"]["provider"] == "local"


def test_tool_call_policy_evaluator_denies_before_executable_registry():
    descriptor = ToolDescriptor(name="connector_tool", provider="local")

    decision = route_tool_descriptor(
        descriptor,
        tool_call_policy_evaluator=lambda _descriptor: ToolCallPolicyResult(False, "tenant_policy"),
    )
    registry = executable_tool_registry(
        [descriptor],
        tool_call_policy_evaluator=lambda _descriptor: ToolCallPolicyResult(False, "tenant_policy"),
    )

    assert decision.route == DENIED_TOOL_ROUTE
    assert decision.executable is False
    assert decision.reasons == ("policy_denied:tenant_policy",)
    assert registry == {}


def test_tool_call_policy_evaluator_can_request_review_before_registry():
    descriptor = ToolDescriptor(name="connector_tool", provider="local")

    decision = route_tool_descriptor(
        descriptor,
        tool_call_policy_evaluator=lambda _descriptor: ToolCallPolicyResult(True, "operator_ask", review_required=True),
    )
    registry = executable_tool_registry(
        [descriptor],
        tool_call_policy_evaluator=lambda _descriptor: ToolCallPolicyResult(
            True,
            "operator_ask",
            review_required=True,
        ),
    )

    assert decision.route == REVIEW_ONLY_TOOL_ROUTE
    assert decision.executable is False
    assert decision.reasons == ("policy_review_required:operator_ask",)
    assert registry == {}


def test_tool_call_policy_evaluator_denies_wrapped_tool_by_declared_policy_name():
    descriptor = ToolDescriptor(
        name="sys_session_send",
        description="Transport wrapper for inline agent dispatch.",
        provider="local",
        policy_name="worker",
        parameters={
            "type": "object",
            "properties": {"agent": {"type": "string"}},
            "required": ["agent"],
        },
    )
    observed_policy_names = []

    def policy(policy_descriptor):
        observed_policy_names.append(policy_descriptor.name)
        if policy_descriptor.name == "worker":
            return ToolCallPolicyResult(False, "sub_agent_denied")
        return True

    decision = route_tool_descriptor(descriptor, tool_call_policy_evaluator=policy)
    registry = executable_tool_registry([descriptor], tool_call_policy_evaluator=policy)

    assert observed_policy_names == ["worker", "worker"]
    assert decision.route == DENIED_TOOL_ROUTE
    assert decision.executable is False
    assert decision.reasons == ("policy_denied:sub_agent_denied",)
    assert decision.to_dict()["name"] == "sys_session_send"
    assert decision.to_dict()["policy_name"] == "worker"
    assert registry == {}


def test_wrapped_tool_policy_name_keeps_model_facing_transport_name():
    descriptor = ToolDescriptor(
        name="sys_session_send",
        description="Transport wrapper for inline agent dispatch.",
        provider="local",
        policy_name="worker",
    )

    decision = route_tool_descriptor(descriptor, tool_call_policy_evaluator=lambda policy_descriptor: True)
    registry = executable_tool_registry([descriptor], tool_call_policy_evaluator=lambda policy_descriptor: True)

    assert decision.route == EXECUTABLE_TOOL_ROUTE
    assert decision.to_dict() == {
        "name": "sys_session_send",
        "policy_name": "worker",
        "provider": "local",
        "route": "executable",
        "reasons": [],
        "risk_flags": [],
        "type": None,
    }
    assert registry["sys_session_send"]["name"] == "sys_session_send"
    assert registry["sys_session_send"]["policy_name"] == "worker"


def test_tool_call_policy_evaluator_errors_fail_closed():
    descriptor = ToolDescriptor(name="connector_tool", provider="local")

    def broken_policy(_descriptor):
        raise RuntimeError("policy backend unavailable")

    decision = route_tool_descriptor(descriptor, tool_call_policy_evaluator=broken_policy)
    registry = executable_tool_registry([descriptor], tool_call_policy_evaluator=broken_policy)

    assert decision.route == DENIED_TOOL_ROUTE
    assert decision.executable is False
    assert decision.reasons == ("policy_evaluation_error:RuntimeError",)
    assert registry == {}


def test_tool_call_policy_evaluator_connection_failures_fail_closed():
    descriptor = ToolDescriptor(name="connector_tool", provider="local")

    def unavailable_policy(_descriptor):
        raise ConnectionError("policy server unreachable")

    decision = route_tool_descriptor(descriptor, tool_call_policy_evaluator=unavailable_policy)
    registry = executable_tool_registry([descriptor], tool_call_policy_evaluator=unavailable_policy)

    assert decision.route == DENIED_TOOL_ROUTE
    assert decision.executable is False
    assert decision.reasons == ("policy_evaluation_error:ConnectionError",)
    assert registry == {}


def test_tool_call_policy_evaluator_timeouts_fail_closed():
    descriptor = ToolDescriptor(name="connector_tool", provider="local")

    def timeout_policy(_descriptor):
        raise TimeoutError("policy backend timed out")

    decision = route_tool_descriptor(descriptor, tool_call_policy_evaluator=timeout_policy)
    registry = executable_tool_registry([descriptor], tool_call_policy_evaluator=timeout_policy)

    assert decision.route == DENIED_TOOL_ROUTE
    assert decision.executable is False
    assert decision.reasons == ("policy_evaluation_timeout",)
    assert registry == {}


def test_tool_call_policy_evaluator_malformed_results_fail_closed():
    descriptor = ToolDescriptor(name="connector_tool", provider="local")

    decision = route_tool_descriptor(
        descriptor,
        tool_call_policy_evaluator=lambda _descriptor: {"allowed": True},
    )
    registry = executable_tool_registry(
        [descriptor],
        tool_call_policy_evaluator=lambda _descriptor: {"allowed": True},
    )

    assert decision.route == DENIED_TOOL_ROUTE
    assert decision.executable is False
    assert decision.reasons == ("policy_evaluation_malformed:dict",)
    assert registry == {}


def test_tool_call_policy_evaluator_malformed_allowed_field_fails_closed():
    descriptor = ToolDescriptor(name="connector_tool", provider="local")

    decision = route_tool_descriptor(
        descriptor,
        tool_call_policy_evaluator=lambda _descriptor: ToolCallPolicyResult("false", "malformed"),  # type: ignore[arg-type]
    )
    registry = executable_tool_registry(
        [descriptor],
        tool_call_policy_evaluator=lambda _descriptor: ToolCallPolicyResult("false", "malformed"),  # type: ignore[arg-type]
    )

    assert decision.route == DENIED_TOOL_ROUTE
    assert decision.executable is False
    assert decision.reasons == ("policy_evaluation_malformed:allowed",)
    assert registry == {}


def test_unsupported_provider_and_tool_type_are_inspectable_and_not_executable():
    descriptors = [
        ToolDescriptor(name="remote_browser", provider="mcp"),
        ToolDescriptor(name="stream_terminal", provider="local", tool_type="terminal"),
    ]

    decisions = route_tool_descriptors(descriptors)
    registry = executable_tool_registry(descriptors)

    assert [decision.route for decision in decisions] == [UNSUPPORTED_TOOL_ROUTE, UNSUPPORTED_TOOL_ROUTE]
    assert decisions[0].reasons == ("unsupported_provider:mcp",)
    assert decisions[1].reasons == ("unsupported_tool_type:terminal",)
    assert registry == {}


def test_tool_routing_preflight_reports_missing_required_tools_and_route_counts():
    descriptors = [
        local_memory_tool_descriptor(),
        ToolDescriptor(name="review_probe", provider="local", risk_flags=("privacy-leakage",)),
        ToolDescriptor(name="remote_browser", provider="mcp"),
    ]

    preflight = build_tool_routing_preflight(
        descriptors,
        required_tool_names=("local_memory", "browser", "browser"),
    )

    assert preflight["ok"] is False
    assert preflight["required_tool_names"] == ["local_memory", "browser"]
    assert preflight["missing_required_tool_names"] == ["browser"]
    assert preflight["executable_tool_names"] == ["local_memory"]
    assert preflight["route_counts"] == {
        EXECUTABLE_TOOL_ROUTE: 1,
        REVIEW_ONLY_TOOL_ROUTE: 1,
        UNSUPPORTED_TOOL_ROUTE: 1,
    }
    assert preflight["diagnostics"] == [
        "required tool is not executable or is unavailable: browser",
    ]


def test_tool_routing_preflight_counts_policy_denials_and_missing_required_tools():
    descriptors = [
        ToolDescriptor(name="allowed_local", provider="local"),
        ToolDescriptor(name="denied_local", provider="local"),
    ]

    def policy(descriptor):
        if descriptor.name == "denied_local":
            raise TimeoutError("policy backend timed out")
        return True

    preflight = build_tool_routing_preflight(
        descriptors,
        required_tool_names=("allowed_local", "denied_local"),
        tool_call_policy_evaluator=policy,
    )

    assert preflight["ok"] is False
    assert preflight["executable_tool_names"] == ["allowed_local"]
    assert preflight["missing_required_tool_names"] == ["denied_local"]
    assert preflight["route_counts"] == {
        DENIED_TOOL_ROUTE: 1,
        EXECUTABLE_TOOL_ROUTE: 1,
    }
    assert preflight["decisions"][1]["route"] == DENIED_TOOL_ROUTE
    assert preflight["decisions"][1]["reasons"] == ["policy_evaluation_timeout"]


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
