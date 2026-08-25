import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional, TypedDict, Union
from uuid import uuid4

import sagemaker_studio.utils.sql_handler as sql_handler
from sagemaker_studio.connections.connection import SUPPORTED_IRC_GLUE_CONNECTION_TYPES, Connection
from sagemaker_studio.connections.helper_factory import HelperFactory
from sagemaker_studio.project import Project
from sagemaker_studio.sql_engine.sql_executor import ErrorStrategy
from sagemaker_studio.utils._sql_cache import ConnectionCache, ManagedConnection


class ConnectionConfig(TypedDict, total=False):
    """Connection configuration.

    Attributes:
        type: Connection type (e.g., 'spark')
    """

    type: str


logger = logging.getLogger(__name__)
logger.info("Importing sqlutils")

_project = None
_duckdb = None
_sql_executor = None

# Module-level state for query history metadata.
# Stores lightweight metadata from the last SQL execution so the kernel
# can include it in the execute_reply. Cleared at the start of each execution.
_last_sql_execution_metadata = None

# Module-level singleton instance (persists in kernel namespace)
_connection_cache = ConnectionCache()


def _make_cache_key(connection_id: Optional[str], connection_name: Optional[str], **kwargs) -> str:
    """Create cache key from connection identifier and relevant kwargs.

    Args:
        connection_id: Connection ID
        connection_name: Connection name
        **kwargs: Additional configuration parameters

    Returns:
        str: Composite cache key incorporating connection identifier and relevant config
    """
    base_key = connection_id or connection_name or "default"

    # Only include kwargs that affect engine configuration
    relevant_keys = ["catalog_name", "schema_name", "database_name"]
    config_parts = [f"{k}={kwargs[k]}" for k in relevant_keys if k in kwargs]

    if config_parts:
        return f"{base_key}::{':'.join(sorted(config_parts))}"
    return base_key


def _get_or_create_connection(
    connection_id: Optional[str],
    connection_name: Optional[str],
    dz_conn: Connection,
    persist_session: bool,
    **kwargs,
) -> Optional[ManagedConnection]:
    """
    Get cached connection or create new one.

    Returns:
        Optional[ManagedConnection]: Connection object with engine and optional connection.
            - connection will be None if persist_session=False (non-persisted mode)
            - Returns None if engine creation fails
    """
    cache_key = _make_cache_key(connection_id, connection_name, **kwargs)

    # Try cache first
    if persist_session and cache_key:
        cached = _connection_cache.get(cache_key)
        if cached:
            return cached

    # Create new engine
    engine = _get_engine_from_connection(
        dz_conn, connection_id=connection_id, connection_name=connection_name, **kwargs
    )

    if not engine:
        return None

    # For persisted sessions, create and cache connection
    if persist_session and cache_key:
        conn = engine.connect()
        managed_conn = ManagedConnection(
            engine=engine, connection=conn, id=str(uuid4()), cache_key=cache_key
        )
        _connection_cache.put(cache_key, managed_conn)
        return managed_conn

    # For non-persisted sessions, return ephemeral ManagedConnection
    return ManagedConnection(engine=engine, connection=None, id=str(uuid4()), cache_key=cache_key)


def sql(
    query: str,
    parameters: Optional[Union[Dict[str, Any], List[str]]] = None,
    connection_id: Optional[str] = None,
    connection_name: Optional[str] = None,
    connection: Optional[ConnectionConfig] = None,
    persist_session: bool = True,
    **kwargs,
):
    """
    Execute a SQL query and return the result as a DataFrame.

    Supports session persistence (default enabled) for connection reuse across calls,
    enabling temporary tables, transaction state, and automatic credential refresh.

    Args:
        query (str): The SQL query to execute.
        parameters (Optional[Union[Dict[str, Any], List[str]]]): Optional parameters for the query.
        connection_id (Optional[str]): The ID of the DataZone connection to use for the query.
        connection_name (Optional[str]): The name of the DataZone connection to use for the query.
        connection (Optional[ConnectionConfig]): Connection details including type (e.g., {"type": "spark"}).
        persist_session: Cache and reuse connection (default True).

    Returns:
        DataFrame: Result of the SQL query execution.

    Note:
        Use close_connection() or close_all_connections() to close cached connections.

    Raises:
        RuntimeError: If Project is not initialized when using connection_name or if there's an error executing the SQL query.
    """
    if not query or not query.strip():
        return None

    if _is_spark_connection(connection):
        spark = _ensure_spark()
        return spark.sql(query)

    resolved_dz_conn = _resolve_connection(connection_id, connection_name)
    if resolved_dz_conn and resolved_dz_conn.type in SUPPORTED_IRC_GLUE_CONNECTION_TYPES:
        spark = _ensure_spark()
        return _execute_irc_connection_query(query, resolved_dz_conn)

    # adding args anyway as we will filter out necessary args to pass down based on engine type
    _apply_athena_context(query, kwargs)

    cached = _get_or_create_connection(
        connection_id, connection_name, resolved_dz_conn, persist_session, **kwargs
    )

    if cached:
        result = next(
            _ensure_sql_executor().execute(
                cached.engine,
                query,
                connection=cached.connection,  # May be None for non-persisted
                parameters=parameters,
            )
        )
        return result.result
    else:
        # Execute query locally using DuckDB if no connection specified
        return (lambda x: x.df() if x else None)(_ensure_duckdb().sql(query))


