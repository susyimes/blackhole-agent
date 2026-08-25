"""
Retry mechanisms and error recovery patterns for Redshift Data API.

This module provides retry logic for handling transient failures and
implementing exponential backoff strategies.
"""

import random
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type

from .exceptions import OperationalError, TransientError, map_boto3_exception


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Optional[tuple] = None,
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay in seconds before first retry
            max_delay: Maximum delay in seconds between retries
            backoff_multiplier: Multiplier for exponential backoff
            jitter: Whether to add random jitter to delays
            retryable_exceptions: Tuple of exception types that should be retried
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or (
            TransientError,
            # Add specific boto3 exceptions that are transient
        )

    def calculate_delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        """
        Calculate delay for the given attempt number.

        Args:
            attempt: Current attempt number (0-based)
            retry_after: Suggested retry delay from server

        Returns:
            Delay in seconds
        """
        if retry_after is not None:
            # Use server-suggested delay if available
            delay = retry_after
        else:
            # Calculate exponential backoff delay
            delay = self.base_delay * (self.backoff_multiplier**attempt)

        # Cap at maximum delay
        delay = min(delay, self.max_delay)

        # Add jitter to avoid thundering herd
        if self.jitter:
            jitter_range = delay * 0.1  # 10% jitter
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """
        Determine if an exception should be retried.

        Args:
            exception: The exception that occurred
            attempt: Current attempt number (0-based)

        Returns:
            True if the exception should be retried
        """
        if attempt >= self.max_attempts:
            return False

        # Check if it's a retryable exception type
        if isinstance(exception, self.retryable_exceptions):
            return True

        # Check for specific boto3 exceptions that are transient
        from botocore.exceptions import ClientError

        if isinstance(exception, ClientError):
            error_code = exception.response.get("Error", {}).get("Code", "")
            transient_codes = {
                "ThrottlingException",
                "ServiceUnavailableException",
                "InternalServerException",
                "RequestTimeoutException",
                "TooManyRequestsException",
            }
            return error_code in transient_codes

        return False


class RetryContext:
    """Context for tracking retry attempts."""

    def __init__(self, operation_name: str, execution_context: Optional[Dict] = None):
        """
        Initialize retry context.

        Args:
            operation_name: Name of the operation being retried
            execution_context: Additional context for logging
        """
        self.operation_name = operation_name
        self.execution_context = execution_context or {}
        self.attempt_count = 0
        self.start_time = time.time()
        self.last_exception = None
        self.total_delay = 0.0

    def log_attempt(self, exception: Exception, delay: float):
        """Log a retry attempt."""
        self.attempt_count += 1
        self.last_exception = exception
        self.total_delay += delay

    def log_success(self):
        """Log successful completion after retries."""

    def log_failure(self):
        """Log final failure after all retries exhausted."""


def with_retry(
    config: Optional[RetryConfig] = None,
    operation_name: Optional[str] = None,
    execution_context: Optional[Dict] = None,
):
    """
    Decorator to add retry logic to a function.

    Args:
        config: Retry configuration (uses default if None)
        operation_name: Name of the operation for logging
        execution_context: Additional context for logging

    Usage:
        @with_retry(RetryConfig(max_attempts=5), "execute_statement")
        def execute_statement(self, sql):
            # Implementation that may fail transiently
            pass
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            context = RetryContext(op_name, execution_context)

            for attempt in range(config.max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    context.log_success()
                    return result

                except Exception as e:
                    # Check if we should retry this exception
                    if not config.should_retry(e, attempt):
                        # Not retryable or max attempts reached
                        if attempt > 0:
                            context.log_failure()
                        raise

                    # Calculate delay for next attempt
                    retry_after = getattr(e, "retry_after", None)
                    delay = config.calculate_delay(attempt, retry_after)

                    # Log the retry attempt
                    context.log_attempt(e, delay)

                    # Wait before retrying
                    if delay > 0:
                        time.sleep(delay)

            # This should never be reached due to the retry logic above
            context.log_failure()
            raise context.last_exception

        return wrapper

    return decorator


def retry_on_transient_error(
    func: Callable,
    args: tuple = (),
    kwargs: Optional[Dict] = None,
    config: Optional[RetryConfig] = None,
    operation_name: Optional[str] = None,
    execution_context: Optional[Dict] = None,
) -> Any:
    """
    Execute a function with retry logic for transient errors.

    Args:
        func: Function to execute
        args: Positional arguments for the function
        kwargs: Keyword arguments for the function
        config: Retry configuration
        operation_name: Name of the operation for logging
        execution_context: Additional context for logging

    Returns:
        Result of the function execution

    Raises:
        The last exception if all retries are exhausted
    """
    if kwargs is None:
        kwargs = {}
    if config is None:
        config = RetryConfig()

    op_name = operation_name or f"{func.__module__}.{func.__name__}"
    context = RetryContext(op_name, execution_context)

    for attempt in range(config.max_attempts + 1):
        try:
            result = func(*args, **kwargs)
            context.log_success()
            return result

        except Exception as e:
            # Map boto3 exceptions to DB-API exceptions with context
            if not isinstance(e, (TransientError, OperationalError)):
                mapped_exception = map_boto3_exception(e, execution_context)
                if mapped_exception != e:
                    e = mapped_exception

            # Check if we should retry this exception
            if not config.should_retry(e, attempt):
                # Not retryable or max attempts reached
                if attempt > 0:
                    context.log_failure()
                raise

            # Calculate delay for next attempt
            retry_after = getattr(e, "retry_after", None)
            delay = config.calculate_delay(attempt, retry_after)

            # Log the retry attempt
            context.log_attempt(e, delay)

            # Wait before retrying
            if delay > 0:
                time.sleep(delay)

    # This should never be reached due to the retry logic above
    context.log_failure()
    raise context.last_exception


class CircuitBreaker:
    """
    Circuit breaker pattern for preventing cascading failures.

    The circuit breaker has three states:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failure threshold exceeded, requests fail immediately
    - HALF_OPEN: Testing if service has recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before attempting recovery
            expected_exception: Exception type that triggers circuit breaker
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of function execution

        Raises:
            OperationalError: If circuit is open
            Original exception: If function fails
        """
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
            else:
                raise OperationalError(
                    f"Circuit breaker is OPEN. Service unavailable. "
                    f"Will retry after {self.recovery_timeout} seconds."
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result

        except self.expected_exception:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.recovery_timeout

    def _on_success(self):
        """Handle successful execution."""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
        self.failure_count = 0

    def _on_failure(self):
        """Handle failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
