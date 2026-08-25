import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Generator, List, Optional, Type, Union

from pandas import DataFrame
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from .athena_transformer import AthenaTransformer
from .big_query_transformer import BigQueryTransformer
from .database_resource import DatabaseResource
from .database_transformer import DatabaseTransformer, SqlStatement
from .documentdb_transformer import DocumentDBTransformer
from .dynamodb_transformer import DynamoDBTransformer
from .mssql_transformer import MSSQLTransformer
from .mysql_transformer import MySQLTransformer
from .opensearch_transformer import OpenSearchTransformer
from .oracle_transformer import OracleTransformer
from .postgresql_transformer import PostgreSQLTransformer
from .redshift_transformer import RedshiftTransformer
from .resource_fetching_definition import FetchMode, SQLAlchemyMetadataAction
from .snowflake_transformer import SnowflakeTransformer
from .vertica_transformer import VerticaTransformer
from .workday_transformer import WorkdayTransformer

try:
    from .teradata_transformer import _TERADATA_DEPS_AVAILABLE as _TERADATA_AVAILABLE
    from .teradata_transformer import (
        TeraDataTransformer,
    )
except ImportError:  # pragma: no cover
    _TERADATA_AVAILABLE = False

logger = logging.getLogger(__name__)


class ErrorStrategy(Enum):
    """Strategy for handling errors during multi-statement execution."""

    STOP_ON_ERROR = "stop_on_error"
    CONTINUE_ON_ERROR = "continue_on_error"


class ExecutionStatus(Enum):
    """Status of statement execution."""

    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """Result of executing a single SQL statement.

    Attributes:
        statement_index: Zero-based index of the statement in the query.
        statement: The SQL statement text that was executed.
        statement_type: Type of SQL statement (SELECT, INSERT, UPDATE, etc.).
        result: The result field can contain different types depending on the execution engine:
            - pandas.DataFrame: For SQL engines (Redshift, Athena, etc.) and DuckDB
            - pyspark.sql.DataFrame: For Spark connections
            - int: Row count for DML operations (INSERT, UPDATE, DELETE)
        error: Error message if execution failed, None on success.
        status: Execution status (SUCCESS or ERROR).
        rows_affected: Number of rows affected by DML operations.
        execution_time: Execution time in seconds (if measured).
        execution_metadata: Engine-specific metadata returned by the database API.
            Each engine provides different fields. Examples:
            - Redshift: {"statement_id": "...", "session_id": "...", "records_updated": N}
            - Athena: {"query_execution_id": "...", "data_scanned_bytes": N, "execution_time_ms": N}
            - Other engines: None or {} until support is added.
    """

    statement_index: int
    statement: str
    statement_type: str
    result: Optional[Any] = None  # Can be pandas DataFrame, Spark DataFrame, or int
    error: Optional[str] = None
    status: str = ExecutionStatus.SUCCESS.value
    rows_affected: Optional[int] = None
    execution_time: Optional[float] = None
    execution_metadata: Optional[Dict[str, Any]] = None


@dataclass
class SingleStatementResult:
    """Internal result from _execute_single with data and metadata separated.

    This is the structured return type from _execute_single() that feeds into
    execute_statements() to build the public ExecutionResult.
    """

    result: Any  # DataFrame or int (rowcount)
    execution_metadata: Optional[Dict[str, Any]] = None