def sql_stream(
    query: str,
    parameters: Optional[Union[Dict[str, Any], List[str]]] = None,
    connection_id: Optional[str] = None,
    connection_name: Optional[str] = None,
    connection: Optional[ConnectionConfig] = None,
    error_strategy: str = ErrorStrategy.STOP_ON_ERROR,
    persist_session: bool = True,
    **kwargs,
):
    """
    Execute SQL statements and stream results progressively.

    Supports session persistence (default enabled) for connection reuse across calls,
    enabling temporary tables, transaction state, and automatic credential refresh.

    Args:
        query (str): The SQL query to execute (can contain multiple statements).
        parameters (Optional[Union[Dict[str, Any], List[str]]]): Optional parameters for the query.
        connection_id (Optional[str]): The ID of the DataZone connection to use for the query.
        connection_name (Optional[str]): The name of the DataZone connection to use for the query.
        connection (Optional[ConnectionConfig]): Connection details including type (e.g., {"type": "spark"}).
        error_strategy (str): Error handling strategy - STOP_ON_ERROR (default) or CONTINUE_ON_ERROR.
        persist_session: Cache and reuse connection (default True).

    Returns:
        Generator[ExecutionResult]: Generator yielding ExecutionResult for each statement.

    Note:
        Use close_connection() or close_all_connections() to close cached connections.

    Raises:
        RuntimeError: If Project is not initialized when using connection_name or if there's an error executing the SQL query.
    """
    if not query or not query.strip():
        return iter([])

    if _is_spark_connection(connection):
        from sagemaker_studio.sql_engine.spark_transformer import SparkTransformer
        from sagemaker_studio.sql_engine.sql_executor import SqlExecutor

        spark = _ensure_spark()
        statements = SparkTransformer.split_query(query)

        # Force schema resolution to catch errors eagerly (e.g., TABLE_OR_VIEW_NOT_FOUND).
        # Without this, spark.sql() is lazy and returns successfully even for invalid tables
        # the error only surfaces later in IPython's display formatter where it's swallowed,
        # causing execute_reply to return OK while an error message appears on iopub.
        def _spark_executor(stmt):
            df = spark.sql(stmt)
            df.schema
            return df

        return _stream_and_capture_metadata(
            SqlExecutor.execute_statements(
                statements,
                _spark_executor,
                error_strategy,
            ),
            connection_type="SPARK",
        )

    resolved_dz_conn = _resolve_connection(connection_id, connection_name)
    if resolved_dz_conn and resolved_dz_conn.type in SUPPORTED_IRC_GLUE_CONNECTION_TYPES:
        from sagemaker_studio.sql_engine.spark_transformer import SparkTransformer
        from sagemaker_studio.sql_engine.sql_executor import SqlExecutor

        spark = _ensure_spark()
        statements = SparkTransformer.split_query(query)

        def execute_stmt(stmt):
            return _execute_irc_connection_query(stmt, resolved_dz_conn)

        return SqlExecutor.execute_statements(
            statements,
            execute_stmt,
            error_strategy,
        )

    # adding args anyway as we will filter out necessary args to pass down based on engine type
    _apply_athena_context(query, kwargs)

    cached = _get_or_create_connection(
        connection_id, connection_name, resolved_dz_conn, persist_session, **kwargs
    )

    if cached:
        conn_type = cached.engine.get_execution_options().get("connection_type", "")
        return _stream_and_capture_metadata(
            _ensure_sql_executor().execute(
                cached.engine,
                query,
                connection=cached.connection,  # May be None for non-persisted
                parameters=parameters,
                error_strategy=error_strategy,
            ),
            connection_id=connection_id,
            connection_type=conn_type,
        )
    else:
        from sagemaker_studio.sql_engine.duckdb_transformer import DuckDBTransformer
        from sagemaker_studio.sql_engine.sql_executor import SqlExecutor

        statements = DuckDBTransformer.split_query(query)
        return _stream_and_capture_metadata(
            SqlExecutor.execute_statements(
                statements,
                lambda stmt: (lambda x: x.df() if x else None)(_ensure_duckdb().sql(stmt)),
                error_strategy,
            ),
            connection_type="DUCKDB",
        )


