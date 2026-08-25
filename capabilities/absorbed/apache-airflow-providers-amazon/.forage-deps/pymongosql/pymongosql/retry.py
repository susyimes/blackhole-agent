# -*- coding: utf-8 -*-
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple, TypeVar

from pymongo.errors import AutoReconnect, ConnectionFailure, NetworkTimeout, ServerSelectionTimeoutError

try:
    from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

    _has_tenacity = True
except ImportError:
    _has_tenacity = False

_logger = logging.getLogger(__name__)
_T = TypeVar("_T")

RETRYABLE_SYSTEM_EXCEPTIONS: Tuple[type, ...] = (
    AutoReconnect,
    NetworkTimeout,
    ConnectionFailure,
    ServerSelectionTimeoutError,
)


@dataclass(frozen=True)
class RetryConfig:
    enabled: bool = False
    attempts: int = 3
    wait_min: float = 0.1
    wait_max: float = 1.0

    @classmethod
    def from_kwargs(cls, kwargs: dict) -> "RetryConfig":
        enabled = bool(kwargs.pop("retry_enabled", False))
        attempts = int(kwargs.pop("retry_attempts", 3))
        wait_min = float(kwargs.pop("retry_wait_min", 0.1))
        wait_max = float(kwargs.pop("retry_wait_max", 1.0))

        if attempts < 1:
            attempts = 1
        if wait_min < 0:
            wait_min = 0.0
        if wait_max < wait_min:
            wait_max = wait_min

        return cls(
            enabled=enabled,
            attempts=attempts,
            wait_min=wait_min,
            wait_max=wait_max,
        )


def execute_with_retry(
    operation: Callable[[], _T],
    retry_config: Optional[RetryConfig],
    operation_name: str,
) -> _T:
    """Execute an operation with retry on transient system-level PyMongo failures."""
    config = retry_config or RetryConfig(enabled=False, attempts=1, wait_min=0.0, wait_max=0.0)

    if not config.enabled or config.attempts <= 1:
        return operation()

    if not _has_tenacity:
        _logger.warning(
            "Retry is enabled but 'tenacity' package is not installed. "
            "Falling back to no-retry. Install it with: pip install pymongosql[retry]"
        )
        return operation()

    def _before_sleep(retry_state: Any) -> None:
        error = retry_state.outcome.exception() if retry_state.outcome else None
        _logger.warning(
            "Retrying %s after transient error (attempt %s/%s): %s",
            operation_name,
            retry_state.attempt_number,
            config.attempts,
            error,
        )

    retrying = Retrying(
        reraise=True,
        stop=stop_after_attempt(config.attempts),
        wait=wait_exponential(min=config.wait_min, max=config.wait_max),
        retry=retry_if_exception_type(RETRYABLE_SYSTEM_EXCEPTIONS),
        before_sleep=_before_sleep,
    )

    return retrying(operation)
