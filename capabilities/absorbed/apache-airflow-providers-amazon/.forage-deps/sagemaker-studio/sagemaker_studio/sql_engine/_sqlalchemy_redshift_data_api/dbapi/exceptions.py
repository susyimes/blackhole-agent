"""
DB-API 2.0 exception hierarchy and Redshift Data API specific exceptions.

This module defines the standard DB-API 2.0 exception hierarchy plus
additional exceptions specific to the Redshift Data API.
"""


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


# Redshift Data API Specific Exceptions
class StatementTimeoutError(OperationalError):
    """Exception raised when a Data API statement execution times out."""

    def __init__(self, message, statement_id=None, timeout_seconds=None, execution_context=None):
        super().__init__(message)
        self.statement_id = statement_id
        self.timeout_seconds = timeout_seconds
        self.execution_context = execution_context or {}

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.statement_id:
            details.append(f"Statement ID: {self.statement_id}")
        if self.timeout_seconds:
            details.append(f"Timeout: {self.timeout_seconds}s")
        if self.execution_context:
            for key, value in self.execution_context.items():
                details.append(f"{key}: {value}")

        if details:
            return f"{base_msg} ({', '.join(details)})"
        return base_msg


class StatementLimitExceededError(OperationalError):
    """Exception raised when Data API statement limits are exceeded."""

    def __init__(
        self, message, limit_type=None, current_count=None, max_count=None, execution_context=None
    ):
        super().__init__(message)
        self.limit_type = limit_type
        self.current_count = current_count
        self.max_count = max_count
        self.execution_context = execution_context or {}

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.limit_type:
            details.append(f"Limit type: {self.limit_type}")
        if self.current_count is not None and self.max_count is not None:
            details.append(f"Usage: {self.current_count}/{self.max_count}")
        if self.execution_context:
            for key, value in self.execution_context.items():
                details.append(f"{key}: {value}")

        if details:
            return f"{base_msg} ({', '.join(details)})"
        return base_msg


class ClusterNotFoundError(OperationalError):
    """Exception raised when the specified Redshift cluster is not found."""

    def __init__(
        self, message, cluster_identifier=None, workgroup_name=None, execution_context=None
    ):
        super().__init__(message)
        self.cluster_identifier = cluster_identifier
        self.workgroup_name = workgroup_name
        self.execution_context = execution_context or {}

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.cluster_identifier:
            details.append(f"Cluster: {self.cluster_identifier}")
        if self.workgroup_name:
            details.append(f"Workgroup: {self.workgroup_name}")
        if self.execution_context:
            for key, value in self.execution_context.items():
                details.append(f"{key}: {value}")

        if details:
            return f"{base_msg} ({', '.join(details)})"
        return base_msg


class AuthenticationError(OperationalError):
    """Exception raised for authentication-related errors."""

    def __init__(self, message, auth_method=None, region=None, execution_context=None):
        super().__init__(message)
        self.auth_method = auth_method
        self.region = region
        self.execution_context = execution_context or {}

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.auth_method:
            details.append(f"Auth method: {self.auth_method}")
        if self.region:
            details.append(f"Region: {self.region}")
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


class StatementExecutionError(OperationalError):
    """Exception raised when a Data API statement execution fails."""

    def __init__(self, message, statement_id=None):
        super().__init__(message)
        self.statement_id = statement_id

    def __str__(self):
        base_msg = super().__str__()
        if self.statement_id:
            return f"{base_msg} (Statement ID: {self.statement_id})"
        return base_msg