def _execute_irc_connection_query(query: str, resolved_dz_conn: Connection):
    spark = _ensure_spark()
    try:
        df = spark.sql(query)
        df.schema
        return df
    except Exception as e:
        if (
            resolved_dz_conn.type in SUPPORTED_IRC_GLUE_CONNECTION_TYPES
            and "org.apache.iceberg.exceptions.NotAuthorizedException" in str(e)
        ):
            # The stored token was rejected, so force a refresh rather than re-reading
            # the same token from the connection's secret.
            spark_catalog_configs = resolved_dz_conn._spark_catalog_configs(
                force_token_refresh=True
            )
            if not spark_catalog_configs:
                raise
            catalog_names = json.loads(spark_catalog_configs["SOURCE_CATALOG_LIST"])
            for catalog_name in catalog_names:
                access_token = spark_catalog_configs["ACCESS_TOKEN"]
                spark.conf.set(f"spark.sql.catalog.{catalog_name}.token", access_token)
            # Force schema resolution like the initial attempt, so a failure of the
            # retried query surfaces here instead of later, lazily.
            retried_df = spark.sql(query)
            retried_df.schema
            return retried_df
        else:
            raise


def sql_stream_with_display(
    query: str,
    dataframe_name: str,
    parameters: Optional[Union[Dict[str, Any], List[str]]] = None,
    connection_id: Optional[str] = None,
    connection_name: Optional[str] = None,
    connection: Optional[ConnectionConfig] = None,
    error_strategy: str = ErrorStrategy.STOP_ON_ERROR,
    **kwargs,
):
    """
    Execute SQL statements, materialise results into the IPython namespace, and display them.

    Each successful result is assigned to the IPython user namespace as
    ``<dataframe_name>_<index>``, displayed, and the consolidated result
    (single DataFrame or list) is stored under ``<dataframe_name>``.

    On error, partial results are saved for debugging and the error is raised.

    Args:
        query (str): The SQL query to execute (can contain multiple statements).
        dataframe_name (str): Variable name prefix for storing results in the IPython namespace.
        parameters (Optional[Union[Dict[str, Any], List[str]]]): Optional parameters for the query.
        connection_id (Optional[str]): The ID of the DataZone connection to use for the query.
        connection_name (Optional[str]): The name of the DataZone connection to use for the query.
        connection (Optional[ConnectionConfig]): Connection details including type (e.g., {"type": "spark"}).
        error_strategy (str): Error handling strategy - STOP_ON_ERROR (default) or CONTINUE_ON_ERROR.

    Raises:
        Exception: If any statement fails, after saving partial results for debugging.
    """
    stream = sql_stream(
        query,
        parameters=parameters,
        connection_id=connection_id,
        connection_name=connection_name,
        connection=connection,
        error_strategy=error_strategy,
        **kwargs,
    )
    _materialise_stream(stream, dataframe_name)


def get_engine(
    connection_id: Optional[str] = None, connection_name: Optional[str] = None, **kwargs
):
    """
    Returns the SQL engine for the specified connection.

    Args:
        connection_id (Optional[str]): The ID of the DataZone connection to get the SQL engine for.
        connection_name (Optional[str]): The name of the DataZone connection to get the SQL engine for.

    Returns:
        The SQL engine instance for executing queries.

    Raises:
        ValueError: If multiple connection parameters are provided
        RuntimeError: If project initialization fails or if SQL is not supported for this connection type.
    """

    provided_params = sum(x is not None for x in [connection_id, connection_name])
    if provided_params == 0:
        # No connection provided, use local DuckDB engine
        return None
    if provided_params > 1:
        raise ValueError("Only one of connection_id or connection_name should be provided")

    conn = _resolve_connection(connection_id, connection_name)
    return _get_engine_from_connection(
        conn, connection_id=connection_id, connection_name=connection_name, **kwargs
    )


