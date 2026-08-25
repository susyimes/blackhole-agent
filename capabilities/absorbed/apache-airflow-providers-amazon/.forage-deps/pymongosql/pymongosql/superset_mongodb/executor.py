# -*- coding: utf-8 -*-
import logging
from typing import Any, Dict, List, Optional

from ..executor import ExecutionContext, StandardQueryExecution
from ..result_set import ResultSet
from ..sql.query_builder import QueryExecutionPlan
from .detector import SubqueryDetector
from .query_db_sqlite import QueryDBSQLite

_logger = logging.getLogger(__name__)


class SupersetExecution(StandardQueryExecution):
    """Two-stage execution strategy for subquery-based queries using intermediate RDBMS.

    Uses a QueryDatabase backend (SQLite3 by default) to handle complex
    SQL operations that MongoDB cannot perform natively.

    Attributes:
        _query_db_factory: Callable that creates QueryDatabase instances
    """

    def __init__(self, query_db_factory: Optional[Any] = None) -> None:
        """
        Initialize SupersetExecution with optional custom database backend.

        Args:
            query_db_factory: Callable that returns QueryDatabase instance.
                             Defaults to SQLiteBridge if not provided.
        """
        self._query_db_factory = query_db_factory or QueryDBSQLite
        self._execution_plan: Optional[QueryExecutionPlan] = None

    @property
    def execution_plan(self) -> QueryExecutionPlan:
        return self._execution_plan

    def supports(self, context: ExecutionContext) -> bool:
        """Support queries with subqueries, only SELECT statments is supported in this mode."""
        normalized = context.query.lstrip().upper()
        return "superset" in context.execution_mode.lower() and normalized.startswith("SELECT")

    def execute(
        self,
        context: ExecutionContext,
        connection: Any,
        parameters: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute query in two stages: MongoDB for subquery, intermediate DB for outer query"""
        _logger.debug(f"Using subquery execution for query: {context.query[:100]}")

        # Detect if query is a subquery or simple SELECT
        query_info = SubqueryDetector.detect(context.query)

        # If no subquery detected, fall back to standard execution
        if not query_info.has_subquery:
            _logger.debug("No subquery detected, falling back to standard execution")
            return super().execute(context, connection, parameters)

        # Stage 1: Execute MongoDB subquery
        mongo_query = query_info.subquery_text
        _logger.debug(f"Stage 1: Executing MongoDB subquery: {mongo_query}")

        mongo_execution_plan = self._parse_sql(mongo_query)
        mongo_result = self._execute_find_plan(mongo_execution_plan, connection)

        # Extract result set from MongoDB
        mongo_result_set = ResultSet(
            command_result=mongo_result,
            execution_plan=mongo_execution_plan,
            database=connection.database,
        )

        # Fetch all MongoDB results and convert to list of dicts
        mongo_rows = mongo_result_set.fetchall()
        _logger.debug(f"Stage 1 complete: Got {len(mongo_rows)} rows from MongoDB")

        # Convert tuple rows to dictionaries using column names
        column_names = [desc[0] for desc in mongo_result_set.description] if mongo_result_set.description else []
        mongo_dicts = []

        for row in mongo_rows:
            if column_names:
                mongo_dicts.append(dict(zip(column_names, row)))
            else:
                # Fallback if no description available
                mongo_dicts.append({"result": row})

        # Stage 2: Load results into intermediate DB and execute outer query
        db_name = self._query_db_factory.__name__ if hasattr(self._query_db_factory, "__name__") else "QueryDB"
        _logger.debug(f"Stage 2: Loading {len(mongo_dicts)} rows into {db_name}")

        query_db = self._query_db_factory()

        try:
            # Create temporary table with MongoDB results
            querydb_query, table_name = SubqueryDetector.extract_outer_query(context.query)
            if querydb_query is None or table_name is None:
                # Fallback to original query if extraction fails
                querydb_query = context.query
                table_name = "virtual_table"

            query_db.insert_records(table_name, mongo_dicts)

            # Execute outer query against intermediate DB
            _logger.debug(f"Stage 2: Executing QueryDBSQLite query: {querydb_query}")

            querydb_rows = query_db.execute_query(querydb_query)
            _logger.debug(f"Stage 2 complete: Got {len(querydb_rows)} rows from {db_name}")

            # Create a ResultSet-like object from intermediate DB results
            result_set = self._create_result_set_from_db(querydb_rows, querydb_query)

            # Build projection_stage from query database result columns
            projection_stage = {}
            if querydb_rows and isinstance(querydb_rows[0], dict):
                # Extract column names from first result row
                for col_name in querydb_rows[0].keys():
                    projection_stage[col_name] = 1  # 1 means included in projection
            else:
                # If no rows, get column names from the SQLite query directly
                try:
                    cursor = query_db.execute_query_cursor(querydb_query)
                    if cursor.description:
                        # Extract column names from cursor description
                        for col_desc in cursor.description:
                            col_name = col_desc[0]
                            projection_stage[col_name] = 1
                except Exception as e:
                    _logger.warning(f"Could not extract column names from empty result: {e}")

            self._execution_plan = QueryExecutionPlan(collection="query_db_result", projection_stage=projection_stage)

            return result_set

        finally:
            query_db.close()

    def _create_result_set_from_db(self, rows: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """
        Create a command result from query database results.

        Args:
            rows: List of dictionaries from query database
            query: Original SQL query

        Returns:
            Dictionary with command result format
        """
        # Create a mock command result structure compatible with ResultSet
        command_result = {
            "cursor": {
                "id": 0,  # No pagination for query DB results
                "firstBatch": rows,
            }
        }

        return command_result
