"""Bind a gate-passing successor when the compounding catalog is exhausted.

``bind_gate_passing_successor`` walks the compounding ``SUCCESSOR_CATALOG``.
After program weave is proved, the compounding catalog is exhausted. On live
history that weave is a repetition-gate near-duplicate of fabric/lattice/tower,
so bind returns empty unless forage-shaped history still accepts it. Recovered
kernels and first-class genesis then invent until ``genesis_selection_blocked``.

This module closes that hole:

- detect when the compounding catalog has no remaining gate-passing successor
- rank a diversity catalog of unsaturated capability families
- bind the first open, gate-passing diversity mission
- skip a proved diversity item to the next gate-passing family
- preserve operator fields and unscoped remaining campaign work
"""

from __future__ import annotations

# Compatibility exports used by existing capability proofs. Keep them explicit
# while the selector's own proof now checks outcomes rather than catalog names.
from blackhole_agent.kernel_genesis_bind import (
    KERNEL_GENESIS_BIND_GOAL as KERNEL_GENESIS_BIND_GOAL,
    PROGRAM_WEAVE_GOAL as PROGRAM_WEAVE_GOAL,
    PROGRAM_WEAVE_ID as PROGRAM_WEAVE_ID,
    _State as _State,
    _unscoped_remaining_campaign as _unscoped_remaining_campaign,
    _write_forage_history as _write_forage_history,
    bind_gate_passing_successor as bind_gate_passing_successor,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids as leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST as LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import bind_local_mission as bind_local_mission
from blackhole_agent.mission_selection import semantic_similarity as semantic_similarity

import tempfile
from pathlib import Path
from typing import Any, Sequence

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_genesis_bind import (
    COMPOUND_LOOP_ID,
    COMPOSED_PROGRAM_ID,
    CONSUMED_GROWTH_ID,
    KERNEL_GENESIS_BIND_ID,
    PRIMITIVE_COMPOSE_ID,
    PROGRAM_FABRIC_GOAL,
    PROGRAM_FABRIC_ID,
    PROGRAM_LATTICE_GOAL,
    PROGRAM_LATTICE_ID,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_GOAL,
    PROGRAM_TOWER_ID,
    _catalog_item_open,
    _consumed_campaign,
    _register_proved,
    _write_complete_mission,
    genesis_bind_is_needed,
)
from blackhole_agent.kernel_half_open_persist import (
    HALF_OPEN_PERSIST_DONE_WHEN,
    HALF_OPEN_PERSIST_GOAL,
    HALF_OPEN_PERSIST_ID,
)
from blackhole_agent.kernel_mission_memory import (
    MISSION_MEMORY_DONE_WHEN,
    MISSION_MEMORY_GOAL,
    MISSION_MEMORY_ID,
)
from blackhole_agent.mcp_call_isolation import (
    MCP_CALL_DONE_WHEN,
    MCP_CALL_GOAL,
    MCP_CALL_ID,
)
from blackhole_agent.mcp_reverse_channel import (
    MCP_REVERSE_DONE_WHEN,
    MCP_REVERSE_GOAL,
    MCP_REVERSE_ID,
)
from blackhole_agent.mcp_http_transport import (
    MCP_HTTP_DONE_WHEN,
    MCP_HTTP_GOAL,
    MCP_HTTP_ID,
)
from blackhole_agent.mcp_http_event_stream import (
    MCP_HTTP_EVENT_DONE_WHEN,
    MCP_HTTP_EVENT_GOAL,
    MCP_HTTP_EVENT_ID,
)
from blackhole_agent.mcp_handshake_isolation import (
    MCP_HANDSHAKE_DONE_WHEN,
    MCP_HANDSHAKE_GOAL,
    MCP_HANDSHAKE_ID,
)
from blackhole_agent.publication_resilience import (
    PUBLICATION_RESILIENCE_DONE_WHEN,
    PUBLICATION_RESILIENCE_GOAL,
    PUBLICATION_RESILIENCE_ID,
)
from blackhole_agent.browser_actuation import (
    BROWSER_ACTUATION_DONE_WHEN,
    BROWSER_ACTUATION_GOAL,
    BROWSER_ACTUATION_ID,
)
from blackhole_agent.gmail_actuation import (
    GMAIL_ACTUATION_DONE_WHEN,
    GMAIL_ACTUATION_GOAL,
    GMAIL_ACTUATION_ID,
)
from blackhole_agent.godot_actuation import (
    GODOT_ACTUATION_DONE_WHEN,
    GODOT_ACTUATION_GOAL,
    GODOT_ACTUATION_ID,
)
from blackhole_agent.mcp_plugin_reconnect import (
    MCP_RECONNECT_DONE_WHEN,
    MCP_RECONNECT_GOAL,
    MCP_RECONNECT_ID,
)
from blackhole_agent.kernel_half_open_probe import (
    HALF_OPEN_PROBE_DONE_WHEN,
    HALF_OPEN_PROBE_GOAL,
    HALF_OPEN_PROBE_ID,
)
from blackhole_agent.mcp_sampling import (
    MCP_SAMPLING_DONE_WHEN,
    MCP_SAMPLING_GOAL,
    MCP_SAMPLING_ID,
)
from blackhole_agent.mcp_resources import (
    MCP_RESOURCES_DONE_WHEN,
    MCP_RESOURCES_GOAL,
    MCP_RESOURCES_ID,
)
from blackhole_agent.mcp_prompts import (
    MCP_PROMPTS_DONE_WHEN,
    MCP_PROMPTS_GOAL,
    MCP_PROMPTS_ID,
)
from blackhole_agent.mcp_completions import (
    MCP_COMPLETIONS_DONE_WHEN,
    MCP_COMPLETIONS_GOAL,
    MCP_COMPLETIONS_ID,
)
from blackhole_agent.mcp_logging import (
    MCP_LOGGING_DONE_WHEN,
    MCP_LOGGING_GOAL,
    MCP_LOGGING_ID,
)
from blackhole_agent.mcp_elicitation import (
    MCP_ELICITATION_DONE_WHEN,
    MCP_ELICITATION_GOAL,
    MCP_ELICITATION_ID,
)
from blackhole_agent.mcp_cancellation import (
    MCP_CANCELLATION_DONE_WHEN,
    MCP_CANCELLATION_GOAL,
    MCP_CANCELLATION_ID,
)
from blackhole_agent.mcp_resource_subscribe import (
    MCP_SUBSCRIBE_DONE_WHEN,
    MCP_SUBSCRIBE_GOAL,
    MCP_SUBSCRIBE_ID,
)
from blackhole_agent.mcp_roots_list_changed import (
    MCP_ROOTS_CHANGED_DONE_WHEN,
    MCP_ROOTS_CHANGED_GOAL,
    MCP_ROOTS_CHANGED_ID,
)
from blackhole_agent.browser_cdp_actuation import (
    BROWSER_CDP_DONE_WHEN,
    BROWSER_CDP_GOAL,
    BROWSER_CDP_ID,
)
from blackhole_agent.github_actuation import (
    GITHUB_ACTUATION_DONE_WHEN,
    GITHUB_ACTUATION_GOAL,
    GITHUB_ACTUATION_ID,
)
from blackhole_agent.sqlite_actuation import (
    SQLITE_ACTUATION_DONE_WHEN,
    SQLITE_ACTUATION_GOAL,
    SQLITE_ACTUATION_ID,
)
from blackhole_agent.webhook_actuation import (
    WEBHOOK_ACTUATION_DONE_WHEN,
    WEBHOOK_ACTUATION_GOAL,
    WEBHOOK_ACTUATION_ID,
)
from blackhole_agent.mcp_progress import (
    MCP_PROGRESS_DONE_WHEN,
    MCP_PROGRESS_GOAL,
    MCP_PROGRESS_ID,
)
from blackhole_agent.mcp_tools_list_changed import (
    MCP_TOOLS_CHANGED_DONE_WHEN,
    MCP_TOOLS_CHANGED_GOAL,
    MCP_TOOLS_CHANGED_ID,
)
from blackhole_agent.smtp_actuation import (
    SMTP_ACTUATION_DONE_WHEN,
    SMTP_ACTUATION_GOAL,
    SMTP_ACTUATION_ID,
)
from blackhole_agent.mcp_http_auth import (
    MCP_HTTP_AUTH_DONE_WHEN,
    MCP_HTTP_AUTH_GOAL,
    MCP_HTTP_AUTH_ID,
)
from blackhole_agent.imap_actuation import (
    IMAP_ACTUATION_DONE_WHEN,
    IMAP_ACTUATION_GOAL,
    IMAP_ACTUATION_ID,
)
from blackhole_agent.redis_actuation import (
    REDIS_ACTUATION_DONE_WHEN,
    REDIS_ACTUATION_GOAL,
    REDIS_ACTUATION_ID,
)
from blackhole_agent.mqtt_actuation import (
    MQTT_ACTUATION_DONE_WHEN,
    MQTT_ACTUATION_GOAL,
    MQTT_ACTUATION_ID,
)
from blackhole_agent.dns_actuation import (
    DNS_ACTUATION_DONE_WHEN,
    DNS_ACTUATION_GOAL,
    DNS_ACTUATION_ID,
)
from blackhole_agent.ldap_actuation import (
    LDAP_ACTUATION_DONE_WHEN,
    LDAP_ACTUATION_GOAL,
    LDAP_ACTUATION_ID,
)
from blackhole_agent.postgres_actuation import (
    POSTGRES_ACTUATION_DONE_WHEN,
    POSTGRES_ACTUATION_GOAL,
    POSTGRES_ACTUATION_ID,
)
from blackhole_agent.s3_actuation import (
    S3_ACTUATION_DONE_WHEN,
    S3_ACTUATION_GOAL,
    S3_ACTUATION_ID,
)
from blackhole_agent.watch_actuation import (
    WATCH_ACTUATION_DONE_WHEN,
    WATCH_ACTUATION_GOAL,
    WATCH_ACTUATION_ID,
)
from blackhole_agent.mcp_cursor_pagination import (
    MCP_CURSOR_DONE_WHEN,
    MCP_CURSOR_GOAL,
    MCP_CURSOR_ID,
)
from blackhole_agent.mcp_structured_output import (
    MCP_STRUCTURED_DONE_WHEN,
    MCP_STRUCTURED_GOAL,
    MCP_STRUCTURED_ID,
)
from blackhole_agent.websocket_actuation import (
    WEBSOCKET_ACTUATION_DONE_WHEN,
    WEBSOCKET_ACTUATION_GOAL,
    WEBSOCKET_ACTUATION_ID,
)
from blackhole_agent.ssh_actuation import (
    SSH_ACTUATION_DONE_WHEN,
    SSH_ACTUATION_GOAL,
    SSH_ACTUATION_ID,
)
from blackhole_agent.grpc_actuation import (
    GRPC_ACTUATION_DONE_WHEN,
    GRPC_ACTUATION_GOAL,
    GRPC_ACTUATION_ID,
)
from blackhole_agent.amqp_actuation import (
    AMQP_ACTUATION_DONE_WHEN,
    AMQP_ACTUATION_GOAL,
    AMQP_ACTUATION_ID,
)
from blackhole_agent.ftp_actuation import (
    FTP_ACTUATION_DONE_WHEN,
    FTP_ACTUATION_GOAL,
    FTP_ACTUATION_ID,
)
from blackhole_agent.tftp_actuation import (
    TFTP_ACTUATION_DONE_WHEN,
    TFTP_ACTUATION_GOAL,
    TFTP_ACTUATION_ID,
)
from blackhole_agent.leftover_handoff_rebind import (
    LEFTOVER_HANDOFF_REBIND_DONE_WHEN,
    LEFTOVER_HANDOFF_REBIND_GOAL,
    LEFTOVER_HANDOFF_REBIND_ID,
)
from blackhole_agent.orphan_loop_reap import (
    ORPHAN_LOOP_REAP_DONE_WHEN,
    ORPHAN_LOOP_REAP_GOAL,
    ORPHAN_LOOP_REAP_ID,
)
from blackhole_agent.loop_reboot_restore import (
    LOOP_REBOOT_RESTORE_DONE_WHEN,
    LOOP_REBOOT_RESTORE_GOAL,
    LOOP_REBOOT_RESTORE_ID,
)
from blackhole_agent.loop_login_task import (
    LOOP_LOGIN_TASK_DONE_WHEN,
    LOOP_LOGIN_TASK_GOAL,
    LOOP_LOGIN_TASK_ID,
)
from blackhole_agent.loop_login_repair import (
    LOOP_LOGIN_REPAIR_DONE_WHEN,
    LOOP_LOGIN_REPAIR_GOAL,
    LOOP_LOGIN_REPAIR_ID,
)
from blackhole_agent.loop_login_drift import (
    LOOP_LOGIN_DRIFT_DONE_WHEN,
    LOOP_LOGIN_DRIFT_GOAL,
    LOOP_LOGIN_DRIFT_ID,
)
from blackhole_agent.loop_login_stale import (
    LOOP_LOGIN_STALE_DONE_WHEN,
    LOOP_LOGIN_STALE_GOAL,
    LOOP_LOGIN_STALE_ID,
)
from blackhole_agent.loop_login_retire import (
    LOOP_LOGIN_RETIRE_DONE_WHEN,
    LOOP_LOGIN_RETIRE_GOAL,
    LOOP_LOGIN_RETIRE_ID,
)
from blackhole_agent.loop_login_sweep import (
    LOOP_LOGIN_SWEEP_DONE_WHEN,
    LOOP_LOGIN_SWEEP_GOAL,
    LOOP_LOGIN_SWEEP_ID,
)
from blackhole_agent.loop_login_scrub import (
    LOOP_LOGIN_SCRUB_DONE_WHEN,
    LOOP_LOGIN_SCRUB_GOAL,
    LOOP_LOGIN_SCRUB_ID,
)
from blackhole_agent.loop_login_audit import (
    LOOP_LOGIN_AUDIT_DONE_WHEN,
    LOOP_LOGIN_AUDIT_GOAL,
    LOOP_LOGIN_AUDIT_ID,
)
from blackhole_agent.loop_login_prune import (
    LOOP_LOGIN_PRUNE_DONE_WHEN,
    LOOP_LOGIN_PRUNE_GOAL,
    LOOP_LOGIN_PRUNE_ID,
)
from blackhole_agent.loop_login_tombstone import (
    LOOP_LOGIN_TOMBSTONE_DONE_WHEN,
    LOOP_LOGIN_TOMBSTONE_GOAL,
    LOOP_LOGIN_TOMBSTONE_ID,
)
from blackhole_agent.loop_login_compact import (
    LOOP_LOGIN_COMPACT_DONE_WHEN,
    LOOP_LOGIN_COMPACT_GOAL,
    LOOP_LOGIN_COMPACT_ID,
)
from blackhole_agent.loop_login_rollup import (
    LOOP_LOGIN_ROLLUP_DONE_WHEN,
    LOOP_LOGIN_ROLLUP_GOAL,
    LOOP_LOGIN_ROLLUP_ID,
)
from blackhole_agent.loop_login_verify import (
    LOOP_LOGIN_VERIFY_DONE_WHEN,
    LOOP_LOGIN_VERIFY_GOAL,
    LOOP_LOGIN_VERIFY_ID,
)
from blackhole_agent.loop_login_rollup_repair import (
    LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN,
    LOOP_LOGIN_ROLLUP_REPAIR_GOAL,
    LOOP_LOGIN_ROLLUP_REPAIR_ID,
)
from blackhole_agent.loop_login_rollup_journal import (
    LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN,
    LOOP_LOGIN_ROLLUP_JOURNAL_GOAL,
    LOOP_LOGIN_ROLLUP_JOURNAL_ID,
)
from blackhole_agent.loop_login_journal_prune import (
    LOOP_LOGIN_JOURNAL_PRUNE_DONE_WHEN,
    LOOP_LOGIN_JOURNAL_PRUNE_GOAL,
    LOOP_LOGIN_JOURNAL_PRUNE_ID,
)
from blackhole_agent.local_capability_kernel import _write_fixture_ledger
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    load_campaign,
    save_campaign,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    load_recent_mission_history,
    semantic_signature,
)

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
GENESIS_DIVERSIFY_ID = "capability.kernel-genesis-diversify"

