"""
Shared gRPC interceptor and channel-builder base classes for Spark Connect auth.

Concrete interceptors (Athena, EMR Serverless, …) subclass
``BaseSparkConnectGRPCInterceptor`` and implement ``_do_refresh_token`` to call
the service-specific API.  Token state is stored in an immutable ``_TokenState``
namedtuple so that the swap from ``_refresh_token`` is atomic — eliminating the
TOCTOU race between ``cache_expiration_time`` and ``cache_auth_token``.
"""

import datetime
import logging as _logging
import threading as _threading
from collections import namedtuple as _namedtuple

import grpc as _grpc
from pyspark.sql.connect.client import ChannelBuilder as _ChannelBuilder

# ── gRPC call-details boilerplate ────────────────────────────────────────────

_ClientCallDetails = _namedtuple(
    "_ClientCallDetails",
    ("method", "timeout", "metadata", "credentials", "wait_for_ready", "compression"),
)


class _ClientCallDetails(_ClientCallDetails, _grpc.ClientCallDetails):
    pass


# ── Atomic token state ──────────────────────────────────────────────────────

_TokenState = _namedtuple("_TokenState", ("auth_token", "expiration_time"))

_EXPIRED = _TokenState(
    auth_token=None,
    expiration_time=datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
)

# Default early-refresh margin: refresh 5 min before actual expiry
_DEFAULT_EARLY_REFRESH_SECONDS = 5 * 60


# ── Base interceptor ────────────────────────────────────────────────────────


class BaseSparkConnectGRPCInterceptor(
    _grpc.UnaryUnaryClientInterceptor,
    _grpc.UnaryStreamClientInterceptor,
    _grpc.StreamUnaryClientInterceptor,
    _grpc.StreamStreamClientInterceptor,
):
    """Base gRPC interceptor that handles token caching, refresh, and injection.

    Subclasses must implement ``_do_refresh_token`` which performs the actual
    service API call and returns a new ``_TokenState``.
    """

    def __init__(
        self,
        session_id: str,
        initial_auth_token: str = None,
        initial_token_expiry=None,
        early_refresh_seconds: int = _DEFAULT_EARLY_REFRESH_SECONDS,
        logger_name: str = "SparkConnect",
    ):
        self.logger = _logging.getLogger(logger_name)
        self.session_id = session_id
        self._early_refresh_seconds = early_refresh_seconds

        if initial_auth_token and initial_token_expiry:
            self._token_state = _TokenState(
                auth_token=initial_auth_token,
                expiration_time=initial_token_expiry
                - datetime.timedelta(seconds=early_refresh_seconds),
            )
        else:
            self._token_state = _EXPIRED

        self._refresh_lock = _threading.Lock()

        self.logger.debug(
            f"Initialized interceptor for session {session_id}, "
            f"initial token seeded: {initial_auth_token is not None}"
        )

    # ── abstract hook ────────────────────────────────────────────────────

    def _do_refresh_token(self) -> _TokenState:
        """Perform the service-specific API call and return a new ``_TokenState``.

        Called under ``_refresh_lock``.  Must NOT be called directly — use
        ``_refresh_token`` instead.
        """
        raise NotImplementedError

    # ── refresh logic (double-check locking) ─────────────────────────────

    def _refresh_token(self):
        with self._refresh_lock:
            # Double-check: another thread may have refreshed already
            if self._token_state.expiration_time >= datetime.datetime.now(datetime.timezone.utc):
                self.logger.debug(
                    f"Token for session {self.session_id} already refreshed by another thread, skipping"
                )
                return
            self._token_state = self._do_refresh_token()

    # ── metadata injection ───────────────────────────────────────────────

    def _with_metadata(self, client_call_details):
        """Inject the current auth token into gRPC metadata, refreshing if expired."""
        state = self._token_state  # single atomic read
        if state.expiration_time < datetime.datetime.now(datetime.timezone.utc):
            self._refresh_token()
            state = self._token_state

        dict_metadata = dict(client_call_details.metadata or [])
        dict_metadata["x-aws-proxy-auth"] = state.auth_token
        metadata = list(dict_metadata.items())

        return _ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
            compression=client_call_details.compression,
        )

    # ── intercept methods ────────────────────────────────────────────────

    def intercept_unary_unary(self, continuation, client_call_details, request):
        return continuation(self._with_metadata(client_call_details), request)

    def intercept_unary_stream(self, continuation, client_call_details, request):
        return continuation(self._with_metadata(client_call_details), request)

    def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        return continuation(self._with_metadata(client_call_details), request_iterator)

    def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
        return continuation(self._with_metadata(client_call_details), request_iterator)


# ── Base channel builder ─────────────────────────────────────────────────────


class BaseCustomChannelBuilder(_ChannelBuilder):
    """Channel builder that wraps the channel with a ``BaseSparkConnectGRPCInterceptor``."""

    def _create_interceptor(self) -> BaseSparkConnectGRPCInterceptor:
        """Return the concrete interceptor instance.  Must be implemented by subclasses."""
        raise NotImplementedError

    def toChannel(self) -> _grpc.Channel:  # noqa: N802
        channel = super().toChannel()
        return _grpc.intercept_channel(channel, self._create_interceptor())