def _create_credential_provider(credential_getter):
    """Factory that creates a credential provider from a getter function."""

    def credential_provider():
        creds = credential_getter()
        expiry = creds.expiration

        if not expiry:
            # Default to 15 min from now if no expiry provided
            expiry = datetime.now(timezone.utc) + timedelta(minutes=15)

        return {
            "access_key_id": creds.access_key_id,
            "secret_access_key": creds.secret_access_key,
            "session_token": creds.session_token,
            "expiration": expiry.isoformat(),
        }

    return credential_provider


def _resolve_connection(connection_id: str, connection_name: str):
    """Resolve a connection by name or id. Returns None if neither is provided."""
    if not connection_name and not connection_id:
        return None
    project = _ensure_project()
    if not project:
        raise RuntimeError("Project is not initialized.")
    if connection_name:
        return project.connection(connection_name)
    return project.connection(id=connection_id)


def _get_engine_from_connection(
    conn: Connection,
    connection_id: Optional[str] = None,
    connection_name: Optional[str] = None,
    **kwargs,
):
    """Create a SQL engine from an already-resolved connection. Returns None if conn is None."""
    if conn is None:
        return None

    sql_executor = _ensure_sql_executor()

    if conn.type not in sql_executor.get_supported_connection_types():
        raise RuntimeError(
            f"SQL is not supported for connection type {conn.type}. Supported types are {', '.join(sql_executor.get_supported_connection_types())}."
        )

    sql_helper = HelperFactory.get_sql_helper(conn.type)

    # Create credential provider that refreshes credentials
    if connection_id or connection_name:
        # Re-fetch connection for fresh credentials
        def credential_getter():
            return _resolve_connection(connection_id, connection_name).connection_creds

    else:
        # Fall back to cached credentials when identifiers not available
        def credential_getter():
            return conn.connection_creds

    kwargs["credential_provider"] = _create_credential_provider(credential_getter)

    connection_config = sql_helper.to_sql_config(conn, **kwargs)

    return sql_executor.create_engine(conn.type, connection_config)


def _apply_athena_context(query: str, kwargs: dict) -> None:
    """Extract catalog/database from the query and inject into kwargs for the engine.

    If catalog_name and schema_name are already passed from older UI logic, this is a no-op.
    """
    if "catalog_name" in kwargs and "schema_name" in kwargs:
        return

    execution_ctx = sql_handler.get_execution_context(query)
    catalog = execution_ctx.get("catalog")
    database = execution_ctx.get("database")
    logger.debug(f"Found catalog {catalog} database: {database}")
    if catalog and database:
        kwargs["catalog_name"] = catalog
        kwargs["schema_name"] = database


def list_connections() -> List[Dict[str, Any]]:
    """
    List all active persistent database connections.

    Returns:
        List[Dict[str, Any]]: List of connection details including:
            - id: Unique identifier for this cache entry (use with close_connection)
            - cache_key: Full cache key including configuration
            - created_at: When the connection was created
            - last_used: When the connection was last used

    Example:
        >>> connections = list_connections()
        >>> for conn in connections:
        ...     print(f"ID: {conn['id']}, Key: {conn['cache_key']}")
        >>> # Close a specific connection
        >>> close_connection(id=connections[0]['id'])
    """
    return [
        {
            "id": mc.id,
            "cache_key": mc.cache_key,
            "created_at": mc.created_at,
            "last_used": mc.last_used,
        }
        for mc in _connection_cache._cache.values()
    ]


def close_connection(id: str) -> bool:
    """
    Close a specific persistent database connection by its unique ID.

    Args:
        id (str): The unique identifier of the connection to close.
                  Obtain this from list_connections().

    Returns:
        bool: True if connection was found and closed, False if not found.

    Example:
        >>> connections = list_connections()
        >>> close_connection(id=connections[0]['id'])
        True
    """
    return _connection_cache.remove_by_id(id)


