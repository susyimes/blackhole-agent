"""
DB-API 2.0 compatible interface for Redshift Data API.

This module provides a DB-API 2.0 compatible interface that uses
the AWS Redshift Data API for executing SQL statements.
"""

from .client import RedshiftDataAPIClient, create_client
from .connection import Connection
from .connection_params import ConnectionParams, create_connection_params, parse_connection_url
from .cursor import Cursor
from .exceptions import (
    ClusterNotFoundError,
    DatabaseError,
    DataError,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
    StatementLimitExceededError,
    StatementTimeoutError,
    Warning,
)

# DB-API 2.0 module attributes
apilevel = "2.0"
threadsafety = 2  # Threads may share the module and connections
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
    "StatementTimeoutError",
    "StatementLimitExceededError",
    "ClusterNotFoundError",
    "Connection",
    "Cursor",
    "ConnectionParams",
    "parse_connection_url",
    "create_connection_params",
    "RedshiftDataAPIClient",
    "create_client",
    "connect",
    "apilevel",
    "threadsafety",
    "paramstyle",
]


def connect(cluster_identifier, database_name, db_user, region, **kwargs):
    """
    Create a connection to Redshift using the Data API.

    Args:
        cluster_identifier: The Redshift cluster identifier
        database_name: The database name
        db_user: The database user name
        region: The AWS region
        **kwargs: Additional connection parameters

    Returns:
        Connection: A DB-API 2.0 compatible connection object
    """
    return Connection(
        cluster_identifier=cluster_identifier,
        database_name=database_name,
        db_user=db_user,
        region=region,
        **kwargs
    )
