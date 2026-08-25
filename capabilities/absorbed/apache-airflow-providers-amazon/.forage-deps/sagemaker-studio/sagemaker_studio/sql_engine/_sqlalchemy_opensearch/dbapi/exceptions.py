"""
DB-API 2.0 exception hierarchy and OpenSearch specific exceptions.

This module defines the standard DB-API 2.0 exception hierarchy plus
additional exceptions specific to OpenSearch operations.
"""

import functools


# DB-API 2.0 Standard Exception Hierarchy
class Error(Exception):
    """Base class for all database-related errors."""


class Warning(Exception):
    """Exception raised for important warnings like data truncations."""


class InterfaceError(Error):
    """Exception raised for errors related to the database interface."""


class DatabaseError(Error):
    """Exception raised for errors related to the database."""


class DataError(DatabaseError):
    """Exception raised for errors due to problems with the processed data."""


class OperationalError(DatabaseError):
    """Exception raised for errors related to the database's operation."""


class IntegrityError(DatabaseError):
    """Exception raised when the relational integrity of the database is affected."""


class InternalError(DatabaseError):
    """Exception raised when the database encounters an internal error."""


class ProgrammingError(DatabaseError):
    """Exception raised for programming errors."""


class NotSupportedError(DatabaseError):
    """Exception raised when a method or database API is not supported."""


# OpenSearch Specific Exceptions
class OpenSearchConnectionError(OperationalError):
    """Exception raised when OpenSearch connection fails."""

    def __init__(self, message, host=None, port=None, execution_context=None):
        super().__init__(message)
        self.host = host
        self.port = port
        self.execution_context = execution_context or {}

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.host:
            details.append(f"Host: {self.host}")
        if self.port:
            details.append(f"Port: {self.port}")
        if self.execution_context:
            for key, value in self.execution_context.items():
                details.append(f"{key}: {value}")

        if details:
            return f"{base_msg} ({', '.join(details)})"
        return base_msg


class AuthenticationError(OperationalError):
    """Exception raised for authentication-related errors."""

    def __init__(self, message, auth_method=None, host=None, execution_context=None):
        super().__init__(message)
        self.auth_method = auth_method
        self.host = host
        self.execution_context = execution_context or {}

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.auth_method:
            details.append(f"Auth method: {self.auth_method}")
        if self.host:
            details.append(f"Host: {self.host}")
        if self.execution_context:
            for key, value in self.execution_context.items():
                details.append(f"{key}: {value}")

        if details:
            return f"{base_msg} ({', '.join(details)})"
        return base_msg


class InvalidParameterError(ProgrammingError):
    """Exception raised for invalid connection or query parameters."""

    def __init__(self, message, parameter_name=None, parameter_value=None, execution_context=None):
        super().__init__(message)
        self.parameter_name = parameter_name
        self.parameter_value = parameter_value
        self.execution_context = execution_context or {}

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.parameter_name:
            details.append(f"Parameter: {self.parameter_name}")
        if self.parameter_value is not None:
            details.append(f"Value: {self.parameter_value}")
        if self.execution_context:
            for key, value in self.execution_context.items():
                details.append(f"{key}: {value}")

        if details:
            return f"{base_msg} ({', '.join(details)})"
        return base_msg


