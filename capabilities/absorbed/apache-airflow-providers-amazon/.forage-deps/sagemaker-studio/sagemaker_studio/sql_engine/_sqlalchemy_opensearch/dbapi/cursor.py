"""
DB-API 2.0 Cursor class for OpenSearch.

This module provides the Cursor class that handles SQL statement execution
and result fetching through the OpenSearch SQL plugin.
"""

from typing import Any, Dict, List, Optional, Union

from .exceptions import (
    InterfaceError,
    OperationalError,
    ProgrammingError,
    map_opensearch_exception,
)
from .retry import RetryConfig, retry_on_transient_error


class QueryExecutor:
    """Handles query execution for the OpenSearch SQL plugin."""

    def __init__(self, connection):
        """Initialize with connection."""
        self.connection = connection
        self.client = connection.client
        self.connection_params = connection.connection_params

    def execute_query(
        self, sql: str, parameters: Optional[Union[List, Dict]] = None
    ) -> Dict[str, Any]:
        """
        Execute a SQL query using the OpenSearch SQL plugin.

        Args:
            sql: The SQL statement to execute
            parameters: Optional list or dict of parameters for the SQL statement

        Returns:
            Dict containing query execution results

        Raises:
            ProgrammingError: If SQL is invalid
        """
        # Create execution context for error handling and logging
        execution_context = {
            "sql": sql[:200] + "..." if len(sql) > 200 else sql,  # Truncate long SQL
            "parameter_count": len(parameters) if parameters else 0,
            "host": self.connection_params.host,
            "port": self.connection_params.port,
            "index": self.connection_params.index,
        }

        # Prepare query body
        body = {"query": sql}

        # Add parameters if provided
        if parameters:
            formatted_params = self._format_parameters(parameters)
            if formatted_params:
                body["parameters"] = formatted_params

        # Execute the query with retry logic for transient failures
        retry_config = RetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0)

        try:

            def submit_query():
                return self.client.transport.perform_request("POST", "/_plugins/_sql", body=body)

            response = retry_on_transient_error(
                submit_query,
                config=retry_config,
                operation_name="execute_sql_query",
                execution_context=execution_context,
            )

            return response

        except Exception as e:
            # Map OpenSearch exceptions with execution context
            mapped_exception = map_opensearch_exception(e, execution_context)
            raise mapped_exception

    def _format_parameters(self, parameters: Union[List, Dict]) -> Dict[str, Any]:
        """
        Format parameters for the OpenSearch SQL plugin.

        Args:
            parameters: List of parameter values (positional) or Dict of parameter names/values (named)

        Returns:
            Dict of formatted parameters for OpenSearch SQL
        """
        if isinstance(parameters, dict):
            # Handle named parameters
            return {name: self._format_parameter_value(value) for name, value in parameters.items()}
        else:
            # Handle positional parameters - convert to named parameters
            return {
                f"param_{i}": self._format_parameter_value(value)
                for i, value in enumerate(parameters)
            }

    def _format_parameter_value(self, param_value: Any) -> Any:
        """
        Format a single parameter value for OpenSearch SQL.

        Args:
            param_value: The parameter value to format

        Returns:
            Formatted parameter value for OpenSearch SQL
        """
        if param_value is None:
            return None
        elif isinstance(param_value, (bool, int, float, str)):
            return param_value
        elif isinstance(param_value, (list, dict)):
            return param_value
        else:
            # Convert other types to string
            return str(param_value)


class ResultConverter:
    """Converts OpenSearch SQL results to DB-API format."""

    @staticmethod
    def convert_column_metadata(schema: List[Dict[str, Any]]) -> List[tuple]:
        """
        Convert OpenSearch SQL schema to DB-API description format.

        Args:
            schema: List of column schema from OpenSearch SQL

        Returns:
            List of tuples in DB-API description format:
            (name, type_code, display_size, internal_size, precision, scale, null_ok)
        """
        description = []
        for col in schema:
            name = col.get("name", "")
            type_name = col.get("type", "text")

            # Map OpenSearch types to simplified type codes
            type_code = ResultConverter._map_type_name_to_code(type_name)

            # DB-API description format: (name, type_code, display_size, internal_size, precision, scale, null_ok)
            description.append(
                (
                    name,
                    type_code,
                    None,  # display_size - not provided by OpenSearch SQL
                    None,  # internal_size - not provided by OpenSearch SQL
                    None,  # precision - not provided by OpenSearch SQL
                    None,  # scale - not provided by OpenSearch SQL
                    True,  # null_ok - OpenSearch fields are generally nullable
                )
            )

        return description

    @staticmethod
    def _map_type_name_to_code(type_name: str) -> str:
        """
        Map OpenSearch type names to simplified type codes.

        Args:
            type_name: OpenSearch type name

        Returns:
            Simplified type code
        """
        type_mapping = {
            "text": "STRING",
            "keyword": "STRING",
            "long": "NUMBER",
            "integer": "NUMBER",
            "short": "NUMBER",
            "byte": "NUMBER",
            "double": "NUMBER",
            "float": "NUMBER",
            "half_float": "NUMBER",
            "scaled_float": "NUMBER",
            "boolean": "BOOLEAN",
            "date": "DATETIME",
            "binary": "BINARY",
            "ip": "STRING",
            "geo_point": "STRING",
            "geo_shape": "STRING",
            "object": "JSON",
            "nested": "JSON",
        }

        return type_mapping.get(type_name.lower(), "STRING")

    @staticmethod
    def convert_datarows(
        datarows: List[List[Any]], schema: List[Dict[str, Any]]
    ) -> List[List[Any]]:
        """
        Convert OpenSearch SQL datarows to Python values.

        Args:
            datarows: List of rows from OpenSearch SQL
            schema: Column schema for type conversion

        Returns:
            List of rows with converted Python values
        """
        converted_rows = []

        for row in datarows:
            converted_row = []
            for i, field in enumerate(row):
                col_type = schema[i].get("type", "text") if i < len(schema) else "text"
                converted_value = ResultConverter._convert_field_value(field, col_type)
                converted_row.append(converted_value)
            converted_rows.append(converted_row)

        return converted_rows

    @staticmethod
    def _convert_field_value(field: Any, column_type: str) -> Any:
        """
        Convert a single field value from OpenSearch SQL format to Python value.

        Args:
            field: Field value from OpenSearch SQL
            column_type: Column type name

        Returns:
            Converted Python value
        """
        # Handle null values
        if field is None:
            return None

        # For most types, OpenSearch SQL returns values in appropriate Python types
        # We may need additional conversion for specific types in the future
        column_type = column_type.lower()

        if column_type == "date":
            # Handle date/datetime conversion if needed
            # For now, return as-is since OpenSearch SQL typically returns ISO strings
            return field
        elif column_type in ("object", "nested"):
            # Ensure JSON objects are returned as dicts/lists
            if isinstance(field, str):
                try:
                    import json

                    return json.loads(field)
                except (json.JSONDecodeError, TypeError):
                    return field
            return field
        else:
            # Return as-is for other types
            return field


