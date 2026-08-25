import datetime
import logging
import os
import traceback
from functools import wraps
from typing import Any, Callable

import botocore
from aws_embedded_metrics.logger.metrics_context import MetricsContext
from aws_embedded_metrics.sinks.stdout_sink import StdoutSink

from sagemaker_studio.utils._internal import InternalUtils

_utils = InternalUtils()

# Constants
DEFAULT_HTTP_CODE = "500"
DEFAULT_ERROR_CODE = "InternalError"
SUCCESS_HTTP_CODE = "200"
SUCCESS_MESSAGE = "Success"
FORBIDDEN_HTTP_CODE = "403"
SERVICE_UNAVAILABLE_CODE = "503"
METRIC_NAMESPACE = "SagemakerUnifiedStudio-Python-SDK"


# Error patterns for classification
ACCESS_DENIED_PATTERNS = (
    "AccessDenied",
    "Access denied",
    "permission",
    "Unauthorized",
)
UX_ERROR_PATTERNS = (
    "ResourceLimitExceeded",
    "S3RegionMismatch",
    "ThrottlingException",
    "NoSuchBucket",
    "ResourceNotFound",
    "ValidationException",
)
CONNECTION_ERROR_PATTERNS = (
    "ConnectionError",
    "ConnectTimeoutError",
    "EndpointConnectionError",
    "ProxyConnectionError",
    "ReadTimeoutError",
)


# All client-side error patterns (not faults)
CLIENT_ERROR_PATTERNS = ACCESS_DENIED_PATTERNS + UX_ERROR_PATTERNS + CONNECTION_ERROR_PATTERNS


logger = logging.getLogger("metrics")


class ErrorChecker:
    """Determines if an error represents a service error or user error."""

    def is_service_error(self, http_code: str, error_code: str = "") -> bool:
        """Determine if an error represents a service error based on HTTP status code and error details.
        Args:
            http_code: The HTTP status code (numeric string) or error code if not numeric
            error_code: The error code details (optional, used as fallback)
        Returns:
            bool: True if the error is a service error (5xx server error), False otherwise (4xx user error)
        """

        # Try to parse as numeric HTTP status code
        try:
            status_code = int(http_code)
            return 500 <= status_code < 600
        except (ValueError, TypeError):
            pass

        # Fallback: Check error patterns
        error_to_check = error_code or http_code
        return not any(error_to_check.startswith(pattern) for pattern in CLIENT_ERROR_PATTERNS)


class LogFileSink(StdoutSink):
    """Custom sink that writes metrics to log file."""

    def accept(self, context: MetricsContext) -> None:
        for serialized_content in self.serializer.serialize(context):
            if serialized_content:
                logger.info(serialized_content)

    @staticmethod
    def name() -> str:
        return "LogFileSink"


def _extract_codes(excep: Exception) -> tuple[str, str]:
    """Extract HTTP status code and error code from exception.
    Args:
        excep: The exception to extract codes from
    Returns:
        Tuple of (http_code, error_code) as strings
    """
    try:
        if isinstance(excep, botocore.exceptions.ClientError):
            error_code = excep.response["Error"]["Code"]
            http_code = str(excep.response["ResponseMetadata"]["HTTPStatusCode"])
            return http_code, error_code

        if isinstance(excep, botocore.exceptions.EndpointConnectionError):
            return SERVICE_UNAVAILABLE_CODE, "EndpointConnectionError"

        if isinstance(excep, botocore.exceptions.NoCredentialsError):
            return FORBIDDEN_HTTP_CODE, "NoCredentials"

        # Default for unknown exceptions
        return DEFAULT_HTTP_CODE, type(excep).__name__

    except Exception:
        logger.exception("Failed to extract error codes from exception, using defaults")
        return DEFAULT_HTTP_CODE, "InternalErrorLogging"


def _set_context_properties(
    context: MetricsContext, operation: str, http_code: str, error_details: str
) -> None:
    """Set all context properties and dimensions.
    Args:
        context: The metrics context to populate
        operation: The operation name
        http_code: HTTP status code
        error_details: Error details or message
    """
    context.namespace = METRIC_NAMESPACE
    context.should_use_default_dimensions = False
    context.put_dimensions({"Operation": operation})

    # Set metadata properties
    context.set_property("AccountId", _utils._get_account_id())
    context.set_property("DataZoneDomainId", _utils._get_domain_id())
    context.set_property("Userid", _utils._get_user_id())
    context.set_property("Stage", _utils._get_datazone_stage())
    context.set_property("HTTPErrorCode", http_code)
    context.set_property("ErrorCode", error_details)