class SqlExecutor:
    MAX_STATEMENTS = 10

    def __init__(self):
        self._transformer_classes: Dict[str, Type[DatabaseTransformer]] = {
            "REDSHIFT": RedshiftTransformer,
            "ATHENA": AthenaTransformer,
            "MYSQL": MySQLTransformer,
            "SNOWFLAKE": SnowflakeTransformer,
            "BIGQUERY": BigQueryTransformer,
            "DYNAMODB": DynamoDBTransformer,
            "DOCUMENTDB": DocumentDBTransformer,
            "SQLSERVER": MSSQLTransformer,
            "POSTGRESQL": PostgreSQLTransformer,
            "OPENSEARCH": OpenSearchTransformer,
            "ORACLE": OracleTransformer,
            "VERTICA": VerticaTransformer,
            "WORKDAYLDQ": WorkdayTransformer,
        }
        if _TERADATA_AVAILABLE:
            self._transformer_classes["TERADATA"] = TeraDataTransformer

    @staticmethod
    def execute_statements(
        statements: List[SqlStatement],
        executor_func,
        error_strategy: str = ErrorStrategy.STOP_ON_ERROR,
    ) -> Generator[ExecutionResult, None, None]:
        """Execute multiple statements with error handling.

        The executor_func can return either:
        - A plain result (DataFrame, int, etc.) for simple engines (Spark, DuckDB)
        - A SingleStatementResult for engines that provide metadata (Redshift, Athena)
        """
        if len(statements) > SqlExecutor.MAX_STATEMENTS:
            raise ValueError(
                f"Too many statements: {len(statements)}. Maximum allowed: {SqlExecutor.MAX_STATEMENTS}"
            )

        for i, stmt in enumerate(statements):
            try:
                raw_result = executor_func(stmt.statement)

                # Support both plain results and structured SingleStatementResult
                if isinstance(raw_result, SingleStatementResult):
                    result = raw_result.result
                    execution_metadata = raw_result.execution_metadata
                else:
                    result = raw_result
                    execution_metadata = None

                yield ExecutionResult(
                    statement_index=i,
                    statement=stmt.statement,
                    statement_type=stmt.statement_type,
                    result=result,
                    status=ExecutionStatus.SUCCESS.value,
                    execution_metadata=execution_metadata,
                )
            except Exception as e:
                yield ExecutionResult(
                    statement_index=i,
                    statement=stmt.statement,
                    statement_type=stmt.statement_type,
                    error=str(e),
                    status=ExecutionStatus.ERROR.value,
                )
                if error_strategy == ErrorStrategy.STOP_ON_ERROR:
                    break

    def get_supported_connection_types(self) -> list[str]:
        """
        Returns the supported connection types as a list of strings.
        """
        return [str(key) for key in self._transformer_classes.keys()]

    def _get_transformer(self, connection_type: str) -> Type[DatabaseTransformer]:
        """Get transformer class for the given connection type and configure loggers."""
        if connection_type not in self._transformer_classes:
            if connection_type == "TERADATA" and not _TERADATA_AVAILABLE:
                raise ImportError(
                    "Teradata support requires the 'teradatasql' and 'teradatasqlalchemy' packages. "
                    "Install them with: pip install sagemaker-studio[teradata]"
                )
            raise ValueError(f"Unsupported connection type: {connection_type}")

        transformer = self._transformer_classes[connection_type]
        [
            logging.getLogger(logger_name).setLevel(logging.WARNING)
            for logger_name in transformer.get_loggers()
        ]  # Set loggers to warn

        return transformer

    def create_engine(self, connection_type: str, connection_data: Dict[str, Any]) -> Engine:
        """Create SQLAlchemy engine based on connection type and data."""
        transformer = self._get_transformer(connection_type)

        config = transformer.to_sqlalchemy_config(connection_data)

        if "connection_string" not in config:
            raise ValueError(
                f"Transformer for {connection_type} must return 'connection_string' in config"
            )

        connection_string = config.pop("connection_string")

        return create_engine(connection_string, **config).execution_options(
            connection_type=connection_type
        )

    def execute(
        self,
        engine: Engine,
        query: str,
        parameters: Optional[Union[Dict[str, Any], List[str]]] = None,
        *,
        connection: Optional[Connection] = None,
        error_strategy: str = ErrorStrategy.STOP_ON_ERROR,
    ) -> Generator[ExecutionResult, None, None]:
        """Execute SQL query with optional parameters using provided engine.

        This method supports two connection lifecycle patterns:
        - Auto-managed (connection=None): Creates and closes connection automatically
        - Caller-managed (connection provided): Uses provided connection, caller handles lifecycle

        The query is split into individual statements and executed sequentially. Each statement
        yields an ExecutionResult containing the result data or error information.

        Args:
            engine: SQLAlchemy engine configured for the target database.
            query: SQL query string, may contain multiple statements separated by semicolons.
            connection: Optional SQLAlchemy connection. If None, a new connection is created
                and automatically closed after execution. If provided, the connection remains
                open and must be closed by the caller.
            parameters: Optional query parameters for parameterized queries. Can be a dictionary
                for named parameters or a list for positional parameters.
            error_strategy: Error handling strategy. STOP_ON_ERROR (default) stops execution
                on first error. CONTINUE_ON_ERROR executes remaining statements after errors.

        Yields:
            ExecutionResult: Result for each executed statement in the query.

        Raises:
            SQLAlchemyError: For database-specific errors (table exists, syntax errors, etc.)
            ValueError: If query contains more than MAX_STATEMENTS statements.

        Example:
            >>> # Auto-managed connection
            >>> for result in executor.execute(engine, "SELECT 1; SELECT 2"):
            ...     print(result.result)

            >>> # Caller-managed connection (persistent session)
            >>> conn = engine.connect()
            >>> for result in executor.execute(engine, "CREATE TEMP TABLE t (id INT)", connection=conn):
            ...     pass
            >>> for result in executor.execute(engine, "INSERT INTO t VALUES (1)", connection=conn):
            ...     pass
            >>> conn.close()
        """
        execution_options = engine.get_execution_options()
        connection_type = execution_options.get("connection_type", "UNKNOWN")

        transformer = self._get_transformer(connection_type)
        statements = transformer.split_query(query)

        try:
            # no connection => auto-close after execution
            if connection is None:
                with engine.connect() as conn:
                    yield from self.execute_statements(
                        statements,
                        lambda stmt: self._execute_single(conn, stmt, parameters),
                        error_strategy,
                    )
            # caller manages connection lifecycle
            else:
                yield from self.execute_statements(
                    statements,
                    lambda stmt: self._execute_single(connection, stmt, parameters),
                    error_strategy,
                )

        except SQLAlchemyError:
            raise

    def _execute_single(
        self,
        connection: Connection,
        statement: str,
        parameters: Optional[Union[Dict[str, Any], List[str]]] = None,
    ) -> SingleStatementResult:
        """Execute a single SQL statement and return result with metadata.

        Returns:
            SingleStatementResult containing the query data and engine-specific metadata.
        """
        result = connection.execute(text(statement), parameters or {})

        # Extract metadata BEFORE fetching data — cursor is released after fetchall()
        execution_metadata = None
        connection_type = "UNKNOWN"
        try:
            connection_type = connection.engine.get_execution_options().get(
                "connection_type", "UNKNOWN"
            )
            transformer = self._get_transformer(connection_type)
            execution_metadata = transformer.get_execution_metadata(result.cursor)
        except Exception:
            logger.debug(
                "Failed to extract execution metadata for %s", connection_type, exc_info=True
            )

        # Check if query returns results (SELECT, SHOW, DESCRIBE, etc.)
        if result.returns_rows:
            data = DataFrame(result.fetchall(), columns=result.keys())
        else:
            # For INSERT, UPDATE, DELETE, etc. - return affected row count
            data = result.rowcount

        return SingleStatementResult(result=data, execution_metadata=execution_metadata)

    def get_resources(
        self,
        engine: Engine,
        connection_type: str,
        resource_type: Optional[str],
        parents: Dict[str, str],
    ) -> List[DatabaseResource]:
        """
        Fetch database resources (databases, schemas, tables, or columns).

        This function delegates to a driver-specific SQL helper to obtain a
        `ResourceFetchingDefinition`, then either:
          * uses SQLAlchemy's Inspector to read metadata (schemas/tables/columns), or
          * executes the provided SQL and reads the first column of the result.

        The returned `DatabaseResource` instances use `resource_type` if provided;
        otherwise the helper's `default_type`. Child resource kinds are taken from
        the helper's definition.

        Args:
          resource_type: The kind of resource to fetch. Expected values include
            `"DATABASE"`, `"SCHEMA"`, `"TABLE"`, `"COLUMN"`. If `None`, the helper’s
            `default_type` is used.
          parents: Mapping of required parent identifiers, depending on
            `resource_type`. Typical expectations:
              * `"SCHEMA"`: `{"DATABASE": "<db>"}`.
              * `"TABLE"`: `{"DATABASE": "<db>", "SCHEMA": "<schema>"}`.
              * `"COLUMN"`: `{"DATABASE": "<db>", "SCHEMA": "<schema>", "TABLE": "<table>"}`.
            Exact keys/requirements are determined by the SQL helper’s
            `get_resources_action`.
          connection_id: Optional identifier of the connection to use.
          connection_name: Optional human-friendly name of the connection to use.
          **kwargs: Extra options forwarded to `get_engine`, `_get_connection`, and
            the SQL execution helper (e.g., execution options).

        Returns:
          A list of `DatabaseResource` objects, one per discovered resource name.

        Raises:
          ValueError: If the helper returns an unsupported fetching mode or an
            unsupported SQLAlchemy metadata action.
        """
        transformer = self._get_transformer(connection_type)

        definition = transformer.get_resources_action(resource_type, parents)

        if definition.mode is FetchMode.SQLALCHEMY_METADATA:
            inspector = inspect(engine)
            action = definition.sqlalchemy_action

            if action is SQLAlchemyMetadataAction.GET_SCHEMA_NAMES:
                resource_names = inspector.get_schema_names()

            elif action is SQLAlchemyMetadataAction.GET_TABLE_NAMES:
                schema = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                resource_names = inspector.get_table_names(schema=schema)

            elif action is SQLAlchemyMetadataAction.GET_COLUMN_NAMES:
                schema = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                table = DatabaseTransformer.get_required_resource_parent(parents, "TABLE")
                columns = inspector.get_columns(table_name=table, schema=schema)
                resource_names = [c["name"] for c in columns]

            else:
                raise ValueError(f"Unsupported SQLAlchemy metadata action: {action}")

        elif definition.mode is FetchMode.SQL_EXECUTION:
            # definition.sql is guaranteed by __post_init__
            try:
                result = next(
                    self.execute(engine, definition.sql, parameters=definition.sql_parameters)
                )
            except StopIteration:
                raise ValueError(
                    f"SQL execution returned no results for resource type: {resource_type}"
                )

            if result.status != ExecutionStatus.SUCCESS.value:
                raise ValueError(f"SQL execution failed: {result.error}")

            result_df = result.result if isinstance(result.result, DataFrame) else None
            resource_names = (
                []
                if result_df is None or result_df.shape[1] < 1
                else result_df.iloc[:, 0].astype(str).tolist()
            )
        else:
            raise ValueError(f"Unsupported resource fetching mode: {definition.mode}")

        kind = resource_type if resource_type is not None else definition.default_type
        return [DatabaseResource(name, kind, list(definition.children)) for name in resource_names]