GENESIS_DIVERSIFY_DONE_WHEN = (
    f"capability_exists:{GENESIS_DIVERSIFY_ID};"
    f"capability_proved:{GENESIS_DIVERSIFY_ID};"
    "no_skill_route"
)
GENESIS_DIVERSIFY_GOAL = (
    "When experience fuel is empty and every remaining catalog successor fails "
    "controller selection gates, repair the empty successor: mint a diversity-ranked "
    "mission on a different capability family in-process so a live consumed campaign "
    "cannot leave genesis unbound."
)

COMPOUNDING_THROUGH_FABRIC = (
    KERNEL_GENESIS_BIND_ID,
    CONSUMED_GROWTH_ID,
    COMPOUND_LOOP_ID,
    PRIMITIVE_COMPOSE_ID,
    COMPOSED_PROGRAM_ID,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_ID,
    PROGRAM_LATTICE_ID,
    PROGRAM_FABRIC_ID,
)

DIVERSITY_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": GENESIS_DIVERSIFY_ID,
        "goal": GENESIS_DIVERSIFY_GOAL,
        "done_when": GENESIS_DIVERSIFY_DONE_WHEN,
        "source": "genesis_bind_diversity",
    },
    {
        "id": MISSION_MEMORY_ID,
        "goal": MISSION_MEMORY_GOAL,
        "done_when": MISSION_MEMORY_DONE_WHEN,
        "source": "genesis_bind_memory",
    },
    {
        "id": HALF_OPEN_PERSIST_ID,
        "goal": HALF_OPEN_PERSIST_GOAL,
        "done_when": HALF_OPEN_PERSIST_DONE_WHEN,
        "source": "genesis_bind_half_open",
    },
    {
        "id": MCP_HANDSHAKE_ID,
        "goal": MCP_HANDSHAKE_GOAL,
        "done_when": MCP_HANDSHAKE_DONE_WHEN,
        "source": "genesis_bind_handshake",
    },
    {
        "id": MCP_CALL_ID,
        "goal": MCP_CALL_GOAL,
        "done_when": MCP_CALL_DONE_WHEN,
        "source": "genesis_bind_call_isolation",
    },
    {
        "id": MCP_REVERSE_ID,
        "goal": MCP_REVERSE_GOAL,
        "done_when": MCP_REVERSE_DONE_WHEN,
        "source": "genesis_bind_reverse_channel",
    },
    {
        "id": MCP_HTTP_ID,
        "goal": MCP_HTTP_GOAL,
        "done_when": MCP_HTTP_DONE_WHEN,
        "source": "genesis_bind_http_transport",
    },
    {
        "id": MCP_HTTP_EVENT_ID,
        "goal": MCP_HTTP_EVENT_GOAL,
        "done_when": MCP_HTTP_EVENT_DONE_WHEN,
        "source": "genesis_bind_http_event_stream",
    },
    {
        "id": PUBLICATION_RESILIENCE_ID,
        "goal": PUBLICATION_RESILIENCE_GOAL,
        "done_when": PUBLICATION_RESILIENCE_DONE_WHEN,
        "source": "genesis_bind_publication",
    },
    {
        "id": BROWSER_ACTUATION_ID,
        "goal": BROWSER_ACTUATION_GOAL,
        "done_when": BROWSER_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_browser",
    },
    {
        "id": GMAIL_ACTUATION_ID,
        "goal": GMAIL_ACTUATION_GOAL,
        "done_when": GMAIL_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_gmail",
    },
    {
        "id": GODOT_ACTUATION_ID,
        "goal": GODOT_ACTUATION_GOAL,
        "done_when": GODOT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_godot",
    },
    {
        "id": MCP_RECONNECT_ID,
        "goal": MCP_RECONNECT_GOAL,
        "done_when": MCP_RECONNECT_DONE_WHEN,
        "source": "genesis_bind_reconnect",
    },
    {
        "id": HALF_OPEN_PROBE_ID,
        "goal": HALF_OPEN_PROBE_GOAL,
        "done_when": HALF_OPEN_PROBE_DONE_WHEN,
        "source": "genesis_bind_half_open_probe",
    },
    {
        "id": MCP_SAMPLING_ID,
        "goal": MCP_SAMPLING_GOAL,
        "done_when": MCP_SAMPLING_DONE_WHEN,
        "source": "genesis_bind_sampling",
    },
    {
        "id": MCP_RESOURCES_ID,
        "goal": MCP_RESOURCES_GOAL,
        "done_when": MCP_RESOURCES_DONE_WHEN,
        "source": "genesis_bind_resources",
    },
    {
        "id": MCP_PROMPTS_ID,
        "goal": MCP_PROMPTS_GOAL,
        "done_when": MCP_PROMPTS_DONE_WHEN,
        "source": "genesis_bind_prompts",
    },
    {
        "id": MCP_COMPLETIONS_ID,
        "goal": MCP_COMPLETIONS_GOAL,
        "done_when": MCP_COMPLETIONS_DONE_WHEN,
        "source": "genesis_bind_completions",
    },
    {
        "id": MCP_LOGGING_ID,
        "goal": MCP_LOGGING_GOAL,
        "done_when": MCP_LOGGING_DONE_WHEN,
        "source": "genesis_bind_logging",
    },
    {
        "id": MCP_ELICITATION_ID,
        "goal": MCP_ELICITATION_GOAL,
        "done_when": MCP_ELICITATION_DONE_WHEN,
        "source": "genesis_bind_elicitation",
    },
    {
        "id": MCP_CANCELLATION_ID,
        "goal": MCP_CANCELLATION_GOAL,
        "done_when": MCP_CANCELLATION_DONE_WHEN,
        "source": "genesis_bind_cancellation",
    },
    {
        "id": MCP_SUBSCRIBE_ID,
        "goal": MCP_SUBSCRIBE_GOAL,
        "done_when": MCP_SUBSCRIBE_DONE_WHEN,
        "source": "genesis_bind_resource_subscribe",
    },
    {
        "id": MCP_ROOTS_CHANGED_ID,
        "goal": MCP_ROOTS_CHANGED_GOAL,
        "done_when": MCP_ROOTS_CHANGED_DONE_WHEN,
        "source": "genesis_bind_roots_list_changed",
    },
    {
        "id": BROWSER_CDP_ID,
        "goal": BROWSER_CDP_GOAL,
        "done_when": BROWSER_CDP_DONE_WHEN,
        "source": "genesis_bind_browser_cdp",
    },
    {
        "id": GITHUB_ACTUATION_ID,
        "goal": GITHUB_ACTUATION_GOAL,
        "done_when": GITHUB_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_github",
    },
    {
        "id": SQLITE_ACTUATION_ID,
        "goal": SQLITE_ACTUATION_GOAL,
        "done_when": SQLITE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_sqlite",
    },
    {
        "id": WEBHOOK_ACTUATION_ID,
        "goal": WEBHOOK_ACTUATION_GOAL,
        "done_when": WEBHOOK_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_webhook",
    },
    {
        "id": MCP_PROGRESS_ID,
        "goal": MCP_PROGRESS_GOAL,
        "done_when": MCP_PROGRESS_DONE_WHEN,
        "source": "genesis_bind_progress",
    },
    {
        "id": MCP_TOOLS_CHANGED_ID,
        "goal": MCP_TOOLS_CHANGED_GOAL,
        "done_when": MCP_TOOLS_CHANGED_DONE_WHEN,
        "source": "genesis_bind_tools_list_changed",
    },
    {
        "id": SMTP_ACTUATION_ID,
        "goal": SMTP_ACTUATION_GOAL,
        "done_when": SMTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_smtp",
    },
    {
        "id": MCP_HTTP_AUTH_ID,
        "goal": MCP_HTTP_AUTH_GOAL,
        "done_when": MCP_HTTP_AUTH_DONE_WHEN,
        "source": "genesis_bind_http_auth",
    },
    {
        "id": IMAP_ACTUATION_ID,
        "goal": IMAP_ACTUATION_GOAL,
        "done_when": IMAP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_imap",
    },
    {
        "id": REDIS_ACTUATION_ID,
        "goal": REDIS_ACTUATION_GOAL,
        "done_when": REDIS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_redis",
    },
    {
        "id": MQTT_ACTUATION_ID,
        "goal": MQTT_ACTUATION_GOAL,
        "done_when": MQTT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mqtt",
    },
    {
        "id": DNS_ACTUATION_ID,
        "goal": DNS_ACTUATION_GOAL,
        "done_when": DNS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_dns",
    },
    {
        "id": LDAP_ACTUATION_ID,
        "goal": LDAP_ACTUATION_GOAL,
        "done_when": LDAP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ldap",
    },
    {
        "id": POSTGRES_ACTUATION_ID,
        "goal": POSTGRES_ACTUATION_GOAL,
        "done_when": POSTGRES_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_postgres",
    },
    {
        "id": S3_ACTUATION_ID,
        "goal": S3_ACTUATION_GOAL,
        "done_when": S3_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_s3",
    },
    {
        "id": WATCH_ACTUATION_ID,
        "goal": WATCH_ACTUATION_GOAL,
        "done_when": WATCH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_watch",
    },
    {
        "id": MCP_CURSOR_ID,
        "goal": MCP_CURSOR_GOAL,
        "done_when": MCP_CURSOR_DONE_WHEN,
        "source": "genesis_bind_cursor_pagination",
    },
    {
        "id": MCP_STRUCTURED_ID,
        "goal": MCP_STRUCTURED_GOAL,
        "done_when": MCP_STRUCTURED_DONE_WHEN,
        "source": "genesis_bind_structured_output",
    },
    {
        "id": WEBSOCKET_ACTUATION_ID,
        "goal": WEBSOCKET_ACTUATION_GOAL,
        "done_when": WEBSOCKET_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_websocket",
    },
    {
        "id": SSH_ACTUATION_ID,
        "goal": SSH_ACTUATION_GOAL,
        "done_when": SSH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ssh",
    },
    {
        "id": GRPC_ACTUATION_ID,
        "goal": GRPC_ACTUATION_GOAL,
        "done_when": GRPC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_grpc",
    },
    {
        "id": AMQP_ACTUATION_ID,
        "goal": AMQP_ACTUATION_GOAL,
        "done_when": AMQP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_amqp",
    },
    {
        "id": FTP_ACTUATION_ID,
        "goal": FTP_ACTUATION_GOAL,
        "done_when": FTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ftp",
    },
    {
        "id": TFTP_ACTUATION_ID,
        "goal": TFTP_ACTUATION_GOAL,
        "done_when": TFTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_tftp",
    },
    {
        "id": LEFTOVER_HANDOFF_REBIND_ID,
        "goal": LEFTOVER_HANDOFF_REBIND_GOAL,
        "done_when": LEFTOVER_HANDOFF_REBIND_DONE_WHEN,
        "source": "genesis_bind_leftover_handoff",
    },
    {
        "id": ORPHAN_LOOP_REAP_ID,
        "goal": ORPHAN_LOOP_REAP_GOAL,
        "done_when": ORPHAN_LOOP_REAP_DONE_WHEN,
        "source": "genesis_bind_orphan_loop",
    },
    {
        "id": LOOP_REBOOT_RESTORE_ID,
        "goal": LOOP_REBOOT_RESTORE_GOAL,
        "done_when": LOOP_REBOOT_RESTORE_DONE_WHEN,
        "source": "genesis_bind_loop_reboot",
    },
    {
        "id": LOOP_LOGIN_TASK_ID,
        "goal": LOOP_LOGIN_TASK_GOAL,
        "done_when": LOOP_LOGIN_TASK_DONE_WHEN,
        "source": "genesis_bind_loop_login",
    },
    {
        "id": LOOP_LOGIN_REPAIR_ID,
        "goal": LOOP_LOGIN_REPAIR_GOAL,
        "done_when": LOOP_LOGIN_REPAIR_DONE_WHEN,
        "source": "genesis_bind_loop_login_repair",
    },
    {
        "id": LOOP_LOGIN_DRIFT_ID,
        "goal": LOOP_LOGIN_DRIFT_GOAL,
        "done_when": LOOP_LOGIN_DRIFT_DONE_WHEN,
        "source": "genesis_bind_loop_login_drift",
    },
    {
        "id": LOOP_LOGIN_STALE_ID,
        "goal": LOOP_LOGIN_STALE_GOAL,
        "done_when": LOOP_LOGIN_STALE_DONE_WHEN,
        "source": "genesis_bind_loop_login_stale",
    },
    {
        "id": LOOP_LOGIN_RETIRE_ID,
        "goal": LOOP_LOGIN_RETIRE_GOAL,
        "done_when": LOOP_LOGIN_RETIRE_DONE_WHEN,
        "source": "genesis_bind_loop_login_retire",
    },
    {
        "id": LOOP_LOGIN_SWEEP_ID,
        "goal": LOOP_LOGIN_SWEEP_GOAL,
        "done_when": LOOP_LOGIN_SWEEP_DONE_WHEN,
        "source": "genesis_bind_loop_login_sweep",
    },
    {
        "id": LOOP_LOGIN_SCRUB_ID,
        "goal": LOOP_LOGIN_SCRUB_GOAL,
        "done_when": LOOP_LOGIN_SCRUB_DONE_WHEN,
        "source": "genesis_bind_loop_login_scrub",
    },
    {
        "id": LOOP_LOGIN_AUDIT_ID,
        "goal": LOOP_LOGIN_AUDIT_GOAL,
        "done_when": LOOP_LOGIN_AUDIT_DONE_WHEN,
        "source": "genesis_bind_loop_login_audit",
    },
    {
        "id": LOOP_LOGIN_PRUNE_ID,
        "goal": LOOP_LOGIN_PRUNE_GOAL,
        "done_when": LOOP_LOGIN_PRUNE_DONE_WHEN,
        "source": "genesis_bind_loop_login_prune",
    },
    {
        "id": LOOP_LOGIN_TOMBSTONE_ID,
        "goal": LOOP_LOGIN_TOMBSTONE_GOAL,
        "done_when": LOOP_LOGIN_TOMBSTONE_DONE_WHEN,
        "source": "genesis_bind_loop_login_tombstone",
    },
    {
        "id": LOOP_LOGIN_COMPACT_ID,
        "goal": LOOP_LOGIN_COMPACT_GOAL,
        "done_when": LOOP_LOGIN_COMPACT_DONE_WHEN,
        "source": "genesis_bind_loop_login_compact",
    },
    {
        "id": LOOP_LOGIN_ROLLUP_ID,
        "goal": LOOP_LOGIN_ROLLUP_GOAL,
        "done_when": LOOP_LOGIN_ROLLUP_DONE_WHEN,
        "source": "genesis_bind_loop_login_rollup",
    },
    {
        "id": LOOP_LOGIN_VERIFY_ID,
        "goal": LOOP_LOGIN_VERIFY_GOAL,
        "done_when": LOOP_LOGIN_VERIFY_DONE_WHEN,
        "source": "genesis_bind_loop_login_verify",
    },
    {
        "id": LOOP_LOGIN_ROLLUP_REPAIR_ID,
        "goal": LOOP_LOGIN_ROLLUP_REPAIR_GOAL,
        "done_when": LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN,
        "source": "genesis_bind_loop_login_rollup_repair",
    },
    {
        "id": LOOP_LOGIN_ROLLUP_JOURNAL_ID,
        "goal": LOOP_LOGIN_ROLLUP_JOURNAL_GOAL,
        "done_when": LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN,
        "source": "genesis_bind_loop_login_rollup_journal",
    },
    {
        "id": LOOP_LOGIN_JOURNAL_PRUNE_ID,
        "goal": LOOP_LOGIN_JOURNAL_PRUNE_GOAL,
        "done_when": LOOP_LOGIN_JOURNAL_PRUNE_DONE_WHEN,
        "source": "genesis_bind_loop_login_journal_prune",
    },
)