def log_session_metric(
    metric_name: str,
    session_id: str = None,
    duration_ms: int = None,
    additional_properties: dict = None,
) -> None:
    """Log session-level metrics for SDK usage tracking.

    Args:
        metric_name: Metric name (SessionCreated, SessionStopped)
        session_id: Athena Spark session ID
        duration_ms: Session duration in milliseconds
        additional_properties: Optional additional metadata
    """
    logger.info(f"Logging session metric: {metric_name}")

    context = MetricsContext().empty()
    context.namespace = METRIC_NAMESPACE
    context.should_use_default_dimensions = False
    context.put_dimensions({"MetricType": "SessionMetric"})

    context.set_property("SessionId", session_id or "unknown")
    try:
        context.set_property("AccountId", _utils._get_account_id())
    except Exception:
        context.set_property("AccountId", "unknown")
    try:
        context.set_property("Userid", _utils._get_user_id())
    except Exception:
        context.set_property("Userid", "unknown")
    try:
        context.set_property("Stage", _utils._get_datazone_stage())
    except Exception:
        context.set_property("Stage", "unknown")

    if additional_properties:
        for key, value in additional_properties.items():
            context.set_property(key, str(value))

    context.put_metric(metric_name, 1, "Count")

    if duration_ms:
        context.put_metric("SessionDuration", duration_ms, "Milliseconds")

    _metrics_logger = _get_session_metrics_logger()
    for serialized_content in LogFileSink().serializer.serialize(context):
        if serialized_content:
            _metrics_logger.info(serialized_content)


def _get_session_metrics_logger() -> logging.Logger:
    """Get or initialize the session metrics file logger."""
    metrics_logger = logging.getLogger("session_metrics")
    if not metrics_logger.handlers:
        log_file = "/var/log/studio/data-notebook-kernel-server/spark_connect_session_metrics.log"
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            handler = logging.FileHandler(log_file)
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            metrics_logger.addHandler(handler)
            metrics_logger.setLevel(logging.INFO)
        except (PermissionError, OSError) as e:
            logger.error(f"Failed to create session metrics log file: {e}")
    return metrics_logger


def sync_with_metrics(operation: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to track metrics for synchronous operations."""

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.info(f"Starting metric collection for operation: {operation}")
            start_time = datetime.datetime.now()

            # Initialize metric counters
            user_error = service_error = success = 0
            http_code = SUCCESS_HTTP_CODE
            error_details = SUCCESS_MESSAGE
            is_exception = False

            error_checker = ErrorChecker()

            try:
                result = func(*args, **kwargs)
                success = 1
                return result
            except Exception as excep:
                http_code, error_details = _extract_codes(excep)
                is_exception = True
                raise
            finally:
                # Create and flush metrics synchronously
                try:
                    logger.info(f"Flushing metrics for operation: {operation}")
                    elapsed = datetime.datetime.now() - start_time
                    context = MetricsContext().empty()
                    _set_context_properties(context, operation, http_code, error_details)
                    # Set user_error/service_error metrics based on exception
                    if is_exception:
                        if error_checker.is_service_error(http_code, error_details):
                            service_error = 1
                        else:
                            user_error = 1
                        stack_trace = traceback.format_exc()
                        context.set_property("StackTrace", stack_trace)
                    # Put metrics
                    context.put_metric("Success", success, "Count")
                    context.put_metric("UserError", user_error, "Count")
                    context.put_metric("ServiceError", service_error, "Count")
                    context.put_metric(
                        "Latency", int(elapsed.total_seconds() * 1000), "Milliseconds"
                    )
                    # Use LogFileSink for synchronous flushing
                    sink = LogFileSink()
                    sink.accept(context)
                    logger.info(f"Flushed metrics for operation: {operation}")
                except Exception:
                    logger.exception(f"Failed to flush metrics for operation: {operation}")

        return wrapper

    return decorate
