"""
DB-API 2.0 compatible interface for OpenSearch.

This module provides a DB-API 2.0 compatible interface that uses
the OpenSearch Python client for executing SQL statements.
"""

from .client import OpenSearchClient, create_client
from .connection import Connection
from .connection_params import ConnectionParams, create_connection_params, parse_connection_url
from .cursor import Cursor
from .exceptions import (
    AuthenticationError,
    DatabaseError,
    DataError,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    InvalidParameterError,
    NotSupportedError,
    OpenSearchConnectionError,
    OperationalError,
    ProgrammingError,
    QueryExecutionError,
    TransientError,
    Warning,
)

# DB-API 2.0 module attributes
apilevel = "2.0"
threadsafety = 1  # Threads may share the module but not connections
paramstyle = "named"

__all__ = [
    "Error",
    "Warning",
    "InterfaceError",
    "DatabaseError",
    "DataError",
    "OperationalError",
    "IntegrityError",
    "InternalError",
    "ProgrammingError",
    "NotSupportedError",
    "AuthenticationError",
    "OpenSearchConnectionError",
    "QueryExecutionError",
    "InvalidParameterError",
    "TransientError",
    "Connection",
    "Cursor",
    "ConnectionParams",
    "parse_connection_url",
    "create_connection_params",
    "OpenSearchClient",
    "create_client",
    "connect",
    "apilevel",
    "threadsafety",
    "paramstyle",
]


def connect(host="localhost", port=443, index="_all", **kwargs):
    """
    Create a connection to OpenSearch.

    Args:
        host: The OpenSearch host
        port: The OpenSearch port
        index: The default index to query
        **kwargs: Additional connection parameters

    Returns:
        Connection: A DB-API 2.0 compatible connection object
    """
    return Connection(host=host, port=port, index=index, **kwargs)