class Cursor:
    """DB-API 2.0 Cursor class for OpenSearch."""

    def __init__(self, connection):
        """Initialize cursor with connection."""
        self.connection = connection
        self.description = None
        self._executor = QueryExecutor(connection)
        self._result_data = []
        self._current_row = 0
        self._closed = False
        self._rowcount = -1
        self.arraysize = 1  # DB-API 2.0 default arraysize

    def execute(self, sql: str, parameters: Optional[Union[List, Dict]] = None):
        """
        Execute SQL statement.

        Args:
            sql: The SQL statement to execute
            parameters: Optional parameters for the SQL statement

        Raises:
            InterfaceError: If cursor is closed
            ProgrammingError: If SQL is invalid
            OperationalError: If execution fails
        """
        if self._closed:
            raise InterfaceError("Cursor is closed")

        # Reset cursor state
        self.description = None
        self._result_data = []
        self._current_row = 0
        self._rowcount = -1

        # Execute the query
        try:
            result = self._executor.execute_query(sql, parameters)
            self._process_result(result)
        except Exception as e:
            # Ensure OpenSearch exceptions are properly mapped
            if not isinstance(e, (InterfaceError, ProgrammingError, OperationalError)):
                mapped_exception = map_opensearch_exception(e)
                raise mapped_exception
            raise

    def _process_result(self, result: Dict[str, Any]):
        """
        Process query result and set up cursor state.

        Args:
            result: Result from OpenSearch SQL query
        """
        # Extract schema and datarows from result
        schema = result.get("schema", [])
        datarows = result.get("datarows", [])
        total = result.get("total", len(datarows))

        # Set up column metadata
        if schema:
            self.description = ResultConverter.convert_column_metadata(schema)
        else:
            self.description = []

        # Convert and store result data
        if datarows and schema:
            self._result_data = ResultConverter.convert_datarows(datarows, schema)
        else:
            self._result_data = []

        # Set rowcount
        self._rowcount = total if total is not None else len(self._result_data)

    def fetchone(self):
        """
        Fetch single row.

        Returns:
            Single row as a list or None if no more rows

        Raises:
            InterfaceError: If cursor is closed
        """
        if self._closed:
            raise InterfaceError("Cursor is closed")

        if self._current_row >= len(self._result_data):
            return None

        row = self._result_data[self._current_row]
        self._current_row += 1
        return row

    def fetchall(self):
        """
        Fetch all remaining rows.

        Returns:
            List of all remaining rows

        Raises:
            InterfaceError: If cursor is closed
        """
        if self._closed:
            raise InterfaceError("Cursor is closed")

        # Return all remaining rows
        remaining_rows = self._result_data[self._current_row :]
        self._current_row = len(self._result_data)
        return remaining_rows

    def fetchmany(self, size=None):
        """
        Fetch multiple rows.

        Args:
            size: Number of rows to fetch (default: cursor.arraysize or 1)

        Returns:
            List of up to size rows

        Raises:
            InterfaceError: If cursor is closed
        """
        if self._closed:
            raise InterfaceError("Cursor is closed")

        if size is None:
            size = getattr(self, "arraysize", 1)

        # Return up to size rows
        end_row = min(self._current_row + size, len(self._result_data))
        rows = self._result_data[self._current_row : end_row]
        self._current_row = end_row
        return rows

    def close(self):
        """Close the cursor."""
        self._closed = True
        self.description = None
        self._result_data = []
        self._current_row = 0
        self._rowcount = -1

    @property
    def rowcount(self):
        """Return number of rows affected by last operation."""
        return self._rowcount

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