def close_all_connections() -> int:
    """
    Close all persistent database connections.

    Returns:
        int: Number of connections closed.

    Example:
        >>> count = close_all_connections()
        >>> print(f"Closed {count} connections")
    """
    return _connection_cache.clear()


def _ensure_project():
    """Initialize Project on demand"""
    global _project
    if _project is None:
        try:
            _project = Project()
        except Exception:
            _project = False
    return _project


def _ensure_duckdb():
    """Initialize Project on demand"""
    global _duckdb
    if _duckdb is None:
        import duckdb as _duckdb

        # Refer to https://duckdb.org/duckdb-docs.pdf
        _duckdb.sql("SET python_scan_all_frames = true;")
        # Refer to https://duckdb.org/docs/stable/core_extensions/httpfs/s3api#credential_chain-provider
        _duckdb.sql("CREATE SECRET (TYPE s3, PROVIDER credential_chain);")
    return _duckdb


def _ensure_sql_executor():
    """Initialize SqlExecutor on demand"""
    global _sql_executor
    if _sql_executor is None:
        from sagemaker_studio.sql_engine.sql_executor import SqlExecutor

        _sql_executor = SqlExecutor()
    return _sql_executor


def _ensure_spark():
    """Get Spark session from kernel namespace"""
    try:
        from IPython import get_ipython

        ipython = get_ipython()
        if ipython is None:
            raise RuntimeError("IPython kernel not available")

        spark = ipython.user_ns.get("spark")
        if spark is None:
            raise RuntimeError("Spark session not initialized in kernel namespace")

        return spark
    except ImportError:
        raise RuntimeError("IPython not available - Spark execution requires Jupyter kernel")


def _is_spark_connection(connection: Optional[ConnectionConfig] = None) -> bool:
    """Check if connection dict specifies Spark"""
    if not connection:
        return False

    conn_type = connection.get("type", "")
    if conn_type == "spark":
        return True
    elif conn_type:
        raise ValueError(
            f"connection object is currently supported for Spark only. "
            f"Use connection_id or connection_name for other engines. Got type: {conn_type}"
        )
    return False


def _materialise_stream(stream, dataframe_name: str):
    """Consume a result stream, display/assign results in IPython, and return consolidated output."""
    logger.info("display/assign results")
    from IPython import get_ipython
    from IPython.display import display

    ip = get_ipython()

    results: list = []
    for result in stream:
        if result.status == "success":
            display(result.result)
            results.append(result)
        else:
            # Save partial results for debugging before raising
            if len(results) > 0:
                for r in results:
                    ip.user_ns[f"{dataframe_name}_{r.statement_index}"] = r.result
            raise Exception(result.error)

    # No results — nothing to assign
    if not results:
        return

    # All statements succeeded - save indexed vars if multiple results
    if len(results) > 1:
        for r in results:
            ip.user_ns[f"{dataframe_name}_{r.statement_index}"] = r.result

    # Save main variable
    final = results[0].result if len(results) == 1 else [r.result for r in results]
    ip.user_ns[dataframe_name] = final


def _stream_and_capture_metadata(
    stream: Generator,
    connection_id: Optional[str] = None,
    connection_type: Optional[str] = None,
) -> Generator:
    """Wrap a result stream to capture per-statement execution metadata.

    Yields results unchanged while storing lightweight metadata (statement text,
    status, engine-specific info) on the module for downstream consumers.
    Writes incrementally so metadata is available even if iteration is interrupted.

    Note: state reset happens eagerly at call time. The actual iteration is
    delegated to an inner generator so callers don't see stale metadata between
    invocation and the first next() call.
    """
    global _last_sql_execution_metadata
    _last_sql_execution_metadata = []  # Eagerly reset on call

    def _inner():
        for result in stream:
            entry = {
                "statement_index": getattr(result, "statement_index", 0),
                "statement": getattr(result, "statement", ""),
                "status": getattr(result, "status", "success"),
                "execution_metadata": getattr(result, "execution_metadata", None),
            }
            if getattr(result, "error", None):
                entry["error"] = result.error
            if connection_id:
                entry["connection_id"] = connection_id
            if connection_type:
                entry["connection_type"] = connection_type
            _last_sql_execution_metadata.append(entry)
            yield result

    return _inner()


logger.info("Finished importing sqlutils")