class TransientError(OperationalError):
    """Exception raised for transient errors that may be retried."""

    def __init__(
        self,
        message,
        retry_after=None,
        attempt_count=None,
        max_attempts=None,
        execution_context=None,
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.attempt_count = attempt_count
        self.max_attempts = max_attempts
        self.execution_context = execution_context or {}

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.retry_after:
            details.append(f"Retry after: {self.retry_after}s")
        if self.attempt_count is not None and self.max_attempts is not None:
            details.append(f"Attempt: {self.attempt_count}/{self.max_attempts}")
        if self.execution_context:
            for key, value in self.execution_context.items():
                details.append(f"{key}: {value}")

        if details:
            return f"{base_msg} ({', '.join(details)})"
        return base_msg


class QueryExecutionError(OperationalError):
    """Exception raised when an OpenSearch query execution fails."""

    def __init__(self, message, query=None, error_type=None):
        super().__init__(message)
        self.query = query
        self.error_type = error_type

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.error_type:
            details.append(f"Error type: {self.error_type}")
        if self.query:
            # Truncate long queries
            query_str = self.query[:100] + "..." if len(self.query) > 100 else self.query
            details.append(f"Query: {query_str}")

        if details:
            return f"{base_msg} ({', '.join(details)})"
        return base_msg


# Exception Mapping Utilities
def map_opensearch_exception(opensearch_exception, execution_context=None):
    """
    Map OpenSearch client exceptions to appropriate DB-API exceptions.

    Args:
        opensearch_exception: The OpenSearch exception to map
        execution_context: Optional dict with execution context (query, host, etc.)

    Returns:
        Appropriate DB-API exception instance
    """
    execution_context = execution_context or {}

    # If the exception is already a DB-API Error, return it as-is to avoid double-wrapping
    if isinstance(opensearch_exception, Error):
        return opensearch_exception

    # Handle opensearch-py exceptions
    try:
        from opensearchpy import AuthenticationException, AuthorizationException, ConflictError
        from opensearchpy import ConnectionError as OSConnectionError
        from opensearchpy import NotFoundError, RequestError, SSLError, TransportError
    except ImportError:
        # If opensearch-py is not available, handle as generic exception
        return OperationalError(f"OpenSearch error: {str(opensearch_exception)}")

    if isinstance(opensearch_exception, (OSConnectionError, SSLError)):
        host = execution_context.get("host", "unknown")
        port = execution_context.get("port", "unknown")
        return OpenSearchConnectionError(
            f"Failed to connect to OpenSearch: {str(opensearch_exception)}",
            host=host,
            port=port,
            execution_context=execution_context,
        )

    elif isinstance(opensearch_exception, (AuthenticationException, AuthorizationException)):
        auth_method = execution_context.get("auth_method", "unknown")
        host = execution_context.get("host", "unknown")
        return AuthenticationError(
            f"Authentication failed: {str(opensearch_exception)}",
            auth_method=auth_method,
            host=host,
            execution_context=execution_context,
        )

    elif isinstance(opensearch_exception, RequestError):
        error_info = getattr(opensearch_exception, "info", None)
        error_type = "unknown"
        if isinstance(error_info, dict):
            error_obj = error_info.get("error", {})
            if isinstance(error_obj, dict):
                error_type = error_obj.get("type", "unknown")

        if error_type in ["parsing_exception", "sql_parse_exception"]:
            return ProgrammingError(f"SQL parsing error: {str(opensearch_exception)}")
        elif error_type in ["verification_exception"]:
            return InvalidParameterError(f"Parameter validation error: {str(opensearch_exception)}")
        else:
            query = execution_context.get("query")
            return QueryExecutionError(
                f"Query execution failed: {str(opensearch_exception)}",
                query=query,
                error_type=error_type,
            )

    elif isinstance(opensearch_exception, NotFoundError):
        return DataError(f"Resource not found: {str(opensearch_exception)}")

    elif isinstance(opensearch_exception, ConflictError):
        return IntegrityError(f"Conflict error: {str(opensearch_exception)}")

    elif isinstance(opensearch_exception, TransportError):
        # Check if it's a transient error
        status_code = getattr(opensearch_exception, "status_code", None)
        if status_code in [429, 502, 503, 504]:  # Rate limiting or server errors
            return TransientError(
                f"Transient error: {str(opensearch_exception)}",
                execution_context=execution_context,
            )
        else:
            return OperationalError(f"Transport error: {str(opensearch_exception)}")

    else:
        # Default to OperationalError for unknown exception types
        return OperationalError(f"OpenSearch error: {str(opensearch_exception)}")


def handle_opensearch_error(func):
    """
    Decorator to automatically map OpenSearch exceptions to DB-API exceptions.

    Usage:
        @handle_opensearch_error
        def some_opensearch_method(self):
            # Method that calls OpenSearch operations
            pass
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Error:
            # Re-raise DB-API exceptions as-is
            raise
        except Exception as e:
            # Map OpenSearch exceptions and re-raise
            mapped_exception = map_opensearch_exception(e)
            raise mapped_exception from e

    return wrapper