# Exception Mapping Utilities
def map_boto3_exception(boto3_exception, execution_context=None):
    """
    Map boto3 ClientError exceptions to appropriate DB-API exceptions.

    Args:
        boto3_exception: The boto3 exception to map
        execution_context: Optional dict with execution context (statement_id, sql, etc.)

    Returns:
        Appropriate DB-API exception instance
    """

    from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

    execution_context = execution_context or {}

    if isinstance(boto3_exception, (NoCredentialsError, PartialCredentialsError)):
        auth_method = execution_context.get("auth_method", "unknown")
        region = execution_context.get("region")
        return AuthenticationError(
            f"AWS credentials error: {str(boto3_exception)}",
            auth_method=auth_method,
            region=region,
            execution_context=execution_context,
        )

    if not isinstance(boto3_exception, ClientError):
        # For non-ClientError boto3 exceptions, wrap in OperationalError
        return OperationalError(f"AWS service error: {str(boto3_exception)}")

    error_code = boto3_exception.response.get("Error", {}).get("Code", "")
    error_message = boto3_exception.response.get("Error", {}).get("Message", str(boto3_exception))
    request_id = boto3_exception.response.get("ResponseMetadata", {}).get("RequestId")

    # Add AWS request ID to execution context
    if request_id:
        execution_context = execution_context.copy()
        execution_context["aws_request_id"] = request_id

    # Map specific AWS error codes to DB-API exceptions
    if error_code in [
        "UnauthorizedOperation",
        "AccessDenied",
        "InvalidUserID.NotFound",
        "TokenRefreshRequired",
    ]:
        auth_method = execution_context.get("auth_method", "unknown")
        region = execution_context.get("region")
        return AuthenticationError(
            error_message,
            auth_method=auth_method,
            region=region,
            execution_context=execution_context,
        )

    elif error_code == "ClusterNotFoundFault":
        cluster_id = _extract_cluster_id_from_message(error_message) or execution_context.get(
            "cluster_identifier"
        )
        return ClusterNotFoundError(
            error_message, cluster_identifier=cluster_id, execution_context=execution_context
        )

    elif error_code == "WorkgroupNotFoundFault":
        workgroup_name = execution_context.get("workgroup_name")
        return ClusterNotFoundError(
            error_message, workgroup_name=workgroup_name, execution_context=execution_context
        )

    elif error_code in ["ValidationException", "InvalidParameterValue", "MissingParameter"]:
        return InvalidParameterError(error_message, execution_context=execution_context)

    elif error_code == "StatementTimeoutException":
        statement_id = _extract_statement_id_from_message(error_message) or execution_context.get(
            "statement_id"
        )
        timeout_seconds = execution_context.get("timeout_seconds")
        return StatementTimeoutError(
            error_message,
            statement_id=statement_id,
            timeout_seconds=timeout_seconds,
            execution_context=execution_context,
        )

    elif error_code in ["StatementExecutionException", "QueryExecutionException"]:
        statement_id = _extract_statement_id_from_message(error_message) or execution_context.get(
            "statement_id"
        )
        return StatementExecutionError(error_message, statement_id=statement_id)

    elif error_code == "ActiveStatementsExceededException":
        return StatementLimitExceededError(
            error_message, limit_type="active_statements", execution_context=execution_context
        )

    elif error_code == "BatchExecuteStatementException":
        return ProgrammingError(error_message)

    elif error_code == "DataException":
        return DataError(error_message)

    elif error_code == "IntegrityConstraintViolationException":
        return IntegrityError(error_message)

    elif error_code == "InternalServerException":
        return InternalError(error_message)

    elif error_code in ["ServiceUnavailableException", "ThrottlingException"]:
        # These are transient errors that can be retried
        retry_after = _extract_retry_after_from_response(boto3_exception.response)
        return TransientError(
            error_message, retry_after=retry_after, execution_context=execution_context
        )

    elif error_code == "UnsupportedOperationException":
        return NotSupportedError(error_message)

    else:
        # Default to OperationalError for unknown error codes
        return OperationalError(f"{error_code}: {error_message}")


def _extract_retry_after_from_response(response):
    """Extract retry-after value from AWS response headers."""
    headers = response.get("ResponseMetadata", {}).get("HTTPHeaders", {})
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after:
        try:
            return int(retry_after)
        except (ValueError, TypeError):
            pass
    return None


def _extract_cluster_id_from_message(message):
    """Extract cluster identifier from error message if present."""
    import re

    # First try "Cluster: identifier" format
    match = re.search(r"cluster:\s*([a-zA-Z0-9_-]+)", message, re.IGNORECASE)
    if match:
        return match.group(1)

    # Then try "cluster identifier" format, but exclude common words
    match = re.search(r"cluster\s+([a-zA-Z0-9_-]+)(?=\s+(?:not|is|does))", message, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def _extract_statement_id_from_message(message):
    """Extract statement ID from error message if present."""
    import re

    # First try "Statement: identifier" format
    match = re.search(r"statement:\s*([a-zA-Z0-9-]+)", message, re.IGNORECASE)
    if match:
        return match.group(1)

    # Then try "statement identifier" format, but exclude common words
    match = re.search(
        r"statement\s+([a-zA-Z0-9-]+)(?=\s+(?:timed|failed|is))", message, re.IGNORECASE
    )
    if match:
        return match.group(1)

    return None


def handle_redshift_data_api_error(func):
    """
    Decorator to automatically map boto3 exceptions to DB-API exceptions.

    Usage:
        @handle_redshift_data_api_error
        def some_data_api_method(self):
            # Method that calls boto3 redshift-data operations
            pass
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Error:
            # Re-raise DB-API exceptions as-is
            raise
        except Exception as e:
            # Map boto3 exceptions and re-raise
            mapped_exception = map_boto3_exception(e)
            raise mapped_exception from e

    return wrapper