_LIVE_SHAPED_GOALS = (
    PROGRAM_TOWER_GOAL,
    PROGRAM_LATTICE_GOAL,
    PROGRAM_FABRIC_GOAL,
    (
        "Repair mixed-stack restoration after a red MCP hop fails the mixed grade: "
        "heal the hop in-process, re-solve the composition, and restore mixed stack "
        "health; an unrepairable hop must leave the stack unhealthy while default "
        "recovery stays blind."
    ),
    (
        "Close operational class `mission_leftover`: Optional later work is mixed "
        "absorbed stack repair so a healable producer restores mixed absorbed stack "
        "health."
    ),
    (
        "Close operational class `mission_leftover`: Optional later work is watching "
        "mixed MCP+absorbed goals in the recovery plane so a red MCP hop is healed."
    ),
    (
        "Repair leftover harvest isolation of the origin ledger: a shipped leftover "
        "still enters genesis fuel because leftover satisfaction only reads the "
        "lagging checkout ledger."
    ),
    (
        "Repair mission-worktree reclamation of stale directories: a path that exists "
        "on disk but is no longer a git working tree still fails git worktree remove, "
        "poisons the GC report, and leaves last_worktree_gc_error sticky so later "
        "valid worktrees never finish clean."
    ),
)


def genesis_diversify_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.kernel_genesis_diversify import "
        "builtin_kernel_genesis_diversify_proof; r=builtin_kernel_genesis_diversify_proof(); "
        "assert r['ok'] and r.get('action')=='kernel_genesis_diversify' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_genesis_diversify_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=GENESIS_DIVERSIFY_ID,
        name="Genesis catalog diversity bind",
        description=(
            "When experience fuel is empty and the compounding catalog's remaining "
            "successor fails controller selection gates, genesis bind ranks a "
            "diversity catalog of unsaturated capability families and fills the "
            "first open gate-passing mission instead of returning empty."
        ),
        kind="python",
        entry="blackhole_agent.kernel_genesis_diversify:builtin_kernel_genesis_diversify_proof",
        proof_command=genesis_diversify_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.kernel-genesis-bind",
        ),
        behavior_paths=(
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/kernel_genesis_bind.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Empty genesis bind after a rejected compounding successor no longer "
            "stalls: a diversity-ranked mission on a different capability family "
            "is bound in-process so recovered kernels cannot leave genesis unbound."
        ),
        tags=("genesis", "selection", "diversity", "catalog", "kernel"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def bind_diversity_successor(
    root: Path,
    *,
    campaign: LocalCampaign | None = None,
    lineage_ref: str = "",
    history: Sequence[Any] | None = None,
) -> tuple[str, str, str]:
    """Return the first open diversity successor that passes selection gates."""

    live_campaign = campaign if campaign is not None else load_campaign(Path(root))
    if not genesis_bind_is_needed(live_campaign):
        return "", "", ""
    live_history = list(
        history
        if history is not None
        else load_recent_mission_history(Path(root))
    )
    for item in DIVERSITY_CATALOG:
        if not _catalog_item_open(item, Path(root), lineage_ref=lineage_ref):
            continue
        goal = str(item.get("goal") or "").strip()
        done_when = str(item.get("done_when") or "").strip()
        if not goal or not done_when:
            continue
        gate = assess_mission_selection(
            Path(root),
            goal,
            done_when,
            history=live_history,
        )
        if gate.accepted:
            return goal, done_when, str(item.get("source") or "genesis_bind_diversity")
    return "", "", ""


def _register_compounding_through_fabric(root: Path) -> None:
    for capability_id in COMPOUNDING_THROUGH_FABRIC:
        _register_proved(root, capability_id)


def _write_live_shaped_history(root: Path) -> None:
    for index, goal in enumerate(_LIVE_SHAPED_GOALS, start=1):
        _write_complete_mission(root, f"live-shaped-{index}", goal, order=index)


def _prepare_exhausted_catalog(root: Path) -> None:
    from blackhole_agent.kernel_unscoped_resume import _register_turn_failed_closers

    _write_fixture_ledger(root)
    _register_turn_failed_closers(root)
    _write_live_shaped_history(root)
    _register_compounding_through_fabric(root)
    save_campaign(root, _consumed_campaign())


def builtin_kernel_genesis_diversify_proof() -> dict[str, Any]:
    """Prove behavioral diversity, rather than enumerating protocol names."""
    from unittest.mock import patch

    from blackhole_agent.mission_selection import MissionHistoryEntry

    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="genesis-diversify-quality-") as tmp:
        root = Path(tmp)
        campaign = _consumed_campaign()
        recipe = "Repair {name} handshake: seal a {name}digest and independently poll it with a later reader."
        history = [
            MissionHistoryEntry(str(i), recipe.format(name=name), semantic_signature(recipe.format(name=name)), name, "complete")
            for i, name in enumerate(("bgp4", "pmsi", "wildad"))
        ]
        repeated = assess_mission_selection(root, recipe.format(name="another_protocol"), "A reference peer works.", history=history)
        checks["renaming_is_repetition"] = not repeated.accepted and repeated.repetition_count == 3
        checks["behavior_family_saturates"] = repeated.recent_family_count == 3
        checks["ledger_only_contract_rejected"] = not assess_mission_selection(
            root, GENESIS_DIVERSIFY_GOAL, GENESIS_DIVERSIFY_DONE_WHEN, history=[]
        ).accepted
        legacy_only = (
            {"id": "capability.fixture-static", "goal": GENESIS_DIVERSIFY_GOAL, "done_when": GENESIS_DIVERSIFY_DONE_WHEN, "source": "static"},
        )
        with patch(__name__ + ".DIVERSITY_CATALOG", legacy_only):
            legacy_bind = bind_diversity_successor(root, campaign=campaign, history=[])
        checks["legacy_catalog_not_auto_accepted"] = legacy_bind == ("", "", "")
        goal = "Repair memory retrieval after process restart without losing the original task context."
        done = "A fresh process answers a fixture question using the previously persisted task context."
        fixture = (
            {"id": "capability.fixture-static", "goal": GENESIS_DIVERSIFY_GOAL, "done_when": GENESIS_DIVERSIFY_DONE_WHEN, "source": "static"},
            {"id": "capability.fixture-outcome", "goal": goal, "done_when": done, "source": "outcome"},
        )
        with patch(__name__ + ".DIVERSITY_CATALOG", fixture):
            chosen = bind_diversity_successor(root, campaign=campaign, history=history)
        checks["chooses_different_measurable_outcome"] = chosen == (goal, done, "outcome")
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    return {
        "ok": all(checks.values()), "action": "kernel_genesis_diversify", "checks": checks,
        "passed_count": sum(checks.values()), "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": GENESIS_DIVERSIFY_GOAL, "done_when": GENESIS_DIVERSIFY_DONE_WHEN,
    }
